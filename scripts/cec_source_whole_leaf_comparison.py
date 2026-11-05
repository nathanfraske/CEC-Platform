"""Internal Source-owned whole-leaf comparison projection.

This is not a saved-board receiver. cec_macro_measurement_evidence owns fresh
public macro receiving, raw native replays and final family/code barriers.
No caller context/proof-success flag is a public admission interface.
"""
import copy,json,time

def _literal(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def _need(v,reason):
 if not v:raise ValueError(reason)

def _remaining(deadline):
 left=deadline-time.monotonic()
 _need(left>0,'whole_leaf_deadline')
 return min(10.,left)

def _fixed_native_query(board,net,excluded,peer_pad_uuids,*,deadline):
 """Independent real native graph with saved-zone islands, no fill/Build.

 Exclude only the owned leaf and moved input land. A zone UUID never joins
 disjoint polygons. Full query inventory and component relation are compared,
 including every unfinished peer's complete actual retained component.
 """
 import pcbnew,cec_force_current as force,cec_native_zone_islands as islands
 rows=[i for i in [*board.GetTracks(),*(p for f in board.GetFootprints()for p in f.Pads())]
  if i.GetNetname()==net and force._uid(i)not in excluded]
 for zone in board.Zones():
  _need(time.monotonic()<deadline,'whole_leaf_native_query_deadline')
  if zone.GetNetname()==net and not zone.GetIsRuleArea():rows.extend(islands.decompose(board,zone,deadline=deadline))
 _need(len(rows)<=1024,'bounded_whole_leaf_fixed_query_inventory')
 objects={repr(force._item_key(i)):i for i in rows}
 _need(len(objects)==len(rows),'unambiguous_whole_leaf_native_query_inventory')
 graph=pcbnew.CONNECTIVITY_DATA()
 for item in rows:
  _need(time.monotonic()<deadline,'whole_leaf_native_query_deadline')
  _need(graph.Add(item),'whole_leaf_fixed_native_query_item_refused')
 relation={}
 for token,item in sorted(objects.items()):
  _need(time.monotonic()<deadline,'whole_leaf_native_query_deadline')
  reached={token}|{repr(force._item_key(i))for i in graph.GetConnectedItems(item)}
  _need(reached<=objects.keys(),'whole_leaf_fixed_query_unknown_conductor')
  relation[token]=sorted(reached)
 peer_tokens={uid:[k for k,v in objects.items()if force._uid(v)==uid]for uid in peer_pad_uuids}
 _need(all(len(v)==1 for v in peer_tokens.values()),'actual_unique_unfinished_peer_land_required')
 return dict(inventory=sorted(objects),component_relation=relation,
  peer_components={uid:relation[tokens[0]]for uid,tokens in peer_tokens.items()},
  saved_zone_islands=True,no_board_mutation=True)

def _final_bindings(source,candidate,before,after,*,deadline):
 import cec_force_current as force
 _need(time.monotonic()<deadline,'whole_leaf_deadline')
 epoch=force._code_identity()
 _need(epoch==before['code_before']==after['code_after'],'whole_leaf_final_code_changed')
 for path,report in((source,before),(candidate,after)):
  _need(force._family(path,report['board_hint'])==report['source_family_after'],
   'whole_leaf_final_family_changed')
 _need(time.monotonic()<deadline,'whole_leaf_deadline')

def _derive_context(parent,child,before,after,proof,pad,*,deadline):
 """Native physical prerequisites, never accept a supplied geometry pass."""
 import cec_force_current as force,cec_measurement_leaf as leaf
 import cec_additive_route_receiving as ast,cec_copper_echo as syntax
 import cec_force_sense_evidence as sense
 from pathlib import Path
 _need(time.monotonic()<deadline,'whole_leaf_deadline')
 source,candidate=Path(parent.GetFileName()),Path(child.GetFileName())
 epoch=force._code_identity()
 for path,report in((source,before),(candidate,after)):
  _need(report.get('source')==str(path)and report.get('complete')is True and report.get('identity_stable')is True
   and report.get('code_before')==epoch and report.get('code_after')==epoch
   and report.get('source_family_before')==report.get('source_family_after')==force._family(path,report['board_hint']),
   'fresh_same_epoch_source_native_evidence_required')
 _need(proof.get('ok')is True and proof.get('complete')is True
  and proof.get('scope')=='independent_saved_source_owned_macro_cell'
  and proof.get('all_original_surviving_native_partitions_preserved')is True
  and proof.get('all_original_physical_ground_returns',{}).get('ok')is True
  and all(proof.get('independent_exact_source_cut_transform_and_additions',{}).get(k)is True for k in('ok','complete'))
  and proof.get('source_candidate_families_and_code_unchanged')is True
  and proof.get('source_macro_packet',{}).get('code_identity')==epoch
  and proof.get('source_sha256')==force._hash(source)
  and proof.get('candidate_sha256')==force._hash(candidate),
  'fresh_independent_macro_receiving_required')
 a=leaf.plan(parent,pad,timeout_s=_remaining(deadline))
 b=leaf.plan(child,pad,timeout_s=_remaining(deadline))
 claims=[q for q in proof['source_macro_packet']['source_plan']['measurement_leaves']if q.get('pad_uuid')==pad]
 _need(claims==[a],'fresh_source_macro_leaf_binding_changed')
 _need(before['lineage']==after['lineage']and before['lineage']['ok']is True,
  'fresh_canonical_manufacturer_input_lineage_changed')
 _need(a['net']==b['net']and a['layer']==b['layer']==0 and a['width_nm']==b['width_nm']
  and a['boundary_uuids']==b['boundary_uuids']and a['points_nm'][-2:]==b['points_nm'][-2:],
  'exact_whole_leaf_owner_width_face_boundary_required')
 old_ids,new_ids=set(a['track_uuids']),set(b['track_uuids']);net=a['net']
 _need(old_ids<=set(proof['retired_track_uuids'])and new_ids<=set(proof['added_native_uuids']),
  'actual_macro_complete_leaf_cut_and_additions_required')
 _,old_nodes=ast._nodes(source);_,new_nodes=ast._nodes(candidate)
 def fixed(board,ids,nodes):
  return {force._uid(i):syntax._freeze(nodes[force._uid(i)])for i in [*board.GetTracks(),*board.Zones()]
   if i.GetNetname()==net and force._uid(i)not in ids}
 _need(fixed(parent,old_ids,old_nodes)==fixed(child,new_ids,new_nodes),'fixed_force_literal_changed')
 def group(item):return force._uid(item.GetParentGroup())if item.GetParentGroup()else None
 def pads(board):
  return {force._uid(p):[force._uid(f),f.GetReference(),f.GetValue(),f.GetFPIDAsString(),bool(f.IsLocked()),group(f),
    sorted((v.GetName(),v.GetText())for v in f.GetFields()),p.GetNumber(),p.GetNetname(),list(p.GetPosition()),
    list(p.GetSize()),list(p.GetDrillSize()),list(p.GetOffset()),int(p.GetShape()),int(p.GetAttribute()),
    p.GetOrientationDegrees(),list(p.GetLayerSet().CuStack()),bool(p.IsLocked()),group(p)]
   for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==net and force._uid(p)!=pad}
 _need(pads(parent)==pads(child),'fixed_force_or_peer_land_changed')
 def pickup(board,q):
  t=next(t for t in board.GetTracks()if force._uid(t)==q['track_uuids'][-1])
  return [t.GetNetname(),int(t.GetLayer()),t.GetWidth(),sorted([list(t.GetStart()),list(t.GetEnd())]),
   bool(t.IsLocked()),group(t),bool(t.HasSolderMask())]
 _need(pickup(parent,a)==pickup(child,b),'actual_pickup_native_kernel_changed')
 key=next((r['input_ref'],r['leg'],r['net'])for r in before['inner_departure']['details']if r['sense_terminal']['uuid']==pad)
 def moved_descriptor(board):
  actual=[p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==pad]
  _need(len(actual)==1,'unique_actual_whole_leaf_input_land_required')
  p=actual[0];fp=p.GetParentFootprint()
  _need(p.GetClass()=='PAD'and p.GetNetname()==net and fp.GetReference()==a['owner']
   and p.GetNumber()==a['pin'],'actual_whole_leaf_input_descriptor_binding_changed')
  return dict(kind='PAD',uuid=pad,net=p.GetNetname(),footprint_uuid=force._uid(fp),
   ref=fp.GetReference(),pad=p.GetNumber(),position_nm=list(p.GetPosition()))
 first_descriptor,last_descriptor=moved_descriptor(parent),moved_descriptor(child)
 _need({k:v for k,v in first_descriptor.items()if k!='position_nm'}==
  {k:v for k,v in last_descriptor.items()if k!='position_nm'},'whole_leaf_input_land_identity_changed')
 absolute=[sense.admit_changed_net(v,v,net,input_legs=[key[:2]])for v in(before,after)]
 peers=[(r['input_ref'],r['leg'],r['net'])for r in before['inner_departure']['details']if r['net']==net and r['sense_terminal']['uuid']!=pad]
 peer_ids=[r['sense_terminal']['uuid']for r in before['inner_departure']['details']if (r['input_ref'],r['leg'],r['net'])in peers]
 first_query=_fixed_native_query(parent,net,old_ids|{pad},peer_ids,deadline=deadline)
 last_query=_fixed_native_query(child,net,new_ids|{pad},peer_ids,deadline=deadline)
 _need(first_query==last_query,'actual_fixed_native_query_inventory_or_peer_component_changed')
 _need(time.monotonic()<deadline,'whole_leaf_deadline')
 return dict(leg=key,pad=pad,old_ids=a['track_uuids'],new_ids=b['track_uuids'],
  old_path=list(reversed(a['track_uuids']))+[pad],new_path=list(reversed(b['track_uuids']))+[pad],
  before_position=a['points_nm'][0],after_position=b['points_nm'][0],peers=peers,
  moved_land_descriptor_before=first_descriptor,moved_land_descriptor_after=last_descriptor,
  absolute_before=absolute[0],absolute_after=absolute[1],fresh_macro_received=True,
  fixed_force_literal_equal=True,fixed_lands_equal=True,same_pickup_kernel=True,exact_owned_inventory=True,
  peer_component_equal=first_query==last_query,fixed_native_query_before=first_query,fixed_native_query_after=last_query,
  source_live=True,policy_equal=before['geometry_policy']==after['geometry_policy'])

def _reconcile_owned_leaf(before,after,context,*,whole_leaf_mode=False,deadline=None):
 """Pure comparison projection; context is private native wrapper output.

 Synthetic tests of this helper are not saved/native receiving. Raw inputs
 are immutable and the result enumerates each comparison-only edit.
 """
 _need(type(whole_leaf_mode)is bool,'explicit_whole_leaf_mode_required')
 if not whole_leaf_mode:return copy.deepcopy(after),[]
 deadline=time.monotonic()+10. if deadline is None else deadline
 _need(time.monotonic()<deadline,'whole_leaf_deadline')
 required=('fresh_macro_received','fixed_force_literal_equal','fixed_lands_equal',
  'same_pickup_kernel','exact_owned_inventory','peer_component_equal','source_live','policy_equal')
 _need(all(context.get(k)is True for k in required),'independent_whole_leaf_precondition_required')
 _need(before['geometry_policy']==after['geometry_policy'],'whole_leaf_cut_policy_changed')
 _need(context['absolute_before']['ok']is True and context['absolute_after']['ok']is True,
  'whole_leaf_explicit_before_after_absolute_required')
 key=tuple(context['leg']);old_ids=set(context['old_ids']);new_ids=set(context['new_ids']);pad=context['pad']
 _need(old_ids and new_ids and not old_ids&new_ids and len(old_ids)<=16 and len(new_ids)<=16,
  'exact_disjoint_owned_leaf_inventory_required')
 _need(context['old_path']==list(reversed(context['old_ids']))+[pad]
  and context['new_path']==list(reversed(context['new_ids']))+[pad],'exact_whole_leaf_path_required')
 adjusted=copy.deepcopy(after);edits=[]
 def row(report,category,k):
  matches=[r for r in report[category]['details']if tuple(r[n]for n in('input_ref','leg','net'))==k]
  _need(len(matches)==1,'unique_whole_leaf_input_row_required');return matches[0]
 a=row(before,'inner_departure',key);b=row(adjusted,'inner_departure',key)
 _need(a['ok']is True and b['ok']is True,'whole_leaf_leg_must_remain_positive')
 _need(len(a['native']['departures'])==len(b['native']['departures'])==1
  and not a['native']['issues']and not b['native']['issues'],'one_inward_whole_leaf_departure_required')
 x,y=a['native']['departures'][0],b['native']['departures'][0]
 variable={'uuid','input_contact_paths'}
 _need({k:v for k,v in x.items()if k not in variable}=={k:v for k,v in y.items()if k not in variable},
  'whole_leaf_pickup_geometry_or_reachability_changed')
 _need(x['uuid']==context['old_ids'][-1]and y['uuid']==context['new_ids'][-1]
  and x['input_contact_paths']=={pad:context['old_path']}and y['input_contact_paths']=={pad:context['new_path']},
  'whole_leaf_actual_departure_path_required')
 y['uuid']=x['uuid'];y['input_contact_paths']=copy.deepcopy(x['input_contact_paths'])
 edits.append('/inner_departure/'+repr(key)+'/native/departures/0/{uuid,input_contact_paths}')
 # A peer remains failed with no new reachable departure. Only an observed
 # geometrically identical owned pickup UUID can be reconciled.
 for peer in context['peers']:
  k=tuple(peer);left=row(before,'inner_departure',k);right=row(adjusted,'inner_departure',k)
  _need(left['ok']is False and right['ok']is False,'unfinished_peer_must_remain_failed')
  _need(not left['native']['departures']and not right['native']['departures'],
   'unfinished_peer_acquired_departure')
  for first,last in zip(left['native']['non_sense_departures'],right['native']['non_sense_departures']):
   if last['uuid']!=context['new_ids'][-1]:continue
   _need(first['uuid']==context['old_ids'][-1]and not first['reachable_input_pad_uuids']
    and not last['reachable_input_pad_uuids']and
    {k:v for k,v in first.items()if k!='uuid'}=={k:v for k,v in last.items()if k!='uuid'},
    'peer_observation_not_exact_owned_pickup')
   last['uuid']=first['uuid'];edits.append('/inner_departure/'+repr(k)+'/native/non_sense_departures/uuid')
  _need(left['native']==right['native'],'unfinished_peer_raw_state_or_geometry_changed')
 # Clip components are matched ONLY inside this positively proved leg and
 # ONLY when fixed contributors and all geometric bounds/face/edges agree.
 # No global component-index normalization or contributor erasure exists.
 def reconcile(first,last,path):
  _need(time.monotonic()<deadline,'whole_leaf_deadline')
  if type(first)is dict and type(last)is dict:
   if 'contributors'in first or 'contributors'in last:
    _need(set(first)==set(last)and {'contributors','component'}<=first.keys(),'clip_component_schema_changed')
    _need({k:v for k,v in first.items()if k not in('contributors','component')}==
     {k:v for k,v in last.items()if k not in('contributors','component')},'clip_component_geometry_changed')
    def partition(rows,ids,position,descriptor):
     _need(type(descriptor)is dict and set(descriptor)=={'kind','uuid','net','footprint_uuid','ref','pad','position_nm'}
      and descriptor['kind']=='PAD'and descriptor['uuid']==pad and descriptor['net']==key[2]
      and descriptor['ref']==key[0]and descriptor['position_nm']==position,
      'actual_native_moved_land_descriptor_required')
     fixed=[];owned=[];seen=set()
     for v in rows:
      if v['uuid']in ids:
       _need(v['uuid']not in seen,'duplicate_owned_clip_contributor')
       _need(v==dict(kind='PCB_TRACK',uuid=v['uuid'],net=key[2]),'owned_clip_contributor_changed')
       seen.add(v['uuid']);owned.append(v)
      elif v['uuid']==pad:
       _need(v['uuid']not in seen,'duplicate_owned_clip_contributor')
       _need(v==descriptor,'moved_clip_land_descriptor_not_actual')
       seen.add(v['uuid']);owned.append(v)
      else:fixed.append(v)
     return sorted(fixed,key=_literal),owned
    f,o=partition(first['contributors'],old_ids,context['before_position'],context['moved_land_descriptor_before'])
    g,p=partition(last['contributors'],new_ids,context['after_position'],context['moved_land_descriptor_after'])
    _need(f==g,'fixed_clip_contributor_changed')
    if o or p:
     _need(o and p,'owned_clip_component_membership_changed')
     # Whole owned leaf+land must be present at both ends of this component;
     # a missing one cannot be repaired by copying an older contributor list.
     _need({v['uuid']for v in o}==old_ids|{pad}and {v['uuid']for v in p}==new_ids|{pad},
      'complete_owned_clip_contributor_inventory_required')
     # A different raw component digest is justified by this component's
     # exact fixed set + verified owned replacement, not by numeric order.
     last['contributors']=copy.deepcopy(first['contributors']);last['component']=first['component']
     edits.extend([path+'/contributors',path+'/component'])
    else:_need(first==last,'unowned_clip_component_changed')
    return
   _need(set(first)==set(last),'clip_schema_changed')
   for k in first:reconcile(first[k],last[k],path+'/'+k)
  elif type(first)is list and type(last)is list:
   _need(len(first)==len(last),'clip_path_or_witness_count_changed')
   for i,(x,y)in enumerate(zip(first,last)):reconcile(x,y,path+'/'+str(i))
  # Diagnostic fields and the moved sense-terminal metadata are handled by
  # existing strict production comparators; do not rewrite other scalars.
 left=row(before,'clipped_isolation',key);right=row(adjusted,'clipped_isolation',key)
 _need(left['ok']is True and right['ok']is True,'whole_leaf_clipped_leg_must_remain_positive')
 for field in ('baseline_geometry','upper','lower'):
  reconcile(left['native'][field],right['native'][field],'/clipped_isolation/'+repr(key)+'/native/'+field)
 # Read-only work counters are not cut geometry or policy. This one counter
 # changes with the proved 5-to-7-edge inventory; enumerate its scoped edit,
 # never erase a result/status/guard or normalize another input's counter.
 if 'contacts_examined'in left['native']or 'contacts_examined'in right['native']:
  x,y=left['native'].get('contacts_examined'),right['native'].get('contacts_examined')
  _need(type(x)is int and type(y)is int and 0<=x<=262144 and 0<=y<=262144,'bounded_native_contact_work_counter_required')
  if x!=y:
   right['native']['contacts_examined']=x
   edits.append('/clipped_isolation/'+repr(key)+'/native/contacts_examined')
 _need(before['geometry_policy']==adjusted['geometry_policy'],'comparison_policy_changed')
 return adjusted,edits




def requests(values):
    import re
    _need(type(values) in (list,tuple) and len(values)<=4
        and all(type(p)is str and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',p)for p in values)
        and len(set(values))==len(values),'literal_bounded_whole_leaf_pad_identities_required')
    return tuple(values)


def reconcile_received_whole_leaves(parent,child,before,after,proof,bindings,pad_uuids,*,deadline):
    """Internal only: derive every context; never accept a caller context."""
    import hashlib
    pads=requests(pad_uuids)
    adjusted=copy.deepcopy(after);observations=[];nets=set()
    old_raw=_literal(before);new_raw=_literal(after)
    claims=proof.get('source_macro_packet',{}).get('source_plan',{}).get('measurement_leaves',())
    for pad in pads:
        _need(time.monotonic()<deadline,'whole_leaf_deadline')
        _need(pad in bindings,'whole_leaf_actual_moved_input_binding_required')
        binding=bindings[pad]
        matching=[q for q in claims if q.get('pad_uuid')==pad]
        _need(len(matching)==1 and matching[0]['owner']==binding['ref']
            and matching[0]['net']==binding['net']
            and matching[0]['points_nm'][0]==binding['before']
            and binding['before']!=binding['after']
            and binding['ref'] in proof.get('moved_refs',()),
            'whole_leaf_claimed_Source_owner_or_moved_land_changed')
        _need(binding['net']not in nets,'one_requested_whole_leaf_per_authored_net_required')
        nets.add(binding['net'])
        context=_derive_context(parent,child,before,after,proof,pad,deadline=deadline)
        _need(context['pad']==pad and context['before_position']==binding['before']
            and context['after_position']==binding['after'],'whole_leaf_live_land_frame_changed')
        projected,edits=_reconcile_owned_leaf(before,adjusted,context,whole_leaf_mode=True,deadline=deadline)
        adjusted=projected
        observations.append(dict(pad_uuid=pad,net=binding['net'],basis='Source_owned_whole_leaf_leg_level_rebind',
            fresh_physical_context=context,edited_comparison_paths=edits,
            raw_before_after_absolute=[context['absolute_before'],context['absolute_after']],
            peer_raw_failure_preserved=True,newly_completed_input=False,
            raw_reports_unchanged=True,current_qualified=False,full_kelvin_qualification=False,
            release_authority=False))
    _need(_literal(before)==old_raw and _literal(after)==new_raw,'raw_whole_leaf_reports_mutated')
    _final_bindings(parent.GetFileName(),child.GetFileName(),before,after,deadline=deadline)
    return adjusted,observations
