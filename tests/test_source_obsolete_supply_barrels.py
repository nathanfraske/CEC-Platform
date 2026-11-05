"""Native Source geometry; only the explicit current/canonical catalog is mocked."""
import copy
import math
from pathlib import Path
from unittest import mock

import pcbnew
import pytest
import wx
import cec_source_obsolete_supply_barrels as op
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track

_quiet = wx.LogNull()


def fixture(tmp_path, *, angle=0, mirror=False, face=pcbnew.F_Cu, grouped=True):
    def xy(point):
        x, y = point[0]-8, point[1]-10
        if mirror: x = -x
        a = math.radians(angle)
        return round(12+x*math.cos(a)-y*math.sin(a),6), round(12+x*math.sin(a)+y*math.cos(a),6)
    net='/RENAMED/EXPLICIT-SUPPLY'
    b=_board([(*xy(p),net) for p in ((5,10),(11,10))],edge=(0,0,26,26));b.SetCopperLayerCount(6)
    for i,fp in enumerate(b.GetFootprints()):
        fp.SetReference('SELECTED_'+str(i));fp.SetValue('100nF');fp.SetLayer(face)
        p=next(iter(fp.Pads()));p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(1.2,1.2))
        layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
    t=track(b,net,xy((5,10)),xy((11,10)),width=.2,layer=6)
    vias=[]
    for point in ((5,10),(11,10),(20,20)):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*xy(point)));v.SetNetCode(t.GetNetCode())
        v.SetWidth(350000);v.SetDrill(250000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetLocked(grouped);b.Add(v);vias.append(v)
    if grouped:
        g=pcbnew.PCB_GROUP(b);g.SetName(op.fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(g)
        for v in vias:g.AddItem(v)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source))
    contract=dict(net=net,role='all_terminal_conservative_aggregate',source_sink_inferred=False,
        branch_sharing_assumed=False,current_authority=dict(amps=.1,geometry_margin=1.25,margin_included=False,source='board_design_basis'),
        required_by_layer_mm={'F.Cu':.2,'In2.Cu':.5,'In3.Cu':.5,'B.Cu':.2},routing_layers=('F.Cu','In2.Cu','In3.Cu','B.Cu'))
    return source,b,force._uid(t),[force._uid(v)for v in vias],{net:contract}


def source_context(board,contracts,**kwargs):
    source=Path(board.GetFileName())
    return dict(contracts=copy.deepcopy(contracts),pads={force._uid(p):dict(ref=f.GetReference(),pin=p.GetNumber(),net=p.GetNetname(),
        role='manufacturer_supply_pin' if i==0 else 'value_qualified_grounded_ceramic_supply_terminal')
        for i,f in enumerate(board.GetFootprints())for p in f.Pads()},
        source_bindings=dict(hierarchy={str(source):force._hash(source)},
            export=dict(exporter=str(Path(__file__).resolve()),exporter_sha256=force._hash(Path(__file__)))))


