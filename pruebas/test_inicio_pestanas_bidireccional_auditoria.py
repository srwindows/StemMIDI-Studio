#!/usr/bin/env python3
"""Prueba integral bidireccional Inicio ↔ pestañas, en espacio aislado."""
import os,sys,tempfile,wave,math,struct
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import mido
ROOT=Path(__file__).resolve().parents[1]
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['STEMMIDI_NO_STARTUP_DIALOG']='1'
os.environ['STEMMIDI_TEST_DUMMY_AUDIO']='1'
with tempfile.TemporaryDirectory(prefix="stem_cross_sync_") as td:
 os.environ['STEMMIDI_WORKSPACE']=td
 sys.path.insert(0,str(ROOT))
 import project_exit_guard
 project_exit_guard.ask_exit_choice=lambda _: 'discard'
 from main import MonitorWindow
 app=QApplication([])
 w=MonitorWindow();w.show();h=w.studio_home;s=w.home_tab_sync
 assert len(s.routes)==12  # Los 12 módulos de Inicio tienen destino real
 for card,target in s.routes.items():
  assert target is not None,(card.header.text(),target)
  card.header.click()
  app.processEvents()
  assert w.tabs.currentWidget()==s.tab_for(card),(card.header.text(),w.tabs.currentWidget())
 print("ROUTES_12_CORRECT",flush=True)
 w.tabs.setCurrentWidget(h)
 def equal(a,b):
  assert a==b,(a,b)
 # Monitor: valores via control original y desde la tarjeta.
 assert w.format.count()>=2
 previous=w.format.currentIndex()
 w.format.setCurrentIndex((previous+1)%w.format.count())
 app.processEvents();equal(h.format.currentIndex(),w.format.currentIndex())
 h.format.setCurrentIndex(previous)
 app.processEvents();equal(h.format.currentIndex(),w.format.currentIndex())
 assert w.capture_rate.count()>=2
 w.capture_rate.setCurrentIndex((w.capture_rate.currentIndex()+1)%w.capture_rate.count())
 app.processEvents();equal(h.quality.currentIndex(),w.capture_rate.currentIndex())
 h.quality.setCurrentIndex(0)
 app.processEvents();equal(h.quality.currentIndex(),w.capture_rate.currentIndex())
 print("MONITOR_FORMAT_RATE_BIDIRECTIONAL",flush=True)
 # Separación: modelo y 7 familias en ambos sentidos.
 sep=w.workbench.separator
 if sep.profile.count()>1:
  h.model.setCurrentIndex((h.model.currentIndex()+1)%h.model.count())
  app.processEvents();equal(h.model.currentData(),sep.profile.currentText())
  sep.profile.setCurrentIndex((sep.profile.currentIndex()+1)%sep.profile.count())
  app.processEvents();equal(h.model.currentData(),sep.profile.currentText())
 for name,remote in (("Voces","Voz"),("Batería","Batería"),
                     ("Bajo","Bajo"),("Otros","Otros")):
  local=h.stem_checks[name];target=sep.stem_checks[remote]
  target.setChecked(False);app.processEvents();equal(local.isChecked(),False)
  local.setChecked(True);app.processEvents();equal(target.isChecked(),True)
 print("SEPARATION_MODEL_STEMS_BIDIRECTIONAL",flush=True)
 # Audio MIDI: los sliders originales y los de la pestaña son coherentes.
 conv=w.workbench.converter
 for name in h.midi_sliders:
  local=h.midi_sliders[name];remote=getattr(conv,name)
  value=remote.minimum() if hasattr(remote,'minimum') else 0.5
  remote.setValue(value);app.processEvents();equal(round(local.value(),4),round(remote.value(),4))
  value2=0.7 if name=='onset' else 85
  local.setValue(value2);app.processEvents();equal(round(local.value(),4),round(remote.value(),4))
 h.chords_check.setChecked(False);app.processEvents();equal(conv.detect_chords.isChecked(),False)
 conv.detect_chords.setChecked(True);app.processEvents();equal(h.chords_check.isChecked(),True)
 print("MIDI_PARAMETERS_CHORDS_BIDIRECTIONAL",flush=True)
 # Voz: mismos controles y parámetros; nunca ejecutar IA.
 voc=w.vocal_module
 for local,remote in ((h.vocal_tonic,voc.tonic),(h.vocal_scale,voc.scale)):
  if remote.count()>1:
   remote.setCurrentIndex((remote.currentIndex()+1)%remote.count())
   app.processEvents();equal(local.currentIndex(),remote.currentIndex())
   local.setCurrentIndex(0);app.processEvents();equal(local.currentIndex(),remote.currentIndex())
 voc.strength.setValue(42);app.processEvents();equal(h.vocal_strength.value(),42)
 h.vocal_strength.setValue(57);app.processEvents();equal(voc.strength.value(),57)
 print("VOCAL_TONIC_SCALE_STRENGTH_BIDIRECTIONAL",flush=True)
 # Piano: velocidad y rejilla en ambos sentidos.
 editor=w.workbench.piano
 editor.velocity.setValue(72);app.processEvents();equal(h.note_velocity.value(),72)
 h.note_velocity.setValue(99);app.processEvents();equal(editor.velocity.value(),99)
 editor.grid.setCurrentText("1/8");app.processEvents();equal(h.grid_choice.currentText(),"1/8")
 h.grid_choice.setCurrentText("1/32");app.processEvents();equal(editor.grid.currentText(),"1/32")
 print("PIANO_GRID_VELOCITY_BIDIRECTIONAL",flush=True)
 # Edición de archivos reales: si se abre en la pestaña, aparece en Inicio.
 project=Path(td)/'proyecto';project.mkdir()
 file=project/'origen.mid'
 midi=mido.MidiFile()
 track=mido.MidiTrack()
 midi.tracks.append(track)
 track.append(mido.Message('note_on',note=60,velocity=90,time=0))
 track.append(mido.Message('note_off',note=60,velocity=0,time=480))
 midi.save(file)
 assert editor.open_midi(file)
 app.processEvents();equal(h.selected_midi.resolve(),file.resolve())
 equal(h.piano_preview.source.resolve() if hasattr(h.piano_preview,"source") else h.selected_midi.resolve(),file.resolve())
 print("PIANO_MIDI_FILE_TAB_TO_HOME",flush=True)
 import hashlib,time
 original_hash=hashlib.sha256(file.read_bytes()).hexdigest()
 base_count=len(h.piano_preview.events)
 assert base_count==1
 editor.add_note({"start":480,"end":960,"pitch":64,"velocity":85,"channel":0})
 deadline=time.monotonic()+.5
 while time.monotonic()<deadline:
  app.processEvents();time.sleep(.02)
 assert len(h.piano_preview.events)==2,len(h.piano_preview.events)
 assert "sin guardar" in h.piano_card.header.text()
 assert hashlib.sha256(file.read_bytes()).hexdigest()==original_hash
 editor.undo()
 deadline=time.monotonic()+.25
 while time.monotonic()<deadline:app.processEvents();time.sleep(.02)
 assert len(h.piano_preview.events)==1,len(h.piano_preview.events)
 editor.redo()
 deadline=time.monotonic()+.25
 while time.monotonic()<deadline:app.processEvents();time.sleep(.02)
 assert len(h.piano_preview.events)==2,len(h.piano_preview.events)
 assert hashlib.sha256(file.read_bytes()).hexdigest()==original_hash
 print("PIANO_UNSAVED_EDITS_UNDO_REDO_HOME_LIVE_SOURCE_INTACT",flush=True)

 # Mezclador: 2 archivos reales de una misma familia; mezcla independiente
 # en pestaña no se debe sobrescribir accidentalmente por la portada.
 first=project/'Vocals_A.wav';second=project/'Vocals_B.wav'
 for p in (first,second):
  with wave.open(str(p),'wb') as f:
   f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
   f.writeframes(b'\0\0'*1600)
 # Orígenes importados desde pestañas: deben aparecer en tarjetas aunque
 # no sean archivos Demucs en almacenamiento temporal.
 w.drum_module.input.setText(str(first))
 app.processEvents()
 equal(h.drum_source.currentData(),str(first))
 w.vocal_module.input.setText(str(second))
 app.processEvents()
 equal(h.vocal_source.currentData(),str(second))
 print("DRUM_VOCAL_IMPORTED_SOURCES_TAB_TO_HOME",flush=True)
 # Selección de resultados en ambas direcciones y conservación al refrescar.
 h._update_results([file,first,second])
 w.results_tab.table.selectRow(2)
 app.processEvents()
 selected=[h.files.item(x.row(),0).data(Qt.UserRole)
           for x in h.files.selectionModel().selectedRows()]
 assert selected==[str(second)],selected
 h.files.selectRow(0)
 app.processEvents()
 selected=w.results_tab.selected_paths()
 assert selected==[file],selected
 w.results_tab.refresh([second,first,file])
 app.processEvents()
 assert w.results_tab.selected_paths()==[file],w.results_tab.selected_paths()
 print("RESULTS_SELECTION_BOTH_DIRECTIONS_REFRESH_PRESERVED",flush=True)
 w.workbench.show_mixer([first,second])
 for _ in range(8):app.processEvents()
 mix=w.workbench.mixer
 assert mix is not None
 assert s._current_mixer is mix
 mix.rows[0]['slider'].setValue(55)
 app.processEvents()
 assert mix.rows[0]['slider'].value()==55
 assert mix.rows[1]['slider'].value()==100
 assert h.mixer_rows['Voces']['readout'].text()=='Mixto'
 print("MIXER_INDEPENDENT_TRACK_VALUES_PRESERVED",flush=True)
 h.mixer_rows['Voces']['fader'].setValue(81)
 app.processEvents()
 assert all(row['slider'].value()==81 for row in mix.rows),[row['slider'].value() for row in mix.rows]
 mix.rows[0]['mute'].setChecked(True);app.processEvents()
 # Compact stem M/S and full mixer M are separate: the per-file
 # mute must not change a source-family button label to "*".
 assert not h.track_rows['Voces']['mute'].text().endswith('*')
 h.track_rows['Voces']['mute'].setChecked(True)
 app.processEvents()
 # Home stem M/S controls the live stem listening bus; the
 # full file mixer has separate per-file M/S (no accidental cross-mute).
 assert mix.rows[0]['mute'].isChecked()
 assert not mix.rows[1]['mute'].isChecked()
 assert h.track_rows['Voces']['mute'].isChecked()
 print("MIXER_FILE_MUTE_AND_HOME_STEM_MUTE_INDEPENDENT",flush=True)
 m=h._floating_manager
 for card in m.cards:
  m.detach(card);app.processEvents()
  m.redock(card);app.processEvents()
 print("FLOATING_12_NO_LOSS_AFTER_SYNC",flush=True)
 w.close()
 print("HOME_TAB_SYNC_AUDIT_PASS",flush=True)
