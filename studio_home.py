"""Pantalla Inicio de StemMIDI Studio, vinculada a los motores y tareas reales.

Los gráficos representan únicamente datos cargados de archivos reales o
datos medidos por el monitor, nunca sonidos o resultados simulados.
"""
from __future__ import annotations
import file_dialogs
import json, math, struct, subprocess, os
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF, QProcess, QTimer, Signal
from PySide6.QtGui import (
    QColor, QBrush, QPen, QPainter, QFont, QLinearGradient, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QPushButton, QCheckBox, QSlider, QDial, QSpinBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QStackedWidget, QSizePolicy, QAbstractItemView,
    QMessageBox, QFileDialog
)

AUDIO={".wav",".mp3",".flac",".ogg",".m4a",".aac",".wma",".aif",".aiff"}
MIDI={".mid",".midi",".kar"}
CYAN="#24d9f5"
BLUE="#138be9"
DIM="#8bb9d4"
ROOT=Path(__file__).resolve().parent
COLORS={"Voces":"#2087f7","Batería":"#fd505b","Bajo":"#23dd78",
        "Guitarra":"#f89532","Piano":"#ba56fa","Viento":"#46cacc",
        "Otros":"#ffe262"}

def Qc(text):return QColor(text)

def label(text,object_name=None,muted=False):
    w=QLabel(text)
    if object_name:w.setObjectName(object_name)
    elif muted:w.setObjectName("muted")
    return w

def action(text,slot,primary=False):
    b=QPushButton(text)
    if primary:b.setObjectName("primary")
    b.clicked.connect(slot)
    return b

def padded_row(*items,spacing=7):
    row=QHBoxLayout()
    row.setContentsMargins(0,0,0,0)
    row.setSpacing(spacing)
    for value in items:
        if isinstance(value,int):row.addStretch(value)
        else:row.addWidget(value)
    return row

def form_row(name,control,minimum=95):
    row=QHBoxLayout()
    title=label(name)
    title.setMinimumWidth(minimum)
    title.setObjectName("homeLabel")
    row.addWidget(title)
    row.addWidget(control,1)
    return row

class Card(QFrame):
    def __init__(self,title,parent=None):
        super().__init__(parent)
        self.setObjectName("studioCard")
        lay=QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(0)
        self.header=QPushButton(title.split("  ",1)[-1])
        self.header.setObjectName("studioCardHeading")
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QSize
        folder=ROOT/"assets"
        match=("record" if "Monitor" in title else
               "layers" if "Separación" in title or "Pistas separadas" in title else
               "note" if "Audio a MIDI" in title else
               "folder" if "Resultados" in title else
               "wave" if "Vista de audio" in title else
               "mixer" if "Mezclador" in title else
               "piano" if "Piano Roll" in title else "info")
        self.header.setIcon(QIcon(str(folder/f"ui_{match}.svg")))
        self.header.setIconSize(QSize(22,22))
        self.header.setMinimumHeight(26)
        heading_row=QHBoxLayout()
        heading_row.setSpacing(0)
        heading_row.setContentsMargins(0,0,0,0)
        heading_row.addWidget(self.header,1)
        self.help_button=QPushButton("?",self)
        self.help_button.setObjectName("cardHelpButton")
        self.help_button.setFixedSize(28,34)
        self.help_button.setToolTip("Abrir ayuda de esta sección")
        heading_row.addWidget(self.help_button)
        lay.addLayout(heading_row)
        self.body=QWidget()
        self.inner=QVBoxLayout(self.body)
        self.inner.setContentsMargins(12,7,12,7)
        self.inner.setSpacing(4)
        lay.addWidget(self.body,1)

class BalanceDial(QDial):
    """Dial estéreo de balance con recorrido visual de izquierda a derecha."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setRange(-100,100)
        self.setValue(0)
        self.setSingleStep(2)
        self.setPageStep(10)
        self.setWrapping(False)
        self.setNotchesVisible(False)
        self.setFixedSize(57,57)
        self.setToolTip("Balance de grabación: izquierda / centro / derecha. "
                        "No altera el volumen del sistema.")
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.setValue(0)
            event.accept()
        else:super().mouseDoubleClickEvent(event)
    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        center=QPointF(self.width()/2,self.height()/2)
        radius=22.0
        p.setBrush(QBrush(Qc("#07182a")))
        p.setPen(QPen(Qc("#285575"),1.4))
        p.drawEllipse(center,radius,radius)
        for tick in (-100,-50,0,50,100):
            angle=math.radians(-135+270*(tick+100)/200)
            # 0 (centro) en posición superior.
            a=QPointF(center.x()+25*math.sin(angle),
                      center.y()-25*math.cos(angle))
            b=QPointF(center.x()+28*math.sin(angle),
                      center.y()-28*math.cos(angle))
            p.setPen(QPen(Qc("#28d7f6" if tick==0 else "#5987a6"),1.6))
            p.drawLine(a,b)
        inner=QRectF(center.x()-16,center.y()-16,32,32)
        grad=QLinearGradient(inner.topLeft(),inner.bottomRight())
        grad.setColorAt(0,Qc("#3c7195"))
        grad.setColorAt(.55,Qc("#183d5c"))
        grad.setColorAt(1,Qc("#0b243b"))
        p.setPen(QPen(Qc("#6ca4bc"),1))
        p.setBrush(QBrush(grad))
        p.drawEllipse(inner)
        angle=math.radians(-135+270*(self.value()+100)/200)
        end=QPointF(center.x()+12*math.sin(angle),
                    center.y()-12*math.cos(angle))
        p.setPen(QPen(Qc("#49dcf6"),3,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(center,end)
        p.end()

class BrandLogo(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFixedSize(198,137)
        from PySide6.QtSvg import QSvgRenderer
        self.renderer=QSvgRenderer(str(ROOT/"assets"/"stemmidi_icon.svg"))
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.renderer.isValid():
            self.renderer.render(painter,QRectF(0,0,self.width(),self.height()))
        painter.end()

class WaveCanvas(QWidget):
    """La envolvente dibujada procede de muestras decodificadas con ffmpeg."""
    clicked=Signal(float)
    def __init__(self,small=False,parent=None):
        super().__init__(parent)
        self.small=small
        self.data=[]
        self.wave_color="#23c3ff"
        self.source=None
        self.processor=None
        self._wanted=None
        self.cursor=0.
        self.selection=0.
        self.selection_start=0.
        self.zoom_factor=1
        self.view_start=0.
        self.duration_seconds=0.
        self._normalizer=.5
        self.setMinimumHeight(23 if small else 96)
        self.setToolTip("Forma de onda real. Haz clic para situar el cursor.")
        from PySide6.QtWidgets import QApplication
        instance=QApplication.instance()
        if instance:
            instance.aboutToQuit.connect(self.cancel_decode)
    def set_file(self,path):
        candidate=Path(path).resolve() if path else None
        if candidate==self.source:return
        self.source=candidate
        self.data=[]
        self.duration_seconds=0.
        self.update()
        if self.processor is not None:
            self.cancel_decode()
        if candidate is None or not candidate.is_file() or candidate.suffix.lower() not in AUDIO:return
        process=QProcess(self)
        process.setProgram("ffmpeg")
        process.setArguments(["-nostdin","-hide_banner","-v","error","-i",str(candidate),
            "-map","0:a:0","-vn","-ac","1","-ar","320","-f","f32le","pipe:1"])
        process.finished.connect(lambda rc,status,p=process,c=candidate:self._finished(p,c,rc))
        self.processor=process
        process.start()
    def cancel_decode(self):
        proc=self.processor
        self.processor=None
        if proc is None:return
        try:
            proc.blockSignals(True)
            if proc.state()!=QProcess.NotRunning:
                proc.kill()
                proc.waitForFinished(2000)
            proc.deleteLater()
        except RuntimeError:
            pass

    def _finished(self,proc,candidate,rc):
        if proc is not self.processor or candidate!=self.source:return
        try:
            data=bytes(proc.readAllStandardOutput())
        except RuntimeError:
            self.processor=None
            return
        if rc==0 and len(data)>=4:
            size=len(data)//4
            # Evitar procesar millones de puntos en cada repintado.
            step=max(1,size//5000)
            self.data=[abs(x[0]) for x in struct.iter_unpack("<f",data[:size*4])][::step]
            self.duration_seconds=size/320.0
        self.processor=None
        try:proc.deleteLater()
        except RuntimeError:pass
        self.update()
    def set_cursor(self,fraction):
        self.cursor=max(0.,min(1.,float(fraction)))
        self.update()
    def set_zoom(self,value):
        self.zoom_factor=max(1,int(value))
        self.view_start=max(0.,min(1-1/self.zoom_factor,self.view_start))
        self.update()
    def set_view_start(self,fraction):
        self.view_start=max(0.,min(1-1/self.zoom_factor,float(fraction)))
        self.update()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            fx=max(0.,min(1.,event.position().x()/max(1,self.width())))
            fraction=fx if self.small else self.view_start+fx/self.zoom_factor
            self.set_cursor(fraction)
            self.clicked.emit(fraction)
    def wheelEvent(self,event):
        if event.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom_factor+(1 if event.angleDelta().y()>0 else -1))
        elif event.modifiers() & Qt.ShiftModifier:
            self.set_view_start(self.view_start-event.angleDelta().y()/120*
                                (.05/self.zoom_factor))
        self.update()
        event.accept()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing,False)
        w=max(1,self.width());h=max(1,self.height())
        p.fillRect(self.rect(),Qc("#061528"))
        if not self.small:
            p.fillRect(QRectF(0,0,w,18),Qc("#09223b"))
            p.setPen(QPen(Qc("#254660"),1))
            for i in range(13):
                x=round(i*w/12)
                p.drawLine(x,18,x,h)
                if self.duration_seconds:
                    frac=self.view_start+i/(12*self.zoom_factor)
                    sec=frac*self.duration_seconds
                    p.setPen(Qc("#b5d8e8"))
                    p.drawText(x+2,13,f"{int(sec//60)}:{int(sec%60):02d}")
                    p.setPen(QPen(Qc("#254660"),1))
            for i in range(1,5):
                y=round(18+i*(h-18)/5)
                p.drawLine(0,y,w,y)
        if self.data:
            waveform=Qc(self.wave_color)
            p.setPen(QPen(waveform,1.3 if not self.small else 1))
            chunk=max(1,len(self.data)//w)
            middle=h*.53
            scale=h*(.40 if not self.small else .37)
            # Envolvente normalizada por percentil alto. Una grabación
            # silenciosa debe tener un dibujo legible, no un hilo plano.
            peak=sorted(self.data)[min(len(self.data)-1,
                     int(len(self.data)*.98))] if self.data else 1.
            peak=max(0.001,peak)
            self._normalizer=peak
            first=int(self.view_start*len(self.data)) if not self.small else 0
            span=max(1,int(len(self.data)/self.zoom_factor)) if not self.small else len(self.data)
            window=self.data[first:min(len(self.data),first+span)]
            for x in range(w):
                i=x*len(window)//w
                stop=min(len(window),i+max(1,len(window)//w))
                sample=max(window[i:stop] or [0])
                extent=min(scale,max(0.,(sample/peak)**.78*scale))
                p.drawLine(x,int(middle-extent),x,int(middle+extent))
                if not self.small and extent>2:
                    p.setPen(QPen(Qc("#7bdfff"),.7))
                    p.drawLine(x,int(middle-extent*.83),x,int(middle-extent))
                    p.setPen(QPen(waveform,1.3))
        elif not self.small:
            p.setPen(Qc("#7099b0"))
            p.drawText(self.rect(),Qt.AlignCenter,"Selecciona un audio para ver su forma de onda")
        if self.small and self.selection>0 and self.data:
            xx=int(self.selection_start*w)
            ww=max(8,int(self.selection*w))
            p.fillRect(QRectF(xx,0,ww,h),QColor(14,150,237,35))
            p.setPen(QPen(Qc("#cceaff"),1.5))
            p.drawRect(QRectF(xx+1,1,min(ww,w-xx)-2,h-2))
        if not self.small:
            cursor=(self.cursor-self.view_start)*self.zoom_factor
            if 0<=cursor<=1:
                x=int(cursor*w)
                p.setPen(QPen(Qc("#ff4f5c"),2))
                p.drawLine(x,0,x,h)
                p.setBrush(Qc("#ff5d65"));p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(x,5),4,4)
        p.end()

class VerticalMeter(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.levels=[0.,0.]
        self.setFixedWidth(39)
        self.setMinimumHeight(111)
    def set_levels(self,left,right):
        self.levels=[max(0.,min(1.,float(left)*3)),max(0.,min(1.,float(right)*3))]
        self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),Qc("#04121d"))
        h=max(1,self.height()-14)
        for c,level in enumerate(self.levels):
            x=7+c*14
            for j in range(24):
                yf=int(7+(23-j)*h/24)
                is_on=(j/24)<level
                col=("#40e985" if j<15 else "#d0e82e" if j<21 else "#ff4d50") if is_on else "#19313c"
                p.fillRect(x,yf,10,max(2,int(h/26)),Qc(col))
        p.end()

class StemMeter(QWidget):
    """Nivel estimado a partir de muestras reales de la pista en el cursor."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.level=0.
        self.setFixedWidth(11)
        self.setMinimumHeight(90)
        self.setToolTip("Nivel estimado de la pista en el instante de reproducción; no es VU de entrada.")
    def set_level(self,value):
        value=max(0.,min(1.,float(value)))
        if abs(value-self.level)>.01:
            self.level=value
            self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),Qc("#031629"))
        height=max(1,self.height()-6)
        for idx in range(18):
            filled=(idx/18)<self.level
            color=("#1cd976" if idx<12 else "#fae343" if idx<16 else "#ff5065") if filled else "#103343"
            y=3+(17-idx)*height/18
            p.fillRect(1,int(y),9,max(2,int(height/20)),Qc(color))
        p.end()

