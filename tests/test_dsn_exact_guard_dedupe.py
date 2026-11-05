import pytest
import cec_dsn_exact_guard_dedupe as d

def test_exact_nodes_only_preserves_all_other_literal_bytes():
    guard='(via_keepout "named" (polygon "BACK layer" 0 0 0 1 0 1 1)(window(polygon "BACK layer" 0 .2 .2 .3 .2 .3 .3))(rule(clearance .5)))'
    raw='(pcb p(parser(string_quote "))(structure'+guard+guard+')(network(net X(pins J1-1 J2-1))))'
    after,r=d.deduplicate_text(raw)
    assert r['removed_nodes']==1 and after==raw.replace(guard+guard,guard)
    assert '(network(net X(pins J1-1 J2-1)))'in after

@pytest.mark.parametrize('replacement',[
 ('via_keepout','keepout'),('named','other'),('BACK layer','arbitrary_inner'),
 ('clearance .5','clearance .6'),('1 0 1 1','0 1 -1 1'),
 ('(rule(clearance .5))','(rule(clearance .5))(net FOREIGN)'),
 (' .3 .3',' .4 .3'),
])
def test_changed_type_name_layer_rule_net_rotation_or_hole_is_never_duplicate(replacement):
    guard='(via_keepout named(polygon "BACK layer" 0 0 0 1 0 1 1)(window(polygon "BACK layer" 0 .2 .2 .3 .2 .3 .3))(rule(clearance .5)))'
    other=guard.replace(*replacement);assert other!=guard
    text='(pcb p(structure'+guard+other+'))';after,r=d.deduplicate_text(text)
    assert after==text and r['removed_nodes']==0

@pytest.mark.parametrize('raw',['(pcb p(structure)(structure))','(pcb p(structure)','(pcb p(network))'])
def test_unknown_or_malformed_structure_refuses(raw):
    with pytest.raises(ValueError):d.deduplicate_text(raw)
