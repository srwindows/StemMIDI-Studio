"""Monitor PCM post-EQ, vúmetros, gráficos y escucha segura sin salida audible."""
from __future__ import annotations

import os,sys,math
from pathlib import Path
from unittest.mock import patch
import numpy as np
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from audio_engine import CaptureWorker
from capture_live_listen import is_feedback_route,LiveProcessedListen
from main import MonitorWindow

# Validación de retorno acústico/sumador: fuente .monitor nunca vuelve
# a entrar en ese mismo sink. Entrada física sí puede monitorizarse.
source="alsa_output.usb-FANTOM.pro-output-0.monitor"
sink="alsa_output.usb-FANTOM.pro-output-0"
alt="alsa_output.pci-0000_00_1f.3.hdmi-stereo"
assert is_feedback_route(source,sink)
assert not is_feedback_route(source,alt)
assert not is_feedback_route("alsa_input.usb-FANTOM.pro-input-0",sink)
guard=CaptureWorker(source,sample_rate=48000)
try:
    guard.set_live_listen(True,sink)
    raise AssertionError("Se permitió enviar señal al mismo monitor")
except ValueError:
    pass
guard.set_live_listen(True,alt)
assert guard._listen_requested==alt
guard.set_live_listen(False)
assert guard._listen_requested==""
print("SAFETY_NO_FEEDBACK_TO_SAME_MONITORED_SINK_PASS",flush=True)

class FakeInput:
    def __init__(self):self.closed=False
    def fileno(self):return 46
    def close(self):self.closed=True

class FakePacat:
    def __init__(self,args,**kwargs):
        self.args=list(args);self.stdin=FakeInput();self.terminated=False
    def poll(self):return 0 if self.terminated else None
    def terminate(self):self.terminated=True
    def wait(self,timeout=None):return 0
    def kill(self):self.terminated=True

streams=[]
state=[]
stereo=np.stack((
  (.21*np.sin(2*np.pi*145*np.arange(2048)/48000)).astype("<f4"),
  (.14*np.sin(2*np.pi*145*np.arange(2048)/48000)).astype("<f4")),
  axis=1).astype("<f4").tobytes()
proc=CaptureWorker(source,sample_rate=48000)
proc.set_input_controls(4,-25)
proc.set_input_eq(True,10,-4,3)
proc.set_live_listen(True,alt)
proc.live_listen_state.connect(lambda active,message:state.append((active,message)))

def writer(fd,data):
    streams.append(bytes(data))
    return len(data)

with patch("capture_live_listen.subprocess.Popen",side_effect=FakePacat), \
     patch("capture_live_listen.os.set_blocking") as setnonblock, \
     patch("capture_live_listen.os.write",side_effect=writer), \
     patch("capture_live_listen.shutil.which",return_value="/usr/bin/pacat"):
    expected=proc._processed_chunk(stereo)
    proc._feed_live_listen(expected)
    assert streams==[expected]
    assert proc._live_listen.process is not None
    assert "--format=float32le" in proc._live_listen.process.args
    assert "--device="+alt in proc._live_listen.process.args
    assert state[-1][0] is True
    setnonblock.assert_called()
    proc.set_input_eq(True,-10,5,-2)
    changed=proc._processed_chunk(stereo)
    proc._feed_live_listen(changed)
    assert streams[-1]==changed and changed!=expected
    proc.set_input_controls(-15,-25)
    lowered=proc._processed_chunk(stereo)
    proc._feed_live_listen(lowered)
    assert streams[-1]==lowered
    proc.set_live_listen(False)
    proc._feed_live_listen(lowered)
    assert proc._live_listen.process is None
assert state[-1][0] is False
print("LIVE_PLAYBACK_ACCEPTS_PRECISE_POST_EQ_GAIN_BALANCE_PCM_AND_STOPS_PASS",flush=True)

# Una salida bloqueada no debe bloquear la capturadora: se conserva
# la continuidad y en caso de exceso se desactiva solo la escucha.
sends=[]
def occasionally_block(fd,data):
    if not sends:
        sends.append(None)
        raise BlockingIOError()
    sends.append(bytes(data))
    return len(data)
with patch("capture_live_listen.subprocess.Popen",side_effect=FakePacat), \
     patch("capture_live_listen.os.set_blocking"), \
     patch("capture_live_listen.os.write",side_effect=occasionally_block), \
     patch("capture_live_listen.shutil.which",return_value="/usr/bin/pacat"):
    listen=LiveProcessedListen(source,48000)
    listen.start(alt)
    listen.feed(expected)
    assert listen.pending==expected
    listen.feed(changed)
    assert sends[-1]==expected+changed
    assert listen.pending==b""
    listen.stop()
print("NONBLOCKING_OUTPUT_MAINTAINS_PCM_CONTINUITY_AFTER_BACKPRESSURE_PASS",flush=True)

