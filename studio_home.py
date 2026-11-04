"""Pantalla Inicio de StemMIDI Studio, vinculada a los motores y tareas reales.

Los gráficos representan únicamente datos cargados de archivos reales o
datos medidos por el monitor, nunca sonidos o resultados simulados.
"""
from __future__ import annotations
import file_dialogs
import json, math, struct, subprocess, os, time
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF, QProcess, QTimer, QSignalBlocker, Signal
from PySide6.QtGui import (
    QColor, QBrush, QPen, QPainter, QFont, QLinearGradient, QPainterPath,
    QPixmap
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
        # El raster completo de la onda se construye una sola vez por
        # archivo/zoom/tamaño. El movimiento solo desplaza un QPixmap.
        self._wave_cache=None
        self._wave_cache_key=None
        self._wave_tiles={}
        self._wave_peak_key=None
        self._wave_peak=.5
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
        self._wave_tiles.clear()
        self._wave_cache=None
        self._wave_cache_key=None
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
            # Conservar detalle de muestras también a ×50 sin sobrecargar el repintado.
            step=max(1,size//80000)
            self.data=[abs(x[0]) for x in struct.iter_unpack("<f",data[:size*4])][::step]
            self.duration_seconds=size/320.0
        self.processor=None
        self._wave_tiles.clear()
        self._wave_cache=None
        self._wave_cache_key=None
        try:proc.deleteLater()
        except RuntimeError:pass
        self.update()
    def set_cursor(self,fraction):
        self.cursor=max(0.,min(1.,float(fraction)))
        self.update()
    def set_zoom(self,value):
        previous=self.zoom_factor
        self.zoom_factor=max(1,min(50,int(value)))
        self.view_start=max(0.,min(1-1/self.zoom_factor,self.view_start))
        if previous!=self.zoom_factor:
            self._wave_tiles.clear()
            self._wave_cache=None
            self._wave_cache_key=None
        self.update()
    def set_view_start(self,fraction):
        self.view_start=max(0.,min(1-1/self.zoom_factor,float(fraction)))
        self.update()

    def follow_playhead(self,fraction,anchor=.75):
        """Desplazar la ventana visible con el audio; no cambiar el zoom.

        Mientras avanza la reproducción, el cursor se mantiene alrededor
        del 75 % del ancho. Al llegar al final, la vista se detiene
        exactamente en el último tramo de la onda.
        """
        if self.small or self.zoom_factor<=1:
            return False
        fraction=max(0.,min(1.,float(fraction)))
        span=1./self.zoom_factor
        left=self.view_start
        if fraction>=left+span*anchor:
            new_left=min(1.-span,max(0.,fraction-span*anchor))
        elif fraction<left:
            # Salto de reproducción hacia atrás: volver a mostrar la guía.
            new_left=max(0.,fraction-span*.20)
        else:
            return False
        if abs(new_left-left)<=1e-7:
            return False
        self.set_view_start(new_left)
        return True

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            fx=max(0.,min(1.,event.position().x()/max(1,self.width())))
            fraction=fx if self.small else self.view_start+fx/self.zoom_factor
            self.set_cursor(fraction)
            self.clicked.emit(fraction)
    def wheelEvent(self,event):
        if event.modifiers() & Qt.ControlModifier:
            self.set_zoom(max(1,min(50,self.zoom_factor+
                         (1 if event.angleDelta().y()>0 else -1))))
        elif event.modifiers() & Qt.ShiftModifier:
            self.set_view_start(self.view_start-event.angleDelta().y()/120*
                                (.05/self.zoom_factor))
        self.update()
        event.accept()
    def _cached_waveform(self,width,height,tile_index=0):
        """Raster por bloques: evita pixmaps gigantes incluso a zoom ×50.

        Solo se mantienen unos pocos tramos adyacentes del audio. En un
        desplazamiento cada fotograma reutiliza imágenes estáticas; un
        nuevo tramo solo se genera cuando entra por un borde.
        """
        if not self.data:return None
        zoom=1 if self.small else max(1,self.zoom_factor)
        total_width=width*zoom
        tile_width=2048
        start=tile_index*tile_width
        if start>=total_width:return None
        count=min(tile_width,total_width-start)
        key=(id(self.data),len(self.data),total_width,height,self.small,
             self.wave_color)
        if key!=self._wave_cache_key:
            self._wave_tiles.clear()
            self._wave_cache_key=key
            self._wave_peak_key=None
        tile=self._wave_tiles.get(tile_index)
        if tile is not None:return tile
        if self._wave_peak_key!=id(self.data):
            peak=max(.001,sorted(self.data)[
                min(len(self.data)-1,int(len(self.data)*.98))])
            self._normalizer=peak
            self._wave_peak=peak
            self._wave_peak_key=id(self.data)
        else:peak=self._wave_peak
        raster=QPixmap(count,height)
        raster.fill(Qt.transparent)
        painter=QPainter(raster)
        painter.setRenderHint(QPainter.Antialiasing,False)
        blue=Qc(self.wave_color)
        highlight=Qc("#7bdfff")
        middle=height*.53
        scale=height*(.40 if not self.small else .37)
        total=len(self.data)
        for local_x in range(count):
            global_x=start+local_x
            sample_start=global_x*total//total_width
            sample_stop=max(sample_start+1,(global_x+1)*total//total_width)
            sample=max(self.data[sample_start:min(sample_stop,total)] or [0])
            extent=min(scale,max(0.,(sample/peak)**.78*scale))
            painter.setPen(QPen(blue,1.3 if not self.small else 1))
            painter.drawLine(local_x,int(middle-extent),local_x,int(middle+extent))
            if not self.small and extent>2:
                painter.setPen(QPen(highlight,.7))
                painter.drawLine(local_x,int(middle-extent*.83),
                                 local_x,int(middle-extent))
        painter.end()
        self._wave_tiles[tile_index]=raster
        if len(self._wave_tiles)>6:
            # Descartar el bloque más alejado de la zona de reproducción.
            farthest=max(self._wave_tiles,key=lambda k:abs(k-tile_index))
            if farthest!=tile_index:self._wave_tiles.pop(farthest,None)
        self._wave_cache=raster
        return raster

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
            scale=1 if self.small else self.zoom_factor
            first_x=0. if self.small else self.view_start*w*scale
            last_x=first_x+w
            tile_size=2048
            p.setRenderHint(QPainter.SmoothPixmapTransform,True)
            for tile_id in range(int(first_x//tile_size),
                                 int((last_x-1e-7)//tile_size)+1):
                tile=self._cached_waveform(w,h,tile_id)
                if tile is None:continue
                left=max(first_x,tile_id*tile_size)
                right=min(last_x,(tile_id+1)*tile_size)
                left_in_tile=left-tile_id*tile_size
                length=right-left
                if length>0:
                    p.drawPixmap(QRectF(left-first_x,0,length,h),tile,
                                 QRectF(left_in_tile,0,length,h))
            p.setRenderHint(QPainter.SmoothPixmapTransform,False)
        elif not self.small:
            p.setPen(Qc("#7099b0"))
            p.drawText(self.rect(),Qt.AlignCenter,"Selecciona un audio para ver su forma de onda")
        if self.small and self.selection>0 and self.data:
            xx=int(self.selection_start*w)
            ww=max(8,int(self.selection*w))
            p.fillRect(QRectF(xx,0,ww,h),QColor(14,150,237,35))
            p.setPen(QPen(Qc("#cceaff"),1.5))
            p.drawRect(QRectF(xx+1,1,min(ww,w-xx)-2,h-2))
        # Sólo en la tarjeta flotante de batería se traza también la
        # guía de reproducción sobre las seis ondas pequeñas originales.
        if not self.small or self.property("showPlaybackCursor"):
            cursor=(self.cursor-self.view_start)*self.zoom_factor
            if 0<=cursor<=1:
                x=int(cursor*w)
                p.setPen(QPen(Qc("#ff4f5c"),2))
                p.drawLine(x,0,x,h)
                p.setBrush(Qc("#ff5d65"));p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(x,5),4,4)
        p.end()

from studio_vu_unified import (Ballistics,draw_vertical,from_percent,db_fraction)

class VerticalMeter(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.levels=[0.,0.]
        self.setFixedWidth(39)
        self.setMinimumHeight(111)
    def set_levels(self,left,right):
        # Pico real de entrada en escala de −60 a 0 dBFS.
        # El multiplicador lineal ×3 exageraba niveles y los hacía
        # incongruentes con el resto de vúmetros.
        def fraction(v):
            db=20*math.log10(max(1e-8,float(v)))
            return max(0.,min(1.,(db+60.)/60))
        self.levels=[fraction(left),fraction(right)]
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
    """El antiguo medidor de pista no cambia de lugar ni de orientación."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.level=0.
        self._ballistics=Ballistics(1)
        self.setFixedWidth(11)
        self.setMinimumHeight(90)
        self.setToolTip("VU vertical del Monitor · escala −60 a 0 dBFS")
    def set_level(self,value):
        self.level=max(0.,min(1.,float(value)))
        # Entrada anterior: recorrido de escala dBFS [0..1], no PCM.
        amplitude=from_percent(self.level*100)
        self._ballistics.feed((amplitude,),(amplitude,))
        self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        draw_vertical(p,self.rect(),self._ballistics.shown,
                      self._ballistics.held,("L",),True)
        p.end()

class PianoOverview(QWidget):
    """Vista MIDI real: doce compases visibles y desplazamiento, sin miniaturizarlo entero."""
    activated=Signal(float)
    viewChanged=Signal(float)
    zoomChanged=Signal(int)
    pitchChanged=Signal(int,int)
    seekRequested=Signal(int)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumHeight(126)
        self.events=[]
        self._event_starts=[]
        self._max_note_duration=0
        self._selected_track=None
        self._follow_pause_until=0.
        self._pitch_manual=False
        self.full_tick=1
        self.visible_ticks=48*480
        self.ticks_per_beat=480
        self.view_start=0
        self.max_tick=1
        self.cursor_fraction=0.
        self.pitch_lo=48
        self.pitch_hi=84
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.playhead_tick=None
        self._manual_seek_active=False
        self.editor_owner=None
        self.selected_note_indices=set()
        # Multi-selección por pista y número de nota. Cada nota mantiene
        # su identidad incluso cuando hay varias pistas MIDI superpuestas.
        self.selected_note_keys=set()
        self._marquee_origin=None
        self._marquee_end=None
        self._marquee_base=set()
        self._marquee_moved=False
        self._marquee_ctrl_create=False
        self._marquee_tick0=0.
        self._marquee_pitch0=60.
        self._marquee_tick1=0.
        self._marquee_pitch1=60.
        self._edge_position=None
        self._seeking=False
        self._scroll_fraction=0.0
        self._pitch_scroll_fraction=0.0
        self._edge_timer=QTimer(self)
        self._edge_timer.setTimerType(Qt.PreciseTimer)
        self._edge_timer.setInterval(24)
        self._edge_timer.timeout.connect(self._scroll_drag_edge)
        self._drag_origin=None
        self._drag_notes=None
        self._drag_snapshot=False
        self.pencil_mode=False
        self._pencil_anchor=None
        self._pencil_tip=None
        self._pencil_pitch=None
        self.grid_division=16
        self.setToolTip("Trackpad: dos dedos izq./der. = desplazamiento temporal;"
                        " arriba/abajo = desplazamiento vertical de las 88 teclas."
                        " Ctrl+gesto = zoom horizontal · Alt+gesto = zoom vertical."
                        " Mayús+gesto = desplazamiento vertical.")

    def set_midi(self,path):
        self.events=[]
        self._event_starts=[]
        self._max_note_duration=0
        self.selected_note_indices.clear()
        self.selected_note_keys.clear()
        self._marquee_origin=None
        self._marquee_end=None
        self._drag_origin=None
        self._pencil_anchor=None
        self._pencil_tip=None
        self._pencil_pitch=None
        self._selected_track=None
        self.playhead_tick=None
        self._manual_seek_active=False
        self.full_tick=1
        self.view_start=0
        self.cursor_fraction=0.
        self.pitch_lo=48
        self.pitch_hi=84
        self._pitch_manual=False
        self._edge_timer.stop()
        self._seeking=False
        self._scroll_fraction=0.
        self._pitch_scroll_fraction=0.
        if not path or not Path(path).is_file():
            self.update()
            return
        try:
            from piano_roll import parse_file
            midi,tracks=parse_file(path)
            events=[n for tr in tracks for n in tr["notes"]]
            self._index_events(tracks)
            self.ticks_per_beat=midi.ticks_per_beat
            self.visible_ticks=midi.ticks_per_beat*48
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
        self.pitchChanged.emit(self.pitch_lo,self.pitch_hi-self.pitch_lo+1)
        self.zoomChanged.emit(100)
        self.update()

    def _index_events(self,tracks):
        """Índice de notas reales por pista para dibujo y clic, sin recorrer
        toda la composición en cada fotograma de reproducción.
        """
        import bisect
        entries=[dict(n,track_index=ti,note_index=ni)
                 for ti,tr in enumerate(tracks)
                 for ni,n in enumerate(tr["notes"])]
        entries.sort(key=lambda n:(n["start"],n["end"],n["track_index"],n["note_index"]))
        self.events=entries
        self._event_starts=[n["start"] for n in self.events]
        self._max_note_duration=max((n["end"]-n["start"] for n in self.events),default=0)

    def _visible_events(self):
        import bisect
        start=max(0,self.view_start-self._max_note_duration)
        a=bisect.bisect_left(self._event_starts,start)
        b=bisect.bisect_right(self._event_starts,self.view_start+self.visible_ticks)
        return self.events[a:b]

    def hold_follow(self,seconds=3.):
        import time
        self._follow_pause_until=time.monotonic()+seconds

    def follow_tick(self,tick):
        """Seguimiento gradual: cabeza dentro del 72 % del área visible.
        No desplazar la rejilla si el usuario está trabajando con notas.
        """
        import time
        self.playhead_tick=tick
        self._manual_seek_active=False
        if (self._drag_origin is not None or self._marquee_origin is not None
            or self._pencil_anchor is not None
            or time.monotonic()<self._follow_pause_until):
            self.update()
            return
        # La guía queda fijada aproximadamente al 76 % de la ventana
        # mientras el fondo avanza sin saltar 4 % ni recentrados bruscos.
        limit=max(0,self.full_tick-self.visible_ticks)
        edge=self.view_start+self.visible_ticks*.76
        if tick>edge and limit:
            target=max(self.view_start,int(tick-self.visible_ticks*.76))
            self.view_start=min(limit,target)
            self.viewChanged.emit(self.view_start/max(1,limit))
        self.update()

    def set_live_editor(self,editor):
        """Vista reducida del modelo MIDI de la pestaña, sin guardar archivos.

        Reutiliza las notas en memoria para que Deshacer, Rehacer, dibujo y
        cuantización se vean en Inicio al instante. No modifica el origen.
        """
        if editor.midi is None:return
        notes=[note for track in editor.tracks for note in track["notes"]]
        self._index_events(editor.tracks)
        if self._selected_track!=editor.track_index:
            # Al cambiar de pista en el editor principal, conservar
            # selecciones del recuadro hasta una nueva selección explícita.
            if not self.selected_note_keys:
                self.selected_note_keys={
                    (editor.track_index,i) for i in editor.selected_indices}
            self._selected_track=editor.track_index
        self.selected_note_indices={
            i for track,i in self.selected_note_keys if track==editor.track_index}
        self.ticks_per_beat=editor.ticks_per_beat
        self.visible_ticks=max(4*self.ticks_per_beat,self.visible_ticks)
        self.full_tick=max([self.visible_ticks]+[n["end"] for n in notes])
        self.max_tick=self.full_tick
        self.view_start=min(self.view_start,max(0,self.full_tick-self.visible_ticks))
        if notes and not self._pitch_manual:
            near=sorted((n["pitch"] for n in notes
                         if n["start"]<self.view_start+self.visible_ticks))
            if not near:near=sorted(n["pitch"] for n in notes)
            lo=near[int(len(near)*.08)]
            hi=near[min(len(near)-1,int(len(near)*.92))]
            span=max(18,min(27,hi-lo+6))
            self.pitch_lo=max(21,min(108-span,(lo+hi)//2-span//2))
            self.pitch_hi=self.pitch_lo+span
        self.update()

    def set_scroll(self,fraction):
        limit=max(0,self.full_tick-self.visible_ticks)
        self._scroll_fraction=0.
        self.view_start=int(max(0.,min(1.,fraction))*limit)
        self.hold_follow()
        self.viewChanged.emit(float(self.view_start/max(1,limit)))
        self.update()

    def zoom(self,factor):
        self.set_zoom_percent(round(float(factor)*100))

    def set_zoom_percent(self,percent):
        """Acercar/alejar con la guía como centro musical fijo.

        La antigua fórmula usaba el centro del viewport y perdía el
        compás de reproducción cuando la guía estaba lejos del centro.
        """
        percent=max(25,min(2000,int(percent)))
        old_visible=max(1,self.visible_ticks)
        # La guía nunca debe desaparecer durante el zoom. Si todavía no
        # se ha movido, establecer un cursor en el compás visible central.
        if self.playhead_tick is None:
            self.playhead_tick=int(self.view_start+old_visible*.5)
            self._manual_seek_active=True
        anchor=max(0,int(self.playhead_tick))
        self._scroll_fraction=0.
        new_visible=max(2*self.ticks_per_beat,
                        int(48*self.ticks_per_beat*100/percent))
        # Preservar el margen final para que una guía en el último compás
        # permanezca dentro del rollo después de acercar.
        self.full_tick=max(self.full_tick,anchor+1)
        self.visible_ticks=min(max(self.full_tick,2*self.ticks_per_beat),
                               new_visible)
        limit=max(0,self.full_tick-self.visible_ticks)
        self.view_start=max(0,min(limit,round(anchor-self.visible_ticks*.5)))
        self.hold_follow()
        self.zoomChanged.emit(percent)
        self.viewChanged.emit(self.view_start/max(1,limit))
        self.update()

    def set_pencil_mode(self,enabled):
        self.pencil_mode=bool(enabled)
        if not enabled:
            self._pencil_anchor=None
            self._pencil_tip=None
            self._pencil_pitch=None
            if self._marquee_origin is None and self._drag_origin is None:
                self._edge_timer.stop()
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self.setToolTip(
            "Lápiz: pulsa y arrastra para dibujar la duración de una nota MIDI."
            " La nota se guarda al soltar; Esc cancela el trazo."
            if enabled else
            "Selección: clic sobre nota, arrastrar desde vacío para seleccionar varias."
            " Ctrl/Mayús añaden a la selección; Supr elimina las marcadas.")
        self.update()

    def delete_selected_notes(self):
        editor=self.editor_owner
        if editor is None or editor.midi is None:return False
        keys={(t,i) for t,i in self.selected_note_keys
              if 0<=t<len(editor.tracks)
              and 0<=i<len(editor.tracks[t]["notes"])}
        if not keys:
            keys={(editor.track_index,i) for i in editor.selected_indices
                  if 0<=i<len(editor.current_notes)}
        if not keys:return False
        from collections import defaultdict
        by_track=defaultdict(set)
        for track,index in keys:by_track[track].add(index)
        editor.snapshot()
        for track,indices in by_track.items():
            notes=editor.tracks[track]["notes"]
            for index in sorted(indices,reverse=True):
                del notes[index]
        self._set_note_selection(set())
        self.set_live_editor(editor)
        editor.update_track_list()
        editor.redraw()
        self.update()
        return True

    def _pencil_note(self):
        if self._pencil_anchor is None:return None
        step=max(1,round(self.ticks_per_beat*4/(self.grid_division or 4)))
        a=int(self._pencil_anchor)
        b=int(self._pencil_tip if self._pencil_tip is not None else a)
        # Click: una casilla; arrastre: nota larga desde el punto de
        # inicio hasta el borde horizontal que sigue al lápiz.
        start=min(a,b)
        end=max(a+step,b+step)
        return start,end,int(self._pencil_pitch)

    def _finish_pencil(self):
        draft=self._pencil_note()
        self._pencil_anchor=None
        self._pencil_tip=None
        self._pencil_pitch=None
        if draft is None:return
        editor=self.editor_owner
        if editor is None or editor.midi is None:return
        start,end,pitch=draft
        editor.snapshot()
        editor.current_notes.append({
            "start":start,"end":end,"pitch":pitch,
            "velocity":editor.velocity.value(),
            "channel":editor.default_channel()})
        self._set_note_selection({(editor.track_index,len(editor.current_notes)-1)})
        self.set_live_editor(editor)
        self.full_tick=max(self.full_tick,end+int(self.visible_ticks*.2))
        editor.update_track_list()
        editor.redraw()
        self.update()

    def set_pitch_window(self,low,span=None):
        if span is None:span=self.pitch_hi-self.pitch_lo+1
        span=max(8,min(88,int(span)))
        low=max(21,min(109-span,int(low)))
        self.pitch_lo=low
        self.pitch_hi=low+span-1
        self._pitch_manual=True
        self.hold_follow()
        self.pitchChanged.emit(low,span)
        self.update()

    def fit_song(self):
        # Ajustar al contenido musical REAL, no a la duración artificial
        # mínima de 12 compases usada al iniciar el navegador.
        last=max(max((note["end"] for note in self.events),default=0),
                 self.playhead_tick or 0)
        self.visible_ticks=max(4*self.ticks_per_beat,
                               last+4*self.ticks_per_beat)
        self.full_tick=max(self.full_tick,self.visible_ticks)
        self.view_start=0
        self._scroll_fraction=0.
        self.set_pitch_window(21,88)
        self.viewChanged.emit(0.)
        self.zoomChanged.emit(max(25,min(2000,round(
            48*self.ticks_per_beat*100/self.visible_ticks))))
        self.hold_follow()
        self.update()

    def _pan_time(self,delta_ticks):
        """Desplazamiento horizontal fino con fracción acumulada.

        Los gestos de trackpad pueden entregar pocos píxeles por evento:
        perder el decimal producía desplazamiento a saltos o nulo.
        """
        limit=max(0,self.full_tick-self.visible_ticks)
        if not limit:return
        movement=float(delta_ticks)+self._scroll_fraction
        whole=math.trunc(movement)
        self._scroll_fraction=movement-whole
        if not whole:return
        new=max(0,min(limit,self.view_start+whole))
        if new==self.view_start:
            self._scroll_fraction=0.
            return
        self.view_start=new
        self.hold_follow()
        self.viewChanged.emit(new/max(1,limit))
        self.update()

    def _pan_pitches(self,delta_notes):
        """Desplazar el teclado verticalmente sin afectar al tiempo MIDI.

        Conserva fracciones entre eventos pequeños de trackpad y aplica
        los límites reales de la ventana dentro de las 88 notas MIDI.
        """
        span=self.pitch_hi-self.pitch_lo+1
        if span>=88:
            self._pitch_scroll_fraction=0.
            return
        movement=float(delta_notes)+self._pitch_scroll_fraction
        whole=math.trunc(movement)
        self._pitch_scroll_fraction=movement-whole
        if not whole:return
        target=max(21,min(109-span,self.pitch_lo+whole))
        if target==self.pitch_lo:
            self._pitch_scroll_fraction=0.
            return
        self.set_pitch_window(target,span)

    def wheelEvent(self,event):
        """Trackpad bidimensional: X recorre tiempo, Y recorre notas.

        Qt entrega pixelDelta para gestos precisos o angleDelta para
        trackpads emulados. Cada eje se interpreta SOLO en su dirección;
        los gestos diagonales pueden desplazar ambos ejes, sin cruces.
        """
        pixel=event.pixelDelta()
        angle=event.angleDelta()
        dx=(float(pixel.x()) if pixel.x() else
            float(angle.x())/120.*65.)
        dy=(float(pixel.y()) if pixel.y() else
            float(angle.y())/120.*65.)
        if dx==0 and dy==0:
            event.accept()
            return
        mods=event.modifiers()
        dominant=(dx if abs(dx)>abs(dy) else dy)
        direction=1 if dominant>0 else -1
        if mods & Qt.ControlModifier:
            current=48*self.ticks_per_beat*100/max(1,self.visible_ticks)
            self.set_zoom_percent(round(current*(1.18 if direction>0 else 1/1.18)))
        elif mods & Qt.AltModifier:
            span=self.pitch_hi-self.pitch_lo+1
            self.set_pitch_window(self.pitch_lo+direction,
                                  span-2*direction)
        elif mods & Qt.ShiftModifier:
            self._pan_pitches(dy/max(.5,(self.height()-28)/
                              max(1,self.pitch_hi-self.pitch_lo+1))
                              if dy else dx/max(.5,(self.height()-28)/
                              max(1,self.pitch_hi-self.pitch_lo+1)))
        else:
            # X: únicamente compases / tiempo.
            if dx:self._pan_time(-dx*self.visible_ticks/max(1,self.width()-62))
            # Y: únicamente altura / teclado (88 teclas).
            if dy:
                row_px=max(.5,(self.height()-28)/
                           max(1,self.pitch_hi-self.pitch_lo+1))
                self._pan_pitches(dy/row_px)
        event.accept()

    def _raw_point(self,point):
        tick=max(0.,self.view_start+
             (float(point.x())-62)*self.visible_ticks/max(1,self.width()-62))
        row=(self.height()-28)/max(1,self.pitch_hi-self.pitch_lo+1)
        pitch=self.pitch_hi-(float(point.y())-28)/max(.1,row)
        return tick,pitch

    def _scroll_drag_edge(self):
        if self._edge_position is None or (
            self._marquee_origin is None and self._drag_origin is None
            and self._pencil_anchor is None and not self._seeking):return
        x=float(self._edge_position.x());y=float(self._edge_position.y())
        dx=1 if x>=self.width()-14 else -1 if x<=75 else 0
        dy=1 if y<=40 else -1 if y>=self.height()-12 else 0
        changed=False
        if dx:
            step=max(1,round(self.visible_ticks*.017))
            # Mientras se dibuja una nota con el lápiz, ampliar el
            # lienzo virtual al rebasar el último compás existente.
            # De otra forma la nota quedaría atrapada en el borde.
            if (dx>0 and self._pencil_anchor is not None
                and self.view_start>=self.full_tick-self.visible_ticks-step):
                self.full_tick+=max(step*2,self.ticks_per_beat)
            limit=max(0,self.full_tick-self.visible_ticks)
            new=max(0,min(limit,self.view_start+dx*step))
            if new!=self.view_start:
                self.view_start=new
                self.viewChanged.emit(new/max(1,limit))
                changed=True
        if dy and self._marquee_origin is not None:
            span=self.pitch_hi-self.pitch_lo+1
            low=max(21,min(109-span,self.pitch_lo+dy))
            if low!=self.pitch_lo:
                self.pitch_lo=low
                self.pitch_hi=low+span-1
                self._pitch_manual=True
                self.pitchChanged.emit(low,span)
                changed=True
        if changed:
            if self._marquee_origin is not None:
                self._marquee_tick1,self._marquee_pitch1=self._raw_point(
                    self._edge_position)
                self._marquee_select()
            elif self._seeking:
                tick=int(self._raw_point(self._edge_position)[0])
                self.playhead_tick=tick
                self.seekRequested.emit(tick)
            elif self._drag_origin is not None:
                self._move_notes_to(self._edge_position)
            elif self._pencil_anchor is not None:
                self._pencil_tip=self._at_midi(self._edge_position)[0]
            self.update()

    def _note_at(self,point):
        """Detectar la nota visible en SU pista, no solo en la primera."""
        editor=self.editor_owner
        if editor is None or editor.midi is None:return None
        x=float(point.x());y=float(point.y())
        if x<62 or y<28:return None
        row=(self.height()-28)/max(1,self.pitch_hi-self.pitch_lo+1)
        # Dar prioridad a la pista activa cuando dos notas se superponen.
        candidates=list(self._visible_events())
        candidates.sort(key=lambda n:(n["track_index"]==editor.track_index,
                                      n["track_index"],n["note_index"]),reverse=True)
        for note in candidates:
            if not self.pitch_lo<=note["pitch"]<=self.pitch_hi:continue
            xx=62+(note["start"]-self.view_start)/self.visible_ticks*(self.width()-62)
            ww=max(4,(note["end"]-note["start"])/self.visible_ticks*(self.width()-62))
            yy=28+(self.pitch_hi-note["pitch"])*row
            if xx-3<=x<=xx+ww+3 and yy-3<=y<=yy+row+3:
                return note["track_index"],note["note_index"]
        return None

    def _at_midi(self,point):
        unit=self.visible_ticks/max(1,self.width()-62)
        tick=max(0,round(self.view_start+(point.x()-62)*unit))
        grid=0 if not self.grid_division else max(
            1,round(self.ticks_per_beat*4/self.grid_division))
        if grid:tick=round(tick/grid)*grid
        row=(self.height()-28)/max(1,self.pitch_hi-self.pitch_lo+1)
        pitch=max(21,min(108,self.pitch_hi-int((point.y()-28)/max(row,.5))))
        return tick,pitch

    def _set_note_selection(self,keys):
        editor=self.editor_owner
        if editor is None or editor.midi is None:return
        self.selected_note_keys={
            (track,index) for track,index in keys
            if 0<=track<len(editor.tracks)
            and 0<=index<len(editor.tracks[track]["notes"])}
        self._selected_track=editor.track_index
        self.selected_note_indices={
            index for track,index in self.selected_note_keys
            if track==editor.track_index}
        editor.selected_indices=set(self.selected_note_indices)
        editor.selected_index=(min(self.selected_note_indices)
                               if self.selected_note_indices else None)
        editor.update_selected()
        self.update()

    def _note_rect(self,note):
        row=(self.height()-28)/max(1,self.pitch_hi-self.pitch_lo+1)
        x=62+(note["start"]-self.view_start)/self.visible_ticks*(self.width()-62)
        width=max(4,(note["end"]-note["start"])/self.visible_ticks*(self.width()-62))
        y=28+(self.pitch_hi-note["pitch"])*row
        return QRectF(x,y,width,row)

    def _marquee_rect(self):
        if self._marquee_origin is None or self._marquee_end is None:
            return QRectF()
        a_tick=self._marquee_tick0
        b_tick=self._marquee_tick1
        a_pitch=self._marquee_pitch0
        b_pitch=self._marquee_pitch1
        def px(t):return 62+(t-self.view_start)/self.visible_ticks*(self.width()-62)
        row=(self.height()-28)/max(1,self.pitch_hi-self.pitch_lo+1)
        def py(p):return 28+(self.pitch_hi-p)*row
        x1=max(62,min(px(a_tick),px(b_tick)))
        x2=min(self.width(),max(px(a_tick),px(b_tick)))
        y1=max(28,min(py(a_pitch),py(b_pitch)))
        y2=min(self.height(),max(py(a_pitch),py(b_pitch)))
        return QRectF(x1,y1,max(0,x2-x1),max(0,y2-y1))

    def _marquee_select(self):
        # El recuadro conserva coordenadas MUSICALES absolutas mientras
        # la pantalla se desplaza; alcanza notas más allá del margen.
        a=min(self._marquee_tick0,self._marquee_tick1)
        b=max(self._marquee_tick0,self._marquee_tick1)
        lo=min(self._marquee_pitch0,self._marquee_pitch1)
        hi=max(self._marquee_pitch0,self._marquee_pitch1)
        keys=set(self._marquee_base)
        if b>a and hi>lo:
            import bisect
            i=bisect.bisect_left(self._event_starts,
                               max(0,a-self._max_note_duration))
            j=bisect.bisect_right(self._event_starts,b)
            for note in self.events[i:j]:
                if (note["end"]>=a and note["start"]<=b
                    # Al seleccionar con pocas filas verticales por píxel,
                    # el redondeo del ratón puede dejar 71.9 en vez de 72.
                    # Tomar el rango de FILAS intersecadas, no comparar
                    # alturas continuas con un medio semitono arbitrario.
                    and math.floor(lo)<=note["pitch"]<=math.ceil(hi)):
                    keys.add((note["track_index"],note["note_index"]))
        self._set_note_selection(keys)

    def contextMenuEvent(self,event):
        """Copiar/Pegar/Eliminar/Ajustar sobre la selección MIDI real."""
        editor=self.editor_owner
        if editor is None or editor.midi is None:
            event.ignore()
            return
        hit=self._note_at(event.pos())
        # Clic derecho sobre una nota no seleccionada: actuar sobre ella.
        # Sobre una seleccionada: preservar TODO el grupo.
        # Sobre vacío: mantener la selección, para poder pegar allí.
        if hit is not None and hit not in self.selected_note_keys:
            track,index=hit
            if track!=editor.track_index:
                item=editor.tracks_list.topLevelItem(track)
                if item is not None:
                    editor.tracks_list.setCurrentItem(item)
                    if editor.track_index!=track:
                        editor.change_track(item,None)
            self._set_note_selection({hit})
        keys=editor.context_valid_keys(self.selected_note_keys)
        from PySide6.QtWidgets import QMenu
        menu=QMenu(self)
        copy_action=menu.addAction("Copiar")
        paste_action=menu.addAction("Pegar")
        delete_action=menu.addAction("Eliminar")
        menu.addSeparator()
        align_action=menu.addAction("Ajustar al inicio del compás")
        for action in (copy_action,delete_action,align_action):
            action.setEnabled(bool(keys))
        paste_action.setEnabled(bool(getattr(editor,"_context_clipboard",None)))
        chosen=menu.exec(event.globalPos())
        if chosen==copy_action:
            editor.context_copy_notes(keys)
        elif chosen==paste_action:
            tick,_=self._at_midi(event.pos())
            new_keys=editor.context_paste_notes(tick)
            if new_keys:
                self._set_note_selection(new_keys)
                self.set_live_editor(editor)
                last=max(self.events,key=lambda n:n["end"])["end"] if self.events else 0
                self.full_tick=max(self.full_tick,last+int(self.visible_ticks*.2))
        elif chosen==delete_action:
            if editor.context_delete_notes(keys):
                self._set_note_selection(set())
                self.set_live_editor(editor)
        elif chosen==align_action:
            if editor.context_align_to_measure(keys):
                self.set_live_editor(editor)
        self.update()
        event.accept()

    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:
            return super().mousePressEvent(event)
        editor=self.editor_owner
        if editor is None or editor.midi is None:
            return super().mousePressEvent(event)
        self.setFocus()
        self.hold_follow()
        self._drag_origin=None
        self._drag_notes=None
        self._drag_snapshot=False
        self._marquee_origin=None
        self._marquee_end=None
        self._edge_position=event.position()
        self._edge_timer.stop()
        mods=event.modifiers()
        if (self.pencil_mode and float(event.position().x())>=62
            and float(event.position().y())>=28):
            self._pencil_anchor,self._pencil_pitch=self._at_midi(event.position())
            self._pencil_tip=self._pencil_anchor
            self._edge_timer.start()
            self.update()
            event.accept()
            return
        if float(event.position().y())<28 and float(event.position().x())>=62:
            self._seeking=True
            tick=int(self._raw_point(event.position())[0])
            self.playhead_tick=tick
            self.seekRequested.emit(tick)
            event.accept()
            return
        hit=self._note_at(event.position())
        if hit is not None:
            track,index=hit
            key=(track,index)
            if track!=editor.track_index:
                item=editor.tracks_list.topLevelItem(track)
                if item is not None:
                    editor.tracks_list.setCurrentItem(item)
                    if editor.track_index!=track:editor.change_track(item,None)
            if mods & Qt.ControlModifier:
                keys=set(self.selected_note_keys)
                if key in keys:keys.remove(key)
                else:keys.add(key)
            elif mods & Qt.ShiftModifier:
                keys=set(self.selected_note_keys)|{key}
            elif key in self.selected_note_keys:
                keys=set(self.selected_note_keys)
            else:
                keys={key}
            self._set_note_selection(keys)
            # Alt/clic modificador solo cambia la selección; arrastrar
            # una nota seleccionada mueve todas las seleccionadas.
            if not (mods & (Qt.ControlModifier|Qt.ShiftModifier)) and key in keys:
                self._drag_origin=self._at_midi(event.position())
                self._drag_notes={
                    (t,i):dict(editor.tracks[t]["notes"][i])
                    for t,i in keys}
        else:
            # Clic en zona vacía: preparar recuadro. Ctrl+clic sin
            # arrastrar sigue creando una nota nueva.
            self._marquee_origin=event.position()
            self._marquee_end=event.position()
            self._marquee_tick0,self._marquee_pitch0=self._raw_point(
                event.position())
            self._marquee_tick1=self._marquee_tick0
            self._marquee_pitch1=self._marquee_pitch0
            self._marquee_base=(set(self.selected_note_keys)
                if mods & (Qt.ShiftModifier|Qt.ControlModifier) else set())
            self._marquee_ctrl_create=bool(mods & Qt.ControlModifier)
            self._marquee_moved=False
        if self._marquee_origin is not None or self._drag_origin is not None:
            self._edge_timer.start()
        self.update();event.accept()

    def _create_at(self,point):
        editor=self.editor_owner
        if editor is None or editor.midi is None:return
        tick,pitch=self._at_midi(point)
        step=max(1,round(self.ticks_per_beat*4/(self.grid_division or 4)))
        editor.snapshot()
        editor.current_notes.append(dict(start=tick,end=tick+step,pitch=pitch,
              velocity=self.editor_owner.velocity.value(),
              channel=editor.default_channel()))
        self._set_note_selection({
            (editor.track_index,len(editor.current_notes)-1)})
        self.set_live_editor(editor)
        editor.update_track_list()
        editor.redraw()

    def mouseDoubleClickEvent(self,event):
        if self.pencil_mode:
            # Qt envía press/release/press/doubleClick/release; el segundo
            # press ya inició un trazo. Cancelarlo impide duplicar notas.
            self._pencil_anchor=None
            self._pencil_tip=None
            self._pencil_pitch=None
            self._edge_timer.stop()
            self.update()
            event.accept()
            return
        if event.button()==Qt.LeftButton and self._note_at(event.position()) is None:
            self._create_at(event.position());event.accept()
        else:super().mouseDoubleClickEvent(event)

    def _move_notes_to(self,point):
        editor=self.editor_owner
        if editor is None or editor.midi is None or self._drag_origin is None:return
        target=self._at_midi(point)
        dt=target[0]-self._drag_origin[0]
        dp=target[1]-self._drag_origin[1]
        if not dt and not dp:return
        if not self._drag_snapshot:
            editor.snapshot()
            self._drag_snapshot=True
        originals=self._drag_notes or {}
        if not originals:return
        dt=max(dt,-min(n["start"] for n in originals.values()))
        dp=max(21-min(n["pitch"] for n in originals.values()),
               min(108-max(n["pitch"] for n in originals.values()),dp))
        for (track,index),original in originals.items():
            note=editor.tracks[track]["notes"][index]
            start=original["start"]+dt
            duration=max(1,original["end"]-original["start"])
            note.update(start=start,end=start+duration,
                        pitch=original["pitch"]+dp)
        # El modelo de las notas YA se ha actualizado. Durante el arrastre
        # no reordenar todos los eventos MIDI por cada píxel: las seleccionadas
        # se pintan en una segunda pasada desde el modelo vivo.
        self.update()

    def mouseMoveEvent(self,event):
        self._edge_position=event.position()
        if not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        editor=self.editor_owner
        if editor is None or editor.midi is None:return
        self.hold_follow()
        if self._pencil_anchor is not None:
            self._pencil_tip=self._at_midi(event.position())[0]
            self.update()
            event.accept()
            return
        if self._seeking:
            tick=int(self._raw_point(event.position())[0])
            self.playhead_tick=tick
            self.seekRequested.emit(tick)
            self._edge_timer.start()
            self.update();event.accept()
            return
        if self._marquee_origin is not None:
            self._marquee_end=event.position()
            delta=self._marquee_end-self._marquee_origin
            if abs(delta.x())>=4 or abs(delta.y())>=4:
                self._marquee_moved=True
            if self._marquee_moved:
                self._marquee_tick1,self._marquee_pitch1=self._raw_point(
                    event.position())
                self._marquee_select()
            self.update();event.accept()
            return
        if self._drag_origin is None:return super().mouseMoveEvent(event)
        self._move_notes_to(event.position())
        event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:
            self._edge_timer.stop()
            self._edge_position=None
        if event.button()==Qt.LeftButton and self._pencil_anchor is not None:
            self._pencil_tip=self._at_midi(event.position())[0]
            self._finish_pencil()
            event.accept()
            return
        if event.button()==Qt.LeftButton and self._seeking:
            tick=int(self._raw_point(event.position())[0])
            self.playhead_tick=tick
            self.seekRequested.emit(tick)
            self._seeking=False
            self.hold_follow()
            self.update();event.accept()
            return
        if event.button()==Qt.LeftButton and self._marquee_origin is not None:
            if self._marquee_moved:
                self._marquee_end=event.position()
                self._marquee_tick1,self._marquee_pitch1=self._raw_point(
                    event.position())
                self._marquee_select()
            elif self._marquee_ctrl_create:
                self._create_at(event.position())
            else:
                self._set_note_selection(self._marquee_base)
            self._marquee_origin=None
            self._marquee_end=None
            self._marquee_base=set()
            self._marquee_moved=False
            self._marquee_ctrl_create=False
            self.update();event.accept()
            return
        if event.button()==Qt.LeftButton and self._drag_origin is not None:
            if self._drag_snapshot and self.editor_owner:
                self._index_events(self.editor_owner.tracks)
                self.editor_owner.update_track_list()
                self.editor_owner.redraw()
            self._drag_origin=None
            self._drag_notes=None
            self._drag_snapshot=False
            self.update();event.accept()
        else:super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Delete,Qt.Key_Backspace):
            if self.delete_selected_notes():
                event.accept()
            else:super().keyPressEvent(event)
        elif event.key()==Qt.Key_Escape and self._pencil_anchor is not None:
            self._pencil_anchor=None
            self._pencil_tip=None
            self._pencil_pitch=None
            self._edge_timer.stop()
            self.update()
            event.accept()
        elif event.key()==Qt.Key_Escape and self._marquee_origin is not None:
            self._edge_timer.stop()
            self._marquee_origin=None
            self._marquee_end=None
            self._set_note_selection(self._marquee_base)
            self._marquee_base=set()
            event.accept()
        else:super().keyPressEvent(event)

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
        # Subdivisiones del selector de rejilla de Inicio. Limitar
        # densidad para conservar legibilidad y fluidez en MIDI largos.
        subdivision=int(self.grid_division)
        if subdivision:
            step=max(1,round(self.ticks_per_beat*4/subdivision))
            visible=max(1,self.visible_ticks)
            pixels_per_step=(w-left)*step/visible
            stride=max(1,math.ceil(6/max(.01,pixels_per_step)))
            first=max(0,self.view_start//step)
            last=(self.view_start+visible)//step+2
            for number in range(first,last,stride):
                tick=number*step
                if tick%(self.ticks_per_beat)==0:continue
                x=time_x(tick)
                if left<=x<=w:
                    p.setPen(QPen(Qc("#1c4967"),.7))
                    p.drawLine(QPointF(x,top),QPointF(x,h))
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
            for note in self._visible_events():
                key=(note["track_index"],note["note_index"])
                # La posición de estas notas se pinta actualizada debajo;
                # evitar el fantasma de su posición previa al arrastre.
                if self._drag_snapshot and self._drag_notes and key in self._drag_notes:
                    continue
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
                if (note["track_index"],note["note_index"]) in self.selected_note_keys:
                    p.setPen(QPen(QColor("#fff4a2"),1.6))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(QRectF(x,yy,width,height),1,1)
            if self._drag_snapshot and self._drag_notes and self.editor_owner:
                for (track,index) in self._drag_notes:
                    if (track,index) not in self.selected_note_keys:continue
                    note=self.editor_owner.tracks[track]["notes"][index]
                    if not self.pitch_lo<=note["pitch"]<=self.pitch_hi:continue
                    x=max(left,time_x(note["start"]))
                    end=min(w,time_x(note["end"]))
                    if end<=x:continue
                    yy=pos(note["pitch"])+max(.4,row_h*.13)
                    rect=QRectF(x,yy,max(2,end-x),max(2.2,row_h*.74))
                    p.setPen(QPen(QColor("#fff4a2"),1.6))
                    p.setBrush(QBrush(QColor("#1dcaff")))
                    p.drawRoundedRect(rect,1,1)
        else:
            p.setPen(Qc("#93aabf"))
            p.drawText(QRectF(left,top,w-left,h-top),Qt.AlignCenter,
                       "Selecciona un MIDI para representar sus notas")
        p.setPen(QPen(Qc("#28dffc"),1.5))
        cx=left+self.cursor_fraction*(w-left)
        p.drawLine(QPointF(cx,top),QPointF(cx,h))
        if self.playhead_tick is not None:
            x=time_x(self.playhead_tick)
            if left<=x<=w:
                # Guía nítida y luminosa incluso con coordenadas
                # fraccionarias: línea central sin antialias y ancho 3 px.
                p.setRenderHint(QPainter.Antialiasing,False)
                p.setPen(QPen(QColor("#ffe268"),3))
                p.drawLine(QPointF(round(x),0),QPointF(round(x),h))
                p.setRenderHint(QPainter.Antialiasing,True)
                p.setBrush(QColor("#ffe268"))
                p.drawEllipse(QPointF(x,8),3,3)
        if self._pencil_anchor is not None:
            draft=self._pencil_note()
            if draft is not None and self.pitch_lo<=draft[2]<=self.pitch_hi:
                x1=max(left,time_x(draft[0]))
                x2=min(w,time_x(draft[1]))
                if x2>x1:
                    yy=pos(draft[2])+max(.4,row_h*.13)
                    p.setPen(QPen(QColor("#fff4a2"),2))
                    p.setBrush(QBrush(QColor(33,224,182,180)))
                    p.drawRoundedRect(
                        QRectF(x1,yy,max(2,x2-x1),max(2.2,row_h*.74)),2,2)
        if self._marquee_origin is not None and self._marquee_moved:
            rect=self._marquee_rect()
            if rect.width()>0 and rect.height()>0:
                p.setPen(QPen(QColor("#b4f2ff"),1.3,Qt.DashLine))
                p.setBrush(QBrush(QColor(56,190,245,45)))
                p.drawRect(rect)
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
        self._result_duration_cache={}
        self._pause=False
        self._mix_levels={}
        self._mix_pending_changes=set()
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
        # El reloj general de Inicio (900 ms) no basta para un desplazamiento
        # fluido. Este temporizador sigue solo la onda de Vista de audio;
        # no modifica la velocidad ni el motor de reproducción.
        self._wave_ui_position=None
        self._wave_ui_time=None
        self._wave_ui_source=None
        self._wave_overview_last=0.
        self.wave_follow_timer=QTimer(self)
        self.wave_follow_timer.setTimerType(Qt.PreciseTimer)
        self.wave_follow_timer.setInterval(16)
        self.wave_follow_timer.timeout.connect(self._sync_wave_playhead)
        self.wave_follow_timer.start()

    def _build(self):
        page=QWidget()
        page.setObjectName("studioHomePage")
        page.setMinimumWidth(0)
        root=QVBoxLayout(page)
        root.setContentsMargins(12,10,12,8)
        root.setSpacing(9)
        self.page=page
        from home_fit_view import FitHomeView
        self.scroll=FitHomeView(page,self)
        outer=QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.addWidget(self.scroll)
        # Organización por proyecto: la cuadrícula original permanece como
        # opción, sin cambiar los doce módulos ni sus motores.
        from home_workspace import FreeHomeCanvas
        toolbar=QHBoxLayout()
        toolbar.setSpacing(5)
        from PySide6.QtWidgets import QPushButton
        mode=QPushButton("Organizar Inicio por filas",page)
        edit=QPushButton("Mover y ordenar módulos",page)
        reset=QPushButton("Distribución original",page)
        save=QPushButton("Guardar distribución",page)
        status=QLabel("12 módulos · distribución original",page)
        for button in (mode,edit,reset,save):
            button.setObjectName("homeWorkspaceTool")
            button.setStyleSheet(
                "QPushButton#homeWorkspaceTool{background:#0c4182;"
                "border:1px solid #2ba6e9;color:#d7f3ff;"
                "border-radius:4px;padding:3px 8px;min-height:22px;}"
                "QPushButton#homeWorkspaceTool:hover{background:#1767ad;}")
            toolbar.addWidget(button)
        status.setStyleSheet("color:#90d8f0;font-size:10px;")
        toolbar.addWidget(status,1)
        root.addLayout(toolbar,0)
        self.workspace_toolbar={
            "mode":mode,"edit":edit,"reset":reset,"save":save,"status":status}
        # Cuatro módulos arriba, Desglose de batería y herramientas en el
        # centro, Piano Roll e información abajo. Una única pantalla Inicio.
        top=QHBoxLayout();top.setSpacing(9)
        mid=QHBoxLayout();mid.setSpacing(9)
        end=QHBoxLayout();end.setSpacing(9)
        self.mon_card=Card("🔴  Monitor / Grabación")
        self.sep_card=Card("◈  Separación de audio")
        self.midi_card=Card("♫  Audio a MIDI")
        self.result_card=Card("📁  Resultados")
        for card,stretch in ((self.mon_card,27),(self.sep_card,23),
                             (self.midi_card,25),(self.result_card,25)):
            card.setMinimumHeight(318)
            card.setMaximumHeight(346)
            top.addWidget(card,stretch)
        top_container=QWidget(page)
        top_container.setObjectName("homeFactoryTopRow")
        top_container.setLayout(top)
        root.addWidget(top_container,39)
        self.wave_card=Card("▣  Vista de audio")
        self.track_card=Card("◈  Pistas separadas")
        self.mix_card=Card("☷  Mezclador")
        self.drum_card=Card("◉  Desglose de batería")
        for card,stretch in ((self.wave_card,10),(self.drum_card,10),
                             (self.track_card,11),(self.mix_card,13)):
            card.setMinimumHeight(205)
            card.setMaximumHeight(210)
            mid.addWidget(card,stretch)
        mid_container=QWidget(page)
        mid_container.setObjectName("homeFactoryMidRow")
        mid_container.setLayout(mid)
        root.addWidget(mid_container,27)
        self.piano_card=Card("♬  Piano Roll · MIDI")
        self.vocal_card=Card("♬  Afinación vocal")
        self.drum_stems_card=Card("◉  Batería · pistas separadas")
        self.info_card=Card("♫  MIDI a audio")
        self.info_card.setObjectName("midiToAudioHomeCard")
        for card in (self.piano_card,self.vocal_card,
                     self.drum_stems_card,self.info_card):
            card.setMinimumHeight(205)
            card.setMaximumHeight(215)
        self.piano_card.setMinimumWidth(420)
        self.vocal_card.setMinimumWidth(190)
        self.drum_stems_card.setMinimumWidth(295)
        self.info_card.setMinimumWidth(175)
        # El conversor requiere espacio para entrada, formato y transporte.
        # Recuperarlo del exceso de ancho del Piano Roll reducido; la
        # ampliación por candado conserva ambos módulos completos.
        end.addWidget(self.piano_card,37)
        end.addWidget(self.vocal_card,17)
        end.addWidget(self.drum_stems_card,22)
        end.addWidget(self.info_card,24)
        end_container=QWidget(page)
        end_container.setObjectName("homeFactoryEndRow")
        end_container.setLayout(end)
        root.addWidget(end_container,29)
        self._factory_containers=(top_container,mid_container,end_container)
        self.free_canvas=FreeHomeCanvas(self)
        self.free_canvas.hide()
        root.addWidget(self.free_canvas,100)

        # Cada cabecera se conecta a su pestaña definitiva al terminar de
        # instalar las nueve pestañas (HomeTabSynchronizer). Así no se usa
        # tabs.widget(0), que tras insertar Inicio es la propia portada.

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
        from home_workspace import HomeWorkspace
        self.home_workspace=HomeWorkspace(
            self,self._factory_containers,self.free_canvas,
            self.workspace_toolbar)

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
            (self.info_card,"midi"),
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
        signal_row=QHBoxLayout()
        signal_row.setSpacing(7)
        self.monitor_left_controls=QVBoxLayout()
        self.monitor_left_controls.setSpacing(5)
        self.monitor_left_controls.addWidget(self.record_transport,0,Qt.AlignTop)
        signal_row.addLayout(self.monitor_left_controls,0)
        self.capture_analyzer_panel=QFrame()
        self.capture_analyzer_panel.setObjectName("captureAnalyzerPanel")
        self.capture_analyzer_panel.setMinimumHeight(195)
        self.capture_analyzer_panel.setStyleSheet(
            "QFrame#captureAnalyzerPanel{background:#04132c;border:1px solid #247cbe;"
            "border-radius:6px;}"
            "QFrame#captureAnalyzerPanel QLabel{border:0;background:transparent;}")
        analyzers=QVBoxLayout(self.capture_analyzer_panel)
        analyzers.setContentsMargins(6,4,6,5)
        analyzers.setSpacing(3)
        from widgets import Oscilloscope,Spectrum
        from capture_live_listen import available_sinks
        analyzer_title=QHBoxLayout()
        analyzer_title.addWidget(label("SEÑAL FINAL DE CAPTURA · POST-EQ"),1)
        self.capture_graph_status=label("Sin señal",muted=True)
        analyzer_title.addWidget(self.capture_graph_status,0)
        analyzers.addLayout(analyzer_title)
        self.capture_scope=Oscilloscope(self.capture_analyzer_panel)
        self.capture_scope.setMinimumHeight(0)
        self.capture_scope.setFixedHeight(57)
        self.capture_scope.setToolTip(
            "Onda real tras aplicar ganancia, balance y ecualización. "
            "La misma señal se guarda y se envía a escucha procesada.")
        analyzers.addWidget(self.capture_scope)
        self.capture_spectrum=Spectrum(self.capture_analyzer_panel)
        self.capture_spectrum.setMinimumHeight(0)
        self.capture_spectrum.setFixedHeight(72)
        self.capture_spectrum.setToolTip(
            "Análisis de frecuencia en tiempo real del PCM ya ecualizado.")
        analyzers.addWidget(self.capture_spectrum)
        listen_row=QHBoxLayout()
        listen_row.setSpacing(4)
        self.listen_processed=QCheckBox("Escucha procesada",self.capture_analyzer_panel)
        self.listen_processed.setToolTip(
            "Escucha la señal PROCESADA mientras grabas. Selecciona una salida "
            "DIFERENTE de la fuente monitorizada; usa auriculares para evitar acoples. "
            "No se activa automáticamente ni modifica el volumen del sistema.")
        listen_row.addWidget(self.listen_processed)
        self.listen_output=QComboBox(self.capture_analyzer_panel)
        self.listen_output.setMinimumWidth(135)
        self.listen_output.setMaximumWidth(255)
        self.listen_output.setToolTip("Salida exclusiva de escucha procesada")
        listen_row.addWidget(self.listen_output,1)
        analyzers.addLayout(listen_row)
        self.listen_processed.toggled.connect(self.toggle_processed_listen)
        self.listen_output.currentIndexChanged.connect(self.change_processed_listen_output)
        self.capture_analyzer_panel.hide()
        signal_row.addWidget(self.capture_analyzer_panel,1)
        left.addLayout(signal_row)

        # Dos filas compactas; en la cuadrícula Qt la columna de texto
        # podía crecer hasta 200 px y separar etiqueta de selector.
        form=QVBoxLayout()
        form.setContentsMargins(0,0,0,0)
        form.setSpacing(4)
        format_row=QHBoxLayout()
        format_row.setSpacing(7)
        format_caption=label("Formato")
        format_caption.setFixedWidth(69)
        format_row.addWidget(format_caption)
        self.format=QComboBox()
        self.format.setMaximumWidth(245)
        self.format.currentIndexChanged.connect(lambda idx:self.main.format.setCurrentIndex(idx)
            if idx>=0 and idx<self.main.format.count() else None)
        format_row.addWidget(self.format)
        format_row.addStretch(1)
        form.addLayout(format_row)
        quality_row=QHBoxLayout()
        quality_row.setSpacing(7)
        quality_caption=label("Calidad")
        quality_caption.setFixedWidth(69)
        quality_row.addWidget(quality_caption)
        self.quality=QComboBox()
        self.quality.setMaximumWidth(245)
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
        quality_row.addWidget(self.quality)
        quality_row.addStretch(1)
        form.addLayout(quality_row)
        # Los selectores van DEBAJO del transporte compacto, a su
        # izquierda, no debajo del analizador a ancho completo.
        self.monitor_left_controls.addLayout(form)
        self.monitor_left_controls.addStretch(1)
        control_row=QHBoxLayout()
        control_row.setSpacing(7)
        # El control original permanece en Inicio; con candado abierto
        # se sustituye visualmente por el control SUPERIOR funcional.
        self.capture_gain_panel=QWidget()
        level_box=QVBoxLayout(self.capture_gain_panel)
        level_box.setContentsMargins(0,0,0,0)
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
        control_row.addWidget(self.capture_gain_panel,1)
        self.capture_balance_panel=QWidget()
        balance_box=QVBoxLayout(self.capture_balance_panel)
        balance_box.setContentsMargins(0,0,0,0)
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
        self.capture_balance_home_layout=control_row
        control_row.addWidget(self.capture_balance_panel,0)
        left.addLayout(control_row)
        self._capture_peak_hold=0.0
        self._capture_clip_count=0
        self.capture_diagnostics=QFrame()
        self.capture_diagnostics.setObjectName("monitorSignalDiagnostics")
        self.capture_diagnostics.setStyleSheet(
            "QFrame#monitorSignalDiagnostics{background:#041932;"
            "border:1px solid #1d81b7;border-radius:6px;}"
            "QFrame#monitorSignalDiagnostics QLabel{border:none;background:transparent;}")
        diag=QVBoxLayout(self.capture_diagnostics)
        diag.setContentsMargins(8,5,8,5)
        diag.setSpacing(3)
        diag.addWidget(label("ANÁLISIS DE ENTRADA · MEDICIÓN REAL"))
        peak_row=QHBoxLayout()
        self.capture_diag_peak=label("Pico retenido: −∞ dBFS")
        peak_row.addWidget(self.capture_diag_peak,1)
        self.capture_diag_clip=label("CLIP: 0")
        peak_row.addWidget(self.capture_diag_clip)
        reset_peak=action("Reiniciar picos",self.reset_capture_peaks)
        reset_peak.setToolTip("Pone a cero el máximo retenido y el contador de saturaciones.")
        peak_row.addWidget(reset_peak)
        diag.addLayout(peak_row)
        self.capture_diag_route=label("Esperando señal de entrada")
        self.capture_diag_route.setWordWrap(True)
        diag.addWidget(self.capture_diag_route)
        left.addWidget(self.capture_diagnostics)
        self.capture_diagnostics.hide()  # Solo candado abierto.
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
        review=getattr(self,"record_review",None)
        if review is not None:
            review.sync_capture_gain(gain)
        if hasattr(self,"capture_diag_route"):
            self.update_capture_diagnostics()
        self.balance_value.setText("Centro" if balance==0 else
                                   f"L {abs(balance)}" if balance<0 else f"R {balance}")

    def populate_processed_listen_outputs(self):
        from capture_live_listen import available_sinks,is_feedback_route,default_sink
        source=self.main.sources.currentData() or ""
        current=self.listen_output.currentData() or default_sink()
        was=self.listen_output.blockSignals(True)
        self.listen_output.clear()
        for description,sink in available_sinks():
            if not is_feedback_route(source,sink):
                self.listen_output.addItem(description,sink)
        if current:
            index=self.listen_output.findData(current)
            if index>=0:self.listen_output.setCurrentIndex(index)
        self.listen_output.blockSignals(was)
        self.listen_processed.setEnabled(self.listen_output.count()>0)
        self.listen_output.setEnabled(self.listen_output.count()>0)
        if not self.listen_output.count():
            self.capture_graph_status.setText("No hay salida segura")

    def toggle_processed_listen(self,enabled):
        from capture_live_listen import is_feedback_route
        sink=self.listen_output.currentData() or ""
        source=self.main.sources.currentData() or ""
        if enabled and (not sink or is_feedback_route(source,sink)):
            blocked=self.listen_processed.blockSignals(True)
            self.listen_processed.setChecked(False)
            self.listen_processed.blockSignals(blocked)
            self.capture_graph_status.setText("Selecciona otra salida")
            return
        if enabled and (self.main.worker is None or not self.main.worker.isRunning()):
            self.main.start_monitor()
        worker=self.main.worker
        if worker is None:
            blocked=self.listen_processed.blockSignals(True)
            self.listen_processed.setChecked(False)
            self.listen_processed.blockSignals(blocked)
            return
        try:
            worker.set_live_listen(enabled,sink)
            self.capture_graph_status.setText(
                "Activando escucha…" if enabled else "Escucha desactivada")
        except (ValueError,OSError) as err:
            blocked=self.listen_processed.blockSignals(True)
            self.listen_processed.setChecked(False)
            self.listen_processed.blockSignals(blocked)
            self.capture_graph_status.setText(str(err))

    def change_processed_listen_output(self,*_):
        if self.listen_processed.isChecked():
            self.toggle_processed_listen(True)

    def on_processed_listen_state(self,active,message):
        if not active and self.listen_processed.isChecked():
            blocked=self.listen_processed.blockSignals(True)
            self.listen_processed.setChecked(False)
            self.listen_processed.blockSignals(blocked)
        self.capture_graph_status.setText(message)

    def stop_processed_listen_ui(self):
        blocked=self.listen_processed.blockSignals(True)
        self.listen_processed.setChecked(False)
        self.listen_processed.blockSignals(blocked)
        self.capture_graph_status.setText("Sin señal")

    def sync_capture_visual(self,bands,wave):
        if not hasattr(self,"capture_analyzer_panel"):
            return
        if self.capture_analyzer_panel.isVisible():
            self.capture_scope.set_wave(wave)
            self.capture_spectrum.set_bands(bands)
        if not self.listen_processed.isChecked():
            self.capture_graph_status.setText("Señal procesada en vivo")

    def clear_capture_visual(self):
        self.capture_scope.set_wave([0.]*205)
        self.capture_spectrum.set_bands([0.]*48)
        self.stop_processed_listen_ui()

    def reset_capture_peaks(self):
        self._capture_peak_hold=0.0
        self._capture_clip_count=0
        self.update_capture_diagnostics()

    def update_capture_diagnostics(self):
        if not hasattr(self,"capture_diag_route"):
            return
        peak=self._capture_peak_hold
        peak_db=("−∞" if peak<1e-7 else
                 f"{20*math.log10(peak):.1f}")
        self.capture_diag_peak.setText(f"Pico retenido: {peak_db} dBFS")
        saturated=self._capture_clip_count>0
        self.capture_diag_clip.setText(
            f"CLIP: {self._capture_clip_count}" if saturated
            else "CLIP: 0" if peak<.98 else "ALTO · próximo a 0 dBFS")
        self.capture_diag_clip.setStyleSheet(
            "color:#ff6172;font-weight:800;" if saturated else
            "color:#ffc56c;font-weight:800;" if peak>=.98 else
            "color:#79edd8;font-weight:700;")
        main=self.main
        gain=main.input_gain_db
        eq=("EQ "+" / ".join(f"{value:+d}" for value in main.input_eq_values)
            +" dB" if main.input_eq_enabled else "EQ desactivado")
        running=bool(main.worker is not None and main.worker.isRunning())
        self.capture_diag_route.setText(
            ("Señal real activa" if running else "Sin señal activa")+
            f" · Captura {gain:+d} dB · {eq} · No altera tomas anteriores")

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
        # Una batería separada debe alimentar el módulo 5 tanto si se
        # terminó en esta sesión como si se restauró desde el proyecto.
        available=self.workbench.converter.project_stem_paths()
        sources=tuple(str(p) for p in available
                      if Path(p).is_file() and self._stem_for(p)=="Batería"
                      and ("drum" in Path(p).stem.casefold()
                           or "bater" in Path(p).stem.casefold()))
        # La pestaña admite cargar una batería manualmente; debe verse en
        # la tarjeta aunque todavía no figure entre los stems separados.
        imported=module.input.text().strip()
        if imported and Path(imported).is_file() and imported not in sources:
            sources=(*sources,imported)
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
        first.setContentsMargins(0,0,0,0)
        first.setSpacing(3)
        first.addWidget(label("IA"))
        self.engine=QComboBox()
        self.engine.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.engine.setMinimumContentsLength(8)
        self.engine.setToolTip("Modelo de IA para transcribir la pista seleccionada.")
        self.engine.addItem("Basic Pitch","basic")
        self.engine.addItem("Transkun piano","transkun")
        self.engine.currentIndexChanged.connect(self.select_engine)
        first.addWidget(self.engine,2)
        self.load_midi_model=QPushButton("＋",self.midi_card)
        self.load_midi_model.setFixedWidth(24)
        self.load_midi_model.setToolTip(
            "Cargar modelo ONNX de transcripción compatible con Basic Pitch.")
        self.load_midi_model.clicked.connect(self.import_midi_model)
        first.addWidget(self.load_midi_model)
        first.addWidget(label("Preset"))
        self.midi_preset=QComboBox()
        self.midi_preset.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.midi_preset.setMinimumContentsLength(6)
        self.midi_preset.currentIndexChanged.connect(self.choose_midi_preset)
        first.addWidget(self.midi_preset,1)
        c.addLayout(first)
        stems_row=QHBoxLayout()
        stems_row.setSpacing(3)
        stems_label=label("Pista")
        stems_label.setToolTip("Selecciona un instrumento REAL ya separado para convertirlo a MIDI.")
        stems_row.addWidget(stems_label)
        self.midi_stem_select=QComboBox(self.midi_card)
        self.midi_stem_select.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.midi_stem_select.setMinimumContentsLength(10)
        self.midi_stem_select.setToolTip("Pistas extraídas del proyecto. No incluye instrumentos ficticios.")
        self.midi_stem_select.addItem("Elige una pista separada…",None)
        self.midi_stem_select.currentIndexChanged.connect(self._choose_midi_stem)
        stems_row.addWidget(self.midi_stem_select,1)
        self.midi_stem_reload=QPushButton("↻",self.midi_card)
        self.midi_stem_reload.setToolTip("Actualizar lista de pistas separadas existentes.")
        self.midi_stem_reload.setFixedWidth(24)
        self.midi_stem_reload.clicked.connect(lambda:self._sync_midi_stems(force=True))
        stems_row.addWidget(self.midi_stem_reload)
        c.addLayout(stems_row)
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
        from results_dragdrop import ResultsDragTable
        self.files=ResultsDragTable()
        self.files.setColumnCount(3)
        self.files.setHorizontalHeaderLabels(["Nombre","Tipo","Duración"])
        self.files.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.files.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.files.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.files.verticalHeader().hide()
        self.files.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Selección de distintas filas sin salir de la pantalla Inicio.
        self.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files.setToolTip(
            "Ctrl+clic selecciona archivos sueltos; Mayús+clic un intervalo; "
            "Ctrl+A todos. Clic derecho para guardar o eliminar varios.")
        self.files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.files.itemSelectionChanged.connect(self.file_selected)
        self.files.cellDoubleClicked.connect(self.file_double_clicked)
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._results_context_menu)
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
        from PySide6.QtWidgets import QTextBrowser
        from result_file_details import ResultInfoReader
        self.result_about=QTextBrowser(self)
        self.result_about.setObjectName("resultFileTechnicalDetails")
        self.result_about.setReadOnly(True)
        self.result_about.setOpenExternalLinks(False)
        self.result_about.setStyleSheet(
            "QTextBrowser#resultFileTechnicalDetails { background:#031734;"
            "color:#d5f6ff;border:1px solid #287fbe;border-radius:5px;"
            "font-size:12px;padding:5px; }")
        self.result_about.setPlainText(
            "Selecciona un archivo para conocer sus datos reales.")
        self._result_info_reader=ResultInfoReader(self)
        self._result_info_reader.ready.connect(self._show_result_metadata)
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
        # Vista L/R de señal PCM real; sin duplicar ningún motor de audio.
        from widgets import StereoMeter
        self.result_vu=StereoMeter(self)
        self.result_vu.setObjectName("resultStereoMeasuredVu")
        self.result_vu.setMinimumHeight(45)
        self.result_vu.setMaximumHeight(48)
        self.result_vu.setToolTip(
            "Nivel real RMS/Peak del PCM audible (L/R, dBFS), después del "
            "volumen software. Para MIDI se mide el WAV sintetizado.")
        self.result_vu.hide()  # Disponible solo al reproducir; evitar saturar Inicio.
        self.result_vu_caption=label("VU L/R · Sin reproducción",muted=True)
        self.result_vu_caption.setToolTip(self.result_vu.toolTip())
        self.result_vu_caption.setMaximumHeight(17)
        c.addWidget(self.result_vu_caption)
        c.addWidget(self.result_vu)
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
        zoom_in=action("+",lambda:self.wave_zoom.setValue(min(50,self.wave_zoom.value()+1)))
        for b in (zoom_out,zoom_in):b.setFixedWidth(30);progress.addWidget(b)
        c.addLayout(progress)
        self.wave_zoom=QSlider(Qt.Horizontal)
        self.wave_zoom.setRange(1,50);self.wave_zoom.setValue(1)
        self.wave_zoom.setToolTip("Zoom horizontal de ×1 a ×50 con seguimiento continuo")
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
        c.setSpacing(8)
        # Cabecera M/S sobre las columnas M/S de las pistas.
        header=QHBoxLayout();header.setSpacing(4)
        caption=QLabel("Todas")
        caption.setFixedWidth(69)
        header.addWidget(caption)
        self.stem_all_mute=QPushButton("M")
        self.stem_all_solo=QPushButton("S")
        for button,tooltip in (
                (self.stem_all_mute,"Silenciar todas las pistas disponibles"),
                (self.stem_all_solo,"Activar todas las pistas disponibles")):
            button.setCheckable(True)
            button.setFixedSize(27,25)
            button.setToolTip(tooltip)
            self._style_stem_ms_button(button)
            header.addWidget(button)
        header.addStretch(1)
        c.addLayout(header)
        self.stem_all_mute.clicked.connect(
            lambda checked:self.set_all_stems("mute",checked))
        self.stem_all_solo.clicked.connect(
            lambda checked:self.set_all_stems("solo",checked))
        for name in ("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros"):
            row=QHBoxLayout();row.setSpacing(4)
            # El nombre es el selector explícito, NO otro Play.
            col=QPushButton(name)
            col.setObjectName("stemSelectLabel")
            col.setCheckable(True)
            col.setCursor(Qt.PointingHandCursor)
            col.setToolTip("Activar/desactivar la pista "+name+" en la mezcla")
            col.setStyleSheet(
                "QPushButton#stemSelectLabel{color:"+COLORS[name]+
                ";background:transparent;border:1px solid transparent;"
                "font-weight:700;text-align:left;padding:0px 3px;}"
                "QPushButton#stemSelectLabel:checked{background:#0a3765;"
                "border:1px solid #28bcf4;border-radius:4px;}")
            col.setFixedWidth(69)
            col.clicked.connect(lambda checked=False,n=name:self.select_or_play_stem(n))
            row.addWidget(col)
            # Único par M/S a la IZQUIERDA, con separación legible.
            mute=QPushButton("M");solo=QPushButton("S")
            for button,meaning in ((mute,"Silenciar"),(solo,"Escuchar en solo")):
                button.setCheckable(True)
                button.setFixedSize(27,25)
                button.setToolTip(meaning+" · "+name+" · estado compartido con Mezclador")
                self._style_stem_ms_button(button)
                row.addWidget(button)
            tiny=WaveCanvas(small=True)
            tiny.wave_color=COLORS[name]
            tiny.setFixedHeight(24)
            tiny.clicked.connect(lambda fraction,n=name:self.select_or_play_stem(n,fraction))
            tiny.setToolTip("Elegir "+name+" para el transporte general, sin reproducir automáticamente")
            tiny.setMinimumWidth(70)
            row.addWidget(tiny,1)
            play=QPushButton("▶")
            stop=QPushButton("■")
            play.setToolTip(f"Reproducir solo la pista {name}")
            stop.setToolTip(f"Detener la pista {name}")
            # El Play/Stop por fila queda retirado de la interfaz.
            # Se conserva el objeto para no alterar operaciones existentes.
            for button in (play,stop):
                button.setFixedSize(22,23)
                button.hide()
            play.clicked.connect(lambda checked=False,n=name:self.play_stem(n))
            stop.clicked.connect(lambda checked=False,n=name:self.stop_stem(n))
            # Control de ganancia lógico, sin duplicar deslizantes: los
            # faders editables solo se muestran en el Mezclador.
            gain=QSlider(Qt.Horizontal,self)
            gain.setRange(0,150);gain.setValue(100)
            gain.hide()
            c.addLayout(row)
            self.track_rows[name]={"solo":solo,"mute":mute,"gain":gain,
                                   "play":play,"stop":stop,"wave":tiny,"path":None,
                                   "title":col}
            solo.clicked.connect(lambda yes,n=name:self.toggle_stem(n,"solo",yes))
            mute.clicked.connect(lambda yes,n=name:self.toggle_stem(n,"mute",yes))
            gain.valueChanged.connect(lambda val,n=name:self.mix_changed(n))
        c.addStretch(1)

    @staticmethod
    def _style_stem_ms_button(button):
        """Estados M y S claramente resaltados tanto en Inicio como flotante."""
        button.setObjectName("stemMuteButton" if button.text()=="M" else "stemSoloButton")
        button.setStyleSheet("""
            QPushButton#stemMuteButton,QPushButton#stemSoloButton{
                color:#dbf6ff;background:#05295d;border:1px solid #278ac3;
                border-radius:5px;font-weight:800;padding:0px;}
            QPushButton#stemMuteButton:checked{
                color:#fff;background:#9d3045;border:2px solid #ff9eaa;}
            QPushButton#stemSoloButton:checked{
                color:#fff;background:#087eae;border:2px solid #81f8ff;}
            QPushButton#stemMuteButton:disabled,QPushButton#stemSoloButton:disabled{
                color:#748fa7;background:#081d36;border-color:#183950;}
        """)

    def _stem_active_names(self):
        # El refresco de inventario ya verificó el archivo y actualizó
        # setEnabled. No hacer 7 stat() USB por cada cambio de ganancia.
        return {name for name,row in self.track_rows.items()
                if row["path"] is not None and row["solo"].isEnabled()}

    def _stem_audible_names(self):
        return {name for name in self._stem_active_names()
                if self.track_rows[name]["solo"].isChecked()
                and not self.track_rows[name]["mute"].isChecked()}

    @staticmethod
    def _set_stem_check(button,value):
        blocked=button.blockSignals(True)
        try:button.setChecked(bool(value))
        finally:button.blockSignals(blocked)

    def update_stem_header(self):
        available=self._stem_active_names()
        for name,row in self.track_rows.items():
            self._set_stem_check(row["title"],
                                 name in available and row["solo"].isChecked()
                                 and not row["mute"].isChecked())
        if hasattr(self,"stem_all_mute"):
            self.stem_all_mute.setEnabled(bool(available))
            self.stem_all_solo.setEnabled(bool(available))
            self._set_stem_check(self.stem_all_mute,bool(available) and all(
                self.track_rows[name]["mute"].isChecked() for name in available))
            self._set_stem_check(self.stem_all_solo,bool(available) and all(
                self.track_rows[name]["solo"].isChecked()
                and not self.track_rows[name]["mute"].isChecked()
                for name in available))
        manager=getattr(self,"_floating_manager",None)
        popup=manager.windows.get(self.track_card) if manager else None
        transport=getattr(popup,"float_transport",None) if popup else None
        if transport is not None:transport.sync_track_mix()

    def toggle_stem(self,name,mode,checked):
        """M/S excluyentes. Desmutear devuelve el Solo anterior, si lo había.

        El estado lo comparten las tarjetas, el Mezclador y el motor PCM.
        No reinicia la reproducción cuando cambia una pista.
        """
        row=self.track_rows[name]
        if mode=="mute":
            if checked:
                row["_resume_solo"]=row["solo"].isChecked()
                self._set_stem_check(row["solo"],False)
            elif row.pop("_resume_solo",False):
                self._set_stem_check(row["solo"],True)
        else:
            row.pop("_resume_solo",None)
            if checked:self._set_stem_check(row["mute"],False)
        self.mix_changed(name)
        self.update_stem_header()

    def set_all_stems(self,mode,checked):
        """Botones M/S generales; afectan únicamente a pistas disponibles."""
        available=self._stem_active_names()
        # Actualizar las casillas como una única operación: sincronizar la
        # reproducción multipista al terminar y evitar estados parciales.
        for name in available:
            row=self.track_rows[name]
            if mode=="mute":
                if checked:
                    row["_resume_solo"]=row["solo"].isChecked()
                    self._set_stem_check(row["solo"],False)
                elif row.pop("_resume_solo",False):
                    self._set_stem_check(row["solo"],True)
            else:
                row.pop("_resume_solo",None)
                if checked:self._set_stem_check(row["mute"],False)
            self._set_stem_check(row[mode],checked)
            self._mix_pending_changes.add(name)
        for name in available:
            self.mix_changed(name)
        self.update_stem_header()

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
        # Mantener el selector como modelo de sincronización interno sin
        # mostrar dos formas distintas de escoger MIDI. La selección visible
        # se hace SOLO desde la lista superior.
        self.midi_choice=QComboBox(self.piano_card)
        self.midi_choice.hide()
        self.midi_choice.currentIndexChanged.connect(self.choose_midi)
        self.piano_active_name=QLabel("MIDI activo: ninguno",self.piano_card)
        self.piano_active_name.setObjectName("pianoActiveFileName")
        self.piano_active_name.setStyleSheet(
            "color:#e2faff;font-weight:700;background:#071c3b;"
            "border:1px solid #2c9cde;border-radius:4px;padding:3px 6px;")
        self.piano_active_name.setMinimumWidth(155)
        self.piano_active_name.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        header.addWidget(self.piano_active_name,1)
        self.piano_pencil_button=QPushButton("✎")
        self.piano_pencil_button.setCheckable(True)
        self.piano_pencil_button.setFixedWidth(32)
        self.piano_pencil_button.setToolTip(
            "Lápiz MIDI: pulsa y arrastra sobre el rollo para dibujar"
            " notas y definir su duración. Vuelve a pulsar para seleccionar.")
        self.piano_pencil_button.toggled.connect(
            lambda enabled:self.piano_preview.set_pencil_mode(enabled))
        self.piano_pencil_button.setStyleSheet(
            "QPushButton:checked{background:#117fc0;color:white;"
            "border:2px solid #8effcd;}")
        header.addWidget(self.piano_pencil_button)
        self.piano_undo_button=action("↶",self.undo_piano_notes)
        self.piano_redo_button=action("↷",self.redo_piano_notes)
        self.piano_reset_button=action("Reset",self.reset_piano_edits)
        self.piano_undo_button.setToolTip("Deshacer la última edición MIDI")
        self.piano_reset_button.setToolTip(
            "Restaurar todas las notas al estado inicial del MIDI."
            " No sobrescribe el original; se puede Deshacer.")
        self.piano_redo_button.setToolTip("Rehacer la última edición MIDI")
        header.addWidget(self.piano_undo_button)
        header.addWidget(self.piano_reset_button)
        header.addWidget(self.piano_redo_button)
        self.piano_delete_notes_button=action(
            "Eliminar",self.delete_piano_selected_notes)
        self.piano_delete_notes_button.setToolTip(
            "Eliminar las notas MIDI seleccionadas (también multipista)."
            " Una sola operación Deshacer las recupera.")
        header.addWidget(self.piano_delete_notes_button)
        self.piano_full_editor_button=action("Editor completo",self.open_piano)
        self.piano_full_editor_button.setToolTip(
            "Abrir la pestaña completa de Piano Roll sin perder las notas editadas")
        header.addWidget(self.piano_full_editor_button)
        self.grid_choice=QComboBox()
        self.grid_choice.addItems(["Sin ajuste","1/4","1/8","1/16","1/32","1/64"])
        self.grid_choice.setToolTip(
            "Rejilla para dibujar y mover notas. No cuantiza por sí sola "
            "las notas existentes: para eso está Cuantizar notas arriba.")
        self.grid_choice.setCurrentText("1/16")
        self.grid_choice.currentTextChanged.connect(self.change_grid)
        header.addWidget(self.grid_choice)
        self._set_piano_active_name(None)
        # Los controles de velocidad y navegación caben en segunda línea
        # para mantener legible el Piano Roll, ahora más estrecho.
        c.addLayout(header)
        header=QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(label("Posición"))
        back=action("◀",lambda:self.step_piano(-4))
        next_=action("▶",lambda:self.step_piano(4))
        back.setToolTip("Retroceder cuatro compases")
        next_.setToolTip("Avanzar cuatro compases")
        header.addWidget(back)
        header.addWidget(next_)
        self.roll_position=QSlider(Qt.Horizontal)
        self.roll_position.setRange(0,1000)
        self.roll_position.setMinimumWidth(110)
        self.roll_position.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.roll_position.setToolTip(
            "Posición horizontal del piano roll. 0 % al principio, 100 % al final.")
        self.roll_position.valueChanged.connect(
            lambda val:self.piano_preview.set_scroll(val/1000))
        header.addWidget(self.roll_position,1)
        header.addWidget(label("Intensidad MIDI"))
        self.note_velocity=QSlider(Qt.Horizontal)
        self.note_velocity.setRange(1,127);self.note_velocity.setValue(90)
        self.note_velocity.setMaximumWidth(105)
        self.note_velocity.setToolTip(
            "Velocidad MIDI 1–127: fuerza de la pulsación. No cambia el tempo. "
            "Aplica la intensidad a notas seleccionadas; sin selección define "
            "la fuerza de nuevas notas.")
        self.note_velocity.valueChanged.connect(self.change_velocity)
        header.addWidget(self.note_velocity)
        self.vel_value=label("90")
        self.vel_value.setToolTip("Valor de intensidad MIDI de 1 a 127")
        header.addWidget(self.vel_value)
        header.addWidget(label("Tempo canción"))
        self.piano_song_tempo=QSlider(Qt.Horizontal,self.piano_card)
        self.piano_song_tempo.setObjectName("pianoSongTempoBpm")
        self.piano_song_tempo.setRange(35,300)
        self.piano_song_tempo.setValue(120)
        self.piano_song_tempo.setMaximumWidth(104)
        self.piano_song_tempo.setMinimumWidth(70)
        self.piano_song_tempo.setToolTip(
            "Tempo REAL de la canción MIDI y su reproducción."
            " Solo cambia set_tempo, nunca desplaza notas ni compases."
            " Independiente del tempo de composición del generador superior.")
        header.addWidget(self.piano_song_tempo)
        self.piano_song_tempo_readout=label("120 BPM")
        self.piano_song_tempo_readout.setMinimumWidth(56)
        header.addWidget(self.piano_song_tempo_readout)
        self._piano_song_tempo_timer=QTimer(self)
        self._piano_song_tempo_timer.setSingleShot(True)
        self._piano_song_tempo_timer.setInterval(350)
        self._piano_song_tempo_timer.timeout.connect(self.apply_piano_song_tempo)
        self.piano_song_tempo.valueChanged.connect(
            lambda bpm:(self.piano_song_tempo_readout.setText(f"{bpm} BPM"),
                        self._piano_song_tempo_timer.start()))
        self.piano_song_tempo.sliderReleased.connect(self.apply_piano_song_tempo)
        self.workbench.piano.midiOpened.connect(
            lambda _:self._sync_piano_song_tempo())
        self.workbench.piano.tempo_bpm.valueChanged.connect(
            lambda _:self._sync_piano_song_tempo())
        c.addLayout(header)
        self.piano_navigation=QWidget(self.piano_card)
        nav=QHBoxLayout(self.piano_navigation)
        nav.setContentsMargins(0,0,0,0);nav.setSpacing(5)
        nav.addWidget(label("Zoom H"))
        self.piano_zoom_h=QSlider(Qt.Horizontal)
        self.piano_zoom_h.setRange(25,2000)
        self.piano_zoom_h.setValue(100)
        self.piano_zoom_h.setToolTip("Zoom horizontal: 25–2000 %")
        nav.addWidget(self.piano_zoom_h,2)
        self.piano_zoom_h_value=label("100 %")
        nav.addWidget(self.piano_zoom_h_value)
        nav.addWidget(label("Teclas"))
        self.piano_zoom_v=QSlider(Qt.Horizontal)
        self.piano_zoom_v.setRange(8,88)
        self.piano_zoom_v.setValue(37)
        self.piano_zoom_v.setToolTip("Zoom vertical: entre 8 y 88 teclas visibles")
        nav.addWidget(self.piano_zoom_v,1)
        self.piano_zoom_v_value=label("37")
        nav.addWidget(self.piano_zoom_v_value)
        self.piano_fit=action("Ver todo",self.fit_piano)
        self.piano_fit.setToolTip("Mostrar el MIDI entero y las 88 teclas")
        nav.addWidget(self.piano_fit)
        c.addWidget(self.piano_navigation)
        self.piano_navigation.hide()  # en Inicio compacto no quitar altura al roll
        self.piano_preview=PianoOverview()
        self.piano_preview.editor_owner=self.workbench.piano
        self.piano_preview.setToolTip(
            "Clic: seleccionar · Ctrl/Mayús: selección múltiple · Arrastrar:"
            " mover · Arrastrar desde espacio vacío: recuadro para varias"
            " notas · Mayús: añadir · Botón ✎: dibujar manteniendo pulsado"
            " y arrastrando la duración · Eliminar/Supr: borrar seleccionadas")
        self.piano_preview.activated.connect(self.seek_piano)
        self.piano_preview.viewChanged.connect(self._roll_scroll_changed)
        self.piano_preview.zoomChanged.connect(self._sync_piano_zoom)
        self.piano_preview.pitchChanged.connect(self._sync_piano_pitch)
        self.piano_preview.seekRequested.connect(self.seek_piano_tick)
        self.piano_zoom_h.valueChanged.connect(
            self.piano_preview.set_zoom_percent)
        self.piano_zoom_v.valueChanged.connect(self._set_piano_visible_keys)
        roll_row=QHBoxLayout();roll_row.setContentsMargins(0,0,0,0)
        roll_row.setSpacing(3)
        roll_row.addWidget(self.piano_preview,1)
        self.piano_pitch_scroll=QSlider(Qt.Vertical,self.piano_card)
        self.piano_pitch_scroll.setRange(21,72)
        self.piano_pitch_scroll.setValue(48)
        self.piano_pitch_scroll.setToolTip("Desplazamiento vertical de las 88 teclas MIDI")
        self.piano_pitch_scroll.valueChanged.connect(
            lambda v:self.piano_preview.set_pitch_window(v))
        self.piano_pitch_scroll.hide()
        roll_row.addWidget(self.piano_pitch_scroll)
        c.addLayout(roll_row,1)

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
        # Origen importado desde la pestaña vocal: mostrarlo también en
        # Inicio, sin fingir que procede de una separación del proyecto.
        imported=module.input.text().strip()
        if imported and Path(imported).is_file() and imported not in sources:
            sources=(*sources,imported)
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
        c.setContentsMargins(5,3,5,3)
        c.setSpacing(2)
        from midi_to_audio_card import MidiToAudioCard
        self.midi_to_audio=MidiToAudioCard(self,self.info_card)
        c.addWidget(self.midi_to_audio)
        # Conservar las estadísticas en memoria para la integración con
        # Piano Roll, pero no mostrar la tarjeta duplicada de Información.
        self.note_info=label("Notas: —")
        self.duration_info=label("Duración: —")
        self.tempo_info=label("Tempo: —")
        self.key_info=label("Tonalidad: —")

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
        if hasattr(self,"capture_analyzer_panel") and self.capture_analyzer_panel.isVisible():
            self.populate_processed_listen_outputs()

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

    def _refresh_midi_models(self):
        from midi_model_options import list_models
        previous=self.engine.currentData()
        wanted=[("Basic Pitch","basic"),
                ("Transkun piano","transkun")]
        wanted.extend((name,("onnx",path)) for name,path in list_models())
        current=[(self.engine.itemText(i),self.engine.itemData(i))
                 for i in range(self.engine.count())]
        if current==wanted:return
        was=self.engine.blockSignals(True)
        self.engine.clear()
        for name,data in wanted:self.engine.addItem(name,data)
        index=next((i for i in range(self.engine.count())
                    if self.engine.itemData(i)==previous),-1)
        if index>=0:self.engine.setCurrentIndex(index)
        self.engine.blockSignals(was)

    def import_midi_model(self):
        if self.workbench.converter.process is not None:return
        from midi_model_options import import_model
        from studio_paths import workspace_root
        base=workspace_root(__file__)/"modelos"/"audio_a_midi"
        name,_=file_dialogs.get_open_file_name(self,
                 "Cargar modelo de transcripción Basic Pitch ONNX",str(base),
                 "Modelo Basic Pitch ONNX (*.onnx)")
        if not name:return
        try:
            loaded=import_model(name)
        except (OSError,ValueError,RuntimeError) as exc:
            QMessageBox.warning(self,"Modelo incompatible",str(exc))
            return
        self._refresh_midi_models()
        index=next((i for i in range(self.engine.count())
                    if self.engine.itemData(i)==("onnx",str(loaded))),-1)
        if index<0:
            QMessageBox.warning(self,"Modelo","No se pudo incluir el modelo en la lista.")
            return
        self.engine.setCurrentIndex(index)
        self.engine.setToolTip("ONNX compatible: "+str(loaded))

    def select_engine(self,index):
        if self._loading or index<0:return
        converter=self.workbench.converter
        data=self.engine.itemData(index)
        converter.custom_model_path=(str(data[1]) if isinstance(data,tuple)
                                     and data[0]=="onnx" else None)
        converter.piano_specialist.setChecked(data=="transkun")
        converter.save_preferences()

    def _sync_midi_stems(self,force=False):
        converter=self.workbench.converter
        paths=converter.project_stem_paths()
        signature=tuple(str(p) for p in paths)
        if not force and signature==getattr(self,"_midi_stems_signature",None):
            return
        self._midi_stems_signature=signature
        current=self.midi_stem_select.currentData()
        desired=current if current in signature else None
        # Evitar arrastrar la elección de otro proyecto. Si el conversor ya
        # tiene un stem de ESTE proyecto, representarlo correctamente.
        if desired is None:
            loaded=converter.audio_path.text().strip()
            if loaded in signature:desired=loaded
        old=self.midi_stem_select.blockSignals(True)
        self.midi_stem_select.clear()
        self.midi_stem_select.addItem("Elige una pista separada…",None)
        for path in paths:
            category=self._stem_for(path)
            self.midi_stem_select.addItem(f"{category} · {path.name}",str(path))
            self.midi_stem_select.setItemData(
                self.midi_stem_select.count()-1,str(path),Qt.ToolTipRole)
        selected=self.midi_stem_select.findData(desired)
        self.midi_stem_select.setCurrentIndex(max(0,selected))
        self.midi_stem_select.blockSignals(old)
        self.midi_stem_select.setToolTip(
            f"{len(paths)} pistas separadas reales del proyecto. Elige una para convertir."
            if paths else "Aún no existen pistas separadas en el proyecto.")

    def _choose_midi_stem(self,index):
        if self._loading or index<0:return
        path=self.midi_stem_select.itemData(index)
        if path:
            ok=self.workbench.converter.choose_project_stem(path)
            if not ok:
                QMessageBox.warning(self,"Pista no disponible",
                                    "La pista seleccionada ya no está disponible.")
                self._sync_midi_stems(force=True)

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
            self._refresh_midi_models()
            model=converter.custom_model_path
            requested=(("onnx",model) if model else
                       "transkun" if converter.piano_specialist.isChecked()
                       else "basic")
            i=next((j for j in range(self.engine.count())
                    if self.engine.itemData(j)==requested),-1)
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
        # El botón compacto tampoco puede repetir una cola ya iniciada.
        if converter.process is not None or getattr(converter,"_home_queue_busy",False):
            return
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
        if index==2:self.file_selected()

    def _show_result_metadata(self,generation,report):
        if self._result_info_reader.is_current(generation):
            self.result_about.setPlainText(report)

    def _request_result_metadata(self,path):
        if path is None or not Path(path).is_file():
            self._result_info_reader.clear()
            self.result_about.setPlainText("No hay ningún archivo seleccionado.")
            return
        self.result_about.setPlainText("Leyendo metadatos reales del archivo…")
        self._result_info_reader.request(
            path,getattr(self.main,"project_dir",None),self._stem_for(path))

    def _sync_result_vu(self):
        """Medición de la señal REAL del reproductor de Resultados.

        No inferir audio a partir de eventos MIDI ni usar temporizadores
        para generar niveles. La decodificación PCM está en MeasuredPlaybackVU.
        """
        player=self.player
        observed=getattr(player,"_measured_vu",None) if player else None
        active=bool(player and (player._qt_active or player._play_process is not None)
                    and not player._paused and observed and observed.levels)
        sample=(0.,0.,0.,0.)
        if active:
            index=int(max(0,player._position())/100)
            if 0<=index<len(observed.levels):
                gain=player.volume.value()/100.
                sample=tuple(max(0.,min(1.,float(x)*gain))
                             for x in observed.levels[index])
        self.result_vu.set_levels(*sample)
        playing=bool(player and (player._qt_active or player._play_process is not None)
                    and not player._paused)
        # Mantener visible con audio activo, y resetear al detenerlo.
        # Con candado cerrado Resultados es SOLO archivos y transporte.
        self.result_vu.setVisible(self._is_float(self.result_card))
        self.result_vu_caption.setText(
            ("VU L/R · RMS/Peak PCM real" if playing else "VU L/R · Detenido")
            + (" · MIDI sintetizado" if player and player.current_file and
               Path(player.current_file).suffix.lower() in MIDI else ""))
        return sample

    def file_selected(self):
        row=self.files.currentRow()
        if row<0:
            self.selected_file=None
            self._request_result_metadata(None)
            return
        item=self.files.item(row,0)
        if not item:return
        path=Path(item.data(Qt.UserRole))
        self.selected_file=path
        self._request_result_metadata(path)
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
                        editor=self.workbench.piano
                        if editor.current_path==source.resolve() or editor.open_midi(source):
                            self.selected_midi=source
                            self.piano_preview.set_midi(source)
                            self.piano_preview.set_live_editor(editor)
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

    def _results_context_menu(self,position):
        from PySide6.QtWidgets import QMenu
        index=self.files.indexAt(position)
        selected=self._selected_results()
        clicked=None
        if index.isValid():
            item=self.files.item(index.row(),0)
            if item is not None:clicked=Path(item.data(Qt.UserRole))
        # Sobre una fila seleccionada: operar sobre TODAS las seleccionadas.
        # Sobre otra fila: sólo sobre esa, sin borrar otro grupo por error.
        files=selected if (clicked is None or clicked in selected) else [clicked]
        menu=QMenu(self.files)
        all_action=menu.addAction("Seleccionar todos · Ctrl+A")
        clear_action=menu.addAction("Quitar selección")
        menu.addSeparator()
        save=menu.addAction(f"Guardar {len(files)} archivo(s) seleccionados…")
        delete=menu.addAction(f"Eliminar {len(files)} archivo(s) seleccionados…")
        save.setEnabled(bool(files))
        delete.setEnabled(bool(files))
        action=menu.exec(self.files.viewport().mapToGlobal(position))
        if action is all_action:
            self.files.selectAll()
        elif action is clear_action:
            self.files.clearSelection()
        elif action is save:
            self._save_results(files)
        elif action is delete:
            from safe_file_delete import trash_files
            if trash_files(self,files):
                self.refresh(force=True)

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
        from vocal_catalog import vocal_role
        voice=vocal_role(path)
        if voice:return voice
        from drum_module import category as drum_category,PARTS
        audio_path=Path(path)
        # Evitar clasificar por accidente títulos de canciones que contienen
        # palabras como "Ride" o "Crash": únicamente carpetas de despiece
        # auténticas o archivos con nombre exacto de la pieza.
        in_drum_set=any(part.casefold() in ("bateria","batería","drum_stems")
                        for part in audio_path.parts)
        if in_drum_set or audio_path.stem.casefold() in {
                "bombo","caja","toms","charles","ride","crash"}:
            piece=drum_category(audio_path)
            if piece in PARTS:return piece
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
        # Las pistas guardadas del proyecto deben aparecer aun cuando
        # no exista una tarea temporal activa (p. ej. tras reiniciar).
        # Audio→MIDI consulta project_audio_sources; usar la misma fuente
        # autorizada y evitar mezclar proyectos anteriores.
        from task_staging import project_audio_sources
        project=getattr(self.main,"project_dir",None)
        items=project_audio_sources(project,("separaciones",))
        items.extend(Path(p) for p in self.workbench.separation_storage.items
                     if Path(p).is_file())
        items=list(dict.fromkeys(Path(p).resolve() for p in items
                                  if Path(p).is_file()))
        sources={}
        # Preferir resultados de la tarea actual si hay repetidos.
        for path in items:
            kind=self._stem_for(path)
            if kind in self.track_rows:sources[kind]=path
        for name,parts in self.track_rows.items():
            file=sources.get(name)
            parts["path"]=file
            # La selección de extracción no oculta resultados guardados.
            display=bool(file)
            parts["wave"].set_file(file if display else None)
            parts["title"].setEnabled(display)
            if not display:parts["title"].setChecked(False)
            parts["solo"].setEnabled(display)
            parts["mute"].setEnabled(display)
            parts["gain"].setEnabled(display)
            parts["play"].setEnabled(display)
            parts["stop"].setEnabled(display)
            if not display:
                parts["solo"].setChecked(False)
                parts["mute"].setChecked(False)
        self._track_lookup=sources
        self.update_stem_header()

    def select_or_play_stem(self,name,fraction=0.):
        """Una onda en la ventana flotante selecciona, nunca suena sola."""
        manager=getattr(self,"_floating_manager",None)
        popup=(manager.windows.get(self.track_card) if manager else None)
        if popup is not None:
            # Una pulsación sobre nombre/onda alterna su S en el bus común.
            row=self.track_rows.get(name)
            if row is not None and name in self._stem_active_names():
                new_state=not row["solo"].isChecked()
                self._set_stem_check(row["solo"],new_state)
                self.toggle_stem(name,"solo",new_state)
            return
        self.play_stem(name,fraction)

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

    def sync_active_stem_gain(self):
        """El reproductor y el Mezclador comparten nivel y M/S actuales."""
        player=self.player
        if player is None or not player.current_file:return
        current=Path(player.current_file)
        row=next((part for part in self.track_rows.values()
                  if part["path"] is not None and
                  Path(part["path"]).resolve()==current),None)
        if row is None:return
        muted=(row["mute"].isChecked() or (
            any(part["solo"].isChecked() for part in self.track_rows.values())
            and not row["solo"].isChecked()))
        if muted:
            player.stop()
        else:
            player.volume.setValue(min(100,round(
                self.master_volume.value()*row["gain"].value()/100)))

    def mix_changed(self,name):
        if self._loading or getattr(getattr(self,"_tab_sync",None),"_syncing_mixer",False):
            return
        track=self.track_rows[name]
        # Marcar sólo los controles tocados desde Inicio antes de crear
        # la pestaña dinámica: no pisar los otros presets guardados.
        self._mix_pending_changes.add(name)
        self.sync_active_stem_gain()
        self.update_stem_header()
        if (self.player is not None and
            self.selected_file==track["path"] and
            (track["mute"].isChecked() or
              any(v["solo"].isChecked() for v in self.track_rows.values()
                  if v is not track) and not track["solo"].isChecked())):
            self.player.stop()
        if self.workbench.mixer is not None:
            # Inicio -> Mezclador: no permitir que una señal intermedia del
            # Mixer sobrescriba S/M mientras todavía se están transmitiendo.
            bridge=getattr(self,"_tab_sync",None)
            old=bridge._syncing_mixer if bridge else False
            if bridge:bridge._syncing_mixer=True
            try:
                for item in self.workbench.mixer.rows:
                    if self._stem_for(item["path"])!=name:continue
                    item["slider"].setValue(track["gain"].value())
                    item["solo"].setChecked(track["solo"].isChecked())
                    item["mute"].setChecked(track["mute"].isChecked())
            finally:
                if bridge:bridge._syncing_mixer=old

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
            if name not in self._mix_pending_changes:continue
            data=self.track_rows[name]
            row["slider"].setValue(data["gain"].value())
            row["solo"].setChecked(data["solo"].isChecked())
            row["mute"].setChecked(data["mute"].isChecked())
        self._mix_pending_changes.clear()
        bridge=getattr(self,"_tab_sync",None)
        if bridge is not None:
            bridge.bind_mixer()
            bridge.sync_mixer_to_home()

    def _sync_piano_song_tempo(self):
        """Reflejar los BPM reales sin que el deslizador los reescriba."""
        editor=self.workbench.piano
        if editor.midi is None:return
        self._piano_song_tempo_timer.stop()
        target=max(35,min(300,round(editor.current_bpm())))
        with QSignalBlocker(self.piano_song_tempo):
            self.piano_song_tempo.setValue(target)
        self.piano_song_tempo_readout.setText(f"{target} BPM")

    def apply_piano_song_tempo(self):
        """Edición undoable del set_tempo, NO cuantización ni escalado de notas."""
        self._piano_song_tempo_timer.stop()
        editor=self.workbench.piano
        if editor.midi is None or not editor.tracks:return
        bpm=self.piano_song_tempo.value()
        old=editor.current_bpm()
        if abs(bpm-old)<.005:return
        from midi_tempo_utils import set_bpm_preserve_figures
        editor.snapshot()
        set_bpm_preserve_figures(editor.tracks,bpm)
        with QSignalBlocker(editor.tempo_bpm):
            editor.tempo_bpm.setValue(editor.current_bpm())
        editor.redraw()
        editor.dirty=True
        self.piano_preview.set_live_editor(editor)
        self.piano_song_tempo_readout.setText(f"{bpm} BPM")

    def _refresh_piano_after_history(self):
        editor=self.workbench.piano
        if editor.midi is None:return
        self.piano_preview._set_note_selection(set())
        self.piano_preview.set_live_editor(editor)
        self._sync_piano_song_tempo()

    def undo_piano_notes(self):
        editor=self.workbench.piano
        if editor.midi is None:return
        if editor.history:
            editor.undo()
            self._refresh_piano_after_history()
            return
        # open_midi limpia history: ofrecer deshacer también «Nuevo MIDI».
        manager=getattr(self,"_floating_manager",None)
        if manager is not None:
            panel=manager.other_expanders[self.piano_card].piano_tools
            panel.restore_previous_new()

    def redo_piano_notes(self):
        editor=self.workbench.piano
        if editor.midi is None or not editor.future:return
        editor.redo()
        self._refresh_piano_after_history()

    def delete_piano_selected_notes(self):
        """El botón Eliminar usa exactamente la misma transacción que Supr."""
        if self.piano_preview.delete_selected_notes():return
        # Las selecciones del editor completo también son válidas aunque
        # no se hayan marcado desde la miniatura.
        editor=self.workbench.piano
        if editor.midi is None or not editor.selected_indices:return
        preview=self.piano_preview
        preview._set_note_selection({
            (editor.track_index,i) for i in editor.selected_indices})
        preview.delete_selected_notes()

    def reset_piano_edits(self):
        """Un único Reset del editor compartido, accesible en el roll inferior."""
        manager=getattr(self,"_floating_manager",None)
        if manager is None:return
        panel=manager.other_expanders[self.piano_card].piano_tools
        panel.reset_edit()

    def _sync_piano_zoom(self,percent):
        slider=self.piano_zoom_h
        old=slider.blockSignals(True)
        slider.setValue(int(percent))
        slider.blockSignals(old)
        self.piano_zoom_h_value.setText(f"{percent} %")

    def _sync_piano_pitch(self,low,span):
        self.piano_zoom_v_value.setText(str(span))
        old=self.piano_zoom_v.blockSignals(True)
        self.piano_zoom_v.setValue(span)
        self.piano_zoom_v.blockSignals(old)
        slider=self.piano_pitch_scroll
        old=slider.blockSignals(True)
        slider.setRange(21,109-span)
        slider.setValue(low)
        slider.blockSignals(old)

    def _set_piano_visible_keys(self,span):
        preview=self.piano_preview
        previous=preview.pitch_hi-preview.pitch_lo+1
        low=preview.pitch_lo+(previous-span)//2
        preview.set_pitch_window(low,span)

    def fit_piano(self):
        self.piano_preview.fit_song()

    def seek_piano_tick(self,tick):
        """Clic o arrastre de la regla temporal: posición MIDI REAL."""
        preview=self.piano_preview
        tick=max(0,min(preview.full_tick,int(tick)))
        preview.playhead_tick=tick
        preview._manual_seek_active=True
        preview.hold_follow(1.5)
        editor=self.workbench.piano
        if editor.midi is None:return
        manager=self._floating_manager
        owner=manager.windows.get(self.piano_card)
        strip=(getattr(owner,"float_transport",None) if owner else
               manager._mini_players.get(self.piano_card))
        if strip is not None and hasattr(strip,"piano_live"):
            strip.piano_live.seek_tick(tick)
        preview.update()

    def _roll_scroll_changed(self,fraction):
        old=self.roll_position.blockSignals(True)
        self.roll_position.setValue(int(fraction*1000))
        self.roll_position.blockSignals(old)

    def step_piano(self,bars):
        # Los borradores nuevos tienen MIDI en el editor aunque
        # selected_midi sea None hasta pulsar Añadir.
        if not self.selected_midi and not self.workbench.piano.midi:return
        self.piano_preview.view_start=max(0,min(
            self.piano_preview.full_tick-self.piano_preview.visible_ticks,
            self.piano_preview.view_start+bars*4*self.piano_preview.ticks_per_beat))
        self.piano_preview.update()
        self._roll_scroll_changed(
            self.piano_preview.view_start/max(1,self.piano_preview.full_tick-self.piano_preview.visible_ticks))

    def _set_piano_active_name(self,path,unsaved=False):
        """Etiqueta del MIDI elegido arriba; jamás un segundo selector."""
        if unsaved:
            name="Nuevo MIDI · sin guardar"
            tooltip="Borrador temporal. Añádelo al proyecto para publicarlo."
        elif path:
            p=Path(path)
            name=p.name
            tooltip=str(p)
        else:
            name="Ningún MIDI seleccionado"
            tooltip="Selecciona un MIDI en la lista superior del proyecto"
        text="MIDI activo: "+name
        self.piano_active_name.setText(text)
        self.piano_active_name.setToolTip(tooltip)

    def choose_midi(self,index):
        if self._loading:return
        path=self.midi_choice.itemData(index)
        if not path:return
        candidate=Path(path)
        if not candidate.is_file():return
        editor=self.workbench.piano
        if editor.current_path!=candidate.resolve():
            if not editor.open_midi(candidate):return
        self.selected_midi=candidate
        self._set_piano_active_name(candidate)
        self.piano_preview.set_midi(candidate)
        self.piano_preview.set_live_editor(editor)
        self._roll_scroll_changed(0)
        self._update_midi_stats(candidate)
        self.piano_card.header.setText("Piano Roll · "+candidate.name)

    def change_grid(self,text):
        combo=self.workbench.piano.grid
        index=combo.findText(text)
        if index>=0:combo.setCurrentIndex(index)
        # Aunque el índice ya sea el correcto, al cambiar de MIDI varían
        # los ticks por negra (PPQ); no depende de que Qt emita change.
        self.workbench.piano.on_grid_changed()
        # Mostrar la rejilla también sobre la vista de notas de Inicio:
        # antes cambiaba el editor completo pero no se veía aquí.
        self.piano_preview.grid_division={
            "Sin ajuste":0,"1/4":4,"1/8":8,"1/16":16,
            "1/32":32,"1/64":64}.get(text,16)
        self.piano_preview.update()

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
        """Abrir el editor REAL, aun con el candado abierto.

        No recargar cuando ya hay notas modificadas en memoria: hacerlo
        destruiría el trabajo sin guardar y restauraría el MIDI anterior.
        """
        editor=self.workbench.piano
        source=self.selected_midi
        if editor.midi is None and source and source.is_file():
            if not editor.open_midi(source):return
        if self._is_float(self.piano_card):
            self._floating_manager.redock(self.piano_card)
        # La pestaña de la estación contiene el editor completo y ofrece
        # selección de notas, edición, guardado, zoom y transporte.
        self.workbench.tabs.setCurrentWidget(editor)
        editor.setFocus()

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
        # A project switch can replace preset values without changing
        # the number of entries. Counting alone leaves stale itemData
        # in Inicio and the current preset becomes None.
        changed=(self.midi_preset.count()!=src.count() or
                 any(self.midi_preset.itemData(i)!=src.itemData(i)
                     or self.midi_preset.itemText(i)!=src.itemText(i)
                     for i in range(src.count())))
        if changed:
            was=self.midi_preset.blockSignals(True)
            self.midi_preset.clear()
            for i in range(src.count()):
                self.midi_preset.addItem(src.itemText(i),src.itemData(i))
            self.midi_preset.blockSignals(was)
        # QComboBox.findData(tuple) is unreliable on PySide6 because
        # QVariant converts Python tuples to sequence variants. Compare
        # the normalized Python itemData objects, not QVariant identity.
        value=src.currentData()
        index=next((i for i in range(self.midi_preset.count())
                    if self.midi_preset.itemData(i)==value),-1)
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
        project=getattr(self.main,"project_dir",None)
        if project:
            from vocal_catalog import project_vocal_files
            path_list.extend(project_vocal_files(project))
        for p in work.midi_storage.items:
            path=Path(p)
            if path.is_file():path_list.append(path)
        for version in work.midi_storage.versions:
            path=Path(version["composite"])
            if path.is_file():path_list.append(path)
        # Recuperar todos los MIDI de este proyecto, incluidos los que se
        # convirtieron en sesiones previas, sin abrir la pestaña de MIDI.
        project=getattr(self.main,"project_dir",None)
        if project:
            from task_staging import inside
            base=Path(project).resolve()
            for name in ("audio_a_midi","piano_roll","resultados","temporales/midi"):
                folder=base/name
                if not folder.is_dir() or folder.is_symlink():continue
                for file in folder.rglob("*"):
                    if file.is_file() and not file.is_symlink() and file.suffix.lower() in MIDI and inside(file,base):
                        path_list.append(file)
        # El nuevo MIDI→audio sólo publica en temporales/resultados
        # hasta Guardar. Mostrarlo en Resultados sin confirmar el proyecto.
        project=getattr(self.main,"project_dir",None)
        if project:
            from task_staging import inside
            temp=Path(project).resolve()/"temporales"/"resultados"
            if temp.is_dir() and not temp.is_symlink():
                path_list.extend(p for p in temp.iterdir()
                    if p.is_file() and not p.is_symlink()
                    and p.suffix.lower() in AUDIO and inside(p,temp))
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
        selected_paths={str(path.resolve()) for path in self._selected_results()}
        was=self.files.blockSignals(True)
        self.files.setRowCount(len(paths))
        stem_list={str(p):self._stem_for(p) for p in self.workbench.separation_storage.items}
        from vocal_catalog import project_vocal_files
        stem_list.update({str(p):self._stem_for(p) for p in project_vocal_files(
            getattr(self.main,"project_dir",None))})
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
        # Conservar la selección múltiple por ruta, nunca por número de
        # fila: al convertir un MIDI nuevo pueden desplazarse las filas.
        from PySide6.QtCore import QItemSelectionModel
        selection=self.files.selectionModel()
        self.files.clearSelection()
        if selected_paths:
            for row,path in enumerate(paths):
                if str(path.resolve()) in selected_paths:
                    selection.select(self.files.model().index(row,0),
                        QItemSelectionModel.Select|QItemSelectionModel.Rows)
        elif old is None and paths:
            self.files.selectRow(0)
        results=getattr(self.main,"results_tab",None)
        if results is not None and hasattr(results,"refresh"):
            results.refresh(paths)
        if self.files.currentRow()>=0:
            self.file_selected()
        else:
            self._request_result_metadata(None)

    def _result_duration(self,path):
        # ffprobe es caro y durante la apertura el mismo archivo se dibuja
        # en varios módulos. Conservar el resultado mientras sus metadatos
        # físicos permanezcan idénticos; el reemplazo invalida la caché.
        try:
            st=path.stat()
            key=(str(path),st.st_dev,st.st_ino,st.st_size,
                 st.st_mtime_ns,st.st_ctime_ns)
        except (OSError,ValueError):return "—"
        cache=self._result_duration_cache
        if key in cache:return cache[key]
        result="—"
        if path.suffix.lower() in MIDI:
            try:
                import mido
                val=mido.MidiFile(path).length
                result=f"{int(val//60):02d}:{int(val%60):02d}"
            except (OSError,ValueError,EOFError):pass
        else:
            try:
                from audio_import import probe_audio
                info=probe_audio(path)
                val=float(info.get("duration",0))
                if val:result=f"{int(val//60):02d}:{int(val%60):02d}"
            except (OSError,ValueError,AttributeError,TypeError):pass
        # Una cota protege la aplicación de crecer indefinidamente.
        if len(cache)>1024:cache.clear()
        cache[key]=result
        return result

    def refresh(self,force=False):
        work=self.workbench
        self._loading=True
        self._sync_monitor()
        self._sync_separator()
        self._sync_drum_module()
        self._sync_vocal_module()
        self._sync_engine()
        # Some engine/control refreshes can restore the visible preset
        # index to the first placeholder. Synchronize last against the
        # actual converter state after all dependent controls.
        self._sync_preset()
        self._loading=False
        if self.quality.currentIndex()!=self.main.capture_rate.currentIndex():
            was=self.quality.blockSignals(True)
            self.quality.setCurrentIndex(self.main.capture_rate.currentIndex())
            self.quality.blockSignals(was)
        paths=self._gather_files()
        signature=tuple((str(p),p.stat().st_size) for p in paths)
        if force or signature!=self._known_state:
            self._sync_midi_stems(force=True)
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
                self._set_piano_active_name(None)
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
        compositor=getattr(self.main,"composer_tab",None)
        if compositor is not None and not compositor._loading_refresh:
            compositor.sync_project()

    def reset_project_view(self):
        """Pantalla de proyecto limpio, sin representaciones heredadas."""
        if self.player is not None:self.player.clear()
        self.selected_file=None
        self.selected_midi=None
        self._known_state=None
        self._mix_pending_changes.clear()
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

    def _sync_wave_playhead(self):
        """Seguir únicamente el archivo mostrado en Vista de audio."""
        player=self.player
        source=self.wave.source
        if player is None or not source or not player.current_file or player._duration_ms<=0:
            return
        # El origen se normaliza al cargarlo: evitar resolver la ruta en
        # disco 60 veces por segundo (dos stat/lstat por fotograma).
        if getattr(player,"_origin",None)!=source:
            return
        raw_position=player._position()
        active=(player._qt_active or player._play_process is not None)
        running=active and not player._paused
        now=time.monotonic()
        if not running or not getattr(player,"_native_qt",False):
            # FFplay ya usa un reloj monotónico en PreviewPlayer.
            display_pos=raw_position
            self._wave_ui_position=float(display_pos)
        elif self._wave_ui_source!=player.current_file or self._wave_ui_position is None:
            self._wave_ui_position=float(raw_position)
            display_pos=float(raw_position)
        else:
            elapsed=min(.1,max(0.,now-(self._wave_ui_time or now)))
            speed=float(player.speed.currentData() or 1.)
            extrapolated=self._wave_ui_position+elapsed*1000*speed
            correction=float(raw_position)-extrapolated
            if abs(correction)>250:
                # Un salto de reproducción siempre tiene prioridad.
                display_pos=float(raw_position)
            else:
                # Suavizar actualizaciones discretas de QMediaPlayer sin
                # cambiar la posición que realmente reproduce el audio.
                display_pos=extrapolated+max(-3.,min(3.,correction*.08))
            self._wave_ui_position=display_pos
        self._wave_ui_time=now
        self._wave_ui_source=player.current_file
        fraction=max(0.,min(1.,display_pos/player._duration_ms))
        if abs(self.wave.cursor-fraction)>1e-6:
            self.wave.set_cursor(fraction)
        moved=((player._qt_active or player._play_process is not None)
               and not player._paused and self.wave.follow_playhead(fraction))
        # La miniatura no necesita 60 repintados/s; limitarla a 20 Hz
        # descarga la GUI y deja la onda principal a 60 Hz.
        if moved:
            self.overview.selection_start=self.wave.view_start
        # Estado exacto siempre sincronizado; rasterizar miniatura solo
        # cuando toque su próximo fotograma (20 Hz).
        self.overview.cursor=fraction
        if now-self._wave_overview_last>=.05:
            self.overview.update()
            self._wave_overview_last=now

    def _tick(self):
        self.refresh()
        self._sync_player()
        self._sync_wave_playhead()
        sample=self._sync_result_vu()
        audible_file=Path(self.player.current_file) if (
            self.player and self.player.current_file and
            (self.player._play_process is not None or self.player._qt_active)
            and not self.player._paused) else None
        active_category=None
        if audible_file is not None:
            classified=self._stem_for(audible_file)
            from drum_module import PARTS
            if classified in PARTS:active_category="Batería"
            elif classified in self.mixer_rows and classified!="Otros":
                active_category=classified
            elif audible_file.suffix.lower() in MIDI and classified=="Piano":
                active_category="Piano"
            # Sin instrumento conocido no atribuir arbitrariamente su nivel
            # a un canal; el VU estéreo de Resultados sí lo mostrará.
        rms=max(sample[:2])
        db=20*math.log10(max(1e-8,rms))
        value=max(0.,min(1.,(db+60)/60)) if rms>0 else 0.
        for name,details in self.mixer_rows.items():
            details["meter"].set_level(value if active_category==name else 0.)

    def sync_capture_levels(self,left,right,peak_l,peak_r):
        self.level_meter.set_levels(peak_l,peak_r)
        peak=max(float(peak_l),float(peak_r))
        self._capture_peak_hold=max(self._capture_peak_hold,peak)
        if peak>=1.0:self._capture_clip_count+=1
        self.update_capture_diagnostics()
        if hasattr(self,"record_transport"):
            self.record_transport.set_levels(left,right,peak_l,peak_r)
