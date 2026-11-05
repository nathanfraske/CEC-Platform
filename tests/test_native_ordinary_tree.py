"""Branch proposals preserve actual cross-layer connectivity and work bounds."""
import pcbnew
import pytest
import cec_force_current as force
import cec_native_ordinary_tree as tree
from cec_local_copper_cell import copper_inventory


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_integer_tree_and_existing_component_are_order_and_pose_independent(angle,mirror,reverse):
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return [x,y]
    ports=dict(a=at(0,0),b=at(0,10),c=at(30,10),d=at(30,0))
    if reverse:ports=dict(reversed(list(ports.items())))
    variants=tree.spanning_variants(ports,[['b','a'],['c'],['d']])
    assert variants[0]==[['c','d'],['a','d']]
    assert 1<=len(variants)<=4 and all(len(v)==2 for v in variants)
    assert all(['a','b'] not in v for v in variants)
    assert tree.spanning_variants(ports,[list(ports)])==[[]]
    assert tree.spanning_variants(ports,[['a','b'],['c'],['d']],maximum_variants=1)==[variants[0]]


@pytest.mark.parametrize('bad',['missing','repeat','unknown','empty','bool','too_many','coord','variant'])
def test_graph_proposal_bounds_and_exact_partition(bad):
    ports=dict(a=[0,0],b=[1,1]);components=[['a'],['b']];kw={}
    if bad=='missing':components=[['a']]
    elif bad=='repeat':components=[['a','b'],['b']]
    elif bad=='unknown':components=[['a'],['x']]
    elif bad=='empty':components=[['a'],[]]
    elif bad=='bool':ports['a']=[True,0]
    elif bad=='too_many':ports={str(i):[i,0] for i in range(9)};components=[list(ports)]
    elif bad=='coord':ports['a']=[2_000_000_001,0]
    else:kw['maximum_variants']=5
    with pytest.raises(ValueError):tree.spanning_variants(ports,components,**kw)


def native_fixture(plated=True):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,'/renamed/ordinary');b.Add(n)
    def pad(x,attribute):
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(n)
        p.SetPosition(pcbnew.VECTOR2I_MM(x,20));p.SetSize(pcbnew.VECTOR2I_MM(1,1))
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetAttribute(attribute)
        p.SetLayerSet(pcbnew.LSET.AllCuMask());p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
        return p
    a=pad(10,pcbnew.PAD_ATTRIB_PTH if plated else pcbnew.PAD_ATTRIB_NPTH)
    c=pad(15,pcbnew.PAD_ATTRIB_PTH)
    d=pad(20,pcbnew.PAD_ATTRIB_PTH)
    def track(x,y,layer):
        t=pcbnew.PCB_TRACK(b);t.SetNet(n);t.SetLayer(layer);t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I_MM(x,20));t.SetEnd(pcbnew.VECTOR2I_MM(y,20));b.Add(t);return t
    old=track(10,20,pcbnew.F_Cu);alternate=track(10,15,pcbnew.B_Cu)
    return b,old,alternate,a,c,d


def test_retained_real_plated_barrels_connect_ports_without_redundant_top_route():
    b,old,alternate,a,c,d=native_fixture();before=copper_inventory(b)
    cut=[force._uid(old)];r=tree.retained_port_components(b,str(old.GetNetname()),int(pcbnew.F_Cu),cut)
    assert sorted(map(len,r['components']))==[1,2]
    assert any(set(group)=={force._uid(a),force._uid(c)} for group in r['components'])
    proposals=tree.spanning_variants(r['ports'],r['components'])
    assert len(proposals[0])==1
    assert not r['source_cut_authorized'] and not r['route_admitted'] and not r['new_capacity_credited']
    assert copper_inventory(b)==before
    # A newly constructed REAL route can join components before the next
    # branch is planned. No virtual disks or same-XY unions enter this proof.
    t=alternate.Duplicate();t.m_Uuid.Clone(pcbnew.KIID())
    t.SetStart(c.GetPosition());t.SetEnd(d.GetPosition());b.Add(t)
    now=tree.retained_port_components(b,str(old.GetNetname()),int(pcbnew.F_Cu),cut)
    assert len(now['components'])==1 and tree.spanning_variants(now['ports'],now['components'])==[[]]


def test_npth_is_not_a_cross_layer_contact_or_branch_port():
    b,old,alternate,a,c,d=native_fixture(plated=False)
    r=tree.retained_port_components(b,str(old.GetNetname()),int(pcbnew.F_Cu),[force._uid(old)])
    assert force._uid(a) not in r['ports'] and len(r['ports'])==2


@pytest.mark.parametrize('fault',['no_cut','via','wrong_net','wrong_layer','bool_timeout','duplicate'])
def test_native_source_and_budget_must_be_literal(fault):
    b,old,_,_,_,_=native_fixture();ids=[force._uid(old)];net=str(old.GetNetname());layer=int(pcbnew.F_Cu);kw={}
    if fault=='no_cut':ids=[]
    elif fault=='via':ids=['missing-actual-track']
    elif fault=='wrong_net':net='/wrong'
    elif fault=='wrong_layer':layer=int(pcbnew.B_Cu)
    elif fault=='bool_timeout':kw['timeout_s']=True
    else:ids*=2
    with pytest.raises(ValueError):tree.retained_port_components(b,net,layer,ids,**kw)
