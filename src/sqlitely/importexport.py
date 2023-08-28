# -*- coding: utf-8 -*-
"""
Functionality for exporting SQLite data to external files.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    21.08.2023
------------------------------------------------------------------------------
"""
from __future__ import print_function
import codecs
import collections
import copy
import csv
import datetime
import functools
import json
import logging
import os
import re
import sys
import tempfile
import warnings

# ImageFont for calculating column widths in Excel export, not required.
try: from PIL import ImageFont
except ImportError: ImageFont = None
try: import chardet
except ImportError: chardet = None
try: import openpyxl
except ImportError: openpyxl = None
try: import yaml
except ImportError: yaml = None
try: import xlrd
except ImportError: xlrd = None
try: import xlsxwriter
except ImportError: xlsxwriter = None
import six

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
YAML_EXTS = ["yaml", "yml"] if yaml else []
IMPORT_EXTS = EXCEL_EXTS + ["csv", "json"] + YAML_EXTS
IMPORT_WILDCARD = "|".join(filter(bool, [
    "All supported formats ({0})|{0}".format(";".join("*." + x for x in IMPORT_EXTS)),
    "CSV spreadsheet (*.csv)|*.csv",
    "JSON data (*.json)|*.json",
    "All spreadsheets ({0})|{0}".format(";".join("*." + x for x in EXCEL_EXTS + ["csv"]))
    if EXCEL_EXTS else None,
    "Excel workbook ({0})|{0}".format(";".join("*." + x for x in EXCEL_EXTS))
    if EXCEL_EXTS else None,
    "YAML data ({0})|{0}".format(";".join("*." + x for x in YAML_EXTS))
    if YAML_EXTS else None,
]))


"""All supported export formats."""
EXPORT_EXTS = list(filter(bool, [
    "csv", xlsxwriter and "xlsx", "html", "json", "sql", "txt", yaml and "yaml"
]))
"""All export formats printable to console in CLI mode."""
PRINTABLE_EXTS = [x for x in EXPORT_EXTS if x not in ("html", "xlsx")]
"""Readable names for export formats."""
EXT_NAMES = {
    "csv":  "CSV spreadsheet",
    "db":   "SQLite database",
    "html": "HTML document",
    "json": "JSON data",
    "sql":  "SQL statements",
    "txt":  "text document",
    "xlsx": "Excel workbook",
    "yaml": "YAML data",
}
"""Wildcards for export file dialog."""
EXPORT_WILDCARD = "|".join("%s (*.%s)|*.%s" % (util.cap(EXT_NAMES[x]), x, x) for x in EXPORT_EXTS)


logger = logging.getLogger(__name__)



def export_data(make_iterable, filename, format, title, db, columns,
                query="", category="", name="", multiple=False, progress=None):
    """
    Exports database data to file.

    @param   make_iterable   function returning iterable sequence yielding rows
    @param   filename        full path and filename of resulting file
    @param   format          file format like "csv"
    @param   title           export title, as string or a sequence of strings
    @param   db              Database instance
    @param   columns         iterable columns, as [name, ] or [{"name": name}, ]
    @param   query           the SQL query producing the data, if any
    @param   category        category producing the data, if any, "table" or "view"
    @param   name            name of the table or view producing the data, if any
    @param   multiple        whether to use multi-item template
    @param   progress        callback(name, count) to report progress,
                             returning false if export should cancel
    @return                  True on success, False on failure, None on cancel
    """
    result = False
    f, writer, cursor = None, None, None
    TEMPLATES = {
        "root": {
            "html": templates.DATA_HTML_MULTIPLE_PART if multiple else templates.DATA_HTML,
            "json": templates.DATA_JSON,
            "sql":  templates.DATA_SQL_MULTIPLE_PART  if multiple else templates.DATA_SQL,
            "txt":  templates.DATA_TXT_MULTIPLE_PART  if multiple else templates.DATA_TXT,
            "yaml": templates.DATA_YAML_MULTIPLE_PART if multiple else templates.DATA_YAML,
        },
        "rows": {
            "html": templates.DATA_ROWS_HTML,
            "json": templates.DATA_ROWS_JSON,
            "sql":  templates.DATA_ROWS_SQL,
            "txt":  templates.DATA_ROWS_TXT,
            "yaml": templates.DATA_ROWS_YAML,
        },
    }

    columns = [{"name": c} if isinstance(c, six.string_types) else c for c in columns]
    colnames = [c["name"] for c in columns]
    tmpfile, tmpname = None, None # Temporary file for exported rows
    try:
        with open(filename, "wb") as f:
            if category and name: db.lock(category, name, make_iterable, label="export")
            count = 0
            cursor = make_iterable()

            if format in ("csv", "xlsx"):
                f.close()
                if "csv" == format:
                    writer = csv_writer(filename)
                    if query: query = query.replace("\r", " ").replace("\n", " ")
                else:
                    props = {"title": "; ".join(("Source: %s" % db, ) + util.tuplefy(title)),
                             "comments": templates.export_comment()}
                    writer = xlsx_writer(filename, name or "SQL Query", props=props)
                    writer.set_header(True)
                if query:
                    a = [[query]] + (["bold", 0, False] if "xlsx" == format else [])
                    writer.writerow(*a)
                writer.writerow(*([colnames, "bold"] if "xlsx" == format else [colnames]))
                writer.set_header(False) if "xlsx" == format else 0
                for i, row in enumerate(cursor, 1):
                    writer.writerow(["" if row[c] is None else row[c] for c in colnames])
                    count = i
                    if not i % 100 and progress and not progress(name=name, count=i): return None
                writer.close()
                writer = None
            else:
                namespace = {
                    "db":         db,
                    "title":      title,
                    "columns":    columns,
                    "rows":       cursor,
                    "row_count":  0,
                    "sql":        query,
                    "category":   category,
                    "name":       name,
                    "multiple":   multiple,
                    "progress":   progress,
                }
                namespace["namespace"] = namespace # To update row_count

                if "txt" == format: # Run through rows once, to populate text-justify options
                    widths = {c: len(util.unprint(c)) for c in colnames}
                    justs  = {c: True   for c in colnames}
                    try:
                        cursor2 = make_iterable()
                        for i, row in enumerate(cursor2):
                            for col in colnames:
                                v = row[col]
                                if isinstance(v, six.integer_types + (float, )): justs[col] = False
                                v = "" if v is None \
                                    else v if isinstance(v, six.string_types) else str(v)
                                v = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, six.text_type(v))
                                widths[col] = max(widths[col], len(v))
                            if not i % 100 and progress and not progress(): return None
                    finally: util.try_ignore(lambda: cursor2.close())
                    namespace["columnwidths"] = widths # {col: char length}
                    namespace["columnjusts"]  = justs  # {col: True if ljust}
                if progress and not progress(): return None

                # Write out data to temporary file first, to populate row count.
                fh, tmpname = tempfile.mkstemp(prefix="%s.rows." % os.path.basename(filename))
                tmpfile = open(fh, "wb+")
                template = step.Template(TEMPLATES["rows"][format], postprocess=convert_lf,
                                         strip=False, escape="html" == format)
                template.stream(tmpfile, namespace)

                if progress and not progress(): return None

                if "sql" == format and "view" == category:
                    # Add CREATE statement for saving view AS table
                    meta = {"name": name, "columns": columns, "sql": db.get_sql(category, name)}
                    tpl = step.Template(templates.CREATE_VIEW_TABLE_SQL, strip=False)
                    namespace["create_sql"] = tpl.expand(**meta).strip()
                elif name:
                    # Add CREATE statement
                    transform = {"flags": {"exists": True}} if "sql" == format else None
                    create_sql = db.get_sql(category, name, transform=transform)
                    namespace["create_sql"] = create_sql

                tmpfile.flush(), tmpfile.seek(0)
                namespace["data_buffer"] = iter(lambda: tmpfile.read(65536), b"")
                template = step.Template(TEMPLATES["root"][format], postprocess=convert_lf,
                                         strip=False, escape="html" == format)
                template.stream(f, namespace)
                count = namespace["row_count"]

            result = progress(name=name, count=count) if progress else True
    finally:
        if writer:     util.try_ignore(writer.close)
        if tmpfile:    util.try_ignore(tmpfile.close)
        if tmpname:    util.try_ignore(os.unlink, tmpname)
        if not result: util.try_ignore(os.unlink, filename)
        if cursor:     util.try_ignore(lambda: cursor.close())
        if category and name: db.unlock(category, name, make_iterable)

    return result



