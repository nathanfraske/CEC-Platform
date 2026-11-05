"""Prune fixed surface craft faults before searching other copper layers.

This is a plan-local, proposal-only filter. An alternate middle layer cannot
repair an immutable pad-side turn. Every complete packet and saved board
still owes independent craft, field, current, contact and native receiving.
No Source coordinate is snapped, moved or assigned a new conductor rating.
"""
import copy
import math
import time
import pcbnew
import cec_copper_reuse as reuse
import cec_route_quality as craft


class SurfaceLaunch:
    def __init__(self,board,net,*,deadline):
        if (type(net)is not str or not net or board.GetNetcodeFromNetname(net)<=0
                or type(deadline)not in(int,float)or not math.isfinite(deadline)):
            raise ValueError('explicit_bounded_surface_launch_context_required')
        self.board=board;self.net=net;self.deadline=deadline
        self.inventory=reuse.RetainedCopper(reuse.native_inventory(board))
        self.cache={};self.assessed=0;self.reused=0;self.refused=0;self.unknown=0;self.details=[]

    def assess(self,legs,layer):
        self.assessed+=1
        result=dict(ok=False,complete=False,scope='fixed_surface_column_launch_craft',
            board_mutated=False,current_authority=False,routing_admitted=False,
            release_authority=False,no_path_proof=False)
        try:
            if (type(layer)is not int or layer not in tuple(map(int,self.board.GetEnabledLayers().CuStack()))
                    or type(legs)not in(list,tuple)or len(legs)>128):
                raise ValueError('bounded_literal_surface_launch_required')
            packed=[]
            for a,b,w in legs:
                a,b=tuple(a),tuple(b)
                if (len(a)!=2 or len(b)!=2 or any(type(v)is not int for v in (*a,*b))
                        or type(w)is not int or w<=0 or a==b):
                    raise ValueError('exact_native_surface_launch_geometry_required')
                packed.append((a,b,w))
            if time.monotonic()>=self.deadline:raise ValueError('surface_launch_deadline')
            key=(layer,tuple(packed))
            if key in self.cache:
                self.reused+=1;return copy.deepcopy(self.cache[key])
            # Exact retained-capsule reuse only. Near-collinear aliases are
            # NOT snapped onto Source or declared covered by proximity.
            ops=[('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),w,layer)for a,b,w in packed]
            ops,material=reuse.normalize_native_ops(self.board,ops,self.net,inventory=self.inventory)
            tracks=[dict(net=self.net,layer=int(o[4]),start_nm=list(o[1]),end_nm=list(o[2]),width_nm=int(o[3]))for o in ops]
            proof=craft.assess_proposed_route(self.board,tracks,
                deadline=min(self.deadline,time.monotonic()+.25))if tracks else dict(ok=True,complete=True,issues=[])
            result.update(ok=proof.get('ok')is True and proof.get('complete')is True,
                complete=proof.get('complete')is True,material=material,craft=proof)
            if result['complete']and len(self.cache)<256:self.cache[key]=copy.deepcopy(result)
            if not result['complete']:self.unknown+=1
            elif not result['ok']:self.refused+=1
            if not result['ok']and len(self.details)<12:
                self.details.append(dict(layer=layer,legs_nm=packed,proof=copy.deepcopy(result)))
        except (ValueError,TypeError,RuntimeError,AttributeError)as exc:
            result['error']=type(exc).__name__+':'+str(exc);self.unknown+=1
        return result

    def report(self):
        return dict(scope='plan_local_fixed_surface_launch_pruning',assessed=self.assessed,
            exact_same_plan_reuses=self.reused,refused=self.refused,unknown=self.unknown,
            details=self.details,other_layer_search_can_never_waive_surface_faults=True,
            complete_packet_and_saved_board_receiving_still_required=True,
            source_geometry_changed=False,no_path_proof=False,current_authority=False,release_authority=False)
