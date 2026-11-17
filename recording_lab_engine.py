"""Motor de laboratorio de grabación no destructivo: FFmpeg DSP verificable.

Mantiene intacta la captura PCM/FLAC/WAV original. El resultado es una
segunda versión y los filtros se ejecutan en un proceso independiente.
"""
from __future__ import annotations
import json
import math
import subprocess
from pathlib import Path

DEFAULT={
    "auto_after":False,
    "denoise":0,
    "declick":False,
    "highpass":70,
    "lowpass_enabled":False,
    "lowpass":16000,
    "gate_enabled":False,
    "gate_threshold":-46,
    "bass":0,"lowmid":0,"highmid":0,"treble":0,
    "deesser":0,
    "comp_enabled":False,
    "comp_threshold":-22,
    "comp_ratio":3,
    "comp_attack":15,
    "comp_release":150,
    "stereo_width":100,
    "output_gain":0,
    "limiter":True,
    "loudnorm_enabled":False,
    "target_lufs":-16
}
BOUNDS={
    "denoise":(0,25),"highpass":(0,300),"lowpass":(4500,20000),
    "gate_threshold":(-65,-20),
    "bass":(-12,12),"lowmid":(-12,12),"highmid":(-12,12),
    "treble":(-12,12),"deesser":(0,100),
    "comp_threshold":(-45,-8),"comp_ratio":(1,10),
    "comp_attack":(1,100),"comp_release":(30,600),
    "stereo_width":(0,160),"output_gain":(-18,18),
    "target_lufs":(-24,-10)
}
BOOL_KEYS={k for k,v in DEFAULT.items() if isinstance(v,bool)}


def validated(parameters):
    if not isinstance(parameters,dict):raise ValueError("Parámetros del laboratorio inválidos.")
    result=dict(DEFAULT)
    for name,default in DEFAULT.items():
        if name not in parameters:continue
        v=parameters[name]
        if name in BOOL_KEYS:
            if not isinstance(v,bool):raise ValueError("Casilla inválida: "+name)
            result[name]=v
        else:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
                raise ValueError("Valor numérico inválido: "+name)
            lower,upper=BOUNDS[name]
            if not lower<=v<=upper:raise ValueError("Fuera de rango: "+name)
            result[name]=int(v)
    return result


def probe_audio(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink():raise ValueError("Archivo fuente inexistente o enlace no permitido.")
    try:
        p=subprocess.run(["ffprobe","-v","error","-select_streams","a:0",
             "-show_entries","stream=sample_rate,channels","-of","json",str(path)],
             capture_output=True,text=True,timeout=9,check=True)
        data=json.loads(p.stdout)
        item=data["streams"][0]
        sr=int(item["sample_rate"])
        ch=int(item["channels"])
        if sr<8000 or sr>384000 or ch<1 or ch>8:raise ValueError(
            "FLAC admite como máximo 8 canales en este motor.")
        return sr,ch
    except (KeyError,IndexError,json.JSONDecodeError,subprocess.CalledProcessError,
            subprocess.TimeoutExpired,OSError) as exc:
        raise ValueError("No se pudo verificar la pista de audio: "+str(exc)) from exc


def filter_chain(settings,sr):
    p=validated(settings)
    nyquist=sr*.5
    filters=[]
    if p["declick"]:filters.append("adeclick=w=40:o=75:t=2.5")
    if p["denoise"]:
        filters.append(f"afftdn=nr={p['denoise']}:nf=-52:tn=0")
    hp=min(p["highpass"],int(nyquist*.8))
    if hp>=20:filters.append(f"highpass=f={hp}")
    if p["lowpass_enabled"]:
        lp=min(p["lowpass"],int(nyquist*.90))
        if lp<=hp+300:raise ValueError("Paso bajo incompatible con paso alto.")
        filters.append(f"lowpass=f={lp}")
    if p["gate_enabled"]:
        threshold=10**(p["gate_threshold"]/20.)
        filters.append(f"agate=threshold={threshold:.7f}:ratio=2.6:"
                       "attack=8:release=230:range=0.075")
    for key,freq,width in (
         ("bass",120,1.0),("lowmid",390,1.1),
         ("highmid",2800,1.0),("treble",8000,.8)):
        gain=p[key]
        if gain and freq<nyquist*.9:
            filters.append(f"equalizer=f={freq}:t=q:w={width}:g={gain}")
    if p["deesser"]:
        strength=round(p["deesser"]/100.,3)
        filters.append(f"deesser=i={strength}:m=0.5:f=0.5")
    if p["comp_enabled"] and p["comp_ratio"]>1:
        threshold=10**(p["comp_threshold"]/20.)
        filters.append(f"acompressor=threshold={threshold:.7f}:"
            f"ratio={p['comp_ratio']}:attack={p['comp_attack']}:"
            f"release={p['comp_release']}:makeup=1")
    if p["stereo_width"]!=100:
        # stereo width by mid/side, preserving summed mono energy; FFmpeg
        # stereotools= 'slev' controls the side signal and does not pan audio.
        filters.append(f"stereotools=slev={p['stereo_width']/100.:.2f}")
    if p["output_gain"]:
        filters.append(f"volume={p['output_gain']}dB")
    if p["loudnorm_enabled"]:
        filters.append(f"loudnorm=I={p['target_lufs']}:TP=-1.5:LRA=11")
    if p["limiter"]:
        filters.append("alimiter=limit=0.891:level=false")
    return ",".join(filters or ["anull"])


def command(source,output,settings):
    source=Path(source).expanduser().resolve()
    output=Path(output).expanduser().resolve()
    if source==output or output.exists():raise ValueError("El resultado debe tener un nombre nuevo.")
    if output.suffix.lower()!=".flac":raise ValueError("El resultado de estudio debe ser FLAC.")
    sr,channels=probe_audio(source)
    chain=filter_chain(settings,sr)
    return ["ffmpeg","-hide_banner","-loglevel","error","-nostdin","-nostats",
            "-i",str(source),"-map","0:a:0","-vn","-sn","-dn",
            "-af",chain,"-ar",str(sr),"-ac",str(channels),
            "-c:a","flac","-sample_fmt","s32",
            "-bits_per_raw_sample","24","-compression_level","5",
            "-n",str(output)]
