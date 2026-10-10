# PyInstaller build for the installed app: two programs sharing one folder (see lithnode_main.py).
# Windows also bundles Claude Pet (a Windows desktop pet), from its own project folder next to this one.
# Mac and Linux get the engine alone; their window picks folders itself, so no tkinter either.
import sys
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent
PET = ROOT.parent / "Claude Pet"
WINDOWS = sys.platform == "win32"

a = Analysis(
    [str(HERE / "lithnode_main.py")],
    pathex=[str(ROOT), str(PET)] if WINDOWS else [str(ROOT)],
    datas=[(str(ROOT / "static"), "static")] + ([(str(PET / "office.html"), ".")] if WINDOWS else []),
    hiddenimports=["hq", "flows", "agents", "claude_code", "engines", "office_feed", "shot"]
                  + (["hook", "pet", "office", "shared", "tkinter", "tkinter.filedialog", "winsound"] if WINDOWS else []),
    excludes=["test", "unittest", "pydoc_data"] + ([] if WINDOWS else ["tkinter"]),
)
pyz = PYZ(a.pure)
icon = str(HERE / "lithnode.ico") if WINDOWS else None
app = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lithnode-server", console=False, icon=icon)   # the engine; Lithnode.exe is the Electron window
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lithnode-cli", console=True, icon=icon)
coll = COLLECT(app, cli, a.binaries, a.datas, name="Lithnode")
