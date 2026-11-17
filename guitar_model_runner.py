"""Motor dedicado RoFormer local; no modifica el audio-separator general."""
from __future__ import annotations
import argparse,os,re,subprocess,sys,tempfile,shutil
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--key',choices=('electric','acoustic','lead'),required=True)
    parser.add_argument('--model_path',required=True)
    parser.add_argument('--config_path',required=True)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output_dir',required=True)
    parser.add_argument('--overlap',type=int,default=2)
    parser.add_argument('--batch',type=int,default=1)
    args=parser.parse_args()
    model=Path(args.model_path).resolve();cfg=Path(args.config_path).resolve()
    source=Path(args.input).resolve();output=Path(args.output_dir).resolve()
    if not all(p.is_file() for p in (model,cfg,source)):
        raise FileNotFoundError('Falta algún archivo de entrada, configuración o modelo')
    if not (1<=args.overlap<=16 and 1<=args.batch<=4):
        raise ValueError('Valores de procesamiento no válidos')
    base=Path(os.environ.get('STEMMIDI_GUITAR_RUNTIME',
       str(Path.home()/'Library/Application Support/StemMIDI Studio/guitar_runtime')))
    package=base/('melband-roformer-infer' if args.key=='lead' else 'bs-roformer-infer')/'src'
    if not package.is_dir():
        raise FileNotFoundError('Falta el motor RoFormer local: '+str(package))
    sys.path.insert(0,str(package))
    ffmpeg=os.environ.get('STEMMIDI_FFMPEG') or shutil.which('ffmpeg')
    if not ffmpeg:
        raise FileNotFoundError('No se encuentra FFmpeg')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='guitar_infer_') as work:
        root=Path(work);inputfolder=root/'input';inputfolder.mkdir()
        wav=inputfolder/(source.stem+'.wav')
        subprocess.run([ffmpeg,'-nostdin','-v','error','-y','-i',str(source),
            '-ar','44100','-ac','2','-c:a','pcm_f32le',str(wav)],check=True)
        # El solapamiento es un parámetro de inferencia real admitido por ambas arquitecturas.
        yaml=cfg.read_text(encoding='utf8')
        if not re.search(r'(?m)^  num_overlap:\s*\d+',yaml):
            raise ValueError('El YAML del modelo no declara num_overlap')
        yaml=re.sub(r'(?m)^(  num_overlap:)\s*\d+',r'\g<1> '+str(args.overlap),yaml,count=1)
        custom=root/'config.yaml';custom.write_text(yaml,encoding='utf8')
        if args.key=='lead':
            from mel_band_roformer.inference import proc_folder
        else:
            from bs_roformer.inference import proc_folder
        argslist=['--model_path',str(model),'--config_path',str(custom),
            '--input_folder',str(inputfolder),'--store_dir',str(output),'--device','cpu']
        print('Modelo RoFormer:',args.key,'solapamiento:',args.overlap,flush=True)
        proc_folder(argslist)
        # Los checkpoints de guitarra declarados generan sólo el stem objetivo.
        # La pista residual se obtiene por diferencia PCM respecto al audio normalizado.
        target=[p for p in output.iterdir() if p.suffix.lower() in ('.wav','.flac')]
        if len(target)==1:
            dest=output/(source.stem+'_resto.flac')
            subprocess.run([ffmpeg,'-nostdin','-v','error','-y',
                '-i',str(wav),'-i',str(target[0]),
                '-filter_complex','[0:a][1:a]amix=inputs=2:weights=1 -1:normalize=0[a]',
                '-map','[a]','-c:a','flac',str(dest)],check=True)
        print('Separación completa:',*(x.name for x in output.iterdir() if x.is_file()),flush=True)
if __name__=='__main__':
    main()
