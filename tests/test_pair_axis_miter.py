"""Native fixed-port balanced miters; inherited debt is not qualification."""
import json
import math
from pathlib import Path
import pcbnew
import pytest
import cec_pair_axis_miter as worker
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, angle=0, mirror=False, power_face=False, signal_face='F.Cu', reference_hole=False):
    pn, nn = '/renamed/cell/CAN_H', '/renamed/cell/CAN_L'
    b = _board([(11,8.8,pn),(15,11.6,pn),(8.5,8.8,nn),(15,12.45,nn)],edge=(0,0,22,22))
    b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for fp in b.GetFootprints():
        p=list(fp.Pads())[0];p.SetNumber('1');p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetLayerSet(pcbnew.PAD.PTHMask());p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    face=pcbnew.In3_Cu if power_face else b.GetLayerID(signal_face)
    primary=[(10,10),(10,12),(12,12)]
    partner=[(9.55,10),(9.55,12.25),(9.75,12.45),(12,12.45)]
    for net,points in ((pn,primary),(nn,partner)):
        for s,z in zip(points,points[1:]):track(b,net,s,z,layer=face,width=.25)
    for s,z in zip([(11,8.8),(10,9.8),(10,10)],[(10,9.8),(10,10)]):track(b,pn,s,z,layer=face,width=.25)
    for s,z in zip([(8.5,8.8),(9.55,9.85),(9.55,10)],[(9.55,9.85),(9.55,10)]):track(b,nn,s,z,layer=face,width=.25)
    for s,z in zip([(12,12),(14,12),(14.4,11.6)],[(14,12),(14.4,11.6),(15,11.6)]):track(b,pn,s,z,layer=face,width=.25)
    track(b,nn,(12,12.45),(15,12.45),layer=face,width=.25)
    track(b,'+5V',(5,16),(15,16),width=1.)
    ground=pcbnew.NETINFO_ITEM(b,'GND');b.Add(ground)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetNet(ground);z.SetLayer(layer)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER);z.SetLocalClearance(200000);z.SetMinThickness(100000)
        z.Outline().NewOutline()
        for x,y in [(1,1),(21,1),(21,21),(1,21)]:z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
        if reference_hole:
            keep=pcbnew.ZONE(b);keep.SetLayer(layer);keep.SetIsRuleArea(True);keep.SetDoNotAllowZoneFills(True)
            keep.Outline().NewOutline()
            for x,y in [(10.05,11.60),(10.30,11.60),(10.30,11.90),(10.05,11.90)]:keep.Outline().Append(round(x*1e6),round(y*1e6))
            b.Add(keep)
    origin=pcbnew.VECTOR2I_MM(11,11)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*b.Zones()]:
        if angle:item.Rotate(origin,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if mirror:
        # Reflect native geometry, not footprint-side/text serialization.
        # Round through lands and the square outline are reflection invariant.
        for fp in b.GetFootprints():
            at=fp.GetPosition();fp.SetPosition(pcbnew.VECTOR2I(22000000-at.x,at.y))
        for t in b.GetTracks():
            start,end=t.GetStart(),t.GetEnd()
            t.SetStart(pcbnew.VECTOR2I(22000000-start.x,start.y))
            t.SetEnd(pcbnew.VECTOR2I(22000000-end.x,end.y))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='CAN',diff_pair_width=.25,diff_pair_gap=.2,track_width=.25,clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='Default',track_width=.25,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    # Bind the saved project before freezing the source's literal reference
    # sheets. An unsaved BOARD otherwise uses native default clearances.
    b=pcbnew.LoadBoard(str(source));additive._ground_refill(b);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));pair=next(p for p in worker.owner.precision.derive_coupled_pairs(str(source),board=b) if p['name']=='CAN')
    requests=worker.discover(b,source,pair);assert len(requests)==1,requests
    made=worker.construct(b,source,pair,requests[0],140000)
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    return source,child,made


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('source_face',['F.Cu','B.Cu','In2.Cu','In3.Cu'])
def test_real_native_balanced_miter_keeps_skew_and_all_original_material(tmp_path,angle,mirror,source_face):
    power_face=source_face=='In3.Cu'
    source,child,made=fixture(tmp_path,angle,mirror,power_face,source_face)
    before=[p.read_bytes() for p in (source,child)]
    r=worker.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=made['retired_track_uuids'],retreat_nm=140000,
        allow_existing_non_signal_face=power_face)
    assert r['ok'] and r['complete'],r
    assert r['eligible_hard90_before_after']==[1,0]
    assert r['algebra']['exact_skew_unchanged'] and r['continuous_coupling']['ok']
    assert r['exact_native_pair_completion']['connected']
    if power_face:
        reference=r['reference_copper_preservation']
        assert reference['unsupported_source_role_retained_as_unqualified_debt']
        assert not reference['profile_signal_face_qualified'] and not reference['pair_qualified']
    assert not r['pair_qualified'] and not r['fab_ready'] and not r['release_authority']
    assert [p.read_bytes() for p in (source,child)]==before


