"""Representación de los demás VU a partir del ORIGINAL Monitor / Grabación.

Referencia protegida: studio_home.VerticalMeter, restaurado sin cambios
del respaldo anterior. Se conserva geometría y orientación de cada VU.
Los umbrales, 24 bloques, colores y conversión dBFS son los de ese widget.
"""
from __future__ import annotations

import math
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QFont, QPen
from PySide6.QtWidgets import QWidget, QProgressBar

DB_FLOOR = -60.0
BG = "#04121d"
OFF = "#19313c"
GREEN = "#40e985"
AMBER = "#d0e82e"
RED = "#ff4d50"
LABEL = "#9aaec3"
SCALE = (-60, -48, -36, -24, -12, -6, 0)
SEGMENTS = 24

def db_fraction(amplitude):
    try:
        value = float(amplitude)
    except (ValueError, TypeError):
        return 0.
    if not math.isfinite(value):
        return 0.
    db = 20 * math.log10(max(1e-8, value))
    return max(0., min(1., (db + 60.) / 60.))

def from_percent(percent):
    try:
        value = max(0., min(100., float(percent)))
    except (ValueError, TypeError):
        return 0.
    return 10 ** (((value / 100.) * 60. - 60.) / 20.) if value > 0 else 0.

class Ballistics:
    """La misma respuesta del Monitor original: lectura actual sin retardo.

    No suaviza, no inventa señal y no modifica el audio. Conserva por
    compatibilidad la información física RMS y pico si está disponible.
    """
    def __init__(self, channels=2):
        self.channels = channels
        self.raw_rms = [0.] * channels
        self.raw_peak = [0.] * channels
        self.shown = [0.] * channels
        self.held = [0.] * channels

    def feed(self, rms, peaks):
        for i in range(self.channels):
            def value(seq):
                try: v = float(seq[i])
                except (IndexError, TypeError, ValueError): return 0.
                return max(0., min(1.5, v)) if math.isfinite(v) else 0.
            level = value(rms)
            peak = value(peaks)
            self.raw_rms[i] = level
            self.raw_peak[i] = peak
            self.shown[i] = level
            self.held[i] = peak

def _colour(index, lit):
    if not lit:
        return QColor(OFF)
    return QColor(GREEN if index < 15 else AMBER if index < 21 else RED)

def draw_lane(p, x, y, width, height, rms, peak_held=0., show_scale=False):
    """Barra horizontal: 24 segmentos originales girados 90 grados."""
    w = max(1., float(width))
    h = max(2., float(height))
    fraction = db_fraction(rms)
    pitch = w / SEGMENTS
    p.setPen(Qt.NoPen)
    for i in range(SEGMENTS):
        lit = (i / SEGMENTS) < fraction
        p.setBrush(_colour(i, lit))
        xx = x + i * pitch
        p.drawRect(QRectF(xx, y, max(.7, pitch - min(2., pitch*.25)), h))

def draw_vertical_lane(p, x, y, width, height, rms, peak_held=0.):
    """Barra vertical: copia proporcional de los 24 pasos del Monitor."""
    h = max(1., float(height))
    w = max(2., float(width))
    fraction = db_fraction(rms)
    p.setPen(Qt.NoPen)
    for i in range(SEGMENTS):
        lit = (i / SEGMENTS) < fraction
        p.setBrush(_colour(i, lit))
        yy = y + (23 - i) * h / SEGMENTS
        p.drawRect(QRectF(x, yy, w, max(2., h / 26.)))

def draw_stereo(p, bounds, shown, held, names=("L","R"), scale=True):
    p.setRenderHint(QPainter.Antialiasing, False)
    x = float(bounds.x()); y0 = float(bounds.y())
    w = float(bounds.width()); h = float(bounds.height())
    channels = len(names)
    p.fillRect(bounds, QColor(BG))
    label_w = 24. if w >= 140 else 10.
    right = 22. if w >= 180 else 2.
    width = max(3., w - label_w - right - 2.)
    ticks = 14. if scale and h >= 45 else (9. if scale and h >= 31 else 0.)
    available = max(1., h - ticks - 2.)
    row = available / max(1, channels)
    band_h = max(2., min(11., row-2.))
    font = QFont("Sans", 7 if w < 130 else 9, QFont.DemiBold)
    p.setFont(font)
    p.setPen(QColor(LABEL))
    for i, name in enumerate(names):
        yy = y0 + ticks + i * row + (row - band_h)/2.
        if label_w >= 20 or w >= 70:
            p.drawText(QRectF(x, yy-1, label_w, band_h+2),
                       Qt.AlignCenter, str(name))
        draw_lane(p, x+label_w, yy, width, band_h, shown[i], held[i])
    if ticks:
        p.setFont(QFont("Sans", 6 if w < 180 else 8))
        p.setPen(QColor("#8394a8"))
        labels = SCALE if w >= 210 else (-60,-36,-12,0) if w >= 120 else (-60,0)
        for tick in labels:
            xx = x+label_w+(tick+60)/60.*width
            p.drawText(QRectF(xx-15, y0, 30, ticks),
                       Qt.AlignCenter, str(tick))

