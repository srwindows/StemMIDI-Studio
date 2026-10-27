"""Gestor visual de modelos de IA integrado en Preferencias.

Catálogo del motor, instalación explícita, papelera segura, actualización
con restauración y activación por módulo. Nunca descarga al abrirse.
"""
from __future__ import annotations
import time,uuid,shutil
from pathlib import Path
from PySide6.QtCore import Qt,QProcess
from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
    QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QPlainTextEdit,QMessageBox,QSplitter
)
import model_registry as registry

class ModelManager(QWidget):
    def __init__(self,main,parent=None):
        super().__init__(parent)
        self.main=main
        self.setObjectName("modelManager")
        self.setStyleSheet(
            "QWidget#modelManager {background:#03173a;color:#e0f8ff;}"
            "QLabel {background:transparent;color:#e0f8ff;}"
            "QTableWidget {background:#04183b;color:#e0f8ff;"
            "selection-background-color:#2bb1fc;alternate-background-color:#051e4c;}"
            "QHeaderView::section {background:#083483;color:#e0f8ff;}"
            "QPlainTextEdit {background:#04183e;color:#e0f8ff;}")
        self.proc=None
        self.operation=""
        self.running_record=None
        self.pending_backup=[]
        self._had_preexisting=False
        self._stage=None
        self._destination=None
        self.records={}
        self._build()
        self.refresh_table()

    def _build(self):
        lay=QVBoxLayout(self)
        lay.setContentsMargins(8,8,8,7)
        lay.setSpacing(8)
        title=QLabel("GESTOR DE MODELOS DE INTELIGENCIA ARTIFICIAL")
        title.setStyleSheet("font-size:16px;font-weight:800;color:#e0f8ff;")
        lay.addWidget(title)
        intro=QLabel(
            "Catálogo del motor audio-separator. Solo se pueden instalar modelos "
            "con salida compatible con los módulos actuales. Descarga voluntaria; "
            "el catálogo no concede permiso de redistribución. Las puntuaciones "
            "SDR proceden de evaluaciones diferentes y no son una clasificación universal.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#e0f8ff;")
        lay.addWidget(intro)
        toolbar=QHBoxLayout()
        toolbar.setSpacing(7)
        self.search=QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre, instrumento o archivo…")
        self.search.setMaximumWidth(350)
        self.search.textChanged.connect(self.refresh_table)
        toolbar.addWidget(self.search,1)
        self.family=QComboBox()
        self.family.addItems(["Todos los instrumentos","Voces","Batería","Bajo",
                              "Guitarra","Piano","Otros"])
        self.family.currentIndexChanged.connect(self.refresh_table)
        toolbar.addWidget(self.family)
        self.arch=QComboBox()
        self.arch.addItems(["Todas las arquitecturas","VR","MDX","MDXC","Demucs"])
        self.arch.currentIndexChanged.connect(self.refresh_table)
        toolbar.addWidget(self.arch)
        self.status_filter=QComboBox()
        self.status_filter.addItems(["Todos los modelos","Solo instalados",
                                     "Sin instalar","Utilizables en StemMIDI"])
        self.status_filter.currentIndexChanged.connect(self.refresh_table)
        toolbar.addWidget(self.status_filter)
        self.refresh_btn=QPushButton("↻ Actualizar catálogo")
        self.refresh_btn.clicked.connect(self.fetch_catalog)
        toolbar.addWidget(self.refresh_btn)
        lay.addLayout(toolbar)
        self.summary=QLabel()
        self.summary.setStyleSheet("color:#85f0ff;font-weight:bold;")
        lay.addWidget(self.summary)
        self.table=QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels([
            "Modelo","Arquitectura","Pistas","Compatibilidad","Estado","Tamaño"])
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i in (1,2,3,4,5):
            self.table.horizontalHeader().setSectionResizeMode(i,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.detail)
        self.table.setMinimumHeight(230)
        lay.addWidget(self.table,1)
        self.details=QLabel("Selecciona un modelo para consultar los detalles.")
        self.details.setWordWrap(True)
        self.details.setMinimumHeight(76)
        self.details.setStyleSheet(
            "color:#e0f8ff;background:#051e4c;border:1px solid #2bb1fc;"
            "padding:7px;border-radius:5px;")
        lay.addWidget(self.details)
        actions=QHBoxLayout()
        self.install=QPushButton("↓ Instalar")
        self.install.setObjectName("primary")
        self.install.clicked.connect(lambda:self.start_download("install"))
        actions.addWidget(self.install)
        self.update=QPushButton("↻ Reinstalar / actualizar")
        self.update.clicked.connect(lambda:self.start_download("update"))
        actions.addWidget(self.update)
        self.remove=QPushButton("Retirar a papelera")
        self.remove.clicked.connect(self.remove_selected)
        actions.addWidget(self.remove)
        self.use_general=QPushButton("Usar en separación")
        self.use_general.clicked.connect(lambda:self.activate("general"))
        actions.addWidget(self.use_general)
        self.use_drum=QPushButton("Usar en batería")
        self.use_drum.clicked.connect(lambda:self.activate("drum"))
        actions.addWidget(self.use_drum)
        self.cancel=QPushButton("Cancelar tarea")
        self.cancel.clicked.connect(self.cancel_running)
        actions.addWidget(self.cancel)
        lay.addLayout(actions)
        self.progress=QLabel("Catálogo local. «Actualizar catálogo» consulta los modelos compatibles.")
        self.progress.setStyleSheet("color:#e0f8ff;")
        lay.addWidget(self.progress)
        self.log=QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(86)
        self.log.setMaximumBlockCount(250)
        lay.addWidget(self.log)
        self.detail()

    def _row_record(self):
        items=self.table.selectedItems()
        if not items:return None
        name=self.table.item(items[0].row(),0)
        if name is None:return None
        return self.records.get(name.data(Qt.UserRole))

    def refresh_table(self):
        previous=self._row_record()
        previous_name=previous["filename"] if previous else None
        self.records=registry.catalog()
        query=self.search.text().casefold().strip()
        family=self.family.currentText()
        mapping={
            "Voces":"vocals","Batería":"drums","Bajo":"bass",
            "Guitarra":"guitar","Piano":"piano","Otros":"other"}
        wanted=mapping.get(family)
        arch=self.arch.currentText()
        filter_status=self.status_filter.currentIndex()
        active=registry.model_active()
        rows=[]
        for rec in self.records.values():
            if wanted:
                if wanted=="drums" and not (set(rec["stems"]) & {"drums","kick","snare","toms","hh","ride","crash"}):
                    continue
                if wanted!="drums" and wanted not in rec["stems"]:continue
            if arch not in ("Todas las arquitecturas",rec["architecture"]):continue
            if query and query not in " ".join((
                 rec["name"],rec["filename"],rec["architecture"],
                 " ".join(rec["stems"]))).casefold():continue
            installed=registry.installed(rec)
            if filter_status==1 and not installed:continue
            if filter_status==2 and installed:continue
            if filter_status==3 and not registry.compat(rec):continue
            rows.append(rec)
        rows.sort(key=lambda r:(not registry.installed(r),
            r["architecture"],r["name"].lower()))
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for i,rec in enumerate(rows):
            name=QTableWidgetItem(rec["name"])
            name.setData(Qt.UserRole,rec["filename"])
            active_where=[k for k,v in active.items() if v==rec["filename"]]
            state=("Activo ("+",".join(active_where)+")" if active_where
                else "Instalado" if registry.installed(rec) else "No instalado")
            dims=[
                name,QTableWidgetItem(rec["architecture"]),
                QTableWidgetItem(", ".join(registry.AUDIO_LABELS.get(x,x)
                    for x in rec["stems"])),
                QTableWidgetItem(", ".join(registry.compat(rec)) or "Solo catálogo"),
                QTableWidgetItem(state),
                QTableWidgetItem(
                    f"{registry.size(rec)/1048576:.1f} MB" if registry.size(rec)
                    else "—")
            ]
            for col,item in enumerate(dims):
                self.table.setItem(i,col,item)
            if rec["filename"]==previous_name:
                self.table.selectRow(i)
        self.table.blockSignals(False)
        loaded=sum(registry.installed(r) for r in self.records.values())
        self.summary.setText(
            f"{len(rows)} visibles · {len(self.records)} en catálogo · "
            f"{loaded} completos en disco · directorio Recuperación/modelos")
        self.detail()

    def detail(self):
        rec=self._row_record()
        busy=self.proc is not None
        installed=bool(rec and registry.installed(rec))
        managed=bool(rec and registry.model_is_managed(rec))
        active=registry.model_active()
        active_selected=bool(rec and rec["filename"] in active.values())
        general=bool(rec and registry.is_general(rec))
        drums=bool(rec and registry.is_drum(rec))
        self.install.setEnabled(bool(rec and registry.compat(rec)
                                     and not installed and not busy))
        self.update.setEnabled(bool(rec and installed and managed and not active_selected and not busy))
        self.remove.setEnabled(bool(rec and installed and managed and not active_selected and not busy))
        self.use_general.setEnabled(installed and general and not busy)
        self.use_drum.setEnabled(installed and drums and not busy)
        self.cancel.setEnabled(busy)
        self.refresh_btn.setEnabled(not busy)
        if not rec:
            self.details.setText("Selecciona un modelo para consultar su información y compatibilidad.")
            return
        files=", ".join(rec["files"])
        license_note=rec["license"]
        if installed and not managed:
            remove_note="Preexistente/protegido: no se permite borrarlo desde el gestor."
        elif managed:
            remove_note="Instalado por el gestor; al retirar, se traslada a una papelera recuperable."
        else:remove_note="Pendiente de instalar."
        self.details.setText(
            f"{rec['name']} · {rec['architecture']} · "
            f"{registry.quality_label(rec)}\n"
            f"Archivos: {files}. {remove_note}\n"
            f"Licencia: {license_note}")

    def fetch_catalog(self):
        if self.proc is not None:return
        self._run([str(registry.ENGINE),"-l","--list_format=json"],
                  "catalog",None)
        self.progress.setText("Consultando catálogo del motor…")

    def _busy_model(self,rec):
        if rec is None:return False
        sep=self.main.workbench.separator
        drum=self.main.drum_module
        busy=sep.process is not None or drum.process is not None
        busy=busy or drum.studio.process is not None
        if not busy:return False
        return (rec["filename"]==sep.profile.currentText()
                or rec["filename"] in (sep.profile.currentData(),
                                       drum.model_filename())
                or rec["filename"] in registry.model_active().values())

    def start_download(self,kind):
        if self.proc is not None:return
        rec=self._row_record()
        if not rec:return
        if self._busy_model(rec):
            QMessageBox.information(self,"Modelo en uso",
                "Detén el procesamiento de audio antes de actualizar este modelo.")
            return
        if not registry.compat(rec):return
        if not registry.ENGINE.is_file():
            QMessageBox.warning(self,"Motor ausente","No se encuentra audio-separator.")
            return
        if kind=="install" and registry.installed(rec):return
        if kind=="update" and (not registry.model_is_managed(rec)
                or rec["filename"] in registry.model_active().values()):return
        answer=QMessageBox.question(self,"Descarga de modelo",
            f"¿{'Reinstalar' if kind=='update' else 'Descargar'} {rec['name']}?\n"
            "El modelo puede ocupar cientos de MB y usará Internet. "
            "Revisa la licencia del autor antes de redistribuir los pesos.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        folder=registry.locate(rec) if kind=="update" else registry.filename_path(rec)
        folder.mkdir(parents=True,exist_ok=True)
        self._had_preexisting=(kind=="install" and
            any(registry.existing_files(rec)))
        self.pending_backup=[]
        self._destination=folder
        # La descarga se completa primero en una carpeta temporal propia.
        # Ningún fichero existente cambia antes de un éxito confirmado.
        self._stage=registry.HOME/".descargas_stemmidi"/(
            str(uuid.uuid4())+"_"+rec["filename"].replace(".","_"))
        self._stage.mkdir(parents=True,exist_ok=False)
        self._run([str(registry.ENGINE),"--model_filename",rec["filename"],
                   "--model_file_dir",str(self._stage),"--download_model_only"],
                  kind,rec)
        self.progress.setText("Descargando a carpeta temporal: "+rec["name"])

    def _promote_download(self,record):
        if self._stage is None or self._destination is None:
            raise ValueError("No hay descarga temporal válida")
        stage=self._stage
        dest=self._destination
        # No basta un archivo parcial; deben estar todos los pesos y configs.
        for name in record["files"]:
            candidate=stage/name
            if not candidate.is_file() or candidate.is_symlink():
                raise ValueError("Falta el archivo descargado: "+name)
            minimum=1024 if Path(name).suffix.lower() in (
                ".ckpt",".pth",".th",".onnx") else 1
            if candidate.stat().st_size<minimum:
                raise ValueError("Archivo descargado incompleto: "+name)
        old=[]
        promoted=[]
        backup=registry.HOME/".copias_modelos"/(
            str(uuid.uuid4())+"_"+record["filename"].replace(".","_"))
        backup.mkdir(parents=True,exist_ok=False)
        try:
            for name in record["files"]:
                current=dest/name
                if current.is_symlink():
                    raise ValueError("Destino de modelo simbólico no permitido")
                if current.exists():
                    current.rename(backup/name)
                    old.append((current,backup/name))
                (stage/name).rename(current)
                promoted.append(current)
        except Exception:
            for current in reversed(promoted):
                if current.is_file():current.unlink()
            for current,old_name in reversed(old):
                if old_name.exists():old_name.rename(current)
            raise
        # Las copias de la versión anterior permanecen recuperables.
        if not old:
            backup.rmdir()
        return registry.installed(record)

    def _clear_staging(self):
        if self._stage and self._stage.is_dir():
            base=(registry.HOME/".descargas_stemmidi").resolve()
            if self._stage.resolve().parent==base:
                shutil.rmtree(self._stage)
        self._stage=None
        self._destination=None

    def _run(self,command,operation,rec):
        self.proc=QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_process)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._error)
        self.operation=operation
        self.running_record=rec
        self._output=[]
        self.proc.start(command[0],command[1:])
        self.detail()

    def _read_process(self):
        if self.proc is None:return
        chunk=bytes(self.proc.readAllStandardOutput()).decode("utf-8","replace")
        if chunk:
            self._output.append(chunk)
            if self.operation!="catalog":
                last=[line.strip() for line in chunk.replace("\r","\n").splitlines() if line.strip()]
                if last:
                    self.log.appendPlainText(last[-1][-400:])
                    self.progress.setText(last[-1][-140:])

    def _error(self,error):
        if self.proc is not None and error==QProcess.FailedToStart:
            self.log.appendPlainText("Error arrancando el motor: "+self.proc.errorString())

    def _restore_backup(self):
        for original,backup in reversed(self.pending_backup):
            if backup.is_file():
                if original.is_file() and not original.is_symlink():
                    original.unlink()
                backup.rename(original)
        self.pending_backup=[]

    def _done(self,code,status):
        self._read_process()
        op=self.operation
        rec=self.running_record
        ok=code==0 and status==QProcess.NormalExit
        if op=="catalog" and ok:
            try:
                result=registry.cache_catalog_text("".join(self._output))
                self.progress.setText(f"Catálogo actualizado: {len(result)} modelos.")
            except (ValueError,TypeError) as exc:
                ok=False;self.progress.setText("Error en el catálogo: "+str(exc))
        elif op in ("install","update"):
            if ok and rec:
                try:
                    ok=self._promote_download(rec)
                except (ValueError,OSError) as exc:
                    self.log.appendPlainText("No se pudo instalar: "+str(exc))
                    ok=False
            if ok:
                if not self._had_preexisting:
                    registry.mark_managed(rec)
                self.progress.setText(
                    "Modelo instalado y comprobados sus archivos: "+rec["name"])
            else:
                self.progress.setText(
                    "Descarga fallida/cancelada. Archivos anteriores intactos.")
            self._clear_staging()
        elif not ok:
            self.progress.setText("No se ha podido completar la consulta.")
        proc=self.proc
        self.proc=None
        self.operation=""
        self.running_record=None
        self._output=[]
        if proc:proc.deleteLater()
        self.refresh_table()

    def cancel_running(self):
        if self.proc is None:return
        self.proc.kill()
        self.progress.setText("Cancelando descarga o consulta…")

    def remove_selected(self):
        if self.proc is not None:return
        rec=self._row_record()
        if not rec or not registry.model_is_managed(rec):return
        if self._busy_model(rec):
            QMessageBox.information(self,"Modelo en uso",
                "Detén la separación antes de retirar pesos activos.")
            return
        if rec["filename"] in registry.model_active().values():return
        response=QMessageBox.question(self,"Retirar modelo",
            "¿Trasladar este modelo a la papelera segura de StemMIDI?\n"
            "Los modelos preexistentes nunca se borran.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if response!=QMessageBox.Yes:return
        try:
            target=registry.remove_managed(rec)
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"Modelo protegido",str(exc))
            return
        self.progress.setText("Modelo movido a: "+str(target))
        self.refresh_table()

    def activate(self,kind):
        rec=self._row_record()
        if not rec:return
        try:registry.set_active(kind,rec["filename"])
        except ValueError as exc:
            QMessageBox.warning(self,"Modelo incompatible",str(exc))
            return
        if kind=="general":
            self.main.workbench.separator.refresh_model_registry()
        else:
            self.main.drum_module.refresh_model_choices()
        self.progress.setText("Modelo seleccionado para "+
            ("Separación de audio" if kind=="general" else "Desglose de batería"))
        self.refresh_table()
