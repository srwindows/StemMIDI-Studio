"""Pestañas profesionales que REUTILIZAN las mismas vistas de Inicio.

MIDI→audio y Mezclador poseen un solo editor extendido y un solo backend:
el widget se acopla a la pestaña cuando la ventana está cerrada, y vuelve
a la tarjeta al abrirse la ventana. No clonar QWidgets, presets o audio.
"""
from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (
    QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QTreeWidget,QTreeWidgetItem,QSizePolicy
)


def button(text,callback,parent):
    widget=QPushButton(text,parent)
    widget.setCursor(Qt.PointingHandCursor)
    widget.setObjectName("advancedTabAction")
    widget.clicked.connect(callback)
    return widget


class SharedProfessionalDock(QWidget):
    """Mismo QWidget operativo en la pestaña y en la tarjeta flotante."""
    def __init__(self,main,card,expanded,attribute,kind,parent=None):
        super().__init__(parent)
        self.main=main
        self.card=card
        self.expanded=expanded
        self.kind=kind
        self.view=getattr(expanded,attribute)
        self._in_float=False
        self.setObjectName("sharedProfessionalDock")
        self.setStyleSheet("""
        QWidget#sharedProfessionalDock{
            background:#031330;border:1px solid #237aba;border-radius:7px;}
        QFrame#professionalDockTop{
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #0b4bb0,stop:.5 #062b71,stop:1 #031a3c);
            border-bottom:1px solid #27ccf3;border-radius:6px;
        }
        QLabel#professionalDockHeading{
            color:#d9fbff;font-size:15px;font-weight:800;}
        QLabel#professionalDockNote{
            color:#9bdceb;font-size:11px;}
        QPushButton#advancedTabAction{
            background:#0b4c87;color:#e9fcff;border:1px solid #3eb9ec;
            border-radius:4px;padding:3px 9px;min-height:23px;}
        QPushButton#advancedTabAction:hover{background:#126fb3;}
        QTreeWidget#advancedMidiAudit{
            background:#041a3a;color:#dcefff;border:1px solid #237aba;
            alternate-background-color:#082654;}
        """)
        root=QVBoxLayout(self)
        root.setContentsMargins(5,5,5,5)
        root.setSpacing(5)
        top=QFrame(self)
        top.setObjectName("professionalDockTop")
        row=QHBoxLayout(top)
        row.setContentsMargins(10,5,10,5)
        row.setSpacing(7)
        head=QVBoxLayout()
        caption=("SÍNTESIS MIDI → AUDIO · ESTUDIO PROFESIONAL"
                 if kind=="midi" else
                 "MEZCLADOR DEL PROYECTO · ESTUDIO MULTIPISTA")
        title=QLabel(caption,top)
        title.setObjectName("professionalDockHeading")
        head.addWidget(title)
        note=QLabel(
            "Control compartido con Inicio · fuentes originales intactas · ajustes sincronizados",
            top)
        note.setObjectName("professionalDockNote")
        head.addWidget(note)
        row.addLayout(head,1)
        self.heading_row=row
        row.addWidget(button("Abrir ventana flotante",
            lambda:main.studio_home._floating_manager.detach(card),top))
        row.addWidget(button("Resultados",
            lambda:main.tabs.setCurrentWidget(main.results_tab),top))
        row.addWidget(button("Guardar proyecto",
            self.save_project,top))
        root.addWidget(top,0)

        self.placeholder=QLabel(
            "El mismo editor está abierto en su ventana flotante. "
            "Bloquea esa ventana para devolverlo aquí.",self)
        self.placeholder.setObjectName("moduleEmptyState")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.hide()
        root.addWidget(self.placeholder,1)
        self.content=QWidget(self)
        self.content.setObjectName("professionalDockContent")
        self.content_layout=QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0,0,0,0)
        self.content_layout.setSpacing(4)
        root.addWidget(self.content,1)

        self.transport=None
        if kind=="mixer":
            # La pestaña tiene VU de pista y master + transporte real,
            # igual que la tarjeta ampliada; siempre una sola mezcla activa.
            from project_mixer_expanded import ProjectMixerTransport
            self.transport=ProjectMixerTransport(self.view,self.content)
            self.transport.setMinimumHeight(192)
            self.transport.setMaximumHeight(226)
        self.content_layout.insertWidget(0,self.view,1)
        if self.transport is not None:
            self.content_layout.addWidget(self.transport,0)
        self.view.show()
        if kind=="midi":
            self._make_inspector()
        expanded.professional_bridge=self

    def save_project(self):
        from studio_shell import save_project
        if getattr(self.main,"project_dir",None):
            save_project(self.main,show_confirmation=False)

    def _make_inspector(self):
        tools=QHBoxLayout()
        self.analysis_toggle=button("Analizar estructura MIDI",self._toggle_analysis,self)
        self.analysis_toggle.setToolTip(
            "Inspección de pistas, canales, instrumentos, rango de notas y "
            "controladores sin modificar las notas ni el archivo de entrada.")
        tools.addWidget(self.analysis_toggle)
        tools.addStretch()
        self.content_layout.addLayout(tools)
        self.analysis=QTreeWidget(self)
        self.analysis.setObjectName("advancedMidiAudit")
        self.analysis.setColumnCount(7)
        self.analysis.setHeaderLabels(
            ("Pista","Nombre","Canales","Programa GM",
             "Notas","Rango MIDI","CC64"))
        self.analysis.setRootIsDecorated(False)
        self.analysis.setAlternatingRowColors(True)
        self.analysis.setMinimumHeight(125)
        self.analysis.setMaximumHeight(155)
        self.analysis.hide()
        self.content_layout.addWidget(self.analysis)
        self.view.files.itemSelectionChanged.connect(
            lambda:QTimer.singleShot(0,self.refresh_analysis)
            if self.analysis.isVisible() and not self._in_float else None)

    def _toggle_analysis(self):
        visible=not self.analysis.isVisible()
        self.analysis.setVisible(visible)
        self.analysis_toggle.setText(
            "Ocultar análisis MIDI" if visible else "Analizar estructura MIDI")
        if visible:self.refresh_analysis()

    def refresh_analysis(self):
        if self.kind!="midi" or self._in_float:return
        item=self.view.files.currentItem()
        if item is None:
            self.analysis.clear()
            return
        source=item.data(Qt.UserRole)
        if not source:return
        file=Path(str(source))
        self.analysis.clear()
        if not file.is_file() or file.stat().st_size>16*1024*1024:
            self.analysis.addTopLevelItem(QTreeWidgetItem(
                ["No se puede analizar: archivo ausente o demasiado grande"]))
            return
        try:
            import mido
            midi=mido.MidiFile(str(file))
            for index,track in enumerate(midi.tracks):
                channels=set();programs=set();pitches=[]
                sustain=0;name=track.name or f"Pista {index+1}"
                for message in track:
                    channel=getattr(message,"channel",None)
                    if channel is not None:channels.add(channel+1)
                    if message.type=="program_change":
                        programs.add(f"{message.program+1:03d}")
                    if message.type=="note_on" and message.velocity>0:
                        pitches.append(message.note)
                    if message.type=="control_change" and message.control==64:
                        sustain+=1
                self.analysis.addTopLevelItem(QTreeWidgetItem([
                    str(index+1),name,
                    ", ".join(map(str,sorted(channels))) or "—",
                    ", ".join(sorted(programs)) or "—",
                    str(len(pitches)),
                    (f"{min(pitches)}–{max(pitches)}" if pitches else "—"),
                    str(sustain)
                ]))
            self.analysis.resizeColumnToContents(0)
            self.analysis.resizeColumnToContents(2)
            self.analysis.resizeColumnToContents(4)
            self.analysis.resizeColumnToContents(6)
        except (OSError,EOFError,ValueError,TypeError,ImportError) as error:
            self.analysis.addTopLevelItem(QTreeWidgetItem(
                [f"No se pudo leer el MIDI: {error}"]))

    def to_floating(self):
        if self._in_float:return
        self._in_float=True
        if self.kind=="mixer" and self.transport is not None:
            self.transport.live.stop()
            self.transport.timer.stop()
            self.transport.hide()
        self.content_layout.removeWidget(self.view)
        self.view.setParent(self.expanded.extra)
        self.expanded.layout.addWidget(self.view,1)
        self.view.show()
        self.content.hide()
        self.placeholder.show()

    def to_tab(self):
        if not self._in_float:return
        self.expanded.layout.removeWidget(self.view)
        self.view.setParent(self.content)
        self.content_layout.insertWidget(0,self.view,1)
        self._in_float=False
        self.placeholder.hide()
        self.content.show()
        self.view.show()
        if self.kind=="mixer" and self.transport is not None:
            # El transporte flotante acaba de limpiar su sesión PCM.
            self.view.reopen()
            self.view.attach_transport(self.transport)
            self.transport._sync_meters()
            self.transport.timer.start()
            self.transport.show()
        if self.kind=="midi":
            self.view.refresh_files(force=True)

    def synchronize(self):
        if self._in_float:return
        if self.kind=="mixer":
            self.view.refresh_catalog()
        else:
            self.view.refresh_files(force=True)


