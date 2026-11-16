"""Descarga explícita y comprobada de modelos externos de StemMIDI.

Ejecutado como proceso independiente. No escribe en la biblioteca definitiva;
solo prepara pesos completos en un directorio temporal de la aplicación.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def _fail(message):
    print("ERROR " + str(message), flush=True)
    raise SystemExit(1)


def download_one(file, folder):
    name = str(file.get("path", ""))
    if Path(name).name != name or name in ("", ".", ".."):
        _fail("Nombre de descarga no válido")
    url = str(file.get("url", ""))
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        _fail("El origen debe ser el repositorio HTTPS autorizado")
    expected = int(file.get("bytes", 0))
    expected_hash = str(file.get("sha256", ""))
    if not (1 <= expected <= 12 * 1024**3 and len(expected_hash) == 64):
        _fail("Metadatos de integridad no válidos")
    target = folder / name
    if target.exists() or target.is_symlink():
        _fail("Descarga temporal ya existente: " + name)
    part = folder / (name + ".part")
    for attempt in range(3):
        digest = hashlib.sha256()
        read_bytes = 0
        try:
            print("INICIO " + name, flush=True)
            with urlopen(Request(url, headers={"User-Agent": "StemMIDI-Studio/1.1"}), timeout=35) as response:
                if urlsplit(response.url).scheme != "https":
                    raise ValueError("Redirección no segura")
                with part.open("xb") as out:
                    while True:
                        data = response.read(1024 * 1024)
                        if not data:
                            break
                        read_bytes += len(data)
                        if read_bytes > expected:
                            raise ValueError("Descarga supera el tamaño verificado")
                        out.write(data)
                        digest.update(data)
                        if read_bytes % (16 * 1024 * 1024) < len(data):
                            print(f"PROGRESO {name} {read_bytes}/{expected}", flush=True)
            if read_bytes != expected or digest.hexdigest().lower() != expected_hash.lower():
                raise ValueError("Tamaño o SHA-256 distinto del modelo verificado")
            os.replace(part, target)
            print("VERIFICADO " + name, flush=True)
            return
        except Exception as exc:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt == 2:
                _fail(name + ": " + str(exc))
            print("REINTENTO " + name + " " + str(exc), flush=True)
            time.sleep(1 + attempt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    entry = next((m for m in data.get("models", []) if m.get("id") == args.model), None)
    if not entry or entry.get("method") != "direct":
        _fail("El modelo no está autorizado para descarga directa")
    folder = Path(args.stage)
    if not folder.is_dir() or folder.is_symlink():
        _fail("Directorio temporal inexistente o no válido")
    for info in entry["files"]:
        download_one(info, folder)
    print("COMPLETADO", flush=True)


if __name__ == "__main__":
    main()
