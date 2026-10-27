"""Tarjetas desbloqueables de Inicio: mismo QWidget, sin clonaciones ni cruces.

Cada candado transforma el módulo real en una ventana flotante, ampliada,
no modal y sin botón X. El candado abierto lo devuelve exactamente al
QLayout de origen. No se alteran los motores ni se duplican señales.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QEvent, QPoint, QSize, QByteArray, QTimer
from PySide6.QtGui import QCursor, QPixmap, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QFrame, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QComboBox, QLineEdit, QDoubleSpinBox, QSlider, QCheckBox,
    QSizePolicy, QGraphicsDropShadowEffect, QApplication
)
from PySide6.QtGui import QColor

LOCK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><g fill="none" stroke="#65edff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.7"><rect x="7" y="14" width="18" height="15" rx="3" fill="#0a426e"/><path d="M11 14V9a5 5 0 0 1 10 0v5"/></g></svg>"""
UNLOCK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><g fill="none" stroke="#67f2ff" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.7"><rect x="7" y="14" width="18" height="15" rx="3" fill="#0a426e"/><path d="M12 14V8a5 5 0 0 1 9-3"/></g></svg>"""

def lock_icon(unlocked=False):
    renderer=QSvgRenderer(QByteArray((UNLOCK_SVG if unlocked else LOCK_SVG).encode()))
    pixmap=QPixmap(28,28)
    pixmap.fill(Qt.transparent)
    from PySide6.QtGui import QPainter
    painter=QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)

FLOAT_STYLE = """
QFrame#floatingGlass {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #052153,stop:.35 #041a41,stop:1 #031434);
 border:2px solid #27dffe;border-radius:14px;
}
QFrame#studioCard[expandedCard="true"] {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #052153,stop:1 #031739);
 border:1px solid #34caff;border-radius:10px;
}
QFrame#studioCard[expandedCard="true"] QPushButton#studioCardHeading {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d57da,stop:1 #051f4f);
 color:#e0f8ff;font-weight:800;font-size:17px;min-height:33px;
}
QPushButton#homeLockButton {
 background:#052154;border:1px solid #2bb1fc;
 border-radius:6px;min-height:28px;max-height:32px;
 min-width:30px;max-width:32px;padding:0px;
}
QPushButton#homeLockButton:hover {background:#0d58df;border:1px solid #5bf4ff;}
QFrame#floatPanel {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #083484,stop:1 #04193f);
 border:1px solid #2bb1fc;border-radius:8px;
}
QFrame#studioCard[expandedCard="true"] QComboBox,
QFrame#studioCard[expandedCard="true"] QLineEdit,
QFrame#studioCard[expandedCard="true"] QDoubleSpinBox {
 background:#041940;color:#e0f8ff;border:1px solid #2bb1fc;border-radius:5px;
 min-height:24px;
}
QFrame#studioCard[expandedCard="true"] QCheckBox {color:#e0f8ff;}
QFrame#studioCard[expandedCard="true"] QPushButton#primary {
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #13e7f5,stop:1 #067bd6);
 border:1px solid #54f2ff;min-height:31px;font-weight:800;font-size:14px;
}
QFrame#studioCard[expandedCard="true"] QLabel#floatingTitle {
 font-size:12px;font-weight:700;color:#85f0ff;
}
"""

