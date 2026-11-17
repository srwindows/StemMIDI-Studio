"""Transformaciones MIDI no destructivas para Piano Roll.
No adivina notas equivocadas: aplica umbrales musicales explícitos.
"""
from __future__ import annotations
import math
import random

SCALES={
    "Mayor":(0,2,4,5,7,9,11),
    "Menor natural":(0,2,3,5,7,8,10),
    "Menor armónica":(0,2,3,5,7,8,11),
    "Pentatónica mayor":(0,2,4,7,9),
    "Pentatónica menor":(0,3,5,7,10),
}
PROGRESSIONS={
    "I–V–vi–IV":(0,4,5,3),
    "I–vi–IV–V":(0,5,3,4),
    "ii–V–I–I":(1,4,0,0),
    "i–VI–III–VII":(0,5,2,6),
    "I–IV–V–I":(0,3,4,0),
    "Círculo de quintas (iii–vi–ii–V–I)":(2,5,1,4,0),
    "Cadencia de quintas (vi–ii–V–I)":(5,1,4,0),
    "Clásica aprendida (OpenScore CC0)":(0,4,5,3),
}
def pitches(root,scale):
    return set((root+interval)%12 for interval in SCALES[scale])

def grid_ticks(tpb,division):
    return max(1,round(tpb*4/int(division)))

def quantize(notes,tpb,division=16,strength=100,ends=False):
    """Ajustar inicio y, opcionalmente, fin conservando duración positiva."""
    step=grid_ticks(tpb,division)
    weight=max(0,min(100,int(strength)))/100.
    result=[]
    for n in notes:
        note=dict(n)
        start=int(note["start"])
        target=round(start/step)*step
        adjusted=max(0,round(start+(target-start)*weight))
        if ends:
            finish=int(note["end"])
            goal=round(finish/step)*step
            end=max(adjusted+1,round(finish+(goal-finish)*weight))
        else:end=adjusted+max(1,int(note["end"])-start)
        note["start"],note["end"]=adjusted,end
        result.append(note)
    return sorted(result,key=lambda n:(n["start"],n["pitch"],n["end"]))

def clean(notes,tpb,min_duration=0.08,min_velocity=8,remove_out_of_scale=False,
          root=0,scale="Mayor",deduplicate=True,align_outliers=False,division=16,
          tolerance=0.25,sensitivity=0,context_notes=None):
    """Heurísticas de falsas activaciones para MIDI derivado de audio.

    No decide si una nota está afinada por comparación con el audio;
    identifica ecos casi coincidentes, impulsos muy cortos, fragmentos
    anómalos y filtros explícitos. Siempre devuelve una COPIA.
    sensibilidad=0 conserva los umbrales tradicionales.
    """
    import bisect
    duration=max(1,round(tpb*float(min_duration)))
    step=grid_ticks(tpb,division)
    allowed=pitches(root,scale)
    sens=max(0,min(100,int(sensitivity)))
    ordered=sorted((dict(n) for n in notes),
                   key=lambda n:(n["start"],n["pitch"],n["end"]))
    discarded={"cortas":0,"velocidad":0,"repetidas":0,
        "fuera_escala":0,"fuera_compas":0,"ecos":0,"fragmentos":0}
    # Duplicados exactos con canales distintos se conservan.
    base=[];seen=set()
    for note in ordered:
        start=int(note["start"]);end=int(note["end"])
        if end-start<duration:
            discarded["cortas"]+=1;continue
        if int(note["velocity"])<int(min_velocity):
            discarded["velocidad"]+=1;continue
        if remove_out_of_scale and note["pitch"]%12 not in allowed:
            discarded["fuera_escala"]+=1;continue
        if align_outliers:
            deviation=abs(start-round(start/step)*step)
            if deviation>step*float(tolerance):
                discarded["fuera_compas"]+=1;continue
        key=(start,end,int(note["pitch"]),int(note["channel"]))
        if deduplicate and key in seen:
            discarded["repetidas"]+=1;continue
        seen.add(key);base.append(note)
    if sens==0 or len(base)<2:return base,discarded

    # Mediana local contextual. Si solo se eligieron unas notas,
    # comparar contra las NO seleccionadas sin modificarlas.
    reference=sorted(context_notes if context_notes is not None else base,
                     key=lambda n:n["start"])
    starts=[int(n["start"]) for n in reference]
    discard=set()
    from statistics import median
    for idx,n in enumerate(base):
        start=int(n["start"]);end=int(n["end"])
        velocity=int(n["velocity"]);length=max(1,end-start)
        radius=2*tpb
        lo=bisect.bisect_left(starts,start-radius)
        hi=bisect.bisect_right(starts,start+radius)
        neighbors=[]
        skipped_self=False
        for other in reference[lo:min(hi,lo+64)]:
            if other["channel"]!=n["channel"]:continue
            if not skipped_self and all(other.get(k)==n.get(k)
                                        for k in ("start","end","pitch","velocity")):
                skipped_self=True
                continue
            neighbors.append(other)
        if not neighbors:continue
        med_vel=median(x["velocity"] for x in neighbors)
        med_len=median(max(1,x["end"]-x["start"]) for x in neighbors)
        # Espurias de transcripción: pequeñas respecto a la frase local
        # Y flojas; un trino/acento rápido pero fuerte permanece intacto.
        if (length<max(tpb*(.09+sens*.0015),med_len*(.17+sens*.002))
            and velocity<med_vel*(.31+sens*.0042)):
            discard.add(idx)
            discarded["fragmentos"]+=1
    # Duplicado probable por doble onset en la misma altura.
    near=max(2,round(tpb*(.02+sens*.00025)))
    for idx,n in enumerate(base):
        if idx in discard:continue
        # Si el modelo de selección contiene solo el eco, buscar la nota
        # estable dentro del contexto, pero nunca borrar las de fuera.
        if context_notes is not None:
            lo=bisect.bisect_left(starts,n["start"]-near)
            hi=bisect.bisect_right(starts,n["start"]+near)
            skipped_self=False
            for other in reference[lo:hi]:
                if other["pitch"]!=n["pitch"] or other["channel"]!=n["channel"]:
                    continue
                if not skipped_self and all(other.get(k)==n.get(k)
                                            for k in ("start","end","pitch","velocity")):
                    skipped_self=True
                    continue
                if min(n["end"],other["end"])<=max(n["start"],other["start"]):
                    continue
                score0=(n["end"]-n["start"])*max(15,n["velocity"])
                score1=(other["end"]-other["start"])*max(15,other["velocity"])
                if score0<score1:
                    discard.add(idx);discarded["ecos"]+=1
                    break
    for idx,n in enumerate(base):
        if idx in discard:continue
        j=idx+1
        while j<len(base) and base[j]["start"]-n["start"]<=near:
            other=base[j]
            if (j not in discard and other["pitch"]==n["pitch"]
                and other["channel"]==n["channel"]
                and min(n["end"],other["end"])>max(n["start"],other["start"])):
                # Conservar la nota más larga, salvo dinámica muy superior.
                score0=(n["end"]-n["start"])*max(15,n["velocity"])
                score1=(other["end"]-other["start"])*max(15,other["velocity"])
                victim=idx if score0<score1 else j
                discard.add(victim)
                discarded["ecos"]+=1
                if victim==idx:break
            j+=1
    return [note for i,note in enumerate(base) if i not in discard],discarded

