"""Procesador paralelo y reanudable del catálogo MIDI/KAR sin tocar originales."""
from __future__ import annotations
import collections
import json
import multiprocessing as mp
from pathlib import Path
import sqlite3
import time
import zipfile
from midi_collection_catalog import (
    SOURCE,OUT,SUFFIX,_db,_ref_styles,extract,_insert)

_REFS=[]


def _start(refs):
    global _REFS
    _REFS=refs


def _parse(entry):
    rel,size,mtime=entry
    path=SOURCE/rel
    try:
        if size>14_000_000:
            raise ValueError('Too large for initial MIDI catalog')
        info=extract(path,_REFS)
    except Exception as exc:
        # MIDI libraries may throw specialist decoding exceptions for
        # malformed key signatures, vendor sysex or corrupted metadata.
        # One damaged file must never interrupt the remaining 22k files.
        info=dict(status='invalid',
                  error=(type(exc).__name__+':'+str(exc))[:180])
    return rel,size,mtime,info


def write_report(conn,refs,number):
    report={}
    report['source']=str(SOURCE)
    report['source_read_only']=True
    report['total_midi_kar_found']=number
    report['roland_reference_count']=len(refs)
    report['records']=conn.execute('SELECT COUNT(*) FROM canciones').fetchone()[0]
    report['valid']=conn.execute("SELECT COUNT(*) FROM canciones WHERE status='ok'").fetchone()[0]
    report['invalid']=conn.execute("SELECT COUNT(*) FROM canciones WHERE status!='ok'").fetchone()[0]
    for name,where in (
        ('with_drums','drum_notes>20'),
        ('multi_channel','channels>=3'),
        ('with_expression','has_cc11=1'),
        ('with_pedal','has_cc64=1'),
        ('with_lyrics','has_lyrics=1'),
        ('meter_4_4','numerator=4 AND denominator=4'),
    ):
        report[name]=conn.execute(
            "SELECT COUNT(*) FROM canciones WHERE "+where).fetchone()[0]
    report['duplicate_exact_files']=conn.execute('''
        SELECT COALESCE(SUM(n-1),0) FROM
        (SELECT COUNT(*) n FROM canciones WHERE status='ok'
        AND sha256 IS NOT NULL GROUP BY sha256 HAVING n>1)
        ''').fetchone()[0]
    report['archives_status']=dict(conn.execute(
        'SELECT status,COUNT(*) FROM archives GROUP BY status'))
    report['zip_midi_entries']=conn.execute(
        "SELECT COALESCE(SUM(midi_entries),0) FROM archives WHERE status='ok'").fetchone()[0]
    report['top_roland_similar']=[
        dict(name=n,count=c,mean_similarity=round(v,4))
        for n,c,v in conn.execute('''SELECT approximate_style,
             COUNT(*),AVG(similarity) FROM canciones
             WHERE status='ok' AND similarity>=0.55
             AND approximate_style!='' GROUP BY approximate_style
             ORDER BY COUNT(*) DESC LIMIT 30''')]
    report['most_common_tempos']=[
        dict(bpm_band=int(b),count=n)
        for b,n in conn.execute('''SELECT CAST(bpm/10 AS INT)*10 b,
            COUNT(*) n FROM canciones WHERE status='ok'
            AND bpm BETWEEN 40 AND 240 GROUP BY b ORDER BY n DESC LIMIT 12''')]
    report['invalid_examples']=[
        dict(path=p,error=e) for p,e in conn.execute(
        "SELECT path,error FROM canciones WHERE status!='ok' ORDER BY path LIMIT 35")]
    (OUT/'informe_catalogo.json').write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report


def scan_archives(conn):
    status=collections.Counter()
    archives=sorted(p for p in SOURCE.rglob('*') if p.is_file()
                    and p.suffix.lower() in ('.zip','.rar'))
    for p in archives:
        rel=str(p.relative_to(SOURCE))
        try:
            if p.suffix.lower()=='.rar':
                values=(rel,'uninspected-rar',0,0,0,'No extraction performed')
            else:
                with zipfile.ZipFile(p) as z:
                    contents=[i for i in z.infolist() if not i.is_dir()]
                    values=(rel,'ok',len(contents),
                        sum(i.filename.lower().endswith(('.mid','.midi','.kar'))
                            for i in contents),
                        sum(i.file_size for i in contents),'')
        except (OSError,ValueError,zipfile.BadZipFile,OverflowError) as exc:
            values=(rel,'invalid',0,0,0,str(exc)[:130])
        conn.execute('INSERT OR REPLACE INTO archives VALUES (?,?,?,?,?,?)',values)
        status[values[1]]+=1
    conn.commit()
    print('ARCHIVES_INSPECTED_METADATA_ONLY',dict(status),flush=True)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    c=_db(OUT/'catalogo.sqlite3')
    refs=_ref_styles()
    files=sorted(p for p in SOURCE.rglob('*')
                 if p.is_file() and p.suffix.lower() in SUFFIX)
    previous={rel:(size,mtime,status) for rel,size,mtime,status
              in c.execute('SELECT path,bytes,mtime_ns,status FROM canciones')}
    tasks=[]
    for p in files:
        st=p.stat()
        rel=str(p.relative_to(SOURCE))
        if previous.get(rel)==(st.st_size,st.st_mtime_ns,'ok'):continue
        tasks.append((rel,st.st_size,st.st_mtime_ns))
    print('INDEX_START',len(files),'ALREADY_OK',len(files)-len(tasks),
          'TO_PARSE',len(tasks),'STYLE_REFERENCES',len(refs),flush=True)
    start=time.monotonic()
    done=0;errors=0
    # Bounded worker count: preserve headroom for GUI and audio software.
    with mp.Pool(processes=8,initializer=_start,initargs=(refs,)) as pool:
        for rel,size,mtime,info in pool.imap_unordered(_parse,tasks,chunksize=10):
            _insert(c,rel,info,size,mtime)
            done+=1
            if info['status']!='ok':errors+=1
            if done%300==0:
                c.commit()
                elapsed=round(time.monotonic()-start,1)
                print('INDEX_PROGRESS',done,'/',len(tasks),
                      'INVALID',errors,'SECONDS',elapsed,flush=True)
    c.commit()
    scan_archives(c)
    report=write_report(c,refs,len(files))
    c.commit()
    print('FINAL_CATALOG',json.dumps(report,ensure_ascii=False),flush=True)
    c.close()


if __name__=='__main__':
    main()
