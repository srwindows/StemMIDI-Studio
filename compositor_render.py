"""Exportación profesional básica de mezcla estéreo: MIDI→FluidSynth y
audio→FFmpeg, recortes, posiciones, M/S, volumen y panorámica reales.
La renderización se ejecuta en hilo Qt sin congelar la interfaz.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from PySide6.QtCore import QThread,Signal

def _run_cancelable(args,stop_check,timeout):
    """No dejar FluidSynth/FFmpeg funcionando después de Cancelar.

    El proceso externo se controla cada 150 ms sin bloquear el hilo Qt.
    """
    import time
    process=subprocess.Popen(args,stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,text=True)
    started=time.monotonic()
    try:
        while True:
            if stop_check():
                raise InterruptedError("Render cancelado por el usuario")
            if time.monotonic()-started>timeout:
                raise TimeoutError("Tiempo máximo del render excedido")
            try:
                out,err=process.communicate(timeout=.15)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise RuntimeError((err or out)[-900:] or
                               f"Proceso terminado con error {process.returncode}")
        return out,err
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill();process.communicate()
        raise


def render(session,destination,stop_check=lambda:False,meter_file=None):
    tracks=session.audible()
    clips=[(t,c) for t in tracks for c in t["clips"]]
    if not clips:raise ValueError("No hay clips audibles")
    if len(clips)>160:raise ValueError("Demasiados clips para una mezcla")
    target=Path(destination)
    target.parent.mkdir(parents=True,exist_ok=True)
    sf2=Path(os.environ.get("STEMMIDI_COMPOSITOR_SF2",
                             "/usr/share/sounds/sf2/FluidR3_GM.sf2"))
    with tempfile.TemporaryDirectory(prefix="compositor_render_") as td:
        temporary=Path(td)
        inputs=[]
        filters=[]
        out=[]
        track_groups={}
        for index,(track,clip) in enumerate(clips):
            if stop_check():raise InterruptedError("Render cancelado")
            source=session.file_for(clip)
            if not source.is_file():raise FileNotFoundError(source)
            if track["type"]=="midi":
                if not sf2.is_file():raise FileNotFoundError(
                    "Falta SoundFont: "+str(sf2))
                synth=temporary/f"midi_{index:03}.wav"
                args=["fluidsynth","-ni","-g","0.75","-F",str(synth),
                      "-r","44100",str(sf2),str(source)]
                _run_cancelable(args,stop_check,300)
                source=synth
            inputs.extend(["-i",str(source)])
            # El fragmento de clip permanece en segundos musicales reales.
            # El BPM convierte la posición en compases a tiempo absoluto;
            # no estira ni deforma una grabación original.
            start=clip["beat"]*60./session.state["bpm"]
            offset=clip["offset"]
            duration=clip["duration"]
            pan=track["pan"]
            gain=track["volume"]*float(clip.get("gain",1.))
            fade_in=max(0.,min(duration,float(clip.get("fade_in",0.))))
            fade_out=max(0.,min(duration,float(clip.get("fade_out",0.))))
            left=gain*min(1.,1.-pan)
            right=gain*min(1.,1.+pan)
            delayed=max(0,round(start*1000))
            output=f"x{index}"
            volume_fades=(
                (f"afade=t=in:st=0:d={fade_in:.6f},"
                 if fade_in>=.01 else "")+
                (f"afade=t=out:st={max(0.,duration-fade_out):.6f}:"
                 f"d={fade_out:.6f}," if fade_out>=.01 else ""))
            filters.append(
                f"[{index}:a]aresample=44100,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"atrim=start={offset:.6f}:duration={duration:.6f},"
                f"asetpts=PTS-STARTPTS,{volume_fades}"
                f"pan=stereo|c0={left:.6f}*c0|c1={right:.6f}*c1,"
                f"adelay={delayed}|{delayed}[{output}]")
            track_groups.setdefault(track["id"],[]).append(f"[{output}]")
        # Agrupar clips de la misma pista para obtener señal pos-fader
        # MIDI/audio con posición temporal, recortes, fundidos y panorama.
        meter_labels={}
        for index,(track_id,labels) in enumerate(track_groups.items()):
            if len(labels)>1:
                label=f"[bus{index}]"
                filters.append("".join(labels)+f"amix=inputs={len(labels)}:"
                               f"normalize=0:dropout_transition=0{label}")
            else:
                label=labels[0]
            if meter_file is not None:
                main=f"[busmain{index}]"
                vu=f"[busvu{index}]"
                filters.append(f"{label}asplit=2{main}{vu}")
                meter_labels[track_id]=vu
                out.append(main)
            else:
                out.append(label)
        if len(out)==1:
            if meter_file is not None:
                filters.append(
                    f"{out[0]}alimiter=limit=0.95,"
                    "asplit=2[mix][vumaster]")
            else:
                filters.append(f"{out[0]}alimiter=limit=0.95[mix]")
        else:
            if meter_file is not None:
                filters.append(
                    "".join(out)+f"amix=inputs={len(out)}:normalize=0:"
                    "dropout_transition=0,alimiter=limit=0.95,"
                    "asplit=2[mix][vumaster]")
            else:
                filters.append(
                    "".join(out)+f"amix=inputs={len(out)}:normalize=0:"
                    "dropout_transition=0,alimiter=limit=0.95[mix]")
        if meter_file is not None:
            meter_labels["__master__"]="[vumaster]"
        intermediate=temporary/"mezcla.wav"
        cmd=["ffmpeg","-hide_banner","-nostdin","-v","error","-y",
             *inputs,"-filter_complex",";".join(filters),
             "-map","[mix]","-c:a","pcm_s24le","-ar","44100",
             str(intermediate)]
        meter_wavs={}
        if meter_file is not None:
            for index,(track_id,label) in enumerate(meter_labels.items()):
                filename=temporary/f"medidor_{index}.wav"
                meter_wavs[track_id]=filename
                cmd.extend(["-map",label,"-ac","2","-ar","22050",
                            "-c:a","pcm_s16le",str(filename)])
        _run_cancelable(cmd,stop_check,600)
        if stop_check():raise InterruptedError("Render cancelado")
        if not intermediate.is_file() or intermediate.stat().st_size<100:
            raise RuntimeError("Mezcla vacía")
        # Siempre reemplazar atómicamente. No tocar ningún clip original.
        part=target.with_name("."+target.name+".part")
        shutil.copyfile(intermediate,part)
        part.replace(target)
        if meter_file is not None:
            if stop_check():raise InterruptedError("Render cancelado")
            from compositor_meters import make_meter_json
            make_meter_json(
                meter_file,meter_wavs,
                {t["id"]:t["name"] for t in tracks})
    return target


class MixWorker(QThread):
    finished_mix=Signal(str,bool,str)
    def __init__(self,session,destination,preview=False,parent=None,
                 meter_file=None):
        super().__init__(parent)
        from copy import deepcopy
        from compositor_session import CompositorSession
        self.snapshot=CompositorSession()
        self.snapshot.project=session.project
        self.snapshot.state=deepcopy(session.state)
        self.output=Path(destination)
        self.preview=preview
        self.meter_file=meter_file
        self.cancel_requested=False

    def cancel(self):
        self.cancel_requested=True

    def run(self):
        try:
            result=render(
                self.snapshot,self.output,
                stop_check=lambda:self.cancel_requested,
                meter_file=self.meter_file)
            self.finished_mix.emit(str(result),self.preview,"")
        except Exception as error:
            self.finished_mix.emit("",self.preview,str(error))
