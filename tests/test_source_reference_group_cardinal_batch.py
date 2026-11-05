import copy
import pcbnew
import pytest
import cec_source_reference_group_cardinal_batch as op
from test_source_reference_group_transport import two_maps,fixture


def fixture_many(tmp_path):
    source,selections=two_maps(tmp_path)
    proofs=op.single.inspect_many(source,selections)
    return source,[(proofs[0],1,(123457,-234569)),(proofs[1],3,(-345671,456787))]


def fixture_mixed_projection(tmp_path,back=False):
    from test_source_reference_group_transport import fab_body_fixture
    one=tmp_path/'fab';two=tmp_path/'court';one.mkdir();two.mkdir()
    source,owner,gid=fab_body_fixture(one,back=back,external=True)
    other,owner2,gid2=fixture(two)
    second=other.read_text().replace('"X7"','"X8"').replace(op.single.PREFIX+'X7',op.single.PREFIX+'X8')
    extra=[second[a:z]for a,z in op.raw.children(second)
           if op.raw.kind(second[a:z])in('footprint','gr_text','gr_line','group')]
    first=source.read_text();at=first.rfind(')')
    source.write_text(first[:at]+'\n'+'\n'.join(extra)+'\n'+first[at:])
    proofs=[op.single.inspect_native_fab_body(source,owner_uuid=owner,group_uuid=gid),
            op.single.inspect(source,owner_uuid=owner2,group_uuid=gid2)]
    return source,[(proofs[0],1,(123457,-234569)),(proofs[1],3,(-345671,456787))]


def save_literal(source,requests,path):
    nodes=op.expected_nodes(requests);text=source.read_text();spans=op.raw.inventory(text)
    for uid,node in sorted(nodes.items(),key=lambda row:spans[row[0]][0],reverse=True):
        a,z=spans[uid];text=text[:a]+op.single.ast._render(node)+text[z:]
    path.write_text(text);return path


def test_two_independent_maps_one_source_preflight_and_saved_replay(tmp_path,monkeypatch):
    source,requests=fixture_many(tmp_path);original=source.read_bytes();b=pcbnew.LoadBoard(str(source))
    real=op._preflight_source;calls=[]
    def counted(*args):calls.append(1);return real(*args)
    monkeypatch.setattr(op,'_preflight_source',counted)
    result=op.transform_many(b,requests)
    assert calls==[1]and result['source_preflight_count']==1
    assert len(set(result['owner_uuids']))==2 and not result['pose_admitted']
    child=save_literal(source,requests,tmp_path/'child.kicad_pcb')
    assert op.verify(source,child,requests)['ok']
    assert op.verify_native(source,b,requests)['ok']
    assert op.single._cardinal_identity(b)==op.single._cardinal_identity(pcbnew.LoadBoard(str(child)))
    assert source.read_bytes()==original


@pytest.mark.parametrize('back',[False,True])
def test_exact_fab_and_court_maps_mix_only_through_explicit_fresh_proofs(tmp_path,back):
    source,requests=fixture_mixed_projection(tmp_path,back);original=source.read_bytes()
    board=pcbnew.LoadBoard(str(source));result=op.transform_many(board,requests)
    child=save_literal(source,requests,tmp_path/'mixed.kicad_pcb')
    assert op.verify(source,child,requests)['ok']
    assert op.verify_native(source,board,requests)['ok']
    assert not result['pose_admitted']and not result['current_authority']
    assert op.single._cardinal_identity(board)==op.single._cardinal_identity(pcbnew.LoadBoard(str(child)))
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['projection','scope','native_body'])
def test_fab_transport_selector_is_not_forged_map_or_changed_body_authority(tmp_path,fault):
    source,requests=fixture_mixed_projection(tmp_path);board=pcbnew.LoadBoard(str(source))
    requests=copy.deepcopy(requests)
    if fault=='projection':requests[0][0]['outline_geometry']='caller_bbox'
    elif fault=='scope':requests[0][0]['closed_assembly_body_authority']=True
    else:
        fp=next(f for f in board.GetFootprints()if op.single.force._uid(f)==requests[0][0]['owner_uuid'])
        body=next(i for i in fp.GraphicalItems()if i.GetLayer()==pcbnew.F_Fab)
        body.Move(pcbnew.VECTOR2I(1,0))
    before=op.single._cardinal_identity(board)
    with pytest.raises(ValueError):op.transform_many(board,requests)
    assert op.single._cardinal_identity(board)==before


