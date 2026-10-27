import os,sys,wave,struct,math,time,tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['STEMMIDI_NO_STARTUP_DIALOG']='1'
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from preview_player import PreviewPlayer
app=QApplication([])
with tempfile.TemporaryDirectory(prefix="test_real_vu_") as dir:
 p=os.path.join(dir,'stereo.wav')
 with wave.open(p,'wb') as w:
  w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000)
  w.writeframes(b''.join(struct.pack('<hh',int(13000*math.sin(2*math.pi*440*n/48000)),int(4000*math.sin(2*math.pi*600*n/48000))) for n in range(48000)))
 player=PreviewPlayer("VU QA")
 player.load(p)
 deadline=time.time()+7
 while len(player._measured_vu.levels)<7 and time.time()<deadline:
  app.processEvents();time.sleep(.08)
 print('MEASURED',len(player._measured_vu.levels),player._measured_vu.levels[:2],flush=True)
 assert len(player._measured_vu.levels)>=7
 l,r,lp,rp=player._measured_vu.levels[4]
 assert l>r>0.01,(l,r)
 assert lp>rp>0.01,(lp,rp)
 player.clear()
 assert not player._measured_vu.levels
 player.cleanup()
 print('STEREO_FILE_RMS_VU_PASS',flush=True)
