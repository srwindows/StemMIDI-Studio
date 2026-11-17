"""Editable built-in native stereo Reverb for the channel/BUS FX racks.

The DSP is the compiled Pedalboard Reverb, bundled with the app.
No external VST3 or AU file is loaded.
"""
from __future__ import annotations
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,
                               QDial,QDoubleSpinBox,QGridLayout,QFrame)


CONTROLS=(
    ("room_size","Tamaño","Sala",0.,1.,.55),
    ("damping","Absorción","Agudos",0.,1.,.5),
    ("wet_level","Efecto","Reverb",0.,1.,.45),
    ("dry_level","Señal seca","Original",0.,1.,.55),
    ("width","Anchura","Estéreo",0.,1.,1.),
)


class ReverbControls(QWidget):
    """Continuous realtime reverb controls for a single channel or BUS."""
    def __init__(self,reverb,parent=None):
        super().__init__(parent)
        self.reverb=reverb
        self.setObjectName("stemmidiReverbControls")
        self.setStyleSheet("""
          QWidget#stemmidiReverbControls{background:#0a2131;
             border:1px solid #315e78;border-radius:6px}
          QDial{background:transparent}
          QLabel{color:#d8f6ff;background:transparent;font-size:11px}
          QDoubleSpinBox{background:#12354b;color:#f0fcff;border:1px solid #397995;
             border-radius:4px;padding:2px}
        """)
        root=QVBoxLayout(self)
        root.setContentsMargins(10,8,10,8)
        root.setSpacing(7)
        title=QLabel("REVERB DE ESTUDIO · ESTÉREO",self)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color:#a7f9f0;font-size:13px;font-weight:800")
        root.addWidget(title)
        description=QLabel(
            "Reverberación en tiempo real, aplicada solo a esta ruta.\n"
            "Combina señal seca y húmeda; puedes usarla en pistas o buses.",
            self)
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignCenter)
        root.addWidget(description)
        grid=QGridLayout()
        grid.setSpacing(8)
        self.controls={}
        for i,(attribute,label,short,minimum,maximum,default) in enumerate(CONTROLS):
            container=QFrame(self)
            col=QVBoxLayout(container)
            col.setContentsMargins(1,1,1,1);col.setSpacing(4)
            caption=QLabel(label,container)
            caption.setAlignment(Qt.AlignCenter)
            col.addWidget(caption)
            dial=QDial(container)
            dial.setObjectName("reverb_"+attribute)
            dial.setRange(0,1000)
            dial.setWrapping(False)
            dial.setNotchesVisible(True)
            dial.setFixedSize(77,76)
            dial.setToolTip(label+" · "+short+" · cambia el sonido en tiempo real")
            col.addWidget(dial,0,Qt.AlignCenter)
            spin=QDoubleSpinBox(container)
            spin.setRange(minimum,maximum)
            spin.setDecimals(2)
            spin.setSingleStep(.01)
            spin.setValue(float(getattr(reverb,attribute,default)))
            spin.setSuffix(" ")
            col.addWidget(spin)
            dial.setValue(round(float(getattr(reverb,attribute,default))*1000))
            dial.valueChanged.connect(
                lambda val,k=attribute,s=spin:self._change(k,val/1000,s))
            spin.valueChanged.connect(
                lambda val,k=attribute,d=dial:self._change(k,val,d))
            self.controls[attribute]=(dial,spin)
            grid.addWidget(container,i//3,i%3)
        root.addLayout(grid)
        foot=QLabel("0 = sin efecto  ·  1 = máximo · Ajustes guardados con el proyecto",self)
        foot.setAlignment(Qt.AlignCenter)
        foot.setWordWrap(True)
        root.addWidget(foot)

    def _change(self,attribute,value,other):
        value=max(0.,min(1.,float(value)))
        setattr(self.reverb,attribute,value)
        with QSignalBlocker(other):
            if isinstance(other,QDial):other.setValue(round(value*1000))
            else:other.setValue(value)
