"""Bibliotecas persistentes de separaciones y conversiones MIDI.

Recupera trabajos anteriores de las carpetas conocidas y de un índice local
ubicado íntegramente en Recuperación. No modifica archivos fuente.
"""
from __future__ import annotations
import file_dialogs

import json
from datetime import datetime
from pathlib import Path

import mido
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from preview_player import PreviewPlayer
from audio_import import MEDIA_EXTENSIONS

from studio_paths import workspace_root
ROOT=workspace_root(__file__)
INDEX=ROOT/"bibliotecas.json"
AUDIO_EXTS={"."+x for x in MEDIA_EXTENSIONS}
MIDI_EXTS={".mid",".midi",".kar"}


def load_index():
    try:
        raw=json.loads(INDEX.read_text(encoding="utf-8"))
        if isinstance(raw,dict):
            return {"separaciones":list(raw.get("separaciones",[])),
                    "midi":list(raw.get("midi",[])),
                    "carpetas_extra":list(raw.get("carpetas_extra",[]))}
    except (OSError,ValueError,TypeError):
        pass
    return {"separaciones":[],"midi":[],"carpetas_extra":[]}


def save_index(index):
    data=ROOT/"bibliotecas.json.tmp"
    data.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding="utf-8")
    data.replace(INDEX)


def register_result(kind,entry):
    if kind not in ("midi","separaciones"):
        return
    p=Path(entry).expanduser().resolve()
    if not p.exists():
        return
    data=load_index()
    values=[str(x) for x in data[kind]]
    values=[v for v in values if v!=str(p)]
    data[kind]=[str(p)]+values[:300]
    save_index(data)


def known_roots(kind):
    data=load_index()
    directories=[ROOT/("pistas_separadas" if kind=="separaciones" else "midi_generados")]
    pref=ROOT/("preferencias_separador.json" if kind=="separaciones" else "preferencias_midi.json")
    try:
        cfg=json.loads(pref.read_text(encoding="utf-8"))
        key="folder" if kind=="separaciones" else "output_dir"
        path=cfg.get(key)
        if path:directories.append(Path(path))
    except (OSError,ValueError,TypeError):
        pass
    for item in data["carpetas_extra"]:
        directories.append(Path(item))
    # Las carpetas que figuran en el índice son conocidas por los trabajos.
    for item in data[kind]:
        path=Path(item)
        directories.append(path if path.is_dir() else path.parent)
    output=[]
    seen=set()
    for d in directories:
        try:
            resolved=d.expanduser().resolve()
            if resolved.is_dir() and resolved not in seen:
                output.append(resolved);seen.add(resolved)
        except (OSError,RuntimeError):
            continue
    return output


def scan_jobs(kind):
    """Explora solo raíces explícitas y un nivel de subcarpetas, nunca todo el disco."""
    roots=known_roots(kind)
    extensions=MIDI_EXTS if kind=="midi" else AUDIO_EXTS
    groups={}
    seen=set()
    for root in roots:
        try:children=list(root.iterdir())[:4000]
        except OSError:continue
        # Un nivel para archivos de una separación y nada más.
        for node in children:
            if node.is_file() and node.suffix.lower() in extensions:
                files=[node]
            elif node.is_dir() and not node.name.startswith((".", "_")):
                try:files=[p for p in list(node.iterdir())[:1500]
                           if p.is_file() and p.suffix.lower() in extensions]
                except OSError:continue
            else:
                continue
            for path in files:
                if path.name.lower().startswith(("mezcla_previa_","vista_")):
                    continue
                canonical=str(path.resolve())
                if canonical in seen:continue
                seen.add(canonical)
                group=str(path.parent)
                groups.setdefault(group,[]).append(path)
    for files in groups.values():
        files.sort(key=lambda p:p.name.casefold())
    return sorted(groups.items(),key=lambda item:max((p.stat().st_mtime for p in item[1]),default=0),
                  reverse=True)


