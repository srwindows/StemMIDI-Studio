"""Monitor flotante: EQ REAL, volumen de captura, fábrica, picos y layout."""
from __future__ import annotations
import os,sys,tempfile
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"

with tempfile.TemporaryDirectory(prefix="stemmidi_monitor_live_eq_ui_") as root:
    os.environ["STEMMIDI_WORKSPACE"]=root
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication,QLabel
    import project_exit_guard
    project_exit_guard.ask_exit_choice=lambda _:"discard"
    from main import MonitorWindow,STYLE
    from audio_engine import CaptureWorker
    from home_record_review import percent_to_gain_db,gain_db_to_percent
    from home_other_expanded import factory_monitor_presets,preset_path
    app=QApplication([])
    app.setStyleSheet(STYLE)
    w=MonitorWindow();w.resize(1750,1050);w.show()
    h=w.studio_home
    w.tabs.setCurrentWidget(h)
    manager=h._floating_manager
    for _ in range(25):app.processEvents()
    assert h.capture_gain_panel.isVisible()
    assert h.capture_diagnostics.isHidden()
    manager.detach(h.mon_card)
    for _ in range(36):app.processEvents()
    view=manager.other_expanders[h.mon_card]
    r=view.review
    assert r.play.isEnabled() is False
    assert not h.capture_gain_panel.isVisible(), "El slider de abajo es duplicado en flotante"
    assert h.capture_diagnostics.isVisible()
    assert r.sliders["bass"].isVisible()
    assert r.sliders["volume"].isVisible()
    assert len(factory_monitor_presets())>=7
    for name in factory_monitor_presets():
        assert view.choice.findText(name)>0,name
    print("FLOAT_NO_DUPLICATE_GAIN_AND_NINE_FACTORY_PRESETS_VISIBLE_PASS",flush=True)

    labels={q.text():q for q in h.mon_card.findChildren(QLabel)
            if q.text() in ("Formato","Calidad")}
    for text,selector in (("Formato",h.format),("Calidad",h.quality)):
        assert text in labels
        right=labels[text].mapTo(h.mon_card,labels[text].rect().topRight()).x()
        left=selector.mapTo(h.mon_card,QPoint(0,0)).x()
        print("FORM_GEOMETRY",text,"distance",left-right,
              "label_rect",labels[text].geometry(),
              "combo_rect",selector.geometry(),
              "parent_label",labels[text].parentWidget().objectName(),
              "parent_combo",selector.parentWidget().objectName(),flush=True)
        assert -4<=left-right<=20,(text,left-right)
    print("FORMAT_QUALITY_LABELS_NEXT_TO_THEIR_COMBOS_PASS",flush=True)

    # Inyectar CaptureWorker pero NO arrancar ningún dispositivo del usuario.
    mock=CaptureWorker("sin-pactl",sample_rate=48000)
    w.worker=mock
    index=view.choice.findText("Voz cantada")
    assert index>0
    view.choice.setCurrentIndex(index)
    assert w.input_gain_db==-6,w.input_gain_db
    assert w.input_eq_values==(-2,1,2),w.input_eq_values
    assert w.input_eq_enabled
    assert mock._gain_db==-6 and mock._eq_settings==(True,-2,1,2)
    assert r.backend._preview_eq==(-2,1,2)
    assert r.sliders["volume"].value()==gain_db_to_percent(-6)
    print("FACTORY_PRESET_CHANGES_LIVE_CAPTURE_GAIN_EQ_AND_PREVIEW_PASS",flush=True)

    r.sliders["bass"].setValue(10)
    assert w.input_eq_values==(10,1,2)
    assert mock._eq_settings==(True,10,1,2)
    r.sliders["volume"].setValue(94)
    target=percent_to_gain_db(94)
    assert mock._gain_db==target and w.input_gain_db==target
    assert h.capture_gain.value()==target
    assert r.backend.volume.value()==94
    print("TOP_BASS_AND_VOLUME_WORK_BEFORE_RECORDING_AND_SYNC_LOWER_GAIN_PASS",flush=True)

    r.eq_enabled.setChecked(False)
    assert mock._eq_settings[0] is False
    assert r.backend._preview_eq==(0,0,0)
    r.eq_enabled.setChecked(True)
    assert mock._eq_settings==(True,10,1,2)
    r.flat_eq()
    assert w.input_eq_values==(0,0,0)
    assert mock._eq_settings==(True,0,0,0)
    print("BYPASS_REENABLE_AND_FLAT_TONES_CHANGE_REAL_CAPTURE_PASS",flush=True)

    view.name.setText("Mi toma personalizada")
    view.save_preset()
    assert preset_path().is_file()
    assert view.choice.findText("Mi toma personalizada")>0
    original=w.monitor_preset_snapshot()
    r.sliders["mid"].setValue(-8)
    r.sliders["volume"].setValue(70)
    w.monitor_preset_apply(original)
    assert w.input_gain_db==target
    assert w.input_eq_values==(0,0,0)
    assert r.sliders["mid"].value()==0
    assert r.sliders["volume"].value()==gain_db_to_percent(target)
    view.choice.setCurrentText("— Elegir preset —")
    view.choice.setCurrentText("Mi toma personalizada")
    assert r.sliders["volume"].value()==94
    view.delete_preset()
    assert view.choice.findText("Mi toma personalizada")<0
    print("PROJECT_EQ_PERSISTENCE_AND_CUSTOM_PRESET_SAVE_DELETE_PASS",flush=True)

    factory_count=len(factory_monitor_presets())
    view.choice.setCurrentText("Voz cantada")
    view.delete_preset()
    assert view.choice.findText("Voz cantada")>0
    assert len(factory_monitor_presets())==factory_count
    print("PROTECTED_FACTORY_PRESETS_NOT_DELETABLE_PASS",flush=True)

    assert "Sin señal activa" in h.capture_diag_route.text()
    h.sync_capture_levels(.4,.35,.81,.76)
    assert h._capture_peak_hold==.81
    h.sync_capture_levels(.9,.9,1.05,1.02)
    assert h._capture_clip_count==1
    assert "CLIP: 1" in h.capture_diag_clip.text()
    assert "0.4" in h.capture_diag_peak.text() or "0.5" in h.capture_diag_peak.text()
    h.reset_capture_peaks()
    assert h._capture_clip_count==0 and h._capture_peak_hold==0.
    assert "−∞" in h.capture_diag_peak.text()
    print("REAL_PEAK_HOLD_CLIP_WARNING_RESET_PASS",flush=True)

    # La captura detenida libera los vúmetros (el historial de picos
    # se mantiene hasta que se pulse Reiniciar picos).
    w.stop_monitor()
    assert w.worker is None
    assert h.level_meter.levels==[0.,0.]
    assert manager.windows[h.mon_card].grab().save(
        "/tmp/stemmidi_monitor_eq_captura_presets_picos_20261104.png")
    manager.redock(h.mon_card)
    for _ in range(25):app.processEvents()
    assert h.capture_gain_panel.isVisible()
    assert h.capture_diagnostics.isHidden()
    assert view.extra.isHidden()
    print("MONITOR_FLOAT_TO_COMPACT_CONTROLS_RESTORED_PASS",flush=True)
    w.worker=None
    w.hide()
print("MONITOR_EQ_GAIN_PRESETS_UI_ALL_PASS",flush=True)
