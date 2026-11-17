"""Procesamiento vocal de color y mezcla, en float32 estéreo/mono.

Todos los controles son DSP determinista local sobre audio existente.
Rasgado: saturación armónica paralela; dulce: atenuación de aspereza
espectral. No transforma la identidad, no repara una voz lesionada y
no sustituye una toma profesional ni un modelo de voice conversion.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
from scipy.ndimage import gaussian_filter1d

def _filter(data,sr,freq,kind="low",order=2):
    limit=max(30,min(float(freq),sr*.475))
    sos=butter(order,limit,fs=sr,btype=kind,output="sos")
    return sosfilt(sos,data,axis=0).astype(np.float32,copy=False)

def _band(data,sr,low,high):
    return _filter(_filter(data,sr,low,"high"),sr,high,"low")

def _envelope(signal,sr,attack_ms=8,release_ms=65):
    """Envelope follower con ataque y caída, mono enlace estéreo."""
    strength=np.max(np.abs(signal),axis=1)
    sigma=max(1,round(sr*min(attack_ms,release_ms)/1000))
    return gaussian_filter1d(strength,sigma=sigma).astype(np.float32)

def _safe(data):
    peak=float(np.max(np.abs(data))) if data.size else 0.
    if peak>.985:data*=.985/peak
    if not np.all(np.isfinite(data)):raise ValueError("DSP vocal ha producido audio inválido")
    return data

def process_vocal_fx(audio,sr,character="Natural",character_amount=0,
                     warmth=0,air=0,presence=0,deesser=0,gate=0,
                     reverb=0,wet=100,doubler=0,delay=0,delay_ms=220,
                     stereo_width=100,output_gain_db=0):
    """Procesa audio PCM original sin cambiar duración, canales ni muestreo.

    Contraste: los controles se aplican sólo sobre la copia derivada,
    con mezcla húmeda/seca y limitación al rango máximo de amplitud.
    """
    signal=np.asarray(audio,dtype=np.float32)
    mono=signal.ndim==1
    x=signal[:,None].copy() if mono else signal.copy()
    if x.ndim!=2 or not 1<=x.shape[1]<=2 or not np.all(np.isfinite(x)):
        raise ValueError("Audio vocal de entrada inválido")
    settings=(character_amount,warmth,air,presence,deesser,gate,reverb,wet,
              doubler,delay)
    if not 0<=int(stereo_width)<=200 or not -18<=int(output_gain_db)<=18:
        raise ValueError("Ancho estéreo o ganancia de salida incorrectos")
    if not 80<=int(delay_ms)<=600:
        raise ValueError("Tiempo de delay debe estar entre 80 y 600 ms")
    if not all(0<=int(v)<=100 for v in settings):
        raise ValueError("Los controles de efectos deben quedar entre 0 y 100")
    if character not in ("Natural","Dulce","Rasgada","Cálida","Aireada"):
        raise ValueError("Carácter vocal desconocido")
    if sr<8000 or sr>192000:raise ValueError("Frecuencia no admitida")
    if not x.size:return signal.copy()
    if (all(int(v)==0 for v in settings[:7]) and not doubler and
        not delay and stereo_width==100 and output_gain_db==0):
        return signal.copy()
    original=x.copy()
    char=float(character_amount)/100.
    if char and character=="Rasgada":
        # Saturación paralela por armónicos, enfocada en la región vocal.
        # No se añade ruido de manera arbitraria ni se cambia la f0.
        centered=_band(x,sr,175,4400)
        gain=1.2+9.*char
        harmonic=(np.tanh(centered*gain)/np.tanh(gain))
        harmonic=_filter(harmonic,sr,min(7600,sr*.44))
        x += harmonic*(.10+.52*char)
        x /= (1+.15*char)
    elif char and character=="Dulce":
        # Atenuación progresiva del ruido/raspado en agudos: no reconstruye
        # componentes originales perdidos por distorsión de la fuente.
        smooth=_filter(x,sr,5600-3100*char)
        x=x*(1-char*.78)+smooth*(char*.78)
        high=x-_filter(x,sr,4200)
        x -= high*(.12+.22*char)
    elif char and character=="Cálida":
        low=_filter(x,sr,650)
        x=x+(.24*char)*low
        x=_safe(x)
    elif char and character=="Aireada":
        top=x-_filter(x,sr,4100)
        x=x+top*(.17+.44*char)
    if warmth:
        bass=_filter(x,sr,380)
        x=x + bass*(.34*warmth/100.)
    if presence:
        body=_band(x,sr,1350,4800)
        x=x+body*(.52*presence/100.)
    if air:
        top=x-_filter(x,sr,5700)
        x=x+top*(.65*air/100.)
    if deesser:
        sib=x-_filter(x,sr,4400)
        detector=_envelope(sib,sr,5,35)
        # Sólo cuando la banda de sibilancias supera un umbral.
        threshold=.025
        action=np.clip((detector-threshold)/(.11),0.,1.)
        reduction=(.76*deesser/100.)*action
        x=x-sib*reduction[:,None]
    if gate:
        env=_envelope(x,sr,12,80)
        # Reducción progresiva de ruido entre frases.
        floor=10**(-47./20.)
        openness=np.clip((env-floor)/(.012),0.,1.)
        openness=gaussian_filter1d(openness,max(1,round(sr*.012)))
        attenuation=(1.-float(gate)/100.*.94*(1.-openness))
        x*=attenuation[:,None]
    if reverb:
        # Ambiente discreto de estudio por retardos/difusión. Sin IR
        # de terceros; conserva perfectamente el número de muestras.
        dry=x.copy()
        reflections=(.032,.051,.083,.127)
        result=x.copy()
        amount=float(reverb)/100.
        for index,delay in enumerate(reflections):
            offset=max(1,int(sr*delay))
            if offset>=len(x):continue
            weight=(.22/(index+1))*(amount)
            result[offset:]+=dry[:-offset]*weight
        x=result
    if doubler:
        # Doblado por un par de retardos cortos. Es un efecto tipo
        # ADT (automatic double tracking), no otra interpretación nueva.
        amount=doubler/100.
        first=max(1,round(.021*sr))
        second=max(1,round(.034*sr))
        dry=x.copy()
        if len(x)>first:
            x[first:]+=dry[:-first]*(amount*.23)
        if len(x)>second:
            x[second:]+=dry[:-second]*(amount*.18)
    if delay:
        step=max(1,round(delay_ms/1000.*sr))
        dry=x.copy()
        mix_delay=delay/100.
        for echo in range(1,4):
            offset=step*echo
            if offset>=len(x):break
            x[offset:]+=dry[:-offset]*(mix_delay*(.36**echo))
    mix=float(wet)/100.
    x=original*(1-mix)+x*mix
    if stereo_width!=100 and x.shape[1]==2:
        mid=(x[:,0]+x[:,1])*.5
        side=(x[:,0]-x[:,1])*.5
        width=stereo_width/100.
        x[:,0]=mid+side*width
        x[:,1]=mid-side*width
    if output_gain_db:
        x*=10**(output_gain_db/20.)
    _safe(x)
    return x[:,0].astype(np.float32) if mono else x.astype(np.float32)
