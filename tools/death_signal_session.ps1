param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Initialize', 'Capture', 'Analyze')]
    [string]$Mode,
    [string]$Session,
    [ValidateSet('CUSA00900', 'CUSA03173')]
    [string]$Serial,
    [string]$EmulatorVersion,
    [ValidateSet('death', 'control')]
    [string]$Kind = 'death',
    [ValidateRange(1, 20)]
    [int]$Trial = 1,
    [ValidateSet('idle-a', 'idle-b', 'before', 'primary', 'secondary', 'reload')]
    [string]$Stage,
    [string]$Source,
    [ValidateRange(1, 20)]
    [int]$TrialCount = 3,
    [ValidateRange(1, 20)]
    [int]$ControlCount = 1,
    [string[]]$Artifact
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

# Death-signal capture session (issue #78). Same hashed-manifest, multi-trial
# shape as tools/event_flag_session.ps1, with two deliberate differences:
#
#  1. There are two trial KINDS. Death trials die on purpose; control trials
#     warp at a lamp WITHOUT dying. "Changed during the trial" is not "is the
#     death signal", so Analyze subtracts anything that also moved in a
#     control trial. ControlCount cannot be zero: a death-only session proves
#     nothing.
#  2. Reload persistence CLASSIFIES instead of filtering. The flag hunt keeps
#     only bits that survive a reload; a death signal is allowed to be
#     transient. A bit still set after reload is counter-class (usable as a
#     monotonic cursor); one cleared by reload is edge-class (usable by live
#     polling). Both are real results.
#
# Stage meaning depends on the kind:
#   death trial   : before = alive at the hazard, primary = YOU DIED screen,
#                   secondary = respawned at the lamp, reload = after reload
#   control trial : before = at the lamp, primary = warp arrival settled,
#                   secondary = ten idle seconds later, reload = after reload
# idle-a / idle-b are doing nothing, ten seconds apart, in both kinds.

function Resolve-Session([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw '-Session is required for this mode.' }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-TrialPath([string]$Root, [string]$TrialKind, [int]$Number) {
    $prefix = if ($TrialKind -eq 'control') { 'control-{0:d2}' } else { 'trial-{0:d2}' }
    return Join-Path $Root ($prefix -f $Number)
}

function Test-BitHeld([string]$Path, [int64]$Offset, [int]$Bit, [int]$Wanted) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        if ($Offset -ge $stream.Length) { return $false }
        $null = $stream.Seek($Offset, 'Begin')
        $value = $stream.ReadByte()
    } finally { $stream.Dispose() }
    $held = if ((([byte]$value) -band (1 -shl $Bit)) -ne 0) { 1 } else { 0 }
    return ($held -eq $Wanted)
}

