# CEC-Platform memory index

- [Environment rebuild 2026-06-12](env-rebuild-2026-06-12.md) — WSL reinstalled; full toolchain + broker rebuilt from scratch.
- [LLM broker](llm-broker.md) — cec-llm-broker at /home/nathan/cec-llm-broker, :8080, systemd unit; orchestrates the compose LLM backends.
- [Bot git auth](bot-git-auth.md) — git authors/pushes as nathanfraske-bot via PAT on /mnt/e; never the owner.
- [Windows-native serving](windows-native-serving.md) — Phase B: moving LLM seats off WSL/drvfs to Windows-native llama.cpp.
- [DeepSeek-V4 auditor](deepseek-v4-auditor.md) — T5 deep auditor seat; Windows-native llama-server on :8007, broker external backend; GGUF in /mnt/e/models.
- [V4 as a panel seat](v4-seat.md) — hand V4 tasks sync (cec_v4_task.py) or async via the idle queue (cec_v4_queue.py + Stop hook); a tier above a Sonnet sub-agent.
- [AllMyStuff + MyOwnMesh apps](allmystuff-myownmesh-apps.md) — owner's coworker (mrjeeves) Windows apps; per-user Tauri installs; how to update + that AllMyStuff bundles the myownmesh daemon.
- [Convergence blocker: mechanism not corpus](convergence-blocker-mechanism-not-corpus.md) — deterministic route converges the committed board now; fresh/agentic stall is pour-clip enforcement, not a corpus gap.
- [KiCad integration landscape](kicad-integration-landscape.md) — what exists (IPC kipy refill_zones, kicad-sch-api/kicad-skip, circuit-synth, MCP servers, KiBot) and which close our bottlenecks; KiCad-10 compat caveats.
- [dashboard-fixed-port](dashboard-fixed-port.md) — always reuse port 8090 (kill old with the bracket-pkill trick); never increment.
- [thermal-gate-required](thermal-gate-required.md) — a routed board isn't "clean" until electrothermal_solve passes; the route gate skips thermal.
- [cec-thermal2d-field-solver](cec-thermal2d-field-solver.md) — **USE FIRST for any thermal check**: scripts/cec_thermal2d.py is the fine-density field solver (couples layers via real vias, sub-grid thin traces); the analytic electrothermal_solve is only the lumped fallback.
