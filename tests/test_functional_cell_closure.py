import copy
import pytest
import cec_functional_cell_closure as closure


class Pad:
    def __init__(self, pin='PWR', net='rail', code=1, copper=True):
        self.pin, self.net, self.code, self.copper = pin, net, code, copper
    def GetNumber(self): return self.pin
    def GetNetname(self): return self.net
    def GetNetCode(self): return self.code
    def IsOnCopperLayer(self): return self.copper


class Footprint:
    def __init__(self, ref, pads=None, dnp=False):
        self.ref, self.pads, self.dnp = ref, pads or [Pad()], dnp
    def GetReference(self): return self.ref
    def IsDNP(self): return self.dnp
    def Pads(self): return self.pads


class Board:
    def __init__(self, fps=None):
        self.fps = fps or [Footprint('OWNER'), Footprint('SUPPORT')]
    def GetFootprints(self): return self.fps


def binding(support='SUPPORT', owner='OWNER'):
    return dict(support_ref=support, support_pin='PWR', owner_ref=owner, owner_pin='PWR', net='rail')


def cells():
    return {'block': dict(refs={0: ['OWNER'], 1: ['OTHER_BOARD']}, bounds=(0, 0, 1, 1))}


def test_closes_exact_binding_without_mutating_caller_or_other_context():
    board, source, bindings = Board(), cells(), [binding()]
    original, original_bindings = copy.deepcopy(source), copy.deepcopy(bindings)
    result = closure.close(board, source, bindings, context=0)
    assert result['cells']['block']['refs'] == {0: ['OWNER', 'SUPPORT'], 1: ['OTHER_BOARD']}
    assert source == original and bindings == original_bindings
    assert board.fps[1].ref == 'SUPPORT'
    assert not result['release_authority'] and not result['copper_motion_admitted']


def test_existing_same_cell_is_not_duplicated():
    source = cells(); source['block']['refs'][0].append('SUPPORT')
    result = closure.close(Board(), source, [binding()], context=0)
    assert result['additions'] == []


def test_dependency_order_is_resolved_without_proximity_guess():
    board = Board([Footprint(ref) for ref in ('OWNER', 'SUPPORT', 'CHAIN')])
    result = closure.close(board, cells(), [binding('CHAIN', 'SUPPORT'), binding()], context=0)
    assert result['cells']['block']['refs'][0] == ['OWNER', 'SUPPORT', 'CHAIN']


@pytest.mark.parametrize('bad', [
    [binding(), binding()], [binding('OWNER', 'OWNER')],
    [{**binding(), 'net': 'foreign'}], [{**binding(), 'owner_pin': 'missing'}],
    [{**binding(), 'support_pin': 'missing'}], [{**binding(), 'support_ref': 'missing'}],
    [{**binding(), 'net': ''}], [{**binding(), 'assumed_owner': True}],
])
def test_invalid_binding_refuses_without_partial_mutation(bad):
    source = cells(); original = copy.deepcopy(source)
    with pytest.raises(ValueError): closure.close(Board(), source, bad, context=0)
    assert source == original


@pytest.mark.parametrize('pad', [Pad(net='foreign'), Pad(code=0), Pad(copper=False)])
def test_native_support_pin_must_actually_be_on_declared_net(pad):
    with pytest.raises(ValueError):
        closure.close(Board([Footprint('OWNER'), Footprint('SUPPORT', [pad])]), cells(), [binding()], context=0)


def test_dnp_refuses():
    with pytest.raises(ValueError):
        closure.close(Board([Footprint('OWNER'), Footprint('SUPPORT', dnp=True)]), cells(), [binding()], context=0)


def test_conflicting_existing_cell_refuses():
    source = cells(); source['separate'] = dict(refs={0: ['SUPPORT']})
    with pytest.raises(ValueError, match='already_in_other_cell'):
        closure.close(Board(), source, [binding()], context=0)


def test_cycle_with_no_declared_owner_refuses():
    board = Board([Footprint(ref) for ref in ('OWNER', 'SUPPORT', 'CHAIN')])
    with pytest.raises(ValueError, match='binding_cycle'):
        closure.close(board, cells(), [binding('CHAIN', 'SUPPORT'), binding('SUPPORT', 'CHAIN')], context=0)


def test_seeded_cell_does_not_hide_a_binding_cycle():
    with pytest.raises(ValueError, match='binding_cycle'):
        closure.close(Board(), cells(), [binding(), binding('OWNER', 'SUPPORT')], context=0)


def test_unhashable_cell_ref_refuses_as_an_input_error():
    source = cells(); source['block']['refs'][0].append([])
    with pytest.raises(ValueError): closure.close(Board(), source, [binding()], context=0)


@pytest.mark.parametrize('context,budget', [(True, 2), (0, 0), (0, float('inf')), (0, 11)])
def test_bounded_scope_required(context, budget):
    with pytest.raises(ValueError): closure.close(Board(), cells(), [binding()], context=context, timeout_s=budget)


def test_duplicate_native_reference_refuses():
    with pytest.raises(ValueError, match='ambiguous_native'):
        closure.close(Board([Footprint('OWNER'), Footprint('OWNER')]), cells(), [binding()], context=0)
