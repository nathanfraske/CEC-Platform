import time
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_native_component_ports as ports
from test_measurement_leaf import fixture


def test_pair_breadth_funds_distinct_physical_exits_without_dropping_exact_aliases():
    make = lambda x, layers=(0,): dict(at=(x, 0), layers=layers)
    target = make(10000000)
    rows = [(make(x), target) for x in (0, 1, 2, 3, 1000000, 2000000, 3000000)]
    # A retained all-layer contact is different authority, not a newly guessed
    # via. The caller supplies and still independently guards this endpoint.
    rows.append((make(1500000, (0, 2, 8)), target))
    result = ports.diverse_pairs(rows, point=lambda p:p['at'], layers=lambda p:p['layers'],
        limit=len(rows), breadth=4)
    assert result[0] is rows[0]
    assert result[1] is rows[-1]
    assert rows[6] in result[:4]
    assert [id(pair) for pair in result[4:]] == [id(pair) for pair in rows if pair not in result[:4]]
    assert {id(pair) for pair in result} == {id(pair) for pair in rows}
    assert len({pair[0]['at'] for pair in result}) == len(rows)


@pytest.mark.parametrize('quarter',range(4))
def test_pair_breadth_is_translation_and_quarter_turn_invariant(quarter):
    rows = [((x, y), (20_000_000, 15_000_000)) for x,y in
        [(0,0),(1,0),(3_000_000,1_000_000),(9_000_000,2_000_000),(2_000_000,8_000_000)]]
    def rotate(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        return x+41_000_000,y-12_000_000
    original = ports.diverse_pairs(rows, point=lambda p:p, layers=lambda p:(0,8), limit=4,breadth=4)
    moved = [(rotate(a),rotate(b)) for a,b in rows]
    actual = ports.diverse_pairs(moved, point=lambda p:p, layers=lambda p:(0,8), limit=4,breadth=4)
    assert actual == [(rotate(a),rotate(b)) for a,b in original]


@pytest.mark.parametrize('limit,breadth',[(0,1),(257,1),(4,0),(4,5),(64,33),(True,1)])
def test_pair_breadth_refuses_invalid_bounds(limit,breadth):
    with pytest.raises(ValueError):
        ports.diverse_pairs([], point=lambda p:p, layers=lambda p:(0,),limit=limit,breadth=breadth)


def test_pair_breadth_rejects_unbounded_or_nonexact_geometry():
    with pytest.raises(ValueError):
        ports.diverse_pairs([((0,0),(1,1))]*4097,point=lambda p:p,layers=lambda p:(0,))
    for rows,faces in [([((.1,0),(1,1))],(0,)),([((0,0),(1,1))],()),([((0,0),(1,1))],(.1,))]:
        with pytest.raises(ValueError):ports.diverse_pairs(rows,point=lambda p:p,layers=lambda p:faces)


@pytest.mark.parametrize('quarter',range(4))
def test_ports_use_exact_native_component_not_all_same_net_copper(quarter):
    board,pad,anchor,tracks,xy=fixture('renamed_net',quarter)
    island=pcbnew.PCB_TRACK(board);island.SetStart(xy((5,22)));island.SetEnd(xy((25,22)))
    island.SetWidth(200000);island.SetLayer(pcbnew.F_Cu);island.SetNetCode(pad.GetNetCode());board.Add(island)
    via=pcbnew.PCB_VIA(board);via.SetPosition(xy((15,10)));via.SetWidth(600000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNetCode(pad.GetNetCode());board.Add(via)
    boundary=dict(at_nm=list(xy((20,10))),layers=[pcbnew.F_Cu],native_uuids=[force._uid(anchor)])
    before=leaf._binding(board)
    rows=ports.endpoints(board,'renamed_net',boundary,toward_nm=list(xy((15,10))),deadline=time.monotonic()+2)
    assert rows[0]==boundary and len(rows)>1
    assert force._uid(island) not in {u for r in rows for u in r.get('native_uuids',[])}
    assert any(r.get('native_uuids')==[force._uid(via)] and pcbnew.B_Cu in r['layers'] for r in rows)
    assert before==leaf._binding(board)


@pytest.mark.parametrize('fault',['missing','off_seed','unrelated_component','wrong_net'])
def test_forged_native_boundary_fails_closed(fault):
    board,pad,anchor,tracks,xy=fixture('actual')
    boundary=dict(at_nm=list(xy((20,10))),layers=[pcbnew.F_Cu],native_uuids=[force._uid(anchor)])
    if fault=='missing':boundary['native_uuids']=['made_up']
    elif fault=='off_seed':boundary['at_nm']=list(xy((19,10)))
    elif fault=='wrong_net':anchor.SetNetCode(0)
    else:
        orphan=pcbnew.PCB_TRACK(board);orphan.SetStart(xy((20,10)))
        orphan.SetEnd(xy((20,12)));orphan.SetWidth(200000);orphan.SetLayer(pcbnew.B_Cu)
        orphan.SetNetCode(pad.GetNetCode());board.Add(orphan)
        boundary.update(native_uuids=[force._uid(anchor),force._uid(orphan)],layers=[pcbnew.F_Cu,pcbnew.B_Cu])
    before=leaf._binding(board)
    with pytest.raises(ValueError):ports.endpoints(board,'actual',boundary,toward_nm=list(xy((10,10))))
    assert before==leaf._binding(board)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('buried_blocker',[False,True])
def test_access_menu_preserves_real_pad_when_a_prior_uuid_track_alias_shares_its_centre(tmp_path,quarter,buried_blocker):
    board,pad,anchor,tracks,xy=fixture('renamed_contact',quarter)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';board.SetProperties(props)
    pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    import cec_field_coupling as field
    source=tmp_path/'native.kicad_pcb';field._save_field_snapshot(board,source)
    document=source.read_text().replace(force._uid(tracks[0]),'00000000-0000-4000-8000-000000000001')
    document=document.replace(force._uid(pad),'ffffffff-ffff-4fff-8fff-ffffffffffff')
    source.write_text(document);board=pcbnew.LoadBoard(str(source))
    pad=board.FindFootprintByReference('RENAMED_OWNER').FindPadByNumber('3')
    anchor=board.FindFootprintByReference('FIXED').FindPadByNumber('1')
    if buried_blocker:
        foreign=pcbnew.NETINFO_ITEM(board,'actual_foreign');board.Add(foreign)
        item=pcbnew.PCB_TRACK(board);item.SetStart(xy((9,10)));item.SetEnd(xy((11,10)))
        item.SetLayer(pcbnew.In2_Cu);item.SetWidth(200000);item.SetNet(foreign);board.Add(item)
    boundary=dict(at_nm=list(anchor.GetPosition()),layers=[pcbnew.F_Cu],native_uuids=[force._uid(anchor)])
    before=leaf._binding(board)
    rows=ports.endpoints(board,'renamed_contact',boundary,toward_nm=list(pad.GetPosition()),
        max_sites=32,deadline=time.monotonic()+3,prefer_native_via_access=True,minimum_local_via_web_nm=200000)
    native=[r for r in rows if r.get('pad_uuid')==force._uid(pad)]
    assert len(native)==1 and native[0]['native_via_access'] is not buried_blocker
    assert native[0]['at_nm']==list(pad.GetPosition())
    assert before==leaf._binding(board)


@pytest.mark.parametrize('options',[
    {'prefer_native_via_access':1}, {'prefer_native_via_access':True},
    {'prefer_native_via_access':True,'deadline':float('nan')},
    {'minimum_local_via_web_nm':True}, {'minimum_local_via_web_nm':-1},
    {'minimum_local_via_web_nm':2000001}])
def test_native_access_options_cannot_create_an_unbounded_or_nonexact_menu(options):
    board,pad,anchor,tracks,xy=fixture('native')
    boundary=dict(at_nm=list(anchor.GetPosition()),layers=[pcbnew.F_Cu],native_uuids=[force._uid(anchor)])
    with pytest.raises(ValueError):
        ports.endpoints(board,'native',boundary,toward_nm=list(pad.GetPosition()),**options)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('name', ['renamed_supply', '/other/native_domain'])
def test_site_diversity_retains_far_native_barrel_before_near_track_aliases(quarter,name):
    board,pad,anchor,tracks,xy=fixture(name,quarter)
    # All of these exact points belong to the original retained component;
    # they are not another same-net island and remain independent UUIDs.
    for index in range(16):
        route=pcbnew.PCB_TRACK(board)
        route.SetStart(xy((19.9+index*.001,10)))
        route.SetEnd(xy((19.901+index*.001,10)))
        route.SetWidth(200000);route.SetLayer(pcbnew.F_Cu)
        route.SetNetCode(pad.GetNetCode());board.Add(route)
    via=pcbnew.PCB_VIA(board);via.SetPosition(xy((10,10)))
    via.SetWidth(600000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNetCode(pad.GetNetCode());board.Add(via)
    island=pcbnew.PCB_TRACK(board);island.SetStart(xy((5,22)))
    island.SetEnd(xy((25,22)));island.SetWidth(200000)
    island.SetLayer(pcbnew.B_Cu);island.SetNetCode(pad.GetNetCode());board.Add(island)
    boundary=dict(at_nm=list(anchor.GetPosition()),layers=[pcbnew.F_Cu],
        native_uuids=[force._uid(anchor)])
    before=leaf._binding(board)
    options=dict(toward_nm=list(xy((20.1,10))),max_sites=4,
        deadline=time.monotonic()+3.)
    nearest=ports.endpoints(board,name,boundary,**options)
    diverse=ports.endpoints(board,name,boundary,diverse_native_sites=True,**options)
    assert nearest[0]==diverse[0]==boundary
    assert nearest[1]==diverse[1]  # Existing best exit retains precedence.
    assert force._uid(via) not in {u for r in nearest for u in r['native_uuids']}
    assert any(r['native_uuids']==[force._uid(via)] and pcbnew.B_Cu in r['layers']
        and r['at_nm']==list(via.GetPosition()) for r in diverse)
    assert force._uid(island) not in {u for r in diverse for u in r['native_uuids']}
    assert len(diverse)==5 and before==leaf._binding(board)


@pytest.mark.parametrize('invalid',[1,0,None,'yes'])
def test_site_diversity_requires_explicit_boolean_policy(invalid):
    board,pad,anchor,tracks,xy=fixture('scope')
    boundary=dict(at_nm=list(anchor.GetPosition()),layers=[pcbnew.F_Cu],
        native_uuids=[force._uid(anchor)])
    before=leaf._binding(board)
    with pytest.raises(ValueError,match='explicit_native_site_diversity_policy_required'):
        ports.endpoints(board,'scope',boundary,toward_nm=list(pad.GetPosition()),
            diverse_native_sites=invalid)
    assert before==leaf._binding(board)


@pytest.mark.parametrize('quarter',range(4))
def test_access_menu_uses_native_absolute_via_floor_not_smaller_process_menu(quarter):
    board,pad,anchor,tracks,xy=fixture('renamed_floor',quarter)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current'
    board.SetProperties(props);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    settings=board.GetDesignSettings()
    settings.m_ViasMinSize=1000000
    settings.m_MinThroughDrill=300000
    boundary=dict(at_nm=list(anchor.GetPosition()),layers=[pcbnew.F_Cu],
        native_uuids=[force._uid(anchor)])
    before=leaf._binding(board)
    rows=ports.endpoints(board,'renamed_floor',boundary,
        toward_nm=list(pad.GetPosition()),deadline=time.monotonic()+2.,
        prefer_native_via_access=True,diverse_native_sites=True)
    own=[r for r in rows if r.get('pad_uuid')==force._uid(pad)]
    assert len(own)==1 and own[0]['native_via_access'] is False
    assert settings.m_ViasMinSize==1000000
    assert before==leaf._binding(board)
