"""Motor único MIDI→audio para tarjeta compacta y vista ampliada.

Todos los controles de la ventana grande escriben aquí; la vista compacta
conserva exactamente el estado y no inicia un segundo render.
"""
from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QTimer

def setup_advanced(card):
    card.soundfont=None
    card.gain_percent=100
    card.transpose_semitones=0
    card.tempo_percent=100
    card.reverb=True
    card.chorus=True
    card.normalize=False
    card.mono=False
    card.output_basename=""
    card._midi_length=0.
    card._estimated_pcm=0
    card._progress_timer=QTimer(card)
    card._progress_timer.setInterval(200)
    card._progress_timer.timeout.connect(lambda:progress_synthesis(card))

def soundfont_file(card,path):
    if card.busy:return False
    if path is None or str(path)=="":
        card.soundfont=None
        return True
    candidate=Path(path).expanduser().resolve()
    if candidate.is_file() and candidate.suffix.lower()==".sf2":
        card.soundfont=candidate
        return True
    return False

def soundfont_locations(card):
    """Directorios reales, incluidos pendrives montados por udisks/Dolphin."""
    dirs=[]
    previous=getattr(card,"soundfont",None)
    if previous is not None and previous.parent.is_dir():
        dirs.append(previous.parent)
    # No crear unidades fantasma: comprobar montajes y ficheros SF2 reales.
    for base in (Path("/media")/Path.home().name, Path("/run/media")/Path.home().name):
        if not base.is_dir():continue
        for mount in base.iterdir():
            if not mount.is_dir() or mount.is_symlink():continue
            for location in (mount/"soundfont",mount/"SoundFonts",mount/"SF2",mount):
                if location.is_dir() and any(p.is_file() and p.suffix.lower()==".sf2"
                                            for p in location.iterdir()):
                    dirs.append(location)
    system=Path("/usr/share/sounds/sf2")
    if system.is_dir():dirs.append(system)
    return list(dict.fromkeys(p.resolve() for p in dirs))

def choose_soundfont(card):
    from PySide6.QtCore import QUrl
    locations=soundfont_locations(card)
    initial=str(locations[0] if locations else Path.home())
    dialog=QFileDialog(card,"Cargar banco de sonidos SF2",initial,"SoundFont 2 (*.sf2);;Todos los archivos (*)")
    dialog.setFileMode(QFileDialog.ExistingFile)
    dialog.setAcceptMode(QFileDialog.AcceptOpen)
    sidebar=[QUrl.fromLocalFile(str(folder)) for folder in locations]
    sidebar.insert(0,QUrl.fromLocalFile(str(Path.home())))
    dialog.setSidebarUrls(sidebar)
    if dialog.exec()!=QFileDialog.Accepted:return
    files=dialog.selectedFiles()
    if not files:return
    if soundfont_file(card,files[0]):
        expanded=getattr(card,"expanded_view",None)
        if expanded is not None:expanded.refresh_soundfont()
    else:card.status.setText("El archivo elegido no es un banco SF2 válido")

def timidity_options(card):
    options=["-s",("44100" if card.rate.currentIndex()==0 else "48000"),
             "-A",str(card.gain_percent),
             "-K",str(card.transpose_semitones),
             "-T",str(card.tempo_percent),
             "-p",str(card.max_polyphony),
             "--resample="+card.resampler,
             "--reverb="+(f"g,{card.reverb_level}" if card.reverb else "d"),
             "--chorus="+(f"n,{card.chorus_level}" if card.chorus else "d")]
    # Delay real del sintetizador, idéntico en preescucha y exportación.
    options.append("--delay="+(f"b,{card.delay_ms}" if card.delay_ms else "d"))
    bank=card.soundfont
    if bank is not None:
        if not bank.is_file():raise ValueError("El banco SF2 ha dejado de estar disponible")
        # Config de TiMidity creada ÚNICAMENTE en temporales del proyecto.
        import os,tempfile
        fd,name=tempfile.mkstemp(prefix="_midi_sf2_",suffix=".cfg",
                                dir=str(card._current_project/"temporales"))
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            # La configuración del sistema no se edita; exclusivamente SF2 elegido.
            escaped=str(bank).replace("\\","\\\\").replace('"','\\"')
            stream.write(f'soundfont "{escaped}"\n')
        card._tmp_sf2_cfg=Path(name)
        options+=["-c",str(card._tmp_sf2_cfg)]
    return options

def progress_synthesis(card):
    if card._stage!="synth" or card._tmp_render is None:return
    try:
        actual=max(0,card._tmp_render.stat().st_size-44)
    except OSError:return
    # Progreso real de producción PCM; duración MIDI+cola es estimación.
    if card._estimated_pcm:
        value=min(69,int(70*actual/card._estimated_pcm))
        if value>card._last_percent:
            card._last_percent=value
            card.progress.setValue(value)
    card.progress.setFormat(f"{value}% estimado · PCM producido: {actual/1048576:.2f} MiB")

def validate_name(raw,fallback):
    import re
    name=raw.strip()
    if not name:return fallback
    name=Path(name).stem[:90]
    # No rutas externas ni traversal; es un nombre de archivo, nunca carpeta.
    name=re.sub(r'[\\/:*?"<>|\x00-\x1f]',"_",name).strip(" .")
    if name in ("",".",".."):raise ValueError("Nombre de salida incorrecto")
    return name

def final_audio_options(card,already_processed=False):
    # El WAV PCM24 de FluidSynth YA contiene EQ/Compresión, Reverb/Chorus
    # y ganancia de la escucha B; no procesar dos veces esos efectos.
    options=["-ac","1" if card.mono else "2"]
    if already_processed:
        if card.normalize:
            # La normalización LUFS es una opción de masterización,
            # no puede sonar idéntica en un directo sin analizar la mezcla.
            options.extend(["-af","loudnorm=I=-16:TP=-1.5:LRA=11"])
        return options
    filters=[]
    if getattr(card,"eq_enabled",False):
        bass=int(card.eq_bass);mid=int(card.eq_mid);treble=int(card.eq_treble)
        if bass:filters.append(f"bass=g={bass}:f=180")
        if mid:filters.append(f"equalizer=f=1200:t=q:w=1:g={mid}")
        if treble:filters.append(f"treble=g={treble}:f=3600")
        if filters:filters.append("alimiter=limit=0.95")
    if getattr(card,"comp_enabled",False):
        threshold=10**(max(-36,min(-6,int(card.comp_threshold)))/20)
        ratio=max(1,min(8,int(card.comp_ratio)))
        attack=max(1,min(200,int(card.comp_attack)))
        release=max(20,min(1000,int(card.comp_release)))
        filters.append(f"acompressor=threshold={threshold:.6f}:ratio={ratio}:attack={attack}:release={release}:makeup=1")
    if card.normalize:
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    if filters:options.extend(["-af",",".join(filters)])
    return options
