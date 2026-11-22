$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "JMS 16-wafer gap ablations - shared inputs"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Set-Location -LiteralPath $repo
$inputBuilder = Join-Path $PSScriptRoot "inputs.py"
$dest = Join-Path $repo "JMS-version/results/mixed_gap_ablation_20261122/inputs"
$finished = 0
$failed = 0
$started = Get-Date
foreach ($case in "H6","S1","S2","S3") {
    foreach ($seed in 1,2,3) {
        $folder = Join-Path $dest "$case/s$seed"
        New-Item $folder -ItemType Directory -Force | Out-Null
        Write-Host "Preparing $case solver seed $seed"
        $log = Join-Path $folder ("prep-" + (Get-Date -Format "yyyyMMdd-HHmmssfff") + ".log")
        $task = Start-Process -FilePath "G:\conda\envs\a3cenv\python.exe" -ArgumentList @("-B","-X","utf8","-u",$inputBuilder,$case,$seed) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $log -RedirectStandardError "$log.err"
        if ($task.ExitCode -ne 0) { $failed++; Get-Content -LiteralPath "$log.err" -Tail 8 }
        $finished++
        $eta = [Math]::Round(((Get-Date)-$started).TotalSeconds * (12-$finished)/$finished)
        Write-Host "$finished/12 finished | $failed failed | ETA $eta seconds"
    }
}
exit [int]($failed -ne 0)
