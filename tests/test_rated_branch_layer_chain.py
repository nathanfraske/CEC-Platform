"""Real native cross-layer construction, with explicit test-only load catalogs."""
import math
from unittest import mock
import pcbnew,pytest
import wx
quiet=wx.LogNull()
import cec_rated_branch_layer_chain as worker
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
from test_rated_medium_supply_rebuild import fixture


def case(tmp_path,rotation=0,mirror=False,face=pcbnew.F_Cu):
    source,_,uid,net,catalog=fixture(tmp_path,rotation,mirror,face)
    contract=catalog['contracts'][net]
    contract.update(net=net,clearance_mm=.2)
    def point(p):
        x,y=p[0]-15,p[1]-15
        if mirror:x=-x
        a=math.radians(rotation)
        return [round((15+x*math.cos(a)-y*math.sin(a))*1e6),
                round((15+x*math.sin(a)+y*math.cos(a))*1e6)]
    other=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    stages=[dict(layer=pcbnew.LayerName(other),points_nm=[point((5,10)),point((7,10))]),
        dict(layer=pcbnew.LayerName(face),points_nm=[point((7,10)),point((10,10))])]
    return source,uid,net,catalog,stages


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_full_load_chain_derives_only_real_transitions_and_replays_saved_boundaries(tmp_path,rotation,mirror,face):
    source,uid,net,catalog,stages=case(tmp_path,rotation,mirror,face)
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        board,proposal=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,max_source_width_mm=1.,max_replacement_width_mm=1.)
        candidate=force._copy_family(source,tmp_path/'received-chain')
        field._save_field_snapshot(board,candidate)
        proof=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,max_source_width_mm=1.,max_replacement_width_mm=1.)
    assert proof['ok'] and proof['complete'],proof
    assert len(proposal['new_via_uuids'])==1
    assert proposal['derived_new_barrel_sites_nm']==[stages[0]['points_nm'][-1]]
    assert all(r['width_nm']==500000 for r in proposal['full_width_native_legs'])
    assert source.read_bytes()==saved
    assert not proposal['new_barrel_ampacity_credited'] and not proposal['branch_sharing_inferred']
    assert not proposal['routing_admitted'] and not proposal['release_authority']


@pytest.mark.parametrize('fault',['boolean_coordinate','duplicate_point','broken_portal','unknown_face',
    'plane_face','too_many_stages','wrong_end','default_scope','inner_width','source_group',
    'source_underwidth','no_domain_authority','extra_field','unbounded_width'])
def test_hints_are_not_a_source_owner_width_or_connection_waiver(tmp_path,fault):
    source,uid,net,catalog,stages=case(tmp_path)
    if fault=='boolean_coordinate':stages[0]['points_nm'][0][0]=True
    elif fault=='duplicate_point':stages[0]['points_nm'][1]=stages[0]['points_nm'][0]
    elif fault=='broken_portal':stages[1]['points_nm'][0][0]+=1
    elif fault=='unknown_face':stages[0]['layer']='not_copper'
    elif fault=='plane_face':
        stages[0]['layer']='In1.Cu';catalog['contracts'][net]['routing_layers'].append('In1.Cu')
        catalog['contracts'][net]['required_by_layer_mm']['In1.Cu']=.4773698
        b=pcbnew.LoadBoard(str(source));b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.In1_Cu);z.SetNetCode(b.GetNetcodeFromNetname('GND'))
        z.Outline().NewOutline()
        for at in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
        b.Add(z);field._save_field_snapshot(b,source)
    elif fault=='too_many_stages':stages*=5
    elif fault=='wrong_end':stages[-1]['points_nm'][-1][0]+=1
    elif fault=='inner_width':stages[0]['layer']='In2.Cu'
    elif fault in ('source_group','source_underwidth'):
        b=pcbnew.LoadBoard(str(source));edge=next(t for t in b.GetTracks() if force._uid(t)==uid)
        if fault=='source_group':
            g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(edge)
        else:edge.SetWidth(477369)
        field._save_field_snapshot(b,source)
    elif fault=='no_domain_authority':catalog['contracts']={}
    elif fault=='extra_field':stages[0]['permission']=True
    options=dict(max_source_width_mm=1.,max_replacement_width_mm=1.)
    if fault=='default_scope':options={}
    elif fault=='unbounded_width':options['max_replacement_width_mm']=6.
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,**options)
    assert source.read_bytes()==saved


def test_native_blocked_lease_logs_structured_failure_without_mutating_source(tmp_path):
    source,uid,net,catalog,stages=case(tmp_path);saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
         mock.patch.object(worker.fr,'_guarded_profiled_lastmile_legs',return_value=None):
        with pytest.raises(worker.Refused) as exc:
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
                max_source_width_mm=1.,max_replacement_width_mm=1.)
    assert exc.value.diagnostics['failed_stage']['width_nm']==500000
    assert not exc.value.diagnostics['source_mutated']
    assert not exc.value.diagnostics['retirement_authorized']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('fault', ['native','edge','current'])
