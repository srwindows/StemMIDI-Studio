#!/usr/bin/env python3
"""Los 2 presets aprobados son de serie, exactos y Preciso es el predeterminado."""
from pathlib import Path
import os,sys,json,tempfile
os.environ["QT_QPA_PLATFORM"]="offscreen"
SOURCE=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="stemmidi_midi_serie_") as folder:
    os.environ["STEMMIDI_WORKSPACE"]=folder
    sys.path.insert(0,str(SOURCE))
    from PySide6.QtWidgets import QApplication
    from main import MonitorWindow
    from project_flow import create_named_project
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    from midi_factory_presets import USER_APPROVED_MIDI_PRESETS,DEFAULT_MIDI_PRESET
    from ux_controls import PRESET_DIR
    import midi_dialog
    app=QApplication([])
    before=SOURCE/"presets_usuario/audio_a_midi.json"
    if before.is_file():
        customs=json.loads(before.read_text(encoding="utf-8"))
        if "mio" in customs:assert customs["mio"]==USER_APPROVED_MIDI_PRESETS["Preciso"]
        if "mio_2" in customs:assert customs["mio_2"]==USER_APPROVED_MIDI_PRESETS["Más suave"]
    # Simular un arranque previo que dejó preferido otro perfil.
    old_pref=Path(folder)/"preferencias_midi.json"
    old_pref.write_text(json.dumps({"bpm":93,"frame":.77,"detect_chords":False,
                                   "precision_profile":"sensitive"}))
    assert midi_dialog.PREFERENCES==old_pref
    m=MonitorWindow()
    c=m.workbench.converter
    choices=c.presets.choices
    def selected():
        return choices.currentData()
    def assert_profile(label):
        assert selected()==("base",label),(selected(),label)
        assert c.parameter_snapshot()==USER_APPROVED_MIDI_PRESETS[label],(
            label,c.parameter_snapshot(),USER_APPROVED_MIDI_PRESETS[label])
        for control in ("bpm","frame","merge_gap","low","high"):
            assert getattr(c,control).isEnabled() or c.tempo_auto.isChecked()
        print("PARAMETROS_EXACTOS",label,len(c.parameter_snapshot()),flush=True)
    assert DEFAULT_MIDI_PRESET=="Preciso"
    assert_profile("Preciso")
    assert list(c.presets.builtins)[:2]==["Preciso","Más suave"]
    def find(combo,key):
        return next((i for i in range(combo.count()) if combo.itemData(i)==key),-1)
    assert all(find(choices,("base",key))>=0 for key in ("Preciso","Más suave"))
    assert all(choices.itemText(find(choices,("base",key))).startswith("●")
               for key in ("Preciso","Más suave"))
    print("ARRANQUE_NORMAL_PRECISO_PRESELECCIONADO",flush=True)
    c.select_factory_preset("Más suave")
    assert_profile("Más suave")
    base=Path(folder)/"proyectos"
    fmt=next(iter(FORMAT_OPTIONS));rate=next(iter(SAMPLE_RATES))
    assert create_named_project(m,"PrimerEstudio",str(base),fmt,rate)
    assert_profile("Preciso")
    assert str(Path(m.project_dir)/"audio_a_midi")==c.outdir.text()
    print("NUEVO_PROYECTO_A_PRECISO_Y_RUTA_CORRECTA",flush=True)
    c.select_factory_preset("Más suave")
    assert_profile("Más suave")
    assert create_named_project(m,"SegundoEstudio",str(base),fmt,rate)
    assert_profile("Preciso")
    assert str(Path(m.project_dir)/"audio_a_midi")==c.outdir.text()
    print("NUEVO_PROYECTO_B_RESTAURA_PRECISO",flush=True)
    home=m.studio_home
    home.refresh(force=True)
    assert home.midi_preset.currentData()==("base","Preciso"),home.midi_preset.currentData()
    softer=find(home.midi_preset,("base","Más suave"))
    assert softer>=0
    home.midi_preset.setCurrentIndex(softer)
    assert_profile("Más suave")
    print("INICIO_Y_MODULO_AUDIO_MIDI_SINCRONIZADOS",flush=True)
    assert not (PRESET_DIR/"audio_a_midi.json").exists()
    print("PRUEBAS_AISLADAS_SIN_TOCARE_PRESETS_REALES",flush=True)
print("DOS_PRESETS_FABRICA_MIDI_COMPLETO_OK",flush=True)
