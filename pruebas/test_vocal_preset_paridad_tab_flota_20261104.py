"""Paridad real de presets y controles voz entre pestaña y flotante."""
import os,sys,tempfile
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from main import MonitorWindow
from project_flow import create_named_project
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

with tempfile.TemporaryDirectory(prefix="vocal_two_views_") as td:
    app=QApplication([])
    w=MonitorWindow();w.resize(1620,970);w.show()
    assert create_named_project(w,"Vocal parity",Path(td)/"projects",
                                w.format.currentText(),44100)
    tab=w.vocal_module
    manager=w.studio_home._floating_manager
    manager.detach(w.studio_home.vocal_card)
    for _ in range(20):app.processEvents()
    floating=manager.other_expanders[w.studio_home.vocal_card].vocal_studio
    assert floating.mod is tab
    assert tab.full_presets.builtins==floating.presets.builtins
    assert len(tab.full_presets.builtins)>=11,len(tab.full_presets.builtins)
    for preset in tab.full_presets.builtins.values():
        assert set(preset)>=set(tab.full_preset_snapshot())
    for name,target in (
        ("Balada íntima","Dulce"),("Soul cálido","Cálida"),
        ("Rock frontal","Rasgada"),("Voz hablada · podcast","Natural")
    ):
        idx=next((i for i in range(tab.full_presets.choices.count())
                  if tab.full_presets.choices.itemData(i)==("base",name)),-1)
        assert idx>=1,name
        tab.full_presets.choices.setCurrentIndex(idx)
        floating.refresh()
        for _ in range(5):app.processEvents()
        assert tab.character.currentText()==target
        assert floating._controls["character"][1].currentText()==target
        assert tab.full_preset_snapshot()==tab.full_presets.builtins[name]
    print("VOCAL_11_PRESETS_AND_FULL_SETTINGS_IDENTICAL_BOTH_DIRECTIONS",flush=True)
    manager.redock(w.studio_home.vocal_card)
    w.hide()
print("VOCAL_TWO_VIEWS_SHARED_MODEL_PASS",flush=True)
