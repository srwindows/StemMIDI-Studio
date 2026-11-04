"""Cabecera y tema visual de StemMIDI Studio: nueva identidad unificada."""
from __future__ import annotations
import file_dialogs
import json, os, math
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient, QFont, QPainterPath, QRadialGradient
from PySide6.QtWidgets import (
    QWidget,QHBoxLayout,QVBoxLayout,QLabel,QFrame,QPushButton,QTabWidget,
    QFileDialog,QMessageBox,QDialog,QFormLayout,QComboBox,QCheckBox
)
from studio_home import StudioHome,BrandLogo

STYLE_STUDIO="""
* {font-family:'Noto Sans', 'DejaVu Sans',sans-serif; font-size:13px; color:#e0f8ff;}
QMainWindow,QWidget#main, QWidget#studioHomePage,
QDialog, QScrollArea, QScrollArea>QWidget>QWidget {
    background:#031330; color:#e0f8ff;}
QWidget#studioHome {background:#031330;}
QLabel {color:#e0f8ff;}
QLabel#muted,QLabel#homeLabel {color:#e0f8ff;}
QLabel#status {color:#85f0ff; font-weight:650;}
QLabel#section {font-size:14px;font-weight:700;color:#e0f8ff;}
QLabel#title {font-size:23px;font-weight:800;color:#e0f8ff;}
QLabel#bigtime {font-size:25px;font-weight:750;color:#e0f8ff;}
QLabel#mixValue {font-size:10px;color:#e0f8ff;background:#031536;
 border:1px solid #29a9f1;border-radius:4px;padding:2px 1px;}
QFrame#studioCard,QFrame#panel {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #041b43,stop:1 #031535);
    border:1px solid #2bb1fc;border-radius:9px;}
QFrame#inner {background:#041a41;border:1px solid #2bb1fc;border-radius:7px;}
QPushButton#studioCardHeading {
    text-align:left;padding:4px 11px;border:0;
    border-bottom:1px solid #2bb1fc;border-radius:6px 6px 0 0;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0a3f9e,stop:1 #041b44);
    color:#e0f8ff;font-size:15px;font-weight:750;min-height:27px;}
QPushButton#studioCardHeading:hover {color:white;background:#093a92;}
QPushButton {background:#052154;border:1px solid #2bb1fc;
  border-radius:5px;color:#e0f8ff;font-weight:600;
  padding:4px 8px;min-height:18px;}
QPushButton:hover {background:#0a44ab;border-color:#26b9ed;}
QPushButton:pressed {background:#083585;}
QPushButton:disabled {background:#041c45;color:#a3e4f0;border-color:#228ecb;}
QPushButton#primary {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #05c9ed,stop:1 #0d59e0);
    border:1px solid #11dff9;color:#e0f8ff;font-size:13px;font-weight:800;
    min-height:24px;}
QPushButton#primary:hover {background:#1599d9;border-color:#88f4ff;}
QPushButton#primary:disabled {
    background:#052052;border:1px solid #28a6ec;color:#a3e4f0;}
QPushButton#record {background:#e93447;border:1px solid #fa5b66;color:white;}
QPushButton#stop {background:#b7284a;border:1px solid #e64a63;}
QPushButton#cardHelpButton {
    min-width:27px;max-width:27px;min-height:30px;max-height:30px;
    border:1px solid #2bb1fc;background:#041c48;color:#85f0ff;
    border-radius:3px;font-size:17px;font-weight:800;padding:0px;}
QPushButton#cardHelpButton:hover {
    background:#0d53d2;color:white;border:1px solid #46dcff;}
QPushButton#studioToolbar {background:transparent;border:0;
    color:#e0f8ff;font-size:12px;padding:0px;
    min-height:83px;max-height:83px;}
QPushButton#studioToolbar:hover {background:#093991;color:white;}
QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox {
    background:#041a41;border:1px solid #2bb1fc;border-radius:5px;
    color:#e0f8ff;padding:4px 5px;min-height:20px;}
QComboBox:hover,QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus {border-color:#41d6fb;}
QComboBox::drop-down {border:0;width:20px;}
QComboBox QAbstractItemView {background:#051e4c;color:#e0f8ff;
   selection-background-color:#2bb1fc;}
QTabWidget::pane {background:#031434;border:0;top:-1px;}
QTabBar::tab {background:#04193f;color:#e0f8ff;
    border:1px solid #2bb1fc;border-bottom:1px solid #2bb1fc;
    padding:13px 10px;margin-right:1px;font-weight:700;font-size:14px;min-height:23px;}
QTabBar::tab:selected {color:white;background:#0c4fc8;border-color:#0ed2f7;
    border-bottom:1px solid #2bb1fc;}
QTabBar::tab:hover:!selected {background:#093991;color:white;}
QCheckBox {color:#e0f8ff;spacing:6px;}
QCheckBox::indicator {width:14px;height:14px;}
QCheckBox::indicator:checked {background:#00a7ea;border:1px solid #54edff;}
QSlider::groove:horizontal {background:#083687;border-radius:3px;height:5px;}
QSlider::sub-page:horizontal {background:#168ecd;border-radius:3px;}
QSlider::handle:horizontal {background:#74e6ff;border:1px solid #d2ffff;
    width:13px;height:13px;margin:-5px 0;border-radius:7px;}
QSlider::groove:vertical {background:#083382;border-radius:3px;width:6px;}
QSlider::sub-page:vertical {background:#178bdb;}
QSlider::handle:vertical {background:#a8dfff;border:1px solid #e7ffff;
    height:16px;margin:0 -7px;border-radius:3px;}
QTableWidget,QTreeWidget {
  background:#031739;color:#e0f8ff;alternate-background-color:#051e4c;
  border:1px solid #2bb1fc;gridline-color:#a3cad6;selection-background-color:#2bb1fc;}
QTableWidget::item {padding:3px;}
QTreeWidget::item {padding:5px;}
QHeaderView::section {background:#083483;color:#e0f8ff;
   padding:4px;border:0;border-right:1px solid #2bb1fc;}
QScrollBar:vertical {background:#031739;width:9px;}
QScrollBar::handle:vertical {background:#0b49b9;border-radius:4px;}
QScrollBar:horizontal {background:#031739;height:9px;}
QScrollBar::handle:horizontal {background:#0b49b9;border-radius:4px;}
QPlainTextEdit {background:#04183c;color:#e0f8ff;border:1px solid #2bb1fc;
   border-radius:5px;font-family:'DejaVu Sans Mono';font-size:10px;}
QGraphicsView {background:#031637;border:1px solid #2bb1fc;}
QProgressBar {background:#041e4b;color:white;border:1px solid #2bb1fc;
    border-radius:5px;height:9px;}
QProgressBar::chunk {background:#03bae4;border-radius:4px;}
QSplitter::handle {background:#0a41a3;width:4px;}
QPushButton#studioWindowControl {
    background:#031330; border:1px solid #2bb1fc;
    border-radius:5px; color:#85f0ff;font-size:19px;padding:0px;}
QPushButton#studioWindowControl:hover {background:#0b48b4;}
QPushButton#studioCloseControl {
    background:#031330; border:1px solid #27a3e8;
    border-radius:5px;color:#ff6478;font-size:23px;padding:0px;}
QPushButton#studioCloseControl:hover {background:#a6213c;color:white;}
QMenu {background:#041b45;color:#e0f8ff;border:1px solid #2bb1fc;padding:4px;}
QMenu::item {padding:7px 18px;}
QMenu::item:selected {background:#0d59e0;}
QToolTip {background:#051e4c;color:#e0f8ff;border:1px solid #2bb1fc;
  border-radius:5px;padding:7px 9px;font-size:12px;}

/* Lenguaje gráfico común de Inicio: paneles metálicos y títulos luminosos.
   Los módulos antiguos no usaban cabeceras, grupos ni separadores propios. */
QWidget#monitorCanvas,QWidget#studioModuleSurface,
QWidget#vocalTuneModule {
  background:#031330;color:#e0f8ff;
}
QLabel#title {
  background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
     stop:0 #093e9c,stop:.45 #051e4c,stop:1 #031535);
  border-left:3px solid #15c7ed;
  border-bottom:1px solid #2bb1fc;
  border-radius:4px;
  color:#e0f8ff;font-weight:800;
  padding:3px 9px;
  min-height:22px;
}
QLabel#section {
  color:#e0f8ff;
  font-weight:750;
}
QGroupBox {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
     stop:0 #052050,stop:1 #03173a);
  color:#e0f8ff;
  font-weight:750;
  border:1px solid #2bb1fc;
  border-radius:7px;
  margin-top:10px;
  padding-top:8px;
}
QGroupBox::title {
  subcontrol-origin:margin;
  subcontrol-position:top left;
  left:9px;
  padding:0 5px;
  color:#85f0ff;
  background:#052050;
}
QSplitter {background:#031330;border:0;}
QSplitter::handle {background:#0c4dc3;}
QTabWidget#labSections::pane {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
      stop:0 #052051,stop:1 #04183b);
  border:1px solid #2bb1fc;
  border-radius:4px;
}
QTabWidget#labSections QTabBar::tab {
  padding:6px 10px;
  min-height:17px;
  font-size:12px;
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
     stop:0 #083381,stop:1 #041c45);
  border:1px solid #2bb1fc;
}
QTabWidget#labSections QTabBar::tab:selected {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
     stop:0 #0d59e0,stop:1 #0c4ec6);
  border:1px solid #25c6ef;
}
QFrame#panel QLabel#homeLabel {color:#e0f8ff;}
QFrame#inner,QWidget#studioModuleSurface {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #051f4d,stop:1 #031638);
}
/* Tarjetas verdaderas con cabeceras equivalentes a Inicio. */
QFrame#studioCard {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #051e4c,stop:.45 #041a41,stop:1 #031535);
  border:1px solid #2bb1fc;
  border-radius:8px;
}
QFrame#moduleCardBanner {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #0b46b1,stop:.55 #093a92,stop:1 #051e4c);
  border:0;
  border-bottom:1px solid #159de2;
  border-radius:6px 6px 0 0;
  min-height:30px;
  max-height:30px;
}
QLabel#moduleCardHeading {
  color:#e0f8ff;
  font-size:14px;
  font-weight:800;
  background:transparent;
}
QLabel#moduleCardIcon {background:transparent;}
QLabel#moduleEmptyState {
  color:#e0f8ff;
  font-size:15px;
  font-weight:700;
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #052050,stop:1 #04183e);
  border:1px dashed #2bb1fc;
  border-radius:9px;
  padding:15px;
}
QLabel#moduleWorkflowNote {
  color:#e0f8ff;
  font-size:14px;
  line-height:1.2;
  padding:12px;
  background:#041c46;
  border:1px solid #2bb1fc;
  border-radius:5px;
}
QWidget#moduleResultZone {background:transparent;}
"""