def export_data_multiple(filename, format, title, db, category=None, make_iterables=None,
                         limit=None, maxcount=None, empty=True, reverse=False, progress=None):
    """
    Exports database data from multiple tables/views to a single output file.

    @param   filename        full path and filename of resulting file
    @param   format          file format like "csv"
    @param   title           export title, as string or a sequence of strings
    @param   db              Database instance
    @param   category        category to produce the data from, "table" or "view", or None for both
    @param   make_iterables  function yielding pairs of ({info}, function yielding rows)
                             if not using category
    @param   limit           export limits per entity if any, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
    @param   maxcount        maximum total number of rows to export over all entities
    @param   empty           do not skip tables and views with no output rows
    @param   reverse         query rows in reverse order if using category
    @param   progress        callback(name, count) to report progress,
                             returning false if export should cancel
    @return                  True on success, False on failure, None on cancel
    """
    result = True
    f, writer, cursor = None, None, None
    TEMPLATES = {"html": templates.DATA_HTML_MULTIPLE,
                 "json": templates.DATA_JSON_MULTIPLE,
                 "sql":  templates.DATA_SQL_MULTIPLE,
                 "txt":  templates.DATA_TXT_MULTIPLE,
                 "yaml": templates.DATA_YAML_MULTIPLE}

    limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else util.tuplefy(limit)
    itemfiles = collections.OrderedDict() # {data name: path to partial file containing item data}
    categories = [] if make_iterables else [category] if category else db.DATA_CATEGORIES
    items = {c: db.schema[c].copy() for c in categories}
    counts = collections.defaultdict(int) # {name: number of rows yielded}
    for category, name in ((c, n) for c, x in items.items() for n in x):
        db.lock(category, name, filename, label="export")
    if not make_iterables:

        def make_item_iterable(name):
            """Returns cursor yielding rows from entity, auto-closed on error."""
            order_sql = db.get_order_sql(name, reverse=True) if reverse else ""
            limit_sql = db.get_limit_sql(*limit, maxcount=maxcount, totals=counts)
            sql = "SELECT * FROM %s%s%s" % (grammar.quote(name), order_sql, limit_sql)

            category = next((c for c in db.schema if name in db.schema[c]), "")
            msg = "Error querying %s %s." % (category, grammar.quote(name, force=True))
            tick = lambda n: counts.update({name: n})
            return db.select(sql, error=msg, tick=tick)

        def make_item_iterables():
            """Yields pairs of ({item}, callable returning iterable cursor)."""
            for category, item in ((c, x) for c, d in items.items() for x in d.values()):
                title = "%s %s" % (category.capitalize(), grammar.quote(item["name"], force=True))
                yield dict(item, title=title), functools.partial(make_item_iterable, item["name"])

    elif limit or maxcount is not None:

        def make_item_iterable(item, make_iterable):
            """Returns function returning generator yielding rows, using limits."""
            def inner():
                mylimit = limit
                if maxcount is not None:
                    mymax = min(maxcount, limit[0] if limit and limit[0] >= 0 else maxcount)
                    mylimit = [max(0, mymax - sum(counts.values()))] + list(limit[1:])
                qrange = (0, mylimit[0]) if mylimit else None
                qrange = (mylimit[1], (mylimit[1] + mylimit[0]) if mylimit[0] > 0 else -1) \
                         if mylimit and len(mylimit) > 1 else qrange

                cursor = None
                try:
                    cursor = make_iterable()
                    for i, x in enumerate(cursor) if not qrange else ():
                        yield x
                        counts[name] += 1
                    for i, x in enumerate(cursor) if qrange else ():
                        if i < qrange[0]: continue # for
                        if qrange[1] >= 0 and i >= qrange[1]: break # for

                        yield x
                        counts[name] += 1
                except Exception:
                    logger.warning("Error querying %s %s.",
                                   item["type"], grammar.quote(item["name"], force=True),
                                   exc_info=True)
                finally:
                    util.try_ignore(lambda: cursor.close())

            return inner

        def make_item_iterables():
            """Yields pairs of ({item}, callable returning iterable cursor)."""
            for item, make_iterable in make_iterables():
                yield item, make_item_iterable(item, make_iterable)
    else:
        make_item_iterables = make_iterables

    try:
        with open(filename, "wb") as f:
            if format in ("csv", "xlsx"):
                f.close()
                if "csv" == format:
                    writer = csv_writer(filename)
                else:
                    props = {"title": "; ".join(("Source: %s" % db, ) + util.tuplefy(title)),
                             "comments": templates.export_comment()}
                    writer = xlsx_writer(filename, props=props)

            for item_i, (item, make_iterable) in enumerate(make_item_iterables()):
                name = item["name"]

                if format in ("csv", "xlsx"):
                    colnames, cursor, i = [x["name"] for x in item["columns"]], make_iterable(), 0

                    for i, row in enumerate(cursor, 1):
                        if i == 1:
                            if "csv" == format:
                                if item_i: writer.writerow([])   # Blank row between items
                                writer.writerow([name])          # Item name on separate line
                                writer.writerow([""] + colnames) # Start item data from 2nd col
                            else:
                                writer.add_sheet(name)
                                writer.set_header(True)
                                writer.writerow(colnames, "bold")
                                writer.set_header(False)

                        writer.writerow(([""] if "csv" == format else []) +
                                        ["" if row[c] is None else row[c] for c in colnames])
                        if not i % 100 and progress and not progress(name=name, count=i):
                            result = False
                            util.try_ignore(lambda: cursor.close())
                            break # for i, row
                    if progress and not progress(name=name, count=i):
                        result = False
                        break # for i, row
                else:
                    if not empty:
                        cursor = make_iterable()
                        is_empty, _ = not any(cursor), util.try_ignore(lambda: cursor.close())
                        if is_empty: continue # for item_i

                    # Write item data to temporary file, later inserted into main file
                    tmpname = util.unique_path("{0}_{2}{1}".format(*os.path.splitext(filename) + 
                                                                    (util.safe_filename(name), )))
                    itemtitle = "%s %s" % (item["type"].capitalize(),
                                           grammar.quote(name, force=True))
                    result = export_data(make_iterable, tmpname, format, itemtitle, db,
                                         item["columns"], category=item["type"], name=name,
                                         multiple=True, progress=progress)
                    itemfiles[tmpname] = item

                if not result: break # for item_i
                if progress and not progress():
                    result = False
                    break # for item_i

            if result and format not in ("csv", "xlsx"):
                # Produce main export file, combined from partial files
                template = step.Template(TEMPLATES[format], postprocess=convert_lf,
                                         strip=False, escape="html" == format)
                namespace = {
                    "db":       db,
                    "title":    title,
                    "files":    itemfiles,
                    "progress": progress,
                }
                template.stream(f, namespace)
            result = progress() if progress else True
    except Exception as e:
        logger.exception("Error exporting from %s to %s.", db, filename)
        if progress: progress(error=util.format_exc(e), done=True)
        result = False
    finally:
        if writer:     util.try_ignore(writer.close)
        if cursor:     util.try_ignore(lambda: cursor.close())
        if not result: util.try_ignore(os.unlink, filename)
        for n in itemfiles:
            util.try_ignore(os.unlink, n)
        for category, name in ((c, n) for c, x in items.items() for n in x):
            db.unlock(category, name, filename)

    return result


