#!/usr/bin/env python3
"""Ensayo integral de MIDI a audio con archivos y procesos reales en /tmp."""
import os,sys,tempfile,time
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stem_midi_to_audio_test_") as td:
 os.environ["STEMMIDI_WORKSPACE"]=td
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication
 import mido,project_exit_guard
 from main import MonitorWindow
 from project_flow import create_named_project
 from project_transaction import _staged,commit_staged
 from audio_import import probe_audio
 project_exit_guard.ask_exit_choice=lambda _:"discard"
 app=QApplication([])
 main=MonitorWindow();main.resize(1480,920);main.show()
 assert create_named_project(main,"MIDI_a_audio_test",Path(td)/"projects",
                             main.format.currentText(),main.capture_rate.currentData())
 project=Path(main.project_dir)
 midi=project/"audio_a_midi"/"Notas_test.mid"
 midi.parent.mkdir(parents=True,exist_ok=True)
 song=mido.MidiFile()
 tr=mido.MidiTrack()
 tr.extend([mido.Message("note_on",channel=0,note=60,velocity=105,time=0),
            mido.Message("note_off",channel=0,note=60,velocity=0,time=480),
            mido.MetaMessage("end_of_track",time=0)])
 song.tracks.append(tr);song.save(midi)
 original=midi.read_bytes()
 main.workbench.midi_storage.items.append(midi)
 card=main.studio_home.midi_to_audio
 card.refresh(force=True)
 assert card.input.findData(str(midi.resolve()))>=0
 card.input.setCurrentIndex(card.input.findData(str(midi.resolve())))
 assert main.studio_home.info_card.header.text().endswith("MIDI a audio")
 assert main.studio_home.info_card.findChild(type(card),"midiToAudioHomeCard") is None
 print("REPLACED_DUPLICATED_INFO_WITH_CONVERTER_PASS",flush=True)
 # Se mantiene la prueba de 48 kHz como opción explícita (44,1 kHz es el nuevo valor inicial).
 assert card.rate.currentIndex()==0
 card.rate.setCurrentIndex(1)
 formats=["WAV 24 bits","FLAC","MP3 320 kb/s"]
 for fmt in formats:
  card.format.setCurrentText(fmt)
  assert card.start()
  assert card.busy and card.cancel.isEnabled()
  # Cierre protegido durante proceso activo.
  from PySide6.QtWidgets import QMessageBox
  old=QMessageBox.information
  QMessageBox.information=staticmethod(lambda *a,**k:QMessageBox.Ok)
  try:
   assert not main.close()
  finally:QMessageBox.information=old
  assert main.isVisible()
  until=time.monotonic()+25
  while card.busy and time.monotonic()<until:
   app.processEvents();time.sleep(.03)
  assert not card.busy,card.status.text()
  assert card.progress.value()==100,(fmt,card.status.text(),card.progress.value())
  dest=card._dest
  assert dest and dest.is_file(),(fmt,card.status.text())
  info=probe_audio(dest)
  assert info["duration"]>.1 and info["rate"]==48000,(fmt,info)
  assert card._tmp_render is None and card._tmp_encoded is None
  assert dest.relative_to(project).parts[:2]==("temporales","resultados")
  assert any(src==dest for _,src in _staged(project))
  # La tarjeta 4. Resultados debe incorporar inmediatamente la conversión.
  visible={main.studio_home.files.item(i,0).data(256)
           for i in range(main.studio_home.files.rowCount())}
  assert str(dest) in visible,(fmt,dest,sorted(visible))
  assert midi.read_bytes()==original
  print("CONVERSION_OK",fmt,dest.name,info["codec"],round(info["duration"],2),flush=True)
 # Cancel immediately after starting synthesis: no new result published.
 outputs=set((project/"temporales"/"resultados").iterdir())
 card.format.setCurrentText("FLAC")
 assert card.start()
 assert card.stop()
 until=time.monotonic()+5
 while card.busy and time.monotonic()<until:
  app.processEvents();time.sleep(.02)
 assert not card.busy
 assert set((project/"temporales"/"resultados").iterdir())==outputs
 assert midi.read_bytes()==original
 assert not list((project/"temporales").glob("_midi_audio_*"))
 print("CANCEL_NO_PARTIAL_OR_LOST_OLD_OUTPUT_PASS",flush=True)
 assert all(kind=="resultados" for kind,path in _staged(project))
 promoted,ledger=commit_staged(project)
 assert len(promoted)>=3
 assert len(list((project/"resultados").glob("Notas_test_MIDI_audio*")))>=3
 assert all(path.is_file() for path in (project/"resultados").glob("*"))
 print("PROJECT_TRANSACTION_SAVES_OUTPUT_TO_RESULTS_PASS",flush=True)
 main.close()
print("MIDI_TO_AUDIO_CONVERTER_ALL_TESTS_PASS",flush=True)
