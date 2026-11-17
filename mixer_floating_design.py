"""Mezclador flotante 3D operativo: archivos por arrastre y VU por canal.

Vista original conservada en mixer_floating_restored.py. No se emplean
imágenes simuladas: los niveles L/R proceden del motor de mezcla activo.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPoint, QTimer, QSignalBlocker, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QFont, QPixmap, QIcon
from PySide6.QtWidgets import (
    QFrame, QWidget, QLabel, QSlider, QPushButton, QHBoxLayout, QVBoxLayout,
    QScrollArea, QSizePolicy, QListWidgetItem, QGraphicsDropShadowEffect,
    QAbstractItemView, QBoxLayout
)

from mixer_floating_bridge import RestoredFloatingMixer
from mixer_floating_restored import (
    ProjectMixerView, ProjectMixerTransport, FAMILIES, AUDIO, MIDI,
)
from studio_vu_unified import Ballistics, db_fraction
from results_dragdrop import valid_mime_paths, FilesDragList
from PySide6.QtSvg import QSvgRenderer

PANEL_CSS="""
QWidget#projectMixerView{background:transparent;border:0;}
QFrame#floatingFilePanel{
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #1a5198,stop:.12 #113969,stop:.48 #06264c,stop:1 #07162f);
 border:2px solid #39bbec;border-top:2px solid #97ffff;
 border-bottom:2px solid #03609c;border-radius:10px;}
QFrame#floatingChannelCell{
 background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
 stop:0 #03132b,stop:.08 #14509c,stop:.16 #0c356b,
 stop:.65 #061d3a,stop:.90 #154b79,stop:1 #031229);
 border:1px solid #59b9f0;border-top:2px solid #b1ffff;
 border-bottom:2px solid #031328;border-radius:10px;
}
QFrame#floatingChannelCell[dragging="true"]{
 border:2px solid #70ffd2;background:#144c59;}
QScrollArea#floatingChannelScroll{background:transparent;border:0;}
QListWidget#projectMixFiles{
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #173f69,stop:1 #0b2547);color:#f1ffff;
 border:1px solid #57bfe1;border-radius:6px;
 font-size:12px;alternate-background-color:#0e3659;}
QListWidget#projectMixFiles::item{
 padding:2px 7px;min-height:20px;border-bottom:1px solid #2e5372;}
QListWidget#projectMixFiles::item:selected{background:#1679ac;}
QListWidget#projectMixGeneratedFiles{
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #173f69,stop:1 #081f3d);
 color:#e0fcff;border:1px solid #57bfe1;border-radius:6px;
 font-size:11px;alternate-background-color:#103756;
 selection-background-color:#126f9b;selection-color:white;
}
QListWidget#projectMixGeneratedFiles::item{
 padding:2px 7px;min-height:20px;border-bottom:1px solid #254e70;
}
QListWidget#projectMixGeneratedFiles::item:selected{
 background:#127ea8;color:white;
}

QPushButton#floatingMute{
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #7594b1,stop:.12 #2a607c,stop:.39 #103a5b,
 stop:.60 #0b2d50,stop:1 #061c31);
 border:1px solid #61b6d5;border-top:1px solid #cffbff;
 border-bottom:2px solid #051222;border-radius:6px;color:#f2ffff;
 font-weight:900;font-size:13px;min-height:24px;
}
QPushButton#floatingMute:checked{
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #f97d7a,stop:.45 #a82038,stop:1 #510e25);
 color:white;border:1px solid #ffb1ad;}
