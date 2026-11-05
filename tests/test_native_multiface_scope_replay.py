"""Real KiCad source scope and independent saved exclusive-barrel replay."""
import pcbnew
import pytest
import cec_force_current as force
import cec_ordinary_route_receiving as receiving
from cec_native_ordinary_chain_scope import multiface_chain
from test_ordinary_exclusive_via_path import fixture


def native_scope(source,ids,via):
    b=pcbnew.LoadBoard(str(source));rows=[];vias=[]
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK':
            rows.append(dict(uuid=force._uid(t),kind=t.GetClass(),net=str(t.GetNetname()),
                layer=int(t.GetLayer()),width_nm=int(t.GetWidth()),locked=t.IsLocked(),
                grouped=t.GetParentGroup() is not None,start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())))
        elif t.GetClass()=='PCB_VIA':
            vias.append(dict(uuid=force._uid(t),kind=t.GetClass(),net=str(t.GetNetname()),
                through=t.GetViaType()==pcbnew.VIATYPE_THROUGH,at_nm=list(t.GetPosition()),
                locked=t.IsLocked(),grouped=any(g.ContainsItem(t) for g in b.Groups())))
    return multiface_chain(rows,vias,ids,[via],receiving.eligible_nets(b,source,'synthetic'))


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirrored',[False,True])
def test_actual_rotated_native_scope_is_not_a_substitute_for_saved_receiving(tmp_path,quarter,mirrored):
    source,child,ids,via=fixture(tmp_path,quarter,mirrored)
    before=[force._hash(source),force._hash(child)]
    scope=native_scope(source,ids,via)
    assert len(scope['endpoints'])==2 and scope['retired_via_uuids']==[via]
    proof=receiving.receive(source,child,retired_track_uuids=scope['retired_track_uuids'],
        retired_via_uuids=scope['retired_via_uuids'],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_prior_native_terminal_partitions_preserved']
    assert [force._hash(source),force._hash(child)]==before


@pytest.mark.parametrize('fault',['group','power','pair'])
def test_actual_owned_or_nonordinary_native_scope_refuses(tmp_path,fault):
    source,_child,ids,via=fixture(tmp_path,fault=fault)
    with pytest.raises(ValueError):native_scope(source,ids,via)


@pytest.mark.parametrize('fault',['surviving_branch','land','factory'])
def test_topology_alone_never_waives_actual_barrel_ownership_or_factory(tmp_path,fault):
    source,child,ids,via=fixture(tmp_path,fault=fault)
    scope=native_scope(source,ids,via)
    proof=receiving.receive(source,child,retired_track_uuids=scope['retired_track_uuids'],
        retired_via_uuids=scope['retired_via_uuids'],board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']
