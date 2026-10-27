"""Almacenamiento temporal controlado por el usuario para separación y MIDI.

Sólo "Guardar todo" o "Guardar selección" publica archivos finales.
"Nueva tarea" borra EXCLUSIVAMENTE su directorio temporal, tras confirmación.
Los trabajos sin guardar persisten entre reinicios para evitar pérdida por fallo.
"""
from __future__ import annotations
import file_dialogs
import json
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import mido
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QCheckBox, QLabel, QScrollArea, QFrame,
    QPushButton, QFileDialog, QMessageBox, QGridLayout, QLineEdit, QComboBox
)
from preview_player import PreviewPlayer

from studio_paths import workspace_root
ROOT=workspace_root(__file__)
TEMP_ROOT=ROOT/"tareas_temporales"
FINALS={"separaciones":ROOT/"pistas_separadas","midi":ROOT/"midi_generados",
        "bateria":ROOT/"pistas_bateria", "vocal":ROOT/"pistas_vocales"}


def inside(candidate, parent):
    candidate=Path(candidate).resolve()
    parent=Path(parent).resolve()
    return candidate!=parent and parent in candidate.parents


def project_audio_sources(project_dir,kinds=("separaciones",)):
    """Audios guardados en el proyecto ACTIVO, nunca en bibliotecas globales.

    No atraviesa enlaces a carpetas externas; el origen sigue en su sitio.
    """
    if not project_dir:
        return []
    project=Path(project_dir).expanduser().resolve()
    allowed={".wav",".flac",".mp3",".ogg",".opus",".m4a",".aif",".aiff"}
    result=[]
    for kind in kinds:
        if kind not in ("separaciones","bateria","vocal","mezclas","grabaciones"):
            continue
        from project_layout import module_dir
        base=module_dir(project,kind)
        if not base.is_dir():
            continue
        for item in base.rglob("*"):
            if (item.is_file() and not item.is_symlink()
                    and item.suffix.lower() in allowed
                    and inside(item,base)):
                result.append(item.resolve())
    return sorted(set(result),key=lambda p:(p.name.casefold(),str(p)))


def unique_dest(folder,filename):
    folder=Path(folder)
    dest=folder/filename
    index=2
    while dest.exists():
        p=Path(filename)
        dest=folder/(p.stem+f"_{index}"+p.suffix)
        index+=1
    return dest


def make_midi_tracks(source,where):
    """Exporta pistas individuales sin alterar notas, canales ni temporización.

    El tempo, compás y tonalidad son globales al archivo MIDI incluso si los
    mensajes se encuentran en otra pista. Se copian por su tick ABSOLUTO.
    No hay cambios en la fuente ni en su ticks_per_beat.
    """
    midi=mido.MidiFile(str(source))
    if midi.type not in (0,1):
        raise ValueError("El MIDI debe ser de tipo 0 o 1")
    where.mkdir(parents=True,exist_ok=True)
    files=[]
    global_types={"set_tempo","time_signature","key_signature","smpte_offset"}
    # Un delta MIDI es relativo a TODOS los mensajes anteriores de su pista.
    # Extraer sólo algunos deltas comprime indebidamente la escala temporal.
    globals_by_tick=[]
    for track_index,track in enumerate(midi.tracks):
        absolute=0
        for index,msg in enumerate(track):
            absolute+=msg.time
            if msg.is_meta and msg.type in global_types:
                globals_by_tick.append((absolute,track_index,index,msg.copy(time=0)))
    globals_by_tick.sort(key=lambda entry:(entry[0],entry[1],entry[2]))
    global_meta=mido.MidiTrack()
    prev_tick=0
    for absolute,_,_,msg in globals_by_tick:
        global_meta.append(msg.copy(time=absolute-prev_tick))
        prev_tick=absolute

    for i,tr in enumerate(midi.tracks):
        notes=sum(1 for msg in tr if msg.type=="note_on" and msg.velocity>0)
        if not notes:
            continue
        clean="".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in (tr.name or f"Pista_{i+1}"))
        filename=f"{i+1:02d}_{clean[:48].strip() or 'Pista'}.mid"
        outfile=unique_dest(where,filename)
        result=mido.MidiFile(type=1,ticks_per_beat=midi.ticks_per_beat)
        result.tracks.append(mido.MidiTrack(msg.copy() for msg in global_meta))
        # La pista musical no repite eventos globales, pero conserva el
        # tiempo de esos eventos al calcular el delta del siguiente mensaje.
        original_abs=0
        last_written=0
        cleaned=mido.MidiTrack()
        for msg in tr:
            original_abs+=msg.time
            if msg.is_meta and msg.type in global_types:
                continue
            cleaned.append(msg.copy(time=original_abs-last_written))
            last_written=original_abs
        result.tracks.append(cleaned)
        result.save(str(outfile))
        files.append((outfile,notes))
    return files

