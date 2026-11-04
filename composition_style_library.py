"""Catálogo de estilos rítmicos ORIGINALES del generador StemMIDI.

No son grabaciones ni modelos aprendidos de artistas. Son plantillas
originales de ataques, síncopa y acentos, reutilizables sin disco Roland.
16 posiciones normalizadas por compás; patrones A/B y vuelta de frase.
Su propósito es condicionar acordes y melodía, NO generar batería/audio.
"""
from __future__ import annotations
from functools import lru_cache

# Familia -> pulsos de acordes A/B, notas de arpegio A/B,
# ataques melódicos A/B; valores 0..15 equivalen a 16 subdivisiones.
PATTERNS={
 "rock8":((0,8),(0,8),(0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
          (0,3,4,7,8,11,12,15),(0,2,4,6,8,10,12,14)),
 "rock16":((0,6,8,14),(0,4,10,12),
           (0,2,4,6,8,10,12,14),(0,1,4,6,8,9,12,14),
           (0,2,5,7,8,11,13,15),(0,3,4,6,9,10,12,14)),
 "ballad":((0,8),(0,),(0,4,8,12),(0,3,6,10,12),
           (0,4,7,10,13),(0,5,8,12)),
 "pop":((0,8,12),(0,6,8,12),(0,2,4,6,8,10,12,14),
        (0,2,4,6,8,10,12,14),(0,3,4,7,8,11,12),
        (0,2,6,8,10,14)),
 "funk":((0,3,7,10,14),(0,4,6,11,15),
         (0,2,3,6,8,10,11,14),(0,1,3,6,8,9,11,14),
         (0,3,6,7,10,13,15),(0,2,5,8,11,13,15)),
 "disco":((0,4,8,12),(0,4,8,12),
          (0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
          (0,2,4,7,8,10,12,15),(0,3,4,6,8,11,12,14)),
 "house":((0,4,8,12),(0,4,8,12),
          (0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
          (0,3,6,8,11,14),(0,3,7,8,11,15)),
 "techno":((0,4,8,12),(0,4,8,12),
           (0,2,4,6,8,10,12,14),(0,1,4,5,8,9,12,13),
           (0,2,5,8,10,13),(0,3,6,8,11,14)),
 "salsa":((0,5,8,10,14),(0,3,6,8,13),
          (0,2,5,7,8,10,13,15),(0,3,4,6,8,11,12,14),
          (0,3,6,8,11,14),(0,2,5,8,10,13,15)),
 "son":((0,6,10),(0,3,8,12),
        (0,3,5,8,10,13),(0,2,6,8,11,14),
        (0,3,6,10,13),(0,2,5,8,12,14)),
 "cumbia":((0,6,10,14),(0,4,8,14),
           (0,2,4,6,8,10,12,14),(0,1,4,6,8,10,12,15),
           (0,3,6,8,11,14),(0,2,5,8,11,14)),
 "bachata":((0,4,8,14),(0,4,10,12),
            (0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
            (0,3,6,8,11,14),(0,3,5,8,11,15)),
 "merengue":((0,4,8,12),(0,4,8,12),
             (0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
             (0,2,4,6,8,10,12,14),(0,2,5,7,8,10,13,15)),
 "reggaeton":((0,3,8,11),(0,3,7,11),
              (0,2,4,6,8,10,12,14),(0,2,3,6,8,10,11,14),
              (0,3,6,8,11,14),(0,3,7,9,11,15)),
 "dembow":((0,3,7,11,14),(0,3,8,11,15),
           (0,2,3,6,8,10,11,14),(0,1,3,6,8,11,13,15),
           (0,3,5,8,11,14),(0,2,6,8,11,14)),
 "trap":((0,7,11),(0,6,10,14),
         (0,2,4,6,8,10,12,14),(0,1,4,6,8,10,12,15),
         (0,4,7,8,12,15),(0,3,6,10,14)),
 "hiphop":((0,6,10),(0,6,8,13),
           (0,2,4,6,8,10,12,14),(0,2,5,6,8,10,13,14),
           (0,3,6,8,11,14),(0,4,7,9,12,15)),
 "swing":((0,6,10),(0,5,8,13),
          (0,3,6,9,12,15),(0,3,6,9,12,15),
          (0,3,6,8,11,14),(0,4,7,10,13,15)),
 "bossa":((0,3,6,10,14),(0,4,7,11,14),
          (0,2,4,6,8,10,12,14),(0,3,4,6,8,11,12,14),
          (0,4,7,10,14),(0,3,6,9,12,15)),
 "samba":((0,3,6,9,12,15),(0,2,5,8,11,14),
          (0,2,4,6,8,10,12,14),(0,1,3,5,8,9,11,14),
          (0,3,5,8,11,14),(0,2,5,7,10,13,15)),
 "tango":((0,4,8,12),(0,4,8,12),
          (0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
          (0,4,6,8,12,14),(0,3,4,8,11,12)),
 "ranchera":((0,5,10),(0,5,10),
             (0,3,5,8,10,13),(0,3,5,8,10,13),
             (0,3,5,8,10,13),(0,2,5,8,11,14)),
 "vallenato":((0,4,7,12),(0,3,8,12),
              (0,2,4,6,8,10,12,14),(0,1,4,6,8,9,12,14),
              (0,3,6,8,11,14),(0,2,5,8,10,13)),
 "blues":((0,6,10),(0,5,10),
          (0,3,6,9,12,15),(0,3,6,9,12,15),
          (0,3,7,9,12,15),(0,3,6,10,13)),
 "country":((0,4,8,12),(0,4,8,12),
            (0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
            (0,3,6,8,11,14),(0,2,4,7,10,12,14)),
 "waltz":((0,5,10),(0,5,10),
          (0,3,6,9,12,15),(0,3,6,9,12,15),
          (0,3,6,10,13),(0,3,6,9,12,15)),
 "flamenco":((0,3,6,10,13),(0,4,7,10,14),
             (0,2,4,6,8,10,12,14),(0,1,3,6,8,9,12,14),
             (0,2,5,8,11,14),(0,3,6,9,13,15)),
 "afrobeat":((0,3,6,9,12,15),(0,2,5,8,11,14),
             (0,2,4,6,8,10,12,14),(0,2,3,6,8,10,11,14),
             (0,3,6,8,11,14),(0,2,5,7,10,13)),
 "reggae":((0,4,8,12),(0,4,8,12),
           (0,2,4,6,8,10,12,14),(0,2,4,6,8,10,12,14),
           (0,3,7,11,14),(0,2,6,10,14)),
}

# Etiqueta -> familia, variación original. Los cambios de variantes
# desplazan acentos secundarios y densidad: no reutilizan el mismo perfil.
_GROUPS={
 "Rock y Pop":[
  ("Rock clásico","rock8"),("Rock 8 beat","rock8"),
  ("Rock 16 beat","rock16"),("Rock alternativo","rock16"),
  ("Hard rock","rock8"),("Heavy metal","rock16"),
  ("Punk rock","rock8"),("Rock and roll","blues"),
  ("Pop clásico","pop"),("Pop rock","pop"),
  ("Pop moderno","rock16"),("Synth pop","house"),
  ("Indie pop","pop"),("Balada romántica","ballad"),
  ("Balada pop","ballad"),("Balada rock","ballad"),
  ("Power ballad","ballad"),("Soul","funk"),("R&B","funk")],
 "Latinos y Caribe":[
  ("Salsa","salsa"),("Salsa romántica","salsa"),
  ("Salsa dura","salsa"),("Son cubano","son"),
  ("Cumbia","cumbia"),("Cumbia colombiana","cumbia"),
  ("Cumbia villera","cumbia"),("Cumbia pop","cumbia"),
  ("Bachata","bachata"),("Bachata moderna","bachata"),
  ("Merengue","merengue"),("Merengue urbano","merengue"),
  ("Reguetón","reggaeton"),("Reguetón clásico","reggaeton"),
  ("Reguetón lento","reggaeton"),("Dembow","dembow"),
  ("Vallenato","vallenato"),("Bossa nova","bossa"),
  ("Samba","samba"),("Tango","tango"),
  ("Ranchera","ranchera"),("Flamenco pop","flamenco"),
  ("Rumba flamenca","flamenco"),("Bolero","ballad")],
 "Urbano y Electrónica":[
  ("Hip hop","hiphop"),("Boom bap","hiphop"),
  ("Trap","trap"),("Trap latino","trap"),
  ("Drill","trap"),("Dancehall","reggae"),
  ("Disco","disco"),("Funk","funk"),
  ("House","house"),("Deep house","house"),
  ("Techno","techno"),("Electro dance","techno"),
  ("EDM","house"),("Drum and bass","techno"),
  ("Downtempo","hiphop")],
 "Jazz, Blues y Otros":[
  ("Jazz swing","swing"),("Jazz balada","ballad"),
  ("Jazz fusión","funk"),("Blues","blues"),
  ("Blues shuffle","blues"),("Country","country"),
  ("Country rock","rock8"),("Vals","waltz"),
  ("Vals lento","waltz"),("Góspel","funk"),
  ("Reggae","reggae"),("Ska","reggae"),
  ("Afrobeat","afrobeat"),("Highlife","afrobeat")],
}

def _register():
    output={}
    for group,choices in _GROUPS.items():
        for index,(label,family) in enumerate(choices):
            ident="motor:"+label
            assert family in PATTERNS,(label,family)
            assert ident not in output
            chords_a,chords_b,arp_a,arp_b,mel_a,mel_b=PATTERNS[family]
            # 16 subdivision weights, with accents and phrase evolution.
            signature=(chords_a,chords_b,arp_a,arp_b,mel_a,mel_b)
            bars=[]
            for bar in range(4):
                ca=chords_a if bar%2==0 else chords_b
                aa=arp_a if bar%2==0 else arp_b
                ma=mel_a if bar%2==0 else mel_b
                # Variantes de cada familia tienen ataques diferentes,
                # no solamente otro nombre para el mismo ritmo.
                variant=index%4
                chords=set(ca)
                if variant==1:
                    chords.add(12 if 12 not in chords else 14)
                elif variant==2:
                    chords.add(6 if 6 not in chords else 3)
                elif variant==3:
                    chords.add(14 if 14 not in chords else 11)
                ca=tuple(sorted(chords))
                arps=set(aa)
                if variant==1:
                    arps.add(15)
                elif variant==2:
                    arps.add(3)
                elif variant==3:
                    arps.add(7)
                aa=tuple(sorted(arps))
                shift=(index%3) if bar==3 else 0
                active={int((p+shift)%16) for p in ma}
                weights=[round(.15+1.8*(slot in active)+
                              .6*(slot in ca)+.6*(slot in aa),3)
                         for slot in range(16)]
                accents=[round((.86 if slot in ca else .73 if
                                slot in active else .46),3)
                         for slot in range(16)]
                bars.append({"weights":weights,"accents":accents,
                             "density":len(aa)+len(ca),
                             "chord":tuple(sorted(ca)),
                             "arpeggio":tuple(sorted(aa)),
                             "melody":tuple(sorted(active))})
            output[ident]={
                "kind":"built_in","style_id":ident,"name":label,
                "group":group,"family":family,"variant":index,
                "signature":signature,"weights":bars[0]["weights"],
                "accents":bars[0]["accents"],"bar_profiles":bars,
                "density":float(sum(b["density"] for b in bars)/4),
                "bars":4,"source":"original_composer_pattern",
                "has_drum_channel":False}
    return output

@lru_cache(maxsize=1)
def builtin_styles():
    """Never depends on private files or a network connection."""
    return _register()

def grouped_style_names():
    return {group:[("motor:"+label,label) for label,_ in choices]
            for group,choices in _GROUPS.items()}

def builtin_pulses(item,bar,arpeggio=False):
    pattern=item["bar_profiles"][int(bar)%4]
    return list(pattern["arpeggio" if arpeggio else "chord"])
