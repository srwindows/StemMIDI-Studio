"""Audición de la última toma dentro de Monitor / Grabación ampliado.

No edita el WAV/FLAC grabado: el EQ se aplica a FFplay, únicamente a
la escucha. Controles y VU miden un archivo real finalizado.
"""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (
    QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSlider,QCheckBox,QComboBox
)
from preview_player import PreviewPlayer

def percent_to_gain_db(percent):
    """85 % es nivel unidad (0 dB); 0 es silencio, 100 es +12 dB."""
    value=max(0,min(100,int(percent)))
    return (round(-60+value*60/85) if value<=85
            else round((value-85)*12/15))


def gain_db_to_percent(db):
    db=max(-60,min(12,int(db)))
    return (round((db+60)*85/60) if db<=0
            else round(85+db*15/12))


class RecordReview(QFrame):
    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self.setObjectName("takeReviewPanel")
        self.setMinimumHeight(248)
        self.setStyleSheet("""
        QFrame#takeReviewPanel {background:#041b44;border:1px solid #2bb1fc;border-radius:7px;}
        QFrame#takeReviewPanel QLabel {color:#e0f8ff;}
        QFrame#takeReviewPanel QPushButton#takePlay {
          background:#0c8bca;color:#e0f8ff;border:1px solid #31d8f4;
          border-radius:6px;font-weight:800;min-height:28px;}
        QFrame#takeReviewPanel QPushButton#takePlay:disabled {
          background:#051e4c;color:#a3e4f0;border:1px solid #27a1e6;}
        """)
        body=QVBoxLayout(self)
        body.setContentsMargins(10,7,10,7)
        body.setSpacing(5)
        self.backend=PreviewPlayer("Escuchar última toma",self)
        self.backend.hide()
        self.current=None
        self.filename=QLabel("ÚLTIMA GRABACIÓN · Aún no hay una toma disponible",self)
        self.filename.setToolTip("Escucha la última grabación terminada, sin alterar el original.")
        body.addWidget(self.filename)
        bar=QHBoxLayout()
        self.play=QPushButton("▶ Play",self)
        self.play.setObjectName("takePlay")
        self.play.setToolTip("Reproducir o pausar la última grabación guardada")
        self.play.clicked.connect(self.backend.play_pause)
        self.play.setEnabled(False)
        bar.addWidget(self.play)
        self.stop=QPushButton("■",self)
        self.stop.setToolTip("Detener la preescucha")
        self.stop.clicked.connect(self.backend.stop)
        self.stop.setEnabled(False)
        bar.addWidget(self.stop)
        self.seek=QSlider(Qt.Horizontal,self)
        self.seek.setRange(0,1000)
        self.seek.setEnabled(False)
        self.seek.sliderPressed.connect(self.backend.drag_start)
        self.seek.sliderReleased.connect(self.seek_to)
        bar.addWidget(self.seek,1)
        self.time=QLabel("00:00 / 00:00",self)
        bar.addWidget(self.time)
        body.addLayout(bar)
        self.backend.playStateChanged.connect(self.state_changed)
        # El VU del reproductor, ya conectado a PCM real.
        self.vu=self.backend._measured_vu.meter
        self.vu.setParent(self)
        self.vu.setFixedHeight(51)
        self.vu.setToolTip("Niveles L/R de la toma real, antes de aplicar los tonos de preescucha")
        body.addWidget(self.vu)
        controls=QHBoxLayout()
        self.sliders={}
        self.value_labels={}
        current_eq=self.home.main.input_eq_values
        for name,desc,low,high,initial in (
            ("bass","Graves",-12,12,current_eq[0]),
            ("mid","Medios",-12,12,current_eq[1]),
            ("treble","Agudos",-12,12,current_eq[2]),
            ("volume","Volumen",0,100,
             gain_db_to_percent(self.home.main.input_gain_db))
        ):
            section=QVBoxLayout();section.setSpacing(3)
            head=QHBoxLayout()
            head.addWidget(QLabel(desc,self))
            value=QLabel((f"{initial:+d} dB" if name!="volume" else
                f"{initial}% · {percent_to_gain_db(initial):+d}dB"),self)
            self.value_labels[name]=value
            value.setMinimumWidth(80 if name=="volume" else 44)
            if name=="volume":
                self.volume_value_label=value
            head.addWidget(value)
            section.addLayout(head)
            slider=QSlider(Qt.Horizontal,self)
            slider.setFixedHeight(22)
            slider.setRange(low,high)
            slider.setValue(initial)
            slider.setToolTip(
                ("Nivel REAL de grabación: 85%=0 dB, 100%=+12 dB, 0%=silencio. "
                 "También controla el volumen de escucha." if name=="volume" else
                 "EQ REAL de grabación y de preescucha de la última toma. "
                 "Afecta al audio que se guarda, sin modificar tomas anteriores."))
            slider.valueChanged.connect(lambda n,k=name,v=value:
                v.setText(f"{n:+d} dB" if k!="volume" else
                          f"{n}% · {percent_to_gain_db(n):+d}dB"))
            if name=="volume":
                slider.valueChanged.connect(self._gain_changed)
            else:
                slider.valueChanged.connect(self.apply_eq)
                slider.sliderReleased.connect(self.apply_eq)
            section.addWidget(slider)
            if name=="volume":
                # El dial REAL de balance se traslada aquí cuando el
                # candado está abierto; no se crea un dial desconectado.
                self.balance_mount=QVBoxLayout()
                self.balance_mount.setSpacing(0)
                section.addLayout(self.balance_mount)
            controls.addLayout(section,1)
            controls.setAlignment(section,Qt.AlignTop)
            self.sliders[name]=slider
        body.addLayout(controls)
        bottom=QHBoxLayout()
        self.eq_enabled=QCheckBox("EQ activo en grabación",self)
        self.eq_enabled.setChecked(self.home.main.input_eq_enabled)
        self.eq_enabled.toggled.connect(self.apply_eq)
        bottom.addWidget(self.eq_enabled)
        self.reset=QPushButton("Tonos planos",self)
        self.reset.clicked.connect(self.flat_eq)
        bottom.addWidget(self.reset)
        bottom.addWidget(QLabel("Canales",self))
        self.channel_mode=QComboBox(self)
        self.channel_mode.addItems(("Estéreo","Mono (L+R)","Solo izquierdo","Solo derecho"))
        self.channel_mode.setToolTip("Modo de escucha; la grabación original no se modifica")
        self.channel_mode.currentIndexChanged.connect(self.change_channels)
        self.backend.channel_mode=self.channel_mode
        bottom.addWidget(self.channel_mode)
        bottom.addStretch(1)
        body.addLayout(bottom)
        self.state=QLabel("Sin toma reciente · captura EQ y volumen operativos",self)
        self.state.setWordWrap(True)
        self.state.setMaximumHeight(34)
        body.addWidget(self.state)
        self.ticker=QTimer(self)
        self.ticker.setInterval(240)
        self.ticker.timeout.connect(self.refresh)

    def refresh(self):
        recorded=self.home.main.last_file
        target=Path(recorded).expanduser() if recorded else None
        if target is not None and not target.is_file():target=None
        if target!=self.current:
            self.current=target
            if target is None:
                self.backend.clear()
                self.filename.setText("ÚLTIMA GRABACIÓN · Aún no hay una toma disponible")
            else:
                loaded=self.backend.load(str(target))
                self.filename.setText("ÚLTIMA GRABACIÓN · "+target.name
                    if loaded else "No se pudo abrir la última toma")
            self.play.setEnabled(target is not None and self.backend.current_file is not None)
            self.stop.setEnabled(self.play.isEnabled())
            self.seek.setEnabled(self.play.isEnabled())
        self.time.setText(self.backend.clock.text())
        if not self.seek.isSliderDown():
            self.seek.setRange(0,max(1,self.backend._duration_ms))
            self.seek.setValue(self.backend._current_ms)
        if self.backend._play_process is None and not self.backend._qt_active:
            self.play.setText("▶ Play")

    def seek_to(self):
        self.backend.slider.setValue(self.seek.value())
        self.backend.drag_finish()

    def state_changed(self,playing):
        self.play.setText("Ⅱ Pausa" if playing else "▶ Play")
        self.state.setText("Escuchando la última toma" if playing else
                           "Archivo original sin modificar")

    def _gain_changed(self,value):
        """Un ÚNICO nivel de grabación; espejo inferior de Inicio."""
        self.backend.volume.setValue(value)
        self.home.main.set_input_processing(gain_db=percent_to_gain_db(value))

    def sync_capture_gain(self,gain_db):
        """Un ajuste desde Inicio se refleja en el control de arriba."""
        target=gain_db_to_percent(gain_db)
        if self.sliders["volume"].value()!=target:
            from PySide6.QtCore import QSignalBlocker
            with QSignalBlocker(self.sliders["volume"]):
                self.sliders["volume"].setValue(target)
            self.backend.volume.setValue(target)
        if hasattr(self,"volume_value_label"):
            self.volume_value_label.setText(
                f"{target}% · {gain_db:+d}dB")

    def sync_capture_eq(self,enabled,values):
        """Restaurar el EQ de un proyecto sin señales recursivas."""
        from PySide6.QtCore import QSignalBlocker
        if self.eq_enabled.isChecked()!=bool(enabled):
            with QSignalBlocker(self.eq_enabled):
                self.eq_enabled.setChecked(bool(enabled))
        for key,value in zip(("bass","mid","treble"),values):
            slider=self.sliders[key]
            if slider.value()!=value:
                with QSignalBlocker(slider):slider.setValue(value)
                self.value_labels[key].setText(f"{value:+d} dB")
        self.backend.set_preview_eq(*(values if enabled else (0,0,0)))

    def apply_eq(self,*_):
        values=tuple(self.sliders[k].value()
                     for k in ("bass","mid","treble"))
        enabled=self.eq_enabled.isChecked()
        self.home.main.set_input_eq(enabled,*values)
        # Mientras se arrastra un slider, la captura ya se actualiza en
        # caliente. FFplay se reinicia SOLO al soltar, para evitar cortes
        # de la escucha en cada píxel de movimiento del ratón.
        if not any(self.sliders[k].isSliderDown()
                   for k in ("bass","mid","treble")):
            self.backend.set_preview_eq(*(values if enabled else (0,0,0)))
        self.home.update_capture_diagnostics()

    def change_channels(self,*_):
        # FFplay necesita reabrir la señal para cambiar la mezcla de canales.
        if self.backend._play_process is not None and not self.backend._paused:
            position=self.backend._position()
            self.backend._stop_audio()
            self.backend._start_audio(position)

    def flat_eq(self):
        from PySide6.QtCore import QSignalBlocker
        for key in ("bass","mid","treble"):
            with QSignalBlocker(self.sliders[key]):
                self.sliders[key].setValue(0)
            self.value_labels[key].setText("+0 dB")
        self.apply_eq()

    def stop_playback(self):
        self.backend.stop()

    def cleanup(self):
        self.ticker.stop()
        self.backend.cleanup()
