# -*- coding: utf-8 -*-
"""
Setup.py for SQLitely.

------------------------------------------------------------------------------
This file is part of SQLitely - an SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    19.12.2019
------------------------------------------------------------------------------
"""
import setuptools

from sqlitely import conf

setuptools.setup(
    name=conf.Title,
    version=conf.Version,
    description="SQLite database tool",
    url="https://github.com/suurjaak/SQLitely",

    author="Erki Suurjaak",
    author_email="erki@lap.ee",
    license="MIT",
    platforms=["any"],
    keywords="sqlite database",

    install_requires=["antlr4-python2-runtime", "openpyxl", "pyparsing", "wxPython", "xlrd", "XlsxWriter"],
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

    long_description="SQLitely is an SQLite database tool, written in Python.",
)
