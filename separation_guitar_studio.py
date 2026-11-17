"""Panel independiente de guitarras: interfaz, descarga verificada, proceso local y resultados."""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, threading
from pathlib import Path
from urllib.request import urlopen, Request
from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer, Signal, QObject
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QCheckBox, QLineEdit, QFileDialog, QMessageBox,
    QProgressBar, QScrollArea, QDoubleSpinBox, QSpinBox, QGroupBox, QSizePolicy)
from studio_workspace_cards import SectionCard
from studio_paths import workspace_root,ia_executable,ia_python,worker_script
from separation_engine_parameters import command_flags
from preview_player import PreviewPlayer

ROOT=workspace_root(__file__)
HOME=ROOT/'modelos'
# Fuentes verificables; los tamaños son de pesos (no de audio ni dependencias).
BASE='https://huggingface.co/noblebarkrr/BS-Roformer-MVSep-Mega-53-stems/resolve/main/v1/'
LEAD='https://huggingface.co/dshdaaf/separation-models/resolve/main/GUITAR/GUITAR-Mel-Roformer_lead_rhythm_by_Dry_Paint_Dealer_Undr/'
MODELS={
 'electric':{'title':'MVSep Mega 53 · Eléctrica','size':77600000,
  'weight':'bs_mega_53stem_electric-guitar_mvsep.ckpt',
  'yaml':'bs_mega_53stem_electric-guitar_mvsep_config.yaml',
  'base':BASE,'stem':'electric-guitar','outputs':['Guitarra eléctrica','Resto']},
 'acoustic':{'title':'MVSep Mega 53 · Acústica','size':77600000,
  'weight':'bs_mega_53stem_acoustic-guitar_mvsep.ckpt',
  'yaml':'bs_mega_53stem_acoustic-guitar_mvsep_config.yaml',
  'base':BASE,'stem':'acoustic-guitar','outputs':['Guitarra acústica','Resto']},
 'lead':{'title':'Mel-Band · Solista / Rítmica','size':337000000,
  'weight':'model_mel_band_roformer_ep_72_sdr_3.2232.ckpt',
  'yaml':'config_mel_band_roformer_Lead_Rhythm_Guitar.yaml',
  'base':LEAD,'stem':'lead','outputs':['Solista','Rítmica']},
}
PRESETS={'Rápido (CPU)':(1,2),'Equilibrado':(2,3),
         'Detalle alto':(4,4),'Máximo detalle':(8,4)}

class Events(QObject):
    progress=Signal(str)
    downloaded=Signal(str,str)
    analyzed=Signal(object)
    preview_ready=Signal(int,str,str)

