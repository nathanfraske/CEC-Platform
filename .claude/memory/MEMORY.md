# CEC-Platform memory index

- [Environment rebuild 2026-06-12](env-rebuild-2026-06-12.md) — WSL reinstalled; full toolchain + broker rebuilt from scratch.
- [LLM broker](llm-broker.md) — cec-llm-broker at /home/nathan/cec-llm-broker, :8080, systemd unit; orchestrates the compose LLM backends.
- [Bot git auth](bot-git-auth.md) — git authors/pushes as nathanfraske-bot via PAT on /mnt/e; never the owner.
- [Windows-native serving](windows-native-serving.md) — Phase B: moving LLM seats off WSL/drvfs to Windows-native llama.cpp.
