"""Synthetic comparison semantics ONLY; not mocked physical receiving passes."""
import copy,time
import pytest
from cec_source_whole_leaf_comparison import _reconcile_owned_leaf

def fixture():
 pad='input';leg=('A','n','sense');peer=('B','n','sense')
 def departure(uid):return dict(uuid=uid,layer='F.Cu',inner_projection_mm=.7,
  inward_direction=[0,-1],contact_exit_mm=[8,3],transverse_error_nm=0,
  reachable_input_pad_uuids=[pad],input_contact_paths={pad:[uid,pad]})
 def report(uid,pos):
  d=departure(uid);n=copy.deepcopy(d);n.pop('input_contact_paths');n['reachable_input_pad_uuids']=[]
  component=dict(component='component-'+uid,layer='F.Cu',bounds_nm=[0,0,10,10],via=None,
   contributors=[dict(kind='PAD',uuid='fixed',position_nm=[8,4]),
    dict(kind='PCB_TRACK',uuid=uid,net='sense'),dict(kind='PAD',uuid=pad,net='sense',
     footprint_uuid='actual-owner',ref='A',pad='4',position_nm=pos)])
  inner=[dict(input_ref='A',leg='n',net='sense',ok=True,native=dict(departures=[d],issues=[],non_sense_departures=[])),
   dict(input_ref='B',leg='n',net='sense',ok=False,native=dict(departures=[],non_sense_departures=[n],reason='input_not_reached_from_source'))]
  clip=dict(input_ref='A',leg='n',net='sense',ok=True,native={k:dict(witnesses=[dict(path=[copy.deepcopy(component)])])
   for k in('baseline_geometry','upper','lower')})
  return dict(geometry_policy=dict(inner_min=.1),inner_departure=dict(details=inner),clipped_isolation=dict(details=[clip]))
 before,after=report('old',[1,2]),report('new',[2,3])
 ctx=dict(leg=leg,pad=pad,old_ids=['old'],new_ids=['new'],old_path=['old',pad],new_path=['new',pad],
  peers=[peer],before_position=[1,2],after_position=[2,3],absolute_before=dict(ok=True),absolute_after=dict(ok=True))
 for side,pos in(('before',[1,2]),('after',[2,3])):
  ctx['moved_land_descriptor_'+side]=dict(kind='PAD',uuid=pad,net='sense',
   footprint_uuid='actual-owner',ref='A',pad='4',position_nm=pos)
 for flag in('fresh_macro_received','fixed_force_literal_equal','fixed_lands_equal','same_pickup_kernel',
  'exact_owned_inventory','peer_component_equal','source_live','policy_equal'):ctx[flag]=True
 return before,after,ctx

def test_default_remains_strict_and_raw_immutable():
 a,b,c=fixture();old=copy.deepcopy((a,b,c));got,edits=_reconcile_owned_leaf(a,b,c)
 assert got==b and edits==[] and (a,b,c)==old

def test_explicit_projection_matches_only_owned_witness_and_preserves_failed_peer():
 a,b,c=fixture();old=copy.deepcopy((a,b,c));got,edits=_reconcile_owned_leaf(a,b,c,whole_leaf_mode=True)
 assert got==a and len(edits)==8 and got['inner_departure']['details'][1]['ok']is False
 assert (a,b,c)==old

@pytest.mark.parametrize('flag',['fresh_macro_received','fixed_force_literal_equal','fixed_lands_equal',
 'same_pickup_kernel','exact_owned_inventory','peer_component_equal','source_live','policy_equal'])
def test_each_native_wrapper_precondition_mandatory(flag):
 a,b,c=fixture();c[flag]=False
 with pytest.raises(ValueError):_reconcile_owned_leaf(a,b,c,whole_leaf_mode=True)

@pytest.mark.parametrize('fault',['policy','before_absolute','after_absolute','outward','third_contact',
 'peer_pass','peer_reached','force_contributor','component_bounds','cut_witness_count','wrong_input_position','forged_path'])
