"""Aprendizaje simbólico exclusivamente a partir de corpus OpenScore CC0.

No consume MuseScore.com, no usa la sesión de Firefox, no descarga obras
con derechos restringidos. Procesa de forma local MSCX publicados por OpenScore.
Solo estadísticas musicales; jamás utiliza letras.
"""
from __future__ import annotations
from collections import Counter
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import math
import random
import xml.etree.ElementTree as ET

MAJOR=(0,2,4,5,7,9,11)
MINOR=(0,2,3,5,7,8,10)
DURATIONS={'maxima':32,'longa':16,'breve':8,'whole':4,'half':2,
           'quarter':1,'eighth':.5,'16th':.25,'32nd':.125,
           '64th':.0625,'128th':.03125}
LICENCE='CC0-1.0'
MIN_NOTES=8


def _ticks(element,measure_ticks):
    explicit=element.findtext('duration')
    if explicit:
        try:return max(1,round(float(Fraction(explicit))*1920))
        except (ValueError,ZeroDivisionError):pass
    kind=element.findtext('durationType','quarter')
    if kind=='measure':return measure_ticks
    beats=DURATIONS.get(kind,1)
    dots=element.findtext('dots','0')
    try:dots=max(0,min(3,int(dots)))
    except ValueError:dots=0
    return max(1,round(480*beats*sum(.5**i for i in range(dots+1))))


def _measure_ticks(measure,meter):
    override=measure.get('len')
    if override:
        try:
            ticks=round(float(Fraction(override))*1920)
            if ticks>0:return ticks
        except (ValueError,ZeroDivisionError):pass
    return max(120,round(1920*meter[0]/max(1,meter[1])))


def _notes_for_voice(voice,base,measure_ticks,staff_id):
    events=[]
    tick=0
    # In MSCX every voice contains its own sequential score events.
    # Grace notes are not timed training examples.
    tuplet_factor=1.
    for item in voice:
        if item.tag=='Tuplet':
            try:
                ratio=int(item.findtext('normalNotes','2'))/int(
                    item.findtext('actualNotes','3'))
                tuplet_factor=ratio if .2<=ratio<=2 else 1.
            except (ValueError,ZeroDivisionError):tuplet_factor=1.
            continue
        if item.tag in ('endTuplet','EndTuplet'):
            tuplet_factor=1.
            continue
        if item.tag=='tick':
            try:tick=max(0,int(item.text)-base)
            except (ValueError,TypeError):pass
            continue
        if item.tag not in ('Chord','Rest'):continue
        # A duration of 'measure' may be displayed as a whole-measure rest
        duration=round(_ticks(item,measure_ticks)*tuplet_factor)
        if item.tag=='Chord':
            if item.find('grace') is None and item.find('acciaccatura') is None:
                for note in item.findall('Note'):
                    pitch=note.findtext('pitch')
                    try:p=int(pitch)
                    except (ValueError,TypeError):continue
                    if 0<=p<=127:
                        events.append((base+tick,base+tick+duration,p,staff_id))
        tick+=max(1,duration)
    return events


def parse_score(path):
    """Return (melody, accompaniment, tonic, mode, bars) without lyrics."""
    root=ET.parse(path).getroot()
    score=root.find('Score')
    if score is None:raise ValueError('Missing Score element')
    staves=score.findall('Staff')
    if not staves:raise ValueError('No staves')
    measures=[s.findall('Measure') for s in staves]
    bars=max(map(len,measures))
    if bars<4:raise ValueError('Short or empty score')
    cursor=0;key_fifths=0;meter=(4,4)
    starts=[];lengths=[]
    # The first score staff provides the reference for bar alignment.
    first=measures[0]
    for idx in range(bars):
        m=first[idx] if idx<len(first) else None
        if m is not None:
            key=m.find('.//KeySig/accidental')
            if key is not None and key.text:
                try:key_fifths=int(key.text)
                except ValueError:pass
            time=m.find('.//TimeSig')
            if time is not None:
                try:
                    num=int(time.findtext('sigN','4'))
                    den=int(time.findtext('sigD','4'))
                    if 1<=num<=16 and den in (2,4,8,16):meter=(num,den)
                except ValueError:pass
        starts.append(cursor)
        size=_measure_ticks(m,meter) if m is not None else max(120,round(1920*meter[0]/meter[1]))
        lengths.append(size)
        cursor+=size
    voice_by_staff=[]
    for staff_id,staff_measures in enumerate(measures):
        notes=[]
        for b,measure in enumerate(staff_measures[:bars]):
            for voice in measure.findall('voice'):
                notes.extend(_notes_for_voice(voice,starts[b],lengths[b],staff_id))
        notes.sort()
        voice_by_staff.append(notes)
    melody=voice_by_staff[0]
    accompaniment=[n for voice in voice_by_staff[1:] for n in voice]
    if len(melody)<MIN_NOTES or len(accompaniment)<MIN_NOTES:
        raise ValueError('Not a multi-part melody+accompaniment')
    # Key signature is the major relative to the sharps/flats. Prefer
    # the relative minor when the final melodic pitch and bass support it.
    major=(7*key_fifths)%12
    minor=(major+9)%12
    tail=melody[-1][2]%12
    mode='minor' if tail==minor and tail!=major else 'major'
    tonic=minor if mode=='minor' else major
    return melody,accompaniment,tonic,mode,list(zip(starts,lengths))


