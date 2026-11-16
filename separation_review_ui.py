"""Revisión de stems: filas profesionales con onda y medición PCM reales.

No se modifican audios ni nombres en disco. Las etiquetas cortas son solo
visuales. El análisis FFT no representa silencio artificial: se dibujan
picos por intervalos y se comunica RMS real.
"""
from __future__ import annotations

import math
import os
import subprocess
import threading
import weakref
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget,QFrame,QLabel,QHBoxLayout,QVBoxLayout,QCheckBox,QProgressBar,
    QPushButton,QSizePolicy
)
from separation_pro_controls import instrument_for

DISPLAY={"Voz":"Vocal","Batería":"Batería","Bajo":"Bajo",
         "Guitarra":"Guitarra","Piano":"Piano","Otros":"Otros",
         "Instrumental":"Instrumental","Izquierdo":"Izquierdo",
         "Derecho":"Derecho"}
LIVE_NAMES={"Voz":"Voces","Batería":"Batería","Bajo":"Bajo",
            "Guitarra":"Guitarra","Piano":"Piano","Otros":"Otros"}


class ActualWaveform(QWidget):
    measured=Signal(object,float)
    cache={}
    def __init__(self,path,parent=None):
        super().__init__(parent)
        self.path=Path(path)
        self.values=()
        self.rms=0.0
        self.ready=False
        self.setMinimumWidth(95)
        self.setMinimumHeight(25)
        self.setMaximumHeight(29)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.setToolTip("Leyendo la señal PCM real del archivo…")
        self.measured.connect(self._apply)
        self._begin()

    def _begin(self):
        try:
            stat=self.path.stat()
            key=(str(self.path.resolve()),stat.st_size,stat.st_mtime_ns)
        except OSError:
            return
        if key in self.cache:
            self._apply(*self.cache[key])
            return
        ref=weakref.ref(self)
        def analyze():
            # Nunca reducir la señal a 400 Hz: el filtro antialias elimina
            # voces, guitarras y agudos, produciendo ondas falsas de silencio.
            # Analizar PCM a 16 kHz por bloques: memoria acotada incluso con
            # canciones largas y picos de cada pista independientes.
            import shutil
            import time
            import numpy as np
            from studio_paths import resource_root
            native=resource_root(__file__)/"vendor/native/bin/ffmpeg"
            development=Path(__file__).resolve().parent.parent/"native/bin/ffmpeg"
            executable=next((str(p) for p in (native,development)
                             if p.is_file()),shutil.which("ffmpeg"))
            values=()
            rms=-1.0  # Error distinguible de silencio REAL (RMS=0).
            proc=None
            if executable:
                try:
                    command=[executable,"-nostdin","-hide_banner","-loglevel","error",
                             "-i",str(self.path),"-map","0:a:0","-t","1800",
                             "-ac","1","-ar","16000","-f","f32le","pipe:1"]
                    proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                    peaks=[]
                    energy=0.0
                    count=0
                    started=time.monotonic()
                    while time.monotonic()-started<90:
                        raw=proc.stdout.read(4096)
                        if not raw:break
                        if len(raw)%4:break
                        chunk=np.nan_to_num(np.frombuffer(raw,dtype="<f4"),
                                            nan=0.,posinf=0.,neginf=0.)
                        if not len(chunk):continue
                        peaks.append(float(np.max(np.abs(chunk))))
                        energy+=float(np.sum(np.square(chunk.astype("float64"))))
                        count+=len(chunk)
                    try:code=proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        code=proc.wait(timeout=2)
                    if code==0 and count and peaks:
                        peak_values=np.asarray(peaks,dtype="float32")
                        total=len(peak_values)
                        values=tuple(float(np.max(peak_values[
                            int(i*total/112):max(int(i*total/112)+1,
                            int((i+1)*total/112))])) for i in range(112))
                        rms=math.sqrt(energy/count)
                except (OSError,ValueError,subprocess.TimeoutExpired):
                    pass
                finally:
                    if proc is not None and proc.poll() is None:
                        proc.kill()
                        try:proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:pass
            if rms>=0:
                self.cache[key]=(values,rms)
            target=ref()
            if target is not None:
                try:target.measured.emit(values,rms)
                except RuntimeError:pass
        threading.Thread(target=analyze,daemon=True,
                         name="StemMIDI-Waveform-PCM").start()

    def _apply(self,values,rms):
        self.values=values
        self.rms=rms
        self.ready=True
        if rms<0:
            self.setToolTip("No se pudo analizar la señal PCM de este archivo. No significa que esté vacío.")
            self.update()
            return
        db=20*math.log10(max(1e-9,rms))
        self.setToolTip("Nivel RMS del archivo: "+(
            "−∞ dBFS" if db<=-90 else f"{db:.1f} dBFS")+
            (" · sin señal apreciable" if db<-55 else
             " · contiene señal; puede haber filtración de otros instrumentos"))
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor("#06152e"))
        y=self.height()/2
        painter.setPen(QPen(QColor("#355779"),1))
        painter.drawLine(2,int(y),self.width()-2,int(y))
        if not self.ready:
            painter.setPen(QColor("#8fb9d8"))
            painter.setFont(QFont("Sans",9))
            painter.drawText(self.rect(),Qt.AlignCenter,"Analizando onda…")
            return
        width=max(2,self.width()-6)
        if not self.values:
            painter.setPen(QColor("#f7c89f"))
            painter.setFont(QFont("Sans",8))
            painter.drawText(self.rect(),Qt.AlignCenter,"Análisis no disponible")
            return
        peak=max(self.values)
        # Escala FIJA en amplitud (no normalizar cada stem), para que la
        # onda pequeña o ausente se distinga de una separación con señal.
        painter.setPen(QPen(QColor("#23daed") if peak>.002 else
                            QColor("#658299"),1.6))
        for i,v in enumerate(self.values):
            xx=3+int((i+.5)*width/len(self.values))
            amp=min(self.height()*.45,max(0.,float(v))*self.height()*.45)
            painter.drawLine(xx,int(y-amp),xx,int(y+amp))
        if peak<.001:
            painter.setPen(QColor("#a8becf"))
            painter.setFont(QFont("Sans",8))
            painter.drawText(self.rect(),Qt.AlignCenter,"Sin señal apreciable")


