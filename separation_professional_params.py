"""Panel avanzado profesional: parámetros reales del motor sin duplicar lógica.

Los controles aparecen únicamente para la arquitectura seleccionada.
Los cambios se guardan, se pueden deshacer y se entregan a audio-separator.
"""
from __future__ import annotations
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDoubleSpinBox,QFrame,
                               QHBoxLayout,QLabel,QPushButton,QSlider,
                               QSizePolicy,QVBoxLayout,QWidget)
from separador import MODELS
from separation_engine_parameters import (
    MODEL_FIELDS, COMMON_FIELDS, family_for_model,merged_settings,safe_value)

OPTIONS={
    'mdx_segment_size':[128,256,512],
    'mdx_hop_length':[512,1024,2048],
    'mdxc_segment_size':[128,256,512,1024],
    'vr_window_size':[320,512,1024],
    'mp3_bitrate':[128,192,256,320],
    'sample_rate':[44100,48000]
}


class ParameterSlider(QWidget):
    """Deslizante numérico real: etiqueta del valor sin casilla de texto.

    Conserva value()/setValue() para conectar motores, historial y presets.
    Los pasos son exactos; la lista de opciones discretas no crea valores
    imposibles para audio-separator.
    """
    valueChanged=Signal(object)

    def __init__(self,parent,key,spec):
        super().__init__(parent)
        label,minimum,maximum,step,_=spec
        self.key=key
        self.options=tuple(OPTIONS[key]) if key in OPTIONS else None
        self.minimum_value=minimum
        self.increment=step
        self.decimals=(2 if isinstance(minimum,float) or isinstance(maximum,float) else 0)
        row=QHBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(5)
        self.slider=QSlider(Qt.Horizontal,self)
        self.slider.setObjectName('aiSlider_'+key)
        self.slider.setFocusPolicy(Qt.StrongFocus)
        self.slider.setMinimumWidth(70)
        self.slider.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        if self.options:
            self.slider.setRange(0,len(self.options)-1)
        else:
            self.slider.setRange(0,round((maximum-minimum)/step))
        self.readout=QLabel(self)
        self.readout.setObjectName('aiValue_'+key)
        self.readout.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.readout.setFixedWidth(49 if key!='sample_rate' else 55)
        self.readout.setToolTip(label+' · valor actual')
        row.addWidget(self.slider,1)
        row.addWidget(self.readout)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.setMinimumWidth(113)
        self.setMaximumWidth(260)
        self.setToolTip(label+' · arrastra para modificar el valor')
        self.slider.valueChanged.connect(self._changed)
        self._changed(self.slider.value())

    def value(self):
        index=self.slider.value()
        if self.options:return self.options[index]
        value=self.minimum_value+index*self.increment
        return round(value,2) if self.decimals else int(round(value))

    def _changed(self,_):
        val=self.value()
        if self.key=='demucs_segment_size' and val==0:
            txt='Auto'
        elif self.decimals:
            txt=f'{val:.2f}'.replace('.',',')
        else:
            txt=str(val)
        self.readout.setText(txt)
        self.valueChanged.emit(val)

    def setValue(self,value):
        if value is None:value=self.minimum_value
        if self.options:
            index=min(range(len(self.options)),key=lambda i:abs(self.options[i]-float(value)))
        else:
            index=round((float(value)-self.minimum_value)/self.increment)
        index=max(self.slider.minimum(),min(self.slider.maximum(),index))
        self.slider.setValue(index)


def control(parent,key,spec):
    label,minimum,maximum,step,_=spec
    if isinstance(minimum,bool):
        widget=QCheckBox(label,parent)
        widget.setToolTip(label+': parámetro admitido por audio-separator 0.22')
        return widget
    return ParameterSlider(parent,key,spec)


def get(widget):
    if isinstance(widget,QCheckBox):return widget.isChecked()
    if isinstance(widget,QComboBox):return widget.currentData()
    return widget.value()


def put(widget,value):
    old=widget.blockSignals(True)
    try:
        if isinstance(widget,QCheckBox):widget.setChecked(bool(value))
        elif isinstance(widget,QComboBox):
            index=widget.findData(value)
            if index>=0:widget.setCurrentIndex(index)
        else:widget.setValue(value)
    finally:
        widget.blockSignals(old)


