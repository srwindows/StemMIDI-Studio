"""Catálogo común de archivos vocales auténticos del proyecto activo.

No se crean ni copian pistas. Las etiquetas proceden de nombres reconocibles,
limitados a carpetas vocales del proyecto para evitar falsos positivos.
"""
import re
import unicodedata
from pathlib import Path

AUDIO={".wav",".flac",".mp3",".ogg",".opus",".m4a",".aif",".aiff"}
LABELS=("Voz principal","Voz limpia","Coros","Voz afinada",
        "Voz interpretada","Voz masculina","Voz femenina")
VOCAL_FOLDERS={"voces","afinacion_vocal","vocal"}


def _tokens(name):
    txt=unicodedata.normalize("NFKD",name.casefold())
    txt="".join(c for c in txt if not unicodedata.combining(c))
    return set(re.findall(r"[a-z]+",txt))


def vocal_role(path):
    """Clasificación solo en carpetas vocales y usando el nombre del audio."""
    path=Path(path)
    if not any(x.casefold() in VOCAL_FOLDERS for x in path.parts):
        return None
    n=path.stem.casefold()
    tokens=_tokens(path.stem)
    if "(male)" in n or "masculina" in tokens:return "Voz masculina"
    if "(female)" in n or "femenina" in tokens:return "Voz femenina"
    if ("(instrumental)" in n or "(backing)" in n
            or tokens.intersection({"coros","coro","backing","harmonies","harmonias"})):
        return "Coros"
    if (("limpia" in tokens and tokens.intersection({"voz","voces"}))
            or ("clean" in tokens and tokens.intersection({"vocal","vocals","voice","voices"}))
            or "acapella" in tokens or "acappella" in tokens):
        return "Voz limpia"
    if "afinada" in tokens or "tuned" in tokens:return "Voz afinada"
    if "interpretada" in tokens:return "Voz interpretada"
    if ("(vocals)" in n or "(lead)" in n or "principal" in tokens
            or "lead" in tokens):
        return "Voz principal"
    return None


def project_vocal_files(project):
    if not project:return []
    from task_staging import inside
    root=Path(project).resolve()
    # Compatibilidad con proyectos nuevos y anteriores. No escanear fuentes
    # ajenas al proyecto ni carpetas globales /tareas_temporales de otro.
    bases=(root/"temporales"/"voces",root/"temporales"/"vocal",
           root/"temporales"/"afinacion_vocal",
           root/"voces",root/"afinacion_vocal",root/"vocal",
           root/"backup"/"vocal",root/"backup"/"voces",
           root/"backup"/"afinacion_vocal")
    result=[]
    for base in bases:
        if not base.is_dir() or base.is_symlink():continue
        for p in base.rglob("*"):
            if (p.is_file() and not p.is_symlink() and p.suffix.lower() in AUDIO
                    and inside(p,base) and vocal_role(p) is not None):
                result.append(p.resolve())
    return sorted(set(result),key=lambda p:(p.stat().st_mtime_ns,str(p)))


def latest_vocal_stems(project):
    result={}
    for p in project_vocal_files(project):
        role=vocal_role(p)
        if role:result[role]=p
    return result
