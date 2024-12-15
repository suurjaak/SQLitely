# -*- coding: utf-8 -*-
"""
Functionality for exporting SQLite data to external files.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    15.12.2024
------------------------------------------------------------------------------
"""
from __future__ import print_function
import codecs
import collections
import copy
import csv
import datetime
import functools
import io
import itertools
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
import step

from . lib import util
from . import conf
from . import database
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



class Base(object):
    """Base API for import sources and export sinks."""

    ## Number of iterations between calls to progress in various contexts
    PROGRESS_STEP = 100


    def __init__(self, progress=None):
        self._progress = progress


    def _check_cancel(self, *conditions, **progress_args):
        """
        Reports progress to callback function if any, returns whether export should cancel.

        @param   conditions  boolean conditions if any to validate before reporting progress
        """
        if not all(conditions): return False
        if not self._progress: return False
        return not self._progress(**progress_args)



class Sink(Base):
    """Base API for export sinks."""


    @classmethod
    def _constrain_iterable(cls, iterable, name=None, counts=None, limit=(), maxcount=None):
        """
        Yields from iterable, accounting for given limits.

        @param   iterable  iterable object, or callable producing iterable
        @param   counts    dictionary to increase name count in, if any
        """
        if callable(iterable): iterable = iterable()
        if not limit and counts is None and maxcount is None: # Simple loop for plain passthrough
            for row in iterable: yield row
            return

        if counts is None: counts = {}
        counts[name] = 0
        if not limit and maxcount is None:
            for row in iterable:
                counts[name] += 1
                yield row
            return

        if maxcount is not None:
            maxcount = max(0, maxcount - sum(counts.values()))
            mymax = min(maxcount, limit[0]) if limit and limit[0] >= 0 else maxcount
            limit = [mymax] + list(limit[1:])
        from_to = (0, limit[0]) if limit else None # (fromindex, toindex)
        if limit and len(limit) > 1:
            from_to = (limit[1], (limit[1] + limit[0]) if limit[0] > 0 else -1)

        for i, row in enumerate(iterable):
            if i < from_to[0]: continue # for i, row
            if from_to[1] >= 0 and i >= from_to[1]: break # for i, row
            counts[name] += 1
            yield row


    @classmethod
    def _make_item_iterable(cls, db, category, name, counts,
                            limit=(), maxcount=None, reverse=False):
        """
        Yields rows from table or view, using limit and maxcount.

        @param   counts  defaultdict(int) for tracking row counts
        """
        counts[name] = 0
        order_sql = db.get_order_sql(name, reverse=True) if reverse else ""
        limit_sql = db.get_limit_sql(*limit, maxcount=maxcount, totals=counts)
        sql = "SELECT * FROM %s%s%s" % (grammar.quote(name), order_sql, limit_sql)

        msg = "Error querying %s %s." % (category, grammar.quote(name, force=True))
        tick = lambda n: counts.update({name: n})
        return db.select(sql, error=msg, tick=tick)


    def _measure_columns(self, columns, make_iterable):
        """
        Returns column widths and justification for txt output. Returns early if cancelled.

        @param   columns        output columns as [{name}]
        @param   make_iterable  function returning iterable sequence yielding rows
        @return  {column name: character width}, {column name: whether left-justified}
        """
        names  = [c["name"] for c in columns]
        widths = {c: len(util.unprint(grammar.quote(c))) for c in names}
        justs  = {c: True for c in names}
        def process_value(row, col):
            v = row[col]
            if isinstance(v, six.integer_types + (float, )): justs[col] = False
            v = "" if v is None else v if isinstance(v, six.string_types) else str(v)
            v = templates.SAFEBYTE_RGX.sub(templates.SAFEBYTE_REPL, six.text_type(v))
            widths[col] = max(widths[col], len(v))

        cursor = make_iterable()
        try:
            for i, row in enumerate(cursor): # Run through all rows once
                for col in names: process_value(row, col)
                if self._check_cancel(not i % self.PROGRESS_STEP):
                    break # for i, row
        finally:
            util.try_ignore(lambda: cursor.close())
        return widths, justs



class ConsoleSink(Sink):
    """Prints data rows to console."""

    ITEM_TEMPLATES = {"json": templates.DATA_ROWS_JSON,
                      "sql":  templates.DATA_ROWS_SQL,
                      "txt":  templates.DATA_ROWS_TXT,
                      "yaml": templates.DATA_ROWS_YAML}


    def __init__(self, format, output=None, progress=None):
        """
        @param   format    output format like "csv"
        @param   output    print-function to use if not print(), must support file-parameter
        @param   progress  callback(?name, ?count, ?done) to report progress,
                           returning false if export should cancel
        """
        if format not in PRINTABLE_EXTS:
            raise ValueError("Unknown format %r" % (format, ))

        super(ConsoleSink, self).__init__(progress=progress)
        self._format = format
        self._output = output or print
        self._flags = {
            "allow_empty":  True,   # produce content even if no rows available
            "combined":     False,  # output as multi-item
        }
        self._state = {
            "columnjusts":  [],     # dict of {column name: True if left-justified} for txt output
            "columnnames":  [],     # list of output column names for current item for txt output
            "columnwidths": [],     # dict of {column name: maximum character width} for txt output
            "started":      False,  # whether items output has started
            "writer":       None,   # csv_writer instance if any
        }


    def configure(self, allow_empty=True, combined=False):
        """
        Configures output options, returns self.

        @param   allow_empty  do not skip items with no output rows
        @param   combined     output as multi-item, e.g. JSON as
                              {name1: [{..}, {..}], name2: [{..}]} instead of [{..}, {..}], [{..}]
        """
        self._flags.update(allow_empty=allow_empty, combined=combined)
        return self


    def write(self, make_iterables, title=None):
        """
        @param   make_iterables  function yielding pairs of
                                 ({name, type, columns, sql}, function yielding rows)
        @param   title           export title if any, as string or a sequence of strings,
                                 output to stderr
        @return                  None if cancelled else True
        """
        result = True
        self._output()
        self._print_meta(title)
        try:
            for item, make_iterable in make_iterables():
                rows = self._prepare_item(item, make_iterable)
                if self._check_cancel(name=item["name"]):
                    result = None
                    return result
                i, row, nextrow = 0, next(rows, None), next(rows, None)
                if row or self._flags["allow_empty"]:
                    if self._state["started"]: self._write_footer()
                    self._write_header(item, bool(row))
                while row:
                    do_cancel = self._check_cancel(not i % self.PROGRESS_STEP,
                                                   name=item["name"], count=i)
                    self._write_row(item, row, is_last_row=do_cancel or not nextrow)
                    if do_cancel:
                        result = None
                        return result
                    i, row, nextrow = i + 1, nextrow, next(rows, None)
                if self._check_cancel(name=item["name"], count=i, done=True):
                    result = None
                    return result
        except Exception:
            logger.exception("Error printing %s to console.", self._format.upper())
            result = False
        finally:
            if self._state["started"]:
                self._write_footer(is_last_item=True)
                self._write_ending()
        return result


    def _prepare_item(self, item, make_iterable):
        """Assembles item metadata, returns rows iterable or None if cancelled."""
        self._state["columnnames"] = [c["name"] for c in item["columns"]]
        if "txt" == self._format:
            widths, justs = self._measure_columns(item["columns"], make_iterable)
            self._state.update({"columnjusts": justs, "columnwidths": widths})
        return make_iterable()


    def _print_meta(self, title):
        """Prints title to stderr as metainfo, if any."""
        if not title: return
        for line in util.tuplefy(title): self._output(line, file=sys.stderr)
        self._output(file=sys.stderr)


    def _write_header(self, item, has_rows=True):
        """Writes out item header."""
        if "csv" == self._format:
            if not self._state["started"]:
                self._state["writer"] = csv_writer(sys.stdout)
            if self._flags["combined"]:
                self._state["writer"].writerow()
                self._state["writer"].writerow([item["name"]])
                self._state["writer"].writerow([""] + self._state["columnnames"])
            else:
                self._state["writer"].writerow(self._state["columnnames"])
        elif "json" == self._format:
            if not self._flags["combined"]: self._output("[")
            else:
                if not self._state["started"]: self._output("{")
                self._output("  %s: [" % json.dumps(item["name"]))
        elif "sql" == self._format:
            sql = item["sql"]
            if "view" == item["type"]:
                tpl = step.Template(templates.CREATE_VIEW_TABLE_SQL, strip=False)
                sql = tpl.expand(item).strip()
            self._output(sql), self._output()
        elif "txt" == self._format:
            headers = []
            justs, widths = self._state["columnjusts"], self._state["columnwidths"]
            for c in self._state["columnnames"]:
                fc = util.unprint(c)
                headers.append((fc.ljust if justs[c] else fc.rjust)(widths[c]))
            hr = "|-%s-|" % "-|-".join("".ljust(widths[c], "-") for c in self._state["columnnames"])
            header = "| " + " | ".join(headers) + " |"

            self._output(item["sql"]), self._output()
            self._output(hr), self._output(header), self._output(hr)
        elif "yaml" == self._format:
            if self._flags["combined"]:
                key = yaml.safe_dump({item["name"]: None})
                content = "%s:" % key[:key.rindex(":")]
                if not has_rows: content += " []"
                self._output(content)
        self._state["started"] = True


    def _write_row(self, item, row, is_last_row=False):
        """Writes out item row."""
        if "csv" == self._format:
            indentcols = [""] if self._flags["combined"] else []
            values = [row[k] for k in self._state["columnnames"]]
            self._state["writer"].writerow(indentcols + values)
        else:
            tpl = step.Template(self.ITEM_TEMPLATES[self._format], strip=False)
            ns = dict(columns=item["columns"], name=item["name"], combined=self._flags["combined"])
            if "txt" == self._format:
                ns.update({k: self._state[k] for k in ("columnjusts", "columnwidths")})
            content = tpl.expand(ns, rows=[row]).rstrip()
            if "json" == self._format and not is_last_row:
                content += ","
            self._output(content)


    def _write_footer(self, is_last_item=False):
        """Writes out item footer if any."""
        if "json" == self._format:
            indent, sep = ("  " if self._flags["combined"] else ""), ("" if is_last_item else ",")
            self._output("%s]%s" % (indent, sep))
        elif "sql"  == self._format:
            self._output(), self._output()
        elif "txt"  == self._format:
            widths = self._state["columnwidths"]
            hr = "|-%s-|" % "-|-".join("".ljust(widths[c], "-") for c in self._state["columnnames"])
            self._output(hr), self._output(), self._output(), self._output()
        elif "yaml" == self._format:
            self._output()


    def _write_ending(self):
        """Writes out any final wrap-up content."""
        if "json" == self._format:
            if self._state["started"] and self._flags["combined"]: self._output("}")



