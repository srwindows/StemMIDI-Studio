"""Reproducción continua multipista: mute en vivo mediante FFmpeg azmq.

Audio de los stems originales en un único flujo; las casillas solo cambian
filtros volume dinámicos, nunca reconstruyen mezcla ni reinician el reloj.
FFplay usa la misma salida PulseAudio elegida por el programa.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import math
import os
import queue
import random
import signal
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from audio_import import probe_audio
from preview_player import AudioRoute


class _LiveFilterCommands:
    """REQ/REP de FFmpeg en hilo aparte: nunca bloquear la interfaz Qt."""
    def __init__(self,port):
        self.port=port
        self._messages=queue.Queue()
        self._thread=threading.Thread(target=self._work,daemon=True,
                                      name="StemMIDI-MuteEnVivo")
        self._thread.start()

    def update(self,index,enabled):
        self._messages.put((index,bool(enabled)))

    def close(self):
        self._messages.put(None)

    def _work(self):
        library=ctypes.util.find_library("zmq")
        if not library:return
        z=ctypes.CDLL(library)
        z.zmq_ctx_new.restype=ctypes.c_void_p
        z.zmq_socket.argtypes=[ctypes.c_void_p,ctypes.c_int]
        z.zmq_socket.restype=ctypes.c_void_p
        z.zmq_connect.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        z.zmq_send.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_int]
        z.zmq_recv.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
        z.zmq_setsockopt.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t]
        z.zmq_close.argtypes=[ctypes.c_void_p]
        z.zmq_ctx_term.argtypes=[ctypes.c_void_p]
        context=z.zmq_ctx_new()
        try:
            while True:
                item=self._messages.get()
                if item is None:break
                index,on=item
                # Un cambio de volumen dura unas milésimas de segundo;
                # si FFmpeg aún está arrancando, reintentar sin detenerlo.
                for trial in range(14):
                    socket=z.zmq_socket(context,3)  # ZMQ_REQ
                    timeout=ctypes.c_int(160)
                    for opt in (27,28):  # ZMQ_RCVTIMEO / ZMQ_SNDTIMEO
                        z.zmq_setsockopt(socket,opt,ctypes.byref(timeout),
                                         ctypes.sizeof(timeout))
                    try:
                        z.zmq_connect(socket,
                            f"tcp://127.0.0.1:{self.port}".encode())
                        msg=f"volume@s{index} volume {1 if on else 0}".encode()
                        rc=z.zmq_send(socket,msg,len(msg),0)
                        buffer=ctypes.create_string_buffer(256)
                        if rc>=0 and z.zmq_recv(socket,buffer,256,0)>0:
                            if buffer.value.startswith(b"0 "):break
                    finally:
                        z.zmq_close(socket)
                    time.sleep(.08)
        finally:
            z.zmq_ctx_term(context)


class LiveStemMixer(QObject):
    changed=Signal()
    error=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self._decoder=None
        self._sink=None
        self._commands=None
        self._names=[]
        self._files=[]
        self._selected=set()
        self._port=None
        self._start_ms=0
        self._anchor=0.
        self._paused=False
        self._duration_ms=0
        self._position_ms=0
        self._stopping=False

    @property
    def duration_ms(self):
        return self._duration_ms

    @property
    def selected(self):
        return set(self._selected)

    @property
    def running(self):
        return self._sink is not None and self._sink.poll() is None

    @property
    def paused(self):
        return self._paused

    def position(self):
        if self.running and not self._paused:
            return min(self._duration_ms,
                self._start_ms+int((time.monotonic()-self._anchor)*1000))
        return self._position_ms

    def start(self,entries,selected,start_ms=0):
        """entries: (nombre, archivo) estables para TODO el periodo."""
        self.stop()
        inputs=[(name,Path(path).resolve()) for name,path in entries
                if Path(path).is_file()]
        if not inputs:return False
        self._names=[name for name,_ in inputs]
        self._files=[path for _,path in inputs]
        self._selected=set(selected)&set(self._names)
        try:
            self._duration_ms=round(max(probe_audio(p)["duration"] for p in self._files)*1000)
        except (OSError,ValueError,KeyError) as exc:
            self.error.emit("No se pudo leer la duración de los stems: "+str(exc))
            return False
        start_ms=max(0,min(int(start_ms),max(0,self._duration_ms-500)))
        self._port=random.randint(26000,45000)
        command=["ffmpeg","-nostdin","-hide_banner","-loglevel","error"]
        for i,path in enumerate(self._files):
            # El primer input gobierna la cadencia de decodificación;
            # FFmpeg no debe producir minutos por delante de FFplay.
            if i==0:command+=["-re"]
            if start_ms:command+=["-ss",f"{start_ms/1000:.3f}"]
            command+=["-i",str(path)]
        filters=[]
        for i in range(len(inputs)):
            volume=1 if self._names[i] in self._selected else 0
            filters.append(
                f"[{i}:a:0]aresample=48000,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"volume@s{i}={volume}:eval=frame[a{i}]")
        joined="".join(f"[a{i}]" for i in range(len(inputs)))
        # Limitar los picos de la suma, manteniendo independencia del mute.
        filters.append(f"{joined}amix=inputs={len(inputs)}:"
                       "duration=longest:dropout_transition=0:normalize=0,"
                       "alimiter=limit=0.95,"
                       f"azmq=bind_address=tcp\\\\://127.0.0.1\\\\:{self._port}[out]")
        command+=["-filter_complex",";".join(filters),"-map","[out]",
                  "-vn","-ar","48000","-ac","2","-f","f32le","pipe:1"]
        sink=["ffplay","-nodisp","-autoexit","-loglevel","error",
              "-f","f32le","-ar","48000","-ch_layout","stereo","-i","pipe:0"]
        env=os.environ.copy()
        env.setdefault("SDL_AUDIODRIVER","pulseaudio")
        device=AudioRoute.current_id()
        if device:env["PULSE_SINK"]=device
        if env.get("STEMMIDI_TEST_DUMMY_AUDIO")=="1":
            env["SDL_AUDIODRIVER"]="dummy"
        try:
            decoder=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                start_new_session=True)
            sink_proc=subprocess.Popen(sink,stdin=decoder.stdout,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                env=env,start_new_session=True)
            decoder.stdout.close()
        except OSError as exc:
            if "decoder" in locals():
                decoder.terminate()
            self.error.emit("Motor de escucha multipista no disponible: "+str(exc))
            return False
        self._decoder=decoder
        self._sink=sink_proc
        self._commands=_LiveFilterCommands(self._port)
        self._start_ms=start_ms
        self._position_ms=start_ms
        self._anchor=time.monotonic()
        self._paused=False
        self.changed.emit()
        return True

    def set_enabled(self,name,enabled):
        if name not in self._names:return False
        before=name in self._selected
        if before==bool(enabled):return True
        if enabled:self._selected.add(name)
        else:self._selected.discard(name)
        if self._commands is not None:
            self._commands.update(self._names.index(name),enabled)
        self.changed.emit()
        return True

    def pause(self):
        if not self.running:return
        if not self._paused:
            self._position_ms=self.position()
            for proc in (self._decoder,self._sink):
                if proc is not None and proc.poll() is None:
                    try:os.killpg(proc.pid,signal.SIGSTOP)
                    except (OSError,ProcessLookupError):pass
            self._paused=True
        else:
            for proc in (self._decoder,self._sink):
                if proc is not None and proc.poll() is None:
                    try:os.killpg(proc.pid,signal.SIGCONT)
                    except (OSError,ProcessLookupError):pass
            self._start_ms=self._position_ms
            self._anchor=time.monotonic()
            self._paused=False
        self.changed.emit()

    def seek(self,position_ms):
        if not self._files:return False
        current=list(zip(self._names,self._files))
        selected=set(self._selected)
        paused=self._paused
        if not self.start(current,selected,start_ms=position_ms):return False
        if paused:self.pause()
        return True

    def stop(self):
        if self.running:self._position_ms=self.position()
        if self._commands is not None:self._commands.close()
        self._commands=None
        for proc in (self._decoder,self._sink):
            if proc is None:continue
            try:
                if proc.poll() is None:
                    try:os.killpg(proc.pid,signal.SIGCONT)
                    except (OSError,ProcessLookupError):pass
                    proc.terminate()
                proc.wait(timeout=.35)
            except (OSError,subprocess.TimeoutExpired):
                try:proc.kill()
                except OSError:pass
                try:proc.wait(timeout=.35)
                except (OSError,subprocess.TimeoutExpired):pass
        self._decoder=None
        self._sink=None
        self._paused=False
        self.changed.emit()
