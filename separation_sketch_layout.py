"""Revisión de stems según boceto de usuario (noviembre 2026).

Reutiliza los controles de escucha/selección y su motor PCM real, no duplica
reproductores ni modifica audios. Ajusta la geometría de ambas columnas.
"""
from __future__ import annotations
import math

from PySide6.QtCore import Qt, QEvent, QObject, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget
)


class SelectAllStems(QCheckBox):
    """Dos estados al pulsar; el estado parcial es solo informativo."""
    def nextCheckState(self):
        self.setCheckState(Qt.Unchecked if self.checkState()==Qt.Checked
                           else Qt.Checked)


class VerticalMasterVU(QWidget):
    """Dos vúmetros verticales, alimentados por los picos PCM del máster."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.levels=(0., 0.)
        self.setFixedWidth(64)
        # Ocupa verticalmente la escucha + el progreso del motor; aprox.
        # el doble de alto y anclado arriba, sin desplazar las acciones.
        self.setMinimumHeight(235)
        self.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        self.setToolTip("VU general estéreo: niveles reales de la mezcla reproducida")

    def set_levels(self, left, right):
        levels=(min(1.,max(0.,float(left))),min(1.,max(0.,float(right))))
        if levels!=self.levels:
            self.levels=levels
            self.update()

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor("#061633"))
        p.setPen(QColor("#e4f8ff"))
        p.drawText(0,4,self.width(),18,Qt.AlignCenter,"VU")
        top=26
        bottom=max(top+24,self.height()-23)
        height=bottom-top
        for i,level in enumerate(self.levels):
            x=9+i*28
            p.fillRect(x,top,18,height,QColor("#102d49"))
            p.setPen(QPen(QColor("#47738a"),1))
            p.drawRect(x,top,18,height)
            db=20*math.log10(max(level,1e-9))
            proportion=max(0.,min(1.,(db+60)/60))
            fill_h=int(height*proportion)
            if fill_h:
                col=QColor("#22d9b2") if db<-12 else (
                    QColor("#efc344") if db<-3 else QColor("#fc6d61"))
                p.fillRect(x+2,bottom-fill_h+1,15,max(1,fill_h-2),col)
            p.setPen(QColor("#dcefff"))
            p.drawText(x,bottom+3,18,18,Qt.AlignCenter,"L" if i==0 else "R")
        p.end()


def _release_layout(layout):
    """Desconectar controles antiguos sin destruirlos ni desconectar señales."""
    while layout.count():
        item=layout.takeAt(0)
        widget=item.widget()
        if widget is not None:
            widget.hide()
        elif item.layout() is not None:
            _release_layout(item.layout())


def _sketch_transport(main, panel, player):
    """Una fila Play/Pausa/Stop/progreso y otra de controles compactos."""
    from separation_review_ui import dark_combo_popup
    old_responsive=getattr(player,"_reflow_responsive",None)
    if old_responsive is not None:
        # Una actualización diferida del layout anterior restablecía los
        # anchos de Play/Stop y deshacía la compacidad del transporte.
        old_responsive.refresh=lambda:None
    outer=player.layout()
    _release_layout(outer)
    outer.setContentsMargins(7,5,7,5)
    outer.setSpacing(5)
    for widget in (player.filename,player.detail,player.options_button,
                   player.status,player._measured_vu.meter):
        widget.hide()
    play=player.play_button
    play.setText("▶")
    play.setToolTip("Reproducir las pistas marcadas")
    play.setFixedWidth(39)
    stop=player.stop_button
    stop.setText("■")
    stop.setToolTip("Detener y volver al comienzo")
    stop.setFixedWidth(39)
    pause=QPushButton("Ⅱ",player)
    pause.setToolTip("Pausar o continuar la escucha multipista")
    pause.setFixedWidth(39)
    pause.clicked.connect(lambda:main.studio_home._sep_listen.pause())
    player._sketch_pause=pause
    player._sketch_meter=VerticalMasterVU(panel)
    row=QHBoxLayout()
    row.setContentsMargins(0,0,0,0)
    row.setSpacing(5)
    for widget in (play,pause,stop):
        row.addWidget(widget)
    player.slider.setMinimumWidth(45)
    player.slider.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    row.addWidget(player.slider,1)
    player.clock.setMinimumWidth(81)
    player.clock.setMaximumWidth(95)
    row.addWidget(player.clock)
    outer.addLayout(row)
    settings=QHBoxLayout()
    settings.setContentsMargins(0,0,0,0)
    settings.setSpacing(0)
    # Tres grupos contiguos etiqueta/control. El espacio se reserva ENTRE
    # grupos, nunca dentro de la pareja; la salida queda a la izquierda.
    def paired(label,widget):
        pair=QHBoxLayout()
        pair.setContentsMargins(0,0,0,0)
        pair.setSpacing(4)
        # QLabel Preferred absorbe todo el espacio extra y separa
        # visualmente «Salida» de su selector. Ajustarlo al texto REAL.
        label.setFixedWidth(label.fontMetrics().horizontalAdvance(label.text())+5)
        label.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        pair.addWidget(label,0)
        pair.addWidget(widget,1 if widget is player.device_choice else 0)
        return pair
    player.volume_label.setText("Vol.")
    player.volume.setMinimumWidth(55)
    player.volume.setMaximumWidth(75)
    settings.addLayout(paired(player.volume_label,player.volume))
    settings.addSpacing(13)
    player.speed_label.setText("Vel.")
    player.speed.setMinimumWidth(65)
    player.speed.setMaximumWidth(73)
    settings.addLayout(paired(player.speed_label,player.speed))
    settings.addSpacing(13)
    player.route_label.setText("Salida")
    player.device_choice.setMinimumWidth(102)
    player.device_choice.setMaximumWidth(280)
    player.device_choice.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    pair=paired(player.route_label,player.device_choice)
    settings.addLayout(pair,1)
    dark_combo_popup(player.device_choice)
    dark_combo_popup(player.speed)
    outer.addLayout(settings)
    player._sketch_settings_row=settings
    for widget in (play,pause,stop,player.slider,player.clock,
                   player.volume_label,player.volume,player.speed_label,player.speed,
                   player.route_label,player.device_choice):
        widget.show()
    def force_compact_buttons():
        for button in (play,pause,stop):
            button.setMinimumWidth(39)
            button.setMaximumWidth(39)
            button.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        play.setText("▶")
        stop.setText("■")
    # El sistema anterior había dejado un singleShot que recuperaba
    # los mínimos de 100/85px después de reconstruir el transporte.
    QTimer.singleShot(0,force_compact_buttons)
    QTimer.singleShot(250,force_compact_buttons)
    player.setMinimumHeight(81)
    player.setMaximumHeight(95)
    player.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)


def _progress_rearrange(sep):
    """Seis instrumentos en columna, como en el boceto, con el progreso real."""
    info=sep.activity_info
    box=info["box"]
    out=box.layout()
    grid=next((out.itemAt(i).layout() for i in range(out.count())
               if isinstance(out.itemAt(i).layout(),QGridLayout)),None)
    if grid is None:
        raise RuntimeError("No se ha encontrado la rejilla de progreso real")
    for name in info["bars"]:
        grid.removeWidget(info["labels"][name])
        grid.removeWidget(info["bars"][name])
    names=("Voz","Bajo","Piano","Batería","Guitarra","Otros")
    for row,name in enumerate(names):
        lab=info["labels"][name]
        bar=info["bars"][name]
        lab.setMinimumWidth(58)
        lab.setMaximumWidth(74)
        bar.setMinimumWidth(90)
        bar.setFixedHeight(16)
        grid.addWidget(lab,row,0)
        grid.addWidget(bar,row,1)
    grid.setColumnStretch(0,0)
    grid.setColumnStretch(1,1)
    grid.setColumnStretch(2,0)
    grid.setColumnStretch(3,0)
    grid.setHorizontalSpacing(6)
    grid.setVerticalSpacing(2)
    out.setContentsMargins(7,5,7,5)
    out.setSpacing(2)
    box.setMinimumHeight(161)
    box.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    return box


def _column_safe(main):
    """El panel derecho nunca invade el formulario izquierdo."""
    from PySide6.QtWidgets import QSplitter
    splitter=main.workbench.separation_tab
    sep=main.workbench.separator
    panel=main.workbench.sep_results
    wrapper=splitter.widget(1)
    for widget in (sep,panel,wrapper):
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    # Compactar el PRESET real; su mínimo de 447 px forzaba la segunda
    # tarjeta fuera de pantalla en monitores de 1366/1408 px.
    presets=sep.presets
    presets.layout().setContentsMargins(2,2,2,2)
    presets.layout().setSpacing(4)
    # El título del desplegable ya dice «Elegir preset». Una segunda
    # etiqueta PRESET robaba el ancho necesario para las cuatro acciones.
    for label in presets.findChildren(QLabel):
        if label.text()=="PRESET":label.hide()
    presets.choices.setFixedWidth(96)
    presets.choices.setToolTip("Selecciona un preset; el nombre completo aparece en el desplegable")
    presets.name.setFixedWidth(70)
    presets.save_btn.setFixedWidth(64)
    presets.delete_btn.setFixedWidth(60)
    sep._selection_card.setMinimumWidth(0)
    # El valor de calidad no debe quedar reducido a «Norm»; reservar
    # anchura suficiente para mostrar claramente Normal / Alta / Máxima.
    # Dar una fila completa a Calidad y otra a Formato: apretados en
    # una sola fila, ambos valores aparecían cortados en monitores de 1408.
    frame=sep._setup_frame
    form=frame.layout()
    labels={label.text():label for label in frame.findChildren(QLabel)}
    if all(key in labels for key in ("Calidad","Formato","Destino")):
        quality_label=labels["Calidad"]
        format_label=labels["Formato"]
        destination_label=labels["Destino"]
        folder_button=next((button for button in frame.findChildren(QPushButton)
                             if button.text().startswith("Carpeta")),None)
        if folder_button is not None:
            for widget in (quality_label,sep.quality,format_label,
                           sep.export_fmt,destination_label,sep.dest_edit,
                           folder_button):
                form.removeWidget(widget)
            form.addWidget(quality_label,2,0)
            form.addWidget(sep.quality,2,1,1,4)
            form.addWidget(format_label,3,0)
            form.addWidget(sep.export_fmt,3,1,1,4)
            form.addWidget(destination_label,4,0)
            form.addWidget(sep.dest_edit,4,1,1,3)
            form.addWidget(folder_button,4,4)
            frame.setMinimumHeight(198)
            frame.setMaximumHeight(218)
    sep.model_run_selector.setMinimumWidth(0)
    sep.model_run_selector.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    # Un combo con textos de 70 caracteres no puede imponer sus 360 px
    # como anchura mínima; el nombre íntegro sigue visible al desplegar.
    from PySide6.QtWidgets import QComboBox
    sep.model_run_selector.setSizeAdjustPolicy(
        QComboBox.AdjustToMinimumContentsLengthWithIcon)
    sep.model_run_selector.setMinimumContentsLength(6)
    for label in sep._dashboard_cards[3].findChildren(QLabel):
        if label.text().startswith("Modelo IA:"):
            label.setMinimumWidth(0)
            label.setWordWrap(True)
            label.setMaximumHeight(35)
            label.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
    sep.model_run_import.setMinimumWidth(70)
    sep.model_run_import.setMaximumWidth(91)
    sep.model_run_import.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
    # No pedir 880 px en la columna izquierda: a ~770 px caben dos
    # tarjetas de ~370 px si los combos no conservan mínimos invisibles.
    responsive=sep._adaptive_dashboard
    # Este umbral decide cuándo usar una sola columna con scroll propio.
    # Las tarjetas nunca pueden dibujarse sobre el panel derecho.
    orig_update=responsive.update
    # La función preexistente usa 880; elegimos modo amplio sólo si se
    # verifica geométricamente que caben todas las tarjetas compactas.
    # Para prevenir invasión, mantenemos el diseño a una columna cuando
    # el espacio es inferior a 880.
    sep._setup_frame.setMinimumWidth(0)
    splitter.setChildrenCollapsible(False)
    splitter.setStretchFactor(0,58)
    splitter.setStretchFactor(1,42)
    ratio=getattr(sep,"_splitter_ratio_keeper",None)
    if ratio is not None:
        def fit_ratio():
            usable=max(0,splitter.width()-splitter.handleWidth())
            if usable<2:return
            left=max(0,round(usable*.58))
            splitter.setSizes([left,usable-left])
        ratio.update=fit_ratio
    splitter.setSizes([770,560])
    QTimer.singleShot(0,lambda:ratio.update() if ratio else None)


def install(main):
    """Montar la revisión siguiendo el boceto, después de crear el botón aprobar."""
    from PySide6.QtWidgets import QScrollArea
    from project_flow import approve_separation
    panel=main.workbench.sep_results
    sep=main.workbench.separator
    content=panel._review_content
    layout=content.layout()
    area=panel._review_list_area
    player=panel.preview
    progress=_progress_rearrange(sep)
    _sketch_transport(main,panel,player)

    # El QScrollArea anterior imponía 690 px de altura: en pantallas de
    # portátil ocultaba el transporte y apretaba dos columnas hasta solaparlas.
    content.setMinimumHeight(0)
    content.setMinimumWidth(0)
    panel._review_outer_scroll.setMinimumWidth(0)
    panel._review_outer_scroll.setWidgetResizable(True)
    _release_layout(layout)
    layout.setContentsMargins(7,5,7,6)
    layout.setSpacing(5)

    all_box=SelectAllStems("Marcar / desmarcar todas",content)
    all_box.setTristate(True)
    all_box.setToolTip("Marcar o desmarcar todos los stems; la selección también determina qué se escucha")
    all_box.setStyleSheet("font-size:13px;font-weight:700;color:#e4f8ff;")
    layout.addWidget(all_box)
    panel._sketch_all_checkbox=all_box

    area.setMinimumHeight(110)
    area.setMaximumHeight(16777215)
    area.setMinimumWidth(0)
    area.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    panel.container.setMinimumWidth(0)
    panel.rows.setContentsMargins(2,2,2,2)
    panel.rows.setSpacing(3)
    layout.addWidget(area,1)

    # Vúmetros a la DERECHA y desde la altura de Play hasta el pie del
    # progreso: doble longitud sin hacer más larga la pantalla de Resultados.
    meters=QHBoxLayout()
    meters.setContentsMargins(0,0,0,0)
    meters.setSpacing(7)
    playback_and_progress=QVBoxLayout()
    playback_and_progress.setContentsMargins(0,0,0,0)
    playback_and_progress.setSpacing(5)
    playback_and_progress.addWidget(player,0)
    playback_and_progress.addWidget(progress,0)
    meters.addLayout(playback_and_progress,1)
    meters.addWidget(player._sketch_meter,0)
    layout.addLayout(meters)
    player._sketch_meter_group=meters

    # Solo dos acciones abajo. Se conservan las conexiones originales
    # de eliminación y exportación; al guardar se realiza la distribución
    # que antes exigía un tercer botón de aprobación.
    actions=QHBoxLayout()
    actions.setContentsMargins(0,0,0,0)
    actions.setSpacing(7)
    delete=panel.remove_selected_btn
    delete.setText("Eliminar marcados")
    delete.setToolTip("Eliminar solo los stems temporales marcados, previa confirmación")
    save=panel.save_selected
    save.setText("Guardar marcados")
    save.setObjectName("primary")
    save.setToolTip("Guardar las pistas marcadas y, en un proyecto activo, distribuirlas a sus módulos")
    for btn in (delete,save):
        btn.setMinimumWidth(0)
        btn.setMinimumHeight(30)
        btn.setMaximumWidth(16777215)
        btn.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        actions.addWidget(btn,1)
    layout.addLayout(actions)
    for widget in (panel.save_all,panel.new_task,panel.mark_all_btn,
                   panel.mark_none_btn,panel.pitch_btn,panel.approve_button,
                   panel.status,panel.path_label):
        widget.hide()
    # Los widgets que se han trasladado a layouts nuevos ya están visibles.
    for widget in (area,player,progress,delete,save):
        widget.show()

    def save_marked_and_distribute():
        copied=panel.save_files(False)
        if copied and getattr(main,"project_dir",None):
            approve_separation(main,quiet=True)
    try:save.clicked.disconnect()
    except RuntimeError:pass
    save.clicked.connect(save_marked_and_distribute)

    def refresh_selection():
        lines=list(panel.lines)
        all_box.setEnabled(bool(lines))
        if not lines:
            state=Qt.Unchecked
        else:
            checked=sum(line.checked.isChecked() for line in lines)
            state=(Qt.Checked if checked==len(lines) else
                   Qt.Unchecked if checked==0 else Qt.PartiallyChecked)
        blocked=all_box.blockSignals(True)
        all_box.setCheckState(state)
        all_box.blockSignals(blocked)
    panel._refresh_sketch_selection=refresh_selection

    def apply_all(state):
        checked=state==Qt.Checked
        for line in list(panel.lines):
            line.checked.setChecked(checked)
        refresh_selection()
    all_box.checkStateChanged.connect(apply_all)
    for line in panel.lines:
        line.checked.toggled.connect(refresh_selection)
    refresh_selection()

    _column_safe(main)
    panel._sketch_layout_installed=True
    return True
