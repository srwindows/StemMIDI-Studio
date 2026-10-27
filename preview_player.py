"""Reproductor integrado de audios originales, stems, mezclas y MIDI.

Utiliza Qt Multimedia para reproducir y desplazar el cursor de escucha.
MIDI se sintetiza mediante TiMidity en una copia WAV temporal en Recuperación;
el archivo original nunca se modifica. En caso de códec Qt incompatible se
decodifica una copia FLAC con FFmpeg en segundo plano.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid
import weakref
import os
import sys
import signal
import time
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QUrl, QTimer, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from audio_import import probe_audio, describe_audio, normalize_command

from studio_paths import workspace_root
ROOT = workspace_root(__file__)
WORK = ROOT / "previsualizaciones_temporales"
MIDI_SUFFIXES = {".mid", ".midi", ".kar"}
OUTPUT_PREFS = ROOT / "salida_audio_preview.json"


class AudioRoute:
    """Destino de audio común a todas las escuchas, sin modificar PipeWire.

    Si Debian apunta por defecto a un dispositivo multicanal (como FANTOM
    Pro de cuatro canales), se prefiere una salida estéreo analógica
    disponible para la reproducción. La elección se puede cambiar en GUI.
    """
    players = weakref.WeakSet()
    controls = weakref.WeakSet()
    selected_id = None
    before_preview = None

    @staticmethod
    def _id(device):
        try:
            return bytes(device.id()).decode("utf-8", "replace")
        except (TypeError,AttributeError):
            return ""

    @classmethod
    def devices(cls):
        return list(QMediaDevices.audioOutputs())

    @classmethod
    def recommended_id(cls):
        devices=cls.devices()
        if not devices:
            return None
        preferred=QMediaDevices.defaultAudioOutput()
        if cls._id(preferred) and preferred.preferredFormat().channelCount() in (1,2):
            return cls._id(preferred)
        stereo=[d for d in devices if d.preferredFormat().channelCount()==2]
        analog=[d for d in stereo if "analog" in cls._id(d).lower()
                or "analóg" in d.description().lower()]
        return cls._id((analog or stereo or devices)[0])

    @classmethod
    def current_id(cls):
        available={cls._id(device) for device in cls.devices()}
        if cls.selected_id in available:
            return cls.selected_id
        try:
            obj=json.loads(OUTPUT_PREFS.read_text(encoding="utf-8"))
            saved=obj.get("device_id")
            if saved in available:
                cls.selected_id=saved
                return saved
        except (OSError,ValueError,TypeError):
            pass
        cls.selected_id=cls.recommended_id()
        return cls.selected_id

    @classmethod
    def choose(cls,ident,persist=True):
        options={cls._id(device):device for device in cls.devices()}
        if ident not in options:
            return False
        cls.selected_id=ident
        if persist:
            try:
                OUTPUT_PREFS.write_text(json.dumps({"device_id":ident},
                    ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            except OSError:
                pass
        for preview in list(cls.players):
            try:
                preview.apply_output_device(options[ident])
                preview.sync_output_selector(ident)
            except RuntimeError:
                pass
        for control in list(cls.controls):
            try:
                index=control.findData(ident)
                if index>=0:
                    blocked=control.blockSignals(True)
                    control.setCurrentIndex(index)
                    control.blockSignals(blocked)
            except RuntimeError:
                pass
        return True

    @classmethod
    def register_control(cls,control):
        cls.controls.add(control)
        blocked=control.blockSignals(True)
        control.clear()
        for device in cls.devices():
            control.addItem(device.description(),cls._id(device))
        index=control.findData(cls.current_id())
        if index>=0:control.setCurrentIndex(index)
        control.blockSignals(blocked)
        control.currentIndexChanged.connect(
            lambda index:cls.choose(control.itemData(index)) if index>=0 else None)


def timecode(ms):
    seconds = max(0, int(ms) // 1000)
    hours, tail = divmod(seconds, 3600)
    minutes, secs = divmod(tail, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}" if hours else f"{minutes:02}:{secs:02}"


class PreviewPlayer(QFrame):
    """Control de previsualización reutilizable, con transporte y volumen."""

    fileLoaded = Signal(str)
    error = Signal(str)
    playStateChanged = Signal(bool)

    def __init__(self, title="PREVISUALIZACIÓN", parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._origin = None
        self._prepared = None
        self._temp_files = []
        self._render = None
        self._pending_play = False
        self._fallback_attempted = False
        self._dragging = False
        self._closing = False
        self._generation = 0
        self._play_process = None
        self._native_qt = sys.platform in ("win32","darwin")
        self._qt_active = False
        self._paused = False
        self._duration_ms = 0
        self._anchor_ms = 0
        self._anchor_time = 0.0
        self._current_ms = 0
        # Ecualizador exclusivo de preescucha; no procesa el archivo origen.
        self._preview_eq=(0,0,0)

        self.output = QAudioOutput(self)
        self.output.setVolume(.85)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        AudioRoute.players.add(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 13)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title_widget = QLabel(title)
        title_widget.setObjectName("section")
        header.addWidget(title_widget)
        header.addStretch()
        self.options_button=QPushButton("Opciones ▾")
        self.options_button.setToolTip("Mostrar u ocultar volumen, velocidad y dispositivo de audio.")
        self.options_button.clicked.connect(self._toggle_compact_details)
        header.addWidget(self.options_button)
        self.detail = QLabel("Sin archivo seleccionado")
        self.detail.setObjectName("muted")
        self.detail.setTextFormat(Qt.PlainText)
        header.addWidget(self.detail)
        layout.addLayout(header)

        self.filename = QLabel("Arrastra o importa un archivo para escucharlo")
        self.filename.setWordWrap(True)
        self.filename.setObjectName("muted")
        self.filename.setTextFormat(Qt.PlainText)
        layout.addWidget(self.filename)

        controls = QHBoxLayout()
        self.play_button = QPushButton("▶ Reproducir")
        self.play_button.setObjectName("primary")
        self.play_button.clicked.connect(self.play_pause)
        controls.addWidget(self.play_button)
        self.stop_button = QPushButton("■ Detener")
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.sliderPressed.connect(self.drag_start)
        self.slider.sliderReleased.connect(self.drag_finish)
        self.slider.sliderMoved.connect(self.update_time_preview)
        controls.addWidget(self.slider, 1)
        self.clock = QLabel("00:00 / 00:00")
        controls.addWidget(self.clock)
        layout.addLayout(controls)
        from playback_vu import MeasuredPlaybackVU
        self._measured_vu=MeasuredPlaybackVU(self,layout)

        extras = QHBoxLayout()
        self.volume_label=QLabel("Volumen")
        extras.addWidget(self.volume_label)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(85)
        self.volume.setMaximumWidth(115)
        self.volume.valueChanged.connect(lambda v:self.output.setVolume(v/100.0))
        extras.addWidget(self.volume)
        extras.addSpacing(10)
        route = QHBoxLayout()
        self.route_label=QLabel("Salida de escucha")
        route.addWidget(self.route_label)
        self.device_choice=QComboBox()
        self.device_choice.setToolTip("Elige dónde se escuchan el audio y los MIDI. "
                        "No modifica el dispositivo predeterminado de Debian.")
        self.device_choice.setMinimumWidth(180)
        self.device_choice.setMaximumWidth(360)
        self.device_choice.currentIndexChanged.connect(self.on_output_changed)
        route.addWidget(self.device_choice,1)
        self.speed_label=QLabel("Velocidad")
        extras.addWidget(self.speed_label)
        self.speed = QComboBox()
        self.speed.addItem("0,75×", .75)
        self.speed.addItem("1,00×", 1.0)
        self.speed.addItem("1,25×", 1.25)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self.change_speed)
        extras.addWidget(self.speed)
        extras.addStretch()
        layout.addLayout(extras)
        self.status = QLabel("Listo")
        self.status.setObjectName("muted")
        self.status.setMaximumWidth(230)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        route.addWidget(self.status)
        layout.addLayout(route)

        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(self.media_error)
        self._ticker=QTimer(self)
        self._ticker.setInterval(150)
        self._ticker.timeout.connect(self._tick_playback)
        self._ticker.start()
        self.volume.sliderReleased.connect(self._on_volume_change)
        self.refresh_output_devices()
        self._update_controls()
        self._compact_active=False
        self._compact_expanded=True

    def set_compact(self,enabled=True):
        """Transporte visible sin ocupar 180 px de altura en cada pestaña.

        Las opciones de dispositivo, volumen y velocidad siguen disponibles
        con un botón, no se eliminan ni se cambia la salida del usuario.
        """
        self._compact_active=bool(enabled)
        self._compact_expanded=not enabled
        self.options_button.setVisible(enabled)
        self._apply_compact()
        return self

    def _toggle_compact_details(self):
        if not self._compact_active:return
        self._compact_expanded=not self._compact_expanded
        self._apply_compact()

    def _apply_compact(self):
        extra=self._compact_expanded or not self._compact_active
        for widget in (self.filename,self.volume_label,self.volume,
                       self.speed_label,self.speed,self.route_label,
                       self.device_choice,self.status):
            widget.setVisible(extra)
        self.options_button.setText("Opciones ▴" if extra else "Opciones ▾")
        self.slider.setMaximumWidth(420 if extra else 280)
        lay=self.layout()
        lay.setContentsMargins(8,5,8,5) if self._compact_active and not extra else lay.setContentsMargins(15,12,15,13)
        lay.setSpacing(3 if self._compact_active and not extra else 7)
        self.updateGeometry()

    def refresh_output_devices(self):
        self.device_choice.blockSignals(True)
        self.device_choice.clear()
        for device in AudioRoute.devices():
            self.device_choice.addItem(device.description(),AudioRoute._id(device))
        ident=AudioRoute.current_id()
        self.sync_output_selector(ident)
        self.device_choice.blockSignals(False)
        if ident:
            AudioRoute.choose(ident,persist=False)
        else:
            self.status.setText("No se encuentra ningún dispositivo de salida de audio")

    def sync_output_selector(self,ident):
        index=self.device_choice.findData(ident)
        if index>=0:
            previous=self.device_choice.blockSignals(True)
            self.device_choice.setCurrentIndex(index)
            self.device_choice.blockSignals(previous)

    def on_output_changed(self,index):
        ident=self.device_choice.itemData(index)
        if ident:
            AudioRoute.choose(ident)

    def apply_output_device(self,device):
        identity=AudioRoute._id(device)
        if AudioRoute._id(self.output.device())==identity:
            return
        was_active=(self._play_process is not None or self._qt_active)
        was_paused=self._paused
        pos=self._position()
        self.output.setDevice(device)
        if was_active:
            self._stop_audio()
            if not was_paused:
                self._start_audio(pos)
            else:
                self._set_clock(pos)
        self.device_choice.setToolTip("Salida: "+device.description())
        if self._origin is None:self.status.setText("Salida seleccionada")

    def exclusive_with(self, other):
        """La reproducción de una pista detiene las otras en la misma zona."""
        self.playStateChanged.connect(lambda playing:other.stop() if playing else None)

    def _update_controls(self):
        exists=self._origin is not None and self._origin.is_file()
        self.play_button.setEnabled(exists and self._render is None)
        self.stop_button.setEnabled(exists or self._render is not None)
        self.slider.setEnabled(exists and self._duration_ms>0)

    def _set_duration(self,ms):
        self._duration_ms=max(0,int(ms))
        self.slider.setRange(0,max(1,self._duration_ms))
        self._set_clock(0)
        self._update_controls()

    def _set_clock(self,ms):
        self._current_ms=max(0,min(int(ms),self._duration_ms or 10**12))
        if not self._dragging:self.slider.setValue(self._current_ms)
        self.clock.setText(f"{timecode(self._current_ms)} / {timecode(self._duration_ms)}")

    def _position(self):
        if self._native_qt and self._qt_active:
            return self.player.position()
        if self._play_process is not None and not self._paused:
            speed=self.speed.currentData() or 1.0
            return min(self._duration_ms or 10**12,
                       self._anchor_ms+round((time.monotonic()-self._anchor_time)*1000*speed))
        return self._current_ms

    def _tick_playback(self):
        if self._native_qt and self._qt_active:
            self._set_clock(self.player.position())
        elif self._play_process is not None and not self._paused:
            self._set_clock(self._position())

    def _stop_audio(self):
        if self._qt_active:
            self._qt_active=False
            self.player.stop()
            self._paused=False
            self.play_button.setText("▶ Reproducir")
            self.playStateChanged.emit(False)
        proc=self._play_process
        self._play_process=None
        was_active=proc is not None
        if proc is not None:
            if proc.state()!=QProcess.NotRunning:
                if self._paused:
                    try:os.kill(proc.processId(),signal.SIGCONT)
                    except (ProcessLookupError,OSError):pass
                proc.terminate()
                if not proc.waitForFinished(200):
                    proc.kill()
                    proc.waitForFinished(300)
            proc.deleteLater()
        self._paused=False
        self.play_button.setText("▶ Reproducir")
        if was_active:self.playStateChanged.emit(False)

    def set_preview_eq(self,bass_db=0,mid_db=0,treble_db=0):
        values=tuple(max(-12,min(12,int(value))) for value in (bass_db,mid_db,treble_db))
        if values==self._preview_eq:return
        self._preview_eq=values
        # FFplay toma los filtros al iniciar; reiniciar en la misma posición
        # solo cuando realmente está reproduciendo, nunca sobre el original.
        if not self._native_qt and self._play_process is not None and not self._paused:
            position=self._position()
            self._stop_audio()
            self._start_audio(position)

    def _start_audio(self,start_ms=0):
        before=AudioRoute.before_preview
        if callable(before):
            before()
        if self._duration_ms and start_ms >= self._duration_ms-100:
            start_ms=0  # Reproducir de nuevo después de llegar al final
        if not self._prepared or not Path(self._prepared).is_file():
            self.status.setText("El audio todavía no está preparado")
            return False
        self._stop_audio()
        if self._native_qt:
            self.player.setSource(QUrl.fromLocalFile(str(self._prepared)))
            self.player.setPlaybackRate(float(self.speed.currentData() or 1.))
            self._qt_active=True
            self._paused=False
            self._anchor_ms=int(start_ms)
            self.player.play()
            if start_ms:
                QTimer.singleShot(100,lambda:self.player.setPosition(int(start_ms))
                    if self._qt_active else None)
            self.play_button.setText("Ⅱ Pausar")
            self.status.setText("Reproduciendo · "+self.device_choice.currentText())
            self.playStateChanged.emit(True)
            self._update_controls()
            return True
        proc=QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        env=QProcessEnvironment.systemEnvironment()
        env.insert("SDL_AUDIODRIVER","pulseaudio")
        sink=AudioRoute.current_id()
        if sink:env.insert("PULSE_SINK",sink)
        proc.setProcessEnvironment(env)
        speed=float(self.speed.currentData() or 1.0)
        args=["-nodisp","-autoexit","-loglevel","error",
              "-volume",str(self.volume.value())]
        if start_ms>0:args+=["-ss",f"{start_ms/1000:.3f}"]
        filters=[]
        mode=getattr(self,"channel_mode",None)
        mode=mode.currentText() if mode is not None else "Estéreo"
        if mode!="Estéreo":
            if getattr(self,"_channel_count",2)<2:
                # Un origen mono no tiene canales izquierdo/derecho separados.
                filters.append("aformat=channel_layouts=mono")
            elif mode=="Mono (L+R)":
                filters.append("pan=mono|c0=0.5*c0+0.5*c1")
            elif mode=="Solo izquierdo":
                filters.append("pan=mono|c0=c0")
            elif mode=="Solo derecho":
                filters.append("pan=mono|c0=c1")
        if speed!=1.0:filters.append(f"atempo={speed:.3f}")
        bass_db,mid_db,treble_db=self._preview_eq
        if bass_db:filters.append(f"bass=g={bass_db}:f=110")
        if mid_db:filters.append(f"equalizer=f=1000:t=q:w=1:g={mid_db}")
        if treble_db:filters.append(f"treble=g={treble_db}:f=4800")
        if any(self._preview_eq):filters.append("alimiter=limit=0.95")
        if filters:args+=["-af",",".join(filters)]
        args+=["-i",str(self._prepared)]
        self._play_process=proc
        self._anchor_ms=int(start_ms)
        self._anchor_time=time.monotonic()
        self._paused=False
        def finished(rc,status):
            if self._play_process is not proc:
                proc.deleteLater();return
            self._play_process=None
            self._paused=False
            self.play_button.setText("▶ Reproducir")
            self._set_clock(self._duration_ms if rc==0 else self._current_ms)
            self.status.setText("Fin de la previsualización" if rc==0
                                else "Falló la salida de audio: "+bytes(proc.readAllStandardOutput()).decode("utf-8","replace")[-150:])
            self.playStateChanged.emit(False)
            proc.deleteLater()
        proc.finished.connect(finished)
        def start_error(error):
            if error != QProcess.FailedToStart or self._play_process is not proc:
                return
            # Qt no emite finished() tras FailedToStart: evitar falsa reproducción.
            self._play_process = None
            self._paused = False
            self.play_button.setText("▶ Reproducir")
            message="FFplay no pudo iniciar: "+proc.errorString()
            self.status.setText(message)
            self.error.emit(message)
            self.playStateChanged.emit(False)
            proc.deleteLater()
            self._update_controls()
        proc.errorOccurred.connect(start_error)
        proc.start("ffplay",args)
        self.play_button.setText("Ⅱ Pausar")
        self.status.setText("Reproduciendo · "+(self.device_choice.currentText() or "Salida predeterminada"))
        self.playStateChanged.emit(True)
        self._update_controls()
        return True

    def _on_volume_change(self):
        if self._native_qt:return
        if self._play_process is not None and not self._paused:
            pos=self._position()
            self._start_audio(pos)

    @property
    def current_file(self):
        return str(self._origin) if self._origin else None

    def load(self, file_path, autoplay=False):
        if not file_path:
            self.clear()
            return False
        path = Path(file_path).expanduser()
        if not path.is_file():
            self.status.setText("El archivo no existe")
            return False
        self._generation += 1
        self._cancel_render()
        self._stop_audio()
        self.player.stop()
        self.player.setSource(QUrl())
        self._delete_temp_files()
        self._set_duration(0)
        self._origin = path.resolve()
        self._measured_vu.load(self._origin)
        self._channel_count=2
        self._prepared = None
        self._fallback_attempted = False
        self._pending_play = autoplay
        self.filename.setText(self._origin.name)
        self.clock.setText("00:00 / 00:00")
        self.slider.setValue(0)
        self.detail.setText(self._origin.suffix.upper().lstrip(".") or "Audio")
        self.status.setText("Preparando archivo…" if autoplay else "Listo para escuchar")
        if self._origin.suffix.lower() in MIDI_SUFFIXES:
            if autoplay:
                self._prepare_midi()
            else:
                self.status.setText("Pulsa Reproducir para sintetizar y escuchar el MIDI")
        else:
            try:
                info = probe_audio(self._origin)
                self._channel_count=info["channels"]
                self.detail.setText(f"{info['codec'].upper()} · {timecode(int(info['duration']*1000))}")
                self._prepared = self._origin
                self._set_duration(round(info["duration"]*1000))
                if autoplay:
                    self._start_audio()
            except ValueError as exc:
                self._origin = None
                self.status.setText(str(exc))
                self.error.emit(str(exc))
                self._update_controls()
                return False
        self.fileLoaded.emit(str(path))
        self._update_controls()
        return True

    def _create_temp(self, suffix):
        # Reproducciones y renders temporales de la sesión ACTIVA:
        # jamás crear archivos de un proyecto nombrado en la raíz global.
        host=self.window()
        project=getattr(host,"project_dir",None)
        target=(Path(project)/"temporales"/"previsualizaciones"
                if project else WORK)
        target.mkdir(parents=True,exist_ok=True)
        path = target / f"vista_{uuid.uuid4().hex}{suffix}"
        self._temp_files.append(path)
        return path

    def _prepare_midi(self):
        path = self._create_temp(".wav")
        self._prepared = None
        self.status.setText("Sintetizando MIDI para escuchar…")
        self._launch_render("timidity", [str(self._origin), "-Ow", "-o", str(path)], path)

    def _launch_render(self, command, args, result):
        generation = self._generation
        job = QProcess(self)
        job.setProcessChannelMode(QProcess.MergedChannels)
        self._render = job

        def done(rc, status):
            if generation != self._generation:
                job.deleteLater()
                return
            output = bytes(job.readAllStandardOutput()).decode("utf-8", "replace")
            self._render = None
            job.deleteLater()
            if rc != 0 or status != QProcess.NormalExit or not result.is_file() or result.stat().st_size < 128:
                self._pending_play = False
                msg = output.strip()[-250:] or "Error preparando el archivo"
                self.status.setText(msg)
                self.error.emit(msg)
            else:
                self._prepared = result
                try:
                    metadata=probe_audio(result)
                    self._set_duration(round(metadata["duration"]*1000))
                except ValueError:
                    self._set_duration(0)
                self.status.setText("Audio preparado")
                if self._pending_play:
                    self._pending_play = False
                    self._start_audio()
            self._update_controls()

        job.finished.connect(done)
        def render_error(error):
            if error != QProcess.FailedToStart or self._render is not job:
                return
            # Sin cierre explícito quedaría bloqueado el botón Reproducir.
            self._render=None
            self._pending_play=False
            message="Motor de previsualización no disponible: "+job.errorString()
            self.status.setText(message)
            self.error.emit(message)
            job.deleteLater()
            self._update_controls()
        job.errorOccurred.connect(render_error)
        job.start(command, args)
        self._update_controls()

    def _fallback_decode(self):
        if self._origin is None or self._fallback_attempted:
            return
        self._fallback_attempted = True
        self.player.stop()
        target = self._create_temp(".flac")
        cmd = normalize_command(self._origin, target)
        self.status.setText("Decodificando para previsualizar…")
        self._pending_play = True
        self._launch_render(cmd[0], cmd[1:], target)

    def play_pause(self):
        if self._origin is None:
            self.status.setText("Selecciona primero un archivo")
            return
        if self._render is not None:
            self._pending_play=True
            return
        if self._origin.suffix.lower() in MIDI_SUFFIXES and self._prepared is None:
            self._pending_play=True
            self._prepare_midi()
            return
        if self._native_qt:
            if not self._qt_active:
                self._start_audio(self._current_ms)
            elif self._paused:
                self.player.play()
                self._paused=False
                self.play_button.setText("Ⅱ Pausar")
                self.playStateChanged.emit(True)
            else:
                self.player.pause()
                self._paused=True
                self._set_clock(self.player.position())
                self.play_button.setText("▶ Continuar")
                self.playStateChanged.emit(False)
            return
        if self._play_process is None:
            self._start_audio(self._current_ms)
            return
        if self._paused:
            try:os.kill(self._play_process.processId(),signal.SIGCONT)
            except (ProcessLookupError,OSError):
                self._stop_audio();return
            self._paused=False
            self._anchor_ms=self._current_ms
            self._anchor_time=time.monotonic()
            self.play_button.setText("Ⅱ Pausar")
            self.status.setText("Reproduciendo")
            self.playStateChanged.emit(True)
        else:
            pos=self._position()
            try:os.kill(self._play_process.processId(),signal.SIGSTOP)
            except (ProcessLookupError,OSError):
                self._stop_audio();return
            self._paused=True
            self._set_clock(pos)
            self.play_button.setText("▶ Continuar")
            self.status.setText("En pausa")
            self.playStateChanged.emit(False)

    def stop(self):
        self._pending_play=False
        if self._render is not None:
            self._cancel_render()
            self.status.setText("Preparación detenida")
        self._stop_audio()
        self.player.stop()
        self._set_clock(0)
        self._update_controls()

    def clear(self):
        self._generation+=1
        self.stop()
        self.player.setSource(QUrl())
        self._delete_temp_files()
        self._origin=None
        self._prepared=None
        self._measured_vu.stop()
        self.filename.setText("Sin archivo seleccionado")
        self.detail.setText("")
        self.status.setText("Listo")
        self._set_duration(0)
        self._update_controls()

    def duration_changed(self,duration):
        # Qt Multimedia solo aporta metadatos; FFplay emite el sonido real.
        pass

    def position_changed(self,position):
        pass

    def drag_start(self):
        self._dragging=True

    def drag_finish(self):
        self._dragging=False
        desired=self.slider.value()
        active=self._play_process is not None or self._qt_active
        paused=self._paused
        if self._native_qt:
            self.player.setPosition(int(desired))
            self._set_clock(desired)
            return
        if active:self._stop_audio()
        self._set_clock(desired)
        if active and not paused:self._start_audio(desired)

    def update_time_preview(self,value):
        self.clock.setText(f"{timecode(value)} / {timecode(self._duration_ms)}")

    def change_speed(self):
        if self._native_qt:
            self.player.setPlaybackRate(float(self.speed.currentData() or 1.))
            return
        if self._play_process is not None:
            pos=self._position()
            paused=self._paused
            self._stop_audio()
            self._set_clock(pos)
            if not paused:self._start_audio(pos)

    def state_changed(self,state):
        pass

    def media_status(self,state):
        if self._native_qt and state==QMediaPlayer.EndOfMedia:
            self._qt_active=False
            self._paused=False
            self._set_clock(self._duration_ms)
            self.play_button.setText("▶ Reproducir")
            self.playStateChanged.emit(False)

    def media_error(self,error,message):
        if self._native_qt and error!=QMediaPlayer.NoError:
            self.status.setText("Error de reproducción multimedia: "+str(message)[:200])
            self.error.emit(str(message))

    def _cancel_render(self):
        if self._render is not None:
            proc = self._render
            self._render = None
            if proc.state() != QProcess.NotRunning:
                proc.terminate()
                if not proc.waitForFinished(500):
                    proc.kill()
                    proc.waitForFinished(800)
            proc.deleteLater()

    def _delete_temp_files(self):
        for temp in self._temp_files:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        self._temp_files.clear()

    def cleanup(self):
        self._measured_vu.stop()
        self._closing = True
        AudioRoute.players.discard(self)
        self._generation += 1
        self._cancel_render()
        self._stop_audio()
        self.player.stop()
        self.player.setSource(QUrl())
        self._delete_temp_files()
        self._origin = None
        self._prepared = None
