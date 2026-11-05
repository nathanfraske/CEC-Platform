"""An explicit larger Source work tier is not a wider cut permission."""
import time
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_force_current as force
import cec_macro_obstacle_cuts as cuts
from test_macro_obstacle_cuts import fixture
from test_field_proposals import track


def many(tmp_path,monkeypatch):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch)
    for i in range(18):
        item=track(parent,'foreign_signal',(6,5.001+i*.001),(8,5.001+i*.001),width=.2)
        ids.append(force._uid(item))
    return source,parent,private,proposal,ids


def test_twenty_literal_thin_leads_require_explicit_32_work_tier(tmp_path,monkeypatch):
    source,parent,private,proposal,ids=many(tmp_path,monkeypatch)
    with pytest.raises(ValueError):
        cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.,max_tracks=16)
    proof=cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.,max_tracks=32)
    assert len(proof)==20 and {q['change']['uuid'] for q in proof}==set(ids)
    assert all(q['authority']['kind']=='positive_source_ordinary' for q in proof)
    assert all(q['source_native_obstacle_ownership']['literal_foreign_native_conflicts'] for q in proof)


@pytest.mark.parametrize('fault',['wide','ground','unrelated'])
def test_extended_work_cannot_acquire_bus_ground_or_an_unrelated_component(tmp_path,monkeypatch,fault):
    source,parent,private,proposal,ids=many(tmp_path,monkeypatch)
    item=next(t for t in parent.GetTracks() if force._uid(t)==ids[-1])
    if fault=='wide':item.SetWidth(400000)
    elif fault=='ground':item.SetNet(parent.FindNet('GND'))
    else:item.Move(pcbnew.VECTOR2I_MM(15,15))
    with pytest.raises(ValueError):
        cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.,max_tracks=32)


def test_unused_component_refusal_names_exact_source_tracks(tmp_path,monkeypatch):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch)
    for t in parent.GetTracks():t.Move(pcbnew.VECTOR2I_MM(0,5))
    with pytest.raises(ValueError) as failure:
        cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.)
    assert str(failure.value)=='additional_cut_component_does_not_block_actual_future_native_copper:'+','.join(sorted(ids))
