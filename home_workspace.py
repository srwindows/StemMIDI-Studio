"""Inicio con 12 módulos reales organizados en 3 filas de 4 casillas.

Arrastrar un título sobre una casilla intercambia SOLAMENTE dos tarjetas:
la arrastrada y la que ocupaba el destino. Nunca redistribuye otras
posiciones, ni aumenta/disminuye el número de módulos en una fila.
La distribución pertenece a cada proyecto; formatos v1/v2 se migran.
"""
from __future__ import annotations

from copy import deepcopy
from math import isfinite
from PySide6.QtCore import QObject, Qt, QEvent, QPoint, QRect, QRectF, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QRubberBand,
    QSizePolicy, QMessageBox
)

IDS = (
    "monitor", "separacion", "audio_a_midi", "resultados",
    "vista_audio", "desglose_bateria", "pistas_separadas", "mezclador",
    "piano_roll", "afinacion_vocal", "bateria_pistas", "midi_a_audio",
)
TITLES = (
    "Monitor / Grabación", "Separación de audio", "Audio a MIDI", "Resultados",
    "Vista de audio", "Desglose de batería", "Pistas separadas", "Mezclador",
    "Piano Roll · MIDI", "Afinación vocal", "Batería · pistas separadas",
    "MIDI a audio",
)
FACTORY_STRETCH = (
    (27, 23, 25, 25),
    (10, 10, 11, 13),
    (37, 17, 22, 24),
)
FACTORY_ROWS = (39, 27, 29)
SLOTS_PER_ROW = 4
STABLE_ROW_HEIGHT = 288  # permite los controles completos del panel más alto


def _float(value, default):
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
        return number if isfinite(number) else default
    except (ValueError, TypeError, OverflowError):
        return default


class FreeHomeCanvas(QWidget):
    """Lienzo de la misma pantalla, SIN coordenadas libres de tarjetas."""
    def __init__(self, home):
        super().__init__(home.page)
        self.setObjectName("homeFreeWorkspace")
        self.setStyleSheet(
            "QWidget#homeFreeWorkspace{background:#031330;"
            "border:1px solid #176799;border-radius:6px;}")
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


