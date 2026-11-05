"""A retained cyclic mesh does not make its actual dead tip functional."""
import copy,json,math
import pytest,pcbnew
import cec_ground_mesh_spur as spur
import cec_force_current as force
import cec_additive_route_receiving as additive
import cec_field_coupling as field
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path,angle=0,mirror=1,layer=pcbnew.F_Cu):
    source,b=ground_fixture(tmp_path)
    def xy(p):
        x,y=p;x*=mirror;r=math.radians(angle)
        return round(12+x*math.cos(r)-y*math.sin(r),6),round(14+x*math.sin(r)+y*math.cos(r),6)
    mesh=[track(b,'GND',xy(a),xy(c)) for a,c in [((0,0),(3,0)),((3,0),(3,3)),((3,3),(0,0))]]
    for item in mesh:item.SetLayer(layer)
    root=pcbnew.PCB_VIA(b);root.SetNetCode(b.GetNetcodeFromNetname('GND'))
    root.SetPosition(pcbnew.VECTOR2I_MM(*xy((3,0))));root.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    root.SetViaType(pcbnew.VIATYPE_THROUGH);root.SetWidth(600000);root.SetDrill(300000);b.Add(root)
    seed=track(b,'GND',xy((0,0)),xy((0,-.6)));seed.SetLayer(layer)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,b,seed,mesh,root,xy


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[1,-1])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_only_spur_removed_whole_retained_mesh_and_saved_returns_preserved(tmp_path,angle,mirror,layer):
    source,b,seed,mesh,root,_=fixture(tmp_path,angle,mirror,layer)
    before=source.read_bytes();p=json.loads(json.dumps(spur.plan(b,force._uid(seed))))
    assert p['retired_track_uuids']==[force._uid(seed)]
    assert p['retained_root_via_uuid']==force._uid(root) and p['retained_mesh_never_pruned']
    spur.subtract(b,p);child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    r=spur.receive(source,child,p,board_hint='unclassified-test')
    assert r['ok'] and r['complete'],r
    assert not r['current_qualified'] and not r['release_authority']
    assert {force._uid(t) for t in mesh}|{force._uid(root)}<={force._uid(t) for t in b.GetTracks()}
    assert source.read_bytes()==before


@pytest.mark.parametrize('case',['locked','group','bridge','pad','foreign_pad','unfilled','missing_root','foreign_track','width','length'])
def test_missing_positive_leaf_or_saved_plane_evidence_refuses(tmp_path,case):
    _,b,seed,mesh,root,xy=fixture(tmp_path)
    if case=='locked':seed.SetLocked(True)
    if case=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(seed)
    if case=='bridge':track(b,'GND',xy((0,-.6)),xy((3,0)))
    if case in ('pad','foreign_pad'):
        f=pcbnew.FOOTPRINT(b);b.Add(f);p=pcbnew.PAD(f);f.Add(p)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);p.SetLayerSet(mask)
        p.SetNetCode(b.GetNetcodeFromNetname('GND' if case=='pad' else '/CONTROL'))
        p.SetPosition(pcbnew.VECTOR2I_MM(*xy((0,-.6))));p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    if case=='unfilled':
        for z in b.Zones():z.UnFill()
    if case=='missing_root':root.SetPosition(pcbnew.VECTOR2I_MM(28,28))
    if case=='foreign_track':track(b,'/CONTROL',xy((0,-.6)),xy((1,-.6)))
    if case=='width':seed.SetWidth(400000)
    if case=='length':seed.SetEnd(pcbnew.VECTOR2I_MM(*xy((0,-5))))
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):spur.plan(b,force._uid(seed))
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('case',['forged','stale','unrelated_change'])
def test_exact_plan_and_saved_delta_are_required(tmp_path,case):
    source,b,seed,mesh,root,_=fixture(tmp_path);p=spur.plan(b,force._uid(seed))
    if case=='forged':
        p=copy.deepcopy(p);p['retired_track_uuids'].append(force._uid(mesh[0]))
    if case=='stale':track(b,'/CONTROL',(23,23),(24,24))
    if case!='unrelated_change':
        with pytest.raises(ValueError,match='stale_or_forged'):spur.subtract(b,p)
    else:
        spur.subtract(b,p);mesh[0].SetWidth(250000)
        child=force._copy_family(source,tmp_path/'other');additive._ground_refill(b);field._save_field_snapshot(b,child)
        assert not spur.receive(source,child,p,board_hint='unclassified-test')['ok']
