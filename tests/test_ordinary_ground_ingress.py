"""Native negotiated ingress: two real ordinary owners, then mandatory GND."""
import copy
import json
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as ground
import cec_ordinary_ground_ingress as op
import cec_ordinary_route_receiving as ordinary
from test_ground_access_existing_pad_rule import fixture as base
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,peer_near=True):
    source,pad_uuid=base(tmp_path,quarter,mirror,layer);b=pcbnew.LoadBoard(str(source))
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    for net in ('lane_one','lane_two'):b.Add(pcbnew.NETINFO_ITEM(b,net))
    face=pcbnew.In2_Cu;selected=[]
    for net,x,lo,hi,locked in [('lane_one',9.7,2,14,True),('lane_two',8.7 if peer_near else 5.,1,19,False)]:
        a,z=point(x,lo),point(x,hi)
        t=track(b,net,[v/1e6 for v in a],[v/1e6 for v in z],layer=face,width=.2)
        t.SetLocked(locked);selected.append(force._uid(t))
        for index,at in enumerate((a,z)):
            fp=pcbnew.FOOTPRINT(b);fp.SetReference('UNRELATED_ENDPOINT_'+net+'_'+str(index));b.Add(fp)
            p=pcbnew.PAD(fp);p.SetNumber('endpoint');p.SetNet(b.FindNet(net));p.SetPosition(at)
            p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
            v=pcbnew.PCB_VIA(b);v.SetPosition(at);v.SetNet(p.GetNet());v.SetWidth(600000);v.SetDrill(300000)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v)
    # A real physical optical cut, not a plotting mask or artificial copper.
    vertices=[(10.3,6),(13,6),(13,10),(10.3,10),(10.3,6)]
    for a,z in zip(vertices,vertices[1:]):
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(point(*a));e.SetEnd(point(*z));b.Add(e)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    assert {'lane_one','lane_two'}<=ordinary.eligible_nets(b,source,'synthetic')
    args=dict(board_hint='synthetic',pad_uuid=pad_uuid,allow_locked_source=True,
        peer_track_uuid=selected[1] if peer_near else None)
    return source,args,selected