def run(b,source,contracts,cut,context=source_context,**kwargs):
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=dict(contracts=copy.deepcopy(contracts))), \
         mock.patch.object(op.canonical,'prepare',side_effect=context):
        return op.plan(b,source,contracts,cut,board_hint='synthetic-explicit-source',**kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_rotated_renamed_native_source_derives_all_and_only_endpoint_barrels(tmp_path,angle,mirror,face):
    source,b,cut,vias,contracts=fixture(tmp_path,angle=angle,mirror=mirror,face=face)
    raw=source.read_bytes();binding=op._native_binding(b)
    q=run(b,source,contracts,[cut])
    assert q['complete'] and q['retired_via_uuids']==sorted(vias[:2])
    assert all(r['contact_face']==face and r['whole_disk_smd_cover'] for r in q['rows'])
    assert all(r['source_retired_inner_contact_uuids']==[cut]for r in q['rows'])
    group=q['source_factory_groups'][0]
    assert group['source_member_uuids']==sorted(vias)
    assert q['factory_group_member_retirements']=={group['uuid']:sorted(vias[:2])}
    assert not any(q[k]for k in('new_capacity_credited','barrel_ampacity_qualified','current_qualified','process_qualified','routing_admitted','release_authority'))
    assert source.read_bytes()==raw and op._native_binding(b)==binding


def test_unlocked_ungrouped_barrels_have_no_factory_group_permission(tmp_path):
    source,b,cut,vias,c=fixture(tmp_path,grouped=False)
    q=run(b,source,c,[cut]);assert q['retired_via_uuids']==sorted(vias[:2])
    assert q['factory_group_member_retirements']=={} and q['source_local_factory_group_uuids']==[]


@pytest.mark.parametrize('bad',['outer','plane','rated_width','zero_width','missing_cut','duplicate_cut','empty_cut','wrong_net_contract',
    'aggregate_role','inferred_source','sharing','wrong_current','absent_catalog','different_catalog'])
def test_wrong_source_tier_or_contract_never_yields_a_barrel_scope(tmp_path,bad):
    source,b,cut,vias,c=fixture(tmp_path);args=[cut];net=next(iter(c));catalog=None
    t=next(t for t in b.GetTracks()if force._uid(t)==cut)
    if bad=='outer':t.SetLayer(pcbnew.F_Cu)
    elif bad=='plane':t.SetLayer(4)
    elif bad=='rated_width':t.SetWidth(600000)
    elif bad=='zero_width':t.SetWidth(0)
    elif bad=='missing_cut':args=['missing']
    elif bad=='duplicate_cut':args=[cut,cut]
    elif bad=='empty_cut':args=[]
    elif bad=='wrong_net_contract':c={'different':c[net]}
    elif bad=='aggregate_role':c[net]['role']='aggregate_source_sink'
    elif bad=='inferred_source':c[net]['source_sink_inferred']=True
    elif bad=='sharing':c[net]['branch_sharing_assumed']=True
    elif bad=='wrong_current':c[net]['current_authority']['amps']=0
    elif bad=='absent_catalog':catalog={}
    elif bad=='different_catalog':catalog=copy.deepcopy(c);catalog[net]['current_authority']['amps']=.2
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=dict(contracts=c if catalog is None else catalog)), \
         mock.patch.object(op.canonical,'prepare',side_effect=source_context):
        # wrong_current is deliberately a corrupt test catalog; real catalog
        # refuses this before returning a contract. The compiler must too.
        with pytest.raises(ValueError):op.plan(b,source,c,args,board_hint='synthetic-explicit-source')


@pytest.mark.parametrize('bad',['ordinary_role','empty_role','null_role','missing_pad_catalog','stale_ref','stale_net','stale_pin','missing_binding','stale_exporter'])
def test_only_fresh_canonical_supply_terminals_authorize_removal(tmp_path,bad):
    source,b,cut,vias,c=fixture(tmp_path)
    def context(*args,**kwargs):
        q=source_context(*args,**kwargs);uid=next(iter(q['pads']))
        if bad=='ordinary_role':q['pads'][uid]['role']='ordinary'
        elif bad=='empty_role':q['pads'][uid]={}
        elif bad=='null_role':q['pads'][uid]=None
        elif bad=='missing_pad_catalog':q.pop('pads')
        elif bad=='stale_ref':q['pads'][uid]['ref']='impostor'
        elif bad=='stale_net':q['pads'][uid]['net']='other'
        elif bad=='stale_pin':q['pads'][uid]['pin']='99'
        elif bad=='missing_binding':q['source_bindings']={}
        elif bad=='stale_exporter':q['source_bindings']['export']['exporter_sha256']='0'*64
        return q
    with pytest.raises(ValueError):run(b,source,c,[cut],context=context)


