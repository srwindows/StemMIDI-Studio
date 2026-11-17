"""Transportes de StemMIDI: botones reales y medición de señal real."""
from __future__ import annotations
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QSizePolicy
from widgets import StereoMeter

class RecordTransport(QFrame):
    """Reutiliza los botones conectados al motor de grabación de Inicio."""
    def __init__(self,home,record,pause,stop,parent=None):
        super().__init__(parent)
        self.home=home
        self.setObjectName("studioTransport")
        self.setStyleSheet("""
        QFrame#studioTransport{background:#041a42;border:1px solid #2bb1fc;border-radius:9px;}
        QFrame#studioTransport QLabel#transportClock{color:#85f0ff;font:700 14px 'DejaVu Sans Mono';}
        QFrame#studioTransport QLabel#transportStatus{color:#e0f8ff;font-size:10px;}
        QFrame#studioTransport QPushButton{min-height:26px;border-radius:6px;font-weight:700;}
        QFrame#studioTransport QPushButton#record{background:#a73348;border:1px solid #f26775;}
        """)
        self.setFixedHeight(42)
        layout=QVBoxLayout(self);layout.setContentsMargins(6,4,6,4);layout.setSpacing(0)
        row=QHBoxLayout();row.setSpacing(5)
        for btn,caption in ((record,"● REC"),(pause,"Ⅱ"),(stop,"■")):
            btn.setText(caption)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumWidth(37)
            btn.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            row.addWidget(btn,1)
        self.clock=QLabel("00:00:00")
        self.clock.setObjectName("transportClock")
        row.addWidget(self.clock)
        layout.addLayout(row)
        # El VU estéreo vertical original ya está inmediatamente a la
        # derecha del transporte dentro de la misma tarjeta de Monitor.
        # No duplicarlo aquí: duplicarlo comprimía y solapaba los mandos.
        self.timer=QTimer(self)
        self.timer.setInterval(240)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
    def refresh(self):
        main=self.home.main
        clock=getattr(main,"clock",None)
        if clock is not None:self.clock.setText(clock.text())
    def set_levels(self,left,right,peak_left,peak_right):
        # El medidor real del mismo módulo recibe los niveles
        # por home.sync_capture_levels(), sin un segundo VU decorativo.
        pass
