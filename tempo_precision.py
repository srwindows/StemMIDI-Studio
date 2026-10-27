#!/usr/bin/env python3
"""Análisis de tempo multipaso con grado de confianza y medias/dobles.

Nunca devuelve una precisión garantizada: en música rubato o melodías sin
percusión los tempos candidatos pueden diferir significativamente.
"""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import find_peaks


def _click_intervals(onsets, min_bpm=40, max_bpm=260):
    intervals=np.diff(onsets)
    if len(intervals)<3:
        return [],{}
    intervals=intervals[(intervals>0.09)&(intervals<2.2)]
    if not len(intervals):
        return [],{}
    # Varias notas pueden producir subdivisiones del pulso (corcheas, tresillos).
    proposals=[]
    for dt in intervals:
        for factor in (1,2,3,4):
            bpm=60*factor/dt
            if min_bpm <= bpm <= max_bpm:
                proposals.append(bpm)
    if not proposals:
        return [],{}
    pitches=np.array(proposals)
    # Agrupación en BPM enteros solo para encontrar picos; se estima con
    # medianas de valores crudos para sub-BPM posteriormente.
    bins=np.arange(40,262,1)
    hist,_=np.histogram(pitches,bins=bins)
    smoothed=np.convolve(hist,np.array([.20,.60,.20]),mode="same")
    peaks,_=find_peaks(smoothed,distance=6)
    chosen=sorted(peaks,key=lambda i:smoothed[i],reverse=True)[:12]
    return [float(np.median(pitches[abs(pitches-(bins[i]+0.5))<2.0])) for i in chosen
            if np.any(abs(pitches-(bins[i]+0.5))<2.0)],{"intervals":len(intervals)}


def _fold_near(value,target=115.):
    # Ambigüedad mitad/doble: por defecto usar zona musical habitual
    # pero mantener candidatos 1/2x y 2x para selección manual.
    options=[value*.25,value*.5,value,value*2.,value*4.]
    viable=[x for x in options if 60<=x<=180]
    if not viable:
        viable=[x for x in options if 40<=x<=260]
    return min(viable,key=lambda x:abs(np.log2(max(x,1e-5)/target))) if viable else value


def _refine_from_beats(pulses,bpm):
    """Refina el BPM usando separación de muchos pulsos, no un único frame."""
    if len(pulses)<8:return bpm
    period=60/max(1e-6,bpm)
    times=np.array(pulses,dtype=float)
    # Evaluar posibles fases con resolución 4 ms
    best=None
    for phase in np.linspace(0,period,90,endpoint=False):
        index=np.rint((times-phase)/period)
        error=np.abs((times-phase)-index*period)
        keep=error<min(.055,period*.13)
        if keep.sum()<7:continue
        strength=int(keep.sum())
        if best is None or strength>best[0]:
            best=(strength,index[keep],times[keep])
    if best is None:return bpm
    _,indices,observed=best
    if len(np.unique(indices))<6:return bpm
    coefficient=np.polyfit(indices,observed,1)
    slope=float(coefficient[0])
    if slope>0 and abs(60/slope-bpm)/bpm<.025:
        return 60/slope
    return bpm


