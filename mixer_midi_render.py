"""Executable de síntesis GM para MIDI asignado a canales del mezclador.

Únicamente resuelve el binario, sin modificar el SoundFont, MIDI ni ruteo.
"""
from pathlib import Path
import shutil
from studio_paths import resource_root


def fluidsynth_executable():
    root=resource_root(__file__)
    candidates=(
        root/"vendor/native/bin/fluidsynth",
        root/"native/bin/fluidsynth",
        root.parent/"native/bin/fluidsynth",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("fluidsynth")
