"""Medición de audio de las salidas reales del render, no animaciones ficticias.

En el render se extraen reducciones PCM de cada bus pos-fader y del
máster pos-limitador. Se calcula RMS/peak estéreo cada ~40 ms para
reproducirlos sincronizados con la posición de escucha del proyecto.
"""
from __future__ import annotations
from array import array
from pathlib import Path
import json
import math
import os
import sys
import wave
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter,QFont
from PySide6.QtWidgets import QWidget


def analyze_pcm(path,frame_ms=40):
    """Valores normalizados [rmsL,rmsR,peakL,peakR] sin cargar todo el WAV."""
    values=[]
    with wave.open(str(path),"rb") as reader:
        channels=reader.getnchannels()
        if reader.getsampwidth()!=2 or channels!=2:
            raise ValueError("El bus de medición debe ser PCM estéreo de 16 bits")
        block=max(1,int(reader.getframerate()*frame_ms/1000))
        max_frames=reader.getframerate()*60*60
        frames_read=0
        while frames_read<max_frames:
            data=reader.readframes(block)
            if not data:break
            frames=len(data)//(2*channels)
            if frames==0:break
            samples=array("h")
            samples.frombytes(data)
            if sys.byteorder!="little":samples.byteswap()
            l=samples[0::2];r=samples[1::2]
            def rms(xs):
                if not xs:return (0.,0.)
                total=sum(int(x)*int(x) for x in xs)
                return (math.sqrt(total/len(xs))/32768.,
                        max(abs(x) for x in xs)/32768.)
            lr,lp=rms(l);rr,rp=rms(r)
            values.append([round(lr,5),round(rr,5),
                           round(lp,5),round(rp,5)])
            frames_read+=frames
    return values


def levels_at(frames,seconds,frame_ms=40):
    if not frames:return (0.,0.,0.,0.)
    index=max(0,min(len(frames)-1,int(max(0,seconds)*1000/frame_ms)))
    return tuple(float(v) for v in frames[index])


def make_meter_json(destination,buses,track_titles):
    """buses: track-id -> fichero PCM, incl. clave __master__."""
    result={"version":1,"frame_ms":40,"tracks":{}}
    for key,path in buses.items():
        result["tracks"][key]=analyze_pcm(path)
    result["track_names"]=track_titles
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    part=destination.with_suffix(destination.suffix+".part")
    part.write_text(json.dumps(result,separators=(",",":")),encoding="utf8")
    os.replace(part,destination)
    return result


from studio_vu_unified import Ballistics,db_fraction,draw_stereo

class LevelMeter(QWidget):
    """VU L/R del Compositor: geometría original, patrón Monitor único."""
    def __init__(self,parent=None,master=False):
        super().__init__(parent)
        self.master=master
        self.levels=(0.,0.,0.,0.)
        self._ballistics=Ballistics(2)
        self.setObjectName("composerMasterMeter" if master else "composerTrackMeter")
        self.setMinimumWidth(45 if not master else 125)
        self.setMaximumWidth(64 if not master else 156)
        self.setFixedHeight(34 if master else 24)
        self.setToolTip("RMS/pico PCM real L/R · diseño y balística Monitor / Grabación · −60..0 dBFS")
    def setLevels(self,values):
        parsed=tuple(max(0.,min(1.5,float(v))) for v in values)
        if parsed!=self.levels:
            self.levels=parsed
            self._ballistics.feed(parsed[:2],parsed[2:])
            self.update()
    @staticmethod
    def db_to_fraction(value):return db_fraction(value)
    def paintEvent(self,event):
        painter=QPainter(self)
        draw_stereo(painter,self.rect(),self._ballistics.shown,
                    self._ballistics.held,("L","R"),True)
        painter.end()
