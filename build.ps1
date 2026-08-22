# build.ps1 -- Bloodborne Archipelago build driver
#
# Usage from the repository root:
#   .\build.ps1 -Test          # run the dependency-free unit tests
#   .\build.ps1 -Data          # regenerate joined events, catalog, and wiki-validation tables
#   .\build.ps1 -Preflight     # verify tests, generated outputs, and shipping boundaries
#   .\build.ps1 -Apworld       # package worlds\bloodborne -> build\bloodborne.apworld
#   .\build.ps1 -All           # Data + Test + Preflight + Apworld
#   .\build.ps1 -Clean         # remove only build\ outputs
#   .\build.ps1 -Package -SoulsFormatsNextRoot C:\path\to\SoulsFormatsNEXT -ClientRepo C:\path\to\from-software-archipelago-clients
#                              # full player build: AP client + suppression binder + apworld + launcher package
#                              # (-ClientPath skips the cargo build; an existing suppression binder is kept)
#
# The large extracted game tree is a research/build input and is never included in the apworld.

[CmdletBinding()]
param(
    [switch]$Test,
    [switch]$Data,
    [switch]$Preflight,
    [switch]$Apworld,
    [switch]$Clean,
    [switch]$All,
    [switch]$Package,
    [string]$SoulsFormatsNextRoot = $env:SOULSFORMATS_NEXT,
    [string]$ClientRepo,
    [string]$ClientPath,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
# The suppression writer's round-trip verification depends on SoulsFormatsNEXT
# behavior; keep this in sync with the pin in .github/workflows/tests.yaml.
$SoulsFormatsNextPin = "7cef52a7366678448d85930eeb8e94093b179d24"
$WorldDir = Join-Path $Repo "worlds\bloodborne"
$BuildDir = Join-Path $Repo "build"
$ArtifactRoot = Join-Path $Repo "Bloodborne.Game.of.the.Year.Edition.PS4-PRELUDE"
$GameArtifacts = Join-Path $ArtifactRoot "bloodborne_artifacts"
$InstallRoot = Join-Path $ArtifactRoot "install\CUSA03173\dvdroot_ps4"
$Params = Join-Path $InstallRoot "params_dump"
$EventRoot = Join-Path $GameArtifacts "event"
$FmgRoot = Join-Path $GameArtifacts "msg\engus\item-msgbnd-dcx"
# Keep this script ASCII-safe: Windows PowerShell 5 treats UTF-8 without a BOM as ANSI.
$GoodsFmg = Join-Path $FmgRoot ((-join [char[]](0x30A2, 0x30A4, 0x30C6, 0x30E0, 0x540D)) + ".fmg.xml")
$WeaponFmg = Join-Path $FmgRoot ((-join [char[]](0x6B66, 0x5668, 0x540D)) + ".fmg.xml")
$ArmorFmg = Join-Path $FmgRoot ((-join [char[]](0x9632, 0x5177, 0x540D)) + ".fmg.xml")

function Step([string]$Message) {
    Write-Host "`n==== $Message" -ForegroundColor Cyan
}

function Invoke-Python([string[]]$Arguments) {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed (exit $LASTEXITCODE): $Python $($Arguments -join ' ')"
    }
}

function Require-File([string]$Path, [string]$Hint = "") {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        $suffix = if ($Hint) { " -- $Hint" } else { "" }
        throw "Required file missing: $Path$suffix"
    }
}

function Require-Directory([string]$Path, [string]$Hint = "") {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        $suffix = if ($Hint) { " -- $Hint" } else { "" }
        throw "Required directory missing: $Path$suffix"
    }
}

if ($All) {
    $Data = $true
    $Test = $true
    $Preflight = $true
    $Apworld = $true
}

if ($Package) {
    $Apworld = $true
}

if (-not ($Test -or $Data -or $Preflight -or $Apworld -or $Clean -or $Package)) {
    Get-Content -LiteralPath $PSCommandPath | Select-Object -Skip 1 -First 12 |
        ForEach-Object { $_ -replace '^#\s?', '' }
    return
}

