param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Initialize', 'Capture', 'Analyze')]
    [string]$Mode,
    [string]$Session,
    [string]$LocationName,
    [ValidateSet('CUSA00900', 'CUSA03173')]
    [string]$Serial,
    [string]$EmulatorVersion,
    [ValidateRange(1, 20)]
    [int]$Trial = 1,
    [ValidateSet('idle-a', 'idle-b', 'before', 'after', 'reload')]
    [string]$Stage,
    [string]$Source,
    [ValidateRange(1, 20)]
    [int]$TrialCount = 3,
    [string[]]$Artifact
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

function Resolve-Session([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw '-Session is required for this mode.' }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ($Mode -eq 'Initialize') {
    if ([string]::IsNullOrWhiteSpace($LocationName)) { throw '-LocationName is required.' }
    if ([string]::IsNullOrWhiteSpace($Serial)) { throw '-Serial is required.' }
    if ([string]::IsNullOrWhiteSpace($EmulatorVersion)) { throw '-EmulatorVersion is required.' }

    $slug = ($LocationName.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    if ([string]::IsNullOrWhiteSpace($Session)) {
        $Session = Join-Path $repo "work/flags/$slug-$stamp"
    }
    New-Item -ItemType Directory -Path $Session -Force | Out-Null
    for ($number = 1; $number -le $TrialCount; $number++) {
        New-Item -ItemType Directory -Path (Join-Path $Session ('trial-{0:d2}' -f $number)) -Force | Out-Null
    }

    $artifactRecords = @()
    foreach ($item in @($Artifact | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        $resolved = (Resolve-Path -LiteralPath $item).Path
        $artifactRecords += [ordered]@{
            path = $resolved
            bytes = (Get-Item -LiteralPath $resolved).Length
            sha256 = Get-Sha256 $resolved
        }
    }
    $manifest = [ordered]@{
        schema = 1
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        location_name = $LocationName
        serial = $Serial
        app_version = '01.09'
        emulator_version = $EmulatorVersion
        trial_count = $TrialCount
        repo_commit = (& git -C $repo rev-parse HEAD).Trim()
        repo_dirty = [bool]((& git -C $repo status --porcelain) | Select-Object -First 1)
        machine = $env:COMPUTERNAME
        artifacts = $artifactRecords
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Session 'manifest.json') -Encoding utf8

    @"
Event-flag capture session: $LocationName

For each trial, restore the identical pre-action save and capture:
  1. idle-a   - do nothing
  2. idle-b   - ten seconds later, still doing nothing
  3. before   - immediately before the one declared action
  4. after    - after the banner clears, without entering another trigger
  5. reload   - quit to the title, reload the save, capture again

Stage 5 is what separates a saved flag from a session artefact. Analyze keeps
only candidates whose bit is still set in every reload capture.

Use Bloodborne-event-flag-snapshot.CT for raw memory regions, or use Capture
mode to copy matching save/dump files into this session. Never mix sources,
base addresses, or lengths within a session.
"@ | Set-Content -LiteralPath (Join-Path $Session 'RUNBOOK.txt') -Encoding utf8
    Write-Output (Resolve-Path -LiteralPath $Session).Path
    exit 0
}

$sessionPath = Resolve-Session $Session
$manifestPath = Join-Path $sessionPath 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "No manifest.json in $sessionPath" }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json

if ($Mode -eq 'Capture') {
    if ([string]::IsNullOrWhiteSpace($Stage)) { throw '-Stage is required.' }
    if ([string]::IsNullOrWhiteSpace($Source)) { throw '-Source is required.' }
    if ($Trial -gt $manifest.trial_count) { throw "Trial $Trial exceeds manifest trial count $($manifest.trial_count)." }
    $resolvedSource = (Resolve-Path -LiteralPath $Source).Path
    $trialPath = Join-Path $sessionPath ('trial-{0:d2}' -f $Trial)
    $destination = Join-Path $trialPath "$Stage.bin"
    Copy-Item -LiteralPath $resolvedSource -Destination $destination
    [ordered]@{
        captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        stage = $Stage
        source = $resolvedSource
        bytes = (Get-Item -LiteralPath $destination).Length
        sha256 = Get-Sha256 $destination
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $trialPath "$Stage.json") -Encoding utf8
    Write-Output $destination
    exit 0
}

$allRows = @()
for ($number = 1; $number -le $manifest.trial_count; $number++) {
    $trialPath = Join-Path $sessionPath ('trial-{0:d2}' -f $number)
    foreach ($input in @('idle-a.bin', 'idle-b.bin', 'before.bin', 'after.bin')) {
        if (-not (Test-Path -LiteralPath (Join-Path $trialPath $input))) {
            throw "Trial $number is incomplete: missing $input"
        }
    }
    $csv = Join-Path $trialPath 'candidates.csv'
    & (Join-Path $PSScriptRoot 'compare_event_snapshots.ps1') `
        -Before (Join-Path $trialPath 'before.bin') `
        -After (Join-Path $trialPath 'after.bin') `
        -ControlBefore (Join-Path $trialPath 'idle-a.bin') `
        -ControlAfter (Join-Path $trialPath 'idle-b.bin') `
        -CsvPath $csv | Out-Null
    foreach ($row in @(Import-Csv -LiteralPath $csv)) {
        $row | Add-Member -NotePropertyName Trial -NotePropertyValue $number
        $allRows += $row
    }
}

$survivors = $allRows |
    Group-Object ByteOffset, Bit, Transition |
    Where-Object { ($_.Group.Trial | Sort-Object -Unique).Count -eq $manifest.trial_count } |
    ForEach-Object { $_.Group | Select-Object -First 1 } |
    Sort-Object @{ Expression = { [int64]$_.ByteOffset } }, @{ Expression = { [int]$_.Bit } } |
    Select-Object Offset, ByteOffset, Bit, BeforeByte, AfterByte, Transition, ControlStable

# Requirement 4 of docs/EVENT-FLAG-RESEARCH.md: the bit must still be set after a
# reload. A transition that does not survive a reload is a session artefact, not a
# saved flag, and it is the difference between a lead and a finding. Only trials
# that captured reload.bin take part; if none did, the filter is skipped and said so.
$reloadTrials = @()
for ($number = 1; $number -le $manifest.trial_count; $number++) {
    $reloadPath = Join-Path (Join-Path $sessionPath ('trial-{0:d2}' -f $number)) 'reload.bin'
    if (Test-Path -LiteralPath $reloadPath) { $reloadTrials += $reloadPath }
}
$persisted = $null
if ($reloadTrials.Count -gt 0) {
    $kept = @()
    foreach ($candidate in @($survivors)) {
        $offset = [int64]$candidate.ByteOffset
        $mask = [byte](1 -shl [int]$candidate.Bit)
        $wanted = [int]($candidate.Transition.Split('>')[-1])
        $survivesAll = $true
        foreach ($reloadPath in $reloadTrials) {
            $stream = [System.IO.File]::OpenRead($reloadPath)
            try {
                if ($offset -ge $stream.Length) { $survivesAll = $false; break }
                $null = $stream.Seek($offset, 'Begin')
                $value = $stream.ReadByte()
            } finally { $stream.Dispose() }
            $bit = if ((([byte]$value) -band $mask) -ne 0) { 1 } else { 0 }
            if ($bit -ne $wanted) { $survivesAll = $false; break }
        }
        if ($survivesAll) { $kept += $candidate }
    }
    $persisted = $kept
    Write-Host "Reload filter: $(@($kept).Count) of $(@($survivors).Count) survived $($reloadTrials.Count) reload capture(s)."
    $survivors = $kept
} else {
    Write-Host "No reload.bin captured, so persistence was NOT tested. These are leads, not flags."
}

$intersectionPath = Join-Path $sessionPath 'intersection.csv'
$survivors | Export-Csv -LiteralPath $intersectionPath -NoTypeInformation
[ordered]@{
    analyzed_utc = (Get-Date).ToUniversalTime().ToString('o')
    trials = $manifest.trial_count
    per_trial_candidates = @(for ($number = 1; $number -le $manifest.trial_count; $number++) {
        @($allRows | Where-Object Trial -eq $number).Count
    })
    intersection_count = @($survivors).Count
    reload_captures = $reloadTrials.Count
    persistence_tested = ($reloadTrials.Count -gt 0)
    intersection = $intersectionPath
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $sessionPath 'analysis.json') -Encoding utf8

Write-Host "Intersected $($manifest.trial_count) trials: $(@($survivors).Count) surviving bit transitions."
Write-Output $intersectionPath
