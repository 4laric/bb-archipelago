[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SoulsFormatsNextRoot,
    [string]$ClientPath,
    [string]$OutputRoot,
    [string]$SuppressionBuild,
    [switch]$SkipClient,
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $repo "build"))
if (-not $OutputRoot) {
    $OutputRoot = $allowedRoot
}
$resolvedOutput = [IO.Path]::GetFullPath($OutputRoot)
$allowedPrefix = $allowedRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not ($resolvedOutput + [IO.Path]::DirectorySeparatorChar).StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must be inside $allowedRoot"
}

$soulsRoot = [IO.Path]::GetFullPath($SoulsFormatsNextRoot)
$soulsProject = Join-Path $soulsRoot "SoulsFormats\SoulsFormats.csproj"
if (-not (Test-Path -LiteralPath $soulsProject -PathType Leaf)) {
    throw "SoulsFormatsNEXT project not found: $soulsProject"
}
if (-not $SkipClient) {
    if (-not $ClientPath -or -not (Test-Path -LiteralPath $ClientPath -PathType Leaf)) {
        throw "Provide -ClientPath for a release package, or use -SkipClient for a tools-only CI artifact."
    }
}

$package = Join-Path $resolvedOutput "BloodborneAPLauncher"
$work = Join-Path $resolvedOutput "launcher-package-work"

# A running launcher locks its bundled DLLs; deleting the old package then
# fails with a bare access-denied. Name the culprit process instead.
$running = @(Get-Process | Where-Object {
    try {
        $_.Path -and $_.Path.StartsWith($package, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        $false
    }
})
if ($running.Count) {
    $names = ($running | ForEach-Object { "$($_.Name) (pid $($_.Id))" }) -join ", "
    throw "Cannot rebuild the package while it is running: $names. Close the launcher and re-run."
}

foreach ($target in @($package, $work)) {
    $full = [IO.Path]::GetFullPath($target)
    if (-not ($full + [IO.Path]::DirectorySeparatorChar).StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unexpected build path: $full"
    }
    if (Test-Path -LiteralPath $full) {
        try {
            Remove-Item -LiteralPath $full -Recurse -Force
        } catch [UnauthorizedAccessException] {
            throw "A file under $full is locked by another process (often a still-running launcher or a shell/console sitting in that directory). Close it and re-run. $($_.Exception.Message)"
        }
    }
}
New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null
New-Item -ItemType Directory -Path $work -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $work "spec") -Force | Out-Null

$pyinstaller = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--paths", $repo,
    "--workpath", (Join-Path $work "pyi-work"),
    "--specpath", (Join-Path $work "spec")
)
& python @pyinstaller --windowed --onedir --name BloodborneAPLauncher `
    --distpath (Join-Path $work "launcher-dist") `
    --add-data "$(Join-Path $repo 'research\enemizer\enemy_tags.json');research\enemizer" `
    --add-data "$(Join-Path $repo 'research\enemizer\slot_policy.json');research\enemizer" `
    (Join-Path $repo "packaging\launcher_entry.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller launcher build failed." }

& python @pyinstaller --console --onedir --name BBEnemizerPlanner `
    --distpath (Join-Path $work "planner-dist") `
    (Join-Path $repo "packaging\enemizer_planner_entry.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller planner build failed." }

