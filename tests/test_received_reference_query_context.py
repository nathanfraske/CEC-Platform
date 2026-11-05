"""Explicit received association queries never accept the copper delta."""
import copy
import json
from pathlib import Path

import cec_swig_guard
cec_swig_guard.pin()
import wx
_quiet=wx.LogNull()
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_nonpolar_print_context as op
import cec_mask_search_reference_mapping as maps
import cec_reference_association_query as association
import cec_chained_annotation_transition as chain
import test_received_guide_print_context as guides
from test_chained_annotation_transition import env,bound
from test_nested_historical_map_replay_20261024 import nested,receive_discovered_map


MODE='same_literal_map_queries'


def _polygon(x):
    p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
    for point in ((x,30),(x+2,30),(x+2,32),(x,32)):
        p.Append(pcbnew.VECTOR2I_MM(*point))
    return p


def _format(item):
    writer=pcbnew.PCB_IO_KICAD_SEXPR();writer.Format(item)
    return writer.GetStringOutput(True)


def case(tmp_path,monkeypatch,*,back=False):
    original=guides.fixture
    def fixture(*args,**kwargs):
        source,table,ids,library=original(*args,**kwargs)
        b=pcbnew.LoadBoard(str(source));net=pcbnew.NETINFO_ITEM(b,'/query_existing_copper');b.Add(net)
        via=pcbnew.PCB_VIA(b);via.SetNet(net);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetPosition(pcbnew.VECTOR2I_MM(45,33));b.Add(via)
        zone=pcbnew.ZONE(b);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(net)
        poly=_polygon(48);zone.Outline().Append(poly);zone.SetFilledPolysList(pcbnew.F_Cu,poly)
        zone.SetIsFilled(True);b.Add(zone);field._save_field_snapshot(b,source)
        return source,table,ids,library
    with monkeypatch.context()as m:
        m.setattr(guides,'fixture',fixture)
        ancestor,mapped,declaration,options=guides.case(tmp_path,monkeypatch,back=back,with_signal=True)
    candidate=force._copy_family(mapped,tmp_path/'copper-child')
    board=pcbnew.LoadBoard(str(mapped));track=next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK')
    via=next(t for t in board.GetTracks()if t.GetClass()=='PCB_VIA');zone=next(iter(board.Zones()))
    retired={force._uid(track),force._uid(via)}
    track.m_Uuid.Clone(pcbnew.KIID());track.Move(pcbnew.VECTOR2I(0,1000000))
    via.m_Uuid.Clone(pcbnew.KIID());via.Move(pcbnew.VECTOR2I(1000000,0))
    # Exact preserved outline, but genuinely different saved filled material.
    zone.SetFilledPolysList(pcbnew.F_Cu,_polygon(48.1));zone.SetIsFilled(True)
    text=mapped.read_text();spans=op.raw.inventory(text);edits=[]
    for uid in retired:edits.append((*spans[uid],''))
    edits.append((*spans[force._uid(zone)],_format(zone)))
    for a,z,replacement in sorted(edits,reverse=True):text=text[:a]+replacement+text[z:]
    at=text.rfind(')');text=text[:at]+_format(track)+_format(via)+text[at:]
    candidate.write_text(text)
    inherited=dict(declaration,mapped_source=bound(mapped),association_identity=MODE)
    return ancestor,mapped,candidate,inherited,options


@pytest.mark.parametrize('back',[False,True])
def test_real_received_interrupted_map_cut_hole_refill_and_full_print_replay(tmp_path,monkeypatch,back):
    ancestor,mapped,candidate,declaration,options=case(tmp_path,monkeypatch,back=back)
    before={p:p.read_bytes()for p in(ancestor,mapped,candidate)}
    default=copy.deepcopy(declaration);default.pop('association_identity')
    with pytest.raises(ValueError,match='only_bounded_unmasked_new_tracks'):
        op.plan(candidate,**options,reference_mapping_transition=default)
    q=op.plan(candidate,**options,reference_mapping_transition=declaration)
    assert q['reference_mapping_transition']==declaration
    records=[r['source_reference_map']for r in q['records']if r.get('source_reference_map')]
    assert len(records)==1;record=records[0]
    assert record['same_literal_Source_map_queries_independently_received']
    assert record['fresh_producer_receiving_precedes_association_query']
    assert record['reference_association_kind']=='fresh_received_same_literal_map_queries'
    assert len(record['exact_same_literal_map_query_sha256'])==64
    assert 'strict_opaque_Source_additive_ancestry_independently_received'not in record
    assert not record['closed_assembly_body_authority']and not record['mask_or_print_admission']
    assert record['unrelated_PCB_changes_not_received']and not record['copper_addition_admission_or_current_authority']
    assert str(Path(association.__file__).resolve())in q['dependency_sha256']
    # Replanning must produce the SAME stable query evidence, not a timing hash.
    again=op.plan(candidate,**options,reference_mapping_transition=declaration)
    assert again==q
    artifact=op.construct_private(candidate,q,tmp_path/'printed')
    received=op.receive(candidate,artifact['candidate'],q)
    assert received['ok']and received['complete'],received
    assert all(p.read_bytes()==text for p,text in before.items())


@pytest.mark.parametrize('bad',[None,True,False,'',MODE+'-unknown',{'mode':MODE}])
def test_query_mode_is_an_exact_enum_not_a_truthy_bypass(tmp_path,monkeypatch,bad):
    _,_,candidate,declaration,options=case(tmp_path,monkeypatch);declaration['association_identity']=bad
    with pytest.raises(ValueError,match='explicit_same_literal_map_query'):
        op.plan(candidate,**options,reference_mapping_transition=declaration)


