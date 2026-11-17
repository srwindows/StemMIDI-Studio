"""Parámetros reales compatibles con audio-separator CLI 0.22.

Separar lo global, lo propio de cada arquitectura y lo que ya se configura
por las casillas de stems. No exponer switches que el CLI no implemente.
"""
from __future__ import annotations
from collections.abc import Mapping

MODEL_FIELDS={
 'Demucs':{
  'demucs_shifts':('Pasadas',1,8,1,'--demucs_shifts'),
  'demucs_overlap':('Solapamiento',0.05,0.95,.05,'--demucs_overlap'),
  'demucs_segment_size':('Segmento (s; 0=auto)',0,7,1,'--demucs_segment_size'),
  'demucs_segments_enabled':('Procesar por segmentos',False,True,1,'--demucs_segments_enabled')},
 'MDX':{
  'mdx_overlap':('Solapamiento',.05,.95,.05,'--mdx_overlap'),
  'mdx_segment_size':('Ventana FFT',128,512,128,'--mdx_segment_size'),
  'mdx_batch_size':('Lote',1,4,1,'--mdx_batch_size'),
  'mdx_hop_length':('Salto FFT',512,2048,512,'--mdx_hop_length'),
  'mdx_enable_denoise':('Suprimir residuos',False,True,1,'--mdx_enable_denoise')},
 'MDXC':{
  'mdxc_overlap':('Solapamiento',2,50,1,'--mdxc_overlap'),
  'mdxc_batch_size':('Lote',1,4,1,'--mdxc_batch_size'),
  'mdxc_pitch_shift':('Tono (semitonos)',-6,6,1,'--mdxc_pitch_shift'),
  'mdxc_override_model_segment_size':('Sobrescribir ventana del modelo',False,True,1,'--mdxc_override_model_segment_size'),
  'mdxc_segment_size':('Ventana (FFT)',128,1024,128,'--mdxc_segment_size')},
 'VR':{
  'vr_window_size':('Ventana',320,1024,64,'--vr_window_size'),
  'vr_batch_size':('Lote',1,4,1,'--vr_batch_size'),
  'vr_aggression':('Intensidad',-100,100,1,'--vr_aggression'),
  'vr_enable_tta':('Analizar dos veces (TTA)',False,True,1,'--vr_enable_tta'),
  'vr_high_end_process':('Reconstruir agudos',False,True,1,'--vr_high_end_process'),
  'vr_enable_post_process':('Posprocesado',False,True,1,'--vr_enable_post_process'),
  'vr_post_process_threshold':('Umbral posprocesado',.10,.30,.05,'--vr_post_process_threshold')},
}

COMMON_FIELDS={
 'invert_spect':('Invertir espectrograma residual',False,True,1,'--invert_spect'),
 'use_soundfile':('Escribir con soundfile',False,True,1,'--use_soundfile'),
 'mp3_bitrate':('MP3 (kb/s)',128,320,32,'--output_bitrate'),
}


def family_for_model(filename):
    if not filename:return 'Canales L/R'
    from model_registry import record_for
    info=record_for(filename)
    family=(info or {}).get('architecture','')
    if family in MODEL_FIELDS:return family
    lower=str(filename).lower()
    if lower.startswith(('htdemucs','demucs')) or lower.endswith('.yaml') and 'demucs' in lower:
        return 'Demucs'
    if lower.endswith('.onnx'):return 'MDX'
    if lower.endswith(('.ckpt','.safetensors')):return 'MDXC'
    if lower.endswith('.pth'):return 'VR'
    return 'Modelo externo'


def values_for(family,quality=0):
    quality=max(0,min(2,int(quality)))
    defaults={
      'Demucs':{'demucs_shifts':(1,2,4)[quality],
                'demucs_overlap':(.25,.50,.65)[quality],
                'demucs_segment_size':0,'demucs_segments_enabled':True},
      'MDX':{'mdx_overlap':(.25,.50,.65)[quality],
             'mdx_segment_size':256,'mdx_batch_size':1,
             'mdx_hop_length':1024,'mdx_enable_denoise':False},
      'MDXC':{'mdxc_overlap':(8,12,16)[quality],
              'mdxc_batch_size':1,'mdxc_pitch_shift':0,
              'mdxc_segment_size':256,
              'mdxc_override_model_segment_size':False},
      'VR':{'vr_window_size':512,'vr_batch_size':1,'vr_aggression':5,
            'vr_enable_tta':False,'vr_high_end_process':False,
            'vr_enable_post_process':False,'vr_post_process_threshold':.2},
    }
    return {**defaults.get(family,{}),'invert_spect':False,
            'use_soundfile':False,'mp3_bitrate':320}


def safe_value(key,value):
    field=next((spec for group in (*MODEL_FIELDS.values(),COMMON_FIELDS)
                 for name,spec in group.items() if name==key),None)
    if field is None:raise ValueError('Parámetro de IA desconocido: '+str(key))
    _,minimum,maximum,step,_=field
    if isinstance(minimum,bool):
        if not isinstance(value,bool):raise ValueError('Se esperaba booleano: '+key)
        return value
    num=float(value)
    if not minimum<=num<=maximum:raise ValueError('Valor de IA fuera de rango: '+key)
    if isinstance(minimum,int) and isinstance(maximum,int):
        if num!=int(num):raise ValueError('Se esperaba entero: '+key)
        return int(num)
    return round(num,4)


def sanitize(overrides):
    if not isinstance(overrides,Mapping):return {}
    valid={}
    for key,value in overrides.items():
        try:valid[key]=safe_value(key,value)
        except (ValueError,TypeError,OverflowError):pass
    return valid


def command_flags(family,quality,overrides=None,*,output_format="FLAC"):
    """Filtra opciones y aplica ajustes MP3 solo al exportar MP3."""
    """Construir argumentos solo para la arquitectura y switches instalados."""
    if family not in MODEL_FIELDS: return []
    data=values_for(family,quality)
    clean=sanitize(overrides or {})
    data.update({k:v for k,v in clean.items() if k in data})
    flags=[]
    fields={**MODEL_FIELDS[family],**COMMON_FIELDS}
    for key,(*_,flag) in fields.items():
        value=data.get(key)
        if key=='mp3_bitrate':
            if str(output_format).upper()=='MP3':flags.extend([flag,str(int(value))+'k'])
            continue
        if key=='demucs_segment_size' and not value:continue
        if key=='mdxc_segment_size' and not data['mdxc_override_model_segment_size']:continue
        if key=='vr_post_process_threshold' and not data['vr_enable_post_process']:continue
        if isinstance(value,bool):
            if key=='demucs_segments_enabled':
                flags.extend([flag,'true' if value else 'false'])
            elif value:flags.append(flag)
        else:
            flags.extend((flag,str(value)))
    return flags


def merged_settings(family,quality,overrides):
    data=values_for(family,quality)
    data.update({key:value for key,value in sanitize(overrides).items() if key in data})
    return data
