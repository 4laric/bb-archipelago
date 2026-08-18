param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('READ', 'WRITE', 'INVREAD', 'INVWRITE')]
    [string]$Command,

    [ValidateSet('F8', 'FC', '100', '104')]
    [string]$Offset,

    [string]$Item,

    [int]$Expected,
    [int]$Replacement,
    [string]$CommandPath = 'C:\Users\alari\bb-archipelago\work\ce-harness-command.txt',
    [string]$StatePath = 'C:\Users\alari\bb-archipelago\work\ce-harness-state.txt'
)

if ($Command -eq 'WRITE') {
    if (-not $Offset) { throw 'WRITE requires -Offset.' }
    if ($Replacement -lt 1 -or $Replacement -gt 10000) { throw 'Replacement must be between 1 and 10000.' }
    $line = "WRITE $Offset $Expected $Replacement"
}
elseif ($Command -eq 'INVREAD') {
    if (-not $Item) { throw 'INVREAD requires -Item (BULLET, VIAL, or numeric item ID).' }
    $line = "INVREAD $Item"
}
elseif ($Command -eq 'INVWRITE') {
    if (-not $Item) { throw 'INVWRITE requires -Item (BULLET, VIAL, or numeric item ID).' }
    if ($Replacement -lt 1 -or $Replacement -gt 99) { throw 'Inventory replacement must be between 1 and 99.' }
    $line = "INVWRITE $Item $Expected $Replacement"
}
else {
    $line = 'READ'
}

$initialWrite = if (Test-Path -LiteralPath $StatePath) { (Get-Item -LiteralPath $StatePath).LastWriteTimeUtc } else { [datetime]::MinValue }
Set-Content -LiteralPath $CommandPath -Value $line -NoNewline

$deadline = (Get-Date).AddSeconds(5)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 100
    if (Test-Path -LiteralPath $StatePath) {
        $item = Get-Item -LiteralPath $StatePath
        if ($item.LastWriteTimeUtc -gt $initialWrite) {
            Get-Content -LiteralPath $StatePath
            exit 0
        }
    }
}

throw 'Timed out waiting for the CE harness. Ensure the table script is running.'
