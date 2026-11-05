"""Native owner/island identity regressions for strict saved routing replay."""
import time
import uuid
import pcbnew
import pytest
from cec_native_items import create_empty_board
import cec_force_current as force
import cec_native_partition_pair as paired

import cec_ordinary_route_receiving as owner

def fixture(ids=None,*,split_owned=False,change_unrelated=False):
    ids=ids or {name:str(uuid.uuid4())for name in('a','b','c','d','owned','unrelated')}
    board=create_empty_board();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'/arbitrary_renamed',1);board.Add(net)
    for name,at in [('a',(1,1)),('b',(9,1)),('c',(21,1)),('d',(26,1))]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(name);board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetPosition(pcbnew.VECTOR2I_MM(*at));p.m_Uuid.Clone(pcbnew.KIID(ids[name]));fp.Add(p)
    def zone(name,rects):
        z=pcbnew.ZONE(board);z.SetNet(net);z.SetLayer(0);z.m_Uuid.Clone(pcbnew.KIID(ids[name]));board.Add(z)
        shape=pcbnew.SHAPE_POLY_SET()
        for x0,y0,x1,y1 in rects:
            shape.NewOutline()
            for x,y in((x0,y0),(x1,y0),(x1,y1),(x0,y1)):shape.Append(round(x*1e6),round(y*1e6))
        z.Outline().Append(shape);z.SetFilledPolysList(0,shape);z.SetIsFilled(True);z.CacheTriangulation(0)
    zone('owned',[(0,0,2,2),(8,0,10,2)]if split_owned else[(0,0,10,2)])
    zone('unrelated',[(20,0,22,2),(25,0,27.1 if change_unrelated else 27,2)])
    return board,ids

def parts(board,**kw):return owner._partition(board,time.monotonic()+5.,**kw)
def canonical(rows):return{frozenset(r)for r in rows}
def zone_rows(board):return paired._inventory(board,time.monotonic()+5.,dict(items=100,polygons=20,vertices=1000))['zones']

def test_explicit_actual_zone_owner_omits_only_its_comparison_markers():
    board,ids=fixture();old=zone_rows(board);before=[force._item_key(i)for fp in board.GetFootprints()for i in fp.Pads()]
    rows=parts(board,retired_uuids={ids['owned']});keys=set().union(*rows)
    proxies={force._item_key(r['item'])for k,values in old.items()if k[0]==ids['owned']for r in values}
    unrelated={force._item_key(r['item'])for k,values in old.items()if k[0]==ids['unrelated']for r in values}
    assert not keys&proxies and unrelated<=keys and len(unrelated)==2
    assert set(before)<=keys
    assert len(rows)==3 # Two unrelated islands remain separate, not one owner bridge.
    assert len(next(r for r in rows if before[0]in r))==2 # Old owned copper STILL connects both pads.

@pytest.mark.parametrize('mode',['unknown_owner','derived_owned_proxy','one_unrelated_island_proxy'])
def test_unknown_or_partial_proxy_UUID_cannot_acquire_retirement(mode):
    board,ids=fixture();rows=zone_rows(board)
    if mode=='unknown_owner':requested=str(uuid.uuid4())
    else:
        chosen='owned'if mode=='derived_owned_proxy'else'unrelated'
        requested=next(force._uid(r['item'])for k,values in rows.items()if k[0]==ids[chosen]for r in values)
    assert canonical(parts(board,retired_uuids={requested}))==canonical(parts(board))

def test_retired_owner_keeps_original_material_in_graph_so_lost_bridge_refuses():
    before,ids=fixture();after,_=fixture(ids,split_owned=True)
    source=parts(before,retired_uuids={ids['owned']});keys=set().union(*source)
    child=parts(after,retained_keys=keys)
    assert canonical(source)!=canonical(child)
    # Comparison pads survive but their original connection has really split.
    assert sum(len(p)==2 for p in source)>sum(len(p)==2 for p in child)

def test_unrelated_zone_island_fill_identity_stays_strict():
    before,ids=fixture();after,_=fixture(ids,change_unrelated=True)
    keys=set().union(*parts(before,retired_uuids={ids['owned']}))
    with pytest.raises(ValueError,match='surviving_source_conductor_missing'):parts(after,retained_keys=keys)

def test_ambiguous_native_owner_identity_is_not_hidden_by_retirement():
    board,ids=fixture();zones=list(board.Zones());zones[1].m_Uuid.Clone(zones[0].m_Uuid)
    with pytest.raises(ValueError,match='ambiguous_native_parent_identity'):parts(board,retired_uuids={ids['owned']})
