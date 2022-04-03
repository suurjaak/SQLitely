# -*- coding: utf-8 -*-
"""
HTML and TXT templates for exports and statistics.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    02.04.2022
------------------------------------------------------------------------------
"""
import datetime
import re

from six.moves import urllib

from . lib import util
from . import conf

# Modules imported inside templates:
#import base64, collections, itertools, json, logging, math, os, pyparsing, sys, six, wx, yaml
#from sqlitely import conf, grammar, images, searchparser, templates

"""Regex for matching unprintable characters (\x00 etc)."""
SAFEBYTE_RGX = re.compile(r"[\x00-\x1f\x7f-\xa0]")

"""Replacer callback for unprintable characters (\x00 etc)."""
SAFEBYTE_REPL = lambda m: m.group(0).encode("unicode-escape").decode("latin1")


def export_comment():
    """Returns export comment like "Exported with SQLitely on [DATETIME]"."""
    dt = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    return "Exported with %s on %s." % (conf.Title, dt)


@util.memoize
def urlquote(v): return urllib.parse.quote(util.to_str(v, "utf-8"), safe="")



"""
HTML data export template.

@param   db_filename  database path or temporary name
@param   title        export title
@param   columns      [{name}, ]
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
  <link rel="shortcut icon" type="image/png" href="data:image/png;base64,{{! images.Icon16x16_8bit.data }}"/>
  <style>
    * { font-family: Tahoma, DejaVu Sans; color: black; font-size: 11px; }
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
    a.toggle::after { content: ".. \\\\25b6"; font-size: 1.2em; }
    a.toggle.open::after { content: " \\\\25b2"; font-size: 0.7em; }
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
%for i, c in enumerate(columns):
    <th><a class="sort" title="Sort by {{ grammar.quote(c["name"]) }}" onclick="onSort({{ i + 1 }})">{{ util.unprint(c["name"]) }}</a></th>
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
@param   columns    [{name}, ]
@param   name       table name
@param   namespace  {"row_count"}
@param   ?progress  callback(count) returning whether to cancel, if any
"""
DATA_ROWS_HTML = """
<%
i = 0
progress = isdef("progress") and progress
%>
%for i, row in enumerate(rows, 1):
<%
namespace["row_count"] += 1
%><tr>
  <td class="index">{{ i }}</td>
%for c in columns:
  <td>{{ "" if row[c["name"]] is None else row[c["name"]] }}</td>
%endfor
</tr>
<%
if not i % 100 and not progress(count=i):
    break # for i, row
%>
%endfor
<%
if progress: progress(name=name, count=i)
%>
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
@param   columns    [{name}, ]
@param   name       table name
@param   ?namespace  {"row_count"}
@param   ?progress  callback(name, count) returning whether to cancel, if any
"""
DATA_ROWS_JSON = """<%
import collections, json
from sqlitely import templates

progress = isdef("progress") and progress
rows = iter(rows)
i, row, nextrow = 1, next(rows, None), next(rows, None)
indent = "  " if nextrow else ""
while row:
    if isdef("namespace"): namespace["row_count"] += 1
    data = collections.OrderedDict(((c["name"], row[c["name"]]) for c in columns))
    text = json.dumps(data, indent=2)
    echo("  " + text.replace("\\n", "\\n  ") + (",\\n" if nextrow else "\\n"))

    i, row, nextrow = i + 1, nextrow, next(rows, None)
    if not i % 100 and progress and not progress(count=i):
        break # while row
if progress: progress(name=name, count=i)
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
@param   columns    [{name, ?type}, ]
@param   name       table name
@param   ?namespace  {"row_count"}
@param   ?progress  callback(name, count) returning whether to cancel, if any
"""
DATA_ROWS_SQL = """<%
from sqlitely import grammar, templates

str_cols = ", ".join(grammar.quote(c["name"]) for c in columns)
progress = isdef("progress") and progress
%>
%for i, row in enumerate(rows, 1):
<%
if isdef("namespace"): namespace["row_count"] += 1
values = [grammar.format(row[c["name"]], c) for c in columns]
%>
INSERT INTO {{ name }} ({{ str_cols }}) VALUES ({{ ", ".join(values) }});
<%
if not i % 100 and progress and not progress(name=name, count=i):
    break # for i, row
%>
%endfor
<%
if progress: progress(name=name, count=i)
%>
"""



"""
TXT SQL update statements export template.

@param   rows       iterable
@param   originals  original rows iterable
@param   columns    [{name, ?type}, ]
@param   pks        [name, ]
@param   name       table name
"""
DATA_ROWS_UPDATE_SQL = """<%
from sqlitely import grammar, templates

str_cols = ", ".join(grammar.quote(c["name"]) for c in columns)
%>
%for row, original in zip(rows, originals):
<%
setstr = ", ".join("%s = %s" % (grammar.quote(c["name"]).encode("utf-8").decode("latin1"), grammar.format(row[c["name"]], c))
                   for c in columns if c["name"] not in pks or row[c["name"]] != original[c["name"]])
wherestr = " AND ".join("%s = %s" % (grammar.quote(c["name"]).encode("utf-8").decode("latin1"), grammar.format(original[c["name"]], c))
                       for c in columns if c["name"] in pks and c["name"] in original)
%>
UPDATE {{ name }} SET {{ setstr }}{{ (" WHERE " + wherestr) if wherestr else "" }};
%endfor
"""



"""
TXT data export template.

@param   db_filename   database path or temporary name
@param   title         export title
@param   columns       [{name}, ]
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
    fc = util.unprint(c["name"])
    headers.append((fc.ljust if columnjusts[c["name"]] else fc.rjust)(columnwidths[c["name"]]))
hr = "|-" + "-|-".join("".ljust(columnwidths[c["name"]], "-") for c in columns) + "-|"
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
@param   columns       [{name}, ]
@param   columnjusts   {col name: ljust or rjust}
@param   columnwidths  {col name: character width}
@param   name          table name
@param   ?namespace    {"row_count"}
@param   ?progress     callback(count) returning whether to cancel, if any
"""
DATA_ROWS_TXT = """<%
import six
from sqlitely import templates

progress = isdef("progress") and progress
%>
%for i, row in enumerate(rows, 1):
<%
values = []
if isdef("namespace"): namespace["row_count"] += 1
%>
    %for c in columns:
<%
raw = row[c["name"]]
value = "" if raw is None \
        else raw if isinstance(raw, six.string_types) else str(raw)
value = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, six.text_type(value))
values.append((value.ljust if columnjusts[c["name"]] else value.rjust)(columnwidths[c["name"]]))
%>
    %endfor
| {{ " | ".join(values) }} |
<%
if not i % 100 and progress and not progress(count=i):
    break # for i, row
%>
%endfor
<%
if progress: progress(name=name, count=i)
%>
"""



"""
TXT data export template for copying row as page.

@param   rows          iterable
@param   columns       [{name}, ]
"""
DATA_ROWS_PAGE_TXT = """<%
import six
from sqlitely.lib import util
from sqlitely import templates

fmtcols = [util.unprint(c["name"]) for c in columns]
colwidth = max(map(len, fmtcols))
%>
%for i, row in enumerate(rows):
    %if i:

    %endif
    %for c, fmtcol in zip(columns, fmtcols):
<%
raw = row[c["name"]]
value = "" if raw is None \
        else raw if isinstance(raw, six.string_types) else str(raw)
value = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, six.text_type(value))
%>
{{ fmtcol.ljust(colwidth) }} = {{ value }}
    %endfor
%endfor
"""



