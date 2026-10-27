#!/usr/bin/env python3
"""Ventana de separación multipista (IA Demucs/UVR o canales estéreo).

El procesamiento corre en otro proceso para que la interfaz y el monitor de
audio sigan respondiendo. Modelos, caché y resultados se guardan en Recuperación.
"""
from __future__ import annotations
import file_dialogs

import re
import shutil
import json
from datetime import datetime
from pathlib import Path

from audio_import import probe_audio, describe_audio, normalize_command
from audio_import_gui import DropPathEdit, pick_audio, check_and_describe
from preview_player import PreviewPlayer
from ux_controls import PresetStrip

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from studio_paths import workspace_root
ROOT = workspace_root(__file__)
OUTPUT_DIR = ROOT / "pistas_separadas"
MODELS_DIR = ROOT / "modelos"
CACHE_DIR = ROOT / "cache_ia"
SEPARATOR = ROOT / "entorno_ia" / "bin" / "audio-separator"
PYTHON = ROOT / "entorno_ia" / "bin" / "python"
PREFERENCES = ROOT / "preferencias_separador.json"

MODELS = {
    "2 pistas · ESTUDIO — MelBand Roformer (voz + instrumental)": "vocals_mel_band_roformer.ckpt",
    "2 pistas · RÁPIDO — MDX (voz + instrumental)": "UVR-MDX-NET-Inst_HQ_3.onnx",
    "4 pistas · ESTUDIO — Demucs FT (voz, batería, bajo, otros)": "htdemucs_ft.yaml",
    "4 pistas · RÁPIDO — Demucs (voz, batería, bajo, otros)": "htdemucs.yaml",
    "6 pistas · DETALLADO — Voz, batería, bajo, guitarra, piano, otros": "htdemucs_6s.yaml",
    "2 canales originales — Izquierdo / Derecho (sin IA)": None,
}
EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".aif", ".mp4", ".mkv"}
AUDIO_OUTPUTS = {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a"}
ENCODERS = {
    "FLAC (sin pérdida)": ("FLAC", ".flac", ["-c:a", "flac"]),
    "WAV (PCM)": ("WAV", ".wav", ["-c:a", "pcm_s16le"]),
    "MP3 (alta calidad)": ("MP3", ".mp3", ["-c:a", "libmp3lame", "-q:a", "2"]),
}


class SeparadorDialog(QDialog):
    def __init__(self, parent=None, file_path=None):
        super().__init__(parent)
        self.setWindowTitle("Separador de pistas — IA musical")
        self.resize(1040, 780)
        self.setMinimumSize(800, 615)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.jobs = []
        self.process = None
        self.preview = None
        self.current_folder = None
        self.workspace = None
        self.embedded = False
        self.import_temp_dir = None
        self.busy = False
        self.cancelled = False
        self.steps = 0
        self.started_at = None
        self.latest_outputs = []
        self.log_lines = 0
        self.current_command = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.create_ui()
        self.load_preferences()
        self.refresh_model_registry()
        self._autosave=QTimer(self)
        self._autosave.setInterval(600)
        self._autosave.setSingleShot(True)
        self._autosave.timeout.connect(self.save_preferences)
        for widget in (self.profile,self.quality,self.export_fmt):
            widget.currentIndexChanged.connect(lambda _:self._autosave.start())
        self.dest_edit.editingFinished.connect(self.save_preferences)
        self.file_edit.editingFinished.connect(self.save_preferences)
        if file_path and Path(file_path).exists():
            self.file_edit.setText(str(file_path))
            self.source_preview.load(file_path)

    def refresh_model_registry(self):
        """Solo ofrece modelos instalados que producen stems generales válidos."""
        from model_registry import catalog,installed,is_general,model_active
        previous=self.profile.currentText()
        for label in list(MODELS):
            if label.startswith("IA instalada · "):
                MODELS.pop(label,None)
        for rec in catalog().values():
            if installed(rec) and is_general(rec):
                label="IA instalada · "+rec["name"]+" ("+rec["filename"]+")"
                MODELS[label]=rec["filename"]
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItems(MODELS)
        active=model_active().get("general")
        target=next((key for key,val in MODELS.items()
                     if key.startswith("IA instalada · ") and val==active),None)
        target=target or previous
        if target in MODELS:
            self.profile.setCurrentText(target)
        self.profile.blockSignals(False)
        self.on_model_change()

    def parameter_snapshot(self):
        return {"profile":self.profile.currentText(),
                "quality":self.quality.currentText(),
                "format":self.export_fmt.currentText(),
                "normalization":getattr(self,"norm_setting",.9),
                "amplification":getattr(self,"amp_setting",0.0),
                "sample_rate":getattr(self,"sample_setting",48000),
                "requested_stems":(self.requested_stems()
                    if hasattr(self,"requested_stems") else [])}

    def apply_parameters(self,data):
        for key,widget in (("profile",self.profile),
                           ("quality",self.quality),("format",self.export_fmt)):
            if data.get(key) and widget.findText(data[key])>=0:
                widget.setCurrentText(data[key])
        for key,attr in (("normalization","norm_setting"),
                         ("amplification","amp_setting")):
            if key in data:
                setattr(self,attr,max(.10 if key=="normalization" else 0.,
                       min(1.0,float(data[key]))))
        if data.get("sample_rate") in (44100,48000):
            self.sample_setting=int(data["sample_rate"])
        if hasattr(self,"stem_checks") and isinstance(data.get("requested_stems"),list):
            requested=set(data["requested_stems"])
            for name,check in self.stem_checks.items():
                if check.isEnabled():check.setChecked(name in requested)
        self.save_preferences()

    def load_preferences(self):
        try:
            data = json.loads(PREFERENCES.read_text(encoding="utf-8"))
            # Migración de la configuración inicial antigua (FT con dos
            # pasadas). Solo se hace una vez, sin impedir escoger ESTUDIO
            # o MÁXIMA calidad explícitamente después.
            old_default = (
                data.get("profile") ==
                "4 pistas · ESTUDIO — Demucs FT (voz, batería, bajo, otros)"
                and data.get("quality") == "Alta (más detalle)"
                and not data.get("optimized_speed_v1", False))
            if old_default:
                self.profile.setCurrentText(
                    "4 pistas · RÁPIDO — Demucs (voz, batería, bajo, otros)")
                self.quality.setCurrentText("Normal (más rápido)")
            else:
                if data.get("profile") in MODELS:
                    self.profile.setCurrentText(data["profile"])
                if data.get("quality") in [self.quality.itemText(i)
                                             for i in range(self.quality.count())]:
                    self.quality.setCurrentText(data["quality"])
            if data.get("format") in ENCODERS:
                self.export_fmt.setCurrentText(data["format"])
            self.norm_setting=float(data.get("normalization",0.9))
            self.amp_setting=float(data.get("amplification",0.0))
            self.sample_setting=int(data.get("sample_rate",48000))
            if data.get("folder"):
                self.dest_edit.setText(str(data["folder"]))
            if data.get("audio_path") and Path(data["audio_path"]).is_file():
                self.file_edit.setText(data["audio_path"])
                self.source_preview.load(data["audio_path"])
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def save_preferences(self):
        prefs = {
            "profile": self.profile.currentText(),
            "quality": self.quality.currentText(),
            "optimized_speed_v1": True,
            "format": self.export_fmt.currentText(),
            "folder": self.dest_edit.text().strip(),
            "audio_path": self.file_edit.text().strip(),
            "normalization": getattr(self,"norm_setting",0.9),
            "amplification": getattr(self,"amp_setting",0.0),
            "sample_rate": getattr(self,"sample_setting",48000),
        }
        try:
            PREFERENCES.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            self.append_log("No se pudo guardar la configuración: " + str(exc))

    def create_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        inner = QWidget()
        inner.setObjectName("main")
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        root = QVBoxLayout(inner)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(13)

        title = QLabel("SEPARACIÓN DE PISTAS")
        title.setObjectName("title")
        root.addWidget(title)
        note = QLabel("Extrae instrumentos de una mezcla grabada. Las pistas resultantes pueden reproducirse y guardarse por separado.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addWidget(note)
        fast="4 pistas · RÁPIDO — Demucs (voz, batería, bajo, otros)"
        studio="4 pistas · ESTUDIO — Demucs FT (voz, batería, bajo, otros)"
        six="6 pistas · DETALLADO — Voz, batería, bajo, guitarra, piano, otros"
        builtins={
            "4 pistas rápidas":{"profile":fast,"quality":"Normal (más rápido)",
                 "format":"FLAC (sin pérdida)"},
            "4 pistas estudio":{"profile":studio,"quality":"Alta (más detalle)",
                 "format":"FLAC (sin pérdida)"},
            "6 pistas detalladas":{"profile":six,"quality":"Normal (más rápido)",
                 "format":"FLAC (sin pérdida)"},
            "Voces rápidas":{"profile":"2 pistas · RÁPIDO — MDX (voz + instrumental)",
                 "quality":"Normal (más rápido)","format":"WAV (PCM)"},
            "Separar estéreo":{"profile":"2 canales originales — Izquierdo / Derecho (sin IA)",
                 "quality":"Normal (más rápido)","format":"WAV (PCM)"}}
        self.presets=PresetStrip("separar_audio",builtins,
                                self.parameter_snapshot,self.apply_parameters,self)
        root.addWidget(self.presets)
        input_box = QFrame()
        input_box.setObjectName("panel")
        input_box.setMinimumHeight(315)
        setup = QGridLayout(input_box)
        setup.setContentsMargins(18, 16, 18, 17)
        setup.setHorizontalSpacing(12)
        setup.setVerticalSpacing(11)

        setup.addWidget(QLabel("Archivo de audio"), 0, 0)
        self.file_edit = DropPathEdit("file")
        self.file_edit.imported = self.on_import_selected
        self.file_edit.editingFinished.connect(self.sync_source_preview)
        self.file_edit.setPlaceholderText("Selecciona una grabación o un archivo de música…")
        setup.addWidget(self.file_edit, 0, 1)
        self.import_button = QPushButton("Importar audio…")
        self.import_button.clicked.connect(self.choose_input)
        setup.addWidget(self.import_button, 0, 2)
        self.import_info = QLabel("Arrastra un audio o vídeo con sonido, o pulsa Importar audio…")
        self.import_info.setObjectName("muted")
        self.import_info.setWordWrap(True)
        setup.addWidget(self.import_info, 5, 0, 1, 3)

        setup.addWidget(QLabel("Tipo de separación"), 1, 0)
        self.profile = QComboBox()
        self.profile.addItems(MODELS)
        self.profile.setCurrentIndex(3)  # Demucs rápido, un solo modelo
        self.profile.currentIndexChanged.connect(self.on_model_change)
        setup.addWidget(self.profile, 1, 1)
        self.manage_models_btn=QPushButton("Modelos de IA…")
        self.manage_models_btn.clicked.connect(self.open_model_manager)
        setup.addWidget(self.manage_models_btn, 1, 2)

        setup.addWidget(QLabel("Calidad de procesamiento"), 2, 0)
        self.quality = QComboBox()
        self.quality.addItems(("Normal (más rápido)", "Alta (más detalle)", "Máxima (más lenta)"))
        self.quality.setCurrentIndex(0)  # una pasada, menos solapamiento
        setup.addWidget(self.quality, 2, 1, 1, 2)

        setup.addWidget(QLabel("Formato de exportación"), 3, 0)
        self.export_fmt = QComboBox()
        self.export_fmt.addItems(ENCODERS)
        setup.addWidget(self.export_fmt, 3, 1, 1, 2)

        setup.addWidget(QLabel("Guardar las pistas en"), 4, 0)
        self.dest_edit = QLineEdit(str(OUTPUT_DIR))
        setup.addWidget(self.dest_edit, 4, 1)
        pick_out = QPushButton("Carpeta…")
        pick_out.clicked.connect(self.choose_folder)
        setup.addWidget(pick_out, 4, 2)
        root.addWidget(input_box)
        self.source_preview = PreviewPlayer("ESCUCHAR AUDIO ORIGINAL", self)
        root.addWidget(self.source_preview)

        controls = QHBoxLayout()
        self.go = QPushButton("Separar pistas")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.start_separation)
        controls.addWidget(self.go)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("stop")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.stop)
        controls.addWidget(self.cancel_button)
        controls.addStretch()
        self.elapsed = QLabel("Tiempo: 00:00")
        self.elapsed.setObjectName("muted")
        controls.addWidget(self.elapsed)
        root.addLayout(controls)

        self.progress_label = QLabel("Esperando archivo de audio")
        self.progress_label.setObjectName("status")
        root.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        results_label = QLabel("PISTAS INDEPENDIENTES")
        results_label.setObjectName("section")
        root.addWidget(results_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Pista", "Formato", "Tamaño"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(lambda _: self.play_selected())
        self.table.currentCellChanged.connect(self.on_selected_result)
        root.addWidget(self.table, 1)
        self.result_preview = PreviewPlayer("ESCUCHAR PISTA EXTRAÍDA", self)
        self.source_preview.exclusive_with(self.result_preview)
        self.result_preview.exclusive_with(self.source_preview)
        root.addWidget(self.result_preview)

        action_row = QHBoxLayout()
        self.mix_button = QPushButton("Mezclador multipista…")
        self.mix_button.setObjectName("primary")
        self.mix_button.clicked.connect(self.open_mixer)
        action_row.addWidget(self.mix_button)
        self.midi_button = QPushButton("Convertir pistas a MIDI…")
        self.midi_button.setObjectName("primary")
        self.midi_button.clicked.connect(self.open_audio_midi)
        action_row.addWidget(self.midi_button)
        self.open_results_button = QPushButton("Abrir carpeta de pistas")
        self.open_results_button.clicked.connect(self.open_results)
        action_row.addWidget(self.open_results_button)
        action_row.addStretch()
        root.addLayout(action_row)
        self.load_previous_button = QPushButton("Cargar carpeta de pistas separadas anteriormente…")
        self.load_previous_button.clicked.connect(self.load_previous_stems)
        root.addWidget(self.load_previous_button)
        self.library_button=QPushButton("Ver biblioteca de extracciones…")
        self.library_button.setObjectName("primary")
        self.library_button.clicked.connect(self.open_library)
        root.addWidget(self.library_button)

        log_label = QLabel("ACTIVIDAD DEL MOTOR")
        log_label.setObjectName("section")
        root.addWidget(log_label)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(92)
        root.addWidget(self.log, 0)

        self.on_model_change()

    def append_log(self, value):
        for line in str(value).replace("\r", "\n").splitlines():
            if line.strip():
                self.log.appendPlainText(line[:1000])

    def sync_source_preview(self):
        source=Path(self.file_edit.text().strip()).expanduser()
        if source.is_file() and self.source_preview.current_file != str(source.resolve()):
            self.source_preview.load(source)

    def open_model_manager(self):
        if not self.embedded or self.workspace is None:
            QMessageBox.information(self,"Gestor de modelos",
                "Abre Preferencias → Modelos de IA desde StemMIDI Studio.")
            return
        from studio_shell import preferences
        preferences(self.workspace.main,open_models=True)

    def choose_input(self):
        candidate = Path(self.file_edit.text()).expanduser()
        start = str(candidate.parent) if candidate.is_file() else str(ROOT / "grabaciones")
        path = pick_audio(self, start)
        if path:
            self.on_import_selected(path)

    def on_import_selected(self, path):
        info, label = check_and_describe(self, path)
        if info:
            self.file_edit.setText(info["path"])
            self.import_info.setText(label)
            self.source_preview.load(info["path"])
            self.append_log("Importado: " + Path(path).name + " — " + label)
            self.save_preferences()
        else:
            self.import_info.setText("Archivo incompatible o sin pista de audio.")

    def choose_folder(self):
        if self.embedded and self.workspace is not None and self.workspace.main.project_dir:
            QMessageBox.information(self,"Destino del proyecto",
                "Las pistas definitivas se guardan directamente en la carpeta "
                "stems del proyecto, sin crear carpetas por cada prueba.")
            return
        start = self.dest_edit.text().strip() or str(OUTPUT_DIR)
        folder = file_dialogs.get_existing_directory(self, "Destino de las pistas", start)
        if folder:
            self.dest_edit.setText(folder)

    def on_model_change(self):
        model = MODELS[self.profile.currentText()]
        if not self.busy:
            if model is None:
                self.progress_label.setText("División exacta L/R, sin inteligencia artificial")
            else:
                tip = (" · 4 modelos especializados; más lento" if model=="htdemucs_ft.yaml"
                       else " · modelo único más rápido" if model=="htdemucs.yaml"
                       else "")
                self.progress_label.setText("Modelo IA: " + model + tip +
                    (" · instalado" if (MODELS_DIR / model).is_file()
                     else " · descarga necesaria"))
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        if hasattr(self, "refresh_stem_choices") and not self.busy:
            self.refresh_stem_choices()

    def set_busy(self, enabled):
        self.busy = enabled
        self.presets.setEnabled(not enabled)
        self.go.setEnabled(not enabled)
        self.cancel_button.setEnabled(enabled)
        self.file_edit.setEnabled(not enabled)
        self.import_button.setEnabled(not enabled)
        self.profile.setEnabled(not enabled)
        self.export_fmt.setEnabled(not enabled)
        self.quality.setEnabled(not enabled)
        self.dest_edit.setEnabled(not enabled)
        available=__import__("separation_pro_controls").stems_for_model(
            MODELS.get(self.profile.currentText()))
        for name,control in getattr(self,"stem_checks",{}).items():
            control.setEnabled(not enabled and name in available)
        if getattr(self,"stem_all",None) is not None:
            self.stem_all.setEnabled(not enabled)
        if getattr(self,"stem_parameters_btn",None) is not None:
            self.stem_parameters_btn.setEnabled(not enabled)
        self.progress.setRange(0,100)
        if enabled:
            self.progress.setValue(0)
        # Sin QProgressBar(0,0): no debe oscilar como progreso indeterminado.

    def start_separation(self):
        input_file = Path(self.file_edit.text().strip()).expanduser()
        if not input_file.is_file():
            QMessageBox.warning(self, "Archivo no encontrado", "Selecciona un archivo de audio existente.")
            return
        try:
            info = probe_audio(input_file)
        except ValueError as exc:
            QMessageBox.warning(self, "Audio no compatible", str(exc))
            return
        self.import_info.setText(describe_audio(info))
        label = self.profile.currentText()
        model = MODELS[label]
        requested=(self.requested_stems() if hasattr(self,"requested_stems")
                   else list(__import__("separation_pro_controls").stems_for_model(model)))
        if not requested:
            QMessageBox.warning(self,"Ninguna pista seleccionada",
                                "Marca al menos un instrumento que quieras extraer.")
            return
        if model:
            from stem_detection import is_separated_stem
            if is_separated_stem(input_file):
                answer=QMessageBox.question(self,"Archivo ya separado",
                    "El audio seleccionado ya es un stem de otro separador. "
                    "Volver a separarlo puede introducir artefactos o asignar "
                    "instrumentos a categorías equivocadas. Para transcribir "
                    "notas utiliza Audio a MIDI directamente.\n\n"
                    "¿Quieres continuar expresamente con otra separación?",
                    QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
                if answer!=QMessageBox.Yes:
                    return
        if model and (not PYTHON.is_file() or not SEPARATOR.is_file()):
            QMessageBox.warning(self, "Motor de IA no instalado",
                                "Falta el motor audio-separator en el disco Recuperación. "
                                "La separación L/R sigue disponible.")
            return
        if self.embedded:
            if not self.workspace.prepare_task("separaciones"):
                return
            base = self.workspace.separation_storage.processing_folder
        else:
            base = Path(self.dest_edit.text().strip()).expanduser()
        try:
            base.mkdir(parents=True, exist_ok=True)
            prefix = (re.sub(r"[^a-zA-Z0-9_-]+", "_", input_file.stem).strip("_") or "Audio")[:120]
            from project_layout import layout_active
            if self.embedded and self.workspace and layout_active(
                    self.workspace.main.project_dir):
                # Las pistas de cada sesión se generan en el mismo
                # directorio temporal. Sin «cancion_pistas_fecha» por pasada.
                output=base
                output.mkdir(parents=True,exist_ok=True)
                prefix_original=prefix
                index=2
                while (output/"_importacion_temporal"/(prefix+".flac")).exists():
                    prefix=f"{prefix_original}_{index}"
                    index+=1
            else:
                suffix = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                output = base / (prefix + "_pistas_" + suffix)
                idx = 2
                while output.exists():
                    output = base / f"{prefix}_pistas_{suffix}_{idx}"
                    idx += 1
                output.mkdir()
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Carpeta no disponible", str(exc))
            return

        self.current_folder = output
        self.active_request=list(requested)
        self.import_temp_dir = output / "_importacion_temporal"
        self.import_temp_dir.mkdir()
        self.save_preferences()
        self.latest_outputs.clear()
        self.result_preview.clear()
        self.table.setRowCount(0)
        self.log.clear()
        self.append_log("Origen: " + str(input_file))
        self.append_log("Destino: " + str(output))
        self.append_log("Modo: " + label)
        self.append_log("Pistas solicitadas: "+", ".join(requested))
        self.append_log("Parámetros: normalización="+str(getattr(self,"norm_setting",.9))+
                        ", amplificación="+str(getattr(self,"amp_setting",0)))
        self.append_log("Rendimiento: "
          + ("1 pasada" if self.quality.currentIndex()==0 else
             "2 pasadas" if self.quality.currentIndex()==1 else "4 pasadas")
          + (" · Demucs FT combina 4 modelos" if model=="htdemucs_ft.yaml" else
             " · Demucs rápido con 1 modelo" if model=="htdemucs.yaml" else ""))
        self.cancelled = False
        self._engine_progress_text_tail=""
        self.started_at = __import__("time").monotonic()
        self.steps = 0
        self.jobs = []
        outfmt, ext, codec = ENCODERS[self.export_fmt.currentText()]
        normalized = self.import_temp_dir / f"{prefix}.flac"
        self.jobs.append(normalize_command(input_file, normalized))
        self.append_log("Preparando audio de entrada: FLAC 24 bits / 44,1 kHz (original intacto)")
        if model is None:
            for channel, caption in ((0, "Canal_Izquierdo"), (1, "Canal_Derecho")):
                path = output / f"{caption}{ext}"
                self.jobs.append([
                    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-n",
                    "-i", str(normalized), "-af", f"pan=mono|c0=c{channel}",
                    "-ar", "48000", *codec, str(path)])
        else:
            self.jobs.append([
                str(PYTHON), str(SEPARATOR), str(normalized),
                "--model_filename", model,
                "--output_dir", str(output),
                "--model_file_dir", str(MODELS_DIR),
                "--output_format", outfmt,
                "--log_level", "info",
                "--normalization", str(getattr(self,"norm_setting",0.9)),
                "--amplification", str(getattr(self,"amp_setting",0)),
                "--sample_rate", str(getattr(self,"sample_setting",48000)),
                "--demucs_shifts", str((1, 2, 4)[self.quality.currentIndex()]),
                "--demucs_overlap", str((0.25, 0.50, 0.65)[self.quality.currentIndex()]),
                "--mdxc_overlap", str((8, 12, 16)[self.quality.currentIndex()]),
                "--mdx_overlap", str((0.25, 0.5, 0.65)[self.quality.currentIndex()]),
            ])
            if len(requested)==1:
                self.jobs[-1].extend(["--single_stem",__import__("separation_pro_controls").SPANISH[requested[0]]])
        self.set_busy(True)
        self.progress_label.setText("Separando pistas: preparando modelo…")
        from separation_pro_controls import start_monitor
        start_monitor(self)
        self.launch_next()

    def launch_next(self):
        if self.cancelled:
            self.finish(False)
            return
        if not self.jobs:
            self.finish(True)
            return
        cmd = self.jobs.pop(0)
        self.current_command = cmd
        self.steps += 1
        self.append_log(f"Etapa {self.steps}: {'división de canal' if cmd[0]=='ffmpeg' else 'separación neuronal'}")
        if getattr(self,"motor_dialog",None):
            self.motor_dialog.start_job(cmd)
            self.motor_dialog.stage_update(f"Etapa {self.steps}: "+
                ("Conversión FFmpeg" if cmd[0]=='ffmpeg' else "Separación IA en curso"))
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("XDG_CACHE_HOME", str(CACHE_DIR))
        env.insert("TORCH_HOME", str(MODELS_DIR))
        env.insert("OMP_NUM_THREADS", "8")
        env.insert("MKL_NUM_THREADS", "8")
        env.insert("PYTHONUNBUFFERED", "1")
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.setWorkingDirectory(str(ROOT))
        proc.readyReadStandardOutput.connect(self.consume_output)
        proc.finished.connect(self.on_process_finished)
        proc.errorOccurred.connect(self.on_process_error)
        self.process = proc
        proc.start(cmd[0], cmd[1:])

    def consume_output(self):
        if self.process is None:
            return
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if text:
            self.append_log(text)
            if getattr(self,"motor_dialog",None):
                self.motor_dialog.add_log()
                self.motor_dialog.receive_output(text)
            if "download" in text.lower():
                self.progress_label.setText("Descargando modelo al disco Recuperación…")
            elif "separat" in text.lower() or "process" in text.lower():
                self.progress_label.setText("Procesando audio con el modelo de IA…")

    def on_process_error(self, error):
        if error == QProcess.FailedToStart and self.process is not None:
            failed=self.process
            self.append_log("ERROR: no se pudo iniciar el motor. " + failed.errorString())
            # FailedToStart no emite finished(): cerrar el estado ocupado.
            QTimer.singleShot(0, lambda: self.on_process_finished(-1,QProcess.CrashExit)
                              if self.process is failed else None)

    def on_process_finished(self, code, status):
        self.consume_output()
        p = self.process
        if p is not None:
            p.deleteLater()
        self.process = None
        if self.cancelled:
            self.finish(False)
            return
        if code != 0 or status != QProcess.NormalExit:
            self.append_log(f"ERROR: la etapa terminó con código {code}.")
            self.finish(False)
            return
        self.refresh_outputs()
        from separation_pro_controls import instrument_progress
        instrument_progress(self)
        self.launch_next()

    def refresh_outputs(self):
        if not self.current_folder or not self.current_folder.exists():
            return
        self.latest_outputs = sorted(
            (p for p in self.current_folder.rglob("*")
             if p.is_file() and p.suffix.lower() in AUDIO_OUTPUTS
             and not p.name.lower().startswith(("mezcla_", "mezcla_previa_"))
             and "_preescuchas" not in p.parts
             and "_importacion_temporal" not in p.parts),
            key=lambda p: p.name.lower())
        self.table.setRowCount(len(self.latest_outputs))
        for i, path in enumerate(self.latest_outputs):
            desc = self.track_name(path)
            self.table.setItem(i, 0, QTableWidgetItem(desc))
            self.table.setItem(i, 1, QTableWidgetItem(path.suffix.upper().lstrip(".")))
            self.table.setItem(i, 2, QTableWidgetItem(f"{path.stat().st_size / 1048576:.2f} MB"))
        if self.latest_outputs:
            if self.table.currentRow() < 0 or self.table.currentRow() >= len(self.latest_outputs):
                self.table.selectRow(0)
            self.on_selected_result(self.table.currentRow(), 0, -1, -1)
        else:
            self.result_preview.clear()

    @staticmethod
    def track_name(path):
        s = path.stem.lower()
        if "mel_band_roformer" in s and "(other)" in s:
            return "Instrumental  ·  " + path.stem
        for key, translated in (
            ("instrumental", "Instrumental"),
            ("vocals", "Voz"),
            ("drums", "Batería"),
            ("bass", "Bajo"),
            ("piano", "Piano"),
            ("guitar", "Guitarra"),
            ("other", "Otros instrumentos"),
            ("canal_izquierdo", "Canal izquierdo"),
            ("canal_derecho", "Canal derecho"),
        ):
            if key in s:
                return translated + "  ·  " + path.stem
        return path.stem

    def finish(self, succeeded):
        self.set_busy(False)
        # Retirar exclusivamente la copia de trabajo normalizada. El original
        # y las pistas ya exportadas nunca se borran.
        if self.import_temp_dir and self.import_temp_dir.is_dir():
            try:
                shutil.rmtree(self.import_temp_dir)
            except OSError as exc:
                self.append_log(f"No se pudo limpiar la importación temporal: {exc}")
        self.import_temp_dir = None
        if succeeded and not self.cancelled:
            from separation_pro_controls import filter_requested_outputs
            filter_requested_outputs(self)
        self.refresh_outputs()
        if self.cancelled:
            self.progress_label.setText("Separación cancelada; comprueba si existen archivos parciales")
            # Mantener último porcentaje confirmado, sin retroceder a cero.
        elif succeeded and self.latest_outputs:
            self.progress_label.setText(f"Motor finalizado · {len(self.latest_outputs)} pistas temporales")
            # El inspector verifica las pistas solicitadas antes de fijar
            # el porcentaje general en 100%; no anticiparlo aquí.
            self.append_log("COMPLETADO: " + str(self.current_folder))
            if self.embedded:
                self.workspace.on_separation_completed(self.current_folder)
            else:
                from bibliotecas import register_result
                register_result("separaciones", self.current_folder)
                QTimer.singleShot(100,self.open_library)
        else:
            self.progress_label.setText("No se ha completado la separación. Revisa el registro.")
            # En error mantener avance real observado, no borrar la telemetría.
            self.append_log("PROCESO NO COMPLETADO. Los archivos de origen no han cambiado.")

        from separation_pro_controls import finish_monitor
        finish_monitor(self,succeeded and not self.cancelled and bool(self.latest_outputs))

    def stop(self):
        if not self.busy:
            return
        self.cancelled = True
        self.jobs.clear()
        self.progress_label.setText("Cancelando procesamiento…")
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            # Cancelación forzosa si el motor no responde a SIGTERM
            p = self.process
            def force_stop():
                try:
                    if p.state() != QProcess.NotRunning:
                        p.kill()
                except RuntimeError:
                    pass  # Qt ya destruyó el QProcess después de finished().
            QTimer.singleShot(3000, force_stop)
        else:
            self.finish(False)

    def tick(self):
        if self.started_at and self.busy:
            elapsed = int(__import__("time").monotonic() - self.started_at)
            self.elapsed.setText(f"Tiempo: {elapsed//60:02}:{elapsed%60:02}")

    def on_selected_result(self, row, col, old_row, old_col):
        if row >= 0 and row < len(self.latest_outputs):
            path = self.latest_outputs[row]
            if self.result_preview.current_file != str(path.resolve()):
                self.result_preview.load(path)

    def play_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.latest_outputs):
            QMessageBox.information(self, "Pistas", "Selecciona una pista para escucharla.")
            return
        self.source_preview.stop()
        self.result_preview.load(self.latest_outputs[row], autoplay=True)

    def stop_preview(self):
        self.result_preview.stop()

    def open_mixer(self):
        if self.embedded:
            from separation_pro_controls import checked_paths
            selection=checked_paths(self.workspace.main)
            if selection:
                self.workspace.show_mixer(selection)
            else:
                QMessageBox.information(self,"Seleccionar stems","Marca las pistas que quieres enviar al mezclador.")
            return
        if self.busy:
            QMessageBox.information(self, "Separación activa",
                                    "Termina la separación para abrir el mezclador.")
            return
        self.refresh_outputs()
        if not self.latest_outputs:
            QMessageBox.information(self, "Sin pistas", "Separa un archivo o carga una carpeta de pistas.")
            return
        from mezclador import MixDialog
        if getattr(self, "mixer", None) and self.mixer.isVisible():
            self.mixer.raise_()
            self.mixer.activateWindow()
            return
        self.mixer = MixDialog(self.latest_outputs, self)
        self.mixer.destroyed.connect(lambda: setattr(self, "mixer", None))
        self.mixer.show()

    def open_audio_midi(self):
        if self.embedded:
            from separation_pro_controls import checked_paths
            chosen=checked_paths(self.workspace.main)
            if not chosen:
                QMessageBox.information(self,"Seleccionar stems","Marca qué pistas pasar a Audio a MIDI.")
                return
            self.workspace.use_selected_stems_as_midi_source(chosen)
            return
        if self.busy:
            QMessageBox.information(self, "Separación activa",
                                    "Termina primero la separación de instrumentos.")
            return
        if not self.current_folder or not self.current_folder.is_dir():
            QMessageBox.information(self, "Pistas", "Separa un audio o carga una carpeta de pistas.")
            return
        from midi_dialog import AudioMidiDialog
        if getattr(self, "midi_dialog", None) is not None:
            self.midi_dialog.raise_()
            self.midi_dialog.activateWindow()
            return
        dlg = AudioMidiDialog(self, stems_folder=self.current_folder)
        self.midi_dialog = dlg
        dlg.destroyed.connect(lambda: setattr(self, "midi_dialog", None))
        dlg.show()

    def load_previous_stems(self):
        if self.busy:
            return
        folder = file_dialogs.get_existing_directory(
            self, "Abrir carpeta de pistas", str(OUTPUT_DIR))
        if folder:
            files = [p for p in Path(folder).iterdir()
                     if p.is_file() and p.suffix.lower() in AUDIO_OUTPUTS]
            if not files:
                QMessageBox.warning(self, "Carpeta vacía",
                                    "No se han encontrado WAV, FLAC, MP3, OGG, Opus ni M4A.")
                return
            self.current_folder = Path(folder)
            self.refresh_outputs()
            self.progress_label.setText(f"{len(self.latest_outputs)} pistas anteriores cargadas")
            self.append_log("Carpeta cargada: " + folder)

    def open_library(self):
        if self.embedded:
            self.workspace.focus_separation_results()
            return
        from bibliotecas import ResultsWindow
        if getattr(self,"library_window",None) is not None:
            self.library_window.focus_folder=self.current_folder
            self.library_window.refresh()
            self.library_window.show()
            self.library_window.raise_()
            return
        window=ResultsWindow("separaciones",self,focus_folder=self.current_folder)
        self.library_window=window
        window.destroyed.connect(lambda: setattr(self,"library_window",None))
        window.show()

    def open_results(self):
        folder = self.current_folder or Path(self.dest_edit.text()).expanduser()
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            QMessageBox.information(self, "Destino", "Todavía no existen resultados.")

    def closeEvent(self, event):
        from piano_roll import PianoRollDialog
        dirty_editors=[e for e in self.findChildren(PianoRollDialog) if e.dirty]
        if dirty_editors:
            dirty_editors[0].raise_();dirty_editors[0].activateWindow()
            QMessageBox.information(self,"Cambios MIDI pendientes",
                "Guarda o descarta las modificaciones del piano roll antes de cerrar.")
            event.ignore();return
        midi = getattr(self, "midi_dialog", None)
        if midi is not None and midi.process is not None and midi.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "MIDI en curso", "Termina o cancela la conversión MIDI antes de cerrar.")
            event.ignore()
            return
        mixer = getattr(self, "mixer", None)
        if mixer is not None and mixer.process is not None and mixer.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Mezcla en curso",
                                    "Cancela o termina la mezcla antes de cerrar esta ventana.")
            event.ignore()
            return
        if self.busy:
            QMessageBox.information(self, "Separación activa",
                                    "Cancela primero la separación; no se perderá el archivo original.")
            event.ignore()
            return
        self.save_preferences()
        self.source_preview.cleanup()
        self.result_preview.cleanup()
        event.accept()
