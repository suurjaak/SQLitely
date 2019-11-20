SQLitely 1.0
============

SQLitely is an SQLite database tool, written in Python.

It can:

- detect and manage SQLite databases in bulk
- create new databases
- create and modify tables, indexes, triggers and views
- free-form search over all database data and metadata
- view and export data and metadata in various formats
- view database table and index size statistics
- copy tables from one database to another
- modify table data
- execute direct SQL queries
- manage database PRAGMA directives
- fix database corruption

Downloads, help texts, and more screenshots at
http://suurjaak.github.io/SQLitely.

[![Screenshots](https://raw.github.com/suurjaak/SQLitely/gh-pages/img/th_collage.png)](https://raw.github.com/suurjaak/SQLitely/gh-pages/img/collage.png)


Using The Program
-----------------

SQLitely offers a convenient way for complex ALTER TABLE operations.
Columns and constraints can be changed, reordered, added, dropped;
the program automatically performs the multiple steps required for SQLite table
modifications while retaining existing data (creating a temporary table,
copying data, dropping old table, and renaming temporary table as old).
Additionally, when renaming tables or columns, all related tables, indexes,
triggers and views are altered automatically.

SQLitely can search over all columns of all tables with a simple
[query syntax](http://suurjaak.github.io/SQLitely/help.html).
Keywords can search from specific tables and columns only
(`table:foo`, `column:bar`), or from certain dates only 
(`date:2012`, `date:2010..2013-06`). Search supports 
wildcards, exact phrases, grouping, excluding, and either-or queries.

SQLitely can show disk space usage for each table and index,
in bytes and overall percentage. (Depending on the size of the database,
this analysis can take a while.)

Fixing database corruption: SQLitely will copy as much data as possible
over into a new database.


SQLitely has been tested under Windows 7, Windows Vista, Windows XP and
Ubuntu Linux. In source code form, it should run wherever Python and the
required Python packages are installed.

If running from pip installation, run `sqlitely` from the command-line. 
If running straight from source code, launch `sqlitely.sh` where shell 
scripts are supported, or `sqlitely.bat` under Windows, or open 
a terminal and run `python -m sqlitely.main` in SQLitely directory.


Installation
------------

Windows: download and launch the latest setup from
https://suurjaak.github.io/SQLitely/downloads.html.

From source code: install Python, pip, and run `pip install sqlitely`. 
The pip installation will add the `sqlitely` command to path.

Windows installers have been provided for convenience. The program itself 
is stand-alone, can work from any directory, and does not need additional
installation. The installed program can be copied to a USB stick and used
elsewhere, same goes for the source code.


Source Dependencies
-------------------

If running from source code, SQLitely needs Python 2.7,
and the following 3rd-party Python packages:
* antlr4-python2-runtime (https://pypi.org/project/antlr4-python2-runtime)
* openpyxl (https://pypi.org/project/openpyxl)
* pyparsing (https://pypi.org/project/pyparsing)
* wxPython 4.0+ (https://wxpython.org/)
* xlrd (https://pypi.org/project/xlrd)
* XlsxWriter (https://pypi.org/project/XlsxWriter)

If openpyxl or pyparsing or xlrd or XlsxWriter are not available,
the program will function regardless, only with lesser service - 
lacking Excel import-export or full search syntax.

Python 2.6 will need the argparse library. Python 3 is yet unsupported.


Attribution
-----------

Includes sqlite_analyzer, a command-line utility for table space analysis,
(c) 2000, D. Richard Hipp, https://www.sqlite.org.

Includes a modified version of step, Simple Template Engine for Python,
(c) 2012, Daniele Mazzocchio, https://github.com/dotpy/step.

Includes a modified version of SQLite.g4 from antlr4-grammars,
(c) 2014, Bart Kiers,
https://github.com/antlr/grammars-v4/blob/master/sqlite/SQLite.g4.

SQL lexer and parser generated with ANTLR v4.7.2,
(c) 2012 The ANTLR Project, https://github.com/antlr/antlr4.

Includes several icons from Fugue Icons,
(c) 2010 Yusuke Kamiyamane, https://p.yusukekamiyamane.com.

Includes fonts Carlito Regular and Carlito bold,
https://fedoraproject.org/wiki/Google_Crosextra_Carlito_fonts.

Binaries compiled with PyInstaller, https://www.pyinstaller.org.

Installers created with Nullsoft Scriptable Install System,
https://nsis.sourceforge.net/.


License
-------

(The MIT License)

Copyright (C) 2019 by Erki Suurjaak

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

The software is provided "as is", without warranty of any kind, express or
implied, including but not limited to the warranties of merchantability,
fitness for a particular purpose and noninfringement. In no event shall the
authors or copyright holders be liable for any claim, damages or other
liability, whether in an action of contract, tort or otherwise, arising from,
out of or in connection with the software or the use or other dealings in
the software.


For licenses of included libraries, see "3rd-party licenses.txt".