def draw_vertical(p, bounds, shown, held, names=("L","R"), scale=True):
    p.setRenderHint(QPainter.Antialiasing, False)
    x = float(bounds.x()); y = float(bounds.y())
    w = float(bounds.width()); h = float(bounds.height())
    count = len(names)
    p.fillRect(bounds, QColor(BG))
    compact = w < 46.
    first_x = x+1. if compact else x+6.
    available = w - (1. if compact else 35.)
    gap = 2. if compact else 5.
    band_w = max(2., (available-(count-1)*gap) / max(1,count))
    top = y+(3. if compact else 15.)
    length = max(2., h-(6. if compact else 26.))
    for i, name in enumerate(names):
        xx = first_x+i*(band_w+gap)
        draw_vertical_lane(p,xx,top,band_w,length,shown[i],held[i])
        if not compact:
            p.setPen(QColor(LABEL))
            p.setFont(QFont("Sans", 7))
            p.drawText(QRectF(xx,y,band_w,13),Qt.AlignCenter,str(name))
    if not compact and scale:
        p.setFont(QFont("Sans", 7))
        p.setPen(QColor("#8394a8"))
        for tick in (-60,-36,-18,0):
            yy = top+length-(tick+60)/60.*length
            p.drawText(QRectF(x+w-29.,yy-7,29,14),
                       Qt.AlignVCenter|Qt.AlignLeft,str(tick))

def draw_mono_horizontal(p, bounds, shown, held, caption="L", scale=True):
    draw_stereo(p, bounds, (shown,), (held,), (caption,), scale)

class UnifiedStereoMeter(QWidget):
    """Adaptador de posición/altura existente con el patrón Monitor original."""
    def __init__(self,parent=None,*,height=58,width=None,labels=("L","R")):
        super().__init__(parent)
        self.names=tuple(labels)
        self._ballistics=Ballistics(len(self.names))
        self.rms=[0.]*len(self.names)
        self.peaks=[0.]*len(self.names)
        self.held=[0.]*len(self.names)
        self.setMinimumHeight(height)
        if width is not None: self.setMinimumWidth(width)
        self.setToolTip("VU del Monitor / Grabación original · 24 bloques, "
                        "verde/amarillo/rojo · −60 a 0 dBFS.")
    def set_levels(self,l,r,lp,rp):
        self._ballistics.feed((l,r),(lp,rp))
        self.rms=list(self._ballistics.raw_rms)
        self.peaks=list(self._ballistics.raw_peak)
        self.held=list(self._ballistics.held)
        self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        draw_stereo(p,self.rect(),self._ballistics.shown,
                    self._ballistics.held,self.names,True)
        p.end()
    @staticmethod
    def norm(v): return db_fraction(v)

class UnifiedMonoMeter(QWidget):
    def __init__(self,parent=None,*,caption="L",height=30,width=None):
        super().__init__(parent)
        self.caption=caption
        self._ballistics=Ballistics(1)
        self.setMinimumHeight(height)
        if width is not None: self.setMinimumWidth(width)
    def set_level(self,value,peak=None):
        self._ballistics.feed((value,),(value if peak is None else peak,))
        self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        draw_mono_horizontal(p,self.rect(),self._ballistics.shown[0],
                             self._ballistics.held[0],self.caption,True)
        p.end()

class UnifiedPercentBar(QProgressBar):
    """Vista de 0–100 para transportes, sin modificar conexiones o sitio."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self._ballistics=Ballistics(1)
        self.setRange(0,100)
        self.setTextVisible(False)
        self.setToolTip("VU original Monitor / Grabación, −60 a 0 dBFS.")
    def setValue(self,value):
        v=int(max(0,min(100,value)))
        self._ballistics.feed((from_percent(v),),(from_percent(v),))
        super().setValue(v)
    def paintEvent(self,event):
        p=QPainter(self)
        draw_lane(p,1,1,max(1,self.width()-2),max(2,self.height()-2),
                  self._ballistics.shown[0])
        p.end()
