"""Native DC load-backbone roles, not net-wide sensing/EMC exemptions.

An aggregate rail and its high-impedance sensing departures can share a net.
Only a wide retained straight conductor on a positively declared, physically
connected source-to-load backbone loses a NAME-ONLY sensitive-signal role.
Real filled zone islands can connect that backbone, but every layer and
disconnected island is a separate node. Zone UUIDs, outlines and projected
overlap never establish electrical continuity; holes remain actual voids.
Thin branches, dangling copper, explicit sensitive classes, switching/fast
roles and unknown geometry retain their original field obligations. No
current, Kelvin, shielding, clearance or release qualification is granted.
"""
import math
import time

import pcbnew


def _backbone(adjacency, sources, sinks, tick):
    """Block-cut tree: exclude pendant branches, including pendant cycles."""
    discovered={};low={};edges=[];blocks=[]
    def visit(vertex, parent=None):
        tick();discovered[vertex]=low[vertex]=len(discovered)
        for peer in sorted(adjacency[vertex]):
            tick()
            if peer==parent:continue
            if peer not in discovered:
                edges.append((vertex,peer));visit(peer,vertex)
                low[vertex]=min(low[vertex],low[peer])
                if low[peer]>=discovered[vertex]:
                    block=set()
                    while edges:
                        edge=edges.pop();block.update(edge)
                        if edge==(vertex,peer):break
                    blocks.append(block)
            elif discovered[peer]<discovered[vertex]:
                edges.append((vertex,peer));low[vertex]=min(low[vertex],discovered[peer])
    for vertex in sorted(adjacency):
        if vertex not in discovered:
            visit(vertex)
            if not adjacency[vertex]:blocks.append({vertex})
    membership={vertex:[] for vertex in adjacency};tree={}
    for index,block in enumerate(blocks):
        key=('block',index);tree[key]=set()
        for vertex in block:membership[vertex].append(key)
    for vertex,keys in membership.items():
        if len(keys)<2:continue
        key=('joint',vertex);tree[key]=set(keys)
        for other in keys:tree[other].add(key)
    def terminal(vertex):
        keys=membership[vertex]
        return ('joint',vertex) if len(keys)>1 else keys[0]
    material=set();witnesses=[]
    for source in sorted(sources):
        tick();start=terminal(source);parents={start:None};pending=[start]
        for key in pending:
            tick()
            for other in sorted(tree[key]):
                if other not in parents:parents[other]=key;pending.append(other)
        for sink in sorted(sinks):
            end=terminal(sink)
            if end not in parents:continue
            path=[];key=end
            while key is not None:
                path.append(key)
                if key[0]=='block':material.update(blocks[key[1]])
                else:material.add(key[1])
                key=parents[key]
            witnesses.append(dict(source_uuid=source,sink_uuid=sink,
                block_count=sum(key[0]=='block' for key in path)))
    return material,witnesses


