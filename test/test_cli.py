#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests command-line interface.

Supports testing compiled binary via environment variable SQLITELY_BINARY as path to exe.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     24.06.2024
@modified    28.12.2024
------------------------------------------------------------------------------
"""
import contextlib
import glob
import io
import json
import logging
import os
import re
import sqlite3
import string
import subprocess
import sys
import unittest

try: import xlsxwriter
except ImportError: xlsxwriter = None
try: import yaml
except ImportError: yaml = None


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test.common import COLUMNS, SCHEMA, DATA, IMPORT_FORMATS, OUTPUT_FORMATS
from test.common import PRINTABLE_FORMATS, MULTISHEET_FORMATS, SPREADSHEET_FORMATS, STATS_FORMATS
from test.common import FileTest, intify, populate_database, populate_datafile, text_type


logger = logging.getLogger()


class TestCLI(FileTest):
    """Tests the command-line interface."""

    ## Path to compiled binary to use instead of executing Python source
    BINARY = None


    def __init__(self, *args, **kwargs):
        super(TestCLI, self).__init__(*args, **kwargs)
        self._proc   = None  # subprocess.Popen instance
        self._dbname = None  # Path to source database


    def setUp(self):
        """Populates temporary file paths."""
        super(TestCLI, self).setUp()
        self._dbname = self.mktemp(".db")
        self.BINARY = os.getenv("SQLITELY_BINARY")


    def tearDown(self):
        """Deletes temoorary files and folders, closes subprocess if any."""
        try: self._proc and self._proc.terminate()
        except Exception: pass
        super(TestCLI, self).tearDown()


    def run_cmd(self, command, *args):
        """Executes SQLitely command, returns (exit code, stdout, stderr)."""
        TIMEOUT = dict(timeout=60) if sys.version_info > (3, 2) else {}
        workdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
        args = [str(x) for x in args]
        cmd = ["python", "-m", "sqlitely", command] + list(args)

        binary_outfile = None
        if self.BINARY: # Testing the command-line interface of a compiled binary
            cmd = [self.BINARY, command] + list(args) + ["--binary-wait", "1"]
            if "--path" not in args: # Patch in flags to ensure output into single file
                if command in ("export", "search") and "--combine" not in args:
                    cmd += ["--combine"]
                if "import" != command and "-o" not in args:
                    binary_outfile = self.mktemp()
                    cmd += ["-o", binary_outfile]
                    if "execute" == command and "--allow-empty" not in args:
                        cmd += ["--allow-empty"]

        logger.debug("Executing command %r.", " ".join(repr(x) if " " in x else x for x in cmd))
        self._proc = subprocess.Popen(cmd, universal_newlines=True, cwd=workdir,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = (x.strip() for x in self._proc.communicate(**TIMEOUT))
        if binary_outfile and os.path.isfile(binary_outfile):
            with open(binary_outfile) as f: out = f.read()

        logger.debug("Command result: %r.", self._proc.poll())
        if out: logger.debug("Command stdout:\n%s", out)
        if err: logger.debug("Command stderr:\n%s", err)
        return self._proc.returncode, out, err


    def test_execute(self):
        """Tests 'execute' command in command-line interface."""
        logger.info("Testing 'execute' command.")

        self.verify_execute_blank()
        self.verify_execute_crud()
        self.verify_execute_file_args()
        self.verify_execute_formats()
        self.verify_execute_flags()


    def test_export(self):
        """Tests 'export' command in command-line interface."""
        logger.info("Testing 'export' command.")
        populate_database(self._dbname, SCHEMA, COLUMNS, DATA)

        self.verify_export_formats()
        self.verify_export_selections()
        self.verify_export_limits()
        self.verify_export_flags()


    def test_import(self):
        """Tests 'import' command in command-line interface."""
        logger.info("Testing 'import' command.")

        self.verify_import_formats()
        self.verify_import_limits()
        self.verify_import_noempty()
        self.verify_import_addpk()
        self.verify_import_rowheader()
        self.verify_import_selections()
        self.verify_import_columns()
        self.verify_import_flags()


    def test_parse(self):
        """Tests 'parse' command in command-line interface."""
        logger.info("Testing 'parse' command.")
        populate_database(self._dbname, SCHEMA, COLUMNS, DATA)

        self.verify_parse_full()
        self.verify_parse_search()
        self.verify_parse_limits()


    def test_pragma(self):
        """Tests 'pragma' command in command-line interface."""
        logger.info("Testing 'pragma' command.")
        populate_database(self._dbname, SCHEMA, COLUMNS, DATA)

        self.verify_pragma_full()
        self.verify_pragma_search()


    def test_search(self):
        """Tests 'search' command in command-line interface."""
        logger.info("Testing 'search' command.")
        populate_database(self._dbname, SCHEMA, COLUMNS, DATA)

        self.verify_search_formats()
        self.verify_search_limits()
        self.verify_search_filters()


    def test_stats(self):
        """Tests 'stats' command in command-line interface."""
        logger.info("Testing 'stats' command.")
        populate_database(self._dbname, SCHEMA, COLUMNS, DATA)

        self.verify_stats_formats()
        self.verify_stats_flags()


    def verify_execute_blank(self):
        """Tests 'execute': queries on missing or blank database."""
        logger.info("Testing failure of query on nonexistent file.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT 1")
        self.assertTrue(res, "Unexpected success from query on nonexistent file.") \
            if not self.BINARY else None # Result from binary always success, uses its own console

        logger.info("Testing success of query on nonexistent file.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT 1", "--create", "-f", "json")
        self.assertFalse(res, "Unexpected failure from query on nonexistent file.")
        self.assertEqual(json.loads(out), [{"1": 1}], "Unexpected result from query.")
        self.assertTrue(os.path.isfile(self._dbname), "Expected database file to exist.")

        logger.info("Testing query on blank file.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT 1", "-f", "json")
        self.assertFalse(res, "Unexpected failure from query on blank file.")
        self.assertEqual(json.loads(out), [{"1": 1}], "Unexpected result from query.")

        logger.info("Testing PRAGMA query.")
        res, out, err = self.run_cmd("execute", self._dbname, "PRAGMA data_version", "-f", "json")
        self.assertFalse(res, "Unexpected failure from PRAGMA query.")
        self.assertEqual(json.loads(out), [{"data_version": 1}], "Unexpected result from query.")


    def verify_execute_crud(self):
        """Tests 'execute': table read-write operations."""
        logger.info("Testing CREATE TABLE query.") # Table foo, 0 rows
        res, out, err = self.run_cmd("execute", self._dbname, "CREATE TABLE foo (bar)")
        self.assertFalse(res, "Unexpected failure from CREATE TABLE query.")
        self.assertFalse(out, "Unexpected output from CREATE TABLE query.")
        self.assertTrue(os.path.getsize(self._dbname), "Expected database file to not be empty.")

        logger.info("Testing INSERT query.") # Table foo, rows 1 2
        res, out, err = self.run_cmd("execute", self._dbname, "INSERT INTO foo VALUES (1), (2)")
        self.assertFalse(res, "Unexpected failure from INSERT query.")
        self.assertFalse(out, "Unexpected output from INSERT query.")

        logger.info("Testing SELECT query.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-f", "json")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(json.loads(out), [{"bar": 1}, {"bar": 2}],
                        "Unexpected output from SELECT query.")

        logger.info("Testing UPDATE query.") # Table foo, rows 1 3
        res, out, err = self.run_cmd("execute", self._dbname, "UPDATE foo SET bar = 3 WHERE bar = 2")
        self.assertFalse(res, "Unexpected failure from UPDATE query.")
        self.assertFalse(out, "Unexpected output from UPDATE query.")
        logger.info("Verifying result of UPDATE query.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-f", "json")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(json.loads(out), [{"bar": 1}, {"bar": 3}],
                        "Unexpected output from SELECT query.")

        logger.info("Testing DELETE query.") # Table foo, 0 rows
        res, out, err = self.run_cmd("execute", self._dbname, "DELETE FROM foo")
        self.assertFalse(res, "Unexpected failure from DELETE query.")
        self.assertFalse(out, "Unexpected output from DELETE query.")
        logger.info("Verifying result of DELETE query.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-f", "json")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(json.loads(out), [], "Unexpected output from SELECT query.")


    def verify_execute_file_args(self):
        """Tests 'execute': query from file, and query parameters."""
        logger.info("Testing query from SQL file.") # Table foo, rows 1 2
        sqlfile = self.mktemp(".sql", "INSERT INTO foo VALUES (1), (2)")
        res, out, err = self.run_cmd("execute", self._dbname, sqlfile)
        self.assertFalse(res, "Unexpected failure from INSERT query.")
        self.assertFalse(out, "Unexpected output from INSERT query.")
        logger.info("Verifying result of INSERT query.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-f", "json")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(json.loads(out), [{"bar": 1}, {"bar": 2}],
                        "Unexpected output from SELECT query.")

        logger.info("Testing multiple query from SQL file.") # Table foo, rows 3 4 5
        sqlfile = self.mktemp(".sql", "INSERT INTO foo VALUES (3), (4), (5); "
                                      "DELETE FROM foo WHERE bar IN (1, 2)")
        res, out, err = self.run_cmd("execute", self._dbname, sqlfile)
        self.assertFalse(res, "Unexpected failure from multiple query.")
        self.assertFalse(out, "Unexpected output from multiple query.")
        logger.info("Verifying result of multiple query.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-f", "json")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(json.loads(out), [{"bar": 3}, {"bar": 4}, {"bar": 5}],
                        "Unexpected output from SELECT query.")

        logger.info("Testing query positional parameters.")
        res, out, err = self.run_cmd("execute", self._dbname,
            "SELECT * FROM foo WHERE bar = ? OR bar = ?", "--param", 3, 4, "-f", "json")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(json.loads(out), [{"bar": 3}, {"bar": 4}],
                        "Unexpected output from SELECT query.")

        logger.info("Testing query keyword parameters.")
        res, out, err = self.run_cmd("execute", self._dbname,
            "SELECT * FROM foo WHERE bar = :a OR bar = :b", "--param", "a=3", "b=5", "-f", "json")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(json.loads(out), [{"bar": 3}, {"bar": 5}],
                        "Unexpected output from SELECT query.")


    def verify_execute_formats(self):
        """Tests 'execute': output to console and file in different formats."""
        logger.info("Testing query export in all formats.")
        for fmt in PRINTABLE_FORMATS:
            logger.info("Testing query export as %s.", fmt.upper())
            res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-f", fmt)
            self.assertFalse(res, "Unexpected failure from SELECT query.")
            self.assertTrue(out, "Unexpected lack of output from SELECT query.")

        for fmt in OUTPUT_FORMATS:
            logger.info("Testing query export to file as %s.", fmt.upper())
            outfile = self.mktemp("." + fmt)
            res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-o", outfile)
            self.assertFalse(res, "Unexpected failure from SELECT query.")
            self.assertTrue(os.path.isfile(outfile), "Output file not created in query export.")
            self.assertTrue(os.path.getsize(outfile), "Output file has no content in query export.")


    def verify_execute_flags(self):
        """Tests 'execute': various command-line flags."""
        logger.info("Testing SELECT query with --allow-empty.")
        outfile = self.mktemp(".csv")
        res, out, err = self.run_cmd("execute", self._dbname,
            "SELECT * FROM foo LIMIT 0", "-o", outfile)
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertFalse(os.path.isfile(outfile), "Output file created in empty query export.")
        res, out, err = self.run_cmd("execute", self._dbname,
            "SELECT * FROM foo LIMIT 0", "-o", outfile, "--allow-empty")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertTrue(os.path.isfile(outfile), "Output file not created in empty query export.")

        logger.info("Testing SELECT query with --overwrite.")
        outfile = self.mktemp(".html", "custom")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-o", outfile)
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertEqual(os.path.getsize(outfile), 6, "Output file overwritten in query export.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-o", outfile,
                                     "--overwrite")
        self.assertFalse(res, "Unexpected failure from SELECT query.")
        self.assertGreater(os.path.getsize(outfile), 6, "Output file not overwritten in query export.")


    def verify_export_formats(self):
        """Tests 'export': output to console and file in different formats."""
        logger.info("Testing export in all formats.")

        for fmt in PRINTABLE_FORMATS:
            logger.info("Testing export as %s.", fmt.upper())
            res, out, err = self.run_cmd("export", self._dbname, "-f", fmt)
            self.assertFalse(res, "Unexpected failure from export.")
            self.assertTrue(out, "Unexpected lack of output from export.")

        for fmt in OUTPUT_FORMATS:
            logger.info("Testing export to file as combined %s.", fmt.upper())
            outfile = self.mktemp("." + fmt)
            res, out, err = self.run_cmd("export", self._dbname, "-o", outfile, "--combine")
            self.assertFalse(res, "Unexpected failure from export.")
            self.assertTrue(os.path.isfile(outfile), "Output file not created in export.")
            self.assertTrue(os.path.getsize(outfile), "Output file has no content in export.")

        for fmt in OUTPUT_FORMATS:
            logger.info("Testing export to separate files as %s.", fmt.upper())
            outpath = self.mkdtemp()
            res, out, err = self.run_cmd("export", self._dbname, "-f", fmt, "--path", outpath)
            self.assertFalse(res, "Unexpected failure from export.")
            files = glob.glob(os.path.join(outpath, "*." + fmt))
            self.assertTrue(files, "Output files not created in export.")


    def verify_export_selections(self):
        """Tests 'export': output to console with entity selections."""
        logger.info("Testing export with entity selections.")

        res, out, err = self.run_cmd("export", self._dbname, "-f", "json", "--select", "parent")
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {"parent": DATA["parent"]},
                        "Unexpected output from export.")

        res, out, err = self.run_cmd("export", self._dbname, "-f", "json",
                                     "--select", "~related", "~empty", "~myview")
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {"parent": DATA["parent"]},
                        "Unexpected output from export.")

        res, out, err = self.run_cmd("export", self._dbname, "-f", "json",
                                     "--select", "~parent", "related", "~empty")
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {"related": DATA["related"]},
                        "Unexpected output from export.")

        logger.info("Testing export with --include-related.")
        res, out, err = self.run_cmd("export", self._dbname, "-f", "json",
                                     "--select", "~parent", "~myview", "related", "--include-related")
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {k: DATA[k] for k in ("parent", "related")},
                        "Unexpected output from export.")


    def verify_export_limits(self):
        """Tests 'export': output to console with limits and offsets."""
        logger.info("Testing export with result limiting.")

        logger.info("Testing export with --limit.")
        res, out, err = self.run_cmd("export", self._dbname, "-f", "json",
                                     "--select", "parent", "--limit", 5)
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {"parent": DATA["parent"][:5]},
                        "Unexpected output from export.")

        logger.info("Testing export with --limit --offset.")
        res, out, err = self.run_cmd("export", self._dbname, "-f", "json",
                                     "--select", "parent", "--limit", 5, "--offset", 5)
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {"parent": DATA["parent"][5:]},
                        "Unexpected output from export.")

        logger.info("Testing export with --limit --max-count.")
        res, out, err = self.run_cmd("export", self._dbname, "-f", "json",
                                     "--limit", 5, "--max-count", 6)
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {"empty": [], "parent": DATA["parent"][:5],
                                           "related": DATA["related"][:1], "myview": []},
                        "Unexpected output from export.")

        logger.info("Testing export with --reverse.")
        res, out, err = self.run_cmd("export", self._dbname, "-f", "json", "--reverse")
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(json.loads(out), {k: v[::-1] for k, v in DATA.items()},
                        "Unexpected output from export.")


    def verify_export_flags(self):
        """Tests 'export': various command-line flags."""
        logger.info("Testing export with --no-empty.")
        outpath = self.mkdtemp()
        res, out, err = self.run_cmd("export", self._dbname, "-f", "html", "--path", outpath)
        self.assertFalse(res, "Unexpected failure from export.")
        files = glob.glob(os.path.join(outpath, "*.html"))
        self.assertTrue(files, "Output files not created in export.")
        self.assertTrue(any("empty" in f for f in files), "Emtpy table not exported.")

        outpath = self.mkdtemp()
        res, out, err = self.run_cmd("export", self._dbname, "-f", "html",
                                     "--path", outpath, "--no-empty")
        self.assertFalse(res, "Unexpected failure from export.")
        files = glob.glob(os.path.join(outpath, "*.html"))
        self.assertTrue(files, "Output files not created in export.")
        self.assertFalse(any("empty" in f for f in files), "Emtpy table exported.")

        logger.info("Testing export with --overwrite.")
        outfile = self.mktemp(".html", "custom")
        res, out, err = self.run_cmd("export", self._dbname, "-o", outfile, "--combine")
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertEqual(os.path.getsize(outfile), 6, "Output file overwritten in export.")
        res, out, err = self.run_cmd("export", self._dbname,
                                     "-o", outfile, "--combine", "--overwrite")
        self.assertFalse(res, "Unexpected failure from export.")
        self.assertGreater(os.path.getsize(outfile), 6, "Output file not overwritten in export.")


    def verify_import_formats(self):
        """Tests 'import': from different formats."""

        for fmt in IMPORT_FORMATS:
            logger.info("Testing import from %s.", fmt.upper())
            combined = fmt in MULTISHEET_FORMATS
            single_name = None if combined else "parent"
            schema = {k: COLUMNS[k] for k in (COLUMNS if combined else [single_name])}
            data   = {k: DATA[k]    for k in (COLUMNS if combined else [single_name])}
            infile = self.mktemp("." + fmt)
            populate_datafile(infile, fmt, data, schema, combined)

            outfile = self.mktemp(".db")
            res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes", "--row-header")
            self.assertFalse(res, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            basename = os.path.splitext(os.path.basename(infile))[0]
            with contextlib.closing(sqlite3.connect(outfile)) as db:
                db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                for item_name in schema:
                    table_name = item_name if combined else basename
                    rows = db.execute("SELECT * FROM %s" % table_name).fetchall()
                    if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                    self.assertEqual(rows, data[item_name],
                                     "Unexpected data in import %r." % item_name)


    def verify_import_limits(self):
        """Tests 'import': with limits and offsets."""
        logger.info("Testing import with result limiting.")

        FLAGSETS = [("--limit", 3), ("--offset", 7), ("--limit", 5, "--offset", 7),
                    ("--max-count", 6), ("--max-count", 16), ("--limit", 3, "--max-count", 6)]

        for fmt in IMPORT_FORMATS:
            logger.info("Testing import from %s.", fmt.upper())
            combined = fmt in MULTISHEET_FORMATS
            single_name = None if combined else "parent"
            schema = {k: COLUMNS[k] for k in (COLUMNS if combined else [single_name])}
            data   = {k: DATA[k]    for k in (COLUMNS if combined else [single_name])}
            infile = self.mktemp("." + fmt)
            populate_datafile(infile, fmt, data, schema, combined)

            for flags in FLAGSETS:
                logger.info("Testing import from %s with %s.", fmt.upper(), " ".join(map(str, flags)))
                outfile = self.mktemp(".db")
                res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes",
                                             "--row-header", *flags)
                self.assertFalse(res, "Unexpected failure from import.")
                self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
                basename = os.path.splitext(os.path.basename(infile))[0]
                with contextlib.closing(sqlite3.connect(outfile)) as db:
                    db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                    total = 0
                    for item_name in schema:
                        table_name = item_name if combined else basename
                        expected = data[item_name]
                        if "--offset" in flags:
                            expected = expected[ flags[flags.index("--offset") + 1]:]
                        if "--limit"  in flags:
                            expected = expected[:flags[flags.index("--limit")  + 1]]
                        if "--max-count" in flags:
                            maxcount = flags[flags.index("--max-count") + 1]
                            if total + len(expected) > maxcount:
                                expected = expected[:maxcount - total - len(expected)]
                        rows = db.execute("SELECT * FROM %s" % table_name).fetchall()
                        if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                        self.assertEqual(rows, expected,
                                         "Unexpected data in import %r." % item_name)
                        total += len(expected)


    def verify_import_noempty(self):
        """Tests 'import': with --no-empty."""
        logger.info("Testing import with --no-empty.")

        for fmt in IMPORT_FORMATS:
            logger.info("Testing import from %s with --no-empty.", fmt.upper())
            combined = fmt in MULTISHEET_FORMATS
            single_name = None if combined else "parent"
            schema = {k: COLUMNS[k] for k in (COLUMNS if combined else [single_name])}
            data   = {k: DATA[k]    for k in (COLUMNS if combined else [single_name])}
            infile = self.mktemp("." + fmt)
            populate_datafile(infile, fmt, data, schema, combined)

            outfile = self.mktemp(".db")
            res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes",
                                         "--row-header", "--no-empty")
            self.assertFalse(res, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            basename = os.path.splitext(os.path.basename(infile))[0]
            with contextlib.closing(sqlite3.connect(outfile)) as db:
                db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                received = set(r["name"] for r in rows)
                expected = set(schema) if combined else set([basename])
                self.assertEqual(received, expected, "Unexpected data in import with --no-empty.")


    def verify_import_addpk(self):
        """Tests 'import': with --add-pk."""
        logger.info("Testing import with --add-pk.")

        for i, fmt in enumerate(IMPORT_FORMATS):
            pk = "custom" if i % 2 else None
            logger.info("Testing import from %s with --add-pk%s.",
                        fmt.upper(), " %s" % pk if pk else "")
            combined = fmt in MULTISHEET_FORMATS
            single_name = None if combined else "parent"
            schema = {k: COLUMNS[k] for k in (COLUMNS if combined else [single_name])}
            data   = {k: DATA[k]    for k in (COLUMNS if combined else [single_name])}
            infile = self.mktemp("." + fmt)
            populate_datafile(infile, fmt, data, schema, combined)

            outfile = self.mktemp(".db")
            res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes",
                                         "--row-header", "--add-pk", *[pk] if pk else [])
            self.assertFalse(res, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            basename = os.path.splitext(os.path.basename(infile))[0]
            with contextlib.closing(sqlite3.connect(outfile)) as db:
                db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                for item_name in schema:
                    table_name = item_name if combined else basename
                    expected = [dict(r, **{pk or "id_2":i + 1})
                                for i, r in enumerate(data[item_name])]
                    rows = db.execute("SELECT * FROM %s" % table_name).fetchall()
                    if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                    self.assertEqual(rows, expected, "Unexpected data in import %r." % item_name)


    def verify_import_rowheader(self):
        """Tests 'import': with --row-header."""
        logger.info("Testing import with --row-header.")

        for fmt in SPREADSHEET_FORMATS:
            logger.info("Testing import from %s with --row-header.", fmt.upper())
            combined = fmt in MULTISHEET_FORMATS
            single_name = None if combined else "parent"
            schema = {k: COLUMNS[k] for k in (COLUMNS if combined else [single_name])}
            data   = {k: DATA[k]    for k in (COLUMNS if combined else [single_name])}
            infile = self.mktemp("." + fmt)
            populate_datafile(infile, fmt, data, schema, combined, header=False)

            outfile = self.mktemp(".db")
            res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes")
            self.assertFalse(res, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            basename = os.path.splitext(os.path.basename(infile))[0]
            with contextlib.closing(sqlite3.connect(outfile)) as db:
                db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                for item_name in schema:
                    table_name = item_name if combined else basename
                    table_row = db.execute("SELECT name FROM sqlite_master "
                                           "WHERE type = 'table' AND name = ?",
                                           [table_name]).fetchone()
                    self.assertEqual(bool(table_row), bool(data[item_name]),
                                     "Unexpected result from existence check on %r." % item_name)
                    if not table_row: continue # for item_name
                    expected = [{c: r[k] for k, c in zip(COLUMNS[item_name], string.ascii_uppercase)}
                                for r in data[item_name]]
                    rows = db.execute("SELECT * FROM %s" % table_name).fetchall()
                    if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                    self.assertEqual(rows, expected, "Unexpected data in import %r." % item_name)


    def verify_import_selections(self):
        """Tests 'import': with table selections."""
        logger.info("Testing import with table selections.")

        SELECTSETS = ({"parent": True}, {"related": False}, {"parent": True, "related": False})

        for fmt in SPREADSHEET_FORMATS:
            logger.info("Testing import from %s with table selections.", fmt.upper())
            combined = fmt in MULTISHEET_FORMATS

            for selectset in SELECTSETS:
                flags = ["--select"] + [("" if v else "~") + k for k, v in selectset.items()]
                schema = {k: COLUMNS[k] for k in COLUMNS if selectset.get(k)}
                if not any(selectset.values()):
                    schema.update({k: COLUMNS[k] for k in COLUMNS if selectset.get(k, True)})
                data   = {k: DATA[k] for k in schema}
                infile = self.mktemp("." + fmt)
                populate_datafile(infile, fmt, data, schema, combined)

                outfile = self.mktemp(".db")
                res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes", *flags)
                self.assertFalse(res, "Unexpected failure from import.")
                self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
                basename = os.path.splitext(os.path.basename(infile))[0]
                with contextlib.closing(sqlite3.connect(outfile)) as db:
                    db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                    rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                    received = set(r["name"] for r in rows)
                    expected = set(schema) if combined else set([basename])
                    self.assertEqual(received, expected,
                                     "Unexpected data in import with %s." % " ".join(flags))


    def verify_import_columns(self):
        """Tests 'import': with column selections."""
        logger.info("Testing import with column selections.")

        COLSETS = {None: ("id", "id,fk", "id,value")}
        for fmt in SPREADSHEET_FORMATS:
            COLSETS[fmt] = ("1", "1..1", "1..2", "1,2", "A..A", "A..B", "A..Z")
        EXPECTEDS = {
            "id": ["id"], "id,fk": ["id", "fk"], "id,value": ["id", "value"], "1": ["id"],
            "1..1": ["id"], "1..2": ["id", "value"], "1,2": ["id", "value"],
            "A..A": ["id"], "A..B": ["id", "value"], "A..Z": ["id", "value", "fk"],
        }

        for fmt in IMPORT_FORMATS:
            logger.info("Testing import from %s with column selections.", fmt.upper())
            combined = fmt in MULTISHEET_FORMATS
            single_name = None if combined else "related"
            schema = {k: COLUMNS[k] for k in (COLUMNS if combined else [single_name])}
            data   = {k: DATA[k]    for k in (COLUMNS if combined else [single_name])}
            infile = self.mktemp("." + fmt)
            populate_datafile(infile, fmt, data, schema, combined)

            basename = os.path.splitext(os.path.basename(infile))[0]
            for i, colset in enumerate(COLSETS[None] + COLSETS.get(fmt, ())):
                flag = colset.upper() if fmt in ("json", "yaml") and i % 2 else colset
                flags = ["--columns", flag]
                outfile = self.mktemp(".db")
                logger.info("Testing import from %s with --colset %s.", fmt.upper(), colset)
                res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes",
                                             "--row-header", "--columns", colset)
                self.assertFalse(res, "Unexpected failure from import.")
                self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
                with contextlib.closing(sqlite3.connect(outfile)) as db:
                    db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                    for item_name in schema:
                        table_name = item_name if combined else basename
                        rows = db.execute("PRAGMA table_info(%s)" % table_name).fetchall()
                        received = [r["name"] for r in rows]
                        expected = [c for c in EXPECTEDS[colset] if c in schema[item_name]]
                        self.assertEqual(received, expected,
                                         "Unexpected columns in import with --colset %r." % colset)


    def verify_import_flags(self):
        """Tests 'import': various command-line flags."""

        TABLE = "mytable"
        for fmt in IMPORT_FORMATS:
            logger.info("Testing import from %s with --table-name.", fmt.upper())
            combined = fmt in MULTISHEET_FORMATS
            single_name = None if combined else "related"
            schema = {k: COLUMNS[k] for k in (COLUMNS if combined else [single_name])}
            data   = {k: DATA[k]    for k in (COLUMNS if combined else [single_name])}
            infile = self.mktemp("." + fmt)
            populate_datafile(infile, fmt, data, schema, combined)

            outfile = self.mktemp(".db")
            res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes",
                                         "--row-header", "--table-name", TABLE)
            self.assertFalse(res, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            with contextlib.closing(sqlite3.connect(outfile)) as db:
                db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                received = set(r["name"] for r in rows)
                expected = set([TABLE + ("_%s" % (i + 1) if i else "") for i in range(len(schema))])
                self.assertEqual(received, expected, "Unexpected tables in import.")

            # Verify data getting inserted into existing tables
            logger.info("Testing import from %s with --create-always.", fmt.upper())
            res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes",
                                         "--row-header", "--table-name", TABLE)
            self.assertFalse(res, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            with contextlib.closing(sqlite3.connect(outfile)) as db:
                db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                received = set(r["name"] for r in rows)
                expected = set([TABLE + ("_%s" % (i + 1) if i else "") for i in range(len(schema))])
                self.assertEqual(received, expected, "Unexpected tables in import.")
                for i, item_name in enumerate(schema):
                    table_name = TABLE + ("_%s" % (i + 1) if i else "")
                    expected = data[item_name] * 2
                    rows = db.execute("SELECT * FROM %s" % table_name).fetchall()
                    if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                    self.assertEqual(rows, expected, "Unexpected data in import %r." % item_name)

            # Verify data getting inserted into new tables
            res, out, err = self.run_cmd("import", infile, outfile, "--assume-yes",
                                         "--row-header", "--table-name", TABLE, "--create-always")
            self.assertFalse(res, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            with contextlib.closing(sqlite3.connect(outfile)) as db:
                db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                rows = db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                received = set(r["name"] for r in rows)
                expected = set([TABLE + ("_%s" % (i + 1) if i else "") for i in range(len(schema) * 2)])
                self.assertEqual(received, expected, "Unexpected tables in import.")


    def verify_parse_full(self):
        """Tests 'parse': full SQL dump."""
        logger.info("Testing parse command with full output to console.")
        res, out, err = self.run_cmd("parse", self._dbname)
        self.assertFalse(res, "Unexpected failure from parse.")
        for sql in (v for d in SCHEMA.values() for v in d.values()):
            self.assertIn(sql, out, "Unexpected output in parse.")

        logger.info("Testing parse command with full output to file.")
        outfile = self.mktemp(".sql")
        res, out, err = self.run_cmd("parse", self._dbname, "-o", outfile)
        self.assertFalse(res, "Unexpected failure from parse.")
        self.assertTrue(os.path.isfile(outfile), "Output file not created in parse.")
        with io.open(outfile, "r", encoding="utf-8") as f: content = f.read()
        for sql in (v for d in SCHEMA.values() for v in d.values()):
            self.assertIn(sql, content, "Unexpected output in parse.")

        logger.info("Testing parse command output to file with --overwrite.")
        outfile = self.mktemp(".sql", "custom")
        res, out, err = self.run_cmd("parse", self._dbname, "-o", outfile)
        self.assertFalse(res, "Unexpected failure from parse.")
        self.assertEqual(os.path.getsize(outfile), 6, "Output file overwritten in parse.")
        res, out, err = self.run_cmd("parse", self._dbname, "-o", outfile, "--overwrite")
        self.assertFalse(res, "Unexpected failure from parse.")
        self.assertGreater(os.path.getsize(outfile), 6, "Output file not overwritten in parse.")


    def verify_parse_search(self):
        """Tests 'parse': filter SQL."""
        logger.info("Testing parse command with filters.")

        FILTERSETS = {
            "parent":         ["parent", "related"],
            "related":        ["TABLE related"],
            "parent related": ["TABLE related"],
            "empty":          ["TABLE empty", "TRIGGER on_insert_empty"],
            "on*empty":       ["TRIGGER on_insert_empty"],
            "table:empty":    ["TABLE empty"],
            "trigger:empty":  ["TRIGGER on_insert_empty"],
            "table:pa*t "
            "index:parent":   ["TABLE parent", "INDEX parent_idx"],
            "column:fk":      ["TABLE related"],
            "column:id":      ["TABLE parent", "TABLE related", "TABLE empty", "INDEX parent_idx", "VIEW myview"],
            "~column:id":     ["TRIGGER on_insert_empty"],
            "table:* "
            "~table:empty":   ["TABLE parent", "TABLE related"],
            "~table:*":       ["INDEX parent_idx", "TRIGGER on_insert_empty", "VIEW myview"],
            "view":           ["VIEW myview"],
        }

        for filterset, expecteds in FILTERSETS.items():
            logger.info("Testing parse command with %r.", filterset)
            res, out, err = self.run_cmd("parse", self._dbname, filterset)
            self.assertFalse(res, "Unexpected failure from parse.")
            for sql in (v for d in SCHEMA.values() for v in d.values()):
                action = self.assertIn if any(x in sql for x in expecteds) else self.assertNotIn
                action(sql, out, "Unexpected output in parse for %r." % filterset)

        logger.info("Testing parse command with --case.")
        res, out, err = self.run_cmd("parse", self._dbname, "ON")
        self.assertFalse(res, "Unexpected failure from parse.")
        for sql in (v for d in SCHEMA.values() for v in d.values()):
            action = self.assertIn if "on" in sql.lower() else self.assertNotIn
            action(sql, out, "Unexpected output in parse with --case.")
        res, out, err = self.run_cmd("parse", self._dbname, "ON", "--case")
        self.assertFalse(res, "Unexpected failure from parse.")
        for sql in (v for d in SCHEMA.values() for v in d.values()):
            action = self.assertIn if "ON" in sql else self.assertNotIn
            action(sql, out, "Unexpected output in parse with --case.")


    def verify_parse_limits(self):
        """Tests 'parse': output limits and offsets."""
        logger.info("Testing parse with --reverse.")
        res, out, err = self.run_cmd("parse", self._dbname, "--reverse")
        self.assertFalse(res, "Unexpected failure from parse.")

        CATEGORY_ORDER = ["table", "view", "index", "trigger"]
        seen = set()
        creates = [x for x in out.splitlines() if x.startswith("CREATE ")]
        order_expected = CATEGORY_ORDER[::-1]
        order_received = [re.sub(r"CREATE (\w+)\s.+$", r"\1", x).lower() for x in creates]
        received = [x for x in order_received if x not in seen and not seen.add(x)]
        expected = [x for x in order_expected if x in received]
        self.assertEqual(received, expected, "Unexpected order in parse with --reverse.")

        LIMITS_OFFSETS = [(2, None), (None, 2), (1, 3)]

        for limit, offset in LIMITS_OFFSETS:
            flags  = [] if limit  is None else ["--limit",  limit]
            flags += [] if offset is None else ["--offset", offset]
            logger.info("Testing parse with %s.", " ".join(map(str, flags)))
            res, out, err = self.run_cmd("parse", self._dbname, *flags + ["--verbose"])
            self.assertFalse(res, "Unexpected failure from parse.")
            creates = [x for x in out.splitlines() if x.startswith("CREATE ")]
            sqls = [v for c in CATEGORY_ORDER for v in SCHEMA.get(c, {}).values()]
            count_expected = min(len(sqls) - (offset or 0), limit or len(sqls))
            self.assertEqual(len(creates), count_expected,
                             "Unexpected number of items in parse with --limit.")
            for remote, local in zip(creates, sqls[offset or 0:]):
                received = re.sub(r"CREATE \w+ (\w+)\s.+$", r"\1", remote, flags=re.DOTALL)
                expected = re.sub(r"CREATE \w+ (\w+)\s.+$", r"\1", local,  flags=re.DOTALL)
                self.assertEqual(expected, received, "Unexpected items in parse with --limit.")


    def verify_pragma_full(self):
        """Tests 'pragma': full SQL dump."""
        SOME_EXPECTED = ["PRAGMA auto_vacuum", "PRAGMA user_version", "PRAGMA page_count",
                         "PRAGMA count_changes"]

        logger.info("Testing pragma command with full output to console.")
        res, out, err = self.run_cmd("pragma", self._dbname)
        self.assertFalse(res, "Unexpected failure from pragma.")
        for expected in SOME_EXPECTED:
            self.assertIn(expected, out, "Unexpected output in pragma.")

        logger.info("Testing pragma command with full output to file.")
        outfile = self.mktemp(".sql")
        res, out, err = self.run_cmd("pragma", self._dbname, "-o", outfile)
        self.assertFalse(res, "Unexpected failure from pragma.")
        self.assertTrue(os.path.isfile(outfile), "Output file not created in pragma.")
        with io.open(outfile, "r", encoding="utf-8") as f: content = f.read()
        for expected in SOME_EXPECTED:
            self.assertIn(expected, content, "Unexpected output in pragma.")

        logger.info("Testing pragma command output to file with --overwrite.")
        outfile = self.mktemp(".sql", "custom")
        res, out, err = self.run_cmd("pragma", self._dbname, "-o", outfile)
        self.assertFalse(res, "Unexpected failure from pragma.")
        self.assertEqual(os.path.getsize(outfile), 6, "Output file overwritten in pragma.")
        res, out, err = self.run_cmd("pragma", self._dbname, "-o", outfile, "--overwrite")
        self.assertFalse(res, "Unexpected failure from pragma.")
        self.assertGreater(os.path.getsize(outfile), 6, "Output file not overwritten in pragma.")


    def verify_pragma_search(self):
        """Tests 'pragma': filter PRAGMAs."""
        logger.info("Testing pragma command with filters.")

        FILTERSETS = {
            "temp":         ["temp_store", "temp_store_directory"],
            "mmap schema":  ["mmap_size", "schema_version", "writable_schema"],
            "000":          ["busy_timeout", "cache_size", "default_cache_size",
                             "wal_autocheckpoint"],
            "freelist":     ["freelist_count"],
        }

        for filterset, expecteds in FILTERSETS.items():
            logger.info("Testing pragma command with %r.", filterset)
            res, out, err = self.run_cmd("pragma", self._dbname, filterset)
            self.assertFalse(res, "Unexpected failure from pragma.")
            pragmas = set(re.sub(r"PRAGMA (\w+)\s=.+$", r"\1", x) for x in out.splitlines()
                          if x.startswith("PRAGMA"))
            pragmas.discard("compile_options") # Unreliable over different python/sqlite versions
            pragmas.discard("trusted_schema") # Unreliable over different python/sqlite versions
            pragmas.discard("pragma_list") # Became always available from SQLite v3.30.0
            self.assertEqual(pragmas, set(expecteds),
                             "Unexpected output in pragma for %r." % filterset)


    def verify_search_formats(self):
        """Tests 'search': output to console and file in different formats."""
        logger.info("Testing search output in all formats.")

        for fmt in PRINTABLE_FORMATS:
            logger.info("Testing search output as %s.", fmt.upper())
            res, out, err = self.run_cmd("search", self._dbname, "-f", fmt, "*")
            self.assertFalse(res, "Unexpected failure from search.")
            self.assertTrue(out, "Unexpected lack of output from search.")

        for fmt in OUTPUT_FORMATS:
            logger.info("Testing search output to file as combined %s.", fmt.upper())
            outfile = self.mktemp("." + fmt)
            res, out, err = self.run_cmd("search", self._dbname, "-o", outfile, "--combine", "*")
            self.assertFalse(res, "Unexpected failure from search.")
            self.assertTrue(os.path.isfile(outfile), "Output file not created in search.")
            self.assertTrue(os.path.getsize(outfile), "Output file has no content in search.")

        for fmt in OUTPUT_FORMATS:
            logger.info("Testing search output to separate files as %s.", fmt.upper())
            outpath = self.mkdtemp()
            res, out, err = self.run_cmd("search", self._dbname, "-f", fmt, "--path", outpath, "*")
            self.assertFalse(res, "Unexpected failure from search.")
            files = glob.glob(os.path.join(outpath, "*." + fmt))
            self.assertTrue(files, "Output files not created in search.")

        for fmt in OUTPUT_FORMATS:
            logger.info("Testing search output to file as combined %s with --overwrite.",
                        fmt.upper())
            outfile = self.mktemp("." + fmt, "custom")
            res, out, err = self.run_cmd("search", self._dbname, "-o", outfile, "--combine", "*")
            self.assertFalse(res, "Unexpected failure from search.")
            self.assertEqual(os.path.getsize(outfile), 6, "Output file overwritten in search.")
            res, out, err = self.run_cmd("search", self._dbname, "-o", outfile, "--combine",
                                         "--overwrite", "*")
            self.assertFalse(res, "Unexpected failure from search.")
            self.assertGreater(os.path.getsize(outfile), 6,
                               "Output file not overwritten in search.")



    def verify_search_limits(self):
        """Tests 'search': output to console with limits and offsets."""
        logger.info("Testing search with result limiting.")

        logger.info("Testing search with --limit.")
        res, out, err = self.run_cmd("search", self._dbname, "-f", "json",
                                     "--limit", 5, "table:parent")
        self.assertFalse(res, "Unexpected failure from search.")
        self.assertEqual(json.loads(out), {"parent": DATA["parent"][:5]},
                        "Unexpected output from search.")

        logger.info("Testing search with --limit --offset.")
        res, out, err = self.run_cmd("search", self._dbname, "-f", "json",
                                     "--limit", 5, "--offset", 5, "table:parent")
        self.assertFalse(res, "Unexpected failure from search.")
        self.assertEqual(json.loads(out), {"parent": DATA["parent"][5:]},
                        "Unexpected output from search.")

        logger.info("Testing search with --limit --max-count.")
        res, out, err = self.run_cmd("search", self._dbname, "-f", "json",
                                     "--limit", 5, "--max-count", 6, "*")
        self.assertFalse(res, "Unexpected failure from search.")
        self.assertEqual(json.loads(out), {"empty": [], "parent": DATA["parent"][:5],
                                           "related": DATA["related"][:1], "myview": []},
                        "Unexpected output from search.")

        logger.info("Testing search with --reverse.")
        res, out, err = self.run_cmd("search", self._dbname, "-f", "json", "--reverse", "*")
        self.assertFalse(res, "Unexpected failure from search.")
        self.assertEqual(json.loads(out), {k: v[::-1] for k, v in DATA.items()},
                        "Unexpected output from search.")


    def verify_search_filters(self):
        """Tests 'search': filter SQL."""
        logger.info("Testing search command with filters.")

        FILTERSETS = {
            "table:parent 2 b":               {"parent":  [2, "b"]},
            "table:parent table:related 2 b": {"parent":  [2, "b"],      "related": [2, "b"]},
            "table:*a* 2 b":                  {"parent":  [2, "b"],      "related": [2, "b"]},
            "this OR these":                  {"parent":  [],            "related": [],            "myview": []},
            "~these":                         {"parent":  ["this"],      "related": ["this"],      "myview": ["this"]},
            '"these two"':                    {"parent":  ["these two"], "related": ["these two"], "myview": ["these two"]},
            '~"these two"':                   {"parent":  ["this"],      "related": ["this"],      "myview": ["this"]},
            "~table:parent 2 b":              {                          "related": [2, "b"],      "myview": [2, "b"]},
            "column:fk 2":                    {"related": [("fk", 2), ]},
            "~column:fk 2":                   {"parent":  [2],           "related": [("fk", 8)],   "myview": [2]},
            "~ignored":                       {"parent":  [],            "related": [],            "myview": []},
            "view:*":                         {                                                    "myview": []},
            "nosuchthing":                    {},
        }

        for filterset, filters in FILTERSETS.items():
            logger.info("Testing search command with %r.", filterset)
            res, out, err = self.run_cmd("search", self._dbname, "-f", "json",
                                         "--no-empty", filterset)
            self.assertFalse(res, "Unexpected failure from search.")
            received, expected = json.loads(out or "{}"), {}
            for name, tfilters in filters.items():
                if not tfilters:
                    expected[name] = DATA[name]
                    continue # for name, tfilters
                rows = []
                for v in tfilters:
                    if isinstance(v, tuple):
                        rows.extend(i for i, r in enumerate(DATA[name]) if r[v[0]] == v[1])
                    elif isinstance(v, text_type):
                        rows.extend(i for i, r in enumerate(DATA[name])
                                    if any(v in x for x in r.values() if isinstance(x, text_type)))
                    else:
                        rows.extend(i for i, r in enumerate(DATA[name])
                                    if any(v == x for x in r.values()))
                expected[name] = [DATA[name][i] for i in sorted(set(rows))]
            self.assertEqual(received, expected, "Unexpected output in search for %r" % filterset)

        logger.info("Testing search command with --case.")
        res, out, err = self.run_cmd("search", self._dbname, "-f", "json", "--no-empty", "b")
        self.assertFalse(res, "Unexpected failure from search.")
        self.assertEqual(json.loads(out or "{}"), {k: DATA[k] for k in ("parent", "related", "myview")},
                         "Unexpected output in search.")
        res, out, err = self.run_cmd("search", self._dbname, "-f", "json", "--no-empty",
                                     "--case", "b")
        self.assertFalse(res, "Unexpected failure from search.")
        self.assertEqual(json.loads(out or "{}"), {}, "Unexpected output in search.")
        res, out, err = self.run_cmd("search", self._dbname, "-f", "json", "--case", "B")
        self.assertFalse(res, "Unexpected failure from search.")
        self.assertEqual(json.loads(out or "{}"), DATA, "Unexpected output in search.")


    def verify_stats_formats(self):
        """Tests 'stats': output to console and file in different formats."""
        logger.info("Testing stats output in all formats.")

        for fmt in (x for x in STATS_FORMATS if x != "html"):
            logger.info("Testing stats output as %s.", fmt.upper())
            res, out, err = self.run_cmd("stats", self._dbname, "-f", fmt)
            self.assertFalse(res, "Unexpected failure from stats.")
            self.assertTrue(out, "Unexpected lack of output from stats.") if "html" != fmt else None

        for fmt in STATS_FORMATS:
            logger.info("Testing stats output to file as combined %s.", fmt.upper())
            outfile = self.mktemp("." + fmt)
            res, out, err = self.run_cmd("stats", self._dbname, "-o", outfile)
            self.assertFalse(res, "Unexpected failure from stats.")
            self.assertTrue(os.path.isfile(outfile), "Output file not created in stats.")
            self.assertTrue(os.path.getsize(outfile), "Output file has no content in stats.")

        for fmt in STATS_FORMATS:
            logger.info("Testing stats output to file as %s with --overwrite.", fmt.upper())
            outfile = self.mktemp("." + fmt, "custom")
            res, out, err = self.run_cmd("stats", self._dbname, "-o", outfile)
            self.assertFalse(res, "Unexpected failure from stats.")
            self.assertEqual(os.path.getsize(outfile), 6, "Output file overwritten in stats.")
            res, out, err = self.run_cmd("stats", self._dbname, "-o", outfile, "--overwrite")
            self.assertFalse(res, "Unexpected failure from stats.")
            self.assertGreater(os.path.getsize(outfile), 6,
                               "Output file not overwritten in stats.")


    def verify_stats_flags(self):
        """Tests 'stats': output with --disk-usage."""
        logger.info("Testing stats output with --disk-usage.")

        for fmt in (x for x in STATS_FORMATS if x != "sql"):
            logger.info("Testing stats output as %s without --disk-usage.", fmt.upper())
            outfile = self.mktemp("." + fmt)
            res, out, err = self.run_cmd("stats", self._dbname, "-o", outfile)
            self.assertFalse(res, "Unexpected failure from stats.")
            self.assertTrue(os.path.getsize(outfile), "Output file has no content in stats.")
            with io.open(outfile, "r", encoding="utf-8") as f: content = f.read()
            for text in ("sizes", "sizes with indexes", "index sizes"):
                self.assertNotIn(text, content, "Unexpected disk usage in stats output.")

        for fmt in (x for x in STATS_FORMATS if x != "sql"):
            logger.info("Testing stats output as %s with --disk-usage.", fmt.upper())
            outfile = self.mktemp("." + fmt)
            res, out, err = self.run_cmd("stats", self._dbname, "-o", outfile, "--disk-usage")
            self.assertFalse(res, "Unexpected failure from stats.")
            self.assertTrue(os.path.getsize(outfile), "Output file has no content in stats.")
            with io.open(outfile, "r", encoding="utf-8") as f: content = f.read()
            for text in ("sizes", "sizes with indexes", "index sizes"):
                self.assertIn(text, content, "Unexpected disk usage in stats output.")

        logger.info("Testing stats output as SQL.")
        outfile = self.mktemp(".sql")
        res, out, err = self.run_cmd("stats", self._dbname, "-o", outfile)
        self.assertFalse(res, "Unexpected failure from stats.")
        self.assertTrue(os.path.getsize(outfile), "Output file has no content in stats.")
        with io.open(outfile, "r", encoding="utf-8") as f: content = f.read()
        testfile = self.mktemp(".db")
        with contextlib.closing(sqlite3.connect(testfile)) as db:
            db.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            db.executescript(content)
            received = set(r["name"] for r in db.execute("SELECT name FROM space_used").fetchall())
            received -= set(["sqlite_master", "sqlite_schema"])
            expected = set(SCHEMA["table"]) | set(SCHEMA["index"])
            self.assertEqual(received, expected, "Unexpected output in stats.")


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t[%(created).06f] [test_cli] %(message)s"
    )
    unittest.main()
