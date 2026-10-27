#!/usr/bin/env python3
"""Auditar Separación compacta en resoluciones reales, sin scroll ni solapes.

Requiere que botones y campos auténticos sigan accesibles sin alterar audio.
"""
import os,sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
from PySide6.QtWidgets import QApplication,QScrollArea,QPushButton,QWidget,QFrame
from PySide6.QtCore import QPoint,QEvent,QCoreApplication
from main import MonitorWindow
app=QApplication([])
w=MonitorWindow()
w.show()
sep=w.workbench.separator
results=w.workbench.sep_results
tab=w.workbench.separation_tab
for width,height in ((1100,735),(1200,760),(1280,768),(1440,900),(1920,1080)):
    w.resize(width,height)
    w.tabs.setCurrentWidget(tab)
    for i in range(20):app.processEvents()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    assert not sep.findChildren(QScrollArea),("Scroll principal prohibido",width)
    important=(sep.presets,sep.file_edit,sep.import_button,
               sep.profile,sep.manage_models_btn,sep.quality,sep.export_fmt,
               sep.dest_edit,sep.source_preview,sep.go,sep.progress,
               sep.cancel_button,sep.mix_button,sep.midi_button,
               sep.open_results_button,sep.load_previous_button,
               sep.library_button)
    for widget in important:
        assert widget.isVisibleTo(sep),(width,"no visible",widget.objectName())
        origin=widget.mapTo(sep,QPoint(0,0))
        assert origin.x()>=0 and origin.y()>=0,(width,widget.objectName(),origin)
        assert origin.x()+widget.width()<=sep.width()+2,(width,"cortado ancho",widget)
        assert origin.y()+widget.height()<=sep.height()+2,(width,"cortado alto",widget)
        assert widget.height()>=11 and widget.width()>=26,(width,"colapsado",widget)
    # No solapes en campos distintos. Los QGridLayout originales provocaban
    # etiquetas superpuestas en 1100x735: comprobar rectángulos reales.
    controls=(sep.file_edit,sep.import_button,sep.profile,
              sep.manage_models_btn,sep.quality,sep.export_fmt,
              sep.dest_edit)
    for i,a in enumerate(controls):
        for b in controls[i+1:]:
            ar=a.geometry();br=b.geometry()
            # Geometría local solo es comparable para el mismo padre
            if a.parentWidget() is b.parentWidget():
                assert not ar.intersects(br),("campos solapados",width,a,b,ar,br)
    assert sep.load_previous_button.isVisible()
    assert sep.library_button.isVisible()
    assert results.save_all is not None
    assert results.save_selected is not None
    assert results.new_task is not None
    headings=[l.text() for l in sep.findChildren(
        __import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel,"moduleCardHeading")]
    assert len(headings)==4,(width,headings)
    assert "01 · ARCHIVO Y AJUSTES" in headings
    assert "02 · PROCESAR" in headings
    assert "03 · DESTINOS Y HERRAMIENTAS" in headings
    print("COMPACT_SEPARATION_GEOMETRY_PASS",width,height,flush=True)
# Diagnostic log is accessible even with height limited:
w.resize(1100,735)
for _ in range(14):app.processEvents()
log=next(b for b in sep.findChildren(QPushButton) if b.text()=="Registro")
log.click()
app.processEvents()
dialog=getattr(sep,"_log_inspector",None)
assert dialog is not None and dialog.isVisible()
assert "Actividad del motor" in dialog.windowTitle()
dialog.close()
print("COMPACT_DIAGNOSTIC_ACCESS_PASS",flush=True)
# No real files are created or touched by this test.
print("COMPACT_SEPARATION_UI_ALL_OK",flush=True)
