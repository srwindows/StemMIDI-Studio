"""Ecualizador FIR estéreo, en tiempo real, para el PCM de captura.

Filtros de tono independientes: shelving graves, campana de medios,
shelving agudos. Muestras originales y procesadas no se confunden.
La misma ruta procesada alimenta los vúmetros y el codificador.
Sin dependencias nuevas aparte de NumPy (ya requerido por captura).
"""
from __future__ import annotations

import numpy as np

TAPS=513
LOW_HZ=180.
MID_HZ=1200.
HIGH_HZ=3600.

def filter_taps(sample_rate:int,bass_db=0,mid_db=0,treble_db=0):
    sample_rate=int(sample_rate)
    if sample_rate < 8000 or sample_rate > 384000:
        raise ValueError("Frecuencia de captura no válida")
    gains=(float(bass_db),float(mid_db),float(treble_db))
    if any(not np.isfinite(x) or abs(x)>12 for x in gains):
        raise ValueError("Ganancia del EQ fuera de ±12 dB")
    # Un filtro FIR de fase lineal en lugar de tres IIR implementados en
    # Python: NumPy realiza las FFT fuera de los bucles de muestras.
    length=8192
    f=np.fft.rfftfreq(length,1./sample_rate)
    f_safe=np.maximum(f,.1)
    low=1./(1.+(f_safe/LOW_HZ)**2.25)
    mid=np.exp(-.5*(np.log2(f_safe/MID_HZ)/.95)**2)
    high=1.-1./(1.+(f_safe/HIGH_HZ)**2.25)
    total_db=gains[0]*low+gains[1]*mid+gains[2]*high
    response=10.**(total_db/20.)
    impulse=np.fft.irfft(response,n=length)
    # Recentrar respuesta de fase cero y ventana FIR continua, retraso
    # de (TAPS-1)/2 muestras. El estado entre bloques conserva la fase.
    half=TAPS//2
    taps=np.concatenate((impulse[-half:],impulse[:half+1]))
    taps*=np.hanning(TAPS)
    return taps.astype(np.float64)

class StereoCaptureEQ:
    """FIR por overlap-save; sin clicks en los límites de los bloques."""
    def __init__(self,sample_rate=48000):
        self.sample_rate=int(sample_rate)
        self._history=np.zeros((TAPS-1,2),dtype=np.float32)
        self._key=None
        self._taps=None
        self._cache_fft={}

    def process(self,stereo,enabled=True,bass_db=0,mid_db=0,treble_db=0):
        frames=np.asarray(stereo,dtype=np.float32)
        if frames.ndim!=2 or frames.shape[1]!=2:
            raise ValueError("El EQ requiere PCM estéreo")
        if not frames.shape[0]:
            return frames.copy()
        key=(int(bass_db),int(mid_db),int(treble_db)) if enabled else (0,0,0)
        history=self._history
        combined=np.concatenate((history,frames),axis=0)
        self._history=combined[-(TAPS-1):].copy()
        if key==(0,0,0):
            # El bypass es bit a bit idéntico al PCM de entrada.
            self._key=key
            return frames.copy()
        if self._key!=key or self._taps is None:
            self._taps=filter_taps(self.sample_rate,*key)
            self._cache_fft.clear()
            self._key=key
        n=frames.shape[0]
        fft_size=1 << (len(combined)+TAPS-2).bit_length()
        kernel_fft=self._cache_fft.get(fft_size)
        if kernel_fft is None:
            kernel_fft=np.fft.rfft(self._taps,n=fft_size)
            self._cache_fft[fft_size]=kernel_fft
        block_fft=np.fft.rfft(combined,n=fft_size,axis=0)
        result=np.fft.irfft(block_fft*kernel_fft[:,None],n=fft_size,axis=0)
        return result[TAPS-1:TAPS-1+n].astype(np.float32)
