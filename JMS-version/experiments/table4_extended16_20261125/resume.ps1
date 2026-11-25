param([string]$Python = 'G:/conda/python.exe')
$ErrorActionPreference = 'Stop'
$code = $PSScriptRoot
$jms = Split-Path -Parent (Split-Path -Parent $code)
$dest = Join-Path $jms 'results/table4_extended16_20261125'
$watch = [Diagnostics.Stopwatch]::StartNew()
$work = @()
foreach ($h in @(3,10)) {
    foreach ($pair in @(@('blocks','free/result.json'),@('pack','pack/result.json'),@('retime','retime/result.json'),@('compare','s3/AB.json'))) {
        $work += [pscustomobject]@{ H=$h; Script=$pair[0]; End=(Join-Path $dest "H$h/$($pair[1])") }
    }
}
$statusPath = Join-Path $dest 'resume_progress.json'
function Report([int]$done,[string]$current) {
    $elapsed = [Math]::Round($watch.Elapsed.TotalSeconds,1)
    $eta = 0
    foreach ($w in $work) {
        if (!(Test-Path -LiteralPath $w.End)) {
            $eta += $(if($w.Script -eq 'compare') {90} elseif($w.Script -eq 'pack'){20} else{30})
        }
    }
    $status = [ordered]@{completed=$done; expected=$work.Count; failed=0; active=$current; elapsed_s=$elapsed; remaining_estimate_s=$eta; estimated_total_s=($elapsed+$eta); basis='Per-case serial replay of historical 16-wafer phases. External running workers are adopted.'}
    $tmp = "$statusPath.tmp"
    $status | ConvertTo-Json | Set-Content -LiteralPath $tmp -Encoding utf8
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
    Write-Host "$current | $done/$($work.Count) completed, 0 failed; elapsed $elapsed s, total ~$($elapsed+$eta) s, remaining ~$eta s"
}
$done = 0
foreach ($w in $work) {
    if (!(Test-Path -LiteralPath $w.End)) {
        $scriptPath=Join-Path $code "$($w.Script).py"
        $active=Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { $_.CommandLine -like '*table4_extended16_20261125*' -and $_.CommandLine -like "*$($w.Script).py* $($w.H)" } | Select-Object -First 1
        if ($active) {
            $pidNumber=$active.ProcessId
            while (Get-Process -Id $pidNumber -ErrorAction SilentlyContinue) {
                Report $done "H=$($w.H) $($w.Script) (adopted)"
                Start-Sleep -Seconds 4
            }
        }
        if (!(Test-Path -LiteralPath $w.End)) {
            Report $done "H=$($w.H) $($w.Script)"
            & $Python -B -u -X utf8 $scriptPath $w.H
            if ($LASTEXITCODE) {throw "H=$($w.H) $($w.Script) failed ($LASTEXITCODE)"}
        }
    }
    $done++
    Report $done "H=$($w.H) $($w.Script)"
}
& $Python -B -u -X utf8 (Join-Path $code 'publish.py')
if ($LASTEXITCODE) {throw "The independent Table 4 publication audit failed ($LASTEXITCODE)"}
