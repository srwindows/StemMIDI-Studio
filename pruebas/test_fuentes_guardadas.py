#!/usr/bin/env python3
"""Módulos: importar trabajos guardados del mismo proyecto, nunca del anterior."""
from pathlib import Path
import os,sys,tempfile,wave
os.environ["QT_QPA_PLATFORM"]="offscreen"
with tempfile.TemporaryDirectory(prefix="stemmidi_saved_sources_test_") as t:
    os.environ["STEMMIDI_WORKSPACE"]=t
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication,QMessageBox
    from main import MonitorWindow
    from project_flow import create_named_project
    from studio_shell import open_project
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    from task_staging import project_audio_sources
    app=QApplication([])
    QMessageBox.information=staticmethod(lambda *args,**kwargs:QMessageBox.Ok)
    QMessageBox.question=staticmethod(lambda *args,**kwargs:QMessageBox.No)
    # No permitir popups modales invisibles en modo offscreen.
    QMessageBox.warning=staticmethod(lambda *args,**kwargs:(_ for _ in ()).throw(
        AssertionError("Aviso inesperado: "+str(args[1:3]))))
    w=MonitorWindow()
    root=Path(t)/"Elegidos"
    fmt=next(iter(FORMAT_OPTIONS));sr=next(iter(SAMPLE_RATES))
    assert create_named_project(w,"A",str(root),fmt,sr)
    a=Path(w.project_dir)
    files={}
    for group,filename in (
        ("separaciones","vocals.wav"),
        ("separaciones","drums.wav"),
        ("bateria","bateria_nueva.wav"),
        ("vocal","voz_afinada.flac"),
    ):
        from project_layout import module_dir
        p=module_dir(a,group)/filename
        p.parent.mkdir(parents=True,exist_ok=True)
        if p.suffix==".flac":
            # Generar FLAC realmente decodificable, sin audio ficticio.
            import subprocess
            template=Path(t)/"voz_test.wav"
            with wave.open(str(template),"wb") as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(22050)
                f.writeframes(bytes(22050*2))
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error",
                "-y","-i",str(template),"-c:a","flac",str(p)],check=True)
        else:
            with wave.open(str(p),"wb") as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(22050)
                f.writeframes(bytes(22050*2))
        files[filename]=p.resolve()
    external=Path(t)/"drums_externo.wav"
    external.write_bytes(b"NO ES DEL PROYECTO")
    (a/"stems"/"drums_link.wav").symlink_to(external)
    assert external not in project_audio_sources(a)
    # El backup debe rechazar enlaces que apunten fuera del proyecto.
    # Tras esa comprobación, retirar SOLO el enlace sintético del test;
    # no se modifica el archivo externo original.
    from project_session import snapshot_on_open
    try:
        snapshot_on_open(a)
    except ValueError as e:
        assert "Enlace simbólico" in str(e)
    else:
        raise AssertionError("Backup siguió enlace externo")
    (a/"stems"/"drums_link.wav").unlink()
    assert external.is_file()
    w.vocal_module.refresh_sources()
    w.drum_module.refresh_sources()
    w.workbench.converter.refresh_project_stems()
    assert all(w.vocal_module.source_choice.findData(str(files[name]))>0
        for name in ("vocals.wav","voz_afinada.flac"))
    assert all(w.drum_module.project_source.findData(str(files[name]))>0
        for name in ("drums.wav","bateria_nueva.wav"))
    assert set(files.values()).issubset(set(w.workbench.converter.project_stem_paths()))
    print("PROYECTO_A_STEMS_GUARDADOS_APARECEN_3_MODULOS",flush=True)
    assert create_named_project(w,"B",str(root),fmt,sr)
    w.vocal_module.refresh_sources()
    w.drum_module.refresh_sources()
    w.workbench.converter.refresh_project_stems()
    assert not any(w.vocal_module.source_choice.findData(str(p))>=0 for p in files.values())
    assert not any(w.drum_module.project_source.findData(str(p))>=0 for p in files.values())
    assert not (set(files.values()) & set(w.workbench.converter.project_stem_paths()))
    print("PROYECTO_B_NO_VE_ARCHIVOS_DE_A",flush=True)
    assert open_project(w,str(a/"A.stemstudio.json"))
    w.vocal_module.refresh_sources()
    w.drum_module.refresh_sources()
    w.workbench.converter.refresh_project_stems()
    assert w.vocal_module.source_choice.findData(str(files["vocals.wav"]))>0
    assert w.drum_module.project_source.findData(str(files["drums.wav"]))>0
    assert files["vocals.wav"] in w.workbench.converter.project_stem_paths()
    print("REABRIR_A_RECUPERA_FUENTES_GUARDADAS",flush=True)
print("SAVED_AUDIO_SOURCES_SCOPE_TEST_OK",flush=True)
