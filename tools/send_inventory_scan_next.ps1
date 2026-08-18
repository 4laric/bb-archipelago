param(
    [Parameter(Mandatory = $true)]
    [int]$Value,
    [string]$CommandPath = 'C:\Users\alari\bb-archipelago\work\inventory-scan-command.txt',
    [string]$StatePath = 'C:\Users\alari\bb-archipelago\work\inventory-scan-state.txt'
)

$initialWrite = if (Test-Path -LiteralPath $StatePath) { (Get-Item -LiteralPath $StatePath).LastWriteTimeUtc } else { [datetime]::MinValue }
Set-Content -LiteralPath $CommandPath -Value "NEXT $Value" -NoNewline
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 100
    if (Test-Path -LiteralPath $StatePath) {
        $item = Get-Item -LiteralPath $StatePath
        if ($item.LastWriteTimeUtc -gt $initialWrite) {
            $state = Get-Content -LiteralPath $StatePath
            if ($state -match '^status=next_ready$' -or $state -match '^status=setup_error$' -or $state -match '^status=command_rejected$') {
                $state
                exit 0
            }
        }
    }
}
throw 'Timed out waiting for inventory scan.'
