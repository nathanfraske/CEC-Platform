#!/usr/bin/env python3
"""cec_reasoning_bakeoff.py -- text-reasoning bake-off across the local fleet.

Purpose: a standing scoreboard the HOST-SIDE deep tier (deepseek-v4-flash /
cec-manager-max) walks into once it is reachable from WSL, benchmarked against
the resident WSL models. Until then that candidate is auto-SKIPPED (health
pre-probe; we never ask the broker to start it, so no 15-min ensure-failed churn).

Vision models run the SAME text suite on purpose: if a vision twin reasons as
well as its text twin, ONE resident vision model can serve both modalities and
we save GPU swaps (the "what value do the vision builds have" question).

Gold answers are computed, not authored: logic grids are brute-force verified
unique, code-prediction gold is captured by exec'ing the snippet at gen time,
math/domain answers come from the same formulas the prompts state. Seeded
parameter draws -> novel values, contamination-resistant.

Methodology carried from docs/llm-manager-bench-2026-06-09.md:
  - cec-manager sampling floor (temp>=0.3 + presence_penalty 0.8; decode-loop hazard)
  - thinking overrun (empty content, answer stranded in reasoning_content) is
    recorded as status="overrun" AND we mine reasoning_content for a secondary
    "mined" score (miner->scribe lite). Strict score only trusts content.
  - thinking stays ENABLED for all seats here (the _NOTHINK rule in the vlm
    bake-off applies to bounded grammar-judging calls, not open reasoning).

Usage:
  python3 scripts/cec_reasoning_bakeoff.py gen [--check]        # (re)write tests/eval/bakeoff/tasks-v1.json
  python3 scripts/cec_reasoning_bakeoff.py run [--models a,b|all] [--limit N] [--tag -v1]
  python3 scripts/cec_reasoning_bakeoff.py smoke                 # 2 tasks, cec-worker only
  python3 scripts/cec_reasoning_bakeoff.py report [--tag -v1]

Results: build/reasoning-bakeoff/results-{model}{tag}.json + transcript{tag}.jsonl,
ledger sidecar board=reasoning-bakeoff mode=eval (degrades to a warning).

TODO (owner-requested 2026-06-10, OPTIONAL/opt-in -- "just if I want it"):
  Live run viewer GUI: a local page (extend the vlm-bakeoff self-contained-HTML
  pattern, but live) that tails the transcript JSONLs (this harness + vlm-bakeoff)
  and the broker log, and shows AS IT HAPPENS: which models/clients are running
  (broker /broker/stats + /broker/models), each call's full prompt/context, the
  full thinking dialogue (reasoning_content) streaming alongside the final
  content, and for vision calls the actual images fed (vlm-bakeoff assets/*.png
  referenced by the transcript). Transcript lines already carry full prompt,
  content, reasoning, and a ts field for exactly this. Plain stdlib http.server
  + EventSource polling is enough; no framework. Strictly read-only.
"""
import argparse, contextlib, hashlib, io, itertools, json, math, os, random, re, sys, time
import urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Two suites: "general" = reasoning challenges; "workload" = the actual seats these
# models hold (manager verdicts, CL-19-style grounded extraction, AutoDiagnoser
# ticket triage, route math). Fresh synthetic cases, never the burned CL-11 fixtures.
SUITES = {"general": ("tasks-v1.json", "-v1"), "workload": ("tasks-workload-v1.json", "-wl1")}
def suite_path(suite):
    return os.path.join(ROOT, "tests", "eval", "bakeoff", SUITES[suite][0])
TASKS_PATH = suite_path("general")
OUT_DIR = os.path.join(ROOT, "build", "reasoning-bakeoff")
BROKER = os.environ.get("CEC_VLLM_URL", "http://localhost:8080/v1")
CLIENT = "reasoning-bakeoff"
SEED = 20260610

# Default roster order: text workers first, then the vision twins + vision judge.
DEFAULT_MODELS = ["cec-worker", "cec-worker-quality",
                  "cec-worker-vision", "cec-worker-quality-vision", "cec-vision-judge"]
ALL_MODELS = DEFAULT_MODELS + ["cec-manager-fast", "cec-manager", "deepseek-v4-flash"]
# Host-side candidates: pre-probe health directly; if unreachable -> SKIP without
# touching the broker (do NOT trigger an on-demand start that can't health-check).
HOST_GATED = {"deepseek-v4-flash", "cec-manager-max"}
FLOORS = {"cec-manager": (0.3, 0.8)}          # (temperature, presence_penalty)
MAX_TOKENS = {"cec-manager": 8000, "cec-manager-fast": 8000, "deepseek-v4-flash": 8000}
DEFAULT_TEMP, DEFAULT_MAX_TOKENS, TIMEOUT = 0.2, 6000, 900

