[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SoulsFormatsNextRoot,
    [string]$OutputRoot,
    [string]$PythonExecutable,
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $repo "build"))
if (-not $OutputRoot) { $OutputRoot = $allowedRoot }
$resolvedOutput = [IO.Path]::GetFullPath($OutputRoot)
$allowedPrefix = $allowedRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not ($resolvedOutput + [IO.Path]::DirectorySeparatorChar).StartsWith(
    $allowedPrefix, [StringComparison]::OrdinalIgnoreCase
)) {
    throw "OutputRoot must be inside $allowedRoot"
}

$soulsPin = "7cef52a7366678448d85930eeb8e94093b179d24"
$soulsRoot = [IO.Path]::GetFullPath($SoulsFormatsNextRoot)
$soulsProject = Join-Path $soulsRoot "SoulsFormats\SoulsFormats.csproj"
if (-not (Test-Path -LiteralPath $soulsProject -PathType Leaf)) {
    throw "SoulsFormatsNEXT project not found: $soulsProject"
}
$soulsHead = (& git -C $soulsRoot rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $soulsHead) {
    throw "SoulsFormatsNEXT must be a git checkout pinned to $soulsPin"
}
if ($soulsHead.Trim() -ne $soulsPin) {
    throw "SoulsFormatsNEXT is at $($soulsHead.Trim()), not pinned $soulsPin"
}

if ($PythonExecutable) {
    $python = [IO.Path]::GetFullPath($PythonExecutable)
    $pythonPrefix = @()
} else {
    $python = "py"
    $pythonPrefix = @("-3.12")
}
$pythonVersion = (& $python @pythonPrefix -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne "3.12") {
    throw "Standalone packaging requires Python 3.12 (found $pythonVersion)"
}
& $python @pythonPrefix -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is missing from the selected Python 3.12 environment"
}

