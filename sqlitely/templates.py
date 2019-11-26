# -*- coding: utf-8 -*-
"""
HTML and TXT templates for exports and statistics.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    26.11.2019
------------------------------------------------------------------------------
"""
import datetime
import re

from . import conf

# Modules imported inside templates:
#import itertools, os, pyparsing, sys, wx
#from sqlitely import conf, grammar, images, searchparser, templates
#from sqlitely.lib import util

"""Regex for matching unprintable characters (\x00 etc)."""
SAFEBYTE_RGX = re.compile(r"[\x00-\x1f\x7f-\xa0]")

"""Replacer callback for unprintable characters (\x00 etc)."""
SAFEBYTE_REPL = lambda m: m.group(0).encode("unicode-escape")


def export_comment():
    """Returns export comment like "Exported with SQLitely on [DATETIME]"."""
    dt = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    return "Exported with %s on %s." % (conf.Title, dt)



"""
HTML data export template.

@param   db_filename  database path or temporary name
@param   title        export title
@param   columns      [name, ]
@param   data_buffer  iterable yielding rows data in text chunks
@param   row_count    number of rows
@param   sql          SQL query giving export data, if any
@param   create_sql   CREATE SQL statement for export object, if any
@param   category     export object category ("table" etc), if any
"""
DATA_HTML = """<%
from sqlitely import conf, grammar, images, templates
from sqlitely.lib import util
%><!DOCTYPE HTML><html lang="en">
<head>
  <meta http-equiv='Content-Type' content='text/html;charset=utf-8' />
  <meta name="Author" content="{{ conf.Title }}">
  <title>{{ title }}</title>
  <link rel="shortcut icon" type="image/png" href="data:image/ico;base64,{{! images.Icon16x16_8bit.data }}"/>
  <style>
    * { font-family: Tahoma; font-size: 11px; }
    body {
      background: #8CBEFF;
      margin: 0;
    }
    #title { font-size: 1.1em; font-weight: bold; color: #3399FF; }
    table#header_table {
      width: 100%;
    }
    #content_wrapper {
      max-width: calc(100vw - 60px);
      overflow-x: auto;
    }
    table#body_table {
      margin-left: auto;
      margin-right: auto;
      border-spacing: 0px 10px;
      padding: 0 10px;
    }
    table#body_table > tbody > tr > td {
      background: white;
      min-width: 800px;
      font-family: Tahoma;
      font-size: 11px;
      border-radius: 10px;
      padding: 10px;
    }
    table#content_table {
      empty-cells: show;
      border-spacing: 2px;
      width: 100%;
    }
    table#content_table td {
      line-height: 1.5em;
      padding: 5px;
      border: 1px solid #C0C0C0;
    }
    a, a.visited { color: #3399FF; text-decoration: none; }
    a:hover, a.visited:hover { text-decoration: underline; }
    #footer {
      text-align: center;
      padding-bottom: 10px;
      color: #666;
    }
    #search { text-align: right; }
    td { text-align: left; vertical-align: top; }
    td.index, th.index { color: gray; width: 10px; }
    td.index { color: gray; text-align: right; }
    th { padding-left: 5px; padding-right: 5px; text-align: center; white-space: nowrap; }
    span#sql { display: inline; font-family: monospace; overflow: visible; white-space: pre-wrap; }
    span#sql.clip { display: inline-block; font-family: inherit; height: 1em; overflow: hidden; }
    a#toggle:hover { cursor: pointer; text-decoration: none; }
    span#sql + a#toggle { padding-left: 3px; }
    span#sql.clip + a#toggle { background: white; position: relative; left: -8px; }
    a.sort { display: block; }
    a.sort:hover { cursor: pointer; text-decoration: none; }
    a.sort::after      { content: ""; display: inline-block; min-width: 6px; position: relative; left: 3px; top: -1px; }
    a.sort.asc::after  { content: "↓"; }
    a.sort.desc::after { content: "↑"; }
    .hidden { display: none; }
  </style>
  <script>
    var sort_col = 0;
    var sort_direction = true;
    var search = "";        // Current search value
    var searchtimer = null; // Search callback timer

    function onSort(col) {
      if (col == sort_col && !sort_direction)
        sort_col = 0, sort_direction = true;
      else if (col == sort_col)
        sort_direction = !sort_direction;
      else
        sort_col = col, sort_direction = true;
      var table = document.getElementById("content_table");
      var rowlist = table.getElementsByTagName("tr");
      var rows = [];
      for (var i = 1, ll = rowlist.length; i != ll; rows.push(rowlist[i++]));
      rows.sort(sortfn);
      for (var i = 0; i < rows.length; i++) table.tBodies[0].appendChild(rows[i]);
      var linklist = document.getElementsByClassName("sort");
      for (var i = 0; i < linklist.length; i++) {
        linklist[i].classList.remove("asc");
        linklist[i].classList.remove("desc");
        if (i == sort_col) linklist[i].classList.add(sort_direction ? "asc" : "desc")
      }
      return false;
    };

    var onSearch = function(evt) {
      window.clearTimeout(searchtimer); // Avoid reacting to rapid changes

      var mysearch = evt.target.value.trim();
      if (27 == evt.keyCode) mysearch = evt.target.value = "";
      var mytimer = searchtimer = window.setTimeout(function() {
        if (mytimer == searchtimer && mysearch != search) {
          search = mysearch;
          doSearch();
        };
        searchtimer = null;
      }, 200);
    };

    var doSearch = function() {
      var words = String(search).split(/\s/g).filter(Boolean);
      var regexes = words.map(function(word) { return new RegExp(escapeRegExp(word), "i"); });
      var table = document.getElementById("content_table");
      table.classList.add("hidden");
      var rowlist = table.getElementsByTagName("tr");
      for (var i = 1, ll = rowlist.length; i < ll; i++) {
        var show = !search;
        var tr = rowlist[i];
        for (var j = 0, cc = tr.childElementCount; j < cc && !show; j++) {
          var text = tr.children[j].innerText;
          if (regexes.every(function(rgx) { return text.match(rgx); })) { show = true; break; };
        };
        tr.classList[show ? "remove" : "add"]("hidden");
      };
      table.classList.remove("hidden");
    };

    /** Escapes special characters in a string for RegExp. */
    var escapeRegExp = function(string) {
      return string.replace(/[-[\]{}()*+!<=:?.\/\\^$|#\s,]/g, "\\$&");
    };

    var sortfn = function(a, b) {
      var v1 = a.children[sort_col].innerText.toLowerCase();
      var v2 = b.children[sort_col].innerText.toLowerCase();
      var result = String(v1).localeCompare(String(v2), undefined, {numeric: true});
      return sort_direction ? result : -result;
    };
  </script>
</head>
<body>
<table id="body_table">
<tr><td><table id="header_table">
  <tr>
    <td>
      <div id="title">{{ title }}</div><br />
      <b>SQL:</b> <span id="sql">{{ sql or create_sql }}</span>
      <a id="toggle" title="Toggle full SQL" onclick="document.getElementById('sql').classList.toggle('clip')">...</a>
      <br />
      Source: <b>{{ db_filename }}</b>.<br />
      <b>{{ row_count }}</b> {{ util.plural("row", row_count, numbers=False) }}{{ " in results" if sql else "" }}.<br />
    </td>
  </tr></table>
  <script> document.getElementById('sql').classList.add('clip'); </script>
</td></tr><tr><td>

<div id="search">
    <input type="search" placeholder="Filter rows" title="Show only rows containing entered text" onkeyup="onSearch(event)" onsearch="onSearch(event)">
</div>
<div id="content_wrapper">
  <table id="content_table">
  <tr>
    <th class="index asc"><a class="sort asc" title="Sort by index" onclick="onSort(0)">#</a></th>
%for i, col in enumerate(columns):
    <th><a class="sort" title="Sort by {{ grammar.quote(col) }}" onclick="onSort({{ i }})">{{ col }}</a></th>
%endfor
  </tr>
<%
for chunk in data_buffer:
    echo(chunk)
%>
  </table>
</div>
</td></tr></table>
<div id="footer">{{ templates.export_comment() }}</div>
</body>
</html>
"""



