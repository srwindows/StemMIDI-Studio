#!/usr/bin/env python3
"""Contrato de carpetas estables, varios módulos y proyectos antiguos intactos."""
import os,sys,tempfile,json,wave,hashlib
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from PySide6.QtWidgets import QApplication,QMessageBox
from project_layout import DIRECTORIES,normalize_location,module_dir,layout_active
from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
from task_staging import TaskStorage
from project_flow import create_named_project
from main import MonitorWindow

def wav(path,seed=1):
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        f.writeframes((bytes([seed,0]))*16000)
    return path

with tempfile.TemporaryDirectory(prefix="stemmidi_project_layout_test_") as directory:
    base=Path(directory)
    os.environ["STEMMIDI_WORKSPACE"]=directory
    app=QApplication([])
    QMessageBox.question=staticmethod(lambda *a,**k:QMessageBox.No)
    QMessageBox.warning=staticmethod(lambda *a,**k:
        (_ for _ in ()).throw(AssertionError("Unexpected warning: "+str(a[1:3]))))
    QMessageBox.information=staticmethod(lambda *a,**k:QMessageBox.Ok)
    main=MonitorWindow()
    parent=base/"mía";parent.mkdir()
    fmt=next(iter(FORMAT_OPTIONS));rate=next(iter(SAMPLE_RATES))
    assert create_named_project(main,"mío",parent,fmt,rate)
    p=parent/"mío"
    assert Path(main.project_dir)==p
    assert Path(main.project_path)==p/"mío.stemstudio.json"
    assert not (p/"mío").exists()
    assert set(f.name for f in p.iterdir() if f.is_dir())==set(DIRECTORIES)
    assert layout_active(p)
    print("EXACT_ONE_PROJECT_FOLDER",p,flush=True)
    for kind,store,public in (
        ("separaciones",main.workbench.separation_storage,"stems"),
        ("midi",main.workbench.midi_storage,"audio_a_midi"),
        ("bateria",main.workbench.drum_storage,"bateria"),
        ("vocal",main.workbench.vocal_storage,"afinacion_vocal")):
        assert store.root==p/"temporales"/kind
        assert module_dir(p,kind)==p/public
    assert main.workbench.separator.dest_edit.text()==str(p/"stems")
    assert main.workbench.converter.outdir.text()==str(p/"audio_a_midi")
    print("SOURCES_OUTPUTS_ONE_FOLDER_PER_MODULE",flush=True)
    store=main.workbench.separation_storage
    work=store.start()
    wav(work/"Voz.wav",1)
    wav(work/"Bateria.wav",2)
    store.set_separation(work)
    results=store.save(p/"backup"/"separaciones",all_files=True)
    assert len(results)==2 and all(r.parent==p/"stems" for r in results)
    assert not (p/"backup"/"separaciones").exists()
    # Same module, second test. New result adds version to FILENAME only.
    wav(work/"Voz.wav",3)
    store.set_separation(work)
    newer=store.save(p/"stems",all_files=True)
    assert len(newer)==2 and all(r.parent==p/"stems" for r in newer)
    assert len(list((p/"stems").glob("*.wav")))==4
    assert all(x.is_file() for x in (p/"stems").iterdir())
    assert not list((p/"stems").glob("*/"))
    assert not any(x.is_dir() for x in (p/"stems").iterdir())
    print("STEMS_SAVED_TWICE_NO_EXTRA_FOLDERS",flush=True)
    from export_dialog import export_files
    import file_dialogs
    old_picker=file_dialogs.get_save_file_name
    try:
        # Aunque el usuario seleccione una carpeta interior errónea,
        # la ruta se corrige a la carpeta canónica de ese módulo.
        file_dialogs.get_save_file_name=lambda *args,**kwargs:(
            str(p/"mío"/"nueva"/"voz_guardada.wav"),"")
        exported=export_files(None,[work/"Voz.wav"],p,"Guardar stem",kind="separaciones")
        assert exported==[p/"stems"/"voz_guardada.wav"],exported
        assert not (p/"mío").exists()
    finally:file_dialogs.get_save_file_name=old_picker
    print("SAVE_DIALOG_ROUTES_TO_STEMS_NOT_NESTED_PROJECT",flush=True)
    midi=main.workbench.midi_storage
    a=midi.next_midi_run();b=midi.next_midi_run()
    assert a==b==p/"temporales"/"midi"/"sesion"/"procesado"
    assert not any(x.is_dir() and x.name.startswith("toma_") for x in a.iterdir())
    print("REPEATED_MIDI_RUNS_REUSE_ONE_WORK_DIRECTORY",flush=True)
    # Guardar el proyecto nunca construye un segundo árbol ni mueve stems.
    from studio_shell import save_project,open_project
    before={x.relative_to(p).as_posix() for x in p.rglob("*") if x.is_dir()}
    assert save_project(main)
    assert save_project(main)
    after={x.relative_to(p).as_posix() for x in p.rglob("*") if x.is_dir()}
    assert after==before,(after-before)
    assert len(list(p.glob("*.stemstudio.json")))==1
    print("TWO_PROJECT_SAVES_NO_DIRECTORY_CHANGE",flush=True)
    # La función de ubicación reconoce carpetas vacías con el mismo nombre,
    # pero rechaza pisar directorios con archivos ajenos.
    from project_layout import project_folder_name
    other=base/"otra"/"mío";other.mkdir(parents=True)
    assert normalize_location(other,"mío",project_folder_name("mío"))==other
    # Tampoco duplicar cuando el usuario elige el directorio de proyecto
    # ya existente: se rechaza, no se crea otra carpeta dentro de él.
    from project_layout import project_folder_name
    assert normalize_location(p,"mío",project_folder_name("mío"))==p
    try:
        create_named_project(main,"mío",p,fmt,rate)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Intentó recrear mío/mío dentro de un proyecto")
    assert not (p/"mío").exists()
    print("EXISTING_NONEMPTY_PROJECT_NOT_NESTED_OR_OVERWRITTEN",flush=True)
    print("EXISTING_EMPTY_PROJECT_NAMED_FOLDER_NOT_DUPLICATED",flush=True)
    assert (p/"backup").is_dir()
    assert open_project(main,str(main.project_path))
    assert (p/"backup").is_dir()
    snapshots=list((p/"backup").glob("Antes_de_abrir_*.zip"))
    print("SNAPSHOTS",len(snapshots),snapshots,flush=True)
    assert len(snapshots)==1
    print("OPEN_PROJECT_BACKUP_ONLY_SNAPSHOTS",flush=True)
    # «Guardar como» hacia un directorio vacío llamado como el proyecto
    # copia ahí directamente y no añade /nuevo/nuevo.
    from project_session import clone_project
    empty_target=base/"copia"/"nuevo"
    empty_target.mkdir(parents=True)
    duplicate=clone_project(p,empty_target,"nuevo")
    assert duplicate==empty_target/"nuevo.stemstudio.json",duplicate
    assert duplicate.is_file()
    assert not (empty_target/"nuevo").exists()
    assert (empty_target/"stems").is_dir()
    assert {x.name for x in (empty_target/"stems").glob("*.wav")}=={
        x.name for x in (p/"stems").glob("*.wav")}
    print("SAVE_AS_INTO_EMPTY_NAMED_FOLDER_ONE_LEVEL",flush=True)
    # Los proyectos anteriores sin carpeta stems conservan sus rutas.
    old=base/"antiguo";old.mkdir()
    (old/"backup"/"separaciones").mkdir(parents=True)
    saved=wav(old/"backup"/"separaciones"/"original.wav")
    assert not layout_active(old)
    assert module_dir(old,"separaciones")==old/"backup"/"separaciones"
    assert saved.is_file()
    print("LEGACY_PROJECT_NON_DESTRUCTIVE_PATH_FALLBACK",flush=True)
print("CONSOLIDATED_LAYOUT_CONTRACT_OK",flush=True)
