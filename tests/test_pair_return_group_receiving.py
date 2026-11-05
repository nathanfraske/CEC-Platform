"""Existing return ownership can only grow by exact new ordinary GND vias."""
from pathlib import Path
import pcbnew as pcb
import pytest
import cec_additive_route_receiving as receive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def barrel(board,at):
    v=pcb.PCB_VIA(board);v.SetViaType(pcb.VIATYPE_THROUGH)
    v.SetLayerPair(pcb.F_Cu,pcb.B_Cu);v.SetPosition(pcb.VECTOR2I_MM(*at))
    v.SetWidth(600000);v.SetDrill(300000);v.SetNetCode(board.GetNetcodeFromNetname('GND'))
    board.Add(v);return v


def fixture(tmp_path):
    source,b=ground_fixture(tmp_path)
    ds=b.GetDesignSettings();ds.m_MinThroughDrill=300000
    ds.m_ViasMinSize=600000;ds.m_ViasMinAnnularWidth=150000
    original=barrel(b,(22,18));fr.group_local_pair_return_vias(b,[original])
    field._save_field_snapshot(b,source)
    target=force._copy_family(source,tmp_path/'pair-return-child')
    child=pcb.LoadBoard(str(target));incoming=barrel(child,(26,18))
    fr.group_local_pair_return_vias(child,[incoming])
    receive._ground_refill(child);field._save_field_snapshot(child,target)
    return source,target,original.m_Uuid.AsString(),incoming.m_Uuid.AsString()


def test_explicit_ground_extension_replays_exact_source_members_without_waivers(tmp_path):
    source,target,old,new=fixture(tmp_path)
    before=[p.read_bytes() for p in (source,target)]
    assert not receive.receive(source,target)['ok']
    proof=receive.receive(source,target,allow_pair_return_via_additions=True)
    assert proof['ok'] and proof['complete'],proof['errors']
    group=[r for r in proof['allowed_original_changes']
           if r['kind']=='exact_new_ground_return_group_extension']
    assert len(group)==1 and group[0]['added_members']==[new]
    assert group[0]['geometry_proofs'][0]['drill_nm']==300000
    assert not proof['release_authority'] and not proof['inherited_debt_qualified']
    assert [p.read_bytes() for p in (source,target)]==before


@pytest.mark.parametrize('fault',['signal_net','non_via','old_member_claim','remove_original',
    'original_via_edit','small_drill','small_ring','renamed_group','ground_outline'])
def test_ground_extension_never_accepts_unrelated_or_unqualified_geometry(tmp_path,fault):
    source,target,old,new=fixture(tmp_path);b=pcb.LoadBoard(str(target))
    items={t.m_Uuid.AsString():t for t in b.GetTracks()}
    g=next(g for g in b.Groups() if g.GetName()==fr.LOCAL_PAIR_RETURN_VIA_GROUP)
    if fault=='signal_net':items[new].SetNetCode(b.GetNetcodeFromNetname('/CONTROL'))
    elif fault=='non_via':
        incoming=track(b,'GND',(22,20),(26,20));g.AddItem(incoming)
    elif fault=='old_member_claim':
        g.AddItem(next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'))
    elif fault=='remove_original':g.RemoveItem(items[old])
    elif fault=='original_via_edit':items[old].SetWidth(800000)
    elif fault=='small_drill':items[new].SetDrill(200000)
    elif fault=='small_ring':items[new].SetDrill(500000)
    elif fault=='renamed_group':g.SetName('not_an_authority')
    elif fault=='ground_outline':
        next(z for z in b.Zones() if z.GetNetname()=='GND').Outline().SetVertex(0,pcb.VECTOR2I_MM(1,1))
    # Keep rejected fixtures native-serializable: the signal-net barrel needs
    # its real GND antipad, and the non-via case must not short /CONTROL.
    receive._ground_refill(b)
    field._save_field_snapshot(b,target)
    proof=receive.receive(source,target,allow_pair_return_via_additions=True)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


def test_ground_extension_mode_requires_positive_boolean_not_truthy_data(tmp_path):
    proof=receive.receive(tmp_path/'none',tmp_path/'other',allow_pair_return_via_additions=1)
    assert proof['errors']==['ValueError:explicit_pair_return_addition_mode_required']
