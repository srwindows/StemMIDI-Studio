"""Registros musicales y posición de generación en un piano roll multipista.

Reglas de acompañamiento:
- Melodía de piano: parte superior, normalmente C4 en adelante.
- Acordes de piano: C2–B3 por defecto, por debajo de la melodía.
- Con parte existente: hueco mínimo para evitar cruzar registros.
- Respetar notas originales: solo se devuelven límites para la parte nueva.

Los modelos de Markov de intervalos/acordes no conocen octavas: las
limitaciones son teoría musical explícita, NO estadísticas entrenadas.
"""
from __future__ import annotations


def bar_ticks(ticks_per_beat,meter):
    return max(1,round(ticks_per_beat*4*meter[0]/meter[1]))


def local_context(notes,start_tick,length_ticks):
    """Copiar y recortar las notas al tramo en el que se compondrá."""
    end=start_tick+length_ticks
    result=[]
    for n in notes:
        if n["start"]>=end or n["end"]<=start_tick:continue
        item=dict(n)
        item["start"]=max(n["start"],start_tick)-start_tick
        item["end"]=min(n["end"],end)-start_tick
        if item["end"]>item["start"]:
            result.append(item)
    return result


def bounds_for_role(role,context,requested_octave,program_profile,
                    auto_separation=True):
    """Devolver (min,max,centro) o una explicación si no hay registro."""
    lo=max(21,int(program_profile.lo))
    hi=min(108,int(program_profile.hi))
    pitches=sorted(int(n["pitch"]) for n in context
                   if n["end"]>n["start"])
    if not auto_separation:
        if role=="melody":
            center=max(lo,min(hi,12*(requested_octave+1)+0))
            return (lo,hi,center),None
        return (max(36,lo-5),min(hi,84),None),None

    if role=="melody":
        # No llevar la línea principal a C3 por un valor bajo heredado del
        # selector de octava: la línea automática se sitúa en C4..C6.
        lo=max(lo,60)
        hi=min(hi,92)
        if pitches:
            # Altura más alta de la armonía EXISTENTE en la sección.
            # Requerir margen respecto a la voz superior del acorde.
            other_top=max(pitches)
            lo=max(lo,other_top+4)
        if hi-lo<9:
            return None,(
                "No cabe la melodía por encima de los acordes existentes. "
                "Baja la octava del acompañamiento o desmarca «Separar registros».")
        # La tesitura melódica se centra en G4–D5 por defecto; conservar
        # la nota elegida solo cuando se mantiene en rango musical.
        preferred=max(67,12*(int(requested_octave)+1))
        center=max(lo,min(hi,preferred))
        hi=min(hi,max(lo+10,center+14))
        return (lo,hi,center),None

    if role=="harmony":
        if pitches:
            # No superponer los acordes con el bajo de la melodía.
            melody_bottom=min(pitches)
            upper=min(60,melody_bottom-5)
        else:
            upper=59
        lower=max(21,upper-23)
        if upper-lower<12:
            return None,(
                "La melodía existente está demasiado grave para colocar "
                "tres voces de acordes por debajo sin cruzarlas. "
                "Sube la melodía o desmarca «Separar registros».")
        return (lower,upper,max(lower,upper-16)),None
    raise ValueError(f"Rol musical inválido: {role}")


def shifted_output(notes,events,start):
    """Transformar una frase local en eventos MIDI de tiempo absoluto."""
    result=[]
    for n in notes:
        q=dict(n)
        q["start"]+=start
        q["end"]+=start
        result.append(q)
    return result,[(start+tick,msg.copy(time=0)) for tick,msg in events]
