"""Estudio Vocal ampliado para Inicio: controles reales, sin duplicar el motor.

La ventana flotante trabaja con VocalTuneModule ya existente. Presets,
Undo/Redo y estado son configuraciones no destructivas; cada audio se
procesa por el motor y se guarda como un archivo nuevo del proyecto.
"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
from results_dragdrop import FilesDragList
from PySide6.QtCore import Qt,QTimer,QSignalBlocker
from PySide6.QtWidgets import (
    QWidget,QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QComboBox,QLineEdit,QSlider,QCheckBox,QTabWidget,QListWidget,
    QListWidgetItem,QMessageBox,QSizePolicy,QFileDialog
)
from ux_controls import PresetStrip
from task_staging import unique_dest,inside
from project_layout import module_dir
import file_dialogs

AUDIO={".wav",".flac",".mp3",".ogg",".m4a",".aif",".aiff"}
VOLUME_NAMES={
    "strength":("Corrección","%"),
    "retune":("Retune","ms"),"humanize":("Humanización","%"),
    "threshold":("Umbral","cents"),
    "compression":("Compresión","%"),
    "highpass":("Corte graves","Hz"),
    "character_amount":("Carácter","%"),
    "warmth":("Calidez","%"),"presence":("Presencia","%"),
    "air":("Aire","%"),"deesser":("De-esser","%"),
    "gate":("Puerta suave","%"),"reverb":("Reverb","%"),
    "wet":("Mezcla FX","%"),
    "doubler":("Doblado ADT","%"),"delay":("Delay","%"),
    "delay_ms":("Tiempo eco","ms"),
    "stereo_width":("Anchura estéreo","%"),
    "output_gain_db":("Salida","dB"),
    "learn_melody":("Melodía","%"),
    "learn_vibrato":("Vibrato","%"),
    "learn_dynamics":("Dinámica","%"),
    "learn_timing":("Tiempo","%"),
}

class VocalHomeStudio(QFrame):
    """Vista útil de la sesión vocal real dentro de su ventana flotante."""

    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self.mod=home._vocal_module
        if self.mod is None:
            raise RuntimeError("El motor de afinación vocal aún no está conectado")
        self.setObjectName("vocalHomeStudio")
        self.setStyleSheet("""
QFrame#vocalHomeStudio {background:#061d41;border:1px solid #277cbd;
    border-radius:6px;color:#e0f8ff;}
QFrame#vocalHomeStudio QLabel {background:transparent;border:none;color:#c8e8ff;}
QFrame#vocalHomeStudio QLabel#vocalHeading {
    color:#6fecff;font-size:12px;font-weight:800;}
QFrame#vocalHomeStudio QTabWidget::pane {
    background:#071d42;border:1px solid #2b91d9;}
QFrame#vocalHomeStudio QTabBar::tab {
    background:#123c74;color:#d9f5ff;padding:6px 12px;border:1px solid #267cca;}
QFrame#vocalHomeStudio QTabBar::tab:selected {
    background:#1261ab;color:#fff;font-weight:700;}
QFrame#vocalHomeStudio QListWidget {
    color:#dff5ff;background:#061832;border:1px solid #347fbd;
    alternate-background-color:#102d55;selection-background-color:#1359a7;
    font-size:11px;}
QFrame#vocalHomeStudio QLineEdit {
    background:#041831;color:#e5f8ff;border:1px solid #2d87bf;}
QFrame#vocalHomeStudio QPushButton {
    background:#0c4582;border:1px solid #2fb5ef;border-radius:4px;
    color:#e7fcff;min-height:25px;padding:3px 8px;}
QFrame#vocalHomeStudio QPushButton:hover {background:#1474b8;}
QFrame#vocalHomeStudio QPushButton#vocalPrimary {
    background:#087eaf;border-color:#57edee;font-weight:700;}
