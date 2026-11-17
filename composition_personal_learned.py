"""Modelo estadistico MIDI: carga local privada opcional o perfil agregado publico.

No incluye canciones, letras ni datos de audio originales. Las etiquetas
de similitud ritmica no equivalen a generos musicales verificados.
"""
from __future__ import annotations
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import random

LABEL="Colección personal (MIDI/KAR)"
PRIVATE_RELATIVE=Path("datos_entrenamiento/catalogo_canciones/modelo_privado_multinstrumental.json")
PUBLIC_RELATIVE=Path("modelos_publicos/multinstrumental_markov_v1.json")
RELATIVE=PRIVATE_RELATIVE


@lru_cache(maxsize=1)
def load_model():
    roots=[]
    workspace=os.environ.get("STEMMIDI_WORKSPACE")
    if workspace:
        roots.append(Path(workspace))
    roots.append(Path(__file__).resolve().parent)
    for relative,expected_type,expected_distribution in (
        (PRIVATE_RELATIVE,"user_supplied_private_symbolic_markov_v1",
                          "PRIVATE_NOT_FOR_PUBLIC_RELEASE"),
        (PUBLIC_RELATIVE,"symbolic_markov_multinstrumental_v1",
                         "PUBLIC_AGGREGATED_MARKOV_V1"),
    ):
        for root in roots:
            try:
                item=json.loads((root/relative).read_text(encoding="utf8"))
                if (item.get("type")==expected_type
                        and item.get("distribution")==expected_distribution
                        and item.get("notes_or_lyrics_stored") is False
                        and item.get("training_metrics",{}).get("songs_train",0)>=300
                        and "global" in item.get("profiles",{})):
                    return item
            except (OSError,ValueError,TypeError):
                continue
    return None


def _mode(scale):
    return ("minor" if scale in ("Menor natural","Menor armónica",
                                  "Pentatónica menor") else "major")


def _profile(model,style):
    profiles=model["profiles"]
    key="rhythm_similarity:"+str(style)
    if style and key in profiles:
        return profiles[key]
    return profiles["global"]


def _chord_probs(model,scale,previous,style):
    mode=_mode(scale)
    global_profile=model["profiles"]["global"]["chords"][mode]
    row=global_profile["rows"].get(str(previous),{})
    unigram=global_profile["unigram"]
    count=sum(row.values())
    total=sum(unigram.values())
    general=[
        .7*(row.get(str(i),0)+.65)/(count+7*.65) +
        .3*(unigram.get(str(i),0)+.65)/(total+7*.65)
        for i in range(7)]
    extra=_profile(model,style)
    if extra is model["profiles"]["global"]:
        return general
    local=extra["chords"][mode]["rows"].get(str(previous),{})
    size=sum(local.values())
    if size<20:
        return general
    specific=[
        (local.get(str(i),0)+.75+5*general[i])/(size+7*.75+5)
        for i in range(7)]
    blend=.45*min(1.,size/100)
    return [(1-blend)*a+blend*b for a,b in zip(general,specific)]


def learned_plan(root,scale,bars,seed,style=None):
    model=load_model()
    if model is None:
        return None
    from piano_roll_tools import SCALES
    functional=("Mayor" if scale=="Pentatónica mayor" else
                "Menor natural" if scale=="Pentatónica menor" else scale)
    steps=SCALES[functional]
    if len(steps)!=7:
        return None
    rng=random.Random(seed)
    sequence=[0]
    for b in range(1,bars):
        weights=_chord_probs(model,functional,sequence[-1],style)
        if b>=2 and sequence[-1]==sequence[-2]:
            weights[sequence[-1]]*=.22
        sequence.append(rng.choices(range(7),weights=weights,k=1)[0])
    if bars>=4:
        sequence[-2:]=[4,0]
    result=[]
    for degree in sequence:
        fundamental=(root+steps[degree])%12
        notes=frozenset((root+steps[(degree+i)%7])%12 for i in (0,2,4))
        result.append((notes,fundamental))
    return result


def transition_bonus(scale,previous,current,style=None):
    model=load_model()
    if model is None:
        return 0.
    weights=_chord_probs(model,scale,previous,style)
    baseline=model["profiles"]["global"]["chords"][_mode(scale)]["unigram"]
    total=sum(baseline.values())
    p=weights[current]
    q=(baseline.get(str(current),0)+.65)/(total+7*.65)
    return max(-1.3,min(1.3,math.log(max(1e-9,p/q))))


def sample_interval(previous,rng,style=None):
    model=load_model()
    if model is None:
        return None
    global_profile=model["profiles"]["global"]
    key=str(max(-12,min(12,int(previous))))
    row=global_profile["intervals"].get(key,{})
    baseline=global_profile["interval_unigram"]
    n=sum(row.values())
    m=sum(baseline.values())
    choices=list(range(-12,13))
    weights=[
        .75*(row.get(str(k),0)+.6)/(n+25*.6) +
        .25*(baseline.get(str(k),0)+.6)/(m+25*.6)
        for k in choices]
    selected=_profile(model,style)
    if selected is not global_profile:
        local=selected["intervals"].get(key,{})
        total=sum(local.values())
        if total>=15:
            specific=[
                (local.get(str(k),0)+1+5*weights[i])/(total+25+5)
                for i,k in enumerate(choices)]
            blend=.4*min(1.,total/100)
            weights=[(1-blend)*a+blend*b for a,b in zip(weights,specific)]
    return rng.choices(choices,weights=weights,k=1)[0]
