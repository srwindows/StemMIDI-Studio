import os,sys,struct,math,wave,tempfile,shutil,time,subprocess
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="sep_pitch_real_") as temp:
    os.environ["STEMMIDI_WORKSPACE"]=temp
    sys.path.insert(0,"/media/javi/Recuperacion/Monitor_de_Grabacion")
    from PySide6.QtWidgets import QApplication,QDialog,QMessageBox
    from PySide6.QtCore import QTimer
    from main import MonitorWindow,STYLE
    from separation_pro_controls import pitch_dialog,remove_selected
    from task_staging import inside
    source=Path(temp)/"Original_INTOCABLE.wav"
    with wave.open(str(source),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000)
        samples=[struct.pack("<h",int(9000*math.sin(2*math.pi*440*i/48000))) for i in range(48000)]
        f.writeframes(b"".join(samples))
    app=QApplication([]);app.setStyleSheet(STYLE)
    main=MonitorWindow();main.show()
    panel=main.workbench.sep_results
    sep=main.workbench.separator
    store=main.workbench.separation_storage
    store.start()
    folder=store.processing_folder
    target=folder/"guitar.wav"
    shutil.copy2(source,target)
    store.set_separation(folder);panel.populate()
    sep.current_folder=folder;sep.refresh_outputs()
    assert len(store.items)==1
    original_bytes=source.read_bytes()
    before=target.stat().st_size
    QDialog.exec=lambda self: QDialog.Accepted
    pitch_dialog(main)
    assert panel._pitch_operation._pitch_process is not None
    start=time.monotonic()
    def verify():
        if len(store.items)<2 and time.monotonic()-start<15:return
        assert len(store.items)==2,[str(x) for x in store.items]
        edited=store.items[-1]
        assert edited.exists() and "tono_+2st" in edited.name,edited
        assert source.read_bytes()==original_bytes
        assert target.stat().st_size==before
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-i',str(edited),
             '-ac','1','-ar','48000','-f','f32le','-']
        audio=subprocess.check_output(cmd)
        import numpy as np
        y=np.frombuffer(audio,dtype="<f4")
        n=min(len(y),48000)
        frequencies=np.fft.rfftfreq(n,1/48000)
        hz=float(frequencies[np.argmax(abs(np.fft.rfft(y[:n])) )])
        print('PITCH_FREQUENCY',hz,'EXPECTED',440*(2**(2/12)),flush=True)
        assert abs(hz-493.883)<5,(hz,493.883)
        selected=[row.path for row in panel.lines if row.checked.isChecked()]
        assert selected==[edited],selected
        QMessageBox.question=staticmethod(lambda *a,**kw: QMessageBox.Yes)
        remove_selected(main)
        assert len(store.items)==1
        assert not edited.exists()
        assert target.exists()
        assert source.read_bytes()==original_bytes
        print('PITCH_AND_DELETE_SELECTED_PASS',flush=True)
        timer.stop();app.quit()
    timer=QTimer();timer.timeout.connect(verify);timer.start(400)
    QTimer.singleShot(20000,lambda:app.exit(5))
    sys.exit(app.exec())
