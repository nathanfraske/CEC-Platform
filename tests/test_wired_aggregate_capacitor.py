"""Canonical ceramic tests; only pre-existing aggregate current is synthetic."""
from pathlib import Path
import pcbnew
import pytest
import cec_wired_aggregate_capacitor as op
from test_source_aggregate_capacitor_cell import fixture as base_fixture
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, quarter=0, back=False):
    source, root, _ = base_fixture(tmp_path,monkeypatch,quarter,back)
    board=pcbnew.LoadBoard(str(source)); fp=board.FindFootprintByReference('RENAMED_C')
    for pad in fp.Pads():
        peer=next(p for p in fp.Pads() if p.GetNumber()!=pad.GetNumber())
        a=pad.GetPosition(); b=peer.GetPosition()
        end=[a.x+(a.x-b.x)//2,a.y+(a.y-b.y)//2]
        track(board,pad.GetNetname(),(a.x/1e6,a.y/1e6),(end[0]/1e6,end[1]/1e6),
              width=.5 if pad.GetNetname()!='GND' else .2,layer=int(fp.GetLayer()))
    op.cap.field._save_field_snapshot(board,source)
    poses={ref:[f.GetPosition().x/1e6+.1 if ref==fp.GetReference() else f.GetPosition().x/1e6,
                f.GetPosition().y/1e6,f.GetOrientationDegrees()]
           for ref in (fp.GetReference(),'AMP73') for f in [board.FindFootprintByReference(ref)]}
    return board,fp,root,poses


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_wired_canonical_identity_both_contacts_no_authority(tmp_path,monkeypatch,quarter,back):
    board,fp,root,poses=fixture(tmp_path,monkeypatch,quarter,back)
    before=Path(board.GetFileName()).read_bytes(); binding=op.cap.row._source_binding(board)
    proof=op.inspect(board,fp,poses,str(root))
    assert proof['scope']==op.SCOPE
    assert all(proof['source_terminal_contacts'].values())
    assert proof['unchanged_selected_bypass_assignments']['AMP73:6:100n']=='EXISTING_FEED'
    assert proof['source_locality_owner']['owner_ref']=='AMP73'
    assert proof['source_linear_stage'] is None
    assert not any(proof[k] for k in ('current_authority','source_trace_retirement_authority',
        'copper_transport_authority','new_barrel_authority','physical_acceptance','release_authority'))
    assert Path(board.GetFileName()).read_bytes()==before
    assert op.cap.row._source_binding(board)==binding


@pytest.mark.parametrize('fault',['unsaved','field','selected','missing_owner','moving_owner',
                                  'flag','timeout','nonfinite','missing_ground_contact'])
def test_unproved_role_refused(tmp_path,monkeypatch,fault):
    board,fp,root,poses=fixture(tmp_path,monkeypatch); options={}
    if fault=='unsaved':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='field':root.write_text(root.read_text().replace('FIXTURE_VENDOR','UNKNOWN'))
    elif fault=='selected':fp=board.FindFootprintByReference('EXISTING_FEED');poses[fp.GetReference()]=[16.6,10,0]
    elif fault=='missing_owner':poses.pop('AMP73')
    elif fault=='moving_owner':poses['AMP73'][0]+=.1
    elif fault=='flag':options['allow_linear_power_stage_reconstruction']=1
    elif fault=='timeout':options['timeout_s']=10.1
    elif fault=='nonfinite':poses['RENAMED_C'][0]=float('nan')
    else:
        for t in list(board.GetTracks()):
            if t.GetNetname()=='GND' and t.GetClass()=='PCB_TRACK':board.Remove(t)
        # Existing plane contact is still real; remove these only for this
        # explicitly isolated negative fixture before saving a new Source.
        for z in list(board.Zones()):board.Remove(z)
        op.cap.field._save_field_snapshot(board,Path(board.GetFileName()))
    with pytest.raises(ValueError):op.inspect(board,fp,poses,str(root),**options)


@pytest.mark.parametrize('fault',['none','missing_selected','missing_stage','missing_domain','current_mismatch'])
def test_moving_owner_requires_fresh_positive_stage_and_complete_selected_cohort(tmp_path,monkeypatch,fault):
    import cec_source_linear_power_stage as stages
    board,fp,root,poses=fixture(tmp_path,monkeypatch)
    poses['AMP73'][0]+=.1
    follower=board.FindFootprintByReference('EXISTING_FEED')
    if fault!='missing_selected':
        poses[follower.GetReference()]=[follower.GetPosition().x/1e6+.1,
            follower.GetPosition().y/1e6,follower.GetOrientationDegrees()]
    calls=[]
    def synthetic_stage(*args,**kwargs):
        # This is only a propagation/selection test, not an INA181 stage
        # admission. Actual TPS2121 current identity is checked independently.
        calls.append(kwargs)
        return {} if fault=='missing_stage' else {'AMP73':{'synthetic_stage_boundary_only':True}}
    monkeypatch.setattr(stages,'collect',synthetic_stage)
    if fault=='missing_domain':
        monkeypatch.setattr(op.cap.full,'_model',lambda *a:('unknown',{},{}))
    if fault=='current_mismatch':
        monkeypatch.setattr(op.cap.cells,'_supply_current_widths',lambda *a:{'current_authority':{}})
    if fault=='none':
        proof=op.inspect(board,fp,poses,str(root),True)
        assert proof['coherent_owner_motion']['source_linear_stage']['synthetic_stage_boundary_only']
        assert proof['independent_copper_ownership_required']
    else:
        with pytest.raises(ValueError):op.inspect(board,fp,poses,str(root),True)
    assert len(calls)==1 and calls[0]['enabled'] is True


@pytest.mark.parametrize('owner_kind',['board','foreign_footprint'])
@pytest.mark.parametrize('touching',[False,True])
def test_copper_artwork_cannot_disappear_from_actual_contact_inventory(tmp_path,monkeypatch,owner_kind,touching):
    board,fp,root,poses=fixture(tmp_path,monkeypatch)
    owner = board if owner_kind=='board' else board.FindFootprintByReference('EXISTING_FEED')
    artwork=pcbnew.PCB_SHAPE(owner);artwork.SetShape(pcbnew.SHAPE_T_SEGMENT)
    artwork.SetLayer(int(fp.GetLayer()));artwork.SetWidth(100000)
    pad=fp.FindPadByNumber('1');at=pad.GetPosition()
    offset=0 if touching else 5_000_000
    artwork.SetStart(pcbnew.VECTOR2I(at.x+offset,at.y-100000))
    artwork.SetEnd(pcbnew.VECTOR2I(at.x+offset,at.y+100000));owner.Add(artwork)
    op.cap.field._save_field_snapshot(board,Path(board.GetFileName()))
    if touching:
        with pytest.raises(ValueError,match='wired_aggregate_uninventoried_copper_artwork_contact'):
            op.inspect(board,fp,poses,str(root))
    else:
        proof=op.inspect(board,fp,poses,str(root))
        assert proof['independent_copper_ownership_required']
        assert not proof['copper_transport_authority']
