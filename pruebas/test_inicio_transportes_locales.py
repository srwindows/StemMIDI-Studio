#!/usr/bin/env python3
"""Verifica transportes de Inicio, VU sin señal ficticia y ausencia de navegación."""
import os,sys,tempfile,wave,math,struct,time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stemmidi_12_transport_") as temp:
 os.environ["STEMMIDI_WORKSPACE"]=temp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QMessageBox
 from PySide6.QtCore import Qt
 from main import MonitorWindow,STYLE
 from floating_transport import KINDS,MULTI,STEMS,DRUMS
 app=QApplication([]);app.setStyleSheet(STYLE)
 main=MonitorWindow();main.resize(1920,1008);main.show()
 h=main.studio_home
 main.tabs.setCurrentWidget(h)
 m=h._floating_manager
 assert len(m.cards)==12
 # Audio sintetizado para medir señal real L/R; nunca toca archivos de proyectos.
 target=Path(temp)/"voces.wav"
 with wave.open(str(target),"wb") as wav:
  wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
  wav.writeframes(b"".join(struct.pack("<hh",
     int(14500*math.sin(2*math.pi*220*i/48000)),
     int(2600*math.sin(2*math.pi*650*i/48000))) for i in range(48000)))
 for c in m.cards:
  c.lock_button.click()
  for _ in range(13):app.processEvents()
  assert m.is_detached(c)
  assert main.tabs.currentWidget() is h
  f=m.windows[c]
  kind=dict(zip(m.cards,KINDS))[c]
  if kind!="monitor":
   assert f.float_transport is not None,kind
   t=f.float_transport
   assert t.play.isVisible() and t.pause.isVisible() and t.stop.isVisible(),kind
   assert t.clock.isVisible() and t.timeline.isVisible(),kind
   assert len(t.vus)==(len(DRUMS) if kind=="drum_stems" else
                        len(STEMS) if kind in MULTI else 2),(kind,len(t.vus))
   t.refresh()
   assert all(v.value()==0 for v in t.vus.values()),kind
   t.play.click()
   assert main.tabs.currentWidget() is h,kind
  else:
   assert h.record_transport.isVisible()
   assert h.level_meter.isVisible()
   assert h.record_review.play.isVisible()
   assert h.record_review.vu.isVisible()
  # El botón principal dentro de cada tarjeta tampoco debe abrir la pestaña.
  if kind=="mixer":h.open_mixer()
  if kind=="piano":h.open_piano()
  if kind=="wave":h.open_audio()
  if kind=="results":h.open_results()
  if kind=="tracks":h.open_results()
  if kind=="monitor":h.open_recording_lab()
  if kind=="drums":h.open_drum_module()
  if kind=="vocal":h.open_vocal_module()
  if kind=="sep":
   # No navegar al módulo de batería mientras separación está flotante.
   h.open_drum_module()
  assert main.tabs.currentWidget() is h,("navigation",kind)
  c.lock_button.click()
  for _ in range(8):app.processEvents()
  assert not m.is_detached(c),kind
  assert main.tabs.currentWidget() is h,("return",kind)
 # Pista real seleccionada => los VU pertenecen a la pista reproducida,
 # los otros seis siguen a cero (el reproductor es monofónico por selección).
 h.track_rows["Voces"]["path"]=target
 h.track_rows["Voces"]["gain"].setEnabled(True)
 h.track_card.lock_button.click()
 for _ in range(8):app.processEvents()
 t=m.windows[h.track_card].float_transport
 assert t._selected_source()==target
 t.play.click()
 deadline=time.time()+8
 while len(h.player._measured_vu.levels)<5 and time.time()<deadline:
  app.processEvents();time.sleep(.08)
 assert len(h.player._measured_vu.levels)>=5
 assert h.player._measured_vu.levels[3][0] > h.player._measured_vu.levels[3][1]>0
 t.refresh()
 assert all(v.value()==0 for n,v in t.vus.items() if n!="Voces")
 # Limpieza de reproductor y retorno sin ningún salto de pestaña.
 t.stop_selected()
 h.track_card.lock_button.click()
 main.close()
 assert not m.windows
 print("TWELVE_FLOAT_LOCAL_TRANSPORT_AND_REAL_TRACK_VU_NO_NAVIGATION_PASS")
