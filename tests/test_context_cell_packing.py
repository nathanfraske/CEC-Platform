import copy
import pytest
from shapely.geometry import box
from cec_cell_packing import pack_context_translations


def member(context, geometry, **facts):
    return dict(context=context, geometry=geometry, **facts)


def group(*members, bounds=(0,0,2,0), preferred=(0,0), sites=()):
    return dict(members=list(members), bounds=bounds, preferred=preferred, sites=sites)


def same_context(a,b):
    return a['context']==b['context']


@pytest.mark.parametrize('tags', [('first','second'), ('renamed','peer')])
def test_other_context_is_not_phantom_body_keepout(tags):
    a,b=tags
    groups={'generic_cell':group(member(a,box(0,0,1,1)))}
    fixed=[member(b,box(0,0,3,3))]
    result=pack_context_translations(groups,fixed,interferes=same_context)
    assert result['ok'] and result['translations']=={'generic_cell':[0,0]}
    assert not result['admission_authority']


def test_matched_cell_moves_both_members_or_neither_without_mutation():
    groups={'matched':group(member('a',box(0,0,1,1)),member('b',box(0,0,1,1)))}
    fixed=[member('b',box(0,0,1,1))]
    before=copy.deepcopy(groups)
    result=pack_context_translations(groups,fixed,interferes=same_context)
    assert result['ok']
    assert result['translations']['matched'][0]>=1.15-1e-7
    assert groups==before


def test_cross_context_height_and_vent_model_is_explicit_and_preserved():
    def model(a,b):
        if a['context']==b['context']:return True
        return a['height']+b['height']+max(a.get('vent',.5),b.get('vent',.5))>21.5
    fixed=[member('opposing',box(0,0,1,1),height=17.2,vent=3)]
    groups={'low':group(member('receiver',box(0,0,1,1),height=1.0))}
    assert pack_context_translations(groups,fixed,interferes=model)['translations']=={'low':[0,0]}
    groups['low']['members'][0]['height']=3.0
    r=pack_context_translations(groups,fixed,interferes=model)
    assert r['ok'] and r['translations']['low'][0]>=1.15-1e-7


def test_internal_collision_is_not_hidden_by_translation():
    groups={'broken':group(member('a',box(0,0,1,1)),member('a',box(.5,0,1.5,1)))}
    r=pack_context_translations(groups,[],interferes=same_context)
    assert not r['ok'] and r['reason']=='rigid_context_cell_internal_collision'
    assert r['group_key']=='broken' and r['member_indices']==[0,1]


def test_native_courtyard_boundary_touch_at_zero_extra_clearance():
    groups={'g':group(member('a',box(0,0,1,1)),bounds=(0,0,0,0))}
    r=pack_context_translations(groups,[member('a',box(1,0,2,1))],
                                interferes=same_context,clearance=0)
    assert r['ok']
    r=pack_context_translations(groups,[member('a',box(.99,0,2,1))],
                                interferes=same_context,clearance=0)
    assert not r['ok']


def test_collision_oracle_deadline_cannot_admit_a_success(monkeypatch):
    import time
    now=[0.]
    monkeypatch.setattr(time,'monotonic',lambda:now[0])
    def oracle(a,b):
        now[0]=11.
        return False
    r=pack_context_translations({'g':group(member('a',box(0,0,1,1)))},
        [member('b',box(0,0,1,1))],interferes=oracle)
    assert not r['ok'] and r['timed_out'] and not r['translations']
    assert r['blocked_group']=='g' and r['partial_prefix_is_not_admitted']


def test_bounded_failure_does_not_grow_or_select_board():
    groups={'cell':group(member('a',box(0,0,1,1)),bounds=(0,0,0,0))}
    r=pack_context_translations(groups,[member('a',box(0,0,3,3))],interferes=same_context)
    assert not r['ok'] and not r['admission_authority']
    assert r['blocked_group']=='cell' and r['refused_by_group']=={'cell':1}
    assert r['blocker_samples'][0]['obstacle_facts']['context']=='a'
    assert 'geometry' not in r['blocker_samples'][0]['obstacle_facts']
    assert r['partial_prefix_is_not_admitted']
    assert groups['cell']['bounds']==(0,0,0,0)


@pytest.mark.parametrize('answer',[None,1,'ignore'])
def test_unknown_collision_answer_fails_closed(answer):
    with pytest.raises(ValueError,match='explicit bool'):
        pack_context_translations({'g':group(member('a',box(0,0,1,1)))},
            [member('b',box(0,0,3,3))],interferes=lambda a,b:answer)


def test_unknown_native_translation_answer_fails_closed():
    with pytest.raises(ValueError,match='explicit bool'):
        pack_context_translations({'g':group(member('a',box(0,0,1,1)))},[],
            interferes=same_context,accept_translation=lambda key,delta:None)


@pytest.mark.parametrize('kwargs',[dict(timeout_s=0),dict(timeout_s=30),dict(max_nodes=0),
    dict(sites_per_group=257),dict(clearance=float('nan'))])
