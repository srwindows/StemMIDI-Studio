"""Controles reales del separador: peticiones, progreso, edición y selección."""
from __future__ import annotations
import math
import re
import shutil
from pathlib import Path
from PySide6.QtCore import Qt,QProcess,QTimer
from PySide6.QtWidgets import (
 QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,
 QGroupBox,QHBoxLayout,QLabel,QMessageBox,QPlainTextEdit,QProgressBar,
 QPushButton,QSlider,QSpinBox,QVBoxLayout,QWidget
)

NAMES={"vocals":"Voz","drums":"Batería","bass":"Bajo","guitar":"Guitarra",
       "piano":"Piano","other":"Otros","instrumental":"Instrumental",
       "canal_izquierdo":"Izquierdo","canal_derecho":"Derecho"}
SPANISH={"Voz":"Vocals","Batería":"Drums","Bajo":"Bass","Guitarra":"Guitar",
         "Piano":"Piano","Otros":"Other","Instrumental":"Instrumental",
         "Izquierdo":"Canal_Izquierdo","Derecho":"Canal_Derecho"}
LABELS=("Voz","Batería","Bajo","Guitarra","Piano","Otros","Instrumental","Izquierdo","Derecho")
TONES=("Do","Do♯","Re","Re♯","Mi","Fa","Fa♯","Sol","Sol♯","La","La♯","Si")

def stems_for_model(model):
    if model is None:return ("Izquierdo","Derecho")
    from model_registry import record_for
    record=record_for(model)
    if record is not None and record.get("stems"):
        available={NAMES[k] for k in record["stems"] if k in NAMES}
        matches=tuple(name for name in LABELS if name in available)
        if matches:return matches
    if "6s" in model:return ("Voz","Batería","Bajo","Guitarra","Piano","Otros")
    if model.startswith(("htdemucs","demucs")):return ("Voz","Batería","Bajo","Otros")
    return ("Voz","Instrumental")  # dos stems; los modelos externos varían

def instrument_for(path):
    name=Path(path).stem.casefold()
    tokens=set(re.findall(r"[a-záéíóúñ]+",name))
    if "canal" in tokens:
        if "izquierdo" in tokens:return "Izquierdo"
        if "derecho" in tokens:return "Derecho"
    for key in ("vocals","drums","bass","guitar","piano","instrumental","other"):
        if key in tokens:return NAMES[key]
    return None

def setup_request_controls(sep,entry):
    bar=QWidget(entry)
    layout=QVBoxLayout(bar);layout.setContentsMargins(4,2,4,2);layout.setSpacing(2)
    first=QHBoxLayout();first.setSpacing(7)
    second=QHBoxLayout();second.setSpacing(7)
    first.addWidget(QLabel("EXTRAER"))
    sep.stem_all=QCheckBox("Todos")
    first.addWidget(sep.stem_all)
    sep.stem_checks={}
    for i,stem in enumerate(LABELS):
        check=QCheckBox(stem)
        check.setToolTip("Solicitar únicamente este resultado. El modelo puede calcular internamente las otras fuentes.")
        (first if i<4 else second).addWidget(check)
        sep.stem_checks[stem]=check
    first.addStretch()
    second.addStretch()
    layout.addLayout(first);layout.addLayout(second)
    entry.body.addWidget(bar)
    desc=QLabel("Marca qué pistas quieres conservar; para guitarra o piano separados utiliza un modelo de 6 pistas.")
    desc.setObjectName("muted");desc.setWordWrap(False)
    entry.body.addWidget(desc)
    sep.stem_note=desc
    sep.norm_setting=getattr(sep,"norm_setting",0.9)
    sep.amp_setting=getattr(sep,"amp_setting",0.0)
    sep.sample_setting=getattr(sep,"sample_setting",48000)
    opts=QPushButton("Parámetros IA…",entry)
    opts.setToolTip("Pico de normalización, amplificación mínima, frecuencia de salida y perfil de calidad.")
    opts.clicked.connect(lambda:parameters_dialog(sep))
    sep.stem_parameters_btn=opts
    second.insertWidget(second.count()-1,opts)
    def update_all(on):
        if sep._sync_selection:return
        sep._sync_selection=True
        for box in sep.stem_checks.values():
            if box.isEnabled():box.setChecked(on)
        sep._sync_selection=False
    def update_one(_=None):
        if sep._sync_selection:return
        sep._sync_selection=True
        enabled=[box for box in sep.stem_checks.values() if box.isEnabled()]
        sep.stem_all.setChecked(bool(enabled) and all(x.isChecked() for x in enabled))
        sep._sync_selection=False
    sep._sync_selection=False
    sep.stem_all.toggled.connect(update_all)
    for box in sep.stem_checks.values():box.toggled.connect(update_one)
    sep.refresh_stem_choices=lambda:refresh_choices(sep)
    sep.requested_stems=lambda:[key for key,cb in sep.stem_checks.items() if cb.isEnabled() and cb.isChecked()]
    sep.profile.currentIndexChanged.connect(sep.refresh_stem_choices)
    refresh_choices(sep)
    return bar

