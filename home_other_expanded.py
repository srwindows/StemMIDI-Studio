"""Vistas operativas de Inicio para los otros once módulos.

La tarjeta original se mantiene viva y visible; los controles de arriba
son espejos sincronizados con los objetos reales, no motores duplicados.
Los presets solo registran parámetros (nunca audios, claves ni archivos).
"""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
import file_dialogs
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (
 QWidget,QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
 QComboBox,QLineEdit,QSlider,QCheckBox,QFileDialog,QMessageBox,QSizePolicy,QProgressBar,
 QListWidget,QListWidgetItem,QSplitter
)

KINDS={
 "monitor":"01 · MONITOR Y GRABACIÓN",
 "midi":"03 · TRANSCRIPCIÓN AUDIO A MIDI",
 "results":"04 · REVISIÓN Y ENTREGA",
 "wave":"VISTA DE AUDIO",
 "drums":"05 · DESGLOSE DE BATERÍA",
 "tracks":"PISTAS SEPARADAS",
 "mixer":"MEZCLADOR",
 "piano":"PIANO ROLL · MIDI",
 "vocal":"06 · AFINACIÓN VOCAL",
 "drum_stems":"BATERÍA · PISTAS SEPARADAS",
 "info":"07 · CONVERSIÓN MIDI A AUDIO",
}
STEM_NAMES=("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros")
DRUM_NAMES=("Bombo","Caja","Toms","Charles","Ride","Crash")

def preset_path():
    # Ajustes propios del proyecto/programa. Los audios se mantienen aparte.
    from studio_paths import workspace_root
    location=workspace_root(__file__)
    return location/"presets_modulos_inicio.json"

def factory_monitor_presets():
    """Curvas iniciales orientativas, NO presets de hardware inventados.

    Los niveles se aplican a PCM float32 de captura. Cada fuente tiene
    margen diferente: ajustar mirando CLIP antes de grabar.
    """
    from home_record_review import gain_db_to_percent
    descriptions=(
        ("Neutro · sin EQ",0,0,0,0,False),
        ("Voz hablada",-3,-3,2,1,True),
        ("Voz cantada",-6,-2,1,2,True),
        ("Piano acústico",-6,1,-1,2,True),
        ("Guitarra acústica",-6,-2,2,2,True),
        ("Bajo eléctrico",-9,3,-2,-1,True),
        ("Percusión",-9,2,-1,2,True),
        ("Directo · margen alto",-12,-1,0,0,True),
        ("Fuente débil · moderado",3,-1,1,1,True),
    )
    result={}
    for name,gain,bass,mid,treble,enabled in descriptions:
        values={
            "ganancia":{"value":gain},
            "preescucha_volume":{"value":gain_db_to_percent(gain)},
            "preescucha_bass":{"value":bass},
            "preescucha_mid":{"value":mid},
            "preescucha_treble":{"value":treble},
            "preescucha_eq_activa":{"checked":enabled},
        }
        result[name]=values
    return result


def read_presets():
    try:
        obj=json.loads(preset_path().read_text(encoding="utf-8"))
        return obj if isinstance(obj,dict) else {}
    except (ValueError,OSError,TypeError):
        return {}

def write_presets(obj):
    dest=preset_path()
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(".tmp")
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(dest)

def title(text):
    label=QLabel(text)
    label.setObjectName("floatingTitle")
    return label

def btn(label,callback,parent):
    w=QPushButton(label,parent)
    w.setCursor(Qt.PointingHandCursor)
    w.clicked.connect(callback)
    w.setMinimumHeight(28)
    return w

