"""Piano Roll: escucha FluidSynth en tiempo real, SF2 reales, posición y VU PCM."""
from pathlib import Path
from types import SimpleNamespace
import math
import tempfile
import bisect
import mido
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QPen, QPainter, QLinearGradient
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QComboBox,QPushButton,QFileDialog
from soundfont_catalog import presets,system_soundfont
from midi_live_synth import LiveMidiSynth
from midi_to_audio_expanded import GM_GROUPS

from studio_vu_unified import Ballistics,draw_mono_horizontal

class PianoMeter(QWidget):
    """Mantiene su orientación horizontal, escala y posición originales."""
    def __init__(self,channel,parent=None):
        super().__init__(parent)
        self.channel=channel
        self.rms=0.;self.peak=0.
        self._ballistics=Ballistics(1)
        self.setMinimumWidth(195)
        self.setFixedHeight(30)
        self.setToolTip("VU Monitor / Grabación: mismo patrón −60..0 dBFS")
    def set_levels(self,rms,peak):
        self.rms=max(0.,float(rms));self.peak=max(0.,float(peak))
        self._ballistics.feed((self.rms,),(self.peak,))
        self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        draw_mono_horizontal(p,self.rect(),self._ballistics.shown[0],
                             self._ballistics.held[0],self.channel)
        p.end()

