#!/usr/bin/env python3
"""Verificación de identidad visual: 9 pestañas, 12 flotantes, explorador."""
import sys,os,time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from main import MonitorWindow,STYLE
from studio_file_browser import StemFileBrowser
from neon_identity import NEON_GLOBAL_CSS
app=QApplication([]);app.setStyle("Fusion");app.setStyleSheet(STYLE)
win=MonitorWindow();win.resize(1920,1020);win.show()
for _ in range(30):app.processEvents()
assert NEON_GLOBAL_CSS.strip() in app.styleSheet(),"tema neón no aplicado"
assert win.tabs.count()>=9
for i in range(win.tabs.count()):
 win.tabs.setCurrentIndex(i)
 for _ in range(45):app.processEvents()
 label=win.tabs.tabText(i).replace("/","-").replace(" ","_")
 filename=f"/tmp/stem_neon_tab_{i:02d}.png"
 assert win.grab().save(filename)
 print("NEON_TAB",i,label,win.tabs.currentWidget().size(),filename,flush=True)
win.tabs.setCurrentWidget(win.studio_home)
home=win.studio_home
manager=home._floating_manager
assert len(manager.cards)==12
for index,card in enumerate(manager.cards):
 card.lock_button.click()
 for _ in range(23):app.processEvents()
 assert manager.is_detached(card)
 floating=manager.windows[card]
 assert floating.grab().save(f"/tmp/stem_neon_flotante_{index:02d}.png")
 card.lock_button.click()
 for _ in range(12):app.processEvents()
browser=StemFileBrowser(win,"Abrir proyecto","/media/javi/Recuperacion",
                       "Proyecto StemMIDI (*.stemstudio.json *.json)","open")
browser.show()
for _ in range(42):app.processEvents()
assert browser.grab().save("/tmp/stem_neon_explorador.png")
assert "#00caff" in app.styleSheet()
browser.reject()
win.close()
print("NEON_9_TABS_12_FLOATS_EXPLORER_VISUAL_PASS",flush=True)