def test_invalid_or_unbounded_contract_refused(kwargs):
    with pytest.raises(ValueError):
        pack_context_translations({},[],interferes=same_context,**kwargs)


def test_clearance_and_member_contexts_survive_contact_site_generation():
    groups={'g':group(member('a',box(0,0,1,1)),member('b',box(5,0,6,1)),
                      bounds=(0,0,4,0),sites=((2.5,0),))}
    fixed=[member('a',box(0,0,2,2)),member('b',box(6.5,0,7.5,2))]
    r=pack_context_translations(groups,fixed,interferes=same_context,clearance=.3)
    assert r['ok'] and r['translations']['g'][0]>=2.3-1e-7
    assert r['translations']['g'][0]>=2.8-1e-7


@pytest.mark.parametrize('delta', [(0., 0.), (2., -1.)])
def test_blocker_witness_binds_the_actual_trial_pose_without_mutating_geometry(delta):
    moving=member('native',box(0,0,1,1),uuid='arbitrary-land')
    obstacle=member('native',box(delta[0],delta[1],delta[0]+2,delta[1]+2),
                    uuid='arbitrary-obstacle')
    groups={'arbitrary-cell':group(moving,
        bounds=(*delta,*delta),preferred=delta)}
    original=moving['geometry'].wkb
    r=pack_context_translations(groups,[obstacle],interferes=same_context,clearance=0)
    assert not r['ok'] and r['nodes']==1 and not r['admission_authority']
    witness=r['blocker_samples'][0]
    assert witness['translation_mm']==list(delta)
    assert witness['posed_member_bounds_mm']==[delta[0],delta[1],delta[0]+1,delta[1]+1]
    assert witness['obstacle_bounds_mm']==list(obstacle['geometry'].bounds)
    assert witness['member_facts']['uuid']=='arbitrary-land'
    assert witness['obstacle_facts']['uuid']=='arbitrary-obstacle'
    assert moving['geometry'].wkb==original and '_context_bounds' not in moving


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('offset',[(0,0),(21.3,-17.8)])
def test_polygon_contacts_find_pockets_hidden_by_diagonal_bounding_rectangles(quarter,offset):
    from shapely import affinity
    from shapely.geometry import LineString
    def pose(shape):
        return affinity.translate(affinity.rotate(shape,quarter*90,origin=(0,0)),*offset)
    moving=member('same',pose(box(-.35,-.4,.35,.4)),uuid='arbitrary-terminal')
    obstacle=member('same',pose(LineString([(-3,-3),(3,3)]).buffer(.10)),
                    uuid='arbitrary-immutable-copper')
    groups={'renamed-cell':group(moving,bounds=(-.5,-.5,.5,1.5))}
    before=copy.deepcopy((groups,[obstacle]))
    legacy=pack_context_translations(groups,[obstacle],interferes=same_context,clearance=.05)
    assert not legacy['ok']
    new=pack_context_translations(groups,[obstacle],interferes=same_context,clearance=.05,
                                  shape_contact_sites=True)
    assert new['ok'] and new['polygon_contact_proposals']['renamed-cell']>0
    dx,dy=new['translations']['renamed-cell']
    actual=affinity.translate(moving['geometry'],dx,dy)
    assert actual.distance(obstacle['geometry'])>=.05-1e-7
    assert not new['admission_authority'] and (groups,[obstacle])==before


def test_polygon_contact_sites_do_not_skip_other_members_or_feasibility_guard():
    from shapely.geometry import LineString
    first=member('same',box(-.35,-.4,.35,.4))
    diagonal=member('same',LineString([(-3,-3),(3,3)]).buffer(.1))
    groups={'g':group(first,bounds=(-.5,-.5,.5,1.5))}
    veto=pack_context_translations(groups,[diagonal],interferes=same_context,
        shape_contact_sites=True,accept_translation=lambda key,delta:False)
    assert not veto['ok'] and not veto['translations']
    satellite=member('other',box(8,0,9,1))
    groups['g']['members'].append(satellite)
    blocker=member('other',box(6,-3,12,4))
    blocked=pack_context_translations(groups,[diagonal,blocker],interferes=same_context,
                                      shape_contact_sites=True)
    assert not blocked['ok'] and not blocked['translations']


@pytest.mark.parametrize('bad',[None,1,'yes'])
def test_polygon_contact_policy_requires_an_explicit_boolean(bad):
    with pytest.raises(ValueError,match='explicit_polygon_contact'):
        pack_context_translations({},[],interferes=same_context,shape_contact_sites=bad)


def test_shared_rectangular_sweep_preserves_actual_holes_and_work_budget():
    from cec_translation_geometry import rectangular_sweep
    from shapely.geometry import Point
    class Work:
        def __init__(self):self.contacts=0
        def tick(self):pass
        def contact(self):self.contacts+=1
    source=box(0,0,6,6).difference(box(2,2,4,4));before=source.wkb;work=Work()
    result=rectangular_sweep(source,.25,.25,work)
    assert result.covers(Point(2.1,3)) and not result.covers(Point(3,3))
    assert source.wkb==before and work.contacts>0


