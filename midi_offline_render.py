"""Render MIDI con el MISMO sintetizador FluidSynth y DSP de la preescucha B.

Modo auxiliar sin audio físico; se ejecuta en otro proceso de StemMIDI
para que la conversión no bloquee Qt ni cambie su dispositivo PipeWire.
"""
from __future__ import annotations
import json
import math
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import QCoreApplication
from midi_live_synth import LiveMidiSynth
from soundfont_catalog import system_soundfont


def render(config, output, cancelled=lambda:False):
    payload=json.loads(Path(config).read_text(encoding="utf-8"))
    midi=Path(payload["source"]).resolve()
    target=Path(output).resolve()
    if not midi.is_file() or midi.suffix.lower() not in (".mid",".midi",".kar"):
        raise ValueError("MIDI de origen no disponible")
    if not target.parent.is_dir():raise ValueError("Directorio temporal inválido")
    sr=int(payload["sample_rate"])
    if sr not in (44100,48000):raise ValueError("Frecuencia no admitida")
    parameters=payload["settings"]
    bank=parameters.get("soundfont")
    parameters["soundfont"]=Path(bank) if bank else system_soundfont()
    parameters["rate"]=SimpleNamespace(currentIndex=lambda:0 if sr==44100 else 1)
    card=SimpleNamespace(**parameters)
    synth=LiveMidiSynth()
    synth._card=card
    synth._original=False
    synth._sample_rate=sr
    try:
        events,duration=synth._timeline(midi)
        if not events:raise ValueError("El MIDI no contiene eventos reproducibles")
        synth._times=[seconds for seconds,_ in events]
        synth._tempo=max(.5,min(2.,card.tempo_percent/100))
        synth._duration_ms=int(duration*1000/synth._tempo)
        synth._create_synth(card.soundfont)
        synth.update_settings(force=True)
        total=max(1,math.ceil((duration/synth._tempo+2.0)*sr))
        event_index=0
        sample=0
        next_percent=-1
        with wave.open(str(target),"wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(3)  # PCM 24-bit
            writer.setframerate(sr)
            while sample<total:
                if cancelled():raise InterruptedError("Conversión cancelada")
                # Aplicar todos los mensajes con tiempo MIDI <= muestra actual.
                source_sec=sample/sr*synth._tempo
                while event_index<len(events) and events[event_index][0]<=source_sec+1e-9:
                    synth._dispatch(events[event_index][1])
                    event_index+=1
                frames=min(512,total-sample)
                if event_index<len(events):
                    next_frame=math.ceil(events[event_index][0]*sr/synth._tempo-1e-9)
                    if next_frame>sample:
                        frames=min(frames,next_frame-sample)
                if frames<=0:frames=1
                out=np.empty((frames,2),dtype=np.float32)
                synth._audio(out,frames,None,None)
                # PCM24, LE interleaved. Same samples as the audio callback;
                # no second EQ/compression/reverb in the FFmpeg encode stage.
                ints=(np.clip(out,-1.,1.)*8388607).astype("<i4")
                writer.writeframesraw(ints.view(np.uint8).reshape(-1,4)[:,:3].tobytes())
                sample+=frames
                percent=int(sample*100/total)
                if percent!=next_percent:
                    next_percent=percent
                    if percent%5==0:print(f"PROGRESS={percent}",flush=True)
        print("SYNTHESIS_PCM24_OK",flush=True)
    finally:
        synth.stop()


def cli(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if len(args)!=3 or args[0]!="--stemmidi-render":
        print("Uso: --stemmidi-render config.json salida.wav",file=sys.stderr)
        return 2
    QCoreApplication.instance() or QCoreApplication(["StemMIDI-render"])
    try:
        render(args[1],args[2])
        return 0
    except Exception as exc:
        print("ERROR: "+str(exc),file=sys.stderr,flush=True)
        return 1

if __name__=="__main__":
    sys.exit(cli())
