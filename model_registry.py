"""Catálogo de modelos, compatibilidad y gestión segura de archivos.

Nunca borra modelos preexistentes ni pesos descargados por terceros.
Las eliminaciones de modelos administrados se trasladan a papelera local.
No anuncia licencias ni clasificaciones de calidad no verificadas.
"""
from __future__ import annotations
import json,re,os,time,shutil
from urllib.parse import urlparse,unquote
from pathlib import Path
from studio_paths import workspace_root

ROOT=workspace_root(__file__)
HOME=ROOT/"modelos"
CACHE=HOME/"catalogo_audio_separator.json"
MANIFEST=HOME/"modelos_administrados.json"
ACTIVE=HOME/"modelos_activos.json"
ENGINE=ROOT/"entorno_ia"/"bin"/"audio-separator"
GROUPS=("VR","MDX","MDXC","Demucs")
AUDIO_LABELS={"vocals":"Voces","instrumental":"Instrumental",
    "drums":"Batería","bass":"Bajo","guitar":"Guitarra",
    "piano":"Piano","other":"Otros","kick":"Bombo",
    "snare":"Caja","toms":"Toms","hh":"Charles",
    "ride":"Ride","crash":"Crash"}
DRUM_STEMS={"kick","snare","toms","hh","ride","crash"}
ALLOWED_SUFFIX={".ckpt",".onnx",".yaml",".yml",".pth",".th",".json"}
BUILTIN={
 "MDXC":[("MDX23C DrumSep · 6 pistas","MDX23C-DrumSep-aufr33-jarredou.ckpt",
     ["kick","snare","toms","hh","ride","crash"],
     ["MDX23C-DrumSep-aufr33-jarredou.ckpt","config_drumsep_mdx23c.yaml"])],
 "Demucs":[("Demucs 4 stems","htdemucs.yaml",
     ["vocals","drums","bass","other"],["htdemucs.yaml"]),
     ("Demucs 6 stems","htdemucs_6s.yaml",
     ["vocals","drums","bass","guitar","piano","other"],["htdemucs_6s.yaml"])],
 "MDX":[("UVR MDX instrumental","UVR-MDX-NET-Inst_HQ_3.onnx",
     ["instrumental","vocals"],["UVR-MDX-NET-Inst_HQ_3.onnx"])]
}

def read_json(path,default):
    try:
        obj=json.loads(Path(path).read_text(encoding="utf-8"))
        return obj if isinstance(obj,type(default)) else default
    except (ValueError,OSError,TypeError):
        return default

def save_json(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    part=p.with_suffix(p.suffix+".tmp")
    part.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(part,p)

def safe_name(name):
    if not isinstance(name,str) or len(name)>180 or not name:
        return False
    if name!=Path(name).name or name in {".",".."}:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.()\- +]*",name))

def catalog_file_name(value):
    if safe_name(value):
        return value
    # Demucs publishes direct file URLs in its catalog; only accept exact
    # HTTPS assets from the official Demucs/UVR endpoints advertised by
    # audio-separator, never arbitrary hosts.
    if not isinstance(value,str) or len(value)>600:return None
    parsed=urlparse(value)
    if parsed.scheme!="https" or parsed.netloc not in (
        "dl.fbaipublicfiles.com","github.com"):return None
    name=unquote(Path(parsed.path).name)
    return name if safe_name(name) and not parsed.query else None

def records_from_json(raw):
    if not isinstance(raw,dict):raise ValueError("Catálogo incorrecto")
    out={}
    for arch,items in raw.items():
        if arch not in GROUPS or not isinstance(items,dict):continue
        for title,data in items.items():
            if not isinstance(data,dict):continue
            filename=data.get("filename")
            files=data.get("download_files") or [filename]
            if not safe_name(filename) or not isinstance(files,list) or len(files)>12:
                continue
            files=[catalog_file_name(f) for f in files]
            if not all(f and Path(f).suffix.lower() in ALLOWED_SUFFIX
                       for f in files):continue
            stems=data.get("stems") or []
            if not isinstance(stems,list):continue
            stemlist=[str(v).strip().lower() for v in stems][:15]
            if not all(re.fullmatch(r"[a-z_ -]{1,30}",v) for v in stemlist):
                continue
            scores=data.get("scores") if isinstance(data.get("scores"),dict) else {}
            out[filename]={
                "name":str(title)[:130],"filename":filename,
                "files":files,"architecture":arch,"stems":stemlist,
                "scores":scores,"target":str(data.get("target_stem") or ""),
                "license":"Consulta las condiciones del autor; no verificada."
            }
    return out

def fallback():
    data={}
    for a,entries in BUILTIN.items():
        data[a]={name:{"filename":f,"stems":stems,"download_files":files}
                 for name,f,stems,files in entries}
    return records_from_json(data)

def catalog():
    records=fallback()
    data=read_json(CACHE,{})
    try:records.update(records_from_json(data))
    except ValueError:pass
    return records

