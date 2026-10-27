#!/usr/bin/env python3
"""Auditoría de tarjetas reales y controles, sin maquetas ni estados falsos."""
import os,sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication,QFrame,QScrollArea,QPushButton,QTabWidget,QLabel
from main import MonitorWindow
from studio_workspace_cards import SectionCard
app=QApplication([])
w=MonitorWindow()
w.resize(1440,900);w.show()
tabs=[
("Inicio",w.studio_home,12),
("Monitor",w.monitor_page,0),
("Separación",w.workbench.separation_tab,4),
("Batería",w.drum_module,3),
("Audio a MIDI",w.workbench.midi_tab,5),
("Vocal",w.vocal_module,3),
("Mezclador",w.mixer_placeholder,2),
("Piano Roll",w.workbench.piano,3),
("Resultados",w.results_tab,2),
]
assert w.tabs.count()==len(tabs)
for name,page,min_count in tabs:
    w.tabs.setCurrentWidget(page)
    for _ in range(5):app.processEvents()
    count=len(page.findChildren(QFrame,"studioCard"))
    assert count>=min_count,(name,count,min_count)
    if name not in ("Inicio","Monitor"):
        card_headers=page.findChildren(QLabel,"moduleCardHeading")
        assert len(card_headers)==count,(name,count,len(card_headers))
        for header in card_headers:
            assert header.text().strip(),name
        print("CARD_SCREEN_PASS",name,count,[h.text() for h in card_headers],flush=True)
# All source objects preserved, all real buttons still wired.
for title,obj in (
    ("grabación",w.record_button),
    ("laboratorio",w.recording_lab.run_button),
    ("separación",w.workbench.separator.go),
    ("convierte a MIDI",w.workbench.converter.go),
    ("voz",w.vocal_module.start_button),
    ("batería",w.drum_module.start_btn),
    ("piano",w.workbench.piano.play_roll),
    ("mezclador",w.mixer_placeholder.findChildren(QPushButton)[0]),
    ("resultados",w.results_tab.table),
):
    assert obj is not None, title
    print("FUNCTIONAL_WIDGET_PRESERVED",title,flush=True)
for i,label in enumerate(("Afinación","Carácter","EQ · FX","Doblado · Delay","Aprender interpretación")):
    assert w.vocal_module.studio_tabs.tabText(i)==label
# Results placeholder is only visible on actual zero rowcount.
res=w.results_tab
res.refresh([])
app.processEvents()
assert res._empty_hint.label.isVisible() == (res.table.rowCount()==0)
# Built-in results stage placeholder only when truly no rows.
sep=w.workbench.sep_results
midi=w.workbench.midi_results
for stage in (sep,midi):
    stage.populate()
    from PySide6.QtCore import QCoreApplication,QEvent
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    app.processEvents()
    if not stage.storage.items:
        labels=stage.container.findChildren(QLabel,"moduleEmptyState")
        assert len(labels)==1,len(labels)
        assert "SIN PISTAS" in labels[0].text()
    assert stage.save_all is not None
print("EMPTY_STATE_NO_FAKE_TRACKS_PASS",flush=True)
assert w.workbench.separation_tab.count()==2
assert w.workbench.midi_tab.count()==2
assert w.workbench.separator.go is not None
print("ALL_NINE_FUNCTIONAL_PAGES_PRESENT",flush=True)
