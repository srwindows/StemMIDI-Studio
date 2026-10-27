"""Exportación independiente del proyecto: nombre, ruta, lotes y ZIP."""
from __future__ import annotations
import os,shutil,tempfile,zipfile
from pathlib import Path
from PySide6.QtWidgets import QMessageBox,QInputDialog
import file_dialogs

def _copy_atomic(source,target):
    source=Path(source).resolve();target=Path(target).expanduser()
    if not source.is_file():raise ValueError("Origen no disponible: "+str(source))
    if target.is_symlink():raise ValueError("No se puede sobrescribir un enlace simbólico")
    if source==target.resolve():raise ValueError("No se puede sobrescribir el archivo de origen")
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".stem_export_",dir=target.parent)
    try:
        with os.fdopen(fd,"wb") as output,source.open("rb") as original:
            shutil.copyfileobj(original,output,1024*1024)
            output.flush();os.fsync(output.fileno())
        if Path(name).stat().st_size!=source.stat().st_size:
            raise OSError("Copia incompleta de "+str(source))
        os.replace(name,target)
    finally:Path(name).unlink(missing_ok=True)
    return target

def _resolve_conflicts(parent,pairs):
    conflicts=[p for _,p in pairs if p.exists()]
    if not conflicts:return pairs
    dialog=QMessageBox(parent)
    dialog.setWindowTitle("Los archivos ya existen")
    dialog.setText(f"Existen {len(conflicts)} nombres de destino. ¿Qué deseas hacer?")
    dialog.setInformativeText("Sobrescribir los archivos elegidos, generar nombres "
                              "disponibles o cancelar. Los archivos de origen no se modifican.")
    overwrite=dialog.addButton("Sobrescribir",QMessageBox.AcceptRole)
    separate=dialog.addButton("Crear nombres nuevos",QMessageBox.ActionRole)
    dialog.addButton("Cancelar",QMessageBox.RejectRole)
    dialog.exec()
    clicked=dialog.clickedButton()
    if clicked is overwrite:return pairs
    if clicked is not separate:return None
    reserved=set()
    output=[]
    for source,target in pairs:
        choice=target
        i=2
        while choice.exists() or choice in reserved:
            choice=target.with_name(target.stem+"_"+str(i)+target.suffix)
            i+=1
        reserved.add(choice)
        output.append((source,choice))
    return output

def _kind_of_file(path,project,kind=None):
    """Determinar módulo dueño de un resultado sin inspeccionar su contenido."""
    from project_layout import MODULES
    if kind:return kind
    if not project:return "resultados"
    source=Path(path).resolve()
    root=Path(project).resolve()
    try:
        parts=source.relative_to(root).parts
    except ValueError:
        return "resultados"
    if len(parts)>2 and parts[0]=="temporales":
        return parts[1] if parts[1] in MODULES else "resultados"
    if parts and parts[0] in MODULES:return parts[0]
    return "resultados"


def _project_output(source,target,project,kind):
    from project_layout import layout_active,save_folder
    if not project or not layout_active(project):return Path(target)
    return save_folder(project,_kind_of_file(source,project,kind),
                       Path(target).parent)/Path(target).name


