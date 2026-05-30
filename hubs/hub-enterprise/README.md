# Hub Enterprise

Tier 3 of 4. **Platform-summary level only** for now — full specification is
deferred until first customer requirements land (**OQ-7**). Do not begin detailed
design here without resolving OQ-7.

| Item | Summary-level intent |
|---|---|
| Tier | 3 of 4 |
| MCU | ESP32-P4 + secure element |
| Host link | USB High Speed (+ optional 1000BASE-T1) |
| Distinguishing hardware | RJ-11 trust channel, secure element |
| Connector (module side) | RJ-45 8P8C, locking boot (universal interface) |
| BOM target | ~$50 (100-qty) |

Builds on one fundamental design with progressively populated features; inherits
the universal RJ-45 interface and the Hub Pro base. See spec
[§1](../../CEC-Platform-Ground-Truth-Spec.md) and **OQ-7**.

## Status

No KiCad project yet — intentionally. This directory is a placeholder pending
the OQ-7 decision on whether to fully specify Enterprise now.
