"""Flujo explícito de proyectos y aceptación de stems originales.

No procesa ni altera audios durante su transferencia entre módulos.
"""
from __future__ import annotations
import json,os,re,shutil,unicodedata
from uuid import uuid4
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
 QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QMessageBox,QFileDialog,
 QWidget,QFormLayout,QLineEdit,QComboBox,QInputDialog
)
from studio_paths import workspace_root
from task_staging import inside
ROOT=workspace_root(__file__)
PROJECTS=ROOT/"proyectos"
KINDS=("separaciones","midi","bateria","vocal")
SAFE_FOLDERS=("grabaciones","temporales")
# La repetición no borra exportaciones guardadas/manuales en separaciones/,
# midi/, bateria/ o voces/. Solo descarta tomas y tareas temporales.
def slug_name(name):
    # Nombres estables y seguros en Debian, Windows y macOS.
    # Nunca permitir separadores de rutas o backslashes en carpetas.
    ascii_name=unicodedata.normalize("NFKD",str(name).strip())
    ascii_name="".join(c for c in ascii_name if not unicodedata.combining(c))
    ascii_name=ascii_name.encode("ascii","ignore").decode("ascii")
    clean=re.sub(r"[^a-zA-Z0-9_-]+","_",ascii_name).strip("_.-")[:74]
    return clean or "Proyecto"

def safe_project_root(folder):
    folder=Path(folder).expanduser().resolve()
    if folder in (Path("/"),Path.home().resolve(),ROOT.resolve()):
        raise ValueError("Selecciona un directorio específico para los proyectos.")
    if not folder.is_dir() and not folder.parent.is_dir():
        raise ValueError("La ruta debe encontrarse en un disco accesible.")
    return folder

def project_directory(main):
    return Path(main.project_dir).resolve() if getattr(main,"project_dir",None) else None

def activate_directory(main,path,project_id,name):
    path=Path(path).resolve()
    from project_layout import project_folder_name
    marker=path/(project_folder_name(name)+".stemstudio.json")
    # Soporta los nombres históricos sin tildes, pero no los renombra.
    if not marker.is_file():
        marker=path/(slug_name(name)+".stemstudio.json")
    if not path.is_dir() or not marker.is_file():
        raise ValueError("El proyecto no tiene su carpeta y manifiesto.")
    if not main.workbench.switch_project(project_id,path):
        return False
    main.project_dir=path
    main.project_name=str(name)
    main.project_path=marker
    main.project_recordings=[]
    main.last_file=None
    main.folder_display.setText(str(path/"grabaciones"))
    main.folder_display.setReadOnly(True)
    main.workbench.bind_project(path)
    main.file_prefix.setText(slug_name(name))
    main.workbench.converter.refresh_project_stems()
    main.tabs.setCurrentWidget(main.studio_home)
    main.studio_home.refresh(force=True)
    main.setWindowTitle("StemMIDI Studio · "+str(name))
    return True

def create_named_project(main,name,base,format_name,rate,show_errors=True,inherit_settings=False):
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    text=str(name).strip()
    if not text or text in (".",".."):
        raise ValueError("Escribe un nombre de proyecto.")
    if format_name not in FORMAT_OPTIONS or int(rate) not in SAMPLE_RATES:
        raise ValueError("Formato o frecuencia de grabación no admitidos.")
    from project_layout import normalize_location,install,project_folder_name
    base=safe_project_root(base)
    component=project_folder_name(text)
    dest=normalize_location(base,text,component)
    # Un proyecto llamado «mío» elegido en una carpeta vacía «mio»
    # no debe crear «mio/mio». Si la ruta contiene cualquier otro dato,
    # nunca se toma ni se sobrescribe silenciosamente.
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise FileExistsError("Ya existe un proyecto o archivos en: "+str(dest)+
            ". Abre el proyecto existente o elige un destino vacío.")
    from studio_shell import _protect_unsaved_project
    if not _protect_unsaved_project(main):
        return False
    preserved_settings=None
    if inherit_settings:
        from studio_settings_library import capture_settings
        preserved_settings=capture_settings(main)
    new_id=uuid4().hex
    if not main.workbench.switch_project(new_id,dest):
        return False
    main.project_dir=dest
    main.project_name=text
    main.project_path=dest/(component+".stemstudio.json")
    main.project_recordings=[]
    main.last_file=None
    # Una sola carpeta raíz y UNA carpeta permanente por módulo.
    # Los procesados múltiples reutilizan temporales sin carpetas de fecha.
    try:
        install(dest)
        main.format.setCurrentText(format_name)
        index=main.capture_rate.findData(int(rate))
        if index>=0:main.capture_rate.setCurrentIndex(index)
        main.limit_lossy_rate(format_name)
        main.folder_display.setText(str(dest/"grabaciones"))
        main.folder_display.setReadOnly(True)
        main.workbench.bind_project(dest)
        if preserved_settings is None:
            main.workbench.converter.select_factory_preset()
        else:
            from studio_settings_library import apply_settings
            apply_settings(main,preserved_settings)
        # El título y la ubicación NUNCA se copian del proyecto anterior.
        main.file_prefix.setText(slug_name(text))
        main.setWindowTitle("StemMIDI Studio · "+text)
        persist(main)
        main.save_config()
        main.tabs.setCurrentWidget(main.studio_home)
        main.studio_home.refresh(force=True)
        return True
    except Exception:
        # Si un disco desconecta a mitad, NO borrar archivos desconocidos.
        raise

