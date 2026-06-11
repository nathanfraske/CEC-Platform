import json, time, urllib.request

PROMPT = """You are reviewing two autorouted candidates of the same PCB. Raw data only; draw your own conclusions.

BOARD: EPS 8-pin power-telemetry module, 96x37mm, 4 copper layers: F.Cu, an inner layer named "GND" (the board's ground plane layer, carrying a full-board ground plane zone), a second inner layer, B.Cu. Same placement input for both arms; same router (Freerouting 1.7.0, deterministic, passes=12), same keepout/pour machinery. A congestion pre-analysis flagged ~20 mid-board hotspot cells and listed contested nets.

ARM A ("free"): the router routed everything with no additional guidance.
ARM B ("directed"): before routing, 4 contested signal nets were given route intents -- relational waypoints compiled into short (2mm) LOCKED track stubs the router must connect through:
- /I2C_SDA: 2 waypoints, B.Cu, south of the hotspot band
- /I2C_SCL: 2 waypoints, B.Cu, parallel to SDA
- /THRESH: 3 waypoints, F.Cu, south detour
- /DETC2: 2 waypoints, F.Cu, south swing
All 9 stubs survived routing and the routes pass through them.

WHOLE-BOARD METRICS (same scorer, both arms):
ARM A: drc_structural=0, unconnected=32, tracks=397, vias=64, total_length=698.2mm, kelvin_gate=false, diffpair_gate=true, objective=3243.8 (lower=better)
ARM B: drc_structural=9, unconnected=32, tracks=410, vias=70, total_length=771.2mm, kelvin_gate=false, diffpair_gate=true, objective=12246.5

ARM B DRC DETAIL (all 9): type=track_dangling, each a 1.2mm track segment, on: /I2C_SDA x2 (B.Cu), /I2C_SCL x2 (B.Cu), /DETC2 x2 (F.Cu), /THRESH x3 (F.Cu).

PER-NET COPPER, the 4 directed nets (mm of track per layer; vias):
/I2C_SDA  ARM A: F.Cu 8.2, GND-layer 61.7  (total 69.9, 4 vias)   ARM B: F.Cu 8.3, B.Cu 52.5, GND-layer 21.9  (total 82.7, 4 vias)
/I2C_SCL  ARM A: F.Cu 11.0, B.Cu 17.9, GND-layer 45.0 (total 73.9, 4 vias)   ARM B: F.Cu 9.8, B.Cu 33.4, GND-layer 39.2 (total 82.4, 5 vias)
/THRESH   ARM A: F.Cu 1.0 (total 1.0, 0 vias)   ARM B: F.Cu 18.2, GND-layer 19.1 (total 37.3, 2 vias)
/DETC2    ARM A: none (0mm)   ARM B: F.Cu 6.9 (total 6.9, 0 vias)

UNROUTED RATLINES REMAINING on these nets:  ARM A: /THRESH 2, /DETC2 1.   ARM B: /THRESH 3, /DETC2 2.
(The 32 whole-board unconnected in both arms are mostly power/ground finishing items handled by a later stage.)

NET CLASS CONTEXT: /I2C_SDA, /I2C_SCL, /THRESH, /DETC2 are ordinary logic signals. The board's power integrity relies on the GND plane as the return path for all signals.

QUESTIONS:
1. Which arm is the better engineering result, and why? Argue from the data.
2. What stands out in this data that the headline metrics (drc count, length, objective) do not capture?
3. The scorer's objective says ARM A wins by ~4x. Do you agree with the scorer? If not, what is it mispricing?
4. What would you do next, concretely, to this pipeline?
Be specific and quantitative. Conclusions over hedging."""


import sys
sys.path.insert(0, "/tmp")
from v4_judge_lib import judge
judge(PROMPT, "v4-blind-judge", max_tokens=6400)
