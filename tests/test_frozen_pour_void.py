"""Existing clearance holes are not authority to cut new power copper."""
import pcbnew
import pytest
import cec_fr
import cec_frozen_pour_void as void
import cec_additive_pair_repair as additive
from unittest.mock import patch


def poly(*, hole=True):
    p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
    for x,y in [(0,0),(10,0),(10,10),(0,10)]:p.Append(round(x*1e6),round(y*1e6))
    if hole:
        p.NewHole()
        for x,y in [(4,4),(4,6),(6,6),(6,4)]:p.Append(round(x*1e6),round(y*1e6),0,0)
    return p


def fixture(*, back=False, quarter=0, filled=True, hole=True):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(4)
    for n in ['RENAMED_SIGNAL','OTHER_POWER']:board.Add(pcbnew.NETINFO_ITEM(board,n))
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    ends=[]
    for i,x in enumerate([4.75,5.25]):
        xy=(x,5) if quarter==0 else (5,x)
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_'+str(i));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('abc');pad.SetNet(board.FindNet('RENAMED_SIGNAL'))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers);fp.Add(pad)
        ends.append(dict(kind='pad',ref=fp.GetReference(),pad='abc',x_mm=xy[0],y_mm=xy[1]))
    z=pcbnew.ZONE(board);z.SetLayer(layer);z.SetNet(board.FindNet('OTHER_POWER'))
    z.SetZoneName('pourfirst:protected');z.SetLocalClearance(200000)
    z.Outline().NewOutline()
    for x,y in [(0,0),(10,0),(10,10),(0,10)]:z.Outline().Append(round(x*1e6),round(y*1e6))
    if filled:z.SetFilledPolysList(layer,poly(hole=hole));z.SetIsFilled(True)
    board.Add(z)
    return board,ends,z,layer


def plan(board,ends,**kw):
    return void.plan(board,ends,net_code=board.FindNet('RENAMED_SIGNAL').GetNetCode(),
        width_nm=200000,clearance_nm=200000,**kw)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',[0,1])
def test_only_existing_full_clearance_void_is_eligible(back,quarter,monkeypatch):
    board,ends,z,layer=fixture(back=back,quarter=quarter)
    monkeypatch.setattr(cec_fr,'_edge_leg_clear',lambda *a:True)
    result=plan(board,ends)
    assert result and result['evidence']['requires_post_refill_zero_copper_loss']
    assert not list(board.GetTracks())
    a,b=[pcbnew.VECTOR2I_MM(ep['x_mm'],ep['y_mm']) for ep in ends]
    assert not cec_fr._tap_foreign_clear(board,a,b,200000,layer,200000,
        {board.FindNet('RENAMED_SIGNAL').GetNetCode()},foreign_cache={})
    # The general guard remains strict; this is no global pour bypass.
    assert result['operations'][0][4]==layer


@pytest.mark.parametrize('kw',[dict(filled=False),dict(hole=False)])
def test_empty_or_obstructed_fills_refuse(kw,monkeypatch):
    board,ends,_,_=fixture(**kw)
    monkeypatch.setattr(cec_fr,'_edge_leg_clear',lambda *a:True)
    assert plan(board,ends) is None


def test_existing_trace_clearance_is_still_binding(monkeypatch):
    board,ends,_,layer=fixture()
    monkeypatch.setattr(cec_fr,'_edge_leg_clear',lambda *a:True)
    tr=pcbnew.PCB_TRACK(board);tr.SetNet(board.FindNet('OTHER_POWER'));tr.SetLayer(layer)
    tr.SetStart(pcbnew.VECTOR2I_MM(5,4.5));tr.SetEnd(pcbnew.VECTOR2I_MM(5,5.5));tr.SetWidth(200000);board.Add(tr)
    assert plan(board,ends) is None


