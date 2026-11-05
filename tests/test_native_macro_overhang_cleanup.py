"""Native ordinary junction trims never delete the bridge or its contacts."""
import math
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_macro_overhang_cleanup as cleanup
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,rotation=0,mirror=False,fault=None):
    board=_board([],edge=(0,0,25,25));net=pcbnew.NETINFO_ITEM(board,'/unrelated_named_control');board.Add(net)
    source_ids=[]
    for layer,first,last in [(pcbnew.In1_Cu,(14,8),(10,12)),
            (pcbnew.In1_Cu,(14,4),(14,8)),(pcbnew.In1_Cu,(10.5,5),(10.5,14))]:
        before={force._uid(t) for t in board.GetTracks()};track(board,net.GetNetname(),first,last,layer=layer)
        source_ids.append(next(force._uid(t) for t in board.GetTracks() if force._uid(t) not in before))
    seed=next(t for t in board.GetTracks() if force._uid(t)==source_ids[0])
    if fault=='locked':seed.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);group.SetName('FROZEN');board.Add(group);group.AddItem(seed)
    elif fault=='sensitive':
        special=pcbnew.NETINFO_ITEM(board,'/SENSE_HI');board.Add(special)
        for item in board.GetTracks():item.SetNet(special)
    elif fault=='body_contact':
        # A genuine finite-width contact beyond the exact centreline extrema
        # must survive; it vetoes trimming rather than disappearing silently.
        track(board,net.GetNetname(),(9.95,11.92),(9,11.92),layer=pcbnew.In1_Cu)
    elif fault=='pad':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('ACTUAL_PAD');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetPosition(pcbnew.VECTOR2I_MM(10,12))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetNet(net)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.In1_Cu);pad.SetLayerSet(layers);fp.Add(pad)
    def move(at):
        x,y=at[0]-12,at[1]-12
        if mirror:x=-x
        angle=math.radians(-rotation)
        return [round((12+x*math.cos(angle)-y*math.sin(angle))*1e6),
            round((12+x*math.sin(angle)+y*math.cos(angle))*1e6)]
    if rotation or mirror:
        assert fault not in ('pad',)
        for item in board.GetTracks():
            first,last=[list(v) for v in (item.GetStart(),item.GetEnd())]
            item.SetStart(pcbnew.VECTOR2I(*move([v/1e6 for v in first])))
            item.SetEnd(pcbnew.VECTOR2I(*move([v/1e6 for v in last])))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    warning=dict(type='track_dangling',items=[dict(uuid=source_ids[0])])
    original=dict(violations=[] if fault!='inherited' else [warning])
    proposed=dict(violations=[warning])
    return source,source_ids[0],original,proposed


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_trim_only_the_dangling_excess_not_the_interior_junction_bridge(tmp_path,rotation,mirror):
    source,uid,original,proposed=fixture(tmp_path,rotation,mirror);before=source.read_bytes()
    result=cleanup.construct(source,tmp_path/'child',board_hint='synthetic',original_native=original,proposed_native=proposed)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['retired_track_uuids']==[uid] and len(result['incoming_track_uuids'])==1
    assert result['independent_exact_source_delta_receiving']['all_prior_native_terminal_partitions_preserved']
    assert result['independent_current_nonregression']['ok']
    assert source.read_bytes()==before and not result['release_authority'] and not result['current_authority']


@pytest.mark.parametrize('fault',['locked','group','sensitive','pad','inherited','body_contact'])
def test_unowned_or_anchored_or_unreported_excess_cannot_be_trimmed(tmp_path,fault):
    source,uid,original,proposed=fixture(tmp_path,fault=fault);before=source.read_bytes()
    result=cleanup.construct(source,tmp_path/'child',board_hint='synthetic',original_native=original,proposed_native=proposed)
    assert result['ok'] and result['complete'] and not result['changed'],result
    assert source.read_bytes()==before and not (tmp_path/'child').exists()


@pytest.mark.parametrize('value',[True,0,-1,30.01,float('nan'),float('inf'),'20'])
def test_transaction_work_limit_is_explicit_finite_and_bounded(tmp_path,value):
    source,uid,original,proposed=fixture(tmp_path);before=source.read_bytes()
    result=cleanup.construct(source,tmp_path/'child',board_hint='synthetic',original_native=original,
        proposed_native=proposed,timeout_s=value)
    assert not result['ok'] and not result['complete'] and result['errors']
    assert source.read_bytes()==before and not (tmp_path/'child').exists()