""")
        self._controls={}
        self._undo=[]
        self._redo=[]
        self._pending_before=None
        self._applying=False
        self._project_key=None
        self._result_signature=()
        self._default=deepcopy(self.mod.full_preset_snapshot())
        self._history_timer=QTimer(self)
        self._history_timer.setSingleShot(True)
        self._history_timer.setInterval(350)
        self._history_timer.timeout.connect(self._finish_edit)
        body=QVBoxLayout(self)
        body.setContentsMargins(8,6,8,7)
        body.setSpacing(5)

        header=QHBoxLayout();header.setSpacing(6)
        header.addWidget(self._label("VOZ DE ENTRADA",True))
        self.source_combo=QComboBox(self)
        self.source_combo.setMinimumWidth(160)
        self.source_combo.currentIndexChanged.connect(self._select_source)
        header.addWidget(self.source_combo,1)
        self.import_button=self._button("Cargar audio…",self.import_voice)
        header.addWidget(self.import_button)
        self.update_button=self._button("Actualizar",self.refresh_sources)
        header.addWidget(self.update_button)
        body.addLayout(header)
        self.source_path=QLabel("Sin archivo de voz",self)
        self.source_path.setObjectName("vocalPath")
        self.source_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source_path.setToolTip("Ruta del audio cargado en este proyecto")
        body.addWidget(self.source_path)

        # Los mismos presets que el estudio de vocal completo.
        # El mismo catálogo y valores completos de la pestaña vocal.
        # No introducir nombres o parámetros exclusivos del flotante.
        builtins=dict(self.mod.full_presets.builtins)
        self.presets=PresetStrip(
            "vocal_completo",builtins,
            self.mod.full_preset_snapshot,self.apply_preset,self)
        body.addWidget(self.presets)

        toolbar=QHBoxLayout();toolbar.setSpacing(5)
        self.undo_button=self._button("↶ Deshacer ajustes",self.undo)
        self.redo_button=self._button("↷ Rehacer ajustes",self.redo)
        toolbar.addWidget(self.undo_button)
        toolbar.addWidget(self.redo_button)
        toolbar.addWidget(self._button("Reset",self.reset))
        toolbar.addSpacing(8)
        self.analyze_btn=self._button("Analizar voz",self.mod.analyze)
        toolbar.addWidget(self.analyze_btn)
        self.auto_btn=self._button("Aplicar análisis",self.mod.apply_analysis)
        toolbar.addWidget(self.auto_btn)
        toolbar.addStretch()
        self.process_btn=self._button("Procesar voz",self.start)
        self.process_btn.setObjectName("vocalPrimary")
        toolbar.addWidget(self.process_btn)
        self.cancel_btn=self._button("Cancelar",self.mod.cancel)
        toolbar.addWidget(self.cancel_btn)
        body.addLayout(toolbar)

        self.tabs=QTabWidget(self)
        self.tabs.setObjectName("vocalFloatTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setMaximumHeight(320)
        body.addWidget(self.tabs,1)
        self._build_tune()
        self._build_character()
        self._build_fx()
        self._build_spatial()
        self._build_reference()

        self.feedback=QLabel("Selecciona una grabación monofónica para empezar.")
        self.feedback.setWordWrap(True)
        self.feedback.setMaximumHeight(42)
        body.addWidget(self.feedback)
        versions=QHBoxLayout()
        versions.addWidget(self._label("TOMAS PROCESADAS",True))
        versions.addStretch()
        versions.addWidget(self._button("A · Original",self.play_original))
        versions.addWidget(self._button("B · Resultado",self.play_processed))
        body.addLayout(versions)
        self.results=FilesDragList(self)
        from results_dragdrop import AUDIO as DROPPABLE_AUDIO
        self.results.set_drop_handler(
            lambda paths:len(paths)==1 and self.load_voice(str(paths[0])),
            DROPPABLE_AUDIO)
        self.results.setAlternatingRowColors(True)
        self.results.setMinimumHeight(64)
        self.results.setMaximumHeight(105)
        self.results.itemDoubleClicked.connect(lambda _:self.play_processed())
        body.addWidget(self.results)

        bottom=QHBoxLayout();bottom.setSpacing(6)
        bottom.addWidget(self._button("Guardar ajustes del proyecto",self.save_session))
        bottom.addWidget(self._button(
            "Guardar voz en Resultados",self.save_result))
        bottom.addWidget(self._button("Exportar archivo…",self.export_result))
        bottom.addStretch()
        self.session_status=QLabel("Sin sesión guardada")
        self.session_status.setWordWrap(True)
        bottom.addWidget(self.session_status)
        body.addLayout(bottom)
        self._view_timer=QTimer(self)
        self._view_timer.setInterval(550)
        self._view_timer.timeout.connect(self.refresh)
        self.refresh_sources()
        self.refresh()

    def _button(self,title,callback):
        button=QPushButton(title,self)
        button.clicked.connect(callback)
        return button

    def _label(self,value,heading=False):
        label=QLabel(value,self)
        if heading:label.setObjectName("vocalHeading")
        return label

    def _tab(self,name,columns=2):
        panel=QWidget(self)
        grid=QGridLayout(panel)
        grid.setContentsMargins(12,9,12,9)
        grid.setSpacing(8)
        grid.setAlignment(Qt.AlignTop)
        for i in range(columns):grid.setColumnStretch(i,1)
        self.tabs.addTab(panel,name)
        return grid

    def _add_slider(self,grid,index,key,columns=2):
        name,suffix=VOLUME_NAMES[key]
        source=getattr(self.mod,key)
        slot=QWidget(self)
        box=QVBoxLayout(slot)
        box.setContentsMargins(2,2,2,2)
        box.setSpacing(3)
        head=QHBoxLayout();head.setSpacing(4)
        head.addWidget(QLabel(name))
        value=QLabel("")
        value.setMinimumWidth(52)
        value.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        head.addWidget(value)
        box.addLayout(head)
        slider=QSlider(Qt.Horizontal,self)
        slider.setRange(int(source.minimum()),int(source.maximum()))
        slider.setValue(int(source.value()))
        slider.setMinimumWidth(90)
        slider.setToolTip(
            "Control real del motor vocal. Cambios aplicados"
            " únicamente al pulsar «Procesar voz».")
        def change(number):
            if self._applying:return
            self._begin_edit()
            source.setValue(number)
            self._history_timer.start()
        slider.valueChanged.connect(change)
        box.addWidget(slider)
        grid.addWidget(slot,index//columns,index%columns)
        self._controls[key]=(source,slider,value,suffix)

    def _add_combo(self,grid,row,column,title,source,key):
        area=QHBoxLayout();area.setSpacing(5)
        area.addWidget(QLabel(title))
        control=QComboBox(self)
        for i in range(source.count()):
            control.addItem(source.itemText(i))
        def changed(index):
            if self._applying:return
            self._begin_edit()
            source.setCurrentIndex(index)
            self._history_timer.start()
        control.currentIndexChanged.connect(changed)
        area.addWidget(control,1)
        grid.addLayout(area,row,column)
        self._controls[key]=(source,control,None,"combo")

    def _add_check(self,grid,row,column,title,source,key):
        check=QCheckBox(title,self)
        check.setChecked(source.isChecked())
        check.toggled.connect(
            lambda state:self._change_check(source,state))
        grid.addWidget(check,row,column)
        self._controls[key]=(source,check,None,"check")

    def _change_check(self,source,enabled):
        if self._applying:return
        self._begin_edit()
        source.setChecked(enabled)
        self._history_timer.start()

    def _build_tune(self):
        g=self._tab("Afinación · escala",3)
        self._add_combo(g,0,0,"Tónica",self.mod.tonic,"tonic")
        self._add_combo(g,0,1,"Escala",self.mod.scale,"scale")
        self._add_check(g,0,2,"Sin corregir notas",self.mod.bypass_tune,"bypass_tune")
        for i,key in enumerate((
                "strength","retune","humanize","threshold",
                "highpass","compression")):
            self._add_slider(g,i+3,key,3)
        self.analysis_info=QLabel(
            "Sin analizar: las notas y la tonalidad se estiman únicamente"
            " desde la voz real. Pulsa «Analizar voz» para obtener el informe.")
        self.analysis_info.setWordWrap(True)
        self.analysis_info.setStyleSheet(
            "color:#8dcae7;padding:5px;border-top:1px solid #2368a3;")
        g.addWidget(self.analysis_info,3,0,1,3)

    def _build_character(self):
        g=self._tab("Carácter vocal",3)
        self._add_combo(g,0,0,"Carácter",self.mod.character,"character")
        for i,key in enumerate((
                "character_amount","warmth","presence","air",
                "deesser","gate")):
            self._add_slider(g,i+3,key,3)

    def _build_fx(self):
        g=self._tab("Efectos · mezcla",3)
        for i,key in enumerate((
            "reverb","wet","doubler","delay","delay_ms","stereo_width")):
            self._add_slider(g,i,key,3)

    def _build_spatial(self):
        g=self._tab("Dinámica · salida",3)
        for i,key in enumerate((
            "compression","highpass","output_gain_db",
            "presence","deesser","gate")):
            self._add_slider(g,i,key,3)

    def _build_reference(self):
        g=self._tab("Interpretación",3)
        self.ref_path=QLabel("Sin voz de referencia",self)
        self.ref_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        g.addWidget(self.ref_path,0,0,1,2)
        g.addWidget(self._button("Cargar referencia…",self.pick_reference),0,2)
        self._add_check(g,1,0,"Tengo autorización",self.mod.ref_consent,
                        "ref_consent")
        self._add_check(g,1,1,"Misma canción y letra",
                        self.mod.learn_same_song,"learn_same_song")
        g.addWidget(self._button("Analizar estilo",self.mod.analyze_reference),1,2)
        for i,key in enumerate((
            "learn_melody","learn_vibrato",
            "learn_dynamics","learn_timing")):
            self._add_slider(g,i+6,key,3)
        g.addWidget(self._button(
            "Aplicar interpretación a mi voz",self.mod.start_learning),3,2)
        self.reference_info=QLabel(self.mod.reference_info.text())
        self.reference_info.setWordWrap(True)
        self.reference_info.setStyleSheet("color:#8dcae7;")
        g.addWidget(self.reference_info,4,0,1,3)

    def _full_state(self):
        # Estado para Undo, no forma parte de los presets globales.
        return {"settings":deepcopy(self.mod.full_preset_snapshot()),
                "source":self.mod.input.text().strip(),
                "reference":self.mod.reference.text().strip(),
                "consent":self.mod.ref_consent.isChecked()}

    def _begin_edit(self):
        if self._applying:return
        if self._pending_before is None:
            self._pending_before=self._full_state()

    def _finish_edit(self):
        before=self._pending_before
        self._pending_before=None
        if before is None:return
        if before!=self._full_state():
            self._undo.append(before)
            self._undo=self._undo[-70:]
            self._redo.clear()
        self._update_buttons()

    def _apply_state(self,data):
        self._history_timer.stop()
        self._pending_before=None
        self._applying=True
        try:
            self.mod.apply_full_preset(data["settings"])
            source=data.get("source","")
            if not source or Path(source).is_file():
                self.mod.input.setText(source)
            ref=data.get("reference","")
            if not ref or Path(ref).is_file():
                self.mod.reference.setText(ref)
            self.mod.ref_consent.setChecked(bool(data.get("consent",False)))
        finally:self._applying=False
        # Una instantánea restaurada no tiene por qué coincidir con el
        # preset que aparecía seleccionado. No mostrar un nombre falso.
        with QSignalBlocker(self.presets.choices):
            self.presets.choices.setCurrentIndex(0)
        self.presets.message.setText("Ajustes restaurados")
        self.home._sync_vocal_module(force=True)
        self.refresh_sources()
        self.refresh()
        self._update_buttons()

    def _update_buttons(self):
        self.undo_button.setEnabled(bool(self._undo))
        self.redo_button.setEnabled(bool(self._redo))

    def undo(self):
        self._finish_edit()
        if not self._undo:return
        old=self._undo.pop()
        self._redo.append(self._full_state())
        self._apply_state(old)
        self.session_status.setText("Deshechos ajustes · audio original intacto")

    def redo(self):
        self._finish_edit()
        if not self._redo:return
        again=self._redo.pop()
        self._undo.append(self._full_state())
        self._apply_state(again)
        self.session_status.setText("Restaurados ajustes · audio original intacto")

    def reset(self):
        previous=self._full_state()
        current=deepcopy(previous)
        current["settings"]=deepcopy(self._default)
        if current==previous:return
        self._apply_state(current)
        self._undo.append(previous)
        self._undo=self._undo[-70:]
        self._redo.clear()
        self._update_buttons()
        self.session_status.setText(
            "Ajustes de fábrica restaurados. Deshacer disponible.")

    def apply_preset(self,settings):
        self._begin_edit()
        self.mod.apply_full_preset(settings)
        self._finish_edit()
        self.refresh()

    def _project(self):
        project=getattr(self.home.main,"project_dir",None)
        return Path(project).resolve() if project else None

    def _session_file(self):
        project=self._project()
        return module_dir(project,"vocal")/"sesion_estudio_vocal.json" if project else None

    def save_session(self):
        path=self._session_file()
        if path is None:
            self.session_status.setText("Abre un proyecto antes de guardar.")
            return False
        current=self._full_state()
        project=self._project()
        # Rutas válidas únicamente si pertenecen al proyecto actual.
        for key in ("source","reference"):
            raw=current.get(key)
            if raw and Path(raw).is_file() and inside(raw,project):
                current[key]=str(Path(raw).resolve().relative_to(project))
            else:current[key]=""
        content={"version":1,"settings":current["settings"],
                 "source":current["source"],
                 "reference":current["reference"],
                 "consent":current["consent"]}
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(content,ensure_ascii=False,
                                       indent=2)+"\n",encoding="utf8")
            temp.replace(path)
        except (OSError,ValueError,TypeError) as error:
            self.session_status.setText("Error de guardado: "+str(error))
            return False
        self.session_status.setText("Sesión vocal guardada en el proyecto.")
        return True

    def _load_session(self):
        path=self._session_file()
        self._undo.clear();self._redo.clear();self._pending_before=None
        if path is None or not path.is_file():return
        try:
            data=json.loads(path.read_text(encoding="utf8"))
            if data.get("version")!=1 or not isinstance(data.get("settings"),dict):
                raise ValueError("Formato de sesión incompatible")
            project=self._project()
            current={"settings":data["settings"],
                     "source":"","reference":"",
                     "consent":bool(data.get("consent",False))}
            for key in ("source","reference"):
                rel=data.get(key)
                if isinstance(rel,str) and rel and not Path(rel).is_absolute():
                    file=(project/rel).resolve()
                    if inside(file,project) and file.is_file():
                        current[key]=str(file)
            self._apply_state(current)
            self.session_status.setText("Sesión vocal recuperada.")
        except (OSError,ValueError,TypeError,KeyError) as error:
            self.session_status.setText("Sesión anterior inválida: "+str(error))

    def refresh_sources(self):
        self.mod.refresh_sources()
        self.home._sync_vocal_module(force=True)
        self._sync_sources()

    def _sync_sources(self):
        selected=self.mod.input.text().strip()
        sources=[]
        for index in range(self.home.vocal_source.count()):
            value=self.home.vocal_source.itemData(index)
            if value and Path(value).is_file() and value not in sources:
                sources.append(str(value))
        if selected and Path(selected).is_file() and selected not in sources:
            sources.append(selected)
        with QSignalBlocker(self.source_combo):
            self.source_combo.clear()
            self.source_combo.addItem("— Selecciona una voz —","")
            for p in sources:self.source_combo.addItem(Path(p).name,p)
            i=self.source_combo.findData(selected)
            self.source_combo.setCurrentIndex(i if i>0 else 0)

    def _select_source(self,index):
        if self._applying:return
        source=self.source_combo.itemData(index)
        if not source:return
        if source==self.mod.input.text().strip():return
        self._begin_edit()
        self.mod.input.setText(source)
        self.home._vocal_listen_file=None
        self.home._sync_vocal_module(force=True)
        self._finish_edit()
        self.refresh()

    def import_voice(self):
        project=self._project()
        if project is None:
            self.feedback.setText("Crea o abre un proyecto para cargar voces.")
            return
        file,_=file_dialogs.get_open_file_name(
            self,"Cargar grabación vocal",str(Path.home()),
            "Audio (*.wav *.flac *.mp3 *.ogg *.m4a *.aif *.aiff)")
        if not file:return False
        return self.load_voice(file)

    def load_voice(self,file):
        """Carga por diálogo o drag/drop: misma validación y copia segura."""
        project=self._project()
        if project is None:
            self.feedback.setText("Crea o abre un proyecto para cargar voces.")
            return False
        source=Path(file).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in AUDIO:
            self.feedback.setText("Archivo de audio no admitido.")
            return False
        try:
            info=subprocess.run([
                "ffprobe","-v","error","-select_streams","a:0",
                "-show_entries","stream=sample_rate",
                "-show_entries","format=duration",
                "-of","json",str(source)],
                capture_output=True,text=True,timeout=9,check=True)
            payload=json.loads(info.stdout)
            streams=payload.get("streams",[])
            duration=float(payload.get("format",{}).get("duration",0))
            if not streams or not .34<=duration<=720:
                raise ValueError(
                    "Archivo no decodificable o voz fuera de 0,35 s a 12 min")
            # Copia dentro del proyecto: si desconecta un USB la toma sigue.
            folder=module_dir(project,"vocal")/"entradas"
            folder.mkdir(parents=True,exist_ok=True)
            if inside(source,project):
                dest=source
            else:
                dest=unique_dest(folder,source.name)
                shutil.copy2(source,dest)
            self._begin_edit()
            self.mod.input.setText(str(dest))
            self.home._vocal_listen_file=None
            self._finish_edit()
            self.home._sync_vocal_module(force=True)
            self.refresh_sources()
            self.feedback.setText("Voz cargada y vinculada al proyecto: "+dest.name)
            return True
        except (OSError,ValueError,subprocess.SubprocessError) as error:
            self.feedback.setText("No se pudo cargar la voz: "+str(error)[:145])
            return False

    def pick_reference(self):
        path,_=file_dialogs.get_open_file_name(
            self,"Referencia vocal autorizada",str(Path.home()),
            "Audio (*.wav *.flac *.mp3 *.ogg *.m4a *.aif *.aiff)")
        if path:
            self._begin_edit()
            self.mod.reference.setText(path)
            self._finish_edit()
            self.refresh()

    def start(self):
        if not self.mod.input.text().strip():
            self.feedback.setText("Primero debes cargar una voz.")
            return
        self.mod.start()
        self.refresh()

    def _processed(self):
        chosen=self.results.currentItem()
        if chosen is not None:
            file=Path(chosen.data(Qt.UserRole))
            if file.is_file():return file
        items=[Path(p) for p in self.mod.storage.items if Path(p).is_file()]
        return items[-1] if items else None

    def play_original(self):
        file=Path(self.mod.input.text()).expanduser()
        if not file.is_file():
            self.feedback.setText("Carga una voz antes de escuchar.")
            return
        self.home._vocal_listen_file=str(file.resolve())
        self.home.player.load(file,autoplay=True)
        self.feedback.setText("A · Original: "+file.name)

    def play_processed(self):
        file=self._processed()
        if file is None:
            self.feedback.setText("Procesa la voz antes de escuchar el resultado.")
            return
        self.home._vocal_listen_file=str(file.resolve())
        self.home.player.load(file,autoplay=True)
        self.feedback.setText("B · Procesada: "+file.name)

    def save_result(self):
        file=self._processed()
        project=self._project()
        if file is None or project is None:
            self.session_status.setText("Procesa una voz para guardar el resultado.")
            return False
        target_folder=project/"resultados"
        target_folder.mkdir(parents=True,exist_ok=True)
        target=unique_dest(target_folder,file.name)
        try:
            shutil.copy2(file,target)
            if target.stat().st_size==0:raise OSError("Resultado vacío")
        except (OSError,ValueError) as error:
            self.session_status.setText("Error al guardar audio: "+str(error))
            return False
        self.save_session()
        self.home.refresh(force=True)
        self.mod.resultsChanged.emit()
        self.session_status.setText("Voz guardada en Resultados: "+target.name)
        return target

    def export_result(self):
        file=self._processed()
        if file is None:
            self.session_status.setText("No hay voz procesada para exportar.")
            return
        self.mod.refresh_results()
        for row in range(self.mod.table.rowCount()):
            item=self.mod.table.item(row,1)
            if item and item.data(Qt.UserRole)==str(file):
                self.mod.table.selectRow(row)
                break
        self.mod.save_selected()
        self.refresh()

    def _sync_results(self):
        files=tuple(
            sorted((str(Path(p)) for p in self.mod.storage.items
                    if Path(p).is_file()),key=str.casefold))
        if files==self._result_signature:return
        selection=(self.results.currentItem().data(Qt.UserRole)
                   if self.results.currentItem() else None)
        self._result_signature=files
        with QSignalBlocker(self.results):
            self.results.clear()
            for path in files:
                item=QListWidgetItem(Path(path).name)
                item.setData(Qt.UserRole,path)
                item.setToolTip(path)
                self.results.addItem(item)
                if path==selection:item.setSelected(True)
            if selection is None and files:
                self.results.setCurrentRow(len(files)-1)

    def expand(self):
        self._view_timer.start()
        self.refresh()

    def collapse(self):
        self._view_timer.stop()
        self.home._vocal_listen_file=None
        if self.home.player:
            self.home.player.stop()

    def refresh(self):
        # Ninguna referencia a archivos de otros proyectos al cambiar sesión.
        key=str(self._project() or "")
        if key!=self._project_key:
            self._project_key=key
            self._result_signature=()
            self._undo.clear();self._redo.clear()
            self.home._vocal_listen_file=None
            self._load_session()
            self._sync_sources()
        if not self.isVisible():return
        self._applying=True
        try:
            for key,entry in self._controls.items():
                source,target,label,suffix=entry
                if suffix=="combo":
                    index=source.currentIndex()
                    if target.currentIndex()!=index:
                        with QSignalBlocker(target):target.setCurrentIndex(index)
                elif suffix=="check":
                    state=source.isChecked()
                    if target.isChecked()!=state:
                        with QSignalBlocker(target):target.setChecked(state)
                else:
                    if not target.isSliderDown() and target.value()!=source.value():
                        with QSignalBlocker(target):target.setValue(source.value())
                    label.setText(
                        f"{source.value():+d} {suffix}" if key=="output_gain_db"
                        else f"{source.value()} {suffix}")
            current=Path(self.mod.input.text()) if self.mod.input.text() else None
            self.source_path.setText(
                "Archivo: "+str(current.name) if current and current.is_file()
                else "Sin archivo de voz cargado")
            if current and current.is_file():
                self.source_path.setToolTip(str(current))
            self.ref_path.setText(
                "Referencia: "+Path(self.mod.reference.text()).name
                if self.mod.reference.text() else "Sin voz de referencia")
            self.analysis_info.setText(self.mod.analysis_text.text())
            self.reference_info.setText(self.mod.reference_info.text())
            busy=self.mod.process is not None
            self.process_btn.setEnabled(not busy)
            self.cancel_btn.setEnabled(busy)
            self.analyze_btn.setEnabled(not busy)
            self.auto_btn.setEnabled(
                not busy and self.mod._analysis_report is not None)
            self.presets.setEnabled(not busy)
            self.tabs.setEnabled(not busy)
            self.import_button.setEnabled(not busy)
            self.update_button.setEnabled(not busy)
            self.source_combo.setEnabled(not busy)
            for source,target,_,_ in self._controls.values():
                target.setEnabled(not busy and source.isEnabled())
            self.undo_button.setEnabled(not busy and bool(self._undo))
            self.redo_button.setEnabled(not busy and bool(self._redo))
            self.feedback.setText(self.mod.status.text())
            self._sync_results()
            self._sync_sources()
            self._update_buttons()
            self.undo_button.setEnabled(not busy and bool(self._undo))
            self.redo_button.setEnabled(not busy and bool(self._redo))
        finally:self._applying=False
