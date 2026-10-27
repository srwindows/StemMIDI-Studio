"""Estado REAL de proyectos StemMIDI, sin mensajes genéricos.

Datos tomados de la carpeta y del manifiesto existentes en disco.
Ventana NO modal: permite consultar el proyecto mientras se actualiza.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (
    QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFrame,QGridLayout,
    QApplication
)

MODULE_LABELS={
    "grabaciones":"Grabaciones","stems":"Stems / Separación",
    "bateria":"Desglose de batería","audio_a_midi":"Audio a MIDI",
    "afinacion_vocal":"Afinación vocal","mezclador":"Mezclador",
    "piano_roll":"Piano Roll","resultados":"Resultados",
    "temporales":"Trabajo temporal","backup":"Copias de seguridad",
}
OUTPUTS=tuple(MODULE_LABELS)


def _date(path):
    try:return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y  %H:%M:%S")
    except OSError:return "Fecha no disponible"


def project_status(project_dir,manifest=None):
    """Devolver únicamente datos verificados del sistema de archivos."""
    root=Path(project_dir).expanduser().resolve()
    selected=Path(manifest).expanduser().resolve() if manifest else None
    manifests=sorted(root.glob("*.stemstudio.json")) if root.is_dir() else []
    if selected is None and len(manifests)==1:selected=manifests[0]
    exists=root.is_dir()
    valid=False
    error=""
    payload={}
    manifest_date=None
    if selected is None:
        error="No se ha identificado ningún manifiesto."
    elif selected.parent != root:
        error="El archivo de proyecto está fuera de la carpeta seleccionada."
    elif not selected.is_file():
        error="El archivo de proyecto todavía no existe en el disco."
    else:
        try:
            payload=json.loads(selected.read_text(encoding="utf-8"))
            valid=(isinstance(payload,dict)
                   and payload.get("application")=="StemMIDI Studio")
            if not valid:error="El JSON existe, pero no contiene un proyecto StemMIDI válido."
        except (ValueError,OSError,UnicodeError) as exc:
            error="No se puede leer el proyecto: "+str(exc)
        if valid:manifest_date=_date(selected)
    directories={}
    if exists:
        for name in OUTPUTS:
            folder=root/name
            if folder.is_dir() and not folder.is_symlink():
                try:
                    # Contar entradas DIRECTAS, sin recorrer todo el árbol.
                    files=sum(1 for item in folder.iterdir() if item.is_file()
                              and not item.is_symlink())
                except OSError:
                    files=None
                directories[name]={"exists":True,"files":files}
            else:
                directories[name]={"exists":False,"files":0}
    backups=[]
    backup=root/"backup"
    if backup.is_dir() and not backup.is_symlink():
        try:
            backups=sorted((f for f in backup.glob("Antes_de_abrir_*.zip")
                            if f.is_file() and not f.is_symlink()),
                           key=lambda p:p.stat().st_mtime,reverse=True)
        except OSError:
            backups=[]
    nested=root/root.name
    nested_project_dir=nested.is_dir()
    # Mostrar incongruencias reales y no inventar duplicaciones.
    declared_dir=payload.get("project_dir","") if valid else ""
    declared_mismatch=bool(declared_dir and
                           Path(str(declared_dir)).expanduser().resolve()!=root)
    return {
        "name":str(payload.get("project_name",root.name)) if valid else root.name,
        "root":str(root),"root_exists":exists,
        "manifest":str(selected) if selected else "",
        "filename":selected.name if selected else "No encontrado",
        "manifest_exists":bool(selected and selected.is_file()),
        "valid":valid,"error":error,"saved_at":manifest_date,
        "directories":directories,"backup_count":len(backups),
        "latest_backup":_date(backups[0]) if backups else None,
        "nested_project_dir":nested_project_dir,
        "declared_path_mismatch":declared_mismatch,
        "declared_path":declared_dir,
        "project_files_count":len(payload.get("project_files",[]))
            if valid and isinstance(payload.get("project_files"),list) else None,
    }


def _text_date():
    return datetime.now().strftime("%H:%M:%S")


class ProjectStatusDialog(QDialog):
    """Panel factual y dinámico, actualiza su contenido cada 750 ms."""
    def __init__(self,parent,project,manifest=None,action="guardado"):
        super().__init__(parent)
        self.setObjectName("liveProjectStatusDialog")
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.setWindowTitle("Proyecto · estado comprobado en el disco")
        self.setMinimumWidth(610)
        self.resize(735,525)
        self.root=Path(project).expanduser().resolve()
        self.manifest=Path(manifest).expanduser().resolve() if manifest else None
        self.action=action
        self.last_snapshot=None
        self.update_count=0

        layout=QVBoxLayout(self)
        layout.setContentsMargins(22,18,22,17)
        layout.setSpacing(10)
        self.title_label=QLabel(self)
        self.title_label.setObjectName("title")
        layout.addWidget(self.title_label)

        mainpanel=QFrame(self)
        mainpanel.setObjectName("inner")
        info=QGridLayout(mainpanel)
        info.setContentsMargins(14,12,14,12)
        info.setSpacing(8)
        def add(title,row):
            caption=QLabel(title,self)
            caption.setObjectName("muted")
            label=QLabel(self)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            info.addWidget(caption,row,0,Qt.AlignTop)
            info.addWidget(label,row,1)
            return label
        self.folder_label=add("Carpeta real:",0)
        self.file_label=add("Archivo JSON:",1)
        self.saving_label=add("Última escritura:",2)
        self.status_label=add("Estado comprobado:",3)
        layout.addWidget(mainpanel)

        self.modules_label=QLabel(self)
        self.modules_label.setObjectName("section")
        self.modules_label.setWordWrap(True)
        self.modules_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.modules_label)
        self.backup_label=QLabel(self)
        self.backup_label.setObjectName("muted")
        self.backup_label.setWordWrap(True)
        layout.addWidget(self.backup_label)
        self.extra_label=QLabel(self)
        self.extra_label.setObjectName("muted")
        self.extra_label.setWordWrap(True)
        layout.addWidget(self.extra_label)
        layout.addStretch(1)

        controls=QHBoxLayout()
        self.refresh_label=QLabel(self)
        self.refresh_label.setObjectName("muted")
        controls.addWidget(self.refresh_label,1)
        self.refresh_button=QPushButton("Actualizar ahora",self)
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        close_button=QPushButton("Cerrar",self)
        close_button.setObjectName("primary")
        close_button.clicked.connect(self.close)
        controls.addWidget(close_button)
        layout.addLayout(controls)

        self.timer=QTimer(self)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self):
        data=project_status(self.root,self.manifest)
        self.last_snapshot=data
        self.update_count+=1
        title={"guardado":"Proyecto guardado","guardado_como":"Copia independiente creada",
               "abierto":"Proyecto abierto"}.get(self.action,"Estado del proyecto")
        self.title_label.setText(title+" · "+data["name"])
        # Una carpeta + un archivo, claramente separados.
        self.folder_label.setText(data["root"]+"/" if data["root_exists"]
                                  else data["root"]+"  · NO EXISTE")
        self.file_label.setText(data["filename"]+
               "  (archivo, no otra carpeta)")
        self.saving_label.setText(data["saved_at"] or "Sin confirmación de escritura")
        self.status_label.setText(
            "JSON válido, presente en disco" if data["valid"]
            else "Atención: "+data["error"])
        module_info=[]
        for name,label in MODULE_LABELS.items():
            info=data["directories"].get(name)
            if info and info["exists"]:
                count=info["files"]
                module_info.append(label+(": "+str(count)+" archivo(s)"
                                          if count is not None else ": no accesible"))
        self.modules_label.setText(
            "Carpetas del proyecto presentes: "+str(len(module_info))+"/"+str(len(MODULE_LABELS))+
            "\n"+" · ".join(module_info))
        if data["backup_count"]:
            self.backup_label.setText(
                "Copias ZIP anteriores: "+str(data["backup_count"])+
                ". Última creada: "+str(data["latest_backup"])+
                ". Se crean al abrir el proyecto, no al pulsar Guardar.")
        else:
            self.backup_label.setText(
                "Copias ZIP anteriores: 0. Todavía no hay copia en backup; "
                "se creará cuando se vuelva a abrir el proyecto.")
        warnings=[]
        if data["nested_project_dir"]:
            warnings.append("Atención: existe otra carpeta «"+
                            self.root.name+"» dentro del proyecto.")
        else:
            warnings.append("Verificado: no hay una carpeta «"+
                            self.root.name+"» duplicada dentro del proyecto.")
        if data["declared_path_mismatch"]:
            warnings.append("Atención: el JSON declara otra ubicación: "+
                            str(data["declared_path"]))
        self.extra_label.setText("\n".join(warnings))
        self.refresh_label.setText("Comprobado en disco a las "+_text_date()+
                                   " · actualización automática cada 0,75 s")

    def closeEvent(self,event):
        self.timer.stop()
        super().closeEvent(event)


def show_project_status(parent,project,manifest=None,action="guardado"):
    old=getattr(parent,"_live_project_dialog",None)
    if old is not None:
        try:old.close()
        except RuntimeError:pass
    dialog=ProjectStatusDialog(parent,project,manifest,action)
    parent._live_project_dialog=dialog
    dialog.show()
    dialog.raise_()
    return dialog
