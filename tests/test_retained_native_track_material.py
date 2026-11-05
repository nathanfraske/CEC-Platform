"""Real retained conductors are not fictitious fill or extra ampacity.

The explicit mode distinguishes partial keeper coverage from destruction of
original native copper. It must preserve every original item and filled region,
replay the actual fill, and leave any exposed contour visible to its own audit.
"""
import copy

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_native_keeper_extension_receiving as extension
import cec_power_contours as contours
import cec_rectilinear_copper as owner
import cec_regional_fill as regional
from test_native_landing_union import keeper_setup


def fixture(tmp_path, angle=0, mirror=False, layer=pcbnew.F_Cu, *, retained=True):
    b,t,z,at=keeper_setup(angle=angle,mirror=mirror,layer=layer)
    t.SetStart(at(2,0));t.SetEnd(at(3.9,0))
    pads=[p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==t.GetNetname()]
    pads[0].SetPosition(at(3.9,0));pads[0].SetSize(pcbnew.VECTOR2I_MM(.4,.4))
    # A real unchanged foreign conductor exactly one factory clearance away.
    # KiCad's native fill safety margin may trim the proposed new fill, but
    # cannot delete this source track's already existing physical material.
    foreign=pcbnew.PCB_TRACK(b);foreign.SetNet(b.FindNet('/RENAMED_FOREIGN'))
    foreign.SetLayer(layer);foreign.SetWidth(200000)
    foreign.SetStart(at(2.8,-.8));foreign.SetEnd(at(4.2,-.8));b.Add(foreign)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(child))
    plan=extension.plan(c,[force._uid(t)],required_width_nm=t.GetWidth(),
        retained_native_track_material=retained)
    emitted=owner.materialize(c,plan);before=pcbnew.LoadBoard(str(source))
    owner.fill(c,plan,emitted['zone_uuid'],regional_source=before)
    additive._ground_refill(c);field._save_field_snapshot(c,child)
    return source,child,plan,emitted


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_material_and_partial_fill_are_separate_exact_observations(tmp_path,angle,mirror,layer):
    source,child,plan,emitted=fixture(tmp_path,angle,mirror,layer)
    original=source.read_bytes();saved=pcbnew.LoadBoard(str(child));before=pcbnew.LoadBoard(str(source))
    proof=owner.receive(saved,plan,emitted['zone_uuid'],regional_source=before,timeout_s=10.)
    assert proof['ok'] and proof['complete'],proof
    assert proof['retained_native_track_material_used']
    assert not proof['missing_source_tracks']
    assert proof['keeper_fill_only_missing_source_tracks']
    assert not proof['keeper_fill_only_encloses_all_source_tracks']
    assert proof['original_native_keeper_fill_preserved']
    assert not proof['fill_only_capacity_qualified'] and not proof['all_power_contours_clean']
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    witnesses,replayed=owner.enclosed_track_witnesses(saved,plan,emitted['zone_uuid'],
        regional_source=before,timeout_s=10.)
    assert witnesses==[] and replayed['ok']
    strict=copy.deepcopy(plan);strict.pop('retained_native_track_material');strict.pop('plan_sha256')
    strict['plan_sha256']=owner._digest(strict)
    rejected=owner.receive(saved,strict,emitted['zone_uuid'],regional_source=before,timeout_s=10.)
    assert not rejected['ok'] and rejected['complete'] and rejected['reason']=='native_conductor_loss'
    audit=contours.audit_board(saved,timeout_s=10.,max_length_width_ratio=2.)
    assert audit['complete'] and audit['finding_count']>0,audit
    literal=extension.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],
        board_hint='synthetic')
    assert literal['ok'] and literal['complete'],literal
    assert not literal['new_capacity_credited'] and not literal['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['retire','no_keeper','native_fill','recompile','nonbool'])
def test_retained_material_is_not_a_general_enclosure_waiver(fault):
    b,t,z,_=keeper_setup()
    kw=dict(required_width_nm=t.GetWidth(),clearance_nm=z.GetLocalClearance(),
        min_thickness_nm=z.GetMinThickness(),retire_source_tracks=False,
        replace_native_zone_uuid=force._uid(z),enclosing_native_zone_uuids=[force._uid(z)],
        fill_policy='source_preserving_regions',retained_native_track_material=True)
    if fault=='retire':kw['retire_source_tracks']=True
    elif fault=='no_keeper':kw['replace_native_zone_uuid']=None
    elif fault=='native_fill':kw['fill_policy']='native'
    elif fault=='recompile':kw['rebuild_keeper_from_tracks']=True
    else:kw['retained_native_track_material']=1
    with pytest.raises(owner.Refused):owner.plan(b,[force._uid(t)],**kw)


@pytest.mark.parametrize('fault',['removed','width','pose','net','layer','lock','old_fill',
    'forged_fill','forged_flag'])
def test_changed_or_missing_actual_source_copper_is_still_refused(tmp_path,fault):
    source,child,plan,emitted=fixture(tmp_path)
    c=pcbnew.LoadBoard(str(child));before=pcbnew.LoadBoard(str(source))
    t=next(t for t in c.GetTracks() if force._uid(t)==plan['source_tracks'][0]['uuid'])
    z=next(z for z in c.Zones() if force._uid(z)==emitted['zone_uuid'])
    if fault=='removed':c.Remove(t)
    elif fault=='width':t.SetWidth(t.GetWidth()+1)
    elif fault=='pose':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='net':t.SetNet(c.FindNet('/RENAMED_FOREIGN'))
    elif fault=='layer':t.SetLayer(pcbnew.B_Cu)
    elif fault=='lock':t.SetLocked(not t.IsLocked())
    elif fault=='old_fill':
        z.SetFilledPolysList(pcbnew.F_Cu,owner._poly([(30000000,30000000),(31000000,30000000),
            (31000000,31000000),(30000000,31000000)]))
    elif fault=='forged_fill':
        fill=z.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        ring=fill.Outline(0);p=ring.CPoint(0);ring.SetPoint(0,pcbnew.VECTOR2I(p.x+1,p.y))
        z.SetFilledPolysList(pcbnew.F_Cu,fill)
    else:
        plan['retained_native_track_material']=1;plan.pop('plan_sha256');plan['plan_sha256']=owner._digest(plan)
    proof=owner.receive(c,plan,emitted['zone_uuid'],regional_source=before,timeout_s=10.)
    assert not proof['ok'] and not proof['complete'],proof
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    # Deliberately malformed input: the normal snapshot writer itself refuses
    # some net-table mutations. Use raw native serialization only to exercise
    # the independent receiver against that adversarial file as well.
    assert pcbnew.SaveBoard(str(child),c)
    literal=extension.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],board_hint='synthetic')
    assert not literal['ok'] and not literal['complete'],literal


@pytest.mark.parametrize('bad',[{},dict(ok=False),dict(ok=True),
    dict(ok=True,independently_replayed_native_additions=True,exact_source_copper_preserved=False)])
def test_unconfirmed_regional_replay_never_becomes_positive(tmp_path,monkeypatch,bad):
    source,child,plan,emitted=fixture(tmp_path)
    saved=pcbnew.LoadBoard(str(child));before=pcbnew.LoadBoard(str(source))
    monkeypatch.setattr(regional,'receive',lambda *a,**kw:bad)
    proof=owner.receive(saved,plan,emitted['zone_uuid'],regional_source=before,timeout_s=10.)
    assert not proof['ok'] and not proof['complete']
    assert proof['reason']=='retained_material_native_regional_replay_refused'
