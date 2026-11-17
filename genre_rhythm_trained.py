"""Perfiles rítmicos agregados de 56 bases MIDI de percusión GM del usuario.

No contiene canciones, patrones MIDI originales ni golpes individuales.
Las carpetas dieron las etiquetas: no es un clasificador de género validado,
ni un modelo de melodía/acordes condicionado por etiquetas verificadas.
"""
from functools import lru_cache
import json
from pathlib import Path
from studio_paths import resource_root

_FILENAME="genre_rhythm_trained_gm_v1.json"

@lru_cache(maxsize=1)
def load():
    # El proceso congelado usa resource_root; Python-IA ejecuta workers
    # desde Resources/workers y necesita resolver el directorio superior.
    roots=(resource_root(__file__),Path(__file__).resolve().parent.parent)
    for root in roots:
        try:
            data=json.loads((root/_FILENAME).read_text(encoding="utf8"))
        except (OSError,ValueError,TypeError):
            continue
        if (data.get("type")=="stemmidi_aggregated_gm_genre_rhythm_v1"
              and data.get("notes_or_events_embedded") is False
              and data.get("source_files_analyzed",0)>=50):
            return data.get("genres",{})
    return {}

def profile_for_label(label,family):
    """Asociación explícita entre etiqueta visible y ritmo agregado disponible."""
    name=label.lower()
    if "hard rock" in name:target="hard_rock"
    elif "heavy metal" in name or "metal" in name:target="metal"
    elif "punk" in name:target="rock"
    elif "rock" in name:target="rock"
    elif "pop" in name:target="pop"
    elif "balada" in name or "ballad" in name:target="ballad"
    elif "blues" in name:target="blues"
    elif "r&b" in name or "soul" in name:target="rnb"
    elif "jazz" in name:target="jazz"
    elif "hip hop" in name or "boom bap" in name:target="hiphop"
    elif "house" in name:target="house"
    elif "techno" in name:target="techno"
    elif "country" in name:target="country"
    elif "fusion" in name or "fusión" in name:target="fusion"
    else:
        target={"rock8":"rock","rock16":"rock","pop":"pop",
                "ballad":"ballad","swing":"jazz","blues":"blues",
                "hiphop":"hiphop","house":"house","techno":"techno",
                "country":"country"}.get(family)
    return load().get(target) if target else None

def weights(profile,arpeggio=False):
    """Pulsos binarios por compás, aprendidos de baterías de varios archivos."""
    if not profile:return None
    groups=profile.get("groups",{})
    kick=groups.get("kick",[])
    snare=groups.get("snare",[])
    hat=groups.get("hat",[])
    if not (len(kick)==len(snare)==len(hat)==16):return None
    if arpeggio:
        raw=[.4*kick[i]+.6*snare[i]+.75*hat[i] for i in range(16)]
    else:
        raw=[1.75*kick[i]+1.2*snare[i]+.16*hat[i] for i in range(16)]
    avg=max(.035,sum(raw)/16)
    return [max(.08,min(5.,.22+x/avg)) for x in raw]
