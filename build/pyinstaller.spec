# -*- mode: python -*-
"""
Pyinstaller spec file for SQLitely, produces a 32-bit or 64-bit executable,
depending on current environment.

Pyinstaller-provided names and variables: Analysis, EXE, PYZ, SPEC, TOC.

@created   23.08.2019
@modified  17.06.2020
"""
import os
import platform
import struct
import sys

DEBUG = False
NAME = "sqlitely"
BUILDPATH = os.path.dirname(os.path.abspath(SPEC))
APPPATH   = os.path.join(os.path.dirname(BUILDPATH), NAME)
ROOTPATH  = os.path.dirname(APPPATH)

ANALYZER = "sqlite3_analyzer.exe"   if "nt"  == os.name else \
           "sqlite3_analyzer_osx"   if "os2" == os.name else \
           "sqlite3_analyzer_linux" if "64" not in platform.architecture()[0] else \
           "sqlite3_analyzer_linux_x64"

os.chdir("..")
a = Analysis(
    [os.path.join(ROOTPATH, "launch.py")],
    excludes=["FixTk", "numpy", "tcl", "tk", "_tkinter", "tkinter", "Tkinter"],
)
# conf.py for configuration docstrings in advanced options
a.datas += [("conf.py",             "%s/conf.py" % NAME,               "DATA"),
            ("bin/" + ANALYZER,     "%s/bin/%s" % (NAME, ANALYZER),    "DATA"),
            ("res/Carlito.ttf",     "%s/media/Carlito.ttf" % NAME,     "DATA"),
            ("res/CarlitoBold.ttf", "%s/media/CarlitoBold.ttf" % NAME, "DATA"), ]
a.binaries = a.binaries - TOC([
    ('tcl85.dll', None, None),
    ('tk85.dll',  None, None),
    ('_tkinter',  None, None)
])
pyz = PYZ(a.pure)


sys.path.append(APPPATH)
from sqlitely import conf

is_64bit = (struct.calcsize("P") * 8 == 64)
ext = ".exe" if "nt" == os.name else ""
app_file = "%s_%s%s%s" % (NAME, conf.Version, "_x64" if is_64bit else "", ext)

exe = EXE(
    pyz,
    a.scripts + ([("v", "", "OPTION")] if DEBUG else []),
    a.binaries,
    a.datas,
    name=app_file,

    debug=DEBUG, # Verbose or non-verbose debug statements printed
    exclude_binaries=False, # Binaries not left out of PKG
    strip=False,   # EXE and all shared libraries run through cygwin's strip, tends to render Win32 DLLs unusable
    upx=True,      # Using Ultimate Packer for eXecutables
    console=DEBUG, # Use the Windows subsystem executable instead of the console one
    icon=os.path.join(BUILDPATH, "sqlitely.ico"),
)
