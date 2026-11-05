"""Native scalar INPUT ownership is not power, pair or arbitrary rip-up."""
import copy,json,time
from pathlib import Path
import pcbnew
import pytest
import cec_cell_escape_replan as cell
import cec_measurement_leaf as leaf
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_route_receiving as ordinary
from test_measurement_leaf import fixture as native_fixture
from test_cell_escape_replan import fixture as cell_fixture
from test_field_proposals import track


def fixture(quarter=0,back=False,name='/unrelated/THRESHOLD-INPUT'):
    b,pad,anchor,tracks,xy=native_fixture(name,quarter)
    b.SetFileName('synthetic-native-scalar-input.kicad_pcb')
    pad.GetParentFootprint().SetValue('TLV7011DBVR');pad.SetNumber('4')
    anchor.SetPosition(xy((14,10)))
    for t,(a,z) in zip(tracks,[((10,10),(12,10)),((12,10),(14,10))]):
        t.SetStart(xy(a));t.SetEnd(xy(z));t.SetLocked(False)
    if back:
        for fp in b.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for p in fp.Pads():
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);layers.AddLayer(pcbnew.B_Mask);p.SetLayerSet(layers)
        for t in tracks:t.SetLayer(pcbnew.B_Cu)
    return b,pad,anchor,tracks,xy


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('name',['/unrelated/THRESHOLD-INPUT','renamed-reference-control'])
def test_source_defined_input_leaf_uses_actual_package_and_native_boundary(quarter,back,name):
    b,pad,anchor,tracks,_=fixture(quarter,back,name);before=leaf._binding(b)
    q=leaf.plan_scalar_input(b,force._uid(pad),board_hint='synthetic')
    assert q['track_uuids']==[force._uid(t) for t in tracks]
    assert q['boundary_uuids']==[force._uid(anchor)] and q['source_length_mm']==pytest.approx(4.)
    assert not q['signal_mode_high_impedance_or_current_assumed'] and not q['sensitive_role_reclassification']
    assert not q['current_authority'] and not q['release_authority']
    assert leaf._binding(b)==before


@pytest.mark.parametrize('fault',['power','declared_current','pair','analog_pair','zone','clock',
    'power_pin_type','unknown_package','output_pin','group','wide','mask','interior_tap','non_smd'])
def test_scalar_input_cannot_retype_or_steal_protected_material(monkeypatch,fault):
    b,pad,anchor,tracks,xy=fixture();net=str(pad.GetNetname())
    import cec_current_topology as topology
    import cec_synth_pipeline as synth
    if fault=='power':monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:{net:{}})
    elif fault=='declared_current':monkeypatch.setattr(synth,'spec_net_current_contract',lambda *a,**kw:{'explicit':True})
    elif fault=='pair':monkeypatch.setattr(leaf.fr,'coupled_pair_nets',lambda *a,**kw:{net})
    elif fault=='analog_pair':monkeypatch.setattr(leaf.semantics,'analog_input_pairs',lambda *a,**kw:[dict(p=net,n='other')])
    elif fault=='zone':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNetCode(pad.GetNetCode());b.Add(z)
    elif fault=='clock':monkeypatch.setattr(field,'classify_net',lambda *a,**kw:dict(power=False,aggressor=True))
    elif fault=='power_pin_type':pad.SetPinType('power_in')
    elif fault=='unknown_package':pad.GetParentFootprint().SetValue('UNKNOWN')
    elif fault=='output_pin':pad.SetNumber('1')
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[0])
    elif fault=='wide':tracks[0].SetWidth(400000)
    elif fault=='mask':tracks[0].SetHasSolderMask(True)
    elif fault=='interior_tap':anchor.SetPosition(xy((11,10)))
    elif fault=='non_smd':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    before=leaf._binding(b)
    with pytest.raises(ValueError):leaf.plan_scalar_input(b,force._uid(pad),board_hint='synthetic',allow_owned_locked=True)
    assert leaf._binding(b)==before


def test_first_real_fork_is_a_retained_boundary_not_a_shared_net_cut():
    b,pad,anchor,tracks,_=fixture();branch=track(b,str(pad.GetNetname()),(12,10),(12,12))
    q=leaf.plan_scalar_input(b,force._uid(pad),board_hint='synthetic')
    assert q['track_uuids']==[force._uid(tracks[0])]
    assert set(q['boundary_uuids'])=={force._uid(tracks[1]),force._uid(branch)}


