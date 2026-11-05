"""No local-budget repair can acquire an unproved shared-rail branch."""
from unittest import mock
import pcbnew
import pytest
import cec_supply_consumer_branch as consumer
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_supply_consumer_branch import fixture


def repair_fixture(monkeypatch,tmp_path,angle=0,mirror=False):
    b,root,anchor,new,old,trunk,group,row,rail,declaration,cap=fixture(
        monkeypatch,tmp_path,angle=angle,mirror=mirror)
    budget=consumer.contract(b,force._uid(root),board_hint='synthetic')
    for at in (old.GetStart(),old.GetEnd()):
        v=pcbnew.PCB_VIA(b);v.SetPosition(at);v.SetNet(root.GetNet());v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    old.SetLayer(pcbnew.In2_Cu)
    source=tmp_path/'source.kicad_pcb';loaded=field._save_field_snapshot(b,source)
    # Synthetic MPN text initially omits KiCad's default stroke thickness.
    # Canonicalize the fixture BEFORE binding the immutable source family.
    field._save_field_snapshot(loaded,source)
    child=force._copy_family(source,tmp_path/'candidate');b=pcbnew.LoadBoard(str(child))
    uid=force._uid(old);start,end=old.GetStart(),old.GetEnd()
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    t=pcbnew.PCB_TRACK(b);t.SetNetCode(b.GetNetcodeFromNetname(root.GetNetname()))
    t.SetStart(start);t.SetEnd(end);t.SetWidth(500000)
    t.SetLayer(pcbnew.In2_Cu);b.Add(t);field._save_field_snapshot(b,child)
    net=str(root.GetNetname())
    raw=dict(net=net,current_authority=rail,profile='jlcpcb_6l_pofv_signal',
        required_by_layer_mm={k:max(.2,v) for k,v in budget['aggregate_required_by_layer_mm'].items()},
        routing_layers=['F.Cu','In2.Cu','B.Cu'],clearance_mm=.2)
    return source,child,uid,net,{'contracts':{net:raw}},declaration,force._uid(t)


OPTIONS=dict(allow_rated_layer_bridges=True,max_source_width_mm=1.,
    max_replacement_width_mm=1.,allow_rated_source_inner_layers=True,
    use_source_declared_consumer_island=True)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_existing_declared_leaf_repair_keeps_source_trunk_and_actual_budget(monkeypatch,tmp_path,angle,mirror):
    source,child,uid,net,catalog,_,incoming=repair_fixture(monkeypatch,tmp_path,angle,mirror)
    original=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        legacy=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            **dict(OPTIONS,use_source_declared_consumer_island=False))
        received=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],**OPTIONS)
        composed=chain.receive(source,child,board_hint='synthetic',phases=[dict(kind='rated_branch',
            candidate=str(child),retired_track_uuids=[uid],**OPTIONS)])
    assert not legacy['ok']
    assert received['ok'] and received['complete'] and composed['ok'] and composed['complete'],(received,composed)
    scope=received['source_proposal']['source_declared_consumer_scope']
    assert scope['aggregate_contracts'][net]['current_authority']['amps']==3.
    assert received['source_proposal']['contracts'][net]['current_authority']['amps']==.5
    assert received['independent_saved_consumer_scope']['proofs'][0]['new_tracks']==[incoming]
    assert not received['current_authority'] and not received['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['outside_leaf','thin','inner_narrow','unknown_load','source_group',
    'missing_policy','boolean_mode','mixed_repair_modes','changed_aggregate'])
def test_unproved_local_reconstruction_refuses_without_aggregate_or_current_waivers(monkeypatch,tmp_path,fault):
    source,child,uid,net,catalog,declaration,incoming=repair_fixture(monkeypatch,tmp_path)
    options=dict(OPTIONS)
    if fault in ('outside_leaf','thin','inner_narrow'):
        b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if force._uid(t)==incoming)
        if fault=='outside_leaf':
            extra=pcbnew.PCB_TRACK(b);extra.SetNetCode(t.GetNetCode());extra.SetLayer(pcbnew.B_Cu)
            extra.SetStart(pcbnew.VECTOR2I_MM(15,5));extra.SetEnd(pcbnew.VECTOR2I_MM(18,5));extra.SetWidth(500000);b.Add(extra)
        elif fault=='thin':t.SetWidth(100000)
        else:t.SetWidth(400000)
        field._save_field_snapshot(b,child)
    if fault in ('unknown_load','source_group'):
        b=pcbnew.LoadBoard(str(source))
        if fault=='source_group':
            g=pcbnew.PCB_GROUP(b);g.SetName('different source owner');b.Add(g)
            g.AddItem(next(t for t in b.GetTracks() if force._uid(t)==uid))
        else:
            fp=pcbnew.FOOTPRINT(b);fp.SetValue('unknown load');b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p)
            p.SetNetCode(b.GetNetcodeFromNetname(net));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(1,1));p.SetPosition(pcbnew.VECTOR2I_MM(5,5))
        field._save_field_snapshot(b,source)
    if fault=='missing_policy':declaration['params']['supply_consumer_allocations']=[]
    if fault=='boolean_mode':options['use_source_declared_consumer_island']=1
    if fault=='mixed_repair_modes':options.update(allow_rated_source_inner_layers=True,repair_undersized_source=True)
    if fault=='changed_aggregate':catalog['contracts'][net]['current_authority']=dict(catalog['contracts'][net]['current_authority'],amps=2.)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        result=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],**options)
    assert not result['ok'] and result['errors'],result
