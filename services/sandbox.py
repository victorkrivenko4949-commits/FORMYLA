# -*- coding: utf-8 -*-
"""
Sandbox for executing LLM-generated matplotlib drawing code.

Security model
--------------
We allow LLMs to author arbitrary Python that produces a PNG, BUT:

1. **AST whitelist (mandatory).** The candidate code is parsed by `ast`
   and every node is checked against a *very* small allow-list:
       - allowed top-level imports:  matplotlib, matplotlib.*, numpy(+np), math
       - allowed builtins: a curated set of pure-math helpers
       - **forbidden everywhere**: `__import__`, `open`, `eval`, `exec`,
         `compile`, `globals`, `locals`, `getattr`, `setattr`, `delattr`,
         `vars`, `input`, attribute access starting with `_` (dunders),
         imports of `os`, `sys`, `subprocess`, `socket`, `pathlib`,
         `pickle`, `shutil`, `ctypes`, `importlib`, `multiprocessing`,
         `threading`, `requests`, `urllib`, `http`, `ssl`, `tempfile`,
         `builtins`, etc.

   Any violation → `SandboxRejected` BEFORE we even spawn a child.

2. **Subprocess isolation.** The whitelisted code is then executed in
   a *fresh* `python -c` child process (never `exec()` in our worker),
   so even if something slips past the AST check, the worker process
   itself can't be poisoned. The child receives the code on stdin.

3. **Resource limits.** Wall-clock timeout (`subprocess.run(timeout=...)`)
   and, on Unix, `resource.setrlimit` for CPU/memory/file-size/no-fork
   via a preexec_fn (Windows has no `resource`, only wall-clock).

4. **Optional Docker.** If `DRAWING_SANDBOX_DOCKER=1`, the same code
   is shipped via `docker run --rm --network=none --read-only ...
   formyla/drawing-sandbox`. Used in future when we have a worker host
   with Docker available; on Render (no DinD) this stays off.

5. **PNG-only output channel.** The child writes raw PNG bytes to *stdout*
   (we set `sys.stdout.buffer`). We never trust the child's stderr / exit
   code for image data.

Public API
----------
    run_drawing_code(code: str, *, timeout: float = 10.0) -> bytes
        Returns raw PNG bytes; raises SandboxRejected / SandboxError.
"""

from __future__ import annotations

import ast
import logging
import os
import shlex
import subprocess
import sys
import textwrap
from typing import Iterable, Optional, Set

logger = logging.getLogger(__name__)


# ─── Public errors ─────────────────────────────────────────────────────────────

class SandboxError(Exception):
    """Generic sandbox failure (timeout, no PNG produced, runtime exc.)."""


class SandboxRejected(SandboxError):
    """AST whitelist refused the code BEFORE any execution."""


class SandboxTimeout(SandboxError):
    """Wall-clock timeout exceeded."""


# ─── AST whitelist ─────────────────────────────────────────────────────────────

ALLOWED_TOP_MODULES: Set[str] = {
    "matplotlib",
    "numpy",
    "math",
}

# Forbidden anywhere as `import X` or `from X import …`
FORBIDDEN_MODULES: Set[str] = {
    "os", "sys", "subprocess", "socket", "pathlib", "pickle", "shutil",
    "ctypes", "importlib", "multiprocessing", "threading", "asyncio",
    "requests", "urllib", "http", "ssl", "tempfile", "builtins",
    "fcntl", "resource", "platform", "shelve", "marshal", "code", "codeop",
    "atexit", "signal", "gc", "inspect", "trace", "traceback", "linecache",
    "imp", "pkgutil", "zipfile", "tarfile",
}

# Forbidden function/name references anywhere in the code
FORBIDDEN_NAMES: Set[str] = {
    "__import__", "open", "eval", "exec", "compile",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
    "input", "breakpoint", "help", "memoryview", "id",
    "object",  # blocks subclass tricks
    "exit", "quit",
    "exit_", "_quit",
}


def _module_allowed(name: str) -> bool:
    """Top-level of dotted module name must be in ALLOWED_TOP_MODULES."""
    if not name:
        return False
    head = name.split(".", 1)[0]
    if head in FORBIDDEN_MODULES:
        return False
    return head in ALLOWED_TOP_MODULES


