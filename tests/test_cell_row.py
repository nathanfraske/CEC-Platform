"""Source-derived repeated-cell layout is invariant to names and rotation."""
import copy
import math

import pcbnew
import pytest
import cec_cell_row as row
from cec_placement_search_domain import rigid_cell_transform


def fixture(rotation=0, prefix=''):
    cells, poses, followers = {}, {}, {}
    for name, x, y in [('floating', 38, 11), ('first', 20, 25),
                       ('second', 32, 25), ('third', 44, 25)]:
        cells[name] = {role: prefix+name+'_'+role for role in ('root', 'a', 'b', 'c')}
        for role, dx, dy, angle in [('root',0,0,90), ('a',-4,-1,270),
                                    ('b',4,0,90), ('c',4,5,270)]:
            poses[cells[name][role]] = (x+dx,y+dy,angle)
        cap = prefix+name+'_cap'
        poses[cap] = (x+3.7,y-2.8,0)
        followers[cap] = cells[name]['b']
    poses[prefix+'unrelated'] = (61,12,180)
    if rotation:
        poses = rigid_cell_transform(poses, cells['first']['root'], rotation)
    return poses, dict(cells=cells, moving_cell='floating',
        row_cells=['first','second','third'], anchor_role='root', follower_owners=followers)


@pytest.mark.parametrize('rotation,prefix', [(0,''),(90,'OTHER_'),(180,'N_'),(270,'X_')])
@pytest.mark.parametrize('side', ['before','after'])
def test_full_rigid_translation_preserves_all_row_and_unrelated_poses(rotation,prefix,side):
    poses, args = fixture(rotation,prefix)
    before = copy.deepcopy(poses)
    proposal = row.extend_row(poses,side=side,**args)
    assert poses == before
    assert len(proposal['poses']) == 5
    root = args['cells']['floating']['root']
    end = args['cells']['first' if side=='before' else 'third']['root']
    sign = -1 if side=='before' else 1
    for axis in (0,1):
        assert proposal['poses'][root][axis] == pytest.approx(
            poses[end][axis]+sign*proposal['pitch_mm'][axis])
    for ref, pose in proposal['poses'].items():
        assert pose[2] == poses[ref][2]
        assert [pose[i]-poses[ref][i] for i in (0,1)] == pytest.approx(proposal['delta_mm'])
    assert not proposal['routing_admitted'] and not proposal['release_authority']


@pytest.mark.parametrize('fault', ['missing','duplicate','missing_role','geometry',
    'orientation','pitch','zero_pitch','nan','fixed','follower','bad_side','too_many'])
def test_ambiguous_or_changed_contracts_refuse_without_mutation(fault):
    poses,args=fixture(); cells=args['cells']
    if fault=='missing': del poses[cells['floating']['b']]
    elif fault=='duplicate': cells['second']['a']=cells['first']['a']
    elif fault=='missing_role': del cells['third']['b']
    elif fault=='geometry': poses[cells['floating']['b']] = (99,99,90)
    elif fault=='orientation': poses[cells['floating']['b']] = (42,11,0)
    elif fault=='pitch':
        for ref in cells['third'].values():
            p=poses[ref];poses[ref]=(p[0]+1,p[1],p[2])
    elif fault=='zero_pitch':
        for role,ref in cells['second'].items():poses[ref]=poses[cells['first'][role]]
    elif fault=='nan':poses[cells['floating']['a']] = (math.nan,0,0)
    elif fault=='fixed':args['immutable_refs']=['floating_cap']
    elif fault=='follower':args['follower_owners']['first_a']='floating_b'
    elif fault=='bad_side':args['side']='somewhere'
    else:args['row_cells']=['first']*17
    with pytest.raises(ValueError):row.extend_row(poses,**args)


def native_fixture():
    poses,args=fixture(); b=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(b,'SUPPLY');b.Add(net)
    for ref,pose in poses.items():
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue('rail-specific-value-'+ref)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
        pad.SetNet(net);fp.Add(pad)
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2])))
        fp.SetOrientationDegrees(pose[2]);b.Add(fp)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(20,25))
    t.SetEnd(pcbnew.VECTOR2I_MM(32,25));t.SetWidth(250000);t.SetNet(net);b.Add(t)
    return b,row.extend_row(poses,**args)


def test_native_draft_preserves_all_values_nets_pad_definitions_and_retained_copper():
    b,p=native_fixture()
    unrelated={fp.GetReference():tuple(fp.GetPosition()) for fp in b.GetFootprints()
               if fp.GetReference() not in p['poses']}
    receipt=row.apply_draft(b,p)
    assert receipt['all_original_copper_exact'] and receipt['component_values_nets_pads_and_faces_exact']
    for ref,at in unrelated.items():assert tuple(b.FindFootprintByReference(ref).GetPosition())==at
    for ref,pose in p['poses'].items():
        assert tuple(b.FindFootprintByReference(ref).GetPosition())==tuple(round(v*1e6) for v in pose[:2])
    assert receipt['requires_incident_copper_reconstruction'] and not receipt['routing_admitted']


