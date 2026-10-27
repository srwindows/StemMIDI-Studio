#!/usr/bin/env python3
"""Control global ayuda profesional: LED, direcciones, persistencia, 9 módulos."""
import os,sys,tempfile,json,wave
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_professional_help_test_") as base:
    os.environ["STEMMIDI_WORKSPACE"]=base
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from PySide6.QtCore import Qt,QEvent,QPoint
    from PySide6.QtGui import QHelpEvent,QMouseEvent
    from PySide6.QtWidgets import (QApplication,QWidget,QAbstractButton,QToolTip,
        QComboBox,QAbstractSlider,QAbstractSpinBox,QCheckBox,QLineEdit,QTabBar)
    from studio_shell import StudioHeader,ProfessionalHelpButton
    from main import MonitorWindow,PREFS
    app=QApplication([])
    first=MonitorWindow()
    first.resize(1400,900)
    first.show()
    for i in range(6):app.processEvents()
    manager=first._context_help
    head=first.findChild(StudioHeader)
    button=head.findChild(ProfessionalHelpButton)
    assert button is head.help_toggle
    assert button.text()==""
    assert manager.enabled is True
    assert button.isChecked() is True
    assert first.tabs.count()==9
    actions=head.layout().itemAt(2).layout()
    surfaces=[actions.itemAt(i).widget() for i in range(actions.count())]
    open_index=next(i for i,w in enumerate(surfaces)
                    if w and w.objectName()=="studioToolbar")
    assert surfaces[open_index+1] is button,[
        (type(w).__name__,getattr(w,"toolTip",lambda:"")()[:40])
        for w in surfaces]
    print("BOTON_INMEDIATO_A_DERECHA_DE_ABRIR_PROYECTO_OK",flush=True)
    for width,height in ((1100,735),(1200,760),(1440,900),(1920,1030)):
        first.resize(width,height)
        for i in range(7):app.processEvents()
        candidates=head.toolbar_buttons[:1]+[button]+head.toolbar_buttons[1:]
        positions=[(w.mapTo(head,QPoint(0,0)).x(),
                    w.mapTo(head,QPoint(0,0)).x()+w.width()) for w in candidates]
        assert positions[0][0]>=0
        assert positions[-1][1]<=head.width(),(width,positions)
        assert all(positions[i][1]<=positions[i+1][0]
                   for i in range(len(positions)-1)),(width,positions)
    first.resize(1400,900)
    for i in range(7):app.processEvents()
    print("BOTONERA_SIN_SOLAPAMIENTOS_EN_4_TAMANOS_OK",flush=True)
    pic_on=button.grab().toImage()
    led_on=pic_on.pixelColor(71,19)
    assert led_on.green()>led_on.red() and led_on.green()>led_on.blue()
    vocal=first.vocal_module
    target=vocal.warmth.slider
    assert "cálida" in manager._tip(target)
    assert "Al mover hacia" in manager._tip(target)
    assert "Valor actual" in manager._tip(target)
    assert "Consejo:" in manager._tip(target)
    assert "graves" in manager._tip(vocal.highpass.slider).lower()
    assert "transición" in manager._tip(vocal.retune.slider).lower()
    check=vocal.learn_same_song
    assert "Si marcas:" in manager._tip(check)
    assert "Si desmarcas:" in manager._tip(check)
    assert "DESACTIVADA" in manager._tip(check)
    check.setChecked(True)
    assert "ACTIVADA" in manager._tip(check)
    selector=vocal.scale
    assert "Opción actual:" in manager._tip(selector)
    assert "Opciones disponibles:" in manager._tip(selector)
    assert "Al seleccionar" in manager._tip(first.tabs.tabBar(),
                                            first.tabs.tabBar().tabRect(0).center())
    print("GUI_CONSEJOS_DIRECCIONES_ESTADOS_PESTANAS_PROBADOS",flush=True)
    assert not button.toolTip().startswith("Ejecuta")
    first.tabs.setCurrentWidget(vocal)
    for i in range(5):app.processEvents()
    def tooltip_on(obj):
        pt=obj.rect().center()
        ev=QHelpEvent(QEvent.ToolTip,pt,obj.mapToGlobal(pt))
        QApplication.sendEvent(obj,ev)
        for i in range(3):app.processEvents()
        return QToolTip.isVisible(),QToolTip.text()
    showing,body=tooltip_on(target)
    assert showing and "Al mover" in body,(showing,body)
    button.click()
    assert not button.isChecked() and not manager.enabled
    assert not QToolTip.isVisible()
    led_off=button.grab().toImage().pixelColor(71,19)
    assert led_off.green()<led_on.green(),(led_on.name(),led_off.name())
    showing,body=tooltip_on(target)
    assert not showing,body
    assert manager._tip(target)==""
    # Nativo preexistente no puede burlar el OFF.
    showing,body=tooltip_on(vocal.start_button)
    assert not showing
    assert json.loads(PREFS.read_text())["professional_help_enabled"] is False
    first.save_config()
    assert json.loads(PREFS.read_text())["professional_help_enabled"] is False
    print("OFF_DESACTIVA_TODOS_LOS_TOOLTIP_Y_PERSISTE_CONFIG",flush=True)
    button.click()
    assert manager.enabled and button.isChecked()
    showing,body=tooltip_on(target)
    assert showing and "Al mover" in body
    print("ON_REACTIVA_TOOLTIP_Y_LED",flush=True)
    from PySide6.QtGui import QMouseEvent
    pt=target.rect().center()
    event=QMouseEvent(QEvent.MouseMove,pt,target.mapToGlobal(pt),
                      Qt.NoButton,Qt.NoButton,Qt.NoModifier)
    QApplication.sendEvent(target,event)
    for i in range(5):app.processEvents()
    assert not QToolTip.isVisible()
    print("MOVIMIENTO_OCULTA_AYUDA",flush=True)
    # Nuevo mezclador cargado después: hereda el interruptor.
    source=Path(base)/"stem.wav"
    with wave.open(str(source),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        f.writeframes(bytes(32000))
    first.workbench.show_mixer([source])
    manager.populate()
    assert "Al mover" in manager._tip(first.workbench.mixer.fader if hasattr(
        first.workbench.mixer,'fader') else vocal.warmth.slider)
    first.close()
    print("NUEVOS_CONTROLES_CON_AYUDA",flush=True)
print("GLOBAL_PROFESSIONAL_HELP_TEST_OK",flush=True)
