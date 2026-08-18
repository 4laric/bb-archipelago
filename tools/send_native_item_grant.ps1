param(
    [Parameter(Mandatory=$true)][string]$RawId,
    [Parameter(Mandatory=$true)][string]$NormalizedId,
    [Parameter(Mandatory=$true)][ValidateRange(1,99)][int]$Quantity,
    [Parameter(Mandatory=$true)][ValidateRange(0,9999)][int]$Expected,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Tag
)
$work='C:\Users\alari\bb-archipelago\work'
$command=Join-Path $work 'native-grant-command.txt'
$state=Join-Path $work 'native-grant-state.txt'
if(Test-Path -LiteralPath $command){throw 'A native grant command is already pending.'}
$before=if(Test-Path -LiteralPath $state){(Get-Item -LiteralPath $state).LastWriteTimeUtc}else{[datetime]::MinValue}
Set-Content -LiteralPath $command -Value "GRANT $RawId $NormalizedId $Quantity $Expected $Tag" -NoNewline
$deadline=(Get-Date).AddSeconds(5)
while((Get-Date)-lt $deadline){
    Start-Sleep -Milliseconds 100
    if(Test-Path -LiteralPath $state){
        $item=Get-Item -LiteralPath $state
        if($item.LastWriteTimeUtc -gt $before){Get-Content -LiteralPath $state; exit 0}
    }
}
throw 'Timed out waiting for the native grant harness.'
