"""Paridad estructural entre pestañas avanzadas y ventanas con candado.

Cada vista avanzada es exactamente el MISMO QWidget de su homóloga flotante.
Sólo se mueve de contenedor; no se clonan motores, controles ni conexiones.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame,QScrollArea,QLabel,QPushButton,QVBoxLayout,
                               QHBoxLayout,QSizePolicy,QWidget)


class SharedAdvancedTab:
    def __init__(self,main,kind,card,tab,expanded,container,position=None,height=320):
        self.main=main
        self.kind=kind
        self.card=card
        self.tab=tab
        self.expanded=expanded
        self.extra=expanded.extra
        self.docked=False
        self.active=False
        self.host=QFrame(container)
        self.host.setObjectName('tabAdvancedSharedHost')
        self.host.setStyleSheet('''
        QFrame#tabAdvancedSharedHost {background:#041b40;border:1px solid #257fc4;border-radius:7px;}
        QLabel#tabAdvancedCaption {color:#a4efff;font-size:13px;font-weight:750;}
        ''')
        layout=QVBoxLayout(self.host)
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(4)
        header=QHBoxLayout()
        caption=QLabel('CONTROLES AVANZADOS · '+{
            'monitor':'GRABACIÓN Y ESCUCHA','wave':'FORMA DE ONDA',
            'midi':'TRANSCRIPCIÓN MIDI','drums':'BATERÍA POR PIEZAS',
            'drum_stems':'SELECCIÓN DE PIEZAS','piano':'EDICIÓN Y COMPOSICIÓN',
            'vocal':'ESTUDIO VOCAL COMPLETO','results':'GESTIÓN DE RESULTADOS'}[kind],self.host)
        caption.setObjectName('tabAdvancedCaption')
        header.addWidget(caption,1)
        self.toggle=QPushButton('Ocultar ▴',self.host)
        self.toggle.setToolTip('Solo oculta el panel; no modifica archivos ni tareas')
        self.toggle.clicked.connect(self.toggle_visible)
        header.addWidget(self.toggle)
        layout.addLayout(header)
        self.scroll=QScrollArea(self.host)
        self.scroll.setObjectName('sharedAdvancedScroll_'+kind)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.scroll.setMinimumHeight(80)
        self.scroll.setMaximumHeight(height)
        layout.addWidget(self.scroll,1)
        self.content=QFrame(self.scroll)
        self.content.setObjectName('sharedAdvancedContent_'+kind)
        self.content_layout=QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2,2,2,2)
        self.content_layout.setSpacing(5)
        self.scroll.setWidget(self.content)
        # Batería tiene seis pistas: no encerrar su interfaz en 250 px
        # con un desplazamiento DENTRO del desplazamiento de la pestaña.
        # El MISMO QWidget de Inicio va aquí directo, y debajo los ajustes
        # expertos añadidos, reales y sincronizados con su motor.
        self.drum_direct=None
        self.drum_title=None
        if kind=='drums':
            self.scroll.hide()
            self.drum_direct=QWidget(self.host)
            self.drum_direct.setObjectName('drumExpertFullWidth')
            self.drum_direct.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
            self.drum_direct_layout=QVBoxLayout(self.drum_direct)
            self.drum_direct_layout.setContentsMargins(2,0,2,3)
            self.drum_direct_layout.setSpacing(7)
            from drum_expert_controls import DrumEngineSettingsPanel
            self.drum_engine_settings=DrumEngineSettingsPanel(main.drum_module,self.drum_direct)
            main.drum_module.expert_engine_panel=self.drum_engine_settings
            self.drum_direct_layout.addWidget(self.drum_engine_settings)
            layout.addWidget(self.drum_direct)
            self.drum_title=self.extra.layout().itemAt(0).widget()
            caption.setText('01 · MODELO, PISTAS Y PARÁMETROS REALES DEL MOTOR')
        # Un ancho flexible: nunca obligar a que las columnas se superpongan.
        self.extra.setMinimumWidth(0)
        self.extra.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        if position is None:container.layout().addWidget(self.host)
        else:container.layout().insertWidget(position,self.host)
        if kind=='vocal' and expanded.vocal_studio is None:
            from home_vocal_studio import VocalHomeStudio
            expanded.vocal_studio=VocalHomeStudio(expanded.home,expanded.extra)
            expanded.layout.addWidget(expanded.vocal_studio,1)
            # La misma vista se usa al desprender la tarjeta.
            expanded.layout.itemAt(0).widget().hide()
        self.timeline=None
        if kind=='drum_stems':
            self.timeline=expanded.drum_timeline
            self.card.inner.removeWidget(self.timeline.panel)
            self.timeline.panel.setParent(self.content)
            self.content_layout.addWidget(self.timeline.panel)
            self.timeline.panel.show()
        # Monitor tenía tres controles exclusivos del candado: analizador
        # post-EQ, diagnósticos de captura y balance L/R. Acoplar los mismos
        # QWidget a la pestaña, nunca crear lecturas o motores simulados.
        self.monitor_extras=[]
        if kind=='monitor':
            h=expanded.home
            for widget in (h.capture_analyzer_panel,h.capture_diagnostics):
                source,index=self._find_original_layout(self.card.inner,widget)
                if source is None:
                    raise RuntimeError('Monitor: falta el control original '+widget.objectName())
                source.removeWidget(widget)
                widget.setParent(self.content)
                self.content_layout.addWidget(widget)
                widget.show()
                self.monitor_extras.append((widget,source,index))
        self.to_tab()
        if kind in ('monitor','wave'):
            # Small monitor view has ONE scroll container, at page level.
            # The full advanced host was consuming 240+225 px by default,
            # pushing the recorder out of view and leaving 2/3 scrollbars.
            # Keep all real widgets, but collapse the two optional areas.
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll.setMinimumHeight(0)
            self.scroll.setMaximumHeight(16777215)
            self.scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            self.scroll.hide()
            self.toggle.setText("Mostrar controles adicionales ▾")
        if kind=='drum_stems':
            # La selección principal con 6 pistas ya está en la sección
            # anterior: conservar el panel complementario (y la línea
            # temporal) accesible, pero plegado de inicio, sin duplicarlo.
            self.scroll.hide()
            self.toggle.setText('Mostrar opciones adicionales ▾')
            caption.setText('02 · SELECCIÓN COMPLEMENTARIA Y LÍNEA TEMPORAL')
        expanded.parity_bridge=self
        if kind=='results':
            self._attach_results_callbacks()

    @staticmethod
    def _find_original_layout(layout,widget):
        for index in range(layout.count()):
            item=layout.itemAt(index)
            if item.widget() is widget:
                return layout,index
            child=item.layout()
            if child is None and item.widget() is not None:
                child=item.widget().layout()
            if child is not None:
                result,location=SharedAdvancedTab._find_original_layout(child,widget)
                if result is not None:
                    return result,location
        return None,-1

    def _attach_results_callbacks(self):
        """Con el mismo panel, la selección procede de la pestaña visible."""
        from PySide6.QtWidgets import QPushButton
        e=self.expanded
        for button in self.extra.findChildren(QPushButton):
            title=button.text()
            if title not in ('Guardar selección…','Guardar todo…'):
                continue
            try:button.clicked.disconnect()
            except RuntimeError:pass
            if title=='Guardar selección…':
                button.clicked.connect(lambda checked=False:
                    self.main.results_tab.save_selected() if self.docked
                    else e.home.export_selected())
            else:
                button.clicked.connect(lambda checked=False:
                    e.home._save_results(self.main.results_tab._paths) if self.docked
                    else e.home.export_all())

    def toggle_visible(self):
        content=self.drum_direct if self.kind=='drums' else self.scroll
        visible=not content.isVisible()
        if visible and self.kind in ('monitor','wave'):
            # Let the PAGE's single scrollbar cover all advanced controls;
            # do not nest another scrolling viewport inside the monitor.
            self.scroll.setFixedHeight(max(90,self.content.sizeHint().height()+12))
        content.setVisible(visible)
        if visible and self.kind in ('monitor','wave'):
            QTimer.singleShot(0,lambda:
                self.scroll.setFixedHeight(max(90,self.content.sizeHint().height()+12))
                if self.scroll.isVisible() else None)
        self.toggle.setText('Ocultar ▴' if visible else 'Mostrar ▾')

    def to_floating(self):
        if not self.docked:return
        self.deactivate()
        if self.kind=='midi' and hasattr(self,'midi_compact'):
            self.midi_compact(False)
        for widget,source,index in self.monitor_extras:
            self.content_layout.removeWidget(widget)
            widget.setParent(self.card)
            source.insertWidget(index,widget)
            widget.hide()
        if self.kind=='drums':
            if hasattr(self,'drum_dense_layout'):
                self.drum_dense_layout.removeWidget(self.extra)
                self.drum_density(False)
            else:
                self.drum_direct_layout.removeWidget(self.extra)
            self.drum_direct.hide()
            if self.drum_title:self.drum_title.show()
        else:
            self.content_layout.removeWidget(self.extra)
        if self.timeline is not None:
            self.timeline.stop()
            self.content_layout.removeWidget(self.timeline.panel)
            self.timeline.panel.setParent(self.card)
        self.extra.setParent(self.card)
        self.card.inner.insertWidget(0,self.extra)
        if self.timeline is not None:
            self.card.inner.insertWidget(1,self.timeline.panel)
            self.timeline.panel.hide()
        self.extra.hide()
        self.docked=False

    def to_tab(self):
        if self.docked:return
        self.card.inner.removeWidget(self.extra)
        if self.kind=='drums':
            if hasattr(self,'drum_dense_layout'):
                self.extra.setParent(self.drum_dense_widget)
                self.drum_dense_layout.addWidget(self.extra,0,0)
                self.drum_density(True)
            else:
                self.extra.setParent(self.drum_direct)
                self.drum_direct_layout.insertWidget(0,self.extra)
            self.drum_direct.show()
            if self.drum_title:self.drum_title.hide()
        else:
            self.extra.setParent(self.content)
            self.content_layout.insertWidget(0,self.extra)
        for widget,source,index in self.monitor_extras:
            source.removeWidget(widget)
            widget.setParent(self.content)
            self.content_layout.addWidget(widget)
            widget.show()
        if self.timeline is not None:
            self.card.inner.removeWidget(self.timeline.panel)
            self.timeline.panel.setParent(self.content)
            self.content_layout.addWidget(self.timeline.panel)
            self.timeline.panel.show()
        self.docked=True
        if self.kind=='midi' and hasattr(self,'midi_compact'):
            self.midi_compact(True)
        self.extra.show()
        if self.main.tabs.currentWidget() is self.tab:
            QTimer.singleShot(0,self.activate)

    def activate(self):
        if not self.docked:return
        if self.active:return
        self.active=True
        e=self.expanded
        if self.kind=='midi':
            e._lift_midi_controls()
            e.midi_browser.refresh(force=True)
        elif self.kind=='piano':
            e.piano_tools.refresh_files(force=True)
        elif self.kind=='vocal':
            e.vocal_studio.expand()
        elif self.kind=='wave':
            e.wave_info.start()
        elif self.kind=='monitor':
            h=e.home
            e.review.balance_mount.addWidget(h.capture_balance_panel)
            h.capture_balance_panel.show()
            h.populate_processed_listen_outputs()
            h.update_capture_diagnostics()
            e.review.apply_eq()
            e.review.ticker.start()
            e.review.refresh()
        elif self.kind=='drums':
            e.refresh_drum_pieces()
        elif self.kind=='drum_stems':
            self.timeline.start()
            e.refresh()
        elif self.kind=='results':
            e.refresh()
        e.refresh_timer.start()

    def deactivate(self):
        if not self.active:return
        self.active=False
        e=self.expanded
        e.refresh_timer.stop()
        if self.kind=='midi':
            e.midi_browser.listen.stop()
            e.midi_browser.cancel_wave_previews()
            e._restore_midi_controls()
        elif self.kind=='vocal':
            e.vocal_studio.collapse()
        elif self.kind=='wave':
            e.wave_info.stop()
        elif self.kind=='monitor':
            e.review.ticker.stop()
            e.review.stop_playback()
            h=e.home
            if h.listen_processed.isChecked():
                h.listen_processed.setChecked(False)
            h.capture_balance_home_layout.addWidget(h.capture_balance_panel,0)
            h.capture_balance_panel.show()
        elif self.kind=='drum_stems':
            self.timeline.stop()


def _scrollable_page(page,key):
    """Preservar TODOS los layouts y widgets originales sin comprimirlos.

    El contenedor de la pestaña recibe una única QScrollArea. Los mismos
    controles siguen siendo hijos de la pestaña, con las mismas señales.
    """
    if getattr(page,'_advanced_parity_scroller',None) is not None:
        return page._advanced_parity_scroller.widget()
    old=page.layout()
    if not isinstance(old,QVBoxLayout):
        raise RuntimeError('Página sin layout vertical: '+key)
    content=QWidget(page)
    content.setObjectName('scrollableAdvancedPage_'+key)
    lay=QVBoxLayout(content)
    lay.setContentsMargins(5,4,5,5)
    lay.setSpacing(old.spacing())
    while old.count():
        stretch=old.stretch(0)
        item=old.takeAt(0)
        if item.widget() is not None:
            widget=item.widget()
            widget.setParent(content)
            lay.addWidget(widget,stretch,item.alignment())
        elif item.layout() is not None:
            lay.addLayout(item.layout(),stretch)
        elif item.spacerItem() is not None:
            lay.addItem(item.spacerItem())
    area=QScrollArea(page)
    area.setObjectName('wholeModuleScroll_'+key)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setWidget(content)
    old.setContentsMargins(0,0,0,0)
    old.addWidget(area,1)
    page._advanced_parity_scroller=area
    return content


def install(main):
    """Instalar SOLO pares que aún no comparten widget automáticamente.

    MIDI→audio y Mezclador comparten sus editores por studio_shared_tabs;
    Separación tiene la vista avanzada especializada en
    separation_advanced_tab. Este módulo cubre los restantes.
    """
    h=main.studio_home
    mgr=h._floating_manager
    monitor_content=_scrollable_page(main.monitor_page,'monitor')
    drum_content=_scrollable_page(main.drum_module,'drums')
    specs=(
        ('monitor',h.mon_card,main.monitor_page,monitor_content,2,240),
        ('wave',h.wave_card,main.monitor_page,monitor_content,3,225),
        ('midi',h.midi_card,main.workbench.midi_tab,
         main.workbench.converter.findChild(QScrollArea).widget(),2,520),
        ('drums',h.drum_card,main.drum_module,drum_content,3,250),
        ('drum_stems',h.drum_stems_card,main.drum_module,drum_content,4,160),
        ('piano',h.piano_card,main.workbench.piano,main.workbench.piano.content_page,2,500),
        ('vocal',h.vocal_card,main.vocal_module,
         main.vocal_module.content_scroll.widget(),2,630),
        ('results',h.result_card,main.results_tab,main.results_tab,2,160),
    )
    bridges={}
    for kind,card,tab,container,position,height in specs:
        if container is None or container.layout() is None:
            raise RuntimeError('No existe la pestaña avanzada: '+kind)
        bridge=SharedAdvancedTab(main,kind,card,tab,
                                 mgr.other_expanders[card],container,position,height)
        bridges[card]=bridge

    def sync(index):
        widget=main.tabs.widget(index)
        if widget is main.monitor_page:
            # A previous advanced scroll offset must never reopen Monitor
            # halfway down the recorder with top controls hidden.
            scroller=getattr(main.monitor_page,"_advanced_parity_scroller",None)
            if scroller is not None:
                QTimer.singleShot(0,lambda:scroller.verticalScrollBar().setValue(0))
        for bridge in bridges.values():
            if widget is bridge.tab and bridge.docked:
                bridge.activate()
            else:
                bridge.deactivate()
    main.tabs.currentChanged.connect(sync)
    sync(main.tabs.currentIndex())
    mgr.advanced_parity_bridges=bridges
    main.advanced_tab_parity=bridges
    return bridges
