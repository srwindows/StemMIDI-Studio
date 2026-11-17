"""Audio a MIDI, superficie sin dos desplazamientos anidados.

Solo recoloca instancias QWidget originales. Ningún callback de transcripción,
modelo, presets, archivos, escuchas, exportación ni ventana flotante se duplica.
"""
from __future__ import annotations
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QHBoxLayout,QVBoxLayout,
    QGridLayout,QScrollArea,QSizePolicy,QPushButton,QListWidget,QLayout,QFormLayout)

class MidiCompactBridge:
    def __init__(self,main):
        self.main=main
        self.converter=main.workbench.converter
        self.bridge=main.advanced_tab_parity[main.studio_home.midi_card]
        self.exp=self.bridge.expanded
        self.browser=self.exp.midi_browser
        self.settings=self.exp.midi_settings
        self.original_extra_height=self.exp.extra.minimumHeight()
        self.original_browser_height=self.browser.minimumHeight()
        self.original_browser_policy=self.browser.sizePolicy()
        self.original_inventory_policies={x:x.sizePolicy() for x in (self.browser.stems,self.browser.drums,self.browser.midis)}
        self.original_sizes={x:(x.minimumHeight(),x.maximumHeight())
               for x in (self.browser.stems,self.browser.drums,self.browser.midis)}
        self.original_settings_grid=[]
        self.original_settings_grid_spacing=self.exp.midi_settings_grid.horizontalSpacing()
        self.docked=None
        self.preset=None
        self.extra_layout=self.exp.extra.layout()
        for i in range(self.extra_layout.count()):
            item=self.extra_layout.itemAt(i)
            if isinstance(item.layout(),QHBoxLayout):
                if any(item.layout().itemAt(j).widget() is self.exp.choice
                       for j in range(item.layout().count())):
                    self.preset=item.layout();break
        assert self.preset is not None

    def place(self,docked):
        if self.docked is docked:return
        self.docked=docked
        e=self.exp
        if docked:
            self.extra_layout.removeWidget(self.browser)
            self.extra_layout.removeWidget(self.settings)
            self.extra_layout.removeItem(self.preset)
            self.browser.setParent(self.stage)
            self.settings.setParent(self.right_top)
            self.left_top_layout.addWidget(self.browser,1)
            self.right_top_layout.insertWidget(0,self.settings)
            self.left_top_layout.addLayout(self.preset)
            self.browser.setMinimumHeight(0)
            self.browser.setMaximumHeight(265)
            # Listas Qt no pueden imponer su sizeHint horizontal de 250px
            # cada una: deben adaptarse al espacio disponible sin recortar.
            self.browser.layout().setContentsMargins(5,3,5,3)
            self.browser.layout().setSpacing(3)
            # El nombre IA y su desplegable NO pueden separarse cuando
            # el widget crece: la pareja mantiene su anchura natural.
            topline=self.browser.layout().itemAt(0).layout()
            ia_label=topline.itemAt(0).widget()
            ia_label.setFixedWidth(ia_label.fontMetrics().horizontalAdvance(ia_label.text())+5)
            self.browser.model.setMinimumWidth(0)
            self.browser.model.setMaximumWidth(194)
            topline.setStretch(1,0)
            if not getattr(self.browser,'_midi_grouped_row',False):
                topline.addStretch(1)
                self.browser._midi_grouped_row=True
            for inventory in (self.browser.stems,self.browser.drums,self.browser.midis):
                inventory.setMinimumHeight(0)
                inventory.setMaximumHeight(167)
                inventory.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Expanding)
            self.browser.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
            self.settings.setMinimumHeight(0)
            self.settings.setMaximumHeight(148)
            self.settings.layout().setContentsMargins(3,3,3,3)
            self.settings.layout().setSpacing(1)
            self.exp.midi_settings_grid.setHorizontalSpacing(4)
            e.extra.setMinimumHeight(0)
            self.bridge.host.hide()
            self.browser.show();self.settings.show()
            if hasattr(self,'library_dock'):
                self.library_dock.dock()
                self.settings_title.hide()
                QTimer.singleShot(0,self.resize_unified)
                QTimer.singleShot(0,self.converter._midi_update_tab_focus)

        else:
            if hasattr(self,'library_dock'):
                self.library_dock.undock()
                self.settings_title.show()
            self.left_top_layout.removeWidget(self.browser)
            self.right_top_layout.removeWidget(self.settings)
            self.left_top_layout.removeItem(self.preset)
            self.browser.setParent(e.extra)
            self.settings.setParent(e.extra)
            self.browser.show()
            self.settings.show()
            for idx in range(self.preset.count()):
                widget=self.preset.itemAt(idx).widget()
                if widget is not None:widget.show()
            self.extra_layout.insertWidget(1,self.browser,1)
            self.extra_layout.insertWidget(2,self.settings)
            self.extra_layout.insertLayout(3,self.preset)
            self.browser.setMinimumHeight(self.original_browser_height)
            self.browser.setMaximumHeight(16777215)
            self.browser.setSizePolicy(self.original_browser_policy)
            self.browser.layout().setContentsMargins(9,5,9,5)
            self.browser.layout().setSpacing(4)
            for inv,(mini,maxi) in self.original_sizes.items():
                inv.setMinimumHeight(mini);inv.setMaximumHeight(maxi)
                inv.setSizePolicy(self.original_inventory_policies[inv])
            self.settings.setMaximumHeight(16777215)
            self.settings.layout().setContentsMargins(10,5,10,7)
            self.settings.layout().setSpacing(3)
            self.exp.midi_settings_grid.setHorizontalSpacing(self.original_settings_grid_spacing)
            e.extra.setMinimumHeight(self.original_extra_height)
            self.bridge.host.show()


