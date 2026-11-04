"""Eliminación reversible en proyectos StemMIDI.

Eliminar en un proyecto mueve archivos a una cuarentena de la sesión.
Guardar: envía los pendientes a la papelera del sistema.
Salir sin guardar: restaura cada archivo a su ruta original, sin sobrescribir.
La bitácora en temporales permite recuperar tras una interrupción.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse

from PySide6.QtWidgets import QMessageBox

PROTECTED={"ACTIVA.json","STEMS_APROBADOS.json"}
QUARANTINE=".pendientes_eliminar"
JOURNAL=".eliminaciones_pendientes.json"


def _inside(file,root):
    root=Path(root).resolve()
    file=Path(file).resolve()
    return file!=root and root in file.parents


def _owner(widget):
    """Resuelve MainWindow sin depender de la pestaña donde está el archivo."""
    queue=[widget]
    visited=set()
    while queue:
        obj=queue.pop(0)
        if obj is None or id(obj) in visited:continue
        visited.add(id(obj))
        root=getattr(obj,"project_dir",None)
        if root and getattr(obj,"workbench",None) is not None:
            return obj
        for name in ("main","home","workspace"):
            sub=getattr(obj,name,None)
            if sub is not None and sub is not obj:queue.append(sub)
        parent=getattr(obj,"parent",None)
        if callable(parent):
            try:queue.append(parent())
            except RuntimeError:pass
        if len(visited)>35:break
    return None


def _paths(root):
    root=Path(root).resolve()
    return root/"temporales"/QUARANTINE,root/"temporales"/JOURNAL


def _journal(root):
    staging,file=_paths(root)
    if not file.is_file():return []
    obj=json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(obj,dict) or not isinstance(obj.get("entries"),list):
        raise ValueError("La bitácora de eliminaciones tiene un formato inválido")
    return obj["entries"]


def _write_journal(root,entries):
    staging,file=_paths(root)
    file.parent.mkdir(parents=True,exist_ok=True)
    if not entries:
        file.unlink(missing_ok=True)
        try:staging.rmdir()
        except OSError:pass
        return
    fd,tmp=tempfile.mkstemp(prefix=".eliminaciones_",suffix=".tmp",dir=file.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump({"version":1,"entries":entries},stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,file)
    finally:Path(tmp).unlink(missing_ok=True)


def _checked_entry(root,entry):
    root=Path(root).resolve()
    staging,_=_paths(root)
    if not isinstance(entry,dict):raise ValueError("Entrada de eliminación corrupta")
    original=Path(entry.get("original","")).resolve()
    stored=Path(entry.get("stored","")).resolve()
    if (not _inside(original,root) or _inside(original,root/"backup")
        or not _inside(stored,staging) or original==stored):
        raise ValueError("La eliminación contiene una ruta no autorizada")
    return original,stored


def pending_deletions(root):
    if not root:return []
    return _journal(root)


def rollback_deletions(root,progress=None):
    """Restituye eliminaciones sin pisar originales; progreso por fichero."""
    root=Path(root).resolve()
    entries=_journal(root)
    restored=[]
    for i,entry in enumerate(reversed(entries),1):
        original,stored=_checked_entry(root,entry)
        if progress is not None:
            progress.message(f"Restaurando archivo {i}/{len(entries)}: {original.name}")
        if not stored.is_file():
            if original.is_file():
                if progress is not None:
                    progress.stage(f"Ya recuperado {i}/{len(entries)}: {original.name}")
                continue
            raise FileNotFoundError("No se encuentra el archivo eliminado: "+str(original))
        if original.exists():
            raise FileExistsError("Otro archivo ocupa la ruta que debe recuperarse: "+
                                  str(original))
        original.parent.mkdir(parents=True,exist_ok=True)
        # No utilizar replace sobre destino existente: os.link crea sin pisar
        # y si NTFS no admite hardlinks, recurrir a copia exclusiva verificada.
        try:
            os.link(stored,original,follow_symlinks=False)
        except OSError:
            fd=os.open(original,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o644)
            with os.fdopen(fd,"wb") as output,stored.open("rb") as inp:
                shutil.copyfileobj(inp,output)
                output.flush();os.fsync(output.fileno())
            if _hash(stored)!=_hash(original):
                original.unlink(missing_ok=True)
                raise OSError("Error verificando restauración de "+original.name)
        stored.unlink()
        restored.append(original)
        if progress is not None:
            progress.stage(f"Recuperado {i}/{len(entries)}: {original.name}")
    _write_journal(root,[])
    return restored


def _hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").digest()


def _trash_now(path):
    gio=shutil.which("gio")
    if gio:
        try:
            result=subprocess.run([gio,"trash","--",str(path)],capture_output=True,
                                  text=True,timeout=30,check=False)
            if result.returncode==0:return
        except (OSError,subprocess.TimeoutExpired):
            pass
    _xdg_trash(path)


def finalize_deletions(root,progress=None):
    """Guardar confirma la eliminación; progreso por fichero real archivado."""
    root=Path(root).resolve()
    entries=_journal(root)
    count=0
    for i,entry in enumerate(list(entries),1):
        original,stored=_checked_entry(root,entry)
        if progress is not None:
            progress.message(f"Enviando a la papelera {i}/{len(entries)}: {original.name}")
        if not stored.is_file():
            if original.is_file():
                raise OSError("La eliminación pendiente está en una situación ambigua: "+str(original))
            raise FileNotFoundError("No se encuentra la eliminación pendiente: "+str(stored))
        if original.exists():raise FileExistsError(str(original))
        original.parent.mkdir(parents=True,exist_ok=True)
        os.rename(stored,original)
        try:
            _trash_now(original)
        except Exception:
            if original.is_file() and not stored.exists():os.rename(original,stored)
            raise
        entries.remove(entry)
        _write_journal(root,entries)
        count+=1
        if progress is not None:
            progress.stage(f"Eliminado {count}/{count+len(entries)}: {original.name}")
    return count


def trash_files(parent,paths):
    files=list(dict.fromkeys(Path(p).expanduser().resolve() for p in paths))
    if not files:return False
    main=_owner(parent)
    if main is None:
        QMessageBox.warning(parent,"Proyecto necesario",
            "Para que «Salir sin guardar» pueda recuperar los archivos, "
            "abre primero un proyecto. No se ha eliminado nada.")
        return False
    root=Path(main.project_dir).resolve()
    for source in files:
        if (not source.is_file() or source.is_symlink()
            or not _inside(source,root) or _inside(source,root/"backup")
            or source.name in PROTECTED or source.name.endswith(".stemstudio.json")):
            QMessageBox.warning(parent,"Archivo protegido o externo",
                "Solo puedes eliminar desde StemMIDI archivos del proyecto activo "
                "que no sean manifiestos ni copias de seguridad.\n"
                "No se ha eliminado ningún archivo.")
            return False
    names="\n".join("• "+p.name for p in files[:9])
    if len(files)>9:names+=f"\n… y {len(files)-9} más"
    reply=QMessageBox.question(parent,"Eliminar del proyecto (reversible)",
        f"¿Quitar {len(files)} archivo(s) de la sesión?\n\n{names}\n\n"
        "Hasta que pulses Guardar, podrás recuperarlos con «Salir sin guardar». "
        "Guardar confirmará la eliminación y los enviará a la papelera.",
        QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
    if reply!=QMessageBox.Yes:return False
    staging,_=_paths(root)
    staged=[]
    entries=_journal(root)
    from project_progress import ProjectProgress
    progress=None
    try:
        progress=ProjectProgress(main,"Eliminando archivos",steps=len(files))
        progress.allow_cancel(True)
        staging.mkdir(parents=True,exist_ok=True)
        for i,original in enumerate(files,1):
            progress.message(f"Retirando {i}/{len(files)}: {original.name}")
            token=uuid4().hex+original.suffix
            stored=staging/token
            os.rename(original,stored)
            entry={"original":str(original),"stored":str(stored)}
            entries.append(entry)
            staged.append((original,stored))
            _write_journal(root,entries)
            progress.stage(f"Retirado {i}/{len(files)}: {original.name}")
        progress.allow_cancel(False)
        progress.complete(f"{len(files)} archivo(s) retirados del proyecto")
        return True
    except Exception as exc:
        # Deshacer sólo los ficheros del lote fallido.
        for original,stored in reversed(staged):
            if stored.is_file() and not original.exists():
                os.rename(stored,original)
            entries=[e for e in entries if e.get("original")!=str(original)]
        _write_journal(root,entries)
        if isinstance(exc,__import__("project_progress").OperationCancelled):
            QMessageBox.information(parent,"Eliminación cancelada",
                "Se han recuperado todos los archivos del lote.")
        else:
            QMessageBox.warning(parent,"Eliminación no realizada",
                "No se ha confirmado la eliminación:\n"+str(exc))
        return False
    finally:
        if progress is not None:progress.close()


def _xdg_trash(source):
    """Papelera XDG recuperable en sistemas donde gio falla con NTFS/FUSE."""
    source=Path(source).absolute()
    trash=Path.home()/".local"/"share"/"Trash"
    files=trash/"files"
    info=trash/"info"
    files.mkdir(parents=True,exist_ok=True)
    info.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(files).free<source.stat().st_size+4096:
        raise OSError("No hay espacio suficiente para una copia en la papelera")
    name=source.name
    i=2
    while (files/name).exists() or (info/(name+".trashinfo")).exists():
        name=f"{source.stem}_{i}{source.suffix}"
        i+=1
    destination=files/name
    handle,temp=tempfile.mkstemp(prefix=".stem_trash_",dir=files)
    os.close(handle)
    partial=Path(temp)
    try:
        shutil.copy2(source,partial)
        if _hash(source)!=_hash(partial):
            raise OSError("La copia en papelera no supera SHA-256")
        os.replace(partial,destination)
        metadata=("[Trash Info]\nPath="+urllib.parse.quote(str(source),safe="/")+
                  "\nDeletionDate="+datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")+"\n")
        (info/(name+".trashinfo")).write_text(metadata,encoding="utf-8")
        try:source.unlink()
        except OSError:
            destination.unlink(missing_ok=True)
            (info/(name+".trashinfo")).unlink(missing_ok=True)
            raise
    finally:partial.unlink(missing_ok=True)
