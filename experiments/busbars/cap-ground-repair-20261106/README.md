# Existing capacitor Ground-via correction

Private ATX candidate `1512d4f046daebaba629ac29db4bc5caf2d53bc6ccf370e44deb903c4259b045`
repairs a genuine partial-overlap via-in-pad defect missed by ordinary native DRC.
The existing C54 Ground via moves 0.10 mm to the pad center. Its UUID,
0.50/0.30 mm diameter/drill, lock, layer stack and process remain unchanged.
Every other native board node and project sidecar is literal-identical.

`slice-closeout.json` joins fresh independent evidence from `checks-final/`
and the sharded `sense-shards/` replay. The result is still **0 opens,
0 native DRC errors and 94 warnings**. All 16 clipped force/sense legs,
Ground returns, current-check findings, pair and field-coupling findings
are preserved. Existing current-model findings are not waived or qualified.

The complete native receipts are stored in `native-check-evidence.tar.gz`
instead of adding roughly 440,000 repeated JSON lines to the source diff.
Its SHA-256 is `9f31da7883263625a76cc5c95e2bf4af1d9894e53b92cec9f55643dbb8d94c32`.
The archive was compared against every original file. To restore the exact
relative paths before replaying `close_slice.py`, run in this directory:

```sh
tar -xzf native-check-evidence.tar.gz
```

No original local evidence was deleted. Each independent receipt's hash is
also bound in `slice-closeout.json`; the archive does not replace those checks.

The generic implementation is `scripts/cec_source_cap_ground_via_repair.py`.
It distinguishes explicit source overlap debt from positive in-pad ownership;
requires canonical capacitor identity and exclusive native pad/plane contacts;
independently reconstructs the exact saved change; refuses unknown nearby fills;
and preserves every original connectivity partition. It grants no authority to
change the via size, add barrels, retire copper or relax manufacturing rules.

The root regression replay passed 138 cases, including the initial 27 repair tests.
Expanded repair-only replay passed 34 cases, including full-fixture translations
and quarter-turns plus quoted-string and trailing-junk checks: 145 unique passing
cases across both replays (172 executions, not 172 unique tests).
Native check constituents are externally limited to 10 seconds. The receiver
does one independent refill and full-root lexical comparison, avoiding a
redundant second refill without normalizing unrelated source data.

`native-via-before-after.png` shows actual saved native pad, via and drill geometry.
No bus bar, component movement, new X/Y compaction, assembled-Z qualification
or fabrication release is claimed. The previously received VBUS shortening is
retained. Canonical boards and the reviewed selector remain unchanged.
