"""Modelos MIDI externos: únicamente Basic Pitch ONNX con firma compatible.

No son modelos de separación, ni transcriptores arbitrarios .pt/.ckpt.
Los modelos del usuario se copian sin alterar el fichero original.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from studio_paths import workspace_root

ROOT=workspace_root(__file__)
LIBRARY=ROOT/"modelos"/"audio_a_midi"
MANIFEST=LIBRARY/"modelos_importados.json"
PYTHON=ROOT/"entorno_ia"/"bin"/"python"

VALIDATOR=r'''
import sys
import onnxruntime as ort
p=sys.argv[1]
s=ort.InferenceSession(p,providers=["CPUExecutionProvider"])
ins=s.get_inputs();outs={o.name:o for o in s.get_outputs()}
if len(ins)!=1 or ins[0].name!="serving_default_input_2:0" or ins[0].type!="tensor(float)":
    raise ValueError("Entrada ONNX incompatible con Basic Pitch")
shape=ins[0].shape
if len(shape)!=3 or shape[1:]!=[43844,1]:
    raise ValueError("Basic Pitch requiere entrada de 43844 muestras y 1 canal")
expected={"StatefulPartitionedCall:1":[172,88],
          "StatefulPartitionedCall:2":[172,88],
          "StatefulPartitionedCall:0":[172,264]}
for name,ends in expected.items():
    out=outs.get(name)
    if out is None or out.type!="tensor(float)" or len(out.shape)!=3 or out.shape[1:]!=ends:
        raise ValueError("Salidas de nota, ataque y contorno incompatibles: "+name)
print("BASIC_PITCH_ONNX_SIGNATURE_VALID")
'''

def validate(path):
    file=Path(path).expanduser().resolve()
    if not file.is_file() or file.suffix.lower()!=".onnx":
        raise ValueError("Selecciona un archivo ONNX (.onnx) existente.")
    if not PYTHON.is_file():
        raise RuntimeError("Falta el motor de IA del programa.")
    if file.stat().st_size<=1000:
        raise ValueError("El fichero es demasiado pequeño para contener un modelo.")
    try:
        completed=subprocess.run([str(PYTHON),"-c",VALIDATOR,str(file)],
            capture_output=True,text=True,timeout=45,check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Tiempo agotado al comprobar el modelo ONNX.") from exc
    if completed.returncode!=0 or "BASIC_PITCH_ONNX_SIGNATURE_VALID" not in completed.stdout:
        msg=(completed.stderr or completed.stdout or "Modelo incompatible").strip()
        raise ValueError("Modelo incompatible con Basic Pitch: "+msg[-550:])
    return file

def list_models():
    try:
        data=json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        return []
    if not isinstance(data,list):return []
    output=[]
    for item in data:
        if not isinstance(item,dict):continue
        filename=item.get("file")
        name=item.get("name")
        if (not isinstance(filename,str) or Path(filename).name!=filename
                or not filename.endswith(".onnx") or not isinstance(name,str)):
            continue
        path=LIBRARY/filename
        if path.is_file() and path.stat().st_size>1000:
            output.append((name,str(path.resolve())))
    return output

def import_model(path):
    source=validate(path)
    digest=hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b""):
            digest.update(block)
    filename="basic_pitch_"+digest.hexdigest()[:16]+".onnx"
    LIBRARY.mkdir(parents=True,exist_ok=True)
    destination=LIBRARY/filename
    if not destination.is_file():
        temp=destination.with_suffix(".onnx.partial")
        try:
            shutil.copyfile(source,temp)
            # Cotejar byte a byte por SHA-256 antes del cambio atómico.
            copied=hashlib.sha256()
            with temp.open("rb") as stream:
                for block in iter(lambda:stream.read(4*1024*1024),b""):
                    copied.update(block)
            if copied.digest()!=digest.digest():
                raise IOError("La copia del modelo no coincide con el original.")
            os.replace(temp,destination)
        finally:
            temp.unlink(missing_ok=True)
    items=[]
    try:
        items=json.loads(MANIFEST.read_text(encoding="utf-8"))
        if not isinstance(items,list):items=[]
    except (OSError,ValueError):pass
    if not any(x.get("file")==filename for x in items if isinstance(x,dict)):
        items.append({"file":filename,"name":source.stem[:70]})
        stage=MANIFEST.with_suffix(".json.tmp")
        stage.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(stage,MANIFEST)
    return destination.resolve()

def registered(path):
    try:target=Path(path).resolve()
    except (ValueError,TypeError,OSError):return False
    return any(target==Path(p) for _,p in list_models())
