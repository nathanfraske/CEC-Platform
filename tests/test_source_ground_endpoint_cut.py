"""A qualified endpoint exception is restoration debt, not a movable route."""
import pcbnew
import pytest
import cec_source_ground_endpoint_cut as cuts
import cec_smd_macro_transport as macro
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, *, back=False, quarter=0, locked=True):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'GND');board.Add(net)
    group=pcbnew.PCB_GROUP(board);group.SetName(fr.ENDPOINT_NECKDOWN_GROUP);board.Add(group)
    owners=[];edges=[];trunks=[]
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    for index,x in enumerate((10.,30.)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_'+str(index))
        fp.SetPosition(pcbnew.VECTOR2I_MM(x,10));board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.3,1.))
        ls=pcbnew.LSET();ls.AddLayer(face);p.SetLayerSet(ls);p.SetNet(net);fp.Add(p)
        p.SetPosition(fp.GetPosition())
        leg=track(board,'GND',(x,10),(x,10.85),width=.2);leg.SetLayer(face);leg.SetLocked(locked)
        trunk=track(board,'GND',(x,10.85),(x,12),width=.5);trunk.SetLayer(face);trunk.SetLocked(True)
        group.AddItem(leg);owners.append(force._uid(fp));edges.append(force._uid(leg));trunks.append(force._uid(trunk))
    if quarter:
        for item in [*board.GetFootprints(),*board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    parent,posed=[pcbnew.LoadBoard(str(source)) for _ in range(2)]
    owner=next(f for f in posed.GetFootprints() if force._uid(f)==owners[0])
    owner.Move(pcbnew.VECTOR2I_MM(.75,0))
    monkeypatch.setattr(cuts.roles,'footprint_contract',lambda f:dict(
        pins={'1':'ground','2':'power_input'},source='synthetic_manufacturer_pin_contract'))
    return parent,posed,source,owners,edges,trunks


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_only_actual_departing_component_is_owned_and_every_other_group_member_stays_literal(tmp_path,monkeypatch,back,quarter):
    a,b,path,owners,edges,trunks=fixture(tmp_path,monkeypatch,back=back,quarter=quarter)
    before=[row._source_binding(q) for q in (a,b)]
    plans=cuts.plan(a,b,source_floor=lambda t:(500000,200000),allow_locked=True)
    assert len(plans)==1
    plan=plans[0]
    assert plan['retired_track_uuids']==[edges[0]]
    assert plan['retained_throat_track_uuids']==[trunks[0]]
    assert set(plan['source_group_cohort_uuids'])==set(edges)
    assert plan['new_endpoint_copper_requires_fresh_qualification']
    assert not plan['current_authority'] and not plan['saved_candidate_authorized']
    assert before==[row._source_binding(q) for q in (a,b)]


@pytest.mark.parametrize('fault',['locked_without_scope','group_name','group_lock','power_stage','unknown_role',
    'stationary','subclass_throat','unqualified_long_lead','overlapping_owner'])
def test_no_label_lock_or_failed_geometry_grants_retirement(tmp_path,monkeypatch,fault):
    a,b,path,owners,edges,trunks=fixture(tmp_path,monkeypatch)
    live={force._uid(t):t for t in a.GetTracks()};allow=True
    if fault=='locked_without_scope':allow=False
    elif fault=='group_name':next(iter(a.Groups())).SetName('ARBITRARY')
    elif fault=='group_lock':next(iter(a.Groups())).SetLocked(True)
    elif fault in ('power_stage','unknown_role'):
        monkeypatch.setattr(cuts.roles,'footprint_contract',lambda f:dict(source='synthetic',
            pins={'1':'ground','2':'switch'}) if fault=='power_stage' else None)
    elif fault=='stationary':b=pcbnew.LoadBoard(str(path))
    elif fault=='subclass_throat':live[trunks[0]].SetWidth(300000)
    elif fault=='unqualified_long_lead':
        live[edges[0]].SetEnd(pcbnew.VECTOR2I_MM(10,15));live[trunks[0]].SetStart(pcbnew.VECTOR2I_MM(10,15))
    else:
        g=pcbnew.PCB_GROUP(a);g.SetName('SECOND_OWNER');a.Add(g);g.AddItem(live[edges[0]])
    before=[row._source_binding(q) for q in (a,b)]
    assert cuts.plan(a,b,source_floor=lambda t:(500000,200000),allow_locked=allow)==[]
    assert before==[row._source_binding(q) for q in (a,b)]


def test_macro_default_refuses_but_complete_restore_scope_keeps_locked_copper_unmoved(tmp_path,monkeypatch):
    import cec_route_dimensions as dimensions
    import cec_current_topology as topology
    a,b,path,owners,edges,trunks=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(force,'_family',lambda *a,**k:{'synthetic':True})
    monkeypatch.setattr(dimensions,'project_resolver',lambda *a,**k:lambda net:{'track_width':.5,'clearance':.2})
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**k:{})
    monkeypatch.setattr(topology,'current_contract_for_net',lambda *a,**k:None)
    before=row._source_binding(b)
    with pytest.raises(ValueError,match='arbitrary_grouped_route_is_immutable'):
        macro.apply(a,b,source_path=path,board_hint='synthetic')
    assert before==row._source_binding(b)
    result=macro.apply(a,b,source_path=path,board_hint='synthetic',rebuild_source_ground_endpoints=True,
        allow_owned_locked_ground_endpoints=True)
    assert result['source_ground_endpoint_restoration_cuts'][0]['retired_track_uuids']==[edges[0]]
    assert result['changes']==[] and not result['saved_candidate_authorized']
    assert before==row._source_binding(b)


@pytest.mark.parametrize('kwargs',[{'timeout_s':True},{'timeout_s':11},{'allow_locked':1},{'timeout_s':float('nan')}])
def test_invalid_scope_refuses_before_native_reads(kwargs):
    with pytest.raises(ValueError):cuts.plan(None,None,source_floor=lambda t:(500000,200000),**kwargs)
