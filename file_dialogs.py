"""Selector común de StemMIDI: nuevo explorador propio y escucha previa."""
from __future__ import annotations
from pathlib import Path
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDialogButtonBox
)
MEDIA={".wav",".wave",".flac",".aif",".aiff",".mp3",".ogg",".opus",
       ".m4a",".aac",".wma",".mid",".midi",".kar",".mp4"}
LAST_FOLDER=None

def _start(directory):
    global LAST_FOLDER
    if directory:
        raw=Path(directory).expanduser()
        if raw.is_file() or (not raw.is_dir() and raw.suffix and raw.parent.is_dir()):
            return str(raw)
        if raw.is_dir():return str(raw)
    if LAST_FOLDER and Path(LAST_FOLDER).is_dir():return LAST_FOLDER
    return str(Path.home())

class MediaPreviewDialog(QDialog):
    """Audición previa: todavía no se ha importado/aceptado el archivo."""
    RESELECT=2
    def __init__(self,path,parent=None):
        super().__init__(parent)
        if parent is not None and parent.window().windowFlags() & Qt.WindowStaysOnTopHint:
            self.setWindowFlag(Qt.WindowStaysOnTopHint,True)
        self.setWindowTitle("Escuchar antes de seleccionar · "+Path(path).name)
        self.setMinimumWidth(760)
        self.resize(880,315)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(15,14,15,14)
        layout.setSpacing(9)
        title=QLabel("PREVISUALIZACIÓN DEL ARCHIVO · AUDIO / MIDI")
        title.setObjectName("title")
        layout.addWidget(title)
        self.path_label=QLabel(str(path))
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        hint=QLabel("Reproduce y comprueba el contenido antes de incorporarlo al proyecto. "
                    "El archivo original no se modifica.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        from preview_player import PreviewPlayer
        self.audition=PreviewPlayer("ESCUCHA PREVIA",self)
        self.audition.load(path)
        layout.addWidget(self.audition)
        row=QHBoxLayout()
        row.addStretch()
        self.back=QPushButton("← Volver al explorador")
        self.back.clicked.connect(lambda:self.done(self.RESELECT))
        row.addWidget(self.back)
        cancel=QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        choose=QPushButton("✓ Seleccionar archivo")
        choose.setObjectName("primary")
        choose.clicked.connect(self.accept)
        row.addWidget(choose)
        layout.addLayout(row)
    def done(self,result):
        try:self.audition.clear()
        finally:super().done(result)

def _audition_one(path,parent):
    if Path(path).suffix.lower() not in MEDIA:return QDialog.Accepted
    dlg=MediaPreviewDialog(path,parent)
    return dlg.exec()

def _studio_picker(parent,caption,initial,filter_text,kind):
    """Punto único: explorador rediseñado, no QFileDialog del sistema."""
    from studio_file_browser import open_browser
    return open_browser(parent,caption,initial,filter_text,kind)


def get_open_file_name(parent=None,caption="",directory="",filter_text="",*args,**kwargs):
    global LAST_FOLDER
    initial=_start(directory)
    while True:
        # Un único explorador moderno y homogéneo en todo el programa.
        chosen,selected_filter=_studio_picker(parent,caption,initial,filter_text,"open")
        path=chosen[0] if chosen else ""
        if not path:return "",""
        # «StemMIDI» es el nombre de la aplicación, NO un filtro .mid.
        # Comprobar extensiones explícitas de la máscara, no palabras de
        # su etiqueta. Anteriormente rechazaba proyectos .stemstudio.json.
        import re
        extensions=set(re.findall(r"\*\.([a-z0-9]+)",
                                  filter_text.casefold()))
        only_midi=(bool(extensions)
                   and extensions.issubset({"mid","midi","kar"}))
        if only_midi and Path(path).suffix.lower() not in (".mid",".midi",".kar"):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(parent,"Formato MIDI requerido",
                "Este selector solo admite archivos .mid, .midi y .kar.")
            initial=str(Path(path).parent)
            continue
        LAST_FOLDER=str(Path(path).parent)
        action=_audition_one(path,parent)
        if action==QDialog.Accepted:return path,selected_filter
        if action!=MediaPreviewDialog.RESELECT:return "",""
        initial=path

def get_open_file_names(parent=None,caption="",directory="",filter_text="",*args,**kwargs):
    global LAST_FOLDER
    initial=_start(directory)
    while True:
        paths,selected_filter=_studio_picker(parent,caption,initial,filter_text,"multi")
        if not paths:return [],""
        LAST_FOLDER=str(Path(paths[0]).parent)
        media=[p for p in paths if Path(p).suffix.lower() in MEDIA]
        if not media:return paths,selected_filter
        # Para lotes, escuchar el primer audio/MIDI antes de aceptar la importación.
        action=_audition_one(media[0],parent)
        if action==QDialog.Accepted:return paths,selected_filter
        if action!=MediaPreviewDialog.RESELECT:return [],""
        initial=paths[0]

def get_save_file_name(parent=None,caption="",directory="",filter_text="",*args,**kwargs):
    global LAST_FOLDER
    chosen,selected_filter=_studio_picker(parent,caption,_start(directory),filter_text,"save")
    result=(chosen[0],selected_filter) if chosen else ("","")
    if result[0]:LAST_FOLDER=str(Path(result[0]).parent)
    return result

def get_existing_directory(parent=None,caption="",directory="",*args,**kwargs):
    global LAST_FOLDER
    chosen,_=_studio_picker(parent,caption,_start(directory),"","dir")
    result=chosen[0] if chosen else ""
    if result:LAST_FOLDER=result
    return result
