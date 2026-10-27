#!/usr/bin/env python3
"""Monitor de Grabación: aplicación gráfica de captura de audio para Debian."""
from __future__ import annotations
import file_dialogs

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLayout, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget, QTabWidget,
)

from audio_engine import CaptureWorker, FORMAT_OPTIONS, SAMPLE_RATES, default_monitor, list_sources
from widgets import Oscilloscope, Spectrum, StereoMeter
from preview_player import PreviewPlayer, AudioRoute

from studio_paths import workspace_root
ROOT = workspace_root(__file__)
RECORDINGS = ROOT / "grabaciones"
PREFS = ROOT / "configuracion.json"

STYLE = """
* {font-family: "Noto Sans", "DejaVu Sans", sans-serif; font-size: 12px;}
QMainWindow, QWidget#main {background:#031434; color:#e0f8ff;}
QLabel {color:#e0f8ff;}
QLabel#title {font-size:24px; font-weight:750; color:#e0f8ff;}
QLabel#subtitle, QLabel#muted {color:#a3e4f0;}
QLabel#section {font-size:14px; font-weight:700; color:#e0f8ff;}
QLabel#bigtime {font-family: "DejaVu Sans Mono", monospace; font-size:25px; color:#e0f8ff; font-weight:700;}
QLabel#status {color:#66d5c1; font-weight:600;}
QFrame#panel {background:#04193f; border:1px solid #2085bd; border-radius:13px;}
QFrame#inner {background:#04173b; border:1px solid #1f7eb4; border-radius:10px;}
QComboBox, QLineEdit {background:#031534; border:1px solid #259bdc; border-radius:5px;
    padding:4px 7px; color:#e0f8ff; min-height:20px;}
QComboBox:hover, QLineEdit:focus {border:1px solid #2bb1fc;}
QComboBox::drop-down {border:0; width:24px;}
QComboBox QAbstractItemView {background:#041c46; color:#e0f8ff; selection-background-color:#2aaef8;}
QPushButton {background:#052052; color:#e0f8ff; border:1px solid #29a9f1;
   border-radius:5px; min-height:18px; padding:4px 9px; font-weight:550;font-size:11px;}
QPushButton:hover {background:#093d9b;}
QPushButton:pressed {background:#041d49;}
QPushButton:disabled {color:#a3e4f0; background:#041a42; border-color:#1b70a0;}
QPushButton#primary {background:#0b48b4; border-color:#2bb1fc; color:white;}
QPushButton#primary:hover {background:#0d53d2;}
QPushButton#record {background:#9e3440; border-color:#d95159; color:white;}
QPushButton#record:hover {background:#bb4050;}
QPushButton#stop {background:#c83745; border-color:#ad4d55; color:#fff;}
QCheckBox {color:#e0f8ff; spacing:8px;}
QCheckBox::indicator {width:16px; height:16px;}
QPlainTextEdit {background:#031637; color:#a3e4f0; border:1px solid #2085bd;
    border-radius:7px; padding:7px; font-family:"DejaVu Sans Mono"; font-size:10px;}
QScrollBar:vertical {background:#04173b; width:10px;}
QScrollBar::handle:vertical {background:#093c98; border-radius:4px;}
QDialog, QScrollArea, QScrollArea > QWidget > QWidget {background:#031434; color:#e0f8ff;}
QSpinBox {background:#031534; border:1px solid #259bdc; border-radius:5px;
    padding:4px 7px; color:#e0f8ff;}
QTableWidget {background:#031637; color:#e0f8ff; gridline-color:#a3cad6; border:1px solid #269ee1;
    border-radius:7px; selection-background-color:#27a3e8; selection-color:white;}
QTableWidget::item {padding:5px;}
QTreeWidget {background:#031637; color:#e0f8ff; border:1px solid #269ee1;
  border-radius:7px; selection-background-color:#27a3e8; selection-color:#fff;}
QTreeWidget::item {padding:5px; min-height:20px;}
QTreeWidget::item:alternate {background:#041a42;}
QTreeWidget::item:selected {background:#0b48b5; color:white;}
QTreeWidget::branch {background:#031637;}
QGraphicsView {background:#041a42; border:1px solid #269ee1; border-radius:5px;}
QTabWidget::pane {background:#031434; border:1px solid #228ecb; top:-1px;}
QTabBar::tab {background:#051e4c; color:#e0f8ff; border:1px solid #2597d8;
  border-bottom:0; padding:6px 12px; margin-right:1px; font-size:11px;}
QTabBar::tab:selected {background:#0b48b7; border-color:#2bb1fc; color:white;}
QTabBar::tab:hover:!selected {background:#093c96;}
QSplitter::handle {background:#083689; width:5px;}
QHeaderView::section {background:#052052; color:#e0f8ff; padding:4px;
    border:0; border-right:1px solid #2494d4; font-weight:600;}
QProgressBar {background:#04193f; color:white; border:1px solid #27a3e8;
    height:9px; border-radius:4px; text-align:center;}
QProgressBar::chunk {background:#0d59e0; border-radius:4px;}
"""


