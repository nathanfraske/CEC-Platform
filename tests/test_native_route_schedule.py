import pcbnew
import pytest


def test_explicit_constrained_routes_precede_more_flexible_scalar_work_only_at_equal_width():
    from cec_native_route_schedule import order
    rows=[dict(uid='a',net='flexible',width=200000),dict(uid='b',net='analog',width=200000),
          dict(uid='c',net='power',width=600000),dict(uid='d',net='GND',width=200000)]
    ordinary={'flexible'}
    legacy=order(rows,['flexible'],ordinary_nets=ordinary)
    new=order(rows,['flexible'],ordinary_nets=ordinary,constrained_before_ordinary=True)
    assert [r['uid'] for r in legacy]==['c','d','a','b']
    assert [r['uid'] for r in new]==['c','d','b','a']
    assert rows[0]['uid']=='a'


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_constrained_order_mode_is_literal_boolean(flag):
    from cec_native_route_schedule import order
    with pytest.raises(ValueError,match='explicit_constrained_route_order_required'):
        order([dict(uid='one',net='unknown',width=200000)],[],ordinary_nets=set(),
            constrained_before_ordinary=flag)
from cec_native_route_schedule import order,endpoint_faces,retained_component_pairs
from test_lastmile import _board


def test_scarce_access_order_never_outranks_wider_source_copper_or_same_width_ground():
    rows=[dict(uid='a',net='LOW_ALPHABETICAL',width=200000),
          dict(uid='b',net='SCARCE_RENAMED',width=200000),
          dict(uid='c',net='RATED_RENAMED',width=3230592),dict(uid='d',net='GND',width=200000)]
    before=[dict(r) for r in rows]
    got=order(rows,['SCARCE_RENAMED'],ordinary_nets={'SCARCE_RENAMED','LOW_ALPHABETICAL'})
    assert [r['uid'] for r in got]==['c','d','b','a'] and rows==before


def test_no_priority_keeps_the_legacy_exact_identity_order_not_alphabetical_net_order():
    rows=[dict(uid='b',net='AAA',width=200000),dict(uid='a',net='ZZZ',width=200000)]
    assert [r['uid'] for r in order(rows,[],ordinary_nets=set())]==['a','b']


@pytest.mark.parametrize('priorities',[['POWER'],['X','X'],['X']*9,[None],[True]])
def test_protected_unknown_or_unbounded_priorities_cannot_be_inserted(priorities):
    with pytest.raises(ValueError):order([dict(uid='u',net='X',width=200000)],priorities,ordinary_nets={'X'})


@pytest.mark.parametrize('kind',['via','pth','smd','npth','nearby'])
def test_only_exact_existing_plating_grants_its_actual_native_faces(kind):
    board=_board([(10,10,'RENAMED')]);board.SetCopperLayerCount(6)
    pad=next(p for f in board.GetFootprints() for p in f.Pads())
    at=tuple(pad.GetPosition());faces=[int(l) for l in board.GetEnabledLayers().CuStack()]
    if kind in ('via','nearby'):
        pad.SetPosition(pcbnew.VECTOR2I_MM(30,30))
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I(at[0]+(1000 if kind=='nearby' else 0),at[1]))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(board.FindNet('RENAMED'));board.Add(v)
    elif kind in ('pth','npth'):
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if kind=='pth' else pcbnew.PAD_ATTRIB_NPTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    r=endpoint_faces(board,at,'RENAMED',faces,pcbnew.F_Cu,ordinary_nets={'RENAMED'})
    assert r['layer_ids']==(faces if kind in ('via','pth') else [pcbnew.F_Cu])
    assert bool(r['native_uuids']) is (kind in ('via','pth'))
    assert not r['new_barrel_or_current_credit'] and not r['release_authority']


def test_ordinary_endpoint_model_cannot_be_used_as_power_current_permission():
    board=_board([(10,10,'POWER')])
    with pytest.raises(ValueError):endpoint_faces(board,(10000000,10000000),'POWER',[0,2],0,ordinary_nets=set())


def test_alternative_port_never_acquires_a_different_same_net_island():
    import time
    import cec_force_current as force
    from test_field_proposals import track
    board=_board([(5,5,'SCALAR'),(25,5,'SCALAR'),(10,25,'SCALAR')])
    vias=[]
    for x,y in ((28,5),(10,25)):
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(x,y));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(0,2);v.SetNet(board.FindNet('SCALAR'));board.Add(v);vias.append(v)
    track(board,'SCALAR',(25,5),(28,5))
    pairs,proof=retained_component_pairs(board,'SCALAR',(5000000,5000000),(25000000,5000000),0,[0,2],
        ordinary_nets={'SCALAR'},deadline=time.monotonic()+3.)
    ids={u for pair in pairs for p in pair for u in p['native_uuids']}
    assert force._uid(vias[0]) in ids and force._uid(vias[1]) not in ids
    assert not proof['already_connected'] and not proof['release_authority']
    assert not proof['new_barrel_or_current_credit']


def test_retained_connected_through_copper_needs_no_extra_ordinary_bridge():
    import time
    from test_field_proposals import track
    board=_board([(5,5,'SCALAR'),(25,5,'SCALAR')]);track(board,'SCALAR',(5,5),(25,5))
    pairs,proof=retained_component_pairs(board,'SCALAR',(5000000,5000000),(25000000,5000000),0,[0,2],
        ordinary_nets={'SCALAR'},deadline=time.monotonic()+3.)
    assert not pairs and proof['already_connected'] and not proof['release_authority']


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_same_xy_real_barrel_faces_are_alternatives_not_duplicate_requests(turn,mirror):
    import time
    import cec_force_current as force
    import cec_field_coupling as field
    import cec_fr as fr
    from test_field_proposals import track
    board=_board([]);board.SetCopperLayerCount(6)
    board.Add(pcbnew.NETINFO_ITEM(board,'SCALAR'))
    vias=[]
    for x in (5,25):
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(x,10))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(0,2);v.SetNet(board.FindNet('SCALAR'));board.Add(v);vias.append(v)
    wall=track(board,'FOREIGN',(15,1),(15,29),width=1.)
    origin=pcbnew.VECTOR2I(0,0)
    for item in [*board.GetTracks(),*board.GetDrawings()]:
        if mirror:item.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        item.Rotate(origin,pcbnew.EDA_ANGLE(turn*90,pcbnew.DEGREES_T))
    start,end=[tuple(v.GetPosition()) for v in vias];face=int(wall.GetLayer())
    other=0 if face==2 else 2
    before=field._field_snapshot_inventory(board)
    pairs,proof=retained_component_pairs(board,'SCALAR',start,end,face,[0,6,8,2],
        ordinary_nets={'SCALAR'},deadline=time.monotonic()+3.)
    assert pairs and any(all(set(p['layers'])=={0,2,6,8} for p in pair) for pair in pairs)
    assert all(tuple(p['at_nm'])==at for pair in pairs for p,at in zip(pair,(start,end)))
    assert all(p['actual_retained_plated'] for pair in pairs for p in pair)
    s,t=[pcbnew.VECTOR2I(*at) for at in (start,end)];code=board.GetNetcodeFromNetname('SCALAR')
    assert not fr._tap_foreign_clear(board,s,t,200000,face,200000,{code})
    assert fr._tap_foreign_clear(board,s,t,200000,other,200000,{code})
    assert before==field._field_snapshot_inventory(board)
    assert not proof['new_barrel_or_current_credit']
