"""MIDI live: FluidSynth native synth + PipeWire/PulseAudio via sounddevice.
Not a pre-rendered WAV: program/CC changes update sounding notes immediately.
"""
from __future__ import annotations
import bisect
import ctypes as C
import ctypes.util
import math
import time
import heapq
from pathlib import Path

from PySide6.QtCore import QObject,QTimer,Signal
import mido
import numpy as np
import sounddevice as sd


class LiveMidiSynth(QObject):
    error=Signal(str)
    stateChanged=Signal(bool)

    def __init__(self,parent=None,stream_factory=None):
        super().__init__(parent)
        self._factory=stream_factory or sd.OutputStream
        self._lib=None
        self._settings=None
        self._synth=None
        self._sfid=-1
        self._soundfont=None
        self._stream=None
        self._events=[]
        self._times=[]
        self._index=0
        self._duration_ms=0
        self._position_ms=0
        self._anchor=0.
        self._paused=False
        self._rms=(0.,0.)
        self._peak=(0.,0.)
        self._active={}
        # Estado de banco MIDI por canal (CC0 MSB y CC32 LSB).
        # Se mantiene separado del override de instrumento SF2.
        self._bank_msb=[0]*16
        self._bank_lsb=[0]*16
        self._last_config=None
        self._original=False
        self._card=None
        self._adsr_notes={}
        self._adsr_due=[]
        self._serial=0
        self._eq_coeffs=()
        self._eq_state=[]
        self._eq_chain=((),[])   # atomic snapshot for PortAudio thread
        self._delay_buffer=None
        self._delay_offset=0
        self._compressor=(False,-18,3,20,250)
        self._comp_env=0.0
        self._sample_rate=44100
        self._tempo=1.0
        self._timeline_ms=0
        self._timer=QTimer(self)
        self._timer.setInterval(12)
        self._timer.timeout.connect(self._tick)

    @property
    def running(self):
        return self._stream is not None

    @property
    def paused(self):
        return self._paused

    @property
    def duration_ms(self):
        return self._duration_ms

    @property
    def position_ms(self):
        if self.running and not self._paused:
            return min(self._duration_ms,int((time.monotonic()-self._anchor)*1000))
        return self._position_ms

    @property
    def levels(self):
        return (*self._rms,*self._peak)

    @staticmethod
    def _api():
        library=ctypes.util.find_library('fluidsynth')
        if not library:
            raise RuntimeError("No se encuentra libfluidsynth")
        lib=C.CDLL(library)
        ptr=C.c_void_p
        def bind(name,restype,args):
            f=getattr(lib,name)
            f.restype=restype
            f.argtypes=args
        bind('new_fluid_settings',ptr,[])
        bind('fluid_settings_setnum',C.c_int,[ptr,C.c_char_p,C.c_double])
        bind('fluid_settings_setint',C.c_int,[ptr,C.c_char_p,C.c_int])
        bind('new_fluid_synth',ptr,[ptr])
        bind('fluid_synth_sfload',C.c_int,[ptr,C.c_char_p,C.c_int])
        bind('fluid_synth_sfunload',C.c_int,[ptr,C.c_int,C.c_int])
        bind('fluid_synth_program_select',C.c_int,[ptr,C.c_int,C.c_int,C.c_int,C.c_int])
        bind('fluid_synth_program_reset',C.c_int,[ptr])
        bind('fluid_synth_noteon',C.c_int,[ptr,C.c_int,C.c_int,C.c_int])
        bind('fluid_synth_noteoff',C.c_int,[ptr,C.c_int,C.c_int])
        bind('fluid_synth_cc',C.c_int,[ptr,C.c_int,C.c_int,C.c_int])
        bind('fluid_synth_pitch_bend',C.c_int,[ptr,C.c_int,C.c_int])
        bind('fluid_synth_all_sounds_off',C.c_int,[ptr,C.c_int])
        bind('fluid_synth_set_gen',C.c_int,[ptr,C.c_int,C.c_int,C.c_float])
        bind('fluid_synth_get_gen',C.c_float,[ptr,C.c_int,C.c_int])
        bind('fluid_synth_write_float',C.c_int,[ptr,C.c_int,ptr,C.c_int,C.c_int,ptr,C.c_int,C.c_int])
        bind('fluid_synth_set_gain',None,[ptr,C.c_float])
        bind('fluid_synth_set_polyphony',C.c_int,[ptr,C.c_int])
        bind('fluid_synth_set_interp_method',C.c_int,[ptr,C.c_int,C.c_int])
        bind('fluid_synth_set_reverb_on',None,[ptr,C.c_int,C.c_int])
        bind('fluid_synth_set_chorus_on',None,[ptr,C.c_int,C.c_int])
        bind('fluid_synth_set_reverb_group_level',None,[ptr,C.c_int,C.c_double])
        bind('fluid_synth_set_chorus_group_level',None,[ptr,C.c_int,C.c_double])
        bind('delete_fluid_synth',None,[ptr])
        bind('delete_fluid_settings',None,[ptr])
        return lib

    @staticmethod
    def _timeline(path):
        midi=mido.MidiFile(str(path))
        events=[]
        seconds=0.
        tempo=500000
        for msg in mido.merge_tracks(midi.tracks):
            seconds+=mido.tick2second(msg.time,midi.ticks_per_beat,tempo)
            if msg.type=="set_tempo":
                tempo=msg.tempo
            elif msg.type in ("note_on","note_off","program_change","control_change","pitchwheel","aftertouch","polytouch"):
                events.append((seconds,msg))
        return events,max(seconds,max((x[0] for x in events),default=0))

    def _create_synth(self,path):
        lib=self._api()
        self._lib=lib
        self._settings=lib.new_fluid_settings()
        if not self._settings:raise RuntimeError('FluidSynth: settings no disponibles')
        lib.fluid_settings_setnum(self._settings,b'synth.sample-rate',float(self._sample_rate))
        lib.fluid_settings_setnum(self._settings,b'synth.gain',0.4)
        lib.fluid_settings_setint(self._settings,b'synth.polyphony',256)
        self._synth=lib.new_fluid_synth(self._settings)
        if not self._synth:raise RuntimeError('FluidSynth: no se pudo crear el sintetizador')
        self._load_bank(path)

    def _load_bank(self,path):
        chosen=Path(path).expanduser().resolve()
        if not chosen.is_file() or chosen.suffix.lower()!='.sf2':
            raise ValueError('SoundFont SF2 no disponible: '+str(chosen))
        if chosen==self._soundfont:return
        previous=self._sfid
        sfid=self._lib.fluid_synth_sfload(self._synth,str(chosen).encode('utf-8'),1)
        if sfid<0:raise RuntimeError('FluidSynth: no puede cargar '+chosen.name)
        self._sfid=sfid
        if previous>=0 and previous!=sfid:
            self._lib.fluid_synth_sfunload(self._synth,previous,1)
        self._soundfont=chosen

    def _audio(self,outdata,frames,time_info,status):
        if self._synth is None:
            outdata.fill(0)
            return
        left=np.empty(frames,dtype=np.float32)
        right=np.empty(frames,dtype=np.float32)
        l=C.c_void_p(left.ctypes.data)
        r=C.c_void_p(right.ctypes.data)
        self._lib.fluid_synth_write_float(self._synth,frames,l,0,1,r,0,1)
        if self._eq_coeffs:
            self._eq_apply(left,right)
        if self._delay_buffer is not None:
            buffer=self._delay_buffer
            index=self._delay_offset
            for pos in range(frames):
                echo_l,echo_r=buffer[index]
                dry_l=float(left[pos]);dry_r=float(right[pos])
                left[pos]=np.clip(dry_l+.30*echo_l,-1.,1.)
                right[pos]=np.clip(dry_r+.30*echo_r,-1.,1.)
                buffer[index,0]=dry_l+.25*echo_l
                buffer[index,1]=dry_r+.25*echo_r
                index=(index+1)%len(buffer)
            self._delay_offset=index
        if self._compressor[0]:
            threshold_db,ratio,attack,release=self._compressor[1:]
            threshold=10**(threshold_db/20)
            a=math.exp(-1/(self._sample_rate*max(1,attack)/1000))
            r=math.exp(-1/(self._sample_rate*max(1,release)/1000))
            env=self._comp_env
            exponent=1.0-1.0/max(1,ratio)
            for i in range(frames):
                magnitude=max(abs(float(left[i])),abs(float(right[i])))
                env=(a if magnitude>env else r)*env+(1-(a if magnitude>env else r))*magnitude
                if env>threshold:
                    gain=(threshold/env)**exponent
                    left[i]*=gain
                    right[i]*=gain
            self._comp_env=env
        outdata[:,0]=left
        outdata[:,1]=right
        self._rms=(float(np.sqrt(np.mean(left*left))),float(np.sqrt(np.mean(right*right))))
        self._peak=(float(np.max(np.abs(left))),float(np.max(np.abs(right))))

    @staticmethod
    def _coefficients(kind,frequency,db,sr,q=.707):
        if db==0:return None
        A=10**(db/40)
        omega=2*math.pi*frequency/sr
        c=math.cos(omega); sn=math.sin(omega)
        if kind=='peak':
            alpha=sn/(2*q)
            b0=1+alpha*A;b1=-2*c;b2=1-alpha*A
            a0=1+alpha/A;a1=-2*c;a2=1-alpha/A
        else:
            alpha=sn/2*math.sqrt(2)
            beta=2*math.sqrt(A)*alpha
            if kind=='low':
                b0=A*((A+1)-(A-1)*c+beta)
                b1=2*A*((A-1)-(A+1)*c)
                b2=A*((A+1)-(A-1)*c-beta)
                a0=(A+1)+(A-1)*c+beta
                a1=-2*((A-1)+(A+1)*c)
                a2=(A+1)+(A-1)*c-beta
            else:
                b0=A*((A+1)+(A-1)*c+beta)
                b1=-2*A*((A-1)+(A+1)*c)
                b2=A*((A+1)+(A-1)*c-beta)
                a0=(A+1)-(A-1)*c+beta
                a1=2*((A-1)-(A+1)*c)
                a2=(A+1)-(A-1)*c-beta
        return (b0/a0,b1/a0,b2/a0,a1/a0,a2/a0)

    def _eq_apply(self,left,right):
        # Never read coefficients and history from two different changes.
        coeffs,states=self._eq_chain
        for index,coeff in enumerate(coeffs):
            b0,b1,b2,a1,a2=coeff
            for ch,data in enumerate((left,right)):
                z1,z2=states[index][ch]
                for i in range(len(data)):
                    x=float(data[i])
                    y=b0*x+z1
                    z1=b1*x-a1*y+z2
                    z2=b2*x-a2*y
                    data[i]=max(-1.0,min(1.0,y))
                states[index][ch]=(z1,z2)

    def start(self,midi_file,card,original=False):
        self.stop()
        from soundfont_catalog import system_soundfont
        self._card=card
        self._original=bool(original)
        try:
            self._events,duration=self._timeline(midi_file)
            if not self._events:
                raise ValueError('El MIDI no tiene eventos reproducibles')
            self._times=[t for t,_ in self._events]
            self._tempo=1.0 if original else max(.5,min(2.,card.tempo_percent/100))
            self._duration_ms=max(1,int(duration*1000/self._tempo))
            self._index=0
            self._bank_msb=[0]*16
            self._bank_lsb=[0]*16
            self._sample_rate=44100 if card.rate.currentIndex()==0 else 48000
            self._create_synth(card.soundfont or system_soundfont())
            self.update_settings(force=True)
            # 'pulse' uses the current PipeWire default sink; does not write MIDI to hardware.
            from preview_player import AudioRoute
            AudioRoute.claim_live(self)
            self._stream=self._factory(samplerate=self._sample_rate,channels=2,
                                      dtype='float32',blocksize=512,device='pulse',
                                      callback=self._audio)
            self._stream.start()
            self._paused=False
            self._position_ms=0
            self._anchor=time.monotonic()
            self._timer.start()
            self.stateChanged.emit(True)
            return True
        except Exception as exc:
            self.error.emit('MIDI directo: '+str(exc))
            self.stop()
            return False

    def _channels_to_change(self):
        if self._original:return []
        if self._card.preset_bank==128:return [9]
        target=self._card.override_channel
        if target is not None:return [target]
        return [x for x in range(16) if x!=9]

    def _program(self,channel,program,bank):
        self._lib.fluid_synth_program_select(self._synth,int(channel),
                 self._sfid,int(bank),int(program))

    def update_settings(self,force=False):
        if not self.running and not force:return
        b=self._card
        state=(str(b.soundfont or ''),b.program_override,b.preset_bank,
               b.override_channel,tuple(b.midi_fx),b.gain_percent,
               b.reverb,b.reverb_level,b.chorus,b.chorus_level,b.eq_enabled,
               b.eq_bass,b.eq_mid,b.eq_treble,b.adsr_enabled,b.adsr_attack,
               b.adsr_decay,b.adsr_sustain,b.adsr_release,b.delay_ms,b.resampler,
               b.comp_enabled,b.comp_threshold,b.comp_ratio,b.comp_attack,b.comp_release)
        if not force and state==self._last_config and self._tempo==(1.0 if self._original else b.tempo_percent/100):return
        old=self._last_config
        self._last_config=state
        if self._original:return
        self._compressor=(bool(b.comp_enabled),int(b.comp_threshold),int(b.comp_ratio),
                         int(b.comp_attack),int(b.comp_release))
        tempo=max(.5,min(2.,b.tempo_percent/100))
        if tempo!=self._tempo:
            source_time=self.position_ms*self._tempo
            self._tempo=tempo
            self._duration_ms=max(1,int((self._times[-1] if self._times else 0)*1000/tempo))
            self._position_ms=int(source_time/tempo)
            self._anchor=time.monotonic()-self._position_ms/1000
        eq=(b.eq_bass,b.eq_mid,b.eq_treble) if b.eq_enabled else (0,0,0)
        if old is None or old[10:14]!=state[10:14]:
            coeffs=[]
            for kind,freq,gain in (('low',180,eq[0]),('peak',1200,eq[1]),('high',3600,eq[2])):
                coeff=self._coefficients(kind,freq,gain,self._sample_rate)
                if coeff:coeffs.append(coeff)
            new_coeffs=tuple(coeffs)
            new_states=[[[0.,0.],[0.,0.]] for _ in coeffs]
            self._eq_chain=(new_coeffs,new_states)
            self._eq_coeffs=new_coeffs
            self._eq_state=new_states
        if old is None or state[0]!=old[0]:
            from soundfont_catalog import system_soundfont
            self._load_bank(b.soundfont or system_soundfont())
        self._lib.fluid_synth_set_gain(self._synth,C.c_float(max(.01,min(1.,b.gain_percent/200))))
        self._lib.fluid_synth_set_polyphony(self._synth,max(16,min(256,b.max_polyphony)))
        self._lib.fluid_synth_set_interp_method(self._synth,-1,
            {'l':1,'c':4,'L':7}.get(b.resampler,4))
        delay=int(b.delay_ms)
        # El índice del delay en state es 19; old[-2] era comp_attack.
        if old is None or old[19]!=delay:
            self._delay_buffer=(np.zeros((max(1,int(self._sample_rate*delay/1000)),2),dtype=np.float32)
                  if delay>0 else None)
            self._delay_offset=0
        self._lib.fluid_synth_set_reverb_on(self._synth,-1,int(b.reverb))
        self._lib.fluid_synth_set_chorus_on(self._synth,-1,int(b.chorus))
        self._lib.fluid_synth_set_reverb_group_level(self._synth,-1,max(0.,min(1.,b.reverb_level/127)))
        self._lib.fluid_synth_set_chorus_group_level(self._synth,-1,max(0.,min(10.,b.chorus_level/14)))
        channels=self._channels_to_change()
        if old is None or state[14:19]!=old[14:19]:
            # SF2 native envelope generators: #34 attack, #36 decay,
            # #37 sustain attenuation (NOT a sustain pedal), #38 release.
            # Channel offsets apply immediately to existing and future voices.
            # Sustain pedal is CC64, deliberately independent of these.
            attack=self._adsr_time_offset(b.adsr_attack) if b.adsr_enabled else 0.
            decay=self._adsr_time_offset(b.adsr_decay) if b.adsr_enabled else 0.
            release=self._adsr_time_offset(b.adsr_release) if b.adsr_enabled else 0.
            level=max(0.001,b.adsr_sustain/100) if b.adsr_enabled else 1.
            sustain=-200.*math.log10(level)
            for ch in range(16):
                if ch==9:continue
                for gen,value in ((34,attack),(36,decay),(37,sustain),(38,release)):
                    result=self._lib.fluid_synth_set_gen(
                        self._synth,ch,gen,C.c_float(value))
                    if result!=0:
                        raise RuntimeError(f"ADSR FluidSynth gen {gen}: {result}")
            # Old CC11 ramps are obsolete; only explicit CC11 expression stays.
            self._adsr_due=[e for e in self._adsr_due if e[4] is not None]
            heapq.heapify(self._adsr_due)
        if b.program_override is not None and (old is None or state[:4]!=old[:4]):
            for ch in channels:
                self._lib.fluid_synth_all_sounds_off(self._synth,ch)
                self._program(ch,b.program_override,b.preset_bank)
                for (nch,_source_note),(note,velocity) in list(self._active.items()):
                    if nch==ch:self._lib.fluid_synth_noteon(self._synth,ch,note,velocity)
        effect_map={'sustain':64,'modulation':1,'expression':11,
                    'brightness':74,'resonance':71}
        effects=dict(b.midi_fx)
        for ch in channels:
            for name,cc in effect_map.items():
                if name in effects:self._lib.fluid_synth_cc(self._synth,ch,cc,effects[name])
                elif old is not None and name in dict(old[4]):
                    self._lib.fluid_synth_cc(self._synth,ch,cc,0 if name=='sustain' else 127)
            self._lib.fluid_synth_pitch_bend(self._synth,ch,
               max(0,min(16383,8192+effects.get('pitch_bend',0))))
        # EQ stays in the output DSP; updated independently without resynthesizing.

    @staticmethod
    def _adsr_time_offset(milliseconds):
        # SoundFont times use logarithmic timecents; 0 is the preset's
        # original envelope, positive values prolong it. A 10 ms
        # reference keeps zero at its original sound and gives a broad
        # audible range without replacing sample/preset data.
        if milliseconds<=0:return 0.
        return float(min(8400,1200*math.log2(1+milliseconds/10)))

    def _schedule(self,when,ch,value,note=None):
        self._serial+=1
        heapq.heappush(self._adsr_due,(when,self._serial,ch,value,note))

    def _dispatch(self,msg):
        ch=getattr(msg,'channel',None)
        if ch is None:return
        if msg.type=='note_on' and msg.velocity>0:
            offset=0 if self._original or ch==9 else self._card.transpose_semitones
            pitch=max(0,min(127,msg.note+offset))
            self._active[(ch,msg.note)]=(pitch,msg.velocity)
            # The FluidSynth per-voice volume envelope (set_gen) now
            # owns ADSR. Do not fake attack/release with CC11 volume.
            self._lib.fluid_synth_noteon(self._synth,ch,pitch,msg.velocity)
        elif msg.type in ('note_off','note_on'):
            data=self._active.pop((ch,msg.note),None)
            if data:
                pitch,_velocity=data
                # Sustain pedal CC64 is enforced inside FluidSynth:
                # the released note remains sounding until pedal up.
                self._lib.fluid_synth_noteoff(self._synth,ch,pitch)
        elif msg.type=='program_change':
            if ch not in self._channels_to_change() or self._card.program_override is None:
                bank=self._bank_msb[ch]*128+self._bank_lsb[ch]
                # GM percussion channel defaults to bank 128 if no bank
                # selection has appeared in the MIDI.
                if ch==9 and bank==0:bank=128
                self._program(ch,msg.program,bank)
        elif msg.type=='control_change':
            if msg.control==0:self._bank_msb[ch]=msg.value
            elif msg.control==32:self._bank_lsb[ch]=msg.value
            # Los controladores interpretativos del propio MIDI deben
            # llegar al sintetizador: silenciarlos cuando había un ajuste
            # manual de FX anulaba el PEDAL CC64 y EXPRESIÓN CC11 de la
            # composición, aunque el archivo los guardaba correctamente.
            # El evento de la partitura tiene prioridad en reproducción;
            # cambios del usuario siguen siendo posibles entre eventos.
            if msg.control not in (64,11,1):
                fx={'brightness':74,'resonance':71}
                overridden=next((name for name,cc in fx.items()
                                 if cc==msg.control),None)
                if (overridden and ch in self._channels_to_change()
                        and overridden in dict(self._card.midi_fx)):
                    return
            self._lib.fluid_synth_cc(self._synth,ch,msg.control,msg.value)
        elif msg.type=='pitchwheel':
            if ch in self._channels_to_change() and 'pitch_bend' in dict(self._card.midi_fx):return
            self._lib.fluid_synth_pitch_bend(self._synth,ch,max(0,min(16383,msg.pitch+8192)))

    def _tick(self):
        if not self.running or self._paused:return
        now=self.position_ms/1000
        source_now=now*self._tempo
        while self._index<len(self._events) and self._events[self._index][0]<=source_now:
            self._dispatch(self._events[self._index][1])
            self._index+=1
        while self._adsr_due and self._adsr_due[0][0]<=now:
            _when,_serial,ch,value,note=heapq.heappop(self._adsr_due)
            if note is None:self._lib.fluid_synth_cc(self._synth,ch,11,value)
            else:self._lib.fluid_synth_noteoff(self._synth,ch,note)
        if now>=self._duration_ms/1000+.3:
            # Do not kill a sustained note 300 ms after the MIDI ended.
            # Leave up to 8s for the user to release CC64 in the UI.
            if not self._original and dict(self._card.midi_fx).get("sustain",0)>=64:
                elapsed=(time.monotonic()-self._anchor)*1000
                if elapsed < self._duration_ms+8000:return
            self.stop()

    def pause(self):
        if not self.running:return
        if not self._paused:
            self._position_ms=self.position_ms
            self._paused=True
            for ch in range(16):self._lib.fluid_synth_all_sounds_off(self._synth,ch)
        else:
            self._anchor=time.monotonic()-self._position_ms/1000
            self._paused=False
            for (ch,_src),(pitch,velocity) in list(self._active.items()):
                self._lib.fluid_synth_noteon(self._synth,ch,pitch,velocity)

    def seek(self,position_ms):
        if not self.running:return False
        target=max(0,min(int(position_ms),self._duration_ms))
        for ch in range(16):self._lib.fluid_synth_all_sounds_off(self._synth,ch)
        self._active.clear()
        self._bank_msb=[0]*16
        self._bank_lsb=[0]*16
        self._index=bisect.bisect_left(self._times,target*self._tempo/1000)
        self._adsr_due.clear()
        # Búsqueda: recuperar los programas y controles vigentes en el
        # instante solicitado. Saltar directamente sin recomponerlos dejaba
        # el último instrumento escuchado, aunque el MIDI pidiera otro.
        self._lib.fluid_synth_program_reset(self._synth)
        for _at,msg in self._events[:self._index]:
            if msg.type in ('program_change','control_change','pitchwheel',
                            'aftertouch','polytouch'):
                self._dispatch(msg)
        if not self._original and self._card.program_override is not None:
            for ch in self._channels_to_change():
                self._program(ch,self._card.program_override,self._card.preset_bank)
        self._position_ms=target
        self._anchor=time.monotonic()-target/1000
        self.update_settings(force=True)
        return True

    def stop(self):
        self._timer.stop()
        from preview_player import AudioRoute
        AudioRoute.release_live(self)
        stream=self._stream
        self._stream=None
        if stream is not None:
            try:stream.stop();stream.close()
            except Exception:pass
        if self._synth:
            for ch in range(16):self._lib.fluid_synth_all_sounds_off(self._synth,ch)
            self._lib.delete_fluid_synth(self._synth)
            self._synth=None
        if self._settings:
            self._lib.delete_fluid_settings(self._settings)
            self._settings=None
        self._sfid=-1
        self._soundfont=None
        self._position_ms=0
        self._rms=(0.,0.)
        self._peak=(0.,0.)
        self._active.clear()
        self._bank_msb=[0]*16
        self._bank_lsb=[0]*16
        self._adsr_due.clear()
        self._eq_coeffs=()
        self._eq_state=[]
        self._eq_chain=((),[])   # atomic snapshot for PortAudio thread
        self._delay_buffer=None
        self._delay_offset=0
        self._comp_env=0.0
        self._last_config=None
        self.stateChanged.emit(False)
