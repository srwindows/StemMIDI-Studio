"""Completar el módulo de batería SIN esconder ninguno de los cinco paneles.

Extiende la mesa compacta con los controles originales de mezcla, seis ondas
con zoom/escucha, lista de resultados, editor MIDI y audio y motor MDX23C.
Cada par etiqueta-control vive en el MISMO layout sin columnas vacías.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QHBoxLayout,QVBoxLayout,
                               QGridLayout,QScrollArea,QSizePolicy,QPushButton)


def _visible_original_section(studio,root,index):
    box=studio.dashboard_sections[index]
    old=studio.dashboard_content.layout()
    old.removeWidget(box)
    box.setParent(root)
    box.setMinimumHeight(0)
    box.setMaximumHeight(16777215)
    box.layout().setContentsMargins(3,2,3,2)
    box.layout().setSpacing(2)
    caption=box.layout().itemAt(0).widget()
    caption.setFixedHeight(20)
    caption.setStyleSheet('font-size:11px;font-weight:750;color:#b2eaff;padding:0 5px;background:#052552;')
    page=box.layout().itemAt(1).widget()
    page.setMinimumHeight(0)
    page.setMaximumHeight(16777215)
    page.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    box.show()
    page.show()
    return box,page


def _attach_editor_label_to_own_slider(studio):
    page=studio.dashboard_sections[2].layout().itemAt(1).widget()
    lay=page.layout()
    original=None
    position=None
    for i in range(lay.count()):
        item=lay.itemAt(i)
        if isinstance(item.layout(),QGridLayout):
            original=item.layout();position=i;break
    assert original is not None
    fields=[]
    for row in range(original.rowCount()):
        for col in range(0,original.columnCount(),2):
            a=original.itemAtPosition(row,col)
            b=original.itemAtPosition(row,col+1)
            if a and b and isinstance(a.widget(),QLabel) and b.widget():
                fields.append((a.widget(),b.widget()))
    assert len(fields)==len(studio.editor_controls),(len(fields),len(studio.editor_controls))
    for name,control in fields:
        original.removeWidget(name)
        original.removeWidget(control)
    lay.removeItem(original)
    original.deleteLater()
    tight=QGridLayout()
    tight.setContentsMargins(0,0,0,0)
    tight.setHorizontalSpacing(8)
    tight.setVerticalSpacing(4)
    for col in range(3):tight.setColumnStretch(col,1)
    for index,(label,control) in enumerate(fields):
        pair=QWidget(page)
        horizontal=QHBoxLayout(pair)
        horizontal.setContentsMargins(0,0,0,0)
        horizontal.setSpacing(4)
        label.setParent(pair)
        label.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        label.setFixedWidth(label.fontMetrics().horizontalAdvance(label.text())+6)
        control.setParent(pair)
        control.setMinimumWidth(115)
        control.setMaximumWidth(157)
        horizontal.addWidget(label)
        horizontal.addWidget(control,1)
        horizontal.addStretch(1)
        tight.addWidget(pair,index//3,index%3)
    lay.insertLayout(position,tight)
    # La indicación «Sin audio seleccionado» junto al selector, no en el
    # extremo opuesto. Conservamos el mismo objeto y las mismas señales.
    source_row=lay.itemAt(0).layout()
    source_label=next(x.widget() for x in (source_row.itemAt(i)
        for i in range(source_row.count())) if isinstance(x.widget(),QLabel)
        and x.widget() is not studio.editor_summary)
    for obj in (source_label,studio.edit_source,studio.editor_summary):
        source_row.removeWidget(obj)
    while source_row.count():
        item=source_row.takeAt(0)
        if item.widget() is not None:item.widget().hide()
    source_label.setFixedWidth(source_label.fontMetrics().horizontalAdvance(source_label.text())+5)
    studio.edit_source.setFixedWidth(196)
    studio.editor_summary.setMaximumWidth(195)
    source_row.setSpacing(5)
    source_row.addWidget(source_label)
    source_row.addWidget(studio.edit_source)
    source_row.addSpacing(9)
    source_row.addWidget(studio.editor_summary)
    source_row.addStretch(1)
    # La onda ocupa el área horizontal entre selector y controles, sin
    # estirar verticalmente el bloque ni empujar los deslizantes abajo.
    studio.big_wave.setMinimumHeight(49)
    studio.big_wave.setMaximumHeight(49)
    studio.big_wave.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    lay.setStretch(lay.indexOf(studio.big_wave),0)
    studio._complete_editor_pairs=fields


def _attach_seq_labels(studio):
    page=studio.dashboard_sections[3].layout().itemAt(1).widget()
    lay=page.layout()
    toolbar=lay.itemAt(0).layout()
    assert isinstance(toolbar,QHBoxLayout)
    controls=(studio.seq_bpm,studio.seq_velocity,studio.seq_swing,studio.seq_bars)
    pairs=[]
    for control in controls:
        i=next(i for i in range(toolbar.count()) if toolbar.itemAt(i).widget() is control)
        label=toolbar.itemAt(i-1).widget()
        assert isinstance(label,QLabel)
        pairs.append((label,control))
    for label,control in pairs:
        toolbar.removeWidget(label);toolbar.removeWidget(control)
    while toolbar.count():
        item=toolbar.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
    for k,(label,control) in enumerate(pairs):
        pair=QWidget(page)
        h=QHBoxLayout(pair)
        h.setContentsMargins(0,0,0,0)
        h.setSpacing(3)
        label.setParent(pair)
        label.setFixedWidth(label.fontMetrics().horizontalAdvance(label.text())+4)
        label.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        control.setParent(pair)
        control.setMinimumWidth(0)
        if k<3:control.setMaximumWidth((118,133,111)[k])
        else:control.setFixedWidth(58)
        h.addWidget(label)
        h.addWidget(control,1)
        toolbar.addWidget(pair)
        if k<3:toolbar.addSpacing(15)
    toolbar.addStretch(1)
    lay.setStretch(1,0)
    studio._complete_seq_pairs=pairs



def _spread_engine_controls(panel):
    root=panel.layout()
    old=panel.grid
    parts={key:panel.sliders[key].parentWidget().parentWidget()
           for key in ('overlap','batch_size','sample_rate','bit_depth')}
    for pair in parts.values():old.removeWidget(pair)
    root.removeItem(old)
    old.deleteLater()
    # Conservar el desplegable, el botón y la etiqueta reales del formato.
    fmtline=None
    for i in range(root.count()):
        item=root.itemAt(i)
        if isinstance(item.layout(),QHBoxLayout):fmtline=item.layout();break
    assert fmtline is not None
    fmt_label=next(fmtline.itemAt(i).widget() for i in range(fmtline.count())
                   if isinstance(fmtline.itemAt(i).widget(),QLabel))
    for widget in (fmt_label,panel.output_format,panel.reset):
        fmtline.removeWidget(widget)
    root.removeItem(fmtline)
    fmtline.deleteLater()
    grid=QGridLayout()
    grid.setContentsMargins(0,0,0,0)
    grid.setHorizontalSpacing(20)
    grid.setVerticalSpacing(4)
    grid.setColumnStretch(0,1)
    grid.setColumnStretch(1,1)
    panel.grid=grid
    root.insertLayout(0,grid)
    for key,row,col in (('overlap',0,0),('batch_size',0,1),
                        ('sample_rate',1,0),('bit_depth',1,1)):
        pair=parts[key]
        label=next(item for item in pair.findChildren(QLabel)
                   if item.parent() is pair)
        label.setStyleSheet('font-size:12px;color:#d8eeff;')
        label.setFixedWidth(label.fontMetrics().horizontalAdvance(label.text())+5)
        slider=panel.sliders[key]
        slider.setFixedWidth(95)
        slider.setFixedHeight(18)
        panel.values[key].setFixedWidth(46)
        field=slider.parentWidget()
        field.setMaximumWidth(150)
        pair.setMaximumWidth(16777215)
        pair.setMinimumWidth(0)
        pair.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        grid.addWidget(pair,row,col,Qt.AlignLeft|Qt.AlignVCenter)
    formatted=QWidget(panel)
    fmtrow=QHBoxLayout(formatted)
    fmtrow.setContentsMargins(0,0,0,0)
    fmtrow.setSpacing(5)
    fmt_label.setParent(formatted)
    fmt_label.setFixedWidth(fmt_label.fontMetrics().horizontalAdvance(fmt_label.text())+5)
    panel.output_format.setParent(formatted)
    panel.output_format.setFixedWidth(94)
    fmtrow.addWidget(fmt_label)
    fmtrow.addWidget(panel.output_format)
    fmtrow.addStretch(1)
    panel.reset.setParent(panel)
    panel.reset.setFixedHeight(22)
    panel.reset.setMaximumWidth(150)
    grid.addWidget(formatted,2,0,Qt.AlignLeft)
    grid.addWidget(panel.reset,2,1,Qt.AlignLeft)
    root.setContentsMargins(10,15,8,4)
    root.setSpacing(0)
    panel.setFixedHeight(114)
    panel._spread_fields=parts
    panel._spread_format=formatted


def install(main):
    mod=main.drum_module
    studio=mod.studio
    bridge=main.advanced_tab_parity[main.studio_home.drum_card]
    desk=main.drum_flat_workspace
    grid=bridge.drum_dense_layout
    dense=bridge.drum_dense_widget

    # Los dos paneles existentes deben disponer de su ALTURA NATURAL; el
    # espacio extra se entrega al mezclador y resultados, NO al editor/seq.
    _attach_editor_label_to_own_slider(studio)
    _attach_seq_labels(studio)
    # Repartir las dieciséis posiciones MIDI a lo ancho del módulo. La
    # columna 17 heredada se quedaba con TODO el espacio sobrante.
    seqpage=studio.dashboard_sections[3].layout().itemAt(1).widget()
    for item_index in range(seqpage.layout().count()):
        candidate=seqpage.layout().itemAt(item_index).layout()
        if isinstance(candidate,QGridLayout):
            candidate.setColumnStretch(0,0)
            candidate.setColumnStretch(17,0)
            for row in range(7):
                slot=candidate.itemAtPosition(row,0)
                if slot is not None and isinstance(slot.widget(),QLabel):
                    caption=slot.widget()
                    caption.setFixedWidth(75)
                    caption.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            for column in range(1,17):candidate.setColumnStretch(column,1)
            break
    # Distribución equilibrada en DOS columnas y TRES filas del mismo panel
    # MDX23C. La versión anterior limitaba cada pareja a ~150 px y obligaba
    # a cuatro valores a apelotonarse en la esquina superior.
    panel=bridge.drum_engine_settings
    _spread_engine_controls(panel)
    # El inspector conserva las tres bandas EQ y los tres botones.
    inspector=studio.inspector
    inspector.setFixedHeight(84)
    inspector.wave.setFixedHeight(24)
    inspector.empty_wave.setFixedHeight(24)
    # La mesa superior gana espacio sin desplazar los controles inferiores.
    grid.setRowStretch(0,0)
    grid.setRowStretch(1,0)
    grid.setRowStretch(2,1)
    grid.setRowStretch(3,0)
    grid.setColumnStretch(0,51)
    grid.setColumnStretch(1,49)

    # Reubicar el reproductor (no clonarlo): permanece visible al pie.
    grid.removeWidget(mod.preview)
    grid.removeWidget(mod.full_presets)
    grid.addWidget(mod.preview,3,0)
    grid.addWidget(mod.full_presets,3,1)

    # Mesa de mezcla original, los seis canales con fader real, panorama,
    # VU, onda, M/S y transportes, MÁS exportación y presets reales.
    mixer,mixer_page=_visible_original_section(studio,dense,1)
    studio.console_canvas.setFixedHeight(235)
    for strip in studio.mixer_rows.values():
        strip.setMinimumWidth(82)
        strip.setMaximumWidth(16777215)
        strip.setFixedHeight(232)
        strip.wave.setFixedHeight(24)
        strip.empty_wave.setFixedHeight(24)
        strip.fader.setMinimumHeight(72)
        strip.fader.setMaximumHeight(86)
        strip.meter.setMinimumHeight(70)
        strip.meter.setMaximumHeight(95)
        strip.layout().setContentsMargins(4,3,4,3)
        strip.layout().setSpacing(2)
    studio.mixer_content.setMinimumHeight(0)
    studio.mixer_content.setMaximumHeight(16777215)
    studio.mixer_content.layout().setContentsMargins(3,2,3,2)
    studio.mixer_content.layout().setSpacing(2)
    studio.mixer_presets.setMaximumHeight(27)
    studio.mixer_presets.layout().setContentsMargins(2,0,2,0)
    studio.mixer_title.setStyleSheet('font-size:11px;font-weight:750;color:#c0f4ff;')
    studio.render_mix_btn.setMaximumWidth(172)
    studio.render_mix_btn.setFixedHeight(22)
    studio.mixer_scroll.setFixedHeight(297)
    studio.mixer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    studio.mixer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    mixer_page.setMinimumHeight(0)
    mixer.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    grid.addWidget(mixer,2,1)

    # Seis ondas originales Y tabla de archivos existentes: ambos visibles,
    # lado a lado, sin sustituirlos por un texto ni hacerlos desaparecer.
    bottom=QWidget(dense)
    bottom.setObjectName('drumWavesResultsPanel')
    columns=QHBoxLayout(bottom)
    columns.setContentsMargins(0,0,0,0)
    columns.setSpacing(4)
    waves,wave_page=_visible_original_section(studio,bottom,0)
    results,result_page=_visible_original_section(studio,bottom,4)
    waves.setMinimumWidth(0)
    results.setMinimumWidth(0)
    results.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    columns.addWidget(waves,1)
    columns.addWidget(results,1)
    wave_page.layout().setContentsMargins(2,1,2,1)
    wave_page.layout().setSpacing(2)
    for row in studio.track_rows.values():
        row.setMinimumHeight(25)
        row.setMaximumHeight(30)
        row.wave.setMinimumHeight(19)
        row.wave.setMaximumHeight(22)
        row.layout().setContentsMargins(2,1,2,1)
        row.layout().setSpacing(3)
    wave_scroll=wave_page.findChild(QScrollArea)
    assert wave_scroll is not None
    wave_scroll.setFixedHeight(213)
    wave_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    wave_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    studio.reload.setFixedHeight(20)
    studio.reload.setMaximumWidth(120)
    results_page=result_page
    explanation=results_page.layout().itemAt(0).widget()
    if isinstance(explanation,QLabel):
        explanation.setWordWrap(True)
        explanation.setMinimumWidth(0)
        explanation.setMaximumHeight(29)
        explanation.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        explanation.setText('Seis stems reales + mezclas y ediciones guardadas.')
        explanation.setToolTip('Archivos auténticos de esta tarea: seis stems del modelo y ediciones o mezclas generadas explícitamente.')
    results_page.layout().setContentsMargins(2,1,2,1)
    results_page.layout().setSpacing(2)
    result_table=mod.result_table
    result_table.setMinimumHeight(170)
    result_table.setMaximumHeight(16777215)
    grid.addWidget(bottom,2,0)

    # Evitar 'widgets invisibles' en el estudio anterior: los cinco paneles
    # son ahora hijos visibles de la mesa (ninguno fue destruido).
    for i in range(5):
        section=studio.dashboard_sections[i]
        assert section.parent() in (dense,bottom),i
        section.show()
    main.drum_complete_workspace=dict(mixer=mixer,waves=waves,results=results,
        editor=studio.dashboard_sections[2],sequencer=studio.dashboard_sections[3],
        bridge=bridge,grid=grid,desk=desk)
    return main.drum_complete_workspace
