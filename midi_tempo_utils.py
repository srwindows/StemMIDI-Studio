"""Tempo MIDI sin modificar figuras, notas, compases ni resolución en ticks.

Los eventos set_tempo son metaeventos (microsegundos por negra).
El tempo modifica la traducción de ticks a segundos, nunca los ticks.
"""
from __future__ import annotations
import mido

MIN_BPM=35
MAX_BPM=300


def first_bpm(tracks):
    # Ante ausencia de set_tempo, el MIDI estándar usa 500000 µs/negra.
    # En tick cero, el último set_tempo en el orden de tracks prevalece.
    zero=None
    later=[]
    for tr in tracks:
        for tick,msg in tr.get("other",()):
            if msg.type!="set_tempo":continue
            if int(tick)==0:zero=int(msg.tempo)
            elif tick>0:later.append((int(tick),int(msg.tempo)))
    if zero is not None:
        return 60_000_000.0/zero
    return 120.0


def set_bpm_preserve_figures(tracks,bpm):
    """Modifica exclusivamente los eventos set_tempo y conserva ticks.

    Si hay varios cambios de tempo, los escala proporcionalmente,
    manteniendo las relaciones entre secciones musicales. Añade
    set_tempo en tick 0 si falta. Return False si no hubo cambios.
    """
    if not tracks:raise ValueError("Se necesita al menos una pista")
    bpm=float(bpm)
    if not (MIN_BPM<=bpm<=MAX_BPM):
        raise ValueError(f"BPM fuera del intervalo {MIN_BPM}–{MAX_BPM}: {bpm}")
    old=first_bpm(tracks)
    if abs(old-bpm)<.005:return False
    ratio=bpm/old
    has_start=False
    for tr in tracks:
        out=[]
        for tick,msg in tr.get("other",()):
            if msg.type=="set_tempo":
                newtempo=max(10000,min(16777215,round(msg.tempo/ratio)))
                msg=msg.copy(tempo=newtempo)
                if tick==0:has_start=True
            out.append((tick,msg))
        tr["other"]=out
    if not has_start:
        tracks[0]["other"].append((0,mido.MetaMessage("set_tempo",
                                           tempo=mido.bpm2tempo(bpm),time=0)))
        tracks[0]["other"].sort(key=lambda entry:entry[0])
    return True