class TaskStorage:
    def __init__(self,kind,namespace=None,project_dir=None):
        assert kind in FINALS
        self.kind=kind
        self.project_dir=Path(project_dir).expanduser().resolve() if project_dir else None
        if namespace is None:
            # Compatibilidad: preservar tareas heredadas sin publicarlas en
            # nuevos proyectos o asociarlas ficticiamente a otros proyectos.
            self.root=TEMP_ROOT/kind
        else:
            import re
            if not re.fullmatch(r"[0-9a-f]{32}",str(namespace)):
                raise ValueError("Identificador de proyecto incorrecto")
            self.root=(self.project_dir/"temporales"/kind if self.project_dir
                       else TEMP_ROOT/"proyectos"/str(namespace)/kind)
        if self.project_dir and not (self.root.resolve()==
                                     (self.project_dir/"temporales"/kind).resolve()):
            raise ValueError("Carpeta temporal fuera del proyecto")
        self.root.mkdir(parents=True,exist_ok=True)
        self.folder=None
        self.items=[]
        self.composite=None
        self.saved=set()
        self.versions=[]
        self.restore()

    @property
    def pending(self):
        return bool(self.folder and self.folder.exists() and (self.items or self.composite))

    @property
    def processing_folder(self):
        if self.folder is None:
            raise RuntimeError("Aún no existe una tarea temporal")
        return self.folder/"procesado"

    def restore(self):
        active=self.root/"ACTIVA.json"
        try:
            obj=json.loads(active.read_text(encoding="utf-8"))
            folder=Path(obj["folder"]).resolve()
            if not inside(folder,self.root) or not folder.is_dir():
                return
            self.folder=folder
            self.items=[Path(s) for s in obj.get("items",[]) if inside(s,folder) and Path(s).is_file()]
            self.composite=Path(obj["composite"]) if obj.get("composite") and inside(obj["composite"],folder) and Path(obj["composite"]).is_file() else None
            self.saved=set(obj.get("saved",[]))
            self.versions=[{"composite":Path(v["composite"]),
                           "items":[Path(x) for x in v.get("items",[])]}
                           for v in obj.get("versions",[])
                           if isinstance(v,dict) and v.get("composite")
                           and inside(v["composite"],folder)
                           and Path(v["composite"]).is_file()]
            if self.kind=="midi" and self.composite is not None and not self.versions:
                self.versions=[{"composite":self.composite,"items":list(self.items)}]
            if not self.items and not self.composite:
                self.items=[p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in (".flac",".mp3",".wav",".mid",".midi") and "_importacion_temporal" not in p.parts and "_audio_midi_entrada_" not in str(p)]
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
            return

    def manifest(self):
        self.root.mkdir(parents=True,exist_ok=True)
        p=self.root/"ACTIVA.json"
        doc={"folder":str(self.folder) if self.folder else None,
             "items":[str(x) for x in self.items],
             "composite":str(self.composite) if self.composite else None,
             "saved":sorted(self.saved),
             "versions":[{"composite":str(v["composite"]),
                          "items":[str(x) for x in v["items"]]}
                         for v in self.versions]}
        tmp=p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(p)

    def start(self):
        from project_layout import layout_active
        self.root.mkdir(parents=True,exist_ok=True)
        if self.project_dir and layout_active(self.project_dir):
            # Una carpeta de trabajo FIJA para cada módulo. Sin fechas
            # ni «toma_*/procesado» repetidos en cada prueba.
            self.folder=self.root/"sesion"
            self.processing_folder.mkdir(parents=True,exist_ok=True)
        else:
            slug=datetime.now().strftime("%Y%m%d_%H%M%S_")+uuid.uuid4().hex[:8]
            self.folder=self.root/slug
            self.processing_folder.mkdir(parents=True,exist_ok=False)
        self.items=[]
        self.composite=None
        self.saved=set()
        self.versions=[]
        self.manifest()
        return self.processing_folder

    def next_midi_run(self):
        """Procesado independiente sin borrar las tomas anteriores."""
        assert self.kind=="midi"
        if self.folder is None or not self.folder.exists():
            self.start()
        from project_layout import layout_active
        if self.project_dir and layout_active(self.project_dir):
            # midi_engine.py ya protege nombres usando sufijos _2, _3…
            # Mantener versiones como archivos, no carpetas por pasada.
            self.processing_folder.mkdir(parents=True,exist_ok=True)
            return self.processing_folder
        run=self.processing_folder/("toma_"+datetime.now().strftime("%H%M%S_%f"))
        run.mkdir(parents=True,exist_ok=False)
        return run

    def select_version(self,index):
        if self.kind!="midi" or not 0<=index<len(self.versions):return False
        v=self.versions[index]
        if not v["composite"].is_file():return False
        self.composite=v["composite"]
        self.items=[x for x in v["items"] if x.is_file()]
        self.manifest()
        return True

    def set_separation(self,folder):
        assert self.kind in ("separaciones","bateria","vocal")
        folder=Path(folder).resolve()
        if not self.folder or not inside(folder,self.folder):
            raise ValueError("La separación no está dentro de la tarea temporal")
        found=sorted(p for p in folder.iterdir() if p.is_file()
                     and p.suffix.lower() in (".flac",".wav",".mp3",".ogg",".opus",".m4a"))
        if self.kind in ("bateria","vocal"):
            # Revisiones dentro de la MISMA tarea: no abandonar carpetas
            # temporales anteriores ni ocultar las tomas ya generadas.
            previous=[p for p in self.items if p.is_file()
                      and inside(p,self.folder)]
            self.items=list(dict.fromkeys(previous+found))
        else:
            self.items=found
        self.manifest()

    def set_midi(self,source):
        assert self.kind=="midi"
        source=Path(source).resolve()
        if not self.folder or not inside(source,self.folder):
            raise ValueError("El MIDI no está dentro de la tarea temporal")
        self.composite=source
        from project_layout import layout_active
        dest=(self.folder/"pistas_midi" if
              self.project_dir and layout_active(self.project_dir) else
              self.folder/"pistas_midi"/(
                  "toma_"+datetime.now().strftime("%H%M%S_%f")))
        tracks=make_midi_tracks(source,dest)
        self.items=[p for p,n in tracks]
        self.versions.append({"composite":source,"items":list(self.items)})
        self.manifest()

    def public_files(self,all_files=False,indices=()):
        selected=list(self.items) if all_files else [self.items[x] for x in indices if 0<=x<len(self.items)]
        if all_files and self.composite:
            selected=[self.composite]+selected
        return selected

    def export_name(self,filename):
        # Archivos definitivos con prefijo del proyecto visible.
        name=Path(filename).name
        if not self.project_dir:return name
        prefix=self.project_dir.name+"_"
        return name if name.startswith(prefix) else prefix+name

    def save(self,dest,all_files=False,indices=()):
        dest=Path(dest).expanduser().resolve()
        from project_layout import layout_active,module_dir
        if self.project_dir and layout_active(self.project_dir):
            dest=module_dir(self.project_dir,self.kind)
        elif self.project_dir and not inside(dest,self.project_dir/"backup"):
            raise ValueError("El destino definitivo debe estar en backup del proyecto antiguo")
        if (inside(dest,self.root) or dest==self.root.resolve()
            or (self.project_dir and
                (inside(dest,self.project_dir/"temporales") or
                 dest==(self.project_dir/"temporales").resolve()))
            or dest==TEMP_ROOT.resolve() or TEMP_ROOT.resolve() in dest.parents):
            raise ValueError("La carpeta definitiva debe estar fuera de tareas_temporales")
        dest.mkdir(parents=True,exist_ok=True)
        entries=self.public_files(all_files,indices)
        if not entries:
            raise ValueError("No hay pistas seleccionadas para guardar")
        copied=[]
        for p in entries:
            if not p.is_file() or not inside(p,self.folder):
                raise ValueError("El archivo temporal ya no existe: "+str(p))
            final=unique_dest(dest,self.export_name(p.name))
            shutil.copy2(p,final)
            if final.stat().st_size!=p.stat().st_size:
                final.unlink(missing_ok=True)
                raise OSError("La copia de audio/MIDI no coincide con el original temporal")
            copied.append(final)
            self.saved.add(str(p))
        self.manifest()
        return copied

    def save_paths(self,dest,paths):
        """Guarda las rutas seleccionadas de ESTA tarea, incluidas tomas MIDI anteriores.

        Valida cada origen contra el directorio temporal autorizado y no
        sobrescribe jamás destinos existentes ni toca el archivo original.
        """
        if self.folder is None or not self.folder.exists():
            raise ValueError("No hay una tarea temporal activa")
        dest=Path(dest).expanduser().resolve()
        from project_layout import layout_active,module_dir
        if self.project_dir and layout_active(self.project_dir):
            dest=module_dir(self.project_dir,self.kind)
        elif self.project_dir and not inside(dest,self.project_dir/"backup"):
            raise ValueError("El destino definitivo debe estar en backup del proyecto antiguo")
        if (inside(dest,self.root) or dest==self.root.resolve()
            or (self.project_dir and
                (inside(dest,self.project_dir/"temporales") or
                 dest==(self.project_dir/"temporales").resolve()))
            or dest==TEMP_ROOT.resolve() or TEMP_ROOT.resolve() in dest.parents):
            raise ValueError("El destino debe estar fuera de tareas_temporales")
        entries=[Path(x).resolve() for x in paths]
        if not entries:
            raise ValueError("Selecciona al menos un resultado")
        # Validar TODO antes de escribir una sola copia.
        for source in entries:
            if not inside(source,self.folder) or not source.is_file():
                raise ValueError("Archivo fuera de la tarea o no disponible: "+str(source))
        dest.mkdir(parents=True,exist_ok=True)
        copied=[]
        for source in entries:
            final=unique_dest(dest,self.export_name(source.name))
            shutil.copy2(source,final)
            if final.stat().st_size!=source.stat().st_size:
                final.unlink(missing_ok=True)
                raise OSError("La copia no coincide con el temporal: "+str(source))
            copied.append(final)
            self.saved.add(str(source))
        self.manifest()
        return copied

    def discard(self):
        if self.folder:
            assert inside(self.folder,self.root)
            # En NTFS/FUSE el cierre asíncrono de Qt/FFmpeg puede retrasar
            # la eliminación de directorios aun cuando los ficheros ya no figuren.
            for attempt in range(8):
                if not self.folder.exists():
                    break
                try:
                    shutil.rmtree(self.folder)
                except OSError:
                    if attempt==7:raise
                    time.sleep(.14)
        self.folder=None;self.items=[];self.composite=None;self.saved.clear()
        self.versions=[]
        self.manifest()


