#!/usr/bin/env python3
"""Editor MIDI en piano roll no destructivo, con edición por pistas.

El archivo original permanece intacto. Conserva eventos MIDI no musicales
(tempo, controles, cambios de programa, letras, etc.) al guardar un derivado.
"""
from __future__ import annotations
import file_dialogs

import copy
import math
from datetime import datetime
from pathlib import Path

import mido
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QColor, QBrush, QPen, QPainter, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGraphicsItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QScrollArea,
    QSlider, QSpinBox, QDoubleSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)
from preview_player import PreviewPlayer
from ux_controls import SliderNumber, PresetStrip, PRESET_DIR
import json


LOW, HIGH = 21, 108
KEY_WIDTH = 108
RULER = 28
ROW_HEIGHT = 23
BEAT_WIDTH = 96
GRID_COLORS = ("#12212f", "#1a2b39")
NOTE_COLOR = QColor("#39b9b4")
SELECT_COLOR = QColor("#eeb857")


def note_name(pitch):
    notes = ("Do", "Do♯", "Re", "Re♯", "Mi", "Fa",
             "Fa♯", "Sol", "Sol♯", "La", "La♯", "Si")
    return f"{notes[pitch%12]}{pitch//12-1}"


def parse_file(path):
    midi = mido.MidiFile(str(path))
    if midi.type not in (0, 1):
        raise ValueError("El editor admite MIDI de tipo 0 y 1. No admite MIDI tipo 2.")
    tracks = []
    for index, source in enumerate(midi.tracks):
        abs_tick = 0
        pending = {}
        notes = []
        other = []
        channels = set()
        program = 0
        for msg in source:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                channels.add(msg.channel)
                pending.setdefault((msg.channel, msg.note), []).append(
                    (abs_tick, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                channels.add(msg.channel)
                stack = pending.get((msg.channel, msg.note), [])
                if stack:
                    start, velocity = stack.pop(0)
                    notes.append({"start":start, "end":max(abs_tick,start+1),
                                  "pitch":msg.note, "velocity":velocity,
                                  "channel":msg.channel})
                else:
                    other.append((abs_tick, msg.copy(time=0)))
            elif msg.type == "end_of_track":
                continue
            else:
                if hasattr(msg,"channel"):
                    channels.add(msg.channel)
                if msg.type=="program_change":
                    program=msg.program
                other.append((abs_tick,msg.copy(time=0)))
        for (channel,pitch), stack in pending.items():
            for start,velocity in stack:
                notes.append({"start":start,"end":start+midi.ticks_per_beat,
                              "pitch":pitch,"velocity":velocity,"channel":channel})
        notes.sort(key=lambda n:(n["start"],n["pitch"],n["end"]))
        name = source.name or f"Pista {index+1}"
        tracks.append({"name":name,"notes":notes,"other":other,
                       "channels":sorted(channels),"program":program})
    return midi,tracks


def export_file(midi,tracks,destination):
    """Escribe una copia MIDI tipo 1 sin perder los eventos ajenos a notas."""
    out=mido.MidiFile(type=1, ticks_per_beat=midi.ticks_per_beat)
    for tr in tracks:
        events=[]
        for tick,msg in tr["other"]:
            # Se copian y ordenan, no se modifica el MIDI en memoria original.
            events.append((max(0,int(tick)), 1, msg.copy(time=0)))
        for n in tr["notes"]:
            ch=max(0,min(15,int(n["channel"])))
            pitch=max(0,min(127,int(n["pitch"])))
            vel=max(1,min(127,int(n["velocity"])))
            begin=max(0,round(n["start"]))
            end=max(begin+1,round(n["end"]))
            events.append((begin,2,mido.Message("note_on",channel=ch,note=pitch,velocity=vel,time=0)))
            events.append((end,0,mido.Message("note_off",channel=ch,note=pitch,velocity=0,time=0)))
        events.sort(key=lambda e:(e[0],e[1]))
        result=mido.MidiTrack()
        prev=0
        for tick,priority,msg in events:
            result.append(msg.copy(time=max(0,tick-prev)))
            prev=tick
        result.append(mido.MetaMessage("end_of_track", time=0))
        out.tracks.append(result)
    out.save(str(destination))
    return destination


class TimelineSlider(QSlider):
    """Permite situar el cursor con clic o arrastre, no solo con el tirador."""
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.width()>1:
            ratio=max(0.,min(1.,event.position().x()/self.width()))
            self.setValue(round(self.minimum()+ratio*(self.maximum()-self.minimum())))
            self.sliderMoved.emit(self.value())
            self.sliderPressed.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton and self.width()>1:
            ratio=max(0.,min(1.,event.position().x()/self.width()))
            self.setValue(round(self.minimum()+ratio*(self.maximum()-self.minimum())))
            self.sliderMoved.emit(self.value())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class NoteBox(QGraphicsRectItem):
    """Nota del piano roll: arrastrar mueve, borde derecho ajusta duración."""
    def __init__(self,editor,index,rect,color):
        super().__init__(rect)
        self.editor=editor
        self.index=index
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#193843"),.45 if rect.width()<4 else 1))
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemIsSelectable,True)
        self.setAcceptHoverEvents(True)
        self._action=None
        self._point=None
        self._start=None
        self._original=None
        self._changed=False

    def hoverMoveEvent(self,event):
        near_right=(self.rect().width()>=18 and
                    event.pos().x()>self.rect().right()-min(12,self.rect().width()*.24))
        self.setCursor(Qt.SizeHorCursor if near_right else Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            additive=bool(event.modifiers() & (Qt.ControlModifier|Qt.ShiftModifier))
            # Arrastrar una nota ya incluida en un grupo conserva TODA
            # la selección. Antes un clic normal deseleccionaba las demás.
            if additive:
                self.editor.select_note(self.index,additive=True)
            elif self.index not in self.editor.selected_indices:
                self.editor.select_note(self.index)
            if additive:
                event.accept()
                return
            self._action=("resize" if self.rect().width()>=18 and
                          event.pos().x()>self.rect().right()-
                              min(12,self.rect().width()*.24) else "move")
            self._point=event.scenePos()
            self._original=copy.deepcopy(self.editor.current_notes[self.index])
            self._base={
                i:copy.deepcopy(self.editor.current_notes[i])
                for i in self.editor.selected_indices
            }
            self._changed=False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if not self._point or not self._action:
            super().mouseMoveEvent(event)
            return
        delta=event.scenePos()-self._point
        ticks=self.editor.delta_to_ticks(delta.x())
        if self._action=="resize":
            new_end=max(self._original["start"]+1,
                  self.editor.snap_tick(self._original["end"]+ticks))
            self.setRect(QRectF(self.editor.tick_x(self._original["start"]),
                self.rect().y(),max(1,self.editor.delta_x(new_end-self._original["start"])),
                self.editor.note_height()))
        else:
            shift_tick=self.editor.snap_tick(self._original["start"]+ticks)-self._original["start"]
            shift_pitch=-round(delta.y()/self.editor.row_px)
            baselines=list(self._base.values())
            shift_tick=max(-min(n["start"] for n in baselines),shift_tick)
            shift_pitch=max(LOW-min(n["pitch"] for n in baselines),
                            min(HIGH-max(n["pitch"] for n in baselines),shift_pitch))
            for item in self.editor.scene.items():
                if isinstance(item,NoteBox) and item.index in self._base:
                    note=self._base[item.index]
                    item.setRect(QRectF(
                        self.editor.tick_x(note["start"]+shift_tick),
                        self.editor.pitch_y(note["pitch"]+shift_pitch)+self.editor.note_offset(),
                        max(2.5,self.editor.delta_x(note["end"]-note["start"])),
                        self.editor.note_height()))
        self._changed=True
        event.accept()

    def mouseReleaseEvent(self,event):
        if self._action and self._original and self._changed:
            if self._action=="resize":
                note=copy.deepcopy(self._original)
                note["end"]=max(note["start"]+1,
                            self.editor.snap_tick(self.editor.x_to_tick(self.rect().right())))
                if note!=self._original:
                    self.editor.modify_note(self.index,note)
                else:self.editor.redraw()
            else:
                delta=event.scenePos()-self._point
                ticks=self.editor.delta_to_ticks(delta.x())
                shift_tick=self.editor.snap_tick(self._original["start"]+ticks)-self._original["start"]
                shift_pitch=-round(delta.y()/self.editor.row_px)
                self.editor.move_notes(self._base,shift_tick,shift_pitch)
        self._action=None
        self._original=None
        self._point=None
        self._base={}
        event.accept()


class RollView(QGraphicsView):
    def __init__(self,editor):
        super().__init__()
        self.editor=editor
        self.setRenderHint(QPainter.Antialiasing,True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setMouseTracking(True)
        self._pan_start=None
        self._scrub_active=False
        self.setDragMode(QGraphicsView.RubberBandDrag)

    def wheelEvent(self,event):
        if event.modifiers() & Qt.AltModifier:
            change=22 if event.angleDelta().y()>0 else -22
            self.editor.zoom_vertical.setValue(max(
                self.editor.zoom_vertical.minimum(),min(
                    self.editor.zoom_vertical.maximum(),
                    self.editor.zoom_vertical.value()+change)))
            event.accept()
        elif event.modifiers() & Qt.ControlModifier:
            change=22 if event.angleDelta().y()>0 else -22
            self.editor.zoom.setValue(max(self.editor.zoom.minimum(),
                    min(self.editor.zoom.maximum(),
                        self.editor.zoom.value()+change)))
            event.accept()
        elif event.modifiers() & Qt.ShiftModifier:
            scroll=self.horizontalScrollBar()
            scroll.setValue(scroll.value()-int(event.angleDelta().y()*.8))
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseMoveEvent(self,event):
        if self._scrub_active:
            self.editor.seek_tick(self.editor.x_to_tick(self.mapToScene(event.pos()).x()))
            event.accept()
            return
        if self._pan_start is not None:
            diff=event.pos()-self._pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-diff.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-diff.y())
            self._pan_start=event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self._scrub_active:
            self._scrub_active=False
            self.editor.seek_tick(self.editor.x_to_tick(self.mapToScene(event.pos()).x()))
            event.accept()
            return
        if event.button()==Qt.MiddleButton and self._pan_start is not None:
            self._pan_start=None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawForeground(self,painter,rect):
        """Teclado y regla fijos respecto al área visible con scroll."""
        super().drawForeground(painter,rect)
        editor=self.editor
        bounds=self.mapToScene(self.viewport().rect()).boundingRect()
        left=bounds.left()
        top=bounds.top()
        painter.save()
        for pitch in range(LOW,HIGH+1):
            y=editor.pitch_y(pitch)
            if y+editor.row_px<bounds.top() or y>bounds.bottom():continue
            black=pitch%12 in (1,3,6,8,10)
            painter.setPen(QPen(QColor("#081623"),1.2))
            painter.setBrush(QBrush(QColor("#061929")))
            painter.drawRect(QRectF(left,y,KEY_WIDTH-1,editor.row_px))
            painter.setBrush(QBrush(QColor("#162e40" if black else "#e4eef3")))
            width=KEY_WIDTH-33 if black else KEY_WIDTH-4
            offset=min(1.0,editor.row_px*.15)
            painter.drawRoundedRect(
                QRectF(left+1,y+offset,width,max(.35,editor.row_px-2*offset)),
                min(2.,editor.row_px*.16),min(2.,editor.row_px*.16))
            painter.setPen(QPen(QColor("#416077" if black else "#ffffff"),1))
            if editor.row_px>=7:
                painter.drawLine(QPointF(left+4,y+2),QPointF(left+width-4,y+2))
            if editor.row_px>=15 and pitch%12 in (0,5,9):
                painter.setPen(QColor("#aed4ed" if black else "#233747"))
                painter.drawText(QRectF(left+10,y+2,width-14,editor.row_px-4),
                                 Qt.AlignLeft|Qt.AlignVCenter,note_name(pitch))
        ruler_y=max(0,top)
        painter.setPen(QPen(QColor("#465e72"),1))
        painter.setBrush(QBrush(QColor("#263b4a")))
        painter.drawRect(QRectF(left+KEY_WIDTH-1,ruler_y,
                                bounds.width()-KEY_WIDTH,RULER))
        start=max(0,int(editor.x_to_tick(left+KEY_WIDTH)//editor.ticks_per_beat))
        finish=int(editor.x_to_tick(bounds.right())//editor.ticks_per_beat)+2
        step=editor.grid_beat_step(max(0,finish-start),minimum_px=14)
        label_step=step
        while editor.beat_px*label_step<55:
            label_step*=2
        label_step=max(4,label_step)
        for beat in range((start//step)*step,finish,step):
            x=editor.tick_x(beat*editor.ticks_per_beat)
            painter.setPen(QPen(QColor("#8ea8b8"),1))
            painter.drawLine(x,ruler_y+RULER-7,x,ruler_y+RULER)
            if beat%label_step==0:
                painter.setPen(QColor("#ebf4f7"))
                painter.drawText(QRectF(x+3,ruler_y+2,45,16),str(beat//4+1))
        if editor._playhead:
            cursorx=editor._playhead.line().x1()
            painter.setPen(QPen(QColor("#ffc95a"),2))
            painter.drawLine(cursorx,ruler_y,cursorx,ruler_y+RULER)
        painter.restore()

    def mouseDoubleClickEvent(self,event):
        pos=self.mapToScene(event.pos())
        if event.button()==Qt.LeftButton and pos.x()>=KEY_WIDTH and pos.y()>=RULER:
            note=self.editor.note_from_point(pos)
            self.editor.add_note(note)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MiddleButton:
            self._pan_start=event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        pos=self.mapToScene(event.pos())
        visible=self.mapToScene(self.viewport().rect()).boundingRect()
        if (event.button()==Qt.LeftButton
                and pos.y()<max(0,visible.top())+RULER
                and pos.x()>=visible.left()+KEY_WIDTH):
            self._scrub_active=True
            self.editor.seek_tick(self.editor.x_to_tick(pos.x()))
            event.accept()
            return
        if (event.button()==Qt.LeftButton and self.editor.tool_mode=="pencil"
            and pos.x()>=KEY_WIDTH and pos.y()>=RULER):
            hit=self.scene().itemAt(pos,self.transform())
            if not isinstance(hit,NoteBox):
                self.editor.add_note(self.editor.note_from_point(pos))
                event.accept()
                return
        if event.button()==Qt.RightButton or (
                event.button()==Qt.LeftButton and self.editor.tool_mode=="erase"):
            pos=self.mapToScene(event.pos())
            hit=self.scene().itemAt(pos,self.transform())
            if isinstance(hit,NoteBox):
                self.editor.delete_note(hit.index)
                event.accept()
                return
        super().mousePressEvent(event)


class PianoRollDialog(QDialog):
    def __init__(self,file_path=None,parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editor MIDI · Piano Roll")
        self.resize(1510,940)
        self.setMinimumSize(990,650)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.midi=None
        self.tracks=[]
        self.current_path=None
        self.track_index=0
        self.selected_index=None
        self.selected_indices=set()
        self.tool_mode="select"
        self._syncing_selection=False
        self._scrubbing_time=False
        self._manual_stop=False
        self.history=[]
        self.future=[]
        self.dirty=False
        self.beat_px=float(BEAT_WIDTH)
        self.row_px=float(ROW_HEIGHT)
        self.quant_ticks=120
        self._scroll_restore=None
        self._playhead=None
        self._pending_seek_ms=None
        self._cursor_timer=QTimer(self)
        self._cursor_timer.setInterval(80)
        self._cursor_timer.timeout.connect(self.update_playhead)
        self.create_ui()
        self._cursor_timer.start()
        self.load_view_settings()
        if file_path:
            self.open_midi(file_path)

    @property
    def current_notes(self):
        return self.tracks[self.track_index]["notes"] if self.tracks else []

    @property
    def ticks_per_beat(self):
        return self.midi.ticks_per_beat if self.midi else 480

    def tick_x(self,tick):
        return KEY_WIDTH+tick*self.beat_px/self.ticks_per_beat

    def delta_x(self,ticks):
        return ticks*self.beat_px/self.ticks_per_beat

    def x_to_tick(self,x):
        return max(0,round((x-KEY_WIDTH)*self.ticks_per_beat/self.beat_px))

    def delta_to_ticks(self,x):
        return round(x*self.ticks_per_beat/self.beat_px)

    def pitch_y(self,pitch):
        return RULER+(HIGH-pitch)*self.row_px

    def y_to_pitch(self,y):
        return max(LOW,min(HIGH,HIGH-math.floor((y-RULER)/self.row_px)))

    @staticmethod
    def _to_slider(value,low,high,steps=1200):
        # Escala logarítmica: de grandes partituras a edición por nota.
        value=max(low,min(high,float(value)))
        return round(steps*math.log(value/low)/math.log(high/low))

    @staticmethod
    def _from_slider(value,low,high,steps=1200):
        return low*(high/low)**(int(value)/steps)

    def note_height(self):
        return max(.35,self.row_px-min(2.,self.row_px*.22))

    def note_offset(self):
        return min(1.,self.row_px*.11)

    def grid_beat_step(self,beats,minimum_px=16):
        # Impedir cientos de miles de QGraphicsItems en MIDI muy largos.
        step=1
        while (step*self.beat_px<minimum_px or beats/step>550):
            step*=2
        return step

    def snap_tick(self,tick):
        return max(0,round(round(tick/self.quant_ticks)*self.quant_ticks)) if self.quant_ticks else max(0,round(tick))

    def note_from_point(self,pos):
        pitch=self.y_to_pitch(pos.y())
        start=self.snap_tick(self.x_to_tick(pos.x()))
        return {"pitch":pitch,"start":start,"end":start+(self.quant_ticks or self.ticks_per_beat),
                "velocity":self.velocity.value(),"channel":self.default_channel()}

    def default_channel(self):
        if not self.tracks:
            return 0
        tr=self.tracks[self.track_index]
        return tr["channels"][0] if tr["channels"] else (9 if "drum" in tr["name"].lower() else 0)

    def create_ui(self):
        from PySide6.QtWidgets import QLayout
        shell=QVBoxLayout(self)
        shell.setContentsMargins(0,0,0,0)
        self.page_scroll=QScrollArea(self)
        self.page_scroll.setObjectName("pianoRollPageScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.NoFrame)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_page=QWidget(self.page_scroll)
        root=QVBoxLayout(self.content_page)
        self.content_layout=root
        root.setSizeConstraint(QLayout.SetMinimumSize)
        root.setContentsMargins(10,7,10,7)
        root.setSpacing(5)
        self.page_scroll.setWidget(self.content_page)
        shell.addWidget(self.page_scroll)
        heading=QHBoxLayout()
        title=QLabel("PIANO ROLL · EDITOR MIDI")
        title.setObjectName("title")
        heading.addWidget(title)
        heading.addStretch()
        self.file_label=QLabel("Sin archivo MIDI")
        self.file_label.setObjectName("muted")
        source_row=QHBoxLayout()
        source_row.addWidget(QLabel("MIDI"))
        self.midi_choice=QComboBox(self)
        self.midi_choice.setMinimumWidth(220)
        self.midi_choice.setToolTip("Elige una toma MIDI temporal o un MIDI guardado de la biblioteca.")
        self.midi_choice.activated.connect(self.select_midi_choice)
        self.midi_choice.setMinimumWidth(0)
        source_row.addWidget(self.midi_choice)
        self.reload_midis=QPushButton("Actualizar lista")
        self.reload_midis.clicked.connect(self.refresh_midi_list)
        source_row.addWidget(self.reload_midis)
        source_row.addSpacing(10)
        source_row.addWidget(self.file_label)
        source_row.addStretch(1)
        heading.addLayout(source_row)
        root.addLayout(heading)
        transport=QHBoxLayout()
        transport.setSpacing(5)
        def tbutton(label,tip,func,primary=False):
            btn=QPushButton(label)
            btn.setToolTip(tip)
            if primary:btn.setObjectName("primary")
            btn.clicked.connect(func)
            btn.setMinimumWidth(43)
            btn.setStyleSheet(
                "QPushButton{font-size:14px;min-height:27px;padding:3px 9px;}"
                "QPushButton:hover{border:1px solid #70e6ff;}")
            transport.addWidget(btn)
            return btn
        self.to_start=tbutton("|◀","Ir al principio (Inicio)",
                              lambda:self.seek_tick(0))
        self.rewind=tbutton("◀◀","Retroceder una negra",
                           lambda:self.step_transport(-1))
        self.play_roll=tbutton("▶ Play","Reproducir o reanudar (Espacio)",
                               self.preview_play,True)
        self.pause_roll=tbutton("Ⅱ","Pausar / continuar",self.pause_toggle)
        self.stop_roll=tbutton("■","Detener y volver a cero",self.preview_stop)
        self.forward=tbutton("▶▶","Avanzar una negra",
                            lambda:self.step_transport(1))
        self.to_end=tbutton("▶|","Ir al final",
                           lambda:self.seek_tick(self.last_tick()))
        self.loop_toggle=QCheckBox("↻ Bucle")
        self.loop_toggle.setToolTip("Repetir reproducción al final del MIDI")
        transport.addWidget(self.loop_toggle)
        self.follow_cursor=QCheckBox("Seguir cursor")
        self.follow_cursor.setChecked(True)
        transport.addWidget(self.follow_cursor)
        transport.addStretch()
        self.position_label=QLabel("00:00 / 00:00")
        self.position_label.setObjectName("status")
        transport.addWidget(self.position_label)
        from ui_responsive import horizontal_controls
        root.addWidget(horizontal_controls(transport,self))
        timeline=QHBoxLayout()
        timeline.addWidget(QLabel("POSICIÓN"))
        self.timeline=TimelineSlider(Qt.Horizontal)
        self.timeline.setRange(0,10000)
        self.timeline.setToolTip("Clic o arrastra para situar el cursor de reproducción.")
        self.timeline.sliderMoved.connect(self.scrub_timeline)
        self.timeline.sliderPressed.connect(self.begin_scrub)
        self.timeline.sliderReleased.connect(self.finish_scrub)
        timeline.addWidget(self.timeline,1)
        self.bar_position=QLabel("1 : 1")
        self.bar_position.setMinimumWidth(66)
        timeline.addWidget(self.bar_position)
        root.addLayout(timeline)
        self.fit_roll=QPushButton("⤢ Encajar pista completa")
        self.fit_roll.setToolTip("Ajustar ambos zooms a todas las notas del MIDI")
        self.fit_roll.clicked.connect(self.fit_notes)

        controls=QHBoxLayout()
        open_btn=QPushButton("Abrir MIDI…")
        open_btn.clicked.connect(self.choose_file)
        controls.addWidget(open_btn)
        self.save_button=QPushButton("Guardar MIDI editado…")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_as)
        controls.addWidget(self.save_button)
        self.undo_btn=QPushButton("Deshacer")
        self.undo_btn.clicked.connect(self.undo)
        controls.addWidget(self.undo_btn)
        self.redo_btn=QPushButton("Rehacer")
        self.redo_btn.clicked.connect(self.redo)
        controls.addWidget(self.redo_btn)
        controls.addStretch()
        controls.addWidget(QLabel("Cuantización"))
        self.grid=QComboBox()
        for label,div in (("Sin ajuste",0),("1/4",1),("1/8",2),("1/16",4),
                          ("1/32",8),("1/64",16)):
            self.grid.addItem(label,div)
        self.grid.setCurrentIndex(3)
        self.grid.currentIndexChanged.connect(self.on_grid_changed)
        controls.addWidget(self.grid)
        controls.addSpacing(10)
        controls.addWidget(QLabel("Herramienta"))
        self.tool=QComboBox()
        self.tool.addItem("▧ Seleccionar / marco","select")
        self.tool.addItem("✎ Dibujar nota","pencil")
        self.tool.addItem("⌫ Borrar nota","erase")
        self.tool.setToolTip("Selección individual, múltiple o dibujo con un clic")
        self.tool.currentIndexChanged.connect(self.change_tool)
        controls.addWidget(self.tool)
        self.select_all_btn=QPushButton("Seleccionar todo")
        self.select_all_btn.clicked.connect(self.select_all_notes)
        controls.addWidget(self.select_all_btn)
        zoom_row=QHBoxLayout()
        zoom_row.setSpacing(7)
        zoom_row.addWidget(QLabel("Zoom horizontal"))
        self.zoom=QSlider(Qt.Horizontal)
        self.zoom.setRange(0,1200)
        self.zoom.setMaximumWidth(110)
        self.zoom.setToolTip("Zoom horizontal · Ctrl+rueda. Rango desde "
                             "0,000001 hasta 300 píxeles por negra.")
        self.zoom.setValue(self._to_slider(BEAT_WIDTH, .000001,300.))
        self.zoom.valueChanged.connect(self.on_zoom)
        zoom_row.addWidget(self.zoom)
        self.zoom_digit=QDoubleSpinBox(self)
        self.zoom_digit.setRange(.000001,300.)
        self.zoom_digit.setDecimals(6)
        self.zoom_digit.setSingleStep(2)
        self.zoom_digit.setSuffix(" px")
        self.zoom_digit.setMinimumWidth(125)
        self.zoom_digit.setMaximumWidth(136)
        self.zoom_digit.setValue(BEAT_WIDTH)
        self.zoom_digit.setToolTip("Píxeles por negra. Se admiten valores "
                "muy pequeños para visualizar pistas largas enteras.")
        self.zoom_digit.valueChanged.connect(self.set_beat_zoom)
        zoom_row.addWidget(self.zoom_digit)
        zoom_row.addSpacing(10)
        zoom_row.addWidget(QLabel("Zoom vertical"))
        self.zoom_vertical=QSlider(Qt.Horizontal)
        self.zoom_vertical.setRange(0,1000)
        self.zoom_vertical.setMaximumWidth(110)
        self.zoom_vertical.setToolTip("Zoom vertical · Alt+rueda: altura de cada semitono.")
        self.zoom_vertical.setValue(self._to_slider(ROW_HEIGHT,.5,48.,1000))
        self.zoom_vertical.valueChanged.connect(self.on_vertical_zoom)
        zoom_row.addWidget(self.zoom_vertical)
        self.zoom_vertical_digit=QDoubleSpinBox(self)
        self.zoom_vertical_digit.setRange(.5,48.)
        self.zoom_vertical_digit.setDecimals(2)
        self.zoom_vertical_digit.setSingleStep(1)
        self.zoom_vertical_digit.setSuffix(" px")
        self.zoom_vertical_digit.setMinimumWidth(88)
        self.zoom_vertical_digit.setMaximumWidth(102)
        self.zoom_vertical_digit.setValue(ROW_HEIGHT)
        self.zoom_vertical_digit.valueChanged.connect(self.set_row_zoom)
        zoom_row.addWidget(self.zoom_vertical_digit)
        zoom_row.addSpacing(10)
        transport.removeWidget(self.fit_roll)
        zoom_row.addWidget(self.fit_roll)
        zoom_row.addStretch(1)
        root.addWidget(horizontal_controls(controls,self))
        root.addWidget(horizontal_controls(zoom_row,self))
        self.roll_presets=PresetStrip("piano_roll_vista",{
            "Edición detallada":{"zoom":180,"zoom_vertical":29,"quant":8,"tempo_mode":"keep_time"},
            "Edición clásica":{"zoom":96,"zoom_vertical":23,"quant":4,"tempo_mode":"keep_time"},
            "Vista general":{"zoom":50,"zoom_vertical":10,"quant":2,"tempo_mode":"keep_time"},
            "Edición libre":{"zoom":115,"zoom_vertical":18,"quant":0,"tempo_mode":"keep_time"},
        },self.view_snapshot,self.apply_view_preset,self)
        self.roll_presets.setVisible(False)
        self.roll_presets.setMaximumHeight(45)
        self.view_presets_toggle=QPushButton("Presets de vista ▾")
        self.view_presets_toggle.clicked.connect(self.toggle_view_presets)
        transport.addWidget(self.view_presets_toggle)
        root.addWidget(self.roll_presets)

        tempo_bar=QHBoxLayout()
        tempo_bar.addWidget(QLabel("TEMPO MIDI"))
        self.tempo_bpm=SliderNumber(35,300,120,.1,2," BPM")
        self.tempo_bpm.setValue(120)
        tempo_bar.addWidget(self.tempo_bpm)
        tempo_bar.addWidget(QLabel("Aplicar como"))
        self.tempo_mode=QComboBox()
        self.tempo_mode.addItem("Corregir rejilla sin alterar los segundos", "keep_time")
        self.tempo_mode.addItem("Cambiar la velocidad de reproducción", "change_speed")
        self.tempo_mode.setMinimumWidth(220)
        tempo_bar.addWidget(self.tempo_mode)
        self.tempo_apply=QPushButton("Aplicar BPM")
        self.tempo_apply.clicked.connect(self.apply_tempo_change)
        tempo_bar.addWidget(self.tempo_apply)
        tempo_bar.addStretch()
        root.addWidget(horizontal_controls(tempo_bar,self))

        split=QSplitter(Qt.Horizontal)
        track_panel=QFrame()
        track_panel.setObjectName("panel")
        tlay=QVBoxLayout(track_panel)
        tlay.addWidget(QLabel("PISTAS MIDI"))
        self.tracks_list=QTreeWidget()
        self.tracks_list.setHeaderLabels(["Pista / Canal","Notas"])
        self.tracks_list.header().setSectionResizeMode(0,QHeaderView.Stretch)
        self.tracks_list.setRootIsDecorated(False)
        self.tracks_list.currentItemChanged.connect(self.change_track)
        tlay.addWidget(self.tracks_list,1)
        tlay.addWidget(QLabel("Nota seleccionada"))
        self.selected_label=QLabel("—")
        self.selected_label.setObjectName("status")
        tlay.addWidget(self.selected_label)
        note_editor=QFrame()
        note_editor.setObjectName("inner")
        fields=QVBoxLayout(note_editor)
        fields.setContentsMargins(5,6,5,6)
        fields.setSpacing(4)
        def field(title,lower,upper):
            row=QHBoxLayout()
            row.setContentsMargins(0,0,0,0)
            label=QLabel(title)
            label.setMinimumWidth(63)
            row.addWidget(label)
            edit=QSpinBox()
            edit.setRange(lower,upper)
            edit.setMinimumWidth(75)
            edit.setToolTip("Introduce un valor MIDI numérico y pulsa Aplicar")
            row.addWidget(edit,1)
            fields.addLayout(row)
            return edit
        self.note_pitch=field("Altura",LOW,HIGH)
        self.note_start=field("Inicio",0,100000000)
        self.note_duration=field("Duración",1,100000000)
        self.note_apply=QPushButton("Aplicar valores a selección")
        self.note_apply.setToolTip(
            "Edita numéricamente notas MIDI seleccionadas. Con varias notas "
            "aplica desplazamientos de altura/inicio y duración comunes.")
        self.note_apply.clicked.connect(self.apply_note_values)
        fields.addWidget(self.note_apply)
        tlay.addWidget(note_editor)
        velrow=QHBoxLayout()
        velrow.addWidget(QLabel("Velocidad"))
        self.velocity=SliderNumber(1,127,90,1)
        self.velocity.valueChanged.connect(self.edit_velocity)
        velrow.addWidget(self.velocity)
        tlay.addLayout(velrow)
        apply_quant=QPushButton("Cuantizar pista seleccionada")
        apply_quant.clicked.connect(self.quantize_track)
        tlay.addWidget(apply_quant)
        split.addWidget(track_panel)

        center=QWidget()
        c_layout=QVBoxLayout(center)
        c_layout.setContentsMargins(0,0,0,0)
        self.scene=QGraphicsScene(self)
        self.view=RollView(self)
        self.view.setScene(self.scene)
        self.scene.selectionChanged.connect(self.sync_scene_selection)
        c_layout.addWidget(self.view,1)
        tip=QLabel("Clic: seleccionar · Ctrl/Mayús+clic: varias · Arrastrar marco: seleccionar · Lápiz: crear nota con un clic · Ctrl+rueda: zoom H · Alt+rueda: zoom V · Encajar pista: vista completa · Doble clic: crear nota · Arrastrar: mover · Borde derecho: duración · Supr: borrar · Ctrl+Z/Y: deshacer/rehacer")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        c_layout.addWidget(tip)
        split.addWidget(center)
        split.setStretchFactor(0,0)
        split.setStretchFactor(1,1)
        split.setSizes([205,1230])
        split.setChildrenCollapsible(False)
        track_panel.setMinimumWidth(160)
        track_panel.setMaximumWidth(280)
        # Altura suficiente para 3 controles de nota y su botón:
        # anteriormente Qt reducía este panel a 13px en ventana 1200x760.
        split.setMinimumHeight(400)
        root.addWidget(split,1)

        actions=QHBoxLayout()
        self.delete_button=QPushButton("Eliminar nota")
        self.delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(self.delete_button)
        self.copy_button=QPushButton("Copiar nota")
        self.copy_button.clicked.connect(self.copy_note)
        actions.addWidget(self.copy_button)
        self.paste_button=QPushButton("Pegar nota")
        self.paste_button.clicked.connect(self.paste_note)
        actions.addWidget(self.paste_button)
        actions.addStretch()
        self.stats=QLabel("Abre una conversión MIDI para editarla")
        self.stats.setObjectName("muted")
        actions.addWidget(self.stats)
        root.addLayout(actions)

        self.preview=PreviewPlayer("ESCUCHAR MIDI · ÚLTIMA VERSIÓN GUARDADA",self)
        self.preview.playStateChanged.connect(self.on_play_state_changed)
        self.preview.setVisible(False)
        self.preview.setMaximumHeight(170)
        self.listen_toggle=QPushButton("▶ Abrir panel de escucha")
        self.listen_toggle.clicked.connect(self.toggle_listen_panel)
        actions.insertWidget(3,self.listen_toggle)
        root.addWidget(self.preview)
        self.redraw()
        QTimer.singleShot(100,self.center_empty_keyboard)
        QShortcut(QKeySequence.Undo,self,activated=self.undo)
        QShortcut(QKeySequence.Redo,self,activated=self.redo)
        QShortcut(QKeySequence("Ctrl+Y"),self,activated=self.redo)
        QShortcut(QKeySequence("Delete"),self,activated=self.delete_selected)
        QShortcut(QKeySequence("Ctrl+A"),self,activated=self.select_all_notes)
        QShortcut(QKeySequence("N"),self,activated=lambda:self.tool.setCurrentIndex(1))
        QShortcut(QKeySequence("V"),self,activated=lambda:self.tool.setCurrentIndex(0))
        QShortcut(QKeySequence.Copy,self,activated=self.copy_note)
        QShortcut(QKeySequence.Paste,self,activated=self.paste_note)
        self.clipboard=None
        QShortcut(QKeySequence("Space"),self,activated=self.transport_toggle)
        QShortcut(QKeySequence("Home"),self,activated=lambda:self.seek_tick(0))
        self.zoom.valueChanged.connect(self.save_view_settings)
        self.zoom_vertical.valueChanged.connect(self.save_view_settings)
        self.zoom_digit.valueChanged.connect(self.save_view_settings)
        self.zoom_vertical_digit.valueChanged.connect(self.save_view_settings)
        self.grid.currentIndexChanged.connect(self.save_view_settings)
        self.tempo_mode.currentIndexChanged.connect(self.save_view_settings)
        self.follow_cursor.toggled.connect(self.save_view_settings)
        self.on_grid_changed()

    def choose_file(self):
        path,_=file_dialogs.get_open_file_name(self,"Abrir MIDI",str(Path.home()),
             "MIDI (*.mid *.midi *.kar)")
        if path:
            if getattr(self,"in_workspace",False) and getattr(self,"workspace",None):
                self.workspace.show_piano_roll(path)
            else:
                self.open_midi(path)

    def open_midi(self,path):
        if not self.check_discard():
            return False
        try:
            midi,tracks=parse_file(path)
        except (OSError,EOFError,ValueError,TypeError) as exc:
            QMessageBox.warning(self,"MIDI no válido",str(exc))
            return False
        self.midi,self.tracks=midi,tracks
        self.current_path=Path(path).resolve()
        self._pending_seek_ms=None
        self.track_index=0
        self.selected_indices.clear()
        self.selected_index=None
        self.history.clear();self.future.clear();self.dirty=False
        self.file_label.setText(self.current_path.name)
        self.tracks_list.blockSignals(True)
        self.tracks_list.clear()
        for idx,tr in enumerate(tracks):
            ch=','.join(str(i+1) for i in tr["channels"]) or "—"
            item=QTreeWidgetItem([f"{idx+1:02} · {tr['name']} · CH {ch}",str(len(tr["notes"]))])
            self.tracks_list.addTopLevelItem(item)
        self.tracks_list.blockSignals(False)
        target=next((i for i,tr in enumerate(tracks) if tr["notes"]),0)
        self.tracks_list.setCurrentItem(self.tracks_list.topLevelItem(target))
        self.change_track(self.tracks_list.currentItem(),None)
        self.preview.load(self.current_path)
        self.tempo_bpm.setValue(self.current_bpm())
        self.refresh_midi_list()
        self.stats.setText(f"{len(tracks)} pistas · {sum(len(t['notes']) for t in tracks)} notas · "
                           f"{self.ticks_per_beat} ticks/negra")
        # Encajar automáticamente al ABRIR, con el tamaño definitivo
        # del viewport, sin perder la posibilidad de hacer zoom manual.
        QTimer.singleShot(0,self.fit_notes)
        return True

    def check_discard(self):
        if not self.dirty:
            return True
        result=QMessageBox.question(self,"Cambios sin guardar",
                 "Hay modificaciones sin guardar. ¿Descartarlas y continuar?",
                 QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        return result==QMessageBox.Yes

    def change_track(self,current,previous):
        if not self.tracks or current is None:
            return
        idx=self.tracks_list.indexOfTopLevelItem(current)
        if idx<0:return
        self.track_index=idx
        self.selected_index=None
        self.selected_indices.clear()
        self.update_selected()
        self.redraw()
        self.focus_notes()

    def focus_notes(self):
        """Al cambiar de pista muestra sus notas, no octavas vacías."""
        if self.current_notes:
            pitches=sorted(n["pitch"] for n in self.current_notes)
            pitch=pitches[len(pitches)//2]
            first=min(n["start"] for n in self.current_notes)
        else:
            pitch=60
            first=0
        # Centrar altura; mantener compás 1 si las notas comienzan pronto.
        self.view.centerOn(self.tick_x(first), self.pitch_y(pitch))
        if first <= self.ticks_per_beat*5:
            self.view.horizontalScrollBar().setValue(0)

    def on_grid_changed(self):
        div=self.grid.currentData()
        self.quant_ticks=max(1,self.ticks_per_beat//div) if div else 0
        if self.midi:self.redraw()

    def toggle_view_presets(self):
        visible=not self.roll_presets.isVisible()
        self.roll_presets.setVisible(visible)
        self.view_presets_toggle.setText("Presets de vista ▴" if visible else "Presets de vista ▾")

    def toggle_listen_panel(self):
        visible=not self.preview.isVisible()
        self.preview.setVisible(visible)
        self.listen_toggle.setText("▴ Ocultar escucha" if visible else "▶ Abrir panel de escucha")
        if not visible:self.preview.stop()

    def center_empty_keyboard(self):
        if not self.midi:
            self.view.verticalScrollBar().setValue(
                max(0,int(self.pitch_y(60)-self.view.viewport().height()*.55)))

    def set_beat_zoom(self,value,redraw=True):
        value=max(.000001,min(300.,float(value)))
        # Preserve current musical viewport center when manually zooming.
        center=self.view.mapToScene(self.view.viewport().rect().center())
        tick=self.x_to_tick(center.x())
        pitch=self.y_to_pitch(center.y())
        self.beat_px=value
        self.zoom.blockSignals(True)
        self.zoom.setValue(self._to_slider(value,.000001,300.))
        self.zoom.blockSignals(False)
        self.zoom_digit.blockSignals(True)
        self.zoom_digit.setValue(value)
        self.zoom_digit.blockSignals(False)
        if redraw:
            self.redraw()
            self.view.centerOn(self.tick_x(tick),self.pitch_y(pitch))

    def set_row_zoom(self,value,redraw=True):
        value=max(.5,min(48.,float(value)))
        center=self.view.mapToScene(self.view.viewport().rect().center())
        pitch=self.y_to_pitch(center.y())
        tick=self.x_to_tick(center.x())
        self.row_px=value
        self.zoom_vertical.blockSignals(True)
        self.zoom_vertical.setValue(self._to_slider(value,.5,48.,1000))
        self.zoom_vertical.blockSignals(False)
        self.zoom_vertical_digit.blockSignals(True)
        self.zoom_vertical_digit.setValue(value)
        self.zoom_vertical_digit.blockSignals(False)
        if redraw:
            self.redraw()
            self.view.centerOn(self.tick_x(tick),self.pitch_y(pitch))

    def on_zoom(self,value):
        self.set_beat_zoom(self._from_slider(value,.000001,300.))

    def on_vertical_zoom(self,value):
        self.set_row_zoom(self._from_slider(value,.5,48.,1000))

    def redraw(self):
        # scene.clear() emits selectionChanged; rebuilding must not erase
        # the model selection during every edit, zoom or rerender.
        previous=self.scene.blockSignals(True)
        self.scene.clear()
        if not self.tracks or not self.midi:
            width=max(800,self.view.viewport().width()+2)
            height=RULER+(HIGH-LOW+1)*self.row_px
            self.scene.setSceneRect(0,0,width,height)
            for pitch in range(LOW,HIGH+1):
                y=self.pitch_y(pitch)
                black=pitch%12 in (1,3,6,8,10)
                self.scene.addRect(QRectF(KEY_WIDTH,y,width-KEY_WIDTH,self.row_px),
                    QPen(QColor("#234459"),.65),
                    QBrush(QColor("#102437" if black else "#163047")))
            for beat in range(0,36,self.grid_beat_step(36)):
                x=self.tick_x(beat*self.ticks_per_beat)
                self.scene.addLine(x,RULER,x,height,
                    QPen(QColor("#37647c" if beat%4==0 else "#1f4057"),1))
            self.stats.setText("Sin archivo MIDI · teclado y rejilla preparados para edición")
            self._playhead=None
            self.view.viewport().update()
            self.scene.blockSignals(previous)
            return
        max_tick=max([self.ticks_per_beat*4]+[n["end"] for n in self.current_notes])
        width=max(KEY_WIDTH+100,self.view.viewport().width(),
                  self.tick_x(max_tick+self.ticks_per_beat*.1)+5)
        height=RULER+(HIGH-LOW+1)*self.row_px
        self.scene.setSceneRect(0,0,width,height)
        # Piano keyboard and semitone lanes
        for pitch in range(LOW,HIGH+1):
            y=self.pitch_y(pitch)
            black=pitch%12 in (1,3,6,8,10)
            self.scene.addRect(QRectF(KEY_WIDTH,y,width-KEY_WIDTH,self.row_px),
                QPen(QColor("#263747"),.4),QBrush(QColor("#172635" if black else "#1d3040")))
            key=self.scene.addRect(QRectF(0,y,KEY_WIDTH-2,self.row_px),
                QPen(QColor("#263b48"),.5),QBrush(QColor("#293946" if black else "#d8e4ea")))
            if self.row_px>=14 and (pitch%12 in (0,5,9) or pitch==LOW):
                label=self.scene.addSimpleText(note_name(pitch))
                label.setBrush(QBrush(QColor("#182a34" if not black else "#e6eff2")))
                label.setPos(7,y-1)
                label.setScale(.8)
        # Time ruler
        self.scene.addRect(QRectF(KEY_WIDTH,0,width-KEY_WIDTH,RULER),
            QPen(QColor("#435769"),.8),QBrush(QColor("#273b4a")))
        num=max(4,int(math.ceil(max_tick/self.ticks_per_beat))+1)
        step=self.grid_beat_step(num)
        for beat in range(0,num,step):
            x=self.tick_x(beat*self.ticks_per_beat)
            self.scene.addLine(x,RULER,x,height,
                QPen(QColor("#5a7587" if beat%4==0 else "#354c5c"),
                     1.3 if beat%4==0 else .7))
            if beat%4==0 and self.beat_px*step>=20:
                mark=self.scene.addSimpleText(str(beat//4+1))
                mark.setBrush(QBrush(QColor("#d6e6ec")))
                mark.setPos(x+4,3)
        if self.quant_ticks:
            subdivisions=min(16,max(1,self.ticks_per_beat//self.quant_ticks))
            if self.beat_px/subdivisions>=8:
                for beat in range(0,num):
                    for sub in range(1,subdivisions):
                        x=self.tick_x(beat*self.ticks_per_beat+sub*self.quant_ticks)
                        self.scene.addLine(x,RULER,x,height,QPen(QColor("#273e4f"),.5))
        for i,n in enumerate(self.current_notes):
            x=self.tick_x(n["start"])
            w=max(2.5,self.delta_x(n["end"]-n["start"]))
            item=NoteBox(self,i,QRectF(x,self.pitch_y(n["pitch"])+self.note_offset(),
                         w,self.note_height()),
                         SELECT_COLOR if i in self.selected_indices else NOTE_COLOR)
            self.scene.addItem(item)
            if i in self.selected_indices:
                self._syncing_selection=True
                item.setSelected(True)
                self._syncing_selection=False
        self._playhead=self.scene.addLine(
            self.tick_x(0),0,self.tick_x(0),height,
            QPen(QColor("#ffc95a"),2))
        self._playhead.setZValue(80)
        self.update_playhead()
        self.update_selected()
        self.stats.setText(f"Pista: {self.tracks[self.track_index]['name']} · "
                           f"{len(self.current_notes)} notas · "
                           f"{sum(len(t['notes']) for t in self.tracks)} notas en total")
        self.scene.blockSignals(previous)

    def change_tool(self,index):
        self.tool_mode=self.tool.currentData() or "select"
        self.view.setDragMode(
            QGraphicsView.RubberBandDrag if self.tool_mode=="select"
            else QGraphicsView.NoDrag)
        self.view.setCursor(Qt.CrossCursor if self.tool_mode=="pencil" else
                            Qt.PointingHandCursor if self.tool_mode=="erase" else
                            Qt.ArrowCursor)

    def sync_scene_selection(self):
        if self._syncing_selection:return
        self.selected_indices={item.index for item in self.scene.selectedItems()
                               if isinstance(item,NoteBox)}
        self.selected_index=(min(self.selected_indices) if self.selected_indices else None)
        self.update_selected()

    def _paint_selection(self):
        self._syncing_selection=True
        try:
            for item in self.scene.items():
                if isinstance(item,NoteBox):
                    active=item.index in self.selected_indices
                    item.setSelected(active)
                    item.setBrush(QBrush(SELECT_COLOR if active else NOTE_COLOR))
        finally:
            self._syncing_selection=False

    def select_note(self,index,additive=False):
        if not 0<=index<len(self.current_notes):return
        if not additive:
            self.selected_indices={index}
        elif index in self.selected_indices:
            self.selected_indices.remove(index)
        else:self.selected_indices.add(index)
        self.selected_index=(index if index in self.selected_indices
                              else min(self.selected_indices) if self.selected_indices else None)
        self._paint_selection()
        self.update_selected()

    def select_all_notes(self):
        self.selected_indices=set(range(len(self.current_notes)))
        self.selected_index=min(self.selected_indices) if self.selected_indices else None
        self._paint_selection()
        self.update_selected()

    def update_selected(self):
        n=(self.current_notes[self.selected_index]
           if self.selected_index is not None and self.selected_index<len(self.current_notes)
           else None)
        if len(self.selected_indices)>1:
            self.selected_label.setText(f"{len(self.selected_indices)} notas seleccionadas")
        elif n:
            self.selected_label.setText(
                f"{note_name(n['pitch'])} · inicio {n['start']} · "
                f"duración {n['end']-n['start']}")
        else:self.selected_label.setText("Sin selección")
        self.velocity.blockSignals(True)
        self.velocity.setValue(n["velocity"] if n else 90)
        self.velocity.blockSignals(False)
        for control,value in (
            (self.note_pitch,n["pitch"] if n else 60),
            (self.note_start,n["start"] if n else 0),
            (self.note_duration,n["end"]-n["start"] if n else self.ticks_per_beat)):
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)
        self.note_apply.setEnabled(n is not None)

    def apply_note_values(self):
        """Edición escrita, una sola transacción para una o varias notas."""
        indexes=sorted(i for i in self.selected_indices if 0<=i<len(self.current_notes))
        if not indexes:return
        anchor=self.current_notes[self.selected_index or indexes[0]]
        delta_pitch=self.note_pitch.value()-anchor["pitch"]
        delta_start=self.note_start.value()-anchor["start"]
        duration=self.note_duration.value()
        originals={i:copy.deepcopy(self.current_notes[i]) for i in indexes}
        delta_pitch=max(LOW-min(n["pitch"] for n in originals.values()),
                        min(HIGH-max(n["pitch"] for n in originals.values()),delta_pitch))
        delta_start=max(-min(n["start"] for n in originals.values()),delta_start)
        if all((n["pitch"]+delta_pitch,n["start"]+delta_start,duration)==
               (n["pitch"],n["start"],n["end"]-n["start"]) for n in originals.values()):
            return
        self.snapshot()
        for i,n in originals.items():
            current=self.current_notes[i]
            current["pitch"]=n["pitch"]+delta_pitch
            current["start"]=n["start"]+delta_start
            current["end"]=current["start"]+duration
        self.redraw()

    def move_notes(self,originals,delta_tick,delta_pitch):
        """Una transacción de deshacer para el arrastre de todo el grupo."""
        if not originals:return
        tick=max(-min(n["start"] for n in originals.values()),int(delta_tick))
        pitch=max(LOW-min(n["pitch"] for n in originals.values()),
                  min(HIGH-max(n["pitch"] for n in originals.values()),int(delta_pitch)))
        if tick==0 and pitch==0:
            self.redraw();return
        self.snapshot()
        for i,n in originals.items():
            self.current_notes[i]["start"]=n["start"]+tick
            self.current_notes[i]["end"]=n["end"]+tick
            self.current_notes[i]["pitch"]=n["pitch"]+pitch
        self.selected_indices=set(originals)
        self.selected_index=min(originals)
        self.redraw()

    def snapshot(self):
        if not self.tracks:return
        # Guardar también eventos meta (tempo) para deshacer/rehacer
        # cambios de BPM además de la edición de notas.
        self.history.append(copy.deepcopy(self.tracks))
        self.history=self.history[-80:]
        self.future.clear()
        self.dirty=True

    def restore(self,data):
        self.tracks=copy.deepcopy(data)
        self.selected_index=None
        self.selected_indices.clear()
        self.update_track_list()
        self.tempo_bpm.setValue(self.current_bpm())
        self.redraw()

    def update_track_list(self):
        for idx,tr in enumerate(self.tracks):
            self.tracks_list.topLevelItem(idx).setText(1,str(len(tr["notes"])))

    def undo(self):
        if not self.history:return
        self.future.append(copy.deepcopy(self.tracks))
        self.restore(self.history.pop())
        self.dirty=True

    def redo(self):
        if not self.future:return
        self.history.append(copy.deepcopy(self.tracks))
        self.restore(self.future.pop())
        self.dirty=True

    def add_note(self,note):
        if not self.tracks:return
        self.snapshot()
        self.current_notes.append(note)
        self.selected_index=len(self.current_notes)-1
        self.selected_indices={self.selected_index}
        self.update_track_list();self.redraw()

    def modify_note(self,index,note):
        if index>=len(self.current_notes):return
        self.snapshot()
        self.current_notes[index]=note
        self.selected_index=index
        self.selected_indices={index}
        self.redraw()

    def delete_note(self,index):
        if not 0<=index<len(self.current_notes):return
        self.snapshot()
        del self.current_notes[index]
        self.selected_index=None
        self.selected_indices.clear()
        self.update_track_list();self.redraw()

    def delete_selected(self):
        indexes=sorted((i for i in self.selected_indices if i<len(self.current_notes)),
                        reverse=True)
        if not indexes:return
        self.snapshot()
        for index in indexes:del self.current_notes[index]
        self.selected_index=None
        self.selected_indices.clear()
        self.update_track_list();self.redraw()

    def edit_velocity(self,value):
        indexes=[i for i in self.selected_indices if 0<=i<len(self.current_notes)]
        if indexes and any(self.current_notes[i]["velocity"]!=value for i in indexes):
            self.snapshot()
            for i in indexes:self.current_notes[i]["velocity"]=value

    def copy_note(self):
        indexes=sorted(i for i in self.selected_indices if 0<=i<len(self.current_notes))
        if indexes:
            self.clipboard=[copy.deepcopy(self.current_notes[i]) for i in indexes]
            self.stats.setText(f"Copiadas {len(indexes)} notas; Pegar desplaza una negra")

    def paste_note(self):
        if not self.clipboard or not self.tracks:return
        notes=self.clipboard if isinstance(self.clipboard,list) else [self.clipboard]
        self.snapshot()
        first=len(self.current_notes)
        for original in notes:
            n=copy.deepcopy(original)
            n["start"]+=self.ticks_per_beat
            n["end"]+=self.ticks_per_beat
            n["channel"]=self.default_channel()
            self.current_notes.append(n)
        self.selected_indices=set(range(first,len(self.current_notes)))
        self.selected_index=first
        self.update_track_list();self.redraw()

    def quantize_track(self):
        if not self.current_notes:
            return
        if not self.quant_ticks:
            QMessageBox.information(self,"Cuantización","Elige una rejilla antes de cuantizar.")
            return
        self.snapshot()
        for n in self.current_notes:
            a=self.snap_tick(n["start"])
            b=self.snap_tick(n["end"])
            n["start"]=a
            n["end"]=max(a+self.quant_ticks,b)
        self.redraw()

    def current_bpm(self):
        data=[]
        for track in self.tracks:
            for tick,msg in track["other"]:
                if msg.type=="set_tempo":
                    data.append((tick,msg.tempo))
        tempo=min(data,key=lambda x:x[0])[1] if data else 500000
        return 60_000_000./tempo

    def apply_tempo_change(self):
        if not self.midi or not self.tracks:
            return
        target=float(self.tempo_bpm.value())
        previous=self.current_bpm()
        if abs(target-previous)<.005:return
        # Los MIDI con cambios internos de tempo también pueden escalarse
        # proporcionalmente sin borrar sus cambios de sección.
        ratio=target/previous
        preserve_seconds=self.tempo_mode.currentData()=="keep_time"
        self.snapshot()
        meta_count=0
        for track in self.tracks:
            if preserve_seconds:
                for note in track["notes"]:
                    note["start"]=round(note["start"]*ratio)
                    note["end"]=max(note["start"]+1,round(note["end"]*ratio))
            new_other=[]
            for tick,msg in track["other"]:
                if preserve_seconds:
                    tick=round(tick*ratio)
                if msg.type=="set_tempo":
                    msg=msg.copy(tempo=max(10000,round(msg.tempo/ratio)))
                    meta_count+=1
                new_other.append((tick,msg))
            track["other"]=new_other
        if not meta_count:
            self.tracks[0]["other"].append((
                0,mido.MetaMessage("set_tempo",tempo=mido.bpm2tempo(target),time=0)))
        self.tempo_bpm.setValue(self.current_bpm())
        self.redraw()
        self.stats.setText(f"BPM: {previous:.2f} → {self.current_bpm():.2f} · "
            +("duración real conservada (se ajustan ticks y compases)"
              if preserve_seconds else "velocidad musical modificada")
            +" · pulsa Aplicar edición a la tarea temporal para escuchar el cambio.")
        self.dirty=True

    def view_snapshot(self):
        return {"zoom":round(self.beat_px,6),
                "zoom_vertical":round(self.row_px,2),"quant":self.grid.currentData(),
                "tempo_mode":self.tempo_mode.currentData(),
                "follow_cursor":self.follow_cursor.isChecked()}

    def apply_view_preset(self,data):
        if "zoom" in data:self.set_beat_zoom(float(data["zoom"]))
        if "zoom_vertical" in data:self.set_row_zoom(float(data["zoom_vertical"]))
        if "quant" in data:
            idx=self.grid.findData(data["quant"])
            if idx>=0:self.grid.setCurrentIndex(idx)
        if "tempo_mode" in data:
            idx=self.tempo_mode.findData(data["tempo_mode"])
            if idx>=0:self.tempo_mode.setCurrentIndex(idx)
        if "follow_cursor" in data:self.follow_cursor.setChecked(bool(data["follow_cursor"]))

    def save_view_settings(self,*args):
        if not hasattr(self,"roll_presets"):return
        PRESET_DIR.mkdir(exist_ok=True)
        path=PRESET_DIR/"ultima_vista_piano.json"
        tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.view_snapshot(),ensure_ascii=False),encoding="utf-8")
        tmp.replace(path)

    def load_view_settings(self):
        try:
            data=json.loads((PRESET_DIR/"ultima_vista_piano.json").read_text(encoding="utf-8"))
            self.apply_view_preset(data)
        except (OSError,ValueError,TypeError):pass

    def refresh_midi_list(self):
        from bibliotecas import scan_jobs
        sources=[]
        workspace=getattr(self,"workspace",None)
        if workspace is not None:
            sources.extend(
                (f"Temporal · {i+1:02d} · {v['composite'].name}",v["composite"])
                for i,v in enumerate(workspace.midi_storage.versions)
                if v["composite"].is_file())
            for i,v in enumerate(workspace.midi_storage.versions):
                sources.extend(
                    (f"Toma {i+1:02d} · {p.name}",p)
                    for p in v["items"] if p.is_file())
        if workspace is not None:
            # Proyecto activo: no mezclar MIDI guardados en otros proyectos
            # ni el índice global de la biblioteca histórica.
            project=getattr(workspace.main,"project_dir",None)
            if project:
                from project_layout import module_dir
                base=module_dir(project,"midi")
                if base.is_dir():
                    sources.extend((f"Guardado · {p.name}",p)
                        for p in base.rglob("*")
                        if p.is_file() and p.suffix.lower() in (".mid",".midi",".kar")
                        and base.resolve() in p.resolve().parents)
        else:
            for group,items in scan_jobs("midi")[:30]:
                sources.extend((f"Guardado · {p.name}",p) for p in items[:75])
        if self.current_path and self.current_path.is_file():
            sources.insert(0,("MIDI abierto · "+self.current_path.name,self.current_path))
        seen=set()
        self.midi_choice.blockSignals(True)
        self.midi_choice.clear()
        for label,p in sources:
            path=str(p.resolve())
            if path not in seen:
                seen.add(path)
                self.midi_choice.addItem(label,path)
        if self.current_path:
            index=self.midi_choice.findData(str(self.current_path))
            if index>=0:self.midi_choice.setCurrentIndex(index)
        self.midi_choice.blockSignals(False)

    def select_midi_choice(self,index):
        path=self.midi_choice.itemData(index)
        if not path:return
        workspace=getattr(self,"workspace",None)
        if workspace is not None:
            workspace.show_piano_roll(path)
        else:
            self.open_midi(path)

    def preview_play(self):
        if not self.midi:return
        # Play no actúa como pausa; solo inicia o reanuda.
        if ((self.preview._play_process is not None or self.preview._qt_active)
             and not self.preview._paused):
            return
        self._manual_stop=False
        self.preview.play_pause()
        self.play_roll.setText("▶ Play" if self.preview._paused else "Ⅱ Pausa")

    def pause_toggle(self):
        if not self.midi:return
        if self.preview._play_process is None and not self.preview._qt_active:
            return
        self.preview.play_pause()
        self.play_roll.setText("▶ Play" if self.preview._paused else "Ⅱ Pausa")

    def transport_toggle(self):
        if ((self.preview._play_process is not None or self.preview._qt_active)
             and not self.preview._paused):
            self.pause_toggle()
        else:self.preview_play()

    def on_play_state_changed(self,playing):
        if playing or self._manual_stop or not self.loop_toggle.isChecked() or not self.midi:
            return
        # Solo bucle al FINAL de una reproducción natural; no cuando
        # se pausa o el usuario busca un nuevo punto.
        duration=self.preview._duration_ms
        if duration>0 and self.preview._current_ms>=duration-160:
            QTimer.singleShot(0,self.restart_loop)

    def restart_loop(self):
        if not self.midi or not self.loop_toggle.isChecked() or self._manual_stop:
            return
        self.seek_tick(0)
        self.preview_play()

    def preview_stop(self):
        self._manual_stop=True
        self.preview.stop()
        self._pending_seek_ms=None
        self.play_roll.setText("▶ Play")
        self.timeline.setValue(0)
        self.update_playhead()

    def last_tick(self):
        return max((n["end"] for tr in self.tracks for n in tr["notes"]),default=0)

    def step_transport(self,direction):
        position=self.seconds_to_tick(self.preview._position()/1000)
        self.seek_tick(max(0,min(self.last_tick(),
                                 position+int(direction)*self.ticks_per_beat)))

    def begin_scrub(self):
        self._scrubbing_time=True

    def scrub_timeline(self,value):
        if not self.midi:return
        tick=round(self.last_tick()*max(0,min(10000,int(value)))/10000)
        self.seek_tick(tick)

    def finish_scrub(self):
        self._scrubbing_time=False
        if self.midi:self.scrub_timeline(self.timeline.value())

    def fit_notes(self):
        """Encajar TODA la pista MIDI en ambos ejes, sin tocar sus eventos.

        No se recorta a los primeros compases. Incluye desde el tiempo
        cero hasta la última nota, y todas las alturas utilizadas.
        """
        if not self.midi or not self.current_notes:
            return
        notes=self.current_notes
        max_tick=max(n["end"] for n in notes)
        lowest=min(n["pitch"] for n in notes)
        highest=max(n["pitch"] for n in notes)
        # Dejar un borde de seguridad para que no corte los extremos.
        w=max(80,self.view.viewport().width()-KEY_WIDTH-18)
        h=max(30,self.view.viewport().height()-RULER-18)
        duration_beats=max(1.,max_tick/self.ticks_per_beat)
        vertical_rows=max(2,highest-lowest+1+4)
        beat_zoom=max(.000001,min(300.,w/(duration_beats+.3)))
        row_zoom=max(.5,min(48.,h/vertical_rows))
        self.set_beat_zoom(beat_zoom,redraw=False)
        self.set_row_zoom(row_zoom,redraw=False)
        self.redraw()
        # La vista comienza en compás 1, y el área de alturas utilizada
        # se centra verticalmente sin desperdiciar el editor.
        self.view.horizontalScrollBar().setValue(0)
        center_y=self.pitch_y((lowest+highest)/2)+self.row_px/2
        current=self.view.mapToScene(self.view.viewport().rect().center())
        self.view.centerOn(current.x(),center_y)
        self.view.horizontalScrollBar().setValue(0)
        self.view.viewport().update()
        self.save_view_settings()

    def _tempo_events(self):
        result=[]
        for tr in self.tracks:
            result.extend((int(t),msg.tempo) for t,msg in tr["other"]
                          if msg.type=="set_tempo")
        return sorted(result) or [(0,500000)]

    def seconds_to_tick(self,seconds):
        if not self.midi:return 0
        last_tick=0
        tempo=500000
        remain=max(0,float(seconds))
        for t,micro in self._tempo_events():
            dt=max(0,t-last_tick)
            interval=mido.tick2second(dt,self.ticks_per_beat,tempo)
            if remain<interval:
                return last_tick+round(mido.second2tick(remain,self.ticks_per_beat,tempo))
            remain-=interval
            last_tick=t
            tempo=micro
        return last_tick+round(mido.second2tick(remain,self.ticks_per_beat,tempo))

    def tick_to_seconds(self,tick):
        last_tick=0
        tempo=500000
        seconds=0.
        for t,micro in self._tempo_events():
            t=min(t,tick)
            seconds+=mido.tick2second(max(0,t-last_tick),self.ticks_per_beat,tempo)
            last_tick=t
            tempo=micro
            if t>=tick:return seconds
        return seconds+mido.tick2second(max(0,tick-last_tick),self.ticks_per_beat,tempo)

    def seek_tick(self,tick):
        if not self.midi:return
        elapsed_ms=round(self.tick_to_seconds(tick)*1000)
        self.preview._set_clock(elapsed_ms)
        if self.preview._native_qt and self.preview._qt_active:
            self.preview.player.setPosition(elapsed_ms)
        if self.preview._prepared is None:
            # Con MIDI se renderiza primero con TiMidity; recordar la
            # posición solicitada para reproducir desde ahí tras render.
            self._pending_seek_ms=elapsed_ms
        elif self.preview._play_process is not None:
            self.preview._start_audio(elapsed_ms)
        self.update_playhead()

    def update_playhead(self):
        if not self.midi or self._playhead is None:return
        if (self._pending_seek_ms is not None
                and self.preview._prepared is not None
                and self.preview._play_process is not None):
            target=self._pending_seek_ms
            self._pending_seek_ms=None
            self.preview._start_audio(target)
        ms=self.preview._position()
        tick=self.seconds_to_tick(ms/1000)
        x=self.tick_x(tick)
        line=self._playhead.line()
        self._playhead.setLine(x,0,x,line.y2())
        duration=max(self.preview._duration_ms,
                     round(self.tick_to_seconds(self.last_tick())*1000))
        self.position_label.setText(
            f"{int(ms//60000):02d}:{int(ms//1000%60):02d} / "
            f"{int(duration//60000):02d}:{int(duration//1000%60):02d}")
        if not self._scrubbing_time:
            self.timeline.blockSignals(True)
            self.timeline.setValue(round(max(0,min(1,ms/max(1,duration)))*10000))
            self.timeline.blockSignals(False)
        self.bar_position.setText(
            f"{int(tick//max(1,self.ticks_per_beat*4)+1)} : "
            f"{int((tick//max(1,self.ticks_per_beat))%4+1)}")
        if self.loop_toggle.isChecked() and duration>0 and ms>=duration-160 and (
            self.preview._play_process is not None or self.preview._qt_active):
            self.seek_tick(0)
        self.play_roll.setText("Ⅱ Pausa" if (
            (self.preview._play_process is not None or self.preview._qt_active)
            and not self.preview._paused) else "▶ Play")
        if (self.follow_cursor.isChecked() and
            self.preview._play_process is not None and not self.preview._paused):
            visible=self.view.mapFromScene(x,RULER+10)
            if visible.x()>self.view.viewport().width()*.83 or visible.x()<0:
                self.view.horizontalScrollBar().setValue(
                    max(0,self.view.horizontalScrollBar().value()+
                        int(visible.x()-self.view.viewport().width()*.35)))

    def save_as(self):
        if not self.midi or not self.current_path:return
        from export_dialog import export_files
        workspace=getattr(self,"workspace",None)
        project=getattr(workspace.main,"project_dir",None) if workspace else None
        from task_staging import unique_dest
        # El editor guarda la exportación en temporales antes de permitir
        # elegir la ruta y el nombre final. No pisa el MIDI original.
        base=(Path(project)/"temporales"/"midi" if project
              else self.current_path.parent)
        base.mkdir(parents=True,exist_ok=True)
        intermediate=unique_dest(base,"piano_roll_exportado.mid")
        try:
            from piano_roll import export_file
            export_file(self.midi,self.tracks,intermediate)
            mido.MidiFile(str(intermediate))
            saved=export_files(self,[intermediate],project,"Guardar MIDI editado",
                               kind="piano_roll")
            if saved:
                if project:
                    # Conservar la edición exportada como MIDI de trabajo:
                    # el MIDI importado del usuario permanece intacto.
                    internal=base/"piano_roll_sesion.mid"
                    if intermediate.resolve()!=internal.resolve():
                        intermediate.replace(internal)
                    self.current_path=internal
                    self.preview.load(internal)
                self.dirty=False
                self.history.clear()
                self.future.clear()
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,"No se pudo guardar MIDI",str(exc))
        finally:
            intermediate.unlink(missing_ok=True)

    def save_file(self,path):
        if not self.midi:raise ValueError("No hay MIDI cargado")
        path=Path(path)
        workspace=getattr(self,"workspace",None)
        project=getattr(workspace.main,"project_dir",None) if workspace else None
        if project:
            from task_staging import inside
            if not (inside(path,Path(project)/"temporales"/"midi")
                    or inside(path,__import__("project_layout").module_dir(project,"midi"))
                    or inside(path,__import__("project_layout").module_dir(project,"piano_roll"))):
                raise ValueError("El MIDI editado debe guardarse dentro del proyecto activo")
        if self.current_path and path.resolve()==self.current_path:
            raise ValueError("No se permite sobrescribir el MIDI de origen")
        if path.exists():
            raise FileExistsError(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        try:
            export_file(self.midi,self.tracks,path)
            # Comprobar que el resultado se puede volver a leer.
            mido.MidiFile(str(path))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        self.dirty=False
        self.history.clear();self.future.clear()
        from bibliotecas import register_result
        from task_staging import TEMP_ROOT
        from task_staging import inside
        if (TEMP_ROOT.resolve() not in path.resolve().parents and
                not (project and inside(path,Path(project)/"temporales"))):
            register_result("midi",path)
        self.preview.load(path)
        self.stats.setText(f"Guardado: {path.name} · edición no destructiva")
        return path

    def closeEvent(self,event):
        if not self.check_discard():
            event.ignore();return
        self.preview.cleanup()
        event.accept()
