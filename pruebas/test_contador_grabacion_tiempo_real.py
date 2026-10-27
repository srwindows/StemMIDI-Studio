#!/usr/bin/env python3
"""Reloj de grabación contra PCM float32 y tiempo REAL del WAV final.
No utiliza micrófonos, monitores ni tarjeta física: prueba aislada.
"""
import os,sys,time,tempfile,subprocess,struct
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.setdefault("STEMMIDI_NO_STARTUP_DIALOG","1")
with tempfile.TemporaryDirectory(prefix="stemmidi_record_clock_") as temp:
    os.environ["STEMMIDI_WORKSPACE"]=temp
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication
    from audio_engine import CaptureWorker,recorded_seconds,CHANNELS,CAPTURE_BYTES_PER_SAMPLE
    from main import MonitorWindow,STYLE
    app=QApplication([])
    app.setStyleSheet(STYLE)
    main=MonitorWindow()
    main.show()
    for _ in range(10):app.processEvents()
    assert CHANNELS==2 and CAPTURE_BYTES_PER_SAMPLE==4
    for rate in (44100,48000,96000,192000):
        worker=CaptureWorker("prueba_sintética_sin_dispositivo",sample_rate=rate)
        worker._rec_bytes=10*rate*CHANNELS*CAPTURE_BYTES_PER_SAMPLE
        main.worker=worker
        main.recording=True
        main.record_started=time.monotonic()
        main.tick()
        assert main.clock.text()=="00:00:10",(rate,main.clock.text())
        assert recorded_seconds(worker._rec_bytes,rate)==10
        # Pausa = no escribir bytes nuevos; el contador se mantiene.
        assert worker.set_record_paused(True) is False  # sin iniciar encoder
        main.tick()
        assert main.clock.text()=="00:00:10"
        worker._rec_bytes=11*rate*CHANNELS*CAPTURE_BYTES_PER_SAMPLE
        main.tick()
        assert main.clock.text()=="00:00:11"
        print("CLOCK_RATE_PAUSE_SAMPLES_PASS",rate,flush=True)
    main.recording=False
    main.tick()
    assert main.clock.text()=="00:00:00"
    main.close()
    # Probar además el mismo encoder usado por CaptureWorker (FFmpeg),
    # no un WAV creado directamente por Python.
    for rate,fmt in ((44100,"WAV (PCM 24 bits · estudio)"),
                     (48000,"WAV (PCM 16 bits)"),
                     (48000,"FLAC (16 bits sin pérdida)"),
                     (96000,"WAV (32 bits float · máster)")):
        worker=CaptureWorker("prueba_sintética_sin_dispositivo",sample_rate=rate)
        path=Path(temp)/(str(rate)+"_"+str(len(fmt))+
            (".flac" if "FLAC" in fmt else ".wav"))
        worker._open_encoder(str(path),fmt)
        # 8 segundos, una pausa simulada de 3 segundos sin escribir,
        # y después 2 segundos. El resultado debe durar exactamente 10.
        block=bytes(1024*CHANNELS*CAPTURE_BYTES_PER_SAMPLE)
        for n in (8*rate,2*rate):
            chunks,left=divmod(n,1024)
            for _ in range(chunks):
                worker._rec.stdin.write(block)
                worker._rec_bytes+=len(block)
            if left:
                data=bytes(left*CHANNELS*CAPTURE_BYTES_PER_SAMPLE)
                worker._rec.stdin.write(data)
                worker._rec_bytes+=len(data)
        assert recorded_seconds(worker._rec_bytes,worker.sample_rate)==10
        worker._close_encoder()
        assert path.is_file() and path.stat().st_size>0,path
        probe=subprocess.run(["ffprobe","-v","error","-show_entries",
            "format=duration","-of","default=noprint_wrappers=1:nokey=1",
            str(path)],capture_output=True,text=True,check=True)
        duration=float(probe.stdout.strip())
        assert abs(duration-10)<.025,(rate,fmt,duration)
        print("RECORDER_FFMPEG_DURATION_PASS",rate,fmt,duration,flush=True)
    print("CAPTURE_RECORD_CLOCK_RATE_PAUSE_AND_FILE_DURATION_ALL_PASS",flush=True)
