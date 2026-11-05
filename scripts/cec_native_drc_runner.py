"""Bound native DRC production, including an optional cap-only reporting build.

The installed toolchain is untouched. An explicit private KiCad 10.0.5 build
must match the official commit with exactly the two approved reporting-cap
changes, and its actual loaded PCB module and runtime files are hash-bound.
All-track/all-severity reporting is mandatory. No rules, source copper,
factory tolerances, current budgets, exclusions or admission gates are edited.
"""
import hashlib
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

import cec_native_drc_inventory as inventory
import cec_native_library_context as library_context
import cec_native_rule_validity as rule_validity
import cec_toolchain as toolchain

OFFICIAL_COMMIT='18fb9289ff0efdca53c0352ed81a0973f0a6b58c'
ENGINE_SOURCE='pcbnew/drc/drc_engine.cpp'
REPORTING_LIMIT=20000
MAX_REPORT_BYTES=32*1024*1024


def _hash(path,*,limit=512*1024*1024):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>limit:raise ValueError('bounded_native_producer_file_required')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def _cap_only_source(official):
    old=['#define ERROR_LIMIT 199\n','#define EXTENDED_ERROR_LIMIT 499\n']
    if type(official) is not str or any(official.count(line)!=1 for line in old):
        raise ValueError('official_native_report_limit_source_not_verified')
    return official.replace(old[0],'#define ERROR_LIMIT 20000\n').replace(old[1],'#define EXTENDED_ERROR_LIMIT 20000\n')


def _describe_build(root):
    root=Path(root).resolve();source=root/'src';build=root/'build'
    if os.name!='posix' or not Path('/proc/self/maps').is_file():
        raise ValueError('private_native_reporting_build_requires_live_linux_module_proof')
    def git(*arguments):
        p=subprocess.run(['git','-C',str(source),*arguments],capture_output=True,text=True,timeout=10)
        if p.returncode:raise ValueError('native_reporting_build_source_inventory_failed')
        return p.stdout
    if (git('rev-parse','HEAD').strip()!=OFFICIAL_COMMIT or git('diff','HEAD','--name-only').splitlines()!=[ENGINE_SOURCE]
            or git('ls-files','--others','--exclude-standard').strip()):
        raise ValueError('native_reporting_build_has_unverified_source_changes')
    official=git('show','HEAD:'+ENGINE_SOURCE);expected=_cap_only_source(official)
    if (source/ENGINE_SOURCE).read_text()!=expected:raise ValueError('native_reporting_build_is_not_exact_cap_only_source')
    cli=build/'kicad/kicad-cli';engine=build/'pcbnew/_pcbnew.kiface'
    files=[cli,engine,build/'common/libkicommon.so.10.0.5',build/'common/gal/libkigal.so.10.0.5',
        build/'api/libkiapi.so.10.0.5',build/'3d-viewer/3d_cache/sg/libkicad_3dsg.so.2.0.0']
    return dict(root=str(root),build=str(build),cli=str(cli),engine=str(engine),official_commit=OFFICIAL_COMMIT,
        source_sha256=_hash(source/ENGINE_SOURCE),patch_sha256=hashlib.sha256(git('diff','HEAD','--',ENGINE_SOURCE).encode()).hexdigest(),
        cmake_cache_sha256=_hash(build/'CMakeCache.txt'),artifacts={str(path.resolve()):_hash(path) for path in files},
        ordinary_report_limit=REPORTING_LIMIT,extended_report_limit=REPORTING_LIMIT,
        geometry_or_rule_source_changed=False,installed_toolchain_replaced=False)