def refresh_choices(sep):
    from separador import MODELS
    supported=stems_for_model(MODELS.get(sep.profile.currentText()))
    sep._sync_selection=True
    for key,cb in sep.stem_checks.items():
        cb.setEnabled(key in supported)
        cb.setChecked(key in supported)
        cb.setVisible(key in supported)
    sep.stem_all.setChecked(True)
    sep._sync_selection=False
    sep.stem_note.setText("Disponibles: "+", ".join(supported)+
       ". Selecciona antes de separar. Algunos modelos calculan todas las fuentes internamente.")

def parameters_dialog(sep):
    dialog=QDialog(sep);dialog.setWindowTitle("Parámetros de separación IA")
    v=QVBoxLayout(dialog);form=QFormLayout()
    norm=QDoubleSpinBox();norm.setRange(.1,1);norm.setDecimals(2);norm.setSingleStep(.05)
    norm.setValue(sep.norm_setting);norm.setToolTip("Pico máximo (lineal), 0,90 recomendado. No mide ruido ni garantiza ausencia de artefactos.")
    gain=QDoubleSpinBox();gain.setRange(0,1);gain.setDecimals(2);gain.setSingleStep(.05)
    gain.setValue(sep.amp_setting);gain.setToolTip("Amplitud mínima; 0,00 desactiva esta corrección.")
    rate=QComboBox();rate.addItems(("44100","48000"));rate.setCurrentText(str(sep.sample_setting))
    def slider_field(spin):
        row=QWidget(dialog)
        lay=QHBoxLayout(row)
        lay.setContentsMargins(0,0,0,0)
        slider=QSlider(Qt.Horizontal)
        slider.setRange(round(spin.minimum()*100),round(spin.maximum()*100))
        slider.setValue(round(spin.value()*100))
        slider.setMinimumWidth(190)
        slider.valueChanged.connect(lambda value:spin.setValue(value/100))
        spin.valueChanged.connect(lambda value:slider.setValue(round(value*100)))
        lay.addWidget(slider,1)
        lay.addWidget(spin)
        row.slider=slider
        return row
    form.addRow("Normalizar pico (0,10–1,00)",slider_field(norm))
    form.addRow("Amplificación mínima (0,00–1,00)",slider_field(gain))
    form.addRow("Frecuencia de salida",rate)
    v.addLayout(form)
    hint=QLabel("El ajuste de calidad del panel principal regula pasadas y solapamiento del modelo. "
       "No existe un control universal para aislar instrumentos sin artefactos.")
    hint.setWordWrap(True);v.addWidget(hint)
    buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);v.addWidget(buttons)
    if dialog.exec()==QDialog.Accepted:
        sep.norm_setting=norm.value();sep.amp_setting=gain.value();sep.sample_setting=int(rate.currentText())
        sep.save_preferences()

def filter_requested_outputs(sep):
    """Excluir únicamente salidas temporales reconocidas y ajenas a la solicitud."""
    if not getattr(sep,"active_request",None) or not sep.current_folder:return
    wanted=set(sep.active_request)
    for p in list(sep.current_folder.iterdir()):
        if not p.is_file() or p.suffix.lower() not in (".wav",".flac",".mp3",".ogg",".opus",".m4a"):
            continue
        stem=instrument_for(p)
        if stem and stem not in wanted:
            p.unlink()
            sep.append_log("Resultado no solicitado eliminado del temporal: "+p.name)
        elif stem is None:
            # No clasificar a ciegas; impedir que se apruebe un archivo desconocido.
            sep.append_log("Salida no reconocida; revisar antes de aprobar: "+p.name)

def extract_engine_percent(text):
    """Solo porcentajes explícitos de tqdm (p.ej. 85%|...|52/62).

    No interpretar cifras de tiempos, muestras, normalización o nombres.
    La salida de QProcess puede llegar dividida en fragmentos arbitrarios.
    """
    found=re.findall(r"(?<![\d.])(?<![\d])([0-9]{1,3})\s*%\s*\|",str(text))
    return [int(p) for p in found if 0<=int(p)<=100]


