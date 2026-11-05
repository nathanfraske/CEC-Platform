"""Remove only literal-identical complete DSN guard nodes; never geometry."""
import hashlib
from pathlib import Path
import cec_source_retaining_ses_import as syntax

def deduplicate_text(text):
    if type(text)is not str or len(text.encode('utf-8'))>32*1024*1024:raise ValueError('bounded_DSN_text_required')
    # KiCad's quote-delimiter declaration is not a quoted string. Replace
    # that one character in a same-length scanner stencil, never in output.
    stencil=text.replace('(string_quote ")','(string_quote Q)')
    if len(stencil)!=len(text):raise ValueError('DSN_scanner_stencil_length_changed')
    structures=[(a,b)for a,b in syntax.children(stencil)if syntax.kind(stencil[a:b])=='structure']
    if len(structures)!=1:raise ValueError('exactly_one_DSN_structure_required')
    start,end=structures[0];node=stencil[start:end];seen=set();remove=[]
    children=syntax.children(node)
    if len(children)>200000:raise ValueError('bounded_DSN_structure_required')
    for a,b in children:
        if syntax.kind(node[a:b])not in ('keepout','via_keepout','wire_keepout'):continue
        literal=text[start+a:start+b]
        if literal in seen:remove.append((start+a,start+b))
        else:seen.add(literal)
    result=text
    for a,b in reversed(remove):result=result[:a]+result[b:]
    return result,dict(scope='literal_complete_DSN_guard_nodes_only',removed_nodes=len(remove),
        removed_spans=remove,all_other_bytes_literal_exact=True,geometry_simplified=False,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),result_sha256=hashlib.sha256(result.encode()).hexdigest())

def deduplicate_file(path):
    path=Path(path)
    if path.is_symlink():raise ValueError('DSN_alias_refused')
    before=path.read_bytes();text=before.decode('utf-8');result,receipt=deduplicate_text(text)
    if receipt['removed_nodes']:
        import cec_fr
        cec_fr._atomic_replace_text(str(path),result)
    return receipt
