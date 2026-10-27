#!/usr/bin/env python3
"""Crear proyecto: vista previa carpeta/JSON y estado del directorio en vivo."""
import os,sys,tempfile,time
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
from PySide6.QtWidgets import QApplication,QDialog,QLineEdit,QLabel
from main import MonitorWindow
from project_flow import new_project_dialog

app=QApplication([])
with tempfile.TemporaryDirectory(prefix="stemmidi_create_live_") as scratch:
    container=Path(scratch)/"mía"
    container.mkdir()
    win=MonitorWindow()
    orig=QDialog.exec
    def fake_exec(dialog):
        lines=dialog.findChildren(QLineEdit)
        inp=next(w for w in lines if "octubre" in w.placeholderText())
        base=next(w for w in lines if w is not inp)
        preview=next(w for w in dialog.findChildren(QLabel)
                     if "Carpeta del proyecto:" in w.text()
                     or "Escribe el nombre del proyecto" in w.text())
        inp.setText("yo")
        base.setText(str(container))
        app.processEvents()
        assert "Carpeta del proyecto: "+str(container/"yo")+"/" in preview.text()
        assert "yo.stemstudio.json" in preview.text()
        assert "NO carpeta" in preview.text()
        assert "Disponible" in preview.text()
        print("PREVIEW_CHANGES_NAME_AND_BASE_WITHOUT_DOUBLE_FOLDER",flush=True)
        actual=container/"yo";actual.mkdir()
        deadline=time.monotonic()+1.65
        while time.monotonic()<deadline:
            app.processEvents();time.sleep(.035)
        assert "Disponible: carpeta vacía" in preview.text(),preview.text()
        (actual/"ocupado.txt").write_text("no borrar",encoding="utf-8")
        deadline=time.monotonic()+1.65
        while time.monotonic()<deadline:
            app.processEvents();time.sleep(.035)
        assert "No disponible: hay archivos" in preview.text(),preview.text()
        print("PREVIEW_DETECTS_EXTERNAL_CREATION_AND_FILES_REALTIME",flush=True)
        return QDialog.Rejected
    QDialog.exec=fake_exec
    try:
        assert not new_project_dialog(win)
    finally:
        QDialog.exec=orig
    assert (container/"yo"/"ocupado.txt").read_text()=="no borrar"
print("LIVE_CREATE_PREVIEW_TEST_PASS",flush=True)
