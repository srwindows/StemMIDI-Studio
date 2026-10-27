#!/usr/bin/env python3
"""Mezclador de stems: mute/solo/ganancia, preescucha y exportación sin modificar originales."""
from __future__ import annotations
import file_dialogs

import math
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from preview_player import PreviewPlayer
from ux_controls import PresetStrip, PRESET_DIR
import json
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget
)

from studio_paths import workspace_root
ROOT = workspace_root(__file__)
FORMATS = {
    "FLAC sin pérdida": (".flac", ("-c:a", "flac")),
    "WAV PCM 24 bits": (".wav", ("-c:a", "pcm_s24le")),
    "MP3 alta calidad": (".mp3", ("-c:a", "libmp3lame", "-q:a", "1")),
}

def gain_db(percent):
    return "-∞ dB" if percent == 0 else f"{20*math.log10(percent/100):+.1f} dB"


def filter_for_mix(track_settings):
    """Crear grafo de FFmpeg usando exclusivamente índices numéricos y ganancias verificadas."""
    active_solos = any(t["solo"] for t in track_settings)
    included = []
    for i, t in enumerate(track_settings):
        if t["volume"] > 0 and not t["mute"] and (not active_solos or t["solo"]):
            included.append((i, t["volume"] / 100.0))
    if not included:
        raise ValueError("Todas las pistas están silenciadas. Activa al menos una.")
    filters = []
    taps = []
    for i, gain in included:
        filters.append(f"[{i}:a]volume={gain:.4f},aresample=48000,"
                       f"aformat=sample_fmts=fltp:channel_layouts=stereo[t{i}]")
        taps.append(f"[t{i}]")
    filters.append("".join(taps) +
                   f"amix=inputs={len(taps)}:duration=longest:dropout_transition=0:"
                   "normalize=0,alimiter=limit=0.96:level=0:attack=5:release=50[out]")
    return ";".join(filters)


