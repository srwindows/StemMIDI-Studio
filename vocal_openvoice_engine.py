"""Motor neuronal OpenVoice V2 (MyShell, MIT) para conversión de timbre.

Ejecuta un modelo oficial y local. Conserva el original, procesa en fragmentos,
no ejecuta checkpoints importados arbitrariamente y devuelve un FLAC nuevo.
El motor preserva principalmente la articulación y el ritmo de la voz fuente;
no afirma reproducir perfectamente las emociones ni el canto del referente.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import numpy as np

RANGES={
    "similarity":(0,100), "timbre":(0,100), "pitch":(-12,12),
    "formants":(-8,8), "resonance":(0,100), "brightness":(-100,100),
    "dynamics":(0,100), "articulation":(0,100), "air":(0,100),
    "rasp":(0,100), "vibrato":(0,100), "stereo":(0,200),
    "tau":(0,100), "chunk_seconds":(2,10), "overlap_ms":(30,450)
}
MODEL_DIR="openvoice_v2"

def locations(module_file=None):
    """Rutas de la instalación de desarrollo y recursos empaquetados."""
    here=Path(module_file or __file__).resolve()
    ancestry=list(here.parents)[:9]
    workspace=Path(os.environ.get("STEMMIDI_WORKSPACE","")).expanduser()
    roots=[workspace] if workspace.is_dir() else []
    roots+=ancestry
    model_candidates=[]
    vendor_candidates=[]
    for base in roots:
        model_candidates += [
            base/"modelos"/"clonacion_neuronal"/MODEL_DIR,
            base/"runtime"/"modelos"/"clonacion_neuronal"/MODEL_DIR,
            base/"ai_models"/MODEL_DIR,
            base/"Resources"/"ai_models"/MODEL_DIR,
        ]
        vendor_candidates += [
            base/"third_party"/"OpenVoice",
            base/"vendor"/"openvoice",
            base/"Resources"/"vendor"/"openvoice",
        ]
    model=next((p for p in model_candidates
        if (p/"checkpoint.pth").is_file() and (p/"config.json").is_file()),None)
    vendor=next((p for p in vendor_candidates
        if (p/"openvoice"/"api.py").is_file() and (p/"LICENSE").is_file()),None)
    return model,vendor

def model_ready():
    model,vendor=locations()
    return bool(model and vendor and (model/"checkpoint.pth").stat().st_size>50*1024*1024)

def _probe(path):
    args=["ffprobe","-v","error","-select_streams","a:0",
          "-show_entries","stream=sample_rate,channels",
          "-show_entries","format=duration","-of","json",str(path)]
    raw=subprocess.run(args,text=True,capture_output=True,check=True)
    info=json.loads(raw.stdout)
    stream=info["streams"][0]
    length=float(info.get("format",{}).get("duration",0))
    if not .8<=length<=300:
        raise ValueError("La voz debe durar entre 0,8 segundos y 5 minutos.")
    return int(stream["sample_rate"]),int(stream.get("channels",1)),length

def _mono(input_path,target_path,sr=22050):
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
        "-i",str(input_path),"-vn","-ac","1","-ar",str(sr),
        "-c:a","pcm_s16le",str(target_path)],check=True)

def _active_reference(samples,sr,max_seconds=12):
    """Selecciona audio activo evitando silencios extensos y clips minúsculos."""
    block=max(1,round(.25*sr))
    pieces=[]
    energies=[]
    for begin in range(0,len(samples)-block+1,block):
        piece=samples[begin:begin+block]
        energies.append(float(np.sqrt(np.mean(np.square(piece,dtype=np.float64)))))
        pieces.append(piece)
    if not energies:
        raise ValueError("Referencia demasiado corta.")
    threshold=max(.002,max(energies)*.09)
    indices=[i for i,e in enumerate(energies) if e>threshold]
    if len(indices)*block/sr<.9:
        raise ValueError("La referencia carece de voz activa suficiente.")
    chosen=indices[:max(1,int(max_seconds*sr/block))]
    return np.concatenate([pieces[i] for i in chosen]).astype(np.float32)

def _revoice(vc,mono,source_se,target_se,sr,chunk_seconds=5.0,overlap=.12,tau=.3):
    """Conversión por fragmentos con ventana solapada para conservar duración."""
    import soundfile as sf
    size=len(mono)
    block=max(2048,int(chunk_seconds*sr))
    fade=max(64,int(overlap*sr))
    hop=block-fade
    out=np.zeros(size,dtype=np.float32)
    weights=np.zeros(size,dtype=np.float32)
    with tempfile.TemporaryDirectory(prefix="openvoice_chunks_") as work:
        tmp=Path(work)/"chunk.wav"
        for i,start in enumerate(range(0,size,hop)):
            end=min(start+block,size)
            if end-start < 1024:break
            sf.write(tmp,mono[start:end],sr,subtype="PCM_16")
            converted=vc.convert(str(tmp),source_se,target_se,tau=tau)
            data=np.asarray(converted,dtype=np.float32)
            if len(data)<end-start:data=np.pad(data,(0,end-start-len(data)))
            data=data[:end-start]
            shape=np.ones(len(data),dtype=np.float32)
            if start>0:
                count=min(fade,len(data))
                shape[:count]=np.linspace(0,1,count)
            if end<size:
                count=min(fade,len(data))
                shape[-count:]=np.minimum(shape[-count:],np.linspace(1,0,count))
            out[start:end]+=data*shape
            weights[start:end]+=shape
            print(f"ETAPA Conversión neuronal {min(100,round(end/size*100))} %",flush=True)
    if not np.all(weights>.000001):
        raise RuntimeError("Hay muestras sin convertir; no se guardará una voz incompleta.")
    return out/weights

def process(source,reference,output,**values):
    from scipy.signal import resample_poly
    import soundfile as sf
    import librosa
    import torch
    from vocal_clone_engine import spectral_profile,_tone_channel
    params={}
    for name,(minimum,maximum) in RANGES.items():
        number=float(values.get(name,{"tau":30,"chunk_seconds":5,
            "overlap_ms":120}.get(name,0)))
        if not np.isfinite(number) or not minimum<=number<=maximum:
            raise ValueError("Valor vocal fuera de rango: "+name)
        params[name]=number
    a=Path(source).expanduser().resolve()
    b=Path(reference).expanduser().resolve()
    target=Path(output).expanduser().resolve()
    if not a.is_file() or not b.is_file() or a==b:
        raise ValueError("Selecciona dos grabaciones vocales distintas.")
    if target.exists() or target in (a,b):
        raise ValueError("El resultado debe ser un archivo nuevo.")
    model,vendor=locations()
    if model is None or vendor is None:
        raise RuntimeError("OpenVoice V2 no está instalado completamente.")
    sys.path.insert(0,str(vendor))
    from openvoice.api import ToneColorConverter
    sample_rate,channels,_=_probe(a)
    _probe(b)
    internal_sr=22050
    torch.set_num_threads(min(8,max(1,os.cpu_count() or 1)))
    with tempfile.TemporaryDirectory(prefix="stemmidi_openvoice_") as tmp:
        temporary=Path(tmp)
        src=temporary/"origen.wav"
        ref=temporary/"referencia.wav"
        _mono(a,src,internal_sr)
        _mono(b,ref,internal_sr)
        signal,sr=sf.read(src,dtype="float32")
        reference_samples,ref_sr=sf.read(ref,dtype="float32")
        if sr!=internal_sr or ref_sr!=sr or len(signal)<2048:
            raise ValueError("No se pudo decodificar correctamente la grabación.")
        if np.max(np.abs(signal))<.002:
            raise ValueError("La señal de entrada está casi en silencio.")
        # La ida/vuelta 16 kHz ↔ 22,05 kHz puede redondear al alza una
        # muestra. Guardar la duración exacta de la toma, no la del
        # último remuestreo de la red neuronal.
        expected_frames=round(len(signal)*sample_rate/internal_sr)
        source_active=_active_reference(signal,sr,10)
        target_active=_active_reference(reference_samples,sr,12)
        sf.write(temporary/"src_embedding.wav",source_active,sr)
        sf.write(temporary/"tgt_embedding.wav",target_active,sr)
        print("ETAPA Cargando pesos oficiales de OpenVoice V2 en CPU…",flush=True)
        converter=ToneColorConverter(str(model/"config.json"),device="cpu",
                                     enable_watermark=False)
        converter.load_ckpt(str(model/"checkpoint.pth"))
        print("ETAPA Extrayendo identidad de ambas voces…",flush=True)
        source_identity=converter.extract_se(str(temporary/"src_embedding.wav"))
        reference_identity=converter.extract_se(str(temporary/"tgt_embedding.wav"))
        identity_mix=params["timbre"]/100.
        desired=source_identity*(1-identity_mix)+reference_identity*identity_mix
        print("ETAPA Transformando la voz con la red neuronal…",flush=True)
        converted=_revoice(converter,signal,source_identity,desired,sr,
           chunk_seconds=params["chunk_seconds"],
           overlap=params["overlap_ms"]/1000.0,
           tau=params["tau"]/100.)
        similarity=params["similarity"]/100.
        rendered=(signal*(1-similarity)+converted*similarity).astype(np.float32)
        # Complementos DSP: parámetros independientes, no se promete un
        # "modelo de emoción" inexistente.
        fx_params={**params,"similarity":0,"timbre":0}
        if any(params[k] for k in ("formants","resonance","brightness","air",
                                    "dynamics","articulation","rasp","vibrato")):
            profile=spectral_profile(rendered,target_active,sr,fx_params)
            rendered=_tone_channel(rendered,sr,profile,fx_params,
                                   np.maximum(np.abs(target_active),1e-5)[::max(1,int(sr*.020))])
        if params["pitch"]:
            rendered=librosa.effects.pitch_shift(rendered,sr=sr,
                                                  n_steps=params["pitch"])
        if sample_rate!=internal_sr:
            fraction=Fraction(sample_rate,internal_sr)
            rendered=resample_poly(rendered,fraction.numerator,
                                   fraction.denominator).astype(np.float32)
        # Mantener la longitud original tras los dos remuestreos.
        # La discrepancia normal es de 0 o 1 muestras; rechazar errores
        # grandes para no ocultar truncamientos de la inferencia.
        delta=int(expected_frames-len(rendered))
        if abs(delta)>max(4,round(sample_rate*.005)):
            raise RuntimeError(
                f"La red produjo una longitud incorrecta ({len(rendered)} "
                f"frente a {expected_frames} muestras).")
        if delta<0:
            rendered=rendered[:expected_frames]
        elif delta>0:
            rendered=np.pad(rendered,(0,delta),mode="edge")
        # Salida neuronal mono; si el origen era estéreo, preservar Side.
        if channels>=2:
            original_stereo=temporary/"origen_stereo.wav"
            subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                "-i",str(a),"-vn","-ac","2","-ar",str(sample_rate),
                "-c:a","pcm_s16le",str(original_stereo)],check=True)
            stereo,stereo_rate=sf.read(original_stereo,dtype="float32",always_2d=True)
            if stereo_rate!=sample_rate or len(stereo)<2:
                raise ValueError("Canales de entrada no válidos.")
            side=.5*(stereo[:,0]-stereo[:,1])
            if len(side)!=len(rendered):
                side=np.interp(np.linspace(0,len(side)-1,len(rendered)),
                               np.arange(len(side)),side).astype(np.float32)
            side*=params["stereo"]/100.
            rendered=np.column_stack((rendered+side,rendered-side))
        peak=float(np.max(np.abs(rendered)))
        if not np.isfinite(peak) or peak<1e-8:
            raise RuntimeError("La conversión neuronal produjo silencio o valores inválidos.")
        if peak>.98:rendered*=.98/peak
        target.parent.mkdir(parents=True,exist_ok=True)
        sf.write(target,rendered,sample_rate,format="FLAC",subtype="PCM_24")
        if target.stat().st_size<1500:raise RuntimeError("FLAC de salida incompleto.")
        print("RESULTADO "+json.dumps({
            "method":"OpenVoiceV2_neural_conversion",
            "sample_rate":sample_rate,"channels":min(channels,2),
            "seconds":round(len(rendered)/sample_rate,3),
            "controls":params},ensure_ascii=False),flush=True)
        return target

def main():
    parser=argparse.ArgumentParser()
    for name in ("source","reference","output"):
        parser.add_argument("--"+name,required=True)
    for name,(minimum,maximum) in RANGES.items():
        parser.add_argument("--"+name.replace("_","-"),type=float,
                            default={"tau":30,"chunk_seconds":5,"overlap_ms":120}.get(
                                name,100 if name in ("similarity","timbre","stereo") else 0))
    args=vars(parser.parse_args())
    for key in ("source","reference","output"):
        pass
    process(**args)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("ERROR OPENVOICE: "+str(exc),file=sys.stderr,flush=True)
        sys.exit(1)
