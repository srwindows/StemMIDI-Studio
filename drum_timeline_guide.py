"""Guía de reproducción para la tarjeta flotante Batería · pistas separadas.

Se dibuja SOBRE las seis ondas originales mediante su cursor opcional.
La duración y la posición proceden de los archivos y del reproductor real;
no hay simulación de tiempo, notas ni nuevos motores de audio.
"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QEvent, QTimer, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel


def clock(seconds, tenths=False):
    total=max(0.,float(seconds))
    minutes=int(total//60)
    sec=int(total)%60
    return f"{minutes:02d}:{sec:02d}.{int(total*10)%10}" if tenths else f"{minutes:02d}:{sec:02d}"


class TimeScale(QWidget):
    """Regla interactiva con marcas y puntero en posición absoluta."""
    seekRequested=Signal(float)
    previewRequested=Signal(float)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.duration=0.
        self.fraction=0.
        self.dragging=False
        self.setMinimumHeight(29)
        self.setMaximumHeight(32)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Escala temporal: clic o arrastra para situar la reproducción.")

    def set_state(self,duration,fraction):
        self.duration=max(0.,float(duration))
        self.fraction=max(0.,min(1.,float(fraction)))
        self.update()

    def _fraction(self,event):
        return max(0.,min(1.,event.position().x()/max(1.,self.width()-1)))

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.duration>0:
            self.dragging=True
            self.fraction=self._fraction(event)
            self.previewRequested.emit(self.fraction)
            self.update()
            event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.dragging:
            self.fraction=self._fraction(event)
            self.previewRequested.emit(self.fraction)
            self.update()
            event.accept()
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.dragging and event.button()==Qt.LeftButton:
            self.fraction=self._fraction(event)
            self.dragging=False
            self.update()
            self.seekRequested.emit(self.fraction)
            event.accept()
        else:super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor("#05234b"))
        w=max(1,self.width()-1)
        h=self.height()
        p.setPen(QPen(QColor("#2c688a"),1))
        p.drawLine(0,h-2,w,h-2)
        count=8 if w>=510 else 6 if w>=300 else 4
        for i in range(count+1):
            frac=i/count
            x=round(frac*w)
            p.setPen(QPen(QColor("#3678ac"),1))
            p.drawLine(x,h-13,x,h-2)
            if self.duration>0:
                label=clock(frac*self.duration,tenths=self.duration<20)
                p.setPen(QColor("#bcf2ff"))
                tw=p.fontMetrics().horizontalAdvance(label)
                xpos=max(1,min(w-tw-1,x-tw//2))
                p.drawText(xpos,h-16,label)
        if self.duration>0:
            x=round(self.fraction*w)
            p.setPen(QPen(QColor("#ffba54"),2))
            p.drawLine(x,2,x,h-2)
            p.setBrush(QColor("#ffba54"))
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF([
                QPointF(x-5,1),QPointF(x+5,1),QPointF(x,8)]))
        p.end()


class DrumTimelineGuide(QObject):
    """Acompaña SOLO a la tarjeta flotante de seis ondas de batería."""
    def __init__(self,home,card,parent=None):
        super().__init__(parent or card)
        self.home=home
        self.card=card
        self.active=False
        self.drag_part=None
        self.duration=0.
        self.cache_key=None
        self.fraction=0.
        self.panel=QFrame(card)
        self.panel.setObjectName("drumTimeGuide")
        self.panel.setStyleSheet(
            "QFrame#drumTimeGuide{background:#052048;border:1px solid #278dd1;"
            "border-radius:5px;} QFrame#drumTimeGuide QLabel{color:#bdefff;}")
        v=QVBoxLayout(self.panel)
        v.setContentsMargins(5,2,5,3)
        v.setSpacing(1)
        summary=QHBoxLayout()
        summary.setSpacing(5)
        caption=QLabel("GUÍA DE REPRODUCCIÓN · ESCALA DE TIEMPO",self.panel)
        caption.setStyleSheet("font-size:10px;font-weight:700;")
        summary.addWidget(caption)
        summary.addStretch(1)
        self.counter=QLabel("00:00.0 / 00:00.0",self.panel)
        self.counter.setObjectName("drumTimeCounter")
        self.counter.setStyleSheet("color:#ffdf9d;font-size:12px;font-weight:800;")
        summary.addWidget(self.counter)
        v.addLayout(summary)
        line=QHBoxLayout()
        line.setSpacing(3)
        text=QLabel("mm:ss",self.panel)
        text.setFixedWidth(50)
        line.addWidget(text)
        self.scale=TimeScale(self.panel)
        self.scale.seekRequested.connect(self.seek)
        self.scale.previewRequested.connect(self.preview_fraction)
        line.addWidget(self.scale,1)
        # Coincide con los dos botones cuadrados al final de cada fila.
        for _ in range(2):
            filler=QWidget(self.panel)
            filler.setFixedWidth(20)
            line.addWidget(filler)
        v.addLayout(line)
        self.timer=QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh)
        self.panel.hide()

    def _rows(self):
        return self.home.drum_stem_rows

    def _transport(self):
        manager=getattr(self.home,"_floating_manager",None)
        window=manager.windows.get(self.card) if manager else None
        return getattr(window,"float_transport",None)

    def _source(self,part):
        row=self._rows().get(part)
        p=row["path"] if row else None
        return Path(p).resolve() if p and Path(p).is_file() else None

    def _duration(self):
        # Las ondas FFmpeg ya analizadas indican la duración; si aún están
        # descodificando, leer una vez los metadatos reales de la fuente.
        files=[(part,self._source(part)) for part in self._rows()]
        source=next((p for _,p in files if p is not None),None)
        if source is None:
            self.cache_key=None
            return 0.
        try:
            stat=source.stat()
            key=(str(source),stat.st_size,stat.st_mtime_ns)
        except OSError:return 0.
        if key!=self.cache_key:
            self.cache_key=key
            self.duration=0.
        if self.duration<=0:
            for part,path in files:
                if path==source:
                    value=self._rows()[part]["wave"].duration_seconds
                    if value>0:self.duration=float(value)
                    break
            if self.duration<=0:
                from audio_import import probe_audio
                try:self.duration=max(0.,float(probe_audio(source)["duration"]))
                except (OSError,ValueError,KeyError,TypeError):pass
        return self.duration

    def start(self):
        if self.active:return
        self.active=True
        self.panel.show()
        for part,row in self._rows().items():
            wave=row["wave"]
            wave.setProperty("showPlaybackCursor",True)
            wave.setFixedHeight(34)
            wave.setCursor(Qt.PointingHandCursor)
            wave.installEventFilter(self)
        self.refresh()
        self.timer.start()

    def stop(self):
        if not self.active:return
        self.active=False
        self.drag_part=None
        self.timer.stop()
        for row in self._rows().values():
            wave=row["wave"]
            wave.removeEventFilter(self)
            wave.setProperty("showPlaybackCursor",False)
            wave.setFixedHeight(20)
            wave.unsetCursor()
            wave.set_cursor(0.)
        self.panel.hide()

    def refresh(self):
        if not self.active:return
        duration=self._duration()
        player=self.home.player
        origin=Path(player.current_file).resolve() if player.current_file else None
        matched=bool(origin and any(origin==self._source(part) for part in self._rows()))
        if matched and player._duration_ms>0:
            # Posición del sonido REAL (sin contador animado independiente).
            duration=player._duration_ms/1000
            position=max(0.,min(duration,player._position()/1000))
        else:
            position=0.
        if self.scale.dragging:
            self.fraction=self.scale.fraction
            position=self.fraction*duration
        elif self.drag_part is not None:
            position=self.fraction*duration
        else:
            self.fraction=position/duration if duration else 0.
        self.scale.set_state(duration,self.fraction)
        self.counter.setText(f"{clock(position,True)} / {clock(duration,True)}")
        for row in self._rows().values():
            wave=row["wave"]
            if wave.cursor!=self.fraction:wave.set_cursor(self.fraction)

    def preview_fraction(self,fraction):
        self.fraction=max(0.,min(1.,float(fraction)))
        self.refresh()

    def seek(self,fraction,part=None):
        fraction=max(0.,min(1.,float(fraction)))
        transport=self._transport()
        if part is None:
            part=transport.track_select.currentText() if transport and transport.track_select else None
        selected=self._source(part)
        if selected is None:return False
        if transport and transport.track_select:
            transport.track_select.setCurrentText(part)
        player=self.home.player
        if player.current_file!=str(selected):
            if not player.load(selected,autoplay=False):return False
            player.slider.setValue(round(fraction*player._duration_ms))
            player.drag_finish()
            player.play_pause()
        elif player._duration_ms:
            player.slider.setValue(round(fraction*player._duration_ms))
            player.drag_finish()
        self.fraction=fraction
        self.refresh()
        return True

    def eventFilter(self,watched,event):
        if not self.active:return False
        part=next((name for name,row in self._rows().items()
                   if watched is row["wave"]),None)
        if part is None:return False
        if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
            if self._source(part) is None:return False
            self.drag_part=part
            self.fraction=max(0.,min(1.,event.position().x()/max(1.,watched.width())))
            self.refresh()
            return True
        if event.type()==QEvent.MouseMove and self.drag_part==part:
            self.fraction=max(0.,min(1.,event.position().x()/max(1.,watched.width())))
            self.refresh()
            return True
        if event.type()==QEvent.MouseButtonRelease and self.drag_part==part:
            self.fraction=max(0.,min(1.,event.position().x()/max(1.,watched.width())))
            self.drag_part=None
            self.seek(self.fraction,part)
            return True
        return False
