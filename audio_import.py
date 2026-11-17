#!/usr/bin/env python3
"""Importador compartido: sondeo por contenido y normalización sin pérdida a FLAC.

La compatibilidad depende de los decodificadores incorporados en FFmpeg local.
No acepta DRM, proyectos propietarios ni archivos sin una pista de audio legible.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

# Lista para el explorador y la importación masiva. Archivos con otras
# extensiones también se admiten individualmente si ffprobe reconoce audio.
MEDIA_EXTENSIONS = frozenset("""
wav wave bwf rf64 w64 aiff aif aifc au snd caf flac mp3 mp2 mpa
ogg oga opus spx vorbis m4a m4b aac alac wma asf wv ape mpc tta
amr ac3 eac3 dts a52 dsf dff mp4 m4v mov mkv mka webm avi
flv mpg mpeg vob ts m2ts mts 3gp 3g2 ogv ra rm tak ofr
""".split())

DIALOG_FILTER = (
    "Audio y vídeo habitual (*.wav *.wave *.flac *.mp3 *.mp2 *.ogg *.oga *.opus "
    "*.m4a *.aac *.wma *.aiff *.aif *.ape *.wv *.caf *.au *.ac3 "
    "*.dts *.amr *.dsf *.dff *.mp4 *.mkv *.mka *.mov *.avi *.webm *.flv "
    "*.mpg *.mpeg *.ts *.m2ts *.3gp);;"
    "Todos los archivos (*);;"
    "Audio sin pérdida (*.wav *.flac *.aiff *.aif *.ape *.wv *.caf);;"
    "Audio comprimido (*.mp3 *.m4a *.ogg *.opus *.wma *.aac *.amr);;"
    "Vídeo con audio (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.mpg *.mpeg *.m2ts)"
)

def supported_candidate(path):
    """Filtro de exploración masiva, no determina soporte del códec."""
    return Path(path).is_file() and Path(path).suffix.lower().lstrip(".") in MEDIA_EXTENSIONS


def probe_audio(path, timeout=12):
    """Verifica realmente que FFmpeg puede identificar un flujo de audio."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No existe el archivo: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"Archivo vacío: {path.name}")
    command = ["ffprobe", "-v", "error", "-show_entries",
               "stream=index,codec_type,codec_name,sample_rate,channels:format=duration,format_name",
               "-of", "json", str(path)]
    try:
        p = subprocess.run(command, capture_output=True, text=True,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"No se pudo examinar el audio: {e}") from e
    if p.returncode:
        raise ValueError(f"FFmpeg no puede leer {path.name}: {p.stderr.strip()[-250:]}")
    try:
        info = json.loads(p.stdout)
        stream = next(s for s in info.get("streams", []) if s.get("codec_type") == "audio")
    except (ValueError, KeyError, StopIteration, TypeError) as exc:
        raise ValueError(f"No hay ninguna pista de audio reconocible en: {path.name}") from exc
    fmt = info.get("format", {})
    try:
        duration = float(fmt.get("duration", 0) or 0)
    except ValueError:
        duration = 0
    return {
        "path": str(path),
        "codec": str(stream.get("codec_name", "desconocido")),
        "rate": int(stream.get("sample_rate", 0) or 0),
        "channels": int(stream.get("channels", 0) or 0),
        "duration": duration,
        "container": str(fmt.get("format_name", "")),
    }


def describe_audio(info):
    mins, secs = divmod(int(info["duration"]), 60)
    return (f"Formato detectado: {info['codec'].upper()} · {info['rate']} Hz · "
            f"{info['channels']} canal(es) · {mins:02}:{secs:02}")


def normalize_command(source, destination):
    """FFmpeg: PCM decodificado y FLAC 24 bits / 44.1 kHz, estéreo.

    Se selecciona la primera pista de audio, incluso en vídeos.
    La opción -n protege archivos preexistentes.
    """
    return ["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-n",
            "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
            "-ar", "44100", "-ac", "2",
            "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24",
            str(destination)]


def normalize_audio(source, destination, timeout=None):
    src = probe_audio(source)
    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise FileExistsError(f"Ya existe {dst}")
    cmd = normalize_command(src["path"], dst)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        dst.unlink(missing_ok=True)
        raise RuntimeError(f"Error al convertir entrada: {exc}") from exc
    if result.returncode:
        dst.unlink(missing_ok=True)
        raise RuntimeError(f"No se ha podido decodificar {Path(source).name}: {result.stderr[-700:]}")
    try:
        converted = probe_audio(dst)
    except ValueError:
        dst.unlink(missing_ok=True)
        raise
    if converted["duration"] <= 0:
        dst.unlink(missing_ok=True)
        raise RuntimeError(f"Sin audio decodificado: {source}")
    return converted


def main():
    parser = argparse.ArgumentParser(description="Importador universal FFmpeg para el monitor de grabación")
    parser.add_argument("source")
    parser.add_argument("destination")
    opts = parser.parse_args()
    result = normalize_audio(opts.source, opts.destination)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
