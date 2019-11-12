# -*- coding: utf-8 -*-
"""
Functionality for exporting SQLite data to external files.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    12.11.2019
------------------------------------------------------------------------------
"""
import collections
import csv
import datetime
import itertools
import logging
import os
import re

# ImageFont for calculating column widths in Excel export, not required.
try: from PIL import ImageFont
except ImportError: ImageFont = None
try: import openpyxl
except ImportError: openpyxl = None
try: import xlrd
except ImportError: xlrd = None
try: import xlsxwriter
except ImportError: xlsxwriter = None

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

"""Wildcards for import file dialog."""
EXCEL_EXTS = (["xls"] if xlrd else []) + (["xlsx"] if openpyxl else [])
IMPORT_WILDCARD = "%s%sCSV spreadsheet (*.csv)|*.csv" % (
    "All spreadsheets ({0})|{0}|".format(";".join("*." + x for x in EXCEL_EXTS + ["csv"])),
    "Excel workbook ({0})|{0}|".format(";".join("*." + x for x in EXCEL_EXTS))
    if EXCEL_EXTS else ""
)

"""FileDialog wildcard strings, matching extensions lists and default names."""
XLSX_WILDCARD = "Excel workbook (*.xlsx)|*.xlsx|" if xlsxwriter else ""

"""Wildcards for export file dialog."""
EXPORT_WILDCARD = ("HTML document (*.html)|*.html|"
                   "Text document (*.txt)|*.txt|"
                   "SQL INSERT statements (*.sql)|*.sql|"
                   "%sCSV spreadsheet (*.csv)|*.csv" % XLSX_WILDCARD)
EXPORT_EXTS = ["html", "txt", "sql", "xlsx", "csv"] if xlsxwriter \
               else ["html", "txt", "sql", "csv"]

"""Maximum file size to do full row count for."""
MAX_IMPORT_FILESIZE_FOR_COUNT = 10 * 1e6

logger = logging.getLogger(__name__)



