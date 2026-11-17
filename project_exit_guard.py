"""Confirmación de salida de StemMIDI Studio.

No hace limpieza, no altera fuentes ni destruye la sesión: devuelve True
únicamente después de una decisión inequívoca del usuario y de que
Guardar / Guardar como hayan terminado correctamente.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox


def ask_exit_choice(main):
    name=str(getattr(main,"project_name",None) or "Sin nombre")
    dialog=QMessageBox(main)
    dialog.setObjectName("stemExitConfirmation")
    dialog.setIcon(QMessageBox.Warning)
    dialog.setWindowTitle("Salir de StemMIDI Studio")
    dialog.setText("¿Quieres guardar el trabajo antes de salir?")
    dialog.setInformativeText(
        f"Proyecto actual: {name}\n\n"
        "Guardar: actualiza el proyecto.\n"
        "Guardar como…: crea otra copia con nombre y ubicación propios.\n"
        "Salir sin guardar: descarta los cambios no guardados.\n"
        "Cancelar: vuelve al programa sin perder lo que estás haciendo."
    )
    dialog.setStandardButtons(QMessageBox.NoButton)
    save=dialog.addButton("Guardar",QMessageBox.AcceptRole)
    save.setObjectName("stemExitSave")
    save_as=dialog.addButton("Guardar como…",QMessageBox.ActionRole)
    save_as.setObjectName("stemExitSaveAs")
    discard=dialog.addButton("Salir sin guardar",QMessageBox.DestructiveRole)
    discard.setObjectName("stemExitDiscard")
    cancel=dialog.addButton("Cancelar",QMessageBox.RejectRole)
    cancel.setObjectName("stemExitCancel")
    dialog.setDefaultButton(cancel)
    dialog.setEscapeButton(cancel)
    dialog.exec()
    # PySide6 puede devolver un envoltorio Python distinto para el mismo
    # QPushButton: las comparaciones «is» devuelven False aunque se haya
    # pulsado correctamente. Usar el objectName estable de cada botón.
    chosen=dialog.clickedButton()
    action=chosen.objectName() if chosen is not None else ""
    if action=="stemExitSave":return "save"
    if action=="stemExitSaveAs":return "save_as"
    if action=="stemExitDiscard":return "discard"
    return "cancel"


def confirm_exit(main):
    """True autoriza el cierre; False mantiene vivos todos los controles."""
    decision=ask_exit_choice(main)
    main._exit_decision=decision
    if decision=="cancel":return False
    if decision=="discard":return True

    if not getattr(main,"project_dir",None):
        QMessageBox.warning(
            main,"Proyecto sin nombre",
            "No hay un proyecto con nombre y carpeta para guardar.\n"
            "Crea o abre primero un proyecto desde Inicio. "
            "El programa permanecerá abierto para no perder tu trabajo.")
        return False

    # El editor de Piano Roll integrado se materializa al guardar proyecto.
    # Las ventanas auxiliares de edición MIDI mantienen copias en memoria:
    # no se pueden declarar guardadas sin solicitar antes su propio archivo.
    from piano_roll import PianoRollDialog
    dirty=[dlg for dlg in main.findChildren(PianoRollDialog)
           if dlg.dirty and dlg is not main.workbench.piano]
    if dirty:
        editor=dirty[0]
        editor.show()
        editor.raise_()
        editor.activateWindow()
        QMessageBox.warning(main,"Edición MIDI pendiente",
            "Hay notas modificadas en una ventana de Piano Roll independiente. "
            "Guarda esas notas desde su editor antes de guardar el proyecto. "
            "No se cerrará el programa.")
        return False

    from studio_shell import save_project,save_project_as
    try:
        if decision=="save":
            return bool(save_project(main,show_confirmation=False))
        if decision=="save_as":
            success=bool(save_project_as(main,show_confirmation=False))
            # Guardar como confirma la copia nueva, no la sesión original.
            # Al cerrar, se descartan los cambios originales, sin publicarlos.
            if success:main._exit_decision="discard"
            return success
    except Exception as error:
        QMessageBox.warning(main,"No se pudo guardar el proyecto",
                            str(error)+"\nStemMIDI Studio permanecerá abierto.")
    return False
