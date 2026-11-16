"""Primer arranque: selección explícita de las IA ya utilizadas en StemMIDI.

No descarga modelos automáticamente ni modifica proyectos. El gestor completo
sigue disponible en Preferencias > Modelos de IA después del primer inicio.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

import model_registry as registry
from studio_paths import resource_root, ia_python, worker_script

CATALOG_FILE = resource_root(__file__) / "first_run_models.json"
STATE_FILE = registry.ROOT / "configuracion" / "asistente_ia.json"
WEIGHT_TYPES = {".ckpt", ".onnx", ".th", ".pth"}


def _models():
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    if catalog.get("schema") != 1 or not isinstance(catalog.get("models"), list):
        raise ValueError("Catálogo inicial de IA inválido")
    return catalog["models"]


def _destination(entry):
    parts = {tuple(Path(item["path"]).parts[:-1]) for item in entry["files"]}
    if len(parts) != 1:
        raise ValueError("Un modelo no puede instalarse en varias carpetas")
    relative = next(iter(parts))
    if relative not in ((), ("voces",), ("bateria",)):
        raise ValueError("Carpeta de modelo no admitida")
    return registry.HOME.joinpath(*relative)


def _complete_file(file, root):
    relative = Path(str(file["path"]))
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) > 2:
        return False
    path = root / relative
    # El tamaño debe coincidir exactamente con el modelo registrado; un
    # fichero parcial al 95 % no se puede dar por instalado.
    return path.is_file() and path.stat().st_size == int(file["bytes"])


def installed(entry):
    return all(_complete_file(file, registry.HOME) for file in entry["files"])


def _size(entry):
    return sum(int(file["bytes"]) for file in entry["files"])


def _format_bytes(n):
    return f"{n / (1024 ** 3):.2f} GiB" if n >= 1024**3 else f"{n / (1024 ** 2):.1f} MiB"


def _record(entry):
    record = registry.record_for(entry["id"])
    if record is not None:
        return record
    return {
        "filename": entry["id"],
        "files": [Path(file["path"]).name for file in entry["files"]],
        "architecture": "MDXC",
        "stems": (["kick", "snare", "toms", "hh", "ride", "crash"]
                  if entry["id"].startswith("aufr33-jarredou_DrumSep") else
                  ["vocals", "instrumental"]),
    }


def _register_guitar(entry):
    """Mantener los metadatos de importación utilizados por el separador."""
    if entry["method"] != "direct":
        return
    import external_model_import
    existing = external_model_import.records()
    if entry["id"] in existing:
        return
    name = entry["id"]
    if "electric-guitar" in name:
        display, stems = "MVSep Mega 53 · Eléctrica", ["electric-guitar", "instrumental"]
    elif "acoustic-guitar" in name:
        display, stems = "MVSep Mega 53 · Acústica", ["acoustic-guitar", "instrumental"]
    else:
        display, stems = "Mel-Band · Solista / Rítmica", ["lead", "instrumental"]
    files = [Path(f["path"]).name for f in entry["files"]]
    existing[name] = {
        "filename": name, "files": files, "family": "MDXC",
        "config": next(f for f in files if f.endswith((".yaml", ".yml"))),
        "role": "general", "stems": stems, "voice_type": None,
        "display": display, "catalog_known": False,
    }
    registry.save_json(external_model_import.MANIFEST, existing)


class FirstRunModelDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("StemMIDI Studio · Instalación inicial de IA")
        self.resize(800, 625)
        self.setMinimumSize(620, 480)
        self.entries = _models()
        self.checks = {}
        self.queue = []
        self.proc = None
        self.stage = None
        self.current = None
        self.completed = 0
        self.offer_more = False
        self.skipped = False
        self._cancel_requested = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 15)
        lay.setSpacing(10)

        head = QLabel("Modelos de inteligencia artificial")
        head.setStyleSheet("font-size:19px; font-weight:700;")
        lay.addWidget(head)
        info = QLabel(
            "En esta instalación no se incluyen los pesos de las IA. "
            "Estas son las IAs utilizadas actualmente en el proyecto. "
            "Elige cuáles descargar; las que ya tengas instaladas se conservarán. "
            "Puedes instalar las demás después en Preferencias → Modelos de IA."
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        panel = QWidget()
        rows = QVBoxLayout(panel)
        rows.setSpacing(7)
        for entry in self.entries:
            row = QHBoxLayout()
            present = installed(entry)
            checkbox = QCheckBox(entry["name"])
            checkbox.setChecked(not present and bool(entry["recommended"]))
            checkbox.setEnabled(not present)
            checkbox.toggled.connect(self.update_summary)
            self.checks[entry["id"]] = checkbox
            row.addWidget(checkbox, 1)
            label = QLabel(
                ("Instalada" if present else _format_bytes(_size(entry)))
            )
            label.setMinimumWidth(96)
            label.setStyleSheet("color:#8fe4ee;" if present else "")
            row.addWidget(label)
            rows.addLayout(row)
        rows.addStretch()
        scroll.setWidget(panel)
        lay.addWidget(scroll, 1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.progress = QLabel("Ninguna descarga comenzará sin tu confirmación.")
        self.progress.setWordWrap(True)
        lay.addWidget(self.progress)

        bar = QHBoxLayout()
        self.install_btn = QPushButton("Instalar seleccionadas")
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self.start)
        bar.addWidget(self.install_btn)
        self.skip_btn = QPushButton("Más tarde · Iniciar sin descargar")
        self.skip_btn.clicked.connect(self.skip)
        bar.addWidget(self.skip_btn)
        self.cancel_btn = QPushButton("Cancelar descargas")
        self.cancel_btn.clicked.connect(self.cancel_downloads)
        self.cancel_btn.hide()
        bar.addWidget(self.cancel_btn)
        lay.addLayout(bar)
        self.update_summary()

    def update_summary(self):
        selected = [e for e in self.entries if self.checks[e["id"]].isChecked()]
        required = sum(_size(e) for e in selected)
        free = shutil.disk_usage(registry.HOME if registry.HOME.is_dir()
                                 else registry.HOME.parent).free
        present = sum(installed(e) for e in self.entries)
        self.summary.setText(
            f"{present} modelos instalados · {len(selected)} seleccionados · "
            f"descarga estimada {_format_bytes(required)} · "
            f"espacio libre {_format_bytes(free)}. "
            "Tamaños basados en los pesos verificados de esta versión."
        )
        self.install_btn.setEnabled(
            self.proc is None and self.current is None and not self.queue
            and bool(selected) and required + 300 * 1024**2 <= free
        )

    def _finish_user_choice(self, outcome):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        registry.save_json(STATE_FILE, {
            "schema": 1, "decision": outcome,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        self.offer_more = outcome == "installed"
        self.accept()

    def skip(self):
        if self.proc is not None:
            return
        self.skipped = True
        self._finish_user_choice("postponed")

    def start(self):
        if self.proc is not None:
            return
        self.queue = [e for e in self.entries
                      if self.checks[e["id"]].isChecked() and not installed(e)]
        if not self.queue:
            self._finish_user_choice("installed")
            return
        self.completed = 0
        self.install_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.cancel_btn.show()
        for check in self.checks.values():
            check.setEnabled(False)
        self._start_next()

    def _start_next(self):
        if not self.queue:
            self.cancel_btn.hide()
            self.progress.setText("Modelos instalados y comprobados.")
            self._finish_user_choice("installed")
            return
        self.current = self.queue.pop(0)
        entry = self.current
        registry.HOME.mkdir(parents=True, exist_ok=True)
        temp_root = registry.HOME / ".descargas_stemmidi"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.stage = Path(tempfile.mkdtemp(prefix="inicial_", dir=temp_root))
        self.progress.setText(
            f"Descargando {self.completed + 1} de "
            f"{self.completed + len(self.queue) + 1}: {entry['name']}"
        )
        if entry["method"] == "direct":
            python = ia_python(__file__)
            worker = worker_script(__file__, "model_download_worker.py")
            command = str(python)
            args = ["-B", str(worker), "--manifest", str(CATALOG_FILE),
                    "--model", entry["id"], "--stage", str(self.stage)]
        else:
            record = _record(entry)
            command = str(registry.engine_for(record))
            args = ["--model_filename", entry["id"],
                    "--model_file_dir", str(self.stage),
                    "--download_model_only"]
        if not Path(command).is_file():
            self._fail("No se encuentra el motor de IA: " + command)
            return
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._output)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._error)
        self.proc.start(command, args)

    def _output(self):
        if self.proc is None:
            return
        output = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines = [line.strip() for line in output.replace("\r", "\n").splitlines()
                 if line.strip()]
        if lines:
            self.progress.setText(
                f"{self.current['name']}: {lines[-1][:180]}"
            )

    def _error(self, code):
        if self.proc is not None and code == QProcess.FailedToStart:
            self._fail("No se pudo ejecutar el motor: " + self.proc.errorString())

    def _verify_stage(self, entry):
        for item in entry["files"]:
            name = Path(item["path"]).name
            source = self.stage / name
            if source.is_symlink() or not source.is_file():
                raise ValueError("Falta un archivo del modelo: " + name)
            if source.stat().st_size != int(item["bytes"]):
                raise ValueError("Tamaño inesperado: " + name)
            h = hashlib.sha256()
            with source.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != item["sha256"]:
                raise ValueError("Verificación SHA-256 fallida: " + name)

    def _promote(self, entry):
        self._verify_stage(entry)
        dest = _destination(entry)
        dest.mkdir(parents=True, exist_ok=True)
        backup_dir = registry.HOME / ".copias_modelos"
        moved = []
        promoted = []
        try:
            for item in entry["files"]:
                name = Path(item["path"]).name
                original = dest / name
                if original.is_symlink():
                    raise ValueError("Destino protegido por enlace simbólico: " + name)
                if original.is_file():
                    if not backup_dir.is_dir():
                        backup_dir.mkdir(parents=True, exist_ok=True)
                    backup = backup_dir / (self.stage.name + "_" + name)
                    original.rename(backup)
                    moved.append((original, backup))
                elif original.exists():
                    raise ValueError("Destino no válido: " + name)
                (self.stage / name).rename(original)
                promoted.append(original)
            _register_guitar(entry)
            registry.mark_managed(_record(entry))
        except Exception:
            for path in reversed(promoted):
                if path.is_file():
                    path.unlink()
            for original, backup in reversed(moved):
                if backup.is_file():
                    backup.rename(original)
            raise

    def _done(self, exitcode, status):
        if self.proc is None or self.current is None:
            return
        self._output()
        entry = self.current
        process = self.proc
        self.proc = None
        if process is not None:
            process.deleteLater()
        if self._cancel_requested:
            self._fail("Instalación cancelada. No se han modificado los modelos anteriores.")
            return
        if exitcode != 0 or status != QProcess.NormalExit:
            self._fail("La descarga ha fallado: " + entry["name"])
            return
        try:
            self._promote(entry)
        except (ValueError, OSError, KeyError) as exc:
            self._fail("No se pudo verificar o instalar " + entry["name"]
                       + ": " + str(exc))
            return
        self._clear_stage()
        self.current = None
        self.completed += 1
        self.update_summary()
        QTimer.singleShot(0, self._start_next)

    def _clear_stage(self):
        if self.stage is not None and self.stage.is_dir():
            root = registry.HOME / ".descargas_stemmidi"
            if self.stage.resolve().parent == root.resolve():
                shutil.rmtree(self.stage)
        self.stage = None

    def _fail(self, message):
        self.progress.setText(message + " Puedes volver a intentarlo o continuar.")
        if self.proc is not None:
            self.proc.kill()
            self.proc.deleteLater()
            self.proc = None
        self._clear_stage()
        self.current = None
        self.queue.clear()
        self._cancel_requested = False
        self.cancel_btn.hide()
        self.install_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        for entry in self.entries:
            self.checks[entry["id"]].setEnabled(not installed(entry))
        self.update_summary()

    def cancel_downloads(self):
        if self.proc is None:
            return
        self._cancel_requested = True
        self.progress.setText("Cancelando la descarga actual...")
        self.proc.kill()

    def closeEvent(self, event):
        if self.proc is not None or self.current is not None or self.queue:
            event.ignore()
            self.cancel_downloads()
        else:
            event.accept()


def startup(main, start_project):
    """Ejecutar después de la intro y ANTES del selector de proyectos."""
    if not CATALOG_FILE.is_file():
        QMessageBox.warning(main, "Modelos de IA",
                            "Falta el catálogo de IA de la distribución.")
        start_project()
        return
    state = registry.read_json(STATE_FILE, {})
    if state.get("schema") == 1 and state.get("decision") in ("installed", "postponed"):
        start_project()
        return
    try:
        models = _models()
        if all(installed(model) for model in models):
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            registry.save_json(STATE_FILE, {"schema": 1, "decision": "installed"})
            start_project()
            return
        dialog = FirstRunModelDialog(main)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        QMessageBox.warning(main, "Instalación inicial de IA", str(exc))
        start_project()
        return
    if dialog.exec() != QDialog.Accepted:
        main.close()
        return
    if dialog.offer_more:
        answer = QMessageBox.question(
            main, "Más modelos de inteligencia artificial",
            "StemMIDI dispone de más IAs opcionales. "
            "¿Quieres abrir ahora el catálogo completo? "
            "También podrás hacerlo más tarde desde Preferencias → Modelos de IA.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            from studio_shell import preferences
            preferences(main, open_models=True)
    try:
        main.workbench.separator.refresh_model_registry()
        main.drum_module.refresh_model_choices()
    except (AttributeError, RuntimeError):
        pass
    start_project()
