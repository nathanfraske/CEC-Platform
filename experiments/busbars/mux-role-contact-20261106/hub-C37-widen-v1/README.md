# Private native Hub rail widening — not admitted

Parent: Hub C37-shift-only candidate `4825def1abce879355b751406634f2dc5d552c207c779710b3cd6877ecf05992`; root remains original Hub `c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db`.

Candidate: `a977b5da70742f0e49b28f9a3d7499eb84ab0f9e508ab171d0604c2635832975`.

Only selected existing F.Cu +5V_HOLD zone `fc65fef1-239d-4859-94dd-f827621e549e` changes relative to the parent: its outline is unioned with one circumscribed octilinear capsule corridor, then genuinely native-refilled. No track, via, component, group, other zone, stack dimension or sidecar changes. C37's +0.10 mm Y move already belongs to the parent. Construction radius 501000 nm and octagon diagonal offset 207521 nm conservatively contain the full 1 mm circular-width witness without bubbly caps.

Actual fill added: **6.855771652483865 mm²**. Actual fill removed: **0 mm²**.

Native saved 1 mm corridor: (75.301,37.151) → (75.950,37.800) → (75.950,47.300) → (75.301,47.949), coordinates in mm. For all three legs, exact native full-width capsule subtraction from the saved actual zone fill is empty; foreign copper clearance 0.2 mm, edge and native rule checks pass. These are positive local geometric witnesses, not new authored tracks or global ampacity proof.

Independent saved replay reruns all 52 zones through native priority-settle fill in RAM: two passes stable, all saved fill payloads exactly match, no zone/layer changes, no board re-save. All 94 source physical native components survive, zero demotions. Paired body/vent screen passes with recorded ATX poses; stack hash remains unchanged. Native DRC remains **0 errors / 166 warnings / 0 opens**, with zero added or removed type/severity/item-UUID signatures.

Existing +5V_HOLD authority is the actual `hub-standard-rev2` 0.5 A design basis, margin 1.25, D1 → RJ_HOLD. Effective 1 mm reconstruction floor is preserved. This study does not qualify its entire domain, barrels, cross-face paths or thermal behavior. Inherited source debt and original pose-receiver refusal remain unresolved; no promotion or admission is claimed. A fresh independent exact scoped receiving proof must compose root → C37 pose/refill → widened outline/refill, preserve every original contact and full native partitions, accept no arbitrary zone changes, and retain current/thermal/field/vent-reservation gates. Local capacity proof and unchanged DRC are not substitutes.

Reproduction stages are in `../build_Hub_widen.py`; every native constituent was externally limited to ten seconds. Existing candidates and review boards were not overwritten.
