"""Saved-source chain proposals stop at actual terminals and branch copper."""
import math
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import root_native_scalar_chain_scope_20261015 as chain


def fixture(angle=0,mirror=False,layer=pcbnew.F_Cu):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'/UNRELATED/SCALAR');board.Add(net)
    c,s=round(math.cos(math.radians(angle))),round(math.sin(math.radians(angle)))
    def point(p):
        x,y=p;x*=(-1 if mirror else 1)
        return pcbnew.VECTOR2I_MM(20+c*x-s*y,20+s*x+c*y)
    tracks=[]
    for a,b in [((0,0),(1,0)),((1,0),(0,1)),((-2,0),(0,0)),((0,1),(0,3))]:
        t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(layer);t.SetWidth(200000)
        t.SetStart(point(a));t.SetEnd(point(b));t.SetLocked(True);board.Add(t);tracks.append(t)
    issue=dict(type='acute_backtrack',net=net.GetNetname(),track_uuids=[force._uid(t) for t in tracks[:2]])
    return board,tracks,issue


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_chain_variants_are_parametric_and_keep_exact_source_locks(angle,mirror,layer):
    b,tracks,issue=fixture(angle,mirror,layer);old=field._field_snapshot_inventory(b)
    rows=chain.request_variants(b,[issue],{issue['net']},max_extra_tracks=2)
    assert {len(r['source_track_uuids']) for r in rows}=={2,3,4}
    assert len(rows)==4
    assert any(set(r['source_track_uuids'])=={force._uid(t) for t in tracks} for r in rows)
    assert all(r['typed_chain']['native_saved_boundary_and_partition_receiving_required']
        and not r['typed_chain']['release_authority'] for r in rows)
    assert all(set(r['typed_chain']['locked_scope_used'])==set(r['source_track_uuids']) for r in rows)
    assert field._field_snapshot_inventory(b)==old


@pytest.mark.parametrize('boundary',['pad','via','tee','width','group','body_tee'])
def test_extension_cannot_cross_actual_native_terminal_branch_width_or_owner(boundary):
    b,tracks,issue=fixture();at=tracks[0].GetStart()
    if boundary=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);p.SetNet(tracks[0].GetNet());p.SetNumber('1')
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
        p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetPosition(at);fp.Add(p)
    elif boundary=='via':
        via=pcbnew.PCB_VIA(b);via.SetNet(tracks[0].GetNet());via.SetPosition(at)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetWidth(600000);via.SetDrill(300000);b.Add(via)
    elif boundary=='width':tracks[2].SetWidth(250000)
    elif boundary=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[2])
    else:
        t=pcbnew.PCB_TRACK(b);t.SetNet(tracks[0].GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
        if boundary=='tee':t.SetStart(at);t.SetEnd(at+pcbnew.VECTOR2I_MM(0,-2))
        else:t.SetStart(at+pcbnew.VECTOR2I_MM(0,-2));t.SetEnd(at+pcbnew.VECTOR2I_MM(0,2))
        b.Add(t)
    old=field._field_snapshot_inventory(b)
    rows=chain.request_variants(b,[issue],{issue['net']},max_extra_tracks=2)
    assert rows and all(force._uid(tracks[2]) not in r['source_track_uuids'] for r in rows)
    assert field._field_snapshot_inventory(b)==old


def test_missing_positive_ordinary_role_returns_no_construction_permission():
    b,tracks,issue=fixture()
    assert chain.request_variants(b,[issue],set(),max_extra_tracks=2)==[]


@pytest.mark.parametrize('limit',[-1,5,True,float('inf')])
def test_unbounded_or_implicit_extension_budget_refuses(limit):
    b,tracks,issue=fixture()
    with pytest.raises(ValueError):chain.request_variants(b,[issue],{issue['net']},max_extra_tracks=limit)
