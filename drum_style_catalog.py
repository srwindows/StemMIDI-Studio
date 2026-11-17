"""Grounded drum-style catalog and General MIDI aggregate profile registry.

Only titles supported by filename evidence from the already trained 944
GM drum MIDI profiles are promoted to *substyles*. A substyle selects from
its subset of trained source *statistics*, not from source MIDI notes.
Unknown/undecipherable filenames remain in Otros patrones.

General MIDI options use an existing local aggregate of 56 distinct files in 13
families (59 originals are currently not accessible). Never claim 59
separately learned styles or distribute the original source MIDI.
"""
from __future__ import annotations
import re
from collections import Counter

# (parent family, explicit filename regex, musical category override)
# Prefer literal recognizable style names. Do not infer a genre from
# generic filenames (AB_TR_31, B-LINE, FILL, DRUM2742, etc.).
SUBSTYLES = {
    "Balada": ("Pop", r"ballad|bald", "pop"),
    "Hard Rock": ("Hard Rock / Metal", r"^hrk_", "rock"),
    "Heavy Metal": ("Hard Rock / Metal", r"heavy|metal", "metal"),
    "R&B": ("Soul / Motown", r"r&b|rnb", "soul"),
    "Soul": ("Soul / Motown", r"^soul", "soul"),
    "Motown": ("Soul / Motown", r"motown", "soul"),
    "Deep House": ("House", r"deep", "house"),
    "Club House": ("House", r"club", "house"),
    "Eurodance": ("Dance", r"euroc", "dance"),
    "Dance Crossover": ("Dance", r"xover", "dance"),
    "Dance Break": ("Dance", r"dancebrk|dancbrk", "breakbeat"),
    "Rock serie SRK": ("Rock", r"^srk_", "rock"),
    "Jazz Rock": ("Jazz Fusión", r"jazzrock", "fusion"),
    "Batucada": ("Batucada / Afro", r"batucada", "afro"),
    "Olodum": ("Batucada / Afro", r"olodum", "afro"),
    "Conga latina": ("Percusión latina", r"conga", "latin"),
    "Mozambique": ("Percusión latina", r"mozamb", "latin"),
    "Samba brasileña": ("Samba", r"brazil|maracana", "samba"),
    "Reggae variante 128": ("Otros patrones", r"^128rega", "reggae"),
    "Industrial serie INDU": ("Otros patrones", r"^\d+indu", "industrial"),
    "Blues Rock": ("Otros patrones", r"bluezrok", "rock"),
}
# 13 *aggregate profiles*, not 13 uniquely supplied full MIDI songs.
GM = {
    "Balada": ("ballad", "Balada"),
    "Blues": ("blues", "Blues"),
    "Country": ("country", "Country"),
    "Fusión": ("fusion", "Jazz Fusión"),
    "Hard Rock": ("hard_rock", "Hard Rock"),
    "Hip-Hop": ("hiphop", "Hip-Hop"),
    "House": ("house", "House"),
    "Jazz": ("jazz", "Jazz"),
    "Metal": ("metal", "Heavy Metal"),
    "Pop": ("pop", "Pop"),
    "R&B": ("rnb", "R&B"),
    "Rock": ("rock", "Rock"),
    "Techno": ("techno", "Techno / Trance"),
}
GM_PREFIX="General MIDI · "

def genre_substyles(model):
    """Return substyle entries only if at least one file is truly classified."""
    profiles=model.get("profiles",{})
    out={}
    for title,(parent,pattern,category) in SUBSTYLES.items():
        matched=tuple(sorted(k for k,v in profiles.items()
                             if v["family"]==parent
                             and re.search(pattern,v["name"],re.I)))
        if matched:out[title]=matched
    return out

def family_for(style):
    if style in SUBSTYLES:return SUBSTYLES[style][0]
    if isinstance(style,str) and style.startswith(GM_PREFIX):
        found=GM.get(style[len(GM_PREFIX):])
        if found:return found[1]
    return style

def base_family(style):
    """Resolve nested aliases to the actual model training family."""
    current=style
    for _ in range(4):
        nxt=family_for(current)
        if nxt==current:return current
        current=nxt
    return current

def is_gm_aggregate(style):
    return isinstance(style,str) and (
        style.startswith(GM_PREFIX) and
        style[len(GM_PREFIX):] in GM)

def role_for(style):
    if style in SUBSTYLES:return SUBSTYLES[style][2]
    if isinstance(style,str) and style.startswith(GM_PREFIX):
        found=GM.get(style[len(GM_PREFIX):])
        if found:
            return {
                "ballad":"pop","blues":"blues","country":"country",
                "fusion":"fusion","hard_rock":"rock","hiphop":"hiphop",
                "house":"house","jazz":"jazz","metal":"metal",
                "pop":"pop","rnb":"soul","rock":"rock","techno":"techno"
            }[found[0]]
    return None

def gm_key(style):
    if isinstance(style,str) and style.startswith(GM_PREFIX):
        info=GM.get(style[len(GM_PREFIX):])
        if info:return info[0]
    return None

def style_options(model,gm_genres=None):
    counts=model.get("training",{}).get("style_counts",{})
    preferred=(
        "Rock","Pop","Blues","Funk","Hip-Hop","Rap","House",
        "Dance","Jazz","Jazz Swing","Bossa Nova","Salsa",
        "Rumba","Reggae","Country","Percusión latina")
    genres=sorted((name for name,count in counts.items()
                   if int(count)>0 and name!="Otros patrones"),
                  key=lambda name:(name not in preferred,
                                   preferred.index(name) if name in preferred else 999,
                                   name.casefold()))
    sub=genre_substyles(model)
    extras=sorted(sub,key=str.casefold)
    gm_profiles=[GM_PREFIX+name for name,(key,_) in GM.items()
            if key in (gm_genres or {})]
    return (["General (aprendido)"]+genres+extras+sorted(gm_profiles,key=str.casefold)
            +(["Otros patrones"] if counts.get("Otros patrones",0) else []))

def pattern_options(model,style):
    if is_gm_aggregate(style):
        # These are aggregate priors from 56 GM sources, not source MIDI
        # files. Do not mislabel the other 944 files as General MIDI patterns.
        return []
    family=base_family(style)
    profiles=model.get("profiles",{})
    subset=genre_substyles(model).get(style)
    if subset is not None:
        keys=subset
    else:
        keys=(k for k,v in profiles.items()
              if family in ("General (aprendido)","General",None,"")
              or v["family"]==family)
    return [(key,profiles[key]["name"]) for key in sorted(
        keys,key=lambda k:(profiles[k]["name"].casefold(),k))
            if key in profiles]
