"""Elementos de interfaz adaptables: sin recortar controles por tamaño."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea,QWidget,QLayout,QSizePolicy,QFrame

def scroll_tab_pages(tabs):
    """Mantiene las páginas existentes pero permite recorrer todo su contenido."""
    previous=tabs.currentIndex()
    for i in range(tabs.count()):
        page=tabs.widget(i)
        title=tabs.tabText(i)
        icon=tabs.tabIcon(i)
        tooltip=tabs.tabToolTip(i)
        tabs.removeTab(i)
        area=QScrollArea(tabs)
        area.setObjectName("accessibleTabScroll")
        area.setFrameShape(QFrame.NoFrame)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        if page.layout() is not None:
            page.layout().setSizeConstraint(QLayout.SetMinimumSize)
        area.setWidget(page)
        tabs.insertTab(i,area,icon,title)
        tabs.setTabToolTip(i,tooltip)
    tabs.setCurrentIndex(previous)
    return tabs

def horizontal_controls(layout,parent=None):
    """Barra con desplazamiento horizontal cuando faltan píxeles.

    Se conserva el mismo layout y los mismos widgets/señales ya conectadas.
    """
    inner=QWidget()
    inner.setObjectName("accessibleControls")
    inner.setLayout(layout)
    layout.setSizeConstraint(QLayout.SetMinimumSize)
    scroll=QScrollArea(parent)
    scroll.setObjectName("accessibleControlScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    scroll.setWidget(inner)
    # Reservar espacio para una barra inferior cuando sea necesaria.
    scroll.setFixedHeight(max(48,inner.sizeHint().height()+17))
    return scroll