def _derive_chords(melody,accomp,tonic,mode,bars):
    steps=MINOR if mode=='minor' else MAJOR
    options=[{(tonic+steps[(d+i)%7])%12 for i in (0,2,4)}
             for d in range(7)]
    chords=[]
    # Sweep notes for each bar. Indexing by bar reduces repeated scans.
    by_bar=[Counter() for _ in bars]
    bass_by_bar=[[] for _ in bars]
    for b,(left,size) in enumerate(bars):
        right=left+size
        for start,end,p,_ in accomp:
            overlap=max(0,min(end,right)-max(start,left))
            if overlap:
                by_bar[b][p%12]+=min(2.,overlap/max(1,size/4))
                if p<56:bass_by_bar[b].append((p,overlap))
        for start,end,p,_ in melody:
            overlap=max(0,min(end,right)-max(start,left))
            if overlap:
                by_bar[b][p%12]+=.18*min(2.,overlap/max(1,size/4))
    previous=None
    for b,hist in enumerate(by_bar):
        if sum(hist.values())<1.3:chords.append(None);continue
        bass_pc=(min(bass_by_bar[b])[0]%12 if bass_by_bar[b] else None)
        scores=[]
        for degree,pcs in enumerate(options):
            hit=sum(weight*(1. if pc in pcs else -.55)
                    for pc,weight in hist.items())
            if bass_pc is not None and (tonic+steps[degree])%12==bass_pc:
                hit+=1.4
            if previous==degree:hit+=.12
            scores.append(hit)
        chosen=max(range(7),key=lambda x:scores[x])
        chords.append(chosen)
        previous=chosen
    return chords


def _intervals(melody):
    return [max(-12,min(12,b[2]-a[2]))
            for a,b in zip(melody,melody[1:])
            if b[0]>a[0] and b[0]-a[0]<=3840]


def _split(path):
    h=hashlib.sha256(str(path).encode('utf8')).digest()
    return 'validation' if h[0]<38 else 'train' # 14.8% held out


def _prob(row,item,support,alpha=.6):
    return (row[item]+alpha)/(sum(row.values())+alpha*support)


def _cross_entropy(rows,unigram,validation):
    total=0;model=0;base=0
    for prev,nxt in validation:
        n=len(unigram)
        model-=math.log(_prob(rows.get(prev,Counter()),nxt,n))
        base-=math.log(_prob(unigram,nxt,n))
        total+=1
    return (round(model/max(1,total),4),round(base/max(1,total),4),total)


