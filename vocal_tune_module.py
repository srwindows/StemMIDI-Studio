"""Afinación vocal basada en pYIN y corrección tonal de voz monofónica.

Lanza el motor del entorno_ia sin bloquear la interfaz y sólo incorpora
a Resultados archivos FLAC reales de la tarea del proyecto actual.
"""
from __future__ import annotations
import file_dialogs
from pathlib import Path
from PySide6.QtCore import Qt,QProcess,Signal,QTimer
from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,
    QFileDialog,QSlider,QMessageBox,QTableWidget,QTableWidgetItem,
    QAbstractItemView,QHeaderView,QLineEdit,QGroupBox,QSpinBox,QGridLayout,QCheckBox,QSizePolicy,QTabWidget,QScrollArea,QFrame
)
from task_staging import TaskStorage
from preview_player import PreviewPlayer
from studio_paths import workspace_root
from studio_slider_spin import StudioSliderSpin
from ux_controls import PresetStrip
ROOT=workspace_root(__file__)
NOTES=("Do","Do#","Re","Re#","Mi","Fa","Fa#","Sol","Sol#","La","La#","Si")
SCALES=("Cromática","Mayor","Menor natural","Pentatónica mayor","Pentatónica menor")
AUDIO=(".wav",".flac",".mp3",".m4a",".aif",".aiff",".ogg")
PRESETS={
 "Natural":(58,160,28,18,15,70),
 "Estudio":(82,90,17,10,35,85),
 "Pop preciso":(98,35,3,5,55,90),
 "Balada expresiva":(68,175,35,15,28,75),
 "Rock":(72,120,30,17,52,95),
    "Voz rasgada · Rock":(70,110,24,17,45,95),
    "Voz dulce · Balada":(66,170,34,14,26,68),
    "Voz cálida · Soul":(74,130,24,13,42,85),
    "Voz aireada · Pop":(78,105,20,10,32,74),
    "Voz limpia · Estudio":(80,105,22,10,36,85),
    "Manual":None
}
FX_PRESETS={
    "Voz rasgada · Rock":("Rasgada",74,16,12,52,30,9,10,100),
    "Voz dulce · Balada":("Dulce",78,27,10,12,65,25,18,100),
    "Voz cálida · Soul":("Cálida",58,45,10,24,45,12,22,100),
    "Voz aireada · Pop":("Aireada",46,17,55,18,45,13,12,100),
    "Voz limpia · Estudio":("Natural",0,20,14,20,56,29,7,100)
}
FX_NEUTRAL=("Natural",0,0,0,0,0,0,0,100)


