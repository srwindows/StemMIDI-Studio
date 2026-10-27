#!/usr/bin/env python3
"""Prueba: cada preset de cada módulo se escribe y se recupera de disco."""
from pathlib import Path
import tempfile,os,sys,json,wave
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_presets_integrales_") as d:
    os.environ["STEMMIDI_WORKSPACE"]=d
    sys.path.insert(0,"/media/javi/Recuperacion/Monitor_de_Grabacion")
    from PySide6.QtWidgets import QApplication
    from ux_controls import PresetStrip,PRESET_DIR
    from main import MonitorWindow
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    from project_flow import create_named_project
    from PySide6.QtWidgets import QMessageBox
    app=QApplication([])
    win=MonitorWindow()
    assert create_named_project(win,"PruebaPresets",str(Path(d)/"projects"),
                                next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
    wave_path=Path(d)/"external.wav"
    with wave.open(str(wave_path),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(22050)
        f.writeframes(bytes(22050*2))
    win.workbench.show_mixer([wave_path])
    strips=[(s.kind,s) for s in win.findChildren(PresetStrip)]
    print("BANCOS_DE_PRESETS",[name for name,_ in strips],flush=True)
    assert len(strips)==len(set(name for name,_ in strips)),strips
    must={"monitor_grabacion","separar_audio","audio_a_midi","mezclador",
          "piano_roll_vista","drum_mixer","drum_editor","drum_pattern","bateria_completa",
          "vocal_eq_fx","vocal_spatial","vocal_completo"}
    assert must.issubset({x for x,_ in strips}),must-{x for x,_ in strips}
    for name,strip in strips:
        key="Auditoria_Config_"+name
        original=strip.snapshot()
        assert isinstance(original,dict),(name,type(original))
        strip.name.setText(key)
        strip.save_custom()
        stored=strip._read()
        assert key in stored,(name,stored)
        assert stored[key]==original,(name,stored[key],original)
        assert (PRESET_DIR/(name+".json")).is_file()
        other=list(strip.builtins.values())[0] if strip.builtins else {}
        if isinstance(other,dict):
            strip.apply(other)
        strip.refresh(select=None)
        idx=next((j for j in range(strip.choices.count()) if strip.choices.itemData(j)==("propio",key)),-1)
        assert idx>0,(name,idx)
        strip.choices.setCurrentIndex(0)
        strip.choices.setCurrentIndex(idx)
        recovered=strip.snapshot()
        assert recovered==original,(name,"expected",original,"actual",recovered)
        # Simular apertura de otra instancia del selector sin reutilizar
        # el widget anterior: lee el JSON persistente de disco.
        other_strip=PresetStrip(name,strip.builtins,strip.snapshot,strip.apply)
        new_index=next((j for j in range(other_strip.choices.count())
                        if other_strip.choices.itemData(j)==("propio",key)),-1)
        assert new_index>0,(name,"preset no persiste en otra instancia")
        other_strip.choices.setCurrentIndex(new_index)
        assert strip.snapshot()==original,(name,"no aplica desde otra instancia")
        print("PRESET_SAVED_RELOADED_APPLIED",name,len(original),flush=True)
    print("ALL_PRESET_MODULES_PASS",flush=True)
