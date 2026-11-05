"""Cheap native ranking must never become cut/current authority."""
import pcbnew
import pytest
import cec_native_retirement_screen as screen
import cec_field_coupling as field
from test_redundant_supply_branch_sweep import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_screen_distinguishes_whole_redundant_tree_from_essential_or_partial_cut(tmp_path,quarter,mirror,face):
    source,ids,main,catalog=fixture(tmp_path,quarter,mirror,face);b=pcbnew.LoadBoard(str(source))
    original=source.read_bytes();fields=field._field_snapshot_inventory(b)
    native={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
    axis=native[main].GetEnd()-native[main].GetStart()
    sides=[u for u in ids for v in [native[u].GetEnd()-native[u].GetStart()] if axis.x*v.y-axis.y*v.x]
    assert len(sides)==2
    assert screen.screen(b,sorted(ids),timeout_s=1.)['state']=='preserved'
    assert screen.screen(b,[main],timeout_s=1.)['state']=='lost'
    assert screen.screen(b,sides,timeout_s=1.)['state']=='lost'
    assert source.read_bytes()==original and field._field_snapshot_inventory(b)==fields
    proof=screen.screen(b,sorted(ids),timeout_s=1.)
    assert proof['complete'] and not proof['source_mutated'] and not proof['admission_or_deletion_authority']


@pytest.mark.parametrize('fault',['missing','mixed_net','bound','unfilled'])
def test_incomplete_or_unknown_native_inventory_is_not_a_no_path_proof(tmp_path,fault):
    source,ids,main,catalog=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));args={};cut=sorted(ids)
    if fault=='missing':cut=['absent']
    elif fault=='bound':args['max_items']=1
    elif fault=='mixed_net':
        t=next(t for t in b.GetTracks() if str(t.m_Uuid.AsString()) in ids)
        n=pcbnew.NETINFO_ITEM(b,'UNRELATED');b.Add(n);t.SetNet(n)
    elif fault=='unfilled':
        z=pcbnew.ZONE(b);z.SetNet(next(iter(b.GetTracks())).GetNet());z.SetLayer(pcbnew.F_Cu);b.Add(z)
    proof=screen.screen(b,cut,**args)
    assert proof['state']=='unknown' and not proof['complete'] and not proof['admission_or_deletion_authority']
