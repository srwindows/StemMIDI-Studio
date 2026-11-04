"""Inventario MIDI/KAR de canciones privadas para análisis local.

- Escribe ÚNICAMENTE bajo datos_entrenamiento/catalogo_canciones.
- Nunca modifica la fuente coleccion MIDI elegida por el usuario.
- No almacena letras karaoke, datos de SysEx ni mensajes completos.
- Parecidos a estilos Roland = similitud de batería, NO etiqueta de género.
- Contenido ZIP se enumera sin extraer ni ejecutar ficheros.
"""
from __future__ import annotations
import collections
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
import zipfile
import mido

SOURCE=Path(os.environ.get("STEMMIDI_TRAINING_CORPUS",
                            str(Path.home()/"Musica"/"MIDI")))
OUT=Path(__file__).resolve().parent/'datos_entrenamiento/catalogo_canciones'
SUFFIX={'.mid','.midi','.kar'}
INSTRUMENT_FAMILIES=('Piano','Percusión cromática','Órgano','Guitarra','Bajo',
                     'Cuerdas','Conjunto','Metales','Lengüetas','Tubo',
                     'Sintetizador melódico','Sintetizador pads','Sintetizador FX',
                     'Étnico','Percusiones melódicas','Efectos')


def _db(path):
    conn=sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS canciones (
        path TEXT PRIMARY KEY, suffix TEXT NOT NULL, bytes INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL, sha256 TEXT,
        status TEXT NOT NULL, error TEXT,
        midi_type INTEGER, ticks_per_beat INTEGER, tracks INTEGER,
        channels INTEGER, programs INTEGER, melodic_notes INTEGER,
        drum_notes INTEGER, bpm REAL, numerator INTEGER, denominator INTEGER,
        approx_bars REAL, pitch_min INTEGER, pitch_max INTEGER,
        has_lyrics INTEGER, has_cc64 INTEGER, has_cc11 INTEGER,
        family TEXT, drums_profile TEXT, note_pcs TEXT,
        approximate_style TEXT, similarity REAL, margin REAL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS archives(
        path TEXT PRIMARY KEY, status TEXT, entries INTEGER,
        midi_entries INTEGER, unpacked_bytes INTEGER,error TEXT
    )''')
    conn.commit()
    return conn


def _hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def _normalise(values):
    total=sum(values)
    return [round(v/total,5) for v in values] if total else [0.]*len(values)


def _cosine(a,b):
    dot=sum(x*y for x,y in zip(a,b))
    norm=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return dot/norm if norm>1e-12 else 0.


def _ref_styles():
    from rhythm_style_catalog import available_styles
    refs=[]
    for name,item in available_styles().items():
        ref=item.get('levels',{})
        if sum(ref.get('kick',()))+sum(ref.get('snare',()))<.01:continue
        refs.append((name,[_normalise(ref.get(key,[0]*16))
                           for key in ('kick','snare','hat')]))
    return refs


def _similarity(refs,grid):
    active=[_normalise(arr) for arr in grid]
    if sum(grid[0])+sum(grid[1])<8:return ('',0.,0.)
    scores=[]
    for name,pattern in refs:
        # Time signatures outside 4/4 are handled separately by catalog.
        score=sum(w*_cosine(a,b) for w,a,b in
                  zip((.4,.45,.15),active,pattern))
        scores.append((score,name))
    if not scores:return ('',0.,0.)
    scores.sort(reverse=True)
    first=scores[0][0]
    second=scores[1][0] if len(scores)>1 else 0.
    return scores[0][1],round(first,4),round(first-second,4)


def extract(path,refs):
    mid=mido.MidiFile(str(path),clip=True)
    if mid.type not in (0,1,2):raise ValueError('Unsupported SMF type')
    if mid.ticks_per_beat<=0:raise ValueError('SMPTE/negative division')
    # First measure and tempo markers are read as they appear; note onsets
    # and average instrumental programme are collected in one pass.
    tick_limit=0; bpm=120.;meter=(4,4);lyrics=False
    cc64=False;cc11=False;programs=set();channels=set()
    count=0;drums=0;pcs=Counter();gm_families=Counter()
    lower=128;upper=-1
    hits=[]
    # Tracks may share channels, but programme changes are per event.
    for track in mid.tracks:
        tick=0
        current_program=collections.defaultdict(int)
        for msg in track:
            tick+=msg.time
            if msg.type=='set_tempo' and msg.tempo>0 and not (
                    tick_limit or bpm!=120.):
                bpm=60_000_000/msg.tempo
            elif msg.type=='time_signature' and tick<=mid.ticks_per_beat*4:
                numerator=int(msg.numerator)
                denominator=int(msg.denominator)
                if numerator>0 and denominator>0:
                    meter=(numerator,denominator)
            elif msg.type in ('lyrics','text') and msg.text:
                lyrics=True
            elif msg.type=='program_change':
                programs.add((msg.channel,msg.program))
                current_program[msg.channel]=msg.program
            elif msg.type=='control_change':
                if msg.control==64:cc64=True
                elif msg.control==11:cc11=True
            elif msg.type=='note_on' and msg.velocity>0:
                channels.add(msg.channel)
                if msg.channel==9:
                    drums+=1
                    hits.append((tick,msg.note,msg.velocity))
                else:
                    count+=1
                    lower=min(lower,msg.note);upper=max(upper,msg.note)
                    pcs[msg.note%12]+=1
                    gm_families[INSTRUMENT_FAMILIES[
                        min(15,current_program[msg.channel]//8)]]+=1
        tick_limit=max(tick_limit,tick)
    bar_ticks=max(1,round(mid.ticks_per_beat*4*meter[0]/meter[1]))
    grid=[[0.]*16 for _ in range(3)]
    for tick,note,velocity in hits:
        index=min(15,max(0,int(tick%bar_ticks*16/bar_ticks)))
        group=(0 if note in (35,36) else
               1 if note in (37,38,39,40) else
               2 if note in (42,44,46) else -1)
        if group>=0:grid[group][index]+=max(.15,velocity/100)
    style,score,margin=_similarity(refs,grid) if meter==(4,4) else ('',0.,0.)
    return dict(sha256=_hash(path),status='ok',error=None,midi_type=mid.type,
        ticks_per_beat=mid.ticks_per_beat,tracks=len(mid.tracks),
        channels=len(channels),programs=len(programs),
        melodic_notes=count,drum_notes=drums,
        bpm=round(bpm,2),numerator=meter[0],denominator=meter[1],
        approx_bars=round(tick_limit/bar_ticks,2),
        pitch_min=lower if count else None,pitch_max=upper if count else None,
        has_lyrics=int(lyrics),has_cc64=int(cc64),has_cc11=int(cc11),
        family=json.dumps(gm_families,ensure_ascii=False),
        drums_profile=json.dumps([_normalise(x) for x in grid]),
        note_pcs=json.dumps(dict(pcs)),
        approximate_style=style,similarity=score,margin=margin)


def _insert(conn,path,row,size,mtime_ns):
    fields=dict(path=path,suffix=Path(path).suffix.lower(),bytes=size,
                mtime_ns=mtime_ns,**row)
    columns=list(fields)
    sql=(f"INSERT OR REPLACE INTO canciones ({','.join(columns)})"+
         f" VALUES ({','.join('?' for _ in columns)})")
    conn.execute(sql,[fields[x] for x in columns])


def main():
    if not SOURCE.is_dir():raise SystemExit(f'Missing source: {SOURCE}')
    OUT.mkdir(parents=True,exist_ok=True)
    conn=_db(OUT/'catalogo.sqlite3')
    refs=_ref_styles()
    print('ROLAND_RHYTHM_PROFILES',len(refs),flush=True)
    files=sorted((p for p in SOURCE.rglob('*') if
                  p.is_file() and p.suffix.lower() in SUFFIX),
                 key=lambda p:str(p))
    print('MIDI_FILES_FOUND',len(files),flush=True)
    seen={(row[0]):(row[1],row[2],row[3]) for row in conn.execute(
        'SELECT path,bytes,mtime_ns,status FROM canciones')}
    counters=Counter()
    start=time.monotonic()
    for index,p in enumerate(files,1):
        relative=str(p.relative_to(SOURCE))
        st=p.stat()
        if relative in seen and seen[relative]==(
                st.st_size,st.st_mtime_ns,'ok'):
            counters['cached']+=1;continue
        try:
            if st.st_size>14_000_000:
                raise ValueError('Too large for initial MIDI catalog')
            info=extract(p,refs)
            counters['valid']+=1
        except (OSError,ValueError,EOFError,TypeError,
                IndexError,OverflowError,MemoryError) as ex:
            info=dict(status='invalid',error=(type(ex).__name__+':'+str(ex))[:180])
            counters['invalid']+=1
        _insert(conn,relative,info,st.st_size,st.st_mtime_ns)
        if index%100==0:
            conn.commit()
            print('INDEX_PROGRESS',index,'/',len(files),
                  'VALID',counters['valid'],'INVALID',counters['invalid'],
                  'S',round(time.monotonic()-start,1),flush=True)
    conn.commit()
    print('MIDI_SCAN_DONE',dict(counters),flush=True)
    archives=sorted(p for p in SOURCE.rglob('*') if
                    p.is_file() and p.suffix.lower() in ('.zip','.rar'))
    for p in archives:
        relative=str(p.relative_to(SOURCE))
        try:
            if p.suffix.lower()=='.zip':
                with zipfile.ZipFile(p) as z:
                    infos=[i for i in z.infolist() if not i.is_dir()]
                    count=len(infos)
                    mids=sum(i.filename.lower().endswith(('.mid','.midi','.kar')) for i in infos)
                    size=sum(i.file_size for i in infos)
                values=(relative,'ok',count,mids,size,'')
            else:
                values=(relative,'uninspected-rar',0,0,0,
                        'No extraction performed')
        except (OSError,ValueError,zipfile.BadZipFile,OverflowError) as ex:
            values=(relative,'invalid',0,0,0,str(ex)[:150])
        conn.execute('INSERT OR REPLACE INTO archives VALUES (?,?,?,?,?,?)',values)
    conn.commit()
    report={}
    report['source']=str(SOURCE)
    report['source_read_only']=True
    report['total_files_scanned']=len(files)
    report['rolland_reference_count']=len(refs)
    report['records']=conn.execute('SELECT COUNT(*) FROM canciones').fetchone()[0]
    report['valid']=conn.execute("SELECT COUNT(*) FROM canciones WHERE status='ok'").fetchone()[0]
    report['invalid']=conn.execute("SELECT COUNT(*) FROM canciones WHERE status!='ok'").fetchone()[0]
    report['with_drums']=conn.execute('SELECT COUNT(*) FROM canciones WHERE drum_notes>20').fetchone()[0]
    report['multi_channel']=conn.execute('SELECT COUNT(*) FROM canciones WHERE channels>=3').fetchone()[0]
    report['with_expression']=conn.execute('SELECT COUNT(*) FROM canciones WHERE has_cc11=1').fetchone()[0]
    report['with_pedal']=conn.execute('SELECT COUNT(*) FROM canciones WHERE has_cc64=1').fetchone()[0]
    report['with_lyrics']=conn.execute('SELECT COUNT(*) FROM canciones WHERE has_lyrics=1').fetchone()[0]
    report['4_4_meter']=conn.execute('SELECT COUNT(*) FROM canciones WHERE numerator=4 and denominator=4').fetchone()[0]
    report['top_roland_similar']=[dict(name=n,count=c,avg_similarity=round(v,3))
        for n,c,v in conn.execute('''SELECT approximate_style,COUNT(*),
          AVG(similarity) FROM canciones WHERE similarity>=0.5
          AND approximate_style!='' GROUP BY approximate_style
          ORDER BY COUNT(*) DESC LIMIT 35''')]
    report['bpm_quantiles']=[dict(bpm=int(b),count=n) for b,n in
        conn.execute('''SELECT CAST(bpm/10 AS INT)*10 b,COUNT(*)
          FROM canciones WHERE bpm BETWEEN 40 AND 240
          GROUP BY b ORDER BY COUNT(*) DESC LIMIT 20''')]
    report['archives']=dict(conn.execute(
        "SELECT status,COUNT(*) FROM archives GROUP BY status"))
    report['zip_midi_entries']=conn.execute(
        "SELECT COALESCE(SUM(midi_entries),0) FROM archives WHERE status='ok'").fetchone()[0]
    report['duplicate_exact_files']=conn.execute('''
        SELECT COALESCE(SUM(n-1),0) FROM
        (SELECT COUNT(*) n FROM canciones WHERE status='ok' AND sha256 IS NOT NULL
         GROUP BY sha256 HAVING n>1)''').fetchone()[0]
    report['invalid_examples']=[dict(path=p,error=e) for p,e in conn.execute(
        "SELECT path,error FROM canciones WHERE status!='ok' LIMIT 35")]
    (OUT/'informe_catalogo.json').write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('CATALOG_FINISHED',json.dumps(report,ensure_ascii=False),
          flush=True)
    conn.close()


if __name__=='__main__':
    main()
