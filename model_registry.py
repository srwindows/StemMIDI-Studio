"""Catálogo de modelos, compatibilidad y gestión segura de archivos.

Nunca borra modelos preexistentes ni pesos descargados por terceros.
Las eliminaciones de modelos administrados se trasladan a papelera local.
No anuncia licencias ni clasificaciones de calidad no verificadas.
"""
from __future__ import annotations
import json,re,os,time,shutil
from urllib.parse import urlparse,unquote
from pathlib import Path
from studio_paths import workspace_root,ia_executable

ROOT=workspace_root(__file__)
HOME=ROOT/"modelos"
CACHE=HOME/"catalogo_audio_separator.json"
MANIFEST=HOME/"modelos_administrados.json"
ACTIVE=HOME/"modelos_activos.json"
ENGINE=ia_executable(__file__)
GROUPS=("VR","MDX","MDXC","Demucs")
AUDIO_LABELS={"vocals":"Voces","instrumental":"Instrumental",
    "drums":"Batería","bass":"Bajo","guitar":"Guitarra",
    "piano":"Piano","other":"Otros","kick":"Bombo",
    "snare":"Caja","toms":"Toms","hh":"Charles",
    "ride":"Ride","crash":"Crash"}
DRUM_STEMS={"kick","snare","toms","hh","ride","crash"}
ALLOWED_SUFFIX={".ckpt",".onnx",".yaml",".yml",".pth",".th",".json"}
# Archivos exactos exigidos por audio-separator 0.22 (no basta un YAML).
BUILTIN={
 "MDXC":[
  ("MDX23C DrumSep · 6 pistas (motor MIT)",
   "aufr33-jarredou_DrumSep_model_mdx23c_ep_141_sdr_10.8059.ckpt",
   ["kick","snare","toms","hh","ride","crash"],
   ["aufr33-jarredou_DrumSep_model_mdx23c_ep_141_sdr_10.8059.ckpt",
    "aufr33-jarredou_DrumSep_model_mdx23c_ep_141_sdr_10.8059.yaml"]),
  ("MelBand RoFormer · Voces e instrumental",
   "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
   ["vocals","instrumental"],
   ["model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
    "model_mel_band_roformer_ep_3005_sdr_11.4360.yaml"]),
  ("MelBand RoFormer · Karaoke solista/coros",
   "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
   ["vocals","instrumental"],
   ["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
    "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml"]),
 ],
 "Demucs":[
  ("Demucs 4 stems","htdemucs.yaml",
   ["vocals","drums","bass","other"],
   ["htdemucs.yaml","955717e8-8726e21a.th"]),
  ("Demucs 6 stems","htdemucs_6s.yaml",
   ["vocals","drums","bass","guitar","piano","other"],
   ["htdemucs_6s.yaml","5c90dfd2-34c22ccb.th"]),
  ("Demucs FT 4 stems","htdemucs_ft.yaml",
   ["vocals","drums","bass","other"],
   ["htdemucs_ft.yaml","04573f0d-f3cf25b2.th",
    "92cfc3b6-ef3bcb9c.th","d12395a8-e57c48e6.th",
    "f7e0c4bc-ba3fe64a.th"]),
 ],
 "MDX":[
  ("UVR MDX instrumental","UVR-MDX-NET-Inst_HQ_3.onnx",
   ["vocals","instrumental"],["UVR-MDX-NET-Inst_HQ_3.onnx"]),
 ],
}

# La IA vocal secundaria guarda sus pesos en /modelos/voces, no en
# /modelos. El gestor debe reconocerlos como instalados allí.
VOCAL_MODEL_FILES={
    "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
    "bs_roformer_male_female_by_aufr33_sdr_7.2889.ckpt",
    "mel_band_roformer_karaoke_gabox.ckpt",
}

