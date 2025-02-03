#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Shared functionality for tests.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     16.09.2024
@modified    28.12.2024
------------------------------------------------------------------------------
"""
import contextlib
import csv
import itertools
import collections
import io
import json
import logging
import os
import shutil
import sqlite3
import unittest
import tempfile
import warnings

try: import openpyxl
except ImportError: openpyxl = None
try: import xlsxwriter
except ImportError: xlsxwriter = None
try: import xlrd
except ImportError: xlrd = None
try: import xlwt
except ImportError: xlwt = None
try: import yaml
except ImportError: yaml = None
try: text_type = basestring       # Py2
except Exception: text_type = str # Py3


logger = logging.getLogger()


EXPORT_FORMATS = ["csv", "html", "json", "sql", "txt", xlsxwriter and "xlsx", yaml and "yaml"]
EXPORT_FORMATS = list(filter(bool, EXPORT_FORMATS))

OUTPUT_FORMATS = ["db"] + EXPORT_FORMATS

PRINTABLE_FORMATS = [x for x in EXPORT_FORMATS if x not in ("html", "xls", "xlsx")]

IMPORT_FORMATS = ["csv", "json", xlrd and xlwt and "xls", openpyxl and xlsxwriter and "xlsx", yaml and "yaml"]
IMPORT_FORMATS = list(filter(bool, IMPORT_FORMATS))

IMPORT_EXTS = IMPORT_FORMATS + (["yml"] if yaml else [])

MULTISHEET_FORMATS  = [x for x in sorted(set(IMPORT_FORMATS + EXPORT_FORMATS)) if x in ("xls", "xlsx")]
SPREADSHEET_FORMATS = ["csv"] + MULTISHEET_FORMATS

STATS_FORMATS = ["html", "sql", "txt"]


## Values for populating test data rows
TEXT_VALUES = ["a this that B", "a these two B"]

## Number of rows auto-populated in test data
ROWCOUNT = 10

COLUMNS = collections.OrderedDict([
    ("empty",   ["id"]),
    ("parent",  ["id", "value"]),
    ("related", ["id", "value", "fk"]),
    ("myview",  ["id", "value"]),
])
COLUMNS["myview"] = COLUMNS["parent"]

## Schema CREATE SQLs, as {category: {name: CREATE SQL}}
SCHEMA = {
    "table": collections.OrderedDict([
        ("empty",           "CREATE TABLE empty (id)"),
        ("parent",          "CREATE TABLE parent (id, value)"),
        ("related",         "CREATE TABLE related (id, value, fk REFERENCES parent (id))"),
    ]),
    "view": collections.OrderedDict([
        ("myview",          "CREATE VIEW myview AS SELECT * FROM parent"),
    ]),
    "index": collections.OrderedDict([
        ("parent_idx",      "CREATE INDEX parent_idx ON parent (id)"),
    ]),
    "trigger": collections.OrderedDict([
        ("on_insert_empty", "CREATE TRIGGER on_insert_empty AFTER INSERT ON empty\n"
                            "BEGIN\nSELECT 'on' FROM empty;\nEND;"),
    ]),
}

# Data as {name: [{row}]}
DATA = collections.OrderedDict([
    ("empty",   []),
    ("parent",  [{"id": i, "value": TEXT_VALUES[i % 2]} for i in range(ROWCOUNT)]),
    ("related", [{"id": i, "value": TEXT_VALUES[i % 2], "fk": ROWCOUNT - i}
                 for i in range(ROWCOUNT)]),
])
DATA["myview"] = DATA["parent"]



class FileTest(unittest.TestCase):
    """Provides convenience for creating temporary files."""

    def __init__(self, *args, **kwargs):
        super(FileTest, self).__init__(*args, **kwargs)
        self.maxDiff = None  # Full diff on assert failure
        try: unittest.util._MAX_LENGTH = 100000
        except Exception: pass
        self._paths = []  # [path to temporary input file, ]


    def tearDown(self):
        """Deletes temoorary files."""
        for path in self._paths:
            try: (shutil.rmtree if os.path.isdir(path) else os.remove)(path)
            except Exception: pass
        super(FileTest, self).tearDown()


    def mkdtemp(self):
        """Returns path of a new temporary directory."""
        path = tempfile.mkdtemp()
        self._paths.append(path)
        return path


    def mktemp(self, suffix=None, content=None):
        """Returns path of a new temporary file, optionally retained on disk with given content."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=content is None) as f:
            if content is not None: f.write(content.encode("utf-8"))
            self._paths.append(f.name)
            return f.name



def intify(v):
    """Returns value as integer if numeric string."""
    return int(v) if isinstance(v, text_type) and v.isdigit() else v


def list_database(connection, category="table"):
    """Returns list of table names from sqlite3 Connection."""
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = ?", [category]).fetchall()
    return sorted(x["name"] for x in rows)


