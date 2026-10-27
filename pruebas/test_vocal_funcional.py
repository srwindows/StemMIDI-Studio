#!/usr/bin/env python3
"""Regresión vocal: DSP real, dos tomas, presets, salidas y fuente original intacta."""
from __future__ import annotations
import os,sys,tempfile,hashlib,math,time,wave
from pathlib import Path
SOURCE_PROJECT=Path(__file__).resolve().parents[1]
sites=list((SOURCE_PROJECT/"entorno_ia/lib").glob("python*/site-packages"))
sites+=list((SOURCE_PROJECT/"entorno_ia/Lib").glob("site-packages"))
for site in sites:
    sys.path.insert(0,str(site))
import numpy as np
import soundfile as sf

os.environ["QT_QPA_PLATFORM"]="offscreen"
SOURCE_PROJECT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="stemmidi_vocal_end2end_") as t:
    base=Path(t)
    os.environ["STEMMIDI_WORKSPACE"]=str(base)
    # Durante la prueba la aplicación aislada usa el motor instalado real.
    (base/"entorno_ia").symlink_to(SOURCE_PROJECT/"entorno_ia",target_is_directory=True)
    (base/"vocal_tune_engine.py").symlink_to(SOURCE_PROJECT/"vocal_tune_engine.py")
    os.environ["PYTHONPATH"]=str(SOURCE_PROJECT)
    sys.path.insert(0,str(SOURCE_PROJECT))
    from PySide6.QtWidgets import QApplication,QMessageBox
    from main import MonitorWindow
    from project_flow import create_named_project
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    from task_staging import inside
    from vocal_fx import process_vocal_fx
    from vocal_tune_engine import apply_dynamics

    # Señal de prueba: región suave, canto sintético armónico y sibilancias.
    sr=22050
    clock=np.arange(sr*3,dtype=np.float32)/sr
    envelope=np.where(clock<.7,.035,.82).astype(np.float32)
    music=(.18*np.sin(2*np.pi*220*clock)+
           .08*np.sin(2*np.pi*440*clock)+
           .14*np.sin(2*np.pi*6400*clock))
    mono=(envelope*music).astype(np.float32)
    xy=np.stack([mono,.92*mono+.003*np.sin(2*np.pi*420*clock)],axis=1)*1.5
    original=base/"voz_fuente_externa.wav"
    sf.write(original,xy,sr,subtype="PCM_16")
    original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    def changed(out):
        return float(np.sqrt(np.mean((out-xy)**2)))
    cases={
       "dulce":dict(character="Dulce",character_amount=85),
       "rasgada":dict(character="Rasgada",character_amount=85),
       "calida":dict(character="Cálida",character_amount=85),
       "aireada":dict(character="Aireada",character_amount=85),
       "warmth":dict(warmth=80),
       "air":dict(air=80),
       "presence":dict(presence=80),
       "deesser":dict(deesser=80),
       "gate":dict(gate=80),
       "reverb":dict(reverb=80),
       "doubler":dict(doubler=80),
       "delay":dict(delay=80),
       "stereo_width":dict(stereo_width=180),
       "gain":dict(output_gain_db=-6)
    }
    for name,params in cases.items():
        value=changed(process_vocal_fx(xy,sr,**params))
        assert value>1.e-5,(name,value)
        print("FX_REAL",name,round(value,7),flush=True)
    for name,params in (
            ("highpass",dict(highpass=130)),
            ("compression",dict(compression=90))):
        delta=changed(apply_dynamics(xy,sr,**params))
        assert delta>1.e-5,(name,delta)
        print("DYNAMICS_REAL",name,round(delta,7),flush=True)
    # Wet=0 debe ignorar procesado de EQ-FX (salvo gain/master).
    dry=process_vocal_fx(xy,sr,warmth=90,wet=0)
    assert np.array_equal(dry,xy),"Mezcla wet=0 altera la señal seca"
    # Natural no crea armónicos: intensidad deshabilitada en GUI.
    nochange=process_vocal_fx(xy,sr,character="Natural",character_amount=95)
    assert np.array_equal(nochange,xy)
    print("CONTROL_BYPASS_SEMANTICA_OK",flush=True)
    from vocal_tune_engine import render
    no_notes_output=base/"procesado_sin_correccion.flac"
    report=render(original,no_notes_output,0,"Mayor",0,
                  warmth=65,compression=35,highpass=100,bypass_tune=False)
    assert report["corrected_regions"]==0,report
    assert report["effects_active"],report
    audio_without_note_fix,out_sr=sf.read(no_notes_output,always_2d=True)
    assert out_sr==sr and audio_without_note_fix.shape==xy.shape
    assert np.sqrt(np.mean((audio_without_note_fix-xy)**2))>.001
    print("VOICE_NO_NOTES_EFFECTS_STILL_RENDER",flush=True)

    app=QApplication([])
    QMessageBox.warning=staticmethod(lambda *a,**k:(
        print("QT_WARNING",str(a[1:3]),flush=True) or QMessageBox.Ok))
    QMessageBox.information=staticmethod(lambda *a,**k:QMessageBox.Ok)
    main=MonitorWindow()
    assert create_named_project(main,"Voz_Auditoria",str(base/"Proyectos"),
                                next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
    project=Path(main.project_dir)
    voice=main.vocal_module
    voice.input.setText(str(original))
    voice.studio_tabs.setCurrentIndex(4)
    assert voice.full_presets.isEnabled()
    assert voice.full_presets.isVisible()==False or voice.full_presets.parent() is voice
    for label,params in (("Primera",dict(
        character="Dulce",character_amount=70,warmth=25,reverb=30)),
                         ("Segunda",dict(
        character="Rasgada",character_amount=78,air=65,delay=45))):
        voice.apply_full_preset(params)
        voice.bypass_tune.setChecked(True)
        voice.start()
        started=time.monotonic()
        while voice.process is not None and time.monotonic()-started<45:
            app.processEvents();time.sleep(.025)
        assert voice.process is None,"Motor vocal no finalizó"
        assert len(voice.storage.items)==(1 if label=="Primera" else 2),(
            label,voice.status.text(),voice.storage.items)
        assert all(f.is_file() and inside(f,project/"temporales"/"vocal")
                   for f in voice.storage.items)
        print("VOICE_RENDER",label,voice.status.text(),flush=True)
    first,second=voice.storage.items
    a,fa=sf.read(first,always_2d=True)
    b,fb=sf.read(second,always_2d=True)
    assert fa==fb==sr and a.shape==b.shape==xy.shape
    assert float(np.sqrt(np.mean((a-b)**2)))>0.002
    assert original_hash==hashlib.sha256(original.read_bytes()).hexdigest()
    saved=voice.storage.save_paths(project/"backup"/"vocal",[second])
    assert len(saved)==1 and saved[0].is_file()
    from task_staging import TaskStorage
    restored=TaskStorage("vocal",main.project_id,project)
    assert restored.items==voice.storage.items
    print("VOICE_TWO_VERSIONS_VISIBLE_REOPEN_SAFE",flush=True)
    print("VOICE_SOURCE_ORIGINAL_UNTOUCHED",flush=True)
print("TEST_VOCAL_END2END_OK",flush=True)
