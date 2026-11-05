"""Add missing registered manufacturer assets to an immutable print snapshot.

Only missing files under an existing enabled nickname may be added. Every
existing directory byte and table setting is retained; board material is not
edited. This is independently received library scope, not footprint geometry,
part selection, routing, current, thermal, assembly or release qualification.
The unmodified native checker must still compare the board against the result.
"""
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

import cec_force_current as force
import cec_manufacturer_land_pattern as patterns
import cec_native_library_context as libraries
import cec_source_retaining_ses_import as raw
import cec_source_literal_additions as literal

MAX_ASSETS=8
MAX_FILES=2048
MAX_BYTES=64*1024*1024


def _need(ok,reason):
    if not ok:raise ValueError(reason)


def _deadline(timeout_s):
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_additive_library_context_required')
    return time.monotonic()+timeout_s


def _tick(deadline):
    _need(time.monotonic()<deadline,'additive_library_context_deadline')


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _stable(value):
    """Canonical wire types; no geometry, authority or value is discarded."""
    return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def _registered():
    """Registration comes from stock manufacturer rules, never the caller."""
    identity=patterns.library_identity();result={}
    for rule in patterns.CATALOG.values():
        asset=(patterns._library(rule)/(rule['new']+'.kicad_mod')).resolve(strict=True)
        _need(asset.is_file()and not asset.is_symlink()and identity[str(asset)]==force._hash(asset),
            'registered_manufacturer_asset_missing_or_changed')
        if 'datasheet'in rule:
            drawing=(patterns.ROOT/rule['datasheet']).resolve(strict=True)
            _need(force._hash(drawing)==rule['datasheet_sha256'],
                'registered_manufacturer_primary_drawing_changed')
        row=dict(library=rule['library'],name=rule['new'],path=str(asset),
            sha256=identity[str(asset)],registration=dict(rule))
        _need(str(asset)not in result,'ambiguous_registered_manufacturer_asset')
        result[str(asset)]=row
    return result,identity


def _directory(path,deadline):
    path=Path(path)
    _need(path.is_dir()and not path.is_symlink(),'ordinary_source_library_directory_required')
    entries=sorted(path.iterdir());_need(0<=len(entries)<=MAX_FILES,'additive_library_file_bound')
    names=[p.name for p in entries]
    _need(len({n.casefold()for n in names})==len(names),'case_ambiguous_library_files_refused')
    result={};total=0
    for p in entries:
        _tick(deadline)
        _need(p.is_file()and not p.is_symlink(),'flat_ordinary_source_library_files_required')
        size=p.stat().st_size;total+=size
        _need(size<=libraries.MAX_ITEM_BYTES and total<=MAX_BYTES,'additive_library_byte_bound')
        result[p.name]=dict(bytes=size,sha256=force._hash(p))
    return result


def plan(board,table,*,asset_paths,timeout_s=10.):
    """Declare exact absent registered files; existing files cannot be replaced."""
    deadline=_deadline(timeout_s);board=Path(board).resolve(strict=True);table=Path(table).resolve(strict=True)
    _need(board.is_file()and board.suffix=='.kicad_pcb','saved_source_board_required')
    _need(type(asset_paths)in(list,tuple)and 1<=len(asset_paths)<=MAX_ASSETS
        and all(type(p)is str and p for p in asset_paths),'finite_explicit_manufacturer_assets_required')
    paths=sorted(str(Path(p).resolve(strict=True))for p in asset_paths)
    _need(len(paths)==len(set(paths)),'unique_manufacturer_assets_required')
    source_sha=force._hash(board);code=force._code_identity();registered,assets=_registered()
    context=libraries.authority(board,table);groups={}
    for path in paths:
        _tick(deadline);_need(path in registered,'unregistered_library_asset_refused')
        row=registered[path];name=row['library'];filename=row['name']+'.kicad_mod'
        parent=context['rows'].get(name)
        _need(parent is not None and parent['enabled'],'existing_enabled_source_library_nickname_required')
        _need((name,row['name'])in map(tuple,context['references']),
            'registered_asset_must_be_referenced_by_actual_source')
        folder=Path(parent['path'])
        _need(not (folder/filename).exists()and not (folder/filename).is_symlink(),
            'only_missing_library_assets_may_be_added')
        group=groups.setdefault(name,dict(source_directory=str(folder),files=_directory(folder,deadline),additions=[]))
        _need(filename.casefold()not in {n.casefold()for n in group['files']},
            'case_shadowing_existing_library_asset_refused')
        group['additions'].append(row)
    for name,group in groups.items():
        group['additions'].sort(key=lambda r:r['name'])
        group['directory_name']='library-'+_digest(dict(library=name,source=group))[:24]+'.pretty'
    _need(force._hash(board)==source_sha and code==force._code_identity()
        and context==libraries.authority(board,table)and assets==_registered()[1],
        'source_or_registered_library_context_changed')
    for group in groups.values():
        _need(group['files']==_directory(group['source_directory'],deadline),'source_library_directory_changed')
    _tick(deadline)
    return _stable(dict(schema=1,scope='missing_registered_manufacturer_asset_addition_only',
        board=str(board),board_sha256=source_sha,source_table=str(table),asset_paths=paths,
        timeout_s=timeout_s,code_identity=code,registered_asset_identities=assets,
        source_library_context=context,libraries=groups,release_authority=False,
        no_board_or_existing_library_material_changes=True))


