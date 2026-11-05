"""A saved connected pivot must rediscover its private copper from the source."""
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_native_placement_context as motion
import cec_pose_additive_reconstruction as receiving
from test_native_local_cell_rotation import fixed_supply_setup

def fixture(tmp_path,*,turn=180,face=pcbnew.F_Cu,fault=None):
    b,fp,fixed,moving,via,dogbone,trunk,rail=fixed_supply_setup(layer=face,square=turn!=180)
    fp.SetReference('UNRELATED_TWO_RAIL_PASSIVE')
    for s,e in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        item=pcbnew.PCB_SHAPE(b);item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetLayer(pcbnew.Edge_Cuts)
        item.SetStart(pcbnew.VECTOR2I_MM(*s));item.SetEnd(pcbnew.VECTOR2I_MM(*e));item.SetWidth(50000);b.Add(item)
    if fault=='remote':
        t=pcbnew.PCB_TRACK(b);t.SetNet(via.GetNet());t.SetLayer(pcbnew.In2_Cu);t.SetWidth(200000)
        t.SetStart(via.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(25,20));b.Add(t)
    if fault=='shared':
        other=pcbnew.FOOTPRINT(b);other.SetReference('SECOND_ACTUAL_OWNER');b.Add(other)
        pad=pcbnew.PAD(other);pad.SetNumber('g');pad.SetNet(via.GetNet());pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetPosition(moving.GetPosition());pad.SetLayerSet(moving.GetLayerSet());other.Add(pad)
    source=tmp_path/'source.kicad_pcb';b.SetFileName(str(source));field._save_field_snapshot(b,source)
    target=force._copy_family(source,tmp_path/'child');child=pcbnew.LoadBoard(str(target))
    ids=dict(fp=force._uid(fp),fixed=force._uid(fixed),via=force._uid(via),dogbone=force._uid(dogbone),trunk=force._uid(trunk))
    owner=child.FindFootprintByReference(fp.GetReference());pivot=owner.FindPadByNumber(fixed.GetNumber())
    if fault in ('remote','shared'):
        owner.Rotate(pivot.GetPosition(),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    else:
        motion.rotate_isolated_local_cells(child,{fp.GetReference():turn},pivot_pad_uuids={fp.GetReference():ids['fixed']})
    live={force._uid(t):t for t in child.GetTracks()}
    if fault=='barrel_left_behind':live[ids['via']].SetPosition(via.GetPosition())
    elif fault=='wrong_barrel':live[ids['via']].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='changed_fixed_pad':pivot.SetSize(pcbnew.VECTOR2I_MM(.7,.7))
    elif fault=='changed_trunk':live[ids['trunk']].SetWidth(300000)
    elif fault=='translated_after_pivot':owner.Move(pcbnew.VECTOR2I_MM(.1,0))
    additive._ground_refill(child);field._save_field_snapshot(child,target)
    return source,target,ids

@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('turn',[90,180,270])
def test_exact_pivot_replays_actual_private_barrels_and_dogbones(tmp_path,face,turn):
    source,target,ids=fixture(tmp_path,turn=turn,face=face)
    before=source.read_bytes()
    proof=receiving.receive(source,target,selected_footprint_uuids=[ids['fp']],board_hint='unrelated',
        selected_pivot_pad_uuids={ids['fp']:ids['fixed']},max_shift_mm=6.)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_original_terminal_and_copper_partitions_preserved']
    assert proof['moved'][0]['quarter_turns']==turn//90
    assert not proof['release_authority'] and source.read_bytes()==before
    assert ids['via'] in proof['source_private_pivot_reconstruction']['rotated_conductor_uuids']

@pytest.mark.parametrize('fault',['remote','shared','barrel_left_behind','wrong_barrel',
    'changed_fixed_pad','changed_trunk','translated_after_pivot'])
def test_source_private_pose_cannot_smuggle_a_wrong_or_shared_copper_move(tmp_path,fault):
    source,target,ids=fixture(tmp_path,fault=fault)
    before=source.read_bytes()
    proof=receiving.receive(source,target,selected_footprint_uuids=[ids['fp']],board_hint='unrelated',
        selected_pivot_pad_uuids={ids['fp']:ids['fixed']},max_shift_mm=6.)
    assert not proof['ok'] and proof['errors'],proof
    assert source.read_bytes()==before

@pytest.mark.parametrize('mode',['unknown_owner','wrong_pad','duplicate','nondict','boolean','empty'])
def test_pivot_scope_is_exact_terminal_data_not_a_copper_allowlist(tmp_path,mode):
    source,target,ids=fixture(tmp_path)
    pivots={ids['fp']:ids['fixed']}
    if mode=='unknown_owner':pivots={'unknown':ids['fixed']}
    elif mode=='wrong_pad':pivots={ids['fp']:ids['via']}
    elif mode=='duplicate':pivots={'unknown':ids['fixed'],ids['fp']:ids['fixed']}
    elif mode=='nondict':pivots=[]
    elif mode=='boolean':pivots={ids['fp']:True}
    elif mode=='empty':pivots={ids['fp']:''}
    proof=receiving.receive(source,target,selected_footprint_uuids=[ids['fp']],board_hint='unrelated',
        selected_pivot_pad_uuids=pivots,max_shift_mm=6.)
    assert not proof['ok'] and proof['errors'],proof

def test_motion_without_explicit_pivot_mode_is_not_a_barrel_move_permission(tmp_path):
    source,target,ids=fixture(tmp_path)
    proof=receiving.receive(source,target,selected_footprint_uuids=[ids['fp']],board_hint='unrelated')
    assert not proof['ok'] and proof['errors'],proof
