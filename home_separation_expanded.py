"""Vista ampliada de la tarjeta de separación: controles vinculados al motor real.

La tarjeta Inicio no se clona: al ampliar se cambia la presentación interna
y todos los ajustes se aplican a los mismos widgets/presets de origen.
"""
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSettings
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

        # Cabecera compacta: 3 filas, sin perder preset, archivo ni modelo.
        top,one=panel()
        one.setContentsMargins(9,6,9,6)
        one.setSpacing(3)
        one.addWidget(head("01 · ARCHIVO, PRESETS Y MODELO"))
        self.preset=QComboBox()
        self.preset.setMinimumWidth(95)
        self.preset.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed)
        self.preset_name=QLineEdit()
        self.preset_name.setPlaceholderText("Nombre preset")
        save=QPushButton("Guardar")
        remove=QPushButton("Borrar")
        for button in (save,remove):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        preset_row=QHBoxLayout()
        preset_row.setContentsMargins(0,0,0,0)
        preset_row.setSpacing(4)
        preset_row.addWidget(QLabel("Preset"))
        preset_row.addWidget(self.preset,2)
        preset_row.addWidget(self.preset_name,3)
        preset_row.addWidget(save)
        preset_row.addWidget(remove)
        one.addLayout(preset_row)
        self.source=QLineEdit()
        self.source.setPlaceholderText("Selecciona un audio…")
        self.source.setToolTip("Ruta del audio de origen")
        self.choose=QPushButton("Importar…")
        audio_row=QHBoxLayout()
        audio_row.setContentsMargins(0,0,0,0)
        audio_row.setSpacing(4)
        audio_row.addWidget(QLabel("Audio"))
        audio_row.addWidget(self.source,1)
        audio_row.addWidget(self.choose)
        one.addLayout(audio_row)
        self.models=QComboBox()
        self.models.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.models.setMinimumWidth(95)
        load=QPushButton("Cargar IA…")
        model_row=QHBoxLayout()
        model_row.setContentsMargins(0,0,0,0)
        model_row.setSpacing(4)
        model_row.addWidget(QLabel("Modelo"))
        model_row.addWidget(self.models,1)
        model_row.addWidget(load)
        one.addLayout(model_row)

        # Segunda etapa vocal, en lugar de la lista de stems duplicada:
        # las seis casillas del VU inferior SON ahora mute en tiempo real.
        from vocal_split_stems import VocalSplitJob,MODES
        self.voice_task=VocalSplitJob(self.root)
        top_area=QHBoxLayout()
        top_area.setSpacing(8)
        top_area.addWidget(top,46)
        stems_panel,stems_body=panel()
        stems_body.setContentsMargins(9,6,9,6)
        stems_body.setSpacing(3)
        stems_body.addWidget(head("VOCES · SOLISTA / COROS"))
        self.voice_settings=QSettings("StemMIDI Studio","SeparacionVocal")
        self.voice_input=QLabel("Entrada: Voces del proyecto",stems_panel)
        self.voice_input.setObjectName("muted")
        stems_body.addWidget(self.voice_input)
        # El estado del origen permanece en el tooltip para dejar altura
        # a los resultados sin solapar controles en un panel compacto.
        self.voice_input.hide()
        self.voice_mode=QComboBox(stems_panel)
        for key,(name,filename) in MODES.items():
            self.voice_mode.addItem(name,key)
        self.voice_mode.setToolTip(
            "Principal/coros: modelo Karaoke sobre la voz extraída. "
            "Masculina/femenina: separa voces por timbre; no garantiza cada cantante.")
        stems_body.addWidget(self.voice_mode)
        # Parámetros REALES, conectados a audio-separator, no decorativos.
        params=QHBoxLayout()
        params.setContentsMargins(0,0,0,0)
        params.setSpacing(4)
        params.addWidget(QLabel("Detalle"))
        self.voice_detail=QComboBox(stems_panel)
        self.voice_detail.addItem("Normal",8)
        self.voice_detail.addItem("Alto",16)
        self.voice_detail.setToolTip(
            "Solapamiento MDXC: alto procesa más ventanas y tarda más.")
        self.voice_detail.setFixedWidth(83)
        params.addWidget(self.voice_detail)
        params.addWidget(QLabel("Formato"))
        self.voice_format=QComboBox(stems_panel)
        for fmt in ("FLAC","WAV","MP3"):self.voice_format.addItem(fmt)
        self.voice_format.setFixedWidth(76)
        params.addWidget(self.voice_format)
        params.addWidget(QLabel("Refuerzo"))
        self.voice_boost=QDoubleSpinBox(stems_panel)
        self.voice_boost.setDecimals(2)
        self.voice_boost.setSingleStep(.05)
        self.voice_boost.setRange(0.,.30)
        self.voice_boost.setToolTip(
            "Amplificación mínima de audio (--amplification), NO identifica cantantes.")
        self.voice_boost.setFixedWidth(65)
        params.addWidget(self.voice_boost)
        self.voice_auto_preview=QCheckBox("Auto",stems_panel)
        self.voice_auto_preview.setToolTip(
            "Al completar, reproducir automáticamente la primera pista vocal.")
        params.addWidget(self.voice_auto_preview)
        stems_body.addLayout(params)
        saved_mode=self.voice_settings.value("mode","lead_backing")
        index=self.voice_mode.findData(saved_mode)
        if index>=0:self.voice_mode.setCurrentIndex(index)
        quality_index=self.voice_detail.findData(
            int(self.voice_settings.value("overlap",8)))
        if quality_index>=0:self.voice_detail.setCurrentIndex(quality_index)
        fmt_index=self.voice_format.findText(
            str(self.voice_settings.value("format","FLAC")))
        if fmt_index>=0:self.voice_format.setCurrentIndex(fmt_index)
        self.voice_boost.setValue(float(self.voice_settings.value("boost",0.)))
        self.voice_auto_preview.setChecked(
            str(self.voice_settings.value("autoplay","false")).lower()=="true")
        for control in (self.voice_mode,self.voice_detail,self.voice_format):
            control.currentIndexChanged.connect(self.save_voice_preferences)
        self.voice_boost.valueChanged.connect(self.save_voice_preferences)
        self.voice_auto_preview.toggled.connect(self.save_voice_preferences)
        controls=QHBoxLayout()
        controls.setContentsMargins(0,0,0,0)
        controls.setSpacing(3)
        self.voice_start=QPushButton("Separar voces",stems_panel)
        self.voice_start.setObjectName("primary")
        controls.addWidget(self.voice_start,1)
        self.voice_install=QPushButton("IA",stems_panel)
        self.voice_install.setToolTip("Instalar el modelo vocal elegido cuando no exista.")
        controls.addWidget(self.voice_install)
        self.voice_cancel=QPushButton("■",stems_panel)
        self.voice_cancel.setFixedWidth(28)
        self.voice_cancel.setToolTip("Detener la separación vocal.")
        controls.addWidget(self.voice_cancel)
        stems_body.addLayout(controls)
        self.voice_status=QLabel("",stems_panel)
        self.voice_status.setObjectName("muted")
        self.voice_status.setWordWrap(False)
        self.voice_status.setFixedHeight(16)
        self.voice_status.setToolTip("Estado y progreso de la IA vocal")
        self.voice_results=[]
        result_row=QHBoxLayout()
        result_row.setContentsMargins(0,0,0,0)
        result_row.setSpacing(4)
        result_row.addWidget(self.voice_status,1)
        for i in range(2):
            button=QPushButton("▶ Voz "+str(i+1),stems_panel)
            button.setFixedHeight(21)
            button.setToolTip("Escuchar pista vocal separada, sin alterar la original.")
            button.hide()
            result_row.addWidget(button,1)
            button.clicked.connect(
                lambda checked=False,slot=i:self.preview_vocal_result(slot))
            self.voice_results.append(button)
        stems_body.addLayout(result_row)
        self.voice_note=QLabel("Voces del mismo género / ≥3: IA especializada.",stems_panel)
        self.voice_note.setObjectName("muted")
        self.voice_note.setToolTip(
            "Esta IA no separa automáticamente cantantes del mismo género "
            "ni tres o más voces solapadas.")
        stems_body.addWidget(self.voice_note)
        self.voice_note.hide()
        stems_panel.setToolTip(
            "La separación no identifica automáticamente a cada cantante "
            "cuando hay tres o más voces o dos cantantes del mismo género.")
        self.voice_start.clicked.connect(self.start_vocal_split)
        self.voice_install.clicked.connect(self.install_vocal_model)
        self.voice_cancel.clicked.connect(self.voice_task.stop)
        self.voice_task.status.connect(self.voice_status.setText)
        self.voice_task.busyChanged.connect(
            lambda busy:self.refresh_voice_controls())
        self.voice_task.ready.connect(self.vocal_results_ready)
        self.voice_mode.currentIndexChanged.connect(
            lambda _:self.refresh_voice_controls())
        stems_panel.setMinimumHeight(184)
        top_area.addWidget(stems_panel,54)
        base.addLayout(top_area,0)

        # Segunda fila: stems y ajustes de calidad auténticos.
        middle=QHBoxLayout()
        middle.setSpacing(9)
        left,one=panel()
        one.setSpacing(3)
        one.addWidget(head("02 · PISTAS A EXTRAER"))
        self.all_stems=QCheckBox("Todos los instrumentos disponibles")
        one.addWidget(self.all_stems)
        controls=QGridLayout()
        controls.setHorizontalSpacing(5)
        controls.setVerticalSpacing(0)
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
        options_one=QHBoxLayout()
        options_one.setSpacing(6)
        options_one.addWidget(QLabel("Calidad"))
        options_one.addWidget(self.quality,1)
        options_one.addWidget(QLabel("Formato"))
        options_one.addWidget(self.fmt,1)
        one.addLayout(options_one)
        options_two=QHBoxLayout()
        options_two.setSpacing(6)
        options_two.addWidget(QLabel("Frecuencia"))
        options_two.addWidget(self.rate,1)
        options_two.addWidget(QLabel("Escucha"))
        options_two.addWidget(self.listen,1)
        one.addLayout(options_two)
        middle.addWidget(right,56)
        base.addLayout(middle,1)

        # Tercera fila: procesado real y progreso observable.
        bottom=QHBoxLayout()
        bottom.setSpacing(9)
        proc,one=panel()
        one.setContentsMargins(10,5,10,5)
        one.setSpacing(3)
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
        one.setContentsMargins(10,5,10,5)
        one.setSpacing(3)
        one.addWidget(head("05 · ESTADO Y PROGRESO"))
        self.progress_state=QLabel("En espera")
        self.progress_state.setWordWrap(True)
        one.addWidget(self.progress_state)
        self.stem_status=QLabel("Los porcentajes de los stems no se inventan.")
        self.stem_status.setObjectName("muted")
        self.stem_status.setWordWrap(True)
        one.addWidget(self.stem_status)
        bottom.addWidget(process,55)
        base.addLayout(bottom,0)
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

    def save_voice_preferences(self,*_):
        self.voice_settings.setValue("mode",self.voice_mode.currentData())
        self.voice_settings.setValue("overlap",self.voice_detail.currentData())
        self.voice_settings.setValue("format",self.voice_format.currentText())
        self.voice_settings.setValue("boost",self.voice_boost.value())
        self.voice_settings.setValue("autoplay",self.voice_auto_preview.isChecked())

    def refresh_voice_controls(self):
        from vocal_split_stems import VocalSplitJob
        mode=self.voice_mode.currentData()
        voice=self.home._sep_listen.available().get("Voces")
        self.voice_input.setText(
            "Voz separada disponible" if voice is not None
            else "Primero extrae Voces")
        self.voice_mode.setToolTip(
            ("Origen: "+str(voice) if voice else "Primero extrae Voces")
            +" · El modelo RoFormer separa principal y resto vocal; "
            "no garantiza identidades individuales.")
        ready=bool(mode and VocalSplitJob.installed(mode))
        busy=self.voice_task.busy
        self.voice_mode.setEnabled(not busy)
        self.recover_voice_results(mode,busy)
        self.voice_start.setEnabled(bool(voice) and ready and not busy)
        self.voice_install.setEnabled(bool(mode) and not ready and not busy)
        self.voice_install.setText("IA ✓" if ready else "Instalar IA")
        self.voice_cancel.setEnabled(busy)
        state=(mode,ready,bool(voice))
        if not busy and getattr(self,"_vocal_status_state",None)!=state:
            self._vocal_status_state=state
            self.voice_status.setText(
                "Modelo preparado" if ready
                else "Modelo no instalado · pulsa Instalar IA")

    def recover_voice_results(self,mode,busy):
        project=getattr(self.home.main,"project_dir",None)
        signature=(str(Path(project).resolve()) if project else "",mode)
        if signature==getattr(self,"_vocal_recovery_signature",None):
            return
        if busy:return
        self._vocal_recovery_signature=signature
        self._voice_paths=[]
        for button in self.voice_results:button.hide()
        self.voice_note.hide()
        if not project or mode not in ("lead_backing","male_female"):return
        root=Path(project)/"temporales"/"voces"
        folders=[root/mode] + sorted(root.glob(mode+"_*"),
                                    key=lambda p:p.stat().st_mtime if p.is_dir() else 0,
                                    reverse=True) if root.is_dir() else []
        for folder in folders:
            if not folder.is_dir():continue
            found=sorted(p for p in folder.iterdir()
                         if p.is_file() and p.suffix.lower() in (".wav",".flac",".mp3")
                         and p.stat().st_size>1024)
            if len(found)>=2:
                self.vocal_results_ready([str(p) for p in found[:2]],autoplay=False)
                return

    def install_vocal_model(self):
        mode=self.voice_mode.currentData()
        if mode:self.voice_task.download(mode)

    def start_vocal_split(self):
        mode=self.voice_mode.currentData()
        if mode and self.voice_task.separate(
                self.home,mode,output_format=self.voice_format.currentText(),
                overlap=self.voice_detail.currentData(),
                amplification=self.voice_boost.value()):
            for button in self.voice_results:button.hide()

    def vocal_results_ready(self,paths,autoplay=True):
        self._voice_paths=[Path(p) for p in paths if Path(p).is_file()]
        # Publicar en Resultados, selector de Audio a MIDI y mute/VU inferior.
        if self._voice_paths:self.home.refresh(force=True)
        for i,button in enumerate(self.voice_results):
            if i>=len(self._voice_paths):
                button.hide()
                continue
            path=self._voice_paths[i]
            label=path.stem.casefold()
            name=("Coros / acompañamiento" if "(instrumental)" in label else
                  "Voz principal" if "(vocals)" in label else
                  "Voz femenina" if "(female)" in label else
                  "Voz masculina" if "(male)" in label else path.stem[:24])
            short=("Coros" if name.startswith("Coros") else
                   "Principal" if name=="Voz principal" else
                   "Femenina" if name=="Voz femenina" else
                   "Masculina" if name=="Voz masculina" else name)
            button.setText("▶ "+short)
            button.setToolTip(name+" · "+str(path))
            button.show()
        self.voice_note.hide()
        if autoplay and self.voice_auto_preview.isChecked():
            QTimer.singleShot(0,lambda:self.preview_vocal_result(0))

    def preview_vocal_result(self,index):
        paths=getattr(self,"_voice_paths",[])
        if 0<=index<len(paths) and paths[index].is_file():
            self.home._sep_listen.stop()
            self.home.player.load(paths[index],autoplay=True)

    def refresh(self):
        if not self.root.isVisible():return
        self._updating=True
        try:
            self.refresh_voice_controls()
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
            found={MAP.get(name,name)
                   for name,path in self.home._sep_listen.available().items()
                   if name!="Original" and path is not None}
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
