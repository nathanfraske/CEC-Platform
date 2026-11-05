"""Explicit Source-bound Ref-on-silk, Value/MPN-on-Fab annotation policy.

Only the declared footprint field layers may change in the original policy.
The explicit readability policy also normalizes those selected fields' mirror
state to their declared physical viewing face. Neither policy hides text,
moves glyphs, edits a footprint's graphical artwork or grants routing/fab release.
Invoke plan/construct/receive as one typed stage, then check the final assembly
and native DRC. It is deliberately opt-in rather than an inferred board rule.
"""
import math
import tempfile
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force

POLICY = 'references-silk-values-mpn-fab-v1'
READABLE_POLICY = 'references-silk-values-mpn-fab-readable-face-v2'
_ANNOTATION_LAYERS = (pcbnew.F_SilkS, pcbnew.B_SilkS, pcbnew.F_Fab, pcbnew.B_Fab)


def _literal_field_scope(node, selected, allow_mirror):
    """Normalize ONLY declared field layer/mirror and implicit stroke tokens.

    Native serialization is not authority to drop empty groups, regenerate
    body graphics or alter unrelated saved metadata. The independent native
    reconstruction still verifies their exact target native values. KiCad
    materializes an omitted default font stroke on a selected custom field;
    normalize that representation only to its SOURCE-native resolved value.
    """
    if not isinstance(node,list):return node
    uid=next((r[1].strip('"') for r in node if isinstance(r,list)
        and len(r)==2 and r[0]=='uuid'),None)
    if uid in selected:
        if not node or node[0]!='property':raise ValueError('selected_native_field_property_required')
        result=[]
        for row in node:
            if isinstance(row,list) and row and row[0]=='layer':continue
            if isinstance(row,list) and row and row[0]=='effects':
                effects=[]
                for child in row:
                    if (isinstance(child,list) and child and child[0]=='font'
                            and not any(isinstance(t,list) and t and t[0]=='thickness' for t in child)):
                        child=[*child,['thickness',str(selected[uid]['source_native_stroke_nm']/1e6)]]
                    if allow_mirror and isinstance(child,list) and child and child[0]=='justify':
                        child=[t for t in child if t!='mirror']
                        if len(child)==1:continue
                    effects.append(child)
                row=effects
            result.append(row)
        return result
    return [_literal_field_scope(child,selected,allow_mirror) for child in node]


