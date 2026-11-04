"""Arrastre real de ratón, soltar, autoencajar por filas y reordenar."""
import os,sys
from pathlib import Path
os.environ["STEMMIDI_NO_STARTUP_DIALOG"]="1"
os.environ["STEMMIDI_TEST_DUMMY_AUDIO"]="1"
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from main import MonitorWindow

def process():
    for _ in range(24):app.processEvents()

app=QApplication([])
w=MonitorWindow();w.resize(1720,1000);w.show()
w.tabs.setCurrentWidget(w.studio_home);process()
ws=w.studio_home.home_workspace
ws.to_free();process()
ws.set_editing(True)
card=w.studio_home.mon_card
old=ws.row_ids[0][:]
factor=abs(w.studio_home.scroll.transform().m11())
header=card.header
p=QPoint(55,12)
pointer_start=header.mapTo(ws.canvas,p)
destination=ws.by_id["pistas_separadas"].mapTo(
    ws.canvas,ws.by_id["pistas_separadas"].rect().center())
target=(destination-pointer_start)
end=QPoint(p.x()+round(target.x()),p.y()+round(target.y()))
QTest.mousePress(header,Qt.LeftButton,pos=p)
QTest.mouseMove(header,end,delay=55)
print("DROP_INDICATOR",ws.drop_indicator.geometry(),"MOVED",card.geometry(),flush=True)
QTest.mouseRelease(header,Qt.LeftButton,pos=p)
process()
assert "monitor" in ws.row_ids[1],(ws.row_ids,pointer_start,destination,target,factor)
assert [len(row) for row in ws.row_ids]==[4,4,4]
assert ws.row_ids[0][0] in ("vista_audio","desglose_bateria","pistas_separadas","mezclador")
assert abs(card.geometry().top() - ws.by_id[ws.row_ids[1][0]].geometry().top())<=1
print("DRAG_DROP_TOP_TO_MIDDLE_EXCHANGES_EXACTLY_TWO_SLOTS",ws.row_ids,flush=True)

# Mover la tarjeta hasta la cuarta casilla de su fila: sólo permuta
# con el módulo de esa casilla, y los otros diez quedan en el mismo lugar.
header=card.header
line=ws.row_surfaces[1].geometry()
p=QPoint(55,12)
target_right=QPoint(line.right()-12,line.center().y())
movement=(target_right-header.mapTo(ws.canvas,p))
end=QPoint(p.x()+round(movement.x()),p.y()+round(movement.y()))
QTest.mousePress(header,Qt.LeftButton,pos=p)
QTest.mouseMove(header,end,delay=55)
print("DROP_INDICATOR",ws.drop_indicator.geometry(),"MOVED",card.geometry(),flush=True)
QTest.mouseRelease(header,Qt.LeftButton,pos=p)
process()
assert ws.row_ids[1][-1]=="monitor",ws.row_ids
assert [len(row) for row in ws.row_ids]==[4,4,4]
rects=[ws.by_id[k].geometry() for k in ws.row_ids[1]]
assert all(a.right()<b.left() for a,b in zip(rects,rects[1:]))
assert max(r.width() for r in rects)-min(r.width() for r in rects)<=2
print("DRAG_DROP_SAME_ROW_EXCHANGES_EXACTLY_TWO_SLOTS",flush=True)
# Puntero agarrado desde el EXTREMO DERECHO de la cabecera: la
# casilla seleccionada sigue siendo aquella bajo el ratón, no la
# casilla debajo del centro de esta tarjeta.
before=[row[:] for row in ws.row_ids]
header=card.header
p=QPoint(max(5,header.width()-67),12)
pointer_start=header.mapTo(ws.canvas,p)
destination=ws.by_id["afinacion_vocal"].mapTo(
    ws.canvas,ws.by_id["afinacion_vocal"].rect().center())
movement=(destination-pointer_start)
end=QPoint(p.x()+round(movement.x()),p.y()+round(movement.y()))
QTest.mousePress(header,Qt.LeftButton,pos=p)
QTest.mouseMove(header,end,delay=55)
QTest.mouseRelease(header,Qt.LeftButton,pos=p)
process()
assert ws.row_ids[2][1]=="monitor",ws.row_ids
assert ws.row_ids[1][3]==before[2][1],ws.row_ids
assert [len(row) for row in ws.row_ids]==[4,4,4]
print("MOUSE_RIGHT_EDGE_GRAB_SWAPS_EXACTLY_UNDER_CURSOR_PASS",flush=True)

assert ws.canvas.grab().save("/tmp/stemmidi_inicio_intercambio_filas_4x4_20261104.png")
ws.set_editing(False)
assert ws.snapshot()["rows"]==ws.row_ids
w.hide();process()
print("MOUSE_EXACT_SWAP_3X4_ALL_PASS",flush=True)