@pytest.mark.parametrize('fault',['wrong_scope','retreat','thin','new_face','new_via','pose','power',
    'lock','unbalanced','missing_member','sidecar','missing_explicit_debt_mode','unknown_debt_mode'])
def test_draft_comparison_never_authorizes_other_source_changes(tmp_path,fault):
    source,child,made=fixture(tmp_path,power_face=True)
    b=pcbnew.LoadBoard(str(child));retired=made['retired_track_uuids'][:];retreat=140000
    options=dict(allow_existing_non_signal_face=True)
    incoming=[t for t in b.GetTracks() if force._uid(t) in made['incoming_track_uuids']]
    if fault=='wrong_scope':retired.pop()
    elif fault=='retreat':retreat=150000
    elif fault=='missing_explicit_debt_mode':options={}
    elif fault=='unknown_debt_mode':options['allow_existing_non_signal_face']=1
    elif fault=='thin':incoming[0].SetWidth(200000)
    elif fault=='new_face':incoming[0].SetLayer(pcbnew.In2_Cu)
    elif fault=='lock':incoming[0].SetLocked(not incoming[0].IsLocked())
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='power':next(t for t in b.GetTracks() if t.GetNetname()=='+5V').SetWidth(900000)
    elif fault=='unbalanced':incoming[0].SetEnd(incoming[0].GetEnd()+pcbnew.VECTOR2I(10000,0))
    elif fault=='missing_member':
        from cec_native_items import discard_items
        discard_items(b,[incoming[0]])
    elif fault=='new_via':
        via=pcbnew.PCB_VIA(b);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(pcbnew.VECTOR2I_MM(18,18));via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(b.FindNet(incoming[0].GetNetname()));b.Add(via)
    else:child.with_suffix('.kicad_pro').write_text('{}')
    if fault=='new_via':
        # Deliberately hostile native file from an untrusted producer. Do
        # not rely on the safe writer rejecting it before receiving runs.
        pcbnew.SaveBoard(str(child),b)
    elif fault not in ('wrong_scope','retreat','missing_explicit_debt_mode','unknown_debt_mode','sidecar'):
        field._save_field_snapshot(b,child)
    frozen=source.read_bytes()
    r=worker.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=retired,retreat_nm=retreat,**options)
    assert not r['ok'] and not r['complete'] and r['errors'],r
    assert source.read_bytes()==frozen and not r['release_authority']


@pytest.mark.parametrize('retreat',[True,0,19999,50000,139000,200001])
def test_no_invisible_miter_or_noninteger_radical_length_waiver(retreat):
    f=worker.frame([[10000000,10000000],[10000000,12000000],[12000000,12000000]],
        [[9550000,10000000],[9550000,12250000],[9750000,12450000],[12000000,12450000]],250000)
    with pytest.raises(ValueError):worker.replacements(f,retreat)


def test_typed_pipeline_chain_rederives_the_source_pair_operation(tmp_path):
    import cec_source_cut_chain as chain
    source,child,made=fixture(tmp_path,power_face=True)
    phase=dict(kind='paired_axis_miter',candidate=str(child),pair_name='CAN',
        retired_track_uuids=made['retired_track_uuids'],retreat_nm=140000,allow_existing_non_signal_face=True)
    r=chain.receive(source,child,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert r['ok'] and r['complete'],r
    proof=r['phase_receiving'][0]['proof']
    assert proof['eligible_hard90_before_after']==[1,0] and not proof['pair_qualified']
    assert not r['inherited_debt_qualified'] and not r['release_authority']


@pytest.mark.parametrize('fault',['extra','boolean','missing_mode','retreat'])
def test_cut_chain_does_not_infer_or_coerce_balanced_axis_modes(tmp_path,fault):
    import cec_source_cut_chain as chain
    source,child,made=fixture(tmp_path,power_face=True)
    phase=dict(kind='paired_axis_miter',candidate=str(child),pair_name='CAN',
        retired_track_uuids=made['retired_track_uuids'],retreat_nm=140000,allow_existing_non_signal_face=True)
    if fault=='extra':phase['skip_reference']=True
    elif fault=='boolean':phase['allow_existing_non_signal_face']=1
    elif fault=='missing_mode':del phase['allow_existing_non_signal_face']
    else:phase['retreat_nm']=True
    r=chain.receive(source,child,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert not r['ok'] and not r['complete'] and r['errors'],r


def test_explicit_inherited_role_mode_still_rejects_new_physical_reference_deficit(tmp_path):
    source,child,made=fixture(tmp_path,power_face=True,reference_hole=True)
    r=worker.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=made['retired_track_uuids'],retreat_nm=140000,
        allow_existing_non_signal_face=True)
    assert not r['ok'] and not r['complete']
    assert any('new_physical_unreferenced_pair_copper_not_permitted' in error for error in r['errors']),r
    assert not r['pair_qualified'] and not r['release_authority']
