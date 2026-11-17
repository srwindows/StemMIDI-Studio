"""Estado de motores externos sin progreso inventado.

La barra mide exclusivamente fases realmente terminadas. Si el motor
no publica porcentaje interno, no simula incrementos: se muestra su
estado QProcess real y el tiempo transcurrido independiente de la barra.
"""
from __future__ import annotations

import time
from PySide6.QtCore import Qt,QTimer,QProcess
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QProgressBar,QPushButton

class EngineTaskIndicator:
    def __init__(self,parent,title,phases=1):
        self.total=max(1,int(phases))
        self.done=0
        self.started=time.monotonic()
        self.process=None
        self.phase="Preparando el motor"
        self.engine_percent_mode=False
        self.engine_percent_known=False
        self._closed=False
        self.dialog=QDialog(parent,Qt.Dialog|Qt.CustomizeWindowHint|Qt.WindowTitleHint)
        self.dialog.setWindowTitle("StemMIDI Studio · "+title)
        self.dialog.setWindowModality(Qt.NonModal)
        self.dialog.setMinimumWidth(460)
        self.dialog.setStyleSheet(
            "QDialog{background:#031734;color:#e9faff;border:1px solid #35b9ed;}"
            "QLabel{color:#e5faff;font-size:13px;}"
            "QProgressBar{background:#061e43;border:1px solid #31b6ee;"
            "min-height:21px;border-radius:5px;color:#e9faff;text-align:center;}"
            "QProgressBar::chunk{background:#10bce5;border-radius:4px;}"
        )
        layout=QVBoxLayout(self.dialog)
        self.title=QLabel(title)
        self.details=QLabel()
        self.details.setWordWrap(True)
        self.bar=QProgressBar()
        self.bar.setRange(0,self.total)
        self.bar.setValue(0)
        self.bar.setFormat("%v/%m fases verificadas")
        layout.addWidget(self.title)
        layout.addWidget(self.details)
        layout.addWidget(self.bar)
        self.cancel_button=QPushButton("■ Cancelar operación",self.dialog)
        self.cancel_button.setObjectName("cancelEngineOperation")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.request_cancel)
        layout.addWidget(self.cancel_button)
        self.on_cancel=None
        self.cancel_requested=False
        self.timer=QTimer(self.dialog)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh)
        self.timer.start()
        self.dialog.show()
        self._refresh()

    def attach(self,process,phase):
        self.process=process
        self.phase=str(phase)
        # Reflejar de inmediato Starting/Running/NotRunning, sin esperar al
        # reloj de estado ni alterar el porcentaje de la barra.
        process.stateChanged.connect(lambda state,p=process:
            self._refresh() if (not self._closed and self.process is p) else None)
        self._refresh()

    def _refresh(self):
        if self._closed:return
        seconds=max(0,int(time.monotonic()-self.started))
        try:
            state=self.process.state() if self.process is not None else QProcess.NotRunning
        except RuntimeError:
            # Qt ya ha destruido el QProcess; no consultar su wrapper.
            self.process=None
            state=QProcess.NotRunning
        running=(state==QProcess.Running)
        starting=(state==QProcess.Starting)
        status=("Motor activo" if running else
                "Iniciando motor" if starting else "Comprobando resultado")
        explanation=(
            "Porcentaje comunicado por el motor, no por temporizador."
            if self.engine_percent_known and self.engine_percent_mode
            else "Sin porcentaje del motor; la barra queda fija hasta recibirlo."
            if self.engine_percent_mode
            else "El motor no comunica porcentaje interno; solo se cuentan fases verificadas.")
        self.details.setText(
            f"{self.phase}\n{status} · {seconds//60:02d}:{seconds%60:02d} "
            f"transcurridos.\n{explanation}")

    def set_cancel_callback(self,callback):
        self.on_cancel=callback
        self.cancel_button.setEnabled(callable(callback) and not self.cancel_requested)

    def request_cancel(self):
        if self.cancel_requested or not callable(self.on_cancel):return
        self.cancel_requested=True
        self.cancel_button.setEnabled(False)
        self.phase="Cancelando operación…"
        self._refresh()
        # La salida efectiva se recibe del QProcess; no mostrar 100%.
        self.on_cancel()

    def enable_engine_percent(self):
        """Rango 0–100 fijo: sin avance simulado mientras no haya telemetría."""
        if self.engine_percent_mode:return
        self.engine_percent_mode=True
        self.bar.setRange(0,100)
        self.bar.setValue(0)
        self.bar.setFormat("IA: porcentaje comunicado por el motor")
        self._refresh()

    def report_engine_percent(self,percent):
        if not self.engine_percent_mode:return
        self.engine_percent_known=True
        self.bar.setValue(max(self.bar.value(),min(99,max(0,int(percent)))))
        self.bar.setFormat("Cálculo IA medido: %p% · pendiente verificar salidas")
        self._refresh()

    def stage(self,caption):
        self.done=min(self.total,self.done+1)
        if not self.engine_percent_mode:
            self.bar.setValue(self.done)
        self.phase=str(caption)
        self._refresh()

    def finish(self,successful,caption=None):
        if successful:
            self.done=self.total
            self.bar.setValue(100 if self.engine_percent_mode else self.total)
        if caption:self.phase=str(caption)
        self._refresh()
        self.timer.stop()
        self.cancel_button.setEnabled(False)
        self._closed=True
        self.process=None
        self.dialog.close()
        self.dialog.deleteLater()
