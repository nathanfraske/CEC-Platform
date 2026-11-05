"""Invocation-local canonical observations are not reusable admission passes."""
import pcbnew
import pytest
import cec_source_device_pinmap as op
import cec_source_ground_leaf as canonical
import cec_device_power_roles as roles
from test_source_device_pinmap import fixture as canonical_fixture


def fixture(tmp_path,monkeypatch):
    board,fp,model,root,tree=canonical_fixture(tmp_path,monkeypatch)
    original=canonical._export;calls=[]
    def counted(path,deadline):calls.append((path,deadline));return original(path,deadline)
    monkeypatch.setattr(canonical,'_export',counted)
    return board,fp,model,root,calls


def test_real_native_proxy_identity_hits_once_next_invocation_fresh(tmp_path,monkeypatch):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    with op.observation_scope(board,board_hint=str(root)):
        assert len(roles.physical_pinmap(fp,model,board_hint=str(root)))==53
        assert len(roles.physical_pinmap(fp,model,board_hint=str(root)))==53
    assert len(calls)==1
    with op.observation_scope(board,board_hint=str(root)):
        roles.physical_pinmap(fp,model,board_hint=str(root))
    assert len(calls)==2 and op._observations.get() is None


def test_returned_copy_cannot_poison_observed_facts(tmp_path,monkeypatch):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    with op.observation_scope(board,board_hint=str(root)):
        proof=op.prove(fp,model,board_hint=str(root));proof['logical_pins']['8']['function']='FORGED'
        proof['hierarchy'].clear();proof['native_pad_nets'].clear()
        again=op.prove(fp,model,board_hint=str(root))
        assert again['logical_pins']['8']['function']=='EN' and len(again['native_pad_nets'])==61
        assert again['hierarchy']
    assert len(calls)==1


@pytest.mark.parametrize('when',['hit','exit'])
@pytest.mark.parametrize('mutation',['source','native'])
def test_actual_mid_scope_change_never_reuses_observation(tmp_path,monkeypatch,when,mutation):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):
        with op.observation_scope(board,board_hint=str(root)):
            op.prove(fp,model,board_hint=str(root))
            if mutation=='source':root.write_text(root.read_text()+'\n')
            else:fp.Move(pcbnew.VECTOR2I(1,0))
            if when=='hit':op.prove(fp,model,board_hint=str(root))
    assert op._observations.get() is None


@pytest.mark.parametrize('when',['hit','exit'])
def test_shared_deadline_applies_to_cached_hits_and_exit(tmp_path,monkeypatch,when):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    now=[100.];monkeypatch.setattr(op.time,'monotonic',lambda:now[0])
    with pytest.raises(ValueError,match='deadline'):
        with op.observation_scope(board,board_hint=str(root),timeout_s=1):
            op.prove(fp,model,board_hint=str(root))
            now[0]=101.
            if when=='hit':op.prove(fp,model,board_hint=str(root))
    assert op._observations.get() is None


def test_clock_rechecked_after_final_file_hash(tmp_path,monkeypatch):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    now=[100.];monkeypatch.setattr(op.time,'monotonic',lambda:now[0])
    original=op.force._hash
    with pytest.raises(ValueError,match='deadline'):
        with op.observation_scope(board,board_hint=str(root),timeout_s=1):
            op.prove(fp,model,board_hint=str(root))
            def slow(path):
                value=original(path)
                if str(path)==str(root):now[0]=102.
                return value
            monkeypatch.setattr(op.force,'_hash',slow)


def test_native_clone_and_different_hint_do_not_alias_parent(tmp_path,monkeypatch):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    child=pcbnew.BOARD();copy=pcbnew.FOOTPRINT(fp);child.Add(copy)
    for p in copy.Pads():
        net=child.FindNet(p.GetNetname())
        if not net:net=pcbnew.NETINFO_ITEM(child,p.GetNetname());child.Add(net)
        p.SetNet(net)
    # Same file, explicitly distinct hint spelling is not a cache key alias.
    alternate=str(root.parent)+'/./'+root.name
    with op.observation_scope(board,board_hint=str(root)):
        op.prove(fp,model,board_hint=str(root))
        op.prove(copy,roles.footprint_contract(copy),board_hint=str(root))
        op.prove(fp,model,board_hint=alternate)
        op.prove(fp,model,board_hint=str(root))
    assert len(calls)==3


def test_nested_scopes_restore_outer_cache_and_exception_cleanup(tmp_path,monkeypatch):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    with op.observation_scope(board,board_hint=str(root)):
        op.prove(fp,model,board_hint=str(root))
        with pytest.raises(RuntimeError):
            with op.observation_scope(board,board_hint=str(root)):
                op.prove(fp,model,board_hint=str(root));raise RuntimeError('caller')
        op.prove(fp,model,board_hint=str(root))
    assert len(calls)==2 and op._observations.get() is None


@pytest.mark.parametrize('budget',[0,-1,11,True,float('nan')])
def test_scope_invalid_budget_never_installs_context(tmp_path,monkeypatch,budget):
    board,fp,model,root,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):
        with op.observation_scope(board,board_hint=str(root),timeout_s=budget):pass
    assert not calls and op._observations.get() is None
