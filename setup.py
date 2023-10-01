# -*- coding: utf-8 -*-
"""
Setup.py for SQLitely.

------------------------------------------------------------------------------
This file is part of SQLitely - an SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    01.10.2023
------------------------------------------------------------------------------
"""
import os
import re
import sys

import setuptools

ROOTPATH  = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOTPATH, "src"))

from sqlitely import conf


PACKAGE = conf.Title.lower()
REPOSITORY = "https://github.com/suurjaak/SQLitely"


def readfile(path):
    """Returns contents of path, relative to current file."""
    root = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(root, path)) as f: return f.read()
    except UnicodeError:
        with open(os.path.join(root, path), "rb") as f:
            return f.read().decode(errors="backslashreplace")

def get_description():
    """Returns package description from README."""
    LINK_RGX = r"\[([^\]]+)\]\(([^\)]+)\)"  # 1: content in [], 2: content in ()
    KEEP = ("ftp://", "http://", "https://", "www.")
    # Unwrap page anchor links like [Page link](#page-link) as "Page link",
    # make package file links like [LICENSE.md](LICENSE.md) point to repository
    repl = lambda m: m.group(1) if m.group(2).startswith("#") else \
                     m.group(0) if any(map(m.group(2).startswith, KEEP)) else \
                     "[%s](%s/blob/master/%s)" % (m.group(1), REPOSITORY, m.group(2))
    return re.sub(LINK_RGX, repl, readfile("README.md"))


setuptools.setup(
    name                 = PACKAGE,
    version              = conf.Version,
    description          = "SQLite database tool",
    url                  = REPOSITORY,

    author               = "Erki Suurjaak",
    author_email         = "erki@lap.ee",
    license              = "MIT",
    platforms            = ["any"],
    keywords             = "sqlite database",

    install_requires     = ["appdirs", "chardet", "openpyxl", "Pillow", "pyparsing", "pytz",
                            "six", "step-template>=0.0.4", "wxPython>=4.0", "xlrd", "XlsxWriter"],
    extras_require       = {
        ':python_version < "3"': ["antlr4-python2-runtime==4.9"],
        ':python_version > "3"': ["antlr4-python3-runtime==4.9"],
    },
    entry_points         = {"gui_scripts": ["{0} = {0}.main:run".format(PACKAGE)]},

    package_dir          = {"": "src"},
    packages             = [PACKAGE],
    include_package_data = True, # Use MANIFEST.in for data files
    classifiers          = [
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
        "Programming Language :: Python :: 3",
    ],

    long_description_content_type = "text/markdown",
    long_description = get_description(),
)