def test_barrel_refusal_names_actual_site_and_failed_independent_gate(tmp_path,fault):
    source,uid,net,catalog,stages=case(tmp_path);saved=source.read_bytes()
    def native(*args,**kw):
        kw['report']['reason']='synthetic_native_obstacle'
        return fault!='native'
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
         mock.patch.object(worker.fr,'_via_spot_clear',side_effect=native), \
         mock.patch.object(worker.fr,'_edge_leg_clear',return_value=fault!='edge'), \
         mock.patch.object(worker.capture,'Guard',return_value=lambda *args:fault!='current'):
        with pytest.raises(worker.Refused) as exc:
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
                max_source_width_mm=1.,max_replacement_width_mm=1.)
    report=exc.value.diagnostics
    assert report['failed_barrel']['at_nm']==stages[0]['points_nm'][-1]
    assert report['failed_barrel']['native_all_layer_clear']==(fault!='native')
    assert report['failed_barrel']['board_edge_clear']==(fault!='edge')
    assert bool(report['failed_barrel']['source_current_refused_faces'])==(fault=='current')
    assert report['failed_barrel']['native_report']['reason']=='synthetic_native_obstacle'
    assert not report['source_mutated'] and not report['retirement_authorized']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('later_face',[pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.B_Cu])
def test_opt_in_failure_stack_reports_later_faces_without_changing_refusal(tmp_path,later_face):
    source,uid,net,catalog,stages=case(tmp_path)
    board=pcbnew.LoadBoard(str(source));foreign=pcbnew.NETINFO_ITEM(board,'unrelated_foreign');board.Add(foreign)
    actual=[]
    for layer in (pcbnew.F_Cu,later_face):
        track=pcbnew.PCB_TRACK(board);track.SetLayer(layer);track.SetNet(foreign)
        # Legal beside the .5-mm source branch, but within the new .8-mm
        # barrel's clearance. Do not create a foreign short in the fixture.
        track.SetWidth(200000);track.SetStart(pcbnew.VECTOR2I_MM(6,10.65))
        track.SetEnd(pcbnew.VECTOR2I_MM(8,10.65));board.Add(track);actual.append(force._uid(track))
    field._save_field_snapshot(board,source);saved=source.read_bytes()
    results=[]
    for enabled in (False,True):
        with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
            with pytest.raises(worker.Refused) as exc:
                worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
                    max_source_width_mm=1.,max_replacement_width_mm=1.,
                    all_layer_failure_diagnostics=enabled)
        results.append(exc.value.diagnostics['failed_barrel'])
    assert results[0]['native_report']==results[1]['native_report']
    assert results[0]['guarded_copper_stack'] is None
    stack=results[1]['guarded_copper_stack']
    assert stack['inventory_complete'] and not stack['native_guard_clear']
    assert {r['uuid'] for layer in stack['layer_rows'] for r in layer['blockers']}==set(actual)
    assert not stack['retirement_authorized'] and not stack['release_authority']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_all_layer_failure_report_cannot_be_implicitly_enabled(tmp_path,flag):
    source,uid,net,catalog,stages=case(tmp_path)
    with pytest.raises(ValueError,match='bounded_explicit_rated_layer_chain_required'):
        worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
            all_layer_failure_diagnostics=flag)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_native_envelope_preserves_full_source_faces_and_saved_receiving(tmp_path,rotation,mirror):
    source,uid,net,catalog,stages=case(tmp_path,rotation,mirror)
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        board,proposal=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,max_source_width_mm=1.,max_replacement_width_mm=1.,
            native_board_envelope=True)
        candidate=force._copy_family(source,tmp_path/'received-native-envelope')
        field._save_field_snapshot(board,candidate)
        proof=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,max_source_width_mm=1.,max_replacement_width_mm=1.)
    assert proof['ok'] and proof['complete'],proof
    assert proposal['native_board_envelope'] is True
    assert len(proposal['new_via_uuids'])==1
    assert all(row['width_nm']==500000 for row in proposal['full_width_native_legs'])
    assert not proposal['branch_sharing_inferred'] and source.read_bytes()==saved


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_native_envelope_flag_is_explicit_not_truthy(tmp_path,flag):
    source,uid,net,catalog,stages=case(tmp_path)
    with pytest.raises(ValueError,match='bounded_explicit_rated_layer_chain_required'):
        worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,native_board_envelope=flag)


@pytest.mark.parametrize('fault',['wrong_face','thin_width','barrel','unknown_operation'])
def test_native_envelope_result_cannot_add_unrequested_face_or_lower_width(tmp_path,fault):
    source,uid,net,catalog,stages=case(tmp_path); saved=source.read_bytes()
    layer=pcbnew.B_Cu
    operation=('trk',pcbnew.VECTOR2I(*stages[0]['points_nm'][0]),
        pcbnew.VECTOR2I(*stages[0]['points_nm'][1]),500000,layer)
    if fault=='wrong_face':operation=(*operation[:4],pcbnew.F_Cu)
    elif fault=='thin_width':operation=(*operation[:3],499999,layer)
    elif fault=='barrel':operation=('via',operation[1],.3,.8)
    elif fault=='unknown_operation':operation=('unknown',*operation[1:])
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
         mock.patch.object(worker.fr,'_multilayer_maze_lastmile_ops',return_value=[operation]):
        with pytest.raises(ValueError,match='native_chain_envelope_changed_face_width_or_barrels'):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
                max_source_width_mm=1.,max_replacement_width_mm=1.,native_board_envelope=True)
    assert source.read_bytes()==saved
