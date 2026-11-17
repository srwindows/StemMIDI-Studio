"""Información técnica real del archivo de Vista de audio, sin botones de transporte duplicados."""
from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel


def fmt_clock(seconds):
    seconds=max(0,int(seconds))
    h,rem=divmod(seconds,3600)
    m,s=divmod(rem,60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_audio_info(stream,format_data,file_size):
    """Mostrar tasa real de bits y media de bytes/s, no confundir ambas."""
    codec=str(stream.get("codec_name") or "?").upper()
    rate=stream.get("sample_rate") or "?"
    channels=stream.get("channels") or "?"
    duration=float(format_data.get("duration") or stream.get("duration") or 0)
    bits=(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample"))
    bit_rate=stream.get("bit_rate") or format_data.get("bit_rate")
    try:kbps=f"{int(bit_rate)/1000:.0f} kb/s"
    except (ValueError,TypeError):kbps="sin dato"
    average=f"{file_size/duration:,.0f} B/s" if duration>0 else "sin dato"
    precision=f" · {bits} bits" if bits and str(bits)!="0" else ""
    return (f"{codec} · {rate} Hz · {channels} canales{precision}",
            f"Tasa: {kbps} · Promedio archivo: {average}",
            duration)


class WaveAudioDetails(QFrame):
    def __init__(self,home,parent=None):
        super().__init__(parent)
        self.home=home
        self.setObjectName("waveTechnicalInfo")
        self.setStyleSheet("QFrame#waveTechnicalInfo{background:#041b43;border:1px solid #2788d0;"
                           "border-radius:5px;} QFrame#waveTechnicalInfo QLabel{color:#bfefff;}")
        grid=QGridLayout(self)
        grid.setContentsMargins(8,3,8,4)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        self.file_line=QLabel("Archivo: sin seleccionar",self)
        self.format_line=QLabel("Formato: —",self)
        self.rate_line=QLabel("Tasa: —",self)
        self.time_line=QLabel("Tiempo: 00:00 / 00:00",self)
        self.scale_line=QLabel("Escala: —",self)
        for i,w in enumerate((self.file_line,self.format_line,self.rate_line,
                              self.time_line,self.scale_line)):
            w.setToolTip("Información obtenida del audio real, sin procesarlo.")
            grid.addWidget(w,i//2,i%2)
        self._source=None
        self._stamp=None
        self._duration=0.
        self._process=QProcess(self)
        self._process.finished.connect(self._finished)
        self._ticker=QTimer(self)
        self._ticker.setInterval(250)
        self._ticker.timeout.connect(self.refresh)

    def start(self):
        self._ticker.start()
        self.refresh()

    def stop(self):
        self._ticker.stop()
        if self._process.state()!=QProcess.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)

    def refresh(self):
        path=self.home._source_for_wave(self.home._gather_files())
        path=Path(path).resolve() if path and Path(path).is_file() else None
        try:
            stat=path.stat() if path else None
            stamp=(str(path),stat.st_size,stat.st_mtime_ns) if stat else None
        except OSError:stamp=None
        if stamp!=self._stamp:
            self._stamp=stamp
            self._source=path if stamp else None
            self._duration=0.
            self.file_line.setText("Archivo: "+(path.name if path else "sin seleccionar"))
            self.format_line.setText("Formato: obteniendo metadatos…" if path else "Formato: —")
            self.rate_line.setText("Tasa: —")
            if self._process.state()!=QProcess.NotRunning:
                self._process.kill()
                self._process.waitForFinished(1000)
            if path is not None:
                self._process.start("ffprobe",[
                    "-v","error","-show_entries",
                    "stream=codec_type,codec_name,sample_rate,channels,bits_per_raw_sample,"
                    "bits_per_sample,bit_rate,duration:format=duration,bit_rate",
                    "-of","json",str(path)])
        player=self.home.player
        same=bool(path and player.current_file and
                  Path(player.current_file).resolve()==path)
        total=(player._duration_ms/1000 if same and player._duration_ms>0
               else self._duration or self.home.wave.duration_seconds)
        pos=player._position()/1000 if same and player._duration_ms else 0
        self.time_line.setText(f"Tiempo: {fmt_clock(pos)} / {fmt_clock(total)}")
        wave=self.home.wave
        start=wave.view_start*total
        end=min(total,(wave.view_start+1/max(1,wave.zoom_factor))*total)
        self.scale_line.setText(f"Escala: {fmt_clock(start)}–{fmt_clock(end)}"
                                f" · zoom ×{wave.zoom_factor}")

    def _finished(self,code,status):
        if not self._source or code!=0:return
        try:
            data=json.loads(bytes(self._process.readAllStandardOutput()).decode())
            stream=next(s for s in data.get("streams",[])
                        if s.get("codec_type")=="audio")
            left,right,duration=format_audio_info(stream,data.get("format",{}),
                                                     self._source.stat().st_size)
        except (OSError,ValueError,KeyError,StopIteration,TypeError):
            self.format_line.setText("No se pueden leer los metadatos")
            return
        self.format_line.setText(left)
        self.rate_line.setText(right)
        self._duration=duration
        self.refresh()
