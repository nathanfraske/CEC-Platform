import copy
import pytest
import cec_source_netlist_semantics as op


def tree(date='2026-10-22T21:30:00-0500'):
    return ['export',['version','E'],['design',['source','/exact/root.kicad_sch'],['date',date],['tool','KiCad10.0.5']],
        ['components',['comp',['ref','renamed'],['value','exact'],['footprint','exact:part']]],
        ['libparts',['libpart',['lib','native'],['pins',['pin',['num','45'],['type','input']]]]],
        ['libraries',['library',['uri','/exact/selected.kicad_sym']]],
        ['nets',['net',['name','source-control'],['node',['ref','renamed'],['pin','45']]]],
        ['unknown',['must-retain','opaque']]]


def test_only_generated_clock_is_volatile_source_tree_unchanged():
    first=tree();before=copy.deepcopy(first)
    assert op.metadata(first)==op.metadata(tree('2027-01-01T01:02:03+00:00'))
    assert first==before


@pytest.mark.parametrize('index',[1,3,4,5,6,7])
def test_full_other_nodes_including_pins_nets_libraries_and_unknowns_bound(index):
    first=tree();second=copy.deepcopy(first);second[index].append(['changed','no'])
    assert op.metadata(first)!=op.metadata(second)


def test_source_and_tool_not_erased():
    for index in(1,3):
        first=tree();second=tree();second[2][index][1]='forged'
        assert op.metadata(first)!=op.metadata(second)


@pytest.mark.parametrize('date',['nonsense','2026-99-22T21:30:00','2026-10-22','',True,['nested']])
def test_unexpected_date_structure_refused(date):
    with pytest.raises(ValueError):op.metadata(tree(date))


def test_duplicate_date_or_design_refused():
    first=tree();first[2].append(['date','2026-10-22T00:00:00'])
    with pytest.raises(ValueError):op.metadata(first)
    first=tree();first.append(copy.deepcopy(first[2]))
    with pytest.raises(ValueError):op.metadata(first)


def test_date_in_other_source_node_is_not_volatile():
    first=tree();second=tree();first.append(['date','first']);second.append(['date','second'])
    assert op.metadata(first)!=op.metadata(second)


def test_raw_evidence_retained_semantic_required_to_compare():
    first=dict(exporter=dict(netlist_sha256='a'*64,exporter_sha256='b'*64,exporter='/bin/exact',**op.metadata(tree())))
    second=copy.deepcopy(first);second['exporter']['netlist_sha256']='c'*64
    assert op.replay_identity(first)==op.replay_identity(second)
    assert first['exporter']['netlist_sha256']=='a'*64
    second['exporter']['netlist_semantic_sha256']='d'*64
    assert op.replay_identity(first)!=op.replay_identity(second)
    second['exporter'].pop('netlist_semantic_policy')
    with pytest.raises(ValueError):op.replay_identity(second)
