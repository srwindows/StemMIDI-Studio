import os,sys,struct,math,wave,tempfile,time
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="sep_pro_real_") as temp:
    os.environ["STEMMIDI_WORKSPACE"]=temp
    sys.path.insert(0,"/media/javi/Recuperacion/Monitor_de_Grabacion")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from main import MonitorWindow,STYLE
    source=Path(temp)/"audio_original.wav"
    with wave.open(str(source),"wb") as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100)
        samples=[]
        for t in range(44100):
            left=int(10000*math.sin(2*math.pi*440*t/44100))
            right=int(8000*math.sin(2*math.pi*660*t/44100))
            samples.append(struct.pack("<hh",left,right))
        f.writeframes(b"".join(samples))
    app=QApplication([]);app.setStyleSheet(STYLE)
    main=MonitorWindow();main.show()
    sep=main.workbench.separator
    sep.profile.setCurrentText("2 canales originales — Izquierdo / Derecho (sin IA)")
    sep.stem_all.setChecked(False)
    sep.stem_checks["Izquierdo"].setChecked(True)
    assert sep.requested_stems()==["Izquierdo"],sep.requested_stems()
    sep.file_edit.setText(str(source))
    assert sep.norm_setting>=0
    sec=main.workbench.sep_results
    sep.start_separation()
    assert sep.busy,"Process never launched"
    assert sep.motor_dialog.isVisible(),"Process dialog absent"
    print("STARTED",sep.active_request,flush=True)
    started=time.monotonic()
    def verify():
        if sep.busy and time.monotonic()-started<28:return
        if sep.busy:
            print("E2E_TIMEOUT",sep.log.toPlainText()[-1500:],flush=True);sep.stop();app.exit(2);return
        outputs=[Path(x).name for x in sec.storage.items]
        print("FINISHED",outputs,"status",sep.progress_label.text(),flush=True)
        assert len(outputs)==1,outputs
        assert "Izquierdo" in outputs[0],outputs
        assert sep.motor_dialog.total.value()==100,sep.motor_dialog.total.value()
        assert sec.lines and sec.lines[0].checked.isChecked()
        assert sec.pitch_btn is not None
        sec.mark_none_btn.click()
        assert not sec.selected_indices()
        sec.mark_all_btn.click()
        assert sec.selected_indices()==[0]
        from project_flow import approve_separation
        approved=approve_separation(main,quiet=True)
        print("APPROVE_STEREO",approved,flush=True)
        print("E2E_SEPARATION_SUCCESS",flush=True)
        app.quit()
    timer=QTimer();timer.timeout.connect(verify);timer.start(300)
    QTimer.singleShot(31000,lambda:app.exit(3))
    result=app.exec()
    sys.exit(result)
