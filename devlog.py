#!/usr/bin/env python3
"""DevLog AI: contenidos técnicos diarios generados localmente con Ollama y versionados con Git.

Requisitos: Python 3.10+, Git, Ollama local con qwen3.5:9b.
No ejecuta código generado por el modelo. No altera otros repositorios.
"""
from __future__ import annotations

import argparse
import hashlib
import random
import json
import os
import re
import subprocess
import sys
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
DEFAULT_MIN_COMMITS = 2
DEFAULT_MAX_COMMITS = 5

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
            'type': 'string',
            'description': 'Incluye código real en un bloque Markdown con apertura ```python y cierre ``` en líneas separadas.'
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
    """Distribución uniforme reproducible por fecha y configuración.

    No usamos hash() de Python porque cambia entre ejecuciones. Repetir un día
    conserva su objetivo y permite reanudar sin commits duplicados.
    """
    if not 1 <= minimum <= maximum <= 10:
        raise ValueError('El rango debe estar entre 1 y 10, y mínimo <= máximo.')
    seed = int.from_bytes(hashlib.sha256(
        f'devlog-v1.2:{target.isoformat()}:{minimum}:{maximum}'.encode('utf-8')
    ).digest()[:8], 'big')
    return random.Random(seed).randint(minimum, maximum)


def generate(target: date, slot: int = 1) -> dict[str, str]:
    """Solicita una lección, valida la salida y reintenta respuestas mal formadas."""
    topic = selected_topic(target, slot)
    prompt = (
        'Eres un mentor de ingeniería de software. Responde SOLO con JSON según el esquema. '
        'Redacta una microlección ORIGINAL y útil en español, orientada a desarrolladores. '
        f'Tema asignado: {topic}. Fecha de catálogo: {target.isoformat()}. '
        f'Entrada numerada del día: {slot}. Crea un contenido distinto para este tema. '
        'Escribe un título concreto, un objetivo comprobable (20-60 palabras), '
        'una explicación de 100-180 palabras, un ejemplo de código en Markdown '
        'con un caso de uso realista (no uses comandos destructivos ni credenciales), '
        'un ejercicio reproducible y criterios específicos para revisarlo. '
        'REQUISITO OBLIGATORIO del campo "ejemplo": debe contener un bloque de código real '
        'en Markdown, que EMPIECE en una línea con tres acentos graves y un lenguaje '
        '(por ejemplo ```python), tenga varias líneas de código y TERMINE en una línea '
        'con tres acentos graves. Incluye el bloque dentro de la cadena JSON como texto '
        'con saltos de línea escapados, no como una propiedad aparte. '
        'No inventes que alguien trabajó ese día, ni afirmes que el ejemplo fue probado. '
        'Evita clichés y contenido de relleno. Devuelve cadenas simples en todos los campos.'
    )
    messages = [
        {'role': 'system', 'content': 'Eres un asistente de documentación técnica preciso. Responde solo con JSON válido.'},
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
                item = json.loads(raw)
                validate(item)
                return item
            except (ValueError, TypeError) as exc:
                last_error = exc

        if attempt < MAX_GENERATION_ATTEMPTS:
            print(f'[REINTENTO {attempt}/{MAX_GENERATION_ATTEMPTS}] '
                  f'Qwen no cumplió el formato: {last_error}', flush=True)
            # No ejecutamos ni archivamos la respuesta inválida.
            messages = [
                messages[0], messages[1],
                {'role': 'user', 'content':
                    'La respuesta anterior fue rechazada: '
                    f'{last_error}. Regenera los seis campos desde cero. '
                    'En particular, el campo "ejemplo" DEBE incluir un bloque de código '
                    'Markdown completo: apertura ```python, código con saltos de línea, '
                    'cierre ```. Devuelve exclusivamente el objeto JSON válido.'},
            ]
    raise RuntimeError(
        f'Qwen no produjo contenido válido tras {MAX_GENERATION_ATTEMPTS} intentos. '
        f'Último problema: {last_error}. No se guardó ni publicó ningún commit.'
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
    result = subprocess.run(['git', *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and result.returncode:
        raise RuntimeError(f'Git {" ".join(args)} falló:\n{result.stderr.strip() or result.stdout.strip()}')
    return result


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
        git('commit', '-m', f'docs({tag}): lección {target.isoformat()} #{slot:02d} [generada con IA]', '--', path_rel, env=env)
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


def main(argv: list[str] | None = None) -> int:
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
    backfill.add_argument('--limit', type=int, default=5, help='Máximo de entradas por ejecución (por defecto, 5)')
    backfill.add_argument('--confirm-retrospective', action='store_true', help='Reconozco que es contenido generado ahora, no actividad humana histórica')
    backfill.add_argument('--no-push', action='store_true')

    catchup = sub.add_parser('catchup', help='Incluye hoy y recupera ejecuciones automatizadas perdidas')
    add_count_options(catchup)
    catchup.add_argument('--days', type=int, default=7)
    catchup.add_argument('--no-push', action='store_true')

    args = parser.parse_args(argv)
    if not 1 <= args.min_commits <= args.max_commits <= 10:
        parser.error('Indica --min-commits y --max-commits entre 1 y 10 (min <= max).')
    check_repo()
    today = datetime.now().astimezone().date()
    dates: list[date]
    if args.command == 'daily':
        dates = [today]
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
    for target in dates:
        target_count = daily_target(target, args.min_commits, args.max_commits)
        print(f'[PLAN] {target.isoformat()} · objetivo: {target_count} commit(s)', flush=True)
        retro = target != today
        for slot in range(1, target_count + 1):
            if create(target, retrospective=retro, no_push=args.no_push, slot=slot):
                count += 1
            else:
                skipped += 1
    if count and not args.no_push:
        push()
    print(f'[FIN] {count} commit(s) nuevos; {skipped} entrada(s) ya existían.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as error:
        print(f'[ERROR] {error}', file=sys.stderr)
        raise SystemExit(1)