def add_field(parent,layout,key,spec,on_change):
    label,minimum,maximum,step,_=spec
    widget=control(parent,key,spec)
    line=QHBoxLayout()
    line.setContentsMargins(0,0,0,0)
    line.setSpacing(5)
    if not isinstance(widget,QCheckBox):
        title=QLabel(label,parent)
        title.setObjectName('aiLabel_'+key)
        title.setMinimumWidth(0)
        title.setMaximumWidth(152)
        title.setToolTip(widget.toolTip())
        line.addWidget(title)
    line.addWidget(widget,1)
    layout.addLayout(line)
    callback=(widget.toggled if isinstance(widget,QCheckBox)
              else widget.valueChanged)
    callback.connect(lambda *_:on_change(key,get(widget)))
    return widget


def install(main):
    sep=main.workbench.separator
    ac=sep._advanced_controls
    advanced=ac['settings']
    vocal=ac['voice']
    home=main.studio_home._floating_manager.sep_expander

    # Selector del MISMO modelo utilizado por Archivo y configuración.
    # Se duplican únicamente los controles de acceso (no los procesos ni
    # las preferencias): ambos reflejan al instante el selector principal.
    from model_registry import record_for,installed
    from separador import MODELS_DIR
    model_row=QHBoxLayout()
    model_row.setContentsMargins(0,0,0,0)
    model_row.setSpacing(5)
    model_title=QLabel('IA instrumentos',advanced)
    model_title.setMinimumWidth(0)
    model_title.setMaximumWidth(122)
    model_row.addWidget(model_title)
    general_choice=QComboBox(advanced)
    general_choice.setMinimumWidth(0)
    general_choice.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    general_choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    general_choice.setMinimumContentsLength(9)
    general_choice.setToolTip('El mismo modelo de IA de Archivo y configuración. Seleccionar aquí cambia el motor real.')
    model_row.addWidget(general_choice,1)
    load_general=QPushButton('Cargar IA…',advanced)
    load_general.setMaximumWidth(94)
    load_general.setToolTip('Abrir el gestor para instalar o activar otros modelos de separación de instrumentos.')
    load_general.clicked.connect(sep.open_model_manager)
    model_row.addWidget(load_general)
    advanced.body.insertLayout(0,model_row)
    general_state=QLabel('',advanced)
    general_state.setObjectName('muted')
    general_state.setWordWrap(True)
    advanced.body.insertWidget(1,general_state)
    import_general=QPushButton('Importar IA externa desde archivo…',advanced)
    import_general.setToolTip('Incorporar un modelo compatible descargado por ti, con sus ficheros de configuración. Nunca sobrescribe los modelos instalados.')
    import_general.setMaximumWidth(275)
    advanced.body.insertWidget(2,import_general)
    general_guard=[False]
    def sync_general_selector(*_):
        if general_guard[0]:return
        general_guard[0]=True
        try:
            names=[sep.profile.itemText(i) for i in range(sep.profile.count())]
            if [general_choice.itemText(i) for i in range(general_choice.count())]!=names:
                general_choice.clear()
                for name in names:general_choice.addItem(name,MODELS.get(name))
            i=sep.profile.currentIndex()
            if general_choice.currentIndex()!=i:general_choice.setCurrentIndex(i)
            filename=MODELS.get(sep.profile.currentText())
            if filename is None:
                state='Separación estéreo L/R · sin IA'
            else:
                rec=record_for(filename)
                ready=installed(rec) if rec else (MODELS_DIR/filename).is_file()
                state=('En uso: '+filename+' · '+('instalado' if ready else 'NO instalado'))
            general_state.setText(state)
            general_state.setToolTip(state)
            general_choice.setEnabled(not sep.busy)
            load_general.setEnabled(not sep.busy)
        finally:general_guard[0]=False
    def choose_general(index):
        if not general_guard[0] and not sep.busy and index>=0:
            sep.profile.setCurrentIndex(index)
    general_choice.currentIndexChanged.connect(choose_general)
    def after_import_general(entry):
        sep.refresh_model_registry()
        target=next((i for i in range(sep.profile.count())
                     if MODELS.get(sep.profile.itemText(i))==entry['filename']),-1)
        if target>=0:sep.profile.setCurrentIndex(target)
        sync_general_selector()
        refresh_model()
    def import_general_files():
        from external_model_import import file_dialog
        file_dialog(advanced,'general',after_import_general)
    import_general.clicked.connect(import_general_files)
    sep.profile.currentIndexChanged.connect(sync_general_selector)
    general_refresh=QTimer(sep)
    general_refresh.setInterval(1200)
    general_refresh.timeout.connect(sync_general_selector)
    general_refresh.start()
    # Demucs/MDX/RoFormer/VR tienen requisitos diferentes. Solo se muestran
    # los controles admitidos por la arquitectura ACTUAL.
    heading=QLabel('',advanced)
    heading.setObjectName('muted')
    heading.setWordWrap(True)
    advanced.body.addWidget(heading)
    families={}
    family_widgets={}
    applying=[False]
    def update_value(key,value):
        if applying[0] or sep.busy:return
        item=safe_value(key,value)
        old=sep.engine_parameters.get(key)
        if old==item:return
        sep.engine_parameters[key]=item
        sep.save_preferences()
        if hasattr(sep,'settings_history'):sep.settings_history.schedule()
        if key=='mdxc_override_model_segment_size':refresh_model()

    def make_group(family,fields):
        panel=QFrame(advanced)
        panel.setObjectName('engineParameters_'+family)
        lay=QVBoxLayout(panel)
        lay.setContentsMargins(0,1,0,2)
        lay.setSpacing(4)
        controls={}
        for key,spec in fields.items():
            controls[key]=add_field(panel,lay,key,spec,update_value)
        families[family]=panel
        family_widgets[family]=controls
        advanced.body.addWidget(panel)
        return panel
    for family,fields in MODEL_FIELDS.items():make_group(family,fields)
    make_group('Común',COMMON_FIELDS)
    reset=QPushButton('Restablecer parámetros de IA',advanced)
    reset.setToolTip('Restaurar los valores de Calidad para el modelo actual; no borra audios')
    reset.setMaximumWidth(245)
    advanced.body.addWidget(reset)

    def refresh_model(*_):
        from PySide6.QtWidgets import QComboBox
        family=family_for_model(MODELS.get(sep.profile.currentText()))
        heading.setText('Motor: '+family+' · se aplican al pulsar Separar pistas')
        applying[0]=True
        try:
            for name,panel in families.items():
                visible=(name==family or (name=='Común' and family in MODEL_FIELDS))
                panel.setVisible(visible)
                if visible:
                    values=merged_settings(family,sep.quality.currentIndex(),
                                           sep.engine_parameters)
                    for key,widget in family_widgets[name].items():
                        put(widget,values.get(key))
                        widget.setEnabled(not sep.busy and (
                            (key!='mdxc_segment_size' or values.get('mdxc_override_model_segment_size',False))
                            and (key!='mp3_bitrate' or sep.export_fmt.currentText().startswith('MP3'))))
            reset.setEnabled(bool(family in MODEL_FIELDS) and not sep.busy)
        finally:applying[0]=False
    def reset_model():
        if sep.busy:return
        family=family_for_model(MODELS.get(sep.profile.currentText()))
        keys=set(MODEL_FIELDS.get(family,{}))|set(COMMON_FIELDS)
        for key in keys:sep.engine_parameters.pop(key,None)
        sep.save_preferences()
        if hasattr(sep,'settings_history'):sep.settings_history.schedule()
        refresh_model()
    reset.clicked.connect(reset_model)
    sep.profile.currentIndexChanged.connect(refresh_model)
    sep.quality.currentIndexChanged.connect(refresh_model)
    sep.export_fmt.currentIndexChanged.connect(refresh_model)
    ac['engine_fields']=family_widgets
    ac['engine_reset']=reset
    ac['engine_family']=heading
    ac['engine_refresh']=refresh_model
    ac['general_model_choice']=general_choice
    ac['general_model_state']=general_state
    ac['general_model_load']=load_general
    ac['general_model_import']=import_general
    ac['general_model_sync']=sync_general_selector
    sep.profile.currentIndexChanged.connect(lambda *_:sync_general_selector())
    sync_general_selector()

    # Vocal: dos modelos MelBand/BS RoFormer, ambos con backend MDXC.
    # El selector Detalle/solapamiento ya existe arriba, se amplió 2..50;
    # aquí se añaden los parámetros MDXC no presentes, más I/O vocal.
    import_vocal=QPushButton('Importar IA vocal externa desde archivo…',vocal)
    import_vocal.setToolTip('Importar un RoFormer/MDXC compatible con su YAML, sin reemplazar los modelos vocales anteriores.')
    import_vocal.setMaximumWidth(320)
    vocal.body.insertWidget(2,import_vocal)
    def import_vocal_files():
        from external_model_import import file_dialog,add_voice_to_choices
        def selected(entry):
            add_voice_to_choices(home,ac['mode'])
            key='external_'+entry['filename']
            index=home.voice_mode.findData(key)
            if index>=0:home.voice_mode.setCurrentIndex(index)
            home.refresh_voice_controls()
            ac['sync']()
        file_dialog(vocal,'vocal',selected)
    import_vocal.clicked.connect(import_vocal_files)
    separator=QLabel('MOTOR VOCAL · RoFormer / MDXC',vocal)
    separator.setObjectName('muted')
    vocal.body.addWidget(separator)
    settings=home.voice_settings
    vocal_fields={}
    field_specs={k:v for k,v in MODEL_FIELDS['MDXC'].items()
                 if k!='mdxc_overlap'}
    field_specs.update({k:v for k,v in COMMON_FIELDS.items()})
    field_specs['normalization']=('Normalizar pico vocal',.10,1.0,.05,'--normalization')
    field_specs['sample_rate']=('Frecuencia vocal (Hz)',44100,48000,3900,'--sample_rate')
    # Normalización y sample_rate no pasan por MODEL_FIELDS: se validan aquí.
    def vocal_changed(key,value):
        if home.voice_task.busy:return
        settings.setValue('engine_'+key,value)
        if key=='mdxc_override_model_segment_size':
            segment=vocal_fields.get('mdxc_segment_size')
            if segment is not None:segment.setEnabled(bool(value))
    for key,spec in field_specs.items():
        widget=add_field(vocal,vocal.body,key,spec,vocal_changed)
        vocal_fields[key]=widget
        raw=settings.value('engine_'+key,
            False if isinstance(spec[1],bool) else
            .90 if key=='normalization' else
            44100 if key=='sample_rate' else
            320 if key=='mp3_bitrate' else
            256 if key=='mdxc_segment_size' else
            1 if key=='mdxc_batch_size' else 0)
        if isinstance(widget,QCheckBox):
            value=str(raw).lower() in ('true','1')
        else:
            try:value=float(raw) if isinstance(spec[1],float) else int(raw)
            except (ValueError,TypeError):value=spec[1]
        put(widget,value)
    vocal_fields['mdxc_segment_size'].setEnabled(bool(
        vocal_fields['mdxc_override_model_segment_size'].isChecked()))
    voice_reset=QPushButton('Restablecer motor vocal',vocal)
    voice_reset.setMaximumWidth(240)
    voice_reset.setToolTip('Restaurar parámetros del motor vocal. No borra los stems.')
    vocal.body.addWidget(voice_reset)
    def restore_voice():
        for key,widget in vocal_fields.items():
            settings.remove('engine_'+key)
            default=(.9 if key=='normalization' else 44100 if key=='sample_rate'
                     else 320 if key=='mp3_bitrate' else 1 if key=='mdxc_batch_size'
                     else 256 if key=='mdxc_segment_size' else False if isinstance(widget,QCheckBox)
                     else 0)
            put(widget,default)
        index=home.voice_detail.findData(8)
        if index>=0:home.voice_detail.setCurrentIndex(index)
        vocal_fields['mdxc_segment_size'].setEnabled(False)
    voice_reset.clicked.connect(restore_voice)
    vocal_fields['mp3_bitrate'].setEnabled(home.voice_format.currentText()=='MP3')
    home.voice_format.currentIndexChanged.connect(lambda _:
        vocal_fields['mp3_bitrate'].setEnabled(home.voice_format.currentText()=='MP3'))
    ac['vocal_fields']=vocal_fields
    ac['vocal_model_import']=import_vocal
    ac['vocal_engine_reset']=voice_reset
    refresh_model()
    return True
