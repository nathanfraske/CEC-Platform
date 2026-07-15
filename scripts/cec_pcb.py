#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_pcb -- repo-wide PCB layout toolkit (any board generator can pull on it)
# ============================================================================
# Refined out of the EPS candidate generator so any board in this repo gets the
# same abilities without re-implementing them:
#
#   GEOMETRY     local_pads / pad_global / courtyard_bbox / part_half
#                -- footprint pad + courtyard math, KiCad-rotation correct, with an
#                   optional antenna-keepout trim (e.g. the ESP32-C6 MINI when no Wi-Fi).
#   PASSIVES     verify_passives(nets, spec)        -- netlist-verified ownership check.
#                auto_cluster(P, comps, spec, ...)  -- geometry-driven: place each
#                   decoupler just outside its OWNER IC's power-pad, courtyard-aware,
#                   fanned, with an overlap-relaxation pass; returns residual overlaps.
#                place_offsets(P, owners, table)    -- explicit owner-/frame-relative
#                   placement (when a board wants hand-validated coords).
#   ROUTING      guides(routes)                     -- routing-candidate guide graphics
#                   (12V pours, Kelvin pairs, spine, CAN, USB...) on toggleable user
#                   layers, drawn IN the board so they're visible while routing.
#   VISUALIZE    routing_plan_png(out, ...)         -- a board-accurate matplotlib
#                   routing-plan (parts + pours + traces + vias + legend + tables).
#   RULES        netclass() / write_netclasses() / write_dru()
#                   -- fill a board's .kicad_pro net_settings + a matching .kicad_dru.
#   BUILD        build_board(...)                   -- assemble + write a .kicad_pcb
#                   (frame + passives + guides + GND zone + edge cuts), one-shot guard.
#
# Built on gen-module-pcb.py's emit primitives (place / parse_netlist / gnd_planes /
# stackup / LAYERS / ff / U / carve / fp_path), imported here ONCE with a no-op board
# filter so importing this toolkit never triggers a board build. See the worked
# example in scripts/gen-eps-condensed.py and scripts/README-cec_pcb.md.
import os, re, sys, math, json, uuid
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/scripts")
# Pull gen-module-pcb's emit helpers WITHOUT running its module-level build loop (its
# CLI filters to board-name args; a name matching nothing builds nothing).
_argv = sys.argv
sys.argv = ["cec_pcb", "__none__"]
import importlib.util
_s = importlib.util.spec_from_file_location("_cec_gmp", ROOT + "/scripts/gen-module-pcb.py")
_gmp = importlib.util.module_from_spec(_s); _s.loader.exec_module(_gmp)
sys.argv = _argv
place         = _gmp.place
parse_netlist = _gmp.parse_netlist
gnd_planes    = _gmp.gnd_planes
stackup       = _gmp.stackup
LAYERS        = _gmp.LAYERS
ff            = _gmp.ff
U             = _gmp.U
carve         = _gmp.carve
fp_path       = _gmp.fp_path

# ============================================================ geometry
_PADS_CACHE = {}
_CRTYD_CACHE = {}


def local_pads(libid):
    """{pad-number: (lx, ly)} local pad centres of a footprint (lib `nick:name`). Memoized: the
    footprint geometry is fixed, so the file is read+parsed once per libid (not per overlap check
    -- auto_cluster's relaxation calls this O(iters x parts^2) times)."""
    if libid in _PADS_CACHE:
        return _PADS_CACHE[libid]
    nick, name = libid.split(":")
    t = open(fp_path(nick, name)).read(); out = {}
    for m in re.finditer(r'\(pad ', t):
        b = carve(t, m.start())
        num = re.match(r'\(pad "([^"]*)"', b); at = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)', b)
        if "np_thru_hole" in b.split("\n")[0]:
            continue          # mechanical peg/stabilizer: no net, never an electrical pad-band member
        if num and at and num.group(1):
            out[num.group(1)] = (float(at.group(1)), float(at.group(2)))
    _PADS_CACHE[libid] = out
    return out

