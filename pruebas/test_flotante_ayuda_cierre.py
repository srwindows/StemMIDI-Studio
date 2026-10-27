import os,sys,time
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['STEMMIDI_NO_STARTUP_DIALOG']='1'
os.environ['STEMMIDI_WORKSPACE']='/tmp/stemmidi_help_test_space'
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from main import MonitorWindow,STYLE
app=QApplication([]);app.setStyleSheet(STYLE)
w=MonitorWindow();w.show()
w.tabs.setCurrentWidget(w.studio_home)
c=w.studio_home.piano_card
m=w.studio_home._floating_manager
c.lock_button.click();app.processEvents()
assert m.is_detached(c)
c.help_button.click();app.processEvents()
help=w._help_center
print('HELP',help.isVisible(),help.parent() is m.windows[c],flush=True)
help.close_btn.click();app.processEvents()
print('HELP_CLOSED',help.isVisible(), 'FLOAT',m.windows[c].isVisible(),flush=True)
assert not help.isVisible() and m.windows[c].isVisible()
c.help_button.click();app.processEvents()
assert help.isVisible() and help.parent() is m.windows[c]
help.close_btn.click();app.processEvents()
assert not help.isVisible() and m.windows[c].isVisible()
c.lock_button.click();app.processEvents()
assert not m.is_detached(c)
c.lock_button.click();app.processEvents()
w.close();app.processEvents()
assert not w.isVisible() and not m.windows
print('HELP_CLOSE_RECOVER_NORMAL_QUIT_PASS')
