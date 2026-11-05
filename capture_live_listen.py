"""Escucha voluntaria del PCM PROCESADO (la misma señal que se graba).

No se conecta a la salida que estamos capturando como «monitor»:
esto evitaría un bucle infinito y una posible subida brusca de nivel.
PulseAudio/PipeWire, formato estéreo float32. No modifica la mezcla
del sistema, no captura por su cuenta y no se activa por defecto.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil


def available_sinks():
    if sys.platform != "linux":
        from native_listen import audio_outputs
        try:
            return [("Salida: "+name,"portaudio:"+str(index))
                    for index,name in audio_outputs()]
        except Exception:
            return []
    try:
        result=subprocess.run(
            ["pactl","-f","json","list","sinks"],capture_output=True,
            check=True,timeout=4)
        sinks=json.loads(result.stdout)
    except (OSError,ValueError,subprocess.SubprocessError):
        return []
    items=[]
    for sink in sinks:
        name=str(sink.get("name","") or "")
        if not name:
            continue
        description=str(sink.get("description") or "")
        if not description or description=="(null)":
            description=str((sink.get("properties") or {}).get("device.description") or "")
        if not description or description=="(null)":
            description=name.rsplit(".",1)[-1] or name
        items.append((description,name))
    return items


def default_sink():
    if sys.platform!="linux":
        from native_listen import default_audio_output
        try:return default_audio_output()
        except Exception:return ""
    try:
        return subprocess.run(
            ["pactl","get-default-sink"],capture_output=True,text=True,
            timeout=3,check=True).stdout.strip()
    except (OSError,subprocess.SubprocessError):
        return ""


def is_feedback_route(source,sink):
    """No reproducir en el propio sink cuando la fuente es su monitor."""
    if not source or not sink:
        return False
    source,sink=str(source),str(sink)
    if source.endswith(".monitor") and source[:-len(".monitor")]==sink:
        return True
    # Un loopback virtual no se debe reproducir hacia sí mismo.
    if source.startswith("soundcard:") and sink.startswith("portaudio:"):
        try:
            import soundcard as sc
            import sounddevice as sd
            ident=source.split(":",1)[1]
            if ident.startswith("name:"):
                from urllib.parse import unquote
                name=unquote(ident.removeprefix("name:"))
                selected=next((m for m in sc.all_microphones(include_loopback=True)
                               if str(m.name)==name),None)
            else:
                selected=next((m for m in sc.all_microphones(include_loopback=True)
                               if str(m.id)==ident),None)
            if selected is not None:
                output=sd.query_devices(int(sink.split(":",1)[1]))
                name=str(selected.name).strip().casefold()
                out=str(output["name"]).strip().casefold()
                if name==out and (
                    bool(getattr(selected,"isloopback",False)) or
                    any(part in name for part in
                        ("blackhole","soundflower","loopback","vb-cable"))):
                    return True
        except (OSError,ValueError,LookupError):
            pass
    return False


class LiveProcessedListen:
    """Salida no bloqueante: el audio y medidores no dependen de la salida."""
    def __init__(self,source,sample_rate):
        self.source=str(source)
        self.sample_rate=int(sample_rate)
        self.sink=""
        self.process=None
        self._native=None
        self.pending=b""
        self._status="Desactivada"

    @property
    def status(self):
        return self._status

    @property
    def active(self):
        if self._native is not None:
            return self._native.active
        return self.process is not None and self.process.poll() is None

    def start(self,sink):
        sink=str(sink or "")
        if not sink:
            raise ValueError("Selecciona un dispositivo de salida")
        if is_feedback_route(self.source,sink):
            raise ValueError(
                "Esta salida es el mismo dispositivo que estás capturando. "
                "Elige otra salida para evitar realimentación")
        if sys.platform!="linux":
            from native_listen import NativeListen
            self.stop()
            native=NativeListen(sink,self.sample_rate)
            native.start()
            self._native=native
            self.sink=sink
            self._status="Escucha procesada en "+sink
            return
        if not shutil.which("pacat"):
            raise RuntimeError("La escucha procesada requiere pacat/PipeWire en Linux")
        self.stop()
        args=["pacat","--playback","--raw","--device="+sink,
              "--format=float32le","--channels=2",
              "--rate="+str(self.sample_rate),"--latency-msec=55",
              "--client-name=StemMIDI Studio",
              "--stream-name=Escucha procesada de grabación"]
        self.process=subprocess.Popen(
            args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,bufsize=0)
        try:
            os.set_blocking(self.process.stdin.fileno(),False)
        except (OSError,ValueError):
            self.stop()
            raise
        self.sink=sink
        self._status="Escucha procesada en "+sink
        self.pending=b""

    def feed(self,pcm):
        if self._native is not None:
            if not self._native.active:
                self.stop()
                self._status="Error: salida de escucha desconectada"
                return
            self._native.feed(pcm)
            return
        process=self.process
        if process is None:
            return
        if process.poll() is not None:
            self.stop()
            self._status="Error: salida de escucha desconectada"
            return
        block=self.pending+pcm
        # Nunca bloquear la grabación si la tarjeta de sonido no consume.
        try:
            sent=os.write(process.stdin.fileno(),block)
        except BlockingIOError:
            sent=0
        except (OSError,ValueError):
            self.stop()
            self._status="La salida de escucha no admite más audio"
            return
        self.pending=block[sent:]
        if len(self.pending)>131072:
            # Un dispositivo bloqueado no debe acumular latencia ilimitada.
            self.stop()
            self._status="Salida lenta o bloqueada: escucha detenida"

    def stop(self):
        native=self._native
        self._native=None
        if native is not None:
            native.stop()
        p=self.process
        self.process=None
        self.pending=b""
        self.sink=""
        if p is None:
            return
        try:
            if p.stdin:p.stdin.close()
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=.4)
        except (OSError,subprocess.SubprocessError):
            pass
        self._status="Desactivada"
