# build.ps1 -- Bloodborne Archipelago build driver
#
# Usage from the repository root:
#   .\build.ps1 -Test          # run the dependency-free unit tests
#   .\build.ps1 -Data          # regenerate joined events, catalog, and wiki-validation tables
#   .\build.ps1 -Preflight     # verify tests, generated outputs, and shipping boundaries
#   .\build.ps1 -Apworld       # package worlds\bloodborne -> build\bloodborne.apworld
#   .\build.ps1 -All           # Data + Test + Preflight + Apworld
#   .\build.ps1 -Clean         # remove only build\ outputs
#   .\build.ps1 -Package -SoulsFormatsNextRoot C:\path\to\SoulsFormatsNEXT [-ClientRepo C:\path\to\from-software-archipelago-clients] [-GameRoot D:\shadPS4\games]
#                              # full player build: AP client + suppression binder + apworld + launcher package
#                              # (-ClientRepo auto-discovers the sibling er-archipelago checkout; -GameRoot makes the
#                              #  suppression build target the installed patch-layer gameparam so the launcher check passes)
#   .\build.ps1 -Doctor [-LauncherSettings C:\path\to\launcher-settings.json]
#                              # preflight the build-side and (with -LauncherSettings) player-side chains (#103)
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
    [switch]$Doctor,
    [string]$LauncherSettings,
    [string]$SoulsFormatsNextRoot = $env:SOULSFORMATS_NEXT,
    [string]$ClientRepo,
    [string]$ClientPath,
    [string]$GameRoot,
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

