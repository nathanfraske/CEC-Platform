"""Connected canonical resistors gain only explicit closed-map translation."""
import json
from pathlib import Path

import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_pose_additive_reconstruction as op
import cec_source_reference_group_transport as maps
from test_detached_ordinary_passive_translation import fixture as canonical_fixture


def trace(board,net,a,z,face):
    t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetStart(a);t.SetEnd(z)
    t.SetWidth(200000);t.SetLayer(face);board.Add(t);return t


def fixture(tmp_path,quarter=0,back=False,small=False):
    source,root,owner=canonical_fixture(tmp_path,quarter=quarter,back=back)
    root.write_text(root.read_text().replace('RENAMED_R','R91'))
    if small:
        root.write_text(root.read_text().replace('fixture:R"','fixture:R_Small"')
            .replace('"R_0_1"','"R_Small_0_1"').replace('"R_1_1"','"R_Small_1_1"'))
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    fp.SetReference('R91');fp.Reference().SetVisible(False)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    court_face=pcbnew.B_CrtYd if back else pcbnew.F_CrtYd
    for item in list(fp.GraphicalItems()):
        if item.GetLayer()==court_face:fp.Remove(item)
    origin=fp.GetPosition();x,y=origin
    vertices=[(x-2000000,y-1500000),(x+2000000,y-1500000),
              (x+2000000,y+1500000),(x-2000000,y+1500000)]
    for a,z in zip(vertices,vertices[1:]+vertices[:1]):
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(court_face);line.SetWidth(50000)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));fp.Add(line)
    fp.BuildCourtyardCaches();chain=fp.GetCourtyard(face).COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    group=pcbnew.PCB_GROUP(b);group.SetName(maps.PREFIX+fp.GetReference());b.Add(group);group.AddItem(fp)
    ink=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    rules=maps._cardinal_rules(source,b);settings=b.GetDesignSettings()
    h=max(800000,round(rules['silk_height']*1e6),settings.m_MinSilkTextHeight)
    stroke=max(120000,round(rules['silk']*1e6),settings.m_MinSilkTextThickness)
    text=pcbnew.PCB_TEXT(b);text.SetText(fp.GetReference());text.SetLayer(ink)
    text.SetMirrored(not back);text.SetTextSize(pcbnew.VECTOR2I(h,h));text.SetTextThickness(stroke)
    text.SetTextPos(origin);text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);group.AddItem(text)
    for a,z in zip(vertices,vertices[1:]+vertices[:1]):
        line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(ink)
        line.SetWidth(stroke);line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z))
        b.Add(line);group.AddItem(line)
    group.SetLocked(True);fp.SetLocked(False)
    # Both real native lands are connected, unlike the detached producer.
    for p in fp.Pads():
        dx,dy=p.GetPosition()-origin
        direction=pcbnew.VECTOR2I((1500000 if dx>0 else -1500000)if dx else 0,
            (1500000 if dy>0 else -1500000)if dy else 0)
        trace(b,p.GetNet(),p.GetPosition(),p.GetPosition()+direction,face)
        if p.GetNumber()=='1':
            v=pcbnew.PCB_VIA(b);v.SetNet(p.GetNet());v.SetPosition(p.GetPosition()+direction)
            v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(0,2);b.Add(v)
    field._save_field_snapshot(b,source)
    return source,root,owner,force._uid(group)


def build(tmp_path,**kwargs):
    source,root,owner,group=fixture(tmp_path,**kwargs)
    proof=maps.inspect(source,owner_uuid=owner,group_uuid=group)
    target=force._copy_family(source,tmp_path/'child')
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    old={p.GetNumber():tuple(p.GetPosition())for p in fp.Pads()}
    # Translate along the local horizontal axis so the two contact tails
    # remain on distinct parallel centerlines for every saved orientation.
    delta=(0,1000000)if kwargs.get('quarter',0)%2==0 else(1000000,0)
    maps.transform_many(b,[(proof,delta)],maximum_translation_mm=6.)
    for p in fp.Pads():
        trace(b,p.GetNet(),p.GetPosition(),pcbnew.VECTOR2I(*old[p.GetNumber()]),
            next(iter(p.GetLayerSet().CuStack())))
    field._save_field_snapshot(b,target)
    return source,target,root,owner,group


