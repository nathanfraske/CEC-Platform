"""Native and translated fixtures for complete two-layer transition lands."""
import hashlib
import json
from types import SimpleNamespace

import pytest
pcbnew = pytest.importorskip('pcbnew')
import cec_transition_landings as landing


def fixture(offset=0, alternate='In3.Cu', net='SUPPLY'):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    for name in (net, 'OTHER'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    edge = pcbnew.PCB_SHAPE(board)
    edge.SetShape(pcbnew.SHAPE_T_RECT)
    edge.SetLayer(pcbnew.Edge_Cuts)
    edge.SetStart(pcbnew.VECTOR2I(int(offset*1e6), 0))
    edge.SetEnd(pcbnew.VECTOR2I(int((offset+24)*1e6), 24_000_000))
    board.Add(edge)
    sites = [(offset+8.,8.), (offset+9.3,8.)]
    for x,y in sites:
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(pcbnew.VECTOR2I(round(x*1e6),round(y*1e6)))
        via.SetWidth(900_000); via.SetDrill(500_000)
        via.SetNetCode(board.GetNetcodeFromNetname(net)); board.Add(via)
    for layer in ('F.Cu', alternate):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(round((offset+4)*1e6),8_000_000))
        track.SetEnd(pcbnew.VECTOR2I(round((offset+12)*1e6),8_000_000))
        track.SetWidth(500_000); track.SetLayer(board.GetLayerID(layer))
        track.SetNetCode(board.GetNetcodeFromNetname(net)); board.Add(track)
    patches = landing.patches_for(net, sites, ('F.Cu', alternate),
        diameter_mm=.9, drill_mm=.5, margin_mm=.65)
    return board, patches


def test_proposal_filter_rejects_disconnected_field_before_native_fill():
    board,_=fixture()
    segments=[(4.,8.,12.,8.,.5,layer) for layer in ('F.Cu','In3.Cu')]
    allowed=landing.proposal_filter(board,'SUPPLY',('F.Cu','In3.Cu'),segments)
    assert allowed([(8.,8.),(9.3,8.)])
    # Both free barrels can exist, but neither is attached to the primary.
    assert not allowed([(8.,16.),(9.3,16.)])


def test_individually_clipped_site_cannot_poison_every_compact_subset():
    board,_=fixture()
    layers=('F.Cu','In3.Cu')
    segments=[(4.,8.,12.,8.,.5,layer) for layer in layers]
    portal=dict(net='OTHER',at_mm=(8.,8.),diameter_mm=.35,
                layer_ids=[board.GetLayerID('In3.Cu')])
    evidence={}
    allowed=landing.proposal_filter(board,'SUPPLY',layers,segments,
        portals=[portal],evidence=evidence)
    candidates=[(8.,8.),(9.3,8.),(10.6,8.)]
    assert not allowed(candidates[:2])
    assert evidence['rejection_counts']=={'field_land_clipped':1}
    assert evidence['samples'][0]['layer']=='In3.Cu'
    assert evidence['samples'][0]['uncovered_sites']==[[8.,8.]]
    usable=allowed.viable_sites(candidates)
    assert usable==[(9.3,8.),(10.6,8.)]
    assert allowed(usable) and evidence['accepted']
    assert candidates==[(8.,8.),(9.3,8.),(10.6,8.)]


def test_preview_diagnostics_are_bounded_and_do_not_grant_admission():
    board,_=fixture()
    layers=('F.Cu','In3.Cu')
    segments=[(4.,8.,12.,8.,.5,layer) for layer in layers]
    evidence={}
    allowed=landing.proposal_filter(board,'SUPPLY',layers,segments,evidence=evidence)
    for index in range(50):
        assert not allowed([(8.,16.+index*.01),(9.3,16.+index*.01)])
    assert evidence['attempted']==50 and len(evidence['samples'])==4
    assert evidence['rejection_counts']=={'field_not_joined_to_primary':50}
    # Free sites do not imply a joined field.
    assert allowed.viable_sites([(8.,16.),(9.3,16.)])==[(8.,16.),(9.3,16.)]
    assert not allowed([(8.,16.),(9.3,16.)])