def new_project_dialog(main,default_name="",inherit_settings=False):
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    dialog=QDialog(main)
    dialog.setWindowTitle("Crear proyecto · StemMIDI Studio")
    dialog.setMinimumWidth(570)
    form=QFormLayout(dialog)
    heading=QLabel("NUEVO PROYECTO · CONSERVAR AJUSTES"
                    if inherit_settings else
                    "PROYECTO NUEVO · ORGANIZACIÓN PROFESIONAL")
    heading.setStyleSheet("font-size:16px;font-weight:800;color:#e0f8ff")
    form.addRow(heading)
    if inherit_settings:
        message=QLabel("Se cerrará el proyecto anterior sin borrar sus archivos. "
           "El nuevo conserva TODOS los parámetros de los módulos, "
           "pero solicita un nombre y una ubicación nuevos. "
           "No se transfieren grabaciones, stems ni MIDI.")
        message.setWordWrap(True)
        form.addRow(message)
    name=QLineEdit(default_name or "")
    name.setPlaceholderText("Ej.: Mi canción - octubre")
    form.addRow("Nombre del proyecto",name)
    base=QLineEdit(str(getattr(main,"projects_base",None) or PROJECTS))
    base.setMinimumWidth(345)
    row=QHBoxLayout();row.addWidget(base,1)
    browse=QPushButton("Elegir…")
    def browse_dir():
        from file_dialogs import get_existing_directory
        result=get_existing_directory(dialog,"Directorio de proyectos",base.text())
        if result:base.setText(result)
    browse.clicked.connect(browse_dir)
    row.addWidget(browse)
    form.addRow("Carpeta base de trabajo",row)
    full_path=QLabel()
    full_path.setWordWrap(True)
    full_path.setStyleSheet("color:#85f0ff")
    def update_path():
        from project_layout import normalize_location,project_folder_name
        try:
            component=project_folder_name(name.text()) if name.text().strip() else ""
            if not component:
                full_path.setText("Escribe el nombre del proyecto para ver su ubicación.")
                return
            target=normalize_location(base.text().strip(),name.text(),component)
            json_file=target/(component+".stemstudio.json")
            if target.exists():
                if not target.is_dir():
                    condition="No disponible: el destino es un archivo, no una carpeta."
                elif any(target.iterdir()):
                    condition="No disponible: hay archivos o carpetas en el destino."
                else:
                    condition="Disponible: carpeta vacía; no se creará otra dentro."
            else:
                condition="Disponible: se creará una sola carpeta para el proyecto."
            full_path.setText(
                "Carpeta del proyecto: "+str(target)+"/\n"
                "Archivo del proyecto (NO carpeta): "+json_file.name+"\n"+
                "Estado real: "+condition)
        except (OSError,ValueError) as exc:
            full_path.setText("Ruta no válida: "+str(exc))
    name.textChanged.connect(lambda _:update_path())
    base.textChanged.connect(lambda _:update_path())
    # Actualización real si otra aplicación crea archivos mientras el
    # usuario mantiene abierto el diálogo de creación del proyecto.
    from PySide6.QtCore import QTimer
    live_path_timer=QTimer(dialog)
    live_path_timer.setInterval(750)
    live_path_timer.timeout.connect(update_path)
    live_path_timer.start()
    update_path()
    form.addRow("Todos los módulos usarán",full_path)
    format_combo=QComboBox()
    for fmt in FORMAT_OPTIONS:format_combo.addItem(fmt)
    format_combo.setCurrentText(main.format.currentText())
    form.addRow("Formato / profundidad",format_combo)
    rate_combo=QComboBox()
    for r in SAMPLE_RATES:rate_combo.addItem(f"{r/1000:g} kHz · estéreo",r)
    rate_combo.setCurrentIndex(max(0,rate_combo.findData(main.capture_rate.currentData())))
    form.addRow("Frecuencia de muestreo",rate_combo)
    quality=QLabel()
    quality.setWordWrap(True)
    quality.setStyleSheet("color:#e0f8ff")
    def explain():
        fmt=format_combo.currentText()
        if "MP3" in fmt or "AAC" in fmt:
            quality.setText("Tasa de bits: 320 kb/s (con pérdidas).")
        elif "Opus" in fmt:
            quality.setText("Tasa de bits: 256 kb/s (con pérdidas, 48 kHz).")
        else:
            quality.setText("PCM o FLAC sin pérdidas: el bitrate depende de "
                "la frecuencia y profundidad. No es una tasa fija seleccionable.")
    format_combo.currentTextChanged.connect(explain);explain()
    form.addRow("Calidad",quality)
    hint=QLabel("Dentro de la carpeta elegida se creará UNA única carpeta "
      "con el nombre del proyecto, salvo si ya has seleccionado un directorio "
      "vacío con ese mismo nombre. Cada módulo tendrá su propia carpeta fija "
      "(stems, batería, Audio a MIDI, etc.). Se reutiliza sin anidar carpetas "
      "en cada guardado. Los archivos existentes no se sobrescriben sin aviso.")
    hint.setWordWrap(True);form.addRow(hint)
    buttons=QHBoxLayout()
    confirm=QPushButton("Crear y conservar ajustes" if inherit_settings
                        else "Crear proyecto")
    confirm.setObjectName("primary")
    cancel=QPushButton("Cancelar")
    buttons.addStretch();buttons.addWidget(confirm);buttons.addWidget(cancel)
    form.addRow(buttons)
    cancel.clicked.connect(dialog.reject)
    def create():
        try:
            # El diálogo no cierra el proyecto anterior hasta que el usuario
            # confirma nombre y destino. Guardar sigue siendo una decisión suya.
            if inherit_settings and getattr(main,"project_dir",None):
                answer=QMessageBox.question(dialog,"Cerrar proyecto anterior",
                    "¿Guardar los cambios del proyecto actual antes de crear el nuevo?\n\n"
                    "Sí: guardar y continuar.\n"
                    "No: continuar sin modificar el manifiesto anterior.\n"
                    "Cancelar: mantener abierto el proyecto actual.",
                    QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel,
                    QMessageBox.Yes)
                if answer==QMessageBox.Cancel:return
                if answer==QMessageBox.Yes:
                    from studio_shell import save_project
                    if not save_project(main,show_confirmation=False):return
            result=create_named_project(main,name.text(),base.text(),
                    format_combo.currentText(),rate_combo.currentData(),
                    inherit_settings=inherit_settings)
        except (OSError,ValueError) as exc:
            QMessageBox.warning(dialog,"Proyecto no creado",str(exc))
            return
        if result:
            selected=Path(base.text()).expanduser().resolve()
            # Para el próximo proyecto mostrar el directorio CONTENEDOR
            # y no el propio proyecto, evitando una nueva copia anidada.
            main.projects_base=str(selected.parent if
                selected==Path(main.project_dir).resolve() else selected)
            main.save_config()
            dialog.accept()
    confirm.clicked.connect(create)
    return dialog.exec()==QDialog.Accepted

