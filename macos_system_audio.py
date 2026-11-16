"""Captura nativa del audio de macOS y entradas USB.

En Sonoma, ScreenCaptureKit puede leer el audio del sistema, incluido el
sonido de YouTube enviado a Roland FANTOM, sin usar el bus de entrada del
instrumento. No altera la salida predeterminada del Mac.
"""
from __future__ import annotations

import collections
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

SYSTEM_AUDIO_SOURCE="macos:system-audio"
SCK_SAMPLE_RATE=48000


def system_audio_helper():
    """Binario específico de macOS, empaquetado o en el árbol de trabajo."""
    if sys.platform!="darwin":
        return None
    locations=[]
    override=os.environ.get("STEMMIDI_SYSTEM_AUDIO_CAPTURE_BIN","").strip()
    if override:
        locations.append(Path(override).expanduser())
    try:
        from studio_paths import resource_root
        locations.append(resource_root(__file__)/"vendor/native/bin/stemmidi-system-audio")
    except (OSError,ImportError):
        pass
    locations.append(Path(__file__).resolve().parent.parent/"native/bin/stemmidi-system-audio")
    for p in locations:
        if p.is_file() and os.access(p,os.X_OK):
            return p
    return None


def record_system_audio(stop_event,rate=48000,frames=4096):
    if system_audio_library() is not None:
        # El permiso de pantalla pertenece al proceso principal de la app,
        # nunca a un ejecutable auxiliar con otra identidad de firma.
        yield from record_system_audio_inprocess(stop_event,rate,frames)
        return
    raise RuntimeError("Motor de captura macOS integrado no disponible. "
                       "Falta libstemmidi-capture.dylib.")


def _legacy_external_capture_unused(stop_event,rate=48000,frames=4096):
    """F32 estéreo desde la mezcla de salida real de macOS.

    ScreenCaptureKit entrega 48 kHz aunque se solicite otra frecuencia.
    FFmpeg remuestrea en flujo cuando el usuario elige 44,1/96/192 kHz.
    Nunca escribir audio temporal en un volumen de solo lectura.
    """
    helper=system_audio_helper()
    if helper is None:
        raise RuntimeError("No está incluido el motor de captura del audio "
                           "del sistema para macOS. Reinstala StemMIDI Studio.")
    rate=int(rate)
    diagnostics=collections.deque(maxlen=30)
    processes=[]
    drains=[]
    def drain(name,pipe):
        try:
            for chunk in iter(pipe.readline,b""):
                line=chunk.decode("utf-8",errors="replace").strip()
                if line:diagnostics.append(name+": "+line)
        except (OSError,ValueError):
            pass

    def launch(args,stdin=None):
        process=subprocess.Popen(
            args,stdin=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            bufsize=0)
        processes.append(process)
        thread=threading.Thread(target=drain,args=(Path(args[0]).name,process.stderr),daemon=True)
        thread.start();drains.append(thread)
        return process

    try:
        source=launch([str(helper),"48000"])
        stream=source.stdout
        decoder=None
        if rate!=SCK_SAMPLE_RATE:
            ffmpeg=helper.with_name("ffmpeg")
            ffmpeg=str(ffmpeg if ffmpeg.is_file() else shutil.which("ffmpeg") or "ffmpeg")
            decoder=launch([
                ffmpeg,"-nostdin","-hide_banner","-loglevel","error",
                "-f","f32le","-ar","48000","-ac","2","-i","pipe:0",
                "-ar",str(rate),"-ac","2","-f","f32le","pipe:1"],
                stdin=source.stdout)
            # El único consumidor de la captura pasa a ser FFmpeg.
            source.stdout.close()
            stream=decoder.stdout
        started=time.monotonic()
        captured=False
        pending=b""
        while not stop_event.is_set():
            r,_,_=select.select([stream],[],[],0.2)
            if not r:
                if not captured and time.monotonic()-started>9:
                    message=" | ".join(diagnostics)
                    raise RuntimeError("La captura de audio del sistema no "
                        "ha recibido señal. Comprueba en Ajustes del Sistema "
                        "→ Privacidad y seguridad → Grabación de pantalla y "
                        "audio del sistema que StemMIDI Studio tenga permiso. "
                        +message[-1000:])
                continue
            data=os.read(stream.fileno(),max(int(frames)*8,8192))
            if not data:
                if stop_event.is_set():break
                message=" | ".join(diagnostics)
                if captured:
                    raise RuntimeError("El motor de audio del sistema se "
                                       "ha interrumpido: "+message[-1000:])
                raise RuntimeError("No se pudo iniciar el audio del sistema. "
                    "Revisa el permiso de grabación de pantalla/audio en "
                    "Ajustes del Sistema. "+message[-1000:])
            buf=pending+data
            aligned=len(buf)-(len(buf)%8)
            pending=buf[aligned:]
            if aligned:
                captured=True
                yield buf[:aligned]
    finally:
        # Cierre controlado: sin zombie, sin alterar la salida de YouTube.
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
        for p in reversed(processes):
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
                try:p.wait(timeout=2)
                except subprocess.TimeoutExpired:pass
        for p in processes:
            for pipe in (p.stdout,p.stderr):
                if pipe is not None:
                    try:pipe.close()
                    except OSError:pass


