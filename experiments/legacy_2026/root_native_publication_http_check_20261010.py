"""Check actual served PNG/native copper bytes against an exact draft frontier."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

import cec_force_current as force
import root_agent_draft_frontier_20261010 as frontier_api


def assert_frontier_review_metadata(selection, hint, row):
    """Byte-correct new plots must not leave a stale review ID/count selected."""
    state = selection['state']['boards'][hint]
    wanted = row['fresh_native_counts']
    actual = {'opens':state['current_opens'], 'scored_drc':state['scored_drc']}
    if (any(type(v) is not int or v < 0 for v in [*actual.values(), *wanted.values()])
            or actual != wanted or state['dashboard_id'] != row['review']['id']):
        raise ValueError('publication_frontier_review_id_or_counts_stale')


def select_publication_boards(publication, hints=None):
    boards=publication.get('boards')
    if not isinstance(boards,dict) or not 1<=len(boards)<=8:
        raise ValueError('bounded_publication_inventory_required')
    if hints is None:return boards
    if (not isinstance(hints,list) or not 1<=len(hints)<=8
            or any(not isinstance(h,str) or not h or h not in boards for h in hints)
            or len(hints)!=len(set(hints))):
        raise ValueError('exact_distinct_published_board_subset_required')
    return {hint:boards[hint] for hint in hints}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--publication', type=Path, required=True)
    p.add_argument('--frontier-state', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--board-hint',action='append',
        help='Verify an explicit subset of an original publication without fabricating or rewriting its metadata')
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('read_only_http_receipt_already_exists')
    selection = frontier_api.load(a.frontier_state, repo=Path.cwd())
    publication = json.loads(a.publication.read_text())
    boards=select_publication_boards(publication,a.board_hint)
    result = dict(schema=1, publication=str(a.publication),
        publication_sha256=force._hash(a.publication), boards={}, errors=[],
        checked_board_hints=list(boards),whole_publication_checked=set(boards)==set(publication['boards']),
        scope='served_native_asset_bytes_and_frontier_identity_only',
        automatically_opened_board_tabs=False, release_authority=False)
    for hint, row in boards.items():
        live = frontier_api.selected(selection, hint)
        if live['sha256'] != row['candidate_sha256'] or Path(row['candidate']).resolve() != Path(live['board']):
            raise ValueError('published_native_board_is_not_current_frontier')
        assert_frontier_review_metadata(selection, hint, row)
        review = row['review']
        folder = Path('build/board-archive')/review['id']
        if force._hash(folder/'board.kicad_pcb') != live['sha256']:
            raise ValueError('archived_native_byte_identity_mismatch')
        assets = []
        for name in ('render.png','plot-f.svg','plot-in1.svg','plot-in2.svg','plot-in3.svg','plot-in4.svg','plot-b.svg'):
            local = folder/name
            url = 'http://localhost:8090/artifact?' + urllib.parse.urlencode({'p':str(local)})
            with urllib.request.urlopen(url, timeout=2.) as response:
                data = response.read(8*1024*1024+1)
                status = response.status
            digest = hashlib.sha256(data).hexdigest()
            if status != 200 or len(data) > 8*1024*1024 or digest != force._hash(local):
                raise ValueError('served_asset_does_not_match_saved_native_publication:'+name)
            assets.append(dict(asset=name, status=status, bytes=len(data), sha256=digest))
        result['boards'][hint] = dict(id=review['id'],viewer_url=review['viewer_url'],
            native_sha256=live['sha256'],counts=row['fresh_native_counts'],assets=assets)
    if not frontier_api.unchanged(selection):
        raise ValueError('frontier_changed_during_read_only_asset_check')
    result['all_png_and_six_native_copper_assets_served_exactly'] = True
    result['all_frontier_review_ids_and_native_counts_bound_exactly'] = True
    force._write(a.out, result)
    print(json.dumps(dict(receipt=str(a.out), ok=True,
        boards={key:dict(id=value['id'], assets=len(value['assets']),counts=value['counts'])
                for key,value in result['boards'].items()})),flush=True)


if __name__ == '__main__':
    main()
