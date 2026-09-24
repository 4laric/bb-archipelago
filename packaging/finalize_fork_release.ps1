[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PackageRoot,
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [string]$ExpectedSignerSubject = $env:EXPECTED_SIGNER_SUBJECT
)

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$build = [IO.Path]::GetFullPath((Join-Path $repo 'build')).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$package = [IO.Path]::GetFullPath($PackageRoot)
$archive = [IO.Path]::GetFullPath($ArchivePath)
foreach ($path in @($package, $archive)) {
    if (-not ($path + [IO.Path]::DirectorySeparatorChar).StartsWith($build, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Release output must stay inside $build : $path"
    }
}
if (-not (Test-Path -LiteralPath $package -PathType Container)) { throw "Package not found: $package" }
if (Test-Path -LiteralPath $archive) { throw "Archive already exists: $archive" }
if ([string]::IsNullOrWhiteSpace($ExpectedSignerSubject)) {
    throw 'ExpectedSignerSubject is required (or set EXPECTED_SIGNER_SUBJECT).'
}
$manifestPath = Join-Path $package 'candidate-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Candidate manifest is missing: $manifestPath"
}

# Keep this catalog in sync with release signing.  The duplicate client in
# tools is optional in older tool directories, but it must be signed if it is
# shipped.  Qt and Python runtime DLLs are third-party, not in this catalog.
$required = @(
    'BBLauncher-AP.exe',
    'ap_backend/bb-ap-backend.exe',
    'ap_backend/ap-client/bb-ap-client.exe',
    'ap_backend/tools/BBSuppressionWriter.exe',
    'ap_backend/tools/BBEventWriter.exe',
    'ap_backend/tools/BBToastWriter.exe',
    'ap_backend/tools/BBEnemizerWriter.exe',
    'ap_backend/tools/MSBBMiner.exe',
    'ap_backend/tools/BBEnemizerPlanner/BBEnemizerPlanner.exe',
    'ap_backend/tools/BBBossEncounterBuilder/BBBossEncounterBuilder.exe'
)
$optional = @('ap_backend/tools/bb-ap-client.exe')
$catalog = [Collections.Generic.List[string]]::new()
foreach ($relative in $required) {
    $path = Join-Path $package $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Signing catalog file is missing: $relative"
    }
    $catalog.Add($relative)
}
foreach ($relative in $optional) {
    if (Test-Path -LiteralPath (Join-Path $package $relative) -PathType Leaf) { $catalog.Add($relative) }
}
$signed = @()
foreach ($relative in $catalog) {
    $path = Join-Path $package $relative
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    if ($signature.Status -ne 'Valid') {
        throw "Authenticode verification failed for ${relative}: $($signature.Status) $($signature.StatusMessage)"
    }
    if (-not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -ne $ExpectedSignerSubject) {
        throw "Unexpected signer for ${relative}: $($signature.SignerCertificate.Subject)"
    }
    if (-not $signature.TimeStamperCertificate) {
        throw "Authenticode timestamp is missing for $relative"
    }
    $signed += [ordered]@{
        path = $relative
        signer_subject = $signature.SignerCertificate.Subject
        timestamp_subject = $signature.TimeStamperCertificate.Subject
    }
    Write-Host "SIGNATURE VERIFIED $relative"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.format -notin @('bb-ap-fork-candidate-v1', 'bb-ap-fork-release-v1')) {
    throw "Unexpected candidate manifest format: $($manifest.format)"
}
if (-not $manifest.release_version -or -not $manifest.version -or -not $manifest.includes_apworld) {
    throw 'A signed release requires ReleaseVersion and a bundled bloodborne.apworld.'
}
if ($manifest.debug_build) { throw 'A signed release cannot use a Debug Qt launcher.' }
if ($manifest.backend_dirty -or $manifest.fork_dirty) {
    throw 'Release source revisions must be clean at build time.'
}
$backendRevision = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $backendRevision -ne $manifest.backend_revision) {
    throw "Backend revision changed since packaging: $backendRevision"
}
if ([string]$manifest.release_version -ne "v$($manifest.version.product_version)" -and
    [string]$manifest.release_version -ne [string]$manifest.version.product_version) {
    throw 'Release version and backend version metadata disagree.'
}
$backendVersion = (Get-Item -LiteralPath (Join-Path $package 'ap_backend/bb-ap-backend.exe')).VersionInfo
if ($backendVersion.ProductVersion -ne $manifest.version.product_version -or
    $backendVersion.FileVersion -ne $manifest.version.file_version) {
    throw 'Frozen backend executable version does not match the release manifest.'
}
$sourcePath = Join-Path $package 'SOURCE-PROVENANCE.json'
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw 'Source provenance is missing.' }
$source = Get-Content -LiteralPath $sourcePath -Raw | ConvertFrom-Json
if ($source.format -ne 'bb-ap-fork-source-provenance-v1' -or
    $source.backend.revision -ne $manifest.backend_revision -or
    $source.fork.revision -ne $manifest.fork_revision -or
    $source.client.revision -ne $manifest.client_ref) {
    throw 'Source provenance does not match the candidate manifest.'
}
if ($source.client.build_input_sha256 -ne $manifest.client_sha256 -and
    $manifest.format -eq 'bb-ap-fork-candidate-v1') {
    throw 'Client build input hash does not match source provenance.'
}
foreach ($relative in @('licenses/BBLauncher-GPL-3.0.txt',
                        'licenses/LICENSE-INVENTORY.md', 'worlds/bloodborne.apworld')) {
    if (-not (Test-Path -LiteralPath (Join-Path $package $relative) -PathType Leaf)) {
        throw "Release evidence is missing: $relative"
    }
}
$links = @(Get-ChildItem -LiteralPath $package -Force -Recurse |
    Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 })
