# Accepted-prefix seven-part native study

All evidence binds ATX source SHA256 `c4c92165a0e8efec60458b91af80807233033bb5668ade92f171cdacb4ce0b88`.
The older 1512 study supplies target poses only, never current-source evidence.
No PCB is saved, source conductor is cut, or transport permission inferred.

Run each constituent separately, with its existing 10-second native limit:

```
timeout 10s /usr/bin/python3 experiments/busbars/mux-role-contact-20261106/native_seven_study.py geometry
timeout 10s /usr/bin/python3 experiments/busbars/mux-role-contact-20261106/native_seven_study.py contacts
timeout 10s /usr/bin/python3 experiments/busbars/mux-role-contact-20261106/native_seven_study.py landings
```

`geometry.json`: exact native courtyard polygons and pad identities for the fixed seven poses; no same-face courtyard collision; paired Hub/vent screen passes. Hub and stack hashes are bound independently. This is physical placement screening, not rerouted copper acceptance.

`contacts.json`: all 24 original native pad contact inventories, 14 barrels reached by actual direct pad or pad-incident-track contact, every original all-layer barrel contact, locks/groups, non-Ground net terminals and external anchors. Polygon areas and SHA256 identities retain reproducibility without repeating large native polygons. Native contact association does not establish exclusive transport ownership.

`landings.json`: all 50 moved-pad/retained-foreign-copper clearance conflicts (39 track and 11 barrel incidences); two factory-size .5/.3 Ground seat probes pass actual pad-process and all-layer 0.2-mm spot checks on the unchanged source copper:

- C54 Ground center `(18.924990,48.610000)`.
- C55 contained off-center seat `(20.500000,50.540000)`; c4's received output-prefix reflow removes the former diagonal conflict.

Ten associated barrels have the same diagnostic +2-mm X projection with their source pad owner: C9 Ground 6ac2229b, C27 Ground 6e5c4098, OUT 6cd5980a, R54 ILM 442d8b20, R54 Ground 8a1767d2, U6 Ground 72f21f4f and c37ec792, OV1 022ac0d2, PR1 29c6dd22 and ILM 64b46a25. Every original nonplane contact in the ledger remains a reconstruction obligation; shared OUT/ILM branches cannot be dropped.

Exceptions to rigid transport:

- C54 c25714c1 is now truly source-Ground-pad centered. Its rigid projected axis is the proposed C54 seat; its original nonplane contact is that Ground land only, plus two saved Ground planes.
- C55 old 8fcb6331 and e0bcdb19 form the original 1.35-mm Ground tail. Rigid motion preserves that failed immediate-return length. The proposed off-center pad seat is a different reconstruction requiring positive old leaf/barrel custody and fresh <=0.8-mm receiving, not a rigid transport claim.
- C51 Ground7f4e567d may remain at original `(17.725,50.125)`; native proposed-pad containment passes. C51 SS d2fedf54 may remain an external control boundary if the old source topology is rebuilt. Its diagnostic rigid projection is not mandatory.

Retaining every original barrel is impossible: c25714c1 overlaps new U6.1/11; 29c6dd22 overlaps U6.3; 6cd5980a overlaps C9.1; 442d8b20 overlaps C9.2; 64b46a25 overlaps C27.1; 022ac0d2 overlaps R54.2. No net-name-based cut permission follows. All source tracks and holes remained present during these observations.
