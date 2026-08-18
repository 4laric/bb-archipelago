param(
    [int]$TimeoutSeconds = 180,
    [UInt64]$EbootBase = 0x800000000,
    [UInt64]$PatchElfAddress = 0x02CF83E0,
    [UInt64]$ElfImageBase = 0x00400000,
    [string]$LogPath = "C:\Users\alari\bb-archipelago\work\intel-sfx-workaround.log"
)

$native = @'
using System;
using System.Runtime.InteropServices;

public static class BloodborneIntelSfxPatch
{
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, int processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool ReadProcessMemory(
        IntPtr process, UInt64 address, byte[] buffer, UIntPtr length, out UIntPtr read);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool WriteProcessMemory(
        IntPtr process, UInt64 address, byte[] buffer, UIntPtr length, out UIntPtr written);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool VirtualProtectEx(
        IntPtr process, UInt64 address, UIntPtr size, uint newProtect, out uint oldProtect);

    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr process);
}
'@

if (-not ("BloodborneIntelSfxPatch" -as [type])) {
    Add-Type $native
}

function Write-Result([string]$Message) {
    $line = "$(Get-Date -Format o) $Message"
    Add-Content -LiteralPath $LogPath -Value $line
    Write-Output $line
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$process = $null
while ((Get-Date) -lt $deadline) {
    $process = Get-Process -Name shadPS4 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($process) { break }
    Start-Sleep -Milliseconds 250
}

if (-not $process) {
    Write-Result "ERROR timed out waiting for shadPS4"
    exit 1
}

$address = $EbootBase + ($PatchElfAddress - $ElfImageBase)
$handle = [BloodborneIntelSfxPatch]::OpenProcess(0x438, $false, $process.Id)
if ($handle -eq [IntPtr]::Zero) {
    Write-Result "ERROR OpenProcess failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    exit 2
}

try {
    $original = [byte[]]::new(1)
    $read = [UIntPtr]::Zero
    $loaded = $false
    while ((Get-Date) -lt $deadline) {
        if ([BloodborneIntelSfxPatch]::ReadProcessMemory($handle, $address, $original, [UIntPtr]::new(1), [ref]$read) -and $read.ToUInt64() -eq 1) {
            $loaded = $true
            break
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $loaded) { throw "eboot address never became readable" }

    if ($original[0] -eq 0xC3) {
        Write-Result "VERIFIED already enabled PID=$($process.Id) address=0x$($address.ToString('X')) byte=C3"
        exit 0
    }

    $oldProtect = 0
    if (-not [BloodborneIntelSfxPatch]::VirtualProtectEx($handle, $address, [UIntPtr]::new(1), 0x40, [ref]$oldProtect)) {
        throw "VirtualProtectEx failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    }

    $replacement = [byte[]](0xC3)
    $written = [UIntPtr]::Zero
    if (-not [BloodborneIntelSfxPatch]::WriteProcessMemory($handle, $address, $replacement, [UIntPtr]::new(1), [ref]$written) -or $written.ToUInt64() -ne 1) {
        throw "WriteProcessMemory failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    }

    $ignored = 0
    [BloodborneIntelSfxPatch]::VirtualProtectEx($handle, $address, [UIntPtr]::new(1), $oldProtect, [ref]$ignored) | Out-Null

    $verify = [byte[]]::new(1)
    $read = [UIntPtr]::Zero
    if (-not [BloodborneIntelSfxPatch]::ReadProcessMemory($handle, $address, $verify, [UIntPtr]::new(1), [ref]$read) -or $verify[0] -ne 0xC3) {
        throw "read-back verification failed"
    }

    Write-Result "VERIFIED applied PID=$($process.Id) address=0x$($address.ToString('X')) original=$($original[0].ToString('X2')) byte=C3"
}
catch {
    Write-Result "ERROR $($_.Exception.Message)"
    exit 3
}
finally {
    [BloodborneIntelSfxPatch]::CloseHandle($handle) | Out-Null
}
