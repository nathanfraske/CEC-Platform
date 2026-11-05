"""New macro warnings never authorize deleting a load, old fault, or power."""
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_macro_tail_cleanup as cleanup
from test_ordinary_redundant_cut_receiving import case


def report(*rows):return dict(violations=list(rows))
def warning(uid,kind='track_dangling'):return dict(type=kind,items=[dict(uuid=uid)])


def test_only_new_exact_track_warning_identities_are_work_hints():
    old=report(warning('inherited'),warning('same-id','clearance'))
    proposed=report(warning('inherited'),warning('same-id'),warning('new'),warning('via','via_dangling'))
    assert cleanup.new_warning_ids(old,proposed)==['new','same-id']


@pytest.mark.parametrize('bad',[None,{},dict(violations=None),report({}),
    report(dict(type='track_dangling',items=None)),report(dict(type='track_dangling',items=[dict(uuid=None)]))])
def test_unbound_or_malformed_native_hint_inventories_refuse(bad):
    with pytest.raises(ValueError):cleanup.new_warning_ids(report(),bad)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('prefix',['/renamed/','/other/'])
def test_native_tail_cut_receives_without_moving_any_surviving_geometry(tmp_path,rotation,mirror,prefix):
    source,_,tracks,_,trunk,_=case(tmp_path,rotation=rotation,mirror=mirror,prefix=prefix)
    saved=source.read_bytes()
    r=cleanup.construct(source,tmp_path/'atomic-cleanup',board_hint='synthetic',
        original_native=report(),proposed_native=report(warning(tracks[-1])))
    assert r['ok'] and r['complete'] and r['changed'],r
    assert r['retired_track_uuids']==tracks and not r['release_authority']
    assert r['original_macro_source_receiving_still_required']
    child=pcbnew.LoadBoard(r['candidate']);assert trunk in {force._uid(t) for t in child.GetTracks()}
    assert source.read_bytes()==saved


def test_an_inherited_warning_is_not_automatically_cleaned_or_hidden(tmp_path):
    source,_,tracks,_,_,_=case(tmp_path)
    r=cleanup.construct(source,tmp_path/'unused',board_hint='synthetic',
        original_native=report(warning(tracks[0])),proposed_native=report(warning(tracks[0])))
    assert r['ok'] and r['complete'] and not r['changed'] and r['candidate'] is None
    assert not (tmp_path/'unused').exists()


@pytest.mark.parametrize('mode',['locked','group','power','gnd','pair','live_bridge'])
def test_a_warning_cannot_bypass_ownership_or_source_native_terminals(tmp_path,mode):
    source,_,tracks,_,trunk,net=case(tmp_path,locked=mode=='locked');b=pcbnew.LoadBoard(str(source))
    if mode=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('protected');b.Add(group)
        group.AddItem(next(t for t in b.GetTracks() if force._uid(t)==tracks[0]))
    if mode in ('power','gnd','pair'):
        net={'power':'+5V','gnd':'GND','pair':'/USB_D_P'}[mode];b.Add(pcbnew.NETINFO_ITEM(b,net));code=b.GetNetcodeFromNetname(net)
        for i in [*b.GetTracks(),*(p for f in b.GetFootprints() for p in f.Pads())]:i.SetNetCode(code)
    field._save_field_snapshot(b,source)
    uid=trunk if mode=='live_bridge' else tracks[0]
    r=cleanup.construct(source,tmp_path/'refused',board_hint='synthetic',
        original_native=report(),proposed_native=report(warning(uid)))
    assert not r['ok'] and r['errors'],r


@pytest.mark.parametrize('timeout',[0,11,True,float('nan'),float('inf')])
def test_unbounded_or_ambiguous_operation_deadlines_refuse(tmp_path,timeout):
    r=cleanup.construct(tmp_path/'missing.kicad_pcb',tmp_path/'unused',board_hint='synthetic',
        original_native=report(),proposed_native=report(),timeout_s=timeout)
    assert not r['ok'] and r['errors'] and not (tmp_path/'unused').exists()


def port_case(tmp_path,rotation=0,mirror=False,locked=False):
    source,_,tracks,_,trunk,net=case(tmp_path,rotation=rotation,mirror=mirror)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    for f in b.GetFootprints():f.Flip(f.GetPosition(),False)
    live[trunk].SetLayer(pcbnew.B_Cu)
    port=pcbnew.PCB_VIA(b);port.SetPosition(live[tracks[0]].GetStart());port.SetNetCode(b.GetNetcodeFromNetname(net))
    port.SetWidth(600000);port.SetDrill(300000);port.SetViaType(pcbnew.VIATYPE_THROUGH)
    port.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);port.SetLocked(locked);b.Add(port)
    field._save_field_snapshot(b,source)
    return source,tracks,trunk,force._uid(port)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('locked',[False,True])
