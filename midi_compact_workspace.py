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
        else:
            if hasattr(self,'library_dock'):
                self.library_dock.undock()
                self.settings_title.show()
            self.left_top_layout.removeWidget(self.browser)
            self.right_top_layout.removeWidget(self.settings)
            self.left_top_layout.removeItem(self.preset)
            self.browser.setParent(e.extra)
            self.settings.setParent(e.extra)
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
    root.setContentsMargins(3,2,3,3)
    root.setSpacing(2)
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
    grid.setColumnStretch(0,53)
    grid.setColumnStretch(1,47)
    grid.setRowStretch(0,0)
    grid.setRowStretch(1,1)
    grid.setRowStretch(2,0)
    root.addWidget(stage,1)
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
        for inventory in (comp.browser.stems,comp.browser.drums):
            inventory.setMaximumHeight(130 if num else 50)
        comp.browser.setMaximumHeight(242 if num else 174)
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