class MotorDialog(QDialog):
    """Lectura fiel del progreso comunicado y de los stems generados.

    Nunca usar barras de rango (0,0): Qt anima ese rango en bucle.
    El modelo puede repetir tqdm por pasadas; su máximo comprobado se
    mantiene visible, sin retroceder ni inventar porcentajes posteriores.
    """
    def __init__(self,sep):
        super().__init__(sep)
        self.sep=sep
        self.setWindowTitle("Separación · actividad y progreso del motor")
        self.resize(690,550)
        self.reported_engine=0
        self.general_percent=0
        self.engine_started=False
        self._last_progress_chunk=""
        self._last_stage=""
        root=QVBoxLayout(self)
        self.stage=QLabel("Preparando el motor…");root.addWidget(self.stage)
        root.addWidget(QLabel("Progreso general · porcentaje comunicado por el motor"))
        self.total=QProgressBar()
        self.total.setRange(0,100)
        self.total.setValue(0)
        self.total.setFormat("%p%")
        root.addWidget(self.total)
        self.rows={}
        for stem in getattr(sep,"active_request",[]):
            row=QHBoxLayout()
            lab=QLabel(stem);lab.setMinimumWidth(120);row.addWidget(lab)
            bar=QProgressBar()
            bar.setRange(0,100);bar.setValue(0)
            bar.setFormat("%p%")
            bar.setToolTip(
                stem+": durante el cálculo sigue el progreso COMÚN de IA; "
                "100 % solamente al comprobar el archivo de este instrumento")
            row.addWidget(bar,1)
            self.rows[stem]=bar
            root.addLayout(row)
        root.addWidget(QLabel("ACTIVIDAD DEL MOTOR · operaciones y mensajes reales"))
        self.technical=QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setMaximumBlockCount(2000)
        root.addWidget(self.technical,1)
        info=QLabel("Las barras avanzan con los porcentajes reales de cálculo "
                    "comunicados por el motor. En el cálculo de IA todas las "
                    "pistas comparten esa fase; el 100 % individual solo se "
                    "marca al comprobar el archivo. Si no hay porcentaje "
                    "verificable, permanecen en el último valor confirmado.")
        info.setWordWrap(True)
        root.addWidget(info)
        close=QPushButton("Ocultar ventana (seguir procesando)")
        close.clicked.connect(self.hide);root.addWidget(close)
        self.refresh_log()

    def refresh_log(self):
        self.technical.setPlainText(self.sep.log.toPlainText())
        self.technical.verticalScrollBar().setValue(
            self.technical.verticalScrollBar().maximum())

    def add_log(self):
        self.refresh_log()

    def stage_update(self,text):
        self._last_stage=str(text)
        self.stage.setText(self._last_stage)

    def start_job(self,command):
        """Una operación nueva no borra el progreso ya confirmado."""
        self.engine_started=bool(command and command[0]!="ffmpeg")
        self._last_progress_chunk=""
        self._last_stage=""
        self.stage.setText("Calculando separación IA…" if self.engine_started
                           else "Preparando o escribiendo audio…")

    def _set_general(self,value):
        self.general_percent=max(self.general_percent,
                                 min(100,max(0,int(value))))
        self.total.setValue(self.general_percent)
        # También actualizar la barra principal de separación, no dejarla
        # en modo marquesina mientras el inspector muestra % exactos.
        if hasattr(self.sep,"progress"):
            self.sep.progress.setRange(0,100)
            self.sep.progress.setValue(self.general_percent)

    def _set_stems(self,common_percent):
        # La IA separa todos los stems en un único cálculo, sin telemetría
        # de computación independiente por fuente.
        for name,bar in self.rows.items():
            if bar.value()<100:
                bar.setValue(max(bar.value(), min(99,common_percent)))

    def receive_output(self,text):
        if not self.engine_started:return
        combined=(self._last_progress_chunk+str(text))
        self._last_progress_chunk=combined[-160:]
        percents=extract_engine_percent(combined)
        if not percents:return
        reported=max(percents)
        self.reported_engine=max(self.reported_engine,reported)
        # 100% del cálculo NO implica haber terminado de escribir los
        # archivos: queda al 99% hasta que se validen las salidas.
        actual=min(99,self.reported_engine)
        self._set_general(actual)
        self._set_stems(actual)
        self.stage.setText(
            f"Motor IA: {self.reported_engine}% calculado"
            +(" · guardando archivos…" if reported==100 else ""))

    def set_ready(self,paths):
        present={instrument_for(p) for p in paths
                 if Path(p).is_file() and Path(p).stat().st_size>0}
        for name,bar in self.rows.items():
            if name in present:
                bar.setValue(100)
        if self.rows:
            # Incluso con los archivos presentes, el proceso aún puede fallar.
            # El global llega a 100 solo tras finalización exitosa verificada.
            self._set_general(min(99,self.reported_engine))
        return present

    def completed(self,success):
        present=self.set_ready(getattr(self.sep,"latest_outputs",[]))
        all_ready=(bool(self.rows) and
                   all(name in present for name in self.rows))
        if success and all_ready:
            self._set_general(100)
            self.stage.setText(
                f"Finalizado · {len(self.rows)} pistas generadas y verificadas")
        elif success:
            self.stage.setText(
                f"Motor finalizado · {len(present.intersection(self.rows))}/"
                f"{len(self.rows)} pistas confirmadas; revisa el registro")
        else:
            self.stage.setText("Cancelado o error · revisa el registro")
        # Nunca convertir fallo/cancelación en 100% ni borrar los
        # porcentajes que el motor ya había comunicado.

    def closeEvent(self,event):
        # El inspector no cancela el proceso externo al ocultarse.
        self.hide()
        event.ignore()

