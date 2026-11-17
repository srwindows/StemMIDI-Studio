"""Salida CoreAudio nativa: C++ en el render thread; Python solo como productor.

La cola de muestras stereo tiene capacidad fija. En el callback CoreAudio
no se ejecuta Python ni VST: mezcla y plugins funcionan en otro hilo.
No usar esta clase para captura de audio. Solo salida de la consola.
"""
from __future__ import annotations
import ctypes
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

RATE = 48000
BLOCK = 512


def _load_library():
    paths = [
        Path(__file__).resolve().parent / "libstemmidi_coreaudio.dylib",
        Path(getattr(sys, "_MEIPASS", "")) / "libstemmidi_coreaudio.dylib",
        Path(getattr(sys, "_MEIPASS", "")) / "vendor/native/lib/libstemmidi_coreaudio.dylib",
    ]
    for path in paths:
        if not path.is_file():
            continue
        lib = ctypes.CDLL(str(path))
        lib.stem_output_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.stem_output_open.restype = ctypes.c_void_p
        lib.stem_output_start.argtypes = [ctypes.c_void_p]
        lib.stem_output_start.restype = ctypes.c_int
        lib.stem_output_stop.argtypes = [ctypes.c_void_p]
        lib.stem_output_close.argtypes = [ctypes.c_void_p]
        lib.stem_output_write.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        lib.stem_output_write.restype = ctypes.c_int
        lib.stem_output_buffered.argtypes = [ctypes.c_void_p]
        lib.stem_output_buffered.restype = ctypes.c_int
        lib.stem_output_underruns.argtypes = [ctypes.c_void_p]
        lib.stem_output_underruns.restype = ctypes.c_uint64
        lib.stem_output_device_latency_ms.argtypes = [ctypes.c_void_p]
        lib.stem_output_device_latency_ms.restype = ctypes.c_double
        lib.stem_output_unit_latency_ms.argtypes = [ctypes.c_void_p]
        lib.stem_output_unit_latency_ms.restype = ctypes.c_double
        return lib
    raise FileNotFoundError("Falta libstemmidi_coreaudio.dylib")


class NativeCoreAudioStream:
    """AudioUnit HAL; produce DSP en Python fuera del callback de tiempo real."""

    def __init__(self, callback, device_name: str, channels=2, rate=RATE, block=BLOCK):
        if sys.platform != "darwin":
            raise RuntimeError("CoreAudio solo funciona en macOS")
        self._lib = _load_library()
        self._callback = callback
        self._rate = int(rate)
        self._block = int(block)
        self._channels = int(channels)
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._worker = None
        self._handle = self._lib.stem_output_open(
            device_name.encode("utf-8"), self._rate, self._channels, self._block * 12
        )
        if not self._handle:
            raise RuntimeError(f"AudioUnit HAL no puede abrir {device_name} a {rate} Hz / {channels} ch")
        self._started = False
        self.last_error = ""

    @property
    def underruns(self):
        return int(self._lib.stem_output_underruns(self._handle)) if self._handle else 0

    @property
    def buffered_frames(self):
        return int(self._lib.stem_output_buffered(self._handle)) if self._handle else 0

    @property
    def coreaudio_latency_ms(self):
        return float(self._lib.stem_output_unit_latency_ms(self._handle)) if self._handle else -1.

    @property
    def device_latency_estimate_ms(self):
        return float(self._lib.stem_output_device_latency_ms(self._handle)) if self._handle else -1.

    def _generate(self):
        # Sondeo/llamadas a plugins solo desde este trabajador, nunca CoreAudio.
        block = np.zeros((self._block, self._channels), dtype=np.float32)
        block.fill(0.)
        self._callback(block, self._block, None, None)
        stereo = np.ascontiguousarray(block[:, :2], dtype=np.float32)
        return self._lib.stem_output_write(
            self._handle,
            stereo.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            self._block,
        )

    def _run(self):
        # Limitar la cola a 4 bloques: el render nativo empieza con tres.
        target = self._block * 4
        try:
            while not self._stop_event.is_set():
                if self.buffered_frames <= target - self._block:
                    if self._generate() == 0:
                        self._stop_event.wait(.002)
                else:
                    self._stop_event.wait(.001)
                if not self._started and self.buffered_frames >= self._block * 3:
                    error = self._lib.stem_output_start(self._handle)
                    if error:
                        self.last_error = f"AudioOutputUnitStart OSStatus={error}"
                        break
                    self._started = True
                    self._ready_event.set()
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {error}"
        finally:
            self._ready_event.set()

    def start(self):
        if self._worker is not None:
            return
        self._stop_event.clear()
        self._ready_event.clear()
        self._worker = threading.Thread(target=self._run, name="StemMIDI-NativeDSP-Producer", daemon=True)
        self._worker.start()
        if not self._ready_event.wait(timeout=1.5) or not self._started:
            error = self.last_error or "No se inició el trabajador CoreAudio"
            self.stop()
            raise RuntimeError(error)

    def stop(self):
        self._stop_event.set()
        # Detener AudioUnit ANTES de liberar el búfer o la instancia.
        if self._handle:
            self._lib.stem_output_stop(self._handle)
        worker = self._worker
        if worker and worker is not threading.current_thread():
            worker.join(timeout=1.5)
            if worker.is_alive():
                raise RuntimeError("Productor DSP no se detuvo, se impide liberar el buffer nativo")
        self._worker = None
        self._started = False

    def close(self):
        if not self._handle:
            return
        self.stop()
        self._lib.stem_output_close(self._handle)
        self._handle = None
