"""Tempo de reproducción del Piano Roll visible e independiente del compositor."""
from __future__ import annotations

from PySide6.QtCore import QObject,Qt,QTimer,QSignalBlocker
from PySide6.QtWidgets import (QFrame,QHBoxLayout,QLabel,QPushButton,QSlider,
                                QSpinBox,QSizePolicy,QSplitter,QWidget)

class PianoRollTempoStrip(QObject):
    """BPM real del MIDI; no usa el slider BPM del generador de acordes."""

    def __init__(self,editor):
        super().__init__(editor)
        self.editor=editor
        parent=editor.content_page
        frame=QFrame(parent)
        frame.setObjectName("pianoRollSongTempoBar")
        frame.setMaximumHeight(41)
        frame.setMinimumHeight(34)
        frame.setStyleSheet("""
            QFrame#pianoRollSongTempoBar {
              background:#0c2336; border:1px solid #376b8d;
              border-radius:5px; }
            QFrame#pianoRollSongTempoBar QLabel {
              color:#cee8f8; border:none; font-size:11px; }
            QFrame#pianoRollSongTempoBar QLabel#tempoStripHeading {
              font-weight:700; color:#8edfff; }
            QFrame#pianoRollSongTempoBar QSpinBox {
              background:#08182b; color:#f2faff; border:1px solid #4983a8;
              border-radius:3px; padding:2px 4px; font-size:12px; }
            QFrame#pianoRollSongTempoBar QPushButton {
              background:#14567b;color:#f2faff;border:1px solid #4795bc;
              border-radius:3px;padding:2px 8px; min-height:22px; }
            QFrame#pianoRollSongTempoBar QPushButton:hover {
              background:#1e779c; }
        """)
        lay=QHBoxLayout(frame)
        lay.setContentsMargins(9,3,9,3)
        lay.setSpacing(7)
        name=QLabel("TEMPO DEL PIANO ROLL",frame)
        name.setObjectName("tempoStripHeading")
        lay.addWidget(name,0)
        self.slider=QSlider(Qt.Horizontal,frame)
        self.slider.setObjectName("pianoRollMainTempoSlider")
        self.slider.setRange(35,300)
        self.slider.setMinimumWidth(75)
        self.slider.setMaximumWidth(240)
        self.slider.setToolTip("Tempo de la canción MIDI: 35 a 300 BPM")
        lay.addWidget(self.slider,2)
        self.spin=QSpinBox(frame)
        self.spin.setObjectName("pianoRollMainTempoBpm")
        self.spin.setRange(35,300)
        self.spin.setSuffix(" BPM")
        self.spin.setFixedWidth(105)
        lay.addWidget(self.spin,0)
        self.minus=QPushButton("−",frame)
        self.plus=QPushButton("+",frame)
        self.minus.setObjectName("pianoRollTempoMinus")
        self.plus.setObjectName("pianoRollTempoPlus")
        for button in (self.minus,self.plus):
            button.setMinimumWidth(28)
            button.setMaximumWidth(33)
            lay.addWidget(button,0)
        self.apply=QPushButton("Aplicar",frame)
        self.apply.setObjectName("pianoRollTempoApply")
        self.apply.setToolTip(
            "Aplicar la velocidad al MIDI sin desplazar las notas "
            "ni cambiar el tempo de composición")
        lay.addWidget(self.apply,0)
        self.hint=QLabel("BPM del MIDI · independiente de Componer",frame)
        self.hint.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        lay.addWidget(self.hint,1)
        self.widget=frame
        container=editor.content_layout
        # Insert immediately above the central roll area. If the tab
        # rearranges the center later, it remains an independent visible row.
        target=next((i for i in range(container.count())
                     if isinstance(container.itemAt(i).widget(),QSplitter)),None)
        if target is None:
            target=max(0,container.count()-2)
        container.insertWidget(target,frame)
        self.debounce=QTimer(self)
        self.debounce.setInterval(320)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.commit)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.slider.sliderReleased.connect(self.commit)
        self.spin.editingFinished.connect(self.commit)
        self.minus.clicked.connect(lambda:self.spin.setValue(self.spin.value()-1))
        self.plus.clicked.connect(lambda:self.spin.setValue(self.spin.value()+1))
        self.apply.clicked.connect(self.commit)
        editor.midiOpened.connect(lambda *_:self.refresh())
        editor.notesChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        editor=self.editor
        if editor.midi is None or not editor.tracks:
            self.hint.setText("Sin MIDI · 120 BPM por defecto")
            self.widget.setEnabled(False)
            with QSignalBlocker(self.slider),QSignalBlocker(self.spin):
                self.slider.setValue(120)
                self.spin.setValue(120)
            return
        self.widget.setEnabled(True)
        current=round(editor.current_bpm())
        current=max(35,min(300,current))
        # Do not override a pending manual BPM drag with a repaint.
        if self.debounce.isActive():return
        with QSignalBlocker(self.slider),QSignalBlocker(self.spin):
            self.slider.setValue(current)
            self.spin.setValue(current)
        self.hint.setText("BPM del MIDI · independiente de Componer")

    def _from_slider(self,value):
        with QSignalBlocker(self.spin):
            self.spin.setValue(value)
        self.debounce.start()

    def _from_spin(self,value):
        with QSignalBlocker(self.slider):
            self.slider.setValue(value)
        self.debounce.start()

    def commit(self):
        self.debounce.stop()
        editor=self.editor
        if editor.midi is None:return
        desired=self.spin.value()
        if abs(editor.current_bpm()-desired)<.01:return
        live=None
        try:
            live=editor._studio_live()
        except (AttributeError,RuntimeError):pass
        was_playing=bool(live is not None and live.running)
        paused=bool(was_playing and live.engine.paused)
        position=live.position_tick() if was_playing else 0
        if was_playing:live.stop()
        with QSignalBlocker(editor.tempo_bpm):
            editor.tempo_bpm.setValue(desired)
        editor.apply_tempo_change()
        if was_playing and live.play():
            if position:live.seek_tick(position)
            if paused:live.pause()
        self.refresh()


def install_professional_tempo(editor):
    """Idempotent and safe for the tab as well as the floating MIDI editor."""
    current=getattr(editor,"_professional_tempo_controller",None)
    if current is not None:return current
    result=PianoRollTempoStrip(editor)
    editor._professional_tempo_controller=result
    return result
