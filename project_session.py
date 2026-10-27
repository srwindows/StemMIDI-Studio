"""Guardado autocontenido de proyectos, copias al abrir y recuperación.

No usa directorios fuera del proyecto salvo para leer entradas elegidas.
"""
from __future__ import annotations
import hashlib,json,os,shutil,tempfile,zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

MEDIA={".wav",".wave",".flac",".mp3",".ogg",".opus",".m4a",".aac",
       ".aif",".aiff",".wma",".mid",".midi",".kar",".mp4",".mov",".avi",
       ".mpg",".mpeg"}

def inside(path,root):
    p=Path(path).resolve();r=Path(root).resolve()
    return p==r or r in p.parents

def _safe_files(root):
    root=Path(root).resolve()
    assert root.is_dir() and not root.is_symlink()
    for item in root.rglob("*"):
        if "backup" in item.relative_to(root).parts[:1]:continue
        if item.is_symlink():
            raise ValueError("Enlace simbólico no admitido en la copia: "+str(item))
        if item.is_file():
            if not inside(item,root):raise ValueError("Archivo externo en proyecto")
            yield item

def snapshot_on_open(root):
    """ZIP de todos los ficheros del proyecto excepto backup, antes de editar.

    Si falla por falta de espacio no permite abrir el proyecto a medio guardar.
    """
    root=Path(root).resolve()
    backup=root/"backup"
    if backup.is_symlink():raise ValueError("Backup no puede ser un enlace")
    backup.mkdir(exist_ok=True)
    now=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    final=backup/("Antes_de_abrir_"+now+".zip")
    fd,temp=tempfile.mkstemp(prefix=".stem_snapshot_",suffix=".tmp",dir=backup)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp,"w",compression=zipfile.ZIP_STORED,
                             allowZip64=True) as pack:
            for path in _safe_files(root):
                pack.write(path,path.relative_to(root).as_posix())
        with zipfile.ZipFile(temp) as pack:
            assert pack.testzip() is None
        os.replace(temp,final)
        return final
    finally:
        Path(temp).unlink(missing_ok=True)

def restore_snapshot(root,archive):
    root=Path(root).resolve()
    source=Path(archive).resolve()
    if not inside(source,root/"backup") or source.suffix.lower()!=".zip":
        raise ValueError("La copia debe pertenecer al backup del proyecto")
    with zipfile.ZipFile(source) as z:
        entries=z.infolist()
        for entry in entries:
            name=Path(entry.filename)
            if (name.is_absolute() or ".." in name.parts or
                entry.filename.startswith("backup/") or
                (entry.external_attr>>16)&0o170000==0o120000):
                raise ValueError("Ruta no segura en el backup")
            target=root/name
            if not inside(target,root) or target.is_symlink():
                raise ValueError("Destino fuera del proyecto: "+str(target))
        if z.testzip() is not None:raise ValueError("El ZIP contiene datos corruptos")
        # Sin borrar archivos posteriores: reversión no destructiva.
        restored=[]
        for entry in entries:
            if entry.is_dir():continue
            target=root/entry.filename
            target.parent.mkdir(parents=True,exist_ok=True)
            fd,temp=tempfile.mkstemp(prefix=".stem_restore_",dir=target.parent)
            try:
                with os.fdopen(fd,"wb") as out, z.open(entry) as stream:
                    shutil.copyfileobj(stream,out)
                    out.flush();os.fsync(out.fileno())
                os.replace(temp,target)
                restored.append(target)
            finally:Path(temp).unlink(missing_ok=True)
    return restored

def _copy_external(path,root):
    path=Path(path).expanduser().resolve()
    root=Path(root).resolve()
    if inside(path,root):return str(path)
    if not path.is_file():return str(path)
    if path.suffix.lower() not in MEDIA:return str(path)
    # Guardar el origen sin modificarlo en UNA subcarpeta del área temporal.
    destdir=root/"temporales"/"importados"
    destdir.mkdir(parents=True,exist_ok=True)
    signature=hashlib.sha256((str(path)+"|"+str(path.stat().st_size)+
                               "|"+str(path.stat().st_mtime_ns)).encode()).hexdigest()[:16]
    new=destdir/(signature+"_"+path.name)
    if not new.is_file() or new.stat().st_size!=path.stat().st_size:
        fd,temp=tempfile.mkstemp(prefix=".stem_import_",dir=destdir)
        try:
            with os.fdopen(fd,"wb") as out,path.open("rb") as source:
                shutil.copyfileobj(source,out,1024*1024)
                out.flush();os.fsync(out.fileno())
            if Path(temp).stat().st_size!=path.stat().st_size:
                raise OSError("Origen incompleto: "+str(path))
            os.replace(temp,new)
        finally:Path(temp).unlink(missing_ok=True)
    return str(new)

def _copy_external_folder(folder,root):
    """Incluir pistas elegidas mediante «Convertir carpeta» dentro de temporales."""
    folder=Path(folder).expanduser().resolve()
    root=Path(root).resolve()
    if inside(folder,root):return str(folder)
    if not folder.is_dir():return str(folder)
    signature=hashlib.sha256(str(folder).encode()).hexdigest()[:12]
    destination=root/"temporales"/"importados"/("carpeta_midi_"+signature)
    destination.mkdir(parents=True,exist_ok=True)
    for source in folder.iterdir():
        if source.is_symlink():
            raise ValueError("Pista simbólica no permitida: "+str(source))
        if source.is_file() and source.suffix.lower() in MEDIA:
            dest=destination/source.name
            if not dest.is_file() or dest.stat().st_size!=source.stat().st_size:
                fd,temp=tempfile.mkstemp(prefix=".stem_folder_",dir=destination)
                try:
                    with os.fdopen(fd,"wb") as output,source.open("rb") as original:
                        shutil.copyfileobj(original,output,1024*1024)
                        output.flush();os.fsync(output.fileno())
                    os.replace(temp,dest)
                finally:Path(temp).unlink(missing_ok=True)
    return str(destination)


