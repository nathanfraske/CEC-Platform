"""A bounded legalizer must inspect the final generated frontier."""
from types import SimpleNamespace
import copy
import pytest
import cec_synth_pipeline as synth


def case():
    candidate=SimpleNamespace(P={'primary':(2.,5.,0.),'neighbor':(6.,5.,0.),
        'follower':(6.,7.,90.)},W=20.,H=20.,back_refs=())
    def box(ref,pose):
        x,y,_=pose
        return (x-.4,x+.4,y-.4,y+.4)
    return candidate,box


@pytest.mark.parametrize('steps',[1,2,4])
def test_generated_goal_at_last_depth_is_retained(steps):
    candidate,box=case();before=copy.deepcopy(candidate.P);trace={}
    rows=synth._placement_bounded_macro_legalizations(candidate,{'primary':(6.,5.,0.)},set(),
        {ref:object() for ref in candidate.P},{'follower':'neighbor'},
        {'neighbor':['follower']},lambda ref:ref=='neighbor',bbox_fn=box,
        exact_bbox_overlap=True,max_steps=steps,trace=trace)
    assert rows
    assert trace['reason']=='legalized'
    for positions,roots,_ in rows:
        combined=dict(candidate.P,**positions)
        assert not synth._placement_bbox_overlap_pairs(combined,box)
        assert combined['follower'][0]-combined['neighbor'][0]==pytest.approx(0)
        assert combined['follower'][1]-combined['neighbor'][1]==pytest.approx(2)
        assert combined['follower'][2]==90
    assert candidate.P==before


def test_fixed_neighbor_is_not_admitted_at_budget_boundary():
    candidate,box=case()
    assert synth._placement_bounded_macro_legalizations(candidate,{'primary':(6.,5.,0.)},set(),
        {ref:object() for ref in candidate.P},{},{},lambda ref:False,bbox_fn=box,
        exact_bbox_overlap=True,max_steps=1)==[]


@pytest.mark.parametrize('flipped',[False,True])
def test_final_frontier_uses_loaded_native_pad_envelopes(tmp_path,flipped):
    import pcbnew
    candidate,_=case();board=pcbnew.CreateEmptyBoard()
    for ref,(x,y,angle) in candidate.P.items():
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(fp.GetPosition());fp.Add(pad)
        board.Add(fp);fp.SetOrientationDegrees(angle)
        if flipped:fp.Flip(fp.GetPosition(),False)
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path));raw=path.read_bytes()
    fps={fp.GetReference():fp for fp in board.GetFootprints()}
    candidate.P={ref:(fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees())
                 for ref,fp in fps.items()}
    candidate.back_refs=set(fps) if flipped else set()
    def bbox(ref,pose):
        pad=next(iter(fps[ref].Pads()));bb=pad.GetBoundingBox()
        dx,dy=pose[0]-candidate.P[ref][0],pose[1]-candidate.P[ref][1]
        return bb.GetLeft()/1e6+dx,bb.GetRight()/1e6+dx,bb.GetTop()/1e6+dy,bb.GetBottom()/1e6+dy
    rows=synth._placement_bounded_macro_legalizations(candidate,
        {'primary':(6.,5.,candidate.P['primary'][2])},set(),fps,
        {'follower':'neighbor'},{'neighbor':['follower']},lambda ref:ref=='neighbor',
        bbox_fn=bbox,exact_bbox_overlap=True,max_steps=1)
    assert rows
    assert path.read_bytes()==raw
    assert all(not synth._placement_bbox_overlap_pairs(dict(candidate.P,**positions),bbox,
        back_refs=candidate.back_refs) for positions,_,_ in rows)