class ExpandedModule:
    def __init__(self,home,kind,card):
        self.home=home
        self.kind=kind
        self.card=card
        self.actual={}
        self.proxies=[]
        self._updating=False
        self.extra=QFrame(card)
        self.extra.setObjectName("floatPanel")
        self.layout=QVBoxLayout(self.extra)
        self.layout.setContentsMargins(12,9,12,10)
        self.layout.setSpacing(7)
        self.layout.addWidget(title(KINDS[kind]+" · CONTROLES AMPLIADOS"))
        self.status=QLabel()
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.details=QLabel()
        self.details.setObjectName("muted")
        self.details.setWordWrap(True)
        self._build()
        self.layout.addWidget(self.status)
        self.layout.addWidget(self.details)
        if self.kind=="drum_stems":
            # Asegurar la legibilidad de las seis casillas originales cuando
            # se incorpora la regla temporal encima de las ondas.
            self.layout.setSpacing(4)
            self.extra.setMinimumHeight(146)
        if self.kind=="monitor":
            # Estado y ganancia ya están en la tarjeta original. Evitar
            # solapamientos con el panel nuevo de tonos en flotante.
            self.status.hide()
            self.details.hide()
        self.card.inner.insertWidget(0,self.extra)
        self.extra.hide()
        if self.kind=="drum_stems":
            from drum_timeline_guide import DrumTimelineGuide
            self.drum_timeline=DrumTimelineGuide(self.home,self.card,self.card)
            self.card.inner.insertWidget(1,self.drum_timeline.panel)
            self.drum_timeline.panel.hide()
        self.refresh_timer=QTimer(self.extra)
        self.refresh_timer.setInterval(700)
        self.refresh_timer.timeout.connect(self.refresh)

    def line(self):
        area=QHBoxLayout()
        area.setSpacing(8)
        area.setContentsMargins(0,0,0,0)
        self.layout.addLayout(area)
        return area

    def action(self,text,callback):
        return btn(text,callback,self.extra)

    def add_actions(self,*items):
        row=self.line()
        for text,callback in items:
            row.addWidget(self.action(text,callback))
        row.addStretch(1)

    def add_combo(self,label,source):
        row=self.line()
        caption=QLabel(label,self.extra)
        caption.setFixedWidth(165)
        row.addWidget(caption)
        mirror=QComboBox(self.extra)
        mirror.setCursor(Qt.PointingHandCursor)
        mirror.setMinimumWidth(220)
        mirror.setMaximumWidth(16777215)
        mirror.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        row.addWidget(mirror,1)
        self.proxies.append((source,mirror,"combo"))
        def select(index):
            if not self._updating and index>=0:
                source.setCurrentIndex(index)
        mirror.currentIndexChanged.connect(select)
        return mirror

    def add_slider(self,label,source):
        row=self.line()
        row.addWidget(QLabel(label))
        slider=QSlider(Qt.Horizontal,self.extra)
        slider.setCursor(Qt.PointingHandCursor)
        slider.setRange(source.minimum(),source.maximum())
        row.addWidget(slider,1)
        number=QLabel()
        number.setMinimumWidth(42)
        row.addWidget(number)
        self.proxies.append((source,slider,"slider",number))
        slider.valueChanged.connect(lambda value:source.setValue(value) if not self._updating else None)
        return slider

    def add_check(self,label,source):
        box=QCheckBox(label,self.extra)
        box.setCursor(Qt.PointingHandCursor)
        self.layout.addWidget(box)
        self.proxies.append((source,box,"check"))
        box.toggled.connect(lambda enabled:source.setChecked(enabled) if not self._updating else None)
        return box

    def register(self,name,widget):
        self.actual[name]=widget

    def preset_toolbar(self):
        row=self.line()
        row.addWidget(QLabel("Preset de captura" if self.kind=="monitor" else "Preset de Inicio"))
        self.choice=QComboBox(self.extra)
        self.choice.setMinimumWidth(175)
        row.addWidget(self.choice,1)
        self.name=QLineEdit(self.extra)
        self.name.setPlaceholderText("Nombre")
        row.addWidget(self.name,1)
        row.addWidget(self.action("Guardar",self.save_preset))
        row.addWidget(self.action("Borrar",self.delete_preset))
        self.choice.currentIndexChanged.connect(self.load_preset)
        self.refresh_preset_names()

    def refresh_preset_names(self):
        if not hasattr(self,"choice"):return
        current=self.choice.currentText()
        block=self.choice.blockSignals(True)
        self.choice.clear()
        self.choice.addItem("— Elegir preset —")
        if self.kind=="monitor":
            for name in factory_monitor_presets():
                self.choice.addItem(name)
        for value in sorted(read_presets().get(self.kind,{})):
            if self.choice.findText(value)<0:
                self.choice.addItem(value)
        if self.choice.findText(current)>0:
            self.choice.setCurrentText(current)
        self.choice.blockSignals(block)

    def snapshot(self):
        values={}
        for name,widget in self.actual.items():
            if isinstance(widget,QComboBox):
                values[name]={"text":widget.currentText(),"index":widget.currentIndex()}
            elif isinstance(widget,QCheckBox):
                values[name]={"checked":widget.isChecked()}
            elif hasattr(widget,"value"):
                values[name]={"value":widget.value()}
        return values

    def apply(self,values):
        for name,data in values.items():
            widget=self.actual.get(name)
            if widget is None or not isinstance(data,dict):continue
            if isinstance(widget,QComboBox):
                idx=widget.findText(str(data.get("text","")))
                if idx<0:idx=data.get("index",-1)
                if isinstance(idx,int) and 0<=idx<widget.count():
                    widget.setCurrentIndex(idx)
            elif isinstance(widget,QCheckBox) and "checked" in data:
                widget.setChecked(bool(data["checked"]))
            elif hasattr(widget,"setValue") and "value" in data:
                value=data["value"]
                if isinstance(value,(int,float)):
                    if hasattr(widget,"minimum") and hasattr(widget,"maximum"):
                        value=max(widget.minimum(),min(widget.maximum(),value))
                    widget.setValue(value)

    def save_preset(self):
        name=self.name.text().strip()
        if not name:
            self.status.setText("Escribe un nombre para guardar el preset.")
            return
        if not self.actual:
            self.status.setText("Este módulo no tiene parámetros ajustables.")
            return
        if self.kind=="monitor" and name in factory_monitor_presets():
            self.review.state.setText(
                "No se sobreescriben presets de fábrica. Usa otro nombre.")
            return
        data=read_presets()
        data.setdefault(self.kind,{})[name]=self.snapshot()
        write_presets(data)
        self.refresh_preset_names()
        self.choice.setCurrentText(name)
        self.status.setText("Preset guardado: "+name)

    def load_preset(self,index):
        if index<=0:return
        name=self.choice.itemText(index)
        data=read_presets().get(self.kind,{}).get(name)
        if data is None and self.kind=="monitor":
            data=factory_monitor_presets().get(name)
        if isinstance(data,dict):
            self.apply(data)
            if self.kind=="monitor":self.review.apply_eq()
            if self.kind=="monitor" and name in factory_monitor_presets():
                self.name.clear()
                self.name.setPlaceholderText("Nombre del nuevo preset…")
                self.review.state.setText(
                    "Preset de captura: "+name+" · comprueba CLIP antes de grabar")
            else:
                self.name.setText(self.choice.itemText(index))
                if self.kind=="monitor":
                    self.review.state.setText("Preset personal: "+name)
            self.status.setText("Preset aplicado: "+self.choice.itemText(index))

    def delete_preset(self):
        name=self.choice.currentText()
        if self.kind=="monitor" and name in factory_monitor_presets():
            self.review.state.setText("Los presets de fábrica no se pueden borrar.")
            return
        data=read_presets()
        if name not in data.get(self.kind,{}):return
        del data[self.kind][name]
        write_presets(data)
        self.name.clear()
        self.refresh_preset_names()
        self.status.setText("Preset eliminado: "+name)

    def _build(self):
        h=self.home
        wb=h.workbench
        if self.kind=="monitor":
            for key,w in (("entrada",h.input),("formato",h.format),("calidad",h.quality),
                          ("ganancia",h.capture_gain),("balance",h.capture_balance)):
                self.register(key,w)
            self.preset_toolbar()
            # El transporte, los ajustes de entrada y el VU reales siguen
            # visibles inmediatamente debajo. No duplicar sus botones.
            # Ganancia ya disponible en el módulo real, no duplicarla.
            from home_record_review import RecordReview
            self.review=RecordReview(h,self.extra)
            h.record_review=self.review
            self.review.backend.exclusive_with(h.main.record_preview)
            h.main.record_preview.exclusive_with(self.review.backend)
            self.layout.addWidget(self.review)
            for key,slider in self.review.sliders.items():
                self.register("preescucha_"+key,slider)
            self.register("preescucha_eq_activa",self.review.eq_enabled)
            self.register("preescucha_canales",self.review.channel_mode)
        elif self.kind=="midi":
            for name,w in (("motor",h.engine),("perfil",h.midi_preset),
                          ("refinamiento",h.refine),("cuantización",h.quant),
                          ("usar_cuantización",h.quant_check),("acordes",h.chords_check)):
                self.register(name,w)
            for name,w in h.midi_sliders.items():
                self.register(name,w)
            self.layout.setContentsMargins(8,5,8,5)
            self.layout.setSpacing(3)
            # Vista amplia: primero las pistas, después los controles reales
            # en dos columnas, y los presets junto a los ajustes. Ningún
            # control duplicado, ni área reservada vacía en el lado derecho.
            self.extra.setMinimumHeight(575)
            from home_midi_browser import MidiHomePanel
            self.midi_browser=MidiHomePanel(h,self.extra)
            self.layout.addWidget(self.midi_browser,1)
            self.midi_settings=QFrame(self.extra)
            self.midi_settings.setObjectName("midiSettingsFrame")
            self.midi_settings.setStyleSheet("""
                QFrame#midiSettingsFrame {
                    background:#041b40;border:1px solid #2189d2;border-radius:7px;
                }
                QFrame#midiSettingsFrame QLabel {
                    border:0;background:transparent;
                }
            """)
            self.midi_settings_box=QVBoxLayout(self.midi_settings)
            self.midi_settings_box.setContentsMargins(10,5,10,7)
            self.midi_settings_box.setSpacing(3)
            self.midi_settings_box.addWidget(title("PARÁMETROS DE TRANSCRIPCIÓN"))
            self.midi_settings_grid=QGridLayout()
            self.midi_settings_grid.setContentsMargins(1,0,1,0)
            self.midi_settings_grid.setHorizontalSpacing(18)
            self.midi_settings_grid.setVerticalSpacing(3)
            self.midi_settings_grid.setColumnStretch(0,1)
            self.midi_settings_grid.setColumnStretch(1,1)
            self.midi_settings_box.addLayout(self.midi_settings_grid)
            self.layout.addWidget(self.midi_settings)
            self.preset_toolbar()
            self.status.hide()
            self.details.hide()
            self._midi_lifted=[]
        elif self.kind=="results":
            row=self.line()
            row.addWidget(QLabel("Buscar"))
            self.search=QLineEdit(self.extra)
            self.search.setPlaceholderText("Filtrar archivos de esta tarea")
            row.addWidget(self.search,1)
            self.result_type=QComboBox(self.extra)
            self.result_type.addItems(("Todos","Audio","MIDI"))
            row.addWidget(self.result_type)
            self.search.textChanged.connect(self.filter_results)
            self.result_type.currentIndexChanged.connect(self.filter_results)
            self.add_actions(("Guardar selección…",h.export_selected),
                             ("Guardar todo…",h.export_all),
                             ("Abrir carpeta",h.open_results_folder))
        elif self.kind=="wave":
            self.add_slider("Zoom horizontal",h.wave_zoom)
            from wave_audio_details import WaveAudioDetails
            self.wave_info=WaveAudioDetails(h,self.extra)
            self.layout.addWidget(self.wave_info)
            # No duplicar Play/Stop: el transporte permanece abajo,
            # tanto en la tarjeta acoplada como en la flotante.
            self.status.hide()
            self.details.hide()
        elif self.kind=="drums":
            self.add_combo("Batería del proyecto",h.drum_source)
            self.add_actions(("Importar batería…",self.import_drum),
                             ("Instalar IA",self.install_drum),
                             ("Desglosar",self.run_drum_here),
                             ("■ Cancelar operación",self.cancel_drum_here))
            from drum_module import PARTS
            self.drum_pieces={}
            mod=h._drum_module
            if mod is not None:
                mod.progressChanged.connect(self.refresh_drum_pieces)
            # El control adicional requiere el alto que antes ocupaban dos
            # listas de indicadores informativos repetidas. Únicamente al
            # separar esta tarjeta de Inicio se oculta la copia inferior.
            self.extra.setMinimumHeight(375)
            self.layout.setSpacing(4)
            selection=QLabel("PISTAS DE BATERÍA · SELECCIÓN, PROGRESO Y MEZCLA",self.extra)
            selection.setObjectName("floatingTitle")
            self.layout.addWidget(selection)
            notice=QLabel(
                "MDX23C calcula las seis piezas; marca las que quieras guardar.",self.extra)
            notice.setWordWrap(True)
            notice.setObjectName("muted")
            self.layout.addWidget(notice)
            columns=QHBoxLayout()
            columns.addWidget(QLabel("Guardar / pista"),2)
            columns.addWidget(QLabel("Avance IA común (real)"),2)
            columns.addWidget(QLabel("Escuchar"),1)
            columns.addWidget(QLabel("Nivel"),2)
            columns.addWidget(QLabel("Mute · Solo"),1)
            self.layout.addLayout(columns)
            for part in PARTS:
                line=QHBoxLayout()
                line.setContentsMargins(0,0,0,0)
                line.setSpacing(5)
                check=QCheckBox(part,self.extra)
                check.setChecked(True)
                check.setMinimumWidth(93)
                line.addWidget(check,2)
                progress=QProgressBar(self.extra)
                progress.setRange(0,100)
                progress.setValue(0)
                progress.setTextVisible(False)
                progress.setMinimumWidth(85)
                line.addWidget(progress,2)
                state=QLabel("Pendiente",self.extra)
                state.setMinimumWidth(70)
                line.addWidget(state,0)
                listen=self.action("▶",lambda checked=False,p=part:self.listen_drum_part(p))
                listen.setEnabled(False)
                listen.setFixedWidth(35)
                listen.setToolTip("Escuchar el archivo real de "+part)
                line.addWidget(listen)
                gain=QSlider(Qt.Horizontal,self.extra)
                gain.setRange(-36,12)
                gain.setValue(0)
                gain.setMinimumWidth(72)
                gain.valueChanged.connect(lambda value,p=part:self.set_drum_mix(p,"gain",value))
                line.addWidget(gain,2)
                gain_txt=QLabel("0 dB",self.extra)
                gain_txt.setFixedWidth(47)
                line.addWidget(gain_txt)
                mute=self.action("M",lambda checked=False,p=part:self.toggle_drum_mix(p,"mute"))
                solo=self.action("S",lambda checked=False,p=part:self.toggle_drum_mix(p,"solo"))
                for control in (mute,solo):
                    control.setCheckable(True)
                    control.setFixedWidth(31)
                    line.addWidget(control)
                self.layout.addLayout(line)
                self.drum_pieces[part]=dict(check=check,progress=progress,
                    state=state,listen=listen,gain=gain,gain_txt=gain_txt,
                    mute=mute,solo=solo)
            self.add_actions(("Guardar pistas marcadas…",self.save_drum_pieces),
                             ("Mezclador / editor completo",self.open_drum_studio))
            self.drum_mix_status=QLabel(
                "El transporte inferior incluye Play, Pausa, Stop, posición "
                "y vúmetros de las seis pistas reales.",self.extra)
            self.drum_mix_status.setWordWrap(True)
            self.layout.addWidget(self.drum_mix_status)
        elif self.kind=="tracks":
            # Esta pantalla es una escucha de los stems, no un mezclador
            # ni un editor de presets. Los faders solo están en Mezclador.
            notice=QLabel(
                "M general: silencia todo. S general: activa todo. "
                "M y S de cada pista permiten cualquier combinación; "
                "el Play inferior reproduce la mezcla de las S marcadas.",self.extra)
            notice.setObjectName("muted")
            notice.setWordWrap(True)
            self.layout.addWidget(notice)
            self.status.hide()
            self.details.hide()
            self.extra.setMinimumHeight(0)
            self.layout.setSpacing(3)
        elif self.kind=="mixer":
            # Mezclador verdadero por ARCHIVO, no por una lista de nombres.
            # Sin presets, botones duplicados ni preescucha individual.
            from project_mixer_expanded import ProjectMixerView
            self.project_mixer=ProjectMixerView(h,self.extra)
            self.layout.addWidget(self.project_mixer,1)
            self.layout.itemAt(0).widget().hide()  # título redundante
            self.status.hide()
            self.details.hide()
            self.extra.setMinimumHeight(0)
            self.layout.setContentsMargins(8,4,8,5)
            self.layout.setSpacing(3)
        elif self.kind=="piano":
            # El piano roll original permanece en la franja inferior.
            # Arriba: catálogo compacto y herramientas reales sobre el
            # editor MIDI existente, sin presets/combos/sliders duplicados.
            from piano_roll_expanded import PianoRollExpanded
            self.piano_tools=PianoRollExpanded(h,self.extra)
            self.layout.addWidget(self.piano_tools,1)
            self.layout.itemAt(0).widget().hide()
            self.status.hide()
            self.details.hide()
            self.layout.setSpacing(3)
            self.layout.setContentsMargins(7,4,7,4)
        elif self.kind=="vocal":
            # CardManager se construye antes que VocalTuneModule: crear
            # el panel únicamente cuando el usuario separa la tarjeta
            # y el motor real ya ha sido registrado con bind_vocal_module.
            self.vocal_studio=None
            self._vocal_hidden=[]
            self._vocal_spacers=[]
            self.status.hide()
            self.details.hide()
            self.layout.setContentsMargins(6,4,6,4)
            self.layout.setSpacing(2)
        elif self.kind=="drum_stems":
            self.selected_parts={}
            grid=QGridLayout();grid.setSpacing(6)
            for i,name in enumerate(DRUM_NAMES):
                item=QCheckBox(name,self.extra)
                item.setChecked(True)
                item.setCursor(Qt.PointingHandCursor)
                grid.addWidget(item,i//3,i%3)
                self.selected_parts[name]=item
            self.layout.addLayout(grid)
            self.add_actions(("Guardar piezas marcadas…",self.export_drum_parts),
                             ("Detener",h.stop_audio))
        elif self.kind=="info":
            # La antigua vista «Información» estaba incrustada encima del
            # nuevo conversor; eliminarla por completo. Los controles de
            # la vista ampliada escriben en el MISMO MidiToAudioCard real.
            from midi_to_audio_expanded import MidiAudioExpanded
            self.info_expanded=MidiAudioExpanded(h.midi_to_audio,self.extra)
            self.layout.addWidget(self.info_expanded,1)
            self.extra.setMinimumHeight(485)
            self.status.hide()
            self.details.hide()
        else:raise ValueError("Módulo no reconocido: "+str(self.kind))

    def import_midi_audio(self):
        path,_=file_dialogs.get_open_file_name(self.extra,"Audio para transcribir","","Audio (*.wav *.flac *.mp3 *.m4a *.ogg *.aiff)")
        if path:
            converter=self.home.workbench.converter
            converter.on_import_file(path)
            self.status.setText("Audio cargado: "+Path(path).name)

    def run_midi_here(self):
        converter=self.home.workbench.converter
        if not converter.use_folder.isChecked() and not Path(converter.audio_path.text()).is_file():
            QMessageBox.information(self.extra,"Audio necesario",
                "Carga el audio antes de convertir desde esta misma ventana.")
            return
        converter.start_conversion()

    def import_drum(self):
        mod=self.home._drum_module
        if mod is None:return
        mod.browse_audio()
        self.home._sync_drum_module(force=True)

    def install_drum(self):
        mod=self.home._drum_module
        if mod is not None:mod.install_model()

    def run_drum_here(self):
        mod=self.home._drum_module
        if mod is None:return
        self.home._choose_drum_source(self.home.drum_source.currentIndex())
        mod.start()
        self.home._sync_drum_module(force=True)

    def cancel_drum_here(self):
        mod=self.home._drum_module
        if mod is not None and mod.process is not None:
            mod.cancel()
            self.status.setText("Cancelación de batería solicitada; esperando al motor.")

    def _drum_source(self,part):
        mod=self.home._drum_module
        if mod is None:return None
        path=mod.studio.sources.get(part)
        return Path(path) if path is not None and Path(path).is_file() else None

    def listen_drum_part(self,part):
        file=self._drum_source(part)
        if file is None:
            self.status.setText("Aún no existe una pista de "+part)
            return
        manager=getattr(self.home,"_floating_manager",None)
        window=manager.windows.get(self.card) if manager is not None else None
        transport=getattr(window,"float_transport",None)
        if transport is not None and transport.track_select is not None:
            transport.track_select.setCurrentText(part)
            transport.play_selected()
        else:
            self.home.player.load(file,autoplay=True)
        self.status.setText("Escuchando "+part+" · "+file.name)

    def set_drum_mix(self,part,field,value):
        mod=self.home._drum_module
        if mod is None or self._drum_source(part) is None:return
        mod.studio.set_state(part,field,value)
        self.refresh_drum_pieces()

    def toggle_drum_mix(self,part,field):
        mod=self.home._drum_module
        if mod is None or self._drum_source(part) is None:return
        value=not mod.studio.channels[part][field]
        mod.studio.set_state(part,field,value)
        self.refresh_drum_pieces()

    def save_drum_pieces(self):
        mod=self.home._drum_module
        if mod is None:return
        paths=[path for part,row in self.drum_pieces.items()
               if row["check"].isChecked() and (path:=self._drum_source(part))]
        if not paths:
            QMessageBox.information(self.extra,"Sin pistas marcadas",
                "Marca una o más pistas ya terminadas para guardarlas.")
            return
        saved=mod._save(paths)
        if saved:self.status.setText(f"Guardadas {len(saved)} pistas de batería.")

    def open_drum_studio(self):
        mod=self.home._drum_module
        if mod is None:return
        self.home.main.tabs.setCurrentWidget(mod)
        mod.studio.scroll_to_section(1)

    def refresh_drum_pieces(self):
        mod=self.home._drum_module
        if mod is None:return
        busy=mod.process is not None and mod._operation in ("normalize","separate")
        for part,row in self.drum_pieces.items():
            path=self._drum_source(part)
            ready=path is not None
            progress=row["progress"]
            if ready and not busy:
                progress.setRange(0,100)
                progress.setValue(100)
                row["state"].setText("Lista")
            elif busy:
                # MDX23C calcula las seis piezas CONJUNTAMENTE.
                # Nunca usar Qt range(0,0): mueve bloques sin avance real.
                progress.setRange(0,100)
                known=bool(getattr(mod,"engine_progress_known",False)
                           and mod._operation=="separate")
                percent=min(99,getattr(mod,"engine_percent",0)) if known else 0
                progress.setValue(percent)
                row["state"].setText(f"IA {percent}%" if known else
                    "Preparando" if mod._operation=="normalize" else "IA activa")
                progress.setToolTip(
                    "Progreso compartido comunicado por MDX23C. "
                    "No es un porcentaje independiente de esta pieza. "
                    "100% solo cuando su archivo esté verificado."
                    if known else
                    "El motor aún no ha comunicado un porcentaje medible.")
            else:
                progress.setRange(0,100)
                progress.setValue(0)
                row["state"].setText("Pendiente")
            row["listen"].setEnabled(ready)
            row["gain"].setEnabled(ready)
            row["mute"].setEnabled(ready)
            row["solo"].setEnabled(ready)
            state=mod.studio.channels[part]
            old=row["gain"].blockSignals(True)
            row["gain"].setValue(state["gain"])
            row["gain"].blockSignals(old)
            row["gain_txt"].setText(f"{state['gain']:+d} dB" if state["gain"] else "0 dB")
            for field in ("mute","solo"):
                button=row[field]
                old=button.blockSignals(True)
                button.setChecked(bool(state[field]))
                button.blockSignals(old)
                button.setStyleSheet(
                    "background:#a04c43;color:white;" if field=="mute" and state[field]
                    else "background:#0b60ce;color:white;" if field=="solo" and state[field]
                    else "")
        if busy:
            measured=(mod.engine_progress_known and mod._operation=="separate")
            self.drum_mix_status.setText(
                f"MDX23C: cálculo común IA {mod.engine_percent}% medido; "
                "pendiente verificar las seis salidas."
                if measured else
                "MDX23C activo, sin porcentaje publicado aún. "
                "Las barras permanecen en 0 hasta recibir datos medibles.")
        else:
            self.drum_mix_status.setText(
                "Marca las pistas que quieras guardar. Vúmetros reales y "
                "transporte de las seis pistas en el panel inferior.")

    def run_vocal_here(self):
        mod=self.home._vocal_module
        if mod is None:return
        self.home._select_vocal_source(self.home.vocal_source.currentIndex())
        mod.start()
        self.home._sync_vocal_module(force=True)

    def import_midi(self):
        filename,_=file_dialogs.get_open_file_name(self.extra,"Cargar MIDI","","MIDI (*.mid *.midi)")
        if not filename:return
        candidate=Path(filename)
        if not candidate.is_file():return
        h=self.home
        target=h.midi_choice.findData(str(candidate))
        if target<0:
            h.midi_choice.addItem(candidate.name,str(candidate))
            target=h.midi_choice.count()-1
        h.midi_choice.setCurrentIndex(target)
        self.status.setText("MIDI seleccionado: "+candidate.name)

    def play_midi(self):
        if self.home.selected_midi is not None and self.home.selected_midi.is_file():
            self.home.piano_preview.set_midi(self.home.selected_midi)
            self.home._update_midi_stats(self.home.selected_midi)
            self.status.setText("Notas visibles: "+self.home.selected_midi.name)
        else:
            self.status.setText("Selecciona un MIDI para visualizar las notas.")

    def play_wave(self):
        source=self.home._source_for_wave(self.home._gather_files())
        if source is not None and source.is_file():
            self.home.player.load(source,autoplay=True)
        else:self.status.setText("No hay audio que reproducir.")

    def play_first_stem(self):
        for name in STEM_NAMES:
            row=self.home.track_rows[name]
            if row["path"] is not None and row["path"].is_file():
                self.home.play_stem(name)
                return
        self.status.setText("No hay pistas reales en este proyecto.")

    def export_drum_parts(self):
        h=self.home
        chosen=[
            (name,row["path"]) for name,row in h.drum_stem_rows.items()
            if self.selected_parts[name].isChecked() and row["path"] is not None
            and row["path"].is_file()
        ]
        if not chosen:
            QMessageBox.information(self.extra,"Sin pistas","No hay piezas seleccionadas disponibles.")
            return
        target=file_dialogs.get_existing_directory(self.extra,"Guardar piezas de batería")
        if not target:return
        destination=Path(target)
        from task_staging import unique_dest
        copied=0
        for name,source in chosen:
            dest=unique_dest(destination,Path(source).name)
            shutil.copy2(source,dest)
            copied+=1
        self.status.setText(f"Guardadas {copied} piezas en {destination}.")

    def filter_results(self,_=None):
        if self.kind!="results":return
        table=self.home.files
        term=self.search.text().casefold().strip()
        kind=self.result_type.currentText()
        for row in range(table.rowCount()):
            item=table.item(row,0)
            type_item=table.item(row,1)
            text=item.text().casefold() if item else ""
            category=type_item.text() if type_item else ""
            table.setRowHidden(row,bool((term and term not in text)
                or (kind!="Todos" and kind!=category)))

    def copy_info(self):
        h=self.home
        text="\n".join(w.text() for w in
             (h.note_info,h.duration_info,h.tempo_info,h.key_info))
        QApplication=__import__("PySide6").QtWidgets.QApplication
        QApplication.clipboard().setText(text)
        self.status.setText("Información copiada.")

    def refresh(self):
        if not self.extra.isVisible():return
        h=self.home
        self._updating=True
        try:
            for data in self.proxies:
                source,target,mode=data[:3]
                if mode=="combo":
                    if (source.count()!=target.count() or any(
                            source.itemText(i)!=target.itemText(i)
                            for i in range(source.count()))):
                        previous=target.blockSignals(True)
                        target.clear()
                        for index in range(source.count()):
                            target.addItem(source.itemText(index),source.itemData(index))
                        target.blockSignals(previous)
                    if target.currentIndex()!=source.currentIndex() and not target.view().isVisible():
                        old=target.blockSignals(True)
                        target.setCurrentIndex(source.currentIndex())
                        target.blockSignals(old)
                elif mode=="slider":
                    target.setRange(source.minimum(),source.maximum())
                    old=target.blockSignals(True)
                    target.setValue(source.value())
                    target.blockSignals(old)
                    data[3].setText(str(source.value()))
                elif mode=="check":
                    old=target.blockSignals(True)
                    target.setChecked(source.isChecked())
                    target.blockSignals(old)
            if self.kind=="monitor":
                self.status.setText(h.monitor_state.text())
                self.details.setText("Ganancia y balance funcionan sobre la entrada activa.")
            elif self.kind=="midi":
                self.midi_browser.refresh()
            elif self.kind=="drums":
                self.refresh_drum_pieces()
                self.status.setText(h._drum_module.status.text()
                    if h._drum_module is not None else h.drum_state.text())
                self.details.setText("MDX23C: "+("instalado" if h._drum_module and h._drum_module.model_ready() else "pendiente"))
            elif self.kind=="vocal":
                if self.vocal_studio is not None:
                    self.vocal_studio.refresh()
            elif self.kind=="piano":
                self.piano_tools.refresh_files()
            elif self.kind=="tracks":
                active=sum(bool(v["path"] and v["path"].is_file()) for v in h.track_rows.values())
                self.status.setText(f"{active} pistas reales disponibles")
                self.details.setText("Solo y Mute siguen operativos en las pistas originales.")
            elif self.kind=="mixer":
                self.project_mixer.refresh_catalog()
            elif self.kind=="drum_stems":
                active=sum(bool(v["path"] and v["path"].is_file()) for v in h.drum_stem_rows.values())
                self.status.setText(f"{active} piezas de batería disponibles")
                self.details.setText("Solo se exportan archivos existentes y piezas marcadas.")
            elif self.kind=="wave":
                self.status.setText(h.wave_title.text())
                self.details.setText("Zoom aplicado directamente a la forma de onda original.")
            elif self.kind=="results":
                self.filter_results()
                self.status.setText(f"{h.files.rowCount()} resultados en esta tarea")
                self.details.setText("Selecciona una o varias filas; guarda sin sobrescribir originales.")
            elif self.kind=="info":
                self.info_expanded.refresh_runtime()
        finally:self._updating=False

    def _lift_midi_controls(self):
        """Colocar los controles originales en 2 columnas, solo en flotante.

        Se trasladan los objetos Qt reales, preservando señales, presets y
        valores. Al cerrar el candado, regresan a sus índices iniciales.
        """
        if self._midi_lifted:return
        from PySide6.QtWidgets import QHBoxLayout
        inner=self.card.inner
        home=self.home
        sliders=tuple(home.midi_sliders.values())
        layouts=[]
        for index in range(inner.count()):
            item=inner.itemAt(index)
            layout=item.layout()
            widget=item.widget()
            if layout is not None:
                contents={layout.itemAt(i).widget() for i in range(layout.count())
                          if layout.itemAt(i).widget() is not None}
                if (any(w in contents for w in sliders)
                        or home.refine in contents or home.quant in contents
                        or home.chords_check in contents):
                    layouts.append((index,"layout",layout))
            elif widget in (home.chords_check,home.midi_run):
                layouts.append((index,"widget",widget))
        if len(layouts)!=8:
            raise RuntimeError("Los ocho controles MIDI no están completos")
        # QVBoxLayout.takeAt elimina la entrada sin destruir su contenido.
        for index,kind,obj in reversed(layouts):
            entry=inner.takeAt(index)
            if (entry.layout() if kind=="layout" else entry.widget()) is not obj:
                raise RuntimeError("Orden de los controles MIDI modificado")
        self._midi_lifted=layouts
        grid=self.midi_settings_grid
        for (_,kind,obj),(row,column) in zip(layouts,
                ((0,0),(0,1),(1,0),(1,1),(2,0),(2,1),(3,0),(3,1))):
            if kind=="layout":
                grid.addLayout(obj,row,column)
            else:
                grid.addWidget(obj,row,column)
        # No ocultar los controles: la misma instancia alimenta el motor.
        self.midi_settings.updateGeometry()

    def _restore_midi_controls(self):
        if not self._midi_lifted:return
        inner=self.card.inner
        grid=self.midi_settings_grid
        # Sacar de la cuadrícula sin destruir los widgets o sub-layouts.
        for index,kind,obj in self._midi_lifted:
            grid.removeItem(next(
                grid.itemAt(i) for i in range(grid.count())
                if (grid.itemAt(i).layout() if kind=="layout"
                    else grid.itemAt(i).widget()) is obj))
        for index,kind,obj in self._midi_lifted:
            if kind=="layout":inner.insertLayout(index,obj)
            else:inner.insertWidget(index,obj)
        self._midi_lifted=[]

    def _toggle_midi_duplicate_rows(self,hide):
        """Solo en flotante: no repetir IA/Pista bajo el catálogo superior.

        Los controles originales permanecen vivos con sus señales y
        reaparecen al cerrar el candado.
        """
        if hide:
            self._midi_original_controls=[]
            self._midi_width_restore=[]
            layout=self.card.inner
            targets={self.home.engine,self.home.midi_preset,
                     self.home.midi_stem_select,self.home.load_midi_model,
                     self.home.midi_stem_reload}
            for index in range(layout.count()):
                row=layout.itemAt(index).layout()
                if not isinstance(row,QHBoxLayout):continue
                widgets=[row.itemAt(j).widget() for j in range(row.count())
                         if row.itemAt(j).widget() is not None]
                if any(w in targets for w in widgets):
                    for w in widgets:
                        self._midi_original_controls.append((w,w.isHidden()))
                        w.hide()
                elif (len(widgets)>=2 and widgets[1] in
                      self.home.midi_sliders.values()):
                    caption=widgets[0]
                    self._midi_width_restore.append(
                        (caption,caption.maximumWidth()))
                    caption.setMaximumWidth(190)
        else:
            for widget,hidden in getattr(self,"_midi_original_controls",()):
                if not hidden:widget.show()
            self._midi_original_controls=[]
            for caption,width in getattr(self,"_midi_width_restore",()):
                caption.setMaximumWidth(width)
            self._midi_width_restore=[]

    def _toggle_drum_original(self,hide):
        # Guardar los estados originales de cada widget, incluido el título
        # y los indicadores; no moverlos ni destruirlos.
        from PySide6.QtWidgets import QLayout
        if hide:
            seen=set()
            self._drum_original_controls=[]
            def walk(layout):
                for i in range(layout.count()):
                    item=layout.itemAt(i)
                    widget=item.widget()
                    nested=item.layout()
                    if widget is not None and widget is not self.extra and id(widget) not in seen:
                        seen.add(id(widget))
                        self._drum_original_controls.append((widget,widget.isHidden()))
                        widget.hide()
                    if nested is not None:walk(nested)
            walk(self.card.inner)
        else:
            for widget,originally_hidden in getattr(self,"_drum_original_controls",()):
                if not originally_hidden:
                    widget.show()
            self._drum_original_controls=[]

    def _toggle_mixer_original(self,hide):
        # Los siete faders compactos permanecen funcionales en Inicio,
        # pero NO se duplican dentro de la ventana ampliada.
        if hide:
            self._mixer_original=[]
            def walk(layout):
                for i in range(layout.count()):
                    item=layout.itemAt(i)
                    widget=item.widget()
                    if widget is not None and widget is not self.extra:
                        self._mixer_original.append((widget,widget.isHidden()))
                        widget.hide()
                    if item.layout() is not None:walk(item.layout())
            walk(self.card.inner)
        else:
            for widget,was_hidden in getattr(self,"_mixer_original",()):
                if not was_hidden:widget.show()
            self._mixer_original=[]

    def _install_piano_splitter(self):
        """Separador vertical real entre panel superior y roll inferior.

        Los widgets reales, sus señales y sus valores se mueven UNA vez
        a un contenedor inferior. Al cerrar el candado vuelven a su
        posición, por lo que la vista acoplada sigue siendo compacta.
        """
        if getattr(self,"_piano_splitter",None) is not None:return
        inner=self.card.inner
        entries=[]
        while inner.count():
            item=inner.takeAt(0)
            obj=item.widget()
            layout=item.layout()
            if obj is not None:
                entries.append(("widget",obj))
            elif layout is not None:
                entries.append(("layout",layout))
            else:
                raise RuntimeError("Elemento desconocido en panel de Piano Roll")
        assert entries and entries[0][1] is self.extra
        bottom=QWidget(self.card)
        bottom.setObjectName("pianoResizableBottom")
        bottom_layout=QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0,0,0,0)
        bottom_layout.setSpacing(4)
        # El separador anterior se podía confundir con una línea ornamental
        # y parecía bajar solamente: botón inequívoco que recoge el panel
        # SUPERIOR, deja al roll ocupar toda la altura y permite revertirlo.
        toggle=QPushButton("↑ Ampliar Piano Roll al máximo",bottom)
        toggle.setObjectName("pianoExpandUpButton")
        toggle.setFixedHeight(26)
        toggle.setToolTip(
            "Oculta los controles de arriba y sube la zona de notas"
            " hasta la cabecera de Piano Roll. También puedes arrastrar"
            " directamente el separador azul situado sobre este botón.")
        toggle.setStyleSheet(
            "QPushButton#pianoExpandUpButton{background:#103d70;"
            "color:#e7faff;border:1px solid #58d7ff;border-radius:4px;"
            "font-weight:700;font-size:12px;}"
            "QPushButton#pianoExpandUpButton:hover{background:#176ba5;}")
        bottom_layout.addWidget(toggle)
        self._piano_expand_button=toggle
        toggle.clicked.connect(self._toggle_piano_full_height)
        for kind,obj in entries[1:]:
            if kind=="widget":
                bottom_layout.addWidget(obj,1 if obj is self.home.piano_preview else 0)
            else:
                bottom_layout.addLayout(obj,1 if any(
                    obj.itemAt(i).widget() is self.home.piano_preview
                    for i in range(obj.count())) else 0)
        splitter=QSplitter(Qt.Vertical,self.card)
        splitter.setObjectName("pianoHeightSplitter")
        splitter.setHandleWidth(13)
        splitter.setStyleSheet("""
            QSplitter#pianoHeightSplitter::handle:vertical{
                background:#1769a5;border-top:2px solid #63dafa;
                border-bottom:2px solid #48b7ef;border-radius:4px;
                margin:1px 0;
            }
            QSplitter#pianoHeightSplitter::handle:vertical:hover{
                background:#23a2dc;border-color:#aeffff;
            }
        """)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.extra)
        splitter.addWidget(bottom)
        splitter.setCollapsible(0,True)
        splitter.setCollapsible(1,False)
        splitter.setStretchFactor(0,0)
        splitter.setStretchFactor(1,1)
        splitter.handle(1).setToolTip(
            "Arrastra esta división hacia arriba para ampliar el Piano Roll"
            " hasta casi toda la ventana; arrástrala abajo para ver"
            " nuevamente las herramientas de composición.")
        splitter.handle(1).setCursor(Qt.SizeVerCursor)
        self.piano_tools.setMinimumHeight(0)
        self.piano_tools.setMaximumHeight(16777215)
        self.extra.setMinimumHeight(0)
        inner.addWidget(splitter,1)
        self._piano_splitter=splitter
        self._piano_split_bottom=bottom
        # La zona inferior conserva al menos 185 px, y puede tomar
        # prácticamente toda la tarjeta al colapsar la zona superior.
        bottom.setMinimumHeight(185)
        from PySide6.QtCore import QTimer
        def init_splitter():
            if self._piano_splitter is not splitter:return
            splitter.setSizes([485,max(190,splitter.height()-485)])
            self._piano_baseline_top=max(1,splitter.sizes()[0])
            preview=self.home.piano_preview
            self._piano_baseline_span=preview.pitch_hi-preview.pitch_lo+1
            self._piano_baseline_center=(preview.pitch_lo+preview.pitch_hi)/2
            splitter.splitterMoved.connect(self._update_piano_pitch_for_split)
        QTimer.singleShot(0,init_splitter)

    def _update_piano_pitch_for_split(self,*args):
        """Arrastrar la división también amplía el número de octavas.

        Herramientas visibles: conserva la vista inicial. Herramientas
        completamente recogidas: muestra las 88 teclas reales.
        """
        split=getattr(self,"_piano_splitter",None)
        if split is None or not hasattr(self,"_piano_baseline_top"):return
        top=split.sizes()[0]
        button=getattr(self,"_piano_expand_button",None)
        if button is not None:
            button.setText("↓ Mostrar herramientas de composición"
                           if top<12 else "↑ Ampliar Piano Roll al máximo")
        fraction=max(0.,min(1.,
            (self._piano_baseline_top-top)/self._piano_baseline_top))
        initial=self._piano_baseline_span
        span=max(8,min(88,round(initial+(88-initial)*fraction)))
        preview=self.home.piano_preview
        if preview.pitch_hi-preview.pitch_lo+1==span:return
        low=round(self._piano_baseline_center-(span-1)/2)
        preview.set_pitch_window(low,span)

    def _toggle_piano_full_height(self):
        split=getattr(self,"_piano_splitter",None)
        if split is None:return
        top=split.sizes()[0]
        if top<12:
            split.moveSplitter(getattr(self,"_piano_baseline_top",480),1)
        else:
            split.moveSplitter(0,1)
        self._update_piano_pitch_for_split()

    def _restore_piano_splitter(self):
        splitter=getattr(self,"_piano_splitter",None)
        if splitter is None:return
        inner=self.card.inner
        bottom=self._piano_split_bottom
        lower=bottom.layout()
        entries=[]
        while lower.count():
            item=lower.takeAt(0)
            if item.widget() is getattr(self,"_piano_expand_button",None):
                item.widget().deleteLater()
                continue
            if item.widget() is not None:
                entries.append(("widget",item.widget()))
            elif item.layout() is not None:
                entries.append(("layout",item.layout()))
        self.extra.setParent(self.card)
        inner.removeWidget(splitter)
        inner.insertWidget(0,self.extra)
        for index,(kind,obj) in enumerate(entries,1):
            if kind=="widget":
                inner.insertWidget(index,obj)
            else:
                inner.insertLayout(index,obj)
        bottom.setParent(None)
        splitter.deleteLater()
        bottom.deleteLater()
        self._piano_splitter=None
        self._piano_split_bottom=None
        self._piano_expand_button=None
        self.piano_tools.setMinimumHeight(475)
        self.piano_tools.setMaximumHeight(475)
        self.extra.setMinimumHeight(0)

    def expand(self):
        if self.kind=="vocal":
            if self.vocal_studio is None:
                from home_vocal_studio import VocalHomeStudio
                self.vocal_studio=VocalHomeStudio(self.home,self.extra)
                self.layout.addWidget(self.vocal_studio,1)
                self.layout.itemAt(0).widget().hide()
            self._vocal_hidden=[]
            # No dejar la versión simplificada encima ni debajo de la
            # vista avanzada (sus controles reales siguen sincronizados).
            for widget in (
                self.home.vocal_source,self.home.vocal_tonic,
                self.home.vocal_scale,self.home.vocal_strength,
                self.home.vocal_run,self.home.vocal_state):
                self._vocal_hidden.append(widget)
                widget.hide()
            for label in self.card.findChildren(QLabel):
                if label.text()=="Voz del proyecto" and label not in self._vocal_hidden:
                    self._vocal_hidden.append(label)
                    label.hide()
            self._vocal_spacers=[]
            inner=self.card.inner
            for index in reversed(range(inner.count())):
                if inner.itemAt(index).spacerItem() is not None:
                    self._vocal_spacers.append(inner.takeAt(index))
            self.extra.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
            self.extra.setMinimumHeight(0)
            self.vocal_studio.show()
        if self.kind=="mixer":
            bridge=getattr(self,"professional_bridge",None)
            if bridge is not None:bridge.to_floating()
            self._toggle_mixer_original(True)
            self.project_mixer.reopen()
        if self.kind=="piano":
            self.home.piano_navigation.show()
            self.home.piano_pitch_scroll.show()
            self._install_piano_splitter()
            self.piano_tools.refresh_files(force=True)
        if self.kind=="info":
            bridge=getattr(self,"professional_bridge",None)
            if bridge is not None:bridge.to_floating()
            self.home.midi_to_audio.hide()
            self.info_expanded.refresh_files(force=True)
        if self.kind=="drums":
            self._toggle_drum_original(True)
        if self.kind=="midi":
            self._toggle_midi_duplicate_rows(True)
            self._lift_midi_controls()
        self.extra.show()
        if self.kind=="drum_stems":
            self.drum_timeline.start()
        if self.kind=="wave":
            self.wave_info.start()
        if self.kind=="monitor":
            self.home.audio_lab_button.hide()
            self.home.capture_gain_panel.hide()
            self.home.record_transport.setMinimumWidth(280)
            self.home.record_transport.setMaximumWidth(280)
            self.home.capture_analyzer_panel.show()
            self.home.populate_processed_listen_outputs()
            self.review.balance_mount.addWidget(self.home.capture_balance_panel)
            self.home.capture_balance_panel.show()
            self.home.capture_diagnostics.show()
            self.home.update_capture_diagnostics()
            self.review.apply_eq()
            self.review.ticker.start()
            self.review.refresh()
        self.refresh_timer.start()
        if self.kind=="vocal":
            self.vocal_studio.expand()
        if self.kind=="midi":
            # Reactivar envolventes tras volver a abrir el panel.
            self.midi_browser.refresh(force=True)
        self.refresh()
    def collapse(self):
        self.refresh_timer.stop()
        if self.kind=="vocal":
            if self.vocal_studio is not None:self.vocal_studio.collapse()
            for widget in self._vocal_hidden:widget.show()
            self._vocal_hidden=[]
            for spacer in reversed(self._vocal_spacers):
                self.card.inner.addItem(spacer)
            self._vocal_spacers=[]
        if self.kind=="piano":
            self._restore_piano_splitter()
            self.home.piano_navigation.hide()
            self.home.piano_pitch_scroll.hide()
        if self.kind=="mixer":
            self._toggle_mixer_original(False)
            bridge=getattr(self,"professional_bridge",None)
            if bridge is not None:bridge.to_tab()
        if self.kind=="info":
            self.home.midi_to_audio.show()
            bridge=getattr(self,"professional_bridge",None)
            if bridge is not None:bridge.to_tab()
        if self.kind=="drum_stems":
            self.drum_timeline.stop()
        if self.kind=="wave":
            self.wave_info.stop()
        if self.kind=="drums":
            self._toggle_drum_original(False)
        if self.kind=="midi":
            self.midi_browser.listen.stop()
            self.midi_browser.cancel_wave_previews()
            self._restore_midi_controls()
            self._toggle_midi_duplicate_rows(False)
        if self.kind=="monitor":
            self.review.stop_playback()
            self.review.ticker.stop()
            if self.home.listen_processed.isChecked():
                self.home.listen_processed.setChecked(False)
            self.home.capture_analyzer_panel.hide()
            self.home.record_transport.setMinimumWidth(0)
            self.home.record_transport.setMaximumWidth(16777215)
            self.home.capture_balance_home_layout.addWidget(
                self.home.capture_balance_panel,0)
            self.home.capture_balance_panel.show()
            self.home.capture_diagnostics.hide()
            self.home.capture_gain_panel.show()
            self.home.audio_lab_button.show()
        self.extra.hide()
        if self.kind=="results":
            self.search.clear()
            self.result_type.setCurrentIndex(0)
            self.filter_results()
