"""Ordinary scope cannot borrow quiet/power authority from shared geometry."""
import json
from types import SimpleNamespace
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_ordinary_signal_completion as op
import cec_native_portal_geometry as geometry
from test_lastmile import _board


def fixture(tmp_path,net='/renamed/CONTROL',quarter=0,back=False):
    b=_board([(5,10,net),(15,10,net)],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    for i,f in enumerate(b.GetFootprints()):
        f.SetReference('RENAMED_'+str(i));f.SetValue('authored unchanged')
        for p in f.Pads():p.SetNumber('1');p.SetPinType('input')
    if quarter or back:
        for f in b.GetFootprints():
            f.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
            if back:f.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {
        'classes':[{'name':'Default','track_width':.22,'clearance':.2,'via_diameter':.6,'via_drill':.3}]}}))
    return source,b,net


def target(b,q):
    r=q['request'];return dict(target_net=r['net'],width_mm=r['width_nm']/1e6,
        clearance_mm=r['clearance_nm']/1e6,route_endpoints=[dict(uuid=force._uid(p),kind='pad',
            x_mm=p.GetPosition().x/1e6,y_mm=p.GetPosition().y/1e6)for p in op._pads(b,r)])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_ordinary_source_native_join_replay_all_poses(tmp_path,monkeypatch,quarter,back):
    import cec_route_proposal_guard as guards
    import cec_field_search as search
    source,b,net=fixture(tmp_path,quarter=quarter,back=back)
    q=op.plan(b,source,board_hint='synthetic',net=net);assert q['complete'],q
    assert q['request']['width_nm']==220000
    candidate=force._copy_family(source,tmp_path/'child');seen=[]
    class Guard:
        def __init__(self,*a,**k):self.counts={}
        def __call__(self,ops):seen.append(('final_guard',ops));return True
    monkeypatch.setattr(guards,'RouteProposalGuard',Guard)
    monkeypatch.setattr(search,'PlanarSearchGuard',lambda *a,**k:SimpleNamespace(active=False))
    monkeypatch.setattr(fr,'_lastmile_route_layers',lambda b,**k:[pcbnew.In2_Cu]if k['exclude_front']else[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
    def bridge(board,A,al,B,bl,width,*args,**kwargs):
        seen.append(('bridge',kwargs))
        if sum(k=='bridge'for k,_ in seen)==1:return None
        return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,next(iter(al)))]
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    before=source.read_bytes();r=geometry.apply_native_portals(candidate,target(b,q),5.)
    assert r['closed']==1 and not r['release_authority'],r
    calls=[kw for k,kw in seen if k=='bridge']
    assert len(calls)==2 and calls[0]['deadline_monotonic']==calls[1]['deadline_monotonic']
    assert calls[0]['native_endpoint_seeds']and calls[0]['canonical_turns_only']
    assert any(k=='final_guard'for k,_ in seen)
    proof=op.receive(source,candidate,board_hint='synthetic',net=net)
    assert proof['ok']and proof['complete']and proof['whole_shared_stage_still_required'],proof
    assert source.read_bytes()==before


@pytest.mark.parametrize('net',['+3V3','GND','/USB_D_P','/USB_D_N','/SENSEC1_LO','/CLOCK','/SB_SENSE0'])
def test_protected_source_role_is_not_ordinary_because_geometry_could_fit(tmp_path,net):
    source,b,net=fixture(tmp_path,net=net)
    q=op.plan(b,source,board_hint='synthetic',net=net)
    assert not q['complete']and q['reason']=='source_net_not_positively_ordinary',q


@pytest.mark.parametrize('pin',['power_in','power_out'])
def test_neutrally_named_supply_pin_is_still_not_ordinary(tmp_path,pin):
    source,b,net=fixture(tmp_path);next(iter(next(iter(b.GetFootprints())).Pads())).SetPinType(pin)
    field._save_field_snapshot(b,source)
    assert not op.plan(b,source,board_hint='synthetic',net=net)['complete']