def test_missing_roles_retain_all_centered_barrels_without_acceptance_authority(tmp_path):
    source,b,cut,vias,c=fixture(tmp_path);raw=source.read_bytes();native=op._native_binding(b)
    def context(*args,**kwargs):
        q=source_context(*args,**kwargs);q['pads']={};return q
    q=run(b,source,c,[cut],context=context)
    assert q['complete'] and q['retirement_eligibility_only'] and not q['has_retirement_candidates']
    assert q['retired_via_uuids']==[] and q['rows']==[]
    assert q['factory_group_member_retirements']=={} and q['source_local_factory_group_uuids']==[]
    assert {r['uuid']for r in q['retained_endpoint_vias']}==set(vias[:2])
    assert all(r['pad_uuid'] and r['reason']=='no_positive_canonical_supply_role_retained_boundary_still_required'
        for r in q['retained_endpoint_vias'])
    assert q['child_fullwidth_global_drill_aware_graph_still_required']
    assert q['exact_literal_retirement_and_all_partitions_still_required']
    assert not any(q[k]for k in('new_capacity_credited','barrel_ampacity_qualified','current_qualified',
        'process_qualified','routing_admitted','release_authority'))
    assert source.read_bytes()==raw and op._native_binding(b)==native


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_two_supply_barrels_retire_but_centered_divider_and_route_barrels_remain(tmp_path,face):
    source,b,cut,vias,c=fixture(tmp_path,face=face);net=next(iter(c));g=next(iter(b.Groups()))
    divider_pads=[];extra_vias=[];extra_cuts=[]
    for i,point in enumerate(((8,18),(14,18),(18,18))):
        if i<2:
            fp=pcbnew.FOOTPRINT(b);fp.SetReference('UNRELATED_DIVIDER_'+str(i));fp.SetValue('10k');fp.SetLayer(face)
            pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1.2,1.2))
            layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
            pad.SetPosition(pcbnew.VECTOR2I_MM(*point));pad.SetNetCode(next(iter(b.GetTracks())).GetNetCode())
            fp.Add(pad);b.Add(fp);divider_pads.append(force._uid(pad))
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*point));v.SetNetCode(next(iter(b.GetTracks())).GetNetCode())
        v.SetWidth(350000);v.SetDrill(250000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetLocked(True);b.Add(v);g.AddItem(v);extra_vias.append(force._uid(v))
    for a,z in (((8,18),(14,18)),((14,18),(18,18))):
        extra_cuts.append(force._uid(track(b,net,a,z,width=.2,layer=6)))
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b);b=pcbnew.LoadBoard(str(source))
    raw=source.read_bytes();native=op._native_binding(b)
    def context(*args,**kwargs):
        q=source_context(*args,**kwargs)
        for uid in divider_pads:q['pads'].pop(uid)
        for i,uid in enumerate(sorted(q['pads'])):
            q['pads'][uid]['role']='manufacturer_supply_pin' if i==0 else 'value_qualified_grounded_ceramic_supply_terminal'
        return q
    q=run(b,source,c,[cut]+extra_cuts,context=context)
    assert q['retired_via_uuids']==sorted(vias[:2]) and q['has_retirement_candidates']
    assert {r['canonical_supply_terminal']['role']for r in q['rows']}=={
        'manufacturer_supply_pin','value_qualified_grounded_ceramic_supply_terminal'}
    retained={r['uuid']:r for r in q['retained_endpoint_vias']}
    assert set(retained)==set(extra_vias)
    for uid,pad_uid in zip(extra_vias[:2],divider_pads):
        assert retained[uid]['pad_uuid']==pad_uid
        assert retained[uid]['reason']=='no_positive_canonical_supply_role_retained_boundary_still_required'
    assert retained[extra_vias[2]]['reason']=='no_centered_source_smd_supply_land_retained_boundary_still_required'
    assert q['source_factory_groups'][0]['source_member_uuids']==sorted(vias+extra_vias)
    assert q['factory_group_member_retirements']=={force._uid(next(iter(b.Groups()))):sorted(vias[:2])}
    assert source.read_bytes()==raw and op._native_binding(b)==native


@pytest.mark.parametrize('bad',['foreign_contact','extra_surface_track','other_face','other_barrel','uncontained_disk',
    'locked_ungrouped','opaque_group','locked_group','nested_group','mixed_group','second_group','typed_dependency','copper_graphic','unknown_fill'])
