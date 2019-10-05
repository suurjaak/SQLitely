# -*- coding: utf-8 -*-
"""
Functionality for exporting SQLite data to external files.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    04.10.2019
------------------------------------------------------------------------------
"""
import collections
import csv
import datetime
import os
import re

try: # ImageFont for calculating column widths in Excel export, not required.
    from PIL import ImageFont
except ImportError:
    ImageFont = None
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

from . lib import util
from . lib.vendor import step
from . import conf
from . import grammar
from . import templates


try: # Used in measuring text extent for Excel column auto-width
    FONT_XLSX = ImageFont.truetype(conf.FontXlsxFile, 15)
    FONT_XLSX_BOLD = ImageFont.truetype(conf.FontXlsxBoldFile, 15)
except IOError: # Fall back to PIL default font if font files not on disk
    FONT_XLSX = FONT_XLSX_BOLD = ImageFont.load_default()
except Exception: # Fall back to a simple mono-spaced calculation if no PIL
    FONT_MONO = type('', (), {"getsize": lambda self, s: (8*len(s), 12)})()
    FONT_XLSX = FONT_XLSX_BOLD = FONT_MONO

"""FileDialog wildcard strings, matching extensions lists and default names."""
XLSX_WILDCARD = "Excel workbook (*.xlsx)|*.xlsx|" if xlsxwriter else ""

WILDCARD = ("HTML document (*.html)|*.html|"
            "Text document (*.txt)|*.txt|"
            "SQL INSERT statements (*.sql)|*.sql|"
            "%sCSV spreadsheet (*.csv)|*.csv" % XLSX_WILDCARD)
EXTS = ["html", "txt", "sql", "xlsx", "csv"] if xlsxwriter \
        else ["html", "txt", "sql", "csv"]


def export_data(make_iterable, filename, title, db, columns,
                query="", category="", name="", progress=None):
    """
    Exports database data to file.

    @param   make_iterable   function returning iterable sequence yielding rows
    @param   filename        full path and filename of resulting file, file extension
                             .html|.csv|.sql|.xslx determines file format
    @param   title           title used in HTML
    @param   db              Database instance
    @param   columns         iterable columns, as [name, ] or [{"name": name}, ]
    @param   query           the SQL query producing the data, if any
    @param   category        category producing the data, if any, "table" or "view"
    @param   name            name of the table or view producing the data, if any
    @param   progress        callback(count) to report progress,
                             returning false if export should cancel
    """
    result = False
    f = None
    is_html = filename.lower().endswith(".html")
    is_csv  = filename.lower().endswith(".csv")
    is_sql  = filename.lower().endswith(".sql")
    is_txt  = filename.lower().endswith(".txt")
    is_xlsx = filename.lower().endswith(".xlsx")
    colnames = [c if isinstance(c, basestring) else c["name"] for c in columns]
    tmpfile, tmpname = None, None # Temporary file for exported rows
    try:
        with open(filename, "w") as f:
            if category and name: db.lock(category, name, make_iterable)
            count = 0

            if is_csv or is_xlsx:
                if is_csv:
                    dialect = csv.excel
                    dialect.delimiter, dialect.lineterminator = ";", "\r"
                    writer = csv.writer(f, dialect)
                    if query:
                        flat = query.replace("\r", " ").replace("\n", " ")
                        query = flat.encode("latin1", "replace")
                    header = [c.encode("latin1", "replace") for c in colnames]
                else:
                    writer = xlsx_writer(filename, name or "SQL Query")
                    writer.set_header(True)
                    header = colnames
                if query:
                    a = [[query]] + (["bold", 0, False] if is_xlsx else [])
                    writer.writerow(*a)
                writer.writerow(*([header, "bold"] if is_xlsx else [header]))
                writer.set_header(False) if is_xlsx else 0
                for i, row in enumerate(make_iterable()):
                    values = []
                    for col in colnames:
                        val = "" if row[col] is None else row[col]
                        if is_csv:
                            val = val if isinstance(val, unicode) else str(val)
                            val = val.encode("latin1", "replace")
                        values.append(val)
                    writer.writerow(values)
                    count = i
                    if not i % 100 and progress and not progress(count=i):
                        break # for i, row
                if is_xlsx: writer.close()
            else:
                namespace = {
                    "db_filename": db.name,
                    "title":       title,
                    "columns":     colnames,
                    "rows":        make_iterable(),
                    "row_count":   0,
                    "sql":         query,
                    "category":    category,
                    "name":        name,
                    "progress":    progress,
                }
                namespace["namespace"] = namespace # To update row_count

                if is_txt: # Run through rows once, to populate text-justify options
                    widths = {c: len(c) for c in colnames}
                    justs  = {c: True   for c in colnames}
                    for i, row in enumerate(make_iterable()):
                        for col in colnames:
                            v = row[col]
                            if isinstance(v, (int, long, float)): justs[col] = False
                            v = "" if v is None \
                                else v if isinstance(v, basestring) else str(v)
                            v = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, unicode(v))
                            widths[col] = max(widths[col], len(v))
                        if not i % 100 and progress and not progress(): return
                    namespace["columnwidths"] = widths # {col: char length}
                    namespace["columnjusts"]  = justs  # {col: True if ljust}
                if progress and not progress(): return

                # Write out data to temporary file first, to populate row count.
                tmpname = util.unique_path("%s.rows" % filename)
                tmpfile = open(tmpname, "wb+")
                template = step.Template(templates.DATA_ROWS_HTML if is_html else
                           templates.DATA_ROWS_SQL if is_sql else templates.DATA_ROWS_TXT,
                           strip=False, escape=is_html)
                template.stream(tmpfile, namespace)

                if progress and not progress(): return

                if is_sql and "table" != category:
                    # Add CREATE statement for saving view AS table
                    meta = {"__type__": grammar.SQL.CREATE_TABLE, "name": name,
                            "columns": columns}
                    namespace["create_sql"], _ = grammar.generate(meta)
                elif name:
                    # Add CREATE statement
                    transform = {"exists": True} if is_sql else None
                    create_sql = db.get_sql(category, name, transform=transform)
                    namespace["create_sql"] = create_sql

                tmpfile.flush(), tmpfile.seek(0)
                namespace["data_buffer"] = iter(lambda: tmpfile.read(65536), "")
                template = step.Template(templates.DATA_HTML if is_html else
                           templates.DATA_SQL if is_sql else templates.DATA_TXT,
                           strip=False, escape=is_html)
                template.stream(f, namespace)
                count = namespace["row_count"]

            result = progress(count=count) if progress else True
    finally:
        if tmpfile:    util.try_until(tmpfile.close)
        if tmpname:    util.try_until(lambda: os.unlink(tmpname))
        if not result: util.try_until(lambda: os.unlink(filename))
        if category and name: db.unlock(category, name, make_iterable)

    return result



