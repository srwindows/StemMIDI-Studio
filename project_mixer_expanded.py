"""Mezclador ampliado: catálogo real, selección múltiple y faders dinámicos."""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QTimer, QEvent, QRect
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QListWidget,
    QListWidgetItem, QSlider, QCheckBox, QScrollArea, QSizePolicy,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle,
)

AUDIO={".wav",".flac",".mp3",".ogg",".m4a",".aif",".aiff",".opus"}
MIDI={".mid",".midi"}
FAMILIES=("Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros")
FONT="#c7efff"
SURFACE="#041734"


def label(text,parent=None):
    widget=QLabel(text,parent)
    widget.setStyleSheet("color:#c7efff;background:transparent;")
    return widget


class ContrastFileCheckboxDelegate(QStyledItemDelegate):
    """Checkbox grande, visible y clicable independientemente del tema Qt."""

    @staticmethod
    def indicator_rect(option,index):
        item_option=QStyleOptionViewItem(option)
        widget=option.widget
        if widget is not None:
            rect=widget.style().subElementRect(
                QStyle.SE_ItemViewItemCheckIndicator,item_option,widget)
        else:
            rect=QRect()
        if not rect.isValid() or rect.isEmpty():
            rect=QRect(option.rect.left()+5,option.rect.center().y()-9,18,18)
        center=rect.center()
        return QRect(center.x()-9,center.y()-9,19,19)

    def paint(self,painter,option,index):
        # Texto/selección se siguen dibujando mediante la clase estándar.
        super().paint(painter,option,index)
        state=index.data(Qt.CheckStateRole)
        if state is None:return
        from PySide6.QtGui import QColor,QPen,QPainterPath,QPainter
        rect=self.indicator_rect(option,index)
        checked=state==Qt.Checked
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#d7fbff"),2))
        painter.setBrush(QColor("#4deafb") if checked else QColor("#081833"))
        painter.drawRoundedRect(rect,4,4)
        if checked:
            mark=QPainterPath()
            mark.moveTo(rect.left()+4,rect.top()+9)
            mark.lineTo(rect.left()+8,rect.top()+13)
            mark.lineTo(rect.left()+15,rect.top()+5)
            painter.setPen(QPen(QColor("#071a31"),2.5,
                                Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            painter.drawPath(mark)
        painter.restore()

    def editorEvent(self,event,model,option,index):
        if (event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonRelease)
            and event.button()==Qt.LeftButton
            and self.indicator_rect(option,index).adjusted(-1,-1,1,1).contains(
                event.position().toPoint())):
            if event.type()==QEvent.MouseButtonRelease:
                old=index.data(Qt.CheckStateRole)
                model.setData(index,Qt.Unchecked if old==Qt.Checked else Qt.Checked,
                              Qt.CheckStateRole)
            return True
        return super().editorEvent(event,model,option,index)


class ProjectMixerView(QWidget):
    """Los faders básicos son espejos del Mezclador de Inicio, no otro motor."""
    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self.sources={}
        self.selected=set()
        self.checked_mutes={}
        self.extra_gains={}
        self.channels={}
        self._signature=None
        self._updating=False
        self._last_refresh=0.
        self._audio_cache={}
        self._render_queue=[]
        self._rendering=None
        self._proc=None
        self._tmp=tempfile.TemporaryDirectory(prefix="stemmidi_mixer_midi_")
        self.transport=None
        self.setObjectName("projectMixerView")
        self.setStyleSheet("""
            QWidget#projectMixerView{background:transparent;border:0;}
            QFrame#projectFilesPanel {
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                     stop:0 #133763,stop:.11 #09254d,stop:1 #04152c);
                border:1px solid #4098cc;border-top:1px solid #8fe7ff;
                border-radius:7px;
            }
            QFrame#projectChannelArea {
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                     stop:0 #0c3265,stop:1 #03162e);
                border:1px solid #267fc4;border-radius:7px;
            }
            QListWidget#projectMixFiles{
                background:#04152f;color:#dcf5ff;
                border:1px solid #2f95dc;border-radius:6px;
                alternate-background-color:#0b254c;font-size:12px;}
            QListWidget#projectMixFiles::item{padding:4px 7px;min-height:21px;}
            QListWidget#projectMixFiles::item:hover{background:#0c4980;}
            QListWidget#projectMixFiles::item:selected{background:#12639a;color:white;}
            QScrollArea#projectChannelScroll{background:#04142f;border:1px solid #1f76c8;border-radius:6px;}
            QFrame#projectChannelCell{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                  stop:0 #03152c,stop:.12 #204c77,stop:.25 #0e3159,
                  stop:.70 #092344,stop:.88 #173d68,stop:1 #051832);
                border:1px solid #377ca9;border-top:1px solid #8ccde7;
                border-radius:6px;
            }
            QFrame#projectChannelCell QLabel{color:#d9f5ff;font-weight:700;}
            QFrame#projectChannelCell QCheckBox{
                color:#dcf9ff;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                  stop:0 #345c86,stop:.5 #143251,stop:1 #041329);
                border:1px solid #5688b0;border-radius:4px;
                padding:1px 6px;min-height:17px;min-width:27px;
            }
            QFrame#projectChannelCell QCheckBox:checked{
                background:#a43649;color:#fff5f6;border-color:#ff7b86;}
            QFrame#projectChannelCell QCheckBox:disabled{color:#6586a1;}
            QCheckBox{color:#f4ecf1;font-weight:700;}
            QCheckBox:checked{color:#ffb9c6;}
        """)
        box=QVBoxLayout(self)
        box.setContentsMargins(2,2,2,2)
        box.setSpacing(3)
        # Canales a la izquierda; selección de archivos SOLO en el margen
        # derecho, a partir de donde comienza «Abrir ventana flotante».
        work_row=QHBoxLayout()
        work_row.setContentsMargins(0,0,0,0)
        work_row.setSpacing(6)
        self.channel_panel=QFrame(self)
        self.channel_panel.setObjectName("projectChannelArea")
        channel_box=QVBoxLayout(self.channel_panel)
        channel_box.setContentsMargins(6,5,6,5)
        channel_box.setSpacing(4)
        channels_head=label("CANALES · FADERS DE GANANCIA",self.channel_panel)
        channels_head.setStyleSheet("color:#93eeff;font-size:11px;font-weight:800;")
        channels_head.setFixedHeight(19)
        channel_box.addWidget(channels_head,0)
        self.channel_scroll=QScrollArea(self.channel_panel)
        self.channel_scroll.setObjectName("projectChannelScroll")
        self.channel_scroll.setWidgetResizable(True)
        self.channel_scroll.setFrameShape(QFrame.NoFrame)
        self.channel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.channel_scroll.setMinimumHeight(142)
        self.channel_scroll.setMaximumHeight(1000)
        self.channel_scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.channel_root=QWidget()
        self.channel_root.setObjectName("projectChannelRoot")
        self.channel_row=QHBoxLayout(self.channel_root)
        self.channel_row.setContentsMargins(4,4,4,4)
        self.channel_row.setSpacing(4)
        self.channel_scroll.setWidget(self.channel_root)
        channel_box.addWidget(self.channel_scroll,1)
        work_row.addWidget(self.channel_panel,1)

        self.file_panel=QFrame(self)
        self.file_panel.setObjectName("projectFilesPanel")
        self.file_panel.setMinimumWidth(265)
        self.file_panel.setMaximumWidth(355)
        self.file_panel.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        file_box=QVBoxLayout(self.file_panel)
        file_box.setContentsMargins(7,6,7,5)
        file_box.setSpacing(4)
        files_head=label("ARCHIVOS PARA MEZCLAR",self.file_panel)
        files_head.setStyleSheet("color:#93eeff;font-weight:800;font-size:11px;")
        files_head.setFixedHeight(19)
        file_box.addWidget(files_head)
        from results_dragdrop import FilesDragList
        self.file_list=FilesDragList(self.file_panel)
        self.file_list.setObjectName("projectMixFiles")
        self.file_list.set_drop_handler(
            lambda paths:self.home._result_file_drag_router.deliver("mixer",paths)
            if getattr(self.home,"_result_file_drag_router",None) else False,
            AUDIO|MIDI)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setItemDelegate(ContrastFileCheckboxDelegate(self.file_list))
        self.file_list.setMinimumHeight(98)
        self.file_list.setMaximumHeight(1000)
        self.file_list.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.file_list.itemChanged.connect(self._check_source)
        file_box.addWidget(self.file_list,1)
        self.summary=label("Marca los archivos que quieras mezclar.",self.file_panel)
        self.summary.setStyleSheet("color:#acdff7;font-size:10px;")
        self.summary.setWordWrap(True)
        self.summary.setMinimumHeight(17)
        self.summary.setMaximumHeight(30)
        file_box.addWidget(self.summary,0)
        work_row.addWidget(self.file_panel,0)
        box.addLayout(work_row,1)
        self.refresh_catalog(force=True)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        # En monitores estrechos los archivos no deben ahogar los 7 faders.
        target=min(355,max(265,round(self.width()*0.28)))
        if self.file_panel.maximumWidth()!=target:
            self.file_panel.setFixedWidth(target)

    @staticmethod
    def _canonical(file):
        return str(Path(file).expanduser().resolve())

    def _catalog(self):
        project=getattr(self.home.main,"project_dir",None)
        if not project:return {}
        main=self.home.main
        files=list(self.home._gather_files())
        try:files.extend(self.home.workbench.converter.project_stem_paths())
        except (AttributeError,ValueError,OSError):pass
        for candidate in (getattr(self.home,"selected_midi",None),
                          getattr(self.home,"selected_file",None)):
            if candidate:files.append(candidate)
        # No mezclar medios de proyectos antiguos; los de fuera solo se
        # admiten cuando fueron cargados explícitamente como origen activo.
        root=Path(project).resolve()
        explicit_sources=[
            getattr(self.home,"selected_midi",None),
            getattr(self.home,"selected_file",None),
            *self.home.workbench.midi_storage.items]
        explicit={self._canonical(p) for p in explicit_sources if p}
        result={}
        for file in files:
            try:
                path=Path(file).expanduser()
                if not path.is_file() or path.is_symlink():continue
                if path.suffix.lower() not in AUDIO|MIDI:continue
                resolved=path.resolve()
                if not resolved.is_relative_to(root) and str(resolved) not in explicit:
                    continue
                result[str(resolved)]=resolved
            except (TypeError,OSError,ValueError):continue
        # Primero todos los formatos de AUDIO y después todos los MIDI.
        # Dentro de cada categoría: orden alfabético sin distinguir mayúsculas.
        return dict(sorted(result.items(),key=lambda entry:(
            1 if entry[1].suffix.lower() in MIDI else 0,
            entry[1].name.casefold(),str(entry[1]).casefold())))

    def refresh_catalog(self,force=False):
        if self._updating:return
        import time
        now=time.monotonic()
        if not force and now-self._last_refresh<3.:return
        self._last_refresh=now
        catalog=self._catalog()
        signature=tuple(catalog)
        if not force and signature==self._signature:return
        self._signature=signature
        self.sources=catalog
        self.selected.intersection_update(catalog)
        self._updating=True
        self.file_list.blockSignals(True)
        try:
            self.file_list.clear()
            for key,path in catalog.items():
                group=(self.home._stem_for(path) if path.suffix.lower() in AUDIO
                       else "MIDI")
                text=f"{group}  ·  {path.name}"
                item=QListWidgetItem(text)
                item.setData(Qt.UserRole,key)
                item.setToolTip(str(path))
                item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if key in self.selected else Qt.Unchecked)
                self.file_list.addItem(item)
        finally:
            self.file_list.blockSignals(False)
            self._updating=False
        self._sync_channels()

    def _check_source(self,item):
        if self._updating:return
        key=item.data(Qt.UserRole)
        if key not in self.sources:return
        if item.checkState()==Qt.Checked:
            self.selected.add(key)
            if self.sources[key].suffix.lower() in MIDI:
                self._schedule_midi(key)
        else:self.selected.discard(key)
        self._sync_channels()
        if self.transport:self.transport.selection_changed()

    def selected_files(self):
        return [(key,self.sources[key]) for key in self.selected if key in self.sources]

    def _channel_plan(self):
        # Los siete canales de siempre ocupan exactamente sus posiciones.
        # Cada archivo adicional marcado obtiene su propio canal, incluso
        # cuando pertenece a una familia que ya tiene otro stem.
        from stem_detection import is_separated_stem
        base={family:None for family in FAMILIES}
        extras=[]
        trusted={str(p.resolve()) for p in self.home.workbench.converter.project_stem_paths()}
        for key,path in sorted(self.selected_files(),key=lambda kv:kv[1].name.casefold()):
            family=self.home._stem_for(path) if path.suffix.lower() in AUDIO else None
            is_family=(family in base and (is_separated_stem(path) or key in trusted))
            if is_family and base[family] is None:
                base[family]=key
            else:extras.append((key,path))
        plan=[(f,base[f],f) for f in FAMILIES]
        plan.extend((key,key,("MIDI · " if path.suffix.lower() in MIDI else "")+
                     path.stem[:18]) for key,path in extras)
        return plan

    def _sync_channels(self):
        plan=self._channel_plan()
        while self.channel_row.count():
            item=self.channel_row.takeAt(0)
            widget=item.widget()
            if widget:widget.deleteLater()
        self.channels={}
        for channel_key,source,label_text in plan:
            box=QFrame(self.channel_root)
            box.setObjectName("projectChannelCell")
            box.setFixedWidth(87)
            layout=QVBoxLayout(box)
            layout.setContentsMargins(3,3,3,3)
            layout.setSpacing(2)
            caption=label(label_text,box)
            caption.setAlignment(Qt.AlignHCenter)
            caption.setToolTip(str(self.sources[source]) if source else label_text)
            caption.setFixedHeight(18)
            caption.setWordWrap(True)
            layout.addWidget(caption)
            # Reutilizar el fader hardware 3D ya probado en el estudio.
            # Su relleno SE ILUMINA DESDE ABAJO, con máximo en la parte
            # superior (QSlider normal) y capuchón tridimensional.
            from studio_home import StudioFader
            fader=StudioFader(box)
            fader.setObjectName("projectVolumeFader")
            fader.setInvertedAppearance(False)
            fader.setInvertedControls(False)
            fader.setToolTip("Arrastra para ajustar el nivel del canal "+label_text)
            fader.setRange(0,150)
            fader.setSingleStep(1)
            fader.setPageStep(10)
            fader.setTracking(True)
            existing=self.home.mixer_rows.get(channel_key)
            value=(existing["fader"].value() if existing is not None
                   else self.extra_gains.get(channel_key,100))
            fader.setValue(value)
            # Los 7 faders base son ajustables SIEMPRE, aunque un canal
            # aún no tenga un archivo marcado. No reproducen nada hasta
            # que se selecciona una fuente. Los adicionales son activos.
            fader.setEnabled(True)
            fader.setMinimumHeight(70)
            fader.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
            layout.addWidget(fader,1,Qt.AlignHCenter)
            readout=label(f"{value}%")
            readout.setAlignment(Qt.AlignCenter)
            readout.setFixedHeight(16)
            readout.setStyleSheet(
                "color:#e1faff;font-weight:800;background:#03172e;"
                "border:1px solid #2a739d;border-radius:3px;")
            layout.addWidget(readout)
            muted=QCheckBox("M",box)
            if existing is not None:
                muted.setChecked(self.home.track_rows[channel_key]["mute"].isChecked())
            else:muted.setChecked(self.checked_mutes.get(channel_key,False))
            muted.setEnabled(source is not None)
            muted.setToolTip("Silenciar únicamente este archivo")
            muted.setMaximumHeight(19)
            layout.addWidget(muted,0,Qt.AlignHCenter)
            fader.valueChanged.connect(
                lambda amount,k=channel_key,t=readout:self._level(k,amount,t))
            muted.toggled.connect(lambda flag,k=channel_key:self._mute(k,flag))
            self.channel_row.addWidget(box,1,Qt.AlignHCenter)
            self.channels[channel_key]=dict(source=source,fader=fader,mute=muted)
        self.channel_root.setMinimumWidth(len(plan)*98+12)
        self.summary.setText(
            f"{len(self.sources)} archivos del proyecto · "
            f"{len(self.selected)} marcados · {len(plan)} canales")
        if self.transport:self.transport.selection_changed()

    def _level(self,key,amount,readout):
        readout.setText(f"{amount}%")
        if key in self.home.mixer_rows:
            self.home.mixer_rows[key]["fader"].setValue(amount)
        else:self.extra_gains[key]=amount
        if self.transport:self.transport.selection_changed()

    def _mute(self,key,flag):
        if key in self.home.track_rows:
            source=self.home.track_rows[key]["mute"]
            source.setChecked(flag)
            self.home.toggle_stem(key,"mute",flag)
        else:self.checked_mutes[key]=flag
        if self.transport:self.transport.selection_changed()

    def paths_for_mix(self):
        return [(key,self.audio_path(key)) for key in sorted(self.selected)
                if self.audio_path(key) is not None]

    def audio_path(self,key):
        if key not in self.sources:return None
        source=self.sources[key]
        if source.suffix.lower() in MIDI:return self._audio_cache.get(key)
        return source

    def ready(self):
        return bool(self.selected) and all(self.audio_path(k) is not None
                                           for k in self.selected)

    def effective_levels(self):
        result={}
        master=self.home.master_volume.value()/100.
        for channel,data in self.channels.items():
            key=data["source"]
            if key is None:continue
            result[key]=(0. if data["mute"].isChecked()
                         else master*data["fader"].value()/100.)
        return result

    def attach_transport(self,transport):
        self.transport=transport
        self.transport.selection_changed()

    def _schedule_midi(self,key):
        if key in self._audio_cache or key in self._render_queue or self._rendering==key:
            return
        self._render_queue.append(key)
        self._next_midi()

    def _next_midi(self):
        if self._proc is not None:return
        while self._render_queue:
            key=self._render_queue.pop(0)
            if key not in self.selected or key not in self.sources:continue
            file=self.sources[key]
            dest=Path(self._tmp.name)/(str(abs(hash(key)))+".wav")
            self._rendering=key
            # El SF2 de este mismo proyecto/programa se usa si fue elegido;
            # de lo contrario TiMidity utiliza su banco configurado.
            options=["-s","44100"]
            card=getattr(self.home,"midi_to_audio",None)
            sf2=getattr(card,"soundfont",None) if card is not None else None
            if sf2 is not None and Path(sf2).is_file():
                config=Path(self._tmp.name)/"soundfont.cfg"
                escaped=str(Path(sf2).resolve()).replace("\\","\\\\").replace('"','\\"')
                config.write_text('soundfont "'+escaped+'"\n',encoding="utf-8")
                options.extend(["-c",str(config)])
            process=QProcess(self)
            self._proc=process
            process.finished.connect(
                lambda code,status,p=process,k=key,o=dest:
                self._midi_finished(p,k,o,code,status))
            process.errorOccurred.connect(
                lambda error,p=process,k=key:
                self._midi_error(p,k,error))
            if sys.platform=="darwin":
                from soundfont_catalog import system_soundfont
                bank=Path(sf2) if sf2 and Path(sf2).is_file() else system_soundfont()
                if bank is None:
                    self._midi_failed(process,key,"Banco General MIDI no disponible")
                    return
                process.start("fluidsynth",[
                    "-ni","-g","0.7","-r","44100",
                    "-F",str(dest),str(bank),str(file)])
            else:
                process.start("timidity",[
                    str(file),"-Ow","-o",str(dest),*options])
            self.summary.setText("Sintetizando MIDI para mezclar: "+file.name)
            if self.transport:self.transport.selection_changed()
            return

    def _midi_error(self,proc,key,error):
        if proc is not self._proc:return
        if error==QProcess.FailedToStart:
            self._midi_failed(proc,key,"Motor MIDI integrado no disponible")

    def _midi_finished(self,proc,key,dest,code,status):
        if proc is not self._proc:return
        success=(code==0 and status==QProcess.NormalExit
                 and dest.is_file() and dest.stat().st_size>128)
        if success:
            self._audio_cache[key]=dest
            self._proc=None
            self._rendering=None
            proc.deleteLater()
            if self.transport:self.transport.selection_changed()
            self._next_midi()
        else:
            error=bytes(proc.readAllStandardError()).decode("utf-8","replace")[-170:]
            self._midi_failed(proc,key,error or "No se ha podido sintetizar el MIDI")

    def _midi_failed(self,proc,key,reason):
        self._proc=None
        self._rendering=None
        proc.deleteLater()
        self.selected.discard(key)
        self.summary.setText("MIDI no reproducible: "+reason)
        for i in range(self.file_list.count()):
            item=self.file_list.item(i)
            if item.data(Qt.UserRole)==key:
                was=self.file_list.blockSignals(True)
                item.setCheckState(Qt.Unchecked)
                self.file_list.blockSignals(was)
                item.setToolTip("Conversión MIDI fallida: "+reason)
                break
        self._sync_channels()
        self._next_midi()

    def reopen(self):
        if self._tmp is None:
            self._tmp=tempfile.TemporaryDirectory(prefix="stemmidi_mixer_midi_")
            self._audio_cache.clear()
        self.refresh_catalog(force=True)
        for key in self.selected:
            if self.sources.get(key) is not None and self.sources[key].suffix.lower() in MIDI:
                self._schedule_midi(key)

    def cleanup(self):
        self.transport=None
        self._render_queue.clear()
        self._rendering=None
        if self._proc is not None:
            proc=self._proc
            self._proc=None
            proc.terminate()
            if not proc.waitForFinished(500):proc.kill()
            proc.deleteLater()
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp=None
        self._audio_cache.clear()


