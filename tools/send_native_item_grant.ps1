param(
    [Parameter(Mandatory=$true)][string]$RawId,
    [Parameter(Mandatory=$true)][string]$NormalizedId,
    [Parameter(Mandatory=$true)][ValidateRange(1,99)][int]$Quantity,
    [ValidatePattern('^(AUTO|[0-9]+)$')][string]$Expected='AUTO',
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Tag,
    [ValidateSet('AUTO','MANUAL')][string]$Trigger='AUTO'
)
$build='bb-0.1.0-r3'
$protocol='BBGRANT1'
$harness='bb-native-grant-v3'
$work='C:\Users\alari\bb-archipelago\work'
$command=Join-Path $work 'native-grant-command.txt'
$state=Join-Path $work 'native-grant-state.txt'
if(Test-Path -LiteralPath $command){throw 'A native grant command is already pending.'}
$current=@{}
if(Test-Path -LiteralPath $state){
    Get-Content -LiteralPath $state | ForEach-Object {
        $pair=$_ -split '=',2
        if($pair.Count -eq 2){$current[$pair[0]]=$pair[1]}
    }
}
if($current.build -ne $build -or $current.protocol -ne $protocol -or $current.harness -ne $harness){
    throw "Grant bridge mismatch: expected $build / $protocol / $harness"
}
$line="$protocol GRANT $RawId $NormalizedId $Quantity $Expected $Tag $Trigger"
$stream=[IO.File]::Open($command,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try {
    $bytes=[Text.Encoding]::ASCII.GetBytes($line)
    $stream.Write($bytes,0,$bytes.Length)
    $stream.Flush($true)
} finally {
    $stream.Dispose()
}
$terminal=@('completed','recovered_complete','failed','command_rejected','quantity_mismatch','setup_error','write_error')
$deadline=(Get-Date).AddSeconds(30)
while((Get-Date)-lt $deadline){
    Start-Sleep -Milliseconds 250
    if(Test-Path -LiteralPath $state){
        $current=@{}
        Get-Content -LiteralPath $state | ForEach-Object {
            $pair=$_ -split '=',2
            if($pair.Count -eq 2){$current[$pair[0]]=$pair[1]}
        }
        if($current.tag -eq $Tag -and $terminal -contains $current.status){
            Get-Content -LiteralPath $state
            if($current.status -in @('completed','recovered_complete')){exit 0}
            throw "Grant failed: $($current.status): $($current.detail)"
        }
    }
}
throw 'Timed out waiting for the native grant harness; command retained for diagnosis.'
