"""Vídeo de presentación aprobado de StemMIDI Studio.

La fuente ejecutada desde Python usa Qt Multimedia; el lanzador de la
compilación Debian lo reproduce externamente antes de arrancar el binario.
STEMMIDI_INTRO_PLAYED evita mostrarlo dos veces tras una recompilación.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QDialog, QVBoxLayout, QApplication

from studio_paths import workspace_root


def intro_path() -> Path:
    """Localiza el vídeo aprobado en recursos empaquetados o en el proyecto.

    En un paquete PyInstaller los recursos son de solo lectura; no buscar
    el vídeo exclusivamente en las preferencias del usuario.
    """
    name="StemMIDI_Intro_Definitiva.mp4"
    candidates=[]
    bundle=getattr(sys,"_MEIPASS",None)
    if bundle:
        candidates.append(Path(bundle)/"intro"/name)
    candidates.extend((
        Path(__file__).resolve().parent/"intro"/name,
        workspace_root(__file__)/"intro"/name,
    ))
    for video in candidates:
        if video.is_file():
            return video
    return candidates[0]


def _intro_player():
    """FFplay del paquete si está incluido, o reproductor del sistema."""
    candidates=[]
    bundle=getattr(sys,"_MEIPASS",None)
    if bundle:
        root=Path(bundle)
        candidates.extend((
            root/"vendor"/"native"/"bin"/"ffplay",
            root/"vendor"/"ffmpeg"/"ffplay.exe",
        ))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffplay")


def play_external_intro() -> bool:
    """Reproduce la intro antes de crear la ventana de Qt en Debian.

    FFplay es el reproductor del sistema comprobado con el MP4 aprobado.
    Se espera a que termine: la ventana principal no puede tapar la intro.
    Si no está disponible o falla, main.py utiliza el reproductor Qt.
    """
    if os.environ.get("STEMMIDI_INTRO_PLAYED") == "1":
        return True
    video = intro_path()
    if not video.is_file():
        return False
    player = _intro_player()
    if not player:
        return False
    env = os.environ.copy()
    if sys.platform == "linux":
        env.setdefault("SDL_AUDIODRIVER", "pulseaudio")
    command = [
        player, "-hide_banner", "-loglevel", "error", "-autoexit",
        "-fs", "-noborder", "-window_title", "StemMIDI Studio - Intro",
        "-exitonkeydown", str(video),
    ]
    try:
        completed = subprocess.run(
            command, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    os.environ["STEMMIDI_INTRO_PLAYED"] = "1"
    return True


def start_external_intro():
    """Iniciar la intro sin bloquear la construcción de la ventana principal.

    La duración, el audio y el vídeo originales NO se alteran.
    El programa trabaja en memoria mientras FFplay reproduce la intro.
    """
    if os.environ.get("STEMMIDI_INTRO_PLAYED") == "1":
        return None
    video=intro_path()
    if not video.is_file():
        return None
    # On macOS FFplay can remain stuck in Cocoa/SDL and a Qt video
    # QDialog can deadlock on QMediaPlayer.stop(). The intro therefore
    # runs in its OWN copy of the app, never in the main GUI process.
    if sys.platform=="darwin":
        if getattr(sys,"frozen",False):
            command=[sys.executable,"--stemmidi-intro-child"]
        else:
            command=[sys.executable,
                     str(Path(__file__).resolve().parent/"main.py"),
                     "--stemmidi-intro-child"]
        try:
            proc=subprocess.Popen(
                command,env=os.environ.copy(),stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError:
            return None
        proc._stemmidi_intro_start=time.monotonic()
        proc._stemmidi_intro_child=True
        return proc
    player=_intro_player()
    if not player:return None
    env=os.environ.copy()
    if sys.platform=="linux":
        env.setdefault("SDL_AUDIODRIVER","pulseaudio")
    # Duración aprobada del MP4: 11.375 s. El límite -t evita que una
    # instancia FFplay/Sdl permanezca abierta indefinidamente en macOS
    # después de terminar el último fotograma y retrase el programa.
    command=[player,"-hide_banner","-loglevel","error","-autoexit",
             "-fs","-noborder","-t","11.4",
             "-window_title","StemMIDI Studio - Intro",str(video)]
    try:
        return subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except OSError:
        return None


def finish_external_intro(process):
    """Esperar solamente los segundos restantes de la intro aprobada."""
    if process is None:
        return os.environ.get("STEMMIDI_INTRO_PLAYED")=="1"
    is_child=getattr(process,"_stemmidi_intro_child",False)
    # Hard deadline measured from LAUNCH, not from completion of window
    # construction. Never leave a stuck video over the main application.
    timeout=(
        max(.1,17.5-(time.monotonic()-process._stemmidi_intro_start))
        if is_child else 25)
    try:
        status=process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if is_child:
            # A damaged video cannot delay the application again.
            os.environ["STEMMIDI_INTRO_PLAYED"]="1"
            return True
        return False
    if is_child:
        # Return even if the child failed: unlike R24, NEVER fall back to a
        # Qt QMediaPlayer inside the main app and re-create its deadlock.
        os.environ["STEMMIDI_INTRO_PLAYED"]="1"
        return True
    if status!=0:return False
    os.environ["STEMMIDI_INTRO_PLAYED"]="1"
    return True


class IntroVideo(QDialog):
    """Vídeo a pantalla completa, termina al acabar, ante un error o al omitir."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("StemMIDI Studio")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background: #020a1a;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.screen_video = QVideoWidget(self)
        layout.addWidget(self.screen_video)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.9)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.screen_video)
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(self._error)
        self.player.setSource(QUrl.fromLocalFile(str(intro_path())))
        # Protección ante ficheros dañados o motores sin eventos de finalización.
        QTimer.singleShot(18000, self.finish)

    def start(self):
        # macOS Qt fullscreen creates a new Space and sometimes leaves this
        # frameless QDialog with 0×0 geometry: sound plays, frames are invisible.
        # A borderless maximized-size window uses the real screen rectangle.
        screen=QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, self.player.play)

    def _status(self, state):
        if state in (QMediaPlayer.MediaStatus.EndOfMedia,
                     QMediaPlayer.MediaStatus.InvalidMedia):
            self.finish()

    def _error(self, *_):
        self.finish()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Q, Qt.Key_Space):
            self.finish()
        else:
            super().keyPressEvent(event)

    def finish(self):
        # On macOS QMediaPlayer.stop can synchronously wait forever for the
        # FFmpeg backend's semaphore. A dedicated intro child exits just
        # after this dialog closes, releasing audio/video resources at OS
        # level without making this synchronous backend call.
        if sys.platform != "darwin":
            self.player.stop()
        self.accept()


def play_intro():
    if os.environ.get("STEMMIDI_INTRO_PLAYED") == "1":
        return
    if not intro_path().is_file():
        return
    dialog = IntroVideo()
    dialog.start()
    dialog.exec()
