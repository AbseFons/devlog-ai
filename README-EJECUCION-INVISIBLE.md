# DevLog AI v1.6 — Gaming Safe + ejecución invisible

Esta actualización sustituye la tarea anterior que abría una ventana de CMD.
Ahora **Windows ejecuta directamente `pythonw.exe`**, sin consola; el lanzador
`scheduled_runner.pyw` escribe las salidas y errores de DevLog AI en
`logs/devlog.log`. También incorpora Gaming Safe v1.5.

## Instalar sobre tu proyecto existente (sin perder commits)

1. Comprueba que ningún `backfill`, `daily`, `catchup` ni `safe-run` siga en curso.
2. Descomprime **DevLog-AI-v1.6-PARCHE-Gaming-Safe-Invisible.zip**.
3. Copia los archivos a la raíz de `devlog-ai`, reemplazando los que ya existan.
   No borres `.git/`, `entries/`, `logs/` ni tu `gaming-safe.local.json`.
4. Desde PowerShell dentro del proyecto, verifica la instalación:

   ```powershell
   python devlog.py safe-status
   python -m unittest discover -s tests -v
   ```

5. Registra los cambios (opcional, para versionar tu herramienta):

   ```powershell
   git add devlog.py gaming_safe.py scheduled_runner.pyw install-task.ps1 run-daily.cmd .gitignore README-EJECUCION-INVISIBLE.md
   git commit -m "feat: Gaming Safe con ejecución invisible"
   git push origin main
   ```

6. **Reinstala** la tarea de Windows, que todavía usa CMD hasta que hagas este paso:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install-task.ps1 -At "20:00"
   ```

## Comprobar que la tarea está en modo invisible

```powershell
(Get-ScheduledTask -TaskName "DevLog AI").Actions | Format-List Execute,Arguments,WorkingDirectory
```

`Execute` debe terminar en `pythonw.exe`, y `Arguments` debe contener
`scheduled_runner.pyw`. **No debe aparecer `cmd.exe`**.

Para probar solo el lanzador, sin generar contenido ni esperar a las 20:00:

```powershell
$pythonw = (Get-ScheduledTask -TaskName "DevLog AI").Actions.Execute
& $pythonw .\scheduled_runner.pyw --self-test
Get-Content .\logs\devlog.log -Tail 12
```

Debe figurar `[TASK] Autoprueba correcta` y no se abrirá CMD.
La tarea real continúa lanzándose cada día a las 20:00:
espera PC sin uso y GPU libre, luego genera, publica y libera Qwen.

Revisar trabajo real:

```powershell
Get-ScheduledTaskInfo -TaskName "DevLog AI" | Format-List LastRunTime,NextRunTime,LastTaskResult
Get-Content .\logs\devlog.log -Tail 80
```

`[TASK] Inicio invisible` indica inicio; `[GENERANDO]` ejecución de Qwen;
`[FIN]` fin de DevLog; `[TASK] Fin · código de salida: 0` indica proceso
terminado correctamente. Un `0` **no garantiza** commits nuevos: puede no haber
entradas pendientes o haber vencido la ventana de Gaming Safe.

### Recuperar la ejecución interrumpida del 20/10/2026

Con la configuración nueva, la tarea intentará recuperarla dentro de los 7 días
siguientes. Para hacerlo manualmente (sin Gaming Safe) usa:

```powershell
python devlog.py catchup --days 7
```

**Limitaciones:** Debes mantener la sesión de Windows iniciada y la PC
encendida. El bloqueo de pantalla puede permitir ejecutar la tarea, pero
suspender/apagar el equipo la impide. El archivo de registro es local.
El lanzador invisible se ejecuta sin consola: ya no es necesario cerrar ni
minimizar CMD; usa `Stop-ScheduledTask -TaskName "DevLog AI"` si necesitas
cancelar una ejecución programada. El control Gaming Safe se aplica a las
ejecuciones programadas; `backfill` manual no queda protegido.

Recomendación: No programes `Backfill` retrospectivo con Gaming Safe; es un
trabajo histórico puntual y conviene mantenerlo controlado manualmente.
