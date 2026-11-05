"""Distinct canonical cap leaves survive complete macro debt derivation."""
import copy,time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_aggregate_cap_ground_leaf as ground
from test_aggregate_cap_ground_leaf import fixture


@pytest.mark.parametrize('quarter',range(4))
def test_actual_canonical_leaf_is_retired_only_with_complete_Ground_boundary_demands(tmp_path,monkeypatch,quarter):
    source,root,parent,pad,ids,peer=fixture(tmp_path,monkeypatch,quarter)
    fp=pad.GetParentFootprint();owner=parent.FindFootprintByReference('AMP73')
    # Native cardinal transform of the existing fixture's local destination.
    x,y=-1000000,-2000000
    for _ in range(quarter):x,y=y,-x
    poses={fp.GetReference():[(x+15000000)/1e6,(y+15000000)/1e6,fp.GetOrientationDegrees()],
        owner.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()]}
    before=escape.row._source_binding(parent)
    q=escape.prepare(parent,poses,board_hint=str(root))
    assert set(ids)<=set(q['retired_track_uuids'])
    leaves=[p for p in q['ground_leaves'] if p['scope']==ground.SCOPE]
    assert len(leaves)==1 and leaves[0]['track_uuids']==ids and leaves[0]['boundary_uuids']==[peer]
    child=pcbnew.LoadBoard(str(source));escape.apply_private(child,q)
    assert not set(ids)&{escape.force._uid(t) for t in child.GetTracks()}
    requests=escape.obligations(parent,child,q)
    immediate=requests['ground:'+escape.force._uid(pad)]
    assert immediate['reach_mm']==.8 and immediate['width_nm']==500000
    boundaries=[r for r in requests.values() if r['kind']=='ground_boundary' and r['net']=='GND']
    assert any(r['b'].get('pad_uuid')==peer for r in boundaries)
    assert all(r['width_nm']==500000 and set(ids)<=set(r['retained_source_ground_fragment']['retired_ground_track_uuids'])
        for r in boundaries)
    assert before==escape.row._source_binding(parent)


def test_source_frame_does_not_accept_a_forged_embedded_cap_leaf(tmp_path,monkeypatch):
    source,root,parent,pad,ids,peer=fixture(tmp_path,monkeypatch)
    fp=pad.GetParentFootprint();owner=parent.FindFootprintByReference('AMP73')
    poses={fp.GetReference():[14,14,0],owner.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()]}
    q=escape.prepare(parent,poses,board_hint=str(root));before=escape.row._source_binding(parent)
    forged=copy.deepcopy(q);forged['ground_leaves'][0]['track_uuids']=ids[:1]
    with pytest.raises(ValueError,match='stale_or_forged'):
        escape.apply_private(parent,forged)
    assert before==escape.row._source_binding(parent)
