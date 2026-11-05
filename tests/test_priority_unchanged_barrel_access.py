"""Native complete enclosure can preserve a bus while a local barrel follows."""
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_priority_preflight as priority
import cec_smd_macro_transport as macro
from test_stationary_qualified_neckdown_contact import pair
from test_smd_macro_transport import inventory


def native_pair(tmp_path,monkeypatch,*,back=False,quarter=0,delta=.22):
    a,b,path,prefix,ground,throat=pair(tmp_path,monkeypatch,positive_barrel=True,back=back,quarter=quarter)
    net=a.FindNet('/opaque_input');via=next(t for t in a.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='/opaque_input')
    fx,fy=0,3
    for _ in range(quarter):fx,fy=fy,-fx
    feed=pcbnew.PCB_TRACK(a);feed.SetStart(via.GetPosition());feed.SetEnd(via.GetPosition()+pcbnew.VECTOR2I_MM(fx,fy))
    feed.SetWidth(1000000);feed.SetLayer(pcbnew.F_Cu if back else pcbnew.B_Cu);feed.SetNet(net);a.Add(feed)
    field._save_field_snapshot(a,path);a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    dx,dy=0,delta
    for _ in range(quarter):dx,dy=dy,-dx
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(dx,dy))
    result=macro.apply(a,b,source_path=path,board_hint='opaque_synthetic')
    monkeypatch.setattr(priority.topology,'route_width_contracts',lambda *a,**kw:
        {'/opaque_input':dict(current_authority=dict(source='board_design_basis'))})
    monkeypatch.setattr(priority.fr,'locked_pour_authority_nets_board',lambda *a,**kw:set())
    return a,b,result,force._uid(feed),force._uid(via)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_same_source_wide_copper_contains_carried_barrel_without_bus_motion(tmp_path,monkeypatch,back,quarter):
    a,b,transport,feed,via=native_pair(tmp_path,monkeypatch,back=back,quarter=quarter)
    assert inventory(a)[feed]==inventory(b)[feed]
    assert not priority.inspect(a,b,transport,board_hint='opaque_synthetic')['ok']
    observed=priority.inspect(a,b,transport,board_hint='opaque_synthetic',allow_contained_source_barrel_motion=True)
    assert observed['ok'] and observed['saved_current_receiving_required']
    proof=observed['source_owned_in_pad_vias_with_unchanged_full_width_access']
    assert proof[0]['uuid']==via and proof[0]['complete_native_barrel_enclosure']
    assert not observed['source_owned_local_power_escape_extensions']
    assert not observed['current_or_clearance_qualified'] and not observed['release_authority']


@pytest.mark.parametrize('fault',['partial','undeclared_feed_width','forged_barrel_motion'])
def test_partial_copper_overlap_or_changed_bus_never_grants_priority_motion(tmp_path,monkeypatch,fault):
    a,b,transport,feed,via=native_pair(tmp_path,monkeypatch)
    if fault=='partial':
        next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,-.62))
        for t in b.GetTracks():
            if t.GetClass()=='PCB_VIA':t.Move(pcbnew.VECTOR2I_MM(0,-.62))
    if fault=='undeclared_feed_width':next(t for t in b.GetTracks() if force._uid(t)==feed).SetWidth(999999)
    if fault=='forged_barrel_motion':next(t for t in b.GetTracks() if force._uid(t)==via).Move(pcbnew.VECTOR2I(1,0))
    before=inventory(b)
    try:observed=priority.inspect(a,b,transport,board_hint='opaque_synthetic',allow_contained_source_barrel_motion=True)
    except ValueError:pass
    else:assert not observed['ok']
    assert inventory(b)==before


def test_contained_barrel_policy_requires_an_explicit_boolean(tmp_path,monkeypatch):
    a,b,transport,feed,via=native_pair(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bounded_source_macro_priority_preflight'):
        priority.inspect(a,b,transport,board_hint='opaque_synthetic',allow_contained_source_barrel_motion=1)
