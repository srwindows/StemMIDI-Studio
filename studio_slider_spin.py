"""Control compacto de estudio: fader y valor numérico editables/sincronizados."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QHBoxLayout,QSlider,QSpinBox,QLabel,QSizePolicy

class StudioSliderSpin(QWidget):
    valueChanged=Signal(int)
    def __init__(self,low=0,high=100,value=0,suffix="",parent=None,width=235):
        super().__init__(parent)
        self.setObjectName("studioSliderSpin")
        self.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        box=QHBoxLayout(self)
        box.setContentsMargins(0,0,0,0)
        box.setSpacing(6)
        self.slider=QSlider(Qt.Horizontal,self)
        self.slider.setRange(int(low),int(high))
        self.slider.setSingleStep(1)
        self.slider.setMinimumWidth(75)
        self.slider.setMaximumWidth(max(75,width-96))
        self.spin=QSpinBox(self)
        self.spin.setRange(int(low),int(high))
        self.spin.setSuffix(" "+suffix if suffix and not suffix.startswith(" ") else suffix)
        self.spin.setButtonSymbols(QSpinBox.PlusMinus)
        self.spin.setFixedWidth(84)
        box.addWidget(self.slider,1)
        box.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.setMaximumWidth(width)
        self.setMinimumWidth(min(width,170))
        self.setValue(value)

    def _from_slider(self,n):
        if self.spin.value()!=n:
            flag=self.spin.blockSignals(True)
            self.spin.setValue(n)
            self.spin.blockSignals(flag)
        self.valueChanged.emit(n)

    def _from_spin(self,n):
        if self.slider.value()!=n:
            flag=self.slider.blockSignals(True)
            self.slider.setValue(n)
            self.slider.blockSignals(flag)
        self.valueChanged.emit(n)

    def value(self):return self.spin.value()
    def setValue(self,n):self.spin.setValue(int(n))
    def setRange(self,lo,hi):
        self.spin.setRange(int(lo),int(hi))
        self.slider.setRange(int(lo),int(hi))
    def minimum(self):return self.spin.minimum()
    def maximum(self):return self.spin.maximum()
    def setSuffix(self,s):self.spin.setSuffix(s)
    def suffix(self):return self.spin.suffix()
    def setSingleStep(self,n):
        self.spin.setSingleStep(int(n))
        self.slider.setSingleStep(int(n))
    def setToolTip(self,t):
        super().setToolTip(t)
        self.slider.setToolTip(t)
        self.spin.setToolTip(t)
