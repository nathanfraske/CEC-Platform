"""Use actual mask artwork during chart/rear-reference seat discovery.

The frozen annotation owner is loaded into a private module namespace, so no
global monkey-patch can affect another worker. Only its obstacle provider is
extended. Its exact reconstruction, second-save, ownership and rule gates are
retained. The independent mask preflight and native DRC remain mandatory.
"""
from pathlib import Path
import copy
import time
import types
from shapely.ops import unary_union
import cec_dense_reference_mapping as original
import cec_reference_mask_obstacles as masks
import cec_force_current as force
import cec_rectangular_field_silk_clearance as ink

POLICY = 'native-mask-artwork-in-chart-and-reverse-reference-seat-search-v1'
require = original.require
_source_path = Path(original.__file__).resolve()
_source_hash = force._hash(_source_path)
_private = types.ModuleType('_cec_private_mask_search_reference_owner')
_private.__file__ = str(_source_path)
exec(compile(_source_path.read_text(), str(_source_path), 'exec'), _private.__dict__)
_old_obstacles, _old_plan = _private.obstacles, _private.plan


def dependencies():
    return {str(q): force._hash(q) for q in
        (Path(__file__).resolve(), _source_path, Path(masks.__file__).resolve(),Path(ink.__file__).resolve())}


def _obstacles(board, face, excluded, clearance, *, assembled_bodies,via_ink_policy='reserve_native_lands',
        reviewed_body_shapes=None,_prepared=None):
    ordinary = _old_obstacles(board, face, excluded, clearance,
        assembled_bodies=assembled_bodies,via_ink_policy=via_ink_policy,
        reviewed_body_shapes=reviewed_body_shapes,_prepared=_prepared)
    material=(_prepared.mask_artwork(board,face,masks.native_mask_artwork)if _prepared is not None
        else masks.native_mask_artwork(board,face)[0])
    if material.is_empty:
        return ordinary
    # Exactly the existing preflight margin, not an opening reduction.
    return unary_union([ordinary, material.buffer(clearance + .002, join_style=2)])


def _plan(*args, **kwargs):
    require(force._hash(_source_path) == _source_hash, 'frozen_annotation_owner_changed')
    bound = dependencies()
    proposal = _old_plan(*args, **kwargs)
    proposal['mask_search_binding'] = dict(policy=POLICY, input_sha256=bound,
        all_source_mask_artwork_in_search=True, original_annotation_gates_retained=True,
        mask_opening_or_glyph_rule_relaxed=False, native_drc_still_required=True)
    require(all(force._hash(Path(q)) == h for q, h in bound.items()),
        'mask_search_owner_changed_during_plan')
    return proposal


_private.obstacles, _private.plan = _obstacles, _plan


def plan(source, **kwargs):
    require(kwargs.get('positive_leaders_only',True)is True,
        'new_reference_construction_requires_positive_native_leaders')
    kwargs['positive_leaders_only']=True
    return _private.plan(source, **kwargs)


def replay_existing_plan(source,candidate,**kwargs):
    """Read-only versioned reconstruction of an already saved artifact.

    Retaining old rendering semantics is NOT new-construction or quality
    authority. Native warnings and every whole-board gate remain visible.
    Exact saved/native replay must pass now; old success receipts do not.
    """
    paths=[Path(p).resolve(strict=True)for p in(source,candidate)]
    require(paths[0]!=paths[1],'distinct_existing_annotation_artifact_required')
    before=[force._hash(p)for p in paths]
    q=_private.plan(paths[0],**kwargs)
    proof=receive(paths[0],paths[1],q)
    require(proof.get('ok')is True and proof.get('complete')is True,
        'existing_annotation_literal_replay_refused:'+str(proof.get('errors')))
    require(before==[force._hash(p)for p in paths],'existing_annotation_artifact_changed')
    return q


def _replay_clock():
    return time.monotonic()


def _replay_family(path):
    result={}
    for p in path.parent.rglob('*'):
        require(not p.is_symlink(),'existing_replay_family_symlink_refused')
        if p.is_file():result[str(p.relative_to(path.parent))]=force._hash(p)
    return result


