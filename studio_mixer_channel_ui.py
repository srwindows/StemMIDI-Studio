"""Inserts por canal, ventanas de plugins y máster PCM/spectrograma.
Solo se instancian desde la pestaña Mezclador, no la ventana flotante.
"""
import math
from collections import deque
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QTimer,QRectF,QPointF,QSignalBlocker,QEvent
from PySide6.QtGui import QPainter,QPen,QColor,QFont,QImage
from PySide6.QtWidgets import (
    QWidget,QFrame,QDialog,QPushButton,QLabel,QVBoxLayout,QHBoxLayout,
    QFormLayout,QSlider,QScrollArea,QMessageBox,QInputDialog,
    QSizePolicy,QDialogButtonBox,QMenu
)
from studio_mixer_bus_ui import PanBalanceDial


INSERT_BUTTON_STYLE = """
QPushButton {
    color: #e4fcff; font-size: 9px; font-weight: 850;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #5a94ab,stop:.14 #296580,stop:.68 #103d59,stop:1 #062035);
    border:1px solid #55a6bd; border-top:1px solid #a5f6fc;
    border-bottom:2px solid #071323; border-radius:4px;
    padding:1px 2px; min-height:18px;
}
QPushButton:hover {background:#1d779e;border-color:#9cfcff;}
QPushButton:pressed {background:#06445e;border-bottom:1px solid #03101a;}
QPushButton:disabled {color:#8fabb9;background:#142c3a;}
"""


class MasterLiveScope(QWidget):
    """Forma de onda master + espectrograma generado del PCM de salida."""
    def __init__(self,engine,parent=None):
        super().__init__(parent)
        self.engine=engine
        self._pcm=np.zeros((1024,2),np.float32)
        self._columns=deque(maxlen=128)
        self._seen=0
        self.setObjectName('mixerTabMasterLiveScope')
        self.setMinimumHeight(65)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setToolTip("MASTER REAL: onda L/R tras buses, efectos y fader master; FFT 48 kHz")

    def refresh(self):
        recent=list(self.engine.master_scope)
        if recent:
            self._pcm=np.concatenate(recent,axis=0)[-8192:].copy()
            if len(self._pcm)>=256:
                mono=np.mean(self._pcm[-2048:],axis=1)
                n=min(2048,len(mono))
                data=np.zeros(2048,np.float32)
                data[-n:]=mono[-n:]
                data*=np.hanning(len(data))
                fft=np.abs(np.fft.rfft(data))
                frequencies=np.fft.rfftfreq(len(data),1/48000)
                mids=np.geomspace(55,20000,65)
                bins=np.searchsorted(frequencies,mids)
                levels=[]
                for i in range(64):
                    left=min(len(fft)-1,bins[i])
                    right=min(len(fft),max(left+1,bins[i+1]))
                    levels.append(float(fft[left:right].max(initial=0)))
                normalized=np.clip((20*np.log10(np.array(levels)+1e-8)+53)/62,0,1)
                self._columns.append(normalized)
            self._seen+=1
        else:
            self._pcm=np.zeros((1024,2),np.float32)
            self._columns.append(np.zeros(64,np.float32))
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing,False)
            w,h=self.width(),self.height()
            p.fillRect(self.rect(),QColor('#061625'))
            p.setPen(QColor('#9cdef2'))
            p.setFont(QFont('Sans',7,QFont.Bold))
            p.drawText(6,10,'MASTER  ·  ONDA L/R  EN TIEMPO REAL')
            wave_top=14
            wave_height=max(18,int(h*.42)-10)
            p.setPen(QPen(QColor('#1a344a'),.7))
            for m in range(1,4):
                y=wave_top+m*wave_height/4
                p.drawLine(0,int(y),w,int(y))
            if self._pcm.size:
                for channel,color,center in (
                    (0,'#35eab9',wave_top+wave_height*.28),
                    (1,'#efb55b',wave_top+wave_height*.75)):
                    arr=self._pcm[:,channel]
                    max_columns=max(1,w)
                    if arr.size>max_columns:
                        cuts=np.linspace(0,len(arr),max_columns+1,dtype=int)
                        highs=np.array([np.max(np.abs(arr[cuts[i]:cuts[i+1]]))
                                        if cuts[i+1]>cuts[i] else 0
                                        for i in range(max_columns)])
                    else:
                        highs=np.abs(arr)
                    p.setPen(QPen(QColor(color),1.))
                    for x,magnitude in enumerate(highs):
                        dy=min(wave_height*.2,float(magnitude)*wave_height*.19)
                        cx=x*w/max(1,len(highs))
                        p.drawLine(int(cx),int(center-dy),int(cx),int(center+dy))
            spec_y=wave_top+wave_height+11
            spec_height=max(4,h-spec_y-1)
            p.setPen(QColor('#9cdef2'))
            p.drawText(6,spec_y-2,'ESPECTROGRAMA  ·  55 Hz — 20 kHz')
            if self._columns and w>0 and spec_height>0:
                arr=np.array(self._columns,dtype=np.float32).T
                if arr.shape[1]<128:
                    pad=np.zeros((64,128-arr.shape[1]),np.float32)
                    arr=np.hstack((pad,arr))
                arr=np.flipud(arr)
                # Mapa continuo oscuro → cian → verde → amarillo.
                strength=np.clip(arr,0,1)
                rr=(255*np.clip((strength-.57)*2.1,0,1)).astype(np.uint8)
                gg=(210*np.clip((strength-.12)*1.5,0,1)).astype(np.uint8)
                bb=(25+165*np.clip((strength-.03)*1.6,0,1)-
                    120*np.clip((strength-.62)*2.5,0,1)).clip(0,255).astype(np.uint8)
                rgb=np.ascontiguousarray(np.stack((rr,gg,bb),axis=-1))
                picture=QImage(rgb.data,rgb.shape[1],rgb.shape[0],
                    rgb.strides[0],QImage.Format_RGB888).copy()
                p.drawImage(QRectF(0,spec_y,w,spec_height),picture)
        finally:
            p.end()