ANSWER_RE = re.compile(r"ANSWER\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
SUFFIX = '\nEnd your reply with one final line of the form "ANSWER: <value>" and nothing after it.'

# ---------------------------------------------------------------- task generation
def _exec_gold(src):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(src, {"__name__": "__main__"})       # fixed snippets below, gen-time only
    return buf.getvalue().strip()

def _gen_quant(rng):
    out = []
    for i in range(2):  # template A: production with planted distractor
        while True:     # constrain draws so the reject split is exact (no 0.2-part ambiguity)
            m, r, h, scrap, distract = rng.randint(4, 9), rng.randint(110, 190), rng.choice([8, 10, 12]), rng.choice([4, 5, 8, 10]), rng.randint(11, 19)
            if (m * r * h * (100 - scrap)) % 100 == 0: break
        good_per_day = m * r * h * (100 - scrap) // 100
        out.append(dict(
            id=f"quant-a{i+1}", family="quant",
            prompt=(f"A plant runs {m} presses. Each press stamps {r} parts per hour and runs {h} hours per day. "
                    f"Quality control rejects {scrap}% of all stamped parts. The maintenance crew has {distract} technicians. "
                    f"Assuming the reject rate divides evenly, how many GOOD parts ship per day?"),
            answer=good_per_day, answer_type="number"))
    for i in range(2):  # template B: rate/meeting with unit trap (minutes vs hours)
        d, va, vb, head = rng.choice([360, 420, 480, 540]), rng.randint(40, 60), rng.randint(60, 80), rng.randint(20, 45)
        t_min = round(d / (va + vb) * 60)
        out.append(dict(
            id=f"quant-b{i+1}", family="quant",
            prompt=(f"Two service vans start {d} km apart and drive toward each other, one at {va} km/h, the other at {vb} km/h. "
                    f"The dispatcher's briefing took {head} minutes before either van moved (it does not count as driving time). "
                    f"How many MINUTES of driving until they meet? Round to the nearest minute."),
            answer=t_min, answer_type="number"))
    for i in range(2):  # template C: tiered billing with threshold
        base, inc1, p1, p2, use = rng.choice([35, 45, 55]), rng.choice([100, 150, 200]), rng.randint(12, 18), rng.randint(22, 30), rng.randint(260, 480)
        cost = base * 100 + min(use, inc1) * p1 + max(0, use - inc1) * p2  # cents
        out.append(dict(
            id=f"quant-c{i+1}", family="quant",
            prompt=(f"A metered plan costs ${base} flat, plus {p1} cents per unit for the first {inc1} units, "
                    f"plus {p2} cents for each unit beyond {inc1}. A customer used {use} units. "
                    f"What is the total bill in CENTS (a whole number)?"),
            answer=cost, answer_type="number"))
    return out

def _gen_logic(rng):
    people, colors, drinks = ["Ava", "Ben", "Cy", "Dee"], ["red", "blue", "green", "gold"], ["tea", "coffee", "cocoa", "juice"]
    out = []
    for i in range(4):
        col = colors[:]; dr = drinks[:]
        rng.shuffle(col); rng.shuffle(dr)
        truth = {p: (c, d) for p, c, d in zip(people, col, dr)}
        pool = []
        for p in people:
            pool.append(("has_col", p, truth[p][0]))
            pool.append(("col_dr", truth[p][0], truth[p][1]))
            for c in colors:
                if c != truth[p][0]: pool.append(("not_col", p, c))
            for d in drinks:
                if d != truth[p][1]: pool.append(("not_dr", p, d))
        def consistent(assign_c, assign_d, clue):
            k, a, b = clue
            m = {p: (assign_c[j], assign_d[j]) for j, p in enumerate(people)}
            if k == "has_col": return m[a][0] == b
            if k == "not_col": return m[a][0] != b
            if k == "not_dr":  return m[a][1] != b
            if k == "col_dr":  return all((c0 != a or d0 == b) for c0, d0 in m.values())
            raise ValueError(k)
        def n_solutions(clues):
            n = 0
            for pc in itertools.permutations(colors):
                for pd in itertools.permutations(drinks):
                    if all(consistent(pc, pd, cl) for cl in clues): n += 1
            return n
        clues = None
        for _ in range(50):                       # greedy: keep a clue only if it prunes solutions
            order = rng.sample(pool, len(pool)); sel = []; n = None
            for cl in order:
                sel.append(cl)
                n2 = n_solutions(sel)
                if n is not None and n2 >= n: sel.pop(); continue
                n = n2
                if n == 1: break
            if n == 1: clues = sel; break
        assert clues, "no unique clue set found"
        target = rng.choice(people)
        text = {"has_col": "{}'s badge is {}.", "not_col": "{}'s badge is not {}.",
                "not_dr": "{} does not drink {}.", "col_dr": "The person with the {} badge drinks {}."}
        clue_lines = "\n".join("- " + text[k].format(a, b) for k, a, b in clues)
        out.append(dict(
            id=f"logic-{i+1}", family="logic",
            prompt=(f"Four technicians (Ava, Ben, Cy, Dee) each have one badge color ({', '.join(colors)}) "
                    f"and one drink ({', '.join(drinks)}); no two share a color or a drink.\n{clue_lines}\n"
                    f"Exactly one assignment satisfies all clues. What does {target} drink?"),
            answer=truth[target][1], answer_type="string"))
    return out

def _gen_math(rng):
    out = []
    n, a, b = rng.choice([900, 1200, 1500]), rng.choice([6, 8]), rng.choice([10, 15, 21])
    cnt = sum(1 for x in range(1, n + 1) if (x % a == 0) ^ (x % b == 0))
    out.append(dict(id="math-1", family="math",
                    prompt=f"How many integers from 1 to {n} inclusive are divisible by {a} or {b} but NOT both?",
                    answer=cnt, answer_type="number"))
    base, exp = rng.choice([3, 7, 9, 13]), rng.randint(180, 420)
    out.append(dict(id="math-2", family="math",
                    prompt=f"What are the last two decimal digits of {base}^{exp}? Give them as a number (0-99).",
                    answer=pow(base, exp, 100), answer_type="number"))
    f = rng.choice([180, 230, 290, 350])
    tz = 0; k = 5
    while k <= f: tz += f // k; k *= 5
    out.append(dict(id="math-3", family="math",
                    prompt=f"How many trailing zeros does {f}! (factorial of {f}) have?",
                    answer=tz, answer_type="number"))
    m1, m2 = rng.choice([(7, 11), (9, 13), (11, 13)])
    r1, r2 = rng.randrange(m1), rng.randrange(m2)
    x = next(x for x in range(m1 * m2) if x % m1 == r1 and x % m2 == r2)
    out.append(dict(id="math-4", family="math",
                    prompt=f"Find the smallest non-negative integer x with x mod {m1} = {r1} and x mod {m2} = {r2}.",
                    answer=x, answer_type="number"))
    nn = rng.choice([6, 7])
    der = round(math.factorial(nn) / math.e)
    out.append(dict(id="math-5", family="math",
                    prompt=(f"{nn} test reports are returned randomly, one to each of {nn} engineers. "
                            f"In how many ways can they be returned so that NO engineer gets their own report (derangements of {nn})?"),
                    answer=der, answer_type="number"))
    return out

def _gen_code(rng):
    snippets = [
        ("code-1", "def f(x, acc=[]):\n    acc.append(x)\n    return len(acc)\nprint(f(1) + f(2) + f(3))"),
        ("code-2", "fs = [lambda: i * j for i in range(3) for j in range(2)]\nprint(sum(f() for f in fs))"),
        ("code-3", "a = [-7, 8]\nprint(a[0] // 3, a[0] % 3, -8 // a[1])"),
        ("code-4", "x = [[0] * 2] * 3\nx[0][1] = 5\ny = x[1][:]\ny[0] = 9\nprint(x[2][1], x[1][0], sum(y))"),
        ("code-5", "d = {k % 3: k for k in range(7)}\nprint(d.get(0, -1) + d.get(3, 10) + len(d))"),
    ]
    out = []
    for sid, src in snippets:
        out.append(dict(id=sid, family="code",
                        prompt=("A Python 3 program:\n```python\n" + src + "\n```\n"
                                "What exactly does it print (the single output line, verbatim)?"),
                        answer=_exec_gold(src), answer_type="string"))
    return out

def _gen_domain(rng):
    out = []
    r1, r2, rl, vin = rng.choice([4700, 6800, 10000]), rng.choice([1000, 2200, 3300]), 10000, rng.choice([12.0, 24.0])
    r2p = r2 * rl / (r2 + rl)
    vout = vin * r2p / (r1 + r2p)
    out.append(dict(id="dom-1", family="domain", tolerance=0.01,
                    prompt=(f"A divider from {vin:.0f} V uses R1={r1} ohm (top) and R2={r2} ohm (bottom). An ADC input of "
                            f"{rl} ohm loads R2 in parallel. What is the loaded output voltage in volts? Three significant figures."),
                    answer=round(vout, 3), answer_type="number"))
    mohm_cm, L, I = rng.choice([1.2, 1.9, 2.6]), rng.choice([8, 12, 15]), rng.choice([3.0, 4.5, 6.0])
    p_mw = I * I * (mohm_cm * L)
    out.append(dict(id="dom-2", family="domain", tolerance=0.01,
                    prompt=(f"A PCB power trace has resistance {mohm_cm} milliohm per cm and runs {L} cm, carrying a steady {I} A. "
                            f"How much power does the trace dissipate, in MILLIWATTS?"),
                    answer=round(p_mw, 2), answer_type="number"))
    rr, cc, vs, vth = rng.choice([10, 22, 47]), rng.choice([1.0, 2.2, 4.7]), 5.0, rng.choice([3.0, 3.3])
    t_ms = -(rr * 1000) * (cc * 1e-6) * math.log(1 - vth / vs) * 1000
    out.append(dict(id="dom-3", family="domain", tolerance=0.01,
                    prompt=(f"An RC charges from 0 V toward {vs:.0f} V through R={rr} kilo-ohm into C={cc} microfarad. "
                            f"After how many MILLISECONDS does the capacitor first reach {vth} V? Three significant figures."),
                    answer=round(t_ms, 3), answer_type="number"))
    vref, tol = rng.choice([2.5, 3.0]), 0.01
    vmin = vref * ((1 - tol) / ((1 - tol) + (1 + tol)))  # equal nominal R, worst-case min at the divider midpoint
    out.append(dict(id="dom-4", family="domain", tolerance=0.01,
                    prompt=(f"A midpoint divider from {vref} V uses two EQUAL nominal resistors with +/-1% tolerance. "
                            f"What is the WORST-CASE MINIMUM midpoint voltage in volts? Four significant figures."),
                    answer=round(vmin, 4), answer_type="number"))
    return out

# ------------------------------------------------- workload suite (the actual seats)
VERDICT_RULES = ("Pipeline policy, apply the FIRST matching rule:\n"
                 "1. ESCALATE if any hard-check failed in both of the last two iterations, "
                 "OR the DRC error count increased versus the previous iteration, "
                 "OR iteration >= 8 with any violation remaining.\n"
                 "2. REPAIR if violations remain and every failing metric improved versus the previous iteration.\n"
                 "3. ACCEPT if there are zero DRC errors and every hard-check passes.")

def _gen_verdict(rng):
    def state(it, drc_prev, drc_now, hc):
        return json.dumps({"iteration": it, "drc_errors_prev_iter": drc_prev, "drc_errors_now": drc_now,
                           "hard_checks": {k: {"prev_iter": "PASS" if a else "FAIL", "now": "PASS" if b else "FAIL"}
                                           for k, (a, b) in hc.items()}}, indent=1)
    cases = [
        ("accept",   state(rng.randint(2, 5), rng.randint(1, 4), 0, {"clearance": (True, True), "current_density": (True, True), "thermal": (True, True)})),
        ("repair",   state(rng.randint(2, 5), 9, 4, {"clearance": (True, True), "current_density": (True, True), "thermal": (True, True)})),
        ("escalate", state(rng.randint(2, 5), 3, 7, {"clearance": (True, True), "current_density": (True, True), "thermal": (True, True)})),
        ("escalate", state(rng.randint(2, 5), 6, 2, {"clearance": (False, False), "current_density": (True, True), "thermal": (True, True)})),
    ]
    rng.shuffle(cases)
    return [dict(id=f"verdict-{i+1}", family="verdict",
                 prompt=(f"You are the routing-pipeline manager. {VERDICT_RULES}\n\nCurrent state:\n{st}\n\n"
                         f"Which action does the policy require?"),
                 answer=gold, answer_type="string")
            for i, (gold, st) in enumerate(cases)]

_TRACES = [
    ("finding", "exceeds the 3 A per-via budget",
     "Analyst trace T-101: Reviewed the 12 V return path on the interposer rev C. Plane stitching on the left edge "
     "is dense and well distributed. Sense divider values at U7 match the schematic (49.9k/10k). However, the "
     "return lane between L2 and L4 funnels through a single 0.5 mm via near the connector keep-out; at the rated "
     "7 A load this exceeds the 3 A per-via budget by a wide margin. Decoupling placement near U3 is nominal. "
     "Thermal camera spot-checks at 60% load showed no anomalies elsewhere."),
    ("pass", None,
     "Analyst trace T-102: Full audit of the hub-standard sense network. The divider at U2 reads 49.9k over 10k, "
     "matching the corrected schematic. ADC reference is buffered, and the feedback trace is routed away from the "
     "switching node with a solid ground pour beneath. DRC reports zero violations after the rework. Current "
     "density on every supply lane stays under half of budget at worst-case load. No further issues identified; "
     "the board meets all checked criteria."),
    ("no-conclusion", None,
     "Analyst trace T-103: Began the electrothermal sweep on the 12VHPWR module. Captured baseline copper "
     "temperatures at 25%, 50% and 75% load steps; data logged to runs/th-0312. The 100% load step and the "
     "post-soak DRC re-check were still queued when the session was terminated by a host reboot. No verdict was "
     "recorded for the remaining steps and the partial data has not been reviewed."),
    ("finding", "solder mask web between the pads is below the 0.2 mm minimum",
     "Analyst trace T-104: Re-examined the connector footprint. An earlier report claimed the sense divider was "
     "misvalued, but that claim was RETRACTED after re-measurement confirmed 49.9k/10k as designed. Separately, "
     "the fab notes flag that the solder mask web between the pads is below the 0.2 mm minimum on pins 9-12, "
     "which the assembler lists as a bridging risk at reflow. All other footprint checks pass."),
]

def _gen_extract(rng):
    out = []
    for i, (gold, must, trace) in enumerate(_TRACES):
        out.append(dict(
            id=f"extract-{i+1}", family="extract", answer=gold, answer_type="verdict_span",
            trace=trace, span_required=(gold == "finding"), span_must_contain=must,
            prompt=(f"You are the verdict extractor. Read the analyst trace and report what IT concludes -- do not "
                    f"add conclusions of your own, and do not report claims the trace retracts. If the trace ends "
                    f"without reaching a conclusion, the verdict is no-conclusion.\n\n{trace}\n\n"
                    f'Reply with: ANSWER: <pass|finding|no-conclusion> | "<one verbatim supporting quote copied '
                    f'exactly from the trace>" (the quote is required only for a finding).')))
    return out

TRIAGE_RULES = ("Taxonomy -- category: hardware|firmware|network|data. "
                "Severity: critical if safety risk or >100 devices down; high if ongoing production data loss; "
                "medium if degraded with a workaround; low otherwise. "
                "Action: rma for a confirmed hardware fault; firmware-rollback if the issue began immediately after "
                "an update and persists across reboot; config-fix when a settings mismatch is identified; "
                "remote-diagnostic when the cause is unknown; escalate-engineering for a reproducible product-wide defect.")

def _gen_triage(rng):
    tickets = [
        ("hardware|medium|rma",
         "Ticket S-2201: Single CEC telemetry node reports 12 V rail sag under load. On-site tech swapped the PSU "
         "and the sag followed the unit, not the site; bench test confirms a failing buck stage on the carrier "
         "board. Customer runs duplicate nodes, so monitoring continues on the twin while this unit is out."),
        ("firmware|high|firmware-rollback",
         "Ticket S-2202: Fleet site reports 14 of 40 gateways stopped logging flow-meter data right after last "
         "night's 3.2.1 firmware push. Power-cycling does not restore logging. Data for those meters is being "
         "lost continuously. The 26 gateways still on 3.2.0 log normally."),
        ("network|low|config-fix",
         "Ticket S-2203: One depot's dashboard shows a single node as offline, but the node's local display shows "
         "normal operation and local logging is intact. Site IT confirms they changed the VLAN last week and the "
         "node still has the old gateway address configured. No data loss: local buffer is uploading via cellular fallback."),
        ("data|critical|escalate-engineering",
         "Ticket S-2204: Three separate customers (300+ devices total) report the same defect: energy totals "
         "double-count whenever a meter rolls over 999999 kWh. Reproduced in the lab on current firmware AND two "
         "prior versions. Billing exports are affected at all sites; one customer flagged invoices already sent."),
    ]
    rng.shuffle(tickets)
    return [dict(id=f"triage-{i+1}", family="triage", answer=gold, answer_type="string",
                 prompt=(f"You are the AutoDiagnoser triage stage. {TRIAGE_RULES}\n\n{txt}\n\n"
                         f"Classify this ticket. Reply with: ANSWER: category|severity|action"))
            for i, (gold, txt) in enumerate(tickets)]

def _gen_routecalc(rng):
    out = []
    i_tot, i_via, derate = rng.choice([24, 27, 33]), 3.0, rng.choice([0.6, 0.7])
    n_vias = math.ceil(i_tot / (i_via * derate))
    out.append(dict(id="route-1", family="routecalc", answer=n_vias, answer_type="number",
                    prompt=(f"A stitching array must carry {i_tot} A between layers. Each via is rated {i_via:.0f} A, "
                            f"derated to {int(derate*100)}% of rating for reliability. What is the minimum WHOLE "
                            f"number of vias required?")))
    W, w, c = rng.choice([16, 18, 22]), rng.choice([1.0, 1.2]), 0.8
    n = 0
    while (n + 1) * w + n * c + 2 * c <= W: n += 1
    out.append(dict(id="route-2", family="routecalc", answer=n, answer_type="number",
                    prompt=(f"A routing channel is {W} mm wide. Traces are {w} mm wide and need {c} mm clearance "
                            f"between adjacent traces AND {c} mm to each channel edge. What is the maximum number "
                            f"of traces that fit?")))
    nv, r_via, i_l = rng.choice([4, 6]), rng.choice([1.5, 1.8]), rng.choice([10, 12])
    p_mw = round((i_l ** 2) * (r_via / nv), 2)
    out.append(dict(id="route-3", family="routecalc", answer=p_mw, answer_type="number", tolerance=0.01,
                    prompt=(f"{nv} identical vias of {r_via} milliohm each share a lane current of {i_l} A equally "
                            f"(parallel array). How much power does the ARRAY dissipate, in MILLIWATTS?")))
    return out

def gen_tasks(check=False, suite="general"):
    rng = random.Random(SEED)
    if suite == "workload":
        tasks = _gen_verdict(rng) + _gen_extract(rng) + _gen_triage(rng) + _gen_routecalc(rng)
    else:
        tasks = _gen_quant(rng) + _gen_logic(rng) + _gen_math(rng) + _gen_code(rng) + _gen_domain(rng)
    path = suite_path(suite)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"seed": SEED, "version": SUITES[suite][0].replace("tasks-", "").replace(".json", ""), "tasks": tasks}, fh, indent=1)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    print(f"wrote {len(tasks)} tasks -> {path} (sha {sha})")
    if check:
        fams = {}
        for t in tasks: fams[t["family"]] = fams.get(t["family"], 0) + 1
        print("families:", fams, "| all golds non-empty:", all(str(t["answer"]) != "" for t in tasks))
    return tasks