def record_for(filename):
    return catalog().get(str(filename))

def is_drum(record):
    return set(record.get("stems") or [])==DRUM_STEMS

def is_general(record):
    stems=set(record.get("stems") or [])
    return (bool(stems) and
        (stems.issubset({"vocals","instrumental","other"}) or
         stems=={"drums","no drums"} or
         stems.issubset({"vocals","drums","bass","other","guitar","piano"})
         and ("drums" in stems or "vocals" in stems)))
def compat(record):
    possibilities=[]
    if is_general(record):possibilities.append("Separación de audio")
    if is_drum(record):possibilities.append("Desglose de batería")
    return possibilities

def filename_path(record):
    # Los modelos DrumSep históricos se guardan en modelos/bateria;
    # los otros en modelos, sin moverlos.
    if is_drum(record):
        return HOME/"bateria"
    return HOME

def locations(record):
    default=filename_path(record)
    return (default,HOME) if default!=HOME else (default,)

def existing_files(record):
    files=[]
    for fname in record["files"]:
        match=next((folder/fname for folder in locations(record)
                    if (folder/fname).is_file() and (folder/fname).stat().st_size>0),None)
        files.append(match)
    return files

def installed(record):
    return all(existing_files(record))

def locate(record):
    paths=existing_files(record)
    if all(paths):
        parents={p.parent for p in paths}
        if len(parents)==1:return next(iter(parents))
    return filename_path(record)

def size(record):
    return sum(p.stat().st_size for p in existing_files(record) if p)

def managed_manifest():
    return read_json(MANIFEST,{})

def model_is_managed(record):
    entry=managed_manifest().get(record["filename"])
    return isinstance(entry,dict) and entry.get("files")==record["files"]

def model_active():
    d=read_json(ACTIVE,{})
    return {k:v for k,v in d.items() if k in ("general","drum") and isinstance(v,str)}

def set_active(kind,filename):
    if kind not in ("general","drum"):raise ValueError("Destino desconocido")
    r=record_for(filename)
    if r is None or not installed(r):raise ValueError("El modelo no está completo")
    if kind=="general" and not is_general(r):raise ValueError("Stems incompatibles con separación general")
    if kind=="drum" and not is_drum(r):raise ValueError("No proporciona seis componentes de batería")
    active=model_active();active[kind]=filename;save_json(ACTIVE,active)

def mark_managed(record):
    data=managed_manifest()
    data[record["filename"]]={"files":record["files"],
        "directory":str(locate(record)),"installed_at":int(time.time())}
    save_json(MANIFEST,data)

def deactivate(filename):
    current=model_active()
    for k,v in list(current.items()):
        if v==filename:current.pop(k)
    save_json(ACTIVE,current)

def remove_managed(record):
    """Solo mueve ficheros registrados a papelera. No elimina definitivamente."""
    if not model_is_managed(record):raise ValueError(
        "Modelo preexistente: protegido. Solo se pueden retirar descargas del gestor.")
    if not installed(record):raise ValueError("Faltan archivos: revisa manualmente")
    entry=managed_manifest().get(record["filename"],{})
    folder=Path(entry.get("directory",""))
    if folder not in (HOME,HOME/"bateria"):raise ValueError("Ubicación de modelo protegida")
    active=model_active()
    if record["filename"] in active.values():
        raise ValueError("Desactiva el modelo antes de retirarlo")
    trash=HOME/".papelera_stemmidi"/(re.sub(r"[^A-Za-z0-9_-]+","_",record["filename"])+"_"+str(int(time.time())))
    trash.mkdir(parents=True,exist_ok=False)
    moved=[]
    try:
        for name in record["files"]:
            file=folder/name
            if not file.is_file() or file.is_symlink():raise ValueError("Archivo protegido o no disponible")
            file.rename(trash/name)
            moved.append((file,trash/name))
    except Exception:
        for dest,src in reversed(moved):
            src.rename(dest)
        raise
    data=managed_manifest();data.pop(record["filename"],None);save_json(MANIFEST,data)
    return trash

def quality_label(record):
    # SDR por fuente no permite comparaciones entre modelos/datasets.
    scores=record.get("scores") or {}
    for key,metrics in scores.items():
        if isinstance(metrics,dict) and isinstance(metrics.get("SDR"),(int,float)):
            return f"SDR publicado: {metrics['SDR']:.2f} dB ({key}; no comparable)"
    return "Sin puntuación comparable publicada"

def cache_catalog_text(text):
    start=text.find("{")
    end=text.rfind("}")
    if start<0 or end<=start:raise ValueError("No se recibió JSON del motor")
    obj=json.loads(text[start:end+1])
    available=records_from_json(obj)
    if len(available)<10:raise ValueError("Catálogo del motor demasiado pequeño")
    save_json(CACHE,obj)
    return available
