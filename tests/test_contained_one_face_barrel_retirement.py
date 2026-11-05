"""Native face/material proofs, not refdes/net/coordinate retirement rules."""
import math
import pcbnew
import pytest
import cec_contained_one_face_barrel_retirement as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path, layer=pcbnew.F_Cu, angle=0, mirror=False, grouped=False):
    def xy(point):
        x, y = point[0]-7, point[1]-5
        if mirror: x = -x
        a = math.radians(angle)
        return round(9+x*math.cos(a)-y*math.sin(a),6), round(9+x*math.sin(a)+y*math.cos(a),6)
    net = '/OTHER-DESIGN/RENAMED-RAIL'
    b = _board([(*xy((5,5)),net), (*xy((9,5)),net)], edge=(0,0,22,22))
    b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        if layer in (pcbnew.F_Cu,pcbnew.B_Cu):fp.SetLayer(layer)
        for p in fp.Pads():
            if layer not in (pcbnew.F_Cu,pcbnew.B_Cu):
                p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                p.SetDrillSize(pcbnew.VECTOR2I(300000,300000))
                p.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                mask=pcbnew.LSET();mask.AddLayer(layer);p.SetLayerSet(mask)
    t = track(b,net,xy((5,5)),xy((9,5)),layer=layer,width=1.0)
    v = pcbnew.PCB_VIA(b); v.SetNetCode(b.GetNetcodeFromNetname(net))
    v.SetPosition(pcbnew.VECTOR2I_MM(*xy((7,5))));v.SetWidth(500000);v.SetDrill(300000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetLocked(True);b.Add(v)
    if grouped:
        g=pcbnew.PCB_GROUP(b);g.SetName('source-owner');b.Add(g);g.AddItem(v)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return source,b,v,t,net


def proposal(b,v,grouped=False):
    uid=force._uid(v)
    return op.plan(b,[uid],allow_locked_via_uuids=[uid],
                   allow_grouped_via_uuids=[uid] if grouped else [])


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_fully_covered_barrel_on_any_one_face_proposes_without_mutation(tmp_path,layer,angle,mirror):
    source,b,v,t,net=fixture(tmp_path,layer,angle,mirror)
    before=field._field_snapshot_inventory(b);p=proposal(b,v)
    assert p['rows'][0]['contact_face']==layer
    assert p['rows'][0]['retained_native_whole_disk_covers']==[force._uid(t)]
    assert before==field._field_snapshot_inventory(b)
    assert not p['current_qualified'] and not p['release_authority']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('grouped',[False,True])
def test_saved_whole_source_receiving_keeps_every_other_object_and_terminal(tmp_path,layer,grouped):
    source,b,v,t,net=fixture(tmp_path,layer,grouped=grouped);p=proposal(b,v,grouped)
    original=source.read_bytes();op.subtract(b,p)
    child=force._copy_family(source,tmp_path/'child');additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=op.receive(source,child,p,board_hint='unclassified-test')
    assert result['ok'] and result['complete'],result
    assert result['surviving_native_partitions_preserved'] and source.read_bytes()==original
    assert result['current_debt_receiving']['ok'] and result['absolute_native_cut_preservation']['same_evidence']
    assert not result['current_qualified'] and not result['release_authority']


@pytest.mark.parametrize('bad',['two_faces','foreign','other_barrel','uncovered','no_contacts',
    'negative_annulus','blank_net','nonthrough','source_lock','source_group','locked_group',
    'typed_dependency','unassigned_copper','rulearea_only'])
def test_warning_or_one_face_label_cannot_authorize_unsafe_copper_removal(tmp_path,bad):
    source,b,v,t,net=fixture(tmp_path,grouped=bad in ('source_group','locked_group'))
    uid=force._uid(v);kwargs=dict(allow_locked_via_uuids=[uid],allow_grouped_via_uuids=[uid])
    if bad=='two_faces':track(b,net,(9,9),(9,11),layer=pcbnew.B_Cu)
    elif bad=='foreign':track(b,'/FOREIGN',(9,9),(9,11))
    elif bad=='other_barrel':
        other=v.Duplicate();other.m_Uuid.Clone(pcbnew.KIID());b.Add(other)
    elif bad=='uncovered':t.SetWidth(200000)
    elif bad in ('no_contacts','rulearea_only'):
        t.SetLayer(pcbnew.B_Cu);t.Move(pcbnew.VECTOR2I_MM(5,0))
        if bad=='rulearea_only':
            z=pcbnew.ZONE(b);z.SetIsRuleArea(True);z.SetLayer(pcbnew.F_Cu);z.SetNetCode(v.GetNetCode())
            z.Outline().NewOutline()
            for x,y in ((8,8),(10,8),(10,10),(8,10)):z.Outline().Append(int(x*1e6),int(y*1e6))
            b.Add(z)
    elif bad=='negative_annulus':v.SetDrill(600000)
    elif bad=='blank_net':v.SetNetCode(0)
    elif bad=='nonthrough':v.SetViaType(pcbnew.VIATYPE_MICROVIA)
    elif bad=='source_lock':kwargs['allow_locked_via_uuids']=[]
    elif bad=='source_group':kwargs['allow_grouped_via_uuids']=[]
    elif bad=='locked_group':next(iter(b.Groups())).SetLocked(True)
    elif bad=='typed_dependency':
        g=pcbnew.PCB_GROUP(b);g.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|'+uid+'|other|conductor');b.Add(g)
    else:
        g=pcbnew.PCB_SHAPE(b);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(pcbnew.F_Cu)
        g.SetStart(pcbnew.VECTOR2I_MM(9,9));g.SetEnd(pcbnew.VECTOR2I_MM(9,11));g.SetWidth(100000);b.Add(g)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,[uid],**kwargs)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('bad',[[],None,['missing']*2,['a'+str(i) for i in range(9)]])
