"""Actual saved copper-equivalent ports, unrelated frames/nets and hostile deltas."""
import copy
import math
import pcbnew
import pytest
import cec_native_track_partition as op
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,net='GND'):
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return (round(x*1e6),round(y*1e6))
    b=_board([],edge=(0,0,20,20));b.SetCopperLayerCount(6)
    if not b.FindNet(net):b.Add(pcbnew.NETINFO_ITEM(b,net))
    def edge(a,z):
        t=track(b,net,[q/1e6 for q in point(*a)],[q/1e6 for q in point(*z)],width=.2,layer=layer)
        t.SetLocked(True);return force._uid(t)
    main=edge((5,8),(15,8));peer=edge((10,5),(10,12));tee=edge((7,8),(7,6))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    requests=[dict(track_uuid=main,peer_uuid=peer,point_nm=list(point(10,8)),locked_source_requested=True),
        dict(track_uuid=main,peer_uuid=tee,point_nm=list(point(7,8)),locked_source_requested=True)]
    return b,source,requests


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('net',['GND','/ARBITRARY_RENAMED_POWER'])
def test_saved_partition_preserves_complete_capsules_process_and_connectivity(tmp_path,quarter,mirror,layer,net):
    b,source,requests=fixture(tmp_path,quarter,mirror,layer,net);before=source.read_bytes()
    q=op.plan(b,requests,source_path=source,board_hint='synthetic')
    delta=op.materialize(b,q,source_path=source,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=op.receive(source,child,requests,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert len(delta['retired_track_uuids'])==1 and len(delta['added_native_uuids'])==3
    assert r['actual_copper_geometry_unchanged'] and not r['release_authority'] and not r['current_qualified']
    row=q['rows'][0];parts=row['fragments']
    assert math.isclose(sum(math.dist(t['start_nm'],t['end_nm']) for t in parts),10000000)
    assert all(a['end_nm']==z['start_nm'] for a,z in zip(parts,parts[1:]))
    assert all(t.IsLocked() and t.GetWidth()==200000 and t.GetLayer()==layer for t in b.GetTracks())
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['no_lock','duplicate','endpoint','near_endpoint','fake_point','boolean_point',
    'nonintegral_cross','foreign_net','other_face','track_group','peer_group','mask','peer_mask',
    'noncanonical','zero_peer','too_long','no_net','missing_peer','same_identity','wrong_keys',
    'timeout','boolean_timeout','unloaded_source','overflow','zero_width','noncopper_layer'])
def test_partition_is_not_contact_or_cut_authority(tmp_path,fault):
    b,source,requests=fixture(tmp_path);requests=copy.deepcopy(requests[:1]);r=requests[0]
    live={force._uid(t):t for t in b.GetTracks()};t,p=live[r['track_uuid']],live[r['peer_uuid']]
    timeout=10.
    if fault=='no_lock':r['locked_source_requested']=False
    elif fault=='duplicate':requests.append(copy.deepcopy(r))
    elif fault=='endpoint':r['point_nm']=list(t.GetStart())
    elif fault=='near_endpoint':p.SetStart(t.GetStart()+pcbnew.VECTOR2I(1,0));r['point_nm']=list(p.GetStart())
    elif fault=='fake_point':r['point_nm'][0]+=1
    elif fault=='boolean_point':r['point_nm'][0]=True
    elif fault=='nonintegral_cross':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,1))
    elif fault=='foreign_net':
        b.Add(pcbnew.NETINFO_ITEM(b,'FOREIGN'));p.SetNet(b.FindNet('FOREIGN'))
    elif fault=='other_face':p.SetLayer(pcbnew.B_Cu)
    elif fault in ('track_group','peer_group'):
        g=pcbnew.PCB_GROUP(b);g.SetName('UNRELATED_OWNER');b.Add(g);g.AddItem(t if fault=='track_group' else p)
    elif fault=='mask':t.SetHasSolderMask(True)
    elif fault=='peer_mask':p.SetHasSolderMask(True)
    elif fault=='noncanonical':p.SetEnd(p.GetEnd()+pcbnew.VECTOR2I(5,0))
    elif fault=='zero_peer':p.SetEnd(p.GetStart())
    elif fault=='too_long':t.SetEnd(pcbnew.VECTOR2I_MM(45,8))
    elif fault=='no_net':t.SetNetCode(0);p.SetNetCode(0)
    elif fault=='missing_peer':r['peer_uuid']='missing'
    elif fault=='same_identity':r['peer_uuid']=r['track_uuid']
    elif fault=='wrong_keys':r['waive_contact']=True
    elif fault=='timeout':timeout=0
    elif fault=='boolean_timeout':timeout=True
    elif fault=='unloaded_source':b.SetFileName('other.kicad_pcb')
    elif fault=='overflow':r['point_nm'][0]=2000000001
    elif fault=='zero_width':t.SetWidth(0)
    elif fault=='noncopper_layer':t.SetLayer(pcbnew.F_SilkS);p.SetLayer(pcbnew.F_SilkS)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,requests,source_path=source,board_hint='synthetic',timeout_s=timeout)
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['width','face','unlock','endpoint','missing_fragment','extra_track',
    'peer_move','new_barrel','changed_request','unchanged_child','forged_plan','zone','source_props'])
def test_independent_saved_replay_refuses_any_unowned_or_material_change(tmp_path,fault):
    b,source,requests=fixture(tmp_path);q=op.plan(b,requests,source_path=source,board_hint='synthetic')
    if fault=='forged_plan':
        q=copy.deepcopy(q);q['rows'][0]['fragments'][0]['end_nm'][0]+=1
        with pytest.raises(ValueError):op.materialize(b,q,source_path=source,board_hint='synthetic')
        return
    delta=op.materialize(b,q,source_path=source,board_hint='synthetic')
    t=next(t for t in b.GetTracks() if force._uid(t) in delta['added_native_uuids'])
    if fault=='width':t.SetWidth(199999)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='unlock':t.SetLocked(False)
    elif fault=='endpoint':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='missing_fragment':b.Remove(t)
    elif fault=='extra_track':track(b,'GND',(1,1),(1,2))
    elif fault=='peer_move':next(t for t in b.GetTracks() if force._uid(t)==requests[0]['peer_uuid']).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='new_barrel':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(10,8))
        v.SetWidth(300000);v.SetDrill(200000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='changed_request':requests[0]['point_nm'][0]+=1
    elif fault=='zone':
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(pcbnew.F_Cu)
        z.SetLocalClearance(200000);z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(2,1),(2,2),(1,2)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    elif fault=='source_props':
        props=b.GetProperties();props['UNOWNED_CHANGE']='yes';b.SetProperties(props)
    child=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(b,child)
    r=op.receive(source,source if fault=='unchanged_child' else child,requests,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority']


def test_collinear_peer_endpoints_are_actual_bounded_contacts(tmp_path):
    b,source,requests=fixture(tmp_path);r=requests[0];live={force._uid(t):t for t in b.GetTracks()}
    live[r['peer_uuid']].SetStart(pcbnew.VECTOR2I_MM(10,8))
    live[r['peer_uuid']].SetEnd(pcbnew.VECTOR2I_MM(12,8))
    q=op.plan(b,[r],source_path=source,board_hint='synthetic')
    assert len(q['rows'][0]['fragments'])==2


def test_exact_nonintegral_crossing_does_not_snap_to_a_native_port():
    assert not op._contact((0,0),(10,10),(0,5),(10,5))==[]
    assert op._contact((0,0),(9,9),(0,5),(9,-4))==[]
