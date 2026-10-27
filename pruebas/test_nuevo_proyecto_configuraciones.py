#!/usr/bin/env python3
"""Proyecto nuevo mantiene controles completos, nunca pistas/rutas. Presets por módulo."""
import os,sys,json,tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stem_new_project_config_") as tmp:
 os.environ["STEMMIDI_WORKSPACE"]=tmp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QMessageBox
 from main import MonitorWindow
 from project_flow import create_named_project
 from studio_shell import save_project,project_payload
 from studio_settings_library import (capture_settings,apply_settings,save_named,load_named,
  delete_named,read_library,settings_dialog,can_apply,LIBRARY_FILE)
 app=QApplication([])
 main=MonitorWindow()
 base=Path(tmp)/"proyectos"
 fmt=main.format.currentText()
 rate=main.capture_rate.currentData()
 assert create_named_project(main,"Proyecto_ANTERIOR",base,fmt,rate)
 previous=Path(main.project_dir)
 old_manifest=Path(main.project_path)
 old_id=main.project_id
 old_audio=previous/"grabaciones"/"original_protegido.wav"
 old_audio.write_bytes(b"NO BORRAR")
 main.last_file=str(old_audio)
 main.workbench.separator.quality.setCurrentText(
     "Alta (más detalle)" if main.workbench.separator.quality.findText("Alta (más detalle)")>=0
        else main.workbench.separator.quality.itemText(0))
 main.set_input_processing(-4,35)
 main.recording_lab.controls["bass"].setValue(6)
 main.drum_module.studio.seq_bpm.setValue(147)
 main.drum_module.studio.seq_swing.setValue(38)
 main.vocal_module.strength.setValue(82)
 main.workbench.piano.set_beat_zoom(71)
 before=capture_settings(main)
 assert len(before)==9,list(before)
 # Un nombre personal para el conjunto completo, otro para un solo módulo.
 full_id=save_named(main,"Estudio_personal","Todos los módulos")
 drums_id=save_named(main,"Batería potente","Desglose de batería")
 assert len(read_library())==2
 assert LIBRARY_FILE.is_file()
 try:
  save_named(main,"Estudio_personal","Todos los módulos")
  raise AssertionError("Se permitió sobrescribir un preset sin confirmación")
 except FileExistsError:pass
 assert save_project(main,show_confirmation=False)
 assert create_named_project(main,"Proyecto_NUEVO",base,
      main.format.currentText(),main.capture_rate.currentData(),
      inherit_settings=True)
 dest=Path(main.project_dir)
 assert dest!=previous and dest.name=="Proyecto_NUEVO",dest
 assert main.project_id!=old_id
 assert main.project_name=="Proyecto_NUEVO"
 assert main.file_prefix.text()=="Proyecto_NUEVO"
 assert main.folder_display.text()==str(dest/"grabaciones")
 assert main.workbench.separator.file_edit.text()==""
 assert main.workbench.converter.audio_path.text()==""
 assert main.last_file is None
 assert not main.project_recordings
 assert old_manifest.is_file() and old_audio.read_bytes()==b"NO BORRAR"
 after=capture_settings(main)
 for module in before:
  if before[module]!=after[module]:
   print("DIFFERENCE",module,before[module],after[module],flush=True)
 assert before==after,"Nuevo proyecto no mantuvo TODOS los parámetros"
 assert not any(str(previous) in json.dumps(v) for v in after.values())
 assert json.loads(Path(main.project_path).read_text())["parameters_recording_lab"]["bass"]==6
 print("NEW_PROJECT_SETTINGS_ALL_MODULES_AND_MEDIA_ISOLATION_PASS")
 main.drum_module.studio.seq_bpm.setValue(110)
 main.recording_lab.controls["bass"].setValue(-2)
 load_named(main,drums_id)
 assert main.drum_module.studio.seq_bpm.value()==147
 assert main.recording_lab.controls["bass"].value()==-2
 load_named(main,full_id)
 assert main.recording_lab.controls["bass"].value()==6
 assert main.drum_module.studio.seq_bpm.value()==147
 print("GLOBAL_AND_INDIVIDUAL_PRESET_RESTORE_PASS")
 assert delete_named(drums_id)
 assert len(read_library())==1
 assert save_project(main,show_confirmation=False)
 # Tras cerrar y abrir otra vez la librería no se pierde.
 assert full_id in read_library()
 assert can_apply(main)
 print("PRESET_SAVE_DELETE_PERSISTENCE_PASS")
 main.close()
 print("NEW_PROJECT_AND_ALL_MODULE_PRESETS_TOTAL_PASS")
