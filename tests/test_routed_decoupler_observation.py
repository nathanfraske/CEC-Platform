"""Saved local PI observation cannot borrow hypothetical construction proofs."""
import ast
import copy
import math
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_prefreeze_local_pi as future
import cec_shared_pin_reference as shared
import cec_support_craft_gate as craft
import cec_synth_pipeline as synth
from test_decoupler_cell import DecouplerCellTests


def fixture(tmp_path, *, turn=0, back=False, prefix='A'):
    board, _ = DecouplerCellTests()._board()
    owner = board.FindFootprintByReference('U1')
    cap = board.FindFootprintByReference('C1')
    owner.SetReference(prefix+'_OWNER'); cap.SetReference(prefix+'_HF')
    owner.SetValue('NATIVE_EXPLICIT_RETURN_CONTRACT'); cap.SetValue('100nF')
    face = pcbnew.B_Cu if back else pcbnew.F_Cu
    for fp in (owner, cap):
        fp.SetLayer(face)
        for pad in fp.Pads():
            at=pad.GetPosition(); x,y=at.x-15000000,at.y-15000000
            for _ in range(turn): x,y=-y,x
            pad.SetPosition(pcbnew.VECTOR2I(15000000+x,15000000+y))
            pad.SetOrientationDegrees(turn*90)
            mask=pcbnew.LSET(); mask.AddLayer(face); pad.SetLayerSet(mask)
        pads=list(fp.Pads()); xs=[p.GetPosition().x for p in pads];ys=[p.GetPosition().y for p in pads]
        court=pcbnew.PCB_SHAPE(fp);court.SetShape(pcbnew.SHAPE_T_RECT)
        court.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
        court.SetStart(pcbnew.VECTOR2I(min(xs)-500000,min(ys)-500000))
        court.SetEnd(pcbnew.VECTOR2I(max(xs)+500000,max(ys)+500000));court.SetWidth(50000);fp.Add(court)
    for pad in (owner.FindPadByNumber('1'),cap.FindPadByNumber('2')):
        via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(pad.GetPosition())
        via.SetNet(pad.GetNet());via.SetWidth(350000);via.SetDrill(250000);board.Add(via)
    for left,right,layer in ((owner.FindPadByNumber('2'),cap.FindPadByNumber('1'),face),
            (owner.FindPadByNumber('1'),cap.FindPadByNumber('2'),pcbnew.F_Cu if back else pcbnew.B_Cu)):
        item=pcbnew.PCB_TRACK(board);item.SetNet(left.GetNet());item.SetWidth(250000)
        item.SetLayer(layer);item.SetStart(left.GetPosition());item.SetEnd(right.GetPosition());board.Add(item)
    path=tmp_path/'saved.kicad_pcb';field._save_field_snapshot(board,path)
    return path, owner.GetReference(), cap.GetReference()


def assignment_for(owner_ref,cap_ref):
    def assignment(board,**_kwargs):
        owner=board.FindFootprintByReference(owner_ref)
        cap=board.FindFootprintByReference(cap_ref)
        pad=owner.FindPadByNumber('2');other=cap.FindPadByNumber('1')
        req=dict(id='actual-saved-explicit-cell',ref=owner_ref,pin='2',pad=pad,
            rail=pad.GetNetname(),return_rail='GND',kind='100n',max_mm=3.5)
        return dict(requirements=[req],missing=[],assigned={req['id']:dict(requirement=req,
            cap_ref=cap_ref,distance_mm=math.dist(tuple(pad.GetPosition()),tuple(other.GetPosition()))/1e6)})
    return assignment


@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('prefix',['RENAMED','OTHER'])
def test_saved_routed_observer_never_replays_or_constructs_and_reproves_both_vips(tmp_path,turn,back,prefix):
    path,owner,cap=fixture(tmp_path,turn=turn,back=back,prefix=prefix)
    raw=path.read_bytes()
    with mock.patch.object(cells.cec_constraints,'_device_bypass_assignment',side_effect=assignment_for(owner,cap)), \
            mock.patch.object(future,'replay_for_measurement',side_effect=AssertionError('future replay is not saved copper')), \
            mock.patch.object(cells,'audit_pre_route_cells_board',side_effect=AssertionError('no pre-route search')), \
            mock.patch.object(cells,'synthesize_board',side_effect=AssertionError('no construction')):
        report=synth._oracle_decoupler_adjacency(str(path),SimpleNamespace(params={'pourfirst_state':'must-not-be-read'}),phase='routed')
    assert report['saved_board_sha256']==force._hash(path) and report['observation_phase']=='routed'
    assert not report['hypothetical_cell_construction_used'] and path.read_bytes()==raw
    assert report['supply_access']['requirements']==1
    row=report['supply_access']['cells'][0]
    assert row['status']=='owned' and row['actual_saved_copper_only']
    for key in ('ground_return','owner_ground_return'):
        proof=row[key]
        assert proof['status']=='covered' and proof['observed_saved_copper']
        assert cells.qualified_via_in_pad_return(proof),proof
        assert proof['all_enabled_face_widths_uniform']and proof['all_actual_pad_face_overlaps_requalified']
        assert proof['topology_evidence']['source']=='native_reused_return_land'
    assert report['details'][0]['pin_proximity_mode']=='dual_via_in_pad_complete_loop'
    assert report['details'][0]['return_gate_mode']=='absolute_ground_distance'


