"""Bounded existing Source operators compose without inventing load or locks."""
from pathlib import Path
from unittest import mock
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_pair_repair as additive
import cec_source_literal_retirement as subtract
import cec_source_retaining_ses_import as raw
from test_detached_passive_transaction import wrapper
from test_ordinary_route_receiving import fixture as ordinary_fixture
from test_distributed_supply import authority
from test_distributed_supply_prefix import native_fixture,compile_boundary


def ordinary_row(source,target,uid,net,*,locks):
    return dict(kind='ordinary_source_reflow',candidate=str(target),candidate_sha256=force._hash(target),
        retired_track_uuids=[uid],allow_locked_track_uuids=locks,net=net)


@pytest.mark.parametrize('rotation,prefix',[(0,'/first/'),(90,'/second/'),(180,'/renamed/'),(270,'plain_')])
@pytest.mark.parametrize('locked',[False,True])
def test_existing_source_branch_receiver_replays_exact_rotation_name_and_lock_scope(tmp_path,rotation,prefix,locked):
    module=wrapper();source,target,uid,net=ordinary_fixture(tmp_path,rotation,prefix,locked=locked)
    row=ordinary_row(source,target,uid,net,locks=[uid]if locked else [])
    before=[p.read_bytes()for p in(source,target)]
    assert module.validate_phases([row])==['ordinary_source_reflow']
    received,proof=module.receive_phase(source,source,row,'synthetic')
    assert received==target and proof['ok']and proof['complete'],proof
    assert proof['locked_scope_used']==([uid]if locked else [])
    assert proof['all_prior_native_terminal_partitions_preserved']and not proof['release_authority']
    assert before==[p.read_bytes()for p in(source,target)]


@pytest.mark.parametrize('fault',['omit_lock','spurious_lock','wrong_net','unknown_cut','pose','metadata','sidecar',
                                  'group','power','cut_only'])
def test_source_lock_scope_never_grants_an_electrical_or_unowned_mutation_waiver(tmp_path,fault):
    module=wrapper();source,target,uid,net=ordinary_fixture(tmp_path,locked=fault!='spurious_lock')
    locks=[]if fault=='omit_lock'else[uid]
    row=ordinary_row(source,target,uid,net,locks=locks)
    if fault=='wrong_net':row['net']='/invented'
    elif fault=='unknown_cut':row['retired_track_uuids']=['unlisted']
    elif fault=='cut_only':raw.write_raw(target,subtract.subtract(raw.raw_text(source),[uid]))
    elif fault=='sidecar':target.with_suffix('.kicad_pro').write_text('{"unowned":true}')
    elif fault in('pose','metadata'):
        b=pcbnew.LoadBoard(str(target))
        if fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
        else:props=b.GetProperties();props['UNOWNED']='true';b.SetProperties(props)
        field._save_field_snapshot(b,target)
    elif fault=='group':
        b=pcbnew.LoadBoard(str(source));g=pcbnew.PCB_GROUP(b);b.Add(g)
        g.AddItem(next(t for t in b.GetTracks()if force._uid(t)==uid));field._save_field_snapshot(b,source)
    elif fault=='power':
        for path in(source,target):
            b=pcbnew.LoadBoard(str(path));n=pcbnew.NETINFO_ITEM(b,'+5V');b.Add(n)
            for i in[*(p for fp in b.GetFootprints()for p in fp.Pads()),*b.GetTracks()]:i.SetNet(n)
            field._save_field_snapshot(b,path)
        row['net']='+5V'
    row['candidate_sha256']=force._hash(target)
    with pytest.raises((ValueError,AssertionError)):
        module.validate_phases([row]);module.receive_phase(source,source,row,'synthetic')