_PADSZ_CACHE = {}


def local_pad_sizes(libid):
    """{pad-number: (sx, sy)} LOCAL (un-rotated) pad sizes of a footprint. Memoized like local_pads
    (geometry is fixed). Used by the Kelvin seat to compute a pad's lateral half-extent toward the
    shunt (the standoff that lands the sense pad hard against the shunt inner edge)."""
    if libid in _PADSZ_CACHE:
        return _PADSZ_CACHE[libid]
    nick, name = libid.split(":")
    t = open(fp_path(nick, name)).read(); out = {}
    for m in re.finditer(r'\(pad ', t):
        b = carve(t, m.start())
        num = re.match(r'\(pad "([^"]*)"', b); sz = re.search(r'\(size (-?[\d.]+) (-?[\d.]+)', b)
        if num and sz and num.group(1):
            out[num.group(1)] = (float(sz.group(1)), float(sz.group(2)))
    _PADSZ_CACHE[libid] = out
    return out


def _rot(lx, ly, A):
    a = math.radians(A)                       # KiCad footprint rotation (y-down)
    return (lx * math.cos(a) + ly * math.sin(a), -lx * math.sin(a) + ly * math.cos(a))

def pad_global(ref, pad, P, comps):
    """Global (x,y) of an IC pad, from its placement P[ref]=(x,y,rot) + footprint."""
    X, Y, A = P[ref]; lx, ly = local_pads(comps[ref])[pad]
    dx, dy = _rot(lx, ly, A); return (X + dx, Y + dy)

def _crtyd_local(libid):
    """Cached (pts, circles, pad_lo, pad_hi): the footprint's local CrtYd vertices + CrtYd circles
    + pad band. Read+parsed once per libid (the geometry is fixed); courtyard_bbox then just
    rotates/translates.

    A CrtYd drawn as an `fp_circle` (the M3 mounting-hole courtyard, round passives, ...) carries
    only a `(center)` and an `(end)` point in the s-expr -- a point ON the circumference, NOT a bbox
    corner. The old parse harvested those two points as if they were polygon vertices, so a mount's
    round courtyard collapsed to the segment centre->end: bbox (0,3.45,0,0) => half (1.725, 0) -- a
    DEGENERATE ~zero-height extent (the long-known mounting-hole bbox bug: edge_keepout and placement
    keepouts then read a 0-height hole at every mount). Circles are now captured as (cx,cy,radius) and
    expanded to their true full bbox below, so an M3 mount reports its real ~6.9mm (half 3.45) extent."""
    if libid in _CRTYD_CACHE:
        return _CRTYD_CACHE[libid]
    nick, name = libid.split(":")
    t = open(fp_path(nick, name)).read()
    pys = [ly for (_lx, ly) in local_pads(libid).values()]
    pad_lo, pad_hi = (min(pys), max(pys)) if pys else (-1e9, 1e9)
    pts = []
    circles = []
    for m in re.finditer(r'\(fp_(line|poly|rect|circle)\b', t):
        kind = m.group(1)
        b = carve(t, m.start())
        if 'CrtYd' not in b:
            continue
        if kind == "circle":                            # round courtyard -> (centre, radius), not 2 verts
            cen = re.search(r'\(center (-?[\d.]+) (-?[\d.]+)\)', b)
            end = re.search(r'\(end (-?[\d.]+) (-?[\d.]+)\)', b)
            if cen and end:
                cx, cy = float(cen.group(1)), float(cen.group(2))
                ex, ey = float(end.group(1)), float(end.group(2))
                circles.append((cx, cy, math.hypot(ex - cx, ey - cy)))
            continue
        for a, c in re.findall(r'\((?:start|end|xy|mid|center) (-?[\d.]+) (-?[\d.]+)\)', b):
            pts.append((float(a), float(c)))
    _CRTYD_CACHE[libid] = (pts, circles, pad_lo, pad_hi)
    return _CRTYD_CACHE[libid]


