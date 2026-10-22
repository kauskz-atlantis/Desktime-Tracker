$pidFile = "C:\ProgramData\ATLDeskManagement\watchdog.pid"
if (Test-Path $pidFile) {
    $wdPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($wdPid) {
        proc = Get-Process -Id $wdPid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "powershell") {
            Stop-Process -Id $wdPid -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}