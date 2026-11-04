"""Compositor profesional: 12 pistas, edición multipista y VU PCM reales."""
from __future__ import annotations
import math,os,struct,sys,tempfile,time,wave
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF,Qt
import mido
from main import MonitorWindow
from project_flow import create_named_project
from compositor_tab import ClipTile,ROW,LEFT,TOP
from compositor_meters import LevelMeter,levels_at
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

def file_audio(path,amp=9500):
    with wave.open(str(path),"wb") as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100)
        f.writeframes(b"".join(
            struct.pack("<hh",int(amp*math.sin(2*math.pi*330*i/44100)),
                               int(amp*math.sin(2*math.pi*330*i/44100)))
            for i in range(44100*2)))

def file_midi(path):
    m=mido.MidiFile(ticks_per_beat=480)
    track=mido.MidiTrack();m.tracks.append(track)
    track.append(mido.Message("note_on",note=60,velocity=92,time=0))
    track.append(mido.Message("note_off",note=60,time=960))
    m.save(path)

with tempfile.TemporaryDirectory(prefix="stem_compact_12tracks_") as td:
    app=QApplication([])
    w=MonitorWindow();w.resize(1760,1000);w.show()
    assert create_named_project(w,"Compacto",Path(td)/"projectos",
                                w.format.currentText(),44100)
    project=Path(w.project_dir)
    assets=Path(td)/"fixtures";assets.mkdir()
    wav=assets/"voz.wav";midi=assets/"piano.mid"
    file_audio(wav);file_midi(midi)
    c=w.composer_tab
    w.tabs.setCurrentWidget(c)
    for _ in range(8):app.processEvents()
    for _ in range(12):
        c.session.create_track("audio")
    aud=c.session.state["tracks"]
    assert len(aud)==12
    clips=[]
    for i in range(2):
        track_id,clip_id=c.session.add(wav,track_id=aud[i]["id"])
        clips.append(clip_id)
    c.refresh_timeline()
    for _ in range(10):app.processEvents()
    assert ROW<=32,ROW
    visible=int((c.timeline.viewport().height()-TOP)/ROW)
    print("COMPACT_VISIBILITY",visible,"row_px",ROW,
          "timeline_height",c.timeline.viewport().height(),flush=True)
    assert visible>=10,visible
    assert c.track_table.rowCount()==12
    assert c.track_table.verticalHeader().defaultSectionSize()==ROW
    assert len(c.track_meters)==12
    assert all(isinstance(m,LevelMeter) for m in c.track_meters.values())
    assert isinstance(c.master_meter,LevelMeter)
    assert not c.preview.isVisible()
    assert c.grab().save("/tmp/stemmidi_compacto_12tracks_ui_20261104.png")
    print("TWELVE_TRACK_LANES_10PLUS_VISIBLE_WITH_PER_TRACK_METERS_PASS",flush=True)

    c.select_clip(clips[0])
    second=next(t for t in c.scene.items()
                if isinstance(t,ClipTile) and t.clip["id"]==clips[1])
    second.setSelected(True)
    assert set(c.selected_ids())==set(clips),c.selected_ids()
    c.set_playhead(1)
    assert set(c.selected_ids())==set(clips)
    before=len(c.session.undo_stack)
    c.split_selected()
    assert len(c.session.undo_stack)==before+1
    assert len(c.session.track(aud[0]["id"])["clips"])==2
    assert len(c.session.track(aud[1]["id"])["clips"])==2
    c.undo()
    assert len(c.session.track(aud[0]["id"])["clips"])==1
    assert len(c.session.track(aud[1]["id"])["clips"])==1
    print("CTRL_MULTICLIP_SPLIT_AT_GUIDE_ONE_UNDO_PASS",flush=True)

    # Seleccionar pistas sin elegir clips: «Dividir pista en la guía»
    # debe actuar sobre las pistas completas, una sola operación.
    c.scene.clearSelection()
    c.selected_clip_id=None
    c.selected_clip_ids.clear()
    c.track_table.selectRow(0)
    c.set_playhead(1.)
    prior=len(c.session.undo_stack)
    c.split_track_at_guide()
    assert len(c.session.undo_stack)==prior+1
    assert len(c.session.track(aud[0]["id"])["clips"])==2
    assert len(c.session.track(aud[1]["id"])["clips"])==1
    c.undo()
    assert len(c.session.track(aud[0]["id"])["clips"])==1
    from PySide6.QtCore import QItemSelectionModel
    select=c.track_table.selectionModel()
    select.clearSelection()
    for row in (0,1):
        select.select(c.track_table.model().index(row,0),
                      QItemSelectionModel.Select|QItemSelectionModel.Rows)
    c.scene.clearSelection()
    c.selected_clip_ids.clear()
    c.selected_clip_id=None
    c.split_track_at_guide()
    assert len(c.session.track(aud[0]["id"])["clips"])==2
    assert len(c.session.track(aud[1]["id"])["clips"])==2
    c.undo()
    print("TRACK_SELECTION_SINGLE_AND_MULTI_TRACK_SPLIT_UNDO_PASS",flush=True)

    c.select_clip(clips[0])
    second=next(t for t in c.scene.items()
                if isinstance(t,ClipTile) and t.clip["id"]==clips[1])
    second.setSelected(True)
    before=len(c.session.undo_stack)
    c.cut_selected()
    assert len(c.session.undo_stack)==before+1
    assert not c.session.track(aud[0]["id"])["clips"]
    assert not c.session.track(aud[1]["id"])["clips"]
    c.set_playhead(8)
    c.paste_clip()
    assert len(c.session.track(aud[0]["id"])["clips"])==1
    assert len(c.session.track(aud[1]["id"])["clips"])==1
    assert all(x["beat"]==8 for t in c.session.state["tracks"]
               for x in t["clips"])
    c.undo()
    assert not c.session.track(aud[0]["id"])["clips"]
    c.undo()
    assert len(c.session.track(aud[0]["id"])["clips"])==1
    assert len(c.session.track(aud[1]["id"])["clips"])==1
    print("CONTEXT_CUT_PASTE_MULTIPLE_AUDIO_CLIPS_UNDO_GROUP_PASS",flush=True)

    # Menú contextual completo al pulsar sobre cualquier región.
    c.select_clip(clips[0])
    menu=c.build_timeline_menu(QPointF(LEFT+ROW,TOP+3))
    text=" ".join(action.text() for action in menu.actions())
    assert all(x in text for x in (
        "Dividir","Cortar","Copiar","Duplicar","Eliminar",
        "Pegar","Seleccionar","Nueva pista","Resultados")),text
    print("RIGHT_CLICK_COMPLETE_DAW_CONTEXT_MENU_PASS",flush=True)

    # El arrastre de dos clips debe mantener su separación y producir
    # UNA operación Undo; también funciona entre pistas compatibles.
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    c.select_clip(clips[0])
    other=next(t for t in c.scene.items()
               if isinstance(t,ClipTile) and t.clip["id"]==clips[1])
    other.setSelected(True)
    tiles=[t for t in c.scene.selectedItems() if isinstance(t,ClipTile)]
    assert len(tiles)==2
    previous_undo=len(c.session.undo_stack)
    for tile in tiles:
        tile.setPos(tile.pos().x()+4*c.pixels_per_beat,tile.pos().y())
    released=QMouseEvent(
        QEvent.MouseButtonRelease,QPointF(70,70),
        Qt.LeftButton,Qt.NoButton,Qt.NoModifier)
    c.timeline.mouseReleaseEvent(released)
    assert len(c.session.undo_stack)==previous_undo+1
    assert all(c.session.clip(clip_id)[1]["beat"]==4 for clip_id in clips)
    c.undo()
    assert all(c.session.clip(clip_id)[1]["beat"]==0 for clip_id in clips)
    print("MULTI_CLIP_DRAG_GROUP_ATOMIC_UNDO_PASS",flush=True)

    # Las medidas salen de los buses PCM pos-fader del render, no del MIDI
    # ni de un control animado. Otra pista silenciada queda realmente a cero.
    c.session.update_track(aud[1]["id"],mute=True)
    c.refresh_timeline()
    c.start_render(True)
    assert c.worker is not None
    deadline=time.monotonic()+45
    while c.worker.isRunning() and time.monotonic()<deadline:
        app.processEvents();time.sleep(.05)
    for _ in range(18):app.processEvents()
    assert not c.worker.isRunning(),c.status.text()
    assert c.meter_data and "__master__" in c.meter_data,c.status.text()
    assert aud[0]["id"] in c.meter_data
    assert aud[1]["id"] not in c.meter_data
    c._update_meters(.50)
    master=c.master_meter.levels
    first=c.track_meters[aud[0]["id"]].levels
    second_levels=c.track_meters[aud[1]["id"]].levels
    assert master[0]>.04 and first[0]>.04,(master,first)
    assert second_levels==(0.,0.,0.,0.)
    c._update_meters(None)
    assert c.master_meter.levels==(0.,0.,0.,0.)
    print("MASTER_REAL_AUDIO_TRACK_METERS_MUTE_AND_ZERO_ON_STOP_PASS",flush=True)
    w.close();app.processEvents()
print("COMPACT_MULTISELECTION_CONTEXT_AND_METER_ALL_PASS",flush=True)
