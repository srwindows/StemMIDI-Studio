"""Rutas del código y de los datos de StemMIDI Studio.

Compatible con proyecto fuente y con distribuciones PyInstaller.
Los recursos SVG y los motores empaquetados usan su ruta de instalación.
Las preferencias, bibliotecas y tareas usan el espacio de trabajo elegido.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

def resource_root(module_file):
    """Ruta de recursos de solo lectura (PyInstaller o código fuente).

    Nunca devolver la carpeta de proyectos para obtener ejecutables/script.
    """
    if getattr(sys,"frozen",False):
        return Path(getattr(sys,"_MEIPASS",Path(sys.executable).parent)).resolve()
    return Path(module_file).resolve().parent


def worker_script(module_file,filename):
    """Scripts auxiliares que se ejecutan mediante Python nativo del sistema.

    En paquetes macOS van en Resources/workers: el programa congelado no
    puede ejecutarse con sys.executable como si fuera Python normal.
    """
    name=Path(filename)
    if name.name!=str(filename) or name.suffix!=".py":
        raise ValueError("Nombre de script auxiliar incorrecto")
    home=resource_root(module_file)
    return home/("workers" if getattr(sys,"frozen",False) else "")/name


def ia_python(module_file):
    """Intérprete de IA independiente y nativo para macOS/Windows/Linux."""
    config=os.environ.get("STEMMIDI_IA_PYTHON","").strip()
    if config:
        return Path(config).expanduser().resolve()
    if sys.platform=="darwin" and getattr(sys,"frozen",False):
        # El intérprete y todos los paquetes de IA viajan dentro del .app.
        python=resource_root(module_file)/"ia_runtime"/"bin"/"python-ia"
        if not python.is_file():
            raise FileNotFoundError("Paquete macOS incompleto: falta Python IA integrado")
        return python
    root=workspace_root(module_file)
    if sys.platform=="win32":
        return root/"entorno_ia"/"Scripts"/"python.exe"
    return root/"entorno_ia"/"bin"/"python"


def ia_executable(module_file,filename="audio-separator"):
    """CLI del entorno IA; la extensión de Windows se resuelve aquí."""
    if not filename or Path(filename).name!=filename:
        raise ValueError("Nombre de ejecutable de IA incorrecto")
    packaged=os.environ.get("STEMMIDI_IA_CLI","").strip()
    if filename=="audio-separator" and packaged:
        binary=Path(packaged).expanduser().resolve()
        if not binary.is_file():
            raise FileNotFoundError("Falta audio-separator integrado: "+str(binary))
        return binary
    if sys.platform=="darwin" and getattr(sys,"frozen",False):
        binary=resource_root(module_file)/"ia_runtime"/"bin"/filename
        if not binary.is_file():
            raise FileNotFoundError("Falta ejecutable de IA integrado: "+str(binary))
        return binary
    parent=ia_python(module_file).parent
    return parent/(filename+".exe" if sys.platform=="win32" else filename)

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
