"""Composición simbólica con motivos, frases, voces y dinámica musical.

Motor de reglas, NO modelo neuronal entrenado. Salida MIDI reproducible por semilla.
"""
import math
import random
from piano_roll_tools import SCALES

def bar_length(tpb,meter=(4,4)):
    return max(1,round(tpb*4*meter[0]/meter[1]))

def detect_tonality(notes,root=0,scale="Mayor"):
    """Detecta centro tonal en notas reales, ponderando inicio y bajo.

    Conserva la selección explícita si la música encaja, y propone una
    tonalidad distinta si hay evidencias suficientes. Algoritmo heurístico.
    """
    if not notes:return root,scale,0.
    keys=("Mayor","Menor natural","Menor armónica")
    pcs=[0.]*12
    for n in notes:
        if n.get("end",0)<=n.get("start",0):continue
        p=int(n["pitch"])%12
        w=max(.18,min(3.,(n["end"]-n["start"])/480))
        if int(n["start"])%480<30:w*=1.35
        if n["pitch"]<55:w*=1.12
        pcs[p]+=w
    total=sum(pcs)
    if not total:return root,scale,0.
    preferred=SCALES.get(scale,SCALES["Mayor"])
    coverage=sum(pcs[(root+step)%12] for step in preferred)/total
    if coverage>=.93:return root,scale,coverage
    # Premiar consonancia de escala y centros de tónica/dominante;
    # no aplicar penalización indiscriminada a notas cromáticas de paso.
    score=[]
    for key in keys:
        steps=SCALES[key]
        for tonic in range(12):
            included=sum(pcs[(tonic+k)%12] for k in steps)/total
            tonic_w=pcs[tonic]/total
            dominant_w=pcs[(tonic+7)%12]/total
            fifth_w=pcs[(tonic+(4 if key=="Mayor" else 3))%12]/total
            goodness=included+(.12*tonic_w+.06*dominant_w+.04*fifth_w)
            if tonic==root and key==scale:goodness+=.018
            score.append((goodness,included,tonic,key))
    score.sort(reverse=True)
    best=score[0]
    # No renombrar tonalidad si hay pocos indicios; evita oscilaciones.
    if best[1]<coverage+.045 or best[1]<.83:return root,scale,coverage
    return best[2],best[3],best[1]


