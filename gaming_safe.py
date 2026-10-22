"""Gaming Safe de DevLog AI: inicia Qwen solo con GPU disponible.

No es un detector infalible de videojuegos. Combina procesos conocidos,
utilización de GPU NVIDIA y memoria libre. La comprobación de inactividad
es opcional y está desactivada por defecto.
No finaliza juegos ni interrumpe una inferencia de Ollama en curso.
"""
from __future__ import annotations

import csv
import ctypes
import io
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GAMES = [
    'cs2.exe', 'csgo.exe', 'valorant-win64-shipping.exe',
    'fortniteclient-win64-shipping.exe', 'r5apex.exe',
    'league of legends.exe', 'leagueclientux.exe',
    'overwatch.exe', 'overwatch2.exe', 'cod.exe', 'cod22-cod.exe',
    'gta5.exe', 'gta5_enhanced.exe', 'cyberpunk2077.exe',
    'eldenring.exe', 'starfield.exe', 'dota2.exe', 'witcher3.exe',
    'minecraft.windows.exe', 'hl2.exe', 'robloxplayerbeta.exe',
    'rocketleague.exe', 'rdr2.exe', 'destiny2.exe',
]

DEFAULT_CONFIG = {
    'idle_minutes': 0,  # 0: no exigir inactividad de teclado/ratón
    'max_gpu_utilization_percent': 10,
    'min_free_vram_mib': 9000,
    'stable_seconds': 120,
    'gpu_index': 0,
    'games': DEFAULT_GAMES,
    'unload_qwen_after_run': True,
}


class SafetyUnavailable(RuntimeError):
    """No es posible observar las señales exigidas: se bloquea por precaución."""


@dataclass(frozen=True)
class Status:
    safe: bool
    reasons: tuple[str, ...]
    idle_seconds: float | None = None
    gpu_percent: float | None = None
    free_vram_mib: int | None = None
    games: tuple[str, ...] = ()

    def display(self) -> str:
        gpu = '?' if self.gpu_percent is None else f'{self.gpu_percent:.0f}%'
        mem = '?' if self.free_vram_mib is None else f'{self.free_vram_mib} MiB'
        idle = 'no exigida' if self.idle_seconds is None else f'{self.idle_seconds/60:.1f} min'
        label = 'LIBRE' if self.safe else 'POSPONER'
        details = '; '.join(self.reasons) if self.reasons else 'condiciones cumplidas'
        return f'[{label}] inactividad: {idle} · GPU: {gpu} · VRAM libre: {mem} · {details}'


def load_config(root: Path) -> dict:
    """El archivo local es opcional y está excluido de Git."""
    config = dict(DEFAULT_CONFIG)
    config['games'] = list(DEFAULT_GAMES)
    file = root / 'gaming-safe.local.json'
    if file.is_file():
        raw = json.loads(file.read_text(encoding='utf-8-sig'))
        if not isinstance(raw, dict):
            raise ValueError('gaming-safe.local.json debe contener un objeto JSON.')
        extra = set(raw) - set(DEFAULT_CONFIG)
        if extra:
            raise ValueError(f'Claves desconocidas en gaming-safe.local.json: {sorted(extra)}')
        config.update(raw)
    for key, low, high in (
        ('idle_minutes', 0, 120), ('max_gpu_utilization_percent', 1, 90),
        ('min_free_vram_mib', 256, 65536), ('stable_seconds', 0, 3600),
        ('gpu_index', 0, 15),
    ):
        value = config[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'Valor incorrecto {key}: se espera entero entre {low} y {high}.')
    if type(config['unload_qwen_after_run']) is not bool:
        raise ValueError('unload_qwen_after_run debe ser true o false.')
    if not isinstance(config['games'], list) or not all(
        isinstance(g, str) and g.strip() and len(g) < 120 for g in config['games']
    ):
        raise ValueError('games debe ser una lista de ejecutables, ej. ["cs2.exe"].')
    return config


