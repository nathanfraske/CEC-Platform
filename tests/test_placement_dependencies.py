"""Electrical closure and frozen copper belong inside the bounded search."""
import copy
from types import SimpleNamespace
import pytest
import cec_placement_dependencies as dependencies
import cec_synth_pipeline as synth


def fixture():
    candidate = SimpleNamespace(P=dict(primary=(2., 5., 0.), neighbor=(6., 5., 0.),
        mate=(6., 9., 90.), bypass=(8., 9., 180.)), W=20., H=20., back_refs=())
    def bbox(ref, pose):
        x, y, _ = pose
        return x-.4, x+.4, y-.4, y+.4
    return candidate, bbox


@pytest.mark.parametrize('reverse', [False, True])
def test_transitive_collateral_group_moves_all_owners_and_bypasses(reverse):
    c, box = fixture(); original = copy.deepcopy(c.P)
    groups = [('neighbor', 'mate'), ('mate', 'bypass')]
    if reverse: groups.reverse()
    results = synth._placement_bounded_macro_legalizations(c, {'primary':(6.,5.,0.)},
        set(), {ref: object() for ref in c.P}, {'bypass':'mate'}, {'mate':['bypass']},
        lambda ref: ref in {'neighbor','mate'}, bbox_fn=box, exact_bbox_overlap=True,
        dependency_context=dict(ok=True,groups=groups), max_steps=1)
    assert results
    for poses, _, _ in results:
        delta = tuple(poses['neighbor'][i]-c.P['neighbor'][i] for i in (0,1))
        for ref in ('neighbor','mate','bypass'):
            assert tuple(poses[ref][i]-c.P[ref][i] for i in (0,1)) == pytest.approx(delta)
            assert poses[ref][2] == c.P[ref][2]
        assert not synth._placement_bbox_overlap_pairs(dict(c.P,**poses),box)
    assert c.P == original


@pytest.mark.parametrize('fault', ['fixed_mate','fixed_bypass','missing','unknown_context','primary_member'])
def test_dependency_cannot_be_silently_dropped_or_override_primary(fault):
    c, box = fixture()
    context = dict(ok=True, groups=[('neighbor','mate')])
    fixed = set(); primary = {'primary':(6.,5.,0.)}
    if fault == 'fixed_mate': fixed.add('mate')
    if fault == 'fixed_bypass': fixed.add('bypass')
    if fault == 'missing': context['groups'][0] += ('absent',)
    if fault == 'unknown_context': context['ok'] = False
    if fault == 'primary_member': primary['mate'] = c.P['mate']
    assert synth._placement_bounded_macro_legalizations(c, primary, set(),
        {ref:object() for ref in c.P}, {'bypass':'mate'}, {'mate':['bypass']},
        lambda ref: True, bbox_fn=box, exact_bbox_overlap=True,
        dependency_context=context, immovable_refs=fixed, max_steps=2) == []


def test_fixed_primary_is_rejected_before_eviction():
    c,box=fixture();trace={}
    assert synth._placement_bounded_macro_legalizations(c,{'primary':(6.,5.,0.)},set(),
        {ref:object() for ref in c.P},{},{},lambda ref:ref!='primary',
        bbox_fn=box,exact_bbox_overlap=True,immovable_refs={'primary'},trace=trace)==[]
    assert trace['reason']=='fixed_primary_move'


@pytest.mark.parametrize('back', [False, True])
def test_commit_reservation_has_no_implicit_same_net_or_face_exemption(back):
    c, box = fixture(); c.back_refs = {'primary'} if back else set()
    row = dict(net='rail',x0=5.,y0=4.,x1=7.,y1=6.,all_layers=True,
               exempt_refs=[],clearance_mm=.3)
    poses = {'primary':(6.,5.,0.)}
    hits = synth._placement_reserved_copper_collisions(c,poses,{'primary':object()},
        [row],{'primary':{'rail'}},bbox_fn=box,clearance_mm=0.)
    assert hits and hits[0]['box'] == pytest.approx((4.7,7.3,3.7,6.3))
    row['exempt_refs'] = ['primary']
    assert not synth._placement_reserved_copper_collisions(c,poses,{'primary':object()},
        [row],{},bbox_fn=box)


