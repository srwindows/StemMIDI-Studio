"""Diseño unificado del Estudio Vocal. Una superficie, un motor, cero scroll.

Las operaciones, resultados y controles usan VocalHomeStudio y VocalTuneModule
existentes. No se duplican ni se sustituyen señales ni se ocultan funciones.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
    QScrollArea, QSizePolicy, QFrame, QComboBox, QAbstractItemView
)


def _compact_studio(studio):
    if getattr(studio, "_vocal_dense_applied", False):
        return
    body=studio.layout()
    assert isinstance(body,QVBoxLayout), "El estudio vocal ha cambiado de estructura"
    parts=[body.takeAt(0) for _ in range(body.count())]
    assert len(parts)==9, "Estructura inesperada del estudio vocal: "+str(len(parts))
    header=parts[0].layout()
    path=parts[1].widget()
    presets=parts[2].widget()
    toolbar=parts[3].layout()
    tabs=parts[4].widget()
    feedback=parts[5].widget()
    versions=parts[6].layout()
    results=parts[7].widget()
    bottom=parts[8].layout()
    assert header and path is studio.source_path
    assert presets is studio.presets and tabs is studio.tabs
    assert feedback is studio.feedback and results is studio.results
    assert toolbar and versions and bottom

    body.setContentsMargins(5,3,5,4)
    body.setSpacing(3)
    studio.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)

    # Una única línea de fuente: el nombre no extiende el ancho del desplegable.
    header.setSpacing(5)
    studio.source_combo.setMinimumWidth(0)
    studio.source_combo.setMaximumWidth(215)
    studio.source_combo.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
    header.setStretch(1,0)
    for widget,max_width in ((studio.import_button,112),
                             (studio.update_button,90)):
        widget.setMaximumWidth(max_width)
    path.setMaximumWidth(215)
    path.setMinimumWidth(0)
    path.setTextInteractionFlags(Qt.TextSelectableByMouse)
    path.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
    header.addWidget(path,0)
    header.addStretch(1)
    body.addLayout(header)

    # Una barra de presets de tamaño natural y una barra de acciones compacta.
    presets.setMinimumHeight(0)
    presets.setMaximumHeight(37)
    presets.layout().setContentsMargins(4,1,4,1)
    presets.layout().setSpacing(4)
    presets.choices.setMinimumWidth(0)
    presets.choices.setMaximumWidth(190)
    presets.name.setMinimumWidth(0)
    presets.name.setMaximumWidth(170)
    presets.save_btn.setMaximumWidth(82)
    presets.delete_btn.setMaximumWidth(76)
    presets.message.setMaximumWidth(95)
    body.addWidget(presets,0)

    toolbar.setSpacing(4)
    for index in range(toolbar.count()):
        w=toolbar.itemAt(index).widget()
        if not isinstance(w,QPushButton): continue
        original=w.text()
        mapping={
          "↶ Deshacer ajustes":"↶ Deshacer",
          "↷ Rehacer ajustes":"↷ Rehacer",
          "Aplicar análisis":"Aplicar análisis",
        }
        w.setToolTip(original)
        w.setText(mapping.get(original,original))
        w.setMaximumHeight(29)
        w.setMinimumWidth(0)
        w.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Fixed)
    body.addLayout(toolbar)

    # Área principal en dos columnas. Todas las pestañas siguen siendo
    # las seis con los mismos controles y valores.
    columns=QHBoxLayout()
    columns.setSpacing(7)
    left=QVBoxLayout()
    right=QVBoxLayout()
    left.setSpacing(3)
    right.setSpacing(4)
    tabs.setMinimumHeight(150)
    tabs.setMaximumHeight(263)
    tabs.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    left.addWidget(tabs,0,Qt.AlignTop)
    feedback.setMaximumHeight(32)
    feedback.setWordWrap(False)
    left.addWidget(feedback,0)
    left.addStretch(1)

    # Preescucha A/B y archivos conservan sus acciones originales.
    versions.setSpacing(3)
    for i in range(versions.count()):
        w=versions.itemAt(i).widget()
        if isinstance(w,QLabel) and w.text()=="TOMAS PROCESADAS":
            w.setText("RESULTADOS")
            w.setMaximumWidth(98)
        elif isinstance(w,QPushButton):
            w.setMaximumWidth(96)
            w.setMaximumHeight(28)
    right.addLayout(versions,0)
    results.setMinimumHeight(76)
    results.setMaximumHeight(210)
    results.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    right.addWidget(results,1)

    # Recolocar el estado fuera de la fila de botones para que no empuje
    # 'Guardar', 'Enviar a Resultados' ni 'Exportar' fuera de la ventana.
    bottom.removeWidget(studio.session_status)
    studio.session_status.setMaximumHeight(26)
    studio.session_status.setWordWrap(False)
    for i in range(bottom.count()):
        w=bottom.itemAt(i).widget()
        if not isinstance(w,QPushButton):continue
        original=w.text()
        replacements={
          "Guardar ajustes del proyecto":"Guardar ajustes",
          "Guardar voz en Resultados":"Guardar voz",
          "Exportar archivo…":"Exportar…",
        }
        w.setToolTip(original)
        w.setText(replacements.get(original,original))
        w.setMinimumWidth(0)
        w.setMaximumWidth(115)
        w.setMaximumHeight(28)
        w.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Fixed)
    bottom.setSpacing(4)
    right.addLayout(bottom,0)
    right.addWidget(studio.session_status,0)
    columns.addLayout(left,70)
    columns.addLayout(right,30)
    body.addLayout(columns,1)
    studio._vocal_dense_applied=True
    studio._vocal_dense_sections=(left,right)
    studio._vocal_dense_original_items=parts


def install(main):
    if getattr(main,"_vocal_dense_installed",False):return True
    mod=main.vocal_module
    bridge=main.advanced_tab_parity[main.studio_home.vocal_card]
    assert bridge.kind=="vocal" and bridge.docked
    studio=bridge.expanded.vocal_studio
    assert studio is not None
    _compact_studio(studio)

    # El antiguo contenedor de controles avanzados generaba la primera
    # barra de scroll. Se usa su MISMO contenido directamente, sin QScrollArea.
    host_layout=bridge.host.layout()
    bridge.scroll.takeWidget()
    host_layout.removeWidget(bridge.scroll)
    bridge.scroll.hide()
    bridge.content.setParent(bridge.host)
    host_layout.insertWidget(1,bridge.content,1)
    bridge.content_layout.setContentsMargins(1,0,1,0)
    bridge.content_layout.setSpacing(0)
    bridge.extra.setMinimumHeight(0)
    bridge.extra.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    host_layout.setContentsMargins(2,2,2,2)
    host_layout.setSpacing(0)
    heading=host_layout.itemAt(0).layout()
    if heading:
        for i in range(heading.count()):
            w=heading.itemAt(i).widget()
            if w is not None:w.hide()
    bridge.host.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)

    # Los controles repetidos del módulo original eran la segunda pantalla
    # desplazable. Permanecen vivos, con su motor, señales y estados, pero
    # no se representan dos veces. VocalHomeStudio contiene las mismas
    # funciones reales de fuente, afinación, presets, FX, resultados y export.
    content=mod.content_scroll.widget()
    layout=content.layout()
    assert isinstance(layout,QVBoxLayout) and layout.count()>=5
    for i in range(layout.count()):
        item=layout.itemAt(i)
        widget=item.widget()
        if widget is None:
            child=item.layout()
            if child is not None:
                for j in range(child.count()):
                    w=child.itemAt(j).widget()
                    if w is not None:w.hide()
        elif widget is not bridge.host:
            widget.hide()

    layout.setContentsMargins(2,1,2,2)
    layout.setSpacing(0)
    layout.setAlignment(Qt.AlignTop)
    mod.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    mod.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    mod.content_scroll.setFrameShape(QFrame.NoFrame)
    mod.content_scroll.setWidgetResizable(True)

    # La vista avanzada ya no aporta una barra propia. La barra que usaba
    # antes era solo ornamental y ahora quedaría vacía; no se usa.
    bridge.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    bridge.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    # No permitir la altura fija de 630px ni paneles que se estiren hacia
    # abajo dejando huecos vacíos a medio camino.
    studio.setMaximumHeight(415)
    studio.setMinimumHeight(0)
    main._vocal_dense_installed=True
    main._vocal_dense_workspace=studio
    QTimer.singleShot(0,studio.refresh)
    return True