def install(main):
    """Reutiliza las instancias ya construidas por las ventanas de Inicio."""
    mgr=main.studio_home._floating_manager
    midi=mgr.other_expanders[main.studio_home.info_card]
    mixer=mgr.other_expanders[main.studio_home.mix_card]

    midi_page=SharedProfessionalDock(
        main,main.studio_home.info_card,midi,
        "info_expanded","midi",main.tabs)
    main.midi_audio_professional=midi_page
    main.midi_audio_tab=midi_page
    index=main.tabs.indexOf(main.workbench.midi_tab)+1
    main.tabs.insertTab(index,midi_page,"MIDI a audio")
    from PySide6.QtGui import QIcon
    main.tabs.setTabIcon(
        index,QIcon(str(Path(__file__).resolve().parent/"assets"/"ui_note.svg")))
    main.tabs.setTabToolTip(
        index,"Estudio profesional de conversión MIDI a audio: "
        "instrumentos SoundFont, efectos, CC, ADSR, EQ, cuantización, "
        "análisis, preescucha A/B y exportación.")
    # Mantener la pestaña Mezclador antigua en lugar de destruirla:
    # conserva preescucha y sus funciones auxiliares mientras añade
    # la mesa profesional completa (mismas pistas/faders de Inicio).
    mixer_page=main.mixer_placeholder
    mixer_dock=SharedProfessionalDock(
        main,main.studio_home.mix_card,mixer,
        "project_mixer","mixer",mixer_page)
    main.mixer_professional=mixer_dock
    mixer_root=mixer_page.layout()
    mixer_root.insertWidget(2,mixer_dock,3)
    # La antigua pestaña solo tenía un botón de abrir el mezclador y una
    # preescucha aislada. Conservar ambos, pero sin ocupar media pantalla:
    # disponibles tras «Herramientas auxiliares».
    from PySide6.QtWidgets import QVBoxLayout
    for i in (0,1):
        item=mixer_root.itemAt(i)
        if item is not None and item.widget() is not None:
            item.widget().hide()
    legacy_item=mixer_root.takeAt(3)
    legacy_layout=legacy_item.layout()
    assert legacy_layout is not None, "Faltan las herramientas antiguas"
    auxiliary=QFrame(mixer_page)
    auxiliary.setObjectName("professionalAuxiliaryMixer")
    aux_layout=QVBoxLayout(auxiliary)
    aux_layout.setContentsMargins(2,2,2,2)
    aux_layout.addLayout(legacy_layout)
    mixer_root.addWidget(auxiliary,0)
    auxiliary.hide()
    def toggle_auxiliary():
        auxiliary.setVisible(not auxiliary.isVisible())
        toggle.setText(
            "Ocultar herramientas auxiliares" if auxiliary.isVisible()
            else "Herramientas auxiliares")
    toggle=button("Herramientas auxiliares",toggle_auxiliary,mixer_dock)
    mixer_dock.heading_row.insertWidget(1,toggle)
    main.mixer_professional_aux=auxiliary

    def select(index):
        widget=main.tabs.widget(index)
        if widget is midi_page:
            midi_page.synchronize()
        elif widget is mixer_page:
            mixer_dock.synchronize()
    main.tabs.currentChanged.connect(select)
    return midi_page,mixer_dock