"""
YAML export template.

@param   title        export title
@param   db_filename  database path or temporary name
@param   row_count    number of rows
@param   sql          SQL query giving export data, if any
@param   create_sql   CREATE SQL statement for export object, if any
@param   data_buffer  iterable yielding rows data in text chunks
"""
DATA_YAML = """<%
from sqlitely.lib import util
from sqlitely import conf, templates

%># {{ title }}.
# Source: {{ db_filename }}.
# {{ templates.export_comment() }}
# {{ row_count }} {{ util.plural("row", row_count, numbers=False) }}.
%if sql:
#
# SQL: {{ sql.replace("\\n", "\\n#      ") }};
#
%endif
%if isdef("create_sql") and create_sql:
#
# {{ create_sql.rstrip(";").replace("\\n", "\\n#  ") }};
#
%endif

<%
for chunk in data_buffer:
    echo(chunk)
%>
"""



"""
YAML data export template for the rows part.

@param   rows          iterable
@param   columns       [{name}, ]
@param   name          table name
@param   ?namespace    {"row_count"}
@param   ?progress     callback(count) returning whether to cancel, if any
"""
DATA_ROWS_YAML = """<%
import yaml

progress = isdef("progress") and progress
for i, row in enumerate(rows, 1):
    if isdef("namespace"): namespace["row_count"] += 1
    for j, c in enumerate(columns):
        data = {c["name"]: row[c["name"]]}
        value = yaml.safe_dump([data], default_flow_style=False, width=1000)
        if j: value = "  " + value[2:]
        echo(value)
    if not i % 100 and progress and not progress(count=i):
        break # while row
if progress: progress(name=name, count=i)
%>"""



"""
YAML data export template for copying row as page.

@param   rows          iterable
@param   columns       [{name}, ]
@param   name          table name
"""
DATA_ROWS_PAGE_YAML = """<%
import yaml

flat = isinstance(rows, list) and len(rows) == 1
for i, row in enumerate(rows, 1):
    for j, c in enumerate(columns):
        data = {c["name"]: row[c["name"]]}
        value = yaml.safe_dump([data], default_flow_style=False, width=1000)
        if flat: value = "\\n".join(x[2:] for x in value.split("\\n"))
        elif j: value = "  " + value[2:]
        echo(value)
%>"""



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
from sqlitely.lib import util
from sqlitely import conf, grammar

wrap_b = lambda x: "<b>%s</b>" % x.group(0)
%>
<a name="{{ category }}">{{ category.capitalize() }}</a>
<a href="{{ category }}:{{ item["name"] }}"><font color="{{ conf.LinkColour }}">{{! pattern_replace.sub(wrap_b, escape(util.unprint(grammar.quote(item["name"])))) }}</font></a>:
<pre><font size="2">{{! pattern_replace.sub(wrap_b, escape(item["sql"])).replace(" ", "&nbsp;") }}</font></pre>
<br /><br />
"""



"""
HTML template for data search results header; start of HTML table.

@param   category  schema category
@param   item      schema category object
"""
SEARCH_ROW_DATA_HEADER_HTML = """<%
from sqlitely.lib import util
from sqlitely import conf, grammar
%>
<font color="{{ conf.FgColour }}">
<br /><br /><b><a name="{{ item["name"] }}">{{ category.capitalize() }} {{ util.unprint(grammar.quote(item["name"])) }}:</a></b><br />
<table border="1" cellpadding="4" cellspacing="0" width="100%">
<tr>
<th>#</th>
%for c in item["columns"]:
<th>{{ util.unprint(c["name"]) }}</th>
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
import six
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
%for c in item["columns"]:
<%
value = row[c["name"]]
value = value if value is not None else ""
value = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, six.text_type(value))
value = escape(value)

if not (keywords.get("column") and not match_kw("column", c)) \
and not (keywords.get("-column") and match_kw("-column", c)):
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
  <li>appdirs,
      <a href="https://pypi.org/project/appdirs/"><font color="{{ conf.LinkColour }}">pypi.org/project/appdirs</font></a></li>
  <li>openpyxl,
      <a href="https://pypi.org/project/openpyxl"><font color="{{ conf.LinkColour }}">
          pypi.org/project/openpyxl</font></a></li>
  <li>Pillow,
      <a href="https://pypi.org/project/Pillow"><font color="{{ conf.LinkColour }}">pypi.org/project/Pillow</font></a></li>
  <li>pyparsing,
      <a href="https://pypi.org/project/pyparsing/"><font color="{{ conf.LinkColour }}">pypi.org/project/pyparsing</font></a></li>
  <li>Python,
      <a href="https://www.python.org/"><font color="{{ conf.LinkColour }}">python.org</font></a></li>
  <li>pytz,
      <a href="https://pythonhosted.org/pytz/"><font color="{{ conf.LinkColour }}">pythonhosted.org/pytz</font></a></li>
  <li>PyYAML,
      <a href="https://pypi.org/project/PyYAML/"><font color="{{ conf.LinkColour }}">pypi.org/project/PyYAML</font></a></li>
  <li>six,
      <a href="https://pypi.org/project/six/"><font color="{{ conf.LinkColour }}">pypi.org/project/six</font></a></li>
  <li>SQLite,
      <a href="https://www.sqlite.org/"><font color="{{ conf.LinkColour }}">sqlite.org</font></a></li>
  <li>sqlite-parser,
      <a href="https://github.com/bkiers/sqlite-parser"><font color="{{ conf.LinkColour }}">github.com/bkiers/sqlite-parser</font></a></li>
  <li>step, Simple Template Engine for Python,
      <a href="https://github.com/dotpy/step"><font color="{{ conf.LinkColour }}">github.com/dotpy/step</font></a></li>
  <li>wxPython,
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
  <li>Nullsoft Scriptable Install System, <a href="https://nsis.sourceforge.io"><font color="{{ conf.LinkColour }}">nsis.sourceforge.io</font></a></li>
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
    <td nowrap="">{{ util.unprint(item["name"]) }}</td>
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
    <td nowrap="">{{ util.unprint(item["name"]) }}</td>
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
    <td nowrap="">{{ util.unprint(item["name"]) }} ({{ len(item["index"]) }})</td>
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
    <td nowrap="">{{ util.unprint(item["name"]) }}</td>
    <td nowrap="">{{ util.unprint(item["table"]) }}</td>
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
numtext = "%d" % round(percent)
text_cell1 = "&nbsp;%s%%&nbsp;" % numtext if (len(numtext) * 7 + 25 < ratio * conf.StatisticsPlotWidth) else ""
text_cell2 = "" if text_cell1 else "&nbsp;%s%%&nbsp;" % numtext
fgcolour = conf.PlotTableColour if "table" == category else conf.PlotIndexColour

%>
<table cellpadding="0" cellspacing="0" width="{{ conf.StatisticsPlotWidth }}"><tr>
  <td bgcolor="{{ fgcolour }}"
      width="{{ int(round(ratio * conf.StatisticsPlotWidth)) }}" align="center">
%if text_cell1:
    <font color="#FFFFFF" size="2"><b>{{! text_cell1 }}</b></font>
%endif
  </td>
  <td bgcolor="{{ conf.PlotBgColour }}" width="{{ int(round((1 - ratio) * conf.StatisticsPlotWidth)) }}">
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
@param   diagram      {"bmp": schema diagram as wx.Bitmap,
                       "svg": schema diagram as SVG string}
