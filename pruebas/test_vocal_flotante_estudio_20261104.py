"""Regresión UI del estudio vocal real conectado a la tarjeta flotante."""
from __future__ import annotations
import os,sys,tempfile,struct,math,wave,time
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from main import MonitorWindow
from project_flow import create_named_project
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

with tempfile.TemporaryDirectory(prefix="vocal_float_20261104_") as tmp:
    app=QApplication([])
    w=MonitorWindow();w.resize(1670,990);w.show()
    assert create_named_project(
        w,"VozEstudio",Path(tmp)/"proyectos",w.format.currentText(),44100)
    home=w.studio_home
    manager=home._floating_manager
    card=home.vocal_card
    manager.detach(card)
    for _ in range(20):app.processEvents()
    assert card in manager.windows
    expand=manager.other_expanders[card]
    v=expand.vocal_studio
    assert v is not None
    print("STUDIO_TABS",[v.tabs.tabText(i) for i in range(v.tabs.count())],flush=True)
    assert v.tabs.count()==5
    assert len(v._controls)>=20
    assert v.presets.choices.count()>=12
    assert not home.vocal_source.isVisible()
    strip=manager.windows[card].float_transport
    assert strip._vocal_vu_area is not None
    assert len(strip.vus)==2
    assert all(m.orientation()==Qt.Horizontal for m in strip.vus.values())
    # Archivo de prueba de voz sin tener que abrir selección del usuario
    original=Path(tmp)/"voz_sin_procesar.wav"
    with wave.open(str(original),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(22050)
        f.writeframes(b"".join(
           struct.pack("<h",int(6500*math.sin(2*math.pi*220*i/22050)))
           for i in range(22050*2)))
    import file_dialogs
    old=file_dialogs.get_open_file_name
    file_dialogs.get_open_file_name=lambda *_args,**_kw:(str(original),"WAV")
    try:v.import_voice()
    finally:file_dialogs.get_open_file_name=old
    assert Path(v.mod.input.text()).is_file(),v.feedback.text()
    assert Path(v.mod.input.text()).resolve()!=original.resolve()
    assert Path(w.project_dir).resolve() in Path(v.mod.input.text()).resolve().parents
    print("VOCAL_IMPORT_COPIED_SAFE_SOURCE",v.mod.input.text(),flush=True)
    v.refresh()
    params=v.mod.full_preset_snapshot()
    before=v.mod.strength.value()
    sl=v._controls["strength"][1]
    sl.setValue(51 if before!=51 else 83)
    v._finish_edit()
    assert v.mod.strength.value()!=before
    v.undo()
    assert v.mod.strength.value()==before
    v.redo()
    assert v.mod.strength.value()!=before
    edited=v.mod.strength.value()
    v.reset()
    assert v.mod.strength.value()==v._default["strength"]
    v.undo()
    assert v.mod.strength.value()==edited
    v.redo()
    assert v.mod.strength.value()==v._default["strength"]
    # Los presets corresponden al motor real y se pueden revertir.
    preset_before=v.mod.full_preset_snapshot()
    i=next(i for i in range(v.presets.choices.count())
           if "Soul cálido" in v.presets.choices.itemText(i))
    v.presets.choices.setCurrentIndex(i)
    assert v.mod.character.currentText()=="Cálida"
    v.undo()
    assert v.mod.full_preset_snapshot()==preset_before
    assert v.presets.choices.currentIndex()==0
    v.redo()
    assert v.mod.character.currentText()=="Cálida"
    v.undo()
    print("VOCAL_UNDO_REDO_RESET_AND_PRESET_HISTORY_PASS",flush=True)
    assert v.save_session()
    session=v._session_file()
    assert session.is_file()
    v.mod.strength.setValue(99)
    v._load_session()
    assert v.mod.strength.value()==v._default["strength"]
    print("VOCAL_PROJECT_SESSION_PERSISTENCE_PASS",flush=True)
    for _ in range(12):app.processEvents()
    shot="/tmp/stemmidi_vocal_estudio_flotante_20261104.png"
    assert manager.windows[card].grab().save(shot)
    print("VOCAL_SCREENSHOT",shot,flush=True)
    manager.redock(card)
    for _ in range(10):app.processEvents()
    assert home.vocal_source.isVisible()
    assert strip not in manager.windows if card in manager.windows else True
    w.close();app.processEvents()
print("VOCAL_FLOAT_GUI_IMPORT_PRESETS_UNDO_SAVING_LAYOUT_PASS",flush=True)
