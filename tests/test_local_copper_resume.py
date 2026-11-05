"""Local PI handoff is item/contact scoped, independent of board/net names."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pcbnew
import pytest
import cec_power_local_replay as local
import cec_placement_route_prefix as prefix
import cec_fr
import cec_frozen_copper
from test_power_local_replay import fixture,copper


def unrelated(board,net):
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNRELATED');board.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(net)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
    p.SetLayerSet(layers);p.SetPosition(pcbnew.VECTOR2I_MM(40,40));fp.Add(p)
    return fp


def legacy(board,items):
    c=local.capture(board,[i.m_Uuid.AsString() for i in items]);c.pop('terminal_refs')
    c['schema']=1;c['terminal_sha256']=local._digest(local._terminals(board,{i.GetNetname() for i in items}))
    return c


def test_shared_supply_is_not_a_global_placement_lock():
    b,n=fixture();items=copper(b,n);fp=unrelated(b,n)
    c=local.capture(b,[i.m_Uuid.AsString() for i in items])
    assert c['terminal_refs']==['DEVICE']
    fp.SetPosition(pcbnew.VECTOR2I_MM(1,2))
    assert local.verify_present(b,c)['ok']
    assert local.replay(b,c)['reused']==3


@pytest.mark.parametrize('defect',['move','flip','shape','layer','net','package','remove'])
def test_incident_terminal_changes_are_rejected(defect):
    b,n=fixture();items=copper(b,n)
    c=local.capture(b,[i.m_Uuid.AsString() for i in items])
    fp=b.FindFootprintByReference('DEVICE');pad=next(iter(fp.Pads()))
    if defect=='move':fp.SetPosition(pcbnew.VECTOR2I_MM(1,0))
    elif defect=='flip':fp.Flip(fp.GetPosition(),False)
    elif defect=='shape':pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif defect=='layer':pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    elif defect=='net':pad.SetNetCode(0)
    elif defect=='package':fp.SetFPID(pcbnew.LIB_ID('changed','package'))
    else:b.Remove(fp)
    with pytest.raises(ValueError,match='terminal'):local.verify_present(b,c)


@pytest.mark.parametrize('defect',['uuid','lock','groups','geometry'])
def test_presence_proof_never_repairs_or_substitutes(defect):
    b,n=fixture();items=copper(b,n)
    c=local.capture(b,[i.m_Uuid.AsString() for i in items])
    if defect=='uuid':items[0].m_Uuid.Clone(pcbnew.KIID())
    elif defect=='lock':items[0].SetLocked(False)
    elif defect=='groups':next(iter(b.Groups())).RemoveItem(items[0])
    else:items[0].SetWidth(pcbnew.FromMM(.4))
    before={i.m_Uuid.AsString():local._geometry(b,i) for i in b.GetTracks()}
    with pytest.raises(ValueError):local.verify_present(b,c)
    assert before=={i.m_Uuid.AsString():local._geometry(b,i) for i in b.GetTracks()}


def test_legacy_upgrade_requires_unchanged_original_not_an_already_moved_board():
    b,n=fixture();items=copper(b,n);fp=unrelated(b,n);c=legacy(b,items)
    scoped=local.for_placement(b,c)
    assert scoped['schema']==2 and scoped['sha256']==c['sha256']
    fp.SetPosition(pcbnew.VECTOR2I_MM(1,0))
    with pytest.raises(ValueError,match='terminal'):local.for_placement(b,c)
    assert local.verify_present(b,scoped)['ok']


def test_new_same_net_contact_is_not_silently_added():
    b,n=fixture();items=copper(b,n);fp=unrelated(b,n)
    c=local.capture(b,[i.m_Uuid.AsString() for i in items])
    next(iter(fp.Pads())).SetPosition(pcbnew.VECTOR2I_MM(10,10))
    with pytest.raises(ValueError,match='contact scope'):local.verify_present(b,c)
    target,n=fixture();fp=unrelated(target,n)
    next(iter(fp.Pads())).SetPosition(pcbnew.VECTOR2I_MM(10,10))
    with pytest.raises(ValueError,match='contact scope'):local.replay(target,c)
    assert not list(target.GetTracks())


def test_item_scoped_anchor_is_fixed_but_other_same_net_device_is_not(tmp_path):
    b,n=fixture();items=copper(b,n);unrelated(b,n)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    ctx=cec_frozen_copper.FrozenCopperContext(path,[],item_uuids=[i.m_Uuid.AsString() for i in items])
    assert ctx.anchor_refs=={'DEVICE'}
    proof=ctx.check({'DEVICE':(1,0,0)})
    assert not proof['ok'] and proof['violations'][0]['attachments_complete']
    assert ctx.check({'UNRELATED':(1,0,0)})['ok']


@pytest.mark.parametrize('name',['GND','AUXILIARY/VOLTAGE'])
def test_prefix_captures_local_items_without_whole_net_or_pair_authority(tmp_path,name):
    b,n=fixture();n.SetNetname(name);items=copper(b,n)
    c=legacy(b,items)
    extra=pcbnew.PCB_TRACK(b);extra.SetNet(n);extra.SetLocked(True)
    extra.SetStart(pcbnew.VECTOR2I_MM(30,30));extra.SetEnd(pcbnew.VECTOR2I_MM(31,30))
    extra.SetWidth(pcbnew.FromMM(.2));extra.SetLayer(pcbnew.F_Cu);b.Add(extra)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    state={'placement_scope':'complete','exact_admission':{'passed':True},'local_copper_contract':c}
    state_path=path.with_suffix('.pourfirst-state.json');state_path.write_text(json.dumps(state))
    with patch('cec_precision_route.derive_coupled_pairs',return_value=[]), \
         patch('cec_fr.locked_pour_authority_nets_board',return_value=set()):
        result=prefix.capture(path)
        assert prefix.preserved_nets(result)==()
        assert set(prefix.preserved_uuids(result))=={i.m_Uuid.AsString() for i in items}
        coverage=prefix.rehydration_coverage(b,result)
        assert coverage['unpreserved_items']==1 and coverage['preserved_items']==3
        assert result['items']==3 and cec_fr.check_copper_geometry_prefix(str(path),result)['ok']
        assert prefix.check_local_copper(path,result)['ok']
        state['exact_admission']['passed']=False;state_path.write_text(json.dumps(state))
        with pytest.raises(ValueError,match='admitted'):prefix.capture(path)


def test_published_materializer_state_does_not_point_into_deleted_staging(tmp_path,monkeypatch):
    import cec_synth_pipeline as synth
    out=tmp_path/'published.kicad_pcb'
    def emit(candidate,cfg,path):
        p=Path(path);p.write_text('synthetic board')
        skeleton=p.with_suffix('.pourfirst-skeleton.kicad_pcb');skeleton.write_text('frozen source')
        p.with_suffix('.pourfirst-state.json').write_text(json.dumps({'skeleton':str(skeleton)}))
    monkeypatch.setattr(synth,'_materialize_rehydrated_board',emit)
    monkeypatch.setattr(synth,'_normalize_materialized_item_ids',lambda p:None)
    monkeypatch.setattr(synth,'_admit_materialized_power_prefix',lambda *a:None)
    candidate=SimpleNamespace(source_board='source',protected_power_prefix={'items':1})
    synth.materialize(candidate,SimpleNamespace(),str(out))
    state=json.loads(out.with_suffix('.pourfirst-state.json').read_text())
    assert Path(state['skeleton']).read_text()=='frozen source'
    assert Path(state['skeleton']).parent==out.parent


def test_missing_frozen_skeleton_prevents_publication(tmp_path):
    p=tmp_path/'stage.kicad_pcb'
    p.with_suffix('.pourfirst-state.json').write_text(json.dumps({'skeleton':'missing.kicad_pcb'}))
    with pytest.raises(ValueError,match='skeleton is missing'):
        prefix.rebase_published_state(p,tmp_path/'final.kicad_pcb')