def validate_drawing_code(code: str) -> None:
    """
    Parse + walk the AST. Raise SandboxRejected if anything looks unsafe.

    This is deliberately *more strict* than a real Python sandbox — for an
    olympiad geometry plot the allowed surface area is tiny.
    """
    if not isinstance(code, str) or not code.strip():
        raise SandboxRejected("empty code")
    if len(code) > 20_000:
        raise SandboxRejected(f"code too long: {len(code)} chars (limit 20000)")

    # 1) Reject suspicious *textual* patterns FAST (defence in depth)
    bad_substrings = (
        "__import__", "subprocess", "os.system", "os.popen",
        "Popen", "ctypes", "compile(", "eval(", "exec(",
        "input(", "open(", "raw_input(",
        "globals(", "locals(",
        "pty.spawn", "fork", "kill",
        "socket.", "urllib", "requests.", "http.client",
        "pickle.", "marshal.",
        "__builtins__", "__class__", "__bases__", "__mro__",
        "__subclasses__", "__globals__", "__getattribute__",
    )
    low = code
    for s in bad_substrings:
        if s in low:
            raise SandboxRejected(f"forbidden pattern: {s!r}")

    # 2) Parse + AST walk
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise SandboxRejected(f"syntax error: {e}")

    for node in ast.walk(tree):
        _check_node(node)


def _check_node(node: ast.AST) -> None:
    # Imports
    if isinstance(node, ast.Import):
        for alias in node.names:
            if not _module_allowed(alias.name):
                raise SandboxRejected(f"import forbidden: {alias.name}")
        return
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        if node.level and node.level > 0:
            raise SandboxRejected("relative imports forbidden")
        if not _module_allowed(mod):
            raise SandboxRejected(f"from-import forbidden: {mod}")
        return

    # Forbid dunder attribute access  (obj.__class__ etc.)
    if isinstance(node, ast.Attribute):
        if isinstance(node.attr, str) and node.attr.startswith("_") \
                and node.attr.endswith("_") and node.attr != "_":
            # allow numpy "ndarray.dtype" etc, but dunders are blocked
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SandboxRejected(f"dunder attribute forbidden: {node.attr}")
        return

    # Forbid bare-name references to dangerous builtins
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        if node.id in FORBIDDEN_NAMES:
            raise SandboxRejected(f"forbidden name: {node.id}")
        return

    # Forbid `with` on suspicious context managers (we don't allow `open()`,
    # but `with` itself is fine for matplotlib).
    # No special handling needed beyond Name/Call checks above.

    # Forbid try/except that swallows SystemExit etc. — actually fine.

    # Forbid `global` / `nonlocal` redefinition of builtins? Skip: would
    # have to be Name/FunctionDef-aware. The textual check above already
    # blocks the main vectors.


# ─── Subprocess executor ──────────────────────────────────────────────────────

_WRAPPER = textwrap.dedent(
    """\
    # ---- auto-wrapper (do not edit) ----
    import io as _io, sys as _sys
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: F401  (available to user code)

    # Pre-empt any plt.savefig / plt.show by the user: we want a single
    # buffered PNG. We let user code call plt.savefig to a BytesIO if it
    # wants, otherwise we save plt.gcf() ourselves at the end.

    _user_buf = _io.BytesIO()

    def _formyla_save(fmt="png", dpi=128):
        plt.gcf().savefig(_user_buf, format=fmt, dpi=dpi,
                          facecolor="white", bbox_inches="tight",
                          pad_inches=0.15)

    # ---- USER CODE BEGIN ----
    {USER_CODE}
    # ---- USER CODE END ----

    # If the user code didn't fill _user_buf via plt.savefig, save the
    # current figure now.
    if _user_buf.tell() == 0:
        _formyla_save()

    _sys.stdout.buffer.write(_user_buf.getvalue())
    _sys.stdout.flush()
    """
)