@param   stats        {"table":   [{name, size, size_total, ?size_index, ?index: []}],
                       "index":   [{name, size, table}],
"""
DATA_STATISTICS_HTML = """<%
import base64, math
from sqlitely.lib.vendor.step import Template
from sqlitely.lib import util
from sqlitely import conf, grammar, images, templates
from sqlitely.templates import urlquote

COLS = {"table":   ["Name", "Columns", "Related tables", "Other relations", "Rows", "Size in bytes"]
                   if stats else ["Name", "Columns", "Related tables", "Other relations", "Rows"],
        "index":   ["Name", "Table", "Columns", "Size in bytes"] if stats else ["Name", "Table", "Columns"],
        "trigger": ["Name", "Owner", "When", "Uses"],
        "view":    ["Name", "Columns", "Uses", "Used by"], }
COL_TOGGLES = {"table":   ["Name", "Columns", "Related tables"],
               "index":   ["Name"],
               "trigger": ["Name"],
               "view":    ["Name", "Columns"], }

@util.memoize(__key__="wrapclass")
def wrapclass(v):
    return ' class="nowrap"' if len(util.unprint(v or "")) < 30 else ""

%><!DOCTYPE HTML><html lang="en">
<head>
  <meta http-equiv='Content-Type' content='text/html;charset=utf-8' />
  <meta name="Author" content="{{ conf.Title }}">
  <title>{{ title }}</title>
  <link rel="shortcut icon" type="image/png" href="data:image/png;base64,{{! images.Icon16x16_8bit.data }}"/>
  <style>
    body {
      background: #8CBEFF;
      color: black;
      font-family: Tahoma, DejaVu Sans;
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
      position: relative;
    }
    div.section > h2:first-child {
      margin-top: 0;
    }
    #diagram { position: relative; }
    #diagram .img {
      max-width: 100%;
      padding-top: 10px;
    }
    #diagram .diagram-format {
      position: absolute;
      right: 0px;
      top: 0px;
    }
    #diagram .diagram-format a:hover { cursor: pointer; text-decoration: underline; }
    #diagram .diagram-format a.open { cursor: default; font-weight: bold; text-decoration: none; }
    table.stats > tbody > tr > th { text-align: left; white-space: nowrap; }
    table.stats > tbody > tr > td { text-align: left; white-space: nowrap; }
    table.stats > tbody > tr > td:nth-child(n+2) {
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .right { text-align: right !important; }
    .name { word-break: break-all; overflow-wrap: anywhere; }
    .nowrap { word-break: normal !important; overflow-wrap: normal !important; }
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
    table.content td { vertical-align: top; }
    table.content > tbody > tr > td {
      border: 1px solid #C0C0C0;
      line-height: 1.5em;
      padding: 5px;
      position: relative;
      word-break: break-all;
      overflow-wrap: anywhere;
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
    div.sql { font-family: monospace; text-align: left; white-space: pre-wrap; word-break: break-all; overflow-wrap: anywhere; }
    a.sort:hover, a.toggle:hover { cursor: pointer; text-decoration: none; }
    a.toggle { display: inline-block; white-space: nowrap; }
    a.toggle::after { content: " \\\\25b6"; }
    a.toggle.open::after { content: " \\\\25bc"; }
    a.toggle.right { display: block; text-align: right; }
    .hidden { display: none; }
    div.toggle.header { text-align: right; }
    div.section div.toggle.header { position: absolute; right: 5px; top: 5px; }
    a.sort { display: inline-block; }
    a.sort::after      { content: ""; display: inline-block; min-width: 10px; text-align: left; position: relative; left: 3px; top: -1px; }
    a.sort.asc::after  { content: "↓"; }
    a.sort.desc::after { content: "↑"; }
    th a.sort:only-child { display: block; }
    th a.toggle { display: inline-block; }
    #footer {
      text-align: center;
      padding-bottom: 10px;
      color: #666;
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

    function onToggleSection(a, id) {
      a.classList.toggle("open");
      var on = a.classList.contains("open");
      if (id) var section = document.getElementById(id);
      else {
        var ptr = a.parentElement;
        while (ptr && (ptr.tagName != "DIV" || !ptr.classList.contains("section")))
          ptr = ptr.parentElement;
        var section = (ptr && ptr.tagName == "DIV" && ptr.classList.contains("section")) ? ptr : null;
      }
      var linklist = section ? section.querySelectorAll("a.toggle") : [];
      for (var i = 0; i < linklist.length; i++) {
        if (on != linklist[i].classList.contains("open")) linklist[i].click();
      };
      return false;
    };

    function onToggleColumn(a, id, col) {
      a.classList.toggle("open");
      var on = a.classList.contains("open");

      var selector = "table#" + id + " > tbody > tr > td:nth-child(" + (col + 1) + ") a.toggle";
      var table = document.getElementById(id);
      var linklist = table.querySelectorAll(selector);
      for (var i = 0; i < linklist.length; i++) {
        if (on != linklist[i].classList.contains("open")) linklist[i].click();
      };
      return false;
    };

    function onSwitch(a1, id1, aid2, id2) {
      var on = a1.classList.contains("open");
      var a2 = document.getElementById(aid2);
      var e1 = document.getElementById(id1);
      var e2 = document.getElementById(id2);
      a1.classList.toggle("open");
      a2.classList.toggle("open");
      e1.classList.toggle("hidden");
      e2.classList.toggle("hidden");
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
has_rows = any(x.get("count") or 0 for x in db.schema.get("table", {}).values())
dt_created, dt_modified = (dt.strftime("%d.%m.%Y %H:%M") if dt else None
                           for dt in (db.date_created, db.last_modified))
%>
<tr><td><table id="header_table">
  <tr>
    <td>
      <div id="title">{{ title }}</div><br />
      Source: <b>{{ db.name }}</b>.<br />
      Size: <b title="{{ stats.get("size", db.filesize) }}">{{ util.format_bytes(stats.get("size", db.filesize)) }}</b> (<span title="{{ stats.get("size", db.filesize) }}">{{ util.format_bytes(stats.get("size", db.filesize), max_units=False) }}</span>).<br />
%if dt_created and dt_modified and dt_created != dt_modified:
      Date: <b>{{ dt_modified }}</b> (created <b>{{ dt_created }}</b>).<br />
%elif dt_modified:
      Date: <b>{{ dt_modified }}</b>.<br />
%elif dt_created:
      Date: created <b>{{ dt_created }}</b>.<br />
%endif
%if db.schema.get("table"):
      <b>{{ util.plural("table", db.schema["table"]) }}</b>{{ ", " if stats or has_rows else "." }}
    %if stats:
      <span title="{{ table_total }}">{{ util.format_bytes(table_total) }}</span>{{ "" if has_rows else "." }}
    %endif
    %if has_rows:
(<span title="{{ util.count(list(db.schema["table"].values())) }}">{{ util.count(list(db.schema["table"].values()), "row") }}</span>).
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

<div class="toggle header">
  <a class="toggle" title="Toggle all sections opened or closed" onclick="onToggleSection(this, 'content_wrapper')">Toggle all</a>
</div>

<div id="content_wrapper">


%if isdef("diagram") and diagram:
<div class="section">

  <h2><a class="toggle" title="Toggle diagram" onclick="onToggle(this, 'diagram')">Schema diagram</a></h2>
  <div id="diagram" class="hidden">

    %if diagram.get("bmp") and diagram.get("svg"):
    <div class="diagram-format">
      <a id="diagram-png-link" title="Show schema diagram as PNG" onclick="onSwitch(this, 'diagram-png', 'diagram-svg-link', 'diagram-svg')" class="open">PNG</a>
      <a id="diagram-svg-link" title="Show schema diagram as SVG" onclick="onSwitch(this, 'diagram-svg', 'diagram-png-link', 'diagram-png')">SVG</a>
    </div>
    %endif

    %if diagram.get("bmp"):
    <img id="diagram-png" class="img" title="Schema diagram" alt="Schema diagram" src="data:image/png;base64,{{! base64.b64encode(util.img_wx_to_raw(diagram["bmp"])) }}" />
    %endif
    %if diagram.get("svg"):
    <div id="diagram-svg" class="img hidden">
{{! diagram["svg"] }}
    </div>
    %endif
  </div>
</div>
%endif


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
      <td title="{{ item["name"] }}">{{ util.unprint(item["name"]) }}</td>
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
    <td title="{{ item["name"] }}">{{ util.unprint(item["name"]) }}</td>
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
    <td title="{{ item["name"] }} ({{ len(item["index"]) }})">{{ util.unprint(item["name"]) }} ({{ len(item["index"]) }})</td>
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
    <td title="{{ item["name"] }}">{{ util.unprint(item["name"]) }}</td>
    <td title="{{ item["table"] }}">{{ item["table"] }}</td>
    <td class="right" title="{{ util.format_bytes(item["size"]) }}">{{ util.format_bytes(item["size"], max_units=False, with_units=False) }}</td>
    <td class="right">{{ int(round(100 * util.safedivf(item["size"], index_total))) }}%</td>
  </tr>
        %endfor
</table>

    %endif

<div class="toggle header">
  <a class="toggle" title="Toggle section opened or closed" onclick="onToggleSection(this)">Toggle all</a>
</div>

</div>

%endif


%if any(db.schema.values()):

<div class="section">

    %for category in filter(db.schema.get, db.CATEGORIES):

<h2><a class="toggle open" title="Toggle {{ util.plural(category) }}" id="toggle_{{ category }}" onclick="onToggle(this, '{{ category }}')">{{ util.plural(category).capitalize() }}</a></h2>
<table class="content" id="{{ category }}">
  <tr>
		<th class="index">#</th>
        %for i, col in enumerate(COLS[category]):
		<th>
      <a class="sort" title="Sort by {{ grammar.quote(col, force=True) }}" onclick="onSort('{{ category }}', {{ i + 1 }})">{{ col }}</a>
            %if col in COL_TOGGLES[category]:
      <a class="toggle" title="Toggle all rows in column" onclick="onToggleColumn(this, '{{ category }}', {{ i + 1 }})"> </a>
            %endif
    </th>
        %endfor
	</tr>
        %for itemi, item in enumerate(db.schema[category].values()):
<%
flags = {}
relateds = db.get_related(category, item["name"])
%>
  <tr>
    <td class="index">{{ itemi + 1 }}</td>
    <td id="{{ category }}/{{! urlquote(item["name"]) }}">
      <table class="subtable">
        <tr>
          <td title="{{ item["name"] }}" {{! wrapclass(item["name"]) }}>
            {{ util.unprint(item["name"]) }}
          </td>
          <td>
            <a class="toggle" title="Toggle SQL" onclick="onToggle(this, '{{ category }}/{{! urlquote(item["name"]) }}/sql')">SQL</a>
          </td>
        </tr>
      </table>
      <div class="sql hidden" id="{{ category }}/{{! urlquote(item["name"]) }}/sql">
{{ db.get_sql(category, item["name"]) }}</div>

    </td>


            %if "table" == category:
<%
count = item["count"]
countstr = util.count(item)
%>
    <td>
      <a class="toggle right" title="Toggle columns" onclick="onToggle(this, '{{ category }}/{{! urlquote(item["name"]) }}/cols')">{{ len(item["columns"]) }}</a>
      <table class="hidden" id="{{ category }}/{{! urlquote(item["name"]) }}/cols">
                %for c in item["columns"]:
        <tr><td {{! wrapclass(c["name"]) }}>{{ util.unprint(c["name"]) }}</td><td {{! wrapclass(c.get("type")) }}>{{ util.unprint(c.get("type", "")) }}</td></tr>
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
                %for item2 in relateds.get("table", {}).values():
<%

lks2, fks2 = db.get_keys(item2["name"])
fmtkeys = lambda x: ("(%s)" if len(x) > 1 else "%s") % ", ".join(map(util.unprint, map(grammar.quote, x)))
for col in lks2:
    for table, keys in col.get("table", {}).items():
        if util.lceq(table, item["name"]):
            rels.append((None, keys or [], item2["name"], col["name"]))
for col in fks2:
    for table, keys in col.get("table", {}).items():
        if util.lceq(table, item["name"]):
            rels.append((item2["name"], col["name"], None, keys or []))
%>
  <a href="#{{category}}/{{! urlquote(item2["name"]) }}" title="Go to {{ category }} {{ grammar.quote(item2["name"], force=True) }}" {{! wrapclass(item2["name"]) }}>{{ item2["name"] }}</a><br />
                %endfor
          </td>
                %if rels:
          <td>
            <a class="toggle" title="Toggle foreign keys" onclick="onToggle(this, '{{ category }}/{{! urlquote(item["name"]) }}/related')">FKs</a>
          </td>
                %endif
        </tr>
      </table>

                %if rels:
      <div class="hidden" id="{{ category }}/{{! urlquote(item["name"]) }}/related">
        <br />
                    %for (a, c1, b, c2) in rels:
                        %if a:
        <a href="#table/{{! urlquote(a) }}" title="Go to table {{ grammar.quote(a, force=True) }}" {{! wrapclass(a) }}>{{ util.unprint(grammar.quote(a)) }}</a>{{ "." if c1 else "" }}{{ fmtkeys(c1) }} <span class="nowrap">REFERENCES</span> {{ fmtkeys(c2) }}<br />
                        %else:
        {{ fmtkeys(c1) }} <span class="nowrap">REFERENCES</span> <a href="#table/{{! urlquote(b) }}" title="Go to table {{ util.unprint(grammar.quote(b, force=True)) }}" {{! wrapclass(b) }}>{{ grammar.quote(b) }}</a>{{ "." if c2 else "" }}{{ fmtkeys(c2) }}<br />
                        %endif
                    %endfor
        </div>
                %endif
    </td>

    <td>
                %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values()):
                    %if "table" != item2["type"] and util.lceq(item2.get("tbl_name"), item["name"]):
<%
flags["has_direct"] = True
%>
  {{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urlquote(item2["name"]) }}" {{! wrapclass(item2["name"]) }}>{{ util.unprint(item2["name"]) }}</a><br />
                    %endif
                %endfor

                %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values()):
                    %if "table" != item2["type"] and not util.lceq(item2.get("tbl_name"), item["name"]):
                        %if flags.get("has_direct") and not flags.get("has_indirect"):
  <br />
                        %endif
<%
flags["has_indirect"] = True
%>
  <em>{{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urlquote(item2["name"]) }}" {{! wrapclass(item2["name"]) }}>{{ util.unprint(item2["name"]) }}</a></em><br />
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
      <a href="#table/{{! urlquote(item["tbl_name"]) }}" title="Go to table {{ grammar.quote(item["tbl_name"], force=True) }}">{{ item["tbl_name"] }}</a>
    </td>
    <td>
                %for col in item["columns"]:
                    %if col.get("expr"):
      <pre>{{ col["expr"] }}</pre>
                    %else:
      {{ util.unprint(col["name"] or "") }}
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
mycategory = "view" if item["tbl_name"] in db.schema["view"] else "table"
%>
      {{ mycategory }} <a href="#{{ mycategory }}/{{! urlquote(item["tbl_name"]) }}" title="Go to {{ mycategory }} {{ grammar.quote(item["tbl_name"], force=True) }}" {{! wrapclass(item["tbl_name"]) }}>{{ util.unprint(item["tbl_name"]) }}</a>
    </td>
    <td>
      {{ item.get("meta", {}).get("upon", "") }} {{ item.get("meta", {}).get("action", "") }}
                %if item.get("meta", {}).get("columns"):
      OF {{ ", ".join(grammar.quote(c["name"]) for c in item["meta"]["columns"]) }}
                %endif
    </td>
    <td>
                %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values()):
                    %if not util.lceq(item2["name"], item["tbl_name"]):
  <em>{{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urlquote(item2["name"]) }}" {{! wrapclass(item2["name"]) }}>{{ util.unprint(item2["name"]) }}</a></em><br />
                    %endif
                %endfor
    </td>
            %endif


            %if "view" == category:
    <td>
      <a class="toggle" title="Toggle columns" onclick="onToggle(this, '{{ category }}/{{! urlquote(item["name"]) }}/cols')">{{ len(item["columns"]) }}</a>
      <table class="hidden" id="{{ category }}/{{! urlquote(item["name"]) }}/cols">
                %for col in item["columns"]:
        <tr><td {{! wrapclass(col["name"]) }}>{{ util.unprint(col["name"]) }}</td><td {{! wrapclass(col.get("type")) }}>{{ util.unprint(col.get("type", "")) }}</td></tr>
                %endfor
      </table>
    </td>

    <td>
                %for item2 in (x for c in ("table", "view") for x in relateds.get(c, {}).values() if x["name"].lower() in item["meta"]["__tables__"]):
      {{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urlquote(item2["name"]) }}" {{! wrapclass(item2["name"]) }}>{{ util.unprint(item2["name"]) }}</a><br />
                %endfor

                %for i, item2 in enumerate(x for c in ("trigger", ) for x in relateds.get(c, {}).values() if util.lceq(x.get("tbl_name"), item["name"])):
                    %if not i:
      <br />
                    %endif
      {{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urlquote(item2["name"]) }}" {{! wrapclass(item2["name"]) }}>{{ util.unprint(item2["name"]) }}</a><br />
                %endfor

    </td>

    <td>
                %for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values() if item["name"].lower() in x["meta"]["__tables__"]):
      <em>{{ item2["type"] }} <a title="Go to {{ item2["type"] }} {{ grammar.quote(item2["name"], force=True) }}" href="#{{ item2["type"] }}/{{! urlquote(item2["name"]) }}" {{! wrapclass(item2["name"]) }}>{{ util.unprint(item2["name"]) }}</a></em><br />
                %endfor
    </td>
            %endif

  </tr>
        %endfor
