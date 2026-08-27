# Connector_Screw source record

This directory records where the proposed Standard Beta screw-terminal ECAD
assets came from and, equally importantly, which details still depend on an
incoming physical sample.

## Catalog identities

| Manufacturer | MPN | LCSC/JLC code | LCSC product | JLC assembly record |
|---|---|---|---|---|
| XFCN | `T34069` | `C481452` | <https://www.lcsc.com/product-detail/C481452.html> | <https://jlcpcb.com/partdetail/Xfcn-T34069/C481452> |
| XFCN | `TTR32100127-0600` | `C45384691` | <https://www.lcsc.com/product-detail/C45384691.html> | <https://jlcpcb.com/partdetail/Xfcn-Ttr321001270600/C45384691> |

The compact ATX daughterboard also uses the directly mated Samtec
`TSW-102-16-G-D-RA` 2×2 right-angle male and `SSQ-102-03-G-D` 2×2 vertical
female. Samtec's TSW table distinguishes in-plane mating length `C` from board
tail `E`: lead style `-16` provides `C=8.13 mm` and meets the calculated
`≥6.4 mm` requirement with a compact `E=5.08 mm` tail. Lead style `-12` has a
much longer `14.99 mm` post/tail envelope and provides no packaging advantage
here. Both local footprints preserve Samtec's odd/even-by-column pin numbering.
Samtec currently flags the exact `G`-plated male MPN as existing-customer-only;
the listed `S`, `L`, and `T` plating variants are geometry-compatible candidate
alternates, but one must be explicitly qualified and substituted in the BOM
rather than silently accepted.

Catalog snapshot checked 2026-08-12. Both JLC records reported an Extended
library part with `manualWeld` assembly mode and displayed “Wave Soldering.”
Stock and price are intentionally not frozen here; refresh them when ordering.
The normalized machine-readable snapshot is
`catalog-snapshot-2026-08-12.json`.

## Source-to-asset map

| Asset | Source and disposition |
|---|---|
| `../../datasheets/XFCN_T34069_C481452.pdf` | XFCN drawing, downloaded through LCSC C481452. |
| `../../datasheets/XFCN_TTR32100127-0600_C45384691.pdf` | XFCN drawing, downloaded through LCSC C45384691. |
| `../../datasheets/Samtec_TSW_TH.pdf` and `../../datasheets/Samtec_SSQ.pdf` | Samtec series drawings for the exact ATX 2×2 companion pair. |
| `../../vendor/Connector_PinHeader_2.54mm.pretty/Samtec_TSW-102-16-G-D-RA_2x02_P2.54mm_Horizontal.kicad_mod` | Exact right-angle male geometry, including the 8.13 mm in-plane mating envelope. |
| `../../vendor/Connector_PinSocket_2.54mm.pretty/Samtec_SSQ-102-03-G-D_2x02_P2.54mm_Vertical.kicad_mod` | Exact vertical female body and double-row pad map. |
| `../../vendor/Connector_Screw.kicad_sym` | CEC-authored symbols. Every physical leg belonging to one metal terminal is intentionally represented as one passive electrical pin. |
| `../../vendor/Connector_Screw.pretty/XFCN_T34069_THT_M3_40A.kicad_mod` | LCSC/EasyEDA land pattern imported with `easyeda2kicad 1.0.1`, then normalized for CEC: all four physical pads renumbered `1`, metadata corrected, Fab/Courtyard added, and model path made project-relative. |
| `../../vendor/Connector_Screw.pretty/XFCN_TTR32100127-0600_THT_M3_60A.kicad_mod` | LCSC/EasyEDA land pattern imported with `easyeda2kicad 1.0.1`, then normalized for CEC: both physical pads renumbered `1`, metadata corrected, Fab/Courtyard added, and a collision-envelope model assigned. |
| `../../vendor/Connector_Screw.pretty/*Daughterboard*PROVISIONAL.kicad_mod` | CEC-authored starting geometry. These are intentionally named `PROVISIONAL`; release is forbidden until the physical sample gates below pass. |
| `../../3dmodels/Connector_Screw.3dshapes/XFCN_T34069_native.step` and `.wrl` | Native EasyEDA model downloaded from the C481452 record and converted by `easyeda2kicad 1.0.1`. |
| `../../3dmodels/Connector_Screw.3dshapes/XFCN_TTR32100127-0600_envelope.step` | CEC-authored clearance model generated from the XFCN drawing. The public EasyEDA C45384691 record supplied no native 3D model. It is not manufacturer CAD. |

