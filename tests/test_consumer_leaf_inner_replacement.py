"""A whole-leaf replacement keeps the actual floor of an explicit inner face."""
from unittest import mock
import pcbnew
import pytest
import cec_consumer_leaf_reconstruction as worker
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_consumer_leaf_reconstruction import case


def make(monkeypatch,tmp_path,angle=0,mirror=False):
    source,scope,catalog,points,_,net,retained,_=case(monkeypatch,tmp_path,angle,mirror)
    scope['grouped_track_uuids'].append(retained)
    b=pcbnew.LoadBoard(str(source));tap=b.FindFootprintByReference('ANY_PORT').FindPadByNumber('1')
    tap.SetAttribute(pcbnew.PAD_ATTRIB_PTH);tap.SetLayerSet(pcbnew.LSET.AllCuMask());tap.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proposal=worker.plan(b,source,board_hint='synthetic',**scope)
    start=tuple(b.FindFootprintByReference('ANY_PORT').FindPadByNumber('1').GetPosition())
    worker.subtract(b,proposal)
    t=pcbnew.PCB_TRACK(b);t.SetNetCode(b.GetNetcodeFromNetname(net));t.SetLayer(pcbnew.In2_Cu)
    t.SetWidth(proposal['full_budget_routing_widths_nm']['In2.Cu']);t.SetStart(pcbnew.VECTOR2I(*start));t.SetEnd(pcbnew.VECTOR2I(*points[-1]));b.Add(t)
    worker.assign(b,proposal,[force._uid(t)]);additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'inner-child');field._save_field_snapshot(b,child)
    return source,child,scope,catalog,force._uid(t)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_existing_native_inner_access_uses_complete_inner_budget_not_outer_floor(monkeypatch,tmp_path,angle,mirror):
    source,child,scope,catalog,incoming=make(monkeypatch,tmp_path,angle,mirror);frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        conservative=worker.receive(source,child,board_hint='synthetic',**scope)
        proof=worker.receive(source,child,board_hint='synthetic',allow_rated_replacement_inner_layers=True,**scope)
    assert not conservative['ok']
    assert proof['ok'] and proof['complete'],proof
    assert proof['source_scope']['full_budget_routing_widths_nm']['In2.Cu']>proof['source_scope']['full_budget_outer_widths_nm']['F.Cu']
    assert proof['incoming_track_uuids']==[incoming] and proof['new_barrels_added']==0
    assert proof['source_scope']['budget']['current_authority']['amps']==.5
    assert proof['source_scope']['budget']['aggregate_current_authority']['amps']==3.
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('fault',['boolean','thin_inner','ground_plane','undeclared_inner_face'])
def test_explicit_inner_replacement_cannot_relax_floor_or_plane_roles(monkeypatch,tmp_path,fault):
    source,child,scope,catalog,incoming=make(monkeypatch,tmp_path);frozen=source.read_bytes()
    b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if force._uid(t)==incoming)
    options=dict(allow_rated_replacement_inner_layers=True)
    if fault=='boolean':options['allow_rated_replacement_inner_layers']=1
    elif fault=='thin_inner':t.SetWidth(200000)
    elif fault=='ground_plane':t.SetLayer(pcbnew.In1_Cu)
    else:t.SetLayer(pcbnew.In3_Cu)
    field._save_field_snapshot(b,child)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        proof=worker.receive(source,child,board_hint='synthetic',**scope,**options)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert source.read_bytes()==frozen
