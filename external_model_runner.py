#!/usr/bin/env python3
"""Adaptador para checkpoints MDXC externos con YAML local, sin modificar IA.

Este proceso independiente utiliza las clases públicas de audio-separator.
No descarga modelos desconocidos ni confía en rutas externas al workspace.
"""
import json,os,sys
from pathlib import Path

def main():
    from audio_separator.separator import Separator
    from audio_separator.utils.cli import main as engine_main
    workspace=Path(os.environ.get('STEMMIDI_WORKSPACE',
        str(Path.home()/'Library/Application Support/StemMIDI Studio'))).resolve()
    manifest=workspace/'modelos'/'modelos_externos.json'
    try:
        entries=json.loads(manifest.read_text(encoding='utf8'))
        if not isinstance(entries,dict):entries={}
    except (OSError,ValueError):entries={}
    original=Separator.download_model_files
    def local_or_builtin(self,filename):
        entry=entries.get(filename)
        if not isinstance(entry,dict) or entry.get('catalog_known') is not False:
            return original(self,filename)
        family=entry.get('family')
        if family not in ('MDXC','MDX','VR') or entry.get('filename')!=filename:
            raise ValueError('Modelo personalizado incompatible con este motor.')
        files=entry.get('files',[])
        config=entry.get('config')
        if not isinstance(files,list) or filename not in files:
            raise ValueError('Los archivos de este modelo no están registrados.')
        if family=='MDXC' and (not isinstance(config,str) or config not in files):
            raise ValueError('La configuración YAML del modelo MDXC no está registrada.')
        folder=(workspace/'modelos'/('voces' if entry.get('role')=='vocal' else '')).resolve()
        path=(folder/filename).resolve()
        config_path=(folder/config).resolve() if config else None
        if (path.parent!=folder or not path.is_file() or path.stat().st_size<1024 or
            (family=='MDXC' and (config_path.parent!=folder or
             not config_path.is_file() or config_path.stat().st_size<=50))):
            raise ValueError('Faltan los pesos o el YAML de este modelo externo.')
        actual=Path(self.model_file_dir).resolve()
        if actual!=folder:
            raise ValueError('Directorio del modelo externo distinto de su biblioteca.')
        self.model_friendly_name=str(entry.get('display',filename))[:100]
        self.model_is_uvr_vip=False
        return filename,family,self.model_friendly_name,str(path),config
    Separator.download_model_files=local_or_builtin
    return engine_main()

if __name__=='__main__':raise SystemExit(main())