def test_finite_distinct_literal_scope_is_required(tmp_path,bad):
    _,b,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(b,bad)


@pytest.mark.parametrize('budget',[0,11,True,float('nan')])
def test_unknown_or_unbounded_native_work_refuses(tmp_path,budget):
    _,b,v,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(b,[force._uid(v)],timeout_s=budget)


@pytest.mark.parametrize('bad',['forged_cover','changed_source','forged_contact','different_lock_scope'])
def test_native_subtraction_rederives_every_fact_before_destroying_any_proxy(tmp_path,bad):
    source,b,v,t,net=fixture(tmp_path);p=proposal(b,v)
    if bad=='forged_cover':p['rows'][0]['retained_native_whole_disk_covers']=['not-a-source-body']
    elif bad=='changed_source':t.SetWidth(1100000)
    elif bad=='forged_contact':p['rows'][0]['contact_face']=pcbnew.B_Cu
    else:p['allow_locked_via_uuids']=[]
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.subtract(b,p)
    assert before==field._field_snapshot_inventory(b)


def test_surface_bridge_is_refused_before_any_native_cut(tmp_path):
    source,b,v,t,net=fixture(tmp_path);t.SetWidth(200000);t.SetEnd(pcbnew.VECTOR2I_MM(8.8,9))
    track(b,net,(9.2,9),(11,9),width=.2)
    with pytest.raises(ValueError,match='whole_disk_inside'):proposal(b,v)


def test_a_real_smd_land_can_cover_a_one_face_barrel_without_a_track_cover(tmp_path):
    source,b,v,t,net=fixture(tmp_path)
    p=next(p for fp in b.GetFootprints() for p in fp.Pads())
    v.SetPosition(p.GetPosition());p.SetSize(pcbnew.VECTOR2I(1200000,1200000));t.SetWidth(200000)
    result=proposal(b,v)
    assert result['rows'][0]['retained_native_whole_disk_covers']==[force._uid(p)]


def test_visible_copper_field_is_an_actual_unassigned_obstacle(tmp_path):
    source,b,v,t,net=fixture(tmp_path)
    fp=next(iter(b.GetFootprints()));text=fp.Reference()
    text.SetVisible(True);text.SetLayer(pcbnew.F_Cu);text.SetText('X')
    text.SetPosition(v.GetPosition());text.SetTextSize(pcbnew.VECTOR2I(1000000,1000000))
    with pytest.raises(ValueError,match='unassigned_native_copper'):proposal(b,v)


def test_unrelated_saved_edit_cannot_hide_inside_the_retirement_transaction(tmp_path):
    source,b,v,t,net=fixture(tmp_path);p=proposal(b,v);op.subtract(b,p);t.SetWidth(1100000)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    result=op.receive(source,child,p,board_hint='unclassified-test')
    assert not result['ok'] and not result['complete']
    assert any('exact_cut_refill' in e for e in result['errors']),result
