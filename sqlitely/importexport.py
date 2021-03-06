# -*- coding: utf-8 -*-
"""
Functionality for exporting SQLite data to external files.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    03.07.2020
------------------------------------------------------------------------------
"""
import collections
import csv
import datetime
import functools
import itertools
import json
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
IMPORT_WILDCARD = "All supported formats (%s)|%s|%s%s"\
                  "CSV spreadsheet (*.csv)|*.csv|JSON data (*.json)|*.json" % (
    ";".join("*." + x for x in EXCEL_EXTS + ["csv"] + ["json"]),
    ";".join("*." + x for x in EXCEL_EXTS + ["csv"] + ["json"]),
    "All spreadsheets ({0})|{0}|".format(";".join("*." + x for x in EXCEL_EXTS + ["csv"])),
    "Excel workbook ({0})|{0}|".format(";".join("*." + x for x in EXCEL_EXTS))
    if EXCEL_EXTS else ""
)

"""FileDialog wildcard strings, matching extensions lists and default names."""
XLSX_WILDCARD = "Excel workbook (*.xlsx)|*.xlsx|" if xlsxwriter else ""

"""Wildcards for export file dialog."""
EXPORT_WILDCARD = ("CSV spreadsheet (*.csv)|*.csv|%s"
                   "HTML document (*.html)|*.html|"
                   "JSON data (*.json)|*.json|"
                   "SQL INSERT statements (*.sql)|*.sql|"
                   "Text document (*.txt)|*.txt" % XLSX_WILDCARD)
