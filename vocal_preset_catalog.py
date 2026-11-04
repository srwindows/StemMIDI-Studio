"""Presets vocales únicos para pestaña y ventana flotante.

Dos UIs consumen el mismo catálogo; las entradas se normalizan con la
configuración por defecto antes de aplicarlas para evitar arrastrar
efectos/ganancias de un preset seleccionado anteriormente.
"""
from __future__ import annotations

from copy import deepcopy


ADDITIONAL_VOCAL_PRESETS = {
    "Balada íntima":{
        "strength":68,"retune":170,"humanize":37,"threshold":18,
        "compression":24,"highpass":70,"character":"Dulce",
        "character_amount":55,"warmth":30,"air":11,
        "presence":18,"deesser":34,"gate":8,"reverb":18,
        "wet":100,"doubler":10,"delay":12,"delay_ms":340},
    "Pop moderno":{
        "strength":92,"retune":45,"humanize":12,"threshold":5,
        "compression":48,"highpass":90,"character":"Natural",
        "warmth":14,"presence":48,"air":38,"deesser":52,
        "gate":24,"reverb":14,"doubler":25,"delay":14},
    "Soul cálido":{
        "strength":72,"retune":155,"humanize":35,"threshold":18,
        "compression":40,"highpass":75,"character":"Cálida",
        "character_amount":50,"warmth":46,"presence":23,
        "air":10,"deesser":28,"reverb":16,"doubler":12},
    "Rock frontal":{
        "strength":70,"retune":120,"humanize":30,"threshold":17,
        "compression":53,"highpass":90,"character":"Rasgada",
        "character_amount":47,"warmth":22,"presence":53,
        "air":21,"deesser":41,"gate":20,"reverb":8,
        "doubler":18,"delay":11,"delay_ms":115},
    "Voz hablada · podcast":{
        "bypass_tune":True,"compression":45,"highpass":95,
        "character":"Natural","character_amount":0,"warmth":18,
        "presence":35,"deesser":45,"gate":30,"reverb":0,
        "doubler":0,"delay":0,"wet":100},
    "Acústica natural":{
        "strength":54,"retune":198,"humanize":40,"threshold":21,
        "compression":17,"highpass":65,"character":"Natural",
        "warmth":13,"presence":15,"air":9,"deesser":22,
        "gate":5,"reverb":7,"doubler":0,"delay":0},
    "Efecto robótico":{
        "strength":100,"retune":20,"humanize":0,"threshold":0,
        "compression":57,"highpass":90,"character":"Natural",
        "presence":35,"air":20,"reverb":0,"doubler":15},
}


def merged_vocal_presets(existing,defaults):
    merged={**deepcopy(existing),**deepcopy(ADDITIONAL_VOCAL_PRESETS)}
    return {
        name:{**deepcopy(defaults),**params}
        for name,params in merged.items()
    }