class CompactTrackVU(QProgressBar):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setRange(0,1000)
        self.setValue(0)
        self.setFormat("−∞")
        self.setTextVisible(True)
        self.setFixedWidth(100)
        self.setFixedHeight(22)
        self.setToolTip("Nivel real de este stem durante la reproducción (dBFS)")
        self.setStyleSheet("""
        QProgressBar {color:#e4faff;font-size:12px;font-weight:700;
            background:#061730;border:1px solid #245981;border-radius:3px;
            text-align:center;}
        QProgressBar::chunk {background:#12bbdc;border-radius:2px;}
        """)

    def show_peak(self,peak):
        peak=min(1.,max(0.,float(peak)))
        db=20*math.log10(max(1e-9,peak))
        self.setValue(max(0,min(1000,round(1000*(db+60)/60))))
        self.setFormat(f"{db:.0f} dB" if db>=-60 else "−∞")


class ReviewTrackLine(QFrame):
    """Solo para resultados de separación; los MIDI mantienen su fila."""
    def __init__(self,path,index,play_callback,stop_callback,parent=None,
                 edit_callback=None):
        super().__init__(parent)
        self.setObjectName("inner")
        self.path=Path(path)
        self.index=index
        name=instrument_for(path)
        self.instrument=name
        row=QHBoxLayout(self)
        row.setContentsMargins(6,2,6,2)
        row.setSpacing(7)
        self.checked=QCheckBox()
        self.checked.setChecked(True)
        self.checked.setToolTip("Escuchar o silenciar este stem. También selecciona su exportación.")
        row.addWidget(self.checked)
        self.name=QLabel(DISPLAY.get(name,"Pista"))
        self.name.setToolTip(str(self.path))
        self.name.setMinimumWidth(62)
        self.name.setMaximumWidth(85)
        self.name.setStyleSheet("font-weight:700;color:#edfbff;")
        row.addWidget(self.name)
        self.wave=ActualWaveform(self.path,self)
        row.addWidget(self.wave,1)
        self.vu=CompactTrackVU(self)
        row.addWidget(self.vu)
        # Compatibilidad con el código de exportación y con los otros
        # módulos: cada pista conserva path, index, checked y name.
        self.format=QLabel(self.path.suffix.lstrip(".").upper())
        self.format.hide()
        self.play=QPushButton("▶")
        self.play.hide()
        self.stop=QPushButton("■")
        self.stop.hide()
        self.setFixedHeight(33)
        self.setToolTip("Archivo: "+str(self.path)+"\nForma de onda real y VU del reproductor.")