# Monitor flotante real: la misma señal ya corregida se entrega a
# los dos analizadores y a los VU, sin abrir el micrófono.
app=QApplication([])
w=MonitorWindow()
w.resize(1790,995);w.show()
h=w.studio_home;w.tabs.setCurrentWidget(h)
for _ in range(30):app.processEvents()
manager=h._floating_manager
manager.detach(h.mon_card)
for _ in range(40):app.processEvents()
view=manager.other_expanders[h.mon_card]
assert h.capture_analyzer_panel.isVisible()
assert h.capture_scope.isVisible() and h.capture_spectrum.isVisible()
assert view.review.balance_mount.count()>0
assert h.capture_balance_panel.parentWidget() is view.review
assert not h.listen_processed.isChecked()
assert h.record_transport.width()<=300
assert h.record_transport.clock.width()<=100
assert h.capture_analyzer_panel.height()>=185
# La escucha NO se activa sola. Evitar feedback incluso si se fuerza
# la selección de la misma salida capturada, y comprobar el destino.
from unittest.mock import patch as patch_ui
selected_source=str(w.sources.currentData() or "")
if selected_source.endswith(".monitor"):
    forbidden=selected_source[:-len(".monitor")]
    assert h.listen_output.findData(forbidden)<0
    h.listen_output.addItem("Ruta no permitida",forbidden)
    h.listen_output.setCurrentIndex(h.listen_output.count()-1)
    h.listen_processed.setChecked(True)
    assert not h.listen_processed.isChecked()
    assert h.capture_graph_status.text()=="Selecciona otra salida"
    h.listen_output.removeItem(h.listen_output.count()-1)
if h.listen_output.count():
    alternative=h.listen_output.itemData(0)
    w.worker=CaptureWorker(selected_source or "fake",sample_rate=48000)
    with patch_ui.object(w,"start_monitor",lambda:None):
        h.listen_output.setCurrentIndex(0)
        h.listen_processed.setChecked(True)
        assert h.listen_processed.isChecked()
        assert w.worker._listen_requested==alternative
        h.listen_processed.setChecked(False)
        assert w.worker._listen_requested==""
    w.worker=None
print("UI_LISTEN_REQUIRES_EXPLICIT_CHECK_AND_FILTERS_FORBIDDEN_DEVICE_PASS",flush=True)
assert (h.capture_scope.mapTo(h.capture_analyzer_panel,QPoint(0,h.capture_scope.height())).y()
        <=h.capture_spectrum.mapTo(h.capture_analyzer_panel,QPoint(0,0)).y())
print("FINAL_LAYOUT_TRANSPORT_BALANCE_SCOPE_SPECTRUM_WITHOUT_OVERLAP_PASS",flush=True)

w.worker=CaptureWorker("fake",sample_rate=48000)
w.worker.visual.connect(w.on_visual)
w.worker.levels.connect(w.on_levels)
h._capture_peak_hold=0
r=view.review
sample=np.stack((
    (.12*np.sin(2*np.pi*120*np.arange(2048)/48000)).astype("<f4"),
    (.12*np.sin(2*np.pi*120*np.arange(2048)/48000)).astype("<f4")),
    axis=1).astype("<f4")
r.sliders["bass"].setValue(-12)
r.sliders["volume"].setValue(85)
w.worker._last_visual=0
attenuated=w.worker._processed_chunk(sample.tobytes())
w.worker._visualize(attenuated)
for _ in range(5):app.processEvents()
low_rms=float(np.sqrt(np.mean(np.frombuffer(attenuated,dtype="<f4")**2)))
low_peak=h._capture_peak_hold
low_spectrum=list(h.capture_spectrum.bands)
low_wave=list(h.capture_scope.wave)
r.sliders["bass"].setValue(12)
w.worker._last_visual=0
boosted=w.worker._processed_chunk(sample.tobytes())
w.worker._visualize(boosted)
for _ in range(5):app.processEvents()
high_rms=float(np.sqrt(np.mean(np.frombuffer(boosted,dtype="<f4")**2)))
assert high_rms>low_rms*4.0,(high_rms,low_rms)
assert max(h.capture_spectrum.bands)>max(low_spectrum)
assert max(abs(x) for x in h.capture_scope.wave)>max(abs(x) for x in low_wave)*3
assert h._capture_peak_hold>low_peak
r.sliders["volume"].setValue(0)
w.worker._last_visual=0
silent=w.worker._processed_chunk(sample.tobytes())
w.worker._visualize(silent)
for _ in range(5):app.processEvents()
assert not np.max(np.abs(np.frombuffer(silent,dtype="<f4")))
assert max(abs(x) for x in h.capture_scope.wave)<1.e-6
assert max(h.capture_spectrum.bands)==0.
print("EQ_GAIN_CHANGES_SIMULTANEOUSLY_CONTROL_CAPTURE_WAVE_SPECTRUM_AND_VU_PASS",flush=True)

w.worker=None
manager.redock(h.mon_card)
for _ in range(35):app.processEvents()
assert h.capture_analyzer_panel.isHidden()
assert h.capture_balance_panel.isVisible()
assert h.record_transport.maximumWidth()==16777215
w.hide()
print("REALTIME_MONITOR_AUDIO_UI_SAFE_LOOPBACK_ALL_PASS",flush=True)
