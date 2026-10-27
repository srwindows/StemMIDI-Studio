"""Desglose de batería: modelo MDX23C de seis familias, datos de proyecto aislados.

No crea pistas sintéticas: lista exclusivamente ficheros de audio generados
por un modelo real que finaliza satisfactoriamente. Instalación de modelos
se hace a petición del usuario; nunca al abrir StemMIDI.
"""
from __future__ import annotations
import file_dialogs
from pathlib import Path
from audio_import import probe_audio, describe_audio, normalize_command
from audio_import_gui import DropPathEdit, pick_audio
from PySide6.QtCore import Qt, QProcess, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QGroupBox
)
from task_staging import TaskStorage, unique_dest, inside
from preview_player import PreviewPlayer
from studio_paths import workspace_root

ROOT=workspace_root(__file__)
MODEL="MDX23C-DrumSep-aufr33-jarredou.ckpt"
PARTS=("Bombo","Caja","Toms","Charles","Ride","Crash")
AUDIO={".wav",".flac",".mp3",".ogg",".m4a",".aiff",".aif"}
ALIASES={
    "kick":"Bombo","bass drum":"Bombo","bombo":"Bombo",
    "snare":"Caja","caja":"Caja",
    "toms":"Toms","tom":"Toms",
    "hh":"Charles","hihat":"Charles","hi-hat":"Charles","charles":"Charles",
    "ride":"Ride","crash":"Crash",
}

def category(path:Path):
    """Clasificar solo etiquetas auténticas producidas por el motor."""
    import re
    tokens=set(x for x in re.split(r"[^a-z0-9]+",path.stem.casefold()) if x)
    if "mezcla" in tokens and "bateria" in tokens:
        return "Mezcla"
    if "hi" in tokens and "hat" in tokens:
        return "Charles"
    for token,category_name in ALIASES.items():
        if token in tokens:return category_name
    return None

def valid_drum_results(folder:Path):
    files=sorted(p for p in Path(folder).iterdir()
                 if p.is_file() and p.suffix.lower() in AUDIO and p.stat().st_size>4096)
    recognised={category(f) for f in files if category(f)}
    if not set(PARTS).issubset(recognised):
        raise ValueError("El modelo de seis pistas no entregó bombo, caja, toms, "
                         "charles, ride y crash completos; "
                         "no se mostrarán salidas incompletas ni archivos ficticios.")
    return files