def test_sink_field_is_qualified_at_its_actual_transition_not_source_preflight(monkeypatch):
    import math
    import cec_force_rails as rails
    from test_force_rails import _mkboard_alt, MM
    board=_mkboard_alt()
    edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_RECT)
    edge.SetStart(pcbnew.VECTOR2I(MM(-5),MM(-12)))
    edge.SetEnd(pcbnew.VECTOR2I(MM(45),MM(65)))
    edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    original=landing.proposal_filter
    def reject_original_sink(board,net,layers,segments,**kwargs):
        legal=original(board,net,layers,segments,**kwargs)
        if net!='+5V_MAIN': return legal
        face={p for s in segments if s[5]=='F.Cu' for p in (s[:2],s[2:4])}
        body={p for s in segments if s[5]!='F.Cu' for p in (s[:2],s[2:4])}
        if any(math.dist(p,(20.,31.5))>2.51 for p in face & body): return legal
        return landing._ProposalFilter(lambda _sites:False,lambda _site:True)
    monkeypatch.setattr(landing,'proposal_filter',reject_original_sink)
    result=rails.lay_force_rails(board,alt_layer='In2.Cu',verbose=False,
        current_by_net={'/SENSE5V_HI':3.,'+5V_MAIN':3.})
    assert isinstance(result['RS2'],dict),result
    assert result['RS2']['vias']==4
    assert any(row['accepted'] and row['nets']==['+5V_MAIN']
               for row in result['RS2']['transition_search'])
    report=landing.install(board,result['_patches']['pours'])
    assert report['ok'] and all(row['required']==2 for row in report['fields'])


def test_proposal_filter_respects_future_portal_and_pending_foreign_copper():
    board,_=fixture()
    layers=('F.Cu','In3.Cu')
    segments=[(4.,8.,12.,8.,.5,layer) for layer in layers]
    portal=dict(net='OTHER',at_mm=(8.,8.),diameter_mm=.35,
                layer_ids=[board.GetLayerID('In3.Cu')])
    assert not landing.proposal_filter(board,'SUPPLY',layers,segments,
        portals=[portal])([(8.,8.),(9.3,8.)])
    assert not landing.proposal_filter(board,'SUPPLY',layers,segments,
        pending_segments=[('OTHER',8.,4.,8.,12.,.5,'In3.Cu')])([(8.,8.),(9.3,8.)])
    assert landing.proposal_filter(board,'SUPPLY',layers,segments,
        pending_segments=[('OTHER',8.,4.,8.,12.,.5,'B.Cu')])([(8.,8.),(9.3,8.)])


@pytest.mark.parametrize('offset', [0.,23.17])
@pytest.mark.parametrize('alternate', ['In2.Cu','In3.Cu','B.Cu'])
def test_full_field_survives_native_fill_on_actual_layers(offset, alternate):
    board, patches = fixture(offset, alternate)
    report = landing.install(board, patches)
    assert report['ok'] and not report['release_authority']
    assert report['fields'][0]['required'] == 2
    assert report['fields'][0]['layers'] == ['F.Cu', alternate]


@pytest.mark.parametrize('defect', ['omitted', 'wrong_layer', 'wrong_net', 'unfilled'])
def test_drawn_outline_or_foreign_copper_cannot_mask_missing_native_land(defect, monkeypatch):
    import cec_fr
    board, patches = fixture()
    original = cec_fr.add_power_pours
    def damaged(board, rows, *, fill):
        rows = [dict(row) for row in rows]
        if defect == 'omitted': rows = rows[:1]
        if defect == 'wrong_layer': rows[-1]['layer'] = 'In2.Cu'
        if defect == 'wrong_net': rows[-1]['net'] = 'OTHER'
        return original(board, rows, fill=fill and defect != 'unfilled')
    monkeypatch.setattr(cec_fr, 'add_power_pours', damaged)
    if defect == 'unfilled':
        import cec_zone_fill
        monkeypatch.setattr(cec_zone_fill, 'fill', lambda board: None)
    with pytest.raises(landing.LandingRefused) as exc:
        landing.install(board, patches)
    assert not exc.value.evidence['ok']
    assert exc.value.evidence['fields'][0]['reason'] == 'native_fill_does_not_land_entire_field'


def test_full_lands_are_required_not_only_centers(monkeypatch):
    import cec_fr
    board, patches = fixture()
    original = cec_fr.add_power_pours
    def clipped(board, rows, *, fill):
        rows = [dict(row) for row in rows]
        rows[-1]['polygon'] = [(7.35,7.35),(9.5,7.35),(9.5,8.65),(7.35,8.65)]
        return original(board, rows, fill=fill)
    monkeypatch.setattr(cec_fr, 'add_power_pours', clipped)
    with pytest.raises(landing.LandingRefused):
        landing.install(board, patches)


@pytest.mark.parametrize('defect', ['barrel_diameter', 'barrel_drill', 'missing_primary'])
def test_required_barrel_and_connection_cannot_be_replaced_by_picture(defect):
    import cec_native_items
    board, patches = fixture()
    tracks = list(board.GetTracks())
    if defect == 'missing_primary':
        cec_native_items.discard_items(board, [t for t in tracks if t.GetClass() == 'PCB_TRACK'
            and board.GetLayerName(t.GetLayer()) == 'In3.Cu'])
    else:
        via = next(t for t in tracks if t.GetClass() == 'PCB_VIA')
        if defect == 'barrel_diameter': via.SetWidth(800_000)
        else: via.SetDrill(400_000)
    with pytest.raises(landing.LandingRefused):
        landing.install(board, patches)


