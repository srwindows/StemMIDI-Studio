"""Escucha multipista inmediata del módulo Audio→MIDI.

La selección sirve para conversión y para escucha. Los stems mantienen
su posición común; activar/desactivar una casilla aplica Mute sin reiniciar.
"""
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Qt
from low_latency_stem_mixer import LowLatencyStemMixer


class MidiStemListen(QObject):
    statusChanged=Signal(str)

    def __init__(self,browser):
        super().__init__(browser)
        self.browser=browser
        self.live=LowLatencyStemMixer(self)
        self._project=None
        self._catalog=()
        self.live.error.connect(self.statusChanged.emit)
        self.browser.home.player.playStateChanged.connect(
            lambda playing:self.stop() if playing and self.live.running else None)

    def entries(self):
        browser=self.browser
        result=[]
        for inventory in (browser.stems,browser.drums):
            for index in range(inventory.count()):
                item=inventory.item(index)
                path=Path(item.data(Qt.UserRole)).resolve()
                if path.is_file() and not path.is_symlink():
                    # El identificador es la ruta; los nombres pueden repetirse.
                    result.append((str(path),path))
        return result

    def selected(self):
        return {str(path.resolve()) for path in self.browser.checked()}

    def sync(self):
        browser=self.browser
        project=browser._project()
        current=(str(project),tuple(str(path) for _,path in self.entries()))
        if current!=self._catalog:
            if self.live.running:
                self.live.stop()
            self._catalog=current
        if self.live.running:
            selected=self.selected()
            for name,_ in self.entries():
                self.live.set_enabled(name,name in selected)

    def _duration_hint(self):
        # El analizador visual ya conoce el tiempo de cada archivo:
        # no invocar ffprobe 14 veces sobre el hilo de interfaz.
        seconds=[]
        for inventory in (self.browser.stems,self.browser.drums):
            for index in range(inventory.count()):
                row=inventory.itemWidget(inventory.item(index))
                if row is None or row.wave.duration_seconds<=0:
                    return None
                seconds.append(row.wave.duration_seconds)
        return round(max(seconds)*1000) if seconds else None

    def play(self):
        self.sync()
        chosen=self.selected()
        if not chosen:
            self.statusChanged.emit("Marca al menos una pista para escuchar.")
            return False
        if self.live.running:
            if self.live.paused:self.live.pause()
            return True
        entries=self.entries()
        if not entries:return False
        # Evitar que dos motores emitan sonido a la vez.
        self.browser.home.player.stop()
        other=getattr(self.browser.home,"_sep_listen",None)
        if other is not None and other.live.running:
            other.stop()
        duration=self._duration_hint()
        self.statusChanged.emit(f"Abriendo mezcla de {len(chosen)} pistas…")
        ok=self.live.start(entries,chosen,duration_ms=duration)
        if ok:self.statusChanged.emit(
            f"Escuchando {len(chosen)} pistas · cambio de mute inmediato")
        return ok

    def selected_changed(self):
        # La selección se aplica en el callback de audio, sin FFmpeg nuevo.
        if self.live.running:
            chosen=self.selected()
            for name,_ in self.entries():
                self.live.set_enabled(name,name in chosen)
            self.statusChanged.emit(
                f"Escuchando {len(chosen)} pistas" if chosen
                else "Pistas silenciadas · marca una para volver a escuchar")

    def pause(self):
        if self.live.running:self.live.pause()

    def stop(self):
        if self.live.running:self.live.stop()

    def seek(self,position_ms):
        if self.live.running:return self.live.seek(position_ms)
        return False

    def cleanup(self):
        self.stop()