def test_source_contact_group_and_lock_uncertainty_refuses_whole_scope(tmp_path,bad):
    source,b,cut,vias,c=fixture(tmp_path);net=next(iter(c))
    v=next(t for t in b.GetTracks()if force._uid(t)==vias[0]);at=v.GetPosition()
    pad=next(p for f in b.GetFootprints()for p in f.Pads()if tuple(p.GetPosition())==tuple(at))
    g=next(iter(b.Groups()))
    if bad=='foreign_contact':
        n=pcbnew.NETINFO_ITEM(b,'/FOREIGN');b.Add(n);f=pcbnew.FOOTPRINT(b);f.SetReference('FOREIGN')
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetPosition(at);p.SetSize(pcbnew.VECTOR2I(350000,350000));p.SetLayerSet(pad.GetLayerSet());p.SetNet(n);f.Add(p);b.Add(f)
    elif bad in('extra_surface_track','other_face'):
        track(b,net,(at.x/1e6,at.y/1e6),(at.x/1e6,at.y/1e6+2),width=.2,layer=pcbnew.B_Cu if bad=='other_face'else pcbnew.F_Cu)
    elif bad=='other_barrel':
        z=v.Duplicate();z.m_Uuid.Clone(pcbnew.KIID());b.Add(z)
    elif bad=='uncontained_disk':pad.SetSize(pcbnew.VECTOR2I(300000,300000))
    elif bad=='offcenter':pad.Move(pcbnew.VECTOR2I(1000,0))
    elif bad=='hole_pad':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    elif bad=='locked_ungrouped':g.RemoveItem(v)
    elif bad=='opaque_group':g.SetName('STRUCTURAL-OWNER')
    elif bad=='locked_group':g.SetLocked(True)
    elif bad=='nested_group':
        outer=pcbnew.PCB_GROUP(b);outer.SetName('outer');b.Add(outer);outer.AddItem(g)
    elif bad=='mixed_group':g.AddItem(track(b,net,(2,2),(3,2),width=.2))
    elif bad=='second_group':
        z=pcbnew.PCB_GROUP(b);z.SetName('other');b.Add(z);z.AddItem(v)
    elif bad=='typed_dependency':
        z=pcbnew.PCB_GROUP(b);z.SetName('TYPED|'+vias[0]);b.Add(z)
        z.AddItem(next(t for t in b.GetTracks()if force._uid(t)==vias[2]))
    elif bad=='copper_graphic':
        z=pcbnew.PCB_SHAPE(b);z.SetShape(pcbnew.SHAPE_T_SEGMENT);z.SetLayer(pcbnew.F_Cu);z.SetWidth(50000)
        z.SetStart(at);z.SetEnd(at+pcbnew.VECTOR2I(0,1000000));b.Add(z)
    elif bad=='unknown_fill':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNetCode(v.GetNetCode());z.Outline().NewOutline()
        for dx,dy in((-1,-1),(1,-1),(1,1),(-1,1)):z.Outline().Append(at.x+dx*1000000,at.y+dy*1000000)
        b.Add(z)
    # This authored negative Source may contain a real foreign-net short.
    # Load its native IO serialization before establishing the pristine
    # baseline; netcode numbering is not the semantic net identity.
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    b=pcbnew.LoadBoard(str(source));before=op._native_binding(b)
    if bad=='foreign_contact':assert any(p.GetNetname()=='/FOREIGN' for f in b.GetFootprints()for p in f.Pads())
    with pytest.raises(ValueError):run(b,source,c,[cut])
    assert before==op._native_binding(b)


@pytest.mark.parametrize('seconds',[0,-1,11,True,float('nan'),float('inf'),1e-12])
def test_finite_original_budget_required(tmp_path,seconds):
    source,b,cut,_,c=fixture(tmp_path)
    with pytest.raises(ValueError):run(b,source,c,[cut],timeout_s=seconds)


def test_missing_or_nonpristine_source_refuses(tmp_path):
    source,b,cut,_,c=fixture(tmp_path)
    with pytest.raises((ValueError,FileNotFoundError)):run(b,tmp_path/'absent.kicad_pcb',c,[cut])
    next(iter(b.GetFootprints())).SetValue('changed')
    with pytest.raises(ValueError,match='pristine'):run(b,source,c,[cut])


@pytest.mark.parametrize('kind',['offcenter','pth','route_only'])
def test_nonterminal_endpoint_vias_remain_real_boundaries_not_retirement_candidates(tmp_path,kind):
    source,b,cut,vias,c=fixture(tmp_path)
    via=next(t for t in b.GetTracks()if force._uid(t)==vias[0])
    pad=next(p for f in b.GetFootprints()for p in f.Pads()if tuple(p.GetPosition())==tuple(via.GetPosition()))
    if kind=='offcenter':pad.Move(pcbnew.VECTOR2I(1000,0))
    elif kind=='pth':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    else:pad.Move(pcbnew.VECTOR2I(2000000,0))
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b);b=pcbnew.LoadBoard(str(source))
    q=run(b,source,c,[cut])
    assert q['retired_via_uuids']==[vias[1]]
    assert q['retained_endpoint_vias']==[dict(uuid=vias[0],net=next(iter(c)),
        reason='no_centered_source_smd_supply_land_retained_boundary_still_required')]


def test_source_epoch_changed_during_canonical_compile_refuses(tmp_path):
    source,b,cut,_,c=fixture(tmp_path)
    def context(*args,**kwargs):
        q=source_context(*args,**kwargs);next(iter(b.GetFootprints())).SetValue('changed');return q
    with pytest.raises(ValueError,match='source_family_native_or_code_changed'):run(b,source,c,[cut],context=context)
