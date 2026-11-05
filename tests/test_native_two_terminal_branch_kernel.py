"""Internal tee/loop degree does not invent a third external terminal."""
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
from cec_native_branch_forest import plan
from test_lastmile import _board
from test_field_proposals import track
from test_native_pending_joint_cohort import row


def fixture(tmp_path,turn=0,shift=(0,0),mode=None):
    net='GND' if mode=='protected' else 'RENAMED_ORDINARY'
    pads=[(10,20,net),(40,20,net),(20,20,'OTHER')]
    if mode=='one_actual':pads.pop(1)
    if mode=='three_actual':pads.append((20,30,net))
    b=_board(pads)
    edges=[track(b,net,a,z) for a,z in [((10,20),(20,20)),((20,20),(30,20)),
        ((30,20),(40,20)),((20,20),(20,30)),((20,30),(30,30)),((30,30),(30,20))]]
    if mode=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('REAL_SOURCE_OWNER');b.Add(g)
        for t in edges:g.AddItem(t)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(*shift))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    ids=[force._uid(t) for t in edges]
    b=pcbnew.LoadBoard(str(path));by_id={force._uid(t):t for t in b.GetTracks()}
    edges=[by_id[u] for u in ids]
    settings=dict(clearance_for=lambda n:200000,allow_literal_body_cohort=True,
        normalize_free_pending_junctions=True,collapse_retained_native_ports=True,
        close_provisional_native_junctions=True,source_path=path,board_hint='synthetic',
        provisional_reconstruction_track_uuids=[force._uid(t) for t in edges])
    if mode=='default':settings['normalize_free_pending_junctions']=False
    return b,edges,settings


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('shift',[(0,0),(3,-2)])
def test_positive_two_actual_terminal_loop_rebuilds_as_one_exact_kernel(tmp_path,turn,shift):
    b,edges,settings=fixture(tmp_path,turn,shift)
    before=field._field_snapshot_inventory(b)
    remaining,forests,proof=plan(b,[row(edges[0])],**settings)
    assert not remaining and len(forests)==1
    f=forests[0]
    assert f['positive_ordinary_two_terminal_kernel'] and len(f['external_ports_nm'])==2
    assert len(f['route_rows'])==1 and set(f['member_uuids'])=={force._uid(t) for t in edges}
    assert not proof['automatic_retirement_authorized'] and not proof['current_qualified']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('mode',['protected','group','default','one_actual'])
def test_two_terminal_classification_cannot_hide_protection_or_phantom_port(tmp_path,mode):
    b,edges,settings=fixture(tmp_path,mode=mode);before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):plan(b,[row(edges[0])],**settings)
    assert field._field_snapshot_inventory(b)==before


def test_third_actual_source_terminal_is_preserved(tmp_path):
    b,edges,settings=fixture(tmp_path,mode='three_actual')
    _,forests,proof=plan(b,[row(edges[0])],**settings)
    assert len(forests)==1 and len(forests[0]['external_ports_nm'])==3
    assert len(forests[0]['route_rows'])==2 and not forests[0]['positive_ordinary_two_terminal_kernel']
