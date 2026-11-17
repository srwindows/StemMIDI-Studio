"""Mesa única de batería, sin superficies duplicadas ni scroll para ver funciones.

Reubica los mismos widgets/controladores MDX23C, editor y secuenciador.
El candado de Inicio conserva su presentación original al desacoplar.
"""
from __future__ import annotations
from PySide6.QtCore import Qt,QTimer,QObject,QEvent
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QHBoxLayout,
    QVBoxLayout,QGridLayout,QSizePolicy,QScrollArea,QSlider,QCheckBox,QProgressBar)
from studio_home import WaveCanvas


def install(main):
    mod=main.drum_module
    e=main.studio_home._floating_manager.other_expanders[main.studio_home.drum_card]
    b=main.advanced_tab_parity[main.studio_home.drum_card]
    studio=mod.studio
    # La GUI conserva cada objeto REAL: los controles no se simulan/clonan.
    b.drum_direct_layout.removeWidget(b.extra)
    b.drum_direct_layout.removeWidget(b.drum_engine_settings)
    dense=QWidget(b.drum_direct)
    dense.setObjectName('drumFlatDesk')
    dense.setStyleSheet('''QWidget#drumFlatDesk {background:#041b3d;}
       QFrame#drumFlatSection {border:1px solid #256fa5;border-radius:5px;
          background:#051e42;}''')
    grid=QGridLayout(dense)
    grid.setContentsMargins(3,2,3,2)
    grid.setSpacing(3)
    grid.setColumnStretch(0,53)
    grid.setColumnStretch(1,47)
    grid.setRowStretch(0,0)
    grid.setRowStretch(1,1)
    grid.setRowStretch(2,0)
    b.drum_dense_widget=dense
    b.drum_dense_layout=grid
    b.drum_direct_layout.addWidget(dense)
    e.extra.setParent(dense)
    grid.addWidget(e.extra,0,0)

    # El cuadro IA queda a la derecha: altura limitada a tres filas.
    right=QWidget(dense)
    rc=QVBoxLayout(right)
    rc.setContentsMargins(0,0,0,0)
    rc.setSpacing(4)
    panel=b.drum_engine_settings
    panel.setParent(right)
    panel.setObjectName('drumRealEngineSettings')
    panel.explanation.hide()  # Sus detalles continúan como ayuda contextual.
    panel.setToolTip(panel.explanation.text())
    panel.layout().setContentsMargins(6,10,6,3)
    panel.layout().setSpacing(2)
    panel.grid.setHorizontalSpacing(6)
    panel.grid.setVerticalSpacing(2)
    for slider in panel.sliders.values():
        slider.setMinimumWidth(60)
        slider.setMaximumWidth(105)
        slider.setFixedHeight(17)
    for value in panel.values.values():value.setFixedWidth(38)
    panel.output_format.setFixedWidth(83)
    panel.output_format.setFixedHeight(21)
    panel.reset.setMaximumWidth(128)
    panel.reset.setFixedHeight(21)
    panel.setFixedHeight(95)
    rc.addWidget(panel)

    # Inspector real del canal, con su forma de onda y ecualización.
    inspector=studio.inspector
    inspector.setParent(right)
    inspector.setFixedHeight(97)
    inspector.wave.setMinimumWidth(110)
    inspector.wave.setFixedHeight(31)
    inspector.empty_wave.setFixedHeight(31)
    for eq in inspector.equalizers.values():
        eq.setMinimumWidth(0)
        eq.setMaximumWidth(147)
        eq.slider.setMinimumWidth(50)
        eq.slider.setMaximumWidth(65)
        eq.spin.setFixedWidth(70)
    for ctrl,text in ((inspector.listen_btn,'▶'),
                      (inspector.edit_btn,'Editar'),
                      (inspector.reset_btn,'Reset')):
        ctrl.setText(text)
        ctrl.setToolTip({'▶':'Escuchar canal seleccionado',
                         'Editar':'Editar pista seleccionada',
                         'Reset':'Restablecer ajustes del canal'}[text])
        ctrl.setMinimumWidth(46)
        ctrl.setMaximumWidth(63)
        ctrl.setFixedHeight(22)
    inspector.layout().setContentsMargins(6,2,6,2)
    inspector.layout().setSpacing(5)
    rc.addWidget(inspector)
    rc.addStretch(0)
    grid.addWidget(right,0,1)

    # Desplazamiento eliminado: el mezclador visible coincide ya con las 6
    # tiras de la cabecera (M/S/ganancia/pan + onda). Evitamos mostrar otro.
    # Los editores inferiores son las páginas originales, no reconstrucciones.
    parent_grid=studio.dashboard_content.layout()
    for key,col in ((2,0),(3,1)):
        frame=studio.dashboard_sections[key]
        parent_grid.removeWidget(frame)
        frame.setParent(dense)
        frame.setMinimumHeight(0)
        frame.setMaximumHeight(16777215)
        frame.layout().setContentsMargins(4,1,4,2)
        frame.layout().setSpacing(2)
        heading=frame.layout().itemAt(0).widget()
        heading.setFixedHeight(17)
        heading.setStyleSheet('font-size:11px;font-weight:700;color:#a5ebff;')
        content=frame.layout().itemAt(1).widget()
        content.setMinimumHeight(0)
        content.layout().setContentsMargins(3,1,3,1)
        content.layout().setSpacing(2)
        grid.addWidget(frame,1,col)

    # Editor de audio real: onda+11 efectos en 6 filas con sus controles.
    studio.big_wave.setMinimumHeight(31)
    studio.big_wave.setMaximumHeight(36)
    studio.editor_presets.layout().setContentsMargins(2,0,2,0)
    studio.editor_presets.setMaximumHeight(27)
    for field in studio.editor_controls:
        field.setMinimumWidth(0)
        field.setMaximumWidth(152)
        field.setFixedHeight(21)
        field.slider.setMinimumWidth(54)
        field.slider.setMaximumWidth(77)
        field.spin.setFixedWidth(64)
    studio.editor_summary.setMaximumWidth(145)
    studio.editor_summary.setWordWrap(False)
    studio.editor_render_btn.setMaximumWidth(190)

    # Secuenciador MIDI real: 16×6 botones siempre visibles (18 px), sin scroll.
    for buttons in studio.step_buttons.values():
        for button in buttons:button.setFixedSize(18,19)
    for attr in ('seq_bpm','seq_velocity','seq_swing'):
        field=getattr(studio,attr)
        field.setMinimumWidth(0)
        field.setMaximumWidth(155)
        field.setFixedHeight(22)
        field.slider.setMinimumWidth(43)
        field.slider.setMaximumWidth(72)
        field.spin.setFixedWidth(65)
    studio.pattern_presets.layout().setContentsMargins(2,0,2,0)
    studio.pattern_presets.setMaximumHeight(26)

    # Compactación REAL del secuenciador: toda la matriz 6×16 y cuatro
    # ajustes en una sola línea, no una altura de 420 px de otra ventana.
    seqpage=studio.dashboard_sections[3].layout().itemAt(1).widget()
    seqlay=seqpage.layout()
    seqlay.setSpacing(1)
    seqlay.setContentsMargins(2,0,2,0)
    toolbar=seqlay.itemAt(0).layout()
    seqtools=(studio.seq_bpm,studio.seq_velocity,studio.seq_swing,studio.seq_bars)
    labels=[]
    for idx,tool in enumerate(seqtools):
        row,col=1+idx//2,(idx%2)*2
        labels.append(toolbar.itemAtPosition(row,col).widget())
    caption=toolbar.itemAtPosition(0,0).widget()
    caption.hide()
    for label,tool in zip(labels,seqtools):
        toolbar.removeWidget(label)
        toolbar.removeWidget(tool)
    seqlay.removeItem(toolbar)
    toolbar_compact=QHBoxLayout()
    toolbar_compact.setSpacing(3)
    for label,tool in zip(labels,seqtools):
        label.setStyleSheet('font-size:11px;color:#d7efff;')
        label.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        toolbar_compact.addWidget(label)
        toolbar_compact.addWidget(tool)
    studio.seq_bpm.setMaximumWidth(114)
    studio.seq_velocity.setMaximumWidth(114)
    studio.seq_swing.setMaximumWidth(105)
    studio.seq_bars.setMaximumWidth(63)
    studio.seq_bars.setFixedHeight(21)
    toolbar_compact.addStretch(1)
    seqlay.insertLayout(0,toolbar_compact)
    # El encabezado repetido y la explicación no son parámetros:
    # la documentación sigue en sus ayudas, sin desperdiciar filas.
    for q in seqpage.findChildren(QLabel):
        if q.text().startswith('Canal 10 General MIDI'):
            q.hide()
    matrix=None
    for i in range(seqlay.count()):
        layout=seqlay.itemAt(i).layout()
        if isinstance(layout,QGridLayout):matrix=layout;break
    if matrix is not None:
        matrix.setVerticalSpacing(0)
        matrix.setHorizontalSpacing(1)
        # El tema Qt daba 25-27 px a las etiquetas (¡más que las teclas!).
        # Cada una de las siete filas debe medir lo mismo que su botón.
        for i in range(matrix.count()):
            widget=matrix.itemAt(i).widget()
            if isinstance(widget,QLabel):
                widget.setFixedHeight(18)
                widget.setStyleSheet('font-size:11px;color:#b5eaff;padding:0;')
    for row in studio.step_buttons.values():
        for button in row:button.setFixedSize(18,18)
    studio.seq_preview.setFixedHeight(22)
    studio.seq_export.setFixedHeight(22)
    for widget in (studio.seq_preview,studio.seq_export):
        widget.setMaximumHeight(22)
    # La edición también disponía de márgenes de ventanas independientes.
    editorpage=studio.dashboard_sections[2].layout().itemAt(1).widget()
    editlay=editorpage.layout()
    editlay.setSpacing(1)
    editlay.setContentsMargins(2,0,2,0)
    for i in range(editlay.count()):
        layout=editlay.itemAt(i).layout()
        if isinstance(layout,QGridLayout):
            layout.setVerticalSpacing(1)
            layout.setHorizontalSpacing(3)
    studio.big_wave.setMinimumHeight(25)
    studio.big_wave.setMaximumHeight(28)
    studio.editor_render_btn.setFixedHeight(22)
    for action in editorpage.findChildren(QPushButton):
        if action.text().startswith('Escuchar original'):
            action.setFixedHeight(22)
    studio.edit_source.setFixedHeight(22)

    # Preescucha y presets completos en una SOLA fila inferior.
    preview=mod.preview
    preview.setParent(dense)
    preview.set_compact(True)
    preview.setMinimumHeight(0)
    # El título y el VU del reproductor estaban en filas separadas.
    # Recolocar el mismo VU REAL y las opciones junto a Play/Stop/posición.
    player_layout=preview.layout()
    title_row=player_layout.itemAt(0).layout()
    transport_row=player_layout.itemAt(2).layout()
    preview.options_button.setParent(preview)
    title_row.removeWidget(preview.options_button)
    preview.detail.hide()
    for i in range(title_row.count()):
        w=title_row.itemAt(i).widget()
        if w is not None:w.hide()
    player_layout.removeItem(title_row)
    transport_row.addWidget(preview.options_button)
    preview.options_button.setFixedSize(79,21)
    preview.options_button.setText('Ajustes ▾')
    def compact_audio_options_label(checked=False):
        preview.options_button.setText('Ajustes ▴' if preview._compact_expanded else 'Ajustes ▾')
    preview.options_button.clicked.connect(compact_audio_options_label)
    preview.play_button.setFixedHeight(21)
    preview.stop_button.setFixedHeight(21)
    preview.slider.setMinimumWidth(75)
    preview.slider.setMaximumWidth(168)
    meter=preview._measured_vu.meter
    player_layout.removeWidget(meter)
    meter.setParent(preview)
    meter.setFixedSize(120,21)
    transport_row.addWidget(meter)
    preview.setMaximumHeight(31)
    # Los ajustes de escucha, si se solicitan, siguen siendo accesibles.
    def preview_expand(checked=False):
        preview.setMaximumHeight(155 if preview._compact_expanded else 31)
    preview.options_button.clicked.connect(preview_expand)
    grid.addWidget(preview,2,0)
    presets=mod.full_presets
    presets.setParent(dense)
    presets.layout().setContentsMargins(3,0,3,0)
    presets.setFixedHeight(29)
    grid.addWidget(presets,2,1)

    # studio_workspace_cards envolvía tres grupos duplicados en enormes
    # SectionCard (50+50+78 px). Sus controles vivos ya están en la mesa.
    content=mod._advanced_parity_scroller.widget()
    for i in range(content.layout().count()):
        item=content.layout().itemAt(i)
        widget=item.widget() if item is not None else None
        if widget is not None and widget.objectName()=='studioCard':
            widget.hide()

    # Eliminar la cabecera y controles REPETIDOS de la pestaña, no su lógica.
    for widget in (mod.description,mod.compact_source,mod.source_panel,
                   mod.status,mod.studio,mod._advanced_parity_scroller.widget().layout().itemAt(0).widget()):
        widget.hide()
    # Botones globales ya están en la mesa: la barra anterior duplicaba.
    mod._advanced_parity_scroller.widget().layout().setSpacing(0)
    mod._advanced_parity_scroller.widget().layout().setContentsMargins(2,0,2,0)
    mod._advanced_parity_scroller.setFrameShape(QFrame.NoFrame)
    mod._advanced_parity_scroller.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    mod._advanced_parity_scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    # Bloque de selección complementario duplicaba seis casillas.
    other=main.advanced_tab_parity[main.studio_home.drum_stems_card]
    other.host.hide()
    other.host.setMinimumHeight(0)
    b.host.layout().setContentsMargins(0,0,0,0)
    b.host.layout().setSpacing(0)
    b.host.setStyleSheet('QFrame#tabAdvancedSharedHost {background:#041b3d;border:0;}')
    b.toggle.hide()
    b.host.layout().itemAt(0).layout().itemAt(0).widget().hide() # caption
    b.drum_direct_layout.setContentsMargins(0,0,0,0)
    b.drum_direct_layout.setSpacing(0)
    # El título de la pestaña no roba 24 px; todo dentro de una mesa.
    mod.setContentsMargins(0,0,0,0)

    # Alternar formato acoplado/ventana original, sin perder sus controles.
    compact=DrumDenseControls(mod,e,b)
    b.drum_density=compact.set_docked
    compact.set_docked(True)
    main.drum_flat_workspace=compact
    e.refresh_timer.timeout.connect(compact.refresh_waveforms)
    mod.resultsChanged.connect(compact.refresh_waveforms)
    main.drum_automatic_density=AutomaticDrumDensity(compact)
    main.drum_header_compactor=CompactBannerOnSmallDrum(main)
    # Un solo modo profesional siempre presente en la pestaña.
    return compact


