"""Saved whole-phase owner replay, not cosmetic flags or decreasing counters."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rectilinear_copper as owner
from test_owned_keeper_recompile import setup, plan
from test_native_publication_safety import fixture as grade_fixture
from root_native_keeper_recompile_receiving_20261012 import receive
from root_native_publication_safety_20261012 import require_saved_grade


def saved(tmp_path, *, angle=0, layer=pcbnew.F_Cu, stray=False):
    b, ts, z = setup(angle=angle, layer=layer)
    if stray:
        fp = pcbnew.FOOTPRINT(b); b.Add(fp)
        pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNet(ts[0].GetNet())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
        pad.SetPosition(pcbnew.VECTOR2I_MM(29,34));pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
        b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    for index, fp in enumerate(b.GetFootprints()):
        fp.SetReference('NODE' + str(index + 1))
        for pin, pad in enumerate(fp.Pads()): pad.SetNumber(str(pin + 1))
    source=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    field._save_field_snapshot(b,source)
    original=pcbnew.LoadBoard(str(source))
    p=plan(b,ts,z,contour_style='chamfer45',fill_policy='conductor_preserving_regions',
           fill_envelope_margin_nm=4)
    emitted=owner.materialize(b,p)
    owner.fill(b,p,emitted['zone_uuid'],regional_source=original,timeout_s=10.)
    field._save_field_snapshot(b,child)
    return source,child,[dict(plan=p,materialized=emitted)]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_cardinal_cross_face_keeper_replay(tmp_path,angle,layer):
    source,child,contours=saved(tmp_path,angle=angle,layer=layer)
    old=(source.read_bytes(),child.read_bytes())
    proof=receive(source,child,contours,board_hint='explicit-fixture')
    assert proof['ok'] and proof['complete'],proof
    assert proof['exact_native_owner_recompile_and_ground_refill_received']
    assert proof['all_source_native_conductor_partitions_preserved']
    assert all(p['native_port_uuids'] for p in proof['retained_native_keeper_ports'])
    assert not proof['release_authority'] and not proof['new_capacity_credited']
    assert not proof['coupled_thermal_qualified']
    assert old==(source.read_bytes(),child.read_bytes())


def test_an_untracked_incumbent_native_terminal_cannot_be_discarded(tmp_path):
    source,child,contours=saved(tmp_path,stray=True)
    proof=receive(source,child,contours,board_hint='explicit-fixture')
    assert not proof['ok'] and not proof['complete']
    assert any('incumbent_keeper_native_port_lost' in e for e in proof['errors']),proof


@pytest.mark.parametrize('fault',['empty','duplicate','wrong_source','retire','new_owner','unlisted_track','moved_pad'])
def test_worker_claims_do_not_cover_unreceived_source_changes(tmp_path,fault):
    source,child,contours=saved(tmp_path);contours=copy.deepcopy(contours)
    if fault=='empty':contours=[]
    elif fault=='duplicate':contours*=2
    elif fault=='wrong_source':contours[0]['plan']['replacement_source_zone']['outline_nm'][0][0]+=1
    elif fault=='retire':contours[0]['plan']['retire_source_tracks']=True
    elif fault=='new_owner':contours[0]['materialized']['zone_uuid']='unreceived-new-zone'
    else:
        b=pcbnew.LoadBoard(str(child))
        if fault=='unlisted_track':
            t=next(iter(b.GetTracks())).Duplicate();b.Add(t)
        else:
            pad=next(p for fp in b.GetFootprints() for p in fp.Pads())
            pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I_MM(1,0))
        field._save_field_snapshot(b,child)
    proof=receive(source,child,contours,board_hint='explicit-fixture')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert not proof['release_authority']


def test_even_unchanged_raw_kelvin_counters_require_actual_keeper_replay_to_publish(tmp_path):
    source,child,contours=saved(tmp_path)
    grade=grade_fixture();epoch=force._code_identity()
    grade['code_identity']=epoch
    before,after=force._hash(source),force._hash(child)
    grade['boards']['source']['sha256']=before;grade['boards']['candidate']['sha256']=after
    construction=dict(contour_phase='typed_owned_keeper_recompile',source=str(source),candidate=str(child),
        source_sha256=before,candidate_sha256=after,contours=[],independent_fresh_keeper_receiving={'ok':True,'complete':True})
    with pytest.raises(ValueError,match='independent_fresh_keeper_requalification_refused'):
        require_saved_grade(grade,epoch=epoch,source_sha256=before,candidate_sha256=after,
                            contour_construction=construction,board_hint='explicit-fixture')
