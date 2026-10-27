"""Fallback screen capture of the AC window with PowerShell + System.Drawing (needs windowed/borderless AC
that is visible on screen; exclusive fullscreen may come out black)."""
from __future__ import annotations

import subprocess
from pathlib import Path

PS = r"""
param([string]$Out)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W { [StructLayout(LayoutKind.Sequential)] public struct R { public int L, T, Ri, B; }
 [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out R r);
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref System.Drawing.Point p);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }
"@ -ReferencedAssemblies System.Drawing
[W]::SetProcessDPIAware() | Out-Null
$p = Get-Process acs -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$h = $p.MainWindowHandle
[W]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 400
$r = New-Object W+R; [W]::GetClientRect($h, [ref]$r) | Out-Null
$pt = New-Object System.Drawing.Point 0, 0; [W]::ClientToScreen($h, [ref]$pt) | Out-Null
$w = $r.Ri - $r.L; $hh = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($pt.X, $pt.Y, 0, 0, (New-Object System.Drawing.Size $w, $hh))
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "$w x $hh"
"""


def capture_window(out: str | Path) -> dict:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    script = out.parent / "_ac_capture.ps1"
    script.write_text(PS, encoding="utf-8")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Out", str(out)],
                           capture_output=True, text=True, timeout=60)
    finally:
        script.unlink(missing_ok=True)
    return {"ok": r.returncode == 0 and out.exists(), "path": str(out), "method": "powershell",
            "stdout": r.stdout.strip(), "stderr": r.stderr.strip()[-500:]}
