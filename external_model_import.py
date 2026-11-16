"""Importación local y reversible de pesos de separación externos.

No inventar compatibilidad: pesos del catálogo o .ckpt MDXC con YAML.
No instalar scripts ni ejecutar checkpoints durante la importación.
"""
from __future__ import annotations
import json,os,re,shutil,tempfile
from pathlib import Path
from studio_paths import workspace_root

ROOT=workspace_root(__file__)
HOME=ROOT/'modelos'
MANIFEST=HOME/'modelos_externos.json'
STEMS={
 '2 pistas: voz e instrumental':['vocals','instrumental'],
 '4 pistas: voz, batería, bajo y otros':['vocals','drums','bass','other'],
 '6 pistas: voz, batería, bajo, guitarra, piano y otros':['vocals','drums','bass','guitar','piano','other'],
}
VOICE_TYPES={'Solista y coros':'lead_backing','Masculina y femenina':'male_female'}
VALID_EXT={'.ckpt','.onnx','.pth','.yaml','.yml'}
MAX_BYTES=12*1024*1024*1024

def _known_hash_model(path):
    '''MDX/VR desconocidos necesitan una huella presente en los metadatos UVR.'''
    import hashlib
    p=Path(path)
    digest=hashlib.md5()
    with p.open('rb') as handle:
        handle.seek(max(0,p.stat().st_size-10_000*1024))
        for chunk in iter(lambda:handle.read(1024*1024),b''):
            digest.update(chunk)
    database='mdx_model_data.json' if p.suffix.lower()=='.onnx' else 'vr_model_data.json'
    try:
        metadata=json.loads((HOME/database).read_text(encoding='utf8'))
        return isinstance(metadata,dict) and digest.hexdigest() in metadata
    except (OSError,ValueError,TypeError):return False

def _valid_name(name):
    return bool(0<len(name)<=180 and name==Path(name).name and
        re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.() +\-]*',name))

def records():
    try:
        obj=json.loads(MANIFEST.read_text(encoding='utf8'))
        if isinstance(obj,dict):
            return {k:v for k,v in obj.items()
                    if _valid_name(k) and isinstance(v,dict)
                    and v.get('family') in ('MDXC','MDX','VR','Demucs')
                    and v.get('role') in ('general','vocal')}
    except (OSError,ValueError,TypeError):pass
    return {}

def get(filename):return records().get(str(filename))

def voice_modes():
    return {'external_'+name:(rec.get('display',name),name)
            for name,rec in records().items() if rec.get('role')=='vocal'}

def supported_in_catalog(filename):
    import model_registry
    rec=model_registry.record_for(filename)
    return rec if rec and not rec.get('external') else None

def validate(files,role,stems=None,voice_type=None):
    paths=[Path(f).expanduser() for f in files]
    if not paths or len(paths)>12:raise ValueError('Selecciona el modelo y sus archivos auxiliares (máximo 12).')
    names=[p.name for p in paths]
    if len(set(names))!=len(names) or not all(_valid_name(n) for n in names):
        raise ValueError('Hay nombres duplicados o no admitidos; renombra los archivos antes de importar.')
    for p in paths:
        if p.is_symlink() or not p.is_file():raise ValueError('No se permiten enlaces ni carpetas como modelos: '+p.name)
        if not 1<=p.stat().st_size<=MAX_BYTES:raise ValueError('Archivo vacío o demasiado grande: '+p.name)
    weights=[p for p in paths if p.suffix.lower() in ('.ckpt','.onnx','.pth')]
    yamls=[p for p in paths if p.suffix.lower() in ('.yaml','.yml')]
    if len(weights)!=1:
        raise ValueError('Selecciona exactamente un archivo de pesos (.ckpt, .onnx o .pth).')
    main=weights[0]
    if main.stat().st_size<1024:raise ValueError('El archivo de pesos parece incompleto.')
    if any(p.suffix.lower() not in VALID_EXT for p in paths):
        raise ValueError('Formato no compatible. No se aceptan ZIP, .pt, scripts ni ejecutables.')
    if role not in ('general','vocal'):raise ValueError('Destino de IA incorrecto.')
    if role=='general' and stems not in STEMS:raise ValueError('Indica qué pistas produce el modelo.')
    if role=='vocal' and voice_type not in VOICE_TYPES:raise ValueError('Indica qué separación vocal realiza el modelo.')
    known=supported_in_catalog(main.name)
    if known:
        if role=='general' and not __import__('model_registry').is_general(known):
            raise ValueError('Este modelo del catálogo no es compatible con separación general.')
        if role=='vocal' and known.get('architecture')!='MDXC':
            raise ValueError('El separador vocal admite modelos MDXC/RoFormer con YAML.')
        needed=set(known['files'])
        if not needed.issubset(set(names)):
            raise ValueError('Faltan archivos auxiliares: '+', '.join(sorted(needed-set(names))))
        family=known['architecture']
        config=next((n for n in known['files'] if n.endswith(('.yaml','.yml'))),None)
    else:
        suffix=main.suffix.lower()
        if suffix in ('.onnx','.pth') and len(paths)==1:
            if not _known_hash_model(main):
                raise ValueError('Este MDX/VR no figura en la base de huellas de modelos compatibles del motor. No se importará como funcional hasta disponer de sus metadatos UVR.')
            family='MDX' if suffix=='.onnx' else 'VR'
            config=None
        else:
            if suffix!='.ckpt' or len(yamls)!=1 or len(paths)!=2:
                raise ValueError('Modelo desconocido: importa un .ckpt RoFormer/MDXC acompañado de YAML o un .onnx/.pth con huella reconocida por el motor.')
            family='MDXC'
            config=yamls[0].name
    if role=='vocal' and (family!='MDXC' or not config):
        raise ValueError('El motor vocal requiere un RoFormer/MDXC con configuración YAML.')
    return {'filename':main.name,'files':names,'family':family,'config':config,
      'role':role,'stems':(list(STEMS[stems]) if role=='general' else ['vocals','instrumental']),
      'voice_type':VOICE_TYPES.get(voice_type),
      'display':('Personalizado · '+main.stem)[:96],
      'catalog_known':bool(known)}

