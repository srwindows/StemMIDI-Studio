"""Original interactive 8-band Channel EQ editor for StemMIDI Studio."""
from __future__ import annotations
import math
import numpy as np
from PySide6.QtCore import Qt,QPointF,QTimer,QSignalBlocker,QRectF
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath,QBrush,QFont
from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QDoubleSpinBox,QComboBox,QCheckBox,QFrame,QSlider
)
from stemmidi_channel_eq import ChannelEQ,TYPES,BAND_COLORS,MODES

class EQGraph(QWidget):
    def __init__(self,effect,parent=None):
        super().__init__(parent)
        self.effect=effect
        self.selected=3
        self.on_select=None
        self.dragged=False
        self.setMinimumSize(420,205)
        self.setMouseTracking(True)
        self.setToolTip("Arrastra un punto de color: horizontal = Hz, vertical = dB; doble clic activa o desactiva.")
        self.frequencies=np.geomspace(20,20000,400)

    def px(self,hz):
        return 30.+math.log10(max(20.,min(20000.,float(hz)))/20)/3*max(1,self.width()-52)

    def hz(self,x):
        return max(20.,min(20000.,20.*10**(3*(x-30)/max(1,self.width()-52))))

    def py(self,gain):
        h=max(1,self.height()-36)
        return 15+(24.-float(gain))/48*h

    def gain(self,y):
        return max(-24.,min(24.,24.-(y-15)/max(1,self.height()-36)*48.))

    def position(self,i):
        band=self.effect.bands[i]
        return QPointF(self.px(band["hz"]),self.py(band["gain"] if i not in (0,7) else 0.))

    def _closest(self,pos):
        distances=[(self.position(i)-pos).manhattanLength() for i in range(8)]
        index=int(np.argmin(distances))
        return index if distances[index]<=22 else -1

    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        hit=self._closest(event.position())
        if hit<0:return
        self.selected=hit;self.dragged=True
        if self.on_select:self.on_select(hit)
        self._drag(event.position())

    def mouseMoveEvent(self,event):
        if self.dragged:self._drag(event.position())

    def mouseReleaseEvent(self,event):
        self.dragged=False

    def mouseDoubleClickEvent(self,event):
        hit=self._closest(event.position())
        if hit<0:return
        self.effect.set_band(hit,enabled=not self.effect.bands[hit]["enabled"])
        if self.on_select:self.on_select(hit)
        self.update()

    def _drag(self,position):
        i=self.selected;band=self.effect.bands[i]
        changes={"hz":self.hz(position.x())}
        if i not in (0,7):changes["gain"]=self.gain(position.y())
        self.effect.set_band(i,**changes)
        if self.on_select:self.on_select(i)
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            w,h=self.width(),self.height()
            p.fillRect(self.rect(),QColor("#081625"))
            p.setPen(QPen(QColor("#244051"),1))
            for f in (20,50,100,200,500,1000,2000,5000,10000,20000):
                x=self.px(f)
                p.drawLine(QPointF(x,13),QPointF(x,h-22))
                p.setPen(QColor("#8baec1"))
                p.setFont(QFont("Arial",8))
                p.drawText(QPointF(x-13,h-5),str(f//1000)+"k" if f>=1000 else str(f))
                p.setPen(QPen(QColor("#244051"),1))
            for gain in (-24,-12,0,12,24):
                y=self.py(gain)
                p.setPen(QPen(QColor("#3c5866") if gain==0 else QColor("#233745"),1))
                p.drawLine(QPointF(30,y),QPointF(w-18,y))
                p.setPen(QColor("#a4baca"))
                p.drawText(2,int(y)+4,f"{gain:+d}")
            if self.effect.analyzer!="Off":
                frequencies,db=self.effect.spectrum()
                mask=(frequencies>=20)&(frequencies<=20000)
                frequencies=frequencies[mask];db=db[mask]
                if len(db)>1:
                    path=QPainterPath()
                    for j,(frequency,value) in enumerate(zip(frequencies,db)):
                        x=self.px(frequency)
                        y=14+(1-min(1,max(0,(value+90)/100)))*(h-36)
                        if j==0:path.moveTo(x,y)
                        else:path.lineTo(x,y)
                    p.setPen(QPen(QColor("#357c9b"),1))
                    p.drawPath(path)
            response=np.clip(self.effect.response_db(self.frequencies),-24.,24.)
            path=QPainterPath()
            for j,(freq,value) in enumerate(zip(self.frequencies,response)):
                x=self.px(freq);y=self.py(value)
                if j==0:path.moveTo(x,y)
                else:path.lineTo(x,y)
            p.setPen(QPen(QColor("#d4f5fb"),2.2))
            p.drawPath(path)
            for i,band in enumerate(self.effect.bands):
                point=self.position(i)
                color=QColor(BAND_COLORS[i])
                if not band["enabled"]:color.setAlpha(85)
                p.setPen(QPen(QColor("#f0ffff") if i==self.selected else QColor("#101d29"),2))
                p.setBrush(QBrush(color))
                radius=7 if i==self.selected else 5
                p.drawEllipse(point,radius,radius)
        finally:p.end()


class ChannelEQControls(QWidget):
    """Native 8-band channel EQ with interactive curve and spectrum."""
    def __init__(self,effect,parent=None):
        super().__init__(parent)
        self.effect=effect
        self.setMinimumWidth(470)
        self.setStyleSheet("""
            QWidget{background:#0c2030;color:#d7f3fc}
            QDoubleSpinBox,QComboBox{background:#183951;color:#f2fdff;
                border:1px solid #437086;padding:2px;border-radius:4px}
            QPushButton{background:#19405c;color:#dff7fc;border:1px solid #4e7e92;
                border-radius:4px;padding:4px}
            QPushButton:checked{background:#176f72;border:1px solid #63e6db}
            QCheckBox{color:#d0edf8}
        """)
        root=QVBoxLayout(self)
        root.setContentsMargins(9,8,9,8);root.setSpacing(5)
        top=QHBoxLayout()
        title=QLabel("CHANNEL EQ  ·  8 BANDAS",self)
        title.setStyleSheet("font-size:14px;font-weight:bold;color:#e3faff")
        top.addWidget(title);top.addStretch()
        self.mode=QComboBox(self);self.mode.addItems(MODES)
        self.mode.setCurrentIndex(self.effect.mode)
        self.mode.currentIndexChanged.connect(self.effect.set_mode)
        top.addWidget(self.mode)
        root.addLayout(top)
        self.graph=EQGraph(effect,self)
        self.graph.on_select=self.select_band
        root.addWidget(self.graph,1)
        buttons=QHBoxLayout();buttons.setSpacing(3)
        self.band_buttons=[]
        for i,color in enumerate(BAND_COLORS):
            button=QPushButton(str(i+1),self)
            button.setCheckable(True)
            button.setToolTip(f"Banda {i+1}: {TYPES[i]}")
            button.setStyleSheet(f"QPushButton{{color:{color};font-weight:bold;border:1px solid {color};"
                "border-radius:4px;padding:4px}"
                f"QPushButton:checked{{background:{color};color:#071624}}")
            button.clicked.connect(lambda checked=False,j=i:self.select_band(j))
            buttons.addWidget(button,1)
            self.band_buttons.append(button)
        root.addLayout(buttons)
        grid=QGridLayout();grid.setHorizontalSpacing(5);grid.setVerticalSpacing(3)
        self.enabled=QCheckBox("Activado",self);self.enabled.toggled.connect(self._edit)
        grid.addWidget(self.enabled,0,0)
        self.freq=QDoubleSpinBox(self);self.freq.setRange(20,20000)
        self.freq.setDecimals(1);self.freq.setSuffix(" Hz")
        self.freq.setSingleStep(10);self.freq.valueChanged.connect(self._edit)
        self.gain=QDoubleSpinBox(self);self.gain.setRange(-24,24)
        self.gain.setDecimals(1);self.gain.setSuffix(" dB")
        self.gain.valueChanged.connect(self._edit)
        self.q=QDoubleSpinBox(self);self.q.setRange(.1,100.)
        self.q.setDecimals(2);self.q.setSingleStep(.05);self.q.valueChanged.connect(self._edit)
        self.slope=QComboBox(self)
        self.slope.addItems(["6 dB/Oct","12 dB/Oct","18 dB/Oct",
                             "24 dB/Oct","36 dB/Oct","48 dB/Oct"])
        self.slopes=(6,12,18,24,36,48)
        self.slope.currentIndexChanged.connect(self._edit)
        for col,(label,widget) in enumerate((("Frecuencia",self.freq),("Ganancia",self.gain),
                                               ("Q",self.q),("Pendiente",self.slope))):
            grid.addWidget(QLabel(label,self),1,col)
            grid.addWidget(widget,2,col)
        root.addLayout(grid)
        footer=QHBoxLayout()
        footer.addWidget(QLabel("Analizador:",self))
        self.analyzer=QComboBox(self);self.analyzer.addItems(["Off","Pre","Post"])
        self.analyzer.currentTextChanged.connect(self._analyzer_changed)
        footer.addWidget(self.analyzer)
        self.resolution=QComboBox(self);self.resolution.addItems(["2048","4096","8192"])
        self.resolution.currentTextChanged.connect(self._resolution_changed)
        footer.addWidget(self.resolution)
        self.qcouple=QCheckBox("Q-Couple",self)
        self.qcouple.setToolTip("Ajusta Q al cambiar la ganancia de las bandas paramétricas")
        self.qcouple.toggled.connect(lambda v:setattr(self.effect,"q_couple",v))
        footer.addWidget(self.qcouple)
        self.qstrength=QComboBox(self)
        self.qstrength.addItems(["Proportional","Light","Medium","Strong","Asymmetric"])
        self.qstrength.setToolTip("Intensidad del acoplamiento Q/ganancia")
        self.qstrength.currentTextChanged.connect(
            lambda value:setattr(self.effect,"q_couple_strength",value))
        footer.addWidget(self.qstrength)
        self.hq=QCheckBox("HQ 2×",self)
        self.hq.setToolTip("Sobremuestreo interno 2× del filtro nativo")
        self.hq.toggled.connect(self.effect.set_hq)
        footer.addWidget(self.hq)
        footer.addStretch()
        footer.addWidget(QLabel("Output",self))
        self.output=QDoubleSpinBox(self);self.output.setRange(-24,24)
        self.output.setSuffix(" dB");self.output.setDecimals(1)
        self.output.valueChanged.connect(self.effect.set_output_gain)
        footer.addWidget(self.output)
        root.addLayout(footer)
        spectrum_row=QHBoxLayout()
        spectrum_row.addWidget(QLabel("FFT:",self))
        self.analyzer_mode=QComboBox(self)
        self.analyzer_mode.addItems(["Peak","RMS"])
        self.analyzer_mode.currentTextChanged.connect(
            lambda value:setattr(self.effect,"analyzer_mode",value))
        spectrum_row.addWidget(self.analyzer_mode)
        spectrum_row.addWidget(QLabel("Decaimiento:",self))
        self.decay=QDoubleSpinBox(self)
        self.decay.setRange(0.,90.)
        self.decay.setDecimals(0)
        self.decay.setSuffix(" dB/s")
        self.decay.setValue(self.effect.analyzer_decay_db_s)
        self.decay.valueChanged.connect(
            lambda value:setattr(self.effect,"analyzer_decay_db_s",value))
        spectrum_row.addWidget(self.decay)
        spectrum_row.addStretch()
        root.addLayout(spectrum_row)
        self._updating=False
        self.select_band(3)
        self.analyzer.setCurrentText(self.effect.analyzer)
        self.resolution.setCurrentText(str(self.effect.resolution))
        self.qcouple.setChecked(self.effect.q_couple)
        self.qstrength.setCurrentText(self.effect.q_couple_strength)
        self.hq.setChecked(self.effect.hq)
        self.analyzer_mode.setCurrentText(self.effect.analyzer_mode)
        self.output.setValue(self.effect.output_gain_db)
        self.timer=QTimer(self)
        self.timer.setInterval(110)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()

    def _analyzer_changed(self,text):
        self.effect.analyzer=text
        self.graph.update()

    def _resolution_changed(self,value):
        self.effect.resolution=int(value)

    def select_band(self,index):
        self.graph.selected=index
        band=self.effect.bands[index]
        self._updating=True
        try:
            with QSignalBlocker(self.enabled):self.enabled.setChecked(band["enabled"])
            with QSignalBlocker(self.freq):self.freq.setValue(band["hz"])
            with QSignalBlocker(self.gain):self.gain.setValue(band["gain"])
            with QSignalBlocker(self.q):self.q.setValue(band["q"])
            with QSignalBlocker(self.slope):
                self.slope.setCurrentIndex(
                    self.slopes.index(band["slope"])
                    if band["slope"] in self.slopes else 1)
            self.gain.setEnabled(index not in (0,7))
            self.slope.setEnabled(index in (0,7))
            for i,button in enumerate(self.band_buttons):
                with QSignalBlocker(button):button.setChecked(i==index)
        finally:self._updating=False
        self.graph.update()

    def _edit(self,*args):
        if self._updating:return
        index=self.graph.selected
        old=self.effect.bands[index]
        gain=self.gain.value()
        q=self.q.value()
        if self.effect.q_couple and 2<=index<=5 and abs(gain-old["gain"])>.01:
            factors={"Proportional":.75,"Light":.35,"Medium":.65,
                     "Strong":1.,"Asymmetric":1.25 if gain<0 else .5}
            strength=factors[self.effect.q_couple_strength]
            scale=(1+abs(gain)/24)/(1+abs(old["gain"])/24)
            q=max(.1,min(100.,old["q"]*scale**strength))
        self.effect.set_band(index,enabled=self.enabled.isChecked(),hz=self.freq.value(),
               gain=gain,q=q,slope=self.slopes[self.slope.currentIndex()])
        self.select_band(index)

    def _refresh(self):
        if self.isVisible():self.graph.update()
