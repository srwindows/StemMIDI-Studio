"""Contrato de estructura única de un proyecto StemMIDI Studio.

No migrar ni borrar proyectos existentes. En proyectos nuevos todos
los resultados se guardan en una carpeta fija por módulo; backup solo
contiene copias recuperables, temporales contiene trabajo sin aprobar.
"""
from __future__ import annotations
from pathlib import Path
import os,re,unicodedata

LAYOUT_VERSION=4
MODULES={
    "grabaciones":"grabaciones",
    "monitor":"grabaciones",
    "separaciones":"stems",
    "stems":"stems",
    "midi":"audio_a_midi",
    "audio_a_midi":"audio_a_midi",
    "bateria":"bateria",
    "vocal":"afinacion_vocal",
    "afinacion_vocal":"afinacion_vocal",
    "mezclador":"mezclador",
    "mezclas":"mezclador",
    "piano_roll":"piano_roll",
    "resultados":"resultados",
}
DIRECTORIES=tuple(dict.fromkeys(MODULES.values()))+("temporales","backup")
REQUIRED=("stems","audio_a_midi","afinacion_vocal","resultados")

def layout_active(project):
    if not project:return False
    root=Path(project).resolve()
    if not root.is_dir() or not all((root/name).is_dir() for name in REQUIRED):
        return False
    # Evitar reclasificar proyectos antiguos que casualmente contengan
    # carpetas llamadas stems/resultados. Su manifiesto es la autoridad.
    manifests=list(root.glob("*.stemstudio.json"))
    if not manifests:return True  # Etapa anterior al primer persist().
    import json
    for manifest in manifests:
        try:
            data=json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(data,dict) and int(data.get("project_layout_version",0))>=LAYOUT_VERSION:
                return True
        except (OSError,ValueError,TypeError):pass
    return False

def install(project):
    """Crear una sola vez subcarpetas fijas, sin tocar medios ya existentes."""
    root=Path(project).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    for name in DIRECTORIES:
        child=root/name
        if child.is_symlink():
            raise ValueError("Carpeta del proyecto es un enlace: "+str(child))
        child.mkdir(exist_ok=True)
    return root

def module_dir(project,kind):
    """Carpeta definitiva: nunca anidar un nuevo nombre de proyecto."""
    root=Path(project).expanduser().resolve()
    if not layout_active(root):
        if kind=="grabaciones":return root/"grabaciones"
        return root/"backup"/("mezclas" if kind=="mezclas" else kind)
    name=MODULES.get(kind)
    if name is None:raise ValueError("Módulo sin destino definido: "+str(kind))
    return root/name

def project_folder_name(name):
    """Nombre visible exacto en Unicode, con limpieza SOLO de caracteres ilegales.

    Debian, macOS y Windows permiten tildes y ñ; no hay motivo para
    quitar «í» al crear la carpeta «mío». NO renombra proyectos antiguos.
    """
    raw=unicodedata.normalize("NFC",str(name).strip())
    if raw in ("",".",".."):
        raise ValueError("Introduce un nombre de proyecto válido")
    clean=re.sub(r'[<>:"/\\|?*\x00-\x1f]',"_",raw).rstrip(" .")[:74].strip(" .")
    if clean.upper().split(".")[0] in {
        "CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),
        *(f"LPT{i}" for i in range(1,10))}:
        clean="_"+clean
    if not clean:raise ValueError("El nombre contiene solo caracteres no admitidos")
    return clean


def normalize_location(parent,name,slug):
    """Compatibilidad si el usuario selecciona el directorio llamado como el proyecto.

    Ejemplos:
      mía + mío -> mía/mio
      mía/mio + mío (directorio vacío elegido) -> mía/mio, no mio/mio
      mía/mio + mío con archivos ajenos -> rechazar, nunca pisarlos.
    """
    base=Path(parent).expanduser().resolve()
    if base.name.casefold()==slug.casefold():
        # Si el usuario selecciona una carpeta con el mismo nombre,
        # NUNCA generamos «mío/mío», esté vacía o contenga datos.
        # create_named_project y clone_project verificarán luego que
        # esté vacía y bloquearán cualquier sobrescritura.
        return base
    return base/slug

def is_project_path(path,project):
    path=Path(path).expanduser().resolve()
    base=Path(project).expanduser().resolve()
    return path==base or base in path.parents

def save_folder(project,kind,destination):
    """Un selector dentro del proyecto no debe crear subcarpetas arbitrarias.

    Fuera del proyecto, el usuario puede exportar libremente a otra carpeta.
    """
    target=Path(destination).expanduser().resolve()
    root=Path(project).expanduser().resolve()
    if layout_active(root) and is_project_path(target,root):
        return module_dir(root,kind)
    return target