@pytest.mark.parametrize('turn',[0,1,2,3])
def test_single_map_exact_api_equivalence(tmp_path,turn):
    source,owner,group=fixture(tmp_path);proof=op.single.inspect(source,owner_uuid=owner,group_uuid=group)
    requests=[(proof,turn,(234567,-345678))]
    single=pcbnew.LoadBoard(str(source));batch=pcbnew.LoadBoard(str(source))
    op.single.transform_cardinal(single,proof,quarter_turns=turn,delta_nm=requests[0][2])
    op.transform_many(batch,requests)
    assert op.single._cardinal_identity(single)==op.single._cardinal_identity(batch)
    assert op.expected_nodes(requests)==op.single.expected_cardinal_nodes(proof,
        quarter_turns=turn,delta_nm=requests[0][2])


@pytest.mark.parametrize('fault',['duplicate','forged_member','forged_owner','wrong_source','angle',
    'bool','delta','empty','too_many','row','source_changed','native_ink','native_group','native_field','native_copper'])
def test_bad_second_request_or_source_refuses_before_any_mutation(tmp_path,fault):
    source,requests=fixture_many(tmp_path);b=pcbnew.LoadBoard(str(source));requests=copy.deepcopy(requests)
    if fault=='duplicate':requests[1]=requests[0]
    elif fault=='forged_member':requests[1][0]['member_uuids'].append('fabricated')
    elif fault=='forged_owner':requests[1][0]['owner_uuid']='fabricated'
    elif fault=='wrong_source':
        other=tmp_path/'other.kicad_pcb';other.write_bytes(source.read_bytes());requests[1][0]['source']=str(other)
    elif fault=='angle':requests[1]=(requests[1][0],45,(0,0))
    elif fault=='bool':requests[1]=(requests[1][0],True,(0,0))
    elif fault=='delta':requests[1]=(requests[1][0],1,(0.,0))
    elif fault=='empty':requests=[]
    elif fault=='too_many':requests=requests*5
    elif fault=='row':requests[1]={'accepted':True}
    elif fault=='source_changed':source.write_text(source.read_text()+'\n')
    elif fault=='native_ink':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='native_group':next(iter(b.Groups())).SetLocked(False)
    elif fault=='native_field':next(iter(b.GetFootprints())).SetValue('changed')
    else:
        t=pcbnew.PCB_TRACK(b);t.SetWidth(200000);b.Add(t)
    before=op.single._cardinal_identity(b)
    with pytest.raises(ValueError):op.transform_many(b,requests)
    assert before==op.single._cardinal_identity(b)


@pytest.mark.parametrize('fault',['map_owner','ink','group','font','extra','unrelated_field'])
def test_saved_literal_extra_or_partial_transport_refuses(tmp_path,fault):
    source,requests=fixture_many(tmp_path);child=save_literal(source,requests,tmp_path/'bad.kicad_pcb')
    b=pcbnew.LoadBoard(str(child))
    if fault=='map_owner':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='ink':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group':next(iter(b.Groups())).SetLocked(False)
    elif fault=='font':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').SetTextThickness(130000)
    elif fault=='unrelated_field':next(iter(b.GetFootprints())).SetField('unknown','changed')
    else:
        t=pcbnew.PCB_TRACK(b);t.SetWidth(200000);b.Add(t)
    op.field._save_field_snapshot(b,child)
    with pytest.raises(ValueError):op.verify(source,child,requests)


