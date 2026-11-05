"""Real full-width metal, never a weaker contact witness or inferred current."""
import copy,json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import pcbnew
import pytest
import cec_orthogonal_contact_strengthening as contact
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import create_empty_board
from test_native_cut_contact_witness import track
from test_lastmile import _board


def operands(board,*,quarter=0,reflect=False,swapped=False,reversed=False,offset=(0,0),gap=499999,face=pcbnew.F_Cu):
    a=track(board,(-1000000,0),(1000000,0),500000)
    b=track(board,(0,gap),(0,2000000),500000)
    for item in(a,b):
        points=[]
        for point in(item.GetStart(),item.GetEnd()):
            x,y=tuple(point)
            if reflect:x=-x
            for _ in range(quarter):x,y=-y,x
            points.append(pcbnew.VECTOR2I(x+offset[0],y+offset[1]))
        if reversed:points.reverse()
        item.SetStart(points[0]);item.SetEnd(points[1]);item.SetLayer(face)
    return (b,a)if swapped else(a,b)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('reflect',[False,True])
@pytest.mark.parametrize('swapped',[False,True])
@pytest.mark.parametrize('reversed',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_positive_one_nm_sliver_produces_real_centreline_extension(quarter,reflect,swapped,reversed,face):
    board=create_empty_board();net=pcbnew.NETINFO_ITEM(board,'opaque_supply');board.Add(net)
    a,b=operands(board,quarter=quarter,reflect=reflect,swapped=swapped,reversed=reversed,
        offset=(-27123456,23765432),face=face)
    for item in(a,b):item.SetNet(net)
    before=[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())for t in(a,b)]
    q=contact._geometry(a,b,face)
    assert q['original_positive_overlap_nm']==1 and q['width_nm']==500000
    added=track(board,q['start_nm'],q['end_nm'],q['width_nm']);added.SetLayer(face);added.SetNet(net)
    # Both new endpoints belong to real original centreline material. There
    # is no requirement to invent an integer inside the original tiny lens.
    assert all(any(t.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*p),0)for t in(a,b))
        for p in(q['start_nm'],q['end_nm']))
    assert contact._already_supported(board,q)
    assert before==[(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())for t in(a,b)]


@pytest.mark.parametrize('gap',[500000,500001,800000,0,-500000])
def test_tangency_near_miss_inward_and_existing_crossing_do_not_gain_eligibility(gap):
    board=create_empty_board();net=pcbnew.NETINFO_ITEM(board,'opaque_supply');board.Add(net)
    pair=operands(board,gap=gap)
    for item in pair:item.SetNet(net)
    with pytest.raises(ValueError):contact._geometry(*pair,pcbnew.F_Cu)


@pytest.mark.parametrize('fault',['wrong_net','face','parallel','skew','zero','width','mask','projection_endpoint'])
def test_geometry_scope_never_authorizes_a_different_contact(fault):
    board=create_empty_board();net=pcbnew.NETINFO_ITEM(board,'opaque_supply');board.Add(net)
    a,b=operands(board)
    for item in(a,b):item.SetNet(net)
    if fault=='wrong_net':b.SetNetCode(0)
    elif fault=='face':b.SetLayer(pcbnew.B_Cu)
    elif fault=='parallel':b.SetEnd(pcbnew.VECTOR2I(1000000,499999))
    elif fault=='skew':b.SetEnd(pcbnew.VECTOR2I(1,2000000))
    elif fault=='zero':b.SetEnd(b.GetStart())
    elif fault=='width':b.SetWidth(499999)
    elif fault=='mask':b.SetHasSolderMask(True)
    else:a.SetStart(pcbnew.VECTOR2I(0,0))
    with pytest.raises(ValueError):contact._geometry(a,b,pcbnew.F_Cu)


