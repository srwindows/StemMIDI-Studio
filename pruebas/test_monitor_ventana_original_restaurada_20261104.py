"""La tarjeta 1 MONITOR/GRABACIÓN conserva todos sus VU originales.

Asegura que la corrección de los demás vúmetros nunca modifica la
referencia, ni reemplaza los QProgressBar de su transporte flotante.
"""
import os,sys,tempfile
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QProgressBar
from PySide6.QtCore import Qt
from main import MonitorWindow
from project_flow import create_named_project
from studio_home import VerticalMeter
from studio_vu_unified import UnifiedPercentBar
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

with tempfile.TemporaryDirectory(prefix="monitor_original_") as td:
    app=QApplication([])
    w=MonitorWindow();w.resize(1700,960);w.show()
    assert create_named_project(w,"REFERENCIA_MONITOR",
             Path(td)/"proyectos",w.format.currentText(),44100)
    h=w.studio_home
    manager=h._floating_manager
    manager.detach(h.mon_card)
    for _ in range(18):app.processEvents()
    window=manager.windows[h.mon_card]
    # El Monitor es una excepción deliberada: lleva el VU ORIGINAL de
    # grabación, no un transporte duplicado de la ventana emergente.
    assert not hasattr(window,"float_transport")
    assert isinstance(h.level_meter,VerticalMeter)
    assert h.level_meter.width()==39
    assert h.level_meter in window.findChildren(VerticalMeter)
    h.level_meter.set_levels(1.,1.)
    app.processEvents()
    img=h.level_meter.grab().toImage()
    top=img.pixelColor(8,9)
    bottom=img.pixelColor(8,max(2,img.height()-30))
    assert top.red()>top.green(),top.name()
    assert bottom.green()>bottom.red(),bottom.name()
    assert window.grab().save("/tmp/stemmidi_monitor_original_restaurado_20261104.png")
    manager.redock(h.mon_card)
    w.close();app.processEvents()
print("MONITOR_FLOAT_ORIGINAL_BARS_UNMODIFIED_PASS",flush=True)
