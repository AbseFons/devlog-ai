param(
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$At = '20:00'
)
$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $base 'run-daily.cmd'
if (-not (Test-Path $runner)) { throw "No se encontró $runner" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'No se encontró Python. Instala Python 3.10+ y agrégalo al PATH.'
}
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$runner`"" -WorkingDirectory $base
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName 'DevLog AI' -Description 'Genera una microlección con Qwen local y la guarda en GitHub' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Tarea instalada: DevLog AI, cada día a las $At."
Write-Host 'La PC y Ollama deben estar disponibles; las entradas pendientes se intentarán recuperar en una próxima ejecución.'
Write-Host "Revisa el registro en $base\logs\devlog.log"