def install_results_review(main):
    """Un transporte real controla mezcla, mute y VU sin Play/Stop por fila."""
    panel=main.workbench.sep_results
    panel._audio_review_enabled=True
    panel.populate()
    player=panel.preview
    player.filename.setText("Escucha de stems marcados")
    player.filename.setToolTip("Las casillas de cada pista determinan lo que se escucha.")
    # Mantener los QComboBox existentes, solo cambiar su distribución.
    player._measured_vu.timer.stop()
    player._measured_vu.meter.setMaximumWidth(210)
    player._measured_vu.meter.setMinimumHeight(53)

    def listen():
        home=getattr(main,"studio_home",None)
        return getattr(home,"_sep_listen",None) if home else None

    def _play():
        engine=listen()
        if engine is None:return
        if engine.live.running:
            engine.pause()
        else:
            panel._sync_review_selection()
            engine.play()
    def _stop():
        engine=listen()
        if engine is not None:engine.stop()
    try:player.play_button.clicked.disconnect()
    except RuntimeError:pass
    try:player.stop_button.clicked.disconnect()
    except RuntimeError:pass
    player.play_button.clicked.connect(_play)
    player.stop_button.clicked.connect(_stop)

    def _seek():
        engine=listen()
        if engine is not None and engine.live.duration_ms:
            engine.seek(round(engine.live.duration_ms*player.slider.value()/1000))
    try:player.slider.sliderReleased.disconnect()
    except RuntimeError:pass
    player.slider.sliderReleased.connect(_seek)

    def _gain(value):
        engine=listen()
        if engine is not None:
            engine.live.set_master_volume(value/100)
    player.volume.valueChanged.connect(_gain)
    def _speed(_=None):
        engine=listen()
        if engine is not None:
            engine.live.set_speed(float(player.speed.currentData() or 1.))
    player.speed.currentIndexChanged.connect(_speed)

    def _checkbox(name,checked):
        engine=listen()
        if engine is not None and name in LIVE_NAMES:
            engine.set_enabled(LIVE_NAMES[name],checked)

    def _sync_catalog():
        engine=listen()
        if engine is None:return
        for line in panel.lines:
            if line.instrument not in LIVE_NAMES:continue
            stem=LIVE_NAMES[line.instrument]
            found=engine.available().get(stem)
            if found is not None and Path(found).resolve()==line.path.resolve():
                engine.set_enabled(stem,line.checked.isChecked())
    panel._sync_review_selection=_sync_catalog

    def _tick():
        engine=listen()
        if engine is None:return
        live=engine.live
        running=live.running
        playing=running and not live.paused
        if hasattr(player,"_sketch_pause"):
            player.play_button.setText("▶")
            player._sketch_pause.setEnabled(running)
        else:
            player.play_button.setText("Ⅱ Pausa" if playing else "▶ Reproducir")
        player.play_button.setEnabled(bool(panel.lines))
        player.stop_button.setEnabled(running)
        player.slider.setEnabled(running and live.duration_ms>0)
        from preview_player import timecode
        pos=live.position() if running else 0
        player.clock.setText(timecode(pos)+" / "+timecode(live.duration_ms))
        if not player.slider.isSliderDown():
            blocked=player.slider.blockSignals(True)
            player.slider.setValue(round(1000*pos/live.duration_ms)
                  if live.duration_ms else 0)
            player.slider.blockSignals(blocked)
        master=live.master_peaks if playing else (0.,0.)
        player._measured_vu.meter.set_levels(*master,*master)
        if hasattr(player,"_sketch_meter"):
            player._sketch_meter.set_levels(*master)
        for line in panel.lines:
            name=LIVE_NAMES.get(line.instrument,"")
            level=live.track_peaks.get(name,(0.,0.)) if playing else (0.,0.)
            line.vu.show_peak(max(level))
    timer=QTimer(panel)
    timer.setInterval(95)
    timer.timeout.connect(_tick)
    timer.start()
    panel._review_timer=timer
    panel._review_tick=_tick
    panel._review_checkbox=_checkbox
    panel._review_listen=listen
    # Las filas nuevas se conectan cuando TaskResults.populate se ejecuta.
    _tick()


