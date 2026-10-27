"""Paleta visual compartida de StemMIDI Studio, revisada octubre 2026.

Una misma identidad para Inicio, pestañas, diálogos, listas y módulos.
No interfiere con señales de audio, estados de motor o colores por instrumento.
"""
COLORS = {
    "canvas": "#010919",
    "panel": "#061839",
    "raised": "#0a285b",
    "input": "#071c44",
    "border": "#148cff",
    "glow": "#00d9ff",
    "electric": "#137bff",
    "light": "#65f6ff",
    "text": "#f4fbff",
    "secondary": "#c1edff",
    "muted": "#9cc8ee",
    "record": "#f31654",
}

# Estas reglas se añaden DESPUÉS del tema actual: no cambian tamaños ni
# disposición de los módulos. El brillo se crea con gradientes de Qt/QSS.
NEON_GLOBAL_CSS = """
QMainWindow, QWidget#main, QWidget#studioHomePage,
QWidget#studioHome, QWidget#monitorCanvas, QWidget#studioModuleSurface {
 background:#010919; color:#f4fbff;
}
QDialog { background:#06132e; color:#f4fbff; }
QLabel { color:#f4fbff; }
QLabel#muted, QLabel#homeLabel { color:#b5dcff; }
QLabel#section, QLabel#floatingTitle { color:#77f3ff; font-weight:800; }
QLabel#status { color:#56f5ff; font-weight:800; }
QFrame#studioCard, QFrame#panel, QFrame#inner {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #09295f, stop:.30 #051b45, stop:1 #010f29);
 border:1px solid #158aff; border-radius:8px;
}
QFrame#moduleCardBanner, QPushButton#studioCardHeading {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #168efd, stop:.20 #0b6bd2, stop:.65 #063985, stop:1 #052554);
 border:1px solid #24cdff;
 border-bottom:2px solid #00e5ff; color:#ffffff; font-weight:800;
}
QPushButton {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #1154a6, stop:.50 #083579, stop:1 #062656);
 color:#f7feff; border:1px solid #258eff; border-radius:5px;
}
QPushButton:hover {background:#126cdb; border-color:#62f7ff;color:white;}
QPushButton:pressed {background:#044b9f; border-color:#b0ffff;}
QPushButton:disabled {background:#12233c;color:#84a8c5;border-color:#34516a;}
QPushButton#primary, QPushButton#browserPrimary {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
  stop:0 #06eaff, stop:.15 #08b6f0, stop:1 #0961ed);
 color:white; border:2px solid #80faff; font-weight:800;
}
QPushButton#primary:hover, QPushButton#browserPrimary:hover {
 background:#18cfff;border:2px solid white;
}
QPushButton#record {background:#d71a50;border:2px solid #ff6b80;color:white;}
QPushButton#stop {background:#832046;border:1px solid #ff4872;color:white;}
QPushButton#homeLockButton,QPushButton#cardHelpButton {
 background:#09346c;border:1px solid #22dcff;color:#8cffff;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
 background:#071f48;color:#ffffff;
 border:1px solid #2798ef;border-radius:5px;
 selection-background-color:#127cfa;selection-color:white;
}
QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus {
 border:2px solid #5bedff; background:#0a2c65;
}
QComboBox QAbstractItemView {background:#061c43;color:#ffffff;
 selection-background-color:#126eff;selection-color:white;}
QGroupBox {background:#051d42;color:#c7f6ff;
 border:1px solid #0f8dec;border-radius:7px;}
QGroupBox::title {color:#9dfaff;background:#061b43;}
QTabWidget::pane {background:#020d26;border:1px solid #1574de;}
QTabBar::tab {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0b356b,stop:1 #051533);
 color:#e6f5ff;border:1px solid #1a66b7;
}
QTabBar::tab:selected {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
  stop:0 #12c2ff,stop:.16 #147efa,stop:1 #0646a9);
 color:white;border:1px solid #3fe8ff;border-bottom:2px solid #71ffff;
}
QTabBar::tab:hover:!selected {background:#1251a7;color:white;}
QCheckBox,QRadioButton {color:#eaf8ff;}
QCheckBox::indicator:checked {background:#127fff;border:1px solid #82ffff;}
QSlider::groove:horizontal {background:#153e78;border:1px solid #285b99;
 border-radius:3px;min-height:5px;max-height:5px;}
QSlider::sub-page:horizontal {background:#00ccff;}
QSlider::handle:horizontal {background:#8dffff;border:1px solid white;
 width:14px;margin:-6px 0;border-radius:7px;}
QSlider::groove:vertical {background:#18457e;border-radius:3px;}
QSlider::sub-page:vertical {background:#01bfff;}
QSlider::handle:vertical {background:#8df6ff;border:1px solid white;}
QTreeWidget,QTableWidget {
 background:#061735;alternate-background-color:#082852;color:#f1fbff;
 border:1px solid #1684e9;selection-background-color:#126ff3;selection-color:#fff;
}
QHeaderView::section {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
   stop:0 #0faaf3,stop:.28 #0c79cb,stop:1 #08418e);
 color:#ffffff;border-right:1px solid #35bfff;
 border-bottom:1px solid #62edff;font-weight:800;
}
QPlainTextEdit,QTextEdit {background:#041530;color:#dff7ff;
 border:1px solid #147dd4;selection-background-color:#107ef0;}
QGraphicsView {background:#051733;border:1px solid #177fe6;}
QProgressBar {background:#051e49;color:#ffffff;
 border:1px solid #198de9;border-radius:5px;}
QProgressBar::chunk {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
 stop:0 #086afa,stop:.45 #00caff,stop:1 #77ffff);border-radius:4px;}
QScrollBar:vertical {background:#04152e;}
QScrollBar::handle:vertical {background:#147be0;border:1px solid #3ee4ff;border-radius:4px;}
QScrollBar:horizontal {background:#04152e;}
QScrollBar::handle:horizontal {background:#147be0;border:1px solid #3ee4ff;border-radius:4px;}
QMenu {background:#061e42;color:#eafaff;border:1px solid #269dff;}
QMenu::item:selected {background:#117bdf;color:white;}
QToolTip {background:#08265c;color:white;border:1px solid #67ebff;}
"""

