"""Distribución tipo Inicio: tarjetas compactas en rejilla, mismos controles reales.

Se instala DESPUÉS de crear los controles selectivos. No cambia señales,
procesado, rutas, ni archivos. No introduce scroll en la pestaña.
"""
from PySide6.QtCore import Qt,QObject,QEvent,QTimer
from PySide6.QtWidgets import (
    QGridLayout,QHBoxLayout,QLabel,QPushButton,QSizePolicy,QWidget
)
from studio_workspace_cards import SectionCard
from separador import MODELS
from separation_pro_controls import stems_for_model

def install(main):
    sep=main.workbench.separator
    # El diálogo original tiene un único lienzo de trabajo, sin scroll.
    root=sep.layout().itemAt(0).widget().layout()
    cards={card.heading.text():card for card in sep.findChildren(SectionCard)}
    entry=next(card for name,card in cards.items() if "ARCHIVO Y AJUSTES" in name)
    run=next(card for name,card in cards.items() if "PROCESAR" in name)
    tools=next(card for name,card in cards.items() if "DESTINOS Y HERRAMIENTAS" in name)
    activity=next(card for name,card in cards.items() if "ACTIVIDAD DEL MOTOR" in name)

    # Separar la reproducción de la configuración; mantener el mismo player.
    preview=SectionCard("03 · ESCUCHAR EL ORIGINAL","wave")
    preview.body.setContentsMargins(9,5,9,7)
    preview.body.addWidget(sep.source_preview)
    sep.source_preview.setMinimumWidth(0)
    sep.source_preview.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)

    # Reagrupar las casillas existentes; no hay interruptores simulados.
    selection=SectionCard("02 · ¿QUÉ QUIERES EXTRAER?","layers")
    selection.body.setContentsMargins(11,5,11,6)
    selection.body.setSpacing(5)
    old_picker=sep.stem_all.parentWidget()
    entry.body.removeWidget(old_picker)
    old_picker.hide()
    grid_holder=QWidget(selection)
    stem_grid=QGridLayout(grid_holder)
    stem_grid.setContentsMargins(1,1,1,1)
    stem_grid.setHorizontalSpacing(9)
    stem_grid.setVerticalSpacing(3)
    heading=QLabel("INSTRUMENTOS",grid_holder)
    heading.setObjectName("muted")
    stem_grid.addWidget(heading,0,0)
    stem_grid.addWidget(sep.stem_all,0,1)
    for widget in sep.stem_checks.values():
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
    selection.body.addWidget(grid_holder)
    selection.body.addWidget(sep.stem_parameters_btn)
    sep.stem_parameters_btn.setMaximumWidth(180)
    sep.stem_parameters_btn.setMinimumHeight(28)
    selection.body.addWidget(sep.stem_note)
    sep.stem_note.setWordWrap(True)
    sep.stem_note.setMaximumHeight(42)
    sep._selection_card=selection
    sep._selection_grid=stem_grid
    sep._old_selection_bar=old_picker

    def rearrange(_=None):
        supported=stems_for_model(MODELS.get(sep.profile.currentText()))
        for cb in sep.stem_checks.values():
            stem_grid.removeWidget(cb)
        for i,key in enumerate(supported):
            cb=sep.stem_checks[key]
            stem_grid.addWidget(cb,1+i//2,i%2)
        # Cambiar de modelo puede ocultar casillas: no ocupan huecos.
    sep.profile.currentIndexChanged.connect(rearrange)
    rearrange()

    entry.heading.setText("01 · ARCHIVO Y CONFIGURACIÓN")
    entry.body.setContentsMargins(10,5,10,7)
    entry.body.setSpacing(5)
    sep._setup_frame.setMinimumHeight(0)
    sep._setup_frame.setMaximumHeight(158)
    sep._setup_frame.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    for control in (sep.file_edit,sep.profile,sep.dest_edit):
        control.setMinimumWidth(0)

    run.heading.setText("04 · PROCESAR AUDIO")
    run.body.setContentsMargins(9,5,9,7)
    tools.heading.setText("05 · ACCIONES SIGUIENTES")
    tools.body.setContentsMargins(10,6,10,8)
    activity.heading.setText("06 · ACTIVIDAD DEL MOTOR")
    activity.body.setContentsMargins(10,6,10,8)
    activity.heading.setToolTip("Registro técnico, progreso global e individual mientras se separa.")

    # Los seis QPushButton ya tienen callbacks conectados.
    row=tools.body.takeAt(0)
    old_buttons=row.layout()
    action_buttons=[
        sep.mix_button,sep.midi_button,sep.open_results_button,
        sep.library_button,sep.load_previous_button,
        next(btn for btn in tools.findChildren(QPushButton) if btn.text()=="Registro")
    ]
    for btn in action_buttons:
        old_buttons.removeWidget(btn)
    buttons=QGridLayout()
    buttons.setContentsMargins(0,0,0,0)
    buttons.setHorizontalSpacing(6)
    buttons.setVerticalSpacing(6)
    for i,btn in enumerate(action_buttons):
        btn.setMaximumWidth(16777215)
        btn.setMinimumWidth(0)
        btn.setMinimumHeight(33)
        btn.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        buttons.addWidget(btn,i//3,i%3)
    tools.body.addLayout(buttons)
    sep._old_tools_buttons_layout=old_buttons

    # Reusar cabecera y descripción existentes.
    existing=[]
    while root.count():
        existing.append(root.takeAt(0))
    title=sep.findChildren(QLabel,"title")
    header=next((item.widget() for item in existing
                 if item.widget() is not None and item.widget().text()=="SEPARACIÓN DE PISTAS"),None)
    desc=sep._subtitle
    assert header is not None
    root.setContentsMargins(8,5,8,9)
    root.setSpacing(8)
    root.addWidget(header)
    root.addWidget(desc)

    board=QGridLayout()
    board.setContentsMargins(0,0,0,0)
    board.setHorizontalSpacing(8)
    board.setVerticalSpacing(8)
    root.addLayout(board)
    root.addStretch(1)
    all_cards=(entry,selection,preview,run,tools,activity)
    for card in all_cards:
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    dashboard_buttons=action_buttons
    sep._dashboard_board=board

    adaptive=getattr(sep,"_adaptive_separation_layout",None)
    if adaptive is not None:
        sep.removeEventFilter(adaptive)
        adaptive.update=lambda:None

    splitter=main.workbench.separation_tab
    splitter.setStretchFactor(0,55)
    splitter.setStretchFactor(1,45)
    # QSplitter suele conservar la proporción previa al maximizar; reajustar
    # solamente cuando cambia el tamaño de la ventana, sin bloquear el asa.
    class _KeepRatio(QObject):
        def __init__(self,parent):
            super().__init__(parent)
            self.pending=False
        def eventFilter(self,obj,event):
            if obj is splitter and event.type()==QEvent.Resize and not self.pending:
                self.pending=True
                QTimer.singleShot(0,self.update)
            return False
        def update(self):
            self.pending=False
            usable=max(0,splitter.width()-splitter.handleWidth())
            if usable:
                splitter.setSizes([round(usable*0.55),round(usable*0.45)])
    ratio_keeper=_KeepRatio(splitter)
    splitter.installEventFilter(ratio_keeper)
    sep._splitter_ratio_keeper=ratio_keeper
    QTimer.singleShot(0,ratio_keeper.update)

    preview_label=next(
        (widget for widget in sep.source_preview.findChildren(QLabel)
         if widget.text()=="ESCUCHAR AUDIO ORIGINAL"),None)

    class _Responsive(QObject):
        def __init__(self,parent):
            super().__init__(parent)
            self.mode=None
        def eventFilter(self,obj,event):
            if obj is sep and event.type()==QEvent.Resize:
                QTimer.singleShot(0,self.update)
            return False
        def update(self):
            import shiboken6
            if not shiboken6.isValid(sep):return
            narrow=sep.width()<880
            if self.mode==narrow:return
            self.mode=narrow
            for card in all_cards:
                board.removeWidget(card)
            for btn in dashboard_buttons:
                buttons.removeWidget(btn)
            if narrow:
                # Estrecho: el formulario ocupa una fila entera, sin
                # truncarse; acciones agrupadas con la selección.
                board.addWidget(entry,0,0,1,2)
                entry.setMinimumHeight(198)
                selection.setMinimumHeight(128)
                tools.setMinimumHeight(148)
                preview.setMinimumHeight(158)
                run.setMinimumHeight(158)
                board.addWidget(selection,1,0)
                board.addWidget(tools,1,1)
                board.addWidget(preview,2,0)
                board.addWidget(run,2,1)
                board.setColumnStretch(0,56)
                board.setColumnStretch(1,44)
                for i,btn in enumerate(dashboard_buttons):
                    buttons.addWidget(btn,i//2,i%2)
                sep.stem_note.hide()
                activity.hide()
                header.hide()
                desc.hide()
                tools.heading.setText("05 · ACCIONES")
                run.heading.setText("04 · PROCESAR")
                sep.go.setText("Separar")
                listen=sep.source_preview
                listen.play_button.setText("▶")
                listen.stop_button.setText("■")
                listen.play_button.setMinimumWidth(30)
                listen.stop_button.setMinimumWidth(30)
                listen.volume_label.setText("Vol.")
                listen.speed_label.setText("Vel.")
                listen.channel_mode.setMaximumWidth(110)
                if preview_label:preview_label.setText("ESCUCHAR ORIGINAL")
            else:
                entry.setMinimumHeight(0)
                selection.setMinimumHeight(0)
                tools.setMinimumHeight(92)
                preview.setMinimumHeight(160)
                run.setMinimumHeight(160)
                board.addWidget(entry,0,0)
                board.addWidget(selection,0,1)
                board.addWidget(preview,1,0)
                board.addWidget(run,1,1)
                board.addWidget(tools,2,0,1,2)
                board.addWidget(activity,3,0,1,2)
                board.setColumnStretch(0,54)
                board.setColumnStretch(1,46)
                for i,btn in enumerate(dashboard_buttons):
                    buttons.addWidget(btn,0,i)
                sep.stem_note.show()
                activity.show()
                header.show()
                desc.show()
                tools.heading.setText("05 · ACCIONES SIGUIENTES")
                run.heading.setText("04 · PROCESAR AUDIO")
                sep.go.setText("Separar pistas")
                listen=sep.source_preview
                listen.play_button.setText("▶ Reproducir")
                listen.stop_button.setText("■ Detener")
                listen.play_button.setMinimumWidth(100)
                listen.stop_button.setMinimumWidth(85)
                listen.volume_label.setText("Volumen")
                listen.speed_label.setText("Velocidad")
                listen.channel_mode.setMaximumWidth(16777215)
                if preview_label:preview_label.setText("ESCUCHAR AUDIO ORIGINAL")
            board.invalidate()
    resp=_Responsive(sep)
    sep.installEventFilter(resp)
    sep._adaptive_dashboard=resp
    QTimer.singleShot(0,resp.update)
    sep._dashboard_cards=(entry,selection,preview,run,tools,activity)
    return True
