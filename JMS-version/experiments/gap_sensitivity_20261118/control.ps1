param(
    [ValidateSet('Plan','Prepare','Diagnose','Run','Resume','Status','Report')][string]$Action='Plan',
    [double[]]$Gaps=@(0.01,0.05,0.10),
    [double[]]$Budgets=@(300),
    [ValidateSet('All','Gap','Budget')][string]$Family='All',
    [ValidateRange(1,2)][int]$MaxWorkers=2,
    [switch]$RetryFailed,
    [string[]]$Cells,
    [string]$Suite='D:\git\git\RDMCT-A3C\JMS-version\results\gap_sensitivity_20261118_r2',
    [string]$Reference='D:\git\git\RDMCT-A3C\JMS-version\results\gap_two_stage_20261117_g05_r1',
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
if (($PSBoundParameters.ContainsKey('Gaps') -or $PSBoundParameters.ContainsKey('Budgets')) -and $Action -notin @('Plan','Prepare','Diagnose')) {
    throw 'Gaps/Budgets are frozen at Prepare. Use a fresh Suite for a different design.'
}
if (($RetryFailed -or $Cells -or $PSBoundParameters.ContainsKey('MaxWorkers')) -and $Action -notin @('Run','Resume')) {
    throw 'MaxWorkers/RetryFailed/Cells apply only to Run/Resume.'
}
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$sensRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$sensEntry=Join-Path $PSScriptRoot 'sensitivity.py'
$sensCulture=[System.Globalization.CultureInfo]::InvariantCulture
Push-Location -LiteralPath $sensRoot
try {
    if ($Action -notin @('Run','Resume')) {
        $sensArgs=@('-X','utf8','-u',$sensEntry,$Action.ToLower(),'--suite',$Suite,'--reference',$Reference)
        if ($Action -in @('Plan','Prepare','Diagnose')) {
            $sensArgs+='--gaps'; $sensArgs+=@($Gaps | ForEach-Object { $_.ToString('G17',$sensCulture) })
            $sensArgs+='--budgets'; $sensArgs+=@($Budgets | ForEach-Object { $_.ToString('G17',$sensCulture) })
        }
        & $Python @sensArgs
        if ($LASTEXITCODE -ne 0) { throw "Sensitivity $Action failed: $LASTEXITCODE" }
    }
    else {
        # Hold a suite-wide OS lock across sequential arms, avoiding duplicate
        # controllers and their external-experiment mutual waiting.
        $sensLockPath=Join-Path $Suite 'foreground.runner.lock'
        $sensHandle=[System.IO.File]::Open($sensLockPath,[System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
        try {
            $sensJson=& $Python -X utf8 $sensEntry members --suite $Suite --family ($Family.ToLower())
            if ($LASTEXITCODE -ne 0) { throw 'Cannot verify frozen suite members.' }
            $sensDecoded=ConvertFrom-Json -InputObject ($sensJson -join "`n")
            $sensMembers=@($sensDecoded | Where-Object { $null -ne $_ })
            if ($sensMembers.Count -eq 0) { Write-Host ('No new variants in family ' + $Family + '; reporting only.') }
            $sensFailures=@()
            foreach ($sensMember in $sensMembers) {
                Write-Host ("VARIANT {0}: gap={1:P1}, budget={2}s, workers<={3}" -f $sensMember.id,$sensMember.gap,$sensMember.budget,$MaxWorkers)
                $sensRunArgs=@('-X','utf8','-u',$sensMember.engine,'resume','--campaign',$sensMember.campaign,'--max-workers',$MaxWorkers.ToString())
                if ($RetryFailed) { $sensRunArgs+='--retry-failed' }
                if ($Cells) { $sensRunArgs+='--cells'; $sensRunArgs+=$Cells }
                & $Python @sensRunArgs
                $sensExit=$LASTEXITCODE
                if ($sensExit -eq 1) {
                    $sensFailures+=$sensMember.id
                    Write-Warning ('Failed/incomplete cells retained for ' + $sensMember.id)
                }
                elseif ($sensExit -ne 0) { throw "Interrupted/abnormal controller exit: $sensExit" }
            }
            & $Python -X utf8 $sensEntry report --suite $Suite
            if ($LASTEXITCODE -ne 0) { throw 'Sensitivity report failed.' }
            if ($sensFailures.Count -gt 0) { throw ('Inspect failed variants, then Resume -RetryFailed: ' + ($sensFailures -join ', ')) }
        }
        finally { $sensHandle.Dispose() }
    }
}
finally { Pop-Location }
