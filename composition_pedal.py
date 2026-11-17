"""Pedal armónico MIDI (CC64) condicionado por registro y rearticulación.

Regla de seguridad: CC64 gobierna TODO un canal, no cada nota por separado.
No se permite conservar graves con el pedal pisado al cambiar de acorde.
Se puede prolongar en C5+ durante una misma armonía, nunca a través de
cambios armónicos por accidente. No altera las notas ni el MIDI de origen.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
import os
from pathlib import Path

MODEL_RELATIVE=Path("datos_entrenamiento/catalogo_canciones/modelo_privado_pedal_armonico.json")

@lru_cache(maxsize=1)
def _model():
    roots=[Path(os.environ["STEMMIDI_WORKSPACE"])] if os.environ.get("STEMMIDI_WORKSPACE") else []
    roots.append(Path(__file__).resolve().parent)
    for root in roots:
        try:
            model=json.loads((root/MODEL_RELATIVE).read_text(encoding="utf-8"))
            if (model.get("type")=="private_piano_cc64_register_v1"
                    and model.get("distribution")=="PRIVATE_NOT_FOR_PUBLIC_RELEASE"
                    and model.get("piano_pedal_intervals",0)>=100):
                return model
        except (OSError,ValueError,TypeError):
            pass
    return None


def _duration_cap(lowest):
    """Límite por registro. Do5=72; CC64 no puede discriminar octavas."""
    defaults=(.39,.56,.79,.95)
    band=0 if lowest<48 else 1 if lowest<60 else 2 if lowest<72 else 3
    limit=defaults[band]
    trained=_model()
    if trained:
        items=trained.get("registers",{})
        key=("sub_bass","bass","middle","high")[band]
        item=items.get(key,{})
        if item.get("observations",0)>=75:
            q=float(item.get("q65_pedal_bars",limit))
            # Los datos de karaoke son ruidosos: solo pueden RECORTAR el
            # pedaleo grave/medio, no vulnerar el máximo armónico seguro.
            # El conjunto aportado contiene bases MIDI heterogéneas; sus
            # cuantiles de registros agudos son paradójicamente MÁS
            # cortos que los graves. Nunca copiar esa relación espuria.
            # Solo usar la estadística para recortar, conservando el
            # orden musical subgraves < graves < medios < agudos.
            if band==0:
                limit=min(limit,max(.30,q))
            elif band==1:
                limit=min(limit,max(.42,q))
            elif band==2:
                limit=min(limit,max(.68,q))
            # Do5+ conserva la ventana superior .95; el corpus no
            # demuestra que su q65=.42 sea deseable musicalmente.
    return limit


def pedal_events(notes,plan,bars,tpb,meter,channel,amount):
    """Genera on/off CC64 con margen seco en cambios de acorde y graves.

    Pedal_amount se interpreta sobre el máximo SEGURO de resonancia
    permitido para el registro, no como volumen ni como sustain global.
    """
    import mido
    bars=max(1,int(bars))
    tpb=max(1,int(tpb))
    bar=max(1,round(tpb*4*meter[0]/meter[1]))
    amount=max(0.,min(1.,float(amount)/100.))
    if not notes or not plan or amount<=0:
        return []
    end_of_song=bars*bar
    valid=[n for n in notes if n["end"]>n["start"]
           and n["start"]<end_of_song]
    if not valid:
        return []
    boundaries={0,end_of_song}
    for b in range(1,bars):
        tick=b*bar
        # Descanso en cualquier cambio armónico (incluye inversiones).
        chord_change=plan[b]!=plan[b-1]
        # Para C5+ y misma armonía se pueden ligar dos compases.
        low_or_mid=any(n["pitch"]<72 and n["start"]<tick+bar
                       and n["end"]>tick-bar for n in valid)
        if chord_change or low_or_mid or b%2==0:
            boundaries.add(tick)
    # Repeticiones de acorde con varias notas a la vez (también en
    # el interior del compás): repedal si hay notas inferiores a C5.
    for b in range(bars):
        first=b*bar;last=first+bar
        members=[n for n in valid if first<=n["start"]<last]
        if not members or min(n["pitch"] for n in members)>=72:
            continue
        onsets=Counter(int(n["start"]) for n in members)
        for tick,count in onsets.items():
            if count>=2 and first+round(.20*tpb)<tick<last-round(.10*tpb):
                boundaries.add(tick)
    stops=sorted(boundaries)
    output=[]
    for left,right in zip(stops,stops[1:]):
        in_segment=[n for n in valid if left<=n["start"]<right]
        if not in_segment:
            continue
        earliest=min(n["start"] for n in in_segment)
        # Incluye notas mantenidas desde el segmento previo: el pedal
        # afecta también a esas voces si todavía están activas.
        sounding=[n for n in valid if n["start"]<right and n["end"]>left]
        lowest=min(n["pitch"] for n in sounding)
        capacity=_duration_cap(lowest)
        # 10 ms a 120 BPM, por encima del ataque: pedaleo sincopado.
        delay=max(1,round(tpb*.02))
        start=earliest+delay
        # Espacio sin pedal antes del siguiente acorde/rearticulación.
        headroom=max(1,round(tpb*(.18 if lowest<60
                                   else .10 if lowest<72 else .04)))
        ceiling=right-headroom
        off=min(ceiling,earliest+round(
            (right-earliest)*capacity*amount))
        if off<=start:
            continue
        output.append((start,mido.Message("control_change",channel=channel,
                                         control=64,value=127,time=0)))
        output.append((off,mido.Message("control_change",channel=channel,
                                       control=64,value=0,time=0)))
    return output
