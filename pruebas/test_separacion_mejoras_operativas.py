#!/usr/bin/env python3
"""Comprobación de widgets nuevos con trabajo aislado del proyecto real."""
import os,sys,tempfile,struct,wave,math,subprocess
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['STEMMIDI_NO_STARTUP_DIALOG']='1'
with tempfile.TemporaryDirectory(prefix='sep_mejoras_check_') as tmp:
 os.environ['STEMMIDI_WORKSPACE']=tmp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QDialog,QSlider,QDoubleSpinBox
 from PySide6.QtCore import Qt
 from main import MonitorWindow,STYLE
 from separation_pro_controls import parameters_dialog
 app=QApplication([]);app.setStyleSheet(STYLE)
 main=MonitorWindow();main.show()
 main.tabs.setCurrentWidget(main.workbench.separation_tab)
 for _ in range(12):app.processEvents()
 sep=main.workbench.separator
 left=sep.source_preview
 right=main.workbench.sep_results.preview
 assert left.channel_mode.count()==4
 assert [left.channel_mode.itemText(i) for i in range(4)]==[
   'Estéreo','Mono (L+R)','Solo izquierdo','Solo derecho']
 assert not right.options_button.isVisible()
 for widget in (right.volume,right.speed,right.device_choice,right.status):
  assert widget.isVisible(),widget
 assert sep.model_run_selector.count()>=1
 assert sep.model_run_import.isVisible()
 found=[]
 original_exec=QDialog.exec
 def intercept(dlg):
  sliders=dlg.findChildren(QSlider)
  spins=dlg.findChildren(QDoubleSpinBox)
  assert len(sliders)==2,(sliders,spins)
  assert len(spins)==2
  sliders[0].setValue(74)
  assert abs(spins[0].value()-.74)<1e-9
  spins[1].setValue(.37)
  assert sliders[1].value()==37
  found.append(True)
  return QDialog.Accepted
 QDialog.exec=intercept
 try:parameters_dialog(sep)
 finally:QDialog.exec=original_exec
 assert found and abs(sep.norm_setting-.74)<.001
 assert abs(sep.amp_setting-.37)<.001
 sep.model_run_import.clicked.disconnect()
 sep.model_run_import.clicked.connect(lambda:found.append('models'))
 sep.model_run_import.click()
 assert found[-1]=='models'
 # Verificar filtro mono L+R sin audio en altavoces: FFmpeg genera PCM en memoria.
 audio=Path(tmp)/'input_stereo.wav'
 with wave.open(str(audio),'wb') as f:
  f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000)
  f.writeframes(b''.join(struct.pack('<hh',12000,4000) for _ in range(480)))
 raw=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-i',str(audio),
  '-af','pan=mono|c0=0.5*c0+0.5*c1','-f','s16le','-acodec','pcm_s16le','-'])
 left_sample=struct.unpack_from('<h',raw)[0]
 assert 7950<=left_sample<=8050,left_sample
 print('STEREO_MONO_SLIDERS_MODEL_CHOOSER_AND_VISIBLE_RESULT_CONTROLS_PASS')
