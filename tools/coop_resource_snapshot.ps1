# Read-only Windows telemetry. Never launches, suspends, or edits a game process.
param([Parameter(Mandatory = $true)][string]$ProcessIds)
$ErrorActionPreference = 'Stop'
if ($ProcessIds -notmatch '^\d+(,\d+)*$') { throw 'ProcessIds must be comma-separated positive integers.' }
$os = Get-CimInstance Win32_OperatingSystem
$processes = @(foreach ($processIdValue in $ProcessIds.Split(',')) {
    try {
        $process = Get-Process -Id ([int]$processIdValue) -ErrorAction Stop
        [ordered]@{
            pid = $process.Id
            status = 'ok'
            name = $process.ProcessName
            started_utc = $process.StartTime.ToUniversalTime().ToString('o')
            executable = $process.Path
            cpu_seconds = $process.TotalProcessorTime.TotalSeconds
            working_set_bytes = $process.WorkingSet64
            private_bytes = $process.PrivateMemorySize64
        }
    } catch {
        [ordered]@{ pid = [int]$processIdValue; status = 'unavailable'; error = $_.Exception.Message }
    }
})
[ordered]@{
    system = [ordered]@{
        total_ram_bytes = [long]$os.TotalVisibleMemorySize * 1024
        available_ram_bytes = [long]$os.FreePhysicalMemory * 1024
        logical_processors = [Environment]::ProcessorCount
    }
    processes = $processes
} | ConvertTo-Json -Depth 5 -Compress