def analyze(path, min_bpm=40, max_bpm=260, max_duration=170):
    path=Path(path)
    # Mismo decodificador FFmpeg que la separación y Audio a MIDI:
    # también permite analizar AAC, WMA, audio contenido en vídeo, etc.
    sr=22050
    cmd=["ffmpeg","-hide_banner","-nostdin","-v","error",
         "-threads","2","-i",str(path),"-map","0:a:0",
         "-t",str(float(max_duration)),"-vn","-sn","-dn",
         "-ac","1","-ar",str(sr),"-f","f32le","pipe:1"]
    result=subprocess.run(cmd,capture_output=True,timeout=100)
    if result.returncode:
        raise ValueError("FFmpeg no puede analizar esta pista: "+
                         result.stderr.decode("utf-8","replace")[-240:])
    y=np.frombuffer(result.stdout,dtype="<f4")
    if y.size < sr*3 or np.max(abs(y))<1e-4:
        return {"bpm":None,"confidence":0,"alternatives":[],
                "beat_offset":0,"reliable":False,
                "warning":"Audio demasiado corto o silencioso para determinar el tempo."}
    # Ventanas lejanas para no depender de una introducción libre o un puente.
    duration=len(y)/sr
    if duration > 72:
        starts=[min(max(0,duration-31),z) for z in (4,duration*.38,duration*.73)]
        windows=[y[int(st*sr):int(min(duration,st+30)*sr)] for st in starts]
    else:
        starts=[0]
        windows=[y]
    window_data=[]
    tempo_votes=[]
    onset_times_all=[]
    for start,seg in zip(starts,windows):
        hop=256
        onset=librosa.onset.onset_strength(y=seg,sr=sr,hop_length=hop)
        if onset.size<120 or max(onset)<.03:
            continue
        # Comparar librosa beat tracking con intervalos detectados.
        b,_beats=librosa.beat.beat_track(onset_envelope=onset,sr=sr,hop_length=hop,trim=True)
        track_tempo=float(np.asarray(b).reshape(-1)[0])
        pulses=librosa.onset.onset_detect(onset_envelope=onset,sr=sr,
                      hop_length=hop,backtrack=False,units="time")
        if len(pulses)<6:
            continue
        pulse_scores=[]
        candidates,_=_click_intervals(pulses,min_bpm,max_bpm)
        if min_bpm<=track_tempo<=max_bpm:
            candidates.insert(0,track_tempo)
        # Evaluación: comprobar qué proporción de tiempos de onset encaja en
        # una rejilla a cada tempo, permitiendo semicorcheas por nota.
        onset_weight=onset / max(np.max(onset),1e-8)
        times=np.arange(len(onset))*hop/sr
        indices,_=find_peaks(onset_weight,prominence=.14,distance=3)
        indices=sorted(indices,key=lambda i:onset_weight[i],reverse=True)[:180]
        if len(indices)<6:continue
        times=times[indices]
        strengths=onset_weight[indices]
        for bpm in candidates:
            if bpm < min_bpm or bpm > max_bpm:continue
            spacing=60/bpm
            # Encuentra fase de pulso con resolución 5 ms en un ciclo,
            # además de aceptar ataques en subdivisiones.
            phases=np.linspace(0,spacing,70,endpoint=False)
            scores=[]
            for phase in phases:
                distance=np.abs(((times-phase+spacing/8)%(spacing/4))-spacing/8)
                score=np.sum(strengths*np.exp(-.5*(distance/.026)**2))/max(strengths.sum(),1e-8)
                scores.append(score)
            best_idx=int(np.argmax(scores))
            pulse_scores.append((float(bpm),float(scores[best_idx]),float(phases[best_idx])))
        if not pulse_scores:continue
        pulse_scores.sort(key=lambda q:q[1],reverse=True)
        best=pulse_scores[0]
        tempo_votes.append(best[0])
        window_data.append((best[0],best[1],start+best[2],pulse_scores[:7]))
        onset_times_all.extend(start+pulses)
    if not window_data:
        return {"bpm":None,"confidence":0,"alternatives":[],
                "beat_offset":0,"reliable":False,
                "warning":"No se detectó un pulso rítmico estable."}
    # Evitar que medias/dobles incompatibles se anulen entre sí.
    normalized=[_fold_near(x) for x in tempo_votes]
    bpm=float(np.median(normalized))
    bpm=float(_refine_from_beats(onset_times_all,bpm))
    # Combina confianza del encaje de onsets y coherencia entre fragmentos.
    alignment=float(np.median([v[1] for v in window_data]))
    agreement=float(np.median(np.abs(np.log2(np.maximum(normalized,1)/bpm))))
    confidence=float(np.clip(.58*alignment+.42*max(0,1-agreement*3.2),0,1))
    alternatives=[]
    for factor in (.5,1.,2.):
        candidate=round(bpm*factor,2)
        if min_bpm<=candidate<=max_bpm and all(abs(candidate-x)>1.0 for x in alternatives):
            alternatives.append(candidate)
    candidates=[round(bpm,2)]+[v for v in alternatives if abs(v-bpm)>1]
    # Los tres análisis tienen que concordar; una mediana de error bajo
    # no basta si las secciones inicial y final divergen notablemente.
    # Ejemplo real (stem Mi princesa): 103 / 112 / 123 BPM recibían
    # "fiable", aun con una diferencia de más del 17 %.
    spread=(max(normalized)-min(normalized))/max(bpm,1e-6)
    coherent=spread<=.08 if len(normalized)>1 else True
    reliable=confidence>=.69 and agreement<.13 and coherent
    if len(window_data)==1 and confidence>.80:
        reliable=True
    if not coherent:
        warning=("Tempo variable o estimaciones incompatibles entre fragmentos "
                 f"({min(normalized):.1f}–{max(normalized):.1f} BPM). "
                 "Se muestra la mediana orientativa: verifica el tempo escuchando.")
    else:
        warning=("" if reliable else
                 "Tempo orientativo: poco pulso, síncopas, rubato o posible mitad/doble. Compruébalo escuchando.")
    if len(window_data)==1 and reliable:
        warning="Comprobado en un fragmento; podrían existir cambios de tempo en el resto de la canción."
    beat_offset=float(window_data[0][2])
    return {"bpm":round(bpm,2),"confidence":round(confidence,2),
            "alternatives":candidates[:3], "beat_offset":round(beat_offset,3),
            "reliable":reliable,"warning":warning,
            "segments":len(window_data),"segment_tempos":[round(x,2) for x in normalized]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    args=parser.parse_args()
    try:
        info=analyze(args.source)
        print(json.dumps(info,ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps({"error":str(exc)},ensure_ascii=False),flush=True)
        raise SystemExit(1)


if __name__=="__main__":
    main()
