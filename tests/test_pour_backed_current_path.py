"""Geometry/process fixtures; mocked authority is never a hardware rating."""
import copy
from pathlib import Path
import pcbnew,pytest
import cec_pour_backed_current_path as owner
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False,face=pcbnew.F_Cu):
    board=_board([],edge=(0,0,60,60));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    net=pcbnew.NETINFO_ITEM(board,'/SYNTHETIC_FULL_CURRENT_GEOMETRY_NOT_A_RATING');board.Add(net)
    def at(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return pcbnew.VECTOR2I(round((30+x)*1e6),round((30+y)*1e6))
    def track(a,z):
        t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(face);t.SetWidth(600000)
        t.SetStart(at(*a));t.SetEnd(at(*z));board.Add(t);return t
    points=[(-3,0),(-1,0),(-.6,.4),(.6,.4),(1,0),(3,0)]
    cut=[track(a,z) for a,z in zip(points,points[1:])]
    track((-4,0),(-3,0));track((3,0),(4,0))
    fp=pcbnew.FOOTPRINT(board);board.Add(fp);fp.SetReference('NATIVE_PORT')
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNumber('1');pad.SetNet(net)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetPosition(at(-3,0))
    ls=pcbnew.LSET();ls.AddLayer(face);pad.SetLayerSet(ls)
    zone=pcbnew.ZONE(board);zone.SetNet(net);zone.SetLayer(face)
    zone.SetZoneName(owner.base.native.ZONE_NAME);zone.SetMinThickness(100000)
    zone.SetLocalClearance(200000);zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.Outline().Append(owner.base.native._poly([list(at(*p)) for p in
        [(-4.5,-1.5),(4.5,-1.5),(4.5,1.5),(-4.5,1.5)]]));board.Add(zone)
    gnd=pcbnew.NETINFO_ITEM(board,'GND');board.Add(gnd)
    ground=pcbnew.ZONE(board);ground.SetNet(gnd);ground.SetLayer(pcbnew.In1_Cu)
    ground.SetMinThickness(100000);ground.SetLocalClearance(200000)
    ground.Outline().Append(owner.base.native._poly([[1000000,1000000],[59000000,1000000],
        [59000000,59000000],[1000000,59000000]]));board.Add(ground)
    board.BuildConnectivity();assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    owner.base.field._save_field_snapshot(board,source)
    contract=dict(net=net.GetNetname(),explicit_synthetic_geometry_not_hardware=True)
    monkeypatch.setattr(owner.full,'_model',lambda *a:('synthetic_geometry',None,contract))
    monkeypatch.setattr(owner.full,'_source_width_floor',lambda *a:400000)
    class Guard:
        def __init__(self,*a,**k):pass
        def __call__(self,*a,**k):return True
    monkeypatch.setattr(owner.capture,'Guard',Guard)
    monkeypatch.setattr(owner.debt,'receive',lambda *a,**k:dict(ok=True,complete=True,
        synthetic_geometry_fixture_not_current_qualification=True))
    args=dict(board_hint='explicit_synthetic_pour_backed_geometry',
        retired_track_uuids=[owner.base.force._uid(t) for t in cut])
    return source,args,owner.base.force._uid(zone),owner.base.force._uid(pad)


def saved(tmp_path,monkeypatch,**kwargs):
    source,args,zone,pad=fixture(tmp_path,monkeypatch,**kwargs)
    q=owner.plan(source,**args);board,added=owner.construct(source,q)
    child=owner.base.force._copy_family(source,tmp_path/'candidate')
    owner.base.field._save_field_snapshot(board,child)
    return source,child,q,zone,pad,added


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_current_path_loses_four_bends_but_no_native_copper_or_authority(tmp_path,monkeypatch,quarter,mirror,face):
    source,child,q,_,_,added=saved(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face)
    raw=source.read_bytes();proof=owner.receive(source,child,q)
    assert proof['ok'] and proof['complete'],proof
    assert proof['native_strokes_before_after']==[5,1] and len(added)==1
    assert proof['saved_trace_length_mm']>0
    assert proof['actual_native_copper_unchanged_under_literal_source_keeper']
    assert proof['all_other_objects_and_ground_sheets_literal']
    assert proof['nonzone_contact_kernels_retained_in_literal_copper']
    assert proof['exact_source_current_width_face_and_authority_retained']
    assert proof['every_surviving_native_partition_preserved']
    assert not proof['current_or_barrel_qualified'] and not proof['release_authority']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['policy','source','contract','width','points','keeper'])