def _compact_cards(converter,cards):
    entry,params,process,activity=cards
    for card in cards:
        card.body.setContentsMargins(4,3,4,3)
        card.body.setSpacing(3)
        card.layout().setContentsMargins(0,0,0,0)
        card.layout().setSpacing(0)
        card.setMinimumHeight(0)
        card.setMaximumHeight(16777215)
        banner=card.layout().itemAt(0).widget()
        banner.hide()
        card.setStyleSheet('QFrame#studioCard {background:transparent; border:none;}')
    # Entrada real: lista de stems, selector y botón conservan conexiones.
    shelf=converter.stem_shelf.parentWidget()
    sl=shelf.layout()
    sl.setContentsMargins(4,2,4,2)
    sl.setSpacing(1)
    # El contenedor duplicaba 5 filas en vertical, dejando enorme margen a
    # la derecha. Repartir las 5 instancias originales en 2 columnas.
    header,inventory,actions,drop,info=[sl.takeAt(0) for _ in range(5)]
    columns=QHBoxLayout();columns.setSpacing(7)
    left=QVBoxLayout();left.setSpacing(1)
    left.addLayout(header.layout())
    left.addWidget(inventory.widget(),1)
    left.addLayout(actions.layout())
    right=QVBoxLayout();right.setSpacing(1)
    right.addWidget(drop.widget(),1)
    right.addWidget(info.widget())
    columns.addLayout(left,54)
    columns.addLayout(right,46)
    sl.addLayout(columns)
    shelf.setMinimumHeight(0);shelf.setMaximumHeight(136)
    converter.stem_drop.setMinimumHeight(47)
    converter.stem_drop.setMaximumHeight(68)
    # Los textos extensos tenían anchuras mínimas >400px en cada columna.
    # Guardamos sus descripciones completas como ayudas emergentes.
    title=header.layout().itemAt(0).widget()
    title.setToolTip(title.text())
    title.setText('STEMS DEL PROYECTO')
    converter.stem_drop.caption.setToolTip(converter.stem_drop.caption.text())
    converter.stem_drop.caption.setText('ARRASTRA AQUÍ UN STEM')
    converter.stem_drop.caption.setWordWrap(True)
    for button,text in ((converter.stem_listen,'▶ Escuchar'),
                        (converter.stem_use,'Usar stem →')):
        button.setToolTip(button.toolTip() or button.text())
        button.setText(text)
        button.setMaximumWidth(128)
    converter.stem_hint.setWordWrap(True)
    converter.stem_shelf.setMinimumHeight(0)
    converter.stem_shelf.setMaximumHeight(78)
    converter.presets.setMaximumHeight(29)
    entry.setMaximumHeight(180)
    # Parámetros: pestañas originales Fuente / Parámetros / Destino.
    tabs=converter.form_tabs
    tabs.setMinimumHeight(0)
    # Cada pestaña debe caber COMPLETA en el desplazamiento exterior.
    # Evitar un scroll adicional dentro de Fuente / Parámetros / Destino.
    parameters=tabs.widget(1).widget()
    for form in parameters.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
    def resize_tabs(index=None):
        index=tabs.currentIndex()
        page=tabs.widget(index).widget()
        page.layout().activate()
        required=page.sizeHint().height()+tabs.tabBar().sizeHint().height()+18
        tabs.setFixedHeight(max(165,required))
    tabs.currentChanged.connect(lambda _index:QTimer.singleShot(0,resize_tabs))
    resize_tabs()
    # Fuente: márgenes grandes de la antigua ventana desaprovechaban espacio.
    fuente=tabs.widget(0).widget()
    fuente.layout().setContentsMargins(5,4,5,4)
    fuente.layout().setSpacing(5)
    for i in range(fuente.layout().count()):
        widget=fuente.layout().itemAt(i).widget()
        if isinstance(widget,QFrame) and widget.objectName()=='panel':
            widget.layout().setContentsMargins(5,3,5,3)
            widget.layout().setSpacing(4)
    # Los textos informativos se mantienen íntegros en tooltip y se
    # muestran en una línea, nunca en un bloque de tres filas.
    converter.audio_info.setWordWrap(False)
    # Las etiquetas y desplegables de Fuente/Conversión forman una pareja;
    # el espacio restante va DESPUÉS, nunca entre ambos.
    source_frame=fuente
    for i in range(source_frame.layout().count()):
        layout=source_frame.layout().itemAt(i).layout()
        if not isinstance(layout,QHBoxLayout):continue
        if not any(layout.itemAt(j).widget() is converter.stem_count
                   for j in range(layout.count())):continue
        label=layout.itemAt(0).widget()
        label.setFixedWidth(label.fontMetrics().horizontalAdvance(label.text())+6)
        converter.stem_count.setMaximumWidth(305)
        layout.setStretch(1,0)
        layout.addStretch(1)
    row=process.body.itemAt(0).layout()
    if isinstance(row,QHBoxLayout):
        label=row.itemAt(0).widget()
        if isinstance(label,QLabel):
            label.setFixedWidth(label.fontMetrics().horizontalAdvance(label.text())+5)
        converter.stem_preview_choice.setMinimumWidth(0)
        converter.stem_preview_choice.setMaximumWidth(165)
        row.addStretch(1)
    for label,short in ((converter.tempo_quality,''),):
        if label is not None:label.setToolTip(label.text())
    for child in fuente.findChildren(QLabel):
        if child.text().startswith('Experimental:'):
            child.setToolTip(child.text())
            child.setText('Detección armónica experimental; depende del audio.')
            child.setWordWrap(False)
    # Procesamiento, exportación y tabla siguen visibles.
    converter.result.setMinimumHeight(0)
    converter.result.setMaximumHeight(82)
    converter.output_preview.set_compact(True)
    converter.output_preview.setMaximumHeight(69)
    converter.status.setMaximumHeight(38)
    converter.progress.setMaximumHeight(13)
    converter.chord_status.setMaximumHeight(30)
    # Log completo, sin un recuadro de 188 píxeles reservado a dos frases.
    converter.log.setMinimumHeight(0)
    converter.log.setMaximumHeight(48)
    converter.log.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    activity.body.setSpacing(2)
    activity.setMaximumHeight(120)
    for i in range(activity.body.count()):
        widget=activity.body.itemAt(i).widget()
        if isinstance(widget,QLabel) and widget.text().startswith('El MIDI contiene'):
            widget.setMaximumHeight(25)
            widget.setToolTip(widget.text())
    return resize_tabs