class DatabaseSink(Sink):
    """Exports database entities or query results to another database."""


    def __init__(self, db, filename, progress=None):
        """
        @param   db        source Database instance
        @param   filename  target database filename (may be same file as source)
        @param   progress  callback(?name, ?count, ?done, ?error) to report progress,
                           returning false if export should cancel
        """
        super(DatabaseSink, self).__init__(progress=progress)
        self._db       = db
        self._filename = filename
        self._flags = {
            "allow_empty":  True,   # retain new tables even if no rows inserted
            "data":         False,  # export table data in addition to schema
            "limit":        (),     # data limits, as (LIMIT, ) or (LIMIT, OFFSET)
            "maxcount":     None,   # maximum total number of rows to export over all tables
            "reverse":      False,  # output data rows in reverse order
        }
        self._state = {
            "allnames2":    None,   # CaselessDict of entity names in target database
            "columnnames":  None,   # list of columns of target table, for query or iterable
            "file_existed": None,   # whether target database file existed
            "fks_on":       None,   # whether foreign key constraint enforcement was enabled
            "fullname":     None,   # fully namespaced name of target table
            "samefile":     None,   # whether target database is same as source
            "schema2":      None,   # name of target database schema
            "sql_logs":     [],     # executed SQL statements as [(sql, params)], for action log
        }


    def configure(self, limit=None, maxcount=None, allow_empty=True, data=False, reverse=False):
        """
        Configures output options.

        @param   limit        table and query row limits, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
        @param   maxcount     maximum rows to export over all tables if exporting data
        @param   allow_empty  do not skip items with no output rows
                              (accounting for limit and maxcount if dumping data)
        @param   data         whether to export table data
        @param   reverse      output table data rows in reverse order
        @return               self
        """
        limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else (limit, )
        self._flags.update(limit=limit, maxcount=maxcount, allow_empty=allow_empty,
                           data=data, reverse=reverse)
        return self


    def export_entities(self, schema, renames=None, selects=False, iterables=None):
        """
        Exports selected tables and views to another database, tables optionally with data,
        auto-creating table and view indexes and triggers. Soft-locks database instance.

        @param   schema     {category: [name, ]} to export
        @param   renames    {category: {name1: name2}}
        @param   selects    {table name: SELECT SQL if not using default}
        @param   iterables  {table name: iterable yielding rows if not using select}
        @return             True on success, False on failure, None on cancel
        """
        result = False
        self._reset()
        self._db.lock(None, None, self._filename, label="database export")
        count_items = 0
        try:
            self._attach_target(toggle_fks=True)
            result, count_items = self._export_entities(schema, renames, selects, iterables)
            self._detach_target(toggle_fks=True)
        except Exception as e:
            self._detach_target(toggle_fks=True)
            self._process_error(e)
            return False
        finally:
            self._db.unlock(None, None, self._filename)
            if not self._state["file_existed"] and (not result or not count_items):
                util.try_ignore(os.unlink, self._filename)
        if result or (result is None and count_items and self._state["file_existed"]):
            sqls, params = zip(*self._state["sql_logs"])
            params = list(filter(bool, params))
            if not self._state["samefile"]: params = [self._filename] + params
            self._db.log_query("EXPORT TO DB", [grammar.terminate(x) for x in sqls], params)
        util.try_ignore(lambda: self._progress(done=True))
        return result


    def export_query(self, table, query, params=(), cursor=None, create_sql=None):
        """
        Exports query results to another database as new table. Soft-locks database instance.

        @param   table       target table name, expected to be unique in target database
        @param   query       SQL query text
        @param   params      SQL query parameters
        @param   cursor      existing results cursor to use instead of making a new query
        @param   create_sql  CREATE TABLE statement if not auto-generating from query columns
        @return              True on success, False on failure, None on cancel
        """
        result = False
        self._reset()
        self._db.lock(None, None, self._filename, label="query export")
        try:
            self._attach_target()
            row_count = self._export_query(table, query, params, cursor, create_sql)
            result = None if row_count is None else True
            if result and self._check_cancel(name=table, count=row_count):
                result = None
            if not result or (not row_count and not self._flags["allow_empty"]):
                self._drop_target_table(table)
                if result: result = False
            self._detach_target()
        except Exception as e:
            util.try_ignore(lambda: cursor.close())
            self._detach_target()
            self._process_error(e, table, query)
            return False
        else:
            sqls, params = zip(*self._state["sql_logs"])
            self._db.log_query("EXPORT QUERY TO DB", [grammar.terminate(x) for x in sqls], params)
        finally:
            self._db.unlock(None, None, self._filename)
            if not self._state["file_existed"] and not result:
                util.try_ignore(os.unlink, self._filename)
        util.try_ignore(lambda: self._progress(name=table, done=True))
        return result


    def _attach_target(self, toggle_fks=False):
        """
        Attaches target database to current SQLite instance if different file, populates file state.

        @param   toggle_fks  whether to disable foreign key constraints if enabled
        """
        self._state["samefile"] = is_samefile = util.is_samepath(self._db.filename, self._filename)
        self._state["file_existed"] = is_samefile or os.path.isfile(self._filename)
        if not is_samefile:
            schemas = [x["name"] for x in self._db.execute("PRAGMA database_list")]
            self._state["schema2"] = util.make_unique("main", schemas, suffix="%s")
            sql = "ATTACH DATABASE ? AS %s" % self._state["schema2"]
            self._db.execute(sql, [self._filename])
            self._state["sql_logs"].append((sql, [self._filename]))
        if toggle_fks:
            self._state["fks_on"] = self._db.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"]
            if self._state["fks_on"]:
                sql = "PRAGMA foreign_keys = off"
                self._db.execute(sql)
                self._state["sql_logs"].append((sql, None))


    def _detach_target(self, toggle_fks=False):
        """
        Detaches target database from current SQLite instance if different file.

        @param   toggle_fks  whether to re-enable foreign key constraints if disabled on attach
        """
        if toggle_fks and self._state["fks_on"]:
            sql = "PRAGMA foreign_keys = on"
            self._db.execute(sql)
            self._state["sql_logs"].append((sql, None))
        if self._state["samefile"] or not self._state["schema2"]: return
        try:
            sql = "DETACH DATABASE %s" % self._state["schema2"]
            self._db.execute(sql)
            self._state["logs"].append((sql, None))
            self._state["schema2"] = None
        except Exception: pass


    def _export_entities(self, schema, renames=None, selects=None, iterables=None):
        """
        Exports given items to target database,
        returns (None if cancel else True, number of items created).
        """
        result = False
        counts = {}
        renames = dict(renames or {})
        for category, mapping in list(renames.items()):
            if isinstance(mapping, dict) and not isinstance(mapping, util.CaselessDict):
                renames[category] = util.CaselessDict(mapping)

        entities = [self._db.schema[c][n] for c in self._db.CATEGORIES for n in schema.get(c, [])]
        for item in entities:
            category, name = item["type"], item["name"]
            name2 = renames.get(category, {}).get(name, name)
            try:
                created, count = self._export_entity(item, name2, counts, renames,
                                                     selects, iterables)
                if created: counts[name] = count
                if created and self._state["samefile"]:
                    self._db.populate_schema(category=category, name=name2, parse=True)
                if created is None or self._check_cancel(name=name, count=count):
                    result = None
                    break # for item
                if not result: result = created
            except Exception as e:
                logger.exception("Error exporting %s %s from %s to %s.",
                                 category, grammar.quote(name, force=True),
                                 self._db, self._filename)
                if self._check_cancel(name=name, error=util.format_exc(e)):
                    result = None
                    break # for item
        return result, len(counts)


    def _export_entity(self, item, name2, counts, renames=None, selects=None, iterables=None):
        """
        Exports entity schema and optionally data to target database.

        @return  (whether table created or None if cancelled, number of rows inserted)
        """
        created, count = False, 0
        category, name = item["type"], item["name"]
        created = self._create_target_entity(category, name, name2, item["sql"], renames)
        if not created or not self._flags["data"] or category != "table":
            return created, count

        insert_sql = self._make_data_insert(item, name2, counts, selects, iterables)
        label = "%s %s" % (category, grammar.quote(name, force=True))
        if name != name2: label += " as %s" % grammar.quote(name2, force=True)
        logger.info("Copying data to %s in %s.", label, self._filename)

        if iterables and name in iterables:
            cursor = iterables[name]
            for row in self._constrain_iterable(cursor, name, counts, self._flags["limit"],
                                                self._flags["maxcount"]):
                params = [row[n] for i, n in enumerate(self._state["columnnames"]) if i < len(row)]
                self._db.execute(insert_sql, params)
                count += 1
                if self._check_cancel(not count % self.PROGRESS_STEP):
                    return None, coumt
            if count:
                self._state["sql_logs"].append((insert_sql, ["( %s )" % util.plural("row", count)]))
            self._db.connection.commit()
            util.try_ignore(lambda: cursor.close())
        else:
            count = self._db.execute(insert_sql).rowcount
            self._db.connection.commit()
            self._state["sql_logs"].append((insert_sql, None))

        if not count and not self._flags["allow_empty"]:
            self._drop_target_table(name2)
            created = False
        return created, count


    def _make_data_insert(self, item, name2, counts, selects=None, iterables=None):
        """Returns INSERT statement for exporting table data to target database."""
        name = item["name"]
        target_prefix = "%s." % self._state["schema2"] if self._state["schema2"] else ""
        source_prefix = "main." if target_prefix else ""
        sql = "INSERT INTO %s%s " % (target_prefix, grammar.quote(name2))
        if iterables and name in iterables:
            cols = self._state["columnnames"] = [c["name"] for c in item["columns"]]
            sql += " VALUES (%s)" % ", ".join("?" * len(cols))
            return sql

        if selects and name in selects: sql += selects[name]
        else: sql += "SELECT * FROM %s%s" % (source_prefix, grammar.quote(name))
        order_sql = self._db.get_order_sql(name, reverse=True) if self._flags["reverse"] else ""
        limit_sql = ""
        if self._flags["limit"] or self._flags["maxcount"]:
            limit_sql = self._db.get_limit_sql(*self._flags["limit"],
                                               maxcount=self._flags["maxcount"], totals=counts)
        return sql + order_sql + limit_sql


    def _export_query(self, table, query, params=(), cursor=None, create_sql=None):
        """Creates and populates query results table, returns count inserted, or None on cancel."""
        count = 0
        is_select = grammar.strip_and_collapse(query)[:6] in ("SELECT", "VALUES")
        sql, cursor = self._prepare_query_table(table, query, params, is_select, cursor, create_sql)
        if is_select and not cursor:
            count = self._db.execute(sql, params).rowcount
            self._state["sql_logs"].append((sql, None))
        else:
            rows = cursor if cursor.description else [{"rowcount": cursor.rowcount}]
            for row in self._constrain_iterable(rows, limit=self._flags["limit"],
                                                maxcount=self._flags["maxcount"]):
                params = [row[n] for i, n in enumerate(self._state["columnnames"]) if i < len(row)]
                self._db.execute(sql, params)
                if self._check_cancel(not count % self.PROGRESS_STEP):
                    return None
                count += 1
            if count:
                self._state["sql_logs"].append((sql, ["( %s )" % util.plural("row", count)]))
            util.try_ignore(lambda: rows.close())
        self._db.connection.commit()
        if count in (None, -1): # If CREATE TABLE AS query
            sql = "SELECT COUNT(*) AS count FROM %s" % self._state["fullname"]
            countrow = self._db.execute(sql).fetchone()
            count = countrow["count"]
        return count


    def _populate_target_schema(self):
        """Populates state for target database schema."""
        self._state["allnames2"] = util.CaselessDict()
        target_prefix = "%s." % self._state["schema2"] if self._state["schema2"] else ""
        for row in self._db.execute("SELECT name, type FROM %ssqlite_master" % target_prefix):
            self._state["allnames2"][row["name"]] = row["type"]


    def _populate_target_columns(self, table):
        """Populates column names of target table for query export.."""
        target_prefix = "%s." % self._state["schema2"] if self._state["schema2"] else ""
        rows = self._db.execute("PRAGMA %stable_xinfo(%s)" %
                                (target_prefix, grammar.quote(table))).fetchall()
        self._state["columnnames"] = [x["name"] for x in rows if x.get("hidden") != 1]


    def _prepare_query_table(self, table, query, params, is_select, cursor=None, create_sql=None):
        """
        Creates new table for query results if applicable, returns SQL to execute for export.

        @return   (SQL to execute for export, database cursor to read from if any)
        """
        action_sql = None
        fullname = grammar.quote(table)
        if not self._state["samefile"]: fullname = "%s.%s" % (self._state["schema2"], fullname)
        self._state["fullname"] = fullname
        if is_select and not cursor:
            if create_sql:
                if not self._create_target_entity("table", table, table, create_sql):
                    raise Exception("Failed to create target table %r" % table)

                self._populate_target_columns(table)
                peek_cursor = self._db.execute(query, params)
                if len(peek_cursor.description) == len(self._state["columnnames"]):
                    action_sql = "INSERT INTO %s %s" % (fullname, query)
                    peek_cursor.close()
                else: # Table has more or fewer columns than query: insert each row manually
                    colstr = ", ".join(grammar.quote(x[0]) for x in peek_cursor.description)
                    paramstr = ", ".join(["?"] * len(peek_cursor.description))
                    action_sql = "INSERT INTO %s (%s) VALUES (%s)" % (fullname, colstr, paramstr)
                    cursor = peek_cursor
            else:
                action_sql = "CREATE TABLE %s AS %s" % (fullname, query)
            if self._flags["limit"]:
                limit_pairs = zip(("LIMIT", "OFFSET"), map(str, self._flags["limit"]))
                action_sql += (" " + " ".join(" ".join(x) for x in limit_pairs))
        else:
            if not cursor: cursor = self._db.execute(query, params)
            cols = [c[0] for c in cursor.description] if cursor.description else ["rowcount"]
            sql = create_sql
            sql = sql or "CREATE TABLE %s (%s)" % (fullname, ", ".join(map(grammar.quote, cols)))
            self._db.executescript(sql)
            self._state["sql_logs"].append((sql, None))
            self._populate_target_columns(table)
            action_sql = "INSERT INTO %s VALUES (%s)" % (fullname, ", ".join(["?"] * len(cols)))
        return action_sql, cursor


    def _create_target_entity(self, category, name, name2, create_sql, renames=None):
        """
        Creates entity in target database, drops existing if any.

        @return  success as True/False, or None on error and cancel
        """
        do_separate_connection = False
        myrenames = dict(renames or {})
        fullname = grammar.quote(name2)
        if not self._state["samefile"]:
            myrenames["schema"] = self._state["schema2"]
            fullname = "%s.%s" % (self._state["schema2"], fullname)
        if myrenames:
            create_sql2, err = grammar.transform(create_sql, renames=myrenames)
            if err: # Fails if original SQL is not parseable: create separately if possible
                if self._check_cancel(name=name, error=err):
                    return None
                if renames:
                    return False
                do_separate_connection = True
            else:
                create_sql = create_sql2

        if self._state["allnames2"] is None:
            self._populate_target_schema()
        if name2 in self._state["allnames2"]:
            category2 = self._state["allnames2"][name2]
            logger.info("Dropping %s %s in %s.",
                        category2, grammar.quote(name2, force=True), self._filename)
            drop_sql = "DROP %s %s" % (category2.upper(), fullname)
            self._db.execute(drop_sql)
            self._state["sql_logs"].append((drop_sql, None))
            self._populate_target_schema() # Repopulate for cascaded drops

        label = "%s %s" % (category, grammar.quote(name, force=True))
        if name != name2: label += " as %s" % grammar.quote(name2, force=True)
        logger.info("Creating %s in %s.", label, self._filename)
        if do_separate_connection:
            with database.Database(self._filename) as db2:
                db2.execute(create_sql)
        else:
            self._db.execute(create_sql)
        self._state["sql_logs"].append((create_sql, None))
        self._state["allnames2"][name2] = category
        self._state["fullname"] = fullname
        return True


    def _process_error(self, exc, table=None, query=None):
        """Logs error, deletes target file if it did not exist before."""
        querystr = " query %r" % query if query else ""
        logger.exception("Error exporting%s from %s to %s.", querystr, self._db, self._filename)
        if not self._state["file_existed"]:
            util.try_ignore(os.unlink, self._filename)
        if self._progress:
            kwargs = dict(done=True, error=util.format_exc(exc), **{"name": table} if table else {})
            util.try_ignore(lambda: self._progress(**kwargs))


    def _reset(self):
        """Clears internal state."""
        for key in list(self._state): self._state[key] = None
        self._state.update(cancelled=False, sql_logs=[])


    def _drop_target_table(self, name):
        """Drops table from target database."""
        label = grammar.quote(name, force=True)
        logger.info("Dropping empty table %s from %s.", label, self._filename)
        sql = "DROP TABLE %s" % self._state["fullname"]
        self._db.execute(sql)
        self._state["sql_logs"].append((sql, None))
        self._db.connection.commit()
        if self._state["allnames2"]: self._state["allnames2"].pop(name, None)



