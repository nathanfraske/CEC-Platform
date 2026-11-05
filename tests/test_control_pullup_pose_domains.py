"""Pull-ups get finite all-pad placement domains, not fictitious Ground vias."""
from pathlib import Path
import pcbnew,pytest
import cec_native_cell_pose_domains as domains
import cec_cell_escape_replan as escape
import cec_control_pullup_placement as pullup
import cec_field_coupling as field
import cec_force_current as force
from test_control_pullup_placement import fixture


def source(tmp_path,monkeypatch,turn=0,back=False):
    b,m,c,r,s,root,tree,unused=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{}})
    b.SetCopperLayerCount(6);r.SetPosition(pcbnew.VECTOR2I_MM(20,10))
    r.FindPadByNumber('1').SetPosition(pcbnew.VECTOR2I_MM(19.55,10))
    r.FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I_MM(20.45,10))
    for fp in b.GetFootprints():
        bounds=[p.GetBoundingBox()for p in fp.Pads()]
        court=pcbnew.PCB_SHAPE(fp);court.SetShape(pcbnew.SHAPE_T_RECT);court.SetLayer(pcbnew.F_CrtYd);court.SetWidth(50000)
        court.SetStart(pcbnew.VECTOR2I(min(v.GetLeft()for v in bounds)-100000,min(v.GetTop()for v in bounds)-100000))
        court.SetEnd(pcbnew.VECTOR2I(max(v.GetRight()for v in bounds)+100000,max(v.GetBottom()for v in bounds)+100000));fp.Add(court)
    if turn:
        for fp in b.GetFootprints():fp.Rotate(pcbnew.VECTOR2I_MM(35,15),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    if back:
        for fp in b.GetFootprints():fp.Flip(pcbnew.VECTOR2I_MM(35,15),False)
    for a,z in [((-20,-30),(90,-30)),((90,-30),(90,70)),((90,70),(-20,70)),((-20,70),(-20,-30))]:
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));e.SetWidth(50000);b.Add(e)
    path=Path(b.GetFileName());field._save_field_snapshot(b,path)
    monkeypatch.setattr(force,'_family',lambda p,h:dict(board=force._hash(Path(p)),source=force._hash(root)))
    return path,b,r,root,{r.GetReference():[r.GetPosition().x/1e6+.3,r.GetPosition().y/1e6,r.GetOrientationDegrees()]}


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_finite_native_pullup_domains_keep_real_supply_and_no_ground(tmp_path,monkeypatch,turn,back):
    path,b,r,root,poses=source(tmp_path,monkeypatch,turn,back);before=path.read_bytes()
    result=domains.propose(path,poses,board_hint=str(root),radius_mm=.75,grid_mm=.25,
        max_candidates=8,max_results=1,complete_owner_ground=True)
    assert result['domains'][r.GetReference()],result['domain_stages']
    assert all('supply_nm'in q and q['ground_nm']==[]for q in result['domains'][r.GetReference()])
    assert path.read_bytes()==before and not result['routing_admitted']


def test_no_ground_screen_is_narrow_source_pullup_scope_not_a_waiver(tmp_path,monkeypatch):
    path,b,r,root,poses=source(tmp_path,monkeypatch)
    q=escape.prepare(b,poses,board_hint=str(root))
    result=domains._pose_ground_screen(b,q,board_hint=str(root),timeout_s=1.,complete_owner_ground=True)
    assert result['not_applicable']and result['ground_terminal_count']==0
    assert not result['new_ground_barrel_authority']
    del q['selected_control_pullups']
    with pytest.raises(ValueError):domains._pose_ground_screen(b,q,board_hint=str(root),timeout_s=1.,complete_owner_ground=True)
