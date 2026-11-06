import copy
import pytest

import cec_bypass_pose_receiving as receiver
import cec_additive_route_receiving as syntax


@pytest.fixture
def source(tmp_path):
    path=tmp_path/'board.kicad_pcb'
    path.write_text('''(kicad_pcb (version 20260101)
  (footprint "X" (at 1 2) (uuid "cap"))
  (gr_text "R" (at 3 4) (uuid "label"))
  (segment (start 1 2) (end 3 4) (uuid "track"))
)''')
    return path


def test_only_native_selected_package_replaces_literal_source(source):
    replay=copy.deepcopy(syntax._nodes(source)[1])
    replay['cap'][2]=['at','2','2']
    replay['label'][2].append('0')
    text=receiver._literal_pose_frame(source,replay,{'cap'})
    assert '(at 3 4)' in text
    assert '(at 3 4 0)' not in text
    assert '(at 2 2)' in text
    assert '(segment (start 1 2) (end 3 4) (uuid "track"))' in text


@pytest.mark.parametrize('selected',[set(),{'missing'},{'label'},{'track'}])
def test_only_complete_explicit_footprint_selection(source,selected):
    with pytest.raises(ValueError,match='exact_native_selected_footprint'):
        receiver._literal_pose_frame(source,syntax._nodes(source)[1],selected)


def test_native_replay_cannot_lose_source_objects(source):
    replay=syntax._nodes(source)[1];del replay['track']
    with pytest.raises(ValueError,match='exact_native_selected_footprint'):
        receiver._literal_pose_frame(source,replay,{'cap'})
