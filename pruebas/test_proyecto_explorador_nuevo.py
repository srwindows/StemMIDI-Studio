#!/usr/bin/env python3
"""Verifica el camino real usado por Abrir proyecto, sin selector Qt antiguo."""
import os,sys,tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QFileDialog
from PySide6.QtCore import QTimer
import file_dialogs, dialog_guard
from studio_file_browser import StemFileBrowser
app=QApplication([])
dialog_guard.install(app)
with tempfile.TemporaryDirectory(prefix="stem_real_project_open_") as tmp:
 project=Path(tmp)/"mi_prueba.stemstudio.json"
 project.write_text('{"kind":"project"}',encoding="utf8")
 def choose():
  dialogs=[d for d in app.topLevelWidgets() if isinstance(d,StemFileBrowser) and d.isVisible()]
  assert len(dialogs)==1,dialogs
  dlg=dialogs[0]
  assert not any(isinstance(d,QFileDialog) and d.isVisible() for d in app.topLevelWidgets())
  assert dlg.types.currentText()=="Proyecto StemMIDI (*.stemstudio.json *.json)"
  dlg.filename.setText(project.name)
  dlg.accept_selection()
 QTimer.singleShot(500,choose)
 chosen,_=file_dialogs.get_open_file_name(None,"Abrir proyecto StemMIDI",tmp,
                                    "Proyecto StemMIDI (*.stemstudio.json *.json)")
 assert chosen==str(project),chosen
 print("PROJECT_FLOW_REAL_OPEN_PATH_PASS",flush=True)
