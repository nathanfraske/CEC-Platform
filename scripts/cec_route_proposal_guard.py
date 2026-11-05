"""Plan-local material, craft and field gate shared by native route builders.

This does not route, alter copper, admit a board, or certify current capacity.
Construct a new guard after any board mutation. Complete native/refilled
receiving remains authoritative; an exhausted/unknown preflight never passes.
"""
from __future__ import annotations

import math
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import pcbnew

import cec_copper_reuse as reuse
import cec_field_coupling as field
import cec_route_quality as craft


class RouteProposalGuard:
    def __init__(self, board, net, *, board_path=None,
                 netclass_resolver=None, deadline=None,memoize_exact_positive=False,
                 preflight_s=2.,board_hint=None):
        if not isinstance(net, str) or not net:
            raise ValueError('invalid_route_proposal_net')
        if deadline is not None and (
                type(deadline) not in (int, float)
                or not math.isfinite(deadline)):
            raise ValueError('invalid_route_proposal_deadline')
        self.board, self.net = board, net
        if board_hint is not None and (type(board_hint)is not str or not board_hint.strip()):
            raise ValueError('nonempty_explicit_proposal_design_identity_required')
        # A private artifact pathname is not the canonical design identity.
        # Carry the caller-bound policy lookup context without granting net,
        # current, shielding, ownership or saved-board admission authority.
        self.board_hint=board_hint
        if (type(preflight_s)not in(int,float)or not math.isfinite(preflight_s)
                or not 0<preflight_s<=10.):
            raise ValueError('bounded_explicit_proposal_preflight_lease_required')
        self.preflight_s=float(preflight_s)
        self.board_path = board_path
        self.resolver, self.deadline = netclass_resolver, deadline
        if type(memoize_exact_positive)is not bool:
            raise ValueError('explicit_plan_local_positive_preflight_reuse_required')
        if memoize_exact_positive and (not board_path or not Path(board_path).is_file()):
            raise ValueError('saved_source_context_for_positive_preflight_reuse_required')
        self.memoize_exact_positive=memoize_exact_positive
        self._positive={};self.memo_hits=0
        # Scalar, immutable native inventory. No borrowed SWIG handles survive
        # a subsequent retirement; it must not be reused after mutation.
        self.inventory = reuse.RetainedCopper(reuse.native_inventory(board))
        self.counts = dict(assessed=0, passed=0, refused=0, unknown=0)
        self.details = []
        self._last_attempt = None
        self._initial_epoch=self._memo_epoch()if memoize_exact_positive else None

    @staticmethod
    def _pack(operations):
        """Only integer manufactured geometry, no borrowed SWIG handles."""
        if len(operations)>144:raise ValueError('proposal_operation_budget')
        rows=[]
        for op in operations:
            if op[0]=='via':
                rows.append(('via',int(op[1].x),int(op[1].y),
                    pcbnew.FromMM(float(op[2])),pcbnew.FromMM(float(op[3]))))
            elif op[0]=='trk':
                rows.append(('trk',int(op[1].x),int(op[1].y),int(op[2].x),int(op[2].y),
                    int(op[3]),int(op[4])))
            else:raise ValueError('explicit_proposal_primitive_required')
        return tuple(rows)

    @staticmethod
    def _unpack(rows):
        return [('via',pcbnew.VECTOR2I(r[1],r[2]),r[3]/1e6,r[4]/1e6)if r[0]=='via'
            else('trk',pcbnew.VECTOR2I(r[1],r[2]),pcbnew.VECTOR2I(r[3],r[4]),r[5],r[6])
            for r in rows]

    def _memo_epoch(self):
        """A private plan epoch, never a saved-board admission cache.

        Full non-normalizing native serialization covers custom pads, masks,
        outlines, keepouts and filled shields, not just track coordinates.
        Bind consumed native scalar floors, effective netclasses, saved companions,
        profile, CEC context and the local Python tree as well. This small
        temporary snapshot is removed before returning; no artifact grows.
        """
        import cec_force_current as force
        import cec_fr as fr
        settings=self.board.GetDesignSettings();scalars={}
        # Only native scalar geometry floors consumed by these receivers.
        # Enumerating every m_* also constructs SWIG-owned meander/teardrop
        # proxies with no Python destructor; it is neither needed nor safe.
        for name in ('m_MinClearance','m_CopperEdgeClearance','m_HoleClearance',
                'm_HoleToHoleMin','m_ViasMinSize','m_MinThroughDrill',
                'm_ViasMinAnnularWidth','m_TrackMinWidth','m_MaxError'):
            value=getattr(settings,name,None)
            if type(value)not in(int,float,bool,str,type(None)):
                raise ValueError('native_scalar_preflight_rule_required')
            scalars[name]=value
        resolve=self.resolver or fr._project_netclass_resolver(str(self.board_path),board=self.board)
        classes={str(n):resolve(str(n))for n in self.board.GetNetsByName()}
        with field._design_identity(self.board_hint):
            profile=field.cec_fab.active_profile_name(self.board,hint=self.board_hint or str(self.board_path))
        with tempfile.TemporaryDirectory(prefix='cec-plan-positive-')as work:
            path=Path(work)/'snapshot.kicad_pcb'
            field._save_field_snapshot(self.board,path)
            board_digest=force._hash(path)
        payload=dict(net=self.net,preflight_s=self.preflight_s,board_hint=self.board_hint,
            native=board_digest,rules=scalars,netclasses=classes,
            family=force._family(self.board_path),code=force._code_identity(),
            environment={k:v for k,v in os.environ.items()if k.startswith('CEC_')},
            profile=field.cec_fab.get_profile(profile)if profile else None,
            functions=[id(field.assess_proposed_route),id(craft.assess_proposed_route)])
        return hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()

    def _finish(self, ops, evidence, status):
        self.counts[status] += 1
        # Bounded historical samples are not the latest decision. Keep the
        # actual last attempt even after the 16-row diagnostic cap is full.
        self._last_attempt = copy.deepcopy(dict(evidence,status=status))
        if len(self.details) < 16:
            self.details.append(evidence)
        return ops if status == 'passed' else None

    def last_attempt(self):
        """Actual latest scalar outcome; never an approval or a live cache."""
        return copy.deepcopy(self._last_attempt)

    def prepare(self, operations):
        """Return the exact assessed material delta, or refuse without writes."""
        self.counts['assessed'] += 1
        if self.deadline is not None and self.deadline<=time.monotonic():
            return self._finish(None, dict(reason='proposal_deadline'), 'unknown')
        try:
            key=None
            if self.memoize_exact_positive:
                if self._memo_epoch()!=self._initial_epoch:
                    return self._finish(None,dict(reason='plan_source_or_policy_epoch_changed'),'unknown')
                key=self._pack(operations)
                if key in self._positive:
                    cached=self._unpack(self._positive[key])
                    if self._memo_epoch()!=self._initial_epoch:
                        return self._finish(None,dict(reason='plan_source_or_policy_epoch_changed'),'unknown')
                    if self.deadline is not None and time.monotonic()>=self.deadline:
                        return self._finish(None,dict(reason='proposal_deadline'),'unknown')
                    self.memo_hits+=1
                    return self._finish(cached,
                        dict(reason='identical_positive_plan_preflight_reused',
                            final_saved_receiving_still_required=True),'passed')
            bound=time.monotonic()+self.preflight_s
            if self.deadline is not None:bound=min(bound,self.deadline)
            if bound<=time.monotonic():
                return self._finish(None,dict(reason='proposal_deadline'),'unknown')
            if len(operations) > 144:
                raise ValueError('proposal_operation_budget')
            ops, material = reuse.normalize_native_ops(
                self.board, operations, self.net, inventory=self.inventory)
            tracks, vias = [], []
            for op in ops:
                if op[0] == 'via':
                    vias.append(dict(net=self.net,
                        at_nm=[int(op[1].x), int(op[1].y)],
                        drill_nm=pcbnew.FromMM(float(op[2])),
                        diameter_nm=pcbnew.FromMM(float(op[3])),
                        top_layer=int(pcbnew.F_Cu), bottom_layer=int(pcbnew.B_Cu)))
                else:
                    tracks.append(dict(net=self.net, layer=int(op[4]),
                        start_nm=[int(op[1].x), int(op[1].y)],
                        end_nm=[int(op[2].x), int(op[2].y)], width_nm=int(op[3])))
            if len(tracks) > 128 or len(vias) > 16:
                raise ValueError('proposal_material_budget')
            evidence = dict(material=material, tracks=len(tracks), vias=len(vias))
            # An entirely retained path is not new material or a new join.
            # The caller must independently prove the actual target contact;
            # don't draw a duplicate just to satisfy its operation count.
            if not tracks and not vias:
                evidence['reason'] = 'no_new_route_material'
                return self._finish(None, evidence, 'refused')
            shape = craft.assess_proposed_route(self.board, tracks, deadline=bound)
            evidence['craft'] = shape
            if shape.get('complete') is not True or shape.get('ok') is not True:
                evidence['reason'] = 'route_craft_refused_or_unknown'
                return self._finish(None, evidence,
                    'refused' if shape.get('ok') is False else 'unknown')
            proof = field.assess_proposed_route(self.board, tracks,
                proposed_vias=vias, board_path=self.board_path,
                netclass_resolver=self.resolver, deadline=bound,board_hint=self.board_hint)
            evidence['field'] = proof
            if proof.get('complete') is not True or proof.get('ok') is not True:
                evidence['reason'] = proof.get('reason') or 'field_refused_or_unknown'
                return self._finish(None, evidence,
                    'refused' if proof.get('ok') is False else 'unknown')
            if self.memoize_exact_positive:
                if self._memo_epoch()!=self._initial_epoch:
                    return self._finish(None,dict(reason='plan_source_or_policy_epoch_changed'),'unknown')
                if self.deadline is not None and time.monotonic()>=self.deadline:
                    return self._finish(None,dict(reason='proposal_deadline'),'unknown')
                if len(self._positive)<8:self._positive[key]=self._pack(ops)
            return self._finish(ops, evidence, 'passed')
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            return self._finish(None, dict(reason='proposal_unknown',
                detail=str(exc)), 'unknown')

    def __call__(self, operations):
        return self.prepare(operations) is not None

    def report(self):
        return dict(schema=1, net=self.net, **self.counts, details=self.details,
            source_design_identity=self.board_hint,
            scope='plan_local_native_material_craft_and_field_preflight',
            board_mutated=False, current_qualified=False,
            inherited_debt_qualified=False, release_authority=False,
            identical_positive_plan_preflight_hits=self.memo_hits,
            per_proposal_preflight_cap_s=self.preflight_s,
            saved_native_or_whole_board_receiving_cached=False,
            no_path_proof=False)
