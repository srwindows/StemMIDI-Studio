"""Editor de Sample Delay interno: dos diales, L/R, enlace y muestras/ms."""
from __future__ import annotations
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDial, QDoubleSpinBox,
    QCheckBox, QComboBox, QFrame
)
from stemmidi_sample_delay import MAX_SAMPLES


class SampleDelayControls(QWidget):
    """Ajusta en tiempo real el procesador nativo de un canal o bus."""
    def __init__(self, effect, parent=None):
        super().__init__(parent)
        self.effect = effect
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(7)
        title = QLabel("SAMPLE DELAY · DESPLAZAMIENTO ESTÉREO", self)
        title.setStyleSheet("color:#a5ecf5;font-weight:800;font-size:11px")
        layout.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(15)
        self._controls = []
        for channel, text in (("left", "DELAY LEFT · L"), ("right", "DELAY RIGHT · R")):
            column = QVBoxLayout()
            label = QLabel(text, self)
            label.setAlignment(Qt.AlignCenter)
            column.addWidget(label)
            dial = QDial(self)
            dial.setRange(0, MAX_SAMPLES)
            dial.setNotchesVisible(True)
            dial.setWrapping(False)
            dial.setFixedSize(90, 90)
            dial.setToolTip("Retardo exacto expresado en muestras")
            column.addWidget(dial, 0, Qt.AlignHCenter)
            value = QDoubleSpinBox(self)
            value.setKeyboardTracking(False)
            value.setAlignment(Qt.AlignCenter)
            value.setMinimumWidth(108)
            column.addWidget(value)
            row.addLayout(column, 1)
            dial.valueChanged.connect(lambda samples,c=channel:self._set_samples(c,samples))
            value.valueChanged.connect(lambda amount,c=channel:self._set_value(c,amount))
            self._controls.append((dial,value))
        layout.addLayout(row)
        bottom = QHBoxLayout()
        self.link = QCheckBox("Link L & R", self)
        self.link.setToolTip("Igualar ambos retardos y mantenerlos enlazados")
        self.link.toggled.connect(self._link)
        bottom.addWidget(self.link)
        bottom.addStretch()
        bottom.addWidget(QLabel("Unidad:",self))
        self.units = QComboBox(self)
        self.units.addItem("Samples", "samples")
        self.units.addItem("ms", "ms")
        self.units.currentIndexChanged.connect(self._unit)
        bottom.addWidget(self.units)
        layout.addLayout(bottom)
        foot = QLabel("0–10.000 muestras · sin feedback ni mezcla añadida",self)
        foot.setAlignment(Qt.AlignCenter)
        foot.setStyleSheet("color:#83b6c8;font-size:9px")
        layout.addWidget(foot)
        self._refresh()

    def _refresh(self):
        mode = self.effect.units
        with QSignalBlocker(self.units):
            self.units.setCurrentIndex(0 if mode == "samples" else 1)
        with QSignalBlocker(self.link):
            self.link.setChecked(self.effect.linked)
        for index, samples in enumerate((
            self.effect.delay_left_samples, self.effect.delay_right_samples
        )):
            dial, value = self._controls[index]
            with QSignalBlocker(dial), QSignalBlocker(value):
                dial.setValue(samples)
                if mode == "samples":
                    value.setDecimals(0)
                    value.setRange(0, MAX_SAMPLES)
                    value.setSingleStep(1.)
                    value.setSuffix(" smp")
                    value.setValue(samples)
                else:
                    value.setDecimals(3)
                    value.setRange(0.,MAX_SAMPLES*1000./self.effect.rate)
                    value.setSingleStep(1000./self.effect.rate)
                    value.setSuffix(" ms")
                    value.setValue(samples*1000./self.effect.rate)

    def _set_samples(self,channel,samples):
        if channel == "left":
            self.effect.delay_left_samples = samples
        else:
            self.effect.delay_right_samples = samples
        self._refresh()

    def _set_value(self,channel,value):
        if self.effect.units == "ms":
            value = round(value * self.effect.rate / 1000.)
        self._set_samples(channel,round(value))

    def _link(self, linked):
        self.effect.linked = linked
        self._refresh()

    def _unit(self, index):
        self.effect.units = self.units.itemData(index)
        self._refresh()