def test_prelegalization_repairs_copper_only_conflict(monkeypatch):
    import cec_pcb
    c, box = fixture()
    c.P = {'primary':c.P['primary']}
    monkeypatch.setattr(cec_pcb,'courtyard_bbox',lambda comp,x,y,a,**kw:box('',(x,y,a)))
    monkeypatch.setattr(synth,'_overlap_pairs',lambda *a,**kw:set())
    region = dict(net='rail',x0=5.,y0=4.,x1=7.,y1=6.,all_layers=True,
                  exempt_refs=[],clearance_mm=.3)
    move = dict(ref='primary',kind='example',placements={'primary':(6.,5.,0.)})
    result = synth._route_feedback_legalized_moves(c,[move],{'primary':'package'}, {},
        reserved_regions=[region],dependency_context=dict(ok=True,groups=[]))
    assert result
    for row in result:
        assert not synth._placement_reserved_copper_collisions(c,row['placements'],
            {'primary':'package'},[region],{},bbox_fn=box)


def test_pad_only_conflict_uses_pad_tangent_not_large_body(monkeypatch):
    import cec_pcb
    c, box = fixture();c.P={'primary':c.P['primary']}
    monkeypatch.setattr(cec_pcb,'courtyard_bbox',lambda comp,x,y,a,**kw:(x-2,x+2,y-2,y+2))
    monkeypatch.setattr(synth,'_overlap_pairs',lambda *a,**kw:set())
    def pads(poses):
        x,y,_=poses['primary']
        if 5.8<x<6.2 and 4.8<y<5.2:
            return [dict(ref='primary',net='power',region_index=-1,overlap_mm2=.04,
                         box=(5.9,6.1,4.9,5.1),member_box=(x-.1,x+.1,y-.1,y+.1))]
        return []
    result=synth._route_feedback_legalized_moves(c,
        [dict(ref='primary',kind='example',placements={'primary':(6.,5.,0.)})],
        {'primary':'package'},{},pad_collision_fn=pads)
    assert result
    x,y,_=result[0]['placements']['primary']
    assert abs(x-6.)+abs(y-5.) == pytest.approx(.25)
    assert not pads(result[0]['placements'])


@pytest.mark.parametrize('rotation', [0.,90.,180.,270.])
@pytest.mark.parametrize('back', [False, True])
def test_native_detection_binding_includes_currently_passing_cells(tmp_path,rotation,back):
    import pcbnew
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board,'/example/DETAMP'); board.Add(net)
    for ref,value,x in (('arbitrary-one','INA181',5.),('arbitrary-two','TLV7011',7.)):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
        board.Add(fp); fp.SetPosition(pcbnew.VECTOR2I_MM(x,5))
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(fp.GetPosition()); pad.SetNet(net); fp.Add(pad)
        fp.SetOrientationDegrees(rotation)
        if back: fp.Flip(fp.GetPosition(),False)
    path = tmp_path/'board.kicad_pcb'; pcbnew.SaveBoard(str(path),board,True)
    before = path.read_bytes()
    evidence = synth._oracle_comparator_adjacency(str(path))
    assert evidence['ok'] and evidence['details'][0]['distance_mm'] == 2.
    context = dependencies.from_board(path,craft={'detection_cell':evidence},
                                     follower_groups={'arbitrary-one':['ceramic']})
    assert context['ok'] and context['groups'] == [('arbitrary-one','arbitrary-two','ceramic')]
    assert path.read_bytes() == before


def test_unreadable_native_source_fails_closed(tmp_path):
    assert not dependencies.from_board(tmp_path/'absent.kicad_pcb')['ok']


def test_transitive_ownership_is_order_independent():
    a = dependencies.cells({'cap':'amp'}, {'amp':['cap']}, [('amp','cmp'),('cmp','inline')])
    b = dependencies.cells({'cap':'amp'}, {'amp':['cap']}, [('inline','cmp'),('cmp','amp')])
    assert a == b and set(next(iter(a[1].values()))) == {'cap','amp','cmp','inline'}