def test_exact_projection_negative_controls(fault):
 a,b,c=fixture();d=b['inner_departure']['details'][0]['native']['departures'][0]
 comp=b['clipped_isolation']['details'][0]['native']['upper']['witnesses'][0]['path'][0]
 if fault=='policy':b['geometry_policy']['inner_min']=0
 elif fault=='before_absolute':c['absolute_before']['ok']=False
 elif fault=='after_absolute':c['absolute_after']['ok']=False
 elif fault=='outward':d['inward_direction']=[0,1]
 elif fault=='third_contact':b['inner_departure']['details'][0]['native']['departures'].append(copy.deepcopy(d))
 elif fault=='peer_pass':b['inner_departure']['details'][1]['ok']=True
 elif fault=='peer_reached':b['inner_departure']['details'][1]['native']['non_sense_departures'][0]['reachable_input_pad_uuids']=['peer']
 elif fault=='force_contributor':comp['contributors'][0]['position_nm']=[9,4]
 elif fault=='component_bounds':comp['bounds_nm']=[0,0,11,10]
 elif fault=='cut_witness_count':b['clipped_isolation']['details'][0]['native']['lower']['witnesses'].append(dict(path=[]))
 elif fault=='wrong_input_position':comp['contributors'][2]['position_nm']=[9,9]
 elif fault=='forged_path':d['input_contact_paths']['input']=['unowned','input']
 with pytest.raises(ValueError):_reconcile_owned_leaf(a,b,c,whole_leaf_mode=True)

def test_expired_budget_never_rescued():
 a,b,c=fixture()
 with pytest.raises(ValueError,match='deadline'):
  _reconcile_owned_leaf(a,b,c,whole_leaf_mode=True,deadline=time.monotonic()-1)

@pytest.mark.parametrize('fault',['macro_code','source_hash','candidate_hash','family','native_code','incomplete_native'])
def test_native_wrapper_refuses_stale_bindings_before_geometry(monkeypatch,fault):
 # Identity-control semantics only; these mocks do not assert native proof.
 from pathlib import Path
 import cec_force_current as force
 from cec_source_whole_leaf_comparison import _derive_context
 class Board:
  def __init__(self,path):self.path=path
  def GetFileName(self):return self.path
 monkeypatch.setattr(force,'_code_identity',lambda:{'code':'current'})
 monkeypatch.setattr(force,'_family',lambda p,h:{'material':'same'})
 monkeypatch.setattr(force,'_hash',lambda p:'hash-'+str(p))
 def raw(path):return dict(source=path,complete=True,identity_stable=True,
  code_before={'code':'current'},code_after={'code':'current'},board_hint='synthetic',
  source_family_before={'material':'same'},source_family_after={'material':'same'})
 a,b=raw('/source'),raw('/candidate')
 proof=dict(ok=True,complete=True,source_candidate_families_and_code_unchanged=True,
  scope='independent_saved_source_owned_macro_cell',all_original_surviving_native_partitions_preserved=True,
  all_original_physical_ground_returns=dict(ok=True),independent_exact_source_cut_transform_and_additions=dict(ok=True,complete=True),
  source_macro_packet=dict(code_identity={'code':'current'}),source_sha256='hash-/source',candidate_sha256='hash-/candidate')
 if fault=='macro_code':proof['source_macro_packet']['code_identity']={'code':'old'}
 elif fault=='source_hash':proof['source_sha256']='stale'
 elif fault=='candidate_hash':proof['candidate_sha256']='stale'
 elif fault=='family':a['source_family_before']={'material':'changed'}
 elif fault=='native_code':b['code_after']={'code':'old'}
 elif fault=='incomplete_native':b['complete']=False
 with pytest.raises(ValueError):
  _derive_context(Board('/source'),Board('/candidate'),a,b,proof,'pad',deadline=time.monotonic()+1)

def test_only_bounded_owned_contact_work_counter_may_change():
 a,b,c=fixture();a['clipped_isolation']['details'][0]['native']['contacts_examined']=10
 b['clipped_isolation']['details'][0]['native']['contacts_examined']=12
 projected,edits=_reconcile_owned_leaf(a,b,c,whole_leaf_mode=True)
 assert projected==a and edits[-1].endswith('/contacts_examined')
 b['clipped_isolation']['details'][0]['native']['contacts_examined']=True
 with pytest.raises(ValueError):_reconcile_owned_leaf(a,b,c,whole_leaf_mode=True)

@pytest.mark.parametrize('fault',['code','family','deadline'])
def test_final_live_barrier_cannot_be_replaced_by_earlier_success(monkeypatch,fault):
 import cec_force_current as force
 from cec_source_whole_leaf_comparison import _final_bindings
 monkeypatch.setattr(force,'_code_identity',lambda:{'code':'old'if fault=='code'else 'current'})
 monkeypatch.setattr(force,'_family',lambda p,h:{'material':'drift'if fault=='family'else 'same'})
 r=dict(code_before={'code':'current'},code_after={'code':'current'},board_hint='synthetic',source_family_after={'material':'same'})
 with pytest.raises(ValueError):_final_bindings('/source','/candidate',r,r,
  deadline=time.monotonic()+(-1 if fault=='deadline'else 1))

