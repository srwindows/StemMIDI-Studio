#!/usr/bin/env python3
"""Interacción real en QFileSystemModel + explorador: mouse, filtros, navegación, vacío."""
import os,sys,tempfile,time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtTest import QTest
from studio_file_browser import StemFileBrowser
app=QApplication([])
def pump(seconds=.15):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  app.processEvents();time.sleep(.015)
def assert_directory_index(d,p):
 end=time.monotonic()+3
 while time.monotonic()<end:
  idx=d._proxy.mapFromSource(d._model.index(str(p)))
  if idx.isValid() and idx.parent()==d.view.rootIndex():return idx
  pump(.05)
 raise AssertionError(("not indexed",p,str(d.current_dir),d._proxy.rowCount(d.view.rootIndex())))
with tempfile.TemporaryDirectory(prefix="stemui_interaction_") as temp:
 root=Path(temp)
 (root/"Carpeta de prueba").mkdir()
 (root/"Carpeta de prueba"/"ensayo.wav").write_bytes(b"STEM")
 (root/"Carpeta de prueba"/"toma.flac").write_bytes(b"STEM")
 (root/"Carpeta de prueba"/"oculto.mp3").write_bytes(b"STEM")
 empty=root/"Carpeta vacía"; empty.mkdir()
 dlg=StemFileBrowser(None,"Importar audio",str(root),"Audio (*.wav *.flac *.mp3)","open")
 dlg.show();pump(.5)
 assert dlg.location.text()==str(root.resolve())
 assert dlg.view.model()==dlg._proxy
 assert dlg.view.horizontalScrollBar().maximum()==0,dlg.view.horizontalScrollBar().maximum()
 # Doble clic real abre un directorio.
 idx=assert_directory_index(dlg,root/"Carpeta de prueba")
 rect=dlg.view.visualRect(idx)
 assert not rect.isEmpty(),rect
 print('BEFORE_DBL',rect,dlg.view.indexAt(rect.center()).data(),flush=True)
 QTest.mouseClick(dlg.view.viewport(),Qt.LeftButton,pos=rect.center())
 QTest.mouseDClick(dlg.view.viewport(),Qt.LeftButton,pos=rect.center())
 pump(.7)
 print('AFTER_DBL',dlg.current_dir,flush=True)
 assert dlg.current_dir==root/"Carpeta de prueba",(dlg.current_dir,root)
 # Filtro y búsqueda operativos
 dlg.search.setText("toma");pump(.1)
 assert dlg._proxy.rowCount(dlg.view.rootIndex())==1,dlg._proxy.rowCount(dlg.view.rootIndex())
 dlg.search.clear();pump(.2)
 assert dlg._proxy.rowCount(dlg.view.rootIndex())==3
 # Seleccionar archivo mediante clic (sin escribir nombre)
 idx=assert_directory_index(dlg,root/"Carpeta de prueba"/"ensayo.wav")
 rect=dlg.view.visualRect(idx)
 QTest.mouseClick(dlg.view.viewport(),Qt.LeftButton,pos=rect.center())
 pump(.1)
 assert dlg.filename.text()=="ensayo.wav",dlg.filename.text()
 dlg.ok_button.click();pump(.1)
 assert dlg.result()==QDialog.Accepted and dlg.selected_paths==[str(root/"Carpeta de prueba"/"ensayo.wav")],dlg.selected_paths
 print("MOUSE_DOUBLE_CLICK_SEARCH_FILTER_FILE_SELECT_PASS",flush=True)
 # Navegación Atrás/Adelante vía botones y selección por ruta
 dlg2=StemFileBrowser(None,"Prueba navegación",str(root),"Audio (*.wav)","open")
 dlg2.show();pump(.2)
 dlg2.go_to(root/"Carpeta de prueba");pump(.2)
 dlg2.back.click();pump(.1)
 assert dlg2.current_dir==root
 dlg2.forward.click();pump(.1)
 assert dlg2.current_dir==root/"Carpeta de prueba"
 dlg2.location.setText(str(root));dlg2.location.returnPressed.emit();pump(.1)
 assert dlg2.current_dir==root
 dlg2.go_to(empty);pump(.45)
 assert dlg2.empty_hint.isVisible(),("empty hint absent",dlg2._proxy.rowCount(dlg2.view.rootIndex()),dlg2.empty_hint.text())
 assert "Esta carpeta no contiene archivos" in dlg2.empty_hint.text()
 dlg2.grab().save("/tmp/stemmidi_highcontrast_empty_1920.png")
 dlg2.reject()
 print("BACK_FORWARD_PATH_EMPTY_STATE_PASS",flush=True)
 print("HIGH_CONTRAST_MOUSE_NAVIGATION_ALL_PASS",flush=True)
