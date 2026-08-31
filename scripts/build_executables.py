#!/usr/bin/env python
"""Build the ``swarm`` CLI as distributable artifacts.

    python scripts/build_executables.py            # all targets available here
    python scripts/build_executables.py --pyz      # just the cross-platform .pyz
    python scripts/build_executables.py --onefile  # single-file PyInstaller build

Outputs land in ``dist/``:

* ``dist/swarm``  or  ``dist/swarm.exe``  - native PyInstaller binary (this OS only;
  PyInstaller does not cross-compile - run on Windows for .exe, Linux for ELF).
* ``dist/swarm.pyz``                       - zipapp; runs anywhere with Python 3.11
  and ``swarm_core`` + ``swarm_tg`` importable.

CI (.github/workflows/build-executables.yml) runs this on windows-latest and
ubuntu-latest and uploads both.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SPEC = ROOT / "packaging" / "swarm.spec"


def _run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, **kw)


def build_pyz() -> Path:
    DIST.mkdir(exist_ok=True)
    out = DIST / "swarm.pyz"
    staging = DIST / "_pyz_build"
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    # zipapp bundles pure-Python source; heavy wheels (solders, redis) stay a
    # runtime requirement. Copy the two first-party packages in.
    import shutil

    for pkg in ("swarm-core", "swarm-tg"):
        src = ROOT / "packages" / pkg / "src"
        for child in src.iterdir():
            dst = staging / child.name
            if child.is_dir():
                shutil.copytree(child, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(child, dst)
    (staging / "__main__.py").write_text(
        "from swarm_core.cli import main\nraise SystemExit(main())\n", encoding="utf-8"
    )
    zipapp.create_archive(staging, out, interpreter="/usr/bin/env python3", compressed=True)
    shutil.rmtree(staging)
    print(f"  -> {out}  ({out.stat().st_size // 1024} KiB)")
    return out


def build_binary(onefile: bool = True) -> Path:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller not installed: pip install pyinstaller")
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", str(DIST), "--workpath", str(DIST / "_work"),
            "--specpath", str(ROOT / "packaging")]
    if onefile:
        args.append("--onefile")
    args.append(str(SPEC))
    _run(args, cwd=ROOT)
    name = "swarm.exe" if sys.platform.startswith("win") else "swarm"
    out = DIST / name
    print(f"  -> {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pyz", action="store_true", help="build only the .pyz")
    ap.add_argument("--binary", action="store_true", help="build only the native binary")
    ap.add_argument("--onefile", action="store_true", default=True)
    a = ap.parse_args()

    made = []
    if a.pyz or not a.binary:
        made.append(build_pyz())
    if a.binary or not a.pyz:
        try:
            made.append(build_binary(onefile=a.onefile))
        except SystemExit as e:
            print(f"skipped native binary: {e}")
    print("\nbuilt:")
    for m in made:
        print(f"  {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