EXPORT_EXTS = ["csv", "xlsx", "html", "json", "sql", "txt"] if xlsxwriter \
               else ["csv", "html", "json", "sql", "txt"]

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
    f, cursor = None, None
    is_csv  = filename.lower().endswith(".csv")
    is_html = filename.lower().endswith(".html")
    is_json = filename.lower().endswith(".json")
    is_sql  = filename.lower().endswith(".sql")
    is_txt  = filename.lower().endswith(".txt")
    is_xlsx = filename.lower().endswith(".xlsx")
    columns = [{"name": c} if isinstance(c, basestring) else c for c in columns]
    colnames = [c["name"] for c in columns]
    tmpfile, tmpname = None, None # Temporary file for exported rows
    try:
        with open(filename, "wb") as f:
            if category and name: db.lock(category, name, make_iterable, label="export")
            count = 0
            cursor = make_iterable()

            if is_csv or is_xlsx:
                if is_csv:
                    dialect = csv.excel
                    dialect.delimiter = ";" # default "," is not actually used by Excel
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
                for i, row in enumerate(cursor, 1):
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
                    "columns":     columns,
                    "rows":        cursor,
                    "row_count":   0,
                    "sql":         query,
                    "category":    category,
                    "name":        name,
                    "progress":    progress,
                }
                namespace["namespace"] = namespace # To update row_count

                if is_txt: # Run through rows once, to populate text-justify options
                    widths = {c: len(util.unprint(c)) for c in colnames}
                    justs  = {c: True   for c in colnames}
                    try:
                        cursor2 = make_iterable()
                        for i, row in enumerate(cursor2):
                            for col in colnames:
                                v = row[col]
                                if isinstance(v, (int, long, float)): justs[col] = False
                                v = "" if v is None \
                                    else v if isinstance(v, basestring) else str(v)
                                v = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, unicode(v))
                                widths[col] = max(widths[col], len(v))
                            if not i % 100 and progress and not progress(): return
                    finally: util.try_until(lambda: cursor2.close())
                    namespace["columnwidths"] = widths # {col: char length}
                    namespace["columnjusts"]  = justs  # {col: True if ljust}
                if progress and not progress(): return

                # Write out data to temporary file first, to populate row count.
                tmpname = util.unique_path("%s.rows" % filename)
                tmpfile = open(tmpname, "wb+")
                template = step.Template(templates.DATA_ROWS_HTML if is_html else
                           templates.DATA_ROWS_SQL if is_sql else templates.DATA_ROWS_JSON
                           if is_json else templates.DATA_ROWS_TXT,
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
                    transform = {"flags": {"exists": True}} if is_sql else None
                    create_sql = db.get_sql(category, name, transform=transform)
                    namespace["create_sql"] = create_sql

                tmpfile.flush(), tmpfile.seek(0)
                namespace["data_buffer"] = iter(lambda: tmpfile.read(65536), "")
                template = step.Template(templates.DATA_HTML if is_html else
                           templates.DATA_SQL if is_sql else templates.DATA_JSON
                           if is_json else templates.DATA_TXT,
                           strip=False, escape=is_html)
                template.stream(f, namespace)
                count = namespace["row_count"]

            result = progress(count=count) if progress else True
    finally:
        if tmpfile:    util.try_until(tmpfile.close)
        if tmpname:    util.try_until(lambda: os.unlink(tmpname))
        if not result: util.try_until(lambda: os.unlink(filename))
        if cursor:     util.try_until(lambda: cursor.close())
        if category and name: db.unlock(category, name, make_iterable)

    return result


def export_data_multiple(filename, title, db, category, progress=None):
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
    items, cursor = db.schema[category], None
    try:
        props = {"title": title, "comments": templates.export_comment()}
        writer = xlsx_writer(filename, props=props)

        for n in items: db.lock(category, n, filename, label="export")
        for name, item in items.items():
            count = 0
            if progress and not progress(name=name, count=count):
                result = False
                break # for name, item

            try:
                cursor = db.execute("SELECT * FROM %s" % grammar.quote(name))
                row = next(cursor, None)
                iterable = itertools.chain([] if row is None else [row], cursor)

                writer.add_sheet(name)
                colnames = [x["name"] for x in item["columns"]]
                writer.set_header(True)
                writer.writerow(colnames, "bold")
                writer.set_header(False)

                for i, row in enumerate(iterable, 1):
                    count = i
                    writer.writerow([row[c] for c in colnames])
                    if not i % 100 and progress and not progress(name=name, count=i):
                        result = False
                        break # for i, row
            except Exception as e:
                logger.exception("Error exporting %s %s from %s.", category, grammar.quote(name), db)
                if progress and not progress(name=name, error=util.format_exc(e)):
                    result = False
            finally: util.try_until(lambda: cursor.close())

            if not result: break # for name, item
            if progress and not progress(name=name, count=count):
                result = False
                break # for name, item
        writer.close()
        if progress: progress(done=True)
    except Exception as e:
        logger.exception("Error exporting %s from %s to %s.",
                         util.plural(category), db, filename)
        if progress: progress(error=util.format_exc(e), done=True)
        result = False
    finally:
        for n in items: db.unlock(category, n, filename)
        util.try_until(lambda: cursor.close())
        if not result: util.try_until(lambda: os.unlink(filename))

    return result


def export_sql(filename, db, sql, title=None):
    """Exports arbitrary SQL to file."""
    template = step.Template(templates.CREATE_SQL, strip=False)
    ns = {"title": title, "db_filename": db.name, "sql": sql}
    with open(filename, "wb") as f: template.stream(f, ns)
    return True


def export_stats(filename, db, data):
    """Exports statistics to HTML or SQL file."""
    filetype  = os.path.splitext(filename)[1][1:].lower()
    TPLARGS = {"html": (templates.DATA_STATISTICS_HTML, dict(escape=True, strip=False)),
               "sql":  (templates.DATA_STATISTICS_SQL,  dict(strip=False)),
               "txt":  (templates.DATA_STATISTICS_TXT,  dict(strip=False))}
    template = step.Template(TPLARGS[filetype][0], **TPLARGS[filetype][1])
    ns = {
        "title":  "Database statistics",
        "db":     db,
        "pragma": db.get_pragma_values(stats=True),
        "sql":    db.get_sql(),
        "stats":  data.get("data", {}),
    }
    with open(filename, "wb") as f: template.stream(f, ns)
    return True


def export_dump(filename, db, progress=None):
    """
    Exports full database dump to SQL file.

    @param   progress        callback(name, count) to report progress,
                             returning false if export should cancel
    """
    result = False
    tables, namespace, cursors = db.schema["table"], {}, []

    def gen(func, *a, **kw):
        cursor = func(*a, **kw)
        cursors.append(cursor)
        for x in cursor: yield x

    try:
        with open(filename, "wb") as f:
            db.lock(None, None, filename, label="database dump")
            namespace = {
                "db":       db,
                "sql":      db.get_sql(),
                "data":     [{"name": t, "columns": opts["columns"],
                              "rows": gen(db.execute, "SELECT * FROM %s" % grammar.quote(t))}
                             for t, opts in tables.items()],
                "pragma":   db.get_pragma_values(dump=True),
                "progress": progress,
                "buffer":   f,
            }
            template = step.Template(templates.DUMP_SQL, strip=False)
            template.stream(f, namespace, unbuffered=True)
            result = progress() if progress else True
    except Exception as e:
        logger.exception("Error exporting database dump from %s to %s.",
                         db, filename)
        if progress: progress(error=util.format_exc(e), done=True)
        result = False
    finally:
        db.unlock(None, None, filename)
        for x in cursors: util.try_until(x.close)
        if not result: util.try_until(lambda: os.unlink(filename))

    return result


def export_to_db(db, filename, schema, renames=None, data=False, selects=None, progress=None):
    """
    Exports selected tables and views to another database, structure only or
    structure plus data, auto-creating table and view indexes and triggers.

    @param   filename  database filename to export to
    @param   schema    {category: [name, ]} to export
    @param   renames   {category: {name1: name2}}
    @param   data      whether to export table data
    @param   selects   {table name: SELECT SQL if not using default}
    @param   progress  callback(?name, ?error) to report export progress,
                       returning false if export should cancel
    """
    result = True
    CATEGORIES = "table", "view"
    sqls0, sqls1, actionsqls = [], [], []
    requireds, processeds, exporteds = {}, set(), set()

    is_samefile = util.lceq(db.filename, filename)
    file_existed = is_samefile or os.path.isfile(filename)
    insert_sql = "INSERT INTO %s.%s SELECT * FROM main.%s;"

    for category, name in ((c, n) for c, nn in schema.items() for n in nn):
        items = [db.schema[category][name]]
        items.extend(db.get_related(category, name, own=True).get("trigger", {}).values())
        for item in items:
            # Foreign tables and tables/views used in triggers for table,
            # tables/views used in view body and view triggers for view.
            for name2 in util.get(item, "meta", "__tables__"):
                if util.lceq(name, name2): continue # for name2
                requireds.setdefault(name, []).append(name2)

    finalargs = {"done": True}
    db.lock(None, None, filename, label="database export")
    try:
        schema2 = "main"
        if not is_samefile:
            schemas = [x.values()[1] for x in
                       db.execute("PRAGMA database_list").fetchall()]
            schema2 = util.make_unique("main", schemas, suffix="%s")
            db.execute("ATTACH DATABASE ? AS %s;" % schema2, [filename])
            sqls0.append("ATTACH DATABASE ? AS %s;" % schema2)
        myrenames = dict(renames or {}, schema=schema2)

        allnames2 = util.CaselessDict({x["name"]: x["type"] for x in db.execute(
            "SELECT name, type FROM %s.sqlite_master" % schema2
        ).fetchall()})

        fks_on = db.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"]
        if fks_on:
            db.execute("PRAGMA foreign_keys = off;")
            sqls0.append("PRAGMA foreign_keys = off;")


        for category, name in ((c, x) for c in CATEGORIES for x in schema.get(c, ())):
            name2 = renames.get(category, {}).get(name, name)
            processeds.add(name)

            if requireds.get(name) \
            and any(x in processeds and x not in exporteds for x in requireds[name]):
                # Skip item if it requires something that failed to export
                reqs = {}
                for name0 in requireds[name]:
                    if name0 in processeds and name0 not in exporteds:
                        category0 = "table" if name0 in db.schema.get("table", {}) else "view"
                        reqs.setdefault(category0, set()).add(name0)
                err = "Requires %s" % " and ".join(
                    "%s %s" % (util.plural(c, vv, numbers=False),
                               ", ".join(grammar.quote(v, force=True)
                                         for v in sorted(vv, key=lambda x: x.lower())))
                    for c, vv in sorted(reqs.items())
                )
                if progress and not progress(name=name, error=err):
                    result = False
                    break # for category, name
                else: continue # for category, name

            try:
                # Create table or view structure
                label = "%s %s" % (category, grammar.quote(name, force=True))
                if name != name2: label += " as %s" % grammar.quote(name2, force=True)

                if name2 in allnames2:
                    logger.info("Dropping %s %s in %s.", allnames2[name2], grammar.quote(name2, force=True), filename)
                    sql = "DROP %s %s.%s;" % (allnames2[name2].upper(), schema2, grammar.quote(name2))
                    db.execute(sql)
                    actionsqls.append(sql)

                logger.info("Creating %s in %s.", label, filename)
                sql, err = grammar.transform(db.schema[category][name]["sql"], renames=myrenames)
                if err:
                    if progress and not progress(name=name, error=err):
                        result = False
                        break # for category, name
                    else: continue # for category, name
                db.execute(sql)
                actionsqls.append(sql)
                if not data or "table" != category: exporteds.add(name)
                allnames2[name2] = category

                # Copy table data
                if data and "table" == category:
                    if selects and name in selects:
                        sql = "INSERT INTO %s.%s %s;" % (
                              schema2, grammar.quote(name2), selects[name])
                    else:
                        sql = insert_sql % (schema2, grammar.quote(name2),
                                            grammar.quote(name))
                    logger.info("Copying data to %s in %s.", label, filename)
                    db.execute(sql)
                    actionsqls.append(sql)
                    exporteds.add(name)

                # Create indexes and triggers for tables, triggers for views
                relateds = db.get_related(category, name, own=True)
                for subcategory, subitemmap in relateds.items():
                    for subname, subitem in subitemmap.items():
                        subname2 = subname
                        if name != name2:
                            subname2 = re.sub(re.escape(name), re.sub(r"\W", "", name2),
                                              subname2, count=1, flags=re.I | re.U)
                        subname2 = util.make_unique(subname2, allnames2)
                        allnames2[subname2] = subcategory

                        sublabel = "%s %s" % (subcategory, grammar.quote(subname, force=True))
                        if subname != subname2: sublabel += " as %s" % grammar.quote(subname2, force=True)
                        logger.info("Creating %s for %s in %s.", sublabel, label, filename)
                        subrenames = dict(myrenames, **{subcategory: {subname: subname2}}
                                                     if subname != subname2 else {})
                        sql, err = grammar.transform(subitem["sql"], renames=subrenames)
                        if sql:
                            db.execute(sql)
                            actionsqls.append(sql)
            except Exception as e:
                logger.exception("Error exporting %s %s from %s to %s.",
                                 category, grammar.quote(name, force=True),
                                 db, filename)
                if progress and not progress(name=name, error=util.format_exc(e)):
                    result = False
                    break # for category, name
            else:
                if progress and not progress(name=name):
                    result = False
                    break # for category, name
    except Exception as e:
        logger.exception("Error exporting from %s to %s.", db, filename)
        finalargs["error"] = util.format_exc(e)
    finally:
        if fks_on:
            try:
                db.execute("PRAGMA foreign_keys = on;")
                sqls1.append("PRAGMA foreign_keys = on;")
            except Exception: pass
        try: 
            db.execute("DETACH DATABASE %s;" % schema2)
            sqls1.append("DETACH DATABASE %s;" % schema2)
        except Exception: pass
        if not file_existed and (not actionsqls or not result):
            util.try_until(lambda: os.unlink(filename))
        db.unlock(None, None, filename)

    result = bool(actionsqls)
    if result: db.log_query("EXPORT TO DB", sqls0 + actionsqls + sqls1,
                            params=None if is_samefile else filename)

    if progress: progress(**finalargs)
    return result
    


def get_import_file_data(filename):
    """
    Returns import file metadata, as {
        "name":        file name and path}.
        "size":        file size in bytes,
        "format":      "xlsx", "xlsx", "csv" or "json",
        "sheets":      [
            "name":    sheet name or None if CSV or JSON,
            "rows":    count or -1 if file too large,
            "columns": [first row cell value, ],
    ]}.
    """
    logger.info("Getting import data from %s.", filename)
    sheets, size = [], os.path.getsize(filename)
    if not size: raise ValueError("File is empty.")

    extname = os.path.splitext(filename)[-1][1:].lower()
    is_csv, is_json, is_xls, is_xlsx = \
        (extname == x for x in ("csv", "json", "xls", "xlsx"))
    if is_csv:
        with open(filename, "rbU") as f:
            firstline = next(f, "")

            if firstline.startswith("\xFF\xFE"): # Unicode little endian header
                try:
                    firstline = firstline.decode("utf-16") # GMail CSVs can be in UTF-16
                except UnicodeDecodeError:
                    firstline = firstline[2:].replace("\x00", "")
                else: # CSV has trouble with Unicode: turn back to str
                    firstline = firstline.encode("latin1", errors="xmlcharrefreplace")
            iterable = itertools.chain([firstline], f)
            csvfile = csv.reader(iterable, csv.Sniffer().sniff(firstline, ",;\t"))
            rows, columns = -1, next(csvfile)
            if 0 < size <= MAX_IMPORT_FILESIZE_FOR_COUNT:
                rows = sum((1 for _ in csvfile), 1 if firstline else 0)
        sheets.append({"rows": rows, "columns": columns, "name": "<no name>"})
    elif is_json:
        rows, columns, buffer, started = 0, {}, "", False
        decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
        with open(filename, "rbU") as f:
            for chunk in iter(functools.partial(f.read, 2**16), ""):
                buffer += chunk
                if not started: # Strip line comments and list start from beginning
                    buffer = re.sub("^//[^\n]*$", "", buffer.lstrip(), flags=re.M).lstrip()
                    if buffer[:1] == "[": buffer, started = buffer[1:].lstrip(), True
                while started and buffer:
                    # Strip whitespace and interleaving commas from between dicts
                    buffer = re.sub(r"^\s*[,]?\s*", "", buffer)
                    try:
                        data, index = decoder.raw_decode(buffer)
                        buffer = buffer[index:]
                        if isinstance(data, collections.OrderedDict):
                            columns, rows = columns or data, rows + 1
                    except ValueError: # Not enough data to decode, read more
                        break # while started and buffer
                if columns and any(x > MAX_IMPORT_FILESIZE_FOR_COUNT for x in (size, f.tell())):
                    break # for chunk
            if rows and f.tell() < size: rows = -1
        sheets.append({"rows": rows, "columns": columns, "name": "<JSON data>"})
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

    return {"name": filename, "size": size, "format": extname, "sheets": sheets}



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
    @param   has_header  whether the spreadsheet file has a header row
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

    continue_on_error, cursor = None, None
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
            db.lock("table", table, filename, label="import")
            logger.info("Running import from %s%s to table %s.",
                        filename, (" sheet '%s'" % sheet) if sheet else "",
                        grammar.quote(table, force=True))
            index, count, errorcount = -1, 0, 0
            for row in iter_file_rows(filename, list(columns), sheet):
                index += 1
                if has_header and not index: continue # for row
                lastcount, lasterrorcount = count, errorcount

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
                if progress and (count != lastcount and not count % 100 or
                                 errorcount != lasterrorcount and not errorcount % 100):
                    result = progress(count=count, errorcount=errorcount)
                    if not result:
                        logger.info("Cancelling%s import on user request.",
                                    " and rolling back" if result is None else "")
                        if result is None: cursor.execute("ROLLBACK")
                        break # for row
            if result:
                cursor.execute("COMMIT")
                db.log_query("IMPORT", [create_sql, sql] if create_sql else [sql],
                             [filename, util.plural("row", count)])
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
        util.try_until(lambda: cursor.close())
        db.unlock("table", table, filename)

    if result is not None and create_sql:
        db.populate_schema(category="table", name=table, parse=True)
    elif result:
        db.populate_schema(category="table", name=table)

    return result



def iter_file_rows(filename, columns, sheet=None):
    """
    Yields rows as [value, ] from spreadsheet or JSON file.

    @param   filename    file path to open
    @param   columns     list of column indexes to return
    @param   sheet       sheet name to read from, if applicable
    """
    size = os.path.getsize(filename)
    is_csv  = filename.lower().endswith(".csv")
    is_json = filename.lower().endswith(".json")
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
                yield [row[i] if i < len(row) else None for i in columns]
    elif is_json:
        started, buffer = False, ""
        decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
        with open(filename, "rbU") as f:
            for chunk in iter(functools.partial(f.read, 2**16), ""):
                buffer += chunk
                if not started: # Strip line comments and list start from beginning
                    buffer = re.sub("^//[^\n]*$", "", buffer.lstrip(), flags=re.M).lstrip()
                    if buffer[:1] == "[": buffer, started = buffer[1:].lstrip(), True
                while started and buffer:
                    # Strip whitespace and interleaving commas from between dicts
                    buffer = re.sub(r"^\s*[,]?\s*", "", buffer)
                    try:
                        data, index = decoder.raw_decode(buffer)
                        buffer = buffer[index:]
                        if isinstance(data, collections.OrderedDict):
                            row = data.values()
                            if len(row) < len(columns):
                                row += [None] * (len(columns) - len(row))
                            yield row
                    except ValueError: # Not enough data to decode, read more
                        break # while started and buffer
                if f.tell() >= size: break # for chunk
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
