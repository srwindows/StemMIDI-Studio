#!/usr/bin/env python3
"""Comprobación global de ajustes numéricos en todas las pantallas Qt."""
import os,sys,tempfile,wave
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_all_controls_") as t:
 os.environ["STEMMIDI_WORKSPACE"]=t
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtCore import QPoint,Qt
 from PySide6.QtWidgets import (
     QApplication,QAbstractSlider,QScrollBar,QAbstractSpinBox,QScrollArea,
     QComboBox,QWidget,QTabWidget
 )
 from main import MonitorWindow
 app=QApplication([])
 win=MonitorWindow()
 stub=Path(t)/"control_audio.wav"
 with wave.open(str(stub),"wb") as f:
    f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
    f.writeframes(bytes(16000*2))
 win.workbench.show_mixer([stub])
 count=0
 failures=[]
 def redraw():
    for _ in range(5):app.processEvents()
 def descendants(control,ancestor):
    p=control
    while p:
        if p is ancestor:return True
        p=p.parentWidget()
    return False
 def verify_current(tabname):
    global count
    tab=win.tabs.currentWidget()
    for c in tab.findChildren(QWidget):
        if not isinstance(c,(QAbstractSlider,QAbstractSpinBox,QComboBox)) or isinstance(c,QScrollBar):
            continue
        if not c.isVisibleTo(tab) or c.isHidden():continue
        path=[]
        p=c.parentWidget()
        while p is not None and p is not tab:
            if isinstance(p,QScrollArea):path.append(p)
            p=p.parentWidget()
        if p is None:continue
        for area in path:
            if not area.isVisibleTo(tab):continue
            area.ensureWidgetVisible(c,12,12)
            redraw()
        count+=1
        if isinstance(c,QAbstractSlider):
            minimum=((20,40) if c.orientation()==Qt.Vertical else (40,12))
        elif isinstance(c,QAbstractSpinBox):
            minimum=(56,22)
        else:minimum=(55,22)
        if c.width()<minimum[0] or c.height()<minimum[1]:
            failures.append((tabname,c.__class__.__name__,"size",c.width(),c.height()))
            continue
        for area in path:
            if not area.isVisibleTo(tab):continue
            point=c.mapTo(area.viewport(),QPoint(0,0))
            view=area.viewport().rect()
            if (point.x()+c.width()<1 or point.y()+c.height()<1 or
                point.x()>view.right() or point.y()>view.bottom()):
                failures.append((tabname,c.__class__.__name__,"outside_scroll",
                    c.width(),c.height(),point.x(),point.y(),view.width(),view.height()))
                break
 for w,h in ((1100,735),(1200,760),(1440,900),(1920,1030)):
    win.resize(w,h);win.show();redraw()
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i);redraw()
        tab=win.tabs.currentWidget()
        if tab is win.vocal_module:
            for n in range(win.vocal_module.studio_tabs.count()):
                win.vocal_module.studio_tabs.setCurrentIndex(n);redraw()
                verify_current(f"{w}x{h} Vocal pagina {n}")
        elif tab is win.workbench.midi_tab:
            for n in range(win.workbench.converter.form_tabs.count()):
                win.workbench.converter.form_tabs.setCurrentIndex(n);redraw()
                verify_current(f"{w}x{h} MIDI pagina {n}")
        else:
            verify_current(f"{w}x{h} {win.tabs.tabText(i)}")
    print("PASS_SIZE",w,h,"controls",count,"errors",len(failures),flush=True)
 for failure in failures[:25]:print("FAILED_CONTROL",failure,flush=True)
 assert count>480,("test coverage unexpectedly small",count)
 assert not failures,(count,len(failures),failures[:15])
 print("GLOBAL_NUMERIC_CONTROLS_ACCESSIBLE",count,flush=True)
