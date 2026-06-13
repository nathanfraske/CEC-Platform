Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
  public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
"@
$targets = New-Object System.Collections.Generic.HashSet[uint32]
$cb = [W+EnumWindowsProc]{
  param($h,$l)
  if (-not [W]::IsWindowVisible($h)) { return $true }
  $t = New-Object System.Text.StringBuilder 512; [W]::GetWindowText($h,$t,512) | Out-Null
  $c = New-Object System.Text.StringBuilder 256; [W]::GetClassName($h,$c,256) | Out-Null
  $title = $t.ToString(); $cls = $c.ToString()
  if ($title -match 'Entry Point|procedure entry|llama|ggml|dynamic link library|win-llama') {
    $procId = [uint32]0; [W]::GetWindowThreadProcessId($h,[ref]$procId) | Out-Null
    Write-Host "window: '$title' [class=$cls pid=$procId] -> WM_CLOSE + kill"
    [W]::SendMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null   # WM_CLOSE
    $me = [System.Diagnostics.Process]::GetCurrentProcess().Id
    if ($procId -ne 0 -and $procId -ne $me) { [void]$targets.Add($procId) }
  }
  return $true
}
[W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
Start-Sleep -Milliseconds 500
foreach ($p in $targets) {
  try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue; Write-Host "killed pid $p" } catch {}
}
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300
$remain = 0
$cb2 = [W+EnumWindowsProc]{ param($h,$l)
  if (-not [W]::IsWindowVisible($h)) { return $true }
  $t = New-Object System.Text.StringBuilder 512; [W]::GetWindowText($h,$t,512)|Out-Null
  if ($t.ToString() -match 'Entry Point|procedure entry|llama|ggml|win-llama') { $script:remain++; Write-Host "STILL OPEN: '$($t.ToString())'" }
  return $true }
[W]::EnumWindows($cb2,[IntPtr]::Zero)|Out-Null
Write-Host "remaining matching windows: $remain"