def export_sql(filename, db, sql, headers=()):
    """Exports arbitrary SQL to file."""
    template = step.Template(templates.CREATE_SQL, strip=False, postprocess=convert_lf)
    ns = {"headers": util.tuplefy(headers) if headers else (), "db": db, "sql": sql}
    with open(filename, "wb") as f: template.stream(f, ns)
    return True


def export_stats(filename, format, db, data, diagram=None):
    """Exports statistics to HTML or SQL or TXT file."""
    TEMPLATES = {"html": templates.DATA_STATISTICS_HTML,
                 "sql":  templates.DATA_STATISTICS_SQL,
                 "txt":  templates.DATA_STATISTICS_TXT}
    template = step.Template(TEMPLATES[format], postprocess=convert_lf,
                             strip=False, escape="html" == format)
    ns = {
        "title":  "Database statistics",
        "db":     db,
        "pragma": db.get_pragma_values(stats=True),
        "sql":    db.get_sql(),
        "stats":  data,
    }
    if diagram: ns["diagram"] = diagram
    with open(filename, "wb") as f: template.stream(f, ns)
    return True


def export_dump(filename, db, data=True, pragma=True, filters=None, related=False,
                limit=None, maxcount=None, empty=True, reverse=False, progress=None):
    """
    Exports full database dump to SQL file.

    @param   db        Database instance
    @param   data      whether to dump table data
    @param   pragma    whether to dump PRAGMA settings
    @param   filters   names of database entities to dump if not all,
                       supports * wildcards
    @param   related   auto-include related items if using filters, recursively
                       (for tables: indexes and triggers, and referenced foreign tables;
                        for views: triggers, and tables and views referenced in view body;
                        for indexes: parent tables;
                        for triggers: parent tables or views, and referenced tables and views)
    @param   limit     query limits, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
    @param   maxcount  maximum total number of rows to export over all tables
    @param   empty     do not skip items with no output rows
                       (accounting for limit)
    @param   reverse   query rows in reverse order
    @param   progress  callback(name, count) to report progress,
                       returning false if export should cancel
    @return            True on success, False on failure, None on cancel
    """
    result = False
    entities, namespace, cursors = copy.deepcopy(db.schema), {}, []
    limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else util.tuplefy(limit)
    related_includes = collections.defaultdict(list) # {name: [name of owned or required entity, ]}
    counts = collections.defaultdict(int) # {name: number of rows yielded}

    def make_iterable(name):
        """Yields rows from table or view, using limit and maxcount."""
        order_sql = db.get_order_sql(name, reverse=True) if reverse else ""
        limit_sql = db.get_limit_sql(*limit, maxcount=maxcount, totals=counts)
        sql = "SELECT * FROM %s%s%s" % (grammar.quote(name), order_sql, limit_sql)

        msg = "Error querying table %s." % grammar.quote(name, force=True)
        tick = lambda n: counts.update({name: n})
        cursors.append(db.select(sql, error=msg, tick=tick))
        return cursors[-1]

    def make_datas():
        """Yields {name, columns, rows} for each table to export."""
        for n, item in entities["table"].items():
            if progress and not progress(name=n): break # for n, item

            yield {"name": n, "columns": item["columns"], "rows": make_iterable(n)}
            if progress and not progress(name=n, done=True): break # for n, item

    if filters:
        entities.clear()
        rgx = util.filters_to_regex(filters)
        # Select all entities matching by name
        default_includes = util.CaselessDict()
        for category in db.schema:
            for name, item in db.schema[category].items():
                if rgx.match(name):
                    entities[category][name] = item
                    default_includes[name] = True
        # Select all owned or referred entities
        for item in [x for d in entities.values() for x in d.values()] if related else ():
            rels, related_includes = db.get_full_related(item["type"], item["name"])
            for category2, items2 in rels.items():
                for name2, item2 in items2.items():
                    if name2 not in default_includes:
                        entities[category2][name2] = item2
                        related_includes[item["name"]].append(name2)

    if not empty:
        empties = []
        offset_sql = " OFFSET %s" % limit[1] if len(limit) > 1 else ""
        for category, name in [(c, n) for c in db.DATA_CATEGORIES for n in entities.get(c, {})]:
            sql = "SELECT 1 FROM %s LIMIT 1%s" % (grammar.quote(name), offset_sql)
            if not any(db.select(sql, error="Error checking count in %s %s." %
                       (category, grammar.quote(name, force=True)))):
                empties.append(name)

        while empties:
            name = empties.pop(0)
            item = next(d[name] for d in db.schema.values() if name in d)
            if item["name"] not in entities.get(item["type"], {}): continue # while

            entities[item["type"]].pop(item["name"])
            if item["type"] in ("table", "view"):
                for rels in db.get_related(item["type"], item["name"], own=True).values():
                    empties.extend(rels)
            empties.extend(related_includes.get(item["name"], []))

    if filters or not empty:
        sql = "\n\n".join("\n\n".join(v["sql"] for v in entities[c].values())
                          for c in db.CATEGORIES)
    else:
        sql = db.get_sql()

    try:
        with open(filename, "wb") as f:
            db.lock(None, None, filename, label="database dump")
            namespace = {
                "db":       db,
                "sql":      sql,
                "data":     make_datas() if data else [],
                "pragma":   db.get_pragma_values(dump=True) if pragma else {},
                "progress": progress,
                "buffer":   f,
            }
            template = step.Template(templates.DUMP_SQL, strip=False, postprocess=convert_lf)
            template.stream(f, namespace, buffer_size=0)
            result = None if progress and not progress(done=True) else True
    except Exception as e:
        logger.exception("Error exporting database dump from %s to %s.",
                         db, filename)
        if progress: progress(error=util.format_exc(e), done=True)
        result = False
    finally:
        db.unlock(None, None, filename)
        for x in cursors: util.try_ignore(x.close)
        if not result: util.try_ignore(os.unlink, filename)

    return result