</table>

    %endfor

<div class="toggle header">
  <a class="toggle" title="Toggle section opened or closed" onclick="onToggleSection(this)">Toggle all</a>
</div>

</div>

%endif


%if pragma or sql:

<div class="section">

    %if pragma:
<h2><a class="toggle" title="Toggle PRAGMAs" onclick="onToggle(this, 'pragma')">PRAGMA settings</a></h2>
<div class="hidden sql" id="pragma">
{{! Template(templates.PRAGMA_SQL).expand(pragma=pragma) }}
</div>
    %endif


    %if sql:
<h2><a class="toggle" title="Toggle full schema" onclick="onToggle(this, 'schema')">Full schema SQL</a></h2>
<div class="hidden sql" id="schema">
{{ sql }}
</div>
    %endif

<div class="toggle header">
  <a class="toggle" title="Toggle section opened or closed" onclick="onToggleSection(this)">Toggle all</a>
</div>

</div>

%endif


</div>
</td></tr></table>
<div id="footer">{{ templates.export_comment() }}</div>
</body>
</html>
"""



"""
Database statistics row plot for HTML export.

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
fmtkeys = lambda x: ("(%s)" if len(x) > 1 else "%s") % ", ".join(map(util.unprint, map(grammar.quote, x)))

index_total = sum(x["size"] for x in stats["index"]) if stats else None
table_total = sum(x["size"] for x in stats["table"]) if stats else None
total = (index_total + sum(x["size"] for x in stats["table"])) if stats else None
has_rows = any(x.get("count") or 0 for x in db.schema.get("table", {}).values())
dt_created, dt_modified = (dt.strftime("%d.%m.%Y %H:%M") if dt else None
                           for dt in (db.date_created, db.last_modified))

