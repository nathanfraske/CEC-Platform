import copy
import math
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_native_parallel_bus as native


def fixture():
    board=pcbnew.BOARD()
    info=pcbnew.NETINFO_ITEM(board,'renamed-aggregate',1);board.Add(info)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary-reference');board.Add(fp)
    pads=[]
    for x in (10.,60.):
        p=pcbnew.PAD(fp);p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetSize(pcbnew.VECTOR2I(3000000,3000000))
        p.SetDrillSize(pcbnew.VECTOR2I(1000000,1000000));p.SetLayerSet(pcbnew.LSET.AllCuMask())
        p.SetPosition(pcbnew.VECTOR2I(round(x*1e6),20000000));p.SetNetCode(1)
        fp.Add(p);pads.append(p)
    paths=[]
    for uid,layer,y in [('front',pcbnew.F_Cu,25.),('back',pcbnew.B_Cu,27.)]:
        ids=[];points=[(10.,20.75),(10.,y),(60.,y),(60.,20.75)]
        for a,b in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(*(round(v*1e6) for v in a)))
            t.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6) for v in b)))
            t.SetWidth(4500000);t.SetLayer(layer);t.SetNetCode(1);board.Add(t)
            ids.append(str(t.m_Uuid.AsString()))
        paths.append(dict(id=uid,track_uuids=ids))
    terminals=[str(p.m_Uuid.AsString()) for p in pads]
    return board,terminals,paths


def inspect(b,t,p,**k):return native.inspect(b,'renamed-aggregate',t,p,**k)


def bounds(result):
    return {q['id']:dict(copper_mm=[.063,.077],series_ohm=[0.,.0005],
        temperature_c=[20.,70.]) for q in result['branches']}


def screen(result,b):
    return native.conditional_screen(result,dict(amps=20.,geometry_margin=1.25,
        margin_included=False),b,permitted_layers=['F.Cu','B.Cu'])


def test_native_saved_dimensions_and_finite_common_contacts_are_required():
    b,t,p=fixture();r=inspect(b,t,p)
    assert r['complete'] and r['finite_native_common_contacts_verified']
    assert r['actual_branch_track_count']==6
    assert all(q['segments'][0]['width_mm']==[4.5,4.5] for q in r['branches'])
    assert not r['routing_admitted'] and not r['release_authority']
    assert not r['equipotential_nodes_qualified'] and not r['terminal_or_barrel_capacity_qualified']
    assert not r['contact_resistance_bounds_qualified'] and not r['coupled_thermal_qualified']
    s=screen(r,bounds(r));assert s['ipc_width_screen_ok']
    assert s['supplied_bounds_are_conditions_not_qualification']
    assert all(q['current_interval_a'][1]>10. for q in s['branches'])
    assert not s['routing_admitted'] and not s['release_authority']


def test_reversed_branches_and_terminals_preserve_native_lengths():
    b,t,p=fixture();first=inspect(b,t,p)
    for row in p:row['track_uuids'].reverse()
    p.reverse();t.reverse();second=inspect(b,t,p)
    def lens(r):return {q['id']:sorted(s['length_mm'][0] for s in q['segments']) for q in r['branches']}
    assert lens(first)==lens(second)


@pytest.mark.parametrize('mutation',[lambda p:p[1].update(id=p[0]['id']),
    lambda p:p[1].update(track_uuids=p[0]['track_uuids']),
    lambda p:p[0]['track_uuids'].append(p[0]['track_uuids'][0]),
    lambda p:p[0].update(track_uuids=['stale']),
    lambda p:p[0].update(extra='caller-cannot-skip-native-checks')])
def test_duplicates_stale_ids_and_unspecified_override_flags_are_refused(mutation):
    b,t,p=fixture();mutation(p)
    with pytest.raises(ValueError):inspect(b,t,p)


def test_same_face_physically_shared_copper_is_not_an_extra_branch():
    b,t,p=fixture()
    ids=set(p[1]['track_uuids'])
    for item in b.GetTracks():
        if str(item.m_Uuid.AsString()) in ids:item.SetLayer(pcbnew.F_Cu)
    with pytest.raises(ValueError,match='shared_copper'):inspect(b,t,p)


