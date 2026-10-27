"""Mejoras funcionales de Separación: preescuchas, IA y monitor.

Qt real: se reutilizan componentes y conexiones existentes. La mezcla
mono y escucha por canal se ejecutan en ffplay, sin alterar el original.
"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt,QObject,QTimer
from PySide6.QtWidgets import (
    QWidget,QLabel,QHBoxLayout,QVBoxLayout,QGridLayout,
    QPushButton,QComboBox,QProgressBar,QSizePolicy,QPlainTextEdit
)
from separador import MODELS,MODELS_DIR
from separation_pro_controls import stems_for_model,instrument_for

def reflow_player(player, original=False):
    """Recolocar todos los controles de PreviewPlayer, no duplicarlos."""
    player.set_compact(False)
    outer=player.layout()
    # Desanidar QLayouts antiguos sin borrar sus widgets.
    while outer.count():
        outer.takeAt(0)
    outer.setContentsMargins(8,5,8,7)
    outer.setSpacing(5)
    player.options_button.hide()
    player.detail.hide()
    title=next((x for x in player.findChildren(QLabel)
                if x.text() in ("ESCUCHAR AUDIO ORIGINAL","PREVISUALIZAR RESULTADO SELECCIONADO")),None)
    if title:title.hide()
    player.filename.setMaximumHeight(32)
    player.filename.setWordWrap(False)
    outer.addWidget(player.filename)
    transport=QHBoxLayout()
    transport.setContentsMargins(0,0,0,0)
    transport.setSpacing(5)
    for widget in (player.play_button,player.stop_button,player.slider,player.clock):
        widget.setMinimumWidth(0)
        transport.addWidget(widget,1 if widget is player.slider else 0)
    player.slider.setMaximumWidth(16777215)
    player.play_button.setMinimumWidth(100)
    player.stop_button.setMinimumWidth(85)
    outer.addLayout(transport)
    outer.addWidget(player._measured_vu.meter)
    settings=QHBoxLayout()
    settings.setContentsMargins(0,0,0,0)
    settings.setSpacing(6)
    player.volume.setMaximumWidth(108)
    for widget in (player.volume_label,player.volume,player.speed_label,player.speed):
        settings.addWidget(widget)
    settings.addStretch(1)
    if original:
        label=QLabel("Canales")
        mode=QComboBox()
        mode.addItems(("Estéreo","Mono (L+R)","Solo izquierdo","Solo derecho"))
        mode.setToolTip("Monitorización: no convierte ni modifica el archivo original.")
        player.channel_mode=mode
        def on_mode(_=None):
            if player._play_process is not None or player._qt_active:
                position=player._position()
                player._start_audio(position)
        mode.currentIndexChanged.connect(on_mode)
        settings.addWidget(label)
        settings.addWidget(mode)
    outer.addLayout(settings)
    route=QHBoxLayout()
    route.setContentsMargins(0,0,0,0)
    route.setSpacing(5)
    player.route_label.setText("Salida")
    player.device_choice.setMinimumWidth(0)
    player.device_choice.setMaximumWidth(16777215)
    player.device_choice.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    player.status.setMaximumWidth(170)
    for widget in (player.route_label,player.device_choice,player.status):
        route.addWidget(widget)
    route.addStretch(1)
    outer.addLayout(route)
    player.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    player.setMinimumWidth(0)
    player._extended_preview=True

def run_model_controls(sep,run):
    layout=QHBoxLayout()
    layout.setContentsMargins(0,2,0,0)
    layout.setSpacing(5)
    name=QLabel("Modelo IA")
    combo=QComboBox()
    combo.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    combo.setMinimumWidth(0)
    combo.setToolTip("Modelo de separación. La lista se obtiene del catálogo ya instalado.")
    button=QPushButton("Cargar IA…")
    button.setToolTip("Abrir gestor de modelos: consultar, instalar y activar IA compatibles.")
    layout.addWidget(name);layout.addWidget(combo,1);layout.addWidget(button)
    run.body.insertLayout(1,layout)
    sep.model_run_selector=combo
    sep.model_run_import=button
    synced=[False]
    def sync_from_profile(_=None):
        if synced[0]:return
        synced[0]=True
        try:
            combo.blockSignals(True)
            combo.clear()
            for index in range(sep.profile.count()):
                label=sep.profile.itemText(index)
                model=MODELS.get(label)
                if model is None or (MODELS_DIR/model).is_file():
                    combo.addItem(label,model)
            target=combo.findText(sep.profile.currentText())
            if target<0:combo.addItem(sep.profile.currentText(),MODELS.get(sep.profile.currentText()))
            combo.setCurrentText(sep.profile.currentText())
            combo.blockSignals(False)
            button.setEnabled(not sep.busy)
            combo.setEnabled(not sep.busy)
        finally:synced[0]=False
    def change_profile(_=None):
        if synced[0]:return
        if combo.currentText() and not sep.busy:
            sep.profile.setCurrentText(combo.currentText())
    def open_manager():
        sep.open_model_manager()
        QTimer.singleShot(400,sync_from_profile)
    sep.profile.currentIndexChanged.connect(sync_from_profile)
    sep.profile.currentIndexChanged.connect(lambda _:combo.setToolTip(
        "Modelo disponible: "+sep.profile.currentText()))
    combo.currentIndexChanged.connect(change_profile)
    button.clicked.connect(open_manager)
    sep._model_selector_sync=sync_from_profile
    sync_from_profile()

def enhance_activity(sep,activity):
    # La antigua zona solo desplegaba un log de 74px, sin telemetría.
    layout=activity.body
    for index in reversed(range(layout.count())):
        item=layout.takeAt(index)
        if item.widget() is not None:item.widget().hide()
    state=QLabel("Estado: en espera")
    state.setObjectName("muted")
    file_label=QLabel("Archivo: ninguno")
    file_label.setObjectName("muted")
    file_label.setMaximumHeight(22)
    total=QProgressBar()
    total.setRange(0,100)
    total.setValue(0)
    total.setFormat("General: 0%")
    layout.addWidget(state)
    layout.addWidget(file_label)
    layout.addWidget(total)
    split=QGridLayout()
    split.setHorizontalSpacing(7)
    split.setVerticalSpacing(2)
    bars={}
    for idx,key in enumerate(("Voz","Batería","Bajo","Guitarra","Piano","Otros")):
        label=QLabel(key)
        bar=QProgressBar()
        bar.setFixedHeight(13)
        bar.setRange(0,100)
        bar.setValue(0)
        bar.setFormat("%p%")
        split.addWidget(label,idx//2,0 if idx%2==0 else 2)
        split.addWidget(bar,idx//2,1 if idx%2==0 else 3)
        bars[key]=bar
    layout.addLayout(split)
    technical=QPlainTextEdit()
    technical.setReadOnly(True)
    technical.setPlaceholderText("El registro de actividad se mostrará aquí.")
    technical.setMaximumBlockCount(500)
    technical.setMinimumHeight(65)
    layout.addWidget(technical,1)
    show=QPushButton("Registro completo…")
    show.setMaximumWidth(150)
    def open_inspector():
        dlg=getattr(sep,"motor_dialog",None)
        if dlg is not None:
            dlg.show()
            dlg.raise_()
        else:
            technical.setFocus()
    show.clicked.connect(open_inspector)
    layout.addWidget(show)
    sep.activity_info={
        "state":state,"file":file_label,"total":total,
        "bars":bars,"log":technical,"open":show
    }
    def update():
        import shiboken6
        if not shiboken6.isValid(sep):return
        info=sep.activity_info
        label=sep.profile.currentText()
        model=MODELS.get(label)
        status=("Separando — etapa "+str(sep.steps) if sep.busy
                else "Finalizado" if sep.latest_outputs
                else "En espera")
        dlg=getattr(sep,"motor_dialog",None)
        stage=dlg.stage.text() if dlg is not None else ""
        info["state"].setText("Estado: "+status+" | "+("IA "+str(model) if model else "Canales L/R")+
                              (" · "+stage if sep.busy and stage else ""))
        src=Path(sep.file_edit.text().strip())
        info["file"].setText("Archivo: "+(src.name if src.name else "ninguno")+"  ·  "+
                             sep.elapsed.text()+" · Restante: sin estimación verificable")
        dlg=getattr(sep,"motor_dialog",None)
        finished=bool(sep.latest_outputs) and not sep.busy
        # El panel integrado refleja el MISMO avance verificable del
        # inspector, sin otra barra animada en bucle.
        general=(dlg.total.value() if dlg is not None
                 else sep.progress.value())
        info["total"].setRange(0,100)
        info["total"].setValue(general)
        info["total"].setFormat(f"General: {general}%")
        active=set(getattr(sep,"active_request",stems_for_model(model)))
        found={instrument_for(p) for p in sep.latest_outputs}
        for name,bar in info["bars"].items():
            on=name in active and model is not None
            bar.setVisible(on)
            if on:
                bar.setRange(0,100)
                if dlg is not None and name in dlg.rows:
                    value=dlg.rows[name].value()
                else:
                    value=100 if name in found else 0
                bar.setValue(value)
                bar.setFormat(f"{value}%")
        lines=sep.log.toPlainText()
        if technical.toPlainText()!=lines:
            technical.setPlainText(lines)
            technical.verticalScrollBar().setValue(technical.verticalScrollBar().maximum())
        sep.model_run_selector.setEnabled(not sep.busy)
        sep.model_run_import.setEnabled(not sep.busy)
    sep._activity_refresh=update
    watcher=QTimer(sep)
    watcher.setInterval(600)
    watcher.timeout.connect(update)
    watcher.start()
    sep._activity_watcher=watcher
    sep.log.textChanged.connect(update)
    QTimer.singleShot(0,update)

def install(main):
    sep=main.workbench.separator
    cards=sep._dashboard_cards
    entry,selection,preview,run,tools,activity=cards
    reflow_player(sep.source_preview,True)
    reflow_player(main.workbench.sep_results.preview,False)
    main.workbench.sep_results.preview.setMinimumHeight(160)
    run_model_controls(sep,run)
    def refresh_ia_when_returning(_=None):
        if main.tabs.currentWidget() is main.workbench.separation_tab and not sep.busy:
            sep.refresh_model_registry()
            sep._model_selector_sync()
    main.tabs.currentChanged.connect(refresh_ia_when_returning)
    enhance_activity(sep,activity)
    # Consumir el espacio antes vacío debajo de los módulos.
    root=sep.layout().itemAt(0).widget().layout()
    board=sep._dashboard_board
    root.removeItem(board)
    while root.count() and root.itemAt(root.count()-1).spacerItem():
        root.takeAt(root.count()-1)
    root.addLayout(board,1)
    board.setRowStretch(0,0)
    board.setRowStretch(1,1)
    board.setRowStretch(2,0)
    board.setRowStretch(3,4)
    activity.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    activity.setMinimumHeight(205)
    preview.setMinimumHeight(160)
    run.setMinimumHeight(160)
    tools.setMinimumHeight(92)
    return True
