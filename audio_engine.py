#!/usr/bin/env python3
"""Captura y codificación de audio de PipeWire/PulseAudio sin alterar las salidas."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal

SAMPLE_RATE = 48000
CHANNELS = 2
CAPTURE_BYTES_PER_SAMPLE = 4  # parec y grabación nativa entregan float32le

def recorded_seconds(bytes_written, sample_rate):
    """Tiempo de audio PCM aceptado por FFmpeg, excluye las pausas.

    El formato de salida (WAV 16/24/32, FLAC, MP3...) no cambia el
    formato de captura: siempre son muestras float32le estéreo.
    """
    rate = int(sample_rate)
    if rate <= 0:
        raise ValueError("Frecuencia de captura inválida")
    return max(0,int(bytes_written)) / (rate * CHANNELS * CAPTURE_BYTES_PER_SAMPLE)

# La captura emplea muestras float32 (sin truncar la fuente a PCM de 16 bits).
# La frecuencia elegida puede exigir remuestreo en PipeWire: no crea
# detalle que no exista en la fuente o en la interfaz física.
SAMPLE_RATES = (44100,48000,88200,96000,176400,192000)
FORMAT_OPTIONS = {
    "WAV (PCM 24 bits · estudio)": ("wav", ["-c:a","pcm_s24le"]),
    "WAV (32 bits float · máster)": ("wav", ["-c:a","pcm_f32le"]),
    "WAV (PCM 32 bits)": ("wav", ["-c:a","pcm_s32le"]),
    "WAV (PCM 16 bits)": ("wav", ["-c:a","pcm_s16le"]),
    "BWF (PCM 24 bits · broadcast)": ("wav", ["-c:a","pcm_s24le","-write_bext","1"]),
    "AIFF (PCM 24 bits)": ("aiff", ["-c:a","pcm_s24be"]),
    "FLAC (24 bits sin pérdida)": ("flac", ["-c:a","flac","-sample_fmt","s32","-bits_per_raw_sample","24","-compression_level","5"]),
    "FLAC (16 bits sin pérdida)": ("flac", ["-c:a","flac","-sample_fmt","s16","-compression_level","5"]),
    "MP3 (320 kb/s)": ("mp3", ["-c:a","libmp3lame","-b:a","320k"]),
    "AAC / M4A (320 kb/s)": ("m4a", ["-c:a","aac","-b:a","320k"]),
    "Opus (256 kb/s)": ("opus", ["-c:a","libopus","-b:a","256k"]),
}



def list_sources(include_mics=False):
    """Fuentes según el motor de audio del sistema operativo."""
    if sys.platform!="linux":
        from native_capture import get_sources
        return get_sources(include_mics)
    cmd = ["pactl", "-f", "json", "list", "sinks"]
    results = []
    try:
        sinks = json.loads(subprocess.run(cmd, capture_output=True, check=True, timeout=5).stdout)
        for sink in sinks:
            monitor = sink.get("monitor_source", "")
            if not monitor:
                continue
            props = sink.get("properties", {})
            label = props.get("device.description") or props.get("node.nick") or sink.get("name", "Salida")
            # Algunas versiones de PipeWire devuelven '(null)' para description.
            if not label or label == "(null)":
                label = props.get("device.description", "Salida")
            results.append({"name": monitor, "label": f"Salida: {label}", "kind": "monitor"})
        if include_mics:
            sources = json.loads(subprocess.run(
                ["pactl", "-f", "json", "list", "sources"],
                capture_output=True, check=True, timeout=5).stdout)
            for source in sources:
                name = source.get("name", "")
                if ".monitor" in name or not name:
                    continue
                label = source.get("description", "")
                if not label or label == "(null)":
                    label = source.get("properties", {}).get("device.description") or name
                results.append({"name": name, "label": f"Entrada: {label}", "kind": "input"})
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError(f"No se pudo consultar el servidor de audio: {exc}") from exc
    return results


def default_monitor():
    if sys.platform!="linux":
        from native_capture import default_source
        return default_source()
    try:
        sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True,
                              text=True, check=True, timeout=3).stdout.strip()
        return sink + ".monitor"
    except (OSError, subprocess.SubprocessError):
        return None


class CaptureWorker(QThread):
    levels = Signal(float, float, float, float)
    visual = Signal(object, object)
    capture_state = Signal(bool, str)
    recording_state = Signal(bool, str)
    recording_finished = Signal(str, bool, str)

    def __init__(self, source: str, parent=None, sample_rate=SAMPLE_RATE):
        super().__init__(parent)
        self.source = source
        if int(sample_rate) not in SAMPLE_RATES:
            raise ValueError("Frecuencia de grabación no admitida")
        self.sample_rate = int(sample_rate)
        # Posprocesamiento de captura, independiente del volumen del sistema.
        self._gain_db = 0
        self._balance = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending_start = None
        self._pending_stop = False
        self._rec = None
        self._rec_path = None
        self._rec_bytes = 0
        self._record_paused = False
        self._capture = None
        self._window = np.hanning(2048).astype(np.float32)
        self._edges = np.unique(np.clip(
            np.rint(np.geomspace(2, 2048 // 2, 49)).astype(int), 1, 1024))
        self._last_visual = 0.0

    def set_input_controls(self, gain_db=0, balance=0):
        """Ajustes atómicos para una captura en curso (sin tocar el dispositivo)."""
        gain_db=int(gain_db)
        balance=int(balance)
        if not -60<=gain_db<=12 or not -100<=balance<=100:
            raise ValueError("Nivel o balance fuera del intervalo")
        with self._lock:
            self._gain_db=gain_db
            self._balance=balance

    @staticmethod
    def apply_input_controls(pcm, gain_db=0, balance=0):
        """Ganancia y balance estéreo en float32, con centro de ganancia unidad.

        Balance no mezcla L/R: al desplazarlo, atenúa únicamente el lado
        opuesto. El audio nunca cambia de frecuencia o número de canales.
        """
        gain_db=int(gain_db)
        balance=int(balance)
        if not -60<=gain_db<=12 or not -100<=balance<=100:
            raise ValueError("Nivel o balance fuera del intervalo")
        if gain_db==0 and balance==0:
            return pcm
        data=np.frombuffer(pcm,dtype="<f4")
        if data.size % CHANNELS:
            raise ValueError("Bloque PCM estéreo incompleto")
        stereo=data.reshape(-1,CHANNELS).copy()
        gain=0.0 if gain_db==-60 else 10.0**(gain_db/20.0)
        left=gain*(1.0-max(balance,0)/100.0)
        right=gain*(1.0-max(-balance,0)/100.0)
        stereo[:,0]*=left
        stereo[:,1]*=right
        return stereo.tobytes()

    def _processed_chunk(self,pcm):
        with self._lock:
            gain=self._gain_db
            balance=self._balance
        return self.apply_input_controls(pcm,gain,balance)

    def request_recording(self, target_file: Path, format_name: str):
        with self._lock:
            if self._rec is not None or self._pending_start is not None:
                return False
            self._pending_start = (str(target_file), format_name)
        return True

    def request_stop_recording(self):
        with self._lock:
            self._pending_stop = True
            self._record_paused = False

    def set_record_paused(self,paused:bool):
        with self._lock:
            if self._rec is None and self._pending_start is None:
                return False
            self._record_paused=bool(paused)
            return True

    def stop_capture(self):
        self._stop.set()
        with self._lock:
            self._pending_stop = True
        process = self._capture
        if process and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    def _open_encoder(self, target, fmt):
        extension, codec = FORMAT_OPTIONS[fmt]
        assert target.lower().endswith("." + extension)
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError("El archivo ya existe; no se sobrescribirá")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-f", "f32le", "-ar", str(self.sample_rate),
                   "-ac", str(CHANNELS), "-i", "pipe:0", "-vn",
                   *codec, "-n", str(path)]
        self._rec = subprocess.Popen(command, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     bufsize=0)
        self._rec_path = str(path)
        self._rec_bytes = 0
        self._record_paused = False
        self.recording_state.emit(True, str(path))

    def _close_encoder(self):
        process, path, recorded = self._rec, self._rec_path, self._rec_bytes
        if process is None:
            return
        self._rec, self._rec_path, self._rec_bytes = None, None, 0
        with self._lock:
            self._record_paused=False
        try:
            if process.stdin:
                process.stdin.close()
            try:
                code = process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=2)
            err = process.stderr.read().decode("utf-8", "replace")[-600:] if process.stderr else ""
            success = code == 0 and recorded > 0 and os.path.getsize(path) > 0
            msg = f"{recorded_seconds(recorded,self.sample_rate):.1f} s grabados" if success else (err or "No se recibió audio")
        except (OSError, subprocess.SubprocessError) as exc:
            success, msg = False, str(exc)
        finally:
            if process.stderr:
                process.stderr.close()
        self.recording_state.emit(False, path or "")
        self.recording_finished.emit(path or "", success, msg)

    def _visualize(self, pcm):
        # float32le intercalado, cálculo de picos sin alterar muestras.
        samples = np.frombuffer(pcm, dtype="<f4")
        if len(samples) < 4:
            return
        if len(samples) % 2:
            samples = samples[:-1]
        stereo = samples.reshape(-1, 2)
        peak = np.max(np.abs(stereo), axis=0)
        rms = np.sqrt(np.mean(stereo ** 2, axis=0))
        self.levels.emit(float(rms[0]), float(rms[1]), float(peak[0]), float(peak[1]))
        now = time.monotonic()
        if now - self._last_visual < .055:
            return
        self._last_visual = now
        mono = np.mean(stereo, axis=1)
        if mono.size < 2048:
            mono = np.pad(mono, (0, 2048 - mono.size))
        else:
            mono = mono[:2048]
        fft = np.abs(np.fft.rfft(mono * self._window)) / 1024.
        spectrum = []
        for a, b in zip(self._edges[:-1], self._edges[1:]):
            strength = float(np.max(fft[a:max(a + 1, b)]))
            spectrum.append(max(0.0, min(1.0, (20.0 * math.log10(max(strength, 1e-7)) + 76.0) / 76.0)))
        wave = mono[::10][:205].tolist()
        self.visual.emit(spectrum, wave)

    def _run_native(self):
        from native_capture import record_chunks
        try:
            for pcm in record_chunks(self.source,self._stop,rate=self.sample_rate):
                if self._stop.is_set():break
                pcm=self._processed_chunk(pcm)
                with self._lock:
                    pending_start=self._pending_start
                    pending_stop=self._pending_stop
                    self._pending_start=None
                    self._pending_stop=False
                if pending_stop:self._close_encoder()
                if pending_start:
                    try:self._open_encoder(*pending_start)
                    except Exception as exc:
                        self.recording_state.emit(False,"")
                        self.recording_finished.emit(pending_start[0],False,str(exc))
                with self._lock:
                    paused=self._record_paused
                if self._rec is not None and not paused:
                    try:
                        self._rec.stdin.write(pcm)
                        self._rec_bytes+=len(pcm)
                    except (OSError,BrokenPipeError) as exc:
                        self._close_encoder()
                        self.capture_state.emit(True,f"Error de grabación: {exc}")
                self._visualize(pcm)
                if not getattr(self,"_reported_started",False):
                    self._reported_started=True
                    self.capture_state.emit(True,"Audio nativo supervisado")
        except Exception as exc:
            self.capture_state.emit(False,str(exc))
        finally:
            self._close_encoder()
            self.capture_state.emit(False,"Supervisión detenida")

    def run(self):
        if sys.platform!="linux":
            return self._run_native()
        command = ["parec", "--record", "--raw",
                   "--device=" + self.source,
                   "--rate=" + str(self.sample_rate),
                   "--channels=" + str(CHANNELS),
                   "--format=float32le",
                   "--latency-msec=90",
                   "--client-name=Monitor de Grabacion",
                   "--stream-name=Analisis de audio"]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, bufsize=0)
            self._capture = process
            # parec arranca bajo demanda al comenzar la lectura.
            while not self._stop.is_set():
                pcm = process.stdout.read(16384)
                if not pcm:
                    break
                pcm=self._processed_chunk(pcm)
                with self._lock:
                    pending_start = self._pending_start
                    pending_stop = self._pending_stop
                    self._pending_start = None
                    self._pending_stop = False
                if pending_stop:
                    self._close_encoder()
                if pending_start:
                    try:
                        self._open_encoder(*pending_start)
                    except Exception as exc:
                        self.recording_state.emit(False, "")
                        self.recording_finished.emit(pending_start[0], False, str(exc))
                with self._lock:
                    paused=self._record_paused
                if self._rec is not None and not paused:
                    try:
                        self._rec.stdin.write(pcm)
                        self._rec_bytes += len(pcm)
                    except (BrokenPipeError, OSError) as exc:
                        self._close_encoder()
                        self.capture_state.emit(True, f"Error de grabación: {exc}")
                self._visualize(pcm)
                if not getattr(self, "_reported_started", False):
                    self._reported_started = True
                    self.capture_state.emit(True, "Señal de audio supervisada")
            if not self._stop.is_set():
                stderr = process.stderr.read().decode("utf-8", "replace")[-400:]
                self.capture_state.emit(False, stderr or "Se ha desconectado la fuente de audio")
        except Exception as exc:
            self.capture_state.emit(False, f"Error al iniciar captura: {exc}")
        finally:
            self._close_encoder()
            if self._capture:
                if self._capture.poll() is None:
                    self._capture.terminate()
                try:
                    self._capture.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._capture.kill()
                    self._capture.wait(timeout=2)
                if self._capture.stdout:
                    self._capture.stdout.close()
                if self._capture.stderr:
                    self._capture.stderr.close()
            self._capture = None
            self.capture_state.emit(False, "Supervisión detenida")
