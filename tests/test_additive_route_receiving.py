"""Source-plus-delta replay refuses stale fill, power edits and broad rules."""
from pathlib import Path

import pcbnew
import pytest

import cec_additive_route_receiving as receiving
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def terminal(board,ref,at):
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*at))
    pad=pcbnew.PAD(fp);pad.SetPadName('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetPosition(fp.GetPosition());layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers);pad.SetNetCode(board.GetNetcodeFromNetname('/CONTROL'))
    fp.Add(pad);board.Add(fp)


def barrel(board,at,diameter=.6,drill=.3):
    item=pcbnew.PCB_VIA(board);item.SetViaType(pcbnew.VIATYPE_THROUGH)
    item.SetPosition(pcbnew.VECTOR2I_MM(*at));item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    item.SetWidth(pcbnew.FromMM(diameter));item.SetDrill(pcbnew.FromMM(drill))
    item.SetNetCode(board.GetNetcodeFromNetname('/CONTROL'));board.Add(item)
    return item


def fixture(tmp_path,*,compact=False,existing_group=False):
    source,board=ground_fixture(tmp_path)
    if compact:
        terminal(board,'X1',(22,14))
        if existing_group:
            terminal(board,'X2',(26,14))
            item=barrel(board,(26,14),.35,.25)
            evidence=fr.group_local_pofv_signal_vias(board,[item])
            assert evidence
            fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    field._save_field_snapshot(board,source)
    family=force._sidecars(source);before=source.read_bytes()
    trial=force._copy_family(source,tmp_path/'trial')
    board=pcbnew.LoadBoard(str(trial))
    item=barrel(board,(22,14),.30 if compact else .6,.20 if compact else .3)
    track(board,'/CONTROL',(22,14),(25,16))
    if compact:assert fr.group_local_pofv_signal_vias(board,[item])
    field._save_field_snapshot(board,trial)
    final=receiving.finalize_private(source,trial,tmp_path/'final')
    assert source.read_bytes()==before and force._sidecars(source)==family
    return source,trial,Path(final['board'])


@pytest.mark.parametrize('compact,existing_group',[(False,False),(True,False),(True,True)])
def test_independent_replay_accepts_only_exact_refill_and_qualified_rules(tmp_path,compact,existing_group):
    source,trial,final=fixture(tmp_path,compact=compact,existing_group=existing_group)
    result=receiving.receive(source,final)
    assert result['ok'] is True and result['complete'] is True,result
    assert result['original_power_and_terminal_geometry_exact'] is True
    assert result['existing_ground_fill_matches_independent_native_replay'] is True
    assert result['release_authority'] is False
    assert not receiving.receive(source,trial)['ok']  # the trial still has stale GND


@pytest.mark.parametrize('mutation',['old_track','ground_outline','power_zone','group','rule','project'])
def test_unrelated_mutation_never_hides_behind_ground_refill(tmp_path,mutation):
    source,trial,final=fixture(tmp_path,compact=True,existing_group=True)
    board=pcbnew.LoadBoard(str(final))
    if mutation=='old_track':
        uid=next(iter(pcbnew.LoadBoard(str(source)).GetTracks())).m_Uuid.AsString()
        item=next(t for t in board.GetTracks() if t.m_Uuid.AsString()==uid)
        item.SetLocked(not item.IsLocked())
    elif mutation=='ground_outline':
        zone=next(z for z in board.Zones() if z.GetNetname()=='GND')
        zone.Outline().SetVertex(0,pcbnew.VECTOR2I_MM(1,1))
    elif mutation=='power_zone':
        # Even a new power pour is outside this explicitly additive route scope.
        z=pcbnew.ZONE(board);z.SetLayer(pcbnew.F_Cu)
        z.SetNetCode(board.GetNetcodeFromNetname('/CONTROL'))
        z.Outline().NewOutline()
        for x,y in ((18,10),(20,10),(20,12),(18,12)):z.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
        board.Add(z)
    elif mutation=='group':
        next(iter(board.Groups())).SetName('UNQUALIFIED_RENAMED_OWNERSHIP')
    elif mutation=='rule':
        rules=final.with_suffix('.kicad_dru')
        rules.write_text(rules.read_text()+'\n(rule "Bad broad waiver" (constraint clearance (min 0mm)))\n')
    else:
        project=final.with_suffix('.kicad_pro');project.write_text(project.read_text()+'\n')
    if mutation not in ('rule','project'):field._save_field_snapshot(board,final)
    result=receiving.receive(source,final)
    assert result['ok'] is False and not result['complete'],result
    assert result['errors']


def test_fabricated_via_group_is_not_factory_permission(tmp_path):
    source,trial,final=fixture(tmp_path,compact=True)
    board=pcbnew.LoadBoard(str(final))
    item=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    item.SetWidth(pcbnew.FromMM(.25))  # .025 mm annulus is below the declared process
    field._save_field_snapshot(board,final)
    result=receiving.receive(source,final)
    assert not result['ok'] and 'unqualified' in result['errors'][0],result


def test_disabled_budget_refuses_before_copy(tmp_path):
    result=receiving.receive(tmp_path/'absent.kicad_pcb',tmp_path/'other.kicad_pcb',timeout_s=0)
    assert result['ok'] is False and result['errors']==['ValueError:invalid_receiving_budget']


def test_native_additive_save_preserves_power_and_only_groups_incoming_vias(tmp_path):
    import cec_additive_pair_repair as additive
    source,board=ground_fixture(tmp_path)
    terminal(board,'X44',(22,14))
    terminal(board,'X89',(26,14))
    old=barrel(board,(26,14),.35,.25)
    evidence=fr.group_local_pofv_signal_vias(board,[old])
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    field._save_field_snapshot(board,source)
    source.with_suffix('.pourfirst-state.json').write_text('{"placement_scope":"complete","exact_admission":{"passed":false},"local_copper_contract":{"schema":1}}')
    trial=force._copy_family(source,tmp_path/'native-trial')
    board=pcbnew.LoadBoard(str(trial))
    original={str(t.m_Uuid.AsString()) for t in board.GetTracks()}
    incoming=barrel(board,(22,14),.3,.2)
    track(board,'/CONTROL',(22,14),(25,16))
    report=additive.save_native_additions(trial,board,{},original)
    assert report['zone_refill']['protected_power_fill_recompiled'] is False
    assert receiving.receive(source,trial)['ok']
    # Native retention is usable despite unqualified local metadata, but that
    # metadata remains unqualified and the source stays immutable.
    proof=additive._invariant_worker(str(source),str(trial))
    assert proof['ok'] and not proof['release_authority'],proof


def test_actual_importer_binds_exact_factory_rule_after_source_sidecars():
    import inspect
    text=inspect.getsource(fr.import_ses)
    copied=text.index('copy_project_sidecars(board_path, out_path)')
    bound=text.index('cec_additive_route_receiving.bind_local_via_rule(board,out_path)')
    assert copied<bound