from studio_vu_unified import (Ballistics,draw_vertical,
                               draw_mono_horizontal)

class ScaledMeter(QWidget):
    """VU estéreo L/R por pista, con el mismo motor visual del máster.

    No suma ni colapsa los canales: utiliza los picos separados medidos por
    LowLatencyStemMixer, 24 segmentos, escala -60...0 dBFS.
    """
    def __init__(self,label_text,parent=None,width=146):
        super().__init__(parent)
        self.caption=label_text
        self._ballistics=Ballistics(2)
        self.is_master=False
        self.setFixedWidth(width)
        self.setFixedHeight(102)
        self.setToolTip("VU ESTÉREO L/R real · 24 segmentos · −60 a 0 dBFS")
    def set_peak(self,amplitude):
        # Compatibilidad con las llamadas antiguas (no se usa para mezcla).
        self.set_peaks(amplitude,amplitude)
    def set_peaks(self,left,right):
        self._ballistics.feed((left,right),(left,right))
        self.update()
    def paintEvent(self,event):
        from PySide6.QtGui import QPainter,QColor,QFont,QPen,QLinearGradient
        from PySide6.QtCore import QRectF
        from studio_vu_unified import draw_stereo
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing,True)
        outer=self.rect().adjusted(1,1,-1,-1)
        grad=QLinearGradient(0,0,0,self.height())
        grad.setColorAt(0,QColor("#164776"))
        grad.setColorAt(.14,QColor("#071b3a"))
        grad.setColorAt(1,QColor("#041020"))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor("#327aa8"),1.0))
        painter.drawRoundedRect(outer,5,5)
        painter.setPen(QColor("#def8ff"))
        painter.setFont(QFont("Sans",8,QFont.DemiBold))
        font=painter.fontMetrics()
        name=font.elidedText(self.caption,Qt.ElideRight,self.width()-13)
        painter.drawText(QRectF(5,3,self.width()-10,18),Qt.AlignCenter,name)
        draw_stereo(painter,self.rect().adjusted(4,22,-4,-5),
                    self._ballistics.shown,self._ballistics.held,
                    ("L","R"),True)
        painter.end()

