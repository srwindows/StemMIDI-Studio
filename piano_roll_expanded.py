"""Panel superior de Piano Roll ampliado.
El editor inferior (PianoOverview) permanece intacto.
"""
from __future__ import annotations
import tempfile
from pathlib import Path
import copy
import mido
from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget,QHBoxLayout,QVBoxLayout,QGridLayout,QLabel,QPushButton,QComboBox,
    QListWidget,QListWidgetItem,QSpinBox,QSlider,QCheckBox,QLineEdit,
    QMessageBox,QDialog,QFrame,QSizePolicy,
)
from piano_roll_tools import SCALES,PROGRESSIONS,quantize,clean,melody,chords


class PianoRollExpanded(QWidget):
    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self._scratch=tempfile.TemporaryDirectory(prefix="stemmidi_piano_roll_")
        self._draft=Path(self._scratch.name)/"piano_roll_borrador.mid"
        self._preview=Path(self._scratch.name)/"piano_roll_previsualizacion.mid"
        self._draft_active=False
        self._new_draft_seq=0
        self._recovery_sessions=[]  # Recupera composiciones completas tras «Nuevo MIDI».
        self._catalog_signature=None
        self._last_catalog_refresh=0.
        self.setObjectName("pianoExtendedTools")
        # La antigua altura de 264 px amontonaba controles y los hacía
        # invadir filas vecinas. Reservar altura real sin usar scroll.
        self.setMinimumHeight(475)
        self.setMaximumHeight(475)
        self.setStyleSheet("""
          QWidget#pianoExtendedTools{background:transparent;color:#d8f6ff;}
          QFrame#rollToolsColumn{background:#082149;border:1px solid #2575bc;border-radius:6px;}
          QListWidget#rollMidiFiles{background:#051731;color:#e6fbff;border:1px solid #4ba8e7;
            border-radius:5px;alternate-background-color:#0b2750;}
          QListWidget#rollMidiFiles::item{padding:3px 5px;min-height:22px;}
          QListWidget#rollMidiFiles::item:selected{background:#156ab5;color:white;}
          QLabel{background:transparent;color:#c5efff;font-size:12px;}
          QPushButton{background:#08559c;color:white;border:1px solid #51bcf4;border-radius:5px;
            padding:3px 7px;min-height:25px;font-size:12px;}
          QPushButton:hover{background:#117cca;}
          QComboBox,QSpinBox,QLineEdit{background:#061b3d;color:#ecfbff;border:1px solid #378cce;
            border-radius:4px;min-height:17px;font-size:12px;}
          QCheckBox{color:#daf6ff;}
          QSlider::groove:horizontal{height:5px;background:#103d68;border-radius:2px;}
          QSlider::handle:horizontal{background:#41d8f7;border:1px solid #d0faff;
            width:13px;margin:-5px 0;border-radius:6px;}
        """)
        root=QVBoxLayout(self)
        root.setContentsMargins(4,4,4,5)
        root.setSpacing(7)
        cols=QHBoxLayout();cols.setSpacing(10)
        root.addLayout(cols,1)
        left=self._column(cols,255,1)
        self.project_column=left
        left.addWidget(self._caption("MIDI DEL PROYECTO"))
        self.files=QListWidget(self)
        self.files.setObjectName("rollMidiFiles")
        self.files.setAlternatingRowColors(True)
        # QListWidget requests 256 px by default and starves the central
        # controls: let Qt shrink this catalog without any scrolling panes.
        self.files.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Expanding)
        self.files.setMinimumHeight(90)
        self.files.itemClicked.connect(self.select_file)
        left.addWidget(self.files,1)
        load=QPushButton("Cargar MIDI…")
        load.clicked.connect(self.import_file)
        left.addWidget(load)

        centre=self._column(cols,370,2)
        self.correction_column=centre
        centre.addWidget(self._caption("CUANTIZACIÓN · CORRECCIÓN"))
        row=QHBoxLayout();row.setSpacing(3)
        self.quant_div=QComboBox()
        for div in (4,8,16,32,64):self.quant_div.addItem("1/"+str(div),div)
        self.quant_div.setCurrentIndex(2)
        self.quant_div.setMaximumWidth(66)
        row.addWidget(self.quant_div)
        self.quant_strength=self._slider(0,100,100," %")
        row.addWidget(self.quant_strength,1)
        row.addWidget(self.quant_strength.readout)
        centre.addLayout(row)
        row=QHBoxLayout();row.setSpacing(4)
        self.quant_ends=QCheckBox("Ajustar finales")
        row.addWidget(self.quant_ends)
        self.quant_button=QPushButton("Cuantizar")
        self.quant_button.clicked.connect(self.quantize)
        row.addWidget(self.quant_button)
        centre.addLayout(row)
        self.min_duration=self._add_slider(centre,"Duración mín.",1,100,8," %")
        self.min_velocity=self._add_slider(centre,"Velocidad mín.",1,127,8)
        self.sensitivity=self._add_slider(centre,"Sensibilidad",0,100,65," %")
        self.sensitivity.setToolTip(
            "0: umbrales clásicos. 65: detecta además fragmentos y ecos"
            " redundantes. 100: más agresivo; utiliza Deshacer si es necesario.")
        row=QHBoxLayout();row.setSpacing(4)
        self.remove_scale=QCheckBox("Fuera escala")
        self.remove_beat=QCheckBox("Fuera rejilla")
        self.remove_beat.setToolTip("Opcional: descarta ataques alejados de la rejilla.")
        row.addWidget(self.remove_scale);row.addWidget(self.remove_beat)
        centre.addLayout(row)
        row=QHBoxLayout();row.setSpacing(6)
        self.clean_button=QPushButton("Limpiar notas fantasma")
        self.clean_button.setToolTip(
            "Limpiar todas las pistas MIDI, o solo las notas seleccionadas"
            " si marcas «Solo seleccionado». Se puede Deshacer.")
        self.clean_button.clicked.connect(self.cleanup_notes)
        self.clean_button.setStyleSheet("font-size:12px;padding:2px 5px;")
        row.addWidget(self.clean_button,1)
        self.clean_only_selected=QCheckBox("Solo seleccionado")
        self.clean_only_selected.setStyleSheet("font-size:12px;spacing:4px;")
        self.clean_only_selected.setObjectName("pianoCleanOnlySelected")
        self.clean_only_selected.setChecked(False)
        self.clean_only_selected.setToolTip(
            "Marcado: solo las notas seleccionadas de cualquier pista."
            " Desmarcado: todas las notas MIDI de todas las pistas.")
        row.addWidget(self.clean_only_selected)
        centre.addLayout(row)

        right=self._column(cols,360,2)
        self.composition_column=right
        right.addWidget(self._caption("COMPOSICIÓN · ARMONÍA EXPRESIVA"))
        row=QHBoxLayout();row.setSpacing(5)
        self.instrument_style=QComboBox(self)
        self.instrument_style.setObjectName("compositionSoundfontGroup")
        self.instrument_style.setToolTip(
            "Grupos REALES del SoundFont cargado; idénticos a los del selector inferior.")
        self.instrument_style.currentIndexChanged.connect(self._style_from_top)
        self.harmony_mode=QComboBox(self)
        self.harmony_mode.addItems(("Adaptarse al MIDI","Composición nueva"))
        self.harmony_mode.setToolTip(
            "Adaptarse: armonizar con notas y acordes existentes de todas"
            " las pistas. Si está vacío, crear una progresión nueva.")
        row.addWidget(self.instrument_style,1)
        row.addWidget(self.harmony_mode,1)
        right.addLayout(row)
        self.instrument_preset=QComboBox(self)
        self.instrument_preset.setObjectName("compositionSoundfontPreset")
        self.instrument_preset.setToolTip(
            "Instrumentos REALES de este grupo del SF2. Elegir aquí"
            " selecciona el mismo preset en el transporte inferior.")
        self.instrument_preset.currentIndexChanged.connect(self._preset_from_top)
        right.addWidget(self.instrument_preset)
        row=QHBoxLayout();row.setSpacing(5)
        self.tonic=QComboBox()
        self.tonic.addItems(("Do","Do♯","Re","Mi♭","Mi","Fa","Fa♯",
                             "Sol","La♭","La","Si♭","Si"))
        self.tonic.setMaximumWidth(76)
        self.scale=QComboBox();self.scale.addItems(tuple(SCALES))
        row.addWidget(self.tonic)
        row.addWidget(self.scale,1)
        self.auto_tonality=QCheckBox("Auto",self)
        self.auto_tonality.setChecked(True)
        self.auto_tonality.setToolTip(
            "Detectar tonalidad desde las notas existentes y adaptar"
            " melodía y acordes. Si el MIDI está vacío, conservar"
            " Do/Re/etc y la escala que has elegido.")
        row.addWidget(self.auto_tonality)
        right.addLayout(row)
        # Two adjacent half-width sliders: no excessive vertical rows.
        row=QHBoxLayout();row.setSpacing(7)
        self.bars=self._half_slider(row,"Compases",1,64,4)
        self.octave=self._half_slider(row,"Octava",2,6,4)
        right.addLayout(row)
        tempo_row=QHBoxLayout();tempo_row.setSpacing(5)
        tempo_row.addWidget(QLabel("Tempo"))
        self.tempo_bpm=self._slider(35,300,120," BPM")
        self.tempo_bpm.setObjectName("compositionTempoBpm")
        self.tempo_bpm.setToolTip(
            "Tempo para componer: a 73 BPM crea frases más espaciadas y"
            " duraciones largas; a tempo rápido puede incorporar más"
            " ataques. No altera los BPM de reproducción de la canción,"
            " que se ajustan abajo en el piano roll.")
        tempo_row.addWidget(self.tempo_bpm,1)
        tempo_row.addWidget(self.tempo_bpm.readout)
        right.addLayout(tempo_row)
        self._tempo_debounce=QTimer(self)
        self._tempo_debounce.setSingleShot(True)
        self._tempo_debounce.setInterval(250)
        self._tempo_debounce.timeout.connect(self.apply_composition_tempo)
        self.tempo_bpm.valueChanged.connect(
            lambda _:self._tempo_debounce.start())
        self.tempo_bpm.sliderReleased.connect(self.apply_composition_tempo)
        # Compensar la nueva fila reduciendo solo el espaciado vertical
        # de esta columna, sin achicar el piano roll ni usar scroll.
        right.setSpacing(4)
        row=QHBoxLayout();row.setSpacing(7)
        self.density=self._half_slider(row,"Densidad",10,100,75,"%")
        self.inversion=self._half_slider(row,"Inversión",0,3,0)
        right.addLayout(row)
        row=QHBoxLayout();row.setSpacing(5)
        self.rhythm=QComboBox()
        for div in (4,8,16,32):self.rhythm.addItem("1/"+str(div),div)
        self.rhythm.setCurrentIndex(1)
        self.rhythm.setToolTip("Resolución rítmica (admite valores irregulares).")
        row.addWidget(QLabel("Ritmo"))
        row.addWidget(self.rhythm)
        self.seed=self._slider(0,9999,1)
        self.seed.setToolTip(
            "Semilla reproducible si está desmarcada «Variar cada vez».")
        row.addWidget(QLabel("Semilla"))
        row.addWidget(self.seed,1)
        row.addWidget(self.seed.readout)
        right.addLayout(row)
        row=QHBoxLayout();row.setSpacing(6)
        self.random_each=QCheckBox("Variar cada vez")
        self.random_each.setChecked(True)
        self.random_each.setToolTip(
            "Activado: cada generación utiliza una semilla nueva."
            " Desactivado: resultado reproducible con la Semilla.")
        # La semilla SIEMPRE se puede mover: con variación aleatoria
        # actúa como semilla base, mezclada con entropía de cada toma.
        self.seed.setToolTip(
            "Deslizador siempre activo. «Variar cada vez» mezcla su valor"
            " con una semilla nueva; desactivado reproduce el resultado.")
        self.melody_pedal=QCheckBox("Pedal CC64")
        self.melody_pedal.setChecked(True)
        self.melody_pedal.setToolTip(
            "Añade pedal de resonancia MIDI CC64 a las frases de piano."
            " En violín, trombón y guitarra se usa articulación, sin pedal.")
        self.auto_quality=QCheckBox("Revisión musical")
        self.auto_quality.setObjectName("compositionAutoQualityReview")
        self.auto_quality.setChecked(True)
        self.auto_quality.setToolTip(
            "Comparar cuatro interpretaciones, valorar armonía,"
            " fraseo, expresión y registro, corregir fallos leves y"
            " elegir la mejor. Puntuación HEURÍSTICA, no evaluación"
            " humana ni garantía de calidad artística. No modifica"
            " el MIDI original.")
        row.addWidget(self.random_each)
        row.addWidget(self.melody_pedal)
        row.addWidget(self.auto_quality)
        right.addLayout(row)
        settings=QHBoxLayout();settings.setSpacing(6)
        self.pedal_amount=self._half_slider(
            settings,"Pedal",0,100,75,"%")
        self.pedal_amount.setObjectName("compositionPedalDuration")
        self.pedal_amount.setToolTip(
            "Intensidad temporal del pedal armónico, NO volumen."
            " El motor levanta el pedal antes de cada cambio de acorde,"
            " reduce su duración en registros graves y permite una"
            " resonancia mayor a partir de Do5 (MIDI 72)."
            " 100 % siempre respeta esos límites para evitar suciedad.")
        self.dynamics_amount=self._half_slider(
            settings,"Expresión",0,100,100,"%")
        self.dynamics_amount.setObjectName("compositionDynamics")
        self.dynamics_amount.setToolTip(
            "0% uniforme; 100% contraste de velocity y curvas CC11"
            " para piano, violín y otros instrumentos.")
        self.melody_pedal.toggled.connect(self.pedal_amount.setEnabled)
        right.addLayout(settings)
        self.gen_melody=QPushButton("Generar melodía expresiva")
        self.gen_melody.setToolTip(
            "Genera DESDE LA GUÍA del Piano Roll en los compases indicados."
            " Adapta notas a los acordes de esa sección y conserva"
            " todas las notas anteriores y posteriores.")
        self.gen_melody.clicked.connect(self.generate_melody)
        self.auto_registers=QCheckBox("Separar registros")
        self.auto_registers.setObjectName("compositionSeparateRegisters")
        self.auto_registers.setChecked(True)
        self.auto_registers.setToolTip(
            "Melodía normalmente desde Do4 (C4 MIDI 60) y acordes debajo."
            " Si ya existen notas, no cruzar los registros de ambas"
            " partes. Desactívalo solo si quieres superponer voces.")
        melody_line=QHBoxLayout();melody_line.setSpacing(5)
        melody_line.addWidget(self.gen_melody,1)
        melody_line.addWidget(self.auto_registers)
        right.addLayout(melody_line)
        row=QHBoxLayout();row.setSpacing(5)
        self.progression=QComboBox()
        # Etiquetas cortas elegidas por el usuario; las claves del motor
        # permanecen en itemData, sin alterar el entrenamiento ni modelos.
        from composition_learned import LABEL as classic_key
        from composition_personal_learned import LABEL as personal_key,load_model
        for key in PROGRESSIONS:
            title="Clásico" if key==classic_key else key
            self.progression.addItem(title,key)
        if load_model() is not None:
            self.progression.addItem("Mejorado",personal_key)
        self.progression.setToolTip(
            "Clásico: modelo simbólico clásico. Mejorado: modelo privado"
            " probabilístico de acordes e intervalos; no son géneros"
            " verificados ni una evaluación humana de calidad musical.")
        self.progression.setToolTip(
            "Progresión base cuando se empieza de cero.")
        self.seventh=QCheckBox("7ª")
        # Perfiles originales portables + huellas Roland opcionales.
        # La colección Roland nunca sustituye ni es requisito de rock,
        # salsa, cumbia, 8 beat y los demás estilos del generador.
        from rhythm_style_catalog import available_styles
        from composition_style_library import grouped_style_names
        self.rhythm_style=QComboBox(self)
        self.rhythm_style.setObjectName("compositionRolandRhythmStyle")
        self.rhythm_style.addItem("Sin patrón",None)
        def heading(title):
            self.rhythm_style.addItem("── "+title+" ──",None)
            item=self.rhythm_style.model().item(self.rhythm_style.count()-1)
            if item is not None:item.setEnabled(False)
        for group,choices in grouped_style_names().items():
            heading(group)
            for code,label in choices:
                self.rhythm_style.addItem(label,code)
        available=available_styles()
        if available:
            heading("Roland FANTOM · ritmos originales")
            for alias,source in (("Balada romántica · Roland","balada _1"),
                                 ("Balada pop · Roland","balada _2")):
                if source in available:self.rhythm_style.addItem(alias,source)
            for name in sorted(available,key=str.casefold):
                label=name.replace("_"," ").strip()
                if label.lower().startswith("rock"):
                    label="Rock · Roland ("+label+")"
                elif label.lower().startswith("hard rock"):
                    label="Hard rock · Roland ("+label+")"
                self.rhythm_style.addItem(label,name)
        self.rhythm_style.setMaxVisibleItems(20)
        self.rhythm_style.setToolTip(
            "72 estilos musicales originales del compositor organizados"
            " por familia (siempre disponibles), más los 59 ritmos"
            " Roland FANTOM privados cuando está conectado el disco."
            " Cambian ataques, acentos y síncopa de acordes y melodía;"
            " no son pistas completas de batería ni audio de acompañamiento.")
        row.addWidget(self.progression,1)
        row.addWidget(QLabel("Estilo"))
        row.addWidget(self.rhythm_style,1)
        row.addWidget(self.seventh)
        right.addLayout(row)
        row=QHBoxLayout();row.setSpacing(5)
        self.arpeggiate=QCheckBox("Arpegiados")
        self.arpeggiate.setToolTip(
            "Acordes desplegados en notas sucesivas y no en bloques simultáneos.")
        self.ligatures=QCheckBox("Ligaduras")
        self.ligatures.setObjectName("compositionLigatures")
        self.ligatures.setChecked(True)
        self.ligatures.setToolTip(
            "Generar frases legato y prolongar notas comunes entre acordes"
            " sin usar CC64. Puedes desactivar el ligado sin desactivar"
            " el pedal; también está el botón «Ligar notas» para editar"
            " las notas seleccionadas manualmente.")
        self.gen_chords=QPushButton("Generar acordes")
        self.gen_chords.setToolTip(
            "Generar DESDE LA GUÍA. Acordes dentro de su banda de"
            " octavas, por debajo de la melodía, con arpegios de"
            " subida y bajada. Conserva los compases fuera del tramo.")
        self.gen_chords.clicked.connect(self.generate_chords)
        self.analyze_midi=QPushButton("Evaluar MIDI")
        self.analyze_midi.setObjectName("compositionAnalyzeMidi")
        self.analyze_midi.setToolTip(
            "Analiza las pistas del MIDI cargado e informa de"
            " posibles problemas armónicos, de fraseo y expresión."
            " No edita ni guarda nada.")
        self.analyze_midi.clicked.connect(self.evaluate_open_midi)
        row.addWidget(self.arpeggiate)
        row.addWidget(self.ligatures)
        row.addWidget(self.gen_chords,1)
        row.addWidget(self.analyze_midi)
        right.addLayout(row)
        # Controles compactos: al añadir BPM no comprimir verticalmente
        # los combos de 35 px, que antes se solapaban 4 px al redistribuir.
        for combo in (self.instrument_style,self.instrument_preset,
                      self.harmony_mode,self.tonic,self.scale,
                      self.progression,self.rhythm,self.rhythm_style):
            combo.setFixedHeight(29)
        self.instrument_style.setEnabled(False)
        self.instrument_preset.setEnabled(False)
        self.gen_melody.setEnabled(False)
        self.gen_chords.setEnabled(False)

        actions=QHBoxLayout();actions.setSpacing(8)
        actions.addWidget(QLabel("Nombre"))
        self.new_name=QLineEdit(self)
        self.new_name.setPlaceholderText("nombre del MIDI")
        actions.addWidget(self.new_name,1)
        self.new=QPushButton("Nuevo MIDI")
        self.new.clicked.connect(self.create_new)
        self.new.setToolTip("Abre un MIDI vacío sin destruir la composición anterior.")
        actions.addWidget(self.new)
        self.recover_new=QPushButton("Recuperar anterior")
        self.recover_new.setObjectName("pianoRecoverPreviousSession")
        self.recover_new.setEnabled(False)
        self.recover_new.setToolTip("Recupera todas las notas, pistas, tempo y edición anteriores a «Nuevo MIDI».")
        self.recover_new.clicked.connect(self.restore_previous_new)
        actions.addWidget(self.recover_new)
        self.add=QPushButton("Añadir MIDI a la lista")
        self.add.clicked.connect(self.commit_to_project)
        actions.addWidget(self.add)
        root.addLayout(actions)
        # Control de duración MIDI: no desafina la altura (pitch), solo
        # prolonga el final de las notas seleccionadas.
        sustain_row=QHBoxLayout();sustain_row.setSpacing(8)
        title=QLabel("Sostenido · notas seleccionadas")
        title.setToolTip("Alarga la duración de las notas seleccionadas; no cambia su altura ni su velocidad.")
        sustain_row.addWidget(title)
        self.sustain_percent=self._slider(100,400,150," %")
        self.sustain_percent.setObjectName("pianoSelectedSustain")
        self.sustain_percent.setToolTip(
            "100 % = misma duración; 200 % = doble duración."
            " No afecta a notas no seleccionadas.")
        sustain_row.addWidget(self.sustain_percent,1)
        sustain_row.addWidget(self.sustain_percent.readout)
        self.sustain_apply=QPushButton("Aplicar duración")
        self.sustain_apply.setToolTip(
            "Prolongar las notas seleccionadas según el deslizante."
            " Un único Deshacer recupera todas.")
        self.sustain_apply.clicked.connect(self.apply_sustain)
        sustain_row.addWidget(self.sustain_apply)
        self.tie_selected=QPushButton("Ligar notas")
        self.tie_selected.setObjectName("pianoTieSelectedNotes")
        self.tie_selected.setToolTip(
            "Selecciona al menos dos notas de una pista. Une las repetidas"
            " de igual altura en un solo sonido; con distintas alturas"
            " aplica legato sin pisar el pedal CC64. Se puede Deshacer.")
        self.tie_selected.clicked.connect(self.apply_ties_to_selection)
        sustain_row.addWidget(self.tie_selected)
        root.addLayout(sustain_row)
        self.info=QLabel("Selecciona un MIDI o crea uno nuevo. El original no se modifica.")
        self.info.setMinimumHeight(16)
        root.addWidget(self.info)
        # Si se abre un MIDI desde cualquier otro módulo, mostrar su BPM
        # sin emitir cambios ni crear una acción Deshacer innecesaria.
        e=self.editor()
        e.midiOpened.connect(lambda _:self._sync_composer_bpm())
        e.tempo_apply.clicked.connect(self._sync_composer_bpm)
        # Undo/Redo/Reset también actualizan el control de tempo del
        # editor inferior; reflejar esos valores arriba sin editar notas.
        e.tempo_bpm.valueChanged.connect(
            lambda _:self.home._sync_piano_song_tempo())
        self.refresh_files(force=True)
        self._sync_composer_bpm()

    @staticmethod
    def _caption(text):
        label=QLabel(text)
        label.setStyleSheet("color:#76efff;font-weight:800;")
        return label

    def _column(self,parent,width,stretch):
        frame=QFrame(self);frame.setObjectName("rollToolsColumn")
        frame.setMinimumWidth(width)
        lay=QVBoxLayout(frame)
        lay.setContentsMargins(10,8,10,8);lay.setSpacing(6)
        parent.addWidget(frame,stretch)
        return lay

    @staticmethod
    def _slider(minimum,maximum,value,suffix=""):
        control=QSlider(Qt.Horizontal)
        control.setRange(minimum,maximum)
        control.setValue(value)
        control.setMinimumWidth(25)
        readout=QLabel(str(value)+suffix)
        readout.setMinimumWidth(32 if maximum<=100 else 25)
        readout.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        control.readout=readout
        control.valueChanged.connect(
            lambda v,r=readout,x=suffix:r.setText(str(v)+x))
        return control

    def _add_slider(self,layout,title,minimum,maximum,value,suffix=""):
        control=self._slider(minimum,maximum,value,suffix)
        row=QHBoxLayout();row.setSpacing(8)
        text=QLabel(title)
        text.setMinimumWidth(74 if len(title)<11 else 96)
        row.addWidget(text)
        row.addWidget(control,1)
        row.addWidget(control.readout)
        layout.addLayout(row)
        return control

    def _half_slider(self,layout,title,minimum,maximum,value,suffix=""):
        widget=self._slider(minimum,maximum,value,(" "+suffix if suffix else ""))
        cell=QHBoxLayout();cell.setSpacing(3)
        label=QLabel(title)
        label.setMinimumWidth(49 if len(title)<8 else 57)
        cell.addWidget(label)
        cell.addWidget(widget,1)
        widget.readout.setMinimumWidth(19 if maximum<10 else 31)
        cell.addWidget(widget.readout)
        layout.addLayout(cell,1)
        return widget

    @staticmethod
    def _spin(minimum,maximum,value,suffix=""):
        control=QSpinBox()
        control.setRange(minimum,maximum);control.setValue(value)
        if suffix:control.setSuffix(suffix)
        return control

    def editor(self):
        return self.home.workbench.piano

    def refresh_files(self,force=False):
        import time
        now=time.monotonic()
        if not force and now-self._last_catalog_refresh<3.:
            return
        self._last_catalog_refresh=now
        candidates=[p for p in self.home._gather_files()
                    if p.suffix.lower() in (".mid",".midi") and p.is_file()]
        # Incluye los MIDI importados que están abiertos por el usuario.
        if self.home.selected_midi and Path(self.home.selected_midi).is_file():
            candidates.append(Path(self.home.selected_midi))
        files=sorted({str(Path(p).resolve()):Path(p).resolve() for p in candidates}.values(),
                     key=lambda p:(p.name.casefold(),str(p).casefold()))
        signature=tuple(str(p) for p in files)
        if not force and signature==self._catalog_signature:return
        self._catalog_signature=signature
        current=(str(self.home.selected_midi.resolve()) if self.home.selected_midi
                 else "")
        self.files.blockSignals(True)
        self.files.clear()
        for item in files:
            entry=QListWidgetItem(item.name)
            entry.setData(Qt.UserRole,str(item))
            entry.setToolTip(str(item))
            self.files.addItem(entry)
            if str(item)==current and not self._draft_active:
                self.files.setCurrentItem(entry)
        self.files.blockSignals(False)

    def _stop_piano_transport(self):
        # Al cambiar de composición no continuar sonando el MIDI anterior.
        manager=self.home._floating_manager
        window=manager.windows.get(self.home.piano_card)
        transport=(getattr(window,"float_transport",None) if window else
                   manager._mini_players.get(self.home.piano_card))
        if transport is not None and hasattr(transport,"piano_live"):
            transport.piano_live.stop()
            self.home.piano_preview.playhead_tick=None
            self.home.piano_preview.update()

    def select_file(self,item):
        path=Path(item.data(Qt.UserRole))
        if not path.is_file():return
        editor=self.editor()
        if not editor.open_midi(path):return
        self._sync_composer_bpm()
        self._stop_piano_transport()
        self.home.change_grid(self.home.grid_choice.currentText())
        self._draft_active=False
        self.home.selected_midi=path
        self.home._set_piano_active_name(path)
        index=self.home.midi_choice.findData(str(path))
        if index<0:
            self.home.midi_choice.addItem(path.name,str(path))
            index=self.home.midi_choice.count()-1
        self.home.midi_choice.setCurrentIndex(index)
        self.home.piano_preview.set_midi(path)
        self.home._update_midi_stats(path)
        self.home.piano_card.header.setText("Piano Roll · "+path.name)
        self.new_name.setText(path.stem+"_editado")
        self.info.setText(f"Editando copia en memoria: {path.name}")

    def import_file(self):
        import file_dialogs
        filename,_=file_dialogs.get_open_file_name(self,"Cargar MIDI","","MIDI (*.mid *.midi)")
        if not filename:return
        path=Path(filename)
        if not path.is_file():return
        if self.editor().open_midi(path):
            self._sync_composer_bpm()
            self._stop_piano_transport()
            self.home.change_grid(self.home.grid_choice.currentText())
            self._draft_active=False
            self.home.selected_midi=path
            self.home._set_piano_active_name(path)
            index=self.home.midi_choice.findData(str(path))
            if index<0:
                self.home.midi_choice.addItem(path.name,str(path))
                index=self.home.midi_choice.count()-1
            self.home.midi_choice.setCurrentIndex(index)
            self.new_name.setText(path.stem+"_editado")
            self.refresh_files(force=True)

    def _capture_session(self):
        """Instantánea real del MIDI y su historial, no solo de una pista."""
        e=self.editor()
        return {
            "midi":copy.deepcopy(e.midi),
            "tracks":copy.deepcopy(e.tracks),
            "initial":copy.deepcopy(getattr(e,"_initial_tracks",None)),
            "history":copy.deepcopy(e.history),
            "future":copy.deepcopy(e.future),
            "dirty":bool(e.dirty),"path":e.current_path,
            "track_index":e.track_index,
            "draft":self._draft,"draft_active":self._draft_active,
            "name":self.new_name.text(),
            "selected_midi":self.home.selected_midi,
        }

    def restore_previous_new(self):
        """Deshace incluso «Nuevo MIDI», cuyo open_midi vacía el historial."""
        if not self._recovery_sessions:return False
        snap=self._recovery_sessions.pop()
        self._stop_piano_transport()
        e=self.editor()
        e.midi=copy.deepcopy(snap["midi"])
        e.tracks=copy.deepcopy(snap["tracks"])
        e._initial_tracks=copy.deepcopy(snap["initial"])
        e.history=copy.deepcopy(snap["history"])
        e.future=copy.deepcopy(snap["future"])
        e.dirty=snap["dirty"]
        e.current_path=snap["path"]
        e.track_index=max(0,min(snap["track_index"],len(e.tracks)-1))
        e.selected_index=None
        e.selected_indices.clear()
        e.file_label.setText(e.current_path.name if e.current_path else "Sin archivo")
        e.update_track_list()
        e.tempo_bpm.setValue(round(e.current_bpm()))
        e.redraw()
        self._draft=snap["draft"]
        self._draft_active=snap["draft_active"]
        self.new_name.setText(snap["name"])
        self.home.selected_midi=snap["selected_midi"]
        self.home._set_piano_active_name(
            self.home.selected_midi,unsaved=self._draft_active)
        self.home.piano_card.header.setText(
            "Piano Roll · Nuevo sin guardar" if self._draft_active
            else "Piano Roll · MIDI")
        if self.home.selected_midi is not None:
            index=self.home.midi_choice.findData(str(self.home.selected_midi))
            if index>=0:
                with QSignalBlocker(self.home.midi_choice):
                    self.home.midi_choice.setCurrentIndex(index)
        self.home.piano_preview._set_note_selection(set())
        self.home.piano_preview.set_live_editor(e)
        self._sync_composer_bpm()
        if hasattr(self.home,"_sync_piano_song_tempo"):
            self.home._sync_piano_song_tempo()
        self.recover_new.setEnabled(bool(self._recovery_sessions))
        self.refresh_files(force=True)
        self.info.setText("Composición anterior recuperada con todas sus pistas y ediciones.")
        return True

    def create_new(self):
        # Guardar la sesión ANTES de abrir, porque open_midi borra Undo/Redo.
        editor=self.editor()
        previous=self._capture_session() if editor.midi is not None else None
        midi=mido.MidiFile(type=1,ticks_per_beat=480)
        meta=mido.MidiTrack()
        meta.append(mido.MetaMessage("track_name",name="Composición",time=0))
        bpm=(self.home.piano_song_tempo.value()
             if hasattr(self.home,"piano_song_tempo") else 120)
        meta.append(mido.MetaMessage(
            "set_tempo",tempo=mido.bpm2tempo(bpm),time=0))
        meta.append(mido.MetaMessage("time_signature",
                                     numerator=4,denominator=4,time=0))
        meta.append(mido.MetaMessage("end_of_track",time=0))
        midi.tracks.append(meta)
        candidate=Path(self._scratch.name)/f"piano_roll_borrador_{self._new_draft_seq}.mid"
        midi.save(str(candidate))
        if not editor.open_midi(candidate):
            candidate.unlink(missing_ok=True)
            return
        if previous is not None:
            self._recovery_sessions.append(previous)
            self._recovery_sessions=self._recovery_sessions[-12:]
            self.recover_new.setEnabled(True)
        self._stop_piano_transport()
        self.home.change_grid(self.home.grid_choice.currentText())
        self._new_draft_seq+=1
        self._draft=candidate
        self._draft_active=True
        self.home.selected_midi=None
        self.home._set_piano_active_name(None,unsaved=True)
        self.home.piano_preview.set_midi(self._draft)
        self.home.piano_card.header.setText("Piano Roll · Nuevo sin guardar")
        self.files.clearSelection()
        self.info.setText(
            "MIDI nuevo en blanco. Puedes recuperar la composición anterior "
            "con «Recuperar anterior» o con Deshacer.")
        if not self.new_name.text().strip():
            self.new_name.setText("composicion_nueva")

    def _ensure_editor(self):
        editor=self.editor()
        if editor.midi is not None and editor.tracks:return editor
        self.info.setText("Selecciona un MIDI o pulsa «Nuevo MIDI en blanco».")
        return None

    def apply_composition_tempo(self):
        """El tempo del generador influye en fraseo, densidad y duración;
        NUNCA cambia el set_tempo real de la canción."""
        self._tempo_debounce.stop()
        self.info.setText(
            f"Composición a {self.tempo_bpm.value()} BPM: tempo de generación. "
            "El BPM del archivo MIDI se cambia únicamente abajo, en «Tempo canción».")

    def _sync_composer_bpm(self):
        """El generador mantiene su BPM propio incluso al cargar otro MIDI."""
        # No sincronizar con la canción: son controles independientes.
        return

    def _publish_preview(self):
        editor=self.editor()
        # El modelo MIDI ya reside en memoria. Serializarlo entero a disco
        # temporal tras cada retoque era lento y causaba tirones innecesarios.
        # Solo exportar al pulsar «Añadir MIDI» o iniciar la reproducción.
        self.home.piano_preview.set_live_editor(editor)
        editor.redraw()
        editor.update_track_list()

    def _choose_note_scope(self,action,selected_count):
        """Tres decisiones explícitas en un diálogo hijo del panel flotante.

        Nunca aplicar nada por ausencia de selección; «Todas» cubre
        las pistas completas y «Cancelar» no registra historial.
        """
        parent=self.window()
        dialog=QDialog(parent)
        dialog.setObjectName("pianoNoteScopeDialog")
        dialog.setWindowTitle(action+" · Piano Roll")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumWidth(475)
        dialog.setStyleSheet("""
          QDialog#pianoNoteScopeDialog {
            background:#041938;color:#e8faff;
            border:1px solid #32b9ee;border-radius:7px;
          }
          QLabel{color:#e0faff;font-weight:600;}
          QPushButton{background:#0b528f;color:white;
            border:1px solid #58c5ff;border-radius:5px;
            padding:6px 10px;min-height:26px;}
          QPushButton:hover{background:#187bc1;}
          QPushButton:disabled{background:#132e47;color:#81a8b4;}
        """)
        body=QVBoxLayout(dialog)
        body.setContentsMargins(14,12,14,12);body.setSpacing(12)
        body.addWidget(QLabel(
            f"{action}: ¿a qué notas deseas aplicar el cambio?"))
        options=QHBoxLayout()
        cancel=QPushButton("Cancelar",dialog)
        cancel.setObjectName("pianoScopeCancel")
        chosen=QPushButton("Aplicar a las notas seleccionadas",dialog)
        chosen.setObjectName("pianoScopeSelected")
        chosen.setEnabled(selected_count>0)
        chosen.setToolTip(f"{selected_count} notas marcadas de una o más pistas.")
        all_notes=QPushButton("Aplicar a todas las notas",dialog)
        all_notes.setObjectName("pianoScopeAll")
        all_notes.setToolTip("Todas las pistas del MIDI actual.")
        choices={"scope":"cancel"}
        def finish(scope):
            choices["scope"]=scope
            dialog.accept() if scope!="cancel" else dialog.reject()
        cancel.clicked.connect(lambda:finish("cancel"))
        chosen.clicked.connect(lambda:finish("selected"))
        all_notes.clicked.connect(lambda:finish("all"))
        options.addWidget(cancel)
        options.addWidget(chosen,1)
        options.addWidget(all_notes,1)
        body.addLayout(options)
        dialog.adjustSize()
        # Qt en XWayland: centrar sobre la tarjeta real, no sobre Inicio,
        # evitando las ventanas emergentes perdidas fuera de la flotante.
        center=parent.geometry().center()
        dialog.move(center.x()-dialog.width()//2,
                    center.y()-dialog.height()//2)
        dialog.exec()
        return choices["scope"]

    def quantize(self):
        e=self._ensure_editor()
        if e is None:return
        selected=self._selected_note_keys(e)
        scope=self._choose_note_scope("Cuantizar",len(selected))
        if scope=="cancel":
            self.info.setText("Cuantización cancelada: MIDI sin modificar.")
            return
        strength=self.quant_strength.value()
        division=self.quant_div.currentData()
        ends=self.quant_ends.isChecked()
        changes={}
        if scope=="selected":
            for track,index in selected:
                old=e.tracks[track]["notes"][index]
                result=quantize([old],e.ticks_per_beat,
                                division,strength,ends)[0]
                if old!=result:changes[(track,index)]=result
        else:
            # Todas LAS PISTAS; la versión anterior solo tocaba la activa.
            for t,tr in enumerate(e.tracks):
                before=tr["notes"]
                if not before:continue
                result=quantize(before,e.ticks_per_beat,
                                division,strength,ends)
                if result!=before:changes[t]=result
        if not changes:
            self.info.setText("Cuantización: sin cambios en el alcance indicado.")
            return
        e.snapshot()
        if scope=="selected":
            for (t,index),item in changes.items():
                e.tracks[t]["notes"][index].update(item)
        else:
            for t,notes in changes.items():
                e.tracks[t]["notes"][:]=notes
        self._publish_preview()
        label=(f"{len(selected)} notas seleccionadas" if scope=="selected"
               else "todas las pistas")
        self.info.setText(
            f"Cuantización aplicada a {label}. Deshacer disponible.")

    def _selected_note_keys(self,e):
        """Las selecciones del roll mini tienen pista explícita; la del
        editor completo pertenece exclusivamente a su pista activa.
        """
        preview=self.home.piano_preview
        selected={(t,i) for t,i in preview.selected_note_keys
                  if 0<=t<len(e.tracks) and 0<=i<len(e.tracks[t]["notes"])}
        if not selected and e.selected_indices:
            selected={(e.track_index,i) for i in e.selected_indices
                      if 0<=i<len(e.current_notes)}
        return selected

    def cleanup_notes(self):
        e=self._ensure_editor()
        if e is None:return
        selected=self._selected_note_keys(e)
        only=self.clean_only_selected.isChecked()
        if only and not selected:
            self.info.setText(
                "Solo seleccionado: marca primero las notas que quieres limpiar.")
            return
        targets={}
        if only:
            for t,i in selected:targets.setdefault(t,set()).add(i)
        else:
            # Sin marcar: limpieza de TODO el archivo, incluidas todas
            # las pistas, sin depender de cuál esté activa.
            targets={t:set(range(len(tr["notes"])))
                     for t,tr in enumerate(e.tracks) if tr["notes"]}
        replacement={}
        removed_stats={}
        for track,indices in targets.items():
            items=e.tracks[track]["notes"]
            selected_notes=[items[i] for i in sorted(indices) if i<len(items)]
            if not selected_notes:continue
            kept,stats=clean(selected_notes,e.ticks_per_beat,
                   min_duration=self.min_duration.value()/100,
                   min_velocity=self.min_velocity.value(),
                   remove_out_of_scale=self.remove_scale.isChecked(),
                   root=self.tonic.currentIndex(),scale=self.scale.currentText(),
                   align_outliers=self.remove_beat.isChecked(),
                   division=self.quant_div.currentData(),
                   sensitivity=self.sensitivity.value(),
                   context_notes=items)
            from collections import Counter
            ids=Counter((n["start"],n["end"],n["pitch"],n["velocity"],n["channel"])
                        for n in kept)
            retained=[]
            for i,n in enumerate(items):
                if i not in indices:retained.append(n);continue
                signature=(n["start"],n["end"],n["pitch"],n["velocity"],n["channel"])
                if ids[signature]>0:
                    retained.append(n);ids[signature]-=1
            replacement[track]=retained
            for reason,count in stats.items():
                removed_stats[reason]=removed_stats.get(reason,0)+count
        changed=any(len(e.tracks[t]["notes"])!=len(kept)
                    for t,kept in replacement.items())
        if changed:
            e.snapshot()
            for track,kept in replacement.items():e.tracks[track]["notes"][:]=kept
            self.home.piano_preview._set_note_selection(set())
            self._publish_preview()
        total=sum(removed_stats.values())
        scope=(f"{len(selected)} notas seleccionadas" if only
               else "todas las pistas del MIDI")
        if total:
            details=", ".join(f"{label}: {removed_stats[label]}"
                     for label in ("cortas","velocidad","repetidas","ecos",
                                   "fragmentos","fuera_escala","fuera_compas")
                     if removed_stats.get(label))
            self.info.setText(
                f"Limpieza ({scope}): {total} retiradas · {details}. Deshacer.")
        else:self.info.setText(
                f"Limpieza ({scope}): ningún indicio con estos ajustes."
                " Sube Sensibilidad o modifica los umbrales.")

    def apply_ties_to_selection(self):
        """Ligaduras de selección o de todas las pistas, con un Deshacer."""
        e=self._ensure_editor()
        if e is None:return
        selected=self._selected_note_keys(e)
        scope=self._choose_note_scope("Ligar notas",len(selected))
        if scope=="cancel":
            self.info.setText("Ligaduras canceladas: MIDI sin modificar.")
            return
        from composition_ligatures import tie_selected_notes
        if scope=="selected":
            targets={}
            for track,index in selected:
                targets.setdefault(track,set()).add(index)
        else:
            targets={i:set(range(len(track["notes"])))
                     for i,track in enumerate(e.tracks) if track["notes"]}
        replacements={}
        joined=connected=0
        for track,indices in targets.items():
            if len(indices)<2:continue
            previous=e.tracks[track]["notes"]
            result,merged,slurred=tie_selected_notes(
                previous,indices,e.ticks_per_beat)
            if result!=previous:
                replacements[track]=result
                joined+=merged;connected+=slurred
        if not replacements:
            self.info.setText(
                "Ligaduras: no hay notas consecutivas compatibles "
                "en el alcance elegido; MIDI intacto.")
            return
        e.snapshot()
        for track,notes in replacements.items():
            e.tracks[track]["notes"][:]=notes
        e.selected_indices.clear()
        e.selected_index=None
        self.home.piano_preview._set_note_selection(set())
        self._publish_preview()
        label=("notas seleccionadas" if scope=="selected"
               else "todas las pistas")
        self.info.setText(
            f"Ligaduras ({label}): {joined} prolongaciones y"
            f" {connected} enlaces legato. Deshacer disponible.")

    def apply_sustain(self):
        """Prolongar notas seleccionadas; una sola operación Deshacer."""
        e=self._ensure_editor()
        if e is None:return
        selected=self._selected_note_keys(e)
        if not selected:
            self.info.setText(
                "Sostenido: selecciona una o varias notas antes de aplicarlo.")
            return
        factor=self.sustain_percent.value()/100.
        if factor<=1.:
            self.info.setText("Sostenido 100 %: duración original, sin cambios.")
            return
        modifications={}
        for track,index in selected:
            note=e.tracks[track]["notes"][index]
            length=max(1,note["end"]-note["start"])
            end=note["start"]+max(1,round(length*factor))
            if end!=note["end"]:modifications[(track,index)]=end
        if not modifications:return
        e.snapshot()
        for (track,index),end in modifications.items():
            e.tracks[track]["notes"][index]["end"]=end
        self._publish_preview()
        self.info.setText(
            f"Sostenido {self.sustain_percent.value()} % aplicado a "
            f"{len(modifications)} notas seleccionadas. Deshacer disponible.")

    def reset_edit(self):
        """Restablece el estado inicial del MIDI abierto sin sobrescribirlo.

        Se guarda un único estado Deshacer para recuperar las ediciones.
        Un borrador nuevo vuelve a estar vacío; tras Añadir a la lista,
        el punto de partida pasa a ser el MIDI publicado.
        """
        e=self._ensure_editor()
        if e is None:return
        initial=getattr(e,"_initial_tracks",None)
        if initial is None:
            self.info.setText("Reset: no se ha registrado un MIDI inicial.")
            return
        if e.tracks==initial:
            self.info.setText("Reset: el MIDI ya está en su estado inicial.")
            return
        self._stop_piano_transport()
        e.snapshot()
        e.restore(initial)
        self.home.piano_preview._set_note_selection(set())
        self.home.piano_preview.set_live_editor(e)
        self.home.piano_preview.set_scroll(0.)
        self.info.setText(
            "Reset: restaurado el MIDI al abrirlo; el original sigue intacto."
            " Puedes Deshacer el reset.")

    @staticmethod
    def _track_role(track):
        role=track.get("_composition_role")
        if role:return role
        title=track.get("name","").lower()
        if title.startswith("melodía"):return "melody"
        if title.startswith("acordes"):return "harmony"
        return None

    def _append_notes(self,notes,description,other_events=(),role=None,
                      start_tick=0,span=None):
        e=self._ensure_editor()
        if e is None or not notes:return
        dirty_before=e.dirty
        redo_before=copy.deepcopy(e.future)
        e.snapshot()
        # Cada parte instrumental nueva debe poder editarse, mezclarse y
        # cambiar de SF2 sin alterar las otras. También evita cruces de
        # note_off entre melodía y acordes del mismo canal.
        track=e.tracks[e.track_index]
        prior_role=self._track_role(track)
        # Si ya existe una pista de la función musical solicitada,
        # generar una TOMA NUEVA sobre esa pista, no apilar interpretaciones.
        candidate=next((i for i,tr in enumerate(e.tracks)
                if self._track_role(tr)==role),None) if role else None
        if candidate is not None and candidate!=e.track_index:
            e.track_index=candidate
            track=e.tracks[candidate]
            prior_role=role
        replacing=bool(role and prior_role==role and track["notes"])
        # Rehacer una sección no debe borrar los otros 16/32 compases.
        # Se recortan los fragmentos que cruzan el principio o final de
        # la sección nueva para no duplicar notas del mismo canal.
        end_tick=(start_tick+span if span is not None else None)
        if replacing:
            retained=[]
            for old in track["notes"]:
                if end_tick is None:
                    continue  # Compatibilidad con la llamada de generación total.
                if old["end"]<=start_tick or old["start"]>=end_tick:
                    retained.append(old)
                else:
                    if old["start"]<start_tick:
                        left=dict(old,end=start_tick)
                        if left["end"]>left["start"]:retained.append(left)
                    if old["end"]>end_tick:
                        right=dict(old,start=end_tick)
                        if right["end"]>right["start"]:retained.append(right)
            track["notes"][:]=retained
            track["other"]=[(tick,msg) for tick,msg in track["other"]
                    if not (getattr(msg,"channel",None) in track["channels"]
                    and msg.type=="control_change" and msg.control in (1,11,64)
                    and (end_tick is None or start_tick<=tick<end_tick))]
            # Si un pedal antiguo estaba sostenido antes de la guía,
            # limpiarlo justo al entrar en la sección regenerada.
            track["other"].append((start_tick,mido.Message(
                "control_change",channel=e.default_channel(),
                control=64,value=0,time=0)))
        create_track=bool(role and track["notes"] and prior_role!=role)
        if create_track:
            used={c for t in e.tracks for c in t.get("channels",())}
            channel=next((c for c in range(16) if c!=9 and c not in used),None)
            if channel is None:
                # No mezclar dos partes en un mismo canal cuando ya hay
                # 15 canales melódicos: aviso sin efectuar modificaciones.
                e.history.pop()
                e.future=redo_before
                e.dirty=dirty_before
                self.info.setText("No quedan canales MIDI libres para otra pista.")
                return
            name=("Melodía" if role=="melody" else "Acordes")
            name+=" · "+self.instrument_preset.currentText()
            new_track={"name":name,"notes":[],"other":[],"channels":[channel],
                       "program":0,"_composition_role":role}
            e.tracks.append(new_track)
            e.track_index=len(e.tracks)-1
            e.selected_indices.clear()
            e.selected_index=None
        else:
            channel=e.default_channel()
            if role and not track["notes"]:
                track["_composition_role"]=role
                original=track.get("name","")
                if (original=="Composición" or original.startswith("Pista")
                        or original.startswith("piano_roll_borrador")):
                    track["name"]=(
                        ("Melodía" if role=="melody" else "Acordes")
                        +" · "+self.instrument_preset.currentText())
        # Los algoritmos trabajan con ticks relativos (0..N compases),
        # la pista completa almacena ticks absolutos desde la guía.
        notes=[dict(n,start=n["start"]+start_tick,
                    end=n["end"]+start_tick,channel=channel)
               for n in notes]
        other_events=[(start_tick+tick,
                       msg.copy(channel=channel,time=0)
                       if hasattr(msg,"channel") else msg.copy(time=0))
                      for tick,msg in other_events]
        self._apply_generated_instrument(e,channel)
        e.current_notes.extend(notes)
        e.current_notes.sort(key=lambda n:(n["start"],n["pitch"],n["end"]))
        e.tracks[e.track_index]["other"].extend(other_events)
        e.tracks[e.track_index]["other"].sort(key=lambda ev:ev[0])
        e.update_track_list()
        self._publish_preview()
        meter=self._midi_meter(e)
        bar=max(1,round(e.ticks_per_beat*4*meter[0]/meter[1]))
        from_bar=start_tick//bar+1
        self.info.setText(
            f"{description}: {len(notes)} notas · desde compás {from_bar}"
            f" · pista {e.track_index+1} · Deshacer disponible.")

    def _piano_sound_transport(self):
        manager=getattr(self.home,"_floating_manager",None)
        if manager is None:return None
        window=manager.windows.get(self.home.piano_card)
        return (getattr(window,"float_transport",None) if window else None)

    def sync_soundfont_catalog(self,transport=None):
        """El árbol de arriba es un espejo literal del SF2 de abajo.

        No crear presets GM imaginarios: si un SF2 solo tiene piano,
        arriba solo hay piano. QSignalBlocker evita callbacks circulares.
        """
        transport=transport or self._piano_sound_transport()
        if transport is None or not hasattr(transport,"sf2_family"):return
        families=transport.sf2_family
        programs=transport.sf2_program
        with QSignalBlocker(self.instrument_style):
            self.instrument_style.clear()
            for i in range(families.count()):
                self.instrument_style.addItem(
                    families.itemText(i),families.itemData(i))
            self.instrument_style.setCurrentIndex(families.currentIndex())
        with QSignalBlocker(self.instrument_preset):
            self.instrument_preset.clear()
            for i in range(programs.count()):
                self.instrument_preset.addItem(
                    programs.itemText(i),programs.itemData(i))
            self.instrument_preset.setCurrentIndex(programs.currentIndex())
        has_voice=(self.instrument_preset.currentData() is not None)
        self.instrument_style.setEnabled(families.count()>0)
        self.instrument_preset.setEnabled(has_voice)
        self.gen_melody.setEnabled(has_voice)
        self._sync_chord_availability()

    def _style_from_top(self,index):
        transport=self._piano_sound_transport()
        if transport is None:return
        key=self.instrument_style.itemData(index)
        target=next((i for i in range(transport.sf2_family.count())
                     if transport.sf2_family.itemData(i)==key),-1)
        if target>=0:
            transport.sf2_family.setCurrentIndex(target)
            self.sync_soundfont_catalog(transport)

    def _preset_from_top(self,index):
        transport=self._piano_sound_transport()
        if transport is None:return
        key=self.instrument_preset.itemData(index)
        if key is None:return
        # bottom pair has the authoritative chosen bank/program.
        target=next((i for i in range(transport.sf2_program.count())
                     if transport.sf2_program.itemData(i)==key),-1)
        if target>=0:
            transport.sf2_program.setCurrentIndex(target)
            self.sync_soundfont_catalog(transport)

    def _selected_sf2_profile(self):
        from composition_adaptive import profile_for_program
        voice=self.instrument_preset.currentData()
        if voice is None:return None
        bank,program=voice
        if bank==128:return None
        return profile_for_program(program)

    def _sync_chord_availability(self):
        from composition_adaptive import profile_for_program
        selected=self.instrument_preset.currentData()
        profile=self._selected_sf2_profile()
        can_chord=bool(profile and not profile.mono)
        self.gen_chords.setEnabled(can_chord)
        self.arpeggiate.setEnabled(can_chord)
        if selected is None:
            self.gen_chords.setToolTip("Carga primero un banco SF2.")
        elif not can_chord:
            self.gen_chords.setToolTip(
                "Instrumento monofónico (o percusión): no admite"
                " acordes de notas simultáneas. Selecciona un piano,"
                " guitarra o instrumento polifónico del SF2.")
        else:
            self.gen_chords.setToolTip(
                "Generar acordes con el instrumento polifónico"
                " seleccionado, en bloque o arpegiados.")

    def _apply_generated_instrument(self,e,channel):
        """Un único instrumento para el canal activo, no TODAS las pistas.

        Se escribe dentro del snapshot existente de la generación:
        el mismo Deshacer revierte las notas, programa y CC expresivos.
        """
        selected=self.instrument_preset.currentData()
        if selected is None:return
        import mido
        bank,program=selected
        if bank==128:return
        track=e.tracks[e.track_index]
        old=track["other"]
        track["other"]=[(at,msg) for at,msg in old
                        if not (getattr(msg,"channel",None)==channel
                                and (msg.type=="program_change"
                                     or (msg.type=="control_change"
                                         and msg.control in (0,32))))]
        if bank:
            track["other"].append((0,mido.Message(
                "control_change",channel=channel,control=0,
                value=min(127,bank//128),time=0)))
            track["other"].append((0,mido.Message(
                "control_change",channel=channel,control=32,
                value=bank%128,time=0)))
        track["other"].append((0,mido.Message(
            "program_change",channel=channel,program=program,time=0)))
        track["program"]=program
        track["channels"]=sorted(set(track["channels"])|{channel})
        track["other"].sort(key=lambda n:n[0])

    def _composition_inputs(self,e,role=None):
        import secrets
        seed=(secrets.randbits(32)^self.seed.value()
              if self.random_each.isChecked() else self.seed.value())
        # No armonizar con la versión de sí misma que va a sustituirse:
        # el contexto es la OTRA parte, o las notas originales del usuario.
        from composition_registers import local_context,bar_ticks
        meter=self._midi_meter(e)
        start=self._generation_start_tick(e,meter)
        duration=self.bars.value()*bar_ticks(e.ticks_per_beat,meter)
        context=local_context(
            [n for track in e.tracks
             if self._track_role(track)!=role
             for n in track["notes"]],start,duration)
        mode=("Libre" if self.harmony_mode.currentIndex()==1 else "Auto")
        root=self.tonic.currentIndex()
        scale=self.scale.currentText()
        if context and mode=="Auto" and self.auto_tonality.isChecked():
            from composition_musical_v2 import detect_tonality
            root,scale,_confidence=detect_tonality(context,root,scale)
            if root!=self.tonic.currentIndex() or scale!=self.scale.currentText():
                self.tonic.setCurrentIndex(root)
                self.scale.setCurrentText(scale)
        selected=self.instrument_preset.currentData()
        if selected is None:
            self.info.setText("Carga un SF2 y elige un instrumento disponible.")
            return None
        bank,program=selected
        if bank==128:
            self.info.setText("Selecciona un instrumento melódico, no un kit de batería.")
            return None
        return seed,context,mode,program

    def _generation_start_tick(self,e,meter):
        """La guía de la vista pequeña es el origen; editor completo como
        respaldo. Desplazarse con scroll no mueve la guía ni crea notas.
        """
        preview=self.home.piano_preview
        tick=getattr(preview,"playhead_tick",None)
        if tick is None:
            if getattr(e,"_pending_seek_ms",None) is not None:
                tick=e.seconds_to_tick(e._pending_seek_ms/1000.)
            else:
                tick=e.seconds_to_tick(max(0,e.preview._position())/1000.)
        tick=max(0,int(tick or 0))
        # Alinear el inicio a la misma rejilla rítmica de subdivisión.
        # En el límite de compás 17 se conserva exactamente compás 17.
        beat=max(1,int(e.ticks_per_beat))
        division=self.rhythm.currentData() or 8
        unit=max(1,round(beat*4/int(division)))
        return round(tick/unit)*unit

    def _generation_window(self,e,role,program,meter):
        from composition_registers import (
            bar_ticks,local_context,bounds_for_role)
        start=self._generation_start_tick(e,meter)
        duration=self.bars.value()*bar_ticks(e.ticks_per_beat,meter)
        context_abs=[n for track in e.tracks
                     if self._track_role(track)!=role
                     for n in track["notes"]]
        context=local_context(context_abs,start,duration)
        from composition_adaptive import profile_for_program
        bounds,error=bounds_for_role(
            role,context,self.octave.value(),profile_for_program(program),
            self.auto_registers.isChecked())
        if error:
            self.info.setText(error)
            return None
        return start,duration,context,bounds

    @staticmethod
    def _midi_meter(editor):
        # Prefer the first time_signature meta event present, otherwise 4/4.
        signatures=sorted(((tick,msg) for track in editor.tracks
                for tick,msg in track.get("other",[])
                if msg.type=="time_signature"),key=lambda pair:pair[0])
        if signatures:
            # Los MIDI nuevos contienen un 4/4 predeterminado. Si el
            # usuario cambia la métrica en tick cero, el ÚLTIMO evento
            # en esa posición tiene prioridad sobre el predeterminado.
            first_tick=signatures[0][0]
            m=next(msg for tick,msg in reversed(signatures)
                   if tick==first_tick)
            return (int(m.numerator),int(m.denominator))
        return (4,4)

    def _best_musical_candidate(self,e,*,role,base_seed,context,mode,
                                program,meter,generator,pitch_bounds=None):
        """Una única modificación MIDI, aunque se comparen cuatro tomas.

        Selección auditable por puntuación estructural; no se presenta
        como modelo neuronal ni como criterio artístico infalible.
        """
        from composition_critic import choose_best
        from composition_adaptive import profile_for_program
        from composition_musical_v2 import context_plan
        import random
        root=self.tonic.currentIndex()
        scale=self.scale.currentText()
        bars=self.bars.value()
        tpb=e.ticks_per_beat
        profile=profile_for_program(program)
        low=(pitch_bounds[0] if pitch_bounds is not None else
             profile.lo if role=="melody" else max(43,profile.lo-5))
        high=(pitch_bounds[1] if pitch_bounds is not None
              else profile.hi)
        score_options=dict(
            tpb=tpb,bars=bars,meter=meter,root=root,scale=scale,
            context=context,lo=low,hi=high,
            dynamics=self.dynamics_amount.value())
        # La misma semilla produce el mismo plan: puntuar melodías
        # generadas desde cero frente a los acordes reales del propio
        # generador, y no solo frente a la escala de siete notas.
        def plan_fn(candidate_seed):
            if role!="melody":return None
            derived_seed=random.Random(candidate_seed).randrange(2**32)
            plan,_=context_plan(context,tpb,bars,root,scale,
                derived_seed,mode,self.progression.currentData(),meter,
                rhythm_style=self.rhythm_style.currentData())
            return plan
        best_result,best_review,selected=choose_best(
            generator,base_seed=base_seed,alternatives=4,
            role=role,score_kwargs=score_options,plan_fn=plan_fn,
            repair_kwargs={k:score_options[k] for k in
                           ("tpb","bars","meter","root","scale",
                            "context","lo","hi")},
            enabled=self.auto_quality.isChecked())
        return best_result,best_review,selected

    def generate_melody(self):
        e=self._ensure_editor()
        if e is None:return
        from composition_adaptive import melodic_phrase
        inputs=self._composition_inputs(e,"melody")
        if inputs is None:return
        seed,context,mode,program=inputs
        meter=self._midi_meter(e)
        window=self._generation_window(e,"melody",program,meter)
        if window is None:return
        start_tick,span,context,pitch_bounds=window
        args=dict(
            root=self.tonic.currentIndex(),scale=self.scale.currentText(),
            bars=self.bars.value(),density=self.density.value(),
            octave=self.octave.value(),pitch_bounds=pitch_bounds,
            division=self.rhythm.currentData(),
            velocity=e.velocity.value(),channel=e.default_channel(),
            existing=context,mode=mode,instrument="Automático",
            program=program,progression=self.progression.currentData(),
            generator_bpm=self.tempo_bpm.value(),
            ligatures=self.ligatures.isChecked(),
            pedal=self.melody_pedal.isChecked(),meter=meter,
            pedal_amount=self.pedal_amount.value(),
            dynamics=self.dynamics_amount.value(),
            rhythm_style=self.rhythm_style.currentData())
        (generated,pedal,source,profile),review,selected=(
            self._best_musical_candidate(
                e,role="melody",base_seed=seed,context=context,mode=mode,
                program=program,meter=meter,pitch_bounds=pitch_bounds,
                generator=lambda proposal_seed:melodic_phrase(
                    e.ticks_per_beat,seed=proposal_seed,**args)))
        style_label=(self.rhythm_style.currentData() or "libre")
        feedback=(f" · {review.summary} · toma {selected}/"
                  f"{4 if self.auto_quality.isChecked() else 1}"
                  f" · {review.changes} ajustes")
        self._append_notes(generated,
           f"Melodía {profile}{feedback} · ritmo {style_label}"
           f" · armonía {source} · semilla {seed}",
           pedal,role="melody",start_tick=start_tick,span=span)

    def generate_chords(self):
        e=self._ensure_editor()
        if e is None:return
        from composition_adaptive import harmonic_accompaniment
        inputs=self._composition_inputs(e,"harmony")
        if inputs is None:return
        if self._selected_sf2_profile().mono:
            self.info.setText("Este instrumento es monofónico: no puede generar acordes.")
            return
        seed,context,mode,program=inputs
        meter=self._midi_meter(e)
        window=self._generation_window(e,"harmony",program,meter)
        if window is None:return
        start_tick,span,context,pitch_bounds=window
        args=dict(
            root=self.tonic.currentIndex(),scale=self.scale.currentText(),
            bars=self.bars.value(),progression=self.progression.currentData(),
            generator_bpm=self.tempo_bpm.value(),
            ligatures=self.ligatures.isChecked(),
            seventh=self.seventh.isChecked(),
            inversion=self.inversion.value(),
            octave=max(2,self.octave.value()-1),
            pitch_bounds=pitch_bounds,
            velocity=e.velocity.value(),channel=e.default_channel(),
            existing=context,mode=mode,instrument="Automático",
            program=program,arpeggiate=self.arpeggiate.isChecked(),
            meter=meter,pedal=self.melody_pedal.isChecked(),
            pedal_amount=self.pedal_amount.value(),
            dynamics=self.dynamics_amount.value(),return_events=True,
            rhythm_style=self.rhythm_style.currentData())
        (generated,events,source,profile),review,selected=(
            self._best_musical_candidate(
                e,role="harmony",base_seed=seed,context=context,mode=mode,
                program=program,meter=meter,pitch_bounds=pitch_bounds,
                generator=lambda proposal_seed:harmonic_accompaniment(
                    e.ticks_per_beat,seed=proposal_seed,**args)))
        style_label=(self.rhythm_style.currentData() or "libre")
        feedback=(f" · {review.summary} · toma {selected}/"
                  f"{4 if self.auto_quality.isChecked() else 1}"
                  f" · {review.changes} ajustes")
        self._append_notes(generated,
           f"Acordes {profile}{feedback} · ritmo {style_label}"
           f" · armonía {source} · semilla {seed}",
           events,role="harmony",start_tick=start_tick,span=span)

    def evaluate_open_midi(self):
        """Auditoría musical de todas las pistas, sin modificar datos."""
        e=self._ensure_editor()
        if e is None:return
        from composition_critic import evaluate
        from composition_adaptive import profile_for_program
        evaluations=[]
        for idx,track in enumerate(e.tracks):
            notes=track.get("notes",())
            if not notes:continue
            context=[n for j,t in enumerate(e.tracks) if j!=idx
                     for n in t.get("notes",())]
            role=self._track_role(track)
            if role is None:
                # Solo es una heurística para pistas externas sin etiqueta.
                unique_starts=len({n["start"] for n in notes})
                role=("harmony" if unique_starts/max(1,len(notes))<.65
                      else "melody")
            profile=profile_for_program(track.get("program",0))
            review=evaluate(
                notes,role=role,tpb=e.ticks_per_beat,
                bars=max(self.bars.value(),1+
                       max(n["start"] for n in notes)//
                       max(1,round(e.ticks_per_beat*4*
                                   self._midi_meter(e)[0]/
                                   self._midi_meter(e)[1]))),
                meter=self._midi_meter(e),
                root=self.tonic.currentIndex(),scale=self.scale.currentText(),
                context=context,
                lo=profile.lo if role=="melody" else max(43,profile.lo-5),
                hi=profile.hi,
                dynamics=self.dynamics_amount.value(),
                events=track.get("other",()))
            evaluations.append((idx+1,review))
        if not evaluations:
            self.info.setText("Evaluación: el MIDI no contiene notas.")
            return
        average=sum(r.score for _,r in evaluations)/len(evaluations)
        issues=[]
        for idx,r in evaluations:
            if r.problems:
                issues.append(f"Pista {idx}: {', '.join(r.problems[:2])}")
        detail="; ".join(issues[:2])
        self.info.setText(
            f"Auditoría orientativa {average:.0f}/100"
            f" · {len(evaluations)} pistas; "
            +(detail or "sin alertas destacadas")
            +" · sin modificar notas.")

    def undo_action(self):
        e=self._ensure_editor()
        if e is None:return
        e.undo()
        self._publish_preview()

    def redo_action(self):
        e=self._ensure_editor()
        if e is None:return
        e.redo()
        self._publish_preview()

    def commit_to_project(self):
        e=self._ensure_editor()
        if e is None:return
        project=getattr(self.home.main,"project_dir",None)
        if project is None:
            self.info.setText("Abre o crea primero un proyecto.")
            return
        from project_layout import module_dir
        from task_staging import unique_dest
        from piano_roll import export_file
        import re
        filename=self.new_name.text().strip() or (
            "composicion_nueva" if self._draft_active else
            (Path(e.current_path).stem+"_editado" if e.current_path else "nuevo_midi"))
        name=re.sub(r'[<>:"/\\|?*\x00-\x1f]',"_",filename).strip(" .")[:80]
        if not name:
            self.info.setText("Introduce un nombre válido para el MIDI.")
            return
        if not name.lower().endswith(".mid"):name+=".mid"
        destdir=module_dir(project,"piano_roll")
        destdir.mkdir(parents=True,exist_ok=True)
        dest=unique_dest(destdir,name)
        try:
            export_file(e.midi,e.tracks,dest)
            mido.MidiFile(str(dest))
        except (OSError,ValueError,TypeError,EOFError) as error:
            dest.unlink(missing_ok=True)
            self.info.setText("No se ha podido añadir el MIDI: "+str(error))
            return
        self._draft_active=False
        e._initial_tracks=copy.deepcopy(e.tracks)
        e.dirty=False;e.history.clear();e.future.clear()
        e.current_path=dest
        e.file_label.setText(dest.name)
        self.home.selected_midi=dest
        self.home._set_piano_active_name(dest)
        self.home.refresh(force=True)
        # El MIDI recién creado pasa a la lista y al selector original.
        self.refresh_files(force=True)
        self.home.piano_preview.set_midi(dest)
        self.info.setText("MIDI añadido al proyecto: "+dest.name)

    def close(self):
        self._scratch.cleanup()