@pytest.mark.parametrize('fault',['no_profile','partial_land','foreign_face','blind','through_pad',
    'nonuniform','custom_stack_uniform','missing_uuid','duplicate_uuid','retired_barrel','custom_land','native_shape_unknown'])
def test_no_saved_native_topology_fact_is_inferred_from_proximity_or_certificate_shape(tmp_path,fault):
    path,oref,cref=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(path));pad=board.FindFootprintByReference(cref).FindPadByNumber('2')
    via=next(v for v in board.GetTracks()if v.GetClass()=='PCB_VIA'and v.GetPosition()==pad.GetPosition())
    if fault=='no_profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_4l_standard';board.SetProperties(props)
    elif fault=='partial_land':via.SetPosition(via.GetPosition()+pcbnew.VECTOR2I(300000,0))
    elif fault=='foreign_face':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('FOREIGN');board.Add(fp)
        foreign=pcbnew.PAD(fp);foreign.SetAttribute(pcbnew.PAD_ATTRIB_SMD);foreign.SetShape(pcbnew.PAD_SHAPE_RECT)
        foreign.SetSize(pcbnew.VECTOR2I(800000,800000));foreign.SetPosition(via.GetPosition())
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);foreign.SetLayerSet(mask)
        foreign.SetNet(board.FindNet('+3V3'));fp.Add(foreign)
    elif fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    elif fault=='through_pad':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='nonuniform':
        via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
        via.SetWidth(pcbnew.In1_Cu,500000)
        assert len({via.GetWidth(face)for face in board.GetEnabledLayers().CuStack()})>1
    elif fault=='custom_stack_uniform':via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
    elif fault=='missing_uuid':via.m_Uuid.Clone(pcbnew.KIID('00000000-0000-0000-0000-000000000000'))
    elif fault=='duplicate_uuid':
        duplicate=pcbnew.PCB_VIA(board);duplicate.m_Uuid.Clone(via.m_Uuid)
        duplicate.SetPosition(pcbnew.VECTOR2I_MM(25,25));board.Add(duplicate)
    elif fault=='retired_barrel':
        from cec_native_items import discard_items
        absent=pcbnew.PCB_VIA(board);absent.m_Uuid.Clone(via.m_Uuid)
        absent.SetPosition(via.GetPosition());absent.SetNet(via.GetNet())
        discard_items(board,[via])
        via=absent  # Never dereference a discarded native proxy.
    elif fault=='custom_land':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    context=(mock.patch.object(cells.cec_fab_profile,'via_at_pad_conflicts',side_effect=RuntimeError('native unavailable'))
        if fault=='native_shape_unknown'else mock.patch.object(cells,'_report_only',wraps=cells._report_only))
    with context: proof=cells._routed_return_evidence(board,pad,(0.,via))
    assert proof['status']=='covered' and not cells.qualified_via_in_pad_return(proof),proof
    assert proof['topology_qualified']is False and proof['topology_observation_refusal']
    gate=synth._decoupler_proximity_gate('GND',2.635,1.577,
        {'best_loop':{'supply_mm':2.35,'loop_proxy_mm':4.2}},
        dict(ground_return=proof,owner_ground_return=proof))
    assert gate['bad']and gate['mode']=='isolated_tangent_supply'


