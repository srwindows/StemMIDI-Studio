"""StemMIDI Studio macOS: runtime autónomo con Python IA, modelos y GM."""
from pathlib import Path
import ctypes.util
import os
import shutil
import sys

if sys.platform == "darwin" and getattr(sys, "frozen", False):
    contents = Path(sys.executable).resolve().parent.parent
    resources = contents / "Resources"
    native = resources / "vendor" / "native"
    native_bin = native / "bin"
    native_lib = native / "lib"
    if native_bin.is_dir():
        os.environ["PATH"] = str(native_bin) + os.pathsep + os.environ.get("PATH", "")
    library = native_lib / "libfluidsynth.3.dylib"
    if library.exists():
        original = ctypes.util.find_library
        def find_stemmidi_library(name):
            if str(name).lower() in ("fluidsynth", "libfluidsynth"):
                return str(library)
            return original(name)
        ctypes.util.find_library = find_stemmidi_library

    # No usar DYLD_LIBRARY_PATH: interfiere con FFmpeg/Qt Multimedia en Sonoma.
    if not os.environ.get("STEMMIDI_WORKSPACE"):
        workspace = Path.home() / "Library" / "Application Support" / "StemMIDI Studio"
        workspace.mkdir(parents=True, exist_ok=True)
        os.environ["STEMMIDI_WORKSPACE"] = str(workspace)
    else:
        workspace = Path(os.environ["STEMMIDI_WORKSPACE"]).expanduser()
    # Trabajadores Python ejecutados desde dentro del .app: ninguna dependencia
    # de rutas privadas del usuario, Homebrew, pip, micromamba o un entorno_ia externo.
    ai = resources / "ia_runtime"
    ai_python = ai / "bin" / "python-ia"
    ai_separator = ai / "bin" / "audio-separator"
    if not ai_python.is_file() or not ai_separator.is_file():
        raise RuntimeError("Instalador incompleto: faltan motores de IA macOS")
    os.environ["STEMMIDI_IA_PYTHON"] = str(ai_python)
    os.environ["STEMMIDI_IA_CLI"] = str(ai_separator)
    os.environ["PYTHONNOUSERSITE"] = "1"
    # Nunca escribir __pycache__ dentro del .app firmado; se invalida
    # la firma y Gatekeeper bloquea futuras ejecuciones.
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    cache = workspace / "cache_ia"
    (cache / "numba").mkdir(parents=True, exist_ok=True)
    (cache / "matplotlib").mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache / "numba")
    os.environ["MPLCONFIGDIR"] = str(cache / "matplotlib")
    os.environ.setdefault("XDG_CACHE_HOME", str(cache))

    gm = resources / "soundfonts" / "FluidR3_GM.sf2"
    if not gm.is_file():
        raise RuntimeError("Instalador incompleto: falta SoundFont General MIDI")
    os.environ["STEMMIDI_SOUNDFONT"] = str(gm)
    os.environ.setdefault("STEMMIDI_COMPOSITOR_SF2", str(gm))

    # Solo enlaces a los pesos dentro del propio .app: cero copia masiva
    # y cero bloqueo en el primer inicio. Se conserva todo fichero propio.
    # Las configuraciones JSON son pequeñas y se copian independientemente
    # para disponer del catálogo offline al abrir el gestor.
    model_source = resources / "ai_models"
    model_dest = workspace / "modelos"
    if model_source.is_dir():
        model_dest.mkdir(parents=True, exist_ok=True)
        for source in model_source.rglob("*"):
            if not source.is_file():continue
            relative=source.relative_to(model_source)
            if len(relative.parts)>2 or any(part.startswith(".") for part in relative.parts):
                continue
            suffix=source.suffix.lower()
            if suffix not in (".th",".ckpt",".onnx",".yaml",".yml",".json"):
                continue
            target=model_dest/relative
            try:
                if target.is_file():
                    continue
                if target.is_symlink():
                    previous=target.readlink()
                    if "StemMIDI Studio.app/Contents/" not in str(previous):
                        continue
                    target.unlink()
                target.parent.mkdir(parents=True,exist_ok=True)
                if suffix==".json":
                    tmp=target.with_name(target.name+".stemmidi_tmp")
                    shutil.copy2(source,tmp)
                    os.replace(tmp,target)
                else:
                    target.symlink_to(source.resolve())
            except OSError:
                # Un fallo de permisos no provoca bloqueo global.
                pass
