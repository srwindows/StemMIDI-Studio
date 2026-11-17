"""Inventario interconectado de Inicio · Audio a MIDI.

Stems visibles y marcables; cola secuencial sobre el motor REAL existente;
historial de MIDI del proyecto, accesible en Resultados y Piano Roll.
No se crean muestras, pistas o modelos falsos.
"""
from __future__ import annotations
from pathlib import Path
import time

from PySide6.QtCore import Qt,QTimer,QSize,QItemSelectionModel,QProcess
from PySide6.QtWidgets import (QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QComboBox,QListWidget,QListWidgetItem,QSizePolicy,QListView,
    QWidget,QCheckBox,QProgressBar,QMenu)

MIDI_EXT={".mid",".midi",".kar"}
DRUM_PARTS=frozenset(("Bombo","Caja","Toms","Charles","Ride","Crash"))

class StemWaveRow(QWidget):
    """Fila real: selección, nombre y envolvente sonora del archivo fuente."""
    def __init__(self,browser,inventory,item,file,name,is_drum=False):
        super().__init__(inventory)
        self.browser=browser
        self.inventory=inventory
        self.item=item
        self.path=Path(file)
        self.setObjectName("midiAudioWaveRow")
        self.setAttribute(Qt.WA_StyledBackground,True)
        self.setToolTip(str(file))
        line=QHBoxLayout(self)
        line.setContentsMargins(2,0,2,0)
        line.setSpacing(3)
        self.check=QCheckBox(self)
        self.check.setObjectName("midiStemCheckbox")
        self.check.setToolTip("Marcar: escuchar en la mezcla y convertir a MIDI")
        self.check.setChecked(item.checkState()==Qt.Checked)
        self.check.stateChanged.connect(self._checked_changed)
        line.addWidget(self.check,0)
        self.caption=QLabel(name,self)
        self.caption.setMinimumWidth(0)
        self.caption.setFixedWidth(65 if is_drum else 103)
        self.caption.setToolTip(str(file))
        line.addWidget(self.caption,0)
        from studio_home import WaveCanvas
        self.wave=WaveCanvas(small=True,parent=self)
        self.wave.setMinimumWidth(36)
        self.wave.setFixedHeight(20)
        self.wave.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.wave.wave_color="#63eaff"
        self.wave.setToolTip("Onda real · clic para escuchar todas las pistas marcadas: "+str(file))
        self.wave.clicked.connect(self._preview)
        line.addWidget(self.wave,1)
        self.wave.set_file(self.path)

    def _checked_changed(self,state):
        self.item.setCheckState(Qt.Checked if state==Qt.Checked.value else Qt.Unchecked)

    def sync_check(self):
        checked=self.item.checkState()==Qt.Checked
        if self.check.isChecked()!=checked:
            blocker=self.check.blockSignals(True)
            self.check.setChecked(checked)
            self.check.blockSignals(blocker)

    def _preview(self,fraction):
        self.inventory.setCurrentItem(self.item)
        other=self.browser.drums if self.inventory is self.browser.stems else self.browser.stems
        other.clearSelection()
        if self.path.is_file():
            if not self.browser.checked():
                self.item.setCheckState(Qt.Checked)
            self.browser.listen.play()

    def mousePressEvent(self,event):
        self.inventory.setCurrentItem(self.item)
        other=self.browser.drums if self.inventory is self.browser.stems else self.browser.stems
        other.clearSelection()
        super().mousePressEvent(event)

    def cleanup(self):
        self.wave.cancel_decode()