class SeparationSettingsHistory:
    """Deshacer/Rehacer de ajustes, nunca borra audio ni tareas temporales."""
    def __init__(self,sep,undo,redo,reset):
        self.sep=sep
        self.undo_button=undo
        self.redo_button=redo
        self._locked=False
        self._states=[]
        self._index=-1
        self._timer=QTimer(sep)
        self._timer.setSingleShot(True)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self.capture)
        undo.clicked.connect(self.undo)
        redo.clicked.connect(self.redo)
        reset.clicked.connect(self.reset)
        for combo in (sep.profile,sep.quality,sep.export_fmt):
            combo.currentIndexChanged.connect(self.schedule)
        for box in sep.stem_checks.values():
            box.toggled.connect(self.schedule)
        self.capture()

    def snapshot(self):
        sep=self.sep
        return (sep.profile.currentText(),sep.quality.currentIndex(),
                sep.export_fmt.currentIndex(),
                tuple(sorted(name for name,box in sep.stem_checks.items()
                             if box.isEnabled() and box.isChecked())),
                round(float(sep.norm_setting),3),
                round(float(sep.amp_setting),3),
                int(sep.sample_setting),
                tuple(sorted(getattr(sep,"engine_parameters",{}).items())))

    def schedule(self,*args):
        if not self._locked and not self.sep.busy:self._timer.start()

    def capture(self):
        if self._locked:return
        state=self.snapshot()
        if self._index>=0 and self._states[self._index]==state:
            return self._buttons()
        self._states=self._states[:self._index+1]+[state]
        self._states=self._states[-35:]
        self._index=len(self._states)-1
        self._buttons()

    def _buttons(self):
        self.undo_button.setEnabled(self._index>0 and not self.sep.busy)
        self.redo_button.setEnabled(self._index<len(self._states)-1
                                    and not self.sep.busy)

    def restore(self,state):
        sep=self.sep
        self._timer.stop()
        self._locked=True
        try:
            model,quality,fmt,checked,norm,amp,rate,eng=state
            if sep.profile.findText(model)>=0:
                sep.profile.setCurrentText(model)
            sep.quality.setCurrentIndex(quality)
            sep.export_fmt.setCurrentIndex(fmt)
            for name,box in sep.stem_checks.items():
                if box.isEnabled():box.setChecked(name in checked)
            sep.norm_setting=norm
            sep.amp_setting=amp
            sep.sample_setting=rate
            sep.engine_parameters=dict(eng)
            sep.save_preferences()
            refresher=getattr(sep,'_advanced_controls',{}).get('engine_refresh')
            if refresher:refresher()
        finally:
            self._locked=False
        self._buttons()

    def undo(self):
        if self.sep.busy or self._index<=0:return
        self._index-=1
        self.restore(self._states[self._index])

    def redo(self):
        if self.sep.busy or self._index>=len(self._states)-1:return
        self._index+=1
        self.restore(self._states[self._index])

    def reset(self):
        if self.sep.busy:return
        sep=self.sep
        # Reiniciar opciones, no archivos, proyecto o resultado separado.
        self._locked=True
        try:
            sep.quality.setCurrentIndex(0)
            sep.export_fmt.setCurrentIndex(0)
            sep.norm_setting=.90
            sep.amp_setting=0.0
            sep.sample_setting=44100
            sep.engine_parameters={}
            refresher=getattr(sep,'_advanced_controls',{}).get('engine_refresh')
            if refresher:refresher()
            for box in sep.stem_checks.values():
                if box.isEnabled():box.setChecked(True)
            sep.save_preferences()
        finally:
            self._locked=False
        self.capture()


