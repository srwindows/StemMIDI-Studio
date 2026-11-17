"""Fuentes de captura nativas para Windows (WASAPI) y macOS (CoreAudio).

Windows: loopback WASAPI de salida, sin alterar el volumen del sistema.
macOS: captura nativa de la mezcla de salida con ScreenCaptureKit;
las entradas de micrófono/USB requieren un permiso independiente.
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
    result=[]
    if sys.platform=="darwin":
        from macos_system_audio import (SYSTEM_AUDIO_SOURCE,
                                        system_audio_library,system_output_name)
        if system_audio_library() is not None:
            # La salida GM no devuelve por USB la mezcla que recibe.
            # ScreenCaptureKit sí captura YouTube sin cambiar de salida.
            destination=system_output_name()
            result.append({"name":SYSTEM_AUDIO_SOURCE,
                           "label":"Audio del sistema → "+destination,
                           "kind":"monitor"})
        # PortAudio puede abrir la ruta de captura durante su inicialización
        # y pedir acceso al micrófono. Consultar directamente las propiedades
        # de hardware CoreAudio NO crea ningún stream de entrada.
        from macos_system_audio import system_input_devices
        found=set()
        for device in system_input_devices():
            channels=int(device.get("channels",0) or 0)
            name=str(device.get("name","")).strip()
            if not name or not channels or name in found:
                continue
            found.add(name)
            result.append({"name":"soundcard:name:"+quote(name,safe=""),
                           "label":"Entrada (CoreAudio): "+name+
                                   " · "+str(channels)+
                                   (" canal" if channels==1 else " canales"),
                           "kind":"input"})
        return result
    sc=_audio()  # consultar entradas solo cuando se solicitan expresamente
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
    if sys.platform=="darwin":
        from macos_system_audio import SYSTEM_AUDIO_SOURCE,system_audio_library
        if system_audio_library() is not None:
            return SYSTEM_AUDIO_SOURCE
    sc=_audio()
    for mic in sc.all_microphones(include_loopback=True):
        if getattr(mic,"isloopback",False):
            return _stable_id(mic)
    microphones=sc.all_microphones(include_loopback=True)
    return _stable_id(microphones[0]) if microphones else None

def record_chunks(device,stop_event,rate=48000,frames=4096):
    if sys.platform=="darwin":
        from macos_system_audio import SYSTEM_AUDIO_SOURCE,record_system_audio
        if str(device)==SYSTEM_AUDIO_SOURCE:
            yield from record_system_audio(stop_event,rate,frames)
            return
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
            "No se pudo abrir la entrada "+str(device)+". Comprueba que el "
            "dispositivo esté conectado y que macOS haya autorizado el "
            "micrófono para StemMIDI si procede. Detalle: "
            f"{exc}") from exc