def panel(title=None):
    w = QFrame()
    w.setObjectName("panel")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(9, 7, 9, 8)
    lay.setSpacing(4)
    if title:
        label = QLabel(title)
        label.setObjectName("section")
        lay.addWidget(label)
    return w, lay


def lbl(text, muted=False):
    widget = QLabel(text)
    if muted:
        widget.setObjectName("muted")
    return widget


class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Todos los QMessageBox/QFileDialog/QInputDialog/QDialog del programa
        # comparten propietario y prioridad mientras haya tarjetas flotantes.
        import dialog_guard
        dialog_guard.install(QApplication.instance())
        self.setWindowTitle("StemMIDI Studio")
        self.resize(1340, 860)
        self.setMinimumSize(970, 660)
        self.worker = None
        self.recording = False
        self.record_pending = False
        self.record_started = None
        self.last_file = None
        self.config = self.load_config()
        self.input_gain_db=max(-60,min(12,int(self.config.get("input_gain_db",0))))
        self.input_balance=max(-100,min(100,int(self.config.get("input_balance",0))))
        self.project_id=uuid4().hex
        self.project_path=None
        self.project_name=None
        self.project_dir=None
        self.projects_base=self.config.get("projects_base",
                            str(__import__("project_flow").PROJECTS))
        self.project_recordings=[]

        host = QWidget()
        host.setObjectName("main")
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(host,"Monitor / Grabación")
        root = QVBoxLayout(host)
        root.setContentsMargins(11, 9, 11, 9)
        root.setSpacing(8)

        top = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("MONITOR DE GRABACIÓN")
        title.setObjectName("title")
        title_col.addWidget(title)
        title_col.addWidget(lbl("Supervisión y captura del audio del sistema · 48 kHz estéreo", True))
        top.addLayout(title_col)
        top.addStretch()
        top.addWidget(QLabel("SALIDA DE ESCUCHA"))
        self.playback_device=QComboBox(self)
        self.playback_device.setMinimumWidth(180)
        self.playback_device.setMaximumWidth(320)
        self.playback_device.setToolTip("Dispositivo donde se reproducen audio, extracciones y MIDI. "
                     "No cambia la salida predeterminada del sistema.")
        AudioRoute.register_control(self.playback_device)
        top.addWidget(self.playback_device)
        self.mode = QLabel("●  PREPARANDO")
        self.mode.setObjectName("status")
        top.addWidget(self.mode, alignment=Qt.AlignVCenter)
        root.addLayout(top)

        # Tres columnas compactas independientes, sin QScrollArea.
        # El espectro deja de reclamar altura mediante stretch expansivo.
        scroller_content = QWidget()
        scroller_content.setObjectName("monitorCanvas")
        content = QHBoxLayout(scroller_content)
        content.setContentsMargins(2,1,2,2)
        content.setSpacing(8)
        root.addWidget(scroller_content, 1)
        left=QVBoxLayout()
        middle=QVBoxLayout()
        right=QVBoxLayout()
        for lane in (left,middle,right):
            lane.setSpacing(6)
        content.addLayout(left,25)
        content.addLayout(middle,31)
        content.addLayout(right,44)

        source_card, sl = panel("FUENTE DE AUDIO")
        source_row = QHBoxLayout()
        self.sources = QComboBox()
        self.sources.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        source_row.addWidget(self.sources, 1)
        self.refresh_button = QPushButton("↻")
        self.refresh_button.setToolTip("Actualizar los dispositivos reales de audio disponibles.")
        self.refresh_button.setFixedWidth(36)
        self.refresh_button.clicked.connect(self.refresh_sources)
        source_row.addWidget(self.refresh_button)
        sl.addLayout(source_row)
        self.show_mics = QCheckBox("Micrófonos / línea")
        self.show_mics.setToolTip("Incluir en la lista los micrófonos y entradas de línea, "
                                 "además de los monitores de audio del sistema.")
        self.show_mics.setChecked(self.config.get("show_mics", False))
        self.show_mics.toggled.connect(self.refresh_sources)
        sl.addWidget(self.show_mics)
        self.source_note = lbl("Los monitores de salida capturan lo que reproduce el ordenador.", True)
        self.source_note.setWordWrap(True)
        sl.addWidget(self.source_note)
        self.source_note.setVisible(False)  # Disponible en la ayuda de fuente
        self.monitor_button = QPushButton("Iniciar supervisión")
        self.monitor_button.setObjectName("primary")
        self.monitor_button.clicked.connect(self.toggle_monitor)
        self.monitor_button.setMaximumWidth(220)
        sl.addWidget(self.monitor_button,alignment=Qt.AlignLeft)
        left.addWidget(source_card)

        vu_card, vl = panel("NIVELES ESTÉREO · dBFS")
        self.meter = StereoMeter()
        self.meter.setMaximumHeight(72)
        vl.addWidget(self.meter)
        lev = QHBoxLayout()
        self.level_left = lbl("L: −∞ dBFS", True)
        self.level_right = lbl("R: −∞ dBFS", True)
        lev.addWidget(self.level_left)
        lev.addStretch()
        lev.addWidget(self.level_right)
        vl.addLayout(lev)
        left.addWidget(vu_card)

        spec_card, spl = panel("ESPECTRO · FRECUENCIAS")
        self.spectrum = Spectrum()
        self.spectrum.setMinimumHeight(76)
        self.spectrum.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        spl.addWidget(self.spectrum, 1)
        spec_card.setMaximumHeight(167)
        spec_card.setMinimumHeight(126)
        left.addWidget(spec_card, 0)

        wave_card, wl = panel("FORMA DE ONDA")
        self.oscillo = Oscilloscope()
        self.oscillo.setMinimumHeight(45)
        self.oscillo.setMaximumHeight(86)
        wl.addWidget(self.oscillo)
        wave_card.setMaximumHeight(136)
        left.addWidget(wave_card,0)
        left.addStretch(1)

        rec_card, rl = panel("GRABADORA")
        time_area = QVBoxLayout()
        self.clock = QLabel("00:00:00")
        self.clock.setObjectName("bigtime")
        self.clock.setAlignment(Qt.AlignHCenter)
        time_area.addWidget(self.clock)
        self.rec_hint = lbl("Listo para grabar", True)
        self.rec_hint.setAlignment(Qt.AlignHCenter)
        time_area.addWidget(self.rec_hint)
        rl.addLayout(time_area)
        rl.addWidget(lbl("Formato de salida"))
        self.format = QComboBox()
        self.format.addItems(FORMAT_OPTIONS.keys())
        self.format.setCurrentText(self.config.get("format", "FLAC (sin pérdida)"))
        rl.addWidget(self.format)
        rl.addWidget(lbl("Frecuencia de muestreo · Hz"))
        self.capture_rate=QComboBox()
        for rate in SAMPLE_RATES:
            self.capture_rate.addItem(f"{rate/1000:g} kHz · estéreo",rate)
        selected_rate=int(self.config.get("sample_rate",48000))
        rate_index=self.capture_rate.findData(selected_rate)
        if rate_index>=0:self.capture_rate.setCurrentIndex(rate_index)
        self.capture_rate.setToolTip(
            "El servidor de audio puede remuestrear fuentes de menor frecuencia. "
            "Seleccionar 192 kHz no convierte una fuente de 48 kHz en audio de alta resolución.")
        rl.addWidget(self.capture_rate)
        self.format.currentTextChanged.connect(self.limit_lossy_rate)
        self.capture_rate.currentIndexChanged.connect(
            lambda idx:self.limit_lossy_rate(self.format.currentText()))
        self.limit_lossy_rate(self.format.currentText())
        rl.addWidget(lbl("Nombre del archivo (opcional)"))
        self.file_prefix = QLineEdit()
        self.file_prefix.setPlaceholderText("Grabacion_sistema")
        self.file_prefix.setText(self.config.get("prefix", "Grabacion_sistema"))
        rl.addWidget(self.file_prefix)
        rl.addWidget(lbl("Carpeta de las grabaciones"))
        self.folder_display = QLineEdit()
        self.folder_display.setText(self.config.get("folder", str(RECORDINGS)))
        self.folder_display.setReadOnly(False)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_display, 1)
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self.select_folder)
        folder_row.addWidget(browse)
        rl.addLayout(folder_row)
        button_row = QHBoxLayout()
        self.record_button = QPushButton("●  Iniciar grabación")
        self.record_button.setObjectName("record")
        self.record_button.clicked.connect(self.toggle_record)
        self.record_button.setMaximumWidth(200)
        button_row.addWidget(self.record_button)
        self.open_button = QPushButton("Abrir carpeta")
        self.open_button.clicked.connect(self.open_folder)
        button_row.addWidget(self.open_button)
        rl.addLayout(button_row)
        backup_controls=QHBoxLayout()
        self.backup_record_btn=QPushButton("Guardar grabación como…")
        self.backup_record_btn.setToolTip(
            "Elige el nombre y la carpeta de destino de esta grabación, "
            "sin sobrescribir el original.")
        self.backup_record_btn.clicked.connect(
            lambda:__import__("project_flow").backup_recording(self))
        backup_controls.addWidget(self.backup_record_btn)
        self.repeat_record_btn=QPushButton("Repetir toma…")
        self.repeat_record_btn.clicked.connect(
            lambda:__import__("project_flow").repeat_project(self))
        backup_controls.addWidget(self.repeat_record_btn)
        rl.addLayout(backup_controls)
        self.current_output = lbl("Sin grabación activa", True)
        self.current_output.setWordWrap(True)
        rl.addWidget(self.current_output)
        self.record_preview = PreviewPlayer("ESCUCHAR ÚLTIMA GRABACIÓN",self)
        rl.addWidget(self.record_preview)
        self.separate_button = QPushButton("Separar audio")
        self.separate_button.setObjectName("primary")
        self.separate_button.clicked.connect(self.open_separator)
        self.midi_button = QPushButton("Audio a MIDI")
        self.midi_button.setObjectName("primary")
        self.midi_button.clicked.connect(self.open_audio_midi)
        self.library_separator_btn=QPushButton("Ver extracciones")
        self.library_separator_btn.clicked.connect(self.open_separations_library)
        self.library_midi_btn=QPushButton("Ver MIDI y Piano Roll")
        self.library_midi_btn.clicked.connect(self.open_midi_library)
        tools1=QHBoxLayout()
        tools1.addWidget(self.separate_button)
        tools1.addWidget(self.midi_button)
        rl.addLayout(tools1)
        tools2=QHBoxLayout()
        tools2.addWidget(self.library_separator_btn)
        tools2.addWidget(self.library_midi_btn)
        rl.addLayout(tools2)
        rl.addWidget(lbl("Consulta las extracciones, selecciona los MIDI y edita sus notas.", True))
        middle.addWidget(rec_card,0)
        from recording_lab import RecordingLab
        self.recording_lab=RecordingLab(self,self)
        self.recording_lab.setMinimumWidth(365)
        right.addWidget(self.recording_lab,1)
        self.monitor_scroll=None
        from ux_controls import PresetStrip
        self.record_presets=PresetStrip("monitor_grabacion",{
            "Grabación sin pérdida":{"format":"FLAC (sin pérdida)"},
            "WAV para edición":{"format":"WAV (PCM 16 bits)"},
            "MP3 compacto":{"format":"MP3 (calidad alta)"}},
            self.monitor_preset_snapshot,self.monitor_preset_apply,self)
        rl.insertWidget(0,self.record_presets)
        self.record_presets.layout().setContentsMargins(4,2,4,2)
        self.record_presets.layout().setSpacing(3)
        self.record_presets.choices.setMinimumWidth(100)
        self.record_presets.choices.setMaximumWidth(130)
        self.record_presets.name.setMinimumWidth(50)
        self.record_presets.name.setMaximumWidth(74)
        self.record_presets.save_btn.setText("+")
        self.record_presets.save_btn.setToolTip("Guardar los ajustes de grabación como preset propio.")
        self.record_presets.save_btn.setMaximumWidth(34)
        self.record_presets.delete_btn.setText("−")
        self.record_presets.delete_btn.setToolTip("Borrar el preset propio seleccionado.")
        self.record_presets.delete_btn.setMaximumWidth(34)
        self.record_presets.message.hide()
        self.record_presets.save_btn.clicked.connect(
            lambda:self.rec_hint.setText(self.record_presets.message.text()))
        self.record_presets.delete_btn.clicked.connect(
            lambda:self.rec_hint.setText(self.record_presets.message.text()))
        self._record_autosave=QTimer(self)
        self._record_autosave.setInterval(700)
        self._record_autosave.setSingleShot(True)
        self._record_autosave.timeout.connect(self.save_config)
        self.format.currentIndexChanged.connect(lambda _:self._record_autosave.start())
        self.sources.currentIndexChanged.connect(lambda _:self._record_autosave.start())
        self.file_prefix.editingFinished.connect(self.save_config)
        self.folder_display.editingFinished.connect(self.save_config)
        self.show_mics.toggled.connect(lambda _:self._record_autosave.start())
        from studio_compact_ui import compact_recorder
        compact_recorder(self,rec_card,rl)

        status_card, stl = panel("ESTADO DEL SISTEMA")
        self.statusline = lbl("Inicializando…", True)
        self.statusline.setWordWrap(True)
        stl.addWidget(self.statusline)
        self.detail = lbl("La aplicación analiza el sonido sin reproducirlo otra vez.", True)
        self.detail.setWordWrap(True)
        stl.addWidget(self.detail)
        middle.addWidget(status_card,0)

        log_card, ll = panel("REGISTRO DE ACTIVIDAD")
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(500)
        ll.addWidget(self.logbox, 1)
        log_card.setMaximumHeight(123)
        middle.addWidget(log_card,0)
        self.log_card=log_card
        self.log_toggle=QPushButton("Registro de actividad ▾",self)
        self.log_toggle.setToolTip("Mostrar u ocultar el registro de mensajes del motor. "
                                   "No cambia ninguna grabación.")
        self.log_toggle.clicked.connect(
            lambda:(
               log_card.setVisible(not log_card.isVisible()),
               self.log_toggle.setText("Registro de actividad ▴"
                   if log_card.isVisible() else "Registro de actividad ▾")))
        middle.addWidget(self.log_toggle,0)
        log_card.hide()
        middle.addStretch(1)
        # Los reproductores mantienen sus opciones avanzadas detrás del
        # botón Opciones, sin saturar la pantalla principal.
        self.record_preview.set_compact(True)
        self.record_preview.detail.hide()

        foot = QHBoxLayout()
        foot.addWidget(lbl("Captura original protegida · Procesamiento no destructivo", True))
        foot.addStretch()
        foot.addWidget(lbl("PipeWire · FFmpeg · 48 kHz", True))
        root.addLayout(foot)
        root.setSpacing(4)
        root.setContentsMargins(7,5,7,5)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(200)
        self.refresh_sources()
        self.log("Aplicación iniciada. Configuración guardada en Recuperación.")
        from workspace_ui import IntegratedWorkspace
        self.workbench=IntegratedWorkspace(self,self.tabs)
        # Si se inicia una previsualización o se sale de la pestaña
        # de captura, detener el monitor SOLO si no hay grabación.
        AudioRoute.before_preview=self.stop_monitor_for_preview
        self.tabs.currentChanged.connect(self.on_workspace_tab_changed)
        # Supervisión opt-in: la captura simultánea puede competir con
        # la escucha o confundir las rutas de monitorización de PipeWire.
        # La grabación sigue pudiendo iniciar la captura cuando se solicita.
        self.mode.setText("●  DETENIDO" if self.sources.count()
                          else "●  SIN FUENTES")
        self.statusline.setText("Supervisión detenida. Pulsa Iniciar supervisión "
                                "solo cuando quieras supervisar o grabar.")
        from studio_shell import install
        install(self)
        from project_flow import add_approval_button
        add_approval_button(self)
        if __import__("os").environ.get("QT_QPA_PLATFORM")!="offscreen" and not __import__("os").environ.get("STEMMIDI_NO_STARTUP_DIALOG"):
            QTimer.singleShot(0,lambda:__import__("project_flow").startup(self))

    @staticmethod
    def load_config():
        try:
            return json.loads(PREFS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def monitor_preset_snapshot(self):
        return {"format":self.format.currentText(),
                "sample_rate":self.capture_rate.currentData(),
                "input_gain_db":self.input_gain_db,
                "input_balance":self.input_balance,
                "show_mics":self.show_mics.isChecked()}

    def monitor_preset_apply(self,params):
        if params.get("format") and self.format.findText(params["format"])>=0:
            self.format.setCurrentText(params["format"])
        if "sample_rate" in params:
            idx=self.capture_rate.findData(params["sample_rate"])
            if idx>=0:self.capture_rate.setCurrentIndex(idx)
        self.limit_lossy_rate(self.format.currentText())
        self.set_input_processing(
            params.get("input_gain_db",self.input_gain_db),
            params.get("input_balance",self.input_balance))
        if "show_mics" in params:
            self.show_mics.setChecked(bool(params["show_mics"]))
        self.save_config()

    def save_config(self):
        prefs = {
            "format": self.format.currentText(),
            "sample_rate": self.capture_rate.currentData(),
            "input_gain_db": self.input_gain_db,
            "input_balance": self.input_balance,
            "prefix": self.file_prefix.text(),
            "folder": self.folder_display.text(),
            "projects_base":str(getattr(self,"projects_base",
                                       __import__("project_flow").PROJECTS)),
            "show_mics": self.show_mics.isChecked(),
            "source": self.sources.currentData(),
            "professional_help_enabled": bool(
                getattr(getattr(self,"_context_help",None),"enabled",
                        self.config.get("professional_help_enabled",True))),
        }
        try:
            PREFS.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.log(f"No se pudo guardar la configuración: {exc}")

    def log(self, message):
        t = datetime.now().strftime("%H:%M:%S")
        self.logbox.appendPlainText(f"[{t}] {message}")

    def refresh_sources(self):
        if self.worker and self.worker.isRunning():
            self.log("Detén la supervisión para actualizar las fuentes.")
            return
        selected = self.sources.currentData() or self.config.get("source") or default_monitor()
        self.sources.clear()
        try:
            sources = list_sources(self.show_mics.isChecked())
        except RuntimeError as exc:
            QMessageBox.warning(self, "Servidor de audio", str(exc))
            sources = []
        for source in sources:
            self.sources.addItem(source["label"], source["name"])
        idx = self.sources.findData(selected)
        if idx < 0:
            idx = self.sources.findData(default_monitor())
        if idx >= 0:
            self.sources.setCurrentIndex(idx)
        self.statusline.setText(f"{len(sources)} fuentes disponibles. Selecciona la salida que está sonando.")

    def set_input_processing(self, gain_db=None, balance=None):
        """Actualiza captura y medidores; no ajusta el volumen de PipeWire."""
        if gain_db is not None:
            self.input_gain_db=max(-60,min(12,int(gain_db)))
        if balance is not None:
            self.input_balance=max(-100,min(100,int(balance)))
        if self.worker is not None:
            self.worker.set_input_controls(self.input_gain_db,self.input_balance)
        home=getattr(self,"studio_home",None)
        if home is not None:
            home.sync_input_controls()
        self.save_config()

    def start_monitor(self):
        if self.worker and self.worker.isRunning():
            return
        device = self.sources.currentData()
        if not device:
            QMessageBox.information(self, "Sin fuente", "No hay una fuente de audio seleccionada.")
            return
        self.worker = CaptureWorker(device, self, sample_rate=self.capture_rate.currentData())
        self.worker.set_input_controls(self.input_gain_db,self.input_balance)
        self.worker.levels.connect(self.on_levels)
        self.worker.visual.connect(self.on_visual)
        self.worker.capture_state.connect(self.on_capture_state)
        self.worker.recording_state.connect(self.on_recording_state)
        self.worker.recording_finished.connect(self.on_recording_finished)
        self.worker.start()
        self.sources.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.show_mics.setEnabled(False)
        self.monitor_button.setText("Detener supervisión")
        self.mode.setText("●  SUPERVISANDO")
        self.statusline.setText("Conectando con la fuente…")
        self.log(f"Supervisión solicitada: {device}")

    def stop_monitor(self):
        worker = self.worker
        if worker:
            worker.stop_capture()
            if not worker.wait(4500):
                self.log("El proceso de captura sigue cerrándose.")
                return
            self.worker = None
        self.recording = False
        self.record_pending = False
        self.record_started = None
        self.sources.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.show_mics.setEnabled(True)
        self.monitor_button.setText("Iniciar supervisión")
        self.mode.setText("●  DETENIDO")
        self.meter.set_levels(0, 0, 0, 0)
        self.spectrum.set_bands([0]*48)
        self.oscillo.set_wave([0]*205)
        self.update_record_button()
        self.log("Supervisión detenida.")

    def toggle_monitor(self):
        if self.worker and self.worker.isRunning():
            self.stop_monitor()
        else:
            self.start_monitor()

    def stop_monitor_for_preview(self):
        if (self.worker and self.worker.isRunning()
                and not self.recording and not self.record_pending):
            self.stop_monitor()
            self.log("Supervisión detenida para permitir la escucha de archivos.")

    def on_workspace_tab_changed(self,index):
        # Se mantiene la supervisión durante la grabación real.
        current=self.tabs.widget(index)
        if current not in (getattr(self,"monitor_page",None),
                           getattr(self,"studio_home",None)):
            self.stop_monitor_for_preview()

    def select_folder(self):
        if getattr(self,"project_dir",None):
            QMessageBox.information(self,"Carpeta del proyecto",
                "Las grabaciones van dentro del proyecto activo. "
                "Puedes escoger otro directorio al crear un nuevo proyecto.")
            return
        current = self.folder_display.text()
        folder = file_dialogs.get_existing_directory(self, "Seleccionar carpeta de grabación", current)
        if folder:
            self.folder_display.setText(folder)
            self.save_config()

    def open_separator(self):
        self.workbench.select_separation_source(self.last_file)

    def open_audio_midi(self):
        self.workbench.select_midi_source(self.last_file)

    def open_separations_library(self):
        self.workbench.focus_separation_results()

    def open_midi_library(self):
        self.workbench.focus_midi_results()

    def open_results_library(self,kind,folder=None,file=None):
        self.workbench.open_saved_library(kind)

    def open_folder(self):
        folder = Path(self.folder_display.text()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, 'Error de carpeta', str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def limit_lossy_rate(self,format_name):
        """No prometer un archivo de alta resolución en códecs limitados."""
        opus="Opus" in str(format_name)
        lossy=any(k in str(format_name) for k in ("MP3","AAC","Opus"))
        current=self.capture_rate.currentData()
        if lossy and (current>48000 or (opus and current!=48000)):
            idx=self.capture_rate.findData(48000)
            if idx>=0:
                was=self.capture_rate.blockSignals(True)
                self.capture_rate.setCurrentIndex(idx)
                self.capture_rate.blockSignals(was)
        self.capture_rate.setToolTip(
            "Compresión con pérdidas: salida a 44,1/48 kHz según códec."
            if lossy else
            "Frecuencia solicitada a PipeWire/PulseAudio. Si la fuente original "
            "es de menor frecuencia, el sistema puede remuestrear; no genera "
            "información ni calidad adicionales.")

    def next_filename(self):
        from project_flow import project_directory,slug_name
        project=project_directory(self)
        if not project:
            raise ValueError("Crea un proyecto antes de grabar")
        folder=project/"grabaciones"
        folder.mkdir(parents=True,exist_ok=True)
        prefix=slug_name(self.file_prefix.text().strip() or self.project_name or "Grabacion")
        ext, _ = FORMAT_OPTIONS[self.format.currentText()]
        name = prefix + "_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        result = folder / (name + "." + ext)
        n = 2
        while result.exists():
            result = folder / (f"{name}_{n}.{ext}")
            n += 1
        return result

    def toggle_record(self):
        if self.record_pending:
            return
        if self.recording:
            self.record_pending = True
            self.record_button.setEnabled(False)
            self.rec_hint.setText("Finalizando archivo…")
            self.worker.request_stop_recording()
            return
        from project_flow import ensure_recording_project,slug_name
        if not ensure_recording_project(self):
            return
        # Cada grabación tiene nombre propio y no reemplaza tomas anteriores.
        suggestion=self.file_prefix.text().strip() or self.project_name or "Grabacion"
        name,ok=__import__("PySide6.QtWidgets",
            fromlist=["QInputDialog"]).QInputDialog.getText(
            self,"Nombre de la grabación",
            "Pon nombre a esta toma (el programa añadirá fecha y hora):",
            text=str(suggestion))
        if not ok:return
        if not name.strip():
            QMessageBox.information(self,"Nombre necesario",
                "Escribe un nombre para identificar la grabación.")
            return
        self.file_prefix.setText(slug_name(name))
        # Si la supervisión existente usa otra frecuencia, reabrir la fuente
        # antes de la nueva grabación, sin modificar ningún archivo anterior.
        if (self.worker and self.worker.isRunning() and not self.recording
            and self.worker.sample_rate!=self.capture_rate.currentData()):
            self.stop_monitor()
        if not self.worker or not self.worker.isRunning():
            self.start_monitor()
        if not self.worker or not self.worker.isRunning():
            return
        try:
            file = self.next_filename()
        except OSError as exc:
            QMessageBox.critical(self, "Error de carpeta", str(exc))
            return
        if self.worker.request_recording(file, self.format.currentText()):
            self.record_pending = True
            self.update_record_button()
            self.rec_hint.setText("Preparando grabación…")
            self.save_config()

    def update_record_button(self):
        self.record_button.setEnabled(not self.record_pending)
        if self.recording:
            self.record_button.setText("■  Detener grabación")
            self.record_button.setObjectName("stop")
        else:
            self.record_button.setText("●  Iniciar grabación")
            self.record_button.setObjectName("record")
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
        for x in (self.format, self.capture_rate, self.file_prefix):
            x.setEnabled(not self.recording and not self.record_pending)
        self.folder_display.setReadOnly(
            bool(getattr(self,"project_dir",None)))
        self.folder_display.setEnabled(not self.recording and not self.record_pending)

    def on_recording_state(self, active, path):
        self.recording = active
        self.record_pending = False
        self.update_record_button()
        if active:
            self.record_started = time.monotonic()
            self.current_output.setText(path)
            self.rec_hint.setText("●  GRABANDO")
            self.mode.setText("●  GRABANDO")
            self.log(f"Grabando: {path}")
        else:
            self.record_started = None
            self.rec_hint.setText("Grabación finalizada")
            self.mode.setText("●  SUPERVISANDO" if self.worker and self.worker.isRunning() else "●  DETENIDO")
            self.log("Codificación terminada.")

    def on_recording_finished(self, path, success, message):
        if success:
            self.last_file = path
            self.record_preview.load(path)
            self.log(f"Guardado: {Path(path).name} ({message})")
            self.current_output.setText(f"Guardado: {path}")
            try:
                from project_flow import register_recording
                register_recording(self,path)
            except (OSError,ValueError) as exc:
                self.log("Grabación guardada, pero el proyecto necesita revisión: "+str(exc))
                QMessageBox.warning(self,"Proyecto no actualizado",
                    "La grabación está guardada correctamente. No se pudo "
                    "actualizar el proyecto: "+str(exc))
            # Solo después de que el archivo original haya sido
            # finalizado y registrado. NUNCA procesar la entrada cruda.
            self.recording_lab.on_recording_finished(path,True)
        else:
            self.log(f"ERROR: {message}")
            self.rec_hint.setText("Error al guardar")
            self.current_output.setText(message)
            QMessageBox.warning(self, "Grabación no completada", message)

    def on_capture_state(self, active, message):
        self.statusline.setText(message)
        if not active and message != "Supervisión detenida":
            self.log(message)

    @staticmethod
    def dbfs(value):
        if value < 1e-7:
            return "−∞"
        return f"{20 * __import__('math').log10(value):.1f}"

    def on_levels(self, l, r, lp, rp):
        self.meter.set_levels(l, r, lp, rp)
        self.level_left.setText(f"L: {self.dbfs(lp)} dBFS")
        self.level_right.setText(f"R: {self.dbfs(rp)} dBFS")
        if hasattr(self,"studio_home"):
            self.studio_home.sync_capture_levels(l,r,lp,rp)

    def on_visual(self, bands, wave):
        self.spectrum.set_bands(bands)
        self.oscillo.set_wave(wave)

    def tick(self):
        if self.recording and self.record_started is not None:
            # El motor envía PCM estéreo float32le (4 bytes/muestra),
            # NO 16 bits. Usar la frecuencia real elegida en esta toma.
            # Los bytes solo aumentan cuando se escribe audio: las pausas
            # quedan excluidas y el reloj coincide con el archivo final.
            from audio_engine import recorded_seconds
            worker=self.worker
            bytes_done=getattr(worker,"_rec_bytes",0) if worker else 0
            rate=getattr(worker,"sample_rate",48000) if worker else 48000
            secs=int(recorded_seconds(bytes_done,rate))
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self.clock.setText(f"{h:02}:{m:02}:{s:02}")
        elif not self.record_pending:
            self.clock.setText("00:00:00")

    def closeEvent(self, event):
        from PySide6.QtCore import QProcess
        work=getattr(self,"workbench",None)
        if work is not None:
            if (work.converter.tempo_job is not None
                and work.converter.tempo_job.state()!=QProcess.NotRunning):
                QMessageBox.information(self,"Análisis del tempo en curso",
                    "Finaliza el análisis de BPM antes de cerrar el programa.")
                event.ignore();return
            if work.separator.busy or (work.converter.process is not None
                and work.converter.process.state()!=QProcess.NotRunning):
                QMessageBox.information(self,"Trabajo en curso",
                    "Termina o cancela el procesamiento de audio/MIDI antes de cerrar.")
                event.ignore();return
            if work.mixer is not None and work.mixer.process is not None and work.mixer.process.state()!=QProcess.NotRunning:
                QMessageBox.information(self,"Mezcla en curso",
                    "Finaliza o cancela la exportación antes de cerrar.")
                event.ignore();return
            if work.piano.dirty:
                QMessageBox.information(self,"Piano Roll",
                    "Aplica la edición temporal o descarta los cambios antes de salir.")
                self.tabs.setCurrentWidget(work.piano)
                event.ignore();return
            work.sep_results.preview.stop()
            work.midi_results.preview.stop()
            work.piano.preview.stop()
        from piano_roll import PianoRollDialog
        dirty_editors=[e for e in self.findChildren(PianoRollDialog) if e.dirty]
        if dirty_editors:
            dirty_editors[0].raise_();dirty_editors[0].activateWindow()
            QMessageBox.information(self,"Cambios MIDI pendientes",
                "Guarda o descarta las modificaciones del piano roll antes de cerrar.")
            event.ignore();return
        separator = getattr(self, "separator_dialog", None)
        if separator is not None:
            sep_midi = getattr(separator, "midi_dialog", None)
            sep_mix = getattr(separator, "mixer", None)
            if (separator.busy
                or (sep_midi is not None and sep_midi.process is not None
                    and sep_midi.process.state() != QProcess.NotRunning)
                or (sep_mix is not None and sep_mix.process is not None
                    and sep_mix.process.state() != QProcess.NotRunning)):
                QMessageBox.information(self, "Proceso musical en curso",
                                        "Finaliza o cancela la separación, conversión MIDI o mezcla antes de cerrar.")
                event.ignore()
                return
        midi = getattr(self, "midi_dialog", None)
        if midi is not None and midi.process is not None and midi.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Conversión MIDI en curso",
                                    "Finaliza o cancela la conversión MIDI antes de cerrar la aplicación.")
            event.ignore()
            return
        if (getattr(self,"recording_lab",None) is not None
                and self.recording_lab.process is not None):
            QMessageBox.information(self,"Laboratorio procesando",
                "Finaliza o cancela el laboratorio antes de cerrar. "
                "Así se mantiene protegida la toma original.")
            event.ignore()
            return
        if self.recording or self.record_pending:
            ans = QMessageBox.question(
                self, "Finalizar grabación",
                "Hay una grabación en curso. ¿Finalizarla y cerrar la aplicación?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                event.ignore()
                return
        # Desacoplar no puede dejar ventanas de nivel superior vivas al cerrar:
        # Qt mantendría su bucle de eventos y parecería que hay que forzar el cierre.
        home=getattr(self,"studio_home",None)
        if home is not None:
            manager=getattr(home,"_floating_manager",None)
            if manager is not None:manager.shutdown()
        self.record_preview.cleanup()
        self.recording_lab.close_cleanup()
        home=getattr(self,"studio_home",None)
        if home is not None:
            home.heartbeat.stop()
            home.player.cleanup()
            for canvas in [home.wave,home.overview]+[
                row["wave"] for row in home.track_rows.values()]:
                canvas.cancel_decode()
        if AudioRoute.before_preview==self.stop_monitor_for_preview:
            AudioRoute.before_preview=None
        self.save_config()
        if self.worker:
            self.worker.stop_capture()
            if not self.worker.wait(10000):
                QMessageBox.warning(self, "Captura ocupada",
                                    "El motor todavía está finalizando. Prueba a cerrar de nuevo.")
                event.ignore()
                return
        if work is not None:
            # Guardar los BPM y filtros elegidos aunque el usuario solo
            # analice el tempo sin llegar a convertir un archivo.
            work.converter.save_preferences()
            work.separator.save_preferences()
        if home is not None and getattr(home,"record_review",None) is not None:
            home.record_review.cleanup()
        event.accept()


if __name__ == "__main__":
    from intro_video import play_external_intro, play_intro
    # Arranque común para fuentes y compilación: primero la intro, después Qt.
    external_intro_ok = play_external_intro()
    app = QApplication(sys.argv)
    app.setApplicationName("StemMIDI Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    if not external_intro_ok:
        play_intro()  # Respaldo Qt si FFplay no está disponible.
    window = MonitorWindow()
    window.show()
    sys.exit(app.exec())