def populate_database(filename, schema, columns, data):
    """
    Populates an SQLite database with schema and data.

    @param   schema   {category: {name: "CREATE .."}}
    @param   columns  {name: [col1, ..]}
    @param   data     {name: [{col1: ..}]}
    """
    logger.debug("Populating test database %r with %s tables and %s rows.",
                 filename, len(data), sum(map(len, data.values())))
    with contextlib.closing(sqlite3.connect(filename, isolation_level=None)) as sqldb:
        sqldb.executescript(";\n\n".join(s for d in schema.values() for s in d.values()))
        for item_name, rows in data.items():
            if not rows or item_name not in schema["table"]: continue # for
            rowstr = "(%s)" % ", ".join("?" * len(columns[item_name]))
            paramstr = ", ".join([rowstr] * len(rows))
            params = [r[c] for r in rows for c in columns[item_name]]
            sqldb.execute("INSERT INTO %s VALUES %s" % (item_name, paramstr), params)


def populate_datafile(filename, format, data, schema, combined=False, header=True):
    """Populates file with data as given format."""
    logger.debug("Populating %s data in %s with %s tables and %s rows.",
                 format.upper(), filename, len(schema), sum(map(len, data.values())))
    if "csv" == format:
        with open(filename, "w") as f:
            prefix = [""] if combined else []
            writer = csv.writer(f, csv.excel, delimiter=";", lineterminator="\n")
            for item_name in schema:
                if combined: writer.writerow([item_name])
                if header: writer.writerow(prefix + schema[item_name])
                for row in data[item_name]:
                    writer.writerow(prefix + [str(row[k]) for k in schema[item_name]])
    elif "json" == format:
        obj = data if combined else next(data[k] for k in schema)
        with open(filename, "w") as f:
            json.dump(obj, f)
    elif "xls" == format:
        wb = xlwt.Workbook()
        for item_name in schema:
            sheet = wb.add_sheet(item_name)
            for j, col_name in enumerate(schema[item_name]) if header else ():
                sheet.write(0, j, col_name)
            for i, row in enumerate(data[item_name]):
                for j, col_name in enumerate(schema[item_name]):
                    sheet.write(i + int(bool(header)), j, row[col_name])
        wb.save(filename)
    if "xlsx" == format:
        wb = xlsxwriter.Workbook(filename)
        for item_name in schema:
            sheet = wb.add_worksheet(item_name)
            for j, col_name in enumerate(schema[item_name]) if header else ():
                sheet.write(0, j, col_name)
            for i, row in enumerate(data[item_name]):
                for j, col_name in enumerate(schema[item_name]):
                    sheet.write(i + int(bool(header)), j, row[col_name])
        wb.close()
    elif "yaml" == format:
        obj = data if combined else next(data[k] for k in schema)
        with open(filename, "w") as f:
            yaml.safe_dump(obj, f)


def validate_data(testcase, fmt, filename=None, content=None, names=None, query=None, columns=None,
                  limit=None, maxcount=None, allow_empty=True, reverse=False, combined=False,
                  data=True, data_expected=None):
    """
    Verifies data in output file or given content.

    @param   testcase       unittest.TestCase instance for asserts
    @param   fmt            output format like "json"
    @param   filename       name of outfile if any
    @param   content        output content string if not using filename
    @param   names          one or more entity names to expect if not all test data
    @param   query          SQL query text if query export
    @param   columns        list of columns to expect in output for single entity, if not all
    @param   limit          per-entity limits, as LIMIT or (LIMIT, ) or (LIMIT, OFFSET)
    @param   maxcount       total number of rows to expect over all entities
    @param   allow_empty    whether to expect entities with no rows
    @param   reverse        whether to expect rows in reverse order
    @param   combined       whether is combined output
    @param   data_expected  pre-provided data to expect, as {name: [{row}]}
    """
    if filename:
        testcase.assertTrue(os.path.isfile(filename), "Expected output file to be created.")

    if not names: names = list(SCHEMA["table"]) + list(SCHEMA["view"])
    if columns: columns = [x["name"] if isinstance(x, dict) else x for x in columns]
    limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else (limit, )
    if filename and "xlsx" != fmt:
        with io.open(filename, encoding="utf-8") as f: content = f.read()

    if data_expected is not None: expected = data_expected
    else:
        expected = collections.OrderedDict()
        total_counter = itertools.count()
        for name in (n for n in names if n in DATA):
            rows = DATA[name] 
            if not data: rows = []
            if reverse: rows = rows[::-1]
            if limit:
                from_, to_= (limit[1], limit[1] + limit[0]) if len(limit) > 1 else (0, limit[0])
                rows = rows[from_:to_]
            if maxcount is not None: rows = [r for r in rows if next(total_counter) < maxcount]
            if columns: rows = [{k: r[k] for k in columns} for r in rows]
            if rows or allow_empty:
                expected[name] = rows

    if expected or allow_empty:
        if filename:
            testcase.assertTrue(os.path.getsize(filename), "Expected output file to have content.")
        else:
            testcase.assertTrue(content, "Expected output file to have content.")

    if "csv" == fmt:
        validate_data_csv(testcase, content, expected, query, columns, combined)
    elif "sql" == fmt:
        validate_data_sql(testcase, content, expected, columns=columns)
    elif "xlsx" == fmt:
        validate_data_xlsx(testcase, filename, expected, query, columns)
    elif fmt in ("html", "txt") or not combined:
        if query and fmt in ("html", "txt", "yaml"):
            testcase.assertIn(query, content, "Expected query in %s output." % fmt.upper())
        for name, rows in expected.items():
            if fmt in ("html", "txt") and not query:
                testcase.assertIn(name, content, "Expected %r in %s output." % (name, fmt.upper()))
            for v in (v for r in rows for v in r.values()):
                testcase.assertIn(str(v), content, "Unexpected data for %r in output." % name)
    elif "json" == fmt:
        try: received = json.loads(content)
        except Exception as e: testcase.fail("Expected valid JSON output (%r)." % e)
        testcase.assertEqual(received, expected, "Unexpected data in JSON output.")
    elif "yaml" == fmt:
        if query:
            testcase.assertIn(query, content, "Expected query in YAML output.")
        try: received = yaml.safe_load(content) or {}
        except Exception as e: testcase.fail("Expected valid YAML output (%r)." % e)
        testcase.assertEqual(received, expected, "Unexpected data in YAML output.")


