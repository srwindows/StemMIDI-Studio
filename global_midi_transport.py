"""Transporte MIDI global accesible desde todas las pestañas de StemMIDI Studio.

Reutiliza PreviewPlayer/TiMidity y su medición PCM real, sin sintetizadores
duplicados ni escritura del MIDI original. Una sola reproducción activa.
"""
from __future__ import annotations
import math
from pathlib import Path

from PySide6.QtCore import Qt,QTimer,QSignalBlocker
from PySide6.QtWidgets import (QFrame,QHBoxLayout,QLabel,QComboBox,QPushButton,
                              QSlider,QProgressBar)
from preview_player import PreviewPlayer,timecode,AudioRoute
from studio_home import MIDI

class GlobalMidiTransport(QFrame):
    def __init__(self,main):
        super().__init__(main)
        self.main=main
        self.setObjectName("globalMidiTransport")
        self.setMinimumHeight(43)
        self.setMaximumHeight(51)
        self.setStyleSheet("""
        QFrame#globalMidiTransport {
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #0b367a,stop:1 #031634);
            border-top:1px solid #2bb1fc;
        }
        QFrame#globalMidiTransport QPushButton {
            min-height:21px;max-height:27px;padding:2px 8px;
        }
        QFrame#globalMidiTransport QComboBox {min-height:21px;max-height:27px;}
        QFrame#globalMidiTransport QLabel {font-size:11px;color:#c9f5ff;}
        QFrame#globalMidiTransport QProgressBar {
            background:#02142c;border:1px solid #267eb4;
            min-height:7px;max-height:9px;border-radius:3px;
        }
        QFrame#globalMidiTransport QProgressBar::chunk {
            background:#30eacb;border-radius:2px;
        }
        """)
        row=QHBoxLayout(self)
        row.setContentsMargins(8,3,8,4)
        row.setSpacing(5)
        self.caption=QLabel("MIDI · GLOBAL")
        self.caption.setToolTip("Reproductor disponible en todas las pestañas. No cambia de módulo.")
        row.addWidget(self.caption)
        self.files=QComboBox(self)
        self.files.setObjectName("globalMidiFiles")
        self.files.setMinimumWidth(155)
        self.files.setMaximumWidth(285)
        self.files.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.files.setMinimumContentsLength(16)
        self.files.setToolTip("MIDI del proyecto activo · selecciona y pulsa ▶. No abre el editor.")
        self.files.currentIndexChanged.connect(self._source_changed)
        row.addWidget(self.files,2)
        self.open_button=QPushButton("Abrir…",self)
        self.open_button.setToolTip("Elegir un MIDI externo para escucharlo, sin importarlo al proyecto.")
        self.open_button.clicked.connect(self.open_midi)
        row.addWidget(self.open_button)
        self.play=QPushButton("▶",self)
        self.play.setObjectName("globalMidiPlay")
        self.play.setToolTip("Reproducir el MIDI seleccionado o reanudar")
        self.pause=QPushButton("Ⅱ",self)
        self.pause.setToolTip("Pausar o reanudar el MIDI")
        self.stop_button=QPushButton("■",self)
        self.stop_button.setToolTip("Detener la reproducción MIDI")
        for w in (self.play,self.pause,self.stop_button):
            w.setFixedWidth(35)
            row.addWidget(w)
        self.play.clicked.connect(self.play_selected)
        self.pause.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop)
        self.timeline=QSlider(Qt.Horizontal,self)
        self.timeline.setRange(0,1000)
        self.timeline.setTracking(False)
        self.timeline.setToolTip("Desplazamiento de reproducción MIDI")
        self.timeline.sliderReleased.connect(self.seek)
        row.addWidget(self.timeline,2)
        self.clock=QLabel("00:00 / 00:00",self)
        self.clock.setMinimumWidth(105)
        row.addWidget(self.clock)
        self.vus={}
        self.vu_db={}
        for channel in ("L","R"):
            tag=QLabel(channel,self)
            row.addWidget(tag)
            from studio_vu_unified import UnifiedPercentBar
            meter=UnifiedPercentBar(self)
            meter.setRange(0,100)
            meter.setTextVisible(False)
            meter.setFixedWidth(54)
            row.addWidget(meter)
            self.vus[channel]=meter
            self.vu_db[channel]=tag
        self.status=QLabel("Sin MIDI",self)
        self.status.setMinimumWidth(55)
        self.status.setMaximumWidth(115)
        row.addWidget(self.status)
        self.preview=PreviewPlayer("MIDI GLOBAL",self)
        self.preview.hide()
        self.preview.error.connect(self._error)
        self.preview.fileLoaded.connect(lambda _:self.refresh())
        self._project_key=None
        self._selected_external=None
        self._catalog=()
        self._cached_scan=0.
        self._followed_preview=None
        self._timer=QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self._update_controls()

    def _project_signature(self):
        return (getattr(self.main,"project_id",None),
                str(getattr(self.main,"project_dir",None) or ""))

    def reset_project(self):
        """Cerrar el MIDI del proyecto anterior y la preescucha temporal."""
        self.preview.clear()
        self._selected_external=None
        self._catalog=()
        self._cached_scan=0.
        self._followed_preview=None
        self._project_key=self._project_signature()
        with QSignalBlocker(self.files):
            self.files.clear()
        self.status.setText("Sin MIDI")
        self.clock.setText("00:00 / 00:00")
        self._update_controls()

    def _inventory(self):
        main=self.main
        project=getattr(main,"project_dir",None)
        if not project:return []
        base=Path(project)
        if not base.is_dir():return []
        work=getattr(main,"workbench",None)
        candidates=[]
        if work is not None:
            for storage_name in ("midi_storage",):
                storage=getattr(work,storage_name,None)
                if storage is None:continue
                candidates.extend(storage.items)
                if storage.composite:candidates.append(storage.composite)
                for version in storage.versions:
                    candidates.extend(version.get("items",()))
                    if version.get("composite"):candidates.append(version["composite"])
            piano=getattr(work,"piano",None)
            if piano is not None and piano.current_path:
                candidates.append(piano.current_path)
        for folder in ("audio_a_midi","piano_roll","resultados",
                       "temporales/midi","temporales/piano_roll"):
            target=base/folder
            if target.is_dir() and not target.is_symlink():
                candidates.extend(
                    path for path in target.rglob("*")
                    if path.suffix.lower() in MIDI and not path.is_symlink())
        unique={}
        for item in candidates:
            try:
                p=Path(item).resolve()
                if p.suffix.lower() not in MIDI or not p.is_file() or p.is_symlink():
                    continue
                # No mezclar proyectos ni recorrer orígenes no relacionados.
                p.relative_to(base.resolve())
                unique[str(p)]=p
            except (OSError,ValueError,TypeError):
                continue
        return sorted(unique.values(),key=lambda p:(p.name.casefold(),str(p)))

    def refresh_catalog(self,force=False):
        import time
        signature=self._project_signature()
        if signature!=self._project_key:
            self.reset_project()
        now=time.monotonic()
        if not force and now-self._cached_scan<2.:return
        self._cached_scan=now
        paths=self._inventory()
        if self._selected_external and self._selected_external.is_file():
            paths.append(self._selected_external)
        catalog=tuple(str(path) for path in paths)
        if catalog==self._catalog:return
        old=self.files.currentData()
        playing=self.preview.current_file
        with QSignalBlocker(self.files):
            self.files.clear()
            for path in paths:
                self.files.addItem(path.name,str(path))
                index=self.files.count()-1
                self.files.setItemData(index,str(path),Qt.ToolTipRole)
            selected=(old if old in catalog else playing if playing in catalog else None)
            if selected is not None:
                index=self.files.findData(selected)
                if index>=0:self.files.setCurrentIndex(index)
            elif self.files.count():self.files.setCurrentIndex(0)
        self._catalog=catalog
        self._update_controls()

    def select_file(self,path,play=False):
        """Reproducir desde listas del módulo sin cambiar la pestaña."""
        if not path:return False
        try:
            item=Path(path).expanduser().resolve()
            if not item.is_file() or item.suffix.lower() not in MIDI:return False
        except (OSError,ValueError,TypeError):return False
        self.refresh_catalog(force=True)
        index=self.files.findData(str(item))
        if index<0:
            self._selected_external=item
            self.refresh_catalog(force=True)
            index=self.files.findData(str(item))
        if index<0:return False
        self.files.setCurrentIndex(index)
        self._update_controls()
        if play:return self.play_selected()
        return True

    def open_midi(self):
        import file_dialogs
        project=getattr(self.main,"project_dir",None)
        directory=str(project) if project else str(Path.home())
        filename,_=file_dialogs.get_open_file_name(
            self,"Escuchar archivo MIDI",directory,"MIDI (*.mid *.midi *.kar)")
        if filename:self.select_file(filename,play=True)

    def _source_changed(self,_index):
        self._update_controls()
        path=self.files.currentData()
        if path:self.status.setText("Listo")
        else:self.status.setText("Sin MIDI")

    def _current_midi_preview(self):
        other=AudioRoute.active_preview()
        if other is not None and other.current_file:
            suffix=Path(other.current_file).suffix.lower()
            if suffix in MIDI and (other._qt_active or other._play_process is not None):
                return other
        return self.preview

    def play_selected(self):
        path=self.files.currentData()
        if not path:return False
        candidate=Path(path)
        if not candidate.is_file():self.refresh_catalog(force=True);return False
        active=AudioRoute.active_preview()
        if (active is not None and active.current_file==str(candidate) and
            (active._play_process is not None or active._qt_active)):
            if active._paused:active.play_pause()
            return True
        # La mezcla en vivo sólo tiene sentido durante la escucha marcada;
        # seleccionar MIDI global la detiene para no reproducir dos fuentes.
        home=getattr(self.main,"studio_home",None)
        if home is not None:
            for attr in ("_sep_listen",):
                source=getattr(home,attr,None)
                if source is not None and source.live.running:source.stop()
            manager=getattr(home,"_floating_manager",None)
            if manager is not None:
                expanded=manager.other_expanders.get(home.midi_card)
                if expanded is not None and expanded.midi_browser.listen.live.running:
                    expanded.midi_browser.listen.stop()
        if self.preview.current_file!=str(candidate):
            return bool(self.preview.load(candidate,autoplay=True))
        if self.preview._render is not None:
            return True
        active=(self.preview._play_process is not None or self.preview._qt_active)
        if active and not self.preview._paused:return True
        self.preview.play_pause()
        return True

    def toggle_pause(self):
        p=self._current_midi_preview()
        active=(p._play_process is not None or p._qt_active)
        if active:p.play_pause()
        elif p.current_file is not None and p._prepared is not None:
            p.play_pause()

    def stop(self):
        self._current_midi_preview().stop()
        self._update_controls()
        self.status.setText("Detenido")

    def seek(self):
        p=self._current_midi_preview()
        if not p.current_file or not p._duration_ms:return
        ms=round(self.timeline.value()/1000*p._duration_ms)
        active=bool(p._play_process is not None or p._qt_active)
        paused=p._paused
        if active:p._stop_audio()
        p._set_clock(ms)
        if active and not paused:p._start_audio(ms)

    @staticmethod
    def _db_norm(value):
        if value<=0:return 0
        db=20*math.log10(max(1e-8,value))
        return max(0,min(100,round((db+60)*100/60)))

    def _update_controls(self):
        item=bool(self.files.currentData() and Path(self.files.currentData()).is_file())
        p=self._current_midi_preview()
        busy=p._render is not None
        running=bool(p._play_process is not None or p._qt_active)
        self.play.setEnabled(item and not busy)
        self.pause.setEnabled(running)
        self.stop_button.setEnabled(running or busy or bool(p.current_file))
        self.timeline.setEnabled(p._duration_ms>0)
        self.play.setText("Ⅱ" if running and not p._paused else "▶")

    def refresh(self):
        self.refresh_catalog()
        p=self._current_midi_preview()
        active=bool(p._play_process is not None or p._qt_active)
        if p is not self.preview and active and p.current_file:
            identity=(id(p),p.current_file)
            if identity!=self._followed_preview:
                self._followed_preview=identity
                self.select_file(p.current_file,play=False)
        if p._render is not None:
            self.status.setText("Sintetizando…")
        elif active:
            self.status.setText("Pausa" if p._paused else "Reproduciendo")
        elif p.current_file:
            self.status.setText("Preparado" if p._prepared is not None else "Sin audio")
        else:self.status.setText("Sin MIDI" if not self.files.count() else "Listo")
        self.clock.setText(p.clock.text())
        if p._duration_ms>0 and not self.timeline.isSliderDown():
            with QSignalBlocker(self.timeline):
                self.timeline.setValue(round(1000*p._position()/p._duration_ms))
        vu=getattr(p,"_measured_vu",None)
        sample=(0.,0.)
        if active and not p._paused and vu is not None:
            index=int(max(0,p._position())/100)
            if index<len(vu.levels):
                gain=p.volume.value()/100.
                sample=(vu.levels[index][0]*gain,vu.levels[index][1]*gain)
        for index,channel in enumerate(("L","R")):
            self.vus[channel].setValue(self._db_norm(sample[index]))
            self.vu_db[channel].setToolTip(
                f"{20*math.log10(max(1e-8,sample[index])):.1f} dBFS"
                if sample[index]>0 else "Silencio")
        self._update_controls()

    def _error(self,message):
        self.status.setText("Error")
        self.status.setToolTip(str(message))

    def cleanup(self):
        self._timer.stop()
        self.preview.cleanup()

def install(main):
    shell=main.centralWidget()
    layout=shell.layout()
    bar=GlobalMidiTransport(main)
    layout.addWidget(bar,0)
    main.studio_midi_transport=bar
    return bar
