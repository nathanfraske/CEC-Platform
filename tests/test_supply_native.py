"""Native local proof never imports old placement and fails closed on errors."""
import hashlib
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_supply_native as native
import cec_synth_pipeline as synth


@pytest.mark.parametrize("names", [("A","B","C"),("X17","Y99","Z")])
def test_native_preference_keeps_contextual_fallbacks_and_input_order(names):
    layouts=[{n:(0.,0.,0.)} for n in names]
    ordered,report=native.preferred_layouts(layouts,{"accepted_indexes":[2,1]})
    assert ordered==[layouts[1],layouts[2],layouts[0]]
    assert list(layouts[0])==[names[0]]
    assert report["fallback_count"]==1
    assert report["ordered_indexes"]==[1,2,0]


def test_no_native_success_does_not_claim_contextual_impossibility():
    layouts=[{"one":(0,0,0)}]
    ordered,report=native.preferred_layouts(layouts,{"accepted_indexes":[],"reason":"native_group_timeout"})
    assert ordered==layouts and report["fallback_count"]==1


@pytest.mark.parametrize("indexes", [[-1],[1],[True],[0,0],["0"]])
def test_native_preference_rejects_corrupt_proof_indexes(indexes):
    with pytest.raises(ValueError):
        native.preferred_layouts([{}],{"accepted_indexes":indexes})


def test_actual_late_layout_provider_uses_native_ranking_not_only_distance():
    import ast,inspect
    tree=ast.parse(inspect.getsource(synth.synth_one))
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
            and n.name=="_qualified_supply_layouts")
    groups=[{"owner":(0,0,0),"cap":(i,0,0)} for i in range(3)]
    env={"_native_supply_layout_cache":{},"_joint_supply_layouts":lambda *a,**k:(list(groups),{}),
         "nl":None,"comps":{},"cfg":SimpleNamespace(params={},pcb="rules"),"passives":[]}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),"actual-provider","exec"),env)
    with mock.patch.object(native,"qualify",return_value=([groups[1]],{"accepted_indexes":[1]})):
        preferred,evidence=env[fn.name]("owner",{})
        strict,_=env[fn.name]("owner",{},native_required=True)
    assert preferred==[groups[1],groups[0],groups[2]]
    assert strict==[groups[1]] and evidence["native_preference"]["fallback_count"]==2


def topology(name):
    comps={name:"cec-Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
           "CAP_IN":"cec-Capacitor_SMD:C_0603_1608Metric",
           "CAP_OUT":"cec-Capacitor_SMD:C_0603_1608Metric"}
    nl=synth.Netlist(comps={r:SimpleNamespace(value="test",props={}) for r in comps},nets={
        "VIN":[(name,"6"),("CAP_IN","1")],"VOUT":[(name,"1"),("CAP_OUT","1")],
        "GND":[(name,"3"),(name,"7"),("CAP_IN","2"),("CAP_OUT","2")],
        "EN":[(name,"4")]})
    reqs={r:{"owner":name,"pin":p,"rail":n,"max_mm":2.}
          for r,p,n in (("CAP_IN","6","VIN"),("CAP_OUT","1","VOUT"))}
    return nl,comps,reqs


@pytest.mark.parametrize("failure", ["timeout","exit"])
def test_native_worker_failures_never_authorize_a_group(failure):
    nl,comps,reqs=topology("IC")
    kwargs=({"side_effect":subprocess.TimeoutExpired("probe",.1)} if failure=="timeout"
            else {"return_value":SimpleNamespace(returncode=2,stderr="failed",stdout="")})
    with mock.patch.object(native.subprocess,"run",**kwargs):
        groups,report=native.qualify(nl,comps,"IC",reqs,[{}],reference_board="rules")
    assert not groups and not report["ok"]
    assert report["reason"] in ("native_group_timeout","native_group_worker_failure")


@pytest.mark.parametrize("name", ["U71","SUPPLY_DEVICE"])
def test_current_lands_qualify_independently_of_reference_placement(tmp_path,name):
    import pcbnew
    nl,comps,reqs=topology(name)
    board=pcbnew.BOARD(); board.SetCopperLayerCount(6)
    props=board.GetProperties(); props["CEC_FAB_PROFILE"]="jlcpcb_6l_pofv_signal"
    board.SetProperties(props)
    # A foreign footprint at the probe origin must NOT be imported as context.
    fp=pcbnew.FOOTPRINT(board); fp.SetReference("OLD_OBSTRUCTION"); board.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I_MM(40,40))
    pad=pcbnew.PAD(fp); pad.SetSize(pcbnew.VECTOR2I_MM(60,60));
    pad.SetPosition(pcbnew.VECTOR2I_MM(40,40))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); fp.Add(pad)
    path=tmp_path/"reference.kicad_pcb"; pcbnew.SaveBoard(str(path),board)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    layouts,_=synth._joint_supply_layouts(nl,comps,name,reqs)
    assert layouts
    good,report=native.qualify(nl,comps,name,reqs,layouts[:2],reference_board=path)
    assert good and report["ok"] and report["copper_layers"]==6
    assert not report["reference_geometry_imported"] and report["source_component_count"]==3
    assert all(r["owned"]==2 for r in report["trials"])
    strict,report=native.qualify(nl,comps,name,reqs,layouts[:1],reference_board=path,ground_max_mm=.01)
    assert not strict and report["trials"][0]["ground_distance_failures"]
    strict_reqs={r:dict(q,max_mm=.01) for r,q in reqs.items()}
    strict,report=native.qualify(nl,comps,name,strict_reqs,layouts[:1],reference_board=path)
    assert not strict and report["trials"][0]["supply_distance_failures"]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
