"""Explorador de archivos de StemMIDI Studio.

Un solo QDialog diseñado para abrir, abrir varios, guardar y elegir carpetas.
Emplea QFileSystemModel para que las operaciones sobre archivos y directorios
sean reales. No depende de QFileDialog, KDialog ni iconos heredados.
"""
from __future__ import annotations

import fnmatch
import os
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QSortFilterProxyModel, Qt, QTimer, QSize, QEvent
from PySide6.QtGui import (QColor, QFont, QKeySequence, QShortcut, QPainter, QPainterPath, QPen, QBrush, QPixmap, QIcon)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QFileSystemModel, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSizePolicy, QSplitter, QTreeView, QVBoxLayout, QWidget
)

BROWSER_STYLE = """
QDialog#StemFileBrowser {background:#04193e;color:#e0f8ff;font-size:13px;}
QWidget#browserTop {background:#083687;border:1px solid #2bb1fc;border-radius:8px;}
QLabel {color:#e0f8ff;font-size:13px;}
QLabel#browserTitle {color:#e0f8ff;font-size:19px;font-weight:800;}
QLabel#browserSubtitle {color:#e0f8ff;font-size:12px;}
QLabel#browserEmpty {color:#e0f8ff;font-size:17px;font-weight:700;
  background:transparent;}
QLabel#browserFeedback {color:#85f0ff;font-size:13px;}
QFrame#browserPanel {background:#051f4f;border:1px solid #2bb1fc;border-radius:7px;}
QLineEdit, QComboBox {
  min-height:37px;background:#052052;color:#e0f8ff;font-size:13px;
  border:1px solid #2bb1fc;border-radius:6px;padding:3px 10px;
  selection-background-color:#2bb1fc;selection-color:#fff;
}
QLineEdit:focus, QComboBox:focus {
  border:2px solid #64edfa;background:#08378b;
}
QLineEdit:disabled, QComboBox:disabled {color:#e0f8ff;}
QListWidget#browserPlaces {
  background:#052154;color:#e0f8ff;
  border:1px solid #2bb1fc;border-radius:7px;
  outline:none;font-size:13px;
}
QListWidget#browserPlaces::item {
  min-height:38px;padding:2px 8px;margin:2px 3px;
  border-left:3px solid transparent;border-radius:4px;
}
QListWidget#browserPlaces::item:hover {
  background:#0c4dc3;color:#fff;border-left:3px solid #56d9f9;
}
QListWidget#browserPlaces::item:selected {
  background:#0d58df;color:#e0f8ff;border-left:3px solid #8bebfc;
  font-weight:700;
}
QTreeView#browserFiles {
  background:#051e4c;color:#e0f8ff;
  alternate-background-color:#052357;
  border:1px solid #2bb1fc;border-radius:7px;
  selection-background-color:#2bb1fc;selection-color:#fff;
  outline:none;font-size:13px;
}
QTreeView#browserFiles::item {
  min-height:35px;padding:3px 6px;
}
QTreeView#browserFiles::item:selected {
  background:#168bd2;color:#fff;font-weight:700;
}
QTreeView#browserFiles::item:hover:!selected {
  background:#0b49b8;
}
QHeaderView::section {
  background:#0a42a7;color:#e0f8ff;border:0;
  border-right:1px solid #2bb1fc;border-bottom:2px solid #53bfdf;
  padding:10px 7px;font-size:13px;font-weight:800;
}
QPushButton {
  min-height:36px;background:#0a44ab;color:#e0f8ff;
  font-size:13px;border:1px solid #2bb1fc;border-radius:6px;
  padding:3px 14px;font-weight:700;
}
QPushButton:hover {background:#0d59e0;color:white;border:1px solid #9debff;}
QPushButton:pressed {background:#0c4ec4;}
QPushButton:focus {border:2px solid #85eeff;}
QPushButton#browserPrimary {
  background:#049ddd;border:2px solid #80efff;color:#e0f8ff;
  font-size:14px;font-weight:800;min-height:40px;
}
QPushButton#browserPrimary:hover {background:#14c1ef;}
QPushButton:disabled {background:#052255;color:#e0f8ff;border-color:#2bb1fc;}
QCheckBox {color:#e0f8ff;font-size:13px;}
QCheckBox::indicator {width:18px;height:18px;}
QScrollBar:vertical {background:#052051;width:12px;}
QScrollBar::handle:vertical {background:#0d59e0;min-height:34px;border-radius:5px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QSplitter::handle {background:#0d59e0;}
QToolTip {color:white;background:#083689;border:1px solid #69c6ed;}
"""


