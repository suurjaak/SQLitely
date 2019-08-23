# -*- coding: utf-8 -*-
"""
HTML and TXT templates for exports and statistics.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    23.08.2019
------------------------------------------------------------------------------
"""
import re

# Modules imported inside templates:
#import base64, datetime, imghdr, os, pyparsing, re, string, sys, urllib, wx
#import conf, images, templates, util
#from lib import util

"""Regex for replacing low bytes unusable in wx.HtmlWindow (\x00 etc)."""
SAFEBYTE_RGX = re.compile("[\x00-\x08,\x0B-\x0C,\x0E-x1F,\x7F]")

"""Replacer callback for low bytes unusable in wx.HtmlWindow (\x00 etc)."""
SAFEBYTE_REPL = lambda m: m.group(0).encode("unicode-escape")

"""HTML data grid export template."""
GRID_HTML = """<%
import datetime
import conf, images
from lib import util
%><!DOCTYPE HTML><html>
<head>
    <meta http-equiv='Content-Type' content='text/html;charset=utf-8' />
    <meta name="Author" content="{{conf.Title}}">
    <title>{{title}}</title>
    <link rel="shortcut icon" type="image/png" href="data:image/ico;base64,{{!images.Icon16x16_8bit.data}}"/>
    <style>
        * { font-family: {{conf.HtmlFontName}}; font-size: 11px; }
        body {
            background: {{conf.HistoryBackgroundColour}};
            margin: 0px 10px 0px 10px;
        }
        .header { font-size: 1.1em; font-weight: bold; color: {{conf.ExportLinkColour}}; }
        .header_table {
            width: 100%;
        }
        .header_left {
            width: 145px;
            text-align: left;
        }
        table.body_table {
            margin-left: auto;
            margin-right: auto;
            border-spacing: 0px 10px;
        }
        table.body_table > tbody > tr > td {
            background: white;
            width: 800px;
            font-family: {{conf.HtmlFontName}};
            font-size: 11px;
            border-radius: 10px;
            padding: 10px;
        }
        table.content_table {
            empty-cells: show;
            border-spacing: 2px;
        }
        table.content_table td {
            line-height: 1.5em;
            padding: 5px;
            border: 1px solid #C0C0C0;
        }
        a, a.visited { color: conf.ExportLinkColour; text-decoration: none; }
        a:hover, a.visited:hover { text-decoration: underline; }
        .footer {
          text-align: center;
          padding-bottom: 10px;
          color: #666;
        }
        .header { font-size: 1.1em; font-weight: bold; color: conf.ExportLinkColour; }
        td { text-align: left; vertical-align: top; }
    </style>
</head>
<body>
<table class="body_table">
<tr><td><table class="header_table">
    <tr>
        <td class="header_left"></td>
        <td>
            <div class="header">{{title}}</div><br />
            Source: <b>{{db_filename}}</b>.<br />
            <b>{{row_count}}</b> {{util.plural("row", row_count, with_items=False)}} in results.<br />
%if sql:
            <b>SQL:</b> {{sql}}
%endif
        </td>
    </tr></table>
</td></tr><tr><td><table class="content_table">
<tr><th>#</th>
%for col in columns:
<th>{{col}}</th>
%endfor
</tr>
%for i, row in enumerate(rows):
<tr>
<td>{{i + 1}}</td>
%for col in columns:
<td>{{"" if row[col] is None else row[col]}}</td>
%endfor
</tr>
%endfor
</table>
</td></tr></table>
<div class="footer">Exported with {{conf.Title}} on {{datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}}.</div>
</body>
</html>
"""


