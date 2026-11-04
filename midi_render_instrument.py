"""Cambios de programa/banco y controladores MIDI sobre una COPIA temporal.

El MIDI original, su duración y las pistas ajenas a la selección se preservan.
"""
from __future__ import annotations
import os,tempfile
from pathlib import Path
import mido


def melodic_channels(midi):
    return sorted({m.channel for track in midi.tracks for m in track
                   if hasattr(m,'channel') and m.type in ('note_on','note_off')
                   and m.channel!=9})


def make_render_midi(original,project,program,channel=None,*,bank=0,effects=None):
    """Banco SF2 real: 0..127 para melodía, 128 para kit en canal 10.

    effects: nombre del controlador -> valor; únicamente inyección al inicio
    de los canales destinatarios, salvo sustain, que libera al final de cada
    pista para evitar notas colgadas. Nunca modifica el origen.
    """
    effects=dict(effects or {})
    if program is None and not effects:return None
    if program is not None and (type(program) is not int or not 0<=program<=127):
        raise ValueError('Programa SF2 fuera de 0–127')
    if type(bank) is not int or not 0<=bank<=16383:
        raise ValueError('Banco SF2 fuera de rango')
    midi=mido.MidiFile(str(original))
    available=melodic_channels(midi)
    if any(m.type in ('note_on','note_off') and getattr(m,'channel',None)==9
           for tr in midi.tracks for m in tr):available.append(9)
    # La batería sólo se reemplaza con un preset de batería explícito.
    if bank==128 and program is not None:
        chosen=[9] if 9 in available else []
    elif channel==9:
        chosen=[9] if 9 in available else []
    elif channel is None:
        chosen=[ch for ch in available if ch!=9]
    else:
        chosen=[channel] if channel in available and channel!=9 else []
    if not chosen:raise ValueError('No hay notas en los canales MIDI seleccionados')
    chosen=set(chosen)
    controls={'sustain':64,'modulation':1,'expression':11,
              'brightness':74,'resonance':71}
    valid={**controls,'pitch_bend':None}
    for key,value in effects.items():
        if key not in valid:raise ValueError('Efecto MIDI no reconocido: '+str(key))
        limit=(-8192,8191) if key=='pitch_bend' else (0,127)
        if type(value) is not int or not limit[0]<=value<=limit[1]:
            raise ValueError('Valor MIDI fuera de rango')
    # Sustituir todos los cambios de programa de los canales elegidos,
    # incluso si viven en pistas de control independientes.
    for track in midi.tracks:
        if program is not None:
            for message in track:
                if message.type=='program_change' and message.channel in chosen:
                    message.program=program
                elif (message.type=='control_change' and
                      message.channel in chosen and message.control in (0,32)):
                    # El MIDI fuente puede tener cambios de banco posteriores;
                    # éstos no deben devolver el timbre a otro SF2 bank.
                    message.value=(bank if bank!=128 else 0) if message.control==0 else 0
            # Control de banco previo al primer evento MIDI por canal;
            # la selección se aplica a la pista que contiene sus notas.
            present={m.channel for m in track if
                     m.type in ('note_on','note_off') and m.channel in chosen}
            for ch in sorted(present,reverse=True):
                initial=[mido.Message('program_change',channel=ch,program=program,time=0)]
                if bank and bank!=128:
                    if bank>127:raise ValueError('Banco melódico no representable por TiMidity')
                    # SF2 de TiMidity selecciona el banco con CC0 (MSB).
                    # CC32=bank reprodujo erróneamente el timbre del banco 0.
                    initial=[mido.Message('control_change',channel=ch,
                             control=0,value=bank,time=0),
                             mido.Message('control_change',channel=ch,
                             control=32,value=0,time=0),*initial]
                for msg in reversed(initial):track.insert(0,msg)
    if effects:
        # Añadir parámetros a un único track para cada canal, evitando
        # multiplicar controles cuando el MIDI tiene varias pistas.
        for ch in sorted(chosen):
            track=next((t for t in midi.tracks if any(
                m.type in ('note_on','note_off') and m.channel==ch for m in t)),None)
            if track is None:continue
            initial=[]
            for key,value in effects.items():
                if key=='pitch_bend':
                    initial.append(mido.Message('pitchwheel',channel=ch,pitch=value,time=0))
                else:
                    initial.append(mido.Message('control_change',channel=ch,
                        control=controls[key],value=value,time=0))
            for msg in reversed(initial):track.insert(0,msg)
            if effects.get('sustain',0)>=64:
                # Insertar release en el mismo tick final, sin alterar duración.
                insert=len(track)
                if insert and track[-1].type=='end_of_track':insert-=1
                track.insert(insert,mido.Message('control_change',channel=ch,
                                      control=64,value=0,time=0))
    tempdir=Path(project)/'temporales'
    if not tempdir.is_dir():raise ValueError('El proyecto no tiene carpeta temporal')
    fd,name=tempfile.mkstemp(prefix='_midi_instrumento_',suffix='.mid',dir=tempdir)
    os.close(fd)
    result=Path(name)
    try:midi.save(result)
    except Exception:
        result.unlink(missing_ok=True)
        raise
    return result
