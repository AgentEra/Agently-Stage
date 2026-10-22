"""Version and explicit executor-boundary probe; works without psutil."""

from __future__ import annotations

import concurrent.futures as cf
import json
import multiprocessing
import sys
import sysconfig
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agently_stage import Stage


def probe(factory):
    out = {}
    with factory() as pool:
        out["direct_pow"] = pool.submit(pow, 2, 10).result(timeout=20)
        stage = Stage(executor=pool)
        try:
            out["stage_pow"] = stage.go(pow, 2, 10).get(timeout=20)
        except Exception as error:
            out["stage_error"] = type(error).__name__ + ": " + str(error)
        finally:
            try:
                stage.close(timeout=20)
            except Exception as error:
                out["close_error"] = type(error).__name__ + ": " + str(error)
    return out


if __name__ == "__main__":
    out = {
        "python": sys.version,
        "gil_disabled_build": sysconfig.get_config_var("Py_GIL_DISABLED"),
        "gil_enabled": getattr(sys, "_is_gil_enabled", lambda: True)(),
        "process": probe(lambda: cf.ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn"))),
    }
    if hasattr(cf, "InterpreterPoolExecutor"):
        out["interpreter"] = probe(cf.InterpreterPoolExecutor)
    else:
        out["interpreter"] = "unavailable on this interpreter"
    print(json.dumps(out, indent=2))