"""TXT SQL insert statements export template."""
SQL_TXT = """<%
import datetime, re, string
import conf

UNPRINTABLES = "".join(set(unichr(i) for i in range(128)).difference(string.printable))
RE_UNPRINTABLE = re.compile("[%s]" % "".join(map(re.escape, UNPRINTABLES)))
str_cols = ", ".join(columns)
%>-- {{title}}.
-- Source: {{db_filename}}.
-- Exported with {{conf.Title}} on {{datetime.datetime.now().strftime("%d.%m.%Y %H:%M")}}.
%if sql:
-- SQL: {{sql}}
%endif
%if table:
{{create_sql}}
%endif

%for row in rows:
<%
values = []
%>
%for col in columns:
<%
value = row[col]
if isinstance(value, basestring):
    if RE_UNPRINTABLE.search(value):
        if isinstance(value, unicode):
            try:
                value = value.encode("latin1")
            except UnicodeError:
                value = value.encode("utf-8", errors="replace")
        value = "X'%s'" % value.encode("hex").upper()
    else:
        if isinstance(value, unicode):
            value = value.encode("utf-8")
        value = '"%s"' % (value.encode("string-escape").replace('\"', '""'))
elif value is None:
    value = "NULL"
else:
    value = str(value)
values.append(value)
%>
%endfor
INSERT INTO {{table}} ({{str_cols}}) VALUES ({{", ".join(values)}});
%endfor
"""



"""HTML template for search results header."""
SEARCH_HEADER_HTML = """<%
import conf
%>
<font size="2" face="{{conf.HtmlFontName}}" color="{{conf.FgColour}}">
Results for "{{text}}" from {{fromtext}}:
<br /><br />
"""


"""HTML template for names search results header, stand-alone table."""
SEARCH_ROW_TABLE_META_HTML = """<%
import conf
%>
Table <a href="table:{{table["name"]}}">
    <font color="{{conf.LinkColour}}">{{!pattern_replace.sub(wrap_b, escape(table["name"]))}}</font></a>:
<table>
%for col in columns:
  <tr>
    <td>{{!pattern_replace.sub(wrap_b, escape(col["name"]))}}</td>
    <td>{{!pattern_replace.sub(wrap_b, escape(col["type"]))}}</td>
  </tr>
%endfor
</table>
<br /><br />
"""


"""HTML template for table search results header, start of HTML table."""
SEARCH_ROW_TABLE_HEADER_HTML = """<%
import conf
%>
<font color="{{conf.FgColour}}">
<br /><br /><b><a name="{{table["name"]}}">Table {{table["name"]}}:</a></b><br />
<table border="1" cellpadding="4" cellspacing="0" width="1000">
<tr>
<th>#</th>
%for col in table["columns"]:
<th>{{col["name"]}}</th>
%endfor
</tr>
"""


"""HTML template for search result of DB table row, HTML table row."""
SEARCH_ROW_TABLE_HTML = """<%
import re
import conf, templates

match_kw = lambda k, x: any(y in x["name"].lower() for y in keywords[k])
%>
<tr>
<td align="right" valign="top">
  <a href="table:{{table["name"]}}:{{count}}">
    <font color="{{conf.LinkColour}}">{{count}}</font>
  </a>
</td>
%for col in table["columns"]:
<%
value = row[col["name"]]
value = value if value is not None else ""
value = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, unicode(value))
value = escape(value)

if not (keywords.get("column") and not match_kw("column", col)) \
and not (keywords.get("-column") and match_kw("-column", col)):
    value = pattern_replace.sub(wrap_b, value)
%>
<td valign="top"><font color="{{conf.FgColour}}">{{!value}}</font></td>
%endfor
</tr>
"""


