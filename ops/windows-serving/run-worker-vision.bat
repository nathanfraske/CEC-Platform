@echo off
rem CEC Windows-native serving launcher -- worker-vision seat (Qwen3.6-35B-A3B + mmproj).
rem Runs natively on Windows (model read from E: at NTFS speed, NOT the WSL drvfs mount).
rem The llama-server.exe.local dir redirects libomp140.x86_64.dll to the BUNDLED LLVM copy
rem (the Microsoft VC-redist libomp in System32 lacks __kmpc_dispatch_deinit -> load fail).
cd /d E:\llama-cpp-win\b9611
llama-server.exe ^
  -m "E:\AI Models\qwen3.6-35b-a3b\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf" ^
  --mmproj "E:\AI Models\qwen3.6-35b-a3b\mmproj-F16.gguf" ^
  --alias cec-worker-vision-win --host 0.0.0.0 --port 8090 ^
  -ngl 99 --ctx-size 16384 -np 1 -fa auto --jinja ^
  > E:\llama-cpp-win\srv.log 2>&1
