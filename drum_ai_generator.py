"""StemMIDI Drum AI: trained style-conditioned probabilistic MIDI drum generator.

The weights are learned on Debian from drum pattern MIDI files. The packaged
model contains aggregate statistics and motif counts, NOT source MIDI tracks.
No network, Torch download, or runtime training is required.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json
import random
import secrets

MODEL_NAME="stemmidi_drum_ai_trained_v1.json"
DEFAULT_ROLE_PITCH={
    "kick":36,"snare":38,"clap":39,"hat_closed":42,
    "hat_open":46,"tom":45,"ride":51,"crash":49,"percussion":54,
}
ORDER=("kick","snare","clap","hat_closed","hat_open","tom",
       "ride","crash","percussion")

def model_path():
    here=Path(__file__).resolve().parent
    for guess in (
        here/MODEL_NAME,
        here.parent/MODEL_NAME,
        here.parent/"ai_models"/MODEL_NAME,
        here.parent/"resources"/MODEL_NAME):
        if guess.is_file():
            return guess
    raise FileNotFoundError(
        "No está integrado el modelo de batería entrenado: "+MODEL_NAME)

def load_model(path=None):
    model=json.loads(Path(path or model_path()).read_text(encoding="utf8"))
    if model.get("format")!="stemmidi-drums-statistical-gen-v1":
        raise ValueError("Versión incompatible del modelo de batería")
    if model.get("training",{}).get("files_train",0)<100:
        raise ValueError("Modelo de batería sin datos de entrenamiento suficientes")
    if not model["global"]["roles"]:
        raise ValueError("Modelo de batería sin ritmos aprendidos")
    return model

def available_styles(model):
    """Expose every verified genre/substyle and the 13 General MIDI aggregates."""
    from drum_style_catalog import style_options
    from genre_rhythm_trained import load as load_gm_aggregates
    return style_options(model,load_gm_aggregates())


def available_patterns(model,style):
    """Return only the exact named profiles belonging to the chosen style."""
    from drum_style_catalog import pattern_options
    return pattern_options(model,style)


def _weighted_pairs(pairs,rg):
    if not pairs:return None
    return rg.choices([int(v) for v,_ in pairs],
                      weights=[max(0.01,int(cnt)) for _,cnt in pairs],k=1)[0]

def _choose_mask(role,genre,whole,rg,pattern=None):
    # Smooth styles with the universal learned prior in sparse genres.
    base=whole["global"]["roles"].get(role,{})
    specific=(whole["styles"].get(genre,{}).get("roles",{}).get(role,{})
              if genre else {})
    n=int(whole["styles"].get(genre,{}).get("bars",0)) if genre else 0
    style_weight=n/(n+45) if specific and n else 0
    learned=pattern.get("roles",{}).get(role,{}) if pattern else {}
    if learned.get("motifs") and rg.random()<.91:
        source=learned
    else:
        source=specific if rg.random()<style_weight else base
    motifs=source.get("motifs") or base.get("motifs") or []
    value=_weighted_pairs(motifs,rg)
    return int(value or 0)

def _choose_velocity(role,genre,whole,rg,pattern=None):
    global_data=whole["global"]["roles"].get(role,{})
    style_data=whole["styles"].get(genre,{}).get("roles",{}).get(role,{}) if genre else {}
    own=pattern.get("roles",{}).get(role,{}) if pattern else {}
    data=(own if own.get("vel") and rg.random()<.84
          else style_data if style_data.get("vel") and rg.random()<.83
          else global_data)
    bucket=_weighted_pairs(data.get("vel",[]),rg)
    if bucket is None:bucket=10
    return max(16,min(127,round(bucket*8 + rg.uniform(-3,3))))

def _choose_pitch(role,genre,whole,rg,pattern=None):
    base=whole["global"]["roles"].get(role,{})
    specific=whole["styles"].get(genre,{}).get("roles",{}).get(role,{}) if genre else {}
    own=pattern.get("roles",{}).get(role,{}) if pattern else {}
    samples=(own.get("pitches") or specific.get("pitches") or
             base.get("pitches") or [])
    chosen=_weighted_pairs(samples,rg)
    return int(chosen or DEFAULT_ROLE_PITCH[role])

def _choose_shift(role,genre,whole,rg,variation,pattern=None):
    # Learn microtiming distribution, never randomize arbitrary rhythms.
    data=whole["styles"].get(genre,{}).get("roles",{}).get(role,{}) if genre else {}
    own=pattern.get("roles",{}).get(role,{}) if pattern else {}
    if own.get("timing"):data=own
    if not data.get("timing"):data=whole["global"]["roles"].get(role,{})
    shift=_weighted_pairs(data.get("timing",[]),rg)
    return max(-.3,min(.3,float(shift or 0)*.1))*min(1,variation/30)

def _phase_probability(role,step,genre,whole):
    universal=whole["global"]["roles"].get(role,{})
    base=float(universal.get("phase",[0.02]*16)[step])
    specific=whole["styles"].get(genre,{}) if genre else {}
    learned=specific.get("roles",{}).get(role)
    if not learned:return base
    n=max(0,int(specific.get("bars",0)))
    return (float(learned["phase"][step])*n+20*base)/(n+20)

def generate(model,style=None,*,bars=4,ticks_per_beat=480,
             start_tick=0,variation=30,seed=None,pattern_id=None):
    """Return channel-10 GM drum notes learned from style rhythmic motifs.

    MIDI ticks and local tempo are inherited from the current Piano Roll.
    4/4 is required by training set; 6/8/3/4 are not silently approximated.
    """
    bars=int(bars)
    tpb=int(ticks_per_beat)
    start_tick=int(start_tick)
    variation=int(variation)
    if not 1<=bars<=64:raise ValueError("Compases de batería fuera de rango (1–64)")
    if tpb<24:raise ValueError("Resolución MIDI insuficiente para semicorcheas")
    if not 0<=variation<=100:raise ValueError("Variación fuera de rango")
    if style in ("General (aprendido)","General","Otros patrones",None,""):
        style=None
    elif style not in model.get("styles",{}):
        raise ValueError("El modelo no ha sido entrenado para ese estilo: "+str(style))
    profile=None
    if pattern_id is not None:
        found=model.get("profiles",{}).get(pattern_id)
        if found is None:
            raise ValueError("Patrón no encontrado en el modelo entrenado.")
        if style is not None and found["family"]!=style:
            raise ValueError("El patrón no pertenece al estilo elegido.")
        profile=found["model"]
    rg=random.Random(int(seed) if seed is not None else secrets.randbits(64))
    grid=tpb/4.0
    notes=[]
    bar_masks={}
    role_pitches={r:_choose_pitch(r,style,model,rg,profile) for r in ORDER}
    # Reuse a trained motif over a phrase to make coherent looping grooves.
    def build_once():
        output=[]
        for bar in range(bars):
            phrase_idx=bar//4
            bar_in_phrase=bar%4
            if phrase_idx not in bar_masks:
                learned={role:_choose_mask(role,style,model,rg,profile)
                         for role in ORDER}
                # A complete groove needs coherent kick/hat timekeeping.
                # Resample from the *learned* motif vocabulary, never inject
                # an invented fixed beat or a copied source MIDI sequence.
                if (style not in ("World",) and
                    (profile is None or any(k!=0 for k,c in
                         profile.get("roles",{}).get("kick",{}).get("motifs",[])))):
                    minimum=(2 if style in
                        ("Rock","Pop","House","Hip-Hop","Funk") else 1)
                    for _ in range(16):
                        if learned["kick"].bit_count()>=minimum:break
                        candidate=_choose_mask("kick",style,model,rg,profile)
                        if candidate.bit_count()>=minimum:
                            learned["kick"]=candidate;break
                    if learned["kick"]==0:
                        learned["kick"]=_choose_mask("kick",style,model,rg,profile)
                if not (learned["hat_closed"] or learned["ride"]):
                    for _ in range(12):
                        candidate=_choose_mask("hat_closed",style,model,rg,profile)
                        if candidate:
                            learned["hat_closed"]=candidate;break
                bar_masks[phrase_idx]=learned
            for role in ORDER:
                mask=bar_masks[phrase_idx][role]
                if bar_in_phrase==3 and variation>=20 and rg.random()<variation/170:
                    alternate=_choose_mask(role,style,model,rg,profile)
                    # A learned fill can vary the final 2 beats without
                    # destroying the main kick/snare groove of the phrase.
                    mask=(mask & 0x00FF) | (alternate & 0xFF00)
                if variation:
                    # Small conditional stochastic perturbation, anchored to
                    # the learned per-step probability for the chosen genre.
                    rate=min(.24,variation*.0024)
                    for step in range(16):
                        if rg.random()<rate:
                            probability=_phase_probability(role,step,style,model)
                            if rg.random()<probability:mask|=(1<<step)
                            else:mask&=~(1<<step)
                for step in range(16):
                    if not(mask & (1<<step)):continue
                    # Avoid two mutually exclusive hi-hats at one step.
                    if role=="hat_closed":
                        openmask=bar_masks[phrase_idx].get("hat_open",0)
                        if openmask&(1<<step):continue
                    velocity=_choose_velocity(role,style,model,rg,profile)
                    shift=_choose_shift(role,style,model,rg,variation,profile)
                    nominal=start_tick+(bar*16+step)*grid
                    begin=max(start_tick,round(nominal+shift*grid))
                    duration=max(1,round(grid*(.50 if role in
                        ("hat_closed","hat_open","ride") else .72)))
                    output.append({"start":int(begin),"end":int(begin+duration),
                        "pitch":role_pitches[role],"velocity":velocity,"channel":9})
        output.sort(key=lambda n:(n["start"],n["pitch"],n["end"]))
        # No overlapping repeated notes of the same drum voice.
        previous={}
        for entry in output:
            earlier=previous.get(entry["pitch"])
            if earlier is not None and earlier["end"]>=entry["start"]:
                earlier["end"]=max(earlier["start"]+1,entry["start"]-1)
            previous[entry["pitch"]]=entry
        return output
    for attempt in range(5):
        notes=build_once()
        if len(notes)>=max(2,bars*2):break
        bar_masks.clear()
    return notes

def training_summary(model):
    info=model["training"]
    return (f"Modelo final de {info['files_train']} patrones MIDI "
            f"y {info['samples_train']} compases. Validado previamente "
            f"con {info['files_heldout']} archivos excluidos del ajuste "
            f"durante la evaluación.")
