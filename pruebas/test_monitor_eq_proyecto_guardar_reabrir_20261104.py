"""Persistencia real de EQ y ganancia en manifiesto y reapertura del proyecto."""
from __future__ import annotations
import json,os,sys,tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
with tempfile.TemporaryDirectory(prefix="stemmidi_project_eq_capture_") as temp:
    os.environ["STEMMIDI_WORKSPACE"]=temp
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    import project_exit_guard
    project_exit_guard.ask_exit_choice=lambda _:"discard"
    from project_flow import create_named_project
    from main import MonitorWindow
    from studio_shell import save_project,open_project
    from home_record_review import gain_db_to_percent
    app=QApplication([])
    w=MonitorWindow();w.show()
    assert create_named_project(w,"Grabación con EQ",Path(temp)/"projects",
                                w.format.currentText(),44100)
    w.set_input_processing(-7,24)
    w.set_input_eq(True,4,-3,6)
    manifest=Path(w.project_path)
    assert save_project(w,show_confirmation=False)
    payload=json.loads(manifest.read_text(encoding="utf-8"))
    monitor=payload["parameters_monitor"]
    assert monitor["input_gain_db"]==-7
    assert monitor["input_balance"]==24
    assert monitor["input_eq"]=={
        "enabled":True,"bass":4,"mid":-3,"treble":6}
    print("PROJECT_MANIFEST_CAPTURE_EQ_AND_GAIN_SAVED_PASS",flush=True)
    w.set_input_processing(0,0)
    w.set_input_eq(False,0,0,0)
    assert w.input_eq_values==(0,0,0) and not w.input_eq_enabled
    assert open_project(w,str(manifest))
    for _ in range(30):app.processEvents()
    assert w.input_gain_db==-7
    assert w.input_balance==24
    assert w.input_eq_enabled and w.input_eq_values==(4,-3,6)
    review=w.studio_home.record_review
    assert tuple(review.sliders[k].value() for k in ("bass","mid","treble"))==(4,-3,6)
    assert review.eq_enabled.isChecked()
    assert review.sliders["volume"].value()==gain_db_to_percent(-7)
    assert w.studio_home.capture_gain.value()==-7
    assert w.studio_home.capture_balance.value()==24
    print("PROJECT_REOPEN_RESTORES_EQ_GAIN_BALANCE_AND_BOTH_SLIDER_VIEWS_PASS",flush=True)
    w.hide()
print("PROJECT_CAPTURE_EQ_SAVE_REOPEN_ALL_PASS",flush=True)
