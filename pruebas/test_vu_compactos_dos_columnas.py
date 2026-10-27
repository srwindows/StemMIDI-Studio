#!/usr/bin/env python3
"""Regresión visual: VU compactos en 2 columnas sin barras interminables."""
import os,sys,tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stem_compact_meters_") as workspace:
    os.environ["STEMMIDI_WORKSPACE"]=workspace
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt,QPoint
    from main import MonitorWindow,STYLE
    from floating_transport import STEMS,DRUMS,MULTI,KINDS
    app=QApplication([])
    app.setStyleSheet(STYLE)
    main=MonitorWindow();main.resize(1920,1008);main.show()
    home=main.studio_home;main.tabs.setCurrentWidget(home)
    manager=home._floating_manager
    for kind,card in zip(KINDS,manager.cards):
        if kind not in MULTI:continue
        card.lock_button.click()
        for _ in range(50):app.processEvents()
        assert manager.is_detached(card)
        floating=manager.windows[card]
        t=floating.float_transport
        assert t.compact_vu_panel.width()<=750,(kind,t.compact_vu_panel.width())
        all_meters=[*t.master_vus.values(),*t.vus.values()]
        assert all(m.width()==190 for m in all_meters),(kind,[m.width() for m in all_meters])
        assert all(m.height()>0 and m.isVisible() for m in all_meters)
        assert all(m.value()==0 for m in all_meters)
        assert all(v.text()=="0%" for v in [*t.master_labels.values(),*t.vu_labels.values()])
        assert len(t.vus)==(6 if kind=="drum_stems" else 7)
        left=DRUMS if kind=="drum_stems" else STEMS
        count=(len(left)+1)//2
        assert t.vus[left[0]].mapTo(t.compact_vu_panel,QPoint()).x()+200<t.vus[left[count]].mapTo(t.compact_vu_panel,QPoint()).x()+5
        assert t.vus[left[0]].mapTo(t.compact_vu_panel,QPoint()).y()<t.vus[left[count-1]].mapTo(t.compact_vu_panel,QPoint()).y()
        assert t.vus[left[count]].mapTo(t.compact_vu_panel,QPoint()).y()<t.vus[left[-1]].mapTo(t.compact_vu_panel,QPoint()).y()
        assert main.tabs.currentWidget() is home
        shot=Path(f"/tmp/stem_compact_vu_{kind}.png")
        assert floating.grab().save(str(shot))
        print("COMPACT_VU",kind, "floating",floating.width(),floating.height(),
              "meters",len(all_meters),"panel",t.compact_vu_panel.size(),
              "at",t.compact_vu_panel.mapTo(floating,QPoint()),"screenshot",shot,flush=True)
        card.lock_button.click()
        for _ in range(20):app.processEvents()
        assert not manager.is_detached(card)
    main.close()
    print("COMPACT_VU_TWO_COLUMNS_FOUR_MODULES_VISUAL_PASS",flush=True)