"""
HTML data export template for the rows part.

@param   rows       iterable
@param   columns    [name, ]
@param   namespace  {"row_count"}
@param   ?progress  callback(count) returning whether to cancel, if any
"""
DATA_ROWS_HTML = """
%for i, row in enumerate(rows, 1):
<%
namespace["row_count"] += 1
%><tr>
  <td class="index">{{ i }}</td>
%for col in columns:
  <td>{{ "" if row[col] is None else row[col] }}</td>
%endfor
</tr>
<%
if not i % 100 and isdef("progress") and progress and not progress(count=i):
    break # for i, row
%>
%endfor
"""



"""
TXT SQL create statements export template.

@param   title         SQL export title
@param   ?db_filename  database path or temporary name
@param   sql           SQL statements string
"""
CREATE_SQL = """<%
from sqlitely import conf, templates

%>--
%if isdef("title") and title:
-- {{ title }}
%endif
%if isdef("db_filename") and db_filename:
-- Source: {{ db_filename }}.
%endif
-- {{ templates.export_comment() }}
--


{{ sql }}
"""



"""
TXT SQL insert statements export template.

@param   title        export title
@param   db_filename  database path or temporary name
@param   row_count    number of rows
@param   sql          SQL query giving export data, if any
@param   create_sql   CREATE SQL statement for export object, if any
@param   data_buffer  iterable yielding rows data in text chunks
"""
DATA_SQL = """<%
from sqlitely.lib import util
from sqlitely import conf, templates

%>-- {{ title }}.
-- Source: {{ db_filename }}.
-- {{ templates.export_comment() }}
-- {{ row_count }} {{ util.plural("row", row_count, numbers=False) }}.
%if sql:
--
-- SQL: {{ sql.replace("\\n", "\\n--      ") }};
--
%endif
%if isdef("create_sql") and create_sql:

{{ create_sql }};
%endif


<%
for chunk in data_buffer:
    echo(chunk)
%>
"""



"""
TXT SQL insert statements export template for the rows part.

@param   rows       iterable
@param   columns    [name, ]
@param   name       table name
@param   ?namespace  {"row_count"}
@param   ?progress  callback(name, count) returning whether to cancel, if any
"""
DATA_ROWS_SQL = """<%
from sqlitely import grammar, templates

str_cols = ", ".join(map(grammar.quote, columns))
%>
%for i, row in enumerate(rows, 1):
<%
if isdef("namespace"): namespace["row_count"] += 1
values = [grammar.format(row[col]) for col in columns]
%>
INSERT INTO {{ name }} ({{ str_cols }}) VALUES ({{ ", ".join(values) }});
<%
if not i % 100 and isdef("progress") and progress and not progress(name=name, count=i):
    break # for i, row
%>
%endfor
"""



"""
TXT data export template.

@param   db_filename   database path or temporary name
@param   title         export title
@param   columns       [name, ]
@param   data_buffer   iterable yielding rows data in text chunks
@param   row_count     number of rows
@param   sql           SQL query giving export data, if any
@param   create_sql    CREATE SQL statement for export object, if any
@param   columnjusts   {col name: True if ljust}
@param   columnwidths  {col name: char length}
"""
DATA_TXT = """<%
from sqlitely.lib import util
from sqlitely import conf, templates

%>{{ title }}.
Source: {{ db_filename }}.
{{ templates.export_comment() }}
{{ row_count }} {{ util.plural("row", row_count, numbers=False) }}.
%if sql:

SQL: {{ sql }}
%endif
%if name:

{{ create_sql.rstrip(";") }};
%endif

<%
headers = []
for c in columns:
    headers.append((c.ljust if columnjusts[c] else c.rjust)(columnwidths[c]))
hr = "|-" + "-|-".join("".ljust(columnwidths[c], "-") for c in columns) + "-|"
header = "| " + " | ".join(headers) + " |"
%>


{{ hr }}
{{ header }}
{{ hr }}
<%
for chunk in data_buffer:
    echo(chunk)
%>
{{ hr }}
"""



"""
TXT data export template for the rows part.

@param   rows          iterable
@param   columns       [name, ]
@param   namespace     {"row_count"}
@param   columnjusts   {col name: ljust or rjust}
@param   columnwidths  {col name: character width}
@param   ?progress     callback(count) returning whether to cancel, if any
"""
DATA_ROWS_TXT = """<%
from sqlitely import templates

%>
%for i, row in enumerate(rows, 1):
<%
values = []
namespace["row_count"] += 1
%>
%for col in columns:
<%
raw = row[col]
value = "" if raw is None \
        else raw if isinstance(raw, basestring) else str(raw)
value = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, unicode(value))
values.append((value.ljust if columnjusts[col] else value.rjust)(columnwidths[col]))
%>
%endfor
| {{ " | ".join(values) }} |
<%
if not i % 100 and isdef("progress") and progress and not progress(count=i):
    break # for i, row
%>
%endfor
"""



