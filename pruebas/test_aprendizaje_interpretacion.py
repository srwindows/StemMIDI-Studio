#!/usr/bin/env python3
"""Prueba end-to-end de transferencia de interpretación dentro de vocal GUI."""
from pathlib import Path
import os,sys,tempfile,time,hashlib,json
os.environ["QT_QPA_PLATFORM"]="offscreen"
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
sys.path.insert(0,str(next((R/"entorno_ia/lib").glob("python*/site-packages"))))
from PySide6.QtWidgets import QApplication,QMessageBox
from main import MonitorWindow
from project_flow import create_named_project
from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
import numpy as np
import soundfile as sf

with tempfile.TemporaryDirectory(prefix="stemmidi_interpretacion_test_") as d:
    base=Path(d)
    os.environ["STEMMIDI_WORKSPACE"]=d
    (base/"entorno_ia").symlink_to(R/"entorno_ia",target_is_directory=True)
    (base/"vocal_interpretation_engine.py").symlink_to(
        R/"vocal_interpretation_engine.py")
    (base/"vocal_tune_engine.py").symlink_to(R/"vocal_tune_engine.py")
    sr=16000;t=np.arange(sr*3)/sr
    src=base/"mi_voz.wav"
    reference=base/"referencia.wav"
    for path,pitch,vibrato,volume in [
        (src,174.,.002,.21),(reference,196.,.011,.26)]:
        phase=2*np.pi*np.cumsum(pitch*(1+vibrato*np.sin(2*np.pi*6*t)))/sr
        sample=volume*(np.sin(phase)+.24*np.sin(2*phase))
        sample*=np.minimum(1.,t/.11)*np.minimum(1.,(3-t)/.15)
        sf.write(str(path),sample.astype(np.float32),sr)
    hashes={path:hashlib.sha256(path.read_bytes()).hexdigest()
             for path in (src,reference)}
    app=QApplication([])
    warnings=[]
    QMessageBox.information=staticmethod(
        lambda *args: (warnings.append(str(args[2])),QMessageBox.Ok)[1])
    QMessageBox.warning=staticmethod(
        lambda *args: (warnings.append("ADVERTENCIA "+str(args[2])),QMessageBox.Ok)[1])
    win=MonitorWindow()
    assert create_named_project(win,"Interpretación de prueba",str(base/"Proyectos"),
                                next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
    voice=win.vocal_module
    voice.input.setText(str(src))
    voice.reference.setText(str(reference))
    voice.studio_tabs.setCurrentIndex(4)
    assert voice.studio_tabs.tabText(4)=="Aprender interpretación"
    voice.start_learning()
    assert voice.process is None and warnings
    voice.ref_consent.setChecked(True)
    voice.start_learning()
    assert voice.process is None and "misma" in warnings[-1].lower()
    voice.learn_same_song.setChecked(True)
    voice.learn_melody.setValue(86)
    voice.learn_vibrato.setValue(67)
    voice.learn_dynamics.setValue(73)
    voice.learn_timing.setValue(32)
    snap=voice.full_preset_snapshot()
    assert snap["learn_melody"]==86 and snap["learn_same_song"]==True
    voice.start_learning()
    assert voice.process is not None,(warnings,voice.status.text(),voice.learn_same_song.isChecked(),voice.ref_consent.isChecked(),voice.input.text(),voice.reference.text(),voice.executable())
    start=time.monotonic()
    while voice.process is not None and time.monotonic()-start<85:
        app.processEvents()
        time.sleep(.025)
    assert voice.process is None,"Proceso IA colgado"
    files=[Path(p) for p in voice.storage.items if Path(p).name.startswith("voz_interpretada")]
    assert len(files)==1,(voice.status.text(),voice._run_output,voice.storage.items)
    rendered,sample_rate=sf.read(str(files[0]),always_2d=True)
    source_audio,_=sf.read(str(src),always_2d=True)
    assert sample_rate==sr and rendered.shape==source_audio.shape
    assert np.isfinite(rendered).all() and np.max(np.abs(rendered))<=1
    diff=float(np.sqrt(np.mean((rendered-source_audio)**2)))
    assert diff>.02,("No cambió el sonido",diff)
    assert "Interpretación" in voice.table.item(0,0).text(),voice.table.item(0,0).text()
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==h
               for path,h in hashes.items())
    print("RENDER_VOZ_REAL_CREADO",str(files[0]),flush=True)
    print("IDENTIDAD_AUDIO_ORIGEN_NO_CAMBIO",hashes,flush=True)
    print("DIFERENCIA_RMS",round(diff,5),flush=True)
    # Verificar que la curva tonal se ha acercado realmente a la referencia,
    # no solo que el audio cambia de volumen, dinámica o ecualización.
    import librosa
    target_audio,_=sf.read(str(reference),always_2d=True)
    def median_pitch(x):
        contour=librosa.yin(x[:,0].astype("float32"),sr=sr,
                           fmin=140,fmax=260,frame_length=2048,hop_length=320)
        return float(np.median(contour))
    original_hz=median_pitch(source_audio)
    learned_hz=median_pitch(rendered)
    reference_hz=median_pitch(target_audio)
    assert abs(learned_hz-reference_hz)<abs(original_hz-reference_hz),(
        original_hz,learned_hz,reference_hz)
    print("AFINACION_ACERCADA_A_REFERENCIA_HZ",
          round(original_hz,2),round(learned_hz,2),round(reference_hz,2),
          flush=True)
    # El proyecto debe recordar valores, fuentes y consentimiento.
    from studio_shell import save_project,open_project
    assert save_project(win)
    data=json.loads(Path(win.project_path).read_text())
    assert data["parameters_vocal_full"]["learn_melody"]==86
    assert data["vocal_reference_authorized"]==True
    assert data["vocal_reference"]
    assert open_project(win,str(win.project_path))
    assert win.vocal_module.learn_melody.value()==86
    assert win.vocal_module.learn_dynamics.value()==73
    assert win.vocal_module.learn_same_song.isChecked()
    assert win.vocal_module.ref_consent.isChecked()
    assert Path(win.vocal_module.reference.text()).is_file()
    print("GUI_RENDER_RESULT_PROJECT_REOPEN_OK",flush=True)
print("TEST_APRENDIZAJE_VOCAL_GUI_OK",flush=True)