@pytest.mark.parametrize('fault',['locked','grouped','stale','forged_transform','membership','authority'])
def test_native_rejects_untrusted_draft_before_moving_any_member(fault):
    b,p=native_fixture(); ref=next(iter(p['poses']));fp=b.FindFootprintByReference(ref)
    if fault=='locked':fp.SetLocked(True)
    elif fault=='grouped':
        g=pcbnew.PCB_GROUP(b);g.SetName('protected-cell');g.AddItem(fp);b.Add(g)
    elif fault=='stale':fp.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='forged_transform':p['poses'][ref]=(1,2,0)
    elif fault=='membership':del p['source_poses'][ref]
    else:p['routing_admitted']=True
    original={f.GetReference():tuple(f.GetPosition()) for f in b.GetFootprints()}
    with pytest.raises(ValueError):row.apply_draft(b,p)
    assert original=={f.GetReference():tuple(f.GetPosition()) for f in b.GetFootprints()}


@pytest.mark.parametrize('axis',[0,1])
def test_one_axis_contact_shortlist_filters_blocked_and_irrelevant_events_before_budget(axis):
    from cec_cell_packing import contact_translation_sites
    part=(0.,0.,1.,1.)
    obstacles=[(-1.,-1.,2.,2.)]+[(.01*i,10.,1.01*i,11.) for i in range(1,20)]
    bounds=(0.,0.,3.,0.)
    if axis:
        part=(part[1],part[0],part[3],part[2])
        obstacles=[(r[1],r[0],r[3],r[2]) for r in obstacles]
        bounds=(0.,0.,0.,3.)
    sites=contact_translation_sites([part],bounds=bounds,obstacles=obstacles,
        clearance=.1,max_sites=2,preferred_origin=(0.,0.))
    assert sites and sites[0][axis]==pytest.approx(2.100001)
    assert all(point[axis]>=2.1 for point in sites)


def test_private_placement_save_reports_load_only_net_propagation_without_routing_authority(tmp_path):
    import cec_field_coupling as field
    import cec_copper_echo as sexpr
    b=pcbnew.BOARD();a=pcbnew.NETINFO_ITEM(b,'TERMINAL_NET');b.Add(a)
    other=pcbnew.NETINFO_ITEM(b,'RETAINED_OLD_RETURN');b.Add(other)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ANY_OWNER')
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetNet(a)
    fp.Add(pad);fp.SetPosition(pcbnew.VECTOR2I_MM(5,5));b.Add(fp)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(5,5))
    t.SetEnd(pcbnew.VECTOR2I_MM(10,5));t.SetWidth(200000);t.SetNet(other);b.Add(t)
    before=field._field_snapshot_inventory(b);path=tmp_path/'draft.kicad_pcb'
    receipt=row.save_placement_draft(b,path)
    assert field._field_snapshot_inventory(b)==before
    assert not receipt['reloaded_copper_identity_exact'] and receipt['load_only_copper_deltas']
    assert not receipt['routing_admitted'] and not receipt['release_authority']
    _,records,_=sexpr._read(path)
    assert records and all(r['net']=='"RETAINED_OLD_RETURN"' for r in records)
    # The production routed-board writer must STILL refuse this draft.
    with pytest.raises(ValueError,match='changed_saved_identity'):
        field._save_field_snapshot(b,tmp_path/'must-not-route.kicad_pcb')


def test_owned_bypass_support_is_not_independently_repacked(monkeypatch):
    import cec_constraints as constraints
    import cec_synth_pipeline as synth
    b,proposal=native_fixture();row.apply_draft(b,proposal)
    _,intent=fixture();intent.pop('follower_owners')
    owned=b.FindFootprintByReference('unrelated')
    owned.SetPosition(b.FindFootprintByReference('first_a').GetPosition())
    extra=pcbnew.PAD(owned);extra.SetNumber('2');extra.SetSize(pcbnew.VECTOR2I_MM(1,1))
    extra.SetAttribute(pcbnew.PAD_ATTRIB_SMD);extra.SetLayerSet(pcbnew.PAD.SMDMask())
    owned.Add(extra)
    monkeypatch.setattr(constraints,'_device_bypass_assignment',lambda *a,**kw:dict(missing=[],
        assigned={'owned':dict(cap_ref='first_cap',requirement=dict(ref='unrelated'))}))
    monkeypatch.setattr(synth,'_footprint_courtyard_box',lambda fp:(
        fp.GetPosition().x/1e6-.4,fp.GetPosition().x/1e6+.4,
        fp.GetPosition().y/1e6-.4,fp.GetPosition().y/1e6+.4))
    before={f.GetReference():tuple(f.GetPosition()) for f in b.GetFootprints()}
    result=row.repack_row_draft(b,intent,max_row_shift_mm=.1)
    assert not result['ok']
    assert any(t['reason']=='owned_local_support_cell_requires_rigid_scope' for t in result['trials'])
    assert before=={f.GetReference():tuple(f.GetPosition()) for f in b.GetFootprints()}


def test_cli_locked_local_recompile_requires_explicit_construction_stage(tmp_path):
    with pytest.raises(SystemExit) as exc:
        row.main(['--source',str(tmp_path/'source.kicad_pcb'),'--source-sha256','unused',
            '--intent',str(tmp_path/'intent.json'),'--out',str(tmp_path/'child'),
            '--hint','synthetic-board','--allow-owned-locked-local-recompile'])
    assert exc.value.code==2 and not (tmp_path/'child').exists()
