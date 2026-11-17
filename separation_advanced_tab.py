"""Controles avanzados reales del separador integrado.

La ventana flotante y la pestaña utilizan los MISMOS atributos de separación,
el MISMO motor vocal y el MISMO proyecto. No hay procesos de IA duplicados.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QObject, QEvent, QTimer
from PySide6.QtWidgets import (QWidget,QHBoxLayout,QVBoxLayout,QGridLayout,
    QLabel,QComboBox,QPushButton,QCheckBox,QDoubleSpinBox,QSlider,QSizePolicy)
from studio_workspace_cards import SectionCard
from separation_professional_params import ParameterSlider
from vocal_split_stems import MODES,VocalSplitJob


class Reflow(QObject):
    def __init__(self,sep,grid,advanced,vocal):
        super().__init__(sep)
        self.sep=sep
        self.grid=grid
        self.advanced=advanced
        self.vocal=vocal
        self.last=None
    def eventFilter(self,obj,event):
        if obj is self.sep and event.type()==QEvent.Resize:
            QTimer.singleShot(0,self.update)
        return False
    def update(self):
        stacked=self.sep.width()<735
        if stacked==self.last:return
        self.last=stacked
        for card in (self.advanced,self.vocal):self.grid.removeWidget(card)
        self.grid.addWidget(self.advanced,0,0)
        self.grid.addWidget(self.vocal,1 if stacked else 0,0 if stacked else 1)
        self.grid.setColumnStretch(0,1)
        self.grid.setColumnStretch(1,0 if stacked else 1)


def _line(parent,text,widget):
    h=QHBoxLayout()
    h.setContentsMargins(0,0,0,0)
    h.setSpacing(6)
    label=QLabel(text,parent)
    label.setMinimumWidth(0)
    label.setMaximumWidth(112)
    h.addWidget(label)
    widget.setMaximumWidth(150)
    h.addWidget(widget)
    h.addStretch(1)
    return h


def _quantity(card,label,minimum,maximum,value,callback):
    """Deslizante horizontal y lectura, sin controles de tipo spinbox."""
    row=QHBoxLayout()
    row.setContentsMargins(0,0,0,0)
    row.setSpacing(5)
    text=QLabel(label,card)
    text.setMinimumWidth(0)
    text.setMaximumWidth(150)
    row.addWidget(text)
    key='norm_setting' if label.startswith('Normalizar') else 'amp_setting'
    control=ParameterSlider(card,key,(label,minimum,maximum,.01,''))
    control.setValue(value)
    control.valueChanged.connect(callback)
    row.addWidget(control,1)
    return row,control,control.slider


def install(main):
    sep=main.workbench.separator
    expanded=main.studio_home._floating_manager.sep_expander
    advanced=SectionCard("07 · PARÁMETROS AVANZADOS DE IA","layers")
    vocal=SectionCard("08 · VOCES · SOLISTA / COROS","mic")
    for card in (advanced,vocal):
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        card.body.setContentsMargins(8,6,8,6)
        card.body.setSpacing(6)

    def setting(key,value):
        if sep.busy:return
        setattr(sep,key,float(value))
        sep.save_preferences()

    norm_row,norm,norm_slider=_quantity(
        advanced,"Normalizar pico",.1,1.0,sep.norm_setting,
        lambda v:setting("norm_setting",v))
    amp_row,amp,amp_slider=_quantity(
        advanced,"Amplificación mínima",0.,1.,sep.amp_setting,
        lambda v:setting("amp_setting",v))
    advanced.body.addLayout(norm_row)
    advanced.body.addLayout(amp_row)

    rate=ParameterSlider(advanced,'sample_rate',
        ('Frecuencia (Hz)',44100,48000,3900,'--sample_rate'))
    rate.setValue(sep.sample_setting)
    rate.valueChanged.connect(
        lambda v:(setattr(sep,"sample_setting",int(v)),sep.save_preferences())
        if v and not sep.busy else None)
    rate.setToolTip("Frecuencia de salida de los stems IA, vinculada al motor real")
    advanced.body.addLayout(_line(advanced,"Frecuencia (Hz)",rate))

    listen=QComboBox(advanced)
    orig=sep.source_preview.channel_mode
    for i in range(orig.count()):
        listen.addItem(orig.itemText(i),orig.itemData(i))
    listen.setCurrentIndex(orig.currentIndex())
    listen.currentIndexChanged.connect(orig.setCurrentIndex)
    orig.currentIndexChanged.connect(lambda idx:
        listen.setCurrentIndex(idx) if listen.currentIndex()!=idx else None)
    listen.setToolTip("Canales de preescucha original, sincronizados con la ventana ampliada")
    advanced.body.addLayout(_line(advanced,"Escucha original",listen))

    note=QLabel("La calidad y el formato se eligen en «Archivo y configuración».",advanced)
    note.setWordWrap(True)
    note.setObjectName("muted")
    advanced.body.addWidget(note)

    mode=QComboBox(vocal)
    for key,(title,_) in MODES.items():mode.addItem(title,key)
    mode.setCurrentIndex(max(0,mode.findData(expanded.voice_mode.currentData())))
    mode.currentIndexChanged.connect(expanded.voice_mode.setCurrentIndex)
    expanded.voice_mode.currentIndexChanged.connect(lambda i:
        mode.setCurrentIndex(i) if i!=mode.currentIndex() else None)
    vocal.body.addWidget(mode)

    params=QGridLayout()
    params.setHorizontalSpacing(6)
    params.setVerticalSpacing(4)
    detail=ParameterSlider(vocal,'mdxc_overlap',
        ('Solapamiento',2,50,1,'--mdxc_overlap'))
    detail.setValue(expanded.voice_detail.currentData() or 8)
    detail.valueChanged.connect(lambda v:
        expanded.voice_detail.setCurrentIndex(expanded.voice_detail.findData(int(v)))
        if expanded.voice_detail.findData(int(v))>=0 else None)
    expanded.voice_detail.currentIndexChanged.connect(lambda i:
        detail.setValue(expanded.voice_detail.itemData(i))
        if i>=0 and detail.value()!=expanded.voice_detail.itemData(i) else None)
    fmt=QComboBox(vocal)
    for i in range(expanded.voice_format.count()):
        fmt.addItem(expanded.voice_format.itemText(i))
    fmt.setCurrentIndex(expanded.voice_format.currentIndex())
    fmt.currentIndexChanged.connect(expanded.voice_format.setCurrentIndex)
    expanded.voice_format.currentIndexChanged.connect(lambda i:
        fmt.setCurrentIndex(i) if fmt.currentIndex()!=i else None)
    boost=ParameterSlider(vocal,'vocal_boost',
        ('Refuerzo',0.,.30,.01,'--amplification'))
    boost.setValue(expanded.voice_boost.value())
    boost.valueChanged.connect(expanded.voice_boost.setValue)
    expanded.voice_boost.valueChanged.connect(lambda v:
        boost.setValue(v) if boost.value()!=v else None)
    auto=QCheckBox("Activar",vocal)
    auto.setChecked(expanded.voice_auto_preview.isChecked())
    auto.toggled.connect(expanded.voice_auto_preview.setChecked)
    expanded.voice_auto_preview.toggled.connect(auto.setChecked)
    for i,(label,control) in enumerate((
            ("Detalle",detail),("Formato",fmt),
            ("Refuerzo",boost),("Preescucha",auto))):
        column=i%2
        row=i//2
        title=QLabel("Solapamiento" if label=="Detalle" else label,vocal)
        title.setMaximumWidth(92)
        title.setMinimumWidth(0)
        if isinstance(control,ParameterSlider):
            control.setMinimumWidth(112)
            control.setMaximumWidth(156)
        params.addWidget(title,row,column*2)
        params.addWidget(control,row,column*2+1)
    params.setColumnStretch(1,0)
    params.setColumnStretch(3,0)
    params.setColumnStretch(4,1)
    vocal.body.addLayout(params)

    actions=QHBoxLayout()
    actions.setContentsMargins(0,0,0,0)
    actions.setSpacing(5)
    start=QPushButton("Separar voces",vocal)
    start.setObjectName("primary")
    start.clicked.connect(expanded.start_vocal_split)
    install_button=QPushButton("Instalar IA",vocal)
    def load_or_change_vocal():
        if expanded.voice_task.busy:return
        if VocalSplitJob.installed(mode.currentData()):
            # El modelo activo ya está cargado; ofrece los modelos
            # vocales alternativos sin descargar nada de nuevo.
            mode.showPopup()
        else:
            expanded.install_vocal_model()
    install_button.clicked.connect(load_or_change_vocal)
    stop=QPushButton("■",vocal)
    stop.setToolTip("Cancelar separación vocal")
    stop.setMaximumWidth(35)
    stop.clicked.connect(expanded.voice_task.stop)
    actions.addWidget(start,1)
    actions.addWidget(stop)
    vocal.body.addLayout(actions)

    # Modelo vocal visible y seleccionable; el mismo objeto controla el
    # proceso de la ventana flotante. No se instala ni ejecuta un clon.
    vocal.body.removeWidget(mode)
    model_line=QHBoxLayout()
    model_line.setContentsMargins(0,0,0,0)
    model_line.setSpacing(5)
    model_caption=QLabel('Modelo vocal',vocal)
    model_caption.setMaximumWidth(86)
    model_line.addWidget(model_caption)
    mode.setMinimumWidth(0)
    mode.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    mode.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    mode.setMinimumContentsLength(8)
    model_line.addWidget(mode,1)
    install_button.setMinimumWidth(73)
    install_button.setMaximumWidth(98)
    install_button.setToolTip('Cargar otro modelo vocal de la lista o instalar el seleccionado si todavía no está en el equipo.')
    model_line.addWidget(install_button)
    vocal.body.insertLayout(0,model_line)
    vocal_model_state=QLabel('',vocal)
    vocal_model_state.setWordWrap(True)
    vocal_model_state.setObjectName('muted')
    vocal.body.insertWidget(1,vocal_model_state)

    status=QLabel("",vocal)
    status.setWordWrap(True)
    status.setObjectName("muted")
    vocal.body.addWidget(status)
    output_buttons=[]
    outputs=QHBoxLayout()
    for i in range(2):
        button=QPushButton("▶ Voz "+str(i+1),vocal)
        button.clicked.connect(lambda checked=False,index=i:
                               expanded.preview_vocal_result(index))
        button.hide()
        outputs.addWidget(button)
        output_buttons.append(button)
    vocal.body.addLayout(outputs)

    def sync():
        # Solo actualización de lectura: no generar clics ni escrituras.
        for widget,key in ((norm,"norm_setting"),(amp,"amp_setting")):
            v=round(float(getattr(sep,key)),2)
            if not widget.slider.isSliderDown() and abs(widget.value()-v)>.001:
                blocked=widget.blockSignals(True)
                widget.setValue(v)
                widget.blockSignals(blocked)
        if not rate.slider.isSliderDown() and sep.sample_setting!=rate.value():
            blocked=rate.blockSignals(True)
            rate.setValue(sep.sample_setting)
            rate.blockSignals(blocked)
        ready=VocalSplitJob.installed(mode.currentData())
        active=bool(expanded.home._sep_listen.available().get("Voces"))
        busy=expanded.voice_task.busy
        install_button.setEnabled(not busy)
        start.setEnabled(ready and active and not busy)
        stop.setEnabled(busy)
        mode.setEnabled(not busy)
        install_button.setText("Cambiar IA…" if ready else "Instalar IA")
        filename=MODES.get(mode.currentData(),('', ''))[1]
        model_summary=('En uso: '+filename+' · '+('instalado' if ready else 'NO instalado'))
        vocal_model_state.setText(model_summary)
        vocal_model_state.setToolTip(model_summary)
        if busy:
            status.setText(expanded.voice_status.text())
        elif not ready:
            status.setText("Modelo vocal no instalado; utiliza «Instalar IA».")
        elif not active:
            status.setText("IA preparada. Primero separa la pista Voces.")
        else:
            status.setText("Modelo vocal preparado. Puedes separar principal/coros o voces masculinas/femeninas.")
        for i,button in enumerate(output_buttons):
            paths=getattr(expanded,"_voice_paths",[])
            path=paths[i] if i<len(paths) else None
            button.setVisible(bool(path and path.is_file()))
            if path:
                button.setText(expanded.voice_results[i].text())
                button.setToolTip(str(path))
        for widget in (rate,norm,amp,listen):
            widget.setEnabled(not sep.busy)
        norm_slider.setEnabled(not sep.busy)
        amp_slider.setEnabled(not sep.busy)

    timer=QTimer(sep)
    timer.setInterval(650)
    timer.timeout.connect(sync)
    timer.start()
    # Actualizar el nombre/estado del modelo EN EL MISMO CLIC; el
    # refresco periódico es solo un respaldo para descargas terminadas.
    mode.currentIndexChanged.connect(sync)
    expanded.voice_task.busyChanged.connect(lambda *_:sync())
    expanded.voice_task.status.connect(lambda msg:status.setText(msg))
    sync()

    # Dos tarjetas nuevas debajo de las opciones base (con scroll, sin
    # invadir la columna de resultados). En pantallas muy estrechas apilar.
    holder=QWidget(sep._compact_canvas)
    holder.setObjectName("separationAdvancedCards")
    grid=QGridLayout(holder)
    grid.setContentsMargins(7,0,7,4)
    grid.setHorizontalSpacing(7)
    grid.setVerticalSpacing(7)
    root=sep._compact_canvas.layout()
    root.addWidget(holder)
    reflow=Reflow(sep,grid,advanced,vocal)
    sep.installEventFilter(reflow)
    sep._advanced_reflow=reflow
    reflow.update()

    # La pestaña sí debe ofrecer ajustes completos. El antiguo botón
    # «Parámetros IA» abría una ventana modal; ahora lleva directamente
    # a los controles de esta misma pestaña.
    button=sep.stem_parameters_btn
    try:button.clicked.disconnect()
    except RuntimeError:pass
    button.setText("Avanzado · IA y voces ↓")
    button.setToolTip("Abrir los controles de IA y voces en esta misma pestaña.")
    button.clicked.connect(lambda:
        sep._compact_scroller.ensureWidgetVisible(holder,14,20))

    sep._advanced_controls={"holder":holder,"settings":advanced,"voice":vocal,
                            "norm":norm,"amp":amp,"rate":rate,"listen":listen,
                            "mode":mode,"detail":detail,"format":fmt,"boost":boost,
                            "autoplay":auto,"install":install_button,
                            "start":start,"stop":stop,"status":status,
                            "outputs":output_buttons,"sync":sync,
                            "vocal_model_state":vocal_model_state,
                            "vocal_model_load":install_button}
    return sep._advanced_controls
