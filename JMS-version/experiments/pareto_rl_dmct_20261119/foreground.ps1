param([Parameter(Mandatory)][string]$Campaign,[int]$Workers=5)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$Host.UI.RawUI.WindowTitle = "晶圆双目标调度 | $Campaign"
$campaignRoot = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot 'runs') $Campaign)).Path
$experimentPython = 'G:\conda\envs\a3cenv\python.exe'
Start-Transcript -Path (Join-Path $campaignRoot ("foreground_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss')))
try {
    & $experimentPython -B -X utf8 -u (Join-Path $PSScriptRoot 'campaign.py') run $campaignRoot --workers $Workers
    $resultCode = $LASTEXITCODE
} finally {
    Stop-Transcript
}
exit $resultCode