class DumpSink(Sink):
    """Exports database dump to SQL file."""


    def __init__(self, db, filename, progress=None):
        """
        @param   db        Database instance
        @param   filename  output SQL filename
        @param   progress  callback(name, ?count, ?error, ?done) to report progress,
                           returning false if export should cancel
        """
        super(DumpSink, self).__init__(progress=progress)
        self._db       = db
        self._filename = filename
        self._flags = {
            "allow_empty": True,   # include tables with no rows
            "data":        False,  # export table data in addition to schema
            "limit":       (),     # data limits, as (LIMIT, ) or (LIMIT, OFFSET)
            "maxcount":    None,   # maximum total number of rows to export over all tables
            "pragma":      True,   # whether to dump PRAGMA settings
            "reverse":     False,  # whether to output data rows in reverse order
        }
        self._state = {
            "cursors":     [],     # list of database cursors used during export
        }


    def configure(self, limit=None, maxcount=None, allow_empty=True,
                  pragma=True, data=False, reverse=False):
        """
        Configures output options.

        @param   limit        table row limits, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
        @param   maxcount     maximum total number of rows to export over all tables
        @param   allow_empty  do not skip items with no output rows
                              (accounting for limit and maxcount)
        @param   pragma       whether to dump PRAGMA settings
        @param   data         whether to export table data, or schemas only
        @param   reverse      whether to output table rows in reverse order
        @return               self
        """
        limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else (limit, )
        self._flags.update(limit=limit, maxcount=maxcount, allow_empty=allow_empty,
                           pragma=pragma, data=data, reverse=reverse)
        return self


    def dump_database(self, schema=None, info=None):
        """
        Dumps database schema and optionally data to SQL file. Soft-locks database instance.

        @param   schema    {category: [name, ]} to export if not everything in database
        @param   info      additional metadata for export, as {title: text or {label: text}}
        @return            True on success, False on failure, None on cancel
        """
        result = False
        self._db.lock(None, None, self._filename, label="database dump")
        try:
            with open(self._filename, "wb") as f:
                namespace = self._make_template_namespace(schema, info, buffer=f)
                template = step.Template(templates.DUMP_SQL, strip=False, postprocess=convert_lf)
                template.stream(f, namespace, buffer_size=0)
                result = None if self._check_cancel(done=True) else True
        except Exception as e:
            logger.exception("Error exporting database dump from %s to %s.",
                             self._db, self._filename)
            util.try_ignore(lambda: self._progress(error=util.format_exc(e), done=True))
            result = False
        finally:
            self._db.unlock(None, None, self._filename)
            for cursor in self._state["cursors"]: util.try_ignore(lambda: cursor.close())
            if not result: util.try_ignore(os.unlink, self._filename)

        return result


    def _collect_schema(self, schema=None):
        """
        Returns {category: {name: {..item..}}} for current export settings.

        @param   schema    {category: [name, ]} to filter by if not everything in database
        """
        entities = copy.deepcopy(self._db.schema)
        for category in set(schema) & set(entities) if schema else ():
            names = [x.lower() for x in schema[category]]
            for name in list(entities[category]):
                if name.lower() not in names: entities[category].pop(name)
        if self._flags["allow_empty"]:
            return entities
        # Discard empty tables and views, and their indexes and triggers
        empties = []
        offset_sql = " OFFSET %s" % self._flags["limit"][1] if len(self._flags["limit"]) > 1 else ""
        for category, name in [(c, n) for c in self._db.DATA_CATEGORIES for n in entities.get(c, {})]:
            sql = "SELECT 1 FROM %s LIMIT 1%s" % (grammar.quote(name), offset_sql)
            if not any(self._db.select(sql, error="Error checking count in %s %s." %
                                       (category, grammar.quote(name, force=True)))):
                empties.append(name)
        while empties:
            name = empties.pop(0)
            item = next(d[name] for d in self._db.schema.values() if name in d)
            if item["name"] not in entities.get(item["type"], {}): continue # while
            entities[item["type"]].pop(item["name"])
            if item["type"] in ("table", "view"):
                for rels in self._db.get_related(item["type"], item["name"], own=True).values():
                    empties.extend(rels)
        return entities


    def _make_datas(self, entities):
        """Yields {name, columns, rows} for each table to export."""
        counts = collections.defaultdict(int) # {name: number of rows yielded}
        for name, item in entities.get("table", {}).items():
            if self._check_cancel(name=name): break # for name, item

            kwargs = dict(db=self._db, category="table", name=name, counts=counts)
            kwargs.update({key: self._flags[key] for key in ("limit", "maxcount", "reverse")})
            cursor = self._make_item_iterable(**kwargs)
            self._state["cursors"].append(cursor)
            yield {"name": name, "columns": item["columns"], "rows": cursor}
            util.try_ignore(lambda: cursor.close())
            if self._check_cancel(name=name, done=True): break # for name, item


    def _make_template_namespace(self, schema=None, info=None, **namespace_extras):
        """Returns namespace dictionary for dump template,"""
        entities = self._collect_schema(schema)
        if schema or not self._flags["allow_empty"]:
            sql = "\n\n".join("\n\n".join(v["sql"] for v in entities[c].values())
                              for c in self._db.CATEGORIES if c in entities)
        else:
            sql = self._db.get_sql()
        return dict({
            "db":       self._db,
            "sql":      sql,
            "data":     self._make_datas(entities) if self._flags["data"] else [],
            "pragma":   self._db.get_pragma_values(dump=True) if self._flags["pragma"] else {},
            "info":     info,
            "progress": self._progress,
        }, **namespace_extras)