def saved(tmp_path,**options):
    source,args,ids=fixture(tmp_path,**options);q=json.loads(json.dumps(op.plan(source,**args)))
    b=op.construct(q);additive._ground_refill(b)
    middle=force._copy_family(source,tmp_path/'middle');field._save_field_snapshot(b,middle)
    g=ground.plan(middle,board_hint='synthetic',pad_uuid=args['pad_uuid'],use_existing_local_pad_rule=True)
    final=Path(ground.write_private(g,tmp_path/'final')['candidate'])
    return source,middle,final,args,q,ids


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_negotiated_paths_preserve_source_ports_and_finish_real_ground_access(tmp_path,quarter,mirror,layer):
    source,middle,final,args,q,ids=saved(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    before=source.read_bytes();r=op.receive_full(source,middle,final,q)
    assert r['ok'] and r['complete'],r
    assert r['retired_track_uuids']==sorted(ids) and r['saved_return_witness_mm']==0
    assert r['source_return_witness_mm']>1.5 and r['signal_only_intermediate_not_adopted_as_baseline']
    assert r['ground_phase']['new_holes']==1 and r['ordinary_phase']['source_ground_ingress_actually_clear']
    assert source.read_bytes()==before and force._sidecars(source)==force._sidecars(final)
    assert not r['release_authority'] and not r['fab_ready'] and not r['current_qualified']
    for path in q['paths']:
        assert path['source_points_nm'][0]==path['candidate_points_nm'][0]
        assert path['source_points_nm'][-1]==path['candidate_points_nm'][-1]
        assert path['width_nm']==200000 and path['layer']==pcbnew.In2_Cu
        assert 0<op._length(path['candidate_points_nm'])-op._length(path['source_points_nm'])<=1000000


def test_dependency_is_discovered_not_just_a_permit_to_rip_an_unrelated_neighbour(tmp_path):
    source,args,ids=fixture(tmp_path)
    with pytest.raises(ValueError,match='no_native_clear_option'):
        op.plan(source,**dict(args,peer_track_uuid=None))
    r=op.discover(source,**{k:v for k,v in args.items() if k!='peer_track_uuid'})
    assert r['ok'] and r['complete'] and r['proposal']['peer_track_uuid']==ids[1]
    assert r['trials'][0]['peer_track_uuid'] is None and r['maximum_peer_trials']==5
    assert r['proposal']['peer_is_actual_native_blocker_of_primary_detour']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_clear_peer_is_retained_and_single_primary_can_finish_without_ripup_expansion(tmp_path,quarter,mirror):
    source,middle,final,args,q,ids=saved(tmp_path,quarter=quarter,mirror=mirror,peer_near=False)
    r=op.receive_full(source,middle,final,q)
    assert r['ok'] and r['complete'] and r['retired_track_uuids']==[ids[0]],r
    assert not q['peer_is_actual_native_blocker_of_primary_detour'] and len(q['paths'])==1
    assert ids[1] in {force._uid(t) for t in pcbnew.LoadBoard(str(final)).GetTracks()}
    with pytest.raises(ValueError):op.plan(source,**dict(args,peer_track_uuid=ids[1]))


@pytest.mark.parametrize('fault',['primary_group','peer_group','mask','width','primary_power','peer_power',
    'primary_clock','peer_pair','wrong_face','no_lock_authority','same_net','curved','distant_peer','unknown_peer',
    'max_extra','max_offset','invalid_bool','deadline','missing_rule'])
def test_typing_and_ownership_cannot_be_inferred_from_a_hole_or_generic_hint(tmp_path,fault):
    source,args,ids=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    first,second=[live[u] for u in ids]
    if fault.endswith('group'):
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED_SOURCE_COPPER');b.Add(g)
        g.AddItem(first if fault=='primary_group' else second)
    elif fault=='mask':
        # KiCad does not serialize an inner-layer mask flag. Exercise the
        # actual in-memory process guard, not an invented saved capability.
        first.SetHasSolderMask(True)
        with pytest.raises(ValueError):op._selected(b,source,'synthetic',ids,True)
        return
    elif fault=='width':first.SetWidth(500000)
    elif fault in ('primary_power','peer_power','primary_clock','peer_pair'):
        names={'primary_power':'+12V','peer_power':'+5V_SYS','primary_clock':'/CLOCK','peer_pair':'/USB_D_P'}
        net=names[fault];b.Add(pcbnew.NETINFO_ITEM(b,net))
        (first if fault.startswith('primary') else second).SetNet(b.FindNet(net))
        with pytest.raises(ValueError):op._selected(b,source,'synthetic',ids,True)
        return
    elif fault=='wrong_face':second.SetLayer(pcbnew.In3_Cu)
    elif fault=='no_lock_authority':args['allow_locked_source']=False
    elif fault=='same_net':
        second.SetNet(first.GetNet())
        with pytest.raises(ValueError):op._selected(b,source,'synthetic',ids,True)
        return
    elif fault=='curved':first.SetEnd(first.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='distant_peer':second.Move(pcbnew.VECTOR2I(-3000000,0))
    elif fault=='unknown_peer':args['peer_track_uuid']='not-a-native-source-track'
    elif fault=='max_extra':args['max_extra_mm']=0
    elif fault=='max_offset':args['max_offset_mm']=2.0001
    elif fault=='invalid_bool':args['allow_locked_source']=1
    elif fault=='deadline':args['timeout_s']=0
    else:source.with_suffix('.kicad_dru').unlink()
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,**args)


@pytest.mark.parametrize('fault',['plan','width','end','layer','lock','part','extra','retired_via','rule',
    'missing_final_ground','wrong_final_ground','wrong_intermediate','wrong_source'])
def test_saved_full_chain_rejects_forged_or_unowned_deltas(tmp_path,fault):
    source,middle,final,args,q,ids=saved(tmp_path)
    b=pcbnew.LoadBoard(str(middle));old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    new=next(t for t in b.GetTracks() if force._uid(t) not in old)
    if fault=='plan':q=copy.deepcopy(q);q['paths'][0]['width_nm']-=1
    elif fault=='width':new.SetWidth(199999)
    elif fault=='end':new.SetEnd(new.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='layer':new.SetLayer(pcbnew.B_Cu)
    elif fault=='lock':new.SetLocked(not new.IsLocked())
    elif fault=='part':next(iter(b.GetFootprints())).SetValue('not-the-source-value')
    elif fault=='extra':track(b,'lane_one',(23,22),(24,22),layer=pcbnew.In2_Cu,width=.2)
    elif fault=='retired_via':b.Remove(next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA'))
    elif fault=='rule':middle.with_suffix('.kicad_dru').write_text('(version 1)')
    elif fault=='missing_final_ground':final=force._copy_family(middle,tmp_path/'no-ground-entry')
    elif fault=='wrong_final_ground':
        child=pcbnew.LoadBoard(str(final));known={force._uid(t) for t in b.GetTracks()}
        via=next(t for t in child.GetTracks() if force._uid(t) not in known)
        via.Move(pcbnew.VECTOR2I(1,0));field._save_field_snapshot(child,final)
    elif fault=='wrong_intermediate':middle=final
    elif fault=='wrong_source':source=middle
    if fault not in ('wrong_intermediate','wrong_source'):field._save_field_snapshot(b,middle)
    r=op.receive_full(source,middle,final,q)
    assert not r['ok'] and not r['complete'] and r['errors'],r


def test_constructor_must_rederive_all_dependency_geometry_from_the_saved_source(tmp_path):
    source,args,ids=fixture(tmp_path);q=op.plan(source,**args)
    q=copy.deepcopy(q);q['paths'][1]['candidate_points_nm'][1][0]+=1
    with pytest.raises(ValueError,match='stale_or_forged'):op.construct(q)