def courtyard_bbox(libid, x=0.0, y=0.0, rot=0.0, *, drop_keepout=False):
    """Global courtyard bbox (xmin,xmax,ymin,ymax) of a placed footprint. If
    drop_keepout, trim an RF-module antenna keepout (a courtyard lobe extending far
    past the pad rows) to the pad band -- used when wireless is unpopulated. The footprint
    parse is memoized (see _crtyd_local), so this is cheap even under auto_cluster's relaxation."""
    pts, circles, pad_lo, pad_hi = _crtyd_local(libid)
    xs = []; ys = []
    for (lx, ly) in pts:
        if drop_keepout and ly < pad_lo - 3.0:          # antenna lobe past the pads
            ly = pad_lo - 1.0
        elif drop_keepout and ly > pad_hi + 3.0:
            ly = pad_hi + 1.0
        dx, dy = _rot(lx, ly, rot); xs.append(x + dx); ys.append(y + dy)
    for (cx, cy, r) in circles:                         # a circle is rotation-invariant: rotate the
        if drop_keepout and cy < pad_lo - 3.0:          # centre, then expand by +/- the radius
            cy = pad_lo - 1.0
        elif drop_keepout and cy > pad_hi + 3.0:
            cy = pad_hi + 1.0
        dx, dy = _rot(cx, cy, rot)
        xs += [x + dx - r, x + dx + r]; ys += [y + dy - r, y + dy + r]
    if not xs:
        return (x - 1, x + 1, y - 1, y + 1)
    return (min(xs), max(xs), min(ys), max(ys))

def part_half(libid):
    """(hx, hy) courtyard half-extent of a part at rot0 (for spacing passives)."""
    x0, x1, y0, y1 = courtyard_bbox(libid)
    return ((x1 - x0) / 2.0, (y1 - y0) / 2.0)

# ============================================================ passives
def verify_passives(nets, spec, *, label="passive"):
    """spec: ref -> (owner, expected_net, role). Assert each part shares its expected
    net so the cluster owner is correct. Warns (does not fail); returns ok bool."""
    members = {nm: {r for r, _ in nodes} for nm, nodes in nets.items()}
    bad = [ref for ref, v in spec.items() if ref not in members.get(v[1], set())]
    for ref in bad:
        own, net = spec[ref][0], spec[ref][1]
        print(f"  VERIFY: {ref} expected on {net} (owner {own}) -- not in netlist", file=sys.stderr)
    print(f"  {label} ownership: {len(spec)-len(bad)}/{len(spec)} netlist-verified")
    return not bad

def _nearest_edge(bb, px, py):
    """Outward axis-aligned unit + the courtyard edge coord nearest the pad."""
    xmin, xmax, ymin, ymax = bb
    d = min([(px - xmin, (-1, 0), xmin), (xmax - px, (1, 0), xmax),
             (py - ymin, (0, -1), ymin), (ymax - py, (0, 1), ymax)], key=lambda c: c[0])
    return d[1], d[2]

def _ovl(a, b, m=0.0):
    return not (a[1] <= b[0] - m or b[1] <= a[0] - m or a[3] <= b[2] - m or b[3] <= a[2] - m)

