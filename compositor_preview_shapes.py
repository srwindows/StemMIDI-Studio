"""Datos visuales de audio/MIDI para los clips del Compositor.

Solo lecturas; no toca los medios ni necesita acceso a audio en tiempo real.
Memoria y cálculos acotados, caché invalidada al cambiar el archivo.
"""
from __future__ import annotations
from array import array
from functools import lru_cache
from pathlib import Path
import math
import subprocess
import sys

@lru_cache(maxsize=256)
def audio_waveform(file_path,file_size,file_mtime,channels=320):
    """Picos de amplitud normalizados, máximo 5 min de decodificación."""
    path=Path(file_path)
    if not path.is_file() or path.stat().st_size!=file_size:
        return ()
    try:
        command=["ffmpeg","-hide_banner","-nostdin","-v","error",
                 "-i",str(path),"-t","300","-ac","1","-ar","320",
                 "-f","s16le","pipe:1"]
        result=subprocess.run(command,stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL,timeout=17,check=True)
        raw=result.stdout
        if len(raw)<2:return ()
        values=array("h");values.frombytes(raw[:len(raw)//2*2])
        if sys.byteorder!="little":values.byteswap()
        if not values:return ()
        bins=max(1,int(channels))
        length=len(values)
        samples_per_bin=max(1,math.ceil(length/bins))
        waveform=[]
        for offset in range(0,length,samples_per_bin):
            peak=max(abs(v) for v in values[offset:offset+samples_per_bin])
            waveform.append(min(1.,peak/32768))
        return tuple(waveform[:bins])
    except (OSError,subprocess.SubprocessError,ValueError):
        return ()


@lru_cache(maxsize=256)
def midi_note_bars(file_path,file_size,file_mtime):
    """(inicio en segundos, duración segundos, nota) de las primeras 5 min."""
    import mido
    path=Path(file_path)
    if not path.is_file() or path.stat().st_size!=file_size:
        return ()
    try:
        midi=mido.MidiFile(str(path))
        tempo=500000
        seconds=0.
        active={}
        bars=[]
        for msg in mido.merge_tracks(midi.tracks):
            seconds+=mido.tick2second(msg.time,midi.ticks_per_beat,tempo)
            if seconds>300:break
            if msg.type=="set_tempo":
                tempo=msg.tempo
            elif msg.type=="note_on" and msg.velocity:
                key=(msg.channel,msg.note)
                active.setdefault(key,[]).append(seconds)
            elif msg.type=="note_off" or (
                    msg.type=="note_on" and not msg.velocity):
                key=(msg.channel,msg.note)
                if active.get(key):
                    start=active[key].pop(0)
                    if len(bars)<6000:
                        bars.append((start,max(.01,seconds-start),msg.note))
        for (ch,pitch),starts in active.items():
            for start in starts:
                if len(bars)<6000:
                    bars.append((start,max(.01,seconds-start),pitch))
        return tuple(bars)
    except (OSError,EOFError,ValueError,TypeError):
        return ()


def data_for(file_path,kind):
    path=Path(file_path)
    try:
        stat=path.stat()
        signature=(str(path),stat.st_size,stat.st_mtime_ns)
        if kind=="midi":return midi_note_bars(*signature)
        return audio_waveform(*signature)
    except OSError:return ()
