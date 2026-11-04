"""Prueba E2E de la ventana vocal: render FLAC + guardado en Resultados."""
from __future__ import annotations
from pathlib import Path
import os,sys,tempfile,math,struct,wave,time,subprocess,json
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from main import MonitorWindow
from project_flow import create_named_project
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

with tempfile.TemporaryDirectory(prefix="vocal_live_fx_20261104_") as td:
    root=Path(td)
    app=QApplication([])
    w=MonitorWindow();w.resize(1680,1000);w.show()
    assert create_named_project(w,"VozFX",root/"proyectos",
                                w.format.currentText(),44100)
    h=w.studio_home
    manager=h._floating_manager
    card=h.vocal_card
    manager.detach(card)
    for _ in range(12):app.processEvents()
    v=manager.other_expanders[card].vocal_studio
    input_=root/"voz_test.wav"
    with wave.open(str(input_),"wb") as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(22050)
        out.writeframes(b"".join(struct.pack("<h",
            int(8000*math.sin(2*math.pi*220*i/22050))) for i in range(22050*3)))
    import file_dialogs
    old=file_dialogs.get_open_file_name
    file_dialogs.get_open_file_name=lambda *_args,**_kw:(str(input_),"WAV")
    try:v.import_voice()
    finally:file_dialogs.get_open_file_name=old
    assert Path(v.mod.input.text()).is_file()
    # Bypass evita el costoso pYIN durante esta prueba, pero todos los FX
    # se procesan de verdad y se exportan a FLAC 24 bits.
    v.mod.bypass_tune.setChecked(True)
    v.mod.compression.setValue(43)
    v.mod.highpass.setValue(80)
    v.mod.warmth.setValue(23)
    v.mod.presence.setValue(20)
    v.mod.reverb.setValue(0)
    v.mod.delay.setValue(0)
    assert v.mod.executable().is_file()
    v.start()
    assert v.mod.process is not None
    deadline=time.monotonic()+85
    while v.mod.process is not None and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(.07)
    for _ in range(20):app.processEvents()
    assert v.mod.process is None,("Timed out rendering",v.mod.status.text())
    v.refresh()
    outputs=[Path(p) for p in v.mod.storage.items if Path(p).is_file()]
    assert outputs,("No result",v.mod.status.text(),v.mod._run_output[-900:])
    output=outputs[-1]
    assert output.suffix.lower()==".flac"
    meta=json.loads(subprocess.run(["ffprobe","-v","error",
        "-show_entries","format=duration",
        "-show_entries","stream=codec_name,sample_rate",
        "-of","json",str(output)],capture_output=True,
        text=True,check=True).stdout)
    assert any(t.get("codec_name")=="flac" for t in meta["streams"])
    assert 2.9<float(meta["format"]["duration"])<3.5,meta
    assert output.stat().st_size>10000
    print("FLAC_EFFECTS_RENDER_REAL_AUDIO_PASS",str(output),
          output.stat().st_size,v.mod.status.text(),flush=True)

    # Guardado en Resultados visible y sin alterar la toma ni el original.
    result=v.save_result()
    assert result and Path(result).is_file(),v.session_status.text()
    assert Path(result).resolve()!=input_.resolve()
    assert Path(result).resolve()!=output.resolve()
    assert (Path(w.project_dir)/"resultados")==Path(result).parent
    assert Path(result).stat().st_size==output.stat().st_size
    assert Path(result) in h._gather_files(),[
        str(x) for x in h._gather_files() if "voz_" in str(x)]
    assert v._session_file().is_file()
    print("VOCAL_SAVE_COPY_TO_PROJECT_RESULTS_PRESERVES_ORIGINAL_PASS",flush=True)

    v.play_original()
    assert h._vocal_listen_file==str(Path(v.mod.input.text()).resolve())
    v.play_processed()
    assert h._vocal_listen_file==str(output.resolve())
    h.player.stop()
    print("VOCAL_AB_COMPARISON_REAL_FILES_PASS",flush=True)
    manager.redock(card)
    assert h._vocal_listen_file is None
    w.close();app.processEvents()
print("VOCAL_END_TO_END_FLOATING_PROCESS_SAVE_RESULTS_PASS",flush=True)
