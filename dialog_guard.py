"""Único gestor de ventanas modales de StemMIDI Studio.

Normaliza mensajes, preguntas, diálogos de selección y QDialog.exec/show
sin cambiar los valores devueltos al código llamante. Cuando una tarjeta
está flotando (Qt.Tool + WindowStaysOnTop), el diálogo se hace transitorio
de ESE flotante y hereda la prioridad de apilamiento. Esto evita el
bloqueo modal invisible observado en KDE.
"""
from __future__ import annotations

import weakref
from PySide6.QtCore import Qt, QEvent, QObject, QTimer
from PySide6.QtWidgets import (
    QApplication,QDialog,QMessageBox,QInputDialog,QFileDialog,QLineEdit,QWidget
)

_MANAGER = None
_INSTALLED = False
_ORIGINALS = {}
_METRICS = {"messages":0,"input":0,"files":0,"dialogs":0,"raised":0}

def manager():
    return _MANAGER() if _MANAGER is not None else None

def _owner(parent=None):
    m=manager()
    if m is None or not m.windows:
        return None
    windows=tuple(w for w in m.windows.values() if w is not None and w.isVisible())
    if not windows:return None
    # Primera prioridad: padres contenidos en la tarjeta flotante.
    cur=parent if isinstance(parent,QWidget) else None
    while cur is not None:
        for win in windows:
            if cur is win:return win
        cur=cur.parentWidget()
    # Segunda: ventana activa dentro del diálogo/modal asociado o flotante.
    app=QApplication.instance()
    active=app.activeWindow() if app is not None else None
    cur=active
    while cur is not None:
        for win in windows:
            if cur is win:return win
        cur=cur.parentWidget()
    # Tercera: última tarjeta activada; o última flotante.
    last=getattr(m,"_last_active_card",None)
    if last in m.windows and m.windows[last] in windows:
        return m.windows[last]
    return windows[-1]

def _prepare(dialog,owner=None,modal=False):
    if owner is None:owner=_owner(dialog.parentWidget())
    if owner is None or dialog is owner:return False
    if dialog.property("_stem_modal_restacking"):return True
    dialog.setProperty("_stem_modal_restacking",True)
    try:
        # Cambiar padre únicamente ANTES de mostrar, nunca mientras la
        # ventana modal espera un resultado; eso provocaba huecos muertos.
        if dialog.parentWidget() is not owner and not dialog.isVisible():
            dialog.setParent(owner)
        # Qt convierte ciertos diálogos con padre en Sheet al mostrar; hay
        # que fijar el tipo Dialog y StayOnTop juntos TRAS asignar el padre.
        if modal:dialog.setWindowModality(Qt.WindowModal)
        flags=((dialog.windowFlags() & ~Qt.WindowType_Mask)
               | Qt.Dialog | Qt.WindowStaysOnTopHint)
        if dialog.windowFlags()!=flags:
            dialog.setWindowFlags(flags)
        dialog.setAttribute(Qt.WA_DeleteOnClose,False)
        _METRICS["raised"]+=1
        return True
    finally:
        dialog.setProperty("_stem_modal_restacking",False)

def _raise_dialog(dlg):
    if not dlg.isVisible():return
    dlg.raise_()
    dlg.activateWindow()

def _exec(dialog,*args,**kwargs):
    _METRICS["dialogs"]+=1
    if _prepare(dialog,modal=True):
        QTimer.singleShot(0,lambda d=dialog:_raise_dialog(d))
    return _ORIGINALS["dialog_exec"](dialog,*args,**kwargs)

def _show(dialog,*args,**kwargs):
    # QDialog.show usado en gestores de modelos, ayuda y cuadros no modales.
    if _prepare(dialog,modal=False):
        QTimer.singleShot(0,lambda d=dialog:_raise_dialog(d))
    return _ORIGINALS["dialog_show"](dialog,*args,**kwargs)

def _message(icon,default_buttons,parent,title,text,buttons=None,default_button=None):
    _METRICS["messages"]+=1
    owner=_owner(parent)
    parent=owner if owner is not None else parent
    box=QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(str(title))
    box.setText(str(text))
    box.setStandardButtons(default_buttons if buttons is None else buttons)
    if default_button is not None and default_button!=QMessageBox.NoButton:
        box.setDefaultButton(default_button)
    result=box.exec()
    return result

