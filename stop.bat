@echo off
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq pythonw.exe" /fo list ^| findstr "PID"') do (
    wmic process where "ProcessId=%%a" get CommandLine 2>nul | findstr "codex_traffic_lights" >nul && (
        taskkill /pid %%a /f >nul 2>&1
        echo Killed PID %%a
    )
)
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr "PID"') do (
    wmic process where "ProcessId=%%a" get CommandLine 2>nul | findstr "codex_traffic_lights" >nul && (
        taskkill /pid %%a /f >nul 2>&1
        echo Killed PID %%a
    )
)
echo Done.
