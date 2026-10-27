"""Consola de batería de seis canales con diseño adaptable.

Los picos visuales se calculan SOLO a partir de muestras reales de la pista
que se está preescuchando, no son VU decorativos ni lecturas de hardware.
"""
from pathlib import Path
import math
from PySide6.QtCore import Qt,QTimer,QRectF,QPointF
from PySide6.QtGui import QColor,QPen,QPainter,QLinearGradient
from PySide6.QtWidgets import (
    QFrame,QWidget,QLabel,QPushButton,QSlider,QDial,
    QVBoxLayout,QHBoxLayout,QSizePolicy
)
from studio_home import WaveCanvas
from studio_slider_spin import StudioSliderSpin

COLORS={
    "Bombo":"#31b9ff","Caja":"#ff9275","Toms":"#cba4ff",
    "Charles":"#f6d06e","Ride":"#6be2c4","Crash":"#f59bcf",
}

class PanDial(QDial):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setRange(-100,100)
        self.setValue(0)
        self.setNotchesVisible(False)
        self.setWrapping(False)
        self.setFixedSize(44,44)
        self.setToolTip("Panorama estéreo: izquierda –100, centro 0, derecha +100. Doble clic: centrar.")

    def mouseDoubleClickEvent(self,event):
        self.setValue(0)
        event.accept()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing,True)
        painter.setPen(QPen(QColor("#2f789d") if self.isEnabled() else QColor("#3b5360"),4))
        painter.drawArc(QRectF(6,6,32,32),210*16,300*16)
        painter.setPen(QPen(QColor("#061827"),1))
        painter.setBrush(QColor("#183b53") if self.isEnabled() else QColor("#1a2a35"))
        painter.drawEllipse(QRectF(9,9,26,26))
        angle=math.radians(240-(self.value()+100)*300/200)
        cx,cy=22.,22.
        painter.setPen(QPen(QColor("#6be3ff") if self.isEnabled() else QColor("#587184"),3))
        painter.drawLine(QPointF(cx,cy),QPointF(cx+10*math.cos(angle),cy-10*math.sin(angle)))
        painter.end()

