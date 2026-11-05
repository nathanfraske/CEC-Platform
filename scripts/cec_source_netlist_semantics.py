"""Full exported source identity except the single generated design/date value."""
import copy
import datetime
import hashlib
import json
import re

POLICY='full-export-tree-except-single-generated-design-date-v1'


def metadata(tree):
    if not isinstance(tree,list)or not tree or tree[0]!='export':
        raise ValueError('actual_export_netlist_tree_required')
    normalized=copy.deepcopy(tree)
    designs=[n for n in normalized[1:]if isinstance(n,list)and n and n[0]=='design']
    if len(designs)>1:raise ValueError('unique_netlist_design_metadata_required')
    if designs:
        dates=[n for n in designs[0][1:]if isinstance(n,list)and n and n[0]=='date']
        if len(dates)>1:raise ValueError('single_generated_netlist_date_required')
        if dates:
            date=dates[0]
            if(len(date)!=2 or type(date[1])is not str
                or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?',date[1])):
                raise ValueError('recognized_generated_iso_netlist_date_required')
            try:datetime.datetime.fromisoformat(date[1].replace('Z','+00:00'))
            except ValueError as exc:raise ValueError('valid_generated_netlist_date_required')from exc
            # Preserve the date node's existence and position, not its clock.
            date[1]='<generated-design-date>'
    encoded=json.dumps(normalized,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    return dict(netlist_semantic_sha256=hashlib.sha256(encoded).hexdigest(),
        netlist_semantic_policy=POLICY)


def replay_identity(proof):
    """Only volatile raw export hash differs; full fresh semantic hash is required."""
    result=copy.deepcopy(proof);exporter=result.get('exporter')
    if(not isinstance(exporter,dict)or exporter.get('netlist_semantic_policy')!=POLICY
        or any(not isinstance(exporter.get(k),str)or not re.fullmatch('[0-9a-f]{64}',exporter[k])
            for k in('netlist_semantic_sha256','netlist_sha256','exporter_sha256'))):
        raise ValueError('fresh_full_netlist_semantic_export_identity_required')
    exporter.pop('netlist_sha256')
    return result