tblstext = idxstext = othrtext = ""
if db.schema.get("table"):
    tblstext = util.plural("table", db.schema["table"]) + (", " if stats else "" if has_rows else ".")
    if stats:
        tblstext += util.format_bytes(table_total) + ("" if has_rows else ".")
    if has_rows:
        tblstext += " (%s)." % util.count(db.schema.get("table", {}).values(), "row")
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
%if dt_created and dt_modified and dt_created != dt_modified:
Date: {{ dt_modified }} (created {{ dt_created }}).
%elif dt_modified:
Date: {{ dt_modified }}.
%elif dt_created:
Date: created {{ dt_created }}.
%endif
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
    util.unprint(x["name"]),
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
    util.unprint(x["name"]),
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
    "%s (%s)" % (util.unprint(x["name"]), len(x["index"])),
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
    util.unprint(x["name"]),
    util.unprint(x["table"]),
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

    row = {"Name": util.unprint(item["name"])}
    if "table" == category:
        row["Columns"] = str(len(item["columns"]))

        row["Rows"] = util.count(item)

        if stats:
            size = next((x["size_total"] for x in stats["table"] if util.lceq(x["name"], item["name"])), "")
            row["Size in bytes"] = util.format_bytes(size, max_units=False, with_units=False) if size != "" else ""

        rels = [] # [(source, keys, target, keys)]
        for item2 in relateds.get("table", {}).values():
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
            if a: s = "%s%s%s REFERENCES %s" % (util.unprint(grammar.quote(a)), "." if c1 else "", fmtkeys(c1), fmtkeys(c2))
            else: s = "%s REFERENCES %s%s%s" % (fmtkeys(c1), util.unprint(grammar.quote(b)), "." if c2 else "", fmtkeys(c2))
            reltexts.append(s)
        row["Related tables"] = reltexts or [""]

        othertexts = []
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values()):
            if "table" != item2["type"] and util.lceq(item2.get("tbl_name"), item["name"]):
                flags["has_direct"] = True
                s = "%s %s" % (item2["type"], util.unprint(grammar.quote(item2["name"])))
                othertexts.append(s)
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values()):
            if "table" != item2["type"] and not util.lceq(item2.get("tbl_name"), item["name"]):
                if flags.get("has_direct") and not flags.get("has_indirect"):
                    flags["has_indirect"] = True
                    s = "%s %s" % (item2["type"], util.unprint(grammar.quote(item2["name"])))
                    othertexts.append(s)
        row["Other relations"] = othertexts or [""]

    elif "index" == category:
        row["Table"] = item["tbl_name"]
        row["Columns"] = [c.get("expr", util.unprint(c.get("name") or "")) for c in item["columns"]]
        if stats and stats.get("index"):
            size = next((x["size"] for x in stats["index"] if util.lceq(x["name"], item["name"])), "")
            row["Size in bytes"] = util.format_bytes(size, max_units=False, with_units=False) if size != "" else ""

    elif "trigger" == category:
        row["Owner"] = ("view" if item["tbl_name"] in db.schema["view"] else "table") + " " + util.unprint(grammar.quote(item["tbl_name"]))
        row["When"] = " ".join(filter(bool, (item.get("meta", {}).get(k, "") for k in ("upon", "action"))))
        if item.get("meta", {}).get("columns"):
            row["When"] += " OF " + ", ".join(util.unprint(grammar.quote(c["name"])) for c in item["meta"]["columns"])
        usetexts = []
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values()):
            if not util.lceq(item2["name"], item["tbl_name"]):
                usetexts.append("%s %s" % (item2["type"], util.unprint(grammar.quote(item2["name"]))))
        row["Uses"] = usetexts or [""]

    elif "view" == category:
        row["Columns"] = str(len(item["columns"]))

        usetexts = []
        for item2 in (x for c in ("table", "view") for x in relateds.get(c, {}).values() if x["name"].lower() in item["meta"]["__tables__"]):
            usetexts.append("%s %s" % (item2["type"], util.unprint(grammar.quote(item2["name"]))))
        for i, item2 in enumerate(x for c in ("trigger", ) for x in relateds.get(c, {}).values() if util.lceq(x.get("tbl_name"), item["name"])):
            if not i:
                usetexts.append("")
                usetexts.append("%s %s" % (item2["type"], util.unprint(grammar.quote(item2["name"]))))
        row["Uses"] = usetexts or [""]

        usedbytexts = []
        for item2 in (x for c in db.CATEGORIES for x in relateds.get(c, {}).values() if item["name"].lower() in x["meta"]["__tables__"]):
            usedbytexts.append("%s %s" % (item2["type"], util.unprint(grammar.quote(item2["name"]))))
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
    cf = util.unprint(c)
    headers.append((cf.ljust if widths[c] else cf.rjust)(widths[c]))
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

