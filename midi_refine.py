"""Posprocesado de Basic Pitch a partir de su matriz REAL de activaciones.

No analiza metadatos ni inventa notas a partir del tempo; contrasta los
eventos con los ataques y activaciones del propio modelo neuronal.

Opciones:
  off: desactivado
  balanced: separar ataques internos claros, sin filtrar notas flojas
  strict: criterios más rigurosos (puede descartar notas suaves)
"""
from __future__ import annotations
from collections import defaultdict
import numpy as np
from scipy.signal import find_peaks


def refine_events(raw, output, mode="balanced", onset_threshold=.5,
                  frame_threshold=.3, min_length_ms=100):
    raw=list(raw)
    stats={"input_notes":len(raw),"output_notes":len(raw),"splits":0,
           "weak_rejected":0,"mode":mode}
    if mode=="off" or not output or len(raw)==0:
        return raw,{},stats
    onsets=output.get("onset")
    frames=output.get("note")
    if not isinstance(onsets,np.ndarray) or not isinstance(frames,np.ndarray):
        return raw,{},stats
    if (frames.ndim!=2 or onsets.ndim!=2 or
        frames.shape!=onsets.shape or frames.shape[1]<88):
        return raw,{},stats
    from basic_pitch.note_creation import model_frames_to_time
    times=np.asarray(model_frames_to_time(len(onsets)),dtype=float)
    # Basic Pitch usa 21 = A0 como primera clase; serie temporal de 86 fps.
    dt=float(np.median(np.diff(times))) if len(times)>2 else 256/22050
    result=[]
    attacks=defaultdict(list)
    # Separar requiere un pico significativamente más claro que el
    # umbral que creó la nota, para no contar vibrato como ataques.
    split_height=max(.54,float(onset_threshold)+.19)
    if mode=="strict":split_height=max(.61,float(onset_threshold)+.22)
    distance=max(5,int(.14/dt))
    minimum_piece=max(.125,float(min_length_ms)/1000.*.7)
    for raw_event in raw:
        a,b,p,amp,bend=raw_event
        a,b=float(a),float(b)
        p=int(p)
        idx=p-21
        if not 0<=idx<88 or b<=a:
            result.append(raw_event)
            continue
        lo=int(np.searchsorted(times,a))
        hi=int(np.searchsorted(times,b,side="right"))
        lo=max(0,min(lo,len(times)-1))
        hi=max(lo+1,min(hi,len(times)))
        note_curve=np.asarray(frames[lo:hi,idx],dtype=float)
        onset_curve=np.asarray(onsets[:,idx],dtype=float)
        if mode=="strict" and note_curve.size>2:
            support=float(np.quantile(note_curve,.6))
            # Un criterio suave y controlable, evita falsos positivos
            # sostenidos únicamente por 1-2 fotogramas.
            if support<max(.15,frame_threshold*.66):
                stats["weak_rejected"]+=1
                continue
        # Marca todos los ataques reconocidos para impedir que la fase
        # posterior "unir microcortes" fusione dos pulsaciones.
        peaks,_=find_peaks(onset_curve,height=split_height,
                          prominence=.20 if mode=="balanced" else .23,
                          distance=distance)
        local=[(float(times[i]),float(onset_curve[i])) for i in peaks
               if (a-.07)<=times[i]<=(b+.045)]
        for when,strength in local:
            attacks[p].append((when,strength))
        # Detectar ataques _dentro_ de una nota larga, y dividirla
        # cuando queda tiempo suficiente a cada lado.
        splits=[]
        for when,strength in local:
            if when-a<minimum_piece or b-when<minimum_piece:
                continue
            if splits and when-splits[-1]<minimum_piece:
                continue
            # Verificar que la activación de sustain no es sólo ruido.
            sample=int(np.searchsorted(times,when))
            span=frames[max(0,sample-2):min(len(times),sample+4),idx]
            if span.size and float(np.max(span))<max(.22,frame_threshold*.76):
                continue
            # Un ataque de amplitud media sólo se acepta si existió
            # una caída previa de energía de esa misma altura.
            prev=np.asarray(frames[max(0,sample-9):max(1,sample-2),idx])
            after=np.asarray(frames[sample:min(len(times),sample+6),idx])
            valley=(prev.size>0 and after.size>0 and
                    float(np.min(prev))<.80*max(.001,float(np.max(after))))
            if strength<.72 and not valley:
                continue
            splits.append(when)
        if not splits:
            result.append(raw_event)
            continue
        boundaries=[a]+splits+[b]
        for start,end in zip(boundaries,boundaries[1:]):
            result.append((start,end,p,amp,bend))
        stats["splits"]+=len(splits)
    for pitch,events in attacks.items():
        attacks[pitch]=sorted(events,key=lambda e:e[0])
    stats["output_notes"]=len(result)
    return result,dict(attacks),stats


def note_at_retrigger(attacks_by_pitch,pitch,start,tolerance=.060,threshold=.54):
    """Una nueva activación distingue pulsación independiente de microcorte."""
    if not attacks_by_pitch:return False
    for t,strength in attacks_by_pitch.get(int(pitch),()):
        if abs(float(t)-float(start))<=tolerance and strength>=threshold:
            return True
    return False
