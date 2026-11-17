"""Tarjetas funcionales de StemMIDI: mismo lenguaje visual que Inicio.

Reorganiza los QLayoutItem existentes tras construir la interfaz. No crea
controles sustitutos, ni cambia callbacks, audio, rutas o archivos.
"""
from pathlib import Path
from PySide6.QtCore import Qt,QObject,QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,QWidget,QLabel,QVBoxLayout,QHBoxLayout,QSizePolicy,QPushButton,
    QScrollArea,QLayout,QAbstractItemView,QTableWidget
)

ASSETS=Path(__file__).resolve().parent/"assets"

class SectionCard(QFrame):
    def __init__(self,title,icon="layers",parent=None):
        super().__init__(parent)
        self.setObjectName("studioCard")
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        outer=QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        banner=QFrame(self)
        banner.setObjectName("moduleCardBanner")
        head=QHBoxLayout(banner)
        head.setContentsMargins(10,2,10,2)
        head.setSpacing(7)
        pic=QLabel(banner)
        pic.setObjectName("moduleCardIcon")
        pic.setPixmap(QIcon(str(ASSETS/f"ui_{icon}.svg")).pixmap(19,19))
        pic.setFixedSize(21,21)
        head.addWidget(pic)
        self.heading=QLabel(title,banner)
        self.heading.setObjectName("moduleCardHeading")
        head.addWidget(self.heading,1)
        outer.addWidget(banner,0)
        self.body=QVBoxLayout()
        self.body.setContentsMargins(9,7,9,8)
        self.body.setSpacing(5)
        outer.addLayout(self.body,1)

def _take(layout):
    return [layout.takeAt(0) for _ in range(layout.count())]

def _add(layout,item,stretch=0):
    if item.widget() is not None:
        layout.addWidget(item.widget(),stretch)
    elif item.layout() is not None:
        layout.addLayout(item.layout(),stretch)
    elif item.spacerItem() is not None:
        layout.addItem(item.spacerItem())

def _move(layout,items,indices,stretch_last=False):
    for j,i in enumerate(indices):
        _add(layout,items[i],1 if stretch_last and j==len(indices)-1 else 0)

def _frame_layout(widget):
    layout=widget.layout()
    assert layout is not None
    layout.setContentsMargins(9,7,9,8)
    layout.setSpacing(5)

def wrap_stage(splitter,widget,title,icon):
    assert splitter.indexOf(widget)>=0
    index=splitter.indexOf(widget)
    card=SectionCard(title,icon,splitter)
    _frame_layout(widget)
    card.body.addWidget(widget,1)
    splitter.insertWidget(index,card)
    card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    return card

def stage_empty_state(stage):
    # El contenido es fiel al estado real: no muestra pistas inventadas.
    # Se actualiza cada vez que TaskResults.populate() reconstruye filas.
    stage.setObjectName("moduleResultZone")

def decorate_separation(main):
    from separation_compact_ui import compact
    compact(main)
    from separation_pro_controls import setup_request_controls,setup_results_controls
    setup_request_controls(main.workbench.separator,
        main.workbench.separator.findChildren(SectionCard)[0])
    wrap_stage(main.workbench.separation_tab,main.workbench.sep_results,
               "PISTAS SEPARADAS · REVISIÓN Y ENTREGA","folder")
    # La tarjeta nueva sustituye al widget 1 del QSplitter: restaurar su
    # factor de expansión (el original se pierde durante el envoltorio).
    splitter=main.workbench.separation_tab
    splitter.setStretchFactor(0,55)
    splitter.setStretchFactor(1,45)
    from PySide6.QtCore import QTimer
    def fit_initial_columns():
        width=max(0,splitter.width()-splitter.handleWidth())
        if width:
            splitter.setSizes([round(width*0.55),round(width*0.45)])
    QTimer.singleShot(0,fit_initial_columns)
    stage_empty_state(main.workbench.sep_results)
    setup_results_controls(main)
    from separation_dashboard_layout import install as install_dashboard
    install_dashboard(main)
    from separation_extended_ui import install as install_extended_ui
    install_extended_ui(main)


