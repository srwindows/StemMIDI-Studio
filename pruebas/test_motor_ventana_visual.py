#!/usr/bin/env python3
"""Visualización de la corrección en contexto real Qt con telemetría simulada y etiquetada."""
import os,sys,tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.setdefault("STEMMIDI_NO_STARTUP_DIALOG","1")
with tempfile.TemporaryDirectory(prefix="stemmidi_qa_progress_") as root:
    os.environ["STEMMIDI_WORKSPACE"]=root
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from main import MonitorWindow,STYLE
    from separation_pro_controls import MotorDialog
    app=QApplication([])
    app.setStyleSheet(STYLE)
    main=MonitorWindow();main.resize(1760,1000);main.show()
    sep=main.workbench.separator
    sep.active_request=["Voz","Batería","Bajo","Guitarra","Piano","Otros"]
    sep.log.clear()
    sep.log.appendPlainText("Origen: grabación.wav")
    sep.log.appendPlainText("Etapa 1: preparando audio FLAC")
    sep.log.appendPlainText("Etapa 2: motor IA iniciado")
    d=MotorDialog(sep);sep.motor_dialog=d;d.show()
    d.start_job(["python","audio-separator"])
    d.receive_output("85%|█████| 52/62 [01:32<00:18]")
    sep.log.appendPlainText("85%|█████| 52/62 [01:32<00:18]")
    sep.log.appendPlainText("Procesando todas las fuentes con el modelo seleccionado")
    d.add_log()
    for _ in range(50):app.processEvents()
    assert all(bar.maximum()==100 and bar.value()==85 for bar in d.rows.values())
    assert d.total.maximum()==100 and d.total.value()==85
    shot="/tmp/stemmidi_progreso_motor_real_85_por_ciento.png"
    assert d.grab().save(shot)
    print("REAL_PROGRESS_VISUAL_85_PERCENT",shot,d.size())
    d.hide();main.close()
