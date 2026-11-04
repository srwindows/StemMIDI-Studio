"""Análisis privado de patrones GM de batería Roland.

Solo extrae estadísticas agregadas de ataques y acentos. No copia,
exporta ni incorpora los MIDI de Roland al ejecutable o al repositorio.
No infiere acordes o melodías de eventos de batería (canal MIDI 10).
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import hashlib
import math
import os

DEFAULT_SOURCE=Path.home()/'Musica'/'Ritmos_MIDI'
DRUM_CHANNEL=9
PERCUSSION_KICK={35,36}
PERCUSSION_SNARE={37,38,39,40}
PERCUSSION_HAT={42,44,46}
PROFILE_SLOTS=16


def _source():
    return Path(os.environ.get('STEMMIDI_RHYTHM_STYLES_DIR',str(DEFAULT_SOURCE)))


def _group(note):
    if note in PERCUSSION_KICK:return 'kick'
    if note in PERCUSSION_SNARE:return 'snare'
    if note in PERCUSSION_HAT:return 'hat'
    return 'other'


def analyze(path):
    import mido
    path=Path(path)
    mid=mido.MidiFile(str(path))
    if mid.type not in (0,1):
        raise ValueError('Patrón no admite MIDI tipo 2')
    meter=(4,4)
    for tr in mid.tracks:
        tick=0
        for msg in tr:
            tick+=msg.time
            if msg.type=='time_signature' and tick==0:
                meter=(msg.numerator,msg.denominator)
    bar_ticks=max(1,round(mid.ticks_per_beat*4*meter[0]/meter[1]))
    levels={k:[0.0]*PROFILE_SLOTS
            for k in ('kick','snare','hat','other')}
    accents=[0.0]*PROFILE_SLOTS
    counts=[0]*PROFILE_SLOTS
    bar_counts={}
    # Cada compás mantiene su propia huella estadística. El código previo
    # promediaba los 16 compases y perdía intros, redobles y contratiempos.
    individual_bars={}
    drum_notes=0
    max_tick=0
    for tr in mid.tracks:
        tick=0
        for msg in tr:
            tick+=msg.time
            max_tick=max(tick,max_tick)
            if msg.type!='note_on' or msg.velocity<=0 or msg.channel!=DRUM_CHANNEL:
                continue
            b=tick//bar_ticks
            slot=min(PROFILE_SLOTS-1,(tick%bar_ticks)*PROFILE_SLOTS//bar_ticks)
            group=_group(msg.note)
            levels[group][slot]+=1.
            accents[slot]+=msg.velocity/127.
            counts[slot]+=1
            bar_counts[b]=bar_counts.get(b,0)+1
            per_bar=individual_bars.setdefault(b,{
                 "kick":[0.]*PROFILE_SLOTS,"snare":[0.]*PROFILE_SLOTS,
                 "hat":[0.]*PROFILE_SLOTS,"other":[0.]*PROFILE_SLOTS,
                 "accent_sum":[0.]*PROFILE_SLOTS,"accent_count":[0]*PROFILE_SLOTS})
            per_bar[group][slot]+=1.
            per_bar["accent_sum"][slot]+=msg.velocity/127.
            per_bar["accent_count"][slot]+=1
            drum_notes+=1
    if not drum_notes:
        raise ValueError('No contiene golpes GM de batería, canal 10')
    # Profiles encode averaged / aggregated rhythm roles, not MIDI events.
    num_bars=max(1,math.ceil(max_tick/bar_ticks))
    for arr in levels.values():
        for i in range(PROFILE_SLOTS):
            arr[i]=round(arr[i]/num_bars,5)
    normalized_accents=[
        round(accents[i]/counts[i],4) if counts[i] else 0.
        for i in range(PROFILE_SLOTS)]
    kick=levels['kick'];snare=levels['snare'];hat=levels['hat']
    weights=[round(.2+kick[i]*2.9+snare[i]*1.8+
                    hat[i]*.38+levels['other'][i]*.25,5)
             for i in range(PROFILE_SLOTS)]
    bar_profiles=[]
    for b in range(num_bars):
        item=individual_bars.get(b)
        if item is None:
            # No suponer acentos rítmicos en un compás de silencio.
            bar_profiles.append({
                "weights":[0.05]*PROFILE_SLOTS,
                "accents":[0.]*PROFILE_SLOTS,"density":0.})
            continue
        local_weights=[
            round(.08+item["kick"][i]*2.9+
                  item["snare"][i]*1.8+item["hat"][i]*.38+
                  item["other"][i]*.25,5)
            for i in range(PROFILE_SLOTS)]
        local_accents=[
            round(item["accent_sum"][i]/item["accent_count"][i],4)
            if item["accent_count"][i] else 0.
            for i in range(PROFILE_SLOTS)]
        bar_profiles.append({
            "weights":local_weights,"accents":local_accents,
            "density":float(bar_counts.get(b,0))})
    return {
        'source':str(path),'name':path.parent.parent.name,
        'variant':path.stem,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'ticks_per_beat':mid.ticks_per_beat,'meter':list(meter),
        'bars':num_bars,'drum_notes':drum_notes,
        'density':round(drum_notes/num_bars,4),
        'weights':weights,'accents':normalized_accents,'levels':levels,
        'bar_profiles':bar_profiles,
        'has_drum_channel':True,
    }


@lru_cache(maxsize=8)
def _scan(directory):
    root=Path(directory)
    if not root.is_dir():return {}
    files=sorted(p for p in root.glob('*/PTN/*')
                 if p.is_file() and p.suffix.lower() in ('.mid','.midi')
                 and p.stat().st_size>=16)
    catalogue={}
    for p in files:
        try:info=analyze(p)
        except (OSError,ValueError,EOFError,TypeError):
            continue
        style=info['name']
        if style in catalogue:
            style=f"{style} ({p.stem.rsplit('_',1)[-1]})"
        info['style_id']=style
        catalogue[style]=info
    return catalogue


def available_styles():
    """Profiles read-only, no external Roland data included in release."""
    return _scan(str(_source()))


def profile(style):
    if not style:return None
    if str(style).startswith("motor:"):
        from composition_style_library import builtin_styles
        return builtin_styles().get(style)
    return available_styles().get(style)


def _rhythm_weights(item,bar_index=None):
    if not item:return None
    global_weights=item["weights"]
    local=item.get("bar_profiles")
    if bar_index is None or not local:return global_weights
    bar=local[int(bar_index)%len(local)]
    # Combina identidad global del género (35 %) con compás original
    # (65 %); no copia golpes concretos ni notas de batería.
    return [max(.05,round(.35*global_weights[i]+
                             .65*bar["weights"][i],5))
            for i in range(PROFILE_SLOTS)]


def groove_strength(item,slot,total_slots,bar_index=None):
    if not item:return 1.
    index=min(15,max(0,(int(slot)*16)//max(1,int(total_slots))))
    weights=_rhythm_weights(item,bar_index)
    return max(.06,float(weights[index]))


def groove_velocity(item,slot,total_slots,bar_index=None):
    if not item:return 0.
    i=min(15,max(0,(int(slot)*16)//max(1,int(total_slots))))
    v=item["accents"][i]
    local=item.get("bar_profiles")
    if bar_index is not None and local:
        lv=local[int(bar_index)%len(local)]["accents"][i]
        if lv:
            v=.35*v+.65*lv if v else lv
    return (v-.7)*28 if v else -5.


def groove_pulses(item,rng,bar_index,arpeggio=False):
    """Cada compás genera sus propios ataques desde la huella local."""
    if item is None:return []
    if item.get("kind")=="built_in":
        from composition_style_library import builtin_pulses
        return builtin_pulses(item,bar_index,arpeggio)
    weights=_rhythm_weights(item,bar_index)
    active=list(range(1,16))
    density=item["density"]
    local=item.get("bar_profiles")
    if local:
        local_density=local[int(bar_index)%len(local)]["density"]
        density=.5*density+.5*local_density
    count=(max(5,min(12,round(6+density/13)))
           if arpeggio else max(2,min(4,round(1+density/14))))
    slots={0}
    while len(slots)<count and active:
        j=rng.choices(range(len(active)),
                       weights=[max(.01,weights[s]**1.25) for s in active],
                       k=1)[0]
        slots.add(active.pop(j))
    return sorted(slots)
