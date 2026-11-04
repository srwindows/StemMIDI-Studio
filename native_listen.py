"""Salida CoreAudio/WASAPI no bloqueante de la escucha procesada.

La captura nunca espera a la reproducción. Si la salida se retrasa, se
descarta audio antiguo para evitar acumulación de latencia.
"""
from __future__ import annotations

from collections import deque
import threading
import numpy as np


def audio_outputs():
    import sounddevice as sd
    return [(i, str(device["name"]))
            for i, device in enumerate(sd.query_devices())
            if int(device.get("max_output_channels", 0)) >= 2]


def default_audio_output():
    import sounddevice as sd
    try:
        idx = int(sd.default.device[1])
    except (TypeError, IndexError, ValueError):
        return ""
    return "portaudio:" + str(idx) if any(i == idx for i, _ in audio_outputs()) else ""


class NativeListen:
    """Alimentador callback con cola acotada, formato estéreo float32."""
    def __init__(self, device: str, sample_rate: int):
        if not device.startswith("portaudio:"):
            raise ValueError("La salida seleccionada no es CoreAudio/WASAPI")
        self.device = int(device.split(":", 1)[1])
        self.sample_rate = int(sample_rate)
        self._lock = threading.Lock()
        self._blocks = deque()
        self._rest = b""
        self._size = 0
        self._stream = None
        self._last_error = ""
        self._max_buffer = self.sample_rate * 2 * 4 // 3

    @property
    def active(self):
        try:
            return self._stream is not None and self._stream.active
        except Exception:
            return False

    @property
    def last_error(self):
        return self._last_error

    def start(self):
        import sounddevice as sd
        # Sin señal hasta recibir un bloque del motor. Volumen neutro;
        # la ganancia y la EQ ya se aplicaron antes de feed().
        stream = sd.OutputStream(
            device=self.device, samplerate=self.sample_rate,
            channels=2, dtype="float32", latency="low", blocksize=0,
            callback=self._callback)
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def feed(self, pcm: bytes):
        if not self.active or not pcm:
            return
        if len(pcm) % 8:
            raise ValueError("PCM estéreo float32 incompleto")
        with self._lock:
            self._blocks.append(bytes(pcm))
            self._size += len(pcm)
            # No bloquear la captura ni introducir segundos de retardo.
            while self._size > self._max_buffer and self._blocks:
                old = self._blocks.popleft()
                self._size -= len(old)
            if self._size > self._max_buffer:
                self._rest = b""

    def _callback(self, outdata, frames, time_info, status):
        outdata.fill(0)
        samples = outdata.reshape(-1)
        needed = int(frames) * 8
        chunks = []
        with self._lock:
            if self._rest:
                take = min(needed, len(self._rest))
                chunks.append(self._rest[:take])
                self._rest = self._rest[take:]
                needed -= take
            while needed > 0 and self._blocks:
                block = self._blocks.popleft()
                self._size -= len(block)
                take = min(needed, len(block))
                chunks.append(block[:take])
                if take < len(block):
                    self._rest = block[take:]
                needed -= take
        if chunks:
            pcm = b"".join(chunks)
            data = np.frombuffer(pcm, dtype="<f4")
            samples[:len(data)] = data

    def stop(self):
        stream = self._stream
        self._stream = None
        with self._lock:
            self._blocks.clear()
            self._rest = b""
            self._size = 0
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