def register(files,role,stems=None,voice_type=None):
    """Importación por copia atómica: los originales jamás se tocan."""
    entry=validate(files,role,stems,voice_type)
    name=entry['filename']
    original=records()
    if name in original:raise ValueError('El modelo ya está importado: '+name)
    dest=HOME/('voces' if role=='vocal' else '')
    for file in entry['files']:
        if (dest/file).exists():
            raise ValueError('Ya existe '+file+' en la biblioteca. No se sobrescribe ningún modelo.')
    HOME.mkdir(parents=True,exist_ok=True)
    dest.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.importacion_ia_',dir=HOME) as temp:
        stage=Path(temp)
        for path in map(Path,files):
            with path.open('rb') as inp,(stage/path.name).open('xb') as out:
                shutil.copyfileobj(inp,out,1024*1024)
            if (stage/path.name).stat().st_size!=path.stat().st_size:
                raise ValueError('La copia del modelo no terminó correctamente.')
        copied=[]
        try:
            for fname in entry['files']:
                os.replace(stage/fname,dest/fname)
                copied.append(dest/fname)
            obj=dict(original)
            obj[name]=entry
            part=stage/'manifest.json'
            part.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
            os.replace(part,MANIFEST)
        except Exception:
            for file in copied:
                file.unlink(missing_ok=True)
            raise
    return entry

def add_voice_to_choices(expanded,tab_mode=None):
    """Actualizar los dos desplegables sin perder el modelo seleccionado."""
    from vocal_split_stems import MODES
    modes=voice_modes()
    for key,pair in modes.items():MODES[key]=pair
    for combo in (expanded.voice_mode,tab_mode):
        if combo is None:continue
        current=combo.currentData()
        blocked=combo.blockSignals(True)
        for key,(title,_) in modes.items():
            if combo.findData(key)<0:combo.addItem(title,key)
        if combo.findData(current)>=0:combo.setCurrentIndex(combo.findData(current))
        combo.blockSignals(blocked)

def file_dialog(parent,role,after=None):
    """Importar, mostrar fallos reales y actualizar vistas solo si tiene éxito."""
    from PySide6.QtWidgets import QFileDialog,QInputDialog,QMessageBox
    paths,_=QFileDialog.getOpenFileNames(parent,
      'Importar IA: selecciona el modelo y su YAML si lo necesita',str(Path.home()),
      'Modelos (*.ckpt *.onnx *.pth *.yaml *.yml);;Todos los archivos (*)')
    if not paths:return None
    # Si el usuario señala solo el peso, localizar el YAML habitual en
    # la MISMA carpeta; nunca descargar ni ejecutar nada automáticamente.
    if len(paths)==1 and Path(paths[0]).suffix.lower()=='.ckpt':
        main=Path(paths[0])
        known=supported_in_catalog(main.name)
        if known:
            needed=known.get('files',[])
            companions=[main.parent/name for name in needed if name!=main.name]
            if all(p.is_file() for p in companions):
                paths.extend(str(p) for p in companions)
        else:
            matches=[p for p in main.parent.glob('*.yaml')
                     if p.stem.startswith(main.stem) or
                        main.stem.startswith(p.stem.replace('_config',''))]
            matches+= [p for p in main.parent.glob('*.yml')
                       if p.stem.startswith(main.stem)]
            matches=list(dict.fromkeys(matches))
            if len(matches)==1:paths.append(str(matches[0]))
    stems=None;voice=None
    if role=='general':
        stems,ok=QInputDialog.getItem(parent,'Pistas del modelo','¿Qué pistas extrae realmente esta IA?',list(STEMS),0,False)
    else:
        voice,ok=QInputDialog.getItem(parent,'Función del modelo vocal','¿Qué tipo de voces separa?',list(VOICE_TYPES),0,False)
    if not ok:return None
    try:entry=register(paths,role,stems,voice)
    except (ValueError,OSError) as exc:
        QMessageBox.warning(parent,'No se pudo importar la IA',str(exc))
        return None
    QMessageBox.information(parent,'Modelo añadido',
      'Modelo copiado a la biblioteca sin modificar el original.\n'+entry['filename']+
      '\nArquitectura: '+entry['family']+
      '\nLa compatibilidad definitiva debe comprobarse con una separación de prueba.'+
      '\nImporta solo modelos de fuentes fiables: algunos formatos de pesos pueden contener contenido ejecutable.'+
      ('\nEsta IA dispone de YAML y utilizará el motor MDXC instalado.' if not entry['catalog_known'] else ''))
    if after:after(entry)
    return entry
