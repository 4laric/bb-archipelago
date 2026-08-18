param(
    [string]$ProcessName = "shadPS4",
    [UInt64]$EbootBase = 0x800000000
)

$native = @'
using System;
using System.Runtime.InteropServices;

public static class BloodborneReadProcessMemory
{
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, int processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool ReadProcessMemory(
        IntPtr process, UInt64 address, byte[] buffer, UIntPtr length, out UIntPtr read);

    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr process);
}
'@

if (-not ("BloodborneReadProcessMemory" -as [type])) {
    Add-Type $native
}

$sites = [ordered]@{
    HP       = [UInt64]0x1BFC5F7
    Echoes   = [UInt64]0x190029B
    Stamina  = [UInt64]0x18F78DB
    Lucidity = [UInt64]0x1901FB4
    Items    = [UInt64]0x14D9556
    OneHit   = [UInt64]0x1A0D47B
}

$process = Get-Process -Name $ProcessName -ErrorAction Stop | Select-Object -First 1
$handle = [BloodborneReadProcessMemory]::OpenProcess(0x10, $false, $process.Id)
if ($handle -eq [IntPtr]::Zero) {
    throw "OpenProcess(PROCESS_VM_READ) failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
}

try {
    foreach ($entry in $sites.GetEnumerator()) {
        $buffer = [byte[]]::new(16)
        $read = [UIntPtr]::Zero
        $address = $EbootBase + $entry.Value
        $ok = [BloodborneReadProcessMemory]::ReadProcessMemory(
            $handle, $address, $buffer, [UIntPtr]16, [ref]$read)
        if (-not $ok) {
            throw "ReadProcessMemory failed at 0x$($address.ToString('X')): $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
        }
        [PSCustomObject]@{
            Site = $entry.Key
            Offset = "0x$($entry.Value.ToString('X'))"
            Address = "0x$($address.ToString('X'))"
            Bytes = ($buffer | ForEach-Object { $_.ToString("X2") }) -join " "
        }
    }
}
finally {
    [BloodborneReadProcessMemory]::CloseHandle($handle) | Out-Null
}