def context_plan(existing,tpb,bars,root,scale,seed,mode,progression,meter,
                 rhythm_style=None):
    """Armonización tonal global: no elegir cada acorde de forma aislada.

    Viterbi sobre los siete acordes diatónicos con costes de consonancia,
    conducción de voces y cadencia. Los acordes aportados por el usuario
    tienen prioridad sobre las probabilidades de progresión.
    """
    from composition_adaptive import harmonic_plan
    bar=bar_length(tpb,meter)
    notes=[n for n in existing if n.get("end",0)>n.get("start",0)]
    # La pentatónica describe la colección MELODICA. La armonía usa
    # acordes de la escala heptatónica relativa, nunca tríadas
    # artificiales formadas por 5 grados pentatónicos.
    functional_scale=("Mayor" if scale=="Pentatónica mayor" else
                      "Menor natural" if scale=="Pentatónica menor" else scale)
    if not notes or mode=="Libre":
        if progression=="Colección personal (MIDI/KAR)":
            from composition_personal_learned import learned_plan
            private_plan=learned_plan(root,scale,bars,seed,rhythm_style)
            if private_plan is not None:
                return private_plan,"modelo MIDI personal privado"
        if progression=="Clásica aprendida (OpenScore CC0)":
            from composition_learned import learned_plan
            learned=learned_plan(root,scale,bars,seed)
            if learned is not None:
                return learned,"modelo OpenScore CC0"
        plan,origin=harmonic_plan((),tpb,bars,root,functional_scale,
                                 seed,mode,progression)
        # Una pieza acabada debe cerrar con V→I, no terminar por
        # accidente en IV después de repetir I–V–vi–IV tres veces.
        # NO alterar progresiones de círculo explícitas ni sus ciclos.
        if bars>=8 and progression=="I–V–vi–IV":
            degrees=SCALES[functional_scale]
            for offset,degree in ((-2,4),(-1,0)):
                fundamental=(root+degrees[degree])%12
                pcs=frozenset((root+degrees[(degree+k)%len(degrees)])%12
                              for k in (0,2,4))
                plan[offset]=(pcs,fundamental)
        return plan,origin
    rng=random.Random(seed)
    personal_learned=(progression=="Colección personal (MIDI/KAR)")
    degrees=SCALES[functional_scale]
    chords=[(frozenset((root+degrees[(d+i)%len(degrees)])%12
                        for i in (0,2,4)), (root+degrees[d])%12)
            for d in range(len(degrees))]
    # Agregación por compás y clase tonal en UNA sola pasada. Antes,
    # una composición de 64 compases con 20.000 notas implicaba
    # 7*64*20.000 comprobaciones repetidas y congelaba la ventana.
    histograms=[[0.]*12 for _ in range(bars)]
    for n in notes:
        begin=max(0,int(n["start"])//bar)
        end=min(bars-1,(max(1,int(n["end"]))-1)//bar)
        if begin>=bars:continue
        for b in range(begin,end+1):
            left=b*bar;right=left+bar
            overlap=max(0,min(n["end"],right)-max(n["start"],left))
            if overlap<=0:continue
            weight=min(2.,overlap/max(1.,bar/3))
            # Dar prioridad a los apoyos de la melodía y a notas
            # sostenidas: la armonía no debe seguir un adorno fugaz.
            if left<=n["start"]<left+bar*.12:weight*=1.65
            elif left+bar*.49<=n["start"]<left+bar*.56:weight*=1.18
            velocity=int(n.get("velocity",85))
            weight*=max(.75,min(1.22,velocity/85))
            histograms[b][int(n["pitch"])%12]+=weight
    emissions=[]
    for histogram in histograms:
        total=sum(histogram)
        scores=[]
        for pcs,fundamental in chords:
            matched=sum(histogram[pc] for pc in pcs)
            score=(2.2*matched-1.08*(total-matched)
                   +.27*histogram[fundamental]
                   +rng.uniform(-.12,.12))
            scores.append(score)
        emissions.append(scores)
    transitions={(1,4):1.25,(3,4):1.35,(4,0):1.65,
                 (4,5):.72,(5,1):.75,(0,3):.60,
                 (0,5):.48,(3,0):.85}
    dp=[emissions[0][d]+(.20 if d==0 else 0) for d in range(7)]
    back=[]
    for b in range(1,bars):
        scores=[];prev=[]
        for d in range(7):
            candidates=[]
            for k in range(7):
                common=len(chords[k][0]&chords[d][0])
                progression_bonus=transitions.get((k,d),0)
                if progression=="Clásica aprendida (OpenScore CC0)":
                    from composition_learned import transition_bonus
                    progression_bonus+=.65*transition_bonus(
                        functional_scale,k,d)
                elif personal_learned:
                    from composition_personal_learned import transition_bonus
                    progression_bonus+=.65*transition_bonus(
                        functional_scale,k,d,rhythm_style)
                repeated=.3 if k==d else 0
                if b%4==3 and d==0:progression_bonus+=.35
                candidates.append(dp[k]+common*.10+progression_bonus+repeated)
            winner=max(range(7),key=lambda k:candidates[k])
            scores.append(candidates[winner]+emissions[b][d])
            prev.append(winner)
        dp=scores;back.append(prev)
    index=max(range(7),key=lambda d:dp[d])
    order=[index]
    for step in reversed(back):
        index=step[index]
        order.append(index)
    order.reverse()
    return [chords[d] for d in order],"existente"

def nearest(pc,target,lo,hi):
    opts=[p for p in range(max(21,lo),min(108,hi)+1) if p%12==pc]
    return min(opts,key=lambda p:abs(p-target)) if opts else max(lo,min(hi,target))

def make_rhythm(rng,slots,density,style=None,bar_index=0):
    target=max(2,min(9,round((2+6*density/100)*slots/16)))
    beats={0,slots//2} if style is None else {0}
    others=[i for i in range(1,slots) if i not in beats]
    if style is not None:
        from rhythm_style_catalog import groove_strength
        weights=[max(.05,groove_strength(style,i,slots,bar_index)*
                     (1.15 if i%max(1,slots//4)==0 else 1.))
                 for i in others]
    else:
        weights=[1.7 if i%max(1,slots//4)==0 else .95 if i%2==0 else .43
                 for i in others]
    while len(beats)<target and others:
        j=rng.choices(range(len(others)),weights=weights,k=1)[0]
        beats.add(others.pop(j));weights.pop(j)
    return sorted(beats)

def _expressive_shape(tick,tpb,meter):
    """Arco gradual de frase (8 y 4 compases), continuo entre compases."""
    bar=bar_length(tpb,meter)
    position=max(0.,float(tick)/max(1,bar))
    return (.68*math.sin(2*math.pi*(position/8-.24))+
            .32*math.sin(2*math.pi*(position/4-.12)))


def _expression_cc11(tick,tpb,meter,dynamics):
    depth=max(0.,min(1.,float(dynamics)/100))
    return max(1,min(127,round(109+21*depth*
                               _expressive_shape(tick,tpb,meter))))


def expression_events(rng,tpb,bars,meter,channel,profile,notes,pedal,plan,
                      pedal_amount=75,dynamics=100):
    import mido
    bar=bar_length(tpb,meter)
    cc=[]
    # CC11: una rampa continua, no saltos de volumen por bloques.
    # 16 muestras por compás (a 120 BPM, ~125 ms en 4/4).
    for b in range(bars):
        for i in range(16):
            tick=b*bar+round(i*bar/16)
            v=_expression_cc11(tick,tpb,meter,dynamics)
            cc.append((tick,mido.Message(
                "control_change",channel=channel,control=11,value=v,time=0)))
        if profile.name in ("Violín","Cuerdas"):
            cc.append((b*bar,mido.Message(
                "control_change",channel=channel,control=1,
                value=max(10,min(74,round(31+14*math.sin(b*.65)))),time=0)))
    cc.append((bars*bar,mido.Message(
        "control_change",channel=channel,control=11,value=127,time=0)))
    # Pedaleo independiente por registro y por transición armónica. Las
    # notas graves jamás quedan sostenidas con CC64 al entrar el acorde
    # siguiente. A diferencia de una nota MIDI, CC64 afecta al canal entero.
    if pedal and profile.pedal and notes and pedal_amount>0:
        from composition_pedal import pedal_events
        cc.extend(pedal_events(notes,plan,bars,tpb,meter,channel,pedal_amount))
    return sorted(cc,key=lambda item:(item[0],item[1].control))

def melodic_phrase(tpb,root=0,scale="Mayor",bars=4,density=75,octave=4,
                   division=8,velocity=88,seed=None,channel=0,existing=(),
                   mode="Auto",instrument="Automático",program=0,
                   progression="I–V–vi–IV",pedal=True,meter=(4,4),
                   pedal_amount=75,dynamics=100,rhythm_style=None,
                   generator_bpm=120,ligatures=False,pitch_bounds=None):
    from composition_adaptive import profile_for_program
    rng=random.Random(seed)
    profile=profile_for_program(program,instrument)
    from rhythm_style_catalog import profile as get_style
    style=get_style(rhythm_style)
    bars=max(1,int(bars))
    bar=bar_length(tpb,meter)
    plan,source=context_plan(existing,tpb,bars,root,scale,
                            rng.randrange(2**32),mode,progression,meter,
                            rhythm_style=rhythm_style)
    # El tempo de composición influye en el fraseo, NUNCA en los metadatos
    # de reproducción ni en las figuras ya existentes en el MIDI.
    generator_bpm=max(35,min(300,int(generator_bpm)))
    effective_density=max(10,min(100,round(density*generator_bpm/120)))
    slots=max(16,int(division)*2)
    grid=bar/slots
    pcs={(root+n)%12 for n in SCALES[scale]}
    if pitch_bounds is None:
        mel_lo,mel_hi=profile.lo,profile.hi
        center=max(mel_lo,min(mel_hi,12*(octave+1)+root))
    else:
        mel_lo,mel_hi,center=(int(x) for x in pitch_bounds)
        mel_lo=max(21,mel_lo);mel_hi=min(108,mel_hi)
        center=max(mel_lo,min(mel_hi,center))
        if mel_hi<mel_lo:raise ValueError("Rango melódico inválido")
    current=center
    notes=[]
    patterns={}
    contour=[rng.choice((-2,-1,0,1,2)) for _ in range(8)]
    classical_learned=(progression=="Clásica aprendida (OpenScore CC0)")
    personal_learned=(progression=="Colección personal (MIDI/KAR)")
    previous_step=0
    for b,(chord,fundamental) in enumerate(plan):
        phrase=b//4;position=b%4
        if phrase not in patterns:
            patterns[phrase]=make_rhythm(rng,slots,effective_density,style,phrase*4)
        # Para estilos con base Roland, conservar el carácter del motivo
        # pero dejar que cada compás siga la acentuación real de su patrón.
        rhythm=(make_rhythm(rng,slots,effective_density,style,b)
                if style is not None else patterns[phrase][:])
        if position==1:
            rhythm=[min(slots-1,i+(i%2)) for i in rhythm]
        elif position==2:
            rhythm=[max(0,i-rng.choice((0,0,1))) for i in rhythm]
        elif position==3:
            rhythm=[i for i in rhythm if i<slots*.72]
        rhythm=sorted(set(rhythm)) or [0]
        for k,i in enumerate(rhythm):
            strong=i in (0,slots//2)
            cadence=position==3 and k==len(rhythm)-1
            candidates=chord if strong or cadence or rng.random()<.75 else pcs
            goal=current+contour[(k+position)%len(contour)]*2
            if classical_learned:
                from composition_learned import sample_interval
                learned_delta=sample_interval(previous_step,rng)
                if learned_delta is not None:
                    goal=current+learned_delta
            elif personal_learned:
                from composition_personal_learned import sample_interval
                learned_delta=sample_interval(previous_step,rng,rhythm_style)
                if learned_delta is not None:
                    goal=current+learned_delta
            if cadence:goal=center+(fundamental-root)%12
            # El modelo Markov aporta intervalos, pero no puede sacar
            # la melodía del registro de su voz ni forzar deriva de octavas.
            if pitch_bounds is not None:
                goal=max(mel_lo,min(mel_hi,round(center+.72*(goal-center))))
            options=[p for p in range(mel_lo,mel_hi+1)
                     if p%12 in candidates]
            if not options:continue
            options.sort(key=lambda p:abs(p-goal)*.65+abs(p-current)*.7)
            pitch=nearest(fundamental,goal,mel_lo,mel_hi) if cadence else rng.choice(options[:min(2,len(options))])
            start=round(b*bar+i*grid+(rng.gauss(0,tpb*.016) if i else 0))
            start=max(b*bar,min((b+1)*bar-1,start))
            next_slot=rhythm[k+1] if k+1<len(rhythm) else slots
            gap=max(1,round((next_slot-i)*grid))
            length=round(gap*rng.uniform(
                .80,1.08) * profile.legato) if generator_bpm<90 else round(
                gap*rng.uniform(.6,1.04)*profile.legato)
            if cadence:length=max(length,round(gap*.99))
            end=max(start+1,min((b+1)*bar+round(tpb*.1),start+length))
            # Velocidad de ataque independiente del volumen CC11 sostenido.
            # El arco de la frase es continuo, no cuatro niveles discretos.
            depth=max(0.,min(1.,dynamics/100))
            curve=13*depth*_expressive_shape(start,tpb,meter)
            attack=(5 if strong else -3 if i%2 else 1)*depth
            from rhythm_style_catalog import groove_velocity
            style_accent=groove_velocity(style,i,slots,b)
            vel=max(27,min(123,round(velocity+curve+attack+
                       style_accent*.52*depth+
                       rng.gauss(0,max(2,profile.dynamics*.35)*depth))))
            notes.append(dict(start=start,end=end,pitch=pitch,
                              velocity=vel,channel=channel))
            previous_step=pitch-current
            current=pitch
    notes.sort(key=lambda n:(n["start"],n["pitch"]))
    # Una línea melódica no debe tener ataques simultáneos.
    for a,b in zip(notes,notes[1:]):
        if a["end"]>b["start"]:a["end"]=max(a["start"]+1,b["start"])
    if not notes:
        notes=[dict(start=0,end=tpb,pitch=center,velocity=velocity,channel=channel)]
    if ligatures:
        from composition_ligatures import link_melody
        notes=link_melody(notes,tpb,100,mono=profile.mono)
    return notes,expression_events(rng,tpb,bars,meter,channel,profile,
                   notes,pedal,plan,pedal_amount,dynamics),source,profile.name

def _voicing(pcs,fundamental,low,previous,seventh_pc,
             floor=43,ceiling=84):
    tones=sorted(pcs,key=lambda p:(p-fundamental)%12)
    if fundamental not in tones:tones.insert(0,fundamental)
    # Séptima DIATÓNICA de la escala/tonalidad real, NO b7 fija.
    # Ejemplo: Do mayor I=Do-Mi-Sol-Si; V=Sol-Si-Re-Fa.
    if seventh_pc is not None and seventh_pc not in tones:
        tones.append(seventh_pc)
    voice=[]
    for i,pc in enumerate(tones[:4]):
        options=[p for p in range(max(21,floor),min(108,ceiling)+1)
                 if p%12==pc]
        target=max(floor,min(ceiling,low+5*i))
        reference=previous[min(i,len(previous)-1)] if previous else target
        if options:
            # Afinidad con ancla fija por encima de la altura anterior.
            # Evita escaladas continuas por inversión en cada compás.
            voice.append(min(options,key=lambda p:
                1.55*abs(p-target)+.75*abs(p-reference)))
    return sorted(set(voice))

def harmonic_accompaniment(tpb,root=0,scale="Mayor",bars=4,velocity=84,
                           seed=None,channel=0,existing=(),mode="Auto",
                           instrument="Automático",program=0,
                           arpeggiate=False,progression="I–V–vi–IV",
                           seventh=False,inversion=0,octave=3,meter=(4,4),
                           pedal=False,pedal_amount=75,dynamics=100,
                           return_events=False,rhythm_style=None,
                           generator_bpm=120,ligatures=False,pitch_bounds=None):
    from composition_adaptive import profile_for_program
    rng=random.Random(seed)
    profile=profile_for_program(program,instrument)
    from rhythm_style_catalog import profile as get_style
    style=get_style(rhythm_style)
    bars=max(1,int(bars));bar=bar_length(tpb,meter)
    generator_bpm=max(35,min(300,int(generator_bpm)))
    plan,source=context_plan(existing,tpb,bars,root,scale,
                        rng.randrange(2**32),mode,progression,meter,
                        rhythm_style=rhythm_style)
    # Antes el piano arrancaba un octavo demasiado grave:
    # low=C2(36) con margen -6 => arpegios A1(33), como en
    # prueba.mid. Piano y guitarra necesitan una tesitura musical
    # de acompañamiento, manteniendo los bajos legítimos en Bajo.
    if pitch_bounds is not None:
        floor,ceiling,low=(int(x) for x in pitch_bounds)
        floor=max(21,floor);ceiling=min(108,ceiling)
        low=max(floor,min(ceiling,low))
        if ceiling-floor<12:raise ValueError("Registro armónico estrecho")
    else:
        if profile.name=="Bajo":
            low=max(36,min(48,12*(octave+1)+root-12))
        else:
            low=max(48,min(65,12*(octave+1)+root))
        floor=(profile.lo if profile.name=="Bajo"
               else max(43,profile.lo-5))
        ceiling=min(profile.hi,84)
    notes=[];previous=None
    for b,(pcs,fundamental) in enumerate(plan):
        seventh_pc=None
        if seventh:
            functional_scale=("Mayor" if scale=="Pentatónica mayor"
                      else "Menor natural" if scale=="Pentatónica menor" else scale)
            degrees=SCALES[functional_scale]
            degree=next((i for i,step in enumerate(degrees)
                         if (root+step)%12==fundamental),None)
            if degree is not None:
                seventh_pc=(root+degrees[(degree+6)%len(degrees)])%12
        voice=_voicing(pcs,fundamental,low,previous,
                       seventh_pc,floor,ceiling)
        for _ in range(int(inversion)):
            if voice:voice=sorted(voice[1:]+[min(84,voice[0]+12)])
        previous=voice[:]
        if not voice:continue
        base=b*bar
        depth=max(0.,min(1.,dynamics/100))
        curve=12*depth*_expressive_shape(base,tpb,meter)
        if arpeggiate:
            order=list(range(len(voice)))
            # Vaivén musical: arpegio ascendente y descendente,
            # no una escalera de notas que sube indefinidamente.
            if len(voice)>=3:
                if b%4==0:order=[0,1,2,1,0,1]
                elif b%4==1:order=[2,1,0,1,2,1]
                elif b%4==2:order=[0,2,1,0,1,2]
                else:order=[1,2,1,0,1,0]
            elif len(voice)==2:
                order=[0,1,0,1] if b%2==0 else [1,0,1,0]
            if style is not None:
                from rhythm_style_catalog import groove_pulses
                offsets=[round(slot*bar/16) for slot in
                         groove_pulses(style,rng,b,arpeggio=True)]
            else:
                steps=max(6,2*len(order))
                offsets=[round(i*bar/steps) for i in range(steps)]
            # A tempo lento, menos ataques y duraciones más largas.
            if generator_bpm<110 and len(offsets)>3:
                spacing=max(1,round(120/generator_bpm))
                offsets=offsets[::spacing]
            for i,offset in enumerate(offsets):
                start=max(base,base+offset+(0 if i==0 else rng.randint(-3,6)))
                next_offset=(offsets[i+1] if i+1<len(offsets) else bar)
                length_factor=(rng.uniform(.84,1.04) if generator_bpm<90
                               else rng.uniform(.72,1.12))
                end=min(base+bar,start+round(
                    max(1,next_offset-offset)*length_factor))
                pitch=voice[order[i%len(order)]]
                from rhythm_style_catalog import groove_velocity
                style_accent=groove_velocity(style,round(offset*16/bar),16,b)
                vel=max(28,min(123,round(velocity+curve+
                    (5 if i%len(order)==0 else -3)*depth+
                    style_accent*.52*depth+
                    rng.gauss(0,max(1,5*depth)))))
                notes.append(dict(start=start,end=max(start+1,end),pitch=pitch,
                                  velocity=vel,channel=channel))
        else:
            # Alternar un acorde sostenido y un patrón rítmico de dos ataques.
            if style is not None:
                from rhythm_style_catalog import groove_pulses
                pulses=[round(slot*bar/16) for slot in
                        groove_pulses(style,rng,b,arpeggio=False)]
            else:
                pulses=[0,bar//2] if b%4 in (1,2) and rng.random()<.78 else [0]
            if generator_bpm<90 and len(pulses)>1:
                pulses=pulses[::2]
            for k,attack in enumerate(pulses):
                gap=(pulses[k+1] if k+1<len(pulses) else bar)-attack
                for i,pitch in enumerate(voice):
                    strum=(round(tpb*.022*i) if profile.name.startswith("Guitarra") else 0)
                    start=base+attack+strum
                    end=max(start+1,base+attack+round(gap*rng.uniform(.77,.96)))
                    from rhythm_style_catalog import groove_velocity
                    style_accent=groove_velocity(style,round(attack*16/bar),16,b)
                    vel=max(27,min(123,round(velocity+curve+
                             (5-i*1.6+style_accent*.52)*depth+
                             rng.gauss(0,max(1,5*depth)))))
                    notes.append(dict(start=start,end=end,pitch=pitch,
                                      velocity=vel,channel=channel))
    if ligatures and notes:
        from composition_ligatures import tie_generated_chords
        notes,_=tie_generated_chords(notes,tpb,meter)
    if return_events:
        events=expression_events(rng,tpb,bars,meter,channel,profile,
                                 notes,pedal,plan,pedal_amount,dynamics)
        return notes,events,source,profile.name
    return notes,source,profile.name
