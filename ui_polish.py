"""Ajuste transversal de listas desplegables de StemMIDI Studio."""
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QComboBox,QSizePolicy,QPushButton,QLineEdit,QSlider

class ComboPolisher(QObject):
    def __init__(self,root):
        super().__init__(root)
        self.root=root
        self._wired=set()
        self.apply_all()
        # Algunas listas de modelos, audio y MIDI se rellenan dinámicamente.
        self.timer=QTimer(self)
        self.timer.setInterval(2400)
        self.timer.timeout.connect(self.apply_all)
        self.timer.start()
    @staticmethod
    def _belongs_to_browser(widget):
        # El explorador tiene distribución propia y no admite reglas de
        # compactación transversales de controles de módulos.
        parent=widget
        while parent is not None:
            if parent.objectName()=="StemFileBrowser":return True
            parent=parent.parentWidget()
        return False
    def apply_one(self,c):
        if not c or not c.isWidgetType() or self._belongs_to_browser(c):return
        try:
            metric=QFontMetrics(c.font())
            texts=[c.itemText(i) for i in range(min(c.count(),220))]
            widest=max((metric.horizontalAdvance(t) for t in texts),default=90)
            # Compactos por contenido. Dispositivos/rutas y nombres más
            # largos pueden llegar a 400 px sin ocupar toda la fila.
            size=max(82,min(410,widest+42))
            if c.maximumWidth()!=size:c.setMaximumWidth(size)
            # No imponer un ancho mínimo grande que rompa pantallas pequeñas.
            c.setMinimumWidth(0)
            if not c.toolTip() and c.currentText():
                c.setToolTip(c.currentText())
            c.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            if id(c) not in self._wired:
                self._wired.add(id(c))
                c.currentIndexChanged.connect(lambda index,combo=c:self.apply_one(combo))
                c.destroyed.connect(lambda obj=None,i=id(c):self._wired.discard(i))
        except RuntimeError:pass
    def apply_button(self,button):
        if self._belongs_to_browser(button):return
        try:
            if button.objectName() in {
                "studioCardHeading","studioToolbar","studioWindowControl",
                "studioCloseControl"}:
                return
            if button.property("allowStretch"):
                return
            text=button.text().strip()
            if not text:return
            # Las filas horizontales no deben estirar botones de 90 px
            # a ocupar 500-800 px. Reservar margen para el icono.
            metric=QFontMetrics(button.font())
            actual=metric.horizontalAdvance(text)
            width=max(35,min(390,max(actual+54,button.sizeHint().width()+12)))
            if button.icon().isNull() is False:width+=18
            if button.minimumWidth()==button.maximumWidth() and button.maximumWidth()<400:
                return
            if button.maximumWidth()!=width:button.setMaximumWidth(width)
        except RuntimeError:
            pass

    def apply_path(self,field):
        """Evita campos de rutas de un metro en todos los módulos."""
        if self._belongs_to_browser(field):return
        try:
            value=field.text().strip()
            hint=field.placeholderText().lower()
            object_name=field.objectName().lower()
            looks_like_path=(
                (value.startswith("/") and len(value)>2) or
                field.isReadOnly() or
                any(token in object_name for token in ("path","ruta","file_path","source_path")) or
                "ruta" in hint or "ubicación" in hint or
                "carpeta" in hint)
            if not looks_like_path or field.property("allowWidePath"):
                return
            maximum=500
            if field.maximumWidth()>maximum:
                field.setMaximumWidth(maximum)
            field.setMinimumWidth(0)
            if value:
                field.setToolTip(value)
                # Qt muestra el final del nombre de archivo, no
                # deja desaparecer extensión/carpeta en el recorte.
                if field.isReadOnly():field.setCursorPosition(len(value))
            if not field.property("_compact_path_wired"):
                field.setProperty("_compact_path_wired",True)
                field.textChanged.connect(
                    lambda text,f=field:self.apply_path(f))
        except RuntimeError:pass

    def apply_slider(self,slider):
        """Limitar sliders de valores, sin impedir mover el cursor de audio."""
        if self._belongs_to_browser(slider):return
        try:
            if slider.orientation()!=Qt.Horizontal or slider.property("allowWideSlider"):
                return
            from preview_player import PreviewPlayer
            parent=slider.parentWidget()
            if isinstance(parent,PreviewPlayer):
                limit=310 if slider is parent.slider else 125
            else:
                limit=230
            if slider.maximumWidth()>limit:
                slider.setMaximumWidth(limit)
            if slider.minimumWidth()>limit:
                slider.setMinimumWidth(0)
            if parent is not None and parent.metaObject().className()=="SliderNumber":
                if parent.maximumWidth()>370:
                    parent.setMaximumWidth(370)
        except RuntimeError:
            pass

    def apply_all(self):
        for slider in self.root.findChildren(QSlider):
            self.apply_slider(slider)
        for field in self.root.findChildren(QLineEdit):
            self.apply_path(field)
        for combo in self.root.findChildren(QComboBox):
            self.apply_one(combo)
        for button in self.root.findChildren(QPushButton):
            self.apply_button(button)

def install(root):
    root._combo_polisher=ComboPolisher(root)
    from preview_player import PreviewPlayer
    for preview in root.findChildren(PreviewPlayer):
        if not getattr(preview,"_extended_preview",False):
            preview.set_compact(True)
    # La reproducción debe estar disponible SIN desplegar una sección
    # oculta al acceder a estos dos módulos.
    vocal=getattr(root,"vocal_module",None)
    if vocal is not None:
        vocal.preview.setVisible(True)
        vocal.preview_toggle.setText("▴ Ocultar escucha A/B")
    piano=getattr(getattr(root,"workbench",None),"piano",None)
    if piano is not None:
        # El nuevo transporter proporciona escucha y cursor arriba.
        # El panel de escucha avanzado permanece accesible por botón para
        # controles de dispositivo, volumen y velocidad, sin quitar espacio.
        piano.preview.setVisible(False)
        piano.listen_toggle.setText("▶ Abrir panel de escucha")
    return root._combo_polisher