def decorate_midi(main):
    midi=main.workbench.converter
    root=midi.findChildren(QScrollArea)[0].widget().layout()
    items=_take(root)
    assert len(items)==18,len(items)
    root.setContentsMargins(10,7,10,8);root.setSpacing(8)
    _move(root,items,(0,1))
    card=SectionCard("01 · ENTRADA Y PISTAS DEL PROYECTO","note")
    _move(card.body,items,(2,3))
    midi.stem_shelf.setMaximumHeight(90)
    def resize_stems(*_):
        import shiboken6
        if not shiboken6.isValid(midi.stem_shelf):
            return
        midi.stem_shelf.setMaximumHeight(
            150 if midi.stem_shelf.count() else 62)
    midi.stem_shelf.model().rowsInserted.connect(resize_stems)
    midi.stem_shelf.model().rowsRemoved.connect(resize_stems)
    midi.stem_shelf.model().modelReset.connect(resize_stems)
    resize_stems()
    root.addWidget(card)
    card2=SectionCard("02 · MODELO Y PARÁMETROS DE TRANSCRIPCIÓN","mixer")
    _move(card2.body,items,(4,))
    midi.form_tabs.setMaximumHeight(420)
    root.addWidget(card2)
    process=SectionCard("03 · CONVERTIR Y REVISAR","wave")
    _move(process.body,items,(5,6,7,8,9,10,11,12,13,14))
    root.addWidget(process)
    log=SectionCard("04 · ACTIVIDAD DEL MOTOR","info")
    _move(log.body,items,(15,16,17))
    midi.log.setMaximumHeight(82)
    root.addWidget(log)
    root.addStretch()
    wrap_stage(main.workbench.midi_tab,main.workbench.midi_results,
               "MIDI GENERADO · ESCUCHA Y EXPORTACIÓN","folder")
    stage_empty_state(main.workbench.midi_results)

def decorate_vocal(main):
    vocal=main.vocal_module
    root=vocal.content_scroll.widget().layout()
    items=_take(root)
    assert len(items)==11,len(items)
    root.setContentsMargins(11,7,11,9);root.setSpacing(8)
    _move(root,items,(0,1))
    inp=SectionCard("01 · VOZ DE ORIGEN Y TONALIDAD","wave")
    _move(inp.body,items,(2,))
    inp.body.setSpacing(3)
    root.addWidget(inp)
    columns=QHBoxLayout()
    columns.setSpacing(9)
    fx=SectionCard("02 · LABORATORIO VOCAL Y EFECTOS","mixer")
    _move(fx.body,items,(3,4,5,6))
    # Los formularios de FX largos conservan scroll SOLO en su propia
    # pestaña. La ventana vocal general muestra todas las operaciones.
    vocal.studio_tabs.setMinimumHeight(185)
    vocal.studio_tabs.setMaximumHeight(228)
    # Los textos largos forzaban botones parcialmente ocultos.
    # Acortamos rótulos visibles, manteniendo explicación íntegra en tooltip.
    labels=("Afinación","Carácter","EQ · FX","Doblado · Delay","Aprender interpretación")
    for i,label in enumerate(labels):
        old=vocal.studio_tabs.tabText(i)
        vocal.studio_tabs.setTabText(i,label)
        vocal.studio_tabs.setTabToolTip(i,old)
    vocal.processing_notice.setMaximumHeight(35)
    columns.addWidget(fx,63)
    outputs=SectionCard("03 · RESULTADOS Y COMPARACIÓN A/B","folder")
    _move(outputs.body,items,(7,8,9,10))
    vocal.table.setMinimumHeight(72)
    vocal.table.setMaximumHeight(147)
    vocal.preview.set_compact(True)
    outputs.body.setSpacing(5)
    columns.addWidget(outputs,37)
    root.addLayout(columns,1)
    root.addStretch(0)

def decorate_drum(main):
    drum=main.drum_module
    root=drum.layout()
    items=_take(root)
    assert len(items)==10,len(items)
    root.setContentsMargins(9,7,9,8)
    root.setSpacing(7)
    _move(root,items,(0,1))
    src=SectionCard("01 · ENTRADA, MODELO Y PRESETS","record")
    _move(src.body,items,(2,3,4,5,6))
    root.addWidget(src,0)
    studio=SectionCard("02 · MESA, EDITOR Y SECUENCIADOR","mixer")
    _move(studio.body,items,(7,))
    root.addWidget(studio,1)
    footer=SectionCard("03 · ESCUCHA Y ARCHIVOS","folder")
    _move(footer.body,items,(8,9))
    drum.preview.set_compact(True)
    root.addWidget(footer,0)

