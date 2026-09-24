[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ForkSourceRoot,
    [string]$QtRoot,
    [string]$QtBin,
    [string]$BuildRoot,
    [string]$ClangCl = 'clang-cl.exe',
    [string]$Ninja = 'ninja.exe',
    [string]$PythonExecutable = 'python.exe',
    [int]$Parallel = 4
)

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$fork = [IO.Path]::GetFullPath($ForkSourceRoot)
if (-not (Test-Path -LiteralPath (Join-Path $fork 'CMakeLists.txt') -PathType Leaf)) {
    throw "ForkSourceRoot is not a BBLauncher source checkout: $fork"
}
if ($Parallel -lt 1) { throw 'Parallel must be at least 1.' }
if (-not $BuildRoot) { $BuildRoot = Join-Path $fork 'build-ap-release' }
$build = [IO.Path]::GetFullPath($BuildRoot)

# A package must never quietly use a different fork checkout than its reviewed pin.
$pin = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bblauncher-ref.txt') -Raw).Trim()
if ($pin -notmatch '^[0-9a-f]{40}$') { throw 'packaging/bblauncher-ref.txt must contain one full commit SHA.' }
$revision = (& git -C $fork rev-parse --verify HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $revision -ne $pin) {
    throw "Fork checkout is $revision; packaging/bblauncher-ref.txt requires $pin."
}
$dirty = @(& git -C $fork status --porcelain --untracked-files=no)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) {
    throw 'Fork checkout has tracked changes. Build the pinned commit from a clean checkout.'
}

if (-not $QtRoot -and -not $QtBin) {
    throw 'Pass -QtRoot (Qt 6.10.0 msvc2022_64) or its -QtBin directory.'
}
if ($QtRoot) {
    $qt = [IO.Path]::GetFullPath($QtRoot)
    $expectedBin = [IO.Path]::GetFullPath((Join-Path $qt 'bin'))
    if ($QtBin -and [IO.Path]::GetFullPath($QtBin) -ne $expectedBin) {
        throw 'QtRoot and QtBin point to different Qt installations.'
    }
    $qtBinPath = $expectedBin
} else {
    $qtBinPath = [IO.Path]::GetFullPath($QtBin)
    $qt = [IO.Path]::GetFullPath((Join-Path $qtBinPath '..'))
}
foreach ($component in @('Core', 'Widgets', 'Network', 'Quick', 'QuickWidgets',
                          'WebView', 'WebSockets', 'Concurrent', 'Test')) {
    $config = Join-Path $qt "lib/cmake/Qt6$component/Qt6$($component)Config.cmake"
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
        throw "Qt 6.10.0 msvc2022_64 is missing $component`: $config"
    }
}
foreach ($required in @((Join-Path $qtBinPath 'windeployqt.exe'),
                        (Join-Path $qt 'qml/QtWebView/qmldir'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "The Qt installation lacks a launcher packaging dependency: $required"
    }
}
if (-not $env:INCLUDE -or -not $env:LIB) {
    throw 'Run from an x64 Visual Studio developer environment (for example ilammy/msvc-dev-cmd).'
}

function Resolve-Executable([string]$value) {
    if (Test-Path -LiteralPath $value -PathType Leaf) {
        return [IO.Path]::GetFullPath($value)
    }
    $command = Get-Command $value -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $command) { throw "Required build tool is not available: $value" }
    return $command.Source
}

$cmake = Resolve-Executable 'cmake.exe'
$ctest = Resolve-Executable 'ctest.exe'
$clang = Resolve-Executable $ClangCl
$ninjaExe = Resolve-Executable $Ninja
$python = Resolve-Executable $PythonExecutable
$env:PATH = "$qtBinPath;$env:PATH"
$env:BB_AP_SOURCE_ROOT = $repo
$env:BB_AP_PYTHON = $python
$env:QT_QPA_PLATFORM = 'offscreen'
Remove-Item Env:BB_AP_BACKEND -ErrorAction SilentlyContinue

& git -C $fork submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw 'Fork submodule checkout failed.' }

$configure = @(
    '-S', $fork, '-B', $build, '-G', 'Ninja',
    '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
    '-DBB_AP_FORK=ON', '-DBB_AP_BUILD_TESTS=ON', '-DBUILD_TESTING=ON',
    '-DFORCE_UAC=OFF', '-DUSE_WEBENGINE=OFF', '-DCRYPTOPP_DISABLE_ASM=ON',
    "-DCMAKE_C_COMPILER=$clang", "-DCMAKE_CXX_COMPILER=$clang",
    "-DCMAKE_MAKE_PROGRAM=$ninjaExe", "-DCMAKE_PREFIX_PATH=$qt"
)
& $cmake @configure
if ($LASTEXITCODE -ne 0) { throw 'BBLauncher CMake configuration failed.' }
& $cmake --build $build --target BB_Launcher apbackend_test apui_test --parallel $Parallel
if ($LASTEXITCODE -ne 0) { throw 'BBLauncher or fork test build failed.' }
& $ctest --test-dir $build --output-on-failure --no-tests=error -R '^(apbackend_test|apui_test)$'
if ($LASTEXITCODE -ne 0) { throw 'BBLauncher fork tests failed.' }

$exe = Join-Path $build 'BB_Launcher.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "The launcher build passed without producing $exe"
}
Write-Host "BBLauncher $revision built and tested: $exe"
Write-Output $exe