def run(board,report_path,*,reporting_build=None,timeout_s=10.,board_hint=None,footprint_table=None):
    """Produce a fresh hash-bound read-only report; never grant release authority."""
    started=time.monotonic();result=dict(ok=False,complete=False,errors=[],release_authority=False,
        admission_unchanged=True,faults_suppressed=0,all_track_errors=True,severity_all=True)
    process=None;contexts=ExitStack()
    try:
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
            raise ValueError('native_drc_ten_second_deadline_required')
        board=Path(board).resolve();report_path=Path(report_path).resolve()
        if (not board.is_file() or board.suffix!='.kicad_pcb' or report_path.exists()
                or report_path.suffix!='.json' or report_path==board
                or report_path.parent==board.parent and report_path.name.startswith(board.stem+'.')):
            raise ValueError('fresh_private_native_report_output_required')
        source_files={str(path):_hash(path) if path.is_file() else None
            for path in (board,board.with_suffix('.kicad_pro'),board.with_suffix('.kicad_dru'))}
        profile=_describe_build(reporting_build) if reporting_build is not None else None
        cli=profile['cli'] if profile else toolchain.require_kicad_cli('complete native DRC reporting')
        cli_hash=_hash(cli);env=os.environ.copy()
        if profile:env['KICAD_RUN_FROM_BUILD_DIR']='1'
        else:env.pop('KICAD_RUN_FROM_BUILD_DIR',None)
        if board_hint is not None:
            if type(board_hint) is not str or not board_hint:
                raise ValueError('explicit_native_board_hint_required')
            import cec_synth_pipeline as synth
            declared=Path(synth.Config.load(board_hint).dir)/'fp-lib-table'
            if footprint_table is not None and Path(footprint_table).resolve()!=declared.resolve():
                raise ValueError('native_board_hint_and_library_table_conflict')
            footprint_table=declared
        env,libraries,verify_libraries=contexts.enter_context(library_context.prepare(
            board,library_table=footprint_table,environment=env))
        report_path.parent.mkdir(parents=True,exist_ok=True)
        command=[str(cli),'pcb','drc','--format','json','--severity-all','--all-track-errors','--output',str(report_path),str(board)]
        rules=board.with_suffix('.kicad_dru')
        if rules.is_file():
            normalized=rule_validity.normalize_conditions(rules.read_text())
            if normalized['changed_conditions']:
                raise ValueError('invalid_multiline_custom_rule_conditions_require_formatting_only_repair')
        if profile:
            rules_proof=rule_validity.probe(command,env=env,engine=profile['engine'],timeout_s=timeout_s)
            if report_path.exists():raise ValueError('native_rule_observer_did_not_stop_before_tests')
        elif rules.is_file():
            raise ValueError('custom_rule_validation_requires_verified_observable_native_engine')
        else:
            rules_proof=dict(ok=True,complete=True,custom_rules_present=False,
                implicit_rule_compilation_observed=False,release_authority=False)
        loaded=set();engine_observed=False;native_started=time.monotonic()
        with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
            process=subprocess.Popen(command,env=env,stdout=stdout,stderr=stderr)
            while process.poll() is None:
                if profile:
                    try:
                        mapping=Path('/proc',str(process.pid),'maps').read_text()
                        if len(mapping)>4*1024*1024:raise ValueError('native_module_map_bound')
                        for line in mapping.splitlines():
                            if profile['build'] in line:
                                loaded.add(line.split(None,5)[-1])
                        engine_observed |= profile['engine'] in loaded
                        if len(loaded)>32:raise ValueError('native_loaded_artifact_bound')
                    except FileNotFoundError:pass
                if time.monotonic()-native_started>timeout_s:
                    raise TimeoutError('native_drc_ten_second_deadline')
                time.sleep(.01)
            process.wait(timeout=1)
            stdout.seek(0);stderr.seek(0)
            output=stdout.read(65536).decode(errors='replace');error=stderr.read(65536).decode(errors='replace')
        if process.returncode!=0:raise ValueError('native_drc_producer_failed:'+str(process.returncode)+':'+error[:2000])
        if profile and not engine_observed:raise ValueError('private_native_pcb_engine_not_observed')
        report_hash=_hash(report_path,limit=MAX_REPORT_BYTES);native=json.loads(report_path.read_text())
        if profile:
            if _describe_build(reporting_build)!=profile:raise ValueError('native_reporting_build_changed_during_run')
            assessment=inventory._assess_verified_limits(native,REPORTING_LIMIT,REPORTING_LIMIT,
                dict(official_source=inventory.PRIMARY_SOURCE,official_commit=OFFICIAL_COMMIT,
                    cap_only_patch_sha256=profile['patch_sha256'],actual_loaded_engine_sha256=profile['artifacts'][profile['engine']]))
        else:assessment=inventory.assess(native)
        if assessment['errors']:raise ValueError('native_report_inventory_unknown:'+str(assessment['errors']))
        if cli_hash!=_hash(cli) or any((None if not Path(path).is_file() else _hash(path))!=digest for path,digest in source_files.items()):
            raise ValueError('native_report_source_family_or_producer_changed')
        verify_libraries()
        result.update(ok=True,complete=True,source_files=source_files,command=command,cli_sha256=cli_hash,
            reporting_build=profile,actual_private_modules_observed=sorted(loaded),report=str(report_path),
            report_sha256=report_hash,native_inventory=assessment,native_elapsed_s=round(time.monotonic()-native_started,6),
            source_and_producer_unchanged=True,producer_stdout=output,producer_stderr=error,
            native_rules_validation=rules_proof,native_library_context=libraries)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=1)
        contexts.close()
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result
