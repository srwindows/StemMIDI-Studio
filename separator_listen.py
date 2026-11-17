"""Preescucha seleccionable de stems en Inicio: nunca modifica pistas originales."""
from __future__ import annotations

import hashlib
import tempfile
import array
import math
import subprocess
import threading
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

NAMES=("Original","Voces","Batería","Bajo","Guitarra","Piano","Viento","Otros",
       "Voz principal","Coros","Voz masculina","Voz femenina")


class SeparatorListen(QObject):
    selectionChanged=Signal()
    busyChanged=Signal(bool)
    statusChanged=Signal(str)

    def __init__(self,home):
        super().__init__(home)
        self.home=home
        self.selected={"Original"}
        self._tmp=tempfile.TemporaryDirectory(prefix="stemmidi_escucha_")
        self._process=QProcess(self)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._errored)
        self._pending=None
        self._cache={}
        self._generation=0
        self._busy=False
        self._levels={}
        self._meter_stop=threading.Event()
        self._meter_processes=set()
        self._meter_lock=threading.Lock()
        self._catalog_project=None
        self._catalog_signature=()
        self._selection_touched=False
        from low_latency_stem_mixer import LowLatencyStemMixer
        self.live=LowLatencyStemMixer(self)
        self.live.error.connect(self.statusChanged.emit)
        # Evita superponer la escucha de otro módulo con el mezclador.
        self.home.player.playStateChanged.connect(
            lambda playing:self.stop() if playing and self.live.running else None)

    def available(self):
        """Archivos auténticos de este proyecto, incluidos los restaurados.

        latest_outputs se vacía al reiniciar el programa: los stems no.
        La sesión temporal y la carpeta definitiva son fuentes autoritativas;
        jamás recuperar audios de otro proyecto ni sustituir un stem por
        una grabación original.
        """
        sep=self.home.workbench.separator
        work=self.home.workbench
        source=sep.file_edit.text()
        if source and Path(source).is_file():
            original=Path(source).resolve()
        elif sep.source_preview.current_file and Path(sep.source_preview.current_file).is_file():
            original=Path(sep.source_preview.current_file).resolve()
        else:
            original=None
        result={"Original":original}
        project=getattr(self.home.main,"project_dir",None)
        project=Path(project).resolve() if project else None
        candidates=[]
        if project is not None:
            from task_staging import project_audio_sources,inside
            candidates.extend(project_audio_sources(project,("separaciones",)))
            # Restauración independiente del objeto TaskStorage: el estado
            # persistente ACTIVA.json conserva las seis salidas de Demucs
            # incluso antes de reconstruir la interfaz del proyecto.
            import json
            active_root=project/"temporales"/"separaciones"
            active=active_root/"ACTIVA.json"
            try:
                info=json.loads(active.read_text(encoding="utf-8"))
                folder=Path(info["folder"]).resolve()
                if inside(folder,active_root):
                    for source in info.get("items",[]):
                        path=Path(source)
                        if inside(path,folder):candidates.append(path)
            except (OSError,ValueError,KeyError,TypeError):
                pass
            candidates.extend(work.separation_storage.items)
            candidates.extend(sep.latest_outputs)
            try:
                from project_flow import approved_map
                candidates.extend(approved_map(self.home.main).values())
            except (OSError,ValueError,KeyError):
                pass
        else:
            candidates.extend(sep.latest_outputs)
            candidates.extend(work.separation_storage.items)
        if project is not None:
            from vocal_catalog import latest_vocal_stems
            for role,path in latest_vocal_stems(project).items():
                result[role]=path
        for path in candidates:
            candidate=Path(path)
            if (not candidate.is_file() or candidate.is_symlink()
                    or candidate.suffix.lower() not in
                    {".wav",".flac",".mp3",".m4a",".ogg",".aif",".aiff",".opus"}):
                continue
            if project is not None and not inside(candidate,project):
                continue
            name=self.home._stem_for(candidate)
            if name in NAMES and name!="Original":
                result[name]=candidate.resolve()
        return result

    def sync_catalog(self):
        """Activar stems existentes por defecto, no la grabación original.

        Una selección manual permanece intacta incluso si se desmarca todo.
        Al cambiar de proyecto descartar las selecciones del anterior.
        """
        found=self.available()
        project=getattr(self.home.main,"project_dir",None)
        project=str(Path(project).resolve()) if project else None
        signature=tuple(sorted((name,str(path)) for name,path in found.items()
                               if name!="Original" and path is not None))
        changed=project!=self._catalog_project or signature!=self._catalog_signature
        if not changed:return found
        project_changed=project!=self._catalog_project
        if project_changed:
            if self.live.running:self.live.stop()
            self._selection_touched=False
        previous=set(self.selected)
        stems={name for name,_ in signature}
        if stems:
            if project_changed or not self._selection_touched:
                # No reproducir la mezcla original por defecto ni dar
                # pistas por marcadas: el usuario decide qué escuchar.
                self.selected=set()
            else:
                self.selected.intersection_update(stems|{"Original"})
        elif project_changed:
            self.selected={"Original"} if found["Original"] else set()
        else:
            self.selected.intersection_update({"Original"})
        self._catalog_project=project
        self._catalog_signature=signature
        # Si cambió el catálogo, refrescar también los QCheckBox que
        # estaban deshabilitados aunque la selección manual sea la misma.
        self.selectionChanged.emit()
        return found

    def select_only(self,name,autoplay=False):
        found=self.sync_catalog()
        if name not in found or found[name] is None:return False
        previous=set(self.selected)
        self.selected={name}
        self._selection_touched=True
        if self.live.running:
            for other in NAMES:
                self.live.set_enabled(other,other==name)
        if self.selected!=previous:self.selectionChanged.emit()
        return self.play() if autoplay and not self.live.running else True

    def set_enabled(self,name,checked):
        """El checkbox es MUTE: actualizar ganancia SIN reiniciar la música."""
        if name not in NAMES:return
        found=self.sync_catalog()
        if checked and found.get(name) is None:return
        old=set(self.selected)
        self._selection_touched=True
        if checked:self.selected.add(name)
        else:self.selected.discard(name)
        if checked and name!="Original":
            self.selected.discard("Original")
        elif checked and name=="Original":
            self.selected={"Original"}
        if old!=self.selected:
            if self.live.running:
                for source in old|self.selected:
                    self.live.set_enabled(source,source in self.selected)
                if name in self.selected and found.get(name):
                    self._analyze(found[name])
            self.selectionChanged.emit()

    def paths(self):
        found=self.available()
        return [(name,found[name]) for name in NAMES
                if name in self.selected and name in found and found[name] is not None]

    def play(self):
        self.sync_catalog()
        if self.live.running:
            if self.live.paused:self.live.pause()
            return True
        found=self.available()
        if not self.selected:
            self.statusChanged.emit("Marca al menos una pista; las demás quedarán muteadas.")
            return False
        entries=[(name,found[name]) for name in NAMES
                 if found.get(name) is not None]
        if not entries:
            self.statusChanged.emit("No hay pistas disponibles para escuchar.")
            return False
        # Reemplaza la preescucha global solo una vez al pulsar Play.
        self.home.player.stop()
        for name,path in entries:
            if name in self.selected:self._analyze(path)
        ok=self.live.start(entries,self.selected)
        if ok:self.statusChanged.emit("Reproduciendo stems · mute sin reinicios")
        return ok

    def pause(self):
        self.live.pause()

    def seek(self,position_ms):
        return self.live.seek(position_ms)

    def _analyze(self,path):
        """Analizar RMS PCM real por intervalos de 100 ms, solo cuando se escucha."""
        path=Path(path)
        try:key=(str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns)
        except OSError:return
        if key in self._levels:return
        self._levels[key]=[]
        def work():
            process=None
            try:
                process=subprocess.Popen([
                    "ffmpeg","-nostdin","-hide_banner","-loglevel","error",
                    "-i",key[0],"-map","0:a:0","-t","1800",
                    "-ac","2","-ar","12000","-f","f32le","pipe:1"],
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                with self._meter_lock:self._meter_processes.add(process)
                while not self._meter_stop.is_set():
                    chunk=process.stdout.read(9600)
                    if len(chunk)!=9600:break
                    floats=array.array("f")
                    floats.frombytes(chunk)
                    if sys.byteorder!="little":floats.byteswap()
                    l=sum(x*x for x in floats[0::2])
                    r=sum(x*x for x in floats[1::2])
                    self._levels[key].append((
                        min(1.,math.sqrt(l/1200)),
                        min(1.,math.sqrt(r/1200))))
            except (OSError,ValueError):pass
            finally:
                if process is not None:
                    if process.poll() is None:process.terminate()
                    try:process.wait(timeout=.5)
                    except subprocess.TimeoutExpired:process.kill()
                    with self._meter_lock:self._meter_processes.discard(process)
        threading.Thread(target=work,daemon=True,name="StemMIDI-SepMeter").start()

    def meter_at(self,path,seconds):
        path=Path(path)
        try:key=(str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns)
        except OSError:return (0.,0.)
        frames=self._levels.get(key)
        if not frames:return (0.,0.)
        index=max(0,int(seconds*10))
        return frames[min(len(frames)-1,index)] if index<len(frames) else (0.,0.)

    def _play_path(self,path):
        player=self.home.player
        if player.current_file==str(path.resolve()):
            player.play_pause()
            return True
        return bool(player.load(path,autoplay=True))

    def _finished(self,return_code,exit_status):
        item=self._pending
        self._pending=None
        self._busy=False
        self.busyChanged.emit(False)
        if item is None:return
        signature,path=item
        if return_code==0 and path.is_file() and path.stat().st_size:
            self._cache[signature]=path
            current=tuple((name,str(p),p.stat().st_size,p.stat().st_mtime_ns)
                          for name,p in self.paths())
            if current==signature:
                self._play_path(path)
                self.statusChanged.emit("Escuchando mezcla de pistas marcadas")
        else:
            self.statusChanged.emit("No se pudo crear la mezcla de preescucha.")

    def _errored(self,_error):
        self._pending=None
        if self._busy:
            self._busy=False
            self.busyChanged.emit(False)
        self.statusChanged.emit("FFmpeg no pudo iniciar la mezcla temporal.")

    def stop(self):
        self.live.stop()
        if self._process.state()!=QProcess.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)
        self._pending=None
        if self._busy:
            self._busy=False
            self.busyChanged.emit(False)

    def cleanup(self):
        self.stop()
        self._meter_stop.set()
        with self._meter_lock:
            for proc in tuple(self._meter_processes):
                try:proc.terminate()
                except OSError:pass
        try:self._tmp.cleanup()
        except OSError:pass  # Windows puede retener un archivo temporal hasta cerrar el backend.