def train_corpus(paths, output, source_revisions, max_scores=0):
    """Learn 7-state harmonic and 25-state melodic interval transitions.

    Validation pieces excluded from training; no lyrics or full works in
    the output weights. Classical accompaniment only, not 59 modern styles.
    """
    chord_rows={'major':{str(k):Counter() for k in range(7)},
                'minor':{str(k):Counter() for k in range(7)}}
    chord_unigrams={'major':Counter({str(i):0 for i in range(7)}),
                    'minor':Counter({str(i):0 for i in range(7)})}
    step_rows={str(k):Counter() for k in range(-12,13)}
    step_unigram=Counter({str(i):0 for i in range(-12,13)})
    validation_chords={'major':[],'minor':[]}
    validation_steps=[]
    metrics=Counter()
    examples=[]
    for idx,path in enumerate(paths):
        if max_scores and idx>=max_scores:break
        try:melody,accomp,tonic,mode,bars=parse_score(path)
        except (ET.ParseError,OSError,ValueError,OverflowError):
            metrics['skipped']+=1;continue
        chords=_derive_chords(melody,accomp,tonic,mode,bars)
        chord_pairs=[(str(a),str(b)) for a,b in zip(chords,chords[1:])
                     if a is not None and b is not None]
        steps=_intervals(melody)
        interval_pairs=[(str(a),str(b)) for a,b in zip(steps,steps[1:])]
        if len(chord_pairs)<2 or len(interval_pairs)<4:
            metrics['insufficient']+=1;continue
        subset=_split(path)
        metrics['scores_'+subset]+=1
        metrics['notes_'+subset]+=len(melody)+len(accomp)
        if subset=='train':
            for a,b in chord_pairs:
                chord_rows[mode][a][b]+=1
                chord_unigrams[mode][b]+=1
                metrics['chord_pairs_train']+=1
            for a,b in interval_pairs:
                step_rows[a][b]+=1
                step_unigram[b]+=1
                metrics['interval_pairs_train']+=1
        else:
            validation_chords[mode].extend(chord_pairs)
            validation_steps.extend(interval_pairs)
        if len(examples)<8:examples.append(str(path))
    if metrics['scores_train']<20 or metrics['scores_validation']<4:
        raise RuntimeError('Insufficient legal training examples')
    mode_scores={}
    for mode in ('major','minor'):
        mode_scores[mode]=_cross_entropy(chord_rows[mode],
                                        chord_unigrams[mode],
                                        validation_chords[mode])
    melodic=_cross_entropy(step_rows,step_unigram,validation_steps)
    def totals(rows):
        return {str(k):dict(sorted(v.items())) for k,v in rows.items()}
    model={
        'version':1,'type':'symbolic_markov_v1','license':LICENCE,
        'sources':source_revisions,
        'scores_train':metrics['scores_train'],
        'scores_validation':metrics['scores_validation'],
        'notes_train':metrics['notes_train'],
        'chord_pairs_train':metrics['chord_pairs_train'],
        'interval_pairs_train':metrics['interval_pairs_train'],
        'chords':{mode:totals(rows) for mode,rows in chord_rows.items()},
        'chord_unigram':{k:dict(v) for k,v in chord_unigrams.items()},
        'intervals':totals(step_rows),
        'interval_unigram':dict(step_unigram),
        'validation':{'chord_nll':mode_scores,'melodic_interval_nll':melodic},
        'limitations':'Classical symbolic scores, not human performance velocity/CC64 or modern genre music.',
    }
    out=Path(output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(model,ensure_ascii=False,sort_keys=True,
                              separators=(',',':')),encoding='utf8')
    print('LEARNED_CC0_SCORES',metrics['scores_train'],metrics['scores_validation'],
          'SKIP',metrics['skipped'],metrics['insufficient'],flush=True)
    print('HARMONY_HOLDOUT_NLL',mode_scores,flush=True)
    print('MELODY_HOLDOUT_NLL',melodic,flush=True)
    print('LEARNED_MODEL_PATH',out,flush=True)
    return model


if __name__=='__main__':
    import argparse,subprocess
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',nargs='+',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--limit',type=int,default=0)
    args=parser.parse_args()
    paths=[];sources={}
    for entry in args.sources:
        base=Path(entry).resolve()
        if not (base/'LICENSE.txt').is_file() or 'CC0 1.0 Universal' not in (base/'LICENSE.txt').read_text()[:500]:
            raise RuntimeError('Missing verified CC0 license: '+str(base))
        commit=subprocess.check_output(['git','-C',str(base),'rev-parse','HEAD'],
                                       text=True).strip()
        sources[base.name]={'url':'https://github.com/OpenScore/'+
                           base.name.replace('OpenScore_',''),
                            'sha':commit,'license':'CC0-1.0'}
        paths.extend(base.glob('scores/**/*.mscx'))
    paths=sorted(paths)
    print('AVAILABLE_CC0_SCORES',len(paths),flush=True)
    train_corpus(paths,args.output,sources,max_scores=args.limit)
