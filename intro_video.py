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
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QDialog, QVBoxLayout

from studio_paths import workspace_root


def intro_path() -> Path:
    return workspace_root(__file__) / "intro" / "StemMIDI_Intro_Definitiva.mp4"


def play_external_intro() -> bool:
    """Reproduce la intro antes de crear la ventana de Qt en Debian.

    FFplay es el reproductor del sistema comprobado con el MP4 aprobado.
    Se espera a que termine: la ventana principal no puede tapar la intro.
    Si no está disponible o falla, main.py utiliza el reproductor Qt.
    """
    if os.environ.get("STEMMIDI_INTRO_PLAYED") == "1":
        return True
    video = intro_path()
    if not video.is_file() or sys.platform != "linux":
        return False
    player = shutil.which("ffplay")
    if not player:
        return False
    env = os.environ.copy()
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
            timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    os.environ["STEMMIDI_INTRO_PLAYED"] = "1"
    return True


class IntroVideo(QDialog):
    """Vídeo a pantalla completa, termina al acabar, ante un error o al omitir."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("StemMIDI Studio")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
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
        QTimer.singleShot(10500, self.finish)

    def start(self):
        self.showFullScreen()
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
