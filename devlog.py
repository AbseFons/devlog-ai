#!/usr/bin/env python3
"""DevLog AI: contenidos técnicos diarios generados localmente con Ollama y versionados con Git.

Requisitos: Python 3.10+, Git, Ollama local con qwen3.5:9b.
No ejecuta código generado por el modelo. No altera otros repositorios.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import random
import json
import os
import re
import subprocess
import sys
import time as wall_time
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ENTRIES = ROOT / 'entries'
START_DATE = date(2026, 8, 20)
MODEL = os.getenv('DEVLOG_MODEL', 'qwen3.5:9b')
OLLAMA_URL = os.getenv('DEVLOG_OLLAMA_URL', 'http://127.0.0.1:11434/api/chat')
TIMEOUT = int(os.getenv('DEVLOG_TIMEOUT', '360'))
# Se descarga de RAM tras cinco minutos de inactividad; Ollama lo carga bajo demanda.
KEEP_ALIVE = os.getenv('DEVLOG_KEEP_ALIVE', '5m')
MAX_GENERATION_ATTEMPTS = 3


class GenerationFormatError(RuntimeError):
    """La respuesta de Ollama es inválida, pero el lote puede continuar."""


class GamingPause(RuntimeError):
    """Usuario activo o juego detectado entre dos generaciones."""

DEFAULT_MIN_COMMITS = 1
DEFAULT_MAX_COMMITS = 10

TOPICS = [
    'Git: diferencia entre merge y rebase',
    'Python: comprensión de listas',
    'SQL: JOIN INNER y LEFT',
    'APIs REST: métodos HTTP',
    'Python: manejo de excepciones',
    'Git: ramas y estrategias de integración',
    'SQL: índices y consultas eficientes',
    'Python: pruebas unitarias con unittest',
    'Seguridad: validación de entradas',
    'JavaScript: promesas y async/await',
    'Algoritmos: búsqueda binaria',
    'Python: iteradores y generadores',
    'Diseño: principios SOLID',
    'Git: revisión de conflictos',
    'Bases de datos: transacciones ACID',
    'Python: dataclasses',
    'APIs: códigos de respuesta HTTP',
    'Algoritmos: ordenamiento por mezcla',
    'Testing: casos borde',
    'Seguridad: gestión de secretos',
    'Docker: imágenes y contenedores',
    'Python: pathlib y rutas',
    'Git: cherry-pick',
    'SQL: GROUP BY y HAVING',
    'APIs: paginación',
    'Python: tipado y anotaciones',
    'Diseño: separación de responsabilidades',
    'JavaScript: closures',
    'Algoritmos: pilas y colas',
    'Testing: mocks y stubs',
    'Seguridad: inyección SQL',
    'Git: hooks',
    'Python: context managers',
    'SQL: claves foráneas',
    'APIs: idempotencia',
    'Algoritmos: grafos y BFS',
    'Python: logging estructurado',
    'Diseño: adaptadores',
    'JavaScript: módulos ES',
    'Testing: cobertura y límites',
    'Seguridad: control de acceso',
    'Git: bisect',
    'Python: sqlite3',
    'SQL: normalización de tablas',
    'APIs: autenticación frente a autorización',
    'Algoritmos: recursión',
    'Python: sets y diccionarios',
    'Diseño: inyección de dependencias',
    'JavaScript: manejo de errores',
    'Testing: pruebas de integración',
    'Seguridad: hash de contraseñas',
    'Git: etiquetas y versiones',
    'Python: argparse',
    'SQL: Common Table Expressions',
    'APIs: rate limiting',
    'Algoritmos: programación dinámica',
    'Python: funciones puras',
    'Diseño: arquitectura por capas',
    'JavaScript: event loop',
    'Testing: pruebas basadas en propiedades',
    'Seguridad: dependencias y CVE',
    'Git: reflog',
    'Python: concurrencia básica',
    'SQL: EXPLAIN',
    'APIs: versionado',
    'Algoritmos: tablas hash',
    'Python: serialización JSON',
    'Diseño: repositorios',
    'JavaScript: manipulación del DOM',
    'Testing: pirámide de pruebas',
    'Seguridad: principio de mínimo privilegio',
    'Git: commits convencionales',
    'Python: pytest frente a unittest',
    'SQL: restricciones CHECK y UNIQUE',
    'APIs: diseño de errores',
    'Algoritmos: árboles binarios',
    'Python: decoradores',
    'Diseño: eventos de dominio',
    'JavaScript: fetch y AbortController',
    'Testing: pruebas de regresión',
]

SCHEMA = {
    'type': 'object',
    'properties': {
        'titulo': {'type': 'string'},
        'objetivo': {'type': 'string'},
        'explicacion': {'type': 'string'},
        'ejemplo': {
            'type': 'object',
            'properties': {
                'descripcion': {'type': 'string'},
                'lenguaje': {'type': 'string'},
                'codigo': {'type': 'string'},
            },
            'required': ['descripcion', 'lenguaje', 'codigo'],
            'additionalProperties': False,
        },
        'ejercicio': {'type': 'string'},
        'criterios': {'type': 'string'},
    },
    'required': ['titulo', 'objetivo', 'explicacion', 'ejemplo', 'ejercicio', 'criterios'],
    'additionalProperties': False,
}


def selected_topic(target: date, slot: int = 1) -> str:
    number = (target - START_DATE).days + (slot - 1) * 13
    round_number = max(0, number) // len(TOPICS) + 1
    topic = TOPICS[number % len(TOPICS)]
    return f'{topic} (serie {round_number})'


def daily_target(target: date, minimum: int, maximum: int) -> int:
    """Meta estable y variada para cada fecha.

    Cada bloque de 10 días reparte equilibradamente el rango elegido. Para
    1..10, cada valor aparece exactamente una vez por bloque, pero en orden
    barajado con una semilla reproducible. Reanudar nunca cambia la meta.
    """
    if not 1 <= minimum <= maximum <= 10:
        raise ValueError('El rango debe estar entre 1 y 10, y mínimo <= máximo.')
    delta = (target - START_DATE).days
    block, slot = divmod(delta, 10)
    seed = int.from_bytes(hashlib.sha256(
        f'devlog-v1.3:{block}:{minimum}:{maximum}'.encode('utf-8')
    ).digest()[:8], 'big')
    options = list(range(minimum, maximum + 1))
    # En rangos inferiores a 10, repetir opciones permite distribuirlas
    # sin que todos los días reciban siempre el mismo valor.
    distribution = [options[i % len(options)] for i in range(10)]
    random.Random(seed).shuffle(distribution)
    return distribution[slot]


def normalize_generated_item(item: object) -> object:
    """Formatea los bloques Markdown en Python, en vez de pedírselos a Qwen.

    También admite respuestas antiguas donde «ejemplo» era una cadena con
    Markdown, para no romper compatibilidad con entradas y pruebas v1.3.
    """
    if not isinstance(item, dict):
        return item
    example = item.get('ejemplo')
    if not isinstance(example, dict):
        return item
    if set(example) != {'descripcion', 'lenguaje', 'codigo'}:
        raise ValueError('El objeto ejemplo requiere descripcion, lenguaje y codigo.')
    description = example['descripcion']
    language = example['lenguaje']
    code = example['codigo']
    if not all(isinstance(x, str) for x in (description, language, code)):
        raise ValueError('Los campos de ejemplo deben ser cadenas JSON.')
    description = description.strip()
    language = language.strip().lower()
    code = code.strip().replace('\r\n', '\n')
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_+.#-]{0,23}', language):
        raise ValueError('El lenguaje del ejemplo es inválido.')
    if len(description) < 20:
        raise ValueError('La descripción del ejemplo es insuficiente.')

    # Algunos modelos devuelven accidentalmente un bloque ya delimitado.
    # Si está completo, quitar los delimitadores y construirlos nosotros.
    lines = code.splitlines()
    if lines and lines[0].startswith('```') and lines[-1].strip() == '```':
        code = '\n'.join(lines[1:-1]).strip()
    if '```' in code or len(code) < 25 or len(code.splitlines()) < 2:
        raise ValueError('El ejemplo no contiene varias líneas de código utilizable.')

    normalized = dict(item)
    normalized['ejemplo'] = f'{description}\n\n```{language}\n{code}\n```'
    return normalized


def generate(target: date, slot: int = 1) -> dict[str, str]:
    """Pide código como un campo JSON separado y arma Markdown de forma estable."""
    topic = selected_topic(target, slot)
    prompt = (
        'Eres un mentor de ingeniería de software. Responde SOLO con JSON según el esquema. '
        'Redacta una microlección ORIGINAL y útil en español. '
        f'Tema: {topic}. Fecha de catálogo: {target.isoformat()}. Entrada del día: {slot}. '
        'Incluye título concreto, objetivo de 20-60 palabras, explicación de 100-180 palabras, '
        'ejercicio reproducible y criterios específicos de evaluación. '
        'MUY IMPORTANTE: "ejemplo" es un OBJETO JSON, NO una cadena Markdown. '
        'Debe contener "descripcion" (explicación breve del ejemplo), '
        '"lenguaje" (por ejemplo "javascript", "python", "sql" o "bash") y '
        '"codigo" (solo código real, con al menos dos líneas, sin delimitadores Markdown). '
        'El programa pondrá los delimitadores Markdown por sí solo. '
        'En "codigo", no escribas tres acentos graves, únicamente el texto del código. '
        'Escribe un caso de uso realista. No uses comandos destructivos ni credenciales. '
        'No inventes que alguien trabajó ese día ni afirmes que el código fue probado. '
        'Evita contenido repetitivo o de relleno. Todos los demás campos son cadenas.'
    )
    messages = [
        {'role': 'system', 'content': 'Eres un asistente técnico preciso. Devuelve JSON válido según el esquema.'},
        {'role': 'user', 'content': prompt},
    ]
    last_error = None
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        payload = {
            'model': MODEL,
            'messages': messages,
            'format': SCHEMA,
            'stream': False,
            'think': False,
            'keep_alive': KEEP_ALIVE,
            'options': {'temperature': 0.2},
        }
        req = Request(
            OLLAMA_URL,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urlopen(req, timeout=TIMEOUT) as response:
                outer = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(
                'No se pudo consultar Ollama. Verifica que Ollama esté funcionando '
                f'y que el modelo {MODEL!r} esté instalado. Detalle: {exc}'
            ) from exc
        raw = outer.get('message', {}).get('content', '')
        if not raw:
            last_error = ValueError('Ollama devolvió una respuesta vacía.')
        else:
            try:
                item = normalize_generated_item(json.loads(raw))
                validate(item)
                return item
            except (ValueError, TypeError) as exc:
                last_error = exc

        if attempt < MAX_GENERATION_ATTEMPTS:
            print(f'[REINTENTO {attempt}/{MAX_GENERATION_ATTEMPTS}] '
                  f'Qwen no cumplió el formato: {last_error}', flush=True)
            # Una respuesta defectuosa no se ejecuta, guarda ni archiva.
            messages = [
                messages[0], messages[1],
                {'role': 'user', 'content':
                    f'La respuesta se rechazó por: {last_error}. Regenera los seis campos. '
                    'En especial, "ejemplo" debe ser un OBJETO con "descripcion", '
                    '"lenguaje" y "codigo". En "codigo" escribe solamente código '
                    'multilínea, SIN Markdown ni acentos graves. No pongas el ejemplo '
                    'como una cadena. Responde exclusivamente JSON según el esquema.'},
            ]
    raise GenerationFormatError(
        f'Qwen no produjo contenido válido tras {MAX_GENERATION_ATTEMPTS} intentos. '
        f'Último problema: {last_error}. Esta entrada quedó pendiente.'
    )


def validate(item: object) -> None:
    if not isinstance(item, dict) or set(item) != set(SCHEMA['required']):
        raise ValueError('Faltan campos o hay campos imprevistos en la salida del modelo.')
    limits = {'titulo': 8, 'objetivo': 40, 'explicacion': 150,
              'ejemplo': 80, 'ejercicio': 45, 'criterios': 45}
    for key, minimum in limits.items():
        val = item[key]
        if not isinstance(val, str) or not (minimum <= len(val.strip()) <= 18000):
            raise ValueError(f'Campo insuficiente, excesivo o inválido: {key}')
    if not re.search(r'(?m)^```[a-zA-Z0-9_+.-]*\s*\n[\s\S]+?\n```(?:\s|$)', item['ejemplo']):
        raise ValueError('El ejemplo no contiene un bloque de código Markdown completo (apertura y cierre).')


def to_markdown(target: date, item: dict[str, str], generated_at: datetime, retro: bool, slot: int = 1) -> str:
    mode = 'Retrospectiva (no demuestra actividad humana en esa fecha)' if retro else 'Programada / generación del día'
    fields = [
        f'# {item["titulo"].strip()}',
        '',
        f'- **Fecha del catálogo:** {target.isoformat()}',
        f'- **Entrada n.º:** {slot}',
        f'- **Generado:** {generated_at.isoformat(timespec="seconds")}',
        f'- **Tipo:** {mode}',
        f'- **Modelo local:** {MODEL}',
        '- **Estado:** pendiente de revisión',
        '',
        '## Objetivo', item['objetivo'].strip(), '',
        '## Explicación', item['explicacion'].strip(), '',
        '## Ejemplo (no ejecutado automáticamente)', item['ejemplo'].strip(), '',
        '## Ejercicio', item['ejercicio'].strip(), '',
        '## Criterios de revisión', item['criterios'].strip(), '',
    ]
    return '\n'.join(fields)


def git(*args: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(['git', *args], cwd=ROOT, env=env, capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), encoding='utf-8', errors='replace')
    if check and result.returncode:
        raise RuntimeError(f'Git {" ".join(args)} falló:\n{result.stderr.strip() or result.stdout.strip()}')
    return result



@contextmanager
def single_instance():
    """Evita que backfill y la tarea de las 20:00 modifiquen Git a la vez."""
    directory = ROOT / 'logs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'devlog.lock'
    with open(path, 'a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'\0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('DevLog AI ya está ejecutándose en otra ventana o tarea. '
                               'No se iniciará otro proceso simultáneo.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def check_repo() -> None:
    if git('rev-parse', '--is-inside-work-tree', check=False).stdout.strip() != 'true':
        raise RuntimeError('Esta carpeta todavía no es un repositorio Git. Sigue los pasos de README.md.')
    branch = git('branch', '--show-current').stdout.strip()
    if branch != 'main':
        raise RuntimeError(f'Estás en la rama {branch!r}; debes trabajar en main.')
    for property in ('user.email', 'user.name'):
        if not git('config', '--get', property, check=False).stdout.strip():
            raise RuntimeError(f'Configura Git primero: git config {property} "TU_VALOR"')


def check_clean() -> None:
    if git('status', '--porcelain', '--untracked-files=all').stdout.strip():
        raise RuntimeError('El repositorio tiene cambios sin registrar. Revisa git status antes de automatizar.')


def file_for(target: date, slot: int = 1) -> Path:
    if slot < 1 or slot > 10:
        raise ValueError('El número de entrada debe estar entre 1 y 10.')
    suffix = '' if slot == 1 else f'-{slot:02d}'
    return ENTRIES / str(target.year) / f'{target.isoformat()}{suffix}.md'


def create(target: date, *, retrospective: bool, no_push: bool, slot: int = 1) -> bool:
    output = file_for(target, slot)
    if output.exists():
        print(f'[OMITIDO] Ya existe {output.relative_to(ROOT)}')
        return False
    check_clean()
    print(f'[GENERANDO] {target.isoformat()} · entrada {slot:02d} · {selected_topic(target, slot)}', flush=True)
    item = generate(target, slot)
    now = datetime.now().astimezone()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_markdown(target, item, now, retrospective, slot), encoding='utf-8')
    path_rel = output.relative_to(ROOT).as_posix()
    env = os.environ.copy()
    if retrospective:
        # Fecha de autor = fecha de catálogo; fecha de commit = fecha real de generación.
        # GitHub muestra el gráfico a partir de la fecha de autor.
        local_tz = now.tzinfo
        env['GIT_AUTHOR_DATE'] = datetime.combine(target, time(12, 0), tzinfo=local_tz).isoformat()
        env['GIT_COMMITTER_DATE'] = now.isoformat()
    try:
        git('add', '--', path_rel)
        tag = 'retro' if retrospective else 'diario'
        git('commit', '-m', f'docs({tag}): lección {target.isoformat()} #{slot:02d}', '--', path_rel, env=env)
    except Exception:
        # El archivo no se elimina para permitir revisión y recuperación manual.
        print(f'[AVISO] El archivo está en {path_rel}; revisa git status para resolver el error.', file=sys.stderr)
        raise
    print(f'[COMMIT] {target.isoformat()} · entrada {slot:02d}')
    return True


def push() -> None:
    git('push', 'origin', 'main')
    print('[PUSH] Enviado a origin/main')


def days_in_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Usa la fecha YYYY-MM-DD.') from exc


def release_qwen() -> None:
    """Descarga del modelo mediante API local oficial. No afecta al servicio Ollama."""
    payload = {'model': MODEL, 'messages': [], 'keep_alive': 0, 'stream': False}
    req = Request(OLLAMA_URL, data=json.dumps(payload).encode('utf-8'),
                  headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(req, timeout=25) as response:
            result = json.load(response)
        print(f'[VRAM] Qwen descargado de Ollama ({result.get("done_reason", "solicitado")}).', flush=True)
    except (OSError, ValueError, HTTPError, URLError, TimeoutError) as exc:
        print(f'[AVISO] No fue posible descargar Qwen: {exc}. '
              'Ollama aplicará su keep_alive normal.', flush=True)


def gaming_status() -> int:
    from gaming_safe import check, load_config
    config = load_config(ROOT)
    status = check(config, before_load=True)
    print('[GAMING SAFE] ' + status.display(), flush=True)
    print('[GAMING SAFE] Esta prueba no genera commits ni carga Qwen.', flush=True)
    return 0 if status.safe else 2


def gaming_safe_run(*, days: int, interval_minutes: int, max_wait_minutes: int,
                    once: bool = False, no_push: bool = False) -> int:
    """Se ejecuta a las 20:00; si la GPU está ocupada, espera sin cargar Qwen.

    Permanece dentro de la tarea de Windows. Comprueba juegos conocidos antes
    de cada entrada; la inactividad humana solo se aplica si se configura.
    """
    from gaming_safe import check, load_config
    cfg = load_config(ROOT)
    if not 1 <= days <= 366:
        raise ValueError('--days debe estar entre 1 y 366.')
    if not 1 <= interval_minutes <= 120:
        raise ValueError('--interval-minutes debe estar entre 1 y 120.')
    if not 1 <= max_wait_minutes <= 1440:
        raise ValueError('--max-wait-minutes debe estar entre 1 y 1440.')
    deadline = wall_time.monotonic() + max_wait_minutes * 60
    idle_policy = 'no exigida' if cfg['idle_minutes'] == 0 else f'{cfg["idle_minutes"]} min'
    print(f'[GAMING SAFE] Vigilancia iniciada: intervalo {interval_minutes} min; '
          f'ventana de espera {max_wait_minutes} min; '
          f'inactividad {idle_policy}; '
          f'GPU < {cfg["max_gpu_utilization_percent"]}%; '
          f'VRAM libre >= {cfg["min_free_vram_mib"]} MiB.', flush=True)
    while True:
        before = check(cfg, before_load=True)
        print('[GAMING SAFE] ' + before.display(), flush=True)
        ready = before.safe
        if ready and cfg['stable_seconds']:
            print(f'[GAMING SAFE] Confirmando estabilidad durante {cfg["stable_seconds"]} s...', flush=True)
            if wall_time.monotonic() + cfg['stable_seconds'] > deadline:
                ready = False
            else:
                wall_time.sleep(cfg['stable_seconds'])
                after = check(cfg, before_load=True)
                print('[GAMING SAFE] Segunda medición: ' + after.display(), flush=True)
                ready = after.safe
        if ready:
            attempted = False
            def pause_if_playing():
                nonlocal attempted
                # No consultar GPU durante Qwen: la carga de inferencia daría un falso positivo.
                stage = check(cfg, before_load=False)
                if not stage.safe:
                    raise GamingPause(stage.display())
                attempted = True
            try:
                print('[GAMING SAFE] Condiciones libres. Iniciando catchup...', flush=True)
                rc = main(['catchup', '--days', str(days)] + (['--no-push'] if no_push else []),
                          safety_guard=pause_if_playing)
            finally:
                if attempted and cfg['unload_qwen_after_run']:
                    release_qwen()
            if rc != 3:
                return rc
            print('[GAMING SAFE] Se pausó entre entradas: progreso conservado. '
                  'Se reintentará cuando el equipo esté libre.', flush=True)
        if once:
            print('[GAMING SAFE] Ejecución única pospuesta; no se inició trabajo inseguro.', flush=True)
            return 2
        remaining = deadline - wall_time.monotonic()
        if remaining <= 0:
            print('[GAMING SAFE] Terminó la ventana de espera sin condiciones adecuadas. '
                  'La próxima tarea recuperará hasta los días configurados.', flush=True)
            return 0
        delay = min(interval_minutes * 60, remaining)
        print(f'[GAMING SAFE] Próxima evaluación en {delay/60:.1f} min.', flush=True)
        wall_time.sleep(delay)


def main(argv: list[str] | None = None, *, safety_guard=None) -> int:
    parser = argparse.ArgumentParser(description='DevLog AI — diario de desarrollo con Qwen local')
    sub = parser.add_subparsers(dest='command', required=True)
    def add_count_options(command):
        command.add_argument('--min-commits', type=int, default=DEFAULT_MIN_COMMITS,
                             help=f'Mínimo de commits diarios (por defecto {DEFAULT_MIN_COMMITS})')
        command.add_argument('--max-commits', type=int, default=DEFAULT_MAX_COMMITS,
                             help=f'Máximo de commits diarios (por defecto {DEFAULT_MAX_COMMITS})')

    daily = sub.add_parser('daily', help='Genera varias entradas y commits de hoy')
    add_count_options(daily)
    daily.add_argument('--no-push', action='store_true')

    backfill = sub.add_parser('backfill', help='Crea retrospectivamente entradas que faltan')
    add_count_options(backfill)
    backfill.add_argument('--start', type=parse_date, default=START_DATE)
    backfill.add_argument('--end', type=parse_date, default=date(2026, 10, 19))
    backfill.add_argument('--limit', type=int, default=5, help='Máximo de días incompletos por ejecución (por defecto, 5)')
    backfill.add_argument('--confirm-retrospective', action='store_true', help='Reconozco que es contenido generado ahora, no actividad humana histórica')
    backfill.add_argument('--no-push', action='store_true')

    plan = sub.add_parser('plan', help='Previsualiza cantidad de commits por fecha sin llamar a Qwen ni cambiar Git')
    add_count_options(plan)
    plan.add_argument('--start', type=parse_date, default=START_DATE)
    plan.add_argument('--end', type=parse_date, default=date(2026, 10, 19))

    catchup = sub.add_parser('catchup', help='Incluye hoy y recupera ejecuciones automatizadas perdidas')
    add_count_options(catchup)
    catchup.add_argument('--days', type=int, default=7)
    catchup.add_argument('--no-push', action='store_true')

    status_cmd = sub.add_parser('safe-status', help='Muestra si Gaming Safe puede iniciar sin cargar Qwen ni tocar Git')
    safe_run = sub.add_parser('safe-run', help='Espera hasta que el equipo esté libre y ejecuta catchup')
    safe_run.add_argument('--days', type=int, default=7, help='Ventana de recuperación automática, por defecto 7 días')
    safe_run.add_argument('--interval-minutes', type=int, default=15, help='Cada cuántos minutos revisar si está ocupado')
    safe_run.add_argument('--max-wait-minutes', type=int, default=420, help='Tiempo máximo de espera, por defecto 7 horas')
    safe_run.add_argument('--once', action='store_true', help='Comprueba y prueba solo una vez; útil para diagnóstico')
    safe_run.add_argument('--no-push', action='store_true', help='No enviar a GitHub')

    args = parser.parse_args(argv)
    if args.command == 'safe-status':
        return gaming_status()
    if args.command == 'safe-run':
        check_repo()
        return gaming_safe_run(days=args.days, interval_minutes=args.interval_minutes,
                               max_wait_minutes=args.max_wait_minutes, once=args.once,
                               no_push=args.no_push)
    if not 1 <= args.min_commits <= args.max_commits <= 10:
        parser.error('Indica --min-commits y --max-commits entre 1 y 10 (min <= max).')
    check_repo()
    today = datetime.now().astimezone().date()
    dates: list[date]
    if args.command == 'daily':
        dates = [today]
    elif args.command == 'plan':
        if args.end < args.start or args.end > today:
            parser.error('El intervalo debe ser válido y no incluir fechas futuras.')
        targets = 0
        missing = 0
        for target in days_in_range(args.start, args.end):
            goal = daily_target(target, args.min_commits, args.max_commits)
            existing = sum(file_for(target, slot).exists() for slot in range(1, goal + 1))
            extras = sum(file_for(target, slot).exists() for slot in range(goal + 1, 11))
            targets += goal
            missing += goal - existing
            extra_note = f' · fuera del objetivo: {extras}' if extras else ''
            print(f'[PLAN] {target.isoformat()} · objetivo: {goal} · existentes: {existing} '
                  f'· faltan: {goal - existing}{extra_note}')
        print(f'[RESUMEN] {targets} entradas objetivo · {missing} entradas por generar.')
        return 0
    elif args.command == 'backfill':
        if not args.confirm_retrospective:
            parser.error('Para backfill usa --confirm-retrospective (ver README.md).')
        if args.end < args.start or args.end > today:
            parser.error('El intervalo debe ser válido y no incluir fechas futuras.')
        if not 1 <= args.limit <= 366:
            parser.error('--limit debe estar entre 1 y 366.')
        dates = [
            d for d in days_in_range(args.start, args.end)
            if any(not file_for(d, slot).exists()
                   for slot in range(1, daily_target(d, args.min_commits, args.max_commits) + 1))
        ][:args.limit]
    else:
        if not 1 <= args.days <= 366:
            parser.error('--days debe estar entre 1 y 366.')
        start = max(date(2026, 10, 20), today - timedelta(days=args.days - 1))
        dates = list(days_in_range(start, today))

    count = 0
    skipped = 0
    failures = []
    for target in dates:
        target_count = daily_target(target, args.min_commits, args.max_commits)
        print(f'[PLAN] {target.isoformat()} · objetivo: {target_count} commit(s)', flush=True)
        retro = target != today
        for slot in range(1, target_count + 1):
            try:
                if safety_guard is not None and not file_for(target, slot).exists():
                    safety_guard()
                if create(target, retrospective=retro, no_push=args.no_push, slot=slot):
                    count += 1
                else:
                    skipped += 1
            except GamingPause as exc:
                print(f'[PAUSA] {exc}', flush=True)
                if count and not args.no_push:
                    push()
                print(f'[PAUSA] {count} commit(s) nuevos conservados; '
                      'las entradas pendientes se reanudarán en la siguiente oportunidad.', flush=True)
                return 3
            except GenerationFormatError as exc:
                # No abortar los 5 días por un solo ejemplo defectuoso.
                # Los archivos anteriores y su historial Git permanecen intactos.
                failures.append((target, slot, str(exc)))
                print(f'[PENDIENTE] {target.isoformat()} · entrada {slot:02d}: {exc}', flush=True)
    if count and not args.no_push:
        push()
    print(f'[FIN] {count} commit(s) nuevos; {skipped} entrada(s) ya existían; '
          f'{len(failures)} entrada(s) pendientes por error.')
    if failures:
        print('[AVISO] Puedes repetir el mismo comando; se reintentarán las entradas pendientes. '
              'Los commits generados correctamente se conservaron.')
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        with single_instance():
            raise SystemExit(main())
    except (ValueError, RuntimeError) as error:
        print(f'[ERROR] {error}', file=sys.stderr)
        raise SystemExit(1)
