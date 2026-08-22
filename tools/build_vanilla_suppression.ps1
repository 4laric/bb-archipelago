[CmdletBinding()]
param(
    [string]$GameParam,
    [string]$Paramdef,
    [string]$OutputRoot,
    [string]$SoulsFormatsNextRoot = $env:SOULSFORMATS_NEXT,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Artifacts = Join-Path $Repo "Bloodborne.Game.of.the.Year.Edition.PS4-PRELUDE\bloodborne_artifacts"
if (-not $GameParam) {
    $GameParam = Join-Path $Artifacts "param\gameparam\gameparam.parambnd.dcx"
}
if (-not $Paramdef) {
    $Paramdef = Join-Path $Artifacts "paramdef\paramdef.paramdefbnd.dcx"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $Repo "work\vanilla-suppression-build"
}
if (-not $SoulsFormatsNextRoot) {
    throw "Pass -SoulsFormatsNextRoot or set SOULSFORMATS_NEXT."
}
if (-not $Apply) {
    throw "Refusing to build without -Apply. The output is separate and is never installed automatically."
}

$GameParam = (Resolve-Path -LiteralPath $GameParam).Path
$Paramdef = (Resolve-Path -LiteralPath $Paramdef).Path
$SoulsFormatsNextRoot = (Resolve-Path -LiteralPath $SoulsFormatsNextRoot).Path
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$OutputParam = Join-Path $OutputRoot "gameparam.parambnd.dcx"
$Plan = Join-Path $OutputRoot "suppression-plan.json"
$Manifest = Join-Path $OutputRoot "build-manifest.json"

if (Test-Path -LiteralPath $OutputParam) {
    throw "Refusing to overwrite existing output: $OutputParam"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

& python (Join-Path $PSScriptRoot "plan_vanilla_suppression.py") `
    --output $Plan --allow-refusals
if ($LASTEXITCODE -ne 0) { throw "Suppression planning failed." }

$Project = Join-Path $PSScriptRoot "bb_suppression_writer\BBSuppressionWriter.csproj"
& dotnet build $Project "-p:SoulsFormatsNextRoot=$SoulsFormatsNextRoot" -v:minimal
if ($LASTEXITCODE -ne 0) { throw "Suppression writer build failed." }
& dotnet run --project $Project "-p:SoulsFormatsNextRoot=$SoulsFormatsNextRoot" `
    --no-build -- $Plan $GameParam $Paramdef $OutputParam --apply
if ($LASTEXITCODE -ne 0) { throw "Suppression writer failed." }

$ManifestJson = @{
    format = "bb-vanilla-suppression-build-v1"
    source_gameparam_sha256 = (Get-FileHash -LiteralPath $GameParam -Algorithm SHA256).Hash.ToLower()
    source_paramdef_sha256 = (Get-FileHash -LiteralPath $Paramdef -Algorithm SHA256).Hash.ToLower()
    plan_sha256 = (Get-FileHash -LiteralPath $Plan -Algorithm SHA256).Hash.ToLower()
    output_gameparam_sha256 = (Get-FileHash -LiteralPath $OutputParam -Algorithm SHA256).Hash.ToLower()
    output_relative_path = "param/gameparam/gameparam.parambnd.dcx"
    installed = $false
} | ConvertTo-Json
[IO.File]::WriteAllText($Manifest, $ManifestJson, [Text.UTF8Encoding]::new($false))

Write-Host "Built and reopened the suppressed binder: $OutputParam" -ForegroundColor Green
Write-Host "Nothing was installed. Manifest: $Manifest" -ForegroundColor Yellow
