"""Regresión: pestañas profesionales y flotantes comparten controles reales."""
from pathlib import Path
import os,sys,tempfile
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from main import MonitorWindow
from project_flow import create_named_project
import project_exit_guard
project_exit_guard.ask_exit_choice=lambda _:"discard"

def pump():
    for _ in range(18): app.processEvents()

with tempfile.TemporaryDirectory(prefix="stemmidi_shared_pro_") as temp:
    app=QApplication([])
    w=MonitorWindow();w.resize(1700,990);w.show()
    assert create_named_project(w,"Pestañas PRO",Path(temp)/"project",
                                w.format.currentText(),44100)
    pump()
    home=w.studio_home
    manager=home._floating_manager
    midi_card=home.info_card
    midi_float=manager.other_expanders[midi_card]
    midi_tab=w.midi_audio_tab
    midi_bridge=w.midi_audio_professional
    assert midi_bridge.view is midi_float.info_expanded
    assert midi_bridge.view is home.midi_to_audio.expanded_view
    assert midi_bridge.view.parentWidget() is midi_bridge.content
    assert w.tabs.indexOf(midi_tab)>=0
    assert w.tabs.indexOf(midi_tab)==w.tabs.indexOf(w.workbench.midi_tab)+1
    assert "MIDI a audio" in w.tabs.tabText(w.tabs.indexOf(midi_tab))
    print("MIDI_TAB_USES_UNIQUE_EXISTING_ENGINE_AND_EDITOR_PASS",flush=True)
    assert not midi_bridge._in_float
    view=midi_bridge.view
    index_before=view.format.currentIndex()
    index_after=(index_before+1)%view.format.count()
    view.format.setCurrentIndex(index_after)
    assert home.midi_to_audio.format.currentIndex()==index_after
    w.tabs.setCurrentWidget(midi_tab)
    pump()
    assert w.grab().save("/tmp/stemmidi_pestana_midi_audio_pro_20261104.png")
    manager.detach(midi_card);pump()
    assert midi_bridge._in_float
    assert view.parentWidget() is midi_float.extra
    assert midi_bridge.placeholder.isVisible()
    assert view.format.currentIndex()==index_after
    assert view is home.midi_to_audio.expanded_view
    manager.redock(midi_card);pump()
    assert not midi_bridge._in_float
    assert view.parentWidget() is midi_bridge.content
    assert view.format.currentIndex()==index_after
    assert home.midi_to_audio.format.currentIndex()==index_after
    print("MIDI_TAB_FLOAT_TAB_SAME_WIDGET_VALUES_AND_NO_DUPLICATION_PASS",flush=True)

    mixer_card=home.mix_card
    mixer_exp=manager.other_expanders[mixer_card]
    mixer_bridge=w.mixer_professional
    mixer=mixer_bridge.view
    assert mixer is mixer_exp.project_mixer
    assert mixer_bridge.transport is mixer.transport
    assert w.tabs.indexOf(w.mixer_placeholder)>=0
    w.tabs.setCurrentWidget(w.mixer_placeholder);pump()
    assert w.grab().save("/tmp/stemmidi_pestana_mezclador_pro_20261104.png")
    assert mixer.parentWidget() is mixer_bridge.content
    manager.detach(mixer_card);pump()
    assert mixer_bridge._in_float
    assert mixer.parentWidget() is mixer_exp.extra
    strip=manager.windows[mixer_card].float_transport
    assert mixer.transport is strip.project_mixer_strip
    assert not mixer_bridge.transport.timer.isActive()
    manager.redock(mixer_card);pump()
    assert mixer.parentWidget() is mixer_bridge.content
    assert mixer.transport is mixer_bridge.transport
    assert mixer_bridge.transport.timer.isActive()
    assert not mixer_bridge._in_float
    print("MIXER_TAB_FLOAT_TAB_ONE_VIEW_ONE_ACTIVE_TRANSPORT_PASS",flush=True)

    # La navegación desde Inicio va directamente a la pestaña con su
    # editor avanzado, no a la pestaña de otro módulo.
    w.tabs.setCurrentWidget(home)
    home.info_card.header.click()
    pump()
    assert w.tabs.currentWidget() is midi_tab
    print("HOME_MIDI_AUDIO_NAVIGATION_GOES_TO_PROFESSIONAL_TAB_PASS",flush=True)
    w.hide()
print("PROFESSIONAL_TABS_SHARED_ALL_PASS",flush=True)
