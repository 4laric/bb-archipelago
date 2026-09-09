param(
    [Parameter(Mandatory = $true)] [string] $MapStudio,
    [Parameter(Mandatory = $true)] [string] $SoulsFormatsNext,
    [Parameter(Mandatory = $true)] [string] $ScriptRoot,
    [Parameter(Mandatory = $true)] [string] $Gameparam,
    [Parameter(Mandatory = $true)] [string] $Paramdef,
    [string] $Seed = "12345",
    [string] $Output = "work/enemizer/first-boot"
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$packageRoot = [System.IO.Path]::GetFullPath((Join-Path $workspace $Output))
$mapOutput = Join-Path $packageRoot "dvdroot_ps4/map/MapStudio"
$scriptOutput = Join-Path $packageRoot "dvdroot_ps4/script"
$manifest = Join-Path $packageRoot "bb-enemizer-plan.json"
$audit = Join-Path $packageRoot "offline-audit.json"

Push-Location $workspace
try {
    python tools/build_enemizer_catalog.py
    if ($LASTEXITCODE -ne 0) { throw "catalog generation failed" }

    dotnet build tools/bb_enemizer_writer/BBEnemizerWriter.csproj -c Release `
        -p:SoulsFormatsNextRoot=$SoulsFormatsNext
    if ($LASTEXITCODE -ne 0) { throw "enemizer writer build failed" }
    $writer = Join-Path $workspace "tools/bb_enemizer_writer/bin/Release/net9.0/BBEnemizerWriter.dll"
    python tools/audit_enemizer.py --seeds 25 --output $audit `
        --ai-writer $writer --ai-gameparam $Gameparam --ai-paramdef $Paramdef --ai-scripts $ScriptRoot
    if ($LASTEXITCODE -ne 0) { throw "offline release gate failed" }

    python -m tools.bb_enemizer.cli --seed $Seed --output $manifest
    if ($LASTEXITCODE -ne 0) { throw "manifest generation failed" }

    dotnet run --project tools/bb_enemizer_writer/BBEnemizerWriter.csproj -c Release `
        -p:SoulsFormatsNextRoot=$SoulsFormatsNext -- `
        $manifest $MapStudio $mapOutput --apply
    if ($LASTEXITCODE -ne 0) { throw "MSBB write or persisted verification failed" }
    dotnet $writer --ai $manifest $Gameparam $Paramdef $ScriptRoot $scriptOutput --apply
    if ($LASTEXITCODE -ne 0) { throw "AI transplant or persisted verification failed" }

    $metadata = @{
        format = "bb-enemizer-first-boot-v1"
        seed = $Seed
        manifest = "bb-enemizer-plan.json"
        audit = "offline-audit.json"
        map_root = "dvdroot_ps4/map/MapStudio"
        script_root = "dvdroot_ps4/script"
        ai_report = "dvdroot_ps4/script.json"
        warning = "Experimental first-boot build; not yet traversal-playtested."
    } | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $packageRoot "package.json") -Value $metadata -Encoding utf8
    Write-Host "First-boot package ready: $packageRoot"
}
finally {
    Pop-Location
}
