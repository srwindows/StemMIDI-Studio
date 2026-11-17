"""Pestaña Compositor · mini-DAW multipista MIDI/audio ligado al proyecto.

Lista de Resultados, clips arrastrables, edición no destructiva,
transporte con síntesis/mix real, exportación y persistencia por proyecto.
"""
from __future__ import annotations
from pathlib import Path
import math
import uuid
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt,QTimer,QSignalBlocker,QRectF
from PySide6.QtGui import QBrush,QColor,QPen,QFont,QPainterPath
from PySide6.QtWidgets import (
 QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QLineEdit,
 QComboBox,QSpinBox,QDoubleSpinBox,QSlider,QCheckBox,QListWidget,QListWidgetItem,
 QTableWidget,QTableWidgetItem,QAbstractItemView,QGraphicsView,QGraphicsScene,
 QGraphicsRectItem,QGraphicsItem,QSplitter,QMessageBox,QFileDialog,QFrame,
 QHeaderView,QProgressBar,QSizePolicy,QInputDialog,QMenu)
from compositor_session import CompositorSession,AUDIO,MIDI
from compositor_render import MixWorker
from preview_player import PreviewPlayer

LEFT=16
ROW=30
TOP=32


class ComposerFileList(QListWidget):
    """El explorador de Resultados expone URLs reales para drag-and-drop."""
    def __init__(self,owner):
        super().__init__(owner)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.CopyAction)

    def mimeData(self,items):
        from PySide6.QtCore import QMimeData,QUrl
        data=QMimeData()
        paths=[]
        for item in items:
            path=item.data(Qt.UserRole)
            if path:paths.append(QUrl.fromLocalFile(str(path)))
        data.setUrls(paths)
        return data


class ClipTile(QGraphicsRectItem):
    def __init__(self,owner,track,clip,row,pixels):
        width=max(24,clip["duration"]*owner.session.state["bpm"]/60.*pixels)
        super().__init__(0,0,width,ROW-6)
        self.owner=owner
        self.track=track
        self.clip=clip
        self._shape_key=owner.request_preview_shape(track,clip)
        self.setPos(LEFT+clip["beat"]*pixels,TOP+row*ROW+3)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setToolTip(
            f"{track['name']} · {clip['label']}\n"
            f"Compás {clip['beat']/4.+1:.2f} · "
            f"{clip['duration']:.2f} s\n"
            "Arrastra para mover; doble clic MIDI: abrir Piano Roll")
        color="#1787be" if track["type"]=="audio" else "#8952bf"
        if track["mute"]:color="#42536b"
        self.setBrush(QBrush(QColor(color)))
        self.setPen(QPen(QColor("#70edff"),1.2))
        self.setZValue(2)
        text=owner.scene.addText(clip["label"][:26])
        text.setParentItem(self)
        text.setDefaultTextColor(QColor("#f1fbff"))
        text.setPos(4,-2)
        font=QFont();font.setPointSize(7);font.setBold(True)
        text.setFont(font)
        text.setAcceptedMouseButtons(Qt.NoButton)

    def paint(self,painter,option,widget=None):
        super().paint(painter,option,widget)
        content=self.owner.preview_shape(self._shape_key)
        if not content:return
        box=self.rect().adjusted(3,12,-3,-2)
        if box.width()<5 or box.height()<5:return
        painter.save()
        painter.setClipRect(box)
        if self.track["type"]=="audio":
            # Picos reales calculados de la grabación, sin inventar onda.
            painter.setPen(QPen(QColor("#a3f3df"),1.2))
            path=QPainterPath()
            middle=box.center().y()
            half=box.height()*.46
            points=len(content)
            start=max(0,self.clip["offset"])
            duration=max(.01,self.clip["duration"])
            # Los picos abarcan hasta los primeros 300 s de fuente.
            # Se proyecta la región del clip de manera aproximada.
            for i in range(max(12,int(box.width()))):
                fraction=i/max(1,int(box.width())-1)
                time_offset=start+fraction*duration
                source_span=min(300.,self.clip.get(
                    "source_duration",duration+start))
                idx=min(points-1,max(0,round(time_offset/
                    max(source_span,.01)*(points-1))))
                amp=content[idx]
                x=box.left()+fraction*box.width()
                path.moveTo(x,middle-amp*half)
                path.lineTo(x,middle+amp*half)
            painter.drawPath(path)
        else:
            painter.setPen(QPen(QColor("#c8b3f7"),1.0))
            painter.setBrush(QBrush(QColor("#e2b6ff")))
            start=self.clip["offset"]
            end=start+self.clip["duration"]
            shown=[(t,d,p) for t,d,p in content
                   if t<end and t+d>start]
            if shown:
                low=min(n[2] for n in shown)
                high=max(n[2] for n in shown)
                span=max(10,high-low)
                for t,d,p in shown[:1500]:
                    left=max(t,start)-start
                    right=min(t+d,end)-start
                    if right<=left:continue
                    x=box.left()+box.width()*left/self.clip["duration"]
                    w=max(1.5,box.width()*(right-left)/self.clip["duration"])
                    y=box.bottom()-box.height()*(p-low+.5)/(span+1)
                    painter.drawRect(QRectF(x,y,w,max(2,box.height()/21)))
        painter.restore()

    def mousePressEvent(self,event):
        # Qt gestiona Ctrl/Majús + la selección múltiple y el marco.
        # No sustituir aquí una selección previa por una única nota.
        if event.button()==Qt.RightButton and not self.isSelected():
            self.owner.select_clip(self.clip["id"])
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if self.track["type"]=="midi":
            self.owner.select_clip(self.clip["id"])
            self.owner.open_clip_midi()
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self,event):
        # El movimiento de un grupo se confirma una sola vez desde la
        # vista, para que Deshacer recupere TODOS los clips en una transacción.
        super().mouseReleaseEvent(event)