def auto_cluster(P, comps, spec, *, clr=0.45, drop_keepout=(), fixed_overrides=None, iters=120):
    """Geometry-driven decoupling placement. spec: ref -> (owner, pad). Each passive is
    parked just outside its owner's courtyard edge nearest that power-pad, fanned along
    the edge, then an overlap-relaxation pass separates residual collisions (passive vs
    passive and passive vs any placed footprint). `fixed_overrides` {ref:(x,y,rot)} are
    honoured verbatim (and treated as fixed). Returns the list of residual overlaps
    (ref pairs) so the caller can nudge/override the few that don't settle."""
    fixed_overrides = fixed_overrides or {}
    movable = []
    by_owner = defaultdict(list)
    for ref, (owner, pad) in spec.items():
        if ref in fixed_overrides:
            P[ref] = fixed_overrides[ref]; continue
        by_owner[owner].append((ref, pad)); movable.append(ref)
    for owner, members in by_owner.items():
        if owner not in P or owner not in comps:
            continue
        bb = courtyard_bbox(comps[owner], *P[owner], drop_keepout=(owner in drop_keepout))
        by_edge = defaultdict(list)
        for ref, pad in members:
            px, py = pad_global(owner, pad, P, comps)
            d, e = _nearest_edge(bb, px, py)
            by_edge[d].append((ref, px, py, e))
        for d, lst in by_edge.items():
            lst.sort(key=lambda v: (v[2] if d[0] else v[1]))     # along the edge
            for ref, px, py, e in lst:
                hx, hy = part_half(comps[ref])
                if d[0]:                                          # left/right edge
                    P[ref] = (e + d[0] * (hx + clr), py, 90)
                else:                                             # top/bottom edge
                    P[ref] = (px, e + d[1] * (hy + clr), 0)
    # relaxation: push apart any overlap (movable parts only move)
    obstacles = [r for r in P if r not in movable and r in comps]
    for _ in range(iters):
        moved = False
        for ref in movable:
            ax = courtyard_bbox(comps[ref], *P[ref])
            arx, ary = (ax[0] + ax[1]) / 2, (ax[2] + ax[3]) / 2
            for other in movable + obstacles:
                if other == ref or other not in comps:
                    continue
                ob = courtyard_bbox(comps[other], *P[other], drop_keepout=(other in drop_keepout))
                if not _ovl(ax, ob, clr * 0.4):
                    continue
                ovx = min(ax[1], ob[1]) - max(ax[0], ob[0])
                ovy = min(ax[3], ob[3]) - max(ax[2], ob[2])
                bcx, bcy = (ob[0] + ob[1]) / 2, (ob[2] + ob[3]) / 2
                x, y, r = P[ref]
                if ovx < ovy:
                    x += 0.35 if arx >= bcx else -0.35
                else:
                    y += 0.35 if ary >= bcy else -0.35
                P[ref] = (x, y, r); moved = True
                break
        if not moved:
            break
    return _overlaps(P, comps, movable, drop_keepout)

def _overlaps(P, comps, movable, drop_keepout=()):
    out = []
    refs = [r for r in P if r in comps]
    for i, a in enumerate(refs):
        if a not in movable:
            continue
        ba = courtyard_bbox(comps[a], *P[a])
        for b in refs[i + 1:]:
            bb = courtyard_bbox(comps[b], *P[b], drop_keepout=(b in drop_keepout))
            if _ovl(ba, bb, 0.0):
                out.append((a, b))
    return out

def place_offsets(P, table):
    """Explicit placement. table: ref -> (x, y, rot) already resolved by the board
    (frame-/owner-relative is the board's call). Reproduces hand-validated coords."""
    P.update(table); return P

# ============================================================ routing guides
def guides(routes):
    """routes: list of dicts on toggleable user layers:
        {"poly": [(x,y)...], "layer": L, "w": 0.12}
        {"line": [(x,y)...], "layer": L, "w": 0.25}
        {"text": s, "at": (x,y), "layer": L, "size": 0.7}
    Returns the gr_* s-expr block (non-copper -> no DRC impact)."""
    out = []
    for r in routes:
        L = r["layer"]
        if "poly" in r:
            s = " ".join(f"(xy {ff(x)} {ff(y)})" for x, y in r["poly"])
            out.append(f'\t(gr_poly (pts {s}) (stroke (width {r.get("w",0.12)}) (type solid)) '
                       f'(fill none) (layer "{L}") (uuid "{U()}"))')
        elif "line" in r:
            for (x1, y1), (x2, y2) in zip(r["line"], r["line"][1:]):
                out.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) '
                           f'(stroke (width {r.get("w",0.25)}) (type solid)) (layer "{L}") (uuid "{U()}"))')
        elif "text" in r:
            x, y = r["at"]
            out.append(f'\t(gr_text "{r["text"]}" (at {ff(x)} {ff(y)} 0) (layer "{L}") '
                       f'(uuid "{U()}") (effects (font (size {r.get("size",0.7)} {r.get("size",0.7)}) '
                       f'(thickness 0.12))))')
    return "\n".join(out)

