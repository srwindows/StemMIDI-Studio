"""Transacción explícita de proyecto, sin borrar proyectos ajenos.

Trabajo nuevo: temporales/<modulo>/...
Guardar: promoción de ficheros del área provisional a la carpeta definitiva.
Salir sin guardar: elimina SOLO archivos nuevos de la sesión y restaura
manifiesto/configuración anterior. No borra material de otras sesiones.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,os,shutil,tempfile
from project_layout import module_dir
from task_staging import inside

MEDIA={".wav",".flac",".mp3",".ogg",".opus",".m4a",".aif",".aiff",".mid",".midi"}
KINDS={"midi":"audio_a_midi","audio_a_midi":"audio_a_midi",
       "voces":"stems","midi_editado":"piano_roll",
       "separaciones":"stems",
       "bateria":"bateria","vocal":"afinacion_vocal",
       "grabaciones":"grabaciones","piano_roll":"piano_roll",
       "mezclador":"mezclador","resultados":"resultados"}
EXCLUDED={"importados","previsualizaciones","_importacion_temporal"}
STATE_FILES={"ACTIVA.json","STEMS_APROBADOS.json"}


def _files(root):
    root=Path(root).resolve()
    if not root.is_dir():return {}
    return {str(path.relative_to(root)):path for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
            and inside(path,root)}


def begin(main):
    project=getattr(main,"project_dir",None)
    if not project:return
    root=Path(project).resolve()
    # Una sesión interrumpida sin guardar debe restaurar también los
    # archivos pendientes de eliminar, incluso tras un cierre anormal.
    from safe_file_delete import rollback_deletions
    rollback_deletions(root)
    temp=root/"temporales"
    manifest=Path(main.project_path) if getattr(main,"project_path",None) else None
    main._project_transaction={
        "root":root,
        "previous":set(_files(temp)),
        "temp_metadata":{rel:path.read_bytes() for rel,path in _files(temp).items()
                         if path.suffix.lower()==".json" and path.stat().st_size<2_000_000},
        "manifest":manifest,
        "manifest_bytes":manifest.read_bytes() if manifest and manifest.is_file() else None,
    }


def _staged(root):
    root=Path(root).resolve()
    temp=root/"temporales"
    for rel,path in sorted(_files(temp).items()):
        parts=Path(rel).parts
        if not parts or parts[0] in EXCLUDED:continue
        kind=parts[0]
        if kind not in KINDS or path.suffix.lower() not in MEDIA:continue
        if any(p in EXCLUDED for p in parts):continue
        if "_audio_midi_entrada_" in path.name:continue
        yield kind,path


def _equal(a,b):
    if a.stat().st_size!=b.stat().st_size:return False
    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream,"sha256").digest()
    return digest(a)==digest(b)


def _atomic_copy(source,dest,on_chunk=None):
    dest.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(prefix=".stem_commit_",dir=dest.parent)
    try:
        with os.fdopen(handle,"wb") as f,source.open("rb") as inp:
            while True:
                chunk=inp.read(1024*1024)
                if not chunk:break
                f.write(chunk)
                if on_chunk is not None:on_chunk(len(chunk))
            f.flush();os.fsync(f.fileno())
        if not _equal(source,Path(temp)):raise OSError("Error verificando "+source.name)
        os.replace(temp,dest)
    finally:
        Path(temp).unlink(missing_ok=True)


def commit_staged(project,index=None,progress=None):
    """Promover ficheros provisionales con índice estable por tarea.

    Repetir Guardar o actualizar una toma NO crea .mid_2/.mid_3. Si un
    fichero de destino era anterior/ajeno, preservar su nombre y elegir
    otro solamente una vez; el índice mantiene esa correspondencia.
    """
    root=Path(project).resolve()
    ledger=dict(index or {})
    saved={}
    # PREFLIGHT: comprobar TODAS las categorías, fuentes, destinos y
    # referencias ANTES de copiar un solo byte. No dejar medias
    # exportaciones si aparece una categoría nueva como «voces».
    from project_layout import MODULES
    unmapped=sorted(set(KINDS)-set(MODULES))
    if unmapped:
        raise ValueError("Módulos sin destino definido: "+", ".join(unmapped))
    plans=[]
    reserved={}
    for kind,source in _staged(root):
        if not source.is_file() or source.is_symlink():
            raise ValueError("Archivo temporal no disponible: "+str(source))
        key=source.relative_to(root).as_posix()
        destination=ledger.get(key)
        if isinstance(destination,str) and destination:
            target=root/destination
            if not inside(target,root) or inside(target,root/"temporales"):
                raise ValueError("El índice de exportaciones no es seguro")
        else:
            # KINDS es la tabla de normalización única para carpetas
            # históricas; «voces» -> stems y «midi_editado» -> piano_roll.
            target=module_dir(root,KINDS[kind])/source.name
            if kind=="midi" and "pistas_midi" in source.parts:
                target=module_dir(root,"midi")/"pistas_midi"/source.name
            if target.exists() and not _equal(source,target):
                from task_staging import unique_dest
                target=unique_dest(target.parent,source.name)
            ledger[key]=target.relative_to(root).as_posix()
        if target.is_symlink() or (target.parent.exists() and target.parent.is_symlink()):
            raise ValueError("Destino inseguro (enlace): "+str(target))
        if not inside(target,root) or inside(target,root/"temporales"):
            raise ValueError("Destino definitivo no válido: "+str(target))
        if target in reserved and reserved[target]!=source:
            if not _equal(source,reserved[target]):
                raise ValueError("Dos fuentes distintas comparten un destino: "+str(target))
        reserved[target]=source
        plans.append((key,source,target))
    # Los medios ya confirmados durante esta misma operación se restauran
    # si el usuario interrumpe el proceso ANTES del commit del manifiesto.
    from project_progress import OperationCancelled
    applied=[]
    try:
        for key,source,target in plans:
            if progress is not None:progress.begin_media(source.name)
            if target.exists():
                if _equal(source,target):
                    saved[key]=ledger[key]
                    if progress is not None:progress.end_media(source.name)
                    continue
                backup=root/"backup"/"Exportaciones_anteriores"/target.relative_to(root)
                _atomic_copy(target,backup)
            else:
                backup=None
            _atomic_copy(source,target,
                         on_chunk=progress.copied if progress is not None else None)
            # Registrar la modificación ANTES del evento de progreso:
            # Cancelar desde esa señal debe restaurar también este fichero.
            applied.append((target,backup))
            saved[key]=ledger[key]
            if progress is not None:progress.end_media(source.name)
        return saved,ledger
    except OperationCancelled:
        if progress is not None:progress.allow_cancel(False)
        for target,backup in reversed(applied):
            if backup is not None and backup.is_file():
                _atomic_copy(backup,target)
            elif backup is None:
                target.unlink(missing_ok=True)
        raise


def discard(main):
    """No guardar manifiesto, ajustes ni archivos NUEVOS de temporales."""
    tx=getattr(main,"_project_transaction",None)
    if not tx:return []
    root=tx["root"];temp=root/"temporales"
    if not root.is_dir() or not inside(temp,root):
        raise ValueError("Proyecto no válido durante descarte")
    # Eliminar archivos no es Guardar. Recuperar antes de la limpieza
    # de temporales: el archivo devuelto puede ser anterior a esta sesión.
    from safe_file_delete import rollback_deletions,pending_deletions
    pending=pending_deletions(root)
    current_paths=set(_files(temp))
    for entry in pending:
        source=Path(entry["original"])
        if inside(source,temp):
            current_paths.add(str(source.relative_to(temp)))
    current_paths={p for p in current_paths if not (
        p.startswith(".pendientes_eliminar/") or
        p==".eliminaciones_pendientes.json")}
    anticipated=current_paths-tx["previous"]
    from project_progress import ProjectProgress
    progress=ProjectProgress(main,"Descartando cambios no guardados",
           steps=len(pending)+len(anticipated)+1)
    try:
        rollback_deletions(root,progress=progress)
        current=_files(temp)
        fresh=set(current)-tx["previous"]
        # Sólo archivos creados en esta sesión. Los antiguos, incluso temporales,
        # se conservan para evitar perder trabajos de sesiones anteriores.
        removed=[]
        for rel in sorted(fresh,reverse=True):
            path=current[rel]
            if not inside(path,temp) or path.is_symlink():continue
            progress.message(f"Descartando temporal {len(removed)+1}/{len(fresh)}: {path.name}")
            path.unlink()
            removed.append(path)
            progress.stage(f"Temporal retirado {len(removed)}/{len(fresh)}: {path.name}")
        for rel,data in tx["temp_metadata"].items():
            path=temp/rel
            if not inside(path,temp):continue
            path.parent.mkdir(parents=True,exist_ok=True)
            fd,partial=tempfile.mkstemp(prefix=".stem_state_",dir=path.parent)
            try:
                with os.fdopen(fd,"wb") as stream:stream.write(data)
                os.replace(partial,path)
            finally:Path(partial).unlink(missing_ok=True)
        for folder in sorted((x for x in temp.rglob("*") if x.is_dir() and not x.is_symlink()),
                             key=lambda x:len(x.parts),reverse=True):
            try:folder.rmdir()
            except OSError:pass
        previous=tx["manifest_bytes"];manifest=tx["manifest"]
        if manifest is not None:
            if previous is None and manifest.exists():
                # Nunca borrar el manifiesto de un proyecto ya creado: preferible
                # no tocarlo en ausencia de estado previo.
                pass
            elif previous is not None and manifest.read_bytes()!=previous:
                handle,tmp=tempfile.mkstemp(prefix=".stem_revert_",dir=manifest.parent)
                try:
                    with os.fdopen(handle,"wb") as f:
                        f.write(previous);f.flush();os.fsync(f.fileno())
                    os.replace(tmp,manifest)
                finally:Path(tmp).unlink(missing_ok=True)
        progress.stage("Metadatos y manifiesto restaurados")
        progress.complete("Cambios descartados y archivos recuperados")
        return removed
    finally:
        progress.close()

def commit_edited_midi(editor,project):
    """Aplicar notas al MISMO MIDI del proyecto, no crear _piano_nuevo_N.mid.

    Para archivos importados externos la edición queda bajo piano_roll/.
    Mantiene una sola copia de seguridad recuperable del archivo anterior.
    """
    from piano_roll import export_file
    import mido
    project=Path(project).resolve()
    source=Path(editor.current_path).resolve()
    if inside(source,project) and not inside(source,project/"temporales"):
        dest=source
    elif inside(source,project/"temporales"):
        # MIDI temporal que se convierte a MIDI definitivo con el mismo
        # nombre; al pulsar Guardar otra vez se sustituye ese MISMO fichero.
        dest=module_dir(project,"midi")/source.name
    else:
        dest=module_dir(project,"piano_roll")/source.name
    if not dest.suffix.lower() in (".mid",".midi"):
        raise ValueError("El editor debe trabajar sobre un archivo MIDI.")
    dest.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(prefix=".stem_midi_edit_",suffix=".mid",dir=dest.parent)
    os.close(handle)
    trial=Path(temp)
    try:
        export_file(editor.midi,editor.tracks,trial)
        mido.MidiFile(str(trial))
        if dest.is_file():
            if _equal(dest,trial):
                trial.unlink()
                editor.dirty=False
                editor.current_path=dest
                return dest
            backup=project/"backup"/"MIDI_anterior"
            backup.mkdir(parents=True,exist_ok=True)
            _atomic_copy(dest,backup/(dest.stem+".mid"))
        os.replace(trial,dest)
        editor.current_path=dest
        editor.dirty=False
        editor.history.clear();editor.future.clear()
        editor.preview.load(dest)
        editor.notesChanged.emit()
        # Si el MIDI se originó en temporales, actualizar su copia de
        # trabajo tras guardar. Así una segunda pulsación de Guardar no
        # restaura por error la versión anterior de la transcripción.
        if inside(source,project/"temporales") and source!=dest:
            _atomic_copy(dest,source)
        return dest
    finally:trial.unlink(missing_ok=True)

def rebase_payload(obj,promoted,project):
    """Guardar rutas definitivas en lugar de referencias a temporales."""
    project=Path(project).resolve()
    links={str(project/source):str(project/target)
           for source,target in promoted.items()}
    def walk(value):
        if isinstance(value,str):return links.get(value,value)
        if isinstance(value,list):return [walk(x) for x in value]
        if isinstance(value,dict):return {k:walk(v) for k,v in value.items()}
        return value
    return walk(obj)


def finish_commit(main,promoted):
    """Retirar copias de trabajo YA verificadas y actualizar sus referencias.

    Nunca eliminar un archivo sin constatar que la copia definitiva tiene
    los mismos bytes. Los originales externos no participan en este paso.
    """
    project=Path(main.project_dir).resolve()
    links={str(project/source):str(project/target)
           for source,target in promoted.items()}
    if not links:return []
    work=main.workbench
    def rebase(obj):
        if obj is None:return obj
        key=str(obj)
        return Path(links[key]) if key in links else obj
    for store in (work.separation_storage,work.midi_storage,
                  work.drum_storage,work.vocal_storage):
        store.items=[Path(rebase(p)) for p in store.items]
        store.composite=rebase(store.composite)
        store.versions=[{"composite":Path(rebase(v["composite"])),
                         "items":[Path(rebase(x)) for x in v["items"]]}
                        for v in store.versions]
        store.saved.update(str(p) for p in store.items)
        if store.composite:store.saved.add(str(store.composite))
        store.manifest()
    for attr in ("last_file",):
        val=getattr(main,attr,None)
        if val and str(val) in links:setattr(main,attr,links[str(val)])
    main.project_recordings=[links.get(str(p),str(p))
                             for p in main.project_recordings]
    for obj,attribute in ((work.converter,"output"),
                          (work.converter,"chord_output"),):
        value=getattr(obj,attribute,None)
        if value is not None and str(value) in links:
            setattr(obj,attribute,Path(links[str(value)]))
    for line in (work.separator.file_edit,work.converter.audio_path,
                 main.drum_module.input,main.vocal_module.input):
        value=line.text().strip()
        if value in links:line.setText(links[value])
    if work.separator.latest_outputs:
        work.separator.latest_outputs=[Path(rebase(p))
                                       for p in work.separator.latest_outputs]
    for attr in ("selected_file","selected_midi"):
        value=getattr(main.studio_home,attr,None)
        if value is not None and str(value) in links:
            setattr(main.studio_home,attr,Path(links[str(value)]))
    # Approval metadata may still reference a staged instrument.
    approval=work.separation_storage.root/"STEMS_APROBADOS.json"
    if approval.is_file():
        import json
        try:
            old=json.loads(approval.read_text(encoding="utf-8"))
            new=rebase_payload(old,promoted,project)
            if new!=old:
                from project_flow import atomic_json
                atomic_json(approval,new)
        except (OSError,ValueError,TypeError):
            pass
    removed=[]
    for original,destination in links.items():
        src=Path(original);target=Path(destination)
        if not inside(src,project/"temporales"):continue
        if not src.is_file() or src.is_symlink() or not target.is_file():continue
        if not _equal(src,target):continue
        src.unlink()
        removed.append(src)
    # No borrar archivos importados: son originales de trabajo externos
    # reproducibles y pueden seguir referenciados por otros módulos.
    if main.last_file and Path(main.last_file).is_file():
        main.record_preview.load(main.last_file)
    try:
        main.workbench.converter.refresh_project_stems()
        main.studio_home.refresh(force=True)
    except (RuntimeError,AttributeError):
        pass
    return removed

def prune_deleted_payload(payload,project):
    """El manifiesto no debe referirse a pistas cuya eliminación se confirma."""
    from safe_file_delete import pending_deletions
    root=Path(project).resolve()
    dead={str(Path(entry["original"]).resolve())
          for entry in pending_deletions(root)}
    if not dead:return payload
    payload=dict(payload)
    for key in ("recordings","midi_files","separated_files","drum_files",
                "vocal_files","mixer_sources","project_files"):
        entries=payload.get(key)
        if isinstance(entries,list):
            payload[key]=[x for x in entries if str(x) not in dead]
    for key in ("source_recording","source_separation","source_midi",
                "selected_midi","midi_editor_file","drum_input",
                "vocal_input","recording_lab_original","recording_lab_processed"):
        if str(payload.get(key,"")) in dead:
            payload[key]="" if key!="selected_midi" else None
    stems=payload.get("approved_stems")
    if isinstance(stems,dict):
        payload["approved_stems"]={name:path for name,path in stems.items()
                                   if str(path) not in dead}
    return payload


def prune_deleted_runtime(main,original_paths):
    """Mantener sincronizadas las listas de módulos tras Guardar eliminaciones."""
    dead={str(Path(x).resolve()) for x in original_paths}
    if not dead:return
    wb=main.workbench
    for store in (wb.separation_storage,wb.midi_storage,
                  wb.drum_storage,wb.vocal_storage):
        store.items=[p for p in store.items if str(p) not in dead]
        if store.composite and str(store.composite) in dead:
            store.composite=None
        store.versions=[
            {"composite":v["composite"],
             "items":[p for p in v["items"] if str(p) not in dead]}
            for v in store.versions if str(v["composite"]) not in dead]
        store.saved.difference_update(dead)
        store.manifest()
    main.project_recordings=[p for p in main.project_recordings
                             if str(p) not in dead]
    if str(main.last_file) in dead:
        main.last_file=None
        main.record_preview.clear()
    for obj,field in ((wb.converter,"output"),(wb.converter,"chord_output")):
        if str(getattr(obj,field,None)) in dead:
            setattr(obj,field,None)
    for control in (wb.converter.audio_path,wb.separator.file_edit,
                    main.drum_module.input,main.vocal_module.input):
        if control.text().strip() in dead:control.clear()
    if str(wb.piano.current_path) in dead:
        # No borrar ediciones en memoria: la referencia a disco deja
        # de existir, pero se puede trabajar hasta guardar como.
        wb.piano.dirty=True
    for prop in ("selected_file","selected_midi"):
        if str(getattr(main.studio_home,prop,None)) in dead:
            setattr(main.studio_home,prop,None)

def save_clone_snapshot(main,source_root,target_manifest,project_name):
    """Guardar como = confirmar SOLO la copia; fuente original sin cambios.

    Se utiliza el estado en memoria de todos los paneles y se exporta el
    Piano Roll editado al clon sin escribir el MIDI original.
    """
    import json
    from project_flow import atomic_json
    from project_session import rebase_json,prepare_payload
    from studio_shell import project_payload
    from safe_file_delete import pending_deletions,finalize_deletions
    root=Path(source_root).resolve()
    target_manifest=Path(target_manifest).resolve()
    target=target_manifest.parent
    if root==target or root in target.parents:
        raise ValueError("Guardar como no puede modificar el proyecto activo")
    previous=json.loads(target_manifest.read_text(encoding="utf-8"))
    index=previous.get("committed_outputs",{})
    promoted,new_index=commit_staged(target,index)
    state=rebase_json(project_payload(main),root,target)
    state["project_id"]=previous["project_id"]
    state["project_name"]=str(project_name)
    state["project_dir"]=str(target)
    state["committed_outputs"]=new_index
    editor=main.workbench.piano
    if editor.dirty and editor.midi is not None and editor.current_path:
        from piano_roll import export_file
        import mido
        source=Path(editor.current_path).resolve()
        if inside(source,root):
            dest=target/source.relative_to(root)
            if inside(dest,target/"temporales"):
                dest=module_dir(target,"midi")/dest.name
        else:
            dest=module_dir(target,"piano_roll")/source.name
        dest.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix=".stem_clone_midi_",suffix=".mid",dir=dest.parent)
        os.close(fd)
        try:
            export_file(editor.midi,editor.tracks,tmp)
            mido.MidiFile(tmp)
            os.replace(tmp,dest)
        finally:Path(tmp).unlink(missing_ok=True)
        state["midi_editor_file"]=str(dest)
        if str(state.get("selected_midi","")) in (
                str(source),str(target/source.relative_to(root)) if inside(source,root) else ""):
            state["selected_midi"]=str(dest)
    state=rebase_payload(state,promoted,target)
    removed=[entry["original"] for entry in pending_deletions(target)]
    state=prune_deleted_payload(state,target)
    state=prepare_payload(target,state)
    state["committed_outputs"]=new_index
    # Guardar el manifiesto solamente en el nuevo proyecto.
    atomic_json(target_manifest,state)
    finalize_deletions(target)
    # Tras verificar las copias no conservar duplicados de staging dentro
    # del CLON: el proyecto original y sus temporales no se tocan nunca.
    links={target/source:target/final for source,final in promoted.items()}
    for source,final in links.items():
        if inside(source,target/"temporales") and source.is_file() and final.is_file() and _equal(source,final):
            source.unlink()
    for active in (target/"temporales").glob("*/ACTIVA.json"):
        try:
            data=json.loads(active.read_text(encoding="utf-8"))
            data=rebase_payload(data,promoted,target)
            data["saved"]=[str(x) for x in data.get("items",[])]
            atomic_json(active,data)
        except (OSError,ValueError,TypeError):
            pass
    return target_manifest