def export_to_db(db, filename, schema, renames=None, data=False, selects=None,
                 limit=None, maxcount=None, empty=True, reverse=False, progress=None):
    """
    Exports selected tables and views to another database, structure only or
    structure plus data, auto-creating table and view indexes and triggers.

    @param   db        Database instance
    @param   filename  database filename to export to
    @param   schema    {category: [name, ]} to export
    @param   renames   {category: {name1: name2}}
    @param   data      whether to export table data
    @param   selects   {table name: SELECT SQL if not using default}
    @param   limit     query limits, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
    @param   maxcount  maximum total number of rows to export over all entities
    @param   empty     do not skip tables with no output rows
    @param   reverse   query rows in reverse order
    @param   progress  callback(?name, ?error) to report export progress,
                       returning false if export should cancel
    @return            True on success, False on failure, None on cancel
    """
    result = True
    CATEGORIES = db.DATA_CATEGORIES
    sqls0, sqls1, actionsqls = [], [], []
    requireds, processeds, exporteds = {}, set(), set()
    limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else util.tuplefy(limit)
    totalcount = 0

    is_samefile = util.lceq(db.filename, filename)
    file_existed = is_samefile or os.path.isfile(filename)
    insert_sql = "INSERT INTO %s.%s SELECT * FROM main.%s"

    for category, name in ((c, n) for c, nn in schema.items() for n in nn):
        items = [db.schema[category][name]]
        items.extend(db.get_related(category, name, own=True).get("trigger", {}).values())
        for item in items:
            # Foreign tables and tables/views used in triggers for table,
            # tables/views used in view body and view triggers for view.
            for name2 in util.getval(item, "meta", "__tables__", default=[]):
                if util.lceq(name, name2): continue # for name2
                requireds.setdefault(name, []).append(name2)

    finalargs, fks_on = {"done": True}, None
    db.lock(None, None, filename, label="database export")
    try:
        schema2 = "main"
        if not is_samefile:
            schemas = [list(x.values())[1] for x in
                       db.execute("PRAGMA database_list").fetchall()]
            schema2 = util.make_unique("main", schemas, suffix="%s")
            sql = "ATTACH DATABASE ? AS %s" % schema2
            db.execute(sql, [filename]), sqls0.append(sql)
        myrenames = dict(renames or {}, schema=schema2)

        allnames2 = util.CaselessDict({x["name"]: x["type"] for x in db.execute(
            "SELECT name, type FROM %s.sqlite_master" % schema2
        ).fetchall()})

        fks_on = db.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"]
        if fks_on:
            sql = "PRAGMA foreign_keys = off"
            db.execute(sql), sqls0.append(sql)


        for category, name in ((c, x) for c in CATEGORIES for x in schema.get(c, ())):
            name2 = myrenames.get(category, {}).get(name, name)
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
                    result = None
                    break # for category, name
                continue # for category, name

            try:
                # Create table or view structure
                label = "%s %s" % (category, grammar.quote(name, force=True))
                if name != name2: label += " as %s" % grammar.quote(name2, force=True)

                if name2 in allnames2:
                    logger.info("Dropping %s %s in %s.",
                                allnames2[name2], grammar.quote(name2, force=True), filename)
                    sql = "DROP %s %s.%s" % (allnames2[name2].upper(),
                                             schema2, grammar.quote(name2))
                    db.execute(sql), actionsqls.append(sql)

                logger.info("Creating %s in %s.", label, filename)
                sql, err = grammar.transform(db.schema[category][name]["sql"], renames=myrenames)
                if err:
                    if progress and not progress(name=name, error=err):
                        result = None
                        break # for category, name
                    continue # for category, name
                db.execute(sql), actionsqls.append(sql)
                if not data or "table" != category: exporteds.add(name)
                allnames2[name2] = category

                # Copy table data
                if data and "table" == category:
                    if selects and name in selects:
                        sql = "INSERT INTO %s.%s %s" % (
                              schema2, grammar.quote(name2), selects[name])
                    else:
                        sql = insert_sql % (schema2, grammar.quote(name2),
                                            grammar.quote(name))

                    order_sql = db.get_order_sql(name, reverse=True) if reverse else ""
                    limit_sql = db.get_limit_sql(*limit, maxcount=maxcount, totals=totalcount)
                    sql += order_sql + limit_sql

                    logger.info("Copying data to %s in %s.", label, filename)
                    count = db.execute(sql).rowcount
                    db.connection.commit()
                    actionsqls.append(sql)
                    exporteds.add(name)
                    totalcount += count

                    if not empty and not count:
                        logger.info("Dropping empty %s from %s.", label, filename)
                        sql = "DROP TABLE %s.%s" % (schema2, grammar.quote(name2))
                        db.execute(sql), actionsqls.append(sql)
                        db.connection.commit()
                        exporteds.discard(name)
                        continue # for category, name
                    if progress and not progress(name=name, count=count):
                        result = None
                        break # for category, name

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
                    result = None
                    break # for category, name
            else:
                if progress and not progress(name=name):
                    result = None
                    break # for category, name
    except Exception as e:
        logger.exception("Error exporting from %s to %s.", db, filename)
        finalargs["error"] = util.format_exc(e)
        result = False
    finally:
        if fks_on:
            try:
                sql = "PRAGMA foreign_keys = on"
                db.execute(sql), sqls1.append(sql)
            except Exception: pass
        try: 
            sql = "DETACH DATABASE %s" % schema2
            db.execute(sql), sqls1.append(sql)
        except Exception: pass
        if not file_existed and (not actionsqls or not result):
            util.try_ignore(os.unlink, filename)
        db.unlock(None, None, filename)

    result = result and bool(actionsqls)
    if result: db.log_query("EXPORT TO DB", [x + ";" for x in sqls0 + actionsqls + sqls1],
                            params=None if is_samefile else filename)

    if progress: progress(**finalargs)
    return result    