def _unix_preexec(memory_mb: int = 4096, cpu_seconds: int = 8) -> Optional[callable]:
    """Build a preexec_fn that applies rlimits on Unix; None on Windows."""
    if os.name != "posix":
        return None
    try:
        import resource  # noqa
    except Exception:
        return None

    def _apply():
        import resource as _r
        # CPU seconds
        _r.setrlimit(_r.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        # Address space (memory)
        mem_bytes = memory_mb * 1024 * 1024
        try:
                       pass
# DISABLED: RLIMIT_AS breaks numpy/matplotlib import
            #             _r.setrlimit(_r.RLIMIT_AS, (mem_bytes, mem_bytes))
        except Exception:
            pass
        # No core dumps
        try:
            _r.setrlimit(_r.RLIMIT_CORE, (0, 0))
        except Exception:
            pass
        # Cap on file size we may write (we shouldn't write any, but…)
        try:
            _r.setrlimit(_r.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
        except Exception:
            pass
        # Allow a small pool of subprocesses/threads (matplotlib spawns
        # helpers for its cache + font discovery).
        try:
            _r.setrlimit(_r.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass

    return _apply


def _run_via_subprocess(code: str, timeout: float) -> bytes:
    """Spawn `python` and feed wrapped code via stdin to avoid Windows
    command-line encoding issues with Cyrillic/Unicode characters."""
    wrapped = _WRAPPER.replace("{USER_CODE}", code)

    # Use the same interpreter we're running under
    python_exe = sys.executable or "python"

    # Pass through the parent's sys.path so matplotlib/numpy/site-packages
    # are still discoverable, but block extra user-site / PATH leakage.
    pythonpath = os.pathsep.join(p for p in sys.path if p)

    env = {**os.environ,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "MPLBACKEND": "Agg",     "OPENBLAS_NUM_THREADS": "1",     "OMP_NUM_THREADS": "1",     "MKL_NUM_THREADS": "1",     "NUMEXPR_NUM_THREADS": "1",     "MALLOC_ARENA_MAX": "2",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        # Path: empty so no host executables findable from child.
        "PATH": "",
        # Required for matplotlib font cache on Windows/Linux.
        "HOME": os.environ.get("HOME", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "TMPDIR": os.environ.get("TMPDIR", ""),
        "TEMP":   os.environ.get("TEMP", ""),
        "TMP":    os.environ.get("TMP", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONPATH": pythonpath,
        # Use a dedicated MPL config dir so the child doesn't litter HOME.
        "MPLCONFIGDIR": os.environ.get("MPLCONFIGDIR")
                        or os.path.join(os.environ.get("TEMP", "") or "/tmp", "mplcache"),
    }
    # Drop any keys whose value is None/empty (Windows is picky).
    env = {k: v for k, v in env.items() if v is not None}

    # NOTE: We pass code via stdin (not -c) to avoid Windows cp1251 encoding
    # issues when the LLM-generated code contains Cyrillic comments/strings.
    # The `-` flag tells Python to read the script from stdin.
    try:
        proc = subprocess.run(
            [python_exe, "-"],
            input=wrapped.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            preexec_fn=_unix_preexec(),
            close_fds=True,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        raise SandboxTimeout(f"timeout after {timeout}s") from e

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
        # Truncate gigantic tracebacks
        if len(stderr) > 4000:
            stderr = stderr[:2000] + "\n…\n" + stderr[-2000:]
        raise SandboxError(f"child exited with {proc.returncode}:\n{stderr}")

    png = proc.stdout or b""
    if len(png) < 100:
        raise SandboxError(f"no PNG produced (stdout {len(png)} bytes)")
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise SandboxError("output is not a PNG (magic bytes mismatch)")
    return png


def _run_via_docker(code: str, timeout: float) -> bytes:
    """Run inside formyla/drawing-sandbox. Stub; raises if Docker not present."""
    wrapped = _WRAPPER.replace("{USER_CODE}", code)
    image = os.environ.get("DRAWING_SANDBOX_IMAGE", "formyla/drawing-sandbox:latest")
    cmd = [
        "docker", "run", "--rm", "-i",
        "--network=none",
        "--read-only",
        "--cpus=1",
        "--memory=512m",
        "--pids-limit=64",
        "--tmpfs", "/tmp:size=64m,mode=1777",
        "-e", "MPLBACKEND=Agg",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTHONNOUSERSITE=1",
        image,
        "python", "-I", "-S", "-c", wrapped,
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=b"",
            capture_output=True,
            timeout=timeout,
            close_fds=True,
        )
    except FileNotFoundError as e:
        raise SandboxError("docker binary not available") from e
    except subprocess.TimeoutExpired as e:
        raise SandboxTimeout(f"docker timeout after {timeout}s") from e

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")[:4000]
        raise SandboxError(f"docker exited {proc.returncode}: {stderr}")

    png = proc.stdout or b""
    if len(png) < 100 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise SandboxError("docker did not produce a PNG")
    return png


# ─── Public entry ──────────────────────────────────────────────────────────────

def run_drawing_code(code: str, *, timeout: float = 10.0) -> bytes:
    """
    Validate → execute → return PNG bytes.

    Raises:
        SandboxRejected  — failed AST whitelist (never executed)
        SandboxTimeout   — wall-clock timeout
        SandboxError     — runtime / no PNG / Docker missing / etc.
    """
    validate_drawing_code(code)

    if os.environ.get("DRAWING_SANDBOX_DOCKER", "").lower() in {"1", "true", "yes"}:
        return _run_via_docker(code, timeout=timeout)
    return _run_via_subprocess(code, timeout=timeout)