@pytest.mark.parametrize('fault',['missing','duplicate','owner','pin','cap','requirement','status'])
def test_routed_assignment_access_must_be_complete_unique_and_exact(tmp_path,fault):
    path,owner,cap=fixture(tmp_path)
    real=cells.audit_board
    def corrupted(board,**kw):
        result=real(board,**kw);row=result['cells'][0]
        if fault=='missing':result['cells']=[]
        elif fault=='duplicate':result['cells'].append(copy.deepcopy(row))
        else:row[{'requirement':'source_requirement_id'}.get(fault,fault)]='wrong'
        return result
    with mock.patch.object(cells.cec_constraints,'_device_bypass_assignment',side_effect=assignment_for(owner,cap)), \
            mock.patch.object(cells,'audit_board',side_effect=corrupted):
        with pytest.raises(ValueError,match='complete_unique_actual_saved_cell_access_required'):
            synth._oracle_decoupler_adjacency(str(path),phase='routed')


def test_routed_input_change_is_not_a_fresh_measurement(tmp_path):
    path,owner,cap=fixture(tmp_path);real=cells.audit_board
    def changed(board,**kw):
        result=real(board,**kw)
        # Deliberate source tamper is a test fault, not an implementation edit.
        with path.open('a')as handle:handle.write('\n; concurrent source change\n')
        return result
    with mock.patch.object(cells.cec_constraints,'_device_bypass_assignment',side_effect=assignment_for(owner,cap)), \
            mock.patch.object(cells,'audit_board',side_effect=changed):
        with pytest.raises(ValueError,match='saved_routed_decoupler_input_changed'):
            synth._oracle_decoupler_adjacency(str(path),phase='routed')


@pytest.mark.parametrize('phase',[None,True,'unknown','geometry'])
def test_unknown_observation_phase_is_not_a_placement_or_routed_pass(phase):
    with pytest.raises(ValueError,match='explicit_decoupler_adjacency_phase_required'):
        synth._oracle_decoupler_adjacency('not-opened',phase=phase)


def test_final_pipeline_explicitly_selects_saved_routed_observation():
    tree=ast.parse(Path(synth.__file__).read_text())
    oracle=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='route_oracle_grade')
    calls=[n for n in ast.walk(oracle)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)
        and n.func.id=='_oracle_decoupler_adjacency']
    assert len(calls)==1 and any(k.arg=='phase'and isinstance(k.value,ast.Constant)
        and k.value.value=='routed'for k in calls[0].keywords)


def test_default_placement_still_uses_its_original_replay_and_collective_preflight(tmp_path):
    path,owner,cap=fixture(tmp_path)
    with mock.patch.object(cells.cec_constraints,'_device_bypass_assignment',side_effect=assignment_for(owner,cap)), \
            mock.patch.object(future,'replay_for_measurement',return_value={'applicable':False})as replay, \
            mock.patch.object(cells,'audit_pre_route_cells_board',return_value={'cells':[]})as preflight, \
            mock.patch.object(cells,'audit_board',side_effect=AssertionError('not the saved observer')):
        implicit=synth._oracle_decoupler_adjacency(str(path))
        explicit=synth._oracle_decoupler_adjacency(str(path),phase='placement')
    assert replay.call_count==preflight.call_count==2 and implicit==explicit
    assert 'observation_phase'not in implicit


@pytest.mark.parametrize('back',[False,True])
def test_local_dogbone_remains_a_real_return_but_is_never_a_vip(tmp_path,back):
    path,owner,cap=fixture(tmp_path,back=back)
    board=pcbnew.LoadBoard(str(path));pad=board.FindFootprintByReference(cap).FindPadByNumber('2')
    via=next(v for v in board.GetTracks()if v.GetClass()=='PCB_VIA'and v.GetPosition()==pad.GetPosition())
    via.SetPosition(via.GetPosition()+pcbnew.VECTOR2I(800000,0))
    t=pcbnew.PCB_TRACK(board);t.SetNet(pad.GetNet());t.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
    t.SetWidth(250000);t.SetStart(pad.GetPosition());t.SetEnd(via.GetPosition());board.Add(t)
    found=cells._existing_return(board,pad,1.5,allow_native_track_body=True)
    assert found is not None
    proof=cells._routed_return_evidence(board,pad,found)
    assert proof['status']=='covered'and not cells.qualified_via_in_pad_return(proof)


@pytest.mark.parametrize('back',[False,True])
def test_native_uniformity_is_checked_after_a_real_saved_padstack_roundtrip(tmp_path,back):
    path,owner,cap=fixture(tmp_path,back=back)
    board=pcbnew.LoadBoard(str(path));pad=board.FindFootprintByReference(cap).FindPadByNumber('2')
    via=next(v for v in board.GetTracks()if v.GetClass()=='PCB_VIA'and v.GetPosition()==pad.GetPosition())
    uid=str(via.m_Uuid.AsString());via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
    via.SetWidth(pcbnew.In1_Cu,500000);field._save_field_snapshot(board,path)
    saved=pcbnew.LoadBoard(str(path));pad=saved.FindFootprintByReference(cap).FindPadByNumber('2')
    via=next(v for v in saved.GetTracks()if str(v.m_Uuid.AsString())==uid)
    assert len({via.GetWidth(face)for face in saved.GetEnabledLayers().CuStack()})>1
    assert not cells.qualified_via_in_pad_return(cells._routed_return_evidence(saved,pad,(0.,via)))