def export_query_to_db(db, filename, table, query, params=(), create_sql=None,
                       empty=True, limit=None, progress=None):
    """
    Exports query results to another database.

    @param   db          Database instance
    @param   filename    database filename to export to
    @param   table       target table name, expected to be unique in target database
    @param   query       SQL query text
    @param   params      SQL query parameters
    @param   create_sql  CREATE TABLE statement if not auto-generating from query columns
    @param   empty       create target table even if query returns nothing
    @param   limit       query limits, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
    @param   progress    callback(?done, ?error) to report export progress,
                         returning false if export should cancel
    @return              True if table was created, None on cancel, False otherwise
    """
    result, err = True, False
    is_samefile = util.lceq(db.filename, filename)
    file_existed = is_samefile or os.path.isfile(filename)
    finalargs, logs = {"name": table, "done": True}, []  # [(sql, params), ]

    schemas = [list(x.values())[1] for x in
               db.execute("PRAGMA database_list").fetchall()]
    schema2 = util.make_unique("main", schemas, suffix="%s")
    limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else util.tuplefy(limit)

    db.lock(None, None, filename, label="query export")

    if progress and not progress(name=table):
        db.unlock(None, None, filename)
        progress(**finalargs)
        result = None
        return result

    try:
        sql = "ATTACH DATABASE ? AS %s" % schema2
        db.execute(sql, [filename])
        logs.append((sql, None if is_samefile else filename))

        count = 0
        fullname = "%s.%s" % (schema2, grammar.quote(table))
        if "SELECT" == query.strip()[:6].upper():
            if create_sql:
                sql = grammar.transform(create_sql, renames={"schema": schema2})[0]
                db.executescript(sql)
                logs.append((sql, None))
                sql = "INSERT INTO %s %s" % (fullname, query)
            else:
                sql = "CREATE TABLE %s AS %s" % (fullname, query)
            if limit: sql += (" " +
                " ".join(" ".join(x) for x in zip(("LIMIT", "OFFSET"), map(str, limit)))
            )
            count = db.execute(sql, params).rowcount
            logs.append((sql, None))
        else:
            cursor = db.execute(query, params)
            cols = [c[0] for c in cursor.description] if cursor.description else ["rowcount"]
            sql = create_sql
            sql = sql or "CREATE TABLE %s (%s)" % (fullname, ", ".join(map(grammar.quote, cols)))
            db.executescript(sql)
            logs.append((sql, None))

            insert_sql = "INSERT INTO %s VALUES (%s)" % (fullname, ", ".join(["?"] * len(cols)))
            rows = cursor if cursor.description else [{"rowcount": cursor.rowcount}]
            qrange = (0, limit[0]) if limit else None # (fromindex, toindex)
            qrange = (limit[1], (limit[1] + limit[0]) if limit[0] > 0 else -1) \
                     if limit and len(limit) > 1 else qrange
            for i, row in enumerate(rows):
                if qrange and i < qrange[0]: continue # for
                if qrange and qrange[1] >= 0 and i >= qrange[1]: break # for

                params = list(row.values())
                db.execute(insert_sql, params)
                logs.append((sql, params))
                count += 1
        db.connection.commit()
        if count is None and (progress or not empty): # If CREATE TABLE AS query
            count = db.execute("SELECT COUNT(*) AS count FROM %s" % fullname).fetchone()["count"]
        if progress and not progress(name=table, count=count):
            result, count = None, None
        if not empty and not count:
            sql = "DROP TABLE %s" % fullname
            db.executescript(sql)
            logs.append((sql, None))
            result = False if result else result

    except Exception as e:
        result, err = False, True
        logger.exception("Error exporting query %r from %s to %s.", query, db, filename)
        finalargs["error"] = util.format_exc(e)
        if not file_existed:
            util.try_ignore(os.unlink, filename)
    finally:
        try: 
            sql = "DETACH DATABASE %s" % schema2
            db.execute(sql)
            logs.append((sql, None))
        except Exception: pass
        db.unlock(None, None, filename)

    if not err:
        sqls, params = zip(*logs)
        db.log_query("EXPORT QUERY TO DB", [x + ";" for x in sqls], params)
    if progress: progress(**finalargs)
    return result


def export_to_console(make_iterables, format, title=None,
                      output=None, multiple=False, progress=None):
    """
    Prints entity rows to console.

    @param   db              Database instance
    @param   format          file format like "csv"
    @param   title           export title if any, as string or a sequence of strings
    @param   make_iterables  function yielding pairs of ({info}, function yielding rows)
    @param   output          print-function to use if not print()
    @param   multiple        whether to output as multi-item
    @param   progress        callback(?done, ?error) to report export progress,
                             returning false if export should cancel
    @return                  True on success, None on cancel
    """
    ITEM_TEMPLATES = {"json": templates.DATA_ROWS_JSON,
                      "sql":  templates.DATA_ROWS_SQL,
                      "txt":  templates.DATA_ROWS_TXT,
                      "yaml": templates.DATA_ROWS_YAML}
    output = output or print
    result, writer, started, hr, allnames = True, None, False, "", set()
    ns = {"multiple": multiple}

    output()
    for line in util.tuplefy(title) if title else ():
        output(line, file=sys.stderr)
    title and output(file=sys.stderr)

    for item, make_iterable in make_iterables():
        name = item["name"]
        if progress and not progress(name=name):
            result = None
            break # for item

        if "view" == item["type"]:
            name = util.make_unique(name, allnames)

        ns.update({"columns": item["columns"], "name": name})

        # Run through rows once for txt output, to populate text-justify options
        colnames = [c["name"] for c in item["columns"]]
        widths   = {c: len(util.unprint(c)) for c in colnames}
        justs    = {c: True   for c in colnames}
        do_break = False
        for i, row in enumerate(make_iterable()) if "txt" == format else ():
            for col in colnames:
                v = row[col]
                if isinstance(v, six.integer_types + (float, )): justs[col] = False
                v = "" if v is None \
                    else v if isinstance(v, six.string_types) else str(v)
                v = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, six.text_type(v))
                widths[col] = max(widths[col], len(v))
                if not i % 100 and progress and not progress():
                    do_break, result = True, None
                    break # for i, row
            ns.update({"columnjusts": justs, "columnwidths": widths})
        if do_break:
            break # for item

        rows = make_iterable()
        i, row, nextrow = 0, next(rows, None), next(rows, None)
        while row:

            if not started:
                allnames.add(name)
                if   "csv"  == format:
                    writer = csv_writer(sys.stdout)
                elif "json" == format:
                    if multiple: output("{")

            if not i:
                if   "csv"  == format:
                    if multiple:
                        writer.writerow()
                        writer.writerow([item["name"]])
                    writer.writerow(([""] if multiple else []) + colnames)
                elif "json" == format:
                    output("[" if multiple else "  %s: [" % json.dumps(item["name"]))
                elif "sql"  == format:
                    if started:
                        output("\n")

                    sql = item["sql"]
                    if "view" == item["type"]:
                        tpl = step.Template(templates.CREATE_VIEW_TABLE_SQL, strip=False)
                        sql = tpl.expand(**item).strip()
                    output(sql)
                    output()
                elif "txt"  == format:
                    if started:
                        output(hr)
                        output("\n\n")

                    headers = []
                    for c in colnames:
                        fc = util.unprint(c)
                        headers.append((fc.ljust if justs[c] else fc.rjust)(widths[c]))
                    hr = "|-%s-|" % "-|-".join("".ljust(widths[c], "-") for c in colnames)
                    header = "| " + " | ".join(headers) + " |"

                    output(item["sql"])
                    output()
                    output(hr)
                    output(header)
                    output(hr)
                elif "yaml" == format:
                    if started: output()
                    if multiple:
                        key = yaml.safe_dump({name: None})
                        output("%s:" % key[:key.rindex(":")])

            do_break = not i % 100 and progress and not progress(name=name, count=i + 1)
            if "csv" == format:
                writer.writerow(([""] if multiple else []) + list(row.values()))
            else:
                ns.update({"rows": [row]})
                tpl = step.Template(ITEM_TEMPLATES[format], strip=False)
                content = tpl.expand(ns).rstrip()
                if "json" == format and nextrow and not do_break:
                    content += ","
                output(content)

            started = True
            i, row, nextrow = i + 1, nextrow, next(rows, None)
            if do_break:
                result = None
                break # while row

        if progress and not progress(name=name, count=i, done=True):
            result = None
            break # for item

    if started:
        if "json" == format:
            if multiple:
                output("  ]")
                output("}")
            else:
                output("]")
        elif "txt" == format:
            output(hr)

    return result



