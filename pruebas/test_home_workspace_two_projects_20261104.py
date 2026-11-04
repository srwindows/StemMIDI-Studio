"""Dos proyectos tienen sus propias filas autoencajables y ventanas flotantes."""
from __future__ import annotations
import os,sys,tempfile,json
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
import studio_shell,project_status_dialog
from main import MonitorWindow
from project_flow import create_named_project
studio_shell._protect_unsaved_project=lambda _:True
project_status_dialog.show_project_status=lambda *args,**kwargs:None

with tempfile.TemporaryDirectory(prefix="stemmidi_rows_two_projects_") as td:
    app=QApplication([])
    w=MonitorWindow();w.resize(1680,970);w.show()
    assert create_named_project(
        w,"Filas A",Path(td)/"projects",w.format.currentText(),44100)
    project_a=Path(w.project_path)
    home=w.studio_home;w.tabs.setCurrentWidget(home)
    for _ in range(12):app.processEvents()
    ws=home.home_workspace;manager=home._floating_manager
    ws.to_free()
    assert ws.reorder_card(home.vocal_card,0,1)
    assert ws.reorder_card(home.drum_stems_card,1,2)
    saved_rows=json.loads(json.dumps(ws.row_ids))
    float_card=home.result_card
    manager.detach(float_card)
    for _ in range(10):app.processEvents()
    floating=manager.windows[float_card]
    floating.resize(770,560);floating.move(187,116)
    assert studio_shell.save_project(w,show_confirmation=False)
    saved_a=json.loads(project_a.read_text())["home_workspace"]
    assert saved_a["version"]==3 and saved_a["rows"]==saved_rows
    assert "resultados" in saved_a["floating"]
    print("PROJECT_A_STORES_ROW_ORDER_AND_FLOATING_WINDOW_PASS",flush=True)

    assert create_named_project(
        w,"Filas B",Path(td)/"projects",w.format.currentText(),44100)
    project_b=Path(w.project_path)
    assert not ws.is_free and not manager.windows
    assert studio_shell.save_project(w,show_confirmation=False)
    assert json.loads(project_b.read_text())["home_workspace"]["mode"]=="factory"
    print("PROJECT_B_DEFAULT_INDEPENDENT_PASS",flush=True)

    assert studio_shell.open_project(w,project_a)
    for _ in range(20):app.processEvents()
    assert ws.is_free and ws.row_ids==saved_rows
    assert manager.is_detached(float_card)
    restored=manager.windows[float_card].geometry()
    assert restored.width()>740 and restored.height()>520,restored
    print("PROJECT_A_ROWS_AND_FLOAT_GEOMETRY_RELOADED_PASS",restored,flush=True)

    assert studio_shell.open_project(w,project_b)
    for _ in range(20):app.processEvents()
    assert not ws.is_free and not manager.windows
    assert all(not row.isHidden() for row in ws.rows)
    print("PROJECT_B_SEPARATE_FACTORY_LAYOUT_RELOADED_PASS",flush=True)
    w.hide()
print("PER_PROJECT_AUTO_SNAP_PERSISTENCE_ALL_PASS",flush=True)
