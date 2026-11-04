"""Separador secundario de pistas vocales sobre el stem Voces auténtico.

La salida de modelos Karaoke sobre Voces distingue principal y resto
(coros). Los modelos hombre/mujer NO identifican cantantes con el mismo
género ni garantizan separación de tres o más voces simultáneas.
"""
from pathlib import Path
from PySide6.QtCore import QObject,QProcess,Signal
from studio_paths import workspace_root

ROOT=workspace_root(__file__)
MODEL_DIR=ROOT/"modelos"/"voces"
EXEC=ROOT/"entorno_ia"/"bin"/"audio-separator"
MODES={
    "lead_backing":("Principal / Coros · MelBand RoFormer",
                    "mel_band_roformer_karaoke_gabox.ckpt"),
    "male_female":("Voz masculina / femenina",
                   "bs_roformer_male_female_by_aufr33_sdr_7.2889.ckpt")
}

class VocalSplitJob(QObject):
    status=Signal(str)
    busyChanged=Signal(bool)
    ready=Signal(list)
    def __init__(self,parent=None):
        super().__init__(parent)
        self._process=None
        self._kind=""
        self._folder=None
        self.results=[]

    @property
    def busy(self):
        return self._process is not None and self._process.state()!=QProcess.NotRunning

    @staticmethod
    def installed(mode):
        filename=MODES[mode][1]
        model=MODEL_DIR/filename
        return model.is_file() and model.stat().st_size>5000000

    @staticmethod
    def source_file(home):
        return home._sep_listen.available().get("Voces")

    def _launch(self,args,kind,folder=None):
        if self.busy:return False
        if not EXEC.is_file():
            self.status.emit("No está instalado audio-separator.")
            return False
        proc=QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        self._process=proc
        self._kind=kind
        self._folder=folder
        self._log=""
        proc.readyReadStandardOutput.connect(
            lambda:self._read_output(proc))
        proc.finished.connect(
            lambda rc,state:self._finished(proc,rc,state))
        proc.errorOccurred.connect(
            lambda error:self.status.emit("Error de ejecución: "+proc.errorString())
            if proc is self._process else None)
        self.status.emit(
            "Instalando modelo vocal real…" if kind=="download"
            else "Separando audio vocal mediante IA…")
        proc.start(str(EXEC),args)
        self.busyChanged.emit(True)
        return True

    def download(self,mode):
        if mode not in MODES:return False
        MODEL_DIR.mkdir(parents=True,exist_ok=True)
        return self._launch([
            "--model_file_dir",str(MODEL_DIR),
            "-m",MODES[mode][1],"--download_model_only"],"download")

    def separate(self,home,mode,*,output_format="FLAC",overlap=8,amplification=0.):
        if mode not in MODES:return False
        if output_format not in ("FLAC","WAV","MP3"):
            self.status.emit("Formato vocal no válido.");return False
        if overlap not in (8,16):
            self.status.emit("Detalle de IA no válido.");return False
        if not 0.<=float(amplification)<=.30:
            self.status.emit("Refuerzo fuera de rango.");return False
        source=self.source_file(home)
        if source is None or not Path(source).is_file():
            self.status.emit("Primero separa la pista Voces del proyecto.")
            return False
        if not self.installed(mode):
            self.status.emit("Instala primero el modelo de IA vocal.")
            return False
        project=getattr(home.main,"project_dir",None)
        if not project:
            self.status.emit("Abre un proyecto para guardar las voces.")
            return False
        from task_staging import inside
        source=Path(source).resolve()
        project=Path(project).resolve()
        if not inside(source,project):
            self.status.emit("La voz seleccionada no pertenece al proyecto actual.")
            return False
        folder=project/"temporales"/"voces"/mode
        folder.mkdir(parents=True,exist_ok=True)
        # Nunca sobrescribir un resultado anterior sin pedirlo.
        existing={x.name for x in folder.iterdir() if x.is_file()}
        if existing:
            i=2
            while (project/"temporales"/"voces"/f"{mode}_{i}").exists():
                i+=1
            folder=project/"temporales"/"voces"/f"{mode}_{i}"
            folder.mkdir()
        return self._launch([
            "--model_file_dir",str(MODEL_DIR),
            "-m",MODES[mode][1],
            "--output_dir",str(folder),
            "--output_format",output_format,
            "--amplification",f"{float(amplification):.2f}",
            "--mdxc_overlap",str(overlap),
            str(source)],"separate",folder)

    def _read_output(self,proc):
        if proc is not self._process:return
        text=bytes(proc.readAllStandardOutput()).decode("utf-8","replace")
        self._log=(self._log+text)[-15000:]
        lines=[x.strip() for x in text.replace("\r","\n").splitlines() if x.strip()]
        if lines:
            from re import sub
            msg=sub(r"\x1b\[[0-9;]*m","",lines[-1])
            self.status.emit(msg[:150])

    def _finished(self,proc,code,state):
        if proc is not self._process:return
        self._read_output(proc)
        self._process=None
        self.busyChanged.emit(False)
        if code!=0 or state!=QProcess.NormalExit:
            self.status.emit("No se pudo completar la separación vocal. "+
                             self._log[-220:].strip())
        elif self._kind=="download":
            self.status.emit("Modelo vocal instalado. Ya puedes procesar la pista.")
        elif self._folder:
            outputs=sorted(x.resolve() for x in self._folder.iterdir()
                           if x.suffix.lower() in {".flac",".wav",".mp3"}
                           and x.is_file() and x.stat().st_size>1024)
            if len(outputs)>=2:
                self.results=outputs
                self.ready.emit([str(x) for x in outputs])
                self.status.emit(f"{len(outputs)} pistas vocales generadas.")
            else:
                self.status.emit("El proceso no generó dos pistas vocales válidas.")
        proc.deleteLater()

    def stop(self):
        if self._process is not None:
            self._process.terminate()
            if not self._process.waitForFinished(750):
                self._process.kill()
                self._process.waitForFinished(250)