class ComposerTimeline(QGraphicsView):
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:super().dragEnterEvent(event)

    def dragMoveEvent(self,event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:super().dragMoveEvent(event)

    def dropEvent(self,event):
        urls=event.mimeData().urls()
        if not urls:
            return super().dropEvent(event)
        pos=self.mapToScene(event.position().toPoint())
        beat=self.owner.snap_beat(max(0.,(pos.x()-LEFT)/
                                       self.owner.pixels_per_beat))
        row=int((pos.y()-TOP)/ROW)
        tracks=self.owner.session.state["tracks"]
        target=tracks[row] if 0<=row<len(tracks) else None
        errors=[]
        count=0
        for url in urls:
            path=Path(url.toLocalFile())
            try:
                from compositor_session import MIDI
                kind="midi" if path.suffix.lower() in MIDI else "audio"
                track_id=(target["id"] if target and
                          target["type"]==kind else None)
                self.owner.session.add(path,track_id=track_id,
                                       at_beat=beat)
                count+=1
            except (ValueError,OSError) as error:
                errors.append(str(error))
        self.owner.refresh_timeline()
        self.owner.status.setText(
            f"{count} clip(s) colocados en compás {beat/4+1:.2f}"
            +(" · "+errors[0] if errors else ""))
        event.acceptProposedAction()

    def keyPressEvent(self,event):
        ctrl=bool(event.modifiers()&Qt.ControlModifier)
        if event.key() in (Qt.Key_Delete,Qt.Key_Backspace):
            self.owner.delete_selected()
        elif ctrl and event.key()==Qt.Key_A:
            self.owner.select_all_clips()
        elif ctrl and event.key()==Qt.Key_C:
            self.owner.copy_selected()
        elif ctrl and event.key()==Qt.Key_X:
            self.owner.cut_selected()
        elif ctrl and event.key()==Qt.Key_V:
            self.owner.paste_clip()
        else:
            return super().keyPressEvent(event)
        event.accept()

    def mousePressEvent(self,event):
        scene_point=self.mapToScene(event.pos())
        if event.button()==Qt.LeftButton and scene_point.y()<TOP:
            beat=(scene_point.x()-LEFT)/self.owner.pixels_per_beat
            self.owner.set_playhead(beat)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        updates={}
        for tile in self.scene().selectedItems():
            if not isinstance(tile,ClipTile):continue
            beat=self.owner.snap_beat(max(
                0.,(tile.pos().x()-LEFT)/self.owner.pixels_per_beat))
            tracks=self.owner.session.state["tracks"]
            row=max(0,min(len(tracks)-1,
                          int(round((tile.pos().y()-TOP-3)/ROW))))
            if not tracks:continue
            destination=tracks[row]
            if (abs(beat-tile.clip["beat"])>.001 or
                    destination["id"]!=tile.track["id"]):
                updates[tile.clip["id"]]=(beat,destination["id"])
        if updates:
            try:
                self.owner.session.move_clips(updates)
                self.owner.refresh_timeline()
            except (ValueError,KeyError) as error:
                self.owner.status.setText("Arrastre: "+str(error))
                self.owner.refresh_timeline()

    def contextMenuEvent(self,event):
        pos=self.mapToScene(event.pos())
        tile=self.itemAt(event.pos())
        while tile is not None and not isinstance(tile,ClipTile):
            tile=tile.parentItem()
        if tile is not None and not tile.isSelected():
            self.owner.select_clip(tile.clip["id"])
        menu=self.owner.build_timeline_menu(pos)
        menu.exec(event.globalPos())
        event.accept()

    def __init__(self,owner):
        super().__init__(owner)
        self.setObjectName("composerTimeline")
        self.owner=owner
        self.setScene(owner.scene)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QBrush(QColor("#041a37")))
        self.setMinimumHeight(290)
        self.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.setAcceptDrops(True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)


