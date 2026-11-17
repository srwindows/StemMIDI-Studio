"""Piano Roll tab only: full editor + real floating tools in a professional dock.

Moves the exact existing tool widgets between the tab and the floating card.
No change to playback, MIDI algorithms, other tabs, or the float's native UI.
"""
from __future__ import annotations
import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSignalBlocker, QObject, QEvent, QPoint
from PySide6.QtWidgets import (
    QFrame, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout,
    QTabWidget, QScrollArea, QSplitter, QLayout, QSizePolicy,
    QAbstractItemView, QProgressBar, QListWidgetItem, QComboBox, QPushButton, QSlider, QCheckBox, QSpinBox, QDoubleSpinBox,
    QGraphicsRectItem, QGraphicsSimpleTextItem
)


class _PianoMidiDrop(QObject):
    """Accept local MIDI drops from Results/mixer on the real project list."""
    def __init__(self,owner,widget):
        super().__init__(widget)
        self.owner=owner
        self.list=widget
        widget.setAcceptDrops(True)
        widget.viewport().setAcceptDrops(True)
        widget.setDragEnabled(True)
        widget.setDragDropMode(QAbstractItemView.DragDrop)
        widget.installEventFilter(self)
        widget.viewport().installEventFilter(self)

    def eventFilter(self,obj,event):
        if (self.owner._floating or
                obj not in (self.list,self.list.viewport())):
            return False
        kind=event.type()
        if kind in (QEvent.DragEnter,QEvent.DragMove,QEvent.Drop):
            from results_dragdrop import valid_mime_paths
            paths=valid_mime_paths(event.mimeData())
            valid=bool(paths and all(p.suffix.lower() in
                            ('.mid','.midi','.kar') for p in paths))
            if not valid:
                event.ignore()
                return True
            if kind==QEvent.Drop:
                for file in paths:
                    if not self.owner._load_project_midi(file):
                        event.ignore()
                        return True
                event.setDropAction(Qt.CopyAction)
                event.accept()
            else:
                event.setDropAction(Qt.CopyAction)
                event.accept()
            return True
        return False


