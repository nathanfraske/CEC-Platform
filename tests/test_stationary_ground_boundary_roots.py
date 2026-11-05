"""A stranded fixed branch need not detour through a newly moving capacitor."""
import copy
import pcbnew
import pytest
import cec_cell_ground_cut_boundaries as original
import cec_cell_row_rebuild as binding
import cec_force_current as force
import cec_stationary_ground_boundary_roots as roots
from cec_native_items import discard_items
from test_stationary_ground_forest import fixture

def context(tmp_path,quarter=0,back=False):
    parent,posed,source,q,owner,fixed,via,edges,tail=fixture(tmp_path,quarter,back)
    q['poses']={owner.GetReference():[posed.FindFootprintByReference(owner.GetReference()).GetPosition().x/1e6,
        posed.FindFootprintByReference(owner.GetReference()).GetPosition().y/1e6,
        posed.FindFootprintByReference(owner.GetReference()).GetOrientationDegrees()]}
    discard_items(posed,[t for t in posed.GetTracks() if force._uid(t) in q['retired_track_uuids']])
    return parent,posed,q,force._uid(via)

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_unchanged_source_root_replaces_only_the_moving_request_endpoint(tmp_path,quarter,back):
    a,b,q,rid=context(tmp_path,quarter,back);before=[binding._source_binding(x) for x in (a,b)]
    old=original.requests(a,b,q);new=roots.requests(a,b,q)
    assert old and old.keys()==new.keys()
    assert all(r['a'].get('native_uuids')==[rid] for r in new.values())
    for key,row in new.items():
        assert row['b']==old[key]['b'] and row['width_nm']==old[key]['width_nm'] and row['net']==old[key]['net']=='GND'
        proof=row['stationary_source_ground_root_restoration']
        assert proof['unchanged_native_barrel_and_live_process'] and proof['native_original_component_membership']
        assert len(proof['actual_saved_reference_contacts'])==2 and not proof['current_qualified'] and not proof['release_authority']
        assert proof['original_moving_entry_endpoint']==old[key]['a']
    assert before==[binding._source_binding(x) for x in (a,b)]

@pytest.mark.parametrize('fault',['moved_root','root_width','root_drill','missing_root','lost_plane','moved_fixed_pad'])
def test_changed_unqualified_or_missing_stationary_material_has_no_root_credit(tmp_path,fault):
    a,b,q,rid=context(tmp_path);root=next(t for t in b.GetTracks() if force._uid(t)==rid)
    if fault=='moved_root':root.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='root_width':root.SetWidth(root.GetWidth(root.TopLayer())+1)
    elif fault=='root_drill':root.SetDrill(root.GetDrillValue()+1)
    elif fault=='missing_root':discard_items(b,[root])
    elif fault=='lost_plane':next(iter(b.Zones())).UnFill()
    else:
        old=original.requests(a,b,q);uid=next(iter(old.values()))['b']['pad_uuid']
        next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==uid).Move(pcbnew.VECTOR2I(1,0))
    try:actual=roots.requests(a,b,q)
    except ValueError:return
    assert not any(r.get('stationary_source_ground_root_restoration') for r in actual.values())

@pytest.mark.parametrize('timeout',[True,0,-1,10.001,float('nan')])
def test_no_larger_native_lease_is_granted(timeout):
    with pytest.raises(ValueError):roots.requests(None,None,None,timeout_s=timeout)

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_private_root_macro_keeps_complete_saved_native_receiving(tmp_path,monkeypatch,quarter,back):
    from test_complete_macro_cell import fixture as macro_fixture
    import cec_fixed_ground_root_macro as private
    import cec_additive_route_receiving as additive
    import cec_field_coupling as field
    source,parent,unused,old=macro_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    board,packet=private.compiler.compile(source,old['source_plan']['poses'],board_hint='opaque')
    additive._ground_refill(board)
    proof=private.macro.screen(source,board,packet,board_hint='opaque')
    assert proof['complete'],proof.get('errors')
    private.escape.construct_private(board,proof['packet'],proof['selection']);additive._ground_refill(board)
    child=force._copy_family(source,tmp_path/'private-fixed-ground-root-macro')
    field._save_field_snapshot(board,child)
    result=private.macro.receive(source,child,board_hint='opaque')
    assert result['ok'] and result['complete'],result['errors']
    assert not result['routing_admitted'] and not result['release_authority']

def test_root_extension_never_patches_shared_global_macro_engines():
    import cec_cell_macro_requests as compiler
    import cec_cell_escape_replan as escape
    import cec_complete_macro_cell as macro
    expected=compiler.compile,escape.complete_connection_screen,macro.receive
    import cec_fixed_ground_root_macro as private
    assert expected==(compiler.compile,escape.complete_connection_screen,macro.receive)
    assert private.compiler is not compiler and private.escape is not escape and private.macro is not macro
