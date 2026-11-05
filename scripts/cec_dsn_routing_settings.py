"""Bounded, byte-preserving Specctra execution settings, not route authority.

On the pinned FR 1.7.0 family, ``-oit`` is an improvement threshold, NOT
seconds or an optimization enable switch. A route-only stage must explicitly
set the native ``structure/autoroute_settings/postroute`` flag. No geometry,
net/pin ownership, layer rules, fanout or autoroute setting is rewritten.
"""
import hashlib
import json
import math
import re
import time

MAX_BYTES = 64 * 1024 ** 2
MAX_TOKENS = 2_000_000
MAX_DEPTH = 128
_TOKEN = re.compile(r'\s+|[()]|"(?:\\.|[^"\\])*"|[^\s()"]+')
_TARGETS = {('pcb',), ('pcb', 'structure'),
            ('pcb', 'structure', 'layer'),
            ('pcb', 'structure', 'layer', 'type'),
            ('pcb', 'structure', 'plane'),
            ('pcb', 'structure', 'autoroute_settings'),
            ('pcb', 'structure', 'autoroute_settings', 'postroute'),
            ('pcb', 'structure', 'autoroute_settings', 'layer_rule'),
            ('pcb', 'structure', 'autoroute_settings', 'layer_rule', 'active')}


def _scopes(text, deadline):
    if not isinstance(text, str) or not text or '\x00' in text:
        raise ValueError('invalid_native_DSN_text')
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('DSN_execution_settings_byte_bound')
    # Native KiCad delimiter declaration is a literal quote, not a string.
    # Mask only that declaration, without shifting any character positions.
    scan = re.sub(r'(?m)^(\s*\(string_quote\s+)"(\s*\)\s*)$', r'\1Q\2', text)
    if len(scan) != len(text):
        raise ValueError('DSN_execution_settings_offset_identity')
    stack, records, end, count, roots = [], [], 0, 0, 0
    for match in _TOKEN.finditer(scan):
        if time.monotonic() >= deadline:
            raise RuntimeError('DSN_execution_settings_deadline')
        if match.start() != end:
            raise ValueError('invalid_DSN_execution_settings_token')
        end = match.end()
        raw = match.group()
        if raw.isspace():
            continue
        count += 1
        if count > MAX_TOKENS:
            raise ValueError('DSN_execution_settings_token_bound')
        if raw == '(':
            if len(stack) >= MAX_DEPTH or (stack and stack[-1]['name'] is None):
                raise ValueError('invalid_DSN_execution_settings_depth_or_head')
            if not stack:
                roots += 1
            else:
                stack[-1]['children'] += 1
            stack.append(dict(name=None, start=match.start(), atoms=[], children=0,
                              quoted_head=False, quoted_atoms=False))
        elif raw == ')':
            if not stack or stack[-1]['name'] is None:
                raise ValueError('unbalanced_DSN_execution_settings_scope')
            row = stack.pop()
            path = tuple(s['name'] for s in stack) + (row['name'],)
            if path in _TARGETS:
                if row['quoted_head']:
                    raise ValueError('quoted_DSN_execution_keyword_not_native')
                row.update(path=path, stop=match.end())
                records.append(row)
        else:
            if not stack:
                raise ValueError('DSN_execution_settings_atom_outside_root')
            value = json.loads(raw) if raw.startswith('"') else raw
            if stack[-1]['name'] is None:
                stack[-1]['name'] = value
                stack[-1]['quoted_head'] = raw.startswith('"')
            elif stack[-1]['name'] in ('postroute', 'layer', 'type', 'layer_rule', 'active'):
                stack[-1]['atoms'].append(value)
                stack[-1]['quoted_atoms'] |= raw.startswith('"')
    if end != len(scan) or stack or roots != 1:
        raise ValueError('incomplete_or_multiple_DSN_execution_settings_roots')
    if len([r for r in records if r['path'] == ('pcb',)]) != 1:
        raise ValueError('actual_DSN_pcb_root_required')
    return records


