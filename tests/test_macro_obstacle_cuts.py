"""Native foreign-lead cooperation is bounded, positive and never a bus waiver."""
import time
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_cell_row_rebuild as rows
import cec_macro_obstacle_cuts as cuts
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,quarter=0,back=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for net in ('device_rail','foreign_signal','GND'):board.Add(pcbnew.NETINFO_ITEM(board,net))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('unrelated_device_owner');fp.SetPosition(pcbnew.VECTOR2I_MM(5,5))
    board.Add(fp);pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    ls=pcbnew.LSET();ls.AddLayer(face);pad.SetLayerSet(ls);pad.SetNet(board.FindNet('device_rail'))
    pad.SetPosition(pcbnew.VECTOR2I_MM(5,5));fp.Add(pad)
    first=track(board,'foreign_signal',(6,5),(8,5),width=.2);first.SetLayer(face)
    second=track(board,'foreign_signal',(8,5),(9,5),width=.2);second.SetLayer(face)
    if quarter:
        for item in [fp,first,second]:item.Rotate(pcbnew.VECTOR2I_MM(5,5),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    source=tmp_path/'native.kicad_pcb';field._save_field_snapshot(board,source)
    parent=pcbnew.LoadBoard(str(source));private=pcbnew.LoadBoard(str(source))
    moving=private.FindFootprintByReference(fp.GetReference())
    x,y=((2,0),(0,-2),(-2,0),(0,2))[quarter];moving.Move(pcbnew.VECTOR2I_MM(x,y))
    monkeypatch.setattr(cuts.ordinary,'eligible_nets',lambda *args:{'foreign_signal'})
    proposal=dict(board_hint='opaque_board',poses={fp.GetReference():[]})
    ids=[force._uid(first),force._uid(second)]
    return source,parent,private,proposal,ids


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_whole_literal_cut_component_can_clear_real_future_native_copper(tmp_path,monkeypatch,quarter,back):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    before=[rows._source_binding(b) for b in (parent,private)];raw=source.read_bytes()
    proof=cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.)
    assert {q['change']['uuid'] for q in proof}==set(ids)
    assert all(q['authority']['kind']=='positive_source_ordinary' for q in proof)
    for row in proof:
        owned=row['source_native_obstacle_ownership']
        assert owned['component_source_track_uuids']==sorted(ids)
        assert owned['literal_foreign_native_conflicts']
        assert owned['every_surviving_component_contact_requires_independent_saved_reconstruction']
    assert [rows._source_binding(b) for b in (parent,private)]==before and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['ground','wide','long','locked','group','not_blocking','unowned',
    'unrelated_component','stale','already_owned','no_motion'])
def test_no_arbitrary_ground_bus_or_unrelated_source_edge_is_acquired(tmp_path,monkeypatch,fault):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch)
    live={force._uid(t):t for t in parent.GetTracks()};extra={}
    if fault=='ground':live[ids[0]].SetNet(parent.FindNet('GND'))
    elif fault=='wide':live[ids[0]].SetWidth(400000)
    elif fault=='long':live[ids[0]].SetEnd(pcbnew.VECTOR2I_MM(16,5))
    elif fault=='locked':live[ids[0]].SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(parent);g.SetName('immutable_source');parent.Add(g);g.AddItem(live[ids[0]])
    elif fault=='not_blocking':
        for t in live.values():t.Move(pcbnew.VECTOR2I_MM(0,5))
    elif fault=='unowned':monkeypatch.setattr(cuts.ordinary,'eligible_nets',lambda *args:set())
    elif fault=='unrelated_component':
        t=track(parent,'foreign_signal',(20,20),(21,20),width=.2);ids.append(force._uid(t))
    elif fault=='stale':ids[0]='missing-source-track'
    elif fault=='already_owned':extra['excluded_uuids']=[ids[0]]
    elif fault=='no_motion':private.FindFootprintByReference(next(iter(proposal['poses']))).SetPosition(pcbnew.VECTOR2I_MM(5,5))
    before=[rows._source_binding(b) for b in (parent,private)]
    with pytest.raises((ValueError,KeyError)):
        cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.,**extra)
    assert [rows._source_binding(b) for b in (parent,private)]==before


def test_locked_cut_requires_explicit_positive_source_scope(tmp_path,monkeypatch):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch)
    for t in parent.GetTracks():t.SetLocked(True)
    assert len(cuts.ownership(parent,private,source,proposal,ids,allow_locked=True,
        deadline=time.monotonic()+10.))==2


@pytest.mark.parametrize('length',[8.001,16.,24.,32.])
def test_explicit_longer_work_extent_does_not_change_ownership_or_copper_rules(tmp_path,monkeypatch,length):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch)
    edge=next(t for t in parent.GetTracks() if force._uid(t)==ids[0])
    edge.SetEnd(pcbnew.VECTOR2I(round((6+length)*1e6),5000000))
    with pytest.raises(ValueError):cuts.ownership(parent,private,source,proposal,[ids[0]],deadline=time.monotonic()+10.)
    proof=cuts.ownership(parent,private,source,proposal,[ids[0]],deadline=time.monotonic()+10.,max_source_track_mm=length)
    assert len(proof)==1 and proof[0]['source_native_obstacle_ownership']['literal_foreign_native_conflicts']


