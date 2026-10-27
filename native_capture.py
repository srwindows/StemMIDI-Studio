"""Fuentes de captura nativas para Windows (WASAPI) y macOS (CoreAudio).

Windows: loopback WASAPI de salida, sin alterar el volumen del sistema.
macOS: audio de entrada; para capturar *audio del sistema* requiere un
dispositivo virtual configurado por el usuario, p. ej. BlackHole.
"""
from __future__ import annotations
import sys
import numpy as np

def _audio():
    import soundcard
    return soundcard

def get_sources(include_mics=False):
    sc=_audio()
    result=[]
    for mic in sc.all_microphones(include_loopback=True):
        loop=bool(getattr(mic,"isloopback",False))
        # macOS no expone monitor de salida sin dispositivo virtual.
        if not include_mics and not loop and sys.platform!="darwin":
            continue
        label=("Salida (WASAPI): " if loop else "Entrada (CoreAudio): " 
               if sys.platform=="darwin" else "Micrófono: ")+str(mic.name)
        result.append({"name":"soundcard:"+str(mic.id),
                       "label":label,"kind":"monitor" if loop else "input"})
    return result

def default_source():
    sc=_audio()
    for mic in sc.all_microphones(include_loopback=True):
        if getattr(mic,"isloopback",False):
            return "soundcard:"+str(mic.id)
    microphones=sc.all_microphones(include_loopback=True)
    return "soundcard:"+str(microphones[0].id) if microphones else None

def record_chunks(device,stop_event,rate=48000,frames=4096):
    sc=_audio()
    ident=str(device).removeprefix("soundcard:")
    microphone=sc.get_microphone(ident,include_loopback=True)
    if microphone is None:
        raise RuntimeError("Dispositivo de audio no disponible: "+ident)
    try:
        context=microphone.recorder(samplerate=rate,channels=2)
        with context as rec:
            while not stop_event.is_set():
                data=np.asarray(rec.record(numframes=frames),dtype=np.float32)
                if data.ndim==1:data=data[:,None]
                if data.shape[1]==1:data=np.repeat(data,2,axis=1)
                data=data[:,:2]
                if data.size:
                    yield data.astype("<f4",copy=False).tobytes()
    except Exception as exc:
        raise RuntimeError(
            "La captura nativa no pudo abrirse. En macOS, configura "
            "antes una entrada virtual (por ejemplo, BlackHole). "
            f"Detalle: {exc}") from exc