def set_postroute(text, enabled, *, timeout_s=5.):
    """Return an explicitly requested execution-only edit and its manifest.

    Idempotent, quote-aware and fail-closed on duplicate/ambiguous settings.
    All bytes outside the single owned execution setting remain exact. The
    manifest is NOT evidence of connectivity, DRC or fabrication readiness.
    """
    if type(enabled) is not bool:
        raise ValueError('explicit_boolean_postroute_required')
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10):
        raise ValueError('invalid_DSN_execution_settings_deadline')
    deadline = time.monotonic() + timeout_s
    if time.monotonic() >= deadline:
        raise RuntimeError('DSN_execution_settings_deadline')
    records = _scopes(text, deadline)
    structure = [r for r in records if r['path'] == ('pcb', 'structure')]
    settings = [r for r in records if r['path'] == ('pcb', 'structure', 'autoroute_settings')]
    fields = [r for r in records if r['path'] ==
              ('pcb', 'structure', 'autoroute_settings', 'postroute')]
    layers = [r for r in records if r['path'] == ('pcb', 'structure', 'layer')]
    planes = [r for r in records if r['path'] == ('pcb', 'structure', 'plane')]
    if len(structure) != 1 or len(settings) > 1 or len(fields) > 1:
        raise ValueError('unambiguous_native_DSN_execution_scope_required')
    if not layers or any(len(row['atoms']) != 1 for row in layers):
        raise ValueError('native_DSN_layer_inventory_required')
    layer_end = max(row['stop'] for row in layers)
    plane_start = min((row['start'] for row in planes), default=structure[0]['stop'])
    if layer_end > plane_start or (settings and not
            layer_end <= settings[0]['start'] < settings[0]['stop'] <= plane_start):
        # FR 1.7.0 constructs layer_structure while reading the first plane.
        # Its settings parser then skips a later autoroute_settings scope.
        # Never report a syntactically present but ignored flag as received.
        raise ValueError('native_DSN_execution_settings_must_precede_planes')
    flag = 'on' if enabled else 'off'
    before = None
    if fields:
        row = fields[0]
        if (row['children'] or row['quoted_atoms'] or len(row['atoms']) != 1
                or row['atoms'][0] not in ('on', 'off')):
            raise ValueError('invalid_native_DSN_postroute_flag')
        before = row['atoms'][0] == 'on'
        start, stop = row['start'], row['stop']
        replacement = text[start:stop] if before == enabled else '(postroute '+flag+')'
    elif settings:
        start = stop = settings[0]['stop'] - 1
        replacement = '\n (postroute '+flag+')\n'
    else:
        start = stop = layer_end
        layer_rules = []
        signal_index = 0
        for layer in layers:
            types = [r for r in records if r['path'] == ('pcb', 'structure', 'layer', 'type')
                     and layer['start'] < r['start'] < r['stop'] < layer['stop']]
            if len(types) != 1 or types[0]['atoms'] not in (['power'], ['signal']):
                raise ValueError('native_DSN_layer_type_required')
            name=json.dumps(layer['atoms'][0],ensure_ascii=False)
            if types[0]['atoms'] == ['power']:
                layer_rules.append('\n (layer_rule '+name+' (active off))')
            else:
                direction='horizontal' if signal_index%2==0 else 'vertical'
                signal_index+=1
                layer_rules.append('\n (layer_rule '+name+' (active on)'
                    ' (preferred_direction '+direction+')'
                    ' (preferred_direction_trace_costs 1.0)'
                    ' (against_preferred_direction_trace_costs 2.0))')
        # Supplying settings bypasses FR's absent-settings plane heuristics.
        # Keep authored power-plane layers explicitly inactive for ordinary
        # routing; do not accidentally open them merely by disabling postroute.
        # Crucially the DSN parser calls AutorouteSettings(int), NOT its
        # RoutingBoard constructor. Unspecified layer/via flags and costs
        # are zero/false. A lone postroute field silently disables routing.
        # Declare a complete, reproducible coarse search profile instead;
        # this is NOT a claim of equivalence to absent-settings heuristics.
        if not signal_index:raise ValueError('native_DSN_signal_layer_required')
        replacement = ('\n (autoroute_settings (fanout off) (autoroute on)'
            ' (postroute '+flag+') (vias on) (via_costs 50) (plane_via_costs 5)'
            ' (start_ripup_costs 100) (start_pass_no 1)'+''.join(layer_rules)+')\n')
    result = text[:start] + replacement + text[stop:]
    received = [r for r in _scopes(result, deadline) if r['path'] ==
                ('pcb', 'structure', 'autoroute_settings', 'postroute')]
    if (len(received) != 1 or received[0]['children'] or received[0]['atoms'] != [flag]
            or result[:start] != text[:start]
            or result[start+len(replacement):] != text[stop:]):
        raise ValueError('DSN_execution_settings_exact_receiving_failed')
    return result, dict(schema=1, policy='explicit_native_postroute_v1',
        requested_postroute=enabled, previous_explicit_postroute=before,
        changed=result != text, original_span=[start, stop],
        outside_owned_setting_exact=True, source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        output_sha256=hashlib.sha256(result.encode()).hexdigest(),
        inserted_settings_before_planes=True,
        new_scope_search_profile='explicit_signal_layers_vias_costs_v1' if not settings else None,
        absent_settings_heuristics_equivalent=False if not settings else None,
        route_or_release_authority=False)


