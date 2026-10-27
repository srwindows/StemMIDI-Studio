#!/usr/bin/env python3
"""Prueba integrada de Guardar, Abrir, Guardar como y Revertir proyecto."""
import os,sys,tempfile,zipfile,json,hashlib,wave
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
with tempfile.TemporaryDirectory(prefix='stemmidi_project_full_') as scratch:
 root=Path(scratch)
 os.environ['STEMMIDI_WORKSPACE']=str(root)
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 import file_dialogs
 from PySide6.QtWidgets import QApplication,QMessageBox
 from main import MonitorWindow
 from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
 from project_flow import create_named_project
 from studio_shell import save_project,open_project,project_payload
 from project_session import restore_snapshot,clone_project,inside
 app=QApplication([])
 QMessageBox.warning=staticmethod(lambda *a,**k:(_ for _ in ()).throw(
       AssertionError('UNEXPECTED_WARNING: '+str(a[1:3]))))
 QMessageBox.information=staticmethod(lambda *a,**k:QMessageBox.Ok)
 QMessageBox.question=staticmethod(lambda *a,**k:QMessageBox.No)
 win=MonitorWindow()
 fmt=next(iter(FORMAT_OPTIONS));rate=next(iter(SAMPLE_RATES))
 assert create_named_project(win,'Mi proyecto',str(root/'proyectos'),fmt,rate)
 project=Path(win.project_dir)
 from project_layout import DIRECTORIES
 assert {p.name for p in project.iterdir() if p.is_dir()}==set(DIRECTORIES)
 manifest=Path(win.project_path)
 external=root/'externo.wav'
 with wave.open(str(external),'wb') as f:
  f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
  f.writeframes(bytes(32000))
 digest=hashlib.sha256(external.read_bytes()).hexdigest()
 win.workbench.separator.file_edit.setText(str(external))
 win.workbench.converter.audio_path.setText(str(external))
 win.drum_module.input.setText(str(external))
 win.vocal_module.input.setText(str(external))
 win.vocal_module.ref_consent.setChecked(True)
 win.vocal_module.reference.setText(str(external))
 folder_sources=root/"lote_audio_original"
 folder_sources.mkdir()
 (folder_sources/"guitarra.wav").write_bytes(external.read_bytes())
 win.workbench.converter.folder_path.setText(str(folder_sources))
 win.workbench.converter.use_folder.setChecked(True)
 win.vocal_module.warmth.setValue(49)
 win.workbench.converter.onset.setValue(.47)
 win.workbench.converter.detect_chords.setChecked(True)
 # Nota MIDI editada en memoria; Guardar proyecto debe incluirla.
 import mido
 midi=mido.MidiFile(type=1)
 tr=mido.MidiTrack()
 tr.append(mido.Message("note_on",note=62,velocity=80,time=0))
 tr.append(mido.Message("note_off",note=62,velocity=0,time=480))
 midi.tracks.append(tr)
 midi_source=project/"temporales"/"midi"/"piano_fuente.mid"
 midi_source.parent.mkdir(parents=True,exist_ok=True)
 midi.save(midi_source)
 win.workbench.show_piano_roll(midi_source)
 assert win.workbench.piano.midi is not None
 win.workbench.piano.dirty=True
 assert save_project(win)
 assert (project/"temporales"/"midi"/"piano_roll_sesion.mid").is_file()
 assert not list((project/"temporales"/"midi").glob("_piano_nuevo_*.mid"))
 print("PIANO_ROLL_MEMORIA_GUARDADA_EN_TEMPORALES",flush=True)
 initial=json.loads(manifest.read_text(encoding='utf-8'))
 assert initial['version']==3
 for field in ('source_separation','source_midi','drum_input','vocal_input'):
  assert inside(initial[field],project/'temporales'),(field,initial[field])
  assert Path(initial[field]).is_file()
 assert initial['parameters_midi']['onset']==.47
 assert initial["midi_use_folder"] is True
 assert inside(initial["midi_source_folder"],project/"temporales")
 assert (Path(initial["midi_source_folder"])/"guitarra.wav").is_file()
 assert inside(initial["vocal_reference"],project/"temporales")
 assert initial["vocal_reference_authorized"] is True
 assert initial['parameters_vocal_full']['warmth']==49
 assert initial["midi_editor_file"]==str(project/"temporales"/"midi"/"piano_roll_sesion.mid")
 assert len(initial['project_files'])>0
 assert save_project(win)
 assert list(project.glob('*.stemstudio.json'))==[manifest]
 assert not list((project/'backup').glob('Antes_de_abrir_*.zip'))
 print('GUARDAR_DOS_VECES_SOBRESCRIBE_UN_MANIFIESTO_OK',flush=True)
 assert open_project(win,str(manifest)) is True
 copies=list((project/'backup').glob('Antes_de_abrir_*.zip'))
 assert len(copies)==1
 with zipfile.ZipFile(copies[0]) as z:
  assert z.testzip() is None and manifest.name in z.namelist()
  assert any(p.startswith('temporales/importados/') for p in z.namelist())
 assert win.vocal_module.warmth.value()==49
 assert win.workbench.converter.onset.value()==.47
 assert win.workbench.converter.detect_chords.isChecked()
 assert Path(win.workbench.converter.audio_path.text()).is_file()
 assert win.workbench.converter.use_folder.isChecked()
 assert (Path(win.workbench.converter.folder_path.text())/"guitarra.wav").is_file()
 assert win.vocal_module.ref_consent.isChecked()
 assert Path(win.vocal_module.reference.text()).is_file()
 print("CARPETA_AUDIO_Y_REFERENCIA_VOCAL_RESTAURADAS",flush=True)
 print('ABRIR_JSON_Y_CREAR_BACKUP_COMPLETO_OK',flush=True)
 clone_path=clone_project(project,root/'proyectos','Mi proyecto nuevo')
 assert clone_path.is_file() and clone_path.parent !=project
 clone=json.loads(clone_path.read_text(encoding='utf-8'))
 assert clone['project_id']!=initial['project_id']
 assert inside(clone['source_midi'],clone_path.parent)
 assert Path(clone['source_midi']).read_bytes()==external.read_bytes()
 assert not any(inside(v,project) for v in (
     clone['source_midi'],clone['vocal_input'],clone['drum_input']))
 print('GUARDAR_COMO_NOMBRE_Y_RUTA_REBASE_OK',flush=True)
 modified=dict(initial,notice='CAMBIADO')
 manifest.write_text(json.dumps(modified,ensure_ascii=False))
 restored=restore_snapshot(project,copies[0])
 assert manifest in restored
 after=json.loads(manifest.read_text())
 assert after['notice']!='CAMBIADO'
 assert digest==hashlib.sha256(external.read_bytes()).hexdigest()
 print('REVERTIR_BACKUP_RESTABLECE_ARCHIVOS_SIN_TOCAR_ORIGINALES_OK',flush=True)
print('TEST_PROYECTO_COMPLETO_SUPERADO',flush=True)