def system_audio_permission_granted():
    """Permiso efectivo de esta app según macOS. Solo consulta; NO solicita.

    No confundir el interruptor visible en Ajustes con un permiso que
    efectivamente llegue a la identidad firmada de esta compilación.
    """
    path=system_audio_library()
    if path is None:
        return False
    try:
        import ctypes
        lib=ctypes.CDLL(str(path))
        check=lib.stemmidi_sck_permission_granted
        check.argtypes=()
        check.restype=ctypes.c_int
        return check()==1
    except (OSError,AttributeError):
        return False


def system_audio_library():
    """Biblioteca ScreenCaptureKit cargada DENTRO de StemMIDI Studio.

    El ejecutable auxiliar recibía una identidad TCC distinta y repetía
    el aviso de privacidad. La biblioteca conserva el contexto de firma
    y los permisos del proceso principal.
    """
    if sys.platform != "darwin":
        return None
    locations = []
    override = os.environ.get("STEMMIDI_SYSTEM_AUDIO_LIBRARY", "").strip()
    if override:
        locations.append(Path(override).expanduser())
    try:
        from studio_paths import resource_root
        locations.append(
            resource_root(__file__) / "vendor/native/lib/libstemmidi-capture.dylib"
        )
    except (ImportError, OSError):
        pass
    locations.append(
        Path(__file__).resolve().parent.parent / "native/lib/libstemmidi-capture.dylib"
    )
    for candidate in locations:
        if candidate.is_file():
            return candidate
    return None


def system_input_devices():
    """Entradas visibles a CoreAudio SIN abrir streams ni pedir permiso MIC.

    Los dispositivos físicos y virtuales se consultan por propiedades de
    hardware. Solo cuando el usuario selecciona una entrada y pulsa REC
    se solicitará el permiso de micrófono que macOS pueda necesitar.
    """
    import ctypes,json
    path=system_audio_library()
    if path is None:
        return []
    try:
        library=ctypes.CDLL(str(path))
        method=library.stemmidi_input_devices_json
        method.argtypes=()
        method.restype=ctypes.c_char_p
        raw=method()
        devices=json.loads(raw.decode("utf-8")) if raw else []
        return [item for item in devices if isinstance(item,dict)
                and item.get("name") and int(item.get("channels",0))>0]
    except (OSError,AttributeError,UnicodeError,ValueError):
        return []


