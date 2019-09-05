SQLitely 1.0
============

SQLitely is an SQLite database tool, written in Python.

You can open SQLite databases and look at their contents:

- search across all tables and columns
- view any database table and export their data, fix database corruption
- change, add or delete data in any table
- execute direct SQL queries

Downloads, help texts, and more screenshots at
http://suurjaak.github.io/SQLitely.

[![Screenshots](https://raw.github.com/suurjaak/SQLitely/gh-pages/img/th_collage.png)](https://raw.github.com/suurjaak/SQLitely/gh-pages/img/collage.png)


Using The Program
-----------------

Searching an opened database supports a simple Google-like
[query syntax](http://suurjaak.github.io/SQLitely/help.html).
You can use keywords to search from specific tables and columns only
(`table:foo`, `column:bar`), or from certain dates only 
(`date:2012`, `date:2010..2013-06`). Search supports 
wildcards, exact phrases, grouping, excluding, and either-or queries.

SQLitely can be minimized to tray, clicking the tray icon opens 
a search popup.

The program itself is stand-alone, can work from any directory, and does not 
need additional installation, Windows installers have been provided for 
convenience. The installed program can be copied to a USB stick and used
elsewhere, same goes for the source code. The command line interface only needs
Python to run.

SQLitely has been tested under Windows 7, Windows Vista, Windows XP and
Ubuntu Linux, and reported to work under OS X and Windows 8. In source code
form, it should run wherever Python and the required Python packages are
installed.

If running from pip installation, run `sqlitely` from the command-line. 
If running from straight source code, launch `sqlitely.sh` where shell 
scripts are supported, or launch `sqlitely.bat` under Windows, or open 
a terminal and run `python -m sqlitely.main` in SQLitely directory.


Installation
------------

Windows: download and launch the latest setup from
https://suurjaak.github.io/SQLitely/downloads.html.

Mac/Linux/other: install Python, wxPython, pip, and run
`pip install sqlitely`

The pip installation will add the `sqlitely` command to path.
For more thorough instructions, see [INSTALL.md](INSTALL.md).


Source Dependencies
-------------------

If running from source code, SQLitely needs Python 2.7,
and the following 3rd-party Python packages:
* wxPython 2.9+ (http://wxpython.org/)
The following are also listed in `requirements.txt` for pip:
* pyparsing (https://pypi.org/project/pyparsing/)
* XlsxWriter (https://pypi.python.org/pypi/XlsxWriter)

If other Python libraries are not available, the program will function 
regardless, only with lesser service - like lacking Excel export or full 
search syntax.

SQLitely can also run under wxPython 2.8.12+, with some layout quirks.
Python 2.6 will need the argparse library. Python 3 is yet unsupported.


Attribution
-----------

SQLitely includes step, Simple Template Engine for Python,
(c) 2012, Daniele Mazzocchio (https://github.com/dotpy/step).

Several icons from:
  Fugue Icons, (c) 2010 Yusuke Kamiyamane,
  http://p.yusukekamiyamane.com/

Includes fonts Carlito Regular and Carlito bold,
https://fedoraproject.org/wiki/Google_Crosextra_Carlito_fonts

Binaries compiled with PyInstaller 2.1, http://www.pyinstaller.org

Installers created with Nullsoft Scriptable Install System 3.0b1,
http://nsis.sourceforge.net/


License
-------

Copyright (c) 2019 by Erki Suurjaak.
Released as free open source software under the MIT License,
see [LICENSE.md](LICENSE.md) for full details.