@pytest.mark.parametrize('bound',[True,0,33,None,float('nan'),float('inf')])
def test_obstacle_work_extent_is_explicit_finite_and_bounded(bound):
    with pytest.raises(ValueError):cuts.ownership(None,None,None,{},[],deadline=time.monotonic()+10.,max_source_track_mm=bound)


@pytest.mark.parametrize('bound',[True,0,17,None,8.5])
def test_obstacle_item_work_count_is_explicit_and_bounded(bound):
    with pytest.raises(ValueError):cuts.ownership(None,None,None,{},[],deadline=time.monotonic()+10.,max_tracks=bound)


def test_nonordinary_lead_retains_independently_rederived_full_current_plan(tmp_path,monkeypatch):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(cuts.ordinary,'eligible_nets',lambda *args:set());calls=[]
    def full(board,path,**kwargs):
        calls.append(kwargs);return dict(source_fixture_contract=True,retired_track_uuids=kwargs['retired_track_uuids'])
    monkeypatch.setattr(cuts.full,'plan',full)
    proof=cuts.ownership(parent,private,source,proposal,ids,deadline=time.monotonic()+10.)
    assert len(calls)==2
    assert all(q['authority']['kind']=='unchanged_full_current_source_edge'
        and q['authority']['source_plan']['retired_track_uuids']==[q['change']['uuid']] for q in proof)


@pytest.mark.parametrize('ids',[None,True,{},list(map(str,range(9))),['a','a']])
def test_invalid_or_unbounded_cut_scope_refuses_before_native_inventory(ids):
    with pytest.raises(ValueError):cuts.ownership(None,None,None,{},ids,deadline=time.monotonic()+10.)


@pytest.mark.parametrize('back',[False,True])
def test_complete_macro_independently_reconstructs_foreign_ports_not_retired_bends(tmp_path,monkeypatch,back):
    import cec_cell_macro_requests as compiler
    import cec_complete_macro_cell as macro
    import cec_cell_escape_replan as escape
    import cec_additive_route_receiving as additive
    from test_complete_macro_cell import fixture as macro_fixture
    source,parent,unused,initial=macro_fixture(tmp_path,monkeypatch,back=back)
    parent.Add(pcbnew.NETINFO_ITEM(parent,'independent_scalar'))
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    points=[(15.4,8.3),(14.1,8.3),(14.1,10.),(15.4,10.),(16.4,10.)]
    added=[]
    for a,b in zip(points,points[1:]):
        edge=track(parent,'independent_scalar',a,b,width=.2);edge.SetLayer(face);added.append(force._uid(edge))
    field._save_field_snapshot(parent,source)
    original_eligible=cuts.ordinary.eligible_nets
    monkeypatch.setattr(cuts.ordinary,'eligible_nets',lambda *args:original_eligible(*args)|{'independent_scalar'})
    owned=added[1:3];raw=source.read_bytes()
    private,packet=compiler.compile(source,initial['source_plan']['poses'],board_hint='opaque',
        additional_obstacle_track_uuids=owned)
    assert packet['explicit_additional_obstacle_track_uuids']==sorted(owned)
    component=next(q for q in packet['additional_source_cut_components'] if q['net']=='independent_scalar')
    assert set(component['source_extra_edge_uuids'])==set(owned)
    assert len(component['surviving_contacts'])==2 and len(component['request_ids'])==1
    assert component['retired_internal_bends_are_not_anchors']
    additive._ground_refill(private)
    proof=macro.screen(source,private,packet,board_hint='opaque')
    assert proof['complete'],(proof.get('errors'),proof.get('empty_obligations'),proof.get('selection'))
    escape.construct_private(private,proof['packet'],proof['selection']);additive._ground_refill(private)
    candidate=force._copy_family(source,tmp_path/'received-foreign-obstacle-child')
    field._save_field_snapshot(private,candidate)
    accepted=macro.receive(source,candidate,board_hint='opaque',additional_obstacle_track_uuids=owned)
    assert accepted['ok'] and accepted['complete'],accepted['errors']
    assert accepted['all_original_surviving_native_partitions_preserved']
    assert accepted['all_original_physical_ground_returns']['ok']
    assert not macro.receive(source,candidate,board_hint='opaque')['ok']
    damaged=pcbnew.LoadBoard(str(candidate))
    original={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    from cec_native_items import discard_items
    discard_items(damaged,[t for t in damaged.GetTracks() if t.GetNetname()=='independent_scalar'
        and force._uid(t) not in original])
    field._save_field_snapshot(damaged,candidate)
    assert not macro.receive(source,candidate,board_hint='opaque',additional_obstacle_track_uuids=owned)['ok']
    assert source.read_bytes()==raw and not accepted['release_authority']