class ComposerTab(QWidget):
    def __init__(self,main):
        super().__init__(main)
        self.main=main
        self.setObjectName("compositorMainTab")
        self.session=CompositorSession()
        self.project_key=None
        self.selected_clip_id=None
        self.selected_clip_ids=set()
        self._rebuilding_scene=False
        self.playhead_beat=0.
        self.pixels_per_beat=24
        self.worker=None
        self._catalog_signature=None
        self._loading_refresh=False
        self._copied_clip=None
        self._copied_clips=[]
        self.track_meters={}
        self.meter_data={}
        self._render_ready_signature=None
        self._render_requested_signature=None
        self._preview_pool=ThreadPoolExecutor(max_workers=2,
                                              thread_name_prefix="composer-preview")
        self._preview_futures={}
        self._preview_cache={}
        self.scene=QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._selection_changed)
        self._build()
        self._ticker=QTimer(self)
        self._ticker.setInterval(3000)
        self._ticker.timeout.connect(self.refresh_catalog)
        self._ticker.start()
        self._preview_timer=QTimer(self)
        self._preview_timer.setInterval(360)
        self._preview_timer.timeout.connect(self._poll_preview_shapes)
        self._preview_timer.start()
        self._transport_timer=QTimer(self)
        self._transport_timer.setInterval(80)
        self._transport_timer.timeout.connect(self._follow_playback)
        self._transport_timer.start()
        self.sync_project()

    def _button(self,text,callback,tooltip=None):
        button=QPushButton(text,self)
        button.clicked.connect(callback)
        if tooltip:button.setToolTip(tooltip)
        return button

    def _build(self):
        from compositor_professional_layout import build
        build(self)

    def _preview_key(self,clip):
        try:
            p=self.session.file_for(clip)
            s=p.stat()
            return (str(p),s.st_size,s.st_mtime_ns)
        except (ValueError,OSError,TypeError):
            return None

    def request_preview_shape(self,track,clip):
        key=self._preview_key(clip)
        if key is None:return None
        if key not in self._preview_cache and key not in self._preview_futures:
            from compositor_preview_shapes import data_for
            self._preview_futures[key]=self._preview_pool.submit(
                data_for,key[0],track["type"])
        return key

    def preview_shape(self,key):
        return self._preview_cache.get(key,())

    def _poll_preview_shapes(self):
        ready=[]
        for key,future in list(self._preview_futures.items()):
            if not future.done():continue
            ready.append(key)
            try:
                data=future.result()
            except Exception:
                # Límite de hilo: ningún fichero corrupto puede cerrar Qt.
                data=()
            self._preview_cache[key]=data
            del self._preview_futures[key]
        if ready:
            # Solo repintar el contenido de la escena. No reconstruir
            # las pistas: conservar selección, scroll y arrastre.
            self.scene.update()
        if len(self._preview_cache)>256:
            for key in list(self._preview_cache)[:128]:
                self._preview_cache.pop(key,None)

    def _selection_changed(self):
        if self._rebuilding_scene:return
        ids={item.clip["id"] for item in self.scene.selectedItems()
             if isinstance(item,ClipTile)}
        self.selected_clip_ids=ids
        if not ids:
            self.selected_clip_id=None
        elif self.selected_clip_id not in ids:
            self.selected_clip_id=next(iter(ids))
        self._read_clip_to_inspector()
        if hasattr(self,"selection_label"):
            self.selection_label.setText(
                f"{len(ids)} clip(s)" if ids else "Sin selección")

    def selected_ids(self):
        if self.selected_clip_ids:return list(self.selected_clip_ids)
        if self.selected_clip_id:return [self.selected_clip_id]
        return []

    def selected_track_ids(self):
        rows={index.row() for index in self.track_table.selectedIndexes()}
        tracks=self.session.state["tracks"]
        if not rows and 0<=self.track_table.currentRow()<len(tracks):
            rows={self.track_table.currentRow()}
        return [tracks[i]["id"] for i in sorted(rows) if 0<=i<len(tracks)]

    def select_all_clips(self,track_id=None):
        self._rebuilding_scene=True
        for item in self.scene.items():
            if isinstance(item,ClipTile):
                item.setSelected(track_id is None or
                                 item.track["id"]==track_id)
        self._rebuilding_scene=False
        self._selection_changed()

    def _add_at_position(self,beat,track_id=None):
        paths=self.selected_files()
        if not paths:
            self.status.setText(
                "Selecciona primero uno o varios archivos de Resultados.")
            return
        added=[];errors=[]
        from compositor_session import MIDI
        selected_track=(self.session.track(track_id) if track_id else None)
        for path in paths:
            kind="midi" if path.suffix.lower() in MIDI else "audio"
            target=(track_id if selected_track is not None and
                    selected_track["type"]==kind else None)
            try:
                _,clip_id=self.session.add(path,track_id=target,at_beat=beat)
                added.append(clip_id)
            except (ValueError,OSError,RuntimeError) as error:
                errors.append(str(error))
        self._set_after_edit(added)
        self.status.setText(
            f"{len(added)} clips insertados en compás {beat/4+1:.2f}."
            +(" "+errors[0] if errors else ""))

    def build_timeline_menu(self,position):
        """Menú contextual real en clips, filas vacías y regla de tiempo."""
        menu=QMenu(self.timeline)
        menu.setObjectName("composerTimelineContextMenu")
        beat=self.snap_beat(max(
            0.,(position.x()-LEFT)/self.pixels_per_beat))
        row=int((position.y()-TOP)/ROW)
        tracks=self.session.state["tracks"]
        target=tracks[row] if 0<=row<len(tracks) else None
        count=len(self.selected_ids())
        menu.addAction(
            f"Situar guía en compás {beat/4+1:.2f}",
            lambda:self.set_playhead(beat))
        if count:
            menu.addAction(
                f"Dividir {count} clip(s) en la guía",self.split_selected)
            menu.addAction(f"Cortar {count} clip(s)  Ctrl+X",self.cut_selected)
            menu.addAction(f"Copiar {count} clip(s)  Ctrl+C",self.copy_selected)
            menu.addAction(
                f"Duplicar {count} clip(s)",self.duplicate_selected)
            menu.addAction(
                f"Eliminar {count} clip(s)  Supr",self.delete_selected)
        else:
            menu.addAction("Dividir pista en la guía",self.split_selected)
        if self._copied_clips:
            menu.addAction("Pegar clips aquí  Ctrl+V",
                           lambda:(self.set_playhead(beat),self.paste_clip()))
        menu.addSeparator()
        if target is not None:
            menu.addAction(
                f"Seleccionar clips de «{target['name']}»",
                lambda id=target["id"]:self.select_all_clips(id))
        menu.addAction("Seleccionar todos los clips  Ctrl+A",
                       self.select_all_clips)
        menu.addSeparator()
        menu.addAction(
            "Añadir archivos seleccionados de Resultados aquí",
            lambda:self._add_at_position(
                beat,target["id"] if target else None))
        menu.addAction("Importar MIDI o audio…",self.import_media)
        menu.addAction("Nueva pista de audio",lambda:self.create_empty_track("audio"))
        menu.addAction("Nueva pista MIDI",lambda:self.create_empty_track("midi"))
        return menu

    def _track_context_menu(self,pos):
        index=self.track_table.indexAt(pos)
        if index.isValid() and index.row()>=0:
            if index.row() not in {x.row() for x in
                                  self.track_table.selectedIndexes()}:
                self.track_table.selectRow(index.row())
        menu=QMenu(self.track_table)
        menu.setObjectName("composerTrackContextMenu")
        ids=self.selected_track_ids()
        menu.addAction("Nueva pista audio",lambda:self.create_empty_track("audio"))
        menu.addAction("Nueva pista MIDI",lambda:self.create_empty_track("midi"))
        if ids:
            menu.addSeparator()
            menu.addAction("Seleccionar clips de pista(s)",
                           lambda:self._select_clips_of_tracks(ids))
            menu.addAction(
                "Dividir pista(s) en la guía",self.split_track_at_guide)
            menu.addAction(
                f"Eliminar {len(ids)} pista(s)",self.delete_track)
            if len(ids)==1:
                t=self.session.track(ids[0])
                menu.addAction(
                    "Silenciar pista" if not t["mute"] else "Quitar silencio",
                    lambda:self.update_track(t["id"],mute=not t["mute"]))
                menu.addAction(
                    "Solo pista" if not t["solo"] else "Desactivar Solo",
                    lambda:self.update_track(t["id"],solo=not t["solo"]))
        menu.addSeparator()
        menu.addAction("Importar archivo a proyecto",self.import_media)
        menu.exec(self.track_table.viewport().mapToGlobal(pos))

    def _select_clips_of_tracks(self,ids):
        selected=set(ids)
        self._rebuilding_scene=True
        for item in self.scene.items():
            if isinstance(item,ClipTile):
                item.setSelected(item.track["id"] in selected)
        self._rebuilding_scene=False
        self._selection_changed()

    def split_track_at_guide(self):
        ids=set(self.selected_track_ids())
        if not ids:return
        affected=[clip["id"] for track in self.session.state["tracks"]
                  if track["id"] in ids for clip in track["clips"]]
        new=self.session.split_clips(affected,self.playhead_beat)
        self._set_after_edit(new)
        self.status.setText(
            f"{len(new)} clips divididos en pista(s) seleccionadas. "
            "Deshacer disponible." if new else
            "Ningún clip de esas pistas cruza la guía.")

    def create_empty_track(self,kind):
        if not self.project_key:
            self.status.setText("No hay proyecto activo.")
            return
        id=self.session.create_track(kind)
        self.refresh_timeline()
        row=next(i for i,t in enumerate(self.session.state["tracks"])
                 if t["id"]==id)
        self.track_table.selectRow(row)
        self.status.setText(f"Pista {kind.upper()} creada. Deshacer disponible.")

    def copy_selected(self):
        ids=self.selected_ids()
        if not ids:return
        from copy import deepcopy
        self._copied_clips=[]
        for track in self.session.state["tracks"]:
            for clip in track["clips"]:
                if clip["id"] in ids:
                    self._copied_clips.append((
                        track["id"],track["type"],deepcopy(clip)))
        if self._copied_clips:
            self._copied_clip=(
                self._copied_clips[0][1],self._copied_clips[0][2])
        self.status.setText(
            f"{len(self._copied_clips)} clip(s) copiados. Pega en la guía.")

    def paste_clip(self):
        if not self._copied_clips or not self.project_key:return
        try:
            new=self.session.paste_many(
                self._copied_clips,self.playhead_beat)
        except (ValueError,KeyError,OSError) as error:
            self.status.setText("Pegar clips: "+str(error))
            return
        self._set_after_edit(new)
        self.status.setText(
            f"{len(new)} clips pegados en compás {self.playhead_beat/4+1:.2f}."
            " Deshacer disponible.")

    def cut_selected(self):
        ids=self.selected_ids()
        if not ids:return
        self.copy_selected()
        self.session.delete_clips(ids)
        self._set_after_edit([])
        self.status.setText(
            f"{len(ids)} clips cortados; Ctrl+V para pegarlos."
            " Deshacer disponible.")

    def duplicate_selected(self):
        ids=self.selected_ids()
        if not ids:return
        try:
            result=self.session.clone_clips(ids)
        except (ValueError,KeyError,OSError) as error:
            self.status.setText("Duplicar: "+str(error))
            return
        self._set_after_edit(result)

    def _set_after_edit(self,clip_ids):
        self.selected_clip_ids=set(clip_ids)
        self.selected_clip_id=clip_ids[0] if clip_ids else None
        self.refresh_timeline()

    def toggle_library(self):
        self.browser.setVisible(not self.browser.isVisible())

    def toggle_inspector(self):
        self.inspector.setVisible(not self.inspector.isVisible())

    def update_selected_track(self,**changes):
        track=self.selected_track()
        if track is None:return
        self.update_track(track["id"],**changes)

    def _refresh_mixer_selection(self):
        track=self.selected_track()
        if track is None:
            self.mixer_track_label.setText("Selecciona una pista para mezclar")
            for control in (self.mixer_mute,self.mixer_solo,
                            self.mixer_volume,self.mixer_pan):
                control.setEnabled(False)
            return
        self.mixer_track_label.setText(track["name"]+"  ·  "+
                                       track["type"].upper())
        for control in (self.mixer_mute,self.mixer_solo,
                        self.mixer_volume,self.mixer_pan):
            control.setEnabled(True)
        for control,value in ((self.mixer_mute,track["mute"]),
                              (self.mixer_solo,track["solo"]),
                              (self.mixer_volume,round(track["volume"]*100)),
                              (self.mixer_pan,round(track["pan"]*100))):
            with QSignalBlocker(control):
                (control.setChecked(value) if isinstance(control,QCheckBox)
                 else control.setValue(value))

    def _value(self,minimum,maximum,decimals):
        spin=QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum,maximum)
        spin.setSingleStep(.25 if minimum==0 else .1)
        spin.setMaximumWidth(110)
        return spin

    def sync_project(self):
        """Vincular al proyecto ACTIVO; no mostrar medios de otro proyecto."""
        root=getattr(self.main,"project_dir",None)
        target=str(Path(root).resolve()) if root else None
        if self.project_key!=target:
            if self.worker is not None and self.worker.isRunning():
                self.status.setText("Termina o cancela el render antes de cambiar proyecto.")
                return
            self.preview.stop()
            try:self.session.open_project(root)
            except (ValueError,OSError) as ex:
                self.status.setText("Compositor: "+str(ex))
                return
            self.project_key=target
            self.selected_clip_id=None
            self.selected_clip_ids.clear()
            self.meter_data={}
            # No pegar por error una pista de la canción anterior.
            self._copied_clip=None
            self._copied_clips=[]
            self._render_ready_signature=None
            self._render_requested_signature=None
            self.playhead_beat=0.
            self.project_title.setText(
                "Proyecto: "+Path(target).name if target else
                "Sin proyecto activo")
            with QSignalBlocker(self.tempo):
                self.tempo.setValue(self.session.state["bpm"])
            self._catalog_signature=None
            self.refresh_timeline()
        self.refresh_catalog()

    def refresh_catalog(self,force=False):
        root=getattr(self.main,"project_dir",None)
        if root and str(Path(root).resolve())!=self.project_key:
            self.sync_project()
            return
        if self.project_key is None:
            self.files.clear()
            return
        try:
            home=self.main.studio_home
            paths=[Path(p) for p in home._gather_files()
                   if Path(p).suffix.lower() in AUDIO|MIDI
                   and Path(p).is_file() and not Path(p).is_symlink()]
        except (RuntimeError,OSError):
            paths=[]
        filter_text=self.filter.text().strip().casefold()
        matches=sorted(set(paths),key=lambda p:(p.suffix.lower() in MIDI,
                        p.name.casefold(),str(p)))
        matches=[p for p in matches if filter_text in p.name.casefold()]
        key=(str(self.project_key),filter_text,
             tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns)
                   for p in matches))
        if key==self._catalog_signature and not force:return
        selected={self.files.item(i).data(Qt.UserRole)
                  for i in range(self.files.count())
                  if self.files.item(i).isSelected()}
        self._catalog_signature=key
        self.files.clear()
        for path in matches:
            item=QListWidgetItem(
                ("♫  " if path.suffix.lower() in MIDI else "▥  ")+path.name)
            item.setData(Qt.UserRole,str(path))
            item.setToolTip(str(path))
            self.files.addItem(item)
            if str(path) in selected:item.setSelected(True)
        self.status.setText(
            f"{len(matches)} archivos del proyecto disponibles · "
            f"{len(self.session.state['tracks'])} pistas en arreglo.")

    def selected_files(self):
        return [Path(item.data(Qt.UserRole))
                for item in self.files.selectedItems()]

    def selected_track(self):
        row=self.track_table.currentRow()
        tracks=self.session.state["tracks"]
        return tracks[row] if 0<=row<len(tracks) else None

    def _add(self,paths,to_existing=False):
        if not self.project_key:
            self.status.setText("Crea o abre primero un proyecto.")
            return
        chosen=self.selected_track() if to_existing else None
        errors=[]
        added=0
        for file in paths:
            try:
                match=chosen["id"] if chosen is not None else None
                t,c=self.session.add(file,track_id=match)
                added+=1
            except (ValueError,RuntimeError,OSError) as error:
                errors.append(f"{file.name}: {error}")
        self.refresh_timeline()
        self.refresh_catalog(True)
        self.status.setText(
            f"{added} archivo(s) añadidos al arreglo"
            +(f" · {errors[0]}" if errors else ""))

    def add_from_results(self):
        self._add(self.selected_files())

    def add_to_selected_track(self):
        self._add(self.selected_files(),to_existing=True)

    def import_media(self):
        if not self.project_key:return
        files,_=QFileDialog.getOpenFileNames(
            self,"Importar pistas de audio y MIDI",
            str(self.session.project),
            "Audio y MIDI (*.wav *.flac *.mp3 *.ogg *.m4a *.aif *.aiff"
            " *.opus *.mid *.midi *.kar)")
        self._add(files)

    def change_bpm(self,bpm):
        if not self.project_key:return
        if self.session.set_bpm(bpm):
            self.refresh_timeline(self.selected_clip_id)

    def change_zoom(self,pixels):
        self.pixels_per_beat=int(pixels)
        self.refresh_timeline(self.selected_clip_id)

    def snap_beat(self,beat):
        step=self.grid.currentData()
        if not step:return round(max(0.,float(beat)),4)
        return max(0.,round(float(beat)/step)*step)

    def set_playhead(self,beat):
        self.playhead_beat=self.snap_beat(beat)
        self.refresh_timeline(self.selected_clip_id)
        self.status.setText(
            f"Guía del Compositor: compás {self.playhead_beat/4+1:.2f}"
            " · Cortar en guía divide el clip seleccionado.")

    def rename_track(self,row,col):
        tracks=self.session.state["tracks"]
        if col!=0 or row<0 or row>=len(tracks):return
        track=tracks[row]
        name,accepted=QInputDialog.getText(
            self,"Renombrar pista", "Nombre de la pista:",text=track["name"])
        if accepted and name.strip():
            self.session.update_track(track["id"],name=name)
            self.refresh_timeline()

    def refresh_timeline(self,focus_id=None):
        if focus_id is not None:self.selected_clip_id=focus_id
        if self.selected_clip_id:
            try:self.session.clip(self.selected_clip_id)
            except KeyError:self.selected_clip_id=None
        tracks=self.session.state["tracks"]
        saved_track_ids=set(self.selected_track_ids())
        saved_ids=set(self.selected_clip_ids)
        if self.selected_clip_id:saved_ids.add(self.selected_clip_id)
        self.track_meters={}
        with QSignalBlocker(self.track_table):
            self.track_table.clearContents()
            self.track_table.setRowCount(len(tracks))
            for row,track in enumerate(tracks):
                label=QTableWidgetItem(track["name"])
                label.setToolTip(
                    "Doble clic: nombre editable en inspector de la pista")
                label.setData(Qt.UserRole,track["id"])
                label.setFlags(label.flags()&~Qt.ItemIsEditable)
                self.track_table.setItem(row,0,label)
                for col,key in ((1,"mute"),(2,"solo")):
                    box=QPushButton("M" if key=="mute" else "S")
                    box.setObjectName("composer"+key.title()+track["id"])
                    box.setCheckable(True)
                    box.setChecked(track[key])
                    box.setFixedSize(23,23)
                    box.setStyleSheet(
                        "QPushButton{padding:0;background:#192d40;"
                        "border:1px solid #587188;color:#dceaf4;}"
                        "QPushButton:hover{background:#255173;}"
                        "QPushButton:checked{background:"+
                        ("#9b522c" if key=="mute" else "#208363")+
                        ";color:white;border:1px solid #a4efed;}")
                    box.setToolTip(
                        ("Silenciar" if key=="mute" else "Reproducir solo")
                        +" esta pista")
                    box.toggled.connect(
                        lambda flag,k=key,id=track["id"]:
                        self.update_track(id,**{k:flag}))
                    self.track_table.setCellWidget(row,col,box)
                from compositor_meters import LevelMeter
                meter=LevelMeter(self.track_table)
                self.track_meters[track["id"]]=meter
                self.track_table.setCellWidget(row,5,meter)
                for col,key,top in ((3,"volume",200),(4,"pan",100)):
                    slider=QSlider(Qt.Horizontal)
                    slider.setRange(-100 if key=="pan" else 0,top)
                    slider.setValue(round(track[key]*100))
                    slider.setToolTip(
                        "Volumen 0–200 %" if key=="volume" else
                        "Panorama -100 izquierda a +100 derecha")
                    slider.sliderReleased.connect(
                        lambda w=slider,k=key,id=track["id"]:
                        self.update_track(id,**{k:w.value()/100}))
                    self.track_table.setCellWidget(row,col,slider)
            # Conservar la selección (también múltiple) entre refrescos
            # y al mover la guía; no cambiarla al reconstruir la tabla.
            from PySide6.QtCore import QItemSelectionModel
            selection=self.track_table.selectionModel()
            selection.clearSelection()
            for row,track in enumerate(tracks):
                if track["id"] in saved_track_ids:
                    selection.select(self.track_table.model().index(row,0),
                       QItemSelectionModel.Select|QItemSelectionModel.Rows)
            if not saved_track_ids and self.selected_clip_id:
                target=next((i for i,t in enumerate(tracks)
                    if any(c["id"]==self.selected_clip_id
                           for c in t["clips"])),-1)
                if target>=0:self.track_table.selectRow(target)
        self._rebuilding_scene=True
        self.scene.clear()
        beats=max(64,math.ceil((self.session.end_seconds()*
                  self.session.state["bpm"]/60+16)/4)*4)
        width=LEFT+beats*self.pixels_per_beat+70
        height=TOP+max(12,len(tracks))*ROW+2
        self.scene.setSceneRect(0,0,width,height)
        base_pen=QPen(QColor("#1b4168"),1)
        major_pen=QPen(QColor("#286aa0"),1)
        for beat in range(0,beats+1,4):
            x=LEFT+beat*self.pixels_per_beat
            self.scene.addLine(x,28,x,height,major_pen)
            t=self.scene.addText(str(beat//4+1))
            t.setDefaultTextColor(QColor("#a4dcfa"))
            t.setPos(x+3,0)
        for row in range(max(12,len(tracks))):
            track=tracks[row] if row<len(tracks) else None
            y=TOP+row*ROW
            self.scene.addRect(0,y,width,ROW-1,
                QPen(QColor("#124578")),
                QBrush(QColor("#092447" if row%2==0 else "#0a1b39")))
            if track is None:continue
            for clip in track["clips"]:
                tile=ClipTile(self,track,clip,row,self.pixels_per_beat)
                self.scene.addItem(tile)
                if clip["id"] in saved_ids:
                    tile.setSelected(True)
        # Línea de guía amarilla de reproducción/corte (compás relativo).
        x=LEFT+self.playhead_beat*self.pixels_per_beat
        self._guide_item=self.scene.addLine(
            x,25,x,height,QPen(QColor("#ffe77c"),2))
        self._guide_item.setZValue(5)
        self._rebuilding_scene=False
        self._selection_changed()
        self._read_clip_to_inspector()
        self._refresh_mixer_selection()
        self.position_label.setText(
            f"{int(self.playhead_beat//4)+1:03}."
            f"{int(self.playhead_beat%4)+1:02}."
            f"{int((self.playhead_beat%1)*100):02}")
        self.track_table.viewport().update()

    def select_clip(self,clip_id):
        self.selected_clip_id=clip_id
        self.selected_clip_ids={clip_id}
        self._rebuilding_scene=True
        for tile in self.scene.items():
            if isinstance(tile,ClipTile):
                tile.setSelected(tile.clip["id"]==clip_id)
        self._rebuilding_scene=False
        self._read_clip_to_inspector()
        try:
            track,_=self.session.clip(clip_id)
            row=self.session.state["tracks"].index(track)
            with QSignalBlocker(self.track_table):
                self.track_table.selectRow(row)
        except KeyError:pass
        self._refresh_mixer_selection()

    def _read_clip_to_inspector(self):
        try:track,clip=self.session.clip(self.selected_clip_id)
        except (KeyError,TypeError):
            self.clip_name.setText("Sin clip seleccionado")
            self.apply_clip.setEnabled(False)
            return
        self.apply_clip.setEnabled(True)
        self.clip_name.setText(clip["label"][:40])
        for w,value in ((self.clip_beat,clip["beat"]/4+1),
                        (self.clip_offset,clip["offset"]),
                        (self.clip_duration,clip["duration"]),
                        (self.clip_gain,clip.get("gain",1.)),
                        (self.clip_fade_in,clip.get("fade_in",0.)),
                        (self.clip_fade_out,clip.get("fade_out",0.))):
            with QSignalBlocker(w):w.setValue(value)

    def apply_clip_edit(self):
        if not self.selected_clip_id:return
        try:
            self.session.edit_clip(
                self.selected_clip_id,
                beat=(self.clip_beat.value()-1)*4,
                offset=self.clip_offset.value(),
                duration=self.clip_duration.value(),
                gain=self.clip_gain.value(),
                fade_in=self.clip_fade_in.value(),
                fade_out=self.clip_fade_out.value())
        except (KeyError,ValueError,OSError) as err:
            self.status.setText("Edición: "+str(err))
            return
        self.refresh_timeline(self.selected_clip_id)

    def split_selected(self):
        # Si hay selección múltiple, dividir sus clips simultáneamente.
        # Si solo hay pistas seleccionadas, dividir los clips que cruzan
        # la guía en TODAS esas pistas. Un único paso de Deshacer.
        ids=self.selected_ids()
        if not ids:
            tracks=set(self.selected_track_ids())
            ids=[clip["id"] for track in self.session.state["tracks"]
                 if track["id"] in tracks for clip in track["clips"]]
        if not ids:
            self.status.setText(
                "Selecciona clips o pistas para dividir en la guía.")
            return
        point=self.playhead_beat
        try:
            new=self.session.split_clips(ids,point)
        except (ValueError,KeyError) as error:
            self.status.setText("División: "+str(error))
            return
        if not new:
            self.status.setText(
                "La guía debe encontrarse dentro del clip, no al inicio o final.")
            return
        self._set_after_edit(new)
        self.status.setText(
            f"{len(new)} clip(s) divididos en compás {point/4+1:.2f}."
            " Deshacer disponible.")

    def delete_selected(self):
        ids=self.selected_ids()
        if not ids:return
        self.session.delete_clips(ids)
        self._set_after_edit([])
        self.status.setText(
            f"{len(ids)} clip(s) eliminados del arreglo; fuentes intactas."
            " Deshacer disponible.")

    def delete_track(self):
        ids=self.selected_track_ids()
        if not ids:return
        self.session.delete_tracks(ids)
        self._set_after_edit([])
        self.status.setText(
            f"{len(ids)} pistas eliminadas del arreglo. Deshacer disponible.")

    def move_track(self,delta):
        t=self.selected_track()
        if t is None:return
        self.session.move_track(t["id"],delta)
        self.refresh_timeline(self.selected_clip_id)

    def update_track(self,id,**changes):
        modified=self.session.update_track(id,**changes)
        if modified:
            # El audio pre-renderizado no puede reflejar controles cambiados
            # al vuelo. Detenerlo y exigir nuevo render es más fiable que
            # aparentar Mute/Volumen activos mientras sigue sonando lo viejo.
            self._invalidate_preview()
        self.refresh_timeline(self.selected_clip_id)

    def _invalidate_preview(self):
        if not hasattr(self,"preview"):return
        if (self.preview._qt_active or self.preview._play_process is not None):
            self.preview.stop()
            self._update_meters(None)
            self.status.setText(
                "Mezcla modificada. Pulsa Escuchar para aplicar los cambios.")
        self._render_ready_signature=None

    def _select_row_related_clip(self):
        selected=self.selected_track()
        if selected is None:return
        # Seleccionar una PISTA no equivale a seleccionar su primer clip.
        # Así, «Dividir pista» trabaja con todos los clips que atraviesan
        # la guía, sin limitarse automáticamente al primero.
        if (self.selected_clip_id is not None and not any(
                c["id"]==self.selected_clip_id
                for c in selected["clips"])):
            self._rebuilding_scene=True
            for tile in self.scene.items():
                if isinstance(tile,ClipTile):tile.setSelected(False)
            self._rebuilding_scene=False
            self.selected_clip_ids.clear()
            self.selected_clip_id=None
            self._read_clip_to_inspector()
        self._refresh_mixer_selection()

    def open_clip_midi(self):
        if not self.selected_clip_id:return
        track,clip=self.session.clip(self.selected_clip_id)
        if track["type"]!="midi":
            self.status.setText("Este clip es audio; edítalo en Vista de audio.")
            return
        self.main.workbench.show_piano_roll(self.session.file_for(clip))
        self.status.setText(
            "MIDI abierto en Piano Roll. Exporta una nueva versión desde "
            "allí y añádela al Compositor cuando esté lista.")

    def undo(self):
        if self.session.undo():self.refresh_timeline(self.selected_clip_id)

    def redo(self):
        if self.session.redo():self.refresh_timeline(self.selected_clip_id)

    def save(self):
        if self.project_key:
            self.session._save()
            self.status.setText("Arreglo guardado en compositor/arreglo.json")

    def _session_signature(self):
        return hashlib.sha256(json.dumps(
            self.session.state,sort_keys=True,
            ensure_ascii=False).encode("utf8")).hexdigest()

    def _update_meters(self,position):
        from compositor_meters import levels_at
        if position is None:
            zero=(0.,0.,0.,0.)
            if hasattr(self,"master_meter"):
                self.master_meter.setLevels(zero)
            for widget in self.track_meters.values():
                widget.setLevels(zero)
            return
        if hasattr(self,"master_meter"):
            self.master_meter.setLevels(
                levels_at(self.meter_data.get("__master__",()),position))
        for track_id,widget in self.track_meters.items():
            widget.setLevels(
                levels_at(self.meter_data.get(track_id,()),position))

    def toggle_playback(self):
        """Space: tocar, pausar o recomponer solo si se editó el arreglo."""
        if not self.project_key:return
        if self.worker is not None and self.worker.isRunning():return
        preview_file=self.preview.current_file
        if (preview_file and Path(preview_file).is_file() and
                self._render_ready_signature==self._session_signature()):
            self.preview.play_pause()
        else:self.start_render(True)

    def _follow_playback(self):
        """La guía visible sigue la posición REAL del motor de escucha."""
        if not self.project_key or self.preview is None:return
        active=self.preview._qt_active or self.preview._play_process is not None
        if not active or self.preview._paused:
            self._update_meters(None)
            return
        position=max(0,self.preview._position())/1000.
        self._update_meters(position)
        beat=position*self.session.state["bpm"]/60.
        if abs(beat-self.playhead_beat)<.025:return
        self.playhead_beat=beat
        if hasattr(self,"_guide_item"):
            x=LEFT+beat*self.pixels_per_beat
            self._guide_item.setLine(x,25,x,self.scene.sceneRect().height())
        if hasattr(self,"position_label"):
            self.position_label.setText(
                f"{int(beat//4)+1:03}.{int(beat%4)+1:02}."
                f"{int((beat%1)*100):02}")

    def stop_play(self):
        self.preview.stop()
        self._update_meters(None)
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("Cancelación solicitada.")

    def start_render(self,preview):
        if not self.project_key:return
        if self.worker is not None and self.worker.isRunning():
            self.status.setText("Ya se está renderizando un arreglo.")
            return
        if not any(t["clips"] for t in self.session.audible()):
            self.status.setText("No hay clips audibles.")
            return
        self.preview.stop()
        self._update_meters(None)
        if preview:
            out=self.session.folder/"cache"/"preescucha_compositor.wav"
        else:
            from datetime import datetime
            name=("Compositor_"+
                  datetime.now().strftime("%Y%m%d_%H%M%S_%f")+".wav")
            root=self.session.project/"resultados"
            from task_staging import unique_dest
            out=unique_dest(root,name)
        self._render_requested_signature=self._session_signature()
        meter_file=(
            self.session.folder/"cache"/"vumetros_compositor.json"
            if preview else None)
        self.worker=MixWorker(
            self.session,out,preview,parent=self,meter_file=meter_file)
        self.worker.finished_mix.connect(self._render_done)
        self.progress.setRange(0,0)
        self.status.setText("Renderizando pistas y MIDI con FluidSynth / FFmpeg…")
        self.worker.start()

    def _render_done(self,path,preview,error):
        self.progress.setRange(0,1)
        self.progress.setValue(0 if error else 1)
        if error:
            self.status.setText("Render: "+error[:180])
            return
        self.status.setText("Mezcla "+("preparada para escucha." if preview
                            else "exportada a Resultados: "+Path(path).name))
        if preview:
            # Bus de audio real por pista y salida master pos-limitador.
            meter_file=self.session.folder/"cache"/"vumetros_compositor.json"
            try:
                data=json.loads(meter_file.read_text(encoding="utf8"))
                self.meter_data=(
                    data["tracks"] if data.get("version")==1 else {})
            except (OSError,ValueError,KeyError,TypeError):
                self.meter_data={}
            self._render_ready_signature=self._render_requested_signature
            self.preview.load(path,autoplay=True)
        else:
            self.main.studio_home.refresh(force=True)
            self.refresh_catalog(True)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"track_table"):
            compact=self.width()<1270
            self.track_table.setColumnHidden(3,compact)
            self.track_table.setColumnHidden(4,self.width()<1550)
            self.track_table.setColumnHidden(5,False)
            # En tamaños estrechos el fader y el panorama siguen en la
            # pestaña inferior «Mezclador»: no desaparecen funciones.
            if compact and hasattr(self,"mixer_track_label"):
                self.mixer_track_label.setToolTip(
                    "Volumen y panorama disponibles en Mezclador")

    def closeEvent(self,event):
        self.stop_play()
        if self.worker is not None and self.worker.isRunning():
            if not self.worker.wait(4500):
                self.status.setText(
                    "Terminando proceso de audio; repite el cierre.")
                event.ignore()
                return
        self._preview_timer.stop()
        self._transport_timer.stop()
        self._preview_pool.shutdown(wait=False,cancel_futures=True)
        super().closeEvent(event)
