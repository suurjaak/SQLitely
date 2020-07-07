# -*- coding: utf-8 -*-
"""
Setup.py for SQLitely.

------------------------------------------------------------------------------
This file is part of SQLitely - an SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    05.07.2020
------------------------------------------------------------------------------
"""
import atexit
import os
import stat
import sys
import setuptools
from setuptools.command.install import install

from sqlitely import conf


class CustomInstall(install):
    """Sets executable bits on sqlite_analyzer binaries after installation."""

    def __init__(self, *args, **kwargs):
        install.__init__(self, *args, **kwargs)
        if "nt" != os.name: atexit.register(self._post_install)

    def _post_install(self):

        def find_module_path(name):
            paths = list(sys.path)
            if getattr(self, "install_purelib", None):
                paths.insert(0, self.install_purelib)
            for p in paths:
                try:
                    if os.path.isdir(p) and name in os.listdir(p):
                        return os.path.join(p, name)
                except Exception: pass

        install_path = find_module_path(conf.Title.lower())
        bin_path = os.path.join(install_path, "bin") if install_path else None
        mask = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        for f in os.listdir(bin_path) if bin_path else ():
            p = os.path.join(bin_path, f)
            try: os.chmod(p, mask)
            except Exception: pass


def readfile(path):
    """Returns contents of path, relative to current file."""
    root = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(root, path)) as f: return f.read().decode("utf-8")


setuptools.setup(
    cmdclass={"install": CustomInstall},
    name=conf.Title,
    version=conf.Version,
    description="SQLite database tool",
    url="https://github.com/suurjaak/SQLitely",

    author="Erki Suurjaak",
    author_email="erki@lap.ee",
    license="MIT",
    platforms=["any"],
    keywords="sqlite database",

    install_requires=["antlr4-python2-runtime==4.8", "openpyxl<=3.0.0", "Pillow<=6.2.2", "pyparsing", "pytz", "wxPython>=4.0", "xlrd", "XlsxWriter"],
    entry_points={"gui_scripts": ["sqlitely = sqlitely.main:run"]},

    packages=setuptools.find_packages(),
    include_package_data=True, # Use MANIFEST.in for data files
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: Unix",
        "Operating System :: MacOS",
        "Topic :: Database",
        "Topic :: Utilities",
        "Topic :: Desktop Environment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
    ],

    long_description_content_type="text/markdown",
    long_description=readfile("README.md"),
)
