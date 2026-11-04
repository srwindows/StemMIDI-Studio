"""Ventana principal sin decoración KDE, con movimiento y redimensionado propios.

Afecta solo al QMainWindow. Diálogos, flotantes, pestañas y sus controles
conservan exactamente sus tipos y relaciones actuales.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QEvent, QPoint, QRect
from PySide6.QtWidgets import QApplication, QWidget, QLabel


class _EdgeGrip(QWidget):
    """Zona transparente de 6 px sobre cada borde, sin marco visible."""
    def __init__(self, controller, edges, cursor):
        super().__init__(controller.main)
        self.owner = controller
        self.edges = edges
        self.setObjectName("mainBorderlessResizeGrip")
        self.setCursor(cursor)
        self.setStyleSheet("background:transparent;border:0;")
        self.setMouseTracking(True)
        self._origin_global = QPoint()
        self._origin_rect = QRect()
        self._resizing = False
        self.show()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.owner.main.isMaximized():
            return super().mousePressEvent(event)
        window = self.owner.main.windowHandle()
        # En Wayland la superficie debe moverse por el compositor.
        if QApplication.platformName() == "wayland" and window is not None:
            if window.startSystemResize(self.edges):
                event.accept()
                return
        self._resizing = True
        self._origin_global = event.globalPosition().toPoint()
        self._origin_rect = QRect(self.owner.main.geometry())
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._resizing:
            return super().mouseMoveEvent(event)
        delta = event.globalPosition().toPoint() - self._origin_global
        original = self._origin_rect
        rect = QRect(original)
        minimum_width = self.owner.main.minimumWidth()
        minimum_height = self.owner.main.minimumHeight()
        if self.edges & Qt.LeftEdge:
            rect.setLeft(min(original.left() + delta.x(),
                             original.right() - minimum_width + 1))
        if self.edges & Qt.RightEdge:
            rect.setRight(max(original.right() + delta.x(),
                              original.left() + minimum_width - 1))
        if self.edges & Qt.TopEdge:
            rect.setTop(min(original.top() + delta.y(),
                            original.bottom() - minimum_height + 1))
        if self.edges & Qt.BottomEdge:
            rect.setBottom(max(original.bottom() + delta.y(),
                               original.top() + minimum_height - 1))
        self.owner.main.setGeometry(rect)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._resizing and event.button() == Qt.LeftButton:
            self._resizing = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class FramelessWindowController(QObject):
    """La cabecera ya existente actúa de asidero, sin interceptar botones."""
    def __init__(self, main, banner):
        super().__init__(main)
        self.main = main
        self.banner = banner
        self._moving = False
        self._press_global = QPoint()
        self._press_window = QPoint()
        # Únicamente zona decorativa, logo y rótulos de la cabecera.
        # Los QPushButton de proyectos y ventanas no reciben este filtro.
        self._handles = [banner, banner.text_panel, banner.logo]
        self._handles.extend(banner.text_panel.findChildren(QLabel))
        for widget in self._handles:
            widget.installEventFilter(self)
            widget.setMouseTracking(True)
        main.installEventFilter(self)
        self._grips = [
            _EdgeGrip(self, Qt.LeftEdge, Qt.SizeHorCursor),
            _EdgeGrip(self, Qt.RightEdge, Qt.SizeHorCursor),
            _EdgeGrip(self, Qt.TopEdge, Qt.SizeVerCursor),
            _EdgeGrip(self, Qt.BottomEdge, Qt.SizeVerCursor),
            _EdgeGrip(self, Qt.TopEdge | Qt.LeftEdge, Qt.SizeFDiagCursor),
            _EdgeGrip(self, Qt.BottomEdge | Qt.RightEdge, Qt.SizeFDiagCursor),
            _EdgeGrip(self, Qt.TopEdge | Qt.RightEdge, Qt.SizeBDiagCursor),
            _EdgeGrip(self, Qt.BottomEdge | Qt.LeftEdge, Qt.SizeBDiagCursor),
        ]
        self._layout_grips()

    def _layout_grips(self):
        w, h = self.main.width(), self.main.height()
        border = 6
        corner = 14
        rects = (
            (0, corner, border, max(0, h - 2*corner)),
            (max(0, w-border), corner, border, max(0, h - 2*corner)),
            (corner, 0, max(0, w-2*corner), border),
            (corner, max(0, h-border), max(0, w-2*corner), border),
            (0, 0, corner, corner),
            (max(0, w-corner), max(0, h-corner), corner, corner),
            # La esquina superior derecha no cubre el botón × propio,
            # situado inmediatamente debajo (a partir de y=7).
            (max(0, w-corner), 0, corner, border),
            (0, max(0, h-corner), corner, corner),
        )
        for grip, geom in zip(self._grips, rects):
            grip.setGeometry(*geom)
            grip.setVisible(not self.main.isMaximized() and
                            not self.main.isFullScreen() and
                            not self.main.isMinimized())
            grip.raise_()

    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.main:
            if kind in (QEvent.Resize, QEvent.WindowStateChange, QEvent.Show):
                self._layout_grips()
                rounded=getattr(self.main, "_rounded_shell", None)
                if rounded is not None:
                    rounded.sync_window_state()
            return False
        if obj not in self._handles:
            return False
        if kind == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            if self.main.isMaximized():
                self.main.showNormal()
            else:
                self.main.showMaximized()
            event.accept()
            return True
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            # Al arrastrar una cabecera maximizada, primero restaurar la
            # ventana, conservando el cursor sobre el mismo área visual.
            if self.main.isMaximized():
                pointer = event.globalPosition().toPoint()
                ratio = pointer.x() / max(1, self.main.width())
                self.main.showNormal()
                self.main.move(pointer.x()-int(ratio*self.main.width()),
                               pointer.y()-24)
            self._press_global = event.globalPosition().toPoint()
            self._press_window = self.main.pos()
            handle = self.main.windowHandle()
            if QApplication.platformName() == "wayland" and handle is not None:
                if handle.startSystemMove():
                    self._moving = False
                    event.accept()
                    return True
            self._moving = True
            event.accept()
            return True
        if kind == QEvent.MouseMove and self._moving:
            delta = event.globalPosition().toPoint()-self._press_global
            self.main.move(self._press_window + delta)
            event.accept()
            return True
        if kind == QEvent.MouseButtonRelease and self._moving:
            self._moving = False
            event.accept()
            return True
        return False
