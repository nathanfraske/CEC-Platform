"""Missing stock assets may be added, never copied from a cached board or replaced."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import cec_additive_library_context as op


def fixture(tmp_path,monkeypatch,*,flags='',nickname='vendor-a',item='new-land'):
    vendor=tmp_path/'vendor';vendor.mkdir();lib=vendor/'parts.pretty';lib.mkdir()
    for name in ('old-land','new-land','second-land'):
        (lib/(name+'.kicad_mod')).write_text('(footprint '+json.dumps(name)+')')
    drawing=vendor/'drawing.pdf';drawing.write_bytes(b'bound synthetic primary drawing')
    rule=dict(library='vendor-a',directory='parts.pretty',old='old-land',new='new-land',
        datasheet='drawing.pdf',datasheet_sha256=hashlib.sha256(drawing.read_bytes()).hexdigest())
    monkeypatch.setattr(op.patterns,'ROOT',vendor)
    monkeypatch.setattr(op.patterns,'CATALOG',{'synthetic manufacturer package':rule})
    project=tmp_path/'project';project.mkdir();snapshot=tmp_path/'immutable.pretty';snapshot.mkdir()
    (snapshot/'old-land.kicad_mod').write_bytes(b'original unreferenced module is opaque')
    (snapshot/'readme.txt').write_bytes(b'original non-module bytes are retained too')
    table=project/'fp-lib-table'
    table.write_text('(fp_lib_table (version 7)(lib(name '+json.dumps(nickname)+')'
        '(type "KiCad")(uri "${KIPRJMOD}/../immutable.pretty")(options "")(descr "original")'+flags+')'
        '(lib(name "unaffected")(type "KiCad")(uri "${KIPRJMOD}/../elsewhere.pretty")'
        '(options "")(descr "keep hidden and disabled")(hidden)(disabled)))')
    family=tmp_path/'private-board';family.mkdir();board=family/'renamed.kicad_pcb'
    board.write_text('(kicad_pcb (footprint '+json.dumps(nickname+':'+item)+'(layer "B.Cu")))')
    return board,table,snapshot,lib/'new-land.kicad_mod'


@pytest.mark.parametrize('hidden',['','(hidden)'])
def test_complete_old_snapshot_retained_and_missing_registered_asset_is_added(tmp_path,monkeypatch,hidden):
    board,table,old,asset=fixture(tmp_path,monkeypatch,flags=hidden)
    originals={p:p.read_bytes()for p in (board,table,*old.iterdir(),asset)}
    plan=op.plan(board,table,asset_paths=[str(asset)])
    target=op.construct_private(board,table,plan,tmp_path/'derived')
    received=op.receive(board,table,target,plan)
    assert received['ok']and received['complete'],received
    assert received['source_board_byte_exact']and received['existing_library_files_preserved']
    assert not received['geometry_or_current_authority']and not received['release_authority']
    row=received['new_library_context']['rows']['vendor-a']
    assert row['enabled']and row['hidden']==bool(hidden)
    new=Path(row['path'])
    assert sorted(p.name for p in new.iterdir())==['new-land.kicad_mod','old-land.kicad_mod','readme.txt']
    assert all((new/p.name).read_bytes()==p.read_bytes()for p in old.iterdir())
    assert (new/'new-land.kicad_mod').read_bytes()==asset.read_bytes()
    assert received['new_library_context']['rows']['unaffected']==plan['source_library_context']['rows']['unaffected']
    assert all(p.read_bytes()==data for p,data in originals.items())


@pytest.mark.parametrize('change',['old-file','extra-file','new-file','table','board','source-file','source-table','drawing'])
def test_fresh_receiver_refuses_any_changed_or_added_unowned_material(tmp_path,monkeypatch,change):
    board,table,old,asset=fixture(tmp_path,monkeypatch)
    plan=op.plan(board,table,asset_paths=[str(asset)])
    target=op.construct_private(board,table,plan,tmp_path/'derived')
    folder=next((tmp_path/'derived').glob('*.pretty'))
    path={'old-file':folder/'old-land.kicad_mod','extra-file':folder/'surprise.kicad_mod',
        'new-file':folder/'new-land.kicad_mod','table':target,'board':board,
        'source-file':old/'old-land.kicad_mod','source-table':table,'drawing':asset.parent.parent/'drawing.pdf'}[change]
    path.write_bytes(b'changed')
    result=op.receive(board,table,target,plan)
    assert not result['ok']and not result['complete']and result['error']


@pytest.mark.parametrize('change',['code','sha','group','asset-list','timeout','source-context'])
def test_caller_cannot_forge_or_reuse_a_plan(tmp_path,monkeypatch,change):
    board,table,old,asset=fixture(tmp_path,monkeypatch)
    plan=op.plan(board,table,asset_paths=[str(asset)])
    target=op.construct_private(board,table,plan,tmp_path/'derived');fake=copy.deepcopy(plan)
    if change=='code':fake['code_identity']={}
    elif change=='sha':fake['board_sha256']='0'*64
    elif change=='group':fake['libraries']['vendor-a']['files']={}
    elif change=='asset-list':fake['asset_paths']=[str(asset.parent/'second-land.kicad_mod')]
    elif change=='timeout':fake['timeout_s']=2.
    else:fake['source_library_context']['rows']['unaffected']['enabled']=True
    result=op.receive(board,table,target,fake)
    assert not result['ok']and not result['complete']


@pytest.mark.parametrize('state',['existing','case-shadow','disabled','wrong-alias','unreferenced','duplicate','unregistered','directory','symlink'])
def test_no_replacement_alias_enabling_or_arbitrary_asset_synthesis(tmp_path,monkeypatch,state):
    flags='(disabled)'if state=='disabled'else''
    alias='other'if state=='wrong-alias'else'vendor-a'
    item='something-else'if state=='unreferenced'else'new-land'
    board,table,old,asset=fixture(tmp_path,monkeypatch,flags=flags,nickname=alias,item=item)
    paths=[str(asset)]
    if state=='existing':(old/'new-land.kicad_mod').write_text('do not replace')
    elif state=='case-shadow':(old/'NEW-LAND.kicad_mod').write_text('do not shadow')
    elif state=='duplicate':paths*=2
    elif state=='unregistered':paths=[str(asset.parent/'second-land.kicad_mod')]
    elif state=='directory':(old/'nested').mkdir()
    elif state=='symlink':(old/'linked.kicad_mod').symlink_to(asset)
    with pytest.raises(ValueError):op.plan(board,table,asset_paths=paths)


@pytest.mark.parametrize('where',['board','table','library','existing'])
def test_constructor_never_writes_into_a_source_namespace(tmp_path,monkeypatch,where):
    board,table,old,asset=fixture(tmp_path,monkeypatch)
    plan=op.plan(board,table,asset_paths=[str(asset)])
    output={'board':board.parent/'new','table':table.parent/'new','library':old/'new','existing':tmp_path/'present'}[where]
    if where=='existing':output.mkdir()
    with pytest.raises(ValueError):op.construct_private(board,table,plan,output)


@pytest.mark.parametrize('limit',[0,True,float('nan'),float('inf'),10.01,-1])
def test_finite_phase_bounds_are_not_optional(tmp_path,monkeypatch,limit):
    board,table,old,asset=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):op.plan(board,table,asset_paths=[str(asset)],timeout_s=limit)


def test_environment_variable_binding_is_retained_in_the_new_absolute_table(tmp_path,monkeypatch):
    board,table,old,asset=fixture(tmp_path,monkeypatch)
    table.write_text(table.read_text().replace('${KIPRJMOD}/../immutable.pretty','${SYNTHETIC_PARTS}'))
    monkeypatch.setenv('SYNTHETIC_PARTS',str(old))
    plan=op.plan(board,table,asset_paths=[str(asset)])
    target=op.construct_private(board,table,plan,tmp_path/'derived')
    result=op.receive(board,table,target,plan)
    assert result['ok'],result
    assert '${SYNTHETIC_PARTS}'not in target.read_text()


def test_saved_plan_and_saved_receipt_are_exact_wire_roundtrips(tmp_path,monkeypatch):
    board,table,old,asset=fixture(tmp_path,monkeypatch)
    proposal=op.plan(board,table,asset_paths=[str(asset)])
    saved=tmp_path/'proposal.json';saved.write_text(json.dumps(proposal))
    incoming=json.loads(saved.read_text());assert incoming==proposal
    target=op.construct_private(board,table,incoming,tmp_path/'derived')
    received=op.receive(board,table,target,json.loads(saved.read_text()))
    assert received['ok']and received['complete'],received
    assert json.loads(json.dumps(received))==received
    incoming['source_library_context']['references'][0][1]='forged'
    assert not op.receive(board,table,target,incoming)['ok']