# ============================================================ routing-plan PNG
def routing_plan_png(out, *, W, H, title, P, comps, pours=(), traces=(), vias=(),
                     tables=(), legend=(), mounts=(), drop_keepout=(), subtitle=()):
    """Board-accurate matplotlib routing plan. Parts drawn from their courtyards;
    pours = [(poly, color, alpha, label, label_xy)], traces = [(pts, color, lw, ls)],
    vias = [(x,y)], tables = [(title, [lines])], legend = [(color, lw, ls, label)]."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon, Circle
    from matplotlib.lines import Line2D
    fig = plt.figure(figsize=(17.5, 8.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.65, 1.0], wspace=0.02)
    ax = fig.add_subplot(gs[0]); nx = fig.add_subplot(gs[1]); nx.axis("off")
    ax.set_aspect("equal"); ax.set_xlim(-3, W + 3); ax.set_ylim(H + 3, -4); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, ec="#222", lw=1.6))
    ax.text(W / 2, -2.0, title, ha="center", va="center", fontsize=11, weight="bold", color="#101418")
    for ref, (x, y, rot) in P.items():
        if ref not in comps:
            continue
        x0, x1, y0, y1 = courtyard_bbox(comps[ref], x, y, rot, drop_keepout=(ref in drop_keepout))
        big = ref.startswith("J")
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=True,
                     fc="#dde6ee" if big else "#eef1f4", ec="#9aa7b4", lw=0.7, alpha=0.95, zorder=2))
        if ref[0] in "UJRD" or ref.startswith("RS"):
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, ref, ha="center", va="center",
                    fontsize=8 if big else 6.4, color="#101418", zorder=6, weight="bold")
    for (mx, my, mr) in mounts:
        ax.add_patch(Circle((mx, my), mr, fill=True, fc="#f2d34e", ec="#b69a18", lw=0.8, zorder=1))
    for poly, color, alpha, label, lxy in pours:
        ax.add_patch(Polygon(poly, closed=True, fc=color, ec=color, alpha=alpha, lw=1.0, zorder=3))
        if label:
            ax.text(lxy[0], lxy[1], label, fontsize=6.5, color=color, zorder=6, weight="bold")
    for pts, color, lw, ls in traces:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color, lw=lw, ls=ls, zorder=5)
    for (vx, vy) in vias:
        ax.plot(vx, vy, 'o', ms=2.4, mfc="#1f9e6f", mec="none", zorder=4)
    if legend:
        h = []
        for c, lw, ls, lab in legend:
            if ls in ('o', '.', 's', '*'):       # marker entry (e.g. a via)
                h.append(Line2D([], [], color=c, lw=0, marker=ls, mfc=c, mec="none", ms=6, label=lab))
            else:
                h.append(Line2D([], [], color=c, lw=lw, ls=ls, label=lab))
        ax.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=3,
                  fontsize=8, framealpha=.95)
    y = 0.99
    for ttl, lines in tables:
        nx.text(0.0, y, ttl, fontsize=11, weight="bold", color="#101418", transform=nx.transAxes)
        for k, ln in enumerate(lines):
            nx.text(0.02, y - 0.034 * (k + 1), ln, fontsize=8.2, color="#222",
                    transform=nx.transAxes, family="DejaVu Sans")
        y -= 0.034 * (len(lines) + 1) + 0.025
    for s in subtitle:
        nx.text(0.0, y, s, fontsize=8, color="#444", transform=nx.transAxes, style="italic"); y -= 0.04
    fig.savefig(out, dpi=145, bbox_inches="tight", facecolor="white")
    print(f"WROTE {os.path.relpath(out, ROOT)}")

# ============================================================ netclasses + DRU
def netclass(name, track, via_d, via_dr, priority, *, clr=0.2, dpw=0.2, dpg=0.25,
            color="rgba(0, 0, 0, 0.000)"):
    """Build one KiCad net_settings class dict."""
    return {"bus_width": 12, "clearance": clr, "diff_pair_gap": dpg, "diff_pair_width": dpw,
            "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": name,
            "pcb_color": color, "priority": priority, "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": track, "tuning_profile": "", "via_diameter": via_d, "via_drill": via_dr,
            "wire_width": 6}

def write_netclasses(pro_path, classes, patterns):
    """Merge net_settings (classes + [(netclass, pattern)...]) into a .kicad_pro,
    preserving any other keys KiCad manages."""
    pro = json.load(open(pro_path)) if os.path.exists(pro_path) and os.path.getsize(pro_path) else {}
    pro["net_settings"] = {"classes": classes, "meta": {"version": 4}, "net_colors": None,
                           "netclass_assignments": None,
                           "netclass_patterns": [{"netclass": nc, "pattern": p} for nc, p in patterns]}
    json.dump(pro, open(pro_path, "w"), indent=2)
    print(f"WROTE {os.path.relpath(pro_path, ROOT)}  ({len(classes)} classes, {len(patterns)} patterns)")

def write_dru(dru_path, rules, header=""):
    """Write a .kicad_dru. rules: list of (name, constraint, condition) or raw blocks
    (a 3-tuple is a rule; a 1-tuple/str is a literal comment block)."""
    body = ["(version 1)", ""]
    if header:
        body += ["# " + ln for ln in header.strip().splitlines()] + [""]
    for r in rules:
        if isinstance(r, (tuple, list)) and len(r) == 3:
            name, constraint, cond = r
            body.append(f'(rule "{name}"\n\t(constraint {constraint})\n\t(condition "{cond}"))')
        else:
            body.append(str(r[0] if isinstance(r, (tuple, list)) else r))
        body.append("")
    open(dru_path, "w").write("\n".join(body).rstrip() + "\n")
    print(f"WROTE {os.path.relpath(dru_path, ROOT)}")

# ============================================================ board build
def export_netlist(dir_, base):
    netf = f"{ROOT}/modules/{dir_}/{base}.net"
    os.system(f"cd {ROOT}/modules/{dir_} && kicad-cli sch export netlist -o {base}.net "
              f"{base}.kicad_sch >/dev/null 2>&1")
    return netf

def build_board(out, netf, P, mounts, logo, W, H, *, guides_str="", zones=True,
                drop_keepout=(), gen="cec-cec_pcb", note=None, force_argv=True,
                corner_radius=0.0, back_refs=(), inner_power_routing=False,
                fiducials=()):
    """Assemble + write a .kicad_pcb: net decls, footprints (frame+passives), edge cuts,
    optional GND zone, routing guides, back note. One-shot guard: refuses to overwrite a
    board that already carries tracks/vias unless --force is on sys.argv."""
    if os.path.exists(out) and re.search(r"\n\s*\((?:segment|via)\b", open(out).read()):
        if force_argv and "--force" not in sys.argv:
            print(f"  SKIP {os.path.relpath(out, ROOT)}: already routed; pass --force"); return False
    comps, vals, nets = parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    fps = []
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if lib:
            fps.append(place(lib, ref, x, y, rot, padnet, code_of, val=vals.get(ref),
                             flip=(ref in back_refs)))
        else:
            print(f"  WARN no footprint for {ref}", file=sys.stderr)
    for i, (x, y) in enumerate(mounts, 1):
        fps.append(place("cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via", f"H{i}", x, y, 0,
                         padnet, code_of, gnd_all=True))
    for i, (x, y) in enumerate(fiducials, 1):
        # assembly fiducials (round-2 item 6, 2026-07-08): the placer always PLANNED
        # FID1.. via place_mechanical but materialize dropped them ("board-level
        # finishing") -- same emission path as the hand 12vhpwr's FID1-3.
        fps.append(place("cec-Fiducial:Fiducial_1mm_Mask2mm", f"FID{i}", x, y, 0,
                         padnet, code_of))
    if logo:
        # (x, y) = back copper logo (module convention); (x, y, False) = FRONT logo
        # (hub-rev2 centerpiece: the shine-through CEC mark at the LED-ring center).
        _lflip = logo[2] if len(logo) > 2 else True
        fps.append(place("cec:CEC_Logo_Copper", "LOGO1", logo[0], logo[1], 0, padnet, code_of, flip=_lflip))
    e = []
    r = float(corner_radius or 0.0)
    if r <= 0:
        pts = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            e.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) '
                     f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
    else:
        # ROUNDED-CORNER outline (owner ask 2026-07-08): 4 shortened edges + 4 quarter arcs.
        c = r * (1 - 0.7071067811865476)          # arc midpoint inset from the corner
        lines = [((r, 0), (W - r, 0)), ((W, r), (W, H - r)),
                 ((W - r, H), (r, H)), ((0, H - r), (0, r))]
        arcs = [((W - r, 0), (W - c, c), (W, r)),          # TR
                ((W, H - r), (W - c, H - c), (W - r, H)),  # BR
                ((r, H), (c, H - c), (0, H - r)),          # BL
                ((0, r), (c, c), (r, 0))]                  # TL
        for (x1, y1), (x2, y2) in lines:
            e.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) '
                     f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
        for (sx, sy), (mx, my), (ex, ey) in arcs:
            e.append(f'\t(gr_arc (start {ff(sx)} {ff(sy)}) (mid {ff(mx)} {ff(my)}) (end {ff(ex)} {ff(ey)}) '
                     f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
    note = note or f'\t(gr_text "CEC {os.path.basename(out)[:-10]}  4L 2oz/1oz" ' \
                   f'(at {ff(logo[0] if logo else W/2)} {ff(H-3)} 0) (layer "B.SilkS") (uuid "{U()}") ' \
                   f'(effects (font (size 0.9 0.9) (thickness 0.13)) (justify mirror)))'
    netdecl = '\t(net 0 "")\n' + "\n".join(f'\t(net {code_of[x]} "{x}")' for x in names)
    # inner_power_routing (the 24-pin/Hub stackup exception, CLAUDE.md): ONE inner GND
    # plane (In1) + In2 left EMPTY as a rail-routing layer (12V/5V/3V3/5VSB route around
    # each other) -- cable boards keep both inners GND.
    _zl = '"In1.Cu"' if inner_power_routing else '"In1.Cu" "In2.Cu"'
    zone = (gnd_planes(code_of["GND"], W, H, layers=_zl) + "\n") if (zones and "GND" in code_of) else ""
    if inner_power_routing:
        # In2's declared KIND drives KiCad's DSN (type ...) export: 'power' makes
        # Freerouting refuse the layer entirely (measured: 0 tracks on the freed In2
        # until this flip). Rename the stale '12V' hint too -- it is a rail-ROUTING
        # layer on this stackup class, not a plane.
        doc_kind_fix = True
    g = (guides_str + "\n") if guides_str else ""
    doc = (f"(kicad_pcb\n\t(version 20260206)\n\t(generator \"{gen}\")\n\t(generator_version \"10.0\")\n"
           "\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n\t(paper \"A4\")\n" + LAYERS +
           "\n\t(setup\n" + stackup() + "\n\t\t(pad_to_mask_clearance 0)\n"
           "\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
           + netdecl + "\n" + "\n".join(fps) + "\n" + "\n".join(e) + "\n" + zone + g + note +
           "\n\t(embedded_fonts no)\n)\n")
    if inner_power_routing:
        doc = doc.replace('(6 "In2.Cu" power "12V")', '(6 "In2.Cu" signal "PWR_RT")', 1)
    # drop the RF antenna keepout courtyard lobe (no wireless) where requested
    if drop_keepout:
        doc = doc.replace("-10.98", "-4.95")     # ESP32-C6 MINI antenna lobe -> body
    open(out, "w").write(doc)
    print(f"WROTE {os.path.relpath(out, ROOT)}  board={W}x{H:.0f}mm  parts={len(fps)}")
    return True
