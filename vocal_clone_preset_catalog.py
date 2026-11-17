"""Presets de parámetros para clonación y color vocal (DSP + OpenVoice V2).

Son configuraciones reproducibles, no modelos entrenados ni promesas de
clonar emociones o de producir una técnica de canto determinada.
Cada preset completa los 12 controles y no modifica archivos de audio.
"""
from __future__ import annotations
from copy import deepcopy

PRESET_OVERRIDES = {
    'Natural': {},
    'Clonación fiel': {'similarity': 95, 'timbre': 98, 'dynamics': 40, 'resonance': 25, 'air': 10},
    'Clonación sutil': {'similarity': 70, 'timbre': 78, 'resonance': 18, 'dynamics': 38, 'air': 12},
    'Timbre original': {'similarity': 0, 'timbre': 0, 'resonance': 0, 'dynamics': 0, 'articulation': 0, 'air': 0},
    'Grave cálida': {'similarity': 75, 'timbre': 86, 'pitch': -2, 'formants': -2, 'resonance': 48, 'brightness': -30, 'air': 8},
    'Grave profundo': {'similarity': 82, 'timbre': 88, 'pitch': -5, 'formants': -4, 'resonance': 55, 'brightness': -33, 'air': 5},
    'Aguda clara': {'similarity': 82, 'timbre': 88, 'pitch': 2, 'formants': 2, 'brightness': 28, 'air': 28, 'resonance': 19},
    'Brillante juvenil': {'similarity': 82, 'timbre': 85, 'pitch': 3, 'formants': 2, 'brightness': 36, 'air': 38},
    'Suave aireada': {'similarity': 76, 'timbre': 82, 'brightness': 5, 'air': 55, 'rasp': 0, 'dynamics': 58, 'articulation': 14},
    'Aterciopelada': {'similarity': 75, 'timbre': 85, 'resonance': 46, 'brightness': -28, 'air': 8, 'rasp': 0, 'articulation': 18},
    'Rasgada potente': {'similarity': 80, 'timbre': 90, 'rasp': 65, 'resonance': 40, 'brightness': 12, 'articulation': 63, 'dynamics': 57},
    'Balada íntima': {'similarity': 78, 'timbre': 86, 'air': 22, 'dynamics': 78, 'articulation': 16, 'vibrato': 20},
    'Balada dramática': {'similarity': 82, 'timbre': 90, 'dynamics': 90, 'articulation': 34, 'vibrato': 36, 'rasp': 12},
    'Pop moderno': {'similarity': 86, 'timbre': 91, 'resonance': 24, 'brightness': 22, 'dynamics': 55, 'articulation': 48, 'air': 32},
    'Rock directo': {'similarity': 85, 'timbre': 89, 'resonance': 39, 'brightness': 14, 'dynamics': 62, 'articulation': 77, 'rasp': 38},
    'Soul / R&B': {'similarity': 82, 'timbre': 91, 'resonance': 43, 'brightness': -13, 'dynamics': 75, 'articulation': 30, 'vibrato': 27},
    'Jazz cálido': {'similarity': 79, 'timbre': 90, 'resonance': 46, 'brightness': -22, 'dynamics': 60, 'articulation': 27, 'air': 18},
    'Acústica natural': {'similarity': 60, 'timbre': 70, 'resonance': 18, 'brightness': 0, 'dynamics': 50, 'articulation': 22, 'air': 10},
    'Flamenco expresivo': {'similarity': 84, 'timbre': 90, 'resonance': 40, 'dynamics': 76, 'articulation': 72, 'rasp': 28, 'vibrato': 17},
    'Rap definido': {'similarity': 82, 'timbre': 85, 'resonance': 26, 'brightness': 17, 'dynamics': 35, 'articulation': 90, 'vibrato': 0},
    'Canto lírico suave': {'similarity': 78, 'timbre': 88, 'resonance': 39, 'brightness': 8, 'dynamics': 68, 'articulation': 23, 'vibrato': 34},
    'Falsete luminoso': {'similarity': 70, 'timbre': 80, 'pitch': 5, 'formants': 3, 'brightness': 33, 'air': 47, 'rasp': 0},
    'Locución de radio': {'similarity': 75, 'timbre': 89, 'resonance': 48, 'brightness': 16, 'dynamics': 29, 'articulation': 65, 'stereo': 0},
    'Podcast natural': {'similarity': 70, 'timbre': 82, 'resonance': 30, 'brightness': 6, 'dynamics': 35, 'articulation': 48, 'stereo': 0},
    'Narración cálida': {'similarity': 77, 'timbre': 85, 'formants': -1, 'resonance': 45, 'brightness': -18, 'dynamics': 55, 'articulation': 58, 'stereo': 0},
    'Coro ancho': {'similarity': 70, 'timbre': 78, 'resonance': 29, 'air': 35, 'dynamics': 42, 'stereo': 175},
}

def factory_presets(defaults):
    if not isinstance(defaults,dict):
        raise TypeError("Valores por defecto inválidos")
    expected=set(defaults)
    presets={}
    for name,overrides in PRESET_OVERRIDES.items():
        if not isinstance(name,str) or not name or set(overrides)-expected:
            raise ValueError("Preset de fábrica inválido: "+str(name))
        merged={**deepcopy(defaults),**overrides}
        presets[name]=merged
    return presets
