"""Native pre-refill ownership, exact post-refill frames and cut forwarding."""
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_fr as fr
import cec_stationary_ground_boundary_roots as roots
from test_complete_cell_connections import native_source


def test_normal_source_barrel_is_not_adopted_by_local_factory(tmp_path,monkeypatch):
    _,parent,_,_=native_source(tmp_path,monkeypatch)
    vias=[v for v in parent.GetTracks() if v.GetClass()=='PCB_VIA']
    assert vias and all((v.GetWidth(),v.GetDrillValue())==(600000,300000)for v in vias)
    before=row._source_binding(parent)
    assert fr.group_local_pofv_signal_vias(parent,vias) is None
    assert row._source_binding(parent)==before


@pytest.mark.parametrize('rows',[(),({'authority':{'kind':'untrusted_not_permission'}},)])
def test_stationary_wrapper_forwards_exact_cut_rows_without_filtering(tmp_path,monkeypatch,rows):
    _,parent,private,proposal=native_source(tmp_path,monkeypatch)
    seen=[]
    # Plumbing only: no ownership or positive native verdict is mocked.
    def receive(*args,**kwargs):
        seen.append(kwargs['additional_source_ground_cut_rows'])
        return {}
    monkeypatch.setattr(roots.original,'requests',receive)
    assert roots.requests(parent,private,proposal,additional_source_ground_cut_rows=rows)=={}
    assert len(seen)==1 and seen[0] is rows


def test_refill_requests_are_derived_before_refill_but_live_frame_is_exact(tmp_path,monkeypatch):
    import cec_additive_route_receiving as additive
    path,parent,private,proposal=native_source(tmp_path,monkeypatch)
    additive._ground_refill(private)
    refilled=row._source_binding(private)
    source_minus_cut=pcbnew.LoadBoard(str(path));escape.apply_private(source_minus_cut,proposal)
    prefill=row._source_binding(source_minus_cut)
    assert prefill!=refilled
    original=escape.obligations;seen=[]
    def observe(source,draft,fresh):
        seen.append(row._source_binding(draft))
        return original(source,draft,fresh)
    monkeypatch.setattr(escape,'obligations',observe)
    result=escape.complete_connection_screen(path,private,proposal,board_hint='opaque',
        allow_native_ground_refill=True,per_obligation_leases=True)
    assert result['complete'],result
    assert seen and all(binding==prefill for binding in seen)
    assert row._source_binding(private)==refilled


def test_changed_ground_fill_cannot_borrow_prefill_requests(tmp_path,monkeypatch):
    import cec_additive_route_receiving as additive
    path,parent,private,proposal=native_source(tmp_path,monkeypatch)
    additive._ground_refill(private)
    zone=next(z for z in private.Zones() if z.GetNetname()=='GND')
    zone.UnFill()
    before=row._source_binding(private)
    result=escape.complete_connection_screen(path,private,proposal,board_hint='opaque',
        allow_native_ground_refill=True,per_obligation_leases=True)
    assert not result['complete']
    assert any('complete_connection_draft_differs_from_exact_source_cut_and_pose'in e for e in result['errors'])
    assert row._source_binding(private)==before
