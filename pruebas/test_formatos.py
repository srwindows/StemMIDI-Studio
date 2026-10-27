#!/usr/bin/env python3
"""Comprueba los seis codificadores con una señal sintética, sin capturar audio privado."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_engine import FORMAT_OPTIONS

success = True
for label, (ext, codec) in FORMAT_OPTIONS.items():
    dest = ROOT / "pruebas" / f"test_temporal.{ext}"
    dest.unlink(missing_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-f", "lavfi",
           "-i", "sine=frequency=440:sample_rate=48000:duration=1.0",
           "-ac", "2", *codec, "-n", str(dest)]
    encode = subprocess.run(cmd, capture_output=True, text=True)
    if encode.returncode:
        print("ERROR", label, encode.stderr.strip())
        success = False
        continue
    probe = subprocess.run(["ffprobe", "-v", "error",
                            "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
                            "-of", "default=nw=1", str(dest)],
                           capture_output=True, text=True)
    print(("OK" if probe.returncode == 0 else "ERROR"), label,
          f"{dest.stat().st_size:,} bytes", probe.stdout.replace("\n", " ").strip())
    success &= probe.returncode == 0 and dest.stat().st_size > 100
    dest.unlink(missing_ok=True)

sys.exit(0 if success else 1)