def receive(source,target,root,owner,group,**kwargs):
    args=dict(selected_footprint_uuids=[owner],reference_group_uuids=[group],board_hint=str(root),
        max_shift_mm=6.,allow_source_ordinary_resistor_reference_maps=True)
    args.update(kwargs);return op.receive(source,target,**args)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_saved_connected_renamed_resistor_with_exact_map(tmp_path,quarter,back):
    source,target,root,owner,group=build(tmp_path,quarter=quarter,back=back)
    original=source.read_bytes();family=force._family(source,str(root))
    r=receive(source,target,root,owner,group)
    assert r['ok']and r['complete'],r
    assert r['source_ordinary_resistor_witness']['mpn']=='0402WGF1003TCE'
    assert r['source_ordinary_resistor_translation_only']
    assert r['all_source_tracks_arcs_and_barrels_retained_exactly']
    assert r['all_original_terminal_and_copper_partitions_preserved']
    assert r['all_source_reference_group_memberships_and_locks_preserved']
    assert r['no_source_ground_or_signal_barrel_motion_authorized']
    assert len(r['source_ordinary_resistor_contact_restoration'])==2
    assert {c['net']for c in r['source_ordinary_resistor_contact_restoration']}=={'/ALPHA','/BETA'}
    assert not r['routing_admitted']and not r['release_authority']
    assert original==source.read_bytes()and family==force._family(source,str(root))


def test_real_R_small_and_blank_native_pin_annotations(tmp_path):
    source,target,root,owner,group=build(tmp_path,small=True)
    b=pcbnew.LoadBoard(str(source))
    assert all(not p.GetPinType()for f in b.GetFootprints()for p in f.Pads())
    assert receive(source,target,root,owner,group)['ok']


@pytest.mark.parametrize('value',[False,0,1,0.,1.,None,'true',[],{}])
def test_default_and_nonboolean_flag_do_not_authorize_group(tmp_path,value):
    source,target,root,owner,group=build(tmp_path)
    r=receive(source,target,root,owner,group,allow_source_ordinary_resistor_reference_maps=value)
    assert not r['ok']and r['errors'],r
    if value is False:
        omitted=op.receive(source,target,selected_footprint_uuids=[owner],reference_group_uuids=[group],
            board_hint=str(root),max_shift_mm=6.)
        assert omitted['errors']==r['errors']


@pytest.mark.parametrize('extra',[
    {'allow_source_ground_barrel_motion':True},{'allow_field_reflow':True},
    {'allow_endpoint_neckdown_additions':True},{'allow_reoriented_pivot_contacts':True},
    {'allow_retained_capacitor_supply_additions':True},{'selected_pivot_pad_uuids':{}},
    {'source_ground_barrel_seats':[{}]},{'max_shift_mm':6.000001},
    {'reference_group_uuids':[]},{'reference_group_uuids':['unknown']},
    {'selected_footprint_uuids':[]},{'selected_footprint_uuids':['unknown']}])
def test_narrow_optin_has_no_other_motion_or_contact_policy(tmp_path,extra):
    source,target,root,owner,group=build(tmp_path)
    r=receive(source,target,root,owner,group,**extra)
    assert not r['ok']and r['errors'],r


@pytest.mark.parametrize('fault',['source_pin','source_mpn','source_value','source_package','source_symbol',
    'source_ground','source_power','source_pair','source_clock','source_measurement',
    'dnp','locked','tht','same_net','duplicate_pin','extra_pad','copper_art'])