class HorizontalMasterMeter(QWidget):
    """La barra HORIZONTAL del máster conserva sus 220×31 y ubicación."""
    def __init__(self,channel,parent=None):
        super().__init__(parent)
        self.caption="Máster "+channel
        self.channel=channel
        self.peak=0.
        self._ballistics=Ballistics(1)
        self.setFixedSize(220,31)
        self.setToolTip("Máster "+channel+" · mismo VU Monitor · −60..0 dBFS")
    def set_peak(self,amplitude):
        self.peak=max(0.,min(1.5,float(amplitude)))
        self._ballistics.feed((self.peak,),(self.peak,))
        self.update()
    def paintEvent(self,event):
        from PySide6.QtGui import QPainter
        painter=QPainter(self)
        draw_mono_horizontal(painter,self.rect(),self._ballistics.shown[0],
                            self._ballistics.held[0],self.channel,True)
        painter.end()

class ProjectMixerTransport(QFrame):
    """Único transporte, volumen máster y VU dinámicos para esta ventana."""
    def __init__(self,view,parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QPushButton
        from low_latency_stem_mixer import LowLatencyStemMixer
        self.view=view
        self.setObjectName("projectMixerTransport")
        self.setStyleSheet("""
            QFrame#projectMixerTransport {background:#041a3f;
                border:1px solid #2bbafa;border-radius:7px;}
            QFrame#projectMixerTransport QLabel{color:#ccefff;}
            QFrame#projectMixerTransport QScrollArea{
                background:#041b3c;border:0;}
            QFrame#projectMixerTransport QPushButton {
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                   stop:0 #64a7d1,stop:.12 #2f6c9f,
                   stop:.49 #144677,stop:.55 #10375f,stop:1 #051a39);
                color:#edfcff;border:1px solid #73a9c9;
                border-top:1px solid #d8f9ff;
                border-bottom:2px solid #06203a;
                border-radius:5px;padding:3px 10px;min-height:26px;
                font-weight:800;}
            QFrame#projectMixerTransport QPushButton:hover {
                border-color:#72edff;background:#1364a0;}
            QFrame#projectMixerTransport QPushButton:pressed {
                background:#082444;border-top:2px solid #06162b;
                border-bottom:1px solid #66dfff;}
            QFrame#projectMixerTransport QPushButton:disabled {
                color:#7092ab;border-color:#284c69;
                background:#0a2947;}
            QSlider#projectTimeline::groove:horizontal{
                height:9px;background:#031327;border:1px solid #4382ae;
                border-radius:4px;}
            QSlider#projectTimeline::sub-page:horizontal{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #7bffff,stop:.4 #22cbe9,stop:1 #0a6088);
                border-radius:4px;}
            QSlider#projectTimeline::handle:horizontal{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #ffffff,stop:.5 #9bd4f5,stop:1 #426d91);
                border:1px solid #dbfcff;border-radius:6px;
                width:13px;margin:-4px 0;}
        """)
        self.live=LowLatencyStemMixer(self)
        self.live.error.connect(self._error)
        self._notice=""
        self._meter_names=()
        layout=QVBoxLayout(self)
        layout.setContentsMargins(8,5,8,7);layout.setSpacing(4)
        # Transporte: botones → VU master L/R → progreso CORTO → reloj.
        # La barra no debe atravesar la ventana ni separar los botones del VU.
        transport=QGridLayout()
        transport.setContentsMargins(0,0,0,0)
        transport.setHorizontalSpacing(9)
        transport.setVerticalSpacing(2)
        transport.setColumnStretch(4,1)
        buttons=QHBoxLayout()
        buttons.setContentsMargins(0,0,0,0)
        buttons.setSpacing(5)
        self.play=QPushButton("▶ Play",self)
        self.pause=QPushButton("Ⅱ",self)
        self.stop=QPushButton("■",self)
        for button in (self.play,self.pause,self.stop):
            button.setCursor(Qt.PointingHandCursor)
        buttons.addWidget(self.play)
        buttons.addWidget(self.pause)
        buttons.addWidget(self.stop)
        transport.addLayout(buttons,0,0,2,1,Qt.AlignVCenter)
        self.master_meters={}
        for row_index,name in enumerate(("L","R")):
            meter=HorizontalMasterMeter(name,self)
            transport.addWidget(meter,row_index,1)
            self.master_meters[name]=meter
        self.timeline=QSlider(Qt.Horizontal,self)
        self.timeline.setObjectName("projectTimeline")
        self.timeline.setRange(0,1000)
        self.timeline.setTracking(False)
        self.timeline.sliderReleased.connect(self.seek)
        self.timeline.setProperty("allowWideSlider",True)
        self.timeline.setFixedWidth(340)  # aproximadamente cuatro tiras de canal
        transport.addWidget(self.timeline,0,2,2,1,Qt.AlignVCenter)
        self.clock=label("00:00 / 00:00")
        self.clock.setStyleSheet("color:#e2f9ff;font-weight:800;")
        transport.addWidget(self.clock,0,3,2,1,Qt.AlignVCenter)
        layout.addLayout(transport)
        volume=QHBoxLayout()
        volume.addWidget(label("Volumen general"))
        self.master_volume=QSlider(Qt.Horizontal,self)
        self.master_volume.setRange(self.view.home.master_volume.minimum(),
                                    self.view.home.master_volume.maximum())
        self.master_volume.setValue(self.view.home.master_volume.value())
        self.master_volume.valueChanged.connect(self._set_master)
        self.view.home.master_volume.valueChanged.connect(self._pull_master)
        self.master_volume.setMaximumWidth(230)
        volume.addWidget(self.master_volume,0)
        self.master_value=label(str(self.master_volume.value())+" %")
        volume.addWidget(self.master_value)
        volume.addStretch(1)
        layout.addLayout(volume)
        layout.addWidget(label("VU POR CANAL · ESTÉREO L/R · −60 a 0 dBFS"))
        self.meter_scroll=QScrollArea(self)
        self.meter_scroll.setWidgetResizable(True)
        self.meter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.meter_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.meter_scroll.setMinimumHeight(86);self.meter_scroll.setMaximumHeight(117)
        self.meter_root=QWidget()
        self.meter_row=QHBoxLayout(self.meter_root)
        self.meter_row.setContentsMargins(2,2,2,2);self.meter_row.setSpacing(6)
        self.meter_scroll.setWidget(self.meter_root)
        layout.addWidget(self.meter_scroll)
        self.track_meters={}
        self.status=label("Marca los archivos del proyecto para escucharlos.")
        layout.addWidget(self.status)
        self.play.clicked.connect(self.play_selected)
        self.pause.clicked.connect(self.pause_selected)
        self.stop.clicked.connect(self.stop_selected)
        self.timer=QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.refresh)
        self._compact_state=None
        self._meter_width_state=None
        self.timer.start()
        self.view.attach_transport(self)
        self._sync_meters()
        self._fit_layout()

    def _set_master(self,value):
        self.view.home.master_volume.setValue(value)
        self.master_value.setText(str(value)+" %")
        self.selection_changed()

    def _pull_master(self,value):
        old=self.master_volume.blockSignals(True)
        self.master_volume.setValue(value)
        self.master_volume.blockSignals(old)
        self.master_value.setText(str(value)+" %")
        self.selection_changed()

    def _sync_meters(self):
        plan=self.view._channel_plan()
        signature=tuple((a,b,c) for a,b,c in plan)
        if signature==self._meter_names:return
        self._meter_names=signature
        while self.meter_row.count():
            item=self.meter_row.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.track_meters={}
        for channel,source,caption in plan:
            meter=ScaledMeter(caption,self.meter_root,146)
            if self._compact_state:
                meter.setFixedHeight(73)
            self.meter_row.addWidget(meter)
            self.track_meters[channel]=(source,meter)
        self.meter_row.addStretch()
        self._meter_width_state=None
        self._fit_meter_widths()

    def _fit_meter_widths(self):
        if not self.track_meters:
            return
        # Encajar las siete lecturas L/R en monitores de 1100px sin crear
        # scroll horizontal ni convertirlas en mono.
        count=len(self.track_meters)
        available=max(0,self.meter_scroll.viewport().width())
        space=max(0,available-12-(count-1)*6-8)
        desired=min(260,max(114,space//count))
        if desired==self._meter_width_state:
            return
        self._meter_width_state=desired
        for source,meter in self.track_meters.values():
            meter.setFixedWidth(desired)
        self.meter_root.setMinimumWidth(count*(desired+6)+12)

    def _fit_layout(self):
        # En alturas 735–800px reducir adornos, NO ocultar transporte,
        # faders, botones M ni el segundo canal del vúmetro.
        compact=self.window().height()<810
        if compact != self._compact_state:
            self._compact_state=compact
            self.setMinimumHeight(190 if compact else 230)
            self.setMaximumHeight(205 if compact else 272)
            self.status.setVisible(not compact)
            for meter in self.master_meters.values():
                meter.setFixedSize(194 if compact else 220,
                                   25 if compact else 31)
            self.meter_scroll.setMinimumHeight(76 if compact else 107)
            self.meter_scroll.setMaximumHeight(82 if compact else 117)
            for _,meter in self.track_meters.values():
                meter.setFixedHeight(73 if compact else 102)
        self._fit_meter_widths()

    def selection_changed(self):
        self._sync_meters()
        if self.live.running:
            inputs=self.view.paths_for_mix()
            ids={key for key,_ in inputs}
            # Una pista nueva exige integrar otra entrada FFmpeg. Mantener
            # la posición actual al reconstruir; mute/faders NO reinician.
            if any(key not in self.live._names for key in ids):
                pos=self.live.position()
                was_paused=self.live.paused
                self.live.set_track_levels(self.view.effective_levels())
                if inputs and self.live.start(inputs,ids,start_ms=pos):
                    if was_paused:self.live.pause()
            else:
                for key in self.live._names:self.live.set_enabled(key,key in ids)
                self.live.set_track_levels(self.view.effective_levels())
        self.refresh()

    def _error(self,message):
        self._notice=message
        self.status.setText(message)

    def play_selected(self):
        if self.live.running:
            if self.live.paused:self.live.pause()
            return
        if not self.view.ready():
            self.status.setText("Selecciona archivos válidos; espera a los MIDI pendientes.")
            return
        inputs=self.view.paths_for_mix()
        if not inputs:return
        self.view.home._sep_listen.stop()
        self.view.home.player.stop()
        self.live.set_track_levels(self.view.effective_levels())
        if self.live.start(inputs,{key for key,_ in inputs}):
            self.status.setText(f"Mezclando {len(inputs)} pistas en sincronía")
        self.refresh()

    def pause_selected(self):
        if self.live.running:self.live.pause()

    def stop_selected(self):
        self.live.stop()
        self.refresh()

    def seek(self):
        if self.live.running and self.live.duration_ms:
            self.live.seek(round(self.live.duration_ms*self.timeline.value()/1000))
            self.live.set_track_levels(self.view.effective_levels())

    def refresh(self):
        from preview_player import timecode
        self._sync_meters()
        self._fit_layout()
        if self.live.running and (
            (self.live.duration_ms and self.live.position()>=self.live.duration_ms)
            or (self.live._eof and self.live._queue.empty() and self.live.blocks)):
            self.live.stop()
        self.play.setEnabled(self.view.ready())
        self.pause.setEnabled(self.live.running)
        self.stop.setEnabled(self.live.running)
        self.timeline.setEnabled(self.live.running and self.live.duration_ms>0)
        pos=self.live.position() if self.live.running else 0
        self.clock.setText(f"{timecode(pos)} / {timecode(self.live.duration_ms)}")
        if not self.timeline.isSliderDown() and self.live.duration_ms:
            old=self.timeline.blockSignals(True)
            self.timeline.setValue(round(1000*pos/self.live.duration_ms))
            self.timeline.blockSignals(old)
        peaks=(self.live.master_peaks if self.live.running and not self.live.paused
               else (0.,0.))
        for channel,peak in zip(("L","R"),peaks):
            self.master_meters[channel].set_peak(peak)
        actual=(self.live.track_peaks if self.live.running and not self.live.paused
                else {})
        for channel,(source,meter) in self.track_meters.items():
            peak=actual.get(source,(0.,0.)) if source else (0.,0.)
            meter.set_peaks(peak[0],peak[1])
        if self.live.running:
            self.status.setText(
                f"Reproduciendo {len(self.view.selected)} archivos · "
                f"{len([v for v in self.view.effective_levels().values() if v==0])} muteados"
                if not self.live.paused else "Pausado")
        elif not self._notice:
            self.status.setText(
                f"{len(self.view.selected)} seleccionados · pulsa Play"
                if self.view.ready() else
                "Marca archivos; MIDI seleccionado pendiente de síntesis"
                if self.view.selected else "Marca los archivos del proyecto para mezclarlos")

    def cleanup(self):
        self.timer.stop()
        self.live.stop()
        self.view.cleanup()