def start_monitor(sep):
    if getattr(sep,"motor_dialog",None) is not None:
        sep.motor_dialog.close()
    sep.motor_dialog=MotorDialog(sep)
    sep.motor_dialog.show()
    sep.motor_dialog.raise_()

def instrument_progress(sep):
    dlg=getattr(sep,"motor_dialog",None)
    if dlg is not None:
        dlg.set_ready(sep.latest_outputs)
        dlg.refresh_log()

def finish_monitor(sep,success):
    dlg=getattr(sep,"motor_dialog",None)
    if dlg is not None:
        dlg.set_ready(sep.latest_outputs);dlg.completed(success);dlg.refresh_log()

def setup_results_controls(main):
    panel=main.workbench.sep_results
    controls=QHBoxLayout()
    all_btn=QPushButton("Marcar todas")
    none_btn=QPushButton("Desmarcar")
    remove_btn=QPushButton("Eliminar marcadas")
    remove_btn.setObjectName("stop")
    tone_btn=QPushButton("Cambiar tonalidad…")
    all_btn.clicked.connect(lambda:[line.checked.setChecked(True) for line in panel.lines])
    none_btn.clicked.connect(lambda:[line.checked.setChecked(False) for line in panel.lines])
    remove_btn.clicked.connect(lambda:remove_selected(main))
    tone_btn.clicked.connect(lambda:pitch_dialog(main))
    for btn in (all_btn,none_btn,remove_btn,tone_btn):controls.addWidget(btn)
    controls.addStretch()
    panel.layout().insertLayout(panel.layout().count()-2,controls)
    panel.mark_all_btn=all_btn;panel.mark_none_btn=none_btn
    panel.remove_selected_btn=remove_btn;panel.pitch_btn=tone_btn
    panel.status.setToolTip("Las casillas gobiernan guardado, aprobación y transferencias.")

def checked_paths(main):
    panel=main.workbench.sep_results
    return [panel.storage.items[i] for i in panel.selected_indices()
            if i<len(panel.storage.items) and Path(panel.storage.items[i]).is_file()]

