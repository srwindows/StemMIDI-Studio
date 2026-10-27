"""Vista ampliada de la tarjeta de separación: controles vinculados al motor real.

La tarjeta Inicio no se clona: al ampliar se cambia la presentación interna
y todos los ajustes se aplican a los mismos widgets/presets de origen.
"""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (
 QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,
 QPushButton,QComboBox,QLineEdit,QSlider,QDoubleSpinBox,QCheckBox,
 QProgressBar,QSizePolicy
)

LABELS=("Voces","Batería","Bajo","Guitarra","Piano","Otros","Viento")
MAP={"Voces":"Voz","Batería":"Batería","Bajo":"Bajo","Guitarra":"Guitarra",
     "Piano":"Piano","Otros":"Otros","Viento":"Viento"}

def children_of(layout):
    for i in range(layout.count()):
        item=layout.itemAt(i)
        if item.widget() is not None:
            yield item.widget()
        if item.layout() is not None:
            yield from children_of(item.layout())

def head(text):
    w=QLabel(text)
    w.setObjectName("floatingTitle")
    w.setMinimumHeight(24)
    return w

def panel():
    w=QFrame()
    w.setObjectName("floatPanel")
    lay=QVBoxLayout(w)
    lay.setContentsMargins(12,9,12,10)
    lay.setSpacing(6)
    return w,lay

def row(*elements):
    lay=QHBoxLayout();lay.setContentsMargins(0,0,0,0);lay.setSpacing(7)
    for e in elements:
        if isinstance(e,int):lay.addStretch(e)
        else:
            if isinstance(e,QLabel):
                e.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Preferred)
                e.setMinimumWidth(max(68,e.minimumWidth()))
            lay.addWidget(e,1 if isinstance(e,QLineEdit) else 0)
    if not any(isinstance(e,QLineEdit) for e in elements):
        lay.addStretch(1)
    return lay

def dual_spin(text,initial,low,high,fn):
    box=QWidget()
    lay=QHBoxLayout(box)
    lay.setContentsMargins(0,0,0,0)
    lay.setSpacing(7)
    title=QLabel(text)
    title.setMinimumWidth(137)
    slider=QSlider(Qt.Horizontal)
    slider.setRange(round(low*100),round(high*100))
    num=QDoubleSpinBox()
    num.setDecimals(2);num.setSingleStep(.01)
    num.setRange(low,high);num.setValue(initial)
    num.setFixedWidth(74)
    slider.setValue(round(initial*100))
    slider.valueChanged.connect(lambda v:num.setValue(v/100))
    num.valueChanged.connect(lambda v:(slider.setValue(round(v*100)),fn(v)))
    lay.addWidget(title)
    lay.addWidget(slider,1)
    lay.addWidget(num)
    return box,num