def prepare_payload(root,payload):
    """Captura ajustes y medios externos, SIN añadir carpetas al nivel raíz."""
    root=Path(root).resolve()
    result=dict(payload)
    paths=("source_recording","source_separation","source_midi","selected_midi",
           "drum_input","vocal_input","midi_editor_file","vocal_reference",
           "recording_lab_original","recording_lab_processed")
    for key in paths:
        value=result.get(key)
        if isinstance(value,str) and value.strip():
            result[key]=_copy_external(value,root)
    if result.get("midi_use_folder") and result.get("midi_source_folder"):
        result["midi_source_folder"]=_copy_external_folder(
            result["midi_source_folder"],root)
    if isinstance(result.get("recordings"),list):
        result["recordings"]=[_copy_external(v,root) if isinstance(v,str) else v
                              for v in result["recordings"]]
    if isinstance(result.get("mixer_sources"),list):
        result["mixer_sources"]=[_copy_external(v,root) if isinstance(v,str) else v
                              for v in result["mixer_sources"]]
    result["project_files"]=[path.relative_to(root).as_posix()
                             for path in _safe_files(root)]
    result["notice"]=("Proyecto autocontenido: medios originales importados "
                       "en temporales/importados; resultados en sus tareas.")
    result["version"]=3
    return result

def rebase_json(obj,original,clone):
    original=str(Path(original).resolve())
    clone=str(Path(clone).resolve())
    if isinstance(obj,str):
        return clone+obj[len(original):] if (
            obj==original or obj.startswith(original+os.sep)) else obj
    if isinstance(obj,list):return [rebase_json(x,original,clone) for x in obj]
    if isinstance(obj,dict):return {k:rebase_json(v,original,clone)
                                    for k,v in obj.items()}
    return obj

def clone_project(root,new_parent,new_name):
    """Guardar como: nuevo proyecto independiente, copiado íntegramente."""
    from project_flow import slug_name,atomic_json
    from project_layout import normalize_location,project_folder_name
    root=Path(root).resolve();new_parent=Path(new_parent).expanduser().resolve()
    component=project_folder_name(new_name)
    new_dir=normalize_location(new_parent,new_name,component)
    use_selected_empty=new_dir==new_parent
    if new_dir.exists() and (
            not use_selected_empty or not new_dir.is_dir() or any(new_dir.iterdir())):
        raise FileExistsError("El proyecto destino ya contiene archivos: "+str(new_dir))
    if not new_parent.is_dir() or inside(new_dir,root):
        raise ValueError("El nuevo proyecto debe estar fuera del proyecto de origen")
    staging=(new_parent.parent if use_selected_empty else new_parent)/(
        ".stem_copy_"+uuid4().hex)
    # Jamás seguir enlaces simbólicos hacia archivos de otros proyectos.
    for item in root.rglob("*"):
        if item.is_symlink():
            raise ValueError("Guardar como no admite enlaces externos: "+str(item))
    copied=False
    try:
        shutil.copytree(root,staging,symlinks=False)
        # Reescribir todos los manifiestos JSON que contienen rutas absolutas
        # a los medios duplicados, sin cambiar notas, muestras ni archivos.
        for f in staging.rglob("*.json"):
            if "backup" in f.relative_to(staging).parts[:1]:continue
            try:document=json.loads(f.read_text(encoding="utf-8"))
            except (OSError,UnicodeError,ValueError):continue
            changed=rebase_json(document,root,new_dir)
            if isinstance(changed,dict):
                if changed.get("application")=="StemMIDI Studio":
                    changed["project_name"]=str(new_name)
                    changed["project_id"]=uuid4().hex
                    changed["project_dir"]=str(new_dir)
                atomic_json(f,changed)
        # Mantener SOLO un manifiesto principal de proyecto.
        manifests=[f for f in staging.glob("*.stemstudio.json")]
        if len(manifests)!=1:
            raise ValueError("El origen no contiene exactamente un manifiesto")
        new_manifest=staging/(component+".stemstudio.json")
        if manifests[0]!=new_manifest:manifests[0].rename(new_manifest)
        # ID del proyecto único en todas las referencias de la copia.
        doc=json.loads(new_manifest.read_text(encoding="utf-8"))
        new_id=uuid4().hex
        doc["project_id"]=new_id
        atomic_json(new_manifest,doc)
        if use_selected_empty:
            # El directorio seleccionado se ha comprobado vacío justo al
            # principio. Revalidarlo antes del renombrado, sin tocar archivos.
            if any(new_dir.iterdir()):
                raise FileExistsError("La carpeta dejó de estar vacía: "+str(new_dir))
            new_dir.rmdir()
        try:
            staging.rename(new_dir)
        except OSError:
            if use_selected_empty:new_dir.mkdir(exist_ok=True)
            raise
        copied=True
        return new_dir/(component+".stemstudio.json")
    finally:
        if not copied and staging.exists():shutil.rmtree(staging)
