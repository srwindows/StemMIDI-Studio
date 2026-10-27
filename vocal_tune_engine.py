"""Corrección monofónica de afinación vocal sobre audio real.

Detección f0 por pYIN; corrección por notas hacia una escala musical.
No sintetiza voz ni corrige dicción/timbre por arte de magia. Permite
procesamiento con fidelidad temporal y conserva original sin cambios.
Dependencias instaladas en entorno_ia: librosa, numpy, soundfile.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np

NOTES=("Do","Do#","Re","Re#","Mi","Fa","Fa#","Sol","Sol#","La","La#","Si")
SCALES={
    "Cromática":tuple(range(12)),
    "Mayor":(0,2,4,5,7,9,11),
    "Menor natural":(0,2,3,5,7,8,10),
    "Pentatónica mayor":(0,2,4,7,9),
    "Pentatónica menor":(0,3,5,7,10),
}

def target_midi(midi, tonic, scale):
    allowed={int((int(tonic)+x)%12) for x in SCALES[scale]}
    candidates=[pitch for pitch in range(24,109) if pitch%12 in allowed]
    return min(candidates,key=lambda x:(abs(x-midi),abs(x-round(midi))))

def collect_regions(midi_track, voiced,hop,sr,tonic,scale,strength,minimum=.11):
    """Devuelve regiones con una altura mediana definida, no silencios."""
    if not len(midi_track):return []
    rounded=np.where(voiced,np.rint(midi_track),-100).astype(int)
    # segmentos por nota real detectada
    segments=[]
    start=None
    current=None
    for i,note in enumerate(list(rounded)+[-100]):
        if note!=current:
            if start is not None and current!=-100:
                end=i
                valid=midi_track[start:end][voiced[start:end]]
                if len(valid) and (end-start)*hop/sr>=minimum:
                    pitch=float(np.median(valid))
                    desired=target_midi(pitch,tonic,scale)
                    shift=(desired-pitch)*(strength/100.)
                    if abs(shift)>=.045 and abs(shift)<6.0:
                        segments.append((max(0,(start*hop)-hop),
                                         min((end*hop)+hop,len(voiced)*hop),
                                         shift))
            start=i
            current=note
    return segments

def decode(source):
    """Extrae PCM float32 preservando canales y frecuencia del audio original."""
    probe=subprocess.run(["ffprobe","-v","error","-select_streams","a:0",
        "-show_entries","stream=sample_rate,channels",
        "-show_entries","format=duration","-of","json",str(source)],
        capture_output=True,text=True,check=True)
    info=json.loads(probe.stdout)
    duration=float(info.get("format",{}).get("duration",0))
    if duration<=0 or duration>12*60:
        raise ValueError("La voz debe durar entre unos segundos y 12 minutos.")
    stream=info["streams"][0]
    sample_rate=int(stream["sample_rate"])
    if not 8000<=sample_rate<=192000:
        raise ValueError("Frecuencia de audio no compatible.")
    channels=2 if int(stream.get("channels",1))>=2 else 1
    command=["ffmpeg","-v","error","-nostdin","-i",str(source),
        "-vn","-ac",str(channels),"-ar",str(sample_rate),
        "-f","f32le","-acodec","pcm_f32le","pipe:1"]
    decoded=subprocess.run(command,capture_output=True,check=True)
    data=np.frombuffer(decoded.stdout,dtype="<f4").copy()
    if not data.size or data.size%channels:
        raise ValueError("El audio contiene muestras incompletas.")
    if data.size//channels<sample_rate//3:
        raise ValueError("El audio de voz es demasiado corto.")
    samples=data.reshape(-1,channels).T
    return samples,sample_rate

def analyse_voice(source, max_seconds=35):
    """Análisis descriptivo y estimación de tonalidad con pYIN.

    Analiza una muestra limitada para poder ejecutarse en CPU. La clave
    musical sugerida NO está garantizada con una voz sin acompañamiento.
    """
    import librosa
    from scipy.ndimage import gaussian_filter1d
    audio,sr=decode(source)
    mono=np.mean(audio,axis=0).astype(np.float32)
    mono=mono[:int(sr*max_seconds)]
    analysis=librosa.resample(mono,orig_sr=sr,target_sr=22050) if sr!=22050 else mono
    if not np.any(np.abs(analysis)>0.003):
        raise ValueError("La voz está en silencio o tiene un nivel demasiado bajo.")
    f0,v,_=librosa.pyin(analysis,sr=22050,fmin=75.,fmax=900.,
                        frame_length=2048,hop_length=512,fill_na=np.nan)
    good=np.isfinite(f0)&np.asarray(v,dtype=bool)
    if np.count_nonzero(good)<16:
        raise ValueError("No se han encontrado suficientes notas cantadas para analizarlas.")
    pitches=librosa.hz_to_midi(f0[good])
    cents=np.abs(pitches-np.rint(pitches))*100
    histogram=np.bincount((np.rint(pitches).astype(int)%12),minlength=12).astype(float)
    choices=[]
    for tonic in range(12):
        for scale in ("Mayor","Menor natural"):
            mask=np.array([(i-tonic)%12 in SCALES[scale] for i in range(12)])
            score=float(histogram[mask].sum()/(histogram.sum()+1.e-9))
            choices.append((score,tonic,scale))
    score,tonic,scale=max(choices,key=lambda x:x[0])
    # Una única nota o intervalo pequeño no permite inferir la tonalidad
    # de una canción; bajar confianza e impedir aplicación automática.
    pitch_classes=np.unique(np.rint(pitches).astype(int)%12)
    if len(pitch_classes)<4 or np.percentile(pitches,90)-np.percentile(pitches,10)<4:
        score=min(score,.45)
    note_std=float(np.std(pitches-np.rint(pitches)))
    voiced_ratio=round(float(np.mean(good)),3)
    median_cents=round(float(np.median(cents)),1)
    rms=float(np.sqrt(np.mean(analysis**2)))
    peak=float(np.max(np.abs(analysis)))
    suggested=("Natural" if median_cents<13 else
               "Estudio" if median_cents<27 else "Pop preciso")
    return {"duration_analyzed":round(len(analysis)/22050,1),
            "median_pitch_midi":round(float(np.median(pitches)),1),
            "low_pitch_midi":round(float(np.percentile(pitches,10)),1),
            "high_pitch_midi":round(float(np.percentile(pitches,90)),1),
            "median_error_cents":median_cents,
            "pitch_jitter_cents":round(note_std*100,1),
            "rms_dbfs":round(20*np.log10(max(rms,1.e-8)),1),
            "peak_dbfs":round(20*np.log10(max(peak,1.e-8)),1),
            "voiced_ratio":voiced_ratio,
            "suggested_tonic":tonic,"suggested_scale":scale,
            "key_fit_score":round(score,2),
            "suggested_preset":suggested,
            "note":"Tonalidad orientativa calculada sobre una voz aislada."}

def apply_dynamics(audio,sr,compression=0,highpass=0):
    if not compression and not highpass:return audio
    from scipy.signal import butter,sosfilt
    from scipy.ndimage import gaussian_filter1d
    signal=np.asarray(audio,dtype=np.float32)
    wasmono=signal.ndim==1
    channels=signal.reshape(-1,1) if wasmono else signal.copy()
    if highpass:
        cutoff=int(highpass)
        if not 40<=cutoff<=190:raise ValueError("Filtro de graves incorrecto")
        filter_sos=butter(2,cutoff,fs=sr,btype="highpass",output="sos")
        channels=sosfilt(filter_sos,channels,axis=0).astype(np.float32)
    if compression:
        value=int(compression)
        if not 0<=value<=100:raise ValueError("Compresión incorrecta")
        envelope=gaussian_filter1d(np.max(np.abs(channels),axis=1),
                                   sigma=max(1,sr*.015))
        threshold=10**((-18.0)/20)
        ratio=1.+value*.045
        over=np.maximum(envelope/threshold,1.)
        gain=np.power(over,1./ratio-1.)
        channels*=gain[:,None]
    peak=np.max(np.abs(channels)) if channels.size else 0
    if peak>.98:channels=channels*(.98/peak)
    return channels[:,0] if wasmono else channels

def correct_audio(audio,sr,tonic,scale,strength,retune_ms=60,humanize=10,threshold_cents=8):
    import librosa
    channels=np.asarray(audio,dtype=np.float32)
    was_mono=channels.ndim==1
    if was_mono:channels=channels.reshape(1,-1)
    if channels.ndim!=2 or channels.shape[0]>2 or not np.all(np.isfinite(channels)):
        raise ValueError("La voz contiene muestras inválidas.")
    mono=np.mean(channels,axis=0).astype(np.float32)
    analysis_rate=22050
    analysis=(librosa.resample(mono,orig_sr=sr,target_sr=analysis_rate)
              if sr!=analysis_rate else mono)
    hop=256
    # Analizar a 22,05 kHz evita coste excesivo sin reducir
    # resolución ni tasa de muestreo del AUDIO EXPORTADO.
    f0,voiced,_=librosa.pyin(analysis,sr=analysis_rate,fmin=75.,fmax=900.,
        frame_length=2048,hop_length=hop,fill_na=np.nan)
    v=np.asarray(voiced,dtype=bool)&np.isfinite(f0)
    midi=np.zeros(len(f0),dtype=np.float32)
    if v.any():midi[v]=librosa.hz_to_midi(f0[v])
    if not 20<=int(retune_ms)<=250 or not 0<=int(humanize)<=100:
        raise ValueError("Ajustes de retune/humanización fuera de rango.")
    if not 0<=int(threshold_cents)<=70:
        raise ValueError("Umbral de corrección fuera de rango.")
    effective_strength=strength*(1-.35*humanize/100)
    segments=[(a,b,shift) for a,b,shift in collect_regions(
        midi,v,hop,analysis_rate,tonic,scale,effective_strength)
        if abs(shift)*100>=threshold_cents]
    result=channels.copy()
    corrected=0
    ratio=float(sr)/float(analysis_rate)
    for base_s,base_e,shift in segments:
        s=max(0,min(channels.shape[1],round(base_s*ratio)))
        e=max(s,min(channels.shape[1],round(base_e*ratio)))
        length=e-s
        if length<2048:continue
        original=channels[:,s:e]
        pitched=librosa.effects.pitch_shift(original,sr=sr,n_steps=shift,
                                           bins_per_octave=12)
        if pitched.shape[-1]!=length:
            pitched=librosa.util.fix_length(pitched,size=length)
        fade=min(round(sr*(retune_ms/1000.)),length//3)
        envelope=np.ones(length,dtype=np.float32)
        if fade:
            envelope[:fade]=np.linspace(0,1,fade,dtype=np.float32)
            envelope[-fade:]=np.linspace(1,0,fade,dtype=np.float32)
        envelope=envelope[None,:]
        result[:,s:e]=result[:,s:e]*(1-envelope)+pitched*envelope
        corrected+=1
    peak=float(np.max(np.abs(result))) if result.size else 0.
    if peak>.98:result*=.98/peak
    output=(result[0] if was_mono else result.T)
    return output.astype(np.float32),{"detected_notes":int(v.sum()),
                                      "corrected_regions":corrected,
                                      "duration_seconds":round(result.shape[1]/sr,2),
                                      "output_sample_rate":int(sr),
                                      "output_channels":int(result.shape[0])}

def render(source,destination,tonic,scale,strength,retune_ms=60,humanize=10,
           threshold_cents=8,compression=0,highpass=0,character="Natural",
           character_amount=0,warmth=0,air=0,presence=0,deesser=0,
           gate=0,reverb=0,wet=100,bypass_tune=False,
           doubler=0,delay=0,delay_ms=220,stereo_width=100,output_gain_db=0):
    import soundfile as sf
    source=Path(source).expanduser().resolve()
    dest=Path(destination).expanduser().resolve()
    if not source.is_file():raise ValueError("No existe el archivo de voz.")
    if dest.exists():raise FileExistsError("No se sobrescribirá un resultado existente.")
    if str(source)==str(dest):raise ValueError("El original nunca puede ser reemplazado.")
    if not 0<=tonic<12 or scale not in SCALES or not 0<=strength<=100:
        raise ValueError("Tonalidad o intensidad incorrecta.")
    audio,sample_rate=decode(source)
    if bypass_tune:
        result=audio[0] if audio.shape[0]==1 else audio.T.copy()
        meta={"corrected_regions":0,"output_sample_rate":sample_rate,
              "output_channels":audio.shape[0],
              "duration_seconds":round(audio.shape[1]/sample_rate,2),
              "pitch_tuning":"desactivada"}
    else:
        result,meta=correct_audio(audio,sample_rate,tonic,scale,strength,
                                  retune_ms,humanize,threshold_cents)
        if meta["corrected_regions"]==0:
            # Una voz puede estar afinada ya, hablada o carecer de regiones
            # analizables. Esto NO debe impedir aplicar EQ/dinámica/FX.
            meta["tuning_notice"]=(
                "Sin regiones que corregir: se conserva la altura original. "
                "Se aplican igualmente dinámica, ecualización y efectos.")
    from vocal_fx import process_vocal_fx
    result=apply_dynamics(result,sample_rate,compression,highpass)
    result=process_vocal_fx(
        result,sample_rate,character=character,
        character_amount=character_amount,warmth=warmth,
        air=air,presence=presence,deesser=deesser,gate=gate,
        reverb=reverb,wet=wet,doubler=doubler,delay=delay,
        delay_ms=delay_ms,stereo_width=stereo_width,
        output_gain_db=output_gain_db)
    meta["character"]=character
    meta["character_intensity"]=character_amount
    meta["effects_active"]=bool(
        any(v for v in (character_amount if character!="Natural" else 0,
                        warmth,air,presence,deesser,gate,reverb,doubler,
                        delay,compression,highpass,output_gain_db))
        or stereo_width != 100)

    dest.parent.mkdir(parents=True,exist_ok=True)
    sf.write(str(dest),result,sample_rate,format="FLAC",subtype="PCM_24")
    return meta

def main():
    parser=argparse.ArgumentParser(description="Corrección tonal de voz monofónica")
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",default="")
    parser.add_argument("--tonic",type=int,default=0)
    parser.add_argument("--scale",choices=SCALES.keys(),default="Cromática")
    parser.add_argument("--strength",type=int,default=75)
    parser.add_argument("--analyze",action="store_true")
    parser.add_argument("--retune-ms",type=int,default=60)
    parser.add_argument("--humanize",type=int,default=10)
    parser.add_argument("--threshold-cents",type=int,default=8)
    parser.add_argument("--compression",type=int,default=0)
    parser.add_argument("--highpass",type=int,default=0)
    parser.add_argument("--character",choices=["Natural","Dulce","Rasgada","Cálida","Aireada"],default="Natural")
    for name in ("character-amount","warmth","air","presence","deesser","gate","reverb"):
        parser.add_argument("--"+name,type=int,default=0)
    parser.add_argument("--wet",type=int,default=100)
    parser.add_argument("--bypass-tune",action="store_true")
    parser.add_argument("--doubler",type=int,default=0)
    parser.add_argument("--delay",type=int,default=0)
    parser.add_argument("--delay-ms",type=int,default=220)
    parser.add_argument("--stereo-width",type=int,default=100)
    parser.add_argument("--output-gain-db",type=int,default=0)
    opts=parser.parse_args()
    try:
        print("Analizando entonación vocal…",flush=True)
        if opts.analyze:
            report=analyse_voice(opts.input)
            print("ANALISIS "+json.dumps(report,ensure_ascii=False),flush=True)
            return
        if not opts.output:
            raise ValueError("Es obligatorio especificar una salida para afinar.")
        result=render(opts.input,opts.output,opts.tonic,opts.scale,opts.strength,
            opts.retune_ms,opts.humanize,opts.threshold_cents,opts.compression,
            opts.highpass,character=opts.character,
            character_amount=opts.character_amount,warmth=opts.warmth,
            air=opts.air,presence=opts.presence,deesser=opts.deesser,
            gate=opts.gate,reverb=opts.reverb,wet=opts.wet,
            bypass_tune=opts.bypass_tune,
            doubler=opts.doubler,delay=opts.delay,delay_ms=opts.delay_ms,
            stereo_width=opts.stereo_width,output_gain_db=opts.output_gain_db)
        print("RESULTADO "+json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as exc:
        print("ERROR: "+str(exc),file=sys.stderr,flush=True)
        sys.exit(1)

if __name__=="__main__":main()