def _settings(policy, board_hint, mpn_field_names, max_footprints, timeout_s):
    if (policy not in (POLICY, READABLE_POLICY) or type(policy) is not str
            or type(board_hint) is not str or not board_hint
            or type(mpn_field_names) not in (list, tuple)
            or not 1 <= len(mpn_field_names) <= 8
            or any(type(n) is not str or not n.strip() or n != n.strip()
                   or n in ('Reference', 'Value', 'Footprint', 'Datasheet', 'Description')
                   for n in mpn_field_names)
            or len(set(mpn_field_names)) != len(mpn_field_names)
            or type(max_footprints) is not int or not 1 <= max_footprints <= 2048
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('explicit_bounded_manufacturing_legend_policy_required')


def plan(source, *, policy, board_hint, mpn_field_names=('MPN',),
         max_footprints=2048, timeout_s=10.):
    _settings(policy, board_hint, mpn_field_names, max_footprints, timeout_s)
    started = time.monotonic()
    source = Path(source).resolve()
    epoch = force._code_identity()
    family = force._family(source, board_hint)
    board = pcbnew.LoadBoard(str(source))
    if board is None:raise ValueError('native_manufacturing_legend_source_unreadable')
    owners = sorted(board.GetFootprints(), key=force._uid)
    if not 1 <= len(owners) <= max_footprints:
        raise ValueError('manufacturing_legend_footprint_domain_exceeded')
    # Live group resolution may omit a nested footprint field. Literal saved
    # membership remains ownership and cannot silently authorize a relayer.
    _, nodes = additive._nodes(source)
    grouped = {u for node in nodes.values() if node[0] == 'group'
               for u in additive._members(node)}
    grouped.update(force._uid(i) for g in board.Groups() for i in g.GetItems())
    selected_names = {'Reference', 'Value', *mpn_field_names}
    records = []
    inspected = 0
    for fp in owners:
        if time.monotonic() - started >= timeout_s:
            raise ValueError('manufacturing_legend_source_deadline')
        fields = list(fp.GetFields())
        selected = [f for f in fields if f.GetName() in selected_names]
        names = [f.GetName() for f in selected]
        if len(set(names)) != len(names) or not {'Reference', 'Value'} <= set(names):
            raise ValueError('unique_native_reference_value_and_mpn_fields_required')
        for label in sorted(selected, key=force._uid):
            inspected += 1
            name = str(label.GetName())
            target = ((pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS)
                      if name == 'Reference' else
                      (pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab))
            old = int(label.GetLayer())
            old_mirror = bool(label.IsMirrored())
            target_mirror = (bool(fp.IsFlipped()) if policy == READABLE_POLICY else old_mirror)
            if old == target and old_mirror == target_mirror:
                continue
            if old not in _ANNOTATION_LAYERS:
                raise ValueError('copper_or_unowned_drawing_field_cannot_be_relayered')
            if label.IsLocked() or force._uid(label) in grouped:
                raise ValueError('locked_or_group_owned_field_layer_refused')
            records.append(dict(footprint_uuid=force._uid(fp), field_uuid=force._uid(label),
                field_name=name, text=str(label.GetText()), source_layer=old,
                target_layer=int(target), visible=bool(label.IsVisible()),
                source_native_stroke_nm=int(label.GetTextThickness()),
                source_mirrored=old_mirror, target_mirrored=target_mirror))
    if (time.monotonic() - started >= timeout_s or epoch != force._code_identity()
            or family != force._family(source, board_hint)):
        raise ValueError('manufacturing_legend_source_family_code_or_deadline_changed')
    mirrors_unchanged=all(r['source_mirrored']==r['target_mirrored'] for r in records)
    return dict(schema=1, scope=('source_exact_declared_field_layers_and_readable_face_only'
        if policy==READABLE_POLICY else 'source_exact_declared_field_layers_only'), policy=policy,
        source=str(source), source_sha256=force._hash(source), source_family=family,
        board_hint=board_hint, mpn_field_names=sorted(mpn_field_names),
        max_footprints=max_footprints, timeout_s=timeout_s, code_identity=epoch,
        inspected_footprints=len(owners), inspected_fields=inspected, records=records,
        strings_fonts_poses_visibility_and_other_native_evidence_unchanged=True,
        strings_fonts_poses_visibility_mirroring_and_other_native_evidence_unchanged=mirrors_unchanged,
        mirroring_unchanged=mirrors_unchanged,
        no_placement_copper_or_routing_authority=True, routing_admitted=False,
        fab_ready=False, release_authority=False)


def construct(source, proposal):
    fresh = plan(source, **{k: proposal[k] for k in (
        'policy', 'board_hint', 'mpn_field_names', 'max_footprints', 'timeout_s')})
    if fresh != proposal:
        raise ValueError('stale_or_forged_manufacturing_legend_plan')
    board = pcbnew.LoadBoard(str(source))
    labels = {force._uid(label): label for fp in board.GetFootprints() for label in fp.GetFields()}
    for row in fresh['records']:
        labels[row['field_uuid']].SetLayer(row['target_layer'])
        labels[row['field_uuid']].SetMirrored(row['target_mirrored'])
    return board


def _declared_literal(source_text,native_text,records):
    """Splice only selected layer/mirror syntax, not native-save collateral.

    Native KiCad serialization may omit an authored empty Datasheet field
    or materialize implicit font strokes on UNSELECTED custom properties.
    Neither is this annotation operation's authority. Read target layer and
    justification from an independently constructed native projection, but
    retain every other source byte, including opaque/empty properties.
    """
    import cec_source_retaining_ses_import as raw
    old,new=raw.inventory(source_text),raw.inventory(native_text)
    selected={}
    for row in records:selected.setdefault(row['footprint_uuid'],[]).append(row)
    result=source_text
    def children(text,kind):
        return [(a,b,text[a:b])for a,b in raw.children(text)if raw.kind(text[a:b])==kind]
    def replace(text,kind,replacement):
        hits=children(text,kind)
        if len(hits)>1:raise ValueError('ambiguous_selected_native_field_syntax')
        if hits:
            a,b,_=hits[0];return text[:a]+replacement+text[b:]
        if not replacement:return text
        at=raw.children(text,root_end=True)
        return text[:at]+'\n'+replacement+'\n'+text[at:]
    for uid in sorted(selected,key=lambda u:old[u][0],reverse=True):
        a,b=old[uid];x,y=new[uid];before=source_text[a:b];projected=native_text[x:y]
        fields={raw.node_uuid(t):(i,j,t)for i,j,t in children(before,'property')}
        targets={raw.node_uuid(t):t for _,_,t in children(projected,'property')}
        for row in sorted(selected[uid],key=lambda r:fields[r['field_uuid']][0],reverse=True):
            fid=row['field_uuid'];i,j,original=fields[fid];target=targets[fid]
            layer=children(target,'layer')
            if len(layer)!=1:raise ValueError('exact_selected_native_field_layer_required')
            edited=replace(original,'layer',layer[0][2])
            if row['source_mirrored']!=row['target_mirrored']:
                oe,ne=children(edited,'effects'),children(target,'effects')
                if len(oe)!=1 or len(ne)!=1:raise ValueError('exact_selected_native_field_effects_required')
                nj=children(ne[0][2],'justify')
                if len(nj)>1:raise ValueError('unique_native_field_justification_required')
                effects=replace(oe[0][2],'justify',nj[0][2]if nj else '')
                edited=replace(edited,'effects',effects)
            before=before[:i]+edited+before[j:]
        result=result[:a]+before+result[b:]
    return result


def write_private(source,candidate,proposal):
    """Save a declared field derivative without reserializing its source."""
    import cec_source_retaining_ses_import as raw
    source,candidate=(Path(p).resolve()for p in(source,candidate))
    if source==candidate or force._hash(source)!=force._hash(candidate):
        raise ValueError('exact_private_manufacturing_legend_source_copy_required')
    board=construct(source,proposal)
    with tempfile.TemporaryDirectory(prefix='cec-legend-literal-')as work:
        projected=Path(work)/'projection.kicad_pcb';field._save_field_snapshot(board,projected)
        text=_declared_literal(raw.raw_text(source),raw.raw_text(projected),proposal['records'])
    raw.write_raw(candidate,text)
    return dict(candidate=str(candidate),sha256=force._hash(candidate),unadmitted=True)


def receive(source, candidate, proposal, *, board_hint, timeout_s=10.):
    report = dict(ok=False, complete=False, errors=[], routing_admitted=False,
                  fab_ready=False, release_authority=False)
    try:
        _settings(proposal['policy'], board_hint, proposal['mpn_field_names'],
                  proposal['max_footprints'], timeout_s)
        source, candidate = (Path(p).resolve() for p in (source, candidate))
        if source == candidate or board_hint != proposal['board_hint']:
            raise ValueError('distinct_exact_manufacturing_legend_source_and_candidate_required')
        started = time.monotonic()
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        expected = construct(source, proposal)
        selected={r['field_uuid']:r for r in proposal['records']}
        first_literal,_=additive._nodes(source);last_literal,_=additive._nodes(candidate)
        allow_mirror=proposal['policy']==READABLE_POLICY
        if syntax._freeze(_literal_field_scope(first_literal,selected,allow_mirror)) != syntax._freeze(
                _literal_field_scope(last_literal,selected,allow_mirror)):
            raise ValueError('manufacturing_legend_changed_unowned_literal_source_evidence')
        with tempfile.TemporaryDirectory(prefix='cec-manufacturing-legend-') as work:
            projected = Path(work) / 'source-with-declared-field-layers.kicad_pcb'
            field._save_field_snapshot(expected, projected)
            first, _ = additive._nodes(projected)
            # Literal scope above independently retains all authored metadata.
            # Compare BOTH sides through the same native projection; otherwise
            # an omitted native default would force unrelated source rewrites.
            normalized=Path(work)/'candidate-native-projection.kicad_pcb'
            field._save_field_snapshot(pcbnew.LoadBoard(str(candidate)),normalized)
            last, _ = additive._nodes(normalized)
            if syntax._freeze(first) != syntax._freeze(last):
                raise ValueError('manufacturing_legend_changed_unowned_native_evidence')
            second=Path(work)/'second-save.kicad_pcb'
            field._save_field_snapshot(pcbnew.LoadBoard(str(candidate)),second)
            again,_=additive._nodes(second)
            if syntax._freeze(first)!=syntax._freeze(again):
                raise ValueError('manufacturing_legend_not_stable_under_second_native_save')
        if force._sidecars(source) != force._sidecars(candidate):
            raise ValueError('manufacturing_legend_changed_project_or_process_sidecars')
        if (time.monotonic() - started >= timeout_s or epoch != force._code_identity()
                or families != [force._family(p, board_hint) for p in (source, candidate)]):
            raise ValueError('manufacturing_legend_receiving_epoch_or_lease_changed')
        report.update(ok=True, complete=True, changed=bool(proposal['records']), code_identity=epoch,
            source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
            modified_footprint_uuids=sorted({r['footprint_uuid'] for r in proposal['records']}),
            changed_field_uuids=[r['field_uuid'] for r in proposal['records']],
            declared_mirror_changes=[dict(field_uuid=r['field_uuid'],
                source_mirrored=r['source_mirrored'],target_mirrored=r['target_mirrored'])
                for r in proposal['records'] if r['source_mirrored']!=r['target_mirrored']],
            independent_complete_native_source_replay_matched=True,
            literal_source_retained_except_exact_declared_fields=True,
            implicit_stroke_representation_bound_to_source_native_field=True,
            whole_saved_second_native_roundtrip_stable=True,
            all_source_evidence_except_declared_field_layers_exact=proposal['mirroring_unchanged'],
            all_source_evidence_except_declared_field_layers_and_readability_mirroring_exact=True,
            strings_fonts_poses_visibility_bom_netlist_copper_and_rules_unchanged=True,
            strings_fonts_poses_visibility_mirroring_bom_netlist_copper_and_rules_unchanged=proposal['mirroring_unchanged'],
            source_family_and_code_unchanged=True,
            full_native_DRC_placement_current_Kelvin_stack_and_visual_receiving_required=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--board-hint', required=True)
    parser.add_argument('--policy', choices=(POLICY,READABLE_POLICY), required=True)
    parser.add_argument('--mpn-field-name', action='append', default=None)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('fresh_private_manufacturing_legend_output_required')
    proposal = plan(args.source, policy=args.policy, board_hint=args.board_hint,
                    mpn_field_names=args.mpn_field_name or ['MPN'])
    board = construct(args.source, proposal)
    candidate = force._copy_family(args.source, args.out / 'UNADMITTED-legend-policy')
    write_private(args.source, candidate, proposal)
    proof = receive(args.source, candidate, proposal, board_hint=args.board_hint)
    receipt = dict(ok=proof['ok'], complete=proof['complete'], changed=proof.get('changed', False),
        errors=proof['errors'], source=proposal['source'], source_sha256=proposal['source_sha256'],
        candidate=str(candidate), candidate_sha256=force._hash(candidate), code_identity=proposal['code_identity'],
        records=[dict(plan=proposal, independent_saved_receiving=proof)],
        source_family_and_code_unchanged=proof.get('source_family_and_code_unchanged', False),
        routing_admitted=False, fab_ready=False, release_authority=False)
    force._write(args.out / 'stage.json', receipt)
    print(str(args.out / 'stage.json'), flush=True)
    if not proof['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    _quiet = wx.LogNull()
    main()
