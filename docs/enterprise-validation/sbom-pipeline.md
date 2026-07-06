# SBOM pipeline

Verification artifact for **REQ-HUB-COMMON-014, -094** and **REQ-MOD-COMMON-052**.
`verification-map.json` artifact key: `sbom-pipeline`. **Status: pipeline design only —
gated on a real firmware build tree** (`west spdx`-class tooling needs a buildable image).

## 1. Ruled format decision (implements REQ-HUB-COMMON-014, 9th ruling 2026-07-02)

**SPDX is the native per-release artifact of record; CycloneDX is derived on demand.**
This is a primary + derived pair, not an either/or — the N2 ratification item
("Adopt these recs") resolved the SPDX-vs-CycloneDX split by keeping both: SPDX because
the Hub's firmware base is Zephyr and `west spdx` is a first-party, already-integrated
generator; CycloneDX because the PSIRT/VEX tooling ecosystem (vuln-to-component linkage,
`sbom-pipeline.md` §5 below) is CycloneDX-native. Do not re-litigate this split as a
pending decision in future docs — it is RESOLVED.

## 2. Hub: `west spdx` generation, wired to the firmware build

- Hub firmware builds on Zephyr (HSS → wolfBoot → Zephyr, per the firmware-fabric
  scope doc). `west spdx` runs as a post-build step against the same CMake/Ninja build
  directory the release build already produces — no parallel build required.
- Output: one SPDX 2.3 (tag-value or JSON) document per firmware image, covering the
  Zephyr kernel, all enabled subsystems/drivers, and vendored HALs (PolarFire SoC HAL,
  wolfCrypt/wolfBoot sources) at their pinned commit/version.
- **Per-release attach**: the SPDX document is attached as a release artifact alongside
  the signed firmware image itself (same release, same version tag) — never generated
  after the fact from a rebuilt or reconstructed tree.

## 3. CycloneDX conversion path

Derived on demand, not generated per-release by default (§1). Candidate tooling:

1. **CycloneDX CLI (`cyclonedx-cli convert`)** — official OWASP tool; supports SPDX-JSON
   input → CycloneDX-JSON output. First candidate: no custom code, actively maintained.
2. **Custom translation script** — fallback if the CLI's SPDX-relationship coverage
   proves lossy (SPDX's richer relationship graph vs CycloneDX's component-tree model);
   only worth building once the PSIRT pipeline names a specific VEX field it needs that
   the CLI drops.
- Conversion runs at PSIRT-integration time (when a CSA needs a VEX statement against a
  specific release), not baked into the release-artifact step — keeps the release
  pipeline simple and the derived artifact demonstrably regenerable from the artifact
  of record.

## 4. Module-family SBOMs — honest tooling gap (ESP-IDF side)

All four ENT module families (24-pin, EPS, PCIe, 12VHPWR) build on **ESP-IDF**
(ESP32-P4), not Zephyr. **There is no `west`-equivalent SPDX generator for ESP-IDF** —
`idf.py`'s build system has no first-party SBOM output, and ESP-IDF's
`idf_component.yml`/`dependencies.lock` manifests describe component *registry*
dependencies, not a full build-time bill of materials (compiler, vendored third-party
sources pulled in via `git`/local components, toolchain version). This is a real gap,
not a stopgap detail:

- **Interim**: hand-assembled SPDX documents per release, sourced from the
  `dependencies.lock` manifest + toolchain version pin + a manual vendored-source list —
  labor, not automation, and a known drift risk (nothing fails CI if a vendored source
  changes without the SBOM being updated).
- **Candidate automation**: a generic build-artifact scanner (Anchore Syft or `cdxgen`)
  against the built ESP-IDF binary/component tree — produces CycloneDX directly (skips
  the SPDX-native step for modules only), making module SBOMs CycloneDX-primary while
  the Hub stays SPDX-primary. Flag this asymmetry wherever module/Hub SBOMs are compared.
- Owner-visible action: close this gap before REQ-MOD-COMMON-052's "SHALL ship an SBOM
  per firmware release" is anything more than a hand-built document.

## 5. CI hook sketch

```
release-build:
  hub:      west build ... && west spdx -d <builddir> -o hub-<ver>.spdx.json
  modules:  idf.py build ...  # no native SBOM step (see §4)
release-publish:
  attach hub-<ver>.spdx.json           # artifact of record
  attach module-<family>-<ver>.spdx.json (hand-built or scanner-derived, §4)
  # CycloneDX NOT generated here by default — derived on demand (§3) when
  # PSIRT opens a VEX statement against this release.
```

`scripts/cec_sbom_gen.py` is the planned (not yet written) wrapper invoking the above
and validating every attached SBOM parses before release publish.
