#!/usr/bin/env python3
"""QA real del candado sin cruz y ajustes persistentes con aislamiento."""
import os,sys,tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="candado_inicio_") as td:
    os.environ["STEMMIDI_WORKSPACE"]=td
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import ux_controls
    ux_controls.PRESET_DIR=Path(td)/"presets"
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication,QPushButton,QMessageBox
    from main import MonitorWindow,STYLE
    a=QApplication([]);a.setStyleSheet(STYLE)
    w=MonitorWindow();w.show()
    w.tabs.setCurrentWidget(w.studio_home)
    for _ in range(15):a.processEvents()
    home=w.studio_home
    manager=home._floating_manager
    assert len(manager.cards)==12
    sep=home.workbench.separator
    assert manager.cards[1] is home.sep_card
    for card in manager.cards:
        original_min=card.minimumSize()
        original_max=card.maximumSize()
        card.lock_button.click()
        for _ in range(12):a.processEvents()
        assert manager.is_detached(card)
        assert card.lock_button.isVisible()
        assert card.lock_button.cursor().shape()==Qt.PointingHandCursor
        assert manager.windows[card].windowFlags() & Qt.FramelessWindowHint
        assert card.lock_button.toolTip().find("devolver")>=0
        if card is home.sep_card:
            expanded=manager.sep_expander
            assert expanded.root.isVisible()
            assert expanded.models.count()>0
            assert expanded.preset.count()>1
            assert expanded.stems["Voces"].isChecked()
            expanded.norm.setValue(.72)
            expanded.amp.setValue(.12)
            assert abs(sep.norm_setting-.72)<0.001
            assert abs(sep.amp_setting-.12)<0.001
            expanded.stems["Bajo"].setChecked(False)
            assert not sep.stem_checks["Bajo"].isChecked()
            assert not home.stem_checks["Bajo"].isChecked()
            expanded.preset_name.setText("Candado QA")
            expanded.save_preset()
            assert "Candado QA" in sep.presets._read()
            sep.norm_setting=.2
            saved=sep.presets._read()["Candado QA"]
            sep.apply_parameters(saved)
            assert abs(sep.norm_setting-.72)<.001
            expanded.refresh()
            assert expanded.preset_name.text()=="Candado QA"
            QMessageBox.information=staticmethod(lambda *args,**kwargs: QMessageBox.Ok)
            expanded.run.click()
            assert w.tabs.currentWidget() is home
            expanded.remove_preset()
            assert "Candado QA" not in sep.presets._read()
            assert w.tabs.currentWidget() is home
            expanded.refresh_timer.stop()
            assert expanded.root.isVisible()
        card.lock_button.click()
        for _ in range(12):a.processEvents()
        assert not manager.is_detached(card)
        assert card.minimumSize()==original_min
        assert card.maximumSize()==original_max
        assert card.isVisible()
        assert card.lock_button.isVisible()
    assert w.tabs.currentWidget() is home
    print("12_LOCKS_OPEN_RETURN_PRESETS_IA_SLIDERS_HAND_CURSOR_PASS")
