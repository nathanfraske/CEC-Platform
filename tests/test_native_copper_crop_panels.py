"""A native pour outside one crop cannot manufacture metal on another face."""
import os
from pathlib import Path
import subprocess
import sys
import pcbnew
from PIL import Image,ImageChops
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board


def test_each_layer_panel_matches_its_independent_native_crop(tmp_path):
    board=_board([],edge=(0,0,100,100));board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'GND');board.Add(net)
    zone=pcbnew.ZONE(board);zone.SetNet(net);zone.SetLayer(pcbnew.F_Cu)
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in ((25,-100),(150,-100),(150,200),(25,200)):
        poly.Outline(0).Append(x*1000000,y*1000000)
    zone.Outline().Append(poly);zone.SetFilledPolysList(pcbnew.F_Cu,poly)
    zone.SetIsFilled(True);board.Add(zone)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    sha=force._hash(source)
    script=Path(__file__).resolve().parents[1]/'build/root_native_copper_crop_20261024.py'
    def render(name,layers):
        path=tmp_path/name
        command=[sys.executable,str(script),'--source',str(source),'--sha256',sha,
            '--bounds-mm','20','20','30','30','--layers',*map(str,layers),
            '--net','GND','--out',str(path)]
        job=subprocess.run(command,env=dict(os.environ,PYTHONPATH='scripts:ops:tests:build'),
            text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10.)
        assert job.returncode==0,job.stdout
        with Image.open(path)as image:return image.copy()
    combined=render('combined.png',[pcbnew.F_Cu,pcbnew.B_Cu])
    for col,face in enumerate((pcbnew.F_Cu,pcbnew.B_Cu)):
        single=render(str(face)+'.png',[face])
        crop=combined.crop((col*1400,0,(col+1)*1400,combined.height))
        assert ImageChops.difference(single,crop).getbbox()is None
    assert force._hash(source)==sha
