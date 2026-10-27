"""VU para preescuchas: señal PCM real decodificada en segundo plano.

La medición calcula RMS por ventanas de 100 ms. No anima ni inventa datos;
se mantiene en cero cuando el archivo no está cargado o está detenido.
No modifica los originales, no abre dispositivos y limita el análisis a 30 min.
"""
from __future__ import annotations
import array
import math
import subprocess
import sys
import threading
from pathlib import Path
from PySide6.QtCore import QTimer
from widgets import StereoMeter

class MeasuredPlaybackVU:
    def __init__(self,player,layout):
        self.player=player
        self.meter=StereoMeter(player)
        self.meter.setMinimumHeight(53)
        self.meter.setMaximumHeight(69)
        self.meter.setToolTip("VU de preescucha: RMS L/R medido del audio real, muestreo de monitorización.")
        layout.addWidget(self.meter)
        self.levels=[]
        self.generation=0
        self.running_process=None
        self.timer=QTimer(player)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.update)
        self.timer.start()
    def load(self,path):
        self.generation+=1
        gen=self.generation
        self.levels=[]
        self.meter.set_levels(0,0,0,0)
        old=self.running_process
        if old is not None and old.poll() is None:
            try:old.terminate()
            except (OSError,ProcessLookupError):pass
        candidate=Path(path)
        if not candidate.is_file():return
        def analyze():
            proc=None
            try:
                proc=subprocess.Popen(
                    ["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
                     "-i",str(candidate),"-map","0:a:0","-t","1800",
                     "-ac","2","-ar","24000","-f","f32le","pipe:1"],
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                self.running_process=proc
                block=19200  # 100 ms, 24000 Hz, two channels, float32
                pending=b""
                while gen==self.generation:
                    data=proc.stdout.read(block-len(pending))
                    if not data:break
                    pending+=data
                    if len(pending)!=block:continue
                    floats=array.array('f')
                    floats.frombytes(pending)
                    if sys.byteorder!="little":floats.byteswap()
                    sums=[0.0,0.0];peaks=[0.0,0.0]
                    for n in range(0,len(floats),2):
                        for ch in (0,1):
                            value=abs(floats[n+ch])
                            sums[ch]+=value*value
                            peaks[ch]=max(peaks[ch],value)
                    count=len(floats)//2
                    rms=(min(1.0,math.sqrt(sums[0]/count)),
                         min(1.0,math.sqrt(sums[1]/count)))
                    if gen!=self.generation:break
                    self.levels.append((rms[0],rms[1],
                                        min(1.,peaks[0]),min(1.,peaks[1])))
                    pending=b""
            except (OSError,ValueError,IndexError):
                return
            finally:
                if proc is not None:
                    if proc.poll() is None:
                        proc.terminate()
                    try:proc.wait(timeout=.5)
                    except subprocess.TimeoutExpired:proc.kill()
                    if self.running_process is proc:self.running_process=None
        threading.Thread(target=analyze,daemon=True,name="StemMIDI-PreviewVU").start()
    def update(self):
        player=self.player
        playing=bool(player._qt_active or player._play_process is not None)
        if not playing or player._paused or not self.levels:
            self.meter.set_levels(0,0,0,0)
            return
        second=max(0,player._position())/1000
        index=min(len(self.levels)-1,int(second*10))
        self.meter.set_levels(*self.levels[index])
    def stop(self):
        self.generation+=1
        old=self.running_process
        if old is not None and old.poll() is None:
            try:old.terminate()
            except (OSError,ProcessLookupError):pass
        self.running_process=None
        self.levels=[]
        self.meter.set_levels(0,0,0,0)
