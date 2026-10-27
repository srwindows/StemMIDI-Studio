#!/usr/bin/env python3
"""Auditoría ejecutable: 12 flotantes, mensaje, pregunta, input, fichero y diálogo."""
import os,sys,tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="dialogs_guard_test_") as folder:
 os.environ["STEMMIDI_WORKSPACE"]=folder
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtCore import Qt,QTimer
 from PySide6.QtWidgets import QApplication,QDialog,QMessageBox,QInputDialog,QFileDialog,QLineEdit
 from studio_file_browser import StemFileBrowser
 import dialog_guard
 from main import MonitorWindow,STYLE
 app=QApplication([]);app.setStyleSheet(STYLE)
 main=MonitorWindow();main.resize(1920,1008);main.show()
 main.tabs.setCurrentWidget(main.studio_home)
 manager=main.studio_home._floating_manager
 examples=[]
 def inspect(cls,owner,mode):
  widgets=[widget for widget in app.topLevelWidgets() if isinstance(widget,cls)
           and widget.isVisible() and widget is not owner]
  assert widgets,(cls,mode,[(w.windowTitle(),w.isVisible()) for w in app.topLevelWidgets()])
  dlg=widgets[-1]
  assert dlg.parentWidget() is owner,(mode,dlg.parentWidget(),owner)
  assert dlg.windowFlags() & Qt.WindowStaysOnTopHint,(mode,dlg.windowFlags())
  assert dlg.windowModality()==Qt.WindowModal,(mode,dlg.windowModality())
  examples.append(mode)
  if isinstance(dlg,QMessageBox):
   if mode=="question":dlg.done(QMessageBox.No)
   else:dlg.done(QMessageBox.Ok)
  elif isinstance(dlg,QInputDialog):
   dlg.setTextValue("Grabación prueba")
   dlg.done(QDialog.Accepted)
  else:dlg.done(QDialog.Rejected)
 for card in manager.cards:
  card.lock_button.click()
  for _ in range(6):app.processEvents()
  owner=manager.windows[card]
  # Explicit parent main despite the floating card being the true foreground
  QTimer.singleShot(100,lambda o=owner:inspect(QMessageBox,o,"information"))
  result=QMessageBox.information(main,"Diálogo detrás","Este aviso debe verse encima.")
  assert result==QMessageBox.Ok
  QTimer.singleShot(100,lambda o=owner:inspect(QMessageBox,o,"question"))
  result=QMessageBox.question(main,"Confirmar","Elegir No",
       QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
  assert result==QMessageBox.No
  if card is main.studio_home.piano_card:
   QTimer.singleShot(100,lambda o=owner:inspect(QInputDialog,o,"input"))
   val,accepted=QInputDialog.getText(main,"Nombre","Nombre:",text="Inicial")
   assert accepted and val=="Grabación prueba"
   custom=QDialog(main);custom.setWindowTitle("QDialog personalizado")
   QTimer.singleShot(100,lambda o=owner:inspect(QDialog,o,"custom"))
   assert custom.exec()==QDialog.Rejected
   from file_dialogs import _studio_picker
   QTimer.singleShot(180,lambda o=owner:inspect(StemFileBrowser,o,"file"))
   paths,_=QFileDialog.getOpenFileName(main,"Seleccionar audio",folder,"Audio (*.wav)")
   assert paths==""
  assert owner.isVisible() and manager.is_detached(card)
  card.lock_button.click()
  for _ in range(3):app.processEvents()
  assert card.isVisible() and not manager.is_detached(card)
 assert len(examples)==27,(len(examples),examples)
 assert not manager.windows
 main.close()
 assert not main.isVisible()
 print("AUDIT_12_FLOATS_24_MESSAGES_QUESTION_INPUT_CUSTOM_FILE_PARENT_FOCUS_PASS")
 print("METRICS",dialog_guard.metrics())
