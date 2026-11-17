"""Cambio no destructivo de instrumento MIDI exclusivo del Mezclador.

El archivo original conserva sus notas, tiempos y demás eventos.
Se sintetiza una copia temporal con el programa SoundFont elegido;
el canal GM 10 de batería nunca recibe el programa melódico.
"""
from __future__ import annotations
from pathlib import Path


def available_instruments(sf2):
    """Únicamente instrumentos melódicos que existen en el SoundFont real."""
    from soundfont_catalog import presets
    return tuple(sorted(((int(bank),int(program),str(name))
                         for bank,program,name in presets(sf2)
                         if 0<=int(bank)<128 and 0<=int(program)<=127),
                        key=lambda item:(item[0],item[1],item[2].casefold())))


def prepare_midi_for_instrument(original,output,instrument):
    """Crear MIDI temporal para FluidSynth, sin modificar notas ni original.

    instrument=(banco SF2, programa GM de 0 a 127), o None
    para reproducir los cambios de programa del archivo tal cual.
    """
    import mido
    input_path=Path(original)
    output_path=Path(output)
    if input_path.resolve()==output_path.resolve():
        raise ValueError("El MIDI original debe permanecer intacto")
    if instrument is None:
        raise ValueError("No hace falta generar una copia si no hay sustitución")
    bank,program=map(int,instrument)
    if not 0<=bank<=127 or not 0<=program<=127:
        raise ValueError("Banco o instrumento MIDI fuera de rango")
    midi=mido.MidiFile(str(input_path))
    # Detectar canales globalmente: los programas pueden residir en una pista
    # de control separada de la pista que contiene las notas.
    channels=sorted({msg.channel for track in midi.tracks for msg in track
                     if msg.type in ("note_on","note_off")
                     and getattr(msg,"channel",9)!=9})
    if not channels:
        raise ValueError("El MIDI no contiene notas melódicas")
    for track in midi.tracks:
        for msg in track:
            channel=getattr(msg,"channel",9)
            if channel not in channels:
                continue
            if msg.type=="program_change":
                msg.program=program
            elif msg.type=="control_change":
                if msg.control==0:msg.value=bank
                elif msg.control==32:msg.value=0
    # Colocar banco/programa al principio absoluto del archivo, sin
    # alterar el orden ni el tiempo de las notas posteriores.
    prefix=[]
    for channel in channels:
        prefix.extend((
            mido.Message("control_change",channel=channel,
                         control=0,value=bank,time=0),
            mido.Message("control_change",channel=channel,
                         control=32,value=0,time=0),
            mido.Message("program_change",channel=channel,
                         program=program,time=0),
        ))
    midi.tracks[0][:0]=prefix
    output_path.parent.mkdir(parents=True,exist_ok=True)
    midi.save(str(output_path))
    return output_path
