#!/usr/bin/env python3
"""Auditoría automatizada de accesibilidad geométrica, 9 módulos y subpestañas.

No crea proyectos permanentes ni modifica audio: todo bajo TemporaryDirectory.
Si se oculta un control por una altura fija o scroll imposible, falla.
"""
import os,sys,tempfile,wave
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_layout_") as folder:
 os.environ["STEMMIDI_WORKSPACE"]=folder
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtCore import QPoint,Qt
 from PySide6.QtWidgets import QApplication,QScrollArea,QSpinBox,QPushButton,QAbstractSlider
 from main import MonitorWindow
 app=QApplication([])
 main=MonitorWindow()
 stub=Path(folder)/"pista.wav"
 with wave.open(str(stub),"wb") as f:
    f.setnchannels(2);f.setsampwidth(2);f.setframerate(22050)
    f.writeframes(bytes(22050*4))
 tested=0
 def refresh():
    for _ in range(5):app.processEvents()
 def reveal(area,control,where):
    global tested
    assert isinstance(area,QScrollArea),(where,type(area))
    assert area.isVisible(),(where,"scroll container not visible")
    assert control.isVisibleTo(area),(where,"widget hidden",control)
    area.ensureWidgetVisible(control,22,16)
    refresh()
    p=control.mapTo(area.viewport(),QPoint(0,0))
    view=area.viewport().rect()
    rect=(p.x(),p.y(),control.width(),control.height())
    horizontal=p.x()<view.right() and (p.x()+control.width())>0
    vertical=p.y()<view.bottom() and (p.y()+control.height())>0
    assert horizontal and vertical,(where,rect,view,area.horizontalScrollBar().maximum(),area.verticalScrollBar().maximum())
    assert control.width()>=40 and control.height()>=(12 if isinstance(control,QAbstractSlider) else 16),(where,"control collapsed",rect)
    tested+=1
 for width,height in [(1100,735),(1200,760),(1440,900),(1920,1030)]:
    main.resize(width,height)
    main.show()
    refresh()
    tabs=main.tabs
    assert tabs.count()==9,tabs.count()
    assert tabs.tabBar().usesScrollButtons()
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i);refresh()
        assert tabs.widget(i).isVisible(),(width,height,i,tabs.tabText(i))
    # Separación se rediseñó SIN scroll general; comprobamos geometría
    # visible directamente, no el antiguo QScrollArea que ya no existe.
    from PySide6.QtCore import QCoreApplication,QEvent
    tabs.setCurrentWidget(main.workbench.separation_tab);refresh()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    sep=main.workbench.separator
    assert not sep.findChildren(QScrollArea),("Separación","scroll principal")
    for ctl in (sep.profile,sep.export_fmt,sep.quality,sep.file_edit,
                sep.import_button,sep.dest_edit,sep.go,sep.progress,
                sep.source_preview,sep.load_previous_button,
                sep.library_button,sep.midi_button,sep.mix_button):
        assert ctl.isVisibleTo(sep),("Separación oculta",ctl)
        p=ctl.mapTo(sep,QPoint(0,0))
        assert p.x()>=0 and p.y()>=0
        assert p.x()+ctl.width()<=sep.width()+2,(width,"Separación ancho",ctl.objectName())
        assert p.y()+ctl.height()<=sep.height()+2,(height,"Separación altura",ctl.objectName())
        tested+=1
    tabs.setCurrentWidget(main.workbench.midi_tab);refresh()
    m=main.workbench.converter
    for sub,controls in [
        (0,[m.audio_path,m.file_button]),
        (1,[m.bpm,m.onset,m.grid_offset,m.merge_gap,m.note_shift]),
        (2,[m.outdir,m.filename]),
    ]:
        m.form_tabs.setCurrentIndex(sub);refresh()
        area=m.form_tabs.widget(sub)
        assert isinstance(area,QScrollArea),("Audio MIDI",sub)
        assert area.viewport().height()>=160,(sub,area.viewport().height())
        for ctl in controls:reveal(area,ctl,f"MIDI pagina{sub}")
    tabs.setCurrentWidget(main.vocal_module);refresh()
    v=main.vocal_module
    for sub,controls in [
        (0,[v.retune,v.compression,v.highpass]),
        (1,[v.character,v.character_amount,v.bypass_tune]),
        (2,[v.warmth,v.air,v.wet,v.fx_presets]),
        (3,[v.doubler,v.delay_ms,v.output_gain_db,v.spatial_presets]),
        (4,[v.reference,v.ref_analyze]),
    ]:
        v.studio_tabs.setCurrentIndex(sub);refresh()
        area=v.studio_tabs.widget(sub)
        assert isinstance(area,QScrollArea),("Vocal",sub)
        assert area.viewport().height()>=160,("Vocal scroll not tall",sub,area.viewport().height())
        for ctl in controls:reveal(area,ctl,f"Vocal pagina{sub}")
    # La zona principal y todos los presets inferiores deben alcanzarse
    # incluso al final de la ventana pequeña.
    reveal(v.content_scroll,v.strength,"Corrección tonal vocal")
    reveal(v.content_scroll,v.full_presets,"Preset vocal completo")
    reveal(v.content_scroll,v.start_button,"Procesar voz")
    reveal(v.content_scroll,v.save_btn,"Guardar voz")
    tabs.setCurrentWidget(main.drum_module);refresh()
    drum=main.drum_module
    reveal(drum.studio.dashboard_scroll,drum.studio.dashboard_sections[4],
           "Bateria resultados")
    reveal(drum.studio.dashboard_scroll,drum.studio.dashboard_sections[2],
           "Bateria editor")
    reveal(drum.studio.dashboard_scroll,drum.studio.dashboard_sections[3],
           "Bateria secuenciador")
    tabs.setCurrentWidget(main.workbench.piano);refresh()
    piano=main.workbench.piano
    for ctl in (piano.note_pitch,piano.note_start,piano.note_duration,
                piano.note_apply,piano.zoom_digit,piano.zoom_vertical_digit,
                piano.tempo_bpm,piano.apply_button if hasattr(piano,'apply_button') else main.workbench.apply_button):
        reveal(piano.page_scroll,ctl,"Piano Roll")
    # El panel de nota nunca puede volver a reducirse a 13px.
    assert piano.note_pitch.parentWidget().height()>=32
    # Mezclador real, no solo la pantalla de instrucciones.
    if main.workbench.mixer is None:
        main.workbench.show_mixer([stub])
    tabs.setCurrentWidget(main.workbench.mixer);refresh()
    mixer=main.workbench.mixer
    for ctl in (mixer.output_fmt,mixer.export_button,mixer.offset):
        outer=next(a for a in mixer.findChildren(QScrollArea)
                   if a.parentWidget() is mixer)
        reveal(outer,ctl,"Mezclador")
    print("TAMANIO",width,height,"CONTROLES_VERIFICADOS_ACUMULADOS",tested,flush=True)
    # El proyecto no debe degradarse al variar tamaños repetidamente.
 assert tested>=120,tested
 print("GEOMETRIA_ACCESIBLE_9_MODULOS_OK",tested,flush=True)