"""Text shown in Help -> About dialog (HTML content)."""
ABOUT_HTML = """<%
import sys
import conf
%>
<font size="2" face="{{conf.HtmlFontName}}" color="{{conf.FgColour}}">
<table cellpadding="0" cellspacing="0"><tr><td valign="top">
<img src="memory:{{conf.Title.lower()}}.png" /></td><td width="10"></td><td valign="center">
<b>{{conf.Title}} version {{conf.Version}}</b>, {{conf.VersionDate}}.<br /><br />

{{conf.Title}} is written in Python, released as free open source software
under the MIT License.
</td></tr></table><br /><br />


&copy; 2019, Erki Suurjaak.
<a href="{{conf.HomeUrl}}"><font color="{{conf.LinkColour}}">{{conf.HomeUrl.replace("https://", "").replace("http://", "")}}</font></a><br /><br /><br />



{{conf.Title}} has been built using the following open source software:
<ul>
  <li>wxPython{{" 3.0.2.0" if getattr(sys, 'frozen', False) else ""}},
      <a href="http://wxpython.org"><font color="{{conf.LinkColour}}">wxpython.org</font></a></li>
  <li>Pillow{{" 2.8.1" if getattr(sys, 'frozen', False) else ""}},
      <a href="https://pypi.python.org/pypi/Pillow/"><font color="{{conf.LinkColour}}">pypi.python.org/pypi/Pillow</font></a></li>
  <li>step, Simple Template Engine for Python,
      <a href="https://github.com/dotpy/step"><font color="{{conf.LinkColour}}">github.com/dotpy/step</font></a></li>
  <li>pyparsing{{" 2.0.3" if getattr(sys, 'frozen', False) else ""}}, 
      <a href="http://pyparsing.wikispaces.com/"><font color="{{conf.LinkColour}}">pyparsing.wikispaces.com</font></a></li>
  <li>XlsxWriter{{" 0.7.3" if getattr(sys, 'frozen', False) else ""}},
      <a href="https://github.com/jmcnamara/XlsxWriter"><font color="{{conf.LinkColour}}">
          github.com/jmcnamara/XlsxWriter</font></a></li>
%if getattr(sys, 'frozen', False):
  <li>Python 2.7.10, <a href="http://www.python.org"><font color="{{conf.LinkColour}}">www.python.org</font></a></li>
  <li>PyInstaller 2.1, <a href="http://www.pyinstaller.org">
      <font color="{{conf.LinkColour}}">www.pyinstaller.org</font></a></li>
%endif
</ul><br /><br />



Several icons from Fugue Icons, &copy; 2010 Yusuke Kamiyamane<br />
<a href="http://p.yusukekamiyamane.com/"><font color="{{conf.LinkColour}}">p.yusukekamiyamane.com</font></a>
<br /><br />
Includes fonts Carlito Regular and Carlito bold,
<a href="https://fedoraproject.org/wiki/Google_Crosextra_Carlito_fonts"><font color="{{conf.LinkColour}}">fedoraproject.org/wiki/Google_Crosextra_Carlito_fonts</font></a>
%if getattr(sys, 'frozen', False):
<br /><br />
Installer created with Nullsoft Scriptable Install System 3.0b1,
<a href="http://nsis.sourceforge.net/"><font color="{{conf.LinkColour}}">nsis.sourceforge.net</font></a>
%endif

</font>
"""