class GuitarPanel(QWidget):
    def __init__(self,sep,host,parent=None):
        super().__init__(parent)
        self.sep=sep
        self.host=host
        self.process=None
        self.outputs=[]
        self.rows=[]
        self.meter_data={}
        self.playing=False
        self._fullscreen=None
        self.events=Events(self)
        self.events.progress.connect(self.status_message)
        self.events.downloaded.connect(self._download_finished)
        self.events.analyzed.connect(self._analyzed)
        self.events.preview_ready.connect(self._preview_ready)
        self.preview_generation=0
        self.preview_active=[]
        self.preview_mix=None
        outer=QVBoxLayout(self);outer.setContentsMargins(2,2,2,2);outer.setSpacing(5)
        top=QHBoxLayout();top.setSpacing(5)
        self.model=QComboBox()
        for key,info in MODELS.items():self.model.addItem(info['title'],key)
        self.model.currentIndexChanged.connect(self.refresh)
        self.expand=QPushButton('Pantalla completa')
        self.expand.clicked.connect(self.toggle_fullscreen)
        top.addWidget(QLabel('Modelo'));top.addWidget(self.model,1);top.addWidget(self.expand)
        outer.addLayout(top)
        self.state=QLabel()
        outer.addWidget(self.state)
        source=QHBoxLayout();source.setSpacing(4)
        self.path=QLineEdit();self.path.setPlaceholderText('Audio de origen para las guitarras')
        self.path.setText(sep.file_edit.text().strip())
        browse=QPushButton('Archivo…')
        browse.clicked.connect(self.choose_audio)
        source.addWidget(QLabel('Fuente'));source.addWidget(self.path,1);source.addWidget(browse)
        outer.addLayout(source)
        download=QHBoxLayout();download.setSpacing(4)
        self.download_menu=QComboBox()
        self.download_menu.addItem('Descargar modelo grande…',None)
        for key,info in MODELS.items():
            self.download_menu.addItem('%s (%.0f MB)'%(info['title'],info['size']/1e6),key)
        self.install_btn=QPushButton('Instalar')
        self.install_btn.clicked.connect(self.install_selected)
        download.addWidget(self.download_menu,1);download.addWidget(self.install_btn)
        outer.addLayout(download)
        params=QGridLayout();params.setHorizontalSpacing(6);params.setVerticalSpacing(3)
        self.preset=QComboBox();self.preset.addItems(PRESETS)
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.overlap=QSpinBox();self.overlap.setRange(1,8);self.overlap.setValue(2)
        self.overlap.setToolTip('Divisiones superpuestas de cada bloque; aumenta detalle y tiempo de CPU.')
        self.batch=QSpinBox();self.batch.setRange(1,4);self.batch.setValue(3)
        self.batch.setToolTip('Hilos de cálculo en CPU (OMP_NUM_THREADS).')
        for i,(lab,w) in enumerate([('Preset',self.preset),('Solapamiento',self.overlap),
                                     ('Hilos CPU',self.batch)]):
            params.addWidget(QLabel(lab),0,i)
            params.addWidget(w,1,i)
        outer.addLayout(params)
        actions=QHBoxLayout();actions.setSpacing(4)
        self.run=QPushButton('Separar guitarras');self.run.setObjectName('primary')
        self.run.clicked.connect(self.start)
        self.cancel=QPushButton('Cancelar');self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.stop)
        actions.addWidget(self.run,1);actions.addWidget(self.cancel)
        outer.addLayout(actions)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0)
        self.progress.setMaximumHeight(13);outer.addWidget(self.progress)
        result_header=QHBoxLayout()
        result_header.addWidget(QLabel('STEMS GENERADOS'),1)
        all_btn=QPushButton('Marcar todos');all_btn.clicked.connect(self.mark_all)
        result_header.addWidget(all_btn);outer.addLayout(result_header)
        self.results=QWidget()
        self.result_layout=QVBoxLayout(self.results)
        self.result_layout.setContentsMargins(1,2,1,2);self.result_layout.setSpacing(4)
        self.empty=QLabel('Sin resultados de guitarra.');self.result_layout.addWidget(self.empty)
        self.results_scroll=QScrollArea();self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setWidget(self.results);self.results_scroll.setMinimumHeight(90)
        outer.addWidget(self.results_scroll,1)
        self.preview=PreviewPlayer('PREESCUCHA DE GUITARRAS MARCADAS',self)
        self.preview.playStateChanged.connect(self._playing_changed)
        outer.addWidget(self.preview)
        master=QHBoxLayout();master.setSpacing(5)
        self.master_meter=QProgressBar();self.master_meter.setRange(0,100)
        self.master_meter.setValue(0);self.master_meter.setFormat('-∞ dBFS')
        self.master_meter.setMaximumHeight(16)
        self.master_peak=QLabel('Pico: -∞ dBFS')
        master.addWidget(QLabel('VU general'));master.addWidget(self.master_meter,1)
        master.addWidget(self.master_peak)
        outer.addLayout(master)
        bottom=QHBoxLayout();bottom.setSpacing(5)
        self.remove_btn=QPushButton('Eliminar marcados')
        self.remove_btn.setObjectName('stop');self.remove_btn.clicked.connect(self.remove_marked)
        self.save_btn=QPushButton('Guardar → Resultados')
        self.save_btn.setObjectName('primary');self.save_btn.clicked.connect(self.save_marked)
        bottom.addWidget(self.remove_btn);bottom.addWidget(self.save_btn,1)
        outer.addLayout(bottom)
        self.message=QLabel('Motor local · Sin ejecución en nube')
        outer.addWidget(self.message)
        self.meter_timer=QTimer(self);self.meter_timer.timeout.connect(self.update_meters)
        self.meter_timer.start(80)
        self.refresh()

    def status_message(self,message):
        self.message.setText(str(message)[:160])
    def current_key(self):return self.model.currentData()
    def model_files(self,key):
        info=MODELS[key]
        return [HOME/info['weight'],HOME/info['yaml']]
    def installed(self,key):
        a,b=self.model_files(key)
        return a.is_file() and a.stat().st_size>=MODELS[key]['size']*.85 and b.is_file() and b.stat().st_size>100
    def refresh(self,*_):
        key=self.current_key()
        if not key:return
        self.state.setText(('Instalado · ' if self.installed(key) else 'No instalado · ')+
                           'Modelo: '+MODELS[key]['title'])
    def choose_audio(self):
        from audio_import_gui import pick_audio
        path,_=QFileDialog.getOpenFileName(self,'Audio para separación de guitarras',
                                            str(Path.home()),'Audio (*.wav *.flac *.mp3 *.m4a *.ogg *.aiff *.aif);;Todos (*)')
        if path:self.path.setText(path)
    def apply_preset(self,*_):
        overlap,threads=PRESETS[self.preset.currentText()]
        self.overlap.setValue(overlap);self.batch.setValue(threads)
    def install_selected(self):
        key=self.download_menu.currentData()
        if not key:
            QMessageBox.information(self,'Modelo','Selecciona un modelo de descarga.')
            return
        if self.installed(key):
            QMessageBox.information(self,'Modelo','Ya está instalado.')
            return
        info=MODELS[key]
        HOME.mkdir(parents=True,exist_ok=True)
        free=shutil.disk_usage(HOME).free
        # Reserva adicional para descargas parciales y archivos de trabajo.
        required=info['size']*2+1024**3
        if free<required:
            QMessageBox.warning(self,'Espacio insuficiente',
                'Disponibles: %.2f GiB; necesarios: %.2f GiB (incluye reserva). No se instalará.'%
                (free/1024**3,required/1024**3))
            return
        if QMessageBox.question(self,'Instalar IA',
             'Descargar %s (aprox. %.0f MB) en el disco de trabajo?'%
             (info['title'],info['size']/1e6),
             QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.install_btn.setEnabled(False)
        self.events.progress.emit('Descargando '+info['title']+'…')
        def worker():
            files=self.model_files(key);partfiles=[]
            try:
                for dst in files:
                    if dst.is_file() and dst.stat().st_size>100:continue
                    url=info['base']+dst.name+'?download=true'
                    temp=dst.with_suffix(dst.suffix+'.part')
                    partfiles.append(temp)
                    req=Request(url,headers={'User-Agent':'StemMIDI-Studio/1.1'})
                    with urlopen(req,timeout=45) as response, temp.open('wb') as out:
                        while True:
                            block=response.read(1024*1024)
                            if not block:break
                            out.write(block)
                    if temp.stat().st_size < (info['size']*.85 if dst.suffix=='.ckpt' else 100):
                        raise IOError('Descarga incompleta: '+dst.name)
                    os.replace(temp,dst)
                self._register(key)
                self.events.downloaded.emit(key,'')
            except Exception as exc:
                for p in partfiles:p.unlink(missing_ok=True)
                self.events.downloaded.emit(key,str(exc))
        threading.Thread(target=worker,daemon=True).start()
    def _register(self,key):
        from external_model_import import MANIFEST,records
        info=MODELS[key]
        old=records()
        filename=info['weight']
        entry={'filename':filename,'files':[filename,info['yaml']],'family':'MDXC',
               'config':info['yaml'],'role':'general','stems':[info['stem'],'instrumental'],
               'voice_type':None,'display':info['title'],'catalog_known':False}
        old[filename]=entry
        temp=MANIFEST.with_suffix('.tmp')
        temp.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf8')
        os.replace(temp,MANIFEST)
    def _download_finished(self,key,error):
        self.install_btn.setEnabled(True);self.refresh()
        if error:
            QMessageBox.warning(self,'Instalación fallida',error)
            self.status_message('No instalado: '+error)
        else:self.status_message('Instalado: '+MODELS[key]['title'])
    def start(self):
        key=self.current_key();info=MODELS[key]
        path=Path(self.path.text().strip()).expanduser()
        if not path.is_file():
            QMessageBox.warning(self,'Fuente','Selecciona primero un archivo de audio.');return
        if not self.installed(key):
            QMessageBox.warning(self,'Modelo no instalado','Instala primero '+info['title']);return
        from separador import PYTHON,MODELS_DIR
        script=worker_script(__file__,'guitar_model_runner.py')
        runtime=Path(os.environ.get('STEMMIDI_GUITAR_RUNTIME',
             str(Path.home()/'Library/Application Support/StemMIDI Studio/guitar_runtime')))
        arch=('melband-roformer-infer' if key=='lead' else 'bs-roformer-infer')
        if not PYTHON.is_file() or not script.is_file() or not (runtime/arch/'src').is_dir():
            QMessageBox.warning(self,'Motor ausente','Falta el motor específico RoFormer local.');return
        if self.sep.busy:
            QMessageBox.warning(self,'Separador ocupado','Termina la separación general antes de empezar otra.');return
        out=ROOT/'pistas_separadas'/'guitarras'
        out.mkdir(parents=True,exist_ok=True)
        import datetime
        self.output_dir=out/(path.stem[:55]+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        self.output_dir.mkdir()
        command=[str(PYTHON),'-B',str(script),'--key',key,
             '--model_path',str(MODELS_DIR/info['weight']),
             '--config_path',str(MODELS_DIR/info['yaml']),
             '--input',str(path),'--output_dir',str(self.output_dir),
             '--overlap',str(self.overlap.value()),'--batch',str(self.batch.value())]
        self.process=QProcess(self)
        env=QProcessEnvironment.systemEnvironment()
        env.insert('OMP_NUM_THREADS',str(self.batch.value()))
        env.insert('PYTHONUNBUFFERED','1')
        env.insert('STEMMIDI_GUITAR_RUNTIME',str(runtime))
        env.insert('STEMMIDI_FFMPEG',self._ffmpeg())
        self.process.setProcessEnvironment(env)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.run.setEnabled(False);self.cancel.setEnabled(True)
        self.progress.setRange(0,0)
        self.status_message('Separando '+info['title']+'…')
        self.process.start(command[0],command[1:])
    def read_output(self):
        if self.process is None:return
        output=bytes(self.process.readAllStandardOutput()).decode('utf8','replace')
        if output.strip():self.status_message(output.strip().splitlines()[-1])
    def stop(self):
        if self.process is not None and self.process.state()!=QProcess.NotRunning:
            self.process.kill();self.status_message('Proceso cancelado.')
    def finished(self,code,status):
        self.progress.setRange(0,100);self.progress.setValue(100 if code==0 else 0)
        self.run.setEnabled(True);self.cancel.setEnabled(False)
        if code:
            self.status_message('Error del separador (código %s); revisar registro del motor.'%code)
            return
        files=sorted(p for p in self.output_dir.iterdir() if p.suffix.lower() in ('.wav','.flac','.mp3'))
        self.set_outputs(files)
        self.status_message('%d pistas generadas en %s'%(len(files),self.output_dir))
    def set_outputs(self,files):
        self.preview.stop()
        self.preview_generation+=1
        while self.result_layout.count():
            item=self.result_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.rows=[];self.outputs=list(files);self.meter_data={}
        if not files:
            self.result_layout.addWidget(QLabel('Sin resultados de guitarra.'))
        for path in files:
            bar=QWidget(self.results)
            line=QHBoxLayout(bar);line.setContentsMargins(2,1,2,1);line.setSpacing(6)
            check=QCheckBox(path.stem);check.setChecked(True);check.setToolTip(str(path))
            check.toggled.connect(self.prepare_preview)
            meter=QProgressBar();meter.setRange(0,100);meter.setValue(0)
            meter.setFormat('-∞ dBFS');meter.setMaximumHeight(18)
            meter.setMinimumWidth(75)
            line.addWidget(check,3);line.addWidget(meter,2)
            self.result_layout.addWidget(bar)
            self.rows.append((bar,check,meter))
        self.result_layout.addStretch(1)
        self.analyze_meters(files)
        self.prepare_preview()
    def marked(self):
        return [path for path,(_,check,_) in zip(self.outputs,self.rows) if check.isChecked()]
    def mark_all(self):
        value=not all(check.isChecked() for _,check,_ in self.rows)
        for _,check,_ in self.rows:check.setChecked(value)
    def remove_marked(self):
        files=self.marked()
        if not files:return
        if QMessageBox.warning(self,'Confirmar eliminación',
           'Eliminar definitivamente %d archivo(s) generado(s)?'%len(files),
           QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        errors=[]
        for path in files:
            try:path.unlink()
            except OSError as exc:errors.append(str(exc))
        self.set_outputs([p for p in self.outputs if p.is_file()])
        if errors:QMessageBox.warning(self,'No se pudieron borrar todos','\n'.join(errors))
    def save_marked(self):
        files=self.marked()
        if not files:
            QMessageBox.information(self,'Resultados','Selecciona al menos un stem.');return
        workspace=self.host.workbench
        if not workspace.prepare_task('separaciones'):return
        storage=workspace.separation_storage
        try:
            stage=storage.processing_folder
            for path in files:
                shutil.copy2(path,stage/path.name)
            storage.set_separation(stage)
            storage.save_paths(workspace.sep_results.save_directory,
                               [stage/path.name for path in files])
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,'Error guardando resultados',str(exc));return
        workspace.sep_results.populate()
        workspace.open_saved_library('separaciones')
        self.status_message('%d pistas guardadas y enviadas a Resultados.'%len(files))

    def _ffmpeg(self):
        from console_audio_engine import ffmpeg_executable
        executable=ffmpeg_executable()
        if shutil.which(executable) or Path(executable).is_file():return executable
        # Ruta del motor nativo de desarrollo, no se utiliza en un .app instalado.
        candidate=Path(__file__).resolve().parents[2]/'StemMIDI_macOS_1.1.0/native/bin/ffmpeg'
        return str(candidate) if candidate.is_file() else executable

    def _playing_changed(self,playing):
        self.playing=bool(playing)

    def analyze_meters(self,files):
        ffmpeg=self._ffmpeg()
        def worker():
            for path in files:
                if not path.is_file():continue
                try:
                    command=[ffmpeg,'-nostdin','-hide_banner','-loglevel','error',
                      '-i',str(path),'-map','0:a:0','-ac','1','-ar','8000',
                      '-f','f32le','pipe:1']
                    result=subprocess.run(command,stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE,timeout=120,check=True)
                    import numpy as np
                    pcm=np.frombuffer(result.stdout,dtype='<f4')
                    step=800
                    measures=[]
                    for start in range(0,len(pcm),step):
                        amp=float(np.max(np.abs(pcm[start:start+step]),initial=0))
                        measures.append(amp)
                    self.events.analyzed.emit((str(path),measures))
                except (OSError,subprocess.SubprocessError,ValueError) as exc:
                    self.events.progress.emit('Medición PCM no disponible: '+str(exc))
        threading.Thread(target=worker,daemon=True).start()

    def _analyzed(self,data):
        path,values=data
        if Path(path) in self.outputs or (self.preview_mix is not None and str(self.preview_mix)==path):
            self.meter_data[path]=values

    def prepare_preview(self,*_):
        self.preview.stop();self.playing=False
        files=self.marked();self.preview_active=list(files)
        self.preview_generation+=1
        generation=self.preview_generation
        if not files:
            self.preview.clear()
            self.status_message('Marca al menos una pista para preescuchar.')
            return
        if len(files)==1:
            self.preview_mix=files[0]
            self.preview.load(str(files[0]))
            return
        self.status_message('Preparando mezcla temporal de los stems marcados…')
        ffmpeg=self._ffmpeg()
        dest=ROOT/'previsualizaciones_temporales'
        dest.mkdir(parents=True,exist_ok=True)
        output=dest/('guitarras_preescucha_'+str(generation)+'.flac')
        def worker():
            try:
                command=[ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y']
                for f in files:command+=['-i',str(f)]
                inputs=''.join('[%d:a]'%i for i in range(len(files)))
                command+=['-filter_complex',inputs+
                   'amix=inputs=%d:duration=longest:normalize=1[a]'%len(files),
                   '-map','[a]','-c:a','flac',str(output)]
                subprocess.run(command,stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE,timeout=240,check=True)
                self.events.preview_ready.emit(generation,str(output),'')
            except (OSError,subprocess.SubprocessError) as exc:
                self.events.preview_ready.emit(generation,'',str(exc))
        threading.Thread(target=worker,daemon=True).start()

    def _preview_ready(self,generation,path,error):
        if generation!=self.preview_generation:return
        if error:
            self.status_message('No se pudo preparar la preescucha: '+error)
            return
        self.preview_mix=Path(path)
        self.preview.load(path)
        self.analyze_meters([self.preview_mix])
        self.status_message('Preescucha preparada: %d stems marcados.'%len(self.preview_active))

    @staticmethod
    def _meter_display(bar,value):
        import math
        db=20*math.log10(max(1e-9,value))
        bar.setValue(max(0,min(100,round((db+60)*100/60))))
        bar.setFormat('%+.1f dBFS'%db if db>-90 else '-∞ dBFS')
        return db

    def update_meters(self):
        if not self.playing:
            for _,_,bar in self.rows:
                bar.setValue(0);bar.setFormat('-∞ dBFS')
            self.master_meter.setValue(0)
            self.master_meter.setFormat('-∞ dBFS')
            return
        position=max(0,int(self.preview._current_ms)//100)
        for file,(_,check,meter) in zip(self.outputs,self.rows):
            levels=self.meter_data.get(str(file),())
            value=levels[position] if check.isChecked() and position<len(levels) else 0.
            self._meter_display(meter,value)
        mixed=self.meter_data.get(str(self.preview_mix),()) if self.preview_mix else ()
        if mixed and position<len(mixed):
            value=mixed[position]
        else:
            # No mostrar un valor artificial hasta disponer del PCM mezclado.
            value=0.
        peak=self._meter_display(self.master_meter,value)
        self.master_peak.setText('Pico: %+.1f dBFS'%peak if peak>-90 else 'Pico: -∞ dBFS')
    def toggle_fullscreen(self):
        if self._fullscreen is None:
            dialog=QDialog(self.window());dialog.setWindowTitle('Separación de guitarras · StemMIDI Studio')
            dialog.setAttribute(Qt.WA_DeleteOnClose,False)
            layout=QVBoxLayout(dialog);layout.setContentsMargins(8,8,8,8)
            self.layout().setContentsMargins(6,6,6,6)
            self.setParent(dialog);layout.addWidget(self)
            self._fullscreen=dialog
            self.expand.setText('Volver al módulo')
            dialog.finished.connect(self._restore)
            dialog.showMaximized()
        else:self._fullscreen.close()
    def _restore(self,*_):
        if self._fullscreen is None:return
        self.setParent(self.host_card.body.parentWidget())
        self.host_card.body.addWidget(self)
        self._fullscreen.deleteLater();self._fullscreen=None
        self.expand.setText('Pantalla completa')

def install(main):
    sep=main.workbench.separator
    entry,selection,preview,activity=sep._dashboard_main_cards
    # Reutilizar las siete casillas originales y su lógica.
    grid=sep._selection_grid
    holder=grid.parentWidget()
    selection.body.removeWidget(holder)
    holder.setParent(sep._setup_frame)
    setup=sep._setup_frame.layout()
    setup.addWidget(holder,2,3,2,3)
    holder.setMinimumWidth(150)
    sep._setup_frame.setMaximumHeight(16777215)
    entry.setMinimumHeight(228)
    sep.stem_parameters_btn.setParent(sep._setup_frame)
    setup.addWidget(sep.stem_parameters_btn,4,3,1,2)
    sep.stem_note.setParent(sep._setup_frame)
    setup.addWidget(sep.stem_note,5,3,1,3)
    selection.heading.setText('02 · SEPARACIÓN DE GUITARRAS')
    panel=GuitarPanel(sep,main,selection)
    panel.host_card=selection
    selection.body.addWidget(panel,1)
    selection.setMinimumHeight(325)
    sep._guitar_panel=panel
    # Respetar el modo compacto y ampliar únicamente la ventana de trabajo.
    original=sep._final_reflow
    def reflow():
        original()
        selection.setMinimumHeight(325 if sep.width()>755 else 430)
        entry.setMinimumHeight(230)
    sep._final_reflow=reflow
    QTimer.singleShot(0,reflow)