def get_import_file_data(filename, progress=None):
    """
    Returns import file metadata, as {
        "name":        file name and path}.
        "size":        file size in bytes,
        "modified":    file modification timestamp
        "format":      "xlsx", "xlsx", "csv", "json" or "yaml",
        "sheets":      [
            "name":    sheet name,
            "rows":    count or -1 if file too large,
            "columns": [first row cell value, ],
    ]}.

    @param   progress  callback() returning false if function should cancel
    @return  metadata dict, or None if cancelled
    """
    logger.info("Getting import data from %s.", filename)
    sheets, size = [], os.path.getsize(filename)
    if not size: raise ValueError("File is empty.")
    modified = datetime.datetime.fromtimestamp(os.path.getmtime(filename))

    extname = os.path.splitext(filename)[-1][1:].lower()
    is_csv, is_json, is_xls, is_xlsx = \
        (extname == x for x in ("csv", "json", "xls", "xlsx"))
    is_yaml = extname in YAML_EXTS
    if is_csv:
        rows, columns = 0, []
        with csv_reader(filename) as f:
            iterer = enumerate(f)
            for i, row in iterer:
                if row: # Skip any initial blank rows
                    rows, columns = 1, row
                    break # for i, row
                if progress and not i % 100 and not progress(): break # for i, row
            if rows and size > conf.MaxImportFilesizeForCount: rows = -1
            elif rows and size:
                for i, row in iterer:
                    rows += bool(row)
                    if progress and not i % 100 and not progress(): break # for i, row
        sheets.append({"rows": rows, "columns": columns, "name": "<no name>"})
    elif is_json:
        rows, columns, buffer, started = 0, {}, "", False
        decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
        with open(filename) as f:
            for chunk in iter(functools.partial(f.read, 2**16), ""):
                buffer += chunk
                if not started: # Strip line comments and list start from beginning
                    buffer = re.sub("^//[^\n]*$", "", buffer.lstrip(), flags=re.M).lstrip()
                    if buffer.startswith("["): buffer, started = buffer[1:].lstrip(), True
                    else: started = buffer.startswith("{") # Support files containing a single dict
                while started and buffer:
                    if progress and not progress(): return None
                    # Strip whitespace and interleaving commas from between dicts
                    buffer = re.sub(r"^\s*[,]?\s*", "", buffer)
                    try:
                        data, index = decoder.raw_decode(buffer)
                        buffer = buffer[index:]
                        if isinstance(data, collections.OrderedDict):
                            columns, rows = columns or data, rows + 1
                    except ValueError: # Not enough data to decode, read more
                        break # while started and buffer
                if columns and any(x > conf.MaxImportFilesizeForCount for x in (size, f.tell())):
                    break # for chunk
            if rows and f.tell() < size: rows = -1
        sheets.append({"rows": rows, "columns": columns, "name": "<JSON data>"})
    elif is_xls:
        with xlrd.open_workbook(filename, on_demand=True) as wb:
            for sheet in wb.sheets():
                if progress and not progress(): return None
                columns = [x.value for x in next(sheet.get_rows(), [])]
                while columns and columns[-1] is None: columns.pop(-1)
                columns = [x.strip() if isinstance(x, six.string_types)
                           else "" if x is None else str(x) for x in columns]
                if not columns: rows = 0
                else: rows = -1 if size > conf.MaxImportFilesizeForCount else sheet.nrows
                sheets.append({"rows": rows, "columns": columns, "name": sheet.name})
    elif is_xlsx:
        wb = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore") # openpyxl can throw warnings on styles etc

                wb = openpyxl.load_workbook(filename, data_only=True, read_only=True)
                for sheet in wb.worksheets:
                    if progress and not progress(): return None
                    columns = list(next(sheet.values, []))
                    while columns and columns[-1] is None: columns.pop(-1)
                    columns = [x.strip() if isinstance(x, six.string_types)
                               else "" if x is None else str(x) for x in columns]
                    rows = 0 if not columns else -1 if size > conf.MaxImportFilesizeForCount \
                           else sum(1 for _ in sheet.iter_rows())
                    sheets.append({"rows": rows, "columns": columns, "name": sheet.title})
        finally: wb and wb.close()
    elif is_yaml:
        extname = "yaml"
        rows, columns = 0, {}
        with open(filename, "rbU" if six.PY2 else "rb") as f:
            parser = yaml.parse(f, yaml.SafeLoader)
            stack, collections_stack, mappings_stack, mapping_items = [], [], [], []
            for event in parser:
                if not columns: stack.append(event)

                if len(mappings_stack) == 1 and len(collections_stack) < 3 \
                and isinstance(event, yaml.NodeEvent):  # Collection or scalar in root dictionary
                    # Root level key or value
                    mapping_items.append(event)

                if isinstance(event, yaml.CollectionStartEvent):
                    collections_stack.append(event)
                elif isinstance(event, yaml.CollectionEndEvent):
                    collections_stack.pop()

                if isinstance(event, yaml.MappingStartEvent):
                    mappings_stack.append(event)
                elif isinstance(event, yaml.MappingEndEvent):
                    mappings_stack.pop()
                    if not mappings_stack and len(collections_stack) < 2:  # Root level dictionary
                        rows += 1
                        if not columns:
                            keys = [x for x in mapping_items if isinstance(x, yaml.ScalarEvent)]
                            data = yaml.safe_load(yaml.emit(stack))
                            if isinstance(data, list): data = data[0]
                            columns = collections.OrderedDict((k.value, data[k.value])
                                                              for k in keys if k.value in data)
                if columns and size > conf.MaxImportFilesizeForCount:
                    rows = -1
                    break # for chunk
                if progress and not progress(): return None
        sheets.append({"rows": rows, "columns": columns, "name": "<YAML data>"})
    else:
        raise ValueError("File type not recognized.")

    return {"name": filename, "size": size, "modified": modified, "format": extname, "sheets": sheets}



