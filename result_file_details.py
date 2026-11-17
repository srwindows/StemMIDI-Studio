"""Ficha técnica de resultados, con metadatos leídos del archivo real.

No modifica fuentes; los campos desconocidos se indican, nunca se inventan.
"""
from __future__ import annotations
import datetime
import json
import subprocess
from pathlib import Path
from PySide6.QtCore import QObject,Signal
import threading

MIDI={".mid",".midi",".kar"}
AUDIO={".wav",".flac",".mp3",".ogg",".m4a",".aac",".wma",".aif",".aiff"}

def _size(number):
    for unit in ("B","KiB","MiB","GiB","TiB"):
        if number<1024 or unit=="TiB":return f"{number:.1f} {unit}"
        number/=1024

def _duration(sec):
    if sec is None:return "Sin dato"
    try:
        v=max(0.,float(sec))
        return f"{int(v//3600):02d}:{int(v%3600//60):02d}:{int(v%60):02d}.{int(v%1*1000):03d}"
    except (ValueError,TypeError,OverflowError):return "Sin dato"

def describe(path,project=None,category=None):
    """Generar texto con información confirmada; sin analizar el audio en GUI."""
    path=Path(path).resolve(strict=True)
    st=path.stat()
    lines=[
        "ARCHIVO SELECCIONADO",
        f"Nombre: {path.name}",
        f"Tipo: {'Secuencia MIDI' if path.suffix.lower() in MIDI else 'Archivo de audio'}",
        f"Pista o instrumento: {category or 'No identificado'}",
        f"Formato: {path.suffix.lstrip('.').upper() or 'Desconocido'}",
        f"Tamaño: {_size(st.st_size)} ({st.st_size:,} bytes)",
        f"Última modificación: {datetime.datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M:%S')}",
    ]
    if project:
        root=Path(project).resolve()
        try:
            rel=path.relative_to(root)
            lines.extend([f"Carpeta del proyecto: {rel.parent}",
                          "Estado: Temporal / sin confirmar" if
                          "temporales" in rel.parts else
                          "Estado: Archivo del proyecto"])
        except ValueError:
            lines.append("Estado: Archivo externo al proyecto")
    lines.extend([f"Ruta completa: {path}",""])
    if path.suffix.lower() in MIDI:
        import mido
        midi=mido.MidiFile(path)
        notes=[];channels=set();programs=[];tempos=[];meters=[]
        for track in midi.tracks:
            for msg in track:
                if msg.type=="note_on" and msg.velocity>0:
                    notes.append((msg.note,msg.velocity))
                    channels.add(msg.channel+1)
                elif msg.type=="program_change":
                    programs.append((msg.channel+1,msg.program+1))
                elif msg.type=="set_tempo":
                    tempos.append(msg.tempo)
                elif msg.type=="time_signature":
                    meters.append(f"{msg.numerator}/{msg.denominator}")
        lines.extend(["DATOS MIDI",
           f"Duración: {_duration(midi.length)}",
           f"Formato SMF: tipo {midi.type}",
           f"Pistas: {len(midi.tracks)}",
           f"Resolución: {midi.ticks_per_beat} pulsos por negra",
           f"Notas Note On: {len(notes)}",
           f"Canales MIDI utilizados: {', '.join(map(str,sorted(channels))) if channels else 'Ninguno'}",
           f"Rango de notas: {min(n[0] for n in notes)}–{max(n[0] for n in notes)}" if notes else
           "Rango de notas: Sin notas",
           f"Velocidad MIDI mínima/máxima: {min(n[1] for n in notes)} / {max(n[1] for n in notes)}" if notes else
           "Velocidad MIDI: Sin notas",
           f"Tempo inicial: {60000000/(tempos[0] if tempos else 500000):.2f} BPM"+
             (" (por defecto MIDI)" if not tempos else ""),
           f"Cambios de tempo: {len(tempos)}",
           f"Compases declarados: {', '.join(dict.fromkeys(meters)) if meters else 'Sin dato'}",
           f"Programas MIDI declarados: {', '.join(f'CH{c}: {p}' for c,p in dict.fromkeys(programs)) if programs else 'Sin programa especificado'}",
           "Nivel de audio: requiere sintetizar el MIDI; las velocidades no equivalen a dBFS.",
        ])
    elif path.suffix.lower() in AUDIO:
        info=subprocess.run(["ffprobe","-v","error","-show_entries",
            "stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,"
            "sample_fmt,bits_per_raw_sample,bits_per_sample,bit_rate:format=duration,"
            "format_name,bit_rate","-of","json",str(path)],
            capture_output=True,text=True,timeout=12,check=False)
        if info.returncode!=0:raise ValueError("No se pudieron leer datos de FFprobe")
        parsed=json.loads(info.stdout)
        streams=[s for s in parsed.get("streams",[]) if s.get("codec_type")=="audio"]
        fmt=parsed.get("format",{})
        lines.extend(["DATOS DE AUDIO",
            f"Duración: {_duration(fmt.get('duration'))}",
            f"Contenedor: {fmt.get('format_name') or 'Sin dato'}",
            f"Flujos de audio: {len(streams)}"])
        for i,stream in enumerate(streams,1):
            lines.extend([
                f"Flujo {i} · Códec: {stream.get('codec_name') or 'Sin dato'}",
                f"Frecuencia: {stream.get('sample_rate') or 'Sin dato'} Hz",
                f"Canales: {stream.get('channels') or 'Sin dato'}",
                f"Distribución: {stream.get('channel_layout') or 'Sin dato'}",
                f"Formato de muestras: {stream.get('sample_fmt') or 'Sin dato'}",
                f"Profundidad de bits: {stream.get('bits_per_raw_sample') or stream.get('bits_per_sample') or 'Sin dato'}",
                f"Tasa del flujo: {round(int(stream['bit_rate'])/1000)} kb/s" if stream.get("bit_rate") else
                "Tasa del flujo: Sin dato",
            ])
        if fmt.get("bit_rate"):
            lines.append(f"Tasa media del archivo: {int(fmt['bit_rate'])/1000:.1f} kb/s")
        lines.append("Nivel reproducido: VU L/R medido sobre el audio decodificado; el volumen del reproductor se aplica.")
    else:lines.append("Formato no analizable: se muestran datos del archivo.")
    return "\n".join(lines)

class ResultInfoReader(QObject):
    ready=Signal(int,str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self._generation=0
    def request(self,path,project=None,category=None):
        self._generation+=1
        generation=self._generation
        if path is None:return generation
        def work():
            try:info=describe(path,project,category)
            except Exception as exc:info="No se pudieron obtener metadatos técnicos: "+str(exc)
            self.ready.emit(generation,info)
        threading.Thread(target=work,name="StemMIDI-ResultInfo",daemon=True).start()
        return generation
    def clear(self):
        self._generation+=1
    def is_current(self,generation):
        return generation==self._generation
