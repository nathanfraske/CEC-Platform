# Power-regulator vendor models

These files are retained as design inputs for the BETA power-stage audit and
SPICE checks.  Keep the original vendor filenames and do not edit vendor model
contents.

| File | Source | Use |
|---|---|---|
| `TLV62569_TRANS.lib` | Texas Instruments `SLVMBW3A`, unencrypted transient model | 2 A synchronous buck |
| `TLV75533P_TRANS.lib` | Texas Instruments `SBVM831`, unencrypted transient model | fixed 3.3 V post-LDO |
| `VLS252010HBX-2R2M-1.lib` | TDK simple equivalent-circuit parameters, 2019-01-22 | 2.2 uH inductor |

Datasheet copies and source URLs are recorded in
`docs/beta-power-regulator-selection-2026-08-02.md`.
