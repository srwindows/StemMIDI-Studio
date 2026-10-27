#!/usr/bin/env python3
"""Pruebas sin diálogos clásicos: proyecto, audio, multi, guardar y carpetas."""
import os,sys,tempfile,io
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer,Qt,QItemSelectionModel
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog
from studio_file_browser import StemFileBrowser,open_browser
from file_dialogs import _studio_picker, get_save_file_name,get_existing_directory
app=QApplication([])
with tempfile.TemporaryDirectory(prefix="stem_browser_") as td:
 root=Path(td)
 (root/"Discos y audios").mkdir()
 (root/"bateria.wav").write_bytes(b"123")
 (root/"melodia.flac").write_bytes(b"123")
 (root/"proyecto.stemstudio.json").write_text('{"testing":true}')
 (root/"readme.txt").write_text("text")
 def run(kind,filter_text,name,expect,subdir=False):
  def inspect():
   shown=[x for x in app.topLevelWidgets() if isinstance(x,StemFileBrowser)
          and x.isVisible()]
   assert len(shown)==1,shown
   dlg=shown[0]
   assert not any(x.isVisible() for x in app.topLevelWidgets()
                  if isinstance(x,QFileDialog)), "DIALOGO ANTIGUO DETECTADO"
   assert dlg.view.model() is dlg._proxy
   assert dlg.findChild(type(dlg.location),"") is not None
   dlg.grab().save("/tmp/stemmidi_browser_"+kind+".png")
   if subdir: dlg.go_to(root/"Discos y audios")
   if name:dlg.filename.setText(name)
   dlg.accept_selection()
  QTimer.singleShot(600,inspect)
  results,_=open_browser(None,"Prueba "+kind,str(root),filter_text,kind)
  assert [Path(x) for x in results]==expect,(kind,results,expect)
  print(kind,"PASS",results,flush=True)
 run("open","Proyecto StemMIDI (*.stemstudio.json *.json)","proyecto.stemstudio.json",[root/"proyecto.stemstudio.json"])
 run("open","Audio (*.wav *.flac *.mp3)","bateria.wav",[root/"bateria.wav"])
 run("save","Archivo WAV (*.wav)","mix_final",[root/"mix_final.wav"])
 run("dir","","",[root/"Discos y audios"],True)
 def multimode():
  dlg=next(x for x in app.topLevelWidgets() if isinstance(x,StemFileBrowser) and x.isVisible())
  for i,n in enumerate(("bateria.wav","melodia.flac")):
   src=dlg._model.index(str(root/n))
   idx=dlg._proxy.mapFromSource(src)
   assert idx.isValid(),n
   dlg.view.selectionModel().select(idx,
       QItemSelectionModel.Select|QItemSelectionModel.Rows)
  dlg.accept_selection()
 QTimer.singleShot(800,multimode)
 selected,_=open_browser(None,"Seleccionar pistas",str(root),"Audio (*.wav *.flac)","multi")
 assert sorted(selected)==sorted(map(str,(root/"bateria.wav",root/"melodia.flac"))),selected
 print("multi PASS",selected,flush=True)
 print("FIVE_BROWSER_MODES_PROJECT_AUDIO_SAVE_FOLDER_MULTIPLE_PASS")
