#!/usr/bin/env python3
"""Procesado real de mezcla y edición de batería, con preservación del origen."""
import os,sys,tempfile,math,wave,time,hashlib
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_bateria_integra_") as t:
    os.environ["STEMMIDI_WORKSPACE"]=t
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication,QMessageBox
    from main import MonitorWindow
    from project_flow import create_named_project
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    from drum_module import PARTS
    from task_staging import inside
    import mido
    app=QApplication([])
    QMessageBox.information=staticmethod(lambda *a,**k:QMessageBox.Ok)
    QMessageBox.warning=staticmethod(lambda *a,**k:print("DRUM_WARNING",a[1:3],flush=True) or QMessageBox.Ok)
    w=MonitorWindow()
    assert create_named_project(w,"Bateria_Real",str(Path(t)/"Proyectos"),
                               next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
    drum=w.drum_module
    store=drum.storage
    folder=store.start()
    before={}
    sr=16000
    for index,part in enumerate(PARTS):
        fn=folder/(part+"_fuente.wav")
        with wave.open(str(fn),"wb") as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(sr)
            import struct
            samples=b"".join(struct.pack("<hh",int(2200*math.sin(2*math.pi*(130+index*70)*i/sr)),
                                           int(1800*math.sin(2*math.pi*(130+index*70)*i/sr)))
                             for i in range(sr*2))
            f.writeframes(samples)
        before[fn]=hashlib.sha256(fn.read_bytes()).hexdigest()
    store.set_separation(folder)
    assert len(store.items)==len(PARTS),store.items
    drum.refresh_results()
    studio=drum.studio
    studio.refresh()
    assert any(studio.sources.values())
    studio.apply_full_preset if False else None
    studio.apply_mix_preset(studio.mixer_presets.builtins["Rock potente"])
    studio.render_mix()
    start=time.monotonic()
    while studio.process is not None and time.monotonic()-start<35:
        app.processEvents();time.sleep(.03)
    assert studio.process is None, "Mezcla batería bloqueada"
    mixed=[p for p in store.items if "mezcla_bateria" in p.name]
    assert mixed and all(p.is_file() and p.stat().st_size>1000 for p in mixed),drum.status.text()
    print("DRUM_MIX_OUTPUTS_VALID",len(mixed),flush=True)
    i=studio.edit_source.findData(PARTS[0])
    assert i>=0
    studio.edit_source.setCurrentIndex(i)
    studio.trim_start.setValue(0)
    studio.trim_end.setValue(1000)
    studio.apply_editor_preset({"compression":35,"eq_mid":3,"edit_gain":-3})
    studio.render_edit()
    start=time.monotonic()
    while studio.process is not None and time.monotonic()-start<35:
        app.processEvents();time.sleep(.03)
    assert studio.process is None
    edited=[p for p in store.items if "edit_" in p.name]
    assert edited and edited[-1].stat().st_size>1000,drum.status.text()
    print("DRUM_EDIT_OUTPUTS_VALID",len(edited),flush=True)
    studio.apply_pattern_preset(studio.pattern_presets.builtins["Rock 4/4"])
    midi=studio._pattern()
    notes=sum(m.type=="note_on" and m.velocity>0 for tr in midi.tracks for m in tr)
    assert notes>0
    filename=Path(w.project_dir)/"backup"/"bateria"/"patron_prueba.mid"
    filename.parent.mkdir(parents=True,exist_ok=True)
    midi.save(filename)
    assert mido.MidiFile(filename).tracks
    print("DRUM_PATTERN_NOTES",notes,flush=True)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in before.items())
    print("DRUM_INPUTS_UNMODIFIED",len(before),flush=True)
    # Segunda separación de la misma batería: conservar ambos lotes sin
    # perder los anteriores y seleccionar el lote más reciente en el mixer.
    newer=store.processing_folder/"toma_nueva"
    newer.mkdir(parents=True,exist_ok=False)
    for index,part in enumerate(PARTS):
        fn=newer/(part+"_nueva.wav")
        with wave.open(str(fn),"wb") as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(sr)
            import struct
            samples=b"".join(struct.pack("<hh",int(1700*math.sin(2*math.pi*(180+index*50)*i/sr)),
                                           int(1600*math.sin(2*math.pi*(180+index*50)*i/sr)))
                             for i in range(sr*2))
            f.writeframes(samples)
    store.set_separation(newer)
    studio.refresh()
    assert all(store.folder in p.parents for p in store.items)
    from drum_module import category
    assert all(studio.sources[part].parent==newer for part in PARTS),studio.sources
    assert all(p in store.items for p in before)
    print("DRUM_TWO_TAKES_RETAINED_NEWEST_IN_MIXER",flush=True)
print("TEST_BATERIA_DSP_END2END_OK",flush=True)
