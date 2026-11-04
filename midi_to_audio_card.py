"""Convertidor MIDI -> audio para Inicio, integrado con los proyectos.

Renderiza MIDI con TiMidity y codifica con FFmpeg: procesos reales,
cancelación segura, porcentajes sólo cuando FFmpeg informa tiempo procesado.
Los resultados se publican primero en temporales/resultados hasta Guardar.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QPushButton, QProgressBar, QFileDialog)
from audio_import import probe_audio
from task_staging import unique_dest

MIDI_EXT={".mid",".midi",".kar"}
FORMATS={"WAV 24 bits":(".wav",["-c:a","pcm_s24le"]),
         "WAV 16 bits":(".wav",["-c:a","pcm_s16le"]),
         "FLAC":(".flac",["-c:a","flac"]),
         "MP3 320 kb/s":(".mp3",["-c:a","libmp3lame","-b:a","320k"])}

class MidiToAudioCard(QWidget):
    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self._project=None
        self._source=None
        self._proc=None
        self._stage=""
        self._tmp_render=None
        self._tmp_encoded=None
        self._dest=None
        self._duration=0.
        self._cancelled=False
        self._progress_tail=""
        self._last_percent=0
        self._external=None
        self._additional_sources=[]
        self._current_project=None
        self._tmp_sf2_cfg=None
        self._tmp_midi_render=None
        self._tmp_midi_quant=None
        self.quant_grid=None
        self.quant_strength=100
        self.quant_swing=50
        self.quant_ends=False
        self.program_override=None   # None significa conservar programas MIDI
        self.preset_bank=0  # banco SF2 real, 128 reservado para kits
        self.override_channel=None   # None = todos melódicos; canal 10 intacto
        self.max_polyphony=96
        self.resampler="c"
        self.reverb_level=42
        self.chorus_level=42
        self.midi_fx=()  # tuplas (controlador, valor), histórico inmutable
        self.delay_ms=0
        self.comp_enabled=False
        self.comp_threshold=-18
        self.comp_ratio=3
        self.comp_attack=20
        self.comp_release=250
        self.adsr_enabled=False
        self.adsr_attack=0
        self.adsr_decay=0
        self.adsr_sustain=100
        self.adsr_release=0
        self.eq_enabled=False
        self.eq_bass=0
        self.eq_mid=0
        self.eq_treble=0
        self._tmp_midi_adsr=None
        self._tmp_offline_cfg=None
        self._preview_adsr=None
        from midi_to_audio_engine_options import setup_advanced
        setup_advanced(self)
        from PySide6.QtCore import QProcess
        from preview_player import PreviewPlayer
        self._preview_proc=None
        self._preview_wave=None
        self._preview_midi_source=None
        self._preview_quant=None
        self._preview_soundfont_cfg=None
        self._preview_original=False
        self.render_preview=PreviewPlayer("MIDI AUDIO · PREESCUCHA",self)
        self.render_preview.hide()
        from midi_live_synth import LiveMidiSynth
        self.live_midi=LiveMidiSynth(self)
        self.live_midi.error.connect(lambda message:self.status.setText(message))
        self._preview_live_quant=None
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(3)
        self.input=QComboBox(self)
        self.input.setObjectName("midiToAudioSource")
        self.input.setToolTip("MIDI generado, editado o importado del proyecto activo")
        layout.addWidget(self.input)
        row=QHBoxLayout()
        row.setSpacing(3)
        self.format=QComboBox(self)
        self.format.setObjectName("midiToAudioFormat")
        self.format.addItems(FORMATS)
        self.format.setToolTip("Renderizar a WAV, FLAC o MP3 mediante síntesis MIDI real")
        self.rate=QComboBox(self)
        self.rate.addItems(["44.1 kHz","48 kHz"])
        self.rate.setCurrentIndex(0)  # 44,1 kHz por defecto; 48 kHz opcional
        self.rate.setToolTip("44,1 kHz para música; 48 kHz para vídeo u otros flujos de audio")
        row.addWidget(self.format,2)
        row.addWidget(self.rate,1)
        layout.addLayout(row)
        controls=QHBoxLayout()
        controls.setSpacing(3)
        self.convert=QPushButton("Convertir",self)
        self.convert.setObjectName("midiToAudioConvert")
        self.convert.setToolTip("Iniciar síntesis MIDI y codificación real")
        self.convert.clicked.connect(self.start)
        self.cancel=QPushButton("■ Cancelar",self)
        self.cancel.setObjectName("midiToAudioCancel")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.stop)
        self.choose=QPushButton("Abrir…",self)
        self.choose.setObjectName("midiToAudioChoose")
        self.choose.clicked.connect(self.choose_file)
        self.choose.setToolTip("Elegir un MIDI externo, sin incorporarlo al proyecto")
        controls.addWidget(self.convert,2)
        controls.addWidget(self.cancel,1)
        controls.addWidget(self.choose,1)
        layout.addLayout(controls)
        self.progress=QProgressBar(self)
        self.progress.setObjectName("midiToAudioProgress")
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        self.progress.setFormat("0 %")
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(13)
        layout.addWidget(self.progress)
        self.status=QLabel("Selecciona MIDI · salida temporal",self)
        self.status.setObjectName("muted")
        self.status.setWordWrap(False)
        self.status.setMinimumHeight(17)
        self.status.setToolTip("El trabajo se guarda definitivamente al pulsar Guardar proyecto")
        layout.addWidget(self.status)
        self._timer=QTimer(self)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.input.currentIndexChanged.connect(lambda *_:self._source_changed())
        self.refresh(force=True)

    def _project_path(self):
        path=getattr(self.home.main,"project_dir",None)
        return Path(path).resolve() if path else None

    def refresh(self,force=False):
        # Nunca arrastrar el catálogo de otro proyecto ni detener un trabajo
        # desde un temporizador; cierre/cambio con proceso se bloquea arriba.
        project=self._project_path()
        if self._proc is not None:return
        if not force and project==self._project and self.input.count()>0:
            return
        old=self.input.currentData()
        if self._project is not None and project!=self._project:
            # Un MIDI externo abierto bajo otro proyecto no se hereda.
            self._external=None
            self._additional_sources.clear()
        self._project=project
        external=self._external if self._external and self._external.is_file() else None
        sources=[]
        transport=getattr(self.home.main,"studio_midi_transport",None)
        if transport is not None:
            transport.refresh_catalog(force=True)
            sources=transport._inventory()
        if external is not None:sources.append(external)
        sources.extend(p for p in self._additional_sources if p.is_file())
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.input):
            self.input.clear()
            for source in dict.fromkeys(sources):
                self.input.addItem(Path(source).name,str(source))
                self.input.setItemData(self.input.count()-1,str(source),Qt.ToolTipRole)
            if old:
                idx=self.input.findData(old)
                if idx>=0:self.input.setCurrentIndex(idx)
        self.convert.setEnabled(bool(project and project.is_dir() and self.input.count()))
        self.choose.setEnabled(bool(project and project.is_dir()))
        self.status.setText(
            f"{self.input.count()} MIDI disponibles · temporal hasta guardar"
            if project and self.input.count() else "Selecciona un MIDI del proyecto")

    def _source_changed(self):
        if self._proc is not None:return
        expanded=getattr(self,"expanded_view",None)
        if expanded is not None:expanded.sync_selected_midi()

    def select_source(self,path):
        if self._proc is not None:return False
        try:
            selected=Path(path).expanduser().resolve()
            if not selected.is_file() or selected.suffix.lower() not in MIDI_EXT:
                return False
        except (OSError,ValueError,TypeError):return False
        self._external=selected
        if selected not in self._additional_sources:
            self._additional_sources.append(selected)
        self.refresh(force=True)
        index=self.input.findData(str(selected))
        if index<0:return False
        self.input.setCurrentIndex(index)
        self._source_changed()
        return True

    def choose_file(self):
        if self._proc is not None:return
        directory=self._project or Path.home()
        path,_=QFileDialog.getOpenFileName(self,"Elegir MIDI",str(directory),
                                             "MIDI (*.mid *.midi *.kar)")
        if path:self.select_source(path)

    def _temp_path(self,ext):
        fd,path=tempfile.mkstemp(prefix="_midi_audio_",suffix=ext,
                                dir=str(self._current_project/"temporales"))
        os.close(fd)
        return Path(path)

    def start(self):
        if self._proc is not None:return False
        self.stop_preview()
        self.render_preview.clear()
        self._release_preview_files()
        project=self._project_path()
        source=self.input.currentData()
        if not project or not project.is_dir() or not source:return False
        path=Path(source).resolve()
        if not path.is_file() or path.suffix.lower() not in MIDI_EXT:return False
        # Comprobación previa de validez MIDI, sin alterar el original.
        try:
            import mido
            midi=mido.MidiFile(path)
            if not any(msg.type=="note_on" and msg.velocity>0 for tr in midi.tracks for msg in tr):
                raise ValueError("El archivo no contiene notas MIDI")
        except (OSError,ValueError,EOFError) as exc:
            self.status.setText("MIDI no válido: "+str(exc)[:65])
            return False
        from midi_to_audio_engine_options import validate_name
        try:output_name=validate_name(self.output_basename,path.stem+"_MIDI_audio")
        except ValueError as exc:
            self.status.setText(str(exc))
            return False
        if self.soundfont is not None and not self.soundfont.is_file():
            self.status.setText("Banco SF2 no disponible")
            return False
        if not (project/"temporales").is_dir():
            self.status.setText("No existe la carpeta temporal del proyecto")
            return False
        if not (project/"temporales"/"resultados").is_dir():
            (project/"temporales"/"resultados").mkdir(parents=True)
        ext,_=FORMATS[self.format.currentText()]
        self._current_project=project
        # El nombre de salida no pisa archivos previos (ni pendientes).
        name=output_name+ext
        self._dest=unique_dest(project/"temporales"/"resultados",name)
        self._tmp_render=self._temp_path(".wav")
        self._tmp_encoded=self._temp_path(ext)
        self._source=path
        # El render final debe usar EXACTAMENTE el mismo sintetizador que
        # la escucha B, no TiMidity. Solo aplicar cuantización en la fuente
        # temporal; programa, SF2 y FX se aplican una vez en FluidSynth.
        try:
            from midi_quant_render import quantize_copy
            self._tmp_midi_quant=quantize_copy(
                path,project,self.quant_grid,self.quant_strength,
                self.quant_swing,self.quant_ends)
            self._tmp_midi_render=self._tmp_midi_quant
            self._tmp_offline_cfg=self._temp_path(".json")
            import json
            fields=("program_override","preset_bank","override_channel",
                "midi_fx","gain_percent","reverb","reverb_level","chorus",
                "chorus_level","delay_ms","resampler","comp_enabled",
                "comp_threshold","comp_ratio","comp_attack","comp_release",
                "eq_enabled","eq_bass","eq_mid","eq_treble","adsr_enabled",
                "adsr_attack","adsr_decay","adsr_sustain","adsr_release",
                "max_polyphony","tempo_percent","transpose_semitones")
            settings={key:getattr(self,key) for key in fields}
            settings["soundfont"]=str(self.soundfont) if self.soundfont else None
            settings["midi_fx"]=[list(x) for x in self.midi_fx]
            self._tmp_offline_cfg.write_text(json.dumps({
                "source":str(self._tmp_midi_render or path),
                "sample_rate":44100 if self.rate.currentIndex()==0 else 48000,
                "settings":settings}),encoding="utf-8")
        except (ValueError,OSError,TypeError) as exc:
            self._finish(False,"Configuración de síntesis: "+str(exc))
            return False
        self._cancelled=False
        self._stage="synth"
        self._last_percent=0
        self._duration=0.
        self._midi_length=float(midi.length)
        self._estimated_pcm=max(1,int((self._midi_length/max(.5,self.tempo_percent/100)+2.0) *
            (44100 if self.rate.currentIndex()==0 else 48000)*6))
        self.progress.setValue(0)
        self.progress.setFormat("0 % · iniciando síntesis PCM")
        self.status.setText("FluidSynth: sintetizando la misma señal que B · FX en directo…")
        self.convert.setEnabled(False)
        self.choose.setEnabled(False)
        self.input.setEnabled(False)
        self.format.setEnabled(False)
        self.rate.setEnabled(False)
        self.cancel.setEnabled(True)
        # En el .deb/PyInstaller relanzamos el propio ejecutable en modo
        # renderizador; en fuentes se usa Python global, sin venv.
        import sys
        self._progress_timer.start()
        if getattr(sys,"frozen",False):
            program=sys.executable
            arguments=["--stemmidi-render",str(self._tmp_offline_cfg),str(self._tmp_render)]
        else:
            program=sys.executable
            arguments=[str(Path(__file__).with_name("midi_offline_render.py")),
                       "--stemmidi-render",str(self._tmp_offline_cfg),str(self._tmp_render)]
        self._launch(program,arguments,"synth")
        self._notify_expanded()
        return True

    def _prepare_render_midi(self,path,project,original=False):
        # Las transformaciones se apilan sobre el MIDI temporal. El original
        # nunca se abre para escritura ni se sobreescribe.
        from midi_quant_render import quantize_copy
        from midi_render_instrument import make_render_midi
        self._tmp_midi_quant=None
        if not original:
            self._tmp_midi_quant=quantize_copy(
                path,project,self.quant_grid,self.quant_strength,
                self.quant_swing,self.quant_ends)
        intermediate=self._tmp_midi_quant or path
        if original:return None
        edited=make_render_midi(intermediate,project,
                                self.program_override,self.override_channel,
                                bank=self.preset_bank,effects=dict(self.midi_fx))
        from midi_adsr_envelope import adsr_copy
        self._tmp_midi_adsr=adsr_copy(edited or intermediate,project,
            self.adsr_attack,self.adsr_decay,self.adsr_sustain,
            self.adsr_release) if self.adsr_enabled else None
        # Nunca devolver el origen como archivo temporal eliminable.
        return self._tmp_midi_adsr or edited or (intermediate if intermediate!=path else None)

    def _release_preview_files(self):
        for name in ("_preview_wave","_preview_midi_source","_preview_soundfont_cfg","_preview_quant","_preview_adsr"):
            path=getattr(self,name,None)
            if path:
                try:Path(path).unlink(missing_ok=True)
                except OSError:pass
            setattr(self,name,None)

    def stop_preview(self):
        if self.live_midi.running:self.live_midi.stop()
        if self._preview_live_quant is not None:
            try:self._preview_live_quant.unlink(missing_ok=True)
            except OSError:pass
            self._preview_live_quant=None
        process=self._preview_proc
        if process is not None:
            self._preview_proc=None
            process.kill()
            process.waitForFinished(800)
            process.deleteLater()
        self.render_preview.stop()
        self.status.setText("Preescucha detenida")
        self._notify_expanded()

    def preview_modified(self,original=False,live=False):
        """Live: FluidSynth con cambios inmediatos. Legacy: TiMidity WAV verificable."""
        if self.busy:return False
        if live:
            source=self.input.currentData()
            project=self._project_path()
            if not source or not project or not Path(source).is_file():return False
            self.stop_preview()
            self.render_preview.stop()
            self._release_preview_files()
            try:
                from midi_quant_render import quantize_copy
                if not original:
                    self._preview_live_quant=quantize_copy(
                        Path(source),project,self.quant_grid,self.quant_strength,
                        self.quant_swing,self.quant_ends)
                midi=self._preview_live_quant or Path(source)
                success=self.live_midi.start(midi,self,original=original)
                if success:
                    self.status.setText("MIDI directo A · original" if original else
                                        "MIDI directo B · instrumentos y efectos en tiempo real")
                else:
                    self.status.setText("No se pudo abrir MIDI directo · revisa salida de audio")
                self._notify_expanded()
                return success
            except (OSError,ValueError) as exc:
                self.status.setText("MIDI directo: "+str(exc))
                self.stop_preview()
                return False
        source=self.input.currentData()
        project=self._project_path()
        if not source or not project:return False
        path=Path(source)
        if not path.is_file():return False
        self.stop_preview()
        self.render_preview.clear()
        self._release_preview_files()
        from midi_quant_render import quantize_copy
        from midi_render_instrument import make_render_midi
        from midi_to_audio_engine_options import timidity_options
        self._current_project=project
        self._preview_original=bool(original)
        try:
            self._preview_quant=quantize_copy(
                path,project,self.quant_grid,self.quant_strength,
                self.quant_swing,self.quant_ends) if not original else None
            intermediate=self._preview_quant or path
            self._preview_midi_source=make_render_midi(
                intermediate,project,self.program_override,self.override_channel,
                bank=self.preset_bank,effects=dict(self.midi_fx)
            ) if not original else None
            midi_input=self._preview_midi_source or intermediate
            from midi_adsr_envelope import adsr_copy
            self._preview_adsr=adsr_copy(midi_input,project,
                self.adsr_attack,self.adsr_decay,self.adsr_sustain,
                self.adsr_release) if self.adsr_enabled and not original else None
            midi_input=self._preview_adsr or midi_input
            self._preview_wave=self._temp_path(".wav")
            self.render_preview.set_preview_eq(*(
                (self.eq_bass,self.eq_mid,self.eq_treble)
                if self.eq_enabled and not original else (0,0,0)))
            self.render_preview.set_preview_compressor(
                self.comp_enabled and not original,self.comp_threshold,
                self.comp_ratio,self.comp_attack,self.comp_release)
            options=timidity_options(self)
            self._preview_soundfont_cfg=self._tmp_sf2_cfg
            self._tmp_sf2_cfg=None
            proc=QProcess(self)
            self._preview_proc=proc
            proc.finished.connect(lambda rc,status,p=proc:self._preview_finished(p,rc,status))
            proc.errorOccurred.connect(lambda error,p=proc:self._preview_error(p,error))
            proc.start("timidity",[
                str(midi_input),"-Ow","-o",str(self._preview_wave),*options])
            self.status.setText("Preescucha A (original)…" if original
                else "Preescucha B (ajustes + cuantización)…")
            self._notify_expanded()
            return True
        except (ValueError,OSError) as exc:
            self.status.setText("Error de preescucha: "+str(exc))
            self._release_preview_files()
            self._cleanup_temps()
            self._current_project=None
            return False

    def _preview_error(self,process,error):
        if process is self._preview_proc and error==QProcess.FailedToStart:
            self.status.setText("TiMidity no disponible para preescuchar")
            self._preview_proc=None
            self._release_preview_files()
            self._notify_expanded()

    def _preview_finished(self,process,code,status):
        if process is not self._preview_proc:return
        self._preview_proc=None
        from PySide6.QtCore import QProcess
        process.deleteLater()
        if code!=0 or status!=QProcess.NormalExit:
            self.status.setText("Error al sintetizar la preescucha")
            self._release_preview_files()
            self._notify_expanded()
            return
        try:
            info=probe_audio(self._preview_wave)
            assert info["duration"]>0
        except (OSError,KeyError,ValueError,AssertionError):
            self.status.setText("Preescucha sin audio válido")
            self._release_preview_files()
            self._notify_expanded()
            return
        # La onda permanece temporal mientras se reproduce. Ningún
        # resultado entra en Guardar hasta pulsar Convertir.
        self.render_preview.load(self._preview_wave,autoplay=True)
        self.status.setText("A · Original" if self._preview_original
                            else "B · Ajustes y cuantización")
        self._notify_expanded()

    def _launch(self,program,args,stage):
        proc=QProcess(self)
        proc.setProgram(program)
        proc.setArguments(args)
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        self._proc=proc
        self._stage=stage
        proc.finished.connect(lambda rc,status,p=proc:self._finished(p,rc,status))
        proc.errorOccurred.connect(lambda error,p=proc:self._process_error(p,error))
        if stage=="encode":
            proc.readyReadStandardOutput.connect(lambda p=proc:self._read_ffmpeg_progress(p))
        proc.start()

    def _process_error(self,proc,error):
        if proc is self._proc and error==QProcess.FailedToStart:
            self._finish(False,"Motor no disponible: "+proc.errorString())

    def _read_ffmpeg_progress(self,proc):
        if proc is not self._proc:return
        data=self._progress_tail+bytes(proc.readAllStandardOutput()).decode(
            "utf-8","replace")
        lines=data.split("\n")
        self._progress_tail=lines.pop()
        for row in lines:
            key,sep,value=row.strip().partition("=")
            if sep and key in ("out_time_ms","out_time_us") and self._duration>0:
                try:seconds=int(value)/1e6
                except ValueError:continue
                real=max(70,min(99,70+int(29*seconds/self._duration)))
                if real>self._last_percent:
                    self._last_percent=real
                    self.progress.setValue(real)
                    self.progress.setFormat("%p % · audio codificado")

    def _finished(self,proc,rc,status):
        if proc is not self._proc:return
        if self._stage=="encode":self._read_ffmpeg_progress(proc)
        self._proc=None
        proc.deleteLater()
        if self._cancelled:
            self._finish(False,"Conversión cancelada; MIDI original intacto")
            return
        if rc!=0 or status!=QProcess.NormalExit:
            error=bytes(proc.readAllStandardError()).decode("utf-8","replace")
            self._finish(False,"Falló el motor: "+(error.strip()[-90:] or str(rc)))
            return
        if self._stage=="synth":
            self._progress_timer.stop()
            try:
                info=probe_audio(self._tmp_render)
                self._duration=float(info["duration"])
                if self._duration<=0:raise ValueError("Audio sin duración")
            except (ValueError,OSError,KeyError) as exc:
                self._finish(False,"Síntesis inválida: "+str(exc))
                return
            ext,codec=FORMATS[self.format.currentText()]
            hz="44100" if self.rate.currentIndex()==0 else "48000"
            self._progress_tail=""
            self._last_percent=0
            self.progress.setValue(70)
            self.progress.setFormat("Codificando · 70 %")
            self.status.setText("FFmpeg: codificando audio…")
            from midi_to_audio_engine_options import final_audio_options
            self._launch("ffmpeg",[
                "-hide_banner","-nostdin","-loglevel","error",
                "-progress","pipe:1","-nostats","-y",
                "-i",str(self._tmp_render),"-vn","-ar",hz,
                *final_audio_options(self,already_processed=True),
                *codec,str(self._tmp_encoded)],"encode")
            self._notify_expanded()
            return
        try:
            info=probe_audio(self._tmp_encoded)
            if float(info["duration"])<=0 or self._tmp_encoded.stat().st_size<=128:
                raise ValueError("Archivo de audio vacío")
            if self._dest.exists():raise FileExistsError("El destino ya existe")
            os.replace(self._tmp_encoded,self._dest)
        except (OSError,ValueError,KeyError) as exc:
            self._finish(False,"No se confirmó la conversión: "+str(exc))
            return
        self.progress.setValue(100)
        self.progress.setFormat("100 % · archivo verificado")
        finished_project=self._current_project
        self._finish(True,"Generado: "+self._dest.name+" · pendiente de guardar")
        # Recargar sólo los resultados existentes del proyecto activo.
        if self._project_path()==finished_project:
            # Publicación de resultados de la misma operación, incluso si
            # la tabla de Inicio tenía un catálogo anterior.
            self.home._known_state=None
            self.home.refresh(force=True)
            expanded=getattr(self,"expanded_view",None)
            if expanded is not None:expanded.refresh_outputs()

    def _notify_expanded(self):
        expanded=getattr(self,"expanded_view",None)
        if expanded is not None:expanded.refresh_runtime()

    def _finish(self,ok,message):
        self._progress_timer.stop()
        self._cleanup_temps()
        self._proc=None
        self._stage=""
        self.status.setText(message)
        if not ok:
            self.progress.setValue(0)
            self.progress.setFormat("Cancelado / sin resultado" if self._cancelled else
                                    "Error / sin resultado")
        self.cancel.setEnabled(False)
        self.input.setEnabled(True)
        self.format.setEnabled(True)
        self.rate.setEnabled(True)
        self.choose.setEnabled(True)
        self.convert.setEnabled(bool(self.input.currentData()))
        self._current_project=None
        self.refresh(force=True)
        # La información final permanece visible, no se sobrescribe con
        # el catálogo que se actualiza por temporizador.
        self.status.setText(message)
        self._notify_expanded()

    def _cleanup_temps(self):
        for name in ("_tmp_render","_tmp_encoded","_tmp_sf2_cfg",
                     "_tmp_midi_render","_tmp_midi_quant","_tmp_midi_adsr",
                     "_tmp_offline_cfg"):
            path=getattr(self,name)
            if path and path.exists():
                try:path.unlink()
                except OSError:pass
            setattr(self,name,None)

    def stop(self):
        if self._proc is None:return False
        self._cancelled=True
        self.cancel.setEnabled(False)
        self.status.setText("Cancelando proceso…")
        self._notify_expanded()
        if self._proc.state()!=QProcess.NotRunning:self._proc.kill()
        return True

    def close_cleanup(self):
        self.stop_preview()
        self.render_preview.cleanup()
        self._release_preview_files()
        self._timer.stop()
        self._progress_timer.stop()
        if self._proc is not None:
            # Desvincular antes de matar el proceso: Qt podía emitir
            # finished al destruir la ventana, mientras su lambda
            # intentaba deleteLater() sobre un QProcess ya destruido.
            proc=self._proc
            self._proc=None
            self._cancelled=True
            try:
                proc.finished.disconnect()
                proc.errorOccurred.disconnect()
            except (TypeError,RuntimeError):
                pass
            if proc.state()!=QProcess.NotRunning:
                proc.kill()
                proc.waitForFinished(2500)
            proc.deleteLater()
        self._cleanup_temps()

    @property
    def busy(self):
        return self._proc is not None
