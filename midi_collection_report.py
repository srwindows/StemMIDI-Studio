"""Reports from the private MIDI/KAR catalog. Does not touch original files."""
import collections
import csv
import json
from pathlib import Path
import sqlite3
from midi_collection_catalog import OUT

SYNTH={'Sintetizador melódico','Sintetizador pads','Sintetizador FX'}

def arrangement(family,drums,notes):
    if notes<20:return 'Pocas notas melodicas'
    total=sum(family.values())
    if total<1:return 'Instrumentacion no identificada'
    def share(*names):
        return sum(family.get(n,0) for n in names)/total
    piano=share('Piano','Órgano')
    guitar=share('Guitarra')
    strings=share('Cuerdas','Conjunto')
    bass=share('Bajo')
    synth=share(*SYNTH)
    winds=share('Metales','Lengüetas','Tubo')
    if drums>30:
        if synth>.38:return 'Bateria y sintetizadores'
        if guitar>.23 and bass>.08:return 'Bateria guitarra y bajo'
        if piano>.35:return 'Bateria y teclados'
        if winds>.20:return 'Bateria y vientos/metales'
        return 'Bateria y diversos instrumentos'
    if strings>.45:return 'Cuerdas predominantes'
    if piano>.55:return 'Piano/teclados predominantes'
    if guitar>.45:return 'Guitarra predominante'
    if winds>.40:return 'Vientos/metales predominantes'
    if synth>.45:return 'Sintetizadores predominantes'
    return 'Instrumentacion variada sin bateria GM'

def confidence(style,similarity,margin,drums):
    if not style or drums<35:return 'Sin referencia suficiente'
    if similarity>=.77 and margin>=.075:return 'Similitud ritmica alta'
    if similarity>=.62 and margin>=.04:return 'Similitud ritmica intermedia'
    return 'Similitud no concluyente'

def main():
    db=OUT/'catalogo.sqlite3'
    if not db.is_file():raise RuntimeError('Missing database')
    with sqlite3.connect(db) as conn:
        c=conn.cursor()
        duplicates={sha for sha,n in c.execute(
            "SELECT sha256,COUNT(*) FROM canciones WHERE status='ok' "
            "AND sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*)>1")}
        arrangements=collections.Counter()
        styles=collections.Counter()
        output=OUT/'clasificacion_preliminar.csv'
        with output.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream,delimiter=';')
            writer.writerow(['ruta_relativa','estado','incidencia','tamano_bytes',
                'pistas','canales','programas_gm','bpm_estimado','compas',
                'compases_estimados','notas_melodicas','golpes_bateria',
                'cc64_pedal','cc11_expresion','texto_karaoke_presente',
                'tipo_de_arreglo_estimado','ritmo_roland_similar',
                'similitud_ritmica','margen_similitud',
                'confianza_similitud','duplicado_exacto','genero_verificado'])
            for row in c.execute('SELECT path,status,error,bytes,sha256,tracks,'
                'channels,programs,bpm,numerator,denominator,approx_bars,'
                'melodic_notes,drum_notes,has_cc64,has_cc11,has_lyrics,'
                'family,approximate_style,similarity,margin '
                'FROM canciones ORDER BY path'):
                (path,status,error,size,sha,tracks,channels,programs,bpm,
                 numerator,denominator,bars,notes,drums,pedal,expression,
                 lyrics,family,style,score,margin)=row
                family=json.loads(family) if family else {}
                group=arrangement(family,drums or 0,notes or 0)
                similarity_level=confidence(style,score or 0,margin or 0,drums or 0)
                if status=='ok':
                    arrangements[group]+=1
                    if similarity_level=='Similitud ritmica alta':styles[style]+=1
                writer.writerow([path,status,error or '',size,tracks or 0,
                    channels or 0,programs or 0,bpm or '',
                    str(numerator)+'/'+str(denominator) if numerator else '',
                    bars or '',notes or 0,drums or 0,pedal or 0,
                    expression or 0,lyrics or 0,group if status=='ok' else '',
                    style or '',score or '',margin or '',
                    similarity_level,int(sha in duplicates), ''])
    summary=json.loads((OUT/'informe_catalogo.json').read_text())
    rows=[
        '# Analisis privado de MIDI y KAR',
        '',
        'Fuente: '+summary['source'],
        'MIDI/KAR detectados: '+str(summary['total_midi_kar_found']),
        'Validos: '+str(summary['valid']),
        'No parseables: '+str(summary['invalid']),
        '3 o mas canales: '+str(summary['multi_channel']),
        'Con bateria GM: '+str(summary['with_drums']),
        'Con expresion CC11: '+str(summary['with_expression']),
        'Con pedal CC64: '+str(summary['with_pedal']),
        'Copias exactas adicionales: '+str(summary['duplicate_exact_files']),
        'Entradas MIDI en ZIP (solo enumeradas): '+str(summary['zip_midi_entries']),
        '',
        '## Agrupacion preliminar por instrumentacion',
        '',
    ]
    for name,n in arrangements.most_common():
        rows.append('- '+name+': '+str(n))
    rows+=['','## Mayor semejanza ritmica con estilos Roland','','']
    for name,n in styles.most_common(30):rows.append('- '+name+': '+str(n))
    rows+=['','## Limitaciones',
        '- Tipo de arreglo NO significa genero musical verificado.',
        '- Parecido de bateria a un patron Roland NO prueba el genero.',
        '- Tempo y compases aproximados si hay cambios posteriores.',
        '- Los archivos zip y rar no han sido descomprimidos.',
        '- Las letras de karaoke no se han guardado.',
        '- Todos los archivos fuente permanecen sin cambios.',
        '- Las composiciones pueden tener derechos de terceros. Verificar',
        '  autorizaciones antes de entrenar modelos redistribuibles.',
        '- La columna genero_verificado del CSV esta vacia para revision humana.',
        '',
        'Archivos: catalogo.sqlite3, informe_catalogo.json,',
        'clasificacion_preliminar.csv y RESUMEN.md.'
    ]
    (OUT/'RESUMEN.md').write_text('\n'.join(rows)+'\n',encoding='utf8')
    print('CLASSIFICATION_REPORTED',
          sum(arrangements.values()),'VALID_FILES;',
          'STRONG_RHYTHM_MATCHES',sum(styles.values()),flush=True)

if __name__=='__main__':
    main()
