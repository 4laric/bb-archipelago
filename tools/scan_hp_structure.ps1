param(
    [UInt64]$CandidateBase = 0x21207B650,
    [int]$Radius = 0x1000,
    [string]$OutputPath = "C:\Users\alari\bb-archipelago\work\hp-structure-scan.txt"
)

$native = @'
using System;
using System.Runtime.InteropServices;
public static class BloodborneHpStructureScan {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, int processId);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool ReadProcessMemory(IntPtr process, UInt64 address, byte[] buffer, UIntPtr length, out UIntPtr read);
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr process);
}
'@

if (-not ("BloodborneHpStructureScan" -as [type])) { Add-Type $native }

$process = Get-Process -Name shadPS4 -ErrorAction Stop | Select-Object -First 1
$handle = [BloodborneHpStructureScan]::OpenProcess(0x10, $false, $process.Id)
if ($handle -eq [IntPtr]::Zero) { throw "OpenProcess failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }

try {
    $start = $CandidateBase - [UInt64]$Radius
    $length = $Radius * 2
    $buffer = [byte[]]::new($length)
    $read = [UIntPtr]::Zero
    if (-not [BloodborneHpStructureScan]::ReadProcessMemory($handle, $start, $buffer, [UIntPtr]::new($length), [ref]$read)) {
        throw "ReadProcessMemory failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    }

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("timestamp=$(Get-Date -Format o)")
    $lines.Add("pid=$($process.Id)")
    $lines.Add("candidate_base=0x$($CandidateBase.ToString('X'))")
    $lines.Add("validated_current_hp_offset=+0xF8")
    foreach ($offset in 0..($length - 4)) {
        $value = [BitConverter]::ToInt32($buffer, $offset)
        if ($value -eq 373 -or $value -eq 594) {
            $address = $start + [UInt64]$offset
            $relative = [Int64]$address - [Int64]$CandidateBase
            $sign = if ($relative -ge 0) { '+' } else { '-' }
            $lines.Add("value=$value address=0x$($address.ToString('X')) relative=${sign}0x$([Math]::Abs($relative).ToString('X')) aligned=$([bool](($address % 4) -eq 0))")
        }
    }
    Set-Content -LiteralPath $OutputPath -Value $lines
}
finally {
    [BloodborneHpStructureScan]::CloseHandle($handle) | Out-Null
}
