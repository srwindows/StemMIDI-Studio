"""Análisis avanzado real de un MIDI sin modificar el archivo fuente."""
from __future__ import annotations
import tempfile,sys,os,hashlib
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import mido
from main import MonitorWindow
from project_flow import create_named_project

with tempfile.TemporaryDirectory(prefix="midi_analyze_pro_") as td:
    app=QApplication([])
    w=MonitorWindow();w.resize(1700,1000);w.show()
    assert create_named_project(w,"Inspector MIDI",Path(td)/"projects",
                                w.format.currentText(),44100)
    testfile=Path(td)/"ejemplo_para_analisis.mid"
    midi=mido.MidiFile(type=1,ticks_per_beat=480)
    tempo=mido.MidiTrack()
    tempo.append(mido.MetaMessage("set_tempo",tempo=600000,time=0))
    tempo.append(mido.MetaMessage("time_signature",
                                  numerator=4,denominator=4,time=0))
    midi.tracks.append(tempo)
    track=mido.MidiTrack()
    track.append(mido.MetaMessage("track_name",name="Piano derecho",time=0))
    track.append(mido.Message("program_change",channel=0,program=4,time=0))
    track.append(mido.Message("control_change",channel=0,control=64,value=127,time=0))
    track.append(mido.Message("note_on",channel=0,note=60,velocity=85,time=0))
    track.append(mido.Message("note_off",channel=0,note=60,velocity=0,time=480))
    track.append(mido.Message("note_on",channel=0,note=67,velocity=90,time=0))
    track.append(mido.Message("note_off",channel=0,note=67,velocity=0,time=480))
    track.append(mido.Message("control_change",channel=0,control=64,value=0,time=0))
    midi.tracks.append(track)
    midi.save(testfile)
    hash_before=hashlib.sha256(testfile.read_bytes()).hexdigest()
    bridge=w.midi_audio_professional
    w.tabs.setCurrentWidget(w.midi_audio_tab)
    for _ in range(18):app.processEvents()
    assert bridge.view.add_file(str(testfile))
    bridge.view.refresh_files(force=True)
    for _ in range(15):app.processEvents()
    bridge.analysis_toggle.click()
    for _ in range(15):app.processEvents()
    table=bridge.analysis
    assert table.isVisible()
    assert table.topLevelItemCount()==2,table.topLevelItemCount()
    row=table.topLevelItem(1)
    assert row.text(1)=="Piano derecho",row.text(1)
    assert row.text(2)=="1",row.text(2)
    assert row.text(3)=="005",row.text(3)
    assert row.text(4)=="2",row.text(4)
    assert row.text(5)=="60–67",row.text(5)
    assert row.text(6)=="2",row.text(6)
    assert hashlib.sha256(testfile.read_bytes()).hexdigest()==hash_before
    print("MIDI_PRO_INSPECTOR_TRACK_PROGRAM_NOTES_RANGE_CC64_WITHOUT_EDITS_PASS",flush=True)
    assert w.grab().save("/tmp/stemmidi_midi_pro_inspector_20261104.png")
    bridge.analysis_toggle.click()
    assert table.isHidden()
    assert w.midi_audio_professional.view is w.studio_home.midi_to_audio.expanded_view
    w.hide()
print("MIDI_PRO_ANALYSIS_NON_DESTRUCTIVE_PASS",flush=True)
