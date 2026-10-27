#!/usr/bin/env python3
"""Regresión: notas espurias en silencio y sonidos suaves no deben confundirse.

Ejecutar con entorno_ia/bin/python (usa la misma versión del motor de IA).
No accede a archivos del usuario ni escribe en el proyecto.
"""
from __future__ import annotations
import sys
import tempfile
import wave
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from midi_engine import reject_silent_artifacts

with tempfile.TemporaryDirectory(prefix="stemmidi_test_silencio_") as temp:
    sr=22050
    sec=np.arange(sr,dtype=np.float32)/sr
    tone=.03*np.sin(2*np.pi*440*sec)
    samples=np.concatenate([tone,np.zeros(sr,dtype=np.float32),tone])
    source=Path(temp)/"audio_sintetico.wav"
    with wave.open(str(source),"wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes((np.clip(samples,-1,1)*32767).astype("<i2").tobytes())
    notes=[
        (.4,.7,69,95),
        (1.4,1.6,69,80),
        (2.4,2.8,69,95),
    ]
    filtered,discarded=reject_silent_artifacts(source,notes)
    assert discarded==1,(filtered,discarded)
    assert filtered==[notes[0],notes[2]]
    muted=Path(temp)/"silencio.wav"
    with wave.open(str(muted),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr)
        f.writeframes(bytes(sr*2*2))
    kept,discarded=reject_silent_artifacts(muted,notes)
    assert discarded==0 and kept==notes  # Señal global inaudible: no filtrar a ciegas.
    print("PASS SILENCIO: 1 falso positivo eliminado, 2 notas conservadas")
