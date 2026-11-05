"""Relayering annotation fields is not text, component or copper authority."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_manufacturing_legend_policy as legend
import cec_field_coupling as field
import cec_force_current as force


def fixture(tmp_path, *, turn=0, back=False, kind='C', alias='MPN'):
    b = pcbnew.BOARD(); b.SetCopperLayerCount(6)
    namespace = {'C': 'Capacitor_SMD', 'R': 'Resistor_SMD'}[kind]
    fp = pcbnew.FootprintLoad(str(Path(__file__).resolve().parents[1] / 'lib/vendor' /
                                (namespace + '.pretty')), kind + '_0402_1005Metric')
    assert fp is not None
    b.Add(fp); fp.SetReference('ARBITRARY_781'); fp.SetValue('authored value unchanged')
    fp.SetField(alias, 'unrelated manufacturer number'); fp.SetField('Datasheet', 'https://invalid.example/retained')
    if back: fp.Flip(pcbnew.VECTOR2I(0, 0), False)
    fp.SetOrientationDegrees(turn); fp.SetPosition(pcbnew.VECTOR2I_MM(20, 20))
    for label in fp.GetFields():
        if label.GetName() in ('Reference', 'Value', alias):
            label.SetLayer(pcbnew.B_Fab if back else pcbnew.F_Fab)
            label.SetVisible(label.GetName() != alias)
    fp.Value().SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    fp.GetField(alias).SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    n = pcbnew.NETINFO_ITEM(b, 'RENAMED_NOT_A_BOARD_POLICY'); b.Add(n)
    for pad in fp.Pads(): pad.SetNet(n)
    track = pcbnew.PCB_TRACK(b); track.SetNet(n); track.SetWidth(200000); track.SetLayer(pcbnew.In2_Cu)
    track.SetStart(pcbnew.VECTOR2I_MM(3, 3)); track.SetEnd(pcbnew.VECTOR2I_MM(4, 3)); b.Add(track)
    source = tmp_path / 'source.kicad_pcb'; field._save_field_snapshot(b, source)
    return source, force._uid(fp)


def saved(tmp_path, **options):
    source, uid = fixture(tmp_path, **options)
    proposal = legend.plan(source, policy=legend.POLICY, board_hint='opaque',
                           mpn_field_names=[options.get('alias', 'MPN')])
    proposal = json.loads(json.dumps(proposal))
    board = legend.construct(source, proposal)
    candidate = force._copy_family(source, tmp_path / 'private')
    field._save_field_snapshot(board, candidate)
    return source, candidate, proposal, uid


@pytest.mark.parametrize('policy',[legend.POLICY,legend.READABLE_POLICY])
@pytest.mark.parametrize('back',[False,True])
def test_literal_writer_preserves_empty_metadata_and_unselected_implicit_fonts(tmp_path,policy,back):
    import uuid
    import cec_source_retaining_ses_import as raw
    source,uid=fixture(tmp_path,back=back)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    fp.Value().SetMirrored(not back);field._save_field_snapshot(b,source)
    text=source.read_text();a,z=raw.inventory(text)[uid];node=text[a:z]
    metadata='''
      (property "Datasheet" "" (at 0 0 0) (layer "F.Fab")
        (uuid "EMPTY_ID") (hide yes) (effects (font (size 1 1))))
      (property "Manufacturer" "opaque source data" (at 0 0 0) (layer "F.Fab")
        (uuid "MAKER_ID") (hide yes) (effects (font (size 1 1))))
'''.replace('EMPTY_ID',str(uuid.uuid4())).replace('MAKER_ID',str(uuid.uuid4()))
    # Replace rather than duplicate the ordinary fixture's Datasheet field.
    for i,j in reversed(raw.children(node)):
        if raw.kind(node[i:j])=='property' and node[i:j].split('"')[1]=='Datasheet':
            node=node[:i]+node[j:]
    node=node[:node.rfind(')')]+metadata+node[node.rfind(')'):]
    source.write_text(text[:a]+node+text[z:]);before=source.read_bytes()
    q=legend.plan(source,policy=policy,board_hint='opaque')
    child=force._copy_family(source,tmp_path/'literal-child');legend.write_private(source,child,q)
    assert metadata in child.read_text()and source.read_bytes()==before
    r=legend.receive(source,child,q,board_hint='opaque');assert r['ok']and r['complete'],r
    assert not legend.plan(child,policy=policy,board_hint='opaque')['records']
    # A subsequent full serialization must NOT become repair authority for
    # precisely the opaque metadata the writer was introduced to preserve.
    field._save_field_snapshot(pcbnew.LoadBoard(str(child)),child)
    assert not legend.receive(source,child,q,board_hint='opaque')['ok']


def test_literal_writer_refuses_nonexact_copy_and_forged_plan(tmp_path):
    source,_=fixture(tmp_path);q=legend.plan(source,policy=legend.POLICY,board_hint='opaque')
    with pytest.raises(ValueError):legend.write_private(source,source,q)
    child=force._copy_family(source,tmp_path/'bad-copy');child.write_text(child.read_text()+'\n; unrelated edit\n')
    with pytest.raises(ValueError):legend.write_private(source,child,q)
    child=force._copy_family(source,tmp_path/'forged');q['records'][0]['target_layer']=pcbnew.F_Cu
    with pytest.raises(ValueError):legend.write_private(source,child,q)


@pytest.mark.parametrize('kind', ['C', 'R'])
@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('alias', ['MPN', 'Manufacturer Part Number'])
def test_exact_native_labels_relayer_on_both_faces_all_rotations(tmp_path, kind, turn, back, alias):
    source, candidate, proposal, uid = saved(tmp_path, kind=kind, turn=turn, back=back, alias=alias)
    old = force._hash(source)
    proof = legend.receive(source, candidate, proposal, board_hint='opaque')
    assert proof['ok'] and proof['complete'] and proof['changed'], proof
    assert len(proof['changed_field_uuids']) == 3 and proof['modified_footprint_uuids'] == [uid]
    assert proof['all_source_evidence_except_declared_field_layers_exact']
    assert proof['strings_fonts_poses_visibility_mirroring_bom_netlist_copper_and_rules_unchanged']
    assert force._hash(source) == old and not proof['release_authority']
    again = legend.plan(candidate, policy=legend.POLICY, board_hint='opaque', mpn_field_names=[alias])
    assert not again['records']
    board = pcbnew.LoadBoard(str(candidate)); fp = next(iter(board.GetFootprints()))
    assert fp.Reference().GetLayer() == (pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    assert fp.Value().GetLayer() == fp.GetField(alias).GetLayer() == (pcbnew.B_Fab if back else pcbnew.F_Fab)
    assert not fp.GetField(alias).IsVisible()


@pytest.mark.parametrize('fault', ['text', 'size', 'stroke', 'visible', 'text_pose', 'mirroring', 'angle',
    'wrong_layer', 'unselected_metadata', 'pose', 'pad', 'track', 'body', 'fab', 'model', 'population'])
def test_saved_receiver_rejects_any_unowned_native_change(tmp_path, fault):
    source, candidate, proposal, uid = saved(tmp_path)
    b = pcbnew.LoadBoard(str(candidate)); fp = next(iter(b.GetFootprints())); label = fp.Value()
    if fault == 'text': label.SetText('changed')
    elif fault == 'size': label.SetTextSize(pcbnew.VECTOR2I_MM(.8, .8))
    elif fault == 'stroke': label.SetTextThickness(label.GetTextThickness() + 1)
    elif fault == 'visible': label.SetVisible(not label.IsVisible())
    elif fault == 'text_pose': label.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'mirroring': label.SetMirrored(not label.IsMirrored())
    elif fault == 'angle': label.SetTextAngle(pcbnew.EDA_ANGLE(1, pcbnew.DEGREES_T))
    elif fault == 'wrong_layer': label.SetLayer(pcbnew.B_Fab)
    elif fault == 'unselected_metadata': fp.GetField('Datasheet').SetLayer(pcbnew.F_SilkS)
    elif fault == 'pose': fp.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad': next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(.8, .8))
    elif fault == 'track': next(iter(b.GetTracks())).SetWidth(200001)
    elif fault in ('body', 'fab'):
        next(g for g in fp.GraphicalItems() if g.GetLayer() ==
             (pcbnew.F_SilkS if fault == 'body' else pcbnew.F_Fab)).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'model': fp.Models().clear()
    else: fp.SetDNP(True)
    field._save_field_snapshot(b, candidate)
    assert not legend.receive(source, candidate, proposal, board_hint='opaque')['ok']


@pytest.mark.parametrize('fault', ['group_field', 'copper_field', 'mask_field'])
def test_source_field_ownership_and_nonannotation_layers_refuse(tmp_path, fault):
    source, uid = fixture(tmp_path); b = pcbnew.LoadBoard(str(source)); fp = next(iter(b.GetFootprints()))
    label = fp.Value()
    if fault == 'group_field':
        g = pcbnew.PCB_GROUP(b); b.Add(g); g.AddItem(label)
    else: label.SetLayer(pcbnew.F_Cu if fault == 'copper_field' else pcbnew.F_Mask)
    field._save_field_snapshot(b, source)
    with pytest.raises(ValueError): legend.plan(source, policy=legend.POLICY, board_hint='opaque')


def test_native_inmemory_field_lock_refuses(tmp_path, monkeypatch):
    # KiCad does not serialize a footprint-field lock in this file format.
    # Test the actual accessible lock, not a saved fixture whose lock vanished.
    source, uid = fixture(tmp_path); board = pcbnew.LoadBoard(str(source))
    next(iter(board.GetFootprints())).Value().SetLocked(True)
    monkeypatch.setattr(legend.pcbnew, 'LoadBoard', lambda path: board)
    with pytest.raises(ValueError): legend.plan(source, policy=legend.POLICY, board_hint='opaque')


@pytest.mark.parametrize('ownership', ['locked_footprint', 'group_footprint'])
def test_stationary_footprint_ownership_preserved_not_pose_authority(tmp_path, ownership):
    source, uid = fixture(tmp_path); b = pcbnew.LoadBoard(str(source)); fp = next(iter(b.GetFootprints()))
    if ownership == 'locked_footprint': fp.SetLocked(True)
    else:
        g = pcbnew.PCB_GROUP(b); b.Add(g); g.AddItem(fp)
    field._save_field_snapshot(b, source)
    proposal = legend.plan(source, policy=legend.POLICY, board_hint='opaque')
    candidate = force._copy_family(source, tmp_path / 'private')
    field._save_field_snapshot(legend.construct(source, proposal), candidate)
    assert legend.receive(source, candidate, proposal, board_hint='opaque')['ok']


@pytest.mark.parametrize('options', [{'policy': None}, {'policy': 'inferred'}, {'board_hint': ''},
    {'board_hint': True}, {'mpn_field_names': []}, {'mpn_field_names': ['MPN', 'MPN']},
    {'mpn_field_names': ['Value']}, {'mpn_field_names': ['Datasheet']}, {'mpn_field_names': [' MPN']},
    {'mpn_field_names': True}, {'max_footprints': 0}, {'max_footprints': True}, {'max_footprints': 2049},
    {'timeout_s': True}, {'timeout_s': 0}, {'timeout_s': 11}, {'timeout_s': float('nan')}])
def test_bad_policy_domain_or_deadline_refuses_before_io(options):
    args = dict(policy=legend.POLICY, board_hint='opaque'); args.update(options)
    with pytest.raises(ValueError): legend.plan('missing', **args)


@pytest.mark.parametrize('fault', ['hash', 'field', 'target', 'text', 'scope', 'family', 'epoch'])
def test_forged_or_stale_plan_cannot_authorize_annotations(tmp_path, fault):
    source, candidate, proposal, uid = saved(tmp_path); forged = copy.deepcopy(proposal)
    if fault == 'hash': forged['source_sha256'] = '0' * 64
    elif fault == 'field': forged['records'][0]['field_uuid'] = 'missing'
    elif fault == 'target': forged['records'][0]['target_layer'] = pcbnew.F_Cu
    elif fault == 'text': forged['records'][0]['text'] = 'hidden replacement'
    elif fault == 'scope': forged['mpn_field_names'] = ['Unselected']
    elif fault == 'family': forged['source_family'] = {}
    else: forged['code_identity'] = {}
    with pytest.raises(ValueError): legend.construct(source, forged)
    assert not legend.receive(source, candidate, forged, board_hint='opaque')['ok']


def test_source_sidecar_change_is_not_annotation_authority(tmp_path):
    source, candidate, proposal, uid = saved(tmp_path)
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    assert not legend.receive(source, candidate, proposal, board_hint='opaque')['ok']


def test_original_hidden_reference_stays_hidden(tmp_path):
    source, uid = fixture(tmp_path); b = pcbnew.LoadBoard(str(source)); fp = next(iter(b.GetFootprints()))
    fp.Reference().SetVisible(False); field._save_field_snapshot(b, source)
    proposal = legend.plan(source, policy=legend.POLICY, board_hint='opaque')
    candidate = force._copy_family(source, tmp_path / 'private')
    field._save_field_snapshot(legend.construct(source, proposal), candidate)
    assert legend.receive(source, candidate, proposal, board_hint='opaque')['ok']
    board = pcbnew.LoadBoard(str(candidate))
    assert not next(iter(board.GetFootprints())).Reference().IsVisible()


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_explicit_readability_policy_rehomes_cross_face_fields_without_backwards_text(tmp_path,turn,back):
    source,uid=fixture(tmp_path,turn=turn,back=back)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    for label in (fp.Value(),fp.GetField('MPN')):
        label.SetLayer(pcbnew.F_SilkS if back else pcbnew.B_SilkS)
        label.SetMirrored(not back)
    field._save_field_snapshot(b,source);before=force._hash(source)
    proposal=legend.plan(source,policy=legend.READABLE_POLICY,board_hint='opaque')
    assert len([r for r in proposal['records'] if r['source_mirrored']!=r['target_mirrored']])==2
    candidate=force._copy_family(source,tmp_path/'readable')
    field._save_field_snapshot(legend.construct(source,proposal),candidate)
    proof=legend.receive(source,candidate,proposal,board_hint='opaque')
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_source_evidence_except_declared_field_layers_and_readability_mirroring_exact']
    assert not proof['strings_fonts_poses_visibility_mirroring_bom_netlist_copper_and_rules_unchanged']
    assert len(proof['declared_mirror_changes'])==2
    child=pcbnew.LoadBoard(str(candidate));owner=next(iter(child.GetFootprints()))
    for label in (owner.Reference(),owner.Value(),owner.GetField('MPN')):
        assert bool(label.IsMirrored())==back
    assert force._hash(source)==before and not proof['release_authority']
    assert not legend.plan(candidate,policy=legend.READABLE_POLICY,board_hint='opaque')['records']


def test_original_policy_remains_mirror_preserving_on_cross_face_fields(tmp_path):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    fp.Value().SetLayer(pcbnew.B_SilkS);fp.Value().SetMirrored(True)
    field._save_field_snapshot(b,source)
    q=legend.plan(source,policy=legend.POLICY,board_hint='opaque')
    child=legend.construct(source,q)
    assert next(iter(child.GetFootprints())).Value().IsMirrored()
    assert q['mirroring_unchanged']


@pytest.mark.parametrize('fault',['forged_plan','candidate_mirror','unselected_mirror','hidden_reference'])
def test_readability_policy_does_not_authorize_other_mirror_or_visibility_edits(tmp_path,fault):
    source,uid=fixture(tmp_path)
    q=legend.plan(source,policy=legend.READABLE_POLICY,board_hint='opaque')
    if fault=='forged_plan':
        forged=copy.deepcopy(q);forged['records'][0]['target_mirrored']=not forged['records'][0]['target_mirrored']
        with pytest.raises(ValueError):legend.construct(source,forged)
        return
    candidate=force._copy_family(source,tmp_path/'unowned')
    b=legend.construct(source,q);fp=next(iter(b.GetFootprints()))
    if fault=='candidate_mirror':fp.Value().SetMirrored(not fp.Value().IsMirrored())
    elif fault=='unselected_mirror':fp.GetField('Datasheet').SetMirrored(not fp.GetField('Datasheet').IsMirrored())
    else:fp.Reference().SetVisible(False)
    field._save_field_snapshot(b,candidate)
    assert not legend.receive(source,candidate,q,board_hint='opaque')['ok']


def test_native_reconstruction_cannot_silently_drop_literal_empty_source_group(tmp_path):
    source,uid=fixture(tmp_path)
    # Native KiCad omits empty groups on load/save. It is still authored
    # source evidence, not permission for an annotation relayer to delete it.
    import uuid
    raw=source.read_text();tail=raw.rfind(')')
    source.write_text(raw[:tail]+'(group "unrelated_source_owner" (uuid "'+str(uuid.uuid4())+'") (members))\n'+raw[tail:])
    q=legend.plan(source,policy=legend.READABLE_POLICY,board_hint='opaque')
    candidate=force._copy_family(source,tmp_path/'legacy-group')
    field._save_field_snapshot(legend.construct(source,q),candidate)
    proof=legend.receive(source,candidate,q,board_hint='opaque')
    assert not proof['ok'] and any('literal_source_evidence' in e for e in proof['errors']),proof