def test_native_cutout_hole_is_not_filled_by_outline_projection(monkeypatch):
    import cec_fr
    board, patches = fixture()
    original = cec_fr.add_power_pours
    def cut(board, rows, *, fill):
        rows = [dict(row) for row in rows]
        rows[-1]['holes'] = [[(7.4,7.4),(8.6,7.4),(8.6,8.6),(7.4,8.6)]]
        return original(board, rows, fill=fill)
    monkeypatch.setattr(cec_fr, 'add_power_pours', cut)
    with pytest.raises(landing.LandingRefused): landing.install(board, patches)


def test_required_patch_ablation_fails_closed(monkeypatch):
    import cec_synth_pipeline as synth
    board, patches = fixture()
    monkeypatch.setenv('CEC_ABLATE_RAIL_PATCHES','1')
    with pytest.raises(landing.LandingRefused, match='required_landing_ablation'):
        synth._install_force_rail_landings(board, patches)
    assert not list(board.Zones())


@pytest.mark.parametrize('offset',[0.,23.17])
def test_landing_declaration_excludes_foreign_pad_not_only_filler_antipad(offset):
    import cec_constraints
    board,patches=fixture(offset)
    # Enough spare edge copper for a legal cut without sacrificing the
    # complete land plus its existing conservative bridge margin.
    patches=landing.patches_for('SUPPLY',patches[0]['transition']['sites'],
        ('F.Cu','In3.Cu'),diameter_mm=.9,drill_mm=.5,margin_mm=1.1)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNRELATED');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('any');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I(50_000,50_000))
    pad.SetPosition(pcbnew.VECTOR2I(round((offset+6.95)*1e6),8_850_000))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    pad.SetNetCode(board.GetNetcodeFromNetname('OTHER'));fp.Add(pad)
    report=landing.install(board,patches)
    assert report['ok'] and report['outline_reservations']['changes']
    assert cec_constraints.laid_pour_incursion_summary(board)['n_parts']==0
    assert all(not z.Outline().Collide(pad.GetEffectiveShape(pcbnew.F_Cu),0)
               for z in board.Zones() if z.IsOnLayer(pcbnew.F_Cu))


def test_future_portal_is_reserved_in_actual_outlines_after_cleanup():
    board,patches=fixture()
    patches=landing.patches_for('SUPPLY',patches[0]['transition']['sites'],
        ('F.Cu','In3.Cu'),diameter_mm=.9,drill_mm=.5,margin_mm=1.1)
    portal=dict(net='OTHER',at_mm=[7.,9.],diameter_mm=.35,
        layer_ids=list(board.GetEnabledLayers().CuStack()))
    report=landing.install(board,patches,portals=[portal])
    assert report['ok'] and report['outline_reservations']['changes']
    disk=pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(7_000_000,9_000_000),175_000)
    assert all(not z.Outline().Collide(disk,0) for z in board.Zones())


def test_foreign_keepout_that_severs_field_refuses_instead_of_reducing_vias():
    board,patches=fixture()
    portal=dict(net='OTHER',at_mm=[8.,8.],diameter_mm=.35,
        layer_ids=list(board.GetEnabledLayers().CuStack()))
    with pytest.raises(landing.LandingRefused):
        landing.install(board,patches,portals=[portal])
    assert len([t for t in board.GetTracks() if t.GetClass()=='PCB_VIA'])==2


def test_materializer_does_not_save_partially_constructed_rail(tmp_path, monkeypatch):
    import cec_force_rails
    import cec_synth_pipeline as synth
    board, patches = fixture()
    path = tmp_path/'board.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    cfg = SimpleNamespace(params={'force_rails':True}, dir=str(tmp_path))
    monkeypatch.setattr(synth,'_declared_force_rail_topology',lambda cfg: [])
    monkeypatch.setattr(cec_force_rails,'lay_force_rails',lambda *a,**k:
        {'arbitrary': {'constructed':True}, '_patches': {'pours':patches}})
    monkeypatch.setenv('CEC_ABLATE_RAIL_PATCHES','1')
    assert synth._lay_declared_force_rails(cfg,str(path)) == []
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    report = json.loads(path.with_suffix('.railreport.json').read_text())
    assert report['laid'] == 0 and report['refused']
    assert report['landing_evidence']['reason'] == 'required_landing_ablation'


@pytest.mark.parametrize('sites,layers', [([],['F.Cu','B.Cu']), ([(1,1)],['F.Cu']),
    ([(1,1),(1,1)],['F.Cu','B.Cu']), ([(float('nan'),1)],['F.Cu','B.Cu'])])
def test_invalid_field_not_silently_omitted(sites,layers):
    with pytest.raises(ValueError):
        landing.patches_for('N',sites,layers,diameter_mm=.9,drill_mm=.5,margin_mm=.65)
