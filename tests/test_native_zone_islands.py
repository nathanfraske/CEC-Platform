"""One native zone owner cannot short its disconnected filled islands."""
import time

import pcbnew
import pytest
import cec_cell_ground_cut_boundaries as ground
import cec_force_current as force
import cec_native_fill_geometry as fill
import cec_native_zone_islands as islands


def fixture(*,face=pcbnew.F_Cu,hole=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.Add(pcbnew.NETINFO_ITEM(board,'GND'))
    rings=[[[[0,0],[4000000,0],[4000000,4000000],[0,4000000]]],
        [[[6000000,0],[10000000,0],[10000000,4000000],[6000000,4000000]]]]
    if hole:rings[0].append([[1000000,1000000],[1000000,3000000],
        [3000000,3000000],[3000000,1000000]])
    shape=fill.reconstruct(rings,time.monotonic()+5.)
    zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet('GND'));zone.SetLayer(face)
    zone.Outline().Append(shape);zone.SetFilledPolysList(face,shape);zone.SetIsFilled(True)
    board.Add(zone)
    for n,at in enumerate([(500000,500000),(6500000,500000)]):
        t=pcbnew.PCB_TRACK(board);t.SetNet(zone.GetNet());t.SetLayer(face);t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I(*at));t.SetEnd(pcbnew.VECTOR2I(at[0]+200000,at[1]));board.Add(t)
    return board,zone


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('hole',[False,True])
def test_native_parts_keep_disconnected_islands_and_literal_fill(face,hole):
    board,z=fixture(face=face,hole=hole)
    before=ground.row._source_binding(board)
    proxies=islands.decompose(board,z,deadline=time.monotonic()+5.)
    assert len(proxies)==2
    assert len({force._uid(p) for p in proxies})==2
    assert all(p.GetNetname()=='GND' and list(p.GetLayerSet().CuStack())==[face] for p in proxies)
    rebuilt=pcbnew.SHAPE_POLY_SET()
    for p in proxies:rebuilt.Append(p.GetFilledPolysList(face))
    assert fill.identity(rebuilt,time.monotonic()+5.)==fill.identity(z.GetFilledPolysList(face),time.monotonic()+5.)
    items=ground._items(board)
    assert len(ground._parts(items,time.monotonic()+5.,force._item_key))==2
    assert before==ground.row._source_binding(board)
    # A second exact read uses stable physical identities, not Python handles
    # or the incidental ordering of the original filled polygon array.
    assert {force._item_key(i) for i in items}=={force._item_key(i) for i in ground._items(board)}


def test_only_actual_native_bridge_joins_two_zone_islands():
    board,z=fixture()
    t=pcbnew.PCB_TRACK(board);t.SetNet(z.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I(500000,500000));t.SetEnd(pcbnew.VECTOR2I(6500000,500000));board.Add(t)
    assert len(ground._parts(ground._items(board),time.monotonic()+5.,force._item_key))==1


def test_hole_is_not_solid_copper_and_foreign_face_does_not_join():
    board,z=fixture(hole=True)
    for face,at in [(pcbnew.F_Cu,(2000000,2000000)),(pcbnew.B_Cu,(500000,500000))]:
        t=pcbnew.PCB_TRACK(board);t.SetNet(z.GetNet());t.SetLayer(face);t.SetWidth(100000)
        t.SetStart(pcbnew.VECTOR2I(*at));t.SetEnd(pcbnew.VECTOR2I(at[0]+100000,at[1]));board.Add(t)
    assert len(ground._parts(ground._items(board),time.monotonic()+5.,force._item_key))==4


