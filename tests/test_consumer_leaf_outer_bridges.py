"""Full source-current outer bridges, never an I/N or inner-width shortcut."""
from unittest import mock
import pcbnew
import pytest
import cec_consumer_leaf_reconstruction as worker
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_supply_consumer_branch as consumer
from test_consumer_leaf_reconstruction import case


def make(monkeypatch,tmp_path,angle=0,mirror=False):
    source,scope,catalog,_,_,net,retained,_=case(monkeypatch,tmp_path,angle,mirror)
    scope['grouped_track_uuids'].append(retained);b=pcbnew.LoadBoard(str(source))
    face=next(t.GetLayer() for t in b.GetTracks() if force._uid(t)==retained)
    other=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proposal=worker.plan(b,source,board_hint='synthetic',**scope)
    worker.subtract(b,proposal)
    def point(x,y):
        dummy=pcbnew.PCB_TRACK(b);dummy.SetStart(pcbnew.VECTOR2I_MM(x,y));dummy.SetEnd(pcbnew.VECTOR2I_MM(x,y))
        if angle:dummy.Rotate(pcbnew.VECTOR2I_MM(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirror:dummy.Flip(pcbnew.VECTOR2I_MM(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        return dummy.GetStart()
    via_ids=[]
    for xy in ((15,1),(9,5)):
        v=pcbnew.PCB_VIA(b);v.SetPosition(point(*xy));v.SetNetCode(b.GetNetcodeFromNetname(net));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v);via_ids.append(force._uid(v))
    incoming=[]
    for a,z,layer in (((15,5),(15,1),face),((15,1),(13,1),other),((13,1),(9,5),other),((9,5),(7,5),face)):
        t=pcbnew.PCB_TRACK(b);t.SetStart(point(*a));t.SetEnd(point(*z));t.SetNetCode(b.GetNetcodeFromNetname(net));t.SetLayer(layer)
        t.SetWidth(proposal['full_budget_outer_widths_nm'][pcbnew.LayerName(layer)]);b.Add(t);incoming.append(force._uid(t))
    worker.assign(b,proposal,incoming,via_ids);additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'outer-bridge-child');field._save_field_snapshot(b,child)
    return source,child,scope,catalog,via_ids,incoming


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_two_outer_bridges_keep_existing_complete_local_and_shared_budgets(monkeypatch,tmp_path,angle,mirror):
    source,child,scope,catalog,via_ids,_=make(monkeypatch,tmp_path,angle,mirror)
    frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        legacy=worker.receive(source,child,board_hint='synthetic',**scope)
        proof=worker.receive(source,child,board_hint='synthetic',allow_outer_layer_bridges=True,**scope)
    assert not legacy['ok']
    assert proof['ok'] and proof['complete'],proof
    assert proof['new_barrels_added']==2 and set(proof['incoming_via_uuids'])==set(via_ids)
    assert len(proof['new_actual_supply_contact_webs'])==2
    assert all(p['ok'] and p['actual_contact_layers']==['B.Cu','F.Cu'] for p in proof['new_actual_supply_contact_webs'])
    assert proof['source_scope']['budget']['current_authority']['amps']==.5
    assert proof['source_scope']['budget']['aggregate_current_authority']['amps']==3.
    assert not proof['new_barrel_ampacity_credited'] and not proof['release_authority']
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('fault',['boolean','thin_web','factory_drill','inner_contact','unlisted_barrel','three_vias','foreign_contact'])
def test_explicit_bridge_mode_is_not_a_web_factory_layer_or_contact_waiver(monkeypatch,tmp_path,fault):
    source,child,scope,catalog,via_ids,incoming=make(monkeypatch,tmp_path)
    frozen=source.read_bytes();b=pcbnew.LoadBoard(str(child));via=next(t for t in b.GetTracks() if force._uid(t)==via_ids[0])
    options=dict(allow_outer_layer_bridges=True)
    if fault=='boolean':options['allow_outer_layer_bridges']=1
    elif fault=='thin_web':via.SetDrill(450000)
    elif fault=='factory_drill':via.SetDrill(200000)
    elif fault=='foreign_contact':via.SetPosition(pcbnew.VECTOR2I_MM(7,3))
    elif fault=='inner_contact':
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(via.GetNetCode());t.SetLayer(pcbnew.In2_Cu);t.SetWidth(500000)
        t.SetStart(via.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(15,2));b.Add(t)
    else:
        group=next(g for g in b.Groups() if g.GetName().startswith(consumer.PREFIX))
        if fault=='unlisted_barrel':group.SetName(group.GetName().replace(via_ids[0],'').replace(',,',','))
        else:
            extra=via.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.SetPosition(pcbnew.VECTOR2I_MM(20,1));b.Add(extra)
            group.SetName(group.GetName()+','+force._uid(extra))
    if fault=='foreign_contact':
        # Intentionally invalid input: the canonical writer refuses this
        # moved drill before the independent saved receiver is invoked.
        pcbnew.SaveBoard(str(child),b)
    else:field._save_field_snapshot(b,child)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=worker.receive(source,child,board_hint='synthetic',**scope,**options)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert source.read_bytes()==frozen