def remove_selected(main):
    sep=main.workbench.separator
    panel=main.workbench.sep_results
    store=panel.storage
    converter=main.workbench.converter
    if sep.busy or (converter.process is not None and
                    converter.process.state()!=QProcess.NotRunning):
        QMessageBox.information(panel,"Pistas en uso",
                                "Finaliza primero la separación o la conversión MIDI.")
        return
    paths=checked_paths(main)
    if not paths:
        QMessageBox.information(panel,"Nada seleccionado","Marca las pistas que quieres eliminar.");return
    if not store.folder:return
    from task_staging import inside
    if any(not inside(p,store.folder) for p in paths):
        QMessageBox.warning(panel,"Origen protegido","Solo se pueden eliminar archivos de la tarea temporal.");return
    answer=QMessageBox.question(panel,"Eliminar stems temporales",
        f"¿Eliminar {len(paths)} pistas marcadas?\nNo se borrarán originales ni exportaciones guardadas.",
        QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
    if answer!=QMessageBox.Yes:return
    panel.preview.stop();sep.result_preview.stop()
    selected={Path(p).resolve() for p in paths}
    for p in selected:p.unlink()
    store.items=[p for p in store.items if Path(p).resolve() not in selected]
    store.saved.difference_update({str(p) for p in selected})
    store.manifest()
    sep.refresh_outputs();panel.populate()
    from project_flow import approved_map,approved_path,atomic_json
    mapping=approved_map(main)
    if mapping:
        mapping={name:p for name,p in mapping.items() if Path(p).resolve() not in selected}
        atomic_json(approved_path(main),{"task":str(store.folder.resolve()),"stems":mapping})
    panel.status.setText(f"Eliminadas {len(selected)} pistas temporales. Originales intactos.")
    main.workbench.converter.refresh_project_stems()

def pitch_dialog(main):
    panel=main.workbench.sep_results
    if main.workbench.separator.busy:
        QMessageBox.information(panel,"Separación activa",
                                "Espera a que termine el motor antes de transponer.")
        return
    selections=checked_paths(main)
    if len(selections)!=1:
        QMessageBox.information(panel,"Cambio de tonalidad","Marca exactamente una pista para transponer.");return
    source=Path(selections[0])
    dialog=QDialog(panel);dialog.setWindowTitle("Transponer stem · conservar duración")
    v=QVBoxLayout(dialog)
    heading=QLabel(source.name);heading.setWordWrap(True);v.addWidget(heading)
    form=QFormLayout()
    original=QComboBox();original.addItems(TONES)
    target=QComboBox();target.addItems(TONES);target.setCurrentText("Re")
    semitones=QSpinBox();semitones.setRange(-12,12);semitones.setValue(2)
    info=QLabel("Indica la tonalidad original: no se detecta automáticamente. "
                "El motor cambia el tono y mantiene aproximadamente el tempo.")
    info.setWordWrap(True);v.addWidget(info)
    def recalc():
        value=(target.currentIndex()-original.currentIndex())%12
        if value>6:value-=12
        semitones.setValue(value)
    original.currentIndexChanged.connect(recalc);target.currentIndexChanged.connect(recalc)
    form.addRow("Tonalidad actual (declarada)",original)
    form.addRow("Tonalidad de destino",target)
    form.addRow("Desplazamiento en semitonos",semitones)
    v.addLayout(form)
    buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);v.addWidget(buttons)
    if dialog.exec()!=QDialog.Accepted:return
    shift=semitones.value()
    if shift==0:return
    from task_staging import unique_dest,inside
    store=panel.storage
    if not store.folder or not inside(source,store.folder):
        QMessageBox.warning(panel,"Archivo no temporal","Solo se puede transponer una pista de la tarea.");return
    dest=unique_dest(source.parent,source.stem+f"_tono_{shift:+d}st"+source.suffix)
    codec=({"wav":["-c:a","pcm_s24le"],"flac":["-c:a","flac"],"mp3":["-c:a","libmp3lame","-q:a","2"]}.get(source.suffix.lower().lstrip("."),["-c:a","flac"]))
    if source.suffix.lower() not in (".wav",".flac",".mp3"):
        dest=unique_dest(source.parent,source.stem+f"_tono_{shift:+d}st.flac")
        codec=["-c:a","flac"]
    operation=QDialog(panel);operation.setWindowTitle("Transposición en curso");operation.resize(460,160)
    op_layout=QVBoxLayout(operation);op_layout.addWidget(QLabel(f"{source.name}\n{shift:+d} semitonos → {dest.name}"))
    busy=QProgressBar();busy.setRange(0,0);op_layout.addWidget(busy)
    proc=QProcess(operation)
    proc.setProgram("ffmpeg")
    proc.setArguments(["-hide_banner","-nostdin","-loglevel","error","-y","-i",str(source),
        "-af",f"rubberband=pitch={2**(shift/12):.9f}",*codec,str(dest)])
    def completed(code,status):
        operation.close()
        if code==0 and status==QProcess.NormalExit and dest.exists() and dest.stat().st_size>0:
            store.items.append(dest);store.manifest()
            panel.populate()
            for line in panel.lines:line.checked.setChecked(line.path==dest)
            main.workbench.separator.refresh_outputs()
            panel.status.setText("Nueva versión transpuesta creada; seleccionada para guardar o enviar.")
        else:
            dest.unlink(missing_ok=True)
            QMessageBox.warning(panel,"Error al transponer",
                                bytes(proc.readAllStandardError()).decode("utf-8","replace")[-900:] or "Falló FFmpeg.")
        proc.deleteLater();operation.deleteLater()
    proc.finished.connect(completed)
    proc.setProcessChannelMode(QProcess.SeparateChannels)
    proc.start()
    operation.show()
    panel._pitch_operation=operation
    operation._pitch_process=proc
