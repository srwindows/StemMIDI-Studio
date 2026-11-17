"""Generador MIDI armónico y expresivo SIN modelo neuronal entrenado.

El análisis es tonal/simbólico: notas existentes -> contexto armónico;
acordes existentes -> melodía condicionada, o melodía -> acordes.
No es transcripción de audio ni una IA de aprendizaje profundo.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass
from piano_roll_tools import SCALES, PROGRESSIONS

@dataclass(frozen=True)
class Profile:
    name: str
    lo: int
    hi: int
    mono: bool
    legato: float
    swing: float
    dynamics: int
    pedal: bool

PROFILES={
    "Piano":Profile("Piano",48,88,False,.92,.04,16,True),
    "Violín":Profile("Violín",55,94,True,1.08,.01,13,False),
    "Trombón":Profile("Trombón",40,76,True,.81,.02,12,False),
    "Guitarra acústica":Profile("Guitarra acústica",45,83,False,.74,.10,22,False),
    "Guitarra eléctrica":Profile("Guitarra eléctrica",45,90,False,1.13,.09,24,False),
    "Flauta":Profile("Flauta",60,95,True,.86,.01,14,False),
    "Bajo":Profile("Bajo",28,64,True,.90,.04,17,False),
    "Cuerdas":Profile("Cuerdas",50,92,False,1.11,.02,17,False),
    "Arpa":Profile("Arpa",47,90,False,.94,.04,19,False),
    "Percusión afinada":Profile("Percusión afinada",40,84,True,.60,.01,19,False),
    "Metales conjunto":Profile("Metales conjunto",45,88,False,.95,.02,17,False),
    "Viento":Profile("Viento",48,88,True,.84,.03,13,False),
}
def profile_for_program(program:int, preferred="Automático")->Profile:
    if preferred in PROFILES:return PROFILES[preferred]
    n=max(0,min(127,int(program)))
    if 0<=n<=7 or 16<=n<=23:return PROFILES["Piano"]
    if 24<=n<=25:return PROFILES["Guitarra acústica"]
    if 26<=n<=31:return PROFILES["Guitarra eléctrica"]
    if 32<=n<=39:return PROFILES["Bajo"]
    if 40<=n<=45:return PROFILES["Violín"]
    if n==46:return PROFILES["Arpa"]
    if n==47:return PROFILES["Percusión afinada"]
    if 48<=n<=55:return PROFILES["Cuerdas"]
    if 56<=n<=60:return PROFILES["Trombón"] if n in (57,58) else PROFILES["Viento"]
    if 61<=n<=63:return PROFILES["Metales conjunto"]
    if 64<=n<=79:return PROFILES["Flauta"] if n in (72,73,74,75) else PROFILES["Viento"]
    if 80<=n<=87:return PROFILES["Viento"]
    return PROFILES["Piano"]

def _bar_notes(notes,bar,bar_ticks):
    left=bar*bar_ticks
    right=left+bar_ticks
    return [n for n in notes if n["start"]<right and n["end"]>left]

def _chord_pc(notes,bar,bar_ticks,root,scale,previous,randomizer):
    degrees=SCALES[scale]
    options=[]
    for degree in range(len(degrees)):
        pitches={ (root+degrees[(degree+shift)%len(degrees)])%12
                  for shift in (0,2,4)}
        fundamental=(root+degrees[degree])%12
        section=_bar_notes(notes,bar,bar_ticks)
        score=0.
        for n in section:
            dur=min(n["end"],(bar+1)*bar_ticks)-max(n["start"],bar*bar_ticks)
            weight=max(.15,min(1.5,dur/max(1,bar_ticks/2)))
            if (n["start"]-bar*bar_ticks)%max(1,bar_ticks//4)<bar_ticks*.04:
                weight*=1.6
            score+=weight*(2.4 if n["pitch"]%12 in pitches else -.95)
            if n["pitch"]%12==fundamental:score+=weight*.35
        if previous is not None:
            overlap=len(pitches & previous)
            score+=overlap*.21
            if pitches==previous:score-=.6
        score+=randomizer.uniform(-.35,.35)
        options.append((score,pitches,fundamental))
    options.sort(key=lambda entry:entry[0],reverse=True)
    # Softly randomize between near-best harmonic alternatives.
    best=options[0][0]
    eligible=[option for option in options if option[0]>=best-1.1]
    return randomizer.choice(eligible[:3])

def harmonic_plan(existing,tpb,bars,root=0,scale="Mayor",seed=None,
                  mode="Auto",progression="I–V–vi–IV"):
    """Lista (pitch classes, root pitch class) por compás.

    En Auto, si hay notas en el proyecto se condiciona a ellas.
    En Libre se genera una progresión nueva y variable.
    """
    rng=random.Random(seed)
    bar_ticks=4*tpb
    notes=[n for n in existing if n.get("end",0)>n.get("start",0)]
    follow=bool(notes) and mode!="Libre"
    out=[]
    previous=None
    progress=PROGRESSIONS.get(progression,PROGRESSIONS["I–V–vi–IV"])
    degrees=SCALES[scale]
    variants=list(progress)
    # En Libre, incluso con la misma progresión prefijada, variación de
    # grados e inversión según peso tonal para no repetir cuatro compases.
    for bar in range(bars):
        if follow and _bar_notes(notes,bar,bar_ticks):
            _,pcs,fundamental=_chord_pc(notes,bar,bar_ticks,root,scale,previous,rng)
        elif follow and out:
            pcs,fundamental=out[-1]
        else:
            degree=variants[bar%len(variants)]
            # Círculo de quintas explícito: respetar el orden ii→V→I
            # (o iii→vi→ii→V→I) sin sustituir grados al azar. En las
            # demás progresiones sí se permiten pequeñas variantes.
            strict_circle=(progression.startswith("Círculo de quintas")
                           or progression.startswith("Cadencia de quintas"))
            if not strict_circle:
                if bar%4==0 and bar>0 and rng.random()<.35:
                    degree=rng.choice((0,3,4,5))
                elif rng.random()<.23:
                    degree=rng.choice((degree,(degree+2)%len(degrees),
                                       (degree-2)%len(degrees)))
            fundamental=(root+degrees[degree%len(degrees)])%12
            pcs={(root+degrees[(degree+shift)%len(degrees)])%12
                  for shift in (0,2,4)}
        out.append((frozenset(pcs),int(fundamental)))
        previous=set(pcs)
    return out,("existente" if follow else "nueva")

def _nearest_note(pc,desired,lo,hi):
    valid=[p for p in range(lo,hi+1) if p%12==pc]
    return min(valid,key=lambda p:abs(p-desired)) if valid else max(lo,min(hi,desired))

# Interpretación y estructura musical v2. Se mantienen las funciones
# públicas originales para la interfaz y para importar desde otros módulos.
from composition_musical_v2 import melodic_phrase, harmonic_accompaniment