# #104: -ClientRepo is only needed for nonstandard layouts. Probe the known
# sibling checkouts before asking for the flag.
function Resolve-ClientRepo {
    if ($ClientRepo) { return $ClientRepo }
    $candidates = @(
        (Join-Path $Repo "..\er-archipelago\from-software-archipelago-clients"),
        (Join-Path $HOME "Documents\er-archipelago\from-software-archipelago-clients")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate "Cargo.toml") -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

# #104: the launcher validates the suppression binder against the INSTALLED
# gameparam, so the binder must be built from exactly those bytes -- patch
# layer first, base as fallback. -GameRoot wins, then the extracted install
# tree beside the artifacts; $null means fall back to the artifacts copy.
function Resolve-SuppressionGameParam {
    $relative = "dvdroot_ps4\param\gameparam\gameparam.parambnd.dcx"
    $roots = @()
    if ($GameRoot) { $roots += $GameRoot }
    $roots += (Join-Path $ArtifactRoot "install")
    foreach ($root in $roots) {
        $base = $root
        if ((Split-Path -Leaf $base) -eq "CUSA03173") { $base = Split-Path -Parent $base }
        foreach ($layer in @("CUSA03173-patch", "CUSA03173-UPDATE", "CUSA03173")) {
            $candidate = Join-Path $base (Join-Path $layer $relative)
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return $candidate
            }
        }
    }
    return $null
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

if (-not ($Test -or $Data -or $Preflight -or $Apworld -or $Clean -or $Package -or $Doctor)) {
    Get-Content -LiteralPath $PSCommandPath | Select-Object -Skip 1 -First 14 |
        ForEach-Object { $_ -replace '^#\s?', '' }
    return
}

if ($Doctor) {
    # One-shot preflight of every input -Package and the launcher need, so the
    # player chain fails here in one list instead of one error per run (#103).
    # ASCII only: Windows PowerShell 5 reads this file as ANSI.
    Step "Doctor: build-side chain"
    $script:DoctorFailures = 0
    function Doctor-Line([string]$Status, [string]$Name, [string]$Detail, [string]$Remedy = "") {
        $color = @{ PASS = "Green"; WARN = "Yellow"; FAIL = "Red" }[$Status]
        Write-Host "  [$Status] ${Name}: $Detail" -ForegroundColor $color
        if ($Remedy) { Write-Host "         -> $Remedy" -ForegroundColor $color }
        if ($Status -eq "FAIL") { $script:DoctorFailures++ }
    }

    if (-not $SoulsFormatsNextRoot) {
        Doctor-Line FAIL "SoulsFormatsNEXT" "not provided" "pass -SoulsFormatsNextRoot or set SOULSFORMATS_NEXT"
    } elseif (-not (Test-Path -LiteralPath (Join-Path $SoulsFormatsNextRoot "SoulsFormats\SoulsFormats.csproj") -PathType Leaf)) {
        Doctor-Line FAIL "SoulsFormatsNEXT" "no SoulsFormats csproj under $SoulsFormatsNextRoot" "check out JKAnderson/SoulsFormatsNEXT and pass its root"
    } else {
        $sfnHead = $null
        try {
            $sfnHead = (& git -C $SoulsFormatsNextRoot rev-parse HEAD 2>$null)
            if ($LASTEXITCODE -ne 0) { $sfnHead = $null }
        } catch { $sfnHead = $null }
        if ($null -eq $sfnHead) {
            Doctor-Line WARN "SoulsFormatsNEXT" "not a git checkout; pinned $SoulsFormatsNextPin unverifiable"
        } elseif ($sfnHead.Trim() -ne $SoulsFormatsNextPin) {
            Doctor-Line FAIL "SoulsFormatsNEXT" "at $($sfnHead.Trim()), not the pinned $SoulsFormatsNextPin" "git -C $SoulsFormatsNextRoot fetch; git -C $SoulsFormatsNextRoot checkout $SoulsFormatsNextPin"
        } else {
            Doctor-Line PASS "SoulsFormatsNEXT" "checkout at the pinned $SoulsFormatsNextPin"
        }
    }

    if ($ClientPath) {
        if (Test-Path -LiteralPath $ClientPath -PathType Leaf) {
            Doctor-Line PASS "AP client" "$ClientPath"
        } else {
            Doctor-Line FAIL "AP client" "-ClientPath $ClientPath does not exist"
        }
    } else {
        $doctorClientRepo = $ClientRepo
        if (-not $doctorClientRepo) { $doctorClientRepo = Resolve-ClientRepo }
        $discoveryNote = if ($ClientRepo) { "" } elseif ($doctorClientRepo) { " (auto-discovered)" } else { "" }
        if ($doctorClientRepo -and (Test-Path -LiteralPath (Join-Path $doctorClientRepo "Cargo.toml") -PathType Leaf)) {
            Doctor-Line PASS "AP client" "client checkout at $doctorClientRepo$discoveryNote (cargo build runs during -Package)"
        } elseif ($doctorClientRepo) {
            Doctor-Line FAIL "AP client" "no Cargo.toml under $doctorClientRepo" "check the path letter by letter -- a typo here costs a full package cycle"
        } else {
            Doctor-Line FAIL "AP client" "neither -ClientRepo nor -ClientPath given, and no sibling checkout found" "expected at ..\er-archipelago\from-software-archipelago-clients or ~\Documents\er-archipelago\from-software-archipelago-clients"
        }
    }

    $doctorSuppressionSource = Resolve-SuppressionGameParam
    if ($null -ne $doctorSuppressionSource) {
        Doctor-Line PASS "suppression source" "$doctorSuppressionSource (installed game layer; -Package builds the binder from these bytes)"
    } else {
        Doctor-Line WARN "suppression source" "no installed game found; -Package would fall back to the artifacts gameparam" "pass -GameRoot so the binder matches the installed patch layer the launcher validates"
    }

    $doctorGameparam = Join-Path $GameArtifacts "param\gameparam\gameparam.parambnd.dcx"
    $doctorParamdef = Join-Path $GameArtifacts "paramdef\paramdef.paramdefbnd.dcx"
    foreach ($pair in @(@("artifact gameparam", $doctorGameparam), @("artifact paramdef", $doctorParamdef))) {
        if (Test-Path -LiteralPath $pair[1] -PathType Leaf) {
            Doctor-Line PASS $pair[0] $pair[1]
        } else {
            Doctor-Line FAIL $pair[0] "missing: $($pair[1])" "extract the game files with the UMG/UXM unpack step first"
        }
    }

    $doctorSuppression = Join-Path $Repo "work\vanilla-suppression-build\build-manifest.json"
    if (Test-Path -LiteralPath $doctorSuppression -PathType Leaf) {
        Doctor-Line PASS "suppression binder" "work\vanilla-suppression-build kept (remove it to rebuild)"
    } else {
        Doctor-Line WARN "suppression binder" "not built yet; -Package will build it"
    }

    foreach ($locker in @("BloodborneAPLauncher", "shadPS4", "cheatengine")) {
        if (Get-Process -Name $locker -ErrorAction SilentlyContinue) {
            Doctor-Line WARN "running process $locker" "$locker is running; it can hold package or game files during a rebuild"
        }
    }

    if ($LauncherSettings) {
        Step "Doctor: player-side chain"
        Invoke-Python @("-m", "bb_launcher", "doctor", "--settings", $LauncherSettings)
    }

    if ($script:DoctorFailures -gt 0) {
        throw "Doctor found $script:DoctorFailures build-side failure(s) -- see the FAIL lines above."
    }
    Write-Host "  Doctor: build-side chain clear" -ForegroundColor Green
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

    if (-not $ClientPath -and -not $ClientRepo) {
        $ClientRepo = Resolve-ClientRepo
        if ($ClientRepo) {
            Write-Host "  auto-discovered client checkout: $ClientRepo" -ForegroundColor Green
        }
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
        $suppressionGameParam = Resolve-SuppressionGameParam
        if ($null -eq $suppressionGameParam) {
            $suppressionGameParam = Join-Path $GameArtifacts "param\gameparam\gameparam.parambnd.dcx"
            Write-Host "  WARNING: no installed game found; building suppression from the artifacts gameparam." -ForegroundColor Yellow
            Write-Host "           The launcher's source-hash check will fail if the installed patch layer differs. Pass -GameRoot to build from the installed game." -ForegroundColor Yellow
        } else {
            Write-Host "  suppression source: $suppressionGameParam (installed game layer)" -ForegroundColor Green
        }
        & (Join-Path $Repo "tools\build_vanilla_suppression.ps1") `
            -GameParam $suppressionGameParam `
            -SoulsFormatsNextRoot $SoulsFormatsNextRoot -OutputRoot $suppressionOut -Apply
    }

    Step "Player package: building the launcher package"
    & (Join-Path $Repo "packaging\build_launcher.ps1") `
        -SoulsFormatsNextRoot $SoulsFormatsNextRoot -ClientPath $ClientPath
    Write-Host "  player build complete: $BuildDir" -ForegroundColor Green
}
