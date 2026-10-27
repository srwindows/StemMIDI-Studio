#!/usr/bin/env python3
"""Prueba de humo: captura real breve y eliminación del archivo de prueba."""
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QTimer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_engine import CaptureWorker, FORMAT_OPTIONS, default_monitor

app = QCoreApplication([])
source = default_monitor()
if not source:
    raise SystemExit("No hay un dispositivo de salida predeterminado.")
result = ROOT / "pruebas" / "validacion_temporal.flac"
result.unlink(missing_ok=True)
worker = CaptureWorker(source)
outcome = {"captured": False, "recorded": False, "finished": False}

def state(working, message):
    print("AUDIO:", working, message, flush=True)
    if working:
        outcome["captured"] = True

def rec_done(path, success, msg):
    print("GRABACION:", success, msg, flush=True)
    outcome["recorded"] = success
    outcome["finished"] = True

def finish():
    worker.stop_capture()
    worker.wait(3000)
    size = result.stat().st_size if result.exists() else 0
    print("RESULTADOS:", outcome, "tamaño:", size, flush=True)
    result.unlink(missing_ok=True)
    app.exit(0 if all(outcome.values()) and size > 80 else 3)

worker.capture_state.connect(state)
worker.recording_finished.connect(rec_done)
worker.start()
QTimer.singleShot(450, lambda: worker.request_recording(result, "FLAC (sin pérdida)"))
QTimer.singleShot(1950, worker.request_stop_recording)
QTimer.singleShot(3700, worker.stop_capture)
QTimer.singleShot(4700, finish)
sys.exit(app.exec())
