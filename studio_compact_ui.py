"""Distribución compacta real de la tarjeta Grabadora.

Reubica los widgets ya conectados: no crea botones falsos ni sustituye
operaciones. Los controles que no caben en una fila se agrupan por tarea.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,QVBoxLayout,QGridLayout,QLabel,QWidget,QSizePolicy
)

def compact_recorder(main,card,layout):
    widgets=[]
    while layout.count():
        widgets.append(layout.takeAt(0))
    # Estructura original, auditada: preset, reloj, cuatro títulos/campos,
    # directorio, transporte, acciones, resultado, escucha y accesos rápidos.
    assert len(widgets)==18,len(widgets)
    presets=widgets[0].widget()
    assert presets is main.record_presets
    assert widgets[2].layout() is not None
    assert widgets[4].widget() is main.format
    assert widgets[6].widget() is main.capture_rate
    assert widgets[8].widget() is main.file_prefix
    assert widgets[10].layout() is not None
    assert widgets[11].layout() is not None
    assert widgets[12].layout() is not None
    assert widgets[13].widget() is main.current_output
    assert widgets[14].widget() is main.record_preview

    layout.setContentsMargins(7,6,7,7)
    layout.setSpacing(3)
    layout.addWidget(presets,0)
    presets.setMaximumHeight(35)

    clock_row=QHBoxLayout()
    clock_row.setContentsMargins(0,0,0,0)
    clock_row.setSpacing(6)
    name=widgets[1].widget()
    name.setObjectName("section")
    clock_row.addWidget(name)
    clock_row.addStretch()
    # Relocalizar reloj y estado vinculados al motor original.
    main.clock.setMaximumHeight(31)
    main.clock.setStyleSheet("font-size:21px;font-weight:750;color:#85f0ff;")
    main.rec_hint.setMaximumHeight(24)
    main.rec_hint.setText("Preparado")
    clock_row.addWidget(main.clock)
    layout.addLayout(clock_row,0)

    form=QGridLayout()
    form.setHorizontalSpacing(5)
    form.setVerticalSpacing(3)
    form.setContentsMargins(0,0,0,0)
    entries=[
      ("Formato",main.format),
      ("Calidad",main.capture_rate),
      ("Nombre",main.file_prefix)
    ]
    for line,(title,control) in enumerate(entries):
        caption=QLabel(title,card)
        caption.setObjectName("homeLabel")
        caption.setMinimumWidth(57)
        form.addWidget(caption,line,0)
        form.addWidget(control,line,1)
        control.setMinimumWidth(0)
    folder_title=QLabel("Carpeta",card)
    folder_title.setObjectName("homeLabel")
    form.addWidget(folder_title,3,0)
    folder_row=widgets[10].layout()
    folder_row.setSpacing(4)
    form.addLayout(folder_row,3,1)
    layout.addLayout(form,0)

    record_row=widgets[11].layout()
    record_row.setSpacing(4)
    # El botón de opciones del reproductor pasa junto a Grabar, para
    # que la preescucha sea una sola fila y mantenga ruta/volumen accesibles.
    preview=main.record_preview
    transport_header=preview.layout().itemAt(0).layout()
    for j in range(transport_header.count()):
        widget=transport_header.itemAt(j).widget()
        if widget is not None and widget is not preview.options_button:
            widget.hide()
    record_row.addWidget(preview.options_button)
    layout.addLayout(record_row,0)
    actions_row=widgets[12].layout()
    actions_row.setSpacing(4)
    layout.addLayout(actions_row,0)
    main.current_output.setMaximumHeight(26)
    main.current_output.setToolTip("Ruta y estado de la última toma finalizada.")
    layout.addWidget(main.current_output,0)
    preview.setMinimumHeight(0)
    layout.addWidget(preview,0)
    for index in (15,16):
        row=widgets[index].layout()
        row.setSpacing(4)
        layout.addLayout(row,0)
    # El recordatorio duplicado se conserva en su ayuda, no ocupa 20 px.
    for index in (3,5,7,9,17):
        item=widgets[index]
        if item.widget():
            item.widget().hide()
    main.rec_hint.setToolTip(
        "Estado de la grabación: preparado, grabando, finalizando o error.")
    # Mantener el estado visual en una sola línea al lado del reloj.
    clock_row.addWidget(main.rec_hint)
    # Liberar el antiguo contenedor temporal del reloj (ya vacío).
    time_area=widgets[2].layout()
    while time_area.count():
        time_area.takeAt(0)
    return card
