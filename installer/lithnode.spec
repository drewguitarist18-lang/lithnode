# PyInstaller build for the installed app: two programs sharing one folder (see lithnode_main.py).
# Claude Pet's code comes from its own project folder next to this one.
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent
PET = ROOT.parent / "Claude Pet"

a = Analysis(
    [str(HERE / "lithnode_main.py")],
    pathex=[str(ROOT), str(PET)],
    datas=[(str(ROOT / "static"), "static"), (str(PET / "office.html"), ".")],
    hiddenimports=["hq", "flows", "agents", "claude_code", "office_feed",
                   "hook", "pet", "office", "shared", "tkinter", "tkinter.filedialog", "winsound"],
    excludes=["test", "unittest", "pydoc_data"],
)
pyz = PYZ(a.pure)
icon = str(HERE / "lithnode.ico")
app = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lithnode-server", console=False, icon=icon)   # the engine; Lithnode.exe is the Electron window
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lithnode-cli", console=True, icon=icon)
coll = COLLECT(app, cli, a.binaries, a.datas, name="Lithnode")
