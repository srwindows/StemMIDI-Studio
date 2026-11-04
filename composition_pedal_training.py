"""Aprendizaje estadístico PRIVADO de pedal CC64 en MIDI piano del usuario.

Se conservan solo contadores, cuantiles por registro y validación.
Nunca se copian eventos, notas, canciones, rutas o material protegido.
No usa género inferido ni presume que cada MIDI sea una buena actuación.
"""
from __future__ import annotations
from bisect import bisect_left,bisect_right
from collections import defaultdict
import json,random,sqlite3,statistics
from pathlib import Path
import os

ROOT=Path(__file__).resolve().parent
CORPUS=Path(os.environ.get("STEMMIDI_TRAINING_CORPUS",
                           str(Path.home()/"Musica"/"MIDI")))
SQL=ROOT/"datos_entrenamiento/catalogo_canciones/catalogo.sqlite3"
DEST=ROOT/"datos_entrenamiento/catalogo_canciones/modelo_privado_pedal_armonico.json"
RNG=random.Random(20261103)
SAMPLE_SIZE=1200

def percentile(v,q):
    a=sorted(v)
    if not a:return None
    index=(len(a)-1)*q
    lo=int(index);hi=min(len(a)-1,lo+1)
    return round(a[lo]+(a[hi]-a[lo])*(index-lo),5)

def category(p):
    return ("sub_bass" if p<48 else "bass" if p<60 else
            "middle" if p<72 else "high")

def analyze_midi(path):
    import mido
    mid=mido.MidiFile(str(path))
    if mid.type not in (0,1):return []
    tpb=max(1,mid.ticks_per_beat)
    meter=(4,4)
    for tr in mid.tracks:
        tick=0
        for msg in tr:
            tick+=msg.time
            if msg.type=="time_signature" and tick==0:
                meter=(msg.numerator,msg.denominator)
                break
    bar=max(1,round(tpb*4*meter[0]/meter[1]))
    outcomes=[]
    for tr in mid.tracks:
        tick=0
        programs=[0]*16
        attacks=defaultdict(list)
        presses=defaultdict(list)
        down=[None]*16
        for msg in tr:
            tick+=msg.time
            if msg.type=="program_change":
                programs[msg.channel]=msg.program
            elif msg.type=="note_on" and msg.velocity>0:
                attacks[msg.channel].append((tick,msg.note))
            elif msg.type=="control_change" and msg.control==64:
                ch=msg.channel
                # Aceptar solo preset GM de piano real, no instrumentos
                # cuya rueda CC64 tenga otra semántica.
                if programs[ch]>7:
                    down[ch]=None
                    continue
                if msg.value>=64:
                    down[ch]=tick
                elif down[ch] is not None:
                    start=down[ch];down[ch]=None
                    duration=tick-start
                    if 0<duration<=bar*3:
                        presses[ch].append((start,tick))
        for ch,intervals in presses.items():
            aa=sorted(attacks[ch])
            if len(aa)<12 or len(intervals)<3:continue
            times=[x[0] for x in aa]
            for start,end in intervals:
                lo=bisect_left(times,start)
                hi=bisect_right(times,end)
                if hi-lo==0:continue
                lowest=min(p for _,p in aa[lo:hi])
                outcomes.append((category(lowest),(end-start)/bar))
    return outcomes

def main():
    rows=[x[0] for x in sqlite3.connect(SQL).execute(
        "SELECT path FROM canciones WHERE status='ok' "
        "AND suffix IN ('.mid','.kar','.midi')")]
    chosen=RNG.sample(rows,min(len(rows),SAMPLE_SIZE))
    train=defaultdict(list);heldout=defaultdict(list)
    errors=0;valid=0
    for i,relative in enumerate(chosen,1):
        try:items=analyze_midi(CORPUS/relative)
        except (OSError,ValueError,EOFError,TypeError,IndexError):
            errors+=1;continue
        if items:valid+=1
        target=heldout if i%5==0 else train
        for band,span in items:
            target[band].append(span)
        if i%200==0:
            print("PEDAL_TRAIN_PROGRESS",i,"/",len(chosen),
                  "USABLE",valid,flush=True)
    stats={}
    for name in ("sub_bass","bass","middle","high"):
        data=train[name];test=heldout[name]
        q65=percentile(data,.65)
        if q65 is not None:
            # Reportar validación fuera del entrenamiento para evitar
            # llamar «precisión» a un ajuste probado sobre lo mismo.
            validation=(round(sum(x<=q65 for x in test)/len(test),4)
                        if test else None)
            stats[name]={"observations":len(data),"heldout":len(test),
                         "q50_pedal_bars":percentile(data,.5),
                         "q65_pedal_bars":q65,
                         "q80_pedal_bars":percentile(data,.8),
                         "heldout_coverage_at_q65":validation}
    result={
        "type":"private_piano_cc64_register_v1",
        "distribution":"PRIVATE_NOT_FOR_PUBLIC_RELEASE",
        "method":"Empirical MIDI CC64 quantiles, GM piano, deterministic holdout",
        "limitations":"MIDI CC64 is not a validated performance quality label. "
                      "Harmonic safety caps have priority over learned durations.",
        "songs_sampled":len(chosen),"songs_with_usable_piano_pedal":valid,
        "files_skipped":errors,
        "piano_pedal_intervals":sum(len(v) for v in train.values()),
        "heldout_intervals":sum(len(v) for v in heldout.values()),
        "registers":stats,
        "source_notes_or_lyrics_stored":False,
    }
    assert result["piano_pedal_intervals"]>=100,result
    DEST.write_text(json.dumps(result,ensure_ascii=False,
                              indent=2)+"\n",encoding="utf-8")
    print("PRIVATE_PEDAL_MODEL_TRAINED",
          json.dumps(result,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
