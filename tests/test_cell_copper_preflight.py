"""Cell placements must see actual retained copper, across every layer."""
import copy

import pcbnew
import pytest
import cec_cell_copper_preflight as probe
import cec_field_coupling as field


def fixture(*,layer=pcbnew.F_Cu,via=False,pad_net='CELL',copper_net='FIXED'):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    nets={}
    for name in {pad_net,copper_net}:
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    f=pcbnew.FOOTPRINT(b);f.SetReference('UNRELATED_NAME');f.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    p=pcbnew.PAD(f);p.SetNumber('77');p.SetPosition(f.GetPosition())
    p.SetSize(pcbnew.VECTOR2I_MM(.7,.7));p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
    p.SetNet(nets[pad_net]);f.Add(p);b.Add(f)
    if via:
        t=pcbnew.PCB_VIA(b);t.SetPosition(pcbnew.VECTOR2I_MM(10,10))
        t.SetWidth(600000);t.SetDrill(300000);t.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    else:
        t=pcbnew.PCB_TRACK(b);t.SetLayer(layer);t.SetStart(pcbnew.VECTOR2I_MM(9,10))
        t.SetEnd(pcbnew.VECTOR2I_MM(11,10));t.SetWidth(250000)
    t.SetNet(nets[copper_net]);t.SetLocked(True);b.Add(t)
    return b,f,t


@pytest.mark.parametrize('via',[False,True])
def test_native_overlap_reports_real_object_and_never_changes_material(via):
    b,f,t=fixture(via=via);before=field._field_snapshot_inventory(b)
    r=probe.check(b,[f.GetReference()],retained_uuids=[t.m_Uuid.AsString()])
    assert not r['ok'] and r['complete']
    assert r['conflicts'][0]['conductor_uuid']==t.m_Uuid.AsString()
    assert r['conflicts'][0]['overlap']
    assert before==field._field_snapshot_inventory(b)
    assert not r['routing_admitted'] and not r['release_authority']


@pytest.mark.parametrize('layer',[pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu,pcbnew.B_Cu])
def test_opposite_or_inner_track_is_not_a_front_smd_keepout(layer):
    b,f,t=fixture(layer=layer)
    assert probe.check(b,[f.GetReference()],retained_uuids=[t.m_Uuid.AsString()])['ok']


def test_clearance_without_short_is_not_ignored():
    b,f,t=fixture();f.Move(pcbnew.VECTOR2I_MM(0,.65))
    r=probe.check(b,[f.GetReference()],retained_uuids=[t.m_Uuid.AsString()],clearance_nm=200000)
    assert not r['ok'] and all(not q['overlap'] for q in r['conflicts'])


def test_same_net_contact_is_no_current_or_route_qualification():
    b,f,t=fixture(pad_net='SAME',copper_net='SAME')
    r=probe.check(b,[f.GetReference()],retained_uuids=[t.m_Uuid.AsString()])
    assert r['ok'] and r['requires_zone_refill_hole_mask_current_and_whole_board_receiving']
    assert not r['release_authority'] and not r['routing_admitted']


def test_cell_contact_search_restores_all_original_poses_and_copper():
    b,f,t=fixture(via=True);before=field._field_snapshot_inventory(b)
    r=probe.translation_menu(b,[f.GetReference()],retained_uuids=[t.m_Uuid.AsString()],
        bounds_mm=(-2,-2,2,2))
    assert r['ok'] and r['trials']>0 and r['delta_mm']!=[0.,0.]
    assert before==field._field_snapshot_inventory(b)
    assert probe.pose_trial(b,[f.GetReference()],r['delta_mm'],
        retained_uuids=[t.m_Uuid.AsString()])['ok']


@pytest.mark.parametrize('fault',['missing_ref','missing_copper','duplicate_ref','duplicate_copper','locked','budget'])
def test_missing_protected_or_exhausted_evidence_refuses(fault):
    b,f,t=fixture();refs=[f.GetReference()];ids=[t.m_Uuid.AsString()]
    if fault=='missing_ref':refs=['ABSENT']
    elif fault=='missing_copper':ids=['NOT_A_NATIVE_UUID']
    elif fault=='duplicate_ref':refs*=2
    elif fault=='duplicate_copper':ids*=2
    elif fault=='locked':f.SetLocked(True)
    before=field._field_snapshot_inventory(b)
    if fault=='budget':
        extra=pcbnew.PCB_TRACK(b);extra.SetStart(t.GetStart());extra.SetEnd(t.GetEnd())
        extra.SetWidth(250000);extra.SetNetCode(t.GetNetCode());b.Add(extra)
        r=probe.check(b,refs,retained_uuids=[*ids,extra.m_Uuid.AsString()],max_checks=1)
        assert not r['ok'] and not r['complete'] and r['errors']
        return
    with pytest.raises(ValueError):
        probe.pose_trial(b,refs,(0.,.1),retained_uuids=ids)
    assert before==field._field_snapshot_inventory(b)


def test_through_hole_land_sees_inner_copper():
    b,f,t=fixture(layer=pcbnew.In4_Cu)
    p=next(iter(f.Pads()));p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetLayerSet(pcbnew.PAD.PTHMask())
    r=probe.check(b,[f.GetReference()],retained_uuids=[t.m_Uuid.AsString()])
    assert not r['ok'] and any(q['layer']==b.GetLayerName(pcbnew.In4_Cu) for q in r['conflicts'])
