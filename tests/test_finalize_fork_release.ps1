[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$build = [IO.Path]::GetFullPath((Join-Path $repo 'build'))
$testRoot = Join-Path $build "fork-finalizer-test-$([guid]::NewGuid().ToString('N'))"
$package = Join-Path $testRoot 'BBLauncher-AP'
$archive = Join-Path $testRoot 'BBLauncher-AP-win-x64.zip'
$clientRef = 'c' * 40
$forkRevision = 'b' * 40
$backendRevision = (& git -C $repo rev-parse HEAD).Trim()
$catalog = @(
    'BBLauncher-AP.exe', 'ap_backend/bb-ap-backend.exe',
    'ap_backend/ap-client/bb-ap-client.exe',
    'ap_backend/tools/BBSuppressionWriter.exe',
    'ap_backend/tools/BBEventWriter.exe',
    'ap_backend/tools/BBToastWriter.exe',
    'ap_backend/tools/BBEnemizerWriter.exe',
    'ap_backend/tools/MSBBMiner.exe',
    'ap_backend/tools/BBEnemizerPlanner/BBEnemizerPlanner.exe',
    'ap_backend/tools/BBBossEncounterBuilder/BBBossEncounterBuilder.exe'
)
function Add-File([string]$Relative, [string]$Content) {
    $target = Join-Path $package $Relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    [IO.File]::WriteAllText($target, $Content)
}
try {
    foreach ($relative in $catalog) { Add-File $relative "unsigned:$relative" }
    Add-File 'licenses/BBLauncher-GPL-3.0.txt' 'fixture GPL text'
    Add-File 'licenses/LICENSE-INVENTORY.md' 'fixture inventory'
    Add-File 'worlds/bloodborne.apworld' 'fixture apworld'
    $client = Join-Path $package 'ap_backend/ap-client/bb-ap-client.exe'
    $clientHash = (Get-FileHash -LiteralPath $client -Algorithm SHA256).Hash.ToLowerInvariant()
    $source = [ordered]@{
        format = 'bb-ap-fork-source-provenance-v1'
        backend = @{ revision = $backendRevision; remote = 'fixture-backend' }
        fork = @{ revision = $forkRevision; remote = 'fixture-fork' }
        client = @{ revision = $clientRef; build_input_sha256 = $clientHash }
    }
    $source | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $package 'SOURCE-PROVENANCE.json')
    $records = @(Get-ChildItem -LiteralPath $package -File -Recurse | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = [IO.Path]::GetRelativePath($package, $_.FullName).Replace('\', '/')
            size = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    $manifest = [ordered]@{
        format = 'bb-ap-fork-candidate-v1'
        backend_revision = $backendRevision
        fork_revision = $forkRevision
        backend_dirty = $false
        fork_dirty = $false
        client_ref = $clientRef
        client_sha256 = $clientHash
        fork_sha256 = (Get-FileHash -LiteralPath (Join-Path $package 'BBLauncher-AP.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        apworld_sha256 = (Get-FileHash -LiteralPath (Join-Path $package 'worlds/bloodborne.apworld') -Algorithm SHA256).Hash.ToLowerInvariant()
        release_version = 'v0.1.0-signing-canary.1'
        version = @{ product_version = '0.1.0-signing-canary.1'; file_version = '0.1.0.1' }
        includes_apworld = $true
        tools = @()
        files = $records
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $package 'candidate-manifest.json')
    $manifestBefore = (Get-FileHash -LiteralPath (Join-Path $package 'candidate-manifest.json') -Algorithm SHA256).Hash
    $unsignedRefused = $false
    try {
        & (Join-Path $repo 'packaging/finalize_fork_release.ps1') `
            -PackageRoot $package -ArchivePath $archive -ExpectedSignerSubject 'CN=Fixture Signer'
    } catch {
        $unsignedRefused = $_.Exception.Message -like '*Authenticode verification failed*'
    }
    if (-not $unsignedRefused -or (Test-Path -LiteralPath $archive) -or
        (Get-FileHash -LiteralPath (Join-Path $package 'candidate-manifest.json') -Algorithm SHA256).Hash -ne $manifestBefore) {
        throw 'Unsigned release was not refused without modifying outputs.'
    }

    # Simulate signing changing executable bytes.  The mock is intentionally
    # scoped to this process; production always calls the real Windows API.
    foreach ($relative in $catalog) {
        [IO.File]::AppendAllText((Join-Path $package $relative), ':signed')
    }
    function Get-AuthenticodeSignature {
        param([string]$LiteralPath)
        [pscustomobject]@{
            Status = 'Valid'
            SignerCertificate = [pscustomobject]@{ Subject = 'CN=Fixture Signer' }
            TimeStamperCertificate = [pscustomobject]@{ Subject = 'CN=Fixture Timestamp' }
        }
    }
    function Get-Item {
        param([string]$LiteralPath)
        if ($LiteralPath -like '*bb-ap-backend.exe') {
            return [pscustomobject]@{
                VersionInfo = [pscustomobject]@{
                    ProductVersion = '0.1.0-signing-canary.1'
                    FileVersion = '0.1.0.1'
                }
            }
        }
        Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath
    }
    & (Join-Path $repo 'packaging/finalize_fork_release.ps1') `
        -PackageRoot $package -ArchivePath $archive -ExpectedSignerSubject 'CN=Fixture Signer'
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw 'Finalizer did not create archive.' }
    $final = Get-Content -LiteralPath (Join-Path $package 'candidate-manifest.json') -Raw | ConvertFrom-Json
    if ($final.format -ne 'bb-ap-fork-release-v1' -or @($final.signatures).Count -ne 10) {
        throw 'Final manifest lacks release format or signature catalog.'
    }
    $newClientHash = (Get-FileHash -LiteralPath $client -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($final.client_sha256 -ne $newClientHash -or $final.client_sha256 -eq $clientHash) {
        throw 'Signed client hash was not refreshed.'
    }
    foreach ($relative in $catalog) {
        $record = @($final.files | Where-Object path -eq $relative)
        $digest = (Get-FileHash -LiteralPath (Join-Path $package $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($record.Count -ne 1 -or $record[0].sha256 -ne $digest) {
            throw "Signed file hash was not refreshed: $relative"
        }
    }
    Write-Host 'Finalizer mocked-signature hash refresh passed.'
} finally {
    $verified = [IO.Path]::GetFullPath($testRoot)
    $prefix = $build.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not ($verified + [IO.Path]::DirectorySeparatorChar).StartsWith($prefix,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe test cleanup path: $verified"
    }
    if (Test-Path -LiteralPath $verified) { Remove-Item -LiteralPath $verified -Recurse -Force }
}
