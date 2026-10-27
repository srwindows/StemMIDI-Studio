#!/usr/bin/env python3
"""Prueba de ayuda contextual real sobre los 9 módulos y controles nuevos."""
import os,sys,tempfile,wave
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_hover_help_test_") as d:
    os.environ["STEMMIDI_WORKSPACE"]=d
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QPoint,Qt,QEvent
    from PySide6.QtGui import QHelpEvent,QMouseEvent
    from PySide6.QtWidgets import (
        QApplication,QWidget,QAbstractButton,QComboBox,QAbstractSlider,
        QAbstractSpinBox,QLineEdit,QScrollBar,QTabWidget,QToolTip,QPushButton
    )
    from main import MonitorWindow
    app=QApplication([])
    w=MonitorWindow()
    w.resize(1350,900)
    w.show()
    def events():
        for _ in range(6):app.processEvents()
    events()
    manager=w._context_help
    assert manager.root is w
    assert len(w.tabs.findChildren(QTabWidget))>=1
    assert w.tabs.count()==9
    def interactive():
        return [x for x in w.findChildren(QWidget)
                if isinstance(x,(QAbstractButton,QComboBox,QAbstractSlider,
                                 QAbstractSpinBox,QLineEdit))
                and not isinstance(x,QScrollBar)
                and x.objectName() not in ("qt_spinbox_lineedit",)]
    visible=interactive()
    assert len(visible)>650,len(visible)
    missing=[(type(x).__name__,x.objectName(),x.text()
            if isinstance(x,QAbstractButton) else "")
             for x in visible if not x.toolTip().strip()]
    assert not missing,(len(missing),missing[:20])
    print("WIDGETS_CON_DESCRIPCION",len(visible),flush=True)
    def contains(obj,term):
        text=obj.toolTip().casefold()
        assert term in text,(type(obj).__name__,text,term)
    vocal=w.vocal_module
    for obj,needle in [
        (vocal.warmth.slider,"cálida"),
        (vocal.warmth.spin,"cálida"),
        (vocal.compression.slider,"dinámicas"),
        (vocal.delay_ms.spin,"tiempo de eco"),
        (vocal.start_button,"archivo nuevo"),
        (w.workbench.converter.bpm.slider,"pulsaciones"),
        (w.workbench.piano.zoom_digit,"píxeles por negra"),
        (w.workbench.piano.note_pitch,"altura midi"),
        (w.workbench.separator.profile,"separación"),
    ]:
        contains(obj,needle)
    print("CONTROLES_DSP_MIDI_Y_SEPARACION_EXPLICADOS",flush=True)
    for i in range(w.tabs.count()):
        assert w.tabs.tabToolTip(i),("Sin explicación de pestaña",i)
    for panel in (vocal.studio_tabs,w.workbench.converter.form_tabs):
        for i in range(panel.count()):
            assert panel.tabToolTip(i),("Sin explicación de subpestaña",i)
    print("PAGINAS_Y_SUBPAGINAS_EXPLICADAS",flush=True)

    target=vocal.start_button
    w.tabs.setCurrentWidget(vocal)
    events()
    assert target.isVisible()
    pos=target.rect().center()
    global_pos=target.mapToGlobal(pos)
    def appear():
        event=QHelpEvent(QEvent.ToolTip,pos,global_pos)
        QApplication.sendEvent(target,event)
        events()
        assert QToolTip.isVisible(),"No apareció la explicación"
        assert "archivo nuevo" in QToolTip.text().casefold()
    def mouse(kind,button,buttons):
        event=QMouseEvent(kind,pos,global_pos,button,buttons,Qt.NoModifier)
        QApplication.sendEvent(target,event)
        events()
        assert not QToolTip.isVisible(),("El globo continúa visible",kind)
    appear()
    mouse(QEvent.MouseMove,Qt.NoButton,Qt.NoButton)
    appear()
    mouse(QEvent.MouseButtonPress,Qt.LeftButton,Qt.LeftButton)
    # No se envía MouseButtonRelease; no ejecuta un procesamiento.
    appear()
    QApplication.sendEvent(target,QEvent(QEvent.Leave))
    events()
    assert not QToolTip.isVisible(),"No desapareció al abandonar el botón"
    print("TOOLTIP_HOVER_MOVE_CLICK_LEAVE_OK",flush=True)

    source=Path(d)/"stem_test.wav"
    with wave.open(str(source),"wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0"*(16000*2))
    # Mezclador multipista creado después del gestor; antes no existía.
    w.workbench.show_mixer([source])
    events()
    manager.populate()  # Simula también el siguiente ciclo automático.
    after=interactive()
    assert len(after)>len(visible),(len(visible),len(after))
    missing=[(type(x).__name__,x.objectName()) for x in after
             if not x.toolTip().strip()]
    assert not missing,(len(missing),missing[:20])
    print("MEZCLADOR_DINAMICO_CUBIERTO",len(after),flush=True)
    # Widgets añadidos con la ventana ya abierta no deben quedar sin ayuda.
    new=QPushButton("Actualizar pistas",w.results_tab)
    w.tabs.setCurrentWidget(w.results_tab)
    new.show()
    events()
    assert new.toolTip(), "Falta ayuda en botón añadido dinámicamente"
    print("CONTROLES_NUEVOS_CUBIERTOS",new.toolTip(),flush=True)
    w.close()
print("TODOS_LOS_TOOLTIPS_Y_EVENTOS_OK",flush=True)
