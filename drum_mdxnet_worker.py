"""MDX23C DrumSep (seis pistas) + checkpoints MDX23C locales comprobados.

La instalación nativa aporta el motor `mdxnet-infer`; los modelos
alternativos requieren YAML válido, seis salidas y carga real de pesos.
"""
from __future__ import annotations
import argparse,json,sys,re
from pathlib import Path

MODEL='aufr33-jarredou_DrumSep_model_mdx23c_ep_141_sdr_10.8059.ckpt'
STEMS=frozenset(('kick','snare','toms','hh','ride','crash'))
MANIFEST='modelos_mdx23c_adicionales.json'


def _safe(name):
    return bool(isinstance(name,str) and 2<=len(name)<=180 and name==Path(name).name
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.() +\-]*',name))


def _custom_entry(cache,name):
    try:records=json.loads((cache/MANIFEST).read_text(encoding='utf8'))
    except (OSError,ValueError):return None
    entry=records.get(name) if isinstance(records,dict) else None
    if (not isinstance(entry,dict) or entry.get('architecture')!='MDX23C'
        or entry.get('stems')!=sorted(STEMS) or not _safe(entry.get('config'))):
        return None
    return entry


def _custom_engine(cache,model_name,config_name):
    from mdxnet_infer import MDX23CInference
    if not _safe(model_name) or not _safe(config_name):
        raise ValueError('Nombres de modelo no válidos')
    model=cache/model_name;yaml=cache/config_name
    if not model.is_file() or not yaml.is_file():
        raise FileNotFoundError('Falta el checkpoint o el YAML del motor de batería.')
    engine=MDX23CInference(model_path=model,config_path=yaml,device='cpu')
    if frozenset(engine.stem_names)!=STEMS:
        raise ValueError('Este checkpoint no reconoce las seis salidas de batería requeridas.')
    return engine


def main(argv=None):
    parser=argparse.ArgumentParser(description='Desglose de batería mediante IA MDX23C (seis stems)')
    parser.add_argument('source',nargs='?')
    parser.add_argument('--model_filename',default=MODEL)
    parser.add_argument('--model_file_dir',required=True)
    parser.add_argument('--config_filename',default=None)
    parser.add_argument('--validate_model_only',action='store_true')
    parser.add_argument('--download_model_only',action='store_true')
    parser.add_argument('--output_dir')
    parser.add_argument('--output_format',default='FLAC',choices=('FLAC','WAV'))
    parser.add_argument('--bit_depth',type=int,default=24,choices=(16,24))
    parser.add_argument('--sample_rate',type=int,default=44100,choices=(44100,48000))
    parser.add_argument('--overlap',type=int,default=4)
    parser.add_argument('--batch_size',type=int,default=1)
    parser.add_argument('--log_level',default='info')
    args=parser.parse_args(argv)
    cache=Path(args.model_file_dir).expanduser().resolve()
    name=args.model_filename
    if not _safe(name):raise ValueError('Nombre de pesos no válido')
    original=(name==MODEL)
    if args.download_model_only:
        if not original:raise ValueError('Un modelo adicional se importa desde archivos; no existe descarga automática.')
        from mdxnet_infer import MDX23CInference
        files=MDX23CInference.download_model('drumsep-6stem',cache_dir=cache)
        print('MODELO_BATERIA_SHA256_VERIFICADO',str(files),flush=True)
        return 0
    if args.validate_model_only:
        from mdxnet_infer import MDX23CInference
        if original:
            engine=MDX23CInference.from_pretrained('drumsep-6stem',cache_dir=cache,device='cpu',progress=False)
        else:
            if not args.config_filename:raise ValueError('Se requiere el YAML del checkpoint alternativo.')
            engine=_custom_engine(cache,name,args.config_filename)
        print('MODELO_BATERIA_VALIDADO',name,','.join(engine.stem_names),flush=True)
        return 0
    if not args.source or not args.output_dir:
        raise ValueError('Falta audio de batería o carpeta de resultados')
    source=Path(args.source).expanduser().resolve()
    dest=Path(args.output_dir).expanduser().resolve()
    if not source.is_file():raise FileNotFoundError(source)
    dest.mkdir(parents=True,exist_ok=True)
    if not 1<=args.overlap<=8 or not 1<=args.batch_size<=4:
        raise ValueError('Solapamiento (1-8) y lote (1-4) fuera de rango')
    import soundfile as sf
    import numpy as np
    from mdxnet_infer import MDX23CInference
    if original:
        engine=MDX23CInference.from_pretrained(
            'drumsep-6stem',cache_dir=cache,device='cpu',progress=True)
    else:
        entry=_custom_entry(cache,name)
        if entry is None:
            raise ValueError('Este modelo de batería no está validado en el catálogo local.')
        engine=_custom_engine(cache,name,entry['config'])
    samples,sr=sf.read(source,always_2d=True,dtype='float32')
    if samples.shape[1]!=2:
        raise ValueError('La entrada preparada para IA debe ser estéreo.')
    # batch_size y overlap son parámetros efectivos de MDX23CInference.
    print('PARAMETROS_INFERENCIA batch_size='+str(args.batch_size)+
          ' overlap='+str(args.overlap),flush=True)
    stems=engine.separate(samples,sample_rate=sr,batch_size=args.batch_size,
                          overlap=args.overlap,progress=True)
    if frozenset(stems)!=STEMS:raise ValueError('El motor no generó las seis pistas.')
    # La inferencia trabaja internamente a 44.1 kHz; si se exporta a 48 kHz,
    # remuestrear las muestras, NO cambiar simplemente la cabecera del WAV.
    if args.sample_rate!=engine.config.audio.sample_rate:
        import librosa
    extension='.flac' if args.output_format=='FLAC' else '.wav'
    encoding='PCM_24' if args.bit_depth==24 else 'PCM_16'
    for part,array in stems.items():
        if args.sample_rate!=engine.config.audio.sample_rate:
            array=librosa.resample(np.asarray(array,dtype=np.float32).T,
                 orig_sr=engine.config.audio.sample_rate,
                 target_sr=args.sample_rate).T
        final=dest/(source.stem+'_'+part+extension)
        sf.write(str(final),array,args.sample_rate,format=args.output_format,
                 subtype=encoding)
        if final.stat().st_size<=4096:
            raise RuntimeError('La salida '+final.name+' está vacía.')
    print('PARAMETROS_EXPORTACION formato='+args.output_format+
          ' profundidad='+str(args.bit_depth)+' frecuencia='+str(args.sample_rate),flush=True)
    print('MODELO_BATERIA_SEIS_STEMS_OK',flush=True)
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('ERROR MOTOR BATERIA:',str(exc),file=sys.stderr,flush=True)
        sys.exit(1)