def _render(proposal,output):
    table=Path(proposal['source_table'])
    _,text,_=libraries._table(table.read_text(),table.parent,proposal['source_library_context']['variables'])
    edits=[]
    for a,b in raw.children(text):
        part=text[a:b]
        if raw.kind(part)!='lib':continue
        fields={raw.kind(part[x:y]):(x,y)for x,y in raw.children(part)}
        x,y=fields['name'];name=literal._atoms(part[x+1:y-1])[-1][0]
        if name not in proposal['libraries']:continue
        x,y=fields['uri'];directory=output/proposal['libraries'][name]['directory_name']
        edits.append((a+x,a+y,'(uri '+json.dumps(str(directory))+')'))
    _need(len(edits)==len(proposal['libraries']),'complete_additive_library_table_projection_required')
    for a,b,value in reversed(edits):text=text[:a]+value+text[b:]
    return text


def _disjoint(board,table,output,proposal):
    protected={Path(board).resolve().parent,Path(table).resolve().parent,
        *(Path(r['source_directory'])for r in proposal['libraries'].values())}
    _need(all(output!=p and not output.is_relative_to(p)for p in protected),
        'disjoint_additive_library_output_required')


def construct_private(board,table,proposal,output):
    fresh=plan(board,table,asset_paths=proposal['asset_paths'],timeout_s=proposal['timeout_s'])
    _need(fresh==proposal,'stale_or_forged_additive_library_plan')
    output=Path(output).resolve()
    _need(not output.exists(),'fresh_additive_library_output_required')
    _disjoint(board,table,output,fresh)
    output.mkdir(parents=True)
    for group in fresh['libraries'].values():
        target=output/group['directory_name'];target.mkdir()
        for name in group['files']:
            shutil.copyfile(Path(group['source_directory'])/name,target/name)
        for row in group['additions']:
            shutil.copyfile(row['path'],target/(row['name']+'.kicad_mod'))
    target=output/'fp-lib-table';target.write_text(_render(fresh,output))
    return target


def receive(board,old_table,new_table,proposal,*,timeout_s=10.):
    """Rebuild the complete source addition, then compare actual saved files."""
    result=dict(ok=False,complete=False,scope_only=True,release_authority=False,
        routing_admitted=False,geometry_or_current_authority=False)
    try:
        deadline=_deadline(timeout_s)
        fresh=plan(board,old_table,asset_paths=proposal['asset_paths'],timeout_s=timeout_s)
        _need(fresh==proposal,'stale_or_forged_additive_library_plan')
        new_table=Path(new_table).resolve(strict=True);output=new_table.parent
        _need(new_table.name=='fp-lib-table'and new_table!=Path(old_table).resolve()
            and not new_table.is_symlink(),'distinct_ordinary_saved_library_table_required')
        _disjoint(board,old_table,output,fresh)
        _need(new_table.read_text()==_render(fresh,output),'unowned_library_table_setting_changed')
        for group in fresh['libraries'].values():
            expected=dict(group['files'])
            for row in group['additions']:
                path=Path(row['path'])
                expected[row['name']+'.kicad_mod']=dict(bytes=path.stat().st_size,sha256=row['sha256'])
            _need(_directory(output/group['directory_name'],deadline)==expected,
                'saved_library_missing_extra_or_changed_material')
        incoming=libraries.authority(board,new_table)
        expected=dict(fresh['source_library_context']['rows'])
        for name,group in fresh['libraries'].items():
            expected[name]=dict(expected[name],path=str(output/group['directory_name']))
        _need(incoming['rows']==expected,'unowned_library_row_authority_changed')
        _need(force._hash(board)==fresh['board_sha256']and force._code_identity()==fresh['code_identity']
            and fresh['source_library_context']==_stable(libraries.authority(board,old_table))
            and fresh['registered_asset_identities']==_registered()[1],
            'additive_library_receiving_source_or_asset_changed')
        _tick(deadline)
        result.update(ok=True,complete=True,source_sha256=fresh['board_sha256'],
            source_library_context=fresh['source_library_context'],new_library_context=incoming,
            exact_plan_sha256=_digest(fresh),existing_library_files_preserved=True,
            source_board_byte_exact=True,native_footprint_comparison_still_required=True)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:
        result['error']=str(exc)
    return _stable(result)
