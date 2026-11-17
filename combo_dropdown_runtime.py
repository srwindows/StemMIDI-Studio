"""Desplegables nativos fiables en todas las ventanas de StemMIDI Studio.

Problema de origen: QComboBoxPrivateContainer acaba retenido en un
QGraphicsProxyWidget tras mover módulos de Inicio a pestañas profesionales.
Esos popups se dibujan detrás/fuera del QMainWindow; showPopup() no
comprueba si se puede pulsar realmente un elemento.

La alternativa es un QFrame(Qt.Popup) descendiente DIRECTO de la ventana
QMainWindow, no del combo embebido en la QGraphicsScene. Reutiliza el modelo
de opciones y selecciona mediante QComboBox.setCurrentIndex, conservando
todas las señales, presets, itemData, disabled y contratos del motor.
"""
from __future__ import annotations
import weakref
import shiboken6

from PySide6.QtCore import QObject, Qt, QEvent, QPoint, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QVBoxLayout, QListWidget,
    QListWidgetItem, QLabel, QWidget, QAbstractItemView, QMenu,
)

class _DropdownPopup(QFrame):
    def __init__(self, combo: QComboBox, manager: "DropdownGuard"):
        super().__init__(combo.window(), Qt.Popup | Qt.FramelessWindowHint)
        self.combo = combo
        self.manager = manager
        self.setObjectName("stemNativeDropdownPopup")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Seleccionar " + (combo.objectName() or "opción"))
        self.setStyleSheet("""
            QFrame#stemNativeDropdownPopup {
                background:#051c43; border:1px solid #41cafa;
                border-radius:5px; color:#ecfbff;
            }
            QListWidget {
                background:#071e43; color:#edfaff;
                border:0; selection-background-color:#147be1;
                selection-color:#ffffff; font-size:12px;
                outline:0; padding:1px;
            }
            QListWidget::item {
                padding:4px 8px;
                min-height:20px;
            }
            QListWidget::item:hover {
                background:#0d5cb5;
            }
            QListWidget::item:selected {
                background:#116bcb;
                color:#fff;
            }
            QScrollBar:vertical {background:#071b3b; width:10px;}
            QScrollBar::handle:vertical {
                background:#1688d8; border-radius:3px;
                min-height:20px;
            }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2,2,2,2)
        outer.setSpacing(0)
        self.list = QListWidget(self)
        self.list.setObjectName("stemNativeDropdownItems")
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        outer.addWidget(self.list)
        names=[]
        count=combo.count()
        model=combo.model()
        for i in range(count):
            item=QListWidgetItem(combo.itemIcon(i),combo.itemText(i),self.list)
            item.setData(Qt.UserRole,i)
            index=model.index(i,combo.modelColumn(),combo.rootModelIndex())
            if not bool(model.flags(index) & Qt.ItemIsEnabled):
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item.setToolTip(combo.itemText(i))
            names.append(combo.itemText(i))
        selected=max(0,combo.currentIndex())
        if selected<count:
            self.list.setCurrentRow(selected)
        self.list.itemClicked.connect(self._choose)
        self.list.itemActivated.connect(self._choose)
        width=combo.width()
        metrics=QFontMetrics(self.list.font())
        longest=max((metrics.horizontalAdvance(name) for name in names),
                    default=width)
        width=min(440,max(width,longest+42))
        width=max(width,120)
        row_height=max(24,self.list.sizeHintForRow(0)+3)
        visible_rows=min(11,count)
        total_h=max(31, row_height*visible_rows+6)
        self.resize(width,total_h)
        self.list.setFocus(Qt.PopupFocusReason)
        self._place(combo)

    def _place(self,combo):
        screen=combo.screen() or QApplication.primaryScreen()
        rect=screen.availableGeometry()
        point=combo.mapToGlobal(QPoint(0,combo.height()))
        below=rect.bottom()-point.y()
        above=combo.mapToGlobal(QPoint(0,0)).y()-rect.top()
        if below<self.height() and above>below:
            y=combo.mapToGlobal(QPoint(0,0)).y()-self.height()
        else:
            y=point.y()
        x=min(max(point.x(),rect.left()),max(rect.left(),rect.right()-self.width()))
        y=max(rect.top(),min(y,rect.bottom()-self.height()))
        self.move(x,y)

    def _choose(self,item):
        try:
            if item is None or not bool(item.flags() & Qt.ItemIsEnabled):
                return
            index=item.data(Qt.UserRole)
            if self.combo is not None and isinstance(index,int):
                self.combo.setCurrentIndex(index)
        finally:
            # Cerrar después del MouseButtonRelease, nunca destruir el
            # viewport mientras Qt aún procesa el clic de selección.
            QTimer.singleShot(0,self.close)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Enter):
            item=self.list.currentItem()
            if item is not None:self._choose(item)
            event.accept()
            return
        if event.key()==Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

class DropdownGuard(QObject):
    """Filtro único para todos los QComboBox existentes y futuros."""
    def __init__(self,root):
        super().__init__(root)
        self.root=root
        self.active_popup=None
        self._consume_release=weakref.WeakSet()
        self._arrows=weakref.WeakKeyDictionary()
        QApplication.instance().installEventFilter(self)
        self.decorate_existing()

    def _belongs(self,combo):
        if not isinstance(combo,QWidget):return False
        current=combo
        for _ in range(60):
            if current is self.root:return True
            if current is None:break
            try:current=current.parentWidget()
            except RuntimeError:return False
        return False

    def _decorate(self,combo):
        if combo in self._arrows:return
        arrow=QLabel("▾",combo)
        arrow.setObjectName("stemDropdownArrow")
        arrow.setStyleSheet(
            "QLabel#stemDropdownArrow {color:#99efff; background:transparent;"
            "border:none;font-size:15px;font-weight:800;padding:0px;}")
        arrow.setAlignment(Qt.AlignCenter)
        arrow.setAttribute(Qt.WA_TransparentForMouseEvents,True)
        self._arrows[combo]=arrow
        self._position_arrow(combo)
        arrow.show()
        arrow.raise_()

    def _position_arrow(self,combo):
        arrow=self._arrows.get(combo)
        if arrow is not None:
            arrow.setGeometry(max(0,combo.width()-21),0,19,combo.height())

    def decorate_existing(self):
        for combo in self.root.findChildren(QComboBox):
            self._decorate(combo)

    def _open(self,combo):
        if not combo.isEnabled() or not combo.count():
            return
        if self.active_popup is not None:
            try:self.active_popup.close()
            except RuntimeError:pass
            self.active_popup=None
        popup=_DropdownPopup(combo,self)
        self.active_popup=popup
        # A diferencia de QComboBox.showPopup, nunca se incrusta en la
        # QGraphicsScene de Inicio y muestra como máximo once opciones.
        popup.show()
        popup.raise_()
        popup.list.setFocus(Qt.PopupFocusReason)
        popup.list.scrollToItem(popup.list.currentItem())
        return popup

    def eventFilter(self,obj,event):
        if isinstance(obj,QMenu):
            if event.type()==QEvent.Show and self._belongs(obj):
                # Los QMenu creados desde la escena de Inicio también
                # deben recuperar una ventana popup nativa.
                try:
                    proxy=obj.graphicsProxyWidget()
                    if proxy is not None:proxy.setWidget(None)
                except RuntimeError:pass
            return False
        if not isinstance(obj,QComboBox):return False
        if not self._belongs(obj):return False
        try:
            typ=event.type()
            if typ==QEvent.Show:
                self._decorate(obj)
            elif typ==QEvent.Resize:
                self._position_arrow(obj)
            elif typ==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
                if obj.isEditable() and event.position().x()<obj.width()-27:
                    # Mantener intacta la edición de combo editable.
                    return False
                if not obj.isEnabled():return False
                self._decorate(obj)
                self._consume_release.add(obj)
                active=self.active_popup
                if active is not None and not shiboken6.isValid(active):
                    active=self.active_popup=None
                if active is not None and active.isVisible() \
                    and active.combo is obj:
                    active.close()
                    self.active_popup=None
                else:
                    # Esperar al MouseButtonRelease de la pulsación original.
                    # Mostrar un Qt.Popup EN el MouseButtonPress permite que
                    # Cocoa/Qt cierre el menú inmediatamente al soltar.
                    QTimer.singleShot(0,lambda c=obj:self._open(c)
                        if shiboken6.isValid(c) else None)
                event.accept()
                return True
            elif typ==QEvent.MouseButtonRelease and obj in self._consume_release:
                self._consume_release.discard(obj)
                event.accept()
                return True
            elif typ==QEvent.KeyPress and (
                    event.key()==Qt.Key_F4 or
                    event.key()==Qt.Key_Down and bool(event.modifiers() & Qt.AltModifier)):
                self._decorate(obj)
                self._open(obj)
                event.accept()
                return True
        except RuntimeError:
            return False
        return False

def install(root):
    manager=getattr(root,"_stem_dropdown_guard",None)
    if manager is not None:
        return manager
    manager=DropdownGuard(root)
    root._stem_dropdown_guard=manager
    return manager
