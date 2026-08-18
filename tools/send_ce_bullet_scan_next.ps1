param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(0, 99)]
    [int]$Count
)

$work = Join-Path $PSScriptRoot '..\work'
$command = Join-Path $work 'bullet-scan-command.txt'
$state = Join-Path $work 'bullet-scan-state.txt'

Set-Content -LiteralPath $command -Value "NEXT $Count" -Encoding ascii

$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 250
    if (Test-Path -LiteralPath $state) {
        $text = Get-Content -LiteralPath $state -Raw
        if ($text -match 'status=(next_ready|setup_error|command_rejected)') {
            $text
            exit $(if ($Matches[1] -eq 'next_ready') { 0 } else { 1 })
        }
    }
} while ((Get-Date) -lt $deadline)

Write-Error 'Timed out waiting for Cheat Engine.'