def split_filters(text):
    parts=[piece.strip() for piece in str(text or "").split(";;") if piece.strip()]
    if not parts:
        return [("Todos los archivos (*)",["*"])]
    choices=[]
    for part in parts:
        match=re.search(r"\(([^()]*)\)",part)
        tokens=[s for s in (match.group(1).split() if match else ["*"])
                if "*" in s or "?" in s]
        choices.append((part,tokens or ["*"]))
    return choices


def _browser_icon(folder):
    """Iconografía simple y reconocible, diseñada en Qt, independiente del tema KDE."""
    image=QPixmap(26,24)
    image.fill(Qt.transparent)
    painter=QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    if folder:
        painter.setPen(QPen(QColor("#a2eeff"),1.3))
        painter.setBrush(QColor("#2fc5ec"))
        painter.drawRoundedRect(2,7,22,15,2.5,2.5)
        painter.setBrush(QColor("#8ce7fa"))
        painter.drawRoundedRect(3,4,11,6,1.5,1.5)
        painter.setPen(QPen(QColor("#176e93"),1.1))
        painter.drawLine(5,11,21,11)
    else:
        painter.setPen(QPen(QColor("#a2deff"),1.3))
        painter.setBrush(QColor("#d6f0ff"))
        painter.drawRoundedRect(6,2,16,21,2.1,2.1)
        painter.setBrush(QColor("#4eb4e1"))
        painter.drawRoundedRect(9,9,10,3,1,1)
        painter.drawLine(9,15,18,15)
        painter.drawLine(9,18,16,18)
    painter.end()
    return QIcon(image)


