"""Modelos de batería personalizados: MDX23C de seis stems, con verificación real.

No acepta un modelo por su extensión solamente. El trabajador externo debe
cargar el checkpoint sin errores antes de registrar los archivos.
"""
from __future__ import annotations
from pathlib import Path
import json,os,shutil,uuid,re
from studio_paths import workspace_root

DRUM_STEMS=frozenset(('kick','snare','toms','hh','ride','crash'))
FOLDER=workspace_root(__file__)/'modelos'/'bateria'
MANIFEST=FOLDER/'modelos_mdx23c_adicionales.json'


def valid_filename(name):
    return bool(isinstance(name,str) and 2<=len(name)<=180 and
      name==Path(name).name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.() +\-]*',name))


def list_models():
    try:
        data=json.loads(MANIFEST.read_text(encoding='utf8'))
        if not isinstance(data,dict):return {}
    except (OSError,ValueError):return {}
    out={}
    for name,entry in data.items():
        if (valid_filename(name) and isinstance(entry,dict)
          and entry.get('architecture')=='MDX23C' and entry.get('stems')==sorted(DRUM_STEMS)
          and valid_filename(entry.get('config',''))):
            out[name]=entry
    return out


def config_for(filename):
    return (list_models().get(filename) or {}).get('config')


def ready(filename):
    entry=list_models().get(filename)
    if not entry:return False
    a=FOLDER/filename;b=FOLDER/entry['config']
    return bool(a.is_file() and not a.is_symlink() and a.stat().st_size>100_000
       and b.is_file() and not b.is_symlink() and b.stat().st_size>50)


def validate_candidate(weight,configuration):
    weight=Path(weight);configuration=Path(configuration)
    if (weight.suffix.lower()!='.ckpt' or configuration.suffix.lower() not in ('.yaml','.yml')
        or not all(valid_filename(x.name) for x in (weight,configuration))):
        raise ValueError('Necesitas un checkpoint MDX23C .ckpt y su configuración YAML.')
    if (not weight.is_file() or weight.is_symlink() or weight.stat().st_size<100_000
        or not configuration.is_file() or configuration.is_symlink()):
        raise ValueError('Los pesos no existen, son demasiado pequeños o son enlaces.')
    if configuration.stat().st_size>2_000_000:
        raise ValueError('El archivo YAML es demasiado grande.')
    # La aplicación gráfica no incluye PyYAML: analizar solo la cabecera
    # estructural en stdlib. El trabajador de IA hace la validación real del
    # YAML mediante FullLoader y carga el checkpoint antes de aceptarlo.
    try:raw=configuration.read_text(encoding='utf8')
    except UnicodeError as e:raise ValueError('YAML de batería ilegible: '+str(e))
    sections={}
    for section in ('audio','model','training','inference'):
        match=re.search(r'(?ms)^'+section+r':\s*\n(.*?)(?=^[A-Za-z_]+:|\Z)',raw)
        if not match:raise ValueError('No hay sección '+section+' en el YAML MDX23C.')
        sections[section]=match.group(1)
    training=sections['training']
    instruments=re.search(r'(?ms)^\s+instruments:\s*\n(.*?)(?=^\s+[a-zA-Z_]+:|\Z)',training)
    if instruments is None:
        raise ValueError('No figuran los seis instrumentos en el YAML.')
    found=set(re.findall(r'(?m)^\s*-\s*(kick|snare|toms|hh|ride|crash)\s*$',instruments.group(1)))
    if found!=DRUM_STEMS or re.search(r'(?m)^\s+target_instrument:\s*(?!null|None|~|$)\S+',training):
        raise ValueError('El modelo debe proporcionar las seis salidas: kick, snare, toms, hh, ride y crash.')
    if (re.search(r'(?m)^\s+sample_rate:\s*(?!44100\s*$)\d+',sections['audio']) or
        re.search(r'(?m)^\s+num_channels:\s*(?!2\s*$)\d+',sections['audio'])):
        raise ValueError('Por ahora se admite audio estéreo a 44.100 Hz.')
    if ((FOLDER/weight.name).exists() or (FOLDER/configuration.name).exists()
        or weight.name in list_models()):
        raise ValueError('Ya existe un modelo o configuración con ese nombre. No se sobrescribe.')
    return {'filename':weight.name,'config':configuration.name,
            'architecture':'MDX23C','stems':sorted(DRUM_STEMS),
            'display':('MDX23C · '+weight.stem)[:100]}


def stage(weight,configuration):
    info=validate_candidate(weight,configuration)
    folder=FOLDER/('.validacion_'+uuid.uuid4().hex)
    folder.mkdir(parents=True,exist_ok=False)
    try:
        for file in (weight,configuration):
            with Path(file).open('rb') as inp,(folder/Path(file).name).open('xb') as out:
                shutil.copyfileobj(inp,out,1024*1024)
        return folder,info
    except BaseException:
        shutil.rmtree(folder,ignore_errors=True)
        raise


def approve(stage_folder,info):
    """Se llama SOLO después del exit 0 de --validate_model_only."""
    folder=Path(stage_folder)
    FOLDER.mkdir(parents=True,exist_ok=True)
    new=list_models()
    if info['filename'] in new:raise ValueError('El modelo ya está registrado.')
    for name in (info['filename'],info['config']):
        if (FOLDER/name).exists():raise ValueError('El modelo ya existe: '+name)
    promoted=[]
    try:
        for name in (info['filename'],info['config']):
            source=folder/name
            if source.is_symlink() or not source.is_file():raise FileNotFoundError(name)
            os.rename(source,FOLDER/name)
            promoted.append(FOLDER/name)
        new[info['filename']]=dict(info)
        tmp=folder/'manifest.json'
        tmp.write_text(json.dumps(new,ensure_ascii=False,indent=2),encoding='utf8')
        os.replace(tmp,MANIFEST)
    except BaseException:
        for path in promoted:path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(folder,ignore_errors=True)
    return info


def abort(folder):
    shutil.rmtree(folder,ignore_errors=True)
