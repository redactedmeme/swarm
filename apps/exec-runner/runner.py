"""The jail. Runs an untrusted Python snippet with hard resource limits and a
stripped environment, in a process group we can reap.

Isolation comes from three places, defence-in-depth:

* the container       — ``network_mode: none``, ``read_only`` rootfs,
  ``cap_drop: ALL``, ``no-new-privileges``, non-root user, ``pids_limit``.
  There are NO secrets in this container's environment.
* ``nsjail`` if present — mount namespace, ``/proc`` remount, extra rlimits.
* this module          — ``setrlimit`` for CPU / address space / file size /
  nproc, ``python3 -I -B -S`` (isolated: no site, no ``PYTHff*`` env, no
  user site-packages), a wall-clock kill of the whole process group, and
  output truncation.

Nothing here trusts the caller's ``code`` in any way — it is only ever passed as
a single argv element to a fresh interpreter, never shell-interpreted.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys

# Hard ceilings. The request may lower the timeout but never raise it.
MAX_WALL_SECONDS = 30
MAX_CPU_SECONDS = 10
MAX_ADDRESS_SPACE = 256 * 1024 * 1024   # 256 MiB
MAX_FILE_BYTES = 1 * 1024 * 1024        # 1 MiB of scratch writes
MAX_PROCS = 64
MAX_OUTPUT = 16 * 1024                  # per stream, bytes

_NSJAIL = shutil.which("nsjail")


def _preexec() -> None:  # pragma: no cover - runs in the child only
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS + 1))
    resource.setrlimit(resource.RLIMIT_AS, (MAX_ADDRESS_SPACE, MAX_ADDRESS_SPACE))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCS, MAX_PROCS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setsid()  # own process group -> we can killpg the whole subtree


def _argv(code: str) -> list[str]:
    py = ["python3", "-I", "-B", "-S", "-c", code]
    if _NSJAIL:
        return [
            _NSJAIL, "--quiet", "--disable_proc", "--iface_no_lo",
            "--rlimit_as", str(MAX_ADDRESS_SPACE // (1024 * 1024)),
            "--rlimit_cpu", str(MAX_CPU_SECONDS),
            "--rlimit_fsize", str(MAX_FILE_BYTES // (1024 * 1024)),
            "--time_limit", str(MAX_WALL_SECONDS),
            "--", *py,
        ]
    return py


async def run_code(code: str, timeout: int) -> dict:
    """Execute ``code``. Returns a JSON-able dict; never raises for anything the
    sandboxed process does."""
    code = (code or "").strip()
    if not code:
        return {"status": "error", "error": "no code provided"}
    if len(code) > 200_000:
        return {"status": "error", "error": "code too large"}

    wall = max(1, min(int(timeout or MAX_WALL_SECONDS), MAX_WALL_SECONDS))
    env = {"PATH": "/usr/bin:/usr/local/bin", "LC_ALL": "C.UTF-8", "HOME": "/tmp"}

    try:
        proc = await asyncio.create_subprocess_exec(
            *_argv(code),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd="/tmp",
            preexec_fn=_preexec if os.name == "posix" else None,
            start_new_session=True,
        )
    except Exception as exc:  # pragma: no cover
        return {"status": "error", "error": f"spawn failed: {exc}"}

    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=wall)
    except asyncio.TimeoutError:
        timed_out = True
        _killpg(proc)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=2)
        except Exception:
            out, err = b"", b""

    stdout = out.decode("utf-8", "replace")[:MAX_OUTPUT]
    stderr = err.decode("utf-8", "replace")[:MAX_OUTPUT]
    return {
        "status": "timeout" if timed_out else "ok",
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "jail": "nsjail" if _NSJAIL else "rlimit",
    }


def _killpg(proc) -> None:  # pragma: no cover - timing dependent
    try:
        os.killpg(os.getpgid(proc.pid), 9)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":  # tiny CLI for local sanity checks
    print(asyncio.run(run_code(sys.stdin.read(), MAX_WALL_SECONDS)))
