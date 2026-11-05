"""Independently receive one joint plated-bank and full-load force preclear.

Expected zone geometry is rebuilt from the immutable SOURCE. Native actual
incoming conductors are received at the unchanged whole force load and source
width. All untouched objects and deterministic fills must replay exactly.
No barrel ampacity, shared current, thermal or release qualification is granted.
"""
import argparse
import json
import tempfile
import time
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet = wx.LogNull()
import pcbnew
import cec_force_current as force
import cec_force_crossface_receiving as crossface
import cec_additive_route_receiving as additive
import cec_ordinary_route_receiving as ordinary
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_sense_evidence as sense
import cec_native_supply_via_context as web
import cec_rectilinear_copper as copper
import cec_native_fill_geometry as native_fill
import cec_zone_fill as zone_fill
import cec_route_quality as quality
from root_native_pth_bank_with_rated_preclear_20261013 import force_plan


def receive(source,candidate,scope,*,board_hint):
    r=dict(schema=1,ok=False,complete=False,errors=[],scope='exact_joint_native_pth_bank_force_preclear',
        source_current_reduced=False,branch_sharing_assumed=False,barrel_ampacity_qualified=False,
        coupled_thermal_qualified=False,fab_ready=False,release_authority=False)
    try:
        if (type(scope) is not dict or set(scope)!={'source_zone_uuid','target_layer',
                'enclosure_margin_nm','retired_track_uuids'}):
            raise ValueError('exact_joint_native_bank_scope_required')
        margin=scope['enclosure_margin_nm']
        if type(margin) is not int or not 0<=margin<=100000:
            raise ValueError('bounded_actual_bank_construction_margin_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        net,cut,incoming,ownership=crossface.native_scope(parent,child,scope['retired_track_uuids'])
        plan=force_plan(parent,paths[0],board_hint,scope['retired_track_uuids'])
        contract=plan['contracts'][net];source_width=max(q.GetWidth() for q in cut)
        for item in incoming:
            if item.GetClass()=='PCB_TRACK':
                crossface.require_track_floor(parent,item,contract,source_width)
        bank=next(z for z in parent.Zones() if force._uid(z)==scope['source_zone_uuid'])
        old_face,target=bank.GetLayer(),parent.GetLayerID(scope['target_layer'])
        if (bank.GetIsRuleArea() or not bank.IsFilled() or bank.GetParentGroup() is not None
                or len(bank.GetLayerSet().CuStack())!=1
                or {old_face,target}!={pcbnew.F_Cu,pcbnew.B_Cu} or bank.GetNetname()==net):
            raise ValueError('ungrouped_known_source_bank_and_opposite_outer_face_required')
        shape=bank.GetFilledPolysList(old_face).CloneDropTriangulation()
        native_fill.identity(shape,time.monotonic()+9.5)
        contacts=[q for q in [*parent.GetTracks(),*(p for fp in parent.GetFootprints() for p in fp.Pads())]
            if q.GetNetCode()==bank.GetNetCode() and q.IsOnLayer(old_face)
            and shape.Collide(q.GetEffectiveShape(old_face),0)]
        if not 2<=len(contacts)<=32 or any(q.GetClass()!='PAD'
                or q.GetAttribute()!=pcbnew.PAD_ATTRIB_PTH or not q.HasHole()
                or not q.IsOnLayer(target) for q in contacts):
            raise ValueError('all_actual_source_bank_contacts_must_be_plated_target_pins')
        with force._thermal_hint(board_hint):
            before_domains=topology.board_current_domains(parent,board_hint)
            after_domains=topology.board_current_domains(child,board_hint)
            before_widths=topology.route_width_contracts(parent,board_hint)
            after_widths=topology.route_width_contracts(child,board_hint)
        for name in (net,str(bank.GetNetname())):
            if (not before_domains[name]['complete'] or before_domains[name]!=after_domains[name]
                    or before_widths[name]!=after_widths[name]
                    or before_widths[name]['required_by_layer_mm']['F.Cu']
                        !=before_widths[name]['required_by_layer_mm']['B.Cu']):
                raise ValueError('unchanged_complete_current_domains_and_outer_widths_required')
        root,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        retired=set(scope['retired_track_uuids']);added={force._uid(q) for q in incoming}
        if old.keys()-new.keys()!=retired or new.keys()-old.keys()!=added:
            raise ValueError('exact_cut_and_only_same_net_incoming_native_inventory_required')
        if (force._preservation_snapshot(paths[0])[1]!=force._preservation_snapshot(paths[1])[1]
                or force._sidecars(paths[0])!=force._sidecars(paths[1])):
            raise ValueError('joint_source_metadata_or_sidecars_changed')
        with tempfile.TemporaryDirectory(prefix='cec-joint-native-bank-replay-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'family')
            rebuilt_root=[root[0],*[node for node in root[1:] if not (isinstance(node,list)
                and next((str(x[1]).strip('"') for x in node if isinstance(x,list)
                    and len(x)>1 and x[0]=='uuid'),None) in retired)],
                *[new[u] for u in sorted(added)]]
            expected.write_text(additive._render(rebuilt_root)+'\n')
            rebuilt=pcbnew.LoadBoard(str(expected));rebuilt.SetFileName(str(expected))
            owned=next(z for z in rebuilt.Zones() if force._uid(z)==scope['source_zone_uuid'])
            if margin:
                outer=copper.purposeful_envelope(shape,style='chamfer45',margin_nm=margin,grid_nm=1000)
                owned.Outline().RemoveAllContours();owned.Outline().NewOutline()
                for x,y in outer:owned.Outline().Append(x,y)
            copper._require_unoccupied_outline(rebuilt,owned.Outline(),owned.GetNetname(),target,
                time.monotonic()+9.5,clearance_nm=max(owned.GetLocalClearance(),rebuilt.GetDesignSettings().m_MinClearance),
                allow_native_hole_bridges=True)
            owned.UnFill();owned.SetLayer(target)
            batch=pcbnew.ZONES();batch.append(owned)
            zone_fill.compile_selected(rebuilt,batch,initialize_selected=True)
            missing=shape.CloneDropTriangulation();missing.BooleanSubtract(owned.GetFilledPolysList(target))
            if missing.OutlineCount():raise ValueError('actual_source_bank_copper_lost_on_target_face')
            additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,expected)
            _,actual=additive._nodes(expected)
            if actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('exact_source_bank_source_minus_cut_and_native_ground_replay_differs')
        boundaries=ordinary._boundaries(parent,child,cut,time.monotonic()+9.5)
        if any(not q['restored'] for q in boundaries):
            raise ValueError('all_original_native_branch_boundaries_must_be_restored')
        parts=ordinary._partition(parent,time.monotonic()+9.5,retired_uuids=retired)
        updated=ordinary._partition(child,time.monotonic()+9.5,retained_keys=set().union(*parts))
        if not all(any(q<=v for v in updated) for q in parts):
            raise ValueError('retained_source_native_material_partition_lost')
        strict_web=dict(contract,required_by_layer_mm={k:max(v,source_width/1e6)
            for k,v in contract['required_by_layer_mm'].items()})
        webs=[web.receive(child,force._uid(q),strict_web,timeout_s=2.)
            for q in incoming if q.GetClass()=='PCB_VIA']
        if len(webs)>4 or not all(q['ok'] and q['complete'] for q in webs):
            raise ValueError('complete_actual_two_face_authored_source_webs_required')
        debt=current.receive(*paths,board_hint=board_hint)
        if not debt['ok'] or not debt['complete']:raise ValueError('new_or_worse_current_debt_refused')
        craft=quality.analyze_board(child,track_uuid_scope=added)
        if not craft['geometry_ok'] or not craft['craft_ok']:
            raise ValueError('incoming_canonical_branch_craft_required:'+str(craft))
        with force._thermal_hint(board_hint):
            delta=sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                -field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        if delta:raise ValueError('new_field_blockers_refused')
        first,last=[sense.replay(p,board_hint=board_hint,timeout_s=10.) for p in paths]
        kelvin=sense.compare_contour_preservation(first,last,modified_nets=[net,str(bank.GetNetname())],
            native_copper_transforms=crossface.count_manifest(net,retired,incoming))
        if not kelvin['comparison_complete'] or not kelvin['same_evidence']:
            raise ValueError('absolute_changed_cuts_and_exact_unaffected_evidence_required')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('source_candidate_or_code_changed_during_joint_native_receiving')
        r.update(ok=True,complete=True,source=str(paths[0]),candidate=str(paths[1]),
            source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            code_identity=epoch,source_candidate_and_code_unchanged=True,exact_native_reconstruction=True,
            actual_complete_source_bank_enclosed_on_equal_outer_face=True,
            source_current_domain=plan['source_domain'],current_debt_receiving=debt,
            native_cut_ownership=ownership,native_boundaries_restored=boundaries,
            retained_native_partitions_preserved=True,actual_source_width_webs=webs,
            physical_kelvin_preservation=kelvin,incoming_craft=craft,new_field_blockers=[],
            full_uncapped_fifty_checks_stack_and_outline_receiving_still_required=True)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--construction',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--hint',required=True)
    a=p.parse_args();assert not a.out.exists()
    c=json.loads(a.construction.read_text())
    assert not c['errors'] and force._hash(c['source'])==c['source_sha256']
    assert force._hash(c['candidate'])==c['candidate_sha256']
    scope=dict(source_zone_uuid=c['reflowed_zone_uuid'],target_layer=c['target_layer'],
        enclosure_margin_nm=c['source_bank_enclosure_margin_nm'],retired_track_uuids=c['retired_track_uuids'])
    r=receive(c['source'],c['candidate'],scope,board_hint=a.hint)
    force._write(a.out,r)
    print(json.dumps(dict(receipt=str(a.out),ok=r['ok'],complete=r['complete'],errors=r['errors'])),flush=True)


if __name__=='__main__':main()
