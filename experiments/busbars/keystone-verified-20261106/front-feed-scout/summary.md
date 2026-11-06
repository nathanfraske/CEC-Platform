# Bounded inward-front 5104TR feed scout

Source SHA256: `4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310` (verified before and after each run).

Native /SENSE12V_HI pads: J3.10 (22.549999,77.4), J3.11 (18.349999,77.4), U10.10 (48.685001,32.637599), RS1.1 (51.685001,34.400099), U612V1.3 (56.635001,32.575099). One via at (43.20461,38.5582). Front rated-width source copper runs from vicinity (43.4,38.5582) to (51.685001,35.405895). Existing backside feed is retained unchanged.

The visual bottom-bus hypothesis was misidentified: horizontal front bus (20.75,68.15) to (51.6,68.15) is /SENSE5V_HI, not +5V_MAIN. Its zone bounding box spans x16.998..53.301,y50.024..77.903; bounding box is not its exact filled polygon.

Exactly three vertical poses, centered y70.5, x18.35/20.75/24.0, were screened. Feet y65.15/75.85, conservative enlarged 3.5x2.6mm lands, 12.43x2.4384mm body projection. Full 3.230592mm feed and 0.2mm clearance retained.

All three rejected for fixed-placement land/body conflicts. x18.35: upper land intersects /SENSE5V_HI zone; lower land overlaps J3.11 drill, body overlaps J3 courtyard and component keepout. x20.75 adds +5VSB track/via conflicts and J3.10/.11 drills. x24 adds C25 courtyard/pads, +5V_SYS/GND vias, +5VSB zone, and J3.9/.10 conflicts. Details in case-0/1/2.json.

Source-to-upper-foot guarded link not found for all three; native endpoint-cap rejection prevents lattice search, so this is not a global no-path proof. Lower-foot-to-J3.11 full-width links found at x18.35 and x20.75 only; these do not override landing/drill/body rejection. No broad sweep, displacement, copper removal, added via, synthetic conductor, saved board or canonical edit. This preview does not qualify underside clearance, current, thermal performance, assembly Z or release.