class DrumModule(QWidget):
    resultsChanged=Signal()
    def __init__(self,main,workbench):
        super().__init__(main)
        self.main=main
        self.workbench=workbench
        self.storage=workbench.drum_storage
        self.process=None
        self._operation=None
        self._current_output=None
        self._normalization_output=None
        self._original_input=None
        self.setObjectName("drumModule")
        lay=QVBoxLayout(self)
        lay.setContentsMargins(11,7,11,7)
        lay.setSpacing(6)
        header=QLabel("ESTUDIO DE BATERÍA · DESGLOSE Y EDICIÓN")
        header.setObjectName("title")
        lay.addWidget(header)
        note=QLabel(
            "Separa una pista de batería ya aislada en bombo, caja, toms, "
            "charles, ride y crash. Utiliza un modelo MDX23C auténtico. "
            "Las pistas se guardan temporalmente en este proyecto; "
            "el audio de origen permanece intacto.")
        note.setWordWrap(True)
        self.description=note
        note.setToolTip("Separación MDX23C de 6 pistas reales. El audio original no se modifica.")
        lay.addWidget(note)
        self.compact_source=QWidget(self)
        compact_root=QVBoxLayout(self.compact_source)
        compact_root.setContentsMargins(6,3,6,3)
        compact_root.setSpacing(2)
        compact=QHBoxLayout()
        compact.setSpacing(7)
        source_actions=QHBoxLayout()
        source_actions.setSpacing(7)
        compact_root.addLayout(compact)
        compact_root.addLayout(source_actions)
        source_actions.addStretch(1)
        self.compact_summary=QLabel("Consola lista · sin pistas cargadas")
        self.compact_summary.setStyleSheet(
            "font-size:11px;font-weight:650;color:#85f0ff;")
        compact.addWidget(self.compact_summary,1)
        self.import_audio_btn=QPushButton("Cargar batería…")
        self.import_audio_btn.setObjectName("primary")
        self.import_audio_btn.setToolTip(
            "Cargar WAV, FLAC, MP3, M4A, OGG, Opus, AIFF, WMA o vídeo con sonido.")
        self.import_audio_btn.clicked.connect(self.browse_audio)
        source_actions.addWidget(self.import_audio_btn)
        self.song_btn=QPushButton("Extraer batería de canción…")
        self.song_btn.setToolTip(
            "Si el archivo contiene voz y otros instrumentos, aislar primero la batería.")
        self.song_btn.clicked.connect(self.open_song_separator)
        source_actions.addWidget(self.song_btn)
        self.listen_input_btn=QPushButton("▶ Escuchar entrada")
        self.listen_input_btn.setToolTip(
            "Escuchar el archivo cargado, antes de desglosarlo.")
        self.listen_input_btn.clicked.connect(self.listen_input)
        self.listen_input_btn.setEnabled(False)
        source_actions.addWidget(self.listen_input_btn)
        self.format_btn=QPushButton("Formatos y ayuda")
        self.format_btn.clicked.connect(self.show_import_help)
        source_actions.addWidget(self.format_btn)
        self.compact_toggle=QPushButton("⚙ Fuente y motor  ▾")
        self.compact_toggle.setToolTip("Mostrar la fuente de audio y la configuración del motor de separación.")
        self.compact_toggle.clicked.connect(self.toggle_source_settings)
        source_actions.addWidget(self.compact_toggle)
        self.input_hint=QLabel(
            "¿Qué cargar? UN archivo con la batería sola (bombo, caja, "
            "toms y platos juntos). WAV, FLAC, MP3, M4A, OGG, AIFF… "
            "Si tienes una canción completa, pulsa «Extraer batería de canción…».")
        self.input_hint.setWordWrap(True)
        self.input_hint.setStyleSheet(
            "color:#e0f8ff;font-size:11px;padding:1px 3px;")
        compact_root.addWidget(self.input_hint)
        self.compact_source.setStyleSheet(
            "QWidget#drumSourceStrip{background:#041c45;"
            "border:1px solid #2bb1fc;border-radius:5px;}")
        self.compact_source.setObjectName("drumSourceStrip")
        lay.addWidget(self.compact_source)
        self.compact_source.setVisible(False)
        controls=QGroupBox("Fuente y motor de separación")
        c=QVBoxLayout(controls)
        source_row=QHBoxLayout()
        source_row.addWidget(QLabel("Batería del proyecto"))
        self.project_source=QComboBox()
        self.project_source.setMinimumWidth(340)
        self.project_source.currentIndexChanged.connect(self._select_source)
        source_row.addWidget(self.project_source)
        self.reload_btn=QPushButton("Actualizar pistas")
        self.reload_btn.clicked.connect(self.refresh_sources)
        source_row.addWidget(self.reload_btn)
        source_row.addStretch(1)
        c.addLayout(source_row)
        pick_row=QHBoxLayout()
        pick_row.addWidget(QLabel("Archivo de entrada"))
        self.input=DropPathEdit("file")
        self.input.setReadOnly(True)
        self.input.imported=self.on_import_selected
        self.input.setPlaceholderText("Sin batería cargada; selecciona la pista del proyecto o importa un audio.")
        self.input.setMaximumWidth(485)
        pick_row.addWidget(self.input)
        self.browse=QPushButton("Importar audio de batería…")
        self.browse.clicked.connect(self.browse_audio)
        pick_row.addWidget(self.browse)
        pick_row.addStretch(1)
        c.addLayout(pick_row)
        self.input_details=QLabel(
            "Carga WAV, FLAC, MP3, M4A, OGG, Opus, AIFF, WMA o vídeo con audio. "
            "Si es una canción completa, extrae primero la pista de batería.")
        self.input_details.setObjectName("muted")
        self.input_details.setWordWrap(True)
        c.addWidget(self.input_details)
        model_row=QHBoxLayout()
        model_row.addWidget(QLabel("Motor"))
        self.model=QComboBox()
        self.model.addItem("MDX23C DrumSep · 6 pistas (IA)",MODEL)
        self.model.setToolTip("Bombo, caja, toms, charles, ride y crash: modelos reales, sin pistas simuladas.")
        model_row.addWidget(self.model)
        self.install_btn=QPushButton("Instalar modelo")
        self.install_btn.setToolTip("Descarga el modelo usando audio-separator. Puede ocupar cientos de MB.")
        self.install_btn.clicked.connect(self.install_model)
        model_row.addWidget(self.install_btn)
        self.manage_models_btn=QPushButton("Más modelos de IA…")
        self.manage_models_btn.clicked.connect(self.open_model_manager)
        model_row.addWidget(self.manage_models_btn)
        model_row.addStretch(1)
        c.addLayout(model_row)
        self.model_state=QLabel()
        self.model_state.setObjectName("muted")
        self.model_state.setWordWrap(True)
        c.addWidget(self.model_state)
        c.addWidget(QLabel("Calidad de salida: FLAC sin pérdida · conserva el archivo original"))
        controls.setLayout(c)
        lay.addWidget(controls)
        self.source_panel=controls
        buttons=QHBoxLayout()
        self.start_btn=QPushButton("◈ Desglosar batería")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start)
        buttons.addWidget(self.start_btn)
        self.cancel_btn=QPushButton("Detener proceso")
        self.cancel_btn.clicked.connect(self.cancel)
        buttons.addWidget(self.cancel_btn)
        buttons.addStretch()
        lay.addLayout(buttons)
        self.status=QLabel("Sin tarea de batería.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.result_table=QTableWidget(0,2)
        self.result_table.setHorizontalHeaderLabels(["Instrumento","Archivo de audio"])
        self.result_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.verticalHeader().hide()
        self.result_table.cellClicked.connect(self.preview_selected)
        from drum_studio import DrumStudio
        self.studio=DrumStudio(self)
        lay.addWidget(self.studio,1)
        # Un preset de BATERÍA COMPLETA se guarda/carga desde cualquier
        # pantalla: mesa, editor, secuenciador o resultados.
        from ux_controls import PresetStrip
        self.full_presets=PresetStrip("bateria_completa",{
            "Rock completo":{
                "mix":self.studio.mixer_presets.builtins["Rock potente"],
                "editor":self.studio.editor_presets.builtins["Natural"],
                "pattern":self.studio.pattern_presets.builtins["Rock 4/4"],
                "bpm":115,"swing":0},
            "Pop completo":{
                "mix":self.studio.mixer_presets.builtins["Pop definido"],
                "editor":self.studio.editor_presets.builtins["Natural"],
                "pattern":self.studio.pattern_presets.builtins["Pop moderno"],
                "bpm":110,"swing":0},
            "Jazz completo":{
                "mix":self.studio.mixer_presets.builtins["Jazz acústico"],
                "editor":self.studio.editor_presets.builtins["Natural"],
                "pattern":self.studio.pattern_presets.builtins["Vacío"],
                "bpm":96,"swing":32},
        },self.snapshot_full_preset,self.apply_full_preset,self)
        self.full_presets.setToolTip(
            "Guarda o recupera todos los ajustes de mezcla, edición y patrón "
            "MIDI sin copiar ni modificar ninguna pista de audio.")
        lay.insertWidget(lay.indexOf(self.studio),self.full_presets)
        self.studio.results_layout.addWidget(self.result_table,1)
        self.preview=PreviewPlayer("ESCUCHAR ELEMENTO SELECCIONADO",self)
        lay.addWidget(self.preview)
        bottom=QHBoxLayout()
        for text,callback in (
            ("Guardar selección…",self.save_selected),
            ("Guardar todas las pistas…",self.save_all),
            ("Descartar tarea temporal…",self.discard)):
            b=QPushButton(text)
            b.clicked.connect(callback)
            bottom.addWidget(b)
        bottom.addStretch()
        lay.addLayout(bottom)
        self.refresh_sources()
        self.refresh_results()
        self.refresh_model_choices()
        self._busy(False)
        self._show_full_source=False
        self.input.textChanged.connect(lambda _:self.update_compact_summary())
        # Panel unificado: el botón de separación siempre queda a mano.
        compact.insertWidget(1,self.start_btn)
        compact.insertWidget(2,self.cancel_btn)
        self._on_studio_tab(0)

    def snapshot_full_preset(self):
        editor=self.studio.editor_presets.snapshot()
        return {
            "mix":self.studio.snapshot_mix(),
            "editor":editor,
            "pattern":self.studio.snapshot_pattern(),
            "bpm":self.studio.seq_bpm.value(),
            "velocity":self.studio.seq_velocity.value(),
            "swing":self.studio.seq_swing.value(),
            "bars":self.studio.seq_bars.currentData(),
        }

    def apply_full_preset(self,settings):
        if isinstance(settings.get("mix"),dict):
            self.studio.apply_mix_preset(settings["mix"])
        if isinstance(settings.get("editor"),dict):
            self.studio.apply_editor_preset(settings["editor"])
        if isinstance(settings.get("pattern"),dict):
            self.studio.apply_pattern_preset(settings["pattern"])
        for key,control in (("bpm",self.studio.seq_bpm),
                            ("velocity",self.studio.seq_velocity),
                            ("swing",self.studio.seq_swing)):
            if key in settings:
                control.setValue(max(control.minimum(),
                                     min(control.maximum(),int(settings[key]))))
        if "bars" in settings:
            idx=self.studio.seq_bars.findData(int(settings["bars"]))
            if idx>=0:self.studio.seq_bars.setCurrentIndex(idx)

    def update_compact_summary(self):
        count=sum(bool(path and Path(path).is_file())
                  for path in self.studio.sources.values())
        source=Path(self.input.text()).name if self.input.text() else "sin archivo de entrada"
        if len(source)>48:source=source[:45]+"…"
        status="modelo instalado" if self.model_ready() else "modelo por instalar"
        self.compact_summary.setText(
            f"{count}/6 salidas · Entrada: {source} · {status}")
        if hasattr(self,"listen_input_btn"):
            self.listen_input_btn.setEnabled(
                bool(self.input.text() and Path(self.input.text()).is_file()))
        self.compact_summary.setToolTip(
            self.input.text() if self.input.text() else
            "Sin audio. Pulsa «Cargar batería…» o usa «Extraer batería de canción…».")

    def _on_studio_tab(self,index):
        # Un único panel: ya no existe navegación entre cinco páginas.
        self.compact_source.setVisible(True)
        self.description.setVisible(False)
        self.source_panel.setVisible(self._show_full_source)
        self.start_btn.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.status.setVisible(True)
        self.compact_toggle.setText(
            "⚙ Ocultar fuente ▴" if self._show_full_source
            else "⚙ Fuente y motor ▾")
        self.update_compact_summary()

    def toggle_source_settings(self):
        self._show_full_source=not self._show_full_source
        self._on_studio_tab(self.studio.currentIndex())

    def engine(self):
        exe=ROOT/"entorno_ia"/"bin"/"audio-separator"
        return exe if exe.is_file() and exe.stat().st_mode & 0o111 else None

    def model_filename(self):
        return self.model.currentData() or MODEL

    def refresh_model_choices(self):
        from model_registry import catalog,installed,is_drum,model_active
        filename=self.model_filename()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItem("MDX23C DrumSep · 6 pistas",MODEL)
        for record in catalog().values():
            if is_drum(record) and installed(record) and record["filename"]!=MODEL:
                self.model.addItem(record["name"],record["filename"])
        selected=model_active().get("drum") or filename
        idx=self.model.findData(selected)
        if idx>=0:self.model.setCurrentIndex(idx)
        self.model.blockSignals(False)
        self._update_model_state()

    def model_dir(self):
        from model_registry import record_for,locate
        record=record_for(self.model_filename())
        return locate(record) if record else ROOT/"modelos"/"bateria"

    def model_ready(self):
        from model_registry import record_for,installed
        record=record_for(self.model_filename())
        return installed(record) if record else (
            (self.model_dir()/self.model_filename()).is_file())

    def _update_model_state(self):
        if not self.engine():
            self.model_state.setText(
                "Motor audio-separator ausente; configura el entorno IA.")
        elif self.model_ready():
            self.model_state.setText(
                "Modelo de seis instrumentos disponible en disco. "
                "La calidad debe comprobarse sobre audio real.")
        else:
            self.model_state.setText(
                "Modelo incompleto o no instalado. Usa Preferencias → Modelos de IA "
                "para consultar y descargar pesos auténticos.")

    def refresh_sources(self):
        previous=self.input.text()
        was_project_source=bool(previous and any(
            previous==self.project_source.itemData(i)
            for i in range(1,self.project_source.count())))
        self.project_source.blockSignals(True)
        self.project_source.clear()
        self.project_source.addItem("— Selecciona batería —",None)
        from task_staging import project_audio_sources
        candidates=(list(self.workbench.separation_storage.items)
                    +project_audio_sources(
                        getattr(self.main,"project_dir",None),
                        ("separaciones","bateria")))
        paths=sorted({Path(p).resolve() for p in candidates
                      if Path(p).is_file() and any(word in Path(p).stem.casefold()
                          for word in ("drums","batería","bateria"))},
                     key=lambda p:(p.name.casefold(),str(p)))
        for p in paths:
            self.project_source.addItem(p.name,str(p))
        index=self.project_source.findData(previous)
        if index>=0:self.project_source.setCurrentIndex(index)
        elif not previous and self.project_source.count()>1:
            self.project_source.setCurrentIndex(1)
        self.project_source.blockSignals(False)
        if self.project_source.currentData() and (
             not previous or previous==self.project_source.currentData()
             or was_project_source):
            self.input.setText(self.project_source.currentData())
            self._original_input=self.input.text()

    def _select_source(self,index):
        source=self.project_source.itemData(index)
        if source:self.on_import_selected(source)

    def browse_audio(self):
        """Importación visible: usa el importador universal y verifica por contenido."""
        previous=Path(self.input.text()).expanduser()
        start=str(previous.parent if previous.is_file() else Path.home()/"Música")
        path=pick_audio(self,start)
        if path:self.on_import_selected(path)

    def on_import_selected(self,path):
        """El explorador y arrastrar/soltar siguen la misma validación."""
        if self.process is not None or self.studio.process is not None:
            QMessageBox.information(self,"Proceso activo",
                "Detén el proceso antes de seleccionar otra fuente de audio.")
            return False
        try:
            info=probe_audio(path)
        except (ValueError,OSError) as exc:
            self.input.setText(self._original_input or "")
            QMessageBox.warning(self,"Audio incompatible",str(exc))
            return False
        self.input.setText(info["path"])
        self._original_input=info["path"]
        detail=describe_audio(info)
        self.input_details.setText(
            detail+" · Fuente original intacta; se convierte a FLAC "
            "automáticamente al desglosar.")
        self.status.setText("Audio cargado: "+Path(info["path"]).name+" · "+detail)
        self.input_hint.setText(
            f"Entrada preparada: {Path(info['path']).name} · {detail}. "
            "Puedes escucharla; para separarla en seis elementos instala "
            "el modelo si aún no está disponible.")
        self.input_hint.setToolTip(info["path"])
        self.update_compact_summary()
        return True

    def listen_input(self):
        """Previsualiza el original en el reproductor visible, sin separarlo."""
        file=Path(self.input.text()).expanduser()
        if not file.is_file():
            QMessageBox.information(
                self,"No hay audio","Primero pulsa «Cargar batería…».")
            return
        self.preview.load(file,autoplay=True)
        self.status.setText(
            "Escuchando entrada sin modificar: "+file.name)

    def show_import_help(self):
        QMessageBox.information(self,"Qué audio necesitas y qué formatos admite",
            "Necesitas UN SOLO ARCHIVO DE AUDIO que contenga la batería "
            "(bombo, caja, toms, charles y platos juntos). No hace falta "
            "cargar seis archivos ni bibliotecas de samples/SF2.\n\n"
            "1. CANCIÓN CON VOZ Y OTROS INSTRUMENTOS: pulsa "
            "«Extraer batería de canción…», importa tu canción en "
            "«Separación de audio» y usa el modelo de 4 pistas "
            "(voz, batería, bajo, otros).\n"
            "2. BATERÍA AISLADA: pulsa «Cargar batería…» y elige la grabación "
            "de batería; después «Desglosar batería».\n\n"
            "Entrada: WAV, FLAC, MP3, OGG, Opus, M4A/AAC, WMA, "
            "AIFF, CAF, APE y vídeo MP4/MKV/MOV/AVI con sonido "
            "(según códecs de FFmpeg).\n"
            "Conversión automática: FLAC estéreo, 44,1 kHz, 24 bits.\n"
            "Salida del desglose: FLAC de bombo, caja, toms, "
            "charles, ride y crash.\n\n"
            "El modelo de inteligencia artificial se instala con "
            "«⚙ Fuente y motor → Instalar modelo»; no lo seleccionas "
            "en el explorador de audio. La calidad depende del audio y del modelo.")

    def open_song_separator(self):
        """Flujo guiado para canciones: usa el separador existente del proyecto."""
        if self.process is not None or self.studio.process is not None:
            QMessageBox.information(self,"Proceso activo",
                "Termina el trabajo actual antes de aislar otra batería.")
            return
        sep=self.workbench.separator
        path=self.input.text() if self.input.text() and Path(self.input.text()).is_file() else None
        if path is None:
            path=pick_audio(self,str(Path.home()/"Música"))
            if not path:return
        sep.on_import_selected(path)
        if sep.file_edit.text()!=str(Path(path).expanduser().resolve()):
            return
        for index in range(sep.profile.count()):
            if "4 pistas" in sep.profile.itemText(index) and "RÁPIDO" in sep.profile.itemText(index):
                sep.profile.setCurrentIndex(index)
                break
        self.main.tabs.setCurrentWidget(self.workbench.separation_tab)
        sep.import_info.setText(
            "PASO 1: separa la canción con 4 pistas. "
            "PASO 2: vuelve a Desglose de batería y elige «drums/batería» "
            "en Fuente y motor; después pulsa Desglosar.")
        sep.file_edit.setFocus()

    def _busy(self,busy):
        self.start_btn.setEnabled(not busy)
        self.install_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.browse.setEnabled(not busy)
        self.import_audio_btn.setEnabled(not busy)
        self.song_btn.setEnabled(not busy)
        self.listen_input_btn.setEnabled(
            not busy and bool(self.input.text()
                and Path(self.input.text()).is_file()))
        self.reload_btn.setEnabled(not busy)

    def _start_process_command(self,command,operation):
        self.process=QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self._operation=operation
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._failed)
        self.process.readyReadStandardOutput.connect(self._log)
        self.process.start(str(command[0]),[str(x) for x in command[1:]])
        self._busy(True)
        return True

    def _launch(self,arguments,operation):
        engine=self.engine()
        if not engine:
            QMessageBox.warning(self,"Motor no encontrado",
                "No se encuentra audio-separator en entorno_ia/bin. "
                "No se han generado pistas.")
            return False
        return self._start_process_command([engine,*arguments],operation)

    def _log(self):
        if not self.process:return
        output=bytes(self.process.readAllStandardOutput()).decode("utf-8","replace")
        lines=[x.strip() for x in output.replace("\r","\n").splitlines() if x.strip()]
        if lines:
            self.status.setText(lines[-1][:250])

    def open_model_manager(self):
        from studio_shell import preferences
        preferences(self.main,open_models=True)

    def install_model(self):
        if self.process is not None or (
            hasattr(self,"studio") and self.studio.process is not None):return
        self.model_dir().mkdir(parents=True,exist_ok=True)
        if self.model_ready():
            self.status.setText("El modelo ya está descargado.")
            return
        size=QMessageBox.question(self,"Descargar modelo IA",
            "Se descargará el modelo "+self.model_filename()+". Requiere espacio "
            "en disco y una conexión a Internet. ¿Continuar?",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if size!=QMessageBox.Yes:return
        args=["--model_filename",self.model_filename(),"--model_file_dir",str(self.model_dir()),
              "--download_model_only"]
        self._launch(args,"install")

    def start(self):
        if self.process is not None or (
            hasattr(self,"studio") and self.studio.process is not None):return
        source=Path(self.input.text()).expanduser()
        if not source.is_file():
            QMessageBox.information(self,"Falta audio de batería",
                "Pulsa «Importar audio…» para cargar una batería aislada. "
                "Si es una canción completa, usa primero "
                "«Extraer batería de canción…».")
            return
        try:
            info=probe_audio(source)
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Audio incompatible",str(exc))
            return
        if not self.model_ready():
            QMessageBox.information(self,"Instala primero el modelo",
                "Antes de separar, instala el modelo real de seis pistas "
                "mediante «Instalar modelo».")
            return
        # La siguiente toma se añade a la tarea existente sin perder
        # visibilidad ni referencias de los desgloses anteriores.
        if not self.engine():
            QMessageBox.warning(self,"Motor no disponible",
                "Falta audio-separator en el entorno de IA del programa.")
            return
        try:
            from project_layout import layout_active
            stable=layout_active(getattr(self.main,"project_dir",None))
            if self.storage.folder and self.storage.folder.is_dir():
                if stable:
                    output=self.storage.processing_folder
                    output.mkdir(parents=True,exist_ok=True)
                else:
                    from datetime import datetime
                    from uuid import uuid4
                    output=self.storage.processing_folder/(
                        "toma_"+datetime.now().strftime("%Y%m%d_%H%M%S_")
                        +uuid4().hex[:6])
                    output.mkdir(parents=True,exist_ok=False)
            else:
                output=self.storage.start()
            normal_folder=output/"_importacion_temporal"
            normal_folder.mkdir(parents=True,exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self,"No se puede crear la tarea",str(exc))
            return
        self._current_output=output
        self._original_input=info["path"]
        stem=("entrada_bateria_"+str(len(self.storage.items)+1)
               if layout_active(getattr(self.main,"project_dir",None))
               and self.storage.items else "entrada_bateria")
        self._normalization_output=normal_folder/(stem+".flac")
        self.status.setText("Preparando audio · FLAC 24 bits, estéreo, 44,1 kHz…")
        command=normalize_command(source,self._normalization_output)
        # QProcess ejecuta la conversión en segundo plano; no bloquea Qt.
        # El original nunca se sobrescribe y el temporal no figura como stem.
        self._start_process_command(command,"normalize")

    def _failed(self,error):
        if error==QProcess.FailedToStart and self.process is not None:
            failed=self.process
            self.status.setText("No se pudo iniciar el motor de batería.")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0,lambda:self._finished(-1,QProcess.CrashExit)
                              if self.process is failed else None)

    def _finished(self,code,status):
        operation=self._operation
        process=self.process
        if process is None:return
        self._log()
        self.process=None
        self._operation=None
        self._busy(False)
        if code!=0 or status!=QProcess.NormalExit:
            self.status.setText(
                "Error preparando el audio." if operation=="normalize" else
                "Separación incompleta o fallida. "
                "No se publicarán pistas inventadas ni incompletas.")
        elif operation=="normalize":
            path=self._normalization_output
            if not path or not path.is_file() or path.stat().st_size<4096:
                self.status.setText("No se pudo convertir el audio a FLAC.")
            else:
                self.status.setText("Audio preparado. Desglosando seis elementos reales…")
                args=[str(path),"--model_filename",self.model_filename(),
                      "--model_file_dir",str(self.model_dir()),
                      "--output_dir",str(self._current_output),
                      "--output_format","FLAC"]
                self._launch(args,"separate")
        elif operation=="install":
            self._update_model_state()
            self.status.setText("Modelo descargado." if self.model_ready() else
                                "No se ha podido verificar la descarga del modelo.")
        elif operation=="separate":
            try:
                valid_drum_results(self._current_output)
                self.storage.set_separation(self._current_output)
                self.status.setText(
                    f"Separación terminada: {len(self.storage.items)} archivos reales. "
                    "Elige qué pistas deseas guardar.")
                self.refresh_results()
                self.resultsChanged.emit()
            except (OSError,ValueError) as exc:
                self.status.setText(str(exc))
        # El FLAC convertido solo es material de trabajo. Retirarlo una
        # vez terminada (o fallida) la separación evita acumular gigabytes
        # de copias normalizadas dentro de los proyectos.
        if operation!="normalize" or code!=0 or status!=QProcess.NormalExit:
            from task_staging import inside
            temporary=self._normalization_output
            if temporary and inside(temporary,self.storage.root):
                try:
                    temporary.unlink(missing_ok=True)
                    temporary.parent.rmdir()  # Solo si está vacía.
                except OSError:
                    pass
            self._normalization_output=None
        process.deleteLater()

    def cancel(self):
        if self.process is None:return
        self.process.kill()
        self.status.setText("Procesamiento detenido; los resultados anteriores no se han eliminado.")

    def refresh_results(self):
        paths=[p for p in self.storage.items if Path(p).is_file()]
        self.result_table.setRowCount(len(paths))
        for row,path in enumerate(paths):
            self.result_table.setItem(row,0,QTableWidgetItem(category(path) or "Otros"))
            item=QTableWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.UserRole,str(path))
            self.result_table.setItem(row,1,item)
        if hasattr(self,"studio"):
            self.studio.refresh()
            if hasattr(self,"compact_summary"):
                self.update_compact_summary()

    def selected_paths(self):
        items=[]
        for index in self.result_table.selectionModel().selectedRows():
            row=index.row()
            item=self.result_table.item(row,1)
            if item:items.append(Path(item.data(Qt.UserRole)))
        return items

    def preview_selected(self,row,col):
        item=self.result_table.item(row,1)
        if item:
            path=Path(item.data(Qt.UserRole))
            if path.is_file():self.preview.load(path)

    def _save(self,paths):
        if not paths:
            QMessageBox.information(self,"Sin selección",
                "Selecciona al menos un resultado.")
            return []
        from export_dialog import export_files
        files=export_files(self,paths,getattr(self.main,"project_dir",None),
                           "Guardar instrumentos de batería",kind="bateria")
        if files:
            self.storage.saved.update(str(p) for p in paths)
            self.storage.manifest()
            self.status.setText(f"Exportados {len(files)} resultado(s) de batería.")
        return files

    def save_selected(self):
        self._save(self.selected_paths())

    def save_all(self):
        self._save(self.storage.items)

    def discard(self):
        if self.process is not None or (
            hasattr(self,"studio") and self.studio.process is not None):
            QMessageBox.information(self,"Proceso activo",
                "Detén la separación antes de descartar.")
            return
        if not self.storage.folder:return
        answer=QMessageBox.question(self,"Descartar resultados",
            "¿Eliminar solo los resultados temporales de este desglose? "
            "Se conservarán los archivos originales y los que hayas guardado.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        self.preview.clear()
        self.storage.discard()
        self.refresh_results()
        if hasattr(self,"studio"):
            self.studio.apply_mix_preset({p:{"gain":0,"pan":0,"mute":False,"solo":False}
                for p in PARTS})
        self.status.setText("Tarea temporal descartada.")
        self.resultsChanged.emit()

    def switch_storage(self,storage):
        if self.process is not None or (
            hasattr(self,"studio") and self.studio.process is not None):
            return False
        self.preview.clear()
        self.storage=storage
        self._original_input=None
        self._normalization_output=None
        self._current_output=None
        self.input.clear()
        self.input_details.setText(
            "Carga una batería aislada. WAV, FLAC, MP3, M4A, OGG, Opus, "
            "AIFF, WMA o vídeo con sonido; para canciones completas "
            "pulsa «Desde canción…».")
        self.studio.reset_project()
        # No consultar todavía main.project_dir: lo actualiza el controlador
        # cuando se completa el cambio de proyecto.
        self.project_source.blockSignals(True)
        self.project_source.clear()
        self.project_source.addItem("— Selecciona batería —",None)
        self.project_source.blockSignals(False)
        self.refresh_results()
        self._update_model_state()
        return True
