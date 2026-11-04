"""Porcentaje REAL de las operaciones de proyecto.

La barra no tiene temporizadores ni animación indeterminada: el porcentaje
se deriva exclusivamente de bytes copiados y elementos/fases comprobados.
"""
from __future__ import annotations
import time
from PySide6.QtWidgets import QApplication,QProgressDialog,QProgressBar,QPushButton,QLabel
from PySide6.QtCore import Qt,QEventLoop

class OperationCancelled(ValueError):
    """El usuario solicitó cancelar en un punto transaccional seguro."""


class ProjectProgress:
    def __init__(self,parent,title,steps=1,media_sizes=()):
        self.steps_total=max(1,int(steps))
        self.steps_done=0
        self.media_sizes=[max(1,int(x)) for x in media_sizes]
        self.media_total=sum(self.media_sizes)
        self.media_done=0
        self.copy_done=0
        self.copy_current_size=0
        self.media_index=0
        self.percent=0
        # Una fase de metadatos/gestión se contabiliza UNA VEZ al terminar.
        # Con medios grandes predomina su tamaño real, no el reloj.
        self.step_weight=max(1,self.media_total//max(10,self.steps_total*2))
        self.total_weight=self.media_total+self.steps_total*self.step_weight
        self.dialog=QProgressDialog(parent)
        self.dialog.setWindowTitle("StemMIDI Studio · "+title)
        self.dialog.setWindowModality(Qt.ApplicationModal)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.cancel_requested=False
        self.cancel_allowed=False
        self.cancel_button=QPushButton("■ Cancelar operación")
        self.dialog.setCancelButton(self.cancel_button)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setToolTip(
            "Se habilita cuando la operación puede revertirse con seguridad")
        self.dialog.canceled.connect(self._cancel_clicked)
        # QProgressDialog auto-mostraba la ventana antes de recibir el primer
        # repintado. Se controla su aparición en _pump, no por su temporizador.
        self.dialog.setMinimumDuration(2147483647)
        self.dialog.setRange(0,1000)
        self.dialog.setValue(0)
        self.dialog.setMinimumWidth(490)
        self.dialog.setLabelText("Comprobando proyecto… 0 %")
        self.dialog.setObjectName("realProjectProgress")
        self.dialog.setStyleSheet(
            "QProgressDialog{background:#041939;color:#e9faff;"
            "border:1px solid #30baf1;}"
            "QLabel{color:#e9faff;font-size:13px;}"
            "QProgressBar{background:#061b3b;border:1px solid #30baf1;"
            "border-radius:6px;color:white;text-align:center;min-height:22px;}"
            "QProgressBar::chunk{background:#13bce9;border-radius:5px;}"
        )
        self.on_update=None  # Observador de pruebas: progreso numérico REAL.
        self._last_pump=0.0
        # QProgressDialog.setValue() ejecuta processEvents() de forma
        # interna cuando es modal. Cambiar el QProgressBar evita que
        # repita decodificaciones/catálogos durante la apertura.
        self._bar=self.dialog.findChild(QProgressBar)
        self._label=self.dialog.findChild(QLabel)
        if self._bar is not None:
            self._bar.setTextVisible(True)
            self._bar.setFormat("%p %")
            self._bar.setMinimumHeight(24)
        self._started=time.monotonic()
        self._visible=False
        # Guardar únicamente un JSON no debe abrir una ventana modal,
        # recalcular toda la GUI y cerrarla unas milésimas después.
        # Si la operación dura, la barra aparece con su porcentaje real.
        self._show_after=.22

    def _cancel_clicked(self):
        if self.cancel_allowed:self.cancel_requested=True

    def allow_cancel(self,allowed=True):
        self.cancel_allowed=bool(allowed)
        self.cancel_button.setEnabled(self.cancel_allowed)
        self.cancel_button.setToolTip(
            "Detener de forma segura la operación" if self.cancel_allowed else
            "Finalización crítica: no interrumpir una confirmación irreversible")

    def _pump(self,force=False):
        t=time.monotonic()
        if not self._visible and t-self._started>=self._show_after:
            self.dialog.ensurePolished()
            if self.dialog.layout() is not None:
                self.dialog.layout().activate()
            self.dialog.show()
            self._visible=True
            # Un SOLO despacho de eventos para exponer el QWindow y crear
            # la superficie de pintura. Sin él el WM muestra un rectángulo
            # negro y su barra de título. Nunca repetir en cada fase.
            # Dar una oportunidad acotada a la exposición X11/Wayland sin
            # vaciar por completo la cola de timers de todos los módulos.
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents |
                QEventLoop.ExcludeSocketNotifiers, 5)
            self.dialog.repaint()
            if self._label is not None:self._label.repaint()
            if self._bar is not None:self._bar.repaint()
            self.cancel_button.repaint()
        # Evitar procesar eventos Qt de toda la estación en cada etapa
        # de un guardado de metadatos subsegundo. Durante una copia larga
        # siguen disponibles el botón Cancelar y el porcentaje real.
        if self._visible and t-self._last_pump>=0.12:
            if self.cancel_allowed:
                # Necesario únicamente donde se permite Cancelar.
                QApplication.processEvents()
            else:
                # Abrir un proyecto no es cancelable. processEvents aquí
                # disparaba cascadas de ffprobe, scans y repintados durante
                # el propio proceso de restauración (hasta decenas de s).
                # repaint actualiza el porcentaje sin ejecutar otros slots.
                self.dialog.repaint()
                if self._label is not None:self._label.repaint()
                if self._bar is not None:self._bar.repaint()
                self.cancel_button.repaint()
            self._last_pump=t
        if self.cancel_allowed and self.cancel_requested:
            raise OperationCancelled("Operación cancelada por el usuario")

    def _render(self,caption,force=False):
        amount=(self.media_done+min(self.copy_current_size,
                     self.copy_done)*0.88+self.steps_done*self.step_weight)
        value=max(0,min(999,int(1000*amount/max(1,self.total_weight))))
        self.percent=value
        if self._bar is not None:
            self._bar.setValue(value)
        else:
            self.dialog.setValue(value)
        self.dialog.setLabelText(f"{caption}\nAvance comprobado: {value/10:.1f} %")
        if callable(self.on_update):
            self.on_update(value,caption)
        self._pump(force)

    def message(self,caption):
        """Describir trabajo en curso sin adelantar el porcentaje."""
        self._render(caption,True)

    def stage(self,caption):
        self.steps_done=min(self.steps_total,self.steps_done+1)
        self._render(f"{caption} · {self.steps_done}/{self.steps_total} fases",True)

    def begin_media(self,name,size=None):
        if self.media_index>=len(self.media_sizes):
            return
        self.copy_current_size=(max(1,int(size)) if size is not None
                                else self.media_sizes[self.media_index])
        self.copy_done=0
        self._render(f"Procesando {self.media_index+1}/{len(self.media_sizes)}: {name}",True)

    def copied(self,size):
        self.copy_done+=max(0,int(size))
        self._render(f"Copiando {self.media_index+1}/{len(self.media_sizes)}: "
                     f"{self.copy_done:,}/{self.copy_current_size:,} bytes")

    def end_media(self,name):
        if self.media_index>=len(self.media_sizes):
            return
        self.media_done+=self.copy_current_size
        self.media_index+=1
        self.copy_done=0
        self.copy_current_size=0
        self._render(f"Archivo verificado {self.media_index}/{len(self.media_sizes)}: {name}",True)

    def complete(self,caption):
        self.steps_done=self.steps_total
        self.media_done=self.media_total
        self.copy_current_size=0
        self.copy_done=0
        self.percent=1000
        if self._bar is not None:self._bar.setValue(1000)
        else:self.dialog.setValue(1000)
        self.dialog.setLabelText(caption+"\nCompletado: 100 %")
        if callable(self.on_update):
            self.on_update(1000,caption)
        self._pump(True)

    def close(self):
        self.dialog.close()
        self.dialog.deleteLater()