"""
TXT data export template for copying row as page.

@param   rows          iterable
@param   columns       [name, ]
"""
DATA_ROWS_PAGE_TXT = """<%
from sqlitely import templates

colwidth = max(map(len, columns))
%>
%for i, row in enumerate(rows):
%if i:

%endif
%for col in columns:
<%
raw = row[col]
value = "" if raw is None \
        else raw if isinstance(raw, basestring) else str(raw)
value = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, unicode(value))
%>
{{ col.ljust(colwidth) }} = {{ value }}
%endfor
%endfor
"""



"""
HTML template for search results header.

@param   text      search query
@param   fromtext  search target
"""
SEARCH_HEADER_HTML = """<%
from sqlitely import conf
%>
<font size="2" face="{{ conf.HtmlFontName }}" color="{{ conf.FgColour }}">
Results for "{{ text }}" from {{ fromtext }}:
<br /><br />
"""



"""
HTML template for SQL search results.

@param   category         schema category
@param   item             schema category object
@param   pattern_replace  regex for matching search words
"""
SEARCH_ROW_META_HTML = """<%
from sqlitely import conf, grammar

wrap_b = lambda x: "<b>%s</b>" % x.group(0)
%>
<a name="{{ category }}">{{ category.capitalize() }}</a>
<a href="{{ category }}:{{ item["name"] }}"><font color="{{ conf.LinkColour }}">{{! pattern_replace.sub(wrap_b, escape(grammar.quote(item["name"]))) }}</font></a>:
<pre><font size="2">{{! pattern_replace.sub(wrap_b, escape(item["sql"])).replace(" ", "&nbsp;") }}</font></pre>
<br /><br />
"""



"""
HTML template for data search results header; start of HTML table.

@param   category  schema category
@param   item      schema category object
"""
SEARCH_ROW_DATA_HEADER_HTML = """<%
from sqlitely import conf, grammar
%>
<font color="{{ conf.FgColour }}">
<br /><br /><b><a name="{{ item["name"] }}">{{ category.capitalize() }} {{ grammar.quote(item["name"]) }}:</a></b><br />
<table border="1" cellpadding="4" cellspacing="0" width="1000">
<tr>
<th>#</th>
%for col in item["columns"]:
<th>{{ col["name"] }}</th>
%endfor
</tr>
"""



"""
HTML template for search result of data row; HTML table row.

@param   category         schema category
@param   item             schema category object
@param   row              matching row
@param   count            search result index
@param   keywords         {"column": [], ..}
@param   pattern_replace  regex for matching search words
@param   search           {?case}
"""
SEARCH_ROW_DATA_HTML = """<%
from sqlitely import conf, searchparser, templates

match_kw = lambda k, x: searchparser.match_words(x["name"], keywords[k], any, search.get("case"))
wrap_b   = lambda x: "<b>%s</b>" % x.group(0)
%>
<tr>
<td align="right" valign="top">
  <a href="{{ category }}:{{ item["name"] }}:{{ count }}">
    <font color="{{ conf.LinkColour }}">{{ count }}</font>
  </a>
</td>
%for col in item["columns"]:
<%
value = row[col["name"]]
value = value if value is not None else ""
value = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, unicode(value))
value = escape(value)

if not (keywords.get("column") and not match_kw("column", col)) \
and not (keywords.get("-column") and match_kw("-column", col)):
    value = pattern_replace.sub(wrap_b, value)
%>
<td valign="top"><font color="{{ conf.FgColour }}">{{! value }}</font></td>
%endfor
</tr>
"""



"""Text shown in Help -> About dialog (HTML content)."""
ABOUT_HTML = """<%
import sys, wx
from sqlitely import conf
%>
<font size="2" face="{{ conf.HtmlFontName }}" color="{{ conf.FgColour }}">
<table cellpadding="0" cellspacing="0"><tr><td valign="top">
<img src="memory:{{ conf.Title.lower() }}.png" /></td><td width="10"></td><td valign="center">
<b>{{ conf.Title }} version {{ conf.Version }}</b>, {{ conf.VersionDate }}.<br /><br />


{{ conf.Title }} is an SQLite database manager, released as free open source software
under the MIT License.
</td></tr></table><br /><br />


&copy; 2019, Erki Suurjaak.
<a href="{{ conf.HomeUrl }}"><font color="{{ conf.LinkColour }}">{{ conf.HomeUrl.replace("https://", "").replace("http://", "") }}</font></a><br /><br /><br />



{{ conf.Title }} has been built using the following open source software:
<ul>
  <li>ANTLR4,
      <a href="https://www.antlr.org/"><font color="{{ conf.LinkColour }}">antlr.org</font></a></li>
  <li>openpyxl,
      <a href="https://pypi.org/project/openpyxl"><font color="{{ conf.LinkColour }}">
          pypi.org/project/openpyxl</font></a></li>
  <li>pyparsing,
      <a href="https://pypi.org/project/pyparsing/"><font color="{{ conf.LinkColour }}">pypi.org/project/pyparsing</font></a></li>
  <li>Python,
      <a href="https://www.python.org/"><font color="{{ conf.LinkColour }}">python.org</font></a></li>
  <li>SQLite,
      <a href="https://www.sqlite.org/"><font color="{{ conf.LinkColour }}">sqlite.org</font></a></li>
  <li>sqlite-parser,
      <a href="https://github.com/bkiers/sqlite-parser"><font color="{{ conf.LinkColour }}">github.com/bkiers/sqlite-parser</font></a></li>
  <li>step, Simple Template Engine for Python,
      <a href="https://github.com/dotpy/step"><font color="{{ conf.LinkColour }}">github.com/dotpy/step</font></a></li>
  <li>wxPython{{ " %s" % getattr(wx, "__version__", "") if getattr(sys, 'frozen', False) else "" }},
      <a href="http://wxpython.org"><font color="{{ conf.LinkColour }}">wxpython.org</font></a></li>
  <li>xlrd,
      <a href="https://pypi.org/project/xlrd"><font color="{{ conf.LinkColour }}">
          pypi.org/project/xlrd</font></a></li>
  <li>XlsxWriter,
      <a href="https://pypi.org/project/XlsxWriter"><font color="{{ conf.LinkColour }}">
          pypi.org/project/XlsxWriter</font></a></li>
</ul><br /><br />
%if getattr(sys, 'frozen', False):
Installer and binary executable created with:
<ul>
  <li>Nullsoft Scriptable Install System, <a href="https://nsis.sourceforge.net/"><font color="{{ conf.LinkColour }}">nsis.sourceforge.net</font></a></li>
  <li>PyInstaller, <a href="https://www.pyinstaller.org"><font color="{{ conf.LinkColour }}">pyinstaller.org</font></a></li>
</ul><br /><br />
%endif



Several icons from Fugue Icons, &copy; 2010 Yusuke Kamiyamane<br />
<a href="https://p.yusukekamiyamane.com/"><font color="{{ conf.LinkColour }}">p.yusukekamiyamane.com</font></a>
<br /><br />
Includes fonts Carlito Regular and Carlito bold,
<a href="https://fedoraproject.org/wiki/Google_Crosextra_Carlito_fonts"><font color="{{ conf.LinkColour }}">fedoraproject.org/wiki/Google_Crosextra_Carlito_fonts</font></a>
%if getattr(sys, 'frozen', False):
<br /><br />
Installer created with Nullsoft Scriptable Install System,
<a href="http://nsis.sourceforge.net/"><font color="{{ conf.LinkColour }}">nsis.sourceforge.net</font></a>
%endif

</font>
"""



