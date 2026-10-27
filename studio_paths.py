"""Rutas del código y de los datos de StemMIDI Studio.

Compatible con proyecto fuente y con distribuciones PyInstaller.
Los recursos SVG y los motores empaquetados usan su ruta de instalación.
Las preferencias, bibliotecas y tareas usan el espacio de trabajo elegido.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

def workspace_root(module_file):
    install_dir=Path(module_file).resolve().parent
    explicit=os.environ.get("STEMMIDI_WORKSPACE","").strip()
    if explicit:
        folder=Path(explicit).expanduser().resolve()
        if folder.is_dir():
            return folder
    if getattr(sys,"frozen",False):
        # El paquete que se ejecuta desde nuestro proyecto de desarrollo
        # debe recuperar sus datos del original (no crear otro proyecto vacío).
        # Al copiar el paquete fuera de esta estructura, es independiente.
        for candidate in list(install_dir.parents)[:4]:
            if (candidate/"PROJECT_RESUME.txt").is_file() and \
               (candidate/"main.py").is_file() and \
               (candidate/"tareas_temporales").is_dir():
                return candidate.resolve()
    return install_dir
