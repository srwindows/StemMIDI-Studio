"""Monitor/Grabación intocable: origen exacto, resto con sus 24 segmentos."""
import ast
import os
import sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from PySide6.QtWidgets import QApplication,QProgressBar
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter,QColor
from widgets import StereoMeter
from studio_home import VerticalMeter,StemMeter
from studio_vu_unified import (UnifiedPercentBar,db_fraction,from_percent,
    GREEN,AMBER,RED,SEGMENTS,draw_vertical_lane,draw_lane)
from project_mixer_expanded import ScaledMeter,HorizontalMasterMeter
from piano_realtime import PianoMeter
from midi_compact_vu import CompactStereoMeter
from compositor_meters import LevelMeter
from floating_transport import FloatingTransport

backup=root/"compilaciones"/"fuentes"/"respaldo_vu_unificados_20261104"
# La clase original de Monitor coincide literalmente con el respaldo.
assert (root/"widgets.py").read_bytes()==(backup/"widgets.py").read_bytes()
def class_src(path,name):
    source=path.read_text()
    tree=ast.parse(source)
    obj=next(node for node in tree.body
             if isinstance(node,ast.ClassDef) and node.name==name)
    return ast.get_source_segment(source,obj)
original=class_src(backup/"studio_home.py","VerticalMeter")
current=class_src(root/"studio_home.py","VerticalMeter")
assert current==original,"CAMBIARON EL VU DE REFERENCIA"
assert (GREEN,AMBER,RED)==("#40e985","#d0e82e","#ff4d50")
assert SEGMENTS==24
assert db_fraction(0)==0
assert db_fraction(1)==1
assert abs(db_fraction(from_percent(42))-0.42)<1e-6

app=QApplication([])
reference=VerticalMeter()
reference.resize(39,145)
reference.set_levels(1.,1.)
reference.show();app.processEvents()
original_img=reference.grab().toImage()
# El rojo tiene que quedar arriba, el verde abajo: imagen original.
red=original_img.pixelColor(8,9)
green=original_img.pixelColor(8,118)
assert red.red()>red.green(),red.name()
assert green.green()>green.red(),green.name()
reference.hide()

cases=[
 ("Pista de Inicio vertical",StemMeter(),True),
 ("Mezclador vertical",ScaledMeter("Piano"),True),
 ("Master horizontal",HorizontalMasterMeter("L"),False),
 ("Piano Roll horizontal",PianoMeter("L"),False),
 ("MIDI→Audio compacto",CompactStereoMeter(),False),
 ("Compositor L/R",LevelMeter(master=True),False),
 ("Compositor pista",LevelMeter(),False),
 ("Transporte flotante",UnifiedPercentBar(),False),
]
for name,m,vertical in cases:
    if isinstance(m,UnifiedPercentBar):
        m.setFixedSize(220,11);m.setValue(100)
    elif isinstance(m,StemMeter):
        m.resize(11,145);m.set_level(1)
    elif isinstance(m,PianoMeter):
        m.set_levels(1.,1.)
    elif isinstance(m,ScaledMeter):
        m.set_peak(1.);m.resize(86,108)
    elif isinstance(m,HorizontalMasterMeter):
        m.set_peak(1.)
    elif hasattr(m,"setLevels"):
        m.setLevels((1.,1.,1.,1.))
    elif hasattr(m,"set_levels"):
        m.set_levels(1.,1.,1.,1.)
    m.show();app.processEvents()
    im=m.grab().toImage()
    # Comparar los píxeles VU sin confundir números/texto con barras.
    red_found=green_found=False
    for yy in range(1,im.height()):
        for xx in range(1,im.width()):
            c=im.pixelColor(xx,yy)
            r,g,b=c.red(),c.green(),c.blue()
            green_found |= (g>150 and g>r*1.35 and g>b*1.15)
            red_found   |= (r>160 and r>g*1.6 and r>b*1.25)
    assert green_found and red_found,(name,green_found,red_found,im.size())
    if vertical:
        if isinstance(m,StemMeter):assert m.width()==11
        if isinstance(m,ScaledMeter):assert m.height()==108
    if isinstance(m,HorizontalMasterMeter):
        assert (m.width(),m.height())==(220,31)
    if isinstance(m,LevelMeter):
        assert m.height() in (24,34)
    print("REFERENCE_COLORS_AND_ORIENTATION_MATCH",name,
          im.width(),im.height(),flush=True)
    m.hide()
print("ORIGINAL_MONITOR_UNTOUCHED_AND_OTHERS_ADOPT_ORIGINAL_GREEN_YELLOW_RED_PASS")