def install_progress_panel(sep,activity):
    """Mostrar progresos reales a la DERECHA y registro legible a la izquierda."""
    from PySide6.QtWidgets import QGridLayout,QPlainTextEdit
    from separation_pro_controls import stems_for_model, instrument_for
    from separador import MODELS
    results=sep.workspace.sep_results
    layout=activity.body
    for index in reversed(range(layout.count())):
        item=layout.takeAt(index)
        if item.widget() is not None:item.widget().hide()
    activity.heading.setText("06 · REGISTRO DEL MOTOR")
    layout.setContentsMargins(10,5,10,6)
    layout.setSpacing(4)
    state=QLabel("Motor en espera")
    state.setStyleSheet("font-size:13px;font-weight:650;color:#effcff;")
    state.setWordWrap(False)
    layout.addWidget(state)
    file_label=QLabel("Audio: sin seleccionar")
    file_label.setToolTip("Archivo procesado y duración real de la tarea")
    file_label.setStyleSheet("font-size:13px;color:#cbe8f4;")
    layout.addWidget(file_label)
    technical=QPlainTextEdit()
    technical.setReadOnly(True)
    technical.setMaximumBlockCount(300)
    technical.setMinimumHeight(57)
    technical.setMaximumHeight(100)
    technical.setStyleSheet(
        "QPlainTextEdit{font-size:13px;color:#e4f8ff;background:#03132d;"
        "border:1px solid #285c82;border-radius:4px;padding:3px;}")
    layout.addWidget(technical,1)
    show=QPushButton("Ver registro completo…")
    show.setMaximumWidth(215)
    show.clicked.connect(sep.show_diagnostic_log)
    layout.addWidget(show)

    # El progreso del motor IA es compartido. Solo se declara 100% por
    # instrumento cuando su archivo final está efectivamente verificado.
    box=QFrame(results)
    box.setObjectName("inner")
    out=QVBoxLayout(box)
    out.setContentsMargins(9,6,9,6)
    out.setSpacing(4)
    main_row=QHBoxLayout()
    main_row.setSpacing(8)
    caption=QLabel("PROGRESO REAL DEL MOTOR")
    caption.setStyleSheet("font-size:13px;font-weight:750;color:#d9f9ff;")
    main_row.addWidget(caption,1)
    total=QProgressBar()
    total.setRange(0,100)
    total.setValue(0)
    total.setFixedWidth(155)
    total.setFixedHeight(22)
    total.setFormat("General · 0%")
    main_row.addWidget(total)
    out.addLayout(main_row)
    split=QGridLayout()
    split.setContentsMargins(0,0,0,0)
    split.setHorizontalSpacing(11)
    split.setVerticalSpacing(5)
    bars={}
    for idx,name in enumerate(("Voz","Batería","Bajo","Guitarra","Piano","Otros")):
        place=idx//2
        col=0 if idx%2==0 else 2
        lab=QLabel(DISPLAY.get(name,name))
        lab.setStyleSheet("font-size:13px;color:#e4f6ff;")
        lab.setMinimumWidth(48)
        bar=QProgressBar()
        bar.setRange(0,100)
        bar.setValue(0)
        bar.setFormat("0%")
        bar.setFixedHeight(20)
        bar.setMinimumWidth(65)
        bar.setStyleSheet(
            "QProgressBar{background:#06142e;color:white;font-size:12px;"
            "font-weight:700;border:1px solid #265981;border-radius:3px;"
            "text-align:center;}"
            "QProgressBar::chunk{background:#0dbfe4;border-radius:2px;}")
        split.addWidget(lab,place,col)
        split.addWidget(bar,place,col+1)
        bars[name]=(bar,lab)
    split.setColumnStretch(1,1)
    split.setColumnStretch(3,1)
    out.addLayout(split)
    note=QLabel("Fase común de IA; 100% individual solo tras verificar el stem.")
    note.setStyleSheet("font-size:13px;color:#b4d6e7;")
    out.addWidget(note)
    root=results.layout()
    root.insertWidget(root.indexOf(results.preview)+1,box)
    sep.progress.hide()
    sep.activity_info={"state":state,"file":file_label,"total":total,
                       "bars":{k:pair[0] for k,pair in bars.items()},
                       "labels":{k:pair[1] for k,pair in bars.items()},
                       "log":technical,"open":show,"box":box}
    def update():
        import shiboken6
        if not shiboken6.isValid(sep):return
        label=sep.profile.currentText()
        model=MODELS.get(label)
        dlg=getattr(sep,"motor_dialog",None)
        stage=dlg.stage.text() if dlg else ""
        status=("Separando"+(" · "+stage if stage else "") if sep.busy
                else "Finalizado" if sep.latest_outputs else "En espera")
        state.setText("Estado: "+status)
        source=Path(sep.file_edit.text().strip())
        # No desbordar la columna izquierda con nombres extensos.
        raw="Audio: "+source.name+"  ·  "+sep.elapsed.text()
        file_label.setToolTip(raw)
        file_label.setText(file_label.fontMetrics().elidedText(
            raw,Qt.ElideMiddle,max(115,activity.width()-34)))
        global_value=dlg.total.value() if dlg else sep.progress.value()
        total.setValue(global_value)
        total.setFormat(f"General · {global_value}%")
        active=set(getattr(sep,"active_request",stems_for_model(model)))
        found={instrument_for(p) for p in sep.latest_outputs}
        for name,(bar,lab) in bars.items():
            is_on=name in active and model is not None
            bar.setVisible(is_on)
            lab.setVisible(is_on)
            if is_on:
                if dlg is not None and name in dlg.rows:
                    value=dlg.rows[name].value()
                else:
                    value=100 if name in found else 0
                bar.setValue(value)
                bar.setFormat(f"{value}%")
        lines=sep.log.toPlainText()
        if technical.toPlainText()!=lines:
            technical.setPlainText(lines)
            scroll=technical.verticalScrollBar()
            scroll.setValue(scroll.maximum())
        if hasattr(sep,"model_run_selector"):
            sep.model_run_selector.setEnabled(not sep.busy)
            sep.model_run_import.setEnabled(not sep.busy)
    sep._activity_refresh=update
    watcher=QTimer(sep)
    watcher.setInterval(650)
    watcher.timeout.connect(update)
    watcher.start()
    sep._activity_watcher=watcher
    sep.log.textChanged.connect(update)
    QTimer.singleShot(0,update)
    return box


