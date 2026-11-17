"""Evaluación y corrección CONSERVADORA de partes MIDI generadas.

No es IA entrenada: métricas musicales interpretables y selección
determinista de alternativas. Nunca edita directamente MIDI de usuario.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from collections import Counter
import math
import statistics
from typing import Callable

from piano_roll_tools import SCALES


@dataclass(frozen=True)
class MusicalReview:
    score: float
    harmony: float
    phrasing: float
    expression: float
    instrument: float
    problems: tuple[str, ...]
    changes: int = 0

    @property
    def summary(self):
        issues=", ".join(self.problems[:2])
        return f"Calidad estimada {self.score:.0f}/100 (heurística)" + (
            f" · {issues}" if issues else " · sin alertas destacadas")


def _bar_size(tpb, meter):
    return max(1, round(tpb*4*meter[0]/meter[1]))


def _closest(pitch, pcs, lo, hi, target=None):
    eligible=[p for p in range(max(0,lo),min(127,hi)+1) if p%12 in pcs]
    if not eligible:
        return max(lo,min(hi,pitch))
    goal=pitch if target is None else target
    return min(eligible,key=lambda p:(abs(p-goal),abs(p-pitch),p))


def _scale_pcs(root,scale):
    return {(root+x)%12 for x in SCALES[scale]}


def _chord_pcs_by_bar(context,tpb,bars,meter,root,scale,plan=None):
    if plan is not None:
        assert len(plan)>=bars
        return [set(pcs) for pcs,_ in plan[:bars]]
    # Contexto real tiene prioridad: cubre progresiones que no están
    # en las siete tríadas diatónicas. Las notas muy cortas pesan menos.
    bar=_bar_size(tpb,meter)
    histograms=[[0.]*12 for _ in range(bars)]
    # Linear for ordinary short notes. Do not rescan EVERY note on
    # EVERY bar of a long MIDI; that could freeze the GUI.
    for n in context:
        if n['end']<=n['start']:continue
        begin=max(0,n['start']//bar)
        if begin>=bars:continue
        last=min(bars-1,(n['end']-1)//bar)
        for b in range(begin,last+1):
            overlap=max(0,min((b+1)*bar,n['end'])-
                        max(b*bar,n['start']))
            if overlap:
                histograms[b][int(n['pitch'])%12]+=(min(2.,overlap/
                                           max(1,bar/4)))
    result=[]
    for histogram in histograms:
        if sum(histogram)==0:
            result.append(set())
            continue
        ranking=sorted(range(12),key=lambda x:(-histogram[x],x))
        cutoff=histogram[ranking[0]]*.17
        result.append({pc for pc in ranking[:4]
                       if histogram[pc]>=cutoff})
    return result


def _strong(n,bar,tpb):
    # On beat/half bar: structural pitches should normally be chord tones.
    phase=n['start']%bar
    return (phase<=tpb//5 or abs(phase-bar//2)<=tpb//5
            or abs(phase-tpb)<=tpb//8)


def evaluate(notes, *, role, tpb, bars, meter=(4,4), root=0,
             scale='Mayor', context=(), plan=None, lo=36, hi=96,
             dynamics=100, events=()):
    """Score 0..100; independent dimensions, never edits inputs.

    A passing-tone dissonance on a weak beat is not treated like a
    structural clash. A flat-velocity part is valid at dynamics=0.
    """
    if role not in ('melody','harmony'):
        raise ValueError(f"Unknown musical role: {role}")
    bars=max(1,int(bars))
    bar=_bar_size(tpb,meter)
    valid=sorted((n for n in notes if n['end']>n['start']),
                 key=lambda n:(n['start'],n['pitch']))
    if not valid:
        return MusicalReview(0.,0.,0.,0.,0.,('Sin notas válidas',))
    scale_pcs=_scale_pcs(root,scale)
    chords=_chord_pcs_by_bar(context,tpb,bars,meter,root,scale,plan)
    # If scoring accompaniment against existing melody, the actual
    # candidate chords (not the melody) define harmonic ground.
    if role=='harmony':
        chords=_chord_pcs_by_bar(valid,tpb,bars,meter,root,scale)
    key_bad=sum(n['pitch']%12 not in scale_pcs for n in valid)
    bad_range=sum(n['pitch']<lo or n['pitch']>hi for n in valid)
    invalid=sum(n['end']<=n['start'] or n['velocity']<1 or n['velocity']>127
                for n in notes)
    strong=[n for n in valid if _strong(n,bar,tpb)]
    strong_bad=sum(
        n['pitch']%12 not in chords[min(bars-1,n['start']//bar)]
        for n in strong if chords[min(bars-1,n['start']//bar)])
    relevant=sum(bool(chords[min(bars-1,n['start']//bar)]) for n in strong)
    if role=='harmony' and context:
        # Compare the candidate's bar chords with strong melody notes,
        # not with its own chord-tones (which would be tautological).
        strong_context=[n for n in context if _strong(n,bar,tpb)
                        and n['start']<bars*bar]
        relevant=len(strong_context)
        strong_bad=sum(n['pitch']%12 not in chords[min(bars-1,n['start']//bar)]
                       for n in strong_context)
    harmony=100*(1-min(1.,(.66*key_bad/max(1,len(valid))+
                           .34*strong_bad/max(1,relevant))))
    pitches=[n['pitch'] for n in valid]
    # Excessive mechanical repetition vs intentional motifs: only
    # penalize several bars with exactly identical attack patterns.
    rhythmic_patterns=[]
    for b in range(bars):
        hits=tuple(sorted({n["start"]-b*bar for n in valid
                    if b*bar<=n["start"]<(b+1)*bar}))
        if hits:rhythmic_patterns.append(hits)
    from itertools import groupby
    max_same_rhythm=max((len(list(g)) for _,g in
                        groupby(rhythmic_patterns)),default=0)
    if role=='melody':
        leaps=sum(abs(b-a)>=13 for a,b in zip(pitches,pitches[1:]))
        repeats=max((len(list(group)) for _,group in groupby(pitches)),default=0)
        overlaps=sum(a['end']>b['start'] for a,b in zip(valid,valid[1:]))
        strict_grid=(sum(n['start']%max(1,tpb//2)==0 for n in valid)/
                     len(valid))
        mechanical=10 if len(valid)>=12 and strict_grid>.97 else 0
        steps=[abs(v-u) for u,v in zip(pitches,pitches[1:])]
        mean_step=sum(steps)/len(steps) if steps else 0
        contour_penalty=(min(12,(mean_step-7)*1.4) if mean_step>7
                         else 7 if mean_step<1.3 and len(steps)>8 else 0)
        phrase=100-35*leaps/max(1,len(pitches)-1)-(
            18 if repeats>=5 else 8 if repeats>=4 else 0)-(
            20*overlaps/max(1,len(valid)-1))-mechanical-contour_penalty
    else:
        # Repeating the same pitch while another voice is still held
        # can cause note-off conflicts for a polyphonic synth.
        previous={}
        conflicts=0
        for n in valid:
            key=(n['channel'],n['pitch'])
            if previous.get(key,-1)>n['start']:conflicts+=1
            previous[key]=max(previous.get(key,0),n['end'])
        phrase=100-35*conflicts/max(1,len(valid))
    if max_same_rhythm>=6:
        phrase-=min(12,(max_same_rhythm-5)*2.5)
    # A phrase-final dominant or unstable passing tone is not a
    # convincing resting point when the user's chosen harmony ends I.
    cadence_weak=False
    if plan is not None and valid:
        tonic_chord=set(plan[-1][0])
        last=max(valid,key=lambda n:(n['start'],n['end']))
        if last['pitch']%12 not in tonic_chord:
            cadence_weak=True
            phrase-=9
    # La evaluación antigua daba 96/100 a melodías dentro de la escala
    # pero DO3, o que se cruzaban con los acordes. Evaluar la SEPARACIÓN
    # entre partes, no solo las clases tonales de las notas.
    register_clashes=0
    if context:
        bounds=[None]*bars
        for other in context:
            if other['end']<=other['start']:continue
            left=max(0,int(other['start'])//bar)
            last=min(bars-1,(int(other['end'])-1)//bar)
            if left>=bars:continue
            for b in range(left,last+1):
                if bounds[b] is None:
                    bounds[b]=[other['pitch'],other['pitch']]
                else:
                    bounds[b][0]=min(bounds[b][0],other['pitch'])
                    bounds[b][1]=max(bounds[b][1],other['pitch'])
        for n in valid:
            b=min(bars-1,max(0,n['start']//bar))
            if bounds[b] is None:continue
            if role=='melody' and n['pitch']<bounds[b][1]+4:
                register_clashes+=1
            if role=='harmony' and n['pitch']>bounds[b][0]-5:
                register_clashes+=1
        fraction=register_clashes/max(1,len(valid))
        if fraction:
            phrase-=min(22.,22.*fraction)
    # Arpegios de dirección ÚNICA que suben continuamente no son una
    # frase; se requiere al menos cierta alternancia y regreso.
    monotonic_bars=0
    if role=='harmony':
        for b in range(bars):
            segment=sorted((n for n in valid
                            if b*bar<=n['start']<(b+1)*bar),
                           key=lambda n:(n['start'],n['pitch']))
            attacks=sorted({n['start'] for n in segment})
            if len(attacks)<5:continue
            melodic_line=[next(n['pitch'] for n in segment
                               if n['start']==tick) for tick in attacks]
            shifts=[y-x for x,y in zip(melodic_line,melodic_line[1:])
                    if y!=x]
            if len(shifts)>=4 and (all(x>0 for x in shifts)
                                   or all(x<0 for x in shifts)):
                monotonic_bars+=1
        if monotonic_bars:
            phrase-=min(20.,30.*monotonic_bars/max(1,bars))
    unique_vel=len({n['velocity'] for n in valid})
    spread=statistics.pstdev(n['velocity'] for n in valid) if len(valid)>1 else 0.
    expression=(100. if dynamics==0 else
                min(100.,45+min(45,spread*3.)+
                    min(10,unique_vel/3.)))
    instrument=(100*(1-bad_range/max(1,len(valid))))-min(35,invalid*10)
    if context and register_clashes:
        instrument-=min(50.,50.*register_clashes/max(1,len(valid)))
    issues=[]
    if key_bad:issues.append(f"{key_bad} notas fuera de escala")
    if relevant and strong_bad/relevant>.20:
        issues.append(f"{strong_bad} choques en tiempos fuertes")
    if bad_range:issues.append(f"{bad_range} notas fuera de registro")
    if register_clashes:
        issues.append(f"{register_clashes} notas cruzan registro de la otra pista")
    if monotonic_bars:
        issues.append(f"{monotonic_bars} compases de arpegio sin vaivén")
    if phrase<85:issues.append("fraseo, repetición o solapamientos")
    if max_same_rhythm>=6:issues.append("ritmo idéntico en demasiados compases")
    if cadence_weak:issues.append("final de frase sin resolución")
    if dynamics>0 and expression<72:issues.append("dinámica poco variada")
    if events:
        on=off=0
        pressed=None
        pedal_held=0
        for tick,msg in sorted(events,key=lambda item:item[0]):
            if msg.type=='control_change' and msg.control==64:
                if msg.value>=64:
                    on+=1
                    if pressed is None:pressed=tick
                else:
                    off+=1
                    if pressed is not None:
                        pedal_held+=max(0,tick-pressed)
                        pressed=None
        if on!=off:issues.append("pedal MIDI desequilibrado")
        if pedal_held>bars*bar*.94:
            issues.append("pedal excesivo para la claridad armónica")
    score=max(0.,min(100.,round(.41*harmony+.23*phrase+
                                .16*expression+.20*instrument,2)))
    return MusicalReview(score,round(harmony,1),round(phrase,1),
                         round(expression,1),round(instrument,1),
                         tuple(issues))


def correct_generated(notes, *, role,tpb,bars,meter=(4,4),root=0,
                      scale='Mayor',context=(),plan=None,lo=36,hi=96):
    """Repair small structural faults only on a COPY of generated notes.

    Preserve starts, durations, velocities and note count where possible:
    fixes should not destroy groove, expression or a user's original MIDI.
    """
    fixed=deepcopy(notes)
    ordered=sorted(fixed,key=lambda n:(n['start'],n['pitch']))
    chords=_chord_pcs_by_bar(context,tpb,bars,meter,root,scale,plan)
    scale_pcs=_scale_pcs(root,scale)
    bar=_bar_size(tpb,meter)
    changes=0
    for i,n in enumerate(ordered):
        pitch=n['pitch']
        target=max(lo,min(hi,pitch))
        if target!=pitch:
            n['pitch']=_closest(pitch,scale_pcs,lo,hi,target)
            changes+=1
        if n['pitch']%12 not in scale_pcs:
            n['pitch']=_closest(n['pitch'],scale_pcs,lo,hi)
            changes+=1
        if role=='melody':
            b=min(max(0,n['start']//bar),bars-1)
            if chords[b] and _strong(n,bar,tpb) and n['pitch']%12 not in chords[b]:
                # Only a close chord-tone correction (max 3 semitones),
                # not obliterating deliberate upper extensions or tensions.
                corrected=_closest(n['pitch'],chords[b]&scale_pcs,
                                   lo,hi)
                if abs(corrected-n['pitch'])<=3:
                    n['pitch']=corrected;changes+=1
            if i:
                prev=ordered[i-1]
                leap=abs(n['pitch']-prev['pitch'])
                if leap>=13:
                    # octave displacement: identical pitch class, less jump
                    option=n['pitch']+(-12 if n['pitch']>prev['pitch'] else 12)
                    if lo<=option<=hi and abs(option-prev['pitch'])<leap:
                        n['pitch']=option;changes+=1
                if n['start']<prev['end']:
                    prev['end']=max(prev['start']+1,n['start'])
                    changes+=1
    if role=='melody' and ordered and plan is not None:
        last=ordered[-1]
        final_pcs=set(plan[-1][0]) & scale_pcs
        if final_pcs and last['pitch']%12 not in final_pcs:
            landing=_closest(last['pitch'],final_pcs,lo,hi)
            if abs(landing-last['pitch'])<=5:
                last['pitch']=landing
                changes+=1
    if role=='harmony':
        # Avoid a repeated same-pitch note-on before its prior note-off.
        previous={}
        for n in ordered:
            key=(n['channel'],n['pitch'])
            prior=previous.get(key)
            if prior is not None and prior['end']>n['start']:
                old=prior['end']
                prior['end']=max(prior['start']+1,n['start'])
                if old!=prior['end']:changes+=1
            previous[key]=n
    return fixed,changes


def choose_best(generator:Callable[[int],tuple], *, base_seed:int,
                alternatives:int, role:str, score_kwargs:dict,
                repair_kwargs:dict, enabled=True, plan_fn=None):
    """Build bounded alternatives; evaluate before and after correction.

    Candidate output is (notes, events, source, profile) and is
    compatible with the MIDI API used by the interface.
    Existing user notes and MIDI tracks are not modified.
    """
    alternatives=max(1,min(8,int(alternatives))) if enabled else 1
    best=None
    for index in range(alternatives):
        seed=int(base_seed) if index==0 else (
            (int(base_seed)+index*0x9e3779b9)&0xffffffff)
        notes,events,source,profile=generator(seed)
        kwargs=dict(score_kwargs)
        repair=dict(repair_kwargs)
        if plan_fn is not None:
            harmonic_plan=plan_fn(seed)
            kwargs["plan"]=harmonic_plan
            repair["plan"]=harmonic_plan
        before=evaluate(notes,role=role,events=events,**kwargs)
        changed=0
        if enabled:
            repaired,changed=correct_generated(notes,role=role,**repair)
            after=evaluate(repaired,role=role,events=events,**kwargs)
            if after.score>=before.score:
                notes=repaired;review=after
            else:
                changed=0;review=before
        else:
            review=before
        rank=(review.score,-len(review.problems),-index)
        if best is None or rank>best[0]:
            best=(rank,(notes,events,source,profile),review,changed,index)
    _,result,review,changed,index=best
    return result,MusicalReview(
        review.score,review.harmony,review.phrasing,review.expression,
        review.instrument,review.problems,changed),index+1
