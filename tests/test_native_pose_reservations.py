"""Source-native future lands are disposable obstacles, never pose authority."""
import time
from unittest import mock
import pcbnew
import pytest
import cec_native_pose_reservations as worker
import cec_native_fill_geometry as geometry
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board


def fixture(tmp_path,plated=False,rotation=0,renamed=False,face=pcbnew.F_Cu):
    net='/renamed/future' if renamed else '/foreign'
    b=_board([(10,10,net),(2,2,'/routing')],edge=(0,0,30,30))
    b.SetCopperLayerCount(6)
    fp=b.FindFootprintByReference('X1')
    fp.SetReference('renamed_part' if renamed else 'X1')
    fp.SetOrientationDegrees(rotation)
    pad=next(iter(fp.Pads()));pad.SetNumber('1')
    layers=pcbnew.LSET()
    if plated:
        layers=pcbnew.LSET.AllCuMask()
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    else:layers.AddLayer(face)
    pad.SetLayerSet(layers)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    b.SetFileName(str(source))
    return source,b,fp,net


@pytest.mark.parametrize('plated',[False,True])
@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('renamed',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_faces_rotations_and_renamed_identities_keep_source_and_remove_reservations(
        tmp_path,plated,rotation,renamed,face):
    source,b,fp,net=fixture(tmp_path,plated,rotation,renamed,face)
    saved=source.read_bytes();position=tuple(fp.GetPosition());angle=fp.GetOrientationDegrees()
    target={fp.GetReference():[12,11,rotation+90]}
    proposal=worker.plan(b,target)
    assert len(proposal['lands'])==(6 if plated else 1)
    assert len({r['layer'] for r in proposal['lands']})==len(proposal['lands'])
    assert all(r['net']==net and r['ref']==fp.GetReference() for r in proposal['lands'])
    assert all(geometry.reconstruct(r['polygons_nm'],time.monotonic()+1).OutlineCount()==1
               for r in proposal['lands'])
    assert not proposal['placement_qualified'] and not proposal['current_qualified']
    assert not proposal['release_authority'] and proposal['actual_pose_not_changed']
    old_zones=[force._uid(z) for z in b.Zones()]
    with worker.reserve(b,target,'/routing'):
        assert len(list(b.Zones()))==len(proposal['lands'])
        assert all(z.GetIsRuleArea() and z.GetDoNotAllowTracks() and z.GetDoNotAllowVias()
                   for z in b.Zones())
        assert all(not z.GetDoNotAllowFootprints() and not z.GetDoNotAllowZoneFills()
                   for z in b.Zones())
    assert [force._uid(z) for z in b.Zones()]==old_zones
    assert tuple(fp.GetPosition())==position and fp.GetOrientationDegrees()==angle
    assert source.read_bytes()==saved


def test_exception_and_same_net_reservations_never_persist(tmp_path):
    source,b,fp,net=fixture(tmp_path,True)
    saved=source.read_bytes();poses={fp.GetReference():[12,11,90]}
    with worker.reserve(b,poses,net):assert not list(b.Zones())
    with pytest.raises(RuntimeError,match='consumer failure'):
        with worker.reserve(b,poses,'/routing'):
            assert len(list(b.Zones()))==6
            raise RuntimeError('consumer failure')
    assert not list(b.Zones()) and source.read_bytes()==saved


@pytest.mark.parametrize('fault',['unknown_ref','noncardinal','boolean_coordinate','nan',
    'excessive_shift','boolean_scope','excessive_scope','empty','duplicate_reference',
    'unknown_route_net'])
def test_future_hints_have_no_scope_or_identity_waiver(tmp_path,fault):
    source,b,fp,net=fixture(tmp_path,True);saved=source.read_bytes()
    poses={fp.GetReference():[12,11,90]};options={}
    if fault=='unknown_ref':poses={'missing':[12,11,90]}
    elif fault=='noncardinal':poses[fp.GetReference()][2]=45
    elif fault=='boolean_coordinate':poses[fp.GetReference()][0]=True
    elif fault=='nan':poses[fp.GetReference()][0]=float('nan')
    elif fault=='excessive_shift':poses[fp.GetReference()][0]=17
    elif fault=='boolean_scope':options['max_shift_mm']=True
    elif fault=='excessive_scope':options['max_shift_mm']=7
    elif fault=='empty':poses={}
    elif fault=='duplicate_reference':b.FindFootprintByReference('X2').SetReference(fp.GetReference())
    with pytest.raises(ValueError):
        with worker.reserve(b,poses,'/missing' if fault=='unknown_route_net' else '/routing',**options):pass
    assert not list(b.Zones()) and source.read_bytes()==saved


@pytest.mark.parametrize('frozen',[False,True])
def test_full_source_rated_chain_future_land_reservations_leave_no_saved_rule_area(tmp_path,frozen):
    import cec_rated_branch_layer_chain as chain
    import cec_rated_branch_repair as rated
    from test_rated_branch_layer_chain import case
    source,uid,net,catalog,stages=case(tmp_path)
    b=pcbnew.LoadBoard(str(source))
    b.Add(pcbnew.NETINFO_ITEM(b,'/foreign_land'))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('unrelated_future_header')
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    p=pcbnew.PAD(fp);p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetLayerSet(pcbnew.LSET.AllCuMask())
    p.SetNumber('1');p.SetPosition(fp.GetPosition())
    p.SetNetCode(b.GetNetcodeFromNetname('/foreign_land'));fp.Add(p);b.Add(fp)
    field._save_field_snapshot(b,source)
    poses={'unrelated_future_header':[21,21,90]}
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        child,proposal=chain.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,max_source_width_mm=1,max_replacement_width_mm=1,
            future_poses=poses,frozen_source_pours=frozen)
    assert proposal['future_land_planning']['native_poses'][0]['ref']=='unrelated_future_header'
    assert len(proposal['future_land_planning']['lands'])==6
    assert not list(child.Zones()) and source.read_bytes()==saved
    assert not proposal['new_barrel_ampacity_credited'] and not proposal['branch_sharing_inferred']