class PianoRealtime(QObject):
    error=Signal(str)
    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self.engine=LiveMidiSynth(self)
        self.engine.error.connect(self.error)
        self._scratch=tempfile.TemporaryDirectory(prefix="stemmidi_piano_live_")
        self._midi=Path(self._scratch.name)/"live_notes.mid"
        self._presets={}
        self._rate=SimpleNamespace(currentIndex=lambda:0)
        # Use the configuration of the already integrated synthesis engine
        # as a base, without modifying the settings of MIDI→Audio.
        base=home.midi_to_audio
        keys=("max_polyphony","resampler","reverb","reverb_level","chorus",
            "chorus_level","midi_fx","gain_percent","transpose_semitones",
            "tempo_percent","delay_ms","comp_enabled","comp_threshold","comp_ratio",
            "comp_attack","comp_release","adsr_enabled","adsr_attack","adsr_decay",
            "adsr_sustain","adsr_release","eq_enabled","eq_bass","eq_mid",
            "eq_treble")
        self.config=SimpleNamespace(**{k:getattr(base,k) for k in keys})
        # Evitar heredar un CC64/CC11 fijo desde MIDI→Audio que anule
        # el pedal y la expresión presentes en el MIDI del piano roll.
        self.config.midi_fx=()
        self.config.rate=self._rate
        self.config.soundfont=getattr(base,"soundfont",None)
        self.config.preset_bank=0
        self.config.program_override=None
        self.config.override_channel=None
        self._time_map=[(0.,0)]
        self._ticks=[0]
        self.duration_ticks=0
        self._loaded_preview=None

    @property
    def running(self):
        return self.engine.running
    @property
    def position_ms(self):
        return self.engine.position_ms

    def soundfont(self):
        return self.config.soundfont or system_soundfont()

    def select_soundfont(self,source):
        path=Path(source).expanduser().resolve()
        if not path.is_file() or path.suffix.lower()!=".sf2":
            raise ValueError("Selecciona un archivo SF2 válido")
        entries=presets(path)
        if not entries:raise ValueError("El SoundFont no contiene presets reproducibles")
        self.config.soundfont=path
        self._presets={}
        for bank,program,name in entries:
            key=(128,"Drums") if bank==128 else (bank,program//8)
            self._presets.setdefault(key,[]).append((bank,program,name))
        # If running, change only the SF2/program; no forced new playback.
        if self.running:
            self.engine.update_settings()
        return self._presets

    def catalog(self):
        path=self.soundfont()
        if path is None:return {}
        if not self._presets:
            self.select_soundfont(path)
        return self._presets

    def _active_track_channel(self):
        editor=self.home.workbench.piano
        if editor.midi is None or not editor.tracks:return None
        track=editor.tracks[editor.track_index]
        channels=sorted({n["channel"] for n in track["notes"]})
        if not channels:channels=track.get("channels",[])
        return next((c for c in channels if c!=9),
                    9 if self.config.preset_bank==128 else
                    (channels[0] if channels else None))

    def select_preset(self,bank,program):
        self.config.preset_bank=int(bank)
        self.config.program_override=int(program)
        # Nunca aplicar un programa a los 15 canales: los acompañamientos
        # con programa propio deben conservar su timbre.
        self.config.override_channel=self._active_track_channel()
        if self.running:self.engine.update_settings()

    def apply_instrument_to_midi(self):
        """Escribir el programa REAL en el editor, con Deshacer disponible.
        El archivo original sigue intacto hasta Añadir MIDI a la lista.
        """
        e=self.home.workbench.piano
        if e.midi is None or not e.tracks:
            self.error.emit("Selecciona primero un MIDI")
            return False
        bank=self.config.preset_bank
        program=self.config.program_override
        if program is None:
            self.error.emit("Elige primero un instrumento del SoundFont")
            return False
        e.snapshot()
        import mido
        changed=False
        # Aplicar únicamente a la pista activa; las otras no deben
        # convertirse al mismo preset de manera silenciosa.
        for track in (e.tracks[e.track_index],):
            channels=sorted({n["channel"] for n in track["notes"]})
            if not channels:continue
            if bank==128:
                # Canal 10 para kits de batería, sin inventar notas.
                for note in track["notes"]:
                    note["channel"]=9
                targets=[9]
            else:
                targets=[ch for ch in channels if ch!=9]
            if not targets:continue
            # Retirar únicamente los cambios del mismo programa/canales:
            # evitar que un program_change posterior restaure otro instrumento.
            track["other"]=[
                (tick,msg) for tick,msg in track["other"]
                if not (msg.type=="program_change"
                        and getattr(msg,"channel",-1) in targets)
                and not (msg.type=="control_change"
                         and getattr(msg,"channel",-1) in targets
                         and msg.control in (0,32))]
            for channel in targets:
                if bank not in (0,128):
                    # SF2 bank numbering: MSB/LSB.
                    track["other"].append((0,mido.Message(
                         "control_change",channel=channel,control=0,
                         value=min(127,bank//128),time=0)))
                    track["other"].append((0,mido.Message(
                         "control_change",channel=channel,control=32,
                         value=bank%128,time=0)))
                track["other"].append((0,mido.Message("program_change",
                                    channel=channel,program=program,time=0)))
            track["program"]=program
            track["channels"]=sorted({n["channel"] for n in track["notes"]})
            changed=True
        if not changed:
            self.error.emit("El MIDI no contiene notas compatibles con el instrumento")
            return False
        e.dirty=True
        e.update_track_list()
        e.redraw()  # Emite notesChanged y actualiza la vista en Inicio
        return True

    def _make_playback_file(self):
        from piano_roll import export_file
        e=self.home.workbench.piano
        if e.midi is None or not e.tracks:return None
        if not any(t["notes"] for t in e.tracks):return None
        export_file(e.midi,e.tracks,self._midi)
        return self._midi

    def _build_time_map(self,source):
        f=mido.MidiFile(str(source))
        tpb=f.ticks_per_beat
        ticks=0;tempo=500000;seconds=0.
        points=[(0.,0)]
        for msg in mido.merge_tracks(f.tracks):
            ticks+=msg.time
            seconds+=mido.tick2second(msg.time,tpb,tempo)
            if msg.type=="set_tempo":
                points.append((seconds,ticks))
                tempo=msg.tempo
        # Explicit per-segment tick/sec conversion; playback position is
        # from FluidSynth's monotonic timeline, not estimated from note count.
        self._map=[]
        ticks=0;tempo=500000;seconds=0.
        self._map.append((0.,0,tempo))
        for msg in mido.merge_tracks(f.tracks):
            seconds+=mido.tick2second(msg.time,tpb,tempo)
            ticks+=msg.time
            if msg.type=="set_tempo":
                tempo=msg.tempo
                self._map.append((seconds,ticks,tempo))
        self._seconds=[a for a,_,_ in self._map]
        self.duration_ticks=max(ticks,max((n["end"] for tr in self.home.workbench.piano.tracks
                                           for n in tr["notes"]),default=0))
        self._ticks_per_beat=tpb

    def position_tick(self):
        if not self.running:return 0
        seconds=self.engine.position_ms/1000*self.engine._tempo
        index=max(0,bisect.bisect_right(self._seconds,seconds)-1)
        sec,tick,tempo=self._map[index]
        return min(self.duration_ticks,max(0,
           int(tick+(seconds-sec)*1_000_000*self._ticks_per_beat/tempo)))

    def play(self):
        if self.running:
            if self.engine.paused:self.engine.pause()
            return True
        path=self._make_playback_file()
        if path is None:
            self.error.emit("Selecciona un MIDI que contenga notas")
            return False
        self._build_time_map(path)
        # Instrumento escogido solo sobre el canal de la pista activa.
        # Los demás canales se reproducen con el program_change del MIDI.
        self.config.override_channel=self._active_track_channel()
        # Stop generic output to prevent hearing a second accompaniment.
        self.home.player.stop()
        self.home._sep_listen.stop()
        return self.engine.start(path,self.config)

    def pause(self):
        if self.running:self.engine.pause()
    def stop(self):
        self.engine.stop()
    def seek(self,fraction):
        if self.running:self.engine.seek(int(self.engine.duration_ms*max(0.,min(1.,fraction))))

    def seek_tick(self,tick):
        """Cambiar de posición sin interrumpir la síntesis SF2 activa."""
        e=self.home.workbench.piano
        if e.midi is None:return
        if self.running:
            seconds=e.tick_to_seconds(max(0,int(tick)))
            speed=max(.01,float(self.engine._tempo))
            self.engine.seek(round(seconds*1000/speed))
    def close(self):
        self.stop()
        self._scratch.cleanup()
