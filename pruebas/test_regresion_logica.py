#!/usr/bin/env python3
"""Pruebas automáticas de regresión con datos sintéticos, sin tocar proyectos."""
import os,sys,tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stemmidi_regresion_") as location:
    os.environ["STEMMIDI_WORKSPACE"]=location
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import mido
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from audio_engine import CaptureWorker,FORMAT_OPTIONS,SAMPLE_RATES
    from task_staging import make_midi_tracks,TaskStorage
    from mezclador import filter_for_mix
    from project_flow import create_named_project,repeat_project
    from main import MonitorWindow
    def timeline(track,types):
        t=0;out=[]
        for msg in track:
            t+=msg.time
            if msg.type in types:out.append((t,msg.type,getattr(msg,"tempo",getattr(msg,"note",None))))
        return out
    p=Path(location)
    m=mido.MidiFile(type=1,ticks_per_beat=960)
    conductor=mido.MidiTrack()
    conductor.append(mido.MetaMessage("text",text="Desplazamiento",time=240))
    conductor.append(mido.MetaMessage("set_tempo",tempo=900000,time=720))
    piano=mido.MidiTrack()
    piano.append(mido.MetaMessage("track_name",name="Piano",time=0))
    piano.append(mido.Message("note_on",note=60,velocity=90,time=0))
    piano.append(mido.Message("note_off",note=60,velocity=0,time=1920))
    m.tracks=[conductor,piano]
    midi_file=p/"fuente.mid";m.save(midi_file)
    exported=make_midi_tracks(midi_file,p/"exportados")
    result=mido.MidiFile(exported[0][0])
    assert timeline(result.tracks[0],{"set_tempo"})==timeline(conductor,{"set_tempo"})
    assert timeline(result.tracks[1],{"note_on","note_off"})==timeline(piano,{"note_on","note_off"})
    print("PASS MIDI tempo, canal y nota")
    mix=filter_for_mix([{"solo":False,"mute":False,"volume":100},{"solo":True,"mute":False,"volume":90}])
    assert "[1:a]" in mix and "[0:a]" not in mix
    print("PASS mezcla Solo/Mute")
    samples=np.array([.3,-.2,.4,-.4],dtype="<f4")
    controlled=np.frombuffer(CaptureWorker.apply_input_controls(samples.tobytes(),0,100),dtype="<f4")
    assert np.allclose(controlled,[0,-.2,0,-.4])
    print("PASS balance de captura")
    app=QApplication([])
    main=MonitorWindow()
    assert create_named_project(main,"Validacion QA",str(p/"proyectos"),next(iter(FORMAT_OPTIONS)),SAMPLE_RATES[0])
    project=Path(main.project_dir)
    from project_layout import DIRECTORIES
    assert {p.name for p in project.iterdir() if p.is_dir()}==set(DIRECTORIES)
    # Compatibilidad con proyectos antiguos que sí tenían carpetas extras;
    # su eliminación no debe realizarse al repetir un proyecto.
    for name in ("grabaciones","temporales","separaciones","midi","bateria","voces","backup"):
        (project/name).mkdir(exist_ok=True)
        (project/name/"sentinela.txt").write_text(name)
    assert repeat_project(main,confirm=False)
    assert all((project/name/"sentinela.txt").exists() for name in ("separaciones","midi","bateria","voces","backup"))
    assert all(not (project/name/"sentinela.txt").exists() for name in ("grabaciones","temporales"))
    print("PASS repetición segura de proyecto")
    store=main.workbench.midi_storage
    run=store.next_midi_run()
    f=run/"fuente.mid";f.write_bytes(midi_file.read_bytes())
    store.set_midi(f)
    saved=store.save(project/"backup"/"midi",all_files=True)
    assert saved
    assert TaskStorage("midi",main.project_id,project).composite==f
    # Aunque se indique una carpeta arbitraria interna, reutilizar la
    # carpeta canónica MIDI, sin construir «fuera_backup».
    copied=store.save(project/"fuera_backup",all_files=True)
    assert copied and all(x.parent==project/"audio_a_midi" for x in copied)
    assert not (project/"fuera_backup").exists()
    store.discard()
    assert all(x.exists() for x in saved)
    print("PASS restauración, guardado y descarte sin pérdida")
    print("REGRESIONES_OK",flush=True)
