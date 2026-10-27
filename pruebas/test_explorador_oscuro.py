#!/usr/bin/env python3
"""El explorador moderno no crea JFileDialog/KDialog heredados."""
import os,sys,tempfile
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QFileDialog
from PySide6.QtCore import QTimer
from studio_file_browser import StemFileBrowser
from file_dialogs import _studio_picker
app=QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    source=Path(tmp)/"audio.wav"
    source.write_bytes(b"testing")
    def choose():
        dlg=next(w for w in app.topLevelWidgets() if isinstance(w,StemFileBrowser) and w.isVisible())
        assert dlg.view.model() is dlg._proxy
        assert dlg.windowTitle().startswith("StemMIDI")
        assert not any(isinstance(w,QFileDialog) and w.isVisible() for w in app.topLevelWidgets())
        dlg.filename.setText("audio.wav")
        dlg.accept_selection()
    QTimer.singleShot(450,choose)
    selected,_=_studio_picker(None,"Abrir audio",tmp,"Audio (*.wav)","open")
    assert selected==[str(source)],selected
    print("EXPLORADOR_MODERNO_UNICO_PASS")