class ParallelMixerDashboard(QWidget):
    """Vistas PCM sincronizadas: original + bus, EQ16 editable y espectrograma."""
    def __init__(self,engine,on_eq_change=None,parent=None):
        super().__init__(parent)
        self.engine=engine
        self.on_eq_change=on_eq_change
        self.channel='Voces'
        self.bus_index=1
        self._dry=np.zeros((1024,2),np.float32)
        self._bus=np.zeros((1024,2),np.float32)
        self._columns=deque(maxlen=136)
        self._bands=np.zeros(16,np.float32)
        self._drag_eq=False
        self.setMinimumHeight(218)
        self.setObjectName('parallelMixerAudioDashboard')
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setToolTip('Original directo a MASTER · BUS procesado y retorno FX · EQ16 interactivo')

    def _snapshot(self,buf):
        recent=list(buf) if buf else []
        if not recent:return np.zeros((1024,2),np.float32)
        return np.concatenate(recent,axis=0)[-8192:].copy()

    def refresh(self):
        from collections import deque as _dq
        self._dry=self._snapshot(self.engine.source_scope.get(self.channel))
        self._bus=self._snapshot(self.engine.bus_scope.get(self.bus_index))
        frames=self._bus
        # Espectro real del bus activo: 16 bandas logarítmicas, 20 Hz–20 kHz.
        data=np.mean(frames[-4096:],axis=1)
        work=np.zeros(4096,np.float32)
        work[-len(data):]=data
        win=np.hanning(4096)
        spectrum=np.abs(np.fft.rfft(work*win))/max(1,win.sum()/2)
        freqs=np.fft.rfftfreq(4096,1./48000)
        edges=np.geomspace(20.,20000.,17)
        b=[]
        for k in range(16):
            lo=np.searchsorted(freqs,edges[k])
            hi=max(lo+1,np.searchsorted(freqs,edges[k+1]))
            b.append(float(spectrum[lo:hi].max(initial=0)))
        db=20*np.log10(np.array(b)+1e-8)
        self._bands=np.clip((db+72.)/72.,0,1).astype(np.float32)
        # Cada columna es FFT real. No guardar datos extraños si está parado.
        cols=[]
        bins=np.searchsorted(freqs,np.geomspace(20.,20000.,65))
        for k in range(64):
            lo=min(len(spectrum)-1,bins[k])
            hi=min(len(spectrum),max(lo+1,bins[k+1]))
            cols.append(float(spectrum[lo:hi].max(initial=0)))
        col=np.clip((20*np.log10(np.array(cols)+1e-8)+76)/76,0,1)
        self._columns.append(col.astype(np.float32))
        self.update()

    def _geometry(self):
        w,h=self.width(),self.height()
        cutoff=int(w*.70)
        space=4
        left=QRectF(0,0,max(0,cutoff-space),h)
        right=QRectF(cutoff,0,max(0,w-cutoff),h)
        return left,right

    def _draw_wave(self,p,rect,a,title,color):
        p.fillRect(rect,QColor('#081f32'))
        p.setPen(QColor('#a7dfeb'))
        p.setFont(QFont('Sans',8,QFont.Bold))
        p.drawText(QRectF(rect.x()+5,rect.y()+3,rect.width()-9,15),
                   Qt.AlignLeft|Qt.AlignVCenter,title)
        top=rect.y()+20; plot=max(12,rect.height()-23)
        p.setPen(QPen(QColor('#203c4d'),1))
        for j in (1,2,3):
            y=int(top+plot*j/4)
            p.drawLine(int(rect.x()+3),y,int(rect.right()-3),y)
        length=int(rect.width()-8)
        if length<2 or a.size==0:return
        # Reducción vectorizada: evita cientos de llamadas Python/numpy
        # por cada onda y libera CPU/GIL para el callback de audio.
        if length<=len(a):
            starts=np.linspace(0,len(a)-1,length,dtype=np.intp)
            amp=np.maximum.reduceat(np.abs(a),starts,axis=0).T
        else:
            indices=np.linspace(0,len(a)-1,length,dtype=np.intp)
            amp=np.abs(a[indices]).T
        for channel,c in ((0,color),(1,'#eeb860')):
            p.setPen(QPen(QColor(c),1))
            cy=top+plot*(.27 if channel==0 else .75)
            scale=plot*.22
            for k,value in enumerate(amp[channel]):
                dy=max(0,int(min(scale,value*scale)))
                x=int(rect.x()+4+k)
                p.drawLine(x,int(cy-dy),x,int(cy+dy))
        p.setPen(QPen(QColor('#2c6980'),1))
        p.drawRect(rect.adjusted(0,0,-1,-1))

    def _draw_spectrum(self,p,rect):
        p.fillRect(rect,QColor('#0b2033'))
        p.setFont(QFont('Sans',8,QFont.Bold))
        p.setPen(QColor('#b5f4ff'))
        p.drawText(QRectF(rect.x()+6,rect.y()+2,rect.width()-10,17),
                   Qt.AlignLeft|Qt.AlignVCenter,
                   f'EQ 16 BANDAS  ·  BUS {self.bus_index:02d}')
        x0=rect.x()+9; span=max(10,rect.width()-18)
        top=rect.y()+23; bottom=rect.bottom()-20
        height=max(8,bottom-top)
        gains=self.engine.eq16[self.bus_index]
        for j in range(16):
            x=x0+(j+.5)*span/16
            magnitude=self._bands[j]
            bh=max(1,magnitude*height)
            color=QColor('#4ff0cb' if magnitude<.7 else '#f1bd68')
            p.fillRect(QRectF(x-span/42,bottom-bh,max(2,span/21),bh),color)
            # Marcador blanco editable: posición +/-12 dB en 16 filtros reales.
            eq_y=top+(12.-gains[j])/24.*height
            p.setPen(QPen(QColor('#e6f9ff'),1))
            p.drawLine(int(x-span/44),int(eq_y),int(x+span/44),int(eq_y))
        p.setPen(QColor('#9cc3d4'))
        p.setFont(QFont('Sans',7))
        p.drawText(QRectF(x0,rect.bottom()-17,40,14),'20 Hz')
        p.drawText(QRectF(rect.right()-56,rect.bottom()-17,54,14),
                   Qt.AlignRight,'20 kHz')
        p.drawRect(rect.adjusted(0,0,-1,-1))

    def _draw_spectrogram(self,p,rect):
        p.fillRect(rect,QColor('#061825'))
        p.setPen(QColor('#a4e9f6'))
        p.setFont(QFont('Sans',8,QFont.Bold))
        p.drawText(QRectF(rect.x()+6,rect.y()+2,rect.width()-10,16),
                   Qt.AlignLeft,'ESPECTROGRAMA · BUS')
        if self._columns:
            arr=np.array(self._columns,dtype=np.float32).T
            if arr.shape[1]<136:
                arr=np.pad(arr,((0,0),(136-arr.shape[1],0)))
            z=np.clip(np.flipud(arr),0,1)
            red=(255*np.clip((z-.60)*2.2,0,1)).astype(np.uint8)
            green=(214*np.clip((z-.07)*1.9,0,1)).astype(np.uint8)
            blue=(15+165*np.clip((z-.02)*1.5,0,1)-
                  115*np.clip((z-.7)*2.5,0,1)).clip(0,255).astype(np.uint8)
            rgb=np.ascontiguousarray(np.stack((red,green,blue),axis=-1))
            image=QImage(rgb.data,rgb.shape[1],rgb.shape[0],
                         rgb.strides[0],QImage.Format_RGB888).copy()
            p.drawImage(rect.adjusted(2,19,-2,-2),image)
        p.setPen(QPen(QColor('#2c6980'),1))
        p.drawRect(rect.adjusted(0,0,-1,-1))

    def paintEvent(self,event):
        p=QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing,False)
            p.fillRect(self.rect(),QColor('#051321'))
            left,right=self._geometry()
            upper=QRectF(left.x(),left.y(),left.width(),
                         max(1,left.height()*.5-2))
            lower=QRectF(left.x(),upper.bottom()+4,left.width(),
                         max(1,left.height()-upper.height()-4))
            self._draw_wave(p,upper,self._dry,
                f'ORIGINAL · {self.channel.upper()} · DIRECTO AL MASTER','#45ebc6')
            self._draw_wave(p,lower,self._bus,
                f'BUS {self.bus_index:02d} · SEÑAL PROCESADA · FX','#48ccfa')
            right_top=QRectF(right.x(),right.y(),right.width(),
                             max(1,right.height()*.48-2))
            right_lower=QRectF(right.x(),right_top.bottom()+4,right.width(),
                               max(1,right.height()-right_top.height()-4))
            self._draw_spectrum(p,right_top)
            self._draw_spectrogram(p,right_lower)
        finally:
            p.end()

    def _edit_gain(self,event):
        left,right=self._geometry()
        point=event.position()
        top=right.y()+23
        bottom=right.y()+right.height()*.48-22
        if not (right.left()+8<=point.x()<=right.right()-8 and
                top<=point.y()<=bottom):
            return False
        band=int((point.x()-right.x()-9)/max(1,right.width()-18)*16)
        band=max(0,min(15,band))
        gain=12.-24*(point.y()-top)/max(1,bottom-top)
        if callable(self.on_eq_change):
            self.on_eq_change(band,max(-12.,min(12.,gain)))
        hz=self.engine.EQ16_HZ[band]
        self.setToolTip(f'BUS {self.bus_index:02d}: EQ {hz:.0f} Hz = {gain:+.1f} dB')
        self.update()
        return True

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self._drag_eq=self._edit_gain(event)
            if self._drag_eq:event.accept();return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._drag_eq:
            self._edit_gain(event)
            event.accept();return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        self._drag_eq=False
        super().mouseReleaseEvent(event)

