"""Fresh guard check, retaining the historical unguarded receipt unchanged."""
import sys,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path('/home/codex/src/CEC-Platform');sys.path.insert(0,str(ROOT/'scripts'))
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_current_topology as topology
import cec_component_jumper_metadata as metadata,cec_constraints as constraints
import cec_synth_pipeline as synth
WORK=Path(__file__).parent;path=WORK/'actual_provisional_footprint/board.kicad_pcb'
history=WORK/'transport-receipt.json';prior=force._hash(history);source_hash=force._hash(path)
domain=dict(complete=True,authority_refs=['J1','J2'],basis='SYNTHETIC_FIXTURE_TERMINAL_SCOPE_ONLY_NOT_SOURCE_RATING')
def check(board):
 original=metadata.read_native(board)
 rows=topology.unmodelled_internal_transports(board,['PWR'])
 with patch.object(topology,'current_domain',return_value=domain):
  proof=topology.authority_connectivity(board,'PWR')
 assert not proof['available']and not proof['connected']and proof['reason']=='component_internal_transport_model_required'
 assert topology.unmodelled_internal_transports(board,['UNRELATED_RATED_NET'])=={}
 # Exercise the actual width-checker guard before all track-width branches.
 # The fixture's one-amp declaration is TEST INPUT, not production authority.
 with patch.object(constraints.cec_fab,'active_profile_name',return_value='jlcpcb_6l_pofv_high_current'),patch.object(synth,'spec_gnd_current',return_value=0),patch.object(topology,'board_current_domains',return_value={'PWR':domain}),patch.object(topology,'current_contract_for_net',return_value={'amps':1.}):
  width=constraints.CHECKERS['trace-width-high-current'](board,str(path),{})
 assert width[0]is False and width[1]=='component_internal_transport_model_required'
 assert original==metadata.read_native(board)
 return dict(inventory=rows,authority_connectivity=proof,width_checker=width,unrelated_rated_net_inventory_empty=True,RAM_metadata_unchanged=True)
implicit=check(pcbnew.LoadBoard(str(path)))
# Mutate ONLY a fresh RAM fixture to distinct feet, then install an explicit
# native group through the existing saved setter in this owned scratch folder.
b=pcbnew.LoadBoard(str(path));fp=b.FindFootprintByReference('BB1');fp.SetDuplicatePadNumbersAreJumpers(False)
right=max(fp.Pads(),key=lambda q:q.GetPosition().x);right.SetNumber('2')
directory=WORK/'guard-explicit-fixture';directory.mkdir(exist_ok=True)
explicit_path=directory/'board.kicad_pcb';pcbnew.SaveBoard(str(explicit_path),b)
metadata.apply_saved(explicit_path,{'BB1':dict(groups=[['1','2']],pin_numbers=['1','2'],pad_nets={'1':'PWR','2':'PWR'})})
explicit=check(pcbnew.LoadBoard(str(explicit_path)))
assert force._hash(history)==prior and force._hash(path)==source_hash
result=dict(schema=1,scope='SYNTHETIC_NATIVE_ACTUAL_PROTOTYPE_GUARD_REGRESSION_NOT_CURRENT_QUALIFICATION',actual_prototype=dict(path=str(path),sha256=source_hash),historical_receipt=dict(path=str(history),sha256=prior,preserved=True),implicit=implicit,explicit=explicit,code=[dict(path=str(ROOT/'scripts'/p),sha256=force._hash(ROOT/'scripts'/p))for p in('cec_current_topology.py','cec_constraints.py','cec_component_jumper_metadata.py')],guard_fail_closed=True,no_qualification_opt_in=True,current_qualified=False,release_authority=False)
(WORK/'transport-guard-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(implicit_reason=implicit['authority_connectivity']['reason'],explicit_reason=explicit['authority_connectivity']['reason'],implicit_width_verdict=implicit['width_checker'][:2],explicit_width_verdict=explicit['width_checker'][:2],history_preserved=True)))