# Específico del explorador: acabado de cristal azul eléctrico coherente
# con las cabeceras de Inicio y selección brillante visible.
NEON_BROWSER_CSS = """
QDialog#StemFileBrowser {background:#010b25;color:#ffffff;
 border:2px solid #24dfff;border-radius:8px;}
QWidget#browserTop {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
    stop:0 #168fff,stop:.10 #0965cf,stop:.48 #06367d,stop:1 #051a44);
 border:2px solid #30d9ff;border-bottom:2px solid #75ffff;
 border-radius:9px;}
QLabel#browserTitle {color:#ffffff;font-weight:800;}
QLabel#browserSubtitle {color:#beeeff;}
QListWidget#browserPlaces {background:#041a44;color:#ffffff;
 border:2px solid #16caff;border-radius:8px;}
QListWidget#browserPlaces::item:selected {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #26bfff,stop:.30 #107ffc,stop:1 #074cd4);
 color:#ffffff;border-left:4px solid #8dffff;font-weight:800;}
QTreeView#browserFiles {background:#031637;color:#ffffff;
 alternate-background-color:#072354;
 border:2px solid #11c4ff;border-radius:8px;
 selection-background-color:#1179f9;selection-color:#ffffff;}
QTreeView#browserFiles::item:selected {background:#0e6be7;color:white;font-weight:800;}
QHeaderView::section {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #25cfff,stop:.15 #0c92f5,stop:1 #064cbd);
 color:#ffffff;border:0;border-right:1px solid #76f6ff;
 border-bottom:2px solid #85ffff;font-weight:800;}
QFrame#browserPanel {background:#041b47;border:2px solid #17bdff;border-radius:8px;}
QLineEdit,QComboBox {background:#082052;color:white;border:1px solid #19baff;
 selection-background-color:#1777ff;selection-color:white;}
QLineEdit:focus,QComboBox:focus {border:2px solid #92ffff;background:#0b346f;}
QPushButton {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #137cf2,stop:.30 #0a59b6,stop:1 #073473);
 color:#ffffff;border:1px solid #35ccff;border-radius:6px;}
QPushButton:hover {background:#127bf5;border:2px solid #9affff;}
QPushButton#browserPrimary {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #33ffff,stop:.22 #07ccff,stop:1 #0874ed);
 border:2px solid #adffff;color:#ffffff;font-weight:900;}
QScrollBar::handle:vertical {background:#087dff;border:1px solid #69faff;}
"""
