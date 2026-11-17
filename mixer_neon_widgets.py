"""Controles pintados con Qt para la consola de neón.

El dibujo no es una captura: faders y seek son QSlider editables y cada VU
recibe muestras medidas separadas L/R del mezclador de baja latencia.
"""
from __future__ import annotations
from math import log10
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSlider, QWidget
from studio_vu_unified import Ballistics


class NeonFader(QSlider):
    """Tirador metálico tridimensional con canal turquesa y escala frontal."""
    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.setObjectName("floating3DFader")
        # Se conserva el rango 0-150 del motor; 100 es el nivel normal.
        self.setRange(0, 150)
        self.setSingleStep(1)
        self.setPageStep(10)
        self.setTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(58, 115)
        self.setToolTip("Nivel del canal · 0–100 % normal, hasta 150 % de ganancia")

    def _travel(self):
        return (19., max(51., float(self.height()-20)))

    def _y_from_value(self, value):
        top, bottom = self._travel()
        at100 = top + 13
        if value <= 100:
            return bottom-(bottom-at100)*max(0., value)/100.
        return at100-(at100-top)*min(50., value-100)/50.

    def _y(self):
        return self._y_from_value(self.value())

    def _set_from_y(self, y):
        top, bottom = self._travel()
        at100 = top+13.
        if y >= at100:
            value=100.*(bottom-float(y))/max(1.,bottom-at100)
        else:
            value=100.+50.*(at100-float(y))/max(1.,at100-top)
        self.setValue(round(max(self.minimum(), min(self.maximum(), value))))

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self._set_from_y(event.position().y())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._set_from_y(event.position().y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w,h=float(self.width()),float(self.height())
        top,bottom=self._travel()
        cx=min(23.,max(18.,w*.32))
        y=self._y()
        # Fondo y carril con cuatro bordes para simular profundidad.
        p.setPen(QPen(QColor("#020b16"),2))
        p.setBrush(QColor("#020d1b"))
        p.drawRoundedRect(QRectF(cx-8,top-10,16,bottom-top+19),6,6)
        rail=QLinearGradient(cx-6,0,cx+6,0)
        for at,color in ((0,"#0b344d"),(.19,"#03101e"),(.40,"#0a6885"),
                         (.65,"#08344e"),(1,"#02111d")):
            rail.setColorAt(at,QColor(color))
        p.setPen(QPen(QColor("#498eaa"),.8))
        p.setBrush(rail)
        p.drawRoundedRect(QRectF(cx-5,top-7,10,bottom-top+14),4,4)
        # LED turquesa sobre el tramo activo.
        if y < bottom:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(33,247,231,44))
            p.drawRoundedRect(QRectF(cx-6,y,12,bottom-y+2),5,5)
            light=QLinearGradient(cx-3,0,cx+3,0)
            light.setColorAt(0,QColor("#00a8aa"))
            light.setColorAt(.5,QColor("#8ffff5"))
            light.setColorAt(1,QColor("#0c86b5"))
            p.setBrush(light)
            p.drawRoundedRect(QRectF(cx-3,y,6,bottom-y),3,3)
        # Escala NORMAL de la foto, sin esconder el refuerzo 100-150.
        p.setFont(QFont("Arial",8,QFont.DemiBold))
        for amount in (100,75,50,25,0):
            yy=self._y_from_value(amount)
            p.setPen(QPen(QColor("#6fb8ca"),.9))
            p.drawLine(QPointF(cx+11,yy),QPointF(cx+16,yy))
            p.setPen(QColor("#f3fbff") if amount in (0,100) else QColor("#afdae3"))
            p.drawText(QRectF(cx+17,yy-8,max(17.,w-cx-18),16),
                       Qt.AlignVCenter|Qt.AlignLeft,str(amount))
        # Tirador ancho: brillo, sombra, biseles y hendidura.
        width=27.; height=18.
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0,0,0,145))
        p.drawRoundedRect(QRectF(cx-width/2+2,y-height/2+4,width,height),4,4)
        metal=QLinearGradient(cx,y-height/2,cx,y+height/2)
        for at,color in ((0,"#ffffff"),(.10,"#c4f0f7"),(.22,"#849eae"),
                         (.33,"#4a6471"),(.47,"#e9fbff"),(.65,"#9fb6be"),
                         (.83,"#506575"),(1,"#142937")):
            metal.setColorAt(at,QColor(color))
        p.setPen(QPen(QColor("#d2faff"),1.))
        p.setBrush(metal)
        p.drawRoundedRect(QRectF(cx-width/2,y-height/2,width,height),4,4)
        p.setPen(QPen(QColor("#325568"),1.6))
        p.drawLine(QPointF(cx-12,y+.8),QPointF(cx+12,y+.8))
        p.setPen(QPen(QColor("#f6ffff"),.7))
        p.drawLine(QPointF(cx-12,y-2),QPointF(cx+12,y-2))
        if not self.isEnabled():
            p.fillRect(self.rect(),QColor(5,13,24,64))
        p.end()