class ResultsWindow(QDialog):
    def __init__(self,kind,parent=None,focus_folder=None,focus_file=None,workspace=None):
        super().__init__(parent)
        # Asignar ANTES de la primera exploración de resultados.
        self.workspace=workspace
        self.kind=kind
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Biblioteca de separaciones" if kind=="separaciones" else
                            "Biblioteca de conversiones MIDI")
        self.resize(1160,780)
        self.setMinimumSize(820,555)
        self.focus_folder=Path(focus_folder).resolve() if focus_folder else None
        self.focus_file=Path(focus_file).resolve() if focus_file else None
        self.editor=None
        self.create_ui()
        self.refresh()

    def create_ui(self):
        layout=QVBoxLayout(self)
        layout.setContentsMargins(20,17,20,17)
        layout.setSpacing(12)
        top=QHBoxLayout()
        title=QLabel("BIBLIOTECA DE PISTAS SEPARADAS" if self.kind=="separaciones"
                     else "BIBLIOTECA MIDI · CONVERSIONES Y EDICIÓN")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch()
        refresh=QPushButton("Actualizar resultados")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        choose=QPushButton("Añadir carpeta…")
        choose.clicked.connect(self.add_folder)
        top.addWidget(choose)
        layout.addLayout(top)

        label=QLabel("Selecciona un trabajo o una pista para escucharla."
                     if self.kind=="separaciones" else
                     "Selecciona un MIDI convertido y ábrelo en el piano roll para editar las notas.")
        label.setObjectName("muted")
        label.setWordWrap(True)
        layout.addWidget(label)

        self.tree=QTreeWidget()
        self.tree.setHeaderLabels(["Trabajo / archivo","Tipo","Tamaño","Modificado"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setMinimumHeight(200)
        self.tree.currentItemChanged.connect(self.on_item_change)
        self.tree.itemDoubleClicked.connect(self.on_double_click)
        self.tree.header().resizeSection(0,550)
        self.tree.header().resizeSection(1,100)
        self.tree.header().resizeSection(2,95)
        layout.addWidget(self.tree,1)
        self.count=QLabel("Buscando trabajos…")
        self.count.setObjectName("status")
        layout.addWidget(self.count)

        self.preview=PreviewPlayer(
            "ESCUCHAR INSTRUMENTO O EXTRACCIÓN" if self.kind=="separaciones"
            else "ESCUCHAR CONVERSIÓN MIDI",self)
        layout.addWidget(self.preview)
        row=QHBoxLayout()
        self.open_editor=QPushButton("Abrir piano roll…"
                                    if self.kind=="midi" else "Mezclar pistas…")
        self.open_editor.setObjectName("primary")
        self.open_editor.clicked.connect(self.open_action)
        row.addWidget(self.open_editor)
        self.other_action=QPushButton("Convertir carpeta a MIDI…"
                                     if self.kind=="separaciones" else "Importar MIDI externo…")
        self.other_action.clicked.connect(self.secondary_action)
        row.addWidget(self.other_action)
        self.folder_button=QPushButton("Abrir carpeta en explorador")
        self.folder_button.clicked.connect(self.open_folder)
        row.addWidget(self.folder_button)
        row.addStretch()
        layout.addLayout(row)

    def refresh(self):
        workspace=getattr(self,"workspace",None)
        if workspace is None:
            # Ventana independiente: biblioteca histórica, como antes.
            data=scan_jobs(self.kind)
        else:
            # Una pestaña vinculada NO debe mostrar resultados de otro proyecto.
            project=getattr(workspace.main,"project_dir",None)
            data=[]
            if project:
                from project_layout import module_dir
                base=module_dir(project,self.kind)
                extensions=MIDI_EXTS if self.kind=="midi" else AUDIO_EXTS
                groups={}
                if base.is_dir():
                    for item in base.rglob("*"):
                        if item.is_file() and item.suffix.lower() in extensions:
                            resolved=item.resolve()
                            if base.resolve() in resolved.parents:
                                groups.setdefault(str(resolved.parent),[]).append(resolved)
                data=sorted(groups.items(),key=lambda group:group[0])
        self.tree.blockSignals(True)
        self.tree.clear()
        first=None
        wanted=None
        count=0
        for folder,files in data:
            parent=QTreeWidgetItem([Path(folder).name or folder,
                                   "Trabajo",str(len(files))+" archivos", ""])
            parent.setData(0,Qt.UserRole,folder)
            parent.setData(0,Qt.UserRole+1,"folder")
            parent.setToolTip(0,folder)
            self.tree.addTopLevelItem(parent)
            if not first:first=parent
            for path in files:
                suffix=path.suffix.lower().strip(".").upper()
                try:
                    size=f"{path.stat().st_size/1048576:.2f} MB"
                    modified=datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                except OSError:size="—";modified="—"
                item=QTreeWidgetItem([path.name,suffix,size,modified])
                item.setData(0,Qt.UserRole,str(path))
                item.setData(0,Qt.UserRole+1,"file")
                item.setToolTip(0,str(path))
                parent.addChild(item)
                count+=1
                if self.focus_file and path.resolve()==self.focus_file:
                    wanted=item
                elif not wanted and self.focus_folder and Path(folder)==self.focus_folder:
                    wanted=item
            parent.setExpanded(True)
        self.tree.blockSignals(False)
        if wanted:self.tree.setCurrentItem(wanted)
        elif first:
            self.tree.setCurrentItem(first.child(0) or first)
        self.count.setText(f"{count} archivo(s) · {len(data)} trabajo(s) encontrados")
        if not first:self.preview.clear()

    def current_path(self):
        item=self.tree.currentItem()
        if item is None:return None
        data=item.data(0,Qt.UserRole)
        return Path(data) if data else None

    def on_item_change(self,current,previous):
        if not current:
            self.preview.clear();return
        path=self.current_path()
        if path and path.is_file():
            if self.preview.current_file != str(path.resolve()):
                self.preview.load(path)
            if self.kind=="midi":
                try:
                    mid=mido.MidiFile(str(path))
                    n=sum(msg.type=="note_on" and msg.velocity>0
                          for track in mid.tracks for msg in track)
                    self.count.setText(f"{len(mid.tracks)} pistas · {n} notas · {path.name}")
                except (OSError,ValueError,EOFError):
                    self.count.setText(f"No se ha podido inspeccionar: {path.name}")
        else:
            self.preview.stop()

    def on_double_click(self,item,col):
        path=self.current_path()
        if not path:return
        if path.is_file() and self.kind=="midi":
            self.open_action()
        elif path.is_file():
            self.preview.load(path,autoplay=True)
        elif path.is_dir():
            item.setExpanded(not item.isExpanded())

    def open_action(self):
        path=self.current_path()
        if not path:return
        workspace=getattr(self,"workspace",None)
        if workspace is not None:
            if self.kind=="midi":
                if not path.is_file():
                    QMessageBox.information(self,"Selecciona un MIDI",
                                            "Selecciona un archivo MIDI concreto.")
                    return
                workspace.show_piano_roll(path)
            else:
                folder=path if path.is_dir() else path.parent
                sources=sorted(p for p in folder.iterdir()
                               if p.is_file() and p.suffix.lower() in AUDIO_EXTS
                               and not p.name.lower().startswith(("mezcla_","_")))
                workspace.show_mixer(sources)
            return
        if self.kind=="midi":
            if not path.is_file():
                QMessageBox.information(self,"Selecciona MIDI",
                                        "Haz clic en un MIDI dentro de la biblioteca.")
                return
            from piano_roll import PianoRollDialog
            dlg=PianoRollDialog(path,self)
            dlg.show()
            # Mantener referencias hasta cerrar; permite abrir varios editores.
            if not hasattr(self,"_editors"):
                self._editors=[]
            self._editors.append(dlg)
            dlg.destroyed.connect(lambda: self._editors.remove(dlg) if dlg in self._editors else None)
        else:
            folder=path if path.is_dir() else path.parent
            sources=sorted(p for p in folder.iterdir()
                           if p.is_file() and p.suffix.lower() in AUDIO_EXTS
                           and not p.name.lower().startswith(("mezcla_","_")))
            if not sources:return
            from mezclador import MixDialog
            dlg=MixDialog(sources,self)
            dlg.show()
            if not hasattr(self,"_mixers"):
                self._mixers=[]
            self._mixers.append(dlg)
            dlg.destroyed.connect(lambda: self._mixers.remove(dlg) if dlg in self._mixers else None)

    def secondary_action(self):
        path=self.current_path()
        workspace=getattr(self,"workspace",None)
        if workspace is not None:
            if self.kind=="midi":
                filename,_=file_dialogs.get_open_file_name(self,"Importar MIDI para edición",
                    str(ROOT/"midi_generados"),"MIDI (*.mid *.midi *.kar)")
                if filename:workspace.show_piano_roll(filename)
            elif path:
                workspace.use_stems_as_midi_source(path if path.is_dir() else path.parent)
            return
        if self.kind=="midi":
            from piano_roll import PianoRollDialog
            dlg=PianoRollDialog(None,self)
            dlg.show()
            self._editors=getattr(self,"_editors",[])
            self._editors.append(dlg)
            dlg.choose_file()
        else:
            if path is None:return
            from midi_dialog import AudioMidiDialog
            folder=path if path.is_dir() else path.parent
            dlg=AudioMidiDialog(self,stems_folder=folder)
            dlg.show()
            self._converters=getattr(self,"_converters",[])
            self._converters.append(dlg)

    def open_folder(self):
        path=self.current_path()
        if path is None:return
        folder=path if path.is_dir() else path.parent
        if folder.exists():QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def add_folder(self):
        if getattr(self,"workspace",None) is not None:
            QMessageBox.information(self,"Proyecto activo",
                "Esta biblioteca muestra solo los archivos guardados en el proyecto. "
                "Para trabajar con otros archivos, impórtalos desde el módulo correspondiente.")
            return
        folder=file_dialogs.get_existing_directory(self,"Añadir carpeta de resultados",
               str(ROOT))
        if not folder:return
        data=load_index()
        if folder not in data["carpetas_extra"]:
            data["carpetas_extra"].append(folder)
            save_index(data)
        self.focus_folder=Path(folder).resolve()
        self.refresh()

    def closeEvent(self,event):
        from PySide6.QtCore import QProcess
        for mixer in list(getattr(self,"_mixers",[])):
            if mixer.process is not None and mixer.process.state()!=QProcess.NotRunning:
                QMessageBox.information(self,"Mezcla en curso",
                    "Finaliza o cancela la exportación del mezclador antes de cerrar.")
                event.ignore();return
        for conv in list(getattr(self,"_converters",[])):
            if conv.process is not None and conv.process.state()!=QProcess.NotRunning:
                QMessageBox.information(self,"Conversión MIDI en curso",
                    "Finaliza o cancela la conversión antes de cerrar.")
                event.ignore();return
        # Proteger un editor abierto con cambios pendientes: las ventanas
        # hijas controlan individualmente las confirmaciones de guardado.
        for editor in list(getattr(self,"_editors",[])):
            if editor.isVisible() and getattr(editor,"dirty",False):
                editor.raise_();editor.activateWindow()
                QMessageBox.information(self,"Piano roll sin guardar",
                    "Guarda o descarta primero los cambios del editor MIDI abierto.")
                event.ignore()
                return
        self.preview.cleanup()
        event.accept()