filesize = stats.get("size", db.filesize)
dt_created, dt_modified = (dt.strftime("%d.%m.%Y %H:%M") if dt else None
                           for dt in (db.date_created, db.last_modified))

%>-- Output from sqlite3_analyzer.
-- Source: {{ db.name }}.
-- Size: {{ util.format_bytes(filesize) }} ({{ util.format_bytes(filesize, max_units=False) }}).
%if dt_created and dt_modified and dt_created != dt_modified:
-- Date: {{ dt_modified }} (created {{ dt_created }}).
%elif dt_modified:
-- Date: {{ dt_modified }}.
%elif dt_created:
-- Date: created {{ dt_created }}.
%endif
-- {{ templates.export_comment() }}


{{! stats.get("sql", "-- sqlite3_analyzer result unavailable.").replace("\\r", "") }}
"""



"""
Database dump SQL template.

@param   db         database.Database instance
@param   sql        schema SQL
@param   data       [{name, columns, rows}]
@param   pragma     PRAGMA values as {name: value}
@param   buffer     file or file-like buffer being written to
@param   ?progress  callback(count) returning whether to cancel, if any
"""
DUMP_SQL = """<%
import itertools, logging
from sqlitely.lib import util
from sqlitely.lib.vendor.step import Template
from sqlitely import grammar, templates

logger = logging.getLogger("sqlitely")

is_initial = lambda o, v: o["initial"](db, v) if callable(o.get("initial")) else o.get("initial")
pragma_first = {k: v for k, v in pragma.items() if is_initial(db.PRAGMA[k], v)}
pragma_last  = {k: v for k, v in pragma.items() if not is_initial(db.PRAGMA[k], v)}
progress = isdef("progress") and progress
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
try:
    row = next(table["rows"], None)
    if not row: continue # for table
    rows = itertools.chain([row], table["rows"])
except Exception as e:
    logger.exception("Error exporting table %s from %s.", grammar.quote(table["name"]), db)
    if progress and not progress(name=table["name"], error=util.format_exc(e)):
        break # for table
    else: continue # for table
%>

-- Table {{ grammar.quote(table["name"], force=True) }} data:
<%
try:
    Template(templates.DATA_ROWS_SQL).stream(buffer, dict(table, progress=progress, rows=rows))
except Exception as e:
    logger.exception("Error exporting table %s from %s.", grammar.quote(table["name"]), db)
    if progress and not progress(name=table["name"], error=util.format_exc(e)):
        break # for table
%>

%endfor

{{! Template(templates.PRAGMA_SQL).expand(pragma=pragma_last) }}
"""



"""
Database PRAGMA statements SQL template.

@param   pragma   PRAGMA values as {name: value}
@param   ?schema  schema for PRAGMA directive, if any
"""
PRAGMA_SQL = """<%
import six
from sqlitely import database, grammar

pragma = dict(pragma)
for name, opts in database.Database.PRAGMA.items():
    if opts.get("read") or opts.get("write") is False:
        pragma.pop(name, None)

