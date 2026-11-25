$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'alternatives.py'
$existing = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*$entry*" })
if ($existing.Count -eq 0) {
    Start-Process -FilePath 'G:/conda/python.exe' -ArgumentList @('-B','-u','-X','utf8',('"' + $entry + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Normal
}
