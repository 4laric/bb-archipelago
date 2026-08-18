param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('READ', 'WRITE')]
    [string]$Command,

    [Parameter(Mandatory = $true)]
    [string]$Item,

    [int]$Expected,
    [int]$Replacement
)

$commandPath = 'C:\Users\alari\bb-archipelago\work\inventory-harness-command.txt'
$statePath = 'C:\Users\alari\bb-archipelago\work\inventory-harness-state.txt'

if ($Command -eq 'WRITE') {
    if ($Replacement -lt 1 -or $Replacement -gt 99) { throw 'Replacement must be between 1 and 99.' }
    $line = "WRITE $Item $Expected $Replacement"
}
else {
    $line = "READ $Item"
}

$previous = if (Test-Path -LiteralPath $statePath) { (Get-Item -LiteralPath $statePath).LastWriteTimeUtc } else { [datetime]::MinValue }
Set-Content -LiteralPath $commandPath -Value $line -NoNewline
$deadline = (Get-Date).AddSeconds(5)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 100
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Item -LiteralPath $statePath
        if ($state.LastWriteTimeUtc -gt $previous) {
            Get-Content -LiteralPath $statePath
            exit 0
        }
    }
}
throw 'Timed out waiting for the CE inventory harness.'