class PianoOverview(QWidget):
    """Vista MIDI real: doce compases visibles y desplazamiento, sin miniaturizarlo entero."""
    activated=Signal(float)
    viewChanged=Signal(float)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumHeight(126)
        self.events=[]
        self.full_tick=1
        self.visible_ticks=48*480
        self.ticks_per_beat=480
        self.view_start=0
        self.max_tick=1
        self.cursor=0.
        self.pitch_lo=48
        self.pitch_hi=84
        self.setMouseTracking(True)
        self.setToolTip("Notas MIDI auténticas · Ctrl+rueda: zoom · Mayús+rueda: avanzar compases.")

    def set_midi(self,path):
        self.events=[]
        self.full_tick=1
        self.view_start=0
        self.cursor=0.
        self.pitch_lo=48
        self.pitch_hi=84
        if not path or not Path(path).is_file():
            self.update()
            return
        try:
            from piano_roll import parse_file
            midi,tracks=parse_file(path)
            events=[n for tr in tracks for n in tr["notes"]]
            self.ticks_per_beat=midi.ticks_per_beat
            self.visible_ticks=midi.ticks_per_beat*48
            self.events=events[:40000]
            self.full_tick=max([self.visible_ticks]+[n["end"] for n in events])
            self.max_tick=self.full_tick
            if events:
                # Tomar el registro principalmente de las notas de los
                # primeros compases: evita una franja muy fina e ilegible.
                first=[n["pitch"] for n in events if n["start"]<self.visible_ticks]
                first=sorted(first or [n["pitch"] for n in events])
                lo=first[int(len(first)*.08)]
                hi=first[min(len(first)-1,int(len(first)*.92))]
                center=(lo+hi)//2
                span=max(18,min(27,hi-lo+6))
                self.pitch_lo=max(21,min(108-span,center-span//2))
                self.pitch_hi=self.pitch_lo+span
        except (ValueError,OSError) as exc:
            self.setToolTip("No se pudo dibujar MIDI: "+str(exc)[:150])
        self.update()

    def set_scroll(self,fraction):
        limit=max(0,self.full_tick-self.visible_ticks)
        self.view_start=int(max(0.,min(1.,fraction))*limit)
        self.viewChanged.emit(float(self.view_start/max(1,limit)))
        self.update()

    def zoom(self,factor):
        factor=float(max(0.35,min(4.,factor)))
        previous=int(self.visible_ticks)
        self.visible_ticks=max(4*self.ticks_per_beat,int(48*self.ticks_per_beat/factor))
        self.visible_ticks=min(self.full_tick,self.visible_ticks)
        self.view_start=max(0,min(self.full_tick-self.visible_ticks,
            self.view_start+(previous-self.visible_ticks)//2))
        self.update()

    def wheelEvent(self,event):
        if event.modifiers() & Qt.ControlModifier:
            factor=48*self.ticks_per_beat/self.visible_ticks
            self.zoom(factor*(1.18 if event.angleDelta().y()>0 else 1/1.18))
        elif event.modifiers() & Qt.ShiftModifier:
            limit=max(0,self.full_tick-self.visible_ticks)
            self.view_start=max(0,min(limit,
                self.view_start-(2*self.ticks_per_beat*int(event.angleDelta().y()/120))))
            self.viewChanged.emit(float(self.view_start/max(1,limit)))
            self.update()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            fraction=max(0,min(1,(event.position().x()-47)/max(1,self.width()-47)))
            self.cursor=fraction
            self.activated.emit(fraction)
            self.update()
        else:super().mousePressEvent(event)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing,True)
        w=max(80,self.width());h=max(60,self.height())
        p.fillRect(self.rect(),Qc("#061529"))
        left=62;top=28
        note_rows=max(1,self.pitch_hi-self.pitch_lo+1)
        row_h=(h-top)/note_rows
        def pos(note):return top+(self.pitch_hi-note)*row_h
        def time_x(tick):return left+(tick-self.view_start)/self.visible_ticks*(w-left)
        # Franja de compases azul oscuro, encabezados exactos.
        p.fillRect(QRectF(left,0,w-left,top),Qc("#082038"))
        start_bar=max(0,self.view_start//(self.ticks_per_beat*4))
        visible_bars=math.ceil(self.visible_ticks/(self.ticks_per_beat*4))+2
        for bar in range(start_bar,start_bar+visible_bars):
            tick=bar*self.ticks_per_beat*4
            x=time_x(tick)
            if x<left-10 or x>w+2:continue
            p.setPen(QPen(Qc("#36638a"),1))
            p.drawLine(QPointF(x,0),QPointF(x,h))
            p.setPen(Qc("#d1edff"))
            p.drawText(QRectF(x+5,1,38,17),str(bar+1))
            for sub in range(1,4):
                sx=time_x(tick+sub*self.ticks_per_beat)
                if left<=sx<=w:
                    p.setPen(QPen(Qc("#153957"),1))
                    p.drawLine(QPointF(sx,top),QPointF(sx,h))
        # Clavijas y fondo del teclado piano como la maqueta.
        for note in range(self.pitch_lo,self.pitch_hi+1):
            y=pos(note)
            black=note%12 in (1,3,6,8,10)
            p.fillRect(QRectF(0,y,left-1,row_h+.2),
                       Qc("#253c51" if black else "#eff4f7"))
            p.setPen(QPen(Qc("#899caa"),.5))
            p.drawLine(QPointF(0,y+row_h),QPointF(left,y+row_h))
            if note%12==0:
                p.setPen(QPen(Qc("#3b7395"),1))
                p.drawLine(QPointF(left,y),QPointF(w,y))
                octave=note//12-1
                p.setPen(Qc("#e3faff" if black else "#263e54"))
                p.drawText(QRectF(3,y-1,left-6,max(10,row_h)),f"C{octave}")
        if self.events:
            for note in self.events:
                pitch=note["pitch"]
                start=note["start"];end=note["end"]
                if (not self.pitch_lo<=pitch<=self.pitch_hi
                    or end<self.view_start or start>self.view_start+self.visible_ticks):
                    continue
                x=max(left,time_x(start))
                right=min(w,time_x(end))
                width=max(2,right-x)
                yy=pos(pitch)+max(.4,row_h*.13)
                height=max(2.2,row_h*.74)
                grad=QLinearGradient(x,yy,x,yy+height)
                grad.setColorAt(0,Qc("#52dcff"))
                grad.setColorAt(.7,Qc("#04a7f4"))
                grad.setColorAt(1,Qc("#117ac8"))
                p.setPen(QPen(Qc("#0874ac"),.3))
                p.setBrush(QBrush(grad))
                p.drawRoundedRect(QRectF(x,yy,width,height),1,1)
        else:
            p.setPen(Qc("#93aabf"))
            p.drawText(QRectF(left,top,w-left,h-top),Qt.AlignCenter,
                       "Selecciona un MIDI para representar sus notas")
        p.setPen(QPen(Qc("#28dffc"),1.5))
        cx=left+self.cursor*(w-left)
        p.drawLine(QPointF(cx,top),QPointF(cx,h))
        p.end()

class StudioFader(QSlider):
    """Fader dibujado con capuchón tridimensional; conserva Qt valueChanged."""
    def __init__(self,parent=None):
        super().__init__(Qt.Vertical,parent)
        self.setFixedWidth(32)
        self.setMinimumHeight(98)
        self.setToolTip("Fader: arrastra para controlar la ganancia; rueda para ajuste fino.")

    def _set_from_y(self,y):
        margin=13
        extent=max(1,self.height()-margin*2)
        fraction=max(0.,min(1.,(self.height()-margin-float(y))/extent))
        self.setValue(round(self.minimum()+fraction*(self.maximum()-self.minimum())))

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self._set_from_y(event.position().y())
            event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton:
            self._set_from_y(event.position().y())
            event.accept()
        else:super().mouseMoveEvent(event)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing,True)
        cx=self.width()/2
        h=float(self.height())
        top=12.
        bottom=h-12.
        fraction=(self.value()-self.minimum())/max(1,self.maximum()-self.minimum())
        y=bottom-fraction*(bottom-top)
        # Canal oscuro, graduaciones y luz de posición.
        p.setPen(QPen(Qc("#134362"),1))
        p.setBrush(Qc("#020d1d"))
        p.drawRoundedRect(QRectF(cx-7,3,14,h-6),3,3)
        p.setPen(QPen(Qc("#18374e"),1))
        for n in range(15):
            yy=top+n*(bottom-top)/14
            p.drawLine(QPointF(cx-14,yy),QPointF(cx-10,yy))
            p.drawLine(QPointF(cx+10,yy),QPointF(cx+14,yy))
        p.setPen(QPen(Qc("#114263"),4,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPointF(cx,top),QPointF(cx,bottom))
        p.setPen(QPen(QColor(17,173,241,70),9,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPointF(cx,y),QPointF(cx,bottom))
        p.setPen(QPen(Qc("#219eea"),3,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPointF(cx,y),QPointF(cx,bottom))
        # Capuchón ancho gris azulado, borde y reflejo superior.
        cap=QRectF(cx-13,y-9,26,18)
        grad=QLinearGradient(cap.left(),cap.top(),cap.left(),cap.bottom())
        grad.setColorAt(0,Qc("#e5faff"))
        grad.setColorAt(.36,Qc("#b9dce9"))
        grad.setColorAt(1,Qc("#608ba5"))
        p.setPen(QPen(Qc("#ecffff"),1.3))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(cap,3,3)
        p.setPen(QPen(Qc("#5889a2"),1))
        p.drawLine(QPointF(cap.left()+3,y+2),QPointF(cap.right()-3,y+2))
        p.end()


class StudioHome(QWidget):
    """Portada/estación de trabajo de la referencia de diseño, no un mockup."""
    def __init__(self,main,workbench):
        super().__init__(main)
        self.main=main
        self.workbench=workbench
        self.selected_file=None
        self.selected_midi=None
        self._known_state=None
        self._pause=False
        self._mix_levels={}
        self._stem_selection={}
        self._loading=False
        self.setObjectName("studioHome")
        self.player=None
        self._build()
        self.refresh(force=True)
        self.heartbeat=QTimer(self)
        self.heartbeat.setInterval(900)
        self.heartbeat.timeout.connect(self._tick)
        self.heartbeat.start()

    def _build(self):
        scroll=QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        page=QWidget()
        page.setObjectName("studioHomePage")
        page.setMinimumWidth(1290)
        root=QVBoxLayout(page)
        root.setContentsMargins(12,10,12,8)
        root.setSpacing(9)
        self.scroll=scroll
        self.page=page
        scroll.setWidget(page)
        outer=QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.addWidget(scroll)
        # Cuatro módulos arriba, Desglose de batería y herramientas en el
        # centro, Piano Roll e información abajo. Una única pantalla Inicio.
        top=QHBoxLayout();top.setSpacing(9)
        mid=QHBoxLayout();mid.setSpacing(9)
        end=QHBoxLayout();end.setSpacing(9)
        self.mon_card=Card("🔴  1. Monitor / Grabación")
        self.sep_card=Card("◈  2. Separación de audio")
        self.midi_card=Card("♫  3. Audio a MIDI")
        self.result_card=Card("📁  4. Resultados")
        for card,stretch in ((self.mon_card,27),(self.sep_card,23),
                             (self.midi_card,25),(self.result_card,25)):
            card.setMinimumHeight(318)
            card.setMaximumHeight(346)
            top.addWidget(card,stretch)
        root.addLayout(top,39)
        self.wave_card=Card("▣  Vista de audio")
        self.track_card=Card("◈  Pistas separadas")
        self.mix_card=Card("☷  Mezclador")
        self.drum_card=Card("◉  5. Desglose de batería")
        for card,stretch in ((self.wave_card,10),(self.drum_card,10),
                             (self.track_card,11),(self.mix_card,13)):
            card.setMinimumHeight(205)
            card.setMaximumHeight(210)
            mid.addWidget(card,stretch)
        root.addLayout(mid,27)
        self.piano_card=Card("♬  Piano Roll · MIDI")
        self.vocal_card=Card("♬  6. Afinación vocal")
        self.drum_stems_card=Card("◉  Batería · pistas separadas")
        self.info_card=Card("♧  Información")
        for card in (self.piano_card,self.vocal_card,
                     self.drum_stems_card,self.info_card):
            card.setMinimumHeight(205)
            card.setMaximumHeight(215)
        self.piano_card.setMinimumWidth(420)
        self.vocal_card.setMinimumWidth(190)
        self.drum_stems_card.setMinimumWidth(295)
        self.info_card.setMinimumWidth(175)
        end.addWidget(self.piano_card,47)
        end.addWidget(self.vocal_card,19)
        end.addWidget(self.drum_stems_card,24)
        end.addWidget(self.info_card,10)
        root.addLayout(end,29)

        for card,widget in ((self.mon_card,self.main.tabs.widget(0)),
                            (self.sep_card,self.workbench.separation_tab),
                            (self.midi_card,self.workbench.midi_tab),
                            (self.piano_card,self.workbench.piano)):
            card.header.clicked.connect(lambda checked=False,w=widget:self.main.tabs.setCurrentWidget(w))
        self.result_card.header.clicked.connect(lambda:self.open_results())
        self.track_card.header.clicked.connect(lambda:self.open_results())
        self.wave_card.header.clicked.connect(lambda:self.open_audio())
        self.mix_card.header.clicked.connect(self.open_mixer)
        self.drum_card.header.clicked.connect(self.open_drum_module)
        self.drum_stems_card.header.clicked.connect(self.open_drum_module)
        self.vocal_card.header.clicked.connect(self.open_vocal_module)

        self._monitor_widgets()
        self._separator_widgets()
        self._midi_widgets()
        self._results_widgets()
        self._wave_widgets()
        self._drum_widgets()
        self._tracks_widgets()
        self._mixer_widgets()
        self._piano_widgets()
        self._vocal_widgets()
        self._drum_stems_widgets()
        self._info_widgets()
        self._setup_context_help()
        from preview_player import PreviewPlayer
        self.player=PreviewPlayer("Reproductor de Inicio",self)
        self.player.hide()
        self.player.playStateChanged.connect(lambda active:self.play_btn.setText(
              "Ⅱ" if active else "▶"))
        self.player.fileLoaded.connect(lambda _:self._sync_player())
        self.player.error.connect(lambda message:self.result_hint.setText(str(message)[:110]))
        from home_floating_cards import enable as enable_floating_cards
        enable_floating_cards(self)

    def _setup_context_help(self):
        from help_center import open_help
        links=(
            (self.mon_card,"monitor"),
            (self.sep_card,"separacion"),
            (self.midi_card,"midi"),
            (self.result_card,"resultados"),
            (self.wave_card,"onda"),
            (self.drum_card,"bateria"),
            (self.track_card,"pistas"),
            (self.mix_card,"mezclador"),
            (self.piano_card,"piano"),
            (self.vocal_card,"vocal"),
            (self.drum_stems_card,"bateria"),
            (self.info_card,"info"),
        )
        for card,code in links:
            card.help_button.setWhatsThis("Ayuda de "+code)
            card.help_button.clicked.connect(
                lambda checked=False,topic=code:open_help(self.main,topic))

    def _monitor_widgets(self):
        c=self.mon_card.inner
        c.addWidget(label("Dispositivo de entrada"))
        columns=QHBoxLayout()
        columns.setSpacing(12)
        left=QVBoxLayout()
        left.setSpacing(6)

        self.input=QComboBox()
        self.input.currentIndexChanged.connect(self.select_source)
        self.input.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        left.addWidget(self.input)
        left.addSpacing(5)

        buttons=QHBoxLayout()
        buttons.setSpacing(8)
        self.record_btn=action("● Grabar",self.record,True)
        self.record_btn.setObjectName("record")
        self.pause_btn=action("Pausa",self.pause_record)
        self.stop_btn=action("Detener",self.stop_record)
        from studio_transport import RecordTransport
        self.record_transport=RecordTransport(
            self,self.record_btn,self.pause_btn,self.stop_btn,self.mon_card)
        left.addWidget(self.record_transport)

        form=QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(7)
        form.addWidget(label("Formato"),0,0)
        self.format=QComboBox()
        self.format.currentIndexChanged.connect(lambda idx:self.main.format.setCurrentIndex(idx)
            if idx>=0 and idx<self.main.format.count() else None)
        form.addWidget(self.format,0,1)
        form.addWidget(label("Calidad"),1,0)
        self.quality=QComboBox()
        for i in range(self.main.capture_rate.count()):
            self.quality.addItem(self.main.capture_rate.itemText(i),
                                 self.main.capture_rate.itemData(i))
        self.quality.setCurrentIndex(self.main.capture_rate.currentIndex())
        self.quality.currentIndexChanged.connect(
            lambda idx:self.main.capture_rate.setCurrentIndex(idx)
            if 0<=idx<self.main.capture_rate.count() else None)
        self.quality.setToolTip(
            "Resolución de muestreo. La frecuencia efectiva de una fuente "
            "de 48 kHz no mejora por seleccionar 96/192 kHz.")
        form.addWidget(self.quality,1,1)
        left.addLayout(form)
        control_row=QHBoxLayout()
        control_row.setSpacing(7)
        level_box=QVBoxLayout()
        level_box.setSpacing(1)
        level_box.addWidget(label("Volumen de captura"))
        level_line=QHBoxLayout()
        level_line.setContentsMargins(0,0,0,0)
        level_line.setSpacing(5)
        self.capture_gain=QSlider(Qt.Horizontal)
        self.capture_gain.setObjectName("captureGain")
        self.capture_gain.setRange(-60,12)
        self.capture_gain.setSingleStep(1)
        self.capture_gain.setPageStep(3)
        self.capture_gain.setValue(self.main.input_gain_db)
        self.capture_gain.setToolTip(
            "Ganancia de grabación en dB. Pulsa ? en Monitor para más información.")
        self.capture_gain.setToolTipDuration(3500)
        self.gain_value=label("0 dB")
        self.gain_value.setObjectName("mixValue")
        self.gain_value.setMinimumWidth(52)
        self.gain_value.setAlignment(Qt.AlignCenter)
        level_line.addWidget(self.capture_gain,1)
        level_line.addWidget(self.gain_value)
        level_box.addLayout(level_line)
        self.capture_gain.valueChanged.connect(self._on_capture_gain)
        control_row.addLayout(level_box,1)
        balance_box=QVBoxLayout()
        balance_box.setSpacing(0)
        title=label("Balance L/R")
        title.setAlignment(Qt.AlignCenter)
        balance_box.addWidget(title)
        self.capture_balance=BalanceDial(self)
        self.capture_balance.setValue(self.main.input_balance)
        balance_box.addWidget(self.capture_balance,0,Qt.AlignHCenter)
        self.balance_value=label("Centro")
        self.balance_value.setObjectName("homeLabel")
        self.balance_value.setAlignment(Qt.AlignCenter)
        balance_box.addWidget(self.balance_value)
        self.capture_balance.valueChanged.connect(self._on_capture_balance)
        control_row.addLayout(balance_box,0)
        left.addLayout(control_row)
        self.sync_input_controls()
        left.addStretch(1)

        self.monitor_check=QCheckBox("Monitorizar sonido")
        self.monitor_check.toggled.connect(self.toggle_monitor)
        left.addWidget(self.monitor_check)
        self.audio_lab_button=action("Laboratorio profesional de audio",self.open_recording_lab)
        self.audio_lab_button.setToolTip(
            "Abre restauración de ruidos, ecualizador, de-esser, puerta, "
            "compresor, limitador y normalización. Procesa copias después "
            "de grabar, automáticamente o bajo demanda, sin alterar originales.")
        left.addWidget(self.audio_lab_button)
        self.monitor_state=label("Supervisión detenida",muted=True)
        left.addWidget(self.monitor_state)
        columns.addLayout(left,1)

        right=QVBoxLayout()
        right.setSpacing(9)
        self.level_meter=VerticalMeter(self)
        self.level_meter.setMinimumHeight(180)
        self.level_meter.setMaximumHeight(205)
        right.addWidget(self.level_meter,1,Qt.AlignHCenter)
        monitor_setup=action("⚙",self.monitor_settings)
        monitor_setup.setFixedSize(32,28)
        monitor_setup.setToolTip("Configuración de entrada y salida de audio")
        right.addWidget(monitor_setup,0,Qt.AlignHCenter)
        right.addStretch()
        columns.addLayout(right,0)
        c.addLayout(columns,1)

    def open_recording_lab(self):
        """En flotante, nunca abandonar Inicio por otro módulo."""
        if self._is_float(self.mon_card):return
        self.main.tabs.setCurrentWidget(self.main.monitor_page)
        lab=self.main.recording_lab
        if getattr(self.main,"monitor_scroll",None) is not None:
            self.main.monitor_scroll.ensureWidgetVisible(lab,15,15)
        lab.setFocus()

    def _on_capture_gain(self,gain_db):
        self.main.set_input_processing(gain_db=gain_db)

    def _on_capture_balance(self,balance):
        self.main.set_input_processing(balance=balance)

    def sync_input_controls(self):
        gain=int(self.main.input_gain_db)
        balance=int(self.main.input_balance)
        if self.capture_gain.value()!=gain:
            was=self.capture_gain.blockSignals(True)
            self.capture_gain.setValue(gain)
            self.capture_gain.blockSignals(was)
        if self.capture_balance.value()!=balance:
            was=self.capture_balance.blockSignals(True)
            self.capture_balance.setValue(balance)
            self.capture_balance.blockSignals(was)
        self.gain_value.setText("−∞ dB" if gain==-60 else f"{gain:+d} dB" if gain else "0 dB")
        self.balance_value.setText("Centro" if balance==0 else
                                   f"L {abs(balance)}" if balance<0 else f"R {balance}")

    def monitor_settings(self):
        from studio_shell import preferences
        preferences(self.main)

    def _separator_widgets(self):
        c=self.sep_card.inner
        c.addWidget(label("Modelo de separación"))
        self.model=QComboBox()
        self.model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.model.setMinimumContentsLength(12)
        self.model.currentIndexChanged.connect(self.select_model)
        c.addWidget(self.model)
        c.addWidget(label("Pistas a extraer"))
        self.stem_checks={}
        grid=QGridLayout()
        for i,name in enumerate(("Voces","Guitarra","Batería","Piano",
                                 "Bajo","Viento","Otros")):
            check=QCheckBox(name)
            check.setChecked(True)
            self.stem_checks[name]=check
            check.toggled.connect(lambda state,n=name:self.on_stem_mask(n,state))
            grid.addWidget(check,i//2,i%2)
        c.addLayout(grid)
        self.stem_note=label("Las pistas disponibles dependen del modelo.",muted=True)
        self.stem_note.setWordWrap(True)
        c.addWidget(self.stem_note)
        self.sep_settings=action("⚙ Ajustes avanzados",lambda:
              self.main.tabs.setCurrentWidget(self.workbench.separation_tab))
        actions=QHBoxLayout()
        actions.addWidget(self.sep_settings)
        self.drum_shortcut=action("Desglosar batería",self.open_drum_module)
        actions.addWidget(self.drum_shortcut)
        actions.addStretch(1)
        c.addLayout(actions)
        self.sep_run=action("◈  Separar audio",self.run_separation,True)
        c.addStretch(1)
        c.addWidget(self.sep_run)

    def open_drum_module(self):
        if self._is_float(self.sep_card) or self._is_float(self.drum_card):
            self._sync_drum_module(force=True)
            return
        module=getattr(self.main,"drum_module",None)
        if module is not None:
            module.refresh_sources()
            self.main.tabs.setCurrentWidget(module)

    def _drum_widgets(self):
        """Tarjeta completa vinculada al mismo motor del módulo de batería."""
        c=self.drum_card.inner
        c.setSpacing(4)
        c.addWidget(label("Pista de batería del proyecto"))
        self.drum_source=QComboBox()
        self.drum_source.setObjectName("homeDrumSource")
        self.drum_source.setMinimumContentsLength(11)
        self.drum_source.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.drum_source.addItem("Sin batería en el proyecto",None)
        self.drum_source.setToolTip("Seleccionar el audio real que se desea desglosar.")
        self.drum_source.currentIndexChanged.connect(self._choose_drum_source)
        c.addWidget(self.drum_source)
        self.drum_model=label("MDX23C DrumSep · 6 instrumentos",muted=True)
        c.addWidget(self.drum_model)
        names=(("Bombo","Caja","Toms"),("Charles","Ride","Crash"))
        self.drum_lamps={}
        for part_row in names:
            line=QHBoxLayout()
            line.setSpacing(3)
            for part in part_row:
                lamp=label("○ "+part,muted=True)
                lamp.setToolTip("Se activa solo si existe el archivo real de esta pista.")
                line.addWidget(lamp,1)
                self.drum_lamps[part]=lamp
            c.addLayout(line)
        self.drum_state=label("Modelo no instalado · ninguna pista generada",muted=True)
        self.drum_state.setWordWrap(True)
        c.addWidget(self.drum_state)
        actions=QHBoxLayout()
        actions.setSpacing(4)
        self.drum_install=action("IA",self._install_drum_model)
        self.drum_import=action("Cargar audio…",self._import_drum_audio)
        self.drum_import.setToolTip(
            "Seleccionar batería aislada en WAV, FLAC, MP3, M4A, OGG y otros audios.")
        self.drum_install.setToolTip("Instalar el modelo MDX23C de separación de batería.")
        self.drum_open=action("⚙",self.open_drum_module)
        self.drum_open.setFixedWidth(32)
        self.drum_open.setToolTip("Abrir todas las opciones de Desglose de batería.")
        actions.addWidget(self.drum_import)
        actions.addWidget(self.drum_install)
        actions.addWidget(self.drum_open)
        self.drum_start=action("Desglosar",self._start_drum,True)
        actions.addWidget(self.drum_start,1)
        c.addStretch(1)
        c.addLayout(actions)
        self._drum_module=None
        self._drum_known=None

    def bind_drum_module(self,module):
        """Enlazar después de crear la pestaña (Inicio se crea antes)."""
        self._drum_module=module
        module.resultsChanged.connect(self._sync_drum_module)
        self._sync_drum_module(force=True)

    def _choose_drum_source(self,index):
        if self._loading or self._drum_module is None:return
        path=self.drum_source.itemData(index)
        if path and Path(path).is_file():
            self._drum_module.input.setText(str(path))
            slot=self._drum_module.project_source.findData(path)
            if slot>=0:
                was=self._drum_module.project_source.blockSignals(True)
                self._drum_module.project_source.setCurrentIndex(slot)
                self._drum_module.project_source.blockSignals(was)

    def _import_drum_audio(self):
        if self._drum_module is None:return
        self.open_drum_module()
        self._drum_module.browse_audio()
        self._sync_drum_module(force=True)

    def _install_drum_model(self):
        if self._drum_module is None:return
        self._drum_module.install_model()
        self._sync_drum_module(force=True)

    def _start_drum(self):
        if self._drum_module is None:return
        # No se abre el módulo hasta validar lo necesario; si falta origen
        # o modelo se abre la pestaña para presentar el mensaje preciso.
        module=self._drum_module
        self._choose_drum_source(self.drum_source.currentIndex())
        self.open_drum_module()
        module.start()
        self._sync_drum_module(force=True)

    def _sync_drum_module(self,force=False):
        module=self._drum_module
        if module is None:return
        sources=tuple(str(p) for p in self.workbench.separation_storage.items
                      if Path(p).is_file() and
                      any(word in Path(p).stem.casefold()
                          for word in ("drums","batería","bateria")))
        results=tuple(str(p) for p in module.storage.items if Path(p).is_file())
        running=module.process is not None
        model=module.model_ready()
        state=(sources,results,running,model,module.input.text())
        if state==self._drum_known and not force:return
        self._drum_known=state
        if hasattr(self,"drum_stem_rows"):
            self._sync_drum_stems()
        current=self.drum_source.currentData()
        self._loading=True
        try:
            self.drum_source.clear()
            self.drum_source.addItem("Sin batería en el proyecto",None)
            for path in sources:
                self.drum_source.addItem(Path(path).name,path)
            selected=(module.input.text() if module.input.text() in sources else current)
            idx=self.drum_source.findData(selected)
            if idx<0 and sources:idx=1
            self.drum_source.setCurrentIndex(max(idx,0))
        finally:
            self._loading=False
        from drum_module import category
        real={category(Path(x)) for x in results}
        for part,lamp in self.drum_lamps.items():
            available=part in real
            lamp.setText(("● " if available else "○ ")+part)
            lamp.setStyleSheet("color:#42dfb9;font-weight:600;" if available
                               else "color:#a3e4f0;")
        self.drum_install.setEnabled(not running and not model)
        self.drum_start.setEnabled(not running)
        if running:
            self.drum_state.setText("Procesando audio · ver módulo")
        elif results:
            self.drum_state.setText(f"{len(results)} pistas reales · proyecto actual")
        elif model:
            self.drum_state.setText("IA preparada · selecciona una batería")
        else:
            self.drum_state.setText("Modelo pendiente · instalar IA")

    def _midi_widgets(self):
        c=self.midi_card.inner
        c.setSpacing(2)
        first=QHBoxLayout()
        block=QVBoxLayout();block.setSpacing(3)
        block.addWidget(label("Modelo de transcripción"))
        self.engine=QComboBox()
        self.engine.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.engine.setMinimumContentsLength(10)
        self.engine.addItem("Basic Pitch (preciso)","basic")
        self.engine.addItem("Transkun · piano","transkun")
        self.engine.currentIndexChanged.connect(self.select_engine)
        block.addWidget(self.engine)
        first.addLayout(block,1)
        block2=QVBoxLayout();block2.setSpacing(3)
        block2.addWidget(label("Preset"))
        self.midi_preset=QComboBox()
        self.midi_preset.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.midi_preset.setMinimumContentsLength(8)
        self.midi_preset.currentIndexChanged.connect(self.choose_midi_preset)
        block2.addWidget(self.midi_preset)
        first.addLayout(block2,1)
        c.addLayout(first)
        from ux_controls import SliderNumber
        specs=[
            ("Sensibilidad de ataque","onset",.1,.95,.5,.01,2,""),
            ("Duración mínima","min_duration",40,2000,120,5,0," ms"),
            ("Unión de microcortes","merge_gap",0,250,0,5,0," ms"),
            ("Desplazamiento de ataque","note_shift",-250,250,0,5,0," ms")]
        self.midi_sliders={}
        for title,key,lo,hi,initial,step,decimals,suffix in specs:
            w=SliderNumber(lo,hi,initial,step,decimals,suffix)
            w.setMinimumWidth(135)
            w.number.setFixedWidth(72)
            w.slider.setMinimumWidth(45)
            self.midi_sliders[key]=w
            row=QHBoxLayout()
            lbl=label(title)
            lbl.setObjectName("homeLabel")
            lbl.setMinimumWidth(122)
            row.addWidget(lbl)
            row.addWidget(w,1)
            c.addLayout(row)
            w.valueChanged.connect(lambda val,k=key:self.change_midi_parameter(k,val))
        row=QHBoxLayout()
        row.addWidget(label("Refinamiento"))
        self.refine=QComboBox()
        self.refine.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.refine.setMinimumContentsLength(9)
        self.refine.currentIndexChanged.connect(self.select_refinement)
        row.addWidget(self.refine,1)
        c.addLayout(row)
        quant=QHBoxLayout()
        self.quant_check=QCheckBox("Cuantización (opcional)")
        self.quant_check.toggled.connect(self.toggle_quant)
        quant.addWidget(self.quant_check,1)
        self.quant=QComboBox()
        self.quant.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.quant.setMinimumContentsLength(9)
        self.quant.currentIndexChanged.connect(self.select_quant)
        quant.addWidget(self.quant)
        c.addLayout(quant)
        self.chords_check=QCheckBox("Detectar acordes → MIDI aparte")
        self.chords_check.setToolTip(
            "Opcional: analiza acordes reales del audio y genera una pista MIDI "
            "independiente después de transcribir las notas. Solo en archivo único.")
        self.chords_check.toggled.connect(self.toggle_chord_analysis)
        c.addWidget(self.chords_check)
        self.midi_run=action("♫  Convertir a MIDI",self.run_midi,True)
        c.addStretch(1)
        c.addWidget(self.midi_run)

    def _results_widgets(self):
        c=self.result_card.inner
        tabbar=QHBoxLayout();tabbar.setSpacing(4)
        self.result_pages=QStackedWidget()
        for idx,title in enumerate(("Archivos","Vista previa","Información")):
            b=QPushButton(title)
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False,n=idx:self._result_tab(n))
            tabbar.addWidget(b)
            setattr(self,"results_btn_"+str(idx),b)
        c.addLayout(tabbar)
        self.files=QTableWidget(0,3)
        self.files.setHorizontalHeaderLabels(["Nombre","Tipo","Duración"])
        self.files.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.files.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.files.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.files.verticalHeader().hide()
        self.files.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Selección de distintas filas sin salir de la pantalla Inicio.
        self.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files.setToolTip("Ctrl+Clic selecciona pistas sueltas; Mayús+Clic selecciona un intervalo.")
        self.files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.files.itemSelectionChanged.connect(self.file_selected)
        self.files.cellDoubleClicked.connect(self.file_double_clicked)
        self.files.setAlternatingRowColors(True)
        self.files.setShowGrid(False)
        self.files.setIconSize(__import__("PySide6").QtCore.QSize(18,18))
        self.result_pages.addWidget(self.files)
        result_preview_page=QWidget()
        preview_layout=QVBoxLayout(result_preview_page)
        preview_layout.setContentsMargins(3,2,3,2)
        preview_layout.setSpacing(3)
        self.result_preview=label("Selecciona audio o MIDI. El reproductor está disponible justo debajo.",muted=True)
        self.result_preview.setWordWrap(True)
        preview_layout.addWidget(self.result_preview)
        self.result_wave=WaveCanvas(small=True)
        self.result_wave.setMinimumHeight(38)
        self.result_wave.clicked.connect(lambda _:self.play_selected())
        preview_layout.addWidget(self.result_wave)
        self.result_pages.addWidget(result_preview_page)
        self.result_about=label("Los resultados se conservan en el área temporal.",muted=True)
        self.result_about.setWordWrap(True)
        self.result_pages.addWidget(self.result_about)
        c.addWidget(self.result_pages,1)
        transport=QHBoxLayout()
        self.play_btn=action("▶",self.play_selected,True)
        self.stop_btn_audio=action("■",self.stop_audio)
        self.pause_btn_audio=action("Ⅱ",self.pause_selected)
        self.audio_progress=label("00:00 / 00:00")
        self.volume_icon=label("◖))")
        self.master_volume=QSlider(Qt.Horizontal)
        self.master_volume.setRange(0,100)
        self.master_volume.setValue(85)
        self.master_volume.valueChanged.connect(lambda v:self.player.volume.setValue(v)
              if self.player is not None else None)
        for b in (self.play_btn,self.stop_btn_audio,self.pause_btn_audio):
            b.setFixedWidth(32)
            transport.addWidget(b)
        transport.addWidget(self.audio_progress,1)
        transport.addWidget(self.volume_icon)
        transport.addWidget(self.master_volume,1)
        c.addLayout(transport)
        from PySide6.QtWidgets import QMenu
        self.results_folder=action("▱ Abrir carpeta",self.open_results_folder)
        self.export_btn=QPushButton("Guardar  ▾")
        self.export_btn.setToolTip("Guardar la selección de esta tabla o todos los archivos temporales.")
        self.export_menu=QMenu(self.export_btn)
        self.export_menu.addAction("Guardar selección de esta lista…",self.export_selected)
        self.export_menu.addAction("Guardar todos los resultados…",self.export_all)
        self.export_btn.setMenu(self.export_menu)
        self.discard_btn=QPushButton("Descartar  ▾")
        self.discard_btn.setToolTip("Eliminar solo resultados temporales después de confirmar.")
        self.discard_menu=QMenu(self.discard_btn)
        self.discard_menu.addAction("Descartar separación temporal…",
            lambda:self.discard_results("separaciones"))
        self.discard_menu.addAction("Descartar MIDI temporal…",
            lambda:self.discard_results("midi"))
        self.discard_btn.setMenu(self.discard_menu)
        buttons=padded_row(self.results_folder,self.export_btn,self.discard_btn,spacing=4)
        c.addLayout(buttons)
        self.result_hint=label("",muted=True)
        self.result_hint.setWordWrap(True)
        c.addWidget(self.result_hint)
        self._result_tab(0)

    def _wave_widgets(self):
        c=self.wave_card.inner
        self.wave_title=label("Sin audio seleccionado",muted=True)
        c.addWidget(self.wave_title)
        self.wave=WaveCanvas()
        self.wave.clicked.connect(self.seek_audio_fraction)
        c.addWidget(self.wave,1)
        progress=QHBoxLayout()
        self.overview=WaveCanvas(small=True)
        self.overview.setFixedHeight(22)
        self.overview.clicked.connect(self.seek_audio_fraction)
        progress.addWidget(self.overview,1)
        zoom_out=action("−",lambda:self.wave_zoom.setValue(max(1,self.wave_zoom.value()-1)))
        zoom_in=action("+",lambda:self.wave_zoom.setValue(min(5,self.wave_zoom.value()+1)))
        for b in (zoom_out,zoom_in):b.setFixedWidth(30);progress.addWidget(b)
        c.addLayout(progress)
        self.wave_zoom=QSlider(Qt.Horizontal)
        self.wave_zoom.setRange(1,5);self.wave_zoom.setValue(1)
        self.wave_zoom.setToolTip("Zoom real de la forma de onda")
        self.wave_zoom.valueChanged.connect(self.change_wave_zoom)
        self.wave_zoom.hide()
        self.overview.selection=1.0

    def change_wave_zoom(self,value):
        self.wave.set_zoom(value)
        self.overview.selection=1/max(1,value)
        self.overview.selection_start=self.wave.view_start
        self.overview.update()

    def _tracks_widgets(self):
        c=self.track_card.inner
        self.track_rows={}
        c.setSpacing(2)
        for name in ("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros"):
            row=QHBoxLayout();row.setSpacing(4)
            col=label(name)
            col.setStyleSheet(f"color:{COLORS[name]};")
            col.setFixedWidth(64)
            row.addWidget(col)
            solo=QPushButton("S");mute=QPushButton("M")
            for b in (solo,mute):
                b.setCheckable(True);b.setFixedSize(24,23)
                row.addWidget(b)
            tiny=WaveCanvas(small=True)
            tiny.wave_color=COLORS[name]
            tiny.setFixedHeight(24)
            tiny.clicked.connect(lambda fraction,n=name:self.play_stem(n,fraction))
            tiny.setMinimumWidth(70)
            row.addWidget(tiny,1)
            play=QPushButton("▶")
            stop=QPushButton("■")
            play.setToolTip(f"Reproducir solo la pista {name}")
            stop.setToolTip(f"Detener la pista {name}")
            for button in (play,stop):
                button.setFixedSize(22,23)
                row.addWidget(button)
            play.clicked.connect(lambda checked=False,n=name:self.play_stem(n))
            stop.clicked.connect(lambda checked=False,n=name:self.stop_stem(n))
            # Control de ganancia lógico, sin duplicar deslizantes: los
            # faders editables solo se muestran en el Mezclador.
            gain=QSlider(Qt.Horizontal,self)
            gain.setRange(0,150);gain.setValue(100)
            gain.hide()
            c.addLayout(row)
            self.track_rows[name]={"solo":solo,"mute":mute,"gain":gain,
                                   "play":play,"stop":stop,"wave":tiny,"path":None}
            solo.toggled.connect(lambda yes,n=name:self.mix_changed(n))
            mute.toggled.connect(lambda yes,n=name:self.mix_changed(n))
            gain.valueChanged.connect(lambda val,n=name:self.mix_changed(n))
        c.addStretch(1)

    def _mixer_widgets(self):
        c=self.mix_card.inner
        head=QHBoxLayout()
        head.addStretch()
        head.addWidget(action("Restablecer",self.reset_mixer))
        head.addWidget(action("☷",self.open_mixer))
        c.addLayout(head)
        grid=QHBoxLayout()
        grid.setSpacing(4)
        self.mixer_rows={}
        c.setSpacing(3)
        for name in ("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros"):
            column=QVBoxLayout()
            column.setSpacing(3)
            title=label(name[:7])
            title.setAlignment(Qt.AlignCenter)
            title.setObjectName("homeLabel")
            column.addWidget(title)
            levels=QHBoxLayout()
            levels.setContentsMargins(0,0,0,0)
            levels.setSpacing(4)
            fader=StudioFader(self)
            fader.setRange(0,150);fader.setValue(100)
            fader.setMinimumHeight(91)
            meter=StemMeter(self)
            levels.addWidget(meter)
            levels.addWidget(fader)
            column.addLayout(levels,1)
            readout=label("0.0 dB")
            readout.setObjectName("mixValue")
            readout.setAlignment(Qt.AlignCenter)
            column.addWidget(readout)
            grid.addLayout(column,1)
            self.mixer_rows[name]={"fader":fader,"readout":readout,
                                   "meter":meter}
            fader.valueChanged.connect(lambda value,n=name:self.change_mix(n,value))
        c.addLayout(grid,1)

    def _piano_widgets(self):
        c=self.piano_card.inner
        c.setSpacing(4)
        header=QHBoxLayout()
        self.midi_choice=QComboBox()
        self.midi_choice.setToolTip("Selecciona el MIDI real para dibujar sus notas")
        self.midi_choice.setMaximumWidth(295)
        self.midi_choice.currentIndexChanged.connect(self.choose_midi)
        header.addWidget(self.midi_choice,1)
        header.addWidget(action("↶",lambda:self.workbench.piano.undo()))
        header.addWidget(action("↷",lambda:self.workbench.piano.redo()))
        header.addWidget(action("⌕",self.open_piano))
        self.grid_choice=QComboBox()
        self.grid_choice.addItems(["Sin ajuste","1/4","1/8","1/16","1/32","1/64"])
        self.grid_choice.setCurrentText("1/16")
        self.grid_choice.currentTextChanged.connect(self.change_grid)
        header.addWidget(self.grid_choice)
        # Los controles de velocidad y navegación caben en segunda línea
        # para mantener legible el Piano Roll, ahora más estrecho.
        c.addLayout(header)
        header=QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(label("Velocidad"))
        self.note_velocity=QSlider(Qt.Horizontal)
        self.note_velocity.setRange(1,127);self.note_velocity.setValue(90)
        self.note_velocity.setMaximumWidth(92)
        self.note_velocity.valueChanged.connect(self.change_velocity)
        header.addWidget(self.note_velocity)
        self.vel_value=label("90")
        header.addWidget(self.vel_value)
        header.addWidget(action("◀",lambda:self.step_piano(-4)))
        header.addWidget(action("▶",lambda:self.step_piano(4)))
        self.roll_position=QSlider(Qt.Horizontal)
        self.roll_position.setRange(0,1000)
        self.roll_position.setMinimumWidth(110)
        self.roll_position.setMaximumWidth(160)
        self.roll_position.setToolTip("Mover por los compases del MIDI")
        self.roll_position.valueChanged.connect(lambda val:self.piano_preview.set_scroll(val/1000))
        header.addWidget(self.roll_position)
        c.addLayout(header)
        self.piano_preview=PianoOverview()
        self.piano_preview.activated.connect(self.seek_piano)
        self.piano_preview.viewChanged.connect(self._roll_scroll_changed)
        c.addWidget(self.piano_preview,1)

    def open_vocal_module(self):
        if self._is_float(self.vocal_card):
            self._sync_vocal_module(force=True)
            return
        module=getattr(self.main,"vocal_module",None)
        if module is not None:
            module.refresh_sources()
            self.main.tabs.setCurrentWidget(module)

    def _vocal_widgets(self):
        c=self.vocal_card.inner
        c.setSpacing(3)
        c.addWidget(label("Voz del proyecto"))
        self.vocal_source=QComboBox()
        self.vocal_source.addItem("Sin voz separada",None)
        self.vocal_source.currentIndexChanged.connect(self._select_vocal_source)
        c.addWidget(self.vocal_source)
        row=QHBoxLayout()
        row.setSpacing(4)
        self.vocal_tonic=QComboBox()
        self.vocal_tonic.addItems(("Do","Do#","Re","Re#","Mi","Fa","Fa#",
                                  "Sol","Sol#","La","La#","Si"))
        self.vocal_tonic.currentIndexChanged.connect(self._select_vocal_tonic)
        self.vocal_tonic.setToolTip("Tonalidad de la canción.")
        row.addWidget(self.vocal_tonic)
        self.vocal_scale=QComboBox()
        self.vocal_scale.addItems(("Cromática","Mayor","Menor natural",
                                   "Pentatónica mayor","Pentatónica menor"))
        self.vocal_scale.currentIndexChanged.connect(self._select_vocal_scale)
        self.vocal_scale.setToolTip("Escala musical para corregir las notas.")
        row.addWidget(self.vocal_scale,1)
        c.addLayout(row)
        self.vocal_strength=QSlider(Qt.Horizontal)
        self.vocal_strength.setRange(10,100)
        self.vocal_strength.setValue(75)
        self.vocal_strength.valueChanged.connect(self._select_vocal_strength)
        c.addWidget(self.vocal_strength)
        self.vocal_state=label("Sin voz afinada",muted=True)
        self.vocal_state.setWordWrap(True)
        c.addWidget(self.vocal_state)
        self.vocal_run=action("Afinar voz",self._start_vocal,True)
        c.addStretch(1)
        c.addWidget(self.vocal_run)
        self._vocal_module=None
        self._vocal_known=None

    def _drum_stems_widgets(self):
        c=self.drum_stems_card.inner
        c.setSpacing(1)
        self.drum_stem_rows={}
        for name in ("Bombo","Caja","Toms","Charles","Ride","Crash"):
            row=QHBoxLayout()
            row.setSpacing(3)
            title=label(name)
            title.setFixedWidth(50)
            row.addWidget(title)
            wave=WaveCanvas(small=True)
            wave.setFixedHeight(20)
            wave.setMinimumWidth(70)
            row.addWidget(wave,1)
            play=QPushButton("▶")
            stop=QPushButton("■")
            for b in (play,stop):
                b.setFixedSize(20,20)
                b.setEnabled(False)
                row.addWidget(b)
            play.clicked.connect(lambda checked=False,n=name:self.play_drum_stem(n))
            stop.clicked.connect(lambda checked=False,n=name:self.stop_drum_stem(n))
            wave.clicked.connect(lambda fraction,n=name:self.play_drum_stem(n))
            c.addLayout(row)
            self.drum_stem_rows[name]={"wave":wave,"play":play,
                                       "stop":stop,"path":None}
        c.addStretch(1)

    def _sync_drum_stems(self):
        from drum_module import category
        module=self._drum_module
        paths={} if module is None else {
            category(Path(x)):Path(x) for x in module.storage.items
            if Path(x).is_file()}
        for name,parts in self.drum_stem_rows.items():
            path=paths.get(name)
            if parts["path"]!=path:
                parts["path"]=path
                parts["wave"].set_file(path)
            parts["play"].setEnabled(bool(path))
            parts["stop"].setEnabled(bool(path))

    def play_drum_stem(self,name):
        row=self.drum_stem_rows.get(name)
        if row and row["path"] is not None and row["path"].is_file():
            self.player.load(row["path"],autoplay=True)

    def stop_drum_stem(self,name):
        row=self.drum_stem_rows.get(name)
        if row and row["path"] and self.player.current_file==str(row["path"]):
            self.player.stop()

    def bind_vocal_module(self,module):
        self._vocal_module=module
        module.resultsChanged.connect(lambda:self._sync_vocal_module(force=True))
        self._sync_vocal_module(force=True)

    def _sync_vocal_module(self,force=False):
        module=self._vocal_module
        if module is None:return
        sources=tuple(str(x) for x in self.workbench.separation_storage.items
                     if Path(x).is_file() and any(w in Path(x).stem.casefold()
                     for w in ("vocals","voice","voz","voces")))
        outputs=tuple(str(x) for x in module.storage.items if Path(x).is_file())
        state=(sources,outputs,module.input.text(),
               module.process is not None,module.tonic.currentIndex(),
               module.scale.currentIndex(),module.strength.value())
        if not force and state==self._vocal_known:return
        self._vocal_known=state
        was=self.vocal_source.blockSignals(True)
        self.vocal_source.clear()
        self.vocal_source.addItem("Sin voz separada",None)
        for name in sources:self.vocal_source.addItem(Path(name).name,name)
        index=self.vocal_source.findData(module.input.text())
        if index<0 and sources:index=1
        self.vocal_source.setCurrentIndex(max(index,0))
        self.vocal_source.blockSignals(was)
        for local,remote in (
            (self.vocal_tonic,module.tonic),
            (self.vocal_scale,module.scale)):
            blocked=local.blockSignals(True)
            local.setCurrentIndex(remote.currentIndex())
            local.blockSignals(blocked)
        blocked=self.vocal_strength.blockSignals(True)
        self.vocal_strength.setValue(module.strength.value())
        self.vocal_strength.blockSignals(blocked)
        self.vocal_run.setEnabled(module.process is None)
        self.vocal_state.setText(
            "Corrigiendo notas…" if module.process is not None else
            "Voz afinada disponible" if outputs else
            "Sin resultados vocales · voz solista")

    def _select_vocal_source(self,index):
        if self._vocal_module is None or self._loading:return
        source=self.vocal_source.itemData(index)
        if source:self._vocal_module.input.setText(source)

    def _select_vocal_tonic(self,index):
        if self._vocal_module is not None:
            self._vocal_module.tonic.setCurrentIndex(index)

    def _select_vocal_scale(self,index):
        if self._vocal_module is not None:
            self._vocal_module.scale.setCurrentIndex(index)

    def _select_vocal_strength(self,value):
        if self._vocal_module is not None:
            self._vocal_module.strength.setValue(value)

    def _start_vocal(self):
        if self._vocal_module is None:return
        self._select_vocal_source(self.vocal_source.currentIndex())
        self.open_vocal_module()
        self._vocal_module.start()
        self._sync_vocal_module(force=True)

    def _info_widgets(self):
        c=self.info_card.inner
        c.setSpacing(2)
        self.note_info=label("Notas: —")
        self.duration_info=label("Duración: —")
        self.tempo_info=label("Tempo: —")
        self.key_info=label("Tonalidad: —")
        for item in (self.note_info,self.duration_info,self.tempo_info,self.key_info):
            c.addWidget(item)
        c.addStretch(1)
        edit=action("Editar MIDI ↗",self.open_piano,True)
        edit.setFixedHeight(27)
        c.addWidget(edit)

    def _link_combo(self,source,target):
        index=target.findData(source.currentData())
        if index>=0 and target.currentIndex()!=index:
            was=target.blockSignals(True);target.setCurrentIndex(index);target.blockSignals(was)

    def select_source(self,index):
        ident=self.input.itemData(index)
        if ident is None or self.main.worker is not None:return
        old=self.main.sources.blockSignals(True)
        actual=self.main.sources.findData(ident)
        if actual>=0:self.main.sources.setCurrentIndex(actual)
        self.main.sources.blockSignals(old)

    def toggle_monitor(self,enabled):
        active=self.main.worker is not None and self.main.worker.isRunning()
        if enabled and not active:self.main.start_monitor()
        if not enabled and active and not self.main.recording:
            self.main.stop_monitor()
        self._sync_monitor()

    def _sync_monitor(self):
        self._loading=True
        try:
            if self.input.count()!=self.main.sources.count():
                self.input.clear()
                for i in range(self.main.sources.count()):
                    self.input.addItem(self.main.sources.itemText(i),
                                       self.main.sources.itemData(i))
            self._link_combo(self.main.sources,self.input)
            if self.format.count()!=self.main.format.count():
                self.format.clear()
                for i in range(self.main.format.count()):
                    self.format.addItem(self.main.format.itemText(i))
            i=self.main.format.currentIndex()
            if i>=0 and self.format.currentIndex()!=i:
                old=self.format.blockSignals(True)
                self.format.setCurrentIndex(i)
                self.format.blockSignals(old)
            active=bool(self.main.worker and self.main.worker.isRunning())
            checked=self.monitor_check.blockSignals(True)
            self.monitor_check.setChecked(active)
            self.monitor_check.blockSignals(checked)
            self.monitor_state.setText(
                "● GRABANDO" if self.main.recording else
                "● SUPERVISANDO" if active else "● Supervisión detenida")
            self.record_btn.setText("● REC" if not self.main.recording else "● REC ON")
            self.pause_btn.setEnabled(bool(self.main.recording))
            self.stop_btn.setEnabled(active)
            self.input.setEnabled(not active)
            self.record_btn.setEnabled(not self.main.record_pending)
        finally:self._loading=False

    def record(self):
        if self.main.recording:
            self.main.toggle_record()
        else:self.main.toggle_record()
        QTimer.singleShot(300,self._sync_monitor)

    def pause_record(self):
        worker=self.main.worker
        if not self.main.recording or worker is None:
            return
        self._pause=not self._pause
        if hasattr(worker,"set_record_paused"):
            worker.set_record_paused(self._pause)
            self.pause_btn.setText("Continuar" if self._pause else "Pausa")
            self.monitor_state.setText("● GRABACIÓN PAUSADA" if self._pause
                                       else "● GRABANDO")
        else:
            self._pause=False
            QMessageBox.information(self,"Pausa de grabación",
                "La captura instalada no permite pausar todavía esta grabación.")

    def stop_record(self):
        if self.main.recording:
            if self._pause:self.pause_record()
            self.main.toggle_record()
        elif self.main.worker is not None and self.main.worker.isRunning():
            self.main.stop_monitor()
        self._sync_monitor()

    def select_model(self,index):
        if self._loading:return
        data=self.model.itemData(index)
        sep=self.workbench.separator
        actual=sep.profile.findText(data)
        if actual>=0:sep.profile.setCurrentIndex(actual)
        self._sync_stem_capabilities()

    def _sync_stem_capabilities(self):
        model=self.workbench.separator.profile.currentText().lower()
        six="6 pistas" in model
        text=("Demucs 6 pistas separa guitarra y piano, pero no viento; "
              "en los modelos de 4 pistas están dentro de Otros."
              if not six else
              "Guitarra y piano disponibles. Para viento se requiere un modelo "
              "de separación específico; no se generarán pistas ficticias.")
        self.stem_note.setText(text)
        for name,check in self.stem_checks.items():
            check.setEnabled(True)
            old=check.blockSignals(True)
            check.setChecked(self._stem_selection.get(name,
                 name in ("Voces","Batería","Bajo","Otros")))
            check.blockSignals(old)
            check.setToolTip(
                "Familia solicitada. Solo se extrae cuando el modelo dispone de ella."
                if name=="Viento" else "Selecciona la familia para los resultados.")
        self._show_tracks()

    def on_stem_mask(self,name,enabled):
        self._stem_selection[name]=enabled
        if enabled and name in ("Guitarra","Piano"):
            sep=self.workbench.separator.profile
            if "6 pistas" not in sep.currentText().lower():
                six=next((i for i in range(sep.count())
                    if "6 pistas" in sep.itemText(i).lower()),-1)
                if six>=0:
                    sep.setCurrentIndex(six)
                    self.result_hint.setText(
                        "Modelo cambiado a Demucs de 6 pistas para separar guitarra y piano.")
        if enabled and name=="Viento":
            self.result_hint.setText(
                "Viento seleccionado, pero los modelos instalados no lo aíslan. "
                "No se fabricará una pista de viento a partir de Otros.")
        self._show_tracks()
        self.apply_stem_visibility()

    def apply_stem_visibility(self):
        # El modelo Demucs genera todas sus salidas conjuntamente.
        # Las casillas deciden cuáles quedan marcadas para guardar;
        # las demás siguen disponibles, sin borrarse del área temporal.
        for line in self.workbench.sep_results.lines:
            category=self._stem_for(line.path)
            line.checked.setChecked(
                self._stem_selection.get(category,True) and
                self.stem_checks.get(category).isChecked())

    def run_separation(self):
        sep=self.workbench.separator
        if not Path(sep.file_edit.text().strip()).is_file():
            if not self._is_float(self.sep_card):
                self.main.tabs.setCurrentWidget(self.workbench.separation_tab)
            QMessageBox.information(self,"Selecciona el audio",
                "Importa primero el archivo que deseas separar.")
            return
        sep.start_separation()
        self._tick()

    def select_engine(self,index):
        if self._loading:return
        self.workbench.converter.piano_specialist.setChecked(
            self.engine.itemData(index)=="transkun")

    def choose_midi_preset(self,index):
        if self._loading:return
        target=self.workbench.converter.presets.choices
        data=self.midi_preset.itemData(index)
        for i in range(target.count()):
            if target.itemData(i)==data:
                target.setCurrentIndex(i)
                self._sync_midi_controls()
                return

    def _sync_midi_controls(self):
        converter=self.workbench.converter
        self._loading=True
        try:
            for key,w in self.midi_sliders.items():
                value=getattr(converter,key).value()
                if abs(w.value()-value)>.001:w.setValue(value)
            self._link_combo(converter.refinement,self.refine)
            self._link_combo(converter.quant,self.quant)
            i=self.engine.findData("transkun" if converter.piano_specialist.isChecked()
                                   else "basic")
            if i>=0:self.engine.setCurrentIndex(i)
            self.quant_check.setChecked(converter.quant.currentData() not in ("off",None))
            self.chords_check.setChecked(converter.detect_chords.isChecked())
            self.chords_check.setEnabled(not converter.use_folder.isChecked())
        finally:self._loading=False

    def toggle_chord_analysis(self,enabled):
        if self._loading:return
        self.workbench.converter.detect_chords.setChecked(bool(enabled))

    def change_midi_parameter(self,name,value):
        if self._loading:return
        converter=self.workbench.converter
        widget=getattr(converter,name)
        widget.setValue(value)

    def select_refinement(self,index):
        if self._loading:return
        converter=self.workbench.converter
        v=self.refine.itemData(index)
        i=converter.refinement.findData(v)
        if i>=0:converter.refinement.setCurrentIndex(i)

    def toggle_quant(self,active):
        if self._loading:return
        if not active:
            idx=self.workbench.converter.quant.findData("off")
            if idx>=0:self.workbench.converter.quant.setCurrentIndex(idx)
        else:
            self.select_quant(self.quant.currentIndex())

    def select_quant(self,index):
        if self._loading or not self.quant_check.isChecked():return
        q=self.quant.itemData(index)
        idx=self.workbench.converter.quant.findData(q)
        if idx>=0:self.workbench.converter.quant.setCurrentIndex(idx)

    def run_midi(self):
        converter=self.workbench.converter
        source=Path(converter.audio_path.text().strip())
        if not converter.use_folder.isChecked() and not source.is_file():
            if not self._is_float(self.midi_card):
                self.main.tabs.setCurrentWidget(self.workbench.midi_tab)
            QMessageBox.information(self,"Selecciona el audio",
                    "Importa un archivo de audio antes de convertirlo.")
            return
        converter.start_conversion()
        self._tick()

    def _result_tab(self,index):
        self.result_pages.setCurrentIndex(index)
        for i in range(3):
            btn=getattr(self,"results_btn_"+str(i))
            btn.setChecked(i==index)

    def file_selected(self):
        row=self.files.currentRow()
        if row<0:return
        item=self.files.item(row,0)
        if not item:return
        path=Path(item.data(Qt.UserRole))
        self.selected_file=path
        duration=self._result_duration(path)
        self.audio_progress.setText(f"00:00 / {duration}" if duration!="—" else "00:00 / 00:00")
        self.result_preview.setText(f"Archivo: {path.name}\n"
            "Pulsa ▶ para escucharlo o haz doble clic para editar un MIDI.")
        self.result_wave.set_file(path if path.suffix.lower() in AUDIO else None)
        if path.suffix.lower() in AUDIO:
            self.wave.set_file(path)
            self.overview.set_file(path)
            self.wave_title.setText(path.name)

    def file_double_clicked(self,row,col):
        if self._is_float(self.result_card):
            item=self.files.item(row,0)
            if item is not None:
                source=Path(item.data(Qt.UserRole))
                if source.is_file():
                    self.selected_file=source
                    if source.suffix.lower() in MIDI:
                        self.selected_midi=source
                        self.piano_preview.set_midi(source)
                        self._update_midi_stats(source)
                    else:self.player.load(source,autoplay=True)
            return
        item=self.files.item(row,0)
        if not item:return
        file=Path(item.data(Qt.UserRole))
        if file.suffix.lower() in MIDI:
            self.workbench.show_piano_roll(file)
        elif file.suffix.lower() in AUDIO:
            self.player.load(file,autoplay=True)

    def play_selected(self):
        if self.selected_file and self.selected_file.is_file():
            if self.player.current_file!=str(self.selected_file):
                self.player.load(self.selected_file,autoplay=True)
            else:self.player.play_pause()
        else:
            self.result_hint.setText("Selecciona primero una pista de audio o MIDI.")

    def stop_audio(self):
        if self.player is not None:self.player.stop()

    def pause_selected(self):
        if self.player is not None and self.selected_file is not None:
            if str(self.player.current_file)==str(self.selected_file):
                self.player.play_pause()
            else:self.play_selected()

    def open_results_folder(self):
        """Abrir la carpeta REAL del resultado, nunca mover archivos."""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        candidate=self.selected_file if self.selected_file and self.selected_file.is_file() else None
        if candidate is None:
            sources=(self.workbench.separation_storage,self.workbench.midi_storage)
            candidate=next((s.composite for s in sources
                if s.composite and s.composite.is_file()),None)
            if candidate is None:
                candidate=next((Path(x) for s in sources for x in s.items
                    if Path(x).is_file()),None)
        if candidate is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(candidate).parent)))
        else:
            QMessageBox.information(self,"Abrir carpeta",
                  "Todavía no existe ninguna pista guardada o temporal.")

    def _sync_player(self):
        if self.player is None:return
        self.result_hint.setText(Path(self.player.current_file).name
           if self.player.current_file else "")
        if self.selected_file is not None and str(self.player.current_file)==str(self.selected_file):
            self.audio_progress.setText(self.player.clock.text())

    def seek_audio_fraction(self,fraction):
        if self.player is None:return
        if self.wave.zoom_factor>1:
            self.wave.set_view_start(fraction-.5/self.wave.zoom_factor)
            self.overview.selection_start=self.wave.view_start
            self.overview.update()
        # El original de la forma de onda, no un MIDI seleccionado en Resultados.
        source=self.wave.source
        if source is not None and source.is_file():
            if str(self.player.current_file)!=str(source):
                self.player.load(source,autoplay=False)
        elapsed=round(fraction*self.player._duration_ms)
        self.player._set_clock(elapsed)
        if self.player.current_file is not None:
            self.player.slider.setValue(round(fraction*1000))
            if self.player._play_process is not None:
                self.player._start_audio(elapsed)

    def _selected_results(self):
        rows=sorted({index.row() for index in self.files.selectionModel().selectedRows()})
        results=[]
        for row in rows:
            item=self.files.item(row,0)
            if item is not None:
                results.append(Path(item.data(Qt.UserRole)))
        return results

    def _save_results(self,selected):
        if not selected:
            QMessageBox.information(self,"Guardar resultados",
                "Selecciona una o varias pistas de la tabla.")
            return []
        from export_dialog import export_files
        output=export_files(self,selected,getattr(self.main,"project_dir",None),
                            "Guardar resultados")
        if output:
            for store in (self.workbench.separation_storage,
                          self.workbench.drum_storage,
                          self.workbench.vocal_storage,self.workbench.midi_storage):
                if store.folder:
                    for p in selected:
                        if store.folder.resolve() in Path(p).resolve().parents:
                            store.saved.add(str(p))
                    store.manifest()
            self.result_hint.setText(f"Exportados {len(output)} resultado(s).")
        return output

    def export_selected(self):
        return self._save_results(self._selected_results())

    def export_all(self):
        return self._save_results(self._gather_files())

    def discard_results(self,kind):
        """Utilizar la validación y confirmación del gestor de tareas."""
        if kind not in ("separaciones","midi"):return
        discarded=self.workbench.discard_job(kind)
        if not discarded:return
        if self.player is not None:
            self.player.clear()
        self.selected_file=None
        self.selected_midi=None if kind=="midi" else self.selected_midi
        self._known_state=None
        self.refresh(force=True)
        self.result_hint.setText("Resultados temporales descartados; originales intactos.")

    def export_results(self):
        self.workbench.sep_results.populate()
        self.workbench.midi_results.populate()
        self.open_results()
        QMessageBox.information(self,"Exportar resultados",
            "Selecciona las pistas y pulsa «Guardar selección» o «Guardar todo» "
            "en el panel de resultados. Los originales permanecerán intactos.")

    def open_results(self):
        if self._is_float(self.result_card) or self._is_float(self.track_card):
            self.refresh(force=True)
            return
        self.workbench.sep_results.populate()
        self.workbench.midi_results.populate()
        # El área de Resultados permite acceder a ambos grupos.
        results=getattr(self.main,"results_tab",None)
        if results is not None:
            self.main.tabs.setCurrentWidget(results)
        else:self.main.tabs.setCurrentWidget(self.workbench.saved_audio)

    def open_audio(self):
        if self._is_float(self.wave_card):
            self.wave.update()
            return
        path=self.selected_file
        if path and path.suffix.lower() in MIDI:
            self.workbench.show_piano_roll(path)
        else:
            self.main.tabs.setCurrentWidget(self.workbench.separation_tab)

    def _stem_for(self,path):
        import re
        stem=Path(path).stem.casefold()
        tokens=[x for x in re.split(r"[^a-záéíóúñ0-9]+",stem) if x]
        candidates=set(tokens)
        # Demucs suele exportar 'vocals.flac', 'drums.flac', 'bass.flac',
        # 'other.flac', 'guitar.flac' y 'piano.flac', SIN prefijos.
        def match(*names):
            return any(n in candidates or stem==n for n in names)
        if match("vocals","vocal","voice","voices","voces","voz"):
            return "Voces"
        if match("drums","drum","bateria","batería","percussion"):
            return "Batería"
        if match("bass","bajo","bajos"):
            return "Bajo"
        if match("guitar","guitars","guitarra","guitarras"):
            return "Guitarra"
        if match("piano","keys","keyboard"):
            return "Piano"
        if match("wind","winds","brass","woodwind","viento","vientos"):
            return "Viento"
        return "Otros"

    def _show_tracks(self):
        items=[Path(p) for p in self.workbench.separation_storage.items
               if Path(p).is_file()]
        sources={self._stem_for(path):path for path in items}
        for name,parts in self.track_rows.items():
            file=sources.get(name)
            parts["path"]=file
            display=bool(file) and self._stem_selection.get(name,True)
            parts["wave"].set_file(file if display else None)
            parts["solo"].setEnabled(display)
            parts["mute"].setEnabled(display)
            parts["gain"].setEnabled(display)
            parts["play"].setEnabled(display)
            parts["stop"].setEnabled(display)
            if not display:
                parts["solo"].setChecked(False)
                parts["mute"].setChecked(False)
        self._track_lookup=sources

    def play_stem(self,name,fraction=0.):
        part=self.track_rows.get(name)
        if not part or not part["path"] or not part["path"].is_file():
            return
        if part["mute"].isChecked() or (
            any(r["solo"].isChecked() for r in self.track_rows.values())
            and not part["solo"].isChecked()):
            self.result_hint.setText(f"{name}: silenciado o fuera de Solo")
            return
        self.selected_file=part["path"]
        self.player.load(part["path"],autoplay=True)
        self.player.volume.setValue(min(100,round(
            self.master_volume.value()*part["gain"].value()/100)))
        if fraction and self.player._duration_ms:
            self.seek_audio_fraction(fraction)

    def stop_stem(self,name):
        """Detener una pista no interrumpe una grabación ni otra pista."""
        part=self.track_rows.get(name)
        if (part and part["path"] and self.player is not None
                and self.player.current_file==str(part["path"])):
            self.player.stop()
            self.result_hint.setText(f"{name}: reproducción detenida")

    def mix_changed(self,name):
        if self._loading:return
        track=self.track_rows[name]
        if (self.player is not None and
            self.selected_file==track["path"] and
            (track["mute"].isChecked() or
              any(v["solo"].isChecked() for v in self.track_rows.values()
                  if v is not track) and not track["solo"].isChecked())):
            self.player.stop()
        if self.workbench.mixer is not None:
            for item in self.workbench.mixer.rows:
                if self._stem_for(item["path"])!=name:continue
                item["slider"].setValue(track["gain"].value())
                item["solo"].setChecked(track["solo"].isChecked())
                item["mute"].setChecked(track["mute"].isChecked())
                return

    def change_mix(self,name,value):
        self._mix_levels[name]=value
        widget=self.mixer_rows[name]["readout"]
        if value<=0:description="−∞ dB"
        else:description=f"{20*math.log10(value/100):+.1f} dB"
        widget.setText(description)
        old=self.track_rows[name]["gain"].blockSignals(True)
        self.track_rows[name]["gain"].setValue(value)
        self.track_rows[name]["gain"].blockSignals(old)
        self.mix_changed(name)

    def reset_mixer(self):
        for name,control in self.mixer_rows.items():
            control["fader"].setValue(100)
            self.track_rows[name]["solo"].setChecked(False)
            self.track_rows[name]["mute"].setChecked(False)

    def _is_float(self,card):
        manager=getattr(self,"_floating_manager",None)
        return bool(manager and manager.is_detached(card))

    def open_mixer(self):
        if self._is_float(self.mix_card):
            self._show_tracks()
            self.result_hint.setText("Mezclador de Inicio: faders, reproducción y VU disponibles aquí.")
            return
        sources=[p for p in self.workbench.separation_storage.items if Path(p).is_file()]
        if not sources:
            self.main.tabs.setCurrentWidget(self.workbench.separation_tab)
            QMessageBox.information(self,"Mezclador",
                "Separa primero un archivo para obtener pistas independientes.")
            return
        self.workbench.show_mixer(sources)
        mix=self.workbench.mixer
        if mix is None:return
        for row in mix.rows:
            name=self._stem_for(row["path"])
            if name not in self.track_rows:continue
            data=self.track_rows[name]
            row["slider"].setValue(data["gain"].value())
            row["solo"].setChecked(data["solo"].isChecked())
            row["mute"].setChecked(data["mute"].isChecked())

    def _roll_scroll_changed(self,fraction):
        old=self.roll_position.blockSignals(True)
        self.roll_position.setValue(int(fraction*1000))
        self.roll_position.blockSignals(old)

    def step_piano(self,bars):
        if not self.selected_midi:return
        self.piano_preview.view_start=max(0,min(
            self.piano_preview.full_tick-self.piano_preview.visible_ticks,
            self.piano_preview.view_start+bars*4*self.piano_preview.ticks_per_beat))
        self.piano_preview.update()
        self._roll_scroll_changed(
            self.piano_preview.view_start/max(1,self.piano_preview.full_tick-self.piano_preview.visible_ticks))

    def choose_midi(self,index):
        if self._loading:return
        path=self.midi_choice.itemData(index)
        if not path:return
        candidate=Path(path)
        if not candidate.is_file():return
        self.selected_midi=candidate
        self.piano_preview.set_midi(candidate)
        self._roll_scroll_changed(0)
        self._update_midi_stats(candidate)
        self.piano_card.header.setText("Piano Roll · "+candidate.name)

    def change_grid(self,text):
        combo=self.workbench.piano.grid
        index=combo.findText(text)
        if index>=0:combo.setCurrentIndex(index)

    def change_velocity(self,value):
        self.vel_value.setText(str(value))
        editor=self.workbench.piano
        if hasattr(editor,"velocity"):editor.velocity.setValue(value)

    def seek_piano(self,fraction):
        if self._is_float(self.piano_card):
            if self.selected_midi and self.selected_midi.is_file():
                self.piano_preview.set_scroll(max(0.,min(1.,float(fraction))))
            return
        if self.selected_midi and self.selected_midi.is_file():
            self.workbench.show_piano_roll(self.selected_midi)
            editor=self.workbench.piano
            if editor.midi is not None:
                tick=self.piano_preview.view_start+round(fraction*self.piano_preview.visible_ticks)
                editor.seek_tick(tick)

    def open_piano(self):
        if self._is_float(self.piano_card) or self._is_float(self.info_card):
            if self.selected_midi and self.selected_midi.is_file():
                self.piano_preview.set_midi(self.selected_midi)
                self._update_midi_stats(self.selected_midi)
            return
        if self.selected_midi and self.selected_midi.is_file():
            self.workbench.show_piano_roll(self.selected_midi)
        else:
            self.main.tabs.setCurrentWidget(self.workbench.piano)

    def _update_midi_stats(self,path):
        try:
            import mido
            midi=mido.MidiFile(path)
            notes=[]
            tempo=500000
            for track in midi.tracks:
                for msg in track:
                    if msg.type=="set_tempo":tempo=msg.tempo
                    if msg.type=="note_on" and msg.velocity>0:notes.append(msg.note)
            self.note_info.setText(f"Notas: {len(notes):,}".replace(",","."))
            seconds=midi.length
            self.duration_info.setText(
                f"Duración: {int(seconds//60):02d}:{int(seconds%60):02d}")
            self.tempo_info.setText(f"Tempo: {60000000/tempo:.1f} BPM")
            if notes:
                # Análisis tonal aproximado por clases de altura;
                # no se presenta como tonalidad certificada.
                pcs=[notes.count(n) for n in range(12)]
                histogram=[sum(1 for p in notes if p%12==i) for i in range(12)]
                major=[6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]
                minor=[6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17]
                matches=[]
                for tonic in range(12):
                    for pattern,mode in ((major,"mayor"),(minor,"menor")):
                        score=sum(pattern[(i-tonic)%12]*histogram[i] for i in range(12))
                        matches.append((score,tonic,mode))
                _,key,mode=max(matches)
                names=["Do","Do♯","Re","Mi♭","Mi","Fa","Fa♯","Sol","La♭","La","Si♭","Si"]
                self.key_info.setText(f"Tonalidad: {names[key]} {mode}*")
                self.key_info.setToolTip("* Estimación estadística, no confirmación tonal.")
            else:self.key_info.setText("Tonalidad: —")
        except (ValueError,OSError):
            self.note_info.setText("Notas: —")
            self.duration_info.setText("Duración: —")
            self.tempo_info.setText("Tempo: —")
            self.key_info.setText("Tonalidad: —")

    def _sync_separator(self):
        src=self.workbench.separator.profile
        if self.model.count()!=src.count():
            old=self.model.blockSignals(True)
            self.model.clear()
            for i in range(src.count()):
                full=src.itemText(i)
                lower=full.lower()
                if "melband" in lower:label_="Voces · MelBand Roformer"
                elif "4 pistas" in lower and "rápido" in lower:label_="Demucs · 4 pistas rápido"
                elif "4 pistas" in lower:label_="Demucs FT · 4 pistas estudio"
                elif "6 pistas" in lower:label_="Demucs · 6 pistas"
                elif "mdx" in lower:label_="MDX · voz / instrumental"
                elif "canales" in lower:label_="Estéreo · izq / der"
                else:label_=full
                self.model.addItem(label_,full)
                self.model.setItemData(i,full,Qt.ToolTipRole)
            self.model.blockSignals(old)
        chosen=self.model.findData(src.currentText())
        if chosen>=0 and self.model.currentIndex()!=chosen:
            old=self.model.blockSignals(True)
            self.model.setCurrentIndex(chosen)
            self.model.blockSignals(old)
        self._sync_stem_capabilities()

    def _sync_preset(self):
        src=self.workbench.converter.presets.choices
        if self.midi_preset.count()!=src.count():
            was=self.midi_preset.blockSignals(True)
            self.midi_preset.clear()
            for i in range(src.count()):
                self.midi_preset.addItem(src.itemText(i),src.itemData(i))
            self.midi_preset.blockSignals(was)
        index=self.midi_preset.findData(src.currentData())
        if index>=0:
            before=self.midi_preset.blockSignals(True)
            self.midi_preset.setCurrentIndex(index)
            self.midi_preset.blockSignals(before)

    def _sync_engine(self):
        converter=self.workbench.converter
        self._loading=True
        if self.refine.count()!=converter.refinement.count():
            self.refine.clear()
            for i in range(converter.refinement.count()):
                full=converter.refinement.itemText(i)
                short=("Equilibrado" if "Equilibrado" in full else
                       "Rigor alto" if "Rigor" in full else "Desactivado")
                self.refine.addItem(short,converter.refinement.itemData(i))
                self.refine.setItemData(i,full,Qt.ToolTipRole)
        if self.quant.count()!=converter.quant.count():
            self.quant.clear()
            for i in range(converter.quant.count()):
                full=converter.quant.itemText(i)
                value=converter.quant.itemData(i)
                short="Sin cuantizar" if value in (None,"off") else str(value)
                self.quant.addItem(short,value)
                self.quant.setItemData(i,full,Qt.ToolTipRole)
        self._loading=False
        self._sync_midi_controls()

    def _gather_files(self):
        work=self.workbench
        path_list=[]
        for p in work.separation_storage.items:
            path=Path(p)
            if path.is_file():path_list.append(path)
        for p in work.drum_storage.items:
            path=Path(p)
            if path.is_file():path_list.append(path)
        for p in work.vocal_storage.items:
            path=Path(p)
            if path.is_file():path_list.append(path)
        for p in work.midi_storage.items:
            path=Path(p)
            if path.is_file():path_list.append(path)
        for version in work.midi_storage.versions:
            path=Path(version["composite"])
            if path.is_file():path_list.append(path)
        # Resultados = temporales + trabajos guardados + grabaciones del
        # proyecto ACTIVO; nunca archivos de la biblioteca global de otro.
        project=getattr(self.main,"project_dir",None)
        if project:
            project=Path(project).resolve()
            from project_layout import layout_active,module_dir,MODULES
            if layout_active(project):
                # Mostrar resultados definitivos, no ZIP del historial ni
                # duplicados dentro de backup.
                sources=[project/name for name in dict.fromkeys(MODULES.values())]
            else:
                sources=[project/"backup"]
            for folder in sources:
                if folder.is_dir():
                    for saved in folder.iterdir() if layout_active(project) else folder.rglob("*"):
                        if (saved.is_file() and not saved.is_symlink()
                            and saved.suffix.lower() in (AUDIO | MIDI)):
                            path_list.append(saved)
            recorded=project/"grabaciones"
            if recorded.is_dir():
                for audio in recorded.iterdir():
                    if (audio.is_file() and not audio.is_symlink()
                        and audio.suffix.lower() in AUDIO):
                        path_list.append(audio)
        unique={}
        for p in path_list:unique[str(p.resolve())]=p
        return list(unique.values())

    def _update_results(self,paths):
        old=self.selected_file
        was=self.files.blockSignals(True)
        self.files.setRowCount(len(paths))
        stem_list={str(p):self._stem_for(p) for p in self.workbench.separation_storage.items}
        versions=[str(v["composite"]) for v in self.workbench.midi_storage.versions]
        for row,path in enumerate(paths):
            kind="MIDI" if path.suffix.lower() in MIDI else "Audio"
            if str(path) in stem_list:
                shown=stem_list[str(path)]+path.suffix.lower()
            elif str(path) in versions:
                shown=f"Toma {versions.index(str(path))+1:02d} · {path.name}"
            else:
                shown=path.name
                if len(shown)>37:
                    shown=shown[:21]+"…"+path.suffix.lower()
            # Iconos coloreados por familia, sin modificar el archivo.
            kind_color=COLORS.get(stem_list.get(str(path),""),
                                 "#ad55eb" if kind=="MIDI" else "#168bde")
            from PySide6.QtGui import QPixmap, QIcon
            pix=QPixmap(20,20)
            pix.fill(Qt.transparent)
            painter=QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qc(kind_color))
            painter.drawRoundedRect(QRectF(1,1,18,18),4,4)
            painter.setPen(Qc("#ffffff"))
            f=painter.font();f.setPointSize(11);f.setBold(True);painter.setFont(f)
            painter.drawText(pix.rect(),Qt.AlignCenter,"♫" if kind=="MIDI" else "♪")
            painter.end()
            for col,value in enumerate((shown,kind,self._result_duration(path))):
                item=QTableWidgetItem(value)
                if col==0:
                    item.setIcon(QIcon(pix))
                    item.setData(Qt.UserRole,str(path))
                    item.setToolTip(str(path))
                self.files.setItem(row,col,item)
        self.files.blockSignals(was)
        for row in range(len(paths)):
            self.files.setRowHeight(row,28)
        if old is not None:
            for row,p in enumerate(paths):
                if old.resolve()==p.resolve():
                    self.files.selectRow(row);break
        elif paths:self.files.selectRow(0)
        results=getattr(self.main,"results_tab",None)
        if results is not None and hasattr(results,"refresh"):
            results.refresh(paths)
        self.result_about.setText(
            f"{len(paths)} archivos temporales disponibles.\n"
            "Selecciona una pista para escucharla o abrir el Piano Roll. "
            "Guardar resultados se realiza sin sobrescribir los originales.")

    def _result_duration(self,path):
        if path.suffix.lower() in MIDI:
            try:
                import mido
                val=mido.MidiFile(path).length
                return f"{int(val//60):02d}:{int(val%60):02d}"
            except (OSError,ValueError):return "—"
        try:
            from audio_import import probe_audio
            inf=probe_audio(path)
            val=float(inf.get("duration",0))
            if val:return f"{int(val//60):02d}:{int(val%60):02d}"
        except (OSError,ValueError,AttributeError,TypeError):pass
        return "—"

    def refresh(self,force=False):
        work=self.workbench
        self._loading=True
        self._sync_monitor()
        self._sync_separator()
        self._sync_drum_module()
        self._sync_vocal_module()
        self._sync_preset()
        self._sync_engine()
        self._loading=False
        if self.quality.currentIndex()!=self.main.capture_rate.currentIndex():
            was=self.quality.blockSignals(True)
            self.quality.setCurrentIndex(self.main.capture_rate.currentIndex())
            self.quality.blockSignals(was)
        paths=self._gather_files()
        signature=tuple((str(p),p.stat().st_size) for p in paths)
        if force or signature!=self._known_state:
            self._known_state=signature
            self._update_results(paths)
            self._show_tracks()
            midis=[p for p in paths if p.suffix.lower() in MIDI]
            self._loading=True
            self.midi_choice.clear()
            for p in midis:
                self.midi_choice.addItem(p.name,str(p))
            if midis:
                if self.selected_midi and self.selected_midi in midis:
                    index=midis.index(self.selected_midi)
                else:index=len(midis)-1
                self.midi_choice.setCurrentIndex(index)
            self._loading=False
            if midis:self.choose_midi(self.midi_choice.currentIndex())
            else:
                self.selected_midi=None
                self.piano_preview.set_midi(None)
                self.piano_card.header.setText("Piano Roll · MIDI")
                for item in (self.note_info,self.duration_info,
                             self.tempo_info,self.key_info):
                    item.setText("—")
            audio=self._source_for_wave(paths)
            self.wave.set_file(audio)
            self.overview.set_file(audio)
            self.wave_title.setText(audio.name if audio else "Sin audio seleccionado")
            if self.files.currentRow()<0 and paths:
                self.files.selectRow(len(paths)-1)
        self._update_buttons()

    def reset_project_view(self):
        """Pantalla de proyecto limpio, sin representaciones heredadas."""
        if self.player is not None:self.player.clear()
        self.selected_file=None
        self.selected_midi=None
        self._known_state=None
        self.files.clearSelection()
        self.files.setRowCount(0)
        self.wave.set_file(None)
        self.overview.set_file(None)
        self.wave_title.setText("Sin audio seleccionado")
        self.piano_preview.set_midi(None)
        self.piano_card.header.setText("Piano Roll · MIDI")
        self.midi_choice.clear()
        self.note_info.setText("Notas: —")
        self.duration_info.setText("Duración: —")
        self.tempo_info.setText("Tempo: —")
        self.key_info.setText("Tonalidad: —")
        self.audio_progress.setText("00:00 / 00:00")
        self.result_hint.setText("")
        self._drum_known=None
        self._sync_drum_module(force=True)
        self._sync_vocal_module(force=True)
        self._sync_drum_stems()
        for name,part in self.track_rows.items():
            part["wave"].set_file(None)
            part["path"]=None
            for key in ("solo","mute"):
                was=part[key].blockSignals(True)
                part[key].setChecked(False)
                part[key].blockSignals(was)
            for key in ("play","stop","solo","mute"):
                part[key].setEnabled(False)
            self.mixer_rows[name]["meter"].set_level(0)

    def _source_for_wave(self,paths):
        possibilities=[
            self.workbench.separator.file_edit.text(),
            self.workbench.converter.audio_path.text(),
            self.main.last_file
        ]
        for p in possibilities:
            if p:
                file=Path(p)
                if file.is_file() and file.suffix.lower() in AUDIO:return file
        return next((p for p in paths if p.suffix.lower() in AUDIO),None)

    def _update_buttons(self):
        self.sep_run.setEnabled(not self.workbench.separator.busy)
        self.midi_run.setEnabled(self.workbench.converter.process is None)
        self._sync_monitor()

    def _tick(self):
        self.refresh()
        self._sync_player()
        if self.player is not None and self.player._duration_ms:
            fraction=self.player._position()/self.player._duration_ms
            self.wave.set_cursor(fraction)
            self.overview.set_cursor(fraction)
            playing=self.player._play_process is not None or self.player._qt_active
            for name,details in self.mixer_rows.items():
                stem=self.track_rows[name]["wave"]
                audible=(self.selected_file is not None
                         and self.selected_file==self.track_rows[name]["path"]
                         and not self.track_rows[name]["mute"].isChecked()
                         and (not any(z["solo"].isChecked() for z in self.track_rows.values())
                              or self.track_rows[name]["solo"].isChecked()))
                if playing and audible and stem.data:
                    location=min(len(stem.data)-1,max(0,int(fraction*len(stem.data))))
                    sample=max(stem.data[max(0,location-8):
                         min(len(stem.data),location+8)] or [0.])
                    peak=getattr(stem,"_normalizer",1.)
                    level=(sample/max(peak,.001))**.75
                    details["meter"].set_level(level)
                else:
                    details["meter"].set_level(0.)
        else:
            for item in self.mixer_rows.values():item["meter"].set_level(0.)

    def sync_capture_levels(self,left,right,peak_l,peak_r):
        self.level_meter.set_levels(peak_l,peak_r)
        if hasattr(self,"record_transport"):
            self.record_transport.set_levels(left,right,peak_l,peak_r)
