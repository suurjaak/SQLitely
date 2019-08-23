SQLiteMate 1.0
==============

TODO



Skyperious is a Skype database viewer and merger, written in Python.

You can open Skype SQLite databases and look at their contents:

- search across all messages and contacts
- browse chat history and export as HTML or spreadsheet, see chat statistics
- import contacts from a CSV file to your Skype contacts
- view any database table and export their data, fix database corruption
- change, add or delete data in any table
- execute direct SQL queries
and
- synchronize messages in two Skype databases: keep chat history up-to-date on
  different computers, or restore missing messages from older files into the
  current one

Additionally, it doubles as a useful database browser for any SQLite file.
Also, a command line interface is available with key functions like
exporting, searching, and merging. 
The graphical version includes a Python console window.

Making a backup of the database file is recommended before making any changes.
There is an easy "Save as" button for that on the database index page.

Downloads, help texts, and more screenshots at
http://suurjaak.github.io/Skyperious.


Using The Program
-----------------

Skyperious can look through user directories and detect Skype databases
automatically, or you can select specific files or folders.
Once added to the database list, a file can be opened for browsing, searching 
and exporting, or compared with another database for merging.

Searching an opened database supports a simple Google-like query syntax. 
You can use keywords to search among specific authors or chats only
(from:john chat:links), or from certain dates only (date:2012, date:2010..2013).
Search supports wildcards, exact phrases, grouping, excluding,
and either-or queries.

HTML export can download shared photos and embed them in the resulting HTML.
This can be disabled in File -> Advanced Options -> SharedImageAutoDownload.
As shared photos are kept on the web, Skyperious needs to ask for Skype account
password on HTML export. The password is only used for retrieving the images,
and is not retained.
Image download is also supported in the command-line interface.

In database comparison, you can scan one database for messages not found in
the other, and merge all detected messages to the other database. Or you can
browse and copy specific chats and contacts.

Skyperious offers a number of options from the command line:
  export FILE [-t format]    export Skype databases as HTML, text or spreadsheet
  search "query" FILE        search Skype databases for messages or data
  merge FILE1 FILE2          merge two or more Skype databases into a new database
  diff FILE1 FILE2           compare chat history in two Skype databases
  gui [FILE]                 launch Skyperious graphical program (default option)


Skyperious can be minimized to tray, clicking the tray icon opens 
a search popup.

Skyperious can usually read from the same file Skype is currently using, although
this can cause temporary program errors. Writing to such a file is ill-advised.

The program itself is stand-alone, can work from any directory, and does not 
need additional installation, Windows installers have been provided for 
convenience. The installed program can be copied to a USB stick and used
elsewhere.

Skyperious has been tested under Windows 7, Windows Vista, Windows XP, and 
reported to work under Windows 8.



Attribution
-----------

SQLiteMate has been built using the following open-source software:
- Python 2.7.10 (http://www.python.org)
- wxPython 3.0.2 (http://www.wxpython.org)
- pyparsing 2.0.3 (http://pyparsing.wikispaces.com/)
- XlsxWriter 0.7.3 (https://github.com/jmcnamara/XlsxWriter)

Several icons from:
  Fugue Icons, (c) 2010 Yusuke Kamiyamane,
  http://p.yusukekamiyamane.com/

Binaries compiled with PyInstaller 2.1, http://www.pyinstaller.org

Installer created with Nullsoft Scriptable Install System 3.0b1,
http://nsis.sourceforge.net/


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
