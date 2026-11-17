"""Channel EQ de ocho bandas original para StemMIDI Studio.

8 bandas: high-pass, low shelf, four bells, high shelf, low-pass.
C++ nativo sin cargar VST/AU externos. Ajustes en tiempo real.
"""
from __future__ import annotations
import ctypes
import math
import time
import sys
import threading
from pathlib import Path
import numpy as np

RATE=48000
TYPES=("HP","LOW_SHELF","BELL","BELL","BELL","BELL","HIGH_SHELF","LP")
DEFAULT_FREQ=(35.,90.,250.,700.,2000.,5500.,9500.,17500.)
BAND_COLORS=("#fa6668","#f5a45b","#f6d34c","#65d872","#50cfcf","#64afff","#bb84ff","#f57cb7")
MODES=("Stereo","Left Only","Right Only","Mid Only","Side Only")
_FLOAT=ctypes.POINTER(ctypes.c_float)
_DLL=None

def library():
    global _DLL
    if _DLL is not None:return _DLL
    root=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
    candidates=(root/"libstemmidi_channel_eq.dylib",
                root/"vendor/native/lib/libstemmidi_channel_eq.dylib",
                Path(__file__).resolve().parent/"libstemmidi_channel_eq.dylib")
    for path in candidates:
        if not path.is_file():continue
        lib=ctypes.CDLL(str(path))
        lib.stem_eq_create.argtypes=[ctypes.c_int]
        lib.stem_eq_create.restype=ctypes.c_void_p
        lib.stem_eq_destroy.argtypes=[ctypes.c_void_p]
        lib.stem_eq_reset.argtypes=[ctypes.c_void_p]
        lib.stem_eq_set_band.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,
            ctypes.c_double,ctypes.c_double,ctypes.c_double,ctypes.c_int]
        lib.stem_eq_set_band.restype=ctypes.c_int
        lib.stem_eq_set_gain.argtypes=[ctypes.c_void_p,ctypes.c_double]
        lib.stem_eq_set_mode.argtypes=[ctypes.c_void_p,ctypes.c_int]
        lib.stem_eq_set_hq.argtypes=[ctypes.c_void_p,ctypes.c_int]
        lib.stem_eq_process.argtypes=[ctypes.c_void_p,_FLOAT,_FLOAT,ctypes.c_int]
        _DLL=lib;return lib
    raise RuntimeError("Falta libstemmidi_channel_eq.dylib en la instalación")