class ChannelPluginWindow(QDialog):
    """Editor flotante redimensionable; minimizar oculta al botón de la tira."""
    def __init__(self,controller,channel,uid,parent=None):
        super().__init__(parent)
        self.controller=controller
        self.channel=str(channel)
        self.uid=uid
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint |
                            Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self.resize(430,430)
        self.setMinimumSize(315,240)
        self.setAttribute(Qt.WA_DeleteOnClose,False)
        self.setStyleSheet("""
            QDialog{background:#102739;color:#e8f9ff;}
            QLabel{color:#ceeefa;}
            QSlider::groove:horizontal{height:5px;background:#061b2b;}
            QSlider::sub-page:horizontal{background:#39e1d2;}
            QPushButton{background:#1b4a65;border:1px solid #6fb6c8;
               padding:5px;color:#f2ffff;border-radius:5px;}
        """)
        box=QVBoxLayout(self)
        box.setContentsMargins(12,9,12,9)
        slot=self.controller.bus_fx.channel_slot(self.channel,self.uid)
        if slot is not None and slot.name=="Channel EQ":
            self.resize(600,620)
        elif slot is not None and slot.name=="Reverb":
            self.resize(480,465)
        self.setWindowTitle(f"{slot.name if slot else 'Plugin'} · {self.channel}")
        label=QLabel(f"INSERT · {self.channel} · {slot.name if slot else ''}")
        label.setStyleSheet("font-size:13px;font-weight:bold;")
        box.addWidget(label)
        scroll=QScrollArea(self)
        scroll.setWidgetResizable(True)
        content=QWidget()
        form=QFormLayout(content)
        form.setSpacing(8)
        plugin=slot.plugin if slot else None
        if slot is not None and slot.name=="Channel EQ":
            from channel_eq_controls import ChannelEQControls
            form.addRow(ChannelEQControls(plugin,content))
        elif slot is not None and slot.name=="Sample Delay":
            from sample_delay_controls import SampleDelayControls
            form.addRow(SampleDelayControls(plugin,content))
        elif slot is not None and slot.name=="Reverb":
            from stemmidi_reverb_controls import ReverbControls
            form.addRow(ReverbControls(plugin,content))
        elif plugin is not None and hasattr(plugin,"parameters"):
            for key,parameter in plugin.parameters.items():
                row=QHBoxLayout()
                slide=QSlider(Qt.Horizontal,content)
                slide.setRange(0,1000)
                slide.setValue(round(float(parameter.raw_value)*1000))
                value=QLabel(f"{parameter.raw_value:.3f}",content)
                def change(raw,par=parameter,readout=value):
                    try:
                        par.raw_value=raw/1000.
                        readout.setText(f"{par.raw_value:.3f}")
                    except (ValueError,RuntimeError):
                        pass
                slide.valueChanged.connect(change)
                row.addWidget(slide,1);row.addWidget(value)
                form.addRow(key.replace("_"," ").title(),row)
        elif plugin is not None:
            ranges={
                "Reverb":{"room_size":(0,1),"damping":(0,1),
                          "wet_level":(0,1),"dry_level":(0,1),"width":(0,1)},
                "Delay":{"delay_seconds":(.01,1.4),"feedback":(0,.94),
                         "mix":(0,1)},
                "Compresor":{"threshold_db":(-60,0),"ratio":(1,20),
                             "attack_ms":(.1,100),"release_ms":(10,1000)}
            }.get(slot.name,{})
            for key,(minimum,maximum) in ranges.items():
                if not hasattr(plugin,key):continue
                current=float(getattr(plugin,key))
                row=QHBoxLayout()
                slide=QSlider(Qt.Horizontal,content)
                slide.setRange(0,1000)
                slide.setValue(round(1000*(current-minimum)/(maximum-minimum)))
                value=QLabel(f"{current:.2f}",content)
                def change(raw,attr=key,a=minimum,b=maximum,readout=value):
                    amount=a+(b-a)*raw/1000.
                    try:
                        setattr(plugin,attr,amount)
                        readout.setText(f"{amount:.2f}")
                    except (ValueError,RuntimeError):pass
                slide.valueChanged.connect(change)
                row.addWidget(slide,1);row.addWidget(value)
                form.addRow(key.replace("_"," ").title(),row)
        scroll.setWidget(content)
        box.addWidget(scroll,1)
        collapse=QPushButton("▁  Minimizar al botón del canal",self)
        collapse.clicked.connect(self.hide)
        box.addWidget(collapse)

    def changeEvent(self,event):
        if event.type()==QEvent.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0,self._collapse)
        super().changeEvent(event)

    def _collapse(self):
        self.showNormal()
        self.hide()

    def closeEvent(self,event):
        self.hide()
        event.ignore()


