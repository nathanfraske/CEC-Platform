"""Whole pair reconstruction separates fixed native pad holes from route vias."""
import contextlib,json,math
from pathlib import Path
import pytest
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_field_coupling as field
import cec_precision_route as precision
import cec_current_topology as topology
import cec_synth_pipeline as synth
import cec_paired_route_reconstruction as owned
import cec_additive_route_receiving as additive
from cec_native_items import discard_items


def fixture(angle=0,mirror=False):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    pair=dict(name='arbitrary',kind='diff',p='first_lane',n='second_lane',width=.25,gap=.35,clearance=.2)
    for net in (*[pair[k] for k in ('p','n')],'other_bus'):b.Add(pcbnew.NETINFO_ITEM(b,net))
    c=round(math.cos(math.radians(angle)));s=round(math.sin(math.radians(angle)))
    def at(x,y):
        x*=(-1 if mirror else 1)
        return pcbnew.VECTOR2I_MM(20+c*x-s*y,20+s*x+c*y)
    anchors=[];routes=[];pads=[]
    for x in (0.,10.):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('endpoint-'+str(x));b.Add(fp)
        for member,y in (('p',0.),('n',.6)):
            pad=pcbnew.PAD(fp);pad.SetNumber(member);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetPosition(at(x,y));pad.SetNet(b.FindNet(pair[member]));fp.Add(pad);pads.append(pad)
            via=pcbnew.PCB_VIA(b);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            via.SetPosition(pad.GetPosition());via.SetWidth(300000);via.SetDrill(200000);via.SetNet(pad.GetNet());via.SetLocked(True)
            b.Add(via);anchors.append(via)
    for member,y in (('p',0.),('n',.6)):
        track=pcbnew.PCB_TRACK(b);track.SetStart(at(0,y));track.SetEnd(at(10,y));track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(250000);track.SetNet(b.FindNet(pair[member]));track.SetLocked(True);b.Add(track)
        via=pcbnew.PCB_VIA(b);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetPosition(at(5,y));via.SetWidth(500000);via.SetDrill(300000);via.SetNet(b.FindNet(pair[member]));b.Add(via);routes.append(via)
    return b,pair,anchors,routes,pads


def source_contract(monkeypatch,pair):
    monkeypatch.setattr(precision,'derive_coupled_pairs',lambda *a,**kw:[pair])
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:{})
    monkeypatch.setattr(synth,'spec_net_current_contract',lambda *a,**kw:None)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_plan_retains_every_pad_barrel_and_owns_every_other_pair_barrel(monkeypatch,angle,mirror):
    b,pair,anchors,routes,pads=fixture(angle,mirror);source_contract(monkeypatch,pair)
    before=field._field_snapshot_inventory(b)
    q=owned.plan(b,'arbitrary.kicad_pcb',board_hint='synthetic',pair_name=pair['name'],preserve_native_pad_barrels=True)
    assert q['retained_pair_via_uuids']==sorted(force._uid(v) for v in anchors)
    assert q['retired_via_uuids']==sorted(force._uid(v) for v in routes)
    assert len(q['retired_track_uuids'])==2
    assert q['all_source_nonterminal_pair_barrels_owned'] and not q['all_source_pair_barrels_owned']
    assert not q['source_barrel_classification']['inherited_debt_qualified']
    assert not q['external_lands_retired'] and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['one_route','pad_barrel','foreign_id'])
def test_explicit_mode_still_refuses_selected_inconvenient_subset(monkeypatch,fault):
    b,pair,anchors,routes,pads=fixture();source_contract(monkeypatch,pair)
    requested=[force._uid(v) for v in routes]
    if fault=='one_route':requested=requested[:1]
    elif fault=='pad_barrel':requested.append(force._uid(anchors[0]))
    else:requested.append('not-a-source-barrel')
    with pytest.raises(ValueError,match='all_source_pair_barrels'):
        owned.plan(b,'arbitrary.kicad_pcb',board_hint='synthetic',pair_name=pair['name'],
            retired_via_uuids=requested,preserve_native_pad_barrels=True)


@pytest.mark.parametrize('fault',['unknown_profile','off_origin','partial_pad','pad_hole','wrong_net_contact','blind_route','opaque_route_group'])
def test_missing_witness_or_unknown_terminal_contact_never_makes_barrel_disposable(monkeypatch,fault):
    b,pair,anchors,routes,pads=fixture();source_contract(monkeypatch,pair)
    if fault=='unknown_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif fault=='off_origin':anchors[0].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='partial_pad':pads[0].SetSize(pcbnew.VECTOR2I_MM(.2,.8))
    elif fault=='pad_hole':pads[0].SetDrillSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault=='wrong_net_contact':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetPosition(routes[0].GetPosition());pad.SetNet(b.FindNet('other_bus'));fp.Add(pad)
    elif fault=='blind_route':routes[0].SetViaType(pcbnew.VIATYPE_BLIND);routes[0].SetLayerPair(pcbnew.F_Cu,pcbnew.In2_Cu)
    else:
        g=pcbnew.PCB_GROUP(b);g.SetName('opaque power owner');b.Add(g);g.AddItem(routes[0])
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):
        owned.plan(b,'arbitrary.kicad_pcb',board_hint='synthetic',pair_name=pair['name'],preserve_native_pad_barrels=True)
    assert field._field_snapshot_inventory(b)==before