"""Contents of the default page on search page."""
SEARCH_WELCOME_HTML = """<%
from sqlitely import conf
%>
<font face="{{ conf.HtmlFontName }}" size="2" color="{{ conf.FgColour }}">
<center>
<h5><font color="{{ conf.TitleColour }}">Overview</font></h5>
<table cellpadding="0" cellspacing="5">
<tr>
  <td valign="top">
    <a href="page:#search"><img src="memory:HelpSearch.png" /></a>
  </td><td valign="center">
    Search from table data over entire database,<br />
    using a simple <a href="page:#help"><font color="{{ conf.LinkColour }}">syntax</font></a>.<br /><br />
    Or search in database metadata:<br />
    table and column names and definitions.
  </td><td width="30"></td>
  <td valign="top">
    <a href="page:data"><img src="memory:HelpData.png" /></a>
  </td><td valign="center">
    Browse, filter and change table data,<br />
    export as HTML, SQL, text or spreadsheet.
  </td>
</tr>
<tr>
  <td align="center">
    <br /><a href="page:#search"><b><font color="{{ conf.FgColour }}">Search</font></b></a><br /><br />
  </td><td></td><td></td><td align="center">
    <br /><a href="page:data"><b><font color="{{ conf.FgColour }}">Data</font></b></a><br /><br />
  </td>
</tr>
<tr>
  <td valign="top">
    <a href="page:schema"><img src="memory:HelpSchema.png" /></a>
  </td><td valign="center">
    Create and edit database schema definitions.
  </td><td width="30"></td>
  <td valign="top">
    <a href="page:sql"><img src="memory:HelpSQL.png" /></a>
  </td><td valign="center">
    Make direct SQL queries in the database,<br />
    export results as HTML, text or spreadsheet.
  </td>
</tr>
<tr>
  <td align="center">
    <br /><a href="page:schema"><b><font color="{{ conf.FgColour }}">Schema</font></b></a><br /><br />
  </td><td></td><td></td><td align="center">
    <br /><a href="page:sql"><b><font color="{{ conf.FgColour }}">SQL</font></b></a><br /><br />
  </td>
</tr>

<tr>
  <td valign="top">
    <a href="page:pragma"><img src="memory:HelpPragma.png" /></a>
  </td><td valign="center">
    See and modify database PRAGMA settings.
  </td><td width="30"></td>
  <td valign="top">
    <a href="page:info"><img src="memory:HelpInfo.png" /></a>
  </td><td valign="center">
    See information about the database file,<br />
    view general database statistics,<br />
    check database integrity for corruption and recovery.
  </td>
</tr>
<tr>
  <td align="center">
    <br /><a href="page:pragma"><b><font color="{{ conf.FgColour }}">Pragma</font></b></a><br /><br />
  </td><td></td><td></td><td align="center">
    <br /><a href="page:info"><b><font color="{{ conf.FgColour }}">Information</font></b></a><br /><br />
  </td>
</tr>
</table>
</center>
</font>
"""



