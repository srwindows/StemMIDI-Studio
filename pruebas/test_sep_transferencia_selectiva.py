import os,sys,struct,wave,tempfile,math
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['STEMMIDI_NO_STARTUP_DIALOG']='1'
with tempfile.TemporaryDirectory(prefix='sep_transfer_') as tmp:
 os.environ['STEMMIDI_WORKSPACE']=tmp
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
 from PySide6.QtWidgets import QApplication
 from main import MonitorWindow,STYLE
 app=QApplication([]);app.setStyleSheet(STYLE)
 main=MonitorWindow();main.show()
 work=main.workbench
 store=work.separation_storage
 store.start()
 base=store.processing_folder
 for name in ('Vocals','Drums','Bass'):
  with wave.open(str(base/(name+'.wav')),'wb') as f:
   f.setnchannels(1);f.setsampwidth(2);f.setframerate(44100)
   f.writeframes(struct.pack('<h',0)*5000)
 store.set_separation(base)
 work.sep_results.populate()
 assert len(work.sep_results.lines)==3
 selected=[]
 for row in work.sep_results.lines:
  mark=row.path.name in ('Vocals.wav','Bass.wav')
  row.checked.setChecked(mark)
  if mark:selected.append(row.path)
 work.use_selected_stems_as_midi_source(selected)
 transferred=Path(work.converter.folder_path.text())
 names={p.name for p in transferred.iterdir() if p.is_file()}
 assert names=={'Vocals.wav','Bass.wav'},names
 assert (base/'Drums.wav').exists()
 print('MIDI_TRANSFER_ONLY_CHECKED',sorted(names),flush=True)
 print('SELECTIVE_TRANSFER_PASS',flush=True)
