"""Consola profesional conservada para Compositor, ventana nativa redimensionable.

No recrear la consola en cada apertura: instancia persistente, controles
y motor PCM idénticos a los ya implantados. La pestaña Mezclador sencilla
es independiente, pero ambas comparten catálogo y los faders de Inicio.
"""
from __future__ import annotations
from PySide6.QtCore import Qt,QTimer,QSignalBlocker
from PySide6.QtWidgets import QDialog,QVBoxLayout,QApplication,QPushButton
from studio_pro_console import StudioProConsole,ProConsoleTransport


class ComposerAdvancedMixerDialog(QDialog):
    def __init__(self,composer):
        super().__init__(composer.main)
        self.composer=composer
        self.main=composer.main
        self.setObjectName("composerAdvancedMixerFloating")
        self.setWindowTitle("StemMIDI Studio · Compositor · Consola profesional")
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint |
                            Qt.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(720,500)
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose,False)
        self.setStyleSheet("QDialog#composerAdvancedMixerFloating{"
                           "background:#071521;color:#d7f4ff;}")
        layout=QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(0)
        self.view=StudioProConsole(self.main.studio_home,self)
        layout.addWidget(self.view,1)
        self.transport=ProConsoleTransport(self.view,self.view)
        self.view.install_console_transport(self.transport)
        self.view.float_button.hide()
        self._last_project=None
        self._linked_simple_source=set()
        self.resize_to_display()
        self.setToolTip(
            "Consola avanzada del Compositor: EQ, dinámica, efectos y ruteo. "
            "Arrastra cualquier borde o esquina para cambiar el tamaño.")

    def resize_to_display(self):
        screen=QApplication.primaryScreen()
        if screen is None:return
        bounds=screen.availableGeometry()
        width=min(1350,max(720,bounds.width()-80))
        height=min(855,max(500,bounds.height()-80))
        self.resize(width,height)

    def synchronize(self):
        self.view.refresh_catalog(force=True)
        simple_dock=getattr(self.main,"mixer_professional",None)
        simple=(getattr(simple_dock,"view",None)
                if simple_dock is not None else None)
        project=getattr(self.main,"project_dir",None)
        project_id=str(project) if project else None
        # Si el proyecto cambia, no mezclar las pistas del anterior.
        if project_id!=self._last_project:
            self.view.selected.clear()
            self._last_project=project_id
        if simple is not None:
            simple.refresh_catalog(force=True)
            if not self.view.selected:
                self.view.selected.update(
                    key for key in simple.selected if key in self.view.sources)
                self.view.checked_mutes.update(simple.checked_mutes)
                self.view.extra_gains.update(simple.extra_gains)
                self.view._sync_channels()
                self._linked_simple_source=set(self.view.selected)
        self.transport.selection_changed()

    def open_or_raise(self):
        self.synchronize()
        # La salida PCM simple y la avanzada nunca se reproducen a la vez.
        simple=getattr(getattr(self.main,"mixer_professional",None),"transport",None)
        if simple is not None and simple.live.running:simple.live.stop()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self,event):
        # Cerrar NO destruye ajustes, voces, buses, efectos ni presets.
        if self.transport.live.running:self.transport.live.stop()
        super().closeEvent(event)


def open_console_for_composer(composer):
    existing=getattr(composer,"_pro_mixer_dialog",None)
    if existing is None:
        existing=ComposerAdvancedMixerDialog(composer)
        composer._pro_mixer_dialog=existing
    existing.open_or_raise()
    return existing
