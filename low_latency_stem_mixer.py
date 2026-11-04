"""Mezclador multipista de latencia baja: mute aplicado en la salida PCM.

FFmpeg decodifica todas las pistas a canales independientes, N*estéreo.
PortAudio mezcla cada bloque de 512 muestras justo antes de reproducir.
NO se envían comandos de mute a un decodificador adelantado.
"""
from __future__ import annotations
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Signal

from audio_import import probe_audio
from preview_player import AudioRoute

RATE=48000
BLOCK=512
MAX_PENDING=12

class _DummyStream:
    """Simulación sin salida física, solamente para pruebas del motor."""
    def __init__(self,callback):
        self.callback=callback
        self._stop=threading.Event()
        self._thread=None
    def start(self):
        self._stop.clear()
        def loop():
            next_tick=time.monotonic()
            while not self._stop.is_set():
                self.callback(np.zeros((BLOCK,2),dtype=np.float32),BLOCK,None,None)
                next_tick+=BLOCK/RATE
                self._stop.wait(max(0,next_tick-time.monotonic()))
        self._thread=threading.Thread(target=loop,daemon=True)
        self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread and threading.current_thread()!=self._thread:
            self._thread.join(timeout=.25)
    def close(self):self.stop()

class LowLatencyStemMixer(QObject):
    changed=Signal()
    error=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self._decoder=None
        self._stream=None
        self._decode_thread=None
        self._done=threading.Event()
        self._eof=False
        self._queue=queue.Queue(maxsize=MAX_PENDING)
        self._names=[]
        self._files=[]
        self._selected=frozenset()
        self._start_ms=0
        self._position_ms=0
        self._duration_ms=0
        self._frames_played=0
        self._paused=False
        self._running=False
        self.underruns=0
        self.blocks=0
        self.last_mix_level=0.0
        # Instantáneas atómicas calculadas sobre PCM REAL en el callback,
        # sin cálculos de audio dentro del hilo gráfico Qt.
        self.track_peaks={}
        self.master_peaks=(0.,0.)
        self._last_mask_update_ns=0
        self._last_mask_applied_ns=0
        self._last_output=[]
        self._gain_state=np.zeros(0,dtype=np.float32)
        self._volumes={}
        self._fade=np.linspace(1/BLOCK,1,BLOCK,dtype=np.float32)
    @property
    def duration_ms(self):return self._duration_ms
    @property
    def selected(self):return set(self._selected)
    @property
    def running(self):return self._running
    @property
    def paused(self):return self._paused
    def position(self):
        return min(self._duration_ms,self._start_ms+
                   round(self._frames_played*1000/RATE))

    def _decode(self,proc,channels):
        size=BLOCK*channels*4
        tail=bytearray()
        try:
            while not self._done.is_set():
                chunk=proc.stdout.read(size*3)
                if not chunk:break
                tail.extend(chunk)
                while len(tail)>=size and not self._done.is_set():
                    data=bytes(tail[:size])
                    del tail[:size]
                    frame=np.frombuffer(data,dtype="<f4").reshape(
                        BLOCK,len(self._names),2).copy()
                    while not self._done.is_set():
                        try:self._queue.put(frame,timeout=.05);break
                        except queue.Full:continue
        except (OSError,ValueError):
            pass
        finally:self._eof=True

    def _callback(self,outdata,frames,timing,status):
        outdata.fill(0)
        if not self._running or self._paused:return
        try:chunk=self._queue.get_nowait()
        except queue.Empty:
            self.underruns+=1
            return
        if len(chunk)!=frames:
            return
        names=self._names
        selected=self._selected
        # Ganancias procedentes de los faders ÚNICOS del Mezclador.
        # Lectura atómica de dict inmutable sustituido en la GUI.
        volumes=self._volumes
        target=np.fromiter((float(volumes.get(name,1.))
                            if name in selected else 0. for name in names),
                           dtype=np.float32,count=len(names))
        previous=self._gain_state
        if previous.size!=len(target):previous=np.zeros(len(target),dtype=np.float32)
        if np.array_equal(previous,target):
            mask=np.flatnonzero(target)
            if mask.size:
                # Importante: también en régimen ESTABLE aplicar las
                # ganancias a cada pista. La suma sin target provocaba
                # que cualquier fader mayor de cero sonase al 100 %.
                outdata[:]=np.einsum(
                    "fsc,s->fc",chunk[:,mask,:],target[mask],optimize=False)
        else:
            # Fundido de 10,7 ms para evitar clics al marcar/desmarcar.
            fades=(previous[None,:]+self._fade[:,None]*(target-previous)[None,:])
            outdata[:]=np.einsum('fsc,fs->fc',chunk,fades,optimize=False)
            self._gain_state=target
        # Medición PRE-canal real, con la misma ganancia y mute que se
        # aplican al mezclador (ninguna barra inventada a partir del máster).
        measured=np.max(np.abs(chunk),axis=0)*target[:,None]
        self.track_peaks={name:(float(measured[i,0]),float(measured[i,1]))
                          for i,name in enumerate(names)}
        # Compensación energética + limitador de picos sin hard clipping.
        active=max(1.,float(np.count_nonzero(target)))
        outdata[:]/=np.sqrt(active)
        peak=float(np.max(np.abs(outdata)))
        if peak>.95:outdata[:]*=.95/peak
        self._frames_played+=frames
        self.blocks+=1
        self.last_mix_level=float(np.max(np.abs(outdata)))
        stereo=np.max(np.abs(outdata),axis=0)
        self.master_peaks=(float(stereo[0]),float(stereo[1]))
        if self._last_mask_applied_ns<self._last_mask_update_ns:
            self._last_mask_applied_ns=time.monotonic_ns()

    def _make_command(self,start_ms):
        n=len(self._files)
        cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error"]
        for file in self._files:
            if start_ms:cmd+=["-ss",f"{start_ms/1000:.3f}"]
            cmd+=["-i",str(file)]
        remain=max(.1,(self._duration_ms-start_ms)/1000)
        filters=[]
        for i in range(n):
            filters.append(f"[{i}:a:0]aresample={RATE},"
                           "aformat=channel_layouts=stereo,"
                           f"apad,atrim=duration={remain:.4f}[s{i}]")
        filters.append("".join(f"[s{i}]" for i in range(n))+
                       f"amerge=inputs={n}[out]")
        return cmd+["-filter_complex",";".join(filters),
                    "-map","[out]","-f","f32le","-ar",str(RATE),
                    "-ac",str(n*2),"pipe:1"]

    def start(self,entries,selected,start_ms=0,duration_ms=None):
        self.stop()
        tracks=[(name,Path(path).resolve()) for name,path in entries
                if Path(path).is_file()]
        if not tracks:return False
        self._names=[name for name,_ in tracks]
        self._files=[path for _,path in tracks]
        self._selected=frozenset(selected)&frozenset(self._names)
        try:
            self._duration_ms=(int(duration_ms) if duration_ms and duration_ms>0
                else round(max(probe_audio(path)["duration"]
                               for path in self._files)*1000))
        except (ValueError,OSError,KeyError) as exc:
            self.error.emit("No se pudo abrir el audio: "+str(exc));return False
        start_ms=max(0,min(int(start_ms),max(0,self._duration_ms-500)))
        self._start_ms=start_ms
        self._position_ms=start_ms
        self._frames_played=0
        self._gain_state=np.zeros(len(self._names),dtype=np.float32)
        self.track_peaks={name:(0.,0.) for name in self._names}
        self.master_peaks=(0.,0.)
        self._paused=False
        self._eof=False
        self.underruns=0
        self.blocks=0
        self._queue=queue.Queue(maxsize=MAX_PENDING)
        self._done.clear()
        cmd=self._make_command(start_ms)
        try:
            self._decoder=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            self._decode_thread=threading.Thread(
                target=self._decode,args=(self._decoder,len(self._names)*2),
                name="StemMIDI-PCM-Salida",daemon=True)
            self._decode_thread.start()
            # Abrir PulseAudio en el sink configurado por la aplicación.
            # PortAudio/pulse mantiene la misma selección del sistema.
            selected_sink=AudioRoute.current_id()
            old_sink=os.environ.get("PULSE_SINK")
            if selected_sink:os.environ["PULSE_SINK"]=selected_sink
            try:
                if os.environ.get("STEMMIDI_TEST_DUMMY_AUDIO")=="1":
                    self._stream=_DummyStream(self._callback)
                else:
                    self._stream=sd.OutputStream(
                        samplerate=RATE,channels=2,dtype="float32",
                        blocksize=BLOCK,latency="low",device="pulse",
                        callback=self._callback)
            finally:
                if old_sink is None:os.environ.pop("PULSE_SINK",None)
                else:os.environ["PULSE_SINK"]=old_sink
            # Solo se acumulan ~128 ms de PCM SIN MEZCLAR.
            # El mute responde al siguiente bloque de 10.7 ms.
            self._running=True
            self._stream.start()
            self.changed.emit()
            return True
        except Exception as exc:
            self.error.emit("No se pudo abrir la salida multipista: "+str(exc))
            self.stop()
            return False

    def set_track_levels(self,levels):
        """Reutilizar los faders globales sin reiniciar la reproducción."""
        self._volumes={name:max(0.,min(1.5,float(level)))
                       for name,level in levels.items()}

    def set_enabled(self,name,enabled):
        if name not in self._names:return False
        before=self._selected
        selected=set(before)
        if enabled:selected.add(name)
        else:selected.discard(name)
        if before==frozenset(selected):return True
        self._selected=frozenset(selected)
        self._last_mask_update_ns=time.monotonic_ns()
        self.changed.emit()
        return True

    def pause(self):
        if not self.running:return
        if self._paused:
            self._paused=False
            if self._stream:self._stream.start()
        else:
            if self._stream:self._stream.stop()
            self._paused=True
        self.changed.emit()

    def seek(self,position_ms):
        if not self._files:return False
        entries=list(zip(self._names,self._files))
        selection=self._selected
        was_paused=self._paused
        if not self.start(entries,selection,start_ms=position_ms,
                          duration_ms=self._duration_ms):return False
        if was_paused:self.pause()
        return True

    def stop(self):
        self._running=False
        self._done.set()
        if self._stream is not None:
            try:self._stream.stop();self._stream.close()
            except Exception:pass
        self._stream=None
        if self._decoder is not None:
            try:
                if self._decoder.poll() is None:self._decoder.terminate()
                self._decoder.wait(timeout=.4)
            except (OSError,subprocess.TimeoutExpired):
                try:self._decoder.kill();self._decoder.wait(timeout=.4)
                except Exception:pass
            try:
                if self._decoder.stdout:self._decoder.stdout.close()
            except OSError:pass
        self._decoder=None
        self._paused=False
        self.master_peaks=(0.,0.)
        self.track_peaks={}
        self.changed.emit()
