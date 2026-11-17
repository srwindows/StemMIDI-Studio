"""Resultados: vista compacta y arrastre de archivos reales entre módulos.

El candado cerrado conserva SOLO la tabla de ficheros y el transporte.
Desbloquear muestra el mismo módulo con controles, información y VU.
Los arrastres son URI locales con Qt.CopyAction; nunca mueven ni borran.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject,Qt,QEvent,QMimeData,QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QWidget,QFrame,QTableWidget,QListWidget,QAbstractItemView,QMessageBox
)

AUDIO={".wav",".flac",".mp3",".ogg",".m4a",".aac",".wma",".aif",".aiff",".opus"}
MIDI={".mid",".midi",".kar"}
ALLOWED=AUDIO|MIDI
# Solo el Mezclador y el conversor MIDI→audio admiten lote; los otros
# motores tienen un único campo de entrada y NO deben sustituir en
# silencio los primeros archivos por el último arrastrado.
SINGLE_SOURCE=frozenset(("sep","midi","wave","drums","vocal","piano"))
ACCEPTED={
    "sep":AUDIO,
    "midi":AUDIO,
    "results":frozenset(),
    "wave":AUDIO,
    "drums":AUDIO,
    "tracks":frozenset(),
    "mixer":ALLOWED,
    "piano":MIDI,
    "vocal":AUDIO,
    "drum_stems":frozenset(),
    "info":MIDI,
    "monitor":frozenset(),
}


class ResultsDragTable(QTableWidget):
    """Tabla que emite URI locales de filas seleccionadas, sin efectos MOVE."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setToolTip(
            "Selecciona uno o varios resultados y arrástralos a una "
            "ventana flotante compatible. El archivo original no se mueve.")

    def selected_file_paths(self):
        result=[]
        for model_index in self.selectionModel().selectedRows():
            entry=self.item(model_index.row(),0)
            path=entry.data(Qt.UserRole) if entry is not None else None
            if not path:
                continue
            file=Path(str(path))
            if file.is_file() and not file.is_symlink() and file.suffix.lower() in ALLOWED:
                result.append(file.resolve())
        return list(dict.fromkeys(result))

    def mimeData(self,items):
        mime=QMimeData()
        rows=sorted({item.row() for item in items if item is not None})
        paths=[]
        for row in rows:
            item=self.item(row,0)
            value=item.data(Qt.UserRole) if item else None
            if value is None:
                continue
            path=Path(str(value))
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in ALLOWED:
                paths.append(QUrl.fromLocalFile(str(path.resolve())))
        mime.setUrls(paths)
        return mime

    def supportedDragActions(self):
        return Qt.CopyAction

    def startDrag(self,actions):
        paths=self.selected_file_paths()
        if not paths:
            return
        mime=QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        drag=QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class FilesDragList(QListWidget):
    """Arrastre por copia desde listas MIDI, mezclador y resultados vocales."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setToolTip("Arrastra este archivo a otro módulo compatible. "
                        "No se mueve ni elimina el original.")

    def mimeData(self,items):
        mime=QMimeData()
        files=[]
        for item in items:
            data=item.data(Qt.UserRole)
            if not data:
                continue
            file=Path(str(data))
            if file.is_file() and not file.is_symlink() and file.suffix.lower() in ALLOWED:
                files.append(QUrl.fromLocalFile(str(file.resolve())))
        mime.setUrls(files)
        return mime

    def set_drop_handler(self,callback,extensions=ALLOWED):
        """Aceptar drop sobre las FILAS, no solo en el borde del panel."""
        self.drop_callback=callback
        self.drop_extensions=frozenset(extensions)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)

    def dragEnterEvent(self,event):
        callback=getattr(self,"drop_callback",None)
        paths=valid_mime_paths(event.mimeData())
        if callback and paths and all(p.suffix.lower() in self.drop_extensions
                                      for p in paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self,event):
        callback=getattr(self,"drop_callback",None)
        paths=valid_mime_paths(event.mimeData())
        if callback and paths and all(p.suffix.lower() in self.drop_extensions
                                      for p in paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self,event):
        callback=getattr(self,"drop_callback",None)
        paths=valid_mime_paths(event.mimeData())
        if callback and paths and all(p.suffix.lower() in self.drop_extensions
                                      for p in paths) and callback(paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def supportedDragActions(self):
        return Qt.CopyAction

    def startDrag(self,actions):
        items=self.selectedItems()
        if not items:
            current=self.currentItem()
            items=[current] if current is not None else []
        mime=self.mimeData(items)
        if not mime.hasUrls():
            return
        drag=QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


def set_compact_results(home,compact):
    """Mostrar lo solicitado, sin reconstruir ni duplicar widgets/motores."""
    compact=bool(compact)
    if compact and not getattr(home,"_results_is_compact",False):
        home._results_expanded_page=home.result_pages.currentIndex()
    if not compact:
        target=getattr(home,"_results_expanded_page",0)
        home._result_tab(target if target in (0,1,2) else 0)
    else:
        home._result_tab(0)

    for i in range(3):
        getattr(home,f"results_btn_{i}").setVisible(not compact)
    for widget in (
        home.results_folder,home.export_btn,home.discard_btn,
        home.result_hint,home.result_vu_caption,home.result_vu,
    ):
        if compact:
            widget.hide()
        elif widget is home.result_vu:
            widget.show()   # En flotante VU real, pero nunca inventado.
        else:
            widget.show()

    home._results_is_compact=compact
    home.files.setToolTip(
        "Arrastra uno o varios archivos a cualquier ventana flotante "
        "compatible (copia, sin borrar original)."
        if compact else
        "Ctrl/Mayús selecciona varias pistas. Puedes arrastrarlas "
        "a los otros módulos compatibles.")
    home.result_card.updateGeometry()


def valid_mime_paths(mime):
    if mime is None or not mime.hasUrls():
        return []
    urls=mime.urls()
    if not 1<=len(urls)<=64 or any(not u.isLocalFile() for u in urls):
        return []
    result=[]
    for url in urls:
        path=Path(url.toLocalFile())
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in ALLOWED:
            return []
        result.append(path.resolve())
    return list(dict.fromkeys(result))


class ProjectFileDropRouter(QObject):
    """Recibe drops sobre la tarjeta flotante REAL que edita ese medio."""
    def __init__(self,home):
        super().__init__(home)
        self.home=home
        self.manager=home._floating_manager
        self.card_kind=dict(zip(self.manager.cards,(
            "monitor","sep","midi","results","wave","drums","tracks",
            "mixer","piano","vocal","drum_stems","info"
        )))
        self.targets={}
        self.install()

    def install(self):
        for card,kind in self.card_kind.items():
            if kind in ("results","monitor","tracks","drum_stems"):
                continue
            self.attach(card)

    def attach(self,card):
        """Registrar superficies no especializadas; no anular DropPathEdit."""
        kind=self.card_kind[card]
        for widget in [card,card.body,*card.findChildren(QWidget)]:
            if widget in self.targets:
                continue
            # No interceptar entradas, combos, controles específicos, ni
            # los desplegables Qt. Las listas especializadas mantienen su drop.
            from PySide6.QtWidgets import (
                QAbstractItemView,QLineEdit,QComboBox,QAbstractButton,
                QSlider,QSpinBox,QDoubleSpinBox,QScrollBar,QTextEdit,
                QPlainTextEdit
            )
            if isinstance(widget,(
                    QAbstractItemView,QLineEdit,QComboBox,QAbstractButton,
                    QSlider,QSpinBox,QDoubleSpinBox,QScrollBar,QTextEdit,
                    QPlainTextEdit)):
                continue
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)
            self.targets[widget]=kind
        card.setToolTip(
            "Arrastra aquí archivos compatibles desde Resultados: "
            +("MIDI" if kind in ("info","piano") else
              "audio o MIDI" if kind=="mixer" else "audio")+
            ". El original se conserva.")

    def accepts(self,kind,paths):
        if kind not in ACCEPTED or not paths:
            return False
        if kind in SINGLE_SOURCE and len(paths)!=1:
            return False
        return all(p.suffix.lower() in ACCEPTED[kind] for p in paths)

    def eventFilter(self,obj,event):
        kind=self.targets.get(obj)
        if not kind:
            return False
        if event.type() not in (QEvent.DragEnter,QEvent.DragMove,QEvent.Drop):
            return False
        paths=valid_mime_paths(event.mimeData())
        if not self.accepts(kind,paths):
            event.ignore()
            return False
        if event.type()!=QEvent.Drop:
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return True
        handled=self.deliver(kind,paths)
        if handled:
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()
        return handled

    def deliver(self,kind,paths):
        """Seleccionar/abrir en el motor EXISTENTE; no lanzar el procesado."""
        home=self.home
        wb=home.workbench
        main=home.main
        if not self.accepts(kind,paths):
            return False
        done=0
        for path in paths:
            try:
                if kind=="sep":
                    if wb.separator.busy:
                        continue
                    wb.separator.on_import_selected(str(path))
                    if Path(wb.separator.file_edit.text()).resolve()!=path:
                        continue
                    # No empezar automáticamente una separación de IA.
                elif kind=="midi":
                    wb.converter.audio_path.setText(str(path))
                    wb.converter.source_preview.load(path)
                elif kind=="wave":
                    home.wave.set_file(path)
                    home.overview.set_file(path)
                    home.wave_title.setText(path.name)
                elif kind=="drums":
                    if home._drum_module is None or not home._drum_module.on_import_selected(str(path)):
                        continue
                elif kind=="vocal":
                    if home._vocal_module is None:
                        continue
                    studio=self.manager.other_expanders[home.vocal_card].vocal_studio
                    if studio is None or not studio.load_voice(str(path)):
                        continue
                elif kind=="info":
                    if not home.midi_to_audio.select_source(str(path)):
                        continue
                    if home.midi_to_audio.expanded_view:
                        home.midi_to_audio.expanded_view.refresh_files(force=True)
                elif kind=="piano":
                    wb.show_piano_roll(path)
                elif kind=="mixer":
                    expanded=self.manager.other_expanders[home.mix_card]
                    view=expanded.project_mixer
                    view.refresh_catalog(force=True)
                    key=str(path.resolve())
                    if key not in view.sources:
                        continue
                    view.selected.add(key)
                    view.refresh_catalog(force=True)
                    for index in range(view.file_list.count()):
                        item=view.file_list.item(index)
                        if item.data(Qt.UserRole)==key:
                            item.setCheckState(Qt.Checked)
                            break
                    if path.suffix.lower() in MIDI:
                        view._schedule_midi(key)
                else:
                    return False
                done+=1
            except (ValueError,OSError,RuntimeError) as err:
                home.result_hint.setText(
                    f"No se pudo cargar {path.name} en este módulo: {err}")
        if done:
            home.result_hint.setText(
                f"{done} archivo(s) enviados a {kind}. "
                "Los originales permanecen en Resultados.")
        return done>0


def install(home):
    router=ProjectFileDropRouter(home)
    home._result_file_drag_router=router
    return router