def import_data(filename, db, tables, tablecolumns, pks=None,
                has_header=True, progress=None):
    """
    Imports data from spreadsheet or JSON or YAML data file to database table.
    Will create tables if not existing yet.

    @param   filename       file path to import from
    @param   db             database.Database instance
    @param   tables         tables to import to and sheets to import from, as [(table, sheet)]
                            (sheet can be None if file is CSV/JSON/YAML)
    @param   tablecolumns   mapping of file columns to table columns,
                            as {table: OrderedDict(file column key: table columm name)},
                            where key is column index if spreadsheet else column name
    @param   pks            names of auto-increment primary key to add
                            for new tables, if any, as {table: pk}
    @param   has_header     whether spreadsheet file has a header row
    @param   progress       callback(?table, ?count, ?done, ?error, ?errorcount, ?index) to report
                            progress, returning False if import should cancel,
                            and None if import should rollback.
                            Returning True on error will ignore further errors.
    @return                 success
    """
    result = True

    extname = os.path.splitext(filename)[-1][1:].lower()
    table, sheet, cursor, isolevel = None, None, None, None
    was_open, file_existed = db.is_open(), os.path.isfile(db.filename)
    try:
        if not was_open: db.open()
        continue_on_error, create_sql = None, None
        isolevel = db.connection.isolation_level
        db.connection.isolation_level = None # Disable autocommit
        with db.connection:
            cursor = db.connection.cursor()
            cursor.execute("BEGIN TRANSACTION")

            for i, (table, sheet) in enumerate(tables):
                sheet = sheet if extname not in ("csv", "json") else None
                columns = tablecolumns[table]
                if table not in db.schema.get("table", {}):
                    cols = [{"name": x} for x in columns.values()]
                    if pks.get(table):
                        cols.insert(0, {"name": pks[table], "type": "INTEGER",
                                        "pk": {"autoincrement": True}, "notnull": {}})
                    meta = {"name": table, "__type__": grammar.SQL.CREATE_TABLE,
                            "columns": cols}
                    create_sql, err = grammar.generate(meta)
                    if err: raise Exception(err)

                sql = "INSERT INTO %s (%s) VALUES (%s)" % (grammar.quote(table),
                    ", ".join(grammar.quote(x) for x in columns.values()),
                    ", ".join("?" * len(columns))
                )

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
                                              count=count, errorcount=errorcount,
                                              table=table)
                            if result:
                                continue_on_error = True
                                continue # for row
                            logger.info("Cancelling%s import on user request.",
                                        " and rolling back" if result is None else "")
                            if result is None: cursor.execute("ROLLBACK")
                            break # for row
                    if result and progress \
                    and (count != lastcount and not count % 100 or errorcount != lasterrorcount and not errorcount % 100):
                        result = progress(table=table, count=count, errorcount=errorcount)
                        if not result:
                            logger.info("Cancelling%s import on user request.",
                                        " and rolling back" if result is None else "")
                            if result is None: cursor.execute("ROLLBACK")
                            break # for row

                if result:
                    db.log_query("IMPORT", [create_sql, sql] if create_sql else [sql],
                                 [filename, util.plural("row", count)])
                db.unlock("table", table, filename)
                logger.info("Finished importing %s from %s%s to table %s%s.",
                            util.plural("row", count),
                            filename, (" sheet '%s'" % sheet) if sheet else "",
                            grammar.quote(table, force=True),
                            ", all rolled back" if result is None and count else "")
                mytable = table
                if i == len(tables) - 1:
                    if result: cursor.execute("COMMIT")
                    util.try_ignore(cursor.close)
                    cursor = table = sheet = None
                if result and progress:
                    result = progress(table=mytable, count=count, errorcount=errorcount, done=True)
                if not result:
                    break # for i, (table, sheet)

            logger.info("Finished importing from %s to %s.", filename, db)

    except Exception as e:
        logger.exception("Error running import from %s%s%s in %s.",
                         filename, (" sheet '%s'" % sheet) if sheet else "",
                         (" to table %s " % grammar.quote(table, force=True) if table else ""),
                         db.filename)
        result = False
        if cursor: util.try_ignore(cursor.execute, "ROLLBACK")
        if progress:
            kwargs = dict(error=util.format_exc(e), done=True)
            if table: kwargs.update(table=table)
            progress(**kwargs)
    finally:
        if db.is_open():
            if isolevel is not None: db.connection.isolation_level = isolevel
            if cursor: util.try_ignore(cursor.close)
            if table: db.unlock("table", table, filename)
            if not was_open: db.close()
        if result is None and not file_existed:
            util.try_ignore(os.unlink, db.filename)

    return result