@pytest.mark.parametrize('fault',['remove_owned','extra_owned','peer_unknown'])
def test_no_owned_contributor_disappearance_or_peer_debt_reclassification(fault):
 a,b,c=fixture();component=b['clipped_isolation']['details'][0]['native']['baseline_geometry']['witnesses'][0]['path'][0]
 if fault=='remove_owned':component['contributors']=[v for v in component['contributors']if v['uuid']!='new']
 elif fault=='extra_owned':component['contributors'].append(dict(kind='PCB_TRACK',uuid='third',net='sense'))
 else:b['inner_departure']['details'][1]['ok']=None
 with pytest.raises(ValueError):_reconcile_owned_leaf(a,b,c,whole_leaf_mode=True)

def native_fixture():
 # Existing real native manufacturer-typed leaf fixture, not a success mock.
 import importlib.util
 from pathlib import Path
 spec=importlib.util.spec_from_file_location('owned_leaf_native_fixture',Path(__import__('cec_force_current').__file__).resolve().parents[1]/'tests/test_measurement_leaf.py')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 return m.fixture('/renamed/measurement')

def test_actual_native_leaf_rejects_acquired_third_interior_contact():
 import pcbnew,cec_force_current as force,cec_measurement_leaf as leaf
 b,pad,anchor,tracks,xy=native_fixture()
 assert leaf.plan(b,force._uid(pad))['track_uuids']
 third=pcbnew.PCB_TRACK(b);third.SetStart(xy((13,10)));third.SetEnd(xy((13,12)))
 third.SetWidth(200000);third.SetLayer(0);third.SetNet(pad.GetNet());b.Add(third)
 with pytest.raises(ValueError,match='unowned_interior_contact'):
  leaf.plan(b,force._uid(pad))

def test_actual_fixed_native_peer_query_relation_detects_disconnection():
 import cec_force_current as force
 from cec_source_whole_leaf_comparison import _fixed_native_query
 a,pa,aa,ta,xy=native_fixture();b,pb,ab,tb,_=native_fixture()
 for x,y in zip([pa,aa,*ta],[pb,ab,*tb]):y.m_Uuid.Clone(x.m_Uuid)
 # Canonical native pad keys include the owner footprint identity too.
 pb.GetParentFootprint().m_Uuid.Clone(pa.GetParentFootprint().m_Uuid)
 ab.GetParentFootprint().m_Uuid.Clone(aa.GetParentFootprint().m_Uuid)
 before=_fixed_native_query(a,pa.GetNetname(),set(),[force._uid(aa)],deadline=time.monotonic()+2)
 same=_fixed_native_query(b,pb.GetNetname(),set(),[force._uid(ab)],deadline=time.monotonic()+2)
 assert before==same
 tb[-1].SetEnd(xy((19,10)))
 changed=_fixed_native_query(b,pb.GetNetname(),set(),[force._uid(ab)],deadline=time.monotonic()+2)
 assert before!=changed
 assert before['peer_components']!=changed['peer_components']




@pytest.mark.parametrize('value',[False,True,{},'pad',[{'pad_uuid':'a'}],['unknown'],['00000000-0000-0000-0000-000000000001']*2])
def test_literal_only_public_option_rejects_flags_roles_and_duplicates(value):
 from cec_source_whole_leaf_comparison import requests
 with pytest.raises(ValueError):requests(value)

def test_empty_literal_option_preserves_default():
 from cec_source_whole_leaf_comparison import requests
 assert requests(())==() and requests([])==()

def test_native_leaf_remaining_lease_is_capped_and_never_reset(monkeypatch):
 import cec_source_whole_leaf_comparison as m
 monkeypatch.setattr(m.time,'monotonic',lambda:100.)
 assert m._remaining(101.)==1. and m._remaining(120.)==10.
 with pytest.raises(ValueError,match='deadline'):m._remaining(100.)

def test_public_wrapper_rejects_unknown_kwargs_and_injected_roles():
 import cec_macro_measurement_evidence as m
 with pytest.raises(TypeError):m.receive('source','child',board_hint='renamed',whole_leaf_success=True)
 r=m.receive('source','child',board_hint='renamed',whole_leaf_pad_uuids=[{'net':'sense','role':'quiet'}])
 assert not r['ok']and 'literal_bounded' in r['errors'][0]

