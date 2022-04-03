# -*- coding: utf-8 -*-
"""
Setup.py for SQLitely.

------------------------------------------------------------------------------
This file is part of SQLitely - an SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    27.03.2022
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


def readfile(path):
    """Returns contents of path, relative to current file."""
    root = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(root, path)) as f: s = f.read().decode("utf-8")
    md_link_rgx = r"\[(.+)\]\((.+)+\)"
    def repl(m):
        m2 = re.search(md_link_rgx, m.group(1))
        if m2: return "%s: %s" % (m2.group(1), m2.group(2)) # Image link
        elif m.group(1) == m.group(2): return m.group(1)    # Local link
        else: return "%s (%s)" % (m.group(1), m.group(2)) # Web link
    s = re.sub(md_link_rgx, repl, s)
    return s


setuptools.setup(
    name=PACKAGE,
    version=conf.Version,
    description="SQLite database tool",
    url="https://github.com/suurjaak/SQLitely",

    author="Erki Suurjaak",
    author_email="erki@lap.ee",
    license="MIT",
    platforms=["any"],
    keywords="sqlite database",

    install_requires=["appdirs", "openpyxl", "Pillow", "pyparsing", "pytz", "six",
                      "wxPython>=4.0", "xlrd", "XlsxWriter"],
    extras_require={
        ':python_version < "3"': ["antlr4-python2-runtime==4.9"],
        ':python_version > "3"': ["antlr4-python3-runtime==4.9"],
    },
    entry_points={"gui_scripts": ["{0} = {0}.main:run".format(PACKAGE)]},

    package_dir={"": "src"},
    packages=[PACKAGE],
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
        "Programming Language :: Python :: 3",
    ],

    long_description_content_type="text/markdown",
    long_description=readfile("README.md"),
)