def iter_file_rows(filename, columns, sheet=None):
    """
    Yields rows as [value, ] from spreadsheet or JSON or YAML file.

    @param   filename    file path to open
    @param   columns     list of column keys to return,
                         where key is column index if spreadsheet else column name
    @param   sheet       sheet name to read from, if applicable
    """
    size = os.path.getsize(filename)
    is_csv  = filename.lower().endswith(".csv")
    is_json = filename.lower().endswith(".json")
    is_xls  = filename.lower().endswith(".xls")
    is_xlsx = filename.lower().endswith(".xlsx")
    is_yaml = any(n.endswith("." + x) for n in [filename.lower()] for x in YAML_EXTS)
    if is_csv:
        with csv_reader(filename) as f:
            for row in f:
                yield [row[i] if i < len(row) else None for i in columns]
    elif is_json:
        started, buffer = False, ""
        decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
        with open(filename) as f:
            for chunk in iter(functools.partial(f.read, 2**16), ""):
                buffer += chunk
                if not started: # Strip line comments and list start from beginning
                    buffer = re.sub("^//[^\n]*$", "", buffer.lstrip(), flags=re.M).lstrip()
                    if buffer.startswith("["): buffer, started = buffer[1:].lstrip(), True
                    else: started = buffer.startswith("{") # Support files containing a single dict
                while started and buffer:
                    # Strip whitespace and interleaving commas from between dicts
                    buffer = re.sub(r"^\s*[,]?\s*", "", buffer)
                    try:
                        data, index = decoder.raw_decode(buffer)
                        buffer = buffer[index:]
                        if isinstance(data, collections.OrderedDict):
                            yield [data.get(x) for x in columns]
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
            with warnings.catch_warnings():
                warnings.simplefilter("ignore") # openpyxl can throw warnings on styles etc

                wb = openpyxl.load_workbook(filename, data_only=True, read_only=True)
                for row in wb.get_sheet_by_name(sheet).iter_rows(values_only=True):
                    yield [row[i] if i < len(row) else None for i in columns]
        finally: wb and wb.close()
    elif is_yaml:
        # Keep structures nested in values as YAML strings in database
        cast = lambda x: yaml.safe_dump(x) if isinstance(x, (dict, list)) else x
        with open(filename, "rbU" if six.PY2 else "rb") as f:
            parser = yaml.parse(f, yaml.SafeLoader)
            START_STACK = [yaml.StreamStartEvent(), yaml.DocumentStartEvent()]
            item_stack, collections_stack, mappings_stack = [], [], []
            for event in parser:
                if mappings_stack or isinstance(event, yaml.MappingStartEvent):
                    item_stack.append(event)

                if isinstance(event, yaml.CollectionStartEvent):
                    collections_stack.append(event)
                elif isinstance(event, yaml.CollectionEndEvent):
                    collections_stack.pop()

                if isinstance(event, yaml.MappingStartEvent):
                    mappings_stack.append(event)
                elif isinstance(event, yaml.MappingEndEvent):
                    mappings_stack.pop()
                    if not mappings_stack and len(collections_stack) < 2:  # Root level dictionary
                        data = yaml.safe_load(yaml.emit(START_STACK + item_stack))
                        del item_stack[:]
                        yield [cast(data.get(x)) for x in columns]


def convert_lf(s, newline=os.linesep):
    r"""Returns string with \r \n \r\n linefeeds replaced with given."""
    return re.sub("(\r(?!\n))|((?<!\r)\n)|(\r\n)", newline, s)


class csv_reader(object):
    """
    Convenience wrapper for csv.reader, with Python2/3 compatibility and encoding/dialect detection.

    Usable as a context manager.
    """

    def __init__(self, filename, peek_size=65536):
        self.filename = filename
        self.encoding = None
        self.dialect  = None
        self._file    = None
        self._reader  = None
        self._peek    = peek_size

        self._detect()


    def _detect(self):
        """Auto-detects file character encoding and CSV dialect."""
        encoding, dialect = None, csv.excel
        with open(self.filename, "rb") as f:
            preview = f.read(self._peek)
            if   preview.startswith(b"\xFE\xFF"): encoding = "utf-16be"
            elif preview.startswith(b"\xFF\xFE"): encoding = "utf-16le"
            elif chardet: encoding = chardet.detect_all(preview)[0]["encoding"]
            if "ascii" == encoding: encoding = "utf-8" # Failsafe: ASCII as UTF-8 is valid anyway

            if "utf-16" in (encoding or "").lower() and len(preview) / 2: preview += b"\x00"
            try: dialect = csv.Sniffer().sniff(preview.decode(encoding or "utf-8"), ",;\t")
            except UnicodeError: # chardet is not very reliable, try UTF-8 as fallback
                try: encoding, dialect = "utf-8", csv.Sniffer().sniff(preview.decode("utf-8"), ",;\t")
                except Exception: dialect = csv.excel # Try default as fallback

            if six.PY2: # Sniffer in Py2 sets delimiters as Unicode but reader raises error on them
                for k, v in vars(dialect).items():
                    if isinstance(v, six.text_type) and not k.startswith("_"):
                        setattr(dialect, k, v.encode())
        self.encoding, self.dialect = encoding, dialect


    def open(self):
        """Opens file if not already open."""
        if not self._file:
            self._file   = codecs.open(self.filename, encoding=self.encoding)
            self._reader = csv.reader(self._reencoder() if six.PY2 else self._file, self.dialect)


    def _reencoder(self):
        """Yields lines from file re-encoded as UTF-8; Py2 workaround."""
        if "utf-16" in (self.encoding or "").lower(): # Strip byte order mark if any
            line = next(self._file)
            if line.startswith((u"\uFEFF", u"\uFFFE")): line = line[1:]
            yield line.encode("utf-8")
        for line in self._file: yield line.encode("utf-8")


    def close(self):
        """Closes file if open."""
        if self._file:
            f, self._file, self._reader = self._file, None, None
            f.close()


    def __enter__(self):
        """Context manager entry, opens file if not already open, returns self."""
        self.open()
        return self


    def __exit__(self, exc_type, exc_val, exc_trace):
        """Context manager exit, closes file if open."""
        self.close()
        return exc_type is None


    def __iter__(self):
        """Yields rows from CSV file as lists of column values."""
        for x in self._reader: yield x


class csv_writer(object):
    """Convenience wrapper for csv.writer, with Python2/3 compatbility."""

    def __init__(self, file_or_name):
        if isinstance(file_or_name, six.string_types):
            self._name = file_or_name
            self._file = open(self._name, "wb") if six.PY2 else \
                         codecs.open(self._name, "w", "utf-8")
        else:
            self._name = None
            self._file = file_or_name
        # csv.excel.delimiter default "," is not actually used by Excel.
        self._writer = csv.writer(self._file, csv.excel, delimiter=";")


    def writerow(self, sequence=()):
        """Writes a CSV record from a sequence of fields."""
        values = []
        for v in sequence:
            if six.PY2:
                v = util.to_unicode(v).encode("utf-8", "backslashreplace")
            if isinstance(v, six.string_types):
                v = v.replace("\r", "\\r").replace("\n", "\\n").replace("\x00", "\\x00")
            values.append(v)
        self._writer.writerow(values)


    def close(self):
        """Closes CSV file writer."""
        if self._name: self._file.close()


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
        self._autowrap   = list(autowrap or ()) # [column index to autowrap, ]
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
            safename = util.ellipsize(safename, 31)
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
        self._writers[six.binary_type] = self._writers[six.text_type] = sheet.write_string


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
            fmt_name = style if isinstance(style, six.string_types) \
                       else style.get(c, self._format)
            writefunc(self._row, c, v, self._formats[fmt_name])
            if (merge_cols or not autowidth or "wrap" == fmt_name
            or c in self._autowrap):
                continue # for c, v

            # Calculate and update maximum written column width
            strval = (v.encode("latin1", "replace").decode("latin1")
                      if isinstance(v, six.text_type)
                      else v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime.datetime)
                      else v if isinstance(v, six.string_types) else str(v))
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
