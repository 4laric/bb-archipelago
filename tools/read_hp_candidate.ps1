param(
    [UInt64]$CandidateBase = 0x213FC7230,
    [string]$OutputPath = "C:\Users\alari\bb-archipelago\work\hp-candidate-read.txt"
)

$native = @'
using System;
using System.Runtime.InteropServices;
public static class BloodborneHpCandidateRead {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, int processId);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool ReadProcessMemory(IntPtr process, UInt64 address, byte[] buffer, UIntPtr length, out UIntPtr read);
    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr process);
}
'@

if (-not ("BloodborneHpCandidateRead" -as [type])) { Add-Type $native }

$process = Get-Process -Name shadPS4 -ErrorAction Stop | Select-Object -First 1
$handle = [BloodborneHpCandidateRead]::OpenProcess(0x10, $false, $process.Id)
if ($handle -eq [IntPtr]::Zero) { throw "OpenProcess failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }

try {
    $address = $CandidateBase + 0xE0
    $buffer = [byte[]]::new(64)
    $read = [UIntPtr]::Zero
    if (-not [BloodborneHpCandidateRead]::ReadProcessMemory($handle, $address, $buffer, [UIntPtr]::new(64), [ref]$read)) {
        throw "ReadProcessMemory failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    }

    $lines = @(
        "timestamp=$(Get-Date -Format o)",
        "pid=$($process.Id)",
        "candidate_base=0x$($CandidateBase.ToString('X'))",
        "current_hp_address=0x$(($CandidateBase + 0xF8).ToString('X'))",
        "current_hp_i32=$([BitConverter]::ToInt32($buffer, 0x18))",
        "nearby_E0_64=$(($buffer | ForEach-Object { $_.ToString('X2') }) -join ' ')"
    )
    Set-Content -LiteralPath $OutputPath -Value $lines
}
finally {
    [BloodborneHpCandidateRead]::CloseHandle($handle) | Out-Null
}