def _compact_results(main):
    """Resultados MIDI: dos filas de acciones, no una barra de 600px mínimos."""
    panel=main.workbench.midi_results
    root=panel.layout()
    buttons=(panel.save_all,panel.save_selected,panel.new_task,panel.edit_button)
    index=next(i for i in range(root.count())
               if root.itemAt(i).layout() is not None and
               any(root.itemAt(i).layout().itemAt(j).widget() is panel.save_all
                   for j in range(root.itemAt(i).layout().count())))
    old_controls=root.takeAt(index).layout()
    for btn in buttons:
        old_controls.removeWidget(btn)
        btn.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        btn.setMaximumWidth(16777215)
    new_controls=QGridLayout()
    new_controls.setContentsMargins(0,0,0,0)
    new_controls.setHorizontalSpacing(4)
    new_controls.setVerticalSpacing(4)
    for i,btn in enumerate(buttons):
        new_controls.addWidget(btn,i//2,i%2)
    new_controls.setColumnStretch(0,1)
    new_controls.setColumnStretch(1,1)
    root.insertLayout(index,new_controls)
    # El transporte y el dispositivo siguen accesibles mediante Opciones.
    panel.preview.set_compact(True)
    main.workbench.converter.source_preview.set_compact(True)


def install(main):
    converter=main.workbench.converter
    bridge=main.advanced_tab_parity[main.studio_home.midi_card]
    outer=converter.findChild(QScrollArea)
    assert outer is not None and outer.objectName()!='sharedAdvancedScroll_midi'
    content=outer.widget()
    root=content.layout()
    assert isinstance(root,QVBoxLayout)
    cards=[root.itemAt(i).widget() for i in range(3,7)]
    assert all(x is not None and x.objectName()=='studioCard' for x in cards)
    title=root.itemAt(0).widget();intro=root.itemAt(1).widget()
    old=[root.takeAt(0) for _ in range(root.count())]
    root.setContentsMargins(3,0,3,0)
    root.setSpacing(1)
    header=QHBoxLayout()
    header.setSpacing(7)
    title.setStyleSheet('font-size:16px;font-weight:800;color:#ebf8ff;')
    title.setFixedWidth(118)
    title.setFixedHeight(20)
    intro.setStyleSheet('font-size:11px;color:#b9dbe9;')
    # La descripción no debe ensanchar el panel más que su viewport.
    intro.setWordWrap(True)
    intro.hide()
    title.hide()
    header.addWidget(title)
    header.addWidget(intro,1)
    root.addLayout(header)
    stage=QWidget(content)
    stage.setObjectName('midiCompactDashboard')
    grid=QGridLayout(stage)
    grid.setContentsMargins(0,0,0,0)
    grid.setHorizontalSpacing(5)
    grid.setVerticalSpacing(4)
    grid.setAlignment(Qt.AlignTop)
    grid.setColumnStretch(0,53)
    grid.setColumnStretch(1,47)
    grid.setRowStretch(0,0)
    grid.setRowStretch(1,1)
    grid.setRowStretch(2,0)
    stage.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
    root.addWidget(stage,0,Qt.AlignTop)
    root.addStretch(1)
    top_left=QWidget(stage)
    leftbox=QVBoxLayout(top_left)
    leftbox.setContentsMargins(0,0,0,0)
    leftbox.setSpacing(0)
    top_right=QWidget(stage)
    rightbox=QVBoxLayout(top_right)
    rightbox.setContentsMargins(0,0,0,0)
    rightbox.setSpacing(3)
    # Widgets reales del candado: mismos selectores de motor, presets,
    # inventarios de stems, piezas de batería y MIDI.
    comp=MidiCompactBridge(main)
    comp.stage=stage
    comp.left_top_layout=leftbox
    comp.right_top=top_right
    comp.right_top_layout=rightbox
    bridge.midi_compact=comp.place
    comp.place(True)
    rightbox.addWidget(cards[0],1)
    grid.addWidget(top_left,0,0)
    grid.addWidget(top_right,0,1)
    grid.addWidget(cards[1],1,0)
    grid.addWidget(cards[2],1,1)
    grid.addWidget(cards[3],2,0,1,2)
    # El módulo ya tiene una segunda columna global de resultados.
    # Aquí dos columnas adicionales exigían 1.206px dentro de 724px y
    # ocultaban los controles por desplazamiento horizontal.
    for widget in (top_left,top_right,cards[1],cards[2],cards[3]):
        grid.removeWidget(widget)
    grid.setColumnStretch(0,1)
    grid.setColumnStretch(1,0)
    for row,widget in enumerate((top_left,top_right,cards[1],cards[2],cards[3])):
        grid.addWidget(widget,row,0)
        grid.setRowStretch(row,0)
    converter._midi_compact_dashboard=comp
    converter._midi_dashboard_grid=grid
    converter._midi_original_cards=cards
    converter._midi_compact_resize_tabs=_compact_cards(converter,cards)
    _compact_results(main)
    _unify_midi_surface(main,comp,cards)
    _dense_midi_controls(main,comp,cards)
    _parameters_without_scroll(converter)
    _focus_midi_subtabs(main,converter)
    bridge.host.hide()
    bridge.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    outer.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    outer.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    splitter=main.workbench.midi_tab
    # La aplicación permitía arrastrar el separador hasta dejar 100px para
    # el conversor, aunque se hubiera repartido 69/31 al iniciar. Un
    # splitter horizontal no puede tener su panel de trabajo colapsado.
    converter.setMinimumWidth(615)
    splitter.setChildrenCollapsible(False)
    splitter.setCollapsible(0,False)
    splitter.setCollapsible(1,False)
    splitter.setStretchFactor(0,69)
    splitter.setStretchFactor(1,31)
    adjusting=False

    def limits():
        sizes=splitter.sizes()
        total=sum(sizes)
        if not total:return 0,0
        # Reservar espacio real para guardar, revisar y reproducir MIDI.
        minimum_right=max(410,main.workbench.midi_results.minimumSizeHint().width())
        min_left=max(converter.minimumWidth(),min(round(total*.60),total-minimum_right))
        return total,min_left

    def ensure_visible(_position=None,_index=None):
        nonlocal adjusting
        if adjusting:return
        total,minimum_left=limits()
        if total<=0:return
        if splitter.sizes()[0]<minimum_left:
            adjusting=True
            try:splitter.setSizes([minimum_left,total-minimum_left])
            finally:adjusting=False

    def split():
        nonlocal adjusting
        if adjusting:return
        total,minimum_left=limits()
        if total<=0:return
        desired=max(minimum_left,min(round(total*.69),
                    total-max(410,main.workbench.midi_results.minimumSizeHint().width())))
        adjusting=True
        try:splitter.setSizes([desired,total-desired])
        finally:adjusting=False
    splitter.splitterMoved.connect(ensure_visible)
    main.tabs.currentChanged.connect(lambda _:QTimer.singleShot(0,ensure_visible)
        if main.tabs.currentWidget() is splitter else None)
    QTimer.singleShot(0,split)
    return comp


class MidiLibraryDock:
    """Traslada el inventario MIDI al panel donde se escuchan y guardan.

    No hay copias de QListWidget, señales ni modelos; al abrir el candado
    vuelve a su posición original en MidiHomePanel.
    """
    def __init__(self,comp,results):
        self.comp=comp
        self.results=results
        browser=comp.browser
        self.cols=browser.layout().itemAt(1).layout()
        self.actions=browser.layout().itemAt(2).layout()
        assert self.cols.count()==3 and self.actions.count()==3
        self.library=self.cols.itemAt(2).layout()
        self.controls=self.actions.itemAt(2).layout()
        self.box=QFrame(results)
        self.box.setObjectName('midiLibraryUnified')
        self.box.setStyleSheet('''
            QFrame#midiLibraryUnified {background:#041b40;
                border:1px solid #267eae;border-radius:6px;}
            QListWidget#midiHomeFiles {background:#031734;color:#dcf7ff;
                border:1px solid #187ac4;border-radius:4px;font-size:12px;}
            QListWidget#midiHomeFiles::item {background:#031734;color:#dcf7ff;
                padding:1px;}
            QListWidget#midiHomeFiles::item:selected {background:#0a579b;color:white;}
            QWidget#midiAudioWaveRow {background:#031734;border:0;}
        ''')
        self.row=QVBoxLayout(self.box)
        self.row.setContentsMargins(5,3,5,4)
        self.row.setSpacing(2)
        results.layout().insertWidget(0,self.box)
        self.docked=False
        self.dock()

    def dock(self):
        if self.docked:return
        item=self.cols.takeAt(2)
        controls=self.actions.takeAt(2)
        assert item.layout() is self.library and controls.layout() is self.controls
        self.row.addLayout(self.library,1)
        self.row.addLayout(self.controls)
        self.box.show()
        self.docked=True

    def undock(self):
        if not self.docked:return
        self.row.removeItem(self.library)
        self.row.removeItem(self.controls)
        self.cols.addLayout(self.library,29)
        self.actions.addLayout(self.controls,29)
        self.box.hide()
        self.docked=False


def _unify_midi_surface(main,comp,cards):
    """Una única cabecera, entrada y motor a la izquierda; salidas a la derecha."""
    converter=main.workbench.converter
    results=main.workbench.midi_results
    results._midi_unified=True
    results.layout().setContentsMargins(5,3,5,4)
    results.layout().setSpacing(4)

    # El marco externo de 'MIDI generado' era una barra de título más.
    result_card=results.parentWidget()
    if result_card.objectName()=='studioCard':
        result_card.layout().itemAt(0).widget().hide()
        result_card.body.setContentsMargins(0,0,0,0)
        result_card.setStyleSheet('QFrame#studioCard {background:transparent;border:none;}')

    # El listado MIDI se agrupa con su reproducción/guardado. Los dos
    # inventarios de entrada permanecen en el convertidor.
    library=MidiLibraryDock(comp,results)
    comp.library_dock=library
    panel_title=next((label for label in results.findChildren(QLabel)
        if label.text()=='PISTAS MIDI · REVISAR ANTES DE GUARDAR'),None)
    if panel_title is not None:
        panel_title.setText('CONVERSIONES PENDIENTES')
        panel_title.setStyleSheet(
            'font-size:11px;font-weight:700;color:#a7dffa;'
            'background:transparent;border:0;')
        results._midi_pending_title=panel_title
    for preview,old,new in (
        (converter.source_preview,'ESCUCHAR ARCHIVO DE ORIGEN','Audio de origen'),
        (results.preview,'PREVISUALIZAR RESULTADO SELECCIONADO','MIDI para revisar')):
        for label in preview.findChildren(QLabel):
            if label.text()==old:
                label.setText(new)
                label.setStyleSheet(
                    'font-size:11px;font-weight:700;color:#b6e3fa;'
                    'background:transparent;border:0;')
                break

    # Registro real del motor en la columna de salida: ocupa la altura
    # antes desaprovechada y libera la columna de importación/ajustes.
    activity=cards[3]
    converter._midi_dashboard_grid.removeWidget(activity)
    activity.setParent(results)
    activity.setMaximumHeight(245)
    activity.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    converter.log.setMinimumHeight(38)
    converter.log.setMaximumHeight(210)
    for label in activity.findChildren(QLabel):
        if label.text()=='REGISTRO DE TRANSCRIPCIÓN':
            label.setText('Registro del motor')
            label.setStyleSheet('font-size:11px;font-weight:700;'
                                'color:#b6e3fa;background:transparent;border:0;')
        elif label.text().startswith('El MIDI contiene'):
            label.hide()
    results.layout().addStretch(0)
    results.layout().insertWidget(results.layout().count()-2,activity,1)
    results._midi_activity_panel=activity
    # Sin resultados no debe aparecer un panel vacío de gran altura.
    results.populate()

    # 'Parámetros de transcripción' ya está identificado por sus controles:
    # se quita la cabecera decorativa y se conserva toda la cuadrícula.
    comp.settings_title=comp.settings.layout().itemAt(0).widget()
    comp.settings_title.hide()
    comp.settings.setMaximumHeight(132)
    comp.exp.midi_settings_grid.setVerticalSpacing(1)

    # Presets de conversión se consultan en Parámetros; la bandeja para
    # arrastrar stems se consulta en Fuente. No se repiten como tarjetas
    # completas fuera de las pestañas.
    entry=cards[0]
    tabs=converter.form_tabs
    source_page=tabs.widget(0).widget()
    parameter_page=tabs.widget(1).widget()
    entry.body.removeWidget(converter.presets)
    converter.presets.setParent(parameter_page)
    parameter_page.layout().insertWidget(0,converter.presets)
    shelf=converter.stem_shelf.parentWidget()
    entry.body.removeWidget(shelf)
    shelf.setParent(source_page)
    source_page.layout().insertWidget(0,shelf)
    entry.hide()

    # Duplicación: el navegador de arriba ya lista los stems y tiene Actualizar.
    for label in shelf.findChildren(QLabel):
        if label.text()=='STEMS DEL PROYECTO':label.hide()
    converter.stem_update.hide()
    converter.stem_hint.hide()
    shelf.setMaximumHeight(108)
    converter.stem_drop.setMinimumHeight(37)
    converter.stem_drop.setMaximumHeight(42)

    def resize_source_lists(*_):
        if not library.docked:return
        num=comp.browser.stems.count()+comp.browser.drums.count()
        has_items=bool(num)
        for widget in (comp.browser.stems,comp.browser.drums,
                       comp.browser.stem_title,comp.browser.drum_title,
                       comp.browser.mark_all,comp.browser.clear_all,
                       comp.browser.preview,comp.browser.convert):
            widget.setVisible(has_items and comp.browser.isVisible())
        for inventory in (comp.browser.stems,comp.browser.drums):
            inventory.setMaximumHeight(88 if has_items else 0)
        comp.browser.setMaximumHeight(173 if has_items else 103)
        num_midis=comp.browser.midis.count()
        comp.browser.midis.setMaximumHeight(170 if num_midis else 56)
        library.box.setMaximumHeight(245 if num_midis else 135)
        num_shelf=converter.stem_shelf.count()
        converter.stem_shelf.setVisible(bool(num_shelf))
        converter.stem_listen.setVisible(bool(num_shelf))
        converter.stem_use.setVisible(bool(num_shelf))
        converter.stem_shelf.setMaximumHeight(70)
        shelf.setMaximumHeight(112 if num_shelf else 55)
        # Al no haber stems se oculta la columna de selección: el cajón
        # de arrastre aprovecha TODO el ancho, sin recuadro vacío al lado.
        shelf_columns=shelf.layout().itemAt(0).layout()
        shelf_columns.setStretch(0,54 if num_shelf else 0)
        shelf_columns.setStretch(1,46 if num_shelf else 1)

    for inventory in (comp.browser.stems,comp.browser.drums,comp.browser.midis,
                      converter.stem_shelf):
        model=inventory.model()
        for signal in (model.rowsInserted,model.rowsRemoved,model.modelReset):
            signal.connect(lambda *_:QTimer.singleShot(0,resize_source_lists))
    resize_source_lists()
    comp.resize_unified=resize_source_lists
    QTimer.singleShot(0,converter._midi_compact_resize_tabs)


def _dense_midi_controls(main,comp,cards):
    """Controles desktop compactos, sin estiramiento artificial.

    Mantiene los objetos originales (modelos, señales, drop, progreso).
    Los límites son máximos de anchura, no recortes del contenido ni
    límites de resultados o del número de instrumentos.
    """
    from PySide6.QtWidgets import QComboBox,QLineEdit,QSlider
    converter=main.workbench.converter
    browser=comp.browser
    results=main.workbench.midi_results

    def width(widget,maximum,minimum=None):
        if minimum is not None:
            widget.setMinimumWidth(minimum)
        widget.setMaximumWidth(maximum)
        return widget

    # Línea de IA: las acciones conservan sus nombres completos en tooltip.
    width(browser.model,166,125)
    for button,maximum in ((browser.load_model,104),(browser.reload,98),
                           (browser.mark_all,72),(browser.clear_all,78),
                           (browser.preview,43),(browser.convert,155),
                           (browser.piano,104),(browser.results,100)):
        width(button,maximum)
    # La lista de archivos SÍ se expande (los nombres de pistas pueden ser largos).
    # Los transportes y sus botones NO son barras de 600 píxeles.
    browser.progress_label.setMinimumWidth(0)
    width(browser.progress_label,155)
    width(browser.progress,180)
    progress_row=browser.layout().itemAt(browser.layout().count()-1).layout()
    progress_row.setStretch(1,0)
    if not getattr(browser,'_progress_trailing_stretch',False):
        progress_row.addStretch(1)
        browser._progress_trailing_stretch=True

    # Presets: evitar que el campo «Nombre» ocupe medio monitor.
    width(comp.exp.choice,175,110)
    width(comp.exp.name,180,90)
    comp.exp.choice.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
    comp.exp.name.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
    comp.preset.setSpacing(4)
    if not getattr(comp,'_preset_trailing_stretch',False):
        comp.preset.addStretch(1)
        comp._preset_trailing_stretch=True

    # Cuatro parejas de regulación en dos columnas.  No estirar los
    # deslizantes ni separar etiqueta y valor con márgenes de 150px.
    slider_names={
        'onset':'Sensibilidad',
        'min_duration':'Duración mínima',
        'merge_gap':'Unión microcortes',
        'note_shift':'Desplaz. ataque',
    }
    home=main.studio_home
    grid=comp.exp.midi_settings_grid
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(2)
    # El puente acopla estos cuatro sliders DESPUÉS de construir la
    # ventana. En ese instante grid.count() aún puede ser 0: diferir el
    # ajuste y limitar reintentos (no bloquear el arranque ni duplicar filas).
    names=('onset','min_duration','merge_gap','note_shift')
    def compact_lifted_sliders():
        # Los widgets originales se acoplan al entrar en Audio a MIDI,
        # no necesariamente al arrancar la app. No depender de una ventana
        # de reintentos de 3 s: se aplica cuando el usuario abre la pestaña.
        if grid.count()<8:return
        for i,name in enumerate(names):
            item=grid.itemAt(i)
            line=item.layout() if item is not None else None
            if not isinstance(line,QHBoxLayout):return
            label=line.itemAt(0).widget()
            control=line.itemAt(1).widget()
            if not isinstance(label,QLabel) or not hasattr(control,'slider'):
                return
            if not getattr(label,'_midi_dense_caption',False):
                label.setToolTip(label.text())
                label.setText(slider_names[name])
                label._midi_dense_caption=True
            label.setMinimumWidth(0)
            label.setMaximumWidth(116)
            control.setMinimumWidth(125)
            control.setMaximumWidth(188)
            control.number.setFixedWidth(64)
            control.slider.setMinimumWidth(45)
            control.slider.setMaximumWidth(108)
            control.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            line.setSpacing(3)
            line.setStretch(0,0)
            line.setStretch(1,0)
            if not getattr(line,'_midi_dense_stretch',False):
                line.addStretch(1)
                line._midi_dense_stretch=True

        # Refinamiento y cuantización: mantener cada etiqueta pegada a
        # su selector; la cuadrícula puede estirar la CELDA, no los mandos.
        for index,caption_width,choice_width in ((4,98,145),(5,187,140)):
            line=grid.itemAt(index).layout()
            if not isinstance(line,QHBoxLayout):continue
            caption=line.itemAt(0).widget()
            choice=line.itemAt(1).widget()
            if caption is not None:
                caption.setMinimumWidth(0)
                caption.setMaximumWidth(caption_width)
            if isinstance(choice,QComboBox):
                choice.setMinimumWidth(85)
                choice.setMaximumWidth(choice_width)
                choice.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            line.setSpacing(4)
            line.setStretch(0,0)
            line.setStretch(1,0)
            if not getattr(line,'_midi_dense_stretch',False):
                line.addStretch(1)
                line._midi_dense_stretch=True
        comp._dense_slider_limits_applied=True
    def on_midi_tab_changed(_index=None):
        if main.tabs.currentWidget() is main.workbench.midi_tab:
            QTimer.singleShot(0,compact_lifted_sliders)
            QTimer.singleShot(250,compact_lifted_sliders)
    main.tabs.currentChanged.connect(on_midi_tab_changed)
    QTimer.singleShot(0,on_midi_tab_changed)
    width(home.refine,145)
    width(home.quant,139)
    width(home.midi_run,155)

    # Fuente: archivo y directorio pueden tener rutas muy largas, pero
    # el texto completo permanece dentro de un QLineEdit desplazable.
    width(converter.audio_path,345,225)
    width(converter.folder_path,310,205)
    width(converter.file_button,116)
    width(converter.folder_button,106)
    width(converter.stem_count,245,155)
    width(converter.stem_preview_choice,155,80)
    width(converter.preview_external_midi_button,190)
    width(converter.outdir,390,160)
    width(converter.filename,220,90)
    for widget in (converter.quant,converter.refinement,
                   converter.precision_profile):
        width(widget,185)

    source_page=converter.form_tabs.widget(0).widget()
    shelf=converter.stem_shelf.parentWidget()
    # Reaprovechar la FILA que ya contiene la selección de audio. No
    # reservar otra franja horizontal de lado a lado solo para un drop.
    source_form=converter.audio_path.parentWidget().layout()
    import_row=next((
        source_form.itemAt(i).layout()
        for i in range(source_form.count())
        if source_form.itemAt(i).layout() is not None
        and any(source_form.itemAt(i).layout().itemAt(j).widget()
                is converter.audio_path
                for j in range(source_form.itemAt(i).layout().count()))
    ),None)
    assert isinstance(import_row,QHBoxLayout)
    columns=shelf.layout().itemAt(0).layout()
    drop_column=columns.itemAt(1).layout()
    assert isinstance(drop_column,QVBoxLayout)
    drop_column.removeWidget(converter.stem_drop)
    converter.stem_drop.setParent(converter.audio_path.parentWidget())
    converter.stem_drop.setMinimumWidth(160)
    converter.stem_drop.setMaximumWidth(196)
    converter.stem_drop.caption.setText('Soltar stem aquí')
    converter.stem_drop.setMinimumHeight(29)
    converter.stem_drop.setMaximumHeight(33)
    converter.stem_drop.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
    import_row.insertWidget(2,converter.stem_drop,0)
    import_row.setSpacing(5)
    import_row.setStretch(0,0)
    if not getattr(converter,'_midi_import_row_end',False):
        import_row.addStretch(1)
        converter._midi_import_row_end=True
    columns.setStretch(0,1)
    columns.setStretch(1,0)

    # Carpeta, salida y progreso se muestran en barras cortas alineadas
    # a la izquierda. Las listas conservan todo su ancho útil.
    folder_row=next((
        source_form.itemAt(i).layout()
        for i in range(source_form.count())
        if source_form.itemAt(i).layout() is not None
        and any(source_form.itemAt(i).layout().itemAt(j).widget()
                is converter.folder_path
                for j in range(source_form.itemAt(i).layout().count()))
    ),None)
    if isinstance(folder_row,QHBoxLayout):
        folder_row.setStretch(0,0)
        folder_row.addStretch(1)
    width(converter.progress,230)
    cards[2].body.setAlignment(converter.progress,Qt.AlignLeft)

    # Bandeja de stems: se abre solo si contiene pistas reales; de lo
    # contrario no desperdicia altura bajo las opciones de importación.
    def refresh_shelf(*_):
        has_stems=bool(converter.stem_shelf.count())
        shelf.setVisible(has_stems)
        if has_stems:shelf.setMaximumHeight(110)
        QTimer.singleShot(0,converter._midi_compact_resize_tabs)
    converter.stem_shelf.model().rowsInserted.connect(refresh_shelf)
    converter.stem_shelf.model().rowsRemoved.connect(refresh_shelf)
    converter.stem_shelf.model().modelReset.connect(refresh_shelf)
    refresh_shelf()

    # Densidad adecuada para escritorio sin reducir los objetivos
    # interactivos a menos de 22 px.  Se excluyen los botones de zoom,
    # transportes fijos y controles de otras pestañas de la aplicación.
    for parent in (browser,comp.settings,source_page,converter,results):
        for button in parent.findChildren(QPushButton):
            if button.minimumHeight()<=24:button.setMaximumHeight(26)
        for combo in parent.findChildren(QComboBox):
            if combo.minimumHeight()<=24:combo.setMaximumHeight(26)
    converter._midi_dense_applied=True


def _parameters_without_scroll(converter):
    """Redistribuye los widgets de Parámetros en columnas sin duplicarlos.

    Los modelos de audio/MIDI, los valores y las conexiones permanecen
    intactos. Un QScrollArea interior no debe ser necesario en esta pestaña.
    """
    from PySide6.QtCore import QObject,QEvent
    from PySide6.QtWidgets import QComboBox,QAbstractSpinBox

    tabs=converter.form_tabs
    area=tabs.widget(1)
    assert isinstance(area,QScrollArea)
    page=area.widget()
    opt=page.layout()
    assert isinstance(opt,QVBoxLayout)
    if getattr(page,'_midi_no_scroll_layout',False):
        return

    pieces=[opt.takeAt(0) for _ in range(opt.count())]
    if len(pieces)!=9:
        raise RuntimeError('Estructura inesperada de Parámetros: '+str(len(pieces)))
    preset=pieces[0].widget()
    mode=pieces[1].layout()
    tempo=pieces[2].layout()
    precision=pieces[3].layout()
    refinement_choice=pieces[4].layout()
    piano=pieces[5].widget()
    advanced_widget=pieces[6].widget()
    advanced=advanced_widget.layout()
    refinement=pieces[7].layout()
    info=pieces[8].widget()
    if not (preset is converter.presets and isinstance(mode,QHBoxLayout)
            and isinstance(tempo,QFormLayout)
            and isinstance(advanced,QFormLayout)
            and isinstance(refinement,QFormLayout)):
        raise RuntimeError('Parámetros: tipos de widgets inesperados')

    def take_form_rows(form):
        rows=[]
        while form.rowCount():
            row=form.takeRow(0)
            label=row.labelItem.widget() if row.labelItem is not None else None
            field=row.fieldItem.widget() if row.fieldItem is not None else None
            if field is None:
                raise RuntimeError('Parámetros: campo de formulario no encontrado')
            rows.append((label,field))
        return rows

    rhythm=take_form_rows(tempo)
    attack=take_form_rows(advanced)
    finishing=take_form_rows(refinement)
    if (len(rhythm),len(attack),len(finishing))!=(5,5,4):
        raise RuntimeError('Parámetros: cambió el número de controles')

    opt.setContentsMargins(5,3,5,3)
    opt.setSpacing(1)
    opt.setSizeConstraint(QLayout.SetDefaultConstraint)
    page.setMinimumHeight(0)
    advanced_widget.hide()
    page._midi_saved_original_layout_items=pieces

    preset.setMaximumHeight(30)
    preset.layout().setContentsMargins(3,1,3,1)
    preset.layout().setSpacing(4)
    preset.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Fixed)
    converter.automatic.setToolTip(converter.automatic.text())
    converter.automatic.setText('Automático')
    converter.mode_status.setToolTip(converter.mode_status.text())
    converter.mode_status.setText('IA')
    mode.setSpacing(4)

    for item in (converter.precision_profile,converter.refinement,
                 converter.quant,converter.tempo_options):
        item.setMinimumWidth(0)
        item.setMaximumWidth(132)
        if isinstance(item,QComboBox):item.view().setMinimumWidth(260)
        item.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)

    converter.tempo_auto.setToolTip(converter.tempo_auto.text())
    converter.tempo_auto.setText('BPM auto')
    converter.bpm.setMinimumWidth(0)
    converter.bpm.setMinimumWidth(0)
    converter.bpm.number.setFixedWidth(97)
    converter.bpm.slider.setMinimumWidth(26)
    converter.bpm.slider.setMaximumWidth(39)
    converter.bpm.setMaximumWidth(147)
    rhythm[0][1].layout().setSpacing(3)
    rhythm[0][1].layout().setContentsMargins(0,0,0,0)
    converter.detect_tempo.setMaximumWidth(73)
    converter.detect_tempo.setToolTip(converter.detect_tempo.text())
    converter.detect_tempo.setText('Analizar')
    converter.tempo_options.setMaximumWidth(80)
    converter.tap_button.setMaximumWidth(42)
    rhythm[1][1].layout().setSpacing(2)
    tempo_hint=converter.tempo_quality
    tempo_hint.setToolTip(tempo_hint.text())
    tempo_hint.setText('BPM: Analizar o Tap')
    tempo_hint.setWordWrap(False)
    converter.detect_tempo.setToolTip(tempo_hint.toolTip() or tempo_hint.text())
    converter.align_grid.setToolTip(converter.align_grid.text())
    converter.align_grid.setText('Alinear rejilla')
    piano.setToolTip(piano.text())
    piano.setText('Piano Transkun V2')
    info.setToolTip(info.text())
    info.setText('Ajustes automáticos editables')
    info.setWordWrap(False)
    converter.automatic.setToolTip(info.toolTip() or info.text())

    for line,caption in ((precision,'Precisión'),(refinement_choice,'Refinado')):
        label=next((line.itemAt(i).widget() for i in range(line.count())
                    if isinstance(line.itemAt(i).widget(),QLabel)),None)
        if label is not None:
            label.setToolTip(label.text())
            label.setText(caption)
            label.setMaximumWidth(80)
            label.setMinimumWidth(0)
        line.setSpacing(3)
        line.setStretch(1,0)

    descriptions={
        'onset':'Ataque',
        'frame':'Sostenido',
        'min_duration':'Duración',
        'low':'Rango MIDI',
        'drum':'Golpes batería',
        'min_velocity':'Filtro débiles',
        'merge_gap':'Microcortes',
        'note_shift':'Ajuste ataque',
        'grid_offset':'Rejilla MIDI'
    }
    def short_slider(control,maximum=160,number=57,slider=90):
        control.setMinimumWidth(0)
        control.setMaximumWidth(maximum)
        control.slider.setMinimumWidth(32)
        control.slider.setMaximumWidth(slider)
        control.number.setFixedWidth(number)
        control.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)

    for control in (converter.onset,converter.frame,converter.min_duration,
                    converter.drum,converter.min_velocity,converter.merge_gap,
                    converter.note_shift,converter.grid_offset):
        short_slider(control,144,64,73)
    for control in (converter.min_duration,converter.merge_gap,
                    converter.note_shift,converter.grid_offset):
        control.number.setFixedWidth(76)
    for control in (converter.low,converter.high):
        short_slider(control,109,53,48)
    pitches=rhythm[0][1]  # dummy ref, pitch belongs to attack[3]
    pitches=attack[3][1]
    pitches.layout().setSpacing(1)
    pitches.layout().setContentsMargins(0,0,0,0)
    pitches.setMinimumWidth(0)
    pitches.setMaximumWidth(220)

    names=('onset','frame','min_duration','low','drum')
    for i,name in enumerate(names):
        label,field=attack[i]
        if isinstance(label,QLabel):
            label.setToolTip(label.text())
            label.setText(descriptions[name])
    for i,name in enumerate(('min_velocity','merge_gap','note_shift','grid_offset')):
        label,field=finishing[i]
        if isinstance(label,QLabel):
            label.setToolTip(label.text())
            label.setText(descriptions[name])
    for i,label_name in ((0,''),(1,''),(3,'Cuantizar')):
        label=rhythm[i][0]
        if isinstance(label,QLabel):
            label.setToolTip(label.text())
            label.setText(label_name)

    def row_widget(label,field):
        wrapper=QWidget(page)
        line=QHBoxLayout(wrapper)
        line.setContentsMargins(1,1,1,1)
        line.setSpacing(3)
        if label is not None and label.text().strip():
            label.setMinimumWidth(0)
            label.setMaximumWidth(76 if field is not pitches else 73)
            label.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
            line.addWidget(label,0)
        elif label is not None:
            label.hide()
        field.setMinimumWidth(0)
        if field.layout() is not None and isinstance(field.layout(),QHBoxLayout):
            field.layout().setContentsMargins(0,0,0,0)
            field.layout().setSpacing(3)
        field.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
        line.addWidget(field,0)
        line.addStretch(1)
        wrapper.setMaximumHeight(30)
        wrapper.setMaximumWidth(290 if field is pitches else 234)
        return wrapper

    def layout_holder(layout):
        holder=QWidget(page)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(3)
        holder.setLayout(layout)
        holder.setMaximumHeight(30)
        holder.setMaximumWidth(234)
        return holder

    rows={
        'mode':layout_holder(mode),
        'tempo':row_widget(*rhythm[0]),
        'rhythm':row_widget(*rhythm[1]),
        'hint':row_widget(*rhythm[2]),
        'quant':row_widget(*rhythm[3]),
        'align':row_widget(*rhythm[4]),
        'precision':layout_holder(precision),
        'refinement':layout_holder(refinement_choice),
        'piano':piano,
        'info':info,
    }
    for name,pair in zip(names,attack):
        rows[name]=row_widget(*pair)
    for name,pair in zip(('min_velocity','merge_gap','note_shift','grid_offset'),finishing):
        rows[name]=row_widget(*pair)

    # Los ajustes comparten filas: no hay bloques vacíos, bandas decorativas
    # ni una sola columna de controles dentro de un panel ancho.
    order=(
        'mode','precision','refinement',
        'tempo','rhythm','quant',
        'align','piano','onset',
        'frame','min_duration','low',
        'drum','min_velocity','merge_gap',
        'note_shift','grid_offset'
    )
    grid=QGridLayout()
    grid.setContentsMargins(2,1,2,1)
    grid.setHorizontalSpacing(5)
    grid.setVerticalSpacing(1)
    opt.addWidget(preset,0)
    opt.addLayout(grid,0)

    rows['hint'].hide()
    rows['info'].hide()
    page._midi_parameter_grid=grid
    page._midi_parameter_widgets=rows
    page._midi_parameter_order=order
    page._midi_no_scroll_layout=True

    def redraw_columns():
        width=area.viewport().width()
        columns=3 if width>=950 else 2
        if getattr(page,'_midi_last_column_count',None)==columns:
            return
        page._midi_last_column_count=columns
        while grid.count():
            grid.takeAt(0)
        if columns==3:
            positions=(
                ('mode',0,0,1),('precision',0,1,1),('refinement',0,2,1),
                ('tempo',1,0,1),('rhythm',1,1,1),('quant',1,2,1),
                ('align',2,0,1),('piano',2,1,1),('onset',2,2,1),
                ('frame',3,0,1),('min_duration',3,1,1),('drum',3,2,1),
                ('low',4,0,2),('min_velocity',4,2,1),
                ('merge_gap',5,0,1),('note_shift',5,1,1),
                ('grid_offset',5,2,1))
            for name,row,col,span in positions:
                grid.addWidget(rows[name],row,col,1,span)
        else:
            positions=(
                ('mode',0,0,1),('precision',0,1,1),
                ('refinement',1,0,1),('tempo',1,1,1),
                ('rhythm',2,0,1),('quant',2,1,1),
                ('align',3,0,1),('piano',3,1,1),
                ('onset',4,0,1),('frame',4,1,1),
                ('min_duration',5,0,1),('drum',5,1,1),
                ('low',6,0,2),('min_velocity',7,0,1),
                ('merge_gap',7,1,1),('note_shift',8,0,1),
                ('grid_offset',8,1,1))
            for name,row,col,span in positions:
                grid.addWidget(rows[name],row,col,1,span)
        for i in range(3):
            grid.setColumnStretch(i,1 if i<columns else 0)
        page.layout().activate()
        converter._midi_compact_resize_tabs()
    class ReflowOnResize(QObject):
        def eventFilter(self,obj,event):
            if event.type()==QEvent.Resize:
                QTimer.singleShot(0,redraw_columns)
            return False
    watcher=ReflowOnResize(area)
    page._midi_parameter_reflow_watcher=watcher
    area.viewport().installEventFilter(watcher)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    QTimer.singleShot(0,redraw_columns)
    converter._midi_parameter_reflow=redraw_columns


