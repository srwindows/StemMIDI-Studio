"""Panel compacto de transferencia tímbrica, estilos y biblioteca de modelos.

La opción espectral es operativa. Importar RVC/ONNX registra modelos locales
sin ejecutarlos: un backend neuronal compatible es un requisito independiente.
"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QComboBox,QPushButton,
    QCheckBox,QSlider,QStackedWidget,QMessageBox,QSizePolicy
)
from ux_controls import PresetStrip
from vocal_clone_preset_catalog import factory_presets
from vocal_voice_models import read_catalog,import_models,remove_model
from vocal_engine_capabilities import analyze,NEURAL_KNOBS
import file_dialogs

DEFINITIONS=(
    ("similarity","Identidad",0,100,55,"%",
     "Mezcla de la envolvente espectral de referencia, no identidad neuronal."),
    ("timbre","Timbre",0,100,65,"%",
     "Cantidad de detalle de la transferencia de color tímbrico."),
    ("pitch","Tono",-12,12,0,"st",
     "Transposición de altura por semitonos manteniendo duración."),
    ("formants","Formantes",-8,8,0,"st",
     "Desplaza las resonancias de vocales sin trasladar palabras."),
    ("resonance","Resonancia",0,100,25,"%",
     "Realce de resonancias naturales detectadas en la referencia."),
    ("brightness","Brillo",-100,100,0,"%",
     "Balance de cuerpo y agudos de la nueva toma."),
    ("dynamics","Dinámica",0,100,45,"%",
     "Curva de intensidades relativas de la voz de referencia."),
    ("articulation","Ataques",0,100,20,"%",
     "Acentúa o suaviza los transitorios expresivos."),
    ("air","Aire",0,100,15,"%",
     "Modifica el contenido aireado de la banda alta."),
    ("rasp","Rasgado",0,100,0,"%",
     "Saturación armónica paralela, sin sustituir la voz."),
    ("vibrato","Vibrato",0,100,0,"%",
     "Modulación sintética sutil de altura (~5 Hz)."),
    ("stereo","Estéreo",0,200,100,"%",
     "Control mid-side para expandir o reducir la anchura de la señal.")
)
DEFAULT={key:val for key,_,low,high,val,suffix,tip in DEFINITIONS}
PRESETS=factory_presets(DEFAULT)

class VocalClonePanel(QWidget):
    def __init__(self,studio):
        super().__init__(studio)
        self.studio=studio
        self.mod=studio.mod
        self.sliders={}
        self.numbers={}
        self.engine_sliders={}
        self.engine_numbers={}
        self._engine_inspection={}
        self._applying=False
        self.setObjectName("vocalClonePanel")
        body=QVBoxLayout(self)
        body.setContentsMargins(3,2,3,2)
        body.setSpacing(2)

        model_line=QHBoxLayout()
        model_line.setSpacing(5)
        model_line.addWidget(QLabel("Motor",self))
        self.model=QComboBox(self)
        self.model.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.model.setMinimumWidth(0)
        self.model.setMaximumWidth(190)
        self.model.setMinimumContentsLength(9)
        self.model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        model_line.addWidget(self.model,1)
        add=QPushButton("Añadir…",self)
        add.setToolTip("Registrar varios .onnx, .pth, .pt o .safetensors y .index. No ejecutar pesos importados.")
        add.clicked.connect(self.import_external)
        model_line.addWidget(add)
        remove=QPushButton("Quitar",self)
        remove.clicked.connect(self.remove_external)
        model_line.addWidget(remove)
        model_line.addWidget(QLabel("Modo",self))
        self.group=QComboBox(self)
        self.group.addItems(("Identidad / tono","Estilo / carácter"))
        self.group.setMaximumWidth(135)
        self.group.setMinimumContentsLength(7)
        self.group.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        model_line.addWidget(self.group)
        body.addLayout(model_line)

        reference_line=QHBoxLayout()
        reference_line.setSpacing(5)
        reference_line.addWidget(QLabel("Referencia",self))
        self.reference_path=QLabel("Ninguna",self)
        self.reference_path.setMaximumWidth(275)
        self.reference_path.setMinimumWidth(40)
        self.reference_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        reference_line.addWidget(self.reference_path,1)
        choose=QPushButton("Elegir voz…",self)
        choose.clicked.connect(self._choose_reference)
        reference_line.addWidget(choose)
        self.consent=QCheckBox("Autorizada",self)
        self.consent.setToolTip("Confirma que tienes derechos/permiso para procesar la identidad de esta voz.")
        self.consent.setChecked(self.mod.ref_consent.isChecked())
        self.consent.toggled.connect(self.mod.ref_consent.setChecked)
        self.mod.ref_consent.toggled.connect(self._sync_consent)
        reference_line.addWidget(self.consent)
        reference_line.addStretch(1)
        body.addLayout(reference_line)

        self.presets=PresetStrip("vocal_clonacion",PRESETS,
                                 self.snapshot,self.apply_settings,self)
        self.presets.layout().setContentsMargins(2,0,2,0)
        self.presets.layout().setSpacing(3)
        self.presets.setMaximumHeight(32)
        self.presets.choices.setMinimumWidth(0)
        self.presets.choices.setMaximumWidth(172)
        self.presets.name.setMinimumWidth(0)
        self.presets.name.setMaximumWidth(145)
        self.presets.save_btn.setMaximumWidth(70)
        self.presets.delete_btn.setMaximumWidth(65)
        self.presets.message.setMaximumWidth(110)
        self.presets.choices.setToolTip(
            "26 presets de fábrica para identidad, timbre, estilo y registro. "
            "Los presets personalizados se guardan en la carpeta de trabajo.")
        body.addWidget(self.presets)

        self.pages=QStackedWidget(self)
        for subset in (DEFINITIONS[:6],DEFINITIONS[6:]):
            page=QWidget(self.pages)
            grid=QGridLayout(page)
            grid.setContentsMargins(0,1,0,1)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(1)
            for i,(key,label,low,high,default,suffix,tip) in enumerate(subset):
                cell=QWidget(page)
                line=QHBoxLayout(cell)
                line.setContentsMargins(1,0,1,0)
                line.setSpacing(3)
                caption=QLabel(label,cell)
                caption.setMaximumWidth(76)
                line.addWidget(caption,0)
                slider=QSlider(Qt.Horizontal,cell)
                slider.setRange(low,high)
                slider.setValue(default)
                slider.setMinimumWidth(30)
                slider.setToolTip(tip)
                slider.sliderPressed.connect(self._begin_edit)
                slider.actionTriggered.connect(lambda *_:self._begin_edit())
                line.addWidget(slider,1)
                number=QLabel("",cell)
                number.setMinimumWidth(37)
                number.setMaximumWidth(44)
                number.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
                line.addWidget(number,0)
                cell.setMinimumHeight(22)
                cell.setMaximumHeight(24)
                grid.addWidget(cell,i//3,i%3)
                self.sliders[key]=slider
                self.numbers[key]=(number,suffix)
                slider.valueChanged.connect(
                    lambda value,key=key:self._changed(key,value))
                self._draw_number(key,default)
            for col in range(3):
                grid.setColumnStretch(col,1)
            self.pages.addWidget(page)
        # Motor neuronal: parámetros añadidos solo cuando el backend los
        # declara realmente en RANGES y usa en su convertidor.
        neural_page=QWidget(self.pages)
        neural_grid=QGridLayout(neural_page)
        neural_grid.setContentsMargins(0,1,0,1)
        neural_grid.setHorizontalSpacing(6)
        neural_grid.setVerticalSpacing(2)
        for i,(key,title,minimum,maximum,default,suffix,hint) in enumerate(NEURAL_KNOBS):
            cell=QWidget(neural_page)
            row=QHBoxLayout(cell)
            row.setContentsMargins(1,0,1,0)
            row.setSpacing(3)
            caption=QLabel(title,cell)
            caption.setMaximumWidth(93)
            row.addWidget(caption,0)
            slider=QSlider(Qt.Horizontal,cell)
            slider.setRange(minimum,maximum)
            slider.setValue(default)
            slider.setMinimumWidth(30)
            slider.setToolTip(hint)
            slider.valueChanged.connect(
                lambda value,key=key:self._engine_changed(key,value))
            row.addWidget(slider,1)
            value_label=QLabel(f"{default} {suffix}",cell)
            value_label.setMinimumWidth(43)
            value_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            row.addWidget(value_label)
            cell.setMinimumHeight(22)
            cell.setMaximumHeight(25)
            neural_grid.addWidget(cell,0,i)
            neural_grid.setColumnStretch(i,1)
            self.engine_sliders[key]=slider
            self.engine_numbers[key]=(value_label,suffix)
        note=QLabel(
            "Estos tres ajustes pertenecen al conversor neuronal; "
            "no están disponibles en el motor espectral.",neural_page)
        note.setWordWrap(False)
        note.setToolTip(
            "Tau se envía a OpenVoice; fragmento y solape controlan la "
            "inferencia por bloques. No se crean controles sin backend.")
        neural_grid.addWidget(note,1,0,1,3)
        self.pages.addWidget(neural_page)
        self.group.currentIndexChanged.connect(self.pages.setCurrentIndex)
        body.addWidget(self.pages)

        action_line=QHBoxLayout()
        action_line.setSpacing(5)
        self.render=QPushButton("Procesar timbre y estilo",self)
        self.render.setObjectName("vocalPrimary")
        self.render.clicked.connect(self.mod.start_voice_clone)
        action_line.addWidget(self.render)
        self.state=QLabel("Procesado espectral local; no clona identidad neuronal.",self)
        self.state.setToolTip(
            "La transferencia de timbre es DSP. Los modelos externos no se ejecutan sin un motor de conversión probado.")
        action_line.addWidget(self.state,1)
        body.addLayout(action_line)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.refresh_models()
        self.refresh_reference()
        # Mostrar desde el primer arranque un preset REAL aplicado a los
        # 12 controles: sin un desplegable aparentemente vacío.
        self.sync_selected_preset()
        self.presets.message.setText(f"{len(PRESETS)} de fábrica")

    def _begin_edit(self):
        if not self._applying and hasattr(self.studio,"_begin_edit"):
            self.studio._begin_edit()

    def _draw_number(self,key,value):
        number,suffix=self.numbers[key]
        number.setText(f"{value} {suffix}")

    def _changed(self,key,value):
        self._draw_number(key,value)
        if not self._applying:
            self._begin_edit()
            self.studio._history_timer.start()
            self.mod._mark_pending()
            self.sync_selected_preset()

    def snapshot(self):
        return {name:slider.value() for name,slider in self.sliders.items()}

    def neural_snapshot(self):
        return {name:slider.value() for name,slider in self.engine_sliders.items()}

    def params_for_engine(self):
        params=self.snapshot()
        if self.model.currentData()=="openvoice_v2":
            params.update(self.neural_snapshot())
        allowed=self._engine_inspection.get("parameters",{})
        if not self._engine_inspection.get("available") or set(params)!=set(allowed):
            raise ValueError("Motor no compatible con los parámetros seleccionados.")
        return params

    def apply_neural(self,settings):
        if not isinstance(settings,dict):return
        self._begin_edit()
        self._applying=True
        try:
            for key,value in settings.items():
                if key in self.engine_sliders and isinstance(value,(int,float)):
                    slider=self.engine_sliders[key]
                    slider.setValue(max(slider.minimum(),
                        min(slider.maximum(),int(value))))
        finally:
            self._applying=False
        self.mod._mark_pending()
        self.studio._history_timer.start()
        self.sync_selected_preset()

    def _engine_changed(self,key,value):
        label,suffix=self.engine_numbers[key]
        label.setText(f"{value} {suffix}")
        if not self._applying:
            self._begin_edit()
            self.studio._history_timer.start()
            self.mod._mark_pending()
            self.sync_selected_preset()

    def apply_settings(self,settings):
        if not isinstance(settings,dict):return
        self._begin_edit()
        self._applying=True
        try:
            for key,value in settings.items():
                if key in self.sliders and isinstance(value,(int,float)):
                    slider=self.sliders[key]
                    slider.setValue(max(slider.minimum(),
                                        min(slider.maximum(),int(value))))
        finally:self._applying=False
        self.studio._history_timer.start()
        self.mod._mark_pending()
        self.sync_selected_preset()

    def sync_selected_preset(self):
        """Refleja el nombre solo si los doce parámetros coinciden."""
        if not self.sliders:
            return
        actual=self.snapshot()
        matching=None
        neural_modified=(self.model.currentData()=="openvoice_v2" and
            any(self.engine_sliders[key].value()!=default
                for key,_,_,_,default,*_ in NEURAL_KNOBS))
        for i in range(1,self.presets.choices.count()):
            kind,name=self.presets.choices.itemData(i)
            params=(self.presets.builtins.get(name)
                    if kind=="base" else self.presets._read().get(name))
            if params==actual and not neural_modified:
                matching=i
                break
        with QSignalBlocker(self.presets.choices):
            self.presets.choices.setCurrentIndex(matching if matching is not None else 0)
            self.presets.choices.setItemText(
                0,"— Ajustes personalizados —" if matching is None
                else "— Elegir preset —")
        if matching is None:
            self.presets.message.setText("Personalizado")

    def reset_settings(self):
        self.apply_settings(DEFAULT)

    def _sync_consent(self,enabled):
        with QSignalBlocker(self.consent):
            self.consent.setChecked(enabled)

    def _choose_reference(self):
        self.mod.pick_reference()
        self.refresh_reference()

    def refresh_reference(self):
        path=self.mod.reference.text().strip()
        self.reference_path.setText(Path(path).name if path else "Ninguna")
        self.reference_path.setToolTip(path or "Selecciona una referencia de voz.")
        self._sync_consent(self.mod.ref_consent.isChecked())

    def refresh_models(self,selected=None):
        current=selected if selected is not None else self.model.currentData()
        with QSignalBlocker(self.model):
            self.model.clear()
            self.model.addItem("Local · espectral","local")
            from vocal_openvoice_engine import model_ready
            installed=model_ready()
            self.model.addItem("OpenVoice V2 · neuronal","openvoice_v2")
            self.model.setItemData(1,
                "MyShell OpenVoice V2 (MIT): conversión neuronal de identidad "
                "a partir de una referencia autorizada. Procesamiento CPU."
                if installed else "Faltan pesos o código local de OpenVoice V2.",
                Qt.ToolTipRole)
            self.model.model().item(1).setEnabled(installed)
            for model in read_catalog():
                self.model.addItem(model["name"]+" · no compatible",model["id"])
                self.model.setItemData(self.model.count()-1,model["status"],Qt.ToolTipRole)
            idx=self.model.findData(current)
            if idx < 0 and installed:
                idx=self.model.findData("openvoice_v2")
            self.model.setCurrentIndex(max(0,idx))
        self._model_changed()

    def _model_changed(self,*_):
        """Audita cada motor y muestra exactamente sus controles válidos."""
        selected=self.model.currentData()
        report=analyze(selected)
        self._engine_inspection=report
        available=bool(report["available"])
        groups=report["groups"] if available else ["Sin ajustes"]
        previous=self.group.currentIndex()
        with QSignalBlocker(self.group):
            self.group.clear()
            self.group.addItems(groups)
            index=min(max(0,previous),self.group.count()-1)
            self.group.setCurrentIndex(index)
        self.pages.setCurrentIndex(index if available else 0)
        self.pages.setVisible(available)
        self.group.setEnabled(available and self.mod.process is None)
        self.render.setEnabled(available and self.mod.process is None)
        for key,slider in self.sliders.items():
            slider.setEnabled(available and key in report["parameters"]
                              and self.mod.process is None)
        for key,slider in self.engine_sliders.items():
            slider.setEnabled(available and key in report["parameters"]
                              and self.mod.process is None)
        count=len(report["parameters"])
        if available:
            self.state.setText(
                f"{report['name']} · {count} parámetros comprobados.")
        else:
            self.state.setText(
                "Modelo no compatible; no se muestran parámetros ficticios.")
        self.state.setToolTip(report["detail"]+"\n"+report["method"])

    def import_external(self):
        files,_=file_dialogs.get_open_file_names(
            self,"Importar varios modelos de voz",str(Path.home()),
            "Modelos de conversión (*.onnx *.pth *.pt *.safetensors *.index)")
        if not files:return
        try:
            added=import_models(files)
        except (OSError,ValueError) as error:
            QMessageBox.warning(self,"Importación de modelos",str(error))
            return
        selected=added[0]["id"] if added else None
        self.refresh_models(selected)
        QMessageBox.information(self,"Biblioteca vocal",
            f"{len(added)} modelo(s) nuevo(s) registrados.\n"
            "No se ejecutarán hasta disponer de un motor compatible verificado.")

    def remove_external(self):
        ident=self.model.currentData()
        if ident in ("local","openvoice_v2") or not ident:return
        yes=QMessageBox.question(self,"Eliminar copia de modelo",
            "¿Eliminar esta copia importada? El archivo externo original se conserva.")
        if yes!=QMessageBox.Yes:return
        try:
            remove_model(ident)
        except (OSError,ValueError) as error:
            QMessageBox.warning(self,"Biblioteca vocal",str(error))
            return
        self.refresh_models("local")

    def set_busy(self,busy):
        available=bool(self._engine_inspection.get("available"))
        self.render.setEnabled(not busy and available)
        self.group.setEnabled(not busy and available)
        self.model.setEnabled(not busy)
        self.presets.setEnabled(not busy)
        for key,slider in self.sliders.items():
            slider.setEnabled(not busy and available
                              and key in self._engine_inspection["parameters"])
        for key,slider in self.engine_sliders.items():
            slider.setEnabled(not busy and available
                              and key in self._engine_inspection["parameters"])
        self.consent.setEnabled(not busy)
