"""Modelo armónico/melódico aprendido del corpus CC0 OpenScore.

Entrenamiento fuera de línea en composition_corpus_training.py.
No inferencia neuronal y NO hay dependencias del catálogo comercial.
Modo opcional: los demás estilos conservan su lógica original.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import json
import math
import os
import random
import sys

LABEL="Clásica aprendida (OpenScore CC0)"
FILE="composition_learned_model.json"


@lru_cache(maxsize=1)
def load_model():
    roots=[Path(__file__).resolve().parent]
    workspace=os.getenv('STEMMIDI_WORKSPACE')
    if workspace:roots.append(Path(workspace))
    if hasattr(sys,'_MEIPASS'):roots.insert(0,Path(sys._MEIPASS))
    for root in roots:
        try:
            obj=json.loads((root/FILE).read_text(encoding='utf8'))
            if (obj.get('license')=='CC0-1.0' and
                    obj.get('type')=='symbolic_markov_v1' and
                    obj.get('scores_train',0)>=20):
                return obj
        except (ValueError,OSError):
            continue
    return None


def _mode(scale):
    return 'minor' if scale in ('Menor natural','Menor armónica',
                                'Pentatónica menor') else 'major'


def transition_bonus(scale,previous,current):
    """Bayesian chord-transition log odds against learned unigram.

    Bounded: cannot override the user's melodic input or chord selection.
    """
    model=load_model()
    if not model:return 0.
    mode=_mode(scale)
    row=model['chords'][mode].get(str(previous),{})
    uni=model['chord_unigram'][mode]
    prior=.8
    total=sum(row.values())
    nuni=sum(uni.values())
    p=(row.get(str(current),0)+prior)/(total+7*prior)
    q=(uni.get(str(current),0)+prior)/(nuni+7*prior)
    return max(-1.5,min(1.5,math.log(p/q)))


def sample_degrees(scale,bars,seed):
    """Seeded transition sampling, with explicit V→I at the final cadence."""
    model=load_model()
    if not model:return None
    rng=random.Random(seed)
    mode=_mode(scale)
    rows=model['chords'][mode]
    uniform=model['chord_unigram'][mode]
    total=sum(uniform.values())
    degrees=[0]
    for i in range(1,bars):
        previous=degrees[-1]
        row=rows.get(str(previous),{})
        n=sum(row.values())
        weights=[]
        for degree in range(7):
            prior=uniform.get(str(degree),0)/max(1,total)
            probability=(row.get(str(degree),0)+.75+6*prior)/(
                         n+7*.75+6)
            if i>=2 and degree==degrees[-1]==degrees[-2]:
                probability*=.17
            if i%4==3 and degree==0:probability*=1.25
            weights.append(probability)
        next_degree=rng.choices(range(7),weights=weights,k=1)[0]
        degrees.append(next_degree)
    if bars>=4:
        # Preserve well-defined closing tonality over random wandering.
        degrees[-1]=0
        degrees[-2]=4
    return degrees


def learned_plan(root,scale,bars,seed):
    """Like context_plan: list[(frozenset pitch_classes, root pc)]."""
    degrees=sample_degrees(scale,bars,seed)
    if degrees is None:return None
    from piano_roll_tools import SCALES
    functional=('Mayor' if scale=='Pentatónica mayor' else
                'Menor natural' if scale=='Pentatónica menor' else scale)
    steps=SCALES[functional]
    if len(steps)<7:return None
    plan=[]
    for degree in degrees:
        fundamental=(root+steps[degree])%12
        pcs=frozenset((root+steps[(degree+offset)%7])%12
                      for offset in (0,2,4))
        plan.append((pcs,fundamental))
    return plan


def sample_interval(previous,rng):
    """Melodic interval conditioned on preceding interval (semitones)."""
    model=load_model()
    if model is None:return None
    prev=str(max(-12,min(12,int(previous))))
    row=model['intervals'].get(prev,{})
    prior=model['interval_unigram']
    total=sum(prior.values())
    vals=list(range(-12,13))
    weights=[row.get(str(i),0)+.3+.45*prior.get(str(i),0)/
             max(1,total)*25 for i in vals]
    return rng.choices(vals,weights=weights,k=1)[0]
