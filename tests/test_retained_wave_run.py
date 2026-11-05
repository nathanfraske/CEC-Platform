"""The normal event-driven launch path must retain short-run identity."""
import pytest
from cec_retained_wave_run import command


def test_retention_limits_and_literal_argv_are_mandatory():
    args=command('wave.service','/workspace','/workspace/job.log',
                 ['/usr/bin/python3','script with spaces.py','--value=a;b'])
    assert args.count('--property=RemainAfterExit=yes')==1
    assert '--property=RuntimeMaxSec=540' in args
    assert '--property=MemoryMax=8G' in args
    assert '--property=TimeoutStopSec=10' in args
    assert args[-4:]==['--','/usr/bin/python3','script with spaces.py','--value=a;b']


@pytest.mark.parametrize('options',[dict(runtime_s=0),dict(runtime_s=43201),
    dict(memory_gib=True),dict(memory_gib=0),dict(memory_gib=129)])
def test_resource_bounds(options):
    with pytest.raises(ValueError):command('wave.service','/workspace','/log',['true'],**options)


@pytest.mark.parametrize('unit',['wave','wave.service;false','../wave.service'])
def test_exact_unit_only(unit):
    with pytest.raises(ValueError):command(unit,'/workspace','/log',['true'])
