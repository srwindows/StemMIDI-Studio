"""Procesamiento REAL de buses y envíos AUX de la pestaña Mezclador.

No altera la consola flotante ni el motor de sus otros módulos. Se conecta
temporalmente al callback PCM de la mesa cuando la pestaña está acoplada.

Rutas: archivo → pista (EQ/PAN/FADER) → bus principal (DIN/EQ/FX/plugins)
                                     └→ envío AUX post-fader → bus FX → MASTER

Prohibido cargar plugins externos dentro del callback de audio. El plugin
se carga desde la UI antes de entrar a la cadena DSP. Ningún VST de terceros
se empaqueta: se utiliza su instalación original en el equipo.
"""
from __future__ import annotations
import math
import queue
import uuid
import time
from collections import deque
from dataclasses import dataclass
import numpy as np
from scipy.signal import sosfilt
from low_latency_stem_mixer import RATE, BLOCK
from console_audio_engine import DEFAULT_CHANNEL, _biquad

try:
    from pedalboard import Reverb, Delay, Compressor
except ImportError:
    Reverb = Delay = Compressor = None

from stemmidi_sample_delay import SampleDelay
from stemmidi_channel_eq import ChannelEQ


BUS_DEFAULT = {
    "low": 0., "mid": 0., "high": 0.,
    "reverb": 0., "delay": 0., "delay_ms": 320.,
    "feedback": .28, "gate": 0., "compress": 0.,
    "saturation": 0., "wet": 1.,
}
BUS_TITLES = {
    "low": "GRAVES", "mid": "MEDIOS", "high": "AGUDOS",
    "reverb": "REVERB", "delay": "DELAY",
    "delay_ms": "TIEMPO", "feedback": "FEEDBACK",
    "gate": "GATE", "compress": "COMP", "saturation": "SAT",
    "wet": "WET",
}


@dataclass
class PluginSlot:
    uid: str
    name: str
    plugin: object
    kind: str
    path: str = ""
    bypass: bool = False


