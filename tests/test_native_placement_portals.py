"""A local portal is native contact, not a nearest-via ownership heuristic."""
import pcbnew
import pytest
import cec_native_placement_context as native


def fixture(*,face=pcbnew.F_Cu):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,'/RENAMED_RETURN');b.Add(net)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('OWNER_OTHER_BOARD');b.Add(fp)
    p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(net);p.SetNumber('R')
    p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);ls=pcbnew.LSET();ls.AddLayer(face);p.SetLayerSet(ls)
    p.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(21,20));v.SetNet(net)
    v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    return b,fp,p,v,net


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_short_dogbone_on_actual_face_is_a_read_only_source_contact(face):
    b,fp,p,v,net=fixture(face=face)
    t=pcbnew.PCB_TRACK(b);t.SetLayer(face);t.SetNet(net);t.SetWidth(200000)
    t.SetStart(p.GetPosition());t.SetEnd(v.GetPosition());b.Add(t)
    before=(tuple(p.GetPosition()),tuple(v.GetPosition()),tuple(t.GetStart()))
    rows=native.local_portals(b,[fp.GetReference()])
    assert len(rows)==1 and rows[0]['source_contacts'][0]['dogbone_track_uuids']==[t.m_Uuid.AsString()]
    assert before==(tuple(p.GetPosition()),tuple(v.GetPosition()),tuple(t.GetStart()))
    assert rows[0]['all_actual_pad_contacts_in_scope']
    assert not rows[0]['automatic_motion_or_retirement_authority']


def test_nearby_disconnected_via_and_wrong_layer_do_not_become_owned():
    b,fp,p,v,net=fixture(face=pcbnew.B_Cu)
    assert native.local_portals(b,[fp.GetReference()])==[]
    t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNet(net);t.SetWidth(200000)
    t.SetStart(p.GetPosition());t.SetEnd(v.GetPosition());b.Add(t)
    assert native.local_portals(b,[fp.GetReference()])==[]


def test_shared_via_in_pad_never_silently_reassigns_an_unselected_owner():
    b,fp,p,v,net=fixture();v.SetPosition(p.GetPosition())
    other=pcbnew.FOOTPRINT(b);other.SetReference('SECOND_OWNER');b.Add(other)
    q=pcbnew.PAD(other);other.Add(q);q.SetNet(net);q.SetNumber('G')
    q.SetSize(pcbnew.VECTOR2I_MM(.8,.8));q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    q.SetLayerSet(p.GetLayerSet());q.SetPosition(p.GetPosition())
    rows=native.local_portals(b,[fp.GetReference()])
    assert len(rows)==1 and not rows[0]['all_actual_pad_contacts_in_scope']
    assert {r['ref'] for r in rows[0]['shared_pad_contacts']}=={fp.GetReference(),other.GetReference()}
    assert not rows[0]['electrical_or_release_authority']


def test_second_exact_dogbone_owner_is_not_mistaken_for_a_private_portal():
    b,fp,p,v,net=fixture()
    other=pcbnew.FOOTPRINT(b);other.SetReference('SECOND_OWNER');b.Add(other)
    q=pcbnew.PAD(other);other.Add(q);q.SetNet(net);q.SetNumber('G')
    q.SetSize(pcbnew.VECTOR2I_MM(.4,.4));q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    q.SetLayerSet(p.GetLayerSet());q.SetPosition(pcbnew.VECTOR2I_MM(22,20))
    for pad in (p,q):
        t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNet(net);t.SetWidth(200000)
        t.SetStart(pad.GetPosition());t.SetEnd(v.GetPosition());b.Add(t)
    rows=native.local_portals(b,[fp.GetReference()])
    assert len(rows)==1 and rows[0]['all_actual_pad_contacts_in_scope']
    assert not rows[0]['all_source_contacts_in_scope']
    assert {r['ref'] for r in rows[0]['shared_dogbone_contacts']}=={fp.GetReference(),other.GetReference()}


def test_coincident_barrels_each_retain_every_actual_dogbone_owner():
    b,fp,p,v,net=fixture()
    second=pcbnew.PCB_VIA(b);second.SetPosition(v.GetPosition());second.SetNet(net)
    second.SetWidth(600000);second.SetDrill(300000)
    second.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(second)
    other=pcbnew.FOOTPRINT(b);other.SetReference('SECOND_OWNER');b.Add(other)
    q=pcbnew.PAD(other);other.Add(q);q.SetNet(net);q.SetNumber('G')
    q.SetSize(pcbnew.VECTOR2I_MM(.4,.4));q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    q.SetLayerSet(p.GetLayerSet());q.SetPosition(pcbnew.VECTOR2I_MM(22,20))
    for pad in (p,q):
        t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNet(net);t.SetWidth(200000)
        t.SetStart(pad.GetPosition());t.SetEnd(v.GetPosition());b.Add(t)
    rows=native.local_portals(b,[fp.GetReference()])
    assert {r['via_uuid'] for r in rows}=={v.m_Uuid.AsString(),second.m_Uuid.AsString()}
    for row in rows:
        assert not row['all_source_contacts_in_scope']
        assert {r['ref'] for r in row['shared_dogbone_contacts']}=={fp.GetReference(),other.GetReference()}
        assert not row['automatic_motion_or_retirement_authority']


@pytest.mark.parametrize('kwargs',[{'footprint_refs':['stale']},
    {'footprint_refs':['OWNER_OTHER_BOARD']*2},{'dogbone_nm':True},
    {'dogbone_nm':1500001},{'timeout_s':0},{'timeout_s':float('nan')}])
def test_invalid_or_unbounded_scope_fails(kwargs):
    b,fp,p,v,net=fixture();args=dict(footprint_refs=[fp.GetReference()]);args.update(kwargs)
    with pytest.raises(ValueError):native.local_portals(b,**args)
