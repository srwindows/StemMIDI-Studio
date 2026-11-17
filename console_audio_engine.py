"""Motor real de consola multipista 16 buses; extiende el monitor PCM existente.

El DSP se realiza en bloques de 512 frames sobre cada pista, antes de la mezcla:
panorama stereo, trim, EQ de tres bandas, gate, compresor, saturación,
envíos de reverb/delay, ruteo y ganancias de bus, solo, mute y VU estéreo.
No se alteran WAV/FLAC/MIDI originales. El armado R imprime pistas al WAV
solo después de pulsar REC y elegir ubicación.
"""
from __future__ import annotations
import math
import os
import sys
import shutil
import queue
import threading
import wave
import re
from pathlib import Path

import numpy as np
from scipy.signal import sosfilt
from low_latency_stem_mixer import LowLatencyStemMixer, RATE, BLOCK

def ffmpeg_executable():
    """Localizar FFmpeg tanto en macOS empaquetado como en Linux/Windows."""
    root=Path(sys.executable).resolve().parent
    candidates=[os.environ.get("STEMMIDI_FFMPEG"),shutil.which("ffmpeg"),
        str(root.parent/"Resources/vendor/native/bin/ffmpeg"),
        str(root.parent/"Resources/vendor/native/bin/ffmpeg.exe"),
        str(root/"ffmpeg"),str(root/"ffmpeg.exe"),
        str(Path(__file__).resolve().parent/"ffmpeg")]
    native=os.environ.get("STEMMIDI_MAC_NATIVE_ROOT")
    if native:candidates.insert(0,str(Path(native)/"bin/ffmpeg"))
    for path in candidates:
        if path and Path(path).is_file() and os.access(path,os.X_OK):
            return str(path)
    return "ffmpeg"

DEFAULT_CHANNEL={
    "trim":0.0, "low":0.0, "mid":0.0, "high":0.0,
    "pan":0.0, "send":0.0, "delay":0.0, "gate":0.0,
    "compress":0.0, "saturation":0.0, "bus":1,
    "solo":False, "arm":False, "eq_on":True,
}
def _biquad(frequency, gain_db, typ="peak", q=.75):
    """Coeficientes RBJ para biquad shelving/peak real (SOS)."""
    A=10**(gain_db/40.)
    w=2*math.pi*frequency/RATE
    sn=math.sin(w); cs=math.cos(w)
    alpha=sn/(2*q)
    if typ=="peak":
        b0=1+alpha*A; b1=-2*cs; b2=1-alpha*A
        a0=1+alpha/A; a1=-2*cs; a2=1-alpha/A
    else:
        slope=1.
        alpha=sn/2*math.sqrt((A+1/A)*(1/slope-1)+2)
        two=2*math.sqrt(A)*alpha
        if typ=="low":
            b0=A*((A+1)-(A-1)*cs+two)
            b1=2*A*((A-1)-(A+1)*cs)
            b2=A*((A+1)-(A-1)*cs-two)
            a0=(A+1)+(A-1)*cs+two
            a1=-2*((A-1)+(A+1)*cs)
            a2=(A+1)+(A-1)*cs-two
        else:
            b0=A*((A+1)+(A-1)*cs+two)
            b1=-2*A*((A-1)+(A+1)*cs)
            b2=A*((A+1)+(A-1)*cs-two)
            a0=(A+1)-(A-1)*cs+two
            a1=2*((A-1)-(A+1)*cs)
            a2=(A+1)-(A-1)*cs-two
    return np.array([b0/a0,b1/a0,b2/a0,1.,a1/a0,a2/a0],
                    dtype=np.float64)

