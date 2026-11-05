"""Source-local proposal geometry is not new process or route authority."""
import time
import pcbnew
import pytest
import cec_escape_pose_frontier as events
import cec_force_current as force
import cec_field_coupling as field
from test_ground_local_mesh_entry import fixture as local_fixture


def source_fixture(tmp_path,quarter=0,layer=pcbnew.F_Cu):
    b,source,owner,cap,via=local_fixture(tmp_path,quarter=quarter,layer=layer,barrier=False)
    pads=list(owner.Pads());xs=[p.GetPosition().x for p in pads];ys=[p.GetPosition().y for p in pads]
    points=[(min(xs)-500000,min(ys)-500000),(max(xs)+500000,min(ys)-500000),
        (max(xs)+500000,max(ys)+500000),(min(xs)-500000,max(ys)+500000)]
    for a,z in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(owner);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.F_CrtYd if layer==pcbnew.F_Cu else pcbnew.B_CrtYd)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));line.SetWidth(50000);owner.Add(line)
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    return b,source,b.FindFootprintByReference(owner.GetReference()),b.FindFootprintByReference(cap.GetReference())


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_saved_local_event_contract_is_same_floor_typed_and_read_only(tmp_path,quarter,layer):
    b,source,owner,cap=source_fixture(tmp_path,quarter,layer);before=force._family(source,'synthetic')
    ids=[force._uid(next(p for p in fp.Pads()if p.GetNetname()=='GND'))for fp in(owner,cap)]
    proof=events._source_local_event_contract(b,ids,board_hint='synthetic',deadline=time.monotonic()+10.)
    assert(proof['diameter_nm'],proof['drill_nm'])==(500000,300000)
    assert proof['maximum_ground_reach_mm']==1.5
    assert all(r['all_local_dimensions_at_or_above_ordinary_setup']for r in proof['roots'])
    assert proof['final_source_local_mesh_receiving_still_required']and not proof['release_authority']
    assert force._family(source,'synthetic')==before


@pytest.mark.parametrize('fault',['unknown_owner','regulator','wrong_net','missing_rule','underfloor',
    'unsaved_pose','source_changed','code_changed','deadline'])
def test_local_event_contract_cannot_infer_or_borrow_source_authority(tmp_path,monkeypatch,fault):
    b,source,owner,cap=source_fixture(tmp_path);ground=next(p for p in owner.Pads()if p.GetNetname()=='GND')
    if fault=='unknown_owner':owner.SetValue('UNKNOWN_MANUFACTURER')
    elif fault=='regulator':owner.SetValue('TPS2121RUXR')
    elif fault=='wrong_net':ground.SetNet(b.FindNet('+3V3'))
    elif fault=='missing_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='underfloor':source.with_suffix('.kicad_dru').write_text(source.with_suffix('.kicad_dru').read_text().replace('0.5mm','0.4mm'))
    elif fault=='unsaved_pose':owner.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='source_changed':
        actual=force._family;calls=0
        def changing(*a,**k):
            nonlocal calls
            calls+=1
            return actual(*a,**k)if calls==1 else {'stale':True}
        monkeypatch.setattr(force,'_family',changing)
    elif fault=='code_changed':
        actual=force._code_identity;calls=0
        def changing():
            nonlocal calls
            calls+=1
            return actual()if calls==1 else {'stale':True}
        monkeypatch.setattr(force,'_code_identity',changing)
    if fault in('unknown_owner','regulator','wrong_net'):field._save_field_snapshot(b,source)
    deadline=time.monotonic()-1 if fault=='deadline'else time.monotonic()+10.
    with pytest.raises((ValueError,RuntimeError,OSError)):
        events._source_local_event_contract(b,[force._uid(ground)],board_hint='synthetic',deadline=deadline)


def test_event_optin_uses_source_geometry_not_factory_default_and_keeps_measurement_scope(tmp_path):
    b,source,owner,cap=source_fixture(tmp_path)
    common=dict(selected_refs=[owner.GetReference(),cap.GetReference()],retired_uuids=[],
        radius_mm=1.,max_sites=4,timeout_s=10.,shared_entry_proposals=True)
    legacy=events.ground_translation_events(b,owner.GetReference(),**common)
    scoped=events.ground_translation_events(b,owner.GetReference(),**common,
        source_local_ground=True,board_hint='synthetic')
    assert legacy['declared_portal_geometry_mm']==[.35,.25]and legacy['immediate_portal_reach_mm']==.8
    assert 'source_local_ground_contract'not in legacy
    assert scoped['declared_portal_geometry_mm']==[.5,.3]and scoped['immediate_portal_reach_mm']==1.5
    assert scoped['measurement_portal_reach_mm']==0.
    assert not scoped['routing_admitted']and not scoped['no_path_proof']


def test_ground_local_reach_does_not_expand_manufacturer_measurement_portals(tmp_path):
    b,source,owner,cap=source_fixture(tmp_path)
    for index,pin in enumerate(('9','10')):
        net=pcbnew.NETINFO_ITEM(b,'SOURCE_MEASUREMENT_'+pin);b.Add(net)
        pad=pcbnew.PAD(owner);pad.SetNumber(pin);pad.SetNet(net);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
        owner.Add(pad);pad.SetPosition(pcbnew.VECTOR2I_MM(7+index*.5,7))
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    proof=events.ground_translation_events(b,owner.GetReference(),selected_refs=[owner.GetReference(),cap.GetReference()],
        retired_uuids=[],radius_mm=1.,max_sites=4,timeout_s=10.,shared_entry_proposals=True,
        surface_proposals=True,measurement_portal_proposals=True,source_local_ground=True,board_hint='synthetic')
    assert proof['immediate_portal_reach_mm']==1.5
    assert proof['measurement_portal_reach_mm']==.8
    assert len(proof['source_typed_measurement_portal_witnesses'])==2


