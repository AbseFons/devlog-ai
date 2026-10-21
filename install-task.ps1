param(
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$At = '20:00'
)
$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $base 'scheduled_runner.pyw'
foreach ($name in @('scheduled_runner.pyw','devlog.py','gaming_safe.py')) {
    if (-not (Test-Path (Join-Path $base $name))) {
        throw "Falta $name en $base. Copia primero los archivos del parche v1.6."
    }
}
# Determinar la ruta real de la misma instalación que invocas con `python`.
$resolved = & python -c 'import sys; print(sys.executable)' 2>&1
if ($LASTEXITCODE -ne 0 -or -not $resolved) {
    throw 'No se pudo encontrar Python con el comando python. Verifica tu instalación.'
}
$pythonExe = ([string]($resolved | Select-Object -Last 1)).Trim()
$pythonw = Join-Path (Split-Path -Parent $pythonExe) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "No se encontró pythonw.exe al lado de $pythonExe. Instala Python para Windows con pythonw.exe."
}

# NO ejecutar cmd.exe: pythonw no abre consola; los logs quedan en logs/devlog.log.
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}"' -f $runner) -WorkingDirectory $base
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 10)
# Gaming Safe observa el teclado/ratón de la sesión; requiere sesión interactiva.
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'DevLog AI' -Description 'DevLog AI v1.6: Gaming Safe e invisible (Pythonw); logs a archivo.' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Tarea actualizada: DevLog AI a las $At, sin ventanas CMD."
Write-Host "Ejecutable: $pythonw"
Write-Host "Lanzador:  $runner"
Write-Host 'Funciona al estar iniciada tu sesión de Windows, con Ollama y Git disponibles.'
Write-Host "Registro: $(Join-Path $base 'logs\devlog.log')"
Write-Host 'Autoprueba (sin Qwen): ejecuta el pythonw.exe mostrado con scheduled_runner.pyw --self-test.'
