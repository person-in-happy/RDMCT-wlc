$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'campaign.py'
$working = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$existing = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*$entry*" })
if ($existing.Count -eq 0) {
    Start-Process -FilePath 'G:/conda/python.exe' -ArgumentList @('-u','-B','-X','utf8',('"' + $entry + '"')) -WorkingDirectory $working -WindowStyle Normal
} else {
    Write-Host ("Residence campaign is running in the foreground console PID " + $existing[0].ProcessId)
}
