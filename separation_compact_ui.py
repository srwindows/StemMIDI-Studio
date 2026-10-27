"""Separación de audio: panel profesional y compacto, sin scroll de página.

No cambia el motor: reorganiza los controles reales y mantiene señales.
La lista de stems puede desplazarse solo si existen más pistas de las que caben.
"""
from __future__ import annotations

from PySide6.QtCore import Qt,QObject,QEvent,QTimer
from PySide6.QtWidgets import (
    QFrame,QGridLayout,QHBoxLayout,QLabel,QPushButton,QScrollArea,
    QSplitter,QTabWidget,QVBoxLayout,QWidget,QSizePolicy,QDialog,QPlainTextEdit
)

def _take(layout):
    return [layout.takeAt(0) for _ in range(layout.count())]

def _push(layout,item):
    if item.widget() is not None:layout.addWidget(item.widget())
    elif item.layout() is not None:layout.addLayout(item.layout())
    elif item.spacerItem() is not None:layout.addItem(item.spacerItem())

def _find_layout_widget(layout,name):
    for i in range(layout.count()):
        thing=layout.itemAt(i).widget()
        if thing is not None and hasattr(thing,"text") and thing.text()==name:
            return thing
    raise LookupError("No se encuentra botón: "+name)

def compact(main):
    from studio_workspace_cards import SectionCard
    sep=main.workbench.separator
    results=main.workbench.sep_results
    splitter=main.workbench.separation_tab
    scroll=next(s for s in sep.findChildren(QScrollArea)
                if s.parentWidget() is sep)
    inner=scroll.takeWidget()
    outer=sep.layout()
    removed=outer.takeAt(0)
    assert removed.widget() is scroll
    outer.addWidget(inner)
    scroll.deleteLater()
    sep.setMinimumSize(0,0)
    inner.setObjectName("separationCompactCanvas")
    root=inner.layout()
    items=_take(root)
    assert len(items)==16,len(items)
    root.setContentsMargins(7,5,7,6)
    root.setSpacing(5)
    # Original title / description: useful, but not two oversized rows.
    heading=items[0].widget()
    subtitle=items[1].widget()
    heading.setMaximumHeight(29)
    subtitle.setMaximumHeight(22)
    subtitle.setWordWrap(False)
    root.addWidget(heading,0)
    root.addWidget(subtitle,0)

    entry=SectionCard("01 · ARCHIVO Y AJUSTES","layers")
    entry.setObjectName("studioCard")
    entry.body.setContentsMargins(8,4,8,5)
    entry.body.setSpacing(4)

    presets=items[2].widget()
    assert presets is sep.presets
    presets.layout().setContentsMargins(2,1,2,1)
    presets.layout().setSpacing(3)
    presets.choices.setMinimumWidth(125)
    presets.choices.setMaximumWidth(215)
    presets.name.setMinimumWidth(90)
    presets.name.setMaximumWidth(155)
    presets.save_btn.setMaximumWidth(72)
    presets.delete_btn.setMaximumWidth(73)
    presets.message.hide()
    entry.body.addWidget(presets,0)

    frame=items[3].widget()
    frame.setMinimumHeight(149)
    frame.setMaximumHeight(161)
    frame.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    grid=frame.layout()
    setup_items=_take(grid)
    assert len(setup_items)==14,len(setup_items)
    widgets=[it.widget() for it in setup_items]
    assert all(w is not None for w in widgets)
    # Original order: label/input/import, info, label/model/manage,
    # label/quality, label/format, label/path/folder.
    labels={w.text():w for w in widgets
            if isinstance(w,QLabel) and w is not sep.import_info}
    folder_button=next(w for w in widgets
        if isinstance(w,QPushButton) and w.text().startswith("Carpeta"))
    grid.setContentsMargins(3,3,3,3)
    grid.setHorizontalSpacing(7)
    grid.setVerticalSpacing(5)
    # Primary file and model rows retain their existing controls.
    grid.addWidget(labels["Archivo de audio"],0,0)
    grid.addWidget(sep.file_edit,0,1,1,3)
    sep.import_button.setText("Importar…")
    sep.import_button.setToolTip("Buscar audio o vídeo con sonido para separar.")
    grid.addWidget(sep.import_button,0,4)
    grid.addWidget(labels["Tipo de separación"],1,0)
    grid.addWidget(sep.profile,1,1,1,3)
    sep.manage_models_btn.setText("Modelos…")
    grid.addWidget(sep.manage_models_btn,1,4)
    # Pair quality and output format on one line.
    labels["Calidad de procesamiento"].setText("Calidad")
    labels["Formato de exportación"].setText("Formato")
    grid.addWidget(labels["Calidad de procesamiento"],2,0)
    grid.addWidget(sep.quality,2,1)
    grid.addWidget(labels["Formato de exportación"],2,2)
    grid.addWidget(sep.export_fmt,2,3,1,2)
    destination_label=next(w for w in widgets if isinstance(w,QLabel) and "carpeta" in w.text().lower() or isinstance(w,QLabel) and "guardar las pistas" in w.text().lower())
    destination_label.setText("Destino")
    grid.addWidget(destination_label,3,0)
    grid.addWidget(sep.dest_edit,3,1,1,3)
    grid.addWidget(folder_button,3,4)
    sep.import_info.hide()
    sep.file_edit.setToolTip("Selecciona una pista para separar. "
        "Admite arrastrar y soltar; formato y duración se describen al cargar.")
    for control in (sep.file_edit,sep.profile,sep.dest_edit,
                    sep.quality,sep.export_fmt):
        control.setMinimumWidth(0)
        control.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    grid.setColumnStretch(1,3)
    grid.setColumnStretch(3,2)
    entry.body.addWidget(frame,0)
    entry.body.addWidget(items[4].widget(),0) # preescucha original
    sep.source_preview.set_compact(True)
    sep.source_preview.detail.hide()
    root.addWidget(entry,0)

    run=SectionCard("02 · PROCESAR","wave")
    run.body.setContentsMargins(8,4,8,5)
    run.body.setSpacing(2)
    # Control line has real Separar / Cancelar / elapsed
    _push(run.body,items[5])
    _push(run.body,items[6])
    _push(run.body,items[7])
    sep.progress_label.setMaximumHeight(22)
    sep.progress.setMaximumHeight(12)
    root.addWidget(run,0)

    # Reuse the original button row; two actions previously hidden by
    # workspace logic are made accessible again, without duplicating.
    tools=SectionCard("03 · DESTINOS Y HERRAMIENTAS","folder")
    tools.body.setContentsMargins(8,4,8,6)
    tools.body.setSpacing(3)
    buttons=items[11].layout()
    sep.mix_button.setVisible(True)
    sep.mix_button.setText("Mezclador")
    sep.open_results_button.setVisible(True)
    sep.open_results_button.setText("Abrir stems")
    sep.midi_button.setText("Audio a MIDI")
    for b in (sep.mix_button,sep.open_results_button,sep.midi_button):
        b.setMinimumWidth(0)
    # All five existing actions in one row; descriptive tooltips retain
    # their full meaning when visible text is shortened.
    sep.load_previous_button.setVisible(True)
    sep.library_button.setVisible(True)
    sep.load_previous_button.setText("Anteriores")
    sep.load_previous_button.setToolTip(
        "Cargar una carpeta de pistas separadas en una tarea anterior.")
    sep.library_button.setText("Biblioteca")
    sep.library_button.setToolTip(
        "Abrir la biblioteca de extracciones del proyecto.")
    sep.load_previous_button.setMaximumWidth(104)
    sep.library_button.setMaximumWidth(104)
    sep.load_previous_button.setMinimumWidth(0)
    sep.library_button.setMinimumWidth(0)
    # Both were hidden by the legacy workspace. Reuse their existing
    # click connections rather than creating a second implementation.
    buttons.insertWidget(buttons.count()-1,sep.load_previous_button)
    buttons.insertWidget(buttons.count()-1,sep.library_button)
    tools.body.addLayout(buttons)
    root.addWidget(tools,0)

    # The legacy table/preview are redundant with TaskResults on the right.
    # Keep objects present and connected (the processing code refers to
    # them), but do not let hidden table stretch create tall empty space.
    hidden=QWidget(inner)
    hidden.setObjectName("separationLegacyDetails")
    hidden.setVisible(False)
    hidden_layout=QVBoxLayout(hidden)
    hidden_layout.setContentsMargins(0,0,0,0)
    for index in (8,9,10):
        _push(hidden_layout,items[index])
    hidden.setVisible(False)
    sep._legacy_details=hidden

    # Activity toggles without adding permanent height. A few lines of
    # logs are useful while processing; the user can expand for diagnosis.
    activity=SectionCard("04 · ACTIVIDAD DEL MOTOR","info")
    activity.body.setContentsMargins(6,2,6,5)
    activity.body.setSpacing(2)
    sep.log.setMinimumHeight(0)
    sep.log.setMaximumHeight(100)
    sep.log.setFixedHeight(74)
    sep.log.setVisible(False)
    activity.body.addWidget(sep.log)
    activity.body.addWidget(items[14].widget()) if False else None
    toggle=QPushButton("Mostrar registro ▾",activity)
    toggle.setToolTip("Mostrar/ocultar mensajes técnicos del separador. "
                      "Cuando el registro está plegado no se pierden mensajes.")
    toggle.setMaximumWidth(165)
    def change():
        on=not sep.log.isVisible()
        sep.log.setVisible(on)
        toggle.setText("Ocultar registro ▴" if on else "Mostrar registro ▾")
    toggle.clicked.connect(change)
    activity.body.insertWidget(0,toggle)
    root.addWidget(activity,0)
    items[14].widget().hide()
    # On compact screens the log is shown in a separate inspector, not
    # permanently consuming 80 px at the cost of readable controls.
    log_button=QPushButton("Registro",tools)
    log_button.setMaximumWidth(94)
    log_button.setToolTip("Consultar mensajes de diagnóstico. "
        "No detiene la separación ni cambia archivos.")
    def inspect_log():
        motor=getattr(sep,"motor_dialog",None)
        if motor is not None:
            motor.show()
            motor.raise_()
            motor.activateWindow()
            return
        if sep.height()>=620:
            if not activity.isVisible():
                activity.show()
            toggle.click()
            return
        dialog=QDialog(sep)
        dialog.setWindowTitle("Actividad del motor · Separación")
        dialog.setMinimumSize(570,290)
        dlg_layout=QVBoxLayout(dialog)
        display=QPlainTextEdit(dialog)
        display.setReadOnly(True)
        dlg_layout.addWidget(display)
        def update_text():
            if not display.isVisible():return
            value=sep.log.toPlainText()
            if display.toPlainText()!=value:
                display.setPlainText(value)
                display.verticalScrollBar().setValue(
                    display.verticalScrollBar().maximum())
        updater=QTimer(dialog)
        updater.setInterval(600)
        updater.timeout.connect(update_text)
        updater.start()
        update_text()
        dialog.show()
        sep._log_inspector=dialog
    log_button.clicked.connect(inspect_log)
    buttons.insertWidget(buttons.count()-1,log_button)
    sep._activity_card=activity
    sep._subtitle=subtitle
    sep._setup_frame=frame
    class _Adaptive(QObject):
        def eventFilter(self,obj,event):
            if obj is sep and event.type()==QEvent.Resize:
                QTimer.singleShot(0,self.update)
            return False
        def update(self):
            import shiboken6
            if not shiboken6.isValid(sep):return
            tight=sep.height()<620
            heading.setVisible(not tight)
            subtitle.setVisible(not tight)
            activity.setVisible(not tight)
    adapter=_Adaptive(sep)
    sep._adaptive_separation_layout=adapter
    sep.installEventFilter(adapter)
    QTimer.singleShot(0,adapter.update)
    root.addStretch(1)

    # Right side: results list grows when there are stems, not when empty.
    viewport=next((c for c in results.findChildren(QScrollArea)
            if c.widget() is results.container),None)
    if viewport:
        viewport.setMinimumHeight(100)
        viewport.setMaximumHeight(250)
        viewport.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        viewport.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    results.layout().setContentsMargins(8,6,8,7)
    results.layout().setSpacing(4)
    results.preview.set_compact(True)
    results.preview.detail.hide()
    results.save_selected.setText("Selección")
    results.new_task.setText("Descartar")
    results.save_selected.setToolTip("Guardar las pistas marcadas con nombre y destino elegibles.")
    results.new_task.setToolTip("Descartar la tarea actual tras confirmar; "
        "los originales y resultados definitivos no se borran.")
    # Remove repeated title: outer SectionCard already shows it.
    for lbl in results.findChildren(QLabel):
        if lbl.text()=="PISTAS SEPARADAS · REVISAR ANTES DE GUARDAR":
            lbl.hide()
    for lbl in results.container.findChildren(QLabel,"moduleEmptyState"):
        lbl.setMinimumHeight(82)
    # Card sizes: 68 % working area, 32 % preview/approval, but never too narrow.
    splitter.setStretchFactor(0,7)
    splitter.setStretchFactor(1,4)
    splitter.setSizes([810,460])
    return True
