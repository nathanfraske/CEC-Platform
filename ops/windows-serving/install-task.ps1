# Registers the CEC Windows-native worker-vision server as a logon Scheduled Task.
# RUN ONCE, ELEVATED (right-click > Run as administrator, or from an admin PowerShell):
#     powershell -ExecutionPolicy Bypass -File E:\llama-cpp-win\install-task.ps1
#
# After this, the server starts at each logon and survives reboots. To start it now
# without waiting for a logon:  schtasks /Run /TN CEC-WorkerVision
$action  = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c E:\llama-cpp-win\run-worker-vision.bat'
$trigger = New-ScheduledTaskTrigger -AtLogOn
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$princ   = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName 'CEC-WorkerVision' -Action $action -Trigger $trigger -Settings $set -Principal $princ -Force
Write-Host "Registered CEC-WorkerVision. Starting it now..."
Start-ScheduledTask -TaskName 'CEC-WorkerVision'
Write-Host "Started. Health: http://localhost:8090/health (cold-loads ~the model from E:)."
