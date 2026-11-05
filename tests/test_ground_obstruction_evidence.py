"""The first pad-center failure must not erase later native barrel blockers."""
import json
import pcbnew
import pytest
import cec_decoupler_cell as cell
import cec_fr as fr


def admission(blocker,point=(7.,8.)):
    return dict(ok=False,at_mm=list(point),layer='In3.Cu',blockers=[blocker])


@pytest.mark.parametrize('tier',['ordinary','compact'])
def test_locked_dogbone_blocker_routes_certificate_to_owner_even_if_center_is_only_pad(tier):
    blocker=dict(kind='track',net='/renamed/rail',uuid='native-track',locked=True,layer='B.Cu')
    detail=dict(pad_center=dict(copper_admission=admission(
        dict(kind='pad',ref='OTHER',pad='named pin',net='GND',uuid='native-pad'))))
    dogbone=dict(search_exhausted=True,dogbone_candidates=[dict(copper_admission=admission(blocker))])
    if tier=='ordinary':detail.update(dogbone)
    else:detail['compact_dogbone_attempts']=[dict(error='measured blocked barrel',evidence=dogbone)]
    encoded=json.dumps(detail,sort_keys=True)
    result=cell._ground_obstruction_evidence(detail)
    assert result['protected_blocker_uuids']==['native-track']
    assert result['repair_stage']=='upstream_owned_copper_replan'
    assert {row['blocker']['uuid'] for row in result['blocking_native_objects']}=={'native-track','native-pad'}
    assert not result['no_path_proof'] and not result['blocker_mutation_authorized']
    assert json.dumps(detail,sort_keys=True)==encoded


def test_measurement_retains_duplicate_site_provenance_and_sampling_limit():
    blocker=dict(kind='track',net='OTHER',uuid='same-native',locked=True)
    seats=[dict(copper_admission=admission(blocker,(x,8.))) for x in range(32)]
    detail=dict(dogbone_candidates=seats,dogbone_candidates_truncated=48)
    result=cell._ground_obstruction_evidence(detail)
    assert result['measured_failed_sites']==16 and result['measured_blocker_objects']==1
    assert len(result['blocking_native_objects'][0]['observed_in'])==16
    assert result['ground_seat_samples_truncated']==48
    assert result['protected_blocker_uuids']==['same-native'] and not result['no_path_proof']


def test_temporary_cell_ownership_remains_distinct_from_inherited_authority():
    detail=dict(dogbone_candidates=[dict(copper_admission=admission(
        dict(kind='track',net='V',uuid='temporary',locked=True)))])
    detail.update(cell._ground_obstruction_evidence(detail))
    cell._cell_blocker_provenance(detail,{'source'},{'temporary'})
    assert detail['protected_blocker_uuids']==[]
    assert detail['tentative_blocker_uuids']==['temporary']
    assert detail['repair_stage']=='coupled_cell_replan'
    assert detail['blocking_native_objects'][0]['blocker']['ownership_origin']=='tentative_cell_copper'


def test_native_pad_exclusion_has_exact_identity_and_layers():
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'GND');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('renamed');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('ground');pad.SetNet(net)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    pad.SetPosition(pcbnew.VECTOR2I_MM(10.,10.));fp.Add(pad)
    detail={}
    assert not fr._via_spot_clear(board,pad.GetPosition(),pcbnew.FromMM(.6),
        pcbnew.FromMM(.2),{net.GetNetCode()},drill_nm=pcbnew.FromMM(.3),
        net_code=net.GetNetCode(),report=detail)
    row=detail['blockers'][0]
    assert row['uuid']==pad.m_Uuid.AsString() and row['footprint_uuid']==fp.m_Uuid.AsString()
    assert row['layers']==['F.Cu'] and row['contact']=='via_land_exclusion'
    assert not list(board.GetTracks())
