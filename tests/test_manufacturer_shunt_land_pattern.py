"""A selected manufacturer drawing, never a board/refdes/ampacity heuristic."""
import copy
from pathlib import Path

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_manufacturer_land_pattern as pattern


def fixture(tmp_path,angle=0,back=False,name='NO_BOARD_OR_REFDES_RULE'):
    board=pcbnew.BOARD()
    library=pattern.ROOT/'lib/vendor/Resistor_SMD.pretty'
    fp=pcbnew.FootprintLoad(str(library),'R_2512_6332Metric')
    fp.SetFPIDAsString('cec-Resistor_SMD:R_2512_6332Metric')
    fp.SetReference(name);fp.SetValue('0.5mΩ');fp.SetField('MPN','CSS2H-2512R-L500F')
    board.Add(fp)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientationDegrees(angle);fp.SetPosition(pcbnew.VECTOR2I_MM(17.2,26.5))
    for pad in fp.Pads():
        net=pcbnew.NETINFO_ITEM(board,'UNRELATED_PREFIX/FORCE_'+pad.GetNumber())
        board.Add(net);pad.SetNet(net)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    return source,force._uid(fp)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_exact_drawing_replay_rotates_and_mirrors_without_net_or_pose_changes(tmp_path,angle,back):
    source,uid=fixture(tmp_path,angle,back)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    original={force._uid(p):(p.GetNumber(),p.GetNetname())for p in fp.Pads()}
    proposal=pattern.plan(board,[uid]);before=copy.deepcopy(proposal)
    assert proposal['patterns'][0]['datasheet_sha256']=='7e32b223f4b0f086d9e08cd5a4fb42e9935cf119db3dd9cf3ea7969bdd643909'
    pattern.materialize(board,proposal);assert before==proposal
    assert {force._uid(p):(p.GetNumber(),p.GetNetname())for p in fp.Pads()}==original
    assert all(tuple(p.GetSize())==(1800000,3400000)and p.GetShape()==pcbnew.PAD_SHAPE_RECT for p in fp.Pads())
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,child)
    data=[p.read_bytes()for p in (source,child)]
    received=pattern.receive(source,child,board_hint='synthetic-not-a-board-name',footprint_uuids=[uid])
    assert received['complete']and received['ok'],received
    assert received['all_prior_native_terminal_and_copper_partitions_preserved']
    assert not any(received[k]for k in ('current_authority','assembly_qualified','release_authority'))
    assert data==[p.read_bytes()for p in (source,child)]


@pytest.mark.parametrize('fault',['unknown_part','nearby_part','wrong_value','missing_part','dnp',
    'offset','size','centre','missing_pad','drill','shape','orientation','layers','drill_shape',
    'primary_drawing_changed'])
def test_unselected_or_modified_source_does_not_earn_manufacturer_geometry(tmp_path,monkeypatch,fault):
    source,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    pad=fp.FindPadByNumber('1')
    if fault=='unknown_part':fp.SetField('MPN','GENERIC_2512')
    elif fault=='nearby_part':fp.SetField('MPN','CSS2H-2512R-L300F')
    elif fault=='wrong_value':fp.SetValue('0.5Ω')
    elif fault=='missing_part':fp.SetField('MPN','')
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='offset':pad.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='size':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='centre':pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(1,0))
    elif fault=='missing_pad':fp.Remove(pad)
    elif fault=='drill':pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    elif fault=='shape':pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    elif fault=='orientation':pad.SetOrientationDegrees(pad.GetOrientationDegrees()+90)
    elif fault=='layers':pad.SetLayerSet(pcbnew.PAD.PTHMask())
    elif fault=='drill_shape':pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
    else:
        original=force._hash
        monkeypatch.setattr(force,'_hash',lambda p:'0'*64 if Path(p).suffix=='.pdf'else original(p))
    with pytest.raises(ValueError):pattern.plan(board,[uid])


@pytest.mark.parametrize('fault',['ampacity_claim','changed_drawing','changed_mpn','changed_library'])
def test_producer_cannot_author_a_manufacturer_rule(tmp_path,fault):
    source,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));proposal=pattern.plan(board,[uid])
    if fault=='ampacity_claim':proposal['current_authority']=True
    elif fault=='changed_drawing':proposal['patterns'][0]['drawing']='requested pad enlargement'
    elif fault=='changed_mpn':proposal['patterns'][0]['selected_mpn']='CSS2H-2512R-L300F'
    else:proposal['patterns'][0]['new_library_sha256']='0'*64
    with pytest.raises(ValueError,match='source_rederivation'):pattern.materialize(board,proposal)


@pytest.mark.parametrize('fault',['net','pose','size','shape','pad_identity','mask','extra_track','sidecar'])
def test_saved_child_receives_only_the_exact_native_manufacturer_delta(tmp_path,fault):
    source,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));proposal=pattern.plan(board,[uid])
    pattern.materialize(board,proposal);fp=next(iter(board.GetFootprints()));pad=fp.FindPadByNumber('1')
    if fault=='net':pad.SetNet(fp.FindPadByNumber('2').GetNet())
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='size':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='shape':pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    elif fault=='pad_identity':pad.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='mask':pad.SetLocalSolderMaskMargin(1)
    elif fault=='extra_track':
        track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(pad.GetLayer())
        track.SetWidth(500000);track.SetStart(pad.GetPosition());track.SetEnd(pad.GetPosition()+pcbnew.VECTOR2I(1000000,0))
        board.Add(track)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,child)
    if fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    received=pattern.receive(source,child,board_hint='synthetic',footprint_uuids=[uid])
    assert not received['complete']and received['errors']


def test_old_outer_edge_contacts_that_the_recommended_land_loses_are_not_waived(tmp_path):
    source,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    pad=fp.FindPadByNumber('1');old=tuple(pad.GetPosition())
    # At angle0 the recommended left land ends0.075mm inside the old end.
    start=(old[0]-600000,old[1]);end=(start[0]-1000000,start[1])
    track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(0);track.SetWidth(10000)
    track.SetStart(pcbnew.VECTOR2I(*start));track.SetEnd(pcbnew.VECTOR2I(*end));board.Add(track)
    field._save_field_snapshot(board,source)
    proposal=pattern.plan(board,[uid]);pattern.materialize(board,proposal)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,child)
    received=pattern.receive(source,child,board_hint='synthetic',footprint_uuids=[uid])
    assert not received['complete']and any('lost_prior_native'in e for e in received['errors'])
