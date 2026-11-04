"""Regresión: copiar desde listas de Resultado/Mezclador/MIDI a audio,
soltar sobre las listas destino, Piano Roll, y rechazar formatos erróneos."""
from __future__ import annotations
import hashlib,os,struct,sys,tempfile,wave
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mido
from PySide6.QtCore import Qt,QPoint,QPointF,QUrl,QMimeData,QItemSelectionModel
from PySide6.QtGui import QDropEvent,QDragEnterEvent
from PySide6.QtWidgets import QApplication
from main import MonitorWindow
from project_flow import create_named_project
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

def pump():
    for _ in range(15):app.processEvents()

def mime(*paths):
    m=QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return m

with tempfile.TemporaryDirectory(prefix="stemmidi_drag_lists_") as td:
    app=QApplication([])
    w=MonitorWindow();w.resize(1720,1000);w.show()
    assert create_named_project(w,"ListDrop",Path(td)/"projects",w.format.currentText(),44100)
    h=w.studio_home;manager=h._floating_manager
    w.tabs.setCurrentWidget(h);pump()
    project=Path(w.project_dir)
    source=project/"audio_a_midi"/"prueba.mid"
    source.parent.mkdir(exist_ok=True)
    song=mido.MidiFile()
    t=mido.MidiTrack()
    t.extend([mido.Message("note_on",note=64,velocity=100,time=0),
              mido.Message("note_off",note=64,velocity=0,time=480)])
    song.tracks.append(t);song.save(str(source))
    audio=project/"bateria"/"original.wav"
    audio.parent.mkdir(exist_ok=True)
    with wave.open(str(audio),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(22050)
        f.writeframes(b"".join(struct.pack("<h",(i%200-100)*40)
                      for i in range(22050)))
    original={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,audio)}
    h._update_results([source,audio])
    selection=h.files.selectionModel()
    selection.select(h.files.model().index(0,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    selection.select(h.files.model().index(1,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    out=h.files.mimeData(h.files.selectedItems())
    assert len(out.urls())==2,{u.toString() for u in out.urls()}
    assert {Path(u.toLocalFile()).resolve() for u in out.urls()}=={source.resolve(),audio.resolve()}
    print("RESULTS_MULTISELECT_TWO_REAL_URLS_PASS",flush=True)

    bridge=w.midi_audio_professional
    bridge.view.add_file(str(source))
    bridge.view.refresh_files(force=True);pump()
    midi_files=bridge.view.files
    assert midi_files.count()>0
    for i in range(midi_files.count()):
        if midi_files.item(i).data(Qt.UserRole)==str(source.resolve()):
            midi_files.setCurrentRow(i);break
    assert midi_files.mimeData([midi_files.currentItem()]).hasUrls()
    assert midi_files.supportedDragActions()==Qt.CopyAction
    print("MIDI_TO_AUDIO_SOURCE_LIST_CAN_DRAG_OUT_PASS",flush=True)

    manager.detach(h.mix_card);pump()
    mixer=manager.other_expanders[h.mix_card].project_mixer
    mixer.refresh_catalog(force=True)
    # QDropEvent mantiene un puntero C++ al QMimeData: conservarlo en
    # una variable viva hasta después de entregar el evento.
    drag_mime=mime(source)
    event=QDropEvent(QPointF(9,9),Qt.CopyAction,drag_mime,Qt.LeftButton,Qt.NoModifier)
    mixer.file_list.dropEvent(event);pump()
    assert event.isAccepted(),mixer.sources
    assert str(source.resolve()) in mixer.selected,mixer.selected
    assert mixer.file_list.supportedDragActions()==Qt.CopyAction
    assert any(mixer.file_list.item(i).data(Qt.UserRole)==str(source.resolve()) and
               mixer.file_list.item(i).checkState()==Qt.Checked
               for i in range(mixer.file_list.count()))
    print("DROP_DIRECTLY_ON_MIXER_FILE_LIST_CHECKS_AND_ADDS_SOURCE_PASS",flush=True)
    manager.redock(h.mix_card);pump()

    manager.detach(h.vocal_card);pump()
    studio=manager.other_expanders[h.vocal_card].vocal_studio
    drag_mime=mime(audio)
    event=QDropEvent(QPointF(9,9),Qt.CopyAction,drag_mime,Qt.LeftButton,Qt.NoModifier)
    studio.results.dropEvent(event);pump()
    assert event.isAccepted(),studio.feedback.text()
    assert Path(studio.mod.input.text()).resolve()==audio.resolve()
    print("DROP_ON_VOCAL_FILE_LIST_LOADS_AUDIO_WITH_EXISTING_SAFE_BACKEND_PASS",flush=True)
    manager.redock(h.vocal_card);pump()

    router=h._result_file_drag_router
    # No aceptar un MIDI para procesarlo como voz ni un WAV como MIDI.
    assert not router.accepts("vocal",[source])
    assert not router.accepts("info",[audio])
    for card,file in ((h.vocal_card,source),(h.piano_card,audio)):
        drag_mime=mime(file)
        event=QDragEnterEvent(QPoint(3,3),Qt.CopyAction,drag_mime,
                              Qt.LeftButton,Qt.NoModifier)
        QApplication.sendEvent(card.body,event)
        assert not event.isAccepted(),(card.header.text(),file)
    print("INCOMPATIBLE_FILE_EXTENSIONS_REJECTED_NO_PROCESSING_PASS",flush=True)

    # Cargar MIDI válido en Piano Roll desde Resultados sin cambiar el original.
    assert router.deliver("piano",[source])
    pump()
    assert h.workbench.piano.midi is not None
    print("RESULTS_MIDI_TO_PIANO_EDITOR_LOAD_PASS",flush=True)
    for path,digest in original.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,path
    print("ALL_DROPS_COPY_ONLY_ORIGINALS_UNCHANGED_PASS",flush=True)
    w.hide()
print("RESULTS_CROSS_MODULE_FILE_LISTS_ALL_PASS",flush=True)
