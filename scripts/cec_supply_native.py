"""Isolated native supply-group feasibility, never full-board/plane signoff.

Only stackup, fabrication properties and design/netclass rules come from the
reference PCB. Component identities, lands, nets and poses come from the live
source contract. No old board placement or copper is imported. Run in a short
worker process to contain KiCad's native object lifetimes.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

_NATIVE_KEEPALIVE = []


def preferred_layouts(layouts, proof):
    """Rank proven isolated groups first; retain contextual fallbacks unproved.

    An isolated failure cannot rule out sharing a neighboring board portal.
    It must not, however, outrank an available completely constructed group
    merely because its unrouteable Euclidean loop looked slightly shorter.
    """
    indexes = list(proof.get("accepted_indexes") or ())
    if (any(type(i) is not int or i < 0 or i >= len(layouts) for i in indexes)
            or len(set(indexes)) != len(indexes)):
        raise ValueError("invalid native layout index evidence")
    order = sorted(indexes) + [i for i in range(len(layouts)) if i not in set(indexes)]
    return [layouts[i] for i in order], {
        "scope": "isolated_native_preference_not_full_board_admission",
        "qualified_indexes": sorted(indexes), "ordered_indexes": order,
        "fallback_count": len(layouts)-len(indexes)}


def qualify(nl, comps, owner, requirements, layouts, *, reference_board,
            ground_max_mm=2.5, max_trials=12, timeout_s=60):
    if max_trials < 1 or timeout_s <= 0 or not math.isfinite(ground_max_mm) or ground_max_mm < 0:
        raise ValueError("native supply budgets must be positive")
    payload = {"reference_board":str(reference_board),"owner":owner,
        "requirements":requirements,"layouts":layouts[:max_trials],
        "ground_max_mm":ground_max_mm,
        "components":{r:{"footprint":comps[r],"value":nl.comps[r].value,
                           "props":nl.comps[r].props} for r in sorted({owner,*requirements})},
        "nets":{n:[(r,str(p)) for r,p in nodes if r in {owner,*requirements}]
                for n,nodes in nl.nets.items()}}
    report={"scope":"isolated_native_group_not_full_board", "ok":False,
            "budget":max_trials,"trials":[],"accepted_indexes":[]}
    if not layouts:
        report["reason"]="no_geometric_layouts"
        return [],report
    with tempfile.TemporaryDirectory(prefix="cec-supply-proof-") as tmp:
        request=Path(tmp)/"request.json"; response=Path(tmp)/"response.json"
        request.write_text(json.dumps(payload),encoding="utf-8")
        try:
            proc=subprocess.run([sys.executable,__file__,str(request),str(response)],
                capture_output=True,text=True,timeout=timeout_s)
        except subprocess.TimeoutExpired:
            report["reason"]="native_group_timeout"
            return [],report
        if proc.returncode or not response.is_file():
            report.update(reason="native_group_worker_failure",exit_code=proc.returncode,
                          diagnostic=(proc.stderr or proc.stdout)[-1200:])
            return [],report
        report.update(json.loads(response.read_text()))
    return [layouts[i] for i in report["accepted_indexes"]],report


def _worker(payload):
    import pcbnew
    from cec_native_items import create_empty_board
    import cec_pcb
    import cec_decoupler_cell as cells
    reference=pcbnew.LoadBoard(payload["reference_board"])
    if reference is None:
        raise ValueError("native supply proof requires a rule-bearing reference PCB")
    rows=[]; accepted=[]
    # Retain boards until process exit; borrowed native pads/netclasses must
    # not outlive the objects that own them during a sequence of trials.
    keepalive=_NATIVE_KEEPALIVE
    keepalive.append(reference)
    for index,poses in enumerate(payload["layouts"]):
        board=create_empty_board(); keepalive.append(board)
        board.SetCopperLayerCount(reference.GetCopperLayerCount())
        board.SetDesignSettings(reference.GetDesignSettings())
        board.SetProperties(reference.GetProperties())
        nets={}
        pin_nets={}
        for name,nodes in payload["nets"].items():
            if not nodes: continue
            net=pcbnew.NETINFO_ITEM(board,name); board.Add(net); nets[name]=net
            source_net=reference.GetNetInfo().GetNetItem(name)
            if source_net:
                net.SetNetClass(source_net.GetNetClassSlow())
            for r,p in nodes: pin_nets[(r,p)]=net
        fps={}
        for ref,data in payload["components"].items():
            path=Path(cec_pcb.fp_path(*data["footprint"].split(":",1)))
            fp=pcbnew.FootprintLoad(str(path.parent),path.stem)
            if fp is None: raise ValueError("missing native supply footprint")
            fp.SetReference(ref); fp.SetValue(data["value"])
            for k,v in data["props"].items():
                if isinstance(v,str): fp.SetField(k,v)
            # Use a positive local frame for native routing-grid conventions;
            # these coordinates are a probe domain, not a board-specific seat.
            fp.SetPosition(pcbnew.VECTOR2I_MM(40.+poses[ref][0],40.+poses[ref][1]))
            fp.SetOrientationDegrees(poses[ref][2]); board.Add(fp); fps[ref]=fp
            for pad in fp.Pads():
                net=pin_nets.get((ref,pad.GetNumber()))
                if net: pad.SetNet(net)
        # A generous local domain removes artificial edge constraints. This
        # deliberately does NOT prove the group's eventual board-edge seat.
        for a,b in (((0,0),(80,0)),((80,0),(80,80)),
                    ((80,80),(0,80)),((0,80),(0,0))):
            edge=pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
        assignment={"requirements":[],"assigned":{},"missing":[]}
        supply_bad=[]
        for cap,q in payload["requirements"].items():
            owner=payload["owner"]
            pad=next(p for p in fps[owner].Pads() if p.GetNumber()==str(q["pin"]))
            cp=next(p for p in fps[cap].Pads() if p.GetNetname()==q["rail"])
            req={"id":cap,"ref":owner,"pin":str(q["pin"]),"rail":q["rail"],"pad":pad,
                 "return_rail":q.get("return_rail") or "GND","return_pin":q.get("return_pin")}
            if q.get("return_pin"):
                req["return_pad"]=next(p for p in fps[owner].Pads() if p.GetNumber()==str(q["return_pin"]))
            distance=math.hypot(pad.GetPosition().x-cp.GetPosition().x,
                                pad.GetPosition().y-cp.GetPosition().y)/1e6
            if distance > float(q["max_mm"])+1e-6:
                supply_bad.append(cap)
            assignment["requirements"].append(req)
            assignment["assigned"][cap]={"cap_ref":cap,"requirement":req,"distance_mm":distance}
        result=cells.synthesize_board(board,board_path=payload["reference_board"],assignment=assignment)
        ground_bad=[r["cap"] for r in result["cells"] if r.get("return_rail")=="GND"
                    and float(r.get("ground_pin_distance_mm",float("inf")))>payload["ground_max_mm"]+1e-6]
        ok=result["ok"] and not ground_bad and not supply_bad
        rows.append({"index":index,"ok":ok,"owned":result["owned"],
                     "ground_distance_failures":ground_bad,
                     "supply_distance_failures":supply_bad,"cells":result["cells"]})
        if ok: accepted.append(index)
    return {"ok":bool(accepted),"accepted_indexes":accepted,"trials":rows,
            "reference_geometry_imported":False,
            "copper_layers":reference.GetCopperLayerCount(),
            "source_component_count":len(payload["components"]),
            "reason":"native_local_groups" if accepted else "no_native_local_group"}


if __name__=="__main__":
    result=_worker(json.loads(Path(sys.argv[1]).read_text()))
    Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+"\n")
    # The worker's address space owns the borrowed SWIG graph until exit.
    os._exit(0)