class HomeWorkspace(QObject):
    VERSION = 3

    def __init__(self, home, rows, canvas, toolbar):
        super().__init__(home)
        self.home = home
        self.rows = tuple(rows)
        self.canvas = canvas
        self.toolbar = toolbar
        self.cards = tuple(home._floating_manager.cards)
        self.by_id = dict(zip(IDS, self.cards))
        self.ids = {card: key for key, card in self.by_id.items()}
        self.originals = {}
        for row_number, wrapper in enumerate(self.rows):
            original_layout = wrapper.layout()
            for col in range(original_layout.count()):
                item = original_layout.itemAt(col)
                card = item.widget() if item else None
                if card is not None:
                    self.originals[card] = (
                        original_layout, col,
                        FACTORY_STRETCH[row_number][col],
                        card.minimumSize(), card.maximumSize(),
                        card.sizePolicy(),
                    )
        if len(self.originals) != len(IDS):
            raise RuntimeError("Deben existir exactamente 12 módulos reales")

        self.is_free = False
        self.editing = False
        self.row_ids = [list(IDS[:4]), list(IDS[4:8]), list(IDS[8:])]
        self._drag = None
        self._restoring = False
        self._changed = False
        self._factory_names = {c: c.header.text() for c in self.cards}
        self._names = dict(zip(self.cards, TITLES))

        # Cuadrícula estable de 3 x 4; Qt mantiene las cuatro casillas
        # alineadas incluso al redimensionar el área de Inicio.
        # Reservar altura para 3 filas idénticas. FitHomeView ajusta
        # el zoom al área real, sin scroll ni solapamientos.
        self.canvas.setMinimumHeight(3*STABLE_ROW_HEIGHT+26)
        self.root_layout = QVBoxLayout(self.canvas)
        self.root_layout.setContentsMargins(5, 5, 5, 5)
        self.root_layout.setSpacing(8)
        self.row_layouts = []
        self.row_surfaces = []
        for stretch in FACTORY_ROWS:
            surface=QWidget(self.canvas)
            surface.setObjectName("homeStableRowSurface")
            surface.setMinimumSize(0,0)
            surface.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
            surface.setFixedHeight(STABLE_ROW_HEIGHT)
            line=QHBoxLayout(surface)
            line.setSpacing(8)
            line.setContentsMargins(0,0,0,0)
            self.root_layout.addWidget(surface,stretch)
            self.row_surfaces.append(surface)
            self.row_layouts.append(line)
        self.drop_indicator = QFrame(self.canvas)
        self.drop_indicator.setObjectName("homeSnapTarget")
        self.drop_indicator.setStyleSheet(
            "QFrame#homeSnapTarget{background:rgba(21,160,255,35);"
            "border:2px dashed #75f5ff;border-radius:5px;}")
        self.drop_indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.drop_indicator.hide()

        for card in self.cards:
            card.header.installEventFilter(self)
            card.header.setToolTip(
                "Organizar: arrastra esta tarjeta sobre otra para "
                "INTERCAMBIAR sus posiciones. Tres filas de cuatro.")

        self.toolbar["mode"].clicked.connect(self.toggle_mode)
        self.toolbar["edit"].clicked.connect(self.toggle_edit)
        self.toolbar["reset"].clicked.connect(self.restore_factory)
        self.toolbar["save"].clicked.connect(self.save_project_layout)
        self._sync_controls()

    def _sync_controls(self):
        toolbar = self.toolbar
        toolbar["mode"].setText(
            "Volver a distribución original" if self.is_free
            else "Organizar Inicio por filas")
        toolbar["edit"].setVisible(self.is_free)
        toolbar["reset"].setVisible(self.is_free)
        toolbar["edit"].setText(
            "Fijar distribución" if self.editing else "Mover y ordenar módulos")
        toolbar["save"].setEnabled(bool(getattr(self.home.main, "project_dir", None)))
        if self.is_free:
            toolbar["status"].setText(
                "ARRASTRA SOBRE OTRA TARJETA: solo intercambian sus casillas · 4 por fila"
                if self.editing else
                "3 filas × 4 módulos · activa «Mover y ordenar módulos» para intercambiar")
        else:
            toolbar["status"].setText(
                "12 módulos · distribución original · organización individual por proyecto")

    def toggle_mode(self):
        if self.is_free:
            answer = QMessageBox.question(
                self.home.main, "Volver a la distribución original",
                "¿Usar la cuadrícula original de Inicio? El cambio se guardará "
                "al pulsar «Guardar proyecto».",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                self.to_factory()
        else:
            self.to_free()
            self.set_editing(True)

    def restore_factory(self):
        answer = QMessageBox.question(
            self.home.main, "Restaurar Inicio",
            "¿Restaurar la cuadrícula original de los doce módulos?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.to_factory()

    def _item_for(self, key):
        """Card acoplada o su reserva en la fila mientras está flotando."""
        card = self.by_id[key]
        manager = self.home._floating_manager
        if card in manager.originals:
            return manager.originals[card][1]
        return card

    def _arrange(self):
        """Un solo QLayout por línea: no puede dejar huecos ni solapar."""
        if not self.is_free or self._restoring:
            return
        self._restoring = True
        try:
            for line in self.row_layouts:
                while line.count():
                    line.takeAt(0)
            manager = self.home._floating_manager
            for row_index, keys in enumerate(self.row_ids):
                line = self.row_layouts[row_index]
                for col, key in enumerate(keys):
                    card = self.by_id[key]
                    item = self._item_for(key)
                    if item is None:
                        continue
                    line.addWidget(item, 1)
                    if card in manager.originals:
                        src, placeholder, small, large, policy, _ = manager.originals[card]
                        manager.originals[card] = (
                            line, placeholder, small, large, policy, col)
            self.root_layout.invalidate()
            self.root_layout.activate()
        finally:
            self._restoring = False

    def _reflow(self):
        # Compatibilidad con FitHomeView: las cuatro casillas por línea
        # mantienen anchura relativa al tamaño de Inicio.
        if self.is_free:
            self.root_layout.invalidate()
            self.root_layout.activate()

    def to_free(self, positions=None):
        if self.is_free:
            return
        self.home._floating_manager.recover_all()
        self.is_free = True
        for card in self.cards:
            old_layout = self.originals[card][0]
            old_layout.removeWidget(card)
            card.setParent(self.canvas)
            card.setMinimumSize(155, 125)
            card.setMaximumSize(16777215, 16777215)
            # Ignored evita que un tamaño interno heredado (p. ej. Piano)
            # fuerce la anchura y deje a los demás módulos sin espacio.
            card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            if card is not self.home.piano_card:
                card.header.setText(self._names[card])
            card.show()
        for wrapper in self.rows:
            wrapper.hide()
        self.canvas.show()
        self._arrange()
        self._sync_controls()
        self._changed = True
        QTimer.singleShot(0, self.home.scroll.fit_all)

    def to_factory(self):
        if not self.is_free:
            return
        self.set_editing(False)
        self.home._floating_manager.recover_all()
        self.is_free = False
        self.drop_indicator.hide()
        self.canvas.hide()
        for line in self.row_layouts:
            while line.count():
                line.takeAt(0)
        for card in self.cards:
            card.hide()
            card.setParent(self.home.page)
            line, col, stretch, small, large, policy = self.originals[card]
            line.insertWidget(col, card, stretch)
            card.setMinimumSize(small)
            card.setMaximumSize(large)
            card.setSizePolicy(policy)
            card.header.setText(self._factory_names[card])
            card.show()
        for wrapper in self.rows:
            wrapper.show()
        self._sync_controls()
        self._changed = True
        QTimer.singleShot(0, self.home.scroll.fit_all)

    def set_editing(self, value):
        self.editing = bool(self.is_free and value)
        self._drag = None
        self.drop_indicator.hide()
        self._sync_controls()

    def toggle_edit(self):
        self.set_editing(not self.editing)

    def layout_for(self, card):
        key = self.ids[card]
        return next(
            (self.row_layouts[index]
             for index, contents in enumerate(self.row_ids) if key in contents),
            None)

    def _row_col_at(self, x, y, card=None):
        """Casilla real debajo de la posición de destino: 3 x 4 fijas.

        Nunca interpreta «final de fila» como inserción de una quinta
        tarjeta. Se usa la geometría de las filas y una de cuatro franjas
        iguales, independientes del orden y del módulo arrastrado.
        """
        y = max(0, min(self.canvas.height()-1, int(y)))
        x = max(0, min(self.canvas.width()-1, int(x)))
        lines = [surface.geometry() for surface in self.row_surfaces]
        row = min(range(3), key=lambda r: abs(y-lines[r].center().y()))
        bounds = lines[row]
        fraction = (x-bounds.left())/max(1,bounds.width())
        col = min(SLOTS_PER_ROW-1,
                  max(0,int(max(0.,min(1.,fraction))*SLOTS_PER_ROW)))
        return row,col

    def reorder_card(self, card, row, col):
        """Intercambiar SOLO el módulo de origen y el módulo del destino.

        Dos casillas cambian de contenido. Todas las demás conservan
        fila e índice, incluso si el movimiento atraviesa varias filas.
        """
        if not self.is_free:
            return False
        key = self.ids.get(card)
        if key is None or row not in (0,1,2):
            return False
        if not isinstance(col,int) or not 0<=col<SLOTS_PER_ROW:
            return False
        if any(len(line)!=SLOTS_PER_ROW for line in self.row_ids):
            raise RuntimeError("Inicio exige tres filas de cuatro módulos")
        original_row = next(i for i,keys in enumerate(self.row_ids)
                            if key in keys)
        original_col = self.row_ids[original_row].index(key)
        if (original_row,original_col)==(row,col):
            return False
        swapped = deepcopy(self.row_ids)
        occupant = swapped[row][col]
        first=self._item_for(key)
        second=self._item_for(occupant)
        if first is None or second is None:
            return False
        origin_line=self.row_layouts[original_row]
        destination_line=self.row_layouts[row]
        # Solo se extraen las DOS tarjetas implicadas. Las otras diez
        # quedan en sus QLayout/índices y nunca se reconstruyen sus filas.
        origin_line.removeWidget(first)
        destination_line.removeWidget(second)
        if original_row==row:
            for index,widget in sorted((
                    (original_col,second),(col,first))):
                origin_line.insertWidget(index,widget,1)
        else:
            origin_line.insertWidget(original_col,second,1)
            destination_line.insertWidget(col,first,1)
        swapped[row][col]=key
        swapped[original_row][original_col]=occupant
        self.row_ids=swapped
        # Una tarjeta flotante tiene un placeholder en la cuadrícula:
        # actualizar únicamente su destino para cuando cierre el candado.
        manager=self.home._floating_manager
        for item_key,item_row,item_col in (
                (key,row,col),(occupant,original_row,original_col)):
            item_card=self.by_id[item_key]
            if item_card in manager.originals:
                src,placeholder,small,large,policy,_=manager.originals[item_card]
                manager.originals[item_card]=(
                    self.row_layouts[item_row],placeholder,
                    small,large,policy,item_col)
        origin_line.invalidate()
        if destination_line is not origin_line:
            destination_line.invalidate()
        self.root_layout.activate()
        self._changed = True
        return True

    def _begin(self, card, event):
        self._drag = {
            "card": card,
            "rect": card.geometry(),
            "rect_canvas":QRect(
                card.mapTo(self.canvas,QPoint(0,0)),card.size()),
            "at": event.globalPosition().toPoint(),
            # Anclaje del RATÓN dentro del lienzo. Si el usuario agarra
            # la cabecera por la izquierda, el destino debe seguir siendo
            # lo que haya bajo ese punto, NO el centro de la tarjeta.
            "press_canvas":card.header.mapTo(
                self.canvas,event.position().toPoint()),
        }
        card.raise_()
        card.header.setCursor(Qt.ClosedHandCursor)

    def _projected_cursor(self,event):
        """Posición del puntero dentro del lienzo aunque el drag use zoom."""
        drag=self._drag
        factor=max(.05,abs(self.home.scroll.transform().m11()))
        delta=(event.globalPosition().toPoint()-drag["at"])/factor
        anchor=drag["press_canvas"]
        return anchor.x()+delta.x(),anchor.y()+delta.y()

    def _move(self, event):
        if self._drag is None:
            return
        card = self._drag["card"]
        x, y = self._projected_cursor(event)
        row, col = self._row_col_at(x,y,card)
        line = self.row_surfaces[row].geometry()
        slot_width = max(1, line.width()/SLOTS_PER_ROW)
        self.drop_indicator.setGeometry(
            int(line.x()+col*slot_width),
            line.y(), int(slot_width), line.height())
        self.drop_indicator.show()
        self.drop_indicator.raise_()
        # La guía resalta solo el destino. Al soltar se intercambian
        # exclusivamente origen y destino: los otros diez NO se mueven.
        origin=self._drag["rect_canvas"]
        anchor=self._drag["press_canvas"]-origin.topLeft()
        parent_pos=card.parentWidget().mapTo(self.canvas,QPoint(0,0))
        card.move(int(x-anchor.x()-parent_pos.x()),
                  int(y-anchor.y()-parent_pos.y()))

    def _release(self, event):
        if self._drag is None:
            return
        drag=self._drag
        card=drag["card"]
        x,y=self._projected_cursor(event)
        row,col=self._row_col_at(x,y,card)
        self._drag=None
        self.drop_indicator.hide()
        card.header.setCursor(Qt.OpenHandCursor)
        moved=self.reorder_card(card,row,col)
        # Si se suelta sobre sí mismo o fuera, restaurar su casilla
        # original SIN extraer ni reconstruir las otras once tarjetas.
        if not moved:
            card.setGeometry(drag["rect"])
            self.layout_for(card).invalidate()
            self.root_layout.activate()

    def eventFilter(self, obj, event):
        if not (self.is_free and self.editing) or self._restoring:
            return False
        card = next((c for c in self.cards if obj is c.header), None)
        if card is None or card.parentWidget() not in self.row_surfaces:
            return False
        if event.type() == QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
            self._begin(card,event)
            return True
        if event.type() == QEvent.MouseMove and self._drag is not None:
            if self._drag["card"] is card:
                self._move(event)
                return True
        if event.type() == QEvent.MouseButtonRelease and self._drag is not None:
            if self._drag["card"] is card:
                self._release(event)
                return True
        return False

    def floating_snapshot(self):
        result = {}
        manager = self.home._floating_manager
        for card,win in manager.windows.items():
            key = self.ids.get(card)
            if key is None:
                continue
            screen = win.screen() or QApplication.primaryScreen()
            if screen is None:
                continue
            area = screen.availableGeometry()
            result[key] = [
                round((win.x()-area.x())/max(1,area.width()),6),
                round((win.y()-area.y())/max(1,area.height()),6),
                round(win.width()/max(1,area.width()),6),
                round(win.height()/max(1,area.height()),6),
            ]
        return result

    def snapshot(self):
        return {
            "version":self.VERSION,
            "mode":"free" if self.is_free else "factory",
            "rows": deepcopy(self.row_ids),
            "order": [key for row in self.row_ids for key in row],
            "floating":self.floating_snapshot(),
        }

    @staticmethod
    def _safe_rows(raw):
        """Validar filas v2/v3, convirtiendo 5+3+4 a cuatro por fila.

        El usuario tenía distribuciones anteriores guardadas en proyectos:
        se conservan los doce módulos y su orden al migrarlas a 3 x 4.
        """
        if not isinstance(raw,list) or len(raw)!=3:
            return None
        lines=[]
        for row in raw:
            if not isinstance(row,list) or not 1<=len(row)<=5:
                return None
            if not all(isinstance(v,str) and v in IDS for v in row):
                return None
            lines.append(list(row))
        flattened=[key for row in lines for key in row]
        if len(flattened)!=len(IDS) or len(set(flattened))!=len(IDS):
            return None
        return [flattened[i:i+SLOTS_PER_ROW]
                for i in range(0,len(IDS),SLOTS_PER_ROW)]

    @staticmethod
    def _legacy_rows(data):
        """Migrar posiciones v1 a filas alineadas de cuatro elementos."""
        cards=data.get("cards")
        if not isinstance(cards,dict):
            return None
        def placement(key):
            rect=cards.get(key)
            if isinstance(rect,list) and len(rect)==4:
                return (_float(rect[1],1.),_float(rect[0],1.))
            return (1., float(IDS.index(key))/len(IDS))
        ordering=sorted(IDS,key=placement)
        return [ordering[:4],ordering[4:8],ordering[8:]]

    def restore(self,data):
        self.home._floating_manager.recover_all()
        self.to_factory()
        self.row_ids=[list(IDS[:4]),list(IDS[4:8]),list(IDS[8:])]
        if not isinstance(data,dict):
            self._sync_controls()
            return
        version=data.get("version")
        if version in (2,self.VERSION):
            self.row_ids=self._safe_rows(data.get("rows")) or self.row_ids
        elif version==1:
            self.row_ids=self._legacy_rows(data) or self.row_ids
        else:
            return
        if data.get("mode")=="free":
            self.to_free()
            self.set_editing(False)

        floating=data.get("floating",{})
        if isinstance(floating,dict):
            for key,geometry in floating.items():
                card=self.by_id.get(key)
                if card is None or not isinstance(geometry,list) or len(geometry)!=4:
                    continue
                values=[_float(v,-1) for v in geometry]
                if any(v<0 for v in values):
                    continue
                self.home._floating_manager.detach(card)
                win=self.home._floating_manager.windows.get(card)
                if win is None:
                    continue
                screen=QApplication.primaryScreen()
                if screen is None:
                    continue
                area=screen.availableGeometry()
                x,y,w,h=values
                ww=min(max(win.minimumWidth(),int(area.width()*w)),area.width())
                hh=min(max(win.minimumHeight(),int(area.height()*h)),area.height())
                xx=max(area.left(),min(area.right()-ww+1,
                                       area.left()+int(area.width()*x)))
                yy=max(area.top(),min(area.bottom()-hh+1,
                                      area.top()+int(area.height()*y)))
                win.resize(ww,hh)
                win.move(xx,yy)
        self._changed=False

    def reset_for_project(self):
        self.restore(None)

    def save_project_layout(self):
        if not getattr(self.home.main,"project_dir",None):
            QMessageBox.information(
                self.home.main,"Guardar distribución",
                "Abre o crea un proyecto para conservar la organización.")
            return
        from studio_shell import save_project
        if save_project(self.home.main,show_confirmation=False):
            self._changed=False
            self.toolbar["status"].setText("Filas organizadas y guardadas en este proyecto.")
