import os,sys,tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['STEMMIDI_NO_STARTUP_DIALOG']='1'
with tempfile.TemporaryDirectory(prefix='sep_layout_prof_') as tmp:
 os.environ['STEMMIDI_WORKSPACE']=tmp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QScrollArea
 from PySide6.QtCore import QPoint,QEvent,QCoreApplication
 from main import MonitorWindow,STYLE
 app=QApplication([]);app.setStyleSheet(STYLE)
 main=MonitorWindow();main.show()
 page=main.workbench.separation_tab
 sep=main.workbench.separator
 results=main.workbench.sep_results
 main.tabs.setCurrentWidget(page)
 sep.profile.setCurrentText('6 pistas · DETALLADO — Voz, batería, bajo, guitarra, piano, otros')
 for _ in range(12):app.processEvents()
 expected=('Voz','Batería','Bajo','Guitarra','Piano','Otros')
 assert sep.requested_stems()==list(expected)
 for name in expected:assert sep.stem_checks[name].isVisible()
 sep.stem_all.setChecked(False)
 assert sep.requested_stems()==[]
 sep.stem_checks['Guitarra'].setChecked(True)
 assert sep.requested_stems()==['Guitarra']
 sep.stem_all.setChecked(True)
 assert sep.requested_stems()==list(expected)
 for w,h in [(1920,1008),(1440,900),(1280,768),(1100,735),(1920,1008)]:
  main.resize(w,h)
  for _ in range(40):app.processEvents()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
  app.processEvents()
  controls=[sep.stem_all,sep.stem_parameters_btn,results.mark_all_btn,
            results.mark_none_btn,results.remove_selected_btn,results.pitch_btn]
  controls.extend(sep.stem_checks[n] for n in expected)
  for widget in controls:
   assert widget.isVisible(),(w,'hidden',widget.text())
   p=widget.mapTo(page,QPoint(0,0))
   if not(0<=p.x() and p.x()+widget.width()<=page.width()+2
          and 0<=p.y() and p.y()+widget.height()<=page.height()+2):
    raise AssertionError((w,'clipped',widget.text(),p,widget.size(),page.size()))
  print('ALL_NEW_CONTROLS_VISIBLE',w,h,'panels',page.sizes(),flush=True)
 print('NEW_CONTROLS_QT_LAYOUT_PASS',flush=True)
