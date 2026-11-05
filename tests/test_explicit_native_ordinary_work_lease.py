"""Larger work leases do not enlarge electrical or source-cut authority."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_ordinary_tree as tree
import cec_ordinary_route_receiving as ordinary
from cec_local_copper_cell import copper_inventory
from cec_native_items import discard_items
from test_ordinary_route_receiving import fixture


def fragmented(tmp_path,count,rotation=0,locked=False):
    source,child,uid,net=fixture(tmp_path,rotation=rotation,locked=locked)
    b=pcbnew.LoadBoard(str(source));old=next(t for t in b.GetTracks() if force._uid(t)==uid)
    start,end=list(old.GetStart()),list(old.GetEnd());prototype=old.Duplicate();discard_items(b,[old]);ids=[]
    points=[[start[j]+(end[j]-start[j])*i//count for j in (0,1)] for i in range(count+1)]
    for first,last in zip(points,points[1:]):
        t=prototype.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*first))
        t.SetEnd(pcbnew.VECTOR2I(*last));b.Add(t);ids.append(force._uid(t))
    field._save_field_snapshot(b,source)
    return source,child,ids,net


@pytest.mark.parametrize('count',[33,64,128])
@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('locked',[False,True])
def test_real_saved_larger_cut_requires_explicit_lease_and_preserves_every_terminal(tmp_path,count,rotation,locked):
    source,child,ids,_=fragmented(tmp_path,count,rotation,locked);original=(source.read_bytes(),child.read_bytes())
    kwargs=dict(retired_track_uuids=ids,allow_locked_track_uuids=ids if locked else [],board_hint='synthetic')
    refused=ordinary.receive(source,child,**kwargs)
    assert not refused['ok'] and not refused['complete']
    proof=ordinary.receive(source,child,**kwargs,max_retired_tracks=count)
    assert proof['ok'] and proof['complete'],proof
    assert proof['max_retired_tracks']==count and set(proof['retired_track_uuids'])==set(ids)
    assert proof['all_prior_native_terminal_partitions_preserved']
    assert proof['all_prior_surviving_copper_junctions_preserved']
    assert proof['original_power_pair_sense_and_placement_geometry_exact']
    assert not proof['power_authority'] and not proof['release_authority']
    assert original==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('limit',[0,-1,True,129,64.0,'64',None])
def test_bad_receiver_lease_refuses_before_reading_families(tmp_path,limit):
    proof=ordinary.receive(tmp_path/'missing',tmp_path/'also-missing',retired_track_uuids=['x'],
        board_hint='synthetic',max_retired_tracks=limit)
    assert not proof['ok'] and not proof['complete']
    assert proof['errors']==['ValueError:invalid_ordinary_receiving_budget_or_identity']


@pytest.mark.parametrize('fault',['boundary','power_width','sidecar','scope','barrels','pose'])
def test_explicit_larger_scope_never_waives_role_boundary_pose_or_via_proofs(tmp_path,fault):
    source,child,ids,net=fragmented(tmp_path,64);kwargs={}
    if fault in ('boundary','pose'):
        b=pcbnew.LoadBoard(str(child))
        if fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
        else:
            tracks=[t for t in b.GetTracks() if t.GetNetname()==net];prototype=tracks[0].Duplicate()
            discard_items(b,tracks);prototype.m_Uuid.Clone(pcbnew.KIID())
            prototype.SetStart(pcbnew.VECTOR2I_MM(5,10));prototype.SetEnd(pcbnew.VECTOR2I_MM(5,11));b.Add(prototype)
        field._save_field_snapshot(b,child)
    elif fault=='power_width':
        b=pcbnew.LoadBoard(str(source))
        for t in b.GetTracks():
            if force._uid(t) in ids:t.SetWidth(500000)
        field._save_field_snapshot(b,source)
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='scope':kwargs['allow_locked_track_uuids']=['not-in-the-literal-source-cut']
    else:kwargs['retired_via_uuids']=['not-a-proved-source-barrel-'+str(i) for i in range(5)]
    proof=ordinary.receive(source,child,retired_track_uuids=ids,board_hint='synthetic',max_retired_tracks=64,**kwargs)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert not proof['power_authority'] and not proof['release_authority']


@pytest.mark.parametrize('count',[9,16])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_larger_integer_port_trees_remain_bounded_and_pose_independent(count,angle,mirror):
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return [x,y]
    ports={str(i):at(i*1000000,(i%3)*2000000) for i in range(count)}
    components=[['0','1'],*[[str(i)] for i in range(2,count)]]
    with pytest.raises(ValueError):tree.spanning_variants(ports,components)
    proposals=tree.spanning_variants(ports,components,maximum_ports=count)
    assert 1<=len(proposals)<=4 and all(len(v)==count-2 for v in proposals)
    assert proposals==tree.spanning_variants(dict(reversed(list(ports.items()))),list(reversed(components)),maximum_ports=count)


def many_native_ports():
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6);net=pcbnew.NETINFO_ITEM(b,'/renamed/scalar');b.Add(net)
    pads=[]
    for i in range(9):
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(net)
        p.SetPosition(pcbnew.VECTOR2I_MM(10+i,20));p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetLayerSet(pcbnew.LSET.AllCuMask());pads.append(p)
    ids=[]
    for i in range(64):
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I(10000000+8000000*i//64,20000000))
        t.SetEnd(pcbnew.VECTOR2I(10000000+8000000*(i+1)//64,20000000));b.Add(t);ids.append(force._uid(t))
    back=pcbnew.PCB_TRACK(b);back.SetNet(net);back.SetLayer(pcbnew.B_Cu);back.SetWidth(200000)
    back.SetStart(pads[0].GetPosition());back.SetEnd(pads[2].GetPosition());b.Add(back)
    return b,ids,str(net.GetNetname()),pads


def test_larger_native_port_graph_still_uses_real_retained_cross_layer_barrels_only():
    b,ids,net,pads=many_native_ports();before=copper_inventory(b)
    with pytest.raises(ValueError):tree.retained_port_components(b,net,int(pcbnew.F_Cu),ids)
    with pytest.raises(ValueError):tree.retained_port_components(b,net,int(pcbnew.F_Cu),ids,maximum_source_tracks=64)
    proof=tree.retained_port_components(b,net,int(pcbnew.F_Cu),ids,maximum_source_tracks=64,maximum_ports=16)
    assert len(proof['ports'])==9 and sorted(map(len,proof['components']))==[1]*6+[3]
    assert any(set(group)=={force._uid(p) for p in pads[:3]} for group in proof['components'])
    variants=tree.spanning_variants(proof['ports'],proof['components'],maximum_ports=16)
    assert len(variants[0])==6 and copper_inventory(b)==before
    assert not proof['source_cut_authorized'] and not proof['route_admitted']


@pytest.mark.parametrize('kwargs',[dict(maximum_source_tracks=True),dict(maximum_source_tracks=129),
    dict(maximum_ports=17),dict(maximum_ports=True),dict(maximum_ports=1)])
def test_native_port_work_lease_cannot_be_unbounded_or_implicit(kwargs):
    b,ids,net,_=many_native_ports()
    with pytest.raises(ValueError):tree.retained_port_components(b,net,int(pcbnew.F_Cu),ids,**kwargs)
