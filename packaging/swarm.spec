# PyInstaller spec for the `swarm` CLI. Built via scripts/build_executables.py.
# PyInstaller does not cross-compile: run this on Windows for swarm.exe and on
# Linux for the ELF binary.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = []
for pkg in ("swarm_core", "swarm_tg", "solders", "redis", "aiohttp"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

datas = []
for pkg in ("swarm_core", "swarm_tg"):
    try:
        datas += collect_data_files(pkg, includes=["**/*.json", "**/*.md", "**/*.yaml"])
    except Exception:
        pass

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="swarm",
    console=True,
    upx=False,
    strip=False,
)
