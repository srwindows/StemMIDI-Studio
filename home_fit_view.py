"""Cuadrícula completa de Inicio ajustada a la pantalla, sin scroll.

La página REAL con los 12 QWidget existentes vive en una única
QGraphicsProxyWidget; todo conserva señales, QProcess y candados.
El zoom se calcula del espacio disponible, no oculta ni recorta tarjetas.
"""
from __future__ import annotations
from math import ceil
from PySide6.QtCore import Qt,QRectF,QTimer
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import (QGraphicsView,QGraphicsScene,QFrame,
                               QGraphicsItem,QSizePolicy)

class FitHomeView(QGraphicsView):
    BASE_HEIGHT=816
    MIN_WIDTH=1390
    def __init__(self,page,parent=None):
        scene=QGraphicsScene(parent)
        super().__init__(scene,parent)
        self._page=page
        self._proxy=scene.addWidget(page)
        self._proxy.setCacheMode(QGraphicsItem.NoCache)
        self.setObjectName("homeNoScrollFitView")
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setRenderHint(QPainter.Antialiasing,False)
        self.setAlignment(Qt.AlignCenter)
        self.setBackgroundBrush(QColor("#031330"))
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setMinimumSize(0,0)
        self.setStyleSheet("QGraphicsView#homeNoScrollFitView{border:0;background:#031330;}")
        self._fitting=False
        QTimer.singleShot(0,self.fit_all)

    def fit_all(self):
        if self._fitting:return
        self._fitting=True
        try:
            viewport=self.viewport()
            avail_w=max(1,viewport.width()-2)
            avail_h=max(1,viewport.height()-2)
            # Dar a cada fila su altura original, sin recortar el cuerpo
            # ni crear nuevas pantallas/controles. La página virtual crece
            # en anchura para llenar toda la pantalla cuando es panorámica.
            content_h=max(self.BASE_HEIGHT,self._page.minimumSizeHint().height()+15)
            content_w=max(self.MIN_WIDTH,ceil(avail_w*content_h/avail_h))
            self._page.setFixedSize(content_w,content_h)
            rect=QRectF(0,0,content_w,content_h)
            self.scene().setSceneRect(rect)
            self._proxy.setPos(0,0)
            self.fitInView(rect,Qt.KeepAspectRatio)
        finally:
            self._fitting=False

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.fit_all()

    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(0,self.fit_all)
