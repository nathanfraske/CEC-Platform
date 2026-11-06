"""Read-only one-shot profile using the unchanged ordered phase watchdog."""
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
WORK=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def worker():
    import functools
    import faulthandler
    import pcbnew
    import cec_cell_escape_replan as escape
    import cec_source_ground_leaf as canonical
    import cec_source_linear_power_stage as stage
    import cec_programming_resistor_placement as programming
    import cec_source_timing_capacitor as timing
    import cec_wired_aggregate_capacitor as wired
    import cec_wired_aggregate_ground_leaf as wired_ground
    import cec_measurement_leaf as leaf
    import cec_projected_ground_contact as projected
    import cec_retained_bypass_contact_frame as retained
    import cec_source_supply_endpoint_cut as supply
    import cec_cell_row_rebuild as row
    import cec_force_current as force
    import cec_additional_aggregate_macro as aggregate
    start=time.monotonic();stack=[];counts={}
    def wrap(module,name):
        original=getattr(module,name);key=module.__name__+'.'+name
        @functools.wraps(original)
        def observed(*a,**kw):
            counts[key]=counts.get(key,0)+1
            record=dict(name=key,n=counts[key],start=time.monotonic(),children=0.)
            detail=str(a[1])if len(a)>1 and isinstance(a[1],str)else None
            stack.append(record)
            print('PROFILE='+json.dumps(dict(event='start',name=key,n=record['n'],
                elapsed=record['start']-start,detail=detail,active=[r['name']for r in stack])),flush=True)
            try:return original(*a,**kw)
            finally:
                seconds=time.monotonic()-record['start'];stack.pop()
                if stack:stack[-1]['children']+=seconds
                print('PROFILE='+json.dumps(dict(event='end',name=key,n=record['n'],
                    elapsed=time.monotonic()-start,seconds=seconds,
                    exclusive_s=seconds-record['children'])),flush=True)
        setattr(module,name,observed)
    for module,names in[(pcbnew,['LoadBoard']),(row,['_source_binding']),
        (force,['_code_identity','_family']),
        (canonical,['_hierarchy','_export','_export_fresh','_export_observation_live']),
        (stage,['collect','_collect','_observation_live']),
        (programming,['plan']),(timing,['plan']),
        (wired,['inspect']),(wired_ground,['plan']),(aggregate,['collect']),
        (projected,['plan']),(retained,['plan']),
        (supply,['output_bypass_owner']),
        (leaf,['plan_bypass_ground','plan_rated_bypass_supply','plan_ground','plan_rated_supply']),
        (escape,['_prepare_source'])]:
        for name in names:wrap(module,name)
    faulthandler.dump_traceback_later(9.,repeat=False)
    try:load('exact_compile_scout',WORK/'scout.py').worker()
    finally:faulthandler.cancel_dump_traceback_later()


def main():
    target=WORK/'profile-scoped-v3.json'
    assert not target.exists(),'fresh_profile_required'
    runner=load('ordered_native_watchdog',ROOT/'experiments/busbars/coherent-mux-20261106/scout.py')
    code,output,reason=runner.bounded_compile([sys.executable,str(Path(__file__).resolve()),'--worker'])
    events=[json.loads(s.split('=',1)[1])for s in output.splitlines()if s.startswith('PROFILE=')]
    phases=[json.loads(s.split('=',1)[1])for s in output.splitlines()if s.startswith('CEC_PHASE=')]
    totals={}
    for event in events:
        row=totals.setdefault(event['name'],dict(started=0,finished=0,seconds=0.,exclusive_s=0.))
        if event['event']=='start':row['started']+=1
        else:
            row['finished']+=1;row['seconds']+=event['seconds'];row['exclusive_s']+=event['exclusive_s']
    report=dict(exit_code=code,reason=reason,phases=phases,totals=totals,
        events=events,diagnostic_output=output,board_saved=False,accepted=False)
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(exit_code=code,reason=reason,phases=phases,
        totals=totals,last_events=events[-12:]),indent=2))


if __name__=='__main__':worker()if '--worker'in sys.argv else main()
