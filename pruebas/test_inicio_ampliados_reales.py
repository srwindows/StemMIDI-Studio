#!/usr/bin/env python3
"""QA funcional de 11 módulos ampliados: presets, controles y retorno."""
import os,sys,tempfile,struct,wave
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="studio_float_all_") as temp:
 os.environ["STEMMIDI_WORKSPACE"]=temp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication,QMessageBox,QTableWidgetItem,QFileDialog
 from PySide6.QtCore import Qt
 from main import MonitorWindow,STYLE
 from home_other_expanded import preset_path
 app=QApplication([]);app.setStyleSheet(STYLE)
 w=MonitorWindow();w.resize(1920,1008);w.show()
 home=w.studio_home
 w.tabs.setCurrentWidget(home)
 for _ in range(40):app.processEvents()
 manager=home._floating_manager
 assert len(manager.other_expanders)==11
 presets=("monitor","midi","tracks","mixer","piano","vocal")
 changes={
    "monitor":("ganancia",home.capture_gain,5,-2),
    "midi":("onset",home.midi_sliders["onset"],.77,.45),
    "tracks":("nivel_Voces",home.track_rows["Voces"]["gain"],68,120),
    "mixer":("fader_Voces",home.mixer_rows["Voces"]["fader"],75,105),
    "piano":("velocidad",home.note_velocity,105,50),
    "vocal":("intensidad",home.vocal_strength,66,90)
 }
 for card,view in manager.other_expanders.items():
    original_parent=card.parentWidget()
    original_min=card.minimumSize()
    card.lock_button.click()
    for _ in range(22):app.processEvents()
    assert manager.is_detached(card),view.kind
    assert view.extra.isVisible(),view.kind
    assert card.isVisible(),view.kind
    assert len(view.proxies)>0 or view.kind in ("monitor","results","drums","drum_stems","info"),view.kind
    assert manager.windows[card].windowFlags() & Qt.FramelessWindowHint
    assert manager.windows[card].windowFlags() & Qt.WindowStaysOnTopHint
    if view.kind in presets:
        prop,source,value,other=changes[view.kind]
        assert prop in view.actual, (prop,view.actual)
        source.setValue(value)
        view.refresh()
        view.name.setText("Mi preset")
        view.save_preset()
        assert preset_path().is_file()
        assert view.choice.findText("Mi preset")>0
        source.setValue(other)
        view.choice.setCurrentText("— Elegir preset —")
        view.choice.setCurrentText("Mi preset")
        assert abs(source.value()-value)<.015,(view.kind,source.value(),value)
        view.delete_preset()
        assert view.choice.findText("Mi preset")<0
    if view.kind=="results":
        home.files.setRowCount(2)
        for i,(name,typ) in enumerate((("prueba.wav","Audio"),("prueba.mid","MIDI"))):
            home.files.setItem(i,0,QTableWidgetItem(name))
            home.files.setItem(i,1,QTableWidgetItem(typ))
        view.result_type.setCurrentText("MIDI")
        view.search.setText("prueba")
        view.filter_results()
        assert home.files.isRowHidden(0) and not home.files.isRowHidden(1)
        view.search.clear();view.result_type.setCurrentText("Todos")
        assert not home.files.isRowHidden(0)
    if view.kind=="drum_stems":
        folder=Path(temp)/"temp_parts";folder.mkdir()
        dest=Path(temp)/"destination";dest.mkdir()
        rows=home.drum_stem_rows
        for name in ("Bombo","Caja"):
            p=folder/(name+".wav")
            p.write_bytes(b"test only")
            rows[name]["path"]=p
        view.selected_parts["Bombo"].setChecked(True)
        view.selected_parts["Caja"].setChecked(False)
        import file_dialogs
        get_orig=file_dialogs.get_existing_directory
        file_dialogs.get_existing_directory=lambda *a,**kw:str(dest)
        try:view.export_drum_parts()
        finally:file_dialogs.get_existing_directory=get_orig
        assert (dest/"Bombo.wav").exists() and not (dest/"Caja.wav").exists()
    if view.kind=="info":
        view.copy_info()
        assert QApplication.clipboard().text()=="\n".join(
            x.text() for x in (home.note_info,home.duration_info,home.tempo_info,home.key_info))
    if view.kind=="drums":
        assert view.home._drum_module is not None
    if view.kind=="wave":
        assert view.proxies[0][0] is home.wave_zoom
    # Screenshot for manual geometry inspection, no screenshot files in project.
    if view.kind in ("monitor","midi","tracks","mixer"):
        for _ in range(25):app.processEvents()
        manager.windows[card].grab().save(str(Path(temp)/(view.kind+"_expanded.png")))
    card.lock_button.click()
    for _ in range(18):app.processEvents()
    assert not manager.is_detached(card)
    assert not view.extra.isVisible()
    assert card.minimumSize()==original_min
    assert card.isVisible()
    assert w.tabs.currentWidget() is home,view.kind
    print("PASSED",view.kind,flush=True)
 assert len(manager.windows)==0
 print("ELEVEN_MODULES_PRESET_MONITOR_MIDI_TRACKS_MIXER_PIANO_VOCAL_FILTER_EXPORT_INFO_PASS")
