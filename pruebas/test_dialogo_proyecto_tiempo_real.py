#!/usr/bin/env python3
"""Prueba del mensaje del usuario: carpeta no duplicada, estado REAL actualizado."""
import os,sys,tempfile,time,json,zipfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"]="offscreen"
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
from PySide6.QtWidgets import QApplication,QMessageBox
from main import MonitorWindow
from project_flow import create_named_project
from studio_shell import save_project,save_project_as
from project_status_dialog import project_status,ProjectStatusDialog
from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES

app=QApplication([])
QMessageBox.information=staticmethod(lambda *a,**k:QMessageBox.Ok)
QMessageBox.warning=staticmethod(lambda *a,**k:(_ for _ in ()).throw(
    AssertionError("Unexpected error: "+str(a[1:3]))))
with tempfile.TemporaryDirectory(prefix="stemmidi_dialog_live_") as temp:
    os.environ["STEMMIDI_WORKSPACE"]=temp
    container=Path(temp)/"1"
    container.mkdir()
    win=MonitorWindow()
    assert create_named_project(win,"yo",container,
               next(iter(FORMAT_OPTIONS)),next(iter(SAMPLE_RATES)))
    p=container/"yo"
    path=p/"yo.stemstudio.json"
    assert p.is_dir() and path.is_file()
    assert not (p/"yo").is_dir()
    print("ONE_YO_DIR_AND_ONE_YO_JSON_OK",flush=True)
    snapshot=project_status(p,path)
    assert snapshot["valid"] and snapshot["root"]==str(p)
    assert snapshot["filename"]=="yo.stemstudio.json"
    assert not snapshot["nested_project_dir"]
    assert snapshot["backup_count"]==0
    assert len(snapshot["directories"])==10
    assert all(x["exists"] for x in snapshot["directories"].values())
    print("LIVE_STATUS_READS_FILESYSTEM_NOT_GUESSES",flush=True)
    assert save_project(win)
    dlg=win._live_project_dialog
    assert isinstance(dlg,ProjectStatusDialog)
    assert dlg.timer.isActive()
    assert dlg.isVisible()
    assert dlg.last_snapshot["valid"]
    assert dlg.folder_label.text()==str(p)+"/"
    assert "yo.stemstudio.json" in dlg.file_label.text()
    assert "(archivo, no otra carpeta)" in dlg.file_label.text()
    assert "0." in dlg.backup_label.text()
    assert "no hay una carpeta" in dlg.extra_label.text()
    print("LIVE_SAVE_DIALOG_SEPARATES_ROOT_AND_JSON_FILE",flush=True)
    # La ventana sigue abierta: crear resultado fuera de ella.
    music=p/"stems"/"voz.wav"
    music.write_bytes(b"RIFFtest")
    start=dlg.update_count
    moment=time.monotonic()
    while dlg.update_count==start and time.monotonic()-moment<2.5:
        app.processEvents()
        time.sleep(.025)
    assert dlg.update_count>start,"El temporizador no actualiza el diálogo"
    assert dlg.last_snapshot["directories"]["stems"]["files"]==1
    assert "Stems / Separación: 1 archivo(s)" in dlg.modules_label.text()
    print("LIVE_NEW_STEM_APPEARS_WITHOUT_REOPENING_DIALOG",flush=True)
    with zipfile.ZipFile(p/"backup"/"Antes_de_abrir_20261026_135700_000001.zip","w") as z:
        z.writestr("yo.stemstudio.json",path.read_bytes())
    dlg.refresh()
    assert dlg.last_snapshot["backup_count"]==1
    assert "Copias ZIP anteriores: 1" in dlg.backup_label.text()
    print("LIVE_BACKUP_COUNTER_FROM_DISK",flush=True)
    folder=p/"yo"
    folder.mkdir()
    dlg.refresh()
    assert dlg.last_snapshot["nested_project_dir"] is True
    assert "existe otra carpeta" in dlg.extra_label.text()
    folder.rmdir()
    dlg.refresh()
    assert not dlg.last_snapshot["nested_project_dir"]
    assert "no hay una carpeta" in dlg.extra_label.text()
    print("REAL_NESTED_FOLDER_DETECTED_AND_DISAPPEARS_IN_DIALOG",flush=True)
    dlg.close()
    assert not dlg.timer.isActive()
    print("TIMER_STOPS_ON_CLOSE",flush=True)

actual=Path("/media/javi/Recuperacion/1/yo")
if actual.is_dir():
    state=project_status(actual,actual/"yo.stemstudio.json")
    assert state["valid"] and not state["nested_project_dir"]
    print("ACTUAL_USER_PROJECT_CONFIRMED_NO_DOUBLE_FOLDER",
          state["root"],state["filename"],flush=True)
print("LIVE_PROJECT_DIALOG_COMPLETE_PASS",flush=True)
