param(
    [Parameter(Mandatory = $true)]
    [string]$Before,

    [Parameter(Mandatory = $true)]
    [string]$After,

    [string]$ControlBefore,
    [string]$ControlAfter,
    [string]$CsvPath
)

$beforeBytes = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Before))
$afterBytes = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $After))
if ($beforeBytes.Length -ne $afterBytes.Length) {
    throw "Snapshot lengths differ: $($beforeBytes.Length) and $($afterBytes.Length) bytes."
}

$useControl = -not [string]::IsNullOrWhiteSpace($ControlBefore) -or
    -not [string]::IsNullOrWhiteSpace($ControlAfter)
if ($useControl) {
    if ([string]::IsNullOrWhiteSpace($ControlBefore) -or
        [string]::IsNullOrWhiteSpace($ControlAfter)) {
        throw 'Supply both ControlBefore and ControlAfter, or neither.'
    }
    $controlBeforeBytes = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ControlBefore))
    $controlAfterBytes = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ControlAfter))
    if ($controlBeforeBytes.Length -ne $beforeBytes.Length -or
        $controlAfterBytes.Length -ne $beforeBytes.Length) {
        throw 'All four snapshots must have identical lengths.'
    }
}

$rows = [Collections.Generic.List[object]]::new()
for ($offset = 0; $offset -lt $beforeBytes.Length; $offset++) {
    $old = $beforeBytes[$offset]
    $new = $afterBytes[$offset]
    if ($old -eq $new) { continue }

    if ($useControl -and $controlBeforeBytes[$offset] -ne $controlAfterBytes[$offset]) {
        continue
    }

    $xor = $old -bxor $new
    for ($bit = 0; $bit -lt 8; $bit++) {
        $mask = 1 -shl $bit
        if (($xor -band $mask) -eq 0) { continue }
        $oldBit = if (($old -band $mask) -ne 0) { 1 } else { 0 }
        $newBit = if (($new -band $mask) -ne 0) { 1 } else { 0 }
        $rows.Add([PSCustomObject]@{
            Offset = "0x$($offset.ToString('X8'))"
            ByteOffset = $offset
            Bit = $bit
            BeforeByte = "0x$($old.ToString('X2'))"
            AfterByte = "0x$($new.ToString('X2'))"
            Transition = "$oldBit->$newBit"
            ControlStable = $useControl
        })
    }
}

if (-not [string]::IsNullOrWhiteSpace($CsvPath)) {
    $parent = Split-Path -Parent $CsvPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
    $rows | Export-Csv -LiteralPath $CsvPath -NoTypeInformation
}

Write-Host ("Snapshot bytes: {0}; candidate changed bytes: {1}; candidate changed bits: {2}; control filter: {3}" -f
    $beforeBytes.Length,
    @($rows | Select-Object -ExpandProperty ByteOffset -Unique).Count,
    $rows.Count,
    $useControl)
$rows