if ($Clean) {
    Step "Cleaning build outputs"
    if (Test-Path -LiteralPath $BuildDir) {
        $resolvedBuild = (Resolve-Path -LiteralPath $BuildDir).Path
        $resolvedRepo = (Resolve-Path -LiteralPath $Repo).Path
        if (-not $resolvedBuild.StartsWith($resolvedRepo + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to clean a build directory outside the repository: $resolvedBuild"
        }
        Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
    }
    Write-Host "  build outputs removed" -ForegroundColor Green
}

if ($Data) {
    Step "Regenerating data-derived research tables"
    Require-Directory $Params "dump parameters with Smithbox first"
    Require-Directory $EventRoot "decompile EMEVD with DarkScript first"
    Require-File $GoodsFmg "unpack engus item.msgbnd.dcx with WitchyBND"
    Require-File (Join-Path $Repo "research\mined\msb_treasures.tsv") "run the MSBB miner first"

    Invoke-Python @(
        (Join-Path $Repo "tools\mine_param_joins.py"),
        $Params,
        (Join-Path $Repo "research\mined"),
        (Join-Path $Repo "research\joined")
    )
    Invoke-Python @(
        (Join-Path $Repo "tools\mine_event_flag_joins.py"),
        $EventRoot,
        (Join-Path $Repo "research\joined\fixed_treasure_lots.tsv"),
        (Join-Path $Repo "research\joined")
    )
    Invoke-Python @(
        (Join-Path $Repo "tools\build_location_catalog.py"),
        (Join-Path $Repo "research\joined"),
        $Params,
        $GoodsFmg,
        $WeaponFmg,
        $ArmorFmg,
        (Join-Path $Repo "research\catalog")
    )
    Invoke-Python @(
        (Join-Path $Repo "tools\validate_progression_items.py"),
        $GoodsFmg,
        (Join-Path $Repo "research\joined"),
        $EventRoot,
        (Join-Path $Repo "research\validation\progression_items.tsv")
    )
    Invoke-Python @(
        (Join-Path $Repo "tools\build_emevd_entity_usage.py")
    )
    Write-Host "  derived tables regenerated" -ForegroundColor Green
}

if ($Test) {
    Step "Running tests"
    Invoke-Python @("-m", "unittest", "discover", "-s", (Join-Path $Repo "tests"), "-v")
    Write-Host "  tests passed" -ForegroundColor Green
}

if ($Preflight) {
    Step "Preflight"
    $failures = [Collections.Generic.List[string]]::new()
    foreach ($required in @(
        (Join-Path $WorldDir "__init__.py"),
        (Join-Path $WorldDir "data.py"),
        (Join-Path $WorldDir "model.py"),
        (Join-Path $WorldDir "runtime_bindings.py"),
        (Join-Path $Repo "research\catalog\fixed_location_catalog.tsv"),
        (Join-Path $Repo "research\joined\event_flag_references.tsv"),
        (Join-Path $Repo "research\validation\progression_items.tsv"),
        (Join-Path $Repo "research\enemizer\emevd_entity_usage.tsv"),
        (Join-Path $Repo "research\enemizer\emevd_entity_usage_summary.json")
    )) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            $failures.Add("missing: $required")
        }
    }

    $worldFiles = Get-ChildItem -LiteralPath $WorldDir -Recurse -File -ErrorAction SilentlyContinue
    $forbidden = @($worldFiles | Where-Object {
        $_.Extension -in @(".dcx", ".msb", ".emevd", ".esd", ".ct") -or
        $_.FullName -match '[\\/]research[\\/]'
    })
    if ($forbidden.Count) {
        $failures.Add("shipping world contains research/game artifacts: $($forbidden.FullName -join ', ')")
    }

    Invoke-Python @("-m", "unittest", "discover", "-s", (Join-Path $Repo "tests"), "-v")
    if ($failures.Count) {
        $failures | ForEach-Object { Write-Host "[FAIL] $_" -ForegroundColor Red }
        throw "Preflight failed with $($failures.Count) problem(s)"
    }
    Write-Host "[PASS] model/tests, generated tables, and shipping boundary" -ForegroundColor Green
}