def test_no_route_holes_is_a_valid_complete_empty_retirement_not_a_drill_request(monkeypatch):
    b,pair,anchors,routes,pads=fixture();source_contract(monkeypatch,pair);discard_items(b,routes)
    q=owned.plan(b,'arbitrary.kicad_pcb',board_hint='synthetic',pair_name=pair['name'],preserve_native_pad_barrels=True)
    assert q['retired_via_uuids']==[] and len(q['retained_pair_via_uuids'])==4
    discard_items(b,anchors)
    q=owned.plan(b,'arbitrary.kicad_pcb',board_hint='synthetic',pair_name=pair['name'],preserve_native_pad_barrels=True)
    assert q['retired_via_uuids']==q['retained_pair_via_uuids']==[]


@pytest.mark.parametrize('policy',[1,None,'yes'])
def test_implicit_mode_not_a_source_ownership_grant(monkeypatch,policy):
    b,pair,*_=fixture();source_contract(monkeypatch,pair)
    with pytest.raises(ValueError,match='explicit_source_pad_barrel_preservation'):
        owned.plan(b,'arbitrary.kicad_pcb',board_hint='synthetic',pair_name=pair['name'],preserve_native_pad_barrels=policy)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('fault',[None,'deleted_anchor','moved_anchor','resized_anchor',
    'changed_other_bus','omitted_retire','half_pair'])
def test_real_saved_pair_receive_preserves_pad_barrels_and_retires_only_route_hole(tmp_path,rotation,fault):
    import wx
    quiet=wx.LogNull()
    # Extend the existing fully native CAN receiving fixture with genuine
    # pad-contained source barrels. Its real pair contract, native GND fill,
    # saved connectivity, physical and exact subtract/add gates remain live.
    from test_native_paired_route_reconstruction import fixture as native_fixture
    source,unused,oldplan=native_fixture(tmp_path,rotation=rotation,retire_barrels=True)
    board=pcbnew.LoadBoard(str(source));pads=[p for f in board.GetFootprints() for p in f.Pads()
        if p.GetNetname() in (oldplan['pair']['p'],oldplan['pair']['n'])]
    anchor_vias=[]
    for pad in pads:
        pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(pad.GetPosition());via.SetWidth(300000);via.SetDrill(200000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(pad.GetNetCode());board.Add(via);anchor_vias.append(via)
    evidence=fr.group_local_pofv_signal_vias(board,anchor_vias)
    assert evidence and evidence['added_vias']==4
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    # Existing real signal transitions require real nearby GND barrels; a
    # containing reference zone alone is not a physical return transition.
    # Build these in the immutable SOURCE fixture and retain them unchanged.
    for pad in [p for p in pads if p.GetNetname()==oldplan['pair']['p']]:
        mate=min((p for p in pads if p.GetNetname()==oldplan['pair']['n']),
            key=lambda p:math.dist(tuple(p.GetPosition()),tuple(pad.GetPosition())))
        delta=mate.GetPosition()-pad.GetPosition();span=math.hypot(delta.x,delta.y)
        at=pad.GetPosition()+pcbnew.VECTOR2I(round(delta.x*1200000/span),round(delta.y*1200000/span))
        via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(at);via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(board.FindNet('GND'));board.Add(via)
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    q=owned.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',pair_name='CAN',preserve_native_pad_barrels=True)
    assert len(q['retained_pair_via_uuids'])==4 and len(q['retired_via_uuids'])==2
    child=force._copy_family(source,tmp_path/'new-mode-child');c=pcbnew.LoadBoard(str(child))
    outgoing=set(q['retired_track_uuids'])|set(q['retired_via_uuids'])
    discard_items(c,[t for t in c.GetTracks() if force._uid(t) in outgoing])
    from test_field_proposals import track
    for net in (q['pair']['p'],q['pair']['n']):
        xy=[p.GetPosition() for f in c.GetFootprints() for p in f.Pads() if p.GetNetname()==net]
        track(c,net,tuple(v/1e6 for v in xy[0]),tuple(v/1e6 for v in xy[1]),width=.25)
    additive._ground_refill(c);field._save_field_snapshot(c,child)
    child=Path(additive.finalize_private(source,child,tmp_path/'new-mode-final')['board'])
    requested=list(q['retired_via_uuids'])
    if fault is not None:
        altered=pcbnew.LoadBoard(str(child));anchor=next(t for t in altered.GetTracks()
            if force._uid(t) in q['retained_pair_via_uuids'])
        if fault=='deleted_anchor':discard_items(altered,[anchor])
        elif fault=='moved_anchor':anchor.Move(pcbnew.VECTOR2I_MM(.05,0))
        elif fault=='resized_anchor':anchor.SetWidth(350000)
        elif fault=='changed_other_bus':
            next(t for t in altered.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='+5V').SetWidth(900000)
        elif fault=='omitted_retire':requested=requested[:1]
        elif fault=='half_pair':discard_items(altered,[t for t in altered.GetTracks() if t.GetClass()=='PCB_TRACK'
            and t.GetNetname()==q['pair']['n']])
        if fault!='omitted_retire':field._save_field_snapshot(altered,child)
    result=owned.receive(source,child,board_hint='synthetic',pair_name='CAN',retired_track_uuids=q['retired_track_uuids'],
        retired_via_uuids=requested,preserve_native_pad_barrels=True,timeout_s=30.)
    if fault is not None:
        assert not result['ok'] and not result['complete'] and result['errors'],result
        return
    assert result['ok'] and result['complete'],(result['errors'],result.get('actual_saved_native_pair_physical_contract',{}).get('violations'))
    assert result['actual_saved_native_pair_completion']['connected']
    assert not result['actual_saved_native_pair_physical_contract']['violations']
    assert not result['inherited_debt_qualified'] and not result['release_authority']
