"""Mezclador SIMPLE del proyecto y ventana original de Inicio.

Una sola instancia compartida entre la pestaña Mezclador y el candado de Inicio:
faders 3D compactos, VU por canal L/R vertical, panorama, mute/solo y selección
real de archivos. Sin ruteo, buses, plugins o controles simulados.
"""
from __future__ import annotations
from PySide6.QtCore import Qt,QTimer,QSignalBlocker,QEvent
from PySide6.QtWidgets import (
    QFrame,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QSlider,QScrollArea,QSizePolicy,QListWidgetItem
)
from studio_home import StudioFader
from studio_pro_console import StereoBar,GlassKnob
from project_mixer_expanded import ProjectMixerView,ProjectMixerTransport,HorizontalMasterMeter,label
from console_audio_engine import ProConsoleEngine


class SimpleStudioMixerView(ProjectMixerView):
    is_simple_mixer=True
    def __init__(self,home,parent=None):
        self.solo_channels=set()
        self.pan_positions={}
        super().__init__(home,parent)
        self.setObjectName("simpleStudioMixer")
        self.setStyleSheet("""
        QWidget#simpleStudioMixer {background:#071522;border:0;}
        QFrame#simpleChannel {
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #061523,stop:.14 #20394d,stop:.4 #102638,
                stop:.84 #182c40,stop:1 #071726);
            border:1px solid #3f677c;border-top:2px solid #5c8b9e;
            border-radius:4px;
        }
        QFrame#projectFilesPanel {
            background:#0b1e30;border:1px solid #437288;border-radius:4px;
        }
        QFrame#projectChannelArea {
            background:#071927;border:1px solid #406881;border-radius:4px;
        }
        QListWidget#projectMixFiles {
            color:#e5faff;background:#091d2d;border:1px solid #41677c;
            alternate-background-color:#132a3a;font-size:11px;
            selection-background-color:#21719b;
        }
        QListWidget#projectMixFiles::item{min-height:21px;padding:3px;}
        QPushButton#simpleFloat {
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #317da4,stop:.5 #115373,stop:1 #07263e);
            color:#e8faff;border:1px solid #63b9d5;border-radius:4px;
            min-height:24px;font-weight:800;padding:3px 10px;
        }
        QPushButton#simpleFloat:hover {background:#197eaa;}
        QPushButton#simpleMute:checked {
            background:#a64343;border:1px solid #ef7777;color:white;
        }
        QPushButton#simpleSolo:checked {
            background:#9b7229;border:1px solid #f6c772;color:white;
        }
        QPushButton#simpleMute,QPushButton#simpleSolo {
            background:#203e51;color:#daeff9;
            border:1px solid #537f94;border-radius:3px;
            font-weight:800;min-height:20px;
        }
        """)
        # El panel de archivos de la derecha ya pertenece al proyecto.
        self.file_panel.setMinimumWidth(205)
        self.file_panel.setMaximumWidth(300)
        self.channel_scroll.setObjectName("simpleMixerChannels")
        self.channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.channel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_row.setContentsMargins(3,3,3,3)
        self.channel_row.setSpacing(3)
        self.channel_scroll.viewport().installEventFilter(self)
        QTimer.singleShot(0,self._fit_channels)
        # Botón coherente con el candado y la ventana flotante originales.
        self.float_button=QPushButton("Ventana flotante",self.channel_panel)
        self.float_button.setObjectName("simpleFloat")
        self.float_button.setToolTip("Separar este mezclador con el candado original")
        self.float_button.clicked.connect(self.detach_to_float)
        self.channel_panel.layout().insertWidget(1,self.float_button,0,Qt.AlignRight)

    def resizeEvent(self,event):
        # El panel original se dimensionaba demasiado ancho en pantallas bajas.
        QWidget.resizeEvent(self,event)
        width=min(300,max(205,int(self.width()*.24)))
        if self.file_panel.width()!=width:self.file_panel.setFixedWidth(width)
        self._fit_channels()

    def eventFilter(self,watched,event):
        if (watched is self.channel_scroll.viewport() and
                event.type()==QEvent.Resize):
            QTimer.singleShot(0,self._fit_channels)
        return super().eventFilter(watched,event)

    def _fit_channels(self):
        if not self.channels:return
        count=len(self.channels)
        viewport=max(1,self.channel_scroll.viewport().width())
        # Con pocos canales, ocupar el panel con tiras proporcionadas,
        # sin separaciones inmensas; cuando se añaden archivos se compactan.
        desired=max(74,min(155,(viewport-12)//count-4))
        for data in self.channels.values():
            data["box"].setFixedWidth(desired)
        self.channel_root.setMinimumWidth(count*(desired+4)+12)

    def _sync_channels(self):
        plan=self._channel_plan()
        # Guardar valores de Solo/Pan de las tiras que se reconstruyen.
        for key,entry in self.channels.items():
            if entry.get("solo") is not None and entry["solo"].isChecked():
                self.solo_channels.add(key)
            elif key in self.solo_channels:self.solo_channels.discard(key)
            if entry.get("pan") is not None:
                self.pan_positions[key]=entry["pan"].value()/100.
        while self.channel_row.count():
            item=self.channel_row.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.channels={}
        for index,(key,source,name) in enumerate(plan):
            box=QFrame(self.channel_root)
            box.setObjectName("simpleChannel")
            box.setFixedWidth(86)
            v=QVBoxLayout(box)
            v.setContentsMargins(3,3,3,3)
            v.setSpacing(2)
            title=QLabel(name.upper(),box)
            title.setStyleSheet("color:#e5f8ff;font-size:10px;font-weight:800;")
            title.setAlignment(Qt.AlignCenter)
            title.setFixedHeight(22)
            title.setToolTip(str(self.sources[source]) if source else name)
            v.addWidget(title)
            panrow=QHBoxLayout();panrow.setSpacing(1)
            panrow.addStretch(1)
            pan=GlassKnob("#66cde0",box)
            pan.setRange(-100,100)
            pan.setValue(round(self.pan_positions.get(key,0.)*100))
            pan.setToolTip("Panorama estéreo real · izquierda / derecha")
            panrow.addWidget(pan)
            panrow.addStretch(1)
            v.addLayout(panrow)
            pan_text=QLabel("PAN",box)
            pan_text.setAlignment(Qt.AlignCenter)
            pan_text.setStyleSheet("color:#a5cee2;font-size:9px;")
            v.addWidget(pan_text)
            controls=QHBoxLayout()
            controls.setSpacing(3)
            controls.addStretch(1)
            mute=QPushButton("M",box);mute.setObjectName("simpleMute")
            solo=QPushButton("S",box);solo.setObjectName("simpleSolo")
            for button in (mute,solo):
                button.setCheckable(True)
                button.setFixedWidth(28)
                controls.addWidget(button)
            controls.addStretch(1)
            existing=self.home.mixer_rows.get(key)
            mute.setChecked(
                self.home.track_rows[key]["mute"].isChecked()
                if existing is not None and key in self.home.track_rows
                else self.checked_mutes.get(key,False))
            solo.setChecked(key in self.solo_channels)
            mute.setEnabled(source is not None)
            solo.setEnabled(source is not None)
            mute.setToolTip("Silenciar esta pista")
            solo.setToolTip("Escuchar únicamente las pistas con S activado")
            v.addLayout(controls)
            middle=QHBoxLayout();middle.setSpacing(0)
            middle.addStretch(1)
            fader=StudioFader(box);fader.setRange(0,150)
            value=existing["fader"].value() if existing else self.extra_gains.get(key,100)
            fader.setValue(value)
            fader.setInvertedAppearance(False)
            fader.setInvertedControls(False)
            fader.setMinimumHeight(90)
            fader.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
            middle.addWidget(fader,0)
            vu=StereoBar(box,scale=True)
            vu.setFixedWidth(43)
            vu.setMinimumHeight(90)
            vu.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
            middle.addWidget(vu,0)
            middle.addStretch(1)
            v.addLayout(middle,1)
            readout=QLabel(f"{value}%",box)
            readout.setAlignment(Qt.AlignCenter)
            readout.setStyleSheet(
                "font-weight:800;font-size:10px;color:#d8f8ff;"
                "background:#0a2638;border-bottom:3px solid #37d2c9;")
            readout.setFixedHeight(22)
            v.addWidget(readout)
            fader.valueChanged.connect(
                lambda value,k=key,out=readout:self._level(k,value,out))
            mute.toggled.connect(lambda flag,k=key:self._mute(k,flag))
            solo.toggled.connect(lambda flag,k=key:self._solo(k,flag))
            pan.valueChanged.connect(lambda value,k=key:self._pan(k,value))
            self.channel_row.addWidget(box,0)
            self.channels[key]=dict(source=source,box=box,fader=fader,
                                    mute=mute,solo=solo,pan=pan,meter=vu)
        self.channel_row.addStretch(1)
        self._fit_channels()
        self.summary.setText(
            f"{len(self.selected)} marcados · {len(self.sources)} archivos · "
            f"{len(self.channels)} canales")
        if self.transport:self.transport.selection_changed()

    def _solo(self,key,flag):
        if flag:self.solo_channels.add(key)
        else:self.solo_channels.discard(key)
        if self.transport:self.transport.selection_changed()

    def _pan(self,key,value):
        self.pan_positions[key]=value/100.
        data=self.channels.get(key)
        source=data["source"] if data else None
        if source and self.transport:
            self.transport.live.configure_channel(source,{"pan":value/100.})

    def effective_levels(self):
        levels=super().effective_levels()
        selected_sources={
            self.channels[key]["source"]
            for key in self.solo_channels if key in self.channels
            and self.channels[key]["source"]
        }
        if selected_sources:
            return {key:(value if key in selected_sources else 0.)
                    for key,value in levels.items()}
        return levels

    def attach_transport(self,transport):
        super().attach_transport(transport)
        self._configure_live()

    def _configure_live(self):
        if self.transport is None:return
        for channel,data in self.channels.items():
            key=data["source"]
            if key:
                self.transport.live.configure_channel(
                    key,{"pan":self.pan_positions.get(channel,0.)})

    def _check_source(self,item):
        super()._check_source(item)
        self._configure_live()

    def detach_to_float(self):
        try:
            manager=self.home._floating_manager
            card=self.home.mix_card
            if manager.is_detached(card):manager.redock(card)
            else:manager.detach(card)
        except (AttributeError,RuntimeError) as error:
            self.summary.setText(f"Ventana flotante: {str(error)[:70]}")


class SimpleMixerTransport(ProjectMixerTransport):
    """Transporte y VU máster compartidos con Inicio, sin duplicar los VU."""
    def __init__(self,view,parent=None):
        QFrame.__init__(self,parent)
        self.view=view
        self._notice=""
        self._meter_names=()
        self.track_meters={}
        self.live=ProConsoleEngine(self)
        self.live.error.connect(self._error)
        self.setObjectName("simpleMixerTransport")
        self.setStyleSheet("""
        QFrame#simpleMixerTransport{
            background:#0d2334;border:1px solid #456f84;border-radius:4px;}
        QFrame#simpleMixerTransport QPushButton{
            color:#eafaff;background:#163e57;border:1px solid #5b91a7;
            border-radius:3px;min-height:27px;font-weight:800;padding:3px 9px;}
        QFrame#simpleMixerTransport QPushButton:pressed{background:#155c7d;}
        QFrame#simpleMixerTransport QPushButton:disabled{
            color:#6d879b;border-color:#395166;background:#10283a;}
        QLabel{color:#e7f7ff;}
        QSlider::groove:horizontal{
            background:#091521;border:1px solid #537d90;height:6px;border-radius:3px;}
        QSlider::sub-page:horizontal{background:#3dd7c6;}
        QSlider::handle:horizontal{width:11px;margin:-4px 0;
            background:#eafaff;border:1px solid #8cbaca;border-radius:3px;}
        """)
        outer=QVBoxLayout(self);outer.setContentsMargins(6,4,6,4);outer.setSpacing(2)
        row=QHBoxLayout();row.setSpacing(6)
        self.play=QPushButton("▶",self);self.pause=QPushButton("Ⅱ",self)
        self.stop=QPushButton("■",self)
        for button in (self.play,self.pause,self.stop):
            button.setFixedWidth(37)
            row.addWidget(button)
        self.master_meters={}
        meters=QVBoxLayout();meters.setSpacing(0);meters.setContentsMargins(0,0,0,0)
        for channel in ("L","R"):
            vu=HorizontalMasterMeter(channel,self)
            vu.setFixedSize(151,25)
            self.master_meters[channel]=vu
            meters.addWidget(vu)
        row.addLayout(meters)
        self.timeline=QSlider(Qt.Horizontal,self)
        self.timeline.setRange(0,1000)
        self.timeline.setTracking(False)
        self.timeline.setFixedWidth(206)
        self.timeline.sliderReleased.connect(self.seek)
        row.addWidget(self.timeline)
        self.clock=label("00:00 / 00:00",self)
        self.clock.setMinimumWidth(105)
        row.addWidget(self.clock)
        row.addWidget(label("MÁSTER",self))
        self.master_volume=QSlider(Qt.Horizontal,self)
        self.master_volume.setRange(
            view.home.master_volume.minimum(),view.home.master_volume.maximum())
        self.master_volume.setValue(view.home.master_volume.value())
        self.master_volume.setMaximumWidth(135)
        self.master_volume.valueChanged.connect(self._set_master)
        view.home.master_volume.valueChanged.connect(self._pull_master)
        row.addWidget(self.master_volume)
        self.master_value=label(f"{self.master_volume.value()}%",self)
        row.addWidget(self.master_value)
        row.addStretch()
        outer.addLayout(row)
        self.status=label("Selecciona archivos del proyecto para mezclarlos",self)
        self.status.setStyleSheet("color:#8cc8da;font-size:9px;")
        outer.addWidget(self.status)
        self.play.clicked.connect(self.play_selected)
        self.pause.clicked.connect(self.pause_selected)
        self.stop.clicked.connect(self.stop_selected)
        self.timer=QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.view.attach_transport(self)
        self._sync_meters()
        self.setFixedHeight(95)

    def _sync_meters(self):
        plan=self.view._channel_plan()
        signature=tuple((a,b,c) for a,b,c in plan)
        if signature==self._meter_names:return
        self._meter_names=signature
        self.track_meters={
            channel:(data["source"],data["meter"])
            for channel,data in self.view.channels.items()
        }
        self.view._configure_live()

    def _fit_layout(self):
        return

    def selection_changed(self):
        self.view._configure_live()
        return super().selection_changed()

    def play_selected(self):
        # Una sola salida PCM simultánea del mezclador del proyecto.
        main=self.view.home.main
        dialog=getattr(main.composer_tab,"_pro_mixer_dialog",None) if \
            getattr(main,"composer_tab",None) is not None else None
        if dialog is not None and getattr(dialog,"transport",None) is not None:
            if dialog.transport.live.running:dialog.transport.live.stop()
        self.view._configure_live()
        super().play_selected()
