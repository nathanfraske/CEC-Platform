"""Native complete Source-class Ground spur ownership and saved receiving."""
import copy,json,math
import pcbnew
import pytest
import cec_source_class_ground_land_root_spur as draft
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,turn=0,mirror=False,back=False):
    b=_board([],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    for n in('GND','OTHER'):b.Add(pcbnew.NETINFO_ITEM(b,n))
    def xy(point):
        x,y=point[0]-20,point[1]-20
        if mirror:x=-x
        angle=turn*math.pi/2
        return round(20+x*math.cos(angle)-y*math.sin(angle),6),round(20+x*math.sin(angle)+y*math.cos(angle),6)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    track(b,'OTHER',(2,2),(3,2),width=.5,layer=face)
    def land(ref,point):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*xy(point)))
        fp.SetLayer(face);fp.SetValue('retained');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('2');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(1.2,1.2))
        p.SetDrillSize(pcbnew.VECTOR2I(0,0));layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
        p.SetNet(b.FindNet('GND'));fp.Add(p);p.SetPosition(fp.GetPosition());return p
    root=land('RENAMED_ROOT',(14,20));known=land('KNOWN_RETURN',(10.5,20))
    retained=track(b,'GND',xy((10,20)),xy((14,20)),width=.5,layer=face)
    body=track(b,'GND',xy((14,20)),xy((20,20)),width=.5,layer=face)
    nub=track(b,'GND',xy((20,20)),xy((20.011,20)),width=.5,layer=face)
    tip=track(b,'GND',xy((20.011,20)),xy((20.019,20.008)),width=.5,layer=face)
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I_MM(*xy((10,20))))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via)
    for layer in(pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(layer);z.SetNet(b.FindNet('GND'));z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.Outline().NewOutline()
        for x,y in((1,1),(39,1),(39,39),(1,39)):z.Outline().Append(round(x*1e6),round(y*1e6))
        b.Add(z)
    additive._ground_refill(b);source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    # Real saved class, never an in-memory borrowed width.
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        {'name':'Default','track_width':.5,'clearance':.2,'via_diameter':.6,'via_drill':.3}]}}))
    return source,pcbnew.LoadBoard(str(source)),dict(seed=force._uid(tip),nub=force._uid(nub),
        body=force._uid(body),root=force._uid(root),retained=force._uid(retained),via=force._uid(via)),xy


def save_child(source,b,q,tmp_path):
    draft.subtract(b,q);child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child);return child


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('back',[False,True])
def test_real_native_whole_chain_and_saved_return_proof(tmp_path,turn,mirror,back):
    source,b,ids,xy=fixture(tmp_path,turn,mirror,back);raw=source.read_bytes()
    q=draft.plan(b,source,ids['seed'])
    assert q['retired_track_uuids']==[ids['seed'],ids['nub'],ids['body']]
    assert q['retained_root_pad_uuid']==ids['root']and q['retained_root_track_uuids']==[ids['retained']]
    assert len(q['retained_actual_reference_contacts'])==2
    child=save_child(source,b,q,tmp_path)
    proof=draft.receive(source,child,q,board_hint='synthetic',timeout_s=10.)
    assert proof['ok']and proof['complete'],proof
    assert proof['all_surviving_native_partitions_preserved']
    assert proof['proved_short_ground_returns_preserved']
    assert proof['scope']=='source_class_complete_ground_land_root_spur'
    assert not proof['current_qualified']and not proof['release_authority']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['third_pad','foreign_pad','branch','via_contact','zone_contact',
    'unfilled','one_reference_only','missing_retained','root_moved','grouped','locked','mixed_width',
    'wrong_net','noncanonical','too_long','class_changed','missing_project'])
def test_actual_source_boundaries_refuse_unproved_cuts(tmp_path,fault):
    source,b,ids,xy=fixture(tmp_path);items={force._uid(t):t for t in b.GetTracks()}
    if fault in('third_pad','foreign_pad'):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('THIRD');b.Add(fp);p=pcbnew.PAD(fp)
        p.SetNumber('1');p.SetNet(b.FindNet('OTHER'if fault=='foreign_pad'else'GND'))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.7,.7))
        p.SetPosition(pcbnew.VECTOR2I_MM(17,20));fp.Add(p)
    elif fault=='branch':track(b,'GND',(17,20),(17,22),width=.5)
    elif fault=='via_contact':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(17,20));v.SetNet(b.FindNet('GND'))
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='zone_contact':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNet(b.FindNet('GND'));z.Outline().NewOutline()
        for x,y in((16,19),(18,19),(18,21),(16,21)):z.Outline().Append(round(x*1e6),round(y*1e6))
        b.Add(z);additive._ground_refill(b)
    elif fault=='unfilled':next(iter(b.Zones())).UnFill()
    elif fault=='one_reference_only':b.Remove(next(iter(b.Zones())))
    elif fault=='missing_retained':discard_items(b,[items[ids['retained']]])
    elif fault=='root_moved':b.FindFootprintByReference('RENAMED_ROOT').Move(pcbnew.VECTOR2I_MM(0,3))
    elif fault=='grouped':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(items[ids['body']])
    elif fault=='locked':items[ids['body']].SetLocked(True)
    elif fault=='mixed_width':items[ids['body']].SetWidth(600000)
    elif fault=='wrong_net':items[ids['body']].SetNet(b.FindNet('OTHER'))
    elif fault=='noncanonical':items[ids['seed']].SetEnd(pcbnew.VECTOR2I_MM(20.019,20.009))
    elif fault=='too_long':items[ids['seed']].SetEnd(pcbnew.VECTOR2I_MM(35,34.989))
    if fault=='wrong_net':pcbnew.SaveBoard(str(source),b)
    else:field._save_field_snapshot(b,source)
    if fault=='class_changed':
        p=json.loads(source.with_suffix('.kicad_pro').read_text());p['net_settings']['classes'][0]['track_width']=.6
        source.with_suffix('.kicad_pro').write_text(json.dumps(p))
    elif fault=='missing_project':source.with_suffix('.kicad_pro').unlink()
    with pytest.raises(ValueError):draft.plan(pcbnew.LoadBoard(str(source)),source,ids['seed'])