class InfoSink(Sink):
    """Exports database statistics and arbitrary SQL to file."""

    FORMATS = {"html": templates.DATA_STATISTICS_HTML,
               "sql":  templates.DATA_STATISTICS_SQL,
               "txt":  templates.DATA_STATISTICS_TXT}


    def __init__(self, db, filename):
        """
        @param   db        Database instance
        @param   filename  output SQL filename
        """
        super(InfoSink, self).__init__()
        self._db       = db
        self._filename = filename


    def write_sql(self, sql, headers=()):
        """
        Writes arbitrary SQL text to file.

        @param   headers  one or more strings for file header comments
        @return           True
        """
        template = step.Template(templates.CREATE_SQL, strip=False, postprocess=convert_lf)
        ns = {"headers": util.tuplefy(headers) if headers else (), "db": self._db, "sql": sql}
        with open(self._filename, "wb") as f: template.stream(f, ns)
        return True


    def write_statistics(self, format, data, diagram=None):
        """
        Exports statistics to HTML or SQL or TXT file.

        @param   format   one of "html", "sql" or "txt"
        @param   data     {"table":   [{name, size, size_total, ?size_index, ?index: []}],
                           "index":   [{name, size, table}], }
        @param   diagram  {"bmp": schema diagram as wx.Bitmap,
                           "svg": schema diagram as SVG string}
        """
        if format not in self.FORMATS:
            raise ValueError("Unknown format %r" % (format, ))

        template = step.Template(self.FORMATS[format], postprocess=convert_lf,
                                 strip=False, escape="html" == format)
        ns = {
            "title":  "Database statistics",
            "db":     self._db,
            "pragma": self._db.get_pragma_values(stats=True),
            "sql":    self._db.get_sql(),
            "stats":  data,
        }
        if diagram: ns["diagram"] = diagram
        with open(self._filename, "wb") as f: template.stream(f, ns)
        return True



