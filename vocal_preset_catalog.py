"""Catálogo compartido de presets de AFINACIÓN VOCAL y efectos.

Lo consumen la pestaña principal y el módulo vocal ampliado. Los presets
guardan exclusivamente parámetros, nunca voces, archivos ni referencias.
Los valores son puntos de partida audibles, no análisis automáticos de tonalidad.
"""
from __future__ import annotations
from copy import deepcopy

# Entradas de fábrica: parámetros reales del motor de afinación vocal.
# No se fuerza una tónica específica. La tónica/escala del proyecto se
# mantienen al aplicar un preset de estilo desde la interfaz principal.
ADDITIONAL_VOCAL_PRESETS = {
    "Afinación natural · estudio":{},
    "Afinación sutil": {"strength":48,"retune":205,"humanize":67,"threshold":8,"compression":17,"highpass":70,"reverb":5},
    "Afinación equilibrada":{"strength":72,"retune":130,"humanize":48,"threshold":14,"compression":29,"highpass":80,"reverb":9},
    "Afinación precisa":{"strength":95,"retune":65,"humanize":16,"threshold":5,"compression":36,"highpass":85,"reverb":8},
    "Afinación extrema":{"strength":100,"retune":20,"humanize":0,"threshold":0,"compression":44,"highpass":90,"reverb":5},
    "Afinación progresiva":{"strength":83,"retune":105,"humanize":55,"threshold":15,"compression":23,"highpass":80,"reverb":7},
    "Estudio seco · sin reverb":{"strength":78,"retune":105,"humanize":30,"threshold":12,"compression":24,"highpass":85,"reverb":0,"delay":0,"doubler":0},
    "Voz transparente":{"strength":58,"retune":185,"humanize":58,"threshold":20,"compression":15,"highpass":65,"character":"Natural","character_amount":0,"warmth":8,"presence":18,"air":12,"reverb":3,"doubler":0,"delay":0},
    "Balada íntima":{"strength":68,"retune":170,"humanize":37,"threshold":18,"compression":24,"highpass":70,"character":"Dulce","character_amount":55,"warmth":30,"air":11,"presence":18,"deesser":34,"gate":8,"reverb":18,"wet":100,"doubler":10,"delay":12,"delay_ms":340},
    "Balada romántica":{"strength":70,"retune":155,"humanize":50,"threshold":17,"compression":29,"character":"Dulce","character_amount":65,"warmth":35,"presence":14,"reverb":28,"doubler":12,"delay":20,"delay_ms":370},
    "Balada potente":{"strength":85,"retune":115,"humanize":34,"threshold":12,"compression":48,"character":"Cálida","character_amount":48,"presence":33,"reverb":25,"doubler":22,"delay":16,"delay_ms":330},
    "Pop moderno":{"strength":92,"retune":45,"humanize":12,"threshold":5,"compression":48,"highpass":90,"character":"Natural","warmth":14,"presence":48,"air":38,"deesser":52,"gate":24,"reverb":14,"doubler":25,"delay":14},
    "Pop natural":{"strength":72,"retune":140,"humanize":42,"threshold":17,"compression":34,"highpass":80,"presence":34,"air":20,"reverb":12,"doubler":12},
    "Dance / electrónica":{"strength":96,"retune":35,"humanize":8,"threshold":3,"compression":58,"highpass":100,"presence":55,"air":33,"deesser":55,"reverb":13,"doubler":45,"delay":21,"delay_ms":225},
    "Trap · autotune":{"strength":100,"retune":20,"humanize":0,"threshold":0,"compression":55,"highpass":100,"presence":52,"air":29,"reverb":15,"doubler":20,"delay":18,"delay_ms":220},
    "Urbano melódico":{"strength":93,"retune":48,"humanize":15,"threshold":6,"compression":52,"highpass":95,"presence":45,"air":30,"reverb":16,"doubler":29,"delay":20,"delay_ms":250},
    "Reguetón definido":{"strength":89,"retune":60,"humanize":20,"threshold":8,"compression":59,"highpass":100,"character":"Natural","warmth":17,"presence":55,"deesser":48,"gate":20,"reverb":8,"doubler":16,"delay":12},
    "Rap frontal":{"strength":55,"retune":180,"humanize":55,"threshold":30,"compression":60,"highpass":100,"presence":58,"deesser":46,"gate":25,"reverb":4,"delay":8,"doubler":6},
    "Soul cálido":{"strength":72,"retune":155,"humanize":35,"threshold":18,"compression":40,"highpass":75,"character":"Cálida","character_amount":50,"warmth":46,"presence":23,"air":10,"deesser":28,"reverb":16,"doubler":12},
    "R&B suave":{"strength":76,"retune":150,"humanize":48,"threshold":13,"compression":38,"highpass":70,"character":"Dulce","character_amount":45,"warmth":24,"air":21,"reverb":17,"delay":17,"delay_ms":290},
    "Jazz íntimo":{"strength":53,"retune":225,"humanize":77,"threshold":29,"compression":21,"highpass":65,"character":"Cálida","character_amount":26,"warmth":38,"air":7,"reverb":13,"doubler":0,"delay":0},
    "Blues rasgado":{"strength":59,"retune":205,"humanize":75,"threshold":25,"compression":44,"highpass":80,"character":"Rasgada","character_amount":41,"warmth":34,"presence":32,"reverb":8,"doubler":0},
    "Rock frontal":{"strength":70,"retune":120,"humanize":30,"threshold":17,"compression":53,"highpass":90,"character":"Rasgada","character_amount":47,"warmth":22,"presence":53,"air":21,"deesser":41,"gate":20,"reverb":8,"doubler":18,"delay":11,"delay_ms":115},
    "Rock alternativo":{"strength":69,"retune":150,"humanize":43,"threshold":20,"compression":56,"highpass":90,"character":"Rasgada","character_amount":32,"presence":47,"reverb":12,"doubler":25,"delay":13,"delay_ms":160},
    "Metal directo":{"strength":78,"retune":125,"humanize":23,"threshold":12,"compression":69,"highpass":105,"character":"Rasgada","character_amount":63,"warmth":14,"presence":65,"deesser":57,"gate":32,"reverb":4,"doubler":10},
    "Flamenco expresivo":{"strength":59,"retune":205,"humanize":80,"threshold":27,"compression":32,"highpass":75,"character":"Cálida","character_amount":32,"warmth":22,"presence":34,"reverb":11,"doubler":0},
    "Cumbia y salsa":{"strength":78,"retune":120,"humanize":48,"threshold":15,"compression":44,"highpass":80,"presence":45,"reverb":13,"doubler":22,"delay":8},
    "Country natural":{"strength":61,"retune":180,"humanize":65,"threshold":21,"compression":28,"highpass":75,"warmth":25,"presence":30,"reverb":14,"doubler":14,"delay":9,"delay_ms":150},
    "Acústica natural":{"strength":54,"retune":198,"humanize":40,"threshold":21,"compression":17,"highpass":65,"character":"Natural","warmth":13,"presence":15,"air":9,"deesser":22,"gate":5,"reverb":7,"doubler":0,"delay":0},
    "Coral suave":{"strength":70,"retune":158,"humanize":50,"threshold":15,"compression":25,"highpass":80,"character":"Natural","reverb":24,"doubler":34,"stereo_width":133,"output_gain_db":-2},
    "Voz lírica · suave":{"strength":57,"retune":230,"humanize":87,"threshold":31,"compression":13,"highpass":65,"character":"Cálida","character_amount":20,"reverb":22,"doubler":0},
    "Doblado pop · ancho":{"strength":78,"retune":105,"humanize":32,"threshold":14,"compression":40,"presence":40,"reverb":10,"doubler":58,"stereo_width":145,"output_gain_db":-3},
    "Voz hablada · podcast":{"bypass_tune":True,"compression":45,"highpass":95,"character":"Natural","character_amount":0,"warmth":18,"presence":35,"deesser":45,"gate":30,"reverb":0,"doubler":0,"delay":0,"wet":100},
    "Locución radio":{"bypass_tune":True,"compression":58,"highpass":100,"character":"Cálida","character_amount":24,"warmth":30,"presence":43,"deesser":45,"gate":33,"reverb":0,"doubler":0,"delay":0},
    "Narración cálida":{"bypass_tune":True,"compression":33,"highpass":75,"character":"Cálida","character_amount":27,"warmth":43,"presence":22,"gate":12,"reverb":6,"doubler":0,"delay":0},
    "Voz sin afinación · efectos":{"bypass_tune":True,"character":"Natural","character_amount":0,"reverb":8,"doubler":0,"delay":0},
    "Efecto robótico":{"strength":100,"retune":20,"humanize":0,"threshold":0,"compression":57,"highpass":90,"character":"Natural","presence":35,"air":20,"reverb":0,"doubler":15},
}

def merged_vocal_presets(existing,defaults):
    """Valores completos para ambos selectores de Afinación vocal.

    El primero reproduce exactamente los valores actuales del motor al abrir.
    Las 11 configuraciones originales permanecen disponibles.
    """
    merged={"Afinación natural · estudio":{},**deepcopy(existing),**deepcopy(ADDITIONAL_VOCAL_PRESETS)}
    return {name:{**deepcopy(defaults),**params} for name,params in merged.items()}
