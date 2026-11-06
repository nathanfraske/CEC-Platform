"""Actual schema-three flat land drafts retain native identities, not admission."""
import json
from pathlib import Path

import pytest
from test_agentic_drafts import pcbnew, drafts, ROOT, syntax, echo, uid
from cec_pipeline import flatbars


def request():
    return json.loads((ROOT/'docs/evidence/20261105-bar-land/land-draft.json').read_text())


def bound_inputs(value):
    planpath=ROOT/value['placement']['path'];plan=json.loads(planpath.read_text())
    paths={planpath,Path(plan['contract']['path'])}
    paths.update(Path(plan[side]['path']) for side in ('carrier','cover'))
    for rows in value['flatbars'].values():
        for row in rows:
            partpath=ROOT/row['part']['path'];part=json.loads(partpath.read_text())
            paths.update((partpath,partpath.parent/(part['footprint']+'.kicad_mod')))
    return plan,{path:path.read_bytes() for path in paths}


def native_ids(board):
    items=[*board.GetTracks(),*board.GetDrawings(),*board.Zones(),*board.Groups()]
    for fp in board.GetFootprints():items.extend(flatbars._footprint_items(fp))
    return [uid(item) for item in items]


@pytest.mark.parametrize('refill',[False,True])
def test_actual_flatbar_stage_preserves_exact_native_children_and_sources(tmp_path,monkeypatch,refill):
    import cec_field_coupling as field
    monkeypatch.chdir(ROOT);value=request();plan,before=bound_inputs(value)
    captured={};original=field._save_field_snapshot
    def capture(board,path):
        captured[Path(path).parent.name]=(field._field_snapshot_inventory(board),native_ids(board))
        return original(board,path)
    monkeypatch.setattr(field,'_save_field_snapshot',capture)
    result=drafts.stage(value,tmp_path/'flat-land',refill=refill)
    assert result['complete'] and result['source_unchanged']
    assert result['bar_stack_screen']['ok'] is True
    assert result['routing_admitted'] is False and result['release_authority'] is False
    assert result['current_Kelvin_return_and_pair_receiving_complete'] is False
    for row in result['boards']:
        side=row['side'];saved=pcbnew.LoadBoard(row['path'])
        source=pcbnew.LoadBoard(plan[side]['path'])
        expected_inventory,expected_ids=captured[side]
        assert field._field_snapshot_inventory(saved)==expected_inventory
        assert sorted(native_ids(saved))==sorted(expected_ids)
        assert len(native_ids(saved))==len(set(native_ids(saved)))
        props=lambda b:{str(k):str(v) for k,v in b.GetProperties().asdict().items()}
        assert props(saved)==props(source)
        assert any(k.startswith('CEC_FAB_PROFILE') for k in props(source))
        assert row['refill_required'] is (not refill) and row['native_DRC_required'] is True
        if refill:assert row['native_fill']['stable'] is True
        oldrefs={f.GetReference() for f in source.GetFootprints()}
        newrefs={f.GetReference() for f in saved.GetFootprints()}
        assert newrefs-oldrefs==({'BB1'} if side=='carrier' else set())
        assert not oldrefs-newrefs
        for bar in row['flatbars']:
            fp=saved.FindFootprintByReference(bar['reference'])
            assert set(bar['added_uuids'])=={uid(i) for i in flatbars._footprint_items(fp)}
            assert len(bar['added_uuids'])==len(set(bar['added_uuids']))
            assert bar['footprint_uuid']==uid(fp)
            assert all(bar[k] is False for k in ('current_qualified','assembly_qualified',
                'routing_admitted','release_authority'))
        _,old=syntax._nodes(plan[side]['path']);_,new=syntax._nodes(row['path'])
        for fp in source.GetFootprints():
            if not (side=='carrier' and fp.GetReference()=='C7'):
                assert echo._freeze(old[uid(fp)])==echo._freeze(new[uid(fp)])
        removed={r['uuid'] for r in row['retired_tracks']}
        added={u for r in row['redraws'] for u in r['added_uuids']}
        added|={r['footprint_uuid'] for r in row['flatbars']}
        assert set(new)==(set(old)-removed)|added
        changed=set(row['moved_footprint_uuids'])|{r['source_uuid'] for r in row['redraws']}
        changed|={r['uuid'] for r in row['via_moves']}
        changed|={u for r in row['redraws'] for u in r['group_uuids']}
        if refill:changed|={uid(z) for z in source.Zones() if not z.GetIsRuleArea()}
        assert all(echo._freeze(old[u])==echo._freeze(new[u]) for u in set(old)-changed-removed)
    assert all(path.read_bytes()==data for path,data in before.items())


def test_failed_added_bar_stack_never_creates_output(tmp_path,monkeypatch):
    monkeypatch.chdir(ROOT);value=request();_,before=bound_inputs(value)
    evaluate=drafts.repack.assembly.evaluate_boards;observed=[]
    def reject_inserted(carrier,cover,contract,*args,**kwargs):
        result,data=evaluate(carrier,cover,contract,*args,**kwargs)
        if carrier.FindFootprintByReference('BB1') is not None:
            observed.append(True);result=dict(result,ok=False)
        return result,data
    monkeypatch.setattr(drafts.repack.assembly,'evaluate_boards',reject_inserted)
    with pytest.raises(ValueError,match='passing_paired_stack'):
        drafts.stage(value,tmp_path/'bad-stack')
    assert observed and not (tmp_path/'bad-stack').exists()
    assert all(path.read_bytes()==data for path,data in before.items())


def test_part_identity_change_during_save_cannot_produce_complete_receipt(tmp_path,monkeypatch):
    import cec_field_coupling as field
    monkeypatch.chdir(ROOT);value=request();_,before=bound_inputs(value)
    partpath=(ROOT/value['flatbars']['carrier'][0]['part']['path']).resolve()
    original_save=field._save_field_snapshot;original_sha=drafts.repack.inspection.sha
    saving=False
    def save(board,path):
        nonlocal saving
        result=original_save(board,path);saving=True;return result
    def raced(path):
        if saving and Path(path).resolve()==partpath:return '0'*64
        return original_sha(path)
    monkeypatch.setattr(field,'_save_field_snapshot',save)
    monkeypatch.setattr(drafts.repack.inspection,'sha',raced)
    output=tmp_path/'raced-part'
    with pytest.raises(ValueError,match='identity_mismatch'):drafts.stage(value,output)
    receipt=json.loads((output/'draft.json').read_text())
    assert receipt['complete'] is False and receipt['routing_admitted'] is False
    assert receipt['release_authority'] is False
    assert all(path.read_bytes()==data for path,data in before.items())