class ProConsoleEngine(LowLatencyStemMixer):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._channel_controls={}
        self._channel_filters={}
        self._filter_state={}
        self._bus_levels={i:1. for i in range(1,17)}
        self.bus_peaks={i:(0.,0.) for i in range(1,17)}
        self._fx_reverb=np.zeros((4800,2),np.float32)
        self._fx_delay=np.zeros((12480,2),np.float32)
        self._fx_reverb_offset=0
        self._fx_delay_offset=0
        self.recording=False
        self.recorded_blocks=0
        self.record_dropped_blocks=0
        self._record_queue=None
        self._record_thread=None
        self._record_wavs={}
        self.record_directory=None

    def _make_command(self,start_ms):
        command=super()._make_command(start_ms)
        command[0]=ffmpeg_executable()
        return command

    def configure_channel(self,name,settings):
        if not isinstance(name,str) or not isinstance(settings,dict):
            return
        cfg={**DEFAULT_CHANNEL,**self._channel_controls.get(name,{}),
             **settings}
        for key in ("trim","low","mid","high"):
            cfg[key]=max(-18.,min(18.,float(cfg[key])))
        for key in ("pan",):
            cfg[key]=max(-1.,min(1.,float(cfg[key])))
        for key in ("send","delay","gate","compress","saturation"):
            cfg[key]=max(0.,min(1.,float(cfg[key])))
        cfg["bus"]=max(1,min(16,int(cfg["bus"])))
        for key in ("solo","arm","eq_on"):
            cfg[key]=bool(cfg[key])
        changed=any(cfg[k]!=self._channel_controls.get(name,DEFAULT_CHANNEL).get(k)
                    for k in ("low","mid","high","eq_on"))
        self._channel_controls={**self._channel_controls,name:cfg}
        if changed:
            sos=[]
            if cfg["eq_on"]:
                for key,freq,typ,q in (("low",180,"low",.7),
                                       ("mid",1200,"peak",.9),
                                       ("high",5200,"high",.7)):
                    if abs(cfg[key])>.01:sos.append(_biquad(freq,cfg[key],typ,q))
            self._channel_filters={**self._channel_filters,
                                   name:np.stack(sos) if sos else None}
            self._filter_state.pop(name,None)

    def channel_settings(self,name):
        return dict(self._channel_controls.get(name,DEFAULT_CHANNEL))

    def set_bus_level(self,index,volume):
        if not 1<=int(index)<=16:return
        self._bus_levels={**self._bus_levels,
                          int(index):max(0.,min(1.5,float(volume)))}

    def _filter(self,name,stereo):
        coeff=self._channel_filters.get(name)
        if coeff is None:return stereo
        state=self._filter_state.get(name)
        if state is None or state.shape!=(coeff.shape[0],2,2):
            state=np.zeros((coeff.shape[0],2,2),dtype=np.float64)
        out,new_state=sosfilt(coeff,stereo,axis=0,zi=state)
        self._filter_state[name]=new_state
        return out.astype(np.float32,copy=False)

    def _callback(self,outdata,frames,timing,status):
        outdata.fill(0)
        if not self._running or self._paused:return
        try:chunk=self._queue.get_nowait()
        except queue.Empty:
            self.underruns+=1
            return
        if len(chunk)!=frames or outdata.shape[1]<2:return
        cfgs=self._channel_controls
        volumes=self._volumes
        names=self._names
        solo={name for name,cfg in cfgs.items() if cfg.get("solo")}
        previous=self._gain_state
        if previous.size!=len(names):
            previous=np.zeros(len(names),dtype=np.float32)
        next_gains=np.array([
            float(volumes.get(name,1.)) if name in self._selected
            and (not solo or name in solo) else 0.
            for name in names],dtype=np.float32)
        destinations={}
        direct=np.zeros((frames,2),dtype=np.float32)
        wet_reverb=np.zeros_like(direct)
        wet_delay=np.zeros_like(direct)
        peaks={}
        tap={}
        for i,name in enumerate(names):
            cfg=cfgs.get(name,DEFAULT_CHANNEL)
            current=next_gains[i]
            if not current and not previous[i]:
                peaks[name]=(0.,0.)
                continue
            a=chunk[:,i,:].copy()
            a=self._filter(name,a)
            gate=cfg["gate"]
            if gate:
                threshold=.0015+.06*(gate**2)
                envelope=np.sqrt(np.mean(a*a,axis=1))
                # Suave reducción con apertura dinámica; evita un corte duro.
                gain=np.clip((envelope-threshold*.3)/(threshold*.7+1e-8),.06,1.)
                a*=gain[:,None].astype(np.float32)
            comp=cfg["compress"]
            if comp:
                threshold=.3-.22*comp
                ratio=1.+7*comp
                magnitude=np.abs(a)
                a=np.sign(a)*np.where(magnitude>threshold,
                    threshold+(magnitude-threshold)/ratio,magnitude)
            saturate=cfg["saturation"]
            if saturate:
                drive=1+4*saturate
                a=np.tanh(a*drive)/drive
            a*=10**(cfg["trim"]/20.)
            pan=cfg["pan"]
            a[:,0]*=1.-max(0.,pan)
            a[:,1]*=1.+min(0.,pan)
            if abs(float(previous[i]-current))>.0001:
                ramp=previous[i]+self._fade[:frames]*(current-previous[i])
                a*=ramp[:,None]
            else:
                a*=current
            peaks[name]=(float(np.max(np.abs(a[:,0]))),
                         float(np.max(np.abs(a[:,1]))))
            bus=cfg["bus"]
            if bus not in destinations:
                destinations[bus]=np.zeros_like(direct)
            destinations[bus]+=a
            if cfg["send"]:wet_reverb+=a*cfg["send"]
            if cfg["delay"]:wet_delay+=a*cfg["delay"]
            if self.recording and cfg["arm"]:tap[name]=a.copy()
        self._gain_state=next_gains
        outbus={}
        bus_levels=self._bus_levels
        bus_peaks={}
        for index,mix in destinations.items():
            outbus[index]=mix*bus_levels.get(index,1.)
            direct+=outbus[index]
            bus_peaks[index]=(float(np.max(np.abs(outbus[index][:,0]))),
                              float(np.max(np.abs(outbus[index][:,1]))))
        self.bus_peaks={i:bus_peaks.get(i,(0.,0.)) for i in range(1,17)}
        if not np.any(next_gains) and not np.any(previous):
            # Mute TOTAL: evitar que la cola del FX deje voz audible.
            self._fx_reverb.fill(0)
            self._fx_delay.fill(0)
        # Dos envíos de efectos REALES (retorno a máster, sin alterar pistas).
        # Las colas circulares conservan su estado entre bloques.
        for src,ring,feedback,mix,attr in (
            (wet_reverb,self._fx_reverb,.38,.22,"_fx_reverb_offset"),
            (wet_delay,self._fx_delay,.33,.37,"_fx_delay_offset")):
            if np.max(np.abs(src))==0 and np.max(np.abs(ring))<1e-6:
                continue
            pos=getattr(self,attr)
            indices=(pos+np.arange(frames))%len(ring)
            delayed=ring[indices].copy()
            ring[indices]=src+delayed*feedback
            direct+=delayed*mix
            setattr(self,attr,(pos+frames)%len(ring))
        active=max(1.,float(np.count_nonzero(next_gains)))
        direct*=self._master_volume/math.sqrt(active)
        peak=float(np.max(np.abs(direct)))
        if peak>.95:direct*=.95/peak
        outdata[:,:2]=direct
        self.track_peaks=peaks
        maxes=np.max(np.abs(direct),axis=0)
        self.master_peaks=(float(maxes[0]),float(maxes[1]))
        self.last_mix_level=float(np.max(maxes))
        self._frames_played+=frames
        self.blocks+=1
        if self._last_mask_applied_ns<self._last_mask_update_ns:
            self._last_mask_applied_ns=__import__("time").monotonic_ns()
        if self.recording and self._record_queue is not None:
            try:self._record_queue.put_nowait((direct.copy(),tap))
            except queue.Full:self.record_dropped_blocks+=1

    def start_recording(self,directory):
        if self.recording:return False
        dest=Path(directory).expanduser().resolve()
        if not dest.is_dir():return False
        self.record_directory=dest
        self.record_dropped_blocks=0
        self.recorded_blocks=0
        self._record_queue=queue.Queue(maxsize=256)
        self._record_wavs={}
        from datetime import datetime
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
        outputs={"MASTER":dest/f"Mezcla_master_{stamp}.wav"}
        if outputs["MASTER"].exists():
            for index in range(2,1000):
                alternative=dest/f"Mezcla_master_{stamp}_{index}.wav"
                if not alternative.exists():
                    outputs["MASTER"]=alternative
                    break
        used={str(outputs["MASTER"])}
        for name,cfg in self._channel_controls.items():
            if cfg.get("arm") and name in self._names:
                clean=re.sub(r"[^A-Za-z0-9_.-]+","_",Path(name).stem)[-42:]
                path=dest/f"Pista_{clean}_{stamp}.wav"
                index=2
                while str(path) in used or path.exists():
                    path=dest/f"Pista_{clean}_{stamp}_{index}.wav"
                    index+=1
                outputs[name]=path
                used.add(str(path))
        for name,path in outputs.items():
            f=wave.open(str(path),"wb")
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(RATE)
            self._record_wavs[name]=f
        def writer():
            try:
                while True:
                    item=self._record_queue.get()
                    if item is None:break
                    mix,taps=item
                    for name,data in (("MASTER",mix),*taps.items()):
                        if name in self._record_wavs:
                            samples=(np.clip(data,-1,1)*32767).astype("<i2")
                            self._record_wavs[name].writeframes(samples.tobytes())
                    self.recorded_blocks+=1
            finally:
                for f in self._record_wavs.values():
                    f.close()
                self._record_wavs.clear()
        self._record_thread=threading.Thread(target=writer,
            name="StemMIDI-Consola-WAV",daemon=True)
        self.recording=True
        self._record_thread.start()
        return True

    def stop_recording(self):
        if not self.recording:return
        self.recording=False
        queue_=self._record_queue
        if queue_ is not None:
            try:queue_.put(None,timeout=2)
            except queue.Full:
                # Drenar cola si el disco se ha ralentizado.
                while True:
                    try:queue_.put(None,timeout=.5);break
                    except queue.Full:continue
        if self._record_thread:
            self._record_thread.join(timeout=8)
        self._record_thread=None
        self._record_queue=None

    def stop(self):
        self.stop_recording()
        super().stop()
        self.bus_peaks={i:(0.,0.) for i in range(1,17)}
        self._filter_state.clear()
        self._fx_reverb.fill(0)
        self._fx_delay.fill(0)
        self._fx_reverb_offset=0
        self._fx_delay_offset=0
