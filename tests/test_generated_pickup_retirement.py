"""Real native geometry regressions for bounded generated barrel retirement."""
import copy, math
import pcbnew
import pytest
import cec_force_current as force
import cec_fr as fr
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_generated_pickup_retirement as op
from test_lastmile import _board
from test_field_proposals import track

def fixture(tmp_path, angle=0, mirror=False):
    def xy(p):
        x,y=p[0]-7,p[1]-5
        if mirror: x=-x
        a=math.radians(angle)
        return round(8+x*math.cos(a)-y*math.sin(a),6), round(8+x*math.sin(a)+y*math.cos(a),6)
    name='/RENAMED/HARMLESS'
    b=_board([(*xy((5,5)),name),(*xy((9,5)),name)],edge=(0,0,20,20))
    t=track(b,name,xy((5,5)),xy((9,5)))
    v=pcbnew.PCB_VIA(b);v.SetNetCode(b.GetNetcodeFromNetname(name))
    v.SetPosition(pcbnew.VECTOR2I_MM(*xy((7,5))))
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetWidth(600000);v.SetDrill(300000);v.SetLocked(True);b.Add(v)
    group=pcbnew.PCB_GROUP(b);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(group);group.AddItem(v)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    return path,b,v,t,group,name

@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_rigid_rotations_mirrors_renamed_net_saved_exact_cut(tmp_path,angle,mirror):
    source,b,v,t,g,net=fixture(tmp_path,angle,mirror)
    before=source.read_bytes();plan=op.plan(b,[force._uid(v)])
    uid=force._uid(t);op.subtract(b,plan)
    child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=op.receive(source,child,plan,board_hint='unclassified-test')
    assert result['ok'] and result['complete'],result
    assert result['surviving_native_partitions_preserved']
    assert not result['current_qualified'] and not result['release_authority']
    assert uid in {force._uid(i) for i in b.GetTracks()} and source.read_bytes()==before

@pytest.mark.parametrize('bad',['second_face','foreign','other_barrel','group_name','locked_group',
    'ungrouped','negative_annulus','blank_net','missing','double_request'])
def test_ambiguous_contacts_or_source_ownership_refuse_before_cut(tmp_path,bad):
    source,b,v,t,g,name=fixture(tmp_path)
    ids=[force._uid(v)]
    if bad=='second_face':track(b,name,(8,8),(8,10),layer=pcbnew.B_Cu)
    elif bad=='foreign':track(b,'/OTHER',(8,8),(8,10))
    elif bad=='other_barrel':
        w=pcbnew.PCB_VIA(b);w.SetNetCode(v.GetNetCode());w.SetPosition(v.GetPosition())
        w.SetViaType(pcbnew.VIATYPE_THROUGH);w.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        w.SetWidth(600000);w.SetDrill(300000);b.Add(w)
    elif bad=='group_name':g.SetName('NOT-GENERATED')
    elif bad=='locked_group':g.SetLocked(True)
    elif bad=='ungrouped':g.RemoveItem(v)
    elif bad=='negative_annulus':v.SetDrill(650000)
    elif bad=='blank_net':v.SetNetCode(0)
    elif bad=='missing':ids=['absent-native-id']
    elif bad=='double_request':ids*=2
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,ids)
    assert field._field_snapshot_inventory(b)==before

@pytest.mark.parametrize('bad',[[],None,['a']*17])
def test_unbounded_or_nonliteral_inventory_refuses(tmp_path,bad):
    source,b,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(b,bad)

@pytest.mark.parametrize('bad',[0,11,float('inf'),True])
def test_unknown_budget_refuses(tmp_path,bad):
    source,b,v,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(b,[force._uid(v)],timeout_s=bad)