class VocalTuneModule(QWidget):
    resultsChanged=Signal()
    def __init__(self,main,workbench):
        super().__init__(main)
        self.main=main
        self.workbench=workbench
        self.storage=workbench.vocal_storage
        self.process=None
        self.processing_file=None
        self._operation=None
        self._run_output=""
        self._analysis_report=None
        self._reference_report=None
        self.setObjectName("vocalTuneModule")
        outer=QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        self.content_scroll=QScrollArea(self)
        self.content_scroll.setObjectName("vocalModuleScroll")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content=QWidget(self.content_scroll)
        content.setObjectName("main")
        layout=QVBoxLayout(content)
        layout.setContentsMargins(16,13,16,14)
        layout.setSpacing(10)
        self.content_scroll.setWidget(content)
        outer.addWidget(self.content_scroll)
        title=QLabel("ESTUDIO VOCAL · AFINACIÓN, TIMBRE Y EFECTOS")
        title.setObjectName("title")
        layout.addWidget(title)
        text=QLabel(
            "Afinación, transformación controlada de carácter (dulce/rasgado), "
            "EQ, dinámica y efectos sobre una voz existente. "
            "El original se conserva; la calidad final debe valorarse escuchando.")
        text.setWordWrap(True)
        layout.addWidget(text)
        group=QGroupBox("Voz de entrada y tonalidad")
        g=QVBoxLayout(group)
        row=QHBoxLayout()
        row.addWidget(QLabel("Voz aislada del proyecto"))
        self.source_choice=QComboBox(self)
        row.addWidget(self.source_choice)
        self.update_sources_btn=QPushButton("Actualizar voces")
        self.update_sources_btn.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.update_sources_btn.clicked.connect(self.refresh_sources)
        row.addWidget(self.update_sources_btn)
        row.addStretch(1)
        g.addLayout(row)
        row=QHBoxLayout()
        row.addWidget(QLabel("Archivo de voz"))
        self.input=QLineEdit(self)
        self.input.setReadOnly(True)
        self.input.setPlaceholderText("Sin voz seleccionada")
        self.input.setMaximumWidth(510)
        row.addWidget(self.input,1)
        self.browse=QPushButton("Importar voz…")
        self.browse.clicked.connect(self.browse_audio)
        row.addWidget(self.browse)
        row.addStretch(1)
        g.addLayout(row)
        row=QHBoxLayout()
        row.addWidget(QLabel("Tónica"))
        self.tonic=QComboBox(self)
        self.tonic.addItems(NOTES)
        row.addWidget(self.tonic)
        row.addWidget(QLabel("Escala"))
        self.scale=QComboBox(self)
        self.scale.addItems(SCALES)
        row.addWidget(self.scale,1)
        row.addWidget(QLabel("Corrección"))
        self.strength=QSlider(Qt.Horizontal)
        self.strength.setRange(10,100)
        self.strength.setValue(75)
        self.strength.setMinimumWidth(220)
        row.addWidget(self.strength,2)
        self.strength_text=QLabel("75 %")
        self.strength.valueChanged.connect(
            lambda v:self.strength_text.setText(f"{v} %"))
        row.addWidget(self.strength_text)
        g.addLayout(row)
        g.addWidget(QLabel("Pensado para voz monofónica. La corrección automática "
                           "puede introducir artefactos; conviene escuchar el resultado."))
        layout.addWidget(group)
        advanced=QGroupBox("Análisis del cantante y corrección profesional")
        outer=QHBoxLayout(advanced)
        form=QWidget(advanced)
        grid=QGridLayout(form)
        outer.addWidget(form,0,Qt.AlignLeft)
        outer.addStretch(1)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(12)
        grid.addWidget(QLabel("Preset"),0,0)
        self.preset=QComboBox()
        self.preset.addItems(PRESETS)
        self.preset.setCurrentText("Estudio")
        grid.addWidget(self.preset,0,1)
        self.analyze_btn=QPushButton("Analizar cantante")
        self.analyze_btn.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.analyze_btn.clicked.connect(self.analyze)
        grid.addWidget(self.analyze_btn,0,2)
        self.auto_btn=QPushButton("Aplicar análisis automático")
        self.auto_btn.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.auto_btn.setEnabled(False)
        self.auto_btn.clicked.connect(self.apply_analysis)
        grid.addWidget(self.auto_btn,0,3,1,3)
        grid.setColumnStretch(5,0)
        params=(
            ("retune","Velocidad",20,250,90,"ms"),
            ("humanize","Humanización",0,100,17,"%"),
            ("threshold","Umbral",0,70,10,"cents"),
            ("compression","Compresión",0,100,35,"%"),
            ("highpass","Corte graves",0,190,85,"Hz"),
        )
        for i,(key,label_text,low,high,val,suffix) in enumerate(params):
            row=i//3+1
            col=i%3*2
            grid.addWidget(QLabel(label_text),row,col)
            box=StudioSliderSpin(low,high,val,suffix,self,width=215)
            box.valueChanged.connect(self._manual_preset)
            setattr(self,key,box)
            grid.addWidget(box,row,col+1)
        self.preset.currentTextChanged.connect(self.apply_preset)
        self.analysis_text=QLabel("Sin análisis. Informe: rango, desviación, estabilidad, nivel y tonalidad estimada.")
        self.analysis_text.setObjectName("muted")
        self.analysis_text.setWordWrap(True)
        grid.addWidget(self.analysis_text,3,0,1,6)
        self.studio_tabs=QTabWidget(self)
        self.studio_tabs.setObjectName("vocalStudioRack")
        self.studio_tabs.setDocumentMode(True)
        self.studio_tabs.addTab(advanced,"Afinación y análisis")
        self._build_character_tab()
        self._build_fx_tab()
        self._build_spatial_tab()
        style=QGroupBox("Aprendizaje de interpretación · mantener mi voz")
        style_box=QVBoxLayout(style)
        style_box.setSpacing(9)
        line=QHBoxLayout()
        style_box.addLayout(line)
        self.reference=QLineEdit(self)
        self.reference.setReadOnly(True)
        self.reference.setPlaceholderText("Voz de referencia autorizada (opcional)")
        self.reference.setMaximumWidth(510)
        line.addWidget(self.reference,1)
        self.ref_browse=QPushButton("Elegir referencia…")
        self.ref_browse.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.ref_browse.clicked.connect(self.pick_reference)
        line.addWidget(self.ref_browse)
        self.ref_consent=QCheckBox("Tengo autorización")
        line.addWidget(self.ref_consent)
        self.ref_analyze=QPushButton("Analizar estilo")
        self.ref_analyze.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.ref_analyze.clicked.connect(self.analyze_reference)
        line.addWidget(self.ref_analyze)
        line.addStretch(1)
        self.reference_info=QLabel("Referencia autorizada: compara curvas de afinación "
                                   "y características expresivas. No clona timbre.")
        self.reference_info.setObjectName("muted")
        self.reference_info.setWordWrap(True)
        style_box.addWidget(self.reference_info)
        self.learn_same_song=QCheckBox(
            "Mis mismas palabras y canción · aprender la interpretación")
        self.learn_same_song.setToolTip(
            "Alineación aproximada de dos tomas cantando la misma canción. "
            "No permite copiar la dicción ni interpretar otra letra.")
        self.learn_same_song.toggled.connect(self._mark_pending)
        style_box.addWidget(self.learn_same_song)
        hint=QLabel(
            "Tu voz seguirá siendo la fuente del audio. Se transferirán de forma "
            "aproximada notas, vibrato, intensidad y tempo global. No es "
            "clonación de voz ni un modelo de aprendizaje entrenado.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        style_box.addWidget(hint)
        learning_grid=QGridLayout()
        learning_grid.setHorizontalSpacing(10)
        learning_grid.setVerticalSpacing(10)
        for index,(name,label,default,tip) in enumerate((
            ("learn_melody","Melodía y afinación",85,
             "Sigue las notas cantadas por la referencia, usando el timbre de tu grabación."),
            ("learn_vibrato","Vibrato e inflexiones",70,
             "Sigue parte de las oscilaciones rápidas de afinación de la referencia."),
            ("learn_dynamics","Dinámica expresiva",60,
             "Transfiere variaciones relativas de volumen, no el nivel del micrófono."),
            ("learn_timing","Tempo global",75,
             "Ajusta la duración global a la referencia sin copiar sílabas "
             "ni pausas individuales."),
        )):
            field=StudioSliderSpin(0,100,default,"%",self,width=260)
            field.setToolTip(tip)
            field.slider.setToolTip(tip)
            field.spin.setToolTip(tip)
            field.valueChanged.connect(self._mark_pending)
            setattr(self,name,field)
            learning_grid.addWidget(QLabel(label),index//2,(index%2)*2)
            learning_grid.addWidget(field,index//2,(index%2)*2+1)
        style_box.addLayout(learning_grid)
        self.learn_button=QPushButton("Aplicar interpretación de referencia a mi voz")
        self.learn_button.setObjectName("primary")
        self.learn_button.setToolTip(
            "Genera una nueva toma FLAC con tu propia voz siguiendo aproximadamente "
            "la entonación y dinámica de la referencia, sin sobrescribir originales.")
        self.learn_button.clicked.connect(self.start_learning)
        style_box.addWidget(self.learn_button)
        self.studio_tabs.addTab(style,"Aprender interpretación")
        from ui_responsive import scroll_tab_pages
        scroll_tab_pages(self.studio_tabs)
        self.studio_tabs.setCurrentIndex(1)
        self.studio_tabs.setMinimumHeight(325)
        self.studio_tabs.setMaximumHeight(415)
        layout.addWidget(self.studio_tabs)

        # Banco de presets DEL MÓDULO COMPLETO, visible en todas las pestañas,
        # incluida Voz de referencia. Nunca guarda rutas ni audio.
        self._applying_full_preset=False
        self.full_presets=PresetStrip("vocal_completo",{
            "Voz natural sin efectos":{
                "character":"Natural","character_amount":0,"warmth":0,"presence":0,
                "air":0,"deesser":0,"gate":0,"reverb":0,"wet":100,
                "doubler":0,"delay":0,"stereo_width":100,"output_gain_db":0,
                "compression":0,"highpass":0,"bypass_tune":True},
            "Voz limpia · Estudio":{
                "character":"Natural","character_amount":0,"warmth":15,"presence":30,
                "air":18,"deesser":40,"gate":18,"reverb":9,"wet":100,
                "compression":30,"highpass":85,"doubler":0,"delay":0,
                "stereo_width":100,"output_gain_db":0,"bypass_tune":False},
            "Voz dulce · Balada":{
                "character":"Dulce","character_amount":75,"warmth":30,
                "presence":16,"air":10,"deesser":35,"gate":10,"reverb":30,
                "wet":100,"doubler":15,"delay":18,"delay_ms":320,
                "compression":25,"highpass":70,"bypass_tune":False},
            "Voz rasgada · Rock":{
                "character":"Rasgada","character_amount":70,"warmth":17,
                "presence":50,"air":20,"deesser":32,"gate":20,"reverb":8,
                "wet":100,"doubler":23,"delay":11,"delay_ms":125,
                "compression":55,"highpass":90,"bypass_tune":False}
        },self.full_preset_snapshot,self.apply_full_preset,self)
        self.full_presets.setToolTip(
            "Guarda y recupera la configuración completa de voz y efectos; "
            "la grabación original y sus rutas no forman parte del preset.")
        # Situar el selector antes del rack de pestañas: aparece siempre
        # al entrar en el módulo sin obligar a buscarlo bajo «Referencia».
        layout.insertWidget(layout.indexOf(self.studio_tabs),self.full_presets)
        self.processing_notice=QLabel(
            "Los cambios de controles se aplicarán al pulsar «Procesar voz». "
            "El resultado anterior no cambia hasta entonces.")
        self.processing_notice.setObjectName("muted")
        self.processing_notice.setWordWrap(True)
        layout.addWidget(self.processing_notice)
        buttons=QHBoxLayout()
        self.start_button=QPushButton("Procesar voz")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start)
        buttons.addWidget(self.start_button)
        self.stop_button=QPushButton("Cancelar")
        self.stop_button.clicked.connect(self.cancel)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.status=QLabel("Sin tarea vocal. Selecciona una voz real del proyecto.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table=QTableWidget(0,2,self)
        self.table.setHorizontalHeaderLabels(["Resultado","Archivo FLAC"])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellClicked.connect(self.preview_selected)
        layout.addWidget(self.table,1)
        self.table.setMinimumHeight(105)
        self.preview=PreviewPlayer("ESCUCHAR VOZ AFINADA",self)
        self.preview.setMaximumHeight(150)
        self.preview.setVisible(False)
        layout.addWidget(self.preview)
        actions=QHBoxLayout()
        self.preview_toggle=QPushButton("▶ Abrir escucha A/B")
        self.preview_toggle.clicked.connect(self.toggle_preview)
        actions.addWidget(self.preview_toggle)
        self.compare_choice=QComboBox(self)
        self.compare_choice.addItem("A · Voz original", "original")
        self.compare_choice.addItem("B · Voz procesada", "processed")
        self.compare_choice.setCurrentIndex(1)
        self.compare_choice.setToolTip("Cambiar entre la fuente sin procesar y el resultado sin modificar los archivos.")
        self.compare_choice.currentIndexChanged.connect(self.play_comparison)
        actions.addWidget(self.compare_choice)
        self.save_btn=QPushButton("Guardar selección…")
        self.save_btn.clicked.connect(self.save_selected)
        actions.addWidget(self.save_btn)
        self.discard_btn=QPushButton("Descartar tarea temporal…")
        self.discard_btn.clicked.connect(self.discard)
        actions.addWidget(self.discard_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self.source_choice.currentIndexChanged.connect(self._choose_source)
        self.refresh_sources()
        self.refresh_results()
        self._set_busy(False)
        self.apply_preset("Estudio")
        # Todos los controles que influyen en el procesamiento anuncian la
        # necesidad de volver a renderizar; no fingir edición en tiempo real.
        for selector in (self.tonic,self.scale):
            selector.currentIndexChanged.connect(self._mark_pending)
        self.strength.valueChanged.connect(self._mark_pending)
        self.bypass_tune.toggled.connect(self._mark_pending)
        self.preset.currentTextChanged.connect(self._mark_pending)
        self.character.currentIndexChanged.connect(self._sync_effect_availability)
        self.delay.valueChanged.connect(self._sync_effect_availability)
        self._sync_effect_availability()

    def _sync_effect_availability(self,*_):
        """Los controles dependientes no prometen efectos inexistentes."""
        active=self.process is None
        self.character_amount.setEnabled(
            active and self.character.currentText()!="Natural")
        self.delay_ms.setEnabled(active and self.delay.value()>0)
        self.character_amount.setToolTip(
            "El carácter Natural no necesita intensidad. Elige Dulce, "
            "Rasgada, Cálida o Aireada para activarla."
            if self.character.currentText()=="Natural"
            else "Intensidad del carácter vocal aplicado al nuevo render.")
        self.delay_ms.setToolTip(
            "Activa Delay (valor mayor que cero) para cambiar el tiempo de eco."
            if self.delay.value()==0 else "Tiempo entre repeticiones del eco.")

    def _build_character_tab(self):
        pane=QWidget(self)
        form=QGridLayout(pane)
        form.setContentsMargins(12,8,12,8)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addWidget(QLabel("Carácter"),0,0)
        self.character=QComboBox(self)
        self.character.addItems(("Natural","Dulce","Rasgada","Cálida","Aireada"))
        self.character.currentIndexChanged.connect(self._manual_preset)
        form.addWidget(self.character,0,1)
        form.addWidget(QLabel("Intensidad"),0,2)
        self.character_amount=StudioSliderSpin(0,100,0,"%",self,width=235)
        self.character_amount.setToolTip("Rasgada: armónicos por saturación paralela. Dulce: reducción de brillo y aspereza.")
        self.character_amount.valueChanged.connect(self._manual_preset)
        form.addWidget(self.character_amount,0,3)
        self.bypass_tune=QCheckBox("Solo efectos · sin corregir notas",self)
        self.bypass_tune.setToolTip(
            "Procesa el carácter vocal incluso en fragmentos hablados o sin notas reconocidas.")
        form.addWidget(self.bypass_tune,0,4)
        info=QLabel("Rasgada = saturación controlada de armónicos; Dulce = suavizado "
            "espectral. No se pueden reconstruir al completo las componentes "
            "perdidas de una voz excesivamente rasgada.")
        info.setWordWrap(True)
        info.setObjectName("muted")
        form.addWidget(info,1,0,1,5)
        form.setColumnStretch(5,1)
        self.studio_tabs.addTab(pane,"Carácter vocal")

    def _build_fx_tab(self):
        pane=QWidget(self)
        grid=QGridLayout(pane)
        grid.setContentsMargins(12,7,12,7)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        specs=(
            ("warmth","Calidez",0),
            ("presence","Presencia",0),
            ("air","Aire",0),
            ("deesser","De-esser",0),
            ("gate","Puerta suave",0),
            ("reverb","Ambiente",0),
            ("wet","Mezcla efectos",100),
        )
        for i,(key,title,initial) in enumerate(specs):
            row=i//4
            col=(i%4)*2
            grid.addWidget(QLabel(title),row,col)
            spinner=StudioSliderSpin(0,100,initial,"%",self,width=175)
            spinner.valueChanged.connect(self._manual_preset)
            setattr(self,key,spinner)
            grid.addWidget(spinner,row,col+1)
        notice=QLabel("Ecualización tonal, control de sibilancias, reducción suave "
            "de ruido entre frases, ambiente y mezcla seca/húmeda. "
            "Todos los efectos se calculan sobre un archivo nuevo.")
        notice.setObjectName("muted")
        notice.setWordWrap(True)
        grid.addWidget(notice,2,0,1,8)
        self.fx_presets=PresetStrip("vocal_eq_fx",{
            "Voz clara · Podcast":{"warmth":15,"presence":35,"air":18,"deesser":48,"gate":32,"reverb":0,"wet":100},
            "Balada íntima":{"warmth":32,"presence":19,"air":14,"deesser":35,"gate":8,"reverb":16,"wet":100},
            "Rock frontal":{"warmth":25,"presence":58,"air":23,"deesser":51,"gate":20,"reverb":9,"wet":100},
            "Pop brillante":{"warmth":14,"presence":45,"air":48,"deesser":60,"gate":22,"reverb":19,"wet":100},
            "Natural sin FX":{"warmth":0,"presence":0,"air":0,"deesser":0,"gate":0,"reverb":0,"wet":100},
        },lambda:self._preset_snapshot(("warmth","presence","air","deesser","gate","reverb","wet")),
           self._apply_local_fx_preset,pane)
        grid.addWidget(self.fx_presets,3,0,1,8)
        grid.setColumnStretch(8,1)
        self.studio_tabs.addTab(pane,"EQ · Dinámica · FX")

    def _build_spatial_tab(self):
        pane=QWidget(self)
        grid=QGridLayout(pane)
        grid.setContentsMargins(12,10,12,10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(14)
        controls=(
            ("doubler","Doblado ADT",0,100,0,"%"),
            ("delay","Delay",0,100,0,"%"),
            ("delay_ms","Tiempo delay",80,600,220,"ms"),
            ("stereo_width","Anchura estéreo",0,200,100,"%"),
            ("output_gain_db","Salida", -18,18,0,"dB"),
        )
        for index,(name,title,minimum,maximum,value,suffix) in enumerate(controls):
            row=index//3
            column=index%3*2
            grid.addWidget(QLabel(title),row,column)
            spinner=StudioSliderSpin(minimum,maximum,value,suffix,self,width=220)
            spinner.setToolTip(
                "Ajuste de producción vocal. Los valores se aplican al crear el nuevo FLAC.")
            spinner.valueChanged.connect(self._manual_preset)
            setattr(self,name,spinner)
            grid.addWidget(spinner,row,column+1)
        note=QLabel("Doblado ADT: refuerzo con retardos breves, NO una segunda "
             "interpretación. Delay: repeticiones de eco. Anchura: solo actúa "
             "sobre fuentes estéreo. Salida protegida contra clipping.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        grid.addWidget(note,2,0,1,6)
        self.spatial_presets=PresetStrip("vocal_spatial",{
            "Estudio seco":{"doubler":0,"delay":0,"delay_ms":220,"stereo_width":100,"output_gain_db":0},
            "Doblado discreto":{"doubler":22,"delay":0,"delay_ms":220,"stereo_width":112,"output_gain_db":-2},
            "Pop estéreo":{"doubler":55,"delay":15,"delay_ms":180,"stereo_width":135,"output_gain_db":-3},
            "Balada larga":{"doubler":25,"delay":32,"delay_ms":360,"stereo_width":125,"output_gain_db":-3},
            "Slapback rock":{"doubler":15,"delay":42,"delay_ms":115,"stereo_width":115,"output_gain_db":-4},
        },lambda:self._preset_snapshot(("doubler","delay","delay_ms","stereo_width","output_gain_db")),
           self._apply_local_fx_preset,pane)
        grid.addWidget(self.spatial_presets,3,0,1,6)
        grid.setColumnStretch(6,1)
        self.studio_tabs.addTab(pane,"Doblado · Delay · Máster")

    def full_preset_snapshot(self):
        """Configuración reutilizable sin rutas, ficheros ni identidad de voz."""
        names=("retune","humanize","threshold","compression","highpass",
               "character_amount","warmth","air","presence","deesser","gate",
               "reverb","wet","doubler","delay","delay_ms","stereo_width",
               "output_gain_db","learn_melody","learn_vibrato",
               "learn_dynamics","learn_timing")
        values={name:int(getattr(self,name).value()) for name in names}
        values.update(tonic=self.tonic.currentIndex(),scale=self.scale.currentText(),
                      strength=self.strength.value(),
                      character=self.character.currentText(),
                      bypass_tune=self.bypass_tune.isChecked(),
                      learn_same_song=self.learn_same_song.isChecked())
        return values

    def apply_full_preset(self,settings):
        """Aplica todos los controles; los desconocidos no alteran el módulo."""
        self._applying_full_preset=True
        try:
            if "tonic" in settings:
                self.tonic.setCurrentIndex(max(0,min(11,int(settings["tonic"]))))
            if settings.get("scale") in SCALES:
                self.scale.setCurrentText(settings["scale"])
            if "strength" in settings:
                self.strength.setValue(max(10,min(100,int(settings["strength"]))))
            if settings.get("character") in (
                "Natural","Dulce","Rasgada","Cálida","Aireada"):
                self.character.setCurrentText(settings["character"])
            if "bypass_tune" in settings:
                self.bypass_tune.setChecked(bool(settings["bypass_tune"]))
            if "learn_same_song" in settings:
                self.learn_same_song.setChecked(bool(settings["learn_same_song"]))
            for name in ("retune","humanize","threshold","compression","highpass",
                         "character_amount","warmth","air","presence","deesser",
                         "gate","reverb","wet","doubler","delay","delay_ms",
                         "stereo_width","output_gain_db",
                         "learn_melody","learn_vibrato","learn_dynamics",
                         "learn_timing"):
                if name in settings:
                    target=getattr(self,name)
                    target.setValue(max(target.minimum(),
                                        min(target.maximum(),int(settings[name]))))
            self.strength_text.setText(f"{self.strength.value()} %")
        finally:
            self._applying_full_preset=False
        self._sync_effect_availability()
        self._mark_pending()

    def _mark_pending(self,*_):
        if getattr(self,"_applying_full_preset",False):return
        if not hasattr(self,"processing_notice"):return
        self.processing_notice.setText(
            "AJUSTES MODIFICADOS · Pulsa «Procesar voz» para generar "
            "un nuevo resultado. El FLAC anterior no se ha modificado.")

    def _preset_snapshot(self,names):
        return {name:getattr(self,name).value() for name in names}

    def _apply_local_fx_preset(self,settings):
        for name,value in settings.items():
            control=getattr(self,name,None)
            if isinstance(control,StudioSliderSpin):
                control.setValue(max(control.minimum(),min(control.maximum(),int(value))))

    def toggle_preview(self):
        visible=not self.preview.isVisible()
        self.preview.setVisible(visible)
        self.preview_toggle.setText(
            "▴ Ocultar escucha" if visible else "▶ Abrir escucha A/B")
        if visible:self.play_comparison()
        else:self.preview.stop()

    def play_comparison(self,*_):
        """Audición comparativa de archivos reales, nunca una simulación."""
        if not self.preview.isVisible():return
        kind=self.compare_choice.currentData()
        if kind=="original":
            source=Path(self.input.text()).expanduser()
        else:
            selected=[self.table.item(index.row(),1)
                      for index in self.table.selectionModel().selectedRows()]
            candidates=[Path(item.data(Qt.UserRole)) for item in selected if item]
            if not candidates:
                candidates=[Path(x) for x in self.storage.items if Path(x).is_file()]
            source=candidates[-1] if candidates else None
        if source is None or not source.is_file():
            self.preview.clear()
            self.status.setText("Sin archivo de " + ("origen" if kind=="original" else "resultado")
                               + " para escuchar.")
            return
        self.preview.load(source,autoplay=True)
        self.status.setText(
            ("A · Voz original: " if kind=="original" else "B · Voz procesada: ")+source.name)

    def _manual_preset(self,*_):
        if not getattr(self,"_applying_full_preset",False):
            self._mark_pending()
        if hasattr(self,"preset") and self.preset.currentText()!="Manual":
            was=self.preset.blockSignals(True)
            self.preset.setCurrentText("Manual")
            self.preset.blockSignals(was)

    def apply_preset(self,name):
        params=PRESETS.get(name)
        if params is None:return
        for widget,value in zip((self.strength,self.retune,self.humanize,
                      self.threshold,self.compression,self.highpass),params):
            was=widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(was)
        self.strength_text.setText(f"{self.strength.value()} %")
        effect=FX_PRESETS.get(name,FX_NEUTRAL)
        for control,value in zip(
            (self.character,self.character_amount,self.warmth,self.air,
             self.presence,self.deesser,self.gate,self.reverb,self.wet),
            effect):
            was=control.blockSignals(True)
            if control is self.character:control.setCurrentText(value)
            else:control.setValue(value)
            control.blockSignals(was)
        if hasattr(self,"delay"):
            self._sync_effect_availability()
            self._mark_pending()

    def _set_busy(self,busy):
        self.start_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        for w in (self.tonic,self.scale,self.strength,self.source_choice,self.browse,
                  self.update_sources_btn,self.preset,self.retune,self.humanize,
                  self.threshold,self.compression,self.highpass,self.analyze_btn,
                  self.ref_browse,self.ref_consent,self.ref_analyze,
                  self.learn_same_song,self.learn_melody,self.learn_vibrato,
                  self.learn_dynamics,self.learn_timing,self.learn_button,
                  self.character,self.character_amount,self.bypass_tune,
                  self.warmth,self.presence,self.air,self.deesser,
                  self.gate,self.reverb,self.wet,
                  self.doubler,self.delay,self.delay_ms,
                  self.stereo_width,self.output_gain_db):
            w.setEnabled(not busy)
        for strip in (self.full_presets,self.fx_presets,self.spatial_presets):
            strip.setEnabled(not busy)
        self._sync_effect_availability()

    def executable(self):
        path=ROOT/"entorno_ia"/"bin"/"python"
        return path if path.is_file() else None

    def refresh_sources(self):
        previous=self.input.text()
        self.source_choice.blockSignals(True)
        self.source_choice.clear()
        self.source_choice.addItem("— Selecciona voz —",None)
        from task_staging import project_audio_sources
        candidates=(list(self.workbench.separation_storage.items)
                    +project_audio_sources(
                        getattr(self.main,"project_dir",None),
                        ("separaciones","vocal")))
        choices=sorted({Path(stem).resolve() for stem in candidates
                        if Path(stem).is_file()
                        and Path(stem).suffix.lower() in AUDIO
                        and any(word in Path(stem).stem.casefold()
                                for word in ("vocals","voces","voice","voz"))},
                       key=lambda p:(p.name.casefold(),str(p)))
        for f in choices:self.source_choice.addItem(f.name,str(f))
        idx=self.source_choice.findData(previous)
        if idx>=0:self.source_choice.setCurrentIndex(idx)
        elif choices and not previous:self.source_choice.setCurrentIndex(1)
        self.source_choice.blockSignals(False)
        if self.source_choice.currentData():
            self.input.setText(self.source_choice.currentData())

    def _choose_source(self,index):
        path=self.source_choice.itemData(index)
        if path:self.input.setText(path)

    def browse_audio(self):
        path,_=file_dialogs.get_open_file_name(self,"Seleccionar voz aislada",
            str(Path.home()),"Audio (*.wav *.flac *.mp3 *.m4a *.aif *.aiff *.ogg)")
        if path:self.input.setText(path)

    def pick_reference(self):
        path,_=file_dialogs.get_open_file_name(self,"Referencia vocal autorizada",
            str(Path.home()),"Audio (*.wav *.flac *.mp3 *.m4a *.ogg *.aiff *.aif)")
        if path:self.reference.setText(path)

    def _analyse_source(self,reference=False):
        if self.process is not None:return
        if reference and not self.ref_consent.isChecked():
            QMessageBox.information(self,"Autorización necesaria",
                "Confirma que la persona titular de la voz autoriza utilizarla.")
            return
        file=Path(self.reference.text() if reference else self.input.text()).expanduser()
        if not file.is_file():
            QMessageBox.information(self,"Voz necesaria","Selecciona una voz solista real.")
            return
        executable=self.executable()
        if executable is None:
            QMessageBox.warning(self,"Motor ausente","El entorno IA no está disponible.")
            return
        self._operation="reference" if reference else "analyse"
        self._run_output=""
        self.status.setText("Analizando la voz de referencia…" if reference else
                            "Analizando tesitura y afinación…")
        proc=QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._log)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._error)
        self.process=proc
        self._set_busy(True)
        proc.start(str(executable),[str(ROOT/"vocal_tune_engine.py"),
                   "--input",str(file),"--analyze"])

    def analyze(self):
        self._analyse_source()

    def analyze_reference(self):
        self._analyse_source(True)

    def apply_analysis(self):
        report=self._analysis_report
        if not report:return
        self.preset.setCurrentText(report.get("suggested_preset","Estudio"))
        if float(report.get("key_fit_score",0))>=.8:
            self.tonic.setCurrentIndex(int(report["suggested_tonic"]))
            self.scale.setCurrentText(report["suggested_scale"])
        else:
            QMessageBox.information(self,"Tonalidad incierta",
                "Se ha aplicado el preset, pero la tonalidad sugerida "
                "no es suficientemente fiable para cambiarla.")
        self.status.setText("Ajustes automáticos preparados. Pulsa Afinar voz.")

    def start(self):
        if self.process is not None:return
        source=Path(self.input.text()).expanduser()
        if not source.is_file() or source.suffix.lower() not in AUDIO:
            QMessageBox.information(self,"Sin voz","Selecciona un archivo de voz solista real.")
            return
        python=self.executable()
        if not python:
            QMessageBox.warning(self,"Entorno IA ausente",
                "Falta entorno_ia con librosa y soundfile; no es posible afinar.")
            return
        # Mantener todas las versiones de afinación en una tarea recuperable;
        # una nueva ejecución jamás oculta o abandona los FLAC anteriores.
        from task_staging import unique_dest
        folder=(self.storage.processing_folder if self.storage.folder
                and self.storage.folder.is_dir() else self.storage.start())
        folder.mkdir(parents=True,exist_ok=True)
        target=unique_dest(folder,"voz_afinada.flac")
        self.processing_file=target
        self._operation="tune"
        self._run_output=""
        self.status.setText("Analizando las notas de la voz…")
        self.processing_notice.setText("Procesando los ajustes actuales…")
        proc=QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._log)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._error)
        self.process=proc
        self._set_busy(True)
        proc.start(str(python),[str(ROOT/"vocal_tune_engine.py"),
            "--input",str(source),"--output",str(target),
            "--tonic",str(self.tonic.currentIndex()),
            "--scale",str(self.scale.currentText()),
            "--strength",str(self.strength.value()),
            "--retune-ms",str(self.retune.value()),
            "--humanize",str(self.humanize.value()),
            "--threshold-cents",str(self.threshold.value()),
            "--compression",str(self.compression.value()),
            "--highpass",str(self.highpass.value()),
            "--character",self.character.currentText(),
            "--character-amount",str(self.character_amount.value()),
            "--warmth",str(self.warmth.value()),
            "--air",str(self.air.value()),
            "--presence",str(self.presence.value()),
            "--deesser",str(self.deesser.value()),
            "--gate",str(self.gate.value()),
            "--reverb",str(self.reverb.value()),
            "--wet",str(self.wet.value()),
            "--doubler",str(self.doubler.value()),
            "--delay",str(self.delay.value()),
            "--delay-ms",str(self.delay_ms.value()),
            "--stereo-width",str(self.stereo_width.value()),
            "--output-gain-db",str(self.output_gain_db.value())]+
            (["--bypass-tune"] if self.bypass_tune.isChecked() else []))

    def start_learning(self):
        """Transferencia prosódica real con control de referencia y límites."""
        if self.process is not None:return
        if not self.ref_consent.isChecked():
            QMessageBox.information(self,"Referencia autorizada",
                "Confirma primero que tienes permiso para utilizar esta voz.")
            return
        if not self.learn_same_song.isChecked():
            QMessageBox.information(self,"Misma canción necesaria",
                "Esta primera etapa funciona con dos tomas de la misma "
                "canción y la misma letra. Marca la casilla si coinciden.")
            return
        mine=Path(self.input.text()).expanduser()
        reference=Path(self.reference.text()).expanduser()
        if (not mine.is_file() or not reference.is_file()
                or mine.suffix.lower() not in AUDIO
                or reference.suffix.lower() not in AUDIO):
            QMessageBox.information(self,"Dos voces necesarias",
                "Selecciona tu pista vocal aislada y una pista de referencia "
                "autorizada. Ambas deben cantar la misma canción.")
            return
        if mine.resolve()==reference.resolve():
            QMessageBox.information(self,"Grabaciones diferentes",
                "Debes utilizar tu propia toma y otra toma de referencia.")
            return
        python=self.executable()
        if python is None:
            QMessageBox.warning(self,"Entorno IA no disponible",
                "No se encuentra el motor Python necesario para este procesamiento.")
            return
        from task_staging import unique_dest
        folder=(self.storage.processing_folder if self.storage.folder
                and self.storage.folder.is_dir() else self.storage.start())
        folder.mkdir(parents=True,exist_ok=True)
        target=unique_dest(folder,"voz_interpretada.flac")
        self.processing_file=target
        self._operation="learning"
        self._run_output=""
        self.status.setText("Analizando ambas interpretaciones vocales…")
        self.processing_notice.setText(
            "Aprendizaje asistido en proceso: no se reemplazan los originales.")
        proc=QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._log)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._error)
        self.process=proc
        self._set_busy(True)
        proc.start(str(python),[
            str(ROOT/"vocal_interpretation_engine.py"),
            "--source",str(mine),"--reference",str(reference),
            "--output",str(target),
            "--melody",str(self.learn_melody.value()),
            "--vibrato",str(self.learn_vibrato.value()),
            "--dynamics",str(self.learn_dynamics.value()),
            "--timing",str(self.learn_timing.value())])

    def _log(self):
        if self.process is None:return
        data=bytes(self.process.readAllStandardOutput()).decode("utf-8","replace")
        self._run_output+=data
        lines=[line.strip() for line in data.splitlines() if line.strip()]
        if lines:self.status.setText(lines[-1][:250])

    def _error(self,error):
        if error==QProcess.FailedToStart and self.process is not None:
            failed=self.process
            self.status.setText("No se pudo arrancar el motor vocal.")
            # El evento FailedToStart puede no producir finished(): desbloquear.
            QTimer.singleShot(0,lambda:self._finished(-1,QProcess.CrashExit)
                              if self.process is failed else None)

    def _finished(self,code,exit_status):
        proc=self.process
        if proc is None:return
        self._log()
        self.process=None
        self._set_busy(False)
        output=self.processing_file
        self.processing_file=None
        if self._operation in ("analyse","reference"):
            if code!=0 or exit_status!=QProcess.NormalExit:
                self.status.setText("No se pudo analizar. Necesitamos una voz solista.")
            else:
                import json
                try:
                    line=next(x[8:] for x in self._run_output.splitlines()
                              if x.startswith("ANALISIS "))
                    report=json.loads(line)
                    if self._operation=="reference":
                        self._reference_report=report
                        fluctuation=float(report["pitch_jitter_cents"])
                        self.humanize.setValue(max(10,min(85,round(fluctuation*.75))))
                        self.retune.setValue(170 if fluctuation>24 else 110)
                        self.reference_info.setText(
                            f"Referencia: tesitura MIDI {report['low_pitch_midi']}"
                            f"–{report['high_pitch_midi']}; variación de altura "
                            f"{fluctuation} cents. Ajustada expresividad sin clonar timbre.")
                    else:
                        self._analysis_report=report
                        self.auto_btn.setEnabled(True)
                        self.analysis_text.setText(
                            f"Tesitura MIDI {report['low_pitch_midi']}–{report['high_pitch_midi']} · "
                            f"desviación {report['median_error_cents']} cents · "
                            f"voz detectada {round(report['voiced_ratio']*100)} % · "
                            f"pico {report['peak_dbfs']} dBFS · clave sugerida "
                            f"{NOTES[int(report['suggested_tonic'])]} "
                            f"{report['suggested_scale']} "
                            f"(ajuste {report['key_fit_score']}). "
                            f"Preset recomendado: {report['suggested_preset']}.")
                    self.status.setText("Análisis completado.")
                except (ValueError,KeyError,TypeError,StopIteration):
                    self.status.setText("El motor no ha devuelto un informe válido.")
            self._operation=None
            proc.deleteLater()
            return
        if code!=0 or exit_status!=QProcess.NormalExit or not output or not output.is_file():
            from task_staging import inside
            if output and output.is_file() and inside(output,self.storage.root):
                output.unlink(missing_ok=True)  # Solo el render incompleto.
            self.status.setText("El procesamiento vocal no se completó. "
                                "Comprueba el registro y los parámetros.")
        else:
            try:
                self.storage.set_separation(output.parent)
                self.refresh_results()
                import json
                reports=[line[10:] for line in self._run_output.splitlines()
                         if line.startswith("RESULTADO ")]
                try:
                    info=json.loads(reports[-1]) if reports else {}
                except (ValueError,TypeError):info={}
                if self._operation=="learning":
                    self.status.setText(
                        "Transferencia de interpretación completada. "
                        "Tu voz sigue siendo el origen del audio. "
                        "Revisa la toma A/B antes de guardarla.")
                elif self.bypass_tune.isChecked():
                    message=("Efectos vocales renderizados sin afinación."
                             if info.get("effects_active") else
                             "Copia vocal generada: afinación desactivada y sin efectos activos.")
                    self.status.setText(message+" Escucha antes de guardar.")
                elif int(info.get("corrected_regions",0))==0:
                    self.status.setText(
                        "Voz procesada, sin notas que corregir: se conserva "
                        "la altura y se aplica el procesamiento configurado.")
                else:
                    self.status.setText("Afinación terminada. Escucha y compara antes de guardar.")
                self.processing_notice.setText(
                    "Resultado generado con los ajustes actuales. "
                    "Cualquier cambio posterior requiere «Procesar voz» de nuevo.")
                self.resultsChanged.emit()
            except (ValueError,OSError) as exc:
                self.status.setText("No se ha podido validar la salida: "+str(exc))
        proc.deleteLater()

    def cancel(self):
        if self.process is not None:
            self.process.kill()
            self.status.setText("Cancelando análisis…")

    def refresh_results(self):
        valid=[Path(p) for p in self.storage.items if Path(p).is_file()]
        self.table.setRowCount(len(valid))
        for index,path in enumerate(valid):
            label=("Interpretación asistida" if path.name.startswith("voz_interpretada")
                   else "Voz afinada")
            self.table.setItem(index,0,QTableWidgetItem(label))
            item=QTableWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.UserRole,str(path))
            self.table.setItem(index,1,item)

    def preview_selected(self,row,col):
        item=self.table.item(row,1)
        if item:
            p=Path(item.data(Qt.UserRole))
            if p.is_file() and self.preview.isVisible():
                was=self.compare_choice.blockSignals(True)
                self.compare_choice.setCurrentIndex(1)
                self.compare_choice.blockSignals(was)
                self.preview.load(p)

    def save_selected(self):
        selected=[Path(self.table.item(idx.row(),1).data(Qt.UserRole))
                  for idx in self.table.selectionModel().selectedRows()
                  if self.table.item(idx.row(),1)]
        if not selected:
            QMessageBox.information(self,"Sin resultados",
                "Selecciona la voz que deseas guardar.")
            return
        from export_dialog import export_files
        files=export_files(self,selected,getattr(self.main,"project_dir",None),
                           "Guardar voz afinada",kind="vocal")
        if files:
            self.storage.saved.update(str(p) for p in selected)
            self.storage.manifest()
            self.status.setText(f"Exportados {len(files)} resultado(s) vocales.")

    def discard(self):
        if self.process is not None:
            QMessageBox.information(self,"Proceso activo","Finaliza la afinación antes de descartar.")
            return
        if not self.storage.folder:return
        ans=QMessageBox.question(self,"Descartar voz temporal",
            "¿Eliminar solo esta afinación temporal, sin borrar la voz original "
            "ni los archivos ya guardados?",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if ans!=QMessageBox.Yes:return
        self.preview.clear()
        self.storage.discard()
        self.refresh_results()
        self.resultsChanged.emit()
        self.status.setText("Afinación temporal descartada.")

    def switch_storage(self,store):
        if self.process is not None:return False
        self.preview.clear()
        self.storage=store
        self.input.clear()
        self.reference.clear()
        self.ref_consent.setChecked(False)
        self.learn_same_song.setChecked(False)
        self.bypass_tune.setChecked(False)
        self._analysis_report=None
        self._reference_report=None
        self.auto_btn.setEnabled(False)
        self.analysis_text.setText("Sin análisis de la nueva sesión.")
        self.reference_info.setText("Sin referencia vocal autorizada en este proyecto.")
        # main.project_dir aún puede ser el proyecto anterior durante
        # switch_project(). Las fuentes se listan DESPUÉS en bind_project().
        self.source_choice.blockSignals(True)
        self.source_choice.clear()
        self.source_choice.addItem("— Selecciona voz —",None)
        self.source_choice.blockSignals(False)
        self.refresh_results()
        self.status.setText("Proyecto cambiado. Solo aparecen las voces de este proyecto.")
        return True