def _focus_midi_subtabs(main,converter):
    """En cada subpestaña se muestra solo la zona de trabajo pertinente.

    El selector de stems está en Fuente; los umbrales completos están en
    Parámetros. Se mantienen los mismos widgets, no hay duplicados.
    """
    tabs=converter.form_tabs
    comp=converter._midi_compact_dashboard
    results=main.workbench.midi_results
    process=converter._midi_original_cards[2]
    source=tabs.widget(0).widget()

    # Las acciones de escucha de entrada pertenecen a Fuente, no al
    # transporte de conversión que debe mantenerse visible abajo.
    transport_source=process.body.itemAt(0).layout()
    assert isinstance(transport_source,QHBoxLayout)
    assert any(transport_source.itemAt(k).widget() is converter.stem_preview_choice
               for k in range(transport_source.count()))
    process.body.removeItem(transport_source)
    # Selección para preescucha en el panel de audio de origen, que ya
    # contiene el transporte; evita otra fila debajo de Fuente.
    preview_index=results.layout().indexOf(results.preview)
    results.layout().insertLayout(preview_index,transport_source)
    preview_label=transport_source.itemAt(0).widget()
    preview_label.setToolTip(preview_label.text())
    preview_label.setText('Escuchar pista')
    preview_label.setMaximumWidth(96)
    converter.preview_external_midi_button.setToolTip(
        converter.preview_external_midi_button.text())
    converter.preview_external_midi_button.setText('Cargar MIDI…')
    converter.preview_external_midi_button.setMaximumWidth(115)
    converter.stem_preview_choice.setMaximumWidth(132)
    # Los textos auxiliares quedan disponibles como ayudas emergentes.
    converter.file_button.setToolTip(converter.audio_info.text())
    converter.audio_info.hide()
    for label in source.findChildren(QLabel):
        if label.text().startswith('Detección armónica experimental'):
            converter.detect_chords.setToolTip(
                converter.detect_chords.toolTip()+'\n'+label.text())
            label.hide()

    # El estado de conversión se lee junto a Resultados y el registro,
    # y no debe ocupar otra fila en la columna de parámetros.
    process.body.removeWidget(converter.status)
    results.layout().insertWidget(results.layout().count()-2,converter.status)
    converter.status.setMaximumHeight(23)
    converter.status.setWordWrap(False)
    process.setMaximumHeight(88)

    def update_tab_focus(*_):
        if not comp.docked:
            return
        selected=tabs.currentIndex()
        in_source=selected==0
        comp.browser.setVisible(in_source)
        comp.settings.hide()
        if in_source:comp.resize_unified()
        for index in range(comp.preset.count()):
            child=comp.preset.itemAt(index).widget()
            if child is not None:
                child.hide()
        converter.chord_status.setVisible(converter.detect_chords.isChecked() and in_source)
        converter._midi_parameter_reflow()
        converter._midi_compact_resize_tabs()
        QTimer.singleShot(0,converter._midi_compact_resize_tabs)

    tabs.currentChanged.connect(update_tab_focus)
    converter._midi_update_tab_focus=update_tab_focus
    main.tabs.currentChanged.connect(
        lambda _:QTimer.singleShot(0,update_tab_focus)
        if main.tabs.currentWidget() is main.workbench.midi_tab else None)
    update_tab_focus()