def test_stale_pad_identity_and_length_bound_fail_closed(monkeypatch):
    board,ends,_,_=fixture()
    monkeypatch.setattr(cec_fr,'_edge_leg_clear',lambda *a:True)
    assert plan(board,ends,max_span_mm=.49) is None
    ends[0]['x_mm']+=.001
    assert plan(board,ends) is None


def test_stricter_zone_clearance_and_non_octilinear_path_refuse(monkeypatch):
    board,ends,zone,_=fixture()
    monkeypatch.setattr(cec_fr,'_edge_leg_clear',lambda *a:True)
    zone.SetLocalClearance(700000)
    assert plan(board,ends) is None
    zone.SetLocalClearance(200000)
    fp=board.FindFootprintByReference(ends[1]['ref'])
    pad=next(iter(fp.Pads()));pad.SetPosition(pcbnew.VECTOR2I_MM(5.25,5.1))
    ends[1]['y_mm']=5.1
    assert plan(board,ends) is None


def test_fill_presence_flag_without_polygons_is_not_evidence(monkeypatch):
    board,ends,zone,layer=fixture()
    monkeypatch.setattr(cec_fr,'_edge_leg_clear',lambda *a:True)
    zone.SetFilledPolysList(layer,pcbnew.SHAPE_POLY_SET());zone.SetIsFilled(True)
    assert plan(board,ends) is None
    with pytest.raises(ValueError,match='missing'):
        void.capture(board)


def test_post_refill_proof_detects_even_tiny_copper_loss():
    board,_,zone,layer=fixture();frozen=void.capture(board)
    assert void.preservation(frozen,board)['ok']
    changed=poly();cut=pcbnew.SHAPE_POLY_SET();cut.NewOutline()
    for x,y in [(1000000,1000000),(1000010,1000000),(1000010,1000010),(1000000,1000010)]:cut.Append(x,y)
    changed.BooleanSubtract(cut);zone.SetFilledPolysList(layer,changed)
    report=void.preservation(frozen,board)
    assert not report['ok'] and report['tolerance_nm']==0
    assert report['rows'][0]['lost_area_nm2']==100


def test_missing_zone_or_missing_fill_cannot_pass_preservation():
    board,_,zone,_=fixture();frozen=void.capture(board)
    zone.UnFill()
    assert not void.preservation(frozen,board)['ok']


@pytest.mark.parametrize('lose_copper',[False,True])
def test_refill_control_never_waives_source_copper_loss(monkeypatch,lose_copper):
    board,_,zone,layer=fixture()
    saved=poly()
    class Filler:
        def Fill(self,_zones):
            restored=pcbnew.SHAPE_POLY_SET(saved)
            if lose_copper:
                cut=pcbnew.SHAPE_POLY_SET();cut.NewOutline()
                for x,y in [(1,1),(2,1),(2,2),(1,2)]:cut.Append(x*1000000,y*1000000)
                restored.BooleanSubtract(cut)
            zone.SetFilledPolysList(layer,restored);zone.SetIsFilled(True)
            return True
    monkeypatch.setattr(pcbnew,'ZONE_FILLER',lambda _board:Filler())
    snapshot,proof=void.refreshed_control(board)
    assert proof['ok'] is (not lose_copper)
    assert (snapshot is not None) is (not lose_copper)
    assert proof['tolerance_nm']==0


def test_short_targets_are_ranked_before_native_list_order():
    def certificate(net,distance):
        return dict(detail={'distance_mm':distance},certificate=dict(net=net,width_mm=.2,
            endpoints=[dict(kind='pad',ref=str(i),pad='1',x_mm=x,y_mm=0)
                       for i,x in enumerate((0,distance))]))
    rows=[certificate('LONG',20),certificate('SHORT',1),certificate('MIDDLE',7)]
    with patch.object(additive,'bound_snapshot',return_value=True), \
         patch('cec_certificate_repair._spawn_apply',return_value={}), \
         patch('cec_certificate_repair.refusal_certificates',return_value=rows):
        result=additive.targets('unused',{},limit=2)
    assert [r['target_net'] for r in result['targets']]==['SHORT','MIDDLE']
