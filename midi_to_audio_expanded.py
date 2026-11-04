"""Mesa de conversión MIDI→audio: compacta, operativa, sin scroll.
El motor es el único MidiToAudioCard del proyecto; no se duplica estado.
"""
from __future__ import annotations
import time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSignalBlocker
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import (
 QWidget,QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QListWidget,
 QListWidgetItem,QPushButton,QComboBox,QSlider,QLineEdit,QCheckBox,
 QFileDialog,QAbstractItemView,QProgressBar,QTabWidget,QMenu,QMessageBox)
from midi_to_audio_engine_options import soundfont_file,choose_soundfont
from midi_quant_render import QUANT_OPTIONS
from midi_gm_programs import GM_GROUPS
from preview_player import timecode
from midi_compact_vu import CompactStereoMeter
from soundfont_catalog import presets,system_soundfont

def title(s):
    x=QLabel(s);x.setObjectName("midiAudioSection");return x

from results_dragdrop import FilesDragList

class MidiDropList(FilesDragList):
    def __init__(self,parent,callback):
        super().__init__(parent)
        self.callback=callback;self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls() and any(u.isLocalFile() and
            Path(u.toLocalFile()).suffix.lower() in (".mid",".midi",".kar")
            for u in e.mimeData().urls()):e.acceptProposedAction()
        else:super().dragEnterEvent(e)
    def dragMoveEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
        else:super().dragMoveEvent(e)
    def dropEvent(self,e):
        if any(u.isLocalFile() and self.callback(u.toLocalFile())
               for u in e.mimeData().urls()):e.acceptProposedAction()
        else:super().dropEvent(e)

