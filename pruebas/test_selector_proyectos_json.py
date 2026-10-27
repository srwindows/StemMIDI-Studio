#!/usr/bin/env python3
"""La extensión .stemstudio.json no es un archivo MIDI."""
import os,tempfile,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QMessageBox
import file_dialogs
with tempfile.TemporaryDirectory(prefix='stemmidi_selector_json_') as t:
 a=QApplication([])
 p=Path(t)/"Mi_cancion.stemstudio.json";p.write_text('{"application":"StemMIDI Studio"}')
 midi=Path(t)/"notas.mid";midi.write_bytes(b"MThd")
 incoming=[[str(p)],[str(p)],[str(midi)]]
 orig=file_dialogs._kde_picker
 orig_audition=file_dialogs._audition_one
 orig_warning=QMessageBox.warning
 warned=[]
 try:
  file_dialogs._kde_picker=lambda *a,**k:incoming.pop(0)
  file_dialogs._audition_one=lambda *a,**k:1
  QMessageBox.warning=staticmethod(lambda *args:warned.append(args[1]) or QMessageBox.Ok)
  path,_=file_dialogs.get_open_file_name(None,"Abrir proyecto StemMIDI",str(p),
                    "Proyecto StemMIDI (*.stemstudio.json *.json)")
  assert path==str(p) and not warned,(path,warned)
  print('SELECTOR_PROYECTO_JSON_ADMITIDO',flush=True)
  path,_=file_dialogs.get_open_file_name(None,"Abrir MIDI",str(p),
                    "Archivo MIDI (*.mid *.midi *.kar)")
  assert path==str(midi) and len(warned)==1,(path,warned)
  print('SELECTOR_MIDI_RECHAZA_JSON_CORRECTAMENTE',flush=True)
 finally:
  file_dialogs._kde_picker=orig
  file_dialogs._audition_one=orig_audition
  QMessageBox.warning=orig_warning
print('SELECTOR_EXTENSIONS_OK',flush=True)