class ToolbarButton(QPushButton):
    def __init__(self,icon,text,callback,parent=None):
        super().__init__("",parent)
        self.setObjectName("studioToolbar")
        self.setFixedWidth(98)
        self.setFixedHeight(87)
        symbol=QLabel(self)
        symbol.setAlignment(Qt.AlignCenter)
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPixmap
        kinds={"＋":"new","◫":"presets","▱":"open","▣":"save",
               "✕":"close","⚙":"settings","ⓘ":"help","◎":"info"}
        renderer=QSvgRenderer(str(Path(__file__).resolve().parent/"assets"/
                   f"toolbar_{kinds.get(icon,'info')}.svg"))
        picture=QPixmap(39,39)
        picture.fill(Qt.transparent)
        painter=QPainter(picture)
        renderer.render(painter)
        painter.end()
        symbol.setPixmap(picture)
        symbol.setAttribute(Qt.WA_TransparentForMouseEvents)
        caption=QLabel(text,self)
        caption.setAlignment(Qt.AlignCenter)
        caption.setStyleSheet("font-size:11px;font-weight:600;color:#e0f8ff;")
        caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        # Geometría absoluta DENTRO del botón: Qt dejaba colisionar
        # el SVG y el rótulo al redistribuir la altura del QVBoxLayout.
        symbol.setGeometry(29,6,40,47)
        caption.setWordWrap(True)
        caption.setGeometry(0,57,98,27)
        self._symbol=symbol
        self._caption=caption
        self.clicked.connect(callback)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._symbol.setGeometry((self.width()-40)//2,6,40,47)
        self._caption.setGeometry(0,55,self.width(),30)

class ProfessionalHelpButton(QPushButton):
    """Interruptor de ayuda: signo ? y LED real ON/OFF (no decorativo)."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("professionalHelpToggle")
        self.setFixedSize(88,87)
        self.setCheckable(True)
        self.setAccessibleName("Activar o desactivar las ayudas contextuales")
        self.setToolTip("Ayuda profesional: pulsar activa o desactiva todas "
                        "las explicaciones del ratón. LED verde: activada; "
                        "LED gris: desactivada.")
        self._manager=None
        self.toggled.connect(self._toggle_help)

    def bind(self,manager):
        self._manager=manager
        before=self.blockSignals(True)
        self.setChecked(manager.enabled)
        self.blockSignals(before)
        self.update()

    def _toggle_help(self,checked):
        if self._manager is not None:
            self._manager.set_enabled(bool(checked))
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing,True)
        p.setPen(QPen(QColor("#2d89b7"),1))
        p.setBrush(QColor("#113f62") if self.isChecked() else QColor("#071f36"))
        p.drawRoundedRect(self.rect().adjusted(3,3,-3,-3),7,7)
        p.setBrush(QColor("#082638"))
        p.setPen(QPen(QColor("#64d7ff"),2))
        x=(self.width()-36)//2
        p.drawEllipse(x,9,36,36)
        font=QFont(self.font());font.setPixelSize(27);font.setBold(True)
        p.setFont(font);p.setPen(QColor("#f5fdff"))
        p.drawText(QRectF(x,10,36,33),Qt.AlignCenter,"?")
        led=QColor("#38ff8b") if self.isChecked() else QColor("#536879")
        p.setBrush(led)
        p.setPen(QPen(QColor("#c4ffe0") if self.isChecked()
                      else QColor("#708398"),1))
        p.drawEllipse(self.width()-21,13,12,12)
        font.setPixelSize(11);font.setBold(True);p.setFont(font)
        p.setPen(QColor("#e6f9ff"))
        p.drawText(QRectF(2,60,self.width()-4,20),Qt.AlignCenter,
                   "Ayuda ON" if self.isChecked() else "Ayuda OFF")
        p.end()


class StudioHeader(QFrame):
    def __init__(self,main):
        super().__init__(main)
        self.main=main
        self.setFixedHeight(146)
        row=QHBoxLayout(self)
        row.setContentsMargins(7,1,12,1)
        row.setSpacing(12)
        self.logo=BrandLogo()
        row.addWidget(self.logo,0,Qt.AlignVCenter)
        self.text_panel=QWidget(self)
        self.text_panel.setMinimumWidth(0)
        textcol=QVBoxLayout(self.text_panel)
        textcol.setContentsMargins(0,0,0,0)
        textcol.setSpacing(5)
        textcol.addSpacing(3)
        heading=QLabel('<span style="color:#e0f8ff">Stem</span>'
            '<span style="color:#85f0ff">MIDI</span> '
            '<span style="color:#e0f8ff">Studio</span>')
        heading.setTextFormat(Qt.RichText)
        heading.setStyleSheet('font-size:49px;font-weight:900;')
        heading.setWordWrap(True)
        self.heading=heading
        textcol.addWidget(heading)
        subject=QLabel("Separación de instrumentos   •   Transcripción de audio a MIDI   •   Grabación y mezcla")
        subject.setStyleSheet("font-size:13px;color:#e0f8ff;")
        subject.setWordWrap(True)
        textcol.addWidget(subject)
        creed=QLabel("Libre para usar, estudiar y mejorar. Hecho para compartir, no para lucrarse con el código.")
        creed.setStyleSheet("font-size:13px;color:#85f0ff;")
        creed.setWordWrap(True)
        textcol.addWidget(creed)
        textcol.addStretch(1)
        row.addWidget(self.text_panel,1)
        actions=QHBoxLayout()
        actions.setSpacing(4)
        self.toolbar_buttons=[]
        for icon,title,handler in [
            ("＋","Nuevo proyecto",lambda:__import__(
                "project_flow").new_project_dialog(main,inherit_settings=True)),
            ("▱","Abrir proyecto",lambda:open_project(main)),
            ("◫","Ajustes guardados",lambda:__import__(
                "studio_settings_library").settings_dialog(main)),
            ("▣","Guardar ▾",lambda:self._save_menu()),
            ("✕","Cerrar proyecto",lambda:close_project(main)),
            ("⚙","Preferencias",lambda:preferences(main)),
            ("ⓘ","Ayuda",lambda:help_dialog(main)),
            ("◎","Acerca de",lambda:about_dialog(main))]:
            button=ToolbarButton(icon,title,handler,self)
            if title=="Guardar ▾":
                button.setToolTip(
                    "Guardar, Guardar proyecto como… o revertir desde backup. "
                    "Abre el menú y elige la operación.")
            actions.addWidget(button)
            self.toolbar_buttons.append(button)
            if title=="Abrir proyecto":
                # Siempre inmediatamente a la derecha de Abrir proyecto.
                self.help_toggle=ProfessionalHelpButton(self)
                actions.addWidget(self.help_toggle)
        row.addLayout(actions)
        row.setAlignment(actions,Qt.AlignBottom)
        self.win_controls=[]
        for title,tooltip,callback,name in (
            ("−","Minimizar",self.main.showMinimized,"studioWindowControl"),
            ("□","Maximizar / Restaurar",self.toggle_maximized,"studioWindowControl"),
            ("×","Cerrar StemMIDI Studio",self.main.close,"studioCloseControl")):
            btn=QPushButton(title,self)
            btn.setObjectName(name)
            btn.setFixedSize(29,24)
            btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            btn.raise_()
            self.win_controls.append(btn)

    def _save_menu(self):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        menu=QMenu(self)
        action_save=menu.addAction("Guardar proyecto · sobrescribir estado")
        action_as=menu.addAction("Guardar proyecto como…")
        menu.addSeparator()
        action_restore=menu.addAction("Revertir desde backup…")
        chosen=menu.exec(QCursor.pos())
        if chosen is action_save:save_project(self.main)
        elif chosen is action_as:save_project_as(self.main)
        elif chosen is action_restore:revert_project_backup(self.main)

    def toggle_maximized(self):
        if self.main.isMaximized():self.main.showNormal()
        else:self.main.showMaximized()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        # Mantener accesibles los nuevos botones Proyecto y Biblioteca
        # incluso en pantallas pequeñas, sin solaparse con el título.
        width=self.width()
        title_px=(29 if width<=1130 else
                  34 if width<=1240 else
                  40 if width<=1380 else 49)
        desired_title=f"font-size:{title_px}px;font-weight:900;"
        if self.heading.styleSheet()!=desired_title:
            self.heading.setStyleSheet(desired_title)
        button_width=(58 if width<=1130 else
                      67 if width<=1240 else
                      78 if width<=1380 else 90)
        help_width=(56 if width<=1130 else
                    64 if width<=1240 else 72 if width<=1380 else 82)
        for button in self.toolbar_buttons:
            if button.width()!=button_width:
                button.setFixedWidth(button_width)
        if self.help_toggle.width()!=help_width:
            self.help_toggle.setFixedWidth(help_width)
        for i,btn in enumerate(self.win_controls):
            btn.move(self.width()-111+37*i,7)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing,True)
        w=float(self.width())
        gradient=QLinearGradient(0,0,0,146)
        gradient.setColorAt(0,QColor("#020c1e"))
        gradient.setColorAt(.55,QColor("#05162d"))
        gradient.setColorAt(1,QColor("#03182b"))
        p.fillRect(self.rect(),QBrush(gradient))
        # Forma de onda de la MARCA: decorativa, NO un medidor de entrada.
        start_x=max(600,int(w*.33))
        width=max(1,int(w-start_x-12))
        # Haz azul en la sección central y violeta hacia el extremo derecho.
        for k in range(0,width,3):
            x=start_x+k
            t=k/width
            envelope=(5+23*math.exp(-((t-.10)/.07)**2)
                      +37*math.exp(-((t-.33)/.10)**2)
                      +47*math.exp(-((t-.66)/.09)**2)
                      +31*math.exp(-((t-.82)/.09)**2))
            carrier=(.64*math.sin(t*120*math.pi)
                     +.25*math.sin(t*39*math.pi)
                     +.11*math.sin(t*265*math.pi))
            amplitude=envelope*abs(carrier)
            if t<.50:
                color=QColor("#067fe5") if t<.20 else QColor("#02bcfa")
            elif t<.72:color=QColor("#1e9cff")
            elif t<.87:color=QColor("#762cff")
            else:color=QColor("#4b5cfb")
            color.setAlpha(55)
            p.setPen(QPen(color,8,Qt.SolidLine,Qt.RoundCap))
            p.drawLine(x,int(58-amplitude),x,int(58+amplitude))
            color.setAlpha(215)
            p.setPen(QPen(color,2,Qt.SolidLine,Qt.RoundCap))
            p.drawLine(x,int(58-amplitude),x,int(58+amplitude))
        # Línea oscilante azul/violeta que se disuelve por los lados.
        for phase,rgba in ((0,QColor(0,122,235,100)),(1.7,QColor(87,44,232,115))):
            curve=QPainterPath()
            for j in range(start_x,int(w),3):
                t=(j-start_x)/width
                y=58+15*math.sin(t*12*math.pi+phase)*math.sin(t*math.pi)
                if j==start_x:curve.moveTo(j,y)
                else:curve.lineTo(j,y)
            p.setPen(QPen(rgba,1))
            p.drawPath(curve)
        # Separador inferior horizontal, acorde a la maqueta.
        p.setPen(QPen(QColor("#086d9f"),1))
        p.drawLine(0,145,int(w),145)
        # Oscurecer el fondo de los accesos para mantener contraste con onda.
        glass=QLinearGradient(0,74,0,146)
        glass.setColorAt(0,QColor(4,18,31,0))
        glass.setColorAt(1,QColor(3,12,24,238))
        p.fillRect(QRectF(max(0,w-590),70,min(590,w),74),QBrush(glass))
        p.end()

def project_payload(main):
    w=main.workbench
    home=main.studio_home
    return {
      "version":2,"application":"StemMIDI Studio",
      "project_layout_version": (4 if
          __import__("project_layout").layout_active(
              getattr(main,"project_dir",None)) else 1),
      "project_id":main.project_id,
      "project_name":str(getattr(main,"project_name",None) or ""),
      "project_dir":str(getattr(main,"project_dir",None) or ""),
      "recordings":list(getattr(main,"project_recordings",[])),
      "source_recording":str(main.last_file) if main.last_file else "",
      "approved_stems":__import__("project_flow").approved_map(main),
      "approved_task":__import__("project_flow").approved_task(main),
      "source_separation":w.separator.file_edit.text(),
      "source_midi":w.converter.audio_path.text(),
      "selected_midi":str(home.selected_midi) if home.selected_midi else None,
      "record_format":main.format.currentText(),
      "drum_input":main.drum_module.input.text() if hasattr(main,"drum_module") else "",
      "drum_mix":main.drum_module.studio.snapshot_mix(),
      "drum_pattern":main.drum_module.studio.snapshot_pattern(),
      "drum_bpm":main.drum_module.studio.seq_bpm.value(),
      "drum_velocity":main.drum_module.studio.seq_velocity.value(),
      "drum_swing":main.drum_module.studio.seq_swing.value(),
      "drum_bars":main.drum_module.studio.seq_bars.currentData(),
      "vocal_input":main.vocal_module.input.text() if hasattr(main,"vocal_module") else "",
      "vocal_tonic":main.vocal_module.tonic.currentIndex() if hasattr(main,"vocal_module") else 0,
      "vocal_scale":main.vocal_module.scale.currentText() if hasattr(main,"vocal_module") else "Cromática",
      "vocal_strength":main.vocal_module.strength.value() if hasattr(main,"vocal_module") else 75,
      "vocal_preset":main.vocal_module.preset.currentText() if hasattr(main,"vocal_module") else "Estudio",
      "vocal_retune_ms":main.vocal_module.retune.value() if hasattr(main,"vocal_module") else 90,
      "vocal_humanize":main.vocal_module.humanize.value() if hasattr(main,"vocal_module") else 17,
      "vocal_threshold":main.vocal_module.threshold.value() if hasattr(main,"vocal_module") else 10,
      "vocal_compression":main.vocal_module.compression.value() if hasattr(main,"vocal_module") else 35,
      "vocal_highpass":main.vocal_module.highpass.value() if hasattr(main,"vocal_module") else 85,
      "vocal_character":main.vocal_module.character.currentText(),
      "vocal_character_amount":main.vocal_module.character_amount.value(),
      "vocal_warmth":main.vocal_module.warmth.value(),
      "vocal_air":main.vocal_module.air.value(),
      "vocal_presence":main.vocal_module.presence.value(),
      "vocal_deesser":main.vocal_module.deesser.value(),
      "vocal_gate":main.vocal_module.gate.value(),
      "vocal_reverb":main.vocal_module.reverb.value(),
      "vocal_wet":main.vocal_module.wet.value(),
      "vocal_doubler":main.vocal_module.doubler.value(),
      "vocal_delay":main.vocal_module.delay.value(),
      "vocal_delay_ms":main.vocal_module.delay_ms.value(),
      "vocal_stereo_width":main.vocal_module.stereo_width.value(),
      "vocal_output_gain_db":main.vocal_module.output_gain_db.value(),
      "vocal_bypass_tune":main.vocal_module.bypass_tune.isChecked(),
      "record_rate":main.capture_rate.currentData(),
      "input_gain_db":main.input_gain_db,
      "input_balance":main.input_balance,
      "device_input":main.sources.currentData(),
      "parameters_midi":w.converter.parameter_snapshot(),
      "parameters_separation":w.separator.parameter_snapshot(),
      "parameters_monitor":main.monitor_preset_snapshot(),
      "parameters_recording_lab":main.recording_lab.snapshot(),
      "recording_lab_original":str(main.recording_lab.original) if main.recording_lab.original else "",
      "recording_lab_processed":str(main.recording_lab.processed) if main.recording_lab.processed else "",
      "parameters_vocal_full":main.vocal_module.full_preset_snapshot(),
      "parameters_drum_editor":main.drum_module.studio.editor_presets.snapshot(),
      "parameters_drum_full":main.drum_module.snapshot_full_preset(),
      "parameters_piano_view":w.piano.view_snapshot(),
      "midi_editor_file":str(w.piano.current_path) if w.piano.current_path else "",
      "midi_source_folder":w.converter.folder_path.text(),
      "midi_use_folder":w.converter.use_folder.isChecked(),
      "vocal_reference":main.vocal_module.reference.text()
                         if main.vocal_module.ref_consent.isChecked() else "",
      "vocal_reference_authorized":main.vocal_module.ref_consent.isChecked(),
      "parameters_mixer":(w.mixer.preset_snapshot() if w.mixer else
          getattr(main,"_pending_mixer_preset",None)),
      "mixer_sources":[str(p) for p in w.mixer.sources] if w.mixer else [],
      "midi_files":[str(p) for p in w.midi_storage.items],
      "separated_files":[str(p) for p in w.separation_storage.items],
      "drum_files":[str(p) for p in w.drum_storage.items],
      "vocal_files":[str(p) for p in w.vocal_storage.items],
      "mixer_levels":{name:parts["fader"].value() for name,parts in home.mixer_rows.items()},
      "home_workspace":home.home_workspace.snapshot(),
      "stem_visibility":dict(home._stem_selection),
      "notice":"Las grabaciones y MIDI originales no se incluyen en este archivo."
    }

def save_project(main,show_confirmation=True):
    """Sobrescribe el MISMO .stemstudio.json, sin duplicar carpetas ni trabajos."""
    from project_flow import project_directory,atomic_json
    from project_session import prepare_payload
    project=project_directory(main)
    if not project:
        QMessageBox.information(main,"Guardar proyecto",
            "Crea o abre un proyecto con nombre para guardar todos sus archivos. "
            "También puedes usar «Guardar como…».")
        return False
    progress=None
    try:
        if main.recording or main.record_pending:
            raise ValueError("Finaliza la grabación antes de guardar el proyecto.")
        wb=main.workbench
        audio_converter=getattr(getattr(main,"studio_home",None),"midi_to_audio",None)
        if (wb.separator.busy or wb.converter.process is not None
                or main.drum_module.process is not None
                or main.vocal_module.process is not None
                or main.recording_lab.process is not None
                or (audio_converter is not None and audio_converter.busy)):
            raise ValueError("Espera a que termine el procesamiento activo.")
        # Contar los bytes físicos ANTES de copiar para calcular el
        # porcentaje sobre trabajo REAL, no sobre un QTimer.
        from project_transaction import commit_staged,commit_edited_midi,begin,_staged
        from project_progress import ProjectProgress
        staged=list(_staged(project))
        from safe_file_delete import pending_deletions
        deletion_total=len(pending_deletions(project))
        progress=ProjectProgress(main,"Guardando proyecto",
            steps=12+deletion_total,
            media_sizes=[path.stat().st_size for _,path in staged])
        progress.allow_cancel(True)
        progress.stage("Grabación y procesos comprobados")
        saved_prior={}
        if main.project_path and Path(main.project_path).is_file():
            try:
                saved_prior=json.loads(Path(main.project_path).read_text(
                    encoding="utf-8")).get("committed_outputs",{})
            except (OSError,ValueError,TypeError):
                saved_prior={}
        # Exportaciones individuales y Guardar proyecto comparten el
        # destino conocido: nunca duplicar como stem.mid / stem_2.mid.
        from task_staging import inside
        for store in (wb.separation_storage,wb.midi_storage,
                      wb.drum_storage,wb.vocal_storage):
            for source,target in store.saved_exports.items():
                source_path=Path(source)
                target_path=Path(target)
                if (inside(source_path,Path(project)/"temporales")
                    and inside(target_path,project)
                    and not inside(target_path,Path(project)/"temporales")
                    and target_path.is_file()):
                    saved_prior[source_path.relative_to(project).as_posix()]=(
                        target_path.relative_to(project).as_posix())
        progress.stage("Destinos y exportaciones anteriores identificados")
        promoted,commit_index=commit_staged(project,saved_prior,progress=progress)
        # Después de promover los archivos empieza la confirmación crítica
        # del manifiesto, Piano Roll y eliminaciones. No interrumpir a medias.
        progress.allow_cancel(False)
        progress.stage(f"{len(promoted)} medios procesados y verificados")
        # El Piano Roll guarda sobre el MISMO MIDI del proyecto, con una
        # sola copia recuperable en backup/MIDI_anterior.
        if wb.piano.dirty and wb.piano.midi is not None:
            commit_edited_midi(wb.piano,project)
        progress.stage("Ediciones del Piano Roll verificadas")
        path=Path(main.project_path) if main.project_path else (
            project/(__import__("project_flow").slug_name(main.project_name)+".stemstudio.json"))
        if path.parent.resolve()!=project.resolve():
            raise ValueError("El manifiesto debe permanecer dentro del proyecto.")
        progress.stage("Ubicación del manifiesto validada")
        from project_transaction import rebase_payload,finish_commit
        payload=prepare_payload(project,project_payload(main))
        payload=rebase_payload(payload,promoted,project)
        # El índice de medios debe reflejar lo guardado, no rutas temporales
        # que se retiran tras confirmar la operación.
        if isinstance(payload.get("project_files"),list):
            payload["project_files"]=list(dict.fromkeys(
                promoted.get(entry,entry) for entry in payload["project_files"]))
        payload["committed_outputs"]=commit_index
        from safe_file_delete import pending_deletions
        from project_transaction import prune_deleted_payload,prune_deleted_runtime
        deleted_paths=[item["original"] for item in pending_deletions(project)]
        payload=prune_deleted_payload(payload,project)
        progress.stage("Estado de los módulos y eliminaciones reconciliado")
        # Un único archivo de recuperación anterior, sin crear ZIP en cada
        # apertura. El respaldo se actualiza SOLO al pulsar Guardar.
        if path.exists():
            from project_transaction import _atomic_copy
            _atomic_copy(path,project/"backup"/"Recuperacion_Anterior.stemstudio.json")
        progress.stage("Copia de recuperación comprobada")
        atomic_json(path,payload)
        progress.stage("Manifiesto de proyecto escrito")
        main.project_path=path
        # Ahora sí: el usuario ha confirmado Guardar; materializar las
        # eliminaciones en la papelera. Sin Guardar quedan en cuarentena.
        from safe_file_delete import finalize_deletions
        finalize_deletions(project,progress=progress)
        progress.stage(f"{deletion_total} eliminaciones confirmadas")
        prune_deleted_runtime(main,deleted_paths)
        finish_commit(main,promoted)
        progress.stage("Referencias y copias temporales reconciliadas")
        # Sólo tras guardar correctamente se registran ajustes globales.
        main._explicit_save=True
        try:
            main.save_config()
            wb.converter.save_preferences()
            wb.separator.save_preferences()
        finally:
            main._explicit_save=False
        progress.stage("Preferencias de módulos almacenadas")
        begin(main)
        progress.stage("Sesión de trabajo confirmada")
        progress.complete("Proyecto guardado y verificado")
        progress.close()
        progress=None
        if show_confirmation:
            from project_status_dialog import show_project_status
            show_project_status(main,project,path,action="guardado")
        return True
    except __import__("project_progress").OperationCancelled:
        QMessageBox.information(main,"Guardado cancelado",
            "No se ha confirmado el proyecto. Los medios anteriores están restaurados.")
        return False
    except (OSError,ValueError,TypeError) as exc:
        QMessageBox.warning(main,"No se pudo guardar",str(exc))
        return False
    finally:
        if progress is not None:progress.close()


def save_project_as(main,show_confirmation=True):
    """Guardar como: copia independiente con nombre y carpeta elegidos."""
    from project_session import clone_project
    from project_flow import project_directory
    from PySide6.QtWidgets import QInputDialog
    project=project_directory(main)
    if not project:
        return __import__("project_flow").new_project_dialog(main)
    name,ok=QInputDialog.getText(main,"Guardar proyecto como",
        "Nombre del nuevo proyecto:",text=str(main.project_name or "")+"_copia")
    if not ok or not name.strip():return False
    folder=file_dialogs.get_existing_directory(main,
        "Elige dónde guardar el nuevo proyecto",str(project.parent))
    if not folder:return False
    progress=None
    try:
        # Guardar como copia bytes realmente transferidos a otro proyecto.
        from project_progress import ProjectProgress
        source_files=[f for f in project.rglob("*") if f.is_file()]
        progress=ProjectProgress(main,"Guardando copia del proyecto",steps=7,
                    media_sizes=[f.stat().st_size for f in source_files])
        progress.allow_cancel(True)
        target=clone_project(project,folder,name.strip(),progress=progress)
        from project_transaction import save_clone_snapshot
        progress.message("Consolidando las ediciones de la copia nueva…")
        save_clone_snapshot(main,project,target,name.strip())
        progress.stage("Ediciones y resultados de la copia consolidados")
        progress.stage("Copia guardada y verificada")
        progress.complete("Proyecto duplicado correctamente")
        progress.close()
        progress=None
        # La sesión original sigue abierta con sus cambios sin guardar.
        if show_confirmation:
            from project_status_dialog import show_project_status
            show_project_status(main,target.parent,target,action="guardado_como")
        return True
    except __import__("project_progress").OperationCancelled:
        QMessageBox.information(main,"Copia cancelada",
            "La copia no se ha terminado y el proyecto original sigue intacto.")
        return False
    except (OSError,ValueError,TypeError) as exc:
        QMessageBox.warning(main,"No se pudo guardar como",str(exc))
        return False
    finally:
        if progress is not None:progress.close()


def revert_project_backup(main):
    """Restablece una copia previa, con confirmación, sin borrar medios nuevos."""
    from project_flow import project_directory
    from project_session import restore_snapshot,snapshot_on_open
    import zipfile
    project=project_directory(main)
    if not project:
        QMessageBox.information(main,"Sin proyecto","Abre primero un proyecto.")
        return False
    w=main.workbench
    if (main.recording or main.record_pending or w.separator.busy
            or w.converter.process is not None
            or main.drum_module.process is not None
            or main.vocal_module.process is not None
            or w.piano.dirty):
        QMessageBox.warning(main,"Revertir",
            "Detén el procesamiento y guarda o descarta la edición MIDI "
            "antes de restaurar una versión anterior.")
        return False
    archives=sorted((project/"backup").glob("Antes_de_abrir_*.zip"),reverse=True)
    if not archives:
        QMessageBox.information(main,"Sin copias",
            "Aún no hay ninguna copia generada al abrir este proyecto.")
        return False
    chosen,_=file_dialogs.get_open_file_name(main,
        "Revertir proyecto · seleccionar copia ZIP",
        str(archives[0]),"Copia del proyecto (*.zip)")
    if not chosen:return False
    answer=QMessageBox.question(main,"Revertir desde backup",
        "Se restaurarán los archivos anteriores de esta copia, "
        "sobrescribiendo los que tengan el mismo nombre. Los archivos "
        "posteriores con nombres distintos se conservarán.\n\n"
        "Antes se guardará otra copia del estado actual. ¿Continuar?",
        QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
    if answer!=QMessageBox.Yes:return False
    try:
        snapshot_on_open(project)
        restored=restore_snapshot(project,chosen)
        # Recargar la sesión desde su JSON restaurado para que las nueve
        # pantallas reflejen de inmediato los valores recuperados.
        restored_manifest=Path(main.project_path)
        if not open_project(main,str(restored_manifest)):
            raise ValueError("Backup restaurado, pero no se pudo recargar la sesión.")
        QMessageBox.information(main,"Copia restaurada",
            f"Restaurados {len(restored)} archivos y recargados sus ajustes.")
        return True
    except (OSError,ValueError,TypeError,zipfile.BadZipFile) as exc:
        QMessageBox.warning(main,"No se pudo revertir",str(exc))
        return False

def _protect_unsaved_project(main):
    """Un solo diálogo: Guardar, Descarta o Cancelar al cambiar proyecto.

    Nunca publicar pistas porque el usuario decida cerrar otro proyecto.
    """
    converter=getattr(getattr(main,"studio_home",None),"midi_to_audio",None)
    if converter is not None and converter.busy:
        QMessageBox.information(main,"Conversión MIDI a audio",
            "Cancela o finaliza la conversión antes de cambiar de proyecto.")
        return False
    project=getattr(main,"project_dir",None)
    if not project:return True
    w=main.workbench
    pending=any(store.pending for store in (
        w.separation_storage,w.midi_storage,w.drum_storage,w.vocal_storage))
    pending|=bool(w.piano.dirty)
    from safe_file_delete import pending_deletions
    pending|=bool(pending_deletions(project))
    # También deben ser reversibles los cambios de parámetros SIN media.
    try:
        manifest=json.loads(Path(main.project_path).read_text(encoding="utf-8"))
        current=project_payload(main)
        tracked=("parameters_midi","parameters_separation",
                 "parameters_monitor","parameters_recording_lab",
                 "parameters_vocal_full","parameters_drum_editor",
                 "parameters_drum_full","parameters_piano_view",
                 "parameters_mixer","stem_visibility","home_workspace")
        pending|=any(current.get(key)!=manifest.get(key) for key in tracked)
    except (OSError,ValueError,TypeError,AttributeError):
        pending=True
    # Al cerrar o sustituir un proyecto se pide siempre la elección.
    decision=QMessageBox.question(
        main,"Cambios sin guardar del proyecto",
        "Hay parámetros, MIDI o resultados provisionales que aún no has "
        "guardado.\n\n"
        "Sí: guardar los cambios en sus carpetas definitivas.\n"
        "No: descartar lo nuevo de esta sesión, sin tocar lo ya guardado.\n"
        "Cancelar: continuar trabajando en este proyecto.",
        QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel,
        QMessageBox.Cancel)
    if decision==QMessageBox.Cancel:return False
    if decision==QMessageBox.Yes:
        return save_project(main,show_confirmation=False)
    from project_transaction import discard
    try:
        discard(main)
        # El editor de Piano Roll mantiene notas sin guardar en memoria.
        # El usuario ya eligió expresamente descartarlas.
        w.piano.dirty=False
        return True
    except (OSError,ValueError) as exc:
        QMessageBox.warning(main,"No se pudo descartar",str(exc))
        return False

def open_project(main,path=None):
    if path is None:
        path,_=file_dialogs.get_open_file_name(main,"Abrir proyecto StemMIDI",str(Path.home()),
                                    "Proyecto StemMIDI (*.stemstudio.json *.json)")
    if not path:return False
    progress=None
    try:
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("application")!="StemMIDI Studio":
            raise ValueError("El archivo no es un proyecto de StemMIDI Studio.")
        from uuid import uuid4
        project_id=data.get("project_id") or uuid4().hex
        if project_id!=main.project_id and not _protect_unsaved_project(main):
            return
        # Se permite abrir proyectos antiguos por su identificador, pero
        # un proyecto con carpeta propia solo se vincula a la carpeta que
        # contiene físicamente su .json: no se confía en una ruta del JSON.
        candidate=Path(path).expanduser().resolve()
        from project_layout import project_folder_name
        project_name=str(data.get("project_name") or "")
        allowed_names=(project_folder_name(project_name)+".stemstudio.json",
                       __import__("project_flow").slug_name(project_name)+".stemstudio.json") \
                      if project_name else ()
        named=(bool(project_name) and candidate.name in allowed_names)
        project_dir=candidate.parent if named else None
        # Porcentaje de 18 secciones reales de apertura/restauración.
        # Cada avance se registra DESPUÉS de completar la sección,
        # independientemente de los segundos transcurridos.
        from project_progress import ProjectProgress
        progress=ProjectProgress(main,"Abriendo proyecto",steps=18)
        progress.stage("Manifiesto leído y validado")
        # Abrir no debe generar otro ZIP gigantesco cada vez.
        # El directorio backup recibe únicamente las revisiones necesarias
        # cuando se confirma la sobrescritura de un MIDI.
        # Recuperar eliminaciones pendientes de una sesión interrumpida
        # ANTES de que TaskStorage reconstruya el inventario de pistas.
        if project_dir is not None:
            from safe_file_delete import rollback_deletions
            rollback_deletions(project_dir)
        progress.stage("Eliminaciones pendientes revisadas")
        if not main.workbench.switch_project(project_id,project_dir):
            return False
        progress.stage("Inventarios y tareas del proyecto vinculados")
        main.project_dir=project_dir
        main.project_name=str(data.get("project_name") or "") or None
        main.project_path=candidate
        main.folder_display.setText(str(project_dir/"grabaciones")
                                    if project_dir else
                                    main.config.get("folder",str(__import__(
                                        "main").RECORDINGS)))
        main.folder_display.setReadOnly(bool(project_dir))
        main.workbench.bind_project(project_dir)
        # Al cambiar de proyecto no heredar el tablero del anterior.
        main.studio_home.home_workspace.reset_for_project()
        main.file_prefix.setText(__import__("project_flow").slug_name(
            main.project_name or "Grabacion"))
        progress.stage("Rutas y nombre del proyecto restaurados")
        main.setWindowTitle("StemMIDI Studio · "+str(main.project_name)
                            if main.project_name else "StemMIDI Studio")
        main.project_recordings=[str(Path(v)) for v in data.get("recordings",[])
            if isinstance(v,str) and Path(v).is_file()]
        source_recording=data.get("source_recording")
        main.last_file=(str(source_recording)
            if isinstance(source_recording,str) and Path(source_recording).is_file()
            else (main.project_recordings[-1] if main.project_recordings else None))
        if main.last_file:
            main.record_preview.load(main.last_file)
        else:
            main.record_preview.clear()
        progress.stage("Grabaciones y monitor de audio restaurados")
        w=main.workbench
        if data.get("drum_input") and Path(data["drum_input"]).is_file():
            main.drum_module.input.setText(data["drum_input"])
        if data.get("vocal_input") and Path(data["vocal_input"]).is_file():
            main.vocal_module.input.setText(data["vocal_input"])
        drums=main.drum_module.studio
        if isinstance(data.get("drum_mix"),dict):
            drums.apply_mix_preset(data["drum_mix"])
        if isinstance(data.get("drum_pattern"),dict):
            drums.apply_pattern_preset(data["drum_pattern"])
        for name,control in (("drum_bpm",drums.seq_bpm),
                             ("drum_velocity",drums.seq_velocity),
                             ("drum_swing",drums.seq_swing)):
            if name in data:
                control.setValue(max(control.minimum(),
                    min(control.maximum(),int(data[name]))))
        if "drum_bars" in data:
            position=drums.seq_bars.findData(int(data["drum_bars"]))
            if position>=0:drums.seq_bars.setCurrentIndex(position)
        progress.stage("Pistas y parámetros de batería cargados")
        if "vocal_tonic" in data:
            main.vocal_module.tonic.setCurrentIndex(max(0,min(11,int(data["vocal_tonic"]))))
        if data.get("vocal_scale"):
            main.vocal_module.scale.setCurrentText(str(data["vocal_scale"]))
        if data.get("vocal_preset") in __import__("vocal_tune_module").PRESETS:
            main.vocal_module.preset.setCurrentText(data["vocal_preset"])
        for key,control in (
            ("vocal_strength",main.vocal_module.strength),
            ("vocal_retune_ms",main.vocal_module.retune),
            ("vocal_humanize",main.vocal_module.humanize),
            ("vocal_threshold",main.vocal_module.threshold),
            ("vocal_compression",main.vocal_module.compression),
            ("vocal_highpass",main.vocal_module.highpass),
            ("vocal_character_amount",main.vocal_module.character_amount),
            ("vocal_warmth",main.vocal_module.warmth),
            ("vocal_air",main.vocal_module.air),
            ("vocal_presence",main.vocal_module.presence),
            ("vocal_deesser",main.vocal_module.deesser),
            ("vocal_gate",main.vocal_module.gate),
            ("vocal_reverb",main.vocal_module.reverb),
            ("vocal_wet",main.vocal_module.wet),
            ("vocal_doubler",main.vocal_module.doubler),
            ("vocal_delay",main.vocal_module.delay),
            ("vocal_delay_ms",main.vocal_module.delay_ms),
            ("vocal_stereo_width",main.vocal_module.stereo_width),
            ("vocal_output_gain_db",main.vocal_module.output_gain_db)):
            if key in data:
                control.setValue(max(control.minimum(),
                    min(control.maximum(),int(data[key]))))
        if data.get("vocal_character") in ("Natural","Dulce","Rasgada","Cálida","Aireada"):
            main.vocal_module.character.setCurrentText(data["vocal_character"])
        main.vocal_module.bypass_tune.setChecked(bool(data.get("vocal_bypass_tune",False)))
        progress.stage("Afinación vocal y controles restaurados")
        if isinstance(data.get("parameters_monitor"),dict):
            main.monitor_preset_apply(data["parameters_monitor"])
        progress.stage("Ajustes de monitorización aplicados")
        lab=main.recording_lab
        if isinstance(data.get("parameters_recording_lab"),dict):
            lab.apply_preset(data["parameters_recording_lab"])
        source=data.get("recording_lab_original")
        if isinstance(source,str) and source and Path(source).is_file():
            lab.set_source(source)
        else:
            lab.reset_project_source()
        processed=data.get("recording_lab_processed")
        if isinstance(processed,str) and processed and Path(processed).is_file():
            lab.processed=Path(processed)
            lab.play_processed.setEnabled(True)
            lab.export_button.setEnabled(True)
        progress.stage("Laboratorio de audio y tomas verificadas")
        if isinstance(data.get("parameters_drum_editor"),dict):
            drums.apply_editor_preset(data["parameters_drum_editor"])
        if isinstance(data.get("parameters_vocal_full"),dict):
            main.vocal_module.apply_full_preset(data["parameters_vocal_full"])
        if isinstance(data.get("parameters_piano_view"),dict):
            w.piano.apply_view_preset(data["parameters_piano_view"])
        progress.stage("Presets de batería, voz y Piano Roll aplicados")
        if isinstance(data.get("parameters_midi"),dict):
            w.converter.apply_parameters(data["parameters_midi"])
        if isinstance(data.get("parameters_separation"),dict):
            w.separator.apply_parameters(data["parameters_separation"])
        progress.stage("Parámetros de separación y transcripción cargados")
        for key,handler in (("source_separation",w.separator.on_import_selected),
                            ("source_midi",w.converter.on_import_file)):
            source=data.get(key)
            if source and Path(source).is_file():handler(str(source))
        progress.stage("Fuentes de audio de los módulos comprobadas")
        # El modo de conversión por carpetas se restaura DESPUÉS del audio
        # individual: on_import_file() lo desactiva cuando cambia la fuente.
        midi_folder=data.get("midi_source_folder")
        if (data.get("midi_use_folder") and isinstance(midi_folder,str)
                and Path(midi_folder).is_dir()):
            w.converter.folder_path.setText(midi_folder)
            w.converter.use_folder.setChecked(True)
            w.converter.refresh_folder_previews(Path(midi_folder))
        if (data.get("vocal_reference_authorized")
                and data.get("vocal_reference")
                and Path(data["vocal_reference"]).is_file()):
            main.vocal_module.ref_consent.setChecked(True)
            main.vocal_module.reference.setText(data["vocal_reference"])
        if data.get("record_format"):
            main.format.setCurrentText(data["record_format"])
        if data.get("record_rate"):
            idx=main.capture_rate.findData(int(data["record_rate"]))
            if idx>=0:main.capture_rate.setCurrentIndex(idx)
        main.limit_lossy_rate(main.format.currentText())
        main.set_input_processing(
            data.get("input_gain_db",main.input_gain_db),
            data.get("input_balance",main.input_balance))
        progress.stage("Formatos de grabación y entradas recuperados")
        for name,value in data.get("mixer_levels",{}).items():
            if name in main.studio_home.mixer_rows:
                main.studio_home.mixer_rows[name]["fader"].setValue(int(value))
        for name,visible in data.get("stem_visibility",{}).items():
            if name in main.studio_home.stem_checks:
                main.studio_home.stem_checks[name].setChecked(bool(visible))
        # Cargar la sesión del mezclador con sus pistas y parámetros.
        mixer_sources=[Path(v) for v in data.get("mixer_sources",[])
                       if isinstance(v,str) and Path(v).is_file()]
        if isinstance(data.get("parameters_mixer"),dict):
            main._pending_mixer_preset=data["parameters_mixer"]
        if mixer_sources:
            w.show_mixer(mixer_sources)
            if w.mixer is not None and isinstance(data.get("parameters_mixer"),dict):
                w.mixer.apply_preset(data["parameters_mixer"])
        progress.stage("Mezclador y pistas de audio restaurados")
        # El MIDI original o editado se restaura en Piano Roll, con sus
        # ajustes de visualización ya aplicados.
        midi_editor=data.get("midi_editor_file")
        if isinstance(midi_editor,str) and Path(midi_editor).is_file():
            # Restaurar el EDITOR y sus notas, sin navegar a su pestaña:
            # show_piano_roll() llama setCurrentWidget(piano) y hacía
            # que todo proyecto con MIDI arrancase fuera de Inicio.
            if w.piano.open_midi(midi_editor) is not False:
                w.apply_button.setEnabled(True)
                if isinstance(data.get("parameters_piano_view"),dict):
                    w.piano.apply_view_preset(data["parameters_piano_view"])
        progress.stage("Piano Roll y MIDI editados recuperados")
        main.workbench.converter.refresh_project_stems()
        __import__("project_flow").route_approved(main,refresh=False)
        # Al abrir, un único refresco al final. route_approved ya ha
        # vinculado Batería/Voces; repetir la reconstrucción duplicaba
        # ffprobe, inventario de stems y ondas grandes.
        main.studio_home.refresh(force=True)
        progress.stage("Stems y resultados interconectados")
        from project_transaction import begin
        begin(main)
        progress.stage("Sesión de trabajo y recuperación preparadas")
        midi=data.get("selected_midi")
        if midi and Path(midi).is_file():
            for i in range(main.studio_home.midi_choice.count()):
                if main.studio_home.midi_choice.itemData(i)==str(midi):
                    main.studio_home.midi_choice.setCurrentIndex(i)
        progress.stage("Selección MIDI inicial restaurada")
        progress.complete("Proyecto abierto y verificado")
        progress.close()
        progress=None
        # Posiciones de los 12 módulos y ventanas flotantes: cada
        # proyecto recupera SOLO su disposición guardada. Los proyectos
        # antiguos sin esta clave siguen usando el Inicio original.
        main.studio_home.home_workspace.restore(data.get("home_workspace"))
        # El destino visual de la apertura es SIEMPRE Inicio.
        # Ninguna restauración de archivo MIDI o de mezclador lo cambia.
        main.tabs.setCurrentWidget(main.studio_home)
        from project_status_dialog import show_project_status
        show_project_status(main,candidate.parent,candidate,action="abierto")
        return True
    except (OSError,ValueError,TypeError) as exc:
        QMessageBox.warning(main,"No se pudo abrir",str(exc))
        return False
    finally:
        if progress is not None:progress.close()

def close_project(main):
    """Cerrar la sesión sin destruir medios ni trabajos temporales antiguos."""
    from uuid import uuid4
    if not _protect_unsaved_project(main):
        return
    if not main.workbench.switch_project(uuid4().hex):
        return
    main.project_path=None
    main.project_dir=None
    main.project_name=None
    main.last_file=None
    main.project_recordings=[]
    main.record_preview.clear()
    main.recording_lab.reset_project_source()
    main.folder_display.setReadOnly(False)
    main.workbench.bind_project(None)
    main.studio_home.home_workspace.reset_for_project()
    main.folder_display.setText(str(main.config.get("folder",
        str(__import__("main").RECORDINGS))))
    main.setWindowTitle("StemMIDI Studio")
    main.workbench.converter.refresh_project_stems()
    main.tabs.setCurrentWidget(main.studio_home)
    main.studio_home.result_hint.setText(
        "Proyecto cerrado. Nuevo espacio vacío; ningún archivo anterior se ha eliminado.")

def preferences(main,open_models=False):
    dlg=QDialog(main)
    dlg.setWindowTitle("Preferencias · StemMIDI Studio")
    dlg.resize(1100,745)
    dlg.setMinimumSize(880,590)
    layout=QVBoxLayout(dlg)
    tabs=QTabWidget(dlg)
    layout.addWidget(tabs,1)
    general=QWidget()
    general_layout=QVBoxLayout(general)
    form=QFormLayout()
    format_box=QComboBox()
    for i in range(main.format.count()):format_box.addItem(main.format.itemText(i))
    format_box.setCurrentText(main.format.currentText())
    form.addRow("Formato de grabación",format_box)
    rate_box=QComboBox()
    for i in range(main.capture_rate.count()):
        rate_box.addItem(main.capture_rate.itemText(i),main.capture_rate.itemData(i))
    rate_box.setCurrentIndex(main.capture_rate.currentIndex())
    form.addRow("Frecuencia de muestreo",rate_box)
    output=QComboBox()
    from preview_player import AudioRoute
    AudioRoute.register_control(output)
    form.addRow("Salida de escucha",output)
    capture=QCheckBox("Mostrar micrófonos además de las fuentes del sistema")
    capture.setChecked(main.show_mics.isChecked())
    form.addRow("Captura",capture)
    general_layout.addLayout(form)
    general_layout.addStretch()
    tabs.addTab(general,"Grabación y audio")
    from model_manager import ModelManager
    models=ModelManager(main,tabs)
    tabs.addTab(models,"Modelos de IA")
    if open_models:tabs.setCurrentIndex(1)
    footer=QHBoxLayout()
    footer.addStretch()
    btn=QPushButton("Aplicar preferencias")
    btn.setObjectName("primary")
    def apply():
        if models.proc is not None:
            QMessageBox.information(dlg,"Descarga activa",
                "Cancela o termina la tarea antes de cerrar Preferencias.")
            return
        main.format.setCurrentText(format_box.currentText())
        main.capture_rate.setCurrentIndex(rate_box.currentIndex())
        main.show_mics.setChecked(capture.isChecked())
        if output.currentData():AudioRoute.choose(output.currentData())
        main.save_config()
        dlg.accept()
    def safe_close():
        if models.proc is not None:
            QMessageBox.information(dlg,"Descarga en curso",
                "Cancela o termina la descarga antes de cerrar Preferencias.")
            return
        dlg.reject()
    def safe_close_event(event):
        if models.proc is not None:
            event.ignore()
            QMessageBox.information(dlg,"Modelo descargándose",
                "Pulsa «Cancelar tarea» o espera al resultado.")
        else:
            event.accept()
    dlg.closeEvent=safe_close_event
    btn.clicked.connect(apply)
    footer.addWidget(btn)
    close=QPushButton("Cerrar")
    close.clicked.connect(safe_close)
    footer.addWidget(close)
    layout.addLayout(footer)
    dlg.exec()
    # Los modelos registrados para el motor no alteran proyectos ni audio.
    main.workbench.separator.refresh_model_registry()
    main.drum_module.refresh_model_choices()

def help_dialog(main):
    from help_center import open_help
    return open_help(main)

def about_dialog(main):
    QMessageBox.about(main,"Acerca de StemMIDI Studio",
        "<h2>StemMIDI Studio</h2>"
        "<p><b>Libre para usar, estudiar y mejorar.</b><br>"
        "Hecho para compartir, no para lucrarse con el código.</p>"
        "<p>Estación de grabación, separación de instrumentos, conversión Audio→MIDI, "
        "mezclador y Piano Roll.</p>"
        "<p>Incluye bibliotecas de terceros sujetas a sus respectivas licencias. "
        "La publicación y licencia definitiva del proyecto se documentarán "
        "en su repositorio.</p>")

class ProjectResults(QWidget):
    """Únicamente los resultados asociados al proyecto activo."""
    def __init__(self,main):
        super().__init__(main)
        from PySide6.QtWidgets import (QTableWidget,QTableWidgetItem,
            QHeaderView,QAbstractItemView)
        self.main=main
        self._paths=[]
        from result_file_details import ResultInfoReader
        self._file_info_reader=ResultInfoReader(self)
        self._file_info_reader.ready.connect(self._show_details_ready)
        self._info_dialog=None
        self._info_text=None
        layout=QVBoxLayout(self)
        layout.setContentsMargins(14,12,14,12)
        title=QLabel("RESULTADOS DEL PROYECTO ACTUAL")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle=QLabel("Aquí solo aparecen las separaciones y tomas MIDI "
            "de este proyecto. Los demás proyectos y la biblioteca global "
            "permanecen independientes.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        from results_dragdrop import ResultsDragTable
        self.table=ResultsDragTable(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Archivo","Tipo","Duración"])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setToolTip(
            "Ctrl+clic: varios archivos; Mayús+clic: intervalo; Ctrl+A: todos. "
            "Arrastra la selección a otro módulo compatible, siempre como copia. "
            "Clic derecho para guardar o eliminar la selección.")
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda row,col:self.open_selected())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._result_context_menu)
        layout.addWidget(self.table,1)
        from preview_player import PreviewPlayer
        self.preview=PreviewPlayer("PREVISUALIZACIÓN · RESULTADO SELECCIONADO",self)
        self.preview.set_compact(True)
        layout.addWidget(self.preview)
        self.table.itemSelectionChanged.connect(self.preview_selection)
        buttons=QHBoxLayout()
        for title,callback in (
            ("▶ Reproducir",self.play_selected),
            ("■ Detener",self.preview.stop),
            ("Información…",self.show_file_information),
            ("Seleccionar todo",self.table.selectAll),
            ("Quitar selección",self.table.clearSelection),
            ("Guardar selección…",self.save_selected),
            ("→ Compositor",self.send_to_composer),
            ("Eliminar selección…",self.delete_selected),
            ("Guardar todo…",lambda:self.main.studio_home._save_results(self._paths))):
            b=QPushButton(title)
            b.clicked.connect(callback)
            buttons.addWidget(b)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.note=QLabel("Sin resultados en el proyecto actual.")
        self.note.setObjectName("muted")
        layout.addWidget(self.note)

    def refresh(self,files):
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtCore import QSignalBlocker,QItemSelectionModel
        selected=set(self.selected_paths())
        self._paths=list(files)
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(self._paths))
        home=self.main.studio_home
        from vocal_catalog import vocal_role
        for row,path in enumerate(self._paths):
            role=vocal_role(path)
            label=f"{role} · {path.name}" if role else path.name
            for col,value in enumerate(
                (label,"MIDI" if path.suffix.lower() in (".mid",".midi",".kar") else "Audio",
                 home._result_duration(path))):
                item=QTableWidgetItem(str(value))
                if col==0:
                    item.setToolTip(str(path))
                    item.setData(Qt.UserRole,str(path))
                self.table.setItem(row,col,item)
        # Restaurar la selección por ruta real, no por índice: la inserción
        # de nuevos resultados no debe cambiar la pista seleccionada.
        selection=self.table.selectionModel()
        if selection is not None:
            with QSignalBlocker(self.table),QSignalBlocker(selection):
                self.table.clearSelection()
                for row,path in enumerate(self._paths):
                    if path in selected:
                        selection.select(self.table.model().index(row,0),
                            QItemSelectionModel.Select|QItemSelectionModel.Rows)
        if not self._paths:self.preview.clear()
        self.note.setText(
            f"{len(self._paths)} resultados del proyecto activo. "
            "Ctrl/Mayús permite seleccionar varias pistas."
            if self._paths else "Sin resultados en el proyecto actual.")

    def selected_paths(self):
        return [self._paths[x.row()] for x in self.table.selectionModel().selectedRows()
                if 0<=x.row()<len(self._paths)]

    def preview_selection(self):
        paths=self.selected_paths()
        if paths:
            self.note.setText(
                f"{len(paths)} seleccionado(s) de {len(self._paths)} resultados. "
                "Ctrl+clic / Mayús+clic para ampliar la selección.")
        else:
            self.note.setText(f"{len(self._paths)} resultados · sin selección.")
        if paths and paths[0].is_file():
            if self.preview.current_file!=str(paths[0].resolve()):
                self.preview.load(paths[0])
        else:self.preview.clear()
        if self._info_dialog is not None and self._info_dialog.isVisible():
            self._load_file_information()

    def show_file_information(self):
        """Ficha ampliada sin alterar archivos ni el reproductor."""
        from PySide6.QtWidgets import QDialog,QVBoxLayout,QTextBrowser,QPushButton
        if self._info_dialog is None:
            dialog=QDialog(self)
            dialog.setWindowTitle("StemMIDI Studio · Información del resultado")
            dialog.setMinimumSize(580,450)
            dialog.setStyleSheet(
                "QDialog { background:#041b40;color:#d6f5ff; }"
                "QTextBrowser {background:#031734;color:#d6f5ff;"
                "border:1px solid #278ace;font-size:12px;padding:9px;}")
            box=QVBoxLayout(dialog)
            info=QTextBrowser(dialog)
            info.setOpenExternalLinks(False)
            box.addWidget(info)
            close=QPushButton("Cerrar",dialog)
            close.clicked.connect(dialog.close)
            box.addWidget(close)
            self._info_dialog=dialog
            self._info_text=info
        self._load_file_information()
        self._info_dialog.show()
        self._info_dialog.raise_()

    def _load_file_information(self):
        files=self.selected_paths()
        if not files:
            self._file_info_reader.clear()
            self._info_text.setPlainText("Selecciona un archivo de Resultados.")
            return
        path=files[0]
        self._info_text.setPlainText("Leyendo metadatos del archivo seleccionado…")
        self._file_info_reader.request(path,
            getattr(self.main,"project_dir",None),
            self.main.studio_home._stem_for(path))

    def _show_details_ready(self,generation,report):
        if (self._file_info_reader.is_current(generation)
                and self._info_text is not None):
            self._info_text.setPlainText(report)

    def play_selected(self):
        paths=self.selected_paths()
        if paths and paths[0].is_file():
            self.preview.load(paths[0],autoplay=True)

    def open_selected(self):
        paths=self.selected_paths()
        if not paths:return
        file=paths[0]
        if file.suffix.lower() in (".mid",".midi",".kar"):
            self.main.workbench.show_piano_roll(file)
        else:self.play_selected()

    def send_to_composer(self,paths=None):
        files=list(paths) if paths is not None else self.selected_paths()
        if not files:return False
        editor=getattr(self.main,"composer_tab",None)
        if editor is None:return False
        editor.sync_project()
        editor._add(files)
        self.main.tabs.setCurrentWidget(editor)
        return True

    def save_selected(self):
        self.main.studio_home._save_results(self.selected_paths())

    def delete_selected(self,paths=None):
        files=self.selected_paths() if paths is None else list(paths)
        if not files:return False
        from safe_file_delete import trash_files
        if not trash_files(self,files):return False
        self.preview.stop()
        self.main.studio_home.refresh(force=True)
        return True

    def _result_context_menu(self,position):
        index=self.table.indexAt(position)
        selected=self.selected_paths()
        clicked=self._paths[index.row()] if (index.isValid() and
                             0<=index.row()<len(self._paths)) else None
        files=selected if (clicked is None or clicked in selected) else [clicked]
        menu=QMenu(self)
        all_action=menu.addAction("Seleccionar todos · Ctrl+A")
        clear_action=menu.addAction("Quitar selección")
        menu.addSeparator()
        save=menu.addAction(f"Guardar {len(files)} archivo(s) seleccionados…")
        composer=menu.addAction(
            f"Enviar {len(files)} archivo(s) al Compositor")
        delete=menu.addAction(f"Eliminar {len(files)} archivo(s) seleccionados…")
        save.setEnabled(bool(files))
        composer.setEnabled(bool(files))
        delete.setEnabled(bool(files))
        action=menu.exec(self.table.viewport().mapToGlobal(position))
        if action is all_action:self.table.selectAll()
        elif action is clear_action:self.table.clearSelection()
        elif action is save:self.main.studio_home._save_results(files)
        elif action is composer:self.send_to_composer(files)
        elif action is delete:self.delete_selected(files)

def install(main):
    """Añadir portada fiel a la maqueta sin alterar la lógica preexistente."""
    from PySide6.QtWidgets import QWidget,QTabWidget,QPushButton,QVBoxLayout,QLabel
    from PySide6.QtCore import Qt
    from studio_home import StudioHome

    tabs=main.tabs
    main.monitor_page=tabs.widget(0)
    # Reasociar antes de setCentralWidget para evitar que Qt destruya tabs.
    from main_rounded_shell import RoundedMainShell
    shell=RoundedMainShell(main)
    tabs.setParent(shell)
    vertical=shell.layout()
    banner=StudioHeader(main)
    vertical.addWidget(banner)
    vertical.addWidget(tabs,1)
    main.setCentralWidget(shell)
    main._rounded_shell=shell
    main.studio_banner=banner
    # Movimiento por la cabecera y redimensionado desde los bordes invisibles.
    # El resto de los módulos y la lógica de audio permanecen intactos.
    from frameless_main_window import FramelessWindowController
    main._frameless_controls=FramelessWindowController(main,banner)

    home=StudioHome(main,main.workbench)
    main.studio_home=home
    tabs.insertTab(0,home,"⌂ Inicio")
    tabs.setTabText(tabs.indexOf(main.monitor_page),"♩ Monitor / Grabación")
    tabs.setTabText(tabs.indexOf(main.workbench.separation_tab),"◈ Separación de audio")
    tabs.setTabText(tabs.indexOf(main.workbench.midi_tab),"♫ Audio a MIDI")
    from drum_module import DrumModule
    main.drum_module=DrumModule(main,main.workbench)
    main.workbench.drum_module=main.drum_module
    home.bind_drum_module(main.drum_module)
    tabs.insertTab(tabs.indexOf(main.workbench.midi_tab),main.drum_module,"Desglose de batería")
    main.drum_module.resultsChanged.connect(lambda:home.refresh(force=True))
    from vocal_tune_module import VocalTuneModule
    main.vocal_module=VocalTuneModule(main,main.workbench)
    main.workbench.vocal_module=main.vocal_module
    home.bind_vocal_module(main.vocal_module)
    tabs.insertTab(tabs.indexOf(main.workbench.piano),main.vocal_module,"Afinación vocal")
    main.vocal_module.resultsChanged.connect(lambda:home.refresh(force=True))
    tabs.currentChanged.connect(lambda idx:
        main.drum_module.refresh_sources()
        if tabs.widget(idx) is main.drum_module else None)
    tabs.setTabText(tabs.indexOf(main.workbench.piano),"▥ Piano Roll")

    # La pestaña Resultados debe respetar el ámbito del proyecto,
    # igual que el panel de resultados de la pantalla Inicio.
    for legacy in (main.workbench.saved_audio,main.workbench.saved_midi):
        index=tabs.indexOf(legacy)
        if index>=0:tabs.removeTab(index)
        legacy.hide()
    main.results_tab=ProjectResults(main)
    tabs.addTab(main.results_tab,"▱ Resultados")
    # Compositor real multipista conectado a los mismos Resultados.
    # Orden exacto solicitado: Piano Roll | Compositor | Resultados.
    from compositor_tab import ComposerTab
    main.composer_tab=ComposerTab(main)
    tabs.insertTab(tabs.indexOf(main.results_tab),
                   main.composer_tab,"♫ Compositor")
    tabs.currentChanged.connect(lambda index:
        main.composer_tab.sync_project()
        if tabs.widget(index) is main.composer_tab else None)
    home.refresh(force=True)
    main.recording_lab.resultsChanged.connect(lambda:home.refresh(force=True))

    # El mezclador permanece accesible aunque todavía no haya pistas.
    mixer_page=QWidget()
    ml=QVBoxLayout(mixer_page)
    ml.setSpacing(12)
    title=QLabel("MEZCLADOR DE PISTAS")
    title.setObjectName("title")
    ml.addWidget(title)
    label_=QLabel("Para utilizar el mezclador, carga o separa un audio. "
                  "Después abre las pistas y sus controles de volumen, Solo y Mute.")
    label_.setObjectName("muted")
    label_.setWordWrap(True)
    ml.addWidget(label_)
    button=QPushButton("Abrir el mezclador de pistas")
    button.setObjectName("primary")
    button.clicked.connect(home.open_mixer)
    ml.addWidget(button,alignment=Qt.AlignLeft)
    from preview_player import PreviewPlayer
    main.mixer_prelisten=PreviewPlayer("PREESCUCHA ANTES DE ENVIAR PISTAS AL MEZCLADOR",mixer_page)
    main.mixer_prelisten.set_compact(True)
    ml.addWidget(main.mixer_prelisten)
    audition_button=QPushButton("Escuchar archivo sin añadirlo al proyecto…")
    audition_button.clicked.connect(lambda:(
        main.mixer_prelisten.load(path)
        if (path:=file_dialogs.get_open_file_name(
            main,"Escuchar audio antes de mezclar",str(Path.home()),
            "Audio (*.wav *.flac *.mp3 *.ogg *.m4a);;MIDI (*.mid *.midi)")[0])
        else None))
    ml.addWidget(audition_button,alignment=Qt.AlignLeft)
    ml.addStretch()
    main.mixer_placeholder=mixer_page
    tabs.insertTab(tabs.indexOf(main.workbench.piano),mixer_page,"☷ Mezclador")

    tabs.setCurrentWidget(home)
    tabs.tabBar().setExpanding(True)
    # Con nueve módulos, en pantallas reducidas los últimos tabs quedaban
    # fuera de la ventana sin flechas para alcanzarlos.
    tabs.tabBar().setUsesScrollButtons(True)
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon
    from pathlib import Path
    icon_dir=Path(__file__).resolve().parent/"assets"
    tabicons=[
        ("Inicio","home"),("Monitor / Grabación","mic"),
        ("Separación de audio","layers"),("Desglose de batería","drum"),("Audio a MIDI","note"),("Estudio vocal","vocal"),
        ("Mezclador","mixer"),("Piano Roll","piano"),
        ("Compositor","mixer"),("Resultados","folder")]
    tabs.setIconSize(QSize(22,22))
    for name,iconname in tabicons:
        for i in range(tabs.count()):
            if name in tabs.tabText(i):
                tabs.setTabIcon(i,QIcon(str(icon_dir/f"ui_{iconname}.svg")))
                tabs.setTabText(i,name)
                break
    main.setWindowTitle("StemMIDI Studio · Audio y MIDI")
    main.resize(1536,1024)
    main.setMinimumSize(1100,735)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from pathlib import Path
    assets=Path(__file__).resolve().parent/"assets"
    icon=QIcon(str(assets/"stemmidi_icon.svg"))
    main.setWindowIcon(icon)
    QApplication.instance().setWindowIcon(icon)
    check=assets/"check_white.svg"
    from neon_identity import NEON_GLOBAL_CSS
    QApplication.instance().setStyleSheet(STYLE_STUDIO+NEON_GLOBAL_CSS+
        "\nQCheckBox::indicator:checked {image:url('"+str(check)+"');}\n")
    # No pintar un rectángulo oscuro encima de las esquinas transparentes.
    # La carcasa redondeada pinta el gradiente/borde usando el mismo esquema
    # que floatingGlass; el resto del CSS y módulos no se tocan.
    main.setStyleSheet("QMainWindow#stemMainWindow {background:transparent; border:0;}")
    from studio_workspace_cards import install as install_cards
    install_cards(main)
    # Pestañas profesionales: se trasladan exactamente los mismos
    # editores/controles del flotante, sin un segundo motor independiente.
    from studio_shared_tabs import install as install_shared_tabs
    install_shared_tabs(main)
    import ui_polish
    ui_polish.install(main)
    # Ayuda emergente de todos los controles; las tareas nuevas y el
    # mezclador dinámico se cubren automáticamente al crearse.
    import ui_hover_help
    ui_hover_help.install(main)
    banner.help_toggle.bind(main._context_help)
    from help_center import install_shortcuts
    install_shortcuts(main)
    from home_tab_sync import HomeTabSynchronizer
    main.home_tab_sync=HomeTabSynchronizer(main)
    home._tab_sync=main.home_tab_sync
    # Un transporte MIDI persistente por encima de todos los módulos;
    # no sustituir ninguno de los reproductores que ya funcionan.
    from global_midi_transport import install as install_global_midi
    install_global_midi(main)
    return home

