"""Puente entre la última ventana flotante buena y la consola Pro actual.

La interfaz recuperada procede de la copia de Recuperación del 8-11-2026
12:59. El mezclador profesional permanece EN su pestaña; la ventana clásica
muestra la selección/faders/transporte históricos y sincroniza los controles
de mezcla con la misma sesión y sin sonar simultáneamente.
"""
from mixer_floating_restored import ProjectMixerView
from PySide6.QtCore import Qt


class RestoredFloatingMixer(ProjectMixerView):
    restored_floating_mixer = True

    def __init__(self, home, professional, parent=None):
        self.professional = professional
        self._bridging = True
        super().__init__(home, parent)
        self._bridging = False

    def restore_from_professional(self):
        self._bridging = True
        try:
            self.professional.refresh_catalog(force=True)
            self.refresh_catalog(force=True)
            self.selected = self.professional.selected.intersection(self.sources)
            with self._block_file_signals():
                for i in range(self.file_list.count()):
                    item = self.file_list.item(i)
                    item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in self.selected
                                       else Qt.Unchecked)
            self.checked_mutes.update(self.professional.checked_mutes)
            self.extra_gains.update(self.professional.extra_gains)
            for key, channel in self.professional.channels.items():
                if channel["source"] is not None:
                    self.extra_gains[key] = channel["fader"].value()
                    self.checked_mutes[key] = channel["mute"].isChecked()
            self._sync_channels()
        finally:
            self._bridging = False

    def _block_file_signals(self):
        from PySide6.QtCore import QSignalBlocker
        return QSignalBlocker(self.file_list)

    def push_to_professional(self):
        if self._bridging:
            return
        pro = self.professional
        # Los archivos elegidos en la ventana flotante pueden haberse
        # añadido al proyecto después de abrir la pestaña principal.
        # Actualizar catálogo y selección de forma conjunta.
        pro.sources.update({key:path for key,path in self.sources.items()
                            if path.is_file()})
        pro.selected = self.selected.intersection(self.sources)
        pro.extra_gains.update(self.extra_gains)
        pro.checked_mutes.update(self.checked_mutes)
        pro._sync_channels()
        # Los medidores y canales añadidos permanecen en la consola Pro.
        if pro.transport is not None:
            pro.transport.selection_changed()

    def _check_source(self, item):
        super()._check_source(item)
        self.push_to_professional()

    def _level(self, key, amount, readout):
        super()._level(key, amount, readout)
        if self._bridging:
            return
        self.professional.extra_gains[key] = amount
        strip = self.professional.channels.get(key)
        if strip is not None:
            strip["fader"].setValue(amount)

    def _mute(self, key, flag):
        super()._mute(key, flag)
        if self._bridging:
            return
        self.professional.checked_mutes[key] = bool(flag)
        strip = self.professional.channels.get(key)
        if strip is not None:
            strip["mute"].setChecked(bool(flag))
