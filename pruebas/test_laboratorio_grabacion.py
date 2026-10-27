#!/usr/bin/env python3
"""Procesamiento real de laboratorio, presets, dos renders y persistencia."""
from pathlib import Path
import os,sys,tempfile,time,hashlib,json,subprocess,wave
import numpy as np
os.environ["QT_QPA_PLATFORM"]="offscreen"
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
from PySide6.QtWidgets import QApplication,QMessageBox
from recording_lab_engine import DEFAULT,validated,filter_chain,command
from project_layout import DIRECTORIES
from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
from main import MonitorWindow
from project_flow import create_named_project
from studio_shell import save_project,open_project

def decode(path):
    result=subprocess.run(["ffmpeg","-v","error","-i",str(path),
       "-f","f32le","-ac","1","-ar","16000","pipe:1"],capture_output=True,
       timeout=15,check=True)
    return np.frombuffer(result.stdout,dtype="<f4").copy()

def wait_done(app,lab,seconds=30):
    started=time.monotonic()
    while lab.process is not None and time.monotonic()-started<seconds:
        app.processEvents();time.sleep(.03)
    assert lab.process is None,("FFmpeg no finalizó",lab.status.text())

with tempfile.TemporaryDirectory(prefix="stemmidi_audio_lab_tests_") as tmp:
    os.environ["STEMMIDI_WORKSPACE"]=tmp
    base=Path(tmp)
    source=base/"canción_prueba.wav"
    rate=16000
    tt=np.arange(rate*2,dtype=float)/rate
    x=(.21*np.sin(2*np.pi*230*tt)+.05*np.sin(2*np.pi*100*tt)+
       np.random.default_rng(10).normal(0,.008,len(tt)))
    x[:12000]=x[:12000]*.2
    with wave.open(str(source),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate)
        f.writeframes((np.clip(x,-1,1)*30000).astype("<i2").tobytes())
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    app=QApplication([])
    QMessageBox.information=staticmethod(lambda *a,**k:QMessageBox.Ok)
    QMessageBox.warning=staticmethod(lambda *a,**k:QMessageBox.Ok)
    w=MonitorWindow()
    assert create_named_project(w,"Laboratorio",base/"Proyectos",
        next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
    root=Path(w.project_dir)
    assert all((root/name).is_dir() for name in DIRECTORIES)
    lab=w.recording_lab
    assert len(lab.controls)==16,len(lab.controls)
    assert len(lab.checks)==6
    assert lab.snapshot()==DEFAULT,(lab.snapshot(),DEFAULT)
    w.studio_home.open_recording_lab()
    assert w.tabs.currentWidget() is w.monitor_page
    lab.set_source(source)
    assert lab.original==source and lab.processed is None
    assert lab.play_original.isEnabled()
    lab.apply_preset(dict(BUILTINS_PLACEHOLDER=1) if False else {
        "denoise":9,"declick":True,"gate_enabled":True,"bass":4,
        "lowmid":-3,"highmid":2,"comp_enabled":True,"comp_ratio":4,
        "deesser":35,"output_gain":2,"limiter":True})
    assert lab.snapshot()["comp_ratio"]==4
    assert lab.run_processing()
    wait_done(app,lab)
    output=lab.processed
    assert output and output.is_file(),lab.status.text()
    assert output.parent==root/"grabaciones"
    assert output.name=="canción_prueba_laboratorio.flac"
    orig=decode(source);processed=decode(output)
    assert len(orig)==len(processed) and np.isfinite(processed).all()
    difference=float(np.sqrt(np.mean((orig-processed)**2)))
    assert difference>.005,("No hubo procesamiento",difference)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
    assert lab.export_button.isEnabled()
    print("LAB_PROCESS_ACTUAL_FFMPEG_FLAC_PASS",round(difference,6),flush=True)
    assert lab.run_processing()
    wait_done(app,lab)
    second=lab.processed
    assert second and second!=output and second.parent==root/"grabaciones"
    assert output.is_file()
    assert not any(item.is_dir() for item in (root/"grabaciones").iterdir())
    print("LAB_TWO_RENDERS_WITHOUT_NESTED_FOLDERS_PASS",flush=True)
    lab.auto_after.setChecked(True)
    assert lab.snapshot()["auto_after"]
    lab.on_recording_finished(str(source),True)
    assert lab.process is not None
    wait_done(app,lab)
    third=lab.processed
    assert third!=second and third.parent==root/"grabaciones"
    print("AUTO_PROCESS_ONLY_AFTER_RECORDING_SUCCESS_PASS",flush=True)
    assert lab.source_path.text()==str(source)
    snap=lab.snapshot()
    assert save_project(w)
    data=json.loads(Path(w.project_path).read_text())
    assert data["parameters_recording_lab"]==snap
    assert Path(data["recording_lab_original"]).is_file()
    assert Path(data["recording_lab_processed"]).is_file()
    assert open_project(w,str(w.project_path))
    assert w.recording_lab.snapshot()==snap
    assert w.recording_lab.processed.is_file()
    assert w.recording_lab.original.is_file()
    print("LAB_PRESETS_MANIFEST_REOPEN_PASS",flush=True)
    original_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    assert sha==original_sha
    print("SOURCE_SHA256_UNCHANGED",sha,flush=True)
print("LABORATORIO_TOTAL_OK",flush=True)