class DrumDenseControls:
    def __init__(self,mod,exp,bridge):
        self.mod=mod
        self.exp=exp
        self.bridge=bridge
        self.original={}
        self.added={}
        self.labels=[]
        from drum_module import PARTS
        # Crear solo representaciones de onda y panoramas AUSENTES en la
        # ventana original. Se conectan a la misma mezcla y archivos reales.
        for part in PARTS:
            row=exp.drum_pieces[part]
            h=row['check'].parentWidget()
            line=exp.layout.itemAt(next(i for i in range(exp.layout.count())
                 if exp.layout.itemAt(i).layout() is not None and
                    exp.layout.itemAt(i).layout().indexOf(row['check'])>=0)).layout()
            wave=WaveCanvas(small=True,parent=exp.extra)
            wave.setFixedSize(68,17)
            wave.setToolTip('Onda REAL de '+part+'; clic para seleccionar canal')
            wave.clicked.connect(lambda position,p=part:mod.studio.select_channel(p))
            line.insertWidget(1,wave)
            pan=QSlider(Qt.Horizontal,exp.extra)
            pan.setRange(-100,100)
            pan.setValue(0)
            pan.setFixedSize(57,17)
            pan.setToolTip('Panorámica de '+part+' (-100 izquierda, +100 derecha)')
            pan.valueChanged.connect(lambda value,p=part:exp.set_drum_mix(p,'pan',value))
            line.insertWidget(7,pan)
            wave.hide();pan.hide()
            self.added[part]=(wave,pan)
            self.original[part]={k:(v.minimumWidth(),v.maximumWidth(),v.minimumHeight(),v.maximumHeight())
                for k,v in row.items() if isinstance(v,QWidget)}
        self.original['model']=(exp.drum_model_choice.minimumWidth(),exp.drum_model_choice.maximumWidth())
        self.original['source']=None
        for source,widget,typ in exp.proxies:
            if source is exp.home.drum_source:
                self.source_combo=widget
                self.original['source']=(widget.minimumWidth(),widget.maximumWidth())
                break
        self.original['buttons']={w:(w.text(),w.minimumWidth(),w.maximumWidth(),w.minimumHeight(),w.maximumHeight())
            for w in exp.extra.findChildren(QPushButton) if w is not exp.drum_model_choice}
        self.original['layout']=(exp.layout.contentsMargins(),exp.layout.spacing(),exp.extra.minimumHeight())
        self.notice_labels=[x for x in exp.extra.findChildren(QLabel)
            if x.text().startswith('MDX23C calcula') or x is exp.drum_mix_status]
        self.heading=[x for x in exp.extra.findChildren(QLabel)
            if x.text().startswith('PISTAS DE BATERÍA · SELECCIÓN')]
        self.header_labels=[]
        for i in range(exp.layout.count()):
            entry=exp.layout.itemAt(i)
            layout=entry.layout() if entry else None
            if layout is not None and any(
                isinstance(layout.itemAt(j).widget(),QLabel)
                and layout.itemAt(j).widget().text()=='Guardar / pista'
                for j in range(layout.count())):
                self.header_labels.append(layout)
        # Botones de guardado y estado ocupan filas vacías. En modo experto
        # se reubican junto a sus acciones, sin destruir conexiones.
        self.action_layout=None
        self.save_layout=None
        self.model_layout=None
        for i in range(exp.layout.count()):
            entry=exp.layout.itemAt(i)
            lay=entry.layout() if entry else None
            if lay is None:continue
            widgets=[lay.itemAt(j).widget() for j in range(lay.count())]
            texts=[w.text() for w in widgets if isinstance(w,QPushButton)]
            if 'Importar batería…' in texts:self.action_layout=lay
            if 'Guardar pistas marcadas…' in texts:self.save_layout=lay
            if exp.drum_model_choice in widgets:self.model_layout=lay
        self.save_button=next(w for w in self.original['buttons'] if
                              self.original['buttons'][w][0]=='Guardar pistas marcadas…')
        self.full_button=next(w for w in self.original['buttons'] if
                              self.original['buttons'][w][0]=='Mezclador / editor completo')
        self.model_status_index=exp.layout.indexOf(exp.drum_model_status)
        # Conserva los encabezados originales, acorta su texto en el modo pestaña.
        self.docked=None

    @staticmethod
    def size(w,width,height=20):
        w.setMinimumSize(width,height)
        w.setMaximumSize(width,height)

    def set_docked(self,docked):
        if self.docked is bool(docked):return
        self.docked=bool(docked)
        exp=self.exp
        if docked:
            self.save_layout.removeWidget(self.save_button)
            self.action_layout.insertWidget(self.action_layout.count()-1,self.save_button)
            self.full_button.hide()  # No repetir navegación al mismo editor.
            exp.layout.removeWidget(exp.drum_model_status)
            self.model_layout.insertWidget(self.model_layout.count()-1,exp.drum_model_status)
            exp.layout.setContentsMargins(5,1,5,1)
            exp.layout.setSpacing(1)
            exp.extra.setMinimumHeight(0)
            exp.extra.setMaximumHeight(16777215)
            for label in self.notice_labels:label.hide()
            exp.status.hide();exp.details.hide()
            for label in self.heading:label.hide()
            self.size(self.source_combo,180,21)
            self.size(exp.drum_model_choice,235,21)
            for w in (self.source_combo,exp.drum_model_choice):
                w.setProperty('preserveComboWidth',True)
            exp.drum_model_status.setFixedHeight(17)
            exp.drum_model_status.setFixedWidth(55)
            exp.drum_model_status.setStyleSheet('font-size:10px;color:#a8d9ef;')
            for button,(text,*_) in self.original['buttons'].items():
                short={'Importar batería…':'Cargar batería','Cambiar / instalar IA…':'Motor IA',
                  'Importar modelo…':'Importar IA','Desglosar':'Separar','■ Cancelar':'Cancelar',
                  'Guardar pistas marcadas…':'Guardar marcadas',
                  'Mezclador / editor completo':'Mesa completa'}.get(text,text)
                button.setText(short)
                button.setFixedHeight(21)
                if text in ('Desglosar','■ Cancelar','Importar modelo…'):
                    button.setMaximumWidth(95)
                elif text=='Cambiar / instalar IA…':button.setMaximumWidth(88)
                elif text=='Importar batería…':button.setMaximumWidth(120)
                elif text=='Guardar pistas marcadas…':button.setMaximumWidth(122)
                elif text=='Mezclador / editor completo':button.setMaximumWidth(135)
            for part,row in exp.drum_pieces.items():
                sizes={'check':(83,20),'progress':(105,13),'state':(58,18),
                       'listen':(28,20),'gain':(83,15),'gain_txt':(37,18),
                       'mute':(25,20),'solo':(25,20)}
                for key,(width,height) in sizes.items():
                    self.size(row[key],width,height)
                wave,pan=self.added[part]
                wave.show();pan.show()
                wave.setFixedSize(68,17)
                pan.setFixedSize(57,17)
                line=row['check'].parentWidget().layout() if False else None
            # Las cabeceras se alinean con su propia columna, sin huecos.
            for layout in self.header_labels:
                names=('Pista','Onda','IA','Estado','▶','Vol.','dB','Pan','M','S')
                sizes=(83,68,105,58,28,83,37,57,25,25)
                # Se aprovechan widgets originales y se insertan dos rótulos.
                labels=[layout.itemAt(i).widget() for i in range(layout.count())
                        if isinstance(layout.itemAt(i).widget(),QLabel)]
                while len(labels)<len(names):
                    x=QLabel('',exp.extra);labels.append(x);layout.insertWidget(len(labels)-1,x)
                for name,width,label in zip(names,sizes,labels):
                    label.setText(name);label.setFixedWidth(width)
                    label.setFixedHeight(17)
                    label.setStyleSheet('color:#a6ddec;font-size:10px;')
            exp.extra.setStyleSheet('''QFrame#floatPanel QPushButton {padding:0 3px;font-size:11px;}
                 QFrame#floatPanel QCheckBox {font-size:11px;}
                 QFrame#floatPanel QProgressBar {border:1px solid #237c9d;border-radius:3px;}''')
        else:
            self.action_layout.removeWidget(self.save_button)
            self.save_layout.insertWidget(0,self.save_button)
            self.model_layout.removeWidget(exp.drum_model_status)
            exp.layout.insertWidget(self.model_status_index,exp.drum_model_status)
            self.full_button.show()
            margin,spacing,height=self.original['layout']
            exp.layout.setContentsMargins(margin)
            exp.layout.setSpacing(spacing)
            exp.extra.setMinimumHeight(height)
            exp.extra.setStyleSheet('')
            for label in self.notice_labels:label.show()
            exp.status.show();exp.details.show()
            for label in self.heading:label.show()
            for w,settings in ((self.source_combo,self.original['source']),
                               (exp.drum_model_choice,self.original['model'])):
                w.setMinimumWidth(settings[0]);w.setMaximumWidth(settings[1])
            exp.drum_model_status.setFixedHeight(20)
            exp.drum_model_status.setMaximumWidth(16777215)
            exp.drum_model_status.setStyleSheet('')
            for button,(text,minw,maxw,minh,maxh) in self.original['buttons'].items():
                button.setText(text)
                button.setMinimumWidth(minw);button.setMaximumWidth(maxw)
                button.setMinimumHeight(minh);button.setMaximumHeight(maxh)
            for part,row in exp.drum_pieces.items():
                for key,spec in self.original[part].items():
                    w=row[key];w.setMinimumWidth(spec[0]);w.setMaximumWidth(spec[1]);w.setMinimumHeight(spec[2]);w.setMaximumHeight(spec[3])
                wave,pan=self.added[part];wave.hide();pan.hide()
            for layout in self.header_labels:
                old=('Guardar / pista','Avance IA común (real)','Estado','Play','Nivel','M','S')
                sizes=(105,300,77,43,250,31,31)
                for i,(name,width) in enumerate(zip(old,sizes)):
                    widget=layout.itemAt(i).widget()
                    if isinstance(widget,QLabel):widget.setText(name);widget.setFixedWidth(width)
                for j in range(len(old),layout.count()):
                    widget=layout.itemAt(j).widget()
                    if widget is not None:widget.hide()
        if docked:self.refresh_waveforms()

    def refresh_waveforms(self,*args):
        if not self.docked:return
        self.exp.drum_model_status.setText('LISTO' if self.mod.model_ready()
                and self.mod.engine() else 'SIN IA')
        self.exp.drum_model_status.setToolTip(self.mod.model_state.text())
        for part,(wave,pan) in self.added.items():
            path=self.exp._drum_source(part)
            if getattr(wave,'_dense_file',None)!=str(path or ''):
                wave._dense_file=str(path or '')
                wave.set_file(path)
            desired=self.mod.studio.channels[part]['pan']
            if pan.value()!=desired:
                locked=pan.blockSignals(True);pan.setValue(desired);pan.blockSignals(locked)
            pan.setEnabled(path is not None)