"""Contents of the default page on search page."""
SEARCH_WELCOME_HTML = """<%
import conf
%>
<font face="{{conf.HtmlFontName}}" size="2" color="{{conf.FgColour}}">
<center>
<h5><font color="{{conf.TitleColour}}">Explore the database</font></h5>
<table cellpadding="10" cellspacing="0">
<tr>
  <td>
    <table cellpadding="0" cellspacing="2"><tr><td>
        <a href="page:tables"><img src="memory:HelpTables.png" /></a>
      </td><td width="10"></td><td valign="center">
        Browse, filter and change database tables,<br />
        export as HTML, SQL INSERT-statements or spreadsheet.
      </td></tr><tr><td nowrap align="center">
        <a href="page:tables"><b><font color="{{conf.FgColour}}">Tables</font></b></a><br />
    </td></tr></table>
  </td>
  <td>
    <table cellpadding="0" cellspacing="2"><tr><td>
        <a href="page:sql"><img src="memory:HelpSQL.png" /></a>
      </td><td width="10"></td><td valign="center">
        Make direct SQL queries in the database,<br />
        export results as HTML or spreadsheet.
      </td></tr><tr><td nowrap align="center">
        <a href="page:sql"><b><font color="{{conf.FgColour}}">SQL window</font></b></a><br />
    </td></tr></table>
  </td>
</tr>
<tr>
  <td>
    <table cellpadding="0" cellspacing="2"><tr><td>
        <a href="page:#search"><img src="memory:HelpSearch.png" /></a>
      </td><td width="10"></td><td valign="center">
        Search over database using a simple Google-like <a href="page:#help"><font color="{{conf.LinkColour}}">syntax</font></a>.<br />
      </td></tr><tr><td nowrap align="center">
        <a href="page:#search"><b><font color="{{conf.FgColour}}">Search</font></b></a><br />
    </td></tr></table>
  </td>
  <td>
    <table cellpadding="0" cellspacing="2"><tr><td>
        <a href="page:info"><img src="memory:HelpInfo.png" /></a>
      </td><td width="10"></td><td valign="center">
        See information about the database,<br />
        view general database statistics,<br />
        check database integrity for corruption and recovery.
      </td></tr><tr><td nowrap align="center">
        <a href="page:info"><b><font color="{{conf.FgColour}}">Information</font></b></a>
    </td></tr></table>
  </td>
</tr>
</table>
</center>
</font>
"""