class AudioLevelMeter(QWidget):
    """Pico decodificado del archivo que se escucha; cero con transporte parado."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.db=-72.
        self.setMinimumWidth(25)
        self.setMaximumWidth(30)
        self.setMinimumHeight(85)
        self.setToolTip("Nivel estimado del archivo en preescucha, no una lectura directa del hardware.")

    def set_db(self,value):
        value=max(-72.,min(6.,float(value)))
        if abs(value-self.db)>.6:
            self.db=value
            self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing,False)
        width=self.width()
        height=self.height()
        left=5
        top=9
        barwidth=max(8,width-12)
        usable=max(15,height-18)
        painter.fillRect(QRectF(left,top,barwidth,usable),QColor("#081a2b"))
        grad=QLinearGradient(0,height-9,0,top)
        grad.setColorAt(0.,QColor("#21b9b4"))
        grad.setColorAt(.68,QColor("#6ce87b"))
        grad.setColorAt(.87,QColor("#f5ce61"))
        grad.setColorAt(1.,QColor("#f16f77"))
        fraction=max(0.,min(1.,(self.db+60.)/66.))
        filled=usable*fraction
        if filled>0:
            painter.fillRect(QRectF(left,top+usable-filled,barwidth,filled),grad)
        painter.setPen(QPen(QColor("#1b3951"),1))
        for i in range(1,15):
            y=top+i*usable/15
            painter.drawLine(left,y,left+barwidth,y)
        painter.setPen(QPen(QColor("#3b718d"),1))
        painter.drawRect(QRectF(left,top,barwidth,usable))
        painter.end()

class ConsoleStrip(QFrame):
    def __init__(self,part,studio):
        super().__init__(studio)
        self.studio=studio
        self.part=part
        self.path=None
        self.setObjectName("drumConsoleStrip")
        self.setProperty("activeChannel",False)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.setMinimumWidth(118)
        self.setFixedHeight(255)
        self._create()

    def _create(self):
        lay=QVBoxLayout(self)
        lay.setContentsMargins(8,6,8,6)
        lay.setSpacing(3)
        self.select=QPushButton(self.part)
        self.select.setObjectName("drumConsoleSelect")
        self.select.setToolTip("Selecciona el canal para ver detalle y editar.")
        self.select.setStyleSheet(
            "QPushButton {background:transparent;border:0;border-bottom:2px solid "+
            COLORS[self.part]+";font-weight:800;color:"+COLORS[self.part]+
            ";min-height:21px;} QPushButton:hover {background:#093a92;}")
        self.select.clicked.connect(lambda:self.studio.select_channel(self.part))
        lay.addWidget(self.select)
        self.wave=WaveCanvas(small=True,parent=self)
        self.wave.setFixedHeight(34)
        self.wave.wave_color=COLORS[self.part]
        self.wave.clicked.connect(lambda _:self.studio.select_channel(self.part))
        lay.addWidget(self.wave)
        self.empty_wave=QLabel("○  SIN PISTA")
        self.empty_wave.setAlignment(Qt.AlignCenter)
        self.empty_wave.setStyleSheet(
            "color:#a3e4f0;background:#041b43;"
            "border:1px dashed #29aaf3;border-radius:4px;")
        self.empty_wave.setFixedHeight(34)
        lay.addWidget(self.empty_wave)
        main=QHBoxLayout()
        main.setSpacing(0)
        self.fader=QSlider(Qt.Vertical,self)
        self.fader.setRange(-36,12)
        self.fader.setValue(0)
        self.fader.setTickInterval(6)
        self.fader.setTickPosition(QSlider.TicksBothSides)
        self.fader.setMinimumHeight(82)
        self.fader.setMaximumHeight(108)
        self.fader.setToolTip("Nivel del canal en dB. 0 dB es ganancia unitaria.")
        self.fader.valueChanged.connect(lambda value:self.studio.set_state(self.part,"gain",value))
        main.addWidget(self.fader,1,Qt.AlignHCenter)
        self.meter=AudioLevelMeter(self)
        self.meter.setMaximumHeight(133)
        main.addWidget(self.meter,0,Qt.AlignRight)
        lay.addLayout(main,1)
        self.gain_value=QLabel("0 dB")
        self.gain_value.setAlignment(Qt.AlignCenter)
        self.gain_value.setStyleSheet("color:#e0f8ff;font-weight:800;font-size:12px;")
        lay.addWidget(self.gain_value)
        pan=QHBoxLayout()
        pan.setSpacing(2)
        self.knob=PanDial(self)
        self.knob.valueChanged.connect(lambda value:self.studio.set_state(self.part,"pan",value))
        pan.addWidget(self.knob,0,Qt.AlignCenter)
        right=QVBoxLayout()
        pan_label=QLabel("PAN L/R")
        pan_label.setStyleSheet("font-size:9px;color:#e0f8ff;")
        right.addWidget(pan_label)
        self.pan_value=QLabel("C")
        self.pan_value.setStyleSheet("color:#85f0ff;font-weight:bold;font-size:12px;")
        right.addWidget(self.pan_value)
        pan.addLayout(right)
        lay.addLayout(pan)
        actions=QHBoxLayout()
        actions.setSpacing(3)
        self.mute=QPushButton("M")
        self.mute.setCheckable(True)
        self.mute.setToolTip("Silenciar canal al renderizar la mezcla")
        self.mute.toggled.connect(lambda value:self.studio.set_state(self.part,"mute",value))
        self.solo=QPushButton("S")
        self.solo.setCheckable(True)
        self.solo.setToolTip("Solo: renderiza exclusivamente los canales marcados")
        self.solo.toggled.connect(lambda value:self.studio.set_state(self.part,"solo",value))
        self.play=QPushButton("▶")
        self.play.setToolTip("Escuchar pista real de "+self.part)
        self.play.clicked.connect(lambda:self.studio.listen(self.part))
        for button in (self.mute,self.solo,self.play):
            button.setFixedHeight(24)
            button.setMinimumWidth(25)
            button.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            actions.addWidget(button,1)
        lay.addLayout(actions)
        self.controls=(self.fader,self.knob,self.mute,self.solo,self.play)
        self.update_state({"gain":0,"pan":0,"mute":False,"solo":False},None)

    def update_state(self,state,path):
        actual=Path(path).resolve() if path and Path(path).is_file() else None
        if self.path!=actual:
            self.path=actual
            self.wave.set_file(actual)
        ready=actual is not None
        self.wave.setVisible(ready)
        self.empty_wave.setVisible(not ready)
        for control in self.controls:control.setEnabled(ready)
        value=int(state["gain"])
        if self.fader.value()!=value:
            f=self.fader.blockSignals(True);self.fader.setValue(value);self.fader.blockSignals(f)
        self.gain_value.setText(f"{value:+d} dB" if value else "0 dB")
        if self.knob.value()!=state["pan"]:
            f=self.knob.blockSignals(True);self.knob.setValue(int(state["pan"]));self.knob.blockSignals(f)
        pan=int(state["pan"])
        self.pan_value.setText("C" if pan==0 else f"L{abs(pan)}" if pan<0 else f"R{pan}")
        for button,key,color in (
            (self.mute,"mute","#ad544b"),(self.solo,"solo","#126ea0")):
            if button.isChecked()!=bool(state[key]):
                old=button.blockSignals(True)
                button.setChecked(bool(state[key]))
                button.blockSignals(old)
            button.setStyleSheet(
                f"background:{color};color:white;font-weight:bold;" if button.isChecked()
                else "")
        if not ready:self.meter.set_db(-72.)

    def set_selected(self,selected):
        self.setProperty("activeChannel",bool(selected))
        self.setStyleSheet(
            "QFrame#drumConsoleStrip {background:#052257;"
            "border:2px solid #58d6f6;border-radius:7px;}"
            if selected else
            "QFrame#drumConsoleStrip {background:#041d49;"
            "border:1px solid #2bb1fc;border-radius:7px;}")

    def update_audio_peak(self,playing,path,position_ms):
        if not playing or not self.path or path!=self.path or not self.wave.data:
            self.meter.set_db(-72.)
            return
        points=self.wave.data
        duration=max(1.,self.wave.duration_seconds)
        i=int((position_ms/1000)/duration*len(points))
        lo=max(0,i-9);hi=min(len(points),i+10)
        amplitude=max(points[lo:hi],default=0.)
        amplitude*=10**(self.studio.channels[self.part]["gain"]/20)
        self.meter.set_db(20*math.log10(max(amplitude,0.0001)))

class ChannelInspector(QFrame):
    """Inspector inferior horizontal, con proporciones equivalentes a Inicio."""
    def __init__(self,studio):
        super().__init__(studio)
        self.studio=studio
        self.setObjectName("drumInspector")
        self.setStyleSheet("QFrame#drumInspector {background:#041d49;"
                           "border:1px solid #2bb1fc;border-radius:6px;}")
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.setFixedHeight(137)
        main=QHBoxLayout(self)
        main.setContentsMargins(10,7,10,7)
        main.setSpacing(11)
        identity=QVBoxLayout()
        identity.setSpacing(3)
        label=QLabel("CANAL SELECCIONADO")
        label.setStyleSheet("font-size:10px;font-weight:800;color:#85f0ff;")
        identity.addWidget(label)
        self.name=QLabel("BOMBO")
        self.name.setStyleSheet("font-size:16px;font-weight:bold;color:#85f0ff;")
        identity.addWidget(self.name)
        self.status=QLabel("Sin pista cargada")
        self.status.setStyleSheet("color:#e0f8ff;font-size:11px;")
        self.status.setWordWrap(True)
        self.status.setMaximumHeight(32)
        identity.addWidget(self.status)
        self.gain=QLabel("Nivel: 0 dB")
        self.pan=QLabel("Pan: C")
        for text in (self.gain,self.pan):
            text.setStyleSheet("color:#e0f8ff;font-size:11px;")
        identity.addWidget(self.gain)
        identity.addWidget(self.pan)
        identity.addStretch()
        main.addLayout(identity,1)
        waves=QVBoxLayout()
        waves.setSpacing(4)
        heading=QLabel("FORMA DE ONDA · ORIGINAL")
        heading.setStyleSheet("color:#85f0ff;font-size:10px;font-weight:bold;")
        waves.addWidget(heading)
        self.wave=WaveCanvas(small=True,parent=self)
        self.wave.setMinimumWidth(150)
        self.wave.setFixedHeight(54)
        waves.addWidget(self.wave)
        self.empty_wave=QLabel("○  Sin audio cargado")
        self.empty_wave.setAlignment(Qt.AlignCenter)
        self.empty_wave.setStyleSheet(
            "color:#a3e4f0;background:#04193f;"
            "border:1px dashed #2aacf5;border-radius:4px;")
        self.empty_wave.setFixedHeight(54)
        waves.addWidget(self.empty_wave)
        self.duration=QLabel("Duración: —")
        self.duration.setStyleSheet("color:#e0f8ff;font-size:10px;")
        waves.addWidget(self.duration)
        waves.addStretch()
        main.addLayout(waves,2)
        eq=QVBoxLayout()
        eq.setSpacing(2)
        eq_title=QLabel("EQ DEL CANAL · EXPORTACIÓN")
        eq_title.setStyleSheet("color:#85f0ff;font-size:10px;font-weight:800;")
        eq.addWidget(eq_title)
        self.equalizers={}
        for key,name in (("eq_low","Graves"),("eq_mid","Medios"),
                         ("eq_high","Agudos")):
            line=QHBoxLayout()
            line.setSpacing(3)
            name_label=QLabel(name)
            name_label.setFixedWidth(40)
            name_label.setStyleSheet("color:#e0f8ff;font-size:11px;")
            line.addWidget(name_label)
            control=StudioSliderSpin(-12,12,0,"dB",self,width=180)
            control.setToolTip("EQ real aplicada al exportar la mezcla, sin modificar el original.")
            control.valueChanged.connect(
                lambda value,k=key:self.studio.set_state(
                    self.studio.selected_part,k,value))
            self.equalizers[key]=control
            line.addWidget(control)
            eq.addLayout(line)
        main.addLayout(eq,0)
        actions=QVBoxLayout()
        actions.setSpacing(5)
        self.listen_btn=QPushButton("▶ Escuchar")
        self.listen_btn.clicked.connect(
            lambda:self.studio.listen(self.studio.selected_part))
        self.edit_btn=QPushButton("✎ Editar pista")
        self.edit_btn.clicked.connect(self.studio.edit_selected_channel)
        self.reset_btn=QPushButton("↺ Restablecer")
        self.reset_btn.clicked.connect(self.studio.reset_selected_channel)
        for button in (self.listen_btn,self.edit_btn,self.reset_btn):
            button.setMinimumWidth(108)
            button.setMaximumWidth(150)
            button.setFixedHeight(27)
            actions.addWidget(button)
        actions.addStretch()
        main.addLayout(actions,0)
        self.setToolTip("Picos calculados desde audio real, no medidores de hardware.")
        self.update_selected("Bombo",None,
            {"gain":0,"pan":0,"mute":False,"solo":False})

    def update_selected(self,part,path,state):
        self.name.setText(part.upper())
        self.name.setStyleSheet(
            "font-size:16px;font-weight:800;color:"+COLORS[part]+";")
        file=Path(path).resolve() if path and Path(path).is_file() else None
        self.status.setText(file.name if file else "Sin pista cargada")
        self.status.setToolTip(str(file) if file else "")
        if self.wave.source!=file:
            self.wave.set_file(file)
        ready=file is not None
        self.wave.setVisible(ready)
        self.empty_wave.setVisible(not ready)
        for key,control in self.equalizers.items():
            control.setEnabled(ready)
            value=int(state.get(key,0))
            if control.value()!=value:
                blocked=control.blockSignals(True)
                control.setValue(value)
                control.blockSignals(blocked)
        for control in (self.listen_btn,self.edit_btn,self.reset_btn):
            control.setEnabled(ready)
        gain=int(state["gain"])
        pan=int(state["pan"])
        self.gain.setText(f"Nivel: {gain:+d} dB")
        self.pan.setText("Pan: C" if pan==0
                         else f"Pan: {'L' if pan<0 else 'R'}{abs(pan)}")
        if ready:
            self.duration.setText(
                f"Duración: {self.wave.duration_seconds:.1f} s"
                if self.wave.duration_seconds else "Analizando onda…")
        else:
            self.duration.setText("Duración: —")
