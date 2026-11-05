"""Complete source chain proposals use native boundaries, never design aliases."""
import math
from unittest import mock
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rated_branch_repair as rated
import cec_rated_source_chain_scope as worker
from test_field_proposals import track
from test_lastmile import _board


def case(tmp_path,rotation=0,mirror=False,face=pcbnew.F_Cu):
    net='/arbitrary/%s/%s/%s'%(rotation,mirror,face)
    def xy(p):
        x,y=p[0]-15,p[1]-15
        if mirror:x=-x
        a=math.radians(rotation)
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    b=_board([(*xy(p),net) for p in ((5,10),(17,10))],edge=(0,0,30,30))
    b.SetCopperLayerCount(6)
    for f in b.GetFootprints():
        p=next(iter(f.Pads()));ls=pcbnew.LSET();ls.AddLayer(face);p.SetLayerSet(ls);p.SetNumber('1')
    edges=[track(b,net,xy((5+i,10)),xy((6+i,10)),layer=face,width=.5) for i in range(12)]
    catalog=dict(contracts={net:dict(net=net,current_authority=dict(amps=3.,geometry_margin=1.25,
        margin_included=False,source='explicit_synthetic_catalog'),
        required_by_layer_mm={'F.Cu':.4773698,'B.Cu':.4773698,'In2.Cu':5.719034},
        routing_layers=['F.Cu','B.Cu','In2.Cu'])})
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return b,source,edges,net,catalog,xy


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_degree_two_fragmentation_reaches_actual_native_terminals(tmp_path,rotation,mirror,face):
    b,source,edges,net,catalog,xy=case(tmp_path,rotation,mirror,face)
    old=source.read_bytes();before=field._field_snapshot_inventory(b)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=worker.propose(b,source,board_hint='synthetic',seed_track_uuid=force._uid(edges[5]),
            max_source_width_mm=.5,max_retired_tracks=32)
    assert proof['retired_track_uuids']==sorted(force._uid(t) for t in edges)
    stops=proof['native_extension_stops']
    assert {tuple(s['at_nm']) for s in stops}=={tuple(pcbnew.VECTOR2I_MM(*xy(p))) for p in ((5,10),(17,10))}
    assert all(s['reason']=='retained_native_contact_or_width_boundary' for s in stops)
    assert proof['source_plan']['contracts']==catalog['contracts']
    assert not proof['automatic_retirement_authorized'] and not proof['routing_admitted']
    assert not proof['release_authority'] and not proof['source_current_reduced']
    assert before==field._field_snapshot_inventory(b) and old==source.read_bytes()


@pytest.mark.parametrize('boundary',['via','tee','width','group','interior_contact'])
def test_native_departures_stop_at_retained_barrels_tees_and_other_owners(tmp_path,boundary):
    b,source,edges,net,catalog,xy=case(tmp_path)
    if boundary=='via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy((12,10))))
        v.SetWidth(1200000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(b.GetNetcodeFromNetname(net));b.Add(v)
    elif boundary=='tee':track(b,net,xy((12,10)),xy((12,13)),width=.5)
    elif boundary=='width':edges[7].SetWidth(600000)
    elif boundary=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(edges[7])
    else:track(b,net,xy((11.75,10)),xy((11.75,13)),width=.5)
    field._save_field_snapshot(b,source);before=field._field_snapshot_inventory(b)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=worker.propose(b,source,board_hint='synthetic',seed_track_uuid=force._uid(edges[3]),
            max_source_width_mm=.5,max_retired_tracks=32)
    assert force._uid(edges[-1]) not in proof['retired_track_uuids']
    assert proof['interior_contacts_owned_by_independent_receiving']
    assert len(proof['retired_track_uuids'])<12 and before==field._field_snapshot_inventory(b)


def test_a_work_bound_never_returns_a_truncated_scope_as_complete(tmp_path):
    b,source,edges,net,catalog,_=case(tmp_path);before=field._field_snapshot_inventory(b)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError,match='incomplete_at_explicit_work_bound'):
            worker.propose(b,source,board_hint='synthetic',seed_track_uuid=force._uid(edges[5]),max_source_width_mm=.5)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['untypeable','underwidth','grouped_seed','stale_seed','boolean_bound','unbounded_timeout'])
def test_source_roles_floors_and_finite_work_scope_are_independent_gates(tmp_path,fault):
    b,source,edges,net,catalog,_=case(tmp_path)
    if fault=='untypeable':catalog['contracts']={}
    elif fault=='underwidth':edges[5].SetWidth(477369)
    elif fault=='grouped_seed':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(edges[5])
    field._save_field_snapshot(b,source);before=field._field_snapshot_inventory(b)
    args=dict(seed_track_uuid=force._uid(edges[5]),max_source_width_mm=.5,max_retired_tracks=32)
    if fault=='stale_seed':args['seed_track_uuid']='not_a_native_uuid'
    elif fault=='boolean_bound':args['max_retired_tracks']=True
    elif fault=='unbounded_timeout':args['timeout_s']=10.01
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):worker.propose(b,source,board_hint='synthetic',**args)
    assert before==field._field_snapshot_inventory(b)


def test_changed_catalog_cannot_retype_the_walk_under_a_smaller_load(tmp_path):
    import copy
    b,source,edges,net,catalog,_=case(tmp_path);later=copy.deepcopy(catalog)
    later['contracts'][net]['current_authority']['amps']=2.5
    before=field._field_snapshot_inventory(b)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',side_effect=[catalog,later]):
        with pytest.raises(ValueError,match='source_or_load_contract_changed'):
            worker.propose(b,source,board_hint='synthetic',seed_track_uuid=force._uid(edges[5]),
                max_source_width_mm=.5,max_retired_tracks=32)
    assert before==field._field_snapshot_inventory(b)