"""Long help text shown in a separate tab on search page."""
SEARCH_HELP_LONG_HTML = """<%
from sqlitely import conf
try:
    import pyparsing
except ImportError:
    pyparsing = None
%>
<font size="2" face="{{ conf.HtmlFontName }}" color="{{ conf.FgColour }}">
%if not pyparsing:
<b><font color="red">Search syntax currently limited:</font></b>&nbsp;&nbsp;pyparsing not installed.<br /><br /><br />
%endif
{{ conf.Title }} supports a simple syntax for searching the database:<br /><br />
<table><tr><td width="500">
  <table border="0" cellpadding="5" cellspacing="1" bgcolor="{{ conf.HelpBorderColour }}"
   valign="top" width="500">
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Search for all words</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>this andthis alsothis</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      Row is matched if each word finds a match in at least one column.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Search for exact word or phrase</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>"do re mi"</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      Use quotes (<font color="{{ conf.HelpCodeColour }}"><code>"</code></font>) to search for
      an exact phrase or word. Quoted text is searched exactly as entered,
      leaving empty space as-is and ignoring any wildcard characters.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Search for either word</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>this OR that</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      To find results containing at least one of several words,
      include <font color="{{ conf.HelpCodeColour }}"><code>OR</code></font> between the words.
      <font color="{{ conf.HelpCodeColour }}"><code>OR</code></font> works also
      for phrases and grouped words (but not keywords).
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Group words together</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>(these two) OR this<br/>
      -(none of these)</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      Surround words with round brackets to group them for <code>OR</code>
      queries, or for excluding from results.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Search for partially matching text</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>bas*ball</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      Use an asterisk (<font color="{{ conf.HelpCodeColour }}"><code>*</code></font>) to make a
      wildcard query: the wildcard will match any text between its front and
      rear characters (including empty space and other words).
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Exclude words or keywords</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>-notthisword<br />-"not this phrase"<br />
      -(none of these)<br/>-table:notthistable<br/>
      -date:2013</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      To exclude certain results, add a dash
      (<font color="{{ conf.HelpCodeColour }}"><code>-</code></font>) in front of words,
      phrases, grouped words or keywords.
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Search specific tables</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>table:fromthistable<br />
      view:fromthisview<br />
      -table:notfromthistable<br />
      -view:notfromthisview</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      Use the keyword <font color="{{ conf.HelpCodeColour }}"><code>table:name</code></font>
      or <font color="{{ conf.HelpCodeColour }}"><code>view:name</code></font>
      to constrain results to specific tables and views only.<br /><br />
      Search from more than one source by adding more
      <font color="{{ conf.HelpCodeColour }}"><code>table:</code></font> or
      <font color="{{ conf.HelpCodeColour }}"><code>view:</code></font> keywords, or exclude certain
      sources by adding a <font color="{{ conf.HelpCodeColour }}"><code>-table:</code></font>
      or <font color="{{ conf.HelpCodeColour }}"><code>-view:</code></font> keyword.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Search specific columns</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>column:fromthiscolumn<br />
      -column:notfromthiscolumn</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      Use the keyword <font color="{{ conf.HelpCodeColour }}"><code>column:name</code></font>
      to constrain results to specific columns only.<br /><br />
      Search from more than one column by adding more
      <font color="{{ conf.HelpCodeColour }}"><code>column:</code></font> keywords, or exclude certain
      columns by adding a <font color="{{ conf.HelpCodeColour }}"><code>-column:</code></font> keyword.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{ conf.BgColour }}" width="150">
      <b>Search from specific time periods</b><br /><br />
      <font color="{{ conf.HelpCodeColour }}"><code>date:2008<br />date:2009-01<br />
      date:2005-12-24..2007</code></font>
      <br />
    </td>
    <td bgcolor="{{ conf.BgColour }}">
      <br /><br />
      To find rows from specific time periods (where source has DATE/DATETIME columns), use the keyword
      <font color="{{ conf.HelpCodeColour }}"><code>date:period</code></font> or
      <font color="{{ conf.HelpCodeColour }}"><code>date:periodstart..periodend</code></font>.
      For the latter, either start or end can be omitted.<br /><br />
      A date period can be year, year-month, or year-month-day. Additionally,
      <font color="{{ conf.HelpCodeColour }}"><code>date:period</code></font> can use a wildcard
      in place of any part, so
      <font color="{{ conf.HelpCodeColour }}"><code>date:*-12-24</code></font> would search for
      all rows having a timestamp from the 24th of December.<br /><br />
      Search from a more narrowly defined period by adding more
      <font color="{{ conf.HelpCodeColour }}"><code>date:</code></font> keywords.
      <br />
    </td>
  </tr>
  </table>

</td><td valign="top" align="left">

  <b><font size="3">Examples</font></b><br /><br />

  <ul>
    <li>search for "domain.com" in columns named "url":
        <br /><br />
        <font color="{{ conf.HelpCodeColour }}">
        <code>domain.com column:url</code></font><br />
    </li>
    <li>search for "foo bar" up to 2011:<br /><br />
        <font color="{{ conf.HelpCodeColour }}"><code>"foo bar" date:..2011</code></font>
        <br />
    </li>
    <li>search for either "John" and "my side" or "Stark" and "your side":
        <br /><br />
        <font color="{{ conf.HelpCodeColour }}">
        <code>(john "my side") OR (stark "your side")</code></font><br />
    </li>
    <li>search for either "birthday" or "cake" in 2012,
        except from June to August:<br /><br />
        <font color="{{ conf.HelpCodeColour }}">
        <code>birthday OR cake date:2012 -date:2012-06..2012-08</code>
        </font><br />
    </li>
    <li>search for "TPS report" but not "my TPS report"
        on the first day of the month in 2012:
        <br /><br />
        <font color="{{ conf.HelpCodeColour }}">
        <code>"tps report" -"my tps report" date:2012-*-1</code>
        </font><br />
    </li>
  </ul>

  <br /><br />
  All search texts and keywords are case-insensitive by default. <br />
  Keywords are global, even when in bracketed (grouped words). <br />
  Metadata search supports only <code>table:</code> and <code>view:</code> keywords.

</td></tr></table>
</font>
"""



"""Short help text shown on search page."""
SEARCH_HELP_SHORT_HTML = """<%
import os
from sqlitely import conf
helplink = "Search help"
if "nt" == os.name: # In Windows, wx.HtmlWindow shows link whitespace quirkily
    helplink = helplink.replace(" ", "_")

%>
<font size="2" face="{{ conf.HtmlFontName }}" color="{{ conf.DisabledColour }}">
For searching from specific tables, add "table:name", and from specific columns, add "column:name".
&nbsp;&nbsp;<a href=\"page:#help\"><font color="{{ conf.LinkColour }}">{{ helplink }}</font></a>.
</font>
"""



