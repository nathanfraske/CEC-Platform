"""Priority preflight must rederive a declared strap AND its external leaf."""
import copy
import pcbnew
import pytest
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_macro_priority_preflight as priority
import cec_measurement_leaf as leaf
import cec_smd_macro_transport as transport
from test_measurement_auxiliary_cut import fixture
from test_field_proposals import track


def pair(tmp_path,monkeypatch,quarter=0,back=False):
    board,path,owner,strap,departure=fixture(tmp_path,quarter,back)
    parent=pcbnew.LoadBoard(str(path));child=pcbnew.LoadBoard(str(path))
    child.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I_MM(.5,.5))
    moved=transport.apply(parent,child)
    root=force._uid(owner.FindPadByNumber('9'))
    external,internal=leaf.plan_with_auxiliary_strap(parent,root)
    proofs=[external,internal];retired=[u for r in proofs for u in r['track_uuids']]
    monkeypatch.setattr(priority.topology,'route_width_contracts',lambda *a,**k:{
        external['net']:dict(current_authority=dict(source='board_design_basis'))})
    monkeypatch.setattr(priority.fr,'locked_pour_authority_nets_board',lambda *a,**k:{external['net']})
    return parent,child,moved,proofs,retired


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_rotated_strap_and_external_leaf_keep_both_mandatory_scopes(tmp_path,monkeypatch,quarter,back):
    parent,child,moved,proofs,retired=pair(tmp_path,monkeypatch,quarter,back)
    before=[row._source_binding(b) for b in (parent,child)]
    assert not priority.inspect(parent,child,moved,board_hint='opaque')['ok']
    result=priority.inspect(parent,child,moved,board_hint='opaque',
        source_measurement_leaves=proofs,retired_source_track_uuids=retired)
    assert result['ok'],result
    assert result['independently_typed_source_measurement_reconstruction']==proofs
    assert result['source_measurement_retirement_is_not_force_bus_retirement']
    assert {r['width_nm'] for r in result['independently_typed_source_measurement_reconstruction']}=={200000,250000}
    assert before==[row._source_binding(b) for b in (parent,child)]
    assert not result['current_or_clearance_qualified'] and not result['release_authority']


@pytest.mark.parametrize('fault',['missing_strap','missing_external','duplicate_strap','duplicate_external',
    'strap_width','strap_contact','strap_binding','external_context','external_width','strap_cut',
    'external_cut','wrong_scope','wrong_owner'])
def test_a_missing_forged_or_partial_role_cannot_become_a_priority_waiver(tmp_path,monkeypatch,fault):
    parent,child,moved,proofs,retired=pair(tmp_path,monkeypatch)
    proofs=copy.deepcopy(proofs)
    if fault=='missing_strap':proofs.pop()
    elif fault=='missing_external':proofs.pop(0)
    elif fault=='duplicate_strap':proofs.append(copy.deepcopy(proofs[1]))
    elif fault=='duplicate_external':proofs.append(copy.deepcopy(proofs[0]))
    elif fault=='strap_width':proofs[1]['width_nm']-=1
    elif fault=='strap_contact':proofs[1]['boundary_uuids']=[]
    elif fault=='strap_binding':proofs[1]['source_native_binding']='forged'
    elif fault=='external_context':proofs[0]['separately_owned_source_auxiliary_strap']['width_nm']-=1
    elif fault=='external_width':proofs[0]['width_nm']-=1
    elif fault=='strap_cut':retired.remove(proofs[1]['track_uuids'][0])
    elif fault=='external_cut':retired.remove(proofs[0]['track_uuids'][0])
    elif fault=='wrong_scope':proofs[1]['scope']='a_same_net_cut_allowlist'
    else:moved['moved_owner_footprint_uuids']=[force._uid(parent.FindFootprintByReference('unrelated_external_boundary'))]
    before=[row._source_binding(b) for b in (parent,child)]
    with pytest.raises(ValueError):priority.inspect(parent,child,moved,board_hint='opaque',
        source_measurement_leaves=proofs,retired_source_track_uuids=retired)
    assert before==[row._source_binding(b) for b in (parent,child)]


def test_the_rest_of_the_force_net_is_still_protected(tmp_path,monkeypatch):
    parent,child,moved,proofs,retired=pair(tmp_path,monkeypatch)
    for board in (parent,child):track(board,proofs[0]['net'],(30,20),(34,20),width=1.,layer=pcbnew.B_Cu)
    # The newly created actual force strip is NOT part of either Source
    # measurement obligation. Bind a separate source/candidate population.
    first=next(t for t in parent.GetTracks() if t.GetWidth()==1000000)
    last=next(t for t in child.GetTracks() if t.GetWidth()==1000000)
    last.m_Uuid.Clone(first.m_Uuid)
    moved['changes'].append(dict(uuid=force._uid(first)))
    fresh=leaf.plan_with_auxiliary_strap(parent,proofs[0]['pad_uuid'])
    result=priority.inspect(parent,child,moved,board_hint='opaque',
        source_measurement_leaves=list(fresh),retired_source_track_uuids=retired)
    assert not result['ok']
    assert force._uid(first) in result['moved_priority_source_conductor_uuids']
