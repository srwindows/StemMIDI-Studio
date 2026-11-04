#!/usr/bin/env python3
"""Regresión completa de ventana flotante MIDI→audio, sin alterar usuario."""
import os,sys,time,tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stem_full_converter_") as td:
 os.environ["STEMMIDI_WORKSPACE"]=td
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QFileDialog
 from PySide6.QtCore import QPoint
 import mido,project_exit_guard
 from main import MonitorWindow
 from project_flow import create_named_project
 from audio_import import probe_audio
 project_exit_guard.ask_exit_choice=lambda _:"discard"
 app=QApplication([])
 main=MonitorWindow()
 main.resize(1360,768);main.show()
 assert create_named_project(main,"RenderAvanzado",Path(td)/"projects",
                             main.format.currentText(),main.capture_rate.currentData())
 project=Path(main.project_dir)
 src_dir=project/"audio_a_midi";src_dir.mkdir(parents=True,exist_ok=True)
 midis=[]
 for name,note in (("Piano.mid",60),("Bateria.mid",36)):
  path=src_dir/name
  f=mido.MidiFile()
  tr=mido.MidiTrack()
  tr.extend((mido.Message("note_on",note=note,velocity=115,time=0),
             mido.Message("note_off",note=note,velocity=0,time=960)))
  f.tracks.append(tr);f.save(path);midis.append(path)
 h=main.studio_home
 backend=h.midi_to_audio
 assert backend.select_source(midis[0])
 manager=h._floating_manager
 manager.detach(h.info_card)
 for _ in range(20):app.processEvents()
 expanded=manager.other_expanders[h.info_card].info_expanded
 win=manager.windows[h.info_card]
 assert not backend.isVisible()
 assert expanded.isVisible()
 assert expanded.files.count()>=2,expanded.files.count()
 assert expanded.bank.count()>=2
 assert expanded.convert.isVisible()
 assert expanded.cancel.isVisible()
 assert expanded.format.isVisible()
 assert expanded.output.isVisible()
 assert expanded.results.isVisible()
 assert not hasattr(manager.other_expanders[h.info_card],"copy_info_button")
 assert getattr(win,"float_transport",None) is None
 for target in (expanded.files,expanded.bank,expanded.gain,expanded.tempo,
                expanded.output,expanded.convert,expanded.cancel,expanded.results):
  assert target.isVisible(),(target.objectName(),target.isVisible())
  at=target.mapTo(win,QPoint(0,0))
  assert at.y()>=0 and at.y()+target.height()<=win.height()+3,(
      target.objectName(),at.y(),target.height(),win.height())
 print("FLOATING_FULL_CONVERTER_CONTROLS_VISIBLE_WITHOUT_OLD_INFO_PASS",flush=True)
 # Cargar dos archivos mediante diálogo simulado (separados, con todas las rutas).
 external=Path(td)/"externo MIDI.mid"
 external.write_bytes(midis[0].read_bytes())
 original=QFileDialog.getOpenFileNames
 QFileDialog.getOpenFileNames=staticmethod(lambda *a,**k:([str(external)],""))
 try:expanded.load_files()
 finally:QFileDialog.getOpenFileNames=original
 assert expanded.files.count()>=3
 assert backend.input.currentData()==str(external.resolve())
 assert expanded.name.text()==external.name
 # Ajustes de audio = backend real, NO copias ni valores decorativos.
 expanded.gain.setValue(80)
 expanded.transpose.setValue(5)
 expanded.tempo.setValue(150)
 expanded.reverb.setChecked(False)
 expanded.chorus.setChecked(False)
 expanded.normalize.setChecked(True)
 expanded.rate.setCurrentIndex(0)
 expanded.channels.setCurrentIndex(1)
 expanded.output.setText("Prueba_sonido_avanzado")
 expanded.format.setCurrentText("FLAC")
 expanded.bank.setCurrentIndex(expanded.bank.findText("TimGM 6 MB"))
 assert backend.soundfont and backend.soundfont.name=="TimGM6mb.sf2"
 assert backend.gain_percent==80
 assert backend.transpose_semitones==5
 assert backend.tempo_percent==150
 assert not backend.reverb and not backend.chorus and backend.normalize and backend.mono
 assert backend.rate.currentIndex()==0 and backend.format.currentText()=="FLAC"
 assert backend.output_basename=="Prueba_sonido_avanzado"
 assert expanded.convert_selected() is None
 assert backend.busy
 assert not expanded.convert.isEnabled()
 assert expanded.cancel.isEnabled()
 until=time.monotonic()+25
 while backend.busy and time.monotonic()<until:
  app.processEvents();time.sleep(.025)
 assert not backend.busy,backend.status.text()
 assert backend.progress.value()==100,(backend.progress.value(),backend.status.text())
 result=backend._dest
 assert result and result.is_file(),str(backend.status.text())
 info=probe_audio(result)
 assert info["codec"]=="flac" and info["rate"]==44100 and info["channels"]==1,info
 assert result.name=="Prueba_sonido_avanzado.flac",result.name
 expanded.refresh_outputs()
 assert any(expanded.results.item(i).data(256)==str(result) for i in range(expanded.results.count()))
 assert external.is_file() and midis[0].is_file()
 print("SF2_GAIN_TEMPO_TRANSPOSE_FX_MONO_NORMALIZE_OUTPUT_AND_RESULTS_PASS",flush=True)
 # Cerrar candado no resetea configuración ni conversiones.
 manager.redock(h.info_card)
 for _ in range(16):app.processEvents()
 assert backend.isVisible() and not expanded.isVisible()
 assert backend.format.currentText()=="FLAC" and backend.rate.currentIndex()==0
 assert backend.input.currentData()==str(external.resolve())
 assert result.exists()
 print("REDOCK_PRESERVES_ENGINE_AND_SETTINGS_PASS",flush=True)
 main.close()
print("MIDI_AUDIO_FULL_FLOATING_INTEGRATION_PASS",flush=True)
