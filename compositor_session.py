"""Compositor de pistas MIDI y audio · modelo de sesión por proyecto.

Persistencia atómica, clips no destructivos, múltiples pistas, Undo/Redo,
copias protegidas de archivos temporales y render offline sincronizado.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import uuid

AUDIO={".wav",".flac",".mp3",".ogg",".m4a",".aif",".aiff",".opus"}
MIDI={".mid",".midi",".kar"}
EXTENSIONS=AUDIO|MIDI


def probe(path):
    """Metadatos reales, pero cacheados por tamaño y fecha de cambio.

    Un arrastre de clip no debe volver a ejecutar FFprobe o leer el MIDI
    completo. Si el archivo cambia, la firma invalida la caché.
    """
    path=Path(path).resolve()
    stat=path.stat()
    return _probe_cached(str(path),stat.st_size,stat.st_mtime_ns)

@lru_cache(maxsize=512)
def _probe_cached(file_path,size,mtime_ns):
    path=Path(file_path)
    kind="midi" if path.suffix.lower() in MIDI else "audio"
    try:
        if kind=="midi":
            import mido
            duration=float(mido.MidiFile(str(path)).length)
        else:
            process=subprocess.run(
                ["ffprobe","-v","error","-show_entries",
                 "format=duration","-of","default=noprint_wrappers=1:nokey=1",
                 str(path)],capture_output=True,text=True,timeout=22,check=True)
            duration=float(process.stdout.strip())
    except (OSError,EOFError,subprocess.SubprocessError,TypeError) as error:
        raise ValueError("No se puede leer audio/MIDI: "+path.name) from error
    if not 0<duration<60*60*20:
        raise ValueError("Archivo vacío o duración inválida")
    return kind,round(duration,5)


class CompositorSession:
    def __init__(self,project=None):
        self.project=None
        self.state={"version":1,"bpm":120,"tracks":[]}
        self.undo_stack=[]
        self.redo_stack=[]
        if project:self.open_project(project)

    @property
    def folder(self):
        if self.project is None:
            raise ValueError("Primero abre o crea un proyecto")
        return self.project/"compositor"

    def open_project(self,project):
        """Load and validate BEFORE abandoning the previous session."""
        root=Path(project).resolve() if project else None
        if root==self.project:return
        state={"version":1,"bpm":120,"tracks":[]}
        if root is not None:
            if not root.is_dir():raise FileNotFoundError(root)
            manifest=root/"compositor"/"arreglo.json"
            if manifest.is_file():
                data=json.loads(manifest.read_text(encoding="utf8"))
                self._validate(data)
                state=data
        self.project=root
        self.state=state
        self.undo_stack.clear()
        self.redo_stack.clear()

    def _validate(self,data):
        """Rechazar sesiones corruptas sin ejecutar rutas ni perder cambios."""
        if not isinstance(data,dict) or data.get("version")!=1:
            raise ValueError("Formato de arreglo incompatible")
        bpm=data.get("bpm")
        if (isinstance(bpm,bool) or not isinstance(bpm,(int,float)) or
                not math.isfinite(bpm) or not 35<=bpm<=300):
            raise ValueError("Tempo de proyecto fuera de rango")
        tracks=data.get("tracks")
        if not isinstance(tracks,list) or len(tracks)>128:
            raise ValueError("Lista de pistas inválida o demasiado grande")
        track_ids=set();clip_ids=set()
        for track in tracks:
            if not isinstance(track,dict):
                raise ValueError("Pista dañada en el arreglo")
            ident=track.get("id")
            if not isinstance(ident,str) or not ident or ident in track_ids:
                raise ValueError("ID de pista vacío o duplicado")
            track_ids.add(ident)
            if track.get("type") not in ("midi","audio"):
                raise ValueError("Tipo de pista desconocido")
            if not isinstance(track.get("name"),str):
                raise ValueError("Nombre de pista inválido")
            if not isinstance(track.get("mute"),bool) or not isinstance(
                    track.get("solo"),bool):
                raise ValueError("Mute/Solo inválido")
            for key,low,high in (("volume",0.,2.),("pan",-1.,1.)):
                value=track.get(key)
                if (isinstance(value,bool) or not isinstance(value,(int,float))
                        or not math.isfinite(value) or not low<=value<=high):
                    raise ValueError("Control de pista inválido: "+key)
            clips=track.get("clips")
            if not isinstance(clips,list) or len(clips)>500:
                raise ValueError("Lista de clips inválida o demasiado grande")
            for clip in clips:
                if not isinstance(clip,dict):
                    raise ValueError("Clip inválido")
                ident=clip.get("id")
                if (not isinstance(ident,str) or not ident or
                        ident in clip_ids):
                    raise ValueError("ID de clip vacío o duplicado")
                clip_ids.add(ident)
                if not isinstance(clip.get("label"),str):
                    raise ValueError("Nombre de clip inválido")
                file=clip.get("file")
                if not isinstance(file,str) or not file or "\x00" in file:
                    raise ValueError("Ruta de archivo inválida")
                relative=Path(file)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Archivo fuera del proyecto")
                for key in ("beat","offset","duration"):
                    value=clip.get(key)
                    if (isinstance(value,bool) or not isinstance(value,(int,float))
                            or not math.isfinite(value) or
                            (value<=0 if key=="duration" else value<0)
                            or value>1e7):
                        raise ValueError("Tiempo de clip inválido: "+key)
                for key,low,high in (("gain",0.,4.),
                                     ("fade_in",0.,clip["duration"]),
                                     ("fade_out",0.,clip["duration"])):
                    value=clip.get(key,1. if key=="gain" else 0.)
                    if (not isinstance(value,(int,float)) or
                            not math.isfinite(value) or not low<=value<=high):
                        raise ValueError("Parámetro de clip inválido: "+key)

    def file_for(self,clip):
        p=(self.project/clip["file"]).resolve()
        if p!=self.project and self.project not in p.parents:
            raise ValueError("Ruta de clip fuera del proyecto")
        return p

    def _save(self):
        self._validate(self.state)
        folder=self.folder
        folder.mkdir(parents=True,exist_ok=True)
        target=folder/"arreglo.json"
        with tempfile.NamedTemporaryFile("w",encoding="utf8",
               dir=folder,prefix=".arreglo_",suffix=".tmp",
               delete=False) as stream:
            json.dump(self.state,stream,indent=2,ensure_ascii=False)
            stream.flush()
            import os
            os.fsync(stream.fileno())
            tmp=Path(stream.name)
        tmp.replace(target)

    def commit(self,previous):
        if self.state==previous:return False
        # La instantánea solo se registra después de salvar correctamente.
        # Si fallan la validación o el disco, deshacer sigue íntegro.
        try:
            self._save()
        except (ValueError,OSError,TypeError,KeyError):
            self.state=deepcopy(previous)
            raise
        self.undo_stack.append(previous)
        self.undo_stack=self.undo_stack[-64:]
        self.redo_stack.clear()
        return True

    def undo(self):
        if not self.undo_stack:return False
        current=deepcopy(self.state)
        previous=self.undo_stack.pop()
        self.state=deepcopy(previous)
        try:self._save()
        except (ValueError,OSError,TypeError,KeyError):
            self.state=current
            self.undo_stack.append(previous)
            raise
        self.redo_stack.append(current)
        return True

    def redo(self):
        if not self.redo_stack:return False
        current=deepcopy(self.state)
        following=self.redo_stack.pop()
        self.state=deepcopy(following)
        try:self._save()
        except (ValueError,OSError,TypeError,KeyError):
            self.state=current
            self.redo_stack.append(following)
            raise
        self.undo_stack.append(current)
        self.undo_stack=self.undo_stack[-64:]
        return True

    def set_bpm(self,bpm):
        prev=deepcopy(self.state)
        self.state["bpm"]=int(bpm)
        return self.commit(prev)

    def _materialize(self,source):
        source=Path(source)
        if not source.is_file() or source.is_symlink():
            raise ValueError("Archivo no disponible o enlace no admitido")
        if source.suffix.lower() not in EXTENSIONS:
            raise ValueError("Tipo de archivo incompatible")
        source=source.resolve()
        # Guardar copia del medio dentro del proyecto. Los archivos en
        # Resultados siguen intactos, incluso si desaparecen sus temporales.
        destination=self.folder/"medios"
        destination.mkdir(parents=True,exist_ok=True)
        signature=hashlib.sha256()
        with source.open("rb") as f:
            while chunk:=f.read(1024*1024):
                signature.update(chunk)
        name=signature.hexdigest()[:16]+"_"+source.name
        target=destination/name
        if not target.is_file():
            temp=destination/(name+".part")
            shutil.copyfile(source,temp)
            temp.replace(target)
        return target.relative_to(self.project).as_posix()

    def create_track(self,kind,name=None):
        if kind not in ("midi","audio"):
            raise ValueError("Pista de tipo desconocido")
        previous=deepcopy(self.state)
        number=1+sum(t["type"]==kind for t in self.state["tracks"])
        track={"id":uuid.uuid4().hex,
               "name":str(name).strip()[:110]
                      if name else f"{kind.upper()} {number:02}",
               "type":kind,"mute":False,"solo":False,
               "volume":1.,"pan":0.,"clips":[]}
        self.state["tracks"].append(track)
        self.commit(previous)
        return track["id"]

    def paste_clip_data(self,kind,clip_data,*,at_beat,track_id=None):
        if kind not in ("audio","midi"):
            raise ValueError("Formato de clip desconocido")
        # Verificar que el origen sigue dentro de la sesión antes de copiar.
        source=self.file_for(clip_data)
        if not source.is_file():
            raise FileNotFoundError("El medio copiado ya no está disponible")
        track=self.track(track_id) if track_id else None
        if track is not None and track["type"]!=kind:
            raise ValueError("No se puede pegar en pista de otro formato")
        original=deepcopy(self.state)
        if track is None:
            track={"id":uuid.uuid4().hex,"name":Path(source).stem,
                   "type":kind,"mute":False,"solo":False,
                   "volume":1.,"pan":0.,"clips":[]}
            self.state["tracks"].append(track)
        copy=deepcopy(clip_data)
        copy["id"]=uuid.uuid4().hex
        copy["beat"]=max(0.,float(at_beat))
        track["clips"].append(copy)
        self.commit(original)
        return copy["id"]

    def clone_clip(self,clip_id,*,beat=None,track_id=None):
        track,clip=self.clip(clip_id)
        target=self.track(track_id) if track_id else track
        if target["type"]!=track["type"]:
            raise ValueError("No puede pegar un audio sobre una pista MIDI")
        before=deepcopy(self.state)
        clone=deepcopy(clip)
        clone["id"]=uuid.uuid4().hex
        clone["beat"]=max(0.,float(
            beat if beat is not None else clip["beat"]+
            clip["duration"]*self.state["bpm"]/60.))
        target["clips"].append(clone)
        self.commit(before)
        return clone["id"]

    def add(self,path,track_id=None,at_beat=0):
        typ,duration=probe(path)
        previous=deepcopy(self.state)
        rel=self._materialize(path)
        track=next((t for t in self.state["tracks"]
                    if t["id"]==track_id),None)
        if track is not None and track["type"]!=typ:
            raise ValueError("No se pueden mezclar MIDI y audio en una pista")
        if track is None:
            track={"id":uuid.uuid4().hex,"name":Path(path).stem,
                   "type":typ,"mute":False,"solo":False,
                   "volume":1.,"pan":0.,"clips":[]}
            self.state["tracks"].append(track)
        clip={"id":uuid.uuid4().hex,"file":rel,"label":Path(path).name,
              "beat":max(0.,float(at_beat)),"offset":0.,"duration":duration,
              "source_duration":duration,"gain":1.,"fade_in":0.,"fade_out":0.}
        track["clips"].append(clip)
        self.commit(previous)
        return track["id"],clip["id"]

    def track(self,id):
        return next(t for t in self.state["tracks"] if t["id"]==id)

    def clip(self,id):
        for t in self.state["tracks"]:
            for c in t["clips"]:
                if c["id"]==id:return t,c
        raise KeyError(id)

    def update_track(self,id,**changes):
        t=self.track(id)
        old=deepcopy(self.state)
        for key,value in changes.items():
            if key=="name":t[key]=str(value).strip()[:110] or "Pista"
            elif key in ("mute","solo"):t[key]=bool(value)
            elif key=="volume":t[key]=min(2.,max(0.,float(value)))
            elif key=="pan":t[key]=min(1.,max(-1.,float(value)))
            else:raise ValueError("Parámetro de pista no editable")
        return self.commit(old)

    def edit_clip(self,id,*,beat=None,offset=None,duration=None,track_id=None,
                  gain=None,fade_in=None,fade_out=None):
        t,c=self.clip(id)
        old=deepcopy(self.state)
        if track_id and track_id!=t["id"]:
            target=self.track(track_id)
            if target["type"]!=t["type"]:
                raise ValueError("Mover clip a otra pista requiere igual formato")
            t["clips"].remove(c)
            target["clips"].append(c)
        if beat is not None:c["beat"]=max(0.,float(beat))
        if offset is not None:c["offset"]=max(0.,float(offset))
        if duration is not None:c["duration"]=max(.01,float(duration))
        if gain is not None:c["gain"]=float(gain)
        if fade_in is not None:c["fade_in"]=float(fade_in)
        if fade_out is not None:c["fade_out"]=float(fade_out)
        # Recortar SOLO el segmento del archivo original; no extenderlo.
        _,full=probe(self.file_for(c))
        if (c["offset"]+c["duration"]>full+.01 or
                not math.isfinite(c["gain"]) or not 0<=c["gain"]<=4 or
                not all(math.isfinite(c[k]) and 0<=c[k]<=c["duration"]
                        for k in ("fade_in","fade_out"))):
            self.state=old
            raise ValueError("Desfase, ganancia o fundido fuera de rango")
        return self.commit(old)

    def split(self,id,beat):
        t,c=self.clip(id)
        beats_per_second=self.state["bpm"]/60.
        relative=(float(beat)-c["beat"])/beats_per_second
        if not .02<relative<c["duration"]-.02:
            raise ValueError("Sitúa el corte dentro del clip")
        old=deepcopy(self.state)
        tail=deepcopy(c)
        tail["id"]=uuid.uuid4().hex
        tail["beat"]=float(beat)
        tail["offset"]+=relative
        tail["duration"]-=relative
        c["duration"]=relative
        # Preservar el fade de entrada en la primera mitad y el de
        # salida en la segunda. No crear fundidos al cortar en seco.
        tail["fade_in"]=0.
        c["fade_out"]=0.
        if "fade_in" in c:
            c["fade_in"]=min(c["fade_in"],c["duration"])
        if "fade_out" in tail:
            tail["fade_out"]=min(tail["fade_out"],tail["duration"])
        t["clips"].insert(t["clips"].index(c)+1,tail)
        self.commit(old)
        return tail["id"]

    def split_clips(self,clip_ids,beat):
        """Dividir todos los clips cruzados por la guía en un único Undo."""
        beat=max(0.,float(beat))
        if not math.isfinite(beat):raise ValueError("Posición de guía inválida")
        targets=set(clip_ids)
        previous=deepcopy(self.state)
        result=[]
        beats_per_second=self.state["bpm"]/60.
        for track in self.state["tracks"]:
            for clip in list(track["clips"]):
                if clip["id"] not in targets:continue
                relative=(beat-clip["beat"])/beats_per_second
                if not .02<relative<clip["duration"]-.02:continue
                tail=deepcopy(clip)
                tail["id"]=uuid.uuid4().hex
                tail["beat"]=beat
                tail["offset"]+=relative
                tail["duration"]-=relative
                tail["fade_in"]=0.
                tail["fade_out"]=min(tail.get("fade_out",0.),tail["duration"])
                clip["duration"]=relative
                clip["fade_out"]=0.
                clip["fade_in"]=min(clip.get("fade_in",0.),relative)
                track["clips"].insert(track["clips"].index(clip)+1,tail)
                result.append(tail["id"])
        self.commit(previous)
        return result

    def delete_clips(self,clip_ids):
        """Borrado simultáneo, sin eliminar los medios fuente."""
        ids=set(clip_ids)
        previous=deepcopy(self.state)
        removed=0
        for track in self.state["tracks"]:
            before=len(track["clips"])
            track["clips"][:]=[c for c in track["clips"] if c["id"] not in ids]
            removed+=before-len(track["clips"])
        self.commit(previous)
        return removed

    def delete_tracks(self,track_ids):
        ids=set(track_ids)
        previous=deepcopy(self.state)
        self.state["tracks"][:]=[t for t in self.state["tracks"]
                               if t["id"] not in ids]
        return self.commit(previous)

    def clone_clips(self,clip_ids):
        targets=set(clip_ids)
        previous=deepcopy(self.state)
        new=[]
        for track in self.state["tracks"]:
            clips=[]
            for clip in track["clips"]:
                if clip["id"] in targets:
                    clone=deepcopy(clip)
                    clone["id"]=uuid.uuid4().hex
                    clone["beat"]+=clip["duration"]*self.state["bpm"]/60.
                    clips.append(clone)
                    new.append(clone["id"])
            track["clips"].extend(clips)
        self.commit(previous)
        return new

    def paste_many(self,items,at_beat):
        """Pegar una selección conservando desfases relativos y tipos.

        items: (original_track_id, track_type, clip_dict)
        No permite introducir rutas de otro proyecto.
        """
        if not items:return []
        previous=deepcopy(self.state)
        start=min(float(c["beat"]) for _,_,c in items)
        result=[]
        try:
            for track_id,kind,original in items:
                # La copia puede provenir de un clip ya borrado, pero el
                # archivo está en el proyecto y se valida su ruta.
                source=self.file_for(original)
                if not source.is_file():raise FileNotFoundError(source)
                track=next((t for t in self.state["tracks"]
                            if t["id"]==track_id and t["type"]==kind),None)
                if track is None:
                    number=1+sum(t["type"]==kind for t in self.state["tracks"])
                    track={"id":uuid.uuid4().hex,"name":f"{kind.upper()} {number:02}",
                           "type":kind,"mute":False,"solo":False,
                           "volume":1.,"pan":0.,"clips":[]}
                    self.state["tracks"].append(track)
                clip=deepcopy(original)
                clip["id"]=uuid.uuid4().hex
                clip["beat"]=max(0.,float(at_beat)+float(original["beat"])-start)
                track["clips"].append(clip)
                result.append(clip["id"])
            self.commit(previous)
        except Exception:
            self.state=previous
            raise
        return result

    def move_clips(self,positions):
        """Arrastre multipista atómico: id -> (nuevo compás, pista destino)."""
        if not positions:return False
        old=deepcopy(self.state)
        updates=[]
        for ident,(beat,destination) in positions.items():
            track,clip=self.clip(ident)
            other=self.track(destination)
            beat=float(beat)
            if not math.isfinite(beat) or beat<0 or other["type"]!=track["type"]:
                raise ValueError("Movimiento fuera de rejilla o tipo de pista")
            updates.append((track,clip,other,beat))
        for source,clip,destination,beat in updates:
            if source is not destination:
                source["clips"].remove(clip)
                destination["clips"].append(clip)
            clip["beat"]=beat
        return self.commit(old)

    def delete_clip(self,id):
        t,c=self.clip(id)
        old=deepcopy(self.state)
        t["clips"].remove(c)
        self.commit(old)

    def delete_track(self,id):
        old=deepcopy(self.state)
        self.state["tracks"]=[t for t in self.state["tracks"] if t["id"]!=id]
        return self.commit(old)

    def move_track(self,id,delta):
        tracks=self.state["tracks"]
        i=next(i for i,t in enumerate(tracks) if t["id"]==id)
        j=min(len(tracks)-1,max(0,i+delta))
        old=deepcopy(self.state)
        tracks.insert(j,tracks.pop(i))
        return self.commit(old)

    def audible(self):
        tracks=self.state["tracks"]
        solo=any(t["solo"] for t in tracks)
        return [t for t in tracks
                if not t["mute"] and (not solo or t["solo"]) and t["volume"]>0]

    def end_seconds(self):
        bpm=self.state["bpm"]
        return max((c["beat"]*60/bpm+c["duration"]
                    for t in self.state["tracks"] for c in t["clips"]),default=0.)