def validate_data_csv(testcase, content, data_expected, query=None, columns=None, combined=False):
    """Asserts CSV output containing valid expected data."""
    try: data_received = list(csv.reader(io.StringIO(content), delimiter=";", lineterminator="\n"))
    except Exception as e: testcase.fail("Expected valid CSV output (%r)." % e)

    row_index, indentcols = 0, []
    if combined and content:
        testcase.assertEqual(data_received[row_index], [],
                             "Expected leading blank row in combined CSV output.")
        row_index += 1
        indentcols = [""]
    names_processed = []
    for name, rows_expected in data_expected.items():
        if combined:
            testcase.assertEqual(data_received[row_index], [name],
                                 "Expected table name in combined CSV output.")
            row_index += 1
        if query:
            testcase.assertEqual(data_received[row_index], [query],
                                 "Expected query in CSV output.")
            row_index += 1
        item_columns = columns or COLUMNS[name]
        testcase.assertEqual(data_received[row_index], indentcols + item_columns,
                             "Expected columns in CSV output for %r." % name)
        row_index += 1
        for row in rows_expected:
            received = [intify(x) for x in data_received[row_index]]
            expected = indentcols + [row[k] for k in item_columns]
            testcase.assertEqual(received, expected,
                                 "Unexpected row values in CSV output for %r." % name)
            row_index += 1
        names_processed.append(name)
        if combined and len(names_processed) < len(data_expected):
            testcase.assertEqual(data_received[row_index], [],
                                 "Expected trailing blank row in combined CSV output.")
            row_index += 1


def validate_data_xlsx(testcase, filename, data_expected, query=None, columns=None):
    """Asserts XLSX output containing valid expected data."""
    warnings.filterwarnings("ignore", module="openpyxl") # can throw warnings on styles etc
    try: wb = openpyxl.load_workbook(filename, data_only=True, read_only=True)
    except Exception as e: testcase.fail("Expected valid XLSX output (%r)." % e)
    for name, rows_expected in data_expected.items():
        testcase.assertIn(name, wb, "Expected %r in XLSX output." % name)
        received = []
        for row in wb[name].iter_rows(values_only=True):
            row = list(row)
            while row[-1] is None: row.pop(-1)
            received.append(row)
        item_columns = columns or COLUMNS[name]
        expected = [item_columns] + [[r[k] for k in item_columns] for r in rows_expected]
        if query: expected = [[query]] + expected
        testcase.assertEqual(received, expected,
                             "Unexpected data for %r in XLSX output." % name)


def validate_data_sql(testcase, content, data_expected, schema_expected=None, columns=None):
    """Asserts SQL output containing valid expected data."""
    sqldb = None
    with contextlib.closing(sqlite3.connect(":memory:")) as sqldb:
        try: sqldb.executescript(content)
        except Exception as e: testcase.fail("Expected valid SQL in output (%r)." % e)
        sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))

        received, expected = {}, {}
        for category in ["table", "view", "index", "trigger"]:
            names = list_database(sqldb, category)
            if names: received[category] = set(x.lower() for x in names)
        if schema_expected is not None:
            expected = {k: {v.lower() for v in vv} for k, vv in schema_expected.items()}
        elif data_expected:
            expected = {"table": {k.lower() for k in data_expected}}
        testcase.assertEqual(received, expected, "Unexpected schema in SQL output.")

        for name, rows_expected in data_expected.items():
            rows_received = sqldb.execute("SELECT * FROM %r" % name).fetchall()
            if columns:
                rows_received = [{k: r[k] for k in columns} for r in rows_received]
            testcase.assertEqual(rows_received, rows_expected,
                                 "Unexpected data in SQL output for %r." % name)




logging.getLogger("sqlitely").setLevel(logging.FATAL)
