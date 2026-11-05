"""Real project library parity must survive relocation without suppressions."""
import json
from pathlib import Path

import pytest

import cec_native_library_context as context
import cec_native_drc_runner as runner


def fixture(tmp_path, *, nickname='renamed-vendor', item='part', missing=False, flags=''):
    project=tmp_path/'canonical';project.mkdir()
    library=tmp_path/'library.pretty';library.mkdir()
    if not missing:
        (library/(item+'.kicad_mod')).write_text('(footprint "part" (version 20241229) (generator pcbnew) (layer "F.Cu"))')
    table=project/'fp-lib-table'
    table.write_text('(fp_lib_table (version 7) (lib (name '+json.dumps(nickname)+')'
        '(type "KiCad")(uri "${KIPRJMOD}/../library.pretty")(options "")(descr "source")'+flags+'))')
    private=tmp_path/'candidate';private.mkdir()
    board=private/'different-name.kicad_pcb'
    board.write_text('(kicad_pcb (footprint '+json.dumps(nickname+':'+item)+' (layer "B.Cu")))')
    return board,table,library


def test_relocation_binds_real_authority_files_without_changing_source_or_user_config(tmp_path):
    board,table,library=fixture(tmp_path)
    before={p:p.read_bytes() for p in (board,table,library/'part.kicad_mod')}
    incoming={'KICAD_CONFIG_HOME':str(tmp_path/'user-settings'), 'OTHER':'preserved'}
    with context.prepare(board,library_table=table,environment=incoming) as (env,proof,verify):
        assert env['KICAD_CONFIG_HOME']!=incoming['KICAD_CONFIG_HOME'] and env['OTHER']=='preserved'
        private=Path(proof['private_table'])
        assert str(library.resolve()) in private.read_text() and '${KIPRJMOD}' not in private.read_text()
        assert proof['authority']['references']==[('renamed-vendor','part')]
        assert proof['authority']['referenced_files'][str(library/'part.kicad_mod')]['sha256']
        assert not proof['source_and_context_unchanged'];verify()
        assert proof['source_and_context_unchanged'] and proof['findings_suppressed']==0
    assert not private.exists() and not (tmp_path/'user-settings').exists()
    assert incoming['KICAD_CONFIG_HOME']==str(tmp_path/'user-settings')
    assert all(p.read_bytes()==b for p,b in before.items())


@pytest.mark.parametrize('changed',['table','item','directory','private_table','local_table'])
def test_mid_run_source_or_context_changes_cannot_claim_complete(tmp_path,changed):
    board,table,library=fixture(tmp_path)
    with context.prepare(board,library_table=table,environment={}) as (_,proof,verify):
        target={'table':table,'item':library/'part.kicad_mod','directory':library/'new.kicad_mod',
                'private_table':Path(proof['private_table']), 'local_table':board.parent/'fp-lib-table'}[changed]
        target.write_text('changed')
        with pytest.raises(ValueError):verify()


@pytest.mark.parametrize('change',[
    ('${KIPRJMOD}/../library.pretty','${UNKNOWN}/parts.pretty'),
    ('${KIPRJMOD}/../library.pretty','relative/parts.pretty'),
    ('${KIPRJMOD}/../library.pretty','https://host/parts.pretty'),
    ('(type "KiCad")','(type "Github")'),
    ('(options "")','(options "unbound-option")'),
    ('(version 7)','(version 999)'),
    ('(name "renamed-vendor")','(name "renamed-vendor")(name "duplicate")'),
])
def test_ambiguous_remote_unresolved_or_non_native_authority_refuses(tmp_path,change):
    board,table,_=fixture(tmp_path);table.write_text(table.read_text().replace(*change))
    with pytest.raises(ValueError):
        with context.prepare(board,library_table=table,environment={}):pass


def test_duplicate_alias_refuses_even_when_directories_are_identical(tmp_path):
    board,table,_=fixture(tmp_path)
    table.write_text(table.read_text()[:-1]+table.read_text().split('(lib ',1)[1].join(['(lib ','']))
    with pytest.raises(ValueError):
        with context.prepare(board,library_table=table,environment={}):pass


