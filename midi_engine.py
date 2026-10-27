#!/usr/bin/env python3
"""Motor local de transcripción audio -> MIDI multipista.

Basic Pitch ONNX: detección polifónica de notas para instrumentos tonales.
Batería: estimación de golpes y categoría aproximada por energía espectral.
Es una transcripción, no la recuperación de eventos MIDI originales.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import warnings
import signal
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("OMP_NUM_THREADS", "6")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
warnings.filterwarnings("ignore", category=FutureWarning)
logging.disable(logging.WARNING)

import librosa
import mido
import numpy as np
import pretty_midi
from scipy.signal import find_peaks

from audio_import import MEDIA_EXTENSIONS, probe_audio, normalize_command, supported_candidate
from stem_detection import is_separated_stem
from tempo_precision import analyze as analyze_tempo
from midi_refine import refine_events, note_at_retrigger
from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import Model, predict

ROOT = Path(__file__).resolve().parent
ACTIVE_CHILD = None


def cancel_parent(sig, frame):
    global ACTIVE_CHILD
    if ACTIVE_CHILD is not None and ACTIVE_CHILD.poll() is None:
        try:
            os.killpg(ACTIVE_CHILD.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    raise SystemExit(130)

signal.signal(signal.SIGTERM, cancel_parent)
OUTPUT = ROOT / "midi_generados"
AUDIO_EXTENSIONS = {"." + ext for ext in MEDIA_EXTENSIONS}
PROGRAMS = {
    "vocals": (53, "Voz"),
    "vocal": (53, "Voz"),
    "instrumental": (0, "Instrumental"),
    "drums": (0, "Batería"),
    "bateria": (0, "Batería"),
    "bass": (33, "Bajo"),
    "guitar": (24, "Guitarra"),
    "piano": (0, "Piano"),
    "other": (0, "Otros instrumentos"),
    "izquierdo": (0, "Canal izquierdo"),
    "derecho": (0, "Canal derecho"),
}


def emit(stage, **data):
    print("MIDI_PROGRESS " + json.dumps({"stage": stage, **data}, ensure_ascii=False), flush=True)


def infer_instrument(filepath: Path):
    stem = filepath.stem.lower()
    # En stems de IA el tipo está entre paréntesis: el título de la canción
    # puede contener 'piano', 'bass' o 'drums' y NO debe definir el instrumento.
    tagged = re.findall(r"\((vocals|instrumental|drums|bass|guitar|piano|other)\)", stem)
    if tagged:
        key = tagged[-1]
        if key == "other" and "roformer" in stem:
            key = "instrumental"
        program,name = PROGRAMS[key]
        return ("drums" if key=="drums" else key, program, name)
    for key, (program, name) in PROGRAMS.items():
        if key in stem:
            if key == "other" and "roformer" in stem:
                return ("instrumental", 0, "Instrumental")
            if key in ("drums", "bateria"):
                return ("drums", 0, "Batería")
            return (key, program, name)
    return ("melodic", 0, filepath.stem[:40])


def list_inputs(items, folder):
    result = []
    seen = set()
    for item in items:
        candidate = Path(item).expanduser().resolve()
        if not candidate.is_file():
            raise ValueError(f"Archivo de audio inválido: {candidate}")
        probe_audio(candidate)
        if candidate not in seen:
            result.append(candidate)
            seen.add(candidate)
    if folder:
        directory = Path(folder).expanduser().resolve()
        if not directory.is_dir():
            raise ValueError(f"No existe carpeta de pistas: {directory}")
        for p in sorted(directory.iterdir()):
            if supported_candidate(p):
                if p.name.lower().startswith(("mezcla_", "mezcla_previa_", "_")):
                    continue
                try:
                    probe_audio(p)
                except ValueError:
                    emit("info", message=f"Se omite archivo no decodificable: {p.name}")
                    continue
                if p.resolve() not in seen:
                    result.append(p.resolve())
                    seen.add(p.resolve())
    if not result:
        raise ValueError("No hay archivos de audio seleccionados")
    if len(result) > 16:
        raise ValueError("Máximo 16 pistas por proyecto MIDI General MIDI")
    return result


def estimate_bpm(path):
    info=analyze_tempo(path)
    if info.get("bpm") is None:
        return 120.,False,info
    return float(info["bpm"]), bool(info["reliable"]), info


def profile_settings(kind, opts):
    if not opts.get("automatic", True):
        return (opts["onset"], opts["frame"], opts["min_length_ms"], opts["min_pitch"], opts["max_pitch"])
    if kind in ("bass",):
        base=(.42, .26, 135, 28, 76)
    elif kind in ("vocals", "vocal"):
        base=(.48, .27, 150, 43, 96)
    elif kind in ("piano",):
        base=(.54, .30, 98, 24, 108)
    elif kind in ("guitar",):
        base=(.47, .28, 110, 35, 96)
    else:
        base=(.50, .31, 130, 30, 100)
    onset,frame,length,low,high=base
    quality=opts.get("precision_profile","balanced")
    if quality=="strict":
        onset=min(.93,onset+.10)
        frame=min(.90,frame+.08)
        length+=45
    elif quality=="sensitive":
        onset=max(.10,onset-.09)
        frame=max(.10,frame-.06)
        length=max(40,length-35)
    # Correcciones relativas a los umbrales instrumentales de referencia.
    onset=float(np.clip(onset+(float(opts.get("onset",.5))-.5),.1,.95))
    frame=float(np.clip(frame+(float(opts.get("frame",.3))-.3),.1,.9))
    length=max(35,int(length+(int(opts.get("min_length_ms",120))-120)))
    if "min_pitch" in opts and int(opts["min_pitch"])!=28:
        low=max(21,min(108,int(opts["min_pitch"])))
    if "max_pitch" in opts and int(opts["max_pitch"])!=100:
        high=max(21,min(108,int(opts["max_pitch"])))
    if high<low:high=low
    return onset,frame,length,low,high


def midi_frequency(pitch):
    return 440.0 * 2.0 ** ((pitch-69) / 12.0)


def snap_time(seconds, bpm, grid, offset=0.):
    if grid in ("off", "ninguna", ""):
        return float(seconds)
    denominator = {"1/4": 1, "1/8": 2, "1/16": 4, "1/32": 8}.get(grid, 0)
    if denominator == 0:
        return float(seconds)
    unit = (60.0 / bpm) / denominator
    return max(0., round((seconds-offset)/unit) * unit+offset)


def clean_events(raw, min_len_ms, min_pitch, max_pitch, bpm, quantize,
                 preserve_velocity=False, velocity_floor=0, merge_gap_ms=0,
                 time_shift_ms=0, grid_offset_ms=0, attacks_by_pitch=None):
    notes = []
    for onset, offset, pitch, amp, _bend in raw:
        pitch = int(pitch)
        if not min_pitch <= pitch <= max_pitch:
            continue
        onset = float(onset)
        offset = float(offset)
        if offset - onset < min_len_ms / 1000.0:
            continue
        onset = snap_time(onset+time_shift_ms/1000., bpm, quantize,
                          grid_offset_ms/1000.)
        offset = snap_time(offset+time_shift_ms/1000., bpm, quantize,
                           grid_offset_ms/1000.)
        if offset <= onset:
            offset = onset + (60.0 / bpm / 8.0 if quantize != "off" else .05)
        velocity = (int(np.clip(round(float(amp)*127),1,127)) if preserve_velocity
                    else int(np.clip(45 + float(amp) * 70,35,127)))
        if velocity < velocity_floor:
            continue
        notes.append((round(onset, 4), round(offset, 4), pitch, velocity))
    notes.sort(key=lambda x: (x[0], x[2], x[1]))
    # Evitar notas MIDI superpuestas de igual altura en un mismo canal.
    fixed = []
    last = {}
    for note in notes:
        a,b,p,v = note
        if p in last:
            k = last[p]
            prev = list(fixed[k])
            if a < prev[1]:
                if a <= prev[0]:
                    continue
                prev[1] = max(prev[0] + .02, a - .001)
                fixed[k] = tuple(prev)
        last[p] = len(fixed)
        fixed.append(note)
    if merge_gap_ms > 0:
        # Reconectar vibraciones separadas artificialmente por el detector
        # cuando no hay un segundo ataque claramente distinto.
        merged=[]
        previous_by_pitch={}
        for a,b,p,v in fixed:
            idx=previous_by_pitch.get(p)
            if idx is not None:
                prev=merged[idx]
                gap=a-prev[1]
                if (0 <= gap <= merge_gap_ms/1000. and abs(prev[3]-v)<=25
                        and not note_at_retrigger(attacks_by_pitch,p,a)):
                    merged[idx]=(prev[0],max(prev[1],b),p,
                                 round((prev[3]+v)*.5))
                    continue
            previous_by_pitch[p]=len(merged)
            merged.append((a,b,p,v))
        fixed=merged
    return sorted(fixed,key=lambda x:(x[0],x[2]))


def note_filter_options(opts,attacks=None):
    return {"attacks_by_pitch":attacks,
            "velocity_floor":int(opts.get("min_velocity",0)),
            "merge_gap_ms":int(opts.get("merge_gap_ms",0)),
            "time_shift_ms":int(opts.get("note_shift_ms",0)),
            "grid_offset_ms":int(opts.get("grid_offset_ms",0))}


def specialist_piano(path, opts, bpm):
    """Transkun (modelo específico de piano); MIDI fuente leído y limpiado."""
    global ACTIVE_CHILD
    # En tareas vinculadas, la salida real viene del proyecto activo.
    # La carpeta de trabajo del modelo tampoco debe escapar al proyecto.
    tempdir = Path(opts.get("output_dir") or (ROOT/"midi_generados"))/"_transkun_tmp"
    tempdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="piano_", dir=str(tempdir)) as job:
        output = Path(job) / "piano_transcrito.mid"
        command = [sys.executable, "-m", "transkun.transcribe",
                   str(path), str(output), "--device", "cpu"]
        ACTIVE_CHILD = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True,
                                        start_new_session=True)
        try:
            logs, _ = ACTIVE_CHILD.communicate()
            status = ACTIVE_CHILD.returncode
        finally:
            ACTIVE_CHILD = None
        if status or not output.is_file():
            raise RuntimeError(f"Transkun no consiguió transcribir el piano: {logs[-550:]}")
        midi = pretty_midi.PrettyMIDI(str(output))
        raw = []
        for instr in midi.instruments:
            if instr.is_drum:
                continue
            for n in instr.notes:
                raw.append((n.start, n.end, n.pitch, min(1., max(0.01, n.velocity/127)), None))
        if opts.get("automatic", True):
            min_length, lo, hi = 30, 21, 108
        else:
            min_length, lo, hi = opts["min_length_ms"], opts["min_pitch"], opts["max_pitch"]
        notes = clean_events(raw, min_length, lo, hi, bpm,
                            opts.get("quantize", "off"), preserve_velocity=True,
                            **note_filter_options(opts))
        return notes


def drum_events(path, opts, bpm, reference_audio=None):
    """Extracción heurística de golpes, con puerta contra artefactos de separación IA."""
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    if len(y) < 1024:
        return []
    if reference_audio and Path(reference_audio) != Path(path):
        reference, _ = librosa.load(str(reference_audio), sr=sr, mono=True)
        if reference.size:
            source_rms = float(np.sqrt(np.mean(reference**2)))
            drums_rms = float(np.sqrt(np.mean(y**2)))
            if source_rms > 0.00001 and drums_rms < 0.015 * source_rms:
                emit("info", message="La pista de batería es prácticamente silencio tras la separación IA; se omiten golpes espurios.")
                return []
    hop = 256
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    if not len(onset) or float(np.max(onset)) < 0.04:
        return []
    scale = max(float(np.quantile(onset, .90)), 1e-6)
    threshold = max(.06, min(.8, opts.get("drum_sensitivity", .35))) * scale
    peaks, _ = find_peaks(onset, prominence=threshold, distance=max(2,int(.065*sr/hop)))
    notes = []
    for i in peaks:
        start = float(librosa.frames_to_time(i, sr=sr, hop_length=hop))
        s = int(start*sr)
        piece = y[max(0,s-512):min(len(y),s+int(.10*sr))]
        if len(piece) < 300:
            continue
        nfft = 4096
        power = np.abs(np.fft.rfft(piece * np.hanning(len(piece)), n=nfft)) ** 2
        hz = np.fft.rfftfreq(nfft,1/sr)
        bass = float(power[(hz>=35)&(hz<150)].sum())
        mid = float(power[(hz>=150)&(hz<2000)].sum())
        high = float(power[(hz>=2000)&(hz<11000)].sum())
        if bass > mid * 1.8 and bass > high:
            pitch = 36  # General MIDI kick
        elif high > mid*1.7 and high > bass*4:
            pitch = 42  # General MIDI closed hi-hat
        else:
            pitch = 38  # General MIDI snare, provisional
        pos = snap_time(start+opts.get("note_shift_ms",0)/1000., bpm,
                        opts.get("quantize", "off"),
                        opts.get("grid_offset_ms",0)/1000.)
        duration = .10 if pitch != 42 else .06
        volume = float(np.sqrt(np.mean(piece**2)))
        vel = int(np.clip(55 + 60 * math.sqrt(max(0., volume)), 45, 120))
        if vel >= int(opts.get("min_velocity",0)):
            notes.append((round(pos,4),round(pos+duration,4),pitch,vel))
    return notes


def reject_silent_artifacts(path, notes):
    """Elimina detecciones de Basic Pitch en silencio digital casi absoluto.

    Umbral de comprobación: -68 dBFS RMS durante 350 ms alrededor
    del ataque; es conservador y se aplica sólo si la mezcla global
    tiene amplitud medible (> -55 dBFS). No afecta a originales,
    MIDI de batería, ni notas musicales en pasajes simplemente suaves.
    """
    if not notes:
        return notes, 0
    audio, sr = librosa.load(str(path), sr=11025, mono=True)
    if audio.size < sr or not np.all(np.isfinite(audio)):
        return notes, 0
    global_rms = float(np.sqrt(np.mean(audio.astype(np.float64)**2)))
    if global_rms < 10**(-55/20):
        return notes, 0
    limit = 10**(-68/20)
    retained = []
    dropped = 0
    for note in notes:
        onset = max(0.,float(note[0]))
        a = max(0,int((onset-.03)*sr))
        b = min(len(audio),int((onset+.32)*sr))
        chunk = audio[a:b]
        local_rms = float(np.sqrt(np.mean(chunk.astype(np.float64)**2))) if chunk.size else 0.
        if local_rms < limit:
            dropped += 1
        else:
            retained.append(note)
    return retained, dropped


def make_midi(data, bpm, out):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    tempo = mido.bpm2tempo(bpm)
    meta.append(mido.MetaMessage("track_name", name="Tempo y compás", time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    used_channels = [x for x in range(16) if x != 9]
    melodic_index = 0
    ticks_per_second = 480 * 1_000_000.0 / tempo
    total = 0
    for name, notes, program, is_drums in data:
        channel = 9 if is_drums else used_channels[melodic_index % len(used_channels)]
        if not is_drums:
            melodic_index += 1
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.MetaMessage("track_name", name=name, time=0))
        if not is_drums:
            track.append(mido.Message("program_change", program=program, channel=channel, time=0))
        events = []
        for onset, end, pitch, velocity in notes:
            start_tick = max(0,round(onset * ticks_per_second))
            end_tick = max(start_tick + 1,round(end * ticks_per_second))
            events.append((start_tick,1,int(pitch),int(velocity)))
            events.append((end_tick,0,int(pitch),0))
            total += 1
        # note-offs first at equal tick ensures no hanging/retrigger issues.
        events.sort(key=lambda a: (a[0],a[1],a[2]))
        prev = 0
        for tick,is_on,pitch,velocity in events:
            track.append(mido.Message("note_on" if is_on else "note_off",
                    note=pitch, velocity=velocity, channel=channel, time=tick-prev))
            prev = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(str(out))
    return total


def auto_separate_audio(source, opts, outdir, name):
    """Ejecuta separación IA previa opcional, sin alterar el audio original."""
    global ACTIVE_CHILD
    # Mantener el modelo original rápido; FT combina cuatro modelos
    # y supone una penalización sustancial de tiempo.
    model = {"4": "htdemucs.yaml", "6": "htdemucs_6s.yaml"}.get(
        str(opts.get("separation_stems","4")), "htdemucs.yaml")
    modeldir=ROOT/"modelos"
    sep=ROOT/"entorno_ia"/"bin"/"audio-separator"
    if not sep.is_file():
        raise FileNotFoundError("No se encuentra el motor de separación audio-separator")
    stems_dir = outdir / (name + "_STEMS_" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S"))
    stems_dir.mkdir(parents=True, exist_ok=True)
    emit("separating", model=model, folder=str(stems_dir))
    cmd=[sys.executable, str(sep), str(source),
         "--model_filename",model,
         "--model_file_dir",str(modeldir),
         "--output_dir",str(stems_dir),
         "--output_format","FLAC",
         "--demucs_shifts","1",
         "--demucs_overlap","0.25",
         "--log_level","warning"]
    ACTIVE_CHILD=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                  text=True,start_new_session=True,
                                  env={**os.environ,"TORCH_HOME":str(modeldir),
                                       "XDG_CACHE_HOME":str(ROOT/"cache_ia")})
    try:
        logs,_=ACTIVE_CHILD.communicate()
        rc=ACTIVE_CHILD.returncode
    finally:
        ACTIVE_CHILD=None
    if rc:
        raise RuntimeError("Falló la separación automática: " + logs[-800:])
    stems=sorted(p for p in stems_dir.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)
    if len(stems)<2:
        raise RuntimeError("La separación automática no produjo pistas suficientes")
    emit("separation_done", files=len(stems), folder=str(stems_dir))
    return stems


def normalize_track(source, destination):
    """Decodifica cualquier audio FFmpeg a FLAC para ambos motores MIDI."""
    global ACTIVE_CHILD
    probe_audio(source)
    emit("importing", source=str(source), codec="FLAC 24 bits", rate=44100)
    cmd=normalize_command(source, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_CHILD=subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, text=True,
                                   start_new_session=True)
    try:
        _,err=ACTIVE_CHILD.communicate()
        rc=ACTIVE_CHILD.returncode
    finally:
        ACTIVE_CHILD=None
    if rc != 0:
        raise RuntimeError(f"Error importando {Path(source).name}: {err[-650:]}")
    return probe_audio(destination)


def handle(opts):
    paths = list_inputs(opts["files"], opts.get("folder"))
    outdir = Path(opts["output_dir"]).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="_audio_midi_entrada_",dir=str(outdir)) as tmp:
        return _handle(opts, paths, outdir, Path(tmp))


def _handle(opts, originals, outdir, scratch):
    paths=[]
    original_for_file={}
    for i,original in enumerate(originals):
        safe=re.sub(r"[/\\]+", "_", original.stem)[:120] or "audio"
        target=scratch/f"{i:02d}_{safe}.flac"
        normalize_track(original,target)
        paths.append(target)
        original_for_file[str(target)]=str(original)
    source_for_tempo=paths[0]
    allowed = re.sub(r"[^a-zA-Z0-9_ -]", "_", opts.get("name","Audio_a_MIDI")).strip() or "Audio_a_MIDI"
    output = outdir / (allowed + ".mid")
    k=2
    while output.exists():
        output = outdir/(f"{allowed}_{k}.mid")
        k+=1
    midi_tracks = []
    emit("start", tracks=len(paths), mode="automatic" if opts.get("automatic",True) else "manual")
    requested_split=bool(opts.get("separate_first",False))
    already_stem=(len(originals)==1 and is_separated_stem(originals[0]))
    should_split=requested_split and not already_stem
    if already_stem and requested_split:
        emit("info", message="Este audio ya es una pista separada. "
             "Se omite Demucs y comienza la transcripción directa, sin repetir la separación.")
    if should_split:
        if len(paths)!=1 or opts.get("folder"):
            raise ValueError("La separación automática solo admite un archivo de audio individual")
        paths=auto_separate_audio(paths[0],opts,outdir,allowed)
    tempo_analysis=None
    if opts.get("tempo_auto", True):
        try:
            bpm, reliable, tempo_analysis = estimate_bpm(source_for_tempo)
            emit("tempo", bpm=round(bpm,2), estimated=reliable,
                 confidence=tempo_analysis.get("confidence",0),
                 alternatives=tempo_analysis.get("alternatives",[]),
                 warning=tempo_analysis.get("warning",""))
        except Exception as e:
            bpm = float(opts.get("bpm",120))
            emit("info", message=f"Tempo no estimable: {e}; "
                 f"se utiliza el BPM de referencia {bpm:g}")
    else:
        bpm = float(opts.get("bpm",120))
        emit("tempo",bpm=round(bpm,2),estimated=False,manual=True)
    bpm = min(300.,max(35.,bpm))
    if (opts.get("quantize","off")!="off"
            and opts.get("auto_grid_alignment",True)
            and tempo_analysis is not None
            and tempo_analysis.get("bpm") is not None):
        beat_seconds=60./bpm
        raw_offset=float(tempo_analysis.get("beat_offset",0.))
        offset=((raw_offset+beat_seconds/2)%beat_seconds-beat_seconds/2)
        opts["grid_offset_ms"]=round(offset*1000)
        emit("info",message=f"Rejilla ajustada al pulso: {opts['grid_offset_ms']} ms")
    model = None
    report = []
    source_rms = None
    if should_split:
        reference_audio,_ = librosa.load(str(source_for_tempo), sr=11025, mono=True)
        if reference_audio.size:
            source_rms = float(np.sqrt(np.mean(reference_audio**2)))
    for index,path in enumerate(paths):
        kind, program, name = infer_instrument(
            Path(original_for_file.get(str(path), str(path))))
        stemname = f"{index+1:02d} {name}"
        is_drums = kind == "drums"
        effective=None
        refine_report=None
        emit("processing", current=index+1, total=len(paths), name=name, file=str(path))
        is_silent_artifact = False
        if source_rms and source_rms > 0.00001:
            stem_audio,_ = librosa.load(str(path), sr=11025, mono=True)
            stem_rms = float(np.sqrt(np.mean(stem_audio**2))) if stem_audio.size else 0.
            is_silent_artifact = stem_rms < 0.015*source_rms
        if is_silent_artifact:
            notes = []
            method = "Pista residual casi silenciosa (omitida)"
            emit("info", message=f"{name}: pista casi silenciosa respecto al original; se descartan notas espurias.")
        elif is_drums:
            notes = drum_events(path,opts,bpm)
            method="Percusión heurística (aproximada)"
        elif kind == "piano" and opts.get("piano_specialist", True):
            emit("loading_model", message="Piano: transcripción especializada Transkun en CPU…")
            try:
                notes = specialist_piano(path, opts, bpm)
                if not notes:
                    emit("info", message="Transkun no detectó notas; se utilizará Basic Pitch.")
                    raise ValueError("Sin notas de piano")
                method = "Transkun V2 (piano)"
            except Exception as exc:
                emit("info", message=f"El motor de piano no produjo resultado: {exc}. Probando Basic Pitch.")
                if model is None:
                    model = Model(ICASSP_2022_MODEL_PATH)
                threshold, frame, minlength, lo, hi = profile_settings(kind, opts)
                effective={"onset":round(threshold,3),"frame":round(frame,3),
                           "min_length_ms":int(minlength),
                           "min_pitch":int(lo),"max_pitch":int(hi)}
                emit("effective_thresholds",name=name,
                     onset=round(threshold,3),frame=round(frame,3),
                     min_length_ms=int(minlength),min_pitch=int(lo),max_pitch=int(hi))
                _pred, _pm, events = predict(str(path), model,
                    onset_threshold=threshold, frame_threshold=frame,
                    minimum_note_length=float(minlength),
                    minimum_frequency=midi_frequency(lo),
                    maximum_frequency=midi_frequency(hi),
                    midi_tempo=bpm)
                events,attacks,qa=refine_events(events,_pred,
                    opts.get("note_refinement","balanced"),
                    onset_threshold=threshold,frame_threshold=frame,
                    min_length_ms=float(minlength))
                notes = clean_events(events,float(minlength)*.6 if qa["splits"] else float(minlength),
                    lo,hi,bpm,opts.get("quantize","off"),
                    **note_filter_options(opts,attacks))
                method = "Basic Pitch ONNX (alternativa) / ataques refinados"
                refine_report=qa
                emit("refinement",name=name,**qa)
        else:
            if model is None:
                emit("loading_model", message="Cargando el modelo ONNX Basic Pitch…")
                model = Model(ICASSP_2022_MODEL_PATH)
            threshold,frame,minlength,lo,hi=profile_settings(kind,opts)
            effective={"onset":round(threshold,3),"frame":round(frame,3),
                       "min_length_ms":int(minlength),
                       "min_pitch":int(lo),"max_pitch":int(hi)}
            emit("effective_thresholds",name=name,
                 onset=round(threshold,3),frame=round(frame,3),
                 min_length_ms=int(minlength),min_pitch=int(lo),max_pitch=int(hi))
            _pred,_pm,events=predict(str(path), model,
                onset_threshold=threshold,frame_threshold=frame,
                minimum_note_length=float(minlength),
                minimum_frequency=midi_frequency(lo),
                maximum_frequency=midi_frequency(hi),
                midi_tempo=bpm)
            events,attacks,qa=refine_events(events,_pred,
                opts.get("note_refinement","balanced"),
                onset_threshold=threshold,frame_threshold=frame,
                min_length_ms=float(minlength))
            notes=clean_events(events,float(minlength)*.6 if qa["splits"] else float(minlength),
                               lo,hi,bpm,opts.get("quantize","off"),
                               **note_filter_options(opts,attacks))
            method="Basic Pitch ONNX · ataques refinados" if qa["splits"] else "Basic Pitch ONNX"
            refine_report=qa
            emit("refinement",name=name,**qa)
        if not is_drums and notes:
            notes, silenced = reject_silent_artifacts(path, notes)
            if silenced:
                emit("info",message=(
                    f"{name}: descartadas {silenced} detecciones espurias en "
                    "silencio casi absoluto (umbral RMS -68 dBFS)."))
        midi_tracks.append((stemname,notes,program,is_drums))
        report.append({"file":original_for_file.get(str(path),str(path)),
                       "name":stemname,"notes":len(notes),"method":method,
                       "effective_thresholds":effective,
                       "refinement":refine_report})
        emit("track_done", current=index+1,total=len(paths),name=name,notes=len(notes),method=method)
    if sum(r["notes"] for r in report)==0:
        raise RuntimeError("No se han detectado notas MIDI. Prueba a bajar la sensibilidad o cambiar de pista.")
    count=make_midi(midi_tracks,bpm,output)
    metadata={"version":2,"midi":str(output),"bpm":round(bpm,3),"quantize":opts.get("quantize","off"),
              "automatic":opts.get("automatic",True),"notes":count,"tracks":report,
              "tempo_analysis":tempo_analysis,
              "algorithm_parameters":{name:opts.get(name) for name in
                  ("precision_profile","onset","frame","min_length_ms","min_pitch",
                   "max_pitch","min_velocity","merge_gap_ms","note_shift_ms",
                   "grid_offset_ms","auto_grid_alignment","drum_sensitivity",
                   "note_refinement")}}
    report_path=output.with_suffix(".json")
    report_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    emit("finished",output=str(output),report=str(report_path),notes=count,tracks=len(report),bpm=round(bpm,2))


def main():
    parser=argparse.ArgumentParser(description="Convertir pistas de audio a MIDI multipista (Basic Pitch ONNX).")
    parser.add_argument("--config",type=Path,required=True)
    args=parser.parse_args()
    try:
        config=json.loads(args.config.read_text(encoding="utf-8"))
        handle(config)
    except Exception as exc:
        emit("error",message=f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