def compact_review_transport(player):
    """Un solo transporte, VU máster pequeño y controles repartidos."""
    # reflow_player creó anteriormente las conexiones reales, pero la
    # disposición duplicaba cabeceras, dispositivos y mostraba un gran VU.
    handler=getattr(player,"_reflow_responsive",None)
    if handler is not None:
        player.removeEventFilter(handler)
    outer=player.layout()
    while outer.count():
        outer.takeAt(0)
    outer.setContentsMargins(7,3,7,4)
    outer.setSpacing(4)
    player.filename.hide()
    player.detail.hide()
    player.options_button.hide()
    player.status.hide()
    player._measured_vu.meter.setMinimumWidth(152)
    player._measured_vu.meter.setMaximumWidth(178)
    player._measured_vu.meter.setFixedHeight(54)

    transport=QHBoxLayout()
    transport.setContentsMargins(0,0,0,0)
    transport.setSpacing(5)
    player.play_button.setText("▶ Reproducir")
    player.play_button.setMinimumWidth(90)
    player.play_button.setMaximumWidth(125)
    player.stop_button.setText("■ Detener")
    player.stop_button.setMinimumWidth(68)
    player.stop_button.setMaximumWidth(98)
    player.slider.setMinimumWidth(90)
    player.clock.setMinimumWidth(91)
    for widget in (player.play_button,player.stop_button,
                   player.slider,player.clock):
        transport.addWidget(widget,1 if widget is player.slider else 0)
    outer.addLayout(transport)

    master=QHBoxLayout()
    master.setContentsMargins(0,0,0,0)
    master.setSpacing(7)
    master.addWidget(player._measured_vu.meter)
    player.volume_label.setText("Vol.")
    master.addWidget(player.volume_label)
    player.volume.setMinimumWidth(55)
    player.volume.setMaximumWidth(115)
    master.addWidget(player.volume,1)
    player.speed_label.setText("Vel.")
    master.addWidget(player.speed_label)
    player.speed.setMinimumWidth(65)
    player.speed.setMaximumWidth(90)
    master.addWidget(player.speed)
    outer.addLayout(master)

    route=QHBoxLayout()
    route.setContentsMargins(0,0,0,0)
    route.setSpacing(7)
    player.route_label.setText("Salida")
    route.addWidget(player.route_label)
    player.device_choice.setMinimumWidth(70)
    player.device_choice.setMaximumWidth(16777215)
    player.device_choice.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    route.addWidget(player.device_choice,1)
    outer.addLayout(route)
    player.setMaximumHeight(158)
    player.setMinimumHeight(118)
    player.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)


