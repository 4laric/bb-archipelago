[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ForkExecutable,
    [Parameter(Mandatory = $true)][string]$QtBin,
    [Parameter(Mandatory = $true)][string]$ToolsDirectory,
    [Parameter(Mandatory = $true)][string]$SuppressionDirectory,
    [Parameter(Mandatory = $true)][string]$ClientRef,
    [string]$ClientPath,
    [string]$PythonExecutable = 'python',
    [string]$OutputRoot,
    [switch]$DebugBuild
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $OutputRoot) { $OutputRoot = Join-Path $repo 'build/fork-candidate' }
$output = [IO.Path]::GetFullPath($OutputRoot)
$buildPrefix = [IO.Path]::GetFullPath((Join-Path $repo 'build')).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not ($output + [IO.Path]::DirectorySeparatorChar).StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must be inside $buildPrefix"
}
if (Test-Path -LiteralPath $output) { throw "Output already exists: $output. Choose a fresh OutputRoot." }
if (-not $ClientPath) { $ClientPath = Join-Path $ToolsDirectory 'bb-ap-client.exe' }
$deployQt = Join-Path $QtBin 'windeployqt.exe'
foreach ($path in @($ForkExecutable, $deployQt, $ClientPath,
        (Join-Path $SuppressionDirectory 'gameparam.parambnd.dcx'),
        (Join-Path $SuppressionDirectory 'build-manifest.json'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing bundle input: $path" }
}
foreach ($tool in @('BBSuppressionWriter.exe', 'BBEventWriter.exe', 'BBToastWriter.exe',
                    'BBEnemizerWriter.exe', 'MSBBMiner.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ToolsDirectory $tool))) { throw "Missing build tool: $tool" }
}
New-Item -ItemType Directory -Path $output | Out-Null
$package = Join-Path $output 'BBLauncher-AP'
$work = Join-Path $output 'package-work'
New-Item -ItemType Directory -Path $package, $work | Out-Null
$worldData = @(Get-ChildItem -LiteralPath (Join-Path $repo 'worlds/bloodborne') -File |
    Where-Object { $_.Extension -in '.json', '.tsv' } |
    ForEach-Object { '--add-data'; "$($_.FullName);worlds/bloodborne" })
& $PythonExecutable -m PyInstaller --noconfirm --clean --console --onedir --name bb-ap-backend `
    --paths $repo --collect-submodules worlds `
    --add-data "$(Join-Path $repo 'research/bb_inputs.db');research" `
    --add-data "$(Join-Path $repo 'research/enemizer');research/enemizer" @worldData `
    --distpath (Join-Path $work 'dist') --workpath (Join-Path $work 'pyi') --specpath $work `
    (Join-Path $PSScriptRoot 'backend_entry.py')
if ($LASTEXITCODE -ne 0) { throw 'Frozen backend build failed.' }
$backend = Join-Path $package 'ap_backend'
Copy-Item -LiteralPath (Join-Path $work 'dist/bb-ap-backend') -Destination $backend -Recurse
Copy-Item -LiteralPath $ToolsDirectory -Destination (Join-Path $backend 'tools') -Recurse
New-Item -ItemType Directory -Path (Join-Path $backend 'ap-client'), (Join-Path $backend 'suppression') | Out-Null
Copy-Item -LiteralPath $ClientPath -Destination (Join-Path $backend 'ap-client/bb-ap-client.exe')
foreach ($name in @('gameparam.parambnd.dcx', 'build-manifest.json')) {
    Copy-Item -LiteralPath (Join-Path $SuppressionDirectory $name) -Destination (Join-Path $backend "suppression/$name")
}
$exe = Join-Path $package 'BBLauncher-AP.exe'
Copy-Item -LiteralPath $ForkExecutable -Destination $exe
$qtMode = if ($DebugBuild) { '--debug' } else { '--release' }
& $deployQt $qtMode --compiler-runtime --dir $package $exe
if ($LASTEXITCODE -ne 0) { throw 'Qt dependency deployment failed.' }
& $PythonExecutable (Join-Path $PSScriptRoot 'smoke_fork_bundle.py') $package
if ($LASTEXITCODE -ne 0) { throw 'Frozen fork bundle smoke failed.' }
$manifest = [ordered]@{
    format = 'bb-ap-fork-candidate-v1'
    backend_revision = (& git -C $repo rev-parse HEAD).Trim()
    backend_dirty = [bool]((& git -C $repo status --porcelain --untracked-files=no | Out-String).Trim())
    fork_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    client_ref = $ClientRef
    client_sha256 = (Get-FileHash -LiteralPath $ClientPath -Algorithm SHA256).Hash.ToLowerInvariant()
    debug_build = [bool]$DebugBuild
    game_tested = $false
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $package 'candidate-manifest.json') -Encoding utf8
Write-Host "Created local candidate: $package"
Write-Host 'Backend package smoke passed. This does not claim gameplay acceptance.'
