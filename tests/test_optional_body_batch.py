"""Batch Source parsing is not a cache of optional-body owner approval."""
import pytest
import pcbnew
import cec_optional_body_ink_contract as op
from test_optional_body_ink_contract import fixture


def pair(tmp_path):
    source,table,uid=fixture(tmp_path,name='XFCN_T34069_THT_M3_40A')
    board=pcbnew.LoadBoard(str(source));first=next(iter(board.GetFootprints()))
    second=pcbnew.FOOTPRINT(first);second.SetReference('a_different_terminal')
    second.m_Uuid.Clone(pcbnew.KIID());board.Add(second);second.Move(pcbnew.VECTOR2I_MM(20,11))
    # Native IDs are identity, not semantic body-role matching.
    for item in [*second.Pads(),*second.GraphicalItems(),*second.GetFields()]:item.m_Uuid.Clone(pcbnew.KIID())
    pcbnew.SaveBoard(str(source),board)
    return source,table,[op.force._uid(first),op.force._uid(second)]


def test_one_fresh_batch_reproves_every_owner_and_matches_standalone_proofs(tmp_path,monkeypatch):
    source,table,ids=pair(tmp_path);sha=op.force._hash(source);authority=op.libraries.authority;calls=[]
    def observed(*a,**kw):calls.append(a);return authority(*a,**kw)
    monkeypatch.setattr(op.libraries,'authority',observed)
    proofs=op.inspect_many(source,library_table=table,footprint_uuids=ids,expected_source_sha256=sha)
    assert len(calls)==2 and set(proofs)==set(ids)
    for uid in ids:
        single=op.inspect(source,library_table=table,footprint_uuid=uid,expected_source_sha256=sha)
        assert single==proofs[uid] and len(single['graphic_uuids'])==4
    assert op.force._hash(source)==sha


@pytest.mark.parametrize('fault',['pad_1nm','silk_1nm','locked','unknown_setting'])
def test_later_actual_owner_cannot_borrow_first_owner_success(tmp_path,fault):
    source,table,ids=pair(tmp_path);board=pcbnew.LoadBoard(str(source))
    second=next(f for f in board.GetFootprints()if op.force._uid(f)==ids[1])
    if fault=='pad_1nm':next(iter(second.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='silk_1nm':next(g for g in second.GraphicalItems()if g.GetLayer()==pcbnew.F_SilkS).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='locked':second.SetLocked(True)
    else:second.SetLocalClearance(1)
    pcbnew.SaveBoard(str(source),board)
    with pytest.raises(ValueError):op.inspect_many(source,library_table=table,footprint_uuids=ids,expected_source_sha256=op.force._hash(source))


@pytest.mark.parametrize('ids',[[],['same','same'],[True],['']])
def test_batch_requires_finite_positive_unique_owner_input(tmp_path,ids):
    source,table,uid=fixture(tmp_path)
    with pytest.raises(ValueError):op.inspect_many(source,library_table=table,footprint_uuids=ids,expected_source_sha256=op.force._hash(source))