def windows_idle_seconds() -> float:
    if os.name != 'nt':
        raise SafetyUnavailable('Gaming Safe requiere Windows para detectar inactividad.')
    from ctypes import wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetLastInputInfo.restype = wintypes.BOOL
    kernel32.GetTickCount64.argtypes = []
    kernel32.GetTickCount64.restype = ctypes.c_uint64
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise SafetyUnavailable('Windows no permitió consultar la inactividad de sesión.')
    current_tick = kernel32.GetTickCount64() & 0xFFFFFFFF
    idle_ms = (current_tick - int(info.dwTime)) & 0xFFFFFFFF
    return idle_ms / 1000.0


def active_game_processes(known: list[str]) -> tuple[str, ...]:
    if os.name != 'nt':
        raise SafetyUnavailable('No se pudieron revisar los juegos fuera de Windows.')
    # tasklist ya existe en Windows y no requiere módulos externos.
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], text=True,
                            capture_output=True, timeout=12, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), encoding='utf-8',
                            errors='replace', check=False)
    if result.returncode:
        raise SafetyUnavailable(f'tasklist falló: {result.stderr.strip()}')
    process_names = {row[0].casefold().strip() for row in csv.reader(io.StringIO(result.stdout)) if row}
    found = {name for name in known if name.casefold() in process_names}
    return tuple(sorted(found, key=str.casefold))


def gpu_metrics(index: int = 0) -> tuple[float, int]:
    exe = shutil.which('nvidia-smi')
    if not exe and os.name == 'nt':
        candidates = [
            Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'nvidia-smi.exe',
            Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'NVIDIA Corporation' / 'NVSMI' / 'nvidia-smi.exe',
        ]
        exe = next((str(path) for path in candidates if path.exists()), None)
    if not exe:
        raise SafetyUnavailable('No se encontró nvidia-smi. No iniciaré Qwen a ciegas.')
    args = [exe, '--query-gpu=utilization.gpu,memory.used,memory.total',
            '--format=csv,noheader,nounits']
    result = subprocess.run(args, capture_output=True, text=True, timeout=12, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                            encoding='utf-8', errors='replace', check=False)
    if result.returncode:
        raise SafetyUnavailable(f'nvidia-smi falló: {result.stderr.strip()}')
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if index >= len(lines):
        raise SafetyUnavailable(f'No existe GPU índice {index} según nvidia-smi.')
    try:
        util, used, total = (int(float(x.strip())) for x in lines[index].split(','))
        if not (0 <= util <= 100 and 0 <= used <= total and total > 0):
            raise ValueError('Valores fuera de rango')
    except (ValueError, TypeError) as exc:
        raise SafetyUnavailable('La salida de nvidia-smi es ilegible.') from exc
    return float(util), total - used


def check(config: dict, *, before_load: bool = True) -> Status:
    """Al iniciar comprueba GPU+VRAM. Durante Qwen se ignoran ambas: es su carga."""
    reasons = []
    idle = utilization = None
    free = None
    games = ()
    if config['idle_minutes'] > 0:
        try:
            idle = windows_idle_seconds()
            if idle < config['idle_minutes'] * 60:
                reasons.append(f'equipo activo (< {config["idle_minutes"]} min)')
        except (OSError, SafetyUnavailable) as exc:
            reasons.append(f'inactividad no verificable: {exc}')
    try:
        games = active_game_processes(config['games'])
        if games:
            reasons.append('juego detectado: ' + ', '.join(games))
    except (OSError, subprocess.SubprocessError, SafetyUnavailable) as exc:
        reasons.append(f'procesos no verificables: {exc}')
    if before_load:
        try:
            utilization, free = gpu_metrics(config['gpu_index'])
            if utilization >= config['max_gpu_utilization_percent']:
                reasons.append(f'GPU alta (>= {config["max_gpu_utilization_percent"]}%)')
            if free < config['min_free_vram_mib']:
                reasons.append(f'VRAM libre insuficiente (< {config["min_free_vram_mib"]} MiB)')
        except (OSError, subprocess.SubprocessError, SafetyUnavailable) as exc:
            reasons.append(f'GPU no verificable: {exc}')
    return Status(not reasons, tuple(reasons), idle, utilization, free, games)
