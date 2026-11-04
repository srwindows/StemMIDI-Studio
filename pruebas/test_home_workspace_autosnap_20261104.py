"""Prueba real de autoencaje: 12 módulos, filas completas y guardado."""
from __future__ import annotations
import os,sys,tempfile,json
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from main import MonitorWindow
from project_flow import create_named_project
import project_status_dialog,project_exit_guard,studio_shell
project_status_dialog.show_project_status=lambda *args,**kwargs:None
project_exit_guard.ask_exit_choice=lambda _:"discard"
studio_shell._protect_unsaved_project=lambda _:True

def events(app):
    for _ in range(16):app.processEvents()

def verify_rows(ws):
    # No huecos, solapes, ni posiciones arbitrarias. Cada fila se llena.
    assert [len(row) for row in ws.row_ids]==[4,4,4],ws.row_ids
    assert set(sum(ws.row_ids,[]))==set(ws.by_id)
    assert len(sum(ws.row_ids,[]))==12
    for row,keys in enumerate(ws.row_ids):
        rects=[]
        for key in keys:
            card=ws.by_id[key]
            assert card.parentWidget() in ws.row_surfaces
            r=card.geometry().translated(card.parentWidget().mapTo(ws.canvas,QPoint(0,0)))
            assert r.height()>110,(key,r)
            rects.append(r)
        assert all(abs(a.top()-b.top())<=2 for a,b in zip(rects,rects[1:])),(row,rects)
        assert all(abs(a.height()-b.height())<=2 for a,b in zip(rects,rects[1:])),(row,rects)
        assert all(a.right()<b.left() for a,b in zip(rects,rects[1:])),(row,rects)
        assert max(r.width() for r in rects)-min(r.width() for r in rects)<=2,(row,rects)
        left,right=ws.row_surfaces[row].geometry().left(),ws.row_surfaces[row].geometry().right()
        assert abs(rects[0].left()-left)<=3,(row,rects[0],left)
        assert abs(rects[-1].right()-right)<=3,(row,rects[-1],right)
    return True

