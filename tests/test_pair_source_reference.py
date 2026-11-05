"""Source-only own-via void attribution, not general plane-gap permission."""
from pathlib import Path
import json
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pair_fixed_port_shortening as worker
import cec_pair_source_reference as context
from cec_native_items import discard_items
from test_pair_fixed_port_shortening import four_kernels,kernel_groups
from test_pair_axis_miter import fixture


def endpoint_void_fixture(tmp_path,*,crossface=False,quarter=0,foreign=False,endpoint_kind='via'):
    source,child,groups=four_kernels(tmp_path,crossface=crossface)
    boards=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    for x in (12.8,13.8):
        net=boards[0].FindNet('+5V' if foreign else '/renamed/cell/CAN_L')
        if endpoint_kind=='via':
            v=pcbnew.PCB_VIA(boards[0]);v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetPosition(pcbnew.VECTOR2I_MM(x,12.45));v.SetWidth(500000);v.SetDrill(300000)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(net)
            boards[0].Add(v);copy=v.Duplicate();copy.m_Uuid.Clone(pcbnew.KIID(force._uid(v)));boards[1].Add(copy)
        else:
            fp=pcbnew.FOOTPRINT(boards[0]);fp.SetReference('JENTRY'+str(round(x*10)));fp.SetValue('SOURCE_PLATED_TERMINAL')
            pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetLayerSet(pcbnew.PAD.PTHMask());pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x,12.45));pad.SetNet(net);fp.Add(pad);boards[0].Add(fp)
            copy=pcbnew.Cast_to_FOOTPRINT(fp.Duplicate(False));copy.m_Uuid.Clone(pcbnew.KIID(force._uid(fp)))
            for original,clone in zip([*fp.GetFields(),*fp.Pads()],[*copy.GetFields(),*copy.Pads()]):
                clone.m_Uuid.Clone(pcbnew.KIID(force._uid(original)))
            boards[1].Add(copy)
    for b,path in zip(boards,(source,child)):
        if quarter:
            for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*b.Zones()]:
                item.Rotate(pcbnew.VECTOR2I_MM(11,11),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        additive._ground_refill(b);field._save_field_snapshot(b,path)
    return source,child,groups


@pytest.mark.parametrize('crossface',[False,True])
@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('endpoint_kind',['via','pad'])
def test_actual_unchanged_endpoint_void_is_rederived_without_filling_candidate(tmp_path,crossface,quarter,endpoint_kind):
    source,child,groups=endpoint_void_fixture(tmp_path,crossface=crossface,quarter=quarter,endpoint_kind=endpoint_kind)
    frozen=[p.read_bytes() for p in (source,child)]
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups,
        reference_mode='native_source_reference_context')
    assert r['ok'] and r['complete'],r
    proof=r['exact_native_reference_deficit_receiving'];references=list(proof.get('by_signal_face',{}).values()) or [proof]
    kernels=[k for ref in references for k in ref['kernels']]
    local=[k for k in kernels if k['existing_endpoint_voids']]
    assert len(local)==2
    assert all(k['exact_reference_length_comparison']['ok'] for k in local)
    assert all(k['exact_context_and_endpoint_void_cover']['ok'] for k in local)
    assert all(ref['native_candidate_reference_fill_unchanged'] and ref['diagnostic_refills_never_saved_to_candidate'] for ref in references)
    assert all(ref['new_plane_holes']==ref['new_vias']==0 for ref in references)
    assert [p.read_bytes() for p in (source,child)]==frozen
    assert not r['pair_qualified'] and not r['release_authority']


def test_old_strict_mode_does_not_infer_a_via_void_exclusion(tmp_path):
    source,child,groups=endpoint_void_fixture(tmp_path)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups)
    assert not r['ok'] and any('new_native_unreferenced_pair_copper' in e for e in r['errors']),r


def test_unrelated_reference_hole_is_not_an_own_endpoint_void(tmp_path):
    source,child,made=fixture(tmp_path,reference_hole=True)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',
        kernel_track_uuids=kernel_groups(source,made['retired_track_uuids']),reference_mode='native_source_reference_context')
    assert not r['ok'] and not r['complete'],r
    assert any('same_net_source_endpoint_barrel_required' in e for e in r['errors']),r


@pytest.mark.parametrize('fault',['via_move','via_drill','via_net','reference_fill','sidecar','pose','non45'])
def test_mode_never_authorizes_a_new_hole_or_changed_source_family(tmp_path,fault):
    source,child,groups=endpoint_void_fixture(tmp_path);b=pcbnew.LoadBoard(str(child))
    via=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname().endswith('CAN_L'))
    old_ids={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    if fault=='via_move':via.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='via_drill':via.SetDrill(200000)
    elif fault=='via_net':via.SetNet(b.FindNet('+5V'))
    elif fault=='reference_fill':
        zone=next(z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND');zone.UnFill()
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='non45':
        t=next(t for t in b.GetTracks() if force._uid(t) not in old_ids);t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    if fault=='via_net':pcbnew.SaveBoard(str(child),b)
    elif fault!='sidecar':field._save_field_snapshot(b,child)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',kernel_track_uuids=groups,
        reference_mode='native_source_reference_context')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r


@pytest.mark.parametrize('mode',[True,None,1,'exclude_every_void',''])
def test_unknown_or_coerced_reference_mode_is_never_admission(tmp_path,mode):
    source,child,made=fixture(tmp_path)
    r=worker.receive_literal_phase(source,child,board_hint='synthetic',pair_name='CAN',
        kernel_track_uuids=kernel_groups(source,made['retired_track_uuids']),reference_mode=mode)
    assert not r['ok'] and not r['complete'] and r['errors'],r


def test_hull_check_is_integer_exact_and_does_not_accept_a_one_nm_excursion():
    hull=context._hull([[0,0],[200000,200000],[400000,0]])
    assert context._hull_contains(hull,[200000,0])
    assert not context._hull_contains(hull,[200000,-1])


@pytest.mark.parametrize('crossface',[False,True])
def test_pipeline_receives_explicit_source_endpoint_context_independently(tmp_path,crossface):
    import cec_source_cut_chain as chain
    source,child,groups=endpoint_void_fixture(tmp_path,crossface=crossface)
    phase=dict(kind='paired_fixed_port_shortening',candidate=str(child),pair_name='CAN',
        kernel_track_uuids=groups,reference_mode='native_source_reference_context')
    r=chain.receive(source,child,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert r['ok'] and r['complete'],r
    proof=r['phase_receiving'][0]['proof']
    assert proof['reference_mode']=='native_source_reference_context'
    assert proof['exact_native_reference_deficit_receiving']['ok']
    assert not proof['pair_qualified'] and not r['release_authority']
