"""Resultados compactos/candado + URL copy-drag a ventanas MIDI y audio."""
from __future__ import annotations
import hashlib,os,struct,sys,tempfile,wave
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mido
from PySide6.QtCore import Qt,QPoint,QPointF,QUrl,QMimeData
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication
from main import MonitorWindow
from project_flow import create_named_project
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

def pump():
    for _ in range(18):app.processEvents()

def drop_into(card,source):
    target=card.body
    data=QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(source.resolve()))])
    enter=QDragEnterEvent(QPoint(8,8),Qt.CopyAction,data,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(target,enter)
    assert enter.isAccepted(),("ENTER_NOT_ACCEPTED",card.header.text(),source)
    drop=QDropEvent(QPointF(8,8),Qt.CopyAction,data,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(target,drop)
    assert drop.isAccepted(),("DROP_NOT_ACCEPTED",card.header.text(),source)
    pump()

with tempfile.TemporaryDirectory(prefix="stemmidi_compact_results_") as tmp:
    app=QApplication([])
    w=MonitorWindow();w.resize(1700,1010);w.show()
    assert create_named_project(w,"Compacto DnD",Path(tmp)/"projects",
                                w.format.currentText(),44100)
    home=w.studio_home
    w.tabs.setCurrentWidget(home);pump()
    manager=home._floating_manager
    card=home.result_card
    assert home._results_is_compact
    for item in (home.results_btn_0,home.results_btn_1,
                 home.results_btn_2,home.results_folder,
                 home.export_btn,home.discard_btn,home.result_hint,
                 home.result_vu,home.result_vu_caption):
        assert item.isHidden(),item.objectName()
    assert home.files.isVisible()
    assert all(x.isVisible() for x in (
        home.play_btn,home.stop_btn_audio,home.pause_btn_audio,
        home.master_volume,home.audio_progress))
    print("RESULTS_LOCKED_ONLY_FILES_AND_TRANSPORT_PASS",flush=True)
    assert card.grab().save("/tmp/stemmidi_resultados_candado_cerrado_20261104.png")
    manager.detach(card);pump()
    assert not home._results_is_compact and manager.is_detached(card)
    for item in (home.results_btn_0,home.results_btn_1,home.results_btn_2,
                 home.results_folder,home.export_btn,home.discard_btn):
        assert item.isVisible(),item.objectName()
    assert home.result_vu.isVisible()
    assert manager.other_expanders[card].extra.isVisible()
    home._result_tab(2)
    assert card.grab().save("/tmp/stemmidi_resultados_candado_abierto_20261104.png")
    manager.redock(card);pump()
    assert home._results_is_compact
    assert home.result_pages.currentIndex()==0
    manager.detach(card);pump()
    assert home.result_pages.currentIndex()==2
    manager.redock(card);pump()
    print("RESULTS_FLOAT_FULL_RESTORE_TAB_STATE_PASS",flush=True)

    root=Path(w.project_dir)
    audio=root/"bateria"/"voz_compatible.wav"
    audio.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(audio),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(22050)
        f.writeframes(b"".join(struct.pack("<h",(i%200-100)*50)
                      for i in range(22050)))
    midi=root/"audio_a_midi"/"melodia.mid"
    midi.parent.mkdir(parents=True,exist_ok=True)
    song=mido.MidiFile()
    track=mido.MidiTrack()
    track.append(mido.Message("note_on",note=60,velocity=88,time=0))
    track.append(mido.Message("note_off",note=60,velocity=0,time=480))
    song.tracks.append(track);song.save(str(midi))
    sha_before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (audio,midi)}
    home._update_results([audio,midi]);pump()
    assert home._results_is_compact
    assert card.grab().save("/tmp/stemmidi_resultados_compactos_con_archivos_20261104.png")
    manager.detach(card);pump()
    assert card.grab().save("/tmp/stemmidi_resultados_flotantes_con_archivos_20261104.png")
    manager.redock(card);pump()
    audio_row=next(row for row in range(home.files.rowCount())
                   if home.files.item(row,0) is not None
                   and Path(home.files.item(row,0).data(Qt.UserRole)).resolve()==audio.resolve())
    home.files.selectRow(audio_row)
    m=home.files.mimeData(home.files.selectedItems())
    assert m.hasUrls() and len(m.urls())==1
    assert Path(m.urls()[0].toLocalFile()).resolve()==audio.resolve()
    assert home.files.supportedDragActions()==Qt.CopyAction
    print("DRAG_FROM_HOME_RESULTS_READ_ONLY_URLS_PASS",flush=True)
    w.results_tab.refresh([audio,midi])
    w.results_tab.table.selectRow(1)
    m=w.results_tab.table.mimeData(w.results_tab.table.selectedItems())
    assert len(m.urls())==1 and Path(m.urls()[0].toLocalFile()).resolve()==midi.resolve()
    print("DRAG_FROM_RESULTS_TAB_URLS_PASS",flush=True)

    for target in (home.wave_card,home.midi_card,home.sep_card,
                   home.drum_card,home.vocal_card):
        manager.detach(target);pump()
        drop_into(target,audio)
        manager.redock(target);pump()
    assert w.workbench.converter.audio_path.text()==str(audio.resolve())
    assert w.workbench.separator.file_edit.text()==str(audio.resolve())
    assert Path(home.wave_title.text()).name==audio.name
    assert home._drum_module.input.text()==str(audio.resolve())
    assert Path(home._vocal_module.input.text()).resolve()==audio.resolve()
    print("AUDIO_DROPS_SEPARATION_TRANSCRIPTION_VOICE_DRUM_WAVE_PASS",flush=True)

    for target in (home.info_card,home.mix_card):
        manager.detach(target);pump()
        drop_into(target,midi)
        manager.redock(target);pump()
    assert Path(home.midi_to_audio.input.currentData()).resolve()==midi.resolve()
    print("MIDI_DROPS_MIDI_TO_AUDIO_AND_MIXER_PASS",flush=True)

    for source in (audio,midi):
        assert hashlib.sha256(source.read_bytes()).hexdigest()==sha_before[str(source)]
    print("SOURCE_BYTES_UNCHANGED_AFTER_ALL_DROPS_PASS",flush=True)
    w.hide()
print("RESULTS_COMPACT_AND_DND_ALL_PASS",flush=True)
