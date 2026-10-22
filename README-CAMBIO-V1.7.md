# DevLog AI v1.7 — GPU First

Gaming Safe ya no exige que te alejes del teclado o ratón para poder ejecutar Qwen.

**Nueva política:** sin videojuegos conocidos en ejecución, uso de GPU **estrictamente menor al 10 %** y al menos **9000 MiB** de VRAM libres. El sistema verifica otra vez transcurridos 120 segundos. Solo después puede iniciar Qwen. Si detecta juegos entre entradas, pausa para continuar más adelante. **No puede detener una generación que ya esté ejecutándose.**

## Instalar sobre v1.6

1. Comprueba que no hay ningún `backfill` ni tarea DevLog AI ejecutándose.
2. Copia `gaming_safe.py` y `devlog.py` a la carpeta raíz de tu repo, reemplazando los originales. El resto no es necesario para el parche mínimo.
3. Si creaste `gaming-safe.local.json`, **debes editarlo**, pues sobrescribe los valores por defecto. Ajusta `"idle_minutes": 0` y `"max_gpu_utilization_percent": 10`. Si no existe, no lo crees: v1.7 adopta los valores automáticamente.
4. Comprueba: `python devlog.py safe-status`. Aun usando teclado, debería indicar `inactividad: no exigida`; puede mostrar POSPONER por GPU >=10%, VRAM o juego abierto.
5. Registra los cambios: `git add devlog.py gaming_safe.py` y haz commit y push como de costumbre.

**No hace falta reinstalar la tarea de Windows:** el lanzador invisible `scheduled_runner.pyw` y su configuración de las 20:00 no han cambiado. La próxima ejecución importará los archivos actualizados.

## Recuperar días pendientes

Al próximo inicio automático la tarea intentará recuperar hasta los últimos siete días. Si quieres hacerlo manualmente, `python devlog.py catchup --days 7`, pero este comando **no utiliza Gaming Safe**. Para ejecutar el modo protegido en consola: `python devlog.py safe-run --once --no-push` (puede generar commits locales, pero no publicarlos). Para diagnóstico sin generar: `python devlog.py safe-status`.

## Limitaciones

- La utilización de GPU es una **lectura instantánea**, no una detección perfecta de videojuegos. Algunos juegos pausados pueden estar por debajo del 10% y algunos procesos de trabajo superar ese nivel.
- Los ejecutables de juegos que no aparecen en la lista `games` pueden pasar inadvertidos. Añádelos en `gaming-safe.local.json` cuando corresponda; esta lista **reemplaza** la predeterminada, así que conserva las entradas anteriores.
- **No se revisa el porcentaje de GPU mientras Qwen genera**, porque la carga de Qwen falsearía esa lectura. La presencia de juegos conocidos sí se revisa entre entradas.
- Si tus mediciones normales alcanzan 13–18% durante la noche (como tu log anterior), el límite del 10% puede producir aplazamientos frecuentes. Lo puedes ajustar a 15% en `gaming-safe.local.json` si prefieres priorizar la continuidad.
- El launcher sigue siendo invisible. Revisa `logs/devlog.log` para confirmar el progreso; no confundas el arranque de la tarea con commits creados.
- El contenido generado por IA sigue siendo contenido nuevo en la fecha de ejecución, y no acredita actividad humana retrospectiva.