class MixDialog(QDialog):
    def __init__(self, sources, parent=None):
        super().__init__(parent)
        self.sources = [Path(s) for s in sources]
        self.project_dir = None
        self.setWindowTitle("Mezclador multipista — Monitor de Grabación")
        self.setMinimumSize(760, 570)
        self.resize(960, 740)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.rows = []
        self.process = None
        self.player = None
        self.work_file = None
        self.is_preview = False
        self._cancel_requested = False
        self.temp_previews = []
        self.create_ui()

    def create_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        page_scroll = QScrollArea(self)
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.NoFrame)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName("main")
        page_scroll.setWidget(content)
        outer.addWidget(page_scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(13)
        head = QLabel("MEZCLADOR DE PISTAS")
        head.setObjectName("title")
        root.addWidget(head)
        intro = QLabel("Ajusta el volumen, silencia o escucha pistas en solo. "
                       "Puedes generar una preescucha y exportar una mezcla nueva sin alterar los originales.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        root.addWidget(intro)
        self.presets=PresetStrip("mezclador",{
            "Mezcla equilibrada":{"mix_mode":"all","gain":100},
            "Solo voz":{"mix_mode":"voice","gain":100},
            "Sin voz (instrumental)":{"mix_mode":"instrumental","gain":100},
            "Instrumentos al 80 %":{"mix_mode":"all","gain":80},
        },self.preset_snapshot,self.apply_preset,self)
        root.addWidget(self.presets)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroller.setMinimumHeight(185)
        scroller.setMaximumHeight(340)
        container = QWidget()
        container.setObjectName("main")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 8, 2)
        layout.setSpacing(7)

        top = QFrame()
        top.setObjectName("panel")
        headers = QHBoxLayout(top)
        headers.addWidget(QLabel("PISTA"), 2)
        headers.addWidget(QLabel("MUTE"))
        headers.addWidget(QLabel("SOLO"))
        headers.addWidget(QLabel("NIVEL"), 3)
        headers.addWidget(QLabel("GANANCIA"))
        layout.addWidget(top)

        for i, path in enumerate(self.sources):
            frame = QFrame()
            frame.setObjectName("panel")
            line = QHBoxLayout(frame)
            line.setContentsMargins(12, 8, 12, 8)
            name = QLabel(self.display_name(path.stem))
            name.setMinimumWidth(115)
            name.setWordWrap(True)
            line.addWidget(name, 2)
            mute = QCheckBox()
            mute.setToolTip("No se escuchará esta pista")
            line.addWidget(mute)
            solo = QCheckBox()
            solo.setToolTip("Reproducir únicamente pistas marcadas SOLO")
            line.addWidget(solo)
            fader = QSlider(Qt.Horizontal)
            fader.setRange(0, 150)
            fader.setValue(100)
            fader.setSingleStep(5)
            line.addWidget(fader, 3)
            digit = QSpinBox()
            digit.setRange(0,150)
            digit.setValue(100)
            digit.setSuffix("%")
            digit.setFixedWidth(74)
            fader.valueChanged.connect(digit.setValue)
            digit.valueChanged.connect(fader.setValue)
            line.addWidget(digit)
            value = QLabel("0.0 dB")
            value.setMinimumWidth(64)
            line.addWidget(value)
            fader.valueChanged.connect(lambda v, out=value: out.setText(gain_db(v)))
            self.rows.append({"path": path, "mute": mute, "solo": solo,
                              "slider": fader,"digit":digit})
            layout.addWidget(frame)
        layout.addStretch()
        scroller.setWidget(container)
        root.addWidget(scroller)
        choices=QHBoxLayout()
        choices.addWidget(QLabel("Pista de origen para escuchar"))
        self.source_choice=QComboBox()
        for item in self.sources:
            self.source_choice.addItem(item.name,str(item))
        self.source_choice.currentIndexChanged.connect(self.choose_source)
        choices.addWidget(self.source_choice,1)
        root.addLayout(choices)
        self.source_preview=PreviewPlayer("ESCUCHAR PISTA ORIGINAL",self)
        root.addWidget(self.source_preview)
        self.output_preview=PreviewPlayer("ESCUCHAR MEZCLA / EXPORTACIÓN",self)
        self.source_preview.exclusive_with(self.output_preview)
        self.output_preview.exclusive_with(self.source_preview)
        root.addWidget(self.output_preview)
        if self.sources:
            self.source_preview.load(self.sources[0])

        opt = QFrame()
        opt.setObjectName("panel")
        opt_layout = QGridLayout(opt)
        opt_layout.addWidget(QLabel("Comienzo de preescucha (segundos)"), 0, 0)
        self.offset = QSpinBox()
        self.offset.setMaximum(8*60*60)
        self.offset.setValue(0)
        opt_layout.addWidget(self.offset, 0, 1)
        opt_layout.addWidget(QLabel("Formato de exportación"), 0, 2)
        self.output_fmt = QComboBox()
        self.output_fmt.addItems(FORMATS)
        opt_layout.addWidget(self.output_fmt, 0, 3)
        root.addWidget(opt)

        buttons = QHBoxLayout()
        self.preview_button = QPushButton("Escuchar mezcla (20 s)")
        self.preview_button.setObjectName("primary")
        self.preview_button.clicked.connect(self.preview_mix)
        buttons.addWidget(self.preview_button)
        self.stop_button = QPushButton("Detener audio")
        self.stop_button.clicked.connect(self.stop_playback)
        buttons.addWidget(self.stop_button)
        self.export_button = QPushButton("Exportar mezcla completa…")
        self.export_button.clicked.connect(self.export_mix)
        buttons.addWidget(self.export_button)
        self.cancel_button = QPushButton("Cancelar proceso")
        self.cancel_button.setObjectName("stop")
        self.cancel_button.clicked.connect(self.cancel_job)
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)

        self.status = QLabel("Listo. La preescucha se calcula antes de reproducirse (20 segundos).")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setMaximumHeight(100)
        self.log.setReadOnly(True)
        root.addWidget(self.log)
        self.load_last_settings()
        for row in self.rows:
            row["slider"].valueChanged.connect(lambda _:self.save_last_settings())
            row["mute"].toggled.connect(lambda _:self.save_last_settings())
            row["solo"].toggled.connect(lambda _:self.save_last_settings())
        self.output_fmt.currentIndexChanged.connect(lambda _:self.save_last_settings())
        self.offset.valueChanged.connect(lambda _:self.save_last_settings())

    def preset_snapshot(self):
        return {"tracks":{self.display_name(row["path"].stem):
                          {"volume":row["slider"].value(),
                           "mute":row["mute"].isChecked(),
                           "solo":row["solo"].isChecked()}
                          for row in self.rows},
                "format":self.output_fmt.currentText(),
                "offset":self.offset.value()}

    def apply_preset(self,data):
        mode=data.get("mix_mode")
        roles=data.get("tracks",{})
        for row in self.rows:
            role=self.display_name(row["path"].stem)
            params=roles.get(role,{})
            if mode:
                voice=role=="VOZ"
                muted=(mode=="voice" and not voice) or (mode=="instrumental" and voice)
                row["mute"].setChecked(muted)
                row["solo"].setChecked(False)
                row["slider"].setValue(int(data.get("gain",100)))
            else:
                row["mute"].setChecked(bool(params.get("mute",False)))
                row["solo"].setChecked(bool(params.get("solo",False)))
                if "volume" in params:
                    row["slider"].setValue(int(params["volume"]))
        if data.get("format") in FORMATS:
            self.output_fmt.setCurrentText(data["format"])
        if "offset" in data:self.offset.setValue(int(data["offset"]))
        self.save_last_settings()

    @property
    def last_settings_file(self):
        return PRESET_DIR/"ultima_mezcla.json"

    def save_last_settings(self):
        PRESET_DIR.mkdir(exist_ok=True)
        tmp=self.last_settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.preset_snapshot(),ensure_ascii=False,indent=2),
                       encoding="utf-8")
        tmp.replace(self.last_settings_file)

    def load_last_settings(self):
        try:
            settings=json.loads(self.last_settings_file.read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError):
            return
        self.apply_preset(settings)

    @staticmethod
    def display_name(s):
        for en, es in (("Vocals", "VOZ"), ("Instrumental", "INSTRUMENTAL"),
                        ("Drums", "BATERÍA"), ("Bass", "BAJO"), ("Guitar", "GUITARRA"),
                        ("Piano", "PIANO"), ("Other", "OTROS"), ("Izquierdo", "IZQUIERDO"),
                        ("Derecho", "DERECHO")):
            if en.lower() in s.lower():
                return es
        return s[:45]

    def settings(self):
        return [{"volume": x["slider"].value(), "mute": x["mute"].isChecked(),
                 "solo": x["solo"].isChecked()} for x in self.rows]

    def command_for(self, destination, preview=False):
        if not self.sources or not all(p.is_file() for p in self.sources):
            raise FileNotFoundError("Faltan archivos de pistas; abre de nuevo los resultados.")
        graph = filter_for_mix(self.settings())
        args = ["-hide_banner", "-loglevel", "error", "-nostdin", "-n"]
        if preview:
            args += ["-ss", str(self.offset.value())]
        for path in self.sources:
            args += ["-i", str(path)]
        args += ["-filter_complex", graph, "-map", "[out]"]
        if preview:
            args += ["-t", "20", "-c:a", "flac", str(destination)]
        else:
            ext, codec = FORMATS[self.output_fmt.currentText()]
            assert destination.suffix == ext
            args += [*codec, str(destination)]
        return args

    def busy(self, on):
        self.presets.setEnabled(not on)
        self.preview_button.setEnabled(not on)
        self.export_button.setEnabled(not on)
        self.cancel_button.setEnabled(on)
        if on:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)

    def choose_source(self,index):
        path=self.source_choice.itemData(index)
        if path and Path(path).is_file():
            self.output_preview.stop()
            self.source_preview.load(path)

    def preview_mix(self):
        p = ((Path(self.project_dir)/"temporales"/"mezclas")
             if self.project_dir else ROOT/"previsualizaciones_temporales")
        p.mkdir(exist_ok=True, parents=True)
        out = p / f"mezcla_previa_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.flac"
        self.start_mix(out, True)

    def export_mix(self):
        from project_layout import module_dir
        outdir = (module_dir(self.project_dir,"mezclador")
                  if self.project_dir else self.sources[0].parent)
        outdir.mkdir(parents=True,exist_ok=True)
        ext, _ = FORMATS[self.output_fmt.currentText()]
        prefix=(Path(self.project_dir).name+"_" if self.project_dir else "")
        suggested = outdir / (prefix+"MEZCLA_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ext)
        name, _ = file_dialogs.get_save_file_name(
            self, "Guardar mezcla", str(suggested),
            "Audio (*" + ext + ")")
        if not name:
            return
        dest = Path(name)
        if dest.suffix.lower() != ext:
            dest = Path(str(dest) + ext)
        from project_layout import layout_active,save_folder
        if self.project_dir and layout_active(self.project_dir):
            dest=save_folder(self.project_dir,"mezclador",dest.parent)/dest.name
        if dest.resolve() in [p.resolve() for p in self.sources]:
            QMessageBox.warning(self,"Origen protegido",
                                "No puedes sobrescribir una de las pistas de origen.")
            return
        if dest.exists():
            response=QMessageBox.question(self,"Sobrescribir mezcla",
                "Ya existe ese archivo. ¿Sustituirlo por la nueva mezcla?",
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if response!=QMessageBox.Yes:return
        self.start_mix(dest, False)

    def start_mix(self, dest, preview):
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            return
        if self.project_dir and preview:
            from task_staging import inside
            allowed=Path(self.project_dir)/"temporales"/"mezclas"
            if not inside(dest,allowed):
                QMessageBox.warning(self,"Ruta del proyecto",
                    "La mezcla debe permanecer en el proyecto activo: "+str(allowed))
                return
        self.stop_playback()
        try:
            args = self.command_for(dest, preview)
        except (ValueError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "Mezcla", str(exc))
            return
        self.work_file = dest
        self.is_preview = preview
        self._cancel_requested = False
        self.log.appendPlainText(f"Preparando {'preescucha' if preview else 'exportación'}: {dest}")
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self.read_output)
        proc.finished.connect(self.on_mix_finished)
        proc.errorOccurred.connect(self.process_error)
        self.process = proc
        self.busy(True)
        self.status.setText("Procesando mezcla…")
        proc.start("ffmpeg", args)

    def read_output(self):
        if self.process:
            contents = bytes(self.process.readAllStandardOutput()).decode(errors="replace").strip()
            if contents:
                self.log.appendPlainText(contents[-1200:])

    def process_error(self, error):
        if error == QProcess.FailedToStart and self.process is not None:
            failed=self.process
            self.status.setText("Error: no se ha podido iniciar FFmpeg.")
            self.log.appendPlainText(failed.errorString())
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.on_mix_finished(-1,QProcess.CrashExit)
                              if self.process is failed else None)

    def on_mix_finished(self, code, state):
        self.read_output()
        proc = self.process
        self.process = None
        if proc:
            proc.deleteLater()
        self.busy(False)
        file = self.work_file
        ok = code == 0 and state == QProcess.NormalExit and file and file.exists() and file.stat().st_size > 100
        if self._cancel_requested:
            self.status.setText("Proceso cancelado. Los originales siguen intactos.")
        elif ok:
            self.progress.setValue(100)
            if self.is_preview:
                self.temp_previews.append(file)
                self.status.setText("Preescucha preparada; reproduciendo…")
                self.source_preview.stop()
                self.output_preview.load(file,autoplay=True)
            else:
                self.status.setText("Mezcla exportada: " + str(file))
                self.output_preview.load(file)
                self.log.appendPlainText("Guardado: " + str(file))
                # Una exportación externa también pertenece al proyecto.
                # Conservar copia en el área de trabajo para que «Guardar
                # proyecto» la incluya en el backup de reapertura.
                if self.project_dir:
                    try:
                        from export_dialog import _copy_atomic
                        root=Path(self.project_dir)/"temporales"/"mezclas"
                        dest=root/("mezcla_actual"+file.suffix)
                        if file.resolve()!=dest.resolve():
                            _copy_atomic(file,dest)
                    except (OSError,ValueError) as exc:
                        self.log.appendPlainText(
                            "ATENCIÓN: mezcla exportada pero no incorporada "
                            "al proyecto: "+str(exc))
        else:
            self.status.setText("No se pudo crear la mezcla. Revisa el registro de errores.")
            self.log.appendPlainText(f"FFmpeg terminó con código {code}")
        if self.is_preview and file and file.exists() and not ok:
            try: file.unlink()
            except OSError: pass

    def stop_playback(self):
        self.source_preview.stop()
        self.output_preview.clear()
        if self.player:
            if self.player.state() != QProcess.NotRunning:
                self.player.terminate()
                if not self.player.waitForFinished(500):
                    self.player.kill()
                    self.player.waitForFinished(500)
            self.player.deleteLater()
            self.player = None
        for path in self.temp_previews:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        self.temp_previews.clear()

    def cancel_job(self):
        if not self.process or self.process.state() == QProcess.NotRunning:
            return
        self._cancel_requested = True
        self.process.terminate()
        p = self.process
        from PySide6.QtCore import QTimer
        def force_stop():
            try:
                if p.state() != QProcess.NotRunning:
                    p.kill()
            except RuntimeError:
                pass  # finished() pudo destruir el objeto antes del temporizador.
        QTimer.singleShot(2000,force_stop)

    def closeEvent(self, event):
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Mezcla en curso", "Cancela o finaliza antes de cerrar.")
            event.ignore()
            return
        self.stop_playback()
        self.source_preview.cleanup()
        self.output_preview.cleanup()
        event.accept()
