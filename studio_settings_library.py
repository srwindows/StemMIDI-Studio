"""Biblioteca reutilizable de configuraciones para todos los módulos de StemMIDI.

Sólo controles; nunca nombres, ubicaciones ni audios de otros proyectos.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
 QLineEdit,QPushButton,QMessageBox,QListWidget,QFrame)
from ux_controls import PRESET_DIR

LIBRARY_FILE=PRESET_DIR/"biblioteca_ajustes_completos.json"
CATEGORIES={
 "Todos los módulos":None,
 "Monitor / Grabación":"monitor",
 "Laboratorio de grabación":"lab",
 "Separación de audio":"separation",
 "Audio a MIDI":"midi",
 "Desglose de batería":"drums",
 "Afinación vocal":"vocal",
 "Mezclador":"mixer",
 "Piano Roll":"piano",
 "Inicio · pistas y niveles":"home",
}
_ALLOWED=set(x for x in CATEGORIES.values() if x)

def capture_settings(main):
    """Fotografía de TODOS los ajustes disponibles, sin medios ni metadatos."""
    w=main.workbench
    home=main.studio_home
    mixer=w.mixer
    config={
        "monitor":main.monitor_preset_snapshot(),
        "lab":main.recording_lab.snapshot(),
        "separation":w.separator.parameter_snapshot(),
        "midi":w.converter.parameter_snapshot(),
        "drums":main.drum_module.snapshot_full_preset(),
        "vocal":main.vocal_module.full_preset_snapshot(),
        "piano":w.piano.view_snapshot(),
        "mixer":{"channels":mixer.preset_snapshot()
                     if mixer else getattr(main,"_pending_mixer_preset",None),
                 "levels":{name:parts["fader"].value()
                            for name,parts in home.mixer_rows.items()}},
        "home":{"stem_visibility":dict(home._stem_selection)},
    }
    # Asegurar que todos los perfiles son JSON puro, sin objetos Qt o Path.
    json.dumps(config,ensure_ascii=False,allow_nan=False)
    return config

def apply_settings(main,settings,category=None):
    """Aplicar parámetros sin tocar archivos, rutas ni el proyecto activo."""
    if not isinstance(settings,dict):raise ValueError("Configuración no válida")
    allowed={category} if category in _ALLOWED else _ALLOWED
    w=main.workbench
    home=main.studio_home
    def part(key):
        data=settings.get(key)
        return data if key in allowed and isinstance(data,dict) else None
    if (data:=part("monitor")) is not None:main.monitor_preset_apply(data)
    if (data:=part("lab")) is not None:main.recording_lab.apply_preset(data)
    if (data:=part("separation")) is not None:w.separator.apply_parameters(data)
    if (data:=part("midi")) is not None:w.converter.apply_parameters(data)
    if (data:=part("drums")) is not None:main.drum_module.apply_full_preset(data)
    if (data:=part("vocal")) is not None:main.vocal_module.apply_full_preset(data)
    if (data:=part("piano")) is not None:w.piano.apply_view_preset(data)
    if (data:=part("mixer")) is not None:
        channels=data.get("channels")
        if isinstance(channels,dict):
            main._pending_mixer_preset=channels
            if w.mixer is not None:w.mixer.apply_preset(channels)
        if isinstance(data.get("levels"),dict):
            for name,value in data["levels"].items():
                if name in home.mixer_rows:
                    fader=home.mixer_rows[name]["fader"]
                    fader.setValue(max(fader.minimum(),min(fader.maximum(),int(value))))
    if (data:=part("home")) is not None:
        selected=data.get("stem_visibility")
        if isinstance(selected,dict):
            for name,value in selected.items():
                if name in home.stem_checks:
                    home.stem_checks[name].setChecked(bool(value))
    home.refresh(force=True)

def read_library():
    if not LIBRARY_FILE.exists():return {}
    data=json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
    if not isinstance(data,dict):raise ValueError("Biblioteca de ajustes incorrecta")
    return data

def write_library(data):
    PRESET_DIR.mkdir(parents=True,exist_ok=True)
    temp=LIBRARY_FILE.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,
                                   allow_nan=False)+"\n",encoding="utf-8")
        temp.replace(LIBRARY_FILE)
    finally:
        if temp.exists():temp.unlink()

def save_named(main,name,category):
    title=str(name).strip()
    if not title or len(title)>70 or any(ord(c)<32 for c in title):
        raise ValueError("Escribe un nombre de 1 a 70 caracteres")
    if category not in CATEGORIES:raise ValueError("Tipo de configuración inválido")
    data=capture_settings(main)
    key=CATEGORIES[category]
    stored=data if key is None else {key:data[key]}
    library=read_library()
    identity=category+"\u241f"+title
    if identity in library:raise FileExistsError("Ya existe un ajuste con ese nombre en ese módulo.")
    library[identity]={"name":title,"category":category,
        "settings":stored,"created_at":datetime.now().isoformat(timespec="seconds")}
    write_library(library)
    return identity

def load_named(main,identity):
    profile=read_library().get(identity)
    if not isinstance(profile,dict):raise ValueError("Ajuste inexistente")
    settings=profile.get("settings")
    if not isinstance(settings,dict):raise ValueError("Ajuste dañado")
    if any(k not in _ALLOWED for k in settings):
        raise ValueError("El ajuste contiene módulos desconocidos")
    apply_settings(main,settings)
    return profile

def delete_named(identity):
    library=read_library()
    if identity not in library:return False
    del library[identity]
    write_library(library)
    return True

def can_apply(main):
    from PySide6.QtCore import QProcess
    w=main.workbench
    jobs=[w.converter.process,main.drum_module.process,
          main.drum_module.studio.process,main.vocal_module.process,
          main.recording_lab.process]
    return not (main.recording or main.record_pending or w.separator.busy
      or any(p is not None and
          (not hasattr(p,"state") or p.state()!=QProcess.NotRunning)
          for p in jobs)
      or (w.mixer is not None and w.mixer.process is not None
          and w.mixer.process.state()!=QProcess.NotRunning))

def settings_dialog(main):
    dialog=QDialog(main)
    dialog.setWindowTitle("Biblioteca de ajustes · StemMIDI Studio")
    dialog.resize(700,550)
    lay=QVBoxLayout(dialog)
    title=QLabel("CONFIGURACIONES REUTILIZABLES · TODOS LOS MÓDULOS")
    title.setObjectName("section")
    lay.addWidget(title)
    hint=QLabel("Guarda todos los controles o únicamente un módulo. "
       "Los ajustes permanecen disponibles en cualquier proyecto; "
       "no incluyen archivos, nombres ni ubicaciones de proyectos.")
    hint.setWordWrap(True);lay.addWidget(hint)
    row=QHBoxLayout()
    types=QComboBox(dialog)
    types.addItems(CATEGORIES)
    row.addWidget(QLabel("Módulo"))
    row.addWidget(types,1)
    name=QLineEdit(dialog)
    name.setPlaceholderText("Nombre del ajuste, por ejemplo: Mi mezcla suave")
    row.addWidget(name,2)
    lay.addLayout(row)
    listing=QListWidget(dialog)
    listing.setObjectName("settingsLibraryList")
    listing.setAlternatingRowColors(True)
    listing.setStyleSheet("""
      QListWidget#settingsLibraryList {
        background:#061938;color:#f5fcff;
        alternate-background-color:#0a2754;
        border:2px solid #1aaff0;border-radius:7px;
        font-size:14px;outline:none;
      }
      QListWidget#settingsLibraryList::item {
        min-height:34px;padding:6px 12px;
        border-bottom:1px solid #164981;
      }
      QListWidget#settingsLibraryList::item:selected {
        background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
          stop:0 #0968ed,stop:1 #00aeff);
        color:white;font-weight:800;border-left:3px solid #9dffff;
      }
      QListWidget#settingsLibraryList::item:hover:!selected {
        background:#0d519a;color:white;
      }
      QListWidget#settingsLibraryList::item:disabled {color:#83b4d2;}
    """)
    lay.addWidget(listing,1)
    info=QLabel("Selecciona una configuración o escribe un nombre para guardarla.")
    lay.addWidget(info)
    actions=QHBoxLayout()
    save=QPushButton("Guardar ajustes actuales")
    save.setObjectName("primary")
    restore=QPushButton("Aplicar selección")
    remove=QPushButton("Eliminar selección")
    close=QPushButton("Cerrar")
    for button in (save,restore,remove,close):actions.addWidget(button)
    lay.addLayout(actions)
    def refresh():
        chosen=listing.currentItem().data(Qt.UserRole) if listing.currentItem() else None
        listing.clear()
        try:
            profiles=read_library()
        except (OSError,ValueError) as exc:
            info.setText("Error al leer biblioteca: "+str(exc));return
        if not profiles:
            from PySide6.QtWidgets import QListWidgetItem
            empty=QListWidgetItem(
                "Todavía no hay configuraciones. Escribe un nombre y pulsa Guardar ajustes actuales.")
            empty.setFlags(Qt.NoItemFlags)
            listing.addItem(empty)
        for key,entry in sorted(profiles.items(),
                key=lambda kv:(kv[1].get("category",""),kv[1].get("name",""))):
            from PySide6.QtWidgets import QListWidgetItem
            item=QListWidgetItem(f'{entry.get("category","")} · {entry.get("name","")}')
            item.setData(Qt.UserRole,key)
            listing.addItem(item)
            if key==chosen:listing.setCurrentItem(item)
        info.setText(f"{len(profiles)} configuraciones guardadas.")
    def selected():
        item=listing.currentItem()
        return item.data(Qt.UserRole) if item else None
    def save_clicked():
        try:
            key=save_named(main,name.text(),types.currentText())
            refresh()
            for i in range(listing.count()):
                item=listing.item(i)
                if item.data(Qt.UserRole)==key:listing.setCurrentItem(item);break
            info.setText("Ajustes guardados sin incluir archivos ni rutas.")
        except (ValueError,OSError,TypeError) as exc:
            QMessageBox.warning(dialog,"No se pudo guardar",str(exc))
    def restore_clicked():
        if not selected():return
        if not can_apply(main):
            QMessageBox.warning(dialog,"Proceso activo",
                "Termina la grabación o procesamiento antes de cambiar ajustes.")
            return
        try:
            load_named(main,selected())
            info.setText("Ajustes aplicados; proyecto y archivos sin cambios.")
        except (ValueError,OSError,TypeError) as exc:
            QMessageBox.warning(dialog,"No se pudo aplicar",str(exc))
    def delete_clicked():
        key=selected()
        if not key:return
        answer=QMessageBox.question(dialog,"Eliminar configuración",
            "¿Eliminar este ajuste guardado? No se borrarán grabaciones ni proyectos.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer==QMessageBox.Yes:
            delete_named(key);refresh()
    save.clicked.connect(save_clicked)
    restore.clicked.connect(restore_clicked)
    remove.clicked.connect(delete_clicked)
    close.clicked.connect(dialog.accept)
    listing.itemDoubleClicked.connect(lambda *_:restore_clicked())
    refresh()
    return dialog.exec()
