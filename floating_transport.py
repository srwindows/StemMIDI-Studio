"""Transporte local para las tarjetas flotantes de Inicio.

No cambia pestañas. Utiliza un único reproductor real, compartido con
Inicio; VU por pista sólo mide los datos de audio PCM efectivamente en
reproducción. Nunca representa silencios con barras inventadas.
"""
from pathlib import Path
import math

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,
                               QLabel,QPushButton,QSlider,QComboBox,QCheckBox,
                               QProgressBar,QSizePolicy)

STEMS=("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros")
DRUMS=("Bombo","Caja","Toms","Charles","Ride","Crash")
SEP_STEMS=STEMS+("Voz principal","Coros","Voz masculina","Voz femenina")
KINDS=("monitor","sep","midi","results","wave","drums","tracks",
       "mixer","piano","vocal","drum_stems","info")
MULTI=("sep","tracks","mixer","drums","drum_stems")

class FloatingTransport(QFrame):
    def __init__(self,home,kind,parent=None):
        super().__init__(parent)
        self.home=home
        self.kind=kind
        self.setObjectName("floatingTransportPanel")
        if kind=="mixer":
            from project_mixer_expanded import ProjectMixerTransport
            self.project_mixer_strip=ProjectMixerTransport(
                home._floating_manager.other_expanders[home.mix_card].project_mixer,self)
            frame=QVBoxLayout(self)
            frame.setContentsMargins(0,0,0,0)
            frame.setSpacing(0)
            frame.addWidget(self.project_mixer_strip)
            self.play=self.project_mixer_strip.play
            self.pause=self.project_mixer_strip.pause
            self.stop=self.project_mixer_strip.stop
            self.timeline=self.project_mixer_strip.timeline
            self.track_select=None
            self.vus={}
            return
        self.setStyleSheet("""
            QFrame#floatingTransportPanel{background:#041b43;border:1px solid #2bb1fc;
                border-radius:8px;}
            QFrame#floatingTransportPanel QLabel{color:#e0f8ff;}
            QFrame#floatingTransportPanel QPushButton{min-height:26px;border-radius:5px;}
            QFrame#floatingTransportPanel QProgressBar{
                border:1px solid #2bb1fc;background:#031535;border-radius:3px;
                text-align:center;color:#e0f8ff;min-height:9px;max-height:12px;}
            QFrame#floatingTransportPanel QProgressBar::chunk{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #137ec4,stop:1 #58f1f7);}
        """)
        box=QVBoxLayout(self)
        if kind=="sep":
            # Reservar espacio vertical al formulario ampliado, sin scroll.
            box.setContentsMargins(7,4,7,4)
            box.setSpacing(2)
        else:
            box.setContentsMargins(9,7,9,7)
            box.setSpacing(4)
        self._root_box=box
        header=QHBoxLayout();header.setSpacing(6)
        self._header_caption=QLabel("TRANSPORTE · ESCUCHA EN INICIO")
        header.addWidget(self._header_caption)
        header.addStretch()
        self.state=QLabel("Sin audio")
        self.state.setMaximumWidth(300)
        header.addWidget(self.state)
        box.addLayout(header)
        self._header_row=header
        self.track_select=None
        self.sep_checks={}
        if kind in MULTI and kind!="tracks":
            selector=QHBoxLayout()
            self._select_caption=QLabel("Pista")
            selector.addWidget(self._select_caption)
            self.track_select=QComboBox(self)
            names=DRUMS if kind in ("drums","drum_stems") else (("Original",)+SEP_STEMS if kind=="sep" else STEMS)
            if kind=="tracks":
                self.track_select.addItem("— Elige una pista —")
            self.track_select.addItems(names)
            if kind=="tracks":
                # Una nueva ventana no debe seleccionar Voces por defecto.
                self.track_select.setCurrentIndex(0)
                self.track_select.setToolTip(
                    "Selecciona una pista explícitamente; Play nunca elige Voces automáticamente")
                self.track_select.currentTextChanged.connect(self._track_selection_changed)
            self.track_select.setMinimumWidth(125)
            selector.addWidget(self.track_select)
            selector.addStretch()
            box.addLayout(selector)
            if kind=="sep":
                # La elección de pistas a ESCUCHAR es independiente de
                # las casillas del modelo de IA para EXTRAER.
                self.track_select.hide()
                self._select_caption.hide()
                self.sep_original=QCheckBox("Original",self)
                self.sep_original.setChecked("Original" in self.home._sep_listen.selected)
                selector.insertWidget(0,self.sep_original)
                selector.insertWidget(1,QLabel("Pistas marcadas para escuchar · "
                                              "separadas de las casillas de extracción"))
                self.sep_original.toggled.connect(
                    lambda selected:self.home._sep_listen.set_enabled("Original",selected))
        bar=QHBoxLayout();bar.setSpacing(5)
        self.play=QPushButton("▶ Play",self)
        self.pause=QPushButton("Ⅱ",self)
        self.stop=QPushButton("■",self)
        for w in (self.play,self.pause,self.stop):
            w.setCursor(Qt.PointingHandCursor)
            bar.addWidget(w)
        self.timeline=QSlider(Qt.Horizontal,self)
        self.timeline.setRange(0,1000)
        self.timeline.setTracking(False)
        self.timeline.sliderReleased.connect(self.seek)
        bar.addWidget(self.timeline,1)
        self.clock=QLabel("00:00 / 00:00")
        self.clock.setMinimumWidth(118)
        bar.addWidget(self.clock)
        box.addLayout(bar)
        self._controls_row=bar
        self.vus={}
        self.vu_labels={}
        self.master_labels={}
        if kind in MULTI and kind!="tracks":
            # Medidores profesionales compactos, DOS COLUMNAS. Ninguna
            # barra se expande a toda la anchura de la ventana flotante.
            # Mantener los QProgressBar y su señal original intactos.
            meter_area=QFrame(self)
            meter_area.setObjectName("compactVuPanel")
            meter_area.setStyleSheet("""
                QFrame#compactVuPanel {
                    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #092a62,stop:1 #051538);
                    border:1px solid #218cef;border-radius:7px;
                }
                QFrame#compactVuPanel QLabel {color:#def6ff;font-size:12px;}
                QFrame#compactVuPanel QLabel#vuCaption {
                    color:#80f2ff;font-weight:800;font-size:11px;
                }
                QFrame#compactVuPanel QLabel#vuLevel {
                    color:#86dbfa;font-weight:700;font-size:11px;
                }
                QFrame#compactVuPanel QProgressBar {
                    min-height:11px;max-height:11px;
                    border:1px solid #24b9f1;border-radius:4px;
                    background:#021632;
                }
                QFrame#compactVuPanel QProgressBar::chunk {
                    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 #006eff,stop:.5 #00caff,stop:1 #80ffff);
                    border-radius:3px;
                }
            """)
            meter_area.setMaximumWidth(750)
            outer=QVBoxLayout(meter_area)
            if kind=="sep":
                outer.setContentsMargins(10,5,10,5)
                outer.setSpacing(2)
            else:
                outer.setContentsMargins(11,7,11,9)
                outer.setSpacing(5)
            caption=QLabel("VU MÁSTER · L / R",meter_area)
            caption.setObjectName("vuCaption")
            outer.addWidget(caption)
            master_grid=QGridLayout()
            master_grid.setHorizontalSpacing(24)
            master_grid.setVerticalSpacing(2 if kind=="sep" else 5)
            if kind=="sep":
                master_grid.setColumnStretch(0,1)
                master_grid.setColumnStretch(1,1)
            self.master_vus={}
            for column,channel in enumerate(("L","R")):
                cell,meter,number=self._compact_vu_cell(
                    meter_area,"Máster "+channel,170 if kind=="sep" else 190,
                    label_width=120 if kind=="sep" else 76)
                master_grid.addWidget(cell,0,column)
                self.master_vus[channel]=meter
                self.master_labels[channel]=number
            outer.addLayout(master_grid)
            caption=QLabel("VU POR PISTA · SEÑAL REAL",meter_area)
            caption.setObjectName("vuCaption")
            outer.addWidget(caption)
            tracks=(DRUMS if kind in ("drums","drum_stems")
                    else SEP_STEMS if kind=="sep" else STEMS)
            left_count=(len(tracks)+1)//2
            compact_grid=QGridLayout()
            compact_grid.setHorizontalSpacing(24)
            compact_grid.setVerticalSpacing(0 if kind=="sep" else 4)
            if kind=="sep":
                compact_grid.setColumnStretch(0,1)
                compact_grid.setColumnStretch(1,1)
            for index,name in enumerate(tracks):
                column=0 if index<left_count else 1
                row=index if column==0 else index-left_count
                cell,meter,number=self._compact_vu_cell(
                    meter_area,name,170 if kind=="sep" else 190,
                    label_width=120 if kind=="sep" else 76)
                if kind=="sep":
                    cell.setFixedHeight(19)
                    tag=next((w for w in cell.findChildren(QLabel)
                              if w.text()==name),None)
                    if tag is not None:
                        tag.hide()
                    selector=QCheckBox(name,cell)
                    selector.setFixedWidth(120)
                    selector.setToolTip(name+" · Marcado: suena · Desmarcado: mute")
                    cell.layout().insertWidget(0,selector)
                    self.sep_checks[name]=selector
                    selector.toggled.connect(
                        lambda checked,n=name:self.home._sep_listen.set_enabled(n,checked))
                compact_grid.addWidget(cell,row,column)
                self.vus[name]=meter
                self.vu_labels[name]=number
            outer.addLayout(compact_grid)
            box.addWidget(meter_area,0,Qt.AlignHCenter)
            self.compact_vu_panel=meter_area
        elif kind=="tracks":
            # La pantalla de pistas no duplica el mezclador ni los VU.
            pass
        elif kind=="vocal":
            # VU de PCM REAL L/R, en sentido horizontal, uno debajo del
            # otro, inmediatamente después del desplazamiento temporal.
            # No dejarlos colgando debajo de la ventana.
            meter_column=QVBoxLayout()
            meter_column.setContentsMargins(0,0,0,0)
            meter_column.setSpacing(0)
            self._vocal_vu_area=QFrame(self)
            self._vocal_vu_area.setObjectName("vocalVuRightOfSeek")
            self._vocal_vu_area.setStyleSheet(
                "QFrame#vocalVuRightOfSeek{background:#061a3a;"
                "border:1px solid #2fb1ef;border-radius:4px;}"
                "QFrame#vocalVuRightOfSeek QLabel{font-size:10px;color:#bceaff;}"
                "QFrame#vocalVuRightOfSeek QProgressBar{"
                "border:1px solid #285b89;background:#04152c;"
                "height:9px;min-height:9px;max-height:9px;}"
                "QFrame#vocalVuRightOfSeek QProgressBar::chunk{"
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "stop:0 #1b9bdc,stop:.7 #48e6a2,stop:.9 #efd36c,stop:1 #f16667);}")
            vessel=QVBoxLayout(self._vocal_vu_area)
            vessel.setContentsMargins(7,3,7,2)
            vessel.setSpacing(1)
            for channel in ("L","R"):
                cell,meter,number=self._compact_vu_cell(
                    self._vocal_vu_area,channel,160,label_width=18)
                meter.setFixedHeight(9)
                number.setFixedWidth(57)
                number.setText("−∞ dB")
                meter.setToolTip(
                    "Nivel RMS de "+channel+" medido sobre PCM real."
                    " Escala logarítmica -60 a 0 dBFS.")
                vessel.addWidget(cell)
                self.vus[channel]=meter
                self.vu_labels[channel]=number
            scale=QLabel("−60      −36      −18      −6    0 dBFS")
            scale.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            scale.setStyleSheet("font-family:monospace;font-size:9px;color:#7dbeeb;")
            vessel.addWidget(scale)
            bar.addWidget(self._vocal_vu_area)
        elif kind=="piano":
            # El audio MIDI usa FluidSynth, nunca el reproductor genérico
            # ni un render lento de TiMidity. Los VU proceden del PCM real.
            from piano_realtime import PianoRealtime,PianoMeter
            self.piano_live=PianoRealtime(home,self)
            self.piano_live.error.connect(self.state.setText)
            self.piano_live.engine.stateChanged.connect(lambda _:self.refresh())
            # Recuperar altura del piano sin reducir el teclado.
            # Caption del transporte redundante: el título Piano Roll está
            # ya en la cabecera azul de la ventana.
            self._header_caption.hide()
            box.setContentsMargins(8,2,8,3)
            box.setSpacing(2)
            self._controls_row.setSpacing(3)
            bottom=QHBoxLayout();bottom.setSpacing(12)
            meters=QVBoxLayout();meters.setSpacing(0)
            meters.setContentsMargins(0,0,0,0)
            self.piano_meters={}
            for channel in ("L","R"):
                meter=PianoMeter(channel,self)
                meter.setMaximumWidth(260)
                meters.addWidget(meter)
                self.piano_meters[channel]=meter
            bottom.addLayout(meters,0)
            sound=QVBoxLayout();sound.setSpacing(2)
            top=QHBoxLayout();top.setSpacing(5)
            self.load_sf2=QPushButton("Cargar SF2…",self)
            self.load_sf2.setToolTip("Abrir un banco SoundFont SF2 del sistema o USB")
            self.load_sf2.clicked.connect(self._piano_load_sf2)
            self.sf2_name=QLabel("Banco SF2",self)
            self.sf2_name.setToolTip("Banco de sonido activo")
            top.addWidget(self.load_sf2)
            top.addWidget(self.sf2_name,1)
            self._header_row.removeWidget(self.state)
            top.addWidget(self.state,1)
            self.state.show()
            self.state.setText("MIDI directo")
            sound.addLayout(top)
            choices=QHBoxLayout();choices.setSpacing(4)
            self.sf2_family=QComboBox(self)
            self.sf2_program=QComboBox(self)
            self.sf2_family.setMinimumWidth(105)
            self.sf2_program.setMinimumWidth(145)
            self.sf2_family.setToolTip("Grupo real del SoundFont, incluidos Drums cuando existan")
            self.sf2_program.setToolTip("Únicamente instrumentos disponibles en el banco SF2")
            self.sf2_family.currentIndexChanged.connect(self._piano_family_changed)
            self.sf2_program.currentIndexChanged.connect(self._piano_program_changed)
            choices.addWidget(self.sf2_family,1)
            choices.addWidget(self.sf2_program,2)
            self.apply_preset=QPushButton("Aplicar",self)
            self.apply_preset.setToolTip(
                "Aplicar el instrumento a las pistas MIDI editadas (Deshacer disponible). "
                "Para guardar el nuevo MIDI usa «Añadir MIDI a la lista».")
            self.apply_preset.clicked.connect(self._piano_apply_program)
            choices.addWidget(self.apply_preset)
            sound.addLayout(choices)
            bottom.addLayout(sound,1)
            box.addLayout(bottom)
            self._header_caption.setText("PIANO ROLL · MIDI DIRECTO · FluidSynth")
            self._piano_refresh_banks()
            self.home.workbench.piano.tracks_list.currentItemChanged.connect(
                self._piano_follow_active_instrument)
        else:
            # El transporte estéreo de un solo archivo también es compacto.
            stereo=QHBoxLayout()
            stereo.setSpacing(12)
            for name in ("L","R"):
                cell,meter,number=self._compact_vu_cell(self,name,190)
                stereo.addWidget(cell)
                self.vus[name]=meter
                self.vu_labels[name]=number
            stereo.addStretch(1)
            box.addLayout(stereo)
            self._stereo_row=stereo
        self.play.clicked.connect(self.play_selected)
        self.pause.clicked.connect(self.pause_selected)
        self.stop.clicked.connect(self.stop_selected)
        if kind=="midi":
            browser=self.home._floating_manager.other_expanders[
                self.home.midi_card].midi_browser
            browser.listen.statusChanged.connect(self.state.setText)
            self._header_caption.setText("TRANSPORTE · MEZCLA DE STEMS MARCADOS")
        if kind=="tracks":
            # Un mezclador multipista PCM REAL, reutilizando LowLatencyStemMixer
            # de separación. Todos los streams comparten el mismo reloj.
            from low_latency_stem_mixer import LowLatencyStemMixer
            self.live=LowLatencyStemMixer(self)
            self.live.error.connect(self.state.setText)
            self._header_caption.setText("ESCUCHA CONJUNTA · PISTAS S ACTIVADAS")
            self.state.setText("Marca S en una o varias pistas")
            self._root_box.setContentsMargins(9,6,9,7)
            self._root_box.setSpacing(6)
            self.sync_track_mix()
        if kind=="sep":
            self.home._sep_listen.selectionChanged.connect(self._sync_sep_checks)
            # The transport previously updated Play only on its 120-ms
            # timer. Immediately after checking a recovered stem the
            # button stayed disabled until another refresh, so clicking
            # Play did nothing. Activate it synchronously on selection.
            self.home._sep_listen.selectionChanged.connect(
                lambda:self.play.setEnabled(
                    bool(self.home._sep_listen.paths())
                    and not self.home._sep_listen._busy))
            self.home._sep_listen.statusChanged.connect(self.state.setText)
            self.home._sep_listen.busyChanged.connect(
                lambda busy:self.play.setEnabled(not busy))
            self._sync_sep_checks()
        self.timer=QTimer(self)
        self.timer.setInterval(16 if kind=="piano" else 120)
        self.timer.timeout.connect(self.refresh)
        if kind=="piano":self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.start()
        self.refresh()

    def _piano_sync_composition(self):
        manager=getattr(self.home,"_floating_manager",None)
        if manager is None:return
        expanded=manager.other_expanders.get(self.home.piano_card)
        panel=getattr(expanded,"piano_tools",None)
        if panel is not None:panel.sync_soundfont_catalog(self)

    def _piano_load_sf2(self):
        from PySide6.QtWidgets import QFileDialog
        from midi_to_audio_engine_options import soundfont_locations
        dirs=soundfont_locations(self.home.midi_to_audio)
        dialog=QFileDialog(self,"Cargar banco SoundFont SF2",
                           str(dirs[0] if dirs else Path.home()),"SoundFont SF2 (*.sf2)")
        dialog.setFileMode(QFileDialog.ExistingFile)
        if dirs:
            from PySide6.QtCore import QUrl
            dialog.setSidebarUrls([QUrl.fromLocalFile(str(p)) for p in dirs])
        if dialog.exec()!=QFileDialog.Accepted:return
        path=dialog.selectedFiles()[0]
        try:
            self.piano_live.select_soundfont(path)
            # Banco compartido de la aplicación: MIDI→Audio puede usar
            # el mismo banco, sin alterar su instrumento seleccionado.
            self.home.midi_to_audio.soundfont=Path(path).resolve()
            other=getattr(self.home.midi_to_audio,"expanded_view",None)
            if other is not None:other.refresh_soundfont()
            self._piano_refresh_banks()
        except (ValueError,OSError) as exc:
            self.state.setText(str(exc))

    def _piano_refresh_banks(self):
        from PySide6.QtCore import QSignalBlocker
        try:
            groups=self.piano_live.catalog()
        except (ValueError,OSError) as exc:
            self.state.setText("SF2: "+str(exc))
            groups={}
        self.sf2_name.setText(
            (self.piano_live.soundfont().name if self.piano_live.soundfont()
             else "Sin SoundFont"))
        self.sf2_name.setToolTip(str(self.piano_live.soundfont() or ""))
        with QSignalBlocker(self.sf2_family):
            self.sf2_family.clear()
            for (bank,family),voices in sorted(groups.items(),key=lambda item:
                     (item[0][0]==128,item[0][0],str(item[0][1]))):
                if bank==128:label=f"Drums · {len(voices)} kits"
                else:
                    from midi_to_audio_expanded import GM_GROUPS
                    name=(GM_GROUPS[family] if 0<=family<len(GM_GROUPS)
                          else "Familia "+str(family))
                    label=(name if bank==0 else f"{name} · banco {bank}")
                self.sf2_family.addItem(label,(bank,family))
        self._piano_family_changed(self.sf2_family.currentIndex())
        self._piano_sync_composition()

    def _piano_family_changed(self,index):
        from PySide6.QtCore import QSignalBlocker
        key=self.sf2_family.itemData(index)
        with QSignalBlocker(self.sf2_program):
            self.sf2_program.clear()
            for bank,program,name in self.piano_live._presets.get(key,()):
                self.sf2_program.addItem(f"{program:03d} · {name}",(bank,program))
        self._piano_program_changed(self.sf2_program.currentIndex())
        self._piano_sync_composition()

    def _piano_program_changed(self,index):
        key=self.sf2_program.itemData(index)
        if key is None:return
        self.piano_live.select_preset(*key)
        self._piano_sync_composition()

    def _piano_follow_active_instrument(self,current=None,previous=None):
        """Al escoger una pista, mostrar y escuchar SU instrumento SF2.

        Sin esto, el combo podía seguir diciendo «Violín» al seleccionar
        la pista de piano, y la preescucha reemplazaba incorrectamente
        su programa. No modificar datos MIDI al navegar entre pistas.
        """
        editor=self.home.workbench.piano
        if editor.midi is None or not editor.tracks:return
        track=editor.tracks[editor.track_index]
        # Nuevo MIDI sin notas: respetar el preset que ha elegido el
        # usuario antes de pulsar Generar. No imponer un piano por defecto.
        if not track.get("notes"):return
        channels=track.get("channels",[])
        channel=next((c for c in channels if c!=9),
                     channels[0] if channels else 0)
        bank_msb=bank_lsb=0
        for at,msg in track.get("other",()):
            if at!=0 or getattr(msg,"channel",None)!=channel:continue
            if msg.type=="control_change" and msg.control==0:
                bank_msb=msg.value
            elif msg.type=="control_change" and msg.control==32:
                bank_lsb=msg.value
        bank=128 if channel==9 else bank_msb*128+bank_lsb
        program=track.get("program",0)
        group_key=(bank,"Drums") if bank==128 else (bank,program//8)
        family=next((i for i in range(self.sf2_family.count())
                     if self.sf2_family.itemData(i)==group_key),-1)
        if family<0:
            self.state.setText("Programa de pista no disponible en este SF2")
            self.piano_live.config.program_override=None
            return
        if self.sf2_family.currentIndex()!=family:
            self.sf2_family.setCurrentIndex(family)
        preset=next((i for i in range(self.sf2_program.count())
                     if self.sf2_program.itemData(i)==(bank,program)),-1)
        if preset<0:
            self.state.setText("Preset de pista no disponible en este SF2")
            self.piano_live.config.program_override=None
            return
        self.sf2_program.setCurrentIndex(preset)
        self.piano_live.select_preset(bank,program)
        self._piano_sync_composition()

    def _piano_apply_program(self):
        if self.piano_live.apply_instrument_to_midi():
            self.state.setText("Instrumento aplicado al MIDI · sin guardar")

    def _piano_refresh(self):
        from preview_player import timecode
        live=self.piano_live
        running=live.running
        self.play.setText("Ⅱ Reproduciendo" if running and not live.engine.paused else "▶ Play")
        self.play.setEnabled(True)
        self.pause.setEnabled(running)
        self.stop.setEnabled(running)
        self.timeline.setEnabled(running)
        position=live.position_ms if running else 0
        duration=live.engine.duration_ms if running else 0
        self.clock.setText(f"{timecode(position)} / {timecode(duration)}")
        if not self.timeline.isSliderDown():
            block=self.timeline.blockSignals(True)
            self.timeline.setValue(round(position*1000/duration)
                                   if running and duration>0 else 0)
            self.timeline.blockSignals(block)
        levels=live.engine.levels if running and not live.engine.paused else (0.,)*4
        self.piano_meters["L"].set_levels(levels[0],levels[2])
        self.piano_meters["R"].set_levels(levels[1],levels[3])
        preview=self.home.piano_preview
        if running:
            tick=live.position_tick()
            preview.playhead_tick=tick
            # Reservar margen al final: no esconder la guía por el borde.
            preview.full_tick=max(preview.full_tick,
                live.duration_ticks+int(preview.visible_ticks*.20))
            preview.follow_tick(tick)
            self.state.setText("MIDI sintetizado · PCM real")
        elif preview.playhead_tick is not None:
            if not preview._manual_seek_active:
                # Fin de reproducción/Stop: no dejar una guía anticuada.
                preview.playhead_tick=None
            # Una búsqueda manual detenida sí debe permanecer visible.
            preview.update()

    def sync_track_mix(self):
        """Aplicar M/S y el nivel del Mezclador al PCM actualmente audible."""
        if self.kind!="tracks":return
        names=self.home._stem_audible_names()
        rows=self.home.track_rows
        levels={name:row["gain"].value()/100.*self.home.master_volume.value()/100.
                for name,row in rows.items()}
        self.live.set_track_levels(levels)
        if self.live.running:
            for name in rows:self.live.set_enabled(name,name in names)
        if not self.live.running:
            self.state.setText(
                f"{len(names)} pistas listas · pulsa Play" if names
                else "Marca S en una o varias pistas")
        self.play.setEnabled(bool(names) and
                             (not self.live.running or self.live.paused))
        return names

    def _play_track_mix(self):
        selected=self.home._stem_audible_names()
        if self.live.running:
            if self.live.paused:self.live.pause()
            return
        if not selected:
            self.state.setText("Marca S en una o varias pistas")
            return
        entries=[(name,Path(row["path"]))
                 for name,row in self.home.track_rows.items()
                 if row["path"] is not None and Path(row["path"]).is_file()]
        if not entries:return
        # Evitar dos salidas sonando simultáneamente en la aplicación.
        self.home._sep_listen.stop()
        self.home.player.stop()
        levels={name:row["gain"].value()/100.*self.home.master_volume.value()/100.
                for name,row in self.home.track_rows.items()}
        self.live.set_track_levels(levels)
        if self.live.start(entries,selected):
            self.state.setText(f"Reproduciendo {len(selected)} pistas en sincronía")
        self.refresh()

    def _refresh_tracks_live(self):
        from preview_player import timecode
        live=self.live
        if live.running and (
                (live.duration_ms and live.position()>=live.duration_ms)
                or (live._eof and live._queue.empty() and live.blocks)):
            live.stop()
        # Evitar consultas físicas al pendrive cada 120 ms. El bus PCM
        # conoce ya exactamente qué pistas están activas mientras suena.
        selected=(live.selected if live.running else {
            name for name,row in self.home.track_rows.items()
            if row["path"] is not None and row["solo"].isChecked()
            and not row["mute"].isChecked()})
        self.play.setText("▶ Play" if not live.running or live.paused
                          else "Ⅱ Reproduciendo")
        self.play.setEnabled(bool(selected) and
                             (not live.running or live.paused))
        self.pause.setEnabled(live.running)
        self.stop.setEnabled(live.running)
        self.timeline.setEnabled(live.running and live.duration_ms>0)
        position=live.position() if live.running else 0
        self.clock.setText(f"{timecode(position)} / {timecode(live.duration_ms)}")
        if not self.timeline.isSliderDown() and live.duration_ms:
            blocked=self.timeline.blockSignals(True)
            self.timeline.setValue(round(1000*position/live.duration_ms))
            self.timeline.blockSignals(blocked)
        if live.running:
            self.state.setText(f"Sonando {len(selected)} pistas" if selected
                               else "Todas silenciadas (M)")

    def _sync_sep_checks(self):
        if self.kind!="sep":return
        selected=self.home._sep_listen.selected
        self.sep_original.blockSignals(True)
        self.sep_original.setChecked("Original" in selected)
        self.sep_original.blockSignals(False)
        available=self.home._sep_listen.available()
        for name,box in self.sep_checks.items():
            box.blockSignals(True)
            box.setChecked(name in selected)
            box.setEnabled(available.get(name) is not None)
            box.blockSignals(False)

    def set_docked_mode(self):
        """Mismo transporte real, reducido para Vista de audio en Inicio."""
        if self.kind!="wave":return
        self.setObjectName("dockedWaveTransport")
        self._root_box.setContentsMargins(3,1,3,1)
        self._root_box.setSpacing(1)
        self._header_caption.hide()
        self.state.hide()
        self.setMinimumHeight(62)
        self.setMaximumHeight(75)
        self.play.setText("▶")
        self.play.setToolTip("Reproducir el audio de Vista de audio")
        self.play.setFixedWidth(30)
        self.pause.setFixedWidth(26)
        self.stop.setFixedWidth(26)
        for button in (self.play,self.pause,self.stop):
            button.setStyleSheet("padding:0px;min-height:20px;max-height:22px;")
        self.clock.setMinimumWidth(82)
        self.clock.setMaximumWidth(90)
        self.clock.setStyleSheet("font-size:10px;")
        self._controls_row.setSpacing(2)
        self._stereo_row.setSpacing(4)
        for name in ("L","R"):
            meter=self.vus[name]
            meter.setFixedWidth(86)
            meter.parentWidget().layout().setSpacing(3)
            labels=[c for c in meter.parentWidget().findChildren(QLabel)
                    if c.parentWidget() is meter.parentWidget()]
            for label in labels:
                if label is self.vu_labels[name]:
                    label.setFixedWidth(29)
                    label.setStyleSheet("font-size:9px;")
                else:
                    label.setFixedWidth(14)
                    label.setStyleSheet("font-size:10px;")
        self._stereo_row.setSpacing(2)

    @staticmethod
    def _dbfs(amplitude):
        amplitude=max(0.,float(amplitude))
        if amplitude<1e-7:return float("-inf")
        return 20*math.log10(amplitude)

    @classmethod
    def meter_fraction(cls,amplitude):
        """Medición real de RMS en escala logarítmica −60..0 dBFS."""
        level=cls._dbfs(amplitude)
        return max(0.,min(100.,(level+60.)*100/60))

    def _compact_vu_cell(self,parent,name,meter_width,label_width=76):
        """Etiqueta, barra corta y lectura porcentual calculada del PCM."""
        cell=QFrame(parent)
        cell.setObjectName("compactVuCell")
        row=QHBoxLayout(cell)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(6)
        tag=QLabel(name,cell)
        tag.setFixedWidth(label_width)
        row.addWidget(tag)
        from studio_vu_unified import UnifiedPercentBar
        # La ventana 1 es la referencia: conservar intacta su barra
        # QProgressBar y el estilo que tenía antes de la unificación.
        meter=(QProgressBar(cell) if self.kind=="monitor"
               else UnifiedPercentBar(cell))
        meter.setRange(0,100)
        meter.setValue(0)
        meter.setFixedWidth(meter_width)
        meter.setTextVisible(False)
        meter.setToolTip(name+": nivel medido del audio realmente reproducido")
        row.addWidget(meter)
        number=QLabel("0%",cell)
        number.setObjectName("vuLevel")
        number.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        number.setFixedWidth(37)
        row.addWidget(number)
        return cell,meter,number

    @staticmethod
    def _set_meter(meter,number,value):
        level=max(0,min(100,int(round(value))))
        if meter.value()!=level:
            meter.setValue(level)
        label=f"{level}%"
        if number.text()!=label:
            number.setText(label)
        # Porcentaje de RECORRIDO de escala dBFS, no % de amplitud.
        # Mostrar lectura física equivalente al dejar el puntero encima.
        number.setToolTip(
            f"RMS: {(-60+max(0.,min(100.,float(value)))*.60):.1f} dBFS"
            if value>0 else "RMS: −60 dBFS o menos / silencio")

    def _player(self):
        if self.kind=="monitor" and hasattr(self.home,"record_review"):
            return self.home.record_review.backend
        # Todos los transportes de la pantalla Inicio comparten el mismo
        # reproductor, incluso la separación, sin medir uno distinto.
        return self.home.player

    def _rows(self):
        h=self.home
        return h.drum_stem_rows if self.kind in ("drums","drum_stems") else h.track_rows

    def _selected_source(self):
        # Track and file mixer playback uses a multi-source bus, not
        # a QComboBox-selected single file. track_select is None.
        if self.kind in ("tracks","mixer"):
            return None
        h=self.home
        if self.kind=="monitor":
            candidate=getattr(h.main,"last_file",None)
        elif self.kind=="sep":
            paths=h._sep_listen.paths()
            candidate=paths[0][1] if paths else None
        elif self.kind in ("tracks","mixer","drums","drum_stems"):
            name=self.track_select.currentText()
            row=self._rows().get(name)
            candidate=row["path"] if row else None
        elif self.kind=="midi":
            candidate=h.workbench.converter.audio_path.text()
            if not Path(candidate).is_file():
                candidate=next((p for p in h.workbench.midi_storage.items
                                if Path(p).is_file()),None)
        elif self.kind=="piano":
            candidate=h.selected_midi
        elif self.kind=="vocal":
            module=h._vocal_module
            candidate=getattr(h,"_vocal_listen_file",None)
            if not candidate or not Path(candidate).is_file():
                candidate=module.input.text() if module is not None else None
        elif self.kind=="wave":
            candidate=h._source_for_wave(h._gather_files())
        else:
            candidate=h.selected_file
        if not candidate:return None
        p=Path(candidate).expanduser()
        return p if p.is_file() else None

    def play_selected(self):
        if self.kind=="piano":
            self.piano_live.play()
            self.refresh()
            return
        if self.kind=="tracks":
            self._play_track_mix()
            return
        if self.kind=="midi":
            self._midi_browser().listen.play()
            return
        if self.kind=="sep":
            self.home._sep_listen.play()
            return
        source=self._selected_source()
        if source is None:
            self.state.setText("Selecciona un archivo o pista real")
            return
        player=self._player()
        if player is None:return
        if self.kind in ("tracks","mixer"):
            track=self._rows()[self.track_select.currentText()]
            if track["mute"].isChecked() or (
                any(row["solo"].isChecked() for row in self._rows().values())
                and not track["solo"].isChecked()):
                self.state.setText("Pista silenciada o fuera de Solo")
                return
        if self.kind=="drums":
            module=self.home._drum_module
            if module is not None:
                state=module.studio.channels[self.track_select.currentText()]
                if state["mute"] or (
                    any(c["solo"] for c in module.studio.channels.values())
                    and not state["solo"]):
                    self.state.setText("Pista silenciada o fuera de Solo")
                    return
        if player.current_file!=str(source.resolve()):
            player.load(source,autoplay=True)
        else:
            player.play_pause()
        if self.kind in ("tracks","mixer"):
            level=track["gain"].value()
            player.volume.setValue(min(100,round(self.home.master_volume.value()*level/100)))
        self.state.setText(source.name)

    def pause_selected(self):
        if self.kind=="piano":
            self.piano_live.pause()
            self.refresh()
            return
        if self.kind=="tracks":
            self.live.pause()
            self.refresh()
            return
        if self.kind=="midi":
            self._midi_browser().listen.pause()
            return
        if self.kind=="sep":
            self.home._sep_listen.pause()
            return
        player=self._player()
        if player and player.current_file:
            # Evitar arranque inesperado al pulsar Pausa con reproducción parada.
            if player._qt_active or player._play_process is not None:
                player.play_pause()

    def stop_selected(self):
        if self.kind=="piano":
            # Stop significa detener Y rebobinar TODO el piano roll.
            # Mantener selección, notas y zoom; solo reiniciar el tiempo.
            self.piano_live.stop()
            preview=self.home.piano_preview
            preview.set_scroll(0.)
            preview.playhead_tick=0
            preview._manual_seek_active=True
            preview.update()
            previous=self.timeline.blockSignals(True)
            self.timeline.setValue(0)
            self.timeline.blockSignals(previous)
            self.refresh()
            return
        if self.kind=="tracks":
            self.live.stop()
            self.refresh()
            return
        if self.kind=="midi":
            self._midi_browser().listen.stop()
            return
        if self.kind=="sep":
            self.home._sep_listen.stop()
            return
        player=self._player()
        if player is not None:player.stop()

    def seek(self):
        if self.kind=="piano":
            self.piano_live.seek(self.timeline.value()/1000.)
            return
        if self.kind=="tracks":
            if self.live.running and self.live.duration_ms>0:
                self.live.seek(round(self.timeline.value()/1000*self.live.duration_ms))
                self.sync_track_mix()
            return
        if self.kind=="midi":
            listen=self._midi_browser().listen
            if listen.live.running and listen.live.duration_ms:
                listen.seek(round(listen.live.duration_ms*self.timeline.value()/1000))
            return
        if self.kind=="sep":
            live=self.home._sep_listen.live
            if live.duration_ms>0:
                self.home._sep_listen.seek(round(self.timeline.value()/1000*live.duration_ms))
            return
        player=self._player()
        if player is None or player._duration_ms<=0:return
        position=round(self.timeline.value()/1000*player._duration_ms)
        player.slider.setValue(position)
        player.drag_finish()

    def _refresh_sep_live(self):
        """Lecturas tomadas de stems que continúan sonando en el mismo stream."""
        listen=self.home._sep_listen
        listen.sync_catalog()
        live=listen.live
        playing=live.running and not live.paused
        self.play.setText("Ⅱ Reproduciendo" if playing else "▶ Play")
        self.play.setEnabled(bool(listen.paths()) and not listen._busy)
        self.pause.setEnabled(live.running)
        self.stop.setEnabled(live.running or listen._busy)
        self.timeline.setEnabled(live.running and live.duration_ms>0)
        from preview_player import timecode
        position=live.position()
        self.clock.setText(f"{timecode(position)} / {timecode(live.duration_ms)}")
        if not self.timeline.isSliderDown() and live.duration_ms:
            old=self.timeline.blockSignals(True)
            self.timeline.setValue(round(1000*position/live.duration_ms))
            self.timeline.blockSignals(old)
        self._sync_sep_checks()
        paths=listen.available()
        left_power=0.;right_power=0.
        gain=self.home.player.volume.value()/100.
        for name,meter in self.vus.items():
            path=paths.get(name)
            if playing and path is not None and name in listen.selected:
                left,right=listen.meter_at(path,position/1000)
                left_power+=left*left
                right_power+=right*right
                self._set_meter(meter,self.vu_labels[name],
                                self.meter_fraction(max(left,right)*gain))
            else:self._set_meter(meter,self.vu_labels[name],0)
        # RMS por pista medido sobre el PCM; el agregado es aproximado y
        # no sustituye al medidor PCM posterior a la suma de fases.
        for channel,power in (("L",left_power),("R",right_power)):
            meter=self.master_vus[channel]
            self._set_meter(meter,self.master_labels[channel],
                self.meter_fraction(min(1.,math.sqrt(power))*gain)
                if playing else 0)
            self.master_labels[channel].setToolTip(
                "Nivel estimado a partir de RMS independientes; no pico de la suma.")
        return

    def _midi_browser(self):
        return self.home._floating_manager.other_expanders[
            self.home.midi_card].midi_browser

    def _refresh_midi_live(self):
        from preview_player import timecode
        listen=self._midi_browser().listen
        live=listen.live
        # El medidor procede de PCM realmente mezclado en el callback.
        if live.running and ((live.duration_ms and live.position()>=live.duration_ms)
                             or (live._eof and live._queue.empty() and live.blocks)):
            listen.stop()
        selected=listen.selected()
        running=live.running
        self.play.setText("Ⅱ Reproduciendo" if running and not live.paused else "▶ Play")
        self.play.setEnabled(bool(selected))
        self.pause.setEnabled(running)
        self.stop.setEnabled(running)
        self.timeline.setEnabled(running and live.duration_ms>0)
        position=live.position() if running else 0
        self.clock.setText(f"{timecode(position)} / {timecode(live.duration_ms)}")
        if not self.timeline.isSliderDown() and live.duration_ms:
            old=self.timeline.blockSignals(True)
            self.timeline.setValue(round(1000*position/live.duration_ms))
            self.timeline.blockSignals(old)
        value=self.meter_fraction(live.last_mix_level) if running and not live.paused else 0
        for channel in ("L","R"):
            self._set_meter(self.vus[channel],self.vu_labels[channel],value)

    def refresh(self):
        if self.kind=="piano":
            return self._piano_refresh()
        if self.kind=="tracks":
            return self._refresh_tracks_live()
        if self.kind=="midi":
            return self._refresh_midi_live()
        if self.kind=="sep":
            return self._refresh_sep_live()
        player=self._player()
        playing=bool(player and (player._qt_active or player._play_process is not None)
                     and not player._paused)
        self.play.setText(("Ⅱ" if playing else "▶") if
                          self.objectName()=="dockedWaveTransport" else
                          ("Ⅱ Reproduciendo" if playing else "▶ Play"))
        self.play.setEnabled(self._selected_source() is not None and
                             not (self.kind=="sep" and self.home._sep_listen._busy))
        self.pause.setEnabled(bool(player and (player._qt_active or player._play_process)))
        self.stop.setEnabled(bool(player and player.current_file))
        self.timeline.setEnabled(bool(player and player._duration_ms>0))
        if player:
            self.clock.setText(player.clock.text())
            if not self.timeline.isSliderDown() and player._duration_ms:
                blocked=self.timeline.blockSignals(True)
                self.timeline.setValue(round(
                    1000*max(0,player._position())/player._duration_ms))
                self.timeline.blockSignals(blocked)
        level=(0.,0.)
        if playing and player is not None:
            vu=getattr(player,"_measured_vu",None)
            if vu is not None and vu.levels:
                index=min(len(vu.levels)-1,max(0,int(player._position()/100)))
                gain=player.volume.value()/100.
                level=tuple(max(0.,v*gain) for v in vu.levels[index][:2])
        if self.kind=="tracks":
            # Esta ventana es un selector de stems, no otro mezclador VU.
            # Los medidores y faders permanecen en el módulo Mezclador.
            return
        if self.kind in MULTI:
            for n,meter in self.master_vus.items():
                self._set_meter(
                    meter,self.master_labels[n],
                    self.meter_fraction(level[0 if n=="L" else 1]))
            active_path=Path(player.current_file) if player and player.current_file else None
            for name,meter in self.vus.items():
                if self.kind=="sep":
                    self._sync_sep_checks()
                    selected=self.home._sep_listen.available().get(name)
                else:selected=self._rows()[name]["path"]
                audible=bool(active_path is not None and selected is not None
                             and active_path==Path(selected))
                if audible and self.kind in ("tracks","mixer"):
                    row=self._rows()[name]
                    audible=not row["mute"].isChecked() and (
                        not any(r["solo"].isChecked() for r in self._rows().values())
                        or row["solo"].isChecked())
                if audible and self.kind=="drums":
                    module=self.home._drum_module
                    channels=module.studio.channels if module is not None else {}
                    state=channels.get(name,{})
                    audible=not state.get("mute") and (
                        not any(c.get("solo") for c in channels.values())
                        or state.get("solo",False))
                if self.kind=="sep":
                    # La mezcla FFmpeg no identifica las contribuciones de
                    # cada pista leyendo el máster; no representar falsos VU
                    # individuales mientras su análisis no esté disponible.
                    audible=(playing and name in self.home._sep_listen.selected and
                             selected is not None)
                    if audible:
                        samples=self.home._sep_listen.meter_at(
                            selected,max(0.,player._position())/1000)
                        self._set_meter(meter,self.vu_labels[name],
                            self.meter_fraction(max(samples)*player.volume.value()/100))
                    else:self._set_meter(meter,self.vu_labels[name],0)
                    continue
                scaling=1.
                if audible and self.kind in ("tracks","mixer"):
                    # La ganancia de pista/master ya se aplicó al
                    # control de volumen del reproductor: no duplicarla.
                    scaling=1.
                if audible and self.kind=="drums":
                    module=self.home._drum_module
                    gain=module.studio.channels[name]["gain"] if module else 0
                    scaling=min(1.5,10**(gain/20))
                self._set_meter(
                    meter,self.vu_labels[name],
                    self.meter_fraction(max(level)*scaling) if audible else 0)
        else:
            for channel,value in (("L",level[0]),("R",level[1])):
                meter=self.vus[channel]
                readout=self.vu_labels[channel]
                self._set_meter(meter,readout,self.meter_fraction(value))
                if self.kind=="vocal":
                    db=20*math.log10(value) if value>1e-8 else -120
                    readout.setText(
                        f"{db:.0f} dB" if db>=-60 else "−∞ dB")

    def cleanup(self):
        if self.kind=="piano":
            self.piano_live.stop()
            self.home.piano_preview.playhead_tick=None
            self.home.piano_preview.update()
        if self.kind=="mixer":
            self.project_mixer_strip.cleanup()
            return
        self.timer.stop()
        if self.kind=="tracks":
            # Al devolver la ventana a Inicio la mezcla no sigue oculta.
            self.live.stop()
        # El resto de los transportes no son propietarios del player compartido.
