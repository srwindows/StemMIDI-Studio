"""Compositor: distribución de trabajo inspirada en convenciones DAW.

Implementación PySide6 ORIGINAL: NO importa código ni recursos de Qtractor.
Qtractor (GPL-2.0-or-later) solo se estudia como referencia histórica.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
 QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QPushButton,QComboBox,
 QSlider,QSpinBox,QLineEdit,QTableWidget,QHeaderView,QAbstractItemView,
 QSplitter,QMenuBar,QProgressBar,QTabWidget,QSizePolicy,QCheckBox,
 QToolButton)
from compositor_tab import ComposerTimeline,LEFT,TOP,ROW
from compositor_meters import LevelMeter

STYLE="""
QWidget#compositorMainTab {background:#111923;color:#d6e5ef;}
QWidget#composerWorkspace {background:#101b28;}
QFrame#composerResultsBrowser,QFrame#composerTrackDock,
QFrame#composerInspectorPanel,QFrame#composerToolbar {
    background:#172331;border:1px solid #354b60;border-radius:3px;}
QLabel {color:#dbe7f2;}
QLabel#composerHeading {
    color:#f2f6fa;font-weight:700;font-size:13px;}
QLabel#composerMuted {color:#a0b5c6;font-size:10px;}
QMenuBar#composerMenu {background:#162333;color:#e5f2fb;
    border-bottom:1px solid #37516b;min-height:27px;}
QMenuBar::item {padding:4px 13px;}
QMenuBar::item:selected {background:#284966;}
QMenu {background:#1a2939;color:#e6f2fc;border:1px solid #416481;}
QMenu::item:selected {background:#295a7f;}
QToolButton,QPushButton {background:#26394e;color:#e4edf7;
    border:1px solid #49647d;border-radius:3px;
    font-size:11px;padding:4px 7px;min-height:23px;}
QToolButton:hover,QPushButton:hover {background:#31658a;border-color:#4ab8ef;}
QPushButton:pressed {background:#1b486d;}
QPushButton:disabled {color:#758b9e;background:#172a3c;border-color:#334b5e;}
QPushButton#composerPrimary {background:#1877a9;border:1px solid #51c6ee;
    font-weight:700;color:white;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {
    background:#0d1e2e;color:#e6f3fa;border:1px solid #42617c;
    border-radius:3px;padding:2px 4px;min-height:22px;}
QListWidget#composerProjectFiles {
    background:#0b1825;color:#d9e8f4;
    border:1px solid #354b60;alternate-background-color:#162535;
    selection-background-color:#27587a;selection-color:white;
    outline:0;font-size:12px;}
QListWidget#composerProjectFiles::item {padding:5px 4px;min-height:21px;
    border-bottom:1px solid #16283a;}
QListWidget#composerProjectFiles::item:selected {color:#fff;}
QListWidget#composerProjectFiles::item:hover {background:#28415b;}
QTableWidget#composerTrackList {
    background:#101e2d;color:#e0edf7;border:1px solid #37546a;
    alternate-background-color:#1c2a3a;gridline-color:#33485b;
    selection-background-color:#2b5875;}
QTableWidget#composerTrackList::item {padding:5px;}
QHeaderView::section {
    background:#20384c;color:#cddfeb;font-weight:600;
    border:0;border-right:1px solid #344b5d;padding:3px;}
QGraphicsView#composerTimeline {
    background:#0b1623;border:1px solid #37546a;}
QSplitter::handle {background:#344e64;}
QSplitter::handle:hover {background:#58b8ed;}
QTabWidget#composerDetails::pane {border:1px solid #38536a;background:#152234;}
QTabWidget#composerDetails QTabBar::tab {
    background:#263748;color:#cddce8;padding:4px 14px;}
QTabWidget#composerDetails QTabBar::tab:selected {
    background:#346080;color:#fff;}
QProgressBar {background:#081927;color:#f5fcff;border:1px solid #4c6b82;
    border-radius:3px;min-height:12px;}
QProgressBar::chunk {background:#39b9de;}
"""


def build(c):
    from compositor_tab import ComposerFileList
    from PySide6.QtWidgets import QGraphicsScene
    c.setStyleSheet(STYLE)
    root=QVBoxLayout(c)
    root.setContentsMargins(5,4,5,4)
    root.setSpacing(4)

    # 1. Menú de sesión completo, en lugar de 11 botones truncados.
    menubar=QMenuBar(c)
    menubar.setObjectName("composerMenu")
    c.menu=menubar
    root.setMenuBar(menubar)
    menus={}
    for title in ("Archivo","Edición","Pistas","Clips","Transporte","Ver"):
        menus[title]=menubar.addMenu(title)

    def action(menu,title,callback,shortcut=None):
        a=menus[menu].addAction(title)
        a.triggered.connect(callback)
        if shortcut:a.setShortcut(shortcut)
        return a

    action("Archivo","Importar pistas MIDI/audio…",c.import_media,"Ctrl+I")
    action("Archivo","Guardar arreglo",c.save,"Ctrl+S")
    action("Archivo","Exportar mezcla WAV (24-bit)",lambda:c.start_render(False),"Ctrl+E")
    action("Edición","Deshacer",c.undo,"Ctrl+Z")
    action("Edición","Rehacer",c.redo,"Ctrl+Shift+Z")
    action("Edición","Copiar clip",c.copy_selected,"Ctrl+C")
    action("Edición","Pegar clip en la guía",c.paste_clip,"Ctrl+V")
    action("Edición","Duplicar clip",c.duplicate_selected,"Ctrl+D")
    action("Edición","Eliminar clip",c.delete_selected,"Delete")
    action("Pistas","Añadir pista MIDI vacía",lambda:c.create_empty_track("midi"))
    action("Pistas","Añadir pista de audio vacía",lambda:c.create_empty_track("audio"))
    action("Pistas","Importar archivos de Resultados",c.add_from_results)
    action("Pistas","Subir pista",lambda:c.move_track(-1))
    action("Pistas","Bajar pista",lambda:c.move_track(1))
    action("Pistas","Eliminar pista seleccionada",c.delete_track)
    action("Clips","Dividir en posición de guía",c.split_selected,"Ctrl+K")
    action("Clips","Abrir clip MIDI en Piano Roll",c.open_clip_midi)
    action("Transporte","Reproducir / Pausa",c.toggle_playback,"Space")
    action("Transporte","Detener",c.stop_play)
    action("Transporte","Ir al inicio",lambda:c.set_playhead(0))
    action("Ver","Mostrar/ocultar archivos",c.toggle_library)
    action("Ver","Mostrar/ocultar inspector",c.toggle_inspector)

    # 2. Cabecera legible y transporte principal.
    heading=QHBoxLayout()
    title=QLabel("COMPOSITOR  |  EDICIÓN MULTIPISTA")
    title.setObjectName("composerHeading")
    heading.addWidget(title)
    c.project_title=QLabel("Sin proyecto")
    c.project_title.setObjectName("composerMuted")
    heading.addWidget(c.project_title,1)
    heading.addWidget(QLabel("Tempo"))
    c.tempo=QSpinBox(c)
    c.tempo.setObjectName("composerBpm")
    c.tempo.setRange(35,300)
    c.tempo.setValue(120)
    c.tempo.setMaximumWidth(75)
    c.tempo.valueChanged.connect(c.change_bpm)
    c.tempo.setToolTip("Tempo de edición/colocación: no modifica el BPM ni"
                      " estira los archivos de audio originales.")
    heading.addWidget(c.tempo)
    heading.addWidget(QLabel("4/4"))
    c.position_label=QLabel("001.01.00")
    c.position_label.setStyleSheet(
        "background:#091925;border:1px solid #416582;color:#70e5b3;"
        "font-family:monospace;font-size:14px;font-weight:800;padding:4px 7px;")
    heading.addWidget(c.position_label)
    root.addLayout(heading)

    transport_panel=QFrame(c)
    transport_panel.setObjectName("composerToolbar")
    transport=QHBoxLayout(transport_panel)
    transport.setContentsMargins(6,3,6,3)
    transport.setSpacing(5)
    c.go_start=c._button("⏮",lambda:c.set_playhead(0),"Inicio de canción")
    transport.addWidget(c.go_start)
    c.listen_btn=c._button("▶ Escuchar",c.toggle_playback,
                            "Renderiza la mezcla y abre su reproducción")
    c.listen_btn.setObjectName("composerPrimary")
    transport.addWidget(c.listen_btn)
    transport.addWidget(c._button("■ Parar",c.stop_play))
    transport.addWidget(QLabel("MASTER L/R"))
    c.master_meter=LevelMeter(c,master=True)
    transport.addWidget(c.master_meter)
    transport.addWidget(c._button("↶",c.undo,"Deshacer"))
    transport.addWidget(c._button("↷",c.redo,"Rehacer"))
    transport.addWidget(c._button("✂ Cortar",c.split_selected,
                                  "Dividir clip en la guía"))
    transport.addWidget(c._button("⊕ Pista",lambda:c.create_empty_track("audio"),
                                  "Crear pista de audio vacía"))
    transport.addWidget(c._button("Importar",c.import_media))
    transport.addStretch()
    transport.addWidget(QLabel("Ajuste"))
    c.grid=QComboBox(c)
    c.grid.setObjectName("composerGridSnap")
    for name,step in (("Libre",0),("1/4",1.),
                      ("1/8",.5),("1/16",.25),("1/32",.125)):
        c.grid.addItem(name,step)
    c.grid.setCurrentIndex(3)
    transport.addWidget(c.grid)
    transport.addWidget(QLabel("Zoom"))
    c.zoom=QSlider(Qt.Horizontal)
    c.zoom.setRange(12,76)
    c.zoom.setValue(c.pixels_per_beat)
    c.zoom.setFixedWidth(90)
    c.zoom.valueChanged.connect(c.change_zoom)
    transport.addWidget(c.zoom)
    c.export_btn=c._button("Exportar WAV",lambda:c.start_render(False))
    transport.addWidget(c.export_btn)
    root.addWidget(transport_panel)

    # 3. Disposición de Qtractor: control de pistas a la izquierda,
    # gran arreglo central, archivos de proyecto a la derecha.
    c.vertical_split=QSplitter(Qt.Vertical,c)
    c.vertical_split.setObjectName("composerVerticalWorkspace")
    c.vertical_split.setChildrenCollapsible(False)
    c.vertical_split.setHandleWidth(6)
    horizontal=QSplitter(Qt.Horizontal,c)
    horizontal.setObjectName("composerThreePane")
    horizontal.setChildrenCollapsible(False)
    horizontal.setHandleWidth(7)

    trackdock=QFrame(c)
    trackdock.setObjectName("composerTrackDock")
    tracklay=QVBoxLayout(trackdock)
    tracklay.setContentsMargins(3,3,3,3)
    tracklay.setSpacing(2)
    tracks_label=QLabel("PISTAS  ·  CONTROLES")
    tracks_label.setObjectName("composerHeading")
    tracklay.addWidget(tracks_label)
    c.track_table=QTableWidget(0,6)
    c.track_table.setObjectName("composerTrackList")
    c.track_table.setHorizontalHeaderLabels(
        ["Pista","M","S","Vol","Pan","VU L/R"])
    c.track_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
    for col,width in ((1,24),(2,24),(3,52),(4,48),(5,64)):
        c.track_table.horizontalHeader().setSectionResizeMode(
            col,QHeaderView.Fixed)
        c.track_table.setColumnWidth(col,width)
    c.track_table.horizontalHeader().setFixedHeight(TOP)
    c.track_table.verticalHeader().setVisible(False)
    c.track_table.verticalHeader().setDefaultSectionSize(ROW)
    c.track_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    c.track_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    c.track_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    c.track_table.setAlternatingRowColors(True)
    c.track_table.setContextMenuPolicy(Qt.CustomContextMenu)
    c.track_table.customContextMenuRequested.connect(c._track_context_menu)
    c.track_table.itemSelectionChanged.connect(c._select_row_related_clip)
    c.track_table.cellDoubleClicked.connect(c.rename_track)
    tracklay.addWidget(c.track_table,1)
    horizontal.addWidget(trackdock)

    timeline_container=QFrame(c)
    timeline_container.setObjectName("composerTrackDock")
    tl=QVBoxLayout(timeline_container)
    tl.setContentsMargins(2,3,2,3)
    tl.setSpacing(2)
    name=QLabel("ARREGLO  ·  COMPASES / CLIPS MIDI Y AUDIO")
    name.setObjectName("composerHeading")
    tl.addWidget(name)
    c.timeline=ComposerTimeline(c)
    tl.addWidget(c.timeline,1)
    horizontal.addWidget(timeline_container)

    browser=QFrame(c)
    browser.setObjectName("composerResultsBrowser")
    c.browser=browser
    left=QVBoxLayout(browser)
    left.setContentsMargins(4,4,4,4)
    left.setSpacing(4)
    heading=QHBoxLayout()
    heading.addWidget(QLabel("ARCHIVOS · RESULTADOS"),1)
    heading.addWidget(c._button("↻",lambda:c.refresh_catalog(True)))
    left.addLayout(heading)
    c.filter=QLineEdit(c)
    c.filter.setPlaceholderText("Buscar pistas y stems…")
    c.filter.textChanged.connect(c.refresh_catalog)
    left.addWidget(c.filter)
    c.files=ComposerFileList(c)
    c.files.setObjectName("composerProjectFiles")
    c.files.setAlternatingRowColors(True)
    c.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
    c.files.itemDoubleClicked.connect(lambda _:c.add_from_results())
    left.addWidget(c.files,1)
    left.addWidget(c._button("+ Añadir a pistas",c.add_from_results))
    left.addWidget(c._button("Importar archivos…",c.import_media))
    files_hint=QLabel("Arrastra archivos hasta una pista de la línea de tiempo.")
    files_hint.setObjectName("composerMuted")
    files_hint.setWordWrap(True)
    left.addWidget(files_hint)
    horizontal.addWidget(browser)
    horizontal.setSizes([325,820,225])
    c.horizontal_split=horizontal
    c.vertical_split.addWidget(horizontal)

    # 4. Inspector inferior con campos reales y transporte de mezcla.
    c.inspector=QFrame(c)
    c.inspector.setObjectName("composerInspectorPanel")
    lower=QVBoxLayout(c.inspector)
    lower.setContentsMargins(5,4,5,4)
    lower.setSpacing(5)
    details=QTabWidget(c)
    details.setObjectName("composerDetails")
    c.details=details
    clip_page=QWidget()
    clip_box=QVBoxLayout(clip_page)
    clip_box.setContentsMargins(5,3,5,3)
    clip_box.setSpacing(3)
    editor=QHBoxLayout()
    editor.setSpacing(7)
    clip_box.addLayout(editor)
    editor.addWidget(QLabel("CLIP"))
    c.clip_name=QLabel("Sin selección")
    c.clip_name.setMinimumWidth(80)
    editor.addWidget(c.clip_name,1)
    c.clip_beat=c._value(0,10000,2)
    c.clip_offset=c._value(0,100000,2)
    c.clip_duration=c._value(.01,100000,2)
    for label,widget in (
        ("Compás",c.clip_beat),("Inicio (s)",c.clip_offset),
        ("Duración (s)",c.clip_duration)):
        editor.addWidget(QLabel(label))
        widget.setMaximumWidth(78)
        editor.addWidget(widget)
    c.apply_clip=c._button("Aplicar",c.apply_clip_edit)
    editor.addWidget(c.apply_clip)
    editor.addWidget(c._button("Piano Roll",c.open_clip_midi))
    dynamics_page=QWidget()
    fade=QHBoxLayout(dynamics_page)
    fade.setContentsMargins(7,3,7,3)
    fade.setSpacing(7)
    fade.addWidget(QLabel("DINÁMICA DEL CLIP"))
    c.clip_gain=c._value(0,4,2)
    c.clip_gain.setValue(1.)
    c.clip_fade_in=c._value(0,300,2)
    c.clip_fade_out=c._value(0,300,2)
    for label,control,tip in (
        ("Ganancia",c.clip_gain,"Volumen propio del clip, 0 a 400 %"),
        ("Entrada (s)",c.clip_fade_in,"Fundido desde silencio al comenzar"),
        ("Salida (s)",c.clip_fade_out,"Fundido progresivo hasta silencio")):
        fade.addWidget(QLabel(label))
        control.setToolTip(tip)
        control.setMaximumWidth(85)
        fade.addWidget(control)
    fade.addStretch(1)
    details.addTab(clip_page,"Editor de clip")
    details.addTab(dynamics_page,"Dinámica · fundidos")

    mixer_page=QWidget()
    mixer=QHBoxLayout(mixer_page)
    mixer.setContentsMargins(6,3,6,3)
    c.mixer_track_label=QLabel("Selecciona una pista para mezclar")
    mixer.addWidget(c.mixer_track_label,1)
    c.mixer_mute=QCheckBox("Mute")
    c.mixer_solo=QCheckBox("Solo")
    c.mixer_mute.toggled.connect(lambda b:c.update_selected_track(mute=b))
    c.mixer_solo.toggled.connect(lambda b:c.update_selected_track(solo=b))
    mixer.addWidget(c.mixer_mute)
    mixer.addWidget(c.mixer_solo)
    mixer.addWidget(QLabel("Nivel"))
    c.mixer_volume=QSlider(Qt.Horizontal)
    c.mixer_volume.setRange(0,200)
    c.mixer_volume.setValue(100)
    c.mixer_volume.setMaximumWidth(180)
    c.mixer_volume.sliderReleased.connect(
        lambda:c.update_selected_track(volume=c.mixer_volume.value()/100))
    mixer.addWidget(c.mixer_volume)
    mixer.addWidget(QLabel("Pan"))
    c.mixer_pan=QSlider(Qt.Horizontal)
    c.mixer_pan.setRange(-100,100)
    c.mixer_pan.setMaximumWidth(155)
    c.mixer_pan.sliderReleased.connect(
        lambda:c.update_selected_track(pan=c.mixer_pan.value()/100))
    mixer.addWidget(c.mixer_pan)
    details.addTab(mixer_page,"Mezclador")
    lower.addWidget(details)
    progressrow=QHBoxLayout()
    c.progress=QProgressBar(c)
    c.progress.setRange(0,1)
    c.progress.setValue(0)
    c.progress.setMaximumWidth(110)
    progressrow.addWidget(c.progress)
    c.status=QLabel("Sin proyecto. Crea o abre una sesión.")
    c.status.setObjectName("composerMuted")
    progressrow.addWidget(c.status,1)
    lower.addLayout(progressrow)
    c.preview=__import__("preview_player").PreviewPlayer(
        "PREVISUALIZACIÓN DE LA MEZCLA",c)
    c.preview.set_compact(True)
    # El reproductor sigue reproduciendo y controlando salida audio aunque
    # su panel grande esté recogido. El master medido está arriba junto a Play.
    c.preview.hide()
    lower.addWidget(c.preview)
    c.details_button=c._button(
        "Opciones de escucha ▾",
        lambda:c.preview.setVisible(not c.preview.isVisible()))
    c.details_button.setToolTip(
        "Abrir volumen, dispositivo y barra de posición de la preescucha."
        " Por defecto la zona de pistas ocupa casi todo el editor.")
    progressrow.addWidget(c.details_button)
    c.vertical_split.addWidget(c.inspector)
    c.vertical_split.setSizes([700,100])
    root.addWidget(c.vertical_split,1)
    c.track_table.verticalScrollBar().valueChanged.connect(
        c.timeline.verticalScrollBar().setValue)
    c.timeline.verticalScrollBar().valueChanged.connect(
        c.track_table.verticalScrollBar().setValue)