class NativeFieldRoles:
    def __init__(self,board,*,board_hint=None,netclass_resolver=None,deadline=None):
        from cec_field_coupling import classify_net
        import cec_current_topology as topology
        self.typed={};self.evidence=[];self.refusals=[]
        resolve=netclass_resolver or (lambda _net:None)
        candidate_nets=set()
        for item in board.GetTracks():
            if item.GetClass()!='PCB_TRACK' or item.GetWidth()<500000:continue
            role=classify_net(item.GetNetname(),netclass=resolve(item.GetNetname()))
            if (role['victim'] and not role['aggressor']
                    and role['reasons'] and all(reason.startswith('sensitive:')
                        for reason in role['reasons'])):
                candidate_nets.add(str(item.GetNetname()))
        if not candidate_nets:return
        limit=time.monotonic()+2. if deadline is None else deadline
        def tick():
            if time.monotonic()>=limit:raise ValueError('native_field_backbone_deadline')
        try:
            tick();domains=topology.board_current_domains(board,board_hint=board_hint)
        except Exception as exc:
            self.refusals.append(dict(reason=type(exc).__name__+':'+str(exc)));return
        for net in sorted(candidate_nets):
            try:
                tick();domain=domains.get(net) or {}
                if (domain.get('complete') is not True or type(domain.get('amps')) not in (int,float)
                        or not math.isfinite(domain['amps']) or domain['amps']<=0):
                    raise ValueError('positive_complete_aggregate_current_domain_required')
                sources=set(domain.get('source_refs') or ());sinks=set(domain.get('sink_refs') or ())
                if not sources or not sinks or sources&sinks:
                    raise ValueError('distinct_declared_source_and_load_roles_required')
                material=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
                material.extend(t for t in board.GetTracks() if t.GetNetname()==net)
                if not 2<=len(material)<=512:raise ValueError('native_field_backbone_item_bound')
                native={str(i.m_Uuid.AsString()):i for i in material}
                if len(native)!=len(material):raise ValueError('ambiguous_native_field_identity')
                source_ids=set();sink_ids=set();geometry={};zone_nodes=[];vertices=0
                copper=set(map(int,board.GetEnabledLayers().CuStack()))
                for uid,item in native.items():
                    tick();kind=item.GetClass()
                    if kind=='PAD':
                        if (item.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
                                pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)
                                or item.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)):
                            raise ValueError('unsupported_native_force_land')
                        owner=item.GetParentFootprint()
                        if owner.IsDNP():raise ValueError('dnp_force_terminal_unknown')
                        ref=owner.GetReference()
                        if ref in sources:source_ids.add(uid)
                        if ref in sinks:sink_ids.add(uid)
                        if ref in sources|sinks:
                            import cec_device_power_roles as roles
                            model=roles.footprint_contract(owner)
                            if model and model['pins'].get(item.GetNumber()) in (
                                    'measurement','reference','signal_input','signal_output','control'):
                                raise ValueError('nonload_manufacturer_pin_cannot_be_force_authority')
                    elif kind=='PCB_VIA':
                        if (item.GetViaType()!=pcbnew.VIATYPE_THROUGH or item.TopLayer()!=pcbnew.F_Cu
                                or item.BottomLayer()!=pcbnew.B_Cu):
                            raise ValueError('unsupported_native_force_barrel')
                    elif kind!='PCB_TRACK':raise ValueError('unsupported_native_force_copper')
                    geometry[uid]={layer:item.GetEffectiveShape(layer) for layer in
                        copper.intersection(map(int,item.GetLayerSet().CuStack()))
                        if kind=='PCB_TRACK' or item.FlashLayer(layer)}
                zones=[z for z in board.Zones() if z.GetNetname()==net and not z.GetIsRuleArea()]
                if len(zones)>64:raise ValueError('native_field_backbone_zone_bound')
                seen_zones=set()
                for zone in zones:
                    tick();zone_uid=str(zone.m_Uuid.AsString())
                    if zone_uid in seen_zones or zone_uid in native:
                        raise ValueError('ambiguous_native_field_zone_identity')
                    seen_zones.add(zone_uid)
                    if not zone.IsFilled():raise ValueError('native_field_zone_fill_unknown')
                    for layer in copper.intersection(map(int,zone.GetLayerSet().CuStack())):
                        tick()
                        if not zone.HasFilledPolysForLayer(layer):
                            raise ValueError('native_field_zone_face_fill_unknown')
                        filled=zone.GetFilledPolysList(layer)
                        for index in range(filled.OutlineCount()):
                            tick()
                            # Native UnitSet retains this actual outer ring and
                            # its holes. No polygon conversion, convex hull,
                            # float buffer or same-owner island collapsing.
                            island=filled.UnitSet(index)
                            if island.OutlineCount()!=1:
                                raise ValueError('native_field_zone_island_unknown')
                            for ring in [island.Outline(0),*[island.Hole(0,j)
                                    for j in range(island.HoleCount(0))]]:
                                tick();vertices+=ring.PointCount()
                                if ring.ArcCount() or ring.PointCount()<3 or vertices>200000:
                                    raise ValueError('native_field_zone_geometry_bound')
                            key='zone:'+zone_uid+':'+str(layer)+':'+str(index)
                            if key in geometry:raise ValueError('ambiguous_native_field_island_identity')
                            geometry[key]={layer:island}
                            zone_nodes.append(dict(node=key,zone_uuid=zone_uid,layer_id=layer,
                                filled_island_index=index,holes=island.HoleCount(0)))
                            if len(geometry)>512:
                                raise ValueError('native_field_backbone_item_bound')
                if not source_ids or not sink_ids or len(source_ids)*len(sink_ids)>4096:
                    raise ValueError('native_declared_force_terminals_absent_or_unbounded')
                adjacency={uid:set() for uid in geometry};ids=sorted(geometry)
                boxes={uid:{layer:shape.BBox() for layer,shape in shapes.items()}
                    for uid,shapes in geometry.items()}
                for index,left in enumerate(ids):
                    tick()
                    for right in ids[index+1:]:
                        tick()
                        if any(boxes[left][layer].Intersects(boxes[right][layer])
                                and geometry[left][layer].Collide(geometry[right][layer],0)
                                for layer in geometry[left].keys()&geometry[right].keys()):
                            adjacency[left].add(right);adjacency[right].add(left)
                core,witnesses=_backbone(adjacency,source_ids,sink_ids,tick)
                if not witnesses:raise ValueError('no_actual_native_source_to_load_backbone')
                selected=sorted(uid for uid in core if uid in native and native[uid].GetClass()=='PCB_TRACK'
                    and native[uid].GetWidth()>=500000)
                if zone_nodes:
                    # A filled zone can overlap a trunk AND the root of a
                    # pendant spur. A primitive-level graph then has a tiny
                    # triangle at that root, not proof that the spur's free
                    # end is a load path. Keep such a route sensitive unless
                    # both real full-width endcaps contact other core copper.
                    def supported_ends(uid):
                        item=native[uid];layer=int(item.GetLayer())
                        for at in (item.GetStart(),item.GetEnd()):
                            tick();cap=pcbnew.SHAPE_SEGMENT(at,at,item.GetWidth())
                            if not any(layer in geometry[other]
                                    and boxes[other][layer].Intersects(cap.BBox())
                                    and geometry[other][layer].Collide(cap,0)
                                    for other in core if other!=uid):
                                return False
                        return True
                    selected=[uid for uid in selected if supported_ends(uid)]
                proof=dict(net=net,track_uuids=selected,source_refs=sorted(sources),sink_refs=sorted(sinks),
                    native_source_load_paths=witnesses,connected_zone_islands_not_collapsed=True,
                    actual_native_zone_islands=zone_nodes,
                    native_zone_geometry_vertices=vertices,
                    inherited_current_or_kelvin_debt_qualified=False,release_authority=False)
                self.evidence.append(proof)
                for uid in selected:self.typed[uid]=proof
            except Exception as exc:
                self.refusals.append(dict(net=net,reason=type(exc).__name__+':'+str(exc)))

    def role(self,item,baseline):
        uid=str(item.m_Uuid.AsString())
        if uid not in self.typed:return baseline
        return dict(baseline,victim=False,power=True,
            reasons=[*baseline['reasons'],'native_declared_DC_load_backbone_not_measurement_branch'])

    def report(self):
        return dict(scope='native_per_conductor_field_role_not_EMC_signoff',
            classified_force_track_count=len(self.typed),proofs=self.evidence,refusals=self.refusals,
            thin_and_unproved_branches_remain_sensitive=True,
            current_kelvin_clearance_and_shielding_authority=False,release_authority=False)