class NeonStereoVU(QWidget):
    """Dos lecturas L y R independientes con escala -48...0 dBFS."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.ballistics=Ballistics(2)
        self.setMinimumSize(48,95)
        self.setToolTip("Vúmetro estéreo L/R real · 0, −6, −12, −24, −36 y −48 dBFS")

    def set_peaks(self,left,right):
        pair=(max(0.,float(left)),max(0.,float(right)))
        self.ballistics.feed(pair,pair)
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing,True)
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#071a30"))
        p.drawRoundedRect(rect,4,4)
        # Usar todo el ancho: 2 columnas L/R + escala, sin zona negra vacía.
        left=rect.left()+4.
        gap=2.
        bar_w=11.
        top=rect.top()+15.
        length=max(48.,rect.height()-34.)
        step=length/24.
        p.setFont(QFont("Arial",7,QFont.DemiBold))
        for side,name in enumerate(("L","R")):
            x=left+side*(bar_w+gap)
            p.setPen(QColor("#bce9f5"))
            p.drawText(QRectF(x-2,rect.top()+1.,bar_w+4,13),Qt.AlignCenter,name)
            db=20.*log10(max(1e-12,self.ballistics.shown[side]))
            level=max(0.,min(1.,(db+48.)/48.))
            for i in range(24):
                lit=(i+.5)/24. <= level
                if i>=21: bright="#ff4545"; dim="#40222a"
                elif i>=17: bright="#ffc928"; dim="#453a22"
                else: bright="#26fb53"; dim="#133527"
                y=top+(23-i)*step
                rr=QRectF(x,y,bar_w,max(2.,step-1.1))
                p.setPen(Qt.NoPen)
                if lit:
                    glow=QLinearGradient(x,y,x+bar_w,y)
                    glow.setColorAt(0,QColor(bright).darker(165))
                    glow.setColorAt(.48,QColor(bright))
                    glow.setColorAt(1,QColor(bright).lighter(120))
                    p.setBrush(glow)
                else:
                    p.setBrush(QColor(dim))
                p.drawRoundedRect(rr,.75,.75)
        # Escala única a la derecha, referida a cada una de las columnas.
        scale_x=left+2*bar_w+gap+2
        p.setFont(QFont("Arial",7,QFont.DemiBold))
        for db in (0,-6,-12,-24,-36,-48):
            yy=top+(-db/48.)*length
            p.setPen(QPen(QColor("#5d8999"),.8))
            p.drawLine(QPointF(scale_x-3,yy),QPointF(scale_x,yy))
            p.setPen(QColor("#d2e9f1"))
            p.drawText(QRectF(scale_x+1,yy-6,max(14.,rect.right()-scale_x-2),12),
                       Qt.AlignVCenter|Qt.AlignLeft,str(db))
        p.end()


class NeonSeekSlider(QSlider):
    """Timeline de audio con pista cian y esfera metálica; señal seek real."""
    def __init__(self,parent=None):
        super().__init__(Qt.Horizontal,parent)
        self.setMinimumHeight(36)
        self.setToolTip("Posición de reproducción")

    def _geometry(self):
        left,right=16.,max(17.,float(self.width())-16.)
        val=(self.sliderPosition()-self.minimum())/max(1.,self.maximum()-self.minimum())
        return left,right,left+(right-left)*val

    def _set_from_x(self,x):
        left,right,_=self._geometry()
        fraction=max(0.,min(1.,(float(x)-left)/max(1.,right-left)))
        self.setSliderPosition(round(self.minimum()+fraction*(self.maximum()-self.minimum())))

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.isEnabled():
            self.setSliderDown(True)
            self._set_from_x(event.position().x())
            event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton and self.isSliderDown():
            self._set_from_x(event.position().x())
            event.accept()
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.isSliderDown():
            self._set_from_x(event.position().x())
            self.setSliderDown(False)
            event.accept()
        else:super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        left,right,x=self._geometry()
        mid=self.height()/2.
        p.setPen(QPen(QColor("#337998"),1))
        p.setBrush(QColor("#03172b"))
        p.drawRoundedRect(QRectF(left,mid-5,right-left,10),5,5)
        if x>left:
            fill=QLinearGradient(left,mid-3,x,mid+3)
            fill.setColorAt(0,QColor("#08a6bf"))
            fill.setColorAt(.6,QColor("#6ffffc"))
            fill.setColorAt(1,QColor("#16b4d6"))
            p.setPen(Qt.NoPen);p.setBrush(fill)
            p.drawRoundedRect(QRectF(left,mid-3,x-left,6),3,3)
        p.setPen(QPen(QColor("#061322"),2))
        p.setBrush(QColor(0,0,0,145))
        p.drawEllipse(QRectF(x-11,mid-9,23,23))
        knob=QLinearGradient(x-11,mid-11,x+11,mid+11)
        for at,color in ((0,"#ffffff"),(.28,"#deffff"),(.48,"#8fb9c7"),
                         (.73,"#5b7989"),(1,"#e4f9ff")):
            knob.setColorAt(at,QColor(color))
        p.setPen(QPen(QColor("#b1ecf9"),1))
        p.setBrush(knob)
        p.drawEllipse(QRectF(x-11,mid-11,22,22))
        p.end()
