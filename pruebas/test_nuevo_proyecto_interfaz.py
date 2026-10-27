#!/usr/bin/env python3
"""Comprobación de botones accesibles y de diálogos sin pérdida de datos."""
import os,sys,tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stemmidi_gui_newproject_") as tmp:
 os.environ["STEMMIDI_WORKSPACE"]=tmp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QDialog,QPushButton,QLineEdit,QMessageBox
 from PySide6.QtCore import QTimer
 from main import MonitorWindow,STYLE
 from project_flow import create_named_project,new_project_dialog
 from studio_settings_library import settings_dialog
 app=QApplication([])
 app.setStyleSheet(STYLE)
 w=MonitorWindow();w.resize(1536,960);w.show()
 for _ in range(40):app.processEvents()
 banner=w.studio_banner
 titles=[b._caption.text() for b in banner.toolbar_buttons]
 assert "Nuevo proyecto" in titles and "Ajustes guardados" in titles,titles
 for width in (1120,1350,1536):
  w.resize(width,900)
  for _ in range(25):app.processEvents()
  geometries=[(button._caption.text(),button.geometry()) for button in banner.toolbar_buttons]
  assert all(button.isVisible() and button.width()>45 for button in banner.toolbar_buttons),geometries
  for i,a in enumerate(banner.toolbar_buttons):
   for b in banner.toolbar_buttons[i+1:]:
    assert not a.geometry().intersects(b.geometry()),(width,a._caption.text(),b._caption.text())
  if width==1536:
   assert w.grab().save("/tmp/stemmidi_nuevo_proyecto_cabecera.png")
 print("TOOLBAR_NEW_PROJECT_LIBRARY_NO_BUTTON_OVERLAP_PASS",flush=True)
 folder=Path(tmp)/"proyectos"
 assert create_named_project(w,"Antiguo",folder,w.format.currentText(),w.capture_rate.currentData())
 old_id=w.project_id
 # Simular clic en botón y rellenar el diálogo, sin acceso a archivos reales.
 def fill_dialog():
  dialogs=[x for x in app.topLevelWidgets() if isinstance(x,QDialog)
       and x.isVisible() and "Crear proyecto" in x.windowTitle()]
  assert len(dialogs)==1,[(x.windowTitle(),x.isVisible()) for x in app.topLevelWidgets() if isinstance(x,QDialog)]
  dlg=dialogs[0]
  assert dlg.grab().save("/tmp/stemmidi_nuevo_proyecto_dialogo.png")
  inputs=dlg.findChildren(QLineEdit)
  assert len(inputs)>=2
  inputs[0].setText("Nuevo con ajustes")
  inputs[1].setText(str(folder))
  buttons=[x for x in dlg.findChildren(QPushButton) if "Crear y conservar" in x.text()]
  assert len(buttons)==1
  buttons[0].click()
 orig_question=QMessageBox.question
 QMessageBox.question=staticmethod(lambda *a,**k:QMessageBox.Yes)
 QTimer.singleShot(300,fill_dialog)
 try:
  assert new_project_dialog(w,inherit_settings=True)
 finally:QMessageBox.question=orig_question
 assert w.project_name=="Nuevo con ajustes",w.project_name
 assert w.project_id!=old_id
 print("NEW_PROJECT_DIALOG_CREATE_PRESERVE_PASS",flush=True)
 def close_settings():
  dlg=next(x for x in app.topLevelWidgets() if isinstance(x,QDialog) and x.isVisible() and
     x.windowTitle()=="Biblioteca de ajustes · StemMIDI Studio")
  assert dlg.grab().save("/tmp/stemmidi_lista_de_ajustes.png")
  assert dlg.findChildren(QPushButton)
  dlg.accept()
 QTimer.singleShot(250,close_settings)
 settings_dialog(w)
 print("SETTINGS_LIBRARY_DIALOG_ACCESSIBLE_PASS",flush=True)
 w.close()
 print("GUI_NEW_PROJECT_AND_SETTINGS_LIST_ALL_PASS",flush=True)
