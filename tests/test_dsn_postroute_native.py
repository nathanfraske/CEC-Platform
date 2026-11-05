"""Opt-in pinned-backend gate: route-only must route, not disable all layers.

Run with CEC_TEST_NATIVE_FR=1. Never downloads a backend during test discovery.
These synthetic boards grant no production-board release authority.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pcbnew
import pytest
import cec_fr as fr
from cec_fr02 import set_postroute_in_dsn

pytestmark=pytest.mark.skipif(os.environ.get('CEC_TEST_NATIVE_FR')!='1',
    reason='explicit native pinned-backend test required')


@pytest.mark.parametrize('opposite_side',[False,True])
def test_route_only_real_backend_completes_signal_and_layer_transition(tmp_path,opposite_side):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(2)
    for a,c in [((0,0),(30,0)),((30,0),(30,20)),((30,20),(0,20)),((0,20),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b,pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I(*(pcbnew.FromMM(v) for v in a)))
        edge.SetEnd(pcbnew.VECTOR2I(*(pcbnew.FromMM(v) for v in c)))
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(pcbnew.FromMM(.1));b.Add(edge)
    net=pcbnew.NETINFO_ITEM(b,'SIGNAL (postroute off)');b.Add(net)
    for index,x in enumerate((5,25)):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('P'+str(index+1))
        fp.SetFPID(pcbnew.LIB_ID('Synthetic','NativePad'))
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(10)))
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I(1000000,1000000))
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(fp.GetPosition());pad.SetNet(net)
        fp.Add(pad);b.Add(fp)
        if index and opposite_side:fp.Flip(fp.GetPosition(),False)
    b.BuildConnectivity();b.GetConnectivity().RecalculateRatsnest()
    assert b.GetConnectivity().GetUnconnectedCount(False)==1
    source=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    dsn=tmp_path/'private.dsn';ses=tmp_path/'private.ses'
    assert pcbnew.ExportSpecctraDSN(b,str(dsn))
    manifest=set_postroute_in_dsn(dsn,False)
    assert manifest['new_scope_search_profile']=='explicit_signal_layers_vias_costs_v1'
    fr.validate_dsn_structure(str(dsn))
    fr.run_freerouting(str(dsn),str(ses),passes=3,opt_time=0,threads=1,
                      timeout=20,workdir=str(tmp_path))
    routed=pcbnew.LoadBoard(str(source));assert pcbnew.ImportSpecctraSES(routed,str(ses))
    routed.BuildConnectivity();routed.GetConnectivity().RecalculateRatsnest()
    assert routed.GetConnectivity().GetUnconnectedCount(False)==0
    assert list(routed.GetTracks())
    if opposite_side:assert any(t.GetClass()=='PCB_VIA' for t in routed.GetTracks())
    candidate=tmp_path/'routed.kicad_pcb';pcbnew.SaveBoard(str(candidate),routed)
    report=tmp_path/'native.drc.json'
    result=subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all',
        '--output',str(report),str(candidate)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    drc=json.loads(report.read_text())
    assert not drc['unconnected_items']
    assert not [v for v in drc['violations'] if v['type'] in
                ('shorting_items','clearance','tracks_crossing','track_width','via_diameter','drill_out_of_range')]
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
