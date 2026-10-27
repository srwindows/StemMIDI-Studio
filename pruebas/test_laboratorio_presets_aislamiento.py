#!/usr/bin/env python3
"""Presets del laboratorio y aislamiento entre proyectos, todo en carpeta temporal."""
import os,sys,tempfile,json
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_lab_presets_") as root:
 os.environ["STEMMIDI_WORKSPACE"]=root
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QMessageBox
 from main import MonitorWindow
 from project_flow import create_named_project
 from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
 from recording_lab_engine import DEFAULT
 from ux_controls import PRESET_DIR
 app=QApplication([])
 QMessageBox.warning=staticmethod(lambda *a:QMessageBox.Ok)
 QMessageBox.information=staticmethod(lambda *a:QMessageBox.Ok)
 win=MonitorWindow()
 fmt=next(iter(FORMAT_OPTIONS))
 rate=next(iter(SAMPLE_RATES))
 assert create_named_project(win,"Primero",str(Path(root)/"proyectos"),fmt,rate)
 lab=win.recording_lab
 lab.controls["bass"].setValue(7)
 lab.controls["denoise"].setValue(16)
 lab.auto_after.setChecked(True)
 lab.presets.name.setText("Mi estudio silencioso")
 lab.presets.save_custom()
 path=PRESET_DIR/"laboratorio_grabacion.json"
 assert path.is_file(),path
 d=json.loads(path.read_text(encoding="utf-8"))
 assert d["Mi estudio silencioso"]["bass"]==7
 assert d["Mi estudio silencioso"]["denoise"]==16
 assert d["Mi estudio silencioso"]["auto_after"] is True
 print("LAB_USER_PRESET_PERSISTENCE_PASS",flush=True)
 assert create_named_project(win,"Segundo",str(Path(root)/"proyectos"),fmt,rate)
 assert lab.snapshot()==DEFAULT,(lab.snapshot(),DEFAULT)
 assert lab.original is None and lab.processed is None
 print("LAB_NEW_PROJECT_DOES_NOT_INHERIT_FX_PASS",flush=True)
 for index in range(lab.presets.choices.count()):
  key=lab.presets.choices.itemData(index)
  if key==("propio","Mi estudio silencioso"):
   lab.presets.choices.setCurrentIndex(index);break
 else:raise AssertionError("custom preset not listed")
 assert lab.controls["bass"].value()==7
 assert lab.controls["denoise"].value()==16
 assert lab.auto_after.isChecked()
 print("LAB_USER_PRESET_LOADS_IN_ANOTHER_PROJECT_WHEN_SELECTED_PASS",flush=True)
print("LAB_PRESETS_PROJECT_ISOLATION_OK",flush=True)
