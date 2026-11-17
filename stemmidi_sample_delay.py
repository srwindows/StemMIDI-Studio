"""Sample Delay original y nativo integrado en StemMIDI Studio.

Función equivalente de utilidad: retraso independiente de muestras L/R,
modo enlace, presentación samples/ms. No usa VST3, AU ni código de Logic.
"""
from __future__ import annotations
import ctypes
import sys
from pathlib import Path

import numpy as np

MAX_SAMPLES = 10000
DEFAULT_RATE = 48000
_PTR = ctypes.POINTER(ctypes.c_float)
_LIBRARY = None


def _lib():
    global _LIBRARY
    if _LIBRARY is not None:
        return _LIBRARY
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = (
        root / "libstemmidi_sample_delay.dylib",
        root / "vendor/native/lib/libstemmidi_sample_delay.dylib",
        Path(__file__).resolve().parent / "libstemmidi_sample_delay.dylib",
    )
    for file in candidates:
        if file.is_file():
            library = ctypes.CDLL(str(file))
            library.stem_sample_delay_create.restype = ctypes.c_void_p
            library.stem_sample_delay_destroy.argtypes = [ctypes.c_void_p]
            library.stem_sample_delay_reset.argtypes = [ctypes.c_void_p]
            library.stem_sample_delay_set.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
            library.stem_sample_delay_process.argtypes = [ctypes.c_void_p,_PTR,_PTR,ctypes.c_int]
            _LIBRARY = library
            return library
    raise RuntimeError("No está instalada la biblioteca interna Sample Delay")


class SampleDelay:
    """Procesador stereo de estado persistente para bus o canal."""

    is_effect = True

    def __init__(self, left_samples=0, right_samples=0, linked=False, rate=DEFAULT_RATE):
        self.rate = int(rate)
        self._library = _lib()
        self._handle = self._library.stem_sample_delay_create()
        if not self._handle:
            raise MemoryError("No se pudo reservar Sample Delay")
        self._left = 0
        self._right = 0
        self._linked = bool(linked)
        self._units = "samples"
        self.delay_left_samples = left_samples
        self.delay_right_samples = right_samples
        if self._linked:
            self.delay_right_samples = self._left

    def __del__(self):
        handle = getattr(self, "_handle", None)
        if handle:
            self._library.stem_sample_delay_destroy(handle)
            self._handle = None

    def _set(self):
        self._library.stem_sample_delay_set(self._handle, self._left, self._right)

    @property
    def delay_left_samples(self):
        return self._left

    @delay_left_samples.setter
    def delay_left_samples(self, value):
        self._left = min(MAX_SAMPLES, max(0, round(float(value))))
        if self._linked:
            self._right = self._left
        self._set()

    @property
    def delay_right_samples(self):
        return self._right

    @delay_right_samples.setter
    def delay_right_samples(self, value):
        self._right = min(MAX_SAMPLES, max(0, round(float(value))))
        if self._linked:
            self._left = self._right
        self._set()

    @property
    def delay_left_ms(self):
        return self._left * 1000. / self.rate

    @delay_left_ms.setter
    def delay_left_ms(self, value):
        self.delay_left_samples = round(float(value) * self.rate / 1000.)

    @property
    def delay_right_ms(self):
        return self._right * 1000. / self.rate

    @delay_right_ms.setter
    def delay_right_ms(self, value):
        self.delay_right_samples = round(float(value) * self.rate / 1000.)

    @property
    def linked(self):
        return self._linked

    @linked.setter
    def linked(self, value):
        self._linked = bool(value)
        if self._linked:
            self.delay_right_samples = self._left

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if value not in ("samples", "ms"):
            raise ValueError(value)
        self._units = value

    def reset(self):
        self._library.stem_sample_delay_reset(self._handle)

    def process(self, audio, sample_rate=DEFAULT_RATE, buffer_size=None, reset=False):
        # Compatible con interfaz channel-first de nuestros INSERT existentes.
        inp = np.asarray(audio,dtype=np.float32)
        if inp.ndim != 2 or inp.shape[0] != 2:
            raise ValueError("Sample Delay requiere dos canales de audio")
        if sample_rate != self.rate:
            raise ValueError("Frecuencia de Sample Delay distinta de la del motor")
        if reset:
            self.reset()
        in_stereo = np.ascontiguousarray(inp.T)
        out_stereo = np.empty_like(in_stereo)
        frames = in_stereo.shape[0]
        self._library.stem_sample_delay_process(
            self._handle,
            in_stereo.ctypes.data_as(_PTR),
            out_stereo.ctypes.data_as(_PTR),
            frames,
        )
        return out_stereo.T.copy()

    def process_stereo(self, stereo):
        inp = np.ascontiguousarray(stereo,dtype=np.float32)
        if inp.ndim != 2 or inp.shape[1] != 2:
            raise ValueError("Sample Delay requiere stereo (frames,2)")
        out = np.empty_like(inp)
        self._library.stem_sample_delay_process(
            self._handle, inp.ctypes.data_as(_PTR),out.ctypes.data_as(_PTR),len(inp)
        )
        return out
