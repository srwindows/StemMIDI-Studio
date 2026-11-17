"""Identifica archivos que ya son stems de un separador musical.

Solo se reconocen patrones de exportación inequívocos; no se intenta
deducir el instrumento únicamente a partir de títulos arbitrarios.
"""
from __future__ import annotations
import re
from pathlib import Path

STEM_TAG = re.compile(r"\((vocals?|drums?|bass|other|piano|guitars?|instrumental)\)", re.I)
ENGINE_SUFFIX = re.compile(
    r"(?:^|[_ -])(htdemucs(?:_ft|_6s)?|demucs|mdx[_ -]?net|roformer|uvr[_ -]?mdx)(?:[_ .-]|$)", re.I)
DIRECT_STEM = re.compile(
    r"^(vocals?|drums?|bass|other|piano|guitars?|instrumental)(?:[-_ ]?\d+)?$", re.I)


def is_separated_stem(path):
    p=Path(path)
    name=p.stem
    parent=p.parent.name.lower()
    if STEM_TAG.search(name) and (
        ENGINE_SUFFIX.search(name)
        or "pistas_" in parent or "stems" in parent or "separad" in parent
    ):
        return True
    if DIRECT_STEM.fullmatch(name) and (
        "pistas_" in parent or "stems" in parent or "separad" in parent
    ):
        return True
    return False
