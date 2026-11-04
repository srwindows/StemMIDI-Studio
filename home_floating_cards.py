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
    QMenu, QSizePolicy, QGraphicsDropShadowEffect, QApplication
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
        # Mantener el diseño propio, sin barra ni controles del sistema.
        super().__init__(manager.home.main,Qt.Tool | Qt.FramelessWindowHint)  # Solo sobre StemMIDI, no sobre Firefox/Dolphin
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
        # La cabecera azul y el margen superior son los únicos asideros.
        self.setMouseTracking(True)
        self.frame.setMouseTracking(True)
        self.frame.installEventFilter(manager)

    def _drag_start(self,event):
        # En X11/XWayland usamos arrastre por coordenadas, sin depender de
        # _NET_WM_MOVERESIZE: preserva la ventana sin decoraciones y funciona
        # también cuando la cabecera es un QPushButton.
        self._moving=True
        self._start_global=event.globalPosition().toPoint()
        self._start_position=self.pos()
        if QApplication.platformName()=="wayland":
            # Wayland no permite mover libremente un top-level desde move().
            # El movimiento nativo requiere el serial de pulsación real.
            handle=self.windowHandle()
            if handle is not None and handle.startSystemMove():
                self._moving=False
        return True

    def _drag_move(self,event):
        if not self._moving:return False
        self.move(self._start_position + event.globalPosition().toPoint()-self._start_global)
        return True

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and event.position().y()<75:
            self._drag_start(event);event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._drag_move(event):event.accept()
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self._moving:
            self._drag_move(event)
            self._moving=False
            event.accept()
        else:super().mouseReleaseEvent(event)

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
        # KDE puede ocultar transitoriamente las ventanas Qt.Tool cuando se
        # minimiza o cambia el foco de la principal. No cerrar ni devolver
        # al grid el panel por ese evento: sólo el candado/Escape lo hacen.
        super().hideEvent(event)

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
        from separator_listen import SeparatorListen
        self.home._sep_listen=SeparatorListen(self.home)
        self._mini_players={}
        self._mini_buttons={}
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
            self._install_card_play_controls(card,heading)
            lock.clicked.connect(lambda checked=False, c=card:self.toggle(c))
            card.header.setCursor(Qt.OpenHandCursor)
            card.header.setToolTip("Arrastra este título para mover el módulo flotante")
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
        # Cerrado: Resultados solo tiene inventario + Play/Pausa/Stop.
        from results_dragdrop import set_compact_results
        set_compact_results(self.home,True)
        # Vista de audio: transporte compacto SIEMPRE visible con candado
        # cerrado. Al ampliarla aparece el transporte completo de abajo.
        from floating_transport import FloatingTransport
        self.docked_wave_transport=FloatingTransport(home,"wave",home.wave_card)
        self.docked_wave_transport.set_docked_mode()
        home.wave.setMinimumHeight(41)
        home.wave_card.inner.addWidget(self.docked_wave_transport)
        for klass in (QPushButton,QCheckBox,QComboBox,QSlider,QDoubleSpinBox):
            for widget in home.findChildren(klass):
                widget.setCursor(Qt.PointingHandCursor)

    def _transport_position(self,card,kind):
        """Situar la reproducción EN el formulario, nunca junto al candado.

        Mantener cada control original en su propio módulo y sin crear filas
        adicionales cuando hay una etiqueta o barra que admite los botones.
        """
        inner=card.inner
        if kind in ("sep","drums","vocal"):
            captions={"sep":"Modelo de separación",
                      "drums":"Pista de batería del proyecto",
                      "vocal":"Voz del proyecto"}
            caption_text=captions[kind]
            index=next((i for i in range(inner.count())
                        if isinstance(inner.itemAt(i).widget(),QLabel)
                        and inner.itemAt(i).widget().text()==caption_text),-1)
            if kind=="sep":
                # Este módulo YA está bien. Mantener su fila intacta.
                row=next((inner.itemAt(i).layout() for i in range(inner.count())
                          if isinstance(inner.itemAt(i).layout(),QHBoxLayout)
                          and inner.itemAt(i).layout().count()>0
                          and inner.itemAt(i).layout().itemAt(0).widget() is not None
                          and inner.itemAt(i).layout().itemAt(0).widget().text()==caption_text),None)
                if row is not None:
                    return row
            if index<0:raise RuntimeError("No se encuentra "+caption_text)
            caption=inner.takeAt(index).widget()
            row=QHBoxLayout()
            row.setContentsMargins(0,0,0,0)
            row.setSpacing(5)
            row.addWidget(caption)
            row.addStretch(1)
            inner.insertLayout(index,row)
            return row
        if kind=="midi":
            # La fila Preset se estrecha al reducir la ventana. En cambio
            # "Detectar acordes" tiene hueco a la derecha, sin ganar altura
            # ni reducir los controles de conversión.
            index=next((i for i in range(inner.count())
                        if isinstance(inner.itemAt(i).widget(),QCheckBox)
                        and inner.itemAt(i).widget().text()=="Detectar acordes → MIDI aparte"),-1)
            if index<0:raise RuntimeError("Casilla de detección de acordes no encontrada")
            checkbox=inner.takeAt(index).widget()
            row=QHBoxLayout()
            row.setContentsMargins(0,0,0,0)
            row.setSpacing(3)
            row.addWidget(checkbox)
            row.addStretch(1)
            inner.insertLayout(index,row)
            return row
        if kind in ("mixer","piano"):
            # Barras superiores con espacio propio para la preescucha.
            index=1 if inner.itemAt(0).widget() is not None else 0
            row=inner.itemAt(index).layout()
            if not isinstance(row,QHBoxLayout):
                raise RuntimeError("Barra superior no encontrada: "+kind)
            return row
        if kind in ("tracks","drum_stems"):
            # Las filas tienen ya sus Play/Stop por pista; situar el control
            # general en un renglón compacto sin invadir ninguna onda.
            row=QHBoxLayout()
            row.setContentsMargins(0,0,0,0)
            row.setSpacing(3)
            caption=QLabel("Escucha general",card)
            caption.setStyleSheet("color:#9bdffc;font-size:10px;")
            row.addWidget(caption)
            row.addStretch(1)
            insert_at=next((i for i in range(inner.count())
                            if isinstance(inner.itemAt(i).layout(),QHBoxLayout)),1)
            inner.insertLayout(insert_at,row)
            return row
        raise RuntimeError("Transporte sin sitio válido: "+kind)

    def _install_card_play_controls(self,card,heading):
        """Controles de escucha visibles con candado cerrado, cabecera limpia."""
        if card in (self.home.mon_card,self.home.wave_card,
                    self.home.info_card,self.home.result_card):
            # Resultados ya incluye Play/Stop/Pausa de forma permanente.
            # Evitar un transporte duplicado sobre su título.
            return
        kind=dict(zip(self.cards,("monitor","sep","midi","results",
            "wave","drums","tracks","mixer","piano","vocal",
            "drum_stems","info")))[card]
        row=self._transport_position(card,kind)
        buttons=[]
        for label,tooltip,fn in (
            ("▶","Reproducir preescucha",lambda c=card,k=kind:self._mini_action(c,k,"play")),
            ("Ⅱ","Pausar preescucha",lambda c=card,k=kind:self._mini_action(c,k,"pause")),
            ("■","Detener preescucha",lambda c=card,k=kind:self._mini_action(c,k,"stop"))):
            b=QPushButton(label,card)
            b.setObjectName("homeMiniTransport")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tooltip)
            b.setFixedSize(32 if kind=="sep" else 22,29 if kind=="sep" else 22)
            b.setStyleSheet("QPushButton#homeMiniTransport{padding:0px;"
                "background:#073366;border:1px solid #239de0;"
                "border-radius:4px;color:#b9efff;font-size:12px;}")
            if kind=="mixer":
                # Dejarlos junto a la etiqueta "Escucha", a la izquierda,
                # con aire entre ellos y Restablecer.
                row.insertWidget(len(buttons),b)
            else:
                row.addWidget(b)
            b.clicked.connect(fn)
            buttons.append(b)
        if kind=="mixer":
            caption=QLabel("Escucha",card)
            caption.setStyleSheet("color:#9bdffc;font-size:10px;")
            row.insertWidget(0,caption)
        self._mini_buttons[card]=buttons
        if kind=="sep":
            select=QPushButton("♫",card)
            select.setObjectName("homeMiniTransport")
            select.setToolTip("Elegir pistas que suenan (independiente de extraer)")
            select.setFixedSize(32,29)
            select.setStyleSheet(buttons[0].styleSheet())
            menu=QMenu(select)
            self._mini_sep_menu=menu
            for name in ("Original","Voces","Batería","Bajo",
                         "Guitarra","Piano","Viento","Otros"):
                action=menu.addAction(name)
                action.setCheckable(True)
                action.triggered.connect(
                    lambda checked,n=name:self.home._sep_listen.set_enabled(n,checked))
            def refresh():
                available=self.home._sep_listen.available()
                for action in menu.actions():
                    action.setChecked(action.text() in self.home._sep_listen.selected)
                    action.setEnabled(available.get(action.text()) is not None)
            menu.aboutToShow.connect(refresh)
            select.setMenu(menu)
            row.addWidget(select)
            buttons.append(select)

    def _mini_action(self,card,kind,action):
        if kind=="sep":
            if action=="play":self.home._sep_listen.play()
            elif action=="stop":self.home._sep_listen.stop()
            else:self.home._sep_listen.pause()
            return
        window=self.windows.get(card)
        transport=getattr(window,"float_transport",None) if window else None
        if transport is None:
            transport=self._mini_players.get(card)
            if transport is None:
                from floating_transport import FloatingTransport
                transport=FloatingTransport(self.home,kind,self.home.main)
                transport.timer.stop()
                transport.hide()
                self._mini_players[card]=transport
            if transport.track_select:
                rows=(self.home.drum_stem_rows if kind in ("drums","drum_stems")
                      else self.home.track_rows)
                if kind in ("drums","drum_stems","mixer"):
                    first=next((n for n in rows if rows[n]["path"] is not None
                                and Path(rows[n]["path"]).is_file()),None)
                    if first:transport.track_select.setCurrentText(first)
                # Pistas separadas requiere elección MANUAL; no forzar Voces.
        if action=="play":transport.play_selected()
        elif action=="pause":transport.pause_selected()
        else:transport.stop_selected()

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
            dlg.setParent(owner, Qt.Dialog)  # Dialogo encima de su módulo, no global
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
            self.sep_expander.voice_task.stop()
            self.home._sep_listen.cleanup()
            for transport in self._mini_players.values():transport.cleanup()
        finally:
            self._closing_all=False

    def detach(self,card):
        if card in self.windows:return
        if card is self.home.wave_card:
            self.docked_wave_transport.hide()
            self.home.wave.setMinimumHeight(96)
        for button in self._mini_buttons.get(card,()):button.hide()
        # Ambas distribuciones usan QHBoxLayout: la posición se conserva
        # mediante placeholder para que el resto mantenga ancho y fila.
        workspace=getattr(self.home,"home_workspace",None)
        free=(workspace is not None and workspace.is_free
              and card.parentWidget() in workspace.row_surfaces)
        rows=(list(workspace.row_layouts) if free else
              [c.layout() for c in self.home._factory_containers])
        source=next((lay for lay in rows
                     if lay is not None and lay.indexOf(card)>=0),None)
        if source is None:return
        original_index=source.indexOf(card)
        placeholder=QFrame(card.parentWidget() if free else self.home.page)
        placeholder.setObjectName("floatingPlaceholder")
        placeholder.setStyleSheet(
            "QFrame#floatingPlaceholder{background:#031739;"
            "border:1px dashed #2bb1fc;border-radius:8px;}")
        placeholder.setToolTip(
            "Módulo ampliado · pulsa el candado para recuperarlo.")
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
        # El popup no debe seguir siendo hijo gráfico de Inicio.
        self._native_floating_popups(card)
        large=card in (self.home.mon_card,self.home.midi_card,
                       self.home.track_card,self.home.mix_card,self.home.piano_card,
                       self.home.vocal_card,self.home.drum_stems_card,
                       self.home.info_card)
        target=QSize(1260 if card is self.home.piano_card else
                     1190 if card is self.home.info_card else
                     1050 if card is self.home.vocal_card else
                     940 if card is self.home.sep_card else 870 if large else 800,
                     1030 if card is self.home.piano_card else
                     1004 if card is self.home.info_card else
                     925 if card is self.home.vocal_card else
                     735 if card is self.home.sep_card else
                     930 if card is self.home.mon_card else
                     720 if large else 615)
        bounds=QApplication.primaryScreen().availableGeometry()
        if card is self.home.piano_card:
            # Evita que una ventana pequeña comprima tres columnas de
            # ajustes. En pantallas pequeñas se adapta a su espacio útil.
            floatwin.setMinimumSize(min(1080,bounds.width()-30),
                                    min(970,bounds.height()-30))
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
        if card is self.home.result_card:
            from results_dragdrop import set_compact_results
            set_compact_results(self.home,False)
        router=getattr(self.home,"_result_file_drag_router",None)
        if router is not None and card in router.card_kind:
            if router.card_kind[card] not in ("monitor","results","tracks","drum_stems"):
                router.attach(card)
        # Un editor profesional puede estar acoplado a la pestaña y
        # trasladarse a la tarjeta SOLO durante expand(). Los popups Qt
        # de sus combos nacían en la QGraphicsScene de Inicio: volver a
        # liberarlos AHORA, después del traslado, para que aparezcan
        # junto al desplegable de la ventana flotante.
        self._native_floating_popups(card)
        # Reproductor local en la ventana: no accede a ninguna otra pestaña.
        # Grabación ya posee REC/Play+VU propios, por lo que no se duplica.
        if card is not self.home.mon_card and card is not self.home.info_card:
            # «MIDI a audio» tiene su propio transporte completo:
            # no añadir otra franja de reproducción duplicada.
            from floating_transport import FloatingTransport
            names=dict(zip(self.cards,(
                "monitor","sep","midi","results","wave","drums",
                "tracks","mixer","piano","vocal","drum_stems","info")))
            strip=FloatingTransport(self.home,names[card],floatwin.frame)
            floatwin.body.addWidget(strip,0)
            floatwin.float_transport=strip
            screen=QApplication.primaryScreen().availableGeometry()
            desired=(1030 if names[card]=="piano" else
                930 if names[card]=="vocal" else
                985 if names[card] in ("sep","mixer","drum_stems") else
                900 if names[card]=="midi" else
                545 if names[card]=="tracks" else 850)
            floatwin.resize(floatwin.width(),min(desired,screen.height()-28))
            floatwin.move(screen.center()-QPoint(floatwin.width()//2,floatwin.height()//2))
            strip.show()

    def _native_floating_popups(self,card):
        """Soltar los popup Qt de la QGraphicsScene de Inicio al separar
        una tarjeta. La escena puede conservar QGraphicsProxyWidgets incluso
        después de setParent(floatwin), haciendo que los menús aparezcan en
        coordenadas de Inicio (fuera de la ventana emergente).
        """
        from PySide6.QtWidgets import QMenu
        for combo in card.findChildren(QComboBox):
            try:
                widget=combo.view().window()
                self._detach_popup_proxy(widget)
                widget.installEventFilter(self)
            except RuntimeError:
                continue
        for menu in card.findChildren(QMenu):
            try:
                self._detach_popup_proxy(menu)
                menu.installEventFilter(self)
            except RuntimeError:
                continue

    def _detach_popup_proxy(self,popup):
        try:
            proxy=popup.graphicsProxyWidget()
            scene=getattr(self.home.scroll,"scene",lambda:None)()
            if proxy is not None and proxy.scene() is scene:
                # Importante: no eliminar el popup ni destruir la tarjeta.
                # setWidget(None) lo devuelve a Qt como popup nativo.
                proxy.setWidget(None)
        except RuntimeError:
            # Qt puede haber destruido un proxy previo al cerrar el menú.
            pass

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
        if card is self.home.result_card:
            from results_dragdrop import set_compact_results
            set_compact_results(self.home,True)
        window.body.removeWidget(card)
        workspace=getattr(self.home,"home_workspace",None)
        in_free=(workspace is not None and workspace.is_free
                 and source in workspace.row_layouts)
        if in_free:
            row_index=next((i for i,layout in enumerate(workspace.row_layouts)
                            if layout is source),0)
            card.setParent(workspace.row_surfaces[row_index])
        else:
            card.setParent(self.home.page)
        if source.replaceWidget(placeholder,card) is None:
            source.insertWidget(idx,card,1 if in_free else 0)
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
        if in_free and workspace is not None:
            workspace._arrange()
            workspace._sync_controls()
        if card is self.home.wave_card:
            self.home.wave.setMinimumHeight(41)
            self.docked_wave_transport.show()
        for button in self._mini_buttons.get(card,()):button.show()
        window.hide()
        window.deleteLater()

    def eventFilter(self,obj,event):
        # Interceptar menús creados tras desacoplar la tarjeta, además de
        # los que ya existían antes de abrir el candado.
        if event.type()==QEvent.Show and isinstance(obj,QWidget):
            parent=obj.parentWidget()
            while parent is not None:
                if any(parent is card or parent is window
                       for card,window in tuple(self.windows.items())):
                    self._detach_popup_proxy(obj)
                    break
                parent=parent.parentWidget()
        # Tanto el título como el margen superior son asideros. En Qt6 los
        # eventos MouseMove pueden venir del marco o del título, por eso
        # hay una única coordenada global para arrastrar sin saltos.
        for card,window in tuple(self.windows.items()):
            grip=(obj is card.header or obj is window.frame)
            if not grip:continue
            if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
                if obj is window.frame and event.position().y()>36:
                    return False
                window._drag_start(event)
                return True
            if event.type()==QEvent.MouseMove and window._moving:
                return window._drag_move(event)
            if event.type()==QEvent.MouseButtonRelease and window._moving:
                window._drag_move(event)
                window._moving=False
                return True
        return False

def enable(home):
    home._floating_manager=CardManager(home)
    from results_dragdrop import install as install_result_dragdrop
    install_result_dragdrop(home)
    import dialog_guard
    dialog_guard.bind_manager(home._floating_manager)
    return home._floating_manager
