param([string] $SweepName='near_global')
Set-Location D:/git/git/RDMCT-A3C
$env:PYTHONUTF8="1"
& G:/conda/python.exe -u JMS-version/experiments/square_reverse16_20261125/micro.py $SweepName 2>&1 | Tee-Object -FilePath "JMS-version/results/square_reverse16_20261125/micro_$SweepName.log"
