"""Typed quiet windows independently replay off-centre full-width entries."""
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_quiet_signal_via_clearance_window as operation
from test_quiet_signal_via_clearance_window import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',(False,True))
def test_actual_Source_role_and_native_window_replay_offcentre_entry(tmp_path,monkeypatch,quarter,back):
    source,args,_,_=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    dx,dy=50000,0
    for _ in range(quarter):dx,dy=-dy,dx
    if back:dx=-dx
    args['position_nm']=[args['position_nm'][0]+dx,args['position_nm'][1]+dy]
    board=pcbnew.LoadBoard(str(source));pad,_=operation.geometry._pad(board,args['pad_uuid'])
    assert not operation.geometry.quality.is_canonical_stroke(list(pad.GetPosition()),args['position_nm'],tolerance_nm=0)
    q=operation.plan(source,**args)
    assert q['finite_Source_land_entry']and q['start_nm']!=list(pad.GetPosition())
    assert (q['width_nm'],q['diameter_nm'],q['drill_nm'])==(250000,600000,300000)
    assert operation.geometry.fab._pad_contains_circle(pad,pcbnew.VECTOR2I(*q['start_nm']),125000,tolerance_nm=0)
    before=source.read_bytes();written=operation.write_private(q,tmp_path/'offcentre-child')
    proof=operation.receive(source,Path(written['candidate']),**args)
    assert proof['ok']and proof['complete'],proof
    assert proof['source_sensitive_class_preserved']and proof['original_native_partitions_preserved']
    assert source.read_bytes()==before
    with pytest.raises(ValueError,match='not_positively_ordinary'):operation.geometry.plan(source,**args)