def test_qualified_vips_do_not_relax_the_absolute_ground_pin_distance(tmp_path):
    path,owner,cap=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(path));pad=board.FindFootprintByReference(owner).FindPadByNumber('1')
    old=pad.GetPosition();moved=old+pcbnew.VECTOR2I(0,6000000)
    via=next(v for v in board.GetTracks()if v.GetClass()=='PCB_VIA'and v.GetPosition()==old)
    for t in board.GetTracks():
        if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='GND':
            if t.GetStart()==old:t.SetStart(moved)
            if t.GetEnd()==old:t.SetEnd(moved)
    pad.SetPosition(moved);via.SetPosition(moved);field._save_field_snapshot(board,path)
    with mock.patch.object(cells.cec_constraints,'_device_bypass_assignment',side_effect=assignment_for(owner,cap)):
        report=synth._oracle_decoupler_adjacency(str(path),phase='routed')
    row=report['supply_access']['cells'][0]
    assert all(cells.qualified_via_in_pad_return(row[key])for key in('ground_return','owner_ground_return'))
    assert not report['ok']and 'cap-to-owner GND gap'in row['reason']
    detail=report['details'][0]
    assert detail['return_gate_mode']=='absolute_ground_distance'and detail['return_limit_mm']==2.5
    assert detail['ground_distance_mm']>2.5


def test_explicit_rail_return_keeps_its_loop_policy_without_ground_vip_facts(tmp_path):
    path,owner,cap=fixture(tmp_path);board=pcbnew.LoadBoard(str(path))
    rail=pcbnew.NETINFO_ITEM(board,'/RETURN_NOT_GROUND');board.Add(rail)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname()=='GND':p.SetNet(rail)
    for item in board.GetTracks():
        if item.GetNetname()=='GND':item.SetNet(rail)
    field._save_field_snapshot(board,path)
    original=assignment_for(owner,cap)
    def assignment(actual,**kw):
        data=original(actual,**kw);req=data['requirements'][0]
        req.update(return_rail='/RETURN_NOT_GROUND',return_pin='1',
            return_pad=actual.FindFootprintByReference(owner).FindPadByNumber('1'))
        return data
    with mock.patch.object(cells.cec_constraints,'_device_bypass_assignment',side_effect=assignment):
        report=synth._oracle_decoupler_adjacency(str(path),phase='routed')
    row=report['supply_access']['cells'][0]
    assert row['return_rail']=='/RETURN_NOT_GROUND'and row['ground_return']is None and row['owner_ground_return']is None
    assert report['details'][0]['return_gate_mode']=='rail_to_rail_tangent_loop'


@pytest.mark.parametrize('flag',[None,0,'yes'])
def test_native_topology_opt_in_must_be_explicit_boolean(flag):
    with pytest.raises(ValueError,match='explicit_saved_return_topology_observation_required'):
        cells.audit_board(None,include_return_topology=flag)


def test_all_face_foreign_overlap_is_not_excused_by_a_partial_legacy_probe(tmp_path):
    path,owner,cap=fixture(tmp_path);board=pcbnew.LoadBoard(str(path))
    pad=board.FindFootprintByReference(cap).FindPadByNumber('2')
    via=next(v for v in board.GetTracks()if v.GetClass()=='PCB_VIA'and v.GetPosition()==pad.GetPosition())
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('BACK_FACE_FOREIGN');board.Add(fp)
    foreign=pcbnew.PAD(fp);foreign.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    foreign.SetShape(pcbnew.PAD_SHAPE_RECT);foreign.SetSize(pcbnew.VECTOR2I(800000,800000))
    foreign.SetPosition(via.GetPosition());foreign.SetNet(board.FindNet('+3V3'))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);foreign.SetLayerSet(layers);fp.Add(foreign)
    with mock.patch.object(cells.cec_fab_profile,'via_at_pad_conflicts',return_value=(None,[])):
        proof=cells._routed_return_evidence(board,pad,(0.,via))
    assert not cells.qualified_via_in_pad_return(proof)
    assert 'all_face_pad_process_conflict'in proof['topology_observation_refusal']