@pytest.mark.parametrize('bad',['forged_inventory','changed_source'])
def test_whole_replan_is_required_before_native_destruction(tmp_path,bad):
    source,b,v,t,g,name=fixture(tmp_path);plan=op.plan(b,[force._uid(v)])
    if bad=='forged_inventory':plan['via_uuids'].append(force._uid(t))
    else:t.SetWidth(250000)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.subtract(b,plan)
    assert field._field_snapshot_inventory(b)==before

def test_via_used_as_surface_bridge_is_not_redundant(tmp_path):
    source,b,v,t,g,name=fixture(tmp_path)
    t.SetEnd(pcbnew.VECTOR2I_MM(7.8,8));track(b,name,(8.2,8),(10,8))
    field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));v=next(q for q in b.GetTracks() if q.GetClass()=='PCB_VIA')
    plan=op.plan(b,[force._uid(v)]);op.subtract(b,plan)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    result=op.receive(source,child,plan,board_hint='unclassified-test')
    assert not result['ok'] and not result['complete']
    assert any('partition' in e for e in result['errors']), result

@pytest.mark.parametrize('remote',[False,True])
def test_unassigned_copper_is_excluded_only_after_native_shape_separation(tmp_path,remote):
    source,b,v,t,g,name=fixture(tmp_path)
    graphic=pcbnew.PCB_SHAPE(b);graphic.SetShape(pcbnew.SHAPE_T_SEGMENT)
    graphic.SetStart(pcbnew.VECTOR2I_MM(15,15) if remote else pcbnew.VECTOR2I_MM(8,8))
    graphic.SetEnd(pcbnew.VECTOR2I_MM(16,15) if remote else pcbnew.VECTOR2I_MM(8,10))
    graphic.SetWidth(200000);graphic.SetLayer(pcbnew.F_Cu);b.Add(graphic)
    field._save_field_snapshot(b,source)
    if not remote:
        with pytest.raises(ValueError,match='unassigned_copper_can_contact'):
            op._scoped_terminal_graph(b,name)
    b=pcbnew.LoadBoard(str(source));v=next(q for q in b.GetTracks() if q.GetClass()=='PCB_VIA')
    plan=op.plan(b,[force._uid(v)]);op.subtract(b,plan)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    result=op.receive(source,child,plan,board_hint='unclassified-test')
    assert result['ok']==remote,result
    if remote:
        assert result['actual_drilled_terminal_graphs'][0]['source']['remote_native_graphic_exclusions']
    else:assert any('unassigned_copper_can_contact' in e for e in result['errors']), result

def test_unrelated_change_cannot_pass_exact_replay(tmp_path):
    source,b,v,t,g,name=fixture(tmp_path);plan=op.plan(b,[force._uid(v)])
    op.subtract(b,plan);t.SetWidth(250000)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    assert not op.receive(source,child,plan,board_hint='unclassified-test')['ok']

def test_typed_supply_dependency_is_not_silently_retired(tmp_path):
    source,b,v,t,g,name=fixture(tmp_path);uid=force._uid(v)
    protected=pcbnew.PCB_GROUP(b)
    protected.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|'+uid+'|retained|'+force._uid(t));b.Add(protected)
    plan=op.plan(b,[uid]);before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='typed_supply_annotation'):op.subtract(b,plan)
    assert field._field_snapshot_inventory(b)==before