def ensure_recording_project(main):
    """Si se cerró un proyecto, nueva grabación necesita nombre nuevo."""
    if project_directory(main) is not None and main.project_path:
        return True
    return new_project_dialog(main)

def backup_recording(main):
    path=Path(main.last_file) if main.last_file else None
    project=project_directory(main)
    if not project or not path or not path.is_file() or not inside(path,project/"grabaciones"):
        QMessageBox.information(main,"Sin grabación",
            "No hay grabación disponible en este proyecto.")
        return None
    from export_dialog import export_files
    files=export_files(main,[path],project,"Guardar grabación")
    if files:main.log("Grabación exportada: "+str(files[0]))
    return files[0] if files else None

def repeat_project(main,confirm=True):
    """Vacía la toma activa conservando sólo el manifiesto y backup.

    ÚNICAMENTE elimina ficheros dentro de subcarpetas conocidas y del
    proyecto marcado como activo. Jamás elimina un directorio ajeno.
    """
    project=project_directory(main)
    if not project or not main.project_path or not main.project_path.is_file():
        if confirm:QMessageBox.information(main,"Sin proyecto","Primero crea un proyecto.")
        return False
    from PySide6.QtCore import QProcess
    w=main.workbench
    if (main.recording or main.record_pending or w.separator.busy
        or (w.converter.process is not None
            and w.converter.process.state()!=QProcess.NotRunning)
        or (w.mixer is not None and w.mixer.process is not None
            and w.mixer.process.state()!=QProcess.NotRunning)
        or (w.drum_module is not None and w.drum_module.process is not None)
        or (w.drum_module is not None
            and w.drum_module.studio.process is not None)
        or (w.vocal_module is not None and w.vocal_module.process is not None)
        or w.piano.dirty):
        if confirm:QMessageBox.warning(main,"Operación en curso",
            "Detén la grabación y los procesos; guarda los cambios MIDI antes de repetir.")
        return False
    if project.is_symlink() or (project/"backup").is_symlink():
        raise ValueError("El proyecto contiene enlaces simbólicos: repetición bloqueada.")
    from project_layout import project_folder_name
    candidates=(project/(project_folder_name(main.project_name)+".stemstudio.json"),
                project/(slug_name(main.project_name)+".stemstudio.json"))
    expected=next((path for path in candidates
                   if path.is_file() and main.project_path.resolve()==path.resolve()),None)
    if expected is None:
        raise ValueError("La carpeta activa no coincide con el proyecto")
    data=json.loads(expected.read_text(encoding="utf-8"))
    if data.get("project_id")!=main.project_id:
        raise ValueError("El manifiesto no coincide con el proyecto abierto")
    if confirm:
        response=QMessageBox.question(main,"Repetir · eliminar toma actual",
            "La repetición DESCARTARÁ las grabaciones y resultados temporales "
            "de este proyecto. Se conservarán la carpeta, sus ajustes .json "
            "y todo lo guardado en backup.\n\n"
            "¿Seguro que quieres repetir desde cero?",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if response!=QMessageBox.Yes:return False
    # Cerrar vistas/procesos antes de retirar los archivos.
    main.record_preview.clear()
    main.workbench.sep_results.preview.clear()
    main.workbench.midi_results.preview.clear()
    main.workbench.converter.source_preview.clear()
    main.workbench.separator.source_preview.clear()
    main.workbench.piano.preview.clear()
    main.drum_module.preview.clear()
    main.vocal_module.preview.clear()
    # Tras confirmación, borrar exclusivamente contenido conocido
    # (sin seguir enlaces, y sin afectar backup ni el manifiesto).
    for sub in SAFE_FOLDERS:
        target=project/sub
        if not target.is_dir() or target.is_symlink():continue
        for child in target.iterdir():
            if child.is_symlink():child.unlink()
            elif child.is_dir():shutil.rmtree(child)
            elif child.is_file():child.unlink()
    # Reiniciar tareas sin cambiar identificador ni nombre.
    # Reinicializar las vistas y las cuatro tareas dentro de la misma
    # carpeta/proyecto (sin cambiar su identificador original).
    if not main.workbench.switch_project(main.project_id,project):
        return False
    main.project_dir=project
    main.project_path=expected
    main.project_name=data.get("project_name",main.project_name)
    main.project_recordings=[]
    main.last_file=None
    main.record_preview.clear()
    main.folder_display.setText(str(project/"grabaciones"))
    main.folder_display.setReadOnly(True)
    main.workbench.bind_project(project)
    main.file_prefix.setText(slug_name(main.project_name))
    persist(main,auto=True)
    main.tabs.setCurrentWidget(main.studio_home)
    main.studio_home.refresh(force=True)
    return True

def atomic_json(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def default_project_path(main,record_path=None):
    name=Path(record_path).stem if record_path else "Proyecto_sin_titulo"
    name=re.sub(r"[^a-zA-Z0-9_-]+","_",name)[:70] or "Proyecto"
    return PROJECTS/main.project_id/(name+".stemstudio.json")

def persist(main,auto=False):
    """Guardar metadatos sin duplicar muestras; no se sobreescribe audio."""
    from studio_shell import project_payload
    path=main.project_path or default_project_path(main,getattr(main,"last_file",None))
    data=project_payload(main)
    data["project_name"]=str(getattr(main,"project_name","") or "")
    data["project_dir"]=str(project_directory(main) or "")
    data["recordings"]=list(getattr(main,"project_recordings",[]))
    data["approved_stems"]=approved_map(main)
    data["approved_task"]=approved_task(main)
    data["source_recording"]=str(main.last_file) if main.last_file else ""
    atomic_json(path,data)
    main.project_path=Path(path)
    return path

def register_recording(main,path):
    source=Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size==0:
        return
    if not hasattr(main,"project_recordings"):
        main.project_recordings=[]
    if str(source) not in main.project_recordings:
        main.project_recordings.append(str(source))
    main.last_file=str(source)
    # La grabación pasa a ser el origen del proyecto actual.
    main.workbench.separator.on_import_selected(str(source))
    main.workbench.converter.refresh_project_stems()
    output=persist(main,auto=True)
    main.log("Proyecto actualizado con grabación: "+str(output))
    main.studio_home.refresh(force=True)

def approved_path(main):
    return main.workbench.separation_storage.root/"STEMS_APROBADOS.json"

def approved_task(main):
    store=main.workbench.separation_storage
    data=_read_approval(main)
    if data and store.folder and data.get("task")==str(store.folder.resolve()):
        return data["task"]
    return ""

def _read_approval(main):
    try:
        data=json.loads(approved_path(main).read_text(encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}

def approved_map(main):
    store=main.workbench.separation_storage
    data=_read_approval(main)
    if not store.folder or data.get("task")!=str(store.folder.resolve()):
        return {}
    stored=data.get("stems",{})
    if not isinstance(stored,dict):
        return {}
    result={}
    for name,path in stored.items():
        if not isinstance(path,str) or not path.strip():
            continue
        source=Path(path)
        if (name in ("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros","Izquierdo","Derecho")
            and source.is_file() and inside(source,store.folder)):
            result[name]=str(source)
    return result

def classify(path):
    from studio_home import StudioHome
    # Clasificador ya existente en la interfaz Inicio, sin inferir que
    # una canción original es un stem independiente.
    return StudioHome._stem_for(None,path)

def approve_separation(main,quiet=False):
    store=main.workbench.separation_storage
    if main.workbench.separator.busy:
        if not quiet:QMessageBox.warning(main,"Separación ocupada","Termina la separación antes de aprobarla.")
        return False
    from separation_pro_controls import checked_paths
    files=[Path(p).resolve() for p in checked_paths(main)]
    if not files:
        if not quiet:QMessageBox.information(main,"Seleccionar pistas",
            "Marca al menos un stem para aprobar. Solo se transferirán los marcados.")
        return False
    if not files or not store.folder:
        if not quiet:QMessageBox.information(main,"No hay pistas","Separa audio y escucha las pistas antes de aprobarlas.")
        return False
    groups={}
    for file in files:
        if not inside(file,store.folder):continue
        from separation_pro_controls import instrument_for
        channel=instrument_for(file)
        key=channel if channel in ("Izquierdo","Derecho") else classify(file)
        if key=="Otros":
            # "instrumental" también es un stem legítimo: diversos modelos
            # de dos pistas lo nombran así, no "other". Rechazar solamente
            # nombres desconocidos para no confundir la mezcla original.
            tokens=set(re.findall(r"[^\W_]+",file.stem.casefold(),re.UNICODE))
            if not tokens.intersection({"other","others","otros","instrumental",
                                        "accompaniment","acompanamiento","acompañamiento"}):
                continue
        groups.setdefault(key,str(file))
    if not groups:
        if not quiet:QMessageBox.information(main,"Pistas no identificadas",
            "No se han identificado stems de instrumentos. No se fabricarán resultados.")
        return False
    if not quiet:
        description=", ".join(sorted(groups))
        answer=QMessageBox.question(main,"Aprobar separación",
            "¿Has escuchado los stems y los das por buenos?\n\n"+
            description+"\n\n"
            "Solo se aprobarán los stems marcados. Voces y Batería "
            "se vinculan con sus módulos cuando correspondan; originales intactos.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return False
    # Si alguna pista aprobada anteriormente ya no está seleccionada,
    # limpiar solo entradas previamente asignadas por aprobación.
    previous=approved_map(main)
    for name,field in (("Voces",main.vocal_module.input),
                       ("Batería",main.drum_module.input)):
        if name not in groups and previous.get(name) and field.text()==previous[name]:
            field.clear()
    atomic_json(approved_path(main),{
        "task":str(store.folder.resolve()),"stems":groups})
    route_approved(main)
    try:persist(main,auto=True)
    except OSError as exc:
        main.log("Error persistiendo proyecto tras aprobar: "+str(exc))
    main.workbench.sep_results.status.setText(
        "Separación aprobada · stems enviados a los módulos y disponibles en Audio a MIDI.")
    main.log("Stems aprobados: "+", ".join(sorted(groups)))
    return True

def route_approved(main):
    stems=approved_map(main)
    if not stems:return
    main.drum_module.refresh_sources()
    main.vocal_module.refresh_sources()
    if "Batería" in stems:
        main.drum_module.input.setText(stems["Batería"])
        main.drum_module.update_compact_summary()
        main.drum_module.input_hint.setText(
            "Batería aprobada del proyecto: "+Path(stems["Batería"]).name)
    if "Voces" in stems:
        main.vocal_module.input.setText(stems["Voces"])
        main.vocal_module.status.setText(
            "Voz aprobada del proyecto: "+Path(stems["Voces"]).name)
    main.workbench.converter.refresh_project_stems()
    main.studio_home.refresh(force=True)

def add_approval_button(main):
    results=main.workbench.sep_results
    if getattr(results,"approve_button",None):return
    button=QPushButton("✓ Aprobar separación y distribuir stems")
    button.setObjectName("primary")
    button.setToolTip(
        "Tras escuchar los stems, vincula Batería y Voces con sus módulos. "
        "No mueve ni modifica archivos.")
    button.clicked.connect(lambda:approve_separation(main))
    results.layout().insertWidget(results.layout().count()-1,button)
    results.approve_button=button

def clear_session(main):
    """Nuevo proyecto vacío: los anteriores no se eliminan."""
    from uuid import uuid4
    if not main.workbench.switch_project(uuid4().hex):return False
    main.project_dir=None
    main.project_name=None
    main.project_path=None
    main.project_recordings=[]
    main.last_file=None
    main.tabs.setCurrentWidget(main.studio_home)
    main.workbench.converter.refresh_project_stems()
    main.studio_home.refresh(force=True)
    return True

def startup(main):
    """Se muestra después de que Qt haya construido todos los módulos."""
    box=QDialog(main)
    box.setWindowTitle("StemMIDI Studio · Iniciar proyecto")
    box.setModal(True)
    box.setMinimumSize(490,275)
    v=QVBoxLayout(box)
    heading=QLabel("BIENVENIDO A StemMIDI Studio")
    heading.setStyleSheet("font-size:19px;font-weight:800;color:#e0f8ff;")
    v.addWidget(heading)
    info=QLabel("Elige cómo quieres empezar. Ningún proyecto anterior se "
                "mezclará con el nuevo; tus grabaciones permanecen intactas.")
    info.setWordWrap(True);v.addWidget(info)
    a=QPushButton("＋ Proyecto en blanco")
    a.setObjectName("primary")
    b=QPushButton("▱ Abrir proyecto existente…")
    for btn in (a,b):
        btn.setMinimumHeight(47)
        v.addWidget(btn)
    v.addStretch()
    cancel=QPushButton("Salir de StemMIDI Studio")
    v.addWidget(cancel)
    state={"choice":None}
    def choose_blank():
        state["choice"]="blank";box.accept()
    def choose_open():
        from file_dialogs import get_open_file_name
        source,_=get_open_file_name(box,"Abrir proyecto StemMIDI",
                str(PROJECTS if PROJECTS.exists() else ROOT),
                "Proyecto StemMIDI (*.stemstudio.json *.json)")
        if source:
            state["choice"]=source
            box.accept()
    a.clicked.connect(choose_blank)
    b.clicked.connect(choose_open)
    cancel.clicked.connect(box.reject)
    if box.exec()!=QDialog.Accepted:
        main.close()
        return
    if state["choice"]=="blank":
        if not new_project_dialog(main):
            # Volver al selector inicial, evitando registrar una sesión
            # sin nombre cuando se cancela la creación.
            QTimer=__import__("PySide6.QtCore",fromlist=["QTimer"]).QTimer
            QTimer.singleShot(0,lambda:startup(main))
            return
    elif state["choice"]:
        from studio_shell import open_project
        open_project(main,path=state["choice"])