def test_airwire_to_a_pad_and_a_hole_without_copper_do_not_count_as_nodes():
    b,t,p=fixture();items={str(i.m_Uuid.AsString()):i for i in b.GetTracks()}
    item=items[p[0]['track_uuids'][0]];item.SetStart(pcbnew.VECTOR2I(15000000,20000000))
    with pytest.raises(ValueError,match='finite_endpoint'):inspect(b,t,p)
    b,t,p=fixture();pads=[pad for f in b.GetFootprints() for pad in f.Pads()]
    pads[0].SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    with pytest.raises(ValueError,match='plated_pad'):inspect(b,t,p)


def test_hidden_transition_or_an_arc_is_not_a_planar_branch():
    b,t,p=fixture();items={str(i.m_Uuid.AsString()):i for i in b.GetTracks()}
    items[p[0]['track_uuids'][1]].SetLayer(pcbnew.B_Cu)
    with pytest.raises(ValueError,match='hidden_layer'):inspect(b,t,p)


def test_non45_stroke_is_not_accepted_as_a_bus_path():
    b,t,p=fixture();items={str(i.m_Uuid.AsString()):i for i in b.GetTracks()}
    items[p[0]['track_uuids'][1]].SetEnd(pcbnew.VECTOR2I(60000000,25500000))
    with pytest.raises(ValueError,match='noncanonical'):inspect(b,t,p)


@pytest.mark.parametrize('timeout',[0,11,float('nan'),float('inf'),True])
def test_bounded_deadline_required(timeout):
    b,t,p=fixture()
    with pytest.raises(ValueError):inspect(b,t,p,timeout_s=timeout)


def test_all_resistance_material_and_temperature_bounds_are_explicit():
    b,t,p=fixture();r=inspect(b,t,p);v=bounds(r)
    for bad in ({},{'front':v['front']},dict(v,extra=v['front'])):
        with pytest.raises(ValueError):screen(r,bad)
    for field in ('series_ohm','copper_mm','temperature_c'):
        bad=copy.deepcopy(v);bad['front'].pop(field)
        with pytest.raises(ValueError):screen(r,bad)


def test_thinner_native_body_is_screened_instead_of_using_requested_width():
    b,t,p=fixture();ids=set(p[0]['track_uuids'])
    for item in b.GetTracks():
        if str(item.m_Uuid.AsString()) in ids:item.SetWidth(1000000)
    r=inspect(b,t,p);assert not screen(r,bounds(r))['ipc_width_screen_ok']


def test_extra_same_net_injection_or_branch_point_is_reported_not_idealised():
    b,t,p=fixture();extra=pcbnew.PCB_TRACK(b)
    extra.SetStart(pcbnew.VECTOR2I(30000000,25000000));extra.SetEnd(pcbnew.VECTOR2I(30000000,35000000))
    extra.SetWidth(1000000);extra.SetLayer(pcbnew.F_Cu);extra.SetNetCode(1);b.Add(extra)
    r=inspect(b,t,p)
    assert r['additional_source_port_network_receiving_required']
    assert r['additional_same_net_contacts'][0]['uuid']==str(extra.m_Uuid.AsString())
    assert screen(r,bounds(r))['additional_source_port_network_receiving_required']


def test_native_inputs_and_interval_inputs_are_not_mutated():
    b,t,p=fixture();before=copy.deepcopy(p)
    coords={str(i.m_Uuid.AsString()):(tuple(i.GetStart()),tuple(i.GetEnd()),i.GetWidth()) for i in b.GetTracks()}
    r=inspect(b,t,p);v=bounds(r);old=copy.deepcopy(v);screen(r,v)
    assert p==before and v==old
    assert coords=={str(i.m_Uuid.AsString()):(tuple(i.GetStart()),tuple(i.GetEnd()),i.GetWidth()) for i in b.GetTracks()}


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_rotations_and_world_translations_have_no_board_coordinate_policy(angle):
    b,t,p=fixture();first=inspect(b,t,p)
    origin=pcbnew.VECTOR2I(0,0);turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    delta=pcbnew.VECTOR2I(173000000,-24000000)
    for f in b.GetFootprints():f.Rotate(origin,turn);f.Move(delta)
    for item in b.GetTracks():item.Rotate(origin,turn);item.Move(delta)
    second=inspect(b,t,p)
    assert second['finite_native_common_contacts_verified']
    assert [[s['length_mm'] for s in q['segments']] for q in first['branches']]==[
        [s['length_mm'] for s in q['segments']] for q in second['branches']]