"""
Database statistics HTML.

@param   ?error    error message, if any
@param   ?data     {"table": [{name, size, size_total, ?size_index, ?index: []}],
                   "index": [{name, size, table}]}
@param   ?running  whether analysis is currently running
"""
STATISTICS_HTML = """<%
from sqlitely.lib.vendor.step import Template
from sqlitely.lib import util
from sqlitely import conf, templates
%>
<font face="{{ conf.HtmlFontName }}" size="2" color="{{ conf.FgColour }}">

%if isdef("error"):
    {{ error }}


%elif isdef("data"):
<%
index_total = sum(x["size"] for x in data["index"])
total = index_total + sum(x["size"] for x in data["table"])
%>

<font color="{{ conf.PlotTableColour }}" size="4"><b>Table sizes</b></font>
<table cellpadding="0" cellspacing="4">
  <tr>
    <th></th>
    <th align="left">Name</th>
    <th align="left">Size</th>
    <th align="left">Bytes</th>
  </tr>
    %for item in sorted(data["table"], key=lambda x: (-x["size"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.STATISTICS_ROW_PLOT_HTML).expand(dict(category="table", size=item["size"], total=total)) }}</td>
    <td nowrap="">{{ item["name"] }}</td>
    <td align="right" nowrap="">{{ util.format_bytes(item["size"]) }}</td>
    <td align="right" nowrap="">{{ util.format_bytes(item["size"], max_units=False, with_units=False) }}</td>
  </tr>
    %endfor
</table>

    %if data["index"]:

<br /><br />
<font color="{{ conf.PlotTableColour }}" size="4"><b>Table sizes with indexes</b></font>
<table cellpadding="0" cellspacing="4">
  <tr>
    <th></th>
    <th align="left">Name</th>
    <th align="left">Size</th>
    <th align="left">Bytes</th>
  </tr>
        %for item in sorted(data["table"], key=lambda x: (-x["size_total"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.STATISTICS_ROW_PLOT_HTML).expand(dict(category="table", size=item["size_total"], total=total)) }}</td>
    <td nowrap="">{{ item["name"] }}</td>
    <td align="right" nowrap="">{{ util.format_bytes(item["size_total"]) }}</td>
    <td align="right" nowrap="">{{ util.format_bytes(item["size_total"], max_units=False, with_units=False) }}</td>
  </tr>
        %endfor
</table>

<br /><br />
<font color="{{ conf.PlotIndexColour }}" size="4"><b>Table index sizes</b></font>
<table cellpadding="0" cellspacing="4">
  <tr>
    <th></th>
    <th align="left">Name</th>
    <th align="left">Size</th>
    <th align="left">Bytes</th>
    <th align="left" nowrap="">Index Ratio</th>
  </tr>
        %for item in sorted([x for x in data["table"] if "index" in x], key=lambda x: (-x["size_index"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.STATISTICS_ROW_PLOT_HTML).expand(dict(category="index", size=item["size_index"], total=total)) }}</td>
    <td nowrap="">{{ item["name"] }} ({{ len(item["index"]) }})</td>
    <td align="left" nowrap="">{{ util.format_bytes(item["size_index"]) }}</td>
    <td align="right" nowrap="">{{ util.format_bytes(item["size_index"], max_units=False, with_units=False) }}</td>
    <td align="right">{{ int(round(100 * util.safedivf(item["size_index"], index_total))) }}%</td>
  </tr>
        %endfor
</table>

<br /><br />
<font color="{{ conf.PlotIndexColour }}" size="4"><b>Index sizes</b></font>
<table cellpadding="0" cellspacing="4">
  <tr>
    <th></th>
    <th align="left">Name</th>
    <th align="left">Table</th>
    <th align="left">Size</th>
    <th align="left">Bytes</th>
    <th align="left" nowrap="">Index Ratio</th>
  </tr>
        %for item in sorted(data["index"], key=lambda x: (-x["size"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.STATISTICS_ROW_PLOT_HTML).expand(dict(category="index", size=item["size"], total=total)) }}</td>
    <td nowrap="">{{ item["name"] }}</td>
    <td nowrap="">{{ item["table"] }}</td>
    <td align="right" nowrap="">{{ util.format_bytes(item["size"]) }}</td>
    <td align="right" nowrap="">{{ util.format_bytes(item["size"], max_units=False, with_units=False) }}</td>
    <td align="right">{{ int(round(100 * util.safedivf(item["size"], index_total))) }}%</td>
  </tr>
        %endfor
</table>

    %endif


%elif isdef("running") and running:
    Analyzing..
%else:
    Press Refresh to generate statistics.
%endif

</font>
"""



"""
Database statistics row plot.

@param   category  "table" or "index"
@param   size      item size
@param   total     total size
"""
STATISTICS_ROW_PLOT_HTML = """<%
from sqlitely.lib import util
from sqlitely import conf

ratio = util.safedivf(size, total)
if 0.99 <= ratio < 1: ratio = 0.99
percent = int(round(100 * ratio))
text_cell1 = "&nbsp;%d%%&nbsp;" % round(percent) if (round(percent) > 30) else ""
text_cell2 = "" if text_cell1 else "&nbsp;%d%%&nbsp;" % percent
fgcolour = conf.PlotTableColour if "table" == category else conf.PlotIndexColour

%>
<table cellpadding="0" cellspacing="0" width="{{ conf.StatisticsPlotWidth }}"><tr>
  <td bgcolor="{{ fgcolour }}"
      width="{{ int(round(ratio * conf.StatisticsPlotWidth)) }}" align="center">
%if text_cell1:
    <font color="#FFFFFF" size="2"><b>{{! text_cell1 }}</b></font>
%endif
  </td>
  <td bgcolor="{{ conf.PlotBgColour }}" width="{{ int(round((1 - ratio) * conf.StatisticsPlotWidth)) }}" align="center">
%if text_cell2:
    <font color="{{ fgcolour }}" size="2"><b>{{! text_cell2 }}</b></font>
%endif
  </td>
</tr></table>
"""