@pytest.mark.parametrize('fault',['missing_mapped','extra_flag','stale_mapped','unreceived_source','moved_group','process'])
def test_current_query_inputs_cannot_waive_any_source_or_identity_boundary(tmp_path,monkeypatch,fault):
    _,mapped,candidate,declaration,options=case(tmp_path,monkeypatch)
    if fault=='missing_mapped':declaration.pop('mapped_source')
    elif fault=='extra_flag':declaration['allow_changes']=True
    elif fault=='stale_mapped':declaration['mapped_source']['sha256']='0'*64
    elif fault=='unreceived_source':declaration['source']=bound(mapped)
    elif fault=='process':candidate.with_suffix('.kicad_dru').write_text('(version 1)\n# changed')
    else:
        b=pcbnew.LoadBoard(str(candidate));guide=next(i for g in b.Groups()for i in g.GetItems()if i.GetClass()=='PCB_SHAPE')
        guide.Move(pcbnew.VECTOR2I(1,0));field._save_field_snapshot(b,candidate)
    with pytest.raises(ValueError):op.plan(candidate,**options,reference_mapping_transition=declaration)


def test_failed_live_producer_never_calls_the_query_comparator(tmp_path,monkeypatch):
    _,_,candidate,declaration,options=case(tmp_path,monkeypatch);seen=[]
    monkeypatch.setattr(maps,'receive',lambda *args:dict(ok=False,complete=False,errors=['live producer refused']))
    def forbidden(*args,**kwargs):seen.append(True);raise AssertionError('query preceded live receiving')
    monkeypatch.setattr(association,'compare',forbidden)
    with pytest.raises(ValueError,match='fresh_saved_reference_mapping_refused'):
        op.plan(candidate,**options,reference_mapping_transition=declaration)
    assert seen==[]


@pytest.mark.parametrize('fault',['gids','duplicate_gids','owner','duplicate_owner','chart_claim'])
def test_query_scope_comes_only_from_fresh_original_manifest(tmp_path,monkeypatch,fault):
    _,_,candidate,declaration,options=case(tmp_path,monkeypatch)
    receive=maps.receive
    def corrupt(*args):
        proof=receive(*args);assert proof['ok']
        if fault=='gids':proof['manifest']['added_reverse_group_uuids']=['invented']
        elif fault=='duplicate_gids':proof['manifest']['added_reverse_group_uuids']*=2
        elif fault=='chart_claim':proof['manifest']['added_group_uuid']='invented'
        return proof
    if fault in('owner','duplicate_owner'):
        path=Path(declaration['proposal']['path']);q=json.loads(path.read_text())
        if fault=='owner':q['records'][0]['footprint_uuid']='invented'
        else:q['records']*=2
        path.write_text(json.dumps(q));declaration['proposal']=bound(path)
    else:monkeypatch.setattr(maps,'receive',corrupt)
    with pytest.raises(ValueError):op.plan(candidate,**options,reference_mapping_transition=declaration)


def test_current_chart_is_not_a_per_owner_literal_query_scope(tmp_path,monkeypatch):
    from test_received_chart_print_context import case as chart_case
    _,mapped,_,_,declaration,options=chart_case(tmp_path,monkeypatch)
    candidate=force._copy_family(mapped,tmp_path/'chart-child')
    declaration.update(mapped_source=bound(mapped),association_identity=MODE)
    with pytest.raises(ValueError,match='require_per_owner_projected_maps'):
        op.plan(candidate,**options,reference_mapping_transition=declaration)


def test_historical_fresh_map_replay_preserves_only_explicit_query_enum(nested,tmp_path):
    env,ancestor,qpath,_,_,seen=nested
    declaration=dict(source=bound(ancestor),proposal=bound(qpath),mapped_source=bound(env[0]),association_identity=MODE)
    work=tmp_path/'fresh-query-map';work.mkdir()
    result=chain._fresh_nested_map(env[2],declaration,'renamed',Path('/canonical'),work,lambda name,fn:fn(),10.)
    assert result['association_identity']==MODE and result['mapped_source']==bound(env[0])
    assert result['proposal']!=bound(qpath)and set(result)==set(declaration)
    assert seen==['new_native','new_plan']
    replay=receive_discovered_map(env[2],result)
    assert replay._options['reference_mapping_transition']['association_identity']==MODE
    assert seen==['new_native','new_plan','new_reconstruct','new_receive']


@pytest.mark.parametrize('fault',['unknown','bool','missing_mapped','extra','chart_flag'])
def test_historical_map_replay_does_not_invent_or_broaden_query_modes(nested,tmp_path,fault):
    env,ancestor,qpath,_,_,_=nested
    declaration=dict(source=bound(ancestor),proposal=bound(qpath),mapped_source=bound(env[0]),association_identity=MODE)
    if fault=='unknown':declaration['association_identity']='anything_else'
    elif fault=='bool':declaration['association_identity']=True
    elif fault=='missing_mapped':declaration.pop('mapped_source')
    elif fault=='extra':declaration['allow_cuts']=True
    else:
        q=json.loads(qpath.read_text());q['opposite_face_chart']=True;qpath.write_text(json.dumps(q));declaration['proposal']=bound(qpath)
    work=tmp_path/'refused-query-map';work.mkdir()
    with pytest.raises(ValueError):chain._fresh_nested_map(env[2],declaration,'renamed',Path('/canonical'),work,lambda name,fn:fn(),10.)
