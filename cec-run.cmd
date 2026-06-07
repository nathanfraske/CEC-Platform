@echo off
rem Local entry point for the agentic compute tools (cec_dispatch.py).
rem Delegates to scripts\dispatch.ps1, which finds KiCad's python + kicad-cli + java + the
rem Freerouting jar and passes every argument straight through. No manual PATH config needed.
rem   cec-run request-candidates --board eps-8pin --seeds 0,1 --passes 8 --opt-time 12
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dispatch.ps1" %*
