"""Loaded-native equivalence and bounded-witness cost for local ribbon refusal."""
import copy
import inspect
from unittest.mock import patch

import pytest
import pcbnew
import cec_fr
import cec_pair_ribbon
import cec_precision_route as route


def legacy_stub():
    """Isolated negative control: restore exhaustive per-ribbon diagnostics."""
    source = inspect.getsource(route._route_paired_stub)
    old = 'if len(ribbon_rejections) >= ribbon_witness_limit and ('
    assert source.count(old) == 1
    source = source.replace(old, 'if False and (')
    source = source.replace('if len(ribbon_rejections) < ribbon_witness_limit:', 'if True:')
    source = source.replace('"rejected": ribbon_rejections,', '"rejected": ribbon_rejections[:4],')
    namespace = {}
    exec(compile(source, '<legacy-ribbon-evidence>', 'exec'), route.__dict__, namespace)
    return namespace['_route_paired_stub']


def fixture(tmp_path, kind, quarter, layer):
    board = pcbnew.CreateEmptyBoard(); board.SetCopperLayerCount(6)
    pair = dict(name='renamed', kind='can', p='lane_A', n='lane_B', width=.2, gap=.25)
    for net in ('lane_A', 'lane_B', 'foreign'):
        board.Add(pcbnew.NETINFO_ITEM(board, net))
    def pose(point):
        x, y = point[0]-20, point[1]-20
        for _ in range(quarter): x, y = -y, x
        return x+35, y+31
    def vec(point): return pcbnew.VECTOR2I_MM(*pose(point))
    corners = ((0,0),(40,0),(40,40),(0,40),(0,0))
    for a, b in zip(corners, corners[1:]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetStart(vec(a));edge.SetEnd(vec(b));board.Add(edge)
    endpoints = tuple(map(pose, ((10,20),(18,20),(10,20.45),(18,20.45))))
    layers=pcbnew.LSET();layers.AddLayer(board.GetLayerID(layer))
    avoid = []
    if kind in ('foreign-track', 'partner-copper'):
        item = pcbnew.PCB_TRACK(board)
        item.SetNet(board.FindNet('foreign' if kind=='foreign-track' else pair['n']))
        item.SetLayer(board.GetLayerID(layer));item.SetStart(vec((14,18)));item.SetEnd(vec((14,22)))
        item.SetWidth(pcbnew.FromMM(.4));board.Add(item)
    if kind in ('foreign-pad', 'partner-pad'):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('9');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
        pad.SetPosition(vec((14,20)));pad.SetLayerSet(layers)
        pad.SetNet(board.FindNet('foreign' if kind=='foreign-pad' else pair['n']));fp.Add(pad)
    if kind=='reservation':
        pts=list(map(pose,((13,18),(15,22))))
        avoid=[(min(p[0] for p in pts),min(p[1] for p in pts),
                max(p[0] for p in pts),max(p[1] for p in pts),'retained',layer)]
    if kind=='edge':
        endpoints=tuple(map(pose,((-1,20),(18,20),(-1,20.45),(18,20.45))))
    # Unused net declarations disappear on KiCad save; real endpoint lands
    # retain both nets in the loaded-native fixture.
    for index,point in enumerate(endpoints):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('PORT_%s'%index);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.1,.1))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*point));pad.SetLayerSet(layers)
        pad.SetNet(board.FindNet(pair['p'] if index<2 else pair['n']));fp.Add(pad)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    ps,pe,ns,ne=endpoints
    p,n=[ps,pe],[ns,ne]
    coupling=route._polyline_coupling_coverage(p,n,pair['width'],pair['gap'])
    row=dict(p=p,n=n,coupling=coupling,coupling_contract=route._pair_coupling_contract(
        pair,coupling,{pair['p']:route._dist(ps,pe),pair['n']:route._dist(ns,ne)}))
    return path,pair,endpoints,avoid,[copy.deepcopy(row) for _ in range(12)]