$package = Join-Path $resolvedOutput "BloodborneStandaloneRandomizer"
$work = Join-Path $resolvedOutput "standalone-package-work"
$archive = Join-Path $resolvedOutput "BloodborneStandaloneRandomizer-win-x64.zip"
foreach ($target in @($package, $work, $archive)) {
    $full = [IO.Path]::GetFullPath($target)
    if (-not ($full + [IO.Path]::DirectorySeparatorChar).StartsWith(
        $allowedPrefix, [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to clean unexpected build path: $full"
    }
    if (Test-Path -LiteralPath $full) {
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null
New-Item -ItemType Directory -Path $work -Force | Out-Null

$pyinstaller = @()
$pyinstaller += $pythonPrefix
$pyinstaller += @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--console", "--onedir",
    "--name", "BloodborneRandomizer",
    "--paths", $repo,
    "--distpath", (Join-Path $work "dist"),
    "--workpath", (Join-Path $work "pyi-work"),
    "--specpath", (Join-Path $work "spec"),
    "--exclude-module", "BaseClasses",
    "--exclude-module", "Options",
    "--exclude-module", "worlds.AutoWorld",
    "--exclude-module", "worlds.Files",
    "--exclude-module", "worlds.LauncherComponents",
    "--exclude-module", "worlds.bloodborne.client",
    "--exclude-module", "bb_launcher",
    "--exclude-module", "CommonClient",
    "--exclude-module", "MultiServer",
    "--exclude-module", "NetUtils",
    "--add-data", "$(Join-Path $repo 'tools\bb_standalone\award_targets.json');tools\bb_standalone",
    "--add-data", "$(Join-Path $repo 'research\enemizer\enemy_tags.json');research\enemizer",
    "--add-data", "$(Join-Path $repo 'research\enemizer\slot_policy.json');research\enemizer",
    "--add-data", "$(Join-Path $repo 'research\enemizer\archetype_facts.json');research\enemizer",
    "--add-data", "$(Join-Path $repo 'research\bb_inputs.db');research"
)
$worldData = Get-ChildItem -LiteralPath (Join-Path $repo "worlds\bloodborne") -File |
    Where-Object { $_.Extension -in ".tsv", ".json" } |
    Sort-Object Name
if ($worldData.Count -lt 2) { throw "No Bloodborne standalone world data found" }
foreach ($file in $worldData) {
    $pyinstaller += @("--add-data", "$($file.FullName);worlds\bloodborne")
}
$pyinstaller += (Join-Path $repo "packaging\standalone_entry.py")
& $python @pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller standalone build failed" }

$nativeRoot = Join-Path $work "native"
New-Item -ItemType Directory -Path $nativeRoot -Force | Out-Null
$projects = @(
    @{
        Project = "tools\bb_suppression_writer\BBSuppressionWriter.csproj"
        BuiltName = "BBSuppressionWriter.exe"
        PackageName = "BBStandaloneItemWriter.exe"
    },
    @{
        Project = "tools\bb_enemizer_writer\BBEnemizerWriter.csproj"
        BuiltName = "BBEnemizerWriter.exe"
        PackageName = "BBStandaloneEnemyWriter.exe"
    }
)
foreach ($item in $projects) {
    $project = Join-Path $repo $item.Project
    $publish = Join-Path $nativeRoot ([IO.Path]::GetFileNameWithoutExtension($item.PackageName))
    & dotnet publish $project -c Release -r win-x64 --self-contained true `
        -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:DebugType=None -p:DebugSymbols=false `
        "-p:SoulsFormatsNextRoot=$soulsRoot" -o $publish -v:minimal
    if ($LASTEXITCODE -ne 0) { throw "Native publish failed: $project" }
    $built = Join-Path $publish $item.BuiltName
    if (-not (Test-Path -LiteralPath $built -PathType Leaf)) {
        throw "Native publish did not produce $($item.BuiltName)"
    }
}

Copy-Item -LiteralPath (Join-Path $work "dist\BloodborneRandomizer") `
    -Destination $package -Recurse
$tools = Join-Path $package "tools"
New-Item -ItemType Directory -Path $tools -Force | Out-Null
foreach ($item in $projects) {
    $publish = Join-Path $nativeRoot ([IO.Path]::GetFileNameWithoutExtension($item.PackageName))
    Copy-Item -LiteralPath (Join-Path $publish $item.BuiltName) `
        -Destination (Join-Path $tools $item.PackageName)
}
Copy-Item -LiteralPath (Join-Path $repo "packaging\STANDALONE-README.txt") `
    -Destination (Join-Path $package "README.txt")

$forbidden = Get-ChildItem -LiteralPath $package -File -Recurse | Where-Object {
    $relative = $_.FullName.Substring($package.Length + 1).Replace("\", "/")
    ($_.Extension -eq ".apworld") -or
    ($relative -match "(^|/)(BaseClasses|Options|CommonClient|MultiServer|NetUtils)(\.|/)") -or
    ($relative -match "bb-ap-client|ArchipelagoServer|worlds/bloodborne/client")
}
if ($forbidden.Count) {
    throw "Standalone package contains forbidden network runtime files: $($forbidden.FullName -join ', ')"
}

$revision = (& git -C $repo rev-parse HEAD).Trim()
$dirty = -not [string]::IsNullOrWhiteSpace(
    (& git -C $repo status --porcelain | Out-String)
)
$records = Get-ChildItem -LiteralPath $package -File -Recurse |
    Sort-Object FullName |
    ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($package.Length + 1).Replace("\", "/")
            size = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
$manifest = [ordered]@{
    format = "bb-standalone-package-v1"
    platform = "win-x64"
    revision = $revision
    dirty_worktree = $dirty
    souls_formats_next = $soulsPin
    includes_player_game_files = $false
    includes_archipelago_runtime = $false
    includes_pinned_research_bundle = $true
    gameplay_tested = $false
    files = @($records)
}
$manifestJson = $manifest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText(
    (Join-Path $package "package-manifest.json"),
    $manifestJson + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)

if (-not $NoArchive) {
    Compress-Archive -LiteralPath $package -DestinationPath $archive -CompressionLevel Optimal
    Write-Host "Created $archive"
}
Write-Host "Created $package"