$native = Join-Path $work "native"
New-Item -ItemType Directory -Path $native -Force | Out-Null
$projects = @(
    @{ Project = "tools\bb_enemizer_writer\BBEnemizerWriter.csproj"; Name = "BBEnemizerWriter.exe" },
    @{ Project = "tools\bb_suppression_writer\BBSuppressionWriter.csproj"; Name = "BBSuppressionWriter.exe" },
    @{ Project = "tools\bb_toast_writer\BBToastWriter.csproj"; Name = "BBToastWriter.exe" },
    @{ Project = "tools\msbb_miner\MSBBMiner.csproj"; Name = "MSBBMiner.exe" }
)
foreach ($item in $projects) {
    $project = Join-Path $repo $item.Project
    $publish = Join-Path $native ([IO.Path]::GetFileNameWithoutExtension($item.Name))
    & dotnet publish $project -c Release -r win-x64 --self-contained true `
        -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
        "-p:SoulsFormatsNextRoot=$soulsRoot" -o $publish -v:minimal
    if ($LASTEXITCODE -ne 0) { throw "Native publish failed: $project" }
    if (-not (Test-Path -LiteralPath (Join-Path $publish $item.Name) -PathType Leaf)) {
        throw "Native publish did not produce $($item.Name)"
    }
}

Copy-Item -LiteralPath (Join-Path $work "launcher-dist\BloodborneAPLauncher") -Destination $package -Recurse
$tools = Join-Path $package "tools"
New-Item -ItemType Directory -Path $tools -Force | Out-Null
$plannerPackage = Join-Path $tools "BBEnemizerPlanner"
Copy-Item -LiteralPath (Join-Path $work "planner-dist\BBEnemizerPlanner") -Destination $plannerPackage -Recurse
foreach ($item in $projects) {
    $publish = Join-Path $native ([IO.Path]::GetFileNameWithoutExtension($item.Name))
    Copy-Item -LiteralPath (Join-Path $publish $item.Name) -Destination $tools
}
$clientRecord = $null
if (-not $SkipClient) {
    $clientDestination = Join-Path $tools "bb-ap-client.exe"
    Copy-Item -LiteralPath ([IO.Path]::GetFullPath($ClientPath)) -Destination $clientDestination
    $clientRecord = [ordered]@{
        path = "tools/bb-ap-client.exe"
        sha256 = (Get-FileHash -LiteralPath $clientDestination -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

New-Item -ItemType Directory -Path (Join-Path $package "docs") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repo "docs\LAUNCHER.md") -Destination (Join-Path $package "docs\LAUNCHER.md")
Copy-Item -LiteralPath (Join-Path $repo "docs\PLAYTESTING.md") -Destination (Join-Path $package "docs\PLAYTESTING.md")
Copy-Item -LiteralPath (Join-Path $repo "SECURITY.md") -Destination (Join-Path $package "SECURITY.md")
Copy-Item -LiteralPath (Join-Path $repo "packaging\PACKAGE-README.txt") -Destination (Join-Path $package "README.txt")
Copy-Item -LiteralPath (Join-Path $repo "tables\Bloodborne-native-item-grant-auto-v2.CT") -Destination (Join-Path $package "tools")

# Ship the suppression binder + manifest beside the launcher so the UI
# auto-fills the pair from application_root()/work/vanilla-suppression-build
# and the player never has to locate either file.
if (-not $SuppressionBuild) {
    $defaultSuppression = Join-Path $repo "work\vanilla-suppression-build"
    if ((Test-Path -LiteralPath (Join-Path $defaultSuppression "gameparam.parambnd.dcx") -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $defaultSuppression "build-manifest.json") -PathType Leaf)) {
        $SuppressionBuild = $defaultSuppression
    }
}
if ($SuppressionBuild) {
    $suppressionDestination = Join-Path $package "work\vanilla-suppression-build"
    New-Item -ItemType Directory -Path $suppressionDestination -Force | Out-Null
    foreach ($name in @("gameparam.parambnd.dcx", "build-manifest.json")) {
        $source = Join-Path $SuppressionBuild $name
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Suppression build is missing ${name}: $source"
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $suppressionDestination $name)
    }
    Write-Host "  bundled suppression build: $SuppressionBuild"
}

$revision = (& git -C $repo rev-parse HEAD).Trim()
$dirty = -not [string]::IsNullOrWhiteSpace((& git -C $repo status --porcelain --untracked-files=no | Out-String))
$records = Get-ChildItem -LiteralPath $package -File -Recurse | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($package.Length + 1).Replace("\", "/")
        size = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest = [ordered]@{
    format = "bb-launcher-package-v1"
    platform = "win-x64"
    revision = $revision
    dirty_worktree = $dirty
    includes_client = (-not $SkipClient)
    includes_suppression = [bool]$SuppressionBuild
    includes_game_files = $false
    client = $clientRecord
    files = @($records)
}
$manifestJson = $manifest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText(
    (Join-Path $package "package-manifest.json"),
    $manifestJson,
    [Text.UTF8Encoding]::new($false)
)

if (-not $NoArchive) {
    $archive = Join-Path $resolvedOutput "BloodborneAPLauncher-win-x64.zip"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Compress-Archive -LiteralPath $package -DestinationPath $archive -CompressionLevel Optimal
    Write-Host "Created $archive"
}
Write-Host "Created $package"