def test_only_fresh_canonical_two_pin_ordinary_Source_is_authority(tmp_path,fault):
    source,target,root,owner,group=build(tmp_path)
    if fault.startswith('source_')and fault not in ('source_ground','source_power','source_pair','source_clock','source_measurement'):
        substitutions={'source_pin':('(pin passive line','(pin power_in line'),
            'source_mpn':('0402WGF1003TCE','OTHER'),'source_value':('"100k"','"200k"'),
            'source_package':('fixture:R_0402','fixture:OTHER'),'source_symbol':('fixture:R"','fixture:C"')}
        a,z=substitutions[fault];root.write_text(root.read_text().replace(a,z,1))
    else:
        b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));pads=list(fp.Pads());p=pads[0]
        if fault.startswith('source_'):
            name={'source_ground':'GND','source_power':'+3V3','source_pair':'/USB_DP',
                'source_clock':'/CLOCK','source_measurement':'/SENSEP1_HI'}[fault]
            old_code=p.GetNetCode();net=pcbnew.NETINFO_ITEM(b,name);b.Add(net);p.SetNet(net)
            for t in b.GetTracks():
                if t.GetNetCode()==old_code:t.SetNet(net)
        elif fault=='dnp':fp.SetDNP(True)
        elif fault=='locked':fp.SetLocked(True)
        elif fault=='tht':
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetLayerSet(pcbnew.PAD.PTHMask())
        elif fault=='same_net':
            old_code=pads[1].GetNetCode();pads[1].SetNet(pads[0].GetNet())
            for t in b.GetTracks():
                if t.GetNetCode()==old_code:t.SetNet(pads[0].GetNet())
        elif fault=='duplicate_pin':pads[1].SetNumber(pads[0].GetNumber())
        elif fault=='extra_pad':
            p=pcbnew.PAD(fp);p.SetNumber('3');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetSize(pcbnew.VECTOR2I_MM(.5,.6));p.SetLayerSet(pcbnew.PAD.SMDMask())
            p.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(2,0));fp.Add(p)
        elif fault=='copper_art':
            line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(0)
            line.SetStart(fp.GetPosition());line.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I_MM(1,0));fp.Add(line)
        field._save_field_snapshot(b,source)
    r=receive(source,target,root,owner,group)
    assert not r['ok']and r['errors'],r


@pytest.mark.parametrize('fault',['zero','rotation','flip','far','part','pad','copper_cut','barrel',
    'source_barrel_motion','group_name','group_unlock','member','ink','metadata','sidecar','missing_contacts',
    'unrelated_net','disconnected_same_net','too_many_contacts','too_long_contacts'])
