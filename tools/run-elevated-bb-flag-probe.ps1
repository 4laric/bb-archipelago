$ErrorActionPreference = "Continue"
$executable = "C:\Users\alari\from-software-archipelago-clients\target\debug\bb-flag-probe.exe"
$shadLog = "C:\Users\alari\AppData\Roaming\shadPS4\log\shad_log.txt"
$result = "C:\Users\alari\bb-archipelago\work\rust-live-event-flag-result.txt"
$diagnostic = "C:\Users\alari\bb-archipelago\work\rust-live-event-flag-diagnostic.txt"

& $executable $shadLog 52410800 $result 2>&1 | Out-File -LiteralPath $diagnostic -Encoding utf8
"exit_code=$LASTEXITCODE" | Add-Content -LiteralPath $diagnostic
exit $LASTEXITCODE