if ($Mode -eq 'Initialize') {
    if ([string]::IsNullOrWhiteSpace($Serial)) { throw '-Serial is required.' }
    if ([string]::IsNullOrWhiteSpace($EmulatorVersion)) { throw '-EmulatorVersion is required.' }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    if ([string]::IsNullOrWhiteSpace($Session)) {
        $Session = Join-Path $repo "work/death-signal/$stamp"
    }
    New-Item -ItemType Directory -Path $Session -Force | Out-Null
    for ($number = 1; $number -le $TrialCount; $number++) {
        New-Item -ItemType Directory -Path (Get-TrialPath $Session 'death' $number) -Force | Out-Null
    }
    for ($number = 1; $number -le $ControlCount; $number++) {
        New-Item -ItemType Directory -Path (Get-TrialPath $Session 'control' $number) -Force | Out-Null
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
        signal = 'death'
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        serial = $Serial
        app_version = '01.09'
        emulator_version = $EmulatorVersion
        trial_count = $TrialCount
        control_count = $ControlCount
        repo_commit = (& git -C $repo rev-parse HEAD).Trim()
        repo_dirty = [bool]((& git -C $repo status --porcelain) | Select-Object -First 1)
        machine = $env:COMPUTERNAME
        artifacts = $artifactRecords
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Session 'manifest.json') -Encoding utf8

    @"
Death-signal capture session (issue #78)

DEATH trials (restore the same backup save before each one):
  1. idle-a    - alive, do nothing
  2. idle-b    - ten seconds later, still doing nothing
  3. before    - alive, in range of the chosen enemy/hazard
  4. primary   - YOU DIED is on screen
  5. secondary - respawned at the lamp, control regained
  6. reload    - quit to title, reload the save, capture again

CONTROL trials (no death; the control pair the baseline demands):
  1. idle-a    - at the lamp, do nothing
  2. idle-b    - ten seconds later
  3. before    - immediately before warping
  4. primary   - warp arrival settled at the destination lamp
  5. secondary - ten idle seconds later
  6. reload    - quit to title, reload the save, capture again

Use tables/Bloodborne-death-signal-snapshot.CT for the dumps (F5-F10 in the
order above). Never change the base address or the length within a session.

Analyze subtracts every transition that also moved in a control trial, then
classifies each survivor: still set in reload.bin means counter-class (use as
a monotonic cursor); cleared by reload means edge-class (use live polling).
Neither class is the answer on its own - the write breakpoint
(tables/Bloodborne-death-signal-write-breakpoint.CT) attributes the writer.

See docs/SESSION-death-signal.md before starting.
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
    $limit = if ($Kind -eq 'control') { [int]$manifest.control_count } else { [int]$manifest.trial_count }
    if ($Trial -gt $limit) { throw "$Kind trial $Trial exceeds manifest count $limit." }
    $resolvedSource = (Resolve-Path -LiteralPath $Source).Path
    $trialPath = Get-TrialPath $sessionPath $Kind $Trial
    $destination = Join-Path $trialPath "$Stage.bin"
    Copy-Item -LiteralPath $resolvedSource -Destination $destination
    [ordered]@{
        captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        kind = $Kind
        stage = $Stage
        source = $resolvedSource
        bytes = (Get-Item -LiteralPath $destination).Length
        sha256 = Get-Sha256 $destination
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $trialPath "$Stage.json") -Encoding utf8
    Write-Output $destination
    exit 0
}

function Get-TrialCandidates([string]$TrialPath, [string]$Label) {
    foreach ($input in @('idle-a.bin', 'idle-b.bin', 'before.bin', 'primary.bin')) {
        if (-not (Test-Path -LiteralPath (Join-Path $TrialPath $input))) {
            throw "$Label is incomplete: missing $input"
        }
    }
    $csv = Join-Path $TrialPath 'candidates.csv'
    & (Join-Path $PSScriptRoot 'compare_event_snapshots.ps1') `
        -Before (Join-Path $TrialPath 'before.bin') `
        -After (Join-Path $TrialPath 'primary.bin') `
        -ControlBefore (Join-Path $TrialPath 'idle-a.bin') `
        -ControlAfter (Join-Path $TrialPath 'idle-b.bin') `
        -CsvPath $csv | Out-Null
    return @(Import-Csv -LiteralPath $csv)
}

# Per-trial diffs: what moved between before and primary, minus what idling moves.
$deathRows = @()
for ($number = 1; $number -le [int]$manifest.trial_count; $number++) {
    foreach ($row in @(Get-TrialCandidates (Get-TrialPath $sessionPath 'death' $number) "Death trial $number")) {
        $row | Add-Member -NotePropertyName Trial -NotePropertyValue $number -Force
        $deathRows += $row
    }
}
$controlKeys = @{}
for ($number = 1; $number -le [int]$manifest.control_count; $number++) {
    foreach ($row in @(Get-TrialCandidates (Get-TrialPath $sessionPath 'control' $number) "Control trial $number")) {
        $controlKeys["$($row.ByteOffset):$($row.Bit)"] = $true
    }
}

# Intersect across death trials, then subtract anything the lamp-warp control
# also moved. A survivor changed ONLY when the player died.
$survivors = $deathRows |
    Group-Object ByteOffset, Bit, Transition |
    Where-Object { ($_.Group.Trial | Sort-Object -Unique).Count -eq [int]$manifest.trial_count } |
    ForEach-Object { $_.Group | Select-Object -First 1 } |
    Where-Object { -not $controlKeys.ContainsKey("$($_.ByteOffset):$($_.Bit)") } |
    Sort-Object @{ Expression = { [int64]$_.ByteOffset } }, @{ Expression = { [int]$_.Bit } } |
    Select-Object Offset, ByteOffset, Bit, BeforeByte, AfterByte, Transition, ControlStable

# Classification, not filtration: a send signal may be transient by design.
foreach ($candidate in @($survivors)) {
    $wanted = [int]($candidate.Transition.Split('>')[-1])
    $offset = [int64]$candidate.ByteOffset
    $bit = [int]$candidate.Bit
    $secondaryHeld = $true
    $secondaryCount = 0
    $reloadHeld = $true
    $reloadCount = 0
    for ($number = 1; $number -le [int]$manifest.trial_count; $number++) {
        $trialPath = Get-TrialPath $sessionPath 'death' $number
        $secondaryPath = Join-Path $trialPath 'secondary.bin'
        if (Test-Path -LiteralPath $secondaryPath) {
            $secondaryCount++
            if (-not (Test-BitHeld $secondaryPath $offset $bit $wanted)) { $secondaryHeld = $false }
        }
        $reloadPath = Join-Path $trialPath 'reload.bin'
        if (Test-Path -LiteralPath $reloadPath) {
            $reloadCount++
            if (-not (Test-BitHeld $reloadPath $offset $bit $wanted)) { $reloadHeld = $false }
        }
    }
    $candidate | Add-Member -NotePropertyName SecondaryHeld -NotePropertyValue ($secondaryCount -gt 0 -and $secondaryHeld)
    $candidate | Add-Member -NotePropertyName ReloadHeld -NotePropertyValue ($reloadCount -gt 0 -and $reloadHeld)
}

$counterClass = @($survivors | Where-Object ReloadHeld)
$edgeClass = @($survivors | Where-Object { -not $_.ReloadHeld })
$intersectionPath = Join-Path $sessionPath 'intersection.csv'
$survivors | Export-Csv -LiteralPath $intersectionPath -NoTypeInformation
[ordered]@{
    analyzed_utc = (Get-Date).ToUniversalTime().ToString('o')
    trials = [int]$manifest.trial_count
    control_trials = [int]$manifest.control_count
    per_trial_candidates = @(for ($number = 1; $number -le [int]$manifest.trial_count; $number++) {
        @($deathRows | Where-Object Trial -eq $number).Count
    })
    control_distinct_positions = $controlKeys.Count
    intersection_count = @($survivors).Count
    counter_class = $counterClass.Count
    edge_class = $edgeClass.Count
    intersection = $intersectionPath
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $sessionPath 'analysis.json') -Encoding utf8

Write-Host ("Death trials intersected and control-subtracted: {0} surviving bit transition(s)." -f @($survivors).Count)
Write-Host ("  counter-class (held after reload): {0} - candidate monotonic death records" -f $counterClass.Count)
Write-Host ("  edge-class (cleared by reload):    {0} - candidate transient signals" -f $edgeClass.Count)
if (@($survivors).Count -eq 0) {
    Write-Host "No death-only transition in this region. That is a real result: the death signal is not a saved bit here. Poll HP or the death-state SpEffects instead (docs/SESSION-death-signal.md)."
}
Write-Output $intersectionPath
