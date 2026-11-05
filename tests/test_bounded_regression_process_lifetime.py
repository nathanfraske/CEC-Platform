"""Resource ownership unit tests, not a board/whole-suite pass."""
from pathlib import Path
import os

import pytest

import root_bounded_regression_replay_20261028 as runner


def test_split_preserves_each_module_without_crediting_an_interrupted_batch():
    original=tuple('test_'+str(i)for i in range(9))
    left,right=runner.split_batch(original)
    assert left+right==original and left and right and not set(left)&set(right)
    with pytest.raises(ValueError):runner.split_batch(('test_single',))


def test_process_ownership_requires_root_start_identity_and_follows_only_descendants():
    process={1:dict(ppid=0,start=10,rss=1),2:dict(ppid=1,start=20,rss=2),
        3:dict(ppid=2,start=30,rss=4),4:dict(ppid=0,start=40,rss=8)}
    assert set(runner.owned_processes(1,10,process))=={1,2,3}
    assert not runner.owned_processes(1,11,process)
    assert not runner.owned_processes(99,10,process)


def test_live_proc_reader_identifies_own_start_and_positive_memory():
    inventory=runner.process_inventory()
    assert os.getpid()in inventory and inventory[os.getpid()]['start']>0
    assert inventory[os.getpid()]['rss']>0
    assert runner.available_memory()>0


def test_inventory_xml_never_credits_pass_status(tmp_path):
    xml=tmp_path/'prior.xml'
    xml.write_text('<testsuites><testsuite><testcase classname="tests.test_alpha"/>'
        '<testcase classname="tests.test_beta"><failure/></testcase></testsuite></testsuites>')
    assert runner.module_names(xml)=={'test_alpha','test_beta'}


def test_explicit_fixture_inputs_are_absolute_unique_existing_and_boundable(tmp_path):
    fixture=tmp_path/'current-native-board.kicad_pcb';fixture.write_bytes(b'fixture-only')
    assert runner.fixture_inputs([fixture])=={fixture}
    assert runner.fixture_inputs([])==set()
    for invalid in ([fixture,fixture],[tmp_path/'missing'],[Path('relative.kicad_pcb')]):
        with pytest.raises(ValueError):runner.fixture_inputs(invalid)
    alias=tmp_path/'alias';alias.symlink_to(fixture)
    with pytest.raises(ValueError):runner.fixture_inputs([alias])
