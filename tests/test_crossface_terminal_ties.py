"""Discovery may propose an exact real barrel tie; it never authorizes a cut."""
import pcbnew
import pytest
import cec_crossface_terminal_ties as ties
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


def fixture(turn=0,mirror=False):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,'/arbitrary/POWER');b.Add(n)
    for index,xy in enumerate(((10,10),(10,15),(15,15),(15,10))):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('Different'+str(index));p=pcbnew.PAD(fp)
        p.SetNumber(str(index));p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(pcbnew.VECTOR2I_MM(2,2));p.SetDrillSize(pcbnew.VECTOR2I_MM(1,1))
        p.SetLayerSet(pcbnew.LSET.AllCuMask());p.SetNet(n);p.SetPosition(pcbnew.VECTOR2I_MM(*xy));fp.Add(p);b.Add(fp)
    seeds=[]
    for first,last in (((10,10),(10,15)),((10,15),(15,15)),((15,15),(15,10))):
        old=track(b,n.GetNetname(),first,last,width=.8,layer=pcbnew.In3_Cu);old.SetLocked(True)
        track(b,n.GetNetname(),last,first,width=.8,layer=pcbnew.B_Cu);seeds.append(force._uid(old))
    angle=pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T)
    for item in [*b.GetTracks(),*b.GetFootprints()]:
        if mirror:item.Flip(pcbnew.VECTOR2I_MM(15,15),True)
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),angle)
    return b,seeds


@pytest.mark.parametrize('turn',(0,90,180,270))
@pytest.mark.parametrize('mirror',(False,True))
def test_rotated_mirrored_renamed_tie_expands_to_whole_exact_native_component(turn,mirror):
    b,ids=fixture(turn,mirror);before=field._field_snapshot_inventory(b)
    q=ties.discover(b,ids[:2]);assert set(q['track_uuids'])==set(ids)
    assert q['exact_actual_plated_centres_not_logical_pin_equivalence']
    assert not q['cut_authority'] and not q['current_qualified'] and not q['release_authority']
    assert all(row['unchanged_native_keeper_witnesses'] for row in q['witnesses'])
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',('no_drill','smd','npth','narrow_keeper','staggered','wrong_net',
    'no_keeper','disabled_face','grouped_source','same_face_keeper'))
def test_logical_or_approximate_relationships_do_not_witness_a_real_tie(fault):
    b,ids=fixture();old=next(t for t in b.GetTracks() if force._uid(t)==ids[0])
    keeper=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu
        and {tuple(t.GetStart()),tuple(t.GetEnd())}=={tuple(old.GetStart()),tuple(old.GetEnd())})
    pad=next(p for fp in b.GetFootprints() for p in fp.Pads() if p.GetPosition()==old.GetStart())
    if fault=='no_drill':pad.SetDrillSize(pcbnew.VECTOR2I(0,0))
    elif fault=='smd':pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    elif fault=='npth':pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault=='narrow_keeper':keeper.SetWidth(799999)
    elif fault=='staggered':keeper.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='wrong_net':keeper.SetNetCode(0)
    elif fault=='no_keeper':b.Remove(keeper)
    elif fault=='disabled_face':keeper.SetLayer(pcbnew.In10_Cu)
    elif fault=='grouped_source':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(old)
    else:keeper.SetLayer(old.GetLayer())
    with pytest.raises(ValueError):ties.discover(b,ids[:2])


def test_disconnected_exact_duplicates_are_not_swept_into_the_seed_component():
    b,ids=fixture();n=b.FindNet('/arbitrary/POWER')
    for xy in ((20,20),(25,20)):
        fp=pcbnew.FOOTPRINT(b);p=pcbnew.PAD(fp);p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetSize(pcbnew.VECTOR2I_MM(2,2));p.SetDrillSize(pcbnew.VECTOR2I_MM(1,1))
        p.SetLayerSet(pcbnew.LSET.AllCuMask());p.SetNet(n);p.SetPosition(pcbnew.VECTOR2I_MM(*xy));fp.Add(p);b.Add(fp)
    extra=track(b,n.GetNetname(),(20,20),(25,20),width=.8,layer=pcbnew.In3_Cu)
    track(b,n.GetNetname(),(20,20),(25,20),width=.8,layer=pcbnew.B_Cu)
    assert force._uid(extra) not in ties.discover(b,ids[:2])['track_uuids']


@pytest.mark.parametrize('bound',(True,False,0,17,None,'8'))
def test_invalid_bounds_never_truncate_a_whole_component(bound):
    b,ids=fixture()
    with pytest.raises(ValueError):ties.discover(b,ids[:2],max_tracks=bound)


def test_a_valid_bound_cannot_silently_omit_the_third_edge():
    b,ids=fixture()
    with pytest.raises(ValueError,match='whole_connected'):ties.discover(b,ids[:2],max_tracks=2)


@pytest.mark.parametrize('budget',(True,False,0,-1,11,float('nan'),float('inf')))
def test_invalid_work_budget_refuses_without_any_cut_authority(budget):
    b,ids=fixture()
    with pytest.raises(ValueError):ties.discover(b,ids[:2],timeout_s=budget)
