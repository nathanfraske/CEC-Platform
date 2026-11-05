"""Native segmentation changes neither local budgets nor their safeguards."""
import pcbnew
import pytest
import cec_supply_consumer_branch as consumer
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_supply_consumer_branch import fixture


def subdivide(board, old, count):
    start, end = tuple(old.GetStart()), tuple(old.GetEnd())
    width, layer, code = old.GetWidth(), old.GetLayer(), old.GetNetCode()
    discard_items(board, [old])
    tracks=[]
    for i in range(count):
        at=lambda n:pcbnew.VECTOR2I(*(round(a+(b-a)*n/count) for a,b in zip(start,end)))
        t=pcbnew.PCB_TRACK(board); t.SetStart(at(i)); t.SetEnd(at(i+1))
        t.SetWidth(width); t.SetLayer(layer); t.SetNetCode(code); board.Add(t)
        tracks.append(t)
    return tracks


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_native_subdivision_preserves_the_exact_same_allowance(monkeypatch,tmp_path,angle,mirror):
    board,root,anchor,new,old,trunk,*_=fixture(monkeypatch,tmp_path,angle=angle,mirror=mirror)
    tracks=subdivide(board,old,64)
    field._save_field_snapshot(board,board.GetFileName())
    loaded=pcbnew.LoadBoard(board.GetFileName())
    snapshot=field._field_snapshot_inventory(loaded)
    proof=consumer.inventory(loaded,board_hint='arbitrary',timeout_s=10.)
    assert proof['complete'],proof['refusals']
    assert set(proof['retained_island_track_requirements'])=={force._uid(t) for t in tracks}
    assert force._uid(trunk) not in proof['all_owned_track_requirements']
    assert all(q['current_authority']['amps']==.5 for q in proof['all_owned_track_requirements'].values())
    assert proof['proofs'][0]['budget']['aggregate_current_authority']['amps']==3.
    assert proof['proofs'][0]['physical_trunk_tap_count']==1
    assert field._field_snapshot_inventory(loaded)==snapshot


@pytest.mark.parametrize('fault',['bounded_work','unknown_load','second_tap'])
def test_larger_work_bound_does_not_relax_native_exclusivity(monkeypatch,tmp_path,fault):
    board,root,anchor,new,old,trunk,*_=fixture(monkeypatch,tmp_path)
    subdivide(board,old,consumer.MAX_RETAINED_ISLAND_ITEMS if fault=='bounded_work' else 64)
    if fault=='unknown_load':
        fp=pcbnew.FOOTPRINT(board); board.Add(fp); fp.SetValue('unknown')
        pad=pcbnew.PAD(fp); fp.Add(pad); pad.SetNet(root.GetNet())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(1,1)); pad.SetPosition(root.GetPosition())
    elif fault=='second_tap':
        trunk.SetStart(pcbnew.VECTOR2I_MM(6,5))
    proof=consumer.inventory(board,board_hint='arbitrary',timeout_s=10.)
    assert not proof['complete'] and proof['refusals']
    assert not proof['all_owned_track_requirements']
    if fault=='bounded_work':
        assert 'bounded_retained_consumer_island_required' in str(proof['refusals'])