@pytest.mark.parametrize('kind',['ordinary_source_reflow','distributed_supply_join'])
def test_no_added_current_width_timeout_or_permission_fields_and_unchanged_four_phase_cap(kind):
    module=wrapper();row=dict(kind=kind,candidate='private.kicad_pcb',candidate_sha256='a'*64,net='/arbitrary')
    if kind=='ordinary_source_reflow':row.update(retired_track_uuids=['u'],allow_locked_track_uuids=['u'])
    assert module.validate_phases([row])==[kind]
    for extra in({'amps':1},{'timeout_s':30},{'allow_unknown':True},{'width':.1}):
        with pytest.raises(ValueError):module.validate_phases([dict(row,**extra)])
    with pytest.raises(ValueError):module.validate_phases([row,row])
    with pytest.raises(ValueError):module.validate_phases([row]*5)
    with pytest.raises(ValueError):module.validate_phases([row,dict(kind='ordinary_join',net='/arbitrary',
        candidate='another.kicad_pcb',candidate_sha256='b'*64)])


@pytest.mark.parametrize('fault',['empty_cut','duplicate_cut','unlisted_lock','duplicate_lock','many_cut'])
def test_exact_finite_source_branch_schema(fault):
    module=wrapper();row=dict(kind='ordinary_source_reflow',candidate='private.kicad_pcb',
        candidate_sha256='a'*64,net='/renamed',retired_track_uuids=['u'],allow_locked_track_uuids=['u'])
    if fault=='empty_cut':row['retired_track_uuids']=[]
    elif fault=='duplicate_cut':row['retired_track_uuids']=['u','u']
    elif fault=='unlisted_lock':row['allow_locked_track_uuids']=['not-selected']
    elif fault=='duplicate_lock':row['allow_locked_track_uuids']=['u','u']
    else:row['retired_track_uuids']=[str(i)for i in range(9)]
    with pytest.raises(ValueError):module.validate_phases([row])


@pytest.mark.parametrize('turn,layer',[(0,pcbnew.F_Cu),(1,pcbnew.F_Cu),(2,pcbnew.B_Cu),(3,pcbnew.B_Cu)])
def test_real_saved_distributed_supply_prefix_join_uses_the_existing_source_receiver(tmp_path,turn,layer):
    module=wrapper()
    import cec_distributed_supply as supply
    import cec_distributed_supply_prefix as prefixes
    b,net=native_fixture(tmp_path,turn,layer);source=tmp_path/'source.kicad_pcb'
    field._save_field_snapshot(b,source);target=force._copy_family(source,tmp_path/'target')
    real_audit=supply.audit
    def audit(board,**kwargs):
        kwargs['netclass_resolver']=lambda n:dict(name='Power',track_width=.5,clearance=.2)
        return real_audit(board,**kwargs)
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary),\
            mock.patch.object(supply,'audit',side_effect=audit):
        b=pcbnew.LoadBoard(str(source));old={force._uid(t)for t in b.GetTracks()}
        report=supply.construct(b,board_hint='synthetic',include_nets=[net],timeout_s=5.,
            allow_supply_prefixes=True,netclass_resolver=lambda n:dict(name='Power',track_width=.5,clearance=.2))
        assert report['created_uuids']
        additive.save_native_additions(target,b,report,old,board_hint='synthetic')
        row=dict(kind='distributed_supply_join',candidate=str(target),candidate_sha256=force._hash(target),net=net)
        assert module.validate_phases([row])==['distributed_supply_join']
        received,proof=module.receive_phase(source,source,row,'synthetic')
    assert received==target and proof['ok']and proof['complete'],proof
    assert proof['source_components']==2 and proof['candidate_components']==1
    assert not proof['current_qualified']and not proof['release_authority']


def test_dispatch_never_substitutes_an_ordinary_owner_for_a_missing_supply_contract(tmp_path):
    module=wrapper();source,target,uid,net=ordinary_fixture(tmp_path)
    row=dict(kind='distributed_supply_join',candidate=str(target),candidate_sha256=force._hash(target),net=net)
    module.validate_phases([row])
    with pytest.raises(AssertionError):module.receive_phase(source,source,row,'synthetic')
