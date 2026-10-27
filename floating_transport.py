"""Transporte local para las tarjetas flotantes de Inicio.

No cambia pestañas. Utiliza un único reproductor real, compartido con
Inicio; VU por pista sólo mide los datos de audio PCM efectivamente en
reproducción. Nunca representa silencios con barras inventadas.
"""
from pathlib import Path

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,
                               QLabel,QPushButton,QSlider,QComboBox,
                               QProgressBar,QSizePolicy)

STEMS=("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros")
DRUMS=("Bombo","Caja","Toms","Charles","Ride","Crash")
KINDS=("monitor","sep","midi","results","wave","drums","tracks",
       "mixer","piano","vocal","drum_stems","info")
MULTI=("sep","tracks","mixer","drum_stems")

class FloatingTransport(QFrame):
    def __init__(self,home,kind,parent=None):
        super().__init__(parent)
        self.home=home
        self.kind=kind
        self.setObjectName("floatingTransportPanel")
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
        box=QVBoxLayout(self);box.setContentsMargins(9,7,9,7);box.setSpacing(4)
        header=QHBoxLayout();header.setSpacing(6)
        header.addWidget(QLabel("TRANSPORTE · ESCUCHA EN INICIO"))
        header.addStretch()
        self.state=QLabel("Sin audio")
        self.state.setMaximumWidth(300)
        header.addWidget(self.state)
        box.addLayout(header)
        self.track_select=None
        if kind in MULTI:
            selector=QHBoxLayout()
            selector.addWidget(QLabel("Pista"))
            self.track_select=QComboBox(self)
            names=DRUMS if kind=="drum_stems" else (("Original",)+STEMS if kind=="sep" else STEMS)
            self.track_select.addItems(names)
            self.track_select.setMinimumWidth(125)
            selector.addWidget(self.track_select)
            selector.addStretch()
            box.addLayout(selector)
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
        self.vus={}
        self.vu_labels={}
        self.master_labels={}
        if kind in MULTI:
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
            outer.setContentsMargins(11,7,11,9)
            outer.setSpacing(5)
            caption=QLabel("VU MÁSTER · L / R",meter_area)
            caption.setObjectName("vuCaption")
            outer.addWidget(caption)
            master_grid=QGridLayout()
            master_grid.setHorizontalSpacing(24)
            master_grid.setVerticalSpacing(5)
            self.master_vus={}
            for column,channel in enumerate(("L","R")):
                cell,meter,number=self._compact_vu_cell(
                    meter_area,"Máster "+channel,190)
                master_grid.addWidget(cell,0,column)
                self.master_vus[channel]=meter
                self.master_labels[channel]=number
            outer.addLayout(master_grid)
            caption=QLabel("VU POR PISTA · SEÑAL REAL",meter_area)
            caption.setObjectName("vuCaption")
            outer.addWidget(caption)
            tracks=DRUMS if kind=="drum_stems" else STEMS
            left_count=(len(tracks)+1)//2
            compact_grid=QGridLayout()
            compact_grid.setHorizontalSpacing(24)
            compact_grid.setVerticalSpacing(4)
            for index,name in enumerate(tracks):
                column=0 if index<left_count else 1
                row=index if column==0 else index-left_count
                cell,meter,number=self._compact_vu_cell(
                    meter_area,name,190)
                compact_grid.addWidget(cell,row,column)
                self.vus[name]=meter
                self.vu_labels[name]=number
            outer.addLayout(compact_grid)
            box.addWidget(meter_area,0,Qt.AlignHCenter)
            self.compact_vu_panel=meter_area
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
        self.play.clicked.connect(self.play_selected)
        self.pause.clicked.connect(self.pause_selected)
        self.stop.clicked.connect(self.stop_selected)
        self.timer=QTimer(self);self.timer.setInterval(120)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def _compact_vu_cell(self,parent,name,meter_width):
        """Etiqueta, barra corta y lectura porcentual calculada del PCM."""
        cell=QFrame(parent)
        cell.setObjectName("compactVuCell")
        row=QHBoxLayout(cell)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(6)
        tag=QLabel(name,cell)
        tag.setFixedWidth(76)
        row.addWidget(tag)
        meter=QProgressBar(cell)
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

    def _player(self):
        if self.kind=="monitor" and hasattr(self.home,"record_review"):
            return self.home.record_review.backend
        if self.kind=="sep":
            sep=self.home.workbench.separator
            preview=sep.result_preview
            if preview.current_file and (preview._qt_active or preview._play_process):
                return preview
            if sep.source_preview.current_file:
                return sep.source_preview
        return self.home.player

    def _rows(self):
        h=self.home
        return h.drum_stem_rows if self.kind=="drum_stems" else h.track_rows

    def _selected_source(self):
        h=self.home
        if self.kind=="monitor":
            candidate=getattr(h.main,"last_file",None)
        elif self.kind=="sep":
            sep=h.workbench.separator
            candidate=sep.source_preview.current_file or sep.file_edit.text()
            outputs=[Path(p) for p in sep.latest_outputs if Path(p).is_file()]
            if self.track_select is not None:
                name=self.track_select.currentText()
                if name!="Original":
                    candidate=next((p for p in outputs if h._stem_for(p)==name),None)
        elif self.kind in ("tracks","mixer","drum_stems"):
            name=self.track_select.currentText()
            candidate=self._rows()[name]["path"]
        elif self.kind=="midi":
            candidate=h.workbench.converter.audio_path.text()
            if not Path(candidate).is_file():
                candidate=next((p for p in h.workbench.midi_storage.items
                                if Path(p).is_file()),None)
        elif self.kind=="piano":
            candidate=h.selected_midi
        elif self.kind=="drums":
            module=h._drum_module
            candidate=module.input.text() if module is not None else None
        elif self.kind=="vocal":
            module=h._vocal_module
            candidate=module.input.text() if module is not None else None
        elif self.kind=="wave":
            candidate=h._source_for_wave(h._gather_files())
        else:
            candidate=h.selected_file
        if not candidate:return None
        p=Path(candidate).expanduser()
        return p if p.is_file() else None

    def play_selected(self):
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
        if player.current_file!=str(source.resolve()):
            player.load(source,autoplay=True)
        else:
            player.play_pause()
        if self.kind in ("tracks","mixer"):
            level=track["gain"].value()
            player.volume.setValue(min(100,round(self.home.master_volume.value()*level/100)))
        self.state.setText(source.name)

    def pause_selected(self):
        player=self._player()
        if player and player.current_file:
            # Evitar arranque inesperado al pulsar Pausa con reproducción parada.
            if player._qt_active or player._play_process is not None:
                player.play_pause()

    def stop_selected(self):
        player=self._player()
        if player is not None:player.stop()

    def seek(self):
        player=self._player()
        if player is None or player._duration_ms<=0:return
        position=round(self.timeline.value()/1000*player._duration_ms)
        player.slider.setValue(position)
        player.drag_finish()

    def refresh(self):
        player=self._player()
        playing=bool(player and (player._qt_active or player._play_process is not None)
                     and not player._paused)
        self.play.setText("Ⅱ Reproduciendo" if playing else "▶ Play")
        self.play.setEnabled(self._selected_source() is not None)
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
                level=vu.levels[index][:2]
        if self.kind in MULTI:
            for n,meter in self.master_vus.items():
                self._set_meter(
                    meter,self.master_labels[n],
                    100*level[0 if n=="L" else 1])
            active_path=Path(player.current_file) if player and player.current_file else None
            for name,meter in self.vus.items():
                if self.kind=="sep":
                    out=self.home.workbench.separator.latest_outputs
                    matching=next((Path(p) for p in out if self.home._stem_for(p)==name),None)
                    selected=matching
                else:selected=self._rows()[name]["path"]
                audible=bool(active_path is not None and selected is not None
                             and active_path==Path(selected))
                if audible and self.kind in ("tracks","mixer"):
                    row=self._rows()[name]
                    audible=not row["mute"].isChecked() and (
                        not any(r["solo"].isChecked() for r in self._rows().values())
                        or row["solo"].isChecked())
                scaling=1.
                if audible and self.kind in ("tracks","mixer"):
                    scaling=min(1.5,self._rows()[name]["gain"].value()/100)
                    scaling*=self.home.master_volume.value()/100
                self._set_meter(
                    meter,self.vu_labels[name],
                    100*max(level)*scaling if audible else 0)
        else:
            self._set_meter(self.vus["L"],self.vu_labels["L"],100*level[0])
            self._set_meter(self.vus["R"],self.vu_labels["R"],100*level[1])

    def cleanup(self):
        self.timer.stop()
        # A floating transport does not own the shared player; no stop on redock.