class AutomaticDrumDensity(QObject):
    """Aprovecha el ancho libre, sin que etiquetas y controles se separen."""
    def __init__(self,desk):
        super().__init__(desk.exp.extra)
        self.desk=desk
        self._last=None
        desk.exp.extra.installEventFilter(self)
        QTimer.singleShot(0,self.update)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Resize:
            QTimer.singleShot(0,self.update)
        return False

    def update(self):
        desk=self.desk
        if not desk.docked:return
        width=desk.exp.extra.width()
        # Los controles cambian de tamaño JUNTOS con su encabezado.
        if width>=900:
            lengths={'wave':83,'progress':137,'gain':138,'pan':118}
        elif width>=750:
            lengths={'wave':77,'progress':120,'gain':122,'pan':94}
        elif width>=645:
            lengths={'wave':62,'progress':110,'gain':105,'pan':75}
        else:
            lengths={'wave':49,'progress':96,'gain':88,'pan':54}
        tier=tuple(lengths.values())
        if tier==self._last:return
        self._last=tier
        for part,row in desk.exp.drum_pieces.items():
            wave,pan=desk.added[part]
            wave.setFixedWidth(lengths['wave'])
            row['progress'].setFixedWidth(lengths['progress'])
            row['gain'].setFixedWidth(lengths['gain'])
            pan.setFixedWidth(lengths['pan'])
        for layout in desk.header_labels:
            new_widths=(83,lengths['wave'],lengths['progress'],58,28,
                        lengths['gain'],37,lengths['pan'],25,25)
            labels=[layout.itemAt(i).widget() for i in range(layout.count())
                    if isinstance(layout.itemAt(i).widget(),QLabel)]
            for label,px in zip(labels,new_widths):label.setFixedWidth(px)


