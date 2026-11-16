"""Separador secundario de pistas vocales sobre el stem Voces auténtico.

La salida de modelos Karaoke sobre Voces distingue principal y resto
(coros). Los modelos hombre/mujer NO identifican cantantes con el mismo
género ni garantizan separación de tres o más voces simultáneas.
"""
from pathlib import Path
from PySide6.QtCore import QObject,QProcess,Signal
from studio_paths import workspace_root,ia_executable

ROOT=workspace_root(__file__)
MODEL_DIR=ROOT/"modelos"/"voces"
EXEC=ia_executable(__file__)
MODES={
    "lead_backing":("Principal / Coros · MelBand RoFormer",
                    "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"),
    "male_female":("Masculina / femenina · BS RoFormer",
                   "bs_roformer_male_female_by_aufr33_sdr_7.2889.ckpt")
}
# Los modelos que el usuario importe siguen disponibles tras reiniciar.
from external_model_import import voice_modes
MODES.update(voice_modes())

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
        if mode not in MODES:return False
        filename=MODES[mode][1]
        from external_model_import import get as external_get
        external=external_get(filename)
        if external and external.get('role')=='vocal':
            config=external.get('config')
            return bool(config and (MODEL_DIR/filename).is_file() and
                (MODEL_DIR/filename).stat().st_size>1024 and
                (MODEL_DIR/config).is_file() and (MODEL_DIR/config).stat().st_size>50)
        configs={
            "lead_backing":"mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml",
            "male_female":"config_chorus_male_female_bs_roformer.yaml"}
        model=MODEL_DIR/filename
        config=MODEL_DIR/configs[mode]
        return (model.is_file() and model.stat().st_size>5000000
                and config.is_file() and config.stat().st_size>100)

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
        command=EXEC
        if kind=='separate' and '-m' in args:
            from external_model_import import get as external_get
            filename=args[args.index('-m')+1]
            entry=external_get(filename)
            if entry and not entry.get('catalog_known'):
                from studio_paths import ia_python,worker_script
                worker=worker_script(__file__,'external_model_runner.py')
                if not worker.is_file():
                    self.status.emit('No se encuentra el adaptador del modelo vocal externo.')
                    self._process=None
                    return False
                command=ia_python(__file__)
                args=['-B',str(worker),*args]
        proc.start(str(command),args)
        self.busyChanged.emit(True)
        return True

    def download(self,mode):
        if mode not in MODES:return False
        from external_model_import import get as external_get
        if external_get(MODES[mode][1]):
            self.status.emit('Esta IA externa se importa desde un archivo local, no se descarga.')
            return False
        MODEL_DIR.mkdir(parents=True,exist_ok=True)
        return self._launch([
            "--model_file_dir",str(MODEL_DIR),
            "-m",MODES[mode][1],"--download_model_only"],"download")

    def separate(self,home,mode,*,output_format="FLAC",overlap=8,
                 amplification=0.,settings=None):
        if mode not in MODES:return False
        if output_format not in ("FLAC","WAV","MP3"):
            self.status.emit("Formato vocal no válido.");return False
        if not isinstance(overlap,int) or not 2<=overlap<=50:
            self.status.emit("Solapamiento vocal fuera de rango (2 a 50).");return False
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
        from separation_engine_parameters import command_flags,sanitize
        config=dict(settings or {})
        normalization=float(config.pop("normalization",.90))
        sample_rate=int(config.pop("sample_rate",44100))
        if not .1<=normalization<=1 or sample_rate not in (44100,48000):
            self.status.emit("Normalización o frecuencia vocal no válida.")
            return False
        # El nivel de detalle visible (2..50) es prioritario y se comparte
        # entre pestaña y flotante. Los demás ajustes son independientes.
        config=sanitize(config)
        config["mdxc_overlap"]=int(overlap)
        args=[
            "--model_file_dir",str(MODEL_DIR),
            "-m",MODES[mode][1],
            "--output_dir",str(folder),
            "--output_format",output_format,
            "--normalization",str(normalization),
            "--sample_rate",str(sample_rate),
            # audio-separator 0.22 rechaza 0: reproducir desactivación
            # usando 10⁻⁶, sin ganancia artificial apreciable.
            "--amplification",str(max(0.000001,min(1.0,float(amplification)))),
            *command_flags("MDXC",0,config,output_format=output_format),str(source)]
        return self._launch(args,"separate",folder)

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
            self.status.emit("Modelo vocal descargado; verifica los archivos en el panel.")
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
