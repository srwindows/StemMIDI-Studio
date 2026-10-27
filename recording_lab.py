"""Laboratorio de grabación profesional, no destructivo, para StemMIDI Studio.

El motor de grabación permanece sin efectos. El usuario puede elegir
aplicar el laboratorio MANUALMENTE o AUTOMÁTICAMENTE AL TERMINAR la toma.
"""
from __future__ import annotations
from pathlib import Path
import os
import uuid
from PySide6.QtCore import Qt,QProcess,Signal
from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFrame,QLabel,QPushButton,
    QCheckBox,QComboBox,QLineEdit,QMessageBox,QGroupBox,QScrollArea,QTabWidget,
    QSizePolicy
)
from studio_slider_spin import StudioSliderSpin
from preview_player import PreviewPlayer
from recording_lab_engine import DEFAULT,validated,command

CONTROL_GROUPS=[
 ("LIMPIEZA Y RESTAURACIÓN",[
    ("denoise","Ruido continuo",0,25," dB",
     "0: sin reducción espectral. A la derecha elimina más ruido constante "
     "(ventilación, siseo), pero demasiado puede borrar detalles y producir artefactos."),
    ("highpass","Filtro paso alto",0,300," Hz",
     "0 Hz: desactivado. Al aumentar elimina más graves (rumble/vibraciones). "
     "Al disminuir conserva más cuerpo. No elimina ruido de medios."),
    ("lowpass","Paso bajo",4500,20000," Hz",
     "A la izquierda elimina más agudos/siseo; a la derecha conserva más brillo. "
     "Activa primero la casilla Paso bajo."),
    ("gate_threshold","Umbral puerta", -65,-20," dB",
     "A la derecha cierra la puerta ante sonidos cada vez más fuertes y "
     "puede cortar palabras suaves; a la izquierda deja pasar más fondo.")
 ]),
 ("ECUALIZADOR PARAMÉTRICO",[
    ("bass","Graves · 120 Hz",-12,12," dB",
     "A la derecha realza cuerpo/bajos; a la izquierda elimina resonancia o retumbe."),
    ("lowmid","Medios bajos · 390 Hz",-12,12," dB",
     "A la derecha aporta cuerpo; a la izquierda limpia sonido turbio o acartonado."),
    ("highmid","Presencia · 2,8 kHz",-12,12," dB",
     "A la derecha mejora inteligibilidad; a la izquierda suaviza dureza."),
    ("treble","Agudos · 8 kHz",-12,12," dB",
     "A la derecha añade brillo; a la izquierda reduce aspereza o siseo."),
 ]),
 ("DINÁMICA, INTELIGIBILIDAD Y SALIDA",[
    ("deesser","Reductor de eses",0,100," %",
     "A la derecha reduce más consonantes sibilantes; a la izquierda deja la voz natural."),
    ("comp_threshold","Umbral compresor",-45,-8," dB",
     "A la izquierda comprime sonidos más suaves; a la derecha comprime solo "
     "picos fuertes. Activa la casilla Compresor."),
    ("comp_ratio","Ratio de compresión",1,10,":1",
     "A la derecha reduce más diferencias entre fuerte y suave; "
     "a la izquierda es menos invasivo."),
    ("comp_attack","Ataque",1,100," ms",
     "A la izquierda comprime más rápido los transitorios; "
     "a la derecha conserva mejor los ataques."),
    ("comp_release","Relajación",30,600," ms",
     "A la derecha tarda más en dejar de comprimir; "
     "a la izquierda vuelve antes al volumen original."),
    ("stereo_width","Anchura estéreo",0,160," %",
     "0% suma hacia mono, 100% respeta la apertura, "
     "más de 100% amplía los laterales y puede empeorar compatibilidad mono."),
    ("output_gain","Ganancia final",-18,18," dB",
     "A la derecha sube volumen y aumenta riesgo de saturación; "
     "a la izquierda atenúa la señal."),
    ("target_lufs","Sonoridad final",-24,-10," LUFS",
     "Hacia la derecha hace el objetivo de sonoridad más alto (menos negativo). "
     "Hacia la izquierda lo reduce. La medición es aproximada, de una pasada.")
 ])
]
CHECKS=[
    ("declick","Eliminar clics / chasquidos",
     "Reconstruye algunos impulsos cortos. No repara clips destructivos ni cortes largos."),
    ("lowpass_enabled","Aplicar filtro paso bajo",
     "Activado: elimina frecuencias por encima del corte; desactivado: conserva los agudos."),
    ("gate_enabled","Puerta de ruido",
     "Activada: atenúa silencios bajo el umbral; desactivada: conserva sus niveles."),
    ("comp_enabled","Compresor",
     "Activado: reduce diferencias de nivel; desactivado: mantiene dinámica original."),
    ("limiter","Limitador de picos · -1 dBFS",
     "Activado: atenúa picos que se aproximen al techo; desactivado: no limita."),
    ("loudnorm_enabled","Normalizar sonoridad · LUFS",
     "Activada: adapta sonoridad global en un paso. No equivale a medición LUFS "
     "certificada ni masterización multipaso.")
]
BUILTINS={
 "Original / sin efectos":dict(DEFAULT,highpass=0,limiter=False),
 "Voz clara":dict(DEFAULT,denoise=7,highpass=85,lowmid=-2,
                    highmid=2,deesser=20,comp_enabled=True,
                    comp_threshold=-24,comp_ratio=3,limiter=True),
 "Podcast":dict(DEFAULT,denoise=9,highpass=75,bass=1,lowmid=-2,
                 highmid=3,deesser=30,comp_enabled=True,
                 comp_ratio=3,loudnorm_enabled=True,target_lufs=-16),
 "Restauración suave":dict(DEFAULT,denoise=12,declick=True,highpass=55,
                 gate_enabled=False,lowmid=-1,limiter=True),
 "Música equilibrada":dict(DEFAULT,denoise=3,highpass=35,
                 bass=0,lowmid=0,highmid=0,treble=0,
                 comp_enabled=False,limiter=True),
}

