#!/usr/bin/env python3
"""Transcripción armónica experimental basada en cromagrama STFT del audio.

Genera MIDI de acordes independiente SOLO al encontrar triadas reales probables.
Sin servicios externos ni modelos ficticios; FFmpeg, numpy y mido. No altera el audio.
"""
from __future__ import annotations
import argparse, json, math, os, subprocess, sys
from pathlib import Path
import numpy as np
import mido

SAMPLE_RATE=22050
FFT=8192
HOP=4096
PITCHES=np.arange(36,85)
NAMES=("C","Db","D","Eb","E","F","Gb","G","Ab","A","Bb","B")
# No intenta adivinar acordes con 1-2 notas. Orden de intervalos respecto a raíz.
TEMPLATES={
 "maj":(0,4,7),
 "min":(0,3,7),
 "dim":(0,3,6),
 "aug":(0,4,8),
 "sus2":(0,2,7),
 "sus4":(0,5,7),
 "7":(0,4,7,10),
 "m7":(0,3,7,10),
 "maj7":(0,4,7,11),
}

def read_audio(path,limit_seconds=1800):
    if not Path(path).is_file():
        raise FileNotFoundError(str(path))
    cmd=["ffmpeg","-nostdin","-v","error","-i",str(path),
         "-t",str(limit_seconds),"-vn","-ac","1","-ar",str(SAMPLE_RATE),
         "-f","f32le","pipe:1"]
    proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=240,check=False)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8","replace")[-500:])
    arr=np.frombuffer(proc.stdout,dtype="<f4")
    if len(arr)<FFT:
        raise ValueError("No hay suficiente duración de audio para analizar acordes.")
    return np.asarray(arr,dtype=np.float32)

def calculate_chroma(signal):
    """Espectro real: energía tonal cerca de la fundamental y notas armónicas."""
    freq=np.fft.rfftfreq(FFT,1/SAMPLE_RATE)
    note_freq=440.*2.**((PITCHES-69)/12)
    windows=[]
    # Vector de máscara centrada en la fundamental; evita tratar armónicos
    # como notas independientes: ponderación por el pico más próximo.
    bin_ids=[np.flatnonzero((freq>=f*.978)&(freq<=f*1.022))
             for f in note_freq]
    for j in range(0,len(signal)-FFT+1,HOP):
        samples=signal[j:j+FFT]
        spectrum=np.abs(np.fft.rfft(samples*np.hanning(FFT)))
        local=np.asarray([np.max(spectrum[idx]) if len(idx) else 0.
                         for idx in bin_ids])
        # Ponderación: normalizar contra fundamental dominante de cada ventana.
        chroma=np.zeros(12,dtype=np.float64)
        if local.max()>0:
            for i,pitch in enumerate(PITCHES):
                chroma[pitch%12]+=local[i]/(1+.009*max(0,pitch-60))
        energy=np.sqrt(np.mean(samples**2))
        windows.append((float(energy),chroma))
    return windows

def match_chord(chroma):
    total=chroma.sum()
    if total<=1e-6:return None,0.
    vals=chroma/(total+1e-10)
    sorted_vals=np.sort(vals)[::-1]
    # Rechazar señales monofónicas o sin tríada apreciable.
    if sorted_vals[2]<.10 or sorted_vals[2]<sorted_vals[0]*.25:
        return None,0.
    top_three=set(np.argsort(vals)[-3:].tolist())
    best=None;best_score=-1e6;next_best=-1e6
    for root in range(12):
        for name,intervals in TEMPLATES.items():
            components={(root+x)%12 for x in intervals}
            if len(components & top_three)<3:continue
            inside=sum(vals[p] for p in components)
            # Discriminación de otras notas para evitar falsos armónicos.
            outside=1.-inside
            strength=min(vals[p] for p in components)
            score=inside-.75*outside + .60*strength
            if score>best_score:
                next_best=best_score
                best_score=score;best=(root,name,intervals)
            elif score>next_best:next_best=score
    if best is None or best_score<.40:return None,0.
    # Acordes ambiguos: sólo se expresa lo más estable.
    confidence=min(1.,max(0.,best_score))
    if confidence<.44:return None,confidence
    return best,confidence

def segment_chords(frames):
    energies=np.array([e for e,c in frames])
    floor=max(.0009,float(np.percentile(energies,65))*.14)
    events=[]
    for energy,chroma in frames:
        if energy<floor:
            events.append((None,0.))
        else:
            events.append(match_chord(chroma))
    # Suavizado temporal por mayoría de 5 ventanas: un acorde necesita >0.55 s.
    keys=[v[0] for v in events]
    smoothed=[]
    for i,key in enumerate(keys):
        neighborhood=[key2 for key2 in keys[max(0,i-2):min(len(keys),i+3)]
                      if key2 is not None]
        if len(neighborhood)<3:
            smoothed.append(None);continue
        winner=max(set(neighborhood),key=neighborhood.count)
        smoothed.append(winner if neighborhood.count(winner)>=3 else None)
    segments=[]
    cursor=0
    while cursor<len(smoothed):
        current=smoothed[cursor]
        end=cursor+1
        while end<len(smoothed) and smoothed[end]==current:end+=1
        if current is not None and end-cursor>=3:
            # Tiempo centrado de ventana; inicio estimado sin latencia artificial.
            start=max(0.,(cursor*HOP+FFT*.5)/SAMPLE_RATE)
            stop=(end*HOP+FFT*.5)/SAMPLE_RATE
            confidence=float(np.mean([
                score for k,score in events[cursor:end] if k==current] or [0.]))
            if confidence>=.44 and stop-start>=.50:
                segments.append((start,stop,current,confidence))
        cursor=end
    # Fusionar pequeñas interrupciones del mismo acorde.
    merged=[]
    for seg in segments:
        if merged and merged[-1][2]==seg[2] and seg[0]-merged[-1][1]<.32:
            last=merged.pop()
            merged.append((last[0],seg[1],seg[2],min(last[3],seg[3])))
        else:merged.append(seg)
    return merged