def test_preferred_complete_pose_does_not_build_unused_contact_domains(monkeypatch):
    import cec_cell_packing as packing
    import cec_translation_geometry as geometry
    def unexpected(*args,**kwargs):
        raise AssertionError('unused fallback must not consume geometry budget')
    monkeypatch.setattr(packing,'contact_translation_sites',unexpected)
    monkeypatch.setattr(geometry,'rectangular_sweep',unexpected)
    result=packing.pack_context_translations(
        {'generic':group(member('a',box(0,0,1,1)),bounds=(-1,-1,1,1))},
        [member('a',box(4,0,5,1))],interferes=same_context,
        shape_contact_sites=True)
    assert result['ok'] and result['nodes']==1
    assert result['polygon_contact_proposals']=={}


def test_exhausted_preferred_pose_does_not_build_polygon_fallback(monkeypatch):
    import cec_translation_geometry as geometry
    def unexpected(*args,**kwargs):
        raise AssertionError('exhausted node budget may not start fallback')
    monkeypatch.setattr(geometry,'rectangular_sweep',unexpected)
    result=pack_context_translations(
        {'generic':group(member('a',box(0,0,1,1)),bounds=(-1,-1,1,1))},
        [member('a',box(0,0,1,1))],interferes=same_context,
        shape_contact_sites=True,max_nodes=1)
    assert not result['ok'] and result['exhausted'] and result['nodes']==1
    assert result['polygon_contact_proposals']=={}


def test_lazy_contacts_still_backtrack_after_a_downstream_cell_refusal(monkeypatch):
    import cec_cell_packing as packing
    calls=[];original=packing.contact_translation_sites
    def observed(*args,**kwargs):
        calls.append(kwargs['bounds'])
        return original(*args,**kwargs)
    monkeypatch.setattr(packing,'contact_translation_sites',observed)
    groups={
        'first':group(member('a',box(0,0,1,1)),bounds=(0,0,2,0)),
        'second':group(member('a',box(0,0,1,1)),bounds=(0,0,0,0)),
    }
    result=packing.pack_context_translations(groups,[],interferes=same_context,
        clearance=.15,group_order=['first','second'],shape_contact_sites=True)
    assert result['ok'] and result['translations']['first'][0]>=1.15-1e-7
    assert result['translations']['second']==[0,0] and calls


@pytest.mark.parametrize('limit',[1,2])
def test_actual_polygon_work_exhaustion_is_a_bounded_unadmitted_receipt(limit):
    from shapely.geometry import LineString
    groups={'arbitrary-cell':group(member('same',box(-.35,-.4,.35,.4)),
        bounds=(-.5,-.5,.5,1.5))}
    fixed=[member('same',LineString([(-3,-3),(3,3)]).buffer(.1))]
    before=copy.deepcopy((groups,fixed))
    result=pack_context_translations(groups,fixed,interferes=same_context,clearance=.05,
        shape_contact_sites=True,max_shape_contacts=limit)
    assert not result['ok'] and not result['translations'] and result['exhausted']
    assert not result['timed_out'] and not result['admission_authority']
    assert result['reason']=='bounded_context_polygon_work_exhausted'
    assert result['physical_feasibility']=='not_determined'
    assert result['geometry_work_contacts']==limit and result['geometry_work_limit']==limit
    assert result['blocked_group']=='arbitrary-cell' and result['partial_prefix_is_not_admitted']
    assert (groups,fixed)==before
    replay=pack_context_translations(groups,fixed,interferes=same_context,clearance=.05,
        shape_contact_sites=True,max_shape_contacts=1000)
    assert replay['ok'] and replay['geometry_work_contacts']<=1000


def test_polygon_work_exhaustion_never_admits_a_cooperative_prefix():
    from shapely.geometry import LineString
    groups={'first':group(member('a',box(8,8,9,9)),bounds=(0,0,0,0)),
        'blocked':group(member('b',box(-.35,-.4,.35,.4)),bounds=(-.5,-.5,.5,1.5))}
    result=pack_context_translations(groups,[member('b',LineString([(-3,-3),(3,3)]).buffer(.1))],
        interferes=same_context,group_order=['first','blocked'],shape_contact_sites=True,
        max_shape_contacts=1)
    assert not result['ok'] and not result['translations']
    assert result['furthest_proposed_prefix']=={'first':[0,0]}
    assert result['blocked_group']=='blocked' and result['physical_feasibility']=='not_determined'


@pytest.mark.parametrize('bad',[True,0,-1,1000001,1.5,float('nan')])
def test_polygon_contact_work_budget_cannot_be_unknown_or_unbounded(bad):
    with pytest.raises(ValueError,match='bounded_polygon_contact_work'):
        pack_context_translations({},[],interferes=same_context,max_shape_contacts=bad)
