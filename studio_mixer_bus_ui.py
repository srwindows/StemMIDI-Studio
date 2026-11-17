"""Controles visuales propios de los buses de la pestaña Mezclador."""
import math
from pathlib import Path
from PySide6.QtCore import Qt,QSignalBlocker,QPointF,QRectF
from PySide6.QtGui import QColor,QPainter,QPen,QRadialGradient,QFont
from PySide6.QtWidgets import (
    QWidget,QFrame,QDial,QTabWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QSlider,QListWidget,QPushButton,QComboBox,QFileDialog,QMessageBox,QMenu,
    QSizePolicy,QInputDialog,QDialog,QScrollArea,QFormLayout,QDoubleSpinBox,
    QDialogButtonBox
)
from studio_mixer_bus_fx import BUS_DEFAULT


class PanBalanceDial(QDial):
    """Potenciómetro de paneo de 180º, con centro en 0 y sin giro continuo."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("mixerTabPan180")
        self.setRange(-100,100)
        self.setWrapping(False)
        self.setNotchesVisible(False)
        self._start_y=0.
        self._start_value=0
        self.setToolTip("Balance estéreo · L100 a R100 · doble clic: centro")
        self.setCursor(Qt.PointingHandCursor)

    def setFixedSize(self,w,h):
        # Permitir etiquetas L / R y cinco marcas sin alterar su altura
        # proporcional respecto al dial original.
        super().setFixedSize(max(38,w),round(h*1.25))

    def paintEvent(self,event):
        p=QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            w,h=self.width(),self.height()
            cx=w/2.
            cy=h*.51
            radius=min((w-10)*.42,(h-5)*.44)
            halo=QRectF(cx-radius,cy-radius,2*radius,2*radius)
            p.setPen(QPen(QColor("#071626"),1.5))
            p.setBrush(QColor("#051321"))
            p.drawEllipse(halo)
            grad=QRadialGradient(cx-radius*.3,cy-radius*.5,radius*2.)
            grad.setColorAt(0,QColor("#97b7ca"))
            grad.setColorAt(.3,QColor("#496f83"))
            grad.setColorAt(.82,QColor("#132a3e"))
            grad.setColorAt(1,QColor("#06131d"))
            p.setPen(QPen(QColor("#7899aa"),.8))
            p.setBrush(grad)
            p.drawEllipse(halo)
            # Escala solo semicírculo SUPERIOR: L=-100 (180º),
            # C=0 (90º), R=+100 (0º), sin envoltura de 360º.
            ring=QRectF(cx-radius-2.5,cy-radius-2.5,2*radius+5,2*radius+5)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#355467"),1.6,Qt.SolidLine,Qt.RoundCap))
            p.drawArc(ring,0,180*16)
            value=self.value()
            angle=90.-value*.9
            if value:
                p.setPen(QPen(QColor("#3beed7"),2.5,Qt.SolidLine,Qt.RoundCap))
                p.drawArc(ring,90*16,round((angle-90.)*16))
            for tick in (-100,-50,0,50,100):
                theta=math.radians(90.-tick*.9)
                inner=radius+3.8
                outer=inner+(3 if tick==0 else 2)
                p.setPen(QPen(QColor("#efffff") if tick==0
                              else QColor("#79afc0"),
                              1.1 if tick==0 else .7))
                p.drawLine(QPointF(cx+math.cos(theta)*inner,
                                   cy-math.sin(theta)*inner),
                           QPointF(cx+math.cos(theta)*outer,
                                   cy-math.sin(theta)*outer))
            theta=math.radians(angle)
            tip=QPointF(cx+math.cos(theta)*radius*.73,
                        cy-math.sin(theta)*radius*.73)
            p.setPen(QPen(QColor("#f5fcff"),1.9,Qt.SolidLine,Qt.RoundCap))
            p.drawLine(QPointF(cx,cy),tip)
            p.setPen(QColor("#d0fcff"))
            font=QFont("Sans",7)
            font.setBold(True)
            p.setFont(font)
            p.drawText(QRectF(0,h-9,8,8),Qt.AlignLeft|Qt.AlignVCenter,"L")
            p.drawText(QRectF(w-8,h-9,8,8),Qt.AlignRight|Qt.AlignVCenter,"R")
        finally:
            p.end()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self._start_y=event.position().y()
            self._start_value=self.value()
            self.grabMouse()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton:
            changed=round((self._start_y-event.position().y())*2.0)
            self.setValue(max(-100,min(100,self._start_value+changed)))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.releaseMouse()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self,event):
        self.setValue(0)
        event.accept()


class BusInspector(QTabWidget):
    """EQ/FX/DIN y efectos internos insertados sobre el BUS seleccionado, no la pista."""
    def __init__(self,presentation,parent=None):
        super().__init__(parent)
        self.pres=presentation
        self.host=presentation.bus_fx
        self.setObjectName("mixerBusInspector")
        self.setStyleSheet("""
        QTabWidget::pane{border:1px solid #396481;background:#081c2d;}
        QTabBar::tab{color:#cdeefa;background:#163549;
            border:1px solid #3f6a86;min-width:35px;padding:4px 3px;}
        QTabBar::tab:selected{background:#17618c;color:#ffffff;}
        QLabel{color:#c7e8f6;font-size:9px;}
        QSlider::groove:horizontal{height:5px;background:#071725;}
        QSlider::sub-page:horizontal{background:#45dce0;}
        """)
        self.controls={}
        for caption,definitions in (
          ("EQ",(
             ("low","Graves", -120,120,10),
             ("mid","Medios",-120,120,10),
             ("high","Agudos",-120,120,10))),
          ("FX",(
             ("reverb","Reverb",0,100,100),
             ("delay","Delay",0,100,100),
             ("delay_ms","Tiempo",50,1400,1),
             ("feedback","Feedback",0,90,100))),
          ("DIN",(
             ("gate","Gate",0,100,100),
             ("compress","Compresión",0,100,100),
             ("saturation","Saturación",0,100,100)))):
            page=QWidget(self)
            layout=QVBoxLayout(page)
            layout.setContentsMargins(4,3,4,3)
            layout.setSpacing(1)
            for key,title,minimum,maximum,scale in definitions:
                row=QHBoxLayout()
                row.setSpacing(3)
                label=QLabel(title,page)
                label.setFixedWidth(52)
                row.addWidget(label)
                slider=QSlider(Qt.Horizontal,page)
                slider.setRange(minimum,maximum)
                slider.setToolTip(f"{title} del BUS seleccionado")
                slider.valueChanged.connect(
                    lambda value,k=key,m=scale:self._set_param(k,value/m))
                row.addWidget(slider,1)
                value=QLabel("0",page)
                value.setFixedWidth(30)
                row.addWidget(value)
                layout.addLayout(row)
                self.controls[key]=(slider,value,scale)
            layout.addStretch(1)
            self.addTab(page,caption)

        plugin_page=QWidget(self)
        pc=QVBoxLayout(plugin_page)
        pc.setContentsMargins(3,3,3,3)
        pc.setSpacing(3)
        self.plugin_list=QListWidget(plugin_page)
        self.plugin_list.setFixedHeight(44)
        self.plugin_list.setStyleSheet("""
          QListWidget{color:#d8f7ff;background:#091f31;
             border:1px solid #3c708d;selection-background-color:#1d779e;}
          QListWidget::item{min-height:17px;padding:2px 4px;}
        """)
        self.plugin_list.setToolTip("Cadena de plugins del bus, en orden de señal")
        pc.addWidget(self.plugin_list,1)
        add=QHBoxLayout();add.setSpacing(3)
        self.kind=QComboBox(plugin_page)
        self.kind.addItems(["Reverb","Delay","Compresor","Sample Delay","Channel EQ"])
        self.kind.setMinimumWidth(50)
        self.kind.setToolTip("Efecto integrado")
        add.addWidget(self.kind,1)
        self.add_builtin=QPushButton("+",plugin_page)
        self.add_builtin.setToolTip("Añadir efecto integrado")
        self.add_builtin.clicked.connect(self._add_builtin)
        add.addWidget(self.add_builtin)
        pc.addLayout(add)
        actions=QHBoxLayout();actions.setSpacing(2)
        for text,tip,slot in [
            ("↑","Subir efecto en la cadena",lambda:self._move(-1)),
            ("↓","Bajar efecto en la cadena",lambda:self._move(1)),
            ("Editar","Abrir editor del plugin",self._edit),
            ("×","Quitar efecto del bus",self._remove)]:
            button=QPushButton(text,plugin_page)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            actions.addWidget(button,1)
        pc.addLayout(actions)
        self.addTab(plugin_page,"PLUG")
        self.setMinimumHeight(140)
        self.setMaximumHeight(180)
        self.refresh_bus(1)

    def bus(self):
        return int(self.pres.console.bus_select.currentData() or 1)

    def _set_param(self,name,value):
        if not self.pres.active:
            return
        bus=self.bus()
        self.host.set_control(bus,name,value)
        entry=self.controls[name]
        entry[1].setText(f"{value:.1f}" if name in ("low","mid","high")
                         else f"{round(value)}" if name=="delay_ms"
                         else f"{value:.2f}")

    def refresh_bus(self,bus):
        bus=int(bus)
        params=self.host.controls[bus]
        for key,(slider,text,scale) in self.controls.items():
            val=params[key]
            with QSignalBlocker(slider):
                slider.setValue(round(val*scale))
            text.setText(f"{val:.1f}" if key in ("low","mid","high")
                         else f"{int(val)}" if key=="delay_ms"
                         else f"{val:.2f}")
        self.refresh_plugins()

    def refresh_plugins(self):
        bus=self.bus()
        selected=self.plugin_list.currentRow()
        self.plugin_list.clear()
        for slot in self.host.plugins[bus]:
            text=f"{'OFF ' if slot.bypass else ''}{slot.name}"
            self.plugin_list.addItem(text)
        if self.plugin_list.count():
            self.plugin_list.setCurrentRow(min(max(0,selected),
                                               self.plugin_list.count()-1))
        if self.pres.active and hasattr(self.pres,"_bus_fx_list"):
            self.pres._refresh_bus_fx_strip()

    def _add_builtin(self):
        try:
            self.host.make_builtin(self.bus(),self.kind.currentText())
            self.refresh_plugins()
        except (RuntimeError,ValueError) as ex:
            QMessageBox.warning(self,"Plugin",str(ex))

    def _move(self,n):
        index=self.plugin_list.currentRow()
        bus=self.bus()
        self.host.reorder(bus,index,n)
        self.refresh_plugins()
        self.plugin_list.setCurrentRow(max(0,index+n))

    def _bypass(self):
        index=self.plugin_list.currentRow()
        if index>=0:
            self.host.toggle_bypass(self.bus(),index)
            self.refresh_plugins()

    def _remove(self):
        index=self.plugin_list.currentRow()
        if index>=0:
            self.host.remove(self.bus(),index)
            self.refresh_plugins()

    def _create_parameter_editor(self,slot):
        dialog=QDialog(self)
        dialog.setWindowTitle(f"Plugin · {slot.name} · BUS {self.bus():02d}")
        dialog.resize(630,640) if slot.name=="Channel EQ" else (
            dialog.resize(500,490) if slot.name=="Reverb" else dialog.resize(420,370))
        root=QVBoxLayout(dialog)
        note=QLabel("Los cambios actúan en el bus seleccionado mientras suena.")
        note.setWordWrap(True)
        root.addWidget(note)
        scroll=QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        page=QWidget(scroll)
        form=QFormLayout(page)
        form.setContentsMargins(8,8,8,8)
        form.setSpacing(8)
        plugin=slot.plugin
        if slot.name=="Channel EQ":
            from channel_eq_controls import ChannelEQControls
            form.addRow(ChannelEQControls(plugin,page))
        elif slot.name=="Sample Delay":
            from sample_delay_controls import SampleDelayControls
            form.addRow(SampleDelayControls(plugin,page))
        elif slot.name=="Reverb":
            from stemmidi_reverb_controls import ReverbControls
            form.addRow(ReverbControls(plugin,page))
        elif hasattr(plugin,"parameters"):
            for key,parameter in plugin.parameters.items():
                row=QHBoxLayout()
                slider=QSlider(Qt.Horizontal,page)
                slider.setRange(0,1000)
                slider.setValue(round(float(parameter.raw_value)*1000))
                value=QLabel(str(parameter),page)
                value.setMinimumWidth(60)
                def apply(raw,par=parameter,readout=value):
                    try:
                        par.raw_value=raw/1000.
                        readout.setText(str(par).split("value=")[-1][:34])
                    except (ValueError,RuntimeError):
                        pass
                slider.valueChanged.connect(apply)
                row.addWidget(slider,1)
                row.addWidget(value,0)
                form.addRow(key.replace("_"," ").title(),row)
        else:
            fields={
                "Reverb":{"room_size":(0.,1.),"damping":(0.,1.),
                          "wet_level":(0.,1.),"dry_level":(0.,1.),
                          "width":(0.,1.)},
                "Delay":{"delay_seconds":(.01,1.4),"feedback":(0.,.94),
                         "mix":(0.,1.)},
                "Compresor":{"threshold_db":(-60.,0.),"ratio":(1.,20.),
                             "attack_ms":(.1,100.),"release_ms":(10.,1000.)}
            }.get(slot.name,{})
            for key,(minimum,maximum) in fields.items():
                slider=QSlider(Qt.Horizontal,page)
                slider.setRange(0,1000)
                initial=float(getattr(plugin,key))
                slider.setValue(round(1000*(initial-minimum)/(maximum-minimum)))
                text=QLabel(f"{initial:.2f}",page)
                row=QHBoxLayout();row.addWidget(slider,1);row.addWidget(text)
                def apply(raw,k=key,a=minimum,b=maximum,readout=text):
                    value=a+(b-a)*raw/1000.
                    try:
                        setattr(plugin,k,value)
                        readout.setText(f"{value:.2f}")
                    except (ValueError,RuntimeError):
                        pass
                slider.valueChanged.connect(apply)
                form.addRow(key.replace("_"," ").title(),row)
        scroll.setWidget(page)
        root.addWidget(scroll,1)
        editor=getattr(plugin,"show_editor",None)
        if callable(editor):
            native=QPushButton("Abrir interfaz original del plugin",dialog)
            def open_native():
                try:editor()
                except (RuntimeError,ValueError) as error:
                    QMessageBox.warning(dialog,"Plugin",str(error))
            native.clicked.connect(open_native)
            root.addWidget(native)
        buttons=QDialogButtonBox(QDialogButtonBox.Close,parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        root.addWidget(buttons)
        return dialog

    def _edit(self):
        index=self.plugin_list.currentRow()
        slots=self.host.plugins[self.bus()]
        if not 0<=index<len(slots):return
        dlg=self._create_parameter_editor(slots[index])
        dlg.exec()
