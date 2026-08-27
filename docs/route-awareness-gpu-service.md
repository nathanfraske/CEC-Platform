# Persistent route-awareness service

The placement wave has one process-safe CUDA owner. Spawned KiCad placement
workers continue to run small congestion checks concurrently on CPU. Problems
above the measured crossover are serialized through a private Unix socket to a
warmed CuPy context. The service accelerates global-route prediction only; it
does not waive detailed routing, KiCad connectivity, DRC, or fabrication gates.

## Why it is split this way

Creating a CUDA context in every spawned placement worker wastes startup time
and lets independent CuPy memory pools compete with each other and the local
wave-manager model. Sending every problem to CUDA is also slower: launch and
path-recovery overhead dominate small coarse grids. `cec_coord_router` therefore
admits CUDA only when `connections * layers * height * width` reaches the
measured default floor of 12,000,000 cells.

`cec_fresh_wave` starts the service before it creates its worker pools.
`cec_hub_unattended` starts it one level higher, so the same context and bounded
exact-result cache survive across every wave subprocess in an unattended run.
The service releases the CuPy device and pinned-memory pools after each job,
while retaining the context and compiled kernel cache. Its socket directory is
mode 0700, the socket is mode 0600, and the whole directory is removed at owner
exit. It writes no route tensors or caches to persistent storage.

## Route-aware placement tournament

The Hub uses a two-stage placement tournament:

1. Every candidate receives the 1.0 mm CPU access/capacity proof.
2. The best six coarse candidates, including existing fail-open and intent-class
   floors, receive an equal-resolution 0.5 mm CUDA proof.
3. The final prune compares only candidates measured at that same fine
   resolution before assigning the expensive detailed-router budget.

Fine and coarse residuals are never compared directly. A missing fine proof is
unkeyed and therefore routes fail-open. Critical pair refusals, critical launch
access, declared shutdown/control nets, array fanout, unreachable connections,
and congestion precede ordinary proxy length in the placement key.

## Hub measurements, 2026-08-08

Pinned board:
`build/hub-critical-placement-smoke/hub-standard-rev2/plain-dataflow-s0-placed.kicad_pcb`

- Problem: 173 two-pin connections, 4 legal routing layers, 149 x 173 grid,
  17,837,684 work cells at 0.5 mm.
- Three-iteration CPU route analysis: 72.184 s.
- Three-iteration persistent CUDA route analysis: 23.483 s (3.07x faster).
- Both: residual overuse 208, escaped residual 178, unroutable connections 0.
- CuPy pool before post-job release: 73,602,048 bytes (70.2 MiB).
- Exact repeat: total board analysis 25.536 s to 1.701 s through the bounded
  in-memory result cache.
- Two distinct live placements: fine CUDA work 20.360 s + 20.778 s = 44.418 s;
  both had zero unreachable connections. The dataflow candidate kept priority
  despite higher ordinary congestion because the compact candidate had one
  refused critical-pair route.

The critical-pin repair trace remains a separate latency target. On the live
compact placement it took 86.1 s after safe duplicate-work reductions versus
91.9 s initially, accepting the same one move and retaining the same critical
pair refusal. New per-phase `timing_s` evidence in every repair report makes
materialization, access analysis, bypass checks, and full finalist analysis
independently visible for the next optimization.

## Controls

- `CEC_COORD_SERVICE=0`: disable daemon startup.
- `CEC_COORD_SERVICE_SOCKET=/path/to/socket`: reuse an externally owned daemon.
- `CEC_COORD_AUTO_GPU_FLOOR=12000000`: override CUDA admission work cells.
- `CEC_COORD_SERVICE_CACHE_MB=64`: bound the exact-result memory cache.
- `CEC_COORD_SERVICE_TIMEOUT_S=900`: bound a client request.
- `CEC_WAVE_AWARE_SHORTLIST=0`: disable fine placement refinement; Hub default 6.
- `CEC_WAVE_AWARE_GRID_MM=0.5`: fine tournament grid.
- `CEC_WAVE_AWARE_ITERS=3`: fine tournament negotiation passes.
- `CEC_WAVE_FUTURE_MULTIRESOLUTION=1`: restore coarse-plus-fine diagnostics in
  the initial placement screen. The authoritative route proof is unchanged.

With `backend=auto`, a daemon failure falls back to the deterministic CPU
engine and records the service error. A caller that explicitly forces
`backend=gpu` gets an error instead of a silent downgrade.