@pytest.mark.parametrize('fault',['underwidth','orphan','wrong_net','moved_pad'])
def test_saved_ordinary_scope_rejects_unrooted_or_invalid_new_material(tmp_path,fault):
    source,b,net=fixture(tmp_path);q=op.plan(b,source,board_hint='synthetic',net=net)
    candidate=force._copy_family(source,tmp_path/'bad');child=pcbnew.LoadBoard(str(candidate));ends=op._pads(child,q['request'])
    if fault=='moved_pad':ends[1].Move(pcbnew.VECTOR2I_MM(.1,0))
    t=pcbnew.PCB_TRACK(child);t.SetStart(ends[0].GetPosition());t.SetEnd(ends[1].GetPosition())
    t.SetWidth(50000 if fault=='underwidth'else q['request']['width_nm']);t.SetLayer(pcbnew.F_Cu);t.SetNet(ends[0].GetNet());child.Add(t)
    if fault=='wrong_net':
        new=pcbnew.NETINFO_ITEM(child,'FORGED');child.Add(new);t.SetNet(new)
    elif fault=='orphan':
        extra=pcbnew.PCB_TRACK(child);extra.SetStart(pcbnew.VECTOR2I_MM(25,25));extra.SetEnd(pcbnew.VECTOR2I_MM(26,25))
        extra.SetWidth(q['request']['width_nm']);extra.SetLayer(pcbnew.F_Cu);extra.SetNet(ends[0].GetNet());child.Add(extra)
    if fault=='wrong_net':
        # Intentionally malformed literal evidence: the normal snapshot
        # helper already refuses this short at its save/reload boundary.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate),child)
    else:field._save_field_snapshot(child,candidate)
    assert not op.receive(source,candidate,board_hint='synthetic',net=net)['ok']


def test_constructor_recompiles_source_and_spawns_geometry_not_quiet_scope(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    source,b,net=fixture(tmp_path);candidate=force._copy_family(source,tmp_path/'child');seen=[]
    monkeypatch.setattr(repair,'_spawn_apply',lambda worker,args,**kw:seen.append((worker,args,kw))or{'closed':0})
    r=op.construct_private(source,candidate,{'net':net,'request':{'width_nm':1}},board_hint='synthetic')
    assert not r['complete']and r['independently_recompiled_source_request']['width_nm']==220000
    assert seen[0][0]is geometry.apply_native_portals and seen[0][1][2]<=10
    assert seen[0][1][1]['middle_grid_schedule_mm']==[.5,.25]
    assert seen[0][2]['search_budget_arg']==2


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf')])
def test_generic_portal_lease_cannot_reset_or_expand(seconds):
    with pytest.raises(ValueError,match='bounded_native_portal_work_lease'):
        geometry.apply_native_portals('missing',{},seconds)


@pytest.mark.parametrize('compiled',[False,True])
def test_received_stage_dispatch_never_publishes_incomplete_ordinary_attempt(tmp_path,monkeypatch,compiled):
    import cec_received_private_stage as stage
    source,b,net=fixture(tmp_path);seen=[]
    monkeypatch.setattr(stage,'identity',lambda *a:{'exact':'epoch'})
    monkeypatch.setattr(op,'plan',lambda *a,**kw:{'complete':compiled,'net':net})
    monkeypatch.setattr(op,'construct_private',lambda *a,**kw:seen.append(kw)or{'complete':False})
    monkeypatch.setattr(op,'receive',lambda *a,**kw:pytest.fail('no saved join to receive'))
    r=stage.worker(dict(source=str(source),directory=str(tmp_path),board_hint='synthetic',assembly_instance=None,
        identity={'exact':'epoch'},operator='ordinary_native_portals',net=net))
    assert r['gates']=={}and r['reason']=='finite_proposal_incomplete'
    assert bool(seen)==compiled and not(tmp_path/'publication.json').exists()
