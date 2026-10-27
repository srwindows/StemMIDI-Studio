#!/usr/bin/env python3
"""Separador real (sin modelos IA) dos tandas: guardar siempre en stems sin carpetas nuevas."""
import os,sys,time,tempfile,wave
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
from PySide6.QtWidgets import QApplication,QMessageBox
from main import MonitorWindow
from project_flow import create_named_project
from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
from separador import MODELS
import numpy as np

with tempfile.TemporaryDirectory(prefix="stemmidi_real_stems_two_runs_") as directory:
 os.environ["STEMMIDI_WORKSPACE"]=directory
 root=Path(directory)
 app=QApplication([])
 QMessageBox.information=staticmethod(lambda *args:QMessageBox.Ok)
 QMessageBox.question=staticmethod(lambda *args,**kwargs:QMessageBox.Yes)
 QMessageBox.warning=staticmethod(lambda *args:(_ for _ in ()).throw(
     AssertionError("ALERTA "+str(args[1:3]))))
 main=MonitorWindow()
 assert create_named_project(main,"Prueba stems",root/"mía",
         next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
 project=Path(main.project_dir)
 input_file=root/"voz_estereo.wav"
 t=np.arange(22050)/22050.
 stereo=np.stack((np.sin(2*np.pi*220*t),np.sin(2*np.pi*330*t)),axis=1)
 with wave.open(str(input_file),"wb") as f:
  f.setnchannels(2);f.setsampwidth(2);f.setframerate(22050)
  f.writeframes((stereo*16000).astype("<i2").tobytes())
 separator=main.workbench.separator
 mode=next(k for k,v in MODELS.items() if v is None)
 separator.profile.setCurrentText(mode)
 separator.export_fmt.setCurrentText("WAV (PCM)")
 assert separator.profile.currentText()==mode
 first_roots=set(x.relative_to(project).as_posix() for x in project.rglob("*") if x.is_dir())
 for batch in (1,2):
  separator.file_edit.setText(str(input_file))
  separator.start_separation()
  started=time.monotonic()
  while (separator.busy or not main.workbench.separation_storage.items) and time.monotonic()-started<35:
   app.processEvents()
   time.sleep(.03)
  assert not separator.busy,("still separating",separator.log.toPlainText()[-1000:])
  saved_paths=main.workbench.separation_storage.items
  assert len(saved_paths)==2,(batch,saved_paths,separator.log.toPlainText()[-800:])
  assert all(p.parent==project/"temporales"/"separaciones"/"sesion"/"procesado" for p in saved_paths)
  output=main.workbench.separation_storage.save(project/"backup"/"separaciones",all_files=True)
  assert len(output)==2 and all(x.parent==project/"stems" for x in output)
  assert not list((project/"stems").glob("*/"))
  assert not (project/"backup"/"separaciones").exists()
  print("REAL_SEPARATOR_BATCH_SAVED",batch,[x.name for x in output],flush=True)
 assert len(list((project/"stems").iterdir()))==4
 assert not any(p.is_dir() for p in (project/"stems").iterdir())
 # No folder named after the original file or after the time.
 temp=project/"temporales"/"separaciones"
 assert {p.name for p in temp.iterdir() if p.is_dir()}=={"sesion"}
 proc=temp/"sesion"/"procesado"
 assert all(not f.is_dir() for f in proc.iterdir()
            if f.name!="_importacion_temporal")
 assert set(x.name for x in project.iterdir() if x.is_dir()) == {
     "grabaciones","stems","bateria","audio_a_midi",
     "afinacion_vocal","mezclador","piano_roll","resultados",
     "temporales","backup"}
 print("TWO_REAL_SEPARATIONS_WITHOUT_NESTED_FOLDERS_PASS",flush=True)