class RecordingLab(QFrame):
    resultsChanged=Signal()
    def __init__(self,main,parent=None):
        super().__init__(parent)
        self.main=main
        self.setObjectName("panel")
        self.process=None
        self.original=None
        self.processed=None
        self.temp_output=None
        self.final_output=None
        self.log_data=bytearray()
        layout=QVBoxLayout(self)
        layout.setContentsMargins(8,6,8,6)
        layout.setSpacing(4)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        title=QLabel("LABORATORIO PROFESIONAL DE AUDIO")
        title.setObjectName("section")
        layout.addWidget(title)
        title.setToolTip("Restauración, ecualización y mastering no destructivo. "
             "Siempre se guarda la toma original. Los filtros se aplican "
             "a una copia FLAC, después de terminar la grabación.")
        title.setMaximumHeight(23)

        from ux_controls import PresetStrip
        self.presets=PresetStrip("laboratorio_grabacion",BUILTINS,self.snapshot,
                                 self.apply_preset,self)
        layout.addWidget(self.presets)
        # El banco de presets ocupa una sola fila comprimida, no exige
        # más de 540 px en el ancho de la columna.
        self.presets.setMaximumHeight(43)
        self.presets.choices.setMinimumWidth(96)
        self.presets.choices.setMaximumWidth(123)
        self.presets.name.setMinimumWidth(48)
        self.presets.name.setMaximumWidth(90)
        self.presets.save_btn.setText("+")
        self.presets.save_btn.setToolTip("Guardar estos valores en un preset personal.")
        self.presets.save_btn.setMaximumWidth(34)
        self.presets.delete_btn.setText("−")
        self.presets.delete_btn.setToolTip("Eliminar el preset personal seleccionado.")
        self.presets.delete_btn.setMaximumWidth(34)
        self.presets.message.hide()
        self.presets.layout().setContentsMargins(4,3,4,3)
        self.presets.layout().setSpacing(3)

        source_row=QHBoxLayout()
        source_row.setSpacing(4)
        self.source_path=QLineEdit(self)
        self.source_path.setPlaceholderText("Selecciona una toma original WAV/FLAC/MP3…")
        self.source_path.setReadOnly(True)
        self.source_path.setToolTip("Archivo que se va a procesar. "
             "El original no se modifica en ningún momento.")
        source_row.addWidget(self.source_path,1)
        self.pick_button=QPushButton("Elegir toma…")
        self.pick_button.clicked.connect(self.pick_source)
        self.pick_button.setText("Elegir…")
        self.pick_button.setToolTip("Elegir un audio original de este proyecto u otro archivo permitido.")
        source_row.addWidget(self.pick_button)
        self.last_button=QPushButton("Última toma")
        self.last_button.clicked.connect(self.use_last_recording)
        source_row.addWidget(self.last_button)
        layout.addLayout(source_row)

        self.auto_after=QCheckBox("Procesar automáticamente al terminar cada grabación")
        self.auto_after.setToolTip(
            "Marcada: primero guarda la grabación ORIGINAL y, cuando FFmpeg "
            "termine de escribirla, aplica los efectos en un segundo archivo. "
            "Desmarcada: solo se procesa al pulsar Procesar. No provoca latencia "
            "en la señal durante la grabación.")
        layout.addWidget(self.auto_after)
        self.controls={}
        self.checks={}
        self.sections=QTabWidget(self)
        self.sections.setObjectName("labSections")
        self.sections.setDocumentMode(True)
        self.sections.setUsesScrollButtons(False)
        label_for_check={key:(text,tip) for key,text,tip in CHECKS}
        labels=("RESTAURAR","ECUALIZAR","COMPRESOR","SALIDA")
        sets=(
          ("declick","lowpass_enabled","gate_enabled"),
          (),
          ("comp_enabled",),
          ("limiter","loudnorm_enabled")
        )
        control_pages=(CONTROL_GROUPS[0][1],CONTROL_GROUPS[1][1],
                       CONTROL_GROUPS[2][1][:4],CONTROL_GROUPS[2][1][4:])
        for index,fields in enumerate(control_pages):
            page=QWidget(self.sections)
            page.setObjectName("studioModuleSurface")
            body=QVBoxLayout(page)
            body.setContentsMargins(5,4,5,3)
            body.setSpacing(2)
            settings=QGridLayout()
            settings.setContentsMargins(0,0,0,0)
            settings.setVerticalSpacing(5)
            settings.setHorizontalSpacing(7)
            for i,(name,label,low,high,suffix,help_text) in enumerate(fields):
                caption=QLabel(label,page)
                caption.setToolTip(help_text)
                caption.setMinimumWidth(0)
                caption.setWordWrap(False)
                slider=StudioSliderSpin(low,high,DEFAULT[name],suffix,
                                        page,width=220)
                slider.setObjectName(name)
                slider.slider.setObjectName(name)
                slider.spin.setObjectName(name)
                slider.setToolTip(help_text)
                slider.setMinimumWidth(150)
                slider.setMaximumWidth(220)
                slider.spin.setFixedHeight(24)
                slider.setMaximumHeight(27)
                settings.addWidget(caption,i,0)
                settings.addWidget(slider,i,1)
                self.controls[name]=slider
            body.addLayout(settings)
            relevant=sets[index]
            if relevant:
                checks=QGridLayout()
                checks.setHorizontalSpacing(9)
                checks.setVerticalSpacing(2)
                for j,key in enumerate(relevant):
                    text,help_text=label_for_check[key]
                    check=QCheckBox(text,page)
                    check.setObjectName(key)
                    check.setToolTip(help_text)
                    self.checks[key]=check
                    checks.addWidget(check,j//2,j%2)
                body.addLayout(checks)
            body.addStretch(1)
            self.sections.addTab(page,labels[index])
        self.sections.setMinimumHeight(185)
        layout.addWidget(self.sections,1)

        row=QHBoxLayout()
        self.run_button=QPushButton("Procesar · FLAC")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_from_button)
        row.addWidget(self.run_button,1)
        self.cancel_button=QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.cancel_button.setEnabled(False)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

        self.status=QLabel("Preparado. Selecciona una toma y pulsa Procesar.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.presets.save_btn.clicked.connect(
            lambda:self.status.setText(self.presets.message.text()))
        self.presets.delete_btn.clicked.connect(
            lambda:self.status.setText(self.presets.message.text()))
        ab=QHBoxLayout()
        self.play_original=QPushButton("A/B · Original")
        self.play_processed=QPushButton("A/B · Procesado")
        self.play_original.clicked.connect(lambda:self.play(self.original))
        self.play_processed.clicked.connect(lambda:self.play(self.processed))
        ab.addWidget(self.play_original)
        ab.addWidget(self.play_processed)
        layout.addLayout(ab)
        self.preview=PreviewPlayer("PREESCUCHA A/B",self)
        self.preview.set_compact(True)
        self.preview.detail.hide()
        # El transporte de escucha sigue operativo en una única fila.
        # Las opciones de reproducción se mantienen accesibles junto
        # a los dos botones A/B, no en una cabecera duplicada de 30 px.
        header=self.preview.layout().itemAt(0).layout()
        for i in range(header.count()):
            item=header.itemAt(i)
            widget=item.widget()
            if widget is not None and widget is not self.preview.options_button:
                widget.hide()
        ab.addWidget(self.preview.options_button)
        layout.addWidget(self.preview,0)
        self.export_button=QPushButton("Guardar resultado como…")
        self.export_button.clicked.connect(self.export_current)
        layout.addWidget(self.export_button)
        self.apply_preset(DEFAULT)

    def snapshot(self):
        settings={name:control.value() for name,control in self.controls.items()}
        settings.update({name:checkbox.isChecked()
                        for name,checkbox in self.checks.items()})
        settings["auto_after"]=self.auto_after.isChecked()
        return validated(settings)

    def apply_preset(self,data):
        current=self.snapshot() if self.controls and len(self.controls)==len(
            [name for _,g in CONTROL_GROUPS for name,*_ in g]) else DEFAULT
        settings=validated(dict(current,**data))
        for name,c in self.controls.items():
            if c.value()!=settings[name]:c.setValue(settings[name])
        for name,c in self.checks.items():
            if c.isChecked()!=settings[name]:c.setChecked(settings[name])
        self.auto_after.setChecked(settings["auto_after"])

    def set_source(self,path):
        path=Path(path).expanduser().resolve()
        if not path.is_file():raise FileNotFoundError(str(path))
        if self.process is not None:
            raise ValueError("Espera a terminar el proceso activo.")
        self.preview.clear()
        self.original=path
        self.source_path.setText(str(path))
        self.processed=None
        self.play_processed.setEnabled(False)
        self.export_button.setEnabled(False)
        self.status.setText("Fuente original cargada: "+path.name)
        self.play_original.setEnabled(True)

    def pick_source(self):
        import file_dialogs
        root=Path(self.main.project_dir) if self.main.project_dir else Path.home()
        path,_=file_dialogs.get_open_file_name(self,
            "Elegir toma para restaurar o ecualizar",str(root),
            "Audio (*.wav *.flac *.mp3 *.m4a *.aac *.opus *.aiff *.ogg)")
        if path:
            try:self.set_source(path)
            except (OSError,ValueError) as error:
                QMessageBox.warning(self,"Fuente de audio",str(error))

    def use_last_recording(self):
        path=getattr(self.main,"last_file",None)
        if not path or not Path(path).is_file():
            QMessageBox.information(self,"Sin toma",
                                    "Graba primero una toma o elige un audio.")
            return
        try:self.set_source(path)
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,"Sin toma",str(exc))

    def on_recording_finished(self,path,success):
        if not success:return
        if self.process is not None:
            self.status.setText("Hay un render activo; esta nueva toma "
                                "permanece disponible para procesarla después.")
            return
        try:self.set_source(path)
        except (OSError,ValueError):
            return
        if self.auto_after.isChecked():
            self.run_processing(automatic=True)

    def _destination(self,source):
        project=Path(self.main.project_dir) if self.main.project_dir else None
        if project is None or not project.is_dir():
            raise ValueError("Crea o abre un proyecto para guardar los resultados.")
        from project_layout import module_dir
        from task_staging import unique_dest
        target=module_dir(project,"grabaciones")
        if target.is_symlink():raise ValueError("La carpeta de grabaciones es un enlace.")
        target.mkdir(parents=True,exist_ok=True)
        filename=source.stem+"_laboratorio.flac"
        return unique_dest(target,filename)

    def run_from_button(self):
        self.run_processing(automatic=False)

    def run_processing(self,automatic=False):
        if self.process is not None:
            if not automatic:
                QMessageBox.information(self,"Procesamiento activo",
                                    "Finaliza o cancela antes de continuar.")
            return False
        source=self.original or (Path(self.main.last_file)
                    if self.main.last_file else None)
        if source is None or not source.is_file():
            if not automatic:
                QMessageBox.information(self,"Falta audio",
                                        "Selecciona una grabación original.")
            return False
        try:
            project=Path(self.main.project_dir) if self.main.project_dir else None
            if project is None or not project.is_dir():
                raise ValueError("Se necesita un proyecto activo para procesar.")
            target=self._destination(source)
            temp=project/"temporales"/"monitor"
            temp.mkdir(parents=True,exist_ok=True)
            intermediate=temp/("laboratorio_"+uuid.uuid4().hex+".flac")
            arguments=command(source,intermediate,self.snapshot())
        except (OSError,ValueError,TypeError) as error:
            self.status.setText("No se pudo preparar el laboratorio: "+str(error))
            if not automatic:
                QMessageBox.warning(self,"Laboratorio",str(error))
            return False
        self.temp_output=intermediate
        self.final_output=target
        self.log_data=bytearray()
        proc=QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read_process)
        proc.finished.connect(self._finished_process)
        proc.errorOccurred.connect(self._process_error)
        self.process=proc
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.pick_button.setEnabled(False)
        self.last_button.setEnabled(False)
        self.status.setText("Procesando copia mediante FFmpeg. "
                            "La grabación original permanece intacta.")
        proc.start(arguments[0],arguments[1:])
        return True

    def _read_process(self):
        if self.process is not None:
            self.log_data.extend(bytes(self.process.readAllStandardOutput()))
            if len(self.log_data)>32768:self.log_data=self.log_data[-16384:]

    def _process_error(self,error):
        # No liberar hasta que QProcess haya salido; si no arrancó,
        # finished() no se emitirá.
        if error==QProcess.FailedToStart:
            self._finish_failed("FFmpeg no se pudo iniciar.")

    def _finish_failed(self,description):
        self._read_process()
        if self.temp_output:self.temp_output.unlink(missing_ok=True)
        if self.process:
            self.process.deleteLater()
            self.process=None
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.pick_button.setEnabled(True)
        self.last_button.setEnabled(True)
        self.status.setText("Error en el laboratorio: "+description)
        self.temp_output=None;self.final_output=None

    def _finished_process(self,code,state):
        self._read_process()
        if self.process is None:return
        proc=self.process
        self.process=None
        proc.deleteLater()
        temp=self.temp_output
        final=self.final_output
        self.temp_output=None;self.final_output=None
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.pick_button.setEnabled(True)
        self.last_button.setEnabled(True)
        if code!=0 or state!=QProcess.NormalExit or not temp or not temp.is_file() or temp.stat().st_size<200:
            if temp:temp.unlink(missing_ok=True)
            detail=self.log_data.decode(errors="replace")[-750:]
            self.status.setText("No se ha creado el audio procesado. "+
                                (detail or "FFmpeg terminó con error."))
            return
        try:
            # Conservar todos los resultados y resolver colisiones entre
            # renders consecutivos; os.replace del temporal propio.
            from task_staging import unique_dest
            final=unique_dest(final.parent,final.name)
            os.replace(temp,final)
            self.processed=final
            self.play_processed.setEnabled(True)
            self.export_button.setEnabled(True)
            self.status.setText("Listo: "+final.name+
                ". Original intacto. Escucha A/B para comparar antes de guardar.")
            self.preview.load(final)
            self.resultsChanged.emit()
        except OSError as error:
            # Evita borrar un resultado válido si falla el movimiento.
            self.status.setText("Procesado terminado, pero falta incorporar "
                                "el archivo al proyecto: "+str(error))

    def cancel_processing(self):
        if self.process is not None and self.process.state()!=QProcess.NotRunning:
            self.process.kill()
            self.status.setText("Cancelando solo el procesamiento; "
                                "la grabación original está protegida.")

    def play(self,path):
        if path and Path(path).is_file():self.preview.load(path,autoplay=True)

    def export_current(self):
        if not self.processed or not self.processed.is_file():
            QMessageBox.information(self,"Sin resultado",
                          "Genera primero una nueva versión procesada.")
            return []
        from export_dialog import export_files
        return export_files(self,[self.processed],
                    self.main.project_dir,"Guardar resultado del laboratorio",
                    kind="grabaciones")

    def reset_project_source(self):
        if self.process is not None:
            raise ValueError("El laboratorio está procesando; espera a que termine.")
        self.preview.clear()
        self.original=None;self.processed=None
        self.source_path.clear()
        self.play_original.setEnabled(False)
        self.play_processed.setEnabled(False)
        self.export_button.setEnabled(False)
        self.status.setText("Proyecto cambiado. Selecciona una grabación.")

    def close_cleanup(self):
        if self.process is not None:
            self.cancel_processing()
            self.process.waitForFinished(5000)
        self.preview.cleanup()
