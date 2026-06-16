---
name: allmystuff-myownmesh-apps
description: "Owner's Windows apps AllMyStuff + MyOwnMesh (coworker mrjeeves) — install layout and how to update."
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5360a775-9d1e-4f79-a6b5-7dcde4e2bcb0
---

Two trusted Windows desktop apps by the owner's coworker **mrjeeves** (GitHub `mrjeeves/AllMyStuff`,
public releases). Both are Tauri/NSIS **per-user** installs under `%LOCALAPPDATA%` (no UAC) and self-update.

- **AllMyStuff** → `C:\Users\Natha\AppData\Local\AllMyStuff\`: `allmystuff-gui.exe` (GUI) **+ bundled
  `myownmesh.exe` (its mesh daemon)**. Installing/updating AllMyStuff also updates that bundled daemon —
  so "kill AllMyStuff and MyOwnMesh, GUI + daemon" = kill image names `allmystuff-gui`, `myownmesh-gui`,
  `myownmesh`. Launching `allmystuff-gui.exe` auto-spawns `myownmesh.exe`.
- **MyOwnMesh** is a SEPARATE app, independently versioned (0.2.x vs AllMyStuff 0.1.x), at
  `AppData\Local\MyOwnMesh\` and `AppData\Local\Programs\MyOwnMesh\`.

Update recipe (verified 2026-06-16, took 0.1.9 → 0.1.13): from WSL drive Windows via `powershell.exe`.
Get assets from `api.github.com/repos/mrjeeves/AllMyStuff/releases/tags/<tag>`; Windows x64 installer =
`AllMyStuff_<ver>_x64-setup.exe` (NSIS; there's also an `_x64_en-US.msi`). Steps: Stop-Process the 3 image
names → `Start-Process <setup.exe> -ArgumentList '/S' -Wait` (silent, exit 0) → verify
`(Get-Item allmystuff-gui.exe).VersionInfo.ProductVersion` → `Start-Process allmystuff-gui.exe`. The owner
keeps stale copies around (old MyOwnMesh installs, `.allmystuff`/`.myownmesh\updates\` caches, old setups in
Downloads) — leave them unless asked to clean up.