class ChannelEQ:
    is_effect=True
    def __init__(self,rate=RATE):
        self.rate=int(rate)
        self._dll=library()
        self._handle=self._dll.stem_eq_create(self.rate)
        if not self._handle:raise RuntimeError("No se pudo crear Channel EQ")
        self.bands=[dict(enabled=i not in (0,7),hz=float(DEFAULT_FREQ[i]),
                         gain=0.,q=.707,slope=12) for i in range(8)]
        self.output_gain_db=0.
        self.mode=0
        self.hq=False
        self.analyzer="Post"
        self.analyzer_mode="Peak"
        self.analyzer_decay_db_s=24.
        self.resolution=2048
        self.q_couple=False
        self.q_couple_strength="Medium"

        self._revision=0
        self._analyzer_lock=threading.Lock()
        self._analyzer_pcm=np.zeros(8192,dtype=np.float32)
        self._analyzer_seen=0
        self._analyzer_previous=None
        self._analyzer_last_time=None
        for i in range(8):self._update(i)

    def __del__(self):
        handle=getattr(self,"_handle",None)
        if handle:
            self._dll.stem_eq_destroy(handle)
            self._handle=None

    def _update(self,i):
        b=self.bands[i]
        self._dll.stem_eq_set_band(self._handle,i,int(b["enabled"]),
            b["hz"],b["gain"],b["q"],b["slope"])
        self._revision+=1

    def set_band(self,index,**values):
        if not 0<=index<8:raise IndexError(index)
        b=self.bands[index].copy()
        for key,value in values.items():
            if key not in b:raise KeyError(key)
            if key=="enabled":b[key]=bool(value)
            elif key=="hz":b[key]=max(20.,min(20000.,float(value)))
            elif key=="gain":b[key]=max(-24.,min(24.,float(value)))
            elif key=="q":b[key]=max(.1,min(100.,float(value)))
            elif key=="slope":b[key]=min((6,12,18,24,36,48),
                key=lambda slope:abs(slope-int(value)))
        self.bands[index]=b
        self._update(index)

    def set_output_gain(self,value):
        self.output_gain_db=max(-24.,min(24.,float(value)))
        self._dll.stem_eq_set_gain(self._handle,self.output_gain_db)
        self._revision+=1

    def set_mode(self,value):
        self.mode=max(0,min(4,int(value)))
        self._dll.stem_eq_set_mode(self._handle,self.mode)

    def set_hq(self,enabled):
        self.hq=bool(enabled)
        self._dll.stem_eq_set_hq(self._handle,int(self.hq))

    def reset(self):
        self._dll.stem_eq_reset(self._handle)
        self._analyzer_previous=None
        self._analyzer_last_time=None

    def snapshot(self):
        return dict(bands=[b.copy() for b in self.bands],
            output_gain_db=self.output_gain_db,mode=self.mode,
            analyzer=self.analyzer,analyzer_mode=self.analyzer_mode,
            analyzer_decay_db_s=self.analyzer_decay_db_s,
            resolution=self.resolution,q_couple=self.q_couple,
            q_couple_strength=self.q_couple_strength,hq=self.hq)

    def restore(self,state):
        if not isinstance(state,dict):return
        bands=state.get("bands",[])
        if isinstance(bands,list):
            for i,band in enumerate(bands[:8]):
                if isinstance(band,dict):
                    self.set_band(i,**{k:v for k,v in band.items()
                        if k in self.bands[i]})
        self.set_output_gain(state.get("output_gain_db",0))
        self.set_mode(state.get("mode",0))
        self.set_hq(state.get("hq",False))
        self.analyzer=state.get("analyzer","Post") if state.get("analyzer","Post") in ("Off","Pre","Post") else "Post"
        self.analyzer_mode=state.get("analyzer_mode","Peak") if state.get("analyzer_mode","Peak") in ("Peak","RMS") else "Peak"
        self.analyzer_decay_db_s=max(0.,min(90.,float(state.get("analyzer_decay_db_s",24.))))
        self.resolution=int(state.get("resolution",2048))
        if self.resolution not in (1024,2048,4096,8192):self.resolution=2048
        self.q_couple=bool(state.get("q_couple",False))
        self.q_couple_strength=state.get("q_couple_strength","Medium")
        if self.q_couple_strength not in ("Proportional","Light","Medium","Strong","Asymmetric"):
            self.q_couple_strength="Medium"

    def process_stereo(self,a):
        x=np.ascontiguousarray(a,dtype=np.float32)
        if x.ndim!=2 or x.shape[1]!=2:
            raise ValueError("Channel EQ requiere estéreo (frames,2)")
        y=np.empty_like(x)
        if self.analyzer=="Pre":self._collect(x)
        self._dll.stem_eq_process(self._handle,x.ctypes.data_as(_FLOAT),
                                  y.ctypes.data_as(_FLOAT),len(x))
        if self.analyzer=="Post":self._collect(y)
        return y

    def process(self,a,sample_rate=RATE,buffer_size=None,reset=False):
        if int(sample_rate)!=self.rate:
            raise ValueError("Tasa de muestreo distinta de Channel EQ")
        x=np.asarray(a,dtype=np.float32)
        if x.ndim!=2 or x.shape[0]!=2:raise ValueError("Se requiere estéreo (2,frames)")
        if reset:self.reset()
        return self.process_stereo(x.T).T.copy()

    def _collect(self,x):
        # Solo una instantánea acotada; FFT en el hilo UI, nunca en DSP.
        if self._analyzer_lock.acquire(blocking=False):
            try:
                mono=np.asarray(x[:,0]*.5+x[:,1]*.5,dtype=np.float32)
                if len(mono)>=len(self._analyzer_pcm):
                    self._analyzer_pcm[:]=mono[-len(self._analyzer_pcm):]
                else:
                    self._analyzer_pcm=np.roll(self._analyzer_pcm,-len(mono))
                    self._analyzer_pcm[-len(mono):]=mono
                self._analyzer_seen+=1
            finally:self._analyzer_lock.release()

    def spectrum(self):
        with self._analyzer_lock:
            block=self._analyzer_pcm[-self.resolution:].copy()
        fft=np.abs(np.fft.rfft(block*np.hanning(len(block))))*2/len(block)
        if self.analyzer_mode=="RMS":fft/=math.sqrt(2)
        db=20*np.log10(np.maximum(fft,1e-9))
        now=time.monotonic()
        if self._analyzer_previous is not None and len(self._analyzer_previous)==len(db):
            elapsed=max(0.,min(2.,now-(self._analyzer_last_time or now)))
            db=np.maximum(db,self._analyzer_previous-self.analyzer_decay_db_s*elapsed)
        self._analyzer_previous=db.copy()
        self._analyzer_last_time=now
        return np.fft.rfftfreq(len(block),1/self.rate),db

    def response_db(self,freqs):
        f=np.asarray(freqs,dtype=np.float64)
        internal_rate=self.rate*(2 if self.hq else 1)
        z=np.exp(-2j*np.pi*f/internal_rate)
        result=np.full(f.shape,self.output_gain_db,dtype=np.float64)
        for i,b in enumerate(self.bands):
            if not b["enabled"]:continue
            typ=TYPES[i]
            hz=min(b["hz"],internal_rate*.475)
            q=b["q"];g=b["gain"]
            if typ in ("HP","LP"):
                poles=max(1,min(8,b["slope"]//6))
                for k in range(poles//2):
                    butter=1/(2*math.sin(math.pi*(2*k+1)/(2*poles)))
                    qk=max(.1,min(100.,butter*q/.7071067811865476))
                    w=2*math.pi*hz/internal_rate
                    cs=math.cos(w);alpha=math.sin(w)/(2*qk)
                    if typ=="HP":
                        b0=(1+cs)/2;b1=-(1+cs);b2=b0
                    else:
                        b0=(1-cs)/2;b1=1-cs;b2=b0
                    a0=1+alpha;a1=-2*cs;a2=1-alpha
                    response=(b0+b1*z+b2*z*z)/(a0+a1*z+a2*z*z)
                    result+=20*np.log10(np.maximum(np.abs(response),1e-12))
                if poles%2:
                    k=math.tan(math.pi*hz/internal_rate)
                    b0=(1. if typ=="HP" else k)/(1+k)
                    b1=-b0 if typ=="HP" else b0
                    a1=(k-1)/(k+1)
                    response=(b0+b1*z)/(1+a1*z)
                    result+=20*np.log10(np.maximum(np.abs(response),1e-12))
                continue
            w=2*math.pi*hz/internal_rate;cs=math.cos(w);sn=math.sin(w)
            alpha=sn/(2*q);A=10**(g/40)
            if typ=="BELL":
                b0,b1,b2=1+alpha*A,-2*cs,1-alpha*A
                a0,a1,a2=1+alpha/A,-2*cs,1-alpha/A
            elif typ in ("HP","LP"):
                if typ=="HP":b0=(1+cs)/2;b1=-(1+cs);b2=b0
                else:b0=(1-cs)/2;b1=1-cs;b2=b0
                a0,a1,a2=1+alpha,-2*cs,1-alpha
            else:
                t=sn*math.sqrt(2)/2;two=2*math.sqrt(A)*t
                if typ=="LOW_SHELF":
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
            numerator=b0+b1*z+b2*z*z
            denominator=a0+a1*z+a2*z*z
            result+=20*np.log10(np.maximum(np.abs(numerator/denominator),1e-12))
        return result
