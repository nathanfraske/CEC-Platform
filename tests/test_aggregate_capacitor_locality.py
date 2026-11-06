"""Fresh Source locality and real saved local-loop controls.

Only pre-existing aggregate current authority is fixture-stubbed, as in the
base cap tests. The hierarchy exporter, owner roles, native saved replay and
full-width local-path calculation are real.
"""
import copy
import pcbnew
import pytest
import cec_source_aggregate_capacitor_cell as op
from test_source_aggregate_capacitor_cell import fixture,proposal,saved
from test_field_proposals import track


def annotate(source,root,key,value):
    b=pcbnew.LoadBoard(str(source));fp=b.FindFootprintByReference('RENAMED_C');fp.SetField(key,value)
    op.field._save_field_snapshot(b,source)
    pieces=[]
    for tag,block in op.leaf.sch.SchFile(str(root)).children:
        if tag=='symbol'and op.leaf.sch.prop_value(block,'Reference')=='RENAMED_C':
            block=block[:-1]+f'(property "{key}" "{value}" (at 50 50 0) (effects (font (size 1 1)))))'
        pieces.append(block)
    root.write_text('(kicad_sch\n'+'\n'.join(pieces)+'\n)')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_positive_owner_is_fresh_canonical_not_assignment_leftover(tmp_path,monkeypatch,quarter,back):
    source,root,uid=fixture(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes();board,q=proposal(source,root,uid)
    local=q['source_locality_owner']
    assert local['owner_ref']=='AMP73'and local['pin']=='6'
    assert local['source_pin']['type']=='power_in'
    assert local['maximum_distance_mm']==local['maximum_supply_path_mm']==3.5
    assert local['face']==(pcbnew.B_Cu if back else pcbnew.F_Cu)
    assert q['unchanged_selected_bypass_assignments']['AMP73:6:100n']=='EXISTING_FEED'
    assert source.read_bytes()==raw


@pytest.mark.parametrize('note',['parallel bulk','distribution reservoir','place anywhere'])
def test_free_text_cannot_export_a_Source_local_capacitor(tmp_path,monkeypatch,note):
    source,root,uid=fixture(tmp_path,monkeypatch);annotate(source,root,'Note',note)
    with pytest.raises(ValueError,match='target_capacitor_must_remain_local'):
        op.compile(source,footprint_uuid=uid,target_pose=[25,25,0],board_hint=str(root),max_shift_mm=64)


@pytest.mark.parametrize('fault',['unknown_owner','owner_MPN','source_Note','source_declaration','ambiguous_requirement'])
def test_missing_or_ambiguous_Source_locality_fails_closed(tmp_path,monkeypatch,fault):
    source,root,uid=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));owner=b.FindFootprintByReference('AMP73')
    if fault=='unknown_owner':
        owner.SetValue('UNKNOWN');owner.SetField('MPN','UNKNOWN')
        root.write_text(root.read_text().replace('INA181A2IDBVR','UNKNOWN'))
    elif fault=='owner_MPN':owner.SetField('MPN','INA181A1IDBVR')
    elif fault=='source_Note':b.FindFootprintByReference('RENAMED_C').SetField('Note','not in actual schematic')
    elif fault=='source_declaration':b.FindFootprintByReference('RENAMED_C').SetField('BypassOwner','AMP99.6')
    else:
        # Synthetic requirement-table corruption, not a native positive or
        # a mocked geometry verdict: two owners may never be guessed.
        actual=op.constraints._device_bypass_assignment(b)
        duplicate=copy.copy(actual['requirements'][0]);duplicate['ref']='SECOND_OWNER'
        actual['requirements']=[*actual['requirements'],duplicate]
        monkeypatch.setattr(op.constraints,'_device_bypass_assignment',lambda *a,**k:actual)
    op.field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):proposal(source,root,uid)


def test_real_saved_short_full_width_local_supply_loop_is_received(tmp_path,monkeypatch):
    source,child,q=saved(tmp_path,monkeypatch);r=op.receive(source,child,q)
    assert r['ok']and r['complete'],r
    assert 0<r['actual_cell_paths']['actual_Source_owner_local_supply_path_mm']<=3.5
    assert r['actual_cell_paths']['source_locality_owner']['owner_ref']=='AMP73'


def test_near_pad_but_long_full_width_native_detour_is_not_local(tmp_path,monkeypatch):
    source,root,uid=fixture(tmp_path,monkeypatch);board,q=proposal(source,root,uid)
    points=[(13.5,14),(12,12.5),(12,10),(16,10)]
    for a,z in zip(points,points[1:]):track(board,'/ALPHA',a,z,width=.5)
    track(board,'GND',(14.5,14),(15.2,14),width=.2)
    child=op.force._copy_family(source,tmp_path/'long-loop')
    op.additive._ground_refill(board);op.save_private(board,child,q)
    r=op.receive(source,child,q)
    assert not r['ok']and r['failed_stage']=='actual_paths_and_returns',r
    assert any('actual_full_width_local_supply_loop_required'in e for e in r['errors']),r


def test_receive_rederives_locality_not_serialized_owner_or_bound(tmp_path,monkeypatch):
    source,child,q=saved(tmp_path,monkeypatch)
    q['source_locality_owner']['maximum_supply_path_mm']=32
    r=op.receive(source,child,q)
    assert not r['ok']and r['failed_stage']=='Source_recompile',r
