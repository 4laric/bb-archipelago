param(
    [Parameter(Mandatory = $true)] [string] $MapStudio,
    [Parameter(Mandatory = $true)] [string] $SoulsFormatsNext,
    [string] $Seed = "12345",
    [string] $Output = "work/enemizer/first-boot"
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$packageRoot = [System.IO.Path]::GetFullPath((Join-Path $workspace $Output))
$mapOutput = Join-Path $packageRoot "dvdroot_ps4/map/MapStudio"
$manifest = Join-Path $packageRoot "bb-enemizer-plan.json"
$audit = Join-Path $packageRoot "offline-audit.json"

Push-Location $workspace
try {
    python tools/build_enemizer_catalog.py
    if ($LASTEXITCODE -ne 0) { throw "catalog generation failed" }

    python tools/audit_enemizer.py --seeds 25 --output $audit
    if ($LASTEXITCODE -ne 0) { throw "offline release gate failed" }

    python -m tools.bb_enemizer.cli --seed $Seed --output $manifest
    if ($LASTEXITCODE -ne 0) { throw "manifest generation failed" }

    dotnet run --project tools/bb_enemizer_writer/BBEnemizerWriter.csproj -c Release `
        -p:SoulsFormatsNextRoot=$SoulsFormatsNext -- `
        $manifest $MapStudio $mapOutput --apply
    if ($LASTEXITCODE -ne 0) { throw "MSBB write or persisted verification failed" }

    $metadata = @{
        format = "bb-enemizer-first-boot-v1"
        seed = $Seed
        manifest = "bb-enemizer-plan.json"
        audit = "offline-audit.json"
        map_root = "dvdroot_ps4/map/MapStudio"
        warning = "Experimental first-boot build; not yet traversal-playtested."
    } | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $packageRoot "package.json") -Value $metadata -Encoding utf8
    Write-Host "First-boot package ready: $packageRoot"
}
finally {
    Pop-Location
}