if ($links.Count) { throw "Package contains a filesystem link: $($links[0].FullName)" }

$catalogSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($relative in $catalog) { [void]$catalogSet.Add($relative.Replace('\', '/')) }
$actual = @(Get-ChildItem -LiteralPath $package -File -Recurse |
    Where-Object { $_.FullName -ne $manifestPath } | Sort-Object FullName)
$records = @{}
foreach ($item in @($manifest.files)) {
    $relative = [string]$item.path
    if (-not $relative -or $records.ContainsKey($relative)) { throw "Duplicate manifest file: $relative" }
    $records[$relative] = $item
}
if ($records.Count -ne $actual.Count) { throw 'Package file inventory changed since build.' }
foreach ($file in $actual) {
    $relative = [IO.Path]::GetRelativePath($package, $file.FullName).Replace('\', '/')
    if (-not $records.ContainsKey($relative)) { throw "Unrecorded package file: $relative" }
    if (-not $catalogSet.Contains($relative)) {
        $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($file.Length -ne $records[$relative].size -or $digest -ne $records[$relative].sha256) {
            throw "Unsigned package file changed since build: $relative"
        }
    }
}

# All signature and input checks above complete before changing either output.
$manifest.format = 'bb-ap-fork-release-v1'
$manifest.fork_sha256 = (Get-FileHash -LiteralPath (Join-Path $package 'BBLauncher-AP.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest.client_sha256 = (Get-FileHash -LiteralPath (Join-Path $package 'ap_backend/ap-client/bb-ap-client.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest.apworld_sha256 = (Get-FileHash -LiteralPath (Join-Path $package 'worlds/bloodborne.apworld') -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest.tools = @(Get-ChildItem -LiteralPath (Join-Path $package 'ap_backend/tools') -File -Recurse |
    Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = [IO.Path]::GetRelativePath($package, $_.FullName).Replace('\', '/')
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
$manifest.files = @($actual | ForEach-Object {
    [ordered]@{
        path = [IO.Path]::GetRelativePath($package, $_.FullName).Replace('\', '/')
        size = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
})
$manifest | Add-Member -NotePropertyName signatures -NotePropertyValue @($signed) -Force
$manifestTemp = Join-Path $package ".candidate-manifest.$([guid]::NewGuid().ToString('N')).tmp"
try {
    [IO.File]::WriteAllText($manifestTemp, ($manifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    [IO.File]::Move($manifestTemp, $manifestPath, $true)
} finally {
    if (Test-Path -LiteralPath $manifestTemp) { Remove-Item -LiteralPath $manifestTemp -Force }
}
$archiveDir = Split-Path $archive -Parent
New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
$archiveTemp = Join-Path $archiveDir ".BBLauncher-AP.$([guid]::NewGuid().ToString('N')).zip"
try {
    Compress-Archive -LiteralPath $package -DestinationPath $archiveTemp -CompressionLevel Optimal
    Move-Item -LiteralPath $archiveTemp -Destination $archive
} finally {
    if (Test-Path -LiteralPath $archiveTemp) { Remove-Item -LiteralPath $archiveTemp -Force }
}
Write-Host "Created signed release archive: $archive"
