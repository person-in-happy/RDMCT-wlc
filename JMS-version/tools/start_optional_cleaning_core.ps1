$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$entry = Join-Path $repoRoot 'JMS-version/joint_model/revalidate.py'
$campaignPath = Join-Path $repoRoot 'JMS-version/results/optional_cleaning_20261016_core'
$pythonPath = (Get-Command python -ErrorAction Stop).Source
$manifestPath = Join-Path $campaignPath 'campaign.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    & $pythonPath $entry prepare --suite core --output $campaignPath --time-limit 300 --seeds 1 2 3 --training-seed 1 --spbs-budget 20 --cut-profile standard --memory-mb 14000 --wall-limit 1800
    if ($LASTEXITCODE -ne 0) { throw 'Campaign preparation failed; nothing launched.' }
}
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.time_limit -ne 300 -or ($manifest.seeds -join ',') -ne '1,2,3' -or $manifest.cut_profile -ne 'standard') {
    throw 'Existing protocol differs from the authorized core budget; use a new campaign path.'
}
$running = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python' -and $_.CommandLine -like '*revalidate.py*' -and $_.CommandLine -like "*$campaignPath*"
}
if ($running) { $running | Select-Object ProcessId, CommandLine; return }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$stdout = Join-Path $campaignPath "supervisor_${stamp}.stdout.log"
$stderr = Join-Path $campaignPath "supervisor_${stamp}.stderr.log"
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-u', "`"$entry`"", 'run', '--campaign', "`"$campaignPath`"") -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
@{ pid=$process.Id; campaign=$campaignPath; stdout=$stdout; stderr=$stderr; launched_utc=[DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $campaignPath 'launch.json')
Start-Sleep -Seconds 3
if ($process.HasExited) { throw "Supervisor exited early. Inspect $stderr" }
Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $campaignPath 'launch.json')