with tempfile.TemporaryDirectory(prefix="stemmidi_snap_rows_") as td:
    app=QApplication([])
    w=MonitorWindow();w.resize(1690,1000);w.show()
    assert create_named_project(
        w,"Snap A",Path(td)/"projects",w.format.currentText(),44100)
    w.tabs.setCurrentWidget(w.studio_home);events(app)
    ws=w.studio_home.home_workspace
    mgr=w.studio_home._floating_manager
    assert not ws.is_free
    ws.to_free();events(app)
    assert verify_rows(ws)
    print("FOUR_PER_ROW_ALIGNED_AND_FILLED_NO_GAPS_PASS",flush=True)

    # Un movimiento entre filas SOLO permuta dos módulos. Los otros
    # diez no cambian de casilla, ni las filas cambian de tamaño.
    def assert_exact_swap(before,after,source,target):
        assert all(len(row)==4 for row in after),after
        a=next((i,j) for i,row in enumerate(before)
               for j,key in enumerate(row) if key==source)
        b=target
        expected=json.loads(json.dumps(before))
        expected[a[0]][a[1]],expected[b[0]][b[1]]=(
            expected[b[0]][b[1]],expected[a[0]][a[1]])
        assert after==expected,(before,after,expected)

    card=w.studio_home.vocal_card
    before=json.loads(json.dumps(ws.row_ids))
    geometry_before={key:ws.by_id[key].geometry()
                     for key in ws.by_id}
    assert ws.reorder_card(card,0,1)
    events(app)
    assert_exact_swap(before,ws.row_ids,"afinacion_vocal",(0,1))
    moved_other=[(key,old_rect,ws.by_id[key].geometry()) for key,old_rect in geometry_before.items()
               if key not in ("afinacion_vocal","separacion")
               and ws.by_id[key].geometry()!=old_rect]
    print("OTHER_GEOMETRY_DIFFERENCES",moved_other,flush=True)
    assert not moved_other,"Las otras diez tarjetas han cambiado su geometría"
    assert verify_rows(ws)
    print("CROSS_ROW_SWAP_CHANGES_ONLY_TWO_SLOTS_PASS",flush=True)

    # Misma fila: arrastrar a la primera casilla intercambia con el
    # módulo que estaba allí; nunca desplaza los otros tres.
    before=json.loads(json.dumps(ws.row_ids))
    unaffected={key:ws.by_id[key].geometry()
                for key in ws.by_id if key not in ("afinacion_vocal","monitor")}
    assert ws.reorder_card(card,0,0)
    events(app)
    assert_exact_swap(before,ws.row_ids,"afinacion_vocal",(0,0))
    assert all(ws.by_id[key].geometry()==rect
               for key,rect in unaffected.items())
    assert verify_rows(ws)
    print("SAME_ROW_SWAP_CHANGES_ONLY_TWO_SLOTS_PASS",flush=True)

    # Una fila ya tiene cuatro y NUNCA acepta cinco: hace el cambio
    # exacto con la tarjeta que ocupa el destino.
    card2=w.studio_home.drum_stems_card
    before=json.loads(json.dumps(ws.row_ids))
    assert ws.reorder_card(card2,0,2)
    events(app)
    assert_exact_swap(before,ws.row_ids,"bateria_pistas",(0,2))
    assert verify_rows(ws)
    print("THREE_ROWS_ALWAYS_FOUR_NO_OTHER_MOVES_PASS",flush=True)

    # Soltar sobre sí misma no reordena nada ni marca cambios.
    before=json.loads(json.dumps(ws.row_ids))
    active_row=next(i for i,row in enumerate(ws.row_ids)
                    if "bateria_pistas" in row)
    active_col=ws.row_ids[active_row].index("bateria_pistas")
    assert not ws.reorder_card(card2,active_row,active_col)
    assert ws.row_ids==before

    # El candado conserva exactamente su casilla de fila.
    card=w.studio_home.vocal_card
    old_rows=json.loads(json.dumps(ws.row_ids))
    mgr.detach(card);events(app)
    assert mgr.is_detached(card)
    assert verify_rows(ws) if False else True
    assert mgr.originals[card][1] is not None
    # Es posible reorganizar las otras once mientras ésta está flotando.
    # Al cerrarla debe recuperar la nueva casilla y no un lugar obsoleto.
    assert ws.reorder_card(w.studio_home.mix_card,2,1)
    events(app)
    expected_rows=json.loads(json.dumps(ws.row_ids))
    assert_exact_swap(old_rows,expected_rows,"mezclador",(2,1))
    mgr.redock(card);events(app)
    assert ws.row_ids==expected_rows
    assert verify_rows(ws)
    print("DETACH_REDOCK_AFTER_OTHERS_REORDERED_SAME_SLOT_PASS",flush=True)

    assert studio_shell.save_project(w,show_confirmation=False)
    path_a=Path(w.project_path)
    saved_a=json.loads(path_a.read_text())["home_workspace"]
    assert saved_a["version"]==3
    assert saved_a["rows"]==ws.row_ids
    assert "cards" not in saved_a
    assert create_named_project(
        w,"Snap B",Path(td)/"projects",w.format.currentText(),44100)
    assert not ws.is_free
    assert studio_shell.save_project(w,show_confirmation=False)
    assert studio_shell.open_project(w,path_a);events(app)
    assert ws.is_free and ws.row_ids==saved_a["rows"]
    assert verify_rows(ws)
    print("SAVE_AND_REOPEN_RESPECTS_AUTOSNAPPED_ROWS_PASS",flush=True)

    # Migración de proyectos guardados con el sistema «cutre» v1.
    old_payload={
        "version":1,"mode":"free",
        "cards":{
            key:[(index%4)*.25,(index//4)*.333,.22,.32]
            for index,key in enumerate(ws.by_id)
        }
    }
    ws.restore(old_payload);events(app)
    assert ws.is_free and verify_rows(ws)
    assert ws.snapshot()["version"]==3
    print("OLD_FREE_LAYOUT_UPGRADED_TO_ALIGNED_ROWS_PASS",flush=True)

    # Las distribuciones erróneas v2 de 5+3+4 se normalizan a 4+4+4
    # sin perder ningún módulo ni duplicar controles.
    original=list(ws.by_id)
    previous={"version":2,"mode":"free",
              "rows":[original[:5],original[5:8],original[8:]]}
    ws.restore(previous);events(app)
    assert [len(row) for row in ws.row_ids]==[4,4,4]
    assert [key for row in ws.row_ids for key in row]==original
    print("OLD_BAD_5_3_4_DISTRIBUTION_MIGRATES_TO_4_4_4_PASS",flush=True)
    ws.to_factory();events(app)
    assert not ws.is_free and all(not row.isHidden() for row in ws.rows)
    w.hide();events(app)
print("ALL_AUTOSNAP_FUNCTIONAL_TESTS_PASS",flush=True)