def decorate_piano(main):
    piano=main.workbench.piano
    root=piano.content_layout
    items=_take(root)
    assert len(items)==11,len(items)
    root.setContentsMargins(8,5,8,7);root.setSpacing(6)
    _move(root,items,(0,))
    transport=SectionCard("01 · TRANSPORTE Y POSICIÓN","note")
    _move(transport.body,items,(1,2))
    transport.body.setSpacing(3)
    root.addWidget(transport)
    tools=SectionCard("02 · EDICIÓN, ZOOM Y TEMPO","mixer")
    _move(tools.body,items,(3,4,5,6,7))
    tools.body.setSpacing(3)
    root.addWidget(tools)
    editor=SectionCard("03 · REJILLA MIDI Y TECLADO","piano")
    _move(editor.body,items,(8,9,10))
    editor.body.setSpacing(4)
    piano.preview.set_compact(True)
    root.addWidget(editor,1)

class EmptyTableIndicator(QObject):
    def __init__(self,table):
        super().__init__(table)
        self.table=table
        self.label=QLabel(
            "AÚN NO HAY ARCHIVOS EN ESTE PROYECTO\n\n"
            "Las grabaciones, stems y MIDI aparecerán aquí\n"
            "cuando terminen sus procesos y se incorporen al proyecto.",
            table.viewport())
        self.label.setObjectName("moduleEmptyState")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        # Qt destruye primero el modelo, luego el viewport: los callbacks
        # rowsRemoved/eventFilter podían tocar un QTableWidget ya eliminado.
        # Vinculamos la actualización exclusivamente a un QTimer propiedad
        # de la tabla; Qt lo detiene y destruye junto a ella.
        from PySide6.QtCore import QTimer
        self.timer=QTimer(table)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        self.update()
    def _size(self):
        import shiboken6
        if not shiboken6.isValid(self.table):
            return
        vp=self.table.viewport()
        if not shiboken6.isValid(vp):return
        w=min(560,max(160,vp.width()-40))
        h=min(210,max(80,vp.height()-28))
        self.label.setGeometry((vp.width()-w)//2,(vp.height()-h)//2,w,h)
    def update(self,*_):
        import shiboken6
        if not shiboken6.isValid(self.table):
            return
        self._size()
        if shiboken6.isValid(self.label):
            self.label.setVisible(self.table.rowCount()==0)

def decorate_results(main):
    widget=main.results_tab
    root=widget.layout()
    items=_take(root)
    assert len(items)==6,len(items)
    root.setContentsMargins(11,7,11,9);root.setSpacing(8)
    _move(root,items,(0,1))
    columns=QHBoxLayout()
    columns.setSpacing(9)
    library=SectionCard("01 · ARCHIVOS DE ESTE PROYECTO","folder")
    _move(library.body,items,(2,))
    columns.addWidget(library,72)
    listen=SectionCard("02 · PREESCUCHA Y EXPORTACIÓN","wave")
    _move(listen.body,items,(3,4,5))
    listen.body.addStretch(1)
    columns.addWidget(listen,28)
    root.addLayout(columns,1)
    widget._empty_hint=EmptyTableIndicator(widget.table)

def decorate_mixer(main):
    page=main.mixer_placeholder
    root=page.layout()
    items=_take(root)
    assert len(items)==6,len(items)
    root.setContentsMargins(11,7,11,9);root.setSpacing(8)
    _move(root,items,(0,1))
    columns=QHBoxLayout()
    columns.setSpacing(9)
    primary=SectionCard("01 · MESA DE MEZCLAS","mixer")
    _move(primary.body,items,(2,))
    help_label=QLabel("Para mezclar pistas reales:\n"
        "1. Separa una canción o carga una toma multicanal.\n"
        "2. Selecciona las pistas obtenidas.\n"
        "3. Abre el mezclador y regula volumen, Solo y Mute.\n"
        "4. Exporta la mezcla sin modificar las fuentes.")
    help_label.setObjectName("moduleWorkflowNote")
    help_label.setWordWrap(True)
    primary.body.addWidget(help_label)
    primary.body.addStretch()
    columns.addWidget(primary,48)
    player=SectionCard("02 · ESCUCHA ANTES DE MEZCLAR","wave")
    _move(player.body,items,(3,4))
    player.body.addStretch()
    columns.addWidget(player,52)
    root.addLayout(columns,1)
    # El último spacer del layout anterior se descarta sin cambiar controles.

def install(main):
    decorate_separation(main)
    decorate_midi(main)
    decorate_vocal(main)
    decorate_drum(main)
    decorate_piano(main)
    decorate_results(main)
    decorate_mixer(main)
    return True
