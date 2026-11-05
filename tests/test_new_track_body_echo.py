"""Covered new return echoes are not source cuts or current-budget waivers."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_new_track_body_echo as echo
from test_lastmile import _board
from test_field_proposals import track


def fixture(face=pcbnew.F_Cu,rotate=False,net='/SYNTHETIC/RENAMED-RETURN'):
    xy=lambda p:(p[1],p[0]) if rotate else p
    b=_board([(*xy((6,6)),net)],edge=(0,0,12,12));b.SetCopperLayerCount(6)
    old=track(b,net,xy((6,6)),xy((5.35,6)),layer=face);old.SetWidth(300000)
    original={force._uid(t) for t in b.GetTracks()}
    v=pcbnew.PCB_VIA(b);v.SetNet(old.GetNet());v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(500000);v.SetDrill(300000)
    v.SetPosition(pcbnew.VECTOR2I_MM(*xy((5.27,6))));b.Add(v)
    new=track(b,net,xy((6,6)),xy((5.27,6)),layer=face);new.SetWidth(200000);new.SetLocked(True)
    return b,old,v,new,original


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
def test_new_bridge_can_be_covered_by_two_retained_bodies_with_all_drills_fixed(face,rotate):
    b,old,via,new,ids=fixture(face,rotate);uid=force._uid(new)
    before=field._field_snapshot_inventory(b);p=echo.compact(b,ids)
    assert p['removed']==[uid] and p['board_mutated'],p
    after=field._field_snapshot_inventory(b)
    assert set(before)-set(after)=={('track',uid)}
    assert all(before[k]==after[k] for k in after)
    assert not p['release_authority'] and p['proofs'][0]['fixed_global_holes_subtracted_identically']


@pytest.mark.parametrize('mode',['source_item','mask','group','foreign_net','undersized_land',
    'conditional_land','narrow_receiver','offset','too_long','missing_original'])
def test_new_scope_never_grants_source_mask_group_or_clearance_authority(mode):
    b,old,via,new,ids=fixture()
    if mode=='source_item':ids.add(force._uid(new))
    elif mode=='mask':new.SetHasSolderMask(True)
    elif mode=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(new)
    elif mode=='foreign_net':
        n=pcbnew.NETINFO_ITEM(b,'/OTHER');b.Add(n);via.SetNet(n)
    elif mode=='undersized_land':via.SetWidth(200000)
    elif mode=='conditional_land':via.SetRemoveUnconnected(True)
    elif mode=='narrow_receiver':old.SetWidth(200000)
    elif mode=='offset':new.Move(pcbnew.VECTOR2I(0,180000))
    elif mode=='too_long':new.SetStart(pcbnew.VECTOR2I_MM(8,6))
    else:ids.add('not-an-actual-source-uuid')
    before=field._field_snapshot_inventory(b)
    if mode in ('missing_original','foreign_net'):
        with pytest.raises((ValueError,field._ProposalUnknown)):echo.compact(b,ids)
    else:
        p=echo.compact(b,ids);assert not p['removed'],p
    assert before==field._field_snapshot_inventory(b)


def test_shared_additive_emitter_invokes_new_only_compaction_before_saving(tmp_path):
    import cec_additive_pair_repair as emitter
    b,old,via,new,ids=fixture(net='GND');uid=force._uid(new);survivors={force._uid(old),force._uid(via)}
    path=tmp_path/'board.kicad_pcb';r={}
    emitter.save_native_additions(path,b,r,ids,board_hint='synthetic')
    assert r['new_native_body_echo_compaction']['removed']==[uid]
    saved=pcbnew.LoadBoard(str(path))
    assert {force._uid(t) for t in saved.GetTracks()}==survivors


@pytest.mark.parametrize('mode',['mask','group'])
def test_ineligible_native_features_are_refused_before_any_save_reload(monkeypatch,mode):
    b,old,via,new,ids=fixture()
    if mode=='mask':new.SetHasSolderMask(True)
    else:g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(new)
    before=field._field_snapshot_inventory(b)
    def forbidden(*args,**kwargs):raise AssertionError('ineligible_native_geometry_must_not_be_serialized')
    monkeypatch.setattr(echo.field,'_save_field_snapshot',forbidden)
    r=echo.compact(b,ids)
    assert not r['removed'] and not r['board_mutated']
    assert r['reason']=='no_eligible_plain_new_track_before_serialization'
    assert before==field._field_snapshot_inventory(b)