def export_files(parent,sources,project_dir=None,title="Guardar resultado",kind=None):
    """Nombre/ruta elegibles. Dentro del proyecto: directorio fijo por módulo."""
    files=[]
    for source in sources:
        p=Path(source).expanduser().resolve()
        if p.is_file() and p not in files:files.append(p)
    if not files:
        QMessageBox.information(parent,title,"No hay archivos disponibles para guardar.")
        return []
    if project_dir:
        from project_layout import module_dir
        initial=module_dir(project_dir,_kind_of_file(files[0],project_dir,kind))
    else:
        initial=files[0].parent
    if len(files)==1:
        src=files[0]
        name,_=file_dialogs.get_save_file_name(parent,title,str(initial/src.name),
                                     "Archivo (*"+src.suffix+");;Todos los archivos (*)")
        if not name:return []
        dest=Path(name)
        if not dest.suffix:dest=dest.with_suffix(src.suffix)
        dest=_project_output(src,dest,project_dir,kind)
        pairs=[(src,dest)]
        return _execute(parent,pairs)
    menu=QMessageBox(parent)
    menu.setWindowTitle(title+" · varios archivos")
    menu.setText(f"Se han seleccionado {len(files)} archivos. ¿Cómo quieres guardarlos?")
    menu.setInformativeText(
        "Sugerencias: todos separados con sus nombres originales; "
        "nombre individual para cada archivo; o un ZIP que contenga el lote.")
    together=menu.addButton("Archivos separados en una carpeta",QMessageBox.AcceptRole)
    individually=menu.addButton("Elegir nombre uno por uno",QMessageBox.ActionRole)
    zipped=menu.addButton("Guardar como ZIP",QMessageBox.ActionRole)
    menu.addButton("Cancelar",QMessageBox.RejectRole)
    menu.exec()
    choice=menu.clickedButton()
    if choice is together:
        folder=file_dialogs.get_existing_directory(parent,"Carpeta de los resultados",
                                                   str(initial))
        if not folder:return []
        prefix,ok=QInputDialog.getText(parent,"Nombre del lote",
            "Prefijo opcional para los archivos (vacío conserva nombres):",text="")
        if not ok:return []
        prefix=prefix.replace("/","_").replace("\\","_")
        pairs=[(p,_project_output(p,Path(folder)/(prefix+p.name),
                                   project_dir,kind)) for p in files]
        return _execute(parent,pairs)
    if choice is individually:
        pairs=[]
        for index,p in enumerate(files,1):
            name,_=file_dialogs.get_save_file_name(parent,
                f"{title} · {index}/{len(files)}",
                str(initial/p.name),"Archivo (*"+p.suffix+");;Todos los archivos (*)")
            if not name:return []
            dst=Path(name)
            if not dst.suffix:dst=dst.with_suffix(p.suffix)
            pairs.append((p,_project_output(p,dst,project_dir,kind)))
        return _execute(parent,pairs)
    if choice is zipped:
        stem=(Path(project_dir).name if project_dir else "Resultados")
        name,_=file_dialogs.get_save_file_name(parent,"Guardar lote ZIP",
            str(initial/(stem+"_resultados.zip")),"Archivo ZIP (*.zip)")
        if not name:return []
        target=Path(name)
        if target.suffix.lower()!=".zip":target=target.with_suffix(".zip")
        # Los ZIP de lotes mixtos pertenecen a Resultados, no a Stems.
        if project_dir:
            from project_layout import layout_active,module_dir,is_project_path
            if layout_active(project_dir) and is_project_path(target,project_dir):
                target=module_dir(project_dir,"resultados")/target.name
        choice=_resolve_conflicts(parent,[(files[0],target)])
        if not choice:return []
        target=choice[0][1]
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix=".stem_zip_",dir=target.parent)
        try:
            with zipfile.ZipFile(temp,"w",compression=zipfile.ZIP_STORED) as archive:
                used=set()
                for source in files:
                    name=source.name
                    i=2
                    while name in used:
                        name=source.stem+"_"+str(i)+source.suffix;i+=1
                    used.add(name)
                    archive.write(source,name)
            with zipfile.ZipFile(temp) as z:
                if z.testzip() is not None:raise OSError("ZIP no válido")
            os.replace(temp,target)
        except (OSError,ValueError,zipfile.BadZipFile) as exc:
            QMessageBox.warning(parent,"Error al guardar ZIP",str(exc))
            return []
        finally:Path(temp).unlink(missing_ok=True)
        QMessageBox.information(parent,"Exportado",f"{len(files)} archivos en:\n{target}")
        return [target]
    return []

def _execute(parent,pairs):
    # Varias pistas pueden compartir el mismo nombre. Ofrecer nombres
    # sucesivos sin colisiones, en lugar de perder ese resultado.
    reserved=set()
    unique=[]
    for source,dest in pairs:
        proposal=Path(dest)
        number=2
        while proposal in reserved:
            proposal=dest.with_name(dest.stem+"_"+str(number)+dest.suffix)
            number+=1
        reserved.add(proposal)
        unique.append((source,proposal))
    # No copiar un archivo sobre sí mismo: ya está en la carpeta final.
    same=[target for source,target in unique if Path(source).resolve()==target.resolve()]
    real=[(source,target) for source,target in unique
          if Path(source).resolve()!=target.resolve()]
    pairs=_resolve_conflicts(parent,real)
    if pairs is None:return []
    result=list(same)
    try:
        for source,dest in pairs:
            result.append(_copy_atomic(source,dest))
    except (OSError,ValueError) as exc:
        QMessageBox.warning(parent,"Error al exportar",
                            str(exc)+"\nLos archivos restantes no se han copiado.")
        return result
    QMessageBox.information(parent,"Guardado",
                            f"Se han guardado {len(result)} archivos.\n"+
                            "\n".join(str(x) for x in result[:5])+
                            (f"\n… y {len(result)-5} más." if len(result)>5 else ""))
    return result
