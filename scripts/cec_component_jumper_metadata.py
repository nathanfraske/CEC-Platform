"""Explicit per-component schematic jumper metadata, never copper authority.

KiCad 10's SWIG binding does not expose a usable JumperPadGroups setter.
The saved-file adapter consequently changes only that exact footprint field,
then independently roundtrips native IO and compares every other AST node.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

import pcbnew
import cec_copper_echo as sexpr

_FIELDS = {'jumper_pad_groups', 'duplicate_pad_numbers_are_jumpers'}
_MAX_HIERARCHY_FILES = 128
_MAX_HIERARCHY_BYTES = 16 * 1024 * 1024
_MAX_HIERARCHY_DEPTH = 32


def _children(node, name):
    return [x for x in node[1:] if isinstance(x,list) and x and x[0]==name]


def _one(node, name, default=None):
    rows=_children(node,name)
    if len(rows)>1:raise ValueError('duplicate_jumper_metadata_field:'+name)
    return rows[0] if rows else default


def _atom(value):
    if not isinstance(value,str):raise ValueError('literal_jumper_pin_required')
    value=json.loads(value) if value.startswith('"') else value
    if not value or any(ord(c)<33 for c in value):raise ValueError('literal_jumper_pin_required')
    return value


def _text(value):
    if not isinstance(value,str):raise ValueError('literal_metadata_text_required')
    return json.loads(value) if value.startswith('"') else value


def _parse(text):return sexpr._parse(sexpr._TOKEN.findall(text))
def _render(node):return '('+' '.join(_render(x) if isinstance(x,list) else x for x in node)+')'


def _groups(rows):
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,list) or len(row)<2:raise ValueError('malformed_jumper_group')
        group=tuple(_atom(x)for x in row)
        if len(set(group))!=len(group) or seen.intersection(group):raise ValueError('overlapping_or_duplicate_jumper_groups')
        seen.update(group);result.append(tuple(sorted(group)))
    return tuple(sorted(result))


def from_export(text):
    """Parse actual KiCad exported hierarchy; no part/FPID inference."""
    return from_export_tree(_parse(text))


def from_export_tree(root):
    """Same pure parser for an already freshly exported S-expression tree."""
    if not root or root[0]!='export':raise ValueError('kicad_hierarchy_export_required')
    parts={}
    for part in (_one(root,'libparts',['libparts']))[1:]:
        if not isinstance(part,list) or not part or part[0]!='libpart':raise ValueError('malformed_export_libpart')
        lib=_one(part,'lib');name=_one(part,'part');pins=_one(part,'pins')
        if lib is None or name is None or pins is None:raise ValueError('complete_export_libpart_required')
        key=(_atom(lib[1]),_atom(name[1]));numbers=[]
        for pin in pins[1:]:
            num=_one(pin,'num')
            if num is None or len(num)!=2:raise ValueError('export_pin_number_required')
            numbers.append(_atom(num[1]))
        if key in parts:raise ValueError('duplicate_export_libpart')
        parts[key]=set(numbers)
    nets={}
    for net in (_one(root,'nets',['nets']))[1:]:
        name=_one(net,'name')
        if name is None:raise ValueError('export_net_name_required')
        for node in _children(net,'node'):
            ref=_one(node,'ref');pin=_one(node,'pin')
            if ref is None or pin is None:raise ValueError('export_net_member_required')
            key=(_atom(ref[1]),_atom(pin[1]));value=_text(name[1])
            if key in nets:raise ValueError('ambiguous_export_pin_membership')
            nets[key]=value
    result={}
    for component in (_one(root,'components',['components']))[1:]:
        ref=_one(component,'ref');source=_one(component,'libsource')
        if ref is None or source is None:raise ValueError('export_component_identity_required')
        ref=_atom(ref[1]);key=(_atom(_one(source,'lib')[1]),_atom(_one(source,'part')[1]))
        if ref in result or key not in parts:raise ValueError('ambiguous_export_component')
        implicit=_one(component,'duplicate_pin_numbers_are_jumpers')
        if implicit is not None and (len(implicit)!=2 or implicit[1]not in ('0','no')):
            raise ValueError('implicit_duplicate_pin_jumpers_unsupported')
        raw=_one(component,'jumper_pin_groups',['jumper_pin_groups']);groups=[]
        for group in raw[1:]:
            if not isinstance(group,list)or not group or group[0]!='group':raise ValueError('malformed_export_jumper_group')
            if any(not isinstance(x,list)or len(x)!=2 or x[0]!='pin'for x in group[1:]):raise ValueError('malformed_export_jumper_group')
            groups.append([x[1]for x in group[1:]])
        groups=_groups(groups)
        for group in groups:
            if not set(group)<=parts[key]:raise ValueError('unknown_export_jumper_pin')
            values=[nets.get((ref,pin))for pin in group]
            if any(v is None for v in values)or len(set(values))!=1:raise ValueError('jumper_group_crosses_authored_nets')
        result[ref]=dict(groups=groups,pin_numbers=tuple(sorted(parts[key])),
                         pad_nets={pin:value for (r,pin),value in nets.items()if r==ref})
    return result


def _clock(deadline):
    if time.monotonic()>=deadline:raise ValueError('jumper_export_deadline')


def _hierarchy(path, *, deadline):
    """Strict actual sheet graph, independent of whitespace or discovery."""
    pending=[(Path(path).resolve(strict=True),0,())];found={};total=0
    while pending:
        _clock(deadline);path,depth,ancestors=pending.pop()
        if path in ancestors:raise ValueError('cyclic_jumper_source_hierarchy')
        if path in found:raise ValueError('repeated_jumper_source_hierarchy_file')
        if depth>_MAX_HIERARCHY_DEPTH:raise ValueError('jumper_source_hierarchy_depth_bound')
        if len(found)>=_MAX_HIERARCHY_FILES:raise ValueError('jumper_source_hierarchy_file_bound')
        if total+path.stat().st_size>_MAX_HIERARCHY_BYTES:raise ValueError('jumper_source_hierarchy_byte_bound')
        _clock(deadline);data=path.read_bytes();total+=len(data)
        if total>_MAX_HIERARCHY_BYTES:raise ValueError('jumper_source_hierarchy_byte_bound')
        root=_parse(data.decode('utf-8'));_clock(deadline)
        if not root or root[0]!='kicad_sch':raise ValueError('actual_jumper_source_schematic_required')
        found[path]=hashlib.sha256(data).hexdigest()
        for sheet in _children(root,'sheet'):
            _clock(deadline)
            fields=[x for x in _children(sheet,'property')if len(x)>=2 and _text(x[1])=='Sheetfile']
            if len(fields)!=1 or len(fields[0])<3:raise ValueError('single_jumper_sheetfile_required')
            name=_text(fields[0][2])
            if not name:raise ValueError('nonempty_jumper_sheetfile_required')
            child=(path.parent/name).resolve(strict=True)
            pending.append((child,depth+1,ancestors+(path,)))
    _clock(deadline)
    return found


def observe(schematic, *, timeout_s=10.):
    """One bounded fresh CLI export, immutable actual hierarchy."""
    import cec_pcb_reconcile as reconcile
    if isinstance(timeout_s,bool)or not isinstance(timeout_s,(int,float))or not 0<timeout_s<=10:raise ValueError('bounded_jumper_export_timeout_required')
    deadline=time.monotonic()+timeout_s;files=_hierarchy(schematic,deadline=deadline)
    with tempfile.TemporaryDirectory(prefix='cec-jumper-export-')as tmp:
        output=Path(tmp)/'source.net'
        cli=reconcile.TC.require_kicad_cli('component jumper hierarchy export')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('jumper_export_deadline')
        q=subprocess.run([cli,'sch','export','netlist','-o',str(output),str(schematic)],capture_output=True,text=True,timeout=remaining)
        if q.returncode!=0 or not output.is_file():raise ValueError('jumper_hierarchy_export_failed:'+q.stderr)
        result=from_export(output.read_text())
    observation=dict(files={str(p):h for p,h in files.items()},deadline=deadline,root=str(Path(schematic).resolve(strict=True)))
    check_observation(observation)
    return result,observation


def check_observation(observation):
    _clock(observation['deadline'])
    if 'root'in observation:
        fresh=_hierarchy(observation['root'],deadline=observation['deadline'])
        if {str(p):h for p,h in fresh.items()}!=observation['files']:raise ValueError('jumper_source_hierarchy_changed')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in observation['files'].items()):raise ValueError('jumper_source_hierarchy_changed')
    _clock(observation['deadline'])


def read_native(board, *, refs=None, timeout_s=10.):
    """Read actual RAM footprint metadata via supported FP-only formatter.

    Never call Format(BOARD), SaveBoard, or a connectivity builder. No path
    or project settings are changed and no saved-path proxy is substituted.
    """
    if isinstance(timeout_s,bool)or not isinstance(timeout_s,(int,float))or not 0<timeout_s<=10:raise ValueError('bounded_jumper_native_timeout_required')
    deadline=time.monotonic()+timeout_s;selected=None if refs is None else set(refs);result={}
    for fp in board.GetFootprints():
        _clock(deadline);ref=str(fp.GetReference())
        if selected is not None and ref not in selected:continue
        if ref in result:raise ValueError('unique_native_component_reference_required')
        io=pcbnew.PCB_IO_KICAD_SEXPR();io.Format(fp)
        node=_parse(io.GetStringOutput(False));_clock(deadline)
        if not node or node[0]!='footprint':raise ValueError('native_footprint_formatter_required')
        raw=_one(node,'jumper_pad_groups',['jumper_pad_groups'])
        implicit=_one(node,'duplicate_pad_numbers_are_jumpers')
        if implicit is not None and (len(implicit)!=2 or implicit[1]not in ('yes','no')):raise ValueError('malformed_native_implicit_jumper_mode')
        result[ref]=dict(groups=_groups(raw[1:]),implicit=bool(fp.GetDuplicatePadNumbersAreJumpers()))
    _clock(deadline)
    return result


def _footprints(root):
    result={}
    for fp in _children(root,'footprint'):
        ref=next((_atom(x[2])for x in _children(fp,'property')if len(x)>=3 and _atom(x[1])=='Reference'),None)
        if ref is None or ref in result:raise ValueError('unique_native_component_reference_required')
        result[ref]=fp
    return result


def read_saved(path):
    """Native saved metadata getter (SWIG vector/optional are opaque)."""
    root=_parse(Path(path).read_text());result={}
    for ref,fp in _footprints(root).items():
        raw=_one(fp,'jumper_pad_groups',['jumper_pad_groups'])
        result[ref]=_groups(raw[1:])
    return result


def _without_metadata(root):
    root=copy.deepcopy(root)
    for fp in _children(root,'footprint'):fp[:]=[x for x in fp if not(isinstance(x,list)and x and x[0]in _FIELDS)]
    return sexpr._freeze(root)


def apply_saved(path, contracts, *, timeout_s=10.):
    """Exact private saved-file setter. No pad/net/geometry changes allowed."""
    if isinstance(timeout_s,bool)or not isinstance(timeout_s,(int,float))or not 0<timeout_s<=10:raise ValueError('bounded_jumper_apply_timeout_required')
    deadline=time.monotonic()+timeout_s;path=Path(path);original=path.read_bytes();root=_parse(original.decode());fps=_footprints(root)
    original_nonmetadata=_without_metadata(root)
    # Validate every selected component BEFORE any saved mutation.
    changed=[];expected_groups={};literal_edits={}
    for ref,fp in fps.items():
        if ref not in contracts:continue
        contract=contracts[ref]
        raw_groups=contract['groups']
        if not isinstance(raw_groups,(tuple,list))or any(not isinstance(g,(tuple,list))or any(type(p)is not str for p in g)for g in raw_groups):raise ValueError('literal_contract_jumper_groups_required')
        groups=_groups([list(map(json.dumps,g))for g in raw_groups]);expected_groups[ref]=groups;pads={}
        for pad in _children(fp,'pad'):
            number=_text(pad[1]);net=_one(pad,'net')
            # Mechanical/NPTH unnumbered lands never become group members.
            if not number:continue
            pads.setdefault(number,[]).append((_text(net[-1])or None)if net is not None and len(net)in (2,3) else None)
        for group in groups:
            if not set(group)<=set(pads)or not set(group)<=set(contract['pin_numbers']):raise ValueError('missing_native_jumper_pad')
            expected={contract['pad_nets'].get(pin)for pin in group}
            actual={value for pin in group for value in pads[pin]}
            if None in expected or None in actual or len(expected)!=1 or actual!=expected:raise ValueError('native_jumper_authored_net_mismatch')
        old=_one(fp,'jumper_pad_groups',['jumper_pad_groups']);implicit=_one(fp,'duplicate_pad_numbers_are_jumpers')
        if implicit is not None and (len(implicit)!=2 or implicit[1]not in ('no','yes')):raise ValueError('malformed_native_implicit_jumper_mode')
        if _groups(old[1:])==groups and not(implicit is not None and implicit[1]=='yes'):
            continue
        changed.append(ref);literal_edits[ref]=[]
        desired={'duplicate_pad_numbers_are_jumpers':['duplicate_pad_numbers_are_jumpers','no'],
            'jumper_pad_groups':(['jumper_pad_groups',*[[json.dumps(p)for p in g]for g in groups]]if groups else None)}
        for tag,target in desired.items():
            previous=_one(fp,tag)
            if previous==target:continue
            literal_edits[ref].append(dict(tag=tag,before=copy.deepcopy(previous),after=copy.deepcopy(target)))
            if previous is not None:
                index=fp.index(previous);fp.pop(index)
                if target is not None:fp.insert(index,target)
            elif target is not None:fp.append(target)
    if not changed:
        if time.monotonic()>=deadline:raise ValueError('jumper_apply_deadline')
        if path.read_bytes()!=original:raise ValueError('jumper_saved_input_changed')
        return []
    with tempfile.TemporaryDirectory(prefix='cec-jumper-native-')as tmp:
        candidate=Path(tmp)/'candidate.kicad_pcb';native=Path(tmp)/'native.kicad_pcb'
        baseline=Path(tmp)/'baseline.kicad_pcb';baseline_native=Path(tmp)/'baseline-native.kicad_pcb'
        # Native IO may canonically drop explicit default font thickness etc.
        # Compare both independently normalized paths, never waive any raw
        # saved difference: the emitted candidate itself stays exact below.
        if _without_metadata(root)!=original_nonmetadata:raise ValueError('jumper_raw_nonmetadata_changed')
        baseline.write_bytes(original)
        baseboard=pcbnew.LoadBoard(str(baseline));pcbnew.SaveBoard(str(baseline_native),baseboard)
        import cec_literal_footprint_metadata as literal
        emitted=literal.splice(original.decode(),literal_edits)
        if _parse(emitted)!=root:raise ValueError('jumper_literal_emission_changed_complete_AST')
        candidate.write_text(emitted)
        b=pcbnew.LoadBoard(str(candidate));pcbnew.SaveBoard(str(native),b)
        after=_parse(native.read_text())
        if _without_metadata(after)!=_without_metadata(_parse(baseline_native.read_text())):raise ValueError('jumper_native_roundtrip_changed_nonmetadata')
        observed=read_saved(native)
        for ref in fps:
            if ref in contracts and observed[ref]!=expected_groups[ref]:raise ValueError('jumper_native_roundtrip_metadata_mismatch')
        if time.monotonic()>=deadline:raise ValueError('jumper_apply_deadline')
        if path.read_bytes()!=original:raise ValueError('jumper_saved_input_changed')
        path.write_bytes(candidate.read_bytes())
    return changed
