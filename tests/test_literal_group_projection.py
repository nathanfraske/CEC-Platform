"""Only group UUID quoting is a writer permutation, not group authority."""
import pytest
import pcbnew
import cec_source_literal_group_retention as op
import cec_source_literal_additions as literal
import cec_pose_additive_reconstruction as receiving
import cec_force_current as force
from test_pose_additive_reconstruction import fixture as pose_fixture

GROUP='11111111-1111-4111-8111-111111111111'
FIRST='22222222-2222-4222-8222-222222222222'
SECOND='33333333-3333-4333-8333-333333333333'


def group(*, quoted=False):
    uid='"'+GROUP+'"' if quoted else GROUP
    return f'(group "opaque group" (uuid {uid}) (locked yes) (members "{FIRST}" "{SECOND}"))'


def board(node):
    return '(kicad_pcb\n'+node+'\n)'


def test_exact_source_group_text_survives_known_native_uuid_quote():
    old=group().replace('(locked yes)','\n  (locked yes)')
    native=group(quoted=True).replace(' (members','\n\t(members')
    result=op.retain(board(old),board(native))
    assert result==board(old)


def test_harmless_native_whitespace_does_not_replace_source_group_spelling():
    source=board(group());native=board(group().replace(' (','\n\t('))
    assert op.retain(source,native)==source


@pytest.mark.parametrize('before,after',[('1','1.0'),('1','1e0'),('0','-0')])
def test_opaque_numeric_token_spelling_is_not_a_uuid_writer_permutation(before,after):
    source=group()[:-1]+f' (future_field {before}))'
    native=group(quoted=True)[:-1]+f' (future_field {after}))'
    with pytest.raises(ValueError):op.retain(board(source),board(native))


@pytest.mark.parametrize('fault',['order','add','remove','duplicate','name','lock','unknown_add',
    'unknown_value','uuid','invalid_uuid_quote'])
def test_membership_and_every_non_uuid_field_remain_exact(fault):
    source=group();native=group(quoted=True)
    if fault=='order':native=native.replace(f'"{FIRST}" "{SECOND}"',f'"{SECOND}" "{FIRST}"')
    elif fault=='add':native=native.replace('(members ',f'(members "44444444-4444-4444-8444-444444444444" ')
    elif fault=='remove':native=native.replace(' "'+SECOND+'"','')
    elif fault=='duplicate':native=native.replace(' "'+SECOND+'"',' "'+FIRST+'"')
    elif fault=='name':native=native.replace('opaque group','other group')
    elif fault=='lock':native=native.replace('(locked yes)','(locked no)')
    elif fault=='unknown_add':native=native[:-1]+' (future_field 1))'
    elif fault=='unknown_value':
        source=source[:-1]+' (future_field 1))';native=native[:-1]+' (future_field 2))'
    elif fault=='uuid':native=native.replace(GROUP,'44444444-4444-4444-8444-444444444444')
    else:source=source.replace(GROUP,'not-a-uuid');native=native.replace(GROUP,'not-a-uuid')
    with pytest.raises(ValueError):op.retain(board(source),board(native))


@pytest.mark.parametrize('extra_side',['source','native'])
def test_complete_group_population_is_immutable(extra_side):
    source=group();native=group(quoted=True)
    extra=group().replace(GROUP,'44444444-4444-4444-8444-444444444444')
    if extra_side=='source':source+=extra
    else:native+=extra
    with pytest.raises(ValueError):op.retain(board(source),board(native))


def test_explicit_excluded_group_stays_native_verbatim():
    source=board(group());native=board(group(quoted=True).replace('(locked yes)','(locked no)'))
    assert op.retain(source,native,excluded_group_uuids=[GROUP])==native


@pytest.mark.parametrize('excluded',[None,True,'not-a-list',[GROUP,GROUP],['missing'],[1],[''],list(map(str,range(129)))])
def test_invalid_or_unbounded_exclusion_scope_refuses(excluded):
    with pytest.raises(ValueError):op.retain(board(group()),board(group(quoted=True)),excluded_group_uuids=excluded)


@pytest.mark.parametrize('mutate',[None,'name','copper'])
def test_connected_pose_replays_opaque_bare_group_and_still_rejects_mutation(tmp_path,mutate):
    source,target,selected=pose_fixture(tmp_path)
    native=pcbnew.LoadBoard(str(source))
    edge,=[t for t in native.GetTracks() if t.GetClass()=='PCB_TRACK'
        and tuple(t.GetStart())==(10000000,14000000) and tuple(t.GetEnd())==(16000000,14000000)]
    node=f'(group "opaque Source group" (uuid {GROUP}) (members "{force._uid(edge)}"))'
    for path in (source,target):
        text=path.read_text();_,end=literal._root(text)
        path.write_text(text[:end]+node+'\n'+text[end:])
    # Candidate uses the original literal group, despite native saving the
    # independent projected Source with a quoted group UUID.
    if mutate=='name':target.write_text(target.read_text().replace('opaque Source group','mutated Source group'))
    elif mutate=='copper':
        import re
        text=target.read_text();items,*_=literal._inventory(text)
        a,b,segment=items[force._uid(edge)]
        changed,count=re.subn(r'\(width [^)]+\)','(width 0.201)',segment)
        assert count==1 and changed!=segment
        target.write_text(text[:a]+changed+text[b:])
    before=source.read_bytes()
    result=receiving.receive(source,target,selected_footprint_uuids=[selected],board_hint='arbitrary')
    assert source.read_bytes()==before
    if mutate:assert not result['ok'] and result['errors']
    else:assert result['ok'] and result['complete'],result
