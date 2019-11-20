# -*- mode: python -*-
"""
Pyinstaller spec file for SQLitely, produces a 32-bit or 64-bit executable,
depending on current environment.

@created   03.04.2012
@modified  20.11.2019
"""
import os
import sys

DEBUG = False
NAME = "sqlitely"
BUILDPATH = os.path.dirname(os.path.abspath(SPEC))
APPPATH   = os.path.join(os.path.dirname(BUILDPATH), NAME)
ROOTPATH  = os.path.dirname(APPPATH)

os.chdir("..")
a = Analysis(
    [os.path.join(ROOTPATH, "launch.py")],
    excludes=["FixTk", "numpy", "tcl", "tk", "_tkinter", "tkinter", "Tkinter"],
)
a.datas += [("conf.py", "sqlitely/conf.py", "DATA"), # For configuration docstrings
            ("bin/sqlite3_analyzer.exe", "sqlitely/bin/sqlite3_analyzer.exe", "DATA"),
            ("bin/sqlite3_analyzer_linux", "sqlitely/bin/sqlite3_analyzer_linux", "DATA"),
            ("bin/sqlite3_analyzer_osx", "sqlitely/bin/sqlite3_analyzer_osx", "DATA"),
            ("res/Carlito.ttf", "sqlitely/media/Carlito.ttf", "DATA"),
            ("res/CarlitoBold.ttf", "sqlitely/media/CarlitoBold.ttf", "DATA"), ]
a.binaries = a.binaries - TOC([
    ('tcl85.dll', None, None),
    ('tk85.dll',  None, None),
    ('_tkinter',  None, None)
])
pyz = PYZ(a.pure)


sys.path.append(APPPATH)
from sqlitely import conf

is_64bit = "PROCESSOR_ARCHITEW6432" in os.environ
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