@pytest.mark.parametrize('flags',['','(disabled)','(hidden)'])
def test_missing_items_and_disabled_libraries_are_not_synthesized_or_enabled(tmp_path,flags):
    board,table,library=fixture(tmp_path,missing=True,flags=flags)
    with context.prepare(board,library_table=table,environment={}) as (_,proof,verify):
        row=proof['authority']['rows']['renamed-vendor']
        assert row['enabled']==('(disabled)' not in flags)
        assert flags in Path(proof['private_table']).read_text()
        if row['enabled']:
            assert proof['authority']['referenced_files'][str(library/'part.kicad_mod')]['sha256'] is None
        verify()


def test_missing_alias_remains_missing_not_reconstructed_from_embedded_board(tmp_path):
    board,table,_=fixture(tmp_path)
    table.write_text(table.read_text().replace('(name "renamed-vendor")','(name "other")'))
    with context.prepare(board,library_table=table,environment={}) as (_,proof,verify):
        assert 'renamed-vendor' not in proof['authority']['rows']
        assert not proof['authority']['referenced_files'];verify()


def test_conflicting_candidate_project_table_cannot_override_authority(tmp_path):
    board,table,_=fixture(tmp_path)
    (board.parent/'fp-lib-table').write_text(table.read_text().replace('library.pretty','other.pretty'))
    with pytest.raises(ValueError,match='conflicting_candidate'):
        with context.prepare(board,library_table=table,environment={}):pass


def test_unbound_legacy_invocation_is_honest_and_does_not_change_environment(tmp_path):
    board=tmp_path/'board.kicad_pcb';board.write_text('(kicad_pcb)')
    with context.prepare(board,environment={'A':'B'}) as (env,proof,verify):
        assert env=={'A':'B'} and not proof['bound'] and not proof['isolated'];verify()


def test_external_path_variables_are_resolved_and_bound_not_inherited_from_user_json(tmp_path):
    board,table,library=fixture(tmp_path)
    table.write_text(table.read_text().replace('${KIPRJMOD}/../library.pretty','${PINNED_PARTS}'))
    with context.prepare(board,library_table=table,environment={'PINNED_PARTS':str(library)}) as (_,proof,verify):
        assert proof['authority']['variables']=={'PINNED_PARTS':str(library)};verify()


def test_whole_stage_epoch_and_each_native_producer_bind_the_same_library_authority(tmp_path):
    board,table,library=fixture(tmp_path)
    queued=context.authority(board,table,environment={})
    with context.prepare(board,library_table=table,environment={}) as (_,proof,verify):
        assert queued==proof['authority'];verify()
    (library/'part.kicad_mod').write_text('a changed actual footprint')
    assert queued!=context.authority(board,table,environment={})


def test_actual_native_checker_uses_real_relocated_library_and_reports_actual_mismatch(tmp_path):
    import pcbnew
    import cec_field_coupling as field
    import cec_swig_guard;cec_swig_guard.pin()
    board,table,library=fixture(tmp_path)
    native=pcbnew.BOARD();native.SetCopperLayerCount(6)
    fp=pcbnew.FootprintLoad(str(library),'part');assert fp
    fp.SetFPID(pcbnew.LIB_ID('renamed-vendor','part'));fp.SetPosition(pcbnew.VECTOR2I_MM(10,10));native.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);fp.Add(pad)
    for start,end in [((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))]:
        shape=pcbnew.PCB_SHAPE(native);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetStart(pcbnew.VECTOR2I_MM(*start));shape.SetEnd(pcbnew.VECTOR2I_MM(*end));native.Add(shape)
    field._save_field_snapshot(native,board);original=board.read_bytes()
    produced=runner.run(board,tmp_path/'real-native.json',footprint_table=table)
    assert produced['ok'],produced
    report=json.loads((tmp_path/'real-native.json').read_text())
    types={r['type'] for r in report['violations']}
    assert 'lib_footprint_issues' not in types and 'lib_footprint_mismatch' in types
    assert produced['native_library_context']['source_and_context_unchanged']
    assert board.read_bytes()==original and produced['faults_suppressed']==0