def test_rehashed_plan_cannot_change_source_geometry_or_current_authority(tmp_path,monkeypatch,fault):
    source,child,q,_,_,_=saved(tmp_path,monkeypatch);bad=copy.deepcopy(q)
    if fault=='policy':bad['policy']='forged'
    elif fault=='source':bad['source_sha256']='0'*64
    elif fault=='contract':bad['current_proposal']['contract']['invented_rating']=True
    elif fault=='width':bad['current_proposal']['width_nm']=1
    elif fault=='points':bad['points_nm'][0][0]+=1
    else:bad['literal_backing_zone']['configuration']['uuid']='forged'
    proof=owner.receive(source,child,bad)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('fault',['width','ground','backer','extra','field','pad'])
def test_unowned_saved_changes_and_lost_literal_backing_are_rejected(tmp_path,monkeypatch,fault):
    source,child,q,zone,pad,added=saved(tmp_path,monkeypatch);board=pcbnew.LoadBoard(str(child))
    if fault=='width':next(t for t in board.GetTracks() if owner.base.force._uid(t)==added[0]).SetWidth(599999)
    elif fault=='ground':next(z for z in board.Zones() if z.GetNetname()=='GND').UnFill()
    elif fault=='backer':next(z for z in board.Zones() if owner.base.force._uid(z)==zone).UnFill()
    elif fault=='extra':
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(10,10));t.SetEnd(pcbnew.VECTOR2I_MM(11,10));t.SetWidth(200000);board.Add(t)
    elif fault=='field':next(iter(board.GetFootprints())).SetValue('UNOWNED')
    else:next(p for fp in board.GetFootprints() for p in fp.Pads() if owner.base.force._uid(p)==pad).Move(pcbnew.VECTOR2I(1,0))
    owner.base.field._save_field_snapshot(board,child)
    proof=owner.receive(source,child,q);assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('fault',['unfilled','rule_area','unregistered','underwidth','unknown','ports'])
def test_actual_source_backing_width_ports_and_positive_authority_are_required(tmp_path,monkeypatch,fault):
    source,args,zone,_=fixture(tmp_path,monkeypatch);board=pcbnew.LoadBoard(str(source))
    z=next(z for z in board.Zones() if owner.base.force._uid(z)==zone)
    if fault=='unfilled':z.UnFill()
    elif fault=='rule_area':z.SetIsRuleArea(True)
    elif fault=='unregistered':z.SetZoneName('UNSUPPORTED_FILLER')
    elif fault=='underwidth':monkeypatch.setattr(owner.full,'_source_width_floor',lambda *a:600001)
    elif fault=='unknown':
        def missing(*a):raise ValueError('unknown_synthetic_authority_not_invented')
        monkeypatch.setattr(owner.full,'_model',missing)
    else:
        q=owner.plan(source,**args);args['points_nm']=q['points_nm'];args['points_nm'][0][0]+=1
    if fault=='rule_area':
        # The native serializer drops copper-only fields when a filled zone
        # becomes a rule area. Reload that real saved object as the Source;
        # do not assert identity against its invalid transient copper state.
        assert pcbnew.SaveBoard(str(source),board)
    else:owner.base.field._save_field_snapshot(board,source)
    with pytest.raises((ValueError,owner.native.Refused)):owner.plan(source,**args)


def test_actual_native_custom_width_rule_is_not_waived_by_unchanged_copper(tmp_path,monkeypatch):
    from cec_native_drc_runner import run
    source,args,_,_=fixture(tmp_path,monkeypatch)
    q=owner.plan(source,**args);board,_=owner.construct(source,q)
    child=owner.base.force._copy_family(source,tmp_path/'native-width-negative')
    owner.base.field._save_field_snapshot(board,child)
    child.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "actual test width floor" (constraint track_width (min 0.7mm)))\n')
    report=tmp_path/'native-width-negative.json'
    result=run(child,report,reporting_build=Path('/home/codex/.cache/cec/native-drc-10.0.5'),timeout_s=10.)
    assert result['ok'] and result['complete'] and not result['native_inventory']['potentially_truncated']
    assert any(v['type']=='track_width' for v in __import__('json').loads(report.read_text())['violations'])


def test_generic_discovery_is_read_only_and_not_a_global_route_certificate(tmp_path,monkeypatch):
    source,args,_,_=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(owner.full.topology,'board_current_domains',lambda *a:{'/SYNTHETIC_FULL_CURRENT_GEOMETRY_NOT_A_RATING':{}})
    monkeypatch.setattr(owner.full.topology,'distributed_supply_contracts',lambda *a,**k:dict(contracts={}))
    raw=source.read_bytes();found=owner.discover(source,board_hint=args['board_hint'],maximum_candidates=1)
    assert found['ok'] and found['complete'] and found['proposals']
    assert not found['actual_geometry_constructed'] and not found['current_or_barrel_qualified']
    assert source.read_bytes()==raw