@pytest.mark.parametrize('fault',['unfilled','rule_area','deadline','no_fill'])
def test_unknown_native_material_stays_refused(fault):
    board,z=fixture()
    deadline=time.monotonic()+5.
    if fault=='unfilled':z.SetIsFilled(False)
    elif fault=='rule_area':z.SetIsRuleArea(True)
    elif fault=='deadline':deadline=time.monotonic()-1.
    else:z.UnFill()
    with pytest.raises(ValueError):islands.decompose(board,z,deadline=deadline)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('hole',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_exact_repeated_native_fill_records_are_one_physical_island(face,hole,reverse):
    board,z=fixture(face=face,hole=hole)
    deadline=time.monotonic()+5.
    original=fill.snapshot(z.GetFilledPolysList(face),deadline)
    repeated=original+[original[0],original[1],original[0]]
    if reverse:
        repeated=[[[*reversed(ring)]for ring in polygon]for polygon in reversed(repeated)]
    literal=fill.reconstruct(repeated,deadline)
    z.SetFilledPolysList(face,literal);z.SetIsFilled(True)
    before=z.GetFilledPolysList(face).Format()
    proxies=islands.decompose(board,z,deadline=deadline)
    assert len(proxies)==2 and len({force._uid(p)for p in proxies})==2
    assert len(ground._parts(ground._items(board),deadline,force._item_key))==2
    assert z.GetFilledPolysList(face).Format()==before
    # No occurrence-index identity: ordering/multiplicity changes cannot
    # manufacture another conductor, while actual Source bytes stay intact.
    expected=fill.reconstruct(original,deadline)
    z.SetFilledPolysList(face,expected)
    assert {force._item_key(p)for p in proxies}=={force._item_key(p)for p in
        islands.decompose(board,z,deadline=deadline)}


def test_saved_reloaded_duplicate_native_fill_keeps_holes_and_disconnection(tmp_path):
    board,z=fixture(hole=True);deadline=time.monotonic()+5.
    # Filled_polygon persistence uses fracture bridges, as actual KiCad fill
    # does. An explicit unfractured hole is not a saved filled-record format.
    fractured=z.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();fractured.Fracture(False)
    rows=fill.snapshot(fractured,deadline)
    z.SetFilledPolysList(pcbnew.F_Cu,fill.reconstruct([*rows,*rows,*rows],deadline))
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    source=path.read_bytes();saved=pcbnew.LoadBoard(str(path));zone=list(saved.Zones())[0]
    assert zone.GetFilledPolysList(pcbnew.F_Cu).OutlineCount()==6
    proxies=islands.decompose(saved,zone,deadline=deadline)
    assert len(proxies)==2
    assert len(ground._parts(ground._items(saved),deadline,force._item_key))==2
    # KiCad serializes explicit holes as exact zero-width fracture bridges.
    # Prove the actual saved void rather than requiring one representation.
    track=pcbnew.PCB_TRACK(saved);track.SetNet(zone.GetNet());track.SetLayer(pcbnew.F_Cu)
    track.SetWidth(100000);track.SetStart(pcbnew.VECTOR2I(2000000,2000000))
    track.SetEnd(pcbnew.VECTOR2I(2100000,2000000));saved.Add(track)
    assert len(ground._parts(ground._items(saved),deadline,force._item_key))==3
    assert path.read_bytes()==source


@pytest.mark.parametrize('fault',['other_island','changed_hole','one_nm_shift'])
def test_digest_collision_never_collapses_different_native_material(monkeypatch,fault):
    board,z=fixture(hole=True);deadline=time.monotonic()+5.
    rows=fill.snapshot(z.GetFilledPolysList(pcbnew.F_Cu),deadline)
    other=[[list(point)for point in ring]for ring in rows[0]]
    if fault=='other_island':other=rows[1]
    elif fault=='changed_hole':other[1][0][0]+=1
    else:other=[[[x+1,y]for x,y in ring]for ring in other]
    z.SetFilledPolysList(pcbnew.F_Cu,fill.reconstruct([rows[0],other],deadline))
    before=z.GetFilledPolysList(pcbnew.F_Cu).Format();real=fill.identity
    def forged(shape,lease,**options):
        _,count=real(shape,lease,**options)
        return 'synthetic_digest_collision',count
    monkeypatch.setattr(fill,'identity',forged)
    with pytest.raises(ValueError,match='ambiguous_duplicate_native_zone_island'):
        islands.decompose(board,z,deadline=deadline)
    assert z.GetFilledPolysList(pcbnew.F_Cu).Format()==before


def test_duplicate_empty_area_has_no_material_equality_authority():
    deadline=time.monotonic()+5.
    line=fill.reconstruct([[[[0,0],[1000000,0],[2000000,0]]]],deadline)
    with pytest.raises(ValueError,match='ambiguous_duplicate_native_zone_island'):
        islands._same_native_material(line,line,deadline)


@pytest.mark.parametrize('foreign_net',[False,True])
def test_alias_zone_owner_is_still_refused_by_paired_inventory(foreign_net):
    import cec_native_partition_pair as paired
    board,z=fixture();other=pcbnew.ZONE(z)
    if foreign_net:
        board.Add(pcbnew.NETINFO_ITEM(board,'DIFFERENT'))
        other.SetNet(board.FindNet('DIFFERENT'))
    board.Add(other)
    with pytest.raises(ValueError,match='ambiguous_native_parent_identity'):
        paired.compare(board,board,timeout_s=5.)


def test_equality_checks_do_not_borrow_time_after_deadline():
    board,z=fixture();shape=z.GetFilledPolysList(pcbnew.F_Cu)
    with pytest.raises(ValueError,match='native_zone_island_deadline'):
        islands._same_native_material(shape,shape,time.monotonic()-1.)
