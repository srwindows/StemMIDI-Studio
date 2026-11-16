"""Parámetros profesionales de la inferencia MDX23C de batería.

Solo opciones que usa MDX23CInference.separate(batch_size,overlap) y el
exportador (formato/PCM/frecuencia). Las constantes de arquitectura del
YAML NO se presentan como deslizantes de inferencia.
"""
from __future__ import annotations
import json,os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QGroupBox,QLabel,QSlider,QComboBox,
    QPushButton,QGridLayout,QHBoxLayout,QVBoxLayout,QSizePolicy)
from studio_paths import workspace_root

DEFAULTS={'overlap':4,'batch_size':1,'output_format':'FLAC',
          'bit_depth':24,'sample_rate':44100}
VALUES={'overlap':range(1,9),'batch_size':range(1,5),
        'bit_depth':(16,24),'sample_rate':(44100,48000)}


def settings_path():
    return workspace_root(__file__)/'configuracion'/'bateria_mdx23c.json'


def read_settings():
    result=dict(DEFAULTS)
    try:
        data=json.loads(settings_path().read_text(encoding='utf-8'))
        if isinstance(data,dict):
            for key,choices in VALUES.items():
                if data.get(key) in choices:result[key]=data[key]
            if data.get('output_format') in ('FLAC','WAV'):
                result['output_format']=data['output_format']
    except (OSError,ValueError,TypeError):pass
    return result


def save_settings(values):
    valid=dict(DEFAULTS)
    for key,choices in VALUES.items():
        if values.get(key) in choices:valid[key]=values[key]
    if values.get('output_format') in ('FLAC','WAV'):
        valid['output_format']=values['output_format']
    path=settings_path();path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(valid,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)
    return valid


class DrumEngineSettingsPanel(QGroupBox):
    """Controla la misma instancia DrumModule que el resto de la pestaña."""
    def __init__(self,drum,parent=None):
        super().__init__('AJUSTES REALES DEL MOTOR · MDX23C',parent)
        self.setObjectName('drumRealEngineSettings')
        self.drum=drum
        self.sliders={}
        self.values={}
        self.setStyleSheet('''
          QGroupBox#drumRealEngineSettings {border:1px solid #238ec9;
           border-radius:5px;margin-top:11px;padding:6px;background:#061e44;
           color:#e4f8ff;font-weight:650;}
          QGroupBox#drumRealEngineSettings::title {subcontrol-origin:margin;
           left:9px;padding:0px 5px;}
          QLabel {color:#d8eeff;}
        ''')
        root=QVBoxLayout(self)
        root.setContentsMargins(10,12,10,7);root.setSpacing(6)
        grid=QGridLayout();grid.setContentsMargins(0,0,0,0)
        grid.setHorizontalSpacing(14);grid.setVerticalSpacing(8)
        grid.setColumnStretch(1,1);grid.setColumnStretch(3,1)
        self.grid=grid
        root.addLayout(grid)
        self._field('overlap','Solapamiento',list(VALUES['overlap']),0,0,
            'Número de segmentos superpuestos. Mayor solapamiento puede mejorar uniones a costa de más cálculo.')
        self._field('batch_size','Lote IA',list(VALUES['batch_size']),0,2,
            'Segmentos procesados juntos por inferencia; valores altos consumen más memoria.')
        self._field('sample_rate','Frecuencia de salida',list(VALUES['sample_rate']),1,0,
            'La IA procesa internamente a 44.100 Hz; al exportar a 48.000 Hz se remuestrean las muestras.')
        self._field('bit_depth','Profundidad',list(VALUES['bit_depth']),1,2,
            'Profundidad PCM de los seis archivos guardados: 16 o 24 bits.')
        line=QHBoxLayout();line.setSpacing(5)
        lbl=QLabel('Formato',self);lbl.setFixedWidth(60)
        self.output_format=QComboBox(self)
        self.output_format.addItems(['FLAC','WAV'])
        self.output_format.setFixedWidth(125)
        self.output_format.setProperty('preserveComboWidth',True)
        self.output_format.setToolTip('Contenedor de salida de audio: FLAC sin pérdida o WAV.')
        self.output_format.currentTextChanged.connect(lambda v:self._change('output_format',v))
        line.addWidget(lbl);line.addWidget(self.output_format)
        line.addSpacing(15)
        self.reset=QPushButton('Restablecer motor',self)
        self.reset.setToolTip('Devuelve solo los parámetros de inferencia y exportación a sus valores de fábrica.')
        self.reset.clicked.connect(lambda checked=False:self.restore_defaults())
        line.addWidget(self.reset)
        line.addStretch(1)
        root.addLayout(line)
        self.explanation=QLabel(
            'Inferencia: solapamiento y lote ajustables. Arquitectura, FFT, capas y entrenamiento'
            ' pertenecen al checkpoint y no pueden variarse sin invalidar sus pesos. '
            'Dispositivo en este Mac: CPU (el backend no admite MPS).',self)
        self.explanation.setWordWrap(True)
        self.explanation.setStyleSheet('color:#9ed5e9;font-size:11px;')
        root.addWidget(self.explanation)
        self.sync()

    def _field(self,key,label,options,row,column,tooltip):
        title=QLabel(label,self)
        # Las etiquetas NO ocupan el ancho de la etiqueta más larga de la
        # columna: el deslizador empieza justo después de su propio texto.
        title.setFixedWidth(title.fontMetrics().horizontalAdvance(label)+5)
        title.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        slider=QSlider(Qt.Horizontal,self)
        slider.setObjectName('drumParam_'+key)
        slider.setRange(0,len(options)-1)
        slider.setSingleStep(1)
        slider.setMinimumWidth(90)
        slider.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        slider.setToolTip(tooltip)
        value=QLabel(self);value.setFixedWidth(52)
        value.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        value.setToolTip(tooltip)
        control=QWidget(self)
        control_layout=QHBoxLayout(control)
        control_layout.setContentsMargins(0,0,0,0)
        control_layout.setSpacing(4)
        control_layout.addWidget(slider,1)
        control_layout.addWidget(value)
        grid=self.grid
        pair=QWidget(self)
        pair_layout=QHBoxLayout(pair)
        pair_layout.setContentsMargins(0,0,0,0)
        pair_layout.setSpacing(5)
        pair_layout.addWidget(title)
        pair_layout.addWidget(control,1)
        grid.addWidget(pair,row,column,1,2)
        self.sliders[key]=slider
        self.values[key]=value
        slider.valueChanged.connect(lambda i,k=key,choices=options:
            self._change(k,choices[i]))

    def _change(self,key,value):
        self.drum.engine_settings[key]=value
        if key in self.values:self.values[key].setText(str(value))
        save_settings(self.drum.engine_settings)

    def sync(self):
        values=self.drum.engine_settings
        for key,slider in self.sliders.items():
            blocked=slider.blockSignals(True)
            slider.setValue(list(VALUES[key]).index(values[key]))
            slider.blockSignals(blocked)
            self.values[key].setText(str(values[key]))
        blocked=self.output_format.blockSignals(True)
        self.output_format.setCurrentText(values['output_format'])
        self.output_format.blockSignals(blocked)

    def restore_defaults(self):
        self.drum.engine_settings=save_settings(DEFAULTS)
        self.sync()

    def set_busy(self,busy):
        for control in (*self.sliders.values(),self.output_format,self.reset):
            control.setEnabled(not busy)
