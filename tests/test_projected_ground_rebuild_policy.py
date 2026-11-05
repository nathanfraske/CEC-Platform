"""A retained Ground wall may be rebuilt only by its positive source owner."""
import copy
import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_complete_cell_receiving as receiving
import cec_field_coupling as field
import cec_force_current as force
import cec_additive_route_receiving as additive
from test_cell_escape_replan import fixture as base
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,quarter=0):
    board,unused,owner,cap=base(monkeypatch,prefix='opaque_rebuild')
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    gp=cap.FindPadByNumber('2');at=tuple(gp.GetPosition())
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'))
    via.SetPosition(pcbnew.VECTOR2I(at[0]+750000,at[1]));via.SetWidth(600000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    leg=track(board,'GND',[v/1e6 for v in at],[(at[0]+750000)/1e6,at[1]/1e6],width=.2)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(board);z.SetNet(board.FindNet('GND'));z.SetLayer(face)
        z.SetLocalClearance(200000);z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(25,1),(25,25),(1,25)):z.Outline().Append(x*1000000,y*1000000)
        board.Add(z)
    target={owner.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()],
        cap.GetReference():[at[0]/1e6,at[1]/1e6+.5,90.]}
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.Zones()]:item.Rotate(pivot,angle)
        for ref,pose in target.items():
            # Transform the target through a detached native footprint,
            # preserving the same whole-board rotation as the source.
            f=pcbnew.FOOTPRINT(board);f.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]));f.SetOrientationDegrees(pose[2])
            f.Rotate(pivot,angle);target[ref]=[f.GetPosition().x/1e6,f.GetPosition().y/1e6,f.GetOrientationDegrees()]
    additive._ground_refill(board)
    source=tmp_path/'source.kicad_pcb';board.SetFileName(str(source));field._save_field_snapshot(board,source)
    parent=pcbnew.LoadBoard(str(source))
    return parent,source,target,force._uid(gp),force._uid(leg),force._uid(via)


@pytest.mark.parametrize('quarter',range(4))
def test_opt_in_rebuild_owns_exact_strokes_but_not_barrel_plane_or_clearance(tmp_path,monkeypatch,quarter):
    board,source,target,gp,leg,via=fixture(tmp_path,monkeypatch,quarter)
    before=escape.row._source_binding(board);raw=source.read_bytes()
    retained=escape.prepare(board,target,board_hint='opaque')
    assert gp in retained['native_projected_ground_contacts'] and leg not in retained['retired_track_uuids']
    rebuilt=escape.prepare(board,target,board_hint='opaque',rebuild_projected_ground=True)
    assert rebuilt['rebuild_projected_ground'] is True and leg in rebuilt['retired_track_uuids']
    assert via not in rebuilt['retired_track_uuids']
    assert not rebuilt.get('native_projected_ground_contacts')
    assert any(q['pad_uuid']==gp and leg in q['track_uuids'] for q in rebuilt['ground_leaves'])
    assert escape.row._source_binding(board)==before and source.read_bytes()==raw
    child=pcbnew.LoadBoard(str(source));escape.apply_private(child,rebuilt)
    assert via in {force._uid(t) for t in child.GetTracks()}
    assert leg not in {force._uid(t) for t in child.GetTracks()}
    obligations=escape.obligations(board,child,rebuilt)
    assert obligations['ground:'+gp]['reach_mm']==.8
    assert not rebuilt['routing_admitted'] and not rebuilt['release_authority']


@pytest.mark.parametrize('fault',['drop','truthy','invented_cut'])
def test_ground_rebuild_is_a_rederived_policy_not_worker_retirement_authority(tmp_path,monkeypatch,fault):
    board,source,target,gp,leg,via=fixture(tmp_path,monkeypatch)
    proof=escape.prepare(board,target,board_hint='opaque',rebuild_projected_ground=True)
    forged=copy.deepcopy(proof)
    if fault=='drop':del forged['rebuild_projected_ground']
    elif fault=='truthy':forged['rebuild_projected_ground']=1
    else:forged['retired_track_uuids'].append(via)
    before=escape.row._source_binding(board)
    with pytest.raises(ValueError):escape.apply_private(board,forged)
    assert before==escape.row._source_binding(board)


@pytest.mark.parametrize('value',[1,None,'yes',[],{}])
def test_truthy_or_untyped_ground_policy_refuses_before_source_reads(value):
    with pytest.raises(ValueError):escape.prepare(None,{'opaque':[0,0,0]},board_hint='opaque',rebuild_projected_ground=value)
    with pytest.raises(ValueError):receiving.receive('missing','missing',board_hint='opaque',rebuild_projected_ground=value)
