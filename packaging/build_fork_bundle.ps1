[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ForkExecutable,
    [Parameter(Mandatory = $true)][string]$QtBin,
    [Parameter(Mandatory = $true)][string]$ToolsDirectory,
    [Parameter(Mandatory = $true)][string]$SuppressionDirectory,
    [Parameter(Mandatory = $true)][string]$ClientRef,
    [string]$ClientPath,
    [string]$ForkSourceRoot,
    [string]$PythonExecutable = 'python',
    [string]$OutputRoot,
    [string]$ReleaseVersion,
    [string]$ApworldPath,
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
if (-not $ForkSourceRoot -or -not (Test-Path -LiteralPath (Join-Path $ForkSourceRoot 'dist/web.qml'))) {
    throw 'ForkSourceRoot must contain dist/web.qml so the Mod Downloader browser dependencies can be bundled.'
}
foreach ($path in @($ForkExecutable, $deployQt, $ClientPath,
        (Join-Path $SuppressionDirectory 'gameparam.parambnd.dcx'),
        (Join-Path $SuppressionDirectory 'build-manifest.json'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing bundle input: $path" }
}
foreach ($tool in @('BBSuppressionWriter.exe', 'BBEventWriter.exe', 'BBToastWriter.exe',
                    'BBEnemizerWriter.exe', 'MSBBMiner.exe',
                    'BBEnemizerPlanner/BBEnemizerPlanner.exe',
                    'BBBossEncounterBuilder/BBBossEncounterBuilder.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ToolsDirectory $tool))) { throw "Missing build tool: $tool" }
}
New-Item -ItemType Directory -Path $output | Out-Null
$package = Join-Path $output 'BBLauncher-AP'
$work = Join-Path $output 'package-work'
New-Item -ItemType Directory -Path $package, $work | Out-Null
$versionMetadata = $null
$versionArgument = @()
if ($ReleaseVersion) {
    $worldMetadata = Get-Content -LiteralPath (Join-Path $repo 'worlds/bloodborne/archipelago.json') -Raw | ConvertFrom-Json
    $versionRoot = Join-Path $work 'version'
    & $PythonExecutable (Join-Path $PSScriptRoot 'version_metadata.py') `
        --release-version $ReleaseVersion --output $versionRoot
    if ($LASTEXITCODE -ne 0) { throw 'Windows version metadata generation failed.' }
    $versionMetadata = Get-Content -LiteralPath (Join-Path $versionRoot 'version-metadata.json') -Raw | ConvertFrom-Json
    $releaseRuntimeVersion = @($versionMetadata.file_version_tuple)[0..2] -join '.'
    if ($releaseRuntimeVersion -ne [string]$worldMetadata.world_version) {
        throw "Release version $ReleaseVersion does not match world runtime version $($worldMetadata.world_version)."
    }
    $versionArgument = @(
        '--version-file', (Join-Path $versionRoot 'backend-version.txt'),
        '--add-data', "$(Join-Path $versionRoot 'version-metadata.json');."
    )
    if (-not $ApworldPath) { $ApworldPath = Join-Path $repo 'build/bloodborne.apworld' }
}
if ($ApworldPath -and -not (Test-Path -LiteralPath $ApworldPath -PathType Leaf)) {
    throw "bloodborne.apworld not found: $ApworldPath"
}
$worldData = @(Get-ChildItem -LiteralPath (Join-Path $repo 'worlds/bloodborne') -File |
    Where-Object { $_.Extension -in '.json', '.tsv' } |
    ForEach-Object { '--add-data'; "$($_.FullName);worlds/bloodborne" })
$bossData = @(Get-ChildItem -LiteralPath (Join-Path $repo 'tools/bb_enemizer') -Filter '*.json' -File |
    ForEach-Object { '--add-data'; "$($_.FullName);tools/bb_enemizer" })
& $PythonExecutable -m PyInstaller --noconfirm --clean --console --onedir --name bb-ap-backend `
    --paths $repo --collect-submodules worlds `
    --hidden-import tools.build_standalone_randomizer `
    --hidden-import tools.export_standalone_mod `
    --hidden-import tools.bb_standalone.generate --hidden-import tools.bb_enemizer.cli `
    --add-data "$(Join-Path $repo 'research/bb_inputs.db');research" `
    --add-data "$(Join-Path $repo 'research/enemizer');research/enemizer" @worldData @bossData `
    --add-data "$(Join-Path $repo 'tools/bb_standalone/award_targets.json');tools/bb_standalone" `
    @versionArgument --distpath (Join-Path $work 'dist') --workpath (Join-Path $work 'pyi') --specpath $work `
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
$readme = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'FORK-README.txt') -Raw
if ($ReleaseVersion) {
    $readme = $readme.Replace('BBLauncher-AP: local next-run candidate', "BBLauncher-AP $ReleaseVersion")
    $readme = $readme.Replace('The candidate has offline build and fixture-test evidence, not completed live',
        'This package has offline build and fixture-test evidence, not completed live')
    $readme = $readme.Replace('This candidate is a separate application folder.',
        'This release is a separate application folder.')
}
[IO.File]::WriteAllText((Join-Path $package 'README.txt'), $readme, [Text.UTF8Encoding]::new($false))
New-Item -ItemType Directory -Path (Join-Path $package 'docs') | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'docs/BBLAUNCHER-NEXT-RUN.md') -Destination (Join-Path $package 'docs/BBLAUNCHER-NEXT-RUN.md')
if ($ApworldPath) {
    New-Item -ItemType Directory -Path (Join-Path $package 'worlds') | Out-Null
    Copy-Item -LiteralPath $ApworldPath -Destination (Join-Path $package 'worlds/bloodborne.apworld')
}
$licenses = Join-Path $package 'licenses'
New-Item -ItemType Directory -Path $licenses | Out-Null
$forkLicense = Join-Path $ForkSourceRoot 'LICENSE'
if (-not (Test-Path -LiteralPath $forkLicense -PathType Leaf)) { throw "Fork GPL license is missing: $forkLicense" }
Copy-Item -LiteralPath $forkLicense -Destination (Join-Path $licenses 'BBLauncher-GPL-3.0.txt')
Copy-Item -LiteralPath (Join-Path $repo 'bblauncher_fork/LICENSE-INVENTORY.md') -Destination (Join-Path $licenses 'LICENSE-INVENTORY.md')
$externalRoot = Join-Path $ForkSourceRoot 'externals'
if (Test-Path -LiteralPath $externalRoot -PathType Container) {
    Get-ChildItem -LiteralPath $externalRoot -Recurse -File |
        Where-Object { $_.Name -match '^(LICENSE|COPYING|NOTICE)(\.|$)' } |
        ForEach-Object {
            $relative = [IO.Path]::GetRelativePath($externalRoot, $_.FullName)
            $destination = Join-Path (Join-Path $licenses 'fork-externals') $relative
            New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destination
        }
}
$qtSbom = Join-Path (Split-Path $QtBin -Parent) 'sbom'
if (Test-Path -LiteralPath $qtSbom -PathType Container) {
    $qtNotices = Join-Path $licenses 'qt-sbom'
    New-Item -ItemType Directory -Path $qtNotices | Out-Null
    Get-ChildItem -LiteralPath $qtSbom -Filter '*.spdx' -File |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $qtNotices $_.Name) }
}
$backendRevision = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot record backend source revision.' }
$forkRevision = (& git -C $ForkSourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot record fork source revision.' }
$backendRemote = (& git -C $repo remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot record backend source remote.' }
$forkRemote = (& git -C $ForkSourceRoot remote get-url fork 2>$null)
if ($LASTEXITCODE -ne 0) { $forkRemote = (& git -C $ForkSourceRoot remote get-url origin).Trim() }
if ($LASTEXITCODE -ne 0) { throw 'Cannot record fork source remote.' }
$sourceProvenance = [ordered]@{
    format = 'bb-ap-fork-source-provenance-v1'
    backend = [ordered]@{ remote = $backendRemote; revision = $backendRevision }
    fork = [ordered]@{ remote = ($forkRemote | Out-String).Trim(); revision = $forkRevision }
    client = [ordered]@{ revision = $ClientRef; build_input_sha256 = (Get-FileHash -LiteralPath $ClientPath -Algorithm SHA256).Hash.ToLowerInvariant() }
    build_instructions = @('packaging/build_bblauncher.ps1',
        'packaging/build_fork_bundle.ps1', '.github/workflows/release.yaml',
        'packaging/FORK-README.txt')
}
[IO.File]::WriteAllText((Join-Path $package 'SOURCE-PROVENANCE.json'),
    ($sourceProvenance | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
$qtMode = if ($DebugBuild) { '--debug' } else { '--release' }
& $deployQt $qtMode --compiler-runtime --qmldir (Join-Path $ForkSourceRoot 'dist') --dir $package $exe
if ($LASTEXITCODE -ne 0) { throw 'Qt dependency deployment failed.' }
& $PythonExecutable (Join-Path $PSScriptRoot 'smoke_fork_bundle.py') $package
if ($LASTEXITCODE -ne 0) { throw 'Frozen fork bundle smoke failed.' }
$manifest = [ordered]@{
    format = 'bb-ap-fork-candidate-v1'
    backend_revision = $backendRevision
    backend_dirty = [bool]((& git -C $repo status --porcelain --untracked-files=no | Out-String).Trim())
    fork_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    client_ref = $ClientRef
    client_sha256 = (Get-FileHash -LiteralPath $ClientPath -Algorithm SHA256).Hash.ToLowerInvariant()
    debug_build = [bool]$DebugBuild
    game_tested = $false
    release_version = $ReleaseVersion
    version = $versionMetadata
    includes_apworld = [bool]$ApworldPath
    apworld_sha256 = if ($ApworldPath) { (Get-FileHash -LiteralPath (Join-Path $package 'worlds/bloodborne.apworld') -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
}
if ($ForkSourceRoot) {
    $manifest.fork_revision = $forkRevision
    $manifest.fork_dirty = [bool]((& git -C $ForkSourceRoot status --porcelain --untracked-files=no | Out-String).Trim())
}
$manifest.tools = @(Get-ChildItem -LiteralPath (Join-Path $backend 'tools') -File -Recurse |
    Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = [IO.Path]::GetRelativePath($package, $_.FullName).Replace('\', '/')
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
$manifest.enemy_catalogs = @(Get-ChildItem -LiteralPath (Join-Path $repo 'research/enemizer') -Filter '*.json' |
    Sort-Object Name | ForEach-Object {
        [ordered]@{ name = $_.Name; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
$manifest.files = @(Get-ChildItem -LiteralPath $package -File -Recurse |
    Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = [IO.Path]::GetRelativePath($package, $_.FullName).Replace('\', '/')
            size = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $package 'candidate-manifest.json') -Encoding utf8
Write-Host "Created local candidate: $package"
Write-Host 'Backend package smoke passed. This does not claim gameplay acceptance.'