def stem_fixture(tmp_path,angle=0,mirror=False):
    source,b,via,trunk,group,name=fixture(tmp_path,angle,mirror)
    origin=tuple(trunk.GetStart());theta=math.radians(angle)
    offset=(-round(1125000*math.sin(theta)),round(1125000*math.cos(theta)))
    via.SetPosition(pcbnew.VECTOR2I(*(a+d for a,d in zip(origin,offset))))
    stem=pcbnew.PCB_TRACK(b);stem.SetStart(pcbnew.VECTOR2I(*origin));stem.SetEnd(via.GetPosition())
    stem.SetLayer(pcbnew.F_Cu);stem.SetWidth(200000);stem.SetNetCode(trunk.GetNetCode());stem.SetLocked(True)
    b.Add(stem);group.AddItem(stem);field._save_field_snapshot(b,source)
    return source,b,via,trunk,group,stem,name


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('separate_endpoint_owner',[False,True])
def test_generated_dead_pickup_and_its_own_stem_retire_as_one_received_delta(tmp_path,angle,mirror,separate_endpoint_owner):
    source,b,via,trunk,group,stem,name=stem_fixture(tmp_path,angle,mirror)
    if separate_endpoint_owner:
        group.RemoveItem(stem);owner=pcbnew.PCB_GROUP(b)
        owner.SetName(fr.ENDPOINT_NECKDOWN_GROUP);b.Add(owner);owner.AddItem(stem)
        field._save_field_snapshot(b,source)
    raw=source.read_bytes();vuid,tuid=force._uid(via),force._uid(stem)
    plan=op.plan(b,[vuid],track_uuids=[tuid]);op.subtract(b,plan)
    child=force._copy_family(source,tmp_path/'whole-generated-leaf')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=op.receive(source,child,plan,board_hint='unclassified-test')
    assert result['ok'] and result['complete'],result
    assert result['retired_track_uuids']==[tuid] and result['retired_via_uuids']==[vuid]
    assert result['independent_compound_source_current_nonregression']['ok']
    assert not result['release_authority'] and not result['current_qualified'] and source.read_bytes()==raw


@pytest.mark.parametrize('bad',['ungrouped_stem','other_group','locked_group','too_long','wrong_face',
    'duplicate','missing','trunk','no_smd_root','unlisted_barrel_contact'])
def test_a_generated_barrel_does_not_authorize_arbitrary_trace_deletion(tmp_path,bad):
    source,b,via,trunk,group,stem,name=stem_fixture(tmp_path)
    vuid,tuid=force._uid(via),force._uid(stem);selected=[tuid]
    if bad=='ungrouped_stem':group.RemoveItem(stem)
    elif bad=='other_group':
        group.RemoveItem(stem);other=pcbnew.PCB_GROUP(b);other.SetName('not-generator');b.Add(other);other.AddItem(stem)
    elif bad=='locked_group':group.SetLocked(True)
    elif bad=='too_long':stem.SetStart(stem.GetStart()+pcbnew.VECTOR2I_MM(0,-2))
    elif bad=='wrong_face':stem.SetLayer(pcbnew.B_Cu)
    elif bad=='duplicate':selected*=2
    elif bad=='missing':selected=['not-present']
    elif bad=='trunk':selected=[force._uid(trunk)]
    elif bad=='no_smd_root':
        for f in b.GetFootprints():
            for p in f.Pads():p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    else:
        start=tuple(via.GetPosition())
        track(b,name,tuple(n/1e6 for n in start),(start[0]/1e6,start[1]/1e6+1),width=.2)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,[vuid],track_uuids=selected)
    assert field._field_snapshot_inventory(b)==before


def test_removing_a_generated_stem_cannot_isolate_a_real_interior_terminal(tmp_path):
    source,b,via,trunk,group,stem,name=stem_fixture(tmp_path)
    for fp in b.GetFootprints():
        for pad in fp.Pads():pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ANOTHER_REAL_TERMINAL');b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
    mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(mask);pad.SetNetCode(stem.GetNetCode())
    pad.SetPosition(pcbnew.VECTOR2I((stem.GetStart().x+stem.GetEnd().x)//2,(stem.GetStart().y+stem.GetEnd().y)//2));fp.Add(pad)
    field._save_field_snapshot(b,source);plan=op.plan(b,[force._uid(via)],track_uuids=[force._uid(stem)])
    op.subtract(b,plan);child=force._copy_family(source,tmp_path/'invalid-terminal-cut');field._save_field_snapshot(b,child)
    result=op.receive(source,child,plan,board_hint='unclassified-test')
    assert not result['ok'] and result['errors'],result
