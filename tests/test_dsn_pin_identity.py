"""Network-terminal ownership is scoped, exact and native-alias aware."""
import pytest
import pcbnew
import cec_fr as fr


def fixture(count=3, *, collision=False):
    b = pcbnew.BOARD()
    info = pcbnew.NETINFO_ITEM(b, 'OTHER_NET'); b.Add(info)
    fp = pcbnew.FOOTPRINT(b); fp.SetReference('J_TEST'); b.Add(fp)
    for index in range(count):
        p = pcbnew.PAD(fp); p.SetNumber('S1'); p.SetNet(info)
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH); p.SetLayerSet(pcbnew.PAD.PTHMask())
        fp.Add(p)
    if collision:
        p = pcbnew.PAD(fp); p.SetNumber('S1@1'); p.SetNet(info); fp.Add(p)
    return b


def dsn(pins, *, other=''):
    return ('(pcb "private"\n (parser\n  (string_quote ")\n )\n'
            ' (library (image "J_TEST-S1" (pin S1 (circle F.Cu 1))))\n'
            ' (network (net "OTHER ) (quoted" (pins '+pins+')))\n'
            +other+'\n)\n')


def write(tmp_path, body):
    path = tmp_path/'candidate.dsn'
    path.write_text(body)
    return path


def network(path):
    return [record[0] for record in fr._dsn_network_pin_records(path.read_text())]


def test_exact_atoms_do_not_leave_orphan_alias_suffixes_or_remove_prefix_neighbors(tmp_path):
    path = write(tmp_path, dsn('J_TEST-S1 J_TEST-S1@1 J_TEST-S1@2 J_TEST-S10 OTHER-1'))
    assert fr._dsn_exclude_pins(str(path), {'J_TEST-S1'}, board=fixture()) == 3
    assert network(path) == ['J_TEST-S10', 'OTHER-1']
    assert '(image "J_TEST-S1"' in path.read_text()
    assert '(pin S1 ' in path.read_text()
    assert fr.validate_dsn_structure(str(path))['ok']


def test_opaque_at_names_are_not_aliases_without_native_inventory(tmp_path):
    path = write(tmp_path, dsn('J_TEST-S1 J_TEST-S1@1 J_TEST-S10'))
    assert fr._dsn_exclude_pins(str(path), {'J_TEST-S1'}) == 1
    assert network(path) == ['J_TEST-S1@1', 'J_TEST-S10']


def test_quoted_pin_removed_as_one_atom_but_library_and_wiring_untouched(tmp_path):
    other = '(wiring (fromto "J odd-1" OTHER-1))'
    path = write(tmp_path, dsn('"J odd-1" "J odd-10" OTHER-1', other=other))
    assert fr._dsn_exclude_pins(str(path), {'J odd-1'}) == 1
    assert network(path) == ['J odd-10', 'OTHER-1']
    assert other in path.read_text()
    assert fr.validate_dsn_structure(str(path))['ok']


@pytest.mark.parametrize('tokens', ['J_TEST-S1 J_TEST-S1@1', 'J_TEST-S1@1 J_TEST-S1@2'])
def test_incomplete_native_alias_inventory_refuses_without_writing(tmp_path, tokens):
    path = write(tmp_path, dsn(tokens)); before = path.read_bytes()
    with pytest.raises(ValueError, match='incomplete native DSN alias'):
        fr._dsn_exclude_pins(str(path), {'J_TEST-S1'}, board=fixture())
    assert path.read_bytes() == before


def test_real_pad_name_alias_collision_refuses_without_writing(tmp_path):
    path = write(tmp_path, dsn('J_TEST-S1 J_TEST-S1@1 J_TEST-S1@2'))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='collides with DSN alias'):
        fr._dsn_exclude_pins(str(path), {'J_TEST-S1'}, board=fixture(collision=True))
    assert path.read_bytes() == before


def test_same_ref_on_distinct_footprints_cannot_claim_duplicate_pad_aliases(tmp_path):
    b = fixture(count=1)
    fp = pcbnew.FOOTPRINT(b); fp.SetReference('J_TEST'); b.Add(fp)
    p = pcbnew.PAD(fp); p.SetNumber('S1'); p.SetNetCode(1); fp.Add(p)
    path = write(tmp_path, dsn('J_TEST-S1 J_TEST-S1@1'))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='ambiguous native DSN terminal'):
        fr._dsn_exclude_pins(str(path), {'J_TEST-S1'}, board=b)
    assert path.read_bytes() == before


@pytest.mark.parametrize('tail', ['(', '"unterminated', ')'])
def test_lexical_failure_cannot_produce_a_partial_dsn_write(tmp_path, tail):
    path = write(tmp_path, dsn('J_TEST-S1')+tail); before = path.read_bytes()
    with pytest.raises(ValueError):
        fr._dsn_exclude_pins(str(path), {'J_TEST-S1'})
    assert path.read_bytes() == before
