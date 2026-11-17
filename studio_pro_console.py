"""Consola profesional real de StemMIDI Studio.

16 tiras compactas en matriz, medidores L/R VERTICALES en cada tira, 4
encoders, EQ, mute/solo/armado, envíos reales, 16 buses y ruteo matricial.
Inspiración visual de consolas de estudio; dibujo original con QPainter.
Reutiliza el catálogo y la selección del mezclador del proyecto.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QPoint, QRectF, QSize, QTimer, Signal, QSignalBlocker, QEvent
from PySide6.QtGui import (
    QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QFont,
    QPolygonF, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QDial, QSlider, QPushButton, QCheckBox,
    QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QSizePolicy, QListWidgetItem, QListWidget, QMenu, QFileDialog
)
from project_mixer_expanded import (
    ProjectMixerView, ProjectMixerTransport, ContrastFileCheckboxDelegate,
    AUDIO, MIDI, FAMILIES, label
)
from console_audio_engine import DEFAULT_CHANNEL, ProConsoleEngine, ffmpeg_executable
from studio_home import StudioFader
from studio_vu_unified import Ballistics

COLORS=("#4ecbfa","#f17d72","#ffd462","#80dba2",
        "#a6ddff","#69b5e1","#bda2fa","#50d6c0",
        "#e5b66d","#7eacff","#d58be5","#a3e5e8",
        "#d1b18b","#b0d78c","#f5a6bf","#7dd6e2")
SKIN="""
QWidget#proConsoleRoot{background:#061421;color:#d3f2ff;}
QFrame#proRack,QFrame#proSidebar,QFrame#proChannels{
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #1c3448,stop:.055 #102536,stop:.75 #0b1b29,stop:1 #07121d);
    border:1px solid #3b6174;border-top:1px solid #6fa0b9;
    border-radius:4px;
}
QFrame#proStrip{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #071521,stop:.12 #233849,stop:.3 #122536,
        stop:.74 #0d1e30,stop:.91 #2a3949,stop:1 #081622);
    border:1px solid #39566e;border-top:2px solid #537487;
    border-radius:2px;
}
QFrame#proStrip[active="true"]{border-top:2px solid #48e9fa;}
QLabel{background:transparent;color:#d4f3ff;}
QLabel#proSection{color:#a7edff;font-weight:800;font-size:10px;}
QPushButton{
    color:#d9f5ff;font-weight:700;font-size:10px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #37566c,stop:.18 #1e3b54,stop:.54 #132b40,
        stop:.57 #092136,stop:1 #061422);
    border:1px solid #47748c;border-top:1px solid #93aabd;
    border-bottom:2px solid #020d17;border-radius:3px;
    padding:2px 4px;min-height:18px;
}
QPushButton:hover{border-color:#7be6fa;background:#215479;}
QPushButton:pressed,QPushButton:checked{
    background:#0b5887;color:#ffffff;border-color:#6ad9ff;}
QPushButton#muteButton:checked{background:#b54042;border-color:#f78d85;}
QPushButton#soloButton:checked{background:#a97814;border-color:#ffdc79;}
QPushButton#armButton:checked{background:#bf303b;border-color:#ff818a;}
QPushButton#recButton:checked{background:#c92f3e;border-color:#ffafaa;}
QPushButton:disabled{color:#6f8997;border-color:#2e4556;background:#152635;}
QComboBox{
    color:#e8faff;background:#0b273b;border:1px solid #3a7b9c;
    border-radius:3px;min-height:20px;padding:1px 15px 1px 4px;
    font-size:10px;}
QComboBox QAbstractItemView{background:#0b2437;color:#e4faff;
    selection-background-color:#12658d;}
QSlider::groove:horizontal{height:5px;background:#04101a;
    border:1px solid #315c71;border-radius:2px;}
QSlider::sub-page:horizontal{background:#32d9e1;border-radius:2px;}
QSlider::handle:horizontal{width:12px;margin:-5px 0;
    border:1px solid #f1ffff;border-radius:4px;background:#8cddff;}
QScrollArea{border:none;background:transparent;}
"""

def _txt(text,parent=None,sz=9,color="#d8f4ff",bold=False,center=False):
    w=QLabel(text,parent)
    w.setStyleSheet(f"color:{color};background:transparent;"
        f"font-size:{sz}px;font-weight:{800 if bold else 500};")
    if center:w.setAlignment(Qt.AlignCenter)
    return w

class GlassKnob(QDial):
    """Encoder de consola dibujado a mano: bisel, sombra, arco y LED."""
    def __init__(self,color="#43b9ea",parent=None):
        super().__init__(parent)
        self._color=QColor(color)
        self.setFixedSize(34,32)
        self.setWrapping(False)
        self.setNotchesVisible(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        cx=self.width()/2;cy=self.height()/2
        radius=min(self.width(),self.height())*.43
        p.setPen(QPen(QColor("#030a10"),2))
        p.setBrush(QColor("#051420"))
        p.drawEllipse(QPoint(int(cx),int(cy)),int(radius+2),int(radius+2))
        grad=QRadialGradient(cx-radius*.3,cy-radius*.55,radius*2)
        grad.setColorAt(0,QColor("#7391a0"))
        grad.setColorAt(.25,QColor("#354e60"))
        grad.setColorAt(.57,QColor("#152939"))
        grad.setColorAt(1,QColor("#050e19"))
        p.setPen(QPen(QColor("#7896aa"),.75))
        p.setBrush(grad);p.drawEllipse(QPoint(int(cx),int(cy)),int(radius),int(radius))
        p.setBrush(Qt.NoBrush)
        arc=QRectF(cx-radius-2,cy-radius-2,2*radius+4,2*radius+4)
        p.setPen(QPen(QColor("#152e40"),2.6))
        p.drawArc(arc,225*16,270*16)
        fraction=(self.value()-self.minimum())/max(1,(self.maximum()-self.minimum()))
        p.setPen(QPen(self._color,2.5,Qt.SolidLine,Qt.RoundCap))
        p.drawArc(arc,225*16,int(270*16*fraction))
        # 225° (min) -> -45° (max); forward clockwise on screen.
        angle=math.radians(225-270*fraction)
        x=cx+math.cos(angle)*radius*.65
        y=cy-math.sin(angle)*radius*.65
        p.setPen(QPen(QColor("#f4fbff"),2.1,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPoint(int(cx),int(cy)),QPoint(int(x),int(y)))
        p.end()

class StereoBar(QWidget):
    """VU vertical de dos canales y 30 segmentos dBFS, sin caja horizontal."""
    def __init__(self,parent=None,caption="",scale=True):
        super().__init__(parent)
        self.levels=Ballistics(2)
        self.caption=caption
        self.scale=scale
        self.setMinimumWidth(28)
        self.setMinimumHeight(90)
        self.setToolTip("Nivel real L/R · −60 a +6 dBFS · retención de pico")

    def set_peaks(self,left,right):
        self.levels.feed((max(0.,float(left)),max(0.,float(right))),
                         (max(0.,float(left)),max(0.,float(right))))
        self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing,False)
        h=self.height();w=self.width()
        top=8;bottom=h-7
        if self.caption:
            p.setPen(QColor("#e4f7ff"))
            p.setFont(QFont("Sans",7,QFont.Bold))
            p.drawText(QRectF(0,0,w,12),Qt.AlignCenter,self.caption)
            top+=10
        bars_left=15 if self.scale else 2
        gap=2;bar_w=max(4,(w-bars_left-3-gap)//2)
        p.setPen(QColor("#3d6e80"))
        p.setFont(QFont("Sans",6))
        span=bottom-top
        if self.scale:
            for db in (6,0,-12,-24,-36,-48,-60):
                y=top+(6-db)/66*span
                p.drawText(QRectF(0,y-5,13,11),Qt.AlignRight,str(db))
                p.setPen(QPen(QColor("#345062"),.5))
                p.drawLine(bars_left-1,int(y),w-2,int(y))
                p.setPen(QColor("#91aabb"))
        segs=28
        for c in range(2):
            x=bars_left+c*(bar_w+gap)
            amplitude=self.levels.shown[c]
            db=20*math.log10(max(amplitude,1.e-6))
            count=int(max(0,min(segs,round((db+60)/66*segs))))
            hold=self.levels.held[c]
            held_db=20*math.log10(max(hold,1.e-6))
            hold_idx=int(max(0,min(segs-1,round((held_db+60)/66*segs)-1)))
            for i in range(segs):
                y=bottom-(i+1)*span/segs
                y1=bottom-i*span/segs-1
                if i>=count:
                    color=QColor("#102b2d") if i<17 else QColor("#30271c")
                elif i>=25:color=QColor("#fb565c")
                elif i>=21:color=QColor("#ffcd4e")
                else:color=QColor("#19e18f") if i<18 else QColor("#b2ee54")
                p.fillRect(QRectF(x,y,bar_w,max(1.2,y1-y)),color)
            if hold>0.0001:
                hy=bottom-(hold_idx+1)*span/segs
                p.fillRect(QRectF(x,hy-2,bar_w,2),QColor("#f5fbff"))
        p.end()

class RouteMatrix(QWidget):
    """Matriz 16×16 REAL: seleccionar bus al que envía cada canal."""
    def __init__(self,console,parent=None):
        super().__init__(parent)
        self.console=console
        self.setMinimumSize(230,136)
        self.setMaximumWidth(320)
        self.setToolTip("Pulsa una celda para enrutar la pista de esa fila al bus elegido (1–16)")
        self.setCursor(Qt.PointingHandCursor)

    def _dims(self):
        return (30,19,(self.width()-34)/16,(self.height()-24)/16)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor("#081827"))
        x0,y0,cw,ch=self._dims()
        p.setFont(QFont("Sans",6,QFont.Bold))
        p.setPen(QColor("#8db3c3"))
        for col in range(16):
            p.drawText(QRectF(x0+col*cw,y0-14,cw,11),
                       Qt.AlignCenter,str(col+1))
        first=self.console.routing_page*16
        for row,strip in enumerate(self.console.visible_strips[first:first+16]):
            p.setPen(QColor("#b7cddc"))
            p.drawText(QRectF(0,y0+row*ch,25,ch),Qt.AlignRight,str(first+row+1))
            for col in range(16):
                rect=QRectF(x0+col*cw+.8,y0+row*ch+.7,
                             max(2,cw-1.5),max(2,ch-1.3))
                active=int(strip.controls.get("bus",1))==col+1
                p.fillRect(rect,QColor("#25e5bb") if active else
                           QColor("#203746") if (row+col)%2 else QColor("#273f4a"))
                if active:
                    p.setPen(QPen(QColor("#c2fff9"),.7));p.drawRect(rect)
            if row%4==3:
                p.setPen(QPen(QColor("#476b7a"),.5))
                y=y0+(row+1)*ch
                p.drawLine(QPoint(x0,int(y)),QPoint(self.width()-4,int(y)))
        p.end()

    def mousePressEvent(self,event):
        x0,y0,cw,ch=self._dims()
        px=event.position().x();py=event.position().y()
        if px>=x0 and py>=y0:
            col=int((px-x0)//cw);row=int((py-y0)//ch)
            absolute_row=self.console.routing_page*16+row
            if 0<=row<16 and absolute_row<len(self.console.visible_strips) and 0<=col<16:
                self.console.set_channel_param(
                    self.console.visible_strips[absolute_row].key,"bus",col+1)
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)

class RealWaveOverview(QWidget):
    """Forma de onda derivada del archivo auténtico, nunca simulada."""
    loaded=Signal(str,object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMinimumHeight(125)
        self.path=""
        self.waves=None
        self.position=0.
        self.seek=None
        self.loaded.connect(self._loaded)
        self.setToolTip("Audio real L/R · pulsa para desplazar la reproducción")

    def set_path(self,file):
        path=str(file) if file else ""
        if path==self.path:return
        self.path=path
        self.waves=None
        self.update()
        if not path or not Path(path).is_file():return
        def worker(candidate):
            # Priorizar la lectura nativa para WAV/FLAC: desde el USB,
            # lanzar FFmpeg por archivo podía tardar demasiado en cargar.
            # Cargar siempre PCM real; nunca dibujar ondas inventadas.
            try:
                suffix=Path(candidate).suffix.lower()
                if suffix in (".wav",".flac",".aif",".aiff",".ogg"):
                    import soundfile as sf
                    with sf.SoundFile(candidate) as f:
                        points=[]
                        total=min(len(f),round(f.samplerate*120))
                        step=max(256,round(total/500))
                        remaining=total
                        while remaining>0 and len(points)<520:
                            count=min(step,remaining)
                            frames=f.read(count,dtype="float32",always_2d=True)
                            if not len(frames):break
                            if frames.shape[1]==1:
                                peak=np.array([float(np.max(np.abs(frames[:,0])))]*2)
                            else:
                                peak=np.max(np.abs(frames[:,:2]),axis=0)
                            points.append(peak)
                            remaining-=len(frames)
                    if points:
                        self.loaded.emit(candidate,np.clip(np.asarray(points),0,1))
                        return
                command=[ffmpeg_executable(),"-nostdin","-v","error","-i",candidate,
                         "-t","120","-ar","2000","-ac","2","-f","f32le","pipe:1"]
                process=subprocess.run(command,stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,timeout=45)
                if process.returncode:
                    raise RuntimeError(process.stderr[-260:].decode("utf8","replace"))
                samples=np.frombuffer(process.stdout,dtype="<f4")
                if len(samples)<4:raise ValueError("Sin muestras de audio")
                samples=samples[:len(samples)//2*2].reshape(-1,2)
                size=max(1,math.ceil(len(samples)/500))
                usable=len(samples)//size*size
                if not usable:
                    raise ValueError("No hay muestras suficientes")
                aggregate=np.max(np.abs(samples[:usable].reshape(-1,size,2)),axis=1)
                self.loaded.emit(candidate,np.clip(aggregate,0,1))
            except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired):
                self.loaded.emit(candidate,None)
        threading.Thread(target=worker,args=(path,),daemon=True,
                         name="StemMIDI-Waveform-Overview").start()

    def _loaded(self,path,wave):
        if path!=self.path:return
        self.waves=wave
        self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor("#061928"))
        w=self.width();h=self.height()
        p.setPen(QPen(QColor("#2e5161"),.6))
        for j in range(9):
            x=int(j*w/8)
            p.drawLine(x,1,x,h-1)
        for j in range(1,4):
            y=int(j*h/4)
            p.drawLine(0,y,w,y)
        p.setFont(QFont("Sans",7))
        p.setPen(QColor("#9bbccd"))
        for i in range(9):
            p.drawText(int(i*w/8)+3,11,str(i*15)+"s")
        if self.waves is None:
            p.setPen(QColor("#8da9b6"))
            p.drawText(self.rect(),Qt.AlignCenter,
                       "Selecciona un archivo de audio para ver su forma de onda")
        else:
            array=self.waves
            n=len(array)
            if n:
                for channel,color in ((0,"#38eea3"),(1,"#f6ba52")):
                    cy=h*(.34 if channel==0 else .75)
                    amp=h*.18
                    p.setPen(QPen(QColor(color),1.))
                    stride=max(1,n//max(1,w))
                    for i in range(0,n,stride):
                        x=int(i*w/n)
                        magnitude=float(array[i:i+stride,channel].max())
                        y=magnitude*amp
                        p.drawLine(x,int(cy-y),x,int(cy+y))
        x=int(self.position*w)
        p.setPen(QPen(QColor("#f1faff"),1))
        p.drawLine(x,16,x,h)
        p.end()

    def mousePressEvent(self,event):
        fraction=max(0.,min(1.,event.position().x()/max(1,self.width())))
        if self.seek:self.seek(fraction)
        event.accept()

class ProChannelStrip(QFrame):
    """Una tira de consola estrecha, no siete faders XXL."""
    def __init__(self,console,key,source,name,color,index,parent=None):
        super().__init__(parent)
        self.console=console
        self.key=key
        self.source=source
        self.caption=name
        self._color=color
        self.controls={**DEFAULT_CHANNEL,**console.control_state.get(key,{})}
        self.setObjectName("proStrip")
        self.setProperty("active",source is not None)
        self.setMinimumWidth(58);self.setMaximumWidth(90)
        self.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        self.setToolTip(f"Canal {index+1}: {name} · {source or 'sin archivo'}")
        v=QVBoxLayout(self)
        v.setContentsMargins(2,2,2,3)
        v.setSpacing(1)
        number=_txt(str(index+1),self,8,"#a3bac7",center=True)
        number.setFixedHeight(10);v.addWidget(number)
        self.number_label=number
        title=_txt(name,self,9,"#f0fdff",True,True)
        title.setFixedHeight(18)
        title.setToolTip(source or name)
        v.addWidget(title)
        self.title_label=title
        self.dials={}
        for key_,color_,caption_,minimum,maximum,mult in (
          ("trim","#d05d5f","TRIM",-180,180,.1),
          ("high","#47cde2","AGUDOS",-120,120,.1),
          ("send","#61db84","REVERB",0,100,.01),
          ("pan","#5daafa","PAN",-100,100,.01)):
            row=QHBoxLayout()
            row.setContentsMargins(0,0,0,0);row.setSpacing(0)
            row.addStretch(1)
            dial=GlassKnob(color_,self)
            dial.setRange(minimum,maximum)
            dial.setValue(round(self.controls[key_]/mult))
            dial.setToolTip(f"{caption_} · canal {name}")
            dial.valueChanged.connect(
                lambda value,k=key_,m=mult:self.console.set_channel_param(
                    self.key,k,round(value*m,4)))
            self.dials[key_]=dial
            row.addWidget(dial,0)
            row.addStretch(1)
            v.addLayout(row)
        buttons=QHBoxLayout()
        buttons.setContentsMargins(0,2,0,1)
        buttons.setSpacing(1)
        self.mute=QPushButton("M",self)
        self.solo=QPushButton("S",self)
        self.arm=QPushButton("R",self)
        for btn,tag in ((self.mute,"muteButton"),
                        (self.solo,"soloButton"),
                        (self.arm,"armButton")):
            btn.setObjectName(tag)
            btn.setCheckable(True)
            btn.setFixedSize(18,19)
            buttons.addWidget(btn)
        self.mute.setToolTip("Mute real del canal")
        self.solo.setToolTip("Solo real: silencia todos los canales no solistas")
        self.arm.setToolTip("Armar impresión WAV de esta pista al pulsar REC")
        self.mute.setChecked(console.checked_mutes.get(key,False))
        self.solo.setChecked(bool(self.controls.get("solo")))
        self.arm.setChecked(bool(self.controls.get("arm")))
        self.mute.toggled.connect(lambda checked:self.console._mute(self.key,checked))
        self.solo.toggled.connect(lambda checked:self.console.set_channel_param(
            self.key,"solo",bool(checked)))
        self.arm.toggled.connect(lambda checked:self.console.set_channel_param(
            self.key,"arm",bool(checked)))
        v.addLayout(buttons)
        fader_area=QHBoxLayout()
        fader_area.setSpacing(0)
        fader_area.setContentsMargins(0,1,0,0)
        self.fader=StudioFader(self)
        self.fader.setRange(0,150)
        old=console.home.mixer_rows.get(key)
        amount=(old["fader"].value() if old else
                console.extra_gains.get(key,100))
        self.fader.setValue(amount)
        self.fader.setMinimumHeight(60)
        self.fader.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        self.fader.setInvertedAppearance(False)
        self.fader.setInvertedControls(False)
        fader_area.addWidget(self.fader,0)
        self.meter=StereoBar(self,scale=True)
        self.meter.setMinimumWidth(27)
        self.meter.setMaximumWidth(40)
        self.meter.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        fader_area.addWidget(self.meter,1)
        v.addLayout(fader_area,1)
        self.readout=_txt(f"{amount}%",self,9,"#e8f8ff",True,True)
        self.readout.setFixedHeight(18)
        v.addWidget(self.readout)
        self.fader.valueChanged.connect(lambda amount:
            self.console._level(self.key,amount,self.readout))
        label_=QLabel(name.upper(),self)
        label_.setAlignment(Qt.AlignCenter)
        label_.setFixedHeight(21)
        label_.setToolTip(name)
        label_.setStyleSheet(
            f"color:#e7faff;font-weight:900;font-size:9px;"
            f"background:#0b2638;border-bottom:4px solid {color};")
        v.addWidget(label_)
        self.name_label=label_
        self.mute.setEnabled(source is not None)
        self.solo.setEnabled(source is not None)
        self.arm.setEnabled(source is not None)
        self._compact=None

    def set_compact(self,compact):
        if self._compact==compact:return
        self._compact=compact
        layout=self.layout()
        layout.setContentsMargins(1,0,1,1) if compact else layout.setContentsMargins(2,2,2,3)
        layout.setSpacing(0 if compact else 1)
        self.number_label.setFixedHeight(9 if compact else 10)
        self.title_label.setFixedHeight(12 if compact else 18)
        for dial in self.dials.values():
            dial.setFixedSize(21,20) if compact else dial.setFixedSize(34,32)
        for button in (self.mute,self.solo,self.arm):
            button.setFixedSize(17,15) if compact else button.setFixedSize(18,19)
        self.readout.setFixedHeight(12 if compact else 18)
        self.name_label.setFixedHeight(15 if compact else 21)
        self.fader.setMinimumHeight(35 if compact else 60)
        self.meter.setMinimumHeight(35 if compact else 90)
        self.updateGeometry()

    def mousePressEvent(self,event):
        self.console.select_channel(self.key)
        super().mousePressEvent(event)

class StudioProConsole(ProjectMixerView):
    """Vista profesional de 16 canales basada en el catálogo real del proyecto."""
    is_pro_console=True

    def __init__(self,home,parent=None):
        QWidget.__init__(self,parent)
        self.home=home
        self.sources={}
        self.selected=set()
        self.checked_mutes={}
        self.extra_gains={}
        self.channels={}
        self.control_state={}
        self.visible_strips=[]
        self._signature=None
        self._updating=False
        self._last_refresh=0.
        self._audio_cache={}
        self._render_queue=[]
        self._rendering=None
        self._proc=None
        self._tmp=tempfile.TemporaryDirectory(prefix="stemmidi_console_midi_")
        self.transport=None
        self.inspected_key=None
        self.setObjectName("proConsoleRoot")
        self.setStyleSheet(SKIN)
        root=QHBoxLayout(self)
        root.setContentsMargins(2,2,2,2)
        root.setSpacing(4)

        self.sidebar=QFrame(self)
        self.sidebar.setObjectName("proSidebar")
        self.sidebar.setFixedWidth(189)
        side=QVBoxLayout(self.sidebar)
        side.setContentsMargins(5,5,5,5)
        side.setSpacing(3)
        brand=_txt("StemMIDI  •  CONSOLA PRO",self.sidebar,12,
                   "#e6fcff",True,True)
        brand.setFixedHeight(23)
        side.addWidget(brand)
        route_line=QHBoxLayout()
        route_line.addWidget(_txt("RUTEO",self.sidebar,8,"#a8cbdc",True))
        self.bus_select=QComboBox(self.sidebar)
        for n in range(1,17):
            self.bus_select.addItem(f"Bus {n:02d}",n)
        self.bus_select.setToolTip("Seleccionar el bus de salida cuyo nivel ajustar")
        route_line.addWidget(self.bus_select,1)
        side.addLayout(route_line)
        preset=_txt("PREAJUSTES DE MEZCLA",self.sidebar,9,"#8ae9f6",True)
        side.addWidget(preset)
        self.presets=QComboBox(self.sidebar)
        self.presets.addItems(("Estudio multipista","Voz al frente",
                               "Batería definida","Sin efectos"))
        self.presets.currentTextChanged.connect(self.apply_factory_preset)
        side.addWidget(self.presets)
        preset_buttons=QHBoxLayout()
        self.save_preset=QPushButton("GUARDAR",self.sidebar)
        self.restore_preset=QPushButton("CARGAR",self.sidebar)
        self.save_preset.clicked.connect(self.save_project_preset)
        self.restore_preset.clicked.connect(self.load_project_preset)
        preset_buttons.addWidget(self.restore_preset)
        preset_buttons.addWidget(self.save_preset)
        side.addLayout(preset_buttons)

        sources_line=QHBoxLayout()
        sources_line.addWidget(_txt("FUENTES",self.sidebar,9,"#8ae9f6",True))
        self.open_sources=QPushButton("Seleccionar…",self.sidebar)
        self.open_sources.clicked.connect(self.popup_sources)
        sources_line.addWidget(self.open_sources)
        side.addLayout(sources_line)
        self.file_list=QListWidget(self.sidebar)
        self.file_list.setMinimumHeight(28)
        self.file_list.setMaximumHeight(67)
        self.file_list.setItemDelegate(ContrastFileCheckboxDelegate(self.file_list))
        self.file_list.setStyleSheet(
            "background:#071b2b;color:#d9f6ff;border:1px solid #284d66;"
            "font-size:9px;QListWidget::item{min-height:13px;}")
        self.file_list.itemChanged.connect(self._check_source)
        side.addWidget(self.file_list,0)
        self.summary=_txt("Sin pistas marcadas",self.sidebar,8,"#a8d9ea")
        self.summary.setWordWrap(True)
        self.summary.setMaximumHeight(24)
        side.addWidget(self.summary)
        self.inspect_name=_txt("CANAL: VOCES",self.sidebar,9,"#8ae9f6",True)
        self.inspect_name.setFixedHeight(18)
        side.addWidget(self.inspect_name)

        from PySide6.QtWidgets import QTabWidget
        self.inspector=QTabWidget(self.sidebar)
        self.inspector.setStyleSheet("""
          QTabWidget::pane{border:1px solid #315c74;background:#091b2a;}
          QTabBar::tab{background:#102d40;color:#bce9fc;
                      padding:4px 12px;font-size:9px;border:1px solid #365467;}
          QTabBar::tab:selected{background:#0a5c87;color:#fff;}
        """)
        self.param_sliders={}
        for tab_name,params in (
            ("EQ",(("low","GRAVES",-120,120,.1),
                   ("mid","MEDIOS",-120,120,.1),
                   ("high","AGUDOS",-120,120,.1))),
            ("FX",(("send","REVERB",0,100,.01),
                   ("delay","DELAY",0,100,.01),
                   ("saturation","SAT",0,100,.01))),
            ("DIN",(("gate","GATE",0,100,.01),
                    ("compress","COMP",0,100,.01)))):
            page=QWidget(self.inspector)
            page_layout=QVBoxLayout(page)
            page_layout.setContentsMargins(3,4,3,4)
            page_layout.setSpacing(2)
            for key,title,minimum,maximum,scale in params:
                line=QHBoxLayout();line.setSpacing(3)
                t=_txt(title,page,8,"#c0dfed")
                t.setFixedWidth(43)
                line.addWidget(t)
                slider=QSlider(Qt.Horizontal,page)
                slider.setRange(minimum,maximum)
                slider.setToolTip(f"{title} aplicado en el motor PCM real")
                line.addWidget(slider,1)
                number=_txt("0",page,8)
                number.setFixedWidth(27)
                line.addWidget(number)
                slider.valueChanged.connect(
                    lambda value,k=key,scale=scale,l=number:
                    (l.setText(str(round(value*scale,1))),
                     self.set_channel_param(self.inspected_key,k,value*scale)
                     if self.inspected_key is not None else None))
                self.param_sliders[key]=(slider,number,scale)
                page_layout.addLayout(line)
            page_layout.addStretch(1)
            self.inspector.addTab(page,tab_name)
        self.inspector.setMaximumHeight(132)
        self.inspector.setMinimumHeight(105)
        side.addWidget(self.inspector,0)
        self.main_bus_line=QHBoxLayout()
        self.main_bus_line.setSpacing(4)
        self.main_bus_line.addWidget(_txt("BUS",self.sidebar,9,"#a6dffc",True))
        self.bus_slider=QSlider(Qt.Horizontal,self.sidebar)
        self.bus_slider.setRange(0,150)
        self.bus_slider.setValue(100)
        self.bus_slider.valueChanged.connect(self.set_bus_level)
        self.main_bus_line.addWidget(self.bus_slider,1)
        self.bus_number=_txt("100%",self.sidebar,8,"#e5faff")
        self.main_bus_line.addWidget(self.bus_number)
        side.addLayout(self.main_bus_line)
        self.bus_select.currentIndexChanged.connect(self._bus_changed)

        master=QHBoxLayout()
        master.setSpacing(3)
        for name in ("MASTER","BUS"):
            cell=QVBoxLayout()
            title=_txt(name,self.sidebar,9,"#defaff",True,True)
            title.setFixedHeight(18)
            cell.addWidget(title)
            line=QHBoxLayout();line.setSpacing(0)
            fader=StudioFader(self.sidebar)
            fader.setFixedWidth(25)
            fader.setMinimumHeight(76)
            fader.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
            line.addWidget(fader)
            meter=StereoBar(self.sidebar,scale=True)
            meter.setFixedWidth(49)
            meter.setMinimumHeight(83)
            line.addWidget(meter,1)
            cell.addLayout(line,1)
            readout=_txt("0.0 dB",self.sidebar,9,"#92f5d4",True,True)
            cell.addWidget(readout)
            master.addLayout(cell,1)
            if name=="MASTER":
                self.master_fader=fader
                self.master_meter=meter
                self.master_readout=readout
                fader.setRange(0,150)
                fader.setValue(home.master_volume.value())
                fader.valueChanged.connect(home.master_volume.setValue)
                home.master_volume.valueChanged.connect(fader.setValue)
            else:
                self.selected_bus_fader=fader
                self.bus_meter=meter
                self.bus_readout=readout
                fader.setRange(0,150)
                fader.setValue(100)
                fader.valueChanged.connect(
                    lambda value:self.bus_slider.setValue(value))
                self.bus_slider.valueChanged.connect(fader.setValue)
        side.addLayout(master,1)
        self.float_button=QPushButton("Ventana flotante",self.sidebar)
        self.float_button.clicked.connect(self.detach_to_float)
        side.addWidget(self.float_button,0)
        root.addWidget(self.sidebar,0)

        right=QWidget(self)
        right.setObjectName("proRight")
        self.right_layout=QVBoxLayout(right)
        self.right_layout.setContentsMargins(0,0,0,0)
        self.right_layout.setSpacing(3)
        self.rack=QFrame(right)
        self.rack.setObjectName("proRack")
        rack=QHBoxLayout(self.rack)
        rack.setContentsMargins(4,3,4,3)
        rack.setSpacing(4)
        matrix_col=QVBoxLayout()
        matrix_col.setSpacing(1)
        self.routing_page=0
        route_head=QHBoxLayout()
        route_head.setContentsMargins(0,0,0,0)
        route_head.setSpacing(3)
        route_head.addWidget(_txt("MATRIZ DE RUTEO · 16 BUSES",self.rack,
                                  9,"#b7e5fa",True),1)
        self.route_pages=QComboBox(self.rack)
        self.route_pages.setFixedWidth(93)
        self.route_pages.setToolTip(
            "Cambiar de banco de canales: 1–16, 17–32, 33–48, etc.")
        self.route_pages.currentIndexChanged.connect(self._routing_page_changed)
        route_head.addWidget(self.route_pages,0)
        matrix_col.addLayout(route_head)
        self.routing=RouteMatrix(self,self.rack)
        matrix_col.addWidget(self.routing,1)
        rack.addLayout(matrix_col,0)
        meter_col=QVBoxLayout()
        meter_col.setSpacing(2)
        meter_col.addWidget(_txt("MASTER",self.rack,8,"#d5eaff",True,True))
        self.top_meter=StereoBar(self.rack,scale=True)
        self.top_meter.setFixedWidth(46)
        meter_col.addWidget(self.top_meter,1)
        rack.addLayout(meter_col,0)
        wave_col=QVBoxLayout()
        wave_col.setSpacing(1)
        bar=QHBoxLayout()
        bar.addWidget(_txt("FORMA DE ONDA L/R · AUDIO REAL",
                           self.rack,9,"#a4edff",True))
        self.wave_source=QComboBox(self.rack)
        self.wave_source.setFixedWidth(145)
        self.wave_source.currentIndexChanged.connect(self._wave_selected)
        bar.addWidget(self.wave_source)
        wave_col.addLayout(bar)
        self.wave=RealWaveOverview(self.rack)
        wave_col.addWidget(self.wave,1)
        rack.addLayout(wave_col,1)
        self.rack.setFixedHeight(161)
        self.right_layout.addWidget(self.rack,0)
        # El transporte compartido se INSERTA aquí desde SharedProfessionalDock.
        self.console_transport=None
        self.channel_panel=QFrame(right)
        self.channel_panel.setObjectName("proChannels")
        bank=QVBoxLayout(self.channel_panel)
        bank.setContentsMargins(3,3,3,3)
        bank.setSpacing(1)
        self.channel_scroll=QScrollArea(self.channel_panel)
        self.channel_scroll.setWidgetResizable(True)
        self.channel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.channel_scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.channel_root=QWidget(self.channel_scroll)
        self.channel_root.setObjectName("proChannelRoot")
        self.channel_row=QHBoxLayout(self.channel_root)
        self.channel_row.setContentsMargins(1,1,1,1)
        self.channel_row.setSpacing(1)
        self.channel_scroll.setWidget(self.channel_root)
        self.channel_scroll.viewport().installEventFilter(self)
        bank.addWidget(self.channel_scroll,1)
        self.right_layout.addWidget(self.channel_panel,1)
        root.addWidget(right,1)
        self.right_widget=right
        self.refresh_catalog(force=True)
        self._bus_changed()
        self._sync_wave_sources()

    def _channel_plan(self):
        plan=list(super()._channel_plan())
        while len(plan)<16:
            index=len(plan)+1
            plan.append((f"Reserva {index}",None,f"CH {index:02d}"))
        return plan

    def _sync_channels(self,remember=True):
        # No sobrescribir con valores antiguos un preset recién cargado.
        if remember:
            for key,item in self.channels.items():
                self.control_state[key]=dict(item["strip"].controls)
                if item["source"] is not None:
                    self.checked_mutes[key]=item["strip"].mute.isChecked()
        while self.channel_row.count():
            item=self.channel_row.takeAt(0)
            widget=item.widget()
            if widget is not None:widget.deleteLater()
        self.channels={}
        self.visible_strips=[]
        plan=self._channel_plan()
        for index,(key,source,name) in enumerate(plan):
            strip=ProChannelStrip(self,key,source,name,
                                  COLORS[index%len(COLORS)],index,self.channel_root)
            self.channel_row.addWidget(strip,1)
            self.channels[key]=dict(source=source,fader=strip.fader,
                     mute=strip.mute,solo=strip.solo,record=strip.arm,
                     strip=strip,meter=strip.meter)
            self.visible_strips.append(strip)
        self.channel_row.addStretch(0)
        self._fit_strips()
        self.summary.setText(f"{len(self.selected)} seleccionadas · "
                             f"{len(self.sources)} archivos")
        if self.inspected_key not in self.channels:
            self.inspected_key=plan[0][0] if plan else None
        self.select_channel(self.inspected_key)
        self._sync_wave_sources()
        self._refresh_route_pages()
        self.routing.update()
        self._apply_live_controls()
        if self.transport:self.transport.selection_changed()

    def _refresh_route_pages(self):
        # Sin tope fijo: ampliar la matriz de 16 en 16 al aparecer pistas.
        total=max(1,len(self.visible_strips))
        banks=(total+15)//16
        self.routing_page=min(self.routing_page,banks-1)
        with QSignalBlocker(self.route_pages):
            self.route_pages.clear()
            for bank in range(banks):
                first=bank*16+1
                last=min((bank+1)*16,total)
                self.route_pages.addItem(f"CH {first}–{last}",bank)
            self.route_pages.setCurrentIndex(self.routing_page)
        self.route_pages.setEnabled(banks>1)
        # Pistas seleccionadas por encima de la primera bancada
        # siguen accesibles también cuando el inspector está en otra página.
        self.routing.update()

    def _routing_page_changed(self,index):
        if index<0:return
        self.routing_page=index
        self.routing.update()

    def _fit_strips(self):
        if not self.visible_strips:return
        viewport=self.channel_scroll.viewport()
        area=viewport.width()
        height=viewport.height()
        compact=height<310
        count=len(self.visible_strips)
        desired=max(49,min(86,(max(0,area)-6)//count-1))
        for strip in self.visible_strips:
            strip.set_compact(compact)
            strip.setFixedWidth(desired)
        self.channel_root.setMinimumWidth(count*(desired+1)+3)
        self.channel_root.setMinimumHeight(0)
        self.file_list.setVisible(not compact and self.file_list.count()>0)
        self.inspector.setFixedHeight(115 if compact else 132)
        self.rack.setFixedHeight(140 if compact else 161)

    def eventFilter(self,watched,event):
        if watched is self.channel_scroll.viewport() and event.type()==QEvent.Resize:
            QTimer.singleShot(0,self._fit_strips)
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._fit_strips()
        self.sidebar.setFixedWidth(168 if self.width()<1160 else 189)

    def install_console_transport(self,transport):
        self.console_transport=transport
        transport.setParent(self.right_widget)
        self.right_layout.insertWidget(1,transport,0)
        transport.show()
        self.wave.seek=lambda fraction:self._wave_seek(fraction)
        self._apply_live_controls()

    def attach_transport(self,transport):
        self.transport=transport
        self._apply_live_controls()
        self.transport.selection_changed()

    def _apply_live_controls(self):
        if self.transport is None:return
        for key,element in self.channels.items():
            source=element["source"]
            if source:
                self.transport.live.configure_channel(
                    source,element["strip"].controls)
        self.transport.live.set_track_levels(self.effective_levels())

    def _level(self,key,amount,readout):
        # Las ganancias de los faders conservan la lógica previa.
        super()._level(key,amount,readout)
        if self.transport:
            self.transport.live.set_track_levels(self.effective_levels())

    def _mute(self,key,checked):
        self.checked_mutes[key]=bool(checked)
        super()._mute(key,checked)
        if self.transport:
            self.transport.live.set_track_levels(self.effective_levels())

    def select_channel(self,key):
        if key not in self.channels:return
        self.inspected_key=key
        strip=self.channels[key]["strip"]
        self.inspect_name.setText("CANAL: "+strip.caption.upper())
        for param,(slider,readout,scale) in self.param_sliders.items():
            number=strip.controls.get(param,DEFAULT_CHANNEL[param])
            with QSignalBlocker(slider):
                slider.setValue(round(number/scale))
            readout.setText(str(round(number,1)))
        for other in self.visible_strips:
            other.setProperty("active",other is strip)
            other.style().unpolish(other)
            other.style().polish(other)
        self.routing.update()

    def set_channel_param(self,key,param,value):
        if key not in self.channels or param not in DEFAULT_CHANNEL:return
        strip=self.channels[key]["strip"]
        strip.controls[param]=value
        self.control_state[key]=dict(strip.controls)
        if param=="bus":
            self.routing.update()
        if param=="solo" and self.transport:
            self.transport.live.set_track_levels(self.effective_levels())
        source=self.channels[key]["source"]
        if source and self.transport:
            self.transport.live.configure_channel(source,{param:value})
        if param in self.param_sliders and self.inspected_key==key:
            slider,readout,scale=self.param_sliders[param]
            target=round(value/scale)
            with QSignalBlocker(slider):
                slider.setValue(target)
            readout.setText(str(round(value,1)))
        if self.transport:self.transport.refresh()

    def _bus_changed(self,*_):
        index=self.bus_select.currentData()
        if index is None:return
        value=(self.transport.live._bus_levels.get(index,1.)
               if self.transport else 1.)
        with QSignalBlocker(self.bus_slider):
            self.bus_slider.setValue(round(value*100))
        with QSignalBlocker(self.selected_bus_fader):
            self.selected_bus_fader.setValue(round(value*100))
        self.bus_number.setText(f"{round(value*100)}%")

    def set_bus_level(self,amount):
        index=self.bus_select.currentData()
        if index is None:return
        self.bus_number.setText(f"{amount}%")
        if self.transport:
            self.transport.live.set_bus_level(index,amount/100.)

    def _sync_wave_sources(self):
        current=self.wave_source.currentData()
        with QSignalBlocker(self.wave_source):
            self.wave_source.clear()
            self.wave_source.addItem("Sin audio",None)
            for key,path in self.selected_files():
                if path.suffix.lower() in AUDIO:
                    self.wave_source.addItem(path.stem[:24],str(path))
            matching=self.wave_source.findData(current)
            if (matching<0 or current is None) and self.wave_source.count()>1:
                matching=1
            self.wave_source.setCurrentIndex(max(0,matching))
        self._wave_selected()

    def _wave_selected(self,*_):
        self.wave.set_path(self.wave_source.currentData())

    def _wave_seek(self,fraction):
        if self.transport and self.transport.live.running:
            self.transport.live.seek(round(
                fraction*self.transport.live.duration_ms))

    def _check_source(self,item):
        super()._check_source(item)

    def popup_sources(self):
        menu=QMenu(self)
        menu.setStyleSheet("QMenu{background:#0a2638;color:#e4faff;"
                           "border:1px solid #4dbbd0;}QMenu::item:selected{background:#156788;}")
        for key,path in self.sources.items():
            action=menu.addAction(path.name[:54])
            action.setCheckable(True)
            action.setChecked(key in self.selected)
            action.setData(key)
        if not self.sources:
            empty=menu.addAction("No hay archivos en el proyecto")
            empty.setEnabled(False)
        chosen=menu.exec(self.open_sources.mapToGlobal(
            QPoint(0,self.open_sources.height())))
        if chosen is None:return
        key=chosen.data()
        if key not in self.sources:return
        for i in range(self.file_list.count()):
            item=self.file_list.item(i)
            if item.data(Qt.UserRole)==key:
                item.setCheckState(Qt.Checked if chosen.isChecked()
                                   else Qt.Unchecked)
                break

    def refresh_catalog(self,force=False):
        super().refresh_catalog(force)
        self._sync_wave_sources()

    def save_project_preset(self):
        project=getattr(self.home.main,"project_dir",None)
        if project is None:
            self.summary.setText("Abre un proyecto para guardar ajustes.")
            return
        folder=Path(project)/"presets"
        folder.mkdir(parents=True,exist_ok=True)
        content={"version":1,"channels":self.control_state,
                 "gains":self.extra_gains,
                 "mutes":self.checked_mutes,
                 "bus_levels":self.transport.live._bus_levels
                  if self.transport else {}}
        temp=folder/"mezclador.tmp"
        temp.write_text(json.dumps(content,ensure_ascii=False,indent=2),
                        encoding="utf-8")
        temp.replace(folder/"mezclador.json")
        self.summary.setText("Configuración del mezclador guardada.")

    def load_project_preset(self):
        project=getattr(self.home.main,"project_dir",None)
        if project is None:return
        path=Path(project)/"presets"/"mezclador.json"
        if not path.is_file():
            self.summary.setText("Este proyecto no tiene preset guardado.")
            return
        try:
            content=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(content,dict) or content.get("version")!=1:
                raise ValueError("Formato de preset desconocido")
            states=content.get("channels",{})
            for key,params in states.items():
                if isinstance(params,dict):
                    self.control_state[key]={**DEFAULT_CHANNEL,
                                             **{k:v for k,v in params.items()
                                                 if k in DEFAULT_CHANNEL}}
            self.extra_gains.update(content.get("gains",{}))
            self.checked_mutes.update(content.get("mutes",{}))
            self._sync_channels(remember=False)
            for index,value in content.get("bus_levels",{}).items():
                if self.transport:
                    self.transport.live.set_bus_level(int(index),float(value))
            self._bus_changed()
            self.summary.setText("Preset de este proyecto recuperado.")
        except (OSError,ValueError,TypeError) as exc:
            self.summary.setText("No se pudo cargar: "+str(exc)[:40])

    def apply_factory_preset(self,name):
        if not self.channels:return
        # La fábrica almacena ajustes reales, nunca audio ni rutas privadas.
        defaults={
            "Estudio multipista":{"low":0.,"mid":0.,"high":0.,
                                  "gate":0.,"compress":0.,"saturation":0.,
                                  "send":0.,"delay":0.,"trim":0.,"pan":0.},
            "Voz al frente":{"compress":.32,"mid":2.5,"high":1.5},
            "Batería definida":{"compress":.48,"low":2.0,
                                "high":1.0,"gate":.10},
            "Sin efectos":{"low":0.,"mid":0.,"high":0.,
                           "gate":0.,"compress":0.,"saturation":0.,
                           "send":0.,"delay":0.},
        }.get(name,{})
        for key,channel in self.channels.items():
            if channel["source"] is None:continue
            for param,value in defaults.items():
                self.set_channel_param(key,param,value)
        if defaults:
            self.summary.setText("Preset aplicado a las pistas activas.")

    def detach_to_float(self):
        try:
            self.home._floating_manager.detach(self.home.mix_card)
        except (AttributeError,RuntimeError):
            self.summary.setText("No se pudo abrir la ventana flotante.")

    def update_meters(self,peaks,master,buses,position):
        for channel in self.channels.values():
            source=channel["source"]
            pair=peaks.get(source,(0.,0.)) if source else (0.,0.)
            channel["meter"].set_peaks(*pair)
        self.master_meter.set_peaks(*master)
        self.top_meter.set_peaks(*master)
        idx=self.bus_select.currentData() or 1
        pair=buses.get(idx,(0.,0.))
        self.bus_meter.set_peaks(*pair)
        for name,level,readout in (
            ("MASTER",self.home.master_volume.value(),self.master_readout),
            ("BUS",self.bus_slider.value(),self.bus_readout)):
            text=("-∞" if level==0 else f"{20*math.log10(level/100):+.1f}")
            readout.setText(text+" dB")
        self.wave.position=max(0.,min(1.,position))
        self.wave.update()

    def reopen(self):
        super().reopen()
        self._sync_wave_sources()

class ProConsoleTransport(ProjectMixerTransport):
    """Transporte compacto con backend PCM real, dentro de la propia consola."""
    def __init__(self,view,parent=None):
        QFrame.__init__(self,parent)
        self.view=view
        self._notice=""
        self.live=ProConsoleEngine(self)
        self.live.error.connect(self._error)
        self.setObjectName("consoleTransport")
        self.setStyleSheet("""
        QFrame#consoleTransport{
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #183951,stop:.2 #0b293e,stop:1 #061827);
            border:1px solid #395f70;border-radius:3px;}
        QPushButton{color:#e9fbff;font-weight:900;
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #385d75,stop:.5 #17445e,stop:1 #071b2d);
            border:1px solid #527f96;border-top:1px solid #9bc5d7;
            border-radius:3px;min-height:22px;}
        QPushButton:checked{background:#ac2938;color:#fff;}
        QPushButton:pressed{background:#0b608b;}
        QSlider::groove:horizontal{height:7px;background:#03131e;
            border:1px solid #427386;border-radius:3px;}
        QSlider::sub-page:horizontal{background:#31e6c4;border-radius:3px;}
        QSlider::handle:horizontal{width:11px;margin:-4px 0;
            background:#e6faff;border:1px solid #ffffff;border-radius:4px;}
        """)
        row=QHBoxLayout(self)
        row.setContentsMargins(5,2,5,2)
        row.setSpacing(5)
        self.play=QPushButton("▶",self)
        self.pause=QPushButton("Ⅱ",self)
        self.stop=QPushButton("■",self)
        for button in (self.play,self.pause,self.stop):
            button.setFixedWidth(33)
        self.play.setToolTip("Reproducir pistas elegidas")
        self.pause.setToolTip("Pausar/reanudar")
        self.stop.setToolTip("Detener y volver al inicio")
        row.addWidget(self.play)
        row.addWidget(self.pause)
        row.addWidget(self.stop)
        self.record=QPushButton("● REC",self)
        self.record.setObjectName("recButton")
        self.record.setCheckable(True)
        self.record.setToolTip("Imprimir WAV: master y pistas con R armado")
        self.record.setFixedWidth(60)
        row.addWidget(self.record)
        self.clock=_txt("00:00 / 00:00",self,9,"#d5eefa",True)
        self.clock.setMinimumWidth(96)
        row.addWidget(self.clock)
        self.timeline=QSlider(Qt.Horizontal,self)
        self.timeline.setObjectName("projectTimeline")
        self.timeline.setRange(0,1000)
        self.timeline.setTracking(False)
        self.timeline.setFixedWidth(235)
        self.timeline.sliderReleased.connect(self.seek)
        row.addWidget(self.timeline,1)
        self.status=_txt("Selecciona pistas para reproducir",self,8,
                          "#9bcee0")
        self.status.setMinimumWidth(130)
        self.status.setMaximumWidth(240)
        row.addWidget(self.status,0)
        row.addStretch(1)
        self.setFixedHeight(37)
        self.play.clicked.connect(self.play_selected)
        self.pause.clicked.connect(self.pause_selected)
        self.stop.clicked.connect(self.stop_selected)
        self.record.toggled.connect(self._record_clicked)
        self._meter_names=()
        self.track_meters={}
        # El master físico y el de Inicio son el MISMO control de ganancia.
        self.view.home.master_volume.valueChanged.connect(
            lambda value:(self.live.set_track_levels(
                self.view.effective_levels()),self.selection_changed()))
        self.timer=QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.view.attach_transport(self)
        self.refresh()

    def _sync_meters(self):
        self._meter_names=tuple(self.view._channel_plan())
        self.track_meters={key:(data["source"],data["meter"])
                           for key,data in self.view.channels.items()}

    def _fit_layout(self):
        return

    def _record_clicked(self,active):
        if active:
            if not self.live.running:
                self.record.setChecked(False)
                self.status.setText("Reproduce primero la mezcla.")
                return
            directory=QFileDialog.getExistingDirectory(
                self,"Guardar mezcla y pistas WAV",
                str(getattr(self.view.home.main,"project_dir",None)
                     or Path.home()))
            if not directory or not self.live.start_recording(directory):
                self.record.setChecked(False)
                return
            self.status.setText("Grabando WAV · pulsar REC para terminar")
        else:
            self.live.stop_recording()
            if self.live.record_directory:
                self.status.setText("WAV guardados en "+str(self.live.record_directory))

    def stop_selected(self):
        self.live.stop()
        with QSignalBlocker(self.record):
            self.record.setChecked(False)
        self.refresh()

    def refresh(self):
        from preview_player import timecode
        self._sync_meters()
        if self.live.running and (
            (self.live.duration_ms and self.live.position()>=self.live.duration_ms)
            or (self.live._eof and self.live._queue.empty() and self.live.blocks)):
            self.live.stop()
            with QSignalBlocker(self.record):
                self.record.setChecked(False)
        self.play.setEnabled(self.view.ready())
        self.pause.setEnabled(self.live.running)
        self.stop.setEnabled(self.live.running)
        self.record.setEnabled(self.live.running)
        self.timeline.setEnabled(self.live.running and self.live.duration_ms>0)
        pos=self.live.position() if self.live.running else 0
        self.clock.setText(f"{timecode(pos)} / {timecode(self.live.duration_ms)}")
        if not self.timeline.isSliderDown() and self.live.duration_ms:
            with QSignalBlocker(self.timeline):
                self.timeline.setValue(round(1000*pos/self.live.duration_ms))
        playing=self.live.running and not self.live.paused
        peaks=self.live.track_peaks if playing else {}
        master=self.live.master_peaks if playing else (0.,0.)
        buses=self.live.bus_peaks if playing else {}
        fraction=pos/max(1,self.live.duration_ms)
        self.view.update_meters(peaks,master,buses,fraction)
        if self.live.running and not self.live.paused and not self.live.recording:
            self.status.setText(
                f"{len(self.view.selected)} pistas · PCM {self.live.blocks} bloques")
        elif self.live.paused:
            self.status.setText("Pausado")
        elif not self.live.running and not self._notice:
            self.status.setText(f"{len(self.view.selected)} pistas seleccionadas")

