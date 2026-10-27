#!/usr/bin/env python3
"""Separación: misma pantalla, sin scroll de página, controles reales accesibles.

Las pruebas no utilizan archivos del usuario: se ejecutan en TemporaryDirectory.
"""
import os,sys,tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stem_sep_compact_validation_") as directory:
    os.environ["STEMMIDI_WORKSPACE"]=directory
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication,QScrollArea,QPushButton
    from PySide6.QtCore import QPoint,QCoreApplication,QEvent
    from main import MonitorWindow
    app=QApplication([])
    main=MonitorWindow()
    main.show()
    left=main.workbench.separator
    right=main.workbench.sep_results
    area=main.workbench.separation_tab
    controls=[left.presets,left.file_edit,left.profile,left.quality,
              left.export_fmt,left.dest_edit,left.import_button,
              left.manage_models_btn,left.source_preview,
              left.go,left.cancel_button,left.progress,
              left.mix_button,left.midi_button,left.open_results_button,
              left.load_previous_button,left.library_button]
    # Repeated shrink/enlarge cycles reveal QLayout transitions.
    for width,height in ((1440,900),(1100,735),(1280,768),
                         (1920,1080),(1100,735),(1440,900)):
        main.resize(width,height)
        main.tabs.setCurrentWidget(area)
        for _ in range(30):app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        app.processEvents()
        assert not left.findChildren(QScrollArea)
        for control in controls:
            assert control.isVisible(),(width,"hidden",control.objectName())
            pos=control.mapTo(area,QPoint(0,0))
            assert pos.x()>=0 and pos.y()>=0,(width,"offscreen top",control.objectName(),pos)
            assert pos.x()+control.width()<=area.width()+2,(width,"offscreen right",control.objectName())
            assert pos.y()+control.height()<=area.height()+2,(width,"offscreen bottom",control.objectName())
            assert control.height()>=12,(width,"collapsed",control.objectName())
        # Button rectangles may not overlap one another.
        buttons=[left.mix_button,left.midi_button,left.open_results_button,
                 left.load_previous_button,left.library_button,
                 next(c for c in left.findChildren(QPushButton) if c.text()=="Registro")]
        for i,first in enumerate(buttons):
            p=first.mapTo(area,QPoint(0,0))
            a=(p.x(),p.y(),p.x()+first.width(),p.y()+first.height())
            for second in buttons[i+1:]:
                q=second.mapTo(area,QPoint(0,0))
                b=(q.x(),q.y(),q.x()+second.width(),q.y()+second.height())
                intersect=min(a[2],b[2])-max(a[0],b[0])
                vertical=min(a[3],b[3])-max(a[1],b[1])
                assert intersect<=0 or vertical<=0,(width,"buttons overlap",first.text(),second.text())
        print("NO_SCROLL_NO_OVERLAP_PASS",width,height,flush=True)
    assert len(right.findChildren(QScrollArea))==1,"Only results track list may scroll"
    # Verify existing production code signatures/callbacks remain live.
    from PySide6.QtWidgets import QMessageBox
    warnings=[]
    QMessageBox.warning=staticmethod(lambda *args,**kwargs: warnings.append(args[2]))
    left.file_edit.clear()
    left.go.click()
    app.processEvents()
    assert warnings and "Selecciona un archivo" in warnings[-1],warnings
    assert callable(left.choose_input) and callable(right.save_files)
    print("PROCESS_BUTTON_CONNECTED_AND_RESULTS_ACCESS_PASS",flush=True)
print("SEPARATION_COMPACT_LAYOUT_COMPLETE",flush=True)