class MidiAudioExpanded(QWidget):
    CONFIG_KEYS=(
        "soundfont","gain_percent","transpose_semitones","tempo_percent",
        "reverb","chorus","reverb_level","chorus_level","max_polyphony",
        "resampler","program_override","override_channel","preset_bank",
        "midi_fx","delay_ms","comp_enabled","comp_threshold","comp_ratio",
        "comp_attack","comp_release","adsr_enabled","adsr_attack","adsr_decay",
        "adsr_sustain","adsr_release","eq_enabled","eq_bass","eq_mid",
        "eq_treble","quant_grid",
        "quant_strength","quant_swing","quant_ends","normalize","mono",
        "output_basename")
    def __init__(self,backend,parent=None):
        super().__init__(parent)
        self.setObjectName("midiToAudioExpanded")
        self.backend=backend
        backend.expanded_view=self
        self._restoring=True
        self._history=[];self._history_index=-1
        self._files_signature=()
        self._results_signature=()
        self._last_catalog=0.
        self._history_timer=QTimer(self)
        self._history_timer.setSingleShot(True)
        self._history_timer.setInterval(320)
        self._history_timer.timeout.connect(self._push_history)
        self.setStyleSheet("""
        QWidget#midiToAudioExpanded QLabel#midiAudioSection {
            color:#78eaff;font-size:12px;font-weight:bold;
        }
        QWidget#midiToAudioExpanded QFrame[block="true"] {
            border:1px solid #2e79b2;border-radius:6px;background:#06204a;
        }
        QWidget#midiToAudioExpanded QFrame[block="true"] QLabel,
        QWidget#midiToAudioExpanded QFrame[block="true"] QCheckBox {
            background:transparent;border:0;
        }
        QWidget#midiToAudioExpanded QComboBox {
            min-height:22px;max-height:26px;min-width:0;
        }
        QWidget#midiToAudioExpanded QListWidget {
            border:1px solid #2e8fd0;background:#031738;
            alternate-background-color:#09285a;
        }
        QWidget#midiToAudioExpanded QTabWidget::pane {
            border:1px solid #2e79b2;background:#061d46;border-radius:4px;
        }
        QWidget#midiToAudioExpanded QTabBar::tab {
            background:#092859;color:#a9e9f8;border:1px solid #2e79b2;
            padding:3px 6px;min-height:17px;
        }
        QWidget#midiToAudioExpanded QTabBar::tab:selected {
            background:#1768ab;color:white;
        }
        QWidget#midiToAudioExpanded QSlider::groove:horizontal {
            height:5px;background:#12396d;border-radius:2px;
        }
        QWidget#midiToAudioExpanded QSlider::sub-page:horizontal {
            background:#35e4d1;border-radius:2px;
        }
        QWidget#midiToAudioExpanded QSlider::handle:horizontal {
            background:#a5ffff;border:1px solid #31bce3;
            width:12px;margin:-5px 0;border-radius:6px;
        }
        QWidget#midiToAudioExpanded QPushButton {min-height:24px;}
        """)
        self._numeric_labels={}
        root=QVBoxLayout(self)
        root.setContentsMargins(5,2,5,4)
        root.setSpacing(5)
        top=QHBoxLayout();top.setSpacing(8)
        self._source_panel=QFrame(self);self._source_panel.setProperty("block",True)
        src=QVBoxLayout(self._source_panel);src.setContentsMargins(8,5,8,6);src.setSpacing(3)
        src.addWidget(title("01 · MIDI DE ENTRADA"))
        self.files=MidiDropList(self._source_panel,self.add_file)
        self.files.setObjectName("midiAudioExpandedFiles")
        self.files.setMinimumHeight(75);self.files.setAlternatingRowColors(True)
        self.files.itemSelectionChanged.connect(self._selected_file)
        src.addWidget(self.files,1)
        self.file_note=QLabel("Arrastrar MIDI o cargar archivo")
        self.file_note.hide()
        self.name=QLabel("Sin MIDI seleccionado")
        self.length=QLabel("Duración —")
        self.tracks=QLabel("Pistas — · Notas —")
        self.path=QLabel("Ruta —")
        for label in (self.name,self.length,self.tracks,self.path):
            label.setMaximumHeight(16);label.setToolTip("Archivo MIDI seleccionado")
            label.setTextInteractionFlags(Qt.NoTextInteraction)
        src.addWidget(self.name)
        info=QHBoxLayout();info.setSpacing(4)
        info.addWidget(self.length);info.addWidget(self.tracks)
        src.addLayout(info)
        actions=QHBoxLayout();actions.setSpacing(4)
        self.open_button=self._button("Cargar MIDI…",self.load_files)
        self.open_button.setObjectName("midiAudioBigOpen")
        actions.addWidget(self.open_button,1)
        actions.addWidget(self._button("Actualizar",lambda:self.refresh_files(True)))
        src.addLayout(actions)
        top.addWidget(self._source_panel,35)

        self.instrument_panel=QFrame(self);self.instrument_panel.setProperty("block",True)
        inst=QVBoxLayout(self.instrument_panel)
        inst.setContentsMargins(9,5,9,5);inst.setSpacing(5)
        inst.addWidget(title("02 · INSTRUMENTO"))
        self.instrument_mode=QComboBox(self.instrument_panel)
        self.instrument_mode.setObjectName("midiAudioInstrumentMode")
        self.instrument_mode.addItems(("Conservar instrumentos del MIDI",
                                       "Elegir instrumento del SoundFont"))
        inst.addWidget(self.instrument_mode)
        family=QHBoxLayout();family.setSpacing(4)
        self.instrument_group=QComboBox(self.instrument_panel)
        self.instrument_group.setObjectName("midiAudioInstrumentGroup")
        self.instrument=QComboBox(self.instrument_panel)
        self.instrument.setObjectName("midiAudioInstrument")
        self.instrument.setToolTip("Solo presets existentes en el SF2 seleccionado. MIDI original intacto")
        self._catalog_by_group={}
        self._soundfont_error=""
        family.addWidget(self.instrument_group,2);family.addWidget(self.instrument,3)
        inst.addLayout(family)
        self.instrument_channel=QComboBox(self.instrument_panel)
        self.instrument_channel.addItem("Todos los canales melódicos",None)
        for n in range(16):
            if n!=9:self.instrument_channel.addItem(f"Canal MIDI {n+1}",n)
        self.instrument_channel.addItem("Canal MIDI 10 · Drums",9)
        inst.addWidget(self.instrument_channel)
        self.bank=QComboBox(self.instrument_panel)
        self.bank.setObjectName("midiAudioSoundfont")
        self.bank.addItem("Banco GM del sistema (TiMidity)",None)
        for label,path in (
            ("FluidR3 GM","/usr/share/sounds/sf2/FluidR3_GM.sf2"),
            ("TimGM 6 MB","/usr/share/sounds/sf2/TimGM6mb.sf2"),
            ("SF GMbank","/usr/share/sounds/sf2/sf_GMbank.sf2")):
            if Path(path).is_file():self.bank.addItem(label,str(Path(path).resolve()))
        br=QHBoxLayout();br.setSpacing(4)
        br.addWidget(self.bank,1)
        self.sf2_button=self._button("Cargar SF2…",self.load_bank)
        br.addWidget(self.sf2_button)
        inst.addLayout(br)
        self.instrument_hint=QLabel("Batería MIDI en canal 10 intacta")
        self.instrument_hint.setObjectName("muted")
        inst.addWidget(self.instrument_hint)
        self.instrument_mode.currentIndexChanged.connect(self._instrument_changed)
        self.instrument_group.currentIndexChanged.connect(self._selected_family)
        self.instrument.currentIndexChanged.connect(self._selected_instrument)
        self.instrument_channel.currentIndexChanged.connect(self._instrument_changed)
        self.bank.currentIndexChanged.connect(self.set_bank)
        top.addWidget(self.instrument_panel,35)

        quant=QFrame(self);quant.setProperty("block",True)
        qb=QVBoxLayout(quant);qb.setContentsMargins(9,5,9,5);qb.setSpacing(4)
        qb.addWidget(title("03 · CUANTIZACIÓN"))
        self.quant=QComboBox(quant);self.quant.setObjectName("midiAudioQuantGrid")
        for name,grid in QUANT_OPTIONS:self.quant.addItem(name,grid)
        self.quant.currentIndexChanged.connect(self._quant_changed)
        qb.addWidget(self.quant)
        self.quant_strength=self._slider("Fuerza",0,100,backend.quant_strength,
                lambda v:setattr(backend,"quant_strength",v),qb,"%")
        self.quant_swing=self._slider("Swing",50,75,backend.quant_swing,
                lambda v:setattr(backend,"quant_swing",v),qb,"%")
        self.quant_ends=QCheckBox("Cuantizar también finales de nota")
        self.quant_ends.setMaximumWidth(240)
        self.quant_ends.setChecked(backend.quant_ends)
        self.quant_ends.toggled.connect(
            lambda checked:self._set_state("quant_ends",checked))
        qb.addWidget(self.quant_ends)
        ar=QHBoxLayout();ar.setSpacing(4)
        self.original_preview=self._button("▶ A · Sin efectos",lambda:self.preview_midi(True))
        self.changed_preview=self._button("▶ B · FX en directo",lambda:self.preview_midi(False))
        ar.addWidget(self.original_preview,1);ar.addWidget(self.changed_preview,1)
        self.preview_stop=self._button("■ Stop A/B",self.stop_midi)
        ar.addWidget(self.preview_stop)
        qb.addLayout(ar)
        self.preview_seek=QSlider(Qt.Horizontal,quant)
        self.preview_seek.setObjectName("midiAudioPreviewSeek")
        self.preview_seek.setRange(0,1000)
        self.preview_seek.sliderReleased.connect(self._seek_preview)
        self.preview_clock=QLabel("00:00 / 00:00")
        playrow=QHBoxLayout()
        playrow.addWidget(self.preview_seek,1)
        playrow.addWidget(self.preview_clock)
        qb.addLayout(playrow)
        self.preview_vu=CompactStereoMeter(quant)
        self.preview_vu.setFixedHeight(26)
        self.preview_vu.setToolTip("PCM real sintetizado · nivel medido durante la reproducción")
        qb.addWidget(self.preview_vu)
        self.exact_preview=self._button("♫ Escuchar último archivo convertido",
            self.preview_last_converted)
        self.exact_preview.setToolTip(
            "Escucha el archivo codificado real; el motor es el mismo FluidSynth "
            "que la preescucha B. Si activas normalización LUFS, puede cambiar el nivel.")
        qb.addWidget(self.exact_preview)
        top.addWidget(quant,30)
        root.addLayout(top,1)

        # Parámetros de síntesis en filas compactas, con sliders reales.
        middle=QHBoxLayout();middle.setSpacing(8)
        synthesis=QFrame(self);synthesis.setProperty("block",True)
        syn=QVBoxLayout(synthesis);syn.setContentsMargins(10,6,10,7);syn.setSpacing(5)
        syn.addWidget(title("04 · SÍNTESIS Y EXPRESIÓN"))
        self.gain=self._slider("Ganancia",20,200,backend.gain_percent,
                               lambda v:setattr(backend,"gain_percent",v),syn,"%")
        self.transpose=self._slider("Transponer",-24,24,backend.transpose_semitones,
                               lambda v:setattr(backend,"transpose_semitones",v),syn,"st")
        self.tempo=self._slider("Tempo",50,200,backend.tempo_percent,
                               lambda v:setattr(backend,"tempo_percent",v),syn,"%")
        self.voices=self._slider("Polifonía",16,256,backend.max_polyphony,
                               lambda v:setattr(backend,"max_polyphony",v),syn,"v")
        self.quality=QComboBox(synthesis)
        self.quality.setObjectName("midiAudioQuality")
        for name,key in (("Rápida · lineal","l"),("Normal · cúbica","c"),
                          ("Alta · Lagrange","L")):self.quality.addItem(name,key)
        self.quality.setCurrentIndex(self.quality.findData(backend.resampler))
        self.quality.currentIndexChanged.connect(
            lambda n:self._set_state("resampler",self.quality.itemData(n)))
        gr=QHBoxLayout();gr.addWidget(QLabel("Calidad"),0);gr.addWidget(self.quality,1)
        syn.addLayout(gr)
        middle.addWidget(synthesis,35)

        effects=QFrame(self);effects.setProperty("block",True)
        fx=QVBoxLayout(effects);fx.setContentsMargins(10,6,10,7);fx.setSpacing(5)
        fx.addWidget(title("05 · EFECTOS"))
        revpage=QWidget(effects)
        revbox=QVBoxLayout(revpage)
        revbox.setContentsMargins(3,2,3,2)
        revbox.setSpacing(3)
        self.reverb=QCheckBox("Reverb")
        self.chorus=QCheckBox("Chorus")
        self.reverb.setMaximumWidth(115)
        self.chorus.setMaximumWidth(115)
        self.reverb.setChecked(backend.reverb);self.chorus.setChecked(backend.chorus)
        self.reverb.toggled.connect(lambda n:self._set_state("reverb",n))
        self.chorus.toggled.connect(lambda n:self._set_state("chorus",n))
        revbox.addWidget(self.reverb)
        self.reverb_level=self._slider("Intensidad",0,127,backend.reverb_level,
                    lambda v:self._set_state("reverb_level",v),revbox,"")
        revbox.addWidget(self.chorus)
        self.chorus_level=self._slider("Intensidad",0,127,backend.chorus_level,
                    lambda v:self._set_state("chorus_level",v),revbox,"")
        self.fx_choice=QComboBox(effects)
        self.fx_choice.setObjectName("midiAudioMidiEffects")
        for label,key in (("Sustain · CC64","sustain"),
                          ("Pitch Bend","pitch_bend"),
                          ("Modulación · CC1","modulation"),
                          ("Expresión · CC11","expression"),
                          ("Brillo · CC74","brightness"),
                          ("Resonancia · CC71","resonance"),
                          ("Delay · sintetizador","delay")):
            self.fx_choice.addItem(label,key)
        adjustment=QHBoxLayout();adjustment.setSpacing(4)
        self.fx_enabled=QCheckBox("Activar")
        self.fx_enabled.setObjectName("midiAudioFxEnabled")
        adjustment.addWidget(self.fx_enabled)
        self.fx_amount=QSlider(Qt.Horizontal,effects)
        self.fx_amount.setObjectName("midiAudioFxAmount")
        self.fx_amount.setRange(0,127)
        adjustment.addWidget(self.fx_amount,1)
        self.fx_value=QLabel("127");self.fx_value.setMinimumWidth(35)
        adjustment.addWidget(self.fx_value)
        self.fx_choice.currentIndexChanged.connect(self._refresh_fx_control)
        self.fx_enabled.toggled.connect(self._toggle_fx)
        self.fx_amount.valueChanged.connect(self._value_fx)
        self._refresh_fx_control()
        # Tres paneles compactos: MIDI CC, ADSR y EQ, sin scroll.
        fx_tabs=QTabWidget(effects)
        fx_tabs.setObjectName("midiAudioFxTabs")
        fx_tabs.addTab(revpage,"Reverb")
        midipage=QWidget(fx_tabs)
        midibox=QVBoxLayout(midipage)
        midibox.setContentsMargins(3,2,3,2)
        midibox.setSpacing(2)
        midibox.addWidget(self.fx_choice)
        midibox.addLayout(adjustment)
        fx_tabs.addTab(midipage,"MIDI CC")
        adsrpage=QWidget(fx_tabs)
        adsrbox=QVBoxLayout(adsrpage)
        adsrbox.setContentsMargins(2,1,2,1)
        adsrbox.setSpacing(2)
        self.adsr_enable=QCheckBox("Activar envolvente ADSR")
        self.adsr_enable.setChecked(backend.adsr_enabled)
        self.adsr_enable.setToolTip("ADSR: Ataque, Decaimiento, Nivel S y Liberación; NO es el pedal de sustain")
        self.adsr_enable.toggled.connect(lambda n:self._set_state("adsr_enabled",n))
        adsrbox.addWidget(self.adsr_enable)
        self.sustain_pedal=QCheckBox("Pedal sustain · mantener notas (CC64)")
        self.sustain_pedal.setObjectName("midiAudioSustainPedal")
        self.sustain_pedal.setToolTip(
            "Sostiene las notas después de soltarlas, hasta desactivar el pedal. "
            "Es diferente del nivel S de la envolvente ADSR.")
        self.sustain_pedal.setChecked(dict(backend.midi_fx).get("sustain",0)>=64)
        self.sustain_pedal.toggled.connect(self._set_sustain_pedal)
        adsrbox.addWidget(self.sustain_pedal)
        adsrgrid=QGridLayout()
        adsrgrid.setContentsMargins(0,0,0,0)
        adsrgrid.setHorizontalSpacing(2)
        adsrgrid.setVerticalSpacing(2)
        self.adsr_controls={}
        for idx,(label,key,minimum,maximum,suffix) in enumerate((
            ("Ataque","adsr_attack",0,2000,"ms"),
            ("Decaimiento","adsr_decay",0,2000,"ms"),
            ("Nivel S (vol.)","adsr_sustain",0,100,"%"),
            ("Liberación","adsr_release",0,2000,"ms"))):
            self.adsr_controls[key]=self._mini_slider(label,minimum,maximum,
                getattr(backend,key),lambda v,k=key:self._set_state(k,v),
                adsrgrid,idx,0,suffix)
        adsrbox.addLayout(adsrgrid)
        fx_tabs.addTab(adsrpage,"ADSR")
        eqpage=QWidget(fx_tabs)
        eqbox=QVBoxLayout(eqpage)
        eqbox.setContentsMargins(3,2,3,2)
        eqbox.setSpacing(2)
        self.eq_enable=QCheckBox("Activar EQ · 3 bandas")
        self.eq_enable.setChecked(backend.eq_enabled)
        self.eq_enable.toggled.connect(lambda n:self._set_state("eq_enabled",n))
        eqbox.addWidget(self.eq_enable)
        eqgrid=QGridLayout()
        eqgrid.setContentsMargins(0,0,0,0)
        eqgrid.setHorizontalSpacing(2)
        eqgrid.setVerticalSpacing(2)
        self.eq_controls={}
        for idx,(label,key) in enumerate((("Graves","eq_bass"),("Medios","eq_mid"),("Agudos","eq_treble"))):
            self.eq_controls[key]=self._mini_slider(label,-18,18,
                getattr(backend,key),lambda v,k=key:self._set_state(k,v),
                eqgrid,idx,0,"dB")
        eqbox.addLayout(eqgrid)
        fx_tabs.addTab(eqpage,"EQ")
        compage=QWidget(fx_tabs)
        complayout=QVBoxLayout(compage)
        complayout.setContentsMargins(2,1,2,1)
        complayout.setSpacing(1)
        self.comp_enable=QCheckBox("Activar compresor")
        self.comp_enable.setChecked(backend.comp_enabled)
        self.comp_enable.toggled.connect(lambda value:self._set_state("comp_enabled",value))
        complayout.addWidget(self.comp_enable)
        compgrid=QGridLayout()
        compgrid.setContentsMargins(0,0,0,0)
        compgrid.setVerticalSpacing(1)
        self.comp_controls={}
        for index,(label,key,minimum,maximum,suffix) in enumerate((
            ("Umbral","comp_threshold",-36,-6," dB"),
            ("Ratio","comp_ratio",1,8,":1"),
            ("Ataque","comp_attack",1,200," ms"),
            ("Release","comp_release",20,1000," ms"))):
            self.comp_controls[key]=self._mini_slider(label,minimum,maximum,
                getattr(backend,key),lambda v,k=key:self._set_state(k,v),
                compgrid,index,0,suffix)
        complayout.addLayout(compgrid)
        fx_tabs.addTab(compage,"Comp.")
        fx.addWidget(fx_tabs,1)
        middle.addWidget(effects,27)

        export=QFrame(self);export.setProperty("block",True)
        ex=QVBoxLayout(export);ex.setContentsMargins(9,6,9,7);ex.setSpacing(5)
        ex.addWidget(title("06 · EXPORTACIÓN"))
        self.format=QComboBox(export)
        self.rate=QComboBox(export)
        for combo,source in ((self.format,backend.format),(self.rate,backend.rate)):
            for idx in range(source.count()):
                combo.addItem(source.itemText(idx),source.itemData(idx))
            combo.setCurrentIndex(source.currentIndex())
            combo.currentIndexChanged.connect(source.setCurrentIndex)
            source.currentIndexChanged.connect(combo.setCurrentIndex)
            combo.currentIndexChanged.connect(self._schedule_history)
        self.format.setObjectName("midiAudioExportFormat")
        ex.addLayout(self._compact_choice("Formato",self.format))
        ex.addLayout(self._compact_choice("Frecuencia",self.rate))
        self.channels=QComboBox(export)
        self.channels.addItems(("Estéreo","Mono"))
        self.channels.setCurrentIndex(1 if backend.mono else 0)
        self.channels.currentIndexChanged.connect(
            lambda i:self._set_state("mono",i==1))
        ex.addLayout(self._compact_choice("Canales",self.channels))
        self.normalize=QCheckBox("Normalizar a −16 LUFS")
        self.normalize.setMaximumWidth(205)
        self.normalize.setChecked(backend.normalize)
        self.normalize.toggled.connect(
            lambda n:self._set_state("normalize",n))
        ex.addWidget(self.normalize)
        self.output=QLineEdit(export)
        self.output.setObjectName("midiAudioFileName")
        self.output.setPlaceholderText("Nombre automático")
        self.output.setText(backend.output_basename)
        self.output.textChanged.connect(
            lambda txt:self._set_state("output_basename",txt))
        ex.addWidget(self.output)
        middle.addWidget(export,38)
        root.addLayout(middle,1)

        actions=QHBoxLayout();actions.setSpacing(5)
        self.undo=self._button("↶ Deshacer",self.undo_change)
        self.redo=self._button("↷ Rehacer",self.redo_change)
        self.listen=self._button("Ⅱ Pausa",self.pause_midi)
        self.stop_midi_btn=self._button("■ Stop",self.stop_midi)
        self.convert=self._button("♫ CONVERTIR MIDI A AUDIO",self.convert_selected)
        self.convert.setObjectName("midiAudioBigConvert")
        self.cancel=self._button("■ CANCELAR",backend.stop)
        for obj,weight in ((self.undo,0),(self.redo,0),(self.listen,0),
                           (self.stop_midi_btn,0),(self.convert,2),(self.cancel,0)):
            actions.addWidget(obj,weight)
        root.addLayout(actions)
        # Banda de progreso compacta: no ocupar el ancho entero con una barra.
        progress_strip=QHBoxLayout()
        progress_strip.setSpacing(7)
        self.progress_label=QLabel("CONVERSIÓN")
        self.progress_label.setObjectName("muted")
        self.progress_label.setFixedWidth(86)
        progress_strip.addWidget(self.progress_label)
        self.progress=QProgressBar(self)
        self.progress.setRange(0,100)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(17)
        self.progress.setMaximumWidth(300)
        progress_strip.addWidget(self.progress,1)
        self.status=QLabel("Ajustes listos. La conversión se guarda temporalmente.")
        self.status.setObjectName("muted")
        self.status.setFixedHeight(20)
        self.status.setMaximumWidth(470)
        self.status.setToolTip("Estado de la síntesis y codificación")
        progress_strip.addWidget(self.status,2)
        progress_strip.addStretch(1)
        root.addLayout(progress_strip)

        # Resultados: lista principal a la izquierda y transporte a la derecha.
        # El espacio ganado al compactar el progreso se destina a mostrar pistas.
        footer=QFrame(self);footer.setProperty("block",True)
        fr=QVBoxLayout(footer)
        fr.setContentsMargins(9,5,9,6)
        fr.setSpacing(4)
        fr.addWidget(title("07 · ARCHIVOS CONVERTIDOS · PREESCUCHA Y RESULTADOS"))
        result_area=QHBoxLayout()
        result_area.setSpacing(8)
        self.results=QListWidget(footer)
        self.results.setObjectName("midiAudioExpandedResults")
        self.results.setMinimumHeight(108)
        self.results.setAlternatingRowColors(True)
        self.results.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self._results_menu)
        self._delete_shortcut=QShortcut(QKeySequence.Delete,self.results)
        self._delete_shortcut.activated.connect(self.delete_results)
        self.results.itemDoubleClicked.connect(self.preview_audio)
        result_area.addWidget(self.results,1)
        playback=QFrame(footer)
        playback.setObjectName("midiAudioResultTransport")
        playback.setMaximumWidth(330)
        pl=QVBoxLayout(playback)
        pl.setContentsMargins(3,0,3,0)
        pl.setSpacing(4)
        bar=QHBoxLayout()
        bar.setSpacing(4)
        bar.addWidget(self._button("▶ Escuchar",self.preview_audio),1)
        bar.addWidget(self._button("■ Detener",self.stop_audio),1)
        pl.addLayout(bar)
        resultline=QHBoxLayout()
        resultline.setSpacing(3)
        self.audio_seek=QSlider(Qt.Horizontal,playback)
        self.audio_seek.setObjectName("midiAudioResultSeek")
        self.audio_seek.setRange(0,1000)
        self.audio_seek.sliderReleased.connect(lambda:self._seek_player(
            self.backend.home.player,self.audio_seek))
        self.audio_clock=QLabel("00:00 / 00:00")
        resultline.addWidget(self.audio_seek,1)
        resultline.addWidget(self.audio_clock)
        pl.addLayout(resultline)
        self.audio_vu=CompactStereoMeter(playback)
        self.audio_vu.setFixedHeight(26)
        self.audio_vu.setToolTip("VU de audio: RMS y picos del PCM realmente reproducido")
        pl.addWidget(self.audio_vu)
        self.delete_results_button=self._button("Eliminar seleccionados…",self.delete_results)
        self.delete_results_button.setObjectName("midiAudioDeleteResults")
        self.delete_results_button.setToolTip(
            "Eliminar archivos convertidos del proyecto · reversible hasta Guardar")
        pl.addWidget(self.delete_results_button)
        pl.addWidget(self._button("Ver todos en Resultados",self.show_results))
        pl.addStretch(1)
        result_area.addWidget(playback)
        fr.addLayout(result_area,1)
        root.addWidget(footer,3)

        self._meters_timer=QTimer(self)
        self._meters_timer.setInterval(100)
        self._meters_timer.timeout.connect(self._refresh_players)
        self._meters_timer.start()
        self._ticker=QTimer(self)
        self._ticker.setInterval(350)
        self._ticker.timeout.connect(self.refresh_runtime)
        self._ticker.start()
        self.refresh_soundfont()
        self._restoring=False
        self._push_history()
        self.refresh_files(force=True)
        self.refresh_runtime()

    @staticmethod
    def _compact_choice(text,control):
        line=QHBoxLayout();line.setSpacing(6)
        label=QLabel(text);label.setMinimumWidth(70)
        line.addWidget(label,0);line.addWidget(control,1)
        return line

    @staticmethod
    def _button(label,callback):
        button=QPushButton(label)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _slider(self,label,minimum,maximum,value,apply,parent,suffix):
        line=QHBoxLayout();line.setSpacing(5)
        caption=QLabel(label);caption.setMinimumWidth(88)
        line.addWidget(caption)
        control=QSlider(Qt.Horizontal)
        control.setRange(minimum,maximum)
        control.setValue(value)
        control.setCursor(Qt.PointingHandCursor)
        control.valueChanged.connect(
            lambda v:(apply(v),value_label.setText(f"{v}{suffix}"),
                      self._update_live_synth(user_change=True),self._schedule_history()))
        line.addWidget(control,1)
        value_label=QLabel(f"{value}{suffix}")
        value_label.setMinimumWidth(42)
        value_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        line.addWidget(value_label)
        self._numeric_labels[control]=(value_label,suffix)
        parent.addLayout(line)
        return control

    def _mini_slider(self,label,minimum,maximum,value,apply,grid,r,c,suffix):
        line=QHBoxLayout()
        line.setSpacing(1)
        caption=QLabel(label)
        caption.setFixedWidth(76)
        line.addWidget(caption)
        slider=QSlider(Qt.Horizontal)
        slider.setRange(minimum,maximum)
        slider.setValue(value)
        slider.setMinimumWidth(20)
        slider.setToolTip(f"{label}: {value}{suffix}")
        line.addWidget(slider,1)
        number=QLabel(f"{value}{suffix}")
        number.setMinimumWidth(50)
        number.setMaximumWidth(58)
        number.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        line.addWidget(number)
        slider.valueChanged.connect(lambda x:(apply(x),
            number.setText(f"{x}{suffix}"),self._schedule_history()))
        self._numeric_labels[slider]=(number,suffix)
        grid.addLayout(line,r,c)
        return slider

    def _set_sustain_pedal(self,engaged):
        values=dict(self.backend.midi_fx)
        if engaged:values["sustain"]=127
        else:values.pop("sustain",None)
        self.backend.midi_fx=tuple(sorted(values.items()))
        if self.fx_choice.currentData()=="sustain":self._refresh_fx_control()
        self._update_live_synth(user_change=True)
        self._schedule_history()

    def _set_state(self,key,value):
        b=self.backend
        setattr(b,key,value)
        # Mover un potenciómetro ES activar su efecto. Antes se podía
        # variar el deslizador sin activar la casilla, quedando sin sonido.
        if key=="reverb_level" and not b.reverb:
            b.reverb=True
            with QSignalBlocker(self.reverb):self.reverb.setChecked(True)
        if key=="chorus_level" and not b.chorus:
            b.chorus=True
            with QSignalBlocker(self.chorus):self.chorus.setChecked(True)
        if key.startswith("adsr_") and key!="adsr_enabled" and not b.adsr_enabled:
            b.adsr_enabled=True
            with QSignalBlocker(self.adsr_enable):self.adsr_enable.setChecked(True)
        if key.startswith("eq_") and key!="eq_enabled" and not b.eq_enabled:
            b.eq_enabled=True
            with QSignalBlocker(self.eq_enable):self.eq_enable.setChecked(True)
        if key.startswith("comp_") and key!="comp_enabled" and not b.comp_enabled:
            b.comp_enabled=True
            with QSignalBlocker(self.comp_enable):self.comp_enable.setChecked(True)
        self._update_live_synth(user_change=True)
        self._schedule_history()

    def _update_live_synth(self,user_change=False):
        if not self._restoring and self.backend.live_midi.running:
            try:
                live=self.backend.live_midi
                # Solo el gesto real de modificar un efecto cambia de A a B.
                # refresh_runtime llama a esta función en cada tick y no
                # debe alterar por sí solo la preescucha original.
                if user_change and live._original:
                    live._original=False
                    live._last_config=None
                    self.backend.status.setText("B · FX en directo (automático)")
                if not live._original:live.update_settings()
            except Exception as exc:
                self.backend.status.setText("Efecto MIDI: "+str(exc))

    def _schedule_history(self,*unused):
        if not self._restoring and not self.backend.busy:
            self._history_timer.start()

    def _snapshot(self):
        b=self.backend
        return tuple(getattr(b,key) for key in self.CONFIG_KEYS)+(
               b.rate.currentIndex(),b.format.currentIndex())

    def _push_history(self):
        current=self._snapshot()
        if self._history_index>=0 and current==self._history[self._history_index]:
            return
        self._history=self._history[:self._history_index+1]
        self._history.append(current)
        self._history_index=len(self._history)-1
        if len(self._history)>80:
            self._history.pop(0)
            self._history_index-=1
        self._update_history_buttons()

    def _update_history_buttons(self):
        self.undo.setEnabled(self._history_index>0)
        self.redo.setEnabled(self._history_index+1<len(self._history))

    def _restore(self,snapshot):
        self._restoring=True
        try:
            for key,value in zip(self.CONFIG_KEYS,snapshot):
                setattr(self.backend,key,value)
            rate,fmt=snapshot[-2:]
            b=self.backend
            b.rate.setCurrentIndex(rate)
            b.format.setCurrentIndex(fmt)
            controls=(
              (self.gain,b.gain_percent),(self.transpose,b.transpose_semitones),
              (self.tempo,b.tempo_percent),(self.voices,b.max_polyphony),
              (self.reverb_level,b.reverb_level),(self.chorus_level,b.chorus_level),
              (self.quant_strength,b.quant_strength),(self.quant_swing,b.quant_swing),
              *((control,getattr(b,key)) for key,control in self.adsr_controls.items()),
              *((control,getattr(b,key)) for key,control in self.eq_controls.items()),
              *((control,getattr(b,key)) for key,control in self.comp_controls.items()))
            for widget,value in controls:
                with QSignalBlocker(widget):widget.setValue(value)
                # La etiqueta numérica se actualiza sin disparar el cambio.
                line=widget.parentWidget().layout()
            for widget,checked in ((self.reverb,b.reverb),(self.chorus,b.chorus),
                        (self.normalize,b.normalize),(self.quant_ends,b.quant_ends)):
                with QSignalBlocker(widget):widget.setChecked(checked)
            with QSignalBlocker(self.quant):
                self.quant.setCurrentIndex(max(0,self.quant.findData(b.quant_grid)))
            with QSignalBlocker(self.channels):
                self.channels.setCurrentIndex(1 if b.mono else 0)
            with QSignalBlocker(self.quality):
                self.quality.setCurrentIndex(self.quality.findData(b.resampler))
            with QSignalBlocker(self.output):self.output.setText(b.output_basename)
            with QSignalBlocker(self.rate):self.rate.setCurrentIndex(rate)
            with QSignalBlocker(self.format):self.format.setCurrentIndex(fmt)
            self.refresh_soundfont(preferred=(b.preset_bank,b.program_override))
            with QSignalBlocker(self.instrument_mode):
                self.instrument_mode.setCurrentIndex(1 if b.program_override is not None else 0)
            with QSignalBlocker(self.instrument_channel):
                self.instrument_channel.setCurrentIndex(
                    max(0,self.instrument_channel.findData(b.override_channel)))
            self._refresh_fx_control()
            with QSignalBlocker(self.sustain_pedal):
                self.sustain_pedal.setChecked(dict(b.midi_fx).get("sustain",0)>=64)
            for widget,checked in ((self.adsr_enable,b.adsr_enabled),
                                   (self.eq_enable,b.eq_enabled),
                                   (self.comp_enable,b.comp_enabled)):
                with QSignalBlocker(widget):widget.setChecked(checked)
            self._toggle_instrument(update_backend=False)
            self._update_numeric_labels()
        finally:
            self._restoring=False
        self._update_history_buttons()

    def _update_numeric_labels(self):
        for control,(label,suffix) in self._numeric_labels.items():
            label.setText(f"{control.value()}{suffix}")

    def undo_change(self):
        self._history_timer.stop();self._push_history()
        if self._history_index<=0:return
        self._history_index-=1
        self._restore(self._history[self._history_index])

    def redo_change(self):
        self._history_timer.stop();self._push_history()
        if self._history_index+1>=len(self._history):return
        self._history_index+=1
        self._restore(self._history[self._history_index])

    def _instrument_changed(self,*unused):
        self._toggle_instrument()
        self._update_live_synth(user_change=True)
        self._schedule_history()

    def _toggle_instrument(self,update_backend=True):
        on=self.instrument_mode.currentIndex()==1
        b=self.backend
        choice=self.instrument.currentData()
        group=self.instrument_group.currentData()
        if update_backend:
            if on and choice is not None:
                b.preset_bank,b.program_override=choice
                b.override_channel=(9 if group and group[0]==128 else
                                    self.instrument_channel.currentData())
            else:
                b.program_override=None
                b.preset_bank=0
                b.override_channel=None
        is_drum=bool(group and group[0]==128)
        with QSignalBlocker(self.instrument_channel):
            if is_drum:self.instrument_channel.setCurrentIndex(self.instrument_channel.findData(9))
            elif self.instrument_channel.currentData()==9:self.instrument_channel.setCurrentIndex(0)
        for widget in (self.instrument,self.instrument_group,self.instrument_channel):
            widget.setEnabled(on and not b.busy and bool(self._catalog_by_group))
        self.instrument_channel.setEnabled(on and not b.busy and not is_drum)
        self.instrument_hint.setText(self._soundfont_error or
            ("Drums: kit del banco 128 · canal MIDI 10" if is_drum else
             "Instrumento en directo · canal 10 protegido" if b.live_midi.running else
             "Canal 10 protegido · solo presets reales del SoundFont"))

    def _selected_family(self,index):
        group=self.instrument_group.itemData(index)
        entries=self._catalog_by_group.get(group,())
        with QSignalBlocker(self.instrument):
            self.instrument.clear()
            for bank,program,name in entries:
                self.instrument.addItem(f"{program:03d} · {name}",(bank,program))
            if entries:self.instrument.setCurrentIndex(0)
        self._toggle_instrument(update_backend=not self._restoring)
        if not self._restoring:
            self._update_live_synth(user_change=True)
            self._schedule_history()

    def _selected_instrument(self,index):
        self._instrument_changed()

    def _quant_changed(self,index):
        self._set_state("quant_grid",self.quant.itemData(index))

    def set_bank(self,index):
        if self.backend.busy:return
        if soundfont_file(self.backend,self.bank.itemData(index)):
            self.refresh_soundfont()
            self._schedule_history()
        else:self.instrument_hint.setText("Banco SF2 no disponible")

    def load_bank(self):choose_soundfont(self.backend)

    def refresh_soundfont(self,preferred=None):
        bank=self.backend.soundfont
        idx=0
        if bank:
            idx=self.bank.findData(str(bank))
            if idx<0:
                self.bank.addItem("Personalizado · "+bank.name,str(bank))
                idx=self.bank.count()-1
        with QSignalBlocker(self.bank):self.bank.setCurrentIndex(idx)
        bankfile=bank or system_soundfont()
        self._catalog_by_group={}
        self._soundfont_error=""
        try:
            found=presets(bankfile) if bankfile else ()
        except (OSError,ValueError) as exc:
            found=()
            self._soundfont_error="No se pudo leer el SF2: "+str(exc)
        if not found and not self._soundfont_error:
            self._soundfont_error="No se pudo inventariar el banco de TiMidity"
        for bank_number,program,name in found:
            if bank_number==128:
                key=(128,'drums')
            else:key=(bank_number,program//8)
            self._catalog_by_group.setdefault(key,[]).append((bank_number,program,name))
        # phdr no impone orden por programa: presentar grupos y presets
        # ordenados sin inventar ni omitir entradas reales del SoundFont.
        self._catalog_by_group={key:sorted(entries,key=lambda item:(item[1],item[2].casefold()))
            for key,entries in sorted(self._catalog_by_group.items(),
             key=lambda group:(group[0][0]==128,group[0][0],
                               group[0][1] if isinstance(group[0][1],int) else 999))}
        old=preferred if preferred is not None else (
            self.backend.preset_bank,self.backend.program_override)
        previous_group=self.instrument_group.currentData()
        with QSignalBlocker(self.instrument_group):
            self.instrument_group.clear()
            for (n,family),values in self._catalog_by_group.items():
                if n==128:label=f"Drums · {len(values)} kits"
                else:
                    label=GM_GROUPS[family] if 0<=family<len(GM_GROUPS) else f"Grupo {family}"
                    if n:label+=f" · banco {n}"
                self.instrument_group.addItem(label,(n,family))
            desired=next((key for key,entries in self._catalog_by_group.items()
                          if old[1] is not None and any((n,p)==old for n,p,_ in entries)),None)
            if desired is None and previous_group in self._catalog_by_group:
                desired=previous_group
            index=next((i for i in range(self.instrument_group.count())
                        if self.instrument_group.itemData(i)==desired),-1)
            self.instrument_group.setCurrentIndex(max(0,index))
        self._selected_family(self.instrument_group.currentIndex())
        if old[1] is not None:
            with QSignalBlocker(self.instrument):
                chosen=next((i for i in range(self.instrument.count())
                             if self.instrument.itemData(i)==old),-1)
                if chosen>=0:self.instrument.setCurrentIndex(chosen)
        self._toggle_instrument(update_backend=not self._restoring)
        if not self._restoring:self._update_live_synth()

    def _refresh_fx_control(self,*unused):
        key=self.fx_choice.currentData()
        enabled=dict(self.backend.midi_fx)
        active=key in enabled if key!='delay' else bool(self.backend.delay_ms)
        if key=='delay':mn,mx,default=10,600,180
        elif key=='pitch_bend':mn,mx,default=-8192,8191,0
        else:mn,mx,default=0,127,(127 if key=='sustain' else 64)
        value=(self.backend.delay_ms if key=='delay' else enabled.get(key,default))
        with QSignalBlocker(self.fx_amount):
            self.fx_amount.setRange(mn,mx)
            self.fx_amount.setValue(value or default if key=='delay' else value)
        with QSignalBlocker(self.fx_enabled):self.fx_enabled.setChecked(active)
        self.fx_value.setText(str(self.fx_amount.value()))

    def _toggle_fx(self,on):
        key=self.fx_choice.currentData()
        if key=='delay':
            self.backend.delay_ms=self.fx_amount.value() if on else 0
        else:
            values=dict(self.backend.midi_fx)
            if on:values[key]=self.fx_amount.value()
            else:values.pop(key,None)
            self.backend.midi_fx=tuple(sorted(values.items()))
        if key=="sustain":
            with QSignalBlocker(self.sustain_pedal):
                self.sustain_pedal.setChecked(
                    dict(self.backend.midi_fx).get("sustain",0)>=64)
        self._update_live_synth(user_change=True)
        self._schedule_history()

    def _value_fx(self,value):
        self.fx_value.setText(str(value))
        if not self.fx_enabled.isChecked():
            # Modificar el controlador debe activarlo, como ADSR y EQ.
            with QSignalBlocker(self.fx_enabled):
                self.fx_enabled.setChecked(True)
        self._toggle_fx(True)

    def add_file(self,path):
        if self.backend.busy:return False
        result=self.backend.select_source(path)
        if result:self.refresh_files(force=True)
        return result

    def load_files(self):
        if self.backend.busy:return
        project=self.backend._project_path()
        selected,_=QFileDialog.getOpenFileNames(self,"Cargar archivos MIDI",
            str(project or Path.home()),"MIDI (*.mid *.midi *.kar)")
        for file in selected:self.backend.select_source(file)
        self.refresh_files(force=True)

    def refresh_files(self,force=False):
        if self.backend.busy:return
        if not force and time.monotonic()-self._last_catalog<2.5:return
        self._last_catalog=time.monotonic()
        self.backend.refresh(force=True)
        paths=tuple(str(self.backend.input.itemData(i))
            for i in range(self.backend.input.count()))
        if paths!=self._files_signature:
            with QSignalBlocker(self.files):
                self.files.clear()
                for path in paths:
                    item=QListWidgetItem(Path(path).name)
                    item.setData(Qt.UserRole,path);item.setToolTip(path)
                    self.files.addItem(item)
            self._files_signature=paths
        self.sync_selected_midi()
        self.refresh_outputs()

    def sync_selected_midi(self):
        if not hasattr(self,"files"):return
        selected=self.backend.input.currentData()
        for index in range(self.files.count()):
            if self.files.item(index).data(Qt.UserRole)==selected:
                with QSignalBlocker(self.files):self.files.setCurrentRow(index)
                self._read_midi_info(selected)
                break

    def _selected_file(self):
        item=self.files.currentItem()
        if item and self.backend.select_source(item.data(Qt.UserRole)):
            self._read_midi_info(item.data(Qt.UserRole))

    def _read_midi_info(self,filename):
        file=Path(filename)
        self.name.setText(file.name)
        try:
            import mido
            data=mido.MidiFile(file)
            self.length.setText(f"{data.length//60:.0f}:{int(data.length%60):02d}")
            count=sum(1 for track in data.tracks for m in track if
                m.type=="note_on" and m.velocity>0)
            self.tracks.setText(f"{len(data.tracks)} pistas · {count} notas")
        except (ValueError,OSError,EOFError):
            self.length.setText("Duración —");self.tracks.setText("MIDI ilegible")
        self.path.setText(str(file))
        self.name.setToolTip(str(file))

    def refresh_outputs(self):
        base=self.backend._project_path()
        paths=[]
        if base:
            for folder in (base/"temporales"/"resultados",base/"resultados"):
                if folder.is_dir():
                    paths.extend(str(p) for p in folder.iterdir() if
                        p.is_file() and p.suffix.lower() in (".wav",".flac",".mp3"))
        sig=tuple(sorted(paths))
        if sig!=self._results_signature:
            with QSignalBlocker(self.results):
                self.results.clear()
                for path in sig:
                    item=QListWidgetItem(Path(path).name)
                    item.setData(Qt.UserRole,path);item.setToolTip(path)
                    self.results.addItem(item)
            self._results_signature=sig

    def _selected_result_paths(self):
        root=self.backend._project_path()
        if root is None:return []
        folders={(root/"temporales"/"resultados").resolve(),
                 (root/"resultados").resolve()}
        paths=[]
        for item in self.results.selectedItems():
            value=item.data(Qt.UserRole)
            if not value:continue
            path=Path(value).resolve()
            if path.is_file() and not path.is_symlink() and path.parent in folders:
                paths.append(path)
        return list(dict.fromkeys(paths))

    def _results_menu(self,position):
        item=self.results.itemAt(position)
        if item and not item.isSelected():
            self.results.clearSelection()
            item.setSelected(True)
        menu=QMenu(self.results)
        chosen=menu.addAction("Eliminar archivos seleccionados…")
        chosen.setEnabled(bool(self._selected_result_paths()) and not self.backend.busy)
        if menu.exec(self.results.viewport().mapToGlobal(position))==chosen:
            self.delete_results()

    def delete_results(self):
        selected=self._selected_result_paths()
        if not selected or self.backend.busy:return False
        # No mover a cuarentena un archivo mientras otro reproductor lo utiliza.
        playing=self.backend.home.player
        if playing._origin and Path(playing._origin).resolve() in selected:
            playing.stop()
            playing.clear()
        from safe_file_delete import trash_files
        if not trash_files(self.backend.home,selected):return False
        self._results_signature=()
        self.refresh_outputs()
        self.backend.home.refresh(force=True)
        return True

    def preview_midi(self,original=False):
        self.backend.preview_modified(original=original,live=True)
        self.refresh_runtime()

    def pause_midi(self):
        if self.backend.live_midi.running:self.backend.live_midi.pause()
        else:self.backend.render_preview.play_pause()

    def stop_midi(self):
        self.backend.stop_preview()

    def preview_last_converted(self):
        path=getattr(self.backend,"_dest",None)
        if path is None or not Path(path).is_file():
            self.backend.status.setText("Convierte primero el MIDI para comparar el archivo final")
            return False
        self.backend.home.player.volume.setValue(100)
        return bool(self.backend.home.player.load(path,autoplay=True))

    def preview_audio(self,*args):
        item=self.results.currentItem()
        if item is not None:
            filename=Path(item.data(Qt.UserRole))
            if filename.is_file():
                self.backend.home.player.load(filename,autoplay=True)

    def stop_audio(self):self.backend.home.player.stop()

    def _seek_preview(self):
        if self.backend.live_midi.running:
            self.backend.live_midi.seek(self.preview_seek.value())
        else:
            self._seek_player(self.backend.render_preview,self.preview_seek)

    @staticmethod
    def _seek_player(player,slider):
        if player._origin is None:return
        player.slider.setValue(slider.value())
        player.drag_finish()

    @staticmethod
    def _sample_vu(player,meter,slider,clock):
        duration=player._duration_ms
        position=max(0,int(player._position()))
        active=bool(player._qt_active or player._play_process is not None)
        with QSignalBlocker(slider):
            slider.setRange(0,max(1,duration))
            if not slider.isSliderDown():slider.setValue(min(position,duration))
        slider.setEnabled(bool(player._origin is not None and duration>0))
        clock.setText(f"{timecode(position)} / {timecode(duration)}")
        values=player._measured_vu.levels
        index=int(position/100)
        if active and not player._paused and 0<=index<len(values):
            gain=player.volume.value()/100.0
            meter.set_levels(*(min(1.0,max(0.0,x*gain)) for x in values[index]))
        else:meter.set_levels(0,0,0,0)

    def _refresh_players(self):
        if not self.isVisible():return
        live=self.backend.live_midi
        if live.running:
            with QSignalBlocker(self.preview_seek):
                self.preview_seek.setRange(0,max(1,live.duration_ms))
                if not self.preview_seek.isSliderDown():
                    self.preview_seek.setValue(live.position_ms)
            self.preview_seek.setEnabled(True)
            self.preview_clock.setText(
                f"{timecode(live.position_ms)} / {timecode(live.duration_ms)}")
            self.preview_vu.set_levels(*(live.levels if not live.paused else (0,0,0,0)))
        else:
            self._sample_vu(self.backend.render_preview,self.preview_vu,
                            self.preview_seek,self.preview_clock)
        self._sample_vu(self.backend.home.player,self.audio_vu,
                        self.audio_seek,self.audio_clock)

    def show_results(self):
        main=self.backend.home.main
        main.studio_home.refresh(force=True)
        main.tabs.setCurrentWidget(main.results_tab)

    def convert_selected(self):
        self._history_timer.stop()
        self._push_history()
        self.backend.start()
        self.refresh_runtime()

    def refresh_runtime(self):
        if not hasattr(self,"convert"):return
        b=self.backend
        processing=b.busy
        self.convert.setEnabled(b.convert.isEnabled() and not processing)
        self.cancel.setEnabled(processing)
        for obj in (self.files,self.open_button,self.bank,self.sf2_button,
                    self.instrument_mode,self.gain,self.transpose,self.tempo,
                    self.voices,self.quality,self.reverb,self.chorus,
                    self.reverb_level,self.chorus_level,self.fx_choice,
                    self.fx_enabled,self.fx_amount,self.adsr_enable,self.eq_enable,self.comp_enable,
                    self.sustain_pedal,
                    *self.adsr_controls.values(),*self.eq_controls.values(),
                    *self.comp_controls.values(),
                    self.quant,self.quant_strength,self.quant_swing,self.quant_ends,
                    self.format,self.rate,self.channels,self.normalize,self.output):
            obj.setEnabled(not processing)
        self._toggle_instrument()
        if not processing:self._update_live_synth()
        self.delete_results_button.setEnabled(
            not processing and bool(self.results.selectedItems()))
        self.original_preview.setEnabled(not processing)
        self.changed_preview.setEnabled(not processing)
        self.exact_preview.setEnabled(not processing)
        self.progress.setValue(b.progress.value())
        self.progress.setFormat(b.progress.format())
        self.status.setText(b.status.text())
        self._update_history_buttons()
        if not processing:self.refresh_files()
