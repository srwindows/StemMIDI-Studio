#!/usr/bin/env python3
"""Contrato de ruta única para los 8 módulos, sin medios ni proyectos reales."""
from __future__ import annotations
import os,sys,tempfile,wave
from pathlib import Path

os.environ["QT_QPA_PLATFORM"]="offscreen"
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
with tempfile.TemporaryDirectory(prefix="stemmidi_proyectos_integrados_") as temp:
    os.environ["STEMMIDI_WORKSPACE"]=temp
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from PySide6.QtWidgets import QApplication,QMessageBox
    from audio_engine import FORMAT_OPTIONS,SAMPLE_RATES
    from project_flow import create_named_project
    from studio_shell import open_project
    from main import MonitorWindow
    import export_dialog,shutil
    old_export=export_dialog.export_files
    # En esta regresión del proyecto no se prueban diálogos interactivos:
    # se simula la elección explícita de la carpeta fija del módulo. La interfaz real
    # de guardar con nombres se prueba en test_exportaciones_gui.py.
    def export_test(parent,entries,project_dir=None,title="Guardar",kind=None):
        from project_layout import module_dir
        target=module_dir(project_dir,kind or parent.storage.kind)
        target.mkdir(parents=True,exist_ok=True)
        saved=[]
        for item in entries:
            file=target/Path(item).name
            shutil.copy2(item,file)
            saved.append(file)
        return saved
    export_dialog.export_files=export_test

    app=QApplication([])
    # Instalar el gestor global antes de aplicar mocks del test aislado.
    w=MonitorWindow()
    # Cajas modales: consentimiento solo al abandonar temporales del test.
    old_question=QMessageBox.question
    old_info=QMessageBox.information
    old_warning=QMessageBox.warning
    QMessageBox.question=staticmethod(lambda *args,**kwargs: QMessageBox.No)
    QMessageBox.information=staticmethod(lambda *args,**kwargs: QMessageBox.Ok)
    QMessageBox.warning=staticmethod(lambda *args,**kwargs: (_ for _ in ()).throw(
        AssertionError("Aviso imprevisto: "+str(args[:3]))))
    try:
        fmt=next(iter(FORMAT_OPTIONS))
        rate=next(iter(SAMPLE_RATES))
        parent=Path(temp)/"proyectos_del_usuario"
        for name in ("Proyecto_A","Proyecto_B"):
            assert create_named_project(w,name,str(parent),fmt,rate)
            p=parent/name
            assert w.project_dir==p.resolve()
            assert w.project_path==p/f"{name}.stemstudio.json"
            assert w.folder_display.text()==str(p/"grabaciones")
            assert w.folder_display.isReadOnly()
            assert w.workbench.separator.dest_edit.text()==str(p/"stems")
            assert w.workbench.separator.dest_edit.isReadOnly()
            assert w.workbench.converter.outdir.text()==str(p/"audio_a_midi")
            assert w.workbench.converter.outdir.isReadOnly()
            for kind,store in (("separaciones",w.workbench.separation_storage),
                               ("midi",w.workbench.midi_storage),
                               ("bateria",w.workbench.drum_storage),
                               ("vocal",w.workbench.vocal_storage)):
                assert store.project_dir==p.resolve()
                assert store.root==p/"temporales"/kind
                assert store.root.is_dir()
            assert w.workbench.sep_results.save_directory==p/"stems"
            assert w.workbench.midi_results.save_directory==p/"audio_a_midi"
            assert not w.workbench.converter.audio_path.text()
            assert not w.workbench.converter.folder_path.text()
            assert not w.drum_module.input.text()
            assert not w.vocal_module.input.text()
            print("PASS_CONTEXT",name,flush=True)

            if name=="Proyecto_A":
                storage=w.workbench.separation_storage
                folder=storage.start()
                track=folder/"drums.wav"
                with wave.open(str(track),"wb") as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(22050)
                    wav.writeframes(bytes(2205*2))
                storage.set_separation(folder)
                assert (w.workbench.sep_results.save_files(True))
                output=next((p/"stems").glob("*.wav"))
                assert output.is_file()
                w.workbench.saved_audio.refresh()
                assert w.workbench.saved_audio.tree.topLevelItemCount()>0
                w.workbench.show_mixer([track])
                assert w.workbench.mixer.project_dir==p
                # Guardados finales de batería y voz bajo el MISMO proyecto.
                for kind in ("bateria","vocal"):
                    store=getattr(w.workbench,("drum_storage" if kind=="bateria" else "vocal_storage"))
                    run=store.start()
                    audio=run/(kind+"_resultado.wav")
                    with wave.open(str(audio),"wb") as wav:
                        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(22050)
                        wav.writeframes(bytes(2205*2))
                    store.set_separation(run)
                    copies=store.save(__import__("project_layout").module_dir(p,kind),all_files=True)
                    assert copies and all(x.is_file() for x in copies)
                    assert all(x.parent==__import__("project_layout").module_dir(p,kind) for x in copies)
                import mido
                midi=mido.MidiFile(type=1,ticks_per_beat=480)
                tr=mido.MidiTrack()
                tr.append(mido.Message("note_on",note=60,velocity=95,time=0))
                tr.append(mido.Message("note_off",note=60,velocity=0,time=480))
                midi.tracks.append(tr)
                store=w.workbench.midi_storage
                run=store.next_midi_run()
                source=run/"piano.mid";midi.save(source)
                store.set_midi(source)
                saved_mid=w.workbench.midi_results.save_files(True)
                assert saved_mid and all(x.parent==p/"audio_a_midi" for x in saved_mid)
                w.workbench.piano.refresh_midi_list()
                assert w.workbench.piano.midi_choice.count()>0
                w.studio_home.refresh(force=True)
                present={str(x) for x in w.studio_home._gather_files()}
                assert str(output) in present
                assert str(saved_mid[0]) in present
                for kind in ("bateria","vocal"):
                    assert any(str(__import__("project_layout").module_dir(p,kind)) in x for x in present)
                print("PASS_EXPORT_AND_MIX_CONTEXT_A",flush=True)
                print("PASS_BATERIA_VOCAL_MIDI_SAVED_IN_PROJECT",flush=True)
                print("PASS_GLOBAL_RESULTS_PROJECT_ONLY",flush=True)
            else:
                assert w.workbench.mixer is None
                assert w.workbench.saved_audio.tree.topLevelItemCount()==0
                assert w.workbench.saved_midi.tree.topLevelItemCount()==0
                assert w.workbench.piano.midi_choice.count()==0
                assert not w.studio_home._gather_files()
                print("PASS_NO_CROSS_PROJECT_B",flush=True)

        path=parent/"Proyecto_A"/"Proyecto_A.stemstudio.json"
        assert open_project(w,str(path))
        assert w.project_dir==parent/"Proyecto_A"
        assert w.workbench.saved_audio.tree.topLevelItemCount()>0
        assert w.workbench.separator.dest_edit.text()==str(parent/"Proyecto_A"/"stems")
        assert w.workbench.converter.outdir.text()==str(parent/"Proyecto_A"/"audio_a_midi")
        assert w.workbench.separation_storage.root==(parent/"Proyecto_A"/"temporales"/"separaciones")
        print("PASS_REOPEN_AND_RESTORE_A",flush=True)

        # Archivo individual de mezcla: destino pertenece al proyecto, no al audio importado.
        mix=w.workbench.mixer
        if mix is None:
            a=next((parent/"Proyecto_A"/"stems").glob("*.wav"))
            w.workbench.show_mixer([a])
            mix=w.workbench.mixer
        assert mix.project_dir==parent/"Proyecto_A"
        print("PASS_MIXER_SCOPE_A",flush=True)

    finally:
        QMessageBox.question=old_question
        QMessageBox.information=old_info
        QMessageBox.warning=old_warning
        export_dialog.export_files=old_export
        from preview_player import PreviewPlayer
        for player in list(app.allWidgets()):
            if isinstance(player,PreviewPlayer):
                try:player.cleanup()
                except RuntimeError:pass
        try:w.close()
        except RuntimeError:pass
        app.processEvents()
print("ALL_PROJECT_SCOPE_TESTS_OK",flush=True)
