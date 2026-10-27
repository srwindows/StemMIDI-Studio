#!/usr/bin/env python3
"""Test real: última toma, tonalidad de escucha, presets, redock, seguridad."""
import os,sys,tempfile,wave,struct,math,hashlib,subprocess
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stemmidi_toma_eq_") as temp:
 os.environ["STEMMIDI_WORKSPACE"]=temp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QCheckBox
 from PySide6.QtCore import Qt
 from main import MonitorWindow,STYLE
 app=QApplication([]);app.setStyleSheet(STYLE)
 track=Path(temp)/"Grabacion_REAL.wav"
 with wave.open(str(track),"wb") as wav:
  wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
  wav.writeframes(b"".join(struct.pack("<hh",
        int(10000*math.sin(2*math.pi*120*i/48000)),
        int(7000*math.sin(2*math.pi*2800*i/48000)))
        for i in range(48000)))
 original=hashlib.sha256(track.read_bytes()).hexdigest()
 w=MonitorWindow();w.resize(1920,1008);w.show()
 h=w.studio_home;w.tabs.setCurrentWidget(h)
 m=h._floating_manager
 assert h.audio_lab_button.isVisible()
 assert not hasattr(h.record_review.backend,"_preview_eq") is False
 assert not h.record_review.play.isEnabled()
 w.last_file=str(track)
 h.mon_card.lock_button.click()
 for _ in range(40):app.processEvents()
 view=m.other_expanders[h.mon_card]
 review=view.review
 assert m.is_detached(h.mon_card)
 assert not h.audio_lab_button.isVisible()
 assert review.play.isEnabled()
 assert review.stop.isEnabled()
 assert review.backend.current_file==str(track)
 assert "Grabacion_REAL" in review.filename.text()
 assert review.vu.isVisible()
 assert review.sliders["bass"].isVisible()
 assert review.sliders["mid"].isVisible()
 assert review.sliders["treble"].isVisible()
 assert review.sliders["volume"].isVisible()
 review.sliders["bass"].setValue(7)
 review.sliders["mid"].setValue(-3)
 review.sliders["treble"].setValue(5)
 review.apply_eq()
 assert review.backend._preview_eq==(7,-3,5)
 review.eq_enabled.setChecked(False)
 assert review.backend._preview_eq==(0,0,0)
 review.eq_enabled.setChecked(True)
 assert review.backend._preview_eq==(7,-3,5)
 review.sliders["volume"].setValue(65)
 assert review.backend.volume.value()==65
 review.channel_mode.setCurrentText("Mono (L+R)")
 assert review.backend.channel_mode.currentText()=="Mono (L+R)"
 view.name.setText("Escucha calidad")
 view.save_preset()
 review.flat_eq()
 assert review.backend._preview_eq==(0,0,0)
 view.choice.setCurrentText("— Elegir preset —")
 view.choice.setCurrentText("Escucha calidad")
 assert review.backend._preview_eq==(7,-3,5)
 assert review.backend.volume.value()==65
 assert review.channel_mode.currentText()=="Mono (L+R)"
 graph="bass=g=7:f=110,equalizer=f=1000:t=q:w=1:g=-3,treble=g=5:f=4800,alimiter=limit=0.95"
 proc=subprocess.run(["ffmpeg","-nostdin","-v","error","-i",str(track),
                     "-af",graph,"-f","null","-"],capture_output=True,timeout=12)
 assert proc.returncode==0,proc.stderr.decode()[-600:]
 floatwin=m.windows[h.mon_card]
 print("FLOAT_DIMS",floatwin.width(),floatwin.height(),flush=True)
 print("PREVIEW_DIMS",review.width(),review.height(),
       "BOTTOM",review.mapTo(floatwin,__import__("PySide6").QtCore.QPoint(0,review.height())).y(),
       "WIN",floatwin.height(),flush=True)
 floatwin.grab().save("/tmp/stemmidi_monitor_play_tonos_pre_final.png")
 h.mon_card.lock_button.click()
 for _ in range(35):app.processEvents()
 assert not m.is_detached(h.mon_card)
 assert h.audio_lab_button.isVisible()
 assert not review.isVisible()
 assert track.exists()
 assert hashlib.sha256(track.read_bytes()).hexdigest()==original
 w.close()
 assert not m.windows
 print("MONITOR_PLAY_TONE_EQ_PRESET_ORIGINAL_LAB_AND_CLOSE_PASS",flush=True)