def system_output_name():
    """Nombre de la salida predeterminada CoreAudio SIN leer micrófonos."""
    import ctypes
    path=system_audio_library()
    if path is None:
        return "salida actual de macOS"
    try:
        library=ctypes.CDLL(str(path))
        function=library.stemmidi_system_output_name
        function.argtypes=()
        function.restype=ctypes.c_char_p
        name=function()
        return name.decode("utf-8",errors="replace") if name else "salida actual de macOS"
    except (OSError,AttributeError,UnicodeError):
        return "salida actual de macOS"


def record_system_audio_inprocess(stop_event, rate=48000, frames=4096):
    """Generador PCM desde ScreenCaptureKit en el PROPIO proceso autorizado.

    Una tubería enlaza la devolución asíncrona del SDK con CaptureWorker,
    y FFmpeg remuestrea cuando el usuario elige otra tasa.
    """
    import ctypes

    path = system_audio_library()
    if path is None:
        raise RuntimeError("Falta libstemmidi-capture.dylib en el paquete macOS")
    lib = ctypes.CDLL(str(path))
    lib.stemmidi_sck_run.argtypes = (ctypes.c_int, ctypes.c_int)
    lib.stemmidi_sck_run.restype = ctypes.c_int
    lib.stemmidi_sck_stop.argtypes = ()
    lib.stemmidi_sck_last_error.argtypes = ()
    lib.stemmidi_sck_last_error.restype = ctypes.c_char_p
    rate = int(rate)
    read_fd, write_fd = os.pipe()
    # Si la GUI se retrasa, no bloquear el hilo de captura de CoreAudio.
    os.set_blocking(write_fd, False)
    result = []
    failures = []

    def _capture_thread():
        try:
            result.append(lib.stemmidi_sck_run(48000, write_fd))
        except Exception as error:
            failures.append(str(error))
        finally:
            os.close(write_fd)

    thread = threading.Thread(
        target=_capture_thread, name="StemMIDI-ScreenCaptureKit", daemon=True
    )
    process = None
    stream_fd = read_fd
    output = None
    try:
        thread.start()
        if rate != 48000:
            from studio_paths import resource_root
            ffmpeg = resource_root(__file__) / "vendor/native/bin/ffmpeg"
            if not ffmpeg.is_file():
                ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("Falta FFmpeg para remuestrear la captura del Mac")
            process = subprocess.Popen([
                str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error",
                "-f", "f32le", "-ar", "48000", "-ac", "2", "-i", "pipe:0",
                "-ar", str(rate), "-ac", "2", "-f", "f32le", "pipe:1",
            ], stdin=read_fd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            os.close(read_fd)
            read_fd = -1
            stream_fd = process.stdout.fileno()
        started = time.monotonic()
        got_audio = False
        pending = b""
        while not stop_event.is_set():
            ready, _, _ = select.select([stream_fd], [], [], 0.2)
            if not ready:
                if time.monotonic() - started > 10 and not got_audio:
                    reason = lib.stemmidi_sck_last_error()
                    detail = (reason.decode("utf-8", errors="replace") if reason
                              else "no llegaron datos PCM")
                    raise RuntimeError(
                        "No se pudo iniciar la captura de audio del sistema. "
                        + detail
                    )
                continue
            chunk = os.read(stream_fd, max(4096, int(frames) * 8))
            if not chunk:
                if stop_event.is_set():
                    break
                reason = lib.stemmidi_sck_last_error()
                detail = (reason.decode("utf-8", errors="replace") if reason else "")
                if process is not None and process.poll() not in (0, None):
                    err = process.stderr.read(1200)
                    detail += " " + err.decode("utf-8", errors="replace")
                raise RuntimeError(
                    "La captura ScreenCaptureKit terminó inesperadamente. "
                    + (detail or str(failures or result))
                )
            data = pending + chunk
            aligned = len(data) - len(data) % 8
            pending = data[aligned:]
            if aligned:
                got_audio = True
                yield data[:aligned]
    finally:
        lib.stemmidi_sck_stop()
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        if read_fd >= 0:
            os.close(read_fd)
        if process is not None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    try:
                        pipe.close()
                    except OSError:
                        pass
        thread.join(timeout=3)
