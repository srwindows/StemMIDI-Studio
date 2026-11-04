"""Sincronización bidireccional Inicio ↔ pestañas, sin estado paralelo.

Cada control de Inicio es una vista de los mismos widgets/datos del módulo
completo. La escritura de retorno bloquea señales sólo para impedir bucles.
"""
from pathlib import Path
from PySide6.QtCore import QObject, QSignalBlocker, QTimer, Qt, QItemSelectionModel

STEM_KEYS={"Voces":"Voz","Batería":"Batería","Bajo":"Bajo",
           "Guitarra":"Guitarra","Piano":"Piano","Otros":"Otros","Viento":"Viento"}


class HomeTabSynchronizer(QObject):
    def __init__(self,main):
        super().__init__(main)
        self.main=main
        self.h=main.studio_home
        self.w=main.workbench
        self._syncing_mixer=False
        self._current_mixer=None
        self._notes_sync_timer=QTimer(self)
        self._notes_sync_timer.setSingleShot(True)
        self._notes_sync_timer.setInterval(90)
        self._notes_sync_timer.timeout.connect(self._sync_live_piano)
        self.pairs=[]
        self.routes={}
        self._setup_routes()
        self._setup_controls()
        self._setup_results()
        main.tabs.currentChanged.connect(self._tab_changed)
        self._tab_changed(main.tabs.currentIndex())

    @staticmethod
    def _set(widget,what,value):
        if what=="index":
            if widget.currentIndex()!=value:
                with QSignalBlocker(widget):widget.setCurrentIndex(value)
        elif what=="value":
            if widget.value()!=value:
                with QSignalBlocker(widget):widget.setValue(value)
        elif what=="checked":
            if widget.isChecked()!=value:
                with QSignalBlocker(widget):widget.setChecked(value)

    def pair(self,home,tab,kind="index",on_tab=None):
        """Enlazar de forma inmediata, sin depender de temporizadores."""
        signal={"index":"currentIndexChanged","value":"valueChanged",
                "checked":"toggled"}[kind]
        def forward():
            self._set(tab,kind,getattr(home,
                {"index":"currentIndex","value":"value","checked":"isChecked"}[kind])())
        def backward():
            self._set(home,kind,getattr(tab,
                {"index":"currentIndex","value":"value","checked":"isChecked"}[kind])())
            if on_tab is not None:on_tab()
        getattr(home,signal).connect(lambda *_:forward())
        getattr(tab,signal).connect(lambda *_:backward())
        self.pairs.append((home,tab,kind))
        backward()

    def combo_by_data(self,home,tab,remote_value=None):
        """Los textos pueden diferir entre la tarjeta y la pestaña."""
        def read(widget):
            return widget.currentData() if remote_value is None else remote_value(widget)
        def set_data(widget,key):
            i=widget.findData(key)
            if i<0:i=widget.findText(str(key))
            if i>=0:self._set(widget,"index",i)
        home.currentIndexChanged.connect(lambda _:set_data(tab,read(home)))
        tab.currentIndexChanged.connect(lambda _:set_data(home,read(tab)))
        set_data(home,read(tab))

    def _setup_routes(self):
        h=self.h;m=self.main;w=self.w
        self.routes={
            h.mon_card:m.monitor_page,
            h.sep_card:w.separation_tab,
            h.midi_card:w.midi_tab,
            h.result_card:m.results_tab,
            h.wave_card:m.monitor_page,
            h.drum_card:m.drum_module,
            h.track_card:w.separation_tab,
            h.mix_card:m.mixer_placeholder,
            h.piano_card:w.piano,
            h.vocal_card:m.vocal_module,
            h.drum_stems_card:m.drum_module,
            h.info_card:m.midi_audio_tab,  # el MISMO conversor de la ventana
        }
        for card in self.routes:
            # La cabecera, no el contenido, navega a su módulo.
            # Corrige el antiguo tabs.widget(0), que apuntaba a Inicio.
            card.header.clicked.connect(
                lambda checked=False,c=card:self.open_tab(c))

    def tab_for(self,card):
        return (self.w.mixer if card is self.h.mix_card and self.w.mixer is not None
                else self.routes.get(card))

    def open_tab(self,card):
        target=self.tab_for(card)
        if target is None:return
        if self.main.tabs.indexOf(target)<0:
            # Mezclador dinámico: la pestaña resumida es el punto de entrada.
            target=self.routes.get(card)
        if target is not None and self.main.tabs.indexOf(target)>=0:
            self.main.tabs.setCurrentWidget(target)
            self.sync_all()

    def _setup_controls(self):
        h=self.h;m=self.main;w=self.w
        # Captura: formato/calidad/fuente y ganancia/balance usan el mismo motor.
        self.pair(h.format,m.format)
        self.pair(h.quality,m.capture_rate)
        self.combo_by_data(h.input,m.sources)
        # Separación: modelo, selecciones y motor originales.
        self.combo_by_data(h.model,w.separator.profile,
                           lambda c:c.currentText() if c is w.separator.profile else c.currentData())
        w.separator.profile.currentIndexChanged.connect(
            lambda *_:h._sync_stem_capabilities())
        for name,home_check in h.stem_checks.items():
            source=w.separator.stem_checks.get(STEM_KEYS[name])
            if source is None:continue
            self.pair(home_check,source,"checked",
                      lambda n=name,c=home_check:
                        self._on_sep_tab_check(n,c.isChecked()))
        # Audio→MIDI: parámetros y presets, mismo convertidor/IA.
        conv=w.converter
        self.combo_by_data(h.midi_preset,conv.presets.choices)
        for name,widget in h.midi_sliders.items():
            self.pair(widget,getattr(conv,name),"value")
        self.combo_by_data(h.refine,conv.refinement)
        self.combo_by_data(h.quant,conv.quant)
        self.pair(h.chords_check,conv.detect_chords,"checked")
        # La selección de IA por la pestaña modifica checkboxes y rutas
        # sin emitir un currentIndexChanged sobre el combo de Inicio.
        conv.piano_specialist.toggled.connect(lambda *_:h._sync_midi_controls())
        conv.quant.currentIndexChanged.connect(lambda *_:h._sync_midi_controls())
        conv.audio_path.textChanged.connect(lambda *_:h._sync_midi_stems(force=True))
        # Desglose: origen real y disponibilidad, no copias de audios.
        m.drum_module.input.textChanged.connect(lambda *_:h._sync_drum_module(force=True))
        # Afinación: nota, escala, intensidad y origen originales.
        voc=m.vocal_module
        self.pair(h.vocal_tonic,voc.tonic)
        self.pair(h.vocal_scale,voc.scale)
        self.pair(h.vocal_strength,voc.strength,"value")
        voc.input.textChanged.connect(lambda *_:h._sync_vocal_module(force=True))
        # Piano Roll: rejilla, velocidad y archivo MIDI.
        self.combo_by_data(h.grid_choice,w.piano.grid,
                           lambda c:c.currentText())
        self.pair(h.note_velocity,w.piano.velocity,"value")
        h.midi_choice.currentIndexChanged.connect(lambda *_:self._home_midi_selected())
        w.piano.midiOpened.connect(self._editor_midi_opened)
        w.piano.notesChanged.connect(self._notes_sync_timer.start)

    def _on_sep_tab_check(self,name,checked):
        # La selección en la pestaña actualiza también el estado usado para
        # guardar resultados en Inicio (no basta con mover la casilla).
        self.h._stem_selection[name]=checked
        self.h.apply_stem_visibility()

    def _home_midi_selected(self):
        if self.h._loading:return
        path=self.h.midi_choice.currentData()
        if not path or not Path(path).is_file():return
        editor=self.w.piano
        if editor.current_path is not None and editor.current_path==Path(path).resolve():
            return
        # Respetar el diálogo de cambios MIDI sin guardar del editor.
        if editor.open_midi(path) is False and editor.current_path:
            self._editor_midi_opened(str(editor.current_path))

    def _editor_midi_opened(self,path):
        if not path:return
        file=Path(path).resolve()
        h=self.h
        h.selected_midi=file
        idx=h.midi_choice.findData(str(file))
        if idx>=0:self._set(h.midi_choice,"index",idx)
        h.piano_preview.set_midi(file)
        h._roll_scroll_changed(0)
        h._update_midi_stats(file)
        h.piano_card.header.setText("Piano Roll · "+file.name)
        self._notes_sync_timer.start()

    def _sync_live_piano(self):
        editor=self.w.piano
        if editor.midi is None or editor.current_path is None:return
        home=self.h
        home.piano_preview.set_live_editor(editor)
        notes=sum(len(track["notes"]) for track in editor.tracks)
        home.note_info.setText(f"Notas: {notes}")
        suffix=" · sin guardar" if editor.dirty else ""
        home.piano_card.header.setText(
            "Piano Roll · "+editor.current_path.name+suffix)

    def _setup_results(self):
        h=self.h;r=self.main.results_tab
        h.files.itemSelectionChanged.connect(self._home_result_selection)
        r.table.itemSelectionChanged.connect(self._tab_result_selection)

    def _select_result_rows(self,table,paths):
        if table.selectionModel() is None:return
        selection=table.selectionModel()
        with QSignalBlocker(table),QSignalBlocker(selection):
            table.clearSelection()
            for row in range(table.rowCount()):
                item=table.item(row,0)
                if item is None:continue
                raw=(item.data(Qt.UserRole) or item.toolTip())
                if raw in paths:
                    selection.select(table.model().index(row,0),
                        QItemSelectionModel.Select|QItemSelectionModel.Rows)

    def _home_result_selection(self):
        selected={str(self.h.files.item(r.row(),0).data(Qt.UserRole))
                  for r in self.h.files.selectionModel().selectedRows()
                  if self.h.files.item(r.row(),0) is not None}
        self._select_result_rows(self.main.results_tab.table,selected)

    def _tab_result_selection(self):
        selected={str(self.main.results_tab._paths[row.row()])
                  for row in self.main.results_tab.table.selectionModel().selectedRows()
                  if 0<=row.row()<len(self.main.results_tab._paths)}
        self._select_result_rows(self.h.files,selected)
        self.h.file_selected()

    def bind_mixer(self):
        mixer=self.w.mixer
        if mixer is None or mixer is self._current_mixer:return
        self._current_mixer=mixer
        # El mezclador dinámico se construye con ajustes propios; no
        # sobrescribir presets de proyecto. Sólo enlazar controles.
        for row in mixer.rows:
            row["slider"].valueChanged.connect(
                lambda *_:self.sync_mixer_to_home())
            for key in ("mute","solo"):
                row[key].toggled.connect(
                    lambda checked,part=row,mode=key:
                        self._mixer_ms_exclusive(part,mode,checked))
        self.sync_mixer_to_home()

    def _mixer_ms_exclusive(self,row,mode,checked):
        # Una misma pista no puede estar simultáneamente M y S.
        if checked:
            other=row["solo" if mode=="mute" else "mute"]
            with QSignalBlocker(other):other.setChecked(False)
        self.sync_mixer_to_home()

    def sync_mixer_to_home(self):
        # Durante la propagación Inicio -> Mezclador no se debe devolver
        # a Inicio un estado intermedio M/S. Esto reactivaba S al quitar M.
        if self._syncing_mixer:return
        mixer=self.w.mixer
        if mixer is None or mixer is not self._current_mixer:return
        h=self.h
        self._syncing_mixer=True
        try:
            for name in h.mixer_rows:
                group=[row for row in mixer.rows if h._stem_for(row["path"])==name]
                if not group:continue
                levels=[row["slider"].value() for row in group]
                solos=[row["solo"].isChecked() for row in group]
                mutes=[row["mute"].isChecked() for row in group]
                fader=h.mixer_rows[name]["fader"]
                if len(set(levels))==1:
                    self._set(fader,"value",levels[0])
                    h.change_mix(name,levels[0])
                else:
                    self._set(fader,"value",round(sum(levels)/len(levels)))
                    h.mixer_rows[name]["readout"].setText("Mixto")
                for key,values in (("solo",solos),("mute",mutes)):
                    control=h.track_rows[name][key]
                    self._set(control,"checked",all(values))
                    # Etiquetas siempre M y S, sin abreviaturas ambiguas.
                    control.setText("S" if key=="solo" else "M")
                    control.setToolTip(
                        "Estado mixto: comprueba las pistas individuales en Mezclador"
                        if len(set(values))>1 else
                        "Control de grupo: aplica a todas las pistas de esta familia")
        finally:self._syncing_mixer=False
        # Cuando se cambia M/S o ganancia DESDE la pestaña Mezclador,
        # las señales de los botones compartidos se bloquean para evitar
        # bucles; el motor de escucha sí debe recibir el nuevo estado.
        h.sync_active_stem_gain()
        h.update_stem_header()

    def sync_all(self):
        h=self.h
        for home,tab,kind in self.pairs:
            self._set(home,kind,getattr(tab,
                {"index":"currentIndex","value":"value","checked":"isChecked"}[kind])())
        h._sync_monitor()
        h._sync_separator()
        h._sync_midi_stems()
        h._sync_midi_controls()
        h._sync_drum_module(force=True)
        h._sync_vocal_module(force=True)
        self.bind_mixer()
        self.sync_mixer_to_home()

    def _tab_changed(self,index):
        # Esperar al último ajuste de layout/carga de pista y actualizar
        # la portada, tanto si el usuario pulsa pestaña como si usa cabecera.
        QTimer.singleShot(0,self.sync_all)
