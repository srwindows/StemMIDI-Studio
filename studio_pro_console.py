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
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QPoint, QRectF, QSize, QTimer, Signal, QSignalBlocker, QEvent, QProcess
from PySide6.QtGui import (
    QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QFont,
    QPolygonF, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QDial, QSlider, QPushButton, QCheckBox,
    QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QSizePolicy, QListWidgetItem, QListWidget, QMenu, QFileDialog, QAbstractItemView
)
from project_mixer_expanded import (
    ProjectMixerView, ProjectMixerTransport, ContrastFileCheckboxDelegate,
    AUDIO, MIDI, FAMILIES, label
)
from console_audio_engine import DEFAULT_CHANNEL, ProConsoleEngine, ffmpeg_executable
from studio_home import StudioFader
from studio_vu_unified import Ballistics
from results_dragdrop import FilesDragList, valid_mime_paths
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
import hashlib

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
QFrame#proStrip[dragTarget="true"]{
    border:2px solid #52f4ff;background:#164763;
}
QFrame#proSourcePanel{
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #123c61,stop:.20 #0b2948,stop:1 #061829);
    border:1px solid #4cb9e9;border-top:2px solid #91eaff;
    border-radius:6px;
}
QListWidget#proAvailableSources{
    color:#dff9ff;background:#05192f;
    border:1px solid #277fa6;border-radius:5px;
    font-size:10px;alternate-background-color:#0d304b;
    selection-background-color:#0d78aa;
}
QListWidget#proAvailableSources::item{
    min-height:22px;padding:2px 5px;
    border-bottom:1px solid #164663;
}
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
        self.setAcceptDrops(True)
        self._drop_highlight=False
        v=QVBoxLayout(self)
        v.setContentsMargins(2,3,2,3)
        v.setSpacing(4)
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
            # Repartir la altura recuperada en SEPARAR los potenciómetros,
            # no dejar un rectángulo sin contenido debajo del fader.
            v.addStretch(1)
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
        # Altura reducida a la mitad; ya NO crece hasta ocupar el panel.
        self.fader.setFixedHeight(96)
        self.fader.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.fader.setInvertedAppearance(False)
        self.fader.setInvertedControls(False)
        fader_area.addWidget(self.fader,0)
        self.meter=StereoBar(self,scale=True)
        self.meter.setMinimumWidth(27)
        self.meter.setMaximumWidth(40)
        self.meter.setFixedHeight(96)
        self.meter.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        fader_area.addWidget(self.meter,1)
        self.fader_area=fader_area
        v.addLayout(fader_area,0)
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
        # Los hijos reciben arrastres de Finder y del panel del proyecto.
        for child in (self.fader,self.meter,self.title_label,self.name_label):
            child.setAcceptDrops(True)
            child.installEventFilter(self)
        self._compact=None

    def set_compact(self,compact):
        if self._compact==compact:return
        self._compact=compact
        layout=self.layout()
        layout.setContentsMargins(1,0,1,1) if compact else layout.setContentsMargins(2,2,2,3)
        layout.setSpacing(2 if compact else 4)
        self.number_label.setFixedHeight(9 if compact else 10)
        self.title_label.setFixedHeight(12 if compact else 18)
        for dial in self.dials.values():
            dial.setFixedSize(21,20) if compact else dial.setFixedSize(34,32)
        for button in (self.mute,self.solo,self.arm):
            button.setFixedSize(17,15) if compact else button.setFixedSize(18,19)
        self.readout.setFixedHeight(12 if compact else 18)
        self.name_label.setFixedHeight(15 if compact else 21)
        # Mismo factor de reducción también en pantallas pequeñas.
        self.fader.setFixedHeight(70 if compact else 96)
        self.meter.setFixedHeight(70 if compact else 96)
        self.updateGeometry()

    def _accept_audio_drop(self,event):
        files=valid_mime_paths(event.mimeData())
        if len(files)==1 and files[0].suffix.lower() in AUDIO | MIDI:
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return files[0]
        event.ignore()
        return None

    def _handle_drop_event(self,event):
        if event.type() in (QEvent.DragEnter,QEvent.DragMove):
            result=self._accept_audio_drop(event)
            highlight=result is not None
            if highlight!=self._drop_highlight:
                self._drop_highlight=highlight
                self.setProperty("dragTarget",highlight)
                self.style().unpolish(self)
                self.style().polish(self)
            return True
        if event.type() in (QEvent.DragLeave,QEvent.Drop):
            self._drop_highlight=False
            self.setProperty("dragTarget",False)
            self.style().unpolish(self)
            self.style().polish(self)
            if event.type()==QEvent.Drop:
                source=self._accept_audio_drop(event)
                if source is not None:
                    if self.console.assign_to_channel(self.key,source):
                        event.acceptProposedAction()
                    return True
            else:
                event.accept()
            return True
        return False

    def eventFilter(self,watched,event):
        if watched in (self.fader,self.meter,self.title_label,self.name_label):
            if self._handle_drop_event(event):return True
        if (watched in (self.title_label,self.name_label,self.meter)
                and event.type()==QEvent.MouseButtonPress):
            self.console.select_channel(self.key)
        return super().eventFilter(watched,event)

    def dragEnterEvent(self,event):
        self._handle_drop_event(event)
    def dragMoveEvent(self,event):
        self._handle_drop_event(event)
    def dragLeaveEvent(self,event):
        self._handle_drop_event(event)
    def dropEvent(self,event):
        self._handle_drop_event(event)

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
        self.manual_assignments={}
        self.manual_sources={}
        self._known_auto_files=set()
        self._project_key=None
        self.visible_strips=[]
        self._signature=None
        self._channel_render_signature=None
        self._updating=False
        self._last_refresh=0.
        self._audio_cache={}
        self._midi_instrument_overrides={}
        self._midi_applied_instruments={}
        # Selected SF2 belongs to each LOGICAL mixer strip, not to a
        # filename and never to the shared preview SoundFont.
        self._midi_soundfonts={}
        self._midi_applied_soundfonts={}
        self._midi_render_versions={}
        self._midi_instruments_loaded=False
        # Preview program is per original MIDI file, independent from the
        # 16 mixer channel instruments and without edits to the originals.
        self.preview_midi_programs={}
        self.preview_selected_key=None
        self._preview_loaded_key=None
        self._preview_loaded_program=None
        self._preview_proc=None
        self._preview_rendering=None
        self._preview_cache={}
        self._preview_temp=tempfile.TemporaryDirectory(prefix="stemmidi_mixer_preview_")
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
        self.file_list=FilesDragList(self.sidebar)
        # También acepta archivos desde Resultados sobre la lista compacta.
        # Compartir exactamente el mismo motor y el mismo catálogo de la
        # pestaña y de la ventana flotante: arrastre por copia, nunca mover.
        self.file_list.set_drop_handler(
            lambda paths:self.home._result_file_drag_router.deliver("mixer",paths)
            if getattr(self.home,"_result_file_drag_router",None) else False,
            AUDIO|MIDI)
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
        # Catálogo interno del SF2. NO es un control visible: los únicos
        # selectores de instrumentos están encima de cada canal.
        self.midi_instrument_select=QComboBox(self.sidebar)
        self.midi_instrument_select.setObjectName("mixerMidiCatalog")
        self.midi_instrument_select.addItem("Original del MIDI",None)
        self.midi_instrument_select.hide()

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
            fader.setFixedHeight(96)
            fader.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            line.addWidget(fader)
            meter=StereoBar(self.sidebar,scale=True)
            meter.setFixedWidth(49)
            meter.setFixedHeight(96)
            line.addWidget(meter,1)
            cell.addLayout(line,1)
            readout=_txt("0.0 dB",self.sidebar,9,"#92f5d4",True,True)
            cell.addWidget(readout)
            master.addLayout(cell,1)
            if name=="MASTER":
                self.master_fader=fader
                self.master_meter=meter
                meter.setToolTip("MASTER · nivel real POST-FADER de la salida")
                self.master_readout=readout
                fader.setRange(0,150)
                fader.setValue(home.master_volume.value())
                fader.valueChanged.connect(home.master_volume.setValue)
                home.master_volume.valueChanged.connect(fader.setValue)
            else:
                self.selected_bus_fader=fader
                self.selected_bus_cell=cell
                self.bus_meter=meter
                meter.setToolTip("BUS · nivel POST-BUS, PRE-MASTER; no depende del fader MASTER")
                self.bus_readout=readout
                fader.setRange(0,150)
                fader.setValue(100)
                fader.valueChanged.connect(
                    lambda value:self.bus_slider.setValue(value))
                self.bus_slider.valueChanged.connect(fader.setValue)
        # MASTER/BUS a la altura de los faders de canal, sin dejar
        # el espacio vacío bajo ambos controles.
        side.addStretch(1)
        side.addLayout(master,0)
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
        channel_stack=QVBoxLayout(self.channel_root)
        channel_stack.setContentsMargins(0,0,0,0)
        channel_stack.setSpacing(1)
        self.midi_program_row=QHBoxLayout()
        self.midi_program_row.setContentsMargins(1,0,1,0)
        self.midi_program_row.setSpacing(1)
        channel_stack.addLayout(self.midi_program_row,0)
        self.midi_programs={}
        self.channel_row=QHBoxLayout()
        self.channel_row.setContentsMargins(1,1,1,1)
        self.channel_row.setSpacing(1)
        channel_stack.addLayout(self.channel_row,1)
        self.channel_scroll.setWidget(self.channel_root)
        self.channel_scroll.viewport().installEventFilter(self)
        bank.addWidget(self.channel_scroll,1)
        self.right_layout.addWidget(self.channel_panel,1)
        root.addWidget(right,1)
        self.right_widget=right
        # Panel lateral derecho: resultados del proyecto realmente arrastrables.
        self.sources_panel=QFrame(self)
        self.sources_panel.setObjectName("proSourcePanel")
        self.sources_panel.setFixedWidth(180)
        source_col=QVBoxLayout(self.sources_panel)
        source_col.setContentsMargins(5,6,5,6)
        source_col.setSpacing(5)
        available_title=_txt("ARCHIVOS PARA MEZCLAR",self.sources_panel,10,
                             "#b7f6ff",True)
        available_title.setWordWrap(True)
        source_col.addWidget(available_title)
        info=_txt("Arrastra un archivo al fader deseado.\n"
                  "Si ya hay uno, lo sustituye.",self.sources_panel,
                  9,"#abd5e9")
        info.setWordWrap(True)
        source_col.addWidget(info)
        # Two independent lists: MIDI instruments are never mixed with
        # audio filenames. Both preserve drag-and-drop to each channel.
        midi_header=_txt("MIDI · clic derecho: instrumento",self.sources_panel,
                         9,"#8ceaf1",True)
        midi_header.setFixedHeight(19)
        source_col.addWidget(midi_header,0)
        self.available_midi_files=FilesDragList(self.sources_panel)
        self.available_midi_files.setObjectName("mixerAvailableMIDI")
        audio_header=_txt("AUDIO · WAV / FLAC / MP3…",self.sources_panel,
                          9,"#8ceaf1",True)
        audio_header.setFixedHeight(19)
        self.available_audio_files=FilesDragList(self.sources_panel)
        self.available_audio_files.setObjectName("mixerAvailableAudio")
        original_file_list_skin="""
            QListWidget{color:#e7f8ff;background:#071e31;
              border:1px solid #4a8198;border-radius:5px;
              font-size:11px;alternate-background-color:#102d43;
              selection-background-color:#1b7fa9;selection-color:#ffffff;}
            QListWidget::item{color:#e7f8ff;min-height:26px;
              padding:3px 6px;border-bottom:1px solid #21475e;}
            QListWidget::item:selected{background:#1b7fa9;color:#ffffff;}
            QListWidget::item:!selected{color:#e7f8ff;}
            QListWidget::item:hover:!selected{background:#18455d;color:#ffffff;}
        """
        for listing in (self.available_midi_files,self.available_audio_files):
            listing.setStyleSheet(original_file_list_skin)
            listing.setAlternatingRowColors(True)
            listing.setSelectionMode(QAbstractItemView.SingleSelection)
            listing.setTextElideMode(Qt.ElideMiddle)
            listing.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Backwards-compatible reference for older code opening the MIDI list.
        self.available_files=self.available_midi_files
        source_col.addWidget(self.available_midi_files,2)
        source_col.addWidget(audio_header,0)
        source_col.addWidget(self.available_audio_files,3)
        self.available_midi_files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.available_midi_files.customContextMenuRequested.connect(
            self._midi_preview_context_menu)
        self.available_count=_txt("0 archivos",self.sources_panel,9,"#7edfe9")
        self.available_count.setWordWrap(True)
        source_col.addWidget(self.available_count,0)
        # PREESCUCHA EXCLUSIVA de la lista derecha: no toca el transporte,
        # mute, faders, selección ni buses del mezclador.
        from preview_player import PreviewPlayer
        self.preview_engine=PreviewPlayer("PREESCUCHA DE ARCHIVOS",self.sources_panel)
        self.preview_engine.hide()
        from mixer_midi_live_preview import MixerMidiLivePreview
        self.midi_live_preview=MixerMidiLivePreview(self)
        self.midi_live_preview.error.connect(self._preview_error)
        self.preview_panel=QFrame(self.sources_panel)
        self.preview_panel.setObjectName("mixerFilePreview")
        self.preview_panel.setStyleSheet("""
            QFrame#mixerFilePreview{background:#082d42;
              border:1px solid #40a7be;border-radius:5px;}
            QFrame#mixerFilePreview QLabel{color:#e1fbff;font-size:10px;}
            QFrame#mixerFilePreview QPushButton{background:#176382;
              color:white;font-weight:900;border:1px solid #52bed7;
              border-radius:3px;padding:0;}
            QFrame#mixerFilePreview QSlider::groove:horizontal{
              height:5px;background:#092034;border-radius:2px;}
            QFrame#mixerFilePreview QSlider::sub-page:horizontal{
              background:#32e2b6;border-radius:2px;}
            QFrame#mixerFilePreview QSlider::handle:horizontal{
              background:white;border-radius:4px;width:10px;margin:-3px 0;}
        """)
        preview_col=QVBoxLayout(self.preview_panel)
        preview_col.setContentsMargins(3,4,3,4)
        preview_col.setSpacing(2)
        preview_title=_txt("PREESCUCHA · AUDIO / MIDI",self.preview_panel,
                           9,"#7df0e9",True,True)
        preview_col.addWidget(preview_title)
        self.preview_file_label=_txt("Selecciona un archivo",self.preview_panel,
                                     9,"#c4edff")
        self.preview_file_label.setWordWrap(False)
        self.preview_file_label.setFixedHeight(17)
        preview_col.addWidget(self.preview_file_label)
        controls=QHBoxLayout()
        controls.setSpacing(3)
        self.preview_play=QPushButton("▶",self.preview_panel)
        self.preview_pause=QPushButton("Ⅱ",self.preview_panel)
        self.preview_stop=QPushButton("■",self.preview_panel)
        for button in (self.preview_play,self.preview_pause,self.preview_stop):
            button.setFixedSize(27,23)
            controls.addWidget(button)
        self.preview_play.setToolTip("Escuchar SOLO el archivo seleccionado de la lista derecha")
        self.preview_pause.setToolTip("Pausar/reanudar la preescucha")
        self.preview_stop.setToolTip("Detener la preescucha")
        self.preview_clock=_txt("00:00",self.preview_panel,8,"#d3f6ff",True)
        controls.addWidget(self.preview_clock,1)
        preview_col.addLayout(controls)
        self.preview_timeline=QSlider(Qt.Horizontal,self.preview_panel)
        self.preview_timeline.setRange(0,1000)
        self.preview_timeline.setTracking(False)
        self.preview_timeline.sliderReleased.connect(self._seek_file_preview)
        preview_col.addWidget(self.preview_timeline)
        self.preview_status=_txt("Sin archivo",self.preview_panel,8,"#b3e3f1")
        self.preview_status.setFixedHeight(16)
        preview_col.addWidget(self.preview_status)
        source_col.addWidget(self.preview_panel,0)
        self.preview_play.clicked.connect(self._play_file_preview)
        self.preview_pause.clicked.connect(self._pause_file_preview)
        self.preview_stop.clicked.connect(self._stop_file_preview)
        self.available_midi_files.currentItemChanged.connect(
            lambda item,old:self._available_selection_changed(
                self.available_midi_files,item))
        self.available_audio_files.currentItemChanged.connect(
            lambda item,old:self._available_selection_changed(
                self.available_audio_files,item))
        self.preview_engine.error.connect(self._preview_error)
        self.preview_timer=QTimer(self)
        self.preview_timer.setInterval(150)
        self.preview_timer.timeout.connect(self._refresh_file_preview)
        self.preview_timer.start()
        root.addWidget(self.sources_panel,0)
        self._catalog_timer=QTimer(self)
        self._catalog_timer.setInterval(4000)
        self._catalog_timer.timeout.connect(self._poll_project_sources)
        self._catalog_timer.start()
        self.refresh_catalog(force=True)
        self._bus_changed()
        self._sync_wave_sources()

    def _catalog(self):
        found=super()._catalog()
        for key,path in self.manual_sources.items():
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in AUDIO|MIDI:
                found[key]=path
        return found

    def _project_identity(self):
        project=getattr(self.home.main,"project_dir",None)
        return str(Path(project).resolve()) if project else None

    def _default_family(self,path):
        """Reconocer stems del proyecto, sin tratar canciones como instrumentos."""
        from stem_detection import is_separated_stem
        import re
        stem=Path(path).stem.casefold()
        parts={part.casefold() for part in Path(path).parts}
        tokens=set(re.split(r"[^a-záéíóúñ0-9]+",stem))
        if Path(path).suffix.lower() not in AUDIO:return None
        # La voz afinada propia y los stems de separación son resultados conocidos.
        trusted=(is_separated_stem(path) or
                 bool(parts.intersection({"stems","pistas_separadas",
                                          "separacion","separación",
                                          "afinacion_vocal","voces","vocal"})) or
                 stem.startswith(("voz_afinada","voz-afinada","voz afinada")))
        if not trusted:return None
        for family,words in (
          ("Voces",{"vocals","vocal","voz","voces","voice","voices","afinada"}),
          ("Batería",{"drums","drum","bateria","batería","percussion"}),
          ("Bajo",{"bass","bajo","bajos"}),
          ("Guitarra",{"guitar","guitars","guitarra","guitarras"}),
          ("Piano",{"piano","keys","keyboard"}),
          ("Viento",{"viento","vientos","wind","winds","brass","woodwind"}),
          ("Otros",{"other","others","otros","otro"})):
            if tokens.intersection(words):return family
        return None

    def _channel_plan(self):
        # Siete canales fijos por familias + CH 08…CH 16, sin reemplazar
        # la mesa por una vista reducida al pasar a ventana flotante.
        base=list(ProjectMixerView._channel_plan(self))[:7]
        auto={family:None for family in FAMILIES}
        explicitly_placed={key for key in self.manual_assignments.values()
                           if key in self.selected and key in self.sources}
        # Un resultado nuevo no sustituye otro stem válido ya cargado.
        for family in FAMILIES:
            current=self.channels.get(family,{}).get("source")
            if (current and current in self.selected and current in self.sources
                    and current not in explicitly_placed
                    and self._default_family(self.sources[current])==family):
                auto[family]=current
        for key,path in sorted(self.selected_files(),
                               key=lambda entry:entry[1].name.casefold()):
            family=self._default_family(path)
            if key in explicitly_placed:continue
            if family in auto and auto[family] is None:
                auto[family]=key
        slots=[]
        used=set()
        for family in FAMILIES:
            override=self.manual_assignments.get(family)
            candidate=override if override in self.selected and override in self.sources else auto.get(family)
            if candidate in used and override is None:candidate=None
            if candidate:used.add(candidate)
            slots.append((family,candidate,family))
        extras=[key for key,path in sorted(self.selected_files(),
                key=lambda e:e[1].name.casefold()) if key not in used]
        for n in range(8,17):
            channel=f"CH {n:02d}"
            assigned=self.manual_assignments.get(channel)
            if assigned not in self.selected or assigned not in self.sources:
                assigned=None
            if assigned is None and extras:
                assigned=extras.pop(0)
            if assigned:used.add(assigned)
            slots.append((channel,assigned,channel))
        return slots

    def assign_to_channel(self,channel,path):
        """Un archivo por canal; reemplazo, sin borrar el archivo anterior."""
        if channel not in self.channels:return False
        path=Path(path).expanduser()
        if (not path.is_file() or path.is_symlink() or
                path.suffix.lower() not in AUDIO|MIDI):
            return False
        path=path.resolve()
        project=self._project_identity()
        # Aceptar archivos que ya están en Resultados o importados mediante
        # un arrastre explícito; nunca mover ni eliminar los originales.
        key=str(path)
        old=self.channels[channel]["source"]
        if old==key:return True
        if self.transport and self.transport.live.running:
            self.transport.live.stop()  # Evitar mezcla con rutas ya cambiadas.
        self.sources[key]=path
        # An explicitly dropped source must survive the periodic catalog scan
        # even when it lies inside the project but is not yet in _gather_files.
        self.manual_sources[key]=path
        self.selected.add(key)
        self.manual_assignments[channel]=key
        if old and old!=key and old not in self.manual_assignments.values():
            self.selected.discard(old)
        self._audio_cache.pop(channel,None)
        # A custom SoundFont is a CHANNEL setting: keep its selected patch
        # even if the MIDI file in that strip gets replaced. Audio input
        # disables the selector without changing that channel's bank.
        if channel not in self._midi_soundfonts:
            self._midi_instrument_overrides.pop(channel,None)
        self._midi_applied_instruments.pop(channel,None)
        self._midi_applied_soundfonts.pop(channel,None)
        self._midi_render_versions[channel]=self._midi_render_versions.get(channel,0)+1
        self._sync_channels()
        if path.suffix.lower() in MIDI:
            # El arrastre crea una fuente nueva; no depende de marcar la lista.
            self._schedule_midi(channel)
            # Al soltar un MIDI, mostrar inmediatamente SU instrumento,
            # sin obligar al usuario a buscar el canal en el inspector.
            self.select_channel(channel)
        self._update_available_files()
        self._refresh_file_checks()
        self.summary.setText(f"{path.name} → {channel} · sustituido"
                             if old else f"{path.name} → {channel}")
        return True

    def audio_path(self,key):
        # The same file can have a distinct synth render on each channel.
        if key in self.channels:
            source=self.channels[key]["source"]
            if not source or source not in self.sources:return None
            file=self.sources[source]
            return self._audio_cache.get(key) if file.suffix.lower() in MIDI else file
        return ProjectMixerView.audio_path(self,key)

    def paths_for_mix(self):
        return [(channel,path) for channel,entry in self.channels.items()
                if entry.get("source") and (path:=self.audio_path(channel)) is not None]

    def ready(self):
        loaded=[channel for channel,entry in self.channels.items() if entry["source"]]
        return bool(loaded) and all(self.audio_path(channel) is not None
                                    for channel in loaded)

    def effective_levels(self):
        master=self.home.master_volume.value()/100.
        return {channel:(0. if entry["mute"].isChecked() else
                         master*entry["fader"].value()/100.)
                for channel,entry in self.channels.items()
                if entry["source"]}

    def _midi_render_source_key(self,key):
        return self.channels[key]["source"]

    def _midi_render_key_active(self,key):
        if key not in self.channels:return False
        source=self.channels[key]["source"]
        return bool(source in self.sources and source in self.selected
                    and self.sources[source].suffix.lower() in MIDI)

    def _schedule_midi(self,key):
        if key in self.channels:
            channels=[key]
        else:
            channels=[name for name,item in self.channels.items()
                      if item["source"]==key]
        for channel in channels:
            if not self._midi_render_key_active(channel):continue
            if (channel in self._audio_cache or channel in self._render_queue
                    or self._rendering==channel):continue
            self._render_queue.append(channel)
        self._next_midi()

    def _schedule_selected_midi(self):
        for channel in list(self.channels):
            if self._midi_render_key_active(channel):
                self._schedule_midi(channel)

    def _refresh_file_checks(self):
        with QSignalBlocker(self.file_list):
            for i in range(self.file_list.count()):
                item=self.file_list.item(i)
                item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in self.selected
                                   else Qt.Unchecked)

    def _poll_project_sources(self):
        if self.isVisible():
            self.refresh_catalog()

    def _selected_preview_path(self):
        key=self.preview_selected_key
        file=self.sources.get(key)
        return file if file is not None and file.is_file() else None

    def _available_selection_changed(self,listing,item):
        if item is None:return
        key=item.data(Qt.UserRole)
        if key not in self.sources:return
        other=(self.available_audio_files if listing is self.available_midi_files
               else self.available_midi_files)
        with QSignalBlocker(other):
            other.clearSelection()
            other.setCurrentRow(-1)
        if self.preview_selected_key==key:return
        self.preview_selected_key=key
        self._preview_selection_changed()

    def _preview_selection_changed(self):
        file=self._selected_preview_path()
        self.preview_file_label.setText(file.name if file else "Selecciona un archivo")
        self.preview_file_label.setToolTip(str(file) if file else "")
        new_key=(str(file) if file else None)
        if self.midi_live_preview.running and self.midi_live_preview.source!=file:
            self.midi_live_preview.stop()
        if self._preview_loaded_key!=new_key:
            self._cancel_preview_render()
            self.preview_engine.stop()
            self._preview_loaded_key=None
            self._preview_loaded_program=None
        self._refresh_file_preview()

    def _preview_program_label(self,key):
        program=self.preview_midi_programs.get(key)
        if program is None:return "Original"
        self._available_midi_instruments()
        for i in range(self.midi_instrument_select.count()):
            if self.midi_instrument_select.itemData(i)==program:
                return self.midi_instrument_select.itemText(i)
        return "Programa MIDI"

    def set_preview_midi_instrument(self,key,instrument):
        if key not in self.sources or self.sources[key].suffix.lower() not in MIDI:
            return False
        self._available_midi_instruments()
        if instrument is not None:
            try:instrument=(int(instrument[0]),int(instrument[1]))
            except (TypeError,IndexError,ValueError):return False
            if not any(self.midi_instrument_select.itemData(i)==instrument
                       for i in range(1,self.midi_instrument_select.count())):
                return False
        if instrument is None:self.preview_midi_programs.pop(key,None)
        else:self.preview_midi_programs[key]=instrument
        # ¡CAMBIO EN CALIENTE! No parar, no llamar load, no generar WAV:
        # FluidSynth conmuta programa y voces activas sobre el reloj vigente.
        if (self.midi_live_preview.running and
                str(self.midi_live_preview.source)==key):
            if not self.midi_live_preview.change_instrument(instrument):
                return False
        self._update_available_files()
        self.preview_status.setText(
            "Instrumento: "+self._preview_program_label(key)[:30])
        return True

    def preview_midi_snapshot(self):
        return {key:list(program) for key,program in self.preview_midi_programs.items()
                if key in self.sources and self.sources[key].suffix.lower() in MIDI}

    def restore_preview_midi_snapshot(self,data):
        if not isinstance(data,dict):return
        self._available_midi_instruments()
        valid={self.midi_instrument_select.itemData(i)
               for i in range(1,self.midi_instrument_select.count())}
        self.preview_midi_programs={}
        for key,program in data.items():
            try:
                path=Path(key).resolve()
                value=(int(program[0]),int(program[1]))
                if path.suffix.lower() in MIDI and path.is_file() and value in valid:
                    self.preview_midi_programs[str(path)]=value
            except (OSError,ValueError,IndexError,TypeError):pass
        self._update_available_files()

    def _midi_preview_context_menu(self,point):
        item=self.available_midi_files.itemAt(point)
        if item is None:return
        self.available_midi_files.setCurrentItem(item)
        key=item.data(Qt.UserRole)
        self._available_midi_instruments()
        menu=QMenu(self.available_midi_files)
        menu.setTitle("Instrumento del MIDI")
        original=menu.addAction("Original del MIDI")
        original.setData(None)
        menu.addSeparator()
        names=("Pianos","Percusión cromática","Órganos","Guitarras",
               "Bajos","Cuerdas","Ensamble","Metales","Lengüetas",
               "Flautas","Sintetizadores lead","Sintetizadores pad",
               "Efectos sintetizados","Étnicos","Percusión","Efectos")
        groups={}
        for i in range(1,self.midi_instrument_select.count()):
            program=self.midi_instrument_select.itemData(i)
            if not isinstance(program,(tuple,list)):continue
            bank,number=program
            title=(names[number//8] if bank==0 and number<128
                   else f"Banco {bank}")
            if title not in groups:groups[title]=menu.addMenu(title)
            action=groups[title].addAction(self.midi_instrument_select.itemText(i))
            action.setData(tuple(program))
        choice=menu.exec(self.available_midi_files.mapToGlobal(point))
        if choice is not None:
            self.set_preview_midi_instrument(key,choice.data())
        menu.deleteLater()

    def _cancel_preview_render(self):
        proc=self._preview_proc
        self._preview_proc=None
        self._preview_rendering=None
        if proc is None:return
        if proc.state()!=QProcess.NotRunning:
            proc.kill()
            proc.waitForFinished(350)
        proc.deleteLater()

    def _play_file_preview(self):
        file=self._selected_preview_path()
        if file is None:
            self.preview_status.setText("Elige audio o MIDI")
            return False
        key=str(file.resolve())
        if file.suffix.lower() in MIDI:
            # Permanent FluidSynth streaming replaces every offline FFmpeg
            # / FluidSynth WAV render in the mixer preview.
            self.preview_engine.stop()
            if (self.midi_live_preview.running
                    and self.midi_live_preview.source!=file):
                self.midi_live_preview.stop()
            program=self.preview_midi_programs.get(key)
            success=self.midi_live_preview.play(file,program)
            if success:
                self._preview_loaded_key=key
                self._preview_loaded_program=program
                self.preview_status.setText("Escuchando MIDI en tiempo real")
            else:
                self.preview_status.setText("No se pudo iniciar el MIDI")
            self._refresh_file_preview()
            return bool(success)
        if self.midi_live_preview.running:
            self.midi_live_preview.stop()
        self._cancel_preview_render()
        if self._preview_loaded_key!=key or self.preview_engine.current_file!=key:
            success=bool(self.preview_engine.load(file,autoplay=True))
            if success:
                self._preview_loaded_key=key
                self._preview_loaded_program=None
            return success
        if self.preview_engine._qt_active and not self.preview_engine._paused:
            return True
        self.preview_engine.play_pause()
        return True

    def _pause_file_preview(self):
        if self.midi_live_preview.running:
            self.midi_live_preview.pause()
            self._refresh_file_preview()
            return
        player=self.preview_engine
        if player._qt_active or player._play_process is not None:
            player.play_pause()
        elif player.current_file is not None and player._prepared is not None:
            player.play_pause()

    def _stop_file_preview(self):
        self._cancel_preview_render()
        self.midi_live_preview.stop()
        self.preview_engine.stop()
        self._refresh_file_preview()

    def _seek_file_preview(self):
        if self.midi_live_preview.running:
            ms=round(self.midi_live_preview.duration_ms*
                     self.preview_timeline.value()/1000)
            self.midi_live_preview.seek(ms)
            self._refresh_file_preview()
            return
        player=self.preview_engine
        if not player._duration_ms:return
        ms=round(player._duration_ms*self.preview_timeline.value()/1000)
        player.slider.setValue(ms)
        player.drag_finish()
        self._refresh_file_preview()

    def _preview_error(self,error):
        self.preview_status.setText("Error al escuchar")
        self.preview_status.setToolTip(str(error))

    def _refresh_file_preview(self):
        if not hasattr(self,"preview_engine"):return
        from preview_player import timecode
        player=self.preview_engine
        live=self.midi_live_preview
        midi_active=live.running
        playing=midi_active or bool(player._qt_active or player._play_process is not None)
        preparing=(player._render is not None or self._preview_proc is not None)
        source=self._selected_preview_path()
        duration=(live.duration_ms if midi_active else player._duration_ms)
        pos=(live.position_ms if midi_active else
             player._position() if player.current_file else 0)
        paused=(live.paused if midi_active else player._paused)
        self.preview_play.setEnabled(source is not None)
        self.preview_pause.setEnabled(playing)
        self.preview_stop.setEnabled(playing or preparing)
        self.preview_timeline.setEnabled(duration>0)
        self.preview_clock.setText(timecode(pos))
        if duration and not self.preview_timeline.isSliderDown():
            with QSignalBlocker(self.preview_timeline):
                self.preview_timeline.setValue(round(1000*pos/duration))
        if preparing:
            self.preview_status.setText("Preparando audio…")
        elif playing:
            self.preview_status.setText(
                "En pausa" if paused else
                "MIDI en tiempo real" if midi_active else "Escuchando archivo")
        elif source is None:
            self.preview_status.setText("Sin archivo")
        elif (self._preview_loaded_key==str(source)
              and player._prepared is not None):
            self.preview_status.setText("Preparado")
        else:
            self.preview_status.setText("Pulsa ▶ para escuchar")

    def _update_available_files(self):
        if not hasattr(self,"available_midi_files"):return
        previous=self.preview_selected_key
        ordered=sorted(self.sources.items(),key=lambda item:item[1].name.casefold())
        midi=[(key,path) for key,path in ordered if path.suffix.lower() in MIDI]
        audio=[(key,path) for key,path in ordered if path.suffix.lower() in AUDIO]
        for listing,files in ((self.available_midi_files,midi),
                              (self.available_audio_files,audio)):
            with QSignalBlocker(listing):
                listing.clear()
                selected=-1
                for i,(key,path) in enumerate(files):
                    if path.suffix.lower() in MIDI:
                        assigned=self.preview_midi_programs.get(key)
                        text=(path.name+(" · "+self._preview_program_label(key)
                                          if assigned is not None else ""))
                    else:
                        text=path.name
                    item=QListWidgetItem(text)
                    item.setData(Qt.UserRole,key)
                    item.setToolTip(str(path))
                    listing.addItem(item)
                    if key==previous:selected=i
                listing.setCurrentRow(selected)
        keys=set(self.sources)
        if previous not in keys:
            default=midi[0][0] if midi else audio[0][0] if audio else None
            self.preview_selected_key=default
            if default is not None:
                listing=(self.available_midi_files if default in dict(midi)
                         else self.available_audio_files)
                with QSignalBlocker(listing):listing.setCurrentRow(0)
            self._preview_selection_changed()
        self.available_count.setText(
            f"{len(midi)} MIDI · {len(audio)} audio · arrastra a un canal")
        self._refresh_file_preview()

    def _sync_channels(self,remember=True):
        # No sobrescribir con valores antiguos un preset recién cargado.
        if remember:
            for key,item in self.channels.items():
                self.control_state[key]=dict(item["strip"].controls)
                if item["source"] is not None:
                    self.checked_mutes[key]=item["strip"].mute.isChecked()
        plan=self._channel_plan()
        channel_signature=tuple((key,source,name) for key,source,name in plan)
        # Do not destroy/rebuild 16 complex strips and hundreds of GM items
        # when a periodic catalog refresh reports exactly the same channels.
        if remember and self._channel_render_signature==channel_signature:
            return
        self._channel_render_signature=channel_signature
        while self.channel_row.count():
            item=self.channel_row.takeAt(0)
            widget=item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        while self.midi_program_row.count():
            part=self.midi_program_row.takeAt(0)
            widget=part.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.midi_programs={}
        self.channels={}
        self.visible_strips=[]
        self._available_midi_instruments()
        for index,(key,source,name) in enumerate(plan):
            program=QComboBox(self.channel_root)
            program.setObjectName("mixerChannelMidiProgram")
            is_midi=bool(source and source in self.sources and
                         self.sources[source].suffix.lower() in MIDI)
            program.setEnabled(is_midi)
            program.setFixedHeight(23)
            program.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            program.setStyleSheet("""
              QComboBox#mixerChannelMidiProgram{
                color:#e8faff;background:#103047;border:1px solid #5689a0;
                border-radius:3px;min-height:19px;max-height:23px;
                padding:0px 9px 0px 1px;font-size:10px;font-weight:700;}
              QComboBox#mixerChannelMidiProgram:disabled{
                color:#506b7c;background:#0b2433;border:1px solid #28465a;}
              QComboBox#mixerChannelMidiProgram QAbstractItemView{
                color:#e7f8ff;background:#081f31;
                selection-background-color:#20799b;}
            """)
            program.addItem("—",None)
            # Context menu is attached to the exact CHANNEL selector. A
            # SoundFont loaded here is never shared with other strips.
            program.setContextMenuPolicy(Qt.CustomContextMenu)
            program.installEventFilter(self)
            program.customContextMenuRequested.connect(
                lambda point,ch=key,c=program:
                    self._midi_program_context_menu(ch,c,point))
            if is_midi:
                self._fill_midi_channel_programs(key,program)
                program.view().setMinimumWidth(220)
                program.currentIndexChanged.connect(
                    lambda i,ch=key,c=program:self._channel_program_selected(
                        ch,c.itemData(i)))
            else:
                program.setToolTip("Solo disponible si cargas un archivo MIDI en "+name)
            self.midi_program_row.addWidget(program,0)
            self.midi_programs[key]=program
            strip=ProChannelStrip(self,key,source,name,
                                  COLORS[index%len(COLORS)],index,self.channel_root)
            self.channel_row.addWidget(strip,0)
            self.channels[key]=dict(source=source,fader=strip.fader,
                     mute=strip.mute,solo=strip.solo,record=strip.arm,
                     strip=strip,meter=strip.meter)
            self.visible_strips.append(strip)
        self.midi_program_row.addStretch(0)
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
        QTimer.singleShot(0,self._schedule_selected_midi)

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
            combo=self.midi_programs.get(strip.key)
            if combo is not None:combo.setFixedWidth(desired)
        self.channel_root.setMinimumWidth(count*(desired+1)+3)
        self.channel_root.setMinimumHeight(0)
        self.file_list.setVisible(self.file_list.count()>0)
        self.inspector.setFixedHeight(115 if compact else 132)
        self.rack.setFixedHeight(140 if compact else 161)

    def eventFilter(self,watched,event):
        # macOS/QComboBox can consume the secondary mouse button before it
        # emits customContextMenuRequested. Catch the actual right-click at
        # the CHANNEL dropdown itself, not in a separate global selector.
        for channel,combo in self.midi_programs.items():
            if watched is combo:
                if (event.type()==QEvent.MouseButtonPress and
                        event.button()==Qt.RightButton):
                    self._midi_context_recent=(combo,time.monotonic())
                    if combo.isEnabled():
                        self._midi_program_context_menu(
                            channel,combo,event.position().toPoint())
                    self._midi_context_recent=(combo,time.monotonic())
                    event.accept()
                    return True
                if event.type()==QEvent.ContextMenu:
                    # Do not open a SECOND menu for the same native click.
                    recent=getattr(self,"_midi_context_recent",None)
                    if (recent is not None and recent[0] is combo and
                            time.monotonic()-recent[1]<1.):
                        event.accept()
                        return True
                break
        if watched is self.channel_scroll.viewport() and event.type()==QEvent.Resize:
            QTimer.singleShot(0,self._fit_strips)
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        # Esta vista profesional hereda lógica de catálogo de ProjectMixerView,
        # pero NO sus paneles gráficos (file_panel, channel_panel heredados).
        # Su resizeEvent antiguo accede a file_panel, inexistente aquí,
        # y en Cocoa la excepción interrumpe la ruta nativa de repintado.
        QWidget.resizeEvent(self,event)
        if not all(hasattr(self,name) for name in
                   ("channel_scroll","sidebar","sources_panel")):
            return
        self._fit_strips()
        self.sidebar.setFixedWidth(143 if self.width()<1200 else 171)
        self.sources_panel.setFixedWidth(155 if self.width()<1200 else 180)

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
                    key,element["strip"].controls)
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
        self._sync_midi_instrument_selector(key)
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

    def _available_midi_instruments(self):
        if self._midi_instruments_loaded:return
        from soundfont_catalog import system_soundfont
        from mixer_midi_instrument_choice import available_instruments
        card=getattr(self.home,"midi_to_audio",None)
        font=getattr(card,"soundfont",None) if card is not None else None
        if font is None or not Path(font).is_file():font=system_soundfont()
        if font is None:
            self.summary.setText("SoundFont GM no disponible para cambiar instrumentos.")
            return
        try:
            patches=available_instruments(font)
        except (OSError,ValueError,TypeError) as error:
            self.summary.setText("SoundFont MIDI: "+str(error)[:75])
            return
        with QSignalBlocker(self.midi_instrument_select):
            self.midi_instrument_select.clear()
            self.midi_instrument_select.addItem("Original del MIDI",None)
            for bank,program,name in patches:
                title=(f"{program+1:03d} · {name}" if bank==0
                       else f"{bank}:{program+1:03d} · {name}")
                self.midi_instrument_select.addItem(title,(bank,program))
                self.midi_instrument_select.setItemData(
                    self.midi_instrument_select.count()-1,
                    name+f" · Banco {bank} · Programa {program+1}",
                    Qt.ToolTipRole)
        self._midi_instruments_loaded=True

    def _channel_soundfont_path(self,channel):
        """Resolved SF2 used ONLY when synthesizing this channel's MIDI."""
        override=self._midi_soundfonts.get(channel)
        if override is not None:return Path(override)
        from soundfont_catalog import system_soundfont
        card=getattr(self.home,"midi_to_audio",None)
        current=getattr(card,"soundfont",None) if card is not None else None
        if current and Path(current).is_file():return Path(current).resolve()
        return system_soundfont()

    def _channel_available_instruments(self,channel):
        from mixer_midi_instrument_choice import available_instruments
        font=self._channel_soundfont_path(channel)
        if font is None or not Path(font).is_file():return ()
        return available_instruments(font)

    def _fill_midi_channel_programs(self,channel,combo):
        """Rebuild on bank CHANGE only; avoid expensive repeated Qt items."""
        font=self._channel_soundfont_path(channel)
        signature=str(font) if font is not None else ""
        source=self.channels.get(channel,{}).get("source")
        if source is not None and source not in self.sources:
            return
        if combo.property("mixerFontSignature")!=signature:
            with QSignalBlocker(combo):
                combo.clear()
                combo.addItem("Original",None)
                custom=channel in self._midi_soundfonts
                if custom:
                    choices=self._channel_available_instruments(channel)
                    for bank,program,name in choices:
                        title=(f"{program+1:03d} · {name}" if bank==0
                               else f"{bank}:{program+1:03d} · {name}")
                        combo.addItem(title,(bank,program))
                        combo.setItemData(
                            combo.count()-1,
                            name+f" · Banco {bank} · Programa {program+1}",
                            Qt.ToolTipRole)
                else:
                    self._available_midi_instruments()
                    for index in range(1,self.midi_instrument_select.count()):
                        title=self.midi_instrument_select.itemText(index)
                        combo.addItem(title,
                                      self.midi_instrument_select.itemData(index))
                        combo.setItemData(combo.count()-1,title,Qt.ToolTipRole)
                combo.setProperty("mixerFontSignature",signature)
        desired=self._midi_instrument_overrides.get(channel)
        index=next((i for i in range(combo.count())
                    if combo.itemData(i)==desired),0)
        with QSignalBlocker(combo):
            combo.setCurrentIndex(index)
        bank_name=(Path(font).name if font is not None else "Sin SoundFont")
        combo.setToolTip("Canal "+channel+" · "+bank_name+
                         " · "+combo.itemText(index)+
                         " · clic derecho: cargar banco SF2 exclusivo")

    def set_channel_soundfont(self,channel,path,rerender=True):
        """Assign a real SF2 only to this channel; keep all others intact.

        Custom SF2 dropdown lists only melodic presets actually in that file.
        Original MIDI is never rewritten or moved. If the bank changes, audio
        is rendered again and replaced only when the output is complete.
        """
        source=self.channels.get(channel,{}).get("source")
        if not source or source not in self.sources or (
                self.sources[source].suffix.lower() not in MIDI):
            return False
        bank=None
        choices=()
        if path is not None:
            try:
                requested=Path(path).expanduser()
                if (requested.suffix.lower()!=".sf2" or
                        not requested.is_file()):
                    return False
                bank=requested.resolve()
                from mixer_midi_instrument_choice import available_instruments
                choices=available_instruments(bank)
                if not choices:return False
            except (OSError,ValueError,TypeError,EOFError):
                return False
        previous=self._midi_soundfonts.get(channel)
        if previous==bank:return True
        # Atomic, logical-strip-local change; no global SF2 mutation.
        if bank is None:self._midi_soundfonts.pop(channel,None)
        else:self._midi_soundfonts[channel]=bank
        if bank is not None:
            desired=self._midi_instrument_overrides.get(channel)
            valid={(b,p) for b,p,_ in choices}
            if desired not in valid:
                self._midi_instrument_overrides[channel]=tuple(choices[0][:2])
        else:
            self._midi_instrument_overrides[channel]=None
        self._midi_render_versions[channel]=(
            self._midi_render_versions.get(channel,0)+1)
        self._sync_midi_instrument_selector(channel)
        if rerender:
            self._request_channel_midi_render(channel)
        self.summary.setText(
            ("Banco SoundFont para "+channel+" · "+
             (bank.name if bank is not None else "General MIDI")))
        return True

    def _request_channel_midi_render(self,channel):
        if not self._midi_render_key_active(channel):
            return
        if channel not in self._render_queue and self._rendering!=channel:
            self._render_queue.append(channel)
        self._next_midi()

    def _midi_program_context_menu(self,channel,combo,point):
        """Right-click only on this channel's MIDI instrument dropdown."""
        if not combo.isEnabled() or channel not in self.channels:
            return
        menu=QMenu(combo)
        load=menu.addAction("Cargar SoundFont SF2 para este canal…")
        restore=menu.addAction("Restaurar banco GM de este canal")
        restore.setEnabled(channel in self._midi_soundfonts)
        chosen=menu.exec(combo.mapToGlobal(point))
        if chosen is None:return
        if chosen is load:
            initial=self._midi_soundfonts.get(channel)
            directory=(str(Path(initial).parent) if initial is not None
                       else str(Path.home()))
            filename,_=QFileDialog.getOpenFileName(
                self,"SoundFont SF2 · canal "+channel,
                directory,"Bancos SoundFont (*.sf2)")
            if not filename:return
            if not self.set_channel_soundfont(channel,filename):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self,"SoundFont",
                    "El banco SF2 no se ha podido cargar o no contiene "
                    "instrumentos melódicos válidos.")
        elif chosen is restore:
            self.set_channel_soundfont(channel,None)

    def _sync_midi_instrument_selector(self,channel):
        # Sin casillas, títulos ni selector global. Solo el del canal.
        combo=self.midi_programs.get(channel)
        if combo is None:return
        source=self.channels.get(channel,{}).get("source")
        is_midi=bool(source and source in self.sources and
                     self.sources[source].suffix.lower() in MIDI)
        combo.setEnabled(is_midi)
        if not is_midi:return
        self._fill_midi_channel_programs(channel,combo)

    def _channel_program_selected(self,channel,program):
        self.set_midi_instrument(channel,program)
        self._sync_midi_instrument_selector(channel)

    def set_midi_instrument(self,channel,instrument):
        """Cambiar la voz SOLO de este MIDI; no cambiar sus notas ni buses."""
        source=self.channels.get(channel,{}).get("source")
        if not source or source not in self.sources:
            return False
        if self.sources[source].suffix.lower() not in MIDI:
            return False
        if instrument is not None:
            try:instrument=(int(instrument[0]),int(instrument[1]))
            except (TypeError,ValueError,IndexError):return False
            if instrument not in {
                    (b,p) for b,p,_ in self._channel_available_instruments(channel)}:
                return False
        if self._midi_instrument_overrides.get(channel)==instrument:
            return True
        self._midi_instrument_overrides[channel]=instrument
        self._midi_render_versions[channel]=self._midi_render_versions.get(channel,0)+1
        # No borrar el sonido vigente: cambiar cuando exista nuevo WAV completo.
        if channel not in self._render_queue and self._rendering!=channel:
            self._render_queue.append(channel)
        self._next_midi()
        self._sync_midi_instrument_selector(channel)
        self.summary.setText("Preparando nuevo instrumento MIDI · "+channel)
        return True

    def midi_soundfont_snapshot(self):
        """Project-local SF2 references; no SoundFont data or MIDI copied."""
        return {channel:str(path) for channel,path in self._midi_soundfonts.items()
                if channel in self.channels and Path(path).is_file()}

    def apply_midi_soundfonts(self,data):
        """Restore bank choices BEFORE restoring this channel's program."""
        if not isinstance(data,dict):return
        for channel,path in data.items():
            if channel not in self.channels or not isinstance(path,str):
                continue
            # Files that no longer exist cannot be loaded. Keep default GM.
            if Path(path).is_file():
                self.set_channel_soundfont(channel,path,rerender=False)

    def midi_instrument_snapshot(self):
        """Guardar programa o estado Original por canal, sin rutas privadas."""
        result={}
        for channel,entry in self.channels.items():
            source=entry.get("source")
            if not source or source not in self.sources:
                continue
            if self.sources[source].suffix.lower() not in MIDI:
                continue
            program=self._midi_instrument_overrides.get(channel)
            result[channel]=list(program) if program is not None else None
        return result

    def apply_midi_instruments(self,data):
        if not isinstance(data,dict):return
        for channel,program in data.items():
            if channel in self.channels and (program is None
                                           or isinstance(program,(list,tuple))):
                self.set_midi_instrument(channel,program)
        # Restored banks may already match their first preset, so no
        # currentIndexChanged signal occurs. Still synthesize their SF2
        # and do not keep an earlier GM WAV accidentally.
        for channel in self._midi_soundfonts:
            if channel in self.channels and self._midi_render_key_active(channel):
                self._request_channel_midi_render(channel)

    def _on_midi_render_completed(self,key,old_audio,new_audio):
        self._midi_applied_instruments[key]=(
            self._midi_instrument_overrides.get(key))
        self._midi_applied_soundfonts[key]=self._midi_soundfonts.get(key)
        # No reemplazar a mitad de conversión: el motor recibe el WAV
        # completo y reanuda desde la posición que ya estaba sonando.
        if not old_audio or self.transport is None:return
        live=self.transport.live
        if not live.running or key not in live._names:return
        position=live.position()
        paused=live.paused
        inputs=self.paths_for_mix()
        if live.start(inputs,{channel for channel,_ in inputs},start_ms=position):
            self._apply_live_controls()
            if paused:live.pause()
            self.summary.setText("Instrumento MIDI aplicado · reproducción sincronizada")
        else:
            self.summary.setText("Instrumento renderizado · pulsa Play para escuchar")

    def _on_midi_render_failed(self,key,reason):
        """Si ya existía audio válido, conservarlo ante un render fallido."""
        if key not in self._audio_cache:return False
        self._midi_instrument_overrides[key]=(
            self._midi_applied_instruments.get(key))
        previous_font=self._midi_applied_soundfonts.get(key)
        if previous_font is None:self._midi_soundfonts.pop(key,None)
        else:self._midi_soundfonts[key]=previous_font
        self.summary.setText("Cambio MIDI fallido; sonido anterior conservado: "
                             +str(reason)[:70])
        self._sync_midi_instrument_selector(key)
        return True

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
            self.transport.live.configure_channel(key,{param:value})
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
        # Respectar desmarcar: no reasignar automáticamente hasta que
        # se genere un archivo nuevo o el usuario vuelva a marcarlo.
        key=item.data(Qt.UserRole)
        if item.checkState()!=Qt.Checked and key in self.selected:
            for channel,manual in list(self.manual_assignments.items()):
                if manual==key:self.manual_assignments.pop(channel,None)
        super()._check_source(item)
        self._update_available_files()

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
        identity=self._project_identity()
        if identity!=self._project_key:
            self._project_key=identity
            self._midi_instrument_overrides.clear()
            self._midi_applied_instruments.clear()
            self._midi_soundfonts.clear()
            self._midi_applied_soundfonts.clear()
            self._midi_render_versions.clear()
            self._cancel_preview_render()
            self.midi_live_preview.stop()
            self.preview_engine.clear()
            self.preview_midi_programs.clear()
            self.preview_selected_key=None
            self._preview_loaded_key=None
            self._preview_loaded_program=None
            self._preview_cache.clear()
            if getattr(self,"_preview_temp",None) is not None:
                self._preview_temp.cleanup()
            self._preview_temp=tempfile.TemporaryDirectory(
                prefix="stemmidi_mixer_preview_")
            self._known_auto_files.clear()
            self.manual_assignments.clear()
            self.manual_sources.clear()
        catalog=self._catalog()
        new=set(catalog)-self._known_auto_files
        for key in sorted(new):
            if self._default_family(catalog[key]) is not None:
                self.selected.add(key)
        self._known_auto_files.update(catalog)
        old_signature=self._signature
        super().refresh_catalog(force)
        if force or self._signature!=old_signature:
            self._update_available_files()
            self._sync_wave_sources()

    def save_project_preset(self):
        """Single project save; no second mezcla.json or bus sidecar."""
        from studio_shell import save_project
        if save_project(self.home.main,show_confirmation=False):
            self.summary.setText("Consola y buses guardados en el proyecto.")

    def load_project_preset(self):
        """Reload the console from the same existing project manifest."""
        project=getattr(self.home.main,"project_path",None)
        if not project or not Path(project).is_file():
            self.summary.setText("Este proyecto aún no tiene estado guardado.")
            return
        try:
            from console_project_state import restore as restore_console,legacy_snapshot
            saved=json.loads(Path(project).read_text(encoding="utf-8"))
            data=saved.get("parameters_console_pro")
            if not isinstance(data,dict):
                data=legacy_snapshot(Path(project).parent)
            if not restore_console(self.home.main,data):
                raise ValueError("No hay parámetros de consola en este proyecto")
            self.summary.setText("Consola y BUS recuperados del proyecto.")
        except (OSError,ValueError,TypeError) as exc:
            self.summary.setText("No se pudo cargar: "+str(exc)[:45])

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
        # Conservar el único editor y el candado de la ventana original.
        # Si ya flota, este mismo botón debe devolverlo a la pestaña.
        try:
            manager=self.home._floating_manager
            card=self.home.mix_card
            if manager.is_detached(card):
                manager.redock(card)
            else:
                manager.detach(card)
        except (AttributeError,RuntimeError) as error:
            self.summary.setText(
                "No se pudo cambiar la ventana flotante: "+str(error)[:72])

    def update_meters(self,peaks,master,buses,position):
        for channel,entry in self.channels.items():
            source=entry["source"]
            pair=peaks.get(channel,(0.,0.)) if source else (0.,0.)
            entry["meter"].set_peaks(*pair)
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

    def cleanup(self):
        if hasattr(self,"preview_timer"):self.preview_timer.stop()
        self._cancel_preview_render()
        if hasattr(self,"midi_live_preview"):self.midi_live_preview.cleanup()
        if hasattr(self,"preview_engine"):self.preview_engine.cleanup()
        if getattr(self,"_preview_temp",None) is not None:
            self._preview_temp.cleanup()
            self._preview_temp=None
        super().cleanup()

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
        # En el groove, el clic debe saltar a la posición exacta.
        self.timeline.installEventFilter(self)
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
        self.track_meters={key:(key,data["meter"])
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

    def eventFilter(self, watched, event):
        if watched is self.timeline and event.type()==QEvent.MouseButtonPress:
            if event.button()==Qt.LeftButton and self.live.running:
                from PySide6.QtWidgets import QStyle,QStyleOptionSlider
                option=QStyleOptionSlider()
                self.timeline.initStyleOption(option)
                groove=self.timeline.style().subControlRect(
                    QStyle.CC_Slider,option,QStyle.SC_SliderGroove,self.timeline)
                handle=self.timeline.style().subControlRect(
                    QStyle.CC_Slider,option,QStyle.SC_SliderHandle,self.timeline)
                if not handle.contains(event.position().toPoint()):
                    span=max(1,groove.width()-handle.width())
                    offset=event.position().x()-groove.left()-handle.width()/2
                    value=round(1000*max(0,min(span,offset))/span)
                    self.timeline.setValue(value)
                    self.seek()
                    return True
        return QFrame.eventFilter(self,watched,event)

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
            native=self.live._stream
            if native is not None and hasattr(native,"underruns"):
                self.live.output_xruns=native.underruns
            faults=(self.live.underruns+self.live.output_xruns+
                    self.live.callback_overruns+self.live.callback_errors)
            self.status.setText(
                f"DSP {self.live.last_callback_ms:.1f} ms · XRUN {faults}")
            self.status.setToolTip(
                f"PCM {self.live.blocks} bloques | Cola {self.live._queue.qsize()}/{24}"
                f" | Underflows {self.live.underruns}"
                f" | CoreAudio {self.live.output_xruns}"
                f" | DSP fuera de plazo {self.live.callback_overruns}"
                f" | Excepciones {self.live.callback_errors}"
                f" | Pico callback {self.live.max_callback_ms:.2f} ms"
                f" | Último error {self.live.last_callback_error}"
                f" | Motor {'C++ CoreAudio' if native is not None and hasattr(native,'buffered_frames') else 'PortAudio/Python'}"
                f" | Buffer salida {round(1000*native.buffered_frames/48000,1) if native is not None and hasattr(native,'buffered_frames') else 'N/D'} ms"
                f" | Buffer dispositivo estimado {round(native.device_latency_estimate_ms,1) if native is not None and hasattr(native,'device_latency_estimate_ms') else 'N/D'} ms"
                f" | Fallo motor nativo {self.live.native_output_error}")
        elif self.live.paused:
            self.status.setText("Pausado")
        elif not self.live.running and not self._notice:
            self.status.setText(f"{len(self.view.selected)} pistas seleccionadas")

