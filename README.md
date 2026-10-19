# DevLog AI — diario técnico generado con Qwen local

Proyecto personal para crear **una microlección técnica nueva por día** con Ollama (`qwen3.5:9b`), validar su formato, guardarla en Markdown, crear un commit Git y opcionalmente enviarlo a GitHub. No genera commits vacíos ni ejecuta el código sugerido por la IA.

## Requisitos

1. Windows 10/11, Python 3.10 o posterior, Git y una cuenta de GitHub.
2. Ollama abierto localmente y modelo instalado: `ollama list` debe mostrar `qwen3.5:9b`. Si no aparece, ejecuta `ollama pull qwen3.5:9b`.
3. Correo de Git configurado y vinculado a tu GitHub. Puedes usar el correo `noreply` que GitHub muestra en Settings > Emails.
4. Conexión con GitHub ya autenticada para poder ejecutar `git push` sin introducir contraseñas en tareas programadas.

## 1. Instala el proyecto en un repositorio nuevo

Descomprime el ZIP en una carpeta, por ejemplo `C:\Dev\devlog-ai`. Abre **PowerShell** en ella:

```powershell
python --version
git --version
ollama list
```

Crea un repositorio **vacío, sin README**, en <https://github.com/new>, llamado `devlog-ai`. Después, dentro de la carpeta:

```powershell
git init -b main
git config user.name "TU_USUARIO_O_NOMBRE"
git config user.email "CORREO_VINCULADO_A_GITHUB"
git add .
git commit -m "chore: inicializar DevLog AI"
git remote add origin https://github.com/TU_USUARIO/devlog-ai.git
git push -u origin main
```

> Si tu Git no admite `git init -b main`, ejecuta `git init` y después `git branch -M main` una vez creado el primer commit.

## 2. Prueba la generación de hoy

```powershell
python devlog.py daily --no-push
```

Inspecciona el archivo nuevo en `entries/2026/AAAA-MM-DD.md`. El comando anterior **sí crea un commit local**, pero **no lo sube**. Para subirlo:

```powershell
git push origin main
```

En ejecuciones posteriores, `python devlog.py daily` crea y envía la entrada de hoy. Si ya existe, no crea duplicados.

## 3. Genera las 61 entradas retrospectivas: 20 de agosto a 19 de octubre de 2026

**Hazlo en grupos pequeños** para verificar calidad y conexión. Cada ejecución genera hasta cinco entradas que falten. Repite el comando hasta completar el intervalo:

```powershell
python devlog.py backfill --start 2026-08-20 --end 2026-10-19 --limit 5 --confirm-retrospective
```

También puedes procesar el intervalo entero con `--limit 61`. Si prefieres revisarlas antes de subirlas a GitHub, añade `--no-push` (los commits seguirán creándose en local). Este comando establece la **fecha de autor retrospectiva**, no falsifica la fecha real de generación del documento ni la fecha de committer.

**Precaución:** la generación con un modelo local consume recursos; se detiene si Ollama falla o el contenido no cumple la validación. No se publican entradas incompletas. Si necesitas recuperar un error después de un commit fallido, revisa `git status` antes de reintentar.

## 4. Programa las ejecuciones diarias

En PowerShell, desde la carpeta del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-task.ps1 -At "20:00"
```

El script crea una tarea de Windows llamada **DevLog AI**, a las 20:00 hora de tu PC, todos los días (incluye sábados y domingos). Puedes elegir otra hora con `-At "HH:mm"`.

El archivo `run-daily.cmd` ejecuta `catchup --days 7` para generar las entradas faltantes de los últimos siete días, incluyendo hoy; las anteriores al día real quedan marcadas como retrospectivas. Si la PC está apagada o Ollama no responde, no podrá ejecutarse en ese momento. Windows intentará reanudar la tarea cuando sea posible, y las ejecuciones siguientes pueden recuperar los días faltantes dentro del período de siete días.

### Verifica la tarea

```powershell
Get-ScheduledTask -TaskName "DevLog AI"
Get-Content .\logs\devlog.log -Tail 50
```

### Elimina la tarea si lo deseas

```powershell
Unregister-ScheduledTask -TaskName "DevLog AI" -Confirm:$false
```

## 5. Qué valida el programa

- Comprueba que Git está en una rama `main`, que el correo y nombre están configurados y que el árbol de trabajo está limpio.
- Exige seis campos de contenido técnico y un bloque de código Markdown.
- Usa salidas JSON estructuradas de Ollama para minimizar fallos de formato.
- No ejecuta el código generado por IA ni comandos sugeridos por el modelo.
- Evita archivos duplicados para un mismo día.
- Envía `git push origin main` solo después de guardar los commits locales.
- No altera archivos fuera de este repositorio ni usa `push --force`.

## 6. Solución de problemas

- **No encuentra modelo:** `ollama list`, luego `ollama pull qwen3.5:9b` si hace falta.
- **No conecta a Ollama:** inicia Ollama; comprueba <http://127.0.0.1:11434/api/tags>.
- **No permite push:** autentícate primero manualmente ejecutando `git push origin main` desde PowerShell.
- **GitHub no muestra cuadros:** verifica `git config user.email`, la rama predeterminada, que el repositorio no sea fork y que haya terminado el push; GitHub puede tardar hasta 24 horas en reflejar los commits.
- **Hay cambios locales pendientes:** ejecuta `git status` y resuélvelos antes de volver a automatizar; no se reescriben ni se incluyen archivos ajenos.
- **El modelo genera un contenido insuficiente:** no se crea commit; vuelve a ejecutar el comando.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas no requieren Ollama ni GitHub.

## Referencias

- GitHub: <https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference>
- GitHub: <https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/troubleshooting-missing-contributions>
- Ollama: <https://ollama.com/library/qwen3.5:9b>
- Ollama: <https://ollama.com/blog/structured-outputs>
- Microsoft: <https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create>