class FileDataSink(Sink):
    """Exports table and view data or query data to output files."""

    SINGLE_TEMPLATES = {"html": templates.DATA_HTML,
                        "json": templates.DATA_JSON,
                        "sql":  templates.DATA_SQL,
                        "txt":  templates.DATA_TXT,
                        "yaml": templates.DATA_YAML}

    COMBINED_TEMPLATES = {"html": templates.DATA_HTML_MULTIPLE,
                          "json": templates.DATA_JSON_MULTIPLE,
                          "sql":  templates.DATA_SQL_MULTIPLE,
                          "txt":  templates.DATA_TXT_MULTIPLE,
                          "yaml": templates.DATA_YAML_MULTIPLE}

    PART_TEMPLATES = {"html": templates.DATA_HTML_MULTIPLE_PART,
                      "json": templates.DATA_JSON,
                      "sql":  templates.DATA_SQL_MULTIPLE_PART,
                      "txt":  templates.DATA_TXT_MULTIPLE_PART,
                      "yaml": templates.DATA_YAML_MULTIPLE_PART}

    ROW_TEMPLATES = {"html": templates.DATA_ROWS_HTML,
                     "json": templates.DATA_ROWS_JSON,
                     "sql":  templates.DATA_ROWS_SQL,
                     "txt":  templates.DATA_ROWS_TXT,
                     "yaml": templates.DATA_ROWS_YAML}

    def __init__(self, db, filename, format, progress=None):
        """
        @param   db        Database instance
        @param   filename  full path and filename of resulting file
        @param   format    file format like "csv"
        @param   progress  callback(name, count) to report progress,
                           returning false if export should cancel
        """
        if format not in EXPORT_EXTS:
            raise ValueError("Unknown format %r" % (format, ))

        super(FileDataSink, self).__init__(progress=progress)
        self._db       = db
        self._filename = filename
        self._format   = format
        self._flags = {
            "allow_empty":  True,   # include tables with no rows
            "limit":        (),     # data limits, as (LIMIT, ) or (LIMIT, OFFSET)
            "maxcount":     None,   # maximum total number of rows to export over all tables
            "reverse":      False,  # whether to output data rows in reverse order
        }
        self._state = {
            "columns":      [],     # current item columns as [{name, ?type}]
            "columnjusts":  [],     # dict of {column name: True if left-justified}
            "columnnames":  [],     # list of current item column names
            "columnwidths": [],     # dict of {column name: maximum character width}
            "itemfiles":    collections.OrderedDict(),  # {filename: {name, title, count}}
            "tmpnames":     [],     # list of temporary files for item outputs
            "writer":       None,   # csv_writer/xlsx_writer instance if any
        }


    def configure(self, limit=None, maxcount=None, allow_empty=True, reverse=False):
        """
        Configures combined output options.

        @param   limit        data limits, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
        @param   maxcount     maximum total number of rows to export over all entities
        @param   allow_empty  do not skip items with no output rows
                              (accounting for limit and maxcount)
        @param   reverse      whether to output data rows in reverse order in combined export
                              if make_iterables not given
        @return               self
        """
        limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else (limit, )
        self._flags.update(limit=limit, maxcount=maxcount, allow_empty=allow_empty, reverse=reverse)
        return self


    def export_entity(self, category, name, make_iterable, title, columns, info=None):
        """
        Exports table or view data to output file.

        @param   category        category producing the data, "table" or "view"
        @param   name            name of the table or view producing the data
        @param   make_iterable   function returning iterable sequence yielding rows
        @param   title           export title, as string or a sequence of strings
        @param   columns         iterable columns, as [name, ] or [{"name": name}, ]
        @param   info            additional metadata for export, as {title: text or {label: text}}
        @return                  True on success, False on failure, None on cancel
        """
        return self._export_single(make_iterable, title, columns, category, name, info=info)


    def export_query(self, query, make_iterable, title, name, columns, info=None):
        """
        Exports query data to output file.

        @param   query           the SQL query producing the data
        @param   make_iterable   function returning iterable sequence yielding rows
        @param   title           export title, as string or a sequence of strings
        @param   name            name for target table in SQL output
        @param   columns         iterable columns, as [name, ] or [{"name": name}, ]
        @param   info            additional metadata for export, as {title: text or {label: text}}
        @return                  True on success, False on failure, None on cancel
        """
        return self._export_single(make_iterable, title, columns, name=name, query=query, info=info)


    def export_combined(self, title, category=None, names=None, make_iterables=None, info=None):
        """
        Exports data from multiple tables or views to a single combined output file.

        @param   title           export title, as string or a sequence of strings
        @param   category        category to produce the data from, "table" / "view" / None for both
        @param   names           specific entities to export if not all
        @param   make_iterables  function yielding pairs of
                                 ({name, type, title, columns}, function yielding rows)
                                 if not using category
        @param   info            additional metadata for export, as {title: text or {label: text}}
        """
        result = False
        try:
            schema = self._collect_schema(category, names, make_iterables)
            for category, name in ((c, n) for c in (schema or {}) for n in schema[c]):
                self._db.lock(category, name, self._filename, label="export")
            with open(self._filename, "wb") as f:
                self._prepare_output(f, title, info)
                for item, make_iterable in self._make_iterables(schema, make_iterables):
                    self._prepare_item(make_iterable, item["columns"])
                    row_count = self._write_item_combined(item, make_iterable, info)
                    if row_count is None:
                        result = None
                        return result
                self._finalize_combined(f, title, info)
            result = None if self._check_cancel() else True
        except Exception as e:
            logger.exception("Error exporting from %s to %s.", self._db, self._filename)
            util.try_ignore(lambda: self._progress(error=util.format_exc(e), done=True))
        finally:
            self._cleanup(result, schema)
        return result


    def _cleanup(self, result, schema=None):
        """Cleans up resources, unlocks entities, deletes output file if result not success."""
        util.try_ignore(lambda: self._state["writer"].close())
        for tmpname in self._state["tmpnames"]:
            util.try_ignore(os.unlink, tmpname)
        for category, name in ((c, n) for c in (schema or {}) for n in schema[c]):
            self._db.unlock(category, name, self._filename)
        if not result: util.try_ignore(os.unlink, self._filename)


    def _collect_schema(self, category, names, make_iterables):
        """Returns schema to export as {category: {name: {..item..}}}."""
        categories = [] if make_iterables else [category] if category else self._db.DATA_CATEGORIES
        if names:
            schema = {}
            for name in names:
                item = next((self._db.schema[c][name] for c in categories
                             if name in self._db.schema[c]), None)
                if item: schema.setdefault(item["type"], util.CaselessDict())[name] = item
        else: schema = {c: self._db.schema[c].copy() for c in categories}
        return schema


    def _export_single(self, make_iterable, title, columns,
                       category=None, name=None, query=None, info=None):
        """Exports entity or query to file, returns True/False/None for success/failure/cancel."""
        result = False
        row_count = 0
        if category and name is not None:
            self._db.lock(category, name, make_iterable, label="export")
        try:
            with open(self._filename, "wb") as f:
                self._prepare_output(f, title, info, query)
                self._prepare_item(make_iterable, columns)
                if self._check_cancel():
                    result = None
                    return result
                iterable = self._constrain_iterable(make_iterable, limit=self._flags["limit"],
                                                    maxcount=self._flags["maxcount"])
                if self._format in ("csv", "xlsx"):
                    row_count = self._write_item_spreadsheet(iterable, name, query)
                else:
                    row_count = self._write_item_template(iterable, name)
                if row_count is None:
                    result = None
                    return result
                self._finalize_item_single(f, row_count, title, category, name, query, info)
                result = True
            if self._check_cancel(name=name, count=row_count):
                result = None
                return result
        except Exception as e:
            logger.exception("Error exporting from %s to %s.", self._db, self._filename)
            util.try_ignore(lambda: self._progress(error=util.format_exc(e), done=True))
            result = False
        finally:
            if category and name is not None:
                self._db.unlock(category, name, make_iterable)
            self._cleanup(result)
        return result


    def _finalize_combined(self, file, title, info=None):
        """Writes final output file for combined templated export, merging entity files."""
        if self._format in ("csv", "xlsx"): return
        namespace = {
            "db":       self._db,
            "title":    title,
            "files":    self._state["itemfiles"],
            "combined": True,
            "info":     info,
            "progress": self._progress,
        }
        template = step.Template(self.COMBINED_TEMPLATES[self._format], postprocess=convert_lf,
                                 strip=False, escape="html" == self._format)
        template.stream(file, namespace)


    def _finalize_item_combined(self, item, row_count, info=None):
        """Writes entity file for combined templated export, merging item rows file."""
        category, name = item["type"], item["name"]
        title = "%s %s" % (item["type"].capitalize(), grammar.quote(name, force=True))
        namespace = {
            "category":   category,
            "columns":    self._state["columns"],
            "combined":   True,
            "create_sql": self._make_item_create_sql(category, name),
            "db":         self._db,
            "info":       info,
            "name":       name,
            "progress":   self._progress,
            "row_count":  row_count,
            "sql":        None,
            "title":      title,
        }
        if "txt" == self._format: namespace.update({
            "columnjusts":  self._state["columnjusts"],
            "columnwidths": self._state["columnwidths"],
        })
        rowspath = self._state["tmpnames"][-1]
        prefix = "%s.%s.item" % (os.path.basename(self._filename), len(self._state["tmpnames"]) - 1)
        fh, partpath = tempfile.mkstemp(prefix=prefix)
        self._state["tmpnames"].append(partpath)
        with open(rowspath, "rb") as rowsfile, io.open(fh, "wb+") as partfile:
            namespace["data_buffer"] = iter(lambda: rowsfile.read(65536), b"")
            template = step.Template(self.PART_TEMPLATES[self._format], postprocess=convert_lf,
                                     strip=False, escape="html" == self._format)
            template.stream(partfile, namespace) # Populates row_count
        self._state["itemfiles"][partpath] = dict(item, count=row_count)
        self._state["itemfiles"][partpath].setdefault("title", title)


    def _finalize_item_single(self, file, row_count, title,
                              category=None, name=None, query=None, info=None):
        """Writes entity file for combined templated export, merging item rows file."""
        if self._format in ("csv", "xlsx"): return

        blank = not row_count and not self._flags["allow_empty"]
        namespace = {
            "category":     category,
            "columns":      self._state["columns"],
            "combined":     False,
            "create_sql":   "" if blank else self._make_item_create_sql(category, name, query),
            "db":           self._db,
            "info":         info,
            "name":         name,
            "progress":     self._progress,
            "row_count":    row_count,
            "sql":          query,
            "title":        title,
        }
        if "txt" == self._format: namespace.update({
            "columnjusts":  self._state["columnjusts"],
            "columnwidths": self._state["columnwidths"],
        })
        # Produce main output from temporary file content
        with open(self._state["tmpnames"][-1], "rb") as rowsfile:
            namespace["data_buffer"] = "" if blank else iter(lambda: rowsfile.read(65536), b"")
            template = step.Template(self.SINGLE_TEMPLATES[self._format], postprocess=convert_lf,
                                     strip=False, escape="html" == self._format)
            template.stream(file, namespace)


    def _make_iterables(self, schema, make_iterables=None):
        """Yields pairs of (item, function yielding rows), enforcing limit constraints."""
        counts = collections.defaultdict(int) # {name: number of rows yielded}
        limit, maxcount = self._flags["limit"], self._flags["maxcount"]
        if not make_iterables: # Produce all data ourselves, limited and ordered as configured
            for category, item in ((c, x) for c, d in schema.items() for x in d.values()):
                title = "%s %s" % (category.capitalize(), grammar.quote(item["name"], force=True))
                kwargs = dict(db=self._db, category=item["type"], name=item["name"], counts=counts,
                              limit=limit, maxcount=maxcount, reverse=self._flags["reverse"])
                yield dict(item, title=title), functools.partial(self._make_item_iterable, **kwargs)
        elif limit or maxcount is not None: # Apply configured limits on provided iterables
            for item, make_iterable in make_iterables():
                kwargs = dict(iterable=make_iterable, name=item["name"], counts=counts,
                              limit=limit, maxcount=maxcount)
                yield item, functools.partial(self._constrain_iterable, **kwargs)
        else: # Passthrough
            for item, make_iterable in make_iterables():
                yield item, make_iterable


    def _make_xlsx_writer(self, title, info=None, query=None):
        """Returns xlsx_writer initialized with given metainfo."""
        format_dict = lambda d: "\n".join("%s: %s" % (k, v) for k, v in d.items())
        infostring = "\n\n".join(format_dict(v) if isinstance(v, dict) else "%s: %s" % (k, v)
                                 for k, v in (info or {}).items())
        querystring = "Query: %s" % query if query else None
        commentstrings = [infostring, querystring, templates.export_comment()]
        props = {"title": "; ".join(util.tuplefy(title)),
                 "subject": "Source: %s" % self._db, "author": conf.Title,
                 "comments": "\n\n".join(filter(bool, commentstrings))}
        return xlsx_writer(self._filename, props=props)


    def _prepare_item(self, make_iterable, columns):
        """Populates columns metadata."""
        columns = [x if isinstance(x, dict) else {"name": x} for x in columns]
        self._state["columns"] = columns
        self._state["columnnames"] = [x["name"] for x in columns]
        if "txt" == self._format:
            widths, justs = self._measure_columns(columns, make_iterable)
            self._state.update({"columnjusts": justs, "columnwidths": widths})


    def _prepare_output(self, file, title, info=None, query=None):
        """Closes file handle and opens writers if CSV/XLSX output."""
        if "csv" == self._format:
            file.close()
            self._state["writer"] = csv_writer(self._filename)
        elif "xlsx" == self._format:
            file.close()
            self._state["writer"] = self._make_xlsx_writer(title, info, query)


    def _write_spreadsheet_header(self, name=None, query=None, combined=False):
        """Writes spreadsheet header."""
        writer = self._state["writer"]
        if "csv" == self._format:
            if query: writer.writerow([re.sub("[\r\n]+", " ", query)])
            if combined:
                writer.writerow()
                if name is not None and not query: writer.writerow([name])
                writer.writerow([""] + self._state["columnnames"])
            else: writer.writerow(self._state["columnnames"])
        elif "xlsx" == self._format:
            writer.add_sheet("SQL query" if query else name)
            writer.set_header(True)
            if query: writer.writerow([query], "bold", autowidth=False)
            writer.writerow(self._state["columnnames"])
            writer.set_header(False)


    def _write_spreadsheet_row(self, row, combined=False):
        """Writes spreadsheet row."""
        values = ["" if row[c] is None else row[c] for c in self._state["columnnames"]]
        if "csv" == self._format and combined: values = [""] + values
        self._state["writer"].writerow(values)


    def _write_item_combined(self, item, make_iterable, info=None):
        """Writes item for combined export, returns number of rows written, or None on cancel."""
        cursor = make_iterable()
        try:
            if self._format in ("csv", "xlsx"):
                row_count = self._write_item_spreadsheet(cursor, item["name"], combined=True)
            else:
                row_count = self._write_item_template(cursor, item["name"], combined=True)
                if row_count or self._flags["allow_empty"]:
                    self._finalize_item_combined(item, row_count, info)
            if row_count is not None and self._check_cancel(name=item["name"], count=row_count):
                return None
            return row_count
        finally: util.try_ignore(lambda: cursor.close())


    def _write_item_spreadsheet(self, cursor, name=None, query=None, combined=False):
        """
        Writes data to spreadsheet file, returns number of data rows written, or None on cancel.
        """
        row_count, row, nextrow = 0, next(cursor, None), next(cursor, None)
        if not combined or row or self._flags["allow_empty"]:
            self._write_spreadsheet_header(name, query, combined=combined)
        while row:
            self._write_spreadsheet_row(row, combined=combined)
            row_count, row, nextrow = row_count + 1, nextrow, next(cursor, None)
            if self._check_cancel(not row_count % self.PROGRESS_STEP, name=name, count=row_count):
                return None
        return row_count


    def _make_item_create_sql(self, category, name, query=None):
        """Returns CREATE SQL statement: existing if table else generating new if view or query."""
        if query:
            meta = {"__type__": grammar.SQL.CREATE_TABLE, "name": name,
                    "columns": self._state["columns"]}
            return grammar.generate(meta)[0]
        elif "sql" == self._format and "view" == category:
            # Add CREATE statement for saving view AS table
            meta = {"name": name, "columns": self._state["columns"],
                    "sql": self._db.get_sql(category, name)}
            tpl = step.Template(templates.CREATE_VIEW_TABLE_SQL, strip=False)
            return tpl.expand(meta).strip()
        elif name:
            # Add CREATE statement
            transform = {"flags": {"exists": True}} if "sql" == self._format else None
            try: return self._db.get_sql(category, name, transform=transform)
            except Exception:
                if transform:
                    logger.error("Error transforming CREATE SQL statement for %s %s, "
                                 "falling back to original CREATE SQL.",
                                 category, grammar.quote(name, force=True), exc_info=True)
                    return self._db.get_sql(category, name)
        return None


    def _write_item_template(self, cursor, name=None, combined=False):
        """Writes data to templated file, returns number of rows written."""
        counter = itertools.count(start=1)
        iterate_count = lambda c: (x for x in c if next(counter))  # Count rows locally
        namespace = {
            "columns":   self._state["columns"],
            "combined":  combined,
            "name":      name,
            "progress":  self._progress,
            "rows":      iterate_count(cursor),
        }
        if "txt" == self._format: namespace.update({
            "columnwidths": self._state["columnwidths"],
            "columnjusts":  self._state["columnjusts"],
        })

        # Write out data to temporary file first, obtaining row count for outer template
        prefixfmt = "%%s.%s.rows." % len(self._state["tmpnames"]) if combined else "%s.rows."
        fh, tmpname = tempfile.mkstemp(prefix=prefixfmt % os.path.basename(self._filename))
        self._state["tmpnames"].append(tmpname)
        with io.open(fh, "wb+") as tmpfile:
            template = step.Template(self.ROW_TEMPLATES[self._format], postprocess=convert_lf,
                                     strip=False, escape="html" == self._format)
            template.stream(tmpfile, namespace)
        return next(counter) - 1



