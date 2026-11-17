"""Real-time MIDI audition for the Mixer file list.

FluidSynth renders notes in one persistent PortAudio stream. Program changes
update the existing synth/active notes; they DO NOT stop, seek, write a WAV or
restart the transport. The original .mid/.kar remains read-only.
"""
from __future__ import annotations
import time
from pathlib import Path
from types import SimpleNamespace

import sounddevice as sd
from PySide6.QtCore import QObject, Signal
from midi_live_synth import LiveMidiSynth
from soundfont_catalog import system_soundfont


class MixerMidiLivePreview(QObject):
    error=Signal(str)
    stateChanged=Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine=LiveMidiSynth(self, stream_factory=self._native_output)
        self.engine.error.connect(self.error.emit)
        self.engine.stateChanged.connect(self.stateChanged.emit)
        self.source=None
        self.instrument=None
        self.last_change_ms=None
        self.config=SimpleNamespace(
            soundfont=system_soundfont(),
            rate=SimpleNamespace(currentIndex=lambda:0),
            tempo_percent=100,
            program_override=None,
            preset_bank=0,
            override_channel=None,
            midi_fx=(),
            gain_percent=100,
            reverb=False,reverb_level=0,
            chorus=False,chorus_level=0,
            eq_enabled=False,eq_bass=0,eq_mid=0,eq_treble=0,
            adsr_enabled=False,adsr_attack=0,adsr_decay=0,
            adsr_sustain=100,adsr_release=0,
            delay_ms=0,
            resampler="c",
            comp_enabled=False,comp_threshold=-18,comp_ratio=3,
            comp_attack=20,comp_release=250,
            max_polyphony=96,transpose_semitones=0,
        )

    @staticmethod
    def _native_output(**kwargs):
        # Original LiveMidiSynth uses device="pulse" for Debian/PipeWire.
        # The Mac has only CoreAudio: its real stereo output is the system
        # default sounddevice output; Pulse does not exist on macOS.
        kwargs.pop("device",None)
        # Match the output already selected for the audio preview in Qt.
        # On this Mac, Qt prefers stereo USB Audio while PortAudio defaults to
        # the 4-channel GM: not matching would silently change speakers.
        try:
            from preview_player import AudioRoute
            selected=AudioRoute.current_id()
            selected_name=next(
                (d.description() for d in AudioRoute.devices()
                 if AudioRoute._id(d)==selected),None)
            if selected_name:
                for index,device in enumerate(sd.query_devices()):
                    name=str(device["name"])
                    if (device["max_output_channels"]>=2 and
                            (name.casefold()==selected_name.casefold() or
                             name.casefold() in selected_name.casefold() or
                             selected_name.casefold() in name.casefold())):
                        kwargs["device"]=index
                        break
        except (OSError,RuntimeError,ValueError,AttributeError):
            pass
        kwargs["latency"]="low"
        return sd.OutputStream(**kwargs)

    @property
    def running(self):
        return self.engine.running

    @property
    def paused(self):
        return self.engine.paused

    @property
    def duration_ms(self):
        return self.engine.duration_ms

    @property
    def position_ms(self):
        return self.engine.position_ms

    def play(self, midi_file, instrument=None):
        midi=Path(midi_file).expanduser().resolve()
        if not midi.is_file() or midi.suffix.lower() not in (".mid",".midi",".kar"):
            self.error.emit("El archivo MIDI no está disponible")
            return False
        if self.running and self.source==midi:
            if self.instrument!=instrument:
                self.change_instrument(instrument)
            if self.paused:self.engine.pause()
            return True
        self.config.soundfont=system_soundfont()
        if self.config.soundfont is None:
            self.error.emit("No se encuentra el SoundFont GM")
            return False
        bank,program=(instrument if instrument is not None else (0,None))
        self.config.preset_bank=int(bank)
        self.config.program_override=(int(program) if program is not None else None)
        self.config.override_channel=None
        if not self.engine.start(midi,self.config,original=False):
            self.source=None
            return False
        self.source=midi
        self.instrument=instrument
        return True

    def change_instrument(self,instrument):
        """Hot-swap the patch without stopping or moving the playback clock."""
        if instrument is not None:
            try:instrument=(int(instrument[0]),int(instrument[1]))
            except (ValueError,TypeError,IndexError):
                return False
        if self.instrument==instrument:return True
        self.instrument=instrument
        if not self.running:
            bank,program=instrument if instrument is not None else (0,None)
            self.config.preset_bank=bank
            self.config.program_override=program
            return True
        start=time.perf_counter()
        if instrument is None:
            self._restore_original_programs()
        else:
            bank,program=instrument
            self.config.preset_bank=bank
            self.config.program_override=program
            self.engine.update_settings()
        self.last_change_ms=(time.perf_counter()-start)*1000
        return True

    def _restore_original_programs(self):
        engine=self.engine
        self.config.program_override=None
        self.config.preset_bank=0
        # Capture the original bank/program at the EXACT current MIDI clock.
        # Do not call seek(): seek would interrupt playback and drop active notes.
        original=[(0,0) for _ in range(16)]
        msb=[0]*16
        lsb=[0]*16
        for _at,msg in engine._events[:engine._index]:
            ch=getattr(msg,"channel",None)
            if ch is None:continue
            if msg.type=="control_change":
                if msg.control==0:msb[ch]=msg.value
                elif msg.control==32:lsb[ch]=msg.value
            elif msg.type=="program_change":
                original[ch]=(msb[ch]*128+lsb[ch],msg.program)
        for channel,(bank,program) in enumerate(original):
            if channel==9:continue
            engine._lib.fluid_synth_all_sounds_off(engine._synth,channel)
            engine._program(channel,program,bank)
            for (ch,_note),(pitch,velocity) in tuple(engine._active.items()):
                if ch==channel:
                    engine._lib.fluid_synth_noteon(engine._synth,channel,pitch,velocity)
        # Configuration cache must match new mode; never force tempo re-anchor.
        engine.update_settings()

    def pause(self):
        if self.running:self.engine.pause()

    def seek(self,position_ms):
        return self.engine.seek(position_ms) if self.running else False

    def stop(self):
        self.engine.stop()
        self.source=None
        self.instrument=None

    def cleanup(self):
        self.stop()
