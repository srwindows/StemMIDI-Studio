#!/usr/bin/env python3
"""Exportación: ruta/nombre, varios archivos, ZIP, confirmación y cancelar."""
import tempfile,os,sys,hashlib,zipfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="stemmidi_export_test_") as d:
    os.environ['STEMMIDI_WORKSPACE']=d
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import export_dialog as mod
    from PySide6.QtWidgets import QApplication,QWidget
    app=QApplication([])
    root=Path(d)
    project=root/"proyecto"
    temporary=project/"temporales"
    temporary.mkdir(parents=True)
    (project/"backup").mkdir()
    source1=temporary/"Voz.wav";source2=temporary/"Bateria.wav"
    source1.write_bytes(b"\x00\x01VOICE"*256)
    source2.write_bytes(b"\x03\x01DRUMS"*256)
    before={p:hashlib.sha256(p.read_bytes()).digest() for p in (source1,source2)}
    modes=[]
    selected=[]
    class DialogMock:
        AcceptRole=1
        ActionRole=2
        RejectRole=3
        Ok=4
        def __init__(self,parent=None):
            self.buttons=[]
            self.current=None
        def setWindowTitle(self,*args):pass
        def setText(self,*args):pass
        def setInformativeText(self,*args):pass
        def addButton(self,label,role):
            button=object()
            self.buttons.append((label,button))
            return button
        def exec(self):
            wanted=modes.pop(0)
            self.current=next(b for name,b in self.buttons if name.startswith(wanted))
        def clickedButton(self):return self.current
        @staticmethod
        def information(*args):return DialogMock.Ok
        @staticmethod
        def warning(*args):raise AssertionError("WARNING: "+str(args[1:3]))
    mod.QMessageBox=DialogMock
    mod.file_dialogs.get_save_file_name=lambda *a,**k:(str(selected.pop(0)),"")
    mod.file_dialogs.get_existing_directory=lambda *a,**k:str(selected.pop(0))
    mod.QInputDialog.getText=lambda *a,**k:("",True)
    parent=QWidget()
    # Single custom filename anywhere in user-selected path
    target=root/"externo"/"Voz_renombrada.wav"
    selected.append(target)
    results=mod.export_files(parent,[source1],project)
    assert results==[target] and target.read_bytes()==source1.read_bytes()
    print("SINGLE_NAME_CUSTOM_DIR_OK",flush=True)
    # Multiple: original names into selected directory, no nested folder
    folder=root/"destino";folder.mkdir()
    selected.append(folder);modes.append("Archivos separados")
    results=mod.export_files(parent,[source1,source2],project)
    assert {x.name for x in results}=={source1.name,source2.name}
    assert all(x.parent==folder for x in results)
    print("MULTI_SEPARATE_FOLDER_OK",flush=True)
    # Multiple: each individually with its own chosen file path
    one=root/"uno"/"Pista_1.wav";two=root/"dos"/"Pista_2.wav"
    selected.extend((one,two));modes.append("Elegir nombre")
    results=mod.export_files(parent,[source1,source2],project)
    assert results==[one,two] and all(x.is_file() for x in results)
    print("MULTI_INDIVIDUAL_NAMES_OK",flush=True)
    # Multiple -> ZIP, with name collisions protected
    bundle=root/"audio_en_lote.zip"
    selected.append(bundle);modes.append("Guardar como ZIP")
    results=mod.export_files(parent,[source1,source2],project)
    assert results==[bundle]
    with zipfile.ZipFile(bundle) as ar:
        assert ar.testzip() is None
        assert set(ar.namelist())=={source1.name,source2.name}
    print("MULTI_ZIP_OPTION_OK",flush=True)
    # Conflict: user chooses a free name; original export survives.
    selected.append(target);modes.append("Crear nombres nuevos")
    results=mod.export_files(parent,[source1],project)
    assert results[0]!=target and results[0].is_file()
    assert target.read_bytes()==source1.read_bytes()
    print("CONFLICT_KEEP_BOTH_OK",flush=True)
    # Conflict: explicit overwrite replaces only the destination.
    target.write_bytes(b"old")
    selected.append(target);modes.append("Sobrescribir")
    results=mod.export_files(parent,[source1],project)
    assert results==[target] and target.read_bytes()==source1.read_bytes()
    print("EXPLICIT_OVERWRITE_OK",flush=True)
    # Cancelled multi dialog does not touch anything.
    modes.append("Cancelar")
    assert not mod.export_files(parent,[source1,source2],project)
    assert all(hashlib.sha256(p.read_bytes()).digest()==sha
               for p,sha in before.items())
    print("CANCEL_AND_ORIGINAL_SOURCE_HASHES_OK",flush=True)
print("TEST_EXPORTACIONES_GUI_COMPLETADO",flush=True)
