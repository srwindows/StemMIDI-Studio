"""Regresión de todos los desplegables flotantes: nativos, bien anclados.

Se ejecuta en un workspace nuevo, sin tocar proyectos de usuario.
"""
import os,sys,time,tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","xcb")
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stemmidi_popup_all_module_") as td:
 os.environ["STEMMIDI_WORKSPACE"]=td
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QComboBox,QMenu
 from PySide6.QtCore import QPoint,Qt
 from PySide6.QtTest import QTest
 from main import MonitorWindow
 import project_exit_guard
 project_exit_guard.ask_exit_choice=lambda _: "discard"
 app=QApplication([])
 w=MonitorWindow();w.resize(1550,920);w.show()
 manager=w.studio_home._floating_manager
 passes=0;total=0
 for index,card in enumerate(manager.cards):
  manager.detach(card)
  for _ in range(10):app.processEvents()
  win=manager.windows[card]
  win.move(55+(index%4)*55,65+(index%3)*75)
  for _ in range(10):app.processEvents()
  combos=[x for x in card.findChildren(QComboBox) if x.count()>1 and x.isVisible()]
  for combo in combos:
   total+=1
   popup=combo.view().window()
   assert popup.graphicsProxyWidget() is None,("POPUP STILL EMBEDDED",card.header.text(),combo.objectName())
   expected=combo.mapToGlobal(QPoint(0,combo.height()))
   combo.showPopup()
   for _ in range(4):app.processEvents()
   actual=popup.geometry()
   assert abs(actual.x()-expected.x())<30,(
      "WRONG X",card.header.text(),combo.objectName(),actual,expected)
   assert actual.right()>expected.x() and actual.x()<win.geometry().right()+30
   assert popup.isVisible(),("HIDDEN MENU",card.header.text(),combo.objectName())
   combo.hidePopup()
   for _ in range(3):app.processEvents()
   passes+=1
  if card is w.studio_home.sep_card:
   menu=manager._mini_sep_menu
   assert menu.graphicsProxyWidget() is None,"QMenu still graphics scene child"
   btn=menu.parentWidget()
   pos=btn.mapToGlobal(QPoint(0,btn.height()))
   menu.popup(pos)
   for _ in range(4):app.processEvents()
   assert menu.graphicsProxyWidget() is None and menu.isVisible()
   assert abs(menu.geometry().x()-pos.x())<=20,("WRONG MENU",menu.geometry(),pos)
   menu.hide()
   passes+=1
  manager.redock(card)
  for _ in range(3):app.processEvents()
 # Real selection on quant combo, after moves, with mouse click in popup.
 card=w.studio_home.info_card
 manager.detach(card)
 for _ in range(15):app.processEvents()
 win=manager.windows[card]
 win.move(85,95)
 for _ in range(8):app.processEvents()
 ex=manager.other_expanders[card].info_expanded
 combo=ex.quant
 combo.setCurrentIndex(0)
 combo.showPopup()
 for _ in range(8):app.processEvents()
 listview=combo.view()
 target=listview.model().index(5,0)
 listview.scrollTo(target)
 app.processEvents()
 area=listview.visualRect(target)
 assert not area.isEmpty(),area
 QTest.mouseClick(listview.viewport(),Qt.LeftButton,pos=area.center())
 for _ in range(10):app.processEvents()
 assert combo.currentIndex()==5,("MOUSE COULD NOT SELECT QUANT",combo.currentIndex())
 assert ex.backend.quant_grid==combo.itemData(5)
 print("QUANTIZATION_REAL_POPUP_MOUSE_CHOICE_PASS",combo.currentText(),flush=True)
 combo.showPopup();app.processEvents()
 assert combo.view().window().graphicsProxyWidget() is None
 combo.hidePopup()
 manager.redock(card)
 w.close()
 print("ALL_MODULES_POPUP_NATIVE_AND_ANCHORED",passes,"/",total,"COMBOS",flush=True)