def dark_combo_popup(combo):
    """Evita que el menú nativo de macOS se abra blanco sobre blanco."""
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtWidgets import QListView, QStyledItemDelegate
    # Forzar QListView Qt en lugar de NSMenu: así se respeta el tema
    # oscuro en los elementos normales, resaltados y seleccionados.
    view=QListView(combo)
    view.setItemDelegate(QStyledItemDelegate(view))
    view.setUniformItemSizes(True)
    view.setSpacing(0)
    view.setStyleSheet("""
        QListView {background:#071c40;color:#f1fbff;
            border:2px solid #36c8ff;outline:0px;}
        QListView::item {color:#f1fbff;background:#071c40;
            padding:6px 9px;min-height:27px;}
        QListView::item:hover {background:#164d81;color:white;}
        QListView::item:selected {background:#176eaa;color:#ffffff;}
    """)
    palette=view.palette()
    palette.setColor(QPalette.Base,QColor("#071c40"))
    palette.setColor(QPalette.Text,QColor("#f1fbff"))
    palette.setColor(QPalette.Highlight,QColor("#176eaa"))
    palette.setColor(QPalette.HighlightedText,QColor("#ffffff"))
    view.setPalette(palette)
    combo.setView(view)
    combo.setStyleSheet(
        "QComboBox{background:#051b40;color:#f0faff;"
        "border:1px solid #2ebaf5;border-radius:4px;"
        "padding:4px 6px;min-height:24px;}"
        "QComboBox QAbstractItemView{background:#071c40;"
        "color:#f1fbff;selection-background-color:#176eaa;"
        "selection-color:#ffffff;}"
    )
    combo.setToolTip(combo.toolTip()+
        ("\nLista de opciones de alto contraste" if combo.toolTip() else
         "Lista de opciones de alto contraste"))


def install_review_scrolling(panel):
    """En pantallas de 1366×768 no comprimir/solapar los controles inferiores.

    El desplazamiento afecta solo a la columna de revisión, nunca al audio ni
    al proyecto. En pantallas grandes se expande y la barra no aparece.
    """
    from PySide6.QtWidgets import QScrollArea,QLayout
    from PySide6.QtCore import Qt
    root=panel.layout()
    items=[]
    while root.count():
        items.append(root.takeAt(0))
    content=QWidget(panel)
    column=QVBoxLayout(content)
    column.setContentsMargins(9,7,9,7)
    column.setSpacing(6)
    for item in items:
        if item.widget() is not None:
            column.addWidget(item.widget(),1 if item.widget() is
                             next((area for area in panel.findChildren(QScrollArea)
                                   if area.widget() is panel.container),None) else 0)
        elif item.layout() is not None:
            column.addLayout(item.layout())
        else:
            column.addItem(item)
    list_area=next((area for area in content.findChildren(QScrollArea)
                    if area.widget() is panel.container),None)
    if list_area is not None:
        list_area.setMinimumHeight(222)
        list_area.setMaximumHeight(270)
        # Las seis ondas se mantienen accesibles a la vez; si falta altura,
        # se desplaza la tarjeta completa sin recortar botones ni progresos.
        list_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    outer=QScrollArea(panel)
    outer.setWidgetResizable(True)
    outer.setFrameShape(QFrame.NoFrame)
    outer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    outer.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    content.setMinimumHeight(690)
    outer.setWidget(content)
    outer.setStyleSheet(
        "QScrollArea{background:transparent;border:0px;}"
        "QScrollBar:vertical{background:#041a3a;width:10px;}"
        "QScrollBar::handle:vertical{background:#1462a2;"
        "min-height:38px;border-radius:4px;}")
    root.setContentsMargins(0,0,0,0)
    root.setSpacing(0)
    root.addWidget(outer,1)
    panel._review_outer_scroll=outer
    panel._review_content=content
    panel._review_list_area=list_area
    return outer


def install_separator_scrolling(sep):
    """Scroll vertical del formulario en pantallas pequeñas; sin solapes.

    La versión compacta quitaba el QScrollArea y comprimía el formulario
    al reducir la altura. Restaurarlo después de construir las tarjetas
    mantiene todos los controles y la proporción correcta.
    """
    from PySide6.QtWidgets import QScrollArea,QFrame
    from PySide6.QtCore import Qt
    outer=sep.layout()
    canvas=outer.itemAt(0).widget()
    if canvas is None or isinstance(canvas,QScrollArea):
        return
    assert outer.takeAt(0).widget() is canvas
    scroll=QScrollArea(sep)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setStyleSheet(
        "QScrollArea{background:transparent;border:0px;}"
        "QScrollBar:vertical{background:#041a3a;width:10px;}"
        "QScrollBar::handle:vertical{background:#1462a2;"
        "min-height:32px;border-radius:4px;}")
    scroll.setWidget(canvas)
    outer.addWidget(scroll)
    sep._compact_canvas=canvas
    sep._compact_scroller=scroll