class TabBusEffects:
    """El PCM por bus y sus plugins pertenecen solo a la pestaña."""

    def __init__(self):
        self.controls = {i: dict(BUS_DEFAULT) for i in range(1, 33)}
        self.sends = {}  # source path -> (dest bus, gain), post-fader
        self.plugins = {i: [] for i in range(1, 33)}
        self.channel_plugins = {}
        self.channel_map = {}
        # Solo muestras reales de salida. La visualización FFT se calcula
        # en Qt, nunca dentro del callback CoreAudio.
        self.master_scope = deque(maxlen=14)
        # PCM real: señal original del canal, retorno de cada BUS y máster.
        # Los buffers son cortos y se leen solo desde la GUI.
        self.source_scope = {}
        self.bus_scope = {i:deque(maxlen=14) for i in range(1,33)}
        self.scope_source = None
        self.eq16 = {i:[0.]*16 for i in range(1,33)}
        self._eq16_filters = {}
        self._eq16_state = {}
        self._processors = {}
        self._filters = {}
        self._filter_state = {}
        self._plugin_failures = {}
        self._delay = {}
        self._reverb = {}
        self.live = None
        self._callback_original = None
        self.bus_count = 16
        self._active = False
        self._last_pcm_frame = 0
        # Independent levels and direct route per logical channel.
        # UI thread replaces immutable-by-convention snapshots; audio reads only.
        self.channel_routes = {}
        self._dry_gain_state = np.zeros(0,dtype=np.float32)
        # Independent PRE-FADER clean send for every channel in the matrix.
        self._clean_send_gain_state = np.zeros(0,dtype=np.float32)

    @property
    def supported(self):
        return Reverb is not None

    def bind(self, live):
        if self._active and self.live is live:
            return
        assert not self._active
        from types import MethodType
        self.live = live
        self._last_pcm_frame = 0
        self._dry_gain_state = np.zeros(0,dtype=np.float32)
        self._clean_send_gain_state = np.zeros(0,dtype=np.float32)
        self._callback_original = live._callback
        live._callback = MethodType(self._callback, live)
        self._active = True

    def unbind(self):
        if not self._active:
            return
        live = self.live
        live._callback = self._callback_original
        self._active = False
        self.live = None

    def set_channel_map(self, mapping):
        # Las claves son nombres FFmpeg reales; los valores son tiras
        # lógicas que sobreviven si se reemplaza un archivo arrastrándolo.
        self.channel_map = dict(mapping)

    def _channel_key(self, source):
        return self.channel_map.get(str(source), str(source))

    def get_channel_route(self, key, processed_level=1.):
        """Two PARALLEL, independent paths. dry_enabled is UI focus only."""
        key=str(key)
        prior=self.channel_routes.get(key,{})
        route={
            "processed_level":max(0.,min(1.5,float(processed_level))),
            "dry_level":.5,
            # 00 = no BUS send; 01..32 = independent PRE-FADER clean send.
            # It ignores the clean direct Mute, fader and panorama.
            "dry_bus":0,
            "dry_bus_gain":1.,  # Matrix row fader, independent from CLEAN/FX/BUS
            # Independent stereo pan for both channel direct outputs.
            # The bus source tap is ALWAYS the unpanned original.
            "dry_pan":0.,
            "processed_pan":0.,
            "dry_enabled":False,
            "dry_muted":False,"processed_muted":False,
            "dry_solo":False,"processed_solo":False,
        }
        route.update(prior)
        # Legacy project snapshots had one channel-wide mute. Move it ONLY
        # to the processed path. Never allow that legacy flag to mute dry.
        if "processed_muted" not in prior and prior.get("muted"):
            route["processed_muted"]=True
        return route

    def set_channel_route(self, key, **values):
        key=str(key)
        route=self.get_channel_route(key)
        for setting,value in values.items():
            if setting in ("processed_level","dry_level","dry_bus_gain"):
                route[setting]=max(0.,min(1.5,float(value)))
            elif setting in ("dry_pan","processed_pan"):
                route[setting]=max(-1.,min(1.,float(value)))
            elif setting=="dry_bus":
                index=int(value)
                if index<0 or index>32:
                    raise ValueError("BUS limpio fuera de rango 00-32")
                route[setting]=index
            elif setting in ("dry_enabled","dry_muted","processed_muted",
                             "dry_solo","processed_solo"):
                route[setting]=bool(value)
            elif setting=="muted":
                # Backwards compatibility for pre-R27 project manifests.
                route["processed_muted"]=bool(value)
            else:
                raise KeyError(setting)
        # Snapshot update prevents partial dictionary mutation in audio thread.
        self.channel_routes={**self.channel_routes,key:route}
        return route

    def _make_channel_builtin(self, kind):
        if kind == "Channel EQ":
            return ChannelEQ()
        if kind == "Sample Delay":
            return SampleDelay()
        if not self.supported:
            raise RuntimeError("Efectos integrados no disponibles")
        if kind == "Reverb":
            return Reverb(room_size=.55, wet_level=.45, dry_level=.55)
        if kind == "Delay":
            return Delay(delay_seconds=.29, feedback=.30, mix=.35)
        if kind == "Compresor":
            return Compressor(threshold_db=-20, ratio=3)
        raise ValueError(kind)

    def add_channel_builtin(self, channel, kind):
        key=str(channel)
        slot=PluginSlot(str(uuid.uuid4()),kind,
                        self._make_channel_builtin(kind),"integrado")
        self.channel_plugins={**self.channel_plugins,
                              key:[*self.channel_plugins.get(key,[]),slot]}
        return slot

    # Solo efectos internos; los presets externos no se cargan.

    def channel_slot(self, channel, uid):
        for slot in self.channel_plugins.get(str(channel),()):
            if slot.uid==uid:return slot
        return None

    def channel_action(self, channel, uid, action):
        key=str(channel)
        slots=list(self.channel_plugins.get(key,()))
        index=next((i for i,x in enumerate(slots) if x.uid==uid),-1)
        if index<0:return
        if action=="bypass":
            slot=slots[index]
            slots[index]=PluginSlot(slot.uid,slot.name,slot.plugin,
                                     slot.kind,slot.path,not slot.bypass)
        elif action=="remove":
            slots.pop(index)
        elif action in ("up","down"):
            target=index+(-1 if action=="up" else 1)
            if not 0<=target<len(slots):return
            slots[index],slots[target]=slots[target],slots[index]
        else:
            return
        self.channel_plugins={**self.channel_plugins,key:slots}

    def _process_channel_inserts(self, source, stereo, frames):
        key=self._channel_key(source)
        for slot in self.channel_plugins.get(key,()):
            if slot.bypass:continue
            try:
                if isinstance(slot.plugin,(SampleDelay,ChannelEQ)):
                    stereo=slot.plugin.process_stereo(stereo)
                    continue
                out=slot.plugin.process(
                    np.ascontiguousarray(stereo.T),RATE,
                    buffer_size=frames,reset=False)
                out=np.asarray(out)
                if out.shape==(2,frames):
                    out=out.T.copy()
                elif out.shape != stereo.shape:
                    raise ValueError("Salida de plugin con tamaño incorrecto")
                if not np.isfinite(out).all():
                    raise ValueError("Plugin devolvió valores no finitos")
                stereo=out.astype(np.float32,copy=False)
            except Exception as error:
                # Fallos de procesamiento nunca detienen el audio.
                self._plugin_failures[slot.uid]=str(error)
                # El DSP devuelve audio original si el efecto falla.
        return stereo

    def set_bus_count(self, number):
        if number not in (16, 32):
            raise ValueError("Solo 16 o 32 buses")
        self.bus_count = number

    def set_control(self, bus, name, value):
        bus = int(bus)
        if not 1 <= bus <= 32 or name not in BUS_DEFAULT:
            raise ValueError((bus, name))
        new = dict(self.controls[bus])
        new[name] = float(value)
        if name in ("low", "mid", "high"):
            new[name] = min(12., max(-12., new[name]))
        elif name == "delay_ms":
            new[name] = min(1400., max(50., new[name]))
        else:
            new[name] = min(1., max(0., new[name]))
        old = self.controls[bus]
        self.controls = {**self.controls, bus: new}
        if name in ("low", "mid", "high") and old[name] != new[name]:
            self._filters.pop(bus, None)
            self._filter_state.pop(bus, None)
        if name in ("reverb",):
            self._reverb.pop(bus, None)
        if name in ("delay", "delay_ms", "feedback"):
            self._delay.pop(bus, None)

    EQ16_HZ = tuple(float(x) for x in np.geomspace(20.,20000.,16))

    def set_eq16(self, bus, band, gain_db):
        bus=int(bus);band=int(band)
        if not 1<=bus<=32 or not 0<=band<16:
            raise ValueError("Banda de EQ16 no válida")
        next_=list(self.eq16[bus])
        next_[band]=max(-12.,min(12.,float(gain_db)))
        self.eq16={**self.eq16,bus:next_}
        self._eq16_filters.pop(bus,None)
        self._eq16_state.pop(bus,None)

    def _process_eq16(self,index,a):
        gains=self.eq16[index]
        if not any(abs(g)>.01 for g in gains):
            return a
        sos=self._eq16_filters.get(index)
        if sos is None:
            sos=np.stack([_biquad(hz,g,"peak",1.25)
                          for hz,g in zip(self.EQ16_HZ,gains)
                          if abs(g)>.01])
            self._eq16_filters[index]=sos
        zi=self._eq16_state.get(index)
        if zi is None or zi.shape!=(len(sos),2,2):
            zi=np.zeros((len(sos),2,2),np.float64)
        result,zi=sosfilt(sos,a,axis=0,zi=zi)
        self._eq16_state[index]=zi
        return result.astype(np.float32,copy=False)

    def _scope_append(self,selected,original,buses,master,frames):
        if frames<=0:return
        if selected and original is not None:
            buffer=self.source_scope.setdefault(selected,deque(maxlen=14))
            buffer.append(original[::2].copy())
        for index,stereo in buses.items():
            self.bus_scope[index].append(stereo[::2].copy())
        self.master_scope.append(master[::2].copy())

    def set_send(self, path, bus, amount):
        bus = int(bus)
        amount = min(1., max(0., float(amount)))
        copy = dict(self.sends)
        if bus <= 0 or amount <= 0:
            copy.pop(str(path), None)
        else:
            if bus > 32:
                raise ValueError("BUS AUX fuera de rango")
            copy[str(path)] = (bus, amount)
        self.sends = copy

    def make_builtin(self, bus, kind):
        if kind == "Channel EQ":
            return self._add_slot(bus, ChannelEQ(), kind, "integrado")
        if kind == "Sample Delay":
            return self._add_slot(bus, SampleDelay(), kind, "integrado")
        if not self.supported:
            raise RuntimeError("Efectos integrados no disponibles")
        if kind == "Reverb":
            plugin = Reverb(room_size=.55, wet_level=.45, dry_level=.55)
        elif kind == "Delay":
            plugin = Delay(delay_seconds=.29, feedback=.30, mix=.35)
        elif kind == "Compresor":
            plugin = Compressor(threshold_db=-20, ratio=3)
        else:
            raise ValueError(kind)
        return self._add_slot(bus, plugin, kind, "integrado")

    def _add_slot(self, bus, plugin, title, kind, path=""):
        bus = int(bus)
        if not 1 <= bus <= 32:
            raise ValueError(bus)
        slot = PluginSlot(str(uuid.uuid4()), title, plugin, kind, path)
        self.plugins = {**self.plugins,
                        bus: [*self.plugins[bus], slot]}
        return slot

    def reorder(self, bus, index, distance):
        old = list(self.plugins[int(bus)])
        target = index + distance
        if index < 0 or index >= len(old) or target < 0 or target >= len(old):
            return
        old[index], old[target] = old[target], old[index]
        self.plugins = {**self.plugins, int(bus): old}

    def remove(self, bus, index):
        old = list(self.plugins[int(bus)])
        if 0 <= index < len(old):
            old.pop(index)
            self.plugins = {**self.plugins, int(bus): old}

    def toggle_bypass(self, bus, index):
        old = list(self.plugins[int(bus)])
        if 0 <= index < len(old):
            src = old[index]
            old[index] = PluginSlot(src.uid, src.name, src.plugin,
                                    src.kind, src.path, not src.bypass)
            self.plugins = {**self.plugins, int(bus): old}

    def process_bus(self, index, signal, frames):
        """Solo procesa el BUS afectado: canal original nunca reescrito."""
        params = self.controls[index]
        a = signal
        eq = (params["low"], params["mid"], params["high"])
        if any(abs(x) > .001 for x in eq):
            sos = self._filters.get(index)
            if sos is None:
                coefficients = [_biquad(freq, gain,typ,q) for gain,freq,typ,q in
                                ((eq[0],180,"low",.7),(eq[1],1200,"peak",.9),
                                 (eq[2],5200,"high",.7))
                                if abs(gain) > .001]
                sos = np.stack(coefficients)
                self._filters[index] = sos
            state = self._filter_state.get(index)
            if state is None or state.shape != (len(sos), 2, 2):
                state = np.zeros((len(sos), 2, 2), np.float64)
            processed, state = sosfilt(sos, a, axis=0, zi=state)
            self._filter_state[index] = state
            a = processed.astype(np.float32,copy=False)

        a = self._process_eq16(index,a)

        gate = params["gate"]
        if gate:
            threshold = .0015 + .06 * gate*gate
            envelope = np.sqrt(np.mean(a*a,axis=1))
            gain = np.clip((envelope - threshold*.3)/(threshold*.7+1e-8),.06,1.)
            a = a * gain[:, None]
        comp = params["compress"]
        if comp:
            threshold = .3-.22*comp
            ratio = 1+7*comp
            magnitude = np.abs(a)
            a = np.sign(a)*np.where(magnitude>threshold,
                threshold+(magnitude-threshold)/ratio,magnitude)
        saturate = params["saturation"]
        if saturate:
            drive=1+4*saturate
            a=np.tanh(a*drive)/drive

        if self.supported:
            # Pedalboard conserva la cola de efectos entre bloques.
            delay = params["delay"]
            if delay:
                effect = self._delay.get(index)
                if effect is None:
                    effect=Delay(delay_seconds=params["delay_ms"]/1000.,
                                 feedback=params["feedback"],mix=delay)
                    self._delay[index]=effect
                a = self._plugin_process(effect,a,frames,index)
            reverb=params["reverb"]
            if reverb:
                effect=self._reverb.get(index)
                if effect is None:
                    effect=Reverb(room_size=.57,wet_level=reverb,
                                  dry_level=1-reverb)
                    self._reverb[index]=effect
                a=self._plugin_process(effect,a,frames,index)
        slots=self.plugins.get(index,())
        for slot in slots:
            if not slot.bypass:
                a=self._plugin_process(slot.plugin,a,frames,index,slot.uid)
        return np.asarray(a,dtype=np.float32)

    def _plugin_process(self,plugin,a,frames,bus,uid=""):
        # Pedalboard acepta (canales, frames) y conserva el estado reset=False.
        try:
            output=plugin.process(np.ascontiguousarray(a.T),
                       RATE,buffer_size=frames,reset=False)
            output=np.asarray(output)
            if output.shape==(2,frames):
                output=output.T.copy()
            elif output.shape != a.shape:
                raise ValueError("El plugin devolvió distinto número de muestras")
            if not np.isfinite(output).all():
                raise ValueError("El plugin devolvió muestras no finitas")
            return output.astype(np.float32,copy=False)
        except Exception as exc:
            # Fallo de terceros: pasar audio sin procesar y conservar transporte.
            if uid:
                self._plugin_failures[uid]=str(exc)
                for slot in self.plugins[bus]:
                    if slot.uid==uid:
                        self.toggle_bypass(bus,self.plugins[bus].index(slot))
                        break
            return a

    def _callback(self, live, outdata, frames, timing, status):
        """Mantener vivo CoreAudio ante errores DSP."""
        begin=time.perf_counter_ns()
        if status:
            live.output_xruns+=1
        try:
            self._render_callback(live,outdata,frames,timing,status)
        except Exception as error:
            # PortAudio silencia permanentemente la salida si se escapa
            # una excepción de su callback. Nunca permitirlo.
            outdata.fill(0)
            live.callback_errors+=1
            live.last_callback_error=f"{type(error).__name__}: {error}"[:250]
        finally:
            cost_ms=(time.perf_counter_ns()-begin)/1000000.
            live.last_callback_ms=cost_ms
            if cost_ms>live.max_callback_ms:
                live.max_callback_ms=cost_ms
            if cost_ms>1000.*frames/RATE:
                live.callback_overruns+=1

    def _render_callback(self, live, outdata,frames,timing,status):
        """Callback PCM: base original + bus inserts + sends en paralelo."""
        outdata.fill(0)
        if not live._running or live._paused:
            return
        try:
            chunk=live._queue.get_nowait()
        except queue.Empty:
            live.underruns+=1
            return
        if len(chunk)!=frames or outdata.shape[1]<2:
            return
        # Al iniciar o buscar otra posición, limpiar muestras del archivo
        # anterior. La pausa NO resetea (debe conservar continuidad).
        if live._frames_played < self._last_pcm_frame:
            for group in self.channel_plugins.values():
                for slot in group:
                    if isinstance(slot.plugin,(SampleDelay,ChannelEQ)):
                        slot.plugin.reset()
            for group in self.plugins.values():
                for slot in group:
                    if isinstance(slot.plugin,(SampleDelay,ChannelEQ)):
                        slot.plugin.reset()
        self._last_pcm_frame=live._frames_played+frames
        cfgs=live._channel_controls
        volumes=live._volumes
        names=live._names
        # Solo acts on individual signal PATHS, not on the whole channel.
        # In particular, SOLO(clean) must not also select its FX return.
        previous=live._gain_state
        if previous.size!=len(names):
            previous=np.zeros(len(names),dtype=np.float32)
        old_dry=self._dry_gain_state
        if old_dry.size!=len(names):
            old_dry=np.zeros(len(names),dtype=np.float32)
        old_sends=self._clean_send_gain_state
        if old_sends.size!=len(names):
            old_sends=np.zeros(len(names),dtype=np.float32)

        routes={}
        tap={}
        peaks={}
        direct_master=np.zeros((frames,2),dtype=np.float32)
        selected_key=self.scope_source
        source_preview=None
        routes_config=self.channel_routes
        gains=np.zeros(len(names),dtype=np.float32)
        dry_gains=np.zeros(len(names),dtype=np.float32)
        send_gains=np.zeros(len(names),dtype=np.float32)
        audible_count=0
        active_solos=any(
            (r.get("dry_solo") or r.get("processed_solo"))
            for name in names if name in live._selected
            for r in (routes_config.get(self._channel_key(name),{}),)
        )
        for i,name in enumerate(names):
            cfg=cfgs.get(name,DEFAULT_CHANNEL)
            route=routes_config.get(self._channel_key(name))
            if route is None:
                # Legacy/standalone tests: default still routable to BUS.
                route={"processed_level":float(volumes.get(name,1.)),
                       "dry_level":.5,"dry_enabled":False,"muted":False}
            selected=name in live._selected
            fx_audible=(
                selected and not route.get("processed_muted",False)
                and (not active_solos or route.get("processed_solo",False)))
            dry_audible=(
                selected and not route.get("dry_muted",False)
                and (not active_solos or route.get("dry_solo",False)))
            clean_bus=int(route.get("dry_bus",0))
            # PRE-FADER bus send has its own route; independent of dry
            # Mute/Solo, dry fader and dry pan, but never of file selection.
            clean_bus_active=selected and 1<=clean_bus<=self.bus_count
            clean_send_gain=(float(route.get("dry_bus_gain",1.))
                             if clean_bus_active else 0.)
            send_gains[i]=clean_send_gain
            # Both paths are always independently routed. LIMPIO only
            # changes which saved fader/M/S values the user edits.
            current=float(route["processed_level"]) if fx_audible else 0.
            current_dry=float(route["dry_level"]) if dry_audible else 0.
            gains[i]=current
            dry_gains[i]=current_dry
            if current or current_dry or clean_bus_active:audible_count+=1
            if (not current and not previous[i] and not current_dry
                    and not old_dry[i] and not clean_bus_active):
                peaks[name]=(0.,0.)
                continue

            # Permanent dry DIRECT TO MASTER; never enters channel FX,
            # auxiliary sends or bus, regardless of LIMPIO's UI focus.
            original=chunk[:,i,:]
            if selected_key==self._channel_key(name):
                source_preview=original
            # PRE-FADER, PRE-MUTE, PRE-PAN clean send:
            #   original PCM ──→ chosen BUS (unaffected by the controls
            #   that shape the direct clean output). This bus may receive
            #   several tracks, and its own plugins and fader apply later.
            # A muted direct output, or one with its fader at zero, must
            # never stop sending source audio to the chosen BUS.
            if clean_bus_active and (clean_send_gain or old_sends[i]):
                if clean_bus not in routes:
                    routes[clean_bus]=np.zeros((frames,2),np.float32)
                # Smooth gain changes over one audio block to avoid zipper
                # clicks; unlike a VU this fader directly adjusts PCM.
                if clean_send_gain!=old_sends[i]:
                    envelope=(old_sends[i]+live._fade[:frames]*
                              (clean_send_gain-old_sends[i]))
                    routes[clean_bus]+=original*envelope[:,None]
                else:
                    routes[clean_bus]+=original*clean_send_gain

            # Independent clean DIRECT to MASTER, controlled by its OWN
            # fader, Mute/Solo and panorama, without changing BUS input.
            if current_dry!=old_dry[i]:
                ramp=old_dry[i]+live._fade[:frames]*(current_dry-old_dry[i])
                clean=original*ramp[:,None]
            else:
                clean=original*current_dry
            pan_clean=float(route.get("dry_pan",0.))
            if pan_clean:
                clean=clean.copy()
                clean[:,0]*=1.-max(0.,pan_clean)
                clean[:,1]*=1.+min(0.,pan_clean)
            direct_master+=clean

            # Channel FX may be heard DIRECTLY at MASTER without BUS.
            # An assigned BUS and any AUX remain additional, independent
            # paths through their own effects and BUS gain.
            if not current and not previous[i]:
                peaks[name]=(float(np.max(np.abs(clean[:,0]))),
                             float(np.max(np.abs(clean[:,1]))))
                if live.recording and cfg.get("arm"):tap[name]=original.copy()
                continue
            processed=original.copy()
            if current!=previous[i]:
                ramp=previous[i]+live._fade[:frames]*(current-previous[i])
                processed*=ramp[:,None]
            else:
                processed*=current
            processed*=10**(cfg["trim"]/20.)
            # Processed direct channel retains its OWN panorama;
            # neither of these two pans affects the PRE-FADER clean BUS tap.
            pan=float(route.get("processed_pan",cfg["pan"]))
            processed[:,0]*=1.-max(0.,pan)
            processed[:,1]*=1.+min(0.,pan)
            processed=live._filter(name,processed)
            gate=cfg["gate"]
            if gate:
                threshold=.0015+.06*gate*gate
                envelope=np.sqrt(np.mean(processed*processed,axis=1))
                factor=np.clip((envelope-threshold*.3)/(threshold*.7+1e-8),.06,1.)
                processed*=factor[:,None].astype(np.float32)
            comp=cfg["compress"]
            if comp:
                threshold=.3-.22*comp;ratio=1.+7*comp
                mag=np.abs(processed)
                processed=np.sign(processed)*np.where(
                    mag>threshold,threshold+(mag-threshold)/ratio,mag)
            saturation=cfg["saturation"]
            if saturation:
                drive=1.+4*saturation
                processed=np.tanh(processed*drive)/drive
            processed=self._process_channel_inserts(name,processed,frames)

            # THREE independent output routes:
            #   A. ORIGINAL/direct -> MASTER (own clean fader)
            #   B. CHANNEL INSERTS/direct -> MASTER (own FX fader)
            #   C. Optional clean BUS, processed BUS and AUX -> BUS FX -> MASTER.
            # Before R29 only route C existed for processed audio, so
            # reducing BUS to zero silenced the channel's own FX output.
            # An unused FX chain cannot duplicate the untouched clean
            # signal at unity gain.
            channel_fx_active=(
                any(not slot.bypass for slot in
                    self.channel_plugins.get(self._channel_key(name),()))
                or name in live._channel_filters
                or any(float(cfg.get(k,0.))!=0. for k in (
                    "gate","compress","saturation")))
            channel_fx_out=processed if channel_fx_active else None
            if channel_fx_out is not None:
                direct_master+=channel_fx_out

            mainbus=int(cfg.get("bus",0))
            # An unassigned BUS (0) receives no FX audio; never send to BUS 1
            # implicitly. A dry channel still goes straight to the MASTER.
            if not 1<=mainbus<=self.bus_count:
                mainbus=0
            if mainbus:
                if mainbus not in routes:
                    routes[mainbus]=np.zeros((frames,2),np.float32)
                routes[mainbus]+=processed
            aux=self.sends.get(name)
            if aux is not None:
                dest,amount=aux
                if dest!=mainbus and 1<=dest<=self.bus_count and amount>0:
                    if dest not in routes:
                        routes[dest]=np.zeros((frames,2),np.float32)
                    routes[dest]+=processed*amount
            # Channel FX VU reads the actual direct FX return, not the
            # auxiliary BUS feed. With no channel FX, FX VU is silent.
            # Bus and MASTER VUs remain completely independent.
            displayed=(clean if route["dry_enabled"] else
                       channel_fx_out if channel_fx_out is not None else
                       np.zeros_like(clean))
            peaks[name]=(float(np.max(np.abs(displayed[:,0]))),
                         float(np.max(np.abs(displayed[:,1]))))
            if live.recording and cfg.get("arm"):
                tap[name]=original.copy()
        live._gain_state=gains
        self._dry_gain_state=dry_gains
        self._clean_send_gain_state=send_gains
        bus_peaks={}
        mix=direct_master.copy()
        levels=live._bus_levels
        active=set(routes)
        active.update(i for i in range(1,self.bus_count+1)
                      if self.controls[i]["delay"] or
                      self.controls[i]["reverb"] or self.plugins[i])
        observed_buses={}
        for index in sorted(active):
            incoming=routes.get(index)
            if incoming is None:
                incoming=np.zeros((frames,2),np.float32)
            # Every BUS always carries its processed signal, even when
            # no inserts are active. Its own fader controls ONLY its output.
            processed=self.process_bus(index,incoming,frames)
            bus_gain=float(levels.get(index,1.))
            processed_out=processed*bus_gain
            mix+=processed_out
            observed_buses[index]=processed_out
            bus_peaks[index]=(float(np.max(np.abs(processed_out[:,0]))),
                              float(np.max(np.abs(processed_out[:,1]))))
        live.bus_peaks={i:bus_peaks.get(i,(0.,0.))
                        for i in range(1,self.bus_count+1)}
        live.track_peaks=peaks
        # Master is a single post-sum gain, not an implicit channel-count
        # normalizer or a substitute for any BUS fader.
        mix*=live._master_volume
        # Un pico anómalo no debe bajar todo el MASTER.
        # Limitación por muestra, no normalización global de bloque.
        np.clip(mix,-.98,.98,out=mix)
        outdata[:,:2]=mix
        if frames:
            self._scope_append(selected_key,source_preview,observed_buses,
                               mix,frames)
        live._frames_played+=frames
        live.blocks+=1
        maximum=np.max(np.abs(mix),axis=0)
        live.master_peaks=(float(maximum[0]),float(maximum[1]))
        live.last_mix_level=float(max(maximum))
        if live._last_mask_applied_ns<live._last_mask_update_ns:
            live._last_mask_applied_ns=__import__("time").monotonic_ns()
        if live.recording and live._record_queue is not None:
            try:
                live._record_queue.put_nowait((mix.copy(),tap))
            except queue.Full:
                live.record_dropped_blocks+=1

    def _slot_settings(self,slot):
        plugin=slot.plugin
        if isinstance(plugin,ChannelEQ):
            return {"channel_eq":plugin.snapshot()}
        if isinstance(plugin,SampleDelay):
            return {"sample_delay":{
                "left":plugin.delay_left_samples,"right":plugin.delay_right_samples,
                "linked":plugin.linked,"units":plugin.units}}
        if hasattr(plugin,"parameters"):
            return {"raw":{key:float(param.raw_value)
                           for key,param in plugin.parameters.items()}}
        fields={
            "Reverb":("room_size","wet_level","dry_level","damping","width"),
            "Delay":("delay_seconds","feedback","mix"),
            "Compresor":("threshold_db","ratio","attack_ms","release_ms"),
        }.get(slot.name,())
        return {"attrs":{key:float(getattr(plugin,key))
                         for key in fields if hasattr(plugin,key)}}

    def apply_slot_settings(self,slot,settings):
        plugin=slot.plugin
        if not isinstance(settings,dict):return
        if isinstance(plugin,ChannelEQ):
            plugin.restore(settings.get("channel_eq",{}))
            return
        if isinstance(plugin,SampleDelay):
            values=settings.get("sample_delay",{})
            if isinstance(values,dict):
                plugin.linked=False
                plugin.delay_left_samples=values.get("left",0)
                plugin.delay_right_samples=values.get("right",0)
                plugin.linked=values.get("linked",False)
                plugin.units=values.get("units","samples")
            return
        for key,value in settings.get("raw",{}).items():
            if hasattr(plugin,"parameters") and key in plugin.parameters:
                plugin.parameters[key].raw_value=float(value)
        for key,value in settings.get("attrs",{}).items():
            if hasattr(plugin,key):
                setattr(plugin,key,float(value))

    def config_snapshot(self):
        return {
            "controls": self.controls,
            "eq16": self.eq16,
            "sends": self.sends,
            "channel_routes":self.channel_routes,
            "channel_plugins": {str(channel):[
                {"name":slot.name,"kind":slot.kind,
                 "path":slot.path,"bypass":slot.bypass,
                 "settings":self._slot_settings(slot)}
                for slot in slots]
                for channel,slots in self.channel_plugins.items() if slots},
            "plugins": {str(bus):[
                {"name":slot.name,"kind":slot.kind,
                 "path":slot.path,"bypass":slot.bypass,
                 "settings":self._slot_settings(slot)}
                for slot in lst] for bus,lst in self.plugins.items()
                if lst}
        }