# Ajusta la cabecera solo en ventanas bajas, conservando sus acciones.
# En una pantalla alta su diseño original sigue intacto.
from PySide6.QtCore import QObject,QEvent

class CompactBannerOnSmallDrum(QObject):
    def __init__(self,main):
        super().__init__(main)
        self.main=main
        self.banner=main.studio_banner
        self.active=None
        main.tabs.currentChanged.connect(lambda *_:self.sync())
        main.installEventFilter(self)
        self.sync()

    def eventFilter(self,obj,event):
        if obj is self.main and event.type()==QEvent.Resize:
            QTimer.singleShot(0,self.sync)
        return False

    def sync(self):
        main=self.main
        if main.isHidden():return
        # En 1080p reducir solo la altura decorativa. El logo, las acciones
        # y los textos de marca siguen visibles y funcionales.
        compact=(main.tabs.currentWidget() is main.drum_module and main.height()<=1080)
        if self.active is compact:return
        self.active=compact
        b=self.banner
        b.drum_compact=compact
        if compact:
            b.logo.setFixedSize(98,68)
            b.logo.show()
            for label in b.text_panel.findChildren(QLabel):label.show()
            b.setFixedHeight(75)
        else:
            b.logo.setFixedSize(198,137)
            b.logo.show()
            for label in b.text_panel.findChildren(QLabel):label.show()
            b.setFixedHeight(146)
        for button in b.toolbar_buttons:
            button.setProperty('compactDrumHeader',compact)
            button.setFixedHeight(57 if compact else 87)
        b.help_toggle.setProperty('compactDrumHeader',compact)
        b.help_toggle.setFixedHeight(57 if compact else 87)
        b.help_toggle.update()
        b.heading.setStyleSheet('font-size:25px;font-weight:900;' if compact else
                                'font-size:40px;font-weight:900;')
        b.updateGeometry()
        b.update()
