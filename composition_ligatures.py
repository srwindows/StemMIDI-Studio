"""Ligaduras MIDI: unión de notas iguales y articulación legato.

En MIDI no hay un evento estándar que "dibuje" una ligadura:
- Ligadura de prolongación: un único note_on/note_off para notas de
  igual altura/canal que deberían sonar sin reataque (merge).
- Ligadura de expresión: el note_off de la primera nota se aproxima
  al note_on de la siguiente, sin modificar la altura.
Jamás usar CC64 como sustituto. Prohibido cruzar canales o pistas.
"""
from __future__ import annotations
from copy import deepcopy


def link_melody(notes,tpb,intensity=100,mono=False):
    """Legato melódico no destructivo; no elimina notas distintas.

    Para instrumentos monofónicos, una nota termina como máximo en el
    inicio de la siguiente; para poly, hasta 1/64 negra de superposición
    (si no hay repetición de altura). La frase sigue respirando ante
    silencios largos y en límites estructurales de cuatro compases.
    """
    result=sorted((deepcopy(n) for n in notes),
                  key=lambda x:(x["start"],x["pitch"],x["end"]))
    if len(result)<2 or intensity<=0:return result
    tpb=max(1,int(tpb))
    strength=max(0.,min(1.,intensity/100))
    max_rest=round(tpb*.60*strength)
    overlap=0 if mono else max(1,round(tpb*.015*strength))
    for prev,nxt in zip(result,result[1:]):
        if prev["channel"]!=nxt["channel"]:continue
        if nxt["start"]<=prev["start"]:continue
        rest=nxt["start"]-prev["end"]
        if rest>max_rest or rest<-(tpb//5):continue
        if prev["pitch"]==nxt["pitch"]:
            # Las notas de igual altura en una melodía son articulaciones
            # deliberadas hasta que el usuario las LIGUE explícitamente.
            continue
        # No borrar la respiración al final de cada cuatro compases.
        bar=4*tpb
        if prev["start"]//(4*bar)!=nxt["start"]//(4*bar):
            continue
        target=max(prev["start"]+1,nxt["start"]+overlap)
        if mono:target=min(target,nxt["start"])
        # El legato no acorta notas sostenidas preexistentes.
        if target>prev["end"]:prev["end"]=target
    return result


def merge_tied_pitches(notes,tpb,indices=None,limit_beats=.4):
    """Unir notas repetidas, únicamente MISMA altura/canal y muy próximas.

    indices: subset de índices cuyo usuario ha solicitado ligar; al
    terminar devuelve (nuevo arreglo, número de uniones). Las notas no
    seleccionadas se conservan íntegras. No hay notas solapadas de la
    misma altura en un canal tras una unión.
    """
    result=[deepcopy(n) for n in notes]
    if len(result)<2:return result,0
    indices=set(range(len(result))) if indices is None else set(indices)
    candidates=sorted(indices,key=lambda i:(
        result[i]["channel"],result[i]["pitch"],result[i]["start"],i))
    removed=set();joined=0
    maximum_gap=max(0,round(max(1,int(tpb))*limit_beats))
    for j in range(1,len(candidates)):
        left=candidates[j-1]
        right=candidates[j]
        if left in removed or right in removed:continue
        a=result[left];b=result[right]
        if a["channel"]!=b["channel"] or a["pitch"]!=b["pitch"]:continue
        if b["start"]<a["start"]:continue
        gap=b["start"]-a["end"]
        if gap>maximum_gap:continue
        # No borrar una nota repetida después de una pausa expresiva.
        # Antes de unir, rechazar si existe otro ataque idéntico intermedio.
        if any(k not in (left,right) and k not in removed
               and n["channel"]==a["channel"] and n["pitch"]==a["pitch"]
               and a["start"]<n["start"]<b["start"]
               for k,n in enumerate(result)):
            continue
        a["end"]=max(a["end"],b["end"])
        removed.add(right)
        joined+=1
        # Facilitar cadenas de notas repetidas.
        candidates[j]=left
    return ([n for i,n in enumerate(result) if i not in removed],joined)


def tie_selected_notes(notes,indices,tpb,mono=False):
    """Herramienta manual del Piano Roll.

    Se unen notas idénticas seleccionadas; las distintas, si forman
    una línea y están próximas, se conectan mediante legato de duración.
    Evita la falsa ligadura entre voces simultáneas de acordes.
    """
    indices=set(indices)
    if len(indices)<2:return deepcopy(notes),0,0
    original=[deepcopy(n) for n in notes]
    selected_sorted=sorted(indices,key=lambda i:(
        original[i]["start"],original[i]["pitch"],i))
    distinct=[];adjusted=0
    beat=max(1,int(tpb))
    starts={n["start"] for i,n in enumerate(original) if i in indices}
    polyphonic=len(starts)<len(indices)
    if not polyphonic:
        for left,right in zip(selected_sorted,selected_sorted[1:]):
            a=original[left];b=original[right]
            if a["channel"]!=b["channel"] or a["pitch"]==b["pitch"]:
                continue
            gap=b["start"]-a["end"]
            if -beat//8<=gap<=beat:
                # Legato natural de nota distinta, sin retrigger del
                # pedal ni solapamiento en instrumentos monofónicos.
                new_end=b["start"] if mono else b["start"]+max(1,beat//64)
                if new_end>a["end"]:
                    a["end"]=new_end
                    adjusted+=1
    merged,joined=merge_tied_pitches(
        original,beat,indices=indices,limit_beats=1.)
    return merged,joined,adjusted


def tie_generated_chords(notes,tpb,meter=(4,4)):
    """Mantener notas comunes entre armonías sucesivas sin CC64.

    Solo considerar uniones cerca de un límite de compás. No unir la
    figura rítmica repetida dentro del mismo compás (p.ej. reguetón).
    """
    result=sorted((deepcopy(n) for n in notes),
                  key=lambda n:(n["channel"],n["pitch"],n["start"]))
    candidates={}
    for i,n in enumerate(result):
        candidates.setdefault((n["channel"],n["pitch"]),[]).append(i)
    removed=set()
    bar=max(1,round(tpb*4*meter[0]/meter[1]))
    gap_cap=max(1,round(tpb*.22))
    joined=0
    for ids in candidates.values():
        prev=ids[0]
        for index in ids[1:]:
            if prev in removed:prev=index;continue
            a=result[prev];b=result[index]
            if b["start"]<=a["start"]:prev=index;continue
            is_next_bar=(a["start"]//bar+1==b["start"]//bar)
            gap=b["start"]-a["end"]
            if is_next_bar and -tpb//8<=gap<=gap_cap:
                a["end"]=max(a["end"],b["end"])
                removed.add(index);joined+=1
            else:prev=index
    return sorted((n for i,n in enumerate(result) if i not in removed),
                  key=lambda n:(n["start"],n["pitch"],n["end"])),joined
