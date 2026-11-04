"""Visual 1920×1080 monitor realtime layout, source PCM visual and routing."""
import os,sys
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from main import MonitorWindow
app=QApplication([])
w=MonitorWindow();w.resize(1800,990);w.show()
h=w.studio_home;w.tabs.setCurrentWidget(h)
for _ in range(40):app.processEvents()
h._floating_manager.detach(h.mon_card)
for _ in range(50):app.processEvents()
view=h._floating_manager.other_expanders[h.mon_card]
win=h._floating_manager.windows[h.mon_card]
print("SCREEN",app.primaryScreen().geometry(),flush=True)
for name,widget in (("FLOAT",win),("CARD",h.mon_card),("REVIEW",view.review),
                    ("BALANCE",h.capture_balance_panel),("SIG",h.capture_analyzer_panel),
                    ("SCOPE",h.capture_scope),("SPECTRUM",h.capture_spectrum),
                    ("DIAGNOSTIC",h.capture_diagnostics),("REC_TRANSPORT",h.record_transport)):
    print(name,"SIZE",widget.width(),widget.height(),"VISIBLE",widget.isVisible(),
          "PARENT",widget.parentWidget().objectName() if widget.parentWidget() else None,
          "POS",widget.mapTo(win,__import__("PySide6").QtCore.QPoint(0,0)),flush=True)
view.review.sliders["bass"].setValue(9)
h.sync_capture_visual([.1,.2,.8]*16,[.05,.2,-.2,.5]*51+[0])
for _ in range(20):app.processEvents()
assert win.grab().save("/tmp/stemmidi_monitor_rt_visual_floating_1920x1080.png")
print("OUTPUTS",h.listen_output.count(),[(h.listen_output.itemText(i),h.listen_output.itemData(i))
      for i in range(h.listen_output.count())],flush=True)
print("CAPTURE_SOURCE",w.sources.currentData(),flush=True)
h._floating_manager.redock(h.mon_card)
for _ in range(25):app.processEvents()
print("REDOCK_BALANCE",h.capture_balance_panel.isVisible(),
      "REDOCK_GRAPH_HIDDEN",h.capture_analyzer_panel.isHidden(),flush=True)
w.hide()
