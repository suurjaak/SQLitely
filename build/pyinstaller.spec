# -*- mode: python -*-
"""
Pyinstaller spec file for SQLitely, produces a 32-bit or 64-bit executable,
depending on Python environment.

Pyinstaller-provided names and variables: Analysis, EXE, PYZ, SPEC, TOC.

@created   23.08.2019
@modified  07.07.2024
"""
import atexit
import os
import struct
import sys

NAME        = "sqlitely"
DO_DEBUGVER = False
DO_64BIT    = (struct.calcsize("P") * 8 == 64)

BUILDPATH = os.path.dirname(os.path.abspath(SPEC))
ROOTPATH  = os.path.dirname(BUILDPATH)
APPPATH   = os.path.join(ROOTPATH, "src", NAME)

sys.path.insert(0, os.path.join(ROOTPATH, "src"))
from sqlitely import conf


def cleanup():
    try: os.unlink(entrypoint)
    except Exception: pass


entrypoint = os.path.join(ROOTPATH, "launch.py")
with open(entrypoint, "w") as f:
    f.write("from %s import main; main.run()" % NAME)
atexit.register(cleanup)

a = Analysis(
    [entrypoint],
    excludes=["FixTk", "numpy", "tcl", "tk", "_tkinter", "tkinter", "Tkinter"],
)
SQLITE_ANALYZER = "sqlite3_analyzer.exe"   if "nt"  == os.name else \
                  "sqlite3_analyzer_osx"   if "os2" == os.name else \
                  "sqlite3_analyzer_linux" if not DO_64BIT else \
                  "sqlite3_analyzer_linux_x64"
a.datas += [("conf.py",                    os.path.join(APPPATH, "conf.py"), "DATA"), # For configuration docstrings
            ("bin/" + SQLITE_ANALYZER,     os.path.join(APPPATH, "bin",   SQLITE_ANALYZER),    "DATA"),
            ("res/Carlito.ttf",            os.path.join(APPPATH, "media", "Carlito.ttf"),      "DATA"),
            ("res/CarlitoBold.ttf",        os.path.join(APPPATH, "media", "CarlitoBold.ttf"),  "DATA"),
            ("res/OpenSans.ttf",           os.path.join(APPPATH, "media", "OpenSans.ttf"),     "DATA"),
            ("res/OpenSansBold.ttf",       os.path.join(APPPATH, "media", "OpenSansBold.ttf"), "DATA"),
            ("res/3rd-party licenses.txt", "3rd-party licenses.txt", "DATA"), ]
a.binaries = a.binaries - TOC([
    ("tcl85.dll", None, None), ("tk85.dll",  None, None), ("_tkinter",  None, None)
])
pyz = PYZ(a.pure)

is_64bit = (struct.calcsize("P") * 8 == 64)
ext = ".exe" if "nt" == os.name else ""
app_file = "%s_%s%s%s" % (NAME, conf.Version, "" if is_64bit else "_x86", ext)

exe = EXE(
    pyz,
    a.scripts + ([("v", "", "OPTION")] if DO_DEBUGVER else []),
    a.binaries,
    a.datas,
    name=os.path.join("build", app_file),

    debug=DO_DEBUGVER, # Verbose or non-verbose debug statements printed
    exclude_binaries=False, # Binaries not left out of PKG
    strip=False, # EXE and all shared libraries run through cygwin's strip, tends to render Win32 DLLs unusable
    upx=True, # Using Ultimate Packer for eXecutables
    console=DO_DEBUGVER, # Use the Windows subsystem executable instead of the console one
    icon=os.path.join(ROOTPATH, "res", "Icon.ico"),
)

try: os.remove(entrypoint)
except Exception: pass