class _StyledFileSystemModel(QFileSystemModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._folder_icon=_browser_icon(True)
        self._file_icon=_browser_icon(False)
    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if orientation==Qt.Horizontal and role==Qt.DisplayRole:
            return ("Nombre","Tamaño","Tipo","Modificado")[section] if 0<=section<4 else ""
        return super().headerData(section,orientation,role)
    def data(self,index,role=Qt.DisplayRole):
        if role==Qt.DecorationRole and index.isValid() and index.column()==0:
            return self._folder_icon if self.isDir(index) else self._file_icon
        if role==Qt.DisplayRole and index.isValid() and index.column()==2:
            if self.isDir(index):return "Carpeta"
            path=Path(self.filePath(index))
            return path.suffix[1:].upper() if path.suffix else "Archivo"
        return super().data(index,role)

class _BrowserFooter(QFrame):
    """Zona fija en altura y adaptable en anchura: evita corrimientos de Qt."""
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.align_controls()
    def showEvent(self,event):
        super().showEvent(event)
        self.align_controls()
    def align_controls(self):
        if not hasattr(self,"name_field"):return
        margin=12
        label_width=68
        gutter=11
        control_x=margin+label_width+gutter
        control_width=max(140,self.width()-control_x-margin)
        self.label_name.setGeometry(margin,13,label_width,39)
        self.label_type.setGeometry(margin,60,label_width,39)
        self.name_field.setGeometry(control_x,10,control_width,43)
        self.type_field.setGeometry(control_x,57,control_width,43)

class _SearchFilter(QSortFilterProxyModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.query=""
        self.setDynamicSortFilter(True)
    def filterAcceptsRow(self,row,parent):
        if not self.query:return True
        source=self.sourceModel()
        idx=source.index(row,0,parent)
        if not idx.isValid():return False
        # Mantener el camino padre y las carpetas navegables durante la
        # búsqueda; ocultarlos invalida el índice raíz de esta vista.
        if source.isDir(idx):return True
        return self.query in source.fileName(idx).casefold()

class StemFileBrowser(QDialog):
    """Explorador de uso general. selected_paths y selected_filter tras accept."""
    def __init__(self,parent=None,caption="",initial="",filters="",kind="open"):
        super().__init__(parent)
        self.setObjectName("StemFileBrowser")
        self.setWindowTitle("StemMIDI Studio · "+(caption or "Explorador"))
        from neon_identity import NEON_BROWSER_CSS
        self.setStyleSheet(BROWSER_STYLE+NEON_BROWSER_CSS)
        self.setMinimumSize(850,570)
        screen=QApplication.primaryScreen()
        bounds=screen.availableGeometry() if screen else None
        self.resize(min(1180,bounds.width()-44) if bounds else 1180,
                    min(750,bounds.height()-48) if bounds else 750)
        self.kind=kind
        self.filter_choices=split_filters(filters)
        self.selected_paths=[]
        self.selected_filter=""
        self._history=[]
        self._history_index=-1
        self._updating=False
        self._model=_StyledFileSystemModel(self)
        self._model.setRootPath(QDir.rootPath())
        self._model.setFilter(QDir.AllDirs|QDir.Files|QDir.NoDotAndDotDot)
        self._model.setNameFilterDisables(False)
        self._model.directoryLoaded.connect(lambda *_:QTimer.singleShot(0,self._update_empty_state))
        self._proxy=_SearchFilter(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.rowsInserted.connect(lambda *_:self._update_empty_state())
        self._proxy.rowsRemoved.connect(lambda *_:self._update_empty_state())
        self._build_ui()
        initial_path=Path(str(initial or Path.home())).expanduser()
        if initial_path.is_file() or (not initial_path.is_dir() and
                                      initial_path.suffix and initial_path.parent.is_dir()):
            self._pending_file=initial_path.name
            initial_path=initial_path.parent
        else:
            self._pending_file=None
        self.go_to(initial_path)
        if self._pending_file and kind=="save":
            self.filename.setText(self._pending_file)
        elif self._pending_file and kind in ("open","multi"):
            self.filename.setText(self._pending_file)
        self._apply_filter()
        self._update_info()
        QTimer.singleShot(180,self._update_empty_state)

    def _button(self,text,tip,callback):
        btn=QPushButton(text,self)
        btn.setToolTip(tip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    def _build_ui(self):
        outer=QVBoxLayout(self)
        outer.setContentsMargins(14,12,14,12)
        outer.setSpacing(10)
        top=QFrame(self)
        top.setObjectName("browserTop")
        title_row=QHBoxLayout(top)
        title_row.setContentsMargins(12,8,12,8)
        titles=QVBoxLayout()
        head=QLabel("EXPLORADOR · StemMIDI Studio")
        head.setObjectName("browserTitle")
        titles.addWidget(head)
        sub=QLabel(self.windowTitle().split(" · ",1)[-1]+"  ·  Elegir sin salir del proyecto")
        sub.setObjectName("browserSubtitle")
        titles.addWidget(sub)
        title_row.addLayout(titles,1)
        tag=QLabel({"open":"ABRIR","multi":"SELECCIÓN MÚLTIPLE",
                    "save":"GUARDAR","dir":"CARPETA"}.get(self.kind,"ABRIR"))
        tag.setStyleSheet("color:#85f0ff;font-weight:800;padding-right:9px;")
        title_row.addWidget(tag)
        outer.addWidget(top)

        nav=QHBoxLayout()
        self.back=self._button("‹","Atrás",self.go_back)
        self.forward=self._button("›","Adelante",self.go_forward)
        self.up=self._button("↑","Subir una carpeta",self.go_up)
        self.home=self._button("⌂","Carpeta personal",lambda:self.go_to(Path.home()))
        self.refresh_btn=self._button("↻","Actualizar",self.refresh_folder)
        for b in (self.back,self.forward,self.up,self.home,self.refresh_btn):
            b.setFixedWidth(38)
            nav.addWidget(b)
        self.location=QLineEdit(self)
        self.location.setPlaceholderText("Ruta de carpeta o archivo")
        self.location.setToolTip("Puedes pegar una ruta absoluta aquí y pulsar Intro")
        self.location.returnPressed.connect(self.open_location)
        nav.addWidget(self.location,1)
        self.search=QLineEdit(self)
        self.search.setPlaceholderText("Buscar en esta carpeta")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(215)
        self.search.textChanged.connect(self._search)
        nav.addWidget(self.search)
        outer.addLayout(nav)

        split=QSplitter(Qt.Horizontal,self)
        self.shortcuts=QListWidget(split)
        self.shortcuts.setObjectName("browserPlaces")
        self.shortcuts.setFixedWidth(210)
        self.shortcuts.setSpacing(1)
        self._add_shortcuts()
        self.shortcuts.itemClicked.connect(self.open_shortcut)

        file_panel=QWidget(split)
        fp=QVBoxLayout(file_panel)
        fp.setContentsMargins(0,0,0,0)
        fp.setSpacing(4)
        self.view=QTreeView(file_panel)
        self.view.setObjectName("browserFiles")
        self.view.setIconSize(QSize(25,23))
        self.view.setModel(self._proxy)
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setUniformRowHeights(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0,Qt.AscendingOrder)
        self.view.header().setSectionResizeMode(0,QHeaderView.Stretch)
        for col,width in ((1,90),(2,85),(3,145)):
            self.view.header().setSectionResizeMode(col,QHeaderView.Fixed)
            self.view.setColumnWidth(col,width)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection if
                                   self.kind=="multi" else QAbstractItemView.SingleSelection)
        self.view.doubleClicked.connect(self.open_index)
        self.view.clicked.connect(self.select_index)
        self.view.selectionModel().selectionChanged.connect(
            lambda *_:self._update_info())
        fp.addWidget(self.view,1)
        self.empty_hint=QLabel("",self.view.viewport())
        self.empty_hint.setObjectName("browserEmpty")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setAttribute(Qt.WA_TransparentForMouseEvents,True)
        self.empty_hint.hide()
        self.view.viewport().installEventFilter(self)
        split.addWidget(self.shortcuts)
        split.addWidget(file_panel)
        split.setStretchFactor(0,0)
        split.setStretchFactor(1,1)
        outer.addWidget(split,1)

        status=QHBoxLayout()
        self.info=QLabel("Sin selección")
        self.info.setObjectName("browserFeedback")
        self.info.setStyleSheet("color:#e0f8ff;font-size:13px;")
        status.addWidget(self.info,1)
        self.hidden=QCheckBox("Mostrar ocultos")
        self.hidden.setChecked(False)
        self.hidden.toggled.connect(self._toggle_hidden)
        status.addWidget(self.hidden)
        self.new_folder=self._button("+ Carpeta","Crear una carpeta aquí",self.create_folder)
        status.addWidget(self.new_folder)
        outer.addLayout(status)

        footer=_BrowserFooter(self)
        footer.setObjectName("browserPanel")
        footer.setFixedHeight(112)
        footer.label_name=QLabel("Nombre",footer)
        footer.label_type=QLabel("Tipo",footer)
        self.filename=QLineEdit(footer)
        self.filename.setPlaceholderText(
            "Nombre del archivo" if self.kind=="save" else "Selecciona un archivo o carpeta")
        self.filename.returnPressed.connect(self.accept_selection)
        self.types=QComboBox(footer)
        for name,patterns in self.filter_choices:
            self.types.addItem(name,patterns)
        self.types.currentIndexChanged.connect(self._apply_filter)
        self.types.setToolTip("Filtrar archivos por formato; las carpetas siempre son accesibles")
        footer.name_field=self.filename
        footer.type_field=self.types
        outer.addWidget(footer)

        actions=QHBoxLayout()
        self.path_hint=QLabel("Doble clic para entrar en carpetas · Ctrl para selección múltiple")
        self.path_hint.setStyleSheet("color:#e0f8ff;font-size:12px;")
        actions.addWidget(self.path_hint,1)
        self.cancel_button=self._button("Cancelar","Cerrar sin seleccionar",self.reject)
        self.ok_button=self._button("Guardar" if self.kind=="save" else
                       "Elegir carpeta" if self.kind=="dir" else "Abrir",
                       "Confirmar selección",self.accept_selection)
        self.ok_button.setObjectName("browserPrimary")
        self.ok_button.setMinimumWidth(110)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.ok_button)
        outer.addLayout(actions)
        QShortcut(QKeySequence("Alt+Up"),self).activated.connect(self.go_up)
        QShortcut(QKeySequence("Alt+Left"),self).activated.connect(self.go_back)
        QShortcut(QKeySequence("Alt+Right"),self).activated.connect(self.go_forward)
        QShortcut(QKeySequence("F5"),self).activated.connect(self.refresh_folder)

    def _add_shortcuts(self):
        links=[
            ("⌂  Carpeta personal",Path.home()),
            ("▣  Escritorio",Path.home()/"Escritorio"),
            ("▤  Documentos",Path.home()/"Documentos"),
            ("↓  Descargas",Path.home()/"Descargas"),
            ("♫  Música",Path.home()/"Música"),
            ("▸  Vídeos",Path.home()/"Vídeos"),
            ("◧  Recuperación",Path("/media/javi/Recuperacion")),
            ("▣  Dispositivos",Path("/media")),
            ("⚙  Sistema de archivos",Path("/")),
        ]
        used=set()
        for label,p in links:
            if p.is_dir() and str(p) not in used:
                item=QListWidgetItem(label)
                item.setData(Qt.UserRole,str(p))
                item.setToolTip(str(p))
                self.shortcuts.addItem(item)
                used.add(str(p))
        if Path("/run/media").is_dir():
            item=QListWidgetItem("Discos montados")
            item.setData(Qt.UserRole,"/run/media")
            self.shortcuts.addItem(item)

    def _search(self,value):
        self._proxy.query=value.casefold().strip()
        self._proxy.invalidateFilter()
        self._update_info()
        self._update_empty_state()

    def _toggle_hidden(self,enabled):
        filters=QDir.AllDirs|QDir.Files|QDir.NoDotAndDotDot
        if enabled:filters|=QDir.Hidden
        self._model.setFilter(filters)
        self._update_info()
        self._update_empty_state()

    def _apply_filter(self,*_):
        if self.kind=="dir":
            self._model.setNameFilters([])
        else:
            name_filters=self.types.currentData() or ["*"]
            self._model.setNameFilters(name_filters)
        self.selected_filter=self.types.currentText()
        self._update_info()
        self._update_empty_state()

    def eventFilter(self,obj,event):
        if obj is self.view.viewport() and event.type()==QEvent.Resize:
            self._position_empty_state()
        return super().eventFilter(obj,event)

    def _position_empty_state(self):
        if not hasattr(self,"empty_hint"):return
        size=self.view.viewport().size()
        self.empty_hint.setGeometry(max(10,(size.width()-610)//2),
                                    max(16,(size.height()-150)//2),
                                    max(200,min(610,size.width()-20)),145)

    def _update_empty_state(self):
        if not hasattr(self,"empty_hint") or not hasattr(self,"current_dir"):return
        root=self.view.rootIndex()
        if not root.isValid():
            self.empty_hint.hide()
            return
        # QFileSystemModel carga los directorios de forma asíncrona.
        directory=self._model.index(str(self.current_dir))
        if not self._model.canFetchMore(directory) and self._proxy.rowCount(root)==0:
            if self.search.text().strip():
                title="No hay resultados para esta búsqueda"
                hint="Borra el texto de búsqueda o selecciona otra carpeta"
            else:
                title="Esta carpeta no contiene archivos visibles"
                hint="Prueba Escritorio, Recuperación o Dispositivos, en el panel izquierdo"
            self.empty_hint.setText(title+"\n\n"+hint)
            self._position_empty_state()
            self.empty_hint.show()
            self.empty_hint.raise_()
        else:self.empty_hint.hide()

    def _dir(self):
        return Path(self._model.rootPath() if not hasattr(self,"current_dir")
                    else self.current_dir)

    def go_to(self,path,remember=True):
        candidate=Path(str(path)).expanduser()
        if candidate.is_file():
            self.filename.setText(candidate.name)
            candidate=candidate.parent
        if not candidate.is_dir():
            self.info.setText("Carpeta no encontrada: "+str(candidate))
            return
        try:candidate=candidate.resolve()
        except OSError:return
        self.current_dir=candidate
        if remember:
            if self._history_index<len(self._history)-1:
                self._history=self._history[:self._history_index+1]
            if not self._history or self._history[-1]!=candidate:
                self._history.append(candidate)
            self._history_index=len(self._history)-1
        self.location.setText(str(candidate))
        self.location.setCursorPosition(0)
        src=self._model.index(str(candidate))
        self.view.setRootIndex(self._proxy.mapFromSource(src))
        self.view.clearSelection()
        self.search.clear()
        if self.kind!="save":self.filename.clear()
        self._update_info()
        QTimer.singleShot(200,self._update_empty_state)

    def go_back(self):
        if self._history_index>0:
            self._history_index-=1
            self.go_to(self._history[self._history_index],False)

    def go_forward(self):
        if self._history_index<len(self._history)-1:
            self._history_index+=1
            self.go_to(self._history[self._history_index],False)

    def go_up(self):
        parent=self._dir().parent
        if parent!=self._dir():self.go_to(parent)

    def refresh_folder(self):
        current=self._dir()
        self.go_to(current,False)

    def open_location(self):
        raw=self.location.text().strip()
        if not raw:return
        path=Path(raw).expanduser()
        if path.is_dir():self.go_to(path)
        elif path.is_file():
            self.go_to(path.parent)
            self.filename.setText(path.name)
        else:self.info.setText("La ruta no existe: "+raw)

    def open_shortcut(self,item):
        self.go_to(item.data(Qt.UserRole))

    def _path_for(self,index):
        source=self._proxy.mapToSource(index)
        return Path(self._model.filePath(source))

    def open_index(self,index):
        path=self._path_for(index)
        if path.is_dir():
            self.go_to(path)
        else:
            self.filename.setText(path.name)
            self.accept_selection()

    def select_index(self,index):
        path=self._path_for(index)
        self.filename.setText(path.name)
        self._update_info()

    def _selected_rows(self):
        rows=self.view.selectionModel().selectedRows()
        return [self._path_for(index) for index in rows]

    def _update_info(self):
        if not hasattr(self,"info"):return
        selected=self._selected_rows() if self.view.selectionModel() else []
        if not selected:
            self.info.setText(str(self._dir()))
            return
        if len(selected)>1:
            self.info.setText(f"{len(selected)} elementos seleccionados")
            return
        path=selected[0]
        try:
            if path.is_dir():
                summary="Carpeta"
            else:
                size=path.stat().st_size
                summary=f"{size / (1024**2):.2f} MiB"
            self.info.setText(f"{path.name} · {summary}")
        except OSError:self.info.setText(path.name)

    def create_folder(self):
        base=self._dir()
        from PySide6.QtWidgets import QInputDialog
        name,ok=QInputDialog.getText(self,"Nueva carpeta","Nombre de la carpeta")
        if not ok or not name.strip():return
        name=name.strip()
        if name in (".","..") or "/" in name or "\\" in name:
            QMessageBox.warning(self,"Nombre no válido","Elige un nombre de carpeta válido.")
            return
        target=base/name
        try:target.mkdir()
        except OSError as error:
            QMessageBox.warning(self,"No se pudo crear",str(error))
            return
        self.go_to(target)

    def _names_from_input(self):
        value=self.filename.text().strip().strip('"')
        if self.kind=="multi":
            # Se seleccionan varias filas aunque el campo Nombre esté vacío.
            selected=self._selected_rows()
            if selected:return selected
        if not value:return []
        path=Path(value).expanduser()
        return [path if path.is_absolute() else self._dir()/path]

    def accept_selection(self):
        paths=self._names_from_input()
        if self.kind=="dir":
            selected=self._selected_rows()
            paths=[selected[0]] if selected and selected[0].is_dir() else [self._dir()]
            if not paths[0].is_dir():
                self.info.setText("Selecciona una carpeta existente")
                return
        elif not paths:
            self.info.setText("Selecciona primero un archivo")
            return
        if self.kind in ("open","multi"):
            if len(paths)==1 and paths[0].is_dir():
                self.go_to(paths[0])
                return
            paths=[p for p in paths if p.is_file()]
            if not paths:
                self.info.setText("Selecciona un archivo existente")
                return
            patterns=self.types.currentData() or ["*"]
            valid=lambda p:any(fnmatch.fnmatch(p.name.casefold(),mask.casefold())
                               for mask in patterns)
            if any(not valid(path) for path in paths):
                self.info.setText("El archivo no coincide con el filtro seleccionado")
                return
        if self.kind=="save":
            name=paths[0]
            if not name.parent.is_dir():
                self.info.setText("La carpeta de destino no existe")
                return
            filters=self.types.currentData() or []
            endings=[p[1:] for p in filters if p.startswith("*.") and
                     "*" not in p[1:] and "?" not in p]
            if endings and not any(name.name.casefold().endswith(
                                   extension.casefold()) for extension in endings):
                name=Path(str(name)+endings[0])
            if name.exists():
                answer=QMessageBox.question(self,"Confirmar reemplazo",
                    f"Ya existe {name.name}. ¿Quieres reemplazarlo?",
                    QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
                if answer!=QMessageBox.Yes:return
            paths=[name]
        self.selected_paths=[str(p) for p in paths]
        self.selected_filter=self.types.currentText()
        self.accept()

def open_browser(parent=None,caption="",initial="",filters="",kind="open"):
    dialog=StemFileBrowser(parent,caption,initial,filters,kind)
    if dialog.exec()==QDialog.Accepted:
        return dialog.selected_paths,dialog.selected_filter
    return [],""