def test_native_replay_does_not_grant_other_owner_motion_or_copper_admission(tmp_path):
    source,selections=two_maps(tmp_path)
    other=pcbnew.BOARD();extra=pcbnew.FOOTPRINT(other);extra.SetReference('unowned')
    extra.SetPosition(pcbnew.VECTOR2I_MM(25,25));other.Add(extra)
    extra_path=tmp_path/'extra.kicad_pcb';op.field._save_field_snapshot(other,extra_path)
    node=next(n for n in op.single.ast._nodes(extra_path)[1].values()if n[0]=='footprint')
    text=source.read_text();at=text.rfind(')');source.write_text(text[:at]+op.single.ast._render(node)+'\n'+text[at:])
    proofs=op.single.inspect_many(source,selections);requests=[(p,1,(0,0))for p in proofs]
    b=pcbnew.LoadBoard(str(source));op.transform_many(b,requests)
    b.FindFootprintByReference('unowned').Move(pcbnew.VECTOR2I(100000,0))
    result=op.verify_native(source,b,requests)
    assert result['ok']and result['full_macro_physical_copper_receiving_still_required']
    assert not result['current_authority']and not result['release_authority']
    path=tmp_path/'other_owner.kicad_pcb';op.field._save_field_snapshot(b,path)
    with pytest.raises(ValueError):op.verify(source,path,requests)


@pytest.mark.parametrize('timeout',[0,11,True,float('nan')])
def test_invalid_budget_refuses(tmp_path,timeout):
    source,requests=fixture_many(tmp_path)
    with pytest.raises(ValueError):op.transform_many(pcbnew.LoadBoard(str(source)),requests,timeout_s=timeout)


def test_changed_code_between_independent_maps_cannot_commit(tmp_path,monkeypatch):
    source,requests=fixture_many(tmp_path);b=pcbnew.LoadBoard(str(source))
    before=op.single._cardinal_identity(b);derive=op.single._cardinal_derive_context
    identity=op.single.force._code_identity;changed=[False]
    monkeypatch.setattr(op.single.force,'_code_identity',lambda:'changed'if changed[0]else identity())
    def wrapped(*args):
        result=derive(*args);changed[0]=True;return result
    monkeypatch.setattr(op.single,'_cardinal_derive_context',wrapped)
    with pytest.raises(ValueError,match='source_or_code_changed'):op.transform_many(b,requests)
    assert before==op.single._cardinal_identity(b)


def test_partial_one_of_two_maps_never_satisfies_batch_replay(tmp_path):
    source,requests=fixture_many(tmp_path)
    child=save_literal(source,requests[:1],tmp_path/'partial.kicad_pcb')
    with pytest.raises(ValueError):op.verify(source,child,requests)


def test_private_context_parses_once_and_receiver_rebinds_independently(tmp_path,monkeypatch):
    source,requests=fixture_many(tmp_path);b=pcbnew.LoadBoard(str(source))
    counts=dict(parse=0,inspect=0,family=0,code=0,preflight=0)
    for name,module,attribute in(('inspect',op.single,'_inspect_context'),
            ('family',op.single.force,'_family'),('code',op.single.force,'_code_identity'),
            ('preflight',op,'_preflight_source')):
        original=getattr(module,attribute)
        def counted(*a,_name=name,_original=original,**kw):
            counts[_name]+=1;return _original(*a,**kw)
        monkeypatch.setattr(module,attribute,counted)
    parse=op.single.ast._nodes
    def parsed(path):
        if str(path).endswith('/source.kicad_pcb'):counts['parse']+=1
        return parse(path)
    monkeypatch.setattr(op.single.ast,'_nodes',parsed)
    op.transform_many(b,requests)
    assert counts==dict(parse=1,inspect=1,family=3,code=3,preflight=1)
    assert op.verify_native(source,b,requests)['ok']
    assert counts==dict(parse=2,inspect=2,family=5,code=5,preflight=1)
    with pytest.raises(TypeError):op.transform_many(b,requests,context={'received':True})


def test_opaque_source_mutation_during_private_derivation_refuses_before_commit(tmp_path,monkeypatch):
    source,requests=fixture_many(tmp_path);b=pcbnew.LoadBoard(str(source));before=op.single._cardinal_identity(b)
    real=op.single._cardinal_derive_context;changed=[False]
    def derive(*args):
        result=real(*args)
        if not changed[0]:
            changed[0]=True;text=source.read_text();at=text.rfind(')')
            source.write_text(text[:at]+'(unknown_source_authority yes)\n'+text[at:])
        return result
    monkeypatch.setattr(op.single,'_cardinal_derive_context',derive)
    with pytest.raises(ValueError,match='source_or_code_changed'):op.transform_many(b,requests)
    assert op.single._cardinal_identity(b)==before
