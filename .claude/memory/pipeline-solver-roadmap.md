---
name: pipeline-solver-roadmap
description: "THE standing answer to \"what other solvers can we add / what pipeline improvements\" — docs/pipeline-solver-roadmap.md"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 7334b387-a067-4e04-94c6-a63201c3c803
---

When the owner asks "what other solvers can we add, or what improvements can we make to the
pipeline" (they said they WILL ask again, 2026-07-08): the standing, maintained answer is
**`docs/pipeline-solver-roadmap.md`** — solver inventory, scoped-not-built ranked list (PDN/
ground-impedance, SPICE schematic-cell verification, 2D electrostatic Z0), non-solver pipeline
improvements, and a decision log. Update THAT doc in the same change that lands or scopes
anything solver/pipeline-shaped; don't re-derive from scratch. Related: [[agent-cost-policy]]
(seat policy for in-loop agents), [[cec-thermal2d-field-solver]] (the GPU backend everything
new should reuse — fix its nondeterminism first).
