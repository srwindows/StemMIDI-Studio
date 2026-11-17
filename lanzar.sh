#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
if ! command -v parec >/dev/null || ! command -v ffmpeg >/dev/null; then
    echo "Se necesitan los programas parec (pulseaudio-utils) y ffmpeg" >&2
    exit 1
fi
exec /usr/bin/python3 ./main.py "$@"
