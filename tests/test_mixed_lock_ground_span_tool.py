"""Mixed lock repair is exact stronger metadata, never a physical waiver."""
import sys
from pathlib import Path
import pcbnew,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import cec_mixed_lock_ground_span as worker
import cec_native_ground_span_reflow as original
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_ground_elbow_reflow import native_span_fixture
from test_field_proposals import track


def case(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,old,_=native_span_fixture(tmp_path,quarter,mirror,layer)
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==old])
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return x,y
    points=[point(*p) for p in ((8,8),(11,8),(11,10),(10,10))]
    made=[track(b,'GND',a,z,layer=layer,width=.2) for a,z in zip(points,points[1:])]
    made[0].SetLocked(True);field._save_field_snapshot(b,source)
    ids=[force._uid(t) for t in made];locks=[ids[0]]
    ports=sorted([list(pcbnew.VECTOR2I_MM(*points[0])),list(pcbnew.VECTOR2I_MM(*points[-1]))])
    return source,b,dict(board_hint='synthetic',track_uuids=ids,points_nm=ports,allow_locked_track_uuids=locks)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_stronger_exact_locks_keep_the_original_span_owner_and_all_physical_gates(tmp_path,quarter,mirror,layer):
    source,b,args=case(tmp_path,quarter,mirror,layer);raw=source.read_bytes()
    with pytest.raises(ValueError):original.plan(b,args['track_uuids'],args['points_nm'],allow_locked_track_uuids=args['allow_locked_track_uuids'])
    scope=worker.plan(source,**args);child,added=worker.construct(source,scope)
    target=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(child,target)
    r=worker.receive(source,target,scope,board_hint='synthetic');assert r['ok'] and r['complete'],r
    assert r['source_relock_preparation']['entire_source_tree_except_exact_stronger_locks_equal']
    assert r['source_relock_preparation']['no_source_lock_weakened']
    assert r['original_span_receiver_and_physical_rules_unchanged'] and r['source_span_already_redundant_to_retained_native_copper']
    assert r['ground_trace_length_saved_mm']>3 and all(t.IsLocked() for t in child.GetTracks() if force._uid(t) in added)
    assert source.read_bytes()==raw and not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('fault',['missing_permission','extra_permission','unlocked','all_locked','wide','mask','group','not_ground'])
def test_only_the_actual_explicit_mixed_source_cut_can_be_relocked(tmp_path,fault):
    source,b,args=case(tmp_path);rows=[t for t in b.GetTracks() if force._uid(t) in args['track_uuids']]
    if fault=='missing_permission':args['allow_locked_track_uuids']=[]
    elif fault=='extra_permission':args['allow_locked_track_uuids'].append('not-a-source-track')
    elif fault in ('unlocked','all_locked'):
        for t in rows:t.SetLocked(fault=='all_locked')
    elif fault=='wide':rows[0].SetWidth(500000)
    elif fault=='mask':rows[0].SetHasSolderMask(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('separate_owner');b.Add(g);g.AddItem(rows[0])
    else:
        net=pcbnew.NETINFO_ITEM(b,'/NOT_GROUND');b.Add(net)
        # Keep the hostile saved net electrically self-consistent so this
        # exercises role refusal, not the writer's foreign-short guard.
        for item in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads()),*b.Zones()]:
            if item.GetNetname()=='GND':item.SetNet(net)
    field._save_field_snapshot(b,source);raw=source.read_bytes()
    with pytest.raises(ValueError):worker.plan(source,**args)
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['unlock','width','face','pad','via','sidecar'])
def test_saved_reflow_cannot_weaken_a_lock_or_change_unowned_physical_material(tmp_path,fault):
    source,b,args=case(tmp_path);scope=worker.plan(source,**args);child,added=worker.construct(source,scope)
    t=next(t for t in child.GetTracks() if force._uid(t) in added)
    if fault=='unlock':t.SetLocked(False)
    elif fault=='width':t.SetWidth(210000)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='pad':next(p for fp in child.GetFootprints() for p in fp.Pads()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='via':next(t for t in child.GetTracks() if t.GetClass()=='PCB_VIA').SetDrill(250000)
    target=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(child,target)
    if fault=='sidecar':target.with_suffix('.kicad_dru').write_text('(version 1)\n')
    r=worker.receive(source,target,scope,board_hint='synthetic')
    assert not r['ok'] and r['errors'] and not r['release_authority'],r
