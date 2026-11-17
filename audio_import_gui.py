"""Controles Qt compartidos para importar audio y carpetas desde el explorador."""
from __future__ import annotations
import file_dialogs
from pathlib import Path
from PySide6.QtWidgets import QLineEdit, QFileDialog, QMessageBox
from audio_import import DIALOG_FILTER, describe_audio, probe_audio


class DropPathEdit(QLineEdit):
    """Campo que acepta archivos/carpetas desde el explorador, según el modo."""
    def __init__(self, kind="file", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.imported = None
        self.setAcceptDrops(True)
        self.setToolTip("Puedes arrastrar aquí un archivo" if kind == "file" else
                        "Puedes arrastrar aquí una carpeta")

    def dragEnterEvent(self, event):
        urls=event.mimeData().urls()
        if len(urls)==1 and urls[0].isLocalFile():
            p=Path(urls[0].toLocalFile())
            if (p.is_file() if self.kind=="file" else p.is_dir()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self,event):
        self.dragEnterEvent(event)

    def dropEvent(self,event):
        urls=event.mimeData().urls()
        if len(urls)!=1 or not urls[0].isLocalFile():
            event.ignore()
            return
        path=Path(urls[0].toLocalFile())
        if not (path.is_file() if self.kind=="file" else path.is_dir()):
            event.ignore()
            return
        self.setText(str(path))
        if self.imported:
            self.imported(str(path))
        event.acceptProposedAction()


def pick_audio(parent, start):
    """Selector ampliado. Todos los archivos permite formatos no enumerados."""
    path, _ = file_dialogs.get_open_file_name(
        parent, "Importar archivo de audio o vídeo con audio",
        str(start), DIALOG_FILTER)
    return path


def check_and_describe(parent, filepath):
    """Valida un archivo seleccionado y devuelve sus propiedades."""
    try:
        info=probe_audio(filepath)
        return info,describe_audio(info)
    except (ValueError,OSError) as e:
        QMessageBox.warning(parent,"No se puede importar el audio",str(e))
        return None,str(e)
