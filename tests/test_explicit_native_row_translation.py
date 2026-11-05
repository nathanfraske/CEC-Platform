"""Explicit finite native reach is replayed, not inferred from annotations."""
import copy
import pcbnew
import pytest
import cec_cell_row_rebuild as row
from test_cell_row_rebuild import fixture


@pytest.mark.parametrize('distance',[64.000001,71.,100.,128.])
def test_native_row_requires_explicit_reach_and_retains_immutable_survivors(distance):
    board,_,_,_=fixture(locked=False)
    fp=board.FindFootprintByReference('OWNER')
    poses={'OWNER':[fp.GetPosition().x/1e6+distance,fp.GetPosition().y/1e6,0.]}
    before=row._source_binding(board)
    with pytest.raises(ValueError,match='cell_translation_budget'):row.plan(board,poses,{})
    q=row.plan(board,poses,{},maximum_translation_mm=distance)
    assert q['maximum_translation_mm']==distance
    assert q['routing_admitted'] is False and q['requires_new_power_prefix_and_rated_current_receiving']
    forged=copy.deepcopy(q);forged['maximum_translation_mm']=64.
    with pytest.raises(ValueError):row.apply(board,forged)
    assert row._source_binding(board)==before
    row.apply(board,q)
    assert list(fp.GetPosition())==[round(poses['OWNER'][0]*1e6),10000000]


@pytest.mark.parametrize('value',[True,0,-1,128.000001,float('nan'),float('inf'),'128'])
def test_invalid_native_reach_refuses_without_mutation(value):
    board,poses,cells,_=fixture();before=row._source_binding(board)
    with pytest.raises(ValueError):row.plan(board,poses,cells,maximum_translation_mm=value)
    assert before==row._source_binding(board)


def test_default_row_packet_has_no_silent_reach_change():
    board,poses,cells,_=fixture();q=row.plan(board,poses,cells)
    assert 'maximum_translation_mm' not in q
