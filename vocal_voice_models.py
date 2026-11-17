"""Biblioteca local de modelos de conversión vocal.

La importación NUNCA ejecuta pesos de terceros. Un modelo importado no se
anuncia como utilizable hasta contar con un motor compatible verificado.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from studio_paths import workspace_root

ROOT=workspace_root(__file__)/"modelos"/"clonacion_vocal"
CATALOG=ROOT/"catalogo.json"
WEIGHTS={".pth",".onnx",".safetensors",".pt"}
AUXILIARY={".index"}
MAX_SIZE=8*1024**3

def safe_filename(value):
    return bool(isinstance(value,str) and
        value==Path(value).name and len(value)<=180 and
        re.fullmatch(r"[^\x00-\x1f/\\]+",value) and value not in (".",".."))

def read_catalog():
    try:
        obj=json.loads(CATALOG.read_text(encoding="utf8"))
    except (OSError,TypeError,ValueError):
        return []
    if not isinstance(obj,list):
        return []
    valid=[]
    for entry in obj:
        if not isinstance(entry,dict):continue
        ident=entry.get("id")
        filenames=entry.get("files",[])
        if (not isinstance(ident,str) or
            not re.fullmatch(r"[a-f0-9]{16}",ident) or
            not isinstance(filenames,list) or
            not filenames or not all(safe_filename(f) for f in filenames)):
            continue
        folder=ROOT/ident
        if folder.is_dir() and all((folder/f).is_file() for f in filenames):
            valid.append(entry)
    return valid

def _validate(path):
    p=Path(path).expanduser()
    if p.is_symlink() or not p.is_file():
        raise ValueError("Selecciona un archivo local ordinario, no un enlace.")
    if p.suffix.lower() not in WEIGHTS|AUXILIARY:
        raise ValueError("Formato no admitido: "+p.suffix)
    if not safe_filename(p.name):
        raise ValueError("Nombre de modelo no permitido.")
    size=p.stat().st_size
    if size<1024 or size>MAX_SIZE:
        raise ValueError("Archivo de modelo incompleto o demasiado grande.")
    return p

def _digest(path):
    hasher=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            hasher.update(block)
    return hasher.hexdigest()

def import_models(paths):
    """Importa varios modelos sin modificar originales ni deserializar .pth/.pt.

    Un .index con el mismo nombre base se añade solo cuando existe y se
    selecciona. Los pesos incompatibles quedan registrados, NO ejecutables.
    """
    files=[_validate(p) for p in paths]
    if not files or len(files)>32:
        raise ValueError("Selecciona entre 1 y 32 archivos de modelos.")
    weights=[p for p in files if p.suffix.lower() in WEIGHTS]
    if not weights:
        raise ValueError("Selecciona al menos un archivo .onnx, .pth, .pt o .safetensors.")
    records=read_catalog()
    known={x["id"] for x in records}
    added=[]
    ROOT.mkdir(parents=True,exist_ok=True)
    for weight in weights:
        identity=_digest(weight)[:16]
        if identity in known:continue
        companions=[p for p in files if p.suffix.lower()==".index"
                    and p.stem.lower().split(".")[0]==weight.stem.lower().split(".")[0]]
        selected=[weight]+companions[:1]
        model_dir=ROOT/identity
        if model_dir.exists():
            raise ValueError("Existe un directorio de modelo sin registrar: "+identity)
        # Modelo inerte: solo copia. Nunca torch.load, pickle, exec o scripts.
        with tempfile.TemporaryDirectory(prefix=".modelo_",dir=ROOT) as temporary:
            stage=Path(temporary)
            for p in selected:
                shutil.copyfile(p,stage/p.name)
                if (stage/p.name).stat().st_size!=p.stat().st_size:
                    raise OSError("Copia incompleta: "+p.name)
            stage.rename(model_dir)
        entry={
            "id":identity,"name":weight.stem,"type":weight.suffix.lower(),
            "files":[p.name for p in selected],
            "status":"Importado; motor de conversión neuronal no instalado",
            "executable":False
        }
        records.append(entry)
        known.add(identity)
        added.append(entry)
    if added:
        _save(records)
    return added

def _save(records):
    ROOT.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf8",
            prefix=".catalogo_",suffix=".tmp",dir=ROOT,delete=False) as tmp:
        tmp.write(json.dumps(records,ensure_ascii=False,indent=2))
        name=tmp.name
    os.replace(name,CATALOG)

def remove_model(identity):
    records=read_catalog()
    target=next((r for r in records if r["id"]==identity),None)
    if target is None:return False
    folder=ROOT/identity
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Carpeta de modelo inválida")
    # Solo se borra la copia gestionada, nunca la fuente externa.
    for f in target["files"]:
        (folder/f).unlink()
    folder.rmdir()
    _save([r for r in records if r["id"]!=identity])
    return True