class TrackLine(QFrame):
    def __init__(self,path,index,play_callback,stop_callback,parent=None,
                 edit_callback=None):
        super().__init__(parent)
        self.setObjectName("inner")
        self.path=Path(path)
        self.index=index
        row=QHBoxLayout(self)
        row.setContentsMargins(9,4,9,4)
        row.setSpacing(7)
        self.checked=QCheckBox()
        self.checked.setChecked(True)
        row.addWidget(self.checked)
        self.name=QLabel(self.path.name)
        self.name.setToolTip(str(self.path))
        self.name.setMinimumWidth(125)
        self.name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.name,1)
        self.format=QLabel(self.path.suffix.lstrip(".").upper())
        row.addWidget(self.format)
        self.play=QPushButton("▶ Play")
        self.play.clicked.connect(lambda:play_callback(self.path))
        row.addWidget(self.play)
        self.stop=QPushButton("■ Stop")
        self.stop.clicked.connect(stop_callback)
        row.addWidget(self.stop)
        if edit_callback is not None and self.path.suffix.lower() in (".mid",".midi"):
            self.edit=QPushButton("Editar")
            self.edit.setToolTip("Abrir esta pista MIDI concreta en el piano roll.")
            self.edit.clicked.connect(lambda:edit_callback(str(self.path)))
            row.addWidget(self.edit)