def export_data(make_iterable, filename, title, db, columns,
                query="", category="", name="", progress=None):
    """
    Exports database data to file.

    @param   make_iterable   function returning iterable sequence yielding rows
    @param   filename        full path and filename of resulting file, file extension
                             .html|.csv|.sql|.xslx determines file format
    @param   title           title used in HTML and spreadsheet
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
                    props = {"title": title, "comments": templates.export_comment()}
                    writer = xlsx_writer(filename, name or "SQL Query", props=props)
                    writer.set_header(True)
                    header = colnames
                if query:
                    a = [[query]] + (["bold", 0, False] if is_xlsx else [])
                    writer.writerow(*a)
                writer.writerow(*([header, "bold"] if is_xlsx else [header]))
                writer.set_header(False) if is_xlsx else 0
                for i, row in enumerate(make_iterable(), 1):
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


def export_data_single(filename, title, db, category, progress=None):
    """
    Exports database data from multiple tables/views to a single spreadsheet.

    @param   filename        full path and filename of resulting file
    @param   title           spreadsheet title
    @param   db              Database instance
    @param   category        category producing the data, "table" or "view"
    @param   progress        callback(name, count) to report progress,
                             returning false if export should cancel
    """
    result = True
    items = db.schema[category]
    try:
        props = {"title": title, "comments": templates.export_comment()}
        writer = xlsx_writer(filename, next(iter(items), None), props=props)

        for n in items: db.lock(category, n, filename)
        for idx, (name, item) in enumerate(items.items()):
            count = 0
            if progress and not progress(name=name, count=count):
                result = False
                break # for idx, (name, item)
            if idx: writer.add_sheet(name)
            colnames = [x["name"] for x in item["columns"]]
            writer.set_header(True)
            writer.writerow(colnames, "bold")
            writer.set_header(False)

            sql = "SELECT * FROM %s" % grammar.quote(name)
            for i, row in enumerate(db.execute(sql), 1):
                count = i
                writer.writerow([row[c] for c in colnames])
                if not i % 100 and progress and not progress(name=name, count=i):
                    result = False
                    break # for i, row
            if not result: break # for idx, (name, item)
            if progress and not progress(name=name, count=count):
                result = False
                break # for idx, (name, item)
        writer.close()
        if progress: progress(done=True)
    except Exception as e:
        logger.exception("Error exporting %s from %s to %s.",
                         util.plural(category), db, filename)
        if progress: progress(error=util.format_exc(e), done=True)
        result = False
    finally:
        for n in items: db.unlock(category, n, filename)
        if not result: util.try_until(lambda: os.unlink(filename))

    return result


def export_sql(filename, db, sql, title=None):
    """Exports arbitrary SQL to file."""
    template = step.Template(templates.CREATE_SQL, strip=False)
    ns = {"title": title, "db_filename": db.name, "sql": sql}
    with open(filename, "wb") as f: template.stream(f, ns)
    return True


def export_stats(filename, db, data, filetype="html"):
    """Exports statistics to HTML or SQL file."""
    TPLARGS = {"html": (templates.DATA_STATISTICS_HTML, dict(escape=True)),
               "sql":  (templates.DATA_STATISTICS_SQL,  dict(strip=False))}
    template = step.Template(TPLARGS[filetype][0], **TPLARGS[filetype][1])
    ns = {"title": "Database statistics", "sql": data["data"]["sql"],
          "db_filename": db.name, "db_filesize": data["data"]["filesize"]}
    with open(filename, "wb") as f: template.stream(f, ns, **data)
    return True


def export_dump(filename, db, progress=None):
    """
    Exports full database dump to SQL file.

    @param   progress        callback(name, count) to report progress,
                             returning false if export should cancel
    """
    result = False
    tables = db.schema["table"]
    try:
        with open(filename, "w") as f:
            for t in tables: db.lock("table", t, filename)
            namespace = {
                "db":       db,
                "sql":      db.get_sql(),
                "data":     [{"name": t, "columns": [x["name"] for x in opts["columns"]],
                              "rows": iter(db.execute("SELECT * FROM %s" % grammar.quote(t)))}
                             for t, opts in tables.items()],
                "pragma":   db.get_pragma_values(),
                "progress": progress,
            }
            template = step.Template(templates.DUMP_SQL, strip=False)
            template.stream(f, namespace)
            result = progress() if progress else True
    finally:
        for t in tables: db.unlock("table", t, filename)
        if not result: util.try_until(lambda: os.unlink(filename))

    return result


def get_import_file_data(filename):
    """
    Returns import file metadata, as {
        "name":        file name and path}.
        "size":        file size in bytes,
        "sheets":      [
            "name":    sheet name or None if CSV,
            "rows":    count or -1 if file too large,
            "columns": [first row cell value, ],
    ]}.
    """
    sheets, size = [], os.path.getsize(filename)

    is_csv  = filename.lower().endswith(".csv")
    is_xls  = filename.lower().endswith(".xls")
    is_xlsx = filename.lower().endswith(".xlsx")
    if is_csv:
        rows = -1 if size > MAX_IMPORT_FILESIZE_FOR_COUNT else 0
        with open(filename, "rbU") as f:
            firstline = next(f, "")
            if not rows: rows = sum((1 for _ in f), 1 if firstline else 0)
        if firstline.startswith("\xFF\xFE"): # Unicode little endian header
            try:
                firstline = firstline.decode("utf-16") # GMail CSVs can be in UTF-16
            except UnicodeDecodeError:
                firstline = firstline[2:].replace("\x00", "")
            else: # CSV has trouble with Unicode: turn back to string
                firstline = firstline.encode("latin1", errors="xmlcharrefreplace")
        csvfile = csv.reader([firstline], csv.Sniffer().sniff(firstline, ",;\t"))
        sheets.append({"rows": rows, "columns": next(csvfile), "name": "<no name>"})
    elif is_xls:
        with xlrd.open_workbook(filename, on_demand=True) as wb:
            for sheet in wb.sheets():
                rows = -1 if size > MAX_IMPORT_FILESIZE_FOR_COUNT else sheet.nrows
                columns = [x.value for x in next(sheet.get_rows(), [])]
                while columns and columns[-1] is None: columns.pop(-1)
                sheets.append({"rows": rows, "columns": columns, "name": sheet.name})
    elif is_xlsx:
        wb = None
        try:
            wb = openpyxl.load_workbook(filename, data_only=True, read_only=True)
            for sheet in wb.worksheets:
                rows = -1 if size > MAX_IMPORT_FILESIZE_FOR_COUNT \
                       else sum(1 for _ in sheet.iter_rows())
                columns = list(next(sheet.values, []))
                while columns and columns[-1] is None: columns.pop(-1)
                sheets.append({"rows": rows, "columns": columns, "name": sheet.title})
        finally: wb and wb.close()

    return {"name": filename, "size": size, "sheets": sheets}



def import_data(filename, db, table, columns,
                sheet=None, has_header=True, pk=None, progress=None):
    """
    Imports data from file to database table. Will create table if not exists.

    @param   filename    file path to import from
    @param   db          database.Database instance
    @param   table       table name to import to
    @param   columns     mapping of file columns to table columns,
                         as OrderedDict(file column index: table columm name)
    @param   sheet       sheet name to import from, if applicable
    @param   has_header  whether the file has a header row
    @param   pk          name of auto-increment primary key to add
                         for new table, if any
    @param   progress    callback(?count, ?done, ?error, ?errorcount, ?index) to report
                         progress, returning false if import should cancel,
                         and None if import should rollback
    @return              success
    """
    result = True
    create_sql = None

    if not db.get_category("table", table):
        cols = [{"name": x} for x in columns.values()]
        if pk: cols.insert(0, {"name": pk, "type": "INTEGER", "pk": {"autoincrement": True}})
        meta = {"name": table, "__type__": grammar.SQL.CREATE_TABLE,
                "columns": cols}
        create_sql, err = grammar.generate(meta)
        if err:
            if progress: progress(error=err, done=True)
            return

    sql = "INSERT INTO %s (%s) VALUES (%s)" % (grammar.quote(table),
        ", ".join(grammar.quote(x) for x in columns.values()),
        ", ".join("?" * len(columns))
    )

    continue_on_error = None
    try:
        isolevel = db.connection.isolation_level
        db.connection.isolation_level = None # Disable autocommit
        with db.connection:
            cursor = db.connection.cursor()
            cursor.execute("BEGIN TRANSACTION")
            if create_sql:
                logger.info("Creating new table %s.",
                            grammar.quote(table, force=True))
                cursor.execute(create_sql)
            db.lock("table", table, filename)
            logger.info("Running import from %s%s to table %s.",
                        filename, (" sheet '%s'" % sheet) if sheet else "",
                        grammar.quote(table, force=True))
            index, count, errorcount = -1, 0, 0
            for row in iter_file_rows(filename, list(columns), sheet):
                index += 1
                if has_header and not index: continue # for row

                try:
                    cursor.execute(sql, row)
                    count += 1
                except Exception as e:
                    errorcount += 1
                    if not progress: raise

                    logger.exception("Error executing '%s' with %s.", sql, row)
                    if continue_on_error is None:
                        result = progress(error=util.format_exc(e), index=index,
                                          count=count, errorcount=errorcount)
                        if result:
                            continue_on_error = True
                            continue # for row
                        logger.info("Cancelling%s import on user request.",
                                    " and rolling back" if result is None else "")
                        if result is None: cursor.execute("ROLLBACK")
                        break # for row
                if progress and (count and not count % 100 or errorcount and not errorcount % 100):
                    result = progress(count=count, errorcount=errorcount)
                    if not result:
                        logger.info("Cancelling%s import on user request.",
                                    " and rolling back" if result is None else "")
                        if result is None: cursor.execute("ROLLBACK")
                        break # for row
            if result:
                cursor.execute("COMMIT")
                db.log_query("IMPORT", [create_sql, sql] if create_sql else [sql],
                             util.plural("row", count))
            logger.info("Finished importing %s from %s%s to table %s.",
                        util.plural("row", count),
                        filename, (" sheet '%s'" % sheet) if sheet else "",
                        grammar.quote(table, force=True))
            if progress: progress(count=count, errorcount=errorcount, done=True)
    except Exception as e:
        logger.exception("Error running import from %s%s to table %s.",
                         filename, (" sheet '%s'" % sheet) if sheet else "",
                         grammar.quote(table, force=True))
        if progress: progress(error=util.format_exc(e), done=True)
        result = False
    finally:
        db.connection.isolation_level = isolevel
        db.unlock("table", table, filename)

    if result is not None and create_sql:
        db.populate_schema(category="table", name=table, count=True, parse=True)
    elif result:
        db.populate_schema(category="table", name=table, count=True)

    return result



def iter_file_rows(filename, columns, sheet=None):
    """
    Yields rows as [value, ] from spreadsheet file.

    @param   filename    file path to open
    @param   columns     list of column indexes to return
    @param   sheet       sheet name to read from, if applicable
    """
    is_csv  = filename.lower().endswith(".csv")
    is_xls  = filename.lower().endswith(".xls")
    is_xlsx = filename.lower().endswith(".xlsx")
    if is_csv:
        with open(filename, "rbU") as f:
            firstline = next(f, "")

            if firstline.startswith("\xFF\xFE"): # Unicode little endian header
                try:
                    firstline = firstline.decode("utf-16") # GMail CSVs can be in UTF-16
                except UnicodeDecodeError:
                    firstline = firstline[2:].replace("\x00", "")
                else: # CSV has trouble with Unicode: turn back to string
                    firstline = firstline.encode("latin1", errors="xmlcharrefreplace")
            iterable = itertools.chain([firstline], f)
            csvfile = csv.reader(iterable, csv.Sniffer().sniff(firstline, ",;\t"))
            for row in csvfile:
                yield [row[i] for i in columns]
    elif is_xls:
        with xlrd.open_workbook(filename, on_demand=True) as wb:
            for row in wb.sheet_by_name(sheet).get_rows():
                yield [row[i].value if i < len(row) else None for i in columns]
    elif is_xlsx:
        wb = None
        try:
            wb = openpyxl.load_workbook(filename, data_only=True, read_only=True)
            for row in wb.get_sheet_by_name(sheet).iter_rows(values_only=True):
                yield [row[i] if i < len(row) else None for i in columns]
        finally: wb and wb.close()



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

    def __init__(self, filename, sheetname=None, autowrap=(), props=None):
        """
        @param   sheetname  title of the first sheet to create, if any
        @param   autowrap   a list of column indexes that will get their width
                            set to COL_MAXWIDTH and their contents wrapped
                 props      document properties like 'title', 'subject', etc
        """
        self._workbook = xlsxwriter.Workbook(filename,
            {"constant_memory": True, "strings_to_formulas": False})
        if props: self._workbook.set_properties(props)
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
                continue # for c, v

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
        self._workbook.close()
