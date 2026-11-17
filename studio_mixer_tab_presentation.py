"""Presentación visual EXCLUSIVA de la pestaña Mezclador.

No añade controles de audio, no modifica el motor ni la consola flotante.
Al desacoplar el QWidget se restaura el estilo y las geometrías originales.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import MethodType
from PySide6.QtCore import (QObject,QEvent,Qt,QTimer,QProcess,QProcessEnvironment,
    QRectF,QPoint,QSignalBlocker)
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QSizePolicy,
    QComboBox, QSlider, QPushButton, QMessageBox, QMenu, QFrame, QInputDialog,
    QScrollArea
)
from studio_pro_console import RouteMatrix
from studio_mixer_bus_fx import TabBusEffects
from studio_mixer_bus_ui import PanBalanceDial, BusInspector
from studio_mixer_channel_ui import (
    MasterLiveScope, ParallelMixerDashboard, ChannelPluginWindow,
    INSERT_BUTTON_STYLE
)

TAB_SKIN = """
/* Solo se instala mientras la consola reside en la pestaña. */
QWidget#proConsoleRoot{
  background:#071422;
  color:#e5f5ff;
}
QFrame#proRack,QFrame#proSidebar,QFrame#proChannels{
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #213e54,stop:.06 #193147,stop:.83 #0a1c2a,stop:1 #081522);
  border:1px solid #4a7288;
  border-top:2px solid #67acc6;
  border-radius:6px;
}
QFrame#proStrip{
  background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #071320,stop:.10 #1a3448,stop:.25 #0d2334,
    stop:.76 #10283c,stop:.92 #203b4e,stop:1 #071522);
  border:1px solid #496b7b;
  border-top:2px solid #618ca0;
  border-bottom:1px solid #315067;
  border-radius:4px;
}
QFrame#proStrip[active="true"]{
  border-top:2px solid #56dcee;
  border-left:1px solid #538da6;
  border-right:1px solid #538da6;
}
QFrame#proStrip[dragTarget="true"]{
  border:2px solid #b6ffff;
  background:#1b4c67;
}
QFrame#proSourcePanel{
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #183b57,stop:.12 #0f2b45,stop:1 #091d30);
  border:1px solid #5599b6;
  border-top:2px solid #75ddeb;
  border-radius:6px;
}
QListWidget#proAvailableSources{
  color:#e7f8ff;
  background:#071e31;
  border:1px solid #4a8198;
  border-radius:5px;
  font-size:11px;
  alternate-background-color:#102d43;
  selection-background-color:#1b7fa9;
  selection-color:#ffffff;
}
QListWidget#proAvailableSources::item{
  padding:3px 6px;
  min-height:26px;
  border-bottom:1px solid #21475e;
}
QListWidget#proAvailableSources::item:hover{
  background:#18455d;
}
QPushButton{
  color:#e8f8ff;
  font-weight:750;
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #54748c,stop:.15 #2c5168,stop:.55 #17344a,stop:1 #0a2134);
  border:1px solid #608ca2;
  border-top:1px solid #a4cede;
  border-bottom:2px solid #061622;
  border-radius:4px;
}
QPushButton:hover{border-color:#8ce9f7;background:#245674;}
QPushButton:checked{background:#17638f;border-color:#74d9f0;}
QPushButton#muteButton:checked{background:#a93e40;border-color:#f2a09a;}
QPushButton#soloButton:checked{background:#a47518;border-color:#ffdc83;}
QPushButton#armButton:checked{background:#b6313d;border-color:#ffc0bd;}
QPushButton:disabled{color:#708d9d;background:#162a38;border-color:#38556a;}
QComboBox{
  color:#effaff;
  background:#10324a;
  border:1px solid #5689a0;
  border-radius:4px;
  min-height:22px;
  padding:2px 15px 2px 5px;
}
QComboBox QAbstractItemView{
  background:#092438;color:#ebffff;
  selection-background-color:#20799b;
}
QFrame#proTabSection{
  background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #214860,stop:.4 #13334b,stop:1 #0c253b);
  border:1px solid #3e7995;
  border-left:3px solid #60e4ed;
  border-radius:4px;
}
QLabel#proTabSectionTitle{
  color:#ebfbff;
  font-size:11px;
  font-weight:850;
  background:transparent;
}
QLabel#proTabSectionNote{
  color:#b9d8e9;
  font-size:10px;
  background:transparent;
}
"""


class MixerTabPresentation(QObject):
    """Diseño temporal de la pestaña; guardamos y restauramos TODO lo tocado."""
    def __init__(self, console, parent=None):
        super().__init__(parent)
        self.console = console
        self.active = False
        self._saved = None
        self._applying = False
        self._last_width = None
        self._bar = QFrame(console.channel_panel)
        self._bar.setObjectName("proTabSection")
        self._bar.setFixedHeight(22)
        row = QHBoxLayout(self._bar)
        row.setContentsMargins(9,3,9,3)
        row.setSpacing(10)
        left = QLabel("16 CANALES  /  BALANCE · FADERS ESTÉREO", self._bar)
        left.setObjectName("proTabSectionTitle")
        row.addWidget(left)
        row.addStretch(1)
        right = QLabel("M: Silencio    S: Solo    ·    Arrastra archivos al canal", self._bar)
        right.setObjectName("proTabSectionNote")
        row.addWidget(right)
        self._bar.hide()
        # La barra existente es el tirador: arriba = más altura para canales.
        self._user_rack_height=None
        self._rack_drag=None
        for target in (self._bar,left,right):
            target.setCursor(Qt.SizeVerCursor)
            target.setToolTip("Arrastra hacia arriba para ampliar los canales")
            target.installEventFilter(self)
        self.bus_count = 16
        self.bus_fx = TabBusEffects()
        self._tab_bus_routes = {}
        self._saved_bus_dsp = False
        self._last_bus_selected = 1
        self._strip_state = {}
        self._channel_insert_windows = {}
        self._default_routes_initialized = False
        self._pending_bus_state=None
        self._channel_local_levels = {}
        # BUS insert view next to MASTER / BUS faders. Added only in this tab.
        self._bus_fx_strip=QFrame(console.sidebar)
        self._bus_fx_strip.setObjectName("mixerBusInsertStrip")
        self._bus_fx_strip.setStyleSheet("""
          QFrame#mixerBusInsertStrip{background:#0b2940;
             border:1px solid #33718b;border-radius:4px}
        """)
        bus_strip_layout=QVBoxLayout(self._bus_fx_strip)
        bus_strip_layout.setContentsMargins(2,2,2,2)
        bus_strip_layout.setSpacing(1)
        self._bus_fx_button=QPushButton("+ FX BUS",self._bus_fx_strip)
        self._bus_fx_button.setObjectName("mixerBusInsertAdd")
        self._bus_fx_button.setFixedHeight(19)
        self._bus_fx_button.setToolTip(
            "Insertar filtros en el BUS activo; cada BUS tiene sus propios efectos")
        self._bus_fx_button.setStyleSheet(INSERT_BUTTON_STYLE)
        self._bus_fx_button.clicked.connect(self._bus_insert_menu)
        bus_strip_layout.addWidget(self._bus_fx_button)
        self._bus_fx_list=QFrame(self._bus_fx_strip)
        self._bus_fx_list.setObjectName("mixerSelectedBusInsertList")
        self._bus_fx_list.setStyleSheet(
            "QFrame#mixerSelectedBusInsertList{background:transparent;border:0}")
        self._bus_fx_rows=QVBoxLayout(self._bus_fx_list)
        self._bus_fx_rows.setContentsMargins(0,0,0,0)
        self._bus_fx_rows.setSpacing(2)
        self._bus_fx_rows.setAlignment(Qt.AlignTop)
        # More than two effects cannot fit vertically in a compact sidebar.
        # Clip only this local list, keeping effects top-to-bottom and the
        # MASTER/BUS faders visible; no extra scroll appears for two effects.
        self._bus_fx_scroll=QScrollArea(self._bus_fx_strip)
        self._bus_fx_scroll.setObjectName("mixerBusInsertScroll")
        self._bus_fx_scroll.setFrameShape(QFrame.NoFrame)
        self._bus_fx_scroll.setWidgetResizable(True)
        self._bus_fx_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._bus_fx_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._bus_fx_scroll.setStyleSheet("""
          QScrollArea#mixerBusInsertScroll{background:transparent;border:0;}
          QScrollBar:vertical{background:#0b2635;width:7px;}
          QScrollBar::handle:vertical{background:#2c7088;border-radius:3px;}
        """)
        self._bus_fx_scroll.setWidget(self._bus_fx_list)
        bus_strip_layout.addWidget(self._bus_fx_scroll,0)
        self._bus_fx_visible_limit=6
        self._bus_fx_row_widgets=[]
        # A single top-aligned column immediately below the BUS inspector.
        self._bus_fx_row=QFrame(console.sidebar)
        self._bus_fx_row.setObjectName("mixerBusInsertRow")
        fxrow=QVBoxLayout(self._bus_fx_row)
        fxrow.setContentsMargins(0,0,0,0)
        fxrow.setSpacing(0)
        fxrow.addWidget(self._bus_fx_strip,0)
        self._bus_fx_row.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Maximum)
        self._bus_fx_row.hide()
        self._select_targets = {}
        self._master_scope = MasterLiveScope(self.bus_fx,console.rack)
        self._master_scope.hide()
        self._dashboard=ParallelMixerDashboard(
            self.bus_fx,self._set_eq16_band,console.rack)
        self._dashboard.hide()
        self._scope_timer = QTimer(console)
        self._scope_timer.setInterval(180)
        self._scope_timer.timeout.connect(self._scope_tick)
        self._bus_modes = QComboBox(console.sidebar)
        self._bus_modes.setObjectName("mixerTabBusCount")
        self._bus_modes.setToolTip("Número de buses de mezcla activos en esta pestaña")
        self._bus_modes.addItem("16 buses", 16)
        self._bus_modes.addItem("32 buses", 32)
        self._bus_modes.setFixedWidth(82)
        self._bus_modes.currentIndexChanged.connect(self._bus_count_changed)
        self._bus_modes.hide()
        self._bus_bank = QComboBox(console.rack)
        self._bus_bank.setObjectName("mixerTabBusBank")
        self._bus_bank.addItem("Bus 1–16", 0)
        self._bus_bank.addItem("Bus 17–32", 16)
        self._bus_bank.setToolTip("Banco de columnas de la matriz de ruteo")
        self._bus_bank.currentIndexChanged.connect(self._bank_changed)
        self._bus_bank.setFixedWidth(95)
        self._bus_bank.hide()
        self._routing_original = console.routing
        self._routing_tab = TabBusMatrix(console, self)
        self._routing_tab.hide()
        # Exactly 16 compact horizontal send faders, visually BETWEEN
        # the 16x16 matrix and the two existing MASTER VUs. No VU
        # is added to a channel's new matrix fader.
        self._rack_wave_column=console.rack.layout().itemAt(2).layout()
        self._matrix_send_panel=MatrixChannelSendFaders(
            console,self,self._routing_tab,console.rack)
        console.rack.layout().insertWidget(1,self._matrix_send_panel,0)
        self._matrix_send_panel.hide()
        console.route_pages.currentIndexChanged.connect(
            self._matrix_send_panel.refresh)

        self._bus_inspector=BusInspector(self,console.sidebar)
        self._bus_inspector.hide()
        self._bus_lower=QFrame(console.sidebar)
        self._bus_lower.setObjectName("mixerTabBusSelector")
        self._bus_lower_layout=QHBoxLayout(self._bus_lower)
        self._bus_lower_layout.setContentsMargins(2,3,2,3)
        self._bus_lower_layout.setSpacing(5)
        bus_title=QLabel("BUS ACTIVO",self._bus_lower)
        bus_title.setStyleSheet("color:#8beeff;font-size:10px;font-weight:800;")
        self._bus_lower_layout.addWidget(bus_title)
        self._bus_lower.hide()
        self._aux_panel=QFrame(console.sidebar)
        self._aux_panel.setObjectName("mixerTabAuxPanel")
        self._aux_panel.setStyleSheet("""
        QFrame#mixerTabAuxPanel{background:#0b263c;border:1px solid #336984;
             border-radius:4px;}
        QLabel{color:#bbe8f2;font-size:9px;}
        """)
        aux_layout=QVBoxLayout(self._aux_panel)
        aux_layout.setContentsMargins(3,2,3,2)
        aux_layout.setSpacing(1)
        self._aux_label=QLabel("ENVÍO AUX · PISTA SELECCIONADA",self._aux_panel)
        aux_layout.addWidget(self._aux_label)
        targets=QHBoxLayout();targets.setSpacing(3)
        self._aux_target=QComboBox(self._aux_panel)
        self._aux_target.setToolTip("Envía parte de la señal a otro BUS, en paralelo")
        self._aux_target.currentIndexChanged.connect(self._aux_changed)
        targets.addWidget(self._aux_target,1)
        self._aux_slider=QSlider(Qt.Horizontal,self._aux_panel)
        self._aux_slider.setRange(0,100)
        self._aux_slider.setToolTip("Porcentaje de envío post-fader")
        self._aux_slider.valueChanged.connect(self._aux_changed)
        targets.addWidget(self._aux_slider,1)
        self._aux_readout=QLabel("0%",self._aux_panel)
        targets.addWidget(self._aux_readout)
        aux_layout.addLayout(targets)
        self._aux_panel.hide()
        # Keep the BUS chain exactly aligned to the "Sin AUX" selector.
        self._aux_target.installEventFilter(self)
        self._aux_source=None
        self._aux_targets={}
        self._updating_aux=False
        console.bus_select.currentIndexChanged.connect(self._update_bus_inspector)
        # Project SAVE/LOAD are handled by the central .stemstudio.json.
        # Do not connect independent BUS sidecars to the same buttons.
        self.console.installEventFilter(self)

    def _rack_height_target(self,view):
        auto=max(249,min(340,round(view.height()*.42)))
        # Mantener la elección hecha con el tirador incluso tras Resize/refresh.
        if self._user_rack_height is None:return auto
        maximum=max(135,min(340,view.height()-220))
        return max(135,min(maximum,int(self._user_rack_height)))

    def _drag_rack_height(self,global_y):
        if self._rack_drag is None:return
        initial_y,initial_height=self._rack_drag
        new_height=initial_height+round(global_y-initial_y)
        self._user_rack_height=max(135,min(340,new_height))
        self.console.rack.setFixedHeight(
            self._rack_height_target(self.console))
        self.console._fit_strips()

    def activate(self):
        if self.active:
            self.refresh()
            return
        view = self.console
        self._saved = {
            "style": view.styleSheet(),
            "root_spacing": view.layout().spacing(),
            "right_spacing": view.right_layout.spacing(),
            "sources_width": view.sources_panel.width(),
            "sidebar_width": view.sidebar.width(),
            "rack_height": view.rack.height(),
            "wave_width": view.wave_source.width(),
            "panel_spacing": view.channel_panel.layout().spacing(),
            "side_spacing": view.sidebar.layout().spacing(),
            "source_layout_spacing": view.sources_panel.layout().spacing(),
            "route_head_spacing": self._routing_head().spacing(),
            "bus_select_width": view.bus_select.width(),
            "presets_height": view.presets.height(),
            "routing_header_text": self._routing_head().itemAt(0).widget().text(),
            "inspector_style": view.inspector.styleSheet(),
            "inspect_name": view.inspect_name.text(),
            "bus_row": [],
            "source_row": [],
            "source_list": (view.file_list.isHidden(),
                            view.file_list.minimumHeight(),
                            view.file_list.maximumHeight()),
            "summary_hidden":view.summary.isHidden(),
        }
        self._strip_state = {}
        self.active = True
        # _fit_strips() de la clase profesional reinstala siempre la
        # altura antigua de rack (161 px) en cada resize Qt/Cocoa.
        # Sobrescribirla temporalmente solo mientras está acoplado.
        self._native_fit_strips=view._fit_strips
        def fit_parallel(widget):
            result=self._native_fit_strips()
            if self.active:
                target=self._rack_height_target(widget)
                if widget.rack.height()!=target:
                    widget.rack.setFixedHeight(target)
                for strip in widget.visible_strips:
                    strip.setMaximumHeight(365)
                    strip.setMinimumHeight(0)
            return result
        view._fit_strips=MethodType(fit_parallel,view)
        view.setStyleSheet(self._saved["style"] + "\n" + TAB_SKIN)
        view.layout().setSpacing(7)
        view.right_layout.setSpacing(4)
        view.channel_panel.layout().insertWidget(0, self._bar, 0)
        view.channel_panel.layout().setSpacing(5)
        self._bar.show()
        # Estos cambios se aplican ÚNICAMENTE mientras la consola está
        # dentro de su pestaña y se revierten antes de desacoplarla.
        self._show_tab_controls()
        self._enable_bus_engine()
        self.bus_fx.set_bus_count(self.bus_count)
        self.bus_fx.bind(view.transport.live)
        # Initialise independent dry and processed fader levels per channel.
        for strip in view.visible_strips:
            if strip.key not in self.bus_fx.channel_routes:
                self.bus_fx.set_channel_route(
                    strip.key,processed_level=strip.fader.value()/100.,
                    dry_level=.5,dry_enabled=False,
                    processed_pan=float(strip.controls.get("pan",0.)),
                    muted=strip.mute.isChecked(),
                    processed_solo=strip.solo.isChecked())
        # PROBLEMA REAL: effective_levels() de la consola heredada
        # multiplicaba MASTER × FADER en TODAS LAS PISTAS. La pestaña
        # mantiene cada fader PRE-MASTER, y MASTER actúa una sola vez al
        # FINAL del callback, después de sumar las salidas de los buses.
        self._native_effective_levels=view.effective_levels
        self._native_level=view._level
        self._native_mute=view._mute
        self._native_set_channel_param=view.set_channel_param

        def tab_levels(widget):
            # The transport must keep the original SOURCE enabled whenever
            # EITHER independent path is audible. Do not propagate the Mute
            # of the focused fader to the other path.
            levels={}
            for key,item in widget.channels.items():
                if item["source"] is None:continue
                route=self.bus_fx.get_channel_route(
                    key,item["fader"].value()/100.)
                wet=(0. if route["processed_muted"] else route["processed_level"])
                dry=(0. if route["dry_muted"] else route["dry_level"])
                # An active PRE-FADER clean BUS tap must keep the source
                # track available even if BOTH direct paths are muted.
                bus_number=int(route.get("dry_bus",0))
                bus_feed=1. if 1<=bus_number<=self.bus_count else 0.
                levels[key]=max(dry,wet,bus_feed)
            return levels

        def tab_level(widget,key,amount,readout):
            # One physical fader, two persistent gains. The nonfocused path
            # keeps playing at its previously stored level.
            route=self.bus_fx.get_channel_route(key,amount/100.)
            clean=route["dry_enabled"]
            level_key="dry_level" if clean else "processed_level"
            self.bus_fx.set_channel_route(key,**{level_key:amount/100.})
            readout.setText(f"{'L' if clean else 'FX'} {amount}%")
            if not clean:
                self._channel_local_levels[key]=int(amount)
                widget.extra_gains[key]=int(amount)
            if widget.transport:
                widget.transport.live.set_track_levels(widget.effective_levels())

        def tab_mute(widget,key,checked):
            # Never call the old channel-wide _mute: it would mute the dry
            # and FX branches together and could toggle the home-stem mute.
            route=self.bus_fx.get_channel_route(key)
            field="dry_muted" if route["dry_enabled"] else "processed_muted"
            self.bus_fx.set_channel_route(key,**{field:bool(checked)})
            if widget.transport:
                widget.transport.live.set_track_levels(widget.effective_levels())

        def tab_set_channel_param(widget,key,param,value):
            if param=="pan" and key in widget.channels:
                route=self.bus_fx.get_channel_route(key)
                clean=bool(route["dry_enabled"])
                field="dry_pan" if clean else "processed_pan"
                pan=max(-1.,min(1.,float(value)))
                self.bus_fx.set_channel_route(key,**{field:pan})
                # A CLEAN pan change cannot affect the other FX path,
                # any BUS send, or the legacy native channel controls.
                # The processed pan is also stored in native cfg for
                # correct behavior upon detaching the professional panel.
                if not clean:
                    return self._native_set_channel_param(key,"pan",pan)
                return
            if param=="solo" and key in widget.channels:
                route=self.bus_fx.get_channel_route(key)
                field="dry_solo" if route["dry_enabled"] else "processed_solo"
                self.bus_fx.set_channel_route(key,**{field:bool(value)})
                if widget.transport:
                    widget.transport.live.set_track_levels(widget.effective_levels())
                return
            return self._native_set_channel_param(key,param,value)

        view.effective_levels=MethodType(tab_levels,view)
        view._level=MethodType(tab_level,view)
        view._mute=MethodType(tab_mute,view)
        view.set_channel_param=MethodType(tab_set_channel_param,view)
        live=view.transport.live
        live.set_track_levels(view.effective_levels())
        live.set_master_volume(view.home.master_volume.value()/100.)
        view.home.master_volume.valueChanged.connect(self._set_master_only)
        if not self._default_routes_initialized:
            # Una ruta principal independiente por tira. Se conserva
            # cualquier bus personalizado (distinto de BUS 1).
            for i,strip in enumerate(view.visible_strips):
                if i>0 and int(strip.controls.get("bus",1))==1:
                    view.set_channel_param(strip.key,"bus",min(i+1,self.bus_count))
            self._default_routes_initialized=True
        self._native_select_channel=view.select_channel
        def select_channel(widget,key):
            self._native_select_channel(key)
            self._sync_aux_controls()
            self._selected_wave()
            self._update_bus_inspector()
        view.select_channel=MethodType(select_channel,view)
        self._native_wave_selected=view._wave_selected
        # Al asignar/arrastrar un archivo se regeneran las 16 tiras:
        # volver a aplicar el diseño de esta pestaña INMEDIATAMENTE.
        self._native_sync_channels=view._sync_channels
        def sync_channels(widget,*args,**kwargs):
            result=self._native_sync_channels(*args,**kwargs)
            if self.active:
                for key,item in widget.channels.items():
                    if key not in self.bus_fx.channel_routes:
                        self.bus_fx.set_channel_route(
                            key,processed_level=item["fader"].value()/100.,
                            processed_pan=float(item["strip"].controls.get("pan",0.)),
                            muted=item["mute"].isChecked(),
                            processed_solo=item["solo"].isChecked())
                    route=self.bus_fx.get_channel_route(key)
                    fader=route["dry_level"] if route["dry_enabled"] else route["processed_level"]
                    with QSignalBlocker(item["fader"]):
                        item["fader"].setValue(round(fader*100))
                    item["strip"].readout.setText(
                        f"{'L' if route['dry_enabled'] else 'FX'} {round(fader*100)}%")
                widget.transport.live.set_track_levels(widget.effective_levels())
                QTimer.singleShot(0,self.refresh)
            return result
        view._sync_channels=MethodType(sync_channels,view)
        # Dos formas de onda apiladas: seleccionada (precalculada) y
        # MASTER en tiempo real, desde la MISMA señal PCM de salida.
        wave_col=self._rack_wave_column
        self._wave_header=wave_col.itemAt(0).layout().itemAt(0).widget()
        self._wave_header_saved=self._wave_header.text()
        self._wave_header.setText("ORIGINAL / BUS FX  ·  EQ16  ·  ESPECTROGRAMA")
        wave_col.removeWidget(view.wave)
        view.wave.hide()
        wave_col.insertWidget(1,self._dashboard,1)
        self._dashboard.show()
        self._scope_timer.start()
        self._selected_wave()
        self._bus_inspector.refresh_bus(int(view.bus_select.currentData() or 1))
        self._sync_aux_controls()
        self.refresh()
        pending=getattr(self,"_pending_bus_state",None)
        if isinstance(pending,dict):
            self._load_bus_preset(pending)

    def refresh(self):
        if not self.active or self._applying:
            return
        self._applying = True
        try:
            view = self.console
            width = max(1, view.width())
            # Respeta 16 tiras y panel de archivos, sin scroll horizontal.
            sidebar = 203 if width >= 1420 else 181
            original_sources = 210 if width >= 1420 else 184
            if width < 1190:
                original_sources = 164
                sidebar = 161
            sources = round(original_sources * 1.25)
            if view.sidebar.width() != sidebar:
                view.sidebar.setFixedWidth(sidebar)
            if view.sources_panel.width() != sources:
                view.sources_panel.setFixedWidth(sources)
            view.wave_source.setFixedWidth(154 if width >= 1420 else 125)
            view._fit_strips()
            self._simplify_channel_controls()
            self._bind_channel_select_targets()
            self._sync_channel_map()
            self._matrix_send_panel.refresh()
            self.console.file_list.hide()
            self.console.summary.hide()
            # Evitar que el nombre inferior de los 16 canales quede
            # cortado en la pantalla real de 1080p.
            # El monitor ocupa mayor altura y las tiras son compactas.
            # La parte gráfica se divide 70% dos ondas / 30% FFT + EQ16.
            target=self._rack_height_target(view)
            view.rack.setFixedHeight(target)
            for strip in view.visible_strips:
                strip.setMaximumHeight(365)
                strip.setMinimumHeight(0)
            # The 144px MASTER and BUS faders must not overlap
            # "Ventana flotante" on a shorter macOS desktop. Only compact
            # the SIDEBAR, never reduce the two requested tall faders.
            self._set_sidebar_compact(view.sidebar.height()<710)
            self._last_width = width
        finally:
            self._applying = False

    def _set_sidebar_compact(self,compact):
        """Fit tall bus/master faders without overlap on shorter desktops.

        The small-screen-only consolidation puts the existing floating-view
        button in the sidebar title row; it does not remove any capability.
        The bus FX list already has its own bounded local scroll container.
        """
        view=self.console
        side=view.sidebar.layout()
        if compact:
            if getattr(self,"_compact_title_row",None) is None:
                brand=side.itemAt(0).widget()
                assert brand is not None
                self._compact_brand=brand
                self._compact_brand_title=brand.text()
                side.removeWidget(brand)
                side.removeWidget(view.float_button)
                title=QHBoxLayout()
                title.setContentsMargins(0,0,0,0)
                title.setSpacing(2)
                brand.setText("StemMIDI · PRO")
                brand.setFixedHeight(19)
                title.addWidget(brand,1)
                view.float_button.setText("↗")
                view.float_button.setToolTip("Ventana flotante del mezclador")
                view.float_button.setFixedSize(24,21)
                title.addWidget(view.float_button,0)
                side.insertLayout(0,title)
                self._compact_title_row=title
            if getattr(self,"_compact_preset_row",None) is None:
                # In compact height, the existing preset, LOAD and SAVE
                # occupy a single row rather than three stacked rows.
                preset_label=side.itemAt(2).widget()
                preset_buttons=side.itemAt(4).layout()
                assert preset_label is not None and preset_buttons is not None
                self._compact_preset_label=preset_label
                self._compact_preset_buttons=preset_buttons
                side.removeWidget(preset_label)
                preset_label.hide()
                side.removeWidget(view.presets)
                side.removeItem(preset_buttons)
                preset_buttons.removeWidget(view.restore_preset)
                preset_buttons.removeWidget(view.save_preset)
                preset_line=QHBoxLayout()
                preset_line.setContentsMargins(0,0,0,0)
                preset_line.setSpacing(2)
                preset_line.addWidget(view.presets,1)
                view.restore_preset.setText("↓")
                view.restore_preset.setToolTip("Cargar preajuste de mezcla")
                view.restore_preset.setFixedWidth(23)
                preset_line.addWidget(view.restore_preset,0)
                view.save_preset.setText("↑")
                view.save_preset.setToolTip("Guardar preajuste de mezcla")
                view.save_preset.setFixedWidth(23)
                preset_line.addWidget(view.save_preset,0)
                side.insertLayout(2,preset_line)
                self._compact_preset_row=preset_line
            side.setSpacing(1)
            inspector_height=(90 if view.sidebar.height()<570 else 110)
            self._bus_inspector.setMinimumHeight(inspector_height)
            self._bus_inspector.setFixedHeight(inspector_height)
            view.presets.setMinimumHeight(23)
            view.restore_preset.setMinimumHeight(23)
            view.save_preset.setMinimumHeight(23)
            view.bus_select.setMinimumHeight(20 if view.sidebar.height()<570 else 24)
            limit=(1 if view.sidebar.height()<570 else 4)
            if self._bus_fx_visible_limit!=limit:
                self._bus_fx_visible_limit=limit
                self._refresh_bus_fx_strip()
        else:
            if getattr(self,"_compact_preset_row",None) is not None:
                preset_line=self._compact_preset_row
                preset_line.removeWidget(view.presets)
                preset_line.removeWidget(view.restore_preset)
                preset_line.removeWidget(view.save_preset)
                side.removeItem(preset_line)
                preset_line.deleteLater()
                side.insertWidget(2,self._compact_preset_label)
                self._compact_preset_label.show()
                side.insertWidget(3,view.presets)
                view.restore_preset.setMinimumWidth(0)
                view.restore_preset.setMaximumWidth(16777215)
                view.save_preset.setMinimumWidth(0)
                view.save_preset.setMaximumWidth(16777215)
                view.restore_preset.setText("CARGAR")
                view.save_preset.setText("GUARDAR")
                self._compact_preset_buttons.addWidget(view.restore_preset)
                self._compact_preset_buttons.addWidget(view.save_preset)
                side.insertLayout(4,self._compact_preset_buttons)
                self._compact_preset_row=None
            if getattr(self,"_compact_title_row",None) is not None:
                title=self._compact_title_row
                title.removeWidget(self._compact_brand)
                title.removeWidget(view.float_button)
                side.removeItem(title)
                title.deleteLater()
                side.insertWidget(0,self._compact_brand)
                self._compact_brand.setText(self._compact_brand_title)
                self._compact_brand.setFixedHeight(23)
                view.float_button.setMinimumSize(0,0)
                view.float_button.setMaximumSize(16777215,16777215)
                view.float_button.setText("Ventana flotante")
                side.addWidget(view.float_button,0)
                self._compact_title_row=None
            side.setSpacing(4)
            self._bus_inspector.setMinimumHeight(140)
            self._bus_inspector.setFixedHeight(140)
            view.presets.setMinimumHeight(27)
            view.restore_preset.setMinimumHeight(29)
            view.save_preset.setMinimumHeight(29)
            view.bus_select.setMinimumHeight(29)
            if self._bus_fx_visible_limit!=6:
                self._bus_fx_visible_limit=6
                self._refresh_bus_fx_strip()

    def deactivate(self):
        if not self.active:
            return
        self.active = False
        self._rack_drag=None
        view = self.console
        # Antes del cambio de padre, restaurar sin excepción los controles
        # originales que la ventana flotante ya tenía.
        self._scope_timer.stop()
        self._clear_select_targets()
        wave_col=self._rack_wave_column
        wave_col.removeWidget(self._dashboard)
        self._dashboard.hide()
        wave_col.insertWidget(1,view.wave,1)
        view.wave.show()
        if hasattr(self,"_wave_header"):
            self._wave_header.setText(self._wave_header_saved)
        self._master_scope.hide()
        for window in self._channel_insert_windows.values():
            window.hide()
        # No hay procesos editores VST/AU: solo utilidades integradas.
        self.bus_fx.unbind()
        if hasattr(self,"_native_fit_strips"):
            view._fit_strips=self._native_fit_strips
        view.home.master_volume.valueChanged.disconnect(self._set_master_only)
        view.effective_levels=self._native_effective_levels
        view._level=self._native_level
        view._mute=self._native_mute
        view.set_channel_param=self._native_set_channel_param
        # Restore native mute/solo UI after leaving the two-path bus engine.
        for key,item in view.channels.items():
            strip=item["strip"]
            with QSignalBlocker(strip.mute):
                strip.mute.setChecked(bool(view.checked_mutes.get(key,False)))
            with QSignalBlocker(strip.solo):
                strip.solo.setChecked(bool(strip.controls.get("solo",False)))
        # En la flotante sigue vigente el motor y los niveles originales.
        view.transport.live.set_master_volume(1.)
        view.transport.live.set_track_levels(view.effective_levels())
        if hasattr(self,"_native_sync_channels"):
            view._sync_channels=self._native_sync_channels
        if hasattr(self,"_native_select_channel"):
            view.select_channel=self._native_select_channel
        self._restore_channel_controls()
        # The original floating view uses a single processed-channel fader.
        for key,item in view.channels.items():
            if key in self.bus_fx.channel_routes:
                level=self.bus_fx.get_channel_route(key)["processed_level"]
                with QSignalBlocker(item["fader"]):
                    item["fader"].setValue(round(level*100))
                item["strip"].readout.setText(f"{round(level*100)}%")
        self._hide_tab_controls()
        self._disable_bus_engine()
        old = self._saved
        bank = view.channel_panel.layout()
        bank.removeWidget(self._bar)
        self._bar.hide()
        view.setStyleSheet(old["style"])
        view.layout().setSpacing(old["root_spacing"])
        view.right_layout.setSpacing(old["right_spacing"])
        bank.setSpacing(old["panel_spacing"])
        view.sidebar.setFixedWidth(old["sidebar_width"])
        view.sources_panel.setFixedWidth(old["sources_width"])
        view.wave_source.setFixedWidth(old["wave_width"])
        view.rack.setFixedHeight(old["rack_height"])
        for strip in view.visible_strips:
            strip.setMinimumHeight(0)
            strip.setMaximumHeight(16777215)
        view._fit_strips()

    def _routing_head(self):
        # rack → matriz/forma de onda → cabecera de la matriz
        return self.console.rack.layout().itemAt(0).layout().itemAt(0).layout()

    def _show_tab_controls(self):
        view = self.console
        side = view.sidebar.layout()
        side.setSpacing(4)
        view.sources_panel.layout().setSpacing(8)
        head = self._routing_head()
        head.setSpacing(7)
        view.bus_select.setMinimumHeight(27)
        view.bus_select.setMaximumWidth(100)
        view.presets.setMinimumHeight(27)
        for btn in (view.restore_preset, view.save_preset, view.open_sources):
            btn.setMinimumHeight(29)
        route_row=side.itemAt(1).layout()
        route_row.removeWidget(view.bus_select)
        route_row.addWidget(self._bus_modes,1)
        self._bus_modes.setFixedWidth(99)
        self._bus_modes.show()
        self._bus_lower_layout.addWidget(view.bus_select,1)
        view.bus_select.setMaximumWidth(16777215)
        view.bus_select.setMinimumHeight(29)
        # Selector pegado exactamente encima del fader de BUS inferior.
        side.insertWidget(side.count()-2,self._bus_lower,0)
        self._bus_lower.show()
        view.inspector.setStyleSheet("""
        QTabWidget::pane{border:1px solid #315c74;background:#091b2a;}
        QTabBar::tab{background:#102d40;color:#c8edfd;
                    padding:5px 8px;min-width:42px;font-size:10px;
                    border:1px solid #365467;}
        QTabBar::tab:selected{background:#0a5c87;color:#fff;}
        """)
        head.insertWidget(2, self._bus_bank, 0)
        self._bus_bank.setVisible(self.bus_count == 32)
        assert side.replaceWidget(view.inspector,self._bus_inspector) is not None
        view.inspector.hide()
        self._bus_inspector.show()
        # The effects chain lives DIRECTLY BELOW the AUX selector/slider,
        # never between the EQ/FX/DIN inspector and the AUX controls.
        self._bus_fx_row.show()
        self._bus_fx_strip.show()
        # Two faders + VU + gain labels must remain fully above the
        # bottom "Ventana flotante" control at compact dashboard heights.
        # Twice the previous 72px tab fader: independent MASTER and BUS.
        # Meter height follows its fader; the VUs are slimmer to free room.
        for widget in (view.master_fader,view.master_meter,
                       view.selected_bus_fader,view.bus_meter):
            widget.setFixedHeight(144)
        for meter in (view.master_meter,view.bus_meter):
            meter.setFixedWidth(32)
        # La pestaña ya tiene la lista completa y arrastrable a la derecha.
        # Eliminar solo aquí la duplicación FUENTES/checkboxes del lateral,
        # para recuperar espacio para la cadena de plugins.
        for index in range(side.count()):
            part=side.itemAt(index).layout()
            if part and any(part.itemAt(i).widget() is view.open_sources
                            for i in range(part.count())):
                for i in range(part.count()):
                    widget=part.itemAt(i).widget()
                    if widget is not None:
                        self._saved["source_row"].append((widget,not widget.isHidden()))
                        widget.hide()
                break
        view.file_list.hide()
        view.file_list.setMinimumHeight(0)
        view.file_list.setMaximumHeight(0)
        view.summary.hide()
        # BusInspector itself requires 140px. Avoid its unused 26px gap
        # crushing the insert LEDs/rows below.
        self._bus_inspector.setFixedHeight(140)
        view.inspect_name.setText(f"PROCESADO DEL BUS {int(view.bus_select.currentData() or 1):02d}")
        i=side.indexOf(self._bus_inspector)
        side.insertWidget(i+1,self._aux_panel,0)
        side.insertWidget(i+2,self._bus_fx_row,0,Qt.AlignLeft)
        self._aux_panel.show()
        self._refresh_aux_options()
        QTimer.singleShot(0,self._sync_bus_fx_geometry)
        head.replaceWidget(view.routing, view.routing) if False else None
        assert view.rack.layout().replaceWidget(
            self._routing_original, self._routing_tab) is not None
        self._routing_original.hide()
        self._routing_tab.show()
        self._matrix_send_panel.show()
        QTimer.singleShot(0,self._matrix_send_panel.refresh)
        view.routing = self._routing_tab
        # El deslizador horizontal del bus ya está duplicado debajo.
        for i in range(view.main_bus_line.count()):
            widget = view.main_bus_line.itemAt(i).widget()
            if widget is not None:
                self._saved["bus_row"].append((widget,not widget.isHidden()))
                widget.hide()
        self._refresh_bus_selection()

    def _hide_tab_controls(self):
        view = self.console
        side = view.sidebar.layout()
        # Restore native sidebar structure and its full-width float button.
        if getattr(self,"_compact_title_row",None) is not None:
            self._set_sidebar_compact(False)
        side.setSpacing(self._saved["side_spacing"])
        view.sources_panel.layout().setSpacing(self._saved["source_layout_spacing"])
        head = self._routing_head()
        head.setSpacing(self._saved["route_head_spacing"])
        for btn in (view.restore_preset,view.save_preset,view.open_sources):
            btn.setMinimumHeight(0)
        view.bus_select.setMinimumHeight(0)
        view.bus_select.setMaximumWidth(16777215)
        view.presets.setMinimumHeight(0)
        # Las dos selecciones son widgets exclusivos de la pestaña.
        route_row=side.itemAt(1).layout()
        self._bus_lower_layout.removeWidget(view.bus_select)
        side.removeWidget(self._bus_lower)
        self._bus_lower.hide()
        route_row.removeWidget(self._bus_modes)
        self._bus_modes.hide()
        route_row.addWidget(view.bus_select,1)
        side.removeWidget(self._aux_panel)
        self._aux_panel.hide()
        assert side.replaceWidget(self._bus_inspector,view.inspector) is not None
        self._bus_inspector.hide()
        side.removeWidget(self._bus_fx_row)
        self._bus_fx_row.hide()
        self._bus_fx_strip.hide()
        for widget in (view.master_fader,view.master_meter,
                       view.selected_bus_fader,view.bus_meter):
            widget.setFixedHeight(96)
        for meter in (view.master_meter,view.bus_meter):
            meter.setFixedWidth(49)
        view.inspector.show()
        view.inspect_name.setText(self._saved["inspect_name"])
        for widget,visible in self._saved["source_row"]:
            widget.setVisible(visible)
        view.file_list.setMinimumHeight(self._saved["source_list"][1])
        view.file_list.setMaximumHeight(self._saved["source_list"][2])
        view.file_list.setVisible(not self._saved["source_list"][0])
        view.summary.setVisible(not self._saved["summary_hidden"])
        view.inspector.setStyleSheet(self._saved["inspector_style"])
        self._routing_head().itemAt(0).widget().setText(
            self._saved["routing_header_text"])
        head.removeWidget(self._bus_bank)
        self._bus_bank.hide()
        assert view.rack.layout().replaceWidget(
            self._routing_tab, self._routing_original) is not None
        self._routing_tab.hide()
        self._matrix_send_panel.hide()
        self._routing_original.show()
        view.routing = self._routing_original
        # Volver a los 16 buses que ya tenía la ventana flotante.
        self._last_bus_selected = int(view.bus_select.currentData() or 1)
        with QSignalBlocker(view.bus_select):
            view.bus_select.clear()
            for number in range(1,17):
                view.bus_select.addItem(f"Bus {number:02d}",number)
            view.bus_select.setCurrentIndex(
                max(0,view.bus_select.findData(min(16,self._last_bus_selected))))
        view._bus_changed()
        for widget, visible in self._saved["bus_row"]:
            widget.setVisible(visible)

    def _clear_select_targets(self):
        import shiboken6
        for target in list(self._select_targets):
            if shiboken6.isValid(target):
                target.removeEventFilter(self)
        self._select_targets.clear()

    def _bind_channel_select_targets(self):
        import shiboken6
        self._clear_select_targets()
        for strip in self.console.visible_strips:
            for target in (strip,strip.fader,strip.meter,
                           strip.title_label,strip.name_label,
                           strip.dials["pan"],strip.mute,strip.solo):
                if shiboken6.isValid(target):
                    target.installEventFilter(self)
                    self._select_targets[target]=strip.key

    def _set_master_only(self, value):
        if self.active and self.console.transport:
            # No modificar ni siquiera una ganancia de pista ni bus.
            self.console.transport.live.set_master_volume(value/100.)

    def _selected_wave(self):
        if not self.active:return
        view=self.console
        item=view.channels.get(view.inspected_key)
        key=view.inspected_key if item else None
        path=view.audio_path(key) if key else None
        path=str(path) if path else None
        with QSignalBlocker(view.wave_source):
            match=view.wave_source.findData(path)
            if match>=0:view.wave_source.setCurrentIndex(match)
        view.wave.set_path(path)
        self.bus_fx.scope_source=view.inspected_key
        self._dashboard.channel=str(view.inspected_key or "Voces")
        strip=item.get("strip") if item else None
        if strip is not None:
            assigned=int(strip.controls.get("bus",1))
            index=view.bus_select.findData(assigned)
            if index>=0 and view.bus_select.currentIndex()!=index:
                view.bus_select.setCurrentIndex(index)
        self._dashboard.bus_index=int(view.bus_select.currentData() or 1)
        self._dashboard.update()

    def _set_eq16_band(self,band,gain_db):
        if not self.active:return
        self.bus_fx.set_eq16(self._dashboard.bus_index,band,gain_db)

    def _scope_tick(self):
        if self.active:
            live=self.console.transport.live if self.console.transport else None
            if live is None or not live.running or live.paused:
                self.bus_fx.master_scope.clear()
                self.bus_fx.source_scope.clear()
                for cache in self.bus_fx.bus_scope.values():
                    cache.clear()
            # El scope master está oculto: no calcular su FFT ni pintarlo.
            if self._master_scope.isVisible():
                self._master_scope.refresh()
            if self._dashboard.isVisible():
                self._dashboard.refresh()

    def _sync_channel_map(self):
        mapping={
            str(item["source"]):key
            for key,item in self.console.channels.items()
            if item["source"] is not None
        }
        self.bus_fx.set_channel_map(mapping)

    def _add_channel_plugin(self,channel,kind):
        try:
            self.bus_fx.add_channel_builtin(channel,kind)
            self._redraw_channel_plugins(channel)
        except (ValueError,RuntimeError,OSError) as error:
            QMessageBox.warning(self.console,"Efecto de canal",str(error))

    def _channel_add_menu(self,channel,anchor):
        menu=QMenu(anchor)
        for kind in ("Reverb","Delay","Compresor","Sample Delay","Channel EQ"):
            action=menu.addAction(kind)
            action.triggered.connect(lambda checked=False,k=kind:
                                     self._add_channel_plugin(channel,k))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _plugin_context_menu(self,channel,uid,button):
        menu=QMenu(button)
        for action,text in (("bypass","Bypass ON/OFF"),
                            ("up","Subir en la cadena"),
                            ("down","Bajar en la cadena"),
                            ("remove","Quitar plugin del canal")):
            entry=menu.addAction(text)
            entry.triggered.connect(lambda checked=False,a=action:
                                     self._plugin_action(channel,uid,a))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _plugin_action(self,channel,uid,action):
        self.bus_fx.channel_action(channel,uid,action)
        old=self._channel_insert_windows.get((channel,uid))
        if old is not None and action=="remove":
            old.hide()
            old.deleteLater()
            self._channel_insert_windows.pop((channel,uid),None)
        self._redraw_channel_plugins(channel)

    def _open_channel_plugin(self,channel,uid):
        slot=self.bus_fx.channel_slot(channel,uid)
        if slot is None:return
        key=(channel,uid)
        popup=self._channel_insert_windows.get(key)
        if popup is None:
            popup=ChannelPluginWindow(self,channel,uid,self.console)
            self._channel_insert_windows[key]=popup
        popup.showNormal()
        popup.raise_()
        popup.activateWindow()

    def _redraw_channel_plugins(self,channel):
        state=next((v for strip,v in self._strip_state.items()
                    if strip.key==channel),None)
        if not state:return
        content=state["plugins_layout"]
        while content.count()>1:
            item=content.takeAt(1)
            widget=item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        slots=self.bus_fx.channel_plugins.get(channel,())
        for slot in slots[:6]:
            line=QFrame(state["plugins_box"])
            line.setObjectName("mixerPluginButtonRow")
            row=QHBoxLayout(line)
            row.setContentsMargins(0,0,0,0)
            row.setSpacing(1)
            line.setFixedHeight(20)
            button=QPushButton(slot.name[:11],line)
            button.setObjectName("mixerPluginName")
            button.setToolTip(
                f"{slot.name} · {'DESACTIVADO' if slot.bypass else 'ACTIVO'}"
                " · clic: editar · botón derecho: opciones")
            button.setStyleSheet(INSERT_BUTTON_STYLE)
            button.setFixedHeight(19)
            button.setProperty("pluginChannel",channel)
            button.setProperty("pluginUid",slot.uid)
            button.clicked.connect(lambda checked=False,c=channel,u=slot.uid:
                                   self._open_channel_plugin(c,u))
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos,c=channel,u=slot.uid,b=button:
                self._plugin_context_menu(c,u,b))
            row.addWidget(button,1)
            # LED VERDE=procesando / ROJO=bypass; cambia la cadena DSP real.
            led=QPushButton("●",line)
            led.setObjectName("mixerPluginPower")
            led.setFixedSize(13,18)
            led.setCheckable(True)
            led.setChecked(not slot.bypass)
            led.setToolTip("Activar/desactivar este efecto en el BUS, sin silenciar original")
            led.setStyleSheet("""
                QPushButton{background:#173040;color:#f25762;
                    border:1px solid #7a555e;border-radius:3px;
                    font-size:10px;padding:0;}
                QPushButton:checked{background:#064934;color:#38ff94;
                    border:1px solid #43d597;}
                QPushButton:hover{border-color:#f3fbff;}
            """)
            led.clicked.connect(lambda checked=False,c=channel,u=slot.uid:
                                self._plugin_action(c,u,"bypass"))
            row.addWidget(led,0)
            content.addWidget(line)
        if len(slots)>6:
            more=QPushButton(f"+{len(slots)-6} más",state["plugins_box"])
            more.setStyleSheet(INSERT_BUTTON_STYLE)
            def show_more():
                menu=QMenu(more)
                for slot in self.bus_fx.channel_plugins.get(channel,())[6:]:
                    action=menu.addAction(slot.name)
                    action.triggered.connect(
                        lambda checked=False,c=channel,u=slot.uid:
                        self._open_channel_plugin(c,u))
                menu.exec(more.mapToGlobal(more.rect().bottomLeft()))
            more.clicked.connect(show_more)
            content.addWidget(more)

    def _clean_bus_changed(self,key,bus):
        """Post-clean-fader BUS send for exactly one logical channel."""
        if bus is None:return
        bus=int(bus)
        if bus<0 or bus>32:return
        if bus>16 and self.bus_count!=32:
            # The user requested 00..32 even when the GUI is in 16-BUS
            # mode; promote routing to 32 without changing other strips.
            index=self._bus_modes.findData(32)
            if index>=0:
                self._bus_modes.setCurrentIndex(index)
        self.bus_fx.set_channel_route(key,dry_bus=bus)
        # Both visual controls represent the SAME clean BUS assignment.
        # A change from the matrix updates the channel selector without
        # emitting its signal, and a channel change repaints the matrix.
        item=self.console.channels.get(key)
        if item is not None:
            state=self._strip_state.get(item["strip"])
            if state is not None:
                selector=state["clean_bus_combo"]
                with QSignalBlocker(selector):
                    position=selector.findData(bus)
                    selector.setCurrentIndex(max(0,position))
        self._routing_tab.update()

    def _sync_direct_button(self,strip):
        state=self._strip_state.get(strip)
        if state is None:return
        route=self.bus_fx.get_channel_route(strip.key,strip.fader.value()/100.)
        enabled=bool(route["dry_enabled"])
        button=state["direct_button"]
        with QSignalBlocker(button):
            button.setChecked(enabled)
        level=route["dry_level"] if enabled else route["processed_level"]
        with QSignalBlocker(strip.fader):
            strip.fader.setValue(round(level*100))
        with QSignalBlocker(strip.mute):
            strip.mute.setChecked(bool(
                route["dry_muted"] if enabled else route["processed_muted"]))
        with QSignalBlocker(strip.solo):
            strip.solo.setChecked(bool(
                route["dry_solo"] if enabled else route["processed_solo"]))
        # One visible pan dial, two separate stored panorama values.
        # Change focus without sending a change to the other path.
        pan=strip.dials.get("pan")
        if pan is not None:
            target_pan=(float(route.get("dry_pan",0.)) if enabled else
                        float(route.get("processed_pan",
                              strip.controls.get("pan",0.))))
            with QSignalBlocker(pan):
                pan.setValue(round(target_pan*100))
            pan.setToolTip(
                f"{'LIMPIO' if enabled else 'FX'} · Panorama exclusivo de "
                f"{strip.caption}; el BUS recibe la señal original sin panear.")
        # The selector occupies exactly the top NAME LABEL's space.
        # When not focused on LIMPIO the normal name returns.
        selector=state["clean_bus_combo"]
        with QSignalBlocker(selector):
            index=selector.findData(int(route.get("dry_bus",0)))
            selector.setCurrentIndex(max(0,index))
        strip.title_label.setVisible(not enabled)
        selector.setVisible(enabled)
        selector.setEnabled(strip.source is not None)
        selector.setFixedHeight(strip.title_label.height())
        selector.setToolTip(
            f"{strip.caption} · envío pre-fader al BUS 00–32. "
            "El Mute, el fader y el panorama LIMPIO no afectan al BUS. "
            "BUS 00: sin envío; salida limpia directa al MASTER.")
        target="LIMPIO" if enabled else "FX"
        strip.mute.setToolTip(f"Silenciar solo {target} · {strip.caption}")
        strip.solo.setToolTip(f"Solo solo {target} · {strip.caption}")
        strip.readout.setText(
            f"{'L' if enabled else 'FX'} {round(level*100)}%")

    def _toggle_channel_direct(self,key,enabled):
        # LIMPIO chooses the CONTROLS' target, not the audio path.
        # Both dry and processed signals continue playing independently.
        route=self.bus_fx.set_channel_route(key,dry_enabled=bool(enabled))
        item=self.console.channels.get(key)
        if item is None:return
        strip=item["strip"]
        self._sync_direct_button(strip)
        if self.console.transport:
            self.console.transport.live.set_track_levels(
                self.console.effective_levels())

    def _simplify_channel_controls(self):
        self._strip_state={
            strip:state for strip,state in self._strip_state.items()
            if strip in self.console.visible_strips}
        for strip in self.console.visible_strips:
            if strip not in self._strip_state:
                layout=strip.layout()
                native_pan=strip.dials["pan"]
                row=next((
                    layout.itemAt(i).layout()
                    for i in range(layout.count())
                    if layout.itemAt(i).layout() and
                    layout.itemAt(i).layout().indexOf(native_pan)>=0),
                    None)
                assert row is not None
                pan=PanBalanceDial(strip)
                pan.setFixedSize(native_pan.width(),native_pan.height())
                pan.setValue(round(strip.controls.get("pan",0)*100))
                pan.valueChanged.connect(
                    lambda value,key=strip.key:
                    self.console.set_channel_param(key,"pan",value/100.))
                row.replaceWidget(native_pan,pan)
                native_pan.hide()
                strip.dials["pan"]=pan

                panel=QFrame(strip)
                panel.setObjectName("mixerChannelInsertRack")
                panel.setStyleSheet("""
                  QFrame#mixerChannelInsertRack {
                    background:rgba(9,33,53,150);
                    border:1px solid #35617b;
                    border-radius:4px;
                  }
                """)
                content=QVBoxLayout(panel)
                content.setContentsMargins(2,2,2,2)
                content.setSpacing(2)
                add=QPushButton("+ FX",panel)
                add.setObjectName("mixerChannelInsertAdd")
                add.setFixedHeight(20)
                add.setToolTip("Añadir efecto insertado solo a este canal")
                add.setStyleSheet(INSERT_BUTTON_STYLE)
                add.clicked.connect(lambda checked=False,k=strip.key,a=add:
                                    self._channel_add_menu(k,a))
                content.addWidget(add)
                # Encima del PAN: botones de plugins reales; el espacio sin
                # usar queda detrás y no separa PAN de FADER.
                original_stretch=[layout.stretch(i)
                                  for i in range(layout.count())]
                layout.insertWidget(2,panel,0)
                layout.insertStretch(3,1)
                # DIRECT toggle is immediately ABOVE M and S, independent
                # of the channel FX rack and of the BUS control.
                direct=QPushButton("LIMPIO",strip)
                direct.setObjectName("mixerDirectMasterToggle")
                direct.setCheckable(True)
                direct.setFixedHeight(19)
                direct.setStyleSheet("""
                    QPushButton{background:#163245;color:#9fc1d4;
                        border:1px solid #467287;border-radius:3px;
                        font-size:9px;font-weight:850;padding:1px;}
                    QPushButton:checked{background:#0b7753;color:#effff6;
                        border:1px solid #79f8b6;}
                """)
                direct.setToolTip(
                    "Pulsado: fader, M y S controlan solo la señal LIMPIA. "
                    "Sin pulsar: controlan solo la señal procesada FX. "
                    "Ambas rutas siguen sonando independientemente.")
                direct.setEnabled(strip.source is not None)
                row_buttons=next(
                    (i for i in range(layout.count())
                     if layout.itemAt(i).layout() is not None
                     and layout.itemAt(i).layout().indexOf(strip.mute)>=0),
                    -1)
                assert row_buttons>=0
                layout.insertWidget(row_buttons,direct,0)
                direct.toggled.connect(
                    lambda checked,key=strip.key:
                    self._toggle_channel_direct(key,checked))
                for i in range(layout.count()):
                    layout.setStretch(i,1 if i==3 else 0)
                strip.setMaximumHeight(365)
                strip.setMinimumHeight(0)
                # The existing top channel label (e.g. BATERÍA) changes
                # to BUS 00..32 ONLY while LIMPIO is focused. This does not
                # add another row, scroll or caption to the channel.
                clean_bus=QComboBox(strip)
                clean_bus.setObjectName("mixerCleanBusSelector")
                clean_bus.setFixedHeight(strip.title_label.height())
                clean_bus.setSizePolicy(
                    QSizePolicy.Expanding,QSizePolicy.Fixed)
                clean_bus.setStyleSheet("""
                    QComboBox#mixerCleanBusSelector {
                      color:#ddfff8; background:#103b4c;
                      border:1px solid #39bfa0;border-radius:2px;
                      font-size:9px;font-weight:800;padding:0 1px;
                    }
                    QComboBox#mixerCleanBusSelector::drop-down {
                      width:11px;border:0;
                    }
                    QComboBox#mixerCleanBusSelector QAbstractItemView {
                      background:#0b2638;color:#e7faff;
                      selection-background-color:#226780;
                    }
                """)
                for number in range(33):
                    clean_bus.addItem(f"BUS {number:02d}",number)
                title_pos=layout.indexOf(strip.title_label)
                assert title_pos>=0
                layout.insertWidget(title_pos,clean_bus,0)
                clean_bus.hide()
                clean_bus.currentIndexChanged.connect(
                    lambda index,c=clean_bus,k=strip.key:
                    self._clean_bus_changed(k,c.itemData(index)))
                self._strip_state[strip]={
                    "clean_bus_combo":clean_bus,
                    "native_pan":native_pan,"new_pan":pan,"pan_row":row,
                    "plugins_box":panel,"plugins_layout":content,
                    "direct_button":direct,
                    "sizes":{key:dial.size() for key,dial in strip.dials.items()
                             if key!="pan"},
                    "visibles":{key:not dial.isHidden()
                                 for key,dial in strip.dials.items()
                                 if key!="pan"},
                    "arm_visible":not strip.arm.isHidden(),
                    "stretches":original_stretch,
                    "spacing":layout.spacing(),
                }
                layout.setSpacing(2)
                self._redraw_channel_plugins(strip.key)
            self._sync_direct_button(strip)
            for key in ("trim","high","send"):
                strip.dials[key].hide()
            strip.arm.hide()
            strip.dials["pan"].show()

    def _restore_channel_controls(self):
        for strip,state in list(self._strip_state.items()):
            if strip not in self.console.visible_strips:
                continue
            row=state["pan_row"]
            pan=state["new_pan"]
            oldpan=state["native_pan"]
            # The native floating view has ONE pan, which corresponds
            # to the processed path; don't accidentally copy CLEAN pan
            # when the user detaches while LIMPIO is selected.
            processed_pan=float(self.bus_fx.get_channel_route(
                strip.key).get("processed_pan",strip.controls.get("pan",0.)))
            with QSignalBlocker(oldpan):
                oldpan.setValue(round(processed_pan*100))
            strip.controls["pan"]=processed_pan
            self.console.control_state[strip.key]=dict(strip.controls)
            if strip.source is not None and self.console.transport:
                self.console.transport.live.configure_channel(
                    strip.key,{"pan":processed_pan})
            row.replaceWidget(pan,oldpan)
            pan.hide()
            pan.deleteLater()
            oldpan.show()
            strip.dials["pan"]=oldpan
            layout=strip.layout()
            button=state["direct_button"]
            selector=state["clean_bus_combo"]
            layout.removeWidget(selector)
            selector.hide()
            selector.deleteLater()
            strip.title_label.show()
            layout.removeWidget(button)
            button.hide()
            button.deleteLater()
            layout.removeWidget(state["plugins_box"])
            state["plugins_box"].hide()
            state["plugins_box"].deleteLater()
            # insertStretch inserted at index3, plugin at2; remove
            # the stretch and restore original spacing.
            layout.takeAt(2)
            for key in ("trim","high","send"):
                dial=strip.dials[key]
                size=state["sizes"][key]
                dial.setFixedSize(size.width(),size.height())
                dial.setVisible(state["visibles"][key])
            strip.arm.setVisible(state["arm_visible"])
            layout.setSpacing(state["spacing"])
            for i,stretch in enumerate(state["stretches"]):
                if i<layout.count():
                    layout.setStretch(i,stretch)
        self._strip_state.clear()

    def _enable_bus_engine(self):
        live=self.console.transport.live
        if getattr(self,"_live_wrapped",False):return
        self._native_configure=live.configure_channel
        self._native_bus_level=live.set_bus_level
        def configure(instance,name,settings):
            self._native_configure(name,settings)
            if isinstance(settings,dict) and "bus" in settings:
                bus=max(0,min(self.bus_count,int(settings["bus"])))
                # Native ProConsoleEngine supports only buses 1..16.
                # This professional tab explicitly also supports 0=NONE.
                if bus==0 or bus>16:
                    cfg=dict(instance._channel_controls.get(name,{}))
                    cfg["bus"]=bus
                    instance._channel_controls={
                        **instance._channel_controls,name:cfg}
        def bus_level(instance,index,volume):
            index=int(index)
            if index<=16:return self._native_bus_level(index,volume)
            if 17<=index<=self.bus_count:
                instance._bus_levels={
                    **instance._bus_levels,
                    index:max(0.,min(1.5,float(volume)))}
        live.configure_channel=MethodType(configure,live)
        live.set_bus_level=MethodType(bus_level,live)
        self._live_wrapped=True
        if self.bus_count==32 and self._tab_bus_routes:
            for key,bus in list(self._tab_bus_routes.items()):
                if key in self.console.channels and int(self.console.channels[key]["strip"].controls.get("bus",1))==1:
                    self.console.set_channel_param(key,"bus",bus)
            self._tab_bus_routes.clear()

    def _disable_bus_engine(self):
        if not getattr(self,"_live_wrapped",False):return
        view=self.console
        self._tab_bus_routes={}
        for strip in view.visible_strips:
            bus=int(strip.controls.get("bus",1))
            if bus>16:
                self._tab_bus_routes[strip.key]=bus
                view.set_channel_param(strip.key,"bus",1)
        live=view.transport.live
        live.configure_channel=self._native_configure
        live.set_bus_level=self._native_bus_level
        self._live_wrapped=False
        self._saved["last_bus_count"]=self.bus_count
        self._routing_original.update()

    def _refresh_bus_selection(self):
        view=self.console
        old=view.bus_select.currentData() or self._last_bus_selected
        with QSignalBlocker(view.bus_select):
            view.bus_select.clear()
            for index in range(1,self.bus_count+1):
                view.bus_select.addItem(f"Bus {index:02d}",index)
            chosen=view.bus_select.findData(old)
            view.bus_select.setCurrentIndex(max(0,chosen))
        self._bus_bank.setVisible(self.bus_count==32 and self.active)
        self._routing_head().itemAt(0).widget().setText(
            f"MATRIZ · {self.bus_count} BUSES")
        if self.bus_count==16:
            self._bus_bank.setCurrentIndex(0)
        self._routing_tab.update()
        self._matrix_send_panel.refresh()
        view._bus_changed()
        if self.active:
            self._update_bus_inspector()

    def _bus_count_changed(self,index):
        count=self._bus_modes.itemData(index)
        if count not in (16,32):return
        self.bus_count=count
        self.bus_fx.set_bus_count(count)
        self._refresh_aux_options()
        if self.active and count==16:
            for strip in self.console.visible_strips:
                if int(strip.controls.get("bus",1))>16:
                    self._tab_bus_routes[strip.key]=strip.controls["bus"]
                    self.console.set_channel_param(strip.key,"bus",1)
        if self.active and count==32:
            for key,bus in list(self._tab_bus_routes.items()):
                if key in self.console.channels and int(self.console.channels[key]["strip"].controls.get("bus",1))==1:
                    self.console.set_channel_param(key,"bus",bus)
            self._tab_bus_routes.clear()
        self._refresh_bus_selection()

    def _bank_changed(self,index):
        self._routing_tab.bus_offset=int(self._bus_bank.itemData(index) or 0)
        self._routing_tab.update()

    def _update_bus_inspector(self,*_):
        if not self.active:return
        bus=int(self.console.bus_select.currentData() or 1)
        self.console.inspect_name.setText(f"PROCESADO DEL BUS {bus:02d}")
        self._bus_inspector.refresh_bus(bus)
        self._refresh_bus_fx_strip()
        self._dashboard.bus_index=bus
        self._dashboard.update()

    def _refresh_bus_fx_strip(self):
        """Redraw the selected BUS FX chain as channel-style vertical inserts."""
        if not self.active:return
        bus=int(self.console.bus_select.currentData() or 1)
        while self._bus_fx_rows.count():
            item=self._bus_fx_rows.takeAt(0)
            widget=item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._bus_fx_row_widgets=[]
        slots=self.bus_fx.plugins.get(bus,())
        tiny=self.console.sidebar.height()<570 and self.active
        # In very short windows, keep ALL effects scrollable in this local
        # strip instead of wasting another 18px on "+more" below one effect.
        shown=slots if tiny else slots[:self._bus_fx_visible_limit]
        for index,slot in enumerate(shown):
            frame=QFrame(self._bus_fx_list)
            frame.setObjectName("mixerBusInsertRowItem")
            frame.setFixedHeight(22)
            frame.setProperty("bus",bus)
            frame.setProperty("slotIndex",index)
            line=QHBoxLayout(frame)
            line.setContentsMargins(0,0,0,0)
            line.setSpacing(2)
            button=QPushButton(f"{index+1} · {slot.name[:15]}",frame)
            button.setObjectName("mixerBusInsertName")
            button.setFixedHeight(19)
            button.setToolTip(
                f"BUS {bus:02d} · {slot.name}: clic para EDITAR")
            button.setStyleSheet(INSERT_BUTTON_STYLE)
            button.clicked.connect(
                lambda checked=False,b=bus,i=index:self._edit_bus_insert(i,b))
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda point,b=bus,i=index,anchor=button:
                self._bus_insert_context(b,i,anchor,point))
            line.addWidget(button,1)
            # ONE power LED, identical to channel inserts:
            # GREEN=processing, RED=bypass. No ON/OFF words or buttons.
            led=QPushButton("●",frame)
            led.setObjectName("mixerBusInsertPower")
            led.setFixedSize(13,18)
            led.setCheckable(True)
            led.setChecked(not slot.bypass)
            led.setToolTip(
                f"BUS {bus:02d} · {slot.name} · "+
                ("activo" if not slot.bypass else "en bypass")+
                " · clic para conmutar")
            led.setStyleSheet("""
              QPushButton#mixerBusInsertPower{
                background:#43252d;color:#ff6571;
                border:1px solid #a7525d;border-radius:3px;
                font-size:10px;padding:0;}
              QPushButton#mixerBusInsertPower:checked{
                background:#064934;color:#38ff94;
                border:1px solid #43d597;}
              QPushButton#mixerBusInsertPower:hover{border-color:#e7ffff;}
            """)
            led.clicked.connect(
                lambda checked=False,b=bus,i=index:
                self._set_bus_insert_bypass(b,i,not checked))
            line.addWidget(led,0)
            self._bus_fx_rows.addWidget(frame)
            self._bus_fx_row_widgets.append(frame)
        if len(slots)>self._bus_fx_visible_limit and not tiny:
            more=QPushButton(
                f"+{len(slots)-self._bus_fx_visible_limit} efectos más",
                self._bus_fx_list)
            more.setObjectName("mixerBusInsertMore")
            more.setFixedHeight(18)
            more.clicked.connect(
                lambda checked=False,b=bus,anchor=more:
                self._show_more_bus_inserts(b,anchor))
            self._bus_fx_rows.addWidget(more)
        elif not slots:
            label=QLabel(f"BUS {bus:02d} · sin filtros",self._bus_fx_list)
            label.setFixedHeight(18)
            label.setStyleSheet("font-size:9px;color:#9ec4d1")
            self._bus_fx_rows.addWidget(label)
        # Each LED has a full 22px row. A tall chain scrolls INSIDE this
        # small block, instead of overlapping AUX, MASTER and the fader.
        rows_shown=min(len(slots),self._bus_fx_visible_limit)
        extra=1 if (len(slots)>self._bus_fx_visible_limit and not tiny) or not slots else 0
        inner_height=(rows_shown*22+max(0,rows_shown-1)*2+
                      extra*18+(2 if rows_shown and extra else 0))
        if tiny and slots:
            content_height=len(slots)*22+max(0,len(slots)-1)*2
            self._bus_fx_list.setFixedHeight(content_height)
            viewport_height=22
        else:
            self._bus_fx_list.setFixedHeight(inner_height)
            budget=max(46,min(144,self.console.sidebar.height()-470))
            viewport_height=min(inner_height,budget)
        self._bus_fx_scroll.setFixedHeight(viewport_height)
        self._bus_fx_row.setFixedHeight(19+1+4+viewport_height+4)
        self._bus_fx_button.setText("+ FX")
        self._bus_fx_button.setToolTip(f"Añadir efecto al BUS {bus:02d}")
        self._sync_bus_fx_geometry()

    def _sync_bus_fx_geometry(self):
        """All BUS FX slots share one width; never exceed AUX dropdown edge.

        The auxiliary selector is the actual width reference rather than a
        hardcoded pixel size: compact windows and different DPI scale safely.
        A full effect name stays in its tooltip if the label is too long.
        """
        if not self.active or not self._aux_panel.isVisible():return
        aux_width=self._aux_target.width()
        if aux_width<30:return
        # Origin of both controls is the sidebar's same left content edge.
        self._bus_fx_row.setFixedWidth(aux_width)
        self._bus_fx_strip.setFixedWidth(aux_width)
        self._bus_fx_button.setFixedWidth(aux_width-4)
        self._bus_fx_scroll.setFixedWidth(aux_width-4)
        # Fixed inner item width prevents Qt's stretch/size hints from
        # staggering buttons as labels of different length arrive.
        inner=max(22,aux_width-12)
        if self._bus_fx_list.width()!=inner:
            self._bus_fx_list.setFixedWidth(inner)
        name_width=max(8,inner-15)
        for index,frame in enumerate(self._bus_fx_row_widgets):
            frame.setFixedWidth(inner)
            name=frame.findChild(QPushButton,"mixerBusInsertName")
            if name is None:continue
            name.setFixedWidth(name_width)
            full=self.bus_fx.plugins[int(self.console.bus_select.currentData() or 1)][index].name
            # Prefer recognizable effect names over an unreadable "1 · S…"
            # in a narrow selector-width column.
            short={"Sample Delay":"S.Delay","Compresor":"Comp.",
                   "Channel EQ":"EQ"}.get(full,full)
            name.setText(name.fontMetrics().elidedText(
                short if aux_width<110 else full,
                Qt.ElideRight,max(5,name_width-6)))
            name.setToolTip(f"{index+1} · {full} · clic para editar")
        self._bus_fx_list.updateGeometry()

    def _set_bus_insert_bypass(self,bus,index,bypass):
        slots=self.bus_fx.plugins.get(int(bus),())
        if not 0<=index<len(slots):return
        if bool(slots[index].bypass)!=bool(bypass):
            self.bus_fx.toggle_bypass(bus,index)
        self._bus_inspector.refresh_bus(int(bus))
        self._refresh_bus_fx_strip()

    def _show_more_bus_inserts(self,bus,anchor):
        menu=QMenu(anchor)
        for i,slot in enumerate(self.bus_fx.plugins.get(bus,())):
            if i<self._bus_fx_visible_limit:continue
            sub=menu.addMenu(f"{i+1}. {slot.name}")
            for title,command in (("Editar","edit"),("Activar","on"),
                                  ("Desactivar","off"),("Eliminar","remove")):
                action=sub.addAction(title)
                action.triggered.connect(
                    lambda checked=False,b=bus,j=i,c=command:
                    self._bus_insert_action(j,c,b))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _bus_insert_menu(self):
        menu=QMenu(self._bus_fx_button)
        for kind in ("Channel EQ","Sample Delay","Reverb","Delay","Compresor"):
            action=menu.addAction(kind)
            action.triggered.connect(
                lambda checked=False,name=kind:self._add_bus_insert(name))
        menu.exec(self._bus_fx_button.mapToGlobal(
            self._bus_fx_button.rect().bottomLeft()))

    def _add_bus_insert(self,kind):
        bus=int(self.console.bus_select.currentData() or 1)
        try:
            self.bus_fx.make_builtin(bus,kind)
            self._bus_inspector.refresh_bus(bus)
            self._refresh_bus_fx_strip()
        except (RuntimeError,ValueError) as error:
            QMessageBox.warning(self.console,"Filtro BUS",str(error))

    def _edit_bus_insert(self,index,bus=None):
        bus=int(bus if bus is not None else
                (self.console.bus_select.currentData() or 1))
        slots=self.bus_fx.plugins.get(bus,())
        if not 0<=index<len(slots):return
        # Use the same real editor as channel inserts, not a decorative popup.
        if bus!=int(self.console.bus_select.currentData() or 1):
            selected=self.console.bus_select.findData(bus)
            if selected>=0:self.console.bus_select.setCurrentIndex(selected)
        editor=self._bus_inspector._create_parameter_editor(slots[index])
        editor.exec()

    def _bus_insert_context(self,bus,index,anchor,pos):
        slots=self.bus_fx.plugins.get(bus,())
        if not 0<=index<len(slots):return
        menu=QMenu(anchor)
        for caption,action in (("Editar efecto","edit"),
                               ("Activar","on"),("Desactivar","off"),
                               ("Subir","up"),("Bajar","down"),
                               ("Eliminar","remove")):
            item=menu.addAction(caption)
            item.triggered.connect(
                lambda checked=False,b=bus,i=index,a=action:
                self._bus_insert_action(i,a,b))
        menu.exec(anchor.mapToGlobal(pos))

    def _bus_insert_action(self,index,action,bus=None):
        bus=int(bus if bus is not None else
                (self.console.bus_select.currentData() or 1))
        if action=="edit":
            self._edit_bus_insert(index,bus)
            return
        if action in ("on","off"):
            self._set_bus_insert_bypass(bus,index,action=="off")
            return
        if action=="bypass":
            self.bus_fx.toggle_bypass(bus,index)
        elif action=="up":self.bus_fx.reorder(bus,index,-1)
        elif action=="down":self.bus_fx.reorder(bus,index,1)
        elif action=="remove":self.bus_fx.remove(bus,index)
        self._bus_inspector.refresh_bus(bus)
        self._refresh_bus_fx_strip()

    def _refresh_aux_options(self):
        selected=self._aux_target.currentData()
        with QSignalBlocker(self._aux_target):
            self._aux_target.clear()
            self._aux_target.addItem("Sin AUX",0)
            for index in range(1,self.bus_count+1):
                self._aux_target.addItem(f"AUX {index:02d}",index)
            match=self._aux_target.findData(selected)
            self._aux_target.setCurrentIndex(max(0,match))
        if self.active:self._sync_aux_controls()

    def _sync_aux_controls(self):
        if not self.active:return
        channel=self.console.channels.get(self.console.inspected_key)
        # AUX belongs to the logical channel, not the filename.
        # The same WAV/MIDI may occupy several independent mixer strips.
        self._aux_source=(str(self.console.inspected_key)
                          if channel and channel["source"] else None)
        self._updating_aux=True
        try:
            source=self._aux_source
            current=self.bus_fx.sends.get(str(source)) if source else None
            target=current[0] if current else self._aux_targets.get(str(source),0)
            gain=current[1] if current else 0.
            with QSignalBlocker(self._aux_target):
                self._aux_target.setCurrentIndex(max(0,self._aux_target.findData(target)))
            with QSignalBlocker(self._aux_slider):
                self._aux_slider.setValue(round(gain*100))
            self._aux_slider.setEnabled(bool(source))
            self._aux_target.setEnabled(bool(source))
            title=(self.console.visible_strips[0].key if self.console.visible_strips
                   else "SIN PISTA")
            if self.console.inspected_key:
                title=str(self.console.inspected_key).upper()
            self._aux_label.setText(f"ENVÍO AUX · {title[:16]}")
            self._aux_readout.setText(f"{round(gain*100)}%")
        finally:
            self._updating_aux=False

    def _aux_changed(self,*_):
        if not self.active or self._updating_aux or not self._aux_source:return
        target=int(self._aux_target.currentData() or 0)
        gain=self._aux_slider.value()/100.
        self._aux_targets[str(self._aux_source)]=target
        self._aux_readout.setText(f"{round(gain*100)}%")
        self.bus_fx.set_send(self._aux_source,target,gain)

    def _bus_preset_path(self):
        root=getattr(self.console.home.main,"project_dir",None)
        return Path(root)/"presets"/"mezclador_buses_tab.json" if root else None

    def _save_bus_preset(self):
        if not self.active:return
        path=self._bus_preset_path()
        if path is None:return
        path.parent.mkdir(parents=True,exist_ok=True)
        content=self.bus_fx.config_snapshot()
        content.update({"version":2,"bus_count":self.bus_count,
            "bus_levels":{str(k):v for k,v in
                          self.console.transport.live._bus_levels.items()}})
        tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding="utf8")
        tmp.replace(path)

    def load_project_bus_state(self, content):
        """Restore a full, single-project manifest BUS snapshot."""
        if not isinstance(content,dict):
            return False
        self._pending_bus_state=content
        if not self.active:
            return True
        return self._load_bus_preset(content)

    def _load_bus_preset(self, data=None):
        # data may be the project JSON or None for importing a legacy preset.
        if not self.active:
            if isinstance(data,dict):
                self._pending_bus_state=data
            return False
        path=self._bus_preset_path()
        if isinstance(data,dict):
            content=data
        else:
            if path is None or not path.is_file():
                return False
            content=json.loads(path.read_text(encoding="utf8"))
        try:
            if content.get("version") not in (1,2,3):
                raise ValueError("Versión de bus desconocida")
            # El proyecto contiene el estado completo: no acumular inserts
            # del proyecto anterior ni reusar su DSP o su EQ16.
            from studio_mixer_bus_fx import BUS_DEFAULT
            self.bus_fx.controls={i:dict(BUS_DEFAULT) for i in range(1,33)}
            self.bus_fx.eq16={i:[0.]*16 for i in range(1,33)}
            self.bus_fx.sends={}
            self.bus_fx.plugins={i:[] for i in range(1,33)}
            self.bus_fx.channel_plugins={}
            self.bus_fx.channel_routes={}
            for cache_name in ("_eq16_filters","_eq16_state","_filters",
                               "_filter_state","_processors","_reverb",
                               "_delay","_plugin_failures"):
                getattr(self.bus_fx,cache_name).clear()
            for key,route in content.get("channel_routes",{}).items():
                if key in self.console.channels and isinstance(route,dict):
                    fields={
                        k:v for k,v in route.items()
                        if k in ("processed_level","dry_level",
                                 "dry_pan","processed_pan",
                                 "dry_bus","dry_bus_gain","dry_enabled","muted",
                                 "dry_muted","processed_muted",
                                 "dry_solo","processed_solo")}
                    # Older projects stored only a single channel pan.
                    # Preserve that legacy FX pan when migrating instead
                    # of silently resetting it to the new default center.
                    if "processed_pan" not in fields:
                        fields["processed_pan"]=float(
                            self.console.channels[key]["strip"].controls.get(
                                "pan",0.))
                    self.bus_fx.set_channel_route(key,**fields)
            if self.console.transport:
                self.console.transport.live._bus_levels={
                    i:1. for i in range(1,33)}
            # Configure 32-BUS engine BEFORE restoring its BUS 17-32
            # faders: the transport rejects out-of-range indices otherwise.
            with QSignalBlocker(self._bus_modes):
                self._bus_modes.setCurrentIndex(
                    1 if content.get("bus_count")==32 else 0)
            self._bus_count_changed(self._bus_modes.currentIndex())
            if self.console.transport:
                for key,value in content.get("bus_levels",{}).items():
                    bus=int(key)
                    if 1<=bus<=32:
                        self.console.transport.live.set_bus_level(
                            bus,float(value))
            from studio_mixer_bus_fx import BUS_DEFAULT
            for number,items in content.get("controls",{}).items():
                bus=int(number)
                if not 1<=bus<=32 or not isinstance(items,dict):continue
                for key,value in items.items():
                    if key in BUS_DEFAULT:
                        self.bus_fx.set_control(bus,key,float(value))
            for number,gains in content.get("eq16",{}).items():
                bus=int(number)
                if 1<=bus<=32 and isinstance(gains,list) and len(gains)==16:
                    for band,db in enumerate(gains):
                        self.bus_fx.set_eq16(bus,band,float(db))
            for source,pair in content.get("sends",{}).items():
                # New manifests key sends by CHANNEL. Migrate historical
                # records keyed by source path without duplicating sends
                # across unrelated channels.
                channel_key=(
                    str(source) if source in self.console.channels else
                    next((key for key,item in self.console.channels.items()
                          if item["source"]==str(source)),None))
                if (channel_key and self.console.channels[channel_key]["source"]):
                    self.bus_fx.set_send(
                        channel_key,int(pair[0]),float(pair[1]))
            # Solo efectos internos, nunca plugins externos.
            errors=[]
            for number,rows in content.get("plugins",{}).items():
                bus=int(number)
                if not 1<=bus<=32 or not isinstance(rows,list):
                    continue
                self.bus_fx.plugins={**self.bus_fx.plugins,bus:[]}
                for data in rows:
                    try:
                        if data.get("kind")=="integrado":
                            slot=self.bus_fx.make_builtin(bus,data["name"])
                        elif data.get("path"):
                            continue  # Los VST/AU de proyectos anteriores se omiten.
                        else:
                            continue
                        self.bus_fx.apply_slot_settings(slot,data.get("settings",{}))
                        if data.get("bypass"):
                            self.bus_fx.toggle_bypass(
                                bus,len(self.bus_fx.plugins[bus])-1)
                    except (OSError,ValueError,RuntimeError,KeyError) as error:
                        errors.append(f"BUS {bus}: {data.get('name','Plugin')}: {error}")
            # Plugins INSERT propios de cada canal; conservan sus parámetros,
            # orden, bypass y vínculo con el canal al sustituir el archivo.
            for channel,rows in content.get("channel_plugins",{}).items():
                if channel not in self.console.channels or not isinstance(rows,list):
                    continue
                self.bus_fx.channel_plugins={
                    **self.bus_fx.channel_plugins,channel:[]}
                for data in rows:
                    try:
                        if data.get("kind")=="integrado":
                            slot=self.bus_fx.add_channel_builtin(
                                channel,data["name"])
                        elif data.get("path"):
                            continue  # Sin restauración de plugins externos.
                        else:
                            continue
                        self.bus_fx.apply_slot_settings(
                            slot,data.get("settings",{}))
                        if data.get("bypass"):
                            self.bus_fx.channel_action(channel,slot.uid,"bypass")
                    except (OSError,ValueError,RuntimeError,KeyError) as error:
                        errors.append(f"CANAL {channel}: {data.get('name','Plugin')}: {error}")
                self._redraw_channel_plugins(channel)
            self._bus_inspector.refresh_bus(int(self.console.bus_select.currentData() or 1))
            self.console._bus_changed()
            for strip in self.console.visible_strips:
                self._sync_direct_button(strip)
            self._matrix_send_panel.refresh()
            self.console.transport.live.set_track_levels(
                self.console.effective_levels())
            self._refresh_bus_fx_strip()
            self._sync_aux_controls()
            self._pending_bus_state=None
            if errors:
                QMessageBox.warning(self.console,"Efectos no cargados",
                    chr(10).join(errors[:8]))
            return True
        except (OSError,ValueError,TypeError,KeyError) as ex:
            QMessageBox.warning(self.console,"Preset BUS",str(ex))
            return False

    def eventFilter(self, watched, event):
        if (self.active and watched is self._aux_target
                and event.type()==QEvent.Resize):
            QTimer.singleShot(0,self._sync_bus_fx_geometry)
        if self.active and (watched is self._bar or watched.parent() is self._bar):
            if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
                self._rack_drag=(event.globalPosition().y(),
                                 self.console.rack.height())
                event.accept()
                return True
            if event.type()==QEvent.MouseMove and self._rack_drag is not None:
                self._drag_rack_height(event.globalPosition().y())
                event.accept()
                return True
            if event.type()==QEvent.MouseButtonRelease and self._rack_drag is not None:
                self._drag_rack_height(event.globalPosition().y())
                self._rack_drag=None
                event.accept()
                return True
        if (self.active and watched in self._select_targets and
                event.type()==QEvent.MouseButtonPress):
            key=self._select_targets[watched]
            if key in self.console.channels:
                self.console.select_channel(key)
        if (watched is self.console and self.active and
                event.type() == QEvent.Resize and not self._applying):
            QTimer.singleShot(0, self.refresh)
        return False



class MatrixChannelSendFaders(QWidget):
    """16 independent compact faders: CLEAN pre-fader level going to each BUS.

    Each is precisely aligned with its matrix row and has NO VU meter.
    Values follow the channel when the matrix displays a different page
    (17-32, 33-48, ...) or when its selected BUS changes.
    """
    def __init__(self,console,presentation,matrix,parent=None):
        super().__init__(parent)
        self.console=console
        self.presentation=presentation
        self.matrix=matrix
        self.setObjectName("mixerMatrixSendFaderColumn")
        self.setFixedWidth(93)
        self.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        self.setToolTip(
            "Volúmenes de envío de los 16 canales visibles hacia sus BUS. "
            "No afectan al limpio directo, a FX ni al fader del BUS.")
        self._sliders=[]
        self._channels=[None]*16
        self.matrix.installEventFilter(self)
        for row in range(16):
            slider=QSlider(Qt.Horizontal,self)
            slider.setObjectName(f"mixerMatrixSendRow{row+1:02d}")
            slider.setRange(0,150)
            slider.setSingleStep(1)
            slider.setPageStep(10)
            slider.setTracking(True)
            slider.setValue(100)
            slider.setFocusPolicy(Qt.StrongFocus)
            slider.setStyleSheet("""
               QSlider:horizontal {background:transparent;border:0}
               QSlider::groove:horizontal {height:4px;background:#244658;
                 border:1px solid #52768b;border-radius:2px}
               QSlider::sub-page:horizontal {background:#38c7bd;
                 border:0;border-radius:2px}
               QSlider::handle:horizontal {background:#d4faff;
                 border:1px solid #56a5bb;width:10px;
                 margin:-5px 0;border-radius:4px}
               QSlider:disabled::handle:horizontal {background:#58727d;
                 border-color:#364b55}
            """)
            slider.valueChanged.connect(
                lambda value,r=row:self._changed(r,value))
            self._sliders.append(slider)
        self.hide()

    def _changed(self,row,value):
        key=self._channels[row]
        if key is None:return
        self.presentation.bus_fx.set_channel_route(
            key,dry_bus_gain=value/100.)
        self._tooltip(row)

    def _tooltip(self,row):
        key=self._channels[row]
        if key is None:return
        route=self.presentation.bus_fx.get_channel_route(key)
        send_bus=int(route.get("dry_bus",0))
        value=self._sliders[row].value()
        text=(f"Canal {self.console.routing_page*16+row+1}: {key}"
              f" · ENVÍO {value}% al BUS {send_bus:02d}"
              " · solo volumen de envío; no modifica las demás salidas")
        self._sliders[row].setToolTip(text)

    def refresh(self,*_):
        first=self.console.routing_page*16
        for row,slider in enumerate(self._sliders):
            index=first+row
            strip=(self.console.visible_strips[index] if
                   index<len(self.console.visible_strips) else None)
            key=strip.key if strip is not None else None
            self._channels[row]=key
            if key is None:
                slider.hide()
                continue
            value=self.presentation.bus_fx.get_channel_route(key).get(
                "dry_bus_gain",1.)
            with QSignalBlocker(slider):
                slider.setValue(round(100.*float(value)))
            slider.setEnabled(bool(strip.source))
            slider.show()
            self._tooltip(row)
        self.align()

    def align(self):
        if not self.isVisible():
            return
        # Map real matrix cell centers to THIS panel, not to assumed 16px
        # rows. Thus rack resizing keeps each fader level with its channel.
        x0,y0,cw,ch=self.matrix._dims()
        height=max(7,min(16,round(ch)-1))
        for row,slider in enumerate(self._sliders):
            # Matrix and fader panel are SIBLINGS in the rack. Qt mapTo
            # requires an ancestor; convert via global coordinates.
            center_y=self.mapFromGlobal(self.matrix.mapToGlobal(
                QPoint(0,round(y0+(row+.5)*ch)))).y()
            slider.setGeometry(7,center_y-height//2,
                               max(35,self.width()-14),height)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        QTimer.singleShot(0,self.align)

    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(0,self.refresh)

    def eventFilter(self,watched,event):
        if watched is self.matrix and event.type() in (
                QEvent.Resize,QEvent.Move,QEvent.Show):
            QTimer.singleShot(0,self.align)
        return super().eventFilter(watched,event)


class TabBusMatrix(RouteMatrix):
    """Routing matrix for CLEAN sends (BUS 00..32), linked to strip dropdowns.

    Click an empty cell to connect that channel to its BUS; click its
    active cell to disconnect (BUS 00). Many channels may share a bus.
    Drag an ACTIVE cell to another row/column to MOVE its route:
    the source is disconnected and the destination takes the assignment.
    FX channel buses, AUX sends and direct MASTER routes are untouched.
    """
    def __init__(self,console,presentation):
        super().__init__(console,console.rack)
        self.presentation=presentation
        self.bus_offset=0
        self._press_cell=None
        self._press_pos=None
        self._dragging=False
        self._hover_cell=None
        self.setObjectName("mixerTabRoutingMatrix")
        self.setMouseTracking(True)
        self.setToolTip(
            "Matriz de envíos LIMPIOS · clic: conectar/desconectar BUS; "
            "arrastra una celda verde para mover su BUS a otro canal. "
            "BUS 00 = sin envío al BUS; la salida directa al MASTER se conserva.")

    def _cell_at(self,point):
        """(channel_key, physical_BUS) at a real mouse point, or None."""
        x0,y0,cw,ch=self._dims()
        x=float(point.x());y=float(point.y())
        if not (x0<=x<x0+16*cw and y0<=y<y0+16*ch):
            return None
        col=int((x-x0)//cw)
        row=int((y-y0)//ch)
        index=self.console.routing_page*16+row
        if not (0<=col<16 and 0<=row<16 and
                index<len(self.console.visible_strips)):
            return None
        bus=self.bus_offset+col+1
        if not 1<=bus<=self.presentation.bus_count:
            return None
        return (self.console.visible_strips[index].key,bus)

    def _current_bus(self,key):
        return int(self.presentation.bus_fx.get_channel_route(key).get(
            "dry_bus",0))

    def paintEvent(self,event):
        p=QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(),QColor("#081827"))
            x0,y0,cw,ch=self._dims()
            p.setFont(QFont("Sans",6,QFont.Bold))
            p.setPen(QColor("#8db3c3"))
            for col in range(16):
                p.drawText(QRectF(x0+col*cw,y0-14,cw,11),
                           Qt.AlignCenter,str(self.bus_offset+col+1))
            first=self.console.routing_page*16
            for row,strip in enumerate(self.console.visible_strips[first:first+16]):
                p.setPen(QColor("#b7cddc"))
                p.drawText(QRectF(0,y0+row*ch,25,ch),
                           Qt.AlignRight,str(first+row+1))
                selected_bus=self._current_bus(strip.key)
                for col in range(16):
                    bus=self.bus_offset+col+1
                    rect=QRectF(x0+col*cw+.8,y0+row*ch+.7,
                                max(2,cw-1.5),max(2,ch-1.3))
                    active=selected_bus==bus
                    cell=(strip.key,bus)
                    is_origin=(self._dragging and self._press_cell==cell)
                    is_destination=(self._dragging and self._hover_cell==cell)
                    if is_origin:
                        color=QColor("#c28c39")
                    elif is_destination:
                        color=QColor("#4a9ee8")
                    elif active:
                        color=QColor("#25e5bb")
                    else:
                        color=QColor("#203746") if (row+col)%2 else QColor("#273f4a")
                    p.fillRect(rect,color)
                    if active or is_destination:
                        pen_color=("#e9ffff" if is_destination else "#c2fff9")
                        p.setPen(QPen(QColor(pen_color),.9))
                        p.drawRect(rect)
                if row%4==3:
                    p.setPen(QPen(QColor("#476b7a"),.5))
                    y=y0+(row+1)*ch
                    p.drawLine(QPoint(x0,int(y)),QPoint(self.width()-4,int(y)))
        finally:
            p.end()

    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:
            super(RouteMatrix,self).mousePressEvent(event)
            return
        cell=self._cell_at(event.position())
        if cell is None:
            super(RouteMatrix,self).mousePressEvent(event)
            return
        # Defer mutation to release so a drag does not first unassign the
        # clicked source. QTest clicks and physical mouse drags use the
        # same state machine.
        self._press_cell=cell
        self._press_pos=event.position()
        self._dragging=False
        self._hover_cell=None
        event.accept()

    def mouseMoveEvent(self,event):
        if self._press_cell is not None and (
                event.buttons() & Qt.LeftButton):
            if self._press_pos is not None:
                delta=event.position()-self._press_pos
                if abs(delta.x())+abs(delta.y())>4:
                    self._dragging=True
            if self._dragging:
                self._hover_cell=self._cell_at(event.position())
                self.update()
            event.accept()
            return
        super(RouteMatrix,self).mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self._press_cell is None:
            super(RouteMatrix,self).mouseReleaseEvent(event)
            return
        source=self._press_cell
        target=self._cell_at(event.position())
        moving=self._dragging
        self._press_cell=None
        self._press_pos=None
        self._dragging=False
        self._hover_cell=None
        if target is None:
            self.update()
            event.accept()
            return
        source_key,source_bus=source
        target_key,target_bus=target
        selected=self._current_bus(source_key)
        if moving:
            # Only an active green route can be moved. Dragging a blank
            # background cell must never silently erase another route.
            if source!=target and selected==source_bus:
                if source_key!=target_key:
                    self.presentation._clean_bus_changed(source_key,0)
                self.presentation._clean_bus_changed(target_key,target_bus)
        elif source==target:
            # A click adds a bus or toggles it to BUS 00. Clicking the
            # same bus on multiple rows makes a shared multi-channel bus.
            value=0 if selected==source_bus else source_bus
            self.presentation._clean_bus_changed(source_key,value)
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self,event):
        # A double-click is two normal clicks on Qt; a dedicated double
        # click must not re-arm a new routing change.
        event.accept()
