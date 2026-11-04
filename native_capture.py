"""Fuentes de captura nativas para Windows (WASAPI) y macOS (CoreAudio).

Windows: loopback WASAPI de salida, sin alterar el volumen del sistema.
macOS: audio de entrada; para capturar *audio del sistema* requiere un
dispositivo virtual configurado por el usuario, p. ej. BlackHole.
"""
from __future__ import annotations
import sys
import numpy as np
from urllib.parse import quote, unquote

def _stable_id(mic):
    # AudioObjectID de macOS cambia al reiniciar coreaudiod.
    # Usar un identificador persistente para no perder las fuentes guardadas.
    if sys.platform=="darwin":
        return "soundcard:name:"+quote(str(mic.name),safe="")
    return "soundcard:"+str(mic.id)

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
        result.append({"name":_stable_id(mic),
                       "label":label,"kind":"monitor" if loop else "input"})
    return result

def default_source():
    sc=_audio()
    for mic in sc.all_microphones(include_loopback=True):
        if getattr(mic,"isloopback",False):
            return _stable_id(mic)
    microphones=sc.all_microphones(include_loopback=True)
    return _stable_id(microphones[0]) if microphones else None

def record_chunks(device,stop_event,rate=48000,frames=4096):
    sc=_audio()
    ident=str(device).removeprefix("soundcard:")
    microphones=sc.all_microphones(include_loopback=True)
    if ident.startswith("name:"):
        name=unquote(ident.removeprefix("name:"))
        microphone=next((mic for mic in microphones if str(mic.name)==name),None)
    else:
        microphone=next((mic for mic in microphones if str(mic.id)==ident),None)
    if microphone is None:
        raise RuntimeError("Dispositivo de audio no disponible: "+ident)
    try:
        input_channels=int(getattr(microphone,"channels",2) or 2)
        context=microphone.recorder(samplerate=rate,
                                    channels=1 if input_channels==1 else 2)
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