def _install_messages():
    entries={
        "information":(QMessageBox.Information,QMessageBox.Ok),
        "warning":(QMessageBox.Warning,QMessageBox.Ok),
        "critical":(QMessageBox.Critical,QMessageBox.Ok),
        "question":(QMessageBox.Question,QMessageBox.Yes|QMessageBox.No),
        "about":(QMessageBox.Information,QMessageBox.Ok),
    }
    for name,(icon,default) in entries.items():
        _ORIGINALS["msg_"+name]=getattr(QMessageBox,name)
        def wrap(parent,title,text,*args,_icon=icon,_default=default,**kwargs):
            buttons=args[0] if args else kwargs.get("buttons",_default)
            default_button=(args[1] if len(args)>1
                            else kwargs.get("defaultButton",None))
            return _message(_icon,_default,parent,title,text,buttons,default_button)
        setattr(QMessageBox,name,staticmethod(wrap))

def _get_text(parent,title,label,*args,**kwargs):
    _METRICS["input"]+=1
    owner=_owner(parent)
    dlg=QInputDialog(owner if owner is not None else parent)
    dlg.setWindowTitle(str(title))
    dlg.setLabelText(str(label))
    echo=(args[0] if len(args)>0 else kwargs.get("echo",QLineEdit.Normal))
    initial=(args[1] if len(args)>1 else kwargs.get("text",""))
    dlg.setTextEchoMode(echo)
    dlg.setTextValue(str(initial))
    if "inputMethodHints" in kwargs:dlg.setInputMethodHints(kwargs["inputMethodHints"])
    accepted=dlg.exec()==QDialog.Accepted
    return dlg.textValue(),accepted

def _static_file(kind):
    def impl(parent=None,caption="",directory="",filter="",*args,**kwargs):
        _METRICS["files"]+=1
        from file_dialogs import _studio_picker,_start,LAST_FOLDER
        import file_dialogs
        owner=_owner(parent)
        selected,selected_filter=_studio_picker(
            owner if owner is not None else parent,caption,_start(directory),filter,kind)
        if selected:
            from pathlib import Path
            file_dialogs.LAST_FOLDER=(selected[0] if kind=="dir"
                         else str(Path(selected[0]).parent))
        if kind=="multi":return selected,selected_filter
        if kind=="dir":return selected[0] if selected else ""
        return (selected[0] if selected else ""),selected_filter
    return impl

class _FocusObserver(QObject):
    def eventFilter(self,obj,event):
        if event.type()==QEvent.WindowActivate:
            m=manager()
            if m is not None:
                for card,window in tuple(m.windows.items()):
                    if obj is window:
                        m._last_active_card=card
                        break
        return False

def install(app,main=None):
    global _INSTALLED,_MANAGER
    if main is not None:
        m=getattr(getattr(main,"studio_home",None),"_floating_manager",None)
        if m is not None:_MANAGER=weakref.ref(m)
    if _INSTALLED:return
    _INSTALLED=True
    _ORIGINALS["dialog_exec"]=QDialog.exec
    _ORIGINALS["dialog_show"]=QDialog.show
    QDialog.exec=_exec
    QDialog.show=_show
    _install_messages()
    _ORIGINALS["getText"]=QInputDialog.getText
    QInputDialog.getText=staticmethod(_get_text)
    for method,kind in (("getOpenFileName","open"),("getOpenFileNames","multi"),
                        ("getSaveFileName","save"),("getExistingDirectory","dir")):
        _ORIGINALS[method]=getattr(QFileDialog,method)
        setattr(QFileDialog,method,staticmethod(_static_file(kind)))
    observer=_FocusObserver(app)
    app.installEventFilter(observer)
    app._stem_dialog_focus_observer=observer

def bind_manager(module_manager):
    global _MANAGER
    _MANAGER=weakref.ref(module_manager)

def bind_main(main):
    app=QApplication.instance()
    if app is not None:install(app,main)

def metrics():
    return dict(_METRICS)
