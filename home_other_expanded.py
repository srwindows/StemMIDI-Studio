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
 QComboBox,QLineEdit,QSlider,QCheckBox,QFileDialog,QMessageBox,QSizePolicy
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
 "info":"INFORMACIÓN DEL PROYECTO",
}
STEM_NAMES=("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros")
DRUM_NAMES=("Bombo","Caja","Toms","Charles","Ride","Crash")

def preset_path():
    # Ajustes propios del proyecto/programa. Los audios se mantienen aparte.
    from studio_paths import workspace_root
    location=workspace_root(__file__)
    return location/"presets_modulos_inicio.json"

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
        if self.kind=="monitor":
            # Estado y ganancia ya están en la tarjeta original. Evitar
            # solapamientos con el panel nuevo de tonos en flotante.
            self.status.hide()
            self.details.hide()
        self.card.inner.insertWidget(0,self.extra)
        self.extra.hide()
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
        row.addWidget(QLabel("Preset de Inicio"))
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
        for value in sorted(read_presets().get(self.kind,{})):
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
        data=read_presets()
        data.setdefault(self.kind,{})[name]=self.snapshot()
        write_presets(data)
        self.refresh_preset_names()
        self.choice.setCurrentText(name)
        self.status.setText("Preset guardado: "+name)

    def load_preset(self,index):
        if index<=0:return
        data=read_presets().get(self.kind,{}).get(self.choice.itemText(index))
        if isinstance(data,dict):
            self.apply(data)
            if self.kind=="monitor":self.review.apply_eq()
            self.name.setText(self.choice.itemText(index))
            self.status.setText("Preset aplicado: "+self.choice.itemText(index))

    def delete_preset(self):
        name=self.choice.currentText()
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
            self.preset_toolbar()
            self.add_combo("Motor de transcripción",h.engine)
            self.add_combo("Preset del motor",h.midi_preset)
            self.add_combo("Refinamiento",h.refine)
            self.add_actions(("Cargar audio…",self.import_midi_audio),
                             ("Convertir a MIDI",self.run_midi_here))
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
            self.add_actions(("Escuchar audio",self.play_wave),
                             ("Detener",h.stop_audio))
        elif self.kind=="drums":
            self.add_combo("Batería del proyecto",h.drum_source)
            self.add_actions(("Importar batería…",self.import_drum),
                             ("Instalar IA",self.install_drum),
                             ("Desglosar",self.run_drum_here))
        elif self.kind=="tracks":
            for key in STEM_NAMES:self.register("nivel_"+key,h.track_rows[key]["gain"])
            self.preset_toolbar()
            # Se reutilizan controles S/M y reproducción de las siete filas.
            for key in STEM_NAMES:
                self.add_slider(key+" · nivel",h.track_rows[key]["gain"])
            self.add_actions(("Escuchar selección",self.play_first_stem),
                             ("Detener",h.stop_audio))
        elif self.kind=="mixer":
            for key in STEM_NAMES:
                self.register("fader_"+key,h.mixer_rows[key]["fader"])
                self.register("solo_"+key,h.track_rows[key]["solo"])
                self.register("mute_"+key,h.track_rows[key]["mute"])
            self.preset_toolbar()
            self.add_slider("Volumen de preescucha",h.master_volume)
            self.add_actions(("Restablecer mezcla",h.reset_mixer),
                             ("Detener",h.stop_audio))
        elif self.kind=="piano":
            for name,widget in (("cuadrícula",h.grid_choice),
                                ("velocidad",h.note_velocity)):
                self.register(name,widget)
            self.preset_toolbar()
            self.add_combo("MIDI del proyecto",h.midi_choice)
            self.add_combo("Cuadrícula",h.grid_choice)
            self.add_slider("Velocidad de nota",h.note_velocity)
            self.add_actions(("Cargar MIDI…",self.import_midi),
                             ("Mostrar notas MIDI",self.play_midi))
        elif self.kind=="vocal":
            for name,w in (("tonalidad",h.vocal_tonic),("escala",h.vocal_scale),
                          ("intensidad",h.vocal_strength)):
                self.register(name,w)
            self.preset_toolbar()
            self.add_combo("Voz",h.vocal_source)
            self.add_combo("Tonalidad",h.vocal_tonic)
            self.add_combo("Escala",h.vocal_scale)
            self.add_slider("Intensidad",h.vocal_strength)
            self.add_actions(("Afinar voz",self.run_vocal_here))
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
            self.add_actions(("Copiar información",self.copy_info),
                             ("Actualizar información",lambda:h.refresh(force=True)))
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
                m=h.workbench.converter
                self.status.setText("Audio: "+(Path(m.audio_path.text()).name or "sin cargar"))
                self.details.setText("Transcripción en curso" if m.process else "Motor preparado · ajustes vinculados al convertidor")
            elif self.kind=="drums":
                self.status.setText(h.drum_state.text())
                self.details.setText("MDX23C: "+("instalado" if h._drum_module and h._drum_module.model_ready() else "pendiente"))
            elif self.kind=="vocal":
                self.status.setText(h.vocal_state.text())
                self.details.setText("Tonalidad, escala e intensidad actúan sobre el procesador real.")
            elif self.kind=="piano":
                self.status.setText("Archivo: "+(h.selected_midi.name if h.selected_midi else "ninguno"))
                self.details.setText(h.note_info.text()+" · "+h.tempo_info.text())
            elif self.kind=="tracks":
                active=sum(bool(v["path"] and v["path"].is_file()) for v in h.track_rows.values())
                self.status.setText(f"{active} pistas reales disponibles")
                self.details.setText("Solo y Mute siguen operativos en las pistas originales.")
            elif self.kind=="mixer":
                self.status.setText("Niveles y Solo/Mute editables sin abandonar Inicio.")
                self.details.setText("Los faders actúan sobre la mezcla/preescucha de stems.")
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
                self.status.setText(h.note_info.text()+" · "+h.duration_info.text())
                self.details.setText(h.tempo_info.text()+" · "+h.key_info.text())
        finally:self._updating=False

    def expand(self):
        self.extra.show()
        if self.kind=="monitor":
            self.home.audio_lab_button.hide()
            self.review.ticker.start()
            self.review.refresh()
        self.refresh_timer.start()
        self.refresh()
    def collapse(self):
        self.refresh_timer.stop()
        if self.kind=="monitor":
            self.review.stop_playback()
            self.review.ticker.stop()
            self.home.audio_lab_button.show()
        self.extra.hide()
        if self.kind=="results":
            self.search.clear()
            self.result_type.setCurrentIndex(0)
            self.filter_results()