def time_to_tick(seconds,reference):
    """Mapeo real de segundos a ticks según todos los cambios tempo del MIDI."""
    midi=mido.MidiFile(str(reference))
    tempo_events=[(0,500000)]
    for track in midi.tracks:
        tick=0
        for msg in track:
            tick+=msg.time
            if msg.type=="set_tempo":
                tempo_events.append((tick,msg.tempo))
    tempo_events=sorted(tempo_events)
    elapsed=0.;previous_tick=0;tempo=500000
    for tick,newtempo in tempo_events:
        duration=mido.tick2second(max(0,tick-previous_tick),midi.ticks_per_beat,tempo)
        if elapsed+duration>=seconds:
            return max(0,previous_tick+round(mido.second2tick(seconds-elapsed,
                                        midi.ticks_per_beat,tempo))),midi.ticks_per_beat
        elapsed+=duration;previous_tick=tick;tempo=newtempo
    return max(0,previous_tick+round(mido.second2tick(seconds-elapsed,
                                   midi.ticks_per_beat,tempo))),midi.ticks_per_beat

def save_chord_midi(segments,reference,destination):
    if not segments:return None
    midi_ref=mido.MidiFile(str(reference))
    out=mido.MidiFile(type=1,ticks_per_beat=midi_ref.ticks_per_beat)
    meta=mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name",name="Acordes detectados",time=0))
    # Tempo map from original MIDI, preserving real timing of the source.
    time_events=[]
    for tr in midi_ref.tracks:
        tick=0
        for msg in tr:
            tick+=msg.time
            if msg.type=="set_tempo":
                time_events.append((tick,msg.copy(time=0)))
    # Prioridad al último mensaje de tempo para cada tick.
    tempos={tick:msg for tick,msg in time_events}
    meta.clear()
    previous=0
    for tick,msg in sorted(tempos.items()):
        meta.append(msg.copy(time=max(0,tick-previous)))
        previous=tick
    meta.append(mido.MetaMessage("end_of_track",time=0))
    out.tracks.append(meta)
    track=mido.MidiTrack()
    track.append(mido.MetaMessage("track_name",name="Acordes · audio analizado",time=0))
    track.append(mido.Message("program_change",channel=0,program=0,time=0))
    events=[]
    for start,stop,(root,name,intervals),confidence in segments:
        at,_=time_to_tick(start,reference)
        end,_=time_to_tick(stop,reference)
        # 48=C3; acordes cómodos entre tercera y cuarta octava.
        notes=[48+root+interval for interval in intervals]
        velocity=max(48,min(110,round(55+confidence*40)))
        for pitch in notes:
            events.append((at,1,mido.Message("note_on",note=pitch,
                        velocity=velocity,channel=0,time=0)))
            events.append((max(at+1,end),0,mido.Message("note_off",note=pitch,
                        velocity=0,channel=0,time=0)))
    events.sort(key=lambda item:(item[0],item[1]))
    prev=0
    for tick,_,message in events:
        track.append(message.copy(time=max(0,tick-prev)))
        prev=tick
    track.append(mido.MetaMessage("end_of_track",time=0))
    out.tracks.append(track)
    dest=Path(destination)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        i=2
        while dest.with_name(dest.stem+f"_{i}"+dest.suffix).exists():
            i+=1
        dest=dest.with_name(dest.stem+f"_{i}"+dest.suffix)
    # Escritura exclusiva: no seguir symlink preexistente ni sobrescribir.
    import io
    buff=io.BytesIO()
    out.save(file=buff)
    with dest.open("xb") as f:
        f.write(buff.getvalue())
    return dest

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--audio",required=True)
    parser.add_argument("--midi",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    audio=read_audio(args.audio)
    frames=calculate_chroma(audio)
    segments=segment_chords(frames)
    if not segments:
        print(json.dumps({"status":"no_chords","segments":0,
                          "message":"Sin acordes suficientemente claros; no se creó MIDI ficticio."}),
              flush=True)
        return 0
    result=save_chord_midi(segments,args.midi,args.output)
    print(json.dumps({"status":"ok","output":str(result),"segments":len(segments),
        "chords":[f"{NAMES[x[2][0]]}:{x[2][1]}" for x in segments[:20]]}),
        flush=True)
    return 0

if __name__=="__main__":
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status":"error","message":str(exc)[:360]}),flush=True)
        raise SystemExit(1)
