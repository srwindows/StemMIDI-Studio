"""Estación de trabajo: todas las herramientas incrustadas en la ventana principal."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, QProcess
from PySide6.QtWidgets import (
    QWidget, QDialog, QSplitter, QTabWidget, QVBoxLayout, QLabel, QMessageBox,
    QHBoxLayout, QPushButton,
)

from task_staging import TaskStorage, TaskResults, TEMP_ROOT
from piano_roll import PianoRollDialog
from separador import SeparadorDialog
from midi_dialog import AudioMidiDialog
from bibliotecas import ResultsWindow


def embed(widget,parent):
    """QDialog existente pasa a panel normal sin ventana flotante."""
    widget.setParent(parent)
    widget.setWindowFlags(Qt.Widget)
    widget.setAttribute(Qt.WA_DeleteOnClose,False)
    widget.setMinimumSize(0,0)
    widget.setSizePolicy(__import__("PySide6.QtWidgets",fromlist=["QSizePolicy"]).QSizePolicy.Expanding,
                         __import__("PySide6.QtWidgets",fromlist=["QSizePolicy"]).QSizePolicy.Expanding)
    return widget


class IntegratedWorkspace:
    def __init__(self,main,tabs):
        self.main=main
        self.tabs=tabs
        if not getattr(main,"project_id",None):
            main.project_id=uuid4().hex
        self.separation_storage=TaskStorage("separaciones",main.project_id,getattr(main,"project_dir",None))
        self.midi_storage=TaskStorage("midi",main.project_id,getattr(main,"project_dir",None))
        self.drum_storage=TaskStorage("bateria",main.project_id,getattr(main,"project_dir",None))
        self.vocal_storage=TaskStorage("vocal",main.project_id,getattr(main,"project_dir",None))
        self.vocal_module=None
        self.drum_module=None
        self.midi_run_folder=None
        self.mixer=None
        self.separation_tab=QSplitter(Qt.Horizontal,tabs)
        self.midi_tab=QSplitter(Qt.Horizontal,tabs)

        self.separator=embed(SeparadorDialog(None),self.separation_tab)
        self.separator.embedded=True
        self.separator.workspace=self
        self.sep_results=TaskResults("separaciones",self.separation_storage,self.separation_tab)
        preferred=Path(self.separator.dest_edit.text()).expanduser()
        if not preferred.is_dir():
            preferred=__import__("task_staging").FINALS["separaciones"]
        self.sep_results.save_directory=preferred
        self.separation_tab.addWidget(self.separator)
        self.separation_tab.addWidget(self.sep_results)
        self.separation_tab.setChildrenCollapsible(False)
        self.separation_tab.setStretchFactor(0,5)
        self.separation_tab.setStretchFactor(1,5)

        self.converter=embed(AudioMidiDialog(None),self.midi_tab)
        self.converter.embedded=True
        self.converter.workspace=self
        self.midi_results=TaskResults("midi",self.midi_storage,self.midi_tab)
        self.converter.source_preview.setParent(self.midi_results)
        self.midi_results.layout().insertWidget(2,self.converter.source_preview)
        preferred_midi=Path(self.converter.outdir.text()).expanduser()
        if preferred_midi.is_dir():
            self.midi_results.save_directory=preferred_midi
        self.midi_tab.addWidget(self.converter)
        self.midi_tab.addWidget(self.midi_results)
        self.midi_tab.setChildrenCollapsible(False)
        self.midi_tab.setStretchFactor(0,5)
        self.midi_tab.setStretchFactor(1,5)

        self.piano=embed(PianoRollDialog(None,None),tabs)
        self.piano.in_workspace=True
        self.piano.workspace=self
        # Guardar MIDI como… es una exportación elegible también cuando
        # Piano Roll está integrado; ocultarlo impedía usar el módulo.
        self.piano.save_button.setVisible(True)
        self.piano.save_button.setText("Guardar MIDI como…")
        self.piano.save_button.setToolTip(
            "Elige nombre y ubicación para guardar una copia del MIDI editado.")
        self.apply_button=QPushButton("Aplicar edición a la tarea temporal")
        self.apply_button.setObjectName("primary")
        self.apply_button.setMaximumWidth(300)
        self.apply_button.clicked.connect(self.apply_piano_edit)
        self.piano.content_layout.insertWidget(6,self.apply_button,0,Qt.AlignLeft)
        self.apply_button.setEnabled(False)

        self.tabs.addTab(self.separation_tab,"Separar audio")
        self.tabs.addTab(self.midi_tab,"Audio a MIDI")
        self.tabs.addTab(self.piano,"Piano Roll")

        self.saved_audio=embed(ResultsWindow("separaciones",workspace=self),tabs)
        self.saved_midi=embed(ResultsWindow("midi",workspace=self),tabs)
        self.saved_audio.workspace=self
        self.saved_midi.workspace=self
        self.tabs.addTab(self.saved_audio,"Audio guardado")
        self.tabs.addTab(self.saved_midi,"MIDI guardado")
        self.sep_results.saved.connect(lambda _:self.saved_audio.refresh())
        self.midi_results.saved.connect(lambda _:self.saved_midi.refresh())

        self.sep_results.new_task.clicked.disconnect()
        self.sep_results.new_task.clicked.connect(lambda:self.discard_job("separaciones"))
        self.midi_results.new_task.clicked.disconnect()
        self.midi_results.new_task.clicked.connect(lambda:self.discard_job("midi"))
        self.midi_results.editRequested.connect(self.show_piano_roll)
        # Accesos directos existentes se redirigen a pestañas.
        self.separator.mix_button.clicked.disconnect()
        self.separator.mix_button.clicked.connect(lambda:self.show_mixer(self.separation_storage.items))
        self.separator.midi_button.clicked.disconnect()
        self.separator.midi_button.clicked.connect(
            lambda:self.use_stems_as_midi_source(self.separation_storage.items[0].parent)
            if self.separation_storage.items else None)
        self.separator.library_button.clicked.disconnect()
        self.separator.library_button.clicked.connect(self.focus_separation_results)
        self.converter.library_button.clicked.disconnect()
        self.converter.library_button.clicked.connect(self.focus_midi_results)
        self.converter.editor_button.clicked.disconnect()
        self.converter.editor_button.clicked.connect(
            lambda:self.show_piano_roll(self.midi_storage.composite))
        # Los listados existentes dentro del formulario no duplican el panel de resultados.
        self.separator.table.setVisible(False)
        self.separator.result_preview.setVisible(False)
        for label in self.separator.findChildren(QLabel):
            if label.text()=="PISTAS INDEPENDIENTES":
                label.setVisible(False)
            elif label.text()=="Guardar las pistas en":
                label.setText("Carpeta final sugerida")
        self.separator.mix_button.setVisible(False)
        self.separator.open_results_button.setVisible(False)
        self.separator.load_previous_button.setVisible(False)
        self.separator.library_button.setVisible(False)
        self.converter.result.setVisible(False)
        self.converter.output_preview.setVisible(False)
        for label in self.converter.findChildren(QLabel):
            if label.text()=="Destino":
                label.setText("Carpeta final sugerida")
        self.converter.editor_button.setVisible(False)
        self.converter.library_button.setVisible(False)
        self.converter.open.setVisible(False)
        self.converter.play.setVisible(False)
        # En este flujo "outdir" es el destino preferido de publicación, no
        # la ubicación de los archivos que procesa realmente el motor.
        self.converter.outdir.setPlaceholderText("Destino cuando decidas guardar las pistas")
        self.separator.dest_edit.setPlaceholderText("Destino final preferido")
        self.separation_tab.setSizes([650,620])
        self.midi_tab.setSizes([650,620])
        self.tabs.currentChanged.connect(self._tab_changed)
        self._restore_pending()
        # Nunca importar automáticamente medios de una sesión ajena a Inicio.
        self.separator.file_edit.clear()
        self.converter.audio_path.clear()
        self.piano.refresh_midi_list()

    def switch_project(self,project_id,project_dir=None):
        """Cambiar de proyecto sin borrar ni mezclar resultados de otro."""
        import re
        if not re.fullmatch(r"[0-9a-f]{32}",str(project_id)):
            raise ValueError("Identificador de proyecto inválido")
        if (self.separator.busy or
            (self.converter.process is not None and
             self.converter.process.state()!=QProcess.NotRunning) or
            (self.mixer is not None and self.mixer.process is not None and
             self.mixer.process.state()!=QProcess.NotRunning) or
            self.piano.dirty or self.main.recording or self.main.record_pending or
            (self.drum_module is not None and self.drum_module.process is not None) or
            (self.vocal_module is not None and self.vocal_module.process is not None) or
            (getattr(self.main,"recording_lab",None) is not None
             and self.main.recording_lab.process is not None)):
            QMessageBox.warning(self.main,"Operación en curso",
                "Finaliza o guarda el trabajo actual antes de cambiar de proyecto.")
            return False
        self.sep_results.preview.clear()
        self.midi_results.preview.clear()
        if self.mixer is not None:
            # No dejar cargadas pistas del proyecto anterior en otra pestaña.
            self.mixer.source_preview.cleanup()
            self.mixer.output_preview.cleanup()
            index=self.tabs.indexOf(self.mixer)
            if index>=0:self.tabs.removeTab(index)
            self.mixer.deleteLater()
            self.mixer=None
            placeholder=getattr(self.main,"mixer_placeholder",None)
            if placeholder is not None and self.tabs.indexOf(placeholder)<0:
                self.tabs.insertTab(self.tabs.indexOf(self.piano),placeholder,"Mezclador")
        self.converter.source_preview.clear()
        self.separator.source_preview.clear()
        self.main.record_preview.stop()
        if getattr(self.main,"recording_lab",None):
            self.main.recording_lab.reset_project_source()
            # Un proyecto nuevo no debe heredar los ajustes ni la opción
            # automática del laboratorio del proyecto anterior.
            from recording_lab_engine import DEFAULT as LAB_DEFAULT
            self.main.recording_lab.apply_preset(LAB_DEFAULT)
            self.main.recording_lab.presets.choices.setCurrentIndex(0)
        self.separation_storage=TaskStorage("separaciones",project_id,project_dir)
        self.midi_storage=TaskStorage("midi",project_id,project_dir)
        self.drum_storage=TaskStorage("bateria",project_id,project_dir)
        self.vocal_storage=TaskStorage("vocal",project_id,project_dir)
        if self.vocal_module is not None:
            self.vocal_module.switch_storage(self.vocal_storage)
        if self.drum_module is not None:
            self.drum_module.switch_storage(self.drum_storage)
        self.sep_results.storage=self.separation_storage
        self.midi_results.storage=self.midi_storage
        if project_dir:
            from project_layout import module_dir
            for result,kind in ((self.sep_results,"separaciones"),
                                (self.midi_results,"midi")):
                result.save_directory=module_dir(project_dir,kind)
        else:
            from task_staging import FINALS
            self.sep_results.save_directory=FINALS["separaciones"]
            self.midi_results.save_directory=FINALS["midi"]
        self.midi_run_folder=None
        self.main._pending_mixer_preset=None
        self.main.project_id=project_id
        self.main.last_file=None
        self.separator.file_edit.clear()
        self.converter.audio_path.clear()
        self.converter.folder_path.clear()
        self.converter.use_folder.setChecked(False)
        self.converter.output=None
        self.converter.chord_output=None
        self.separator.latest_outputs.clear()
        self.separator.current_folder=None
        self.separator.table.setRowCount(0)
        self.converter.output=None
        self.converter.result.setRowCount(0)
        self.converter.output_preview.clear()
        self.piano.preview.clear()
        self.piano.midi=None
        self.piano.current_path=None
        self.piano.dirty=False
        self.piano.tracks=[]
        self.piano.scene.clear()
        self.piano.tracks_list.clear()
        self.apply_button.setEnabled(False)
        self.sep_results.populate()
        self.midi_results.populate()
        # Los módulos de fuentes se refrescan en bind_project(), cuando
        # main.project_dir ya es la carpeta realmente seleccionada.
        home=getattr(self.main,"studio_home",None)
        if home:
            home.reset_project_view()
            home.refresh(force=True)
        return True

    def bind_project(self,project_dir):
        """Vincular TODAS las vistas al proyecto nombrado; sin destinos heredados."""
        from task_staging import FINALS
        project=Path(project_dir).expanduser().resolve() if project_dir else None
        from project_layout import module_dir
        separation=(module_dir(project,"separaciones") if project else FINALS["separaciones"])
        midi=(module_dir(project,"midi") if project else FINALS["midi"])
        # Estos campos son destinos de publicación, NO el directorio del motor.
        self.separator.dest_edit.setText(str(separation))
        self.converter.outdir.setText(str(midi))
        self.converter.filename.setText(project.name if project else "")
        self.separator.dest_edit.setReadOnly(bool(project))
        self.converter.outdir.setReadOnly(bool(project))
        self.sep_results.save_directory=separation
        self.midi_results.save_directory=midi
        self.saved_audio.focus_file=None
        self.saved_audio.focus_folder=None
        self.saved_midi.focus_file=None
        self.saved_midi.focus_folder=None
        self.saved_audio.refresh()
        self.saved_midi.refresh()
        if self.drum_module is not None:
            self.drum_module.refresh_sources()
        if self.vocal_module is not None:
            self.vocal_module.refresh_sources()
        self.converter.refresh_project_stems()
        self.piano.refresh_midi_list()
        if self.mixer is not None:
            self.mixer.project_dir=project
        return project

    def _restore_pending(self):
        if self.separation_storage.pending:
            self.sep_results.status.setText("Tarea temporal recuperada tras abrir el programa. "
                                             "Puedes escuchar, guardar o descartar.")
        if self.midi_storage.pending:
            self.midi_results.status.setText("Tarea MIDI temporal recuperada. "
                                              "No se ha borrado ni guardado sin permiso.")
            # Recuperar la FUENTE ORIGINAL de la conversión registrada,
            # incluso si la preferencia antigua la dejó vacía.
            converter=self.converter
            if (not converter.audio_path.text().strip()
                    and not converter.use_folder.isChecked()
                    and self.midi_storage.composite):
                report=self.midi_storage.composite.with_suffix(".json")
                try:
                    import json
                    data=json.loads(report.read_text(encoding="utf-8"))
                    candidates=[Path(x.get("file","")).expanduser()
                        for x in data.get("tracks",[])
                        if isinstance(x,dict) and x.get("file")]
                    source=next((p for p in candidates if p.is_file()),None)
                    if source is not None:
                        converter.on_import_file(str(source))
                except (OSError,ValueError,TypeError):
                    pass

    def _tab_changed(self,idx):
        if self.tabs.widget(idx)==self.saved_audio:
            self.saved_audio.refresh()
        elif self.tabs.widget(idx)==self.saved_midi:
            self.saved_midi.refresh()

    def main_tab(self,kind):
        self.tabs.setCurrentWidget(self.separation_tab if kind=="separaciones" else self.midi_tab)

    def focus_separation_results(self):
        self.sep_results.populate()
        self.main_tab("separaciones")

    def focus_midi_results(self):
        self.midi_results.populate()
        self.main_tab("midi")

    def select_midi_source(self,path):
        if path and Path(path).is_file():
            self.converter.on_import_file(str(path))
        self.main_tab("midi")

    def select_separation_source(self,path):
        if path and Path(path).is_file():
            self.separator.on_import_selected(str(path))
        self.main_tab("separaciones")

    def use_stems_as_midi_source(self,folder):
        if folder and Path(folder).is_dir():
            self.converter.on_import_folder(str(folder))
        self.main_tab("midi")

    def use_selected_stems_as_midi_source(self,paths):
        """Solo utiliza las casillas marcadas en esta tarea."""
        import shutil
        from task_staging import inside
        selected=[Path(p).resolve() for p in paths if Path(p).is_file()]
        store=self.separation_storage
        if not store.folder or not selected or any(
                not inside(p,store.folder) for p in selected):
            QMessageBox.warning(self.main,"Pistas no válidas",
                                "Marca stems temporales de esta tarea.")
            return
        if len(selected)==1:
            self.converter.on_import_file(str(selected[0]))
        else:
            folder=store.processing_folder/"_transferencia_midi_seleccionada"
            folder.mkdir(parents=True,exist_ok=True)
            for entry in folder.iterdir():
                if entry.is_file() and not entry.is_symlink():entry.unlink()
            for path in selected:
                shutil.copy2(path,folder/path.name)
            self.converter.on_import_folder(str(folder))
        self.main_tab("midi")

    def prepare_task(self,kind):
        store=self.separation_storage if kind=="separaciones" else self.midi_storage
        other=self.converter if kind=="separaciones" else self.separator
        if kind=="separaciones" and self.converter.process is not None and self.converter.process.state()!=QProcess.NotRunning:
            QMessageBox.information(self.main,"Audio usado en otra operación",
                "Finaliza primero la conversión MIDI antes de descartar pistas que pueda estar utilizando.")
            return False
        if kind=="midi":
            # Repetir con otros parámetros conserva la fuente y todas las
            # tomas MIDI anteriores; solo "Nueva tarea" las descarta.
            self.midi_run_folder=store.next_midi_run()
            self.midi_results.status.setText(
                "Procesando otra versión; las anteriores siguen disponibles.")
            return True
        if store.folder and store.folder.exists():
            answer=QMessageBox.question(self.main,"Nueva tarea",
                "La tarea anterior sigue en el almacenamiento temporal.\n"
                "¿Descartarla para comenzar una nueva? Solo se borrarán sus archivos "
                "temporales; no se eliminarán los originales ni los archivos guardados.",
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if answer!=QMessageBox.Yes:return False
            if kind=="midi" and self.piano.dirty:
                QMessageBox.information(self.main,"Piano Roll",
                    "Aplica primero las ediciones o descártalas desde el editor.")
                return False
            self._discard_without_question(kind)
        store.start()
        panel=self.sep_results if kind=="separaciones" else self.midi_results
        panel.populate()
        panel.status.setText("Procesando… el resultado quedará aquí sin guardar.")
        return True

    def _discard_without_question(self,kind):
        store=self.separation_storage if kind=="separaciones" else self.midi_storage
        result=self.sep_results if kind=="separaciones" else self.midi_results
        result.preview.clear()
        if kind=="separaciones":
            self.separator.result_preview.clear()
            self.separator.source_preview.stop()
            # La fuente permanece cargada también en el separador para
            # comparar calidad/modelos sin tener que importar otra vez.
            self.separator.latest_outputs.clear()
            self.separator.current_folder=None
            self.separator.table.setRowCount(0)
        else:
            self.converter.output_preview.clear()
            self.converter.source_preview.stop()
            # Nunca borrar el audio original ni su ruta al terminar una
            # conversión o pedir otra toma: se mantiene hasta Importar nuevo.
            self.converter.output=None
            self.converter.result.setRowCount(0)
            self.piano.preview.clear()
            self.piano.dirty=False
            self.piano.current_path=None
            self.piano.midi=None
            self.piano.tracks=[]
            self.piano.scene.clear()
            self.piano.tracks_list.clear()
            self.apply_button.setEnabled(False)
        store.discard()
        if kind=="midi":self.midi_run_folder=None
        result.populate()

    def discard_job(self,kind):
        source=self.separator if kind=="separaciones" else self.converter
        if ((kind=="separaciones" and source.busy) or
            (kind=="midi" and source.process is not None and source.process.state()!=QProcess.NotRunning)):
            QMessageBox.information(self.main,"Proceso en curso",
                "Cancela o termina el procesamiento antes de descartar la tarea.")
            return False
        if kind=="separaciones" and self.converter.process is not None and self.converter.process.state()!=QProcess.NotRunning:
            QMessageBox.information(self.main,"Pistas en uso",
                "Finaliza la conversión MIDI que esté utilizando estos instrumentos.")
            return False
        if kind=="midi" and self.piano.dirty:
            QMessageBox.information(self.main,"Edición MIDI pendiente",
                "Aplica la edición o descarta los cambios antes de crear otra tarea.")
            return False
        store=self.separation_storage if kind=="separaciones" else self.midi_storage
        if not store.folder:return False
        ans=QMessageBox.question(self.main,"Nueva tarea · Descartar",
            "¿Eliminar el resultado TEMPORAL de esta tarea? Esta operación no borra "
            "el archivo original ni las pistas/MIDI que hayas guardado.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if ans!=QMessageBox.Yes:return False
        self._discard_without_question(kind)
        return True

    def on_separation_completed(self,folder):
        try:
            self.separation_storage.set_separation(folder)
            self.sep_results.populate()
            self.converter.refresh_project_stems()
            self.converter.form_tabs.setCurrentIndex(0)
            home=getattr(self.main,"studio_home",None)
            if home:
                home.apply_stem_visibility()
                home.refresh(force=True)
            self.sep_results.status.setText(
                "Separación terminada. Escucha y compara los stems. "
                "Cuando estés conforme, pulsa «Aprobar separación y distribuir stems».")
        except (OSError,ValueError) as exc:
            self.sep_results.status.setText("Error recogiendo resultados: "+str(exc))
        home=getattr(self.main,"studio_home",None)
        if home is None or self.tabs.currentWidget()!=home:
            self.main_tab("separaciones")

    def on_midi_completed(self,path):
        try:
            self.midi_storage.set_midi(path)
            self.midi_results.populate()
            home=getattr(self.main,"studio_home",None)
            if home:home.refresh(force=True)
            self.midi_results.status.setText("Transcripción terminada. Escucha las "
                    "pistas MIDI; puedes editar, guardar todo o solo algunas.")
        except (OSError,ValueError) as exc:
            self.midi_results.status.setText("Error preparando MIDI: "+str(exc))
        home=getattr(self.main,"studio_home",None)
        if home is None or self.tabs.currentWidget()!=home:
            self.main_tab("midi")

    def show_piano_roll(self,path=None):
        path=Path(path) if path else self.midi_storage.composite
        if not path or not path.is_file():
            QMessageBox.information(self.main,"Sin MIDI",
                "Convierte audio, o importa un archivo MIDI desde MIDI guardado.")
            return
        if self.piano.dirty and self.piano.current_path and path.resolve()!=self.piano.current_path:
            if not self.piano.check_discard():return
        # Un archivo MIDI histórico se importa al área de trabajo temporal
        # antes de editar; el original permanece fuera del espacio de edición.
        store=self.midi_storage
        if not store.folder or not __import__("task_staging").inside(path,store.folder):
            if not self.prepare_task("midi"):
                return
            dest=store.processing_folder/(path.stem[:85]+".mid")
            if dest.exists():
                dest=__import__("task_staging").unique_dest(dest.parent,dest.name)
            __import__("shutil").copy2(path,dest)
            try:
                store.set_midi(dest)
                self.midi_results.populate()
            except (OSError,ValueError) as exc:
                QMessageBox.warning(self.main,"No se puede editar MIDI",str(exc))
                return
            path=dest
        self.piano.open_midi(path)
        self.apply_button.setEnabled(True)
        self.tabs.setCurrentWidget(self.piano)

    def apply_piano_edit(self):
        store=self.midi_storage
        if not self.piano.midi or not store.folder:
            return
        dest=store.folder/("editado_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f")+".mid")
        try:
            self.midi_results.preview.clear()
            self.piano.save_file(dest)
            store.set_midi(dest)
            self.midi_results.populate()
            self.piano.open_midi(dest)
            self.converter.output=dest
            self.midi_results.status.setText("Edición aplicada a la tarea TEMPORAL; "
                "elige Guardar todo o Guardar selección para conservarla definitivamente.")
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self.main,"Error aplicando cambios",str(exc))

    def show_mixer(self,sources):
        sources=[Path(p) for p in sources if Path(p).is_file()]
        if not sources:return
        from mezclador import MixDialog
        if self.mixer is not None:
            if self.mixer.process is not None and self.mixer.process.state()!=QProcess.NotRunning:
                QMessageBox.information(self.main,"Mezcla en curso",
                    "Termina la exportación de la mezcla antes de cambiar de pistas.")
                return
            self.mixer.source_preview.cleanup()
            self.mixer.output_preview.cleanup()
            idx=self.tabs.indexOf(self.mixer)
            if idx>=0:self.tabs.removeTab(idx)
            self.mixer.deleteLater()
        self.mixer=embed(MixDialog(sources,None),self.tabs)
        self.mixer.project_dir=(Path(self.main.project_dir).resolve()
                               if self.main.project_dir else None)
        # Nuevo proyecto puede heredar el ajuste completo del mezclador
        # antes de que existan pistas o se construya su interfaz.
        pending=getattr(self.main,"_pending_mixer_preset",None)
        if isinstance(pending,dict):
            self.mixer.apply_preset(pending)
        placeholder=getattr(self.main,"mixer_placeholder",None)
        if placeholder is not None and self.tabs.indexOf(placeholder)>=0:
            self.tabs.removeTab(self.tabs.indexOf(placeholder))
        index=self.tabs.insertTab(self.tabs.indexOf(self.piano),self.mixer,"Mezclador")
        from PySide6.QtGui import QIcon
        self.tabs.setTabIcon(index,QIcon(str(Path(__file__).resolve().parent/"assets"/"ui_mixer.svg")))
        self.tabs.setCurrentWidget(self.mixer)

    def open_saved_library(self,kind):
        # La pestaña Resultados muestra exclusivamente el proyecto actual.
        home=getattr(self.main,"studio_home",None)
        if home:home.refresh(force=True)
        results=getattr(self.main,"results_tab",None)
        if results is not None:self.tabs.setCurrentWidget(results)

    def pending_notice(self):
        pending=[kind for kind,store in (("separaciones",self.separation_storage),
                                        ("midi",self.midi_storage),
                                        ("bateria",self.drum_storage),
                                        ("vocal",self.vocal_storage)) if store.pending]
        if pending:
            return ("Las tareas temporales sin guardar se conservarán en Recuperación "
                    "para revisarlas cuando vuelvas a abrir el programa.")
        return None
