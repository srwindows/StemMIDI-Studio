"""Instrumentos visuales de audio, dibujados con Qt (sin dependencias externas)."""
from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class StereoMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(58)
        self.setMaximumHeight(72)
        self.rms = [0., 0.]
        self.peaks = [0., 0.]
        self.held = [0., 0.]

    def set_levels(self, l, r, lp, rp):
        self.rms = [l, r]
        self.peaks = [lp, rp]
        self.held = [max(lp, self.held[0] * .993), max(rp, self.held[1] * .993)]
        self.update()

    @staticmethod
    def norm(v):
        return max(0., min(1., (20 * math.log10(max(v, 1e-8)) + 60) / 60))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        left, right = 30., self.width() - 24.
        width = max(80., right-left)
        for i, ch in enumerate(("L", "R")):
            y = 15 + i * 23
            p.setPen(QColor("#9aaec3"))
            p.setFont(QFont("Sans", 10, QFont.DemiBold))
            p.drawText(QRectF(0, y, 22, 15), Qt.AlignVCenter, ch)
            count = max(10, int(width / 12))
            pitch = width / count
            level = self.norm(self.rms[i])
            for n in range(count):
                x = left + n * pitch
                q = (n + 1) / count
                bg = QColor("#1c2936")
                active = QColor("#2dc8a8") if q < .72 else (QColor("#f3ba56") if q < .91 else QColor("#f36b69"))
                p.setPen(Qt.NoPen)
                p.setBrush(active if q <= level else bg)
                p.drawRoundedRect(QRectF(x, y, max(2., pitch - 2.), 11), 2, 2)
            pkx = left + self.norm(self.held[i]) * width
            p.setPen(QPen(QColor("#edf8ff"), 2))
            p.drawLine(int(pkx), y-2, int(pkx), y+13)
        p.setFont(QFont("Sans", 8))
        p.setPen(QColor("#8394a8"))
        for db in (-60, -48, -36, -24, -12, -6, 0):
            x = left + (db+60)/60 * width
            rect = QRectF(x-15, 0, 30, 13)
            p.drawText(rect, Qt.AlignHCenter, str(db))


class Spectrum(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.bands = [0.0] * 48

    def set_bands(self, data):
        if not data:
            return
        self.bands = (list(data) + [0.] * 48)[:48]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = QRectF(8, 12, max(1, self.width()-16), max(1, self.height()-35))
        p.setPen(QPen(QColor("#26364a"), 1))
        for level in (0.25, 0.5, 0.75, 1.0):
            y = area.bottom() - level*area.height()
            p.drawLine(int(area.left()), int(y), int(area.right()), int(y))
        n = len(self.bands)
        cell = area.width() / n
        for i, level in enumerate(self.bands):
            height = max(2, level * area.height())
            x = area.left() + i * cell
            gradient = QLinearGradient(0, area.bottom(), 0, area.bottom()-height)
            gradient.setColorAt(0, QColor("#207ca0"))
            gradient.setColorAt(0.6, QColor("#38b6c2"))
            gradient.setColorAt(1, QColor("#67ddbc"))
            p.setBrush(gradient)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x + 1.2, area.bottom()-height, max(1., cell-2.4), height), 2, 2)
        p.setFont(QFont("Sans", 9))
        p.setPen(QColor("#8195aa"))
        for x, label in ((0.02, "40 Hz"), (0.31, "250 Hz"), (0.59, "1 kHz"),
                         (0.81, "5 kHz"), (0.98, "16 kHz")):
            xx = area.left() + x * area.width()
            p.drawText(QRectF(xx-26, area.bottom()+5, 52, 16), Qt.AlignHCenter, label)


class Oscilloscope(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(122)
        self.wave = [0.] * 205
        self.history = deque(maxlen=9)

    def set_wave(self, data):
        self.history.append(list(data))
        self.wave = list(data)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        ycenter = h/2
        p.setPen(QPen(QColor("#26384d"), 1))
        for f in (.2,.35,.5,.65,.8):
            y = int(f*h)
            p.drawLine(8, y, self.width()-8, y)
        if len(self.wave) < 2:
            return
        p.setPen(QPen(QColor("#64e0d0"), 1.7))
        path = QPainterPath()
        span = max(1, self.width()-18)
        for i, sample in enumerate(self.wave):
            xx = 9 + i * span / max(1, len(self.wave)-1)
            yy = ycenter - max(-1., min(1., sample)) * (h*.44)
            if i == 0:
                path.moveTo(xx, yy)
            else:
                path.lineTo(xx, yy)
        p.drawPath(path)