class MidiHomePanel(QFrame):
    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self.setObjectName("midiHomeBrowser")
        self.setStyleSheet("""
          QFrame#midiHomeBrowser{background:#05204a;border:1px solid #27b0f1;border-radius:7px;}
          QListWidget#midiHomeStems,QListWidget#midiHomeDrums,QListWidget#midiHomeFiles{
            background:#031734;border:1px solid #187ac4;border-radius:4px;
            color:#dcf7ff;font-size:12px;}
          QWidget#midiAudioWaveRow{background:#031734;border:0;}
          QCheckBox#midiStemCheckbox{spacing:0;padding:0;min-width:16px;max-width:16px;}
          QCheckBox#midiStemCheckbox::indicator{width:14px;height:14px;
            border:1px solid #48c9ff;border-radius:3px;background:#041a3b;}
          QCheckBox#midiStemCheckbox::indicator:checked{
            border:1px solid #adffff;background:#0cc6e7;
            image:none;}
          QListWidget::item{padding:0px 1px;}
          QListWidget::item:selected{background:#0a579b;color:white;}
        """)
        box=QVBoxLayout(self)
        # No permitir que la franja de botones se pinte sobre las pistas.
        self.setMinimumHeight(367)
        box.setContentsMargins(9,5,9,5);box.setSpacing(4)
        top=QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(QLabel("IA de transcripción"))
        self.model=QComboBox(self)
        self.model.setToolTip("Motor real o modelo importado compatible con Basic Pitch.")
        self.model.setMinimumWidth(150)
        self.model.currentIndexChanged.connect(self.select_model)
        top.addWidget(self.model,1)
        self.load_model=QPushButton("Cargar IA…",self)
        self.load_model.setToolTip("Validar e instalar un modelo ONNX compatible.")
        self.load_model.clicked.connect(home.import_midi_model)
        top.addWidget(self.load_model)
        self.reload=QPushButton("↻ Actualizar",self)
        self.reload.clicked.connect(lambda:self.refresh(force=True))
        top.addWidget(self.reload)
        box.addLayout(top)
        # Tres inventarios independientes, sin mezclar instrumentos con
        # elementos de bateria. Los archivos son siempre reales del proyecto.
        cols=QHBoxLayout()
        cols.setSpacing(7)
        left=QVBoxLayout();left.setSpacing(3)
        self.stem_title=QLabel("STEMS SEPARADOS · 0",self)
        self.stem_title.setToolTip("Voces, piano, guitarra, bajo, viento, otros y bateria completa")
        left.addWidget(self.stem_title)
        self.stems=QListWidget(self)
        self.stems.setObjectName("midiHomeStems")
        self.stems.setToolTip("Marca instrumentos para convertir. Doble clic para preparar una pista.")
        # Dos columnas compactas para que las voces e instrumentos estén
        # visibles juntos, sin ocupar la altura de la zona de parámetros.
        self.stems.setFlow(QListView.TopToBottom)
        self.stems.setWrapping(False)
        self.stems.itemDoubleClicked.connect(self.choose_stem)
        self.stems.itemChanged.connect(self._on_item_changed)
        self.stems.itemClicked.connect(lambda item:self._select_audio(item,self.drums))
        left.addWidget(self.stems,1)
        cols.addLayout(left,39)

        center=QVBoxLayout();center.setSpacing(3)
        self.drum_title=QLabel("BATERÍA DESGLOSADA · 0",self)
        self.drum_title.setToolTip("Piezas individuales creadas en Desglose de bateria")
        center.addWidget(self.drum_title)
        self.drums=QListWidget(self)
        self.drums.setObjectName("midiHomeDrums")
        self.drums.setToolTip("Marca piezas de batería para convertir a MIDI por separado.")
        # Seis piezas en tres filas, visibles incluso en una flotante compacta.
        self.drums.setFlow(QListView.TopToBottom)
        self.drums.setWrapping(False)
        self.drums.itemDoubleClicked.connect(self.choose_stem)
        self.drums.itemChanged.connect(self._on_item_changed)
        self.drums.itemClicked.connect(lambda item:self._select_audio(item,self.stems))
        center.addWidget(self.drums,1)
        cols.addLayout(center,32)

        right=QVBoxLayout();right.setSpacing(3)
        self.midi_title=QLabel("MIDI GENERADOS · 0",self)
        midi_header=QHBoxLayout()
        midi_header.setSpacing(3)
        midi_header.addWidget(self.midi_title,1)
        right.addLayout(midi_header)
        self.midis=QListWidget(self)
        self.midis.setObjectName("midiHomeFiles")
        self.midis.setToolTip(
            "Selección múltiple: Ctrl+clic, Mayús+clic o Ctrl+A. "
            "Clic derecho para guardar o eliminar varios MIDI.")
        self.midis.setSelectionMode(QListWidget.ExtendedSelection)
        self.midis.itemSelectionChanged.connect(self._selected_midi_changed)
        self.midis.itemDoubleClicked.connect(self.open_midi)
        right.addWidget(self.midis,1)
        cols.addLayout(right,29)

        for inventory in (self.stems,self.drums,self.midis):
            inventory.setContextMenuPolicy(Qt.CustomContextMenu)
            inventory.customContextMenuRequested.connect(
                lambda position,list_widget=inventory:
                    self._context_file(list_widget,position))
            inventory.setMinimumHeight(249)
            inventory.setMaximumHeight(280)
            inventory.setSpacing(0)
            inventory.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        box.addLayout(cols,1)

        # Controles debajo de cada inventario; no crear una segunda fila alta.
        actions=QHBoxLayout();actions.setSpacing(7)
        left_buttons=QHBoxLayout();left_buttons.setSpacing(3)
        self.mark_all=QPushButton("Todos",self)
        self.mark_all.setToolTip("Marcar todos los stems y piezas de batería")
        self.mark_all.clicked.connect(lambda:self.set_all(True))
        self.clear_all=QPushButton("Ninguno",self)
        self.clear_all.clicked.connect(lambda:self.set_all(False))
        self.preview=QPushButton("▶",self)
        self.preview.setToolTip("Escuchar todas las pistas marcadas juntas sin crear otra mezcla")
        self.preview.clicked.connect(self.preview_stem)
        for w in (self.mark_all,self.clear_all,self.preview):
            left_buttons.addWidget(w)
        actions.addLayout(left_buttons,39)
        drum_buttons=QHBoxLayout();drum_buttons.setSpacing(2)
        self.convert=QPushButton("Convertir marcados",self)
        self.convert.setObjectName("primary")
        self.convert.setToolTip("Convertir los stems y las piezas marcadas en cola secuencial")
        self.convert.clicked.connect(self.convert_checked)
        drum_buttons.addWidget(self.convert,1)
        actions.addLayout(drum_buttons,32)
        right_buttons=QHBoxLayout();right_buttons.setSpacing(3)
        self.piano=QPushButton("Piano Roll",self)
        self.piano.setToolTip("Abrir el archivo MIDI seleccionado en Piano Roll")
        self.piano.clicked.connect(self.open_midi)
        self.results=QPushButton("Resultados",self)
        self.results.clicked.connect(self.show_results)
        right_buttons.addWidget(self.piano,1)
        right_buttons.addWidget(self.results,1)
        self.midi_play=QPushButton("▶ MIDI",self)
        self.midi_play.setObjectName("playGeneratedMidi")
        self.midi_play.setFixedWidth(63)
        self.midi_play.setToolTip(
            "Escuchar MIDI seleccionado desde aquí, sin abrir Piano Roll. "
            "Control de reproducción compartido entre todos los módulos.")
        self.midi_play.clicked.connect(self.play_selected_midi)
        # Play / Pausa / Stop juntos dentro del mismo módulo y con
        # el MISMO motor MIDI global; no introducir otra salida de sonido.
        self.midi_pause=QPushButton("Ⅱ",self)
        self.midi_pause.setObjectName("pauseGeneratedMidi")
        self.midi_pause.setFixedWidth(27)
        self.midi_pause.setToolTip("Pausar la reproducción MIDI actual; vuelve a pulsar para reanudar.")
        self.midi_pause.clicked.connect(self.pause_selected_midi)
        self.midi_stop=QPushButton("■",self)
        self.midi_stop.setObjectName("stopGeneratedMidi")
        self.midi_stop.setFixedWidth(27)
        self.midi_stop.setToolTip("Detener completamente la reproducción MIDI y volver al inicio.")
        self.midi_stop.clicked.connect(self.stop_selected_midi)
        # Encima de la lista de MIDI, sin comprimir la fila de acciones
        # ni añadir scroll a la distribución compacta.
        for button in (self.midi_play,self.midi_pause,self.midi_stop):
            midi_header.addWidget(button)
        self._midi_transport_timer=QTimer(self)
        self._midi_transport_timer.setInterval(180)
        self._midi_transport_timer.timeout.connect(self._sync_midi_transport)
        self._midi_transport_timer.start()
        self._sync_midi_transport()
        self.midi_actions=QPushButton("⋯",self)
        self.midi_actions.setFixedWidth(26)
        self.midi_actions.setToolTip("Selección múltiple: elegir todas, guardar o eliminar varios MIDI")
        self.midi_actions.setMenu(self._midi_selection_menu())
        right_buttons.addWidget(self.midi_actions,0)
        actions.addLayout(right_buttons,29)
        box.addLayout(actions)
        self.summary=QLabel("Selecciona un stem o marca varios para la cola secuencial.",self)
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(False)
        box.addWidget(self.summary)
        # Una tarea real NO tiene porcentaje por muestras: el motor comunica
        # fases, por lo que esta barra usa modo ocupado hasta terminar cada
        # pista. Nunca se muestran porcentajes inventados.
        progress_row=QHBoxLayout()
        progress_row.setSpacing(7)
        self.progress_label=QLabel("Sin conversión en curso",self)
        self.progress_label.setObjectName("midiProgressLabel")
        self.progress_label.setMinimumWidth(268)
        progress_row.addWidget(self.progress_label,0)
        self.progress=QProgressBar(self)
        self.progress.setObjectName("midiConversionProgress")
        self.progress.setMinimumHeight(18)
        self.progress.setMaximumHeight(20)
        self.progress.setTextVisible(False)
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        self.progress.setToolTip("Actividad real del motor. El contador muestra pistas completadas, no porcentajes estimados.")
        self.progress.setStyleSheet("""
            QProgressBar#midiConversionProgress {
                background:#031634;border:1px solid #248acf;
                border-radius:5px;
            }
            QProgressBar#midiConversionProgress::chunk {
                background:#20d9ed;border-radius:4px;
            }
        """)
        progress_row.addWidget(self.progress,1)
        # Mismo control visible en Inicio y al desacoplar la tarjeta:
        # cancela el motor REAL y la cola, no solo el indicador.
        self.cancel_operation_button=QPushButton("■ Cancelar",self)
        self.cancel_operation_button.setObjectName("cancelMidiHomeConversion")
        self.cancel_operation_button.setToolTip(
            "Detener la conversión en curso y las pistas pendientes. "
            "Los MIDI ya completados permanecen intactos.")
        self.cancel_operation_button.setMinimumWidth(88)
        self.cancel_operation_button.setMaximumWidth(110)
        self.cancel_operation_button.setEnabled(False)
        self.cancel_operation_button.clicked.connect(self.cancel_operation)
        progress_row.addWidget(self.cancel_operation_button,0)
        box.addLayout(progress_row)
        # Siempre a la vista: no desplazar los demás controles al iniciar.
        self._signature=None
        self._batch=[]
        self._batch_total=0
        self._batch_project=None
        self._batch_active=False
        self._cancel_requested=False
        self._batch_done=0
        self._external_job=False
        self._current_file=None
        self._progress_started=None
        self._progress_phase="En cola"
        self._progress_clock=QTimer(self)
        self._progress_clock.setInterval(750)
        self._progress_clock.timeout.connect(self._tick_progress)
        from midi_stem_listen import MidiStemListen
        self.listen=MidiStemListen(self)
        self.listen.statusChanged.connect(self.summary.setText)
        self.home.workbench.converter.progressEvent.connect(self._handle_progress_stage)

    def _tick_progress(self):
        if self._external_job and not self._batch_active:
            converter=self.home.workbench.converter
            if converter.process is None:
                self._external_job=False
                self._progress_clock.stop()
                self._update_cancel_control()
                successful=(not converter.cancelled and converter.output is not None
                            and converter.output.is_file())
                self._batch_done=1 if successful else 0
                self.refresh(force=True)
                self._finish_progress(successful,
                    "Conversión finalizada desde la pestaña Audio a MIDI."
                    if successful else
                    "Conversión de la pestaña cancelada o fallida.")
                return
        if (self._batch_active or self._external_job) and self._progress_started is not None:
            seconds=int(max(0,time.monotonic()-self._progress_started))
            elapsed=f"{seconds//60:02d}:{seconds%60:02d}"
            self.progress_label.setText(
                f"{self._batch_done}/{self._batch_total} · {elapsed} · {self._progress_phase}")

    def _show_progress(self,phase):
        self._progress_phase=phase
        self._tick_progress()
        self.progress_label.show()
        self.progress.show()
        total=max(1,self._batch_total)
        # Progreso REAL por pistas terminadas; durante la pista actual
        # se informa de la fase sin inventar un porcentaje ni oscilar.
        self.progress.setRange(0,total)
        self.progress.setValue(min(self._batch_done,total))
        self._update_cancel_control()
        if self._progress_started is None:
            self.progress_label.setText(f"{self._batch_done}/{total} · {phase}")
        self.progress_label.setToolTip(
            f"{self._batch_done} de {total} pistas realmente finalizadas.")

    def _handle_progress_stage(self,data):
        if not self._batch_active:
            converter=self.home.workbench.converter
            if converter.process is None:return
            if not self._external_job:
                self._external_job=True
                self._cancel_requested=False
                self._batch_total=1
                self._batch_done=0
                self._progress_started=time.monotonic()
                self._current_file=Path(converter.audio_path.text().strip())
                self._progress_clock.start()
        stage=data.get("stage")
        phases={
            "start":"Iniciando",
            "importing":"Decodificando audio",
            "separating":"Separando pistas",
            "separation_done":"Preparando MIDI",
            "tempo":"Analizando tempo",
            "loading_model":"Cargando IA",
            "processing":"Transcribiendo notas",
            "refinement":"Refinando notas",
            "effective_thresholds":"Aplicando parámetros",
            "track_done":"Guardando MIDI",
            "finished":"Verificando archivo",
            "chords":"Analizando acordes",
            "error":"Error del motor",
        }
        if stage in phases:
            self._show_progress(phases[stage])
            self.summary.setText(
                f"Convirtiendo {self._batch_done+1}/{self._batch_total}: "
                f"{self._current_file.name if self._current_file else ''} · "
                f"{phases[stage]}")

    def _finish_progress(self,success,message):
        self.progress_label.show()
        self.progress.show()
        self.progress.setRange(0,max(1,self._batch_total))
        self.progress.setValue(self._batch_done)
        self.progress_label.setText(
            f"{self._batch_done}/{max(1,self._batch_total)} "
            +("terminadas" if success else "completadas · detenida"))
        self.summary.setText(message)
        self._update_cancel_control()

    def _update_cancel_control(self):
        converter=self.home.workbench.converter
        busy=bool(self._batch_active or self._external_job or
                  converter.process is not None)
        self.cancel_operation_button.setEnabled(busy and not self._cancel_requested)
        self.cancel_operation_button.setVisible(True)

    def cancel_operation(self):
        """Detener la conversión real y todas las pistas aún en cola."""
        converter=self.home.workbench.converter
        if self._cancel_requested or not (self._batch_active or
                self._external_job or converter.process is not None):
            return
        self._cancel_requested=True
        self._batch.clear()
        self._show_progress("Cancelando motor y cola pendiente…")
        self.summary.setText(
            f"Cancelando conversión. {self._batch_done} MIDI completos conservados.")
        self._update_cancel_control()
        if converter.process is not None:
            # La transcripción y el análisis de acordes comparten este
            # cancelador, con terminate y kill de respaldo del motor real.
            converter.cancel_conversion()
            if converter.process.state()==QProcess.NotRunning:
                converter.cancelled=True
                if self._batch_active:self._abort("Cola MIDI cancelada.")
        elif self._batch_active:
            self._abort("Cola MIDI cancelada; sin nuevas conversiones.")
        else:
            self._external_job=False
            self._progress_clock.stop()
            self._finish_progress(False,"Operación MIDI cancelada.")

    def cancel_wave_previews(self):
        for inventory in (self.stems,self.drums):
            for i in range(inventory.count()):
                row=inventory.itemWidget(inventory.item(i))
                if isinstance(row,StemWaveRow):row.cleanup()

    def _project(self):
        p=getattr(self.home.main,"project_dir",None)
        return Path(p).resolve() if p else None

    def _audio_files(self):
        return self.home.workbench.converter.project_stem_paths()

    def _midi_files(self):
        home=self.home
        project=self._project()
        from task_staging import inside
        candidates=[Path(p) for p in home._gather_files()]
        store=home.workbench.midi_storage
        candidates.extend(Path(v["composite"]) for v in store.versions)
        candidates.extend(Path(p) for p in store.items)
        # Las carpetas MIDI del proyecto y las versiones temporales también
        # son visibles tras reiniciar, incluso si aún no se ha abierto la
        # pestaña de Resultados. No recorrer la biblioteca global.
        if project:
            for dirname in ("audio_a_midi","piano_roll","resultados","temporales/midi"):
                folder=project/dirname
                if not folder.is_dir() or folder.is_symlink():continue
                for item in folder.rglob("*"):
                    if not item.is_symlink() and item.is_file() and item.suffix.lower() in MIDI_EXT:
                        candidates.append(item)
        output={}
        for item in candidates:
            if (item.is_file() and item.suffix.lower() in MIDI_EXT
                    and not item.is_symlink()
                    and (project is None or inside(item,project))):
                output[str(item.resolve())]=item.resolve()
        return sorted(output.values(),key=lambda p:(p.name.casefold(),str(p)))

    def refresh(self,force=False):
        source=self.home.engine
        desired=[(source.itemText(i),source.itemData(i)) for i in range(source.count())]
        current=[(self.model.itemText(i),self.model.itemData(i)) for i in range(self.model.count())]
        if current!=desired:
            old=self.model.blockSignals(True)
            self.model.clear()
            for title,data in desired:self.model.addItem(title,data)
            self.model.blockSignals(old)
        if self.model.currentIndex()!=source.currentIndex() and not self.model.view().isVisible():
            old=self.model.blockSignals(True)
            self.model.setCurrentIndex(source.currentIndex())
            self.model.blockSignals(old)
        project=self._project()
        audio=self._audio_files()
        # Las voces secundarias deben quedar visibles en la parte superior
        # incluso cuando se añadan numerosos stems al proyecto.
        vocal_priority={"Voz limpia":0,"Coros":1,"Voz principal":2,
                        "Voz afinada":3,"Voz interpretada":4,
                        "Voz masculina":5,"Voz femenina":6}
        audio.sort(key=lambda p:(vocal_priority.get(self.home._stem_for(p),7),
                                 p.name.casefold(),str(p)))
        midi=self._midi_files()
        signature=(str(project),tuple(str(x) for x in audio),
                   tuple(str(x) for x in midi))
        if not force and signature==self._signature:
            self._update_controls()
            return
        old_project=self._signature[0] if self._signature else None
        chosen={str(widget.item(i).data(Qt.UserRole))
                for widget in (self.stems,self.drums)
                for i in range(widget.count())
                if widget.item(i).checkState()==Qt.Checked}
        selected_paths={}
        for widget in (self.stems,self.drums,self.midis):
            selected=widget.currentItem()
            selected_paths[widget]=selected.data(Qt.UserRole) if selected else None
        selected_midi_paths={str(item.data(Qt.UserRole))
                             for item in self.midis.selectedItems()}
        if str(project)!=old_project:
            chosen=set()
            self._batch=[];self._batch_active=False
            self._cancel_requested=False
        self._signature=signature
        inventories=(self.stems,self.drums)
        # Finalizar los analizadores que dejarán de ser visibles antes de
        # destruir los widgets: evita procesos FFmpeg huérfanos o warnings.
        for widget in inventories:
            widget.blockSignals(True)
            for index in range(widget.count()):
                row=widget.itemWidget(widget.item(index))
                if isinstance(row,StemWaveRow):row.cleanup()
            widget.clear()
        counts={}
        for path in audio:
            name=self.home._stem_for(path)
            counts[name]=counts.get(name,0)+1
            label=name if counts[name]==1 else f"{name} #{counts[name]}"
            widget=self.drums if name in DRUM_PARTS else self.stems
            item=QListWidgetItem(label)
            item.setData(Qt.UserRole,str(path))
            item.setToolTip(str(path))
            item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if str(path) in chosen else Qt.Unchecked)
            item.setSizeHint(QSize(0,22))
            widget.addItem(item)
            row=StemWaveRow(self,widget,item,path,label,widget is self.drums)
            widget.setItemWidget(item,row)
            if str(path)==selected_paths[widget]:widget.setCurrentItem(item)
        for widget in inventories:widget.blockSignals(False)
        old=self.midis.blockSignals(True)
        self.midis.clear()
        occurrences={}
        for file in midi:occurrences[file.name]=occurrences.get(file.name,0)+1
        seen={}
        for file in midi:
            seen[file.name]=seen.get(file.name,0)+1
            label=file.name if occurrences[file.name]==1 else (
                f"{file.name} · {seen[file.name]}/{occurrences[file.name]}")
            item=QListWidgetItem(label)
            item.setData(Qt.UserRole,str(file))
            item.setToolTip(str(file))
            self.midis.addItem(item)
            if str(file)==selected_paths[self.midis]:
                self.midis.setCurrentItem(item,QItemSelectionModel.NoUpdate)
            if str(file) in selected_midi_paths:
                item.setSelected(True)
        self.midis.blockSignals(old)
        self._selected_midi_changed()
        self.stem_title.setText(f"STEMS SEPARADOS · {self.stems.count()}")
        self.drum_title.setText(f"BATERÍA DESGLOSADA · {self.drums.count()}")
        self.midi_title.setText(f"MIDI GENERADOS · {self.midis.count()}")
        self.listen.sync()
        self._update_controls()

    def _on_item_changed(self,item):
        self._update_controls()
        self.listen.selected_changed()

    def _update_controls(self):
        for widget in (self.stems,self.drums):
            for idx in range(widget.count()):
                item=widget.item(idx)
                row=widget.itemWidget(item)
                if isinstance(row,StemWaveRow):row.sync_check()
        converter=self.home.workbench.converter
        processing=(self._batch_active or converter.process is not None
                    or getattr(converter,"_home_queue_busy",False))
        available=self.stems.count()+self.drums.count()
        self.convert.setEnabled(not processing and bool(self.checked()))
        self.mark_all.setEnabled(not processing and available>0)
        self.clear_all.setEnabled(not processing and available>0)
        self.load_model.setEnabled(not processing)
        self.piano.setEnabled(self.midis.count()>0)
        self.results.setEnabled(self.midis.count()>0)
        self.preview.setEnabled(available>0)
        self._update_cancel_control()
        if not self._batch_active:
            count=len(self.checked())
            if self.listen.live.running:
                self.summary.setText(f"Escuchando {count} pistas · "
                                     "marca o desmarca para silenciar en directo.")
            else:
                self.summary.setText(
                    f"{self.stems.count()} stems · {self.drums.count()} piezas de batería · "
                    f"{self.midis.count()} MIDI · {count} marcados.")

    def set_all(self,checked):
        for widget in (self.stems,self.drums):
            old=widget.blockSignals(True)
            for i in range(widget.count()):
                widget.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)
            widget.blockSignals(old)
        self._update_controls()
        self.listen.selected_changed()

    def checked(self):
        return [Path(widget.item(i).data(Qt.UserRole))
                for widget in (self.stems,self.drums)
                for i in range(widget.count())
                if widget.item(i).checkState()==Qt.Checked]

    def _select_audio(self,item,other):
        # Preview solo del inventario que el usuario ha seleccionado.
        other.clearSelection()

    def choose_stem(self,item):
        file=Path(item.data(Qt.UserRole))
        if self.home.workbench.converter.choose_project_stem(file):
            self.home._sync_midi_stems(force=True)
            self.summary.setText("Pista preparada: "+file.name)

    def preview_stem(self):
        if not self.checked():
            widget=self.drums if self.drums.selectedItems() else self.stems
            item=widget.currentItem()
            if item is None:
                widget=self.stems if widget is self.drums else self.drums
                item=widget.currentItem()
            if item is None:
                self.summary.setText("Marca las pistas que quieras escuchar.")
                return
            item.setCheckState(Qt.Checked)
        self.listen.play()

    def select_model(self,index):
        if index<0:return
        h=self.home
        if self.model.itemData(index)!=h.engine.currentData():
            h.engine.setCurrentIndex(index)

    def convert_checked(self):
        if (self._batch_active or self._external_job or
                self.home.workbench.converter.process is not None):return
        project=self._project()
        if project is None:
            self.summary.setText("Abre o crea un proyecto antes de convertir.")
            return
        from task_staging import inside
        available={p.resolve() for p in self._audio_files()}
        files=[p.resolve() for p in self.checked()]
        if not files:return
        if any(not p.is_file() or not inside(p,project) or p not in available for p in files):
            self.summary.setText("Hay pistas fuera del proyecto. Actualiza la lista.")
            self.refresh(force=True)
            return
        self._batch=files
        self._batch_total=len(files)
        self._batch_done=0
        self._batch_project=project
        self._batch_active=True
        self._cancel_requested=False
        self._progress_started=time.monotonic()
        self._progress_clock.start()
        converter=self.home.workbench.converter
        converter._home_queue_busy=True
        converter.go.setEnabled(False)
        self.home.midi_run.setEnabled(False)
        self._show_progress("En cola")
        self._update_controls()
        self._next()

    def _next(self):
        if not self._batch_active:return
        if self._cancel_requested:
            self._abort("Cola MIDI cancelada; los MIDI terminados siguen disponibles.")
            return
        if self._project()!=self._batch_project:
            self._abort("El proyecto ha cambiado: cola detenida.")
            return
        # Si está habilitado el análisis de acordes, AudioMidiDialog
        # ejecuta otro proceso después de cada MIDI; esperar a que termine
        # sin solapar motores ni perder el stem siguiente.
        converter=self.home.workbench.converter
        if converter.process is not None:
            if converter.cancelled:
                self._abort("Tarea cancelada; se conservan los MIDI anteriores.")
            else:
                QTimer.singleShot(250,self._next)
            return
        if not self._batch:
            self._batch_active=False
            self._progress_clock.stop()
            converter._home_queue_busy=False
            converter.go.setEnabled(converter.process is None and converter.tempo_job is None)
            self.home.midi_run.setEnabled(True)
            self.refresh(force=True)
            self._finish_progress(True,f"{self._batch_done} conversiones terminadas · "
                                 f"{self.midis.count()} MIDI visibles.")
            return
        file=self._batch.pop(0)
        self._current_file=file
        self._show_progress("Preparando")
        converter=self.home.workbench.converter
        if not file.is_file() or not converter.choose_project_stem(file):
            self._abort("No se puede usar el stem "+file.name)
            return
        converter.use_folder.setChecked(False)
        converter.auto_separate.setChecked(False)
        self.summary.setText(f"Convirtiendo {self._batch_done+1}/{self._batch_total}: "
                             +file.name)
        converter.start_conversion(from_home_queue=True)
        proc=converter.process
        if proc is None:
            self._abort("No ha arrancado el motor MIDI. Revisa el aviso de error.")
            return
        # Al terminar el QProcess, AudioMidiDialog guarda primero la salida
        # mediante on_conversion_finished. La siguiente tarea no se solapa.
        proc.finished.connect(lambda code,status,run=proc:
            QTimer.singleShot(150,lambda:self._finished(code,status,run)))

    def _finished(self,code,status,proc):
        if not self._batch_active:return
        if self._cancel_requested:
            self._abort("Conversión cancelada. Los MIDI anteriores se conservan.")
            return
        converter=self.home.workbench.converter
        if converter.process is not None and converter.process is not proc:
            # La transcripción terminó, pero sigue el análisis de acordes.
            # No contar la pista como terminada hasta concluir esa fase.
            self._show_progress("Analizando acordes")
            QTimer.singleShot(150,lambda:self._finished(code,status,proc))
            return
        if (converter.cancelled or code!=0 or
                converter.output is None or not converter.output.is_file()):
            self._abort("Conversión cancelada o fallida. Los MIDI anteriores se conservan.")
            return
        self._batch_done+=1
        self.progress.setRange(0,max(1,self._batch_total))
        self.progress.setValue(self._batch_done)
        self.progress_label.setText(f"{self._batch_done}/{self._batch_total} completadas")
        self.home.refresh(force=True)
        self.refresh(force=True)
        QTimer.singleShot(0,self._next)

    def _abort(self,message):
        self._batch_active=False
        self._progress_clock.stop()
        self._batch=[]
        self._batch_project=None
        converter=self.home.workbench.converter
        converter._home_queue_busy=False
        converter.go.setEnabled(converter.process is None and converter.tempo_job is None)
        self.home.midi_run.setEnabled(True)
        self._update_controls()
        self._finish_progress(False,message)

    def selected_midi_paths(self):
        """Todas las filas MIDI seleccionadas, únicas y en orden visual."""
        return list(dict.fromkeys(Path(item.data(Qt.UserRole))
                for item in (self.midis.item(i) for i in range(self.midis.count()))
                if item.isSelected() and Path(item.data(Qt.UserRole)).is_file()))

    def _selected_midi_changed(self):
        count=len(self.midis.selectedItems())
        self.midi_title.setText(
            f"MIDI GENERADOS · {self.midis.count()}"
            + (f" · {count} seleccionados" if count>1 else ""))
        if hasattr(self,"midi_actions"):
            self.midi_actions.setEnabled(self.midis.count()>0)
        if hasattr(self,"midi_play"):
            self._sync_midi_transport()

    def _global_midi_transport(self):
        return getattr(self.home.main,"studio_midi_transport",None)

    def _sync_midi_transport(self):
        """Estado real del motor, también al reproducir desde Resultados."""
        if not hasattr(self,"midi_play"):return
        transport=self._global_midi_transport()
        has_file=self.midis.count()>0
        self.midi_play.setEnabled(has_file)
        playing=False
        paused=False
        busy=False
        if transport is not None:
            player=transport._current_midi_preview()
            playing=player._play_process is not None or player._qt_active
            paused=bool(playing and player._paused)
            busy=player._render is not None
        self.midi_pause.setEnabled(playing)
        self.midi_stop.setEnabled(playing or busy)
        self.midi_pause.setText("▶" if paused else "Ⅱ")
        self.midi_pause.setToolTip(
            "Reanudar el MIDI pausado" if paused else
            "Pausar la reproducción MIDI actual")
        self.midi_play.setToolTip(
            "Escuchar el MIDI seleccionado sin abrir Piano Roll.")
        self.midi_stop.setToolTip(
            "Cancelar preparación y detener el MIDI actual")

    def pause_selected_midi(self):
        transport=self._global_midi_transport()
        if transport is None:return False
        player=transport._current_midi_preview()
        if player._play_process is None and not player._qt_active:return False
        transport.toggle_pause()
        self._sync_midi_transport()
        return True

    def stop_selected_midi(self):
        transport=self._global_midi_transport()
        if transport is None:return False
        player=transport._current_midi_preview()
        if (player._play_process is None and not player._qt_active
                and player._render is None):
            return False
        transport.stop()
        self._sync_midi_transport()
        self.summary.setText("Reproducción MIDI detenida.")
        return True

    def play_selected_midi(self):
        selected=self.selected_midi_paths()
        if not selected and self.midis.currentItem() is not None:
            selected=[Path(self.midis.currentItem().data(Qt.UserRole))]
        if not selected:
            self.summary.setText("Selecciona un archivo MIDI generado.")
            return False
        main=self.home.main
        player=getattr(main,"studio_midi_transport",None)
        if player is None:return False
        if player.select_file(selected[0],play=True):
            self.summary.setText("Escuchando MIDI: "+selected[0].name)
            return True
        self.summary.setText("No se pudo reproducir el MIDI seleccionado.")
        return False

    def _select_all_midis(self):
        self.midis.selectAll()
        self._selected_midi_changed()

    def _midi_selection_menu(self):
        menu=QMenu(self)
        menu.addAction("Seleccionar todos · Ctrl+A",self._select_all_midis)
        menu.addAction("Quitar selección",self.midis.clearSelection)
        menu.addSeparator()
        menu.addAction("Guardar MIDI seleccionados…",self._save_selected_midis)
        menu.addAction("Eliminar MIDI seleccionados…",self._delete_selected_midis)
        return menu

    def _save_selected_midis(self,files=None):
        if files is None:files=self.selected_midi_paths()
        if files:
            return self.home._save_results(files)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self,"Selección vacía","Selecciona uno o varios MIDI.")
        return []

    def _delete_selected_midis(self,files=None):
        if files is None:files=self.selected_midi_paths()
        files=list(dict.fromkeys(Path(p) for p in files))
        if not files:return False
        converter=self.home.workbench.converter
        if self._batch_active or converter.process is not None:return False
        from safe_file_delete import trash_files
        self.listen.stop()
        if not trash_files(self,files):return False
        self._signature=None
        self.home.refresh(force=True)
        self.refresh(force=True)
        return True

    def _context_file(self,inventory,position):
        item=inventory.itemAt(position)
        if item is None:return
        if inventory is self.midis:
            current={Path(x.data(Qt.UserRole)) for x in inventory.selectedItems()}
            path=Path(item.data(Qt.UserRole))
            # Clic derecho sobre una fila seleccionada respeta todo el grupo.
            files=self.selected_midi_paths() if path in current else [path]
            menu=QMenu(self)
            choose=menu.addAction("Seleccionar todos · Ctrl+A")
            clear=menu.addAction("Quitar selección")
            menu.addSeparator()
            listen=menu.addAction("▶ Reproducir MIDI seleccionado")
            save=menu.addAction(f"Guardar {len(files)} MIDI seleccionados…")
            delete=menu.addAction(f"Eliminar {len(files)} MIDI seleccionados…")
            busy=self._batch_active or self.home.workbench.converter.process is not None
            delete.setEnabled(not busy)
            chosen=menu.exec(inventory.viewport().mapToGlobal(position))
            if chosen is choose:self._select_all_midis()
            elif chosen is clear:inventory.clearSelection()
            elif chosen is listen and files:
                transport=getattr(self.home.main,"studio_midi_transport",None)
                if transport is not None:transport.select_file(files[0],play=True)
            elif chosen is save:self._save_selected_midis(files)
            elif chosen is delete:self._delete_selected_midis(files)
            return
        # Los stems se marcan con sus casillas para convertir y escuchar,
        # independientemente de la selección de archivos para eliminarlos.
        path=Path(item.data(Qt.UserRole))
        menu=QMenu(self)
        delete=menu.addAction("Eliminar archivo… · pendiente hasta Guardar")
        converter=self.home.workbench.converter
        delete.setEnabled(not (self._batch_active or converter.process is not None))
        if menu.exec(inventory.viewport().mapToGlobal(position)) is not delete:return
        from safe_file_delete import trash_files
        self.listen.stop()
        if trash_files(self,[path]):
            self._signature=None
            self.home.refresh(force=True)
            self.refresh(force=True)

    def open_midi(self,item=None):
        if item is None:item=self.midis.currentItem()
        if item is None:return
        file=Path(item.data(Qt.UserRole))
        if not file.is_file():return
        h=self.home
        h.refresh(force=True)
        index=h.midi_choice.findData(str(file))
        if index>=0:
            h.midi_choice.setCurrentIndex(index)
            h.choose_midi(index)
        else:
            h.selected_midi=file
            h.piano_preview.set_midi(file)
        self.summary.setText("Piano Roll: "+file.name)
        manager=getattr(h,"_floating_manager",None)
        if manager is not None:
            if not manager.is_detached(h.piano_card):manager.detach(h.piano_card)
            manager.bring_forward(h.piano_card)

    def show_results(self):
        home=self.home
        home.refresh(force=True)
        home._update_results(home._gather_files())
        selected=self.selected_midi_paths()
        if not selected and self.midis.currentItem() is not None:
            selected=[Path(self.midis.currentItem().data(Qt.UserRole))]
        paths={str(path.resolve()) for path in selected}
        if paths:
            home._result_tab(0)
            selection=home.files.selectionModel()
            home.files.clearSelection()
            for row in range(home.files.rowCount()):
                item=home.files.item(row,0)
                if item and item.data(Qt.UserRole) in paths:
                    selection.select(home.files.model().index(row,0),
                                     QItemSelectionModel.Select|QItemSelectionModel.Rows)
        manager=getattr(home,"_floating_manager",None)
        if manager is not None:
            if not manager.is_detached(home.result_card):manager.detach(home.result_card)
            manager.bring_forward(home.result_card)
        self.summary.setText("Resultados: archivos MIDI del proyecto visibles.")
