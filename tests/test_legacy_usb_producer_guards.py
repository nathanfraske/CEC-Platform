import ast,pathlib,runpy,sys
from unittest import mock
import pytest
import cec_beta_manifest as manifest
import cec_legacy_output_guard as guard
import cec_fix_eps_rev3_bom_fields as fix

ROOT=pathlib.Path(manifest.__file__).resolve().parent.parent
STAGE=pathlib.Path(__file__).parents[1]
OLD_FP='cec-Connector_USB:USB_C_Receptacle_XKB_U262-16XN-4BVC11'
NEW_FP='cec-Connector_USB:USB_C_Receptacle_GCT_USB4215-03-A'


def text(mpn='U262-161N-4BVC11',footprint=OLD_FP,lcsc='C2765186',ref='J5'):
    properties={'Reference':ref,'Value':'not selection authority','MPN':mpn,
        'Footprint':footprint,'LCSC':lcsc,'Manufacturer':'UNCHANGED-UNTIL-EXACT',
        'Datasheet':'https://example.invalid/stale'}
    return '(kicad_sch\n  (lib_symbols)\n  (symbol\n    (lib_id "x:J")\n    (at 1 2 0)\n'+''.join(
        '    (property "'+k+'" "'+v+'" (at 1 2 0))\n'
        for k,v in properties.items())+'  )\n)'


@pytest.mark.parametrize('ref',['J5','RENAMED_SOURCE','EXT_92'])
def test_exact_old_mpn_and_footprint_evidence_repairs_without_ref_inference(ref):
    source=text(ref=ref);after,changed=fix.repair_text(source)
    assert changed==[ref] and '(property "LCSC" "C319148"' in after
    assert '(property "Footprint" "'+OLD_FP+'"' in after
    assert fix.repair_text(after)==(after,[])


@pytest.mark.parametrize('mpn,fp,lcsc',[
    ('USB4215-03-A',NEW_FP,'C37616412'),
    ('OTHER-SELECTED',OLD_FP,'C999999'),
    ('U262-161N-4BVC11',NEW_FP,'C319148'),
    ('USB4215-03-A',OLD_FP,'C37616412'),
    ('',OLD_FP,''),('UNKNOWN','unknown:package',''),
])
@pytest.mark.parametrize('ref',['J5','UNRELATED_NAME'])
def test_new_or_unknown_selection_fields_are_not_forced(mpn,fp,lcsc,ref):
    source=text(mpn,fp,lcsc,ref);assert fix.repair_text(source)==(source,[])


def test_actual_manifest_atx_destination_refuses_before_writer_is_called():
    entry=manifest.BY_BOARD['atx-24pin-rev3'];target=ROOT/'beta'/entry['directory']/entry['schematic']
    writer=mock.Mock()
    with pytest.raises(ValueError,match='current_manifest_output_forbidden'):
        destination=guard.require_safe_destination(target,root=ROOT);writer(destination)
    writer.assert_not_called()  # No file access/write against actual BETA.


@pytest.mark.parametrize('relative',['beta/atx-24pin-rev3/renamed.kicad_sch',
    'beta/atx-24pin-rev3/nested/service.kicad_sch',
    'beta/output-daughterboards/eps-out-db/new.kicad_sch'])
def test_whole_manifest_source_family_is_protected(tmp_path,relative):
    with pytest.raises(ValueError,match='current_manifest_output_forbidden'):
        guard.require_safe_destination(tmp_path/relative,root=tmp_path)


def test_symlink_parent_alias_cannot_bypass_family_guard(tmp_path):
    protected=tmp_path/'beta/atx-24pin-rev3';protected.mkdir(parents=True)
    alias=tmp_path/'looks-like-scratch';alias.symlink_to(protected,target_is_directory=True)
    with pytest.raises(ValueError,match='current_manifest_output_forbidden'):
        guard.require_safe_destination(alias/'new.kicad_sch',root=tmp_path)


@pytest.mark.parametrize('relative',['build/bootstrap/new.kicad_sch',
    'old-revisions/bootstrap/new.kicad_sch','external-temp/new.kicad_sch'])
def test_archived_and_temporary_bootstrap_destinations_allowed_without_side_effect(tmp_path,relative):
    target=tmp_path/relative;resolved=guard.require_safe_destination(target,root=tmp_path)
    assert resolved==target.resolve() and not target.exists()
    target.parent.mkdir(parents=True,exist_ok=True);resolved.write_text('synthetic bootstrap only')
    assert resolved.read_text()=='synthetic bootstrap only'


def test_atx_generator_default_refuses_before_loading_legacy_generator(monkeypatch):
    generator=STAGE/'scripts/gen-24pin-rev3.py'
    monkeypatch.setattr(sys,'argv',[str(generator)])
    with mock.patch('importlib.import_module',side_effect=AssertionError('must not load legacy generator')):
        with pytest.raises(ValueError,match='current_manifest_output_forbidden'):
            runpy.run_path(str(generator),run_name='__main__')


def test_guard_precedes_first_legacy_import_and_schematic_write_in_staged_generator():
    tree=ast.parse((STAGE/'scripts/gen-24pin-rev3.py').read_text())
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
    protected=next(n.lineno for n in calls if isinstance(n.func,ast.Name)
        and n.func.id=='require_safe_destination')
    legacy=next(n.lineno for n in calls if isinstance(n.func,ast.Attribute)
        and n.func.attr=='import_module')
    write=next(n.lineno for n in calls if isinstance(n.func,ast.Attribute)
        and n.func.attr=='build_schematic')
    assert protected<legacy<write