def test_exact_locked_cut_scope_only(tmp_path):
    source,b,ids,xy=fixture(tmp_path)
    for t in b.GetTracks():
        if force._uid(t)in(ids['seed'],ids['nub'],ids['body']):t.SetLocked(True)
    field._save_field_snapshot(b,source);allow=[ids['seed'],ids['nub'],ids['body']]
    q=draft.plan(b,source,ids['seed'],allow_locked_track_uuids=allow)
    with pytest.raises(ValueError):draft.plan(b,source,ids['seed'],allow_locked_track_uuids=allow+[ids['retained']])
    child=save_child(source,b,q,tmp_path);assert draft.receive(source,child,q,board_hint='synthetic')['ok']


@pytest.mark.parametrize('fault',['forged_plan','extra_cut','addition','root','sidecar','lost_return'])
def test_saved_independent_replay_refuses_mutations(tmp_path,fault):
    source,b,ids,xy=fixture(tmp_path);q=draft.plan(b,source,ids['seed']);child=save_child(source,b,q,tmp_path)
    if fault=='forged_plan':q=copy.deepcopy(q);q['retired_track_uuids'].pop()
    elif fault=='sidecar':
        p=json.loads(child.with_suffix('.kicad_pro').read_text());p['new_policy']='forged';child.with_suffix('.kicad_pro').write_text(json.dumps(p))
    else:
        b=pcbnew.LoadBoard(str(child))
        if fault=='extra_cut':discard_items(b,[next(t for t in b.GetTracks()if force._uid(t)==ids['retained'])])
        elif fault=='addition':track(b,'GND',(25,25),(26,25),width=.5)
        elif fault=='root':b.FindFootprintByReference('RENAMED_ROOT').SetValue('changed')
        else:
            v=next(t for t in b.GetTracks()if force._uid(t)==ids['via']);v.SetPosition(pcbnew.VECTOR2I_MM(9,20))
        additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=draft.receive(source,child,q,board_hint='synthetic');assert not result['ok']and result['errors']


def test_known_short_return_worsening_refuses_even_when_native_partition_survives(tmp_path):
    source,b,ids,xy=fixture(tmp_path)
    track(b,'GND',(10,20),(10,21),width=.5)
    track(b,'GND',(10,21),(10,22),width=.5)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    q=draft.plan(b,source,ids['seed']);child=save_child(source,b,q,tmp_path)
    after=pcbnew.LoadBoard(str(child));via=next(t for t in after.GetTracks()if force._uid(t)==ids['via'])
    via.SetPosition(pcbnew.VECTOR2I_MM(10,21));additive._ground_refill(after);field._save_field_snapshot(after,child)
    proof=draft.receive(source,child,q,board_hint='synthetic')
    assert not proof['ok']and any('worsened_proved_local_return'in e for e in proof['errors']),proof


@pytest.mark.parametrize('placement',['board','footprint'])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_unsupported_copper_graphics_never_supply_or_hide_native_connectivity(tmp_path,placement,face):
    source,b,ids,xy=fixture(tmp_path)
    parent=b if placement=='board'else b.FindFootprintByReference('RENAMED_ROOT')
    graphic=pcbnew.PCB_SHAPE(parent);graphic.SetShape(pcbnew.SHAPE_T_SEGMENT);graphic.SetLayer(face)
    graphic.SetStart(pcbnew.VECTOR2I_MM(25,25));graphic.SetEnd(pcbnew.VECTOR2I_MM(26,25));graphic.SetWidth(500000)
    parent.Add(graphic);field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='unsupported_copper_graphics'):
        draft.plan(pcbnew.LoadBoard(str(source)),source,ids['seed'])


@pytest.mark.parametrize('fault',['duplicate_track','cut_pad_alias','root_pad_alias'])
def test_source_identity_aliases_cannot_disappear_inside_whole_cut(tmp_path,fault):
    source,b,ids,xy=fixture(tmp_path)
    if fault=='duplicate_track':
        other=next(t for t in b.GetTracks()if t.GetNetname()=='OTHER');old=force._uid(other);new=ids['body']
    elif fault=='cut_pad_alias':old=force._uid(b.FindFootprintByReference('KNOWN_RETURN').FindPadByNumber('2'));new=ids['body']
    else:old=force._uid(b.FindFootprintByReference('KNOWN_RETURN').FindPadByNumber('2'));new=ids['root']
    text=source.read_text();assert text.count(old)==1
    source.write_text(text.replace(old,new))
    with pytest.raises(ValueError):draft.plan(pcbnew.LoadBoard(str(source)),source,ids['seed'])


@pytest.mark.parametrize('field_kind',['reference','value','custom'])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_copper_footprint_fields_are_not_ignored_connectivity(tmp_path,field_kind,face):
    source,b,ids,xy=fixture(tmp_path);fp=b.FindFootprintByReference('RENAMED_ROOT')
    if field_kind=='reference':item=fp.Reference()
    elif field_kind=='value':item=fp.Value()
    else:
        fp.SetField('UNSUPPORTED_COPPER','literal')
        item=next(f for f in fp.GetFields()if f.GetName()=='UNSUPPORTED_COPPER')
    item.SetLayer(face);item.SetVisible(True);field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='unsupported_copper_graphics'):
        draft.plan(pcbnew.LoadBoard(str(source)),source,ids['seed'])