lastopts, lastvalue, count = {}, None, 0
is_initial = lambda o, v: o["initial"](None, v) if callable(o.get("initial")) else o.get("initial")
def sortkey(x):
    k, v, o = x
    return ((-1, not callable(o.get("initial"))) if is_initial(o, v)
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
if isinstance(value, six.string_types):
    value = '"%s"' % value.replace('"', '""')
elif isinstance(value, bool): value = str(value).upper()
%>

PRAGMA {{ ("%s." % grammar.quote(schema)) if isdef("schema") and schema else "" }}{{ name }} = {{ value }};
<%
count += 1
%>
%endfor
"""



"""
Database schema diagram SVG template.

@param   fonts        {"normal": wx.Font, "bold": wx.Font}
@param   get_extent   function(text, font=current dc font) returning full text extent
@param   items        diagram objects as [{"name", "type", "bounds", "columns", "stats"}]
@param   lines        diagram relations as {("item1", "item2", ("col1", )): {"name", "pts"}}
@param   show_labels  whether to show foreign relation labels
@param   ?title       diagram title
@param   ?embed       whether to omit full XML headers and provide links for embedding in HTML
"""
DIAGRAM_SVG = """<%
from sqlitely.lib import util
from sqlitely.lib.controls import ColourManager
from sqlitely.components   import SchemaDiagram
from sqlitely import grammar, images, templates
from sqlitely.templates import urlquote
import wx

CRADIUS     = 1
MARGIN      = 10
wincolour   = SchemaDiagram.DEFAULT_COLOURS[wx.SYS_COLOUR_WINDOW]
wtextcolour = SchemaDiagram.DEFAULT_COLOURS[wx.SYS_COLOUR_WINDOWTEXT]
gtextcolour = SchemaDiagram.DEFAULT_COLOURS[wx.SYS_COLOUR_GRAYTEXT]
btextcolour = SchemaDiagram.DEFAULT_COLOURS[wx.SYS_COLOUR_BTNTEXT]
gradcolour  = SchemaDiagram.COLOUR_GRAD_TO
fontsize    = SchemaDiagram.FONT_SIZE + 3
texth       = SchemaDiagram.FONT_SIZE + 2

bounds = None
# Calculate item widths and heights
MINW, MINH = SchemaDiagram.MINW, SchemaDiagram.HEADERH + SchemaDiagram.HEADERP + SchemaDiagram.FOOTERH
itemcoltexts, itemcolmax = {}, {} # {item name: [[name, type], ]}, {item name: {"name", "type"}}
for item in items:
    # Measure title width
    ititle = util.ellipsize(util.unprint(item["name"]), SchemaDiagram.MAX_TITLE)
    extent = get_extent(ititle, fonts["bold"]) # (w, h, descent, lead)
    w, h = max(MINW, extent[0] + extent[3] + 2 * SchemaDiagram.HPAD), MINH

    cols = item.get("columns") or []
    colmax = itemcolmax[item["name"]] = {"name": 0, "type": 0}
    coltexts = itemcoltexts[item["name"]] = [] # [[name, type]]
    for i, c in enumerate(cols):
        coltexts.append([])
        for k in ["name", "type"]:
            v = c.get(k)
            t = util.ellipsize(util.unprint(c.get(k, "")), SchemaDiagram.MAX_TEXT)
            coltexts[-1].append(t)
            if t: extent = get_extent(t)
            if t: colmax[k] = max(colmax[k], extent[0] + extent[3])

    w = max(w, SchemaDiagram.LPAD + 2 * SchemaDiagram.HPAD + sum(colmax.values()))
    h += SchemaDiagram.LINEH * len(item.get("columns") or [])
    if item.get("stats"): h += SchemaDiagram.STATSH - SchemaDiagram.FOOTERH

    item["bounds"] = wx.Rect(item["bounds"].TopLeft, wx.Size(w, h))
    bounds = bounds.Union(item["bounds"]) if bounds else wx.Rect(item["bounds"])
    if item["bounds"].Right > bounds.Right:
        bounds.Right = item["bounds"].Right + SchemaDiagram.HPAD
    if item["bounds"].Bottom > bounds.Bottom:
        bounds.Bottom = item["bounds"].Bottom + SchemaDiagram.HPAD


# Enlarge bounds by foreign lines/labels
for line in lines.values():
    pts = line["pts"]
    lbounds = wx.Rect(*map(wx.Point, sorted(pts[:2])))
    for i, pt in enumerate(pts[2:-1:2], 2):
        lbounds.Union(wx.Rect(*map(wx.Point, sorted(pts[i:i+2]))))
    bounds.Union(lbounds)
    if not show_labels: continue # for line

    extent = get_extent(util.ellipsize(util.unprint(line["name"]), SchemaDiagram.MAX_TEXT))
    tpt1, tpt2 = next(pts[i:i+2] for i in range(len(pts) - 1)
                      if pts[i][0] == pts[i+1][0])
    tx = tpt1[0]
    ty = min(tpt1[1], tpt2[1]) + abs(tpt1[1] - tpt2[1]) // 2
    tw, th = sum(extent[::4]), sum(extent[1:3])
    bounds.Union(wx.Rect(wx.Point(tx - tw // 2, ty - th), wx.Size(tw, th)))

bounds.Width += 2 * MARGIN; bounds.Height += 2 * MARGIN
shift = [MARGIN - v for v in bounds.TopLeft]
adjust = (lambda *a: tuple(a + b for a, b in zip(a, shift))) if shift else lambda *a: a


%>
%if isdef("embed") and embed:
<svg viewBox="0 0 {{ bounds.Width }} {{ bounds.height }}" version="1.1">
%else:
<?xml version="1.0" encoding="UTF-8" ?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 {{ bounds.Width }} {{ bounds.height }}" version="1.1">
%endif

%if isdef("title") and title:
  <title>{{ title }}</title>
%endif
  <desc>{{ templates.export_comment() }}</desc>

  <defs>

    <linearGradient id="item-background">
      <stop style="stop-color: {{ ColourManager.ColourHex(wincolour) }}; stop-opacity: 1;" offset="0" />
      <stop style="stop-color: {{ ColourManager.ColourHex(gradcolour) }}; stop-opacity: 1;" offset="1" />
    </linearGradient>

    <image id="pk" width="9" height="9" xlink:href="data:image/png;base64,{{! images.DiagramPK.data }}" />

    <image id="fk" width="9" height="9" xlink:href="data:image/png;base64,{{! images.DiagramFK.data }}" />

    <filter x="0" y="0" width="1" height="1" id="clearbg">
       <feFlood flood-color="{{ ColourManager.ColourHex(wincolour) }}" />
       <feComposite in="SourceGraphic" in2="" />
    </filter>

  </defs>

  <style type="text/css">
    <![CDATA[

      svg {
        background:      {{ ColourManager.ColourHex(wincolour) }};
        shape-rendering: crispEdges;
      }

      path {
        fill:            none;
        stroke:          {{ ColourManager.ColourHex(gtextcolour) }};
        stroke-width:    1px;
      }

      text {
        fill:            {{ ColourManager.ColourHex(wtextcolour) }};
        font-size:       {{ fontsize }}px;
        font-family:     {{ SchemaDiagram.FONT_FACE }};
        white-space:     pre;
      }

      .item .box {
         fill:           url(#item-background);
         stroke:         {{ ColourManager.ColourHex(gtextcolour) }};
         stroke-width:   1px;
      }

      .item .content {
        fill:            {{ ColourManager.ColourHex(wincolour) }};
        fill-opacity:    1;
      }

      .item .title {
        font-weight:     bold;
        text-anchor:     middle;
      }

      .item .stats text {
        font-size:       {{ fontsize + SchemaDiagram.FONT_STEP_STATS }}px;
      }

      .item .stats .size {
        fill:            {{ ColourManager.ColourHex(wincolour) }};
        text-anchor:     end;
      }

      .item .separator {
        stroke:          {{ ColourManager.ColourHex(gtextcolour) }};
        stroke-width:    1px;
      }

      .relation path {
        stroke:          {{ ColourManager.ColourHex(btextcolour) }};
        stroke-width:    1px;
      }

      .relation .label {
        fill:            {{ ColourManager.ColourHex(btextcolour) }};
        filter:          url(#clearbg);
        text-anchor:     middle;
      }

    ]]>
  </style>


  <g id="relations">

%for (name1, name2, cols), line in lines.items():
<%

path, pts, R = "", line["pts"], CRADIUS
if show_labels:
    tpt1, tpt2 = next(pts[i:i+2] for i in range(len(pts) - 1)
                      if pts[i][0] == pts[i+1][0])
    tx = tpt1[0]
    ty = min(tpt1[1], tpt2[1]) + abs(tpt1[1] - tpt2[1]) // 2
    tx, ty = adjust(tx, ty)

for i, pt in enumerate(pts):
    mypt, is_corner = pt, (0 < i < len(pts) - 1)
    if not i: # Push first point right to start exactly at item border
        mypt = [pt[0] + 0.5, pt[1]]
    if is_corner: # Pull point back by corner arc radius
        pt0, dx, dy = pts[i - 1], 0, 0
        if pt[1] == pt0[1]: dx = -R if pt[0] > pt0[0] else R
        if pt[0] == pt0[0]: dy = -R if pt[1] > pt0[1] else R
        mypt = [pt[0] + dx, pt[1] + dy]
    if pt == pts[-1]: # Pull ending Y back to start exactly at border
        mypt = [mypt[0], mypt[1] + (2 if pt[1] < pts[i-1][1] else -1)]
    path += ("  L" if i else "M") + " %s,%s" % adjust(*mypt)

    if is_corner: # Draw corner arc
        pt2 = pts[i + 1]
        clockwise = (pt0[0] < pt[0] and pt[1] < pt2[1]) or \
                    (pt0[1] < pt[1] and pt[0] > pt2[0]) or \
                    (pt0[0] > pt[0] and pt[1] > pt2[1]) or \
                    (pt0[1] > pt[1] and pt[0] < pt2[0])
        x2 = +R if pt[1] != pt2[1] and pt0[0] < pt[0] or pt[0] < pt2[0] and pt[1] != pt0[1] else -R
        y2 = +R if pt[1] == pt0[1] and pt[1] < pt2[1] or pt0[1] < pt[1] and pt[1] == pt2[1] else -R
        path += " a %s,%s 0 0,%s %s,%s" % (R, R, 1 if clockwise else 0, x2, y2)


# Assemble crowfoot path in segments for consistent rendering
to_right = pts[0][0] < pts[1][0]
ptc1 = [pts[0][0] + 0.5, pts[0][1]]
ptc2 = [ptc1[0] + 0.5 + SchemaDiagram.CARDINALW * (1 if to_right else -1), ptc1[1]]
ptc1, ptc2 = [ptc1, ptc2][::1 if to_right else -1]
crow1, crow2 = "", ""
for i in range(SchemaDiagram.CARDINALW // 2):
    pt1 = [ptc1[0] + i * 2 + (not to_right), ptc1[1] - (SchemaDiagram.CARDINALW // 2 - i if to_right else i + 1)]
    crow1 += "%sM %s,%s h2" % (("  " if i else "", ) + adjust(pt1[0], pt1[1]))
    pt2 = [ptc1[0] + i * 2 + (not to_right), ptc1[1] + (SchemaDiagram.CARDINALW // 2 - i if to_right else i + 1)]
    crow2 += "%sM %s,%s h2" % (("  " if i else "", ) + adjust(pt2[0], pt2[1]))

# Assemble parent-item dash
direction = 2 if pts[-1][1] < pts[-2][1] else -1
ptd1 = [pts[-1][0] - SchemaDiagram.DASHSIDEW - 0.5, pts[-1][1] + direction]
ptd2 = [pts[-1][0] + SchemaDiagram.DASHSIDEW + 0.5, ptd1[1]]
dash = "M %s,%s L %s,%s" % (adjust(*ptd1) + adjust(*ptd2))

%>
    <g id="{{ util.unprint(name1) }}-{{ util.unprint(name2) }}-{{ util.unprint(line["name"]) }}" class="relation">
      <path d="{{ path }}" />
      <path d="{{ crow1 }}" />
      <path d="{{ crow2 }}" />
      <path d="{{ dash }}" />
    %if show_labels:
      <text x="{{ tx }}" y="{{ ty }}" class="label">{{ util.ellipsize(util.unprint(line["name"]), SchemaDiagram.MAX_TEXT) }}</text>
    %endif
    </g>
%endfor

  </g>



  <g id="items">

%for item in items:
<%

pks, fks = item.get("keys") or ((), ())
cols = item.get("columns") or []
itemx, itemy = adjust(*item["bounds"].TopLeft)

istats = item.get("stats")
cheight = SchemaDiagram.HEADERP + len(cols) * SchemaDiagram.LINEH
height = SchemaDiagram.HEADERH + cheight + SchemaDiagram.FOOTERH
if istats: height += SchemaDiagram.STATSH - SchemaDiagram.FOOTERH

%>

    <g id="{{ util.unprint(item["name"]) }}" class="item {{ item["type"] }}">
      <rect x="{{ itemx }}" y="{{ itemy }}" width="{{ item["bounds"].Width }}" height="{{ height }}" {{ 'rx="%s" ry="%s" ' % ((SchemaDiagram.BRADIUS, ) * 2) if "table" == item["type"] else "" }}class="box" />
      <rect x="{{ itemx + 1 }}" y="{{ itemy + SchemaDiagram.HEADERH }}" width="{{ item["bounds"].Width - 1.5 }}" height="{{ cheight }}" class="content" />
      <path d="M {{ itemx }},{{ itemy + SchemaDiagram.HEADERH }} h{{ item["bounds"].Width }}" class="separator" />


    %if isdef("embed") and embed:
      <a xlink:title="Go to {{ item["type"] }} {{ escape(grammar.quote(item["name"], force=True)) }}" xlink:href="#{{ item["type"] }}/{{! urlquote(item["name"]) }}">
    %endif
      <text x="{{ itemx + item["bounds"].Width // 2 }}" y="{{ itemy + SchemaDiagram.HEADERH - SchemaDiagram.HEADERP }}" class="title">{{ util.ellipsize(util.unprint(item["name"]), SchemaDiagram.MAX_TEXT) }}</text>
    %if isdef("embed") and embed:
      </a>
    %endif

      <text x="{{ itemx }}" y="{{ itemy + SchemaDiagram.HEADERH + SchemaDiagram.HEADERP + texth }}" class="columns">
    %for i, col in enumerate(cols):
        <tspan x="{{ itemx + SchemaDiagram.LPAD }}" y="{{ itemy + SchemaDiagram.HEADERH + SchemaDiagram.HEADERP + texth + i * SchemaDiagram.LINEH }}px">{{ itemcoltexts[item["name"]][i][0] }}</tspan>
    %endfor
      </text>

      <text x="{{ itemx }}" y="{{ itemy + SchemaDiagram.HEADERH + SchemaDiagram.HEADERP + texth }}" class="types">
    %for i, col in enumerate(cols):
        <tspan x="{{ itemx + SchemaDiagram.LPAD + itemcolmax[item["name"]]["name"] + SchemaDiagram.HPAD }}" y="{{ itemy + SchemaDiagram.HEADERH + SchemaDiagram.HEADERP + texth + i * SchemaDiagram.LINEH }}px">{{ itemcoltexts[item["name"]][i][1] }}</tspan>
    %endfor
      </text>

    %if istats:
<%

text1 = istats.get("rows") or ""
text2 = istats.get("size") or ""

ty = itemy + height - SchemaDiagram.STATSH + texth - SchemaDiagram.FONT_STEP_STATS
w1 = next(d[0] + d[3] for d in [get_extent(text1)]) if text1 else 0
w2 = next(d[0] + d[3] for d in [get_extent(text2)]) if text2 else 0
if w1 + w2 + 2 * SchemaDiagram.BRADIUS > item["bounds"].Width and item.get("count"):
    text1 = istats["size_maxunits"]

%>

      <g class="stats">
        <path d="M {{ itemx }},{{ itemy + height - SchemaDiagram.STATSH }} h{{ item["bounds"].Width }}" class="separator" />
        %if istats.get("rows"):
          <text x="{{ itemx + SchemaDiagram.BRADIUS }}" y="{{ ty }}" class="rows">{{ text1 }}</text>
        %endif
        %if istats.get("size"):
          <text x="{{ itemx + item["bounds"].Width - SchemaDiagram.BRADIUS }}" y="{{ ty }}" class="size">{{ text2 }}</text>
        %endif
      </g>
    %endif
    %if pks or fks:

        %for i, col in enumerate(cols):
            %if col["name"] in pks:
      <use xlink:href="#pk" x="{{ itemx + 3 }}" y="{{ itemy + SchemaDiagram.HEADERH + SchemaDiagram.HEADERP + i * SchemaDiagram.LINEH }}" />
            %endif
            %if col["name"] in fks:
      <use xlink:href="#fk" x="{{ itemx + item["bounds"].Width - 5 - images.DiagramFK.Bitmap.Width }}" y="{{ itemy + SchemaDiagram.HEADERH + SchemaDiagram.HEADERP + i * SchemaDiagram.LINEH }}" />
            %endif
        %endfor
    %endif
    </g>

%endfor

  </g>
</svg>
"""