KNOWN_GENERAL_STEMS={
 entry[1]:entry[2] for arch,entries in BUILTIN.items()
 for entry in entries if arch!="MDXC" or "DrumSep" not in entry[1]
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
    """Acepta catálogo enriquecido y catálogo REAL de audio-separator 0.22.

    El comando `audio-separator -l` devuelve grupos de modelos en los que
    los datos son cadenas (MDX, VR) o mapas peso→config (MDXC/Demucs).
    La versión antigua del gestor los descartaba TODOS por falta de
    `filename`, anunciando erróneamente que no había catálogo.
    """
    if not isinstance(raw,dict):raise ValueError("Catálogo incorrecto")
    out={}
    for arch,items in raw.items():
        if arch not in GROUPS or not isinstance(items,dict):continue
        for title,data in items.items():
            if isinstance(data,str):
                filename=data
                files=[filename]
                stems=KNOWN_GENERAL_STEMS.get(filename,[])
                scores={}
                target=""
            elif isinstance(data,dict) and "filename" in data:
                filename=data.get("filename")
                files=data.get("download_files") or [filename]
                stems=data.get("stems") or []
                scores=data.get("scores") if isinstance(data.get("scores"),dict) else {}
                target=str(data.get("target_stem") or "")
            elif isinstance(data,dict) and data:
                # Demucs descarga los .th además del .yaml; MDXC precisa
                # tanto su .ckpt como la configuración indicada en el valor.
                if arch=="Demucs":
                    filename=next((k for k in data if k.endswith((".yaml",".yml"))),None)
                    files=list(data)
                else:
                    filename=next((k for k in data if k.endswith((".ckpt",".onnx",".pth"))),None)
                    files=([filename] + [v for k,v in data.items()
                                      if k==filename and isinstance(v,str)])
                stems=KNOWN_GENERAL_STEMS.get(filename,[])
                scores={}
                target=""
            else:
                continue
            if not safe_name(filename) or not isinstance(files,list) or len(files)>12:
                continue
            files=[catalog_file_name(f) for f in files]
            if not files or not all(f and Path(f).suffix.lower() in ALLOWED_SUFFIX
                                    for f in files):continue
            files=list(dict.fromkeys(files))
            if not isinstance(stems,list):continue
            stemlist=[str(v).strip().lower() for v in stems][:15]
            if not all(re.fullmatch(r"[a-z_ -]{1,30}",v) for v in stemlist):
                continue
            out[filename]={
                "name":str(title)[:130],"filename":filename,
                "files":files,"architecture":arch,"stems":stemlist,
                "scores":scores,"target":target,
                "license":"Consulta las condiciones del autor; no verificada."
            }
    return out


def fallback():
    data={}
    for a,entries in BUILTIN.items():
        data[a]={name:{"filename":f,"stems":stems,"download_files":files}
                 for name,f,stems,files in entries}
    return records_from_json(data)

_catalog_cache_key=None
_catalog_cache_records=None

def catalog():
    """Cache invalidable por modificación real del catálogo en disco.

    Con miles de modelos revalidar sus nombres en cada repintado era caro
    y se multiplicaba durante la apertura del proyecto. No cachear para
    siempre: añadir/actualizar un modelo invalida por stat del JSON.
    """
    global _catalog_cache_key,_catalog_cache_records
    try:
        stat=CACHE.stat()
        key=(stat.st_dev,stat.st_ino,stat.st_size,
             stat.st_mtime_ns,stat.st_ctime_ns)
    except OSError:key=None
    if _catalog_cache_records is None or key!=_catalog_cache_key:
        records=fallback()
        data=read_json(CACHE,{})
        try:records.update(records_from_json(data))
        except ValueError:pass
        _catalog_cache_key=key
        _catalog_cache_records=records
    # El catálogo remoto se puede actualizar sin borrar modelos externos.
    from copy import deepcopy
    result=deepcopy(_catalog_cache_records)
    try:
        from external_model_import import records
        for filename,entry in records().items():
            if not entry.get('catalog_known'):
                result[filename]={
                  'name':entry.get('display',filename),'filename':filename,
                  'files':entry['files'],'architecture':entry['family'],
                  'stems':entry['stems'],'scores':{},'target':'',
                  'license':'Modelo importado por el usuario; comprobar licencia del autor.',
                  'external':True,'role':entry['role']}
            elif filename in result:
                result[filename]['external']=True
                result[filename]['role']=entry['role']
    except (ValueError,TypeError,OSError,KeyError):pass
    # Modelos MDX23C importados por el usuario: solo seis stems reales y
    # tras pasar una carga completa en el trabajador de IA.
    try:
        from drum_custom_models import list_models,ready
        for filename,entry in list_models().items():
            if ready(filename):
                result[filename]={
                    'name':entry.get('display',filename),'filename':filename,
                    'files':[filename,entry['config']],
                    'architecture':'MDX23C','stems':entry['stems'],
                    'scores':{},'target':'','role':'drum','external':True,
                    'license':'Modelo añadido por el usuario. Comprobar licencia de origen.'}
    except (ValueError,TypeError,OSError,KeyError):pass
    return result

def record_for(filename):
    return catalog().get(str(filename))

def is_drum(record):
    return set(record.get("stems") or [])==DRUM_STEMS

def is_general(record):
    if record.get('external') and record.get('role')=='vocal':return False
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
    if record["filename"] in VOCAL_MODEL_FILES or record.get('role')=='vocal':
        possibilities.append("Voces · solista/coros")
    return possibilities

def filename_path(record):
    # Conservar los pesos en el módulo que realmente los usa.
    if record.get('external') and record.get('role')=='vocal':return HOME/'voces'
    if is_drum(record):return HOME/"bateria"
    if record["filename"] in VOCAL_MODEL_FILES:return HOME/"voces"
    return HOME

def locations(record):
    default=filename_path(record)
    return (default,HOME) if default!=HOME else (default,)

def existing_files(record):
    files=[]
    for fname in record["files"]:
        # Evitar falsos positivos por descargas interrumpidas: un archivo de
        # pesos de unas decenas de bytes no constituye un modelo instalado.
        minimum=1024 if Path(fname).suffix.lower() in (
            ".ckpt",".pth",".th",".onnx") else 1
        match=next((folder/fname for folder in locations(record)
                    if (folder/fname).is_file() and
                    (folder/fname).stat().st_size>=minimum),None)
        files.append(match)
    return files

def engine_for(record):
    """Motor de instalación según modelo; MDXNet sirve seis pistas reales."""
    name=str(record.get("filename","")) if record else ""
    if name=="aufr33-jarredou_DrumSep_model_mdx23c_ep_141_sdr_10.8059.ckpt" or record.get('role')=='drum':
        from studio_paths import ia_python
        native=ia_python(__file__).parent/"drum-separator"
        if not native.is_file():
            native=Path(__file__).resolve().parent.parent/"portable_resources"/"ia_runtime"/"bin"/"drum-separator"
        return native
    return ENGINE


def installed(record):
    return bool(record) and all(existing_files(record))

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
