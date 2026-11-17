"""ADSR MIDI no destructivo, mediante controlador de expresión CC11 por canal.
El ADSR afecta al canal completo cuando existen notas simultáneas.
"""
from __future__ import annotations
from pathlib import Path
import os
import tempfile
import mido

def adsr_copy(source, project, attack, decay, sustain, release):
    vals=(attack,decay,sustain,release)
    if any(type(v)!=int for v in vals) or any(not 0<=v<=2000 for v in (attack,decay,release)) or not 0<=sustain<=100:
        raise ValueError("Parámetros ADSR fuera de rango")
    if vals==(0,0,100,0):
        return None
    midi=mido.MidiFile(str(source))
    tempo=500000
    for tr in midi.tracks:
        found=next((m.tempo for m in tr if m.type=="set_tempo"),None)
        if found:
            tempo=found
            break
    factor=midi.ticks_per_beat*1000/tempo
    a,d,r=(round(x*factor) for x in (attack,decay,release))
    level=round(sustain*127/100)
    for tr in midi.tracks:
        when=0
        events=[]
        for order,msg in enumerate(tr):
            when+=msg.time
            if msg.type=="end_of_track":
                continue
            if msg.type=="note_on" and msg.velocity>0:
                ch=msg.channel
                if a:
                    events.append((when,0,order,mido.Message("control_change",channel=ch,control=11,value=1,time=0)))
                events.append((when,1,order,msg.copy(time=0)))
                if a:
                    events.append((when+a,2,order,mido.Message("control_change",channel=ch,control=11,value=127,time=0)))
                if d or level<127:
                    events.append((when+a+d,2,order,mido.Message("control_change",channel=ch,control=11,value=level,time=0)))
            elif msg.type=="note_off" or (msg.type=="note_on" and msg.velocity==0):
                if r:
                    ch=msg.channel
                    events.append((when+r//2,2,order,mido.Message("control_change",channel=ch,control=11,value=max(1,level//2),time=0)))
                    events.append((when+r,0,order,mido.Message("control_change",channel=ch,control=11,value=1,time=0)))
                events.append((when+r,1,order,msg.copy(time=0)))
            else:
                events.append((when,1,order,msg.copy(time=0)))
        events.sort(key=lambda entry:(entry[0],entry[1],entry[2]))
        rebuilt=mido.MidiTrack()
        last=0
        for tick,_,_,msg in events:
            rebuilt.append(msg.copy(time=tick-last))
            last=tick
        rebuilt.append(mido.MetaMessage("end_of_track",time=0))
        tr.clear()
        tr.extend(rebuilt)
    folder=Path(project)/"temporales"
    if not folder.is_dir():
        raise ValueError("Carpeta temporal inexistente")
    fd,name=tempfile.mkstemp(dir=folder,prefix="_adsr_",suffix=".mid")
    os.close(fd)
    try:
        midi.save(name)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)