# ---------------------------------------------------------------- model calls
def call_model(model, prompt, max_tokens=None):
    temp, pp = FLOORS.get(model, (DEFAULT_TEMP, None))
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": temp, "max_tokens": max_tokens or MAX_TOKENS.get(model, DEFAULT_MAX_TOKENS)}
    if pp: payload["presence_penalty"] = pp
    req = urllib.request.Request(BROKER + "/chat/completions", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json", "X-CEC-Client": CLIENT})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=TIMEOUT))
    dt = time.time() - t0
    msg = r["choices"][0]["message"]
    return {"content": msg.get("content") or "", "reasoning": msg.get("reasoning_content") or "",
            "elapsed_s": round(dt, 2), "completion_tokens": (r.get("usage") or {}).get("completion_tokens"),
            "tok_s": (r.get("timings") or {}).get("predicted_per_second")}

def probe_host_gated(model):
    """Reachability pre-check for host-side entries -- read /broker/models, GET its
    health URL directly with a 2s timeout. Never asks the broker to start it."""
    try:
        reg = json.load(urllib.request.urlopen(BROKER.rsplit("/v1", 1)[0] + "/broker/models", timeout=5))
        up = reg["models"][model]["upstream"]
        health = up.rsplit("/v1", 1)[0] + "/health"
        with urllib.request.urlopen(health, timeout=2) as h:
            return h.status == 200
    except Exception:
        return False

# ---------------------------------------------------------------- grading
def extract_answer(text, want_pipe=False):
    hits = ANSWER_RE.findall(text or "")
    if not hits: return None
    if want_pipe:  # models often restate a bare "ANSWER: <verdict>" after the full payload
        piped = [h for h in hits if "|" in h]
        if piped: return piped[-1].strip()
    return hits[-1].strip()

def grade(task, raw):
    if raw is None: return False
    if task["answer_type"] == "number":
        m = re.search(r"-?\d[\d,]*\.?\d*", raw.replace(",", ""))
        if not m: return False
        try: val = float(m.group(0))
        except ValueError: return False
        gold = float(task["answer"])
        tol = task.get("tolerance")
        return math.isclose(val, gold, rel_tol=tol) if tol else math.isclose(val, gold, rel_tol=1e-9)
    if task["answer_type"] == "verdict_span":
        # CL-19 zero-tolerance style: verdict must match AND the cited span must be a
        # VERBATIM substring of the trace (and contain the key phrase when required).
        parts = raw.split("|", 1)
        if parts[0].strip().strip('."').casefold() != str(task["answer"]).casefold(): return False
        if not task.get("span_required"): return True
        if len(parts) < 2: return False
        span = parts[1].strip().strip('"').strip()
        norm = lambda s: " ".join(s.split()).casefold()
        if len(span) < 15 or norm(span) not in norm(task["trace"]): return False
        mc = task.get("span_must_contain")
        return (not mc) or mc.casefold() in span.casefold()
    gold = str(task["answer"]).strip().casefold()
    got = raw.strip().strip(".\"'").casefold()
    if "|" in gold:                      # enum-tuple answers: ignore spacing around pipes
        squash = lambda s: re.sub(r"\s*\|\s*", "|", s)
        return squash(got) == squash(gold)
    return got == gold

# ---------------------------------------------------------------- run / report
def warmup(model, tries=3):
    """Absorb cold starts: a worker cold-load over 9p can exceed the broker's
    start_timeout (ensure-failed), so retry the cheap ping across ensure windows
    instead of sacrificing real tasks to the cold start."""
    for k in range(tries):
        try:
            call_model(model, "Reply with the single word OK.", max_tokens=2000)
            return True
        except Exception as e:
            print(f"  warmup {k+1}/{tries} failed ({str(e)[:80]}) -- retrying", flush=True)
    return False

def run_model(model, tasks, tag, transcript, tpath=None):
    tpath = tpath or TASKS_PATH
    if not warmup(model):
        print(f"{model}: START-FAILED after warmup retries -- skipping its tasks", flush=True)
        return dict(model=model, skipped="start-failed after warmup retries")
    rows, strict, mined_ok, overruns = [], 0, 0, 0
    for t in tasks:
        try:
            res = call_model(model, t["prompt"] + SUFFIX)
        except Exception as e:
            rows.append(dict(id=t["id"], status="error", error=str(e)[:200]))
            print(f"  {t['id']:<10} ERROR    {str(e)[:90]}", flush=True); continue
        ans = extract_answer(res["content"], t["answer_type"] == "verdict_span")
        status, ok = "answered", grade(t, ans)
        mined = None
        if not res["content"].strip() and res["reasoning"]:
            status = "overrun"; overruns += 1
            mined = extract_answer(res["reasoning"][-2000:], t["answer_type"] == "verdict_span")
            if grade(t, mined): mined_ok += 1
        elif ok:
            mined_ok += 1                      # strict pass counts for mined too
        strict += 1 if ok else 0
        rows.append(dict(id=t["id"], family=t["family"], status=status, ok=ok,
                         answer=ans, mined_answer=mined, gold=str(t["answer"]),
                         elapsed_s=res["elapsed_s"], tok_s=res["tok_s"],
                         completion_tokens=res["completion_tokens"]))
        # full content AND full reasoning kept on purpose: the live-viewer TODO below
        # ("show me the thinking as it happens") needs complete streams, and local JSONL is cheap.
        transcript.write(json.dumps(dict(ts=round(time.time(), 2), model=model, task=t["id"],
                                         prompt=t["prompt"], content=res["content"], reasoning=res["reasoning"],
                                         **{k: res[k] for k in ("elapsed_s", "tok_s", "completion_tokens")})) + "\n")
        transcript.flush()
        print(f"  {t['id']:<10} {'PASS' if ok else status.upper():<8} {res['elapsed_s']:>7.1f}s  ans={str(ans)[:40]!r} gold={str(t['answer'])[:30]!r}", flush=True)
    toks = [r["tok_s"] for r in rows if r.get("tok_s")]
    summary = dict(model=model, n=len(tasks), strict=strict, mined=mined_ok, overruns=overruns,
                   errors=sum(1 for r in rows if r["status"] == "error"),
                   avg_tok_s=round(sum(toks) / len(toks), 2) if toks else None,
                   total_s=round(sum(r.get("elapsed_s", 0) for r in rows), 1))
    path = os.path.join(OUT_DIR, f"results-{model}{tag}.json")
    with open(path, "w") as fh:
        json.dump(dict(summary=summary, rows=rows, tasks_sha=tasks_sha(tpath), broker=BROKER), fh, indent=1)
    print(f"{model}: strict {strict}/{len(tasks)}  mined {mined_ok}  overruns {overruns}  -> {path}", flush=True)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import cec_ledger
        cec_ledger.append(board="reasoning-bakeoff", mode="eval",
                          verdict=f"{model} strict {strict}/{len(tasks)}",
                          extra=dict(tag=tag, tasks_sha=tasks_sha(tpath),
                                     report=os.path.relpath(path, ROOT), **summary))
    except Exception as e:
        print("ledger append skipped: %s" % e, file=sys.stderr)
    return summary

def tasks_sha(path=None):
    return hashlib.sha256(open(path or TASKS_PATH, "rb").read()).hexdigest()[:16]

def cmd_run(models, tag, limit, suite="general"):
    tpath = suite_path(suite)
    tasks = json.load(open(tpath))["tasks"][:limit or None]
    os.makedirs(OUT_DIR, exist_ok=True)
    summaries = []
    with open(os.path.join(OUT_DIR, f"transcript{tag}.jsonl"), "a") as transcript:
        for m in models:
            print(f"\n=== {m} ({len(tasks)} tasks) ===", flush=True)
            if m in HOST_GATED and not probe_host_gated(m):
                print(f"{m}: SKIPPED -- host-side upstream unreachable from WSL "
                      f"(pending E:\\toolchain\\fix-firewall.bat)", flush=True)
                summaries.append(dict(model=m, skipped="host unreachable")); continue
            summaries.append(run_model(m, tasks, tag, transcript, tpath))
    print("\n" + scoreboard(summaries))

def scoreboard(summaries):
    lines = [f"{'model':<28} {'strict':>7} {'mined':>6} {'overrun':>8} {'avg tok/s':>10} {'total s':>9}"]
    for s in summaries:
        if s.get("skipped"):
            lines.append(f"{s['model']:<28} {'SKIP -- ' + s['skipped']}")
        else:
            lines.append(f"{s['model']:<28} {s['strict']:>4}/{s['n']:<3} {s['mined']:>5} {s['overruns']:>8} "
                         f"{str(s['avg_tok_s']):>10} {s['total_s']:>9}")
    return "\n".join(lines)

def cmd_regrade(tag, suite):
    """Re-score a finished run from its stored FULL transcripts with the current
    grader -- fixes grader bugs retroactively and uniformly, no model re-runs."""
    tpath = suite_path(suite)
    tasks = {t["id"]: t for t in json.load(open(tpath))["tasks"]}
    tpn = os.path.join(OUT_DIR, f"transcript{tag}.jsonl")
    latest = {}
    for L in open(tpn):
        r = json.loads(L)
        if r["task"] in tasks: latest[(r["model"], r["task"])] = r   # keep last per pair
    by_model = {}
    for (m, tid), r in latest.items(): by_model.setdefault(m, {})[tid] = r
    summaries = []
    for m, calls in sorted(by_model.items()):
        rows, strict, mined_ok, overruns = [], 0, 0, 0
        for tid, t in tasks.items():
            r = calls.get(tid)
            if not r: rows.append(dict(id=tid, status="missing")); continue
            ans = extract_answer(r["content"], t["answer_type"] == "verdict_span")
            ok = grade(t, ans); status, mined = "answered", None
            if not (r["content"] or "").strip() and r.get("reasoning"):
                status = "overrun"; overruns += 1
                mined = extract_answer(r["reasoning"][-2000:], t["answer_type"] == "verdict_span")
                if grade(t, mined): mined_ok += 1
            elif ok: mined_ok += 1
            strict += 1 if ok else 0
            rows.append(dict(id=tid, family=t["family"], status=status, ok=ok, answer=ans,
                             mined_answer=mined, gold=str(t["answer"]),
                             elapsed_s=r.get("elapsed_s"), tok_s=r.get("tok_s"),
                             completion_tokens=r.get("completion_tokens")))
        toks = [x["tok_s"] for x in rows if x.get("tok_s")]
        summary = dict(model=m, n=len(tasks), strict=strict, mined=mined_ok, overruns=overruns,
                       errors=sum(1 for x in rows if x["status"] == "missing"),
                       avg_tok_s=round(sum(toks) / len(toks), 2) if toks else None,
                       total_s=round(sum(x.get("elapsed_s") or 0 for x in rows), 1))
        out = os.path.join(OUT_DIR, f"results-{m}{tag}.json")
        with open(out, "w") as fh:
            json.dump(dict(summary=summary, rows=rows, tasks_sha=tasks_sha(tpath),
                           broker=BROKER, regraded=True), fh, indent=1)
        summaries.append(summary)
    print(scoreboard(summaries))

def cmd_report(tag):
    summaries = []
    for fn in sorted(os.listdir(OUT_DIR)):
        if fn.startswith("results-") and fn.endswith(f"{tag}.json"):
            summaries.append(json.load(open(os.path.join(OUT_DIR, fn)))["summary"])
    print(scoreboard(summaries) if summaries else f"no results matching tag {tag!r} in {OUT_DIR}")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen"); g.add_argument("--check", action="store_true")
    g.add_argument("--suite", default="general", choices=sorted(SUITES))
    r = sub.add_parser("run")
    r.add_argument("--models", default=",".join(DEFAULT_MODELS))
    r.add_argument("--suite", default="general", choices=sorted(SUITES))
    r.add_argument("--tag", default=None, help="use --tag=-x form (leading dash); default = suite tag")
    r.add_argument("--limit", type=int)
    sub.add_parser("smoke")
    p = sub.add_parser("report"); p.add_argument("--tag", default="-v1")
    rg = sub.add_parser("regrade")
    rg.add_argument("--suite", default="general", choices=sorted(SUITES))
    rg.add_argument("--tag", default=None)
    a = ap.parse_args()
    if a.cmd == "gen": gen_tasks(check=a.check, suite=a.suite)
    elif a.cmd == "smoke": cmd_run(["cec-worker"], "-smoke", 2)
    elif a.cmd == "run":
        models = ALL_MODELS if a.models == "all" else [m.strip() for m in a.models.split(",") if m.strip()]
        cmd_run(models, a.tag or SUITES[a.suite][1], a.limit, suite=a.suite)
    elif a.cmd == "regrade": cmd_regrade(a.tag or SUITES[a.suite][1], a.suite)
    else: cmd_report(a.tag)

if __name__ == "__main__":
    main()