def restrict_active_layers(text, allowed, *, timeout_s=5.):
    """Restrict backend routing to a received caller layer inventory.

    Does not relabel existing copper, layer types or planes. Authored power
    layers remain inactive even if a caller lists them. No disabled signal
    layer is enabled. Unlisted signal layers are explicitly disabled before
    FR reads planes; all non-active-setting bytes remain exact.
    """
    if (isinstance(allowed, (str, bytes)) or not isinstance(allowed, (list, tuple, set, frozenset))
            or not allowed or any(type(name) is not str or not name for name in allowed)):
        raise ValueError('explicit_nonempty_routing_layer_inventory_required')
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('invalid_DSN_layer_settings_deadline')
    deadline=time.monotonic()+timeout_s
    records=_scopes(text,deadline)
    layers=[r for r in records if r['path']==('pcb','structure','layer')]
    if not layers or any(len(r['atoms'])!=1 for r in layers):
        raise ValueError('native_DSN_layer_inventory_required')
    names=[r['atoms'][0] for r in layers]
    if len(set(names))!=len(names) or not set(allowed)<=set(names):
        raise ValueError('ambiguous_or_unknown_routing_layer')
    settings=[r for r in records if r['path']==('pcb','structure','autoroute_settings')]
    if len(settings)!=1:
        raise ValueError('explicit_native_autoroute_settings_required')
    if settings[0]['start']<max(r['stop'] for r in layers) or any(
            settings[0]['stop']>r['start'] for r in records
            if r['path']==('pcb','structure','plane')):
        raise ValueError('native_DSN_execution_settings_must_precede_planes')
    rules=[r for r in records if r['path']==('pcb','structure','autoroute_settings','layer_rule')]
    if (len(rules)!=len(names) or any(len(r['atoms'])!=1 for r in rules)
            or sorted(r['atoms'][0] for r in rules)!=sorted(names)):
        raise ValueError('one_explicit_routing_rule_per_native_layer_required')
    changes=[]; inventory=[]
    for layer in layers:
        name=layer['atoms'][0]
        types=[r for r in records if r['path']==('pcb','structure','layer','type')
            and layer['start']<r['start']<r['stop']<layer['stop']]
        if len(types)!=1 or types[0]['atoms'] not in (['signal'],['power']):
            raise ValueError('native_DSN_layer_type_required')
        rule=next(r for r in rules if r['atoms']==[name])
        active=[r for r in records if r['path']==('pcb','structure','autoroute_settings','layer_rule','active')
            and rule['start']<r['start']<r['stop']<rule['stop']]
        if (len(active)!=1 or active[0]['children'] or active[0]['quoted_atoms']
                or active[0]['atoms'] not in (['on'],['off'])):
            raise ValueError('unambiguous_native_layer_active_flag_required')
        row=active[0];before=row['atoms'][0]=='on'
        after=before and name in allowed and types[0]['atoms']==['signal']
        inventory.append(dict(layer=name,before=before,after=after,type=types[0]['atoms'][0]))
        if before!=after:changes.append((row['start'],row['stop'],'(active off)'))
    if not any(r['after'] for r in inventory):
        raise ValueError('no_previously_active_permitted_signal_layer')
    result=text
    for start,stop,replacement in sorted(changes,reverse=True):
        result=result[:start]+replacement+result[stop:]
    _scopes(result,deadline)
    return result,dict(schema=1,policy='restrict_explicit_native_routing_layers_v1',
        inventory=inventory,changed=bool(changes),changed_fields=len(changes),
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        output_sha256=hashlib.sha256(result.encode()).hexdigest(),
        allowed=sorted(set(allowed)),route_or_release_authority=False)