class PianoRollTabPro:
    def __init__(self, main):
        self.main=main
        self.piano=main.workbench.piano
        home=main.studio_home
        self.home=home
        self.bridge=home._floating_manager.advanced_parity_bridges[home.piano_card]
        assert self.bridge.kind=='piano'
        self.tools=self.bridge.expanded.piano_tools
        self._packed=False
        self._floating=False
        self._piano_default_settings=None
        self._preset_soundfont_initialised=False
        self._build_workspace()
        self._capture_tools()
        self._pack_tools()
        self._organize_top_and_left()
        self._connect_soundfont_to_composer()
        self._rearrange_tool_tabs()
        self._fix_tab_keyboard_zoom()
        self._bridge_to_float=self.bridge.to_floating
        self._bridge_to_tab=self.bridge.to_tab
        self.bridge.to_floating=self._to_floating
        self.bridge.to_tab=self._to_tab
        # No extra timer or file scan while other tabs are visible.
        main.tabs.currentChanged.connect(self._tab_changed)
        self.piano.midiOpened.connect(self._on_midi_opened)
        self._vu_timer=QTimer(self.piano)
        self._vu_timer.setInterval(90)
        self._vu_timer.timeout.connect(self._refresh_live_vus)
        self._vu_timer.start()
        QTimer.singleShot(0,self._finish_layout)
        QTimer.singleShot(0,self._apply_global_transport_visibility)
        QTimer.singleShot(0,self._init_composition_if_visible)

    def _build_workspace(self):
        piano=self.piano
        root=piano.content_layout
        assert root.count()==5,('Unexpected Piano Roll tab contents',root.count())
        # Preserve original header/source chooser (MIDI project selection).
        for name in ('transport','host','edition','grid'):
            item=root.takeAt(1)
            widget=item.widget()
            assert widget is not None,('Missing piano section',name)
            setattr(self,name,widget)
        assert self.host is self.bridge.host
        # The old whole-page scrolling pushed the actual edit grid below
        # the screen. Only individual tool tabs may scroll now.
        root.setSizeConstraint(QLayout.SetDefaultConstraint)
        root.setContentsMargins(7,3,7,5)
        root.setSpacing(4)
        piano.content_page.setMinimumSize(0,0)
        piano.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        piano.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        piano.page_scroll.setMinimumSize(0,0)

        self.splitter=QSplitter(Qt.Horizontal,piano.content_page)
        self.splitter.setObjectName('pianoStudioBodySplitter')
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        self.splitter.setStyleSheet("""
            QSplitter#pianoStudioBodySplitter::handle:horizontal{
              background:#103d65;border-left:2px solid #42b8e6;
              border-right:2px solid #42b8e6;border-radius:3px;
            }
            QSplitter#pianoStudioBodySplitter::handle:horizontal:hover{
              background:#1486ac;border-color:#7defff;
            }
        """)
        self.left=QFrame(self.splitter)
        self.left.setObjectName('pianoStudioEditorCanvas')
        ll=QVBoxLayout(self.left)
        ll.setContentsMargins(0,0,0,0)
        ll.setSpacing(4)
        # Full-width transport: at 1100px a left-only transport could not
        # fit both the progress scrubber and the horizontal stereo meters.
        self.transport.setParent(piano.content_page)
        self.grid.setParent(self.left)
        self.transport.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
        self.grid.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        ll.addWidget(self.grid,1)
        # The tab already has a MIDI/transport header. Remove the two
        # redundant SectionCard headings and their large padding so the
        # interactive piano grid gets another ~50px on laptop displays.
        for card in (self.transport,self.grid):
            header=card.layout().itemAt(0).widget()
            if header is not None:header.hide()
            card.body.setContentsMargins(6,3,6,3)
            card.body.setSpacing(3)
        self.left.setMinimumWidth(440)

        self.right=QFrame(self.splitter)
        self.right.setObjectName('pianoStudioToolsDock')
        self.right.setStyleSheet("""
          QFrame#pianoStudioToolsDock {background:#051c3d;
            border:1px solid #318bc7;border-radius:5px;}
          QTabWidget#pianoStudioToolsTabs::pane {
            border:1px solid #318bc7;background:#061b3b;
          }
          QTabWidget#pianoStudioToolsTabs QTabBar::tab {
            padding:5px 5px;min-height:22px;font-size:10px;
            margin-right:1px;
          }
        """)
        rl=QVBoxLayout(self.right)
        rl.setContentsMargins(3,3,3,3)
        rl.setSpacing(2)
        self.tabs=QTabWidget(self.right)
        self.tabs.setObjectName('pianoStudioToolsTabs')
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.tabBar().setExpanding(False)
        rl.addWidget(self.tabs,1)
        self.right.setMinimumWidth(380)
        self.right.setMaximumWidth(490)

        self.pages={}
        for key,title in (
            ('project','MIDI'),('correction','Limpiar'),
            ('composition','Componer'),('edition','Editar'),
            ('session','Sesión')
        ):
            area=QScrollArea(self.tabs)
            area.setObjectName('pianoStudioToolsScroll_'+key)
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            inner=QWidget(area)
            inner.setObjectName('pianoStudioToolsContent_'+key)
            body=QVBoxLayout(inner)
            body.setContentsMargins(4,4,4,5)
            body.setSpacing(6)
            body.setAlignment(Qt.AlignTop)
            area.setWidget(inner)
            self.pages[key]=(area,inner,body)
            self.tabs.addTab(area,title)

        # On demand, expose the floating Piano Roll's FluidSynth / SF2
        # program browser and REAL PCM playback in the tab's Session area.
        # Do not open another synth during startup or other module use.
        self._direct_transport=None
        self.tabs.currentChanged.connect(self._tool_tab_changed)

        # The original piano-roll section "Edición, zoom y tempo" is kept
        # intact and MOVED only in this tab; nothing is reconstructed.
        self.edition.setParent(self.pages['edition'][1])
        self.edition.setMinimumWidth(0)
        self.pages['edition'][2].addWidget(self.edition)
        self._make_edition_fit()

        self.splitter.addWidget(self.left)
        self.splitter.addWidget(self.right)
        self.splitter.setStretchFactor(0,7)
        self.splitter.setStretchFactor(1,4)
        root.addWidget(self.transport,0)
        root.addWidget(self.splitter,1)

        # Avoid an oversized 400px minimum inherited from the floating
        # editor; the editing grid expands with the available actual tab.
        self.roll_split=self.grid.findChild(QSplitter)
        assert self.roll_split is not None
        self._previous_roll_min=self.roll_split.minimumHeight()
        self.roll_split.setMinimumHeight(210)
        self.grid.setMinimumHeight(225)
        self.left.setMinimumHeight(0)
        self.splitter.setMinimumHeight(0)
        self.transport.setMaximumHeight(112)

        # Shared parity host is kept alive for detached mode, but no longer
        # wastes a 500px-high area above the grid in the tab.
        self.host.hide()
        self.host.setParent(piano.content_page)
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.pages['composition'][0]))

    def _organize_top_and_left(self):
        """R35 — only the Piano Roll tab: reclaim both dead transport rows."""
        piano=self.piano
        header=piano.content_layout.itemAt(0).layout()
        assert isinstance(header,QHBoxLayout) and header.count()==3
        source_row=header.itemAt(2).layout()
        assert isinstance(source_row,QHBoxLayout)
        header.removeItem(source_row)
        # Keep the actual stateful choice alive for project synchronization,
        # but the users now select files from the VISIBLE left-hand catalog.
        while source_row.count():
            entry=source_row.takeAt(0)
            if entry.widget() is not None:
                entry.widget().hide()
                entry.widget().setParent(piano.content_page)
        piano.file_label.setMaximumWidth(155)
        piano.file_label.setToolTip(
            "Archivo MIDI actualmente editado; selección de archivos a la izquierda")
        piano.file_label.show()
        header.addWidget(piano.file_label)
        header.setSpacing(5)

        # Move the existing note-edit actions into the title bar rather
        # than leaving an orphan toolbar below the piano roll.
        actions=self.grid.body.itemAt(1).layout()
        assert isinstance(actions,QHBoxLayout)
        for button in (piano.delete_button,piano.copy_button,piano.paste_button):
            actions.removeWidget(button)
            button.setParent(piano.content_page)
            button.setMinimumWidth(0)
            button.setMaximumHeight(29)
            button.setStyleSheet("QPushButton{font-size:11px;padding:3px 6px;}")
            header.addWidget(button)
        actions.removeWidget(piano.listen_toggle)
        piano.listen_toggle.hide()
        piano.listen_toggle.setParent(piano.content_page)
        actions.removeWidget(piano.stats)
        piano.stats.setParent(piano.content_page)
        piano.stats.hide()
        self.grid.body.removeItem(actions)

        # Keep PreviewPlayer as the EXISTING audio backend; remove the
        # redundant bottom transport, its controls and its meter entirely.
        self.grid.body.removeWidget(piano.preview)
        piano.preview.setParent(piano.content_page)
        piano.preview.hide()

        # Existing singleton "Conservar compases y figuras" is a stored
        # internal tempo mode, not an actionable list. Hide the dead combo.
        assert piano.tempo_mode.count()==1
        piano.tempo_mode.hide()
        piano.tempo_mode.setToolTip(
            "Conservar figuras y compases: BPM modifica solo el tempo MIDI")

        # The same genuine MIDI project catalog from the floating view
        # moves above the per-file track/channel list. No duplicate lists.
        self._track_panel=self.roll_split.widget(0)
        self._track_panel.setMinimumWidth(0)
        self._track_panel.setMaximumWidth(16777215)
        self._track_layout=self._track_panel.layout()
        self._track_layout.setContentsMargins(3,3,3,4)
        self._track_layout.setSpacing(4)
        self._project_frame=self._frames[0][0]
        self._project_layout=self._project_frame.layout()
        self._float_file_sizes=(
            self._project_frame.minimumHeight(),self._project_frame.maximumHeight(),
            self._project_frame.sizePolicy(),
            self.tools.files.minimumHeight(),self.tools.files.maximumHeight(),
            self.tools.files.sizePolicy(),
            self.tools.files.acceptDrops(),
            self.tools.files.viewport().acceptDrops(),
            self.tools.files.dragEnabled(),self.tools.files.dragDropMode())
        self._project_frame.setMinimumHeight(0)
        self._project_frame.setMaximumHeight(240)
        self._project_frame.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        self.tools.files.setMinimumHeight(95)
        self.tools.files.setMaximumHeight(180)
        self.tools.files.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self._project_layout.addWidget(piano.reload_midis)
        piano.reload_midis.setParent(self._project_frame)
        piano.reload_midis.setText("Actualizar archivos")
        piano.reload_midis.show()
        piano.reload_midis.clicked.connect(self._refresh_project_files)
        self._project_drop=_PianoMidiDrop(self,self.tools.files)
        self.tools.files.itemActivated.connect(self.tools.select_file)
        self._track_layout.insertWidget(0,self._project_frame,1)
        # Visually separate the file inventory from the tracks inside it.
        self._track_layout.itemAt(1).widget().setText("PISTAS DEL MIDI SELECCIONADO")
        self.piano.tracks_list.setMinimumHeight(75)
        self.piano.tracks_list.setMaximumHeight(145)

        # The editor can be 300px tall on a laptop. Scroll ONLY the left
        # inspector when needed, never the piano grid or the entire page.
        self._track_scroller=QScrollArea()
        self._track_scroller.setObjectName("pianoProjectTracksInspector")
        self._track_scroller.setFrameShape(QFrame.NoFrame)
        self._track_scroller.setWidgetResizable(True)
        self._track_scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._track_scroller.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._track_scroller.setMinimumWidth(185)
        self._track_scroller.setMaximumWidth(300)
        old=self.roll_split.replaceWidget(0,self._track_scroller)
        assert old is self._track_panel,(old,self._track_panel)
        self._track_scroller.setWidget(old)
        self.roll_split.setSizes([235,max(440,self.roll_split.width()-235)])

        # The MIDI tab is redundant now that its complete real catalog is
        # permanently visible on the left; the other FOUR tools stay intact.
        project_index=self.tabs.indexOf(self.pages['project'][0])
        if project_index>=0:self.tabs.removeTab(project_index)

        # Editor has the real precision number boxes. Both actual sliders
        # are always reachable in a compact row directly above the grid.
        self._build_compact_transport()
        self._assemble_single_top_bar()
        self._simplify_track_inspector()
        self._set_catalog_contrast()
        self._refresh_project_files()

    def _build_compact_transport(self):
        piano=self.piano
        transport_scroll=self.transport.body.itemAt(0).widget()
        assert isinstance(transport_scroll,QScrollArea)
        native_row=transport_scroll.widget().layout()
        assert isinstance(native_row,QHBoxLayout)
        pos_row=self.transport.body.itemAt(1).layout()
        assert isinstance(pos_row,QHBoxLayout)
        pos_row.removeWidget(piano.timeline)
        piano.timeline.setParent(transport_scroll.widget())
        pos_row.removeWidget(piano.bar_position)
        piano.bar_position.setParent(transport_scroll.widget())
        piano.timeline.setMinimumWidth(90)
        piano.timeline.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        native_row.insertWidget(native_row.indexOf(piano.position_label),
                                piano.timeline,1)
        native_row.insertWidget(native_row.indexOf(piano.position_label),
                                piano.bar_position)
        # One single horizontal transport row; remove dead position-only
        # row and the empty "POSICIÓN" label.
        for item in list((pos_row.itemAt(i) for i in range(pos_row.count()))):
            if item and item.widget():item.widget().hide()
        self.transport.body.removeItem(pos_row)
        for button in (piano.to_start,piano.rewind,piano.play_roll,
                       piano.pause_roll,piano.stop_roll,piano.forward,piano.to_end):
            button.setMinimumWidth(26)
            button.setMaximumWidth(46 if button is piano.play_roll else 36)
            button.setStyleSheet(
                "QPushButton{font-size:11px;min-height:25px;padding:2px 2px;}")
        # The preset selector belongs to the editing tools, not transport.
        native_row.removeWidget(piano.view_presets_toggle)
        piano.view_presets_toggle.setParent(self.pages['edition'][1])
        self.pages['edition'][2].insertWidget(0,piano.view_presets_toggle)

        # Two genuine stereo meters: source is the same PCM measurement as
        # the player, never a simulated activity visualization.
        from studio_vu_unified import UnifiedPercentBar
        self.meter_panel=QFrame(transport_scroll.widget())
        self.meter_panel.setObjectName('pianoTopHorizontalVus')
        vum=QVBoxLayout(self.meter_panel)
        vum.setContentsMargins(2,0,2,0)
        vum.setSpacing(1)
        self.vus={}
        for channel in ('L','R'):
            row=QHBoxLayout()
            row.setContentsMargins(0,0,0,0)
            row.setSpacing(3)
            label=QLabel(channel,self.meter_panel)
            label.setFixedWidth(10)
            row.addWidget(label)
            meter=UnifiedPercentBar(self.meter_panel)
            meter.setRange(0,100)
            meter.setValue(0)
            meter.setTextVisible(False)
            meter.setFixedHeight(8)
            meter.setFixedWidth(95)
            row.addWidget(meter)
            vum.addLayout(row)
            self.vus[channel]=meter
        native_row.insertWidget(native_row.indexOf(piano.position_label),
                                self.meter_panel,0)
        self.transport.setMaximumHeight(120)

        # The two real existing zoom sliders, with their exact numeric
        # editors, are permanently accessible directly under transport.
        zoom_row=QHBoxLayout()
        zoom_row.setContentsMargins(4,0,4,0)
        zoom_row.setSpacing(5)
        for label,slider,digit in (
            ('Zoom H',piano.zoom,piano.zoom_digit),
            ('Zoom V',piano.zoom_vertical,piano.zoom_vertical_digit)):
            zoom_row.addWidget(QLabel(label),0)
            slider.setParent(self.transport)
            slider.setMinimumWidth(48)
            slider.setMaximumWidth(190)
            zoom_row.addWidget(slider,1)
            digit.setParent(self.transport)
            digit.setMinimumWidth(68)
            digit.setMaximumWidth(103)
            zoom_row.addWidget(digit,0)
        zoom_row.addStretch(0)
        self.transport.body.addLayout(zoom_row)
        transport_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        transport_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        transport_scroll.setFixedHeight(40)

    def _assemble_single_top_bar(self):
        """Exactly one top bar: title, real transport, scrub, stereo VU,
        timer, horizontal and vertical zoom. No separate toolbar or dropdown.
        """
        piano=self.piano
        root=piano.content_layout
        header=root.itemAt(0).layout()
        assert isinstance(header,QHBoxLayout)
        title=header.itemAt(0).widget()
        assert isinstance(title,QLabel)
        title.setText("PIANO ROLL")
        title.setToolTip("Editor de notas MIDI")
        title.setMinimumWidth(72)
        title.setMaximumWidth(106)
        title.setStyleSheet("font-weight:800;font-size:12px;")
        while header.count()>1:
            item=header.takeAt(1)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().setParent(piano.content_page)
        # The R35 transport scroll widget is no longer a scrolling row.
        native=self.transport.body.itemAt(0).widget().widget().layout()
        assert isinstance(native,QHBoxLayout)
        buttons=(piano.to_start,piano.rewind,piano.play_roll,
                 piano.pause_roll,piano.stop_roll,piano.forward,piano.to_end)
        ordered=(*buttons,piano.loop_toggle,piano.follow_cursor,
                 piano.timeline,self.meter_panel,piano.position_label)
        for widget in ordered:
            native.removeWidget(widget)
            widget.setParent(piano.content_page)
            if widget in buttons:
                widget.setMaximumWidth(35 if widget is not piano.play_roll else 48)
                widget.setMinimumWidth(24)
            if widget is piano.timeline:
                widget.setMinimumWidth(65)
                widget.setMaximumWidth(16777215)
                widget.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
                header.addWidget(widget,1)
            else:
                header.addWidget(widget,0)
            widget.show()
        piano.loop_toggle.setText("Bucle")
        piano.follow_cursor.setText("Seguir cursor")
        self.meter_panel.setMaximumWidth(100)
        piano.position_label.setMinimumWidth(77)
        piano.position_label.setMaximumWidth(100)
        piano.position_label.setStyleSheet("font-size:10px;")
        # The musical bar counter and precise zoom numbers still receive
        # state updates internally; they are not extra visible controls.
        for widget in (piano.bar_position,piano.file_label,
                       piano.zoom_digit,piano.zoom_vertical_digit):
            widget.setParent(piano.content_page)
            widget.hide()
        for label,slider in (("H",piano.zoom),("V",piano.zoom_vertical)):
            caption=QLabel(label,piano.content_page)
            caption.setFixedWidth(12)
            caption.setToolTip("Zoom horizontal" if label=="H"
                               else "Zoom vertical")
            header.addWidget(caption,0)
            slider.setParent(piano.content_page)
            slider.setMinimumWidth(43)
            slider.setMaximumWidth(102)
            slider.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            slider.setToolTip("Zoom "+("horizontal" if label=="H" else "vertical"))
            header.addWidget(slider,1)
            slider.show()
        header.setSpacing(3)
        header.setContentsMargins(2,0,2,0)
        root.removeWidget(self.transport)
        self.transport.hide()
        self._title_bar=header
        self._title_label=title

    def _simplify_track_inspector(self):
        """One selected track at a time; other channels via the dropdown."""
        p=self.piano
        lay=self._track_layout
        # Library title and style belong exclusively to the docked tab.
        caption=self._project_layout.itemAt(0).widget()
        assert isinstance(caption,QLabel)
        self._floating_catalog_caption=caption.text()
        caption.setText("ARCHIVOS DEL PROYECTO")
        # Delete only the redundant Refresh button from this tab. No
        # change to the floating window and no new mandatory refresh.
        self._project_layout.removeWidget(p.reload_midis)
        p.reload_midis.hide()
        p.reload_midis.setParent(p.content_page)

        # The actual QTreeWidget remains the authoritative model; show a
        # single selected track using a QComboBox instead of many rows.
        track_label=lay.itemAt(1).widget()
        assert isinstance(track_label,QLabel)
        track_label.setText("PISTA SELECCIONADA")
        p.tracks_list.hide()
        self.track_choice=QComboBox(self._track_panel)
        self.track_choice.setObjectName('pianoSelectedInternalTrack')
        self.track_choice.setToolTip(
            "Una sola pista visible. Abre la lista para elegir otra "
            "pista interna del MIDI; la rejilla cambia automáticamente.")
        self.track_choice.setMinimumWidth(0)
        lay.insertWidget(2,self.track_choice,0)
        self.track_choice.currentIndexChanged.connect(self._choose_internal_track)
        p.tracks_list.currentItemChanged.connect(
            lambda current,previous:self._sync_internal_track_choice())
        p.midiOpened.connect(lambda _:self._sync_internal_track_choice())
        p.notesChanged.connect(self._sync_internal_track_if_changed)

        # Remove note-properties widgets and 'Quantize selected' from left;
        # all advanced edit controls remain in the existing EDITAR tool tab.
        for index in range(lay.count()):
            item=lay.itemAt(index)
            widget=item.widget()
            if widget is p.tracks_list or widget is self._project_frame:
                continue
            if widget is not None:
                txt=widget.text().strip() if isinstance(widget,QLabel) else (
                    widget.text().strip() if hasattr(widget,'text') else "")
                if txt.startswith("Nota seleccionada") or widget is p.selected_label:
                    widget.hide()
                if widget.objectName()=="inner" or txt.startswith("Cuantizar pista"):
                    widget.hide()
            if item.layout() is not None:
                inner=item.layout()
                if any(inner.itemAt(i).widget() is p.velocity
                       for i in range(inner.count())):
                    for i in range(inner.count()):
                        inner_item=inner.itemAt(i)
                        if inner_item.widget() is not None:
                            inner_item.widget().hide()
        # These existing three buttons are now directly below the selected
        # track. Their native slots (delete/copy/paste) are unchanged.
        row=QHBoxLayout()
        row.setContentsMargins(0,2,0,1)
        row.setSpacing(3)
        for button,text in ((p.delete_button,"Eliminar selección"),
                            (p.copy_button,"Copiar"),
                            (p.paste_button,"Pegar")):
            self._title_bar.removeWidget(button)
            button.setParent(self._track_panel)
            button.setText(text)
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setStyleSheet("QPushButton{font-size:10px;padding:3px 2px;}")
            button.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            row.addWidget(button,1)
            button.show()
        lay.addLayout(row)
        self._sync_internal_track_choice()

    def _sync_internal_track_choice(self):
        if not hasattr(self,'track_choice'):return
        tree=self.piano.tracks_list
        current=tree.currentItem()
        selected=tree.indexOfTopLevelItem(current) if current else -1
        with QSignalBlocker(self.track_choice):
            self.track_choice.clear()
            for i in range(tree.topLevelItemCount()):
                item=tree.topLevelItem(i)
                # Only the currently selected track is displayed in the
                # closed control, while every other track can be chosen.
                self.track_choice.addItem(
                    item.text(0)+" · "+item.text(1)+" notas",i)
            if selected>=0:
                self.track_choice.setCurrentIndex(selected)
        self.track_choice.setEnabled(tree.topLevelItemCount()>0)

    def _sync_internal_track_if_changed(self):
        if not hasattr(self,'track_choice'):return
        tree=self.piano.tracks_list
        if self.track_choice.count()!=tree.topLevelItemCount():
            self._sync_internal_track_choice()
        elif 0<=tree.indexOfTopLevelItem(tree.currentItem())<self.track_choice.count():
            i=tree.indexOfTopLevelItem(tree.currentItem())
            item=tree.topLevelItem(i)
            label=item.text(0)+" · "+item.text(1)+" notas"
            if self.track_choice.itemText(i)!=label:
                with QSignalBlocker(self.track_choice):
                    self.track_choice.setItemText(i,label)

    def _choose_internal_track(self,index):
        item=self.piano.tracks_list.topLevelItem(index)
        if item is not None:
            self.piano.tracks_list.setCurrentItem(item)

    def _set_catalog_contrast(self):
        catalog=self.tools.files
        self._float_catalog_qss=catalog.styleSheet()
        self._tab_catalog_qss="""
        QListWidget#rollMidiFiles {
          color:#e7f9ff;background:#071a34;
          alternate-background-color:#0b2b4b;
          border:1px solid #38aee7;border-radius:3px;
          selection-background-color:#075d91;
          selection-color:#ffffff;font-size:12px;
        }
        QListWidget#rollMidiFiles::item {
          color:#e7f9ff;background:#09213e;
          min-height:23px;padding:2px 5px;
          border-bottom:1px solid #16476b;
        }
        QListWidget#rollMidiFiles::item:alternate {
          background:#103351;color:#e7f9ff;
        }
        QListWidget#rollMidiFiles::item:selected {
          background:#086fa7;color:#ffffff;
          border-left:3px solid #58f3e4;
        }
        QListWidget#rollMidiFiles::item:hover {
          background:#17527a;color:#ffffff;
        }
        """
        catalog.setAlternatingRowColors(True)
        catalog.setStyleSheet(self._tab_catalog_qss)

    def _rearrange_tool_tabs(self):
        """Full labels and the requested left-to-right tool order.

        Keep the four existing pages/widgets; no tool cloned or removed.
        Undo/Redo operate on the editor history, whereas Reset ONLY
        restores settings, never deletes user notes.
        """
        order=(('composition','Componer'),('edition','Editar'),
               ('correction','Limpiar'),('session','SF2'))
        previous=self.tabs.blockSignals(True)
        try:
            for index,(key,title) in enumerate(order):
                page=self.pages[key][0]
                old_index=self.tabs.indexOf(page)
                assert old_index>=0,(key,old_index)
                self.tabs.removeTab(old_index)
                self.tabs.insertTab(index,page,title)
                self.tabs.setTabToolTip(index,title)
            self.tabs.setCurrentIndex(0)
        finally:
            self.tabs.blockSignals(previous)
        self.tabs.tabBar().setExpanding(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.setUsesScrollButtons(False)
        self.right.setMinimumWidth(402)
        self.right.setMaximumWidth(510)
        self.tabs.setStyleSheet("""
          QTabWidget#pianoStudioToolsTabs::pane{
            border:1px solid #318bc7;background:#061b3b;}
          QTabWidget#pianoStudioToolsTabs QTabBar::tab{
            min-width:75px;min-height:25px;
            padding:5px 8px;margin-right:1px;
            font-size:12px;font-weight:700;color:#c9e9ff;
            background:#0b3152;border:1px solid #326d99;}
          QTabWidget#pianoStudioToolsTabs QTabBar::tab:selected{
            background:#157fbd;color:#fff;border-color:#56cdff;}
        """)
        # Persistent editor controls outside the scrollable tool page.
        toolbar=QHBoxLayout()
        toolbar.setContentsMargins(3,3,3,1)
        toolbar.setSpacing(6)
        self.undo_action=QPushButton("Deshacer",self.right)
        self.redo_action=QPushButton("Rehacer",self.right)
        self.reset_action=QPushButton("Reset",self.right)
        for button in (self.undo_action,self.redo_action,self.reset_action):
            button.setMinimumWidth(0)
            button.setMinimumHeight(29)
            button.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            toolbar.addWidget(button,1)
        self.undo_action.setObjectName('pianoTabUndo')
        self.redo_action.setObjectName('pianoTabRedo')
        self.reset_action.setObjectName('pianoTabDefaults')
        self.undo_action.setToolTip('Deshacer la última edición de notas o composición MIDI')
        self.redo_action.setToolTip('Rehacer la edición MIDI deshecha')
        self.reset_action.setToolTip(
            'Restablecer ajustes de composición, limpieza, edición, zoom y SF2. '
            'NO borrar las notas ni sobrescribir el archivo MIDI.')
        self.undo_action.clicked.connect(self.piano.undo)
        self.redo_action.clicked.connect(self.piano.redo)
        self.reset_action.clicked.connect(self._reset_piano_settings)
        self.right.layout().addLayout(toolbar)
        # Guard against accidentally treating "Adaptarse al MIDI" as new
        # composition when no actual musical reference exists in this song.
        self._generator_buttons=(self.tools.gen_melody,self.tools.gen_chords)
        for button,callback,role in (
            (self.tools.gen_melody,self.tools.generate_melody,'melody'),
            (self.tools.gen_chords,self.tools.generate_chords,'harmony')
        ):
            button.clicked.disconnect(callback)
            button.clicked.connect(lambda _=False,r=role:self._generate_in_tab(r))
        self.tools.harmony_mode.setToolTip(
            'Composición nueva: progresión/melodía nueva según ajustes. '
            'Adaptarse al MIDI: utilizar las notas y acordes existentes '
            'como referencia para generar una parte musical compatible.')
        self.tools.instrument_style.setToolTip(
            'Familias disponibles en el SoundFont SF2 actualmente cargado.')
        self.tools.instrument_preset.setToolTip(
            'Únicamente instrumentos de la familia SF2 seleccionada arriba.')

    def _generate_in_tab(self,role):
        """Reuse floating engine, but never fake "Adaptarse" without notes."""
        if self._floating or not self._packed:
            return (self.tools.generate_melody() if role=='melody'
                    else self.tools.generate_chords())
        if self.tools.harmony_mode.currentIndex()==0:
            e=self.piano
            if e.midi is None or not e.tracks:
                self.tools.info.setText(
                    'Para adaptar, abre un MIDI con acordes o melodía.')
                return
            from composition_registers import bar_ticks
            meter=self.tools._midi_meter(e)
            start=self.tools._generation_start_tick(e,meter)
            span=self.tools.bars.value()*bar_ticks(e.ticks_per_beat,meter)
            reference=[note for track in e.tracks
                       if self.tools._track_role(track)!=role
                       for note in track['notes']
                       if note['start']<start+span and note['end']>start]
            if not reference:
                self.tools.info.setText(
                    'Adaptarse al MIDI: no hay '
                    +('acordes' if role=='melody' else 'melodía')
                    +' de referencia en los compases elegidos. '
                    'Dibuja o carga notas, o selecciona Composición nueva.')
                return
        if role=='melody':
            return self.tools.generate_melody()
        return self.tools.generate_chords()

    def _capture_piano_settings(self):
        if self._piano_default_settings is not None:return
        tracked=[]
        for name,widget in vars(self.tools).items():
            if name in ('instrument_style','instrument_preset'):continue
            if isinstance(widget,(QSlider,QSpinBox,QDoubleSpinBox)):
                tracked.append((widget,widget.value()))
            elif isinstance(widget,QCheckBox):
                tracked.append((widget,widget.isChecked()))
            elif isinstance(widget,QComboBox):
                tracked.append((widget,widget.currentIndex()))
        # Editor-side view/tools also have independent defaults.
        for widget in (self.piano.zoom,self.piano.zoom_vertical,
                       self.piano.grid,self.piano.tool):
            if isinstance(widget,(QSlider,QSpinBox,QDoubleSpinBox)):
                tracked.append((widget,widget.value()))
            elif isinstance(widget,QComboBox):
                tracked.append((widget,widget.currentIndex()))
        self._piano_default_settings=tracked

    def _reset_piano_settings(self):
        from soundfont_catalog import system_soundfont
        self._ensure_composer_soundfont()
        for widget,value in self._piano_default_settings or ():
            if isinstance(widget,QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget,QComboBox):
                if 0<=value<widget.count():widget.setCurrentIndex(value)
            else:widget.setValue(value)
        transport=self._direct_transport
        default_sf2=system_soundfont()
        if transport is not None and default_sf2 is not None:
            transport.piano_live.select_soundfont(default_sf2)
            transport._piano_refresh_banks()
            # Prefer the original bank-0 GM acoustic piano, not an
            # arbitrary bank-8 piano or user-loaded preset.
            family=next((i for i in range(transport.sf2_family.count())
                         if transport.sf2_family.itemData(i)==(0,0)),0)
            transport.sf2_family.setCurrentIndex(family)
            piano=next((i for i in range(transport.sf2_program.count())
                        if transport.sf2_program.itemData(i)==(0,0)),0)
            transport.sf2_program.setCurrentIndex(piano)
            self.tools.sync_soundfont_catalog(transport)
        self.tools.info.setText(
            'Ajustes por omisión restaurados · notas MIDI conservadas.')

    def _connect_soundfont_to_composer(self):
        """The tab shares actual SF2 voices with its hidden native player."""
        self._original_sound_transport=self.tools._piano_sound_transport
        self.tools._piano_sound_transport=lambda: (
            self._original_sound_transport() if self._floating
            else self._direct_transport or self._original_sound_transport())

    def _init_composition_if_visible(self):
        if (self.main.tabs.currentWidget() is self.piano
                and not self._floating):
            self._ensure_composer_soundfont()

    def _ensure_composer_soundfont(self):
        if self._floating:return
        if self._direct_transport is None:
            # Same tested FluidSynth/SF2 transport as the floating window,
            # created only when Piano Roll is first opened.
            from floating_transport import FloatingTransport
            parent=self.pages['session'][1]
            self._direct_transport=FloatingTransport(self.home,'piano',parent)
            self._direct_transport.setObjectName('pianoTabSF2DirectTransport')
            self._direct_transport.setMinimumWidth(0)
            self._direct_transport.sf2_family.setMinimumWidth(0)
            self._direct_transport.sf2_program.setMinimumWidth(0)
            self._direct_transport.clock.setMaximumWidth(90)
            self._direct_transport.timeline.setMinimumWidth(0)
            self._direct_transport.hide()
            self._direct_transport.timer.stop()
        if not self._preset_soundfont_initialised:
            # Bundled FluidR3 GM is the tab's initial SoundFont. Once loaded
            # the user can switch to a custom SF2 without being overridden.
            from soundfont_catalog import system_soundfont
            bundled=system_soundfont()
            if bundled is not None:
                try:
                    self._direct_transport.piano_live.select_soundfont(bundled)
                    self._direct_transport._piano_refresh_banks()
                except (ValueError,OSError) as exc:
                    self.tools.info.setText('SF2: '+str(exc))
            self._preset_soundfont_initialised=True
        self.tools.sync_soundfont_catalog(self._direct_transport)
        self._capture_piano_settings()

    def _fix_tab_keyboard_zoom(self):
        """Single sticky keyboard; minimum zoom fills the whole viewport."""
        from piano_roll import HIGH,LOW,RULER,KEY_WIDTH
        p=self.piano
        self._base_redraw=p.redraw
        self._base_row_zoom=p.set_row_zoom
        self._base_beat_zoom=p.set_beat_zoom

        def redraw_unique_keyboard():
            self._base_redraw()
            # The QGraphicsView.drawForeground() already paints the
            # stationary keyboard/ruler. Delete the old scene copies;
            # otherwise the user sees two simultaneous keyboards.
            for item in list(p.scene.items()):
                if isinstance(item,QGraphicsRectItem):
                    rect=item.rect()
                    if (abs(rect.x())<.01 and
                        abs(rect.width()-(KEY_WIDTH-2))<.1 and
                        rect.y()>=RULER-.01):
                        p.scene.removeItem(item)
                elif isinstance(item,QGraphicsSimpleTextItem):
                    if item.pos().x()<KEY_WIDTH-10 and item.pos().y()>=RULER-2:
                        p.scene.removeItem(item)
            p.view.viewport().update()

        def minimum_row_zoom():
            h=max(1,p.view.viewport().height())
            return max(.5,min(48.,(h-RULER-1)/(HIGH-LOW+1)))

        def row_zoom_limited(value,redraw=True):
            return self._base_row_zoom(max(float(value),minimum_row_zoom()),
                                       redraw=redraw)

        def minimum_beat_zoom():
            notes=p.current_notes
            if notes and p.midi:
                ticks=max(n['end'] for n in notes)
                beats=max(1.,ticks/max(1,p.ticks_per_beat))
            else:
                # Empty lanes: always show 16 musical bars in the viewport,
                # never a tiny four-bar graphic amid hundreds of empty bars.
                beats=64.
            width=max(30,p.view.viewport().width()-KEY_WIDTH-10)
            return max(.000001,min(300.,width/(beats+.25)))

        def beat_zoom_limited(value,redraw=True):
            return self._base_beat_zoom(max(float(value),minimum_beat_zoom()),
                                        redraw=redraw)

        p.redraw=redraw_unique_keyboard
        p.set_row_zoom=row_zoom_limited
        p.set_beat_zoom=beat_zoom_limited
        self._zoom_guard_timer=QTimer(p)
        self._zoom_guard_timer.setSingleShot(True)
        self._zoom_guard_timer.timeout.connect(self._enforce_piano_zoom_limits)
        p.midiOpened.connect(lambda _:self._enforce_piano_zoom_limits())
        # Existing zoom actions call self.set_*_zoom dynamically, so the
        # constraints apply to sliders, wheel, numeric edit and presets.
        self._enforce_piano_zoom_limits()

    def _enforce_piano_zoom_limits(self):
        p=self.piano
        # Reuse the wrapped MIDI editor zoom functions. None of the notes
        # or existing MIDI files is changed.
        p.set_row_zoom(p.row_px,redraw=False)
        p.set_beat_zoom(p.beat_px,redraw=False)
        p.redraw()
        if p.current_notes:
            p.focus_notes()
        else:
            p.view.horizontalScrollBar().setValue(0)
            p.view.verticalScrollBar().setValue(0)

    def _make_edition_fit(self):
        piano=self.piano
        transport_scroll=self.transport.body.itemAt(0).widget()
        assert isinstance(transport_scroll,QScrollArea)
        native_row=transport_scroll.widget().layout()
        assert isinstance(native_row,QHBoxLayout)
        pos_row=self.transport.body.itemAt(1).layout()
        assert isinstance(pos_row,QHBoxLayout)
        pos_row.removeWidget(piano.timeline)
        piano.timeline.setParent(transport_scroll.widget())
        pos_row.removeWidget(piano.bar_position)
        piano.bar_position.setParent(transport_scroll.widget())
        piano.timeline.setMinimumWidth(90)
        piano.timeline.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        native_row.insertWidget(native_row.indexOf(piano.position_label),
                                piano.timeline,1)
        native_row.insertWidget(native_row.indexOf(piano.position_label),
                                piano.bar_position)
        # One single horizontal transport row; remove dead position-only
        # row and the empty "POSICIÓN" label.
        for item in list((pos_row.itemAt(i) for i in range(pos_row.count()))):
            if item and item.widget():item.widget().hide()
        self.transport.body.removeItem(pos_row)
        for button in (piano.to_start,piano.rewind,piano.play_roll,
                       piano.pause_roll,piano.stop_roll,piano.forward,piano.to_end):
            button.setMinimumWidth(26)
            button.setMaximumWidth(46 if button is piano.play_roll else 36)
            button.setStyleSheet(
                "QPushButton{font-size:11px;min-height:25px;padding:2px 2px;}")
        # The preset selector belongs to the editing tools, not transport.
        native_row.removeWidget(piano.view_presets_toggle)
        piano.view_presets_toggle.setParent(self.pages['edition'][1])
        self.pages['edition'][2].insertWidget(0,piano.view_presets_toggle)

        # Two genuine stereo meters: source is the same PCM measurement as
        # the player, never a simulated activity visualization.
        from studio_vu_unified import UnifiedPercentBar
        self.meter_panel=QFrame(transport_scroll.widget())
        self.meter_panel.setObjectName('pianoTopHorizontalVus')
        vum=QVBoxLayout(self.meter_panel)
        vum.setContentsMargins(2,0,2,0)
        vum.setSpacing(1)
        self.vus={}
        for channel in ('L','R'):
            row=QHBoxLayout()
            row.setContentsMargins(0,0,0,0)
            row.setSpacing(3)
            label=QLabel(channel,self.meter_panel)
            label.setFixedWidth(10)
            row.addWidget(label)
            meter=UnifiedPercentBar(self.meter_panel)
            meter.setRange(0,100)
            meter.setValue(0)
            meter.setTextVisible(False)
            meter.setFixedHeight(8)
            meter.setFixedWidth(95)
            row.addWidget(meter)
            vum.addLayout(row)
            self.vus[channel]=meter
        native_row.insertWidget(native_row.indexOf(piano.position_label),
                                self.meter_panel,0)
        self.transport.setMaximumHeight(120)

        # The two real existing zoom sliders, with their exact numeric
        # editors, are permanently accessible directly under transport.
        zoom_row=QHBoxLayout()
        zoom_row.setContentsMargins(4,0,4,0)
        zoom_row.setSpacing(5)
        for label,slider,digit in (
            ('Zoom H',piano.zoom,piano.zoom_digit),
            ('Zoom V',piano.zoom_vertical,piano.zoom_vertical_digit)):
            zoom_row.addWidget(QLabel(label),0)
            slider.setParent(self.transport)
            slider.setMinimumWidth(48)
            slider.setMaximumWidth(190)
            zoom_row.addWidget(slider,1)
            digit.setParent(self.transport)
            digit.setMinimumWidth(68)
            digit.setMaximumWidth(103)
            zoom_row.addWidget(digit,0)
        zoom_row.addStretch(0)
        self.transport.body.addLayout(zoom_row)
        transport_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        transport_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        transport_scroll.setFixedHeight(40)

    def _refresh_project_files(self):
        if not self._packed:return
        self.tools.refresh_files(force=True)
        # KAR is also an ordinary MIDI container accepted by this editor.
        catalog=self.tools.files
        existing={str(catalog.item(i).data(Qt.UserRole))
                  for i in range(catalog.count())}
        imported=[Path(x) for x in self.home._gather_files()
                  if Path(x).suffix.lower()=='.kar' and Path(x).is_file()]
        if (self.piano.current_path is not None and
                self.piano.current_path.suffix.lower()=='.kar'):
            imported.append(self.piano.current_path)
        with QSignalBlocker(catalog):
            for path in imported:
                absolute=str(path.resolve())
                if absolute in existing:continue
                entry=QListWidgetItem(path.name)
                entry.setData(Qt.UserRole,absolute)
                entry.setToolTip(absolute)
                catalog.addItem(entry)
                existing.add(absolute)
        return len(existing)

    def _load_project_midi(self,path):
        path=Path(path)
        if (not path.is_file() or path.is_symlink()
                or path.suffix.lower() not in ('.mid','.midi','.kar')):
            return False
        # Use the original floating tool's loader and selection bookkeeping
        # to keep the project, results, current MIDI and piano notes in sync.
        existing=next((self.tools.files.item(i)
                    for i in range(self.tools.files.count())
                    if self.tools.files.item(i).data(Qt.UserRole)==str(path.resolve())),None)
        if existing is None:
            existing=QListWidgetItem(path.name)
            existing.setData(Qt.UserRole,str(path.resolve()))
            self.tools.files.addItem(existing)
        self.tools.select_file(existing)
        success=(self.piano.current_path==path.resolve())
        if success:
            self._refresh_project_files()
            current=next((self.tools.files.item(i)
                for i in range(self.tools.files.count())
                if self.tools.files.item(i).data(Qt.UserRole)==str(path.resolve())),None)
            if current is not None:
                with QSignalBlocker(self.tools.files):
                    self.tools.files.setCurrentItem(current)
        return success

    def _refresh_live_vus(self):
        if self.main.tabs.currentWidget() is not self.piano:
            return
        measured=(0.,0.)
        transport=self._direct_transport
        if (transport is not None and transport.isVisible()
                and transport.piano_live.running
                and not transport.piano_live.engine.paused):
            pcm=transport.piano_live.engine.levels
            measured=(max(pcm[0],pcm[2]),max(pcm[1],pcm[3]))
        else:
            player=self.piano.preview
            active=bool(player._play_process is not None or player._qt_active)
            vu=getattr(player,'_measured_vu',None)
            if active and not player._paused and vu is not None:
                i=int(max(0,player._position())/100)
                if 0<=i<len(vu.levels):
                    gain=player.volume.value()/100.
                    measured=(vu.levels[i][0]*gain,vu.levels[i][1]*gain)
        for channel,value in zip(('L','R'),measured):
            db=20*math.log10(max(1e-8,value))
            self.vus[channel].setValue(max(0,min(100,round((db+60)*100/60))))
            self.vus[channel].setToolTip(f'{channel}: {db:.1f} dBFS'
                                               if value>0 else 'Silencio')

    def _apply_global_transport_visibility(self):
        bar=getattr(self.main,'studio_midi_transport',None)
        if bar is None:return
        if self.main.tabs.currentWidget() is self.piano:
            # Native global bar remains intact for all other modules.
            if bar.preview._qt_active or bar.preview._render is not None:
                bar.stop()
            bar.hide()

    def _make_edition_fit(self):
        """Compact all native editing/zoom/tempo toolbars, same controls."""
        from PySide6.QtWidgets import QAbstractScrollArea
        body=self.edition.body
        for row in range(body.count()):
            item=body.itemAt(row)
            wrapper=item.widget()
            if wrapper is None:
                continue
            if isinstance(wrapper,QScrollArea):
                inner=wrapper.widget()
                layout=inner.layout()
                if not isinstance(layout,QHBoxLayout):
                    continue
                widgets=self._take_widgets(layout)
                if not widgets:
                    continue
                layout.setSizeConstraint(QLayout.SetDefaultConstraint)
                layout.setContentsMargins(0,0,0,0)
                compact=QGridLayout()
                compact.setContentsMargins(2,2,2,2)
                compact.setHorizontalSpacing(5)
                compact.setVerticalSpacing(5)
                layout.addLayout(compact)
                for i,widget in enumerate(widgets):
                    widget.setParent(inner)
                    compact.addWidget(widget,i//2,i%2)
                    widget.setMinimumWidth(0)
                    if isinstance(widget,QLabel):
                        widget.setWordWrap(True)
                wrapper.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                wrapper.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                wrapper.setFixedHeight(max(48,36*((len(widgets)+1)//2)+8))
                inner.setMinimumWidth(0)
            elif wrapper is self.piano.roll_presets:
                # Native preset strip: two columns, no hidden horizontal
                # overflow, full choices and Save/Delete still functional.
                preset=wrapper
                layout=preset.layout()
                widgets=self._take_widgets(layout)
                compact=QGridLayout()
                compact.setContentsMargins(2,2,2,2)
                compact.setSpacing(4)
                layout.addLayout(compact)
                for i,widget in enumerate(widgets):
                    widget.setParent(preset)
                    compact.addWidget(widget,i//2,i%2)
                    widget.setMinimumWidth(0)
                preset.setMaximumHeight(155)
                preset.setMinimumHeight(0)
                preset.setVisible(True)

    def _capture_tools(self):
        root=self.tools.layout()
        assert root.count()==4,('Floating Piano Roll structure changed',root.count())
        self._old_root=root
        self._old_cols=root.takeAt(0).layout()
        self._old_actions=root.takeAt(0).layout()
        self._old_sustain=root.takeAt(0).layout()
        self._old_info=root.takeAt(0).widget()
        assert self._old_cols and self._old_actions and self._old_sustain
        for layout in (self._old_cols,self._old_actions,self._old_sustain):
            # QLayout.takeAt removes the layout ITEM, but QObject ownership
            # can still point to its old parent. Detach it explicitly to
            # allow safe repeated float/dock cycles.
            layout.setParent(None)
        self._frames=[]
        for i in range(3):
            item=self._old_cols.takeAt(0)
            widget=item.widget()
            assert widget is not None
            self._frames.append((widget,widget.minimumWidth()))
        assert len(self._frames)==3
        self._action_widgets=self._take_widgets(self._old_actions)
        self._sustain_widgets=self._take_widgets(self._old_sustain)
        assert len(self._action_widgets)==5,self._action_widgets
        assert len(self._sustain_widgets)==5,self._sustain_widgets
        # On the tab, wrap the two overlong composition rows. On the
        # floating card they are restored byte-for-byte (same widgets).
        self._composition_wrapped=[]
        self._old_info_wordwrap=self._old_info.wordWrap()
        self._old_tool_height=(self.tools.minimumHeight(),self.tools.maximumHeight())
        self._old_scroll_height=(self.bridge.scroll.minimumHeight(),
                                 self.bridge.scroll.maximumHeight())
        self._old_extra_size=(self.bridge.extra.minimumHeight(),
                              self.bridge.extra.maximumHeight())

    @staticmethod
    def _take_widgets(layout):
        widgets=[]
        while layout.count():
            item=layout.takeAt(0)
            if item.widget() is not None:
                widgets.append(item.widget())
        return widgets

    def _wrap_composition_rows(self):
        if self._composition_wrapped:return
        column=self.tools.composition_column
        for row_index in (8,10,11,12):
            row=column.itemAt(row_index).layout()
            assert isinstance(row,QHBoxLayout),(row_index,row)
            widgets=self._take_widgets(row)
            expected={8:3,10:2,11:4,12:4}[row_index]
            assert len(widgets)==expected,(row_index,len(widgets))
            if row_index==8:
                # Three long checkboxes need two short lines on a laptop.
                group=QVBoxLayout()
                group.setContentsMargins(0,0,0,0);group.setSpacing(3)
                first=QHBoxLayout()
                first.setContentsMargins(0,0,0,0)
                first.addWidget(widgets[0]);first.addWidget(widgets[1])
                group.addLayout(first)
                group.addWidget(widgets[2])
            elif row_index==10:
                # Keep the generator action and its independent setting
                # legible, rather than abbreviating either label.
                group=QVBoxLayout()
                group.setContentsMargins(0,0,0,0);group.setSpacing(3)
                group.addWidget(widgets[0])
                group.addWidget(widgets[1])
            elif row_index==11:
                # Two INDEPENDENT horizontal rows: a QGridLayout would
                # impose the 220px width of the two different combos on
                # both columns and force a horizontal scrollbar.
                group=QVBoxLayout()
                group.setContentsMargins(0,0,0,0)
                group.setSpacing(4)
                progression=QHBoxLayout()
                progression.setContentsMargins(0,0,0,0)
                progression.addWidget(widgets[0],1)
                progression.addWidget(widgets[3])
                style=QHBoxLayout()
                style.setContentsMargins(0,0,0,0)
                style.addWidget(widgets[1])
                style.addWidget(widgets[2],1)
                group.addLayout(progression)
                group.addLayout(style)
            else:
                group=QGridLayout()
                group.setContentsMargins(0,0,0,0)
                group.setSpacing(4)
                for i,j,widget in ((0,0,widgets[0]),(0,1,widgets[1]),
                                   (1,0,widgets[2]),(1,1,widgets[3])):
                    group.addWidget(widget,i,j)
            minimums={widget:widget.minimumWidth() for widget in widgets}
            for widget in widgets:
                widget.setMinimumWidth(0)
            row.addLayout(group)
            self._composition_wrapped.append((row,group,widgets,minimums))

    def _unwrap_composition_rows(self):
        def clear(layout):
            while layout.count():
                item=layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().setParent(self.tools)
                elif item.layout() is not None:
                    clear(item.layout())
        for row,group,widgets,minimums in self._composition_wrapped:
            row.removeItem(group)
            clear(group)
            for widget in widgets:
                widget.setMinimumWidth(minimums[widget])
                row.addWidget(widget)
        self._composition_wrapped=[]

    def _pack_tools(self):
        if self._packed:return
        # The native float re-added its three layouts. Remove them again
        # before placing their real child widgets in the dock's pages.
        while self._old_root.count():
            self._old_root.takeAt(0)
        for layout in (self._old_cols,self._old_actions,self._old_sustain):
            layout.setParent(None)
        for frame,_ in self._frames:
            self._old_cols.removeWidget(frame)
        for widget in self._action_widgets:
            self._old_actions.removeWidget(widget)
        for widget in self._sustain_widgets:
            self._old_sustain.removeWidget(widget)
        self._wrap_composition_rows()
        # Single source of truth. These are the EXACT same four groups used
        # by the floating Piano Roll, reparented only when tab is docked.
        for key,(frame,minimum) in zip(
            ('project','correction','composition'),self._frames):
            if key=='project':
                parent=self._track_panel if hasattr(self,'_track_panel') else self.pages[key][1]
                layout=(self._track_layout if hasattr(self,'_track_layout')
                        else self.pages[key][2])
                frame.setParent(parent)
                if hasattr(self,'_track_layout'):
                    layout.insertWidget(0,frame,1)
                    frame.setMinimumHeight(0)
                    frame.setMaximumHeight(240)
                    frame.setSizePolicy(
                        QSizePolicy.Expanding,QSizePolicy.Preferred)
                    self.tools.files.setMinimumHeight(95)
                    self.tools.files.setMaximumHeight(180)
                    self.tools.files.setSizePolicy(
                        QSizePolicy.Expanding,QSizePolicy.Expanding)
                    self._project_layout.removeWidget(self.piano.reload_midis)
                    self.piano.reload_midis.hide()
                    self.piano.reload_midis.setParent(self.piano.content_page)
                    if hasattr(self,'_floating_catalog_caption'):
                        self._project_layout.itemAt(0).widget().setText(
                            "ARCHIVOS DEL PROYECTO")
                        self.tools.files.setStyleSheet(self._tab_catalog_qss)
                    self.tools.files.setAcceptDrops(True)
                    self.tools.files.viewport().setAcceptDrops(True)
                    self.tools.files.setDragEnabled(True)
                    self.tools.files.setDragDropMode(QAbstractItemView.DragDrop)
                else:
                    layout.addWidget(frame)
            else:
                _,parent,layout=self.pages[key]
                frame.setParent(parent)
                layout.addWidget(frame)
            frame.setMinimumWidth(0)
            frame.show()
        _,parent,layout=self.pages['session']
        name=self._action_widgets
        caption,namefield,new,recover,add=name
        for widget in self._action_widgets+self._sustain_widgets:
            widget.setParent(parent)
        namerow=QHBoxLayout()
        namerow.addWidget(caption)
        namerow.addWidget(namefield,1)
        layout.addLayout(namerow)
        buttons=QHBoxLayout()
        buttons.addWidget(new,1);buttons.addWidget(recover,1)
        layout.addLayout(buttons)
        layout.addWidget(add)
        sustain_label,sustain,readout,apply,tie=self._sustain_widgets
        layout.addWidget(sustain_label)
        span=QHBoxLayout()
        span.addWidget(sustain,1);span.addWidget(readout)
        layout.addLayout(span)
        sustain_buttons=QHBoxLayout()
        sustain_buttons.addWidget(apply,1);sustain_buttons.addWidget(tie,1)
        layout.addLayout(sustain_buttons)
        self._old_info.setParent(parent)
        layout.addWidget(self._old_info)
        self._old_info.setWordWrap(True)
        if self._direct_transport is not None:
            self._direct_transport.setParent(parent)
            layout.addWidget(self._direct_transport)
            self._direct_transport.show()

        # Retain just one vertical scrollbar in the currently selected tool
        # page; the Piano Roll grid never moves away off-screen.
        self.bridge.extra.setMinimumHeight(0)
        self.bridge.extra.setMaximumHeight(16777215)
        self.tools.setMinimumHeight(0)
        self.tools.setMaximumHeight(16777215)
        self.bridge.scroll.setMinimumHeight(0)
        self.bridge.scroll.setMaximumHeight(16777215)
        self._packed=True
        self._floating=False
        self.host.hide()
        self.right.show()

    def _restore_tools_for_floating(self):
        if not self._packed:return
        self._unwrap_composition_rows()
        if self._direct_transport is not None:
            transport=self._direct_transport
            transport.stop_selected()
            transport.timer.stop()
            self.pages['session'][2].removeWidget(transport)
            transport.setParent(self.piano.content_page)
            transport.hide()
        if hasattr(self,'_track_layout'):
            # These controls have been visible ONLY in the Piano tab.
            # Keep the floating three-column window exactly as before.
            self._project_layout.removeWidget(self.piano.reload_midis)
            self.piano.reload_midis.hide()
            self.piano.reload_midis.setParent(self.piano.content_page)
            if hasattr(self,'_floating_catalog_caption'):
                self._project_layout.itemAt(0).widget().setText(
                    self._floating_catalog_caption)
                self.tools.files.setStyleSheet(self._float_catalog_qss)
            (min_h,max_h,policy,min_list,max_list,list_policy,
             drops,viewdrops,drag,dragmode)=self._float_file_sizes
            self._project_frame.setMinimumHeight(min_h)
            self._project_frame.setMaximumHeight(max_h)
            self._project_frame.setSizePolicy(policy)
            self.tools.files.setMinimumHeight(min_list)
            self.tools.files.setMaximumHeight(max_list)
            self.tools.files.setSizePolicy(list_policy)
            self.tools.files.setAcceptDrops(drops)
            self.tools.files.viewport().setAcceptDrops(viewdrops)
            self.tools.files.setDragEnabled(drag)
            self.tools.files.setDragDropMode(dragmode)
        for key,(frame,minimum) in zip(
            ('project','correction','composition'),self._frames):
            if key=='project' and hasattr(self,'_track_layout'):
                self._track_layout.removeWidget(frame)
            else:
                self.pages[key][2].removeWidget(frame)
            frame.setParent(self.tools)
            frame.setMinimumWidth(minimum)
            self._old_cols.addWidget(frame)
        _,parent,layout=self.pages['session']
        # Clear original temporary rows, removing their widgets (not
        # deleting them), then reassemble the FLOATING layout unchanged.
        while layout.count():
            item=layout.takeAt(0)
            if item.layout() is not None:
                sub=item.layout()
                while sub.count():
                    subitem=sub.takeAt(0)
                    if subitem.widget() is not None:
                        subitem.widget().setParent(self.tools)
            elif item.widget() is not None:
                item.widget().setParent(self.tools)
        for widget in self._action_widgets:
            self._old_actions.addWidget(widget)
        for widget in self._sustain_widgets:
            self._old_sustain.addWidget(widget)
        self._old_info.setParent(self.tools)
        self._old_info.setWordWrap(self._old_info_wordwrap)
        for layout in (self._old_cols,self._old_actions,self._old_sustain):
            layout.setParent(None)
        self._old_root.addLayout(self._old_cols,1)
        self._old_root.addLayout(self._old_actions)
        self._old_root.addLayout(self._old_sustain)
        self._old_root.addWidget(self._old_info)
        self.tools.setMinimumHeight(self._old_tool_height[0])
        self.tools.setMaximumHeight(self._old_tool_height[1])
        self.bridge.extra.setMinimumHeight(self._old_extra_size[0])
        self.bridge.extra.setMaximumHeight(self._old_extra_size[1])
        self.bridge.scroll.setMinimumHeight(self._old_scroll_height[0])
        self.bridge.scroll.setMaximumHeight(self._old_scroll_height[1])
        self._packed=False
        self._floating=True

    def _to_floating(self):
        if self.bridge.docked:
            self._restore_tools_for_floating()
        answer=self._bridge_to_float()
        self.right.hide()
        return answer

    def _to_tab(self):
        answer=self._bridge_to_tab()
        if self.bridge.docked:
            self._pack_tools()
            if (self.main.tabs.currentWidget() is self.piano
                    and self.tabs.currentWidget() is self.pages['session'][0]):
                self._tool_tab_changed(self.tabs.currentIndex())
        return answer

    def _tool_tab_changed(self,index):
        if self._floating or not self._packed:return
        if self.tabs.widget(index) is not self.pages['session'][0]:
            if self._direct_transport is not None:
                self._direct_transport.timer.stop()
            if self.tabs.widget(index) is self.pages['composition'][0]:
                self._ensure_composer_soundfont()
            return
        self._ensure_composer_soundfont()
        if self.pages['session'][2].indexOf(self._direct_transport)<0:
            self.pages['session'][2].addWidget(self._direct_transport)
        self._direct_transport.show()
        self._direct_transport.timer.start()
        self._direct_transport.refresh()

    def _finish_layout(self):
        side_width=min(475,max(392,round(self.splitter.width()*.355)))
        self.splitter.setSizes([max(460,self.splitter.width()-side_width),
                                side_width])
        self._refresh_project_files()
        self._on_midi_opened(None)

    def _on_midi_opened(self,filename):
        if self._packed:
            # Opening a new MIDI must update the project list, but moving
            # between tabs must not repeatedly rescan thousands of files.
            self._refresh_project_files()
            self.tools._sync_composer_bpm()
            self._sync_internal_track_choice()
            self._enforce_piano_zoom_limits()

    def _tab_changed(self,index):
        if self.main.tabs.widget(index) is self.piano and self._packed:
            self._refresh_project_files()
            self._tool_tab_changed(self.tabs.currentIndex())
            self._enforce_piano_zoom_limits()
        elif self._direct_transport is not None:
            self._direct_transport.timer.stop()
        # Connected before global_midi_transport installs; therefore its
        # own tab handler may show the bar afterwards. Defer our Piano-only
        # hide until that original handler has run.
        QTimer.singleShot(0,self._apply_global_transport_visibility)


def install(main):
    if getattr(main,'piano_roll_pro_tab',None) is not None:
        return main.piano_roll_pro_tab
    main.piano_roll_pro_tab=PianoRollTabPro(main)
    return main.piano_roll_pro_tab