def test_saved_child_never_owns_parts_group_copper_or_pose_scope(tmp_path,fault):
    source,target,root,owner,group=build(tmp_path)
    b=pcbnew.LoadBoard(str(target));fp=next(iter(b.GetFootprints()));g=next(iter(b.Groups()))
    if fault=='zero':
        original=pcbnew.LoadBoard(str(source));fp.SetPosition(next(iter(original.GetFootprints())).GetPosition())
    elif fault=='rotation':fp.SetOrientationDegrees(fp.GetOrientationDegrees()+90)
    elif fault=='flip':fp.Flip(fp.GetPosition(),False)
    elif fault=='far':fp.Move(pcbnew.VECTOR2I_MM(7,0))
    elif fault=='part':fp.SetField('MPN','OTHER')
    elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    elif fault=='copper_cut':
        original=pcbnew.LoadBoard(str(source));old={force._uid(t)for t in original.GetTracks()}
        from cec_native_items import discard_items
        discard_items(b,[next(t for t in b.GetTracks()if force._uid(t)in old)])
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetNet(next(iter(fp.Pads())).GetNet());v.SetPosition(fp.GetPosition())
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(0,2);b.Add(v)
        # An added isolated barrel cannot be excused by ordinary pose scope.
    elif fault=='source_barrel_motion':
        next(t for t in b.GetTracks()if t.GetClass()=='PCB_VIA').Move(pcbnew.VECTOR2I(1,0))
    elif fault in ('unrelated_net','disconnected_same_net','too_many_contacts','too_long_contacts'):
        pad=next(iter(fp.Pads()));net=pad.GetNet()
        if fault=='unrelated_net':
            net=pcbnew.NETINFO_ITEM(b,'/UNRELATED');b.Add(net)
        if fault=='too_many_contacts':
            for i in range(17):
                trace(b,net,pad.GetPosition(),pad.GetPosition()+pcbnew.VECTOR2I(1000+i,0),0)
        else:
            a=pcbnew.VECTOR2I_MM(20,20)if fault=='disconnected_same_net'else pad.GetPosition()
            z=a+pcbnew.VECTOR2I_MM(33 if fault=='too_long_contacts'else 1,0)
            trace(b,net,a,z,0)
    elif fault=='group_name':g.SetName('FORGED')
    elif fault=='group_unlock':g.SetLocked(False)
    elif fault=='member':g.RemoveItem(next(i for i in g.GetItems()if i.GetClass()=='PCB_SHAPE'))
    elif fault=='ink':next(i for i in g.GetItems()if i.GetClass()=='PCB_TEXT').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='metadata':props=b.GetProperties();props['FORGED']='yes';b.SetProperties(props)
    elif fault=='missing_contacts':
        original=pcbnew.LoadBoard(str(source));old={force._uid(t)for t in original.GetTracks()}
        from cec_native_items import discard_items
        discard_items(b,[t for t in b.GetTracks()if force._uid(t)not in old])
    if fault=='sidecar':target.with_suffix('.kicad_pro').write_text(json.dumps({'forged':True}))
    else:field._save_field_snapshot(b,target)
    r=receive(source,target,root,owner,group)
    assert not r['ok']and r['errors'],r


def test_receiver_does_not_reuse_prior_fresh_pin_roles(tmp_path):
    source,target,root,owner,group=build(tmp_path)
    assert receive(source,target,root,owner,group)['ok']
    root.write_text(root.read_text().replace('(pin passive line','(pin input line',1))
    assert not receive(source,target,root,owner,group)['ok']


def test_native_pad_lock_refuses_before_map_or_canonical_proof(tmp_path,monkeypatch):
    # KiCad's writer does not serialize a PAD's transient lock. Exercise the
    # loaded-native validation directly, not a saved fixture that lost it.
    source,target,root,owner,group=build(tmp_path)
    load=pcbnew.LoadBoard;b=load(str(source));p=next(iter(next(iter(b.GetFootprints())).Pads()))
    p.SetLocked(True);assert p.IsLocked()
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda path:b if Path(path)==source else load(path))
    r=receive(source,target,root,owner,group)
    assert not r['ok']and 'two_surface_pin_ordinary_resistor' in r['errors'][0],r


@pytest.mark.parametrize('changed',['schematic','exporter'])
def test_canonical_inputs_are_live_after_native_reconstruction(tmp_path,monkeypatch,changed):
    import cec_native_partition_pair as partitions
    source,target,root,owner,group=build(tmp_path)
    compare=partitions.compare;digest=force._hash;finished=[]
    def after_native(*args,**kwargs):
        result=compare(*args,**kwargs)
        assert not result['demoted_parts']
        if changed=='schematic':root.write_text(root.read_text().replace('"100k"','"200k"',1))
        finished.append(True);return result
    def changed_exporter(path):
        if changed=='exporter'and finished and Path(path).resolve()==Path('/usr/bin/kicad-cli').resolve():
            return '0'*64
        return digest(path)
    monkeypatch.setattr(partitions,'compare',after_native)
    monkeypatch.setattr(force,'_hash',changed_exporter)
    r=receive(source,target,root,owner,group)
    assert finished and not r['ok']and 'canonical_Source_or_exporter_changed' in r['errors'][0],r
