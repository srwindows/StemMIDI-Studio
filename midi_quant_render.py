"""Cuantización musical no destructiva para el render MIDI.

Se transforman únicamente eventos note_on/off de una copia temporal.
Meta, control, canal, velocity, tempo y contenido SysEx permanecen intactos.
"""
from __future__ import annotations
import os, tempfile
from collections import defaultdict, deque
from pathlib import Path
import mido

QUANT_OPTIONS=[
 ("Sin cuantizar",None),
 ("Redonda · 1/1", (1,1)),
 ("Blanca · 1/2",(2,1)),
 ("Negra · 1/4",(4,1)),
 ("Corchea · 1/8",(8,1)),
 ("Semicorchea · 1/16",(16,1)),
 ("Fusa · 1/32",(32,1)),
 ("Semifusa · 1/64",(64,1)),
 ("Garrapatea · 1/128",(128,1)),
 ("Blanca tresillo · 1/2T",(2,3)),
 ("Negra tresillo · 1/4T",(4,3)),
 ("Corchea tresillo · 1/8T",(8,3)),
 ("Semicorchea tresillo · 1/16T",(16,3)),
 ("Fusa tresillo · 1/32T",(32,3)),
 ("Semifusa tresillo · 1/64T",(64,3)),
 ("Blanca con puntillo · 1/2.",(2,2)),
 ("Negra con puntillo · 1/4.",(4,2)),
 ("Corchea con puntillo · 1/8.",(8,2)),
 ("Semicorchea con puntillo · 1/16.",(16,2)),
 ("Fusa con puntillo · 1/32.",(32,2)),
 ("Semifusa con puntillo · 1/64.",(64,2)),
]
QUANT_DICT=dict(QUANT_OPTIONS)

def grid_ticks(ppq,grid):
    if grid is None:return None
    division,kind=grid
    if kind==3:return ppq * 8 / (division * 3) # triplets
    if kind==2:return ppq * 6 / division     # dotted
    return ppq * 4 / division

def quant_position(original,step,strength,swing=50):
    if step is None:return original
    if step<=0:raise ValueError("Rejilla de cuantización inválida")
    # swing desplaza el segundo pulso de cada pareja. 50 = recto.
    swing=max(50,min(75,swing))
    if swing!=50:
        period=step*2
        pair=int(original//period)
        relative=original-pair*period
        positions=[pair*period,pair*period+step*2*swing/100,
                   (pair+1)*period]
        goal=min(positions,key=lambda x:abs(x-original))
    else:
        goal=round(original/step)*step
    return max(0,round(original+(goal-original)*strength/100))

def quantize_copy(source,project,grid,amount=100,swing=50,ends=False):
    if grid is None or amount==0:return None
    if not 0<=amount<=100 or not 50<=swing<=75:
        raise ValueError("Fuerza/swing fuera de rango")
    midi=mido.MidiFile(str(source))
    if midi.type==2: # compatible también con MIDI tipo 2, por pista.
        pass
    step=grid_ticks(midi.ticks_per_beat,grid)
    for track in midi.tracks:
        abs_ticks=0
        events=[]
        active=defaultdict(deque)
        for index,message in enumerate(track):
            abs_ticks+=message.time
            events.append([abs_ticks,index,message])
            if message.type=="note_on" and message.velocity>0:
                key=(message.channel,message.note)
                active[key].append(len(events)-1)
            elif message.type=="note_off" or (message.type=="note_on" and message.velocity==0):
                key=(message.channel,message.note)
                if not active[key]:continue
                on_idx=active[key].popleft()
                onset=events[on_idx][0]
                new_on=quant_position(onset,step,amount,swing)
                events[on_idx][0]=new_on
                if ends:
                    new_end=quant_position(abs_ticks,step,amount,swing)
                else:
                    new_end=new_on+(abs_ticks-onset)
                events[-1][0]=max(new_on+1,new_end)
        # cuantizar notas que han quedado sin evento off
        for stack in active.values():
            for index in stack:
                events[index][0]=quant_position(events[index][0],step,amount,swing)
        # Conservar orden relativo en las coincidencias y end_of_track al final.
        # Eventos de tempo, cambios de programa y SysEx siguen en ticks originales.
        last_original=abs_ticks
        last_event=max((e[0] for e in events if e[2].type!="end_of_track"),default=0)
        for e in events:
            if e[2].type=="end_of_track":e[0]=max(last_original,last_event)
        events.sort(key=lambda e:(e[0],e[1]))
        absolute=0
        new_track=mido.MidiTrack()
        for position,_,event in events:
            new_track.append(event.copy(time=int(position-absolute)))
            absolute=position
        track.clear()
        track.extend(new_track)
    folder=Path(project)/"temporales"
    if not folder.is_dir():raise ValueError("No existe temporal del proyecto")
    fd,name=tempfile.mkstemp(prefix="_midi_cuantizado_",suffix=".mid",dir=folder)
    os.close(fd)
    out=Path(name)
    try:midi.save(out)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    return out