if ($Apworld) {
    Step "Packaging bloodborne.apworld"
    Require-Directory $WorldDir
    $initText = Get-Content -LiteralPath (Join-Path $WorldDir "__init__.py") -Raw
    if ($initText -notmatch '(?m)^\s*class\s+\w*Bloodborne\w*\s*\(') {
        throw "Archipelago World adapter is not implemented yet; refusing to package the design scaffold as playable."
    }

    New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
    $outFile = Join-Path $BuildDir "bloodborne.apworld"
    if (Test-Path -LiteralPath $outFile) {
        Remove-Item -LiteralPath $outFile -Force
    }
    Add-Type -AssemblyName System.IO.Compression | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
    $source = (Resolve-Path -LiteralPath $WorldDir).Path.TrimEnd('\')
    $files = @(Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object {
        $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
        $_.Extension -notin @('.pyc', '.pyo', '.bak')
    })
    $zip = [IO.Compression.ZipFile]::Open($outFile, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($file in $files) {
            $relative = $file.FullName.Substring($source.Length).TrimStart('\', '/').Replace('\', '/')
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $zip, $file.FullName, "bloodborne/$relative"
            ) | Out-Null
        }
    } finally {
        $zip.Dispose()
    }
    Write-Host "  -> $outFile ($($files.Count) files)" -ForegroundColor Green
}

if ($Package) {
    Step "Player package: resolving inputs"
    if (-not $SoulsFormatsNextRoot) {
        throw "Pass -SoulsFormatsNextRoot or set SOULSFORMATS_NEXT."
    }
    Require-File (Join-Path $SoulsFormatsNextRoot "SoulsFormats\SoulsFormats.csproj") "SoulsFormatsNEXT checkout"

    # The suppression writer verifies a byte-faithful round-trip through
    # SoulsFormatsNEXT; an unpinned checkout can change that behavior.
    $sfnHead = $null
    try {
        $sfnHead = (& git -C $SoulsFormatsNextRoot rev-parse HEAD 2>$null)
        if ($LASTEXITCODE -ne 0) { $sfnHead = $null }
    } catch { $sfnHead = $null }
    if ($null -eq $sfnHead) {
        Write-Host "  WARNING: $SoulsFormatsNextRoot is not a git checkout; cannot verify the pinned SoulsFormatsNEXT $SoulsFormatsNextPin" -ForegroundColor Yellow
    } elseif ($sfnHead.Trim() -ne $SoulsFormatsNextPin) {
        throw "SoulsFormatsNEXT is at $($sfnHead.Trim()), not the pinned $SoulsFormatsNextPin -- run: git -C $SoulsFormatsNextRoot fetch; git -C $SoulsFormatsNextRoot checkout $SoulsFormatsNextPin"
    }

    if (-not $ClientPath) {
        if (-not $ClientRepo) {
            throw "Pass -ClientRepo (a from-software-archipelago-clients checkout) or -ClientPath (a built bb-ap-client.exe)."
        }
        Require-File (Join-Path $ClientRepo "Cargo.toml") "from-software-archipelago-clients checkout"
        Step "Player package: building the AP client (cargo release)"
        & cargo build --release -p bb-archipelago --manifest-path (Join-Path $ClientRepo "Cargo.toml")
        if ($LASTEXITCODE -ne 0) { throw "cargo build failed (exit $LASTEXITCODE)" }
        $ClientPath = Join-Path $ClientRepo "target\release\bb-ap-client.exe"
    }
    Require-File $ClientPath "build the client with -ClientRepo or pass -ClientPath"

    Step "Player package: installing packaging requirements"
    Invoke-Python @("-m", "pip", "install", "-q", "-r", (Join-Path $Repo "packaging\requirements-build.txt"))

    $suppressionOut = Join-Path $Repo "work\vanilla-suppression-build"
    if (Test-Path -LiteralPath (Join-Path $suppressionOut "build-manifest.json") -PathType Leaf) {
        Write-Host "  suppression binder kept: $suppressionOut (remove it to rebuild)" -ForegroundColor Green
    } else {
        Step "Player package: building the vanilla suppression binder"
        & (Join-Path $Repo "tools\build_vanilla_suppression.ps1") `
            -SoulsFormatsNextRoot $SoulsFormatsNextRoot -OutputRoot $suppressionOut -Apply
    }

    Step "Player package: building the launcher package"
    & (Join-Path $Repo "packaging\build_launcher.ps1") `
        -SoulsFormatsNextRoot $SoulsFormatsNextRoot -ClientPath $ClientPath
    Write-Host "  player build complete: $BuildDir" -ForegroundColor Green
}
