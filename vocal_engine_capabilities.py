"""Detección de parámetros REALES de los motores vocales existentes.

No se atribuyen a un peso externo capacidades que no tenga un
adaptador instalado y probado. Se importan los rangos definidos en los
workers concretos en uso, y se valida la estructura del checkpoint
oficial de OpenVoice antes de habilitarlo.
"""
from __future__ import annotations

from functools import lru_cache
import inspect
import json
from pathlib import Path

NEURAL_KNOBS = (
    ("tau","Tau neuronal",0,100,30,"%",
     "Parámetro τ real del conversor de OpenVoice (0.00–1.00)."),
    ("chunk_seconds","Fragmento",2,10,5,"s",
     "Segundos de audio por lote de inferencia neuronal."),
    ("overlap_ms","Solape",30,450,120,"ms",
     "Transición entre lotes para reducir cortes audibles."),
)

@lru_cache(maxsize=4)
def _analyze_known(identifier):
    if identifier=="local":
        from vocal_clone_engine import PARAM_RANGES, convert
        if "params" not in inspect.signature(convert).parameters:
            raise ValueError("Firma del motor espectral incompatible.")
        return {
            "id":identifier,"name":"Transferencia espectral DSP",
            "available":True,"parameters":dict(PARAM_RANGES),
            "groups":["Identidad / tono","Estilo / carácter"],
            "method":"DSP sobre referencia de voz, no clonación neuronal",
            "detail":"Motor verificado por su función convert() y rangos internos.",
        }
    if identifier=="openvoice_v2":
        from vocal_openvoice_engine import RANGES,model_ready,locations,process,_revoice
        names=inspect.signature(_revoice).parameters
        if "tau" not in names or "chunk_seconds" not in names or "overlap" not in names:
            raise ValueError("La versión del motor no admite parámetros neuronales extendidos.")
        if "values" not in inspect.signature(process).parameters:
            raise ValueError("Firma del backend OpenVoice incompatible.")
        actual=dict(RANGES)
        expected={name:(minimum,maximum)
                  for name,_,minimum,maximum,*_ in NEURAL_KNOBS}
        if not expected.items() <= actual.items():
            raise ValueError("El motor neuronal no reconoce todos los parámetros de la vista.")
        model,vendor=locations()
        ready=model_ready()
        reason="Modelo oficial y conversor localizados."
        if ready:
            config=json.loads((model/"config.json").read_text(encoding="utf8"))
            if config.get("_version_")!="v2" or not (
               isinstance(config.get("model"),dict) and
               config.get("data",{}).get("sampling_rate")==22050):
                ready=False
                reason="La configuración del modelo no coincide con OpenVoice V2."
        else:
            reason="Faltan pesos oficiales o código del motor."
        return {
            "id":identifier,"name":"OpenVoice V2 · conversión neuronal",
            "available":ready,"parameters":actual,
            "groups":["Identidad / tono","Estilo / carácter","Motor neuronal"],
            "method":"Conversión neuronal de timbre + DSP de posproceso",
            "detail":reason,
        }
    from vocal_voice_models import read_catalog
    match=next((r for r in read_catalog() if r["id"]==identifier),None)
    if match:
        return {
            "id":identifier,"name":match.get("name","Modelo importado"),
            "available":False,"parameters":{},"groups":[],
            "method":"Pesos importados sin motor identificado",
            "detail":"No se detectó un backend validado para ejecutar "
                     +str(match.get("type","este archivo"))+
                     ". Es necesario integrar su arquitectura antes de mostrar ajustes.",
        }
    return {
        "id":identifier,"name":"Motor desconocido","available":False,
        "parameters":{},"groups":[],"method":"No ejecutable",
        "detail":"No existe un adaptador verificado para este motor.",
    }

def analyze(identifier):
    # Importados pueden añadirse o eliminarse durante la sesión; no se cachean.
    try:
        if identifier in ("local","openvoice_v2"):
            return dict(_analyze_known(identifier))
        return _analyze_known(identifier)
    except (ImportError,OSError,ValueError,TypeError,KeyError) as exc:
        return {
            "id":identifier,"name":str(identifier),"available":False,
            "parameters":{},"groups":[],"method":"Falló auditoría",
            "detail":str(exc),
        }

def enumerate_vocal_pipeline():
    """Módulos detectados en el sistema y su correspondencia con la interfaz."""
    from vocal_tune_engine import render
    from vocal_interpretation_engine import transfer
    return (
        {
            "id":"vocal_tune","name":"Afinador monofónico DSP",
            "section":"Afinación","available":callable(render),
            "settings":tuple(inspect.signature(render).parameters),
        },
        {
            "id":"vocal_interpretation","name":"Transferencia interpretativa",
            "section":"Interpretación","available":callable(transfer),
            "settings":tuple(inspect.signature(transfer).parameters),
        },
        {
            "id":"local","name":"Transferencia espectral",
            "section":"Clonación","available":analyze("local")["available"],
            "settings":tuple(analyze("local")["parameters"]),
        },
        {
            "id":"openvoice_v2","name":"OpenVoice V2 neuronal",
            "section":"Clonación","available":analyze("openvoice_v2")["available"],
            "settings":tuple(analyze("openvoice_v2")["parameters"]),
        },
    )
