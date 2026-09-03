[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackageRoot,
    [Parameter(Mandatory = $true)]
    [string]$ReleaseVersion,
    [switch]$SkipClient
)

$ErrorActionPreference = "Stop"
$package = [IO.Path]::GetFullPath($PackageRoot)
$manifestPath = Join-Path $package "package-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Package manifest not found: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$expectedProductVersion = $ReleaseVersion.Trim()
if ($expectedProductVersion.StartsWith("v")) {
    $expectedProductVersion = $expectedProductVersion.Substring(1)
}
if ($manifest.version.product_version -ne $expectedProductVersion) {
    throw "Package product version is $($manifest.version.product_version), expected $expectedProductVersion"
}
$releaseRuntimeVersion = @($manifest.version.file_version_tuple)[0..2] -join "."
if ($releaseRuntimeVersion -ne [string]$manifest.runtime_version) {
    throw "Release version base is $releaseRuntimeVersion, expected runtime version $($manifest.runtime_version)"
}
$expectedFileVersion = [string]$manifest.version.file_version
$expectedProduct = [string]$manifest.version.product_name
$expectedPublisher = [string]$manifest.version.publisher
$expectedCopyright = [string]$manifest.version.copyright

$catalog = @(
    @{ Path = "BloodborneAPLauncher.exe"; Description = "Bloodborne Archipelago Launcher"; Original = "BloodborneAPLauncher.exe" },
    @{ Path = "tools\BBEnemizerPlanner\BBEnemizerPlanner.exe"; Description = "Bloodborne Enemy Randomization Planner"; Original = "BBEnemizerPlanner.exe" },
    @{ Path = "tools\BBEnemizerWriter.exe"; Description = "Bloodborne Enemy Map Writer"; Original = "BBEnemizerWriter.dll" },
    @{ Path = "tools\BBSuppressionWriter.exe"; Description = "Bloodborne Vanilla Award Suppression Writer"; Original = "BBSuppressionWriter.dll" },
    @{ Path = "tools\BBToastWriter.exe"; Description = "Bloodborne Pickup Toast Writer"; Original = "BBToastWriter.dll" },
    @{ Path = "tools\BBEventWriter.exe"; Description = "Bloodborne Event Overlay Writer"; Original = "BBEventWriter.dll" },
    @{ Path = "tools\MSBBMiner.exe"; Description = "Bloodborne Map Inventory Miner"; Original = "MSBBMiner.dll" }
)
if (-not $SkipClient) {
    $catalog += @{ Path = "tools\bb-ap-client.exe"; Description = "Bloodborne Archipelago Client"; Original = "bb-ap-client.exe" }
}

foreach ($item in $catalog) {
    $path = Join-Path $package $item.Path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Version metadata target is missing: $($item.Path)"
    }
    $info = (Get-Item -LiteralPath $path).VersionInfo
    $expected = [ordered]@{
        ProductName = $expectedProduct
        FileDescription = $item.Description
        CompanyName = $expectedPublisher
        ProductVersion = $expectedProductVersion
        FileVersion = $expectedFileVersion
        OriginalFilename = $item.Original
        LegalCopyright = $expectedCopyright
    }
    foreach ($property in $expected.Keys) {
        $actual = [string]$info.$property
        if ($actual -ne [string]$expected[$property]) {
            throw "$($item.Path) $property is '$actual', expected '$($expected[$property])'"
        }
    }
    Write-Host "VERSION VERIFIED $($item.Path) | $($info.ProductVersion) | $($info.FileVersion)"
}