"""
HTML statistics export template.

@param   title        export title
@param   db_filename  database filename
@param   db_filesize  database size in bytes
@param   data         {"table": [{name, size, size_total, ?size_index, ?index: []}],
                       "index": [{name, size, table}]}
"""
DATA_STATISTICS_HTML = """<%
from sqlitely.lib.vendor.step import Template
from sqlitely.lib import util
from sqlitely import conf, images, templates
%><!DOCTYPE HTML><html lang="en">
<head>
  <meta http-equiv='Content-Type' content='text/html;charset=utf-8' />
  <meta name="Author" content="{{ conf.Title }}">
  <title>{{ title }}</title>
  <link rel="shortcut icon" type="image/png" href="data:image/ico;base64,{{! images.Icon16x16_8bit.data }}"/>
  <style>
    body {
      background: #8CBEFF;
      font-family: Tahoma;
      font-size: 11px;
      margin: 0;
    }
    #title { font-size: 1.1em; font-weight: bold; color: #3399FF; }
    table#header_table {
      width: 100%;
    }
    #content_wrapper {
      max-width: calc(100vw - 60px);
      overflow-x: auto;
      padding: 0 30px 10px 30px;
    }
    table#body_table {
      margin-left: auto;
      margin-right: auto;
      border-spacing: 0px 10px;
      padding: 0 10px;
    }
    table#body_table > tbody > tr > td {
      background: white;
      min-width: 800px;
      font-family: Tahoma;
      font-size: 11px;
      border-radius: 10px;
      padding: 10px;
    }
    h2 { margin-bottom: 5px; margin-top: 20px; }
    td { text-align: left; white-space: nowrap; }
    th { text-align: left; white-space: nowrap; }
    td.right { text-align: right; }
    .table { color: {{ conf.PlotTableColour }}; }
    .index { color: {{ conf.PlotIndexColour }}; }
    table.plot {
      border-collapse: collapse;
      font-weight: bold;
      text-align: center;
      width: {{ conf.StatisticsPlotWidth }}px;
    }
    table.plot.table td {
      color: #FFFFFF;
      text-align: center;
    }
    table.plot.table td:first-child {
      background-color: {{ conf.PlotTableColour }};
    }
    table.plot.index td:first-child {
      background-color: {{ conf.PlotIndexColour }};
    }
    table.plot td:last-child {
      background-color: {{ conf.PlotBgColour }};
    }
    table.plot.table td:last-child {
      color: {{ conf.PlotTableColour }};
    }
    table.plot.index td:last-child {
      color: {{ conf.PlotIndexColour }};
    }
    #footer {
      text-align: center;
      padding-bottom: 10px;
      color: #666;
    }
  </style>
</head>
<body>
<table id="body_table">
<%
index_total = sum(x["size"] for x in data["index"])
table_total = sum(x["size"] for x in data["table"])
total = index_total + sum(x["size"] for x in data["table"])
%>
<tr><td><table id="header_table">
  <tr>
    <td>
      <div id="title">{{ title }}</div><br />
      Source: <b>{{ db_filename }}</b>.<br />
      Source size: <b>{{ util.format_bytes(db_filesize) }}</b> ({{ util.format_bytes(db_filesize, max_units=False) }}).<br />
%if data["table"]:
      <b>{{ util.plural("table", data["table"]) }}</b>, {{ util.format_bytes(table_total) }}.<br />
%endif
%if data["index"]:
      <b>{{ util.plural("index", data["index"]) }}</b>, {{ util.format_bytes(index_total) }}.<br />
%endif
    </td>
  </tr></table>
</td></tr><tr><td>

<div id="content_wrapper">

  <h2 class="table">Table sizes</h2>
  <table class="stats">
    <tr>
      <th></th>
      <th>Name</th>
      <th>Size</th>
      <th>Bytes</th>
    </tr>
%for item in sorted(data["table"], key=lambda x: (-x["size"], x["name"].lower())):
    <tr>
      <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="table", size=item["size"], total=total)) }}</td>
      <td>{{ item["name"] }}</td>
      <td class="right">{{ util.format_bytes(item["size"]) }}</td>
      <td class="right">{{ util.format_bytes(item["size"], max_units=False, with_units=False) }}</td>
    </tr>
%endfor
  </table>


%if data["index"]:

<h2 class="table">Table sizes with indexes</h2>
<table class="stats">
  <tr>
    <th></th>
    <th>Name</th>
    <th>Size</th>
    <th>Bytes</th>
  </tr>
    %for item in sorted(data["table"], key=lambda x: (-x["size_total"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="table", size=item["size_total"], total=total)) }}</td>
    <td>{{ item["name"] }}</td>
    <td class="right">{{ util.format_bytes(item["size_total"]) }}</td>
    <td class="right">{{ util.format_bytes(item["size_total"], max_units=False, with_units=False) }}</td>
  </tr>
    %endfor
</table>

<h2 class="index">Table index sizes</h2>
<table class="stats">
  <tr>
    <th></th>
    <th>Name</th>
    <th>Size</th>
    <th>Bytes</th>
    <th>Index Ratio</th>
  </tr>
    %for item in sorted([x for x in data["table"] if "index" in x], key=lambda x: (-x["size_index"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="index", size=item["size_index"], total=total)) }}</td>
    <td>{{ item["name"] }} ({{ len(item["index"]) }})</td>
    <td class="right">{{ util.format_bytes(item["size_index"]) }}</td>
    <td class="right">{{ util.format_bytes(item["size_index"], max_units=False, with_units=False) }}</td>
    <td class="right">{{ int(round(100 * util.safedivf(item["size_index"], index_total))) }}%</td>
  </tr>
    %endfor
</table>

<h2 class="index">Index sizes</h2>
<table class="stats">
  <tr>
    <th></th>
    <th>Name</th>
    <th>Table</th>
    <th>Size</th>
    <th>Bytes</th>
    <th>Index Ratio</th>
  </tr>
    %for item in sorted(data["index"], key=lambda x: (-x["size"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="index", size=item["size"], total=total)) }}</td>
    <td>{{ item["name"] }}</td>
    <td>{{ item["table"] }}</td>
    <td class="right">{{ util.format_bytes(item["size"]) }}</td>
    <td class="right">{{ util.format_bytes(item["size"], max_units=False, with_units=False) }}</td>
    <td class="right">{{ int(round(100 * util.safedivf(item["size"], index_total))) }}%</td>
  </tr>
    %endfor
</table>

%endif


</div>
</td></tr></table>
<div id="footer">{{ templates.export_comment() }}</div>
</body>
</html>
"""



"""
Database statistics row plot.

@param   category  "table" or "index"
@param   size      item size
@param   total     total size
"""
DATA_STATISTICS_ROW_PLOT_HTML = """<%
from sqlitely.lib import util

ratio = util.safedivf(size, total)
if 0.99 <= ratio < 1: ratio = 0.99
percent = int(round(100 * ratio))
text_cell1 = "&nbsp;%d%%&nbsp;" % round(percent) if (round(percent) > 30) else ""
text_cell2 = "" if text_cell1 else "&nbsp;%d%%&nbsp;" % percent

%>
<table class="plot {{ category }}"><tr>
  <td style="width: {{ percent }}%;">{{! text_cell1 }}</td>
  <td style="width: {{ 100 - percent }}%;">{{! text_cell2 }}</td>
</tr></table>
"""