class _ExistingReplay:
    """One-shot, in-process observation, never a serialized success cache.

    Planning discovers historical rendering only. Saved receiving independently
    replans and reconstructs it through the existing owner. Failed or expired
    stages cannot be resumed with a reset lease on this observation.
    """
    def __init__(self,source,candidate,options):
        self._paths=tuple(Path(p).resolve(strict=True)for p in(source,candidate))
        require(self._paths[0]!=self._paths[1],
            'distinct_existing_annotation_artifact_required')
        require(type(options.get('positive_leaders_only',False))is bool,
            'explicit_existing_replay_rendering_boolean_required')
        self._options=copy.deepcopy(options)
        self._state='new';self._proposal=None;self._identity=None;self._timings={}
        self._saved=None

    def _snapshot(self):
        grade=Path(self._options['grade']).resolve(strict=True)
        hint=self._options['board_hint']
        result=dict(paths=[str(p)for p in self._paths],
            sha256=[force._hash(p)for p in self._paths],
            families=[force._family(p,hint)for p in self._paths],
            complete_saved_families=[_replay_family(p)for p in self._paths],
            grade=dict(path=str(grade),sha256=force._hash(grade)),
            code_identity=force._code_identity(),dependencies=dependencies())
        if self._proposal is not None:
            binding=self._proposal['binding']
            result['native_report']=dict(path=binding['native_report'],
                sha256=force._hash(Path(binding['native_report'])))
            require(result['native_report']['sha256']==binding['native_report_sha256'],
                'existing_replay_native_report_changed')
        return result

    def plan(self):
        require(self._state=='new','existing_replay_plan_stage_already_consumed')
        self._state='failed';started=_replay_clock()
        try:
            before=self._snapshot()
            proposal=_private.plan(self._paths[0],**self._options)
            self._proposal=copy.deepcopy(proposal)
            after=self._snapshot()
            require(before=={k:v for k,v in after.items()if k!='native_report'},
                'existing_replay_inputs_changed_during_plan')
            self._identity=after
            require(_replay_clock()-started<10.,'existing_replay_plan_deadline')
            self._state='planned'
            return copy.deepcopy(proposal)
        finally:
            self._timings['plan']=_replay_clock()-started
            if self._state=='planned'and not self._timings['plan']<10.:
                self._state='failed'
                raise ValueError('existing_replay_plan_deadline')

    def reconstruct(self):
        require(self._state=='planned','existing_replay_fresh_plan_stage_required')
        self._state='failed';started=_replay_clock()
        try:
            require(self._snapshot()==self._identity,'existing_replay_inputs_changed_before_reconstruction')
            self._saved=saved_replay(*self._paths,self._proposal)
            result=self._saved.reconstruct()
            require(_replay_clock()-started<10.,'existing_replay_reconstruct_deadline')
            self._state='reconstructed';return result
        finally:
            self._timings['reconstruct']=_replay_clock()-started
            if self._state=='reconstructed'and not self._timings['reconstruct']<10.:
                self._state='failed'
                raise ValueError('existing_replay_reconstruct_deadline')

    def receive(self):
        require(self._state=='reconstructed','existing_replay_fresh_reconstruction_stage_required')
        self._state='failed';started=_replay_clock()
        try:
            # The same private fresh reconstruction is consumed once. No
            # discovery board, caller receipt or second combined replan.
            proof=self._saved.receive()
            require(proof.get('ok')is True and proof.get('complete')is True,
                'existing_annotation_literal_replay_refused:'+str(proof.get('errors')))
            require(self._snapshot()==self._identity,'existing_replay_inputs_changed_during_receive')
            elapsed=_replay_clock()-started
            require(elapsed<10.,'existing_replay_receive_deadline')
            self._state='received'
            return dict(proof,explicit_staged_existing_replay=dict(
                phase_timings_s=dict(self._timings,receive=elapsed),
                constituent_timeout_s=10.,identity=copy.deepcopy(self._identity),
                independent_saved_receiver_invoked=True,
                new_construction_authority=False))
        finally:
            self._timings['receive']=_replay_clock()-started
            if self._state=='received'and not self._timings['receive']<10.:
                self._state='failed'
                raise ValueError('existing_replay_receive_deadline')

    def observation(self):
        """Diagnostics only, including consumed failed-stage timings."""
        return dict(state=self._state,phase_timings_s=copy.deepcopy(self._timings),
            constituent_timeout_s=10.,identity=copy.deepcopy(self._identity),
            no_saved_verdict_or_new_construction_authority=True)


def existing_replay(source,candidate,**options):
    """Observe an existing saved map in three explicit, separately bounded stages.

    Call ``plan()``, ``reconstruct()``, then ``receive()`` once each. A returned plan is discovery,
    not saved qualification. Historical rendering remains read-only; the public
    construct/write APIs still reject nonpositive-leader plans. Each complete
    stage, including live identities, must finish strictly within ten seconds.
    """
    return _ExistingReplay(source,candidate,options)


