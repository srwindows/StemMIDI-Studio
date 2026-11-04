"""StemMIDI Studio macOS: tool discovery, audio libraries and writable preferences."""
from pathlib import Path
import ctypes.util
import os
import sys

if sys.platform == "darwin" and getattr(sys, "frozen", False):
    app_contents = Path(sys.executable).resolve().parent.parent
    native = app_contents / "Resources" / "vendor" / "native"
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
    # Do NOT set DYLD_LIBRARY_PATH. It would shadow Qt multimedia's FFmpeg
    # libiconv and break every QMediaPlayer on macOS 14.0.
    if not os.environ.get("STEMMIDI_WORKSPACE"):
        home = Path.home() / "Library" / "Application Support" / "StemMIDI Studio"
        home.mkdir(parents=True, exist_ok=True)
        os.environ["STEMMIDI_WORKSPACE"] = str(home)