@pytest.mark.parametrize('seconds',[0,True,-1,11,float('nan')])
def test_scalar_input_lease_is_explicit_finite_and_checked_before_work(seconds):
    b,pad,*_=fixture();before=leaf._binding(b)
    with pytest.raises(ValueError):leaf.plan_scalar_input(b,force._uid(pad),board_hint='synthetic',timeout_s=seconds)
    assert leaf._binding(b)==before


def test_native_lock_grant_is_explicit_and_never_unlocks_source():
    b,pad,_,tracks,_=fixture()
    for t in tracks:t.SetLocked(True)
    before=leaf._binding(b)
    with pytest.raises(ValueError):leaf.plan_scalar_input(b,force._uid(pad),board_hint='synthetic')
    q=leaf.plan_scalar_input(b,force._uid(pad),board_hint='synthetic',allow_owned_locked=True)
    assert set(q['source_owned_locked_track_uuids'])=={force._uid(t) for t in tracks}
    assert all(t.IsLocked() for t in tracks) and before==leaf._binding(b)


@pytest.mark.parametrize('fault',['extra_cut','forged_boundary','forged_role','forged_width','changed_source'])
def test_saved_complete_cell_rederives_input_authority_before_any_mutation(monkeypatch,tmp_path,fault):
    source,b,poses,owner,root,anchor,ids,q=complete(monkeypatch,tmp_path)
    proposal=copy.deepcopy(q)
    if fault=='extra_cut':proposal['retired_track_uuids'].append('unowned')
    elif fault=='forged_boundary':proposal['scalar_input_leaves'][0]['boundary_uuids']=['unowned']
    elif fault=='forged_role':proposal['scalar_input_leaves'][0]['scope']='power_override'
    elif fault=='forged_width':proposal['scalar_input_leaves'][0]['width_nm']=100000
    else:next(t for t in b.GetTracks() if force._uid(t)==ids[0]).SetWidth(210000)
    before=leaf._binding(b)
    with pytest.raises(ValueError):cell.apply_private(b,proposal)
    assert leaf._binding(b)==before


def complete(monkeypatch,tmp_path):
    b,poses,owner,cap=cell_fixture(monkeypatch,prefix='unrelated-input-owner')
    root=owner.FindPadByNumber('4');net=str(root.GetNetname());fp=pcbnew.FOOTPRINT(b)
    fp.SetReference('FIXED');b.Add(fp);p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(b.FindNet(net))
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetPosition(pcbnew.VECTOR2I_MM(16,11));fp.Add(p)
    ids=[]
    for a,z in [((11,11),(12,12)),((12,12),(15,12)),((15,12),(16,11))]:
        t=track(b,net,a,z);t.SetLocked(True);ids.append(force._uid(t))
    source=tmp_path/'source.kicad_pcb';b.SetFileName(str(source));field._save_field_snapshot(b,source)
    q=cell.prepare(b,poses,board_hint='synthetic',allow_owned_locked_escapes=True)
    assert len(q['scalar_input_leaves'])==1
    assert set(q['scalar_input_leaves'][0]['track_uuids'])==set(ids)
    return source,b,poses,owner,root,p,ids,json.loads(json.dumps(q))


def test_saved_native_input_fork_boundary_is_restored_after_cell_motion(monkeypatch,tmp_path):
    source,b,poses,owner,root,anchor,ids,q=complete(monkeypatch,tmp_path)
    parent=pcbnew.LoadBoard(str(source));oldpads={force._uid(p):force._item_key(p) for fp in parent.GetFootprints() for p in fp.Pads()}
    before=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=set(q['retired_track_uuids']))
    cell.apply_private(b,q);requests=cell.obligations(parent,b,q)
    request=requests['scalar_input:'+force._uid(root)]
    assert request['a']['at_nm']==list(root.GetPosition()) and request['b']['at_nm']==list(anchor.GetPosition())
    assert force._uid(anchor) in request['b']['native_uuids']
    assert not request['sensitive_role_reclassification']
    mapping={force._item_key(p):oldpads[force._uid(p)] for fp in b.GetFootprints() for p in fp.Pads()}
    retained=set().union(*before)
    def lost():
        parts=ordinary._partition(b,time.monotonic()+10.,retained_keys=retained,_identity_rebindings=mapping)
        return sum(not any(part<=other for other in parts) for part in before)
    assert lost()==1
    net=str(root.GetNetname());track(b,net,(11,12),(15,12));track(b,net,(15,12),(16,11))
    assert lost()==0
    assert not q['routing_admitted'] and not q['release_authority']
