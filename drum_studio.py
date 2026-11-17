"""Estudio de batería: ondas reales, mixer, edición no destructiva y MIDI.

Nada se escucha o aparece como resultado separado sin ficheros generados
por el modelo real. Los patrones MIDI son notas creadas por el usuario/preset.
"""
from __future__ import annotations

import math,re,subprocess
from pathlib import Path
from PySide6.QtCore import Qt,QProcess,QTimer,Signal,QRectF
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import (
    QWidget,QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,QScrollArea,QLabel,
    QPushButton,QComboBox,QCheckBox,QTabWidget,QSlider,QGroupBox,QMessageBox,QSizePolicy
)
from studio_slider_spin import StudioSliderSpin
from ux_controls import PresetStrip
from studio_home import WaveCanvas
from drum_mixer_console import ConsoleStrip,ChannelInspector
import file_dialogs

PARTS=("Bombo","Caja","Toms","Charles","Ride","Crash")
GM={"Bombo":36,"Caja":38,"Toms":45,"Charles":42,"Ride":51,"Crash":49}
COLORS={"Bombo":"#3baff6","Caja":"#fb8a74","Toms":"#c29af5",
        "Charles":"#f3ca69","Ride":"#6cdbb9","Crash":"#eb90c3"}

def _is_real(p):
    return p is not None and Path(p).is_file()

def _ffmpeg_command():
    import shutil
    return shutil.which("ffmpeg")

def _ffprobe_duration(path):
    result=subprocess.run(["ffprobe","-v","error","-show_entries",
        "format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],
        capture_output=True,text=True,timeout=9)
    if result.returncode!=0:raise ValueError("No se pudo leer la duración")
    return max(0.,float(result.stdout.strip()))

class DrumEditWave(WaveCanvas):
    """Editor de región: arrastra sobre la onda para delimitar el recorte."""
    rangeChanged=Signal(float,float)
    def __init__(self,parent=None):
        super().__init__(small=False,parent=parent)
        self.setMouseTracking(True)
        self.anchor=None
        self.selected=None
        self.setToolTip("Arrastra sobre la forma de onda para seleccionar "
                        "un intervalo. Los deslizantes de Inicio y Final se sincronizan.")

    def _fraction(self,event):
        value=max(0.,min(1.,event.position().x()/max(1,self.width())))
        return max(0.,min(1.,self.view_start+value/self.zoom_factor))

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.data:
            self.anchor=self._fraction(event)
            self.selected=(self.anchor,self.anchor)
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.anchor is not None:
            fraction=self._fraction(event)
            self.selected=(min(fraction,self.anchor),max(fraction,self.anchor))
            self.update()
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.anchor is not None:
            point=self._fraction(event)
            begin=min(self.anchor,point)
            end=max(self.anchor,point)
            self.anchor=None
            if end-begin>=.002:
                self.selected=(begin,end)
                self.rangeChanged.emit(begin,end)
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.selected or not self.data:return
        a,b=self.selected
        start=(a-self.view_start)*self.zoom_factor*self.width()
        width=(b-a)*self.zoom_factor*self.width()
        painter=QPainter(self)
        painter.fillRect(QRectF(start,0,width,self.height()),QColor(12,181,252,44))
        painter.setPen(QPen(QColor("#6ae9ff"),2))
        painter.drawLine(int(start),0,int(start),self.height())
        painter.drawLine(int(start+width),0,int(start+width),self.height())
        painter.end()

class ChannelRow(QFrame):
    """Control por instrumento para tabla de pistas o mesa de mezcla."""
    def __init__(self,part,studio,vertical=False):
        super().__init__(studio)
        self.part=part
        self.studio=studio
        self.vertical=vertical
        self.setObjectName("drumChannel")
        self.setStyleSheet(
            "QFrame#drumChannel {background:#041b44;border:1px solid #2bb1fc;"
            "border-radius:5px;} QFrame#drumChannel QLabel {border:0;}"
        )
        if vertical:
            layout=QVBoxLayout(self)
            layout.setContentsMargins(7,8,7,7)
            layout.setSpacing(5)
            title=QLabel(part)
            title.setStyleSheet(f"color:{COLORS[part]};font-weight:800;")
            title.setAlignment(Qt.AlignCenter)
            layout.addWidget(title)
        else:
            layout=QHBoxLayout(self)
            layout.setContentsMargins(7,3,7,3)
            layout.setSpacing(8)
            title=QLabel(part)
            title.setMinimumWidth(67)
            title.setStyleSheet(f"color:{COLORS[part]};font-weight:800;")
            layout.addWidget(title)
        self.wave=WaveCanvas(small=True,parent=self)
        self.wave.setMinimumHeight(33)
        self.wave.setMaximumHeight(49 if vertical else 48)
        self.wave.clicked.connect(lambda _:self.studio.listen(self.part))
        layout.addWidget(self.wave,0 if vertical else 1)
        if vertical:
            self.fader=QSlider(Qt.Vertical,self)
            self.fader.setRange(-36,12)
            self.fader.setValue(0)
            self.fader.setMinimumHeight(112)
            self.fader.setMaximumHeight(180)
            self.fader.valueChanged.connect(lambda n:self.studio.set_state(self.part,"gain",n))
            layout.addWidget(self.fader,1,Qt.AlignHCenter)
            self.gain_value=QLabel("0 dB")
            self.gain_value.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.gain_value)
        else:
            self.gain=StudioSliderSpin(-36,12,0,"dB",self,width=170)
            self.gain.valueChanged.connect(lambda n:self.studio.set_state(self.part,"gain",n))
            layout.addWidget(self.gain)
        self.pan=StudioSliderSpin(-100,100,0,"",self,width=150 if vertical else 170)
        self.pan.setToolTip("Panorama L/R: -100 izquierda, 0 centro, +100 derecha.")
        self.pan.valueChanged.connect(lambda n:self.studio.set_state(self.part,"pan",n))
        layout.addWidget(self.pan)
        controls=QHBoxLayout()
        controls.setSpacing(4)
        self.mute=QPushButton("M",self)
        self.mute.setCheckable(True)
        self.mute.setToolTip("Mute: silencia esta pista en la mezcla")
        self.mute.toggled.connect(lambda value:self.studio.set_state(self.part,"mute",value))
        self.solo=QPushButton("S",self)
        self.solo.setCheckable(True)
        self.solo.setToolTip("Solo: escuchar únicamente las pistas marcadas")
        self.solo.toggled.connect(lambda value:self.studio.set_state(self.part,"solo",value))
        self.play=QPushButton("▶",self)
        self.play.setToolTip("Escuchar únicamente esta pista")
        self.play.clicked.connect(lambda:self.studio.listen(self.part))
        for button in (self.mute,self.solo,self.play):
            button.setMaximumWidth(50)
            controls.addWidget(button)
        if vertical:
            layout.addLayout(controls)
        else:
            layout.addLayout(controls)
        self.all_controls=[self.pan,self.mute,self.solo,self.play]+(
            [self.fader] if vertical else [self.gain])

    def update_state(self,state,path):
        self.wave.set_file(path if _is_real(path) else None)
        loaded=_is_real(path)
        for widget in self.all_controls:widget.setEnabled(loaded)
        value=state["gain"]
        if self.vertical:
            if self.fader.value()!=value:
                blocked=self.fader.blockSignals(True);self.fader.setValue(value);self.fader.blockSignals(blocked)
            self.gain_value.setText(f"{value:+d} dB" if value else "0 dB")
        else:
            if self.gain.value()!=value:
                blocked=self.gain.blockSignals(True);self.gain.setValue(value);self.gain.blockSignals(blocked)
        if self.pan.value()!=state["pan"]:
            blocked=self.pan.blockSignals(True);self.pan.setValue(state["pan"]);self.pan.blockSignals(blocked)
        for widget,name in ((self.mute,"mute"),(self.solo,"solo")):
            if widget.isChecked()!=state[name]:
                flag=widget.blockSignals(True)
                widget.setChecked(state[name])
                widget.blockSignals(flag)
            widget.setStyleSheet(
                "background:#a04c43;color:white;font-weight:bold;" if
                widget is self.mute and widget.isChecked() else
                "background:#0d59e0;color:white;font-weight:bold;" if
                widget is self.solo and widget.isChecked() else "")