class xlsx_writer(object):
    """Convenience wrapper for xslxwriter, with csv.Writer-like interface."""
    COL_MAXWIDTH   = 100 # In Excel units, 1 == width of "0" in standard font
    ROW_MAXNUM     = 1048576 # Maximum per worksheet
    FMT_DEFAULT    = {"bg_color": "white", "valign": "top"}
    FMT_BOLD       = dict(FMT_DEFAULT, **{"bold": True})
    FMT_WRAP       = dict(FMT_DEFAULT, **{"text_wrap": True})
    FMT_LOCAL      = dict(FMT_DEFAULT, **{"font_color": "#999999"})
    FMT_REMOTE     = dict(FMT_DEFAULT, **{"font_color": "#3399FF"})
    FMT_HIDDEN     = dict(FMT_DEFAULT, **{"font_color": "#C0C0C0"})
    FMT_BOLDHIDDEN = dict(FMT_DEFAULT, **{"font_color": "#C0C0C0", "bold": True})
    FMT_TIMESTAMP  = dict(FMT_DEFAULT, **{"font_color": "#999999",
                                          "align": "left",
                                          "num_format": "yyyy-mm-dd HH:MM", })

    def __init__(self, filename, sheetname=None, autowrap=()):
        """
        @param   sheetname  title of the first sheet to create, if any
        @param   autowrap   a list of column indexes that will get their width
                            set to COL_MAXWIDTH and their contents wrapped
        """
        self._workbook = xlsxwriter.Workbook(filename,
            {"constant_memory": True, "strings_to_formulas": False})
        self._sheet      = None # Current xlsxwriter.Worksheet, if any
        self._sheets     = {} # {lowercase sheet name: xlsxwriter.Worksheet, }
        self._sheetnames = {} # {xlsxwriter.Worksheet: original given name, }
        self._headers    = {} # {sheet name: [[values, style, merge_cols], ], }
        self._col_widths = {} # {sheet name: {col index: width in Excel units}}
        self._autowrap   = [c for c in autowrap] # [column index to autowrap, ]
        self._format     = None

        # Worksheet style formats
        format_default = self._workbook.add_format(self.FMT_DEFAULT)
        self._formats  = collections.defaultdict(lambda: format_default)
        for t in ["bold", "wrap", "local", "remote",
                  "hidden", "boldhidden", "timestamp"]:
            f = getattr(self, "FMT_%s" % t.upper(), self.FMT_DEFAULT)
            self._formats[t] = self._workbook.add_format(f)

        # For calculating column widths
        self._fonts = collections.defaultdict(lambda: FONT_XLSX)
        self._fonts["bold"] = FONT_XLSX_BOLD
        unit_width_default = self._fonts[None].getsize("0")[0]
        self._unit_widths = collections.defaultdict(lambda: unit_width_default)
        self._unit_widths["bold"] = self._fonts["bold"].getsize("0")[0]

        if sheetname: # Create default sheet
            self.add_sheet(sheetname)


    def add_sheet(self, name=None):
        """Adds a new worksheet. Name will be changed if invalid/existing."""
        if self._sheet and hasattr(self._sheet, "_opt_close"):
            self._sheet._opt_close() # Close file handle to not hit ulimit
        safename = None
        if name:
            # Max length 31, no []:\\?/*\x00\x03, cannot start/end with '.
            stripped = name.strip("'")
            safename = re.sub(r"[\[\]\:\\\?\/\*\x00\x03]", " ", stripped)
            safename = safename[:29] + ".." if len(safename) > 31 else safename
            # Ensure unique name, appending (counter) if necessary
            base, counter = safename, 2
            while safename.lower() in self._sheets:
                suffix = " (%s)" % (counter)
                safename = base + suffix
                if len(safename) > 31:
                    safename = "%s..%s" % (base[:31 - len(suffix) - 2], suffix)
                counter += 1
        sheet = self._workbook.add_worksheet(safename)
        self._sheets[sheet.name.lower()] = self._sheet = sheet
        self._sheetnames[sheet] = name or sheet.name
        self._col_widths[sheet.name] = collections.defaultdict(lambda: 0)
        for c in self._autowrap:
            sheet.set_column(c, c, self.COL_MAXWIDTH, self._formats[None])
        self._row = 0

        # Worksheet write functions for different data types
        self._writers = collections.defaultdict(lambda: sheet.write)
        self._writers[datetime.datetime] = sheet.write_datetime
        # Avoid using write_url: URLs are very limited in Excel (max len 256)
        self._writers[str] = self._writers[unicode] = sheet.write_string


    def set_header(self, start):
        """Starts or stops header section: bold lines split from the rest."""
        self._format = "bold" if start else None
        if start:
            self._headers[self._sheet.name] = []
        else:
            self._sheet.freeze_panes(self._row, 0)


    def writerow(self, values, style="", merge_cols=0, autowidth=True):
        """
        Writes to the current row from first column, steps to next row.
        If current sheet is full, starts a new one.

        @param   style       format name to apply for all columns, or a dict
                             mapping column indexes to format names
        @param   merge_cols  how many columns to merge (0 for none)
        @param   autowidth   are the values used to auto-size column max width
        """
        if self._row >= self.ROW_MAXNUM: # Sheet full: start a new one
            name_former = self._sheet.name
            self.add_sheet(self._sheetnames[self._sheet])
            if name_former in self._headers: # Write same header
                self.set_header(True)
                [self.writerow(*x) for x in self._headers[name_former]]
                self.set_header(False)
        if "bold" == self._format:
            self._headers[self._sheet.name] += [(values, style, merge_cols)]
        if merge_cols:
            f = self._formats[self._format]
            self._sheet.merge_range(self._row, 0, self._row, merge_cols, "", f)
            values = values[0] if values else []
        for c, v in enumerate(values):
            writefunc = self._writers[type(v)]
            fmt_name = style if isinstance(style, basestring) \
                       else style.get(c, self._format)
            writefunc(self._row, c, v, self._formats[fmt_name])
            if (merge_cols or not autowidth or "wrap" == fmt_name
            or c in self._autowrap):
                continue # continue for c, v in enumerate(Values)

            # Calculate and update maximum written column width
            strval = (v.encode("latin1", "replace") if isinstance(v, unicode)
                      else v.strftime("%Y-%m-%d %H:%M") \
                      if isinstance(v, datetime.datetime) else
                      v if isinstance(v, basestring) else str(v))
            pixels = max(self._fonts[fmt_name].getsize(x)[0]
                         for x in strval.split("\n"))
            width = float(pixels) / self._unit_widths[fmt_name] + 1
            if not merge_cols and width > self._col_widths[self._sheet.name][c]:
                self._col_widths[self._sheet.name][c] = width
        self._row += 1


    def close(self):
        """Finalizes formatting and saves file content."""

        # Auto-size columns with calculated widths
        for sheet in self._workbook.worksheets():
            c = -1
            for c, w in sorted(self._col_widths[sheet.name].items()):
                w = min(w, self.COL_MAXWIDTH)
                sheet.set_column(c, c, w, self._formats[None])
            sheet.set_column(c + 1, 50, cell_format=self._formats[None])
        self._workbook.set_properties({"comments": "Exported with %s on %s." %
            (conf.Title, datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))})
        self._workbook.close()