"""

# Son widgets reales Qt con dibujo metálico y dos canales de señal.
from mixer_neon_widgets import NeonFader as ChromeFader
from mixer_neon_widgets import NeonStereoVU as StereoVerticalVU
from mixer_neon_widgets import NeonSeekSlider

class ChannelDrop(QFrame):
    """Un canal = su archivo, fader, mute y medidor físico debajo."""
    def __init__(self,view,key,source,name,parent=None):
        super().__init__(parent)
        self.view=view
        self.channel_key=key
        self.source=source
        self.setObjectName("floatingChannelCell")
        self.setAcceptDrops(True)
        self.setFixedWidth(91)
        self.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        self.setProperty("dragging",False)
        self.setToolTip("Arrastra aquí un archivo del proyecto para asignarlo a "+name)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(3,5,3,4)
        layout.setSpacing(2)
        # Iconos vectoriales del programa. Sin caracteres musicales genéricos.
        symbol_files={"Voces":"ui_mic.svg","Batería":"ui_drum.svg",
                      "Piano":"ui_piano.svg","Otros":"ui_layers.svg"}
        symbol_svg={
          "Bajo":'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><g fill="none" stroke="#52dfff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M24 3l5 5-9 9-5-5zM16 14l-5 5M11 19c-4-3-11 0-8 6l4 4c6 3 9-4 6-8M7 23l2 2M26 5l2 2"/></g></svg>',
          "Guitarra":'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><g fill="none" stroke="#52dfff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M24 3l5 5-9 9-5-5zM16 14l-5 5M11 19c-4-3-11 0-8 6l4 4c6 3 9-4 6-8M7 23l2 2M26 5l2 2"/></g></svg>',
          "Viento":'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M3 22c9 0 4-13 13-13s3 13 13 13M8 27c9-1 5-13 15-14" fill="none" stroke="#52dfff" stroke-width="3.4" stroke-linecap="round"/></svg>',
        }
        icon=QLabel(self)
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedHeight(26)
        icon.setStyleSheet("background:transparent;border:0;")
        halo=QGraphicsDropShadowEffect(icon)
        halo.setBlurRadius(9)
        halo.setOffset(0,0)
        halo.setColor(QColor(37,249,255,175))
        icon.setGraphicsEffect(halo)
        resource=Path(__file__).resolve().parent/'assets'/symbol_files.get(name,'')
        if name in symbol_files and resource.is_file():
            renderer=QSvgRenderer(str(resource))
        else:
            renderer=QSvgRenderer(symbol_svg.get(name,symbol_svg['Viento']).encode())
        pixmap=QPixmap(25,25)
        pixmap.fill(Qt.transparent)
        painter=QPainter(pixmap);renderer.render(painter);painter.end()
        icon.setPixmap(pixmap)
        layout.addWidget(icon)
        caption=QLabel(name,self)
        caption.setAlignment(Qt.AlignCenter)
        caption.setFixedHeight(19)
        caption.setStyleSheet("color:#ffffff;font-weight:800;font-size:12px;background:transparent;")
        layout.addWidget(caption)
        description=self.view.sources.get(source)
        self.file_tag=QLabel(description.name if description else "Arrastra aquí",self)
        self.file_tag.setAlignment(Qt.AlignCenter)
        self.file_tag.setFixedHeight(20)
        self.file_tag.setToolTip(str(description) if description else "Arrastra un archivo al canal")
        self.file_tag.setStyleSheet(
            "color:#d9faff;font-size:9px;font-weight:800;"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #1c5277,stop:1 #092948);"
            "border:1px solid #3d98bf;border-radius:5px;padding:2px;")
        layout.addWidget(self.file_tag)
        self.fader=ChromeFader(self)
        value=(self.view.home.mixer_rows[key]["fader"].value()
               if key in self.view.home.mixer_rows
               else self.view.extra_gains.get(key,100))
        self.fader.setValue(value)
        self.fader.setFixedWidth(62)
        self.fader.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        layout.addWidget(self.fader,1,Qt.AlignHCenter)
        self.readout=QLabel(f"{value}%",self)
        self.readout.setAlignment(Qt.AlignCenter)
        self.readout.setFixedHeight(21)
        self.readout.setStyleSheet(
            "color:#f7ffff;font-weight:900;font-size:12px;"
            "background:#061830;border:1px solid #438fae;border-radius:5px;")
        layout.addWidget(self.readout)
        self.mute=QPushButton("M",self)
        # Altavoz real, en vez de un carácter incompatible con macOS.
        speaker_svg=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="#dcfaff" stroke="#f4ffff" stroke-width=".8"><path d="M3 9h5l6-5v16l-6-5H3z"/></g><g fill="none" stroke="#eaffff" stroke-width="1.7" stroke-linecap="round"><path d="M17 8c2 2 2 6 0 8M19 5c4 4 4 10 0 14"/></g></svg>'
        speaker=QPixmap(22,22);speaker.fill(Qt.transparent)
        rendered=QSvgRenderer(speaker_svg)
        pp=QPainter(speaker);rendered.render(pp);pp.end()
        self.mute.setIcon(QIcon(speaker))
        self.mute.setIconSize(QSize(15,15))
        self.mute.setObjectName("floatingMute")
        self.mute.setCheckable(True)
        self.mute.setFixedHeight(24)
        if key in self.view.home.track_rows:
            self.mute.setChecked(self.view.home.track_rows[key]["mute"].isChecked())
        else:
            self.mute.setChecked(self.view.checked_mutes.get(key,False))
        self.mute.setEnabled(source is not None)
        self.mute.setToolTip("Silenciar solo este canal")
        layout.addWidget(self.mute)
        self.meter=StereoVerticalVU(self)
        self.meter.setFixedWidth(59)
        self.meter.setMinimumHeight(120)
        self.meter.setMaximumHeight(182)
        self.meter.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        layout.addWidget(self.meter,1,Qt.AlignHCenter)
        self.fader.valueChanged.connect(
            lambda amount:self.view._level(self.channel_key,amount,self.readout))
        self.mute.toggled.connect(lambda muted:self.view._mute(self.channel_key,muted))

    def _dragged_files(self,event):
        return [path for path in valid_mime_paths(event.mimeData())
                if path.suffix.lower() in AUDIO|MIDI]

    def _hover(self,on):
        self.setProperty("dragging",on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self,event):
        if self._dragged_files(event):
            self._hover(True);event.setDropAction(Qt.CopyAction);event.accept()
        else:event.ignore()

    def dragMoveEvent(self,event):
        if self._dragged_files(event):
            event.setDropAction(Qt.CopyAction);event.accept()
        else:event.ignore()

    def dragLeaveEvent(self,event):
        self._hover(False);event.accept()

    def dropEvent(self,event):
        self._hover(False)
        files=self._dragged_files(event)
        if files and self.view.assign_file(self.channel_key,files[0]):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:event.ignore()

class StyledFloatingMixer(RestoredFloatingMixer):
    """Diseño de siete tiras con asignación manual y stems auto."""
    premium_floating_mixer=True

    def __init__(self,home,professional,parent=None):
        self.manual_sources={}
        self.manual_assignments={}
        self._auto_project=None
        self._designer_ready=False
        super().__init__(home,professional,parent)
        old=self.layout()
        saved_file=self.file_list
        saved_summary=self.summary
        saved_scroll=self.channel_scroll
        while old.count():
            item=old.takeAt(0)
            widget=item.widget()
            if widget is not None and widget not in (saved_file,saved_summary):
                widget.hide();widget.setParent(None);widget.deleteLater()
        saved_scroll.hide()
        self.channels={}
        self._designer_ready=True
        self.setStyleSheet(PANEL_CSS)
        old.setContentsMargins(4,4,4,4)
        old.setSpacing(5)
        self.file_panel=QFrame(self)
        self.file_panel.setObjectName("floatingFilePanel")
        fl=QVBoxLayout(self.file_panel)
        fl.setContentsMargins(9,6,9,7);fl.setSpacing(4)
        headline=QHBoxLayout()
        doc_icon=QLabel("▤",self.file_panel)
        doc_icon.setStyleSheet("color:#49ffff;font-size:28px;font-weight:900;background:transparent;")
        doc_icon.setFixedWidth(32)
        headline.addWidget(doc_icon)
        title=QLabel("Asignación de archivos del proyecto",self.file_panel)
        self.files_heading=title
        title.setStyleSheet("color:#f6ffff;font-size:15px;font-weight:900;background:transparent;")
        headline.addWidget(title)
        headline.addStretch()
        arrow=QLabel("⇩",self.file_panel)
        self.files_arrow=arrow
        arrow.setStyleSheet("color:#44faff;font-size:31px;font-weight:900;background:transparent;")
        arrow.setFixedWidth(36)
        headline.addWidget(arrow)
        hint=QLabel("Arrastra archivos de audio o stems\nsobre un canal para asignarlos",self.file_panel)
        self.files_hint=hint
        hint.setStyleSheet("color:#d6faff;font-size:10px;font-weight:800;background:transparent;")
        hint.setMaximumWidth(215)
        headline.addWidget(hint)
        fl.addLayout(headline)

        # DOS cuadros reales y simultáneos: la selección para mezclar y
        # los resultados recién generados por los motores del proyecto.
        lists=QHBoxLayout()
        lists.setContentsMargins(0,0,0,0)
        lists.setSpacing(7)
        self.files_lists_layout=lists
        assignment=QVBoxLayout()
        assignment.setContentsMargins(0,0,0,0)
        assignment.setSpacing(2)
        selected_title=QLabel("ARCHIVOS DEL PROYECTO · SELECCIÓN",self.file_panel)
        self.files_selected_title=selected_title
        selected_title.setStyleSheet(
            "background:transparent;color:#bceef9;font-size:10px;font-weight:800;")
        assignment.addWidget(selected_title)
        saved_file.setParent(self.file_panel)
        saved_file.setMinimumHeight(76)
        saved_file.setMaximumHeight(84)
        saved_file.setDragEnabled(True)
        assignment.addWidget(saved_file,1)
        lists.addLayout(assignment,1)

        available=QVBoxLayout()
        available.setContentsMargins(0,0,0,0)
        available.setSpacing(2)
        available_title=QLabel("ARCHIVOS GENERADOS · STEMS DISPONIBLES",self.file_panel)
        self.files_generated_title=available_title
        available_title.setStyleSheet(
            "background:transparent;color:#bcf8ff;font-size:10px;font-weight:800;")
        available.addWidget(available_title)
        self.generated_files=FilesDragList(self.file_panel)
        self.generated_files.setObjectName("projectMixGeneratedFiles")
        self.generated_files.setAlternatingRowColors(True)
        self.generated_files.setMinimumHeight(76)
        self.generated_files.setMaximumHeight(84)
        self.generated_files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.generated_files.setToolTip(
            "Archivos reales generados por este proyecto. Arrastra uno "
            "al canal elegido; el original no se mueve ni se borra.")
        available.addWidget(self.generated_files,1)
        lists.addLayout(available,1)
        fl.addLayout(lists,1)
        old.addWidget(self.file_panel,0)
        saved_summary.setParent(self)
        saved_summary.setStyleSheet("color:#8cbed2;font-size:9px;")
        saved_summary.setFixedHeight(16)
        old.addWidget(saved_summary,0)
        self.channel_scroll=QScrollArea(self)
        self.channel_scroll.setObjectName("floatingChannelScroll")
        self.channel_scroll.setFrameShape(QFrame.NoFrame)
        self.channel_scroll.setWidgetResizable(True)
        self.channel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.channel_scroll.setMinimumHeight(405)
        self.channel_scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.channel_root=QWidget(self.channel_scroll)
        self.channel_row=QHBoxLayout(self.channel_root)
        self.channel_row.setContentsMargins(1,1,1,1)
        self.channel_row.setSpacing(4)
        self.channel_scroll.setWidget(self.channel_root)
        old.addWidget(self.channel_scroll,1)
        self._sync_channels()
        self.refresh_catalog(force=True)
        # Mostrar archivos recién terminados sin cerrar la ventana.
        # El propio catálogo evita actualizaciones cuando nada ha cambiado.
        self._generated_timer=QTimer(self)
        self._generated_timer.setInterval(5000)
        self._generated_timer.timeout.connect(self._poll_generated_files)
        self._generated_timer.start()

    def _poll_generated_files(self):
        if self.isVisible():
            self.refresh_catalog()

    def set_tab_mode(self,enabled):
        """El MISMO QWidget: pestaña horizontal y flotante vertical.

        En pestaña los siete canales y los ficheros quedan lado a lado:
        así se evita recortar los vúmetros en pantallas de poca altura.
        """
        enabled=bool(enabled)
        if getattr(self,"_tab_mode",False)==enabled:return
        root=self.layout()
        if enabled:
            for widget in (self.file_panel,self.summary,self.channel_scroll):
                root.removeWidget(widget)
            container=QWidget(self)
            container.setObjectName("neonMixerTabContainer")
            h=QHBoxLayout(container)
            h.setContentsMargins(0,0,0,0)
            h.setSpacing(5)
            h.addWidget(self.channel_scroll,6)
            side=QWidget(container)
            aside=QVBoxLayout(side)
            aside.setContentsMargins(0,0,0,0)
            aside.setSpacing(3)
            aside.addWidget(self.file_panel,1)
            aside.addWidget(self.summary,0)
            h.addWidget(side,5)
            self._tab_host=container
            root.addWidget(container,1)
            self.channel_scroll.setMinimumHeight(280)
            self.channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.file_panel.setMinimumWidth(330)
            self.file_panel.setMaximumWidth(620)
            self.files_lists_layout.setDirection(QBoxLayout.TopToBottom)
            self.files_heading.setText("Archivos para mezclar")
            self.files_hint.setText("Arrastra al canal")
            self.files_arrow.setFixedWidth(26)
            self.files_selected_title.setText("ARCHIVOS DEL PROYECTO")
            self.files_generated_title.setText("ARCHIVOS GENERADOS / STEMS")
            self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.generated_files.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.file_list.setTextElideMode(Qt.ElideMiddle)
            self.generated_files.setTextElideMode(Qt.ElideMiddle)
            self.file_list.setMaximumHeight(900)
            self.generated_files.setMaximumHeight(900)
            self.file_list.setMinimumHeight(100)
            self.generated_files.setMinimumHeight(100)
            self.file_list.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
            self.generated_files.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
            self._tab_mode=True
        else:
            host=getattr(self,"_tab_host",None)
            assert host is not None
            for widget in (self.channel_scroll,self.file_panel,self.summary):
                widget.setParent(None)
            root.removeWidget(host)
            host.hide()
            host.setParent(None)
            host.deleteLater()
            self._tab_host=None
            for widget in (self.file_panel,self.summary,self.channel_scroll):
                widget.setParent(self)
            root.addWidget(self.file_panel,0)
            root.addWidget(self.summary,0)
            root.addWidget(self.channel_scroll,1)
            self.file_panel.setMinimumWidth(0)
            self.file_panel.setMaximumWidth(16777215)
            self.files_lists_layout.setDirection(QBoxLayout.LeftToRight)
            self.files_heading.setText("Asignación de archivos del proyecto")
            self.files_hint.setText("Arrastra archivos de audio o stems\nsobre un canal para asignarlos")
            self.files_arrow.setFixedWidth(36)
            self.files_selected_title.setText("ARCHIVOS DEL PROYECTO · SELECCIÓN")
            self.files_generated_title.setText("ARCHIVOS GENERADOS · STEMS DISPONIBLES")
            self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.generated_files.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.channel_scroll.setMinimumHeight(405)
            self.channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.file_list.setMinimumHeight(76)
            self.generated_files.setMinimumHeight(76)
            self.file_list.setMaximumHeight(84)
            self.generated_files.setMaximumHeight(84)
            self._tab_mode=False
        for data in self.channels.values():
            strip=data["strip"]
            strip.fader.setMinimumHeight(85 if enabled else 115)
            strip.meter.setMinimumHeight(82 if enabled else 120)
            strip.meter.setMaximumHeight(155 if enabled else 182)
            strip.layout().setContentsMargins(3,3 if enabled else 5,3,3 if enabled else 4)
            strip.layout().setSpacing(1 if enabled else 2)
        self.updateGeometry()

    def _catalog(self):
        result=super()._catalog()
        # La pestaña Resultados ya identifica los archivos reales del
        # proyecto abierto. Incluirlos sin copiar archivos de otros proyectos.
        project=getattr(self.home.main,"project_dir",None)
        if project:
            root=Path(project).resolve()
            results=getattr(self.home.main,"results_tab",None)
            for candidate in (getattr(results,"_paths",()) if results else ()):
                try:
                    path=Path(candidate).resolve(strict=True)
                    if (path.is_file() and not path.is_symlink()
                            and path.suffix.lower() in AUDIO|MIDI):
                        # results_tab pertenece al proyecto activo y ya
                        # identifica sus archivos aunque el resultado
                        # temporal esté en otro volumen de trabajo.
                        result[str(path)]=path
                except (TypeError,ValueError,OSError,RuntimeError):
                    continue
        for key,path in self.manual_sources.items():
            if path.is_file() and path.suffix.lower() in AUDIO|MIDI and not path.is_symlink():
                result[key]=path
        return result

    def refresh_catalog(self,force=False):
        before=self._signature
        super().refresh_catalog(force=force)
        if (getattr(self,"generated_files",None) is not None
                and (before!=self._signature or force)):
            self._update_generated_files()

    def _update_generated_files(self):
        # Mostrar ficheros disponibles, aunque aún no estén marcados:
        # seleccionarlos NO altera el motor; arrastrarlos sí los asigna.
        from PySide6.QtCore import QSignalBlocker
        widget=self.generated_files
        selected={item.data(Qt.UserRole) for item in widget.selectedItems()}
        generated={}
        work=self.home.workbench
        for storage in (work.separation_storage,work.drum_storage,work.vocal_storage):
            for file in storage.items:
                try:
                    p=Path(file).resolve()
                    if str(p) in self.sources:generated[str(p)]=p
                except (OSError,ValueError,TypeError):
                    pass
        try:
            for file in self.home.workbench.converter.project_stem_paths():
                p=Path(file).resolve()
                if str(p) in self.sources:generated[str(p)]=p
        except (AttributeError,OSError,ValueError,RuntimeError):
            pass
        results=getattr(self.home.main,"results_tab",None)
        if results is not None:
            for file in getattr(results,"_paths",()):
                try:
                    p=Path(file).resolve()
                    if str(p) in self.sources:generated[str(p)]=p
                except (OSError,ValueError,TypeError):
                    pass
        # Si los datos de trabajo aún no están sincronizados, ofrecer lo
        # que el catálogo del proyecto ya ha reconocido como audio real.
        if not generated:
            generated={k:p for k,p in self.sources.items()
                       if p.suffix.lower() in AUDIO}
        widget.clear()
        for key,path in sorted(generated.items(),key=lambda e:e[1].name.casefold()):
            family=self._mixer_family(path) or "Audio"
            item=QListWidgetItem(f"{family} · {path.name}")
            item.setData(Qt.UserRole,key)
            item.setToolTip(str(path))
            widget.addItem(item)
            if key in selected:item.setSelected(True)
        if not generated:
            placeholder=QListWidgetItem("Aún no hay stems generados en este proyecto")
            placeholder.setFlags(Qt.NoItemFlags)
            widget.addItem(placeholder)

    def _mixer_family(self,path):
        family=self.home._stem_for(path)
        if family in FAMILIES:return family
        if isinstance(family,str) and (family.startswith("Voz") or family=="Coros"):
            return "Voces"
        return None

    def _recognized_stem(self,path):
        from stem_detection import is_separated_stem
        from vocal_catalog import vocal_role
        if path.suffix.lower() not in AUDIO:return False
        parents=(part.casefold() for part in path.parent.parts)
        folder=any(part.startswith(("stems","separad","pistas_"))
                   for part in parents)
        return folder or is_separated_stem(path) or vocal_role(path) is not None

    def _channel_plan(self):
        plan=ProjectMixerView._channel_plan(self)
        base={key:(key,source,name) for key,source,name in plan[:7]}
        # Las separaciones almacenadas en carpetas stems también pueden
        # contener viento/otros; versiones anteriores no reconocían estos
        # nombres como stem directo aunque el motor los clasificara bien.
        auto_used={source for _,source,_ in plan[:7] if source}
        for family in FAMILIES:
            if base[family][1] is not None:continue
            for key,path in sorted(self.selected_files(),key=lambda item:item[1].name.casefold()):
                if (self._recognized_stem(path)
                    and self._mixer_family(path)==family
                    and key not in auto_used):
                    base[family]=(family,key,family)
                    auto_used.add(key)
                    break
        used=set()
        resolved=[]
        # Un archivo arrastrado a otra familia pierde su destino automático
        # anterior: una misma pista no puede quedar asignada dos veces.
        manual_targets={key:family for family,key in self.manual_assignments.items()
                        if key in self.selected and key in self.sources}
        for family in FAMILIES:
            override=self.manual_assignments.get(family)
            source=override if override in self.selected and override in self.sources else base[family][1]
            if source in manual_targets and manual_targets[source]!=family:
                source=None
            if source in used:source=None
            if source:used.add(source)
            resolved.append((family,source,family))
        extras=[]
        for key,path in sorted(self.selected_files(),key=lambda entry:entry[1].name.casefold()):
            if key in used:continue
            used.add(key)
            extras.append((key,key,path.stem[:18]))
        # La mesa de referencia es de SIETE canales fijos. Los archivos
        # no asignados siguen en la lista superior para arrastrarlos a uno
        # de esos siete, sin crear octavas columnas ni barras horizontales.
        return resolved

    def _sync_channels(self):
        if not getattr(self,"_designer_ready",False):
            return ProjectMixerView._sync_channels(self)
        while self.channel_row.count():
            item=self.channel_row.takeAt(0)
            if item.widget():
                # Ocultar de inmediato para que ningún icono anterior asome
                # mientras Qt procesa la destrucción diferida.
                item.widget().hide()
                item.widget().setParent(None)
                item.widget().deleteLater()
        self.channels={}
        plan=self._channel_plan()
        self.channel_row.addStretch(1)
        for key,source,name in plan:
            strip=ChannelDrop(self,key,source,name,self.channel_root)
            self.channel_row.addWidget(strip,0)
            self.channels[key]={"source":source,"fader":strip.fader,
                                "mute":strip.mute,"meter":strip.meter,
                                "strip":strip}
        self.channel_row.addStretch(1)
        self.channel_root.setMinimumWidth(len(plan)*91+max(0,len(plan)-1)*4+4)
        self.summary.setText(
            f"{len(self.sources)} archivos del proyecto · "
            f"{len(self.selected)} activos · {len(plan)} canales")
        if self.transport:self.transport.selection_changed()

    def paths_for_mix(self):
        # El proyecto puede tener muchos resultados seleccionados, pero
        # solo deben sonar los efectivamente asignados a los 7 canales.
        seen=set()
        paths=[]
        for channel,entry in self.channels.items():
            key=entry["source"]
            if key and key not in seen:
                seen.add(key)
                path=self.audio_path(key)
                if path is not None:paths.append((key,path))
        return paths

    def ready(self):
        assigned=[entry["source"] for entry in self.channels.values()
                  if entry["source"]]
        return bool(assigned) and all(self.audio_path(key) is not None
                                     for key in assigned)

    def assign_file(self,channel,file):
        try:
            source=Path(file).expanduser().resolve(strict=True)
        except (OSError,ValueError,RuntimeError):
            return False
        if not source.is_file() or source.is_symlink() or source.suffix.lower() not in AUDIO|MIDI:
            return False
        key=str(source)
        self.manual_sources[key]=source
        self.sources[key]=source
        self.selected.add(key)
        if channel in FAMILIES:
            for prior,assigned in list(self.manual_assignments.items()):
                if assigned==key and prior!=channel:
                    self.manual_assignments.pop(prior,None)
            self.manual_assignments[channel]=key
        else:
            # En canales adicionales, asignar al hueco que deja su antigua
            # pista sin cambiar el motor de audio ni el fichero original.
            original=self.channels.get(channel,{}).get("source")
            if original and original!=key:
                self.selected.discard(original)
            self.manual_assignments.pop(channel,None)
        # No copiar, mover, ni borrar el archivo de audio.
        self._signature=None
        self.refresh_catalog(force=True)
        if not any(self.file_list.item(i).data(Qt.UserRole)==key for i in range(self.file_list.count())):
            return False
        with QSignalBlocker(self.file_list):
            for i in range(self.file_list.count()):
                item=self.file_list.item(i)
                if item.data(Qt.UserRole)==key:item.setCheckState(Qt.Checked)
        self.push_to_professional()
        return True

    def update_channel_vus(self,peaks):
        for data in self.channels.values():
            source=data["source"]
            pair=peaks.get(source,(0.,0.)) if source else (0.,0.)
            data["meter"].set_peaks(*pair)

    def restore_from_professional(self):
        project=getattr(self.home.main,"project_dir",None)
        current=str(Path(project).resolve()) if project else None
        changed=current!=self._auto_project
        if changed:
            # No reutilizar asignaciones de proyectos anteriores.
            self.manual_sources.clear()
            self.manual_assignments.clear()
        super().restore_from_professional()
        if changed:
            self._auto_project=current
            # Una sola autoasignación por familia y por proyecto: respeta
            # cualquier desmarcado posterior y evita seleccionar todos los
            # originales/versiones de un mismo stem.
            if not self.selected and current:
                best={}
                for key,path in self.sources.items():
                    if not self._recognized_stem(path):continue
                    family=self._mixer_family(path)
                    if family not in FAMILIES:continue
                    try:modified=path.stat().st_mtime_ns
                    except OSError:continue
                    if family not in best or modified>best[family][0]:
                        best[family]=(modified,key)
                for family,(_,key) in best.items():
                    self.selected.add(key)
                    self.manual_assignments[family]=key
                if best:
                    with QSignalBlocker(self.file_list):
                        for i in range(self.file_list.count()):
                            item=self.file_list.item(i)
                            item.setCheckState(
                                Qt.Checked if item.data(Qt.UserRole) in self.selected
                                else Qt.Unchecked)
                    self._sync_channels()
                    self.push_to_professional()
        # Una asignación manual continúa mientras dure el proyecto.
        self._sync_channels()

class TopFloatingTransport(QFrame):
    """Transporte único REAL arriba de la lista, vinculado a LowLatencyStemMixer."""
    selection_changed=ProjectMixerTransport.selection_changed
    play_selected=ProjectMixerTransport.play_selected
    pause_selected=ProjectMixerTransport.pause_selected
    stop_selected=ProjectMixerTransport.stop_selected
    seek=ProjectMixerTransport.seek
    _error=ProjectMixerTransport._error

    def __init__(self,view,parent=None):
        super().__init__(parent)
        from low_latency_stem_mixer import LowLatencyStemMixer
        self.view=view
        self.live=LowLatencyStemMixer(self)
        self.live.error.connect(self._error)
        self._notice=""
        self._meter_names=()
        self.track_meters={}
        self.master_meters={}
        self.setObjectName("floatingTopTransport")
        self.setStyleSheet("""
        QFrame#floatingTopTransport {
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #102f56,stop:.17 #0c2d57,stop:.62 #061e3e,stop:1 #04152a);
            border:2px solid #42d9fd;border-top:2px solid #c0ffff;
            border-radius:10px;}
        QFrame#floatingTopTransport QPushButton {
            color:#f9ffff;font-size:24px;font-weight:900;
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #8eaac1,stop:.10 #4e7e9e,stop:.29 #184d74,
                stop:.64 #0a3055,stop:1 #051b32);
            border:1px solid #75c7e4;border-top:2px solid #e5ffff;
            border-bottom:2px solid #031528;border-radius:9px;
            min-height:34px; }
        QFrame#floatingTopTransport QPushButton#neonPlay{
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #438967,stop:.15 #206c53,stop:.50 #103c37,stop:1 #0a2833);
            color:#aaffb8;border:2px solid #55ffb1;border-top:2px solid #b6ffc9;
        }
        QFrame#floatingTopTransport QPushButton:hover{
            border:1px solid #a5f7ff;background:#15648b;}
        QFrame#floatingTopTransport QPushButton:pressed{
            background:#1477a2;border-top:2px solid #04182b;}
        QFrame#floatingTopTransport QPushButton:disabled{color:#7d9dab;}
        QFrame#floatingTopTransport QSlider::groove:horizontal{
            background:#04131e;height:7px;border:1px solid #276e8e;
            border-radius:4px;}
        QFrame#floatingTopTransport QSlider::sub-page:horizontal{
            background:#48e2f2;border-radius:3px;}
        QFrame#floatingTopTransport QSlider::handle:horizontal{
            background:#e4faff;border:1px solid #ffffff;border-radius:6px;
            width:14px;margin:-5px 0;}
        """)
        row=QHBoxLayout(self)
        row.setContentsMargins(12,6,12,6);row.setSpacing(8)
        self.play=QPushButton("▶",self)
        self.pause=QPushButton("Ⅱ",self)
        self.stop=QPushButton("▦",self)
        self.play.setObjectName("neonPlay")
        self.pause.setObjectName("neonPause")
        self.stop.setObjectName("neonStop")
        green_glow=QGraphicsDropShadowEffect(self.play)
        green_glow.setBlurRadius(19)
        green_glow.setOffset(0,0)
        green_glow.setColor(QColor(49,255,123,160))
        self.play.setGraphicsEffect(green_glow)
        self.play.setToolTip("Reproducir pistas asignadas")
        self.pause.setToolTip("Pausar y reanudar")
        self.stop.setToolTip("Detener mezcla")
        for widget in (self.play,self.pause,self.stop):
            widget.setFixedSize(73 if widget is self.play else 67,45)
            row.addWidget(widget)
        self.clock=QLabel("00:00 / 00:00",self)
        self.clock.setStyleSheet("color:#f4ffff;font-size:13px;font-weight:900;background:transparent;")
        self.clock.setFixedWidth(124)
        self.clock.setAlignment(Qt.AlignCenter)
        row.addWidget(self.clock)
        self.timeline=NeonSeekSlider(self)
        self.timeline.setRange(0,1000)
        self.timeline.setTracking(False)
        self.timeline.setProperty("allowWideSlider",True)
        self.timeline.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.timeline.sliderReleased.connect(self.seek)
        row.addWidget(self.timeline,1)
        self.status=QLabel("Sin pistas",self)
        self.status.setStyleSheet("color:#a1d4df;font-size:9px;")
        self.status.setMaximumWidth(120)
        self.status.hide()  # Estado accesible por tooltip; la referencia no duplica texto.
        self.setFixedHeight(68)
        self.play.clicked.connect(self.play_selected)
        self.pause.clicked.connect(self.pause_selected)
        self.stop.clicked.connect(self.stop_selected)
        self.timer=QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.view.attach_transport(self)
        self._sync_meters()

    def _sync_meters(self):
        self._meter_names=tuple(self.view._channel_plan())
        self.track_meters={
            key:(entry["source"],entry["meter"])
            for key,entry in self.view.channels.items()
        }

    def refresh(self):
        from preview_player import timecode
        self._sync_meters()
        if self.live.running and (
            (self.live.duration_ms and self.live.position()>=self.live.duration_ms)
            or (self.live._eof and self.live._queue.empty() and self.live.blocks)):
            self.live.stop()
        self.play.setEnabled(self.view.ready())
        self.pause.setEnabled(self.live.running)
        self.stop.setEnabled(self.live.running)
        self.timeline.setEnabled(self.live.running and self.live.duration_ms>0)
        position=self.live.position() if self.live.running else 0
        self.clock.setText(f"{timecode(position)} / {timecode(self.live.duration_ms)}")
        if not self.timeline.isSliderDown() and self.live.duration_ms:
            with QSignalBlocker(self.timeline):
                self.timeline.setValue(round(position*1000/self.live.duration_ms))
        peak_map=(self.live.track_peaks if self.live.running and not self.live.paused
                  else {})
        self.view.update_channel_vus(peak_map)
        if self.live.running:
            self.status.setText("Pausado" if self.live.paused
                                else f"{len(self.view.selected)} pistas")
        elif self._notice:
            self.status.setText(self._notice[:35])
        else:
            self.status.setText(f"{len(self.view.selected)} pistas seleccionadas")

    def cleanup(self):
        self.timer.stop()
        self.live.stop()
        self.view.cleanup()

