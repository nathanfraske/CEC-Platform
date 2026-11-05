"""Two proposed barrels require their own actual drill-gap check."""
import json
import math
import subprocess
from unittest.mock import patch

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr


def legacy_ranker():
    current=cec_fr._ranked_bridge_seat_pairs
    return lambda a,b,_minimum,**kw: current(a,b,pcbnew.FromMM(.85))


def fixture(tmp_path, *, rotation=0, back=False, spacing=.65, drill=.3, gap=.2):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'RENAMED');board.Add(net)
    side=pcbnew.B_Cu if back else pcbnew.F_Cu
    other=pcbnew.F_Cu if back else pcbnew.B_Cu
    def point(x,y):
        angle=math.radians(rotation)
        return pcbnew.VECTOR2I_MM(20+x*math.cos(angle)-y*math.sin(angle),
                                 20+x*math.sin(angle)+y*math.cos(angle))
    for index,(outer,inner) in enumerate([(-2,0),(spacing+2,spacing)]):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('TERMINAL_'+str(index));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
        layers=pcbnew.LSET();layers.AddLayer(side);pad.SetLayerSet(layers)
        pad.SetPosition(point(outer,0));pad.SetNet(net);fp.Add(pad)
        track=pcbnew.PCB_TRACK(board);track.SetStart(point(outer,0));track.SetEnd(point(inner,0))
        track.SetWidth(pcbnew.FromMM(.2));track.SetLayer(side);track.SetNet(net);board.Add(track)
    points=[(-4,-4),(spacing+4,-4),(spacing+4,4),(-4,4),(-4,-4)]
    for a,b in zip(points,points[1:]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(point(*a));edge.SetEnd(point(*b));edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    path=tmp_path/'pair.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    path.with_suffix('.kicad_pro').write_text(json.dumps({'board':{'design_settings':{'rules':{
        'min_hole_to_hole':gap,'min_hole_clearance':.2,'min_via_diameter':drill+.3,
        'min_through_hole_diameter':drill,'min_via_annular_width':.15,'min_clearance':.2}}}}))
    return path,point(0,0),point(spacing,0),side,other,drill


def solve(data):
    path,a,b,side,other,drill=data;board=pcbnew.LoadBoard(str(path))
    ops=cec_fr._lastmile_bridge(board,(a.x,a.y),{side},(b.x,b.y),{side},
        pcbnew.FromMM(.2),board.GetNetcodeFromNetname('RENAMED'),[other],pcbnew.FromMM(.2),
        drill=drill,dia=drill+.3,allow_maze=False,allow_lattice=False,seat_limit=1)
    return board,ops


@pytest.mark.parametrize('rotation,back',[(0,False),(90,True),(180,False),(270,True),(45,False)])
def test_compact_pair_earns_native_hole_gap(tmp_path,rotation,back):
    data=fixture(tmp_path,rotation=rotation,back=back);before=data[0].read_bytes()
    with patch.object(cec_fr,'_ranked_bridge_seat_pairs',legacy_ranker()):
        assert solve(data)[1] is None
    _,ops=solve(data)
    assert ops and sum(op[0]=='via' for op in ops)==2
    assert data[0].read_bytes()==before


@pytest.mark.parametrize('spacing,drill,gap',[(.499,.3,.2),(.65,.3,.36),(.9,.7,.3)])
def test_actual_drill_and_board_gap_refuse_invalid_pair(tmp_path,spacing,drill,gap):
    data=fixture(tmp_path,spacing=spacing,drill=drill,gap=gap)
    assert solve(data)[1] is None
    if spacing>.85:
        # The old fixed threshold could also admit an invalid larger-drill
        # pair; it was not simply a conservative extra manufacturing margin.
        with patch.object(cec_fr,'_ranked_bridge_seat_pairs',legacy_ranker()):
            assert solve(data)[1] is not None


def seats(x, drill):
    at=pcbnew.VECTOR2I_MM(x,0)
    return [((at.x,at.y),[('via',at,drill,drill+.3)])]


def test_mixed_drill_radii_and_duplicate_origins():
    assert cec_fr._ranked_bridge_seat_pairs(seats(0,.2),seats(.45,.3),0,hole_gap_nm=200000)
    assert not cec_fr._ranked_bridge_seat_pairs(seats(0,.2),seats(.449,.3),0,hole_gap_nm=200000)
    assert not cec_fr._ranked_bridge_seat_pairs(seats(0,.2),seats(0,.3),0,hole_gap_nm=0)


def test_track_only_seat_does_not_invent_a_drill():
    at=pcbnew.VECTOR2I_MM(0,0)
    tracks=[((0,0),[('trk',at,pcbnew.VECTOR2I_MM(.1,0),200000,pcbnew.F_Cu)])]
    assert cec_fr._ranked_bridge_seat_pairs(tracks,seats(.1,.3),0,hole_gap_nm=200000)


def test_existing_viable_candidate_order_is_retained_before_expanded_domain():
    # Globally promoting a shorter newly exposed bridge can change the first
    # N routes in a bounded wave and leave more global opens. Domain expansion
    # is a fallback tier; it must not churn already viable native candidates.
    a=seats(0,.3);b=seats(.65,.3)+seats(2,.3)
    pairs=cec_fr._ranked_bridge_seat_pairs(a,b,850000,hole_gap_nm=200000)
    assert [right[0][0] for _,right in pairs]==[2000000,650000]
    assert len(pairs)==2


def test_preference_never_retains_invalid_wide_drill_pair():
    pairs=cec_fr._ranked_bridge_seat_pairs(seats(0,.7),seats(.9,.7)+seats(1.2,.7),
                                         850000,hole_gap_nm=300000)
    assert [right[0][0] for _,right in pairs]==[1200000]


@pytest.mark.parametrize('gap',[-1,float('nan'),float('inf')])
def test_invalid_hole_rule_is_not_a_waiver(gap):
    with pytest.raises(ValueError):
        cec_fr._ranked_bridge_seat_pairs(seats(0,.2),seats(.5,.3),0,hole_gap_nm=gap)


def test_completed_native_compact_pair_is_drc_and_connectivity_clean(tmp_path):
    data=fixture(tmp_path);board,ops=solve(data);assert ops
    for op in ops:
        if op[0]=='via':
            item=pcbnew.PCB_VIA(board);item.SetPosition(op[1]);item.SetViaType(pcbnew.VIATYPE_THROUGH)
            item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);item.SetDrill(pcbnew.FromMM(op[2]))
            item.SetWidth(pcbnew.FromMM(op[3]))
        else:
            item=pcbnew.PCB_TRACK(board);item.SetStart(op[1]);item.SetEnd(op[2])
            item.SetWidth(op[3]);item.SetLayer(op[4])
        item.SetNet(board.FindNet('RENAMED'));board.Add(item)
    final=tmp_path/'complete.kicad_pcb';pcbnew.SaveBoard(str(final),board,True)
    final.with_suffix('.kicad_pro').write_bytes(data[0].with_suffix('.kicad_pro').read_bytes())
    report=tmp_path/'drc.json'
    run=subprocess.run(['kicad-cli','pcb','drc','--format','json','-o',str(report),str(final)],
                       capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    evidence=json.loads(report.read_text())
    errors=[v for v in evidence['violations'] if v['severity']=='error']
    assert not errors,errors
    assert not evidence['unconnected_items']
