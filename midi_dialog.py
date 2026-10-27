#!/usr/bin/env python3
"""Interfaz gráfica para Audio->MIDI (automático y parámetros avanzados)."""
from __future__ import annotations
import file_dialogs

import json
import re
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, QUrl, QMimeData
from PySide6.QtGui import QDesktopServices, QDrag
from audio_import import probe_audio, describe_audio, supported_candidate
from audio_import_gui import DropPathEdit, pick_audio, check_and_describe
from preview_player import PreviewPlayer
from stem_detection import is_separated_stem
from ux_controls import SliderNumber, PresetStrip
from midi_factory_presets import DEFAULT_MIDI_PRESET, USER_APPROVED_MIDI_PRESETS
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHeaderView, QTabWidget,
    QListWidget, QListWidgetItem, QAbstractItemView,
)

from studio_paths import workspace_root
ROOT=workspace_root(__file__)
MIDI_DIR=ROOT/"midi_generados"
ENGINE=ROOT/"midi_engine.py"
TEMPO_ENGINE=ROOT/"tempo_precision.py"
CHORD_ENGINE=ROOT/"chord_detector.py"
PYTHON=ROOT/"entorno_ia"/"bin"/"python"
PREFERENCES=ROOT/"preferencias_midi.json"


class StemFileList(QListWidget):
    """Pistas verdaderas arrastrables; nunca crea entradas ficticias."""
    def startDrag(self,actions):
        item=self.currentItem()
        if item is None:return
        file=Path(item.data(Qt.UserRole))
        if not file.is_file():return
        drag=QDrag(self)
        mime=QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(file))])
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class StemDropBox(QFrame):
    """Cajón de MIDI, valida rutas contra los stems del proyecto actual."""
    def __init__(self,handler,parent=None):
        super().__init__(parent)
        self.handler=handler
        self.setAcceptDrops(True)
        self.setMinimumHeight(62)
        self.setObjectName("stemDropBox")
        self.setStyleSheet(
            "QFrame#stemDropBox{background:#051e4c;border:2px dashed #1ba9d9;"
            "border-radius:6px;}")
        inner=QVBoxLayout(self)
        self.caption=QLabel("↓ ARRASTRA AQUÍ UN STEM PARA CONVERTIRLO A MIDI")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setStyleSheet("color:#85f0ff;font-weight:750;")
        inner.addWidget(self.caption)

    def dragEnterEvent(self,event):
        urls=event.mimeData().urls()
        if len(urls)==1 and urls[0].isLocalFile():
            source=Path(urls[0].toLocalFile()).resolve()
            if self.handler("can",source):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self,event):
        urls=event.mimeData().urls()
        if len(urls)==1 and urls[0].isLocalFile():
            if self.handler("choose",Path(urls[0].toLocalFile()).resolve()):
                event.acceptProposedAction()
                return
        event.ignore()