class FloatingCard(QDialog):
    def __init__(self,manager,card):
        super().__init__(manager.home.main,Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.manager=manager
        self.card=card
        self.setObjectName("floatingModuleWindow")
        self.setAttribute(Qt.WA_TranslucentBackground,True)
        self.setModal(False)
        self.setWindowTitle(card.header.text()+" · StemMIDI Studio")
        self.setMinimumSize(510,390)
        outer=QVBoxLayout(self)
        outer.setContentsMargins(12,12,12,12)
        outer.setSpacing(0)
        self.frame=QFrame(self)
        self.frame.setObjectName("floatingGlass")
        effect=QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(32)
        effect.setOffset(0,0)
        effect.setColor(QColor(14,201,255,125))
        self.frame.setGraphicsEffect(effect)
        outer.addWidget(self.frame)
        self.body=QVBoxLayout(self.frame)
        self.body.setContentsMargins(4,4,4,4)
        self.body.setSpacing(0)
        self._moving=False
        self._start_global=QPoint()
        self._start_position=QPoint()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:
            # Ningún cierre alternativo: el candado devuelve la tarjeta.
            self.manager.redock(self.card)
            event.accept()
        else:super().keyPressEvent(event)
    def closeEvent(self,event):
        if self.manager.is_detached(self.card):
            event.ignore()
            self.manager.redock(self.card)
        else:super().closeEvent(event)

    def hideEvent(self,event):
        super().hideEvent(event)
        if (self.manager.is_detached(self.card)
                and not self.manager._closing_all
                and self.manager._help_owner is not self.card):
            QTimer.singleShot(0,self._ensure_reachable)

    def _ensure_reachable(self):
        if self.manager.is_detached(self.card) and not self.isVisible():
            self.manager.redock(self.card)

class CardManager(QObject):
    def __init__(self,home):
        super().__init__(home)
        self.home=home
        self.cards=(
            home.mon_card,home.sep_card,home.midi_card,home.result_card,
            home.wave_card,home.drum_card,home.track_card,home.mix_card,
            home.piano_card,home.vocal_card,home.drum_stems_card,home.info_card
        )
        self.windows={}
        self.originals={}
        self._moving_card=None
        self._closing_all=False
        self._help_owner=None
        self._extra_sep_widgets=[]
        for card in self.cards:
            lock=QPushButton(card)
            lock.setObjectName("homeLockButton")
            lock.setIcon(lock_icon(False))
            lock.setIconSize(QSize(23,23))
            lock.setFixedSize(32,34)
            lock.setCursor(Qt.PointingHandCursor)
            lock.setToolTip("Desbloquear · ampliar y separar este módulo")
            # Inserción junto a '?' dentro de la misma cabecera, sin X.
            heading=card.layout().itemAt(0).layout()
            heading.insertWidget(1,lock)
            card.lock_button=lock
            lock.clicked.connect(lambda checked=False, c=card:self.toggle(c))
            card.header.setCursor(Qt.PointingHandCursor)
            card.help_button.setCursor(Qt.PointingHandCursor)
            card.header.installEventFilter(self)
            card.help_button.clicked.connect(lambda checked=False, c=card:
                QTimer.singleShot(0,lambda:self._help_opened(c)))
        from PySide6.QtGui import QShortcut,QKeySequence
        self._rescue_shortcut=QShortcut(QKeySequence("Ctrl+Shift+L"),home.main)
        self._rescue_shortcut.setContext(Qt.ApplicationShortcut)
        self._rescue_shortcut.activated.connect(self.recover_all)
        self._install_sep_extra()
        self._install_other_expanders()
        for klass in (QPushButton,QCheckBox,QComboBox,QSlider,QDoubleSpinBox):
            for widget in home.findChildren(klass):
                widget.setCursor(Qt.PointingHandCursor)

    def _install_sep_extra(self):
        from home_separation_expanded import ExpandedSeparator
        self.sep_expander=ExpandedSeparator(self.home)

    def _install_other_expanders(self):
        from home_other_expanded import ExpandedModule
        keys=("monitor","sep","midi","results","wave","drums",
              "tracks","mixer","piano","vocal","drum_stems","info")
        self.other_expanders={}
        for card,key in zip(self.cards,keys):
            if key!="sep":
                self.other_expanders[card]=ExpandedModule(self.home,key,card)

    def is_detached(self,card):
        return card in self.windows

    def toggle(self,card):
        if card in self.windows:self.redock(card)
        else:self.detach(card)

    def _help_opened(self,card):
        """La ayuda contextual no debe dejar inalcanzable una tarjeta."""
        if card not in self.windows:return
        from help_center import open_help
        dlg=open_help(self.home.main)
        owner=self.windows.get(card)
        if owner is None:return
        self._help_owner=card
        try:
            dlg.setParent(owner, Qt.Dialog | Qt.WindowStaysOnTopHint)
            dlg.setWindowModality(Qt.WindowModal)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            if not getattr(dlg,"_floating_focus_hook",False):
                dlg._floating_focus_hook=True
                dlg.finished.connect(self.restore_float_focus)
                dlg.close_btn.clicked.connect(lambda:
                    QTimer.singleShot(0,self.restore_float_focus))
        except RuntimeError:
            self.recover_all()

    def restore_float_focus(self):
        card=self._help_owner
        self._help_owner=None
        if card not in self.windows:return
        window=self.windows[card]
        if not window.isVisible():window.show()
        window.raise_()
        window.activateWindow()
        card.lock_button.setFocus()

    def recover_all(self):
        """Redock garantizado, sin cerrar procesos ni tocar archivos."""
        for card in tuple(self.windows):
            self.redock(card)

    def bring_forward(self,card):
        window=self.windows.get(card)
        if window is None:return
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def shutdown(self):
        if self._closing_all:return
        self._closing_all=True
        try:
            helpdlg=getattr(self.home.main,"_help_center",None)
            if helpdlg is not None:
                helpdlg.hide()
            self.recover_all()
        finally:
            self._closing_all=False

    def detach(self,card):
        if card in self.windows:return
        original_layout=card.parentWidget().layout()
        # El QHBoxLayout de la cuadrícula contiene la Card directamente.
        # Puede estar anidado en un QVBoxLayout: localizar el QLayoutItem real.
        root=self.home.page.layout()
        rows=[root.itemAt(i).layout() for i in range(root.count())]
        source=next((lay for lay in rows if lay is not None and lay.indexOf(card)>=0),None)
        if source is None:return
        original_index=source.indexOf(card)
        from PySide6.QtWidgets import QSpacerItem
        placeholder=QFrame(self.home.page)
        placeholder.setObjectName("floatingPlaceholder")
        placeholder.setStyleSheet(
            "QFrame#floatingPlaceholder{background:#031739;border:1px dashed #2bb1fc;border-radius:8px;}")
        placeholder.setToolTip("Módulo ampliado · pulsa su candado abierto para recuperarlo.")
        placeholder.setMinimumSize(card.minimumSize())
        placeholder.setMaximumSize(card.maximumSize())
        place=source.replaceWidget(card,placeholder)
        if place is None:raise RuntimeError("No se pudo liberar el módulo")
        old_policy=card.sizePolicy()
        old_min=card.minimumSize()
        old_max=card.maximumSize()
        self.originals[card]=(source,placeholder,old_min,old_max,old_policy,original_index)
        floatwin=FloatingCard(self,card)
        self.windows[card]=floatwin
        self._last_active_card=card
        card.setParent(floatwin.frame)
        floatwin.body.addWidget(card,1)
        card.setMinimumSize(0,0)
        card.setMaximumSize(16777215,16777215)
        card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        card.setProperty("expandedCard",True)
        card.style().unpolish(card)
        card.style().polish(card)
        card.lock_button.setIcon(lock_icon(True))
        card.lock_button.setToolTip("Bloquear · devolver este módulo a su posición original")
        for button in card.findChildren(QPushButton):
            button.setCursor(Qt.PointingHandCursor)
        floatwin.setStyleSheet(FLOAT_STYLE)
        large=card in (self.home.mon_card,self.home.midi_card,
                       self.home.track_card,self.home.mix_card,self.home.piano_card,
                       self.home.vocal_card,self.home.drum_stems_card)
        target=QSize(940 if card is self.home.sep_card else 870 if large else 800,
                     735 if card is self.home.sep_card else 830 if card is self.home.mon_card else 720 if large else 615)
        bounds=QApplication.primaryScreen().availableGeometry()
        floatwin.resize(min(target.width(),bounds.width()-30),
                        min(target.height(),bounds.height()-30))
        floatwin.move(bounds.center()-QPoint(floatwin.width()//2,floatwin.height()//2))
        floatwin.show()
        floatwin.raise_()
        floatwin.activateWindow()
        card.show()
        if card is self.home.sep_card:
            self.sep_expander.expand()
        else:
            self.other_expanders[card].expand()
        # Reproductor local en la ventana: no accede a ninguna otra pestaña.
        # Grabación ya posee REC/Play+VU propios, por lo que no se duplica.
        if card is not self.home.mon_card:
            from floating_transport import FloatingTransport
            names=dict(zip(self.cards,(
                "monitor","sep","midi","results","wave","drums",
                "tracks","mixer","piano","vocal","drum_stems","info")))
            strip=FloatingTransport(self.home,names[card],floatwin.frame)
            floatwin.body.addWidget(strip,0)
            floatwin.float_transport=strip
            screen=QApplication.primaryScreen().availableGeometry()
            desired=985 if names[card] in (
                "sep","tracks","mixer","drum_stems") else 850
            floatwin.resize(floatwin.width(),min(desired,screen.height()-28))
            floatwin.move(screen.center()-QPoint(floatwin.width()//2,floatwin.height()//2))
            strip.show()

    def redock(self,card):
        if card not in self.windows:return
        if self._help_owner is card:
            self._help_owner=None
            dlg=getattr(self.home.main,"_help_center",None)
            if dlg is not None:dlg.hide()
        window=self.windows.pop(card)
        dlg=getattr(self.home.main,"_help_center",None)
        if dlg is not None and dlg.parent() is window:
            dlg.hide()
            dlg.setParent(self.home.main,Qt.Dialog)
            dlg.setWindowModality(Qt.NonModal)
        source,placeholder,minimum,maximum,policy,idx=self.originals.pop(card)
        strip=getattr(window,"float_transport",None)
        if strip is not None:
            strip.cleanup()
            window.body.removeWidget(strip)
            strip.deleteLater()
            window.float_transport=None
        if card is self.home.sep_card:
            self.sep_expander.collapse()
        else:
            self.other_expanders[card].collapse()
        window.body.removeWidget(card)
        card.setParent(self.home.page)
        if source.replaceWidget(placeholder,card) is None:
            source.insertWidget(idx,card)
        placeholder.deleteLater()
        card.setMinimumSize(minimum)
        card.setMaximumSize(maximum)
        card.setSizePolicy(policy)
        card.setProperty("expandedCard",False)
        card.style().unpolish(card)
        card.style().polish(card)
        card.lock_button.setIcon(lock_icon(False))
        card.lock_button.setToolTip("Desbloquear · ampliar y separar este módulo")
        card.show()
        window.hide()
        window.deleteLater()

    def eventFilter(self,obj,event):
        # Pulsar cabecera mientras está ampliada arrastra, no navega de pestaña.
        for card,window in tuple(self.windows.items()):
            if obj is card.header:
                if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
                    window._moving=True
                    window._start_global=event.globalPosition().toPoint()
                    window._start_position=window.pos()
                    return True
                if event.type()==QEvent.MouseMove and window._moving:
                    diff=event.globalPosition().toPoint()-window._start_global
                    window.move(window._start_position+diff)
                    return True
                if event.type()==QEvent.MouseButtonRelease and window._moving:
                    window._moving=False
                    return True
        return False

def enable(home):
    home._floating_manager=CardManager(home)
    import dialog_guard
    dialog_guard.bind_manager(home._floating_manager)
    return home._floating_manager