def melody(tpb,root=0,scale="Mayor",bars=4,density=75,octave=4,
           division=8,velocity=88,seed=1,channel=0):
    """Melodía diatónica con dirección y variedad deterministas."""
    rng=random.Random(seed)
    ticks=grid_ticks(tpb,division)
    allowed=SCALES[scale]
    # Incluir tónica en el ámbito de dos octavas evitando saltos absurdos.
    pitches_=[12*(octave+1)+root+interval+12*k
              for k in (-1,0,1) for interval in allowed]
    pitches_=[p for p in pitches_ if 48<=p<=96]
    if not pitches_:return []
    current=min(pitches_,key=lambda p:abs(p-(60+root)))
    events=[]
    steps=math.ceil(bars*4*tpb/ticks)
    for index in range(steps):
        if rng.randrange(100)>=density:continue
        options=sorted(pitches_,key=lambda p:(abs(p-current),abs(p-(60+root))))
        current=rng.choice(options[:min(len(options),5)])
        start=index*ticks
        if start>=bars*4*tpb:break
        end=min(bars*4*tpb,start+max(1,round(ticks*rng.choice((.72,.88,1.0)))))
        vel=max(1,min(127,int(velocity)+rng.randint(-9,9)))
        events.append(dict(start=start,end=end,pitch=current,velocity=vel,
                           channel=channel))
    return events

def chords(tpb,root=0,scale="Mayor",bars=4,progression="I–V–vi–IV",
           seventh=False,inversion=0,octave=3,velocity=84,channel=1):
    """Acordes por grados, con inversión y posibilidad de séptima."""
    degrees=SCALES[scale]
    progression_degrees=PROGRESSIONS[progression]
    result=[]
    for bar in range(bars):
        degree=progression_degrees[bar%len(progression_degrees)]
        pitches_=[]
        for delta in (0,2,4,6) if seventh else (0,2,4):
            absolute=degree+delta
            note=12*(octave+1)+root+degrees[absolute%len(degrees)]+12*(absolute//len(degrees))
            pitches_.append(note)
        for _ in range(int(inversion)%len(pitches_)):
            pitches_[0]+=12
            pitches_.sort()
        start=bar*4*tpb
        end=(bar+1)*4*tpb
        for pitch in pitches_:
            if 0<=pitch<=127:
                result.append(dict(start=start,end=end,pitch=pitch,
                                   velocity=velocity,channel=channel))
    return result
