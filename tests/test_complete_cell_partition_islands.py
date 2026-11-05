"""Complete-cell motion must preserve each physical Source fill island."""
import json
import time

import pcbnew
import pytest

import cec_complete_cell_receiving as receiving
import cec_force_current as force
from cec_native_items import discard_items,discard_footprint_children
from test_native_partition_pair import board,bridge,clone,setfill,rect


def check(a,b,poses=(),retired=()):
    return receiving._preserve_partitions(a,b,poses,retired,time.monotonic()+10.)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('first',[False,True])
def test_real_bridge_loss_never_borrows_whole_zone_owner(face,first):
    a,z=board(face,first=first);t=bridge(a,z);b=clone(a)
    discard_items(b,[i for i in b.GetTracks()if force._uid(i)==force._uid(t)])
    with pytest.raises(ValueError,match='original_terminal_or_copper_partition_lost'):
        check(a,b,retired={force._uid(t)})


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_legitimate_antipad_refill_preserves_actual_component(face):
    a,z=board(face,solid=True);b=clone(a)
    setfill(next(iter(b.Zones())),[[rect(0,0,10000000,4000000),rect(4500000,1500000,5500000,2500000)]])
    proof=check(a,b)
    assert proof['preserved'] and proof['exact_positive_native_island_overlap']
    assert not proof['whole_zone_uuid_connectivity_credit']
    assert not proof['routing_admitted'] and not proof['release_authority']
    assert json.loads(json.dumps(proof))==proof


@pytest.mark.parametrize('same_uid',[False,True])
def test_exact_moved_cell_pad_keys_rebind_without_cloned_child_overwrite(same_uid):
    a,z=board(solid=True);uids=[]
    for n in range(2):
        fp=pcbnew.FOOTPRINT(a);fp.SetReference('cell'+str(n));a.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(z.GetNet())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
        p.SetSize(pcbnew.VECTOR2I(200000,200000));p.SetPosition(pcbnew.VECTOR2I(500000+n*1000000,500000))
        if same_uid and uids:p.m_Uuid.Clone(pcbnew.KIID(uids[0]))
        fp.Add(p);uids.append(force._uid(p))
    b=clone(a)
    for fp in b.GetFootprints():fp.Move(pcbnew.VECTOR2I(200000,0))
    proof=check(a,b,{'cell0','cell1'})
    assert proof['preserved'] and proof['source_component_count']==1


@pytest.mark.parametrize('fault',['net','size','number','owner','delete'])
def test_rebinding_cannot_hide_changed_native_land_identity(fault):
    a,z=board(solid=True);fp=pcbnew.FOOTPRINT(a);fp.SetReference('cell');a.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(z.GetNet());p.SetSize(pcbnew.VECTOR2I(200000,200000));fp.Add(p)
    p.SetPosition(pcbnew.VECTOR2I(500000,500000));b=clone(a);f=b.FindFootprintByReference('cell');q=next(iter(f.Pads()))
    if fault=='net':q.SetNetCode(0)
    elif fault=='size':q.SetSize(pcbnew.VECTOR2I(300000,200000))
    elif fault=='number':q.SetNumber('2')
    elif fault=='owner':f.SetReference('other')
    else:discard_footprint_children(b,f,[q])
    with pytest.raises(ValueError):check(a,b,{'cell'})


def test_expired_cell_lease_refuses_before_partition_work():
    a,z=board();b=clone(a)
    with pytest.raises(ValueError,match='partition_receiving_deadline'):
        receiving._preserve_partitions(a,b,(),(),time.monotonic()-1.)
