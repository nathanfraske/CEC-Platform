"""Protect received exclusive load/monitor scopes during nonload route search.

Same net does not imply the same current allocation. A new source-typed
divider may tap the shared bus, not silently acquire another consumer's local
supply branch. Read actual native branch geometry and its one retained tap;
do not add copper, guess current sharing, waive spacing or grant admission.
"""
import math
import time

import pcbnew
import cec_force_current as force
import cec_kelvin_copper_cut as cut
import cec_resistive_monitor_branch as monitor
import cec_supply_consumer_branch as consumer


class MonitorAccessGuard:
    def __init__(self,board,source,*,root_pad_uuid,board_hint,timeout_s=10.):
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0<timeout_s<=10 or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_positive_monitor_scope_reservation_required')
        self.board=board;self.deadline=time.monotonic()+timeout_s
        self.demand=monitor.source_contract(board,root_pad_uuid,deadline=self.deadline)
        self.net=self.demand['net'];self.native={force._uid(i):i for i in [
            *(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks(),
            *[z for z in board.Zones() if not z.GetIsRuleArea()]]}
        if len(self.native)>16384:raise ValueError('typed_leaf_native_inventory_bound')
        self.scopes=[];self.cache={};self.assessed=0;self.refused=0
        received=consumer.inventory(board,board_hint=board_hint,
            timeout_s=max(.001,self.deadline-time.monotonic()))
        if not received['complete']:raise ValueError('current_consumer_scope_inventory_required')
        for proof in received['proofs']:
            if proof['net']!=self.net:continue
            capture=proof.get('tap_capture_via_uuid') or proof['anchor_uuid']
            ids=set(proof['exact_branch_material_uuids'])|set(proof['retained_consumer_island_uuids'])
            self.scopes.append(dict(kind='source_declared_load_allocation',
                root_pad_uuid=proof['root_pad_uuid'],material=sorted(ids),capture_uuid=capture))
        # A completed typed divider is also an exclusive leaf. Preserve it
        # rather than creating an untyped shared thin trunk or an interior
        # fork. This is NOT a declaration of an aggregate monitor current.
        owners=[]
        for fp in board.GetFootprints():
            if monitor.resistor_contract(fp) is None:continue
            for pad in fp.Pads():
                if force._uid(pad)==root_pad_uuid or str(pad.GetNetname())!=self.net:continue
                owners.append(pad)
        if len(owners)>64:raise ValueError('typed_monitor_reservation_scope_bound')
        for pad in owners:
            if time.monotonic()>=self.deadline:raise ValueError('typed_leaf_reservation_deadline')
            try:q=monitor.plan(board,force._uid(pad),timeout_s=max(.001,self.deadline-time.monotonic()))
            except (ValueError,RuntimeError):continue
            boundary=q['boundary_uuids']
            captures=[u for u in boundary if self.native[u].GetClass() in ('PAD','PCB_VIA')]
            if len(captures)!=1:continue
            ids=set(q['native_removed_material_uuids'])|{force._uid(pad)}
            self.scopes.append(dict(kind='source_typed_resistive_monitor',
                root_pad_uuid=force._uid(pad),material=sorted(ids),capture_uuid=captures[0]))
        if len(self.scopes)>64 or sum(len(q['material']) for q in self.scopes)>4096:
            raise ValueError('typed_leaf_reservation_material_bound')
        for q in self.scopes:
            if q['capture_uuid'] not in self.native or not set(q['material'])<=set(self.native):
                raise ValueError('typed_leaf_reservation_native_identity_missing')
        self.complete=time.monotonic()<self.deadline
        if not self.complete:raise ValueError('typed_leaf_reservation_deadline')

    def _shape(self,item,layer):
        key=(force._uid(item),layer)
        if key not in self.cache:
            work=cut._Work(self.deadline)
            self.cache[key]=(cut._poly(item.GetFilledPolysList(layer),work)
                if item.GetClass()=='ZONE' and item.IsFilled() else cut._shape(item,layer,False,work))
        return self.cache[key]

    def __call__(self,start,end,width,layer):
        self.assessed+=1
        if (time.monotonic()>=self.deadline or type(width) is not int or width<=0
                or type(layer) is not int or layer not in self.board.GetEnabledLayers().CuStack()):
            self.complete=False;return False
        t=pcbnew.PCB_TRACK(self.board);t.SetStart(pcbnew.VECTOR2I(*start))
        t.SetEnd(pcbnew.VECTOR2I(*end));t.SetWidth(width);t.SetLayer(layer)
        t.SetNetCode(self.board.GetNetcodeFromNetname(self.net))
        shape=cut._shape(t,layer,False,cut._Work(self.deadline))
        for scope in self.scopes:
            capture=self.native[scope['capture_uuid']]
            for uid in scope['material']:
                item=self.native[uid]
                if not item.IsOnLayer(layer):continue
                overlap=shape.intersection(self._shape(item,layer))
                if overlap.is_empty:continue
                if not capture.IsOnLayer(layer) or not self._shape(capture,layer).covers(overlap):
                    self.refused+=1;return False
        return True

    def report(self):
        return dict(schema=1,complete=self.complete,net=self.net,
            source_typed_monitor_pad_uuid=self.demand['pad_uuid'],
            source_scopes=self.scopes,assessed=self.assessed,refused=self.refused,
            shared_bus_taps_only=True,board_mutated=False,current_qualified=False,
            aggregate_rail_or_consumer_load_budget_modified=False,
            admission_authority=False,release_authority=False)
