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
        self.vu.setFixedHeight(63)
        self.vu.setToolTip("Niveles L/R de la toma real, antes de aplicar los tonos de preescucha")
        body.addWidget(self.vu)
        controls=QHBoxLayout()
        self.sliders={}
        for name,desc,low,high,initial in (
            ("bass","Graves",-12,12,0),
            ("mid","Medios",-12,12,0),
            ("treble","Agudos",-12,12,0),
            ("volume","Volumen",0,100,85)
        ):
            section=QVBoxLayout();section.setSpacing(3)
            head=QHBoxLayout()
            head.addWidget(QLabel(desc,self))
            value=QLabel((f"{initial:+d} dB" if name!="volume" else f"{initial}%"),self)
            value.setMinimumWidth(44)
            head.addWidget(value)
            section.addLayout(head)
            slider=QSlider(Qt.Horizontal,self)
            slider.setFixedHeight(22)
            slider.setRange(low,high)
            slider.setValue(initial)
            slider.setToolTip(desc+" durante la reproducción (no modifica el archivo)")
            slider.valueChanged.connect(lambda n,k=name,v=value:
                v.setText(f"{n:+d} dB" if k!="volume" else f"{n}%"))
            if name=="volume":
                slider.valueChanged.connect(self.backend.volume.setValue)
            else:
                slider.sliderReleased.connect(self.apply_eq)
            section.addWidget(slider)
            controls.addLayout(section,1)
            self.sliders[name]=slider
        body.addLayout(controls)
        bottom=QHBoxLayout()
        self.eq_enabled=QCheckBox("EQ activo",self)
        self.eq_enabled.setChecked(True)
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
        self.state=QLabel("No se modifica el original",self)
        bottom.addWidget(self.state,1)
        body.addLayout(bottom)
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

    def apply_eq(self,*_):
        if self.eq_enabled.isChecked():
            self.backend.set_preview_eq(*(self.sliders[k].value()
                                          for k in ("bass","mid","treble")))
        else:self.backend.set_preview_eq(0,0,0)

    def change_channels(self,*_):
        # FFplay necesita reabrir la señal para cambiar la mezcla de canales.
        if self.backend._play_process is not None and not self.backend._paused:
            position=self.backend._position()
            self.backend._stop_audio()
            self.backend._start_audio(position)

    def flat_eq(self):
        for key in ("bass","mid","treble"):
            self.sliders[key].setValue(0)
        self.apply_eq()

    def stop_playback(self):
        self.backend.stop()

    def cleanup(self):
        self.ticker.stop()
        self.backend.cleanup()