class ExpandedSeparator:
    def __init__(self,home):
        self.home=home
        self.sep=home.workbench.separator
        self.card=home.sep_card
        self.hidden_original=[]
        self.root=QWidget(self.card)
        self.root.setObjectName("separationFloatBody")
        self.root.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        base=QVBoxLayout(self.root)
        base.setContentsMargins(8,7,8,8)
        base.setSpacing(8)

        # Primera fila: presets guardados y archivo de entrada real.
        top,one=panel()
        one.addWidget(head("01 · ARCHIVO, PRESETS Y MODELO IA"))
        self.preset=QComboBox()
        self.preset.setMinimumWidth(260)
        self.preset.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        one.addLayout(row(QLabel("Preset"),self.preset))
        self.preset_name=QLineEdit()
        self.preset_name.setPlaceholderText("Nombre de preset propio")
        save=QPushButton("Guardar")
        remove=QPushButton("Borrar")
        one.addLayout(row(self.preset_name,save,remove))
        self.source=QLineEdit()
        self.source.setPlaceholderText("Selecciona un archivo de audio…")
        self.choose=QPushButton("Importar…")
        one.addLayout(row(QLabel("Audio"),self.source,self.choose))
        self.models=QComboBox()
        self.models.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.models.setMinimumWidth(260)
        load=QPushButton("Cargar modelo IA…")
        one.addLayout(row(QLabel("Modelo"),self.models,load))
        base.addWidget(top,0)

        # Segunda fila: stems y ajustes de calidad auténticos.
        middle=QHBoxLayout()
        middle.setSpacing(9)
        left,one=panel()
        one.addWidget(head("02 · PISTAS A EXTRAER"))
        self.all_stems=QCheckBox("Todos los instrumentos disponibles")
        one.addWidget(self.all_stems)
        controls=QGridLayout()
        controls.setSpacing(6)
        self.stems={}
        for i,name in enumerate(LABELS):
            chk=QCheckBox(name)
            self.stems[name]=chk
            controls.addWidget(chk,i//2,i%2)
        one.addLayout(controls)
        self.model_notice=QLabel("La disponibilidad depende del modelo de IA seleccionado.")
        self.model_notice.setWordWrap(True)
        self.model_notice.setObjectName("muted")
        one.addWidget(self.model_notice)
        middle.addWidget(left,44)

        right,one=panel()
        one.addWidget(head("03 · PARÁMETROS DE SEPARACIÓN"))
        self.norm_widget,self.norm=dual_spin("Normalizar pico",getattr(self.sep,"norm_setting",.9),.1,1.0,
                                           lambda v:self.set_setting("norm_setting",v))
        self.amp_widget,self.amp=dual_spin("Amplificación mínima",getattr(self.sep,"amp_setting",0.0),0.0,1.0,
                                         lambda v:self.set_setting("amp_setting",v))
        one.addWidget(self.norm_widget)
        one.addWidget(self.amp_widget)
        self.quality=QComboBox()
        self.fmt=QComboBox()
        self.rate=QComboBox()
        self.rate.addItems(("44100","48000"))
        self.listen=QComboBox()
        self.listen.addItems(("Estéreo","Mono (L+R)","Solo izquierdo","Solo derecho"))
        one.addLayout(row(QLabel("Calidad"),self.quality))
        one.addLayout(row(QLabel("Formato"),self.fmt))
        one.addLayout(row(QLabel("Frecuencia"),self.rate))
        one.addLayout(row(QLabel("Escucha"),self.listen))
        middle.addWidget(right,56)
        base.addLayout(middle,2)

        # Tercera fila: procesado real y progreso observable.
        bottom=QHBoxLayout()
        bottom.setSpacing(9)
        proc,one=panel()
        one.addWidget(head("04 · PROCESAR AUDIO"))
        self.run=QPushButton("▶ Separar pistas")
        self.run.setObjectName("primary")
        self.cancel=QPushButton("Detener")
        one.addLayout(row(self.run,self.cancel))
        self.status=QLabel("Modelo preparado")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        one.addWidget(self.status)
        self.progress=QProgressBar()
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        one.addWidget(self.progress)
        bottom.addWidget(proc,45)
        process,one=panel()
        one.addWidget(head("05 · ESTADO Y PROGRESO"))
        self.progress_state=QLabel("En espera")
        self.progress_state.setWordWrap(True)
        one.addWidget(self.progress_state)
        self.stem_status=QLabel("Los porcentajes de los stems no se inventan.")
        self.stem_status.setObjectName("muted")
        self.stem_status.setWordWrap(True)
        one.addWidget(self.stem_status)
        bottom.addWidget(process,55)
        base.addLayout(bottom,1)
        self.root.hide()
        self.card.inner.insertWidget(0,self.root,1)

        # Presets, modelos y botones están conectados a la implementación real.
        source_presets=self.sep.presets
        self.preset.currentIndexChanged.connect(lambda idx:
            source_presets.choices.setCurrentIndex(idx) if idx>=0 else None)
        source_presets.choices.currentIndexChanged.connect(
            lambda _:self.refresh_presets())
        save.clicked.connect(self.save_preset)
        remove.clicked.connect(self.remove_preset)
        self.choose.clicked.connect(self.sep.choose_input)
        self.source.editingFinished.connect(self.set_source)
        self.models.currentIndexChanged.connect(self.set_model)
        load.clicked.connect(self.sep.open_model_manager)
        self.quality.currentIndexChanged.connect(lambda idx:self.sep.quality.setCurrentIndex(idx))
        self.fmt.currentIndexChanged.connect(lambda idx:self.sep.export_fmt.setCurrentIndex(idx))
        self.rate.currentTextChanged.connect(self.set_rate)
        self.listen.currentIndexChanged.connect(lambda idx:
            self.sep.source_preview.channel_mode.setCurrentIndex(idx))
        self.all_stems.toggled.connect(self.select_all)
        for name,cb in self.stems.items():
            cb.toggled.connect(lambda state,key=name:self.select_stem(key,state))
        self.run.clicked.connect(self.start)
        self.cancel.clicked.connect(self.sep.stop)
        self.refresh_timer=QTimer(self.root)
        self.refresh_timer.setInterval(850)
        self.refresh_timer.timeout.connect(self.refresh)
        self._updating=False

    def save_preset(self):
        strip=self.sep.presets
        strip.name.setText(self.preset_name.text())
        strip.save_custom()
        self.refresh_presets()

    def remove_preset(self):
        strip=self.sep.presets
        strip.choices.setCurrentIndex(self.preset.currentIndex())
        strip.delete_custom()
        self.refresh_presets()

    def refresh_presets(self):
        strip=self.sep.presets
        if (self.preset.count()==strip.choices.count() and
                all(self.preset.itemText(i)==strip.choices.itemText(i)
                    for i in range(strip.choices.count()))):
            if self.preset.currentIndex()!=strip.choices.currentIndex() and not self.preset.view().isVisible():
                block=self.preset.blockSignals(True)
                self.preset.setCurrentIndex(strip.choices.currentIndex())
                self.preset.blockSignals(block)
            return
        was=self.preset.blockSignals(True)
        self.preset.clear()
        for i in range(strip.choices.count()):
            self.preset.addItem(strip.choices.itemText(i),strip.choices.itemData(i))
        self.preset.setCurrentIndex(strip.choices.currentIndex())
        self.preset.blockSignals(was)

    def set_setting(self,name,value):
        setattr(self.sep,name,float(value))
        self.sep.save_preferences()

    def set_rate(self,value):
        if value:
            self.sep.sample_setting=int(value)
            self.sep.save_preferences()

    def set_source(self):
        path=self.source.text().strip()
        if path and Path(path).is_file():
            self.sep.on_import_selected(path)

    def set_model(self,index):
        if not self._updating and index>=0:
            actual=self.models.itemData(index)
            if actual:
                self.sep.profile.setCurrentText(actual)
                self.home._sync_stem_capabilities()

    def select_all(self,value):
        if self._updating:return
        for name,box in self.stems.items():
            if box.isEnabled():box.setChecked(value)

    def select_stem(self,name,value):
        if self._updating:return
        original=self.home.stem_checks.get(name)
        if original is not None:
            original.setChecked(value)
        actual=self.sep.stem_checks.get({"Voces":"Voz"}.get(name,name))
        if actual is not None and actual.isEnabled():
            actual.setChecked(value)
        self._updating=True
        active=[box for box in self.stems.values() if box.isEnabled()]
        self.all_stems.setChecked(bool(active) and all(box.isChecked() for box in active))
        self._updating=False

    def start(self):
        path=Path(self.sep.file_edit.text().strip())
        if not path.is_file():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self.root,"Archivo necesario",
                "Selecciona primero el audio de origen en este mismo panel.")
            return
        self.sep.start_separation()

    def refresh(self):
        if not self.root.isVisible():return
        self._updating=True
        try:
            self.refresh_presets()
            current=self.sep.profile.currentText()
            if (self.models.count()!=self.sep.profile.count()
                    or any(self.models.itemText(i)!=self.sep.profile.itemText(i)
                           for i in range(self.sep.profile.count()))):
                block=self.models.blockSignals(True)
                self.models.clear()
                for i in range(self.sep.profile.count()):
                    text=self.sep.profile.itemText(i)
                    self.models.addItem(text,text)
                self.models.blockSignals(block)
            if self.models.currentText()!=current and not self.models.view().isVisible():
                block=self.models.blockSignals(True)
                self.models.setCurrentText(current)
                self.models.blockSignals(block)
            for orig,target in ((self.sep.quality,self.quality),(self.sep.export_fmt,self.fmt)):
                if (target.count()!=orig.count() or
                        any(target.itemText(i)!=orig.itemText(i)
                            for i in range(orig.count()))):
                    block=target.blockSignals(True)
                    target.clear()
                    for i in range(orig.count()):
                        target.addItem(orig.itemText(i),orig.itemData(i))
                    target.blockSignals(block)
                if not target.view().isVisible() and target.currentIndex()!=orig.currentIndex():
                    block=target.blockSignals(True)
                    target.setCurrentIndex(orig.currentIndex())
                    target.blockSignals(block)
            if not self.source.hasFocus() and self.source.text()!=self.sep.file_edit.text():
                self.source.setText(self.sep.file_edit.text())
            self.rate.blockSignals(True)
            self.rate.setCurrentText(str(self.sep.sample_setting))
            self.rate.blockSignals(False)
            self.listen.blockSignals(True)
            self.listen.setCurrentIndex(self.sep.source_preview.channel_mode.currentIndex())
            self.listen.blockSignals(False)
            from separador import MODELS
            from separation_pro_controls import stems_for_model
            allowed=stems_for_model(MODELS.get(current))
            for name,box in self.stems.items():
                stem=MAP[name]
                permitted=(stem in allowed)
                box.setEnabled(permitted and not self.sep.busy)
                source=self.sep.stem_checks.get(stem)
                box.setChecked(bool(source and source.isChecked()) if permitted else False)
            live=[c for c in self.stems.values() if c.isEnabled()]
            self.all_stems.setChecked(bool(live) and all(c.isChecked() for c in live))
            self.norm.blockSignals(True);self.norm.setValue(self.sep.norm_setting);self.norm.blockSignals(False)
            self.amp.blockSignals(True);self.amp.setValue(self.sep.amp_setting);self.amp.blockSignals(False)
            self.model_notice.setText(
                "Modelo compatible: "+", ".join(allowed)+". No se generan pistas inexistentes.")
            self.status.setText(self.sep.progress_label.text())
            self.progress.setRange(self.sep.progress.minimum(),self.sep.progress.maximum())
            self.progress.setValue(self.sep.progress.value())
            self.run.setEnabled(not self.sep.busy)
            self.cancel.setEnabled(self.sep.busy)
            self.choose.setEnabled(not self.sep.busy)
            self.models.setEnabled(not self.sep.busy)
            self.progress_state.setText(
                ("Separando audio" if self.sep.busy else "En espera")+
                " · "+self.sep.elapsed.text())
            requested=getattr(self.sep,"active_request",[])
            found={__import__("separation_pro_controls").instrument_for(p)
                   for p in self.sep.latest_outputs}
            self.stem_status.setText(" · ".join(
                f"{stem}: {'Listo' if stem in found else 'En proceso' if self.sep.busy else 'Pendiente'}"
                for stem in (requested or allowed)))
        finally:
            self._updating=False

    def expand(self):
        self.hidden_original=[
            w for w in children_of(self.card.inner)
            if w is not self.root and w.isVisible()
        ]
        for w in self.hidden_original:w.hide()
        self.root.show()
        self.refresh_timer.start()
        self.refresh()
    def collapse(self):
        self.refresh_timer.stop()
        self.root.hide()
        for w in self.hidden_original:w.show()
        self.hidden_original=[]
