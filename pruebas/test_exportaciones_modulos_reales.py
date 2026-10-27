#!/usr/bin/env python3
"""Guardar como real de Piano Roll, patrón batería y Mezclador fuera de backup."""
import os,sys,tempfile,wave,time,hashlib
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_export_real_") as t:
 os.environ["STEMMIDI_WORKSPACE"]=t
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QMessageBox
 from main import MonitorWindow
 from project_flow import create_named_project
 from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
 from PySide6.QtCore import Qt
 import file_dialogs
 import mido
 app=QApplication([])
 QMessageBox.information=staticmethod(lambda *args:QMessageBox.Ok)
 QMessageBox.warning=staticmethod(lambda *args:(_ for _ in ()).throw(
    AssertionError("Unexpected warning: "+str(args[1:3]))))
 QMessageBox.question=staticmethod(lambda *args:QMessageBox.Yes)
 w=MonitorWindow()
 root=Path(t)
 assert create_named_project(w,"MiEstudio",str(root/"proyectos"),
         next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
 proj=Path(w.project_dir)
 original_wav=root/"fuentes"/"cancion.wav"
 original_wav.parent.mkdir()
 with wave.open(str(original_wav),"wb") as stream:
  stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000)
  stream.writeframes(bytes(32000))
 sound_hash=hashlib.sha256(original_wav.read_bytes()).hexdigest()
 mid=mido.MidiFile(type=1)
 track=mido.MidiTrack()
 track.append(mido.Message("note_on",note=67,velocity=90,time=0))
 track.append(mido.Message("note_off",note=67,velocity=0,time=480))
 mid.tracks.append(track)
 midi_source=proj/"temporales"/"midi"/"entrada.mid"
 midi_source.parent.mkdir(parents=True,exist_ok=True)
 mid.save(midi_source)
 w.workbench.show_piano_roll(midi_source)
 assert w.workbench.piano.save_button.isHidden() is False
 from export_dialog import export_files as original_export
 import piano_roll
 import export_dialog
 try:
  target=root/"exports"/"piano_editado.mid"
  def export_mock(parent,entries,project_dir=None,title="",kind=None):
   from export_dialog import _copy_atomic
   return [_copy_atomic(entries[0],target)]
  export_dialog.export_files=export_mock
  w.workbench.piano.save_as()
  assert target.is_file() and mido.MidiFile(target).tracks
  assert (proj/"temporales"/"midi"/"piano_roll_sesion.mid").is_file()
  print("PIANO_ROLL_GUARDAR_COMO_EXTERNO_OK",flush=True)
 finally:export_dialog.export_files=original_export
 chooser=file_dialogs.get_save_file_name
 try:
  drum_file=root/"exports"/"ritmo_bateria.mid"
  file_dialogs.get_save_file_name=lambda *a,**k:(str(drum_file),"")
  w.drum_module.studio.export_pattern()
  assert drum_file.is_file()
  assert mido.MidiFile(drum_file).tracks
  assert (proj/"temporales"/"bateria"/"patron_bateria.mid").is_file()
  print("BATERIA_PATRON_GUARDAR_COMO_EXTERNO_OK",flush=True)
  w.workbench.show_mixer([original_wav])
  mix=w.workbench.mixer
  mixer_file=root/"exports"/"mezcla_externa.flac"
  mix.output_fmt.setCurrentText(next(name for name,item in __import__('mezclador').FORMATS.items()
                                    if item[0]==".flac"))
  file_dialogs.get_save_file_name=lambda *a,**k:(str(mixer_file),"")
  mix.export_mix()
  started=time.monotonic()
  while mix.process is not None and time.monotonic()-started<30:
   app.processEvents();time.sleep(.03)
  assert mix.process is None,"FFmpeg no terminó"
  assert mixer_file.is_file() and mixer_file.stat().st_size>1000
  mix_saved=proj/"temporales"/"mezclas"/"mezcla_actual.flac"
  assert mix_saved.is_file() and mix_saved.read_bytes()==mixer_file.read_bytes()
  print("MEZCLADOR_EXPORTA_RUTA_ELEGIDA_OK",flush=True)
 finally:file_dialogs.get_save_file_name=chooser
 assert hashlib.sha256(original_wav.read_bytes()).hexdigest()==sound_hash
 print("FUENTES_ORIGINALES_INTACTAS_OK",flush=True)
print("EXPORTACIONES_MODULOS_REALES_OK",flush=True)