def test_obsolete_two_face_routing_port_is_received_in_the_same_atomic_cut(tmp_path,rotation,mirror,locked):
    source,tracks,trunk,port=port_case(tmp_path,rotation,mirror,locked);before=source.read_bytes()
    r=cleanup.construct(source,tmp_path/'compound',board_hint='synthetic',original_native=report(),
        proposed_native=report(warning(tracks[0])),allow_locked_obsolete_port_vias=locked)
    assert r['ok'] and r['complete'],r
    assert r['retired_via_uuids']==[port]
    assert r['locked_via_scope_used']==([port] if locked else [])
    assert r['original_two_face_port_retirement_witnesses'][0]['source_actual_contact_faces']==[0,2]
    saved=pcbnew.LoadBoard(r['candidate']);assert {force._uid(t) for t in saved.GetTracks()}=={trunk}
    assert source.read_bytes()==before


def test_source_locked_routing_port_needs_explicit_retirement_authority(tmp_path):
    source,tracks,_,_=port_case(tmp_path,locked=True)
    r=cleanup.construct(source,tmp_path/'refused-port',board_hint='synthetic',original_native=report(),
        proposed_native=report(warning(tracks[0])))
    assert not r['ok'] and any('exact_source_lock_retirement_authority' in e for e in r['errors'])
    assert not (tmp_path/'refused-port').exists()


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('whole',[False,True])
def test_exact_locked_ordinary_tail_can_retire_only_through_independent_receiving(tmp_path,rotation,mirror,whole):
    source,_,tracks,_,trunk,_=case(tmp_path,rotation=rotation,mirror=mirror,locked=True)
    raw=source.read_bytes()
    r=cleanup.construct(source,tmp_path/'exact-locked-tail',board_hint='synthetic',original_native=report(),
        proposed_native=report(warning(tracks[0])),allow_locked_obsolete_track_uuids=tracks,
        native_grade=(lambda path,index:report()) if whole else None)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert set(r['locked_track_scope_used'])==set(tracks)
    assert not r['release_authority'] and source.read_bytes()==raw
    child=pcbnew.LoadBoard(r['candidate'])
    assert {force._uid(t) for t in child.GetTracks()}=={trunk}