@pytest.mark.parametrize('options',[{'source_local_ground':1},{'source_local_ground':True},
    {'source_local_ground':True,'board_hint':'synthetic'}])
def test_local_event_optin_requires_named_source_and_shared_typed_roots(options):
    with pytest.raises(ValueError,match='bounded_native_ground_translation_events_required'):
        events.ground_translation_events(None,'owner',selected_refs=[],retired_uuids=[],**options)


@pytest.mark.parametrize('groups',['bad',['x','x'],[True],[[]],['x']*9])
def test_cut_aware_group_scope_is_explicit_bounded_and_not_coerced(groups):
    with pytest.raises(ValueError,match='bounded_source_cell_events_required'):
        events.cell_translation_events('absent',['owner'],board_hint='opaque',seed_delta_mm=(0,0),reference_group_uuids=groups)


def test_cut_aware_wrapper_threads_exact_groups_to_real_authority_before_projection(tmp_path,monkeypatch):
    b,source,owner,cap=source_fixture(tmp_path);calls=[]
    def authority(board,poses,**kwargs):
        calls.append(kwargs);raise ValueError('independent_group_authority_refused')
    monkeypatch.setattr(events.escape,'prepare',authority)
    with pytest.raises(ValueError,match='independent_group_authority_refused'):
        events.cell_translation_events(source,[owner.GetReference()],board_hint='synthetic',
            seed_delta_mm=(.1,0),reference_group_uuids=['literal-source-group'])
    assert calls[0]['reference_group_uuids']==['literal-source-group']


def test_cut_aware_unknown_group_is_not_permission_to_project(tmp_path):
    b,source,owner,cap=source_fixture(tmp_path)
    with pytest.raises(ValueError):events.cell_translation_events(source,[owner.GetReference()],
        board_hint='synthetic',seed_delta_mm=(.1,0),reference_group_uuids=['forged-not-present'])


def test_real_recognized_group_is_carried_by_cut_aware_source_compiler(tmp_path,monkeypatch):
    from test_cell_escape_replan import fixture
    import cec_source_reference_group_transport as transport
    from shapely.ops import nearest_points
    import cec_assembly_envelope as assembly
    b,_,owner,cap=fixture(monkeypatch,prefix='scoped');owner.Reference().SetVisible(False)
    points=[(8500000,8500000),(11500000,8500000),(11500000,11500000),(8500000,11500000)]
    for a,z in zip(points,points[1:]+points[:1]):
        line=pcbnew.PCB_SHAPE(owner);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.F_CrtYd)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));line.SetWidth(50000);owner.Add(line)
    group=pcbnew.PCB_GROUP(b);group.SetName(transport.PREFIX+owner.GetReference());b.Add(group);group.AddItem(owner)
    text=pcbnew.PCB_TEXT(b);text.SetText(owner.GetReference());text.SetLayer(pcbnew.B_SilkS);text.SetMirrored(True)
    text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));text.SetTextThickness(120000);text.SetPosition(pcbnew.VECTOR2I_MM(10,17))
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    b.Add(text);group.AddItem(text)
    court=pcbnew.SHAPE_POLY_SET(owner.GetCourtyard(owner.GetLayer()));chain=court.COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    shape=pcbnew.SHAPE_POLY_SET();text.TransformShapeToPolygon(shape,pcbnew.B_SilkS,0,1000,pcbnew.ERROR_OUTSIDE,False)
    a,z=nearest_points(assembly.polygon_from_native(court),assembly.polygon_from_native(shape).envelope.buffer(.262,join_style=2))
    segments=list(zip(vertices,vertices[1:]+vertices[:1]))+[(tuple(round(v*1e6)for v in a.coords[0]),tuple(round(v*1e6)for v in z.coords[0]))]
    for a,z in segments:
        line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.B_SilkS)
        line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z));line.SetWidth(120000);b.Add(line);group.AddItem(line)
    group.SetLocked(True);owner.SetLocked(False)
    source=tmp_path/'grouped.kicad_pcb';field._save_field_snapshot(b,source)
    uid=force._uid(group);transport.inspect(source,owner_uuid=force._uid(owner),group_uuid=uid)
    before=force._family(source,'opaque');calls=[]
    def projected(private,owners,**kwargs):
        calls.append(1)
        live=next(i for i in private.GetDrawings()if force._uid(i)==force._uid(text))
        assert tuple(live.GetPosition())==(10100000,17000000)
        return dict(deltas_mm=[],no_path_proof=False)
    monkeypatch.setattr(events,'assembly_translation_events',projected)
    result=events.cell_translation_events(source,[owner.GetReference()],board_hint='opaque',
        seed_delta_mm=(.1,0),reference_group_uuids=[uid])
    assert calls and result['source_and_code_unchanged']
    assert force._family(source,'opaque')==before