class _SavedMaskReplay:
    def __init__(self,source,candidate,proposal,timeout_s):
        self._source=Path(source).resolve(strict=True)
        self._proposal=copy.deepcopy(proposal);self._limit=timeout_s
        owner=_private if 'mask_search_binding'in proposal else original
        self._owner=owner.saved_replay(source,candidate,proposal,timeout_s=timeout_s)
        self._deps=None;self._state='new';self._timings={}

    def _stage(self,name,required,next_state,fn):
        require(self._state==required,'saved_mask_'+name+'_stage_order_required')
        self._state='failed';started=_replay_clock()
        try:
            result=fn()
            require(_replay_clock()-started<self._limit,'saved_mask_'+name+'_deadline')
            self._state=next_state;return result
        finally:
            self._timings[name]=_replay_clock()-started
            if self._state==next_state and not self._timings[name]<self._limit:
                self._state='failed';raise ValueError('saved_mask_'+name+'_deadline')

    def reconstruct(self):
        def run():
            self._deps=dependencies();result=self._owner.reconstruct()
            require(self._deps==dependencies(),'saved_mask_owner_changed_during_reconstruction')
            return result
        return self._stage('reconstruct','new','reconstructed',run)

    def receive(self):
        def run():
            require(self._deps==dependencies(),'saved_mask_owner_changed_before_comparison')
            proof=self._owner.receive()
            if 'mask_search_binding'in self._proposal:
                witness=masks.observe(self._source,self._proposal)
                require(witness.get('ok')is True and witness.get('complete')is True,
                    'saved_mask_artwork_preflight_refused:'+str(witness.get('errors')))
                proof.update(actual_native_mask_artwork_in_search_and_replayed=True,
                    independent_mask_artwork_preflight=witness,
                    original_annotation_gates_retained=True,mask_openings_or_glyph_rules_changed=False)
            # observe is a fresh check, never permission to drift after the
            # completed native comparison or to borrow another Source family.
            require(self._owner._snapshot()==self._owner._identity,
                'saved_mask_inputs_changed_during_preflight')
            require(self._deps==dependencies(),'saved_mask_owner_changed_during_comparison')
            proof['read_only_legacy_replay']=self._proposal.get('positive_leaders_only')is not True
            return proof
        return self._stage('compare','reconstructed','received',run)

    def observation(self):
        return dict(state=self._state,phase_timings_s=copy.deepcopy(self._timings),
            constituent_timeout_s=self._limit,owner=self._owner.observation(),
            no_saved_verdict_or_new_construction_authority=True)


def saved_replay(source,candidate,proposal,*,timeout_s=10.):
    """Proposal-bound independent reconstruction then exact saved comparison."""
    return _SavedMaskReplay(source,candidate,proposal,timeout_s)


def construct(source, proposal):
    require('mask_search_binding' in proposal, 'explicit_mask_search_binding_required')
    require(proposal.get('positive_leaders_only')is True,
        'legacy_annotation_replay_cannot_construct_a_new_candidate')
    return _private.construct(source, proposal)


def receive(source, candidate, proposal):
    # Historical dense-reference phases still use their exact original owner.
    if 'mask_search_binding' not in proposal:
        return dict(original.receive(source, candidate, proposal),read_only_legacy_replay=True)
    proof = _private.receive(source, candidate, proposal)
    if proof['ok'] and proof['complete']:
        witness = masks.observe(source, proposal)
        if not (witness['ok'] and witness['complete']):
            proof.update(ok=False, complete=False, errors=witness['errors'])
        else:
            proof.update(actual_native_mask_artwork_in_search_and_replayed=True,
                independent_mask_artwork_preflight=witness,
                original_annotation_gates_retained=True,
                mask_openings_or_glyph_rules_changed=False)
    if proof.get('ok')is True:
        proof['read_only_legacy_replay']=proposal.get('positive_leaders_only')is not True
    return proof


def write_private(source,candidate,proposal):
    require('mask_search_binding'in proposal,'explicit_mask_search_binding_required')
    require(proposal.get('positive_leaders_only')is True,
        'legacy_annotation_replay_cannot_construct_a_new_candidate')
    return _private.write_private(source,candidate,proposal)


# Pure native geometry helpers used by existing review/render tooling.
for _name in ('court', 'record_items', 'chart_decoration', 'polygon'):
    globals()[_name] = getattr(original, _name)