@pytest.mark.parametrize('kind',['foreign-track','foreign-pad','partner-pad','partner-copper','reservation','edge'])
@pytest.mark.parametrize('quarter,layer',[(0,'F.Cu'),(1,'B.Cu'),(2,'F.Cu'),(3,'B.Cu')])
def test_native_refusal_and_first_witnesses_match_exhaustive_control(tmp_path,kind,quarter,layer):
    source,pair,endpoints,avoid,rows=fixture(tmp_path,kind,quarter,layer)
    original_bytes=source.read_bytes()
    results=[]
    for solve in (legacy_stub(),route._route_paired_stub):
        board=pcbnew.LoadBoard(str(source));original_ids={t.m_Uuid.AsString() for t in board.GetTracks()}
        with patch.object(route,'_short_pair_ribbon_candidates',return_value=rows), \
             patch.object(cec_pair_ribbon,'candidates',return_value=[]), \
             patch.object(route,'_joint_endpoint_escape',return_value=None), \
             patch.object(cec_fr,'_snapshot_foreign_blockers',wraps=cec_fr._snapshot_foreign_blockers) as identify:
            report=solve(board,pair,endpoints,layer=layer,avoid=avoid)
        assert report.get('refused')
        assert {t.m_Uuid.AsString() for t in board.GetTracks()}==original_ids
        results.append((report,identify.call_count))
    old,new=[row[0] for row in results]
    assert new['admission']['paired_ribbon'].pop('physical_prefilter_refusals')==8
    assert old['admission']['paired_ribbon'].pop('physical_prefilter_refusals')==0
    assert old==new
    if kind == 'reservation':
        failures = [failure for row in new['admission']['paired_ribbon']['rejected']
                    for member in ('p', 'n') for failure in row.get(member+'_failures', ())]
        assert failures and all(failure['reservation'] is False for failure in failures)
    if kind in ('foreign-track','foreign-pad'):
        assert results[1][1]<results[0][1]/2
    assert source.read_bytes()==original_bytes


@pytest.mark.parametrize('quarter,layer',[(0,'F.Cu'),(1,'B.Cu'),(2,'F.Cu'),(3,'B.Cu')])
def test_real_detour_survives_and_keeps_exact_copper(tmp_path,quarter,layer):
    source,pair,endpoints,avoid,rows=fixture(tmp_path,'reservation',quarter,layer)
    # A detour comes from the real bounded pair constructor, not a mock
    # admission/clearance result.
    board=pcbnew.LoadBoard(str(source))
    with patch.object(route,'_short_pair_ribbon_candidates',return_value=[]), \
         patch.object(cec_pair_ribbon,'candidates',return_value=[]):
        real=route._route_paired_stub(board,pair,endpoints,layer=layer,avoid=avoid)
    assert not real.get('refused'),real
    # Compare ordinary full solver on the same native reservation. Existing
    # suites cover direct fast paths and the correlated constructor too.
    results=[]
    for index,solve in enumerate((legacy_stub(),route._route_paired_stub)):
        native=pcbnew.LoadBoard(str(source))
        result=solve(native,pair,endpoints,layer=layer,avoid=avoid)
        assert not result.get('refused'),result
        output=tmp_path/('%s.kicad_pcb'%index);pcbnew.SaveBoard(str(output),native,True)
        results.append((result,cec_fr.copper_geometry_signature(str(output),[pair['p'],pair['n']])))
    assert results[0]==results[1]


def test_a_valid_ribbon_after_the_prefilter_is_not_skipped(tmp_path):
    source,pair,endpoints,avoid,rows=fixture(tmp_path,'clear',0,'F.Cu')
    valid=copy.deepcopy(rows[0])
    assert valid['coupling_contract']['ok']
    # Keep real native board-edge checks, followed by a genuinely valid
    # nominal-pitch ribbon. No physical predicate or admission is mocked.
    rejected=copy.deepcopy(rows)
    for row in rejected:
        for member in ('p','n'):
            a,b=row[member]
            row[member]=[a,(-10,a[1]),b]
    results=[]
    for index,solve in enumerate((legacy_stub(),route._route_paired_stub)):
        board=pcbnew.LoadBoard(str(source))
        with patch.object(route,'_short_pair_ribbon_candidates',return_value=rejected+[valid]), \
             patch.object(cec_pair_ribbon,'candidates',side_effect=AssertionError('extra domain')), \
             patch.object(route,'_joint_endpoint_escape',side_effect=AssertionError('extra fallback')):
            result=solve(board,pair,endpoints,avoid=avoid)
        assert not result.get('refused'),result
        assert result['local_search']['paired_ribbon']['accepted']
        assert sum(result['local_search']['paired_ribbon_evaluated_by_geometry'].values())==13
        target=tmp_path/('late-%s.kicad_pcb'%index);pcbnew.SaveBoard(str(target),board,True)
        results.append((result,cec_fr.copper_geometry_signature(str(target),[pair['p'],pair['n']])))
    assert results[0]==results[1]
