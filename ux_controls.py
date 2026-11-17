"""Controles compactos para las pestañas del estudio, PySide6."""
from __future__ import annotations
import json
import re
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,QHBoxLayout,QVBoxLayout,QSlider,QSpinBox,QDoubleSpinBox,QComboBox,
    QLineEdit,QPushButton,QLabel,QFrame
)

from studio_paths import workspace_root
ROOT=workspace_root(__file__)
PRESET_DIR=ROOT/"presets_usuario"
class SliderNumber(QWidget):
    """Deslizante + número editable. Compatible con el API habitual de SpinBox."""
    valueChanged=Signal(float)
    def __init__(self,lo,hi,value,step=1,decimals=0,suffix="",parent=None):
        super().__init__(parent)
        self.factor=10**decimals
        self.decimals=decimals
        layout=QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(7)
        self.slider=QSlider(Qt.Horizontal,self)
        self.slider.setRange(round(lo*self.factor),round(hi*self.factor))
        self.slider.setSingleStep(max(1,round(step*self.factor)))
        self.slider.setPageStep(max(1,round(step*10*self.factor)))
        self.slider.setMinimumWidth(92)
        self.slider.setToolTip("Arrastra para ajustar; el número se puede escribir directamente.")
        layout.addWidget(self.slider,1)
        self.number=(QDoubleSpinBox if decimals else QSpinBox)(self)
        self.number.setRange(lo,hi)
        if decimals:self.number.setDecimals(decimals)
        self.number.setSingleStep(step)
        self.number.setSuffix(suffix)
        self.number.setFixedWidth(103 if suffix else 78)
        layout.addWidget(self.number)
        self.slider.valueChanged.connect(self._slider_changed)
        self.number.valueChanged.connect(self._number_changed)
        self.setValue(value)
        self.setMinimumWidth(190)
    def _slider_changed(self,ticks):
        value=ticks/self.factor
        if self.number.value()!=value:
            old=self.number.blockSignals(True)
            self.number.setValue(value)
            self.number.blockSignals(old)
        self.valueChanged.emit(float(value))
    def _number_changed(self,value):
        ticks=round(value*self.factor)
        if ticks!=self.slider.value():
            old=self.slider.blockSignals(True)
            self.slider.setValue(ticks)
            self.slider.blockSignals(old)
        self.valueChanged.emit(float(value))
    def value(self):return self.number.value()
    def setValue(self,value):self.number.setValue(value)
    def setRange(self,a,b):
        self.number.setRange(a,b)
        self.slider.setRange(round(a*self.factor),round(b*self.factor))
    def setSingleStep(self,step):
        self.number.setSingleStep(step)
        self.slider.setSingleStep(max(1,round(step*self.factor)))
    def setDecimals(self,n):
        if n!=self.decimals:raise ValueError("Decimales definidos al construir control")
    def setSuffix(self,text):self.number.setSuffix(text)
    def setToolTip(self,text):
        super().setToolTip(text)
        self.slider.setToolTip(text)
        self.number.setToolTip(text)


class PresetStrip(QFrame):
    """Presets integrados en cada pestaña; guarda solo parámetros, nunca archivos."""
    def __init__(self,kind,builtins,snapshot,apply,parent=None):
        super().__init__(parent)
        self.kind=kind
        self.builtins=builtins
        self.snapshot=snapshot
        self.apply=apply
        self._loading=False
        self.setObjectName("inner")
        row=QHBoxLayout(self)
        row.setContentsMargins(8,6,8,6)
        row.setSpacing(6)
        row.addWidget(QLabel("PRESET"))
        self.choices=QComboBox(self)
        self.choices.setMinimumWidth(155)
        self.choices.setMaximumWidth(235)
        self.choices.setToolTip("Selecciona una configuración guardada sin modificar tus archivos.")
        row.addWidget(self.choices)
        self.name=QLineEdit(self)
        self.name.setPlaceholderText("Nombre de preset propio")
        self.name.setMinimumWidth(100)
        self.name.setMaximumWidth(190)
        row.addWidget(self.name)
        self.save_btn=QPushButton("Guardar")
        self.save_btn.clicked.connect(self.save_custom)
        row.addWidget(self.save_btn)
        self.delete_btn=QPushButton("Borrar")
        self.delete_btn.clicked.connect(self.delete_custom)
        row.addWidget(self.delete_btn)
        self.message=QLabel("")
        self.message.setObjectName("muted")
        self.message.setMinimumWidth(0)
        self.message.setMaximumWidth(170)
        row.addWidget(self.message)
        row.addStretch(1)
        self.choices.currentIndexChanged.connect(self.load_selected)
        self.refresh()
    @property
    def path(self):return PRESET_DIR/(self.kind+".json")
    def _read(self):
        try:
            data=json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data,dict) else {}
        except (OSError,TypeError,ValueError):return {}
    def _write(self,document):
        PRESET_DIR.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(document,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        temp.replace(self.path)
    def refresh(self,select=None):
        last=select or self.choices.currentData()
        self._loading=True
        self.choices.clear()
        self.choices.addItem("— Elegir preset —",None)
        for title in self.builtins:
            self.choices.addItem("● "+title,("base",title))
        for title in sorted(self._read()):
            self.choices.addItem("★ "+title,("propio",title))
        index=next((i for i in range(self.choices.count())
                    if self.choices.itemData(i)==last),-1)
        if index>0:self.choices.setCurrentIndex(index)
        self._loading=False
    def load_selected(self,index):
        if self._loading or index<0:return
        key=self.choices.itemData(index)
        if not key:return
        origin,name=key
        params=self.builtins.get(name) if origin=="base" else self._read().get(name)
        if not isinstance(params,dict):return
        self._loading=True
        try:
            self.apply(dict(params))
            self.name.setText(name if origin=="propio" else "")
            self.message.setText("Aplicado")
        finally:self._loading=False
    def save_custom(self):
        name=self.name.text().strip()
        if not name:
            self.message.setText("Escribe un nombre")
            self.name.setFocus()
            return
        if len(name)>55 or name in self.builtins:
            self.message.setText("Nombre no válido")
            return
        params=self.snapshot()
        if not isinstance(params,dict):return
        old=self._read()
        old[name]=params
        self._write(old)
        self.refresh(("propio",name))
        self.message.setText("Guardado")
    def delete_custom(self):
        key=self.choices.currentData()
        if not key or key[0]!="propio":
            self.message.setText("Selecciona uno propio")
            return
        old=self._read()
        old.pop(key[1],None)
        self._write(old)
        self.refresh()
        self.message.setText("Preset borrado")