class TaskResults(QWidget):
    """Panel incrustado: cada archivo con Play/Stop y selección de guardado."""
    sourceSelected=Signal(str)
    editRequested=Signal(str)
    saved=Signal(str)
    def __init__(self,kind,storage,parent=None):
        super().__init__(parent)
        self.kind=kind
        self.storage=storage
        self.lines=[]
        self.save_directory=FINALS[kind]
        self.create_ui()
        self.populate()

    def create_ui(self):
        main=QVBoxLayout(self)
        main.setContentsMargins(15,12,15,12)
        main.setSpacing(7)
        title=QLabel("PISTAS SEPARADAS · REVISAR ANTES DE GUARDAR"
            if self.kind=="separaciones" else "PISTAS MIDI · REVISAR ANTES DE GUARDAR")
        title.setObjectName("section")
        main.addWidget(title)
        self.status=QLabel("No hay tarea temporal")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        main.addWidget(self.status)
        if self.kind=="midi":
            versions_row=QHBoxLayout()
            versions_row.addWidget(QLabel("Conversión a revisar"))
            self.version_choice=QComboBox(self)
            self.version_choice.setToolTip(
                "Cambia entre todas las versiones MIDI de esta tarea, sin descartar las anteriores.")
            self.version_choice.currentIndexChanged.connect(self.choose_version)
            versions_row.addWidget(self.version_choice,1)
            main.addLayout(versions_row)
        viewport=QScrollArea()
        viewport.setWidgetResizable(True)
        viewport.setFrameShape(QFrame.NoFrame)
        self.container=QWidget()
        self.rows=QVBoxLayout(self.container)
        self.rows.setSpacing(4)
        self.rows.setContentsMargins(2,3,5,3)
        viewport.setWidget(self.container)
        main.addWidget(viewport,1)
        self.preview=PreviewPlayer("PREVISUALIZAR RESULTADO SELECCIONADO",self)
        main.addWidget(self.preview)
        controls=QHBoxLayout()
        self.save_all=QPushButton("Guardar todo")
        self.save_all.setObjectName("primary")
        self.save_all.clicked.connect(lambda:self.save_files(True))
        controls.addWidget(self.save_all)
        self.save_selected=QPushButton("Guardar selección")
        self.save_selected.clicked.connect(lambda:self.save_files(False))
        controls.addWidget(self.save_selected)
        self.new_task=QPushButton("Nueva tarea / Descartar")
        self.new_task.setObjectName("stop")
        self.new_task.clicked.connect(self.ask_discard)
        controls.addWidget(self.new_task)
        if self.kind=="midi":
            self.edit_button=QPushButton("Editar en Piano Roll")
            self.edit_button.clicked.connect(self.request_editor)
            controls.addWidget(self.edit_button)
        controls.addStretch()
        main.addLayout(controls)
        self.path_label=QLabel("Los resultados se almacenan temporalmente en Recuperación.")
        self.path_label.setObjectName("muted")
        self.path_label.setWordWrap(True)
        main.addWidget(self.path_label)

    def populate(self):
        previous_checks={str(line.path.resolve()):line.checked.isChecked()
                         for line in self.lines}
        while self.rows.count():
            item=self.rows.takeAt(0)
            widget=item.widget()
            if widget is not None:widget.deleteLater()
        self.lines.clear()
        for i,path in enumerate(self.storage.items):
            line=TrackLine(path,i,self.play_file,self.stop_file,self,
                           self.editRequested.emit if self.kind=="midi" else None)
            line.checked.setChecked(previous_checks.get(str(Path(path).resolve()),True))
            self.rows.addWidget(line)
            self.lines.append(line)
        num=len(self.storage.items)
        if num==0:
            from PySide6.QtWidgets import QLabel
            placeholder=QLabel(
                "SIN PISTAS EN ESTA TAREA\n\n"
                "01  Importa una grabación o utiliza una pista del proyecto\n"
                "02  Ejecuta Separar o Convertir en el módulo correspondiente\n"
                "03  Escucha, selecciona y guarda aquí los resultados reales")
            placeholder.setObjectName("moduleEmptyState")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setWordWrap(True)
            placeholder.setMinimumHeight(154)
            self.rows.addStretch()
            self.rows.addWidget(placeholder)
        self.rows.addStretch()
        self.status.setText(
            f"{num} pista(s) temporales · selecciona cuáles conservar"
            if num else
            "Aún sin resultados. Importa un audio y pulsa Separar o Convertir.")
        if self.kind=="midi":
            current=str(self.storage.composite) if self.storage.composite else None
            self.version_choice.blockSignals(True)
            self.version_choice.clear()
            for i,v in enumerate(self.storage.versions):
                path=v["composite"]
                self.version_choice.addItem(
                    f"{i+1:02d} · {path.stem} · {len(v['items'])} pista(s)",
                    str(path))
            choice=self.version_choice.findData(current)
            if choice>=0:self.version_choice.setCurrentIndex(choice)
            self.version_choice.blockSignals(False)
        if self.storage.composite:
            self.path_label.setText("MIDI completo disponible al pulsar Guardar todo. "
                                    "Guardar selección exporta las pistas marcadas por separado.")
        else:
            self.path_label.setText("No se ha guardado ningún resultado automáticamente. "
                                    "Guardar todo, selección o Nueva tarea para descartarlo.")
        self.save_all.setEnabled(self.storage.pending and bool(num or self.storage.composite))
        self.save_selected.setEnabled(bool(num))
        self.new_task.setEnabled(self.storage.folder is not None)
        self.preview.clear()

    def choose_version(self,index):
        if self.kind!="midi" or index<0:return
        path=self.version_choice.itemData(index)
        for i,v in enumerate(self.storage.versions):
            if str(v["composite"])==path:
                if self.storage.select_version(i):
                    self.preview.clear()
                    self.populate()
                break

    def play_file(self,path):
        self.preview.load(path,autoplay=True)
        self.sourceSelected.emit(str(path))

    def stop_file(self):
        self.preview.stop()

    def selected_indices(self):
        return [row.index for row in self.lines if row.checked.isChecked()]

    def save_files(self,all_files):
        idx=self.selected_indices()
        if not all_files and not idx:
            QMessageBox.information(self,"Seleccionar pistas",
                "Marca al menos una pista que quieras guardar.")
            return []
        from export_dialog import export_files
        entries=self.storage.public_files(all_files,idx)
        copied=export_files(self,entries,self.storage.project_dir,
                            "Guardar resultados de "+self.kind,kind=self.kind)
        if copied:
            for p in entries:self.storage.saved.add(str(p))
            self.storage.manifest()
            self.save_directory=Path(copied[0]).parent
            self.status.setText(f"Exportados {len(copied)} archivo(s) a "
                                f"{self.save_directory}.")
            self.saved.emit(str(self.save_directory))
        return copied

    def request_editor(self):
        if self.kind!="midi":return
        selected=self.selected_indices()
        if len(selected)==1 and 0<=selected[0]<len(self.storage.items):
            target=self.storage.items[selected[0]]
            if target.is_file():
                self.editRequested.emit(str(target));return
        if self.storage.composite and self.storage.composite.is_file():
            self.editRequested.emit(str(self.storage.composite))
        else:
            QMessageBox.information(self,"Sin MIDI","Convierte primero el audio.")

    def ask_discard(self):
        if not self.storage.folder:return False
        result=QMessageBox.question(self,"Nueva tarea",
            "¿Descartar esta tarea y todos sus archivos temporales que no hayas guardado? "
            "Los archivos definitivos y los originales no se borrarán.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if result!=QMessageBox.Yes:
            return False
        self.preview.clear()
        self.storage.discard()
        self.populate()
        self.status.setText("Tarea descartada. Puedes comenzar otra.")
        return True
