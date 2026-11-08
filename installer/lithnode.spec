# PyInstaller build for the installed app: two programs sharing one folder (see lithnode_main.py).
# Windows also bundles Claude Pet (a Windows desktop pet), from its own project folder next to this one.
# Mac and Linux get the engine alone; their window picks folders itself, so no tkinter either.
import os
import sys
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent
PET = Path(os.environ.get("LITHNODE_PET_DIR") or ROOT.parent / "Claude Pet")   # CI checks claude-pet out elsewhere
WINDOWS = sys.platform == "win32"

a = Analysis(
    [str(HERE / "lithnode_main.py")],
    pathex=[str(ROOT), str(PET)] if WINDOWS else [str(ROOT)],
    datas=[(str(ROOT / "static"), "static")],
    hiddenimports=["hq", "flows", "agents", "claude_code", "engines", "office_feed", "shot", "updates", "version", "settings", "apikeys", "mcp_server"]
                  + (["hook", "pet", "shared", "tkinter", "tkinter.filedialog", "winsound"] if WINDOWS else []),
    excludes=["test", "unittest", "pydoc_data"] + ([] if WINDOWS else ["tkinter"]),
)
pyz = PYZ(a.pure)
icon = str(HERE / "lithnode.ico") if WINDOWS else None


def version_info(name):
    """Windows file details (Properties > Details): product Lithnode, version from version.py. Code signing wants them."""
    if not WINDOWS:
        return None
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    ver = {}
    exec((ROOT / "version.py").read_text(encoding="utf-8"), ver)
    nums = tuple((list(map(int, ver["VERSION"].split("."))) + [0, 0, 0, 0])[:4])
    strings = [StringStruct(k, v) for k, v in (("CompanyName", "Lithnode"), ("FileDescription", "Lithnode"),
               ("FileVersion", ver["VERSION"]), ("InternalName", name), ("LegalCopyright", "MIT License"),
               ("OriginalFilename", name + ".exe"), ("ProductName", "Lithnode"), ("ProductVersion", ver["VERSION"]))]
    return VSVersionInfo(ffi=FixedFileInfo(filevers=nums, prodvers=nums),
                         kids=[StringFileInfo([StringTable("040904B0", strings)]), VarFileInfo([VarStruct("Translation", [1033, 1200])])])


app = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lithnode-server", console=False, icon=icon,   # the engine; Lithnode.exe is the Electron window
          version=version_info("lithnode-server"))
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lithnode-cli", console=True, icon=icon, version=version_info("lithnode-cli"))
coll = COLLECT(app, cli, a.binaries, a.datas, name="Lithnode")