## Datasheet facts used

| MPN | Manufacturer-stated rating | Thread/torque | Drawing geometry used |
|---|---:|---|---|
| `T34069` | 40 A | M3-6H; 0.5 N·m | H62(Y2) brass; 6.3 mm width, 9 mm drawing height, 9 mm depth, 5 mm internal stamped opening, and 1.25 mm nominal sheet feature; Cu/Ni/matte-Sn plating stack. Product photographs show the supplied M3 screw/pressure washer removed from the threaded side face: an external daughterboard or conductor must therefore have a clearance hole and is clamped against that face. The native model registers about 5 mm above its inferred PCB plane and 4 mm of lead below it, which conflicts with LCSC's “9 mm above board” catalog field and must be sample-resolved. |
| `TTR32100127-0600` | 60 A | M3-6H; 1.0 N·m | H62(Y2) brass plus SPCC washer; 10 mm width, 6 mm vertical face, 9 mm body height, 12.7 mm overall depth/lead envelope; two 2.0 × 1.5 mm PCB slots on 9 mm centers; Cu/Ni/matte-Sn plating stack. |

Neither XFCN drawing publishes the current-rating temperature-rise test
condition, contact resistance, derating curve, PCB copper requirement, or
complete assembly stack. The catalog ampere figures therefore remain design
screening values and do not replace platform qualification.

## Incoming-sample gates

Measure at least five parts from the intended production lot before releasing
either footprint or daughterboard interface:

1. T34069: four lead widths/thicknesses and both 5.0/5.5 mm lead center
   spacings; installed Z height; threaded-face width/height; thread depth;
   screw-axis height from the daughterboard bottom-edge datum; supplied screw
   length; pressure-washer outside diameter/contact envelope; usable clamp
   face; and acceptable daughterboard/copper/finish stack.
2. TTR32100127-0600: two lead widths/thicknesses and 9.0 mm spacing; installed
   Z height; threaded-face width/height; thread depth; screw-axis height from
   the daughterboard bottom edge; washer outside diameter; usable clamp face.
3. For both: verify orientation against the Fab markings, capture photographs,
   and update the `PROVISIONAL` footprints plus the TTR envelope model before
   any board is released.

Both interfaces are external bolted joints. The T34069 product record shows a
separate supplied M3 screw/pressure washer and a threaded side face; the
TTR32100127-0600 drawing shows an M3 threaded right-angle face. A daughterboard
therefore needs a clearance hole for either part. The provisional ECAD uses a
3.4 mm plated M3 normal-clearance hole in both cases. Do not release the pad
diameter, washer keepout, screw length, edge datum, or thread engagement until
incoming samples establish the actual joint stack.

## Reproduction commands

The temporary Python environment is not part of the repository. Install the
tools in any disposable environment, then run:

```text
python -m pip install easyeda2kicad==1.0.1 cadquery==2.8.0
easyeda2kicad --lcsc_id C481452 C45384691 --full --output Connector_Screw.kicad_sym
python lib/3dmodels/Connector_Screw.3dshapes/source/generate_ttr32100127_0600_envelope.py
python lib/3dmodels/Connector_Screw.3dshapes/source/validate_models.py
```

The raw converter output is a source, not a release-ready library: it exposes
the terminal legs as separate pins. Use the reviewed CEC library assets above,
where every leg in a monolithic terminal is pad/pin `1`.
