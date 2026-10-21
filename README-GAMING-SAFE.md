# DevLog AI v1.5 — Gaming Safe (Windows + RTX 5070 Ti)

**Actualización de la versión v1.4 que ya te funciona.** No se borra ni reescribe ninguna entrada ni commit. `daily`, `backfill`, `plan` y `catchup` siguen disponibles sin cambios en su sintaxis. El modo Gaming Safe se aplica a la **tarea programada** (`safe-run`); `backfill` manual sigue ejecutándose directamente, aunque estés jugando.

## Instalación en tu repositorio actual

1. **Termina cualquier `backfill` activo** antes de reemplazar archivos; nunca cambies `devlog.py` mientras se esté ejecutando.
2. Haz una copia de seguridad de tu `devlog.py` e `install-task.ps1`, o confía en Git para revertirlos.
3. Copia desde este paquete **`devlog.py`, `gaming_safe.py`, `run-daily.cmd`, `install-task.ps1` y `.gitignore`** a la raíz de tu repositorio. Copia también `gaming-safe.example.json` y este README si quieres conservar la documentación y el ejemplo de configuración. **No reemplaces `.git/`, `entries/` ni `logs/`.**
4. En PowerShell, dentro de la carpeta del proyecto:

```powershell
git status --short
python devlog.py safe-status
git add devlog.py gaming_safe.py run-daily.cmd install-task.ps1 .gitignore gaming-safe.example.json README-GAMING-SAFE.md
git commit -m "feat: Gaming Safe para Ollama y tareas programadas"
git push origin main
powershell -ExecutionPolicy Bypass -File .\install-task.ps1 -At "20:00"
```

`safe-status` **solo diagnostica**: no genera commits, no llama a Qwen y no modifica Git. Devuelve código 2 cuando pospone Qwen; esto es normal si tienes la PC activa. La tarea debe **reinstalarse**: la anterior tenía límite de ejecución de 4 horas y Gaming Safe puede esperar hasta 7 horas.

Para comprobar que existe:

```powershell
Get-ScheduledTask -TaskName "DevLog AI"
Get-ScheduledTaskInfo -TaskName "DevLog AI"
Get-Content .\logs\devlog.log -Tail 60
```

## Qué hace a las 20:00

- Arranca a las 20:00 por el Programador de tareas de Windows. Se ejecuta dentro de **tu sesión interactiva de Windows**: necesita poder observar el teclado y ratón del usuario.
- Comprueba: al menos **10 min sin entrada de teclado/ratón**, **GPU menor que 30%**, **al menos 9000 MiB de VRAM libres** y ausencia de procesos de videojuegos conocidos.
- Si todo está libre, vuelve a comprobarlo **120 s** después antes de activar Qwen. Si no, vuelve a comprobar **cada 15 minutos** durante un máximo de 7 horas (aproximadamente hasta las 03:00).
- Hace `catchup --days 7`, generando los commits diarios faltantes (1–10 según el plan del día) y enviando `git push origin main` al terminar.
- Antes de **cada entrada que falte**, vuelve a revisar actividad de usuario y procesos de juego. Si empiezas a jugar, **no interrumpe** una generación que ya esté en curso; **se detiene entre entradas**, publica el progreso y vuelve a esperar condiciones libres.
- Durante la inferencia **NO** usa el porcentaje GPU/VRAM para pausar: Qwen eleva ambos valores y produciría falsos positivos.
- Al terminar o pausar una generación iniciada por Gaming Safe, solicita a Ollama descargar Qwen con `keep_alive: 0`. No cierra Ollama ni finaliza procesos de juegos.
- Si no hay momento libre en la ventana de espera, **no genera ese día** y recupera las fechas pendientes en la siguiente ejecución, dentro de la ventana de 7 días.

### Configuración opcional

Los valores anteriores son conservadores y orientativos para una **RTX 5070 Ti de 16 GB**; **no garantizan cero caída de FPS**. Hay juegos que no aparecen en la lista de procesos y el muestreo no impide toda superposición entre dos llamadas.

Para configurar sin ensuciar Git:

```powershell
Copy-Item .\gaming-safe.example.json .\gaming-safe.local.json
notepad .\gaming-safe.local.json
```

`gaming-safe.local.json` está ignorado por Git. Ajusta, por ejemplo, `min_free_vram_mib` (9000 MiB por defecto), `idle_minutes` o agrega el **nombre del .exe** de tu juego a `games`. **La lista en el archivo local REEMPLAZA a la lista predeterminada**: incluye todos los juegos que quieres que bloquee. Una PC con otro modelo de GPU puede necesitar umbrales distintos. La omisión o fallo de `nvidia-smi`, `tasklist` o las APIs de Windows hará que el programa posponga Qwen en vez de ejecutarlo sin seguridad.

Puedes ejecutar una comprobación manual sin generar contenido:

```powershell
python devlog.py safe-status
```

Puedes iniciar manualmente el modo Gaming Safe y observarlo en primer plano (estará hasta 7 horas buscando una oportunidad libre):

```powershell
python devlog.py safe-run --days 7 --interval-minutes 15 --max-wait-minutes 420
```

Para una prueba única (no espera indefinidamente, pero espera 120 s si parece libre):

```powershell
python devlog.py safe-run --once --no-push
```

**Precaución:** `--no-push` evita publicar, pero **sí crea commits locales** si todas las condiciones se cumplen. Usa `safe-status` si solo quieres diagnosticar.

## Precisión y limitaciones

- Gaming Safe **no es un anticheat ni un detector completo de todos los juegos**. La utilización GPU no identifica qué proceso la consume; el modo de detección usa también actividad humana y una lista de procesos. Puedes añadir los ejecutables de tus juegos en `gaming-safe.local.json`.
- La lectura de `GetLastInputInfo` depende de la sesión de usuario; no configures la tarea como una cuenta del sistema. Con sesión bloqueada la tarea puede ejecutarse si Windows lo permite, pero Ollama y Git deben estar accesibles en esa misma cuenta.
- Si otro programa necesita el **mismo** modelo de Ollama mientras Gaming Safe está generando, la descarga final de Qwen puede afectar a ese otro programa. En ese caso configura `"unload_qwen_after_run": false`.
- GitHub solo mostrará commits publicados correctamente; los commits generados por IA no verifican trabajo humano y los retrospectivos siguen marcados como tales.
- `safe-status` se puede ejecutar desde un terminal activo y normalmente dirá **POSPONER**: esto es lo esperado por tu uso del teclado.

## Verificar versión y pruebas

```powershell
python -c "import gaming_safe; print('Gaming Safe disponible')"
python -m unittest discover -s tests -v
```
