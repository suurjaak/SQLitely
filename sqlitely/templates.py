# -*- coding: utf-8 -*-
"""
HTML and TXT templates for exports and statistics.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    26.12.2019
------------------------------------------------------------------------------
"""
import datetime
import re

from . import conf

# Modules imported inside templates:
#import collections, itertools, json, math, os, pyparsing, sys, urllib, wx
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
    #sqlintro { font-family: monospace; white-space: pre-wrap; }
    #sql { font-family: monospace; white-space: pre-wrap; }
    a.toggle:hover { cursor: pointer; text-decoration: none; }
    a.toggle::after { content: ".. \\\\25b6"; font-size: 1.2em; position: relative; top: 2px; }
    a.toggle.open::after { content: " \\\\25b2"; font-size: 0.7em; }
    a.sort { display: block; }
    a.sort:hover { cursor: pointer; text-decoration: none; }
    a.sort::after      { content: ""; display: inline-block; min-width: 6px; position: relative; left: 3px; top: -1px; }
    a.sort.asc::after  { content: "↓"; }
    a.sort.desc::after { content: "↑"; }
    .hidden { display: none; }
    @-moz-document url-prefix() { /* Firefox-specific tweaks */
        a.toggle { top: 0; }
        a.toggle::after { font-size: 0.7em; top: 0 !important; }
    }
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
      };
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

    var onToggle = function(a, id1, id2) {
        a.classList.toggle('open');
        document.getElementById(id1).classList.toggle('hidden');
        document.getElementById(id2).classList.toggle('hidden');
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
      <b>SQL:</b>
      <span id="sql" class="hidden">{{ sql or create_sql }}</span>
      <span id="shortsql">{{ (sql or create_sql).split("\\n", 1)[0] }}</span>
      <a class="toggle" title="Toggle full SQL" onclick="onToggle(this, 'shortsql', 'sql')"> </a>
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
JSON export template.

@param   title        export title
@param   db_filename  database path or temporary name
@param   row_count    number of rows
@param   sql          SQL query giving export data, if any
@param   create_sql   CREATE SQL statement for export object, if any
@param   data_buffer  iterable yielding rows data in text chunks
"""
DATA_JSON = """<%
from sqlitely.lib import util
from sqlitely import conf, templates

%>// {{ title }}.
// Source: {{ db_filename }}.
// {{ templates.export_comment() }}
// {{ row_count }} {{ util.plural("row", row_count, numbers=False) }}.
%if sql:
//
// SQL: {{ sql.replace("\\n", "\\n//      ") }};
//
%endif
%if isdef("create_sql") and create_sql:
//
// {{ create_sql.rstrip(";").replace("\\n", "\\n//  ") }};
//
%endif

[
<%
for chunk in data_buffer:
    echo(chunk)
%>
]
"""



"""
JSON export template for the rows part.

@param   rows       iterable
@param   columns    [name, ]
@param   name       table name
@param   ?namespace  {"row_count"}
@param   ?progress  callback(name, count) returning whether to cancel, if any
"""
DATA_ROWS_JSON = """<%
import collections, json
from sqlitely import templates

rows = iter(rows)
i, row, nextrow = 1, next(rows, None), next(rows, None)
indent = "  " if nextrow else ""
while row:
    namespace["row_count"] += 1
    data = collections.OrderedDict(((c, row[c]) for c in columns))
    text = json.dumps(data, indent=2)
    echo("  " + text.replace("\\n", "\\n  ") + (",\\n" if nextrow else "\\n"))

    i, row, nextrow = i + 1, nextrow, next(rows, None)
    if not i % 100 and isdef("progress") and progress and not progress(count=i):
        break # while row
%>"""



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

{{ create_sql.rstrip(";") }};
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
TXT SQL update statements export template.

@param   rows       iterable
@param   originals  original rows iterable
@param   columns    [name, ]
@param   pks        [name, ]
@param   name       table name
"""
DATA_ROWS_UPDATE_SQL = """<%
from sqlitely import grammar, templates

str_cols = ", ".join(map(grammar.quote, columns))
%>
%for row, original in zip(rows, originals):
<%
setstr = ", ".join("%s = %s" % (grammar.quote(col), grammar.format(row[col]))
                   for col in columns if col not in pks or row[col] != original[col])
wherestr = " AND ".join("%s = %s" % (grammar.quote(col), grammar.format(original[col]))
                   for col in pks if col in original)
%>
UPDATE {{ name }} SET {{ setstr }}{{ (" WHERE " + wherestr) if wherestr else "" }};
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
@param   columnjusts   {col name: ljust or rjust}
@param   columnwidths  {col name: character width}
@param   ?namespace    {"row_count"}
@param   ?progress     callback(count) returning whether to cancel, if any
"""
DATA_ROWS_TXT = """<%
from sqlitely import templates

%>
%for i, row in enumerate(rows, 1):
<%
values = []
if isdef("namespace"): namespace["row_count"] += 1
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
<table border="1" cellpadding="4" cellspacing="0" width="100%">
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
    <th align="left" nowrap="">Proportion</th>
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
    <th align="left" nowrap="">Proportion</th>
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
@param   db           database.Database instance
@param   pragma       pragma settings to export, as {name: value},
@param   sql          database schema SQL,
@param   stats        {"table": [{name, size, size_total, ?size_index, ?index: []}],
                       "index": [{name, size, table}]}
"""
DATA_STATISTICS_HTML = """<%
import math, urllib
from sqlitely.lib.vendor.step import Template
from sqlitely.lib import util
from sqlitely import conf, grammar, images, templates

COLS = {"table":   ["Name", "Columns", "Related tables", "Other relations", "Rows", "Size in bytes"]
                   if stats else ["Name", "Columns", "Related tables", "Other relations", "Rows"],
        "index":   ["Name", "Table", "Columns", "Size in bytes"] if stats else ["Name", "Table", "Columns"],
        "trigger": ["Name", "Owner", "When", "Uses"],
        "view":    ["Name", "Columns", "Uses", "Used by"], }
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
    h2 { margin-bottom: 0; margin-top: 20px; }
    div.section {
      border: 1px solid darkgray;
      border-radius: 10px;
      margin-top: 10px;
      padding: 10px;
    }
    div.section > h2:first-child {
      margin-top: 0;
    }
    table.stats > tbody > tr > th { text-align: left; white-space: nowrap; }
    table.stats > tbody > tr > td { text-align: left; white-space: nowrap; }
    table.stats > tbody > tr > td:nth-child(n+2) {
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .right { text-align: right !important; }
    .name { word-break: break-all; word-break: break-word; }
    .nowrap { word-break: normal !important; }
    .table { color: {{ conf.PlotTableColour }}; }
    .index { color: {{ conf.PlotIndexColour }}; }
    table.plot {
      border-collapse: collapse;
      font-weight: bold;
      text-align: center;
      width: {{ 1.5 * conf.StatisticsPlotWidth }}px;
    }
    table.plot td {
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
    table.plot td span {
      position: relative;
    }
    table.plot.table td:last-child {
      color: {{ conf.PlotTableColour }};
    }
    table.plot.index td:last-child {
      color: {{ conf.PlotIndexColour }};
    }
    table.content {
      empty-cells: show;
      border-spacing: 2px;
      width: 100%;
    }
    table.content > tbody > tr > td {
      border: 1px solid #C0C0C0;
      line-height: 1.5em;
      padding: 5px;
      position: relative;
      vertical-align: top;
      word-break: break-all;
      word-break: break-word;
    }
    table.content > tbody > tr > th {
      text-align: center;
      vertical-align: bottom;
      white-space: nowrap;
    }
    table.content > tbody > tr > td.index, table.content > tbody > tr > th.index { color: gray; width: 10px; }
    table.content > tbody > tr > td.index { text-align: right; white-space: nowrap; }
    table.subtable { border-collapse: collapse; width: 100%; }
    table.subtable > tbody > tr > td:last-child { text-align: right; vertical-align: top; }
    a, a.visited { color: #3399FF; text-decoration: none; }
    a:hover, a.visited:hover { text-decoration: underline; }
    div.sql { font-family: monospace; text-align: left; white-space: pre-wrap; word-break: break-all; word-break: break-word; }
    a.sort:hover, a.toggle:hover { cursor: pointer; text-decoration: none; }
    a.toggle { white-space: nowrap; }
    a.toggle::after { content: " \\\\25b6"; }
    a.toggle.open::after { content: " \\\\25bc"; font-size: 0.7em; }
    h2 > a.toggle::after { position: relative; top: 2px; }
    h2 > a.toggle.open::after { top: 0; }
    a.toggle.right { display: block; text-align: right; }
    .hidden { display: none; }
    #toggle_all { text-align: right; }
    a.sort { display: block; }
    a.sort::after      { content: ""; display: inline-block; min-width: 6px; position: relative; left: 3px; top: -1px; }
    a.sort.asc::after  { content: "↓"; }
    a.sort.desc::after { content: "↑"; }
    #footer {
      text-align: center;
      padding-bottom: 10px;
      color: #666;
    }
    @-moz-document url-prefix() { /* Firefox-specific tweaks */
        a.toggle::after { font-size: 0.7em; top: 0 !important; }
    }
  </style>
  <script>
    var sort_cols = {}; // {id: index}
    var sort_directions = {}; // {id: bool}

    window.addEventListener("popstate", onRoute);

    function onRoute(evt) {
      var hash = document.location.hash.slice(1);
      var path = hash.split("/").filter(Boolean), accum = "";
      for (var i = 0; i < path.length; i++) {
        accum += (accum ? "/" : "") + path[i];
        var a = document.getElementById("toggle_" + accum);
        if (a && !a.classList.contains("open")) a.click();
      };
    };

    function onSort(id, col) {
      var sort_col       = sort_cols[id] || 0,
          sort_direction = (id in sort_directions) ? sort_directions[id] : true;
      if (col == sort_col && !sort_direction)
        sort_col = 0, sort_direction = true;
      else if (col == sort_col)
        sort_direction = !sort_direction;
      else
        sort_col = col, sort_direction = true;
      var table = document.getElementById(id);
      var rowlist = [].slice.call(table.getElementsByTagName("tr"));
      rowlist = rowlist.filter(function(x) { return x.parentNode.parentNode == table; });
      var rows = [];
      for (var i = 1, ll = rowlist.length; i != ll; rows.push(rowlist[i++]));
      rows.sort(sortfn.bind(null, sort_col, sort_direction));
      for (var i = 0; i < rows.length; i++) table.tBodies[0].appendChild(rows[i]);
      var linklist = table.getElementsByClassName("sort");
      for (var i = 0; i < linklist.length; i++) {
        linklist[i].classList.remove("asc");
        linklist[i].classList.remove("desc");
        if (i == sort_col - 1) linklist[i].classList.add(sort_direction ? "asc" : "desc")
      };
      sort_cols[id] = sort_col;
      sort_directions[id] = sort_direction;
      return false;
    };

    function onToggle(a, id) {
      a.classList.toggle("open");
      document.getElementById(id).classList.toggle('hidden');
      return false;
    };

    function onToggleAll(a) {
      a.classList.toggle("open");
      var on = a.classList.contains("open");
      var linklist = document.getElementsByClassName("toggle");
      for (var i = 0; i < linklist.length; i++) {
        if (on != linklist[i].classList.contains("open")) linklist[i].click();
      };
      return false;
    };

    var sortfn = function(sort_col, sort_direction, a, b) {
      var v1 = (a.children[sort_col].hasAttribute("data-sort") ? a.children[sort_col].getAttribute("data-sort") : a.children[sort_col].innerText).toLowerCase();
      var v2 = (b.children[sort_col].hasAttribute("data-sort") ? b.children[sort_col].getAttribute("data-sort") : b.children[sort_col].innerText).toLowerCase();
      var result = String(v1).localeCompare(String(v2), undefined, {numeric: true});
      return sort_direction ? result : -result;
    };
  </script>
</head>
<body>
<table id="body_table">
<%
index_total = sum(x["size"] for x in stats.get("index", []))
table_total = sum(x["size"] for x in stats.get("table", []))
total = index_total + sum(x["size"] for x in stats.get("table", []))
rows_total = sum(x.get("count") or 0 for x in db.schema.get("table", {}).values())
rows_pref = "~" if rows_total and any(x.get("is_count_estimated") for x in db.schema["table"].values()) else ""
%>
<tr><td><table id="header_table">
  <tr>
    <td>
      <div id="title">{{ title }}</div><br />
      Source: <b>{{ db.name }}</b>.<br />
      Size: <b title="{{ stats.get("size", db.filesize) }}">{{ util.format_bytes(stats.get("size", db.filesize)) }}</b> (<span title="{{ stats.get("size", db.filesize) }}">{{ util.format_bytes(stats.get("size", db.filesize), max_units=False) }}</span>).<br />
%if db.schema.get("table"):
      <b>{{ util.plural("table", db.schema["table"]) }}</b>{{ ", " if stats or rows_total else "." }}
    %if stats:
      <span title="{{ table_total }}">{{ util.format_bytes(table_total) }}</span>{{ "" if rows_total else "." }}
    %endif
    %if rows_total:
(<span title="{{ rows_total }}">{{ util.plural("row", rows_total, sep=",", pref=rows_pref) }}</span>).
    %endif
      <br />
%endif
%if db.schema.get("index"):
      <b>{{ util.plural("index", db.schema["index"]) }}</b>{{ ", " if stats else "." }}
    %if stats:
      <span title="{{ index_total }}">{{ util.format_bytes(index_total) }}</span>.
    %endif
      <br />
%endif
%if db.schema.get("trigger"):
      <b>{{ util.plural("trigger", db.schema["trigger"]) }}</b>{{ ", " if db.schema.get("view") else "." }}
%endif
%if db.schema.get("view"):
      <b>{{ util.plural("view", db.schema["view"]) }}</b>.
%endif
%if db.schema.get("trigger") or db.schema.get("view"):
    <br />
%endif
    </td>
  </tr></table>
</td></tr><tr><td>

<div id="toggle_all">
  <a class="toggle" title="Toggle all sections opened or closed" onclick="onToggleAll(this)">Toggle all</a>
</div>

<div id="content_wrapper">

%if stats:

<div class="section">

  <h2><a class="toggle open" title="Toggle table sizes" onclick="onToggle(this, 'stats,table')">Table sizes</a></h2>
  <table class="stats" id="stats,table">
    <tr>
      <th></th>
      <th>Name</th>
      <th class="right">Size in bytes</th>
    </tr>
    %for item in sorted(stats["table"], key=lambda x: (-x["size"], x["name"].lower())):
    <tr>
      <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="table", size=item["size"], total=total)) }}</td>
      <td title="{{ item["name"] }}">{{ item["name"] }}</td>
      <td class="right" title="{{ util.format_bytes(item["size"]) }}">{{ util.format_bytes(item["size"], max_units=False, with_units=False) }}</td>
    </tr>
    %endfor
  </table>


    %if stats.get("index"):

<h2><a class="toggle open" title="Toggle table sizes with indexes" onclick="onToggle(this, 'stats,table,index')">Table sizes with indexes</a></h2>
<table class="stats" id="stats,table,index">
  <tr>
    <th></th>
    <th>Name</th>
    <th class="right">Size in bytes</th>
  </tr>
        %for item in sorted(stats["table"], key=lambda x: (-x["size_total"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="table", size=item["size_total"], total=total)) }}</td>
    <td title="{{ item["name"] }}">{{ item["name"] }}</td>
    <td class="right" title="{{ util.format_bytes(item["size_total"]) }}">{{ util.format_bytes(item["size_total"], max_units=False, with_units=False) }}</td>
  </tr>
        %endfor
</table>


<h2><a class="toggle open" title="Toggle table index sizes" onclick="onToggle(this, 'stats,index,table')">Table index sizes</a></h2>
<table class="stats" id="stats,index,table">
  <tr>
    <th></th>
    <th>Name</th>
    <th class="right">Size in bytes</th>
    <th class="right" title="Percentage of all indexes">Proportion</th>
  </tr>
        %for item in sorted([x for x in stats["table"] if "index" in x], key=lambda x: (-x["size_index"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="index", size=item["size_index"], total=total)) }}</td>
    <td title="{{ item["name"] }} ({{ len(item["index"]) }})">{{ item["name"] }} ({{ len(item["index"]) }})</td>
    <td class="right" title="{{ util.format_bytes(item["size_index"]) }}">{{ util.format_bytes(item["size_index"], max_units=False, with_units=False) }}</td>
    <td class="right">{{ int(round(100 * util.safedivf(item["size_index"], index_total))) }}%</td>
  </tr>
        %endfor
</table>

<h2><a class="toggle open" title="Toggle index sizes" onclick="onToggle(this, 'stats,index')">Index sizes</a></h2>
<table class="stats" id="stats,index">
  <tr>
    <th></th>
    <th>Name</th>
    <th>Table</th>
    <th class="right">Size in bytes</th>
    <th class="right" title="Percentage of all indexes">Proportion</th>
  </tr>
        %for item in sorted(stats["index"], key=lambda x: (-x["size"], x["name"].lower())):
  <tr>
    <td>{{! Template(templates.DATA_STATISTICS_ROW_PLOT_HTML).expand(dict(category="index", size=item["size"], total=total)) }}</td>
    <td title="{{ item["name"] }}">{{ item["name"] }}</td>
    <td title="{{ item["table"] }}">{{ item["table"] }}</td>
    <td class="right" title="{{ util.format_bytes(item["size"]) }}">{{ util.format_bytes(item["size"], max_units=False, with_units=False) }}</td>
    <td class="right">{{ int(round(100 * util.safedivf(item["size"], index_total))) }}%</td>
  </tr>
        %endfor
</table>

    %endif


</div>

%endif


<div class="section">

%for category in filter(db.schema.get, db.CATEGORIES):

<h2><a class="toggle open" title="Toggle {{ util.plural(category) }}" id="toggle_{{ category }}" onclick="onToggle(this, '{{ category }}')">{{ util.plural(category).capitalize() }}</a></h2>
<table class="content" id="{{ category }}">
  <tr>
		<th class="index">#</th>
    %for i, col in enumerate(COLS[category]):
		<th>
      <a class="sort" title="Sort by {{ grammar.quote(col, force=True) }}" onclick="onSort('{{ category }}', {{ i + 1 }})">{{ col }}</a>
    </th>
    %endfor
	</tr>
    %for itemi, item in enumerate(db.schema[category].values()):
<%
flags = {}
relateds = db.get_related(category, item["name"])
lks, fks = db.get_keys(item["name"]) if "table" == category else [(), ()]
%>
  <tr>
    <td class="index">{{ itemi + 1 }}</td>
    <td id="{{ category }}/{{! urllib.quote(item["name"], safe="") }}">
      <table class="subtable">
        <tr>
          <td title="{{ item["name"] }}">
            {{ item["name"] }}
          </td>
          <td>
            <a class="toggle" title="Toggle SQL" onclick="onToggle(this, '{{ category }}/{{! urllib.quote(item["name"], safe="") }}/sql')">SQL</a>
          </td>
        </tr>
      </table>
      <div class="sql hidden" id="{{ category }}/{{! urllib.quote(item["name"], safe="") }}/sql">
{{ db.get_sql(category, item["name"]) }}</div>

    </td>


        %if "table" == category:
<%
count = item["count"]
countstr = "{1}{0:,}".format(count, "~" if item.get("is_count_estimated") else "")
%>
    <td>
      <a class="toggle right" title="Toggle columns" onclick="onToggle(this, '{{ category }}/{{! urllib.quote(item["name"], safe="") }}/cols')">{{ len(item["columns"]) }}</a>
      <table class="hidden" id="{{ category }}/{{! urllib.quote(item["name"], safe="") }}/cols">
            %for col in item["columns"]:
        <tr><td>{{ col["name"] }}</td><td>{{ col.get("type", "") }}</td></tr>
            %endfor
      </table>
    </td>

    <td>
      <table class="subtable">
        <tr>
          <td>
<%
rels = [] # [(source, keys, target, keys)]
%>
            %for item2 in relateds.get("table", ()):
<%

lks2, fks2 = db.get_keys(item2["name"])
fmtkeys = lambda x: ("(%s)" if len(x) > 1 else "%s") % ", ".join(map(grammar.quote, x))
for col in lks2:
    for table, keys in col.get("table", {}).items():
        if util.lceq(table, item["name"]):
            rels.append((None, keys, item2["name"], col["name"]))
for col in fks2:
    for table, keys in col.get("table", {}).items():
        if util.lceq(table, item["name"]):
            rels.append((item2["name"], col["name"], None, keys))
%>
  <a href="#{{category}}/{{! urllib.quote(item2["name"], safe="") }}" title="Go to {{ category }} {{ grammar.quote(item2["name"], force=True) }}">{{ item2["name"] }}</a><br />
            %endfor
          </td>
            %if rels:
          <td>
            <a class="toggle" title="Toggle foreign keys" onclick="onToggle(this, '{{ category }}/{{! urllib.quote(item["name"], safe="") }}/related')">FKs</a>
          </td>
            %endif
        </tr>
      </table>

            %if rels:
      <div class="hidden" id="{{ category }}/{{! urllib.quote(item["name"], safe="") }}/related">
        <br />
                %for (a, c1, b, c2) in rels:
                    %if a:
        <a href="#table/{{! urllib.quote(a, safe="") }}" title="Go to table {{ grammar.quote(a, force=True) }}">{{ grammar.quote(a) }}</a>.{{ fmtkeys(c1) }} REFERENCES {{ fmtkeys(c2) }}<br />
                    %else:
        {{ fmtkeys(c1) }} REFERENCES <a href="#table/{{! urllib.quote(b, safe="") }}" title="Go to table {{ grammar.quote(b, force=True) }}">{{ grammar.quote(b) }}</a>.{{ fmtkeys(c2) }}<br />
                    %endif
                %endfor
        </div>
            %endif
    </td>

    <td>
            %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ())):
                %if "table" != item2["type"] and util.lceq(item2.get("tbl_name"), item["name"]):
<%
flags["has_direct"] = True
%>
  {{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urllib.quote(item2["name"], safe="") }}">{{ item2["name"] }}</a><br />
                %endif
            %endfor

            %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ())):
                %if "table" != item2["type"] and not util.lceq(item2.get("tbl_name"), item["name"]):
                    %if flags.get("has_direct") and not flags.get("has_indirect"):
  <br />
                    %endif
<%
flags["has_indirect"] = True
%>
  <em>{{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urllib.quote(item2["name"], safe="") }}">{{ item2["name"] }}</a></em><br />
                %endif
            %endfor
    </td>
    <td class="right nowrap" title="{{ count }}" data-sort="{{ count }}">
      {{ countstr }}
    </td>

            %if stats.get("table"):
<%
size = next((x["size_total"] for x in stats["table"] if util.lceq(x["name"], item["name"])), "")
%>
    <td class="right nowrap" title="{{ util.format_bytes(size) if size != "" else "" }}" data-sort="{{ size }}">
      {{ util.format_bytes(size, max_units=False, with_units=False) if size != "" else "" }}
    </td>
            %endif

        %endif


        %if "index" == category:
    <td>
      <a href="#table/{{! urllib.quote(item["tbl_name"], safe="") }}" title="Go to table {{ grammar.quote(item["tbl_name"], force=True) }}">{{ item["tbl_name"] }}</a>
    </td>
    <td>
            %for col in item["columns"]:
                %if col.get("expr"):
      <pre>{{ col["expr"] }}</pre>
                %else:
      {{ col["name"] }}
                %endif
      <br />
            %endfor
    </td>
            %if stats.get("index"):
<%
size = next((x["size"] for x in stats["index"] if util.lceq(x["name"], item["name"])), "")
%>
    <td class="right nowrap" title="{{ util.format_bytes(size) if size != "" else "" }}" data-sort="{{ size }}">
      {{ util.format_bytes(size, max_units=False, with_units=False) if size != "" else "" }}
    </td>
            %endif
        %endif


        %if "trigger" == category:
    <td>
<%
mycategory = "table" if "INSTEAD OF" != item.get("meta", {}).get("upon") else "view"
%>
      {{ mycategory }} <a href="#{{ mycategory }}/{{! urllib.quote(item["tbl_name"], safe="") }}" title="Go to {{ mycategory }} {{ grammar.quote(item["tbl_name"], force=True) }}">{{ item["tbl_name"] }}</a>
    </td>
    <td>
      {{ item.get("meta", {}).get("upon") }} {{ item.get("meta", {}).get("action") }}
            %if item.get("meta", {}).get("columns"):
      OF {{ ", ".join(grammar.quote(c["name"]) for c in item["meta"]["columns"]) }}
            %endif
    </td>
    <td>
            %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ())):
                %if not util.lceq(item2["name"], item["tbl_name"]):
  <em>{{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urllib.quote(item2["name"], safe="") }}">{{ item2["name"] }}</a></em><br />
                %endif
            %endfor
    </td>
        %endif


        %if "view" == category:
    <td>
      <a class="toggle" title="Toggle columns" onclick="onToggle(this, '{{ category }}/{{! urllib.quote(item["name"], safe="") }}/cols')">{{ len(item["columns"]) }}</a>
      <table class="hidden" id="{{ category }}/{{! urllib.quote(item["name"], safe="") }}/cols">
            %for col in item["columns"]:
        <tr><td>{{ col["name"] }}</td><td>{{ col.get("type", "") }}</td></tr>
            %endfor
      </table>
    </td>

    <td>
            %for item2 in (x for c in ("table", "view") for x in relateds.get(c, ()) if x["name"].lower() in item["meta"]["__tables__"]):
      {{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urllib.quote(item2["name"], safe="") }}">{{ item2["name"] }}</a><br />
            %endfor

            %for i, item2 in enumerate(x for c in ("trigger", ) for x in relateds.get(c, ()) if util.lceq(x.get("tbl_name"), item["name"])):
                %if not i:
      <br />
                %endif
      {{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urllib.quote(item2["name"], safe="") }}">{{ item2["name"] }}</a><br />
            %endfor

    </td>

    <td>
            %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ()) if item["name"].lower() in x["meta"]["__tables__"]):
      <em>{{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urllib.quote(item2["name"], safe="") }}">{{ item2["name"] }}</a></em><br />
            %endfor
    </td>
        %endif

  </tr>
    %endfor
</table>

%endfor

</div>


<div class="section">

<h2><a class="toggle" title="Toggle PRAGMAs" onclick="onToggle(this, 'pragma')">PRAGMA settings</a></h2>
<div class="hidden sql" id="pragma">
{{! Template(templates.PRAGMA_SQL).expand(pragma=pragma) }}
</div>


<h2><a class="toggle" title="Toggle full schema" onclick="onToggle(this, 'schema')">Full schema SQL</a></h2>
<div class="hidden sql" id="schema">
{{ sql }}
</div>

</div>


</div>
</td></tr></table>
<div id="footer">{{ templates.export_comment() }}</div>
</body>
</html>
"""



"""
Database statistics row plot for HTML exoprt.

@param   category  "table" or "index"
@param   size      item size
@param   total     total size
"""
DATA_STATISTICS_ROW_PLOT_HTML = """<%
from sqlitely import conf
from sqlitely.lib import util

width = 1.5 * conf.StatisticsPlotWidth
ratio = util.safedivf(size, total)
if 0.99 <= ratio < 1: ratio = 0.99
percent = int(round(100 * ratio))
text_cell1 = ("&nbsp;%d%%&nbsp;" % percent) if percent > 7 else ""
text_cell2 = "" if text_cell1 else '&nbsp;%d%%&nbsp;' % percent
if text_cell2 and percent:
    indent = percent + max(0, percent - 2) / 2
    text_cell2 = '<span style="left: -%dpx;">%s</span>' % (indent, text_cell2)
%>
<table class="plot {{ category }}"><tr>
  <td style="width: {{ percent }}%;">{{! text_cell1 }}</td>
  <td style="width: {{ 100 - percent }}%;">{{! text_cell2 }}</td>
</tr></table>
"""



"""
Text statistics export template.

@param   db           database.Database instance
@param   ?stats       {"table": [{name, size, size_total, ?size_index, ?index: []}],
                       "index": [{name, size, table}]}
"""
DATA_STATISTICS_TXT = """<%
import math
from sqlitely.lib.vendor.step import Template
from sqlitely.lib import util
from sqlitely import grammar, templates

COLS = {"table":   ["Name", "Columns", "Related tables", "Other relations", "Rows", "Size in bytes"]
                   if stats else ["Name", "Columns", "Related tables", "Other relations", "Rows"],
        "index":   ["Name", "Table", "Columns", "Size in bytes"] if stats else ["Name", "Table", "Columns"],
        "trigger": ["Name", "Owner", "When", "Uses"],
        "view":    ["Name", "Columns", "Uses", "Used by"], }
fmtkeys = lambda x: ("(%s)" if len(x) > 1 else "%s") % ", ".join(map(grammar.quote, x))

index_total = sum(x["size"] for x in stats["index"]) if stats else None
table_total = sum(x["size"] for x in stats["table"]) if stats else None
total = (index_total + sum(x["size"] for x in stats["table"])) if stats else None
rows_total = sum(x.get("count") or 0 for x in db.schema.get("table", {}).values())
rows_pref = "~" if rows_total and any(x.get("is_count_estimated") for x in db.schema["table"].values()) else ""

tblstext = idxstext = othrtext = ""
if db.schema.get("table"):
    tblstext = util.plural("table", db.schema["table"]) + (", " if stats else "" if rows_total else ".")
    if stats:
        tblstext += util.format_bytes(table_total) + ("" if rows_total else ".")
    if rows_total:
        tblstext += " (%s)." % util.plural("row", rows_total, sep=",", pref=rows_pref)
if db.schema.get("index"):
    idxstext = util.plural("index", db.schema["index"]) + (", " if stats else ".")
    if stats: idxstext += util.format_bytes(index_total)
if db.schema.get("trigger"):
      othrtext = util.plural("trigger", db.schema["trigger"]) + (", " if db.schema.get("view") else ".")
if db.schema.get("view"):
      othrtext += util.plural("view", db.schema["view"]) + "."
%>
Source: {{ db.name }}.
Size: {{ util.format_bytes(db.filesize) }} ({{ util.format_bytes(db.filesize, max_units=False) }}).
%if tblstext:
{{ tblstext }}
%endif
%if idxstext:
{{ idxstext }}
%endif
%if othrtext:
{{ othrtext }}
%endif

%if stats:
<%
items = sorted(stats["table"], key=lambda x: (-x["size"], x["name"].lower()))
cols = ["Name", "Size", "Bytes"]
vals = {x["name"]: (
    x["name"],
    util.format_bytes(x["size"]),
    util.format_bytes(x["size"], max_units=False, with_units=False),
) for x in items}
justs  = {0: 1, 1: 0, 2: 0}
%>
{{! Template(templates.DATA_STATISTICS_TABLE_TXT, strip=False).expand(dict(title="Table sizes", items=items, sizecol="size", cols=cols, vals=vals, justs=justs, total=total)) }}
    %if stats["index"]:
<%

items = sorted(stats["table"], key=lambda x: (-x["size_total"], x["name"].lower()))
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

items = sorted([x for x in stats["table"] if "index" in x], key=lambda x: (-x["size_index"], x["name"].lower()))
cols = ["Name", "Size", "Bytes", "Proportion"]
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

items = sorted(stats["index"], key=lambda x: (-x["size"], x["name"].lower()))
cols = ["Name", "Table", "Size", "Bytes", "Proportion"]
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
%endif
%for category in filter(db.schema.get, db.CATEGORIES):

{{ util.plural(category).capitalize() }}
<%
columns = COLS[category]
rows    = []

for item in db.schema.get(category).values():
    flags = {}
    relateds = db.get_related(category, item["name"])
    lks, fks = db.get_keys(item["name"]) if "table" == category else [(), ()]

    row = {"Name": item["name"]}
    if "table" == category:
        row["Columns"] = str(len(item["columns"]))

        count = item["count"]
        row["Rows"] = "{1}{0:,}".format(count, "~" if item.get("is_count_estimated") else "")

        if stats:
            size = next((x["size_total"] for x in stats["table"] if util.lceq(x["name"], item["name"])), "")
            row["Size in bytes"] = util.format_bytes(size, max_units=False, with_units=False) if size != "" else ""

        rels = [] # [(source, keys, target, keys)]
        for item2 in relateds.get("table", ()):
            lks2, fks2 = db.get_keys(item2["name"])
            for col in lks2:
                for table, keys in col.get("table", {}).items():
                    if util.lceq(table, item["name"]):
                        rels.append((None, keys, item2["name"], col["name"]))
            for col in fks2:
                for table, keys in col.get("table", {}).items():
                    if util.lceq(table, item["name"]):
                        rels.append((item2["name"], col["name"], None, keys))
        reltexts = []
        for (a, c1, b, c2) in rels:
            if a: s = "%s.%s REFERENCES %s" % (grammar.quote(a), fmtkeys(c1), fmtkeys(c2))
            else: s = "%s REFERENCES %s.%s" % (fmtkeys(c1), grammar.quote(b), fmtkeys(c2))
            reltexts.append(s)
        row["Related tables"] = reltexts or [""]

        othertexts = []
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ())):
            if "table" != item2["type"] and util.lceq(item2.get("tbl_name"), item["name"]):
                flags["has_direct"] = True
                s = "%s %s" % (item2["type"], grammar.quote(item2["name"]))
                othertexts.append(s)
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ())):
            if "table" != item2["type"] and not util.lceq(item2.get("tbl_name"), item["name"]):
                if flags.get("has_direct") and not flags.get("has_indirect"):
                    flags["has_indirect"] = True
                    s = "%s %s" % (item2["type"], grammar.quote(item2["name"]))
                    othertexts.append(s)
        row["Other relations"] = othertexts or [""]

    elif "index" == category:
        row["Table"] = item["tbl_name"]
        row["Columns"] = [c.get("expr", c.get("name")) for c in item["columns"]]
        if stats and stats.get("index"):
            size = next((x["size"] for x in stats["index"] if util.lceq(x["name"], item["name"])), "")
            row["Size in bytes"] = util.format_bytes(size, max_units=False, with_units=False) if size != "" else ""

    elif "trigger" == category:
        row["Owner"] = ("table" if "INSTEAD OF" != item.get("meta", {}).get("upon") else "view") + " " + grammar.quote(item["tbl_name"])
        row["When"] = "%s %s" % (item.get("meta", {}).get("upon"), item.get("meta", {}).get("action"))
        if item.get("meta", {}).get("columns"):
            row["When"] += " OF " + ", ".join(grammar.quote(c["name"]) for c in item["meta"]["columns"])
        usetexts = []
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ())):
            if not util.lceq(item2["name"], item["tbl_name"]):
                usetexts.append("%s %s" % (item2["type"], grammar.quote(item2["name"])))
        row["Uses"] = usetexts or [""]

    elif "view" == category:
        row["Columns"] = str(len(item["columns"]))

        usetexts = []
        for item2 in (x for c in ("table", "view") for x in relateds.get(c, ()) if x["name"].lower() in item["meta"]["__tables__"]):
            usetexts.append("%s %s" % (item2["type"], grammar.quote(item2["name"])))
        for i, item2 in enumerate(x for c in ("trigger", ) for x in relateds.get(c, ()) if util.lceq(x.get("tbl_name"), item["name"])):
            if not i:
                usetexts.append("")
                usetexts.append("%s %s" % (item2["type"], grammar.quote(item2["name"])))
        row["Uses"] = usetexts or [""]

        usedbytexts = []
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, ()) if item["name"].lower() in x["meta"]["__tables__"]):
            usedbytexts.append("%s %s" % (item2["type"], grammar.quote(item2["name"])))
        row["Used by"] = usedbytexts or [""]

    rows.append(row)

justs = {c: True for c in columns}
if "table" == category:
    justs.update({"Columns": False, "Rows": False, "Size in bytes": False})
elif "index" == category:
    justs.update({"Columns": False, "Size in bytes": False})
elif "view" == category:
    justs.update({"Columns": False})
widths = {c: max(len(c), max(len(x) for r in rows for x in util.tuplefy(r[c]))) for c in columns}

headers = []
for c in columns:
    headers.append((c.ljust if widths[c] else c.rjust)(widths[c]))
hr = "|-" + "-|-".join("".ljust(widths[c], "-") for c in columns) + "-|"
header = "| " + " | ".join(headers) + " |"
%>

{{ hr }}
{{ header }}
{{ hr }}
    %for row in rows:
<%
linecount = max(len(row[c]) if isinstance(row[c], list) else 1 for c in columns)
subrows = [[] for _ in range(linecount)]
for i, c in enumerate(columns):
    for j, v in enumerate(util.tuplefy(row[c]) + ("", ) * (linecount - len(util.tuplefy(row[c])))):
        subrows[j].append((v.ljust if justs[c] else v.rjust)(widths[c]))
%>
        %for subrow in subrows:
| {{ " | ".join(subrow) }} |
        %endfor
{{ hr }}
    %endfor
%endfor
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
        pad = pc.center(len(pad) - len(bar), pad[0]) + pad[0] * len(bar)
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

@param   db      database.Database instance
@param   stats   {"filesize": database size, "sql": "statistics CREATE SQL"}
"""
DATA_STATISTICS_SQL = """<%
from sqlitely.lib import util
from sqlitely import conf, templates

%>-- Output from sqlite3_analyzer.
-- Source: {{ db.name }}.
-- Size: {{ util.format_bytes(stats["filesize"]) }} ({{ util.format_bytes(stats["filesize"], max_units=False) }}).
-- {{ templates.export_comment() }}


{{! stats["sql"].replace("\\r", "") }}
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

is_initial = lambda o, v: o["initial"](db, v) if callable(o.get("initial")) else o.get("initial")
pragma_first = {k: v for k, v in pragma.items() if is_initial(db.PRAGMA[k], v)}
pragma_last  = {k: v for k, v in pragma.items() if not is_initial(db.PRAGMA[k], v)}
%>
-- Database dump.
-- Source: {{ db.name }}.
-- {{ templates.export_comment() }}
%if pragma_first:

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

{{! Template(templates.PRAGMA_SQL).expand(pragma=pragma_last) }}
"""



"""
Database PRAGMA statements SQL template.

@param   pragma   PRAGMA values as {name: value}
@param   ?schema  schema for PRAGMA directive, if any
"""
PRAGMA_SQL = """<%
from sqlitely import database, grammar

pragma = dict(pragma)
for name, opts in database.Database.PRAGMA.items():
    if opts.get("read") or opts.get("write") is False:
        pragma.pop(name, None)

lastopts, lastvalue, count = {}, None, 0
is_initial = lambda o, v: o["initial"](None, v) if callable(o.get("initial")) else o.get("initial")
sortkey = lambda (k, v, o): ((-1, not callable(o.get("initial"))) if is_initial(o, v)
                             else (1, 0) if callable(o.get("initial")) else (0, 0),
                             bool(o.get("deprecated")), o.get("label", k))
%>
%for name, value, opts in sorted(((k, pragma.get(k), o) for k, o in database.Database.PRAGMA.items()), key=sortkey):
<%
if name not in pragma:
    continue # for name, opts

%>
    %if is_initial(opts, value) and (not count or not is_initial(lastopts, lastvalue)):
-- BASE PRAGMAS:
    %elif opts.get("deprecated") and not lastopts.get("deprecated"):

-- DEPRECATED PRAGMAS:
    %elif callable(opts.get("initial")) and not is_initial(opts, value) and not callable(lastopts.get("initial")):

-- CLOSING PRAGMAS:
    %elif not opts.get("deprecated") and not is_initial(opts, value) and (not count or is_initial(lastopts, lastvalue)):

-- COMMON PRAGMAS:
    %endif
<%
lastopts, lastvalue = opts, value
if isinstance(value, basestring):
    value = '"%s"' % value.replace('"', '""')
elif isinstance(value, bool): value = str(value).upper()
%>

PRAGMA {{ ("%s." % grammar.quote(schema)) if isdef("schema") and schema else "" }}{{ name }} = {{ value }};
<%
count += 1
%>
%endfor
"""