def test_internal_projection_refuses_two_requested_pads_on_same_authored_net(monkeypatch):
 # Dispatch/scope control only; geometry is not mocked as public authority.
 import json,cec_source_whole_leaf_comparison as m
 uid='00000000-0000-0000-0000-000000000001';second='00000000-0000-0000-0000-000000000002'
 def replace(v):
  if isinstance(v,dict):return {(uid if k=='input'else k):replace(x)for k,x in v.items()}
  if isinstance(v,(list,tuple)):return [replace(x)for x in v]
  return uid if v=='input'else v
 a,b,c=[replace(v)for v in fixture()]
 monkeypatch.setattr(m,'_derive_context',lambda *args,**kwargs:c)
 monkeypatch.setattr(m,'_final_bindings',lambda *args,**kwargs:None)
 bindings={p:dict(ref=ref,net='sense',before=[1,2],after=[2,3])for p,ref in((uid,'A'),(second,'C'))}
 proof=dict(moved_refs=['A','C'],source_macro_packet=dict(source_plan=dict(measurement_leaves=[
  dict(pad_uuid=p,owner=ref,net='sense',points_nm=[[1,2]])for p,ref in((uid,'A'),(second,'C'))])))
 with pytest.raises(ValueError,match='one_requested_whole_leaf_per_authored_net'):
  m.reconcile_received_whole_leaves(None,None,a,b,proof,bindings,[uid,second],deadline=time.monotonic()+1)

@pytest.mark.parametrize('fault',['not_moved','unclaimed','wrong_owner','wrong_net','wrong_frame'])
def test_only_actual_moved_Source_claimed_leaf_can_opt_in(fault):
 import cec_source_whole_leaf_comparison as m
 uid='00000000-0000-0000-0000-000000000001'
 bindings={uid:dict(ref='A',net='sense',before=[1,2],after=[2,3])}
 claim=dict(pad_uuid=uid,owner='A',net='sense',points_nm=[[1,2]])
 proof=dict(moved_refs=['A'],source_macro_packet=dict(source_plan=dict(measurement_leaves=[claim])))
 if fault=='not_moved':bindings={}
 elif fault=='unclaimed':proof['source_macro_packet']['source_plan']['measurement_leaves']=[]
 elif fault=='wrong_owner':claim['owner']='foreign'
 elif fault=='wrong_net':claim['net']='foreign'
 else:claim['points_nm'][0]=[9,9]
 with pytest.raises(ValueError):
  m.reconcile_received_whole_leaves(None,None,{}, {},proof,bindings,[uid],deadline=time.monotonic()+1)
# Adversarial malformed-evidence controls: projection semantics only, not
# mocked saved-board receiving or a physical qualification claim.
import cec_source_whole_leaf_comparison as draft


@pytest.mark.parametrize('field',['kind','net','ref','pad','footprint_uuid'])
def test_matching_forged_descriptors_do_not_replace_live_binding(field):
    before,after,context=fixture()
    for report in(before,after):
        component=report['clipped_isolation']['details'][0]['native']['baseline_geometry']['witnesses'][0]['path'][0]
        next(v for v in component['contributors']if v['uuid']=='input')[field]='forged-on-both-sides'
    # Context descriptors model independently derived native land identity;
    # two matching report fields are not their own identity authority.
    with pytest.raises(ValueError):
        draft._reconcile_owned_leaf(before,after,context,whole_leaf_mode=True)


@pytest.mark.parametrize('field',['kind','net','ref','pad','footprint_uuid'])
def test_owned_moved_land_contributor_descriptor_except_position_is_immutable(field):
    before,after,context=fixture()
    first=before['clipped_isolation']['details'][0]['native']['baseline_geometry']['witnesses'][0]['path'][0]
    last=after['clipped_isolation']['details'][0]['native']['baseline_geometry']['witnesses'][0]['path'][0]
    for component in(first,last):
        land=next(v for v in component['contributors']if v['uuid']=='input')
        land.update(kind='PAD',net='sense',ref='A',pad='4',footprint_uuid='actual-owner')
    next(v for v in last['contributors']if v['uuid']=='input')[field]='unrelated'
    with pytest.raises(ValueError):
        draft._reconcile_owned_leaf(before,after,context,whole_leaf_mode=True)


@pytest.mark.parametrize('uid',['new','input'])
def test_owned_component_contributor_multiplicity_cannot_be_erased(uid):
    before,after,context=fixture()
    component=after['clipped_isolation']['details'][0]['native']['baseline_geometry']['witnesses'][0]['path'][0]
    component['contributors'].append(copy.deepcopy(next(v for v in component['contributors']if v['uuid']==uid)))
    with pytest.raises(ValueError):
        draft._reconcile_owned_leaf(before,after,context,whole_leaf_mode=True)
