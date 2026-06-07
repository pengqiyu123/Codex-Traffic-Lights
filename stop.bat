@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "$targets = Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -like '*codex_traffic_lights*' }; if (-not $targets) { Write-Host 'No Codex Traffic Lights process found.'; exit 0 }; foreach ($target in $targets) { if (Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue) { Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('Killed PID ' + $target.ProcessId) } }"
echo Done.
