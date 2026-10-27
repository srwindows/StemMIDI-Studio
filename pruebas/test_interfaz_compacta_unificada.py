#!/usr/bin/env python3
"""Monitor sin scroll y con geometría comprobada: 1100 a 1920 px."""
import os,sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication,QScrollArea,QWidget,QSlider,QCheckBox
from main import MonitorWindow
from recording_lab import CONTROL_GROUPS,CHECKS
app=QApplication([])
win=MonitorWindow()
win.show()
lab=win.recording_lab
assert lab.sections.count()==4
assert set(lab.controls)=={key for _,group in CONTROL_GROUPS for key,*_ in group}
assert set(lab.checks)=={key for key,*_ in CHECKS}
assert lab.preview._compact_active
assert win.record_preview._compact_active
assert hasattr(win,"log_toggle")
page=win.monitor_page
assert not page.findChildren(QScrollArea),"La pantalla Monitor no debe utilizar barras de scroll."
assert hasattr(win.studio_home,"audio_lab_button")
assert win.studio_home.audio_lab_button.isEnabled()
for width,height in ((1100,735),(1280,768),(1440,900),(1920,1080)):
    win.resize(width,height)
    win.tabs.setCurrentWidget(page)
    for _ in range(15):app.processEvents()
    # Toda tarjeta fundamental cabe dentro de la misma página.
    assert lab.isVisible()
    for control in (lab,lab.presets,lab.run_button,lab.export_button,
                    lab.auto_after,lab.preview,
                    win.spectrum,win.oscillo,win.record_button,
                    win.record_preview,win.format,win.capture_rate,
                    win.file_prefix,win.folder_display):
        pos=control.mapTo(page,QPoint(0,0))
        assert pos.x()>=0 and pos.y()>=0
        assert pos.x()+control.width()<=page.width()+2,(
            width,height,control.objectName(),pos.x(),control.width(),page.width())
        assert pos.y()+control.height()<=page.height()+2,(
            width,height,control.objectName(),pos.y(),control.height(),page.height())
    assert win.spectrum.height()<=page.height()*.25,(height,win.spectrum.height())
    assert win.spectrum.height()<win.meter.height()*3
    for index in range(lab.sections.count()):
        lab.sections.setCurrentIndex(index)
        for _ in range(4):app.processEvents()
        sub=lab.sections.currentWidget()
        assert sub.isVisible()
        for control in sub.findChildren(QWidget):
            if not control.isVisible():continue
            if not isinstance(control,(QSlider,QCheckBox)) and not control.objectName():
                continue
            pos=control.mapTo(sub,QPoint(0,0))
            assert pos.x()>=0 and pos.y()>=0
            assert pos.x()+control.width()<=sub.width()+2,(
                width,index,control.objectName(),pos.x(),control.width(),sub.width())
            assert pos.y()+control.height()<=sub.height()+2,(
                width,index,control.objectName(),pos.y(),control.height(),sub.height())
    print("COMPACT_LAYOUT_PASS",width,height,
          "spectrum",win.spectrum.height(),
          "tab_height",lab.sections.height(),flush=True)
# Comprobación de que las funciones de audio siguen conectadas: ajustes
# de la GUI producen realmente cambios de parámetros.
lab.controls["bass"].setValue(4)
lab.controls["comp_threshold"].setValue(-25)
lab.auto_after.setChecked(True)
assert lab.snapshot()["bass"]==4
assert lab.snapshot()["comp_threshold"]==-25
assert lab.snapshot()["auto_after"] is True
assert "QGroupBox" in app.styleSheet() and "studioModuleSurface" in app.styleSheet()
assert win.tabs.count()>=8
print("COMPACT_UNIFIED_THEME_AND_AUDIO_CONTROLS_PASS",flush=True)
