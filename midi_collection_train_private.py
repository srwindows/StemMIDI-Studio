"""Statistical training from the user's local MIDI/KAR collection.

The result contains only aggregate transitions (no lyrics/full tracks).
The model stays PRIVATE: not in PyInstaller, GitHub or distributed sources.
Genres are not asserted; arrangement profiles are not genre labels.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from multiprocessing import Pool
from pathlib import Path
import hashlib
import json
import math
import random
import sqlite3
import sys
import time
import mido
from midi_collection_catalog import SOURCE,OUT
from midi_collection_report import arrangement

MAJOR=(0,2,4,5,7,9,11)
MINOR=(0,2,3,5,7,8,10)
MAJOR_PROFILE=(6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88)
MINOR_PROFILE=(6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17)


def _key(hist):
    total=sum(hist)
    if not total:return None
    ranking=[]
    for scale,pattern,mode in ((MAJOR,MAJOR_PROFILE,'major'),
                               (MINOR,MINOR_PROFILE,'minor')):
        for tonic in range(12):
            norm=math.sqrt(sum(x*x for x in pattern))
            dot=sum(hist[(tonic+i)%12]*pattern[i] for i in range(12))
            score=dot/max(1e-9,norm*math.sqrt(sum(x*x for x in hist)))
            coverage=sum(hist[(tonic+i)%12] for i in scale)/total
            ranking.append((score,coverage,tonic,mode))
    ranking.sort(reverse=True)
    best=ranking[0]
    if best[1]<.73:return None
    return best[2],best[3],best[0]-ranking[1][0]


def _extract(path):
    mid=mido.MidiFile(str(path),clip=True)
    if mid.ticks_per_beat<=0 or mid.type==2:
        return None
    tpb=mid.ticks_per_beat
    meter=(4,4);max_tick=0
    channel_notes=defaultdict(list)
    programs=defaultdict(int)
    for track in mid.tracks:
        ticks=0
        active=defaultdict(list)
        for msg in track:
            ticks+=msg.time
            if msg.type=='time_signature' and ticks<tpb*8:
                if 1<=msg.numerator<=12 and msg.denominator in (2,4,8,16):
                    meter=(msg.numerator,msg.denominator)
            if msg.type=='program_change':
                programs[msg.channel]=msg.program
            if msg.type=='note_on' and msg.velocity>0:
                if msg.channel==9:continue
                key=(msg.channel,msg.note)
                active[key].append((ticks,msg.velocity))
            elif msg.type in ('note_off','note_on') and (
                    msg.type=='note_off' or msg.velocity==0):
                if msg.channel==9:continue
                key=(msg.channel,msg.note)
                if active[key]:
                    begin,velocity=active[key].pop()
                    if ticks>begin:
                        channel_notes[msg.channel].append((
                            begin,ticks,msg.note,velocity))
        max_tick=max(max_tick,ticks)
        for (channel,pitch),stacks in active.items():
            for begin,velocity in stacks:
                channel_notes[channel].append((
                    begin,begin+tpb//2,pitch,velocity))
    bar_ticks=max(1,round(tpb*4*meter[0]/meter[1]))
    bars=min(380,max(1,(max_tick+bar_ticks-1)//bar_ticks))
    if bars<8 or len(channel_notes)<3:return None
    # Select a likely lead monophonic voice, not drums or bass.
    ranked=[]
    for channel,notes in channel_notes.items():
        if len(notes)<35:continue
        notes.sort()
        pitch=sum(n[2] for n in notes)/len(notes)
        if pitch<52 or pitch>90:continue
        overlap=sum(b[0]<a[1] for a,b in zip(notes,notes[1:]))
        poly=overlap/max(1,len(notes)-1)
        if poly>.56:continue
        active_bars=len({n[0]//bar_ticks for n in notes})
        if active_bars<5:continue
        density=len(notes)/max(1,active_bars)
        score=((1.-poly)*5+(.6 if channel==0 else 0)+
               min(1.1,(pitch-52)/32)+
               (.5 if 60<=pitch<=81 else 0)-
               .035*abs(density-4))
        ranked.append((score,channel))
    if not ranked:return None
    lead=max(ranked)[1]
    melody=channel_notes[lead]
    accomp=[n for c,notes in channel_notes.items() if c!=lead for n in notes]
    if len(accomp)<50:return None
    hist=[0.]*12
    for n in melody+accomp:
        duration=max(1,min(n[1]-n[0],bar_ticks*2))
        hist[n[2]%12]+=duration/max(1,tpb)
    key=_key(hist)
    if key is None:return None
    tonic,mode,confidence=key
    steps=MAJOR if mode=='major' else MINOR
    # Tokenize chromatically, then select a plausible diatonic chord
    # at each bar, with duration and harmonic-bass weights.
    harmony=[[0.]*12 for _ in range(bars)]
    bass=[Counter() for _ in range(bars)]
    for start,end,pitch,velocity in accomp:
        startbar=max(0,start//bar_ticks)
        endbar=min(bars-1,(max(1,end)-1)//bar_ticks)
        if startbar>=bars:continue
        for b in range(startbar,endbar+1):
            delta=max(0,min(end,(b+1)*bar_ticks)-max(start,b*bar_ticks))
            if delta<=0:continue
            weight=min(2.,delta/max(1,bar_ticks/4))
            if start<=(b*bar_ticks+bar_ticks*.08):weight*=1.18
            harmony[b][pitch%12]+=weight
            if pitch<56:bass[b][pitch%12]+=weight
    chord_sets=[
        {(tonic+steps[(degree+j)%7])%12 for j in (0,2,4)}
        for degree in range(7)]
    degrees=[]
    for b,h in enumerate(harmony):
        mass=sum(h)
        if mass<.85:degrees.append(None);continue
        best=[]
        for deg,pcs in enumerate(chord_sets):
            matched=sum(h[pc] for pc in pcs)
            fundamental=(tonic+steps[deg])%12
            root_bonus=bass[b][fundamental]*.50
            score=matched-0.35*(mass-matched)+root_bonus
            best.append(score)
        degrees.append(max(range(7),key=lambda d:best[d]))
    chord_trans=Counter((a,b) for a,b in zip(degrees,degrees[1:])
                        if a is not None and b is not None)
    if sum(chord_trans.values())<6:return None
    melody.sort()
    intervals=[
        max(-12,min(12,b[2]-a[2])) for a,b in zip(melody,melody[1:])
        if b[0]>a[0] and b[0]-a[0]<=bar_ticks*2
        and -12<=b[2]-a[2]<=12]
    interval_trans=Counter((a,b) for a,b in zip(intervals,intervals[1:]))
    if sum(interval_trans.values())<12:return None
    return mode,chord_trans,interval_trans,confidence,len(melody),len(accomp)


def _worker(task):
    relative,sha,group,style,similarity,margin=task
    try:
        decoded=_extract(SOURCE/relative)
        if decoded is None:return None
        return sha,group,style,similarity,margin,decoded
    except Exception:return None


def _nll(transitions,models,unigrams,length):
    total=0;model_loss=0.;prior_loss=0.
    for (source,target),amount in transitions.items():
        row=models.get(source,Counter())
        p=(row.get(target,0)+.75)/(sum(row.values())+length*.75)
        q=(unigrams.get(target,0)+.75)/(sum(unigrams.values())+length*.75)
        model_loss-=amount*math.log(p)
        prior_loss-=amount*math.log(q)
        total+=amount
    return (round(model_loss/max(1,total),5),
            round(prior_loss/max(1,total),5),total)


def _to_rows(transitions,states):
    rows={str(i):{} for i in states}
    for (a,b),n in transitions.items():
        rows[str(a)][str(b)]=n
    return rows


def _serialize(source):
    modes={}
    for mode in ('major','minor'):
        counts=source.get('chord_'+mode,Counter())
        uni=Counter()
        for (_,b),n in counts.items():uni[b]+=n
        modes[mode]=dict(rows=_to_rows(counts,range(7)),
                         unigram={str(k):v for k,v in uni.items()})
    intervals=source.get('intervals',Counter())
    uni=Counter()
    for (_,b),n in intervals.items():uni[b]+=n
    return dict(chords=modes,
                intervals=_to_rows(intervals,range(-12,13)),
                interval_unigram={str(k):v for k,v in uni.items()})


def main(max_songs=0):
    database=OUT/'catalogo.sqlite3'
    with sqlite3.connect(database) as conn:
        conn.row_factory=sqlite3.Row
        entries=list(conn.execute('''SELECT MIN(path) path, sha256,
            MIN(family) family,MAX(drum_notes) drum_notes,
            MAX(melodic_notes) melodic_notes,MAX(channels) channels,
            MAX(approx_bars) bars,
            MAX(approximate_style) approximate_style,
            MAX(similarity) similarity,MAX(margin) margin
            FROM canciones WHERE status='ok' AND sha256 IS NOT NULL
            GROUP BY sha256 HAVING MAX(channels)>=3
            AND MAX(melodic_notes)>=100 AND MAX(approx_bars) BETWEEN 8 AND 380'''))
    rng=random.Random(20261103)
    rng.shuffle(entries)
    if max_songs>0:entries=entries[:max_songs]
    tasks=[]
    for item in entries:
        family=json.loads(item['family']) if item['family'] else {}
        group=arrangement(family,item['drum_notes'] or 0,
                          item['melodic_notes'] or 0)
        tasks.append((item['path'],item['sha256'],group,
                      item['approximate_style'],
                      item['similarity'] or 0.,item['margin'] or 0.))
    print('PRIVATE_SONGS_AFTER_DEDUP_AND_FILTER',len(tasks),flush=True)
    train=defaultdict(lambda:defaultdict(Counter))
    valid=defaultdict(lambda:defaultdict(Counter))
    metrics=Counter()
    start=time.monotonic()
    with Pool(processes=8) as pool:
        for idx,record in enumerate(pool.imap_unordered(
                _worker,tasks,chunksize=7),1):
            if record is None:
                metrics['invalid_for_learning']+=1
                continue
            sha,group,style,similarity,margin,decoded=record
            mode,chords,intervals,confidence,melody_notes,accomp_notes=decoded
            if bytes.fromhex(sha)[0]<37:
                part='validation'
            else:part='train'
            metrics['songs_'+part]+=1
            metrics['melody_notes_'+part]+=melody_notes
            metrics['accomp_notes_'+part]+=accomp_notes
            if part=='validation':
                valid['global']['chord_'+mode].update(chords)
                valid['global']['intervals'].update(intervals)
            else:
                groups=['global','arrangement:'+group]
                if style and similarity>=.77 and margin>=.075:
                    groups.append('rhythm_similarity:'+style)
                for g in groups:
                    train[g]['chord_'+mode].update(chords)
                    train[g]['intervals'].update(intervals)
                metrics['training_chord_transitions']+=sum(chords.values())
                metrics['training_melody_transitions']+=sum(intervals.values())
            if idx%500==0:
                print('PRIVATE_TRAIN_PROGRESS',idx,'/',len(tasks),
                      'TRAINED',metrics['songs_train'],
                      'HELDOUT',metrics['songs_validation'],
                      'SECONDS',round(time.monotonic()-start),flush=True)
    train_global=train['global']
    baseline={}
    for mode in ('major','minor'):
        target=train_global['chord_'+mode]
        unigram=Counter()
        for (a,b),n in target.items():unigram[b]+=n
        rows=defaultdict(Counter)
        for (a,b),n in target.items():rows[a][b]+=n
        baseline[mode]=_nll(valid['global']['chord_'+mode],rows,unigram,7)
    intervals=train_global['intervals']
    i_unigram=Counter()
    i_rows=defaultdict(Counter)
    for (a,b),n in intervals.items():
        i_unigram[b]+=n
        i_rows[a][b]+=n
    baseline['intervals']=_nll(valid['global']['intervals'],
                               i_rows,i_unigram,25)
    model={
        'type':'user_supplied_private_symbolic_markov_v1',
        'distribution':'PRIVATE_NOT_FOR_PUBLIC_RELEASE',
        'genre_labels_verified':False,
        'style_conditioning':'Roland rhythm resemblance ONLY; not music genre',
        'notes_or_lyrics_stored':False,
        'training_metrics':dict(metrics),
        'profiles':{scope:_serialize(learned)
                    for scope,learned in train.items()
                    if sum(learned['chord_major'].values())+
                       sum(learned['chord_minor'].values())>=120},
        'validation_nll':baseline,
        'limitations':'Automatic melody/key/chord extraction; manual musical review needed.',
    }
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/'modelo_privado_multinstrumental.json'
    path.write_text(json.dumps(model,ensure_ascii=False,
                               sort_keys=True,separators=(',',':')),
                    encoding='utf8')
    print('PRIVATE_MODEL_TRAINING_COMPLETED',
          json.dumps({'songs_train':metrics['songs_train'],
                      'songs_validation':metrics['songs_validation'],
                      'invalid_for_learning':metrics['invalid_for_learning'],
                      'profiles':len(model['profiles']),
                      'evaluation':baseline,
                      'bytes':path.stat().st_size},ensure_ascii=False),
          flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--limit',type=int,default=0)
    args=p.parse_args()
    main(args.limit)
