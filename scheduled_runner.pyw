# DevLog AI v1.6: lanzador sin consola para el Programador de tareas de Windows.
# Con pythonw.exe no hay consola; por eso toda salida y error se escribe en logs/.
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import runpy
import sys
import traceback

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "logs" / "devlog.log"
ARGS = ["safe-run", "--days", "7", "--interval-minutes", "15", "--max-wait-minutes", "420"]

def stamp() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")

def run(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8", buffering=1) as logfile:
            # pythonw no tiene stdout/stderr; redireccionar antes de cargar el programa.
            sys.stdout = logfile
            sys.stderr = logfile
            print(f"[TASK] {stamp()} · Inicio invisible · proyecto: {ROOT}", flush=True)
            if argv == ["--self-test"]:
                print("[TASK] Autoprueba correcta. No se ha iniciado Qwen ni se modificó Git.", flush=True)
                return 0
            if argv:
                print("[TASK][ERROR] Argumentos no reconocidos. Se admite solo --self-test.", flush=True)
                return 2
            if not (ROOT / "devlog.py").is_file() or not (ROOT / "gaming_safe.py").is_file():
                print("[TASK][ERROR] Faltan devlog.py o gaming_safe.py en la carpeta del proyecto.", flush=True)
                return 1
            old_cwd = Path.cwd()
            old_argv = sys.argv[:]
            try:
                os.chdir(ROOT)
                sys.argv = [str(ROOT / "devlog.py"), *ARGS]
                try:
                    runpy.run_path(str(ROOT / "devlog.py"), run_name="__main__")
                    code = 0
                except SystemExit as exc:
                    if exc.code is None:
                        code = 0
                    elif isinstance(exc.code, int):
                        code = exc.code
                    else:
                        print(f"[TASK][ERROR] {exc.code}", flush=True)
                        code = 1
                except BaseException:
                    print("[TASK][ERROR] Excepción no controlada:", flush=True)
                    traceback.print_exc(file=logfile)
                    code = 1
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)
            print(f"[TASK] {stamp()} · Fin · código de salida: {code}", flush=True)
            return code
    except BaseException:
        # Sin consola, el usuario no vería el error. Intentar dejar registro alternativo.
        try:
            with (ROOT / "devlog-task-error.log").open("a", encoding="utf-8") as f:
                f.write(f"[{stamp()}] No fue posible iniciar tarea invisible\n")
                traceback.print_exc(file=f)
        except BaseException:
            pass
        return 1
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr

if __name__ == "__main__":
    raise SystemExit(run())
