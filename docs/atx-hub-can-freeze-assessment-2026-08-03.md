# ATX / Hub CAN and FREEZE assessment — 2026-08-03

Status: analysis only. No CAN, STREAM, or FREEZE electrical/firmware change is
authorized or made by this assessment.

## Current dependency

The Standard control plane is not using CAN only as a one-bit shutdown wire.
It currently carries:

- module telemetry and anomaly reports;
- commands and responses;
- application-level CAN OTA;
- DETECT poke-and-ack identity-to-physical-port binding; and
- the high-priority `0x010` cross-module FREEZE broadcast.

`cec_freeze` timestamps frame arrival in the CAN RX ISR, then defers ring
freezing/dumping to a task. The tripping node freezes locally before it sends,
and all remote nodes align their capture windows to the ISR timestamp. The low
CAN identifier gives FREEZE arbitration priority over anomaly and telemetry.

The segmented J6C contract already provides GND-flanked CAN_H/CAN_L. Its two
reserved STREAM_P/STREAM_N pins remain unconnected on the current ATX and Hub
schematics.

## Can FREEZE be replicated without CAN?

Yes, as a dedicated event signal; no, not as a replacement for the common
message bus.

The lowest-BOM alternative is one open-drain, wired-OR `FREEZE#` conductor on a
reserved STREAM pin, with a ground return, pull-up at the Hub, source series
resistors, ESD protection at cable-exposed nodes, and a GPIO ISR at every node.
That can improve event-edge simultaneity and remain multi-origin, but it carries
only the event. Cause, origin, sequence, re-arm, telemetry, configuration,
identity binding, and OTA still need a message transport. Stuck-low detection
and isolation of a failed module also become explicit design requirements.

Using STREAM_P/N for UART/RS-485 can carry messages, but it is not a drop-in CAN
replacement. A multi-drop implementation needs another transceiver at every
node, bias/termination, addressing, collision avoidance or a strict master,
retry/error handling, and a new boot/update protocol. It loses CAN's native
non-destructive multi-master arbitration—the property that lets any module win
the bus immediately with the lowest FREEZE identifier. It is therefore more
work and is unlikely to lower the complete platform BOM.

A point-to-point GPIO or UART between only the 24-pin and Hub can remove CAN
from that one link only if the 24-pin is deliberately removed from the shared
module control plane. That would also remove its current direct participation
in common telemetry, OTA, poke-and-ack, and module-originated FREEZE. Relaying
through the Hub reintroduces a Hub single point of failure and timing skew.

## Recommendation

Keep CAN_H/CAN_L on the segmented mezzanine. It is still required for the
current platform behavior, not merely for FREEZE. If capture alignment later
proves insufficient on hardware, evaluate a dedicated open-drain `FREEZE#` on
one reserved STREAM pin as a supplement to CAN, not a replacement. Measure CAN
ISR timestamp spread first; do not add the extra wire by assumption.

Evidence reviewed:

- `firmware/esp/components/cec_comms/cec_freeze.c`
- `firmware/esp/components/cec_comms/include/cec_freeze.h`
- `firmware/esp/components/cec_comms/cec_canota.c`
- `firmware/esp/components/cec_comms/cec_pokeack.c`
- `firmware/esp/proto/hub-standard/README.md`
- `docs/mezz-structural-segments-2026-07-22.md`
