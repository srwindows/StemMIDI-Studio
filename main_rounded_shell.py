"""Carcasa principal: misma curvatura y borde cian que floatingGlass.

No encapsula otro QWidget: conserva la jerarquía de QMainWindow y el
QVBoxLayout que utiliza el transporte MIDI persistente.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QColor, QBrush, QPainter, QPainterPath, QPen, QLinearGradient, QRegion,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout


class RoundedMainShell(QWidget):
    RADIUS = 14.0
    INSET = 11

    def __init__(self, main):
        super().__init__(main)
        self.main_window = main
        self.setObjectName("studioShell")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._is_maximized = False
        # La estructura original se conserva: cabecera, tabs, transporte.
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 18, 18, 18)
        self._layout.setSpacing(0)

    def sync_window_state(self):
        maximized = self.main_window.isMaximized() or self.main_window.isFullScreen()
        if maximized != self._is_maximized:
            self._is_maximized = maximized
            self._layout.setContentsMargins(
                0 if maximized else 18, 0 if maximized else 18,
                0 if maximized else 18, 0 if maximized else 18)
        self._update_mask()
        self.update()

    def _bounds(self):
        inset = 0 if self._is_maximized else self.INSET
        return QRectF(self.rect()).adjusted(
            inset + 1, inset + 1, -inset - 1, -inset - 1)

    def _update_mask(self):
        if self.width() < 40 or self.height() < 40:
            return
        if self._is_maximized:
            self.clearMask()
        else:
            # Máscara del PRECERCO exterior, no del borde cian interior.
            # Antes se recortaban los 11px exteriores, haciendo invisible
            # la separación negra característica de los módulos flotantes.
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2),
                                self.RADIUS + 6, self.RADIUS + 6)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_mask()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bounds = self._bounds()
        radius = 0 if self._is_maximized else self.RADIUS
        if not self._is_maximized:
            # Orden exacto, de FUERA hacia DENTRO:
            # transparencia -> línea CIAN -> precerco NEGRO -> interfaz azul.
            # El contorno cian se traza sobre el rectángulo exterior,
            # sin pintar otra línea azul al lado del contenido interior.
            outer = QRectF(self.rect()).adjusted(4, 4, -4, -4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#02060d"))
            painter.drawRoundedRect(outer, radius + 6, radius + 6)
            painter.setBrush(Qt.NoBrush)
            # Halo tenue alrededor del borde exterior, como floatingGlass.
            for width, alpha in ((8, 23), (5, 50)):
                painter.setPen(QPen(QColor(14, 201, 255, alpha), width))
                painter.drawRoundedRect(outer, radius + 6, radius + 6)
            painter.setPen(QPen(QColor("#27dffe"), 2))
            painter.drawRoundedRect(outer, radius + 6, radius + 6)
        bg = QLinearGradient(0, bounds.top(), 0, bounds.bottom())
        bg.setColorAt(0, QColor("#052153"))
        bg.setColorAt(.35, QColor("#041a41"))
        bg.setColorAt(1, QColor("#031434"))
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.NoPen if not self._is_maximized
                       else QPen(QColor("#27dffe"), 0))
        painter.drawRoundedRect(bounds, radius, radius)
        painter.end()
