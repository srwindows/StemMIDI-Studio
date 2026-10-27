#!/usr/bin/env python3
"""Porcentajes de separación honestos, monótonos y sin animación de Qt."""
import os,sys,tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QWidget,QPlainTextEdit,QProgressBar
from separation_pro_controls import MotorDialog,extract_engine_percent
app=QApplication([])
assert extract_engine_percent("85%|██████| 52/62 [01:32<00:18, 1.76s/it]")==[85]
assert extract_engine_percent("Rendimiento: 2 pasadas; 44.1 kHz; 16% normalización")==[]
assert extract_engine_percent(" 123%|too big  23%|real")==[23]
class Sep(QWidget):
 def __init__(self):
  super().__init__()
  self.active_request=["Voz","Batería","Bajo","Guitarra","Piano","Otros"]
  self.log=QPlainTextEdit()
  self.progress=QProgressBar()
  self.latest_outputs=[]
sep=Sep()
d=MotorDialog(sep)
assert d.total.minimum()==0 and d.total.maximum()==100
assert all(b.minimum()==0 and b.maximum()==100 for b in d.rows.values())
assert d.total.value()==0
d.start_job(["ffmpeg","-i","input.wav"])
d.receive_output("80%|for unrelated ffmpeg")
assert d.total.value()==0,"Conversión sin % fiable no debe falsear IA"
d.stage_update("Preparación FFmpeg confirmada")
assert "FFmpeg" in d.stage.text()
d.start_job(["/ruta/entorno_ia/bin/python","audio-separator","--model_filename","htdemucs_6s.yaml"])
d.receive_output("Probando modelo IA; 44100 Hz")
assert d.total.value()==0
d.receive_output("40%")
assert d.total.value()==0,"Necesita marca de tqdm; no cualquier %"
d.receive_output("|████ 20/50 [00:40]")
assert d.total.value()==40, d.total.value()
assert all(b.value()==40 for b in d.rows.values())
d.receive_output("85%|█████████| 52/62 [01:32]")
assert d.total.value()==85
d.receive_output("11%|██| 9/80 [00:03]")
assert d.total.value()==85 and all(b.value()==85 for b in d.rows.values()),"Nunca retroceder"
d.receive_output("100%|██████████| 62/62")
assert d.total.value()==99, "Escribir archivos se confirma aparte"
assert all(b.value()==99 for b in d.rows.values())
assert sep.progress.value()==99
with tempfile.TemporaryDirectory(prefix="stemmidi_real_outputs_") as td:
 base=Path(td)
 vocals=base/"toma_(Vocals)_test.flac"
 vocals.write_bytes(b"VALID")
 d.set_ready([vocals])
 assert d.rows["Voz"].value()==100
 assert all(d.rows[n].value()==99 for n in sep.active_request if n!="Voz")
 assert d.total.value()==99
 d.completed(False)
 assert d.total.value()==99 and d.rows["Batería"].value()==99
 for label,token in [("Batería","Drums"),("Bajo","Bass"),
                     ("Guitarra","Guitar"),("Piano","Piano"),("Otros","Other")]:
  (base/f"toma_({token})_test.flac").write_bytes(b"VALID")
 sep.latest_outputs=list(base.iterdir())
 d.completed(True)
 assert all(b.value()==100 for b in d.rows.values())
 assert d.total.value()==100 and sep.progress.value()==100
 assert "6 pistas" in d.stage.text()
 sep.log.setPlainText("Origen: toma.wav\nEtapa 1: preparación\n85%|52/62\nArchivo: vocals.flac\nCOMPLETADO")
 d.add_log()
 assert "COMPLETADO" in d.technical.toPlainText() and "Etapa 1" in d.technical.toPlainText()
print("MOTOR_PERCENT_TQDM_CHUNKS_MONOTONIC_NO_MARQUEE_FILES_VERIFIED_LOG_PASS")