class DrumStudio(QTabWidget):
    def __init__(self,drum):
        super().__init__(drum)
        self.drum=drum
        self.setObjectName("drumStudio")
        self.channels={
            part:{"gain":0,"pan":0,"mute":False,"solo":False,
                  "eq_low":0,"eq_mid":0,"eq_high":0}
            for part in PARTS}
        self.sources={part:None for part in PARTS}
        self.rows=[]
        self.process=None
        self.output_path=None
        self.output_operation=None
        self.selected_part="Bombo"
        self._build_tracks()
        self._build_mixer()
        self._build_editor()
        self._build_sequencer()
        self._build_results()
        self._compose_dashboard()

    def _compose_dashboard(self):
        """Una sola vista continua: las cinco herramientas siempre montadas.

        Conserva widgets/controladores originales para no duplicar estados
        ni romper exportación, modelos, presets o archivos del proyecto.
        """
        names=("ONDAS · 6 INSTRUMENTOS","MEZCLADOR · 6 CANALES",
               "EDITOR DE AUDIO","SECUENCIADOR MIDI","RESULTADOS")
        self.dashboard_sections={}
        original=[self.widget(i) for i in range(self.count())]
        assert len(original)==5
        for i in reversed(range(self.count())):
            self.removeTab(i)
        self.dashboard=QWidget(self)
        top=QVBoxLayout(self.dashboard)
        top.setContentsMargins(0,0,0,0)
        top.setSpacing(0)
        self.dashboard_scroll=QScrollArea(self.dashboard)
        self.dashboard_scroll.setObjectName("drumDashboardScroll")
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.dashboard_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.dashboard_scroll.setFrameShape(QFrame.NoFrame)
        top.addWidget(self.dashboard_scroll,1)
        content=QWidget()
        content.setObjectName("drumDashboardContents")
        content.setStyleSheet(
            "QWidget#drumDashboardContents {background:#04183c;}")
        grid=QGridLayout(content)
        grid.setContentsMargins(4,3,4,6)
        grid.setHorizontalSpacing(9)
        grid.setVerticalSpacing(9)

        def section(index,row,column,column_span=1):
            frame=QFrame(content)
            frame.setObjectName("drumDashboardSection")
            frame.setStyleSheet(
                "QFrame#drumDashboardSection {background:#041a41;"
                "border:1px solid #2bb1fc;border-radius:6px;}")
            layout=QVBoxLayout(frame)
            layout.setContentsMargins(6,6,6,6)
            layout.setSpacing(4)
            caption=QLabel(names[index])
            caption.setStyleSheet(
                "color:#e0f8ff;font-weight:800;font-size:12px;"
                "background:#052257;padding:5px 7px;border-radius:3px;")
            caption.setFixedHeight(28)
            layout.addWidget(caption)
            page=original[index]
            layout.addWidget(page,1)
            # removeTab() marca explícitamente como ocultas las páginas
            # anteriores. Deben reactivarse al incorporarlas al panel.
            page.setVisible(True)
            self.dashboard_sections[index]=frame
            grid.addWidget(frame,row,column,1,column_span)
            return page

        waves=section(0,0,0)
        mixer=section(1,0,1)
        editor=section(2,2,0)
        sequence=section(3,2,1)
        results=section(4,3,0,2)
        grid.setColumnStretch(0,46)
        grid.setColumnStretch(1,54)
        grid.setRowStretch(0,0)
        grid.setRowStretch(1,0)
        grid.setRowStretch(2,0)

        # La vista de ondas debe ofrecer onda y audición, no repetir
        # controles de mezcla que ya están enfrente.
        for row in self.track_rows.values():
            row.gain.hide()
            row.pan.hide()
            row.mute.hide()
            row.solo.hide()
            row.setMinimumHeight(42)
            row.setMaximumHeight(50)
            row.wave.setMaximumHeight(34)
        wave_scroll=waves.findChild(QScrollArea)
        if wave_scroll is not None:
            wave_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            wave_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            wave_scroll.setFixedHeight(332)
        waves.setMinimumHeight(372)

        # Reducir los seis strips sin reducir legibilidad.
        # El inspector con EQ por canal no desaparece: queda integrado
        # horizontalmente entre la consola y el editor, sin otra pestaña.
        self.mixer_content.layout().removeWidget(self.inspector)
        self.inspector.setParent(content)
        self.inspector.show()
        grid.addWidget(self.inspector,1,0,1,2)
        self.mixer_footer.hide()
        self.toggle_inspector_btn.hide()
        self.mixer_content.setMinimumHeight(0)
        self.mixer_content.setMaximumHeight(365)
        self.console_canvas.setFixedHeight(261)
        for row in self.mixer_rows.values():
            row.setMinimumWidth(89)
            row.setMaximumWidth(140)
        self.mixer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.mixer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mixer_scroll.setFixedHeight(378)
        mixer.setMinimumHeight(380)

        # El editor original distribuía 4 controles de 175 px por fila,
        # demasiado para media pantalla. Reorganizamos controles reales.
        editor_layout=editor.layout()
        editor_grid=editor.findChild(QGridLayout)
        # Conserva todos los widgets y callbacks; solo refluye la malla.
        grid_editor=None
        page_layout=editor.layout()
        for idx in range(page_layout.count()):
            item=page_layout.itemAt(idx)
            if item and item.layout() and isinstance(item.layout(),QGridLayout):
                grid_editor=item.layout()
                break
        if grid_editor is not None:
            assignments=[]
            for row_idx in range(grid_editor.rowCount()):
                for col_idx in range(grid_editor.columnCount()):
                    item=grid_editor.itemAtPosition(row_idx,col_idx)
                    if item and item.widget():
                        assignments.append((row_idx,col_idx,item.widget()))
            for _,_,widget in assignments: grid_editor.removeWidget(widget)
            # La lectura natural se conserva agrupando etiqueta + deslizador.
            assignments.sort(key=lambda x:(x[0],x[1]))
            for j in range(0,len(assignments),2):
                pair=assignments[j:j+2]
                r=(j//2)//2
                c=((j//2)%2)*2
                for x,(_,_,widget) in enumerate(pair):
                    if x==1:
                        widget.setMaximumWidth(175)
                    grid_editor.addWidget(widget,r,c+x)
            grid_editor.setHorizontalSpacing(4)
            grid_editor.setVerticalSpacing(4)
        self.big_wave.setMinimumHeight(78)
        self.big_wave.setMaximumHeight(92)
        self.editor_summary.setMaximumWidth(210)
        self.editor_summary.setToolTip("Pista seleccionada y duración del archivo original.")
        editor.setMinimumHeight(420)

        # El secuenciador de 16 pasos se mantiene completo sin pestañas.
        # Distribución a dos líneas de los parámetros de tempo.
        seq_layout=sequence.layout()
        toolbar_item=seq_layout.itemAt(0)
        if toolbar_item and toolbar_item.layout():
            toolbar=toolbar_item.layout()
            # Extraer exactamente los widgets existentes, sin nuevos
            # controles que no estén unidos al motor MIDI.
            seq_items=[]
            while toolbar.count():
                item=toolbar.takeAt(0)
                if item.widget(): seq_items.append(item.widget())
            toolbar2=QGridLayout()
            toolbar2.setContentsMargins(0,0,0,0)
            toolbar2.setHorizontalSpacing(4)
            toolbar2.setVerticalSpacing(4)
            fields=[self.seq_bpm,self.seq_velocity,self.seq_swing,self.seq_bars]
            if seq_items:
                # El primer QLabel es el título; las siguientes etiquetas
                # son BPM, Velocidad, Swing, Compases.
                title=seq_items[0]
                title.setText("PATRÓN DE 16 PASOS")
                toolbar2.addWidget(title,0,0,1,4)
                label_map={}
                for i,field in enumerate(fields):
                    fidx=seq_items.index(field)
                    if fidx>0:label_map[field]=seq_items[fidx-1]
                for i,field in enumerate(fields):
                    row=1+i//2
                    col=(i%2)*2
                    if field in label_map:
                        toolbar2.addWidget(label_map[field],row,col)
                    toolbar2.addWidget(field,row,col+1)
                    if hasattr(field,"setMaximumWidth"):
                        field.setMaximumWidth(185)
                # No dejar etiquetas vivas ocultas accidentalmente.
                for widget in seq_items:
                    if widget.parent() and not widget.isVisible() and (
                        widget not in fields and widget not in label_map.values()
                        and widget is not title):
                        widget.deleteLater()
            seq_layout.insertLayout(0,toolbar2)
            # El layout anterior vacío se retira, la nueva malla ocupa su lugar.
            seq_layout.removeItem(toolbar)
        for buttons in self.step_buttons.values():
            for button in buttons:button.setFixedSize(24,24)
        sequence.setMinimumHeight(420)
        results.setMinimumHeight(180)
        self.drum.result_table.setMinimumHeight(126)
        # QScrollArea no calcula siempre las alturas de páginas reparentadas;
        # fijar las tarjetas evita que Qt las aplaste a cero.
        for i,height in ((0,384),(1,384),(2,430),(3,430),(4,215)):
            self.dashboard_sections[i].setMinimumHeight(height)
        content.setMinimumHeight(384+137+430+215+44)

        self.dashboard_scroll.setWidget(content)
        self.dashboard_content=content
        self.addTab(self.dashboard,"Estudio de batería")
        self.tabBar().hide()
        self.setCurrentIndex(0)
        self.setObjectName("drumUnifiedDashboard")
        # El único desplazamiento es el de la superficie completa.
        self._refresh_mixer_density()
        self._update_dashboard_layout()

    def _update_dashboard_layout(self):
        if not hasattr(self,"dashboard_scroll"):return
        available=max(850,self.dashboard_scroll.viewport().width())
        left=int(available*.455)
        right=available-left-9
        self.dashboard_sections[0].setMinimumWidth(max(340,left-24))
        self.dashboard_sections[1].setMinimumWidth(max(460,right-24))

    def scroll_to_section(self,index):
        if not hasattr(self,"dashboard_scroll"):return
        card=self.dashboard_sections.get(index)
        if card is not None:
            self.dashboard_scroll.ensureWidgetVisible(card,0,12)

    def _build_tracks(self):
        page=QWidget(self)
        outer=QVBoxLayout(page)
        outer.setContentsMargins(6,5,6,5)
        outer.setSpacing(5)
        heading=QHBoxLayout()
        heading.addWidget(QLabel("ONDA ORIGINAL · NIVEL · PANORAMA · MUTE / SOLO"))
        heading.addStretch()
        self.reload=QPushButton("Actualizar ondas")
        self.reload.clicked.connect(self.refresh)
        heading.addWidget(self.reload)
        outer.addLayout(heading)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body=QWidget()
        stack=QVBoxLayout(body)
        stack.setSpacing(5)
        stack.setContentsMargins(2,2,2,2)
        self.track_rows={}
        for part in PARTS:
            row=ChannelRow(part,self)
            row.setMinimumHeight(55)
            self.track_rows[part]=row
            self.rows.append(row)
            stack.addWidget(row)
        stack.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll,1)
        self.addTab(page,"6 pistas · ondas")

    def _build_mixer(self):
        page=QWidget(self)
        page.setObjectName("drumConsolePage")
        viewport=QVBoxLayout(page)
        viewport.setContentsMargins(0,0,0,0)
        viewport.setSpacing(0)
        # Desplazar el bloque ENTERO únicamente en ventanas bajas. Los
        # faders y botones no pueden quedar cortados por barras intermedias.
        self.mixer_scroll=QScrollArea(page)
        self.mixer_scroll.setFrameShape(QFrame.NoFrame)
        self.mixer_scroll.setWidgetResizable(True)
        self.mixer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mixer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        viewport.addWidget(self.mixer_scroll,1)
        self.mixer_content=QWidget()
        self.mixer_content.setMinimumHeight(551)
        outer=QVBoxLayout(self.mixer_content)
        outer.setContentsMargins(6,5,6,4)
        outer.setSpacing(5)
        header=QHBoxLayout()
        header.setSpacing(9)
        self.mixer_title=QLabel("MEZCLADOR DE BATERÍA  /  6 CANALES")
        self.mixer_title.setStyleSheet(
            "color:#e0f8ff;font-size:14px;font-weight:800;")
        header.addWidget(self.mixer_title)
        self.mixer_state=QLabel("0/6 pistas")
        self.mixer_state.setStyleSheet("color:#85f0ff;font-weight:bold;")
        header.addWidget(self.mixer_state)
        header.addStretch(1)
        self._inspector_user_open=None
        self.toggle_inspector_btn=QPushButton("Canal y EQ ▾")
        self.toggle_inspector_btn.setToolTip(
            "Mostrar u ocultar el detalle, la ecualización y el editor del canal seleccionado.")
        self.toggle_inspector_btn.clicked.connect(self.toggle_mixer_inspector)
        header.addWidget(self.toggle_inspector_btn)
        self.render_mix_btn=QPushButton("↓  Exportar mezcla · FLAC 24 bits")
        self.render_mix_btn.setObjectName("primary")
        self.render_mix_btn.clicked.connect(self.render_mix)
        self.render_mix_btn.setToolTip(
            "Combina las pistas reales con fader, panorámica, Mute y Solo. "
            "Nunca sustituye los stems de origen.")
        header.addWidget(self.render_mix_btn)
        outer.addLayout(header)
        divider=QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color:#a3cad6;")
        outer.addWidget(divider)
        self.console_canvas=QWidget(self.mixer_content)
        self.console_canvas.setFixedHeight(292)
        main=QHBoxLayout(self.console_canvas)
        main.setContentsMargins(0,0,4,0)
        main.setSpacing(7)
        self.mixer_rows={}
        for part in PARTS:
            strip=ConsoleStrip(part,self)
            self.mixer_rows[part]=strip
            self.rows.append(strip)
            main.addWidget(strip,1)
        outer.addWidget(self.console_canvas)
        self.inspector=ChannelInspector(self)
        outer.addWidget(self.inspector)
        presets={
            "Natural · equilibrada":{p:{"gain":0,"pan":0,"mute":False,"solo":False} for p in PARTS},
            "Rock potente":{p:{"gain":v,"pan":0,"mute":False,"solo":False} for p,v in
                zip(PARTS,(3,3,1,-3,-5,-5))},
            "Pop definido":{p:{"gain":v,"pan":pn,"mute":False,"solo":False} for p,v,pn in
                zip(PARTS,(2,2,0,-3,-7,-6),(0,0,-20,20,30,-30))},
            "Jazz acústico":{p:{"gain":v,"pan":pn,"mute":False,"solo":False} for p,v,pn in
                zip(PARTS,(-2,0,-3,-1,0,-3),(0,0,20,-15,15,-12))},
            "Electrónica":{p:{"gain":v,"pan":0,"mute":False,"solo":False} for p,v in
                zip(PARTS,(4,3,0,0,-8,-5))},
        }
        self.mixer_presets=PresetStrip("drum_mixer",presets,self.snapshot_mix,self.apply_mix_preset,self.mixer_content)
        outer.insertWidget(2,self.mixer_presets)
        self.mixer_footer=QLabel(
            "Las seis pistas permanecen vacías hasta producir stems reales · "
            "Selecciona un canal para escucharlo, editarlo o ajustar su mezcla.")
        self.mixer_footer.setStyleSheet("color:#e0f8ff;font-size:10px;")
        outer.addWidget(self.mixer_footer)
        outer.addStretch(1)
        self.mixer_scroll.setWidget(self.mixer_content)
        self.console_scroll=self.mixer_scroll
        self.addTab(page,"Mezclador · 6 canales")
        self._refresh_mixer_density()
        self.level_timer=QTimer(self)
        self.level_timer.setInterval(85)
        self.level_timer.timeout.connect(self.update_mix_levels)
        self.level_timer.start()
        self.select_channel("Bombo")

    def _build_editor(self):
        page=QWidget(self)
        lay=QVBoxLayout(page)
        lay.setContentsMargins(9,5,9,5)
        lay.setSpacing(6)
        source_row=QHBoxLayout()
        source_row.addWidget(QLabel("EDITAR PISTA"))
        self.edit_source=QComboBox(self)
        self.edit_source.addItem("— Seleccionar instrumento —",None)
        for part in PARTS:self.edit_source.addItem(part,part)
        self.edit_source.currentIndexChanged.connect(self._set_edit_source)
        source_row.addWidget(self.edit_source)
        source_row.addStretch(1)
        self.editor_summary=QLabel("Sin audio seleccionado.")
        self.editor_summary.setObjectName("muted")
        source_row.addWidget(self.editor_summary)
        lay.addLayout(source_row)
        self.big_wave=DrumEditWave(page)
        self.big_wave.rangeChanged.connect(self._wave_drag_range)
        self.big_wave.setMinimumHeight(90)
        lay.addWidget(self.big_wave,1)
        grid=QGridLayout()
        grid.setHorizontalSpacing(10);grid.setVerticalSpacing(8)
        controls=(
            ("trim_start","Inicio",0,86400000,0,"ms"),
            ("trim_end","Final",0,86400000,0,"ms"),
            ("fade_in","Fade entrada",0,30000,0,"ms"),
            ("fade_out","Fade salida",0,30000,0,"ms"),
            ("edit_gain","Ganancia", -24,24,0,"dB"),
            ("highpass","Filtro graves",0,1000,0,"Hz"),
            ("lowpass","Filtro agudos",1000,20000,20000,"Hz"),
            ("compression","Compresión",0,100,0,"%"),
            ("eq_low","EQ graves", -12,12,0,"dB"),
            ("eq_mid","EQ medios", -12,12,0,"dB"),
            ("eq_high","EQ agudos", -12,12,0,"dB"),
        )
        self.editor_controls=[]
        for i,(name,title,low,high,value,suffix) in enumerate(controls):
            r=i//4;c=(i%4)*2
            grid.addWidget(QLabel(title),r,c)
            spin=StudioSliderSpin(low,high,value,suffix,page,width=175)
            spin.setToolTip("Ajuste no destructivo aplicado a una nueva copia FLAC.")
            setattr(self,name,spin)
            self.editor_controls.append(spin)
            grid.addWidget(spin,r,c+1)
        lay.addLayout(grid)
        params=("fade_in","fade_out","edit_gain","highpass","lowpass","compression",
                "eq_low","eq_mid","eq_high")
        editor_presets={
            "Natural":{"fade_in":0,"fade_out":0,"edit_gain":0,"highpass":0,"lowpass":20000,"compression":0,"eq_low":0,"eq_mid":0,"eq_high":0},
            "Bombo contundente":{"fade_in":0,"fade_out":30,"edit_gain":3,"highpass":30,"lowpass":9000,"compression":55,"eq_low":3,"eq_mid":-2,"eq_high":0},
            "Caja presente":{"fade_in":0,"fade_out":60,"edit_gain":2,"highpass":110,"lowpass":16000,"compression":43,"eq_low":-2,"eq_mid":4,"eq_high":2},
            "Toms limpios":{"fade_in":0,"fade_out":90,"edit_gain":1,"highpass":48,"lowpass":14000,"compression":35,"eq_low":2,"eq_mid":-1,"eq_high":0},
            "Charles suave":{"fade_in":0,"fade_out":20,"edit_gain":-3,"highpass":300,"lowpass":14500,"compression":15,"eq_low":-2,"eq_mid":-2,"eq_high":1},
            "Ride aireado":{"fade_in":0,"fade_out":70,"edit_gain":-2,"highpass":250,"lowpass":18000,"compression":12,"eq_low":-3,"eq_mid":-1,"eq_high":3},
            "Crash controlado":{"fade_in":0,"fade_out":150,"edit_gain":-4,"highpass":230,"lowpass":15000,"compression":25,"eq_low":-3,"eq_mid":-1,"eq_high":-2},
        }
        self.editor_presets=PresetStrip("drum_editor",editor_presets,
            lambda:{name:getattr(self,name).value() for name in params},
            self.apply_editor_preset,page)
        lay.addWidget(self.editor_presets)
        buttons=QHBoxLayout()
        self.editor_render_btn=QPushButton("Crear versión editada · FLAC 24 bits")
        self.editor_render_btn.setObjectName("primary")
        self.editor_render_btn.clicked.connect(self.render_edit)
        buttons.addWidget(self.editor_render_btn)
        original=QPushButton("Escuchar original")
        original.clicked.connect(self.listen_editor)
        buttons.addWidget(original)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        self.addTab(page,"Editor de audio")

    def _build_sequencer(self):
        import mido
        page=QWidget(self)
        lay=QVBoxLayout(page)
        lay.setContentsMargins(9,7,9,7)
        lay.setSpacing(6)
        toolbar=QHBoxLayout()
        toolbar.addWidget(QLabel("PATRÓN MIDI DE BATERÍA · 16 PASOS"))
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("BPM"))
        self.seq_bpm=StudioSliderSpin(50,240,120,"",page,width=195)
        toolbar.addWidget(self.seq_bpm)
        toolbar.addWidget(QLabel("Velocidad"))
        self.seq_velocity=StudioSliderSpin(1,127,100,"",page,width=178)
        toolbar.addWidget(self.seq_velocity)
        toolbar.addWidget(QLabel("Swing"))
        self.seq_swing=StudioSliderSpin(0,60,0,"%",page,width=175)
        toolbar.addWidget(self.seq_swing)
        toolbar.addWidget(QLabel("Compases"))
        self.seq_bars=QComboBox(page)
        for count in (1,2,4,8):self.seq_bars.addItem(str(count),count)
        self.seq_bars.setCurrentIndex(2)
        toolbar.addWidget(self.seq_bars)
        lay.addLayout(toolbar)
        matrix=QGridLayout()
        matrix.setHorizontalSpacing(4)
        matrix.setVerticalSpacing(5)
        matrix.addWidget(QLabel("Instrumento"),0,0)
        for step in range(16):
            label=QLabel(str(step+1))
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(27)
            label.setStyleSheet("color:#85f0ff;" if step%4==0 else "color:#a3e4f0;")
            matrix.addWidget(label,0,step+1)
        self.step_buttons={}
        for r,part in enumerate(PARTS,1):
            name=QLabel(part)
            name.setStyleSheet(f"color:{COLORS[part]};font-weight:700;")
            matrix.addWidget(name,r,0)
            row=[]
            for i in range(16):
                button=QPushButton("●" if False else "·")
                button.setCheckable(True)
                button.setFixedSize(29,27)
                button.setProperty("drumPart",part)
                button.toggled.connect(lambda checked,b=button:self._step_style(b,checked))
                self._step_style(button,False)
                matrix.addWidget(button,r,i+1)
                row.append(button)
            self.step_buttons[part]=row
        matrix.setColumnStretch(17,1)
        lay.addLayout(matrix)
        rhythmic_presets={
            "Vacío":{},
            "Rock 4/4":{"Bombo":(0,8),"Caja":(4,12),"Charles":(0,2,4,6,8,10,12,14)},
            "Pop moderno":{"Bombo":(0,6,8,14),"Caja":(4,12),"Charles":tuple(range(0,16,2))},
            "House":{"Bombo":(0,4,8,12),"Caja":(4,12),"Charles":(2,6,10,14)},
            "Funk":{"Bombo":(0,3,8,10),"Caja":(4,7,12),"Charles":(0,2,4,6,8,10,12,14,15)},
            "Breakbeat":{"Bombo":(0,7,10),"Caja":(4,12,15),"Charles":(0,2,4,6,8,10,12,14)},
        }
        self.pattern_presets=PresetStrip("drum_pattern",
            {name:{part:list(steps) for part,steps in value.items()}
             for name,value in rhythmic_presets.items()},
            self.snapshot_pattern,self.apply_pattern_preset,page)
        lay.addWidget(self.pattern_presets)
        actions=QHBoxLayout()
        self.seq_preview=QPushButton("▶ Escuchar patrón MIDI")
        self.seq_preview.clicked.connect(self.play_pattern)
        self.seq_export=QPushButton("Exportar MIDI…")
        self.seq_export.clicked.connect(self.export_pattern)
        actions.addWidget(self.seq_preview)
        actions.addWidget(self.seq_export)
        actions.addStretch(1)
        lay.addLayout(actions)
        note=QLabel("Canal 10 General MIDI · el patrón está vacío al iniciar. "
                    "Los presets crean eventos MIDI editables, nunca audio separado ficticio.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch()
        self.addTab(page,"Secuenciador MIDI")

    def _build_results(self):
        page=QWidget(self)
        self.results_layout=QVBoxLayout(page)
        self.results_layout.setContentsMargins(6,4,6,4)
        self.results_layout.setSpacing(3)
        explanation=QLabel("Archivos auténticos de esta tarea: seis stems del modelo y "
            "ediciones o mezclas generadas explícitamente.")
        explanation.setObjectName("muted")
        self.results_layout.addWidget(explanation)
        self.addTab(page,"Resultados")

    def _step_style(self,button,checked):
        button.setText("●" if checked else "·")
        button.setStyleSheet(
            "background:#0d59e0;color:white;border:1px solid #6fe1ff;"
            if checked else
            "background:#041d4a;color:#a3e4f0;border:1px solid #2599da;")

    def snapshot_pattern(self):
        return {part:[n for n,b in enumerate(buttons) if b.isChecked()]
                for part,buttons in self.step_buttons.items()}

    def apply_pattern_preset(self,settings):
        for part,buttons in self.step_buttons.items():
            valid=[v for v in settings.get(part,[]) if isinstance(v,int) and 0<=v<16]
            for i,button in enumerate(buttons):button.setChecked(i in valid)

    def _pattern(self):
        import mido
        midi=mido.MidiFile(type=1,ticks_per_beat=480)
        track=mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.MetaMessage("track_name",name="StemMIDI Drum Editor",time=0))
        track.append(mido.MetaMessage("set_tempo",tempo=mido.bpm2tempo(self.seq_bpm.value()),time=0))
        events=[]
        beats_per_bar=1920
        for bar in range(self.seq_bars.currentData()):
            for part,steps in self.snapshot_pattern().items():
                for step in steps:
                    # Swing desplazando las semicorcheas pares (offbeat).
                    tick=bar*beats_per_bar+step*120+(
                        round(self.seq_swing.value()/100.*110) if step%2 else 0)
                    events.append((tick,1,mido.Message("note_on",channel=9,
                        note=GM[part],velocity=self.seq_velocity.value())))
                    events.append((tick+75,0,mido.Message("note_off",channel=9,
                        note=GM[part],velocity=0)))
        last=0
        for position,order,msg in sorted(events,key=lambda x:(x[0],x[1])):
            track.append(msg.copy(time=position-last))
            last=position
        track.append(mido.MetaMessage("end_of_track",
            time=max(0,self.seq_bars.currentData()*beats_per_bar-last)))
        return midi

    def play_pattern(self):
        path=self.drum.storage.root/"patron_bateria_escucha.mid"
        path.parent.mkdir(parents=True,exist_ok=True)
        self._pattern().save(str(path))
        self.drum.preview.load(path,autoplay=True)

    def export_pattern(self):
        project=getattr(self.drum.main,"project_dir",None)
        from project_layout import module_dir
        base=(module_dir(project,"bateria") if project else Path.home())
        base.mkdir(parents=True,exist_ok=True)
        path,_=file_dialogs.get_save_file_name(self,"Exportar patrón de batería",
            str(base/((Path(project).name+"_" if project else "")+"Patron_bateria.mid")),
            "MIDI (*.mid)")
        if not path:return
        destination=Path(path)
        if destination.suffix.lower()!=".mid":
            destination=destination.with_suffix(".mid")
        if project:
            from project_layout import layout_active,save_folder
            if layout_active(project):
                destination=save_folder(project,"bateria",destination.parent)/destination.name
        if destination.exists():
            response=QMessageBox.question(self,"Sobrescribir patrón",
                "El archivo MIDI ya existe. ¿Sobrescribirlo?",
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if response!=QMessageBox.Yes:return
        destination.parent.mkdir(parents=True,exist_ok=True)
        from uuid import uuid4
        temp=destination.with_name("."+destination.stem+"_export_"+uuid4().hex+".mid")
        try:
            self._pattern().save(str(temp))
            temp.replace(destination)
        finally:
            temp.unlink(missing_ok=True)
        self.drum.status.setText("Patrón MIDI exportado: "+destination.name)
        if project:
            try:
                from export_dialog import _copy_atomic
                internal=Path(project)/"temporales"/"bateria"/"patron_bateria.mid"
                if destination.resolve()!=internal.resolve():
                    _copy_atomic(destination,internal)
            except (OSError,ValueError) as exc:
                self.drum.status.setText(
                    "Patrón exportado, pero no incluido en el proyecto: "+str(exc))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"dashboard_scroll"):
            self._update_dashboard_layout()
        elif hasattr(self,"toggle_inspector_btn"):
            self._refresh_mixer_density()

    def toggle_mixer_inspector(self):
        self._inspector_user_open=not self.inspector.isVisible()
        self._refresh_mixer_density()

    def _refresh_mixer_density(self):
        if not hasattr(self,"inspector"):
            return
        if hasattr(self,"dashboard_scroll"):
            # Inspector horizontal visible dentro del mismo dashboard.
            self.inspector.show()
            self.mixer_footer.hide()
            self.toggle_inspector_btn.hide()
            self.mixer_content.setMinimumHeight(0)
            return
        spacious=self.height()>=555
        visible=(spacious if self._inspector_user_open is None
                 else self._inspector_user_open)
        if self.inspector.isVisible()!=visible:
            self.inspector.setVisible(visible)
        self.mixer_footer.setVisible(visible)
        self.mixer_content.setMinimumHeight(551 if visible else 0)
        self.toggle_inspector_btn.setText(
            "Ocultar detalle · EQ ▴" if visible else "Ver canal · EQ ▾")

    def select_channel(self,part):
        if part not in PARTS:return
        self.selected_part=part
        for name,strip in self.mixer_rows.items():
            strip.set_selected(name==part)
        self.inspector.update_selected(
            part,self.sources.get(part),self.channels[part])

    def edit_selected_channel(self):
        part=self.selected_part
        if not _is_real(self.sources.get(part)):return
        index=self.edit_source.findData(part)
        if index>=0:self.edit_source.setCurrentIndex(index)
        self.scroll_to_section(2)

    def reset_selected_channel(self):
        part=self.selected_part
        if not _is_real(self.sources.get(part)):return
        self.set_state(part,"gain",0)
        self.set_state(part,"pan",0)

    def update_mix_levels(self):
        if not self.isVisible():return
        player=getattr(self.drum,"preview",None)
        if player is None:return
        origin=getattr(player,"_origin",None)
        origin=Path(origin).resolve() if origin else None
        playing=bool((player._native_qt and player._qt_active)
            or (player._play_process is not None and not player._paused))
        position=player._position() if playing else 0
        for strip in self.mixer_rows.values():
            strip.update_audio_peak(playing,origin,position)
        if self.selected_part:
            selected=self.inspector
            if _is_real(self.sources.get(self.selected_part)):
                selected.duration.setText(
                    "Duración: {:.1f} s".format(selected.wave.duration_seconds)
                    if selected.wave.duration_seconds else "Leyendo audio…")

    def set_state(self,part,name,value):
        if part not in self.channels:return
        if name in ("mute","solo"):value=bool(value)
        else:value=int(value)
        self.channels[part][name]=value
        for row in self.rows:
            if row.part==part:
                row.update_state(self.channels[part],self.sources[part])
        if part==self.selected_part:
            self.inspector.update_selected(
                part,self.sources.get(part),self.channels[part])

    def snapshot_mix(self):
        return {part:dict(self.channels[part]) for part in PARTS}

    def apply_mix_preset(self,data):
        for part in PARTS:
            settings=data.get(part)
            if not isinstance(settings,dict):continue
            for key in ("gain","pan","mute","solo","eq_low","eq_mid","eq_high"):
                if key not in settings and not key.startswith("eq_"):
                    continue
                value=settings.get(key,0)
                if key in ("mute","solo"):
                    self.channels[part][key]=bool(value)
                elif key=="gain":
                    self.channels[part][key]=max(-36,min(12,int(value)))
                elif key=="pan":
                    self.channels[part][key]=max(-100,min(100,int(value)))
                else:
                    self.channels[part][key]=max(-12,min(12,int(value)))
        self._sync_channels()

    def apply_editor_preset(self,values):
        for key,value in values.items():
            control=getattr(self,key,None)
            if isinstance(control,StudioSliderSpin):
                control.setValue(max(control.minimum(),min(control.maximum(),int(value))))

    def _real_sources(self):
        from drum_module import category
        found={part:None for part in PARTS}
        for file in self.drum.storage.items:
            path=Path(file)
            if "ediciones" in path.parts or path.name.lower().startswith(
                    ("edit_","mezcla_")):
                continue
            part=category(path)
            # La toma real más reciente es la fuente del canal; las previas
            # siguen disponibles en Resultados y nunca se sobrescriben.
            if part in found and path.is_file():
                found[part]=path
        return found

    def refresh(self):
        self.sources=self._real_sources()
        self._sync_channels()
        current=self.edit_source.currentData()
        if not _is_real(self.sources.get(current)):
            self.big_wave.set_file(None)
        self.editor_render_btn.setEnabled(_is_real(self.sources.get(current)))
        self.render_mix_btn.setEnabled(any(_is_real(f) for f in self.sources.values()))
        if current:
            # Renderizar un resultado nuevo no debe borrar la selección
            # de corte ni los ajustes pendientes del editor.
            original=self.sources.get(current)
            if getattr(self,"_last_editor_source",None)!=original:
                self._last_editor_source=original
                self._set_edit_source()
        # La carga de formas de onda puede volver a mostrar widgets de
        # QScrollArea. Mantener la densidad adaptativa tras cada refresco.
        self._refresh_mixer_density()

    def _sync_channels(self):
        for row in self.rows:
            row.update_state(self.channels[row.part],self.sources[row.part])
        if hasattr(self,"mixer_state"):
            count=sum(_is_real(f) for f in self.sources.values())
            self.mixer_state.setText(f"{count}/6 pistas reales")
        if hasattr(self,"inspector"):
            self.inspector.update_selected(
                self.selected_part,self.sources.get(self.selected_part),
                self.channels[self.selected_part])

    def listen(self,part):
        path=self.sources.get(part)
        if _is_real(path):
            self.drum.preview.load(path,autoplay=True)
            self.drum.status.setText("Escuchando pista original: "+part)

    def listen_editor(self):
        self.listen(self.edit_source.currentData())

    def _wave_drag_range(self,start,end):
        span=min(self.trim_end.maximum(),round(self.big_wave.duration_seconds*1000))
        self.trim_start.setValue(round(start*span))
        self.trim_end.setValue(round(end*span))
        self.editor_summary.setText(
            f"Región: {self.trim_start.value()/1000:.2f}"
            f"–{self.trim_end.value()/1000:.2f} s · arrastrar para modificar")

    def _set_edit_source(self,*_):
        part=self.edit_source.currentData()
        path=self.sources.get(part)
        self._last_editor_source=path
        active=_is_real(path)
        self.big_wave.set_file(path if active else None)
        self.editor_render_btn.setEnabled(active)
        for field in self.editor_controls:field.setEnabled(active)
        if not active:
            self.editor_summary.setText("Sin audio real de "+str(part or "este instrumento"))
            return
        try:seconds=_ffprobe_duration(path)
        except (OSError,ValueError,subprocess.TimeoutExpired):
            self.editor_summary.setText("Duración de audio no disponible")
            return
        millis=min(86400000,round(seconds*1000))
        self.trim_start.setRange(0,max(0,millis))
        self.trim_end.setRange(0,max(0,millis))
        self.trim_start.setValue(0)
        self.trim_end.setValue(millis)
        self.big_wave.selected=None
        self.big_wave.update()
        self.editor_summary.setText(f"{seconds:.2f} s · {path.name[:48]}")

    def _result_target(self,description):
        store=self.drum.storage
        if not store.folder or not store.folder.is_dir():
            raise ValueError("No hay una tarea de batería real en este proyecto.")
        folder=store.folder/"ediciones"
        folder.mkdir(parents=True,exist_ok=True)
        import uuid
        return folder/(description+"_"+uuid.uuid4().hex[:8]+".flac")

    def _start_ffmpeg(self,arguments,where,operation):
        if self.process is not None or self.drum.process is not None:return
        executable=_ffmpeg_command()
        if not executable:
            QMessageBox.warning(self,"FFmpeg no encontrado",
                "Instala ffmpeg antes de mezclar o editar pistas de batería.")
            return
        self.output_path=Path(where)
        self.output_operation=operation
        self.process=QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._log)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._failed)
        self.drum.status.setText("Procesando audio auténtico con FFmpeg…")
        self.render_mix_btn.setEnabled(False)
        self.editor_render_btn.setEnabled(False)
        self.process.start(executable,arguments)

    def _log(self):
        if self.process is None:return
        content=bytes(self.process.readAllStandardOutput()).decode("utf-8","replace")
        if content.strip():
            self.drum.status.setText(content.strip().splitlines()[-1][-210:])

    def _failed(self,*_):
        if self.process is not None:
            self.drum.status.setText("Fallo iniciando el render. Comprueba FFmpeg.")

    def _finished(self,exitcode,status):
        proc=self.process
        if proc is None:return
        self._log()
        self.process=None
        output=self.output_path
        self.output_path=None
        valid=(exitcode==0 and status==QProcess.NormalExit and
            output is not None and output.is_file() and output.stat().st_size>500)
        if valid:
            from task_staging import inside
            if not inside(output,self.drum.storage.folder):
                valid=False
            else:
                self.drum.storage.items.append(output)
                self.drum.storage.manifest()
                self.drum.refresh_results()
                self.drum.resultsChanged.emit()
                self.drum.status.setText("Audio generado: "+output.name+
                    " · editable y disponible en Resultados.")
                self.drum.preview.load(output)
                self.scroll_to_section(4)
        if not valid:
            self.drum.status.setText("Error renderizando audio; no se ha publicado un resultado inválido.")
            if output is not None:output.unlink(missing_ok=True)
        self.render_mix_btn.setEnabled(any(_is_real(p) for p in self.sources.values()))
        self.editor_render_btn.setEnabled(
            _is_real(self.sources.get(self.edit_source.currentData())))
        proc.deleteLater()

    def render_mix(self):
        if self.process is not None:return
        any_solo=any(settings["solo"] and _is_real(self.sources[p])
                     for p,settings in self.channels.items())
        active=[]
        for part in PARTS:
            f=self.sources[part]
            info=self.channels[part]
            if not _is_real(f) or info["mute"] or (any_solo and not info["solo"]):
                continue
            active.append((f,info))
        if not active:
            QMessageBox.information(self,"Sin pistas",
                "Necesitas al menos un stem real y audible para generar una mezcla.")
            return
        try:target=self._result_target("mezcla_bateria")
        except ValueError as exc:
            QMessageBox.warning(self,"Sin tarea",str(exc))
            return
        arguments=["-nostdin","-hide_banner","-loglevel","error","-y"]
        filters=[]
        inputs=[]
        for i,(path,info) in enumerate(active):
            arguments+=["-i",str(path)]
            # Pan preserva amplitud cuando el control está centrado.
            pos=info["pan"]/100
            left=1. if pos<=0 else 1.-pos
            right=1. if pos>=0 else 1.+pos
            chain=[f"[{i}:a]aformat=channel_layouts=stereo"]
            for key,freq in (("eq_low",110),("eq_mid",1500),("eq_high",7000)):
                amount=int(info.get(key,0))
                if amount:
                    chain.append(f"equalizer=f={freq}:width_type=o:width=1:g={amount}")
            chain.extend((f"volume={info['gain']}dB",
                f"pan=stereo|c0={left:.3f}*c0|c1={right:.3f}*c1[s{i}]"))
            filters.append(",".join(chain))
            inputs.append(f"[s{i}]")
        filters.append("".join(inputs)+
            f"amix=inputs={len(active)}:duration=longest:normalize=0,"
            "alimiter=limit=0.94[out]")
        arguments+=["-filter_complex",";".join(filters),"-map","[out]",
             "-c:a","flac","-sample_fmt","s32","-bits_per_raw_sample","24",str(target)]
        self._start_ffmpeg(arguments,target,"mix")

    def render_edit(self):
        if self.process is not None:return
        part=self.edit_source.currentData()
        file=self.sources.get(part)
        if not _is_real(file):
            QMessageBox.information(self,"Pista necesaria",
                "Selecciona un instrumento que tenga audio separado real.")
            return
        start=self.trim_start.value()/1000
        end=self.trim_end.value()/1000
        if end<=start+.02:
            QMessageBox.warning(self,"Intervalo inválido",
                "El final debe estar después del inicio de la selección.")
            return
        length=end-start
        fades=(self.fade_in.value()/1000,self.fade_out.value()/1000)
        if sum(fades)>length:
            QMessageBox.warning(self,"Fade demasiado largo",
                "Los desvanecimientos no pueden superar la duración seleccionada.")
            return
        try:target=self._result_target("edit_"+part.lower())
        except ValueError as exc:
            QMessageBox.warning(self,"Sin tarea",str(exc))
            return
        chain=[f"atrim=start={start:.4f}:end={end:.4f}","asetpts=PTS-STARTPTS"]
        if self.edit_gain.value():
            chain.append(f"volume={self.edit_gain.value()}dB")
        if self.highpass.value()>=20:
            chain.append(f"highpass=f={self.highpass.value()}")
        if self.lowpass.value()<19500:
            chain.append(f"lowpass=f={self.lowpass.value()}")
        for control,freq in ((self.eq_low,110),(self.eq_mid,1500),(self.eq_high,7000)):
            if control.value():
                chain.append(
                    f"equalizer=f={freq}:width_type=o:width=1:g={control.value()}")
        if self.compression.value():
            ratio=1+self.compression.value()*.065
            chain.append(f"acompressor=threshold=0.15:ratio={ratio:.2f}:attack=8:release=110")
        if fades[0]>0:
            chain.append(f"afade=t=in:st=0:d={fades[0]:.3f}")
        if fades[1]>0:
            chain.append(f"afade=t=out:st={max(0,length-fades[1]):.3f}:d={fades[1]:.3f}")
        chain.append("alimiter=limit=0.94")
        args=["-nostdin","-hide_banner","-loglevel","error","-y",
            "-i",str(file),"-af",",".join(chain),"-c:a","flac",
            "-sample_fmt","s32","-bits_per_raw_sample","24",str(target)]
        self._start_ffmpeg(args,target,"edit")

    def reset_project(self):
        """Cambiar de proyecto deja vacío el secuenciador, no arrastra ritmos."""
        self.apply_pattern_preset({})
        self.seq_bpm.setValue(120)
        self.seq_velocity.setValue(100)
        self.seq_swing.setValue(0)
        self.seq_bars.setCurrentIndex(2)
        self.edit_source.setCurrentIndex(0)
        self._last_editor_source=None
        self.apply_mix_preset({
            p:{"gain":0,"pan":0,"mute":False,"solo":False,
               "eq_low":0,"eq_mid":0,"eq_high":0} for p in PARTS})
        self.editor_presets.refresh()
        self.mixer_presets.refresh()
        self.pattern_presets.refresh()

    def close(self):
        if self.process is not None:
            self.process.kill()
            self.process.waitForFinished(2500)
        super().close()
