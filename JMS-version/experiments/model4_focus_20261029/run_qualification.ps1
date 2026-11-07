param([switch]$PlanOnly)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location -LiteralPath $repoPath
$pythonPath = 'G:\conda\envs\a3cenv\python.exe'
$backendPath = Join-Path $repoPath 'JMS-version/model4_pjob_20261027'
$cases = @('qualification_n8_mixed_single','qualification_n8_mixed_dual')
$cells = foreach ($case in $cases) { foreach ($seed in 1,2,3) { [pscustomobject]@{case=$case;seed=$seed} } }
foreach ($case in $cases) {
    & $pythonPath -X utf8 -c 'import sys,json;sys.path.insert(0,sys.argv[1]);from model import Config;from pjobs import groups_from_config;c=Config(**json.load(open(sys.argv[2],encoding=''utf-8'')));assert len(c.pjobs)==6;assert sum(g.count for g in groups_from_config(c))==8' $backendPath (Join-Path $PSScriptRoot "$case.json")
    if ($LASTEXITCODE -ne 0) { throw "Invalid input: $case" }
}
if ($PlanOnly) { $cells | Format-Table; Write-Host '6 runs; 270+30 s, SPBS 20 s, SCIP 6000 MiB, RSS guard 7000 MiB, wall guard 1800 s; 1 CPU worker.'; return }
& $pythonPath -X utf8 -c 'import sys;sys.path.insert(0,sys.argv[1]);from evidence_supplement import no_other_queue;no_other_queue()' $backendPath
if ($LASTEXITCODE -ne 0) { throw 'Another campaign is active. Run this supplement after it finishes.' }
$batchPath = Join-Path $repoPath ('JMS-version/results/model4_paper_qualification_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $batchPath -ErrorAction Stop | Out-Null
$configPath = Join-Path $batchPath 'configs'
New-Item -ItemType Directory -Path $configPath | Out-Null
foreach ($case in $cases) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot "$case.json") -Destination $configPath }
Copy-Item -LiteralPath $PSCommandPath -Destination $batchPath
$inventory = (& $pythonPath -X utf8 -c 'import sys,json;sys.path.insert(0,sys.argv[1]);from run_experiments import assets;print(json.dumps(assets()))' $backendPath) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not freeze runtime assets.' }
foreach ($asset in $inventory.PSObject.Properties) {
    $snapshot = Join-Path (Join-Path $batchPath 'frozen_code') $asset.Name
    New-Item -ItemType Directory -Path (Split-Path $snapshot -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoPath $asset.Name) -Destination $snapshot
}
$inventory | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $batchPath 'assets.json') -Encoding UTF8
@{expected=6;cells=$cells;threads=1;jobs=1;memory_mb=6000;rss_guard_mb=7000;wall_guard_s=1800;
  primary_s=270;refinement_s=30;spbs_s=20;scope='Qualification and decoding validation; not an algorithm speed comparison'} |
  ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $batchPath 'protocol.json') -Encoding UTF8
$startedAt=Get-Date; $completedCount=0; $failedCount=0; $records=@()
foreach ($cell in $cells) {
    $cellName="$($cell.case)__s$($cell.seed)"
    $runPath=Join-Path $batchPath $cellName
    $arguments=@('-X','utf8','-u',(Join-Path $backendPath 'run_experiments.py'),'solve',
        '--config',(Join-Path $configPath "$($cell.case).json"),'--output',$runPath,
        '--seed',"$($cell.seed)",'--method','scip','--time-limit','270','--stage2-limit','30',
        '--initialization','spbs','--initialization-budget','20','--memory-mb','6000')
    $quotedArguments=($arguments | ForEach-Object { '"'+$_+'"' }) -join ' '
    $process=Start-Process -FilePath $pythonPath -ArgumentList $quotedArguments -NoNewWindow -PassThru -WorkingDirectory $repoPath -RedirectStandardOutput (Join-Path $batchPath "$cellName.stdout.log") -RedirectStandardError (Join-Path $batchPath "$cellName.stderr.log")
    $cellStarted=Get-Date; $lastPrint=-15; $peak=0; $guard=$null
    try {
        while (-not $process.HasExited) {
            $process.Refresh(); $rss=$process.WorkingSet64/1MB; $peak=[Math]::Max($peak,$rss)
            $elapsed=((Get-Date)-$cellStarted).TotalSeconds
            if ($rss -gt 7000) { $guard='process_memory_guard' }
            if ($elapsed -gt 1800) { $guard='wall_guard' }
            if ($guard) { Stop-Process -Id $process.Id; break }
            if ($elapsed-$lastPrint -ge 15) {
                $done=$completedCount+$failedCount
                $average=if ($done) { ((Get-Date)-$startedAt).TotalSeconds/$done } else { 360 }
                $eta=[Math]::Round(($cells.Count-$done-1)*$average+[Math]::Max(0,$average-$elapsed))
                Write-Host "RUN $cellName | completed=$completedCount failed=$failedCount total=6 | elapsed=$([Math]::Round($elapsed))s RSS=$([Math]::Round($rss))MiB ETA~${eta}s"
                $lastPrint=$elapsed
            }
            Start-Sleep -Seconds 1
        }
        $process.WaitForExit(); $process.Refresh(); $exitCode=$process.ExitCode
    } catch {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id }
        throw
    }
    $resultPath=Join-Path $runPath 'result.json'
    $valid=$false
    if (($exitCode -eq 0) -and -not $guard -and (Test-Path -LiteralPath $resultPath)) {
        $result=Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $valid=$result.validation.valid -and $result.original_model_check
    }
    if ($valid) { $completedCount++ } else { $failedCount++ }
    $records+=@{cell=$cellName;exit_code=$exitCode;valid=$valid;guard=$guard;peak_sampled_rss_mib=$peak;wall_seconds=((Get-Date)-$cellStarted).TotalSeconds}
    @{completed=$completedCount;failed=$failedCount;expected=6;records=$records} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $batchPath 'progress.json') -Encoding UTF8
}
Write-Host "FINISHED completed=$completedCount failed=$failedCount total=6 | $batchPath"
if ($failedCount) { throw 'Some observations failed; inspect saved logs. Existing outputs are retained.' }