"""
Database statistics text.

@param   db_filename  database filename
@param   db_filesize  database size in bytes
@param   data         {"table": [{name, size, size_total, ?size_index, ?index: []}],
                       "index": [{name, size, table}]}
"""
DATA_STATISTICS_TXT = """<%
from sqlitely.lib.vendor.step import Template
from sqlitely.lib import util
from sqlitely import templates

index_total = sum(x["size"] for x in data["index"])
table_total = sum(x["size"] for x in data["table"])
total = index_total + sum(x["size"] for x in data["table"])
%>
Source: {{ db_filename }}.
Size: {{ util.format_bytes(db_filesize) }} ({{ util.format_bytes(db_filesize, max_units=False) }}).

<%
items = sorted(data["table"], key=lambda x: (-x["size"], x["name"].lower()))
cols = ["Name", "Size", "Bytes"]
vals = {x["name"]: (
    x["name"],
    util.format_bytes(x["size"]),
    util.format_bytes(x["size"], max_units=False, with_units=False),
) for x in items}
justs  = {0: 1, 1: 0, 2: 0}
%>
{{! Template(templates.DATA_STATISTICS_TABLE_TXT, strip=False).expand(dict(title="Table sizes", items=items, sizecol="size", cols=cols, vals=vals, justs=justs, total=total)) }}
%if data["index"]:
<%

items = sorted(data["table"], key=lambda x: (-x["size_total"], x["name"].lower()))
cols = ["Name", "Size", "Bytes"]
vals = {x["name"]: (
    x["name"],
    util.format_bytes(x["size_total"]),
    util.format_bytes(x["size_total"], max_units=False, with_units=False),
) for x in items}
justs  = {0: 1, 1: 0, 2: 0}
%>

{{! Template(templates.DATA_STATISTICS_TABLE_TXT, strip=False).expand(dict(title="Table sizes with indexes", items=items, sizecol="size_total", cols=cols, vals=vals, justs=justs, total=total)) }}
<%

items = sorted([x for x in data["table"] if "index" in x], key=lambda x: (-x["size_index"], x["name"].lower()))
cols = ["Name", "Size", "Bytes", "Index Ratio"]
vals = {x["name"]: (
    "%s (%s)" % (x["name"], len(x["index"])),
    util.format_bytes(x["size_index"]),
    util.format_bytes(x["size_index"], max_units=False, with_units=False),
    "%s%%" % int(round(100 * util.safedivf(x["size_index"], index_total))),
) for x in items}
justs  = {0: 1, 1: 0, 2: 0, 3: 0}
%>

{{! Template(templates.DATA_STATISTICS_TABLE_TXT, strip=False).expand(dict(title="Table index sizes", items=items, sizecol="size_index", cols=cols, vals=vals, justs=justs, total=total)) }}
<%

items = sorted(data["index"], key=lambda x: (-x["size"], x["name"].lower()))
cols = ["Name", "Table", "Size", "Bytes", "Index Ratio"]
vals = {x["name"]: (
    x["name"],
    x["table"],
    util.format_bytes(x["size"]),
    util.format_bytes(x["size"], max_units=False, with_units=False),
    "%s%%" % int(round(100 * util.safedivf(x["size"], index_total))),
) for x in items}
justs  = {0: 1, 1: 1, 2: 0, 3: 0, 4: 0}
%>

{{! Template(templates.DATA_STATISTICS_TABLE_TXT, strip=False).expand(dict(title="Index sizes", items=items, sizecol="size", cols=cols, vals=vals, justs=justs, total=total)) }}
%endif
"""



"""
Database statistics table section.

@param   title    section title
@param   items    section item rows
@param   sizecol  name of item column containing size
@param   cols     [col1, ]
@param   vals     {row name: [row val1, ], }
@param   justs    {col index: ljust or rjust}
@param   total    total size to set ratio of
"""
DATA_STATISTICS_TABLE_TXT = """<%
from sqlitely.lib import util

PLOT_WIDTH, PAD, X = 30, 2, "="

def plot(size):
    ratio = util.safedivf(size, total)
    if 0.99 <= ratio < 1: ratio = 0.99
    bar = X * int(PLOT_WIDTH * ratio)
    pad = " " * (PLOT_WIDTH - len(bar))
    pc = " %s%% " % int(round(100 * ratio))
    if len(bar) - len(pc) > 3:
        bar = pc.center(len(bar), bar[0])
    else:
        pad = pc.center(len(pad), pad[0])
    return bar + pad

widths = {i: max([len(x[i]) for x in vals.values()] +
                 [len(cols[i])])
          for i in range(len(cols))}
%>
{{ title }}
{{ (" " * PAD).join([" " * (PLOT_WIDTH + 2)] + [x.ljust(widths[i]) for i, x in enumerate(cols)]) }}
%for item in items:
[{{ plot(item[sizecol]) }}]{{ (" " * PAD) }}{{ (" " * PAD).join((x.ljust if justs[i] else x.rjust)(widths[i]) for i, x in enumerate(vals[item["name"]])) }}
%endfor
"""



"""
Database statistics SQL export template.

@param   db_filename  database path or temporary name
@param   db_filesize  database size in bytes
@param   sql          SQL query giving export data, if any
"""
DATA_STATISTICS_SQL = """<%
from sqlitely.lib import util
from sqlitely import conf, templates

%>-- Output from sqlite3_analyzer.
-- Source: {{ db_filename }}.
-- Source size: {{ util.format_bytes(db_filesize) }} ({{ util.format_bytes(db_filesize, max_units=False) }}).
-- {{ templates.export_comment() }}


{{! sql.replace("\\r", "") }}
"""



"""
Database dump SQL template.

@param   db         database.Database instance
@param   sql        schema SQL
@param   data       [{name, columns, rows}]
@param   pragma     PRAGMA values as {name: value}
@param   ?progress  callback(count) returning whether to cancel, if any
"""
DUMP_SQL = """<%
import itertools
from sqlitely.lib.vendor.step import Template
from sqlitely import grammar, templates

PRAGMAS_FIRST = ("auto_vacuum", "encoding")
pragma_first = {k: v for k, v in pragma.items() if k in PRAGMAS_FIRST}
pragma_last  = {k: v for k, v in pragma.items() if k not in PRAGMAS_FIRST}
%>
-- Database dump.
-- Source: {{ db.name }}.
-- {{ templates.export_comment() }}
%if pragma_first:

-- Initial PRAGMA settings
{{! Template(templates.PRAGMA_SQL).expand(pragma=pragma_first) }}

%endif
%if sql:

{{ sql }}

%endif

%for table in data:
<%
if progress and not progress(): break # for table
row = next(table["rows"], None)
if not row: continue # for table
rows = itertools.chain([row], table["rows"])
%>
-- Table {{ grammar.quote(table["name"], force=True) }} data:
{{! Template(templates.DATA_ROWS_SQL).expand(dict(table, progress=progress, rows=rows)) }}

%endfor

-- PRAGMA settings
{{! Template(templates.PRAGMA_SQL).expand(pragma=pragma_last) }}
"""



"""
Database PRAGMA statements SQL template.

@param   pragma   PRAGMA values as {name: value}
"""
PRAGMA_SQL = """<%
from sqlitely import database

pragma = dict(pragma)
for name, opts in database.Database.PRAGMA.items():
    if opts.get("read") or opts.get("write") is False:
        pragma.pop(name, None)

lastopts, count = {}, 0
sortkey = lambda x: (bool(x[1].get("deprecated")), x[1]["label"])
%>
%for name, opts in sorted(database.Database.PRAGMA.items(), key=sortkey):
<%
if name not in pragma:
    lastopts = opts
    continue # for name, opts

%>
    %if opts.get("deprecated") and bool(lastopts.get("deprecated")) != bool(opts.get("deprecated")):

-- DEPRECATED:
    %endif
<%
value = pragma[name]
if isinstance(value, basestring):
    value = '"%s"' % value.replace('"', '""')
elif isinstance(value, bool): value = str(value).upper()
lastopts = opts
%>
{{ "\\n" if count else "" }}PRAGMA {{ name }} = {{ value }};
<%
count += 1
%>
%endfor
"""
