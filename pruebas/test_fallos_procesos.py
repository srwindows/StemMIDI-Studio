#!/usr/bin/env python3
"""Los motores inexistentes liberan GUI y no bloquean cambios de proyecto."""
import os,sys,tempfile,time
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_failed_start_") as tmp:
    os.environ["STEMMIDI_WORKSPACE"]=tmp
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication
    from main import MonitorWindow
    app=QApplication([])
    gui=MonitorWindow()
    vocal=gui.vocal_module
    job=QProcess(vocal)
    job.finished.connect(vocal._finished)
    job.errorOccurred.connect(vocal._error)
    vocal._operation="tune"
    vocal.processing_file=None
    vocal.process=job
    vocal._set_busy(True)
    job.start("/__stemmidi_no_existe__/vocal",[])
    drums=gui.drum_module
    drums._start_process_command(["/__stemmidi_no_existe__/drums"],"normalize")
    deadline=time.monotonic()+6
    while time.monotonic()<deadline and (vocal.process is not None or drums.process is not None):
        app.processEvents()
        time.sleep(.01)
    assert vocal.process is None, "Motor vocal sigue bloqueado"
    assert drums.process is None, "Motor batería sigue bloqueado"
    assert vocal.start_button.isEnabled(), "Botón de voz no restaurado"
    assert drums.start_btn.isEnabled(), "Botón de batería no restaurado"
    print("NO_ENGINE_VOCAL_AND_DRUM_UNLOCK_OK")
