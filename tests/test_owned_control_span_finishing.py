"""Native manufacturer ownership, not a net-name or low-current assumption."""
import json,copy
import pcbnew,pytest
import cec_owned_control_span_finishing as repair
import cec_force_current as force
import cec_field_coupling as field
import cec_current_topology as topology
from test_control_current_branch import fixture as control_fixture
from test_field_proposals import track


def case(tmp_path,monkeypatch,quarter=0,back=False):
    _,source,b,domains=control_fixture(tmp_path,monkeypatch,distributed=True)
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**k:domains)
    g=repair.capture.Guard(b,source,net='RAIL_OTHER',board_hint='synthetic',timeout_s=10.)
    scope=g.scopes[0];via=next(g.native[u] for u in scope['exclusive_material_uuids'] if g.native[u].GetClass()=='PCB_VIA')
    end=g.native[scope['retained_capture_uuids'][0]];old_at=via.GetPosition();at=old_at+pcbnew.VECTOR2I(600000,0)
    old_inner=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu]
    width=old_inner[0].GetWidth()
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.F_Cu:
            if t.GetStart()==old_at:t.SetStart(at)
            if t.GetEnd()==old_at:t.SetEnd(at)
    via.SetPosition(at)
    from cec_native_items import discard_items
    discard_items(b,old_inner)
    corner=pcbnew.VECTOR2I(at.x,end.GetPosition().y)
    old=[]
    for a,z in [(at,corner),(corner,end.GetPosition())]:
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(via.GetNetCode());t.SetWidth(width);t.SetLayer(pcbnew.In2_Cu)
        t.SetStart(a);t.SetEnd(z);t.SetLocked(True);b.Add(t);old.append(t)
    miter=pcbnew.VECTOR2I(at.x,end.GetPosition().y+600000)
    ghosts=[]
    for p in (at,miter,end.GetPosition()):
        t=pcbnew.PCB_TRACK(b);t.SetStart(p);t.SetEnd(p);ghosts.append(t)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*ghosts]:
        if quarter:item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source)
    monkeypatch.setattr(repair.debt,'receive',lambda *a,**k:dict(ok=True,complete=True,synthetic_fixture_only=True))
    args=dict(board_hint='synthetic',retired_track_uuids=[force._uid(t) for t in old],start_uuid=force._uid(via),
        end_uuid=force._uid(end),layer=int(pcbnew.F_Cu if back else pcbnew.B_Cu),
        points_nm=[list(t.GetStart()) for t in ghosts],allow_locked_source=True)
    return source,args


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('annular_landing',[False,True])
def test_same_control_leaf_is_independently_reowned_after_native_face_change(tmp_path,monkeypatch,quarter,back,annular_landing):
    source,args=case(tmp_path,monkeypatch,quarter,back);raw=source.read_bytes()
    if annular_landing:
        b=pcbnew.LoadBoard(str(source));port=next(t for t in b.GetTracks() if force._uid(t)==args['end_uuid'])
        adjacent=next(t for t in b.GetTracks() if force._uid(t) in args['retired_track_uuids']
            and tuple(port.GetPosition()) in (tuple(t.GetStart()),tuple(t.GetEnd())))
        far=adjacent.GetStart() if adjacent.GetEnd()==port.GetPosition() else adjacent.GetEnd()
        at=list(port.GetPosition());delta=[far[i]-at[i] for i in (0,1)]
        shifted=[at[i]+300000*((delta[i]>0)-(delta[i]<0)) for i in (0,1)]
        args['points_nm']=[list(p) for p in next(iter(repair.kernel.capacity.fr._canonical_45_xy_paths(args['points_nm'][0],shifted)))]
    proposal=repair.plan(source,**args)
    assert len(proposal['actual_unchanged_barrel_port_contacts'])==2
    assert all(q['integer_native_drill_subtraction'] and q['contact_vertices'] for q in proposal['actual_unchanged_barrel_port_contacts'])
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    got=repair.receive(source,child,proposal,board_hint='synthetic')
    assert got['ok'] and got['complete'],got['errors']
    assert got['source_typed_control_and_exact_original_input_capture_reowned'] and got['all_surviving_native_partitions_preserved']
    assert got['centerline_removed_mm']>.17 and got['manufacturer_control_current_unknown_not_invented']
    assert source.read_bytes()==raw and not got['current_or_barrel_qualified'] and not got['new_vias'] and not got['pads_moved']


@pytest.mark.parametrize('fault',['wrong_package','dnp','wrong_tie','group','locked','wrong_port','inner_destination',
    'raw_diagonal','backtrack','unowned_supply_span'])
def test_control_ownership_is_positive_and_does_not_grant_supply_repair_authority(tmp_path,monkeypatch,fault):
    source,args=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source));fp=b.FindFootprintByReference('OWNER_RENAMED_0')
    if fault=='wrong_package':fp.SetValue('UNQUALIFIED')
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='wrong_tie':fp.FindPadByNumber('4').SetNet(b.FindNet('OUTPUT_OTHER'))
    elif fault=='group':
        t=next(t for t in b.GetTracks() if force._uid(t) in args['retired_track_uuids']);g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
    elif fault=='locked':args['allow_locked_source']=False
    elif fault=='wrong_port':args['end_uuid']=args['start_uuid']
    elif fault=='inner_destination':args['layer']=int(pcbnew.In3_Cu)
    elif fault=='raw_diagonal':args['points_nm'][1][0]+=1
    elif fault=='backtrack':args['points_nm'].insert(1,[args['points_nm'][0][0],args['points_nm'][0][1]+100000])
    elif fault=='unowned_supply_span':args['retired_track_uuids']=[force._uid(next(t for t in b.GetTracks()
        if t.GetClass()=='PCB_TRACK' and not t.IsLocked()))]
    field._save_field_snapshot(b,source)
    with pytest.raises((ValueError,TypeError,KeyError)):repair.plan(source,**args)


@pytest.mark.parametrize('fault',['width','face','point','root_drill','owner_pose','extra_track','sidecar','forged_role'])
def test_saved_receiving_rejects_unowned_or_forged_changes(tmp_path,monkeypatch,fault):
    source,args=case(tmp_path,monkeypatch);proposal=repair.plan(source,**args)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu)
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='face':t.SetLayer(pcbnew.In3_Cu)
    elif fault=='point':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='root_drill':next(v for v in b.GetTracks() if force._uid(v)==args['end_uuid']).SetDrill(310000)
    elif fault=='owner_pose':b.FindFootprintByReference('OWNER_RENAMED_0').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='extra_track':q=t.Duplicate();q.m_Uuid.Clone(pcbnew.KIID());b.Add(q)
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='forged_role':proposal['owned_manufacturer_control']['manufacturer_role']['current_max_a']=.001
    field._save_field_snapshot(b,child);got=repair.receive(source,child,proposal,board_hint='synthetic')
    assert not got['ok'] and got['errors'] and not got['release_authority']