"""Long help text shown in a separate tab on search page."""
SEARCH_HELP_LONG = """<%
import conf
try:
    import pyparsing
except ImportError:
    pyparsing = None
%>
<font size="2" face="{{conf.HtmlFontName}}" color="{{conf.FgColour}}">
%if not pyparsing:
<b><font color="red">Search syntax currently limited:</font></b>&nbsp;&nbsp;pyparsing not installed.<br /><br /><br />
%endif
{{conf.Title}} supports a Google-like syntax for searching the database:<br /><br />
<table><tr><td width="500">
  <table border="0" cellpadding="5" cellspacing="1" bgcolor="{{conf.HelpBorderColour}}"
   valign="top" width="500">
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Search for exact word or phrase</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>"do re mi"</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      Use quotes (<font color="{{conf.HelpCodeColour}}"><code>"</code></font>) to search for
      an exact phrase or word. Quoted text is searched exactly as entered,
      leaving whitespace as-is and ignoring any wildcard characters.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Search for either word</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>this OR that</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      To find messages containing at least one of several words,
      include <font color="{{conf.HelpCodeColour}}"><code>OR</code></font> between the words.
      <font color="{{conf.HelpCodeColour}}"><code>OR</code></font> works also
      for phrases and grouped words (but not keywords).
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Group words together</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>(these two) OR this<br/>
      -(none of these)</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      Surround words with round brackets to group them for <code>OR</code>
      queries or for excluding from results.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Search for partially matching text</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>bas*ball</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      Use an asterisk (<font color="{{conf.HelpCodeColour}}"><code>*</code></font>) to make a
      wildcard query: the wildcard will match any text between its front and
      rear characters (including other words).
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Exclude words or keywords</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>-notthisword<br />-"not this phrase"<br />
      -(none of these)<br/>-table:notthistable<br/>
      -date:2013</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      To exclude certain results, add a dash
      (<font color="{{conf.HelpCodeColour}}"><code>-</code></font>) in front of words,
      phrases, grouped words or keywords.
    </td>
  </tr>
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Search specific tables</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>table:fromthistable<br />
      -table:notfromthistable</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      Use the keyword <font color="{{conf.HelpCodeColour}}"><code>table:name</code></font>
      to constrain results to specific tables only.<br /><br />
      Search from more than one table by adding more
      <font color="{{conf.HelpCodeColour}}"><code>table:</code></font> keywords, or exclude certain
      tables by adding a <font color="{{conf.HelpCodeColour}}"><code>-table:</code></font> keyword.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Search specific columns</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>column:fromthiscolumn<br />
      -column:notfromthiscolumn</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      Use the keyword <font color="{{conf.HelpCodeColour}}"><code>column:name</code></font>
      to constrain results to specific columns only.<br /><br />
      Search from more than one column by adding more
      <font color="{{conf.HelpCodeColour}}"><code>column:</code></font> keywords, or exclude certain
      columns by adding a <font color="{{conf.HelpCodeColour}}"><code>-column:</code></font> keyword.
      <br />
    </td>
  </tr>
  <tr>
    <td bgcolor="{{conf.BgColour}}" width="150">
      <b>Search from specific time periods</b><br /><br />
      <font color="{{conf.HelpCodeColour}}"><code>date:2008<br />date:2009-01<br />
      date:2005-12-24..2007</code></font>
      <br />
    </td>
    <td bgcolor="{{conf.BgColour}}">
      <br /><br />
      To find rows from specific time periods (where row has timestamp columns), use the keyword
      <font color="{{conf.HelpCodeColour}}"><code>date:period</code></font> or
      <font color="{{conf.HelpCodeColour}}"><code>date:periodstart..periodend</code></font>.
      For the latter, either start or end can be omitted.<br /><br />
      A date period can be year, year-month, or year-month-day. Additionally,
      <font color="{{conf.HelpCodeColour}}"><code>date:period</code></font> can use a wildcard
      in place of any part, so
      <font color="{{conf.HelpCodeColour}}"><code>date:*-12-24</code></font> would search for
      all messages from the 24th of December.<br /><br />
      Search from a more narrowly defined period by adding more
      <font color="{{conf.HelpCodeColour}}"><code>date:</code></font> keywords.
      <br />
    </td>
  </tr>
  </table>

</td><td valign="top" align="left">

  <b><font size="3">Examples</font></b><br /><br />

  <ul>
    <li>search for "flickr.com" in tables named "links":
        <br /><br />
        <font color="{{conf.HelpCodeColour}}">
        <code>flickr.com table:links</code></font><br />
    </li>
    <li>search for "foo bar" up to 2011:<br /><br />
        <font color="{{conf.HelpCodeColour}}"><code>"foo bar" date:..2011</code></font>
        <br />
    </li>
    <li>search for either "John" and "my side" or "Stark" and "your side":
        <br /><br />
        <font color="{{conf.HelpCodeColour}}">
        <code>(john "my side") OR (stark "your side")</code></font><br />
    </li>
    <li>search for either "barbecue" or "grill" in 2012,
        except from June to August:<br /><br />
        <font color="{{conf.HelpCodeColour}}">
        <code>barbecue OR grill date:2012 -date:2012-06..2012-08</code>
        </font><br />
    </li>
    <li>search for "TPS report" but not "my TPS report"
        on the first day of the month in 2012:
        <br /><br />
        <font color="{{conf.HelpCodeColour}}">
        <code>"tps report" -"my tps report" date:2012-*-1</code>
        </font><br />
    </li>
  </ul>

  <br /><br />
  All search text is case-insensitive. <br />
  Keywords are case-sensitive
  (<code>OR</code>, <code>table:</code>, <code>column:<(code>, <code>date:</code>).

</td></tr></table>
</font>
"""


"""Short help text shown on search page."""
SEARCH_HELP_SHORT = """<%
import os
import conf
helplink = "Search help"
if "nt" == os.name: # In Windows, wx.HtmlWindow shows link whitespace quirkily
    helplink = helplink.replace(" ", "_")
%>
<font size="2" face="{{conf.HtmlFontName}}" color="{{conf.DisabledColour}}">
For searching from specific tables, add "table:name", and from specific columns, add "column:name".
&nbsp;&nbsp;<a href=\"page:#help\"><font color="{{conf.LinkColour}}">{{helplink}}</font></a>.
</font>
"""