@pytest.mark.parametrize('mode',['partial','wrong_track','group','power','gnd','pair'])
def test_explicit_lock_scope_does_not_authorize_unowned_or_protected_material(tmp_path,mode):
    source,_,tracks,_,trunk,_=case(tmp_path,locked=True);board=pcbnew.LoadBoard(str(source))
    if mode=='partial':
        old=next(t for t in board.GetTracks() if force._uid(t)==tracks[0])
        stem=pcbnew.PCB_TRACK(board);stem.SetStart(old.GetEnd())
        stem.SetEnd(old.GetEnd()+pcbnew.VECTOR2I_MM(1,0));stem.SetWidth(old.GetWidth())
        stem.SetLayer(old.GetLayer());stem.SetNetCode(old.GetNetCode());stem.SetLocked(True);board.Add(stem)
        tracks.append(force._uid(stem))
    if mode=='group':
        group=pcbnew.PCB_GROUP(board);group.SetName('protected');board.Add(group)
        group.AddItem(next(t for t in board.GetTracks() if force._uid(t)==tracks[0]))
    if mode in ('power','gnd','pair'):
        net={'power':'+5V','gnd':'GND','pair':'/USB_D_P'}[mode]
        board.Add(pcbnew.NETINFO_ITEM(board,net));code=board.GetNetcodeFromNetname(net)
        for item in [*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads())]:item.SetNetCode(code)
    field._save_field_snapshot(board,source)
    scope=tracks[:1] if mode=='partial' else [trunk] if mode=='wrong_track' else tracks
    r=cleanup.construct(source,tmp_path/'not-authorized',board_hint='synthetic',original_native=report(),
        proposed_native=report(warning(tracks[0])),allow_locked_obsolete_track_uuids=scope)
    assert not r['ok'] and r['errors'],r


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_port_and_its_subpad_source_stem_retire_in_one_exact_received_delta(tmp_path,rotation,mirror):
    source,tracks,trunk,port=port_case(tmp_path,rotation,mirror,locked=True)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    t=live[trunk];v=live[port];old_end=pcbnew.VECTOR2I(t.GetEnd())
    span=tuple(z-a for a,z in zip(tuple(t.GetStart()),tuple(t.GetEnd())))
    corner=v.GetPosition()+pcbnew.VECTOR2I(*(round(d*60000/20000000) for d in span))
    t.SetEnd(corner)
    other=pcbnew.PCB_TRACK(b);other.SetStart(corner);other.SetEnd(old_end);other.SetLayer(pcbnew.B_Cu)
    other.SetWidth(200000);other.SetNetCode(t.GetNetCode());b.Add(other)
    stem=pcbnew.PCB_TRACK(b);stem.SetStart(v.GetPosition());stem.SetEnd(corner);stem.SetLayer(pcbnew.B_Cu)
    stem.SetWidth(200000);stem.SetNetCode(t.GetNetCode());b.Add(stem)
    field._save_field_snapshot(b,source);raw=source.read_bytes()
    r=cleanup.construct(source,tmp_path/'whole-port-and-stem',board_hint='synthetic',
        original_native=report(),proposed_native=report(warning(tracks[0])),allow_locked_obsolete_port_vias=True)
    assert r['ok'] and r['complete'],r
    assert set(r['retired_track_uuids'])==set(tracks)|{force._uid(stem)}
    assert r['retired_via_uuids']==[port]
    assert r['source_subsumed_port_stem_witnesses'][0]['entire_original_capsule_inside_original_via_land']
    child=pcbnew.LoadBoard(r['candidate']);assert {force._uid(x) for x in child.GetTracks()}=={trunk,force._uid(other)}
    assert source.read_bytes()==raw


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_finite_crosslayer_warning_cascade_is_received_against_one_original_prefix(tmp_path,rotation,mirror):
    from test_lastmile import _board
    from test_field_proposals import track
    import math
    def xy(p):
        x,y=p[0]-15,p[1]-15
        if mirror:x=-x
        a=math.radians(rotation)
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    net='/different/CELL_CONTROL'
    b=_board([(*xy((5,10)),net),(*xy((25,10)),net)],edge=(0,0,30,30))
    trunk=track(b,net,xy((5,10)),xy((25,10)),width=.2)
    bridge=track(b,net,xy((12,13)),xy((15,10)),layer=pcbnew.B_Cu,width=.2)
    tail=track(b,net,xy((12,13)),xy((12,16)),width=.2)
    ports=[]
    for point in ((12,13),(15,10)):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy(point)));v.SetNetCode(trunk.GetNetCode())
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLocked(True);b.Add(v);ports.append(force._uid(v))
    source=tmp_path/'cascade.kicad_pcb';field._save_field_snapshot(b,source);raw=source.read_bytes();calls=[]
    def native_grade(path,index):
        calls.append(index);saved=pcbnew.LoadBoard(str(path));ids={force._uid(t) for t in saved.GetTracks()}
        return report(warning(force._uid(bridge))) if force._uid(bridge) in ids else report()
    r=cleanup.construct(source,tmp_path/'atomic-cascade',board_hint='synthetic',original_native=report(),
        proposed_native=report(warning(force._uid(tail))),allow_locked_obsolete_port_vias=True,native_grade=native_grade)
    assert r['ok'] and r['complete'] and r['original_prefix_received_as_one_delta'],r
    assert calls==[0,1] and len(r['passes'])==2
    assert set(r['retired_track_uuids'])=={force._uid(tail),force._uid(bridge)}
    assert set(r['retired_via_uuids'])==set(ports)
    assert r['final_exclusive_barrel_uuids']==[ports[0]] and r['final_single_face_barrel_uuids']==[ports[1]]
    child=pcbnew.LoadBoard(r['candidate']);assert {force._uid(t) for t in child.GetTracks()}=={force._uid(trunk)}
    assert source.read_bytes()==raw and not r['release_authority']


def test_stale_native_feedback_refuses_instead_of_repeating_cleanup_forever(tmp_path):
    source,_,tracks,_,_,_=case(tmp_path)
    r=cleanup.construct(source,tmp_path/'refused-cycle',board_hint='synthetic',original_native=report(),
        proposed_native=report(warning(tracks[0])),native_grade=lambda *_:report(warning(tracks[0])))
    assert not r['ok'] and r['errors'] and len(r['passes'])<=2
