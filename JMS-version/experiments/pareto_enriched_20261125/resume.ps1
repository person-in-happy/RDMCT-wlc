param([string]$Python="G:/conda/python.exe")
$ErrorActionPreference="Stop"
$out=Join-Path $PSScriptRoot "../../results/pareto_enriched_20261125"
$statusPath=Join-Path $out "resume_progress.json"
$stages=@(
  @("native_caps.py","all",238), @("neighbor.py","all","--seconds","12",200),
  @("reroute.py",10), @("lift.py",20), @("extend.py",22), @("lift.py",20),
  @("follow.py",145), @("templates.py",47), @("lift.py",20),
  @("epsilon.py",285), @("lowarc.py",135), @("mixed_packing.py",82),
  @("screen_arcs.py",25), @("screen_arcs.py","cross873",74), @("screen_arcs.py","cross875",70),
  @("lift.py",20), @("collect.py",4), @("arc_certificate.py",22), @("collect.py",4)
)
$timer=[Diagnostics.Stopwatch]::StartNew()
function Show-Phase($index,$failed) {
    $remaining=0
    for($j=$index;$j -lt $stages.Count;$j++) { $remaining += [double]$stages[$j][-1] }
    $phase=if ($index -lt $stages.Count) { $stages[$index][0] } else { "complete" }
    $s=[ordered]@{stage=$phase;completed=$index;total=$stages.Count;failed=$failed;elapsed=$timer.Elapsed.TotalSeconds;
      estimated_total=$timer.Elapsed.TotalSeconds+$remaining;estimated_remaining=$remaining;
      basis="Historical fresh serial stage estimate. Cached stages are validated and skipped. Each active solver prints its measured ETA."}
    $tmp="$statusPath.$PID.tmp"
    [IO.File]::WriteAllText($tmp,($s|ConvertTo-Json))
    Move-Item -LiteralPath $tmp -Destination $statusPath -Force
    Write-Host ($s|ConvertTo-Json -Compress)
}
for($i=0;$i -lt $stages.Length;$i++) {
    Show-Phase $i 0
    $row=$stages[$i]
    $source=Join-Path $PSScriptRoot $row[0]
    $extra=@()
    if($row.Count -gt 2) { $extra=@($row[1..($row.Count-2)]) }
    & $Python -B -u -X utf8 $source @extra
    if ($LASTEXITCODE -ne 0) { Show-Phase $i 1; throw "Stage $i failed at $source" }
}
Show-Phase $stages.Length 0
