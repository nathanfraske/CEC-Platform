"""Exact association identity is never producer or copper authority."""
from pathlib import Path

import cec_swig_guard
cec_swig_guard.pin()
import wx
_quiet = wx.LogNull()
import pcbnew
import pytest
import cec_force_current as force
import cec_source_retaining_ses_import as raw
from test_source_reference_group_transport import fixture as original_fixture

import cec_reference_association_query as op


def save(board, path):
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path), board)


def pair(tmp_path, *, angle=0, bottom=False, interrupted=False):
    mapped, owner, group = original_fixture(tmp_path)
    b = pcbnew.LoadBoard(str(mapped)); fp = next(iter(b.GetFootprints()))
    g = next(iter(b.Groups())); at = fp.GetPosition()
    if angle:
        for item in g.GetItems():
            item.Rotate(at, pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    if bottom:
        fp.Flip(at, False)
        for item in g.GetItems():
            if item.GetClass() == 'PCB_TEXT':
                item.SetLayer(pcbnew.F_SilkS); item.SetMirrored(False)
            elif item.GetClass() == 'PCB_SHAPE':
                item.SetLayer(pcbnew.F_SilkS)
    if interrupted:
        # An exact retained fragment is query evidence only. This deliberate
        # non-closed rendering would require its enclosing producer replay.
        first = next(i for i in g.GetItems() if i.GetClass() == 'PCB_SHAPE')
        a,z=first.GetStart(),first.GetEnd()
        first.SetEnd(pcbnew.VECTOR2I((a.x+z.x)//2,(a.y+z.y)//2))
    save(b, mapped)
    source = tmp_path/'descendant.kicad_pcb'; source.write_bytes(mapped.read_bytes())
    return mapped, source, [(owner, group)]


def query(mapped, source, selections, **kwargs):
    return op.compare(mapped, source, selections, board_hint='synthetic-association', **kwargs)


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('bottom', [False, True])
@pytest.mark.parametrize('interrupted', [False, True])
def test_exact_renamed_native_association_all_cardinals_and_faces(tmp_path, angle, bottom, interrupted):
    mapped, source, selections = pair(tmp_path, angle=angle, bottom=bottom, interrupted=interrupted)
    before = [p.read_bytes() for p in (mapped, source)]
    q = query(mapped, source, selections)
    assert q['ok'] and q['complete'] and q['association_identity_preserved']
    assert q['association_only'] and q['producer_replay_still_required']
    assert q['caller_uuid_selection_is_not_producer_authority']
    assert q['unrelated_PCB_changes_not_received']
    assert not any(q[k] for k in ('closed_body_authority', 'mask_authority', 'copper_admission',
        'current_authority', 'pose_authority', 'print_admission', 'release_authority'))
    assert before == [p.read_bytes() for p in (mapped, source)]
    assert set(q['records'][0]['complete_literal_subtree_sha256']) == {
        selections[0][1], *q['records'][0]['member_uuids']}


def test_unrelated_real_copper_cut_and_new_hole_are_not_pcb_acceptance(tmp_path):
    mapped, source, selections = pair(tmp_path, interrupted=True)
    text = source.read_text()
    extra = '''(segment (start 1 1) (end 2 1) (width 0.2) (layer "F.Cu")
        (net 0) (uuid "cf1783d0-2161-42da-a188-b9ac1a8b70b5"))
      (via (at 2 1) (size 0.5) (drill 0.3) (layers "F.Cu" "B.Cu")
        (net 0) (uuid "a242f39a-d08a-4dc8-8951-31f591c8eefb"))'''
    mapped.write_text(text[:text.rfind(')')]+extra+text[text.rfind(')'):])
    changed = extra.replace('(start 1 1) (end 2 1)', '(start 1 2) (end 2 2)')
    changed = changed.replace('cf1783d0-2161-42da-a188-b9ac1a8b70b5', 'a0e8fe8f-18b2-41c9-b954-aeb259541e98')
    changed = changed.replace('(at 2 1)', '(at 2 2)').replace(
        'a242f39a-d08a-4dc8-8951-31f591c8eefb', '6aed8260-bde3-467e-a3eb-89b0b251967a')
    source.write_text(text[:text.rfind(')')]+changed+text[text.rfind(')'):])
    q = query(mapped, source, selections)
    assert q['ok'] and q['unrelated_PCB_changes_not_received'] and not q['copper_admission']
    assert not q['mask_authority'] and not q['current_authority']


@pytest.mark.parametrize('change', ['owner_move', 'owner_turn', 'owner_flip', 'ref', 'value', 'fpid',
    'part_metadata', 'pad_net', 'pad_size', 'pad_hole', 'text', 'text_move', 'text_font', 'guide_move',
    'guide_width', 'group_name', 'group_unlock', 'group_remove', 'owner_lock', 'owner_visible', 'dnp'])
def test_any_changed_protected_part_map_or_metadata_refuses(tmp_path, change):
    mapped, source, selections = pair(tmp_path)
    b = pcbnew.LoadBoard(str(source)); fp = next(iter(b.GetFootprints())); g = next(iter(b.Groups()))
    text = next(i for i in g.GetItems() if i.GetClass() == 'PCB_TEXT')
    guide = next(i for i in g.GetItems() if i.GetClass() == 'PCB_SHAPE'); pad = next(iter(fp.Pads()))
    if change == 'owner_move': fp.Move(pcbnew.VECTOR2I(1, 0))
    elif change == 'owner_turn': fp.Rotate(fp.GetPosition(), pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
    elif change == 'owner_flip': fp.Flip(fp.GetPosition(), False)
    elif change == 'ref': fp.SetReference('OTHER')
    elif change == 'value': fp.SetValue('changed')
    elif change == 'fpid': fp.SetFPID(pcbnew.LIB_ID('Different','Part'))
    elif change == 'part_metadata': fp.SetLibDescription('not-the-source-part-metadata')
    elif change == 'pad_net': pad.SetNetCode(0)
    elif change == 'pad_size': pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1, 0))
    elif change == 'pad_hole': pad.SetDrillSize(pcbnew.VECTOR2I(100000, 100000))
    elif change == 'text': text.SetText('OTHER')
    elif change == 'text_move': text.Move(pcbnew.VECTOR2I(1, 0))
    elif change == 'text_font': text.SetTextSize(pcbnew.VECTOR2I_MM(.81, .81))
    elif change == 'guide_move': guide.Move(pcbnew.VECTOR2I(1, 0))
    elif change == 'guide_width': guide.SetWidth(guide.GetWidth()+1)
    elif change == 'group_name': g.SetName('impostor')
    elif change == 'group_unlock': g.SetLocked(False)
    elif change == 'group_remove': g.RemoveItem(guide)
    elif change == 'owner_lock': fp.SetLocked(True)
    elif change == 'owner_visible': fp.Reference().SetVisible(True)
    elif change == 'dnp': fp.SetDNP(True)
    save(b, source)
    with pytest.raises(ValueError): query(mapped, source, selections)


@pytest.mark.parametrize('boundary', ['mapped', 'source'])
@pytest.mark.parametrize('fault', ['nested', 'duplicate_owner', 'duplicate_member', 'extra_copper',
    'foreign_fp', 'unreadable', 'wrong_text_face', 'wrong_mirror', 'hidden_literal', 'unknown_member'])
def test_native_uncertainty_refuses_even_when_both_subtrees_could_match(tmp_path, boundary, fault):
    mapped, source, selections = pair(tmp_path)
    path = mapped if boundary == 'mapped' else source
    b = pcbnew.LoadBoard(str(path)); g = next(iter(b.Groups())); fp = next(iter(b.GetFootprints()))
    label = next(i for i in g.GetItems() if i.GetClass() == 'PCB_TEXT')
    guide = next(i for i in g.GetItems() if i.GetClass() == 'PCB_SHAPE')
    if fault == 'nested':
        other = pcbnew.PCB_GROUP(b); other.SetName('unrelated'); b.Add(other)
        other.AddItem(g)
    elif fault == 'extra_copper':
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I_MM(1,1)); t.SetEnd(pcbnew.VECTOR2I_MM(2,1))
        t.SetWidth(200000); t.SetLayer(pcbnew.F_Cu); b.Add(t); g.AddItem(t)
    elif fault == 'foreign_fp':
        second = pcbnew.FOOTPRINT(b); second.SetReference('SECOND'); b.Add(second); g.AddItem(second)
    elif fault == 'unreadable': label.SetTextSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault == 'wrong_text_face': label.SetLayer(pcbnew.F_SilkS)
    elif fault == 'wrong_mirror': label.SetMirrored(False)
    save(b, path)
    if fault in ('duplicate_owner', 'duplicate_member'):
        # Author the actual duplicate. Native AddItem can reparent it and
        # SaveBoard may otherwise erase the negative fixture before testing.
        import uuid
        text=path.read_text();uid=force._uid(fp if fault=='duplicate_owner' else guide)
        other='(group "unrelated" (uuid "'+str(uuid.uuid4())+'") (members "'+uid+'"))'
        at=text.rfind(')');path.write_text(text[:at]+other+text[at:])
    elif fault == 'hidden_literal':
        path.write_text(path.read_text().replace('(gr_text "X7"', '(gr_text "X7" (hide yes)', 1))
    elif fault == 'unknown_member':
        path.write_text(path.read_text().replace('(members', '(members "00000000-0000-4000-8000-000000000001"', 1))
    # The comparator is not permitted to accept an invalid association merely
    # because an identical invalid rendering is supplied at both boundaries.
    other_path = source if boundary == 'mapped' else mapped
    other_path.write_bytes(path.read_bytes())
    with pytest.raises(ValueError): query(mapped, source, selections)


@pytest.mark.parametrize('fault', ['root_duplicate', 'nested_pad_duplicate', 'missing_owner', 'missing_guide',
    'duplicate_group_member', 'duplicate_members_row', 'nested_pad_group', 'duplicate_ref'])
def test_literal_identity_cannot_be_lost_or_repaired_by_native_loader(tmp_path, fault):
    mapped, source, selections = pair(tmp_path)
    text = source.read_text(); spans = raw.inventory(text)
    b = pcbnew.LoadBoard(str(source)); g = next(iter(b.Groups())); fp = next(iter(b.GetFootprints()))
    guide = next(i for i in g.GetItems() if i.GetClass() == 'PCB_SHAPE')
    if fault in ('root_duplicate', 'duplicate_ref'):
        a,z=spans[selections[0][0]]; duplicate=text[a:z]
        if fault == 'duplicate_ref':
            # New real identities, but the native label would no longer
            # uniquely name its actual component in the current board.
            import uuid
            import re
            duplicate=re.sub(r'\(uuid "?([0-9a-f-]+)"?\)', lambda m:'(uuid "'+str(uuid.uuid4())+'")', duplicate)
        text=text[:text.rfind(')')]+duplicate+text[text.rfind(')'):]
    elif fault == 'nested_pad_duplicate':
        pad=next(iter(fp.Pads())); text=text.replace(force._uid(pad), selections[0][0], 1)
    elif fault in ('missing_owner', 'missing_guide'):
        a,z=spans[selections[0][0] if fault=='missing_owner' else force._uid(guide)];text=text[:a]+text[z:]
    elif fault == 'duplicate_group_member':
        text=text.replace('(members', '(members "'+force._uid(guide)+'"', 1)
    elif fault == 'duplicate_members_row':
        text=text.replace('(members', '(members "'+force._uid(guide)+'") (members', 1)
    elif fault == 'nested_pad_group':
        import uuid
        pad=next(iter(fp.Pads()));other='(group "pad-owner" (uuid "'+str(uuid.uuid4())+'") (members "'+force._uid(pad)+'"))'
        at=text.rfind(')');text=text[:at]+other+text[at:]
    source.write_text(text)
    with pytest.raises(ValueError): query(mapped, source, selections)


@pytest.mark.parametrize('fault', ['sidecar', 'stack', 'native_floor', 'fab_floor'])
def test_process_and_current_fab_floor_signatures_must_remain_exact(tmp_path, monkeypatch, fault):
    mapped, source, selections = pair(tmp_path)
    if fault == 'sidecar': source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault == 'stack':
        b=pcbnew.LoadBoard(str(source)); b.SetCopperLayerCount(6); save(b, source)
    else:
        process=op._process
        def changed(path, board, tree):
            q=process(path, board, tree)
            if path==source:
                if fault=='native_floor':q['native_silk_floors_nm'][2]+=1
                else:q['cardinal_rules']['silk_clearance']+=.001
            return q
        monkeypatch.setattr(op,'_process',changed)
    with pytest.raises(ValueError, match='process_or_fab_floors_changed'): query(mapped, source, selections)


@pytest.mark.parametrize('fault', ['mapped', 'source', 'family', 'code', 'dependency'])
def test_final_entry_exit_bindings_refuse_stale_evidence(tmp_path, monkeypatch, fault):
    mapped, source, selections = pair(tmp_path); boundary=op._boundary; state={'done':False}
    epoch=op.force._code_identity; dependencies=op._dependencies
    def observed(path, *args):
        result=boundary(path,*args)
        if path==source:
            state['done']=True
            if fault in ('mapped','source'):
                target=mapped if fault=='mapped' else source; target.write_bytes(target.read_bytes()+b'\n')
            elif fault=='family':source.with_suffix('.kicad_dru').write_text('(version 1)\n')
        return result
    monkeypatch.setattr(op,'_boundary',observed)
    if fault=='code':monkeypatch.setattr(op.force,'_code_identity',lambda:'stale' if state['done'] else epoch())
    if fault=='dependency':monkeypatch.setattr(op,'_dependencies',lambda:{'changed':'0'} if state['done'] else dependencies())
    with pytest.raises(ValueError,match='Source_family_or_code_changed'):query(mapped,source,selections)


@pytest.mark.parametrize('seconds', [True, 0, -1, 10.0001, float('nan'), float('inf'), 1e-12])
def test_exact_original_finite_lease_required(tmp_path, seconds):
    mapped, source, selections = pair(tmp_path)
    with pytest.raises(ValueError): query(mapped, source, selections, timeout_s=seconds)


@pytest.mark.parametrize('fault', ['empty', 'duplicates', 'duplicate_owner', 'duplicate_group', 'missing_owner',
    'missing_group', 'dict', 'bool', 'too_many', 'caller_exceptions'])
def test_only_bounded_owner_group_query_parameters(tmp_path, fault):
    mapped, source, selections = pair(tmp_path); owner,group=selections[0]; extra={}
    if fault=='empty':selections=[]
    elif fault=='duplicates':selections*=2
    elif fault=='duplicate_owner':selections.append((owner,'other'))
    elif fault=='duplicate_group':selections.append(('other',group))
    elif fault=='missing_owner':selections=[('other',group)]
    elif fault=='missing_group':selections=[(owner,'other')]
    elif fault=='dict':selections={owner:group}
    elif fault=='bool':selections=[(True,group)]
    elif fault=='too_many':selections=[(str(i),str(i+1000))for i in range(129)]
    elif fault=='caller_exceptions':extra={'ignored_uuids':[owner]}
    with pytest.raises((TypeError,ValueError)):query(mapped,source,selections,**extra)


def test_missing_or_identical_saved_boundary_refuses(tmp_path):
    mapped, source, selections = pair(tmp_path)
    with pytest.raises(ValueError):query(mapped,mapped,selections)
    with pytest.raises(FileNotFoundError):query(mapped,tmp_path/'missing.kicad_pcb',selections)


def test_original_deadline_still_applies_after_both_boundaries(tmp_path,monkeypatch):
    mapped,source,selections=pair(tmp_path);boundary=op._boundary;clock=op.time.monotonic;state={'done':False}
    now=clock()
    def observed(path,*args):
        result=boundary(path,*args)
        if path==source:state['done']=True
        return result
    monkeypatch.setattr(op,'_boundary',observed)
    monkeypatch.setattr(op.time,'monotonic',lambda:now+20 if state['done'] else now)
    with pytest.raises(ValueError,match='deadline'):query(mapped,source,selections)
