"""Distribución final del panel según las fotografías del 06/11/2026.

REUTILIZA los botones y el registro originales, nunca deja dos modelos IA,
ni procesos de separación duplicados. Se aplica después del layout boceto.
"""
from __future__ import annotations
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QGridLayout,QHBoxLayout,QLabel,QPushButton,
                               QSizePolicy,QWidget)


def _remove_from_layout(layout,target):
    for i in range(layout.count()):
        it=layout.itemAt(i)
        if it.widget() is target:
            layout.removeWidget(target)
            return True
        sub=it.layout()
        if sub is None and it.widget() is not None:
            sub=it.widget().layout()
        if sub is not None and _remove_from_layout(sub,target):return True
    return False


def install(main):
    sep=main.workbench.separator
    board=sep._dashboard_board
    entry,selection,preview,run,tools,activity=sep._dashboard_cards

    # En la barra de presets están los tres botones reales, con las
    # mismas señales del historial. No crear otro historial ni otro Reset.
    history=sep.settings_history
    undo,redo=history.undo_button,history.redo_button
    reset=next(b for b in tools.findChildren(QPushButton) if b.text()=='Reset')
    p=sep.presets
    row=p.layout()
    for button in (undo,redo,reset):
        assert _remove_from_layout(tools.body,button)
        button.setMinimumHeight(25)
        button.setMaximumHeight(27)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
    undo.setText('↶')
    undo.setToolTip('Deshacer el último ajuste')
    redo.setText('↷')
    redo.setToolTip('Rehacer el ajuste deshecho')
    undo.setFixedWidth(29)
    redo.setFixedWidth(29)
    reset.setFixedWidth(44)
    row.setContentsMargins(0,0,0,0)
    row.setSpacing(2)
    p.choices.setMinimumWidth(62)
    p.choices.setMaximumWidth(102)
    p.choices.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    p.name.setMinimumWidth(43)
    p.name.setMaximumWidth(75)
    p.name.setToolTip('Nombre del preset personalizado')
    p.name.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    for button,low,high in ((p.save_btn,46,57),(p.delete_btn,42,51)):
        button.setMinimumWidth(low)
        button.setMaximumWidth(high)
        button.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        button.setMinimumHeight(25)
    def attach_history():
        # Las reparaciones responsivas anteriores podían recolocarlos de
        # nuevo dentro de la tarjeta oculta. Fijar la propiedad del widget.
        for button in (undo,redo,reset):
            _remove_from_layout(tools.body,button)
            button.setParent(p)
            if row.indexOf(button)<0:
                row.insertWidget(row.count()-1,button)
            button.show()
        for widget,width in ((p.choices,76),(p.name,50),
                             (p.save_btn,69),(p.delete_btn,58),
                             (undo,29),(redo,29),(reset,55)):
            widget.setFixedWidth(width)
        p.message.hide()
    attach_history()
    QTimer.singleShot(250,attach_history)
    QTimer.singleShot(850,attach_history)
    p.message.hide()
    for widget in (p.choices,p.name,p.save_btn,p.delete_btn,undo,redo,reset):
        widget.show()

    # Solo UN selector de modelo IA. El desplegable duplicado de «04 ·
    # Procesar audio» permanece conectado internamente pero oculto.
    for widget in (sep.model_run_selector,sep.model_run_import):
        _remove_from_layout(run.body,widget)
        widget.hide()
    sep.model_run_selector.setMinimumWidth(0)

    frame=sep._setup_frame
    setup=frame.layout()
    # El botón de modelos se traslada desde la columna del formulario.
    assert _remove_from_layout(setup,sep.manage_models_btn)
    sep.profile.setMinimumWidth(0)
    setup.removeWidget(sep.profile)
    setup.addWidget(sep.profile,1,1,1,4)
    sep.manage_models_btn.setText('Cargar IA…')
    sep.manage_models_btn.setToolTip(
        'Instalar y activar un modelo de separación. El selector está arriba.')

    # Los botones Separar y Cancelar son los originales (mismo motor).
    assert _remove_from_layout(run.body,sep.go)
    assert _remove_from_layout(run.body,sep.cancel_button)
    action_line=QHBoxLayout()
    action_line.setSpacing(5)
    action_line.setContentsMargins(1,0,1,0)
    for button in (sep.go,sep.cancel_button,sep.manage_models_btn):
        button.setMaximumWidth(16777215)
        button.setMinimumWidth(0)
        button.setMinimumHeight(29)
        button.setMaximumHeight(31)
        button.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        action_line.addWidget(button,1)
        button.show()
    entry.body.addLayout(action_line)
    sep._entry_action_line=action_line

    # Registro técnico real en la ubicación antes ocupada por PROCESAR.
    # Se quitan las dos tarjetas redundantes de la rejilla; el panel de
    # historial desaparece por completo, no solo su texto de cabecera.
    activity.heading.setText('04 · REGISTRO DEL MOTOR')
    activity.body.setContentsMargins(7,4,7,5)
    activity.body.setSpacing(2)
    activity.setMinimumHeight(145)
    activity.setMaximumHeight(210)
    activity.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    sep.activity_info['log'].setMinimumHeight(48)
    sep.activity_info['log'].setMaximumHeight(90)
    sep.activity_info['open'].setMaximumHeight(25)
    for old in (run,tools):
        board.removeWidget(old)
        old.setVisible(False)
    run.setParent(sep._compact_canvas)
    tools.setParent(sep._compact_canvas)

    # El dashboard anterior programaba un refresco al redimensionar;
    # sustituimos SU función para impedir que recupere las tarjetas antiguas.
    original_responsive=sep._adaptive_dashboard
    original_responsive.mode=None
    def arrange():
        import shiboken6
        if not shiboken6.isValid(sep):return
        narrow=sep.width()<755
        for card in (entry,selection,preview,activity):
            board.removeWidget(card)
        if narrow:
            board.addWidget(entry,0,0,1,2)
            board.addWidget(selection,1,0,1,2)
            board.addWidget(preview,2,0,1,2)
            board.addWidget(activity,3,0,1,2)
            board.setColumnStretch(0,1)
            board.setColumnStretch(1,0)
        else:
            board.addWidget(entry,0,0)
            board.addWidget(selection,0,1)
            board.addWidget(preview,1,0)
            board.addWidget(activity,1,1)
            board.setColumnStretch(0,54)
            board.setColumnStretch(1,46)
        for i in range(4):board.setRowStretch(i,0)
        entry.setMinimumHeight(0)
        entry.setMaximumHeight(16777215)
        selection.setMinimumHeight(165 if not narrow else 110)
        preview.setMinimumHeight(145)
        activity.setMinimumHeight(145)
        activity.show()
        entry.show();selection.show();preview.show()
        run.hide();tools.hide()
        sep._compact_canvas.setMinimumHeight(0)
        board.invalidate()
    original_responsive.update=arrange
    sep._final_reflow=arrange
    sep._dashboard_main_cards=(entry,selection,preview,activity)
    QTimer.singleShot(0,arrange)
    QTimer.singleShot(150,arrange)
    return True
