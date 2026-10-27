"""Transferencia ASISTIDA de interpretación vocal (primera etapa verificable).

Misma canción y fraseo próximo. Retiene muestras de la voz de entrada,
sin encoder de identidad, modelo clonado ni sustitución tímbrica.
Transferibles: tempo global, notas, fluctuación fina de altura y dinámica.
No atribuir articulación, respiraciones ni emoción a esta versión.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np


def _log(message):
    print("ETAPA "+message,flush=True)


def extract_features(mono, sample_rate, analysis_rate=16000, hop=320):
    import librosa
    from scipy.ndimage import gaussian_filter1d
    if mono.ndim!=1:
        raise ValueError("El análisis vocal requiere un canal monofónico.")
    signal=librosa.resample(mono.astype(np.float32),orig_sr=sample_rate,
                            target_sr=analysis_rate) if sample_rate!=analysis_rate else mono.astype(np.float32)
    if len(signal)<analysis_rate:
        raise ValueError("Se necesita al menos un segundo de voz.")
    f0,voiced,_=librosa.pyin(signal,sr=analysis_rate,fmin=75.0,fmax=850.,
        hop_length=hop,frame_length=2048,fill_na=np.nan)
    mask=np.asarray(voiced,dtype=bool)&np.isfinite(f0)
    midi=np.full(len(f0),np.nan,dtype=np.float32)
    if np.any(mask):midi[mask]=librosa.hz_to_midi(f0[mask])
    if np.count_nonzero(mask)<min(18,len(mask)//6):
        raise ValueError("No se detectan suficientes notas cantadas. "
                         "Utiliza dos pistas vocales limpias, sin instrumentos.")
    rms=librosa.feature.rms(y=signal,frame_length=2048,
                           hop_length=hop,center=True)[0]
    times=librosa.frames_to_time(np.arange(len(midi)),sr=analysis_rate,hop_length=hop)
    rms=np.interp(times,librosa.frames_to_time(np.arange(len(rms)),sr=analysis_rate,
                                        hop_length=hop),rms).astype(np.float32)
    return {"time":times,"midi":midi,"voiced":mask,
            "rms":np.maximum(rms,1e-6),"duration":len(signal)/analysis_rate}


def _filled_midi(track):
    from scipy.ndimage import gaussian_filter1d
    a=np.asarray(track,dtype=float)
    valid=np.flatnonzero(np.isfinite(a))
    if not len(valid):raise ValueError("Falta información tonal")
    interpolated=np.interp(np.arange(len(a)),valid,a[valid])
    # Corregir outliers de pYIN con filtro robusto, conservando la curva
    # original para calcular después el vibrato de referencia.
    from scipy.ndimage import median_filter
    return median_filter(interpolated,size=5,mode="nearest")


def _warped_output(audio,source_sr,desired_len):
    """Ajusta tempo global con phase vocoder, NO por resampling de tono."""
    import librosa
    desired_len=int(desired_len)
    if abs(desired_len-len(audio))/max(1,len(audio))<.003:
        return audio.copy()
    ratio=desired_len/max(1,len(audio))
    output=librosa.effects.time_stretch(audio.T,rate=1/ratio)
    output=librosa.util.fix_length(output,size=desired_len,axis=-1).T
    return output.astype(np.float32)


def transfer(source,reference,output,melody=85,vibrato=70,dynamics=60,
             timing=75,max_seconds=240):
    """Transferir prosodia aproximada entre dos interpretaciones de la misma canción.

    No es un modelo de imitación de técnica vocal: el audio de entrada no se
    re-sintetiza como una nueva identidad. No clona voces.
    """
    import librosa
    import soundfile as sf
    from scipy.ndimage import gaussian_filter1d
    from vocal_tune_engine import decode

    a=Path(source).expanduser().resolve()
    b=Path(reference).expanduser().resolve()
    target=Path(output).expanduser().resolve()
    if not a.is_file() or not b.is_file():
        raise ValueError("Selecciona las dos grabaciones vocales existentes.")
    if target in (a,b) or target.exists():
        raise ValueError("El destino debe ser nuevo y no puede reemplazar voces originales.")
    params=dict(melody=melody,vibrato=vibrato,dynamics=dynamics,timing=timing)
    if any(not 0<=float(v)<=100 for v in params.values()):
        raise ValueError("Los porcentajes deben estar entre 0 y 100.")
    _log("Decodificando voces originales y de referencia.")
    mine,sr=decode(a)
    theirs,reference_sr=decode(b)
    own=mine.T.astype(np.float32)
    ref=theirs.T.astype(np.float32)
    duration=len(own)/sr
    ref_duration=len(ref)/reference_sr
    if duration>max_seconds or ref_duration>max_seconds:
        raise ValueError("Esta primera versión admite como máximo 4 minutos "
                         "por voz. Divide las grabaciones en fragmentos.")
    length_ratio=ref_duration/max(duration,1e-6)
    if not .7<=length_ratio<=1.3:
        raise ValueError("Las duraciones difieren demasiado para transferir "
                         "la misma canción (máximo ±30 %). Alinea las tomas.")
    if np.max(np.abs(own))<.002 or np.max(np.abs(ref))<.002:
        raise ValueError("Alguna de las voces está casi en silencio.")
    _log("Extrayendo curvas de notas y variaciones de voz.")
    original_features=extract_features(np.mean(own,axis=1),sr)
    reference_features=extract_features(np.mean(ref,axis=1),reference_sr)
    original_pitch=_filled_midi(original_features["midi"])
    reference_pitch=_filled_midi(reference_features["midi"])
    mine_mask=original_features["voiced"]
    ref_mask=reference_features["voiced"]
    # Reloj relativo, con tempos similares: evita imponer vocales/sonidos
    # de otro cantante sobre la señal de la voz del usuario.
    output_seconds=duration+(ref_duration-duration)*(timing/100.)
    desired_len=max(1,round(output_seconds*sr))
    _log("Ajustando la duración global sin alterar intencionalmente el tono.")
    rendered=_warped_output(own,sr,desired_len)
    frame_hop=max(120,round(sr*.12))
    window_size=max(1536,round(sr*.48))
    window_size=min(window_size,len(rendered))
    # Curvas normalizadas a la duración resultante. Una referencia que
    # interpreta OTRA canción no dispone de alineación fonética fiable.
    centers=list(range(0,len(rendered),frame_hop))
    if centers[-1]!=len(rendered)-1:centers.append(len(rendered)-1)
    normalized=np.asarray(centers)/max(1,len(rendered)-1)
    src_t=normalized*original_features["time"][-1]
    ref_t=normalized*reference_features["time"][-1]
    mf=original_features
    rf=reference_features
    valid_mine=np.interp(src_t,mf["time"],mine_mask.astype(float))>.6
    valid_ref=np.interp(ref_t,rf["time"],ref_mask.astype(float))>.6
    base_src=np.interp(src_t,mf["time"],original_pitch)
    base_ref=np.interp(ref_t,rf["time"],reference_pitch)
    # Octava natural: una voz grave no se convertirá en soprano por error.
    octave=12*round((float(np.median(original_pitch[mine_mask]))-
                     float(np.median(reference_pitch[ref_mask])))/12.)
    base_ref=base_ref+octave
    # Alisado suave retiene inflexiones: banda de nota a escala de 250 ms,
    # vibrato a escala menor. No se promete copiar respiraciones/dicción.
    fsrc=gaussian_filter1d(base_src,sigma=2.2)
    fref=gaussian_filter1d(base_ref,sigma=2.2)
    note_shift=(fref-fsrc)*(melody/100.)
    vibrato_ref=(base_ref-fref)
    vibrato_self=(base_src-fsrc)
    fine_shift=(vibrato_ref-vibrato_self)*(vibrato/100.)
    shifts=np.clip(note_shift+fine_shift,-6.,6.)
    shifts[~(valid_mine&valid_ref)]=0.
    voiced_count=int(np.count_nonzero(valid_mine&valid_ref))
    if voiced_count<max(8,len(shifts)//8):
        raise ValueError("Las frases cantadas no coinciden suficientemente. "
                         "Utiliza dos versiones aisladas de la misma canción.")
    _log("Transferencia controlada de entonación y vibrato en tu propia voz.")
    # Ventanas cruzadas para que una variación de tono no corte las sílabas.
    # Nunca procesar fragmentos en silencio, ni sumar ventanas fuera de rango.
    accum=np.zeros_like(rendered,dtype=np.float32)
    weight=np.zeros((len(rendered),1),dtype=np.float32)
    changed=0
    for position,shift,active in zip(centers,shifts,valid_mine&valid_ref):
        left=max(0,position-window_size//2)
        right=min(len(rendered),left+window_size)
        left=max(0,right-window_size)
        chunk=rendered[left:right]
        if len(chunk)<1024:continue
        # El alcance temporal se reduce en las uniones con silencios.
        if active and abs(float(shift))>.06:
            try:
                effected=librosa.effects.pitch_shift(chunk.T,sr=sr,
                                                      n_steps=float(shift)).T
                if len(effected)!=len(chunk):
                    effected=librosa.util.fix_length(effected.T,size=len(chunk)).T
                changed+=1
            except ValueError:
                effected=chunk
        else:
            effected=chunk
        # Hann con pequeña base para cubrir bordes del archivo.
        fade=np.hanning(len(chunk)).astype(np.float32)
        if left==0:fade[:len(chunk)//2]=1.0
        if right==len(rendered):fade[len(chunk)//2:]=1.0
        fade=np.maximum(fade,.0001)[:,None]
        accum[left:right]+=effected*fade
        weight[left:right]+=fade
    rendered=accum/np.maximum(weight,1.e-5)
    _log("Adaptando dinámica de la referencia sin cambiar el timbre.")
    if dynamics:
        # Comparar variaciones relativas, no copiar el volumen absoluto del
        # micro ni el compresor usado en la pista de referencia.
        t=np.arange(len(rendered),dtype=float)/sr
        normalized_t=t/max(float(t[-1]),1e-6)
        a_t=normalized_t*mf["time"][-1]
        b_t=normalized_t*rf["time"][-1]
        own_db=20*np.log10(np.maximum(1e-5,np.interp(a_t,mf["time"],mf["rms"])))
        ref_db=20*np.log10(np.maximum(1e-5,np.interp(b_t,rf["time"],rf["rms"])))
        own_db-=float(np.median(own_db[own_db>-50])) if np.any(own_db>-50) else 0.
        ref_db-=float(np.median(ref_db[ref_db>-50])) if np.any(ref_db>-50) else 0.
        difference=np.clip(ref_db-own_db,-6.,6.)*(dynamics/100.)
        difference=gaussian_filter1d(difference,sigma=max(1,sr*.065))
        gain=np.power(10.,difference/20.).astype(np.float32)
        rendered*=gain[:,None]
    peak=float(np.max(np.abs(rendered)))
    if peak>.98:rendered*=.98/peak
    target.parent.mkdir(parents=True,exist_ok=True)
    sf.write(str(target),rendered,sr,format="FLAC",subtype="PCM_24")
    return {"mode":"transferencia_interpretacion_asistida",
            "pitch_windows_changed":changed,"reference_used":str(b),
            "voiced_overlap_windows":voiced_count,
            "duration_seconds":round(len(rendered)/sr,3),
            "output_sample_rate":sr,"output_channels":rendered.shape[1],
            "melody_strength":int(melody),"vibrato_strength":int(vibrato),
            "dynamics_strength":int(dynamics),"timing_strength":int(timing),
            "reference_octave_adjustment":int(octave),
            "limitation":("Conserva muestras de la voz original. Aproxima "
              "melodía, vibrato, duración global y dinámica sobre la misma "
              "canción; no copia fonética, respiración, emoción ni técnica "
              "vocal completa, y no aprende un modelo persistente.")}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    parser.add_argument("--reference",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--melody",type=int,default=85)
    parser.add_argument("--vibrato",type=int,default=70)
    parser.add_argument("--dynamics",type=int,default=60)
    parser.add_argument("--timing",type=int,default=75)
    args=parser.parse_args()
    try:
        report=transfer(args.source,args.reference,args.output,
                        args.melody,args.vibrato,args.dynamics,args.timing)
        print("RESULTADO "+json.dumps(report,ensure_ascii=False),flush=True)
    except Exception as error:
        print("ERROR: "+str(error),file=sys.stderr,flush=True)
        raise SystemExit(1)

if __name__=="__main__":main()