def fixture(tmp_path,quarter=0,face=pcbnew.F_Cu):
    net='arbitrary_rated_supply';board=_board([],edge=(-10,-10,10,10));board.SetCopperLayerCount(6)
    ni=pcbnew.NETINFO_ITEM(board,net);board.Add(ni)
    pair=operands(board,quarter=quarter,face=face)
    for item in pair:item.SetNet(ni)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    contract=dict(net=net,required_by_layer_mm={'F.Cu':.5,'B.Cu':.5},routing_layers=['F.Cu','B.Cu'],
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    # Synthetic explicit catalog authority only. No hardware current inferred.
    domains={net:dict(net=net,complete=True,source_refs=['supply'],sink_refs=['sink'])}
    stack=ExitStack()
    stack.enter_context(patch.object(contact.full.topology,'board_current_domains',return_value=domains))
    stack.enter_context(patch.object(contact.full.topology,'route_width_contracts',return_value={net:contract}))
    return source,[force._uid(t)for t in pair],contract,domains,stack


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_public_json_saved_reconstruction_preserves_all_Source_and_current(tmp_path,quarter,face):
    source,ids,contract,domains,stack=fixture(tmp_path,quarter,face)
    with stack:
        before=source.read_bytes();q=json.loads(json.dumps(contact.plan(source,board_hint='synthetic',track_uuids=ids)))
        saved=contact.write_private(source,tmp_path/'private',q)
        proof=contact.receive(source,saved['board'],q)
        assert proof['ok']and proof['complete'],proof
        assert not proof['current_qualified']and not proof['release_authority']
        assert q['unchanged_current_contract']==contract and not q['current_sharing_inferred']
        assert source.read_bytes()==before and proof['original_contact_predicate_not_relaxed']
        with pytest.raises(ValueError,match='already_centerline_supported'):
            contact.plan(saved['board'],board_hint='synthetic',track_uuids=ids)


@pytest.mark.parametrize('fault',['start','width','model','Source','extra','original','layer','rule','proposal'])
def test_saved_or_proposal_tampering_never_receives_contact_repair(tmp_path,fault):
    source,ids,contract,domains,stack=fixture(tmp_path)
    with stack:
        q=contact.plan(source,board_hint='synthetic',track_uuids=ids)
        child=contact.write_private(source,tmp_path/'private',q)['board'];board=pcbnew.LoadBoard(child)
        added=next(t for t in board.GetTracks()if force._uid(t)==q['bridge_uuid'])
        if fault=='start':added.SetStart(added.GetStart()+pcbnew.VECTOR2I(1,0))
        elif fault=='width':added.SetWidth(499999)
        elif fault=='model':contract['required_by_layer_mm']['F.Cu']=.6
        elif fault=='Source':source.write_bytes(source.read_bytes()+b'\n')
        elif fault=='extra':t=track(board,(4000000,4000000),(5000000,4000000),500000);t.SetNet(board.FindNet(q['geometry']['net']))
        elif fault=='original':next(t for t in board.GetTracks()if force._uid(t)in ids).SetLocked(True)
        elif fault=='layer':added.SetLayer(pcbnew.B_Cu)
        elif fault=='rule':Path(child).with_suffix('.kicad_dru').write_text('(version 1)\n')
        else:q['geometry']['original_positive_overlap_nm']=2
        field._save_field_snapshot(board,child)
        proof=contact.receive(source,child,q)
        assert not proof['ok']and proof['errors'],proof


@pytest.mark.parametrize('protected',['measurement','coupled','resistive','analog_pair','unresolved_monitor'])
def test_positive_protected_routing_roles_do_not_gain_supply_repair_authority(tmp_path,protected):
    source,ids,contract,domains,stack=fixture(tmp_path)
    with stack:
        board=pcbnew.LoadBoard(str(source));fp=pcbnew.FOOTPRINT(board);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet(contract['net']));fp.Add(pad)
        field._save_field_snapshot(board,source)
        with ExitStack()as roles:
            if protected=='measurement':roles.enter_context(patch.object(contact.roles,'footprint_contract',return_value={'pins':{'1':'measurement'}}))
            elif protected=='coupled':roles.enter_context(patch.object(contact.fr,'coupled_pair_nets',return_value={contract['net']}))
            elif protected=='resistive':roles.enter_context(patch.object(contact.roles,'resistive_sensing_endpoint_contract',return_value={'positive_test_role':True}))
            else:
                import cec_pair_semantics as semantics
                if protected=='analog_pair':roles.enter_context(patch.object(semantics,'analog_input_pairs',return_value=[{'p':contract['net'],'n':'other'}]))
                else:roles.enter_context(patch.object(semantics,'unresolved_current_monitor_nets',return_value={contract['net']}))
            with pytest.raises(ValueError,match='protected_measurement_or_coupled'):
                contact.plan(source,board_hint='synthetic',track_uuids=ids)


@pytest.mark.parametrize('name',['Kelvin','Sense','Differential','Analog','Clock','Highspeed','CustomSensitive'])
@pytest.mark.parametrize('composite',[False,True])
def test_opaque_positive_current_net_keeps_its_actual_protected_project_class(tmp_path,name,composite):
    source,ids,contract,domains,stack=fixture(tmp_path)
    with stack:
        settings=dict(classes=[dict(name='Default',track_width=.5),dict(name='Power',track_width=.5),
            dict(name=name,track_width=.5)],netclass_assignments={contract['net']:['Power',name]if composite else name})
        source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=settings)))
        before=source.read_bytes()
        with pytest.raises(ValueError,match='protected_measurement_or_coupled'):
            contact.plan(source,board_hint='synthetic',track_uuids=ids)
        assert source.read_bytes()==before


@pytest.mark.parametrize('target',['Source','candidate'])
def test_final_live_input_fence_refuses_mutation_after_real_material_receiving(tmp_path,target):
    source,ids,contract,domains,stack=fixture(tmp_path)
    with stack:
        q=contact.plan(source,board_hint='synthetic',track_uuids=ids)
        child=contact.write_private(source,tmp_path/'private',q)['board'];original=contact.additive.receive
        def changed(*args,**kwargs):
            proof=original(*args,**kwargs);assert proof['ok']and proof['complete']
            path=source if target=='Source'else Path(child)
            path.write_bytes(path.read_bytes()+b'\n')
            return proof
        with patch.object(contact.additive,'receive',side_effect=changed):
            proof=contact.receive(source,child,q)
        assert not proof['ok']and any('identity_changed'in e for e in proof['errors'])


def test_plan_final_Source_fence_includes_last_native_literal_identity_read(tmp_path):
    source,ids,contract,domains,stack=fixture(tmp_path)
    with stack:
        original=contact.additive._nodes
        def changed(path):
            actual=original(path);source.write_bytes(source.read_bytes()+b'\n');return actual
        with patch.object(contact.additive,'_nodes',side_effect=changed):
            with pytest.raises(ValueError,match='Source_identity_or_deadline_changed'):
                contact.plan(source,board_hint='synthetic',track_uuids=ids)


@pytest.mark.parametrize('value',[True,0,-1,float('nan'),float('inf'),10.,'9'])
def test_invalid_native_deadline_refuses_before_Source_IO(value):
    with pytest.raises(ValueError,match='bounded_contact_strengthening_deadline'):
        contact.plan('/missing/never-read.kicad_pcb',board_hint='synthetic',track_uuids=[],timeout_s=value)


@pytest.mark.parametrize('value',[True,0,-1,2000001,1.5,float('nan')])
def test_invalid_geometry_work_reach_refuses_before_native_operands(value):
    with pytest.raises(ValueError,match='bounded_integer_contact_strengthening_reach'):
        contact._geometry(None,None,pcbnew.F_Cu,maximum_reach_nm=value)
