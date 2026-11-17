"""VU estéreo PCM compacto (medición real suministrada por el reproductor)."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter,QColor,QPen
import math

from studio_vu_unified import UnifiedStereoMeter

class CompactStereoMeter(UnifiedStereoMeter):
    """VU compacto del mismo patrón Monitor, sin desplazar controles."""
    def __init__(self,parent=None):
        super().__init__(parent,height=26,width=65)
        self.setFixedHeight(26)
