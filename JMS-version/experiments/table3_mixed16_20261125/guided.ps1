$ErrorActionPreference='Stop'
$py='G:/conda/python.exe'
$src = Join-Path $PSScriptRoot 'guided.py'
$out = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'results/table3_mixed16_20261125/proposals'
$count = 0
foreach ($caseName in @('guided31','guided22','guidedinter')) {
    $folder=Join-Path $out $caseName
    if (Test-Path -LiteralPath (Join-Path $folder 'result.json')) { $count++; continue }
    $existing=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($src) -and $_.CommandLine.TrimEnd().EndsWith($caseName) })
    if ($existing.Count) { $worker=Get-Process -Id $existing[0].ProcessId }
    else { $worker=Start-Process -FilePath $py -ArgumentList @('-B','-u','-X','utf8',$src,$caseName) -PassThru -NoNewWindow }
    while (-not $worker.HasExited) {
        $checkpoint=Join-Path $folder 'checkpoint.json'
        $used=0
        if (Test-Path -LiteralPath $checkpoint) { $used=(Get-Content -LiteralPath $checkpoint -Raw | ConvertFrom-Json).elapsed }
        $left=[Math]::Max(0,240-$used)
        $batchLeft=$left+(2-$count)*240
        Write-Host "16 mixed guided native proposals: completed $count/3. $caseName stage elapsed $([int]$used)s, remaining $([int]$left)s; remaining search budget $([int]$batchLeft)s plus model construction."
        Start-Sleep -Seconds 6
        $worker.Refresh()
    }
    if (-not (Test-Path -LiteralPath (Join-Path $folder 'result.json'))) { throw "Check guided proposal $caseName" }
    $count++
}
