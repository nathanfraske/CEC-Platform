"""Compound old barrel/stem retirement must preserve real source boundaries."""
import pcbnew
import pytest
import cec_contained_one_face_barrel_retirement as op
import cec_contained_one_face_barrel_stage as stage
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_contained_one_face_barrel_retirement import fixture as base
from test_field_proposals import track
from test_contained_one_face_barrel_stage import reporting_build


def fixture(tmp_path, face=pcbnew.F_Cu, angle=0, mirror=False):
    source,b,v,left,net=base(tmp_path,face,angle,mirror)
    start,end=tuple(left.GetStart()),tuple(left.GetEnd());root=tuple((x+y)//2 for x,y in zip(start,end))
    dx,dy=((end[0]-start[0])//40,(end[1]-start[1])//40)
    axis=(root[0]+dx-dy,root[1]+dy+dx);v.SetPosition(pcbnew.VECTOR2I(*axis))
    right=left.Duplicate();right.m_Uuid.Clone(pcbnew.KIID());right.SetStart(pcbnew.VECTOR2I(*root));b.Add(right)
    left.SetEnd(pcbnew.VECTOR2I(*root))
    leaf=left.Duplicate();leaf.m_Uuid.Clone(pcbnew.KIID());leaf.SetStart(pcbnew.VECTOR2I(*root))
    leaf.SetEnd(v.GetPosition());leaf.SetLocked(True);b.Add(leaf)
    field._save_field_snapshot(b,source)
    return source,b,v,leaf,left,right,net


def proposal(board,via,leaf):
    uid,sid=force._uid(via),force._uid(leaf)
    return op.plan(board,[uid],allow_locked_via_uuids=[uid],leaf_track_uuids=[sid],
        allow_locked_leaf_track_uuids=[sid])


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_compound_native_scope_has_one_full_width_root_and_surviving_barrel_cover(tmp_path,face,angle,mirror):
    source,b,v,leaf,left,right,net=fixture(tmp_path,face,angle,mirror)
    original=field._field_snapshot_inventory(b);p=proposal(b,v,leaf)
    assert op.attached_short_leaf_uuids(b,[force._uid(v)])==[force._uid(leaf)]
    assert p['leaf_track_uuids']==[force._uid(leaf)]
    assert p['source_leaf_rows'][0]['retained_root_track_uuids']==sorted([force._uid(left),force._uid(right)])
    assert force._uid(leaf) not in p['rows'][0]['retained_native_whole_disk_covers']
    assert original==field._field_snapshot_inventory(b)
    assert not p['current_qualified'] and not p['release_authority']


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
def test_exact_saved_compound_cut_keeps_every_other_copper_body_and_terminal(tmp_path,face):
    source,b,v,leaf,*_=fixture(tmp_path,face);p=proposal(b,v,leaf);original=source.read_bytes()
    op.subtract(b,p);child=force._copy_family(source,tmp_path/'received')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    r=op.receive(source,child,p,board_hint='unclassified-test')
    assert r['ok'] and r['complete'],r
    assert r['retired_leaf_track_uuids']==p['leaf_track_uuids'] and r['surviving_native_partitions_preserved']
    assert r['current_debt_receiving']['ok'] and r['absolute_native_cut_preservation']['same_evidence']
    assert source.read_bytes()==original and not r['current_qualified']


@pytest.mark.parametrize('bad',['too_long','too_wide','wrong_net','wrong_face','not_exact_axis',
    'pad_contact','zone_outline','interior_branch','narrow_root','source_lock','unowned_group',
    'typed_reference','second_stem','unassigned_copper'])
def test_via_warning_does_not_authorize_live_branch_or_protected_source_stem(tmp_path,bad):
    source,b,v,leaf,left,right,net=fixture(tmp_path)
    sid=force._uid(leaf);kwargs=dict(allow_locked_via_uuids=[force._uid(v)],leaf_track_uuids=[sid],
        allow_locked_leaf_track_uuids=[sid])
    if bad=='too_long':leaf.SetStart(leaf.GetStart()+pcbnew.VECTOR2I_MM(-2,0))
    elif bad=='too_wide':leaf.SetWidth(1000001)
    elif bad=='wrong_net':
        foreign=pcbnew.NETINFO_ITEM(b,'/DIFFERENT-RAIL');b.Add(foreign);leaf.SetNet(foreign)
    elif bad=='wrong_face':leaf.SetLayer(pcbnew.B_Cu)
    elif bad=='not_exact_axis':leaf.SetEnd(leaf.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif bad=='pad_contact':
        pad=next(p for f in b.GetFootprints() for p in f.Pads());pad.SetPosition(v.GetPosition())
    elif bad=='zone_outline':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNetCode(v.GetNetCode());z.Outline().NewOutline()
        for x,y in ((8,8),(10,8),(10,10),(8,10)):z.Outline().Append(int(x*1e6),int(y*1e6))
        b.Add(z)
    elif bad=='interior_branch':track(b,net,(9.05,9.05),(9.05,11),width=.2)
    elif bad=='narrow_root':left.SetWidth(800000);right.SetWidth(800000)
    elif bad=='source_lock':kwargs['allow_locked_leaf_track_uuids']=[]
    elif bad=='unowned_group':
        g=pcbnew.PCB_GROUP(b);g.SetName('different-source-owner');b.Add(g);g.AddItem(leaf)
        kwargs['allow_grouped_leaf_track_uuids']=[sid]
    elif bad=='typed_reference':
        g=pcbnew.PCB_GROUP(b);g.SetName('SOURCE_TYPED|'+sid+'|boundary');b.Add(g)
    elif bad=='second_stem':
        second=leaf.Duplicate();second.m_Uuid.Clone(pcbnew.KIID());b.Add(second)
        kwargs['leaf_track_uuids'].append(force._uid(second));kwargs['allow_locked_leaf_track_uuids'].append(force._uid(second))
    else:
        g=pcbnew.PCB_SHAPE(b);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(pcbnew.F_Cu)
        g.SetStart(leaf.GetStart());g.SetEnd(leaf.GetEnd());g.SetWidth(100000);b.Add(g)
    original=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,[force._uid(v)],**kwargs)
    assert original==field._field_snapshot_inventory(b)


def test_a_forged_leaf_root_or_retained_cover_is_rederived_before_any_deletion(tmp_path):
    source,b,v,leaf,*_=fixture(tmp_path);p=proposal(b,v,leaf)
    p['source_leaf_rows'][0]['retained_root_track_uuids']=['nonexistent-source-authority']
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='exact_source_replan'):op.subtract(b,p)
    assert before==field._field_snapshot_inventory(b)


def test_coupled_pair_member_needs_its_own_receiver_even_if_geometrically_a_leaf(tmp_path):
    source,b,v,leaf,*rest=fixture(tmp_path);old=v.GetNetCode()
    positive=pcbnew.NETINFO_ITEM(b,'/RENAMED/PACKET_P');negative=pcbnew.NETINFO_ITEM(b,'/RENAMED/PACKET_N')
    b.Add(positive);b.Add(negative)
    for item in [*b.GetTracks(),*(p for f in b.GetFootprints() for p in f.Pads())]:
        if item.GetNetCode()==old:item.SetNet(positive)
    with pytest.raises(ValueError,match='coupled_pair_requires'):proposal(b,v,leaf)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
def test_native_stage_selects_source_warning_and_compound_leaf_only_when_enabled(tmp_path,face):
    source,b,v,leaf,*_=fixture(tmp_path,face);original=source.read_bytes()
    r=stage.run(source,tmp_path/'stage',board_hint='unclassified-test',
        expected_source_sha256=force._hash(source),reporting_build=reporting_build(),
        allow_locked_source=True,allow_leaf_cleanup=True)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert r['retired_native_dangling_barrels']==1 and r['retired_pad_free_source_leaf_tracks']==1
    assert not r['new_native_fault_ids'] and r['independent_whole_source_receiving']['ok']
    assert source.read_bytes()==original and not source.with_suffix('.kicad_prl').exists()
    assert not r['routing_admitted'] and not r['release_authority']


def test_default_barrel_only_stage_refuses_new_dangling_leaf_instead_of_waiving_it(tmp_path):
    source,b,v,leaf,*_=fixture(tmp_path);r=stage.run(source,tmp_path/'refused',board_hint='unclassified-test',
        expected_source_sha256=force._hash(source),reporting_build=reporting_build(),allow_locked_source=True)
    assert not r['ok'] and not r['changed'] and r['candidate']==str(source.resolve())
    assert any('track_dangling' in k for k in r['new_native_fault_ids'])
