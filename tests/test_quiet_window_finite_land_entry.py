"""Longer pad-centre distance is not a longer exposed lead or a tiny cap."""
from pathlib import Path
import math
import pytest
import cec_quiet_signal_via_clearance_window as operation
import cec_force_current as force
from test_quiet_signal_via_clearance_window import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',(False,True))
def test_positive_full_native_start_disk_within_actual_Source_land(tmp_path,monkeypatch,quarter,back):
    source,args,_,_=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    board=operation.pcbnew.LoadBoard(str(source));pad,_=operation.geometry._pad(board,args['pad_uuid'])
    centre=list(pad.GetPosition());unit=[(args['position_nm'][k]>centre[k])-(args['position_nm'][k]<centre[k])for k in(0,1)]
    args['position_nm']=[centre[k]+unit[k]*1600000 for k in(0,1)]
    q=operation.plan(source,**args)
    assert q['finite_Source_land_entry'] and q['source_pad_centre_nm']==centre
    assert math.dist(q['start_nm'],q['at_nm'])<=1500000
    assert operation.geometry.fab._pad_contains_circle(pad,operation.pcbnew.VECTOR2I(*q['start_nm']),125000,tolerance_nm=0)
    result=operation.write_private(q,tmp_path/'child');proof=operation.receive(source,Path(result['candidate']),**args)
    assert proof['ok'] and proof['complete'],proof
    assert not proof['ordinary_net_alias'] and not proof['Kelvin_input_authority']


def test_native_curved_land_boundary_never_becomes_bbox_or_shorter_lead_waiver(tmp_path,monkeypatch):
    source,args,_,_=fixture(tmp_path,monkeypatch)
    board=operation.pcbnew.LoadBoard(str(source));pad,_=operation.geometry._pad(board,args['pad_uuid'])
    centre=list(pad.GetPosition());args['position_nm']=[centre[0],centre[1]-1700000]
    with pytest.raises(ValueError,match='start_cap_not_inside_actual_land'):
        operation.plan(source,**args)


def test_finite_entry_cannot_be_supplied_to_ordinary_public_owner(tmp_path,monkeypatch):
    source,args,_,_=fixture(tmp_path,monkeypatch)
    with pytest.raises(TypeError):operation.geometry.plan(source,**args,_start_nm=[1,2])
