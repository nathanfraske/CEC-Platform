"""Source-owned internal bends are not fabricated surviving terminals."""
import copy
import time

import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as binding
import cec_force_current as force
import cec_macro_cut_components as cuts
from cec_native_items import discard_items
from test_field_proposals import track


def native_fixture(tmp_path,quarter=0,back=False,*,branched=True,capsule=False,gap=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'opaque_boundary');board.Add(net)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    def pad(ref,at):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*at));board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(net);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        ls=pcbnew.LSET();ls.AddLayer(face);p.SetLayerSet(ls);fp.Add(p);p.SetPosition(pcbnew.VECTOR2I_MM(*at))
    if capsule:
        pad('literal_source',(1,1));edges=[track(board,net.GetNetname(),(1,1),(2,1),width=.2)]
        track(board,net.GetNetname(),(2.200001 if gap else 2.1,1),(3,1),width=.2)
    else:
        pad('first_terminal',(2,2));pad('second_terminal',(12,2))
        edges=[track(board,net.GetNetname(),(2,2),(7,2),width=.2),
            track(board,net.GetNetname(),(7,2),(12,2),width=.2)]
        if branched:
            pad('third_terminal',(7,7));edges.append(track(board,net.GetNetname(),(7,2),(7,7),width=.25))
    for t in board.GetTracks():t.SetLayer(face)
    if quarter:
        at=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(at,angle)
    source=tmp_path/'literal.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    parent,private=[pcbnew.LoadBoard(str(source)) for _ in range(2)]
    ids={force._uid(t) for t in edges};extras=[]
    for t in parent.GetTracks():
        if force._uid(t) not in ids:continue
        extras.append(dict(change=dict(uuid=force._uid(t),net=t.GetNetname()),
            authority=dict(kind='positive_source_ordinary',native_source_uuid=force._uid(t))))
    discard_items(private,[t for t in private.GetTracks() if force._uid(t) in ids])
    for fp in private.GetFootprints():fp.Move(pcbnew.VECTOR2I_MM(.5,.5))
    return parent,private,extras,ids,dict(source_process_barrel_motion=[])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_all_true_ports_are_restored_without_an_obsolete_internal_bend(tmp_path,quarter,back):
    parent,private,extras,retired,transport=native_fixture(tmp_path,quarter,back)
    before=[binding._source_binding(b) for b in (parent,private)]
    requests,records=cuts.requests(parent,private,extras,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
    assert len(records)==1 and len(requests)==2
    record=records[0]
    assert set(record['source_extra_edge_uuids'])==retired and record['retired_internal_bends_are_not_anchors']
    pads={force._uid(p) for f in private.GetFootprints() for p in f.Pads()}
    actual={r[e]['pad_uuid'] for r in requests.values() for e in ('a','b')}
    assert actual==pads and all(r['width_nm']==250000 for r in requests.values())
    assert all(r['every_surviving_source_component_port_mandatory'] for r in requests.values())
    assert before==[binding._source_binding(b) for b in (parent,private)]
    assert not record['new_current_or_routing_or_fabrication_authority']


@pytest.mark.parametrize('gap',[False,True])
def test_real_capsule_contact_is_projected_but_same_net_proximity_is_not(tmp_path,gap):
    parent,private,extras,retired,transport=native_fixture(tmp_path,capsule=True,gap=gap)
    if gap:
        with pytest.raises(ValueError,match='actual_surviving_ports'):
            cuts.requests(parent,private,extras,retired,transport,
                project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
        return
    requests,records=cuts.requests(parent,private,extras,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
    assert len(requests)==1 and len(records[0]['surviving_contacts'])==2
    p=next(q for q in records[0]['surviving_contacts'] if q['source_class']=='PCB_TRACK')
    assert p['source_contact']['at_nm']==[2050000,1000000]
    assert p['projected_literal_ports']==[p['source_contact']]


@pytest.mark.parametrize('fault',['duplicate','missing','authority','retired','mask','group','width','ground_relabel'])
def test_forged_or_unowned_cut_components_refuse_without_mutating_native_source(tmp_path,fault):
    parent,private,extras,retired,transport=native_fixture(tmp_path)
    extras=copy.deepcopy(extras);edge=next(t for t in parent.GetTracks() if force._uid(t)==extras[0]['change']['uuid'])
    if fault=='duplicate':extras+=copy.deepcopy(extras[:1])
    elif fault=='missing':extras[0]['change']['uuid']='missing'
    elif fault=='authority':extras[0]['authority']['kind']='guessed_current'
    elif fault=='retired':retired=retired-{force._uid(edge)}
    elif fault=='mask':edge.SetHasSolderMask(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(parent);g.SetName('protected');g.AddItem(edge);parent.Add(g)
    elif fault=='width':edge.SetWidth(400000)
    else:
        for row in extras:row['authority']['kind']='positive_existing_low_power_ground_boundary'
    before=[binding._source_binding(b) for b in (parent,private)]
    with pytest.raises(ValueError):cuts.requests(parent,private,extras,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
    assert before==[binding._source_binding(b) for b in (parent,private)]


@pytest.mark.parametrize('timeout',[True,0,-1,float('nan'),float('inf')])
def test_deadline_and_scope_are_bounded_before_native_reads(timeout):
    with pytest.raises(ValueError):cuts.requests(None,None,[],set(),{},
        project_contacts=None,deadline=timeout)