class FileDataSource(Base):
    """Imports data from spreadsheets and JSON/YAML data files."""


    def __init__(self, filename, db=None, progress=None):
        """
        @param   filename  source data file path
        @param   db        target Database instance if any
        @param   progress  callback() to report progress from get_file_data()
                           or callback(?name, ?section, ?count, ?done, ?error, ?errorcount, ?index)
                           to report progress from import_data(),
                           returning False if process should cancel,
                           and None if import should rollback.
                           Returning True on error will ignore further errors.
        """
        format = self.get_format(filename)
        if not format:
            raise ValueError("File format not recognized")

        super(FileDataSource, self).__init__(progress)
        self._filename = filename
        self._db       = db
        self._file     = None  # Opened file handle or openpyxl/xlrd workbook
        self._format   = format
        self._flags = {
            "seek":        True,  # skip initial empty spreadsheet rows
            "has_header":  True,  # whether spreadsheet file being imported has header rows
            "limit":       (),    # import limits per sheet as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
            "maxcount":    None,  # maximum total number of rows to import over all sheets
        }
        self._state = {
            "continue_on_error": None,   # whether import should continue on error
            "create_sql":        None,   # CREATE TABLE statement for current table
            "cursor":            None,   # database transaction cursor
            "error_count":       0,      # number of insert errors for current table
            "error_count_last":  0,      # number of insert errors for current table from last loop
            "file_existed":      False,  # whether database existed before
            "has_names":         False,  # whether source file has column names (JSON/YAML)
            "has_sections":      False,  # whether multiple sheet format
            "insert_count":      0,      # number of successful inserts for current table
            "insert_sql":        None,   # INSERT statement for current table
            "new_tables":        [],     # new tables created in database
            "section":           None,   # current worksheet being imported
            "table":             None,   # current table being imported to
            "was_open":          False,  # whether database was open before
        }


    def configure(self, has_header=True, limit=None, maxcount=None, seek=True):
        """
        Configures import options.

        @param   has_header     whether spreadsheet file has header rows
        @param   limit          import limits per sheet, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
        @param   maxcount       maximum total number of rows to import over all sheets
        @param   seek           whether to skip initial empty spreadsheet rows
        @return                 self
        """
        limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else (limit, )
        self._flags.update(has_header=has_header, limit=limit, maxcount=maxcount, seek=seek)
        return self


    def get_file_info(self):
        """
        Returns import file metadata, as {
            "name":        file name and path,
            "size":        file size in bytes,
            "modified":    file modification timestamp
            "format":      "xlsx", "xlsx", "csv", "json" or "yaml",
            "sections":      [
                "name":    worksheet name if multiple sheet format else descriptive label,
                "rows":    count or -1 if file too large,
                "columns": [first row cell value, ] for spreadsheets, or
                           OrderedDict(first row column name: value) for JSON/YAML
        ]}, or None if cancelled.
        """
        if not os.path.isfile(self._filename) or not os.path.getsize(self._filename):
            raise ValueError("File is empty." if os.path.isfile(self._filename) else "No such file.")

        logger.info("Getting import data from %s.", self._filename)
        filesize = os.path.getsize(self._filename)
        result = {"name": self._filename, "size": filesize, "format": self._format, "sections": [],
                  "modified": datetime.datetime.fromtimestamp(os.path.getmtime(self._filename))}
        self._open_file()
        try:
            for section_name in self._get_sections():
                row_count, row_index, columns = 0, 0, []
                for row_index, row in self._produce_rows(section=section_name, dicts=True):
                    row_count += 1
                    if row_count != 1: continue # for row_index, row
                    if isinstance(row, dict): columns = row
                    else: columns = [x.strip() if isinstance(x, six.string_types)
                                     else "" if x is None else str(x) for x in row]
                    if self._format in ("xls", "xlsx") or filesize > conf.MaxImportFilesizeForCount:
                        break # for row_index, row
                rows = self._get_row_count(row_count, row_index - row_count + 1, section_name)
                result["sections"].append({"name": section_name, "rows": rows, "columns": columns})
                if self._check_cancel():
                    return None
        finally:
            self._close_file()
        return result


    @classmethod
    def get_format(cls, filename):
        """Returns import file format like "yaml", or None, detected from filename extension."""
        extname = os.path.splitext(filename)[-1][1:].lower()
        if extname in IMPORT_EXTS:
            return "yaml" if extname in YAML_EXTS else extname
        return None


    def import_data(self, tables):
        """
        Imports data from spreadsheet or JSON or YAML data file to database table.
        Will create tables if not existing yet.

        @param   tables  tables to import to and sections to import from, as [{
                           "name": table name,
                           "section": worksheet name, ignored if not multiple sheet format,
                           "columns": OrderedDict(file column key: table column name)
                           ?"pk": name of auto-increment primary key to add if new table,
                         }];
                         file column key is column index if spreadsheet else column name
        @return          True on success, False on failure, None on cancel
        """
        if not os.path.isfile(self._filename) or not os.path.getsize(self._filename):
            raise ValueError("File is empty." if os.path.isfile(self._filename) else "No such file.")

        result = True
        try:
            total_insert_count = 0
            self._prepare_import()
            for item in tables:
                self._prepare_table(item)
                if self._check_cancel(name=item["name"], section=item["section"], index=0, count=0):
                    result = None
                    break # for item
                insert_count = self._import_table(total_insert_count)
                self._db.unlock("table", item["name"], self._filename)
                if insert_count is False or insert_count is None:
                    result = insert_count
                    break # for item
                total_insert_count += insert_count
        except Exception as e:
            self._process_import_error(e)
            result = False
        finally:
            self._finalize_import(result)
        return result


    def iter_rows(self, columns=None, section=None):
        """
        Yields rows as a list of values.

        @param   columns     list of column keys to return if not all columns,
                             where key is column index if spreadsheet else column name
        @param   section     sheet name to read from, if multiple sheet format
        """
        if not os.path.isfile(self._filename) or not os.path.getsize(self._filename):
            raise ValueError("File is empty." if os.path.isfile(self._filename) else "No such file.")

        try:
            for row_index, row in self._produce_rows(columns, section):
                yield row
        finally:
            self._close_file()


    def _import_table(self, total_count):
        """
        Imports current file section to database,
        returns number of rows inserted, or False/None on failure/cancel.
        """
        result, insert_count = True, 0
        section, columns, insert_sql = (self._state[k] for k in ("section", "columns", "insert_sql"))
        logger.info("Running import from %s%s to table %s.",
                    self._filename, " sheet %r" % section if self._state["has_sections"] else "",
                    grammar.quote(self._state["table"], force=True))

        check_insertable = self._make_insert_checker(total_count)
        report_feedback = self._make_insert_reporter()
        for index, row in enumerate(self.iter_rows(columns, section)):
            do_insert = check_insertable(index)
            try:
                if do_insert:
                    self._state["cursor"].execute(insert_sql, row)
                    insert_count += 1
            except Exception as e:
                result = self._process_insert_error(e, row, index, insert_count)
            if result:
                result = report_feedback(index, insert_count, do_insert)
            if not result or do_insert is None:
                break # for index, row
        result = self._finalize_import_item(result, insert_count)
        return insert_count if result else result


    def _make_insert_checker(self, total_insert_count):
        """
        Returns function(row_index) to check whether row should be inserted.

        Returned function returns None if item import should stop, or True/False to insert.
        """
        table, section, has_names = (self._state[k] for k in ("table", "section", "has_names"))
        limit, maxcount, has_header = (self._flags[k] for k in ("limit", "maxcount", "has_header"))
        indexrange = ()

        if limit:
            amount, fromrow = limit if len(limit) == 2 else (limit[0], 0)
            amount, fromrow = (sys.maxsize if amount < 0 else amount), max(0, fromrow)
            indexrange = fromrow, fromrow + amount
        if maxcount and maxcount > 0:
            indexrange = indexrange or (0, sys.maxsize)
            untilrow = min(indexrange[1], indexrange[0] + maxcount - total_insert_count)
            indexrange = indexrange[0], untilrow
        elif maxcount == 0:
            indexrange = (-1, -1)

        def check_insertable(row_index):
            do_insert = True
            if has_header and not has_names and not row_index: do_insert = False
            elif indexrange:
                row_index = row_index - bool(has_header and not has_names)
                if row_index < indexrange[0]:    do_insert = False
                elif row_index >= indexrange[1]: do_insert = None
            if not row_index and do_insert is not None:
                if self._check_cancel(name=table, section=section, index=0, count=0):
                    do_insert = None
            return do_insert
        return check_insertable


    def _make_insert_reporter(self):
        """
        Returns function(row_index, insert_count_do_insert) to report progress.

        Returned function returns True if import should continue, False/None to stop/rollback.
        """
        table, section = self._state["table"], self._state["section"]

        def report_feedback(row_index, insert_count, do_insert):
            result = True
            insert_count_last, error_count = self._state["insert_count"], self._state["error_count"]
            error_count_last = self._state["error_count_last"]
            self._state.update(insert_count=insert_count, error_count_last=error_count)
            if not self._progress:
                return result

            do_report = False
            if not do_insert and row_index and not row_index % self.PROGRESS_STEP \
            or insert_count != insert_count_last and not insert_count % self.PROGRESS_STEP \
            or error_count != error_count_last and not error_count % self.PROGRESS_STEP:
                do_report = True

            if do_report:
                result = self._progress(name=table, section=section, index=row_index,
                                        count=insert_count, errorcount=error_count)
                if result is None:
                    logger.info("Cancelling and rolling back import on user request.")
                    self._state["cursor"].execute("ROLLBACK")
                elif not result:
                    logger.info("Cancelling import on user request.")
            return result
        return report_feedback


    def _prepare_import(self):
        """Populates database and source metadata, opens transaction cursor."""
        self._state["has_sections"] = self._format in ("xls", "xlsx")
        self._state["has_names"]    = self._format in ("json", "yaml")
        self._state["file_existed"] = os.path.isfile(self._db.filename)
        self._state["was_open"]     = self._db.is_open()

        self._db.open()
        self._state["cursor"] = self._db.connection.cursor()
        self._state["cursor"].execute("BEGIN TRANSACTION")


    def _prepare_table(self, item):
        """Populates item metadata, prepares SQL statements, creates new table if needed."""
        create_sql = None
        table, section, columns = item["name"], item["section"], item["columns"]

        if table not in self._db.schema.get("table", {}):
            cols = [{"name": x} for x in columns.values()]
            if item.get("pk") is not None:
                cols.insert(0, {"name": item["pk"], "type": "INTEGER",
                                "pk": {"autoincrement": True}, "notnull": {}})
            meta = {"name": table, "columns": cols, "__type__": grammar.SQL.CREATE_TABLE}
            create_sql, err = grammar.generate(meta)
            if err: raise Exception(err)
            logger.info("Creating new table %s.", grammar.quote(table, force=True))
            self._state["cursor"].execute(create_sql)
            self._state["new_tables"].append(table)
            self._db.populate_schema(category="table", name=table, parse=True)

        insert_sql = "INSERT INTO %s (%s) VALUES (%s)" % (grammar.quote(table),
            ", ".join(grammar.quote(x) for x in columns.values()),
            ", ".join("?" * len(columns))
        )
        self._state.update(table=table, section=section, create_sql=create_sql, insert_sql=insert_sql,
                           columns=columns, insert_count=0, error_count=0, error_count_last=0)
        self._db.lock("table", table, self._filename, label="import")


    def _process_import_error(self, exc):
        """Rolls back transaction, logs and reports error."""
        table, section, has_sections = (self._state[k] for k in ("table", "section", "has_sections"))
        logger.exception("Error running import from %s%s%s in %s.",
                         self._filename, (" sheet %r" % section) if section and has_sections else "",
                         (" to table %s " % grammar.quote(table, force=True) if table else ""),
                         self._db.filename)
        util.try_ignore(lambda: self._state["cursor"].execute("ROLLBACK"))
        if self._progress:
            report_args = {"error": util.format_exc(exc), "done": True}
            if table: report_args.update({"name": table, "section": section})
            self._progress(**report_args)


    def _process_insert_error(self, exc, row, row_index, insert_count):
        """
        Raises on row insert error if no progress callback, else returns callback response:
        True for continuing import with any further errors, False for stopping import,
        None for stopping import and rolling back all actions.
        """
        self._state["error_count"] += 1
        if not self._progress: raise

        logger.exception("Error executing '%s' with %s.", self._state["insert_sql"], row)
        if self._state["continue_on_error"]:
            return True

        result = self._progress(error=util.format_exc(exc), index=row_index,
                                count=insert_count, errorcount=self._state["error_count"],
                                name=self._state["table"], section=self._state["section"])
        if result:
            self._state["continue_on_error"] = True
        elif result is None:
            logger.info("Cancelling and rolling back import on user request.")
            self._state["cursor"].execute("ROLLBACK")
        else:
            logger.info("Cancelling import on user request.")
        return result


    def _finalize_import(self, result):
        """Commits or rolls back changes, cleans up resources upon completion."""
        action = "ROLLBACK" if result is None else "COMMIT"
        util.try_ignore(lambda: self._state["cursor"].execute(action))
        self._db.unlock("table", self._state["table"], self._filename)
        if self._db.is_open():
            if self._state["cursor"]:
                util.try_ignore(self._state["cursor"].close)
            if self._state["table"]:
                self._db.unlock("table", self._state["table"], self._filename)
            if not self._state["was_open"]:
                self._db.close()

        if not result and not self._state["file_existed"]:
            try:
                if not os.path.getsize(self._db.filename):
                    os.unlink(self._db.filename)
            except Exception: pass
        if result is None:
            if self._state["file_existed"] and "table" in self._db.schema:
                # Discard traces of created tables if import cancelled
                for table in self._state["new_tables"]:
                    self._db.schema["table"].pop(table, None)
        logger.info("Finished importing from %s to %s.", self._filename, self._db)


    def _finalize_import_item(self, result, insert_count):
        """Logs import results, unlocks table, checks for cancel, returns result."""
        if result:
            sqls = list(filter(bool, [self._state["create_sql"], self._state["insert_sql"]]))
            self._db.log_query("IMPORT", sqls, [self._filename, util.plural("row", insert_count)])
        table, section, has_sections = (self._state[k] for k in ("table", "section", "has_sections"))
        self._db.unlock("table", table, self._filename)
        logger.info("Finished importing %s from %s%s to table %s%s.",
                    util.plural("row", insert_count),
                    self._filename, (" sheet %r" % section) if has_sections else "",
                    grammar.quote(table, force=True),
                    ", all rolled back" if result is None and insert_count else "")
        if result and self._progress:
            result = self._progress(name=table, section=section, count=insert_count, done=True,
                                    errorcount=self._state["error_count"])
        return result


    def _get_row_count(self, rows_counted, rows_skipped, section=None):
        """Returns total row count for file or worksheet, or -1 if file too large to count."""
        total = rows_counted
        if rows_counted == 0: pass
        elif os.path.getsize(self._filename) > conf.MaxImportFilesizeForCount:
            total = -1
        elif "xls" == self._format:
            sheet = self._file.sheet_by_name(section)
            total = sheet.nrows - rows_skipped
        elif "xlsx" == self._format:
            sheet = self._file[section]
            total = sum(1 for _ in sheet.iter_rows()) - rows_skipped
        return total


    def _get_sections(self):
        """Returns worksheet names; or descriptive title if not multiple sheet format."""
        if "csv" == self._format:
            return ["<CSV data>"]
        elif "json" == self._format:
            return ["<JSON data>"]
        elif "xls" == self._format:
            return [sheet.name for sheet in self._file.sheets()]
        elif "xlsx" == self._format:
            return [sheet.title for sheet in self._file.worksheets]
        elif "yaml" == self._format:
            return ["<YAML data>"]


    def _open_file(self):
        """Opens data file for reading, if not already open."""
        if self._file is not None: return
        if "csv" == self._format:
            self._file = csv_reader(self._filename)
            self._file.open()
        elif "json" == self._format:
            self._file = io.open(self._filename, encoding="utf-8")
        elif "xls" == self._format:
            self._file = xlrd.open_workbook(self._filename, on_demand=True)
        elif "xlsx" == self._format:
            warnings.filterwarnings("ignore", module="openpyxl") # can throw warnings on styles etc
            self._file = openpyxl.load_workbook(self._filename, data_only=True, read_only=True)
        elif "yaml" == self._format:
            self._file = open(self._filename, "rbU" if six.PY2 else "rb")


    def _close_file(self):
        """Closes currently open data file, if any."""
        if self._file is None: return
        if "xls" == self._format:
            util.try_ignore(lambda: self._file.release_resources())
        else:
            util.try_ignore(lambda: self._file.close())
        self._file = None


    def _produce_rows(self, columns=None, section=None, dicts=False):
        """
        Yields rows from data file, as (row index, row data).

        @param   columns  list of column keys to return if not all,
                          where key is column index if spreadsheet else column name
        @param   section  name of spreadsheet to use if multiple sheet format
        @param   dicts    return data as OrderedDict if JSON/YAML format (ignores columns)
        @return           (row true index starting from 0, [value1, ..] or {key1: value1, ..})
        """
        if self._format in ("csv", "xls", "xlsx"):
            index, started, seek = 0, False, self._flags["seek"]
            for index, row in enumerate(self._produce_raw_data(section)):
                if not started and self._check_cancel(not index % self.PROGRESS_STEP):
                    return
                if not started and seek and all(x in ("", None) for x in row): # Seek to content
                    continue # for row
                if columns: row = [row[i] if i < len(row) else None for i in columns]
                else:
                    while row and row[-1] in (None, ""): row.pop(-1)
                yield index, row
                started = True
        elif self._format in ("json", "yaml"):
            caster = yaml.safe_dump if "yaml" == self._format else \
                     functools.partial(json.dumps, indent=2)
            # Flatten nested lists and dicts back to JSON/YAML strings
            cast = lambda x: caster(x) if isinstance(x, (dict, list)) else x
            for index, data in enumerate(self._produce_raw_data()):
                if dicts:     row = collections.OrderedDict((k, cast(v)) for k, v in data.items())
                elif columns: row = [cast(data.get(x)) for x in columns]
                else:         row = [cast(x) for x in data.values()]
                yield index, row


    def _produce_raw_data(self, section=None):
        """
        Yields unmodified data from file, as lists of column values if spreadsheet else as dicts.

        @param   section  name of spreadsheet to use if multiple sheet format
        """
        self._open_file()
        if "csv" == self._format:
            for data in self._file:
                yield data
        elif "json" == self._format:
            for data in self._iter_json_dicts(self._file):
                yield data
        elif "xls" == self._format:
            for data in self._file.sheet_by_name(section).get_rows():
                yield [x.value for x in data]
        elif "xlsx" == self._format:
            for data in self._file[section].iter_rows(values_only=True):
                yield list(data)
        elif "yaml" == self._format:
            for data in self._iter_yaml_dicts(self._file):
                yield data



    @classmethod
    def _iter_json_dicts(cls, file):
        """Yields top-level dictionaries from opened JSON file handle, as OrderedDict."""
        buffer, started = "", False
        decoder = json.JSONDecoder(object_pairs_hook=collections.OrderedDict)
        for chunk in iter(functools.partial(file.read, 2**16), ""):
            if not chunk:
                break # for chunk
            buffer += chunk
            if not started: # Strip line comments and list start from beginning
                buffer = re.sub("^//[^\n]*$", "", buffer.lstrip(), flags=re.M).lstrip()
                if buffer.startswith("["): buffer, started = buffer[1:].lstrip(), True
                elif buffer.startswith("{"): started = True # Support a single root dict
            while started and buffer:
                # Strip whitespace and interleaving commas from between dicts
                buffer = re.sub(r"^\s*[,]?\s*", "", buffer)
                try:
                    data, index = decoder.raw_decode(buffer)
                    if isinstance(data, collections.OrderedDict):
                        # Ensure original order in top-level keys, use plain dicts for nested values
                        data, ordered_data = json.loads(buffer[:index]), data
                        yield collections.OrderedDict((k, data[k]) for k in ordered_data)
                    buffer = buffer[index:]
                except ValueError: # Not enough data to decode, read more
                    break # while started and buffer
        if buffer.startswith("]"): buffer = buffer[1:]
        if buffer:
            logger.warning("Invalid trailing content in %r: %s bytes not parseable (%r)",
                           file.name, len(buffer), util.ellipsize(buffer, 100))


    @classmethod
    def _iter_yaml_dicts(cls, file):
        """Yields top-level dictionaries from opened YAML file handle, as OrderedDict."""
        parser = yaml.parse(file, yaml.SafeLoader)
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
                    serialized = yaml.emit(START_STACK + item_stack)
                    data = ordered_data = yaml.safe_load(serialized)
                    if sys.version_info < (3, 7): # dicts became officially insert-order in Py3.7
                        ordered_data = yaml.load(serialized, OrderedYamlLoader)
                    # Ensure original order in top-level keys, use plain dicts for nested values
                    yield collections.OrderedDict((k, data[k]) for k in ordered_data)
                    del item_stack[:]



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
            elif chardet:
                try:
                    if hasattr(chardet, "detect_all"): # v4+
                        encoding = chardet.detect_all(preview)[0]["encoding"]
                    else:
                        encoding = chardet.detect(preview)["encoding"]
                except Exception: pass
            if "ascii" == encoding: encoding = "utf-8" # Failsafe: ASCII as UTF-8 is valid anyway

            if "utf-16" in (encoding or "").lower() and len(preview) / 2: preview += b"\x00"
            try: dialect = csv.Sniffer().sniff(preview.decode(encoding or "utf-8"), ",;\t")
            except csv.Error: # Format not deducable
                dialect = csv.excel
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
            self._file = codecs.open(self.filename, encoding=self.encoding)
            csvfile = self._reencoder() if six.PY2 else self._reliner()
            self._reader = csv.reader(csvfile, self.dialect)


    def _reencoder(self):
        """Yields lines from file re-encoded as UTF-8; Py2 workaround."""
        if "utf-16" in (self.encoding or "").lower(): # Strip byte order mark if any
            line = next(self._file, "")
            if line.startswith((u"\uFEFF", u"\uFFFE")): line = line[1:]
            yield line.encode("utf-8")
        for line in self._file: yield line.encode("utf-8")


    def _reliner(self):
        """Yields lines from file, ensuring no mixed linefeeds; Py3 workaround."""
        line = next(self._file, "")
        while line:
            yield line
            line, prevline = next(self._file, ""), line
            if prevline[-1:] == "\r" and prevline[-2:] != "\r\n" and line == "\r\n":
                line = next(self._file, "") # Skip invalid lines mixing Windows and Unix linefeeds


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
        unit_width_default = get_text_extent(self._fonts[None], "0")[0] or 1
        self._unit_widths = collections.defaultdict(lambda: unit_width_default)
        self._unit_widths["bold"] = get_text_extent(self._fonts["bold"], "0")[0] or 1

        if sheetname: # Create default sheet
            self.add_sheet(sheetname)


    def add_sheet(self, name=None):
        """Adds a new worksheet. Name will be changed if invalid/existing."""
        if self._sheet and hasattr(self._sheet, "_opt_close"):
            self._sheet._opt_close() # Close file handle to not hit ulimit
        safename = None
        if name is not None:
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
        self._sheetnames[sheet] = name if name is not None else sheet.name
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
            widths = [sum(get_text_extent(self._fonts[fmt_name], x)[0] for x in line)
                      for line in strval.splitlines()]
            pixels = max(widths) if widths else 0
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


def convert_lf(s, newline=os.linesep):
    r"""Returns string with \r \n \r\n linefeeds replaced with given."""
    return re.sub("(\r(?!\n))|((?<!\r)\n)|(\r\n)", newline, s)


@util.memoize
def get_text_extent(font, text):
    """Returns (width, height) of text in specified font."""
    if hasattr(font, "getsize"): return font.getsize(text)     # <  PIL 9.2.0
    if hasattr(font, "getbbox"): return font.getbbox(text)[2:] # >= PIL 8.0.0
    return None


if yaml:
    def node_to_ordered_dict(loader, node):
        loader.flatten_mapping(node)
        return collections.OrderedDict(loader.construct_pairs(node))

    class OrderedYamlLoader(yaml.SafeLoader): pass

    DICT_TAG = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG
    OrderedYamlLoader.add_constructor(DICT_TAG, node_to_ordered_dict)