class AudioMidiDialog(QDialog):
    def __init__(self, parent=None, file_path=None, stems_folder=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Audio a MIDI — Transcripción musical")
        self.resize(1020, 800)
        self.setMinimumSize(800, 620)
        self.process=None
        self.embedded=False
        self.workspace=None
        self.player=None
        self.output=None
        self.chord_output=None
        self._chord_source=None
        self._chord_requested=False
        self.stats=[]
        self.buf=""
        self.cancelled=False
        self.start_time=None
        self.job_file=None
        self.tempo_job=None
        self._tempo_taps=[]
        self.create_ui()
        self.load_preferences()
        # Cada inicio comienza con el preset de serie solicitado, en lugar
        # de heredar el último ajuste de un proyecto distinto.
        self.select_factory_preset()
        self._setting_ready=True
        self._autosave=QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(650)
        self._autosave.timeout.connect(self.save_preferences)
        self._connect_autosave()
        if file_path and Path(file_path).is_file():
            self.audio_path.setText(str(file_path))
            self.source_preview.load(file_path)
        if stems_folder and Path(stems_folder).is_dir():
            self.on_import_folder(str(stems_folder))
        elif self.audio_path.text() and Path(self.audio_path.text()).is_file():
            self.source_preview.load(self.audio_path.text())
            if is_separated_stem(self.audio_path.text()):
                self.auto_separate.setChecked(False)
                self.audio_info.setText("Pista ya separada: se transcribirá directamente "
                    "a MIDI, sin ejecutar Demucs otra vez.")
        self.on_automatic_changed(self.automatic.isChecked())
        self.refresh_project_stems()

    def _connect_autosave(self):
        widgets=[self.bpm,self.onset,self.frame,self.min_duration,
                 self.low,self.high,self.drum,self.min_velocity,
                 self.merge_gap,self.note_shift,self.grid_offset]
        for w in widgets:
            w.valueChanged.connect(lambda value:self._autosave.start())
        combos=[self.precision_profile,self.quant,self.stem_count,self.refinement]
        for widget in combos:
            widget.currentIndexChanged.connect(lambda index:self._autosave.start())
        checks=[self.automatic,self.tempo_auto,self.piano_specialist,
                self.auto_separate,self.align_grid,self.use_folder,self.detect_chords]
        for check in checks:
            check.toggled.connect(lambda checked:self._autosave.start())
        self.filename.editingFinished.connect(self.save_preferences)
        self.outdir.editingFinished.connect(self.save_preferences)
        self.form_tabs.currentChanged.connect(lambda _:self._autosave.start())

    def parameter_snapshot(self):
        return {"automatic":self.automatic.isChecked(),
                "tempo_auto":self.tempo_auto.isChecked(),
                "bpm":self.bpm.value(),"quantize":self.quant.currentData(),
                "precision_profile":self.precision_profile.currentData(),
                "note_refinement":self.refinement.currentData(),
                "piano_specialist":self.piano_specialist.isChecked(),
                "detect_chords":self.detect_chords.isChecked(),
                "separate_first":self.auto_separate.isChecked(),
                "separation_stems":self.stem_count.currentData(),
                "onset":self.onset.value(),"frame":self.frame.value(),
                "min_length_ms":self.min_duration.value(),
                "min_pitch":self.low.value(),"max_pitch":self.high.value(),
                "drum_sensitivity":self.drum.value(),
                "min_velocity":self.min_velocity.value(),
                "merge_gap_ms":self.merge_gap.value(),
                "note_shift_ms":self.note_shift.value(),
                "grid_offset_ms":self.grid_offset.value(),
                "auto_grid_alignment":self.align_grid.isChecked()}

    def apply_parameters(self,data):
        selects={"precision_profile":self.precision_profile,
                 "note_refinement":self.refinement,
                 "quantize":self.quant,"separation_stems":self.stem_count}
        for key,combo in selects.items():
            if key in data:
                i=combo.findData(data[key])
                if i>=0:combo.setCurrentIndex(i)
        checks={"automatic":self.automatic,"tempo_auto":self.tempo_auto,
                "piano_specialist":self.piano_specialist,
                "detect_chords":self.detect_chords,
                "separate_first":self.auto_separate,"auto_grid_alignment":self.align_grid}
        for key,check in checks.items():
            if key in data:check.setChecked(bool(data[key]))
        numbers={"bpm":self.bpm,"onset":self.onset,"frame":self.frame,
                 "min_length_ms":self.min_duration,"min_pitch":self.low,
                 "max_pitch":self.high,"drum_sensitivity":self.drum,
                 "min_velocity":self.min_velocity,"merge_gap_ms":self.merge_gap,
                 "note_shift_ms":self.note_shift,"grid_offset_ms":self.grid_offset}
        for key,widget in numbers.items():
            if key in data:widget.setValue(data[key])
        if self.audio_path.text() and is_separated_stem(self.audio_path.text()):
            self.auto_separate.setChecked(False)
        self.save_preferences()

    def select_factory_preset(self,name=DEFAULT_MIDI_PRESET):
        """Restaura todos los controles del preset oficial y marca su nombre.

        No toca archivos de audio ni cambia las rutas del proyecto.
        """
        values=self.presets.builtins.get(name)
        if not isinstance(values,dict):
            raise ValueError("Preset MIDI de fábrica desconocido: "+str(name))
        self.apply_parameters(values)
        self.presets.refresh(select=("base",name))
        return self.parameter_snapshot()

    def load_preferences(self):
        try:
            cfg=json.loads(PREFERENCES.read_text(encoding="utf-8"))
            self.use_folder.setChecked(bool(cfg.get("use_folder",False)))
            self.automatic.setChecked(bool(cfg.get("automatic",True)))
            self.tempo_auto.setChecked(bool(cfg.get("tempo_auto",True)))
            self.bpm.setValue(float(cfg.get("bpm",120)))
            quant=self.quant.findData(cfg.get("quantize","off"))
            if quant>=0:self.quant.setCurrentIndex(quant)
            self.piano_specialist.setChecked(bool(cfg.get("piano_specialist",True)))
            self.detect_chords.setChecked(bool(cfg.get("detect_chords",False)))
            self.auto_separate.setChecked(bool(cfg.get("separate_first",False)))
            sep=self.stem_count.findData(str(cfg.get("separation_stems","4")))
            if sep>=0:self.stem_count.setCurrentIndex(sep)
            self.onset.setValue(float(cfg.get("onset",.5)))
            self.frame.setValue(float(cfg.get("frame",.3)))
            self.min_duration.setValue(int(cfg.get("min_length_ms",120)))
            self.low.setValue(int(cfg.get("min_pitch",28)))
            self.high.setValue(int(cfg.get("max_pitch",100)))
            self.drum.setValue(float(cfg.get("drum_sensitivity",.35)))
            self.align_grid.setChecked(bool(cfg.get("auto_grid_alignment",True)))
            idx=self.refinement.findData(cfg.get("note_refinement","balanced"))
            if idx>=0:self.refinement.setCurrentIndex(idx)
            idx=self.precision_profile.findData(cfg.get("precision_profile","balanced"))
            if idx>=0:self.precision_profile.setCurrentIndex(idx)
            self.min_velocity.setValue(int(cfg.get("min_velocity",0)))
            self.merge_gap.setValue(int(cfg.get("merge_gap_ms",0)))
            self.note_shift.setValue(int(cfg.get("note_shift_ms",0)))
            self.grid_offset.setValue(int(cfg.get("grid_offset_ms",0)))
            self.outdir.setText(cfg.get("output_dir",str(MIDI_DIR)))
            self.filename.setText(cfg.get("name","Transcripcion"))
            self.folder_path.setText(cfg.get("folder_path",""))
            self.audio_path.setText(cfg.get("audio_path",""))
            tab=int(cfg.get("active_section",0))
            if 0<=tab<self.form_tabs.count():
                self.form_tabs.setCurrentIndex(tab)
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
            pass

    def save_preferences(self):
        try:
            data={
                "use_folder":self.use_folder.isChecked(),
                "automatic":self.automatic.isChecked(),
                "tempo_auto":self.tempo_auto.isChecked(),
                "bpm":self.bpm.value(),
                "quantize":self.quant.currentData(),
                "piano_specialist":self.piano_specialist.isChecked(),
                "detect_chords":self.detect_chords.isChecked(),
                "separate_first":self.auto_separate.isChecked(),
                "separation_stems":self.stem_count.currentData(),
                "onset":self.onset.value(),"frame":self.frame.value(),
                "min_length_ms":self.min_duration.value(),
                "min_pitch":self.low.value(),"max_pitch":self.high.value(),
                "drum_sensitivity":self.drum.value(),
                "precision_profile":self.precision_profile.currentData(),
                "note_refinement":self.refinement.currentData(),
                "min_velocity":self.min_velocity.value(),
                "merge_gap_ms":self.merge_gap.value(),
                "note_shift_ms":self.note_shift.value(),
                "grid_offset_ms":self.grid_offset.value(),
                "auto_grid_alignment":self.align_grid.isChecked(),
                "output_dir":self.outdir.text(),"name":self.filename.text(),
                "folder_path":self.folder_path.text(),"audio_path":self.audio_path.text(),
                "active_section":self.form_tabs.currentIndex(),
            }
            PREFERENCES.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        except (OSError,ValueError,TypeError) as exc:
            self.log.appendPlainText("No se pudieron guardar preferencias MIDI: "+str(exc))

    def create_ui(self):
        outer=QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        inner=QWidget()
        inner.setObjectName("main")
        root=QVBoxLayout(inner)
        root.setContentsMargins(22,18,24,21)
        root.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        heading=QLabel("AUDIO A MIDI")
        heading.setObjectName("title")
        root.addWidget(heading)
        intro=QLabel("Reconoce alturas, acordes y duración de las notas. "
                    "Convierte una grabación o varias pistas de instrumentos en un archivo MIDI multipista.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        source=QFrame()
        source.setObjectName("panel")
        form=QVBoxLayout(source)
        form.setContentsMargins(17,14,17,16)
        form.setSpacing(11)

        self.use_folder=QCheckBox("Convertir una carpeta de pistas separadas en un MIDI multipista")
        self.use_folder.setToolTip("Recomendado después de separar voz, batería, bajo y demás instrumentos")
        self.use_folder.toggled.connect(self.on_folder_toggle)
        form.addWidget(self.use_folder)
        fr=QHBoxLayout()
        self.audio_path=DropPathEdit("file")
        self.audio_path.imported=self.on_import_file
        self.audio_path.editingFinished.connect(self.sync_source_preview)
        self.audio_path.setPlaceholderText("Arrastra o importa un archivo de audio o vídeo…")
        fr.addWidget(self.audio_path,1)
        self.file_button=QPushButton("Importar audio…")
        self.file_button.clicked.connect(self.pick_audio)
        fr.addWidget(self.file_button)
        form.addLayout(fr)
        self.audio_info=QLabel("Compatible con formatos decodificables por FFmpeg; los vídeos deben tener sonido.")
        self.audio_info.setObjectName("muted")
        self.audio_info.setWordWrap(True)
        form.addWidget(self.audio_info)
        folder_row=QHBoxLayout()
        self.folder_path=DropPathEdit("directory")
        self.folder_path.imported=self.on_import_folder
        self.folder_path.setPlaceholderText("Arrastra una carpeta de pistas de cualquier formato admitido…")
        self.folder_path.setEnabled(False)
        folder_row.addWidget(self.folder_path,1)
        self.folder_button=QPushButton("Elegir carpeta")
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self.pick_folder)
        folder_row.addWidget(self.folder_button)
        form.addLayout(folder_row)
        self.auto_separate=QCheckBox("Separar instrumentos automáticamente antes de generar el MIDI")
        self.auto_separate.setChecked(False)
        self.auto_separate.setToolTip("Para una canción mezclada: primero separa instrumentos con IA y después los transcribe")
        form.addWidget(self.auto_separate)
        self.detect_chords=QCheckBox("♬ Detectar acordes · crear MIDI independiente (opcional)")
        self.detect_chords.setChecked(False)
        self.detect_chords.setToolTip(
            "Analiza el espectro del audio real con cromagrama y busca triadas/"
            "séptimas sostenidas. Genera un MIDI de acordes independiente, "
            "sólo si existe confianza suficiente; no inventa armonía.")
        form.addWidget(self.detect_chords)
        chords_hint=QLabel("Experimental: útil para acompañamiento polifónico. "
            "No se garantiza distinguir todos los acordes de grabaciones complejas.")
        chords_hint.setWordWrap(True)
        chords_hint.setObjectName("muted")
        form.addWidget(chords_hint)
        stems_row=QHBoxLayout()
        stems_row.addWidget(QLabel("Separación automática:"))
        self.stem_count=QComboBox()
        self.stem_count.addItem("4 pistas · Voz / Batería / Bajo / Otros (Demucs)", "4")
        self.stem_count.addItem("6 pistas · Añade guitarra y piano", "6")
        stems_row.addWidget(self.stem_count,1)
        form.addLayout(stems_row)
        root.addWidget(source)

        # Banco de stems real del proyecto, compartido por todos los módulos.
        shelf=QFrame(self)
        shelf.setObjectName("panel")
        shelf_layout=QVBoxLayout(shelf)
        shelf_layout.setContentsMargins(11,8,11,9)
        shelf_layout.setSpacing(5)
        header=QHBoxLayout()
        heading=QLabel("STEMS DEL PROYECTO · ARRASTRAR Y PREESCUCHAR")
        heading.setStyleSheet("font-weight:800;color:#e0f8ff;")
        header.addWidget(heading)
        header.addStretch()
        self.stem_update=QPushButton("↻ Actualizar pistas")
        self.stem_update.clicked.connect(self.refresh_project_stems)
        header.addWidget(self.stem_update)
        shelf_layout.addLayout(header)
        self.stem_shelf=StemFileList(self)
        self.stem_shelf.setStyleSheet(
            "QListWidget{background:#04183e;color:#e0f8ff;"
            "border:1px solid #2bb1fc;border-radius:4px;}"
            "QListWidget::item{background:#051e4c;color:#e0f8ff;"
            "padding:6px;border-bottom:1px solid #194763;}"
            "QListWidget::item:selected{background:#0d54d3;color:white;}"
            "QListWidget::item:hover{background:#093d9b;color:white;}")
        self.stem_shelf.setDragEnabled(True)
        self.stem_shelf.setDragDropMode(QAbstractItemView.DragOnly)
        self.stem_shelf.setSelectionMode(QAbstractItemView.SingleSelection)
        self.stem_shelf.setMaximumHeight(160)
        self.stem_shelf.itemSelectionChanged.connect(self.stem_preview_selected)
        self.stem_shelf.itemDoubleClicked.connect(
            lambda item:self.choose_project_stem(Path(item.data(Qt.UserRole))))
        shelf_layout.addWidget(self.stem_shelf)
        row=QHBoxLayout()
        self.stem_listen=QPushButton("▶ Escuchar stem seleccionado")
        self.stem_listen.clicked.connect(self.listen_project_stem)
        row.addWidget(self.stem_listen)
        self.stem_use=QPushButton("Usar este stem →")
        self.stem_use.setObjectName("primary")
        self.stem_use.clicked.connect(lambda:self.choose_project_stem(
            self.selected_project_stem()))
        row.addWidget(self.stem_use)
        row.addStretch()
        shelf_layout.addLayout(row)
        self.stem_drop=StemDropBox(self.handle_stem_drop,self)
        shelf_layout.addWidget(self.stem_drop)
        self.stem_hint=QLabel("Sin pistas separadas. Se mostrarán aquí al terminar una separación.")
        self.stem_hint.setObjectName("muted")
        shelf_layout.addWidget(self.stem_hint)
        root.addWidget(shelf)

        source_actions=QHBoxLayout()
        source_actions.addWidget(QLabel("Pista de audio para escuchar"))
        self.stem_preview_choice=QComboBox()
        self.stem_preview_choice.setMinimumWidth(220)
        self.stem_preview_choice.currentIndexChanged.connect(self.preview_stem)
        source_actions.addWidget(self.stem_preview_choice,1)
        self.preview_external_midi_button=QPushButton("Cargar MIDI para escuchar…")
        self.preview_external_midi_button.clicked.connect(self.preview_external_midi)
        source_actions.addWidget(self.preview_external_midi_button)
        root.addLayout(source_actions)
        self.source_preview=PreviewPlayer("ESCUCHAR ARCHIVO DE ORIGEN",self)
        root.addWidget(self.source_preview)

        config=QFrame()
        config.setObjectName("panel")
        opt=QVBoxLayout(config)
        opt.setContentsMargins(17,14,17,16)
        opt.setSpacing(10)
        mode_header=QHBoxLayout()
        self.automatic=QCheckBox("Modo AUTOMÁTICO (recomendado)")
        self.automatic.setChecked(True)
        self.automatic.toggled.connect(self.on_automatic_changed)
        mode_header.addWidget(self.automatic)
        mode_header.addStretch()
        self.mode_status=QLabel("Selección inteligente de parámetros")
        self.mode_status.setObjectName("status")
        mode_header.addWidget(self.mode_status)
        opt.addLayout(mode_header)

        grid=QFormLayout()
        grid.setSpacing(11)
        self.tempo_auto=QCheckBox("Detectar automáticamente")
        self.tempo_auto.setChecked(True)
        self.tempo_auto.toggled.connect(self.on_tempo_toggle)
        tempo_row=QHBoxLayout()
        self.bpm=SliderNumber(35,300,120,.1,2," BPM")
        self.bpm.setRange(35,300)
        self.bpm.setDecimals(2)
        self.bpm.setSingleStep(.1)
        self.bpm.setValue(120)
        self.bpm.setSuffix(" BPM")
        self.bpm.setEnabled(False)
        tempo_row.addWidget(self.tempo_auto)
        tempo_row.addStretch()
        tempo_row.addWidget(self.bpm)
        tempo_widget=QWidget(); tempo_widget.setLayout(tempo_row)
        grid.addRow("Tempo MIDI",tempo_widget)
        detection_row=QHBoxLayout()
        self.detect_tempo=QPushButton("Analizar BPM")
        self.detect_tempo.clicked.connect(self.analyze_tempo)
        detection_row.addWidget(self.detect_tempo)
        self.tempo_options=QComboBox()
        self.tempo_options.setMinimumWidth(155)
        self.tempo_options.setToolTip("BPM detectado y alternativas a mitad o doble del pulso")
        self.tempo_options.addItem("Candidatos…",None)
        self.tempo_options.currentIndexChanged.connect(self.choose_tempo)
        detection_row.addWidget(self.tempo_options,1)
        self.tap_button=QPushButton("Tap")
        self.tap_button.setToolTip("Marca el pulso varias veces con clics regulares")
        self.tap_button.clicked.connect(self.tap_tempo)
        detection_row.addWidget(self.tap_button)
        detect_holder=QWidget();detect_holder.setLayout(detection_row)
        grid.addRow("Comprobar ritmo",detect_holder)
        self.tempo_quality=QLabel("Analiza la canción o pulsa Tap para corregir el pulso. "
                                  "La mitad/doble velocidad puede ser ambigua.")
        self.tempo_quality.setObjectName("muted")
        self.tempo_quality.setWordWrap(True)
        grid.addRow("",self.tempo_quality)
        self.quant=QComboBox()
        self.quant.addItem("Sin cuantizar (respeta interpretación)", "off")
        for grid_name in ["1/4","1/8","1/16","1/32"]:
            self.quant.addItem("Cuantizar a "+grid_name,grid_name)
        grid.addRow("Cuantización",self.quant)
        self.align_grid=QCheckBox("Alinear automáticamente la rejilla al primer pulso")
        self.align_grid.setChecked(True)
        self.align_grid.setToolTip(
            "Cuando el BPM es automático y se cuantiza, usa la fase del "
            "pulso detectado en lugar de asumir que empieza en 0 segundos.")
        grid.addRow("",self.align_grid)
        opt.addLayout(grid)

        algorithm_profile=QHBoxLayout()
        algorithm_profile.addWidget(QLabel("Precisión del reconocimiento"))
        self.precision_profile=QComboBox()
        self.precision_profile.addItem("Equilibrada (predeterminada)","balanced")
        self.precision_profile.addItem("Estricta · menos notas falsas","strict")
        self.precision_profile.addItem("Sensible · rescatar notas suaves","sensitive")
        self.precision_profile.setToolTip(
            "Ajusta los umbrales de ataque y sustain por instrumento. "
            "Estricta detecta menos notas pero puede perder notas débiles.")
        algorithm_profile.addWidget(self.precision_profile,1)
        opt.addLayout(algorithm_profile)
        refine_row=QHBoxLayout()
        refine_row.addWidget(QLabel("Refinar ataques y notas repetidas"))
        self.refinement=QComboBox(self)
        self.refinement.addItem("Equilibrado · preservar notas suaves","balanced")
        self.refinement.addItem("Rigor alto · filtrar notas débiles","strict")
        self.refinement.addItem("Desactivado · Basic Pitch sin refinado","off")
        self.refinement.setToolTip("Contrasta los eventos con las activaciones reales del modelo. "
            "Separa ataques internos de una nota larga y evita fusionar "
            "dos pulsaciones distintas; en Rigor alto puede perder notas débiles.")
        refine_row.addWidget(self.refinement,1)
        opt.addLayout(refine_row)
        self.piano_specialist=QCheckBox("Usar transcriptor especializado para piano (Transkun V2)")
        self.piano_specialist.setChecked(True)
        self.piano_specialist.setToolTip("Recomendado para pistas de piano separadas; mayor uso de CPU")
        opt.addWidget(self.piano_specialist)

        self.advanced_widget=QFrame()
        self.advanced_widget.setObjectName("inner")
        advanced=QFormLayout(self.advanced_widget)
        advanced.setContentsMargins(14,14,14,14)
        advanced.setSpacing(10)
        self.onset=SliderNumber(.1,.95,.5,.01,2)
        self.onset.setRange(.1,.95);self.onset.setSingleStep(.05);self.onset.setDecimals(2);self.onset.setValue(.5)
        self.onset.setToolTip("Probabilidad mínima para detectar el inicio de una nota")
        advanced.addRow("Sensibilidad de ataque (onset)",self.onset)
        self.frame=SliderNumber(.1,.9,.3,.01,2)
        self.frame.setRange(.1,.9);self.frame.setSingleStep(.05);self.frame.setDecimals(2);self.frame.setValue(.3)
        advanced.addRow("Umbral de nota sostenida",self.frame)
        self.min_duration=SliderNumber(40,2000,120,10,0," ms")
        self.min_duration.setRange(40,2000);self.min_duration.setSingleStep(10)
        self.min_duration.setSuffix(" ms");self.min_duration.setValue(120)
        advanced.addRow("Duración mínima de nota",self.min_duration)
        lowhigh=QHBoxLayout()
        self.low=SliderNumber(21,108,28,1)
        self.high=SliderNumber(21,108,100,1)
        for control in (self.low,self.high):
            control.setMinimumWidth(165)
            control.slider.setMinimumWidth(65)
            control.number.setFixedWidth(75)
        lowhigh.addWidget(QLabel("De"))
        lowhigh.addWidget(self.low)
        lowhigh.addWidget(QLabel("a"))
        lowhigh.addWidget(self.high)
        pitches=QWidget();pitches.setLayout(lowhigh)
        advanced.addRow("Rango de notas MIDI",pitches)
        self.drum=SliderNumber(.06,.8,.35,.01,2)
        self.drum.setDecimals(2);self.drum.setRange(.06,.8);self.drum.setSingleStep(.05);self.drum.setValue(.35)
        self.drum.setToolTip("Un valor bajo detecta más golpes, incluido ruido")
        advanced.addRow("Sensibilidad de golpes de batería",self.drum)
        opt.addWidget(self.advanced_widget)
        refinement=QFormLayout()
        self.min_velocity=SliderNumber(0,127,0,1)
        self.min_velocity.setRange(0,127)
        self.min_velocity.setValue(0)
        self.min_velocity.setToolTip("Descartar notas MIDI con velocidad inferior al valor elegido; 0 lo desactiva.")
        refinement.addRow("Filtro de notas débiles",self.min_velocity)
        self.merge_gap=SliderNumber(0,250,0,5,0," ms")
        self.merge_gap.setRange(0,250)
        self.merge_gap.setSingleStep(5)
        self.merge_gap.setSuffix(" ms")
        self.merge_gap.setValue(0)
        self.merge_gap.setToolTip("Une fragmentos muy próximos de una misma altura. 0 desactiva.")
        refinement.addRow("Unir microcortes de notas",self.merge_gap)
        self.note_shift=SliderNumber(-250,250,0,5,0," ms")
        self.note_shift.setRange(-250,250)
        self.note_shift.setSingleStep(5)
        self.note_shift.setSuffix(" ms")
        refinement.addRow("Ajuste fino de ataques",self.note_shift)
        self.grid_offset=SliderNumber(-400,400,0,5,0," ms")
        self.grid_offset.setRange(-400,400)
        self.grid_offset.setSingleStep(5)
        self.grid_offset.setSuffix(" ms")
        self.grid_offset.setToolTip("Desplaza la rejilla al cuantizar sin mover el audio original.")
        refinement.addRow("Desplazar rejilla MIDI",self.grid_offset)
        opt.addLayout(refinement)
        presets={
            "Equilibrado":{"automatic":True,"precision_profile":"balanced",
                "note_refinement":"balanced",
                "quantize":"off","min_velocity":0,"merge_gap_ms":0,
                "note_shift_ms":0,"grid_offset_ms":0},
            "Melodía precisa":{"automatic":True,"precision_profile":"strict",
                "note_refinement":"strict",
                "quantize":"off","min_velocity":50,"merge_gap_ms":25},
            "Notas suaves":{"automatic":True,"precision_profile":"sensitive",
                "note_refinement":"balanced",
                "quantize":"off","min_velocity":0,"merge_gap_ms":35},
            "Piano polifónico":{"automatic":True,"precision_profile":"balanced",
                "piano_specialist":True,"quantize":"off","min_pitch":21,"max_pitch":108},
            "Ritmo cuantizado":{"automatic":True,"precision_profile":"balanced",
                "quantize":"1/16","auto_grid_alignment":True,
                "note_shift_ms":0}}
        # Los presets integrados son resultados repetibles: incluyen
        # TODOS los parámetros que ahora actúan incluso en Automático.
        defaults={
            "onset":.5,"frame":.3,"min_length_ms":120,
            "min_pitch":28,"max_pitch":100,"drum_sensitivity":.35,
            "min_velocity":0,"merge_gap_ms":0,"note_shift_ms":0,
            "grid_offset_ms":0,"auto_grid_alignment":True,
            "precision_profile":"balanced","note_refinement":"balanced",
            "quantize":"off","automatic":True}
        for preset in presets.values():
            full=dict(defaults)
            full.update(preset)
            preset.clear()
            preset.update(full)
        # Los dos ajustes guardados por el usuario pasan a ser presets de
        # serie INMUTABLES; prevalecen sus 20 parámetros exactos sobre
        # los valores generales del motor.
        presets={**USER_APPROVED_MIDI_PRESETS,**presets}
        self.presets=PresetStrip("audio_a_midi",presets,
                                 self.parameter_snapshot,self.apply_parameters,self)
        root.insertWidget(2,self.presets)
        self.automatic_info=QLabel(
            "Automático: los umbrales del instrumento son la base y los "
            "deslizantes de ataque, sostenido y duración los corrigen. "
            "El refinado separa ataques repetidos dentro de notas largas. "
            "La cuantización es opcional y no mejora la detección de notas.")
        self.automatic_info.setObjectName("muted")
        self.automatic_info.setWordWrap(True)
        opt.addWidget(self.automatic_info)
        root.addWidget(config)

        outpanel=QFrame();outpanel.setObjectName("panel")
        outlay=QFormLayout(outpanel)
        outlay.setContentsMargins(17,14,17,14)
        self.outdir=QLineEdit(str(MIDI_DIR))
        output_row=QHBoxLayout()
        output_row.addWidget(self.outdir,1)
        choose=QPushButton("Carpeta…")
        choose.clicked.connect(self.pick_dest)
        output_row.addWidget(choose)
        holder=QWidget();holder.setLayout(output_row)
        outlay.addRow("Destino",holder)
        self.filename=QLineEdit("Transcripcion")
        outlay.addRow("Nombre del MIDI",self.filename)
        root.addWidget(outpanel)

        actions=QHBoxLayout()
        self.go=QPushButton("Convertir a MIDI")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.start_conversion)
        actions.addWidget(self.go)
        self.cancel=QPushButton("Cancelar")
        self.cancel.setObjectName("stop")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_conversion)
        actions.addWidget(self.cancel)
        self.play=QPushButton("Escuchar MIDI")
        self.play.clicked.connect(self.listen)
        actions.addWidget(self.play)
        self.open=QPushButton("Abrir carpeta")
        self.open.clicked.connect(self.open_output)
        actions.addWidget(self.open)
        root.addLayout(actions)
        browser_actions=QHBoxLayout()
        self.editor_button=QPushButton("Editar MIDI en Piano Roll…")
        self.editor_button.setObjectName("primary")
        self.editor_button.clicked.connect(self.open_editor)
        browser_actions.addWidget(self.editor_button)
        self.library_button=QPushButton("Ver conversiones MIDI…")
        self.library_button.clicked.connect(self.open_library)
        browser_actions.addWidget(self.library_button)
        browser_actions.addStretch()
        root.addLayout(browser_actions)

        self.status=QLabel("Listo para transcribir. Se recomienda separar los instrumentos antes de convertirlos.")
        self.status.setObjectName("status");self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.progress=QProgressBar()
        self.progress.setRange(0,100);self.progress.setValue(0)
        root.addWidget(self.progress)

        self.result=QTableWidget(0,3)
        self.result.setHorizontalHeaderLabels(["Pista / instrumento","Notas detectadas","Método"])
        self.result.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.result.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.result.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.result.verticalHeader().setVisible(False)
        self.result.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result.setMinimumHeight(110)
        root.addWidget(self.result,1)
        self.output_preview=PreviewPlayer("ESCUCHAR MIDI CONVERTIDO",self)
        self.source_preview.exclusive_with(self.output_preview)
        self.output_preview.exclusive_with(self.source_preview)
        root.addWidget(self.output_preview)
        self.chord_preview=PreviewPlayer("ESCUCHAR MIDI DE ACORDES · ARCHIVO INDEPENDIENTE",self)
        self.chord_preview.set_compact(True)
        self.chord_preview.setVisible(False)
        self.chord_preview.exclusive_with(self.output_preview)
        self.output_preview.exclusive_with(self.chord_preview)
        root.addWidget(self.chord_preview)
        self.chord_status=QLabel("Detector de acordes desactivado.")
        self.chord_status.setObjectName("muted")
        self.chord_status.setWordWrap(True)
        root.addWidget(self.chord_status)
        self.chord_edit=QPushButton("Editar acordes en Piano Roll")
        self.chord_edit.setVisible(False)
        self.chord_edit.clicked.connect(self.open_chord_editor)
        root.addWidget(self.chord_edit)

        activity=QLabel("REGISTRO DE TRANSCRIPCIÓN")
        activity.setObjectName("section")
        root.addWidget(activity)
        self.log=QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(95)
        root.addWidget(self.log)

        small=QLabel("El MIDI contiene eventos de notas, no audio. "
                     "Los resultados son estimaciones y se pueden editar después en un secuenciador MIDI.")
        small.setObjectName("muted");small.setWordWrap(True)
        root.addWidget(small)
        self.form_tabs=QTabWidget(self)
        self.form_tabs.setDocumentMode(True)
        self.form_tabs.addTab(source,"Fuente")
        self.form_tabs.addTab(config,"Parámetros")
        self.form_tabs.addTab(outpanel,"Destino")
        from ui_responsive import scroll_tab_pages
        scroll_tab_pages(self.form_tabs)
        self.form_tabs.currentChanged.connect(self.resize_form_tabs)
        root.insertWidget(3,self.form_tabs)
        # La bandeja queda sobre las pestañas Fuente/Parámetros/Destino:
        # incluso al editar parámetros se ven las pistas y el cajón MIDI.
        root.removeWidget(shelf)
        root.insertWidget(3,shelf)
        self.resize_form_tabs(0)
        self.on_folder_toggle(False)

    def resize_form_tabs(self,index):
        # No reservar un gran espacio vacío cuando solo se ve Fuente.
        # Parámetros dispone de más altura para sus controles numéricos.
        # La zona avanzada tiene cinco filas de deslizantes dobles.
        # Nunca comprimirlas hasta recortar sus valores editables.
        # Cada página tiene su propio scroll: 820px de controles avanzados
        # nunca deben comprimirse dentro de una altura fija sin desplazamiento.
        self.form_tabs.setFixedHeight({0:365,1:465,2:235}.get(index,365))

    def on_folder_toggle(self,enabled):
        self.audio_path.setEnabled(not enabled)
        self.file_button.setEnabled(not enabled)
        self.folder_path.setEnabled(enabled)
        self.folder_button.setEnabled(enabled)
        self.auto_separate.setEnabled(not enabled)
        self.detect_chords.setEnabled(not enabled)
        self.detect_chords.setToolTip("Los acordes se analizan a partir de un archivo "
            "de audio individual, no de una carpeta de stems." if enabled else
            "Detectar acordes en el audio y exportarlos como MIDI independiente.")
        self.stem_count.setEnabled(not enabled)
        self.stem_preview_choice.setEnabled(enabled)
        if not enabled:
            filename=Path(self.audio_path.text())
            if filename.is_file() and filename.suffix.lower() not in (".mid",".midi",".kar"):
                self.source_preview.load(filename)
        elif self.folder_path.text() and Path(self.folder_path.text()).is_dir():
            self.refresh_folder_previews(Path(self.folder_path.text()))

    def refresh_folder_previews(self, directory):
        self.stem_preview_choice.blockSignals(True)
        self.stem_preview_choice.clear()
        from audio_import import supported_candidate
        for file in sorted(Path(directory).iterdir()):
            if supported_candidate(file) and not file.name.lower().startswith(("mezcla_","_")):
                self.stem_preview_choice.addItem(file.name,str(file))
        self.stem_preview_choice.blockSignals(False)
        if self.stem_preview_choice.count():
            self.stem_preview_choice.setCurrentIndex(0)
            if self.use_folder.isChecked():
                self.preview_stem(0)

    def preview_stem(self,index):
        if index < 0 or not self.use_folder.isChecked():
            return
        path=self.stem_preview_choice.itemData(index)
        if path and Path(path).is_file():
            self.output_preview.stop()
            self.source_preview.load(path)

    def preview_external_midi(self):
        filename,_=file_dialogs.get_open_file_name(self,
             "Selecciona un MIDI para escucharlo",
             str(ROOT / "midi_generados"),
             "Archivos MIDI (*.mid *.midi *.kar)")
        if filename:
            self.output_preview.stop()
            self.source_preview.load(filename)

    def on_automatic_changed(self, automatic):
        # Los controles manuales también ajustan el modo Automático:
        # ocultarlos antes hacía parecer que sus valores se ignoraban.
        self.advanced_widget.setVisible(True)
        self.precision_profile.setEnabled(automatic)
        self.mode_status.setText(
            "Umbrales por instrumento + deslizantes"
            if automatic else "Umbrales manuales exactos")
        self.precision_profile.setToolTip(
            "En modo automático el perfil es una base por instrumento, "
            "y los deslizantes corrigen esa base. En modo manual los "
            "valores indicados se aplican directamente.")

    def on_tempo_toggle(self, enabled):
        self.bpm.setEnabled(not enabled)

    def choose_tempo(self,index):
        bpm=self.tempo_options.itemData(index)
        if bpm is not None:
            self.tempo_auto.setChecked(False)
            self.bpm.setValue(float(bpm))
            self.tempo_quality.setText(
                f"BPM elegido: {float(bpm):.2f}. Se usará en la siguiente conversión.")

    def tap_tempo(self):
        now=time.monotonic()
        self._tempo_taps=[t for t in self._tempo_taps if now-t<5.5]
        self._tempo_taps.append(now)
        if len(self._tempo_taps)<3:
            self.tempo_quality.setText("Marca el pulso al menos tres veces…")
            return
        intervals=[b-a for a,b in zip(self._tempo_taps,self._tempo_taps[1:])
                   if .2<=b-a<=1.8]
        if len(intervals)<2:return
        intervals.sort()
        median=intervals[len(intervals)//2]
        value=min(300.,max(35.,60./median))
        self.tempo_auto.setChecked(False)
        self.bpm.setValue(value)
        self.tempo_options.blockSignals(True)
        self.tempo_options.clear()
        self.tempo_options.addItem(f"{value:.2f} BPM · Tap",value)
        self.tempo_options.blockSignals(False)
        self.tempo_quality.setText(f"Tap tempo: {value:.2f} BPM · "
                                   f"{len(intervals)} intervalos")

    def analyze_tempo(self):
        if self.tempo_job and self.tempo_job.state()!=QProcess.NotRunning:
            return
        path=None
        if self.use_folder.isChecked():
            root=Path(self.folder_path.text())
            if root.is_dir():
                from audio_import import supported_candidate
                sources=[p for p in root.iterdir() if supported_candidate(p)]
                if sources:
                    path=next((p for p in sources if "drum" in p.stem.lower()),
                              sources[0])
        else:
            path=Path(self.audio_path.text().strip()).expanduser()
        if not path or not path.is_file():
            QMessageBox.information(self,"Analizar tempo",
                "Importa antes un archivo de audio o una carpeta de instrumentos.")
            return
        self.detect_tempo.setEnabled(False)
        self.go.setEnabled(False)
        self.tempo_quality.setText("Analizando pulsos en distintos fragmentos de la canción…")
        job=QProcess(self)
        job.setProcessChannelMode(QProcess.MergedChannels)
        job.setWorkingDirectory(str(ROOT))
        self.tempo_job=job
        def finish(rc,status):
            output=bytes(job.readAllStandardOutput()).decode("utf-8","replace").strip()
            self.tempo_job=None
            job.deleteLater()
            self.detect_tempo.setEnabled(True)
            if self.process is None:
                self.go.setEnabled(True)
            try:
                result=json.loads(output.splitlines()[-1])
                if rc or result.get("error"):
                    raise ValueError(result.get("error",output[-200:]))
                bpm=result.get("bpm")
                if bpm is None:
                    self.tempo_quality.setText(result.get("warning","No se detectó el pulso."))
                    return
                self.tempo_options.blockSignals(True)
                self.tempo_options.clear()
                for i,val in enumerate(result.get("alternatives",[bpm])):
                    self.tempo_options.addItem(
                        f"{float(val):.2f} BPM"+(" · principal" if i==0 else
                          " · mitad/doble"),float(val))
                self.tempo_options.setCurrentIndex(0)
                self.tempo_options.blockSignals(False)
                self.tempo_auto.setChecked(False)
                self.bpm.setValue(float(bpm))
                # Ajuste fino de fase: normalizar el primer pulso dentro
                # de medio tiempo para evitar offsets de varios segundos.
                seconds_per_beat=60./float(bpm)
                raw_offset=float(result.get("beat_offset",0))
                grid_phase=((raw_offset+seconds_per_beat/2)%seconds_per_beat
                              -seconds_per_beat/2)
                self.grid_offset.setValue(round(grid_phase*1000))
                conf=int(float(result.get("confidence",0))*100)
                note=result.get("warning","")
                self.tempo_quality.setText(
                    f"Tempo estimado: {float(bpm):.2f} BPM · "
                    f"coherencia {conf}% · {result.get('segments',1)} fragmentos. "
                    +note)
                self.log.appendPlainText("Analizador: "+self.tempo_quality.text())
            except (IndexError,ValueError,TypeError,json.JSONDecodeError) as exc:
                self.tempo_quality.setText("No se pudo analizar el tempo: "+str(exc))
        job.finished.connect(finish)
        def tempo_start_error(error):
            if error==QProcess.FailedToStart:
                self.tempo_quality.setText(
                    "Error al iniciar el analizador: "+job.errorString())
                self.tempo_job=None
                self.detect_tempo.setEnabled(True)
                if self.process is None:self.go.setEnabled(True)
        job.errorOccurred.connect(tempo_start_error)
        job.start(str(PYTHON),[str(TEMPO_ENGINE),"--source",str(path)])

    def project_stem_paths(self):
        if self.workspace is None:return []
        from task_staging import project_audio_sources
        from project_flow import approved_map
        candidates=([Path(path) for path in approved_map(self.workspace.main).values()]
                    +project_audio_sources(
                        getattr(self.workspace.main,"project_dir",None),
                        ("separaciones","bateria","vocal")))
        return sorted({Path(p).resolve() for p in candidates
                       if Path(p).is_file()},key=lambda p:(p.name.casefold(),str(p)))

    def selected_project_stem(self):
        item=self.stem_shelf.currentItem()
        return Path(item.data(Qt.UserRole)) if item else None

    def refresh_project_stems(self):
        previous=self.selected_project_stem()
        paths=self.project_stem_paths()
        self.stem_shelf.blockSignals(True)
        self.stem_shelf.clear()
        for path in paths:
            from studio_home import StudioHome
            group=StudioHome._stem_for(None,path)
            item=QListWidgetItem(f"♫  {group:9s}  ·  {path.name}")
            item.setData(Qt.UserRole,str(path))
            item.setToolTip(str(path))
            self.stem_shelf.addItem(item)
            if previous==path:self.stem_shelf.setCurrentItem(item)
        self.stem_shelf.blockSignals(False)
        self.stem_hint.setText(
            f"{len(paths)} pistas auténticas del proyecto. "
            "Selecciona una para escuchar o arrástrala al cajón."
            if paths else "Sin stems de este proyecto. Separa una grabación "
            "para ver aquí cada instrumento.")
        self.stem_listen.setEnabled(bool(paths))
        self.stem_use.setEnabled(bool(paths))

    def stem_preview_selected(self):
        path=self.selected_project_stem()
        if path and path.is_file():
            self.source_preview.load(path,autoplay=False)

    def listen_project_stem(self):
        path=self.selected_project_stem()
        if path and path.resolve() in self.project_stem_paths():
            self.source_preview.load(path,autoplay=True)

    def choose_project_stem(self,path):
        if path is None:return False
        file=Path(path).resolve()
        if file not in self.project_stem_paths():return False
        self.on_import_file(str(file))
        # Es una pista separada: evitar separar otra vez.
        self.auto_separate.setChecked(False)
        self.use_folder.setChecked(False)
        self.stem_drop.caption.setText("✓ "+file.name+" · listo para convertir")
        self.stem_hint.setText("Pista seleccionada para conversión individual: "+file.name)
        return self.audio_path.text()==str(file)

    def handle_stem_drop(self,action,path):
        if action=="can":
            return Path(path).resolve() in self.project_stem_paths()
        if action=="choose":
            return self.choose_project_stem(path)
        return False

    def pick_audio(self):
        name=pick_audio(self, ROOT/"grabaciones")
        if name:self.on_import_file(name)

    def sync_source_preview(self):
        source=Path(self.audio_path.text().strip()).expanduser()
        if source.is_file() and self.source_preview.current_file!=str(source.resolve()):
            self.on_import_file(str(source))

    def on_import_file(self, name):
        info,label=check_and_describe(self,name)
        if info:
            self.audio_path.setText(info["path"])
            self.use_folder.setChecked(False)
            self.source_preview.load(info["path"])
            if is_separated_stem(info["path"]):
                self.auto_separate.setChecked(False)
                self.audio_info.setText(label+" · Instrumento ya separado: "
                    "transcripción directa, sin repetir Demucs.")
            else:
                self.audio_info.setText(label)
            self.save_preferences()
        else:
            self.audio_path.clear()
            self.audio_info.setText("El archivo no contiene audio decodificable.")

    def on_import_folder(self, folder):
        path=Path(folder)
        if not path.is_dir():
            QMessageBox.warning(self,"Carpeta inválida","No existe la carpeta seleccionada.")
            return
        paths=[p for p in path.iterdir() if supported_candidate(p) and not p.name.startswith("_")]
        if not paths:
            QMessageBox.warning(self,"Sin audio","No hay archivos de audio o vídeo reconocidos en la carpeta.")
            return
        self.folder_path.setText(str(path))
        self.use_folder.setChecked(True)
        self.refresh_folder_previews(path)
        self.audio_info.setText(f"Carpeta importada: {len(paths)} archivo(s) candidato(s); los códecs se validarán al convertir.")
        self.save_preferences()

    def pick_folder(self):
        directory=file_dialogs.get_existing_directory(self,"Carpeta de stems",str(ROOT/"pistas_separadas"))
        if directory:
            self.on_import_folder(directory)

    def pick_dest(self):
        if self.embedded and self.workspace is not None and self.workspace.main.project_dir:
            QMessageBox.information(self,"Destino del proyecto",
                "Los MIDI definitivos se guardan directamente en audio_a_midi "
                "del proyecto, sin carpetas adicionales por conversión.")
            return
        d=file_dialogs.get_existing_directory(self,"Carpeta de MIDI",self.outdir.text())
        if d:self.outdir.setText(d)

    def settings(self):
        path=self.audio_path.text().strip()
        folder=self.folder_path.text().strip()
        if self.use_folder.isChecked():
            if not Path(folder).is_dir():
                raise ValueError("Selecciona una carpeta de pistas válida")
            files=[]
        else:
            if not Path(path).is_file():
                raise ValueError("Selecciona un archivo de audio válido")
            probe_audio(path)
            files=[path]
            folder=None
        if self.low.value() > self.high.value():
            raise ValueError("El mínimo de nota MIDI no puede superar el máximo")
        out=self.outdir.text().strip()
        if not out:raise ValueError("Elige una carpeta de destino")
        name=re.sub(r'[^A-Za-z0-9._-]+','_',self.filename.text().strip()) or "Transcripcion"
        return {
            "files":files,"folder":folder,"automatic":self.automatic.isChecked(),
            "tempo_auto":self.tempo_auto.isChecked(),"bpm":self.bpm.value(),
            "quantize":self.quant.currentData(),"onset":self.onset.value(),
            "frame":self.frame.value(),"min_length_ms":self.min_duration.value(),
            "min_pitch":self.low.value(),"max_pitch":self.high.value(),
            "drum_sensitivity":self.drum.value(),
            "precision_profile":self.precision_profile.currentData(),
            "note_refinement":self.refinement.currentData(),
            "min_velocity":self.min_velocity.value(),
            "merge_gap_ms":self.merge_gap.value(),
            "note_shift_ms":self.note_shift.value(),
            "grid_offset_ms":self.grid_offset.value(),
            "auto_grid_alignment":self.align_grid.isChecked(),
            "piano_specialist":self.piano_specialist.isChecked(),
            "separate_first":(self.auto_separate.isChecked()
                   and not self.use_folder.isChecked()
                   and not is_separated_stem(path)),
            "separation_stems":self.stem_count.currentData(),
            "detect_chords":self.detect_chords.isChecked(),
            "output_dir":out,"name":name,
        }

    def set_busy(self,busy):
        self.presets.setEnabled(not busy)
        self.go.setEnabled(not busy and self.tempo_job is None)
        self.cancel.setEnabled(busy)
        self.use_folder.setEnabled(not busy)
        self.automatic.setEnabled(not busy)
        self.tempo_auto.setEnabled(not busy)
        self.detect_tempo.setEnabled(not busy and self.tempo_job is None)
        self.tap_button.setEnabled(not busy)
        self.tempo_options.setEnabled(not busy)
        self.piano_specialist.setEnabled(not busy)
        self.auto_separate.setEnabled(not busy and not self.use_folder.isChecked())
        self.detect_chords.setEnabled(not busy and not self.use_folder.isChecked())
        self.stem_count.setEnabled(not busy and not self.use_folder.isChecked())
        self.audio_path.setEnabled(not busy and not self.use_folder.isChecked())
        self.file_button.setEnabled(not busy and not self.use_folder.isChecked())
        self.folder_path.setEnabled(not busy and self.use_folder.isChecked())
        self.folder_button.setEnabled(not busy and self.use_folder.isChecked())
        self.outdir.setEnabled(not busy)
        self.filename.setEnabled(not busy)
        if busy:self.progress.setRange(0,0)
        else:self.progress.setRange(0,100)

    def start_conversion(self):
        if self.process is not None and self.process.state()!=QProcess.NotRunning:
            return
        if not PYTHON.is_file() or not ENGINE.is_file():
            QMessageBox.warning(self,"Motor no disponible","Falta el motor de conversión MIDI.")
            return
        try:
            cfg=self.settings()
            if self.embedded:
                if not self.workspace.prepare_task("midi"):
                    return
                cfg["output_dir"]=str(self.workspace.midi_run_folder)
            if self.embedded and self.workspace is not None and self.workspace.main.project_dir:
                # La configuración efímera pertenece a la toma MIDI actual.
                self.job_file=self.workspace.midi_run_folder/"config_job.json"
            else:
                MIDI_DIR.mkdir(exist_ok=True,parents=True)
                self.job_file=MIDI_DIR/("config_job_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f")+".json")
            self.job_file.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding="utf-8")
            self.save_preferences()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Parámetros",str(exc))
            return
        self.output=None
        self.chord_output=None
        self.chord_preview.clear()
        self.chord_preview.setVisible(False)
        self.chord_edit.setVisible(False)
        self._chord_requested=bool(cfg["detect_chords"] and len(cfg["files"])==1
                                    and not cfg["folder"])
        self._chord_source=(cfg["files"][0] if self._chord_requested else None)
        self.chord_status.setText("Se analizarán acordes del audio tras la transcripción."
            if self._chord_requested else "Detector de acordes desactivado.")
        self.output_preview.clear()
        self.cancelled=False
        self.result.setRowCount(0)
        self.log.clear()
        self.buf=""
        self.start_time=__import__("time").monotonic()
        self.set_busy(True)
        self.status.setText("Iniciando transcripción local…")
        proc=QProcess(self)
        env=QProcessEnvironment.systemEnvironment()
        env.insert("OMP_NUM_THREADS","6")
        env.insert("OPENBLAS_NUM_THREADS","4")
        env.insert("XDG_CACHE_HOME",str(ROOT/"cache_ia"))
        env.insert("PYTHONUNBUFFERED","1")
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self.read_output)
        proc.finished.connect(self.on_conversion_finished)
        proc.errorOccurred.connect(self.on_process_error)
        proc.setWorkingDirectory(str(ROOT))
        self.process=proc
        proc.start(str(PYTHON),[str(ENGINE),"--config",str(self.job_file)])
        self.log.appendPlainText("Modo: "+("AUTOMÁTICO" if cfg["automatic"] else "MANUAL"))
        self.log.appendPlainText("Origen: "+str(cfg["folder"] or cfg["files"][0]))
        self.log.appendPlainText("Salida: "+cfg["output_dir"])

    def read_output(self):
        if self.process is None:return
        txt=bytes(self.process.readAllStandardOutput()).decode("utf-8","replace")
        self.buf+=txt.replace("\r","\n")
        lines=self.buf.split("\n")
        self.buf=lines.pop()
        for line in lines:
            if line.startswith("MIDI_PROGRESS "):
                try:self.handle_progress(json.loads(line[14:]))
                except (json.JSONDecodeError,ValueError) as exc:self.log.appendPlainText("Progreso inválido: "+str(exc))
            elif line.strip():
                self.log.appendPlainText(line[-700:])

    def handle_progress(self,data):
        status=data.get("stage")
        if status=="start":
            self.stats=[]
            self.status.setText(f"Analizando {data.get('tracks')} pista(s)…")
        elif status=="importing":
            self.status.setText("Importando y decodificando: " + Path(data.get("source","audio")).name)
            self.log.appendPlainText("Decodificando a FLAC 24 bits: " + str(data.get("source","")))
        elif status=="separating":
            self.status.setText(f"Separando instrumentos automáticamente ({data.get('model')})…")
            self.log.appendPlainText("Generando pistas de instrumentos en: "+str(data.get("folder")))
        elif status=="separation_done":
            self.status.setText(f"{data.get('files')} pistas separadas; comienza la transcripción MIDI")
            self.log.appendPlainText(f"Separación completada ({data.get('files')} pistas)")
        elif status=="tempo":
            bpm=data.get("bpm")
            if bpm:
                self.bpm.setValue(float(bpm))
            conf=data.get("confidence")
            manual=data.get("manual",False)
            label="manual" if manual else (
                f"coherencia {round(float(conf)*100)}%"
                if conf is not None else "estimado")
            text=f"Tempo: {bpm} BPM ({label})"
            self.log.appendPlainText(text)
            if data.get("warning"):
                self.log.appendPlainText(data["warning"])
            if not manual:
                self.tempo_quality.setText(text+" · "+data.get("warning",""))
        elif status=="loading_model":
            self.status.setText(data.get("message","Cargando modelo neuronal…"))
        elif status=="processing":
            self.status.setText(f"Pista {data.get('current')}/{data.get('total')}: {data.get('name')}")
        elif status=="refinement":
            self.log.appendPlainText(
                f"{data.get('name','Pista')}: refinado {data.get('mode')}, "
                f"{data.get('input_notes')}→{data.get('output_notes')} "
                f"eventos (divisiones: {data.get('splits')}; "
                f"descartadas: {data.get('weak_rejected')}).")
        elif status=="effective_thresholds":
            self.log.appendPlainText(
                f"{data.get('name')}: umbrales efectivos "
                f"ataque={data.get('onset')}, sostenido={data.get('frame')}, "
                f"mínima={data.get('min_length_ms')} ms · "
                f"notas {data.get('min_pitch')}–{data.get('max_pitch')}")
        elif status=="track_done":
            n=data.get("notes",0)
            i=data.get("current",1)
            self.log.appendPlainText(f"{data.get('name')}: {n} notas")
            total=int(data.get("total",1))
            self.progress.setRange(0,total)
            self.progress.setValue(int(i))
            self.result.setRowCount(self.result.rowCount()+1)
            row=self.result.rowCount()-1
            self.result.setItem(row,0,QTableWidgetItem(str(data.get("name"))))
            self.result.setItem(row,1,QTableWidgetItem(str(n)))
            self.result.setItem(row,2,QTableWidgetItem(str(data.get("method","IA"))))
        elif status=="finished":
            self.output=Path(data.get("output",""))
            if self.output.is_file():
                self.output_preview.load(self.output)
            self.status.setText(f"MIDI terminado: {data.get('notes')} notas · {data.get('tracks')} pistas · {data.get('bpm')} BPM")
            self.log.appendPlainText("GUARDADO: "+str(self.output))
        elif status=="error":
            self.status.setText("Error: "+str(data.get("message","Error de transcripción")))
            self.log.appendPlainText(self.status.text())
        elif status=="info":
            self.log.appendPlainText(data.get("message",""))

    def on_conversion_finished(self,code,status):
        self.read_output()
        proc=self.process
        if proc:
            proc.deleteLater()
        self.process=None
        if self.buf.strip():
            line=self.buf.strip()
            if line.startswith("MIDI_PROGRESS "):
                try:self.handle_progress(json.loads(line[14:]))
                except (ValueError,json.JSONDecodeError):self.log.appendPlainText(line)
            else:self.log.appendPlainText(line)
        self.buf=""
        self.set_busy(False)
        if self.job_file and self.job_file.exists():
            try:self.job_file.unlink()
            except OSError:pass
        if self.cancelled:
            self.status.setText("Conversión cancelada; el audio original no se ha modificado.")
        elif code!=0 or status!=QProcess.NormalExit or self.output is None or not self.output.is_file():
            self.status.setText("Error al generar el MIDI. Revisa el registro de actividad.")
        else:
            self.progress.setRange(0,100);self.progress.setValue(100)
            if self.embedded:
                self.workspace.on_midi_completed(self.output)
            else:
                from bibliotecas import register_result
                register_result("midi",self.output)
                QTimer.singleShot(150,self.open_library)
            if self._chord_requested and self._chord_source:
                self.start_chord_analysis()

    def start_chord_analysis(self):
        """Análisis aparte; la transcripción principal ya está guardada."""
        if not CHORD_ENGINE.is_file() or not PYTHON.is_file():
            self.chord_status.setText("No está disponible el detector de acordes.")
            return
        source=Path(self._chord_source)
        if not source.is_file() or not self.output or not self.output.is_file():
            self.chord_status.setText("No hay fuente válida para detectar acordes.")
            return
        # Nunca pisar el MIDI musical ni una copia existente.
        target=self.output.with_name(self.output.stem+"_Acordes.mid")
        self.set_busy(True)
        self.chord_status.setText("Analizando armonía del audio, sin modificar el original…")
        proc=QProcess(self)
        proc.setWorkingDirectory(str(ROOT))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(self.on_chord_analysis_finished)
        proc.errorOccurred.connect(self.on_process_error)
        self.process=proc
        proc.start(str(PYTHON),[str(CHORD_ENGINE),"--audio",str(source),
                   "--midi",str(self.output),"--output",str(target)])

    def on_chord_analysis_finished(self,code,status):
        proc=self.process
        output=bytes(proc.readAllStandardOutput()).decode("utf-8","replace") if proc else ""
        if proc:proc.deleteLater()
        self.process=None
        self.set_busy(False)
        try:result=json.loads(output.strip().splitlines()[-1])
        except (ValueError,IndexError):result={"status":"error","message":output[-300:]}
        if self.cancelled:
            self.chord_status.setText("Análisis de acordes cancelado; se conserva el MIDI de notas.")
            return
        if code!=0 or status!=QProcess.NormalExit or result.get("status")=="error":
            self.chord_status.setText("No se pudo analizar acordes: "+
                                      result.get("message","Comprueba el registro."))
            self.log.appendPlainText(self.chord_status.text())
            return
        if result.get("status")=="no_chords":
            self.chord_status.setText(result.get("message","No se encontraron acordes claros."))
            self.log.appendPlainText(self.chord_status.text())
            return
        file=Path(result.get("output",""))
        if not file.is_file():
            self.chord_status.setText("No existe el MIDI de acordes generado.")
            return
        self.chord_output=file
        self.chord_preview.load(file)
        self.chord_preview.setVisible(True)
        self.chord_edit.setVisible(True)
        self.chord_status.setText(
            f"{result.get('segments',0)} acordes detectados · MIDI independiente: {file.name}")
        self.log.appendPlainText(self.chord_status.text())
        if self.embedded:
            storage=self.workspace.midi_storage
            from task_staging import inside
            if storage.folder and inside(file,storage.folder):
                if file not in storage.items:
                    storage.items.append(file)
                if storage.versions:
                    current=storage.versions[-1]["items"]
                    if file not in current:current.append(file)
                storage.manifest()
                self.workspace.midi_results.populate()
        else:
            from bibliotecas import register_result
            register_result("midi",file)

    def open_chord_editor(self):
        if not self.chord_output or not self.chord_output.is_file():return
        if self.workspace is not None:
            self.workspace.show_piano_roll(self.chord_output)
        else:
            from piano_roll import PianoRollDialog
            editor=PianoRollDialog(self.chord_output,self)
            editor.show()
            self._chord_editor=editor

    def on_process_error(self,error):
        if error==QProcess.FailedToStart and self.process is not None:
            failed=self.process
            self.status.setText("No se pudo iniciar el motor MIDI")
            self.log.appendPlainText(failed.errorString())
            # La señal finished() no llega en FailedToStart.
            QTimer.singleShot(0, lambda: self.on_conversion_finished(-1,QProcess.CrashExit)
                              if self.process is failed else None)

    def cancel_conversion(self):
        if self.process and self.process.state()!=QProcess.NotRunning:
            self.cancelled=True
            self.status.setText("Cancelando…")
            p=self.process
            p.terminate()
            def force_stop():
                try:
                    if p.state()!=QProcess.NotRunning:
                        p.kill()
                except RuntimeError:
                    pass  # El proceso ya fue eliminado por Qt.
            QTimer.singleShot(3000,force_stop)

    def listen(self):
        if not self.output or not self.output.exists():
            QMessageBox.information(self,"Sin MIDI","Primero convierte un archivo a MIDI, o usa Cargar MIDI para escuchar.")
            return
        if self.output_preview.current_file != str(self.output.resolve()):
            self.output_preview.load(self.output,autoplay=True)
        else:
            self.output_preview.play_pause()
        self.log.appendPlainText("Previsualización del MIDI convertido mediante TiMidity.")

    def open_editor(self):
        if self.embedded:
            self.workspace.show_piano_roll(self.output)
            return
        if not self.output or not self.output.is_file():
            QMessageBox.information(self,"Piano Roll",
                "Primero convierte un audio a MIDI o abre un archivo desde la biblioteca.")
            return
        from piano_roll import PianoRollDialog
        if getattr(self,"piano_roll",None) is not None:
            self.piano_roll.show()
            self.piano_roll.raise_();self.piano_roll.activateWindow()
            return
        editor=PianoRollDialog(self.output,self)
        self.piano_roll=editor
        editor.destroyed.connect(lambda: setattr(self,"piano_roll",None))
        editor.show()

    def open_library(self):
        if self.embedded:
            self.workspace.focus_midi_results()
            return
        from bibliotecas import ResultsWindow
        if getattr(self,"library_window",None) is not None:
            self.library_window.focus_file=self.output
            self.library_window.refresh()
            self.library_window.show()
            self.library_window.raise_()
            return
        window=ResultsWindow("midi",self,focus_file=self.output)
        self.library_window=window
        window.destroyed.connect(lambda: setattr(self,"library_window",None))
        window.show()

    def open_output(self):
        path=self.output.parent if self.output else Path(self.outdir.text()).expanduser()
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self,event):
        from piano_roll import PianoRollDialog
        dirty_editors=[e for e in self.findChildren(PianoRollDialog) if e.dirty]
        if dirty_editors:
            dirty_editors[0].raise_();dirty_editors[0].activateWindow()
            QMessageBox.information(self,"Cambios MIDI pendientes",
                "Guarda o descarta las modificaciones del piano roll antes de cerrar.")
            event.ignore();return
        if self.process and self.process.state()!=QProcess.NotRunning:
            QMessageBox.information(self,"Conversión en curso",
                                    "Termina o cancela la conversión antes de cerrar.")
            event.ignore();return
        self.source_preview.cleanup()
        self.output_preview.cleanup()
        self.chord_preview.cleanup()
        if self.player and self.player.state()!=QProcess.NotRunning:
            self.player.terminate();self.player.waitForFinished(1200)
        if self.tempo_job and self.tempo_job.state()!=QProcess.NotRunning:
            self.tempo_job.terminate()
            self.tempo_job.waitForFinished(1200)
        self.save_preferences()
        event.accept()
