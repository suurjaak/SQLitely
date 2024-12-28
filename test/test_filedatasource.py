#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests importexport.FileDataSource.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     07.09.2024
@modified    28.12.2024
------------------------------------------------------------------------------
"""
import contextlib
import collections
import datetime
import logging
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import database, grammar, importexport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test.common import COLUMNS, DATA, SCHEMA
from test.common import IMPORT_EXTS, IMPORT_FORMATS, MULTISHEET_FORMATS, SPREADSHEET_FORMATS
from test.common import FileTest, intify, list_database, populate_datafile


logger = logging.getLogger()


DATA    = type(DATA)   ((k, v) for k, v in DATA.items()    if k not in SCHEMA.get("view", {}))
COLUMNS = type(COLUMNS)((k, v) for k, v in COLUMNS.items() if k not in SCHEMA.get("view", {}))


class TestFileDataSource(FileTest):
    """Unit-tests FileDataSource public API."""


    def test_get_format(self):
        """Tests FileDataSource.get_format()."""
        logger.info("Verifying FileDataSource.get_format()")
        for ext in IMPORT_EXTS:
            logger.debug("Verifying get_format() for %s.", ext.upper())
            expected = "yaml" if "yml" == ext else ext
            for transform in (str.lower, str.upper):
                filename = "my input file.%s" % transform(ext)
                received = importexport.FileDataSource.get_format(filename)
                self.assertEqual(received, expected,
                                 "Unexpected result from get_format(%r)." % filename)


    def test_get_file_info(self):
        """Tests FileDataSource.get_file_info()."""
        logger.info("Verifying FileDataSource.get_file_info()")
        for fmt in IMPORT_FORMATS:
            self.verify_get_file_info(fmt) 

        logger.info("Verifying get_file_info() with nonexistent file.")
        for fmt in IMPORT_FORMATS:
            with self.assertRaises(Exception, msg="Expected error on nonexistent file."):
                importexport.FileDataSource(self.mktemp("." + fmt)).get_file_info()

        logger.info("Verifying get_file_info() with empty file.")
        for fmt in IMPORT_FORMATS:
            infile = self.mktemp("." + fmt)
            with self.assertRaises(Exception, msg="Expected error on empty file."):
                importexport.FileDataSource(self.mktemp("." + fmt, "")).get_file_info()

        logger.info("Verifying get_file_info() with unexpected format.")
        table_name = "parent"
        schema = {table_name: COLUMNS[table_name]}
        data   = {table_name: DATA[table_name]}
        infile = self.mktemp(".xls")
        populate_datafile(infile, "csv", data, schema)
        with self.assertRaises(Exception, msg="Expected error on unexpected format."):
            importexport.FileDataSource(infile).get_file_info()

        self.verify_get_file_info_seek()


    def test_iter_rows(self):
        """Verifies FileDataSource.iter_rows()."""
        logger.info("Verifying FileDataSource.iter_rows().")
        for fmt in IMPORT_FORMATS:
            self.verify_iter_rows(fmt)
        for fmt in IMPORT_FORMATS:
            self.verify_iter_rows_columns(fmt)
        for fmt in IMPORT_FORMATS:
            self.verify_iter_rows_progress(fmt)
        for fmt in MULTISHEET_FORMATS:
            self.verify_iter_rows_unknown_sheet(fmt)


    def test_import_data(self):
        """Verifies FileDataSource.import_data(),"""
        logger.info("Verifying FileDataSource.import_data().")
        for fmt in IMPORT_FORMATS:
            self.verify_import_data_format(fmt)
        self.verify_import_data_missing_blank()
        self.verify_import_data_populated()
        self.verify_import_data_pk()
        self.verify_import_data_schemastate()
        for fmt in IMPORT_FORMATS:
            self.verify_import_data_progress(fmt)
        for fmt in MULTISHEET_FORMATS:
            self.verify_import_data_unknown_sheet(fmt)
            self.verify_import_data_populated_error(fmt)
        self.verify_import_data_configure()


    def verify_get_file_info(self, fmt):
        """Tests FileDataSource.get_file_info() for given format."""
        logger.info("Verifying get_file_info() with %s.", fmt.upper())

        infile, schema, data, _ = self.prepare_import(fmt)
        single_name = None if fmt in MULTISHEET_FORMATS else "parent"
        has_sections = fmt in SPREADSHEET_FORMATS

        info = importexport.FileDataSource(infile).get_file_info()
        self.assertIsInstance(info, dict, "Unexpected return type from "
                              "FileDataSource(%r).get_file_info()." % infile)
        self.assertEqual(info["name"], infile)
        self.assertEqual(info["size"], os.path.getsize(infile))
        self.assertEqual(info["format"], fmt)
        self.assertIsInstance(info["modified"], datetime.datetime)
        self.assertIsInstance(info["sections"], list)
        self.assertEqual(len(info["sections"]), len(data))
        for section in info["sections"]:
            item_data = data[single_name or section["name"]]
            item_columns = schema[single_name or section["name"]]
            if not single_name: self.assertIn(section["name"], data)
            self.assertEqual(section["rows"], len(item_data) + has_sections)
            self.assertEqual(list(section["columns"]), item_columns)
            if not has_sections:
                self.assertIsInstance(section["columns"], collections.OrderedDict)
                self.assertEqual(section["columns"], data[single_name][0])


    def verify_get_file_info_seek(self):
        """Tests FileDataSource.configure(seek=False)."""
        logger.info("Verifying FileDataSource.configure(seek=False).get_file_info().")
        table_name = "parent"
        schema = {table_name: COLUMNS[table_name]}
        data   = {table_name: DATA[table_name]}
        data[table_name] = [{k: "" for k in schema[table_name]}] * 2 + data[table_name]
        infile = self.mktemp(".csv")
        populate_datafile(infile, "csv", data, schema, header=False)
        info = importexport.FileDataSource(infile).configure(seek=False).get_file_info()
        for section in info["sections"]:
            self.assertEqual(section["rows"], len(data[table_name]))
            self.assertFalse(section["columns"])

        info = importexport.FileDataSource(infile).configure(seek=True).get_file_info()
        for section in info["sections"]:
            self.assertEqual(section["rows"], len(DATA[table_name]))
            firstrow = [str(DATA[table_name][0][k]) for k in schema[table_name]]
            self.assertEqual(section["columns"], firstrow)


    def verify_import_data_format(self, fmt):
        """Verifies FileDataSource.import_data() for given format."""
        logger.info("Verifying import_data() with %s.", fmt.upper())

        infile, schema, data, tables = self.prepare_import(fmt)
        outfile = self.mktemp(".db")
        db = database.Database(outfile)
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                self.assertEqual(rows, data[table], "Unexpected data in import %r." % table)


    def verify_import_data_missing_blank(self):
        """Verifies FileDataSource.import_data() for a nonexistent or empty file."""
        logger.info("Verifying import_data() failing for nonexistent file.")
        infile, outfile = self.mktemp(".csv"), self.mktemp(".db")
        db = database.Database(outfile)
        with self.assertRaises(Exception, msg="Expected error on nonexistent file."):
            importexport.FileDataSource(infile, db).import_data([])

        logger.info("Verifying import_data() failing for empty file.")
        infile, outfile = self.mktemp(".csv", ""), self.mktemp(".db")
        with self.assertRaises(Exception, msg="Expected error on empty file."):
            importexport.FileDataSource(infile, db).import_data([])


    def verify_import_data_pk(self):
        """Verifies FileDataSource.import_data() adding a primary key."""
        logger.info("Verifying import_data() adding primary key.")
        fmt = "json"
        infile, schema, data, tables = self.prepare_import(fmt)
        for item in tables: item["pk"] = "my_pk"
        outfile = self.mktemp(".db")
        db = database.Database(outfile)
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                expected = [dict(x, my_pk=i + 1) for i, x in enumerate(data[table])]
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)


    def verify_import_data_populated(self):
        """Verifies FileDataSource.import_data() for an existing populated database."""
        logger.info("Verifying import_data() with an existing populated database.")
        fmt = "json"
        infile, schema, data, tables = self.prepare_import(fmt)
        outfile = self.mktemp(".db")
        db = database.Database(outfile)
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                expected = data[table]
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)

        # Add same data again
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                expected = data[table] * 2
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)

        # Add same data to new tables
        for item in tables: item["name"] = "%s_dupe" % item["name"]
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        expected_tables = list(schema) + [x["name"] for x in tables]
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in expected_tables:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                expected = data[table] * 2 if table in schema else data[table.replace("_dupe", "")]
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)


    def verify_import_data_populated_error(self, fmt):
        """Verifies FileDataSource.import_data() rollback for an existing populated database."""
        logger.info("Verifying import_data() rollback with an existing populated database for %s.",
                    fmt.upper())
        infile, schema, data, tables = self.prepare_import(fmt)
        outfile = self.mktemp(".db")
        db = database.Database(outfile)
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                expected = data[table]
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)

        # Try to add same data again but from invalid sheet names
        for item in tables[1:]: item["section"] = "no such sheet"
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertFalse(result, "Expected failure on unknown sheet.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                expected = data[table]
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)

        # Try to add same data to new tables but from invalid sheet names
        for item in tables:
            item["name"], item["section"] = "%s_dupe" % item["name"], "no such sheet"
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertFalse(result, "Expected failure on unknown sheet.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            received = list_database(sqldb)
            self.assertEqual(set(received), set(schema), "Unexpeced tables on rollback.")


    def verify_import_data_progress(self, fmt):
        """Verifies FileDataSource(progress).import_data() for specific format."""
        logger.info("Verifying FileDataSource(progress).import_data() for %s.", fmt.upper())

        progress_calls = []
        def progress(name=None, count=0, **kwargs):
            progress_calls.append(kwargs)
            if cancel_at and name == cancel_table and count >= cancel_at:
                return False
            return True

        infile, schema, data, tables = self.prepare_import(fmt)

        cancel_table = "parent"
        for cancel_at in (None, 5):
            del progress_calls[:]

            outfile = self.mktemp(".db")
            db = database.Database(outfile)
            source = importexport.FileDataSource(infile, db, progress=progress)
            if cancel_at: source.PROGRESS_STEP = cancel_at
            result = source.import_data(tables)
            self.assertTrue(progress_calls, "Expected calls to progress().")
            if cancel_at:
                self.assertFalse(result, "Unexpected success on cancelling import.")
            else:
                self.assertTrue(result, "Unexpected failure from import.")
            self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
            with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
                sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                tables_received = list_database(sqldb)
                if cancel_at:
                    self.assertNotIn("related", tables_received,
                                     "Unexpected table in import after cancel.")
                for table in schema:
                    if table not in tables_received: continue # for table
                    rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                    if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                    expected = data[table]
                    if cancel_at and table == cancel_table:
                        expected = expected[:cancel_at]
                    elif cancel_at:
                        expected = []
                    self.assertEqual(rows, expected, "Unexpected data in import %r." % table)


    def verify_import_data_schemastate(self):
        """Verifies FileDataSource.import_data() leaving Database state as expected."""
        logger.info("Verifying import_data() and state of Database.schema afterwards.")
        fmt = "json"
        infile, schema, _, tables = self.prepare_import(fmt)
        outfile = self.mktemp(".db")
        db = database.Database(outfile)
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        self.assertTrue(db.is_open(), "Expected Database instance to remain open after import.")
        self.assertEqual(set(db.schema["table"]), set(schema),
                         "Expected Database.schema to be populated after import.")
        self.assertFalse(db.get_locks(), "Unexpected locks on database after import.")
        self.assertTrue(db.log, "Expected import to populate Database action log.")

        db.close()
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertFalse(db.is_open(), "Expected Database instance to remain closed after import.")
        self.assertFalse(db.get_locks(), "Unexpected locks on database after import.")

        progress_calls = []
        def progress(name=None, section=None, index=None, count=None, **__):
            progress_calls.append(1)
            return False if name and section and index == count == 0 else True

        db.open()
        for item in tables: item["name"] = "%s_dupe" % item["name"]
        result = importexport.FileDataSource(infile, db, progress).import_data(tables)
        self.assertFalse(result, "Expected failure on cancelling import.")
        self.assertTrue(progress_calls, "Expected calls to progress().")
        self.assertTrue(db.is_open(), "Expected Database instance to remain open after import.")
        self.assertEqual(set(db.schema["table"]), set(schema),
                         "Expected Database.schema to not include new tables on cancel.")
        self.assertFalse(db.get_locks(), "Unexpected locks on database after import.")


    def verify_import_data_unknown_sheet(self, fmt):
        """Verifies FileDataSource.import_data() with a nonexistent sheet."""
        logger.info("Verifying import_data() failing with unknown sheet for %s.", fmt.upper())
        infile, schema, data, tables = self.prepare_import(fmt)
        for item in tables[1:]: item["section"] = "no such sheet"

        outfile = self.mktemp(".db")
        db = database.Database(outfile)
        db.close()
        os.remove(outfile)
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertFalse(result, "Expected failure on unknown sheet.")
        self.assertFalse(os.path.isfile(outfile), "Expected dropping empty database on error.")

        logger.info("Verifying import_data() with empty and whitespaced table names.")
        infile, schema, data, tables = self.prepare_import(fmt)
        for i, item in enumerate(tables): item["name"] = " " * i
        outfile = self.mktemp(".db")
        db = database.Database(outfile)
        result = importexport.FileDataSource(infile, db).import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for i, table in enumerate(schema):
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(" " * i)).fetchall()
                self.assertEqual(rows, data[table], "Unexpected data in import %r." % table)


    def verify_import_data_configure(self):
        """Verifies FileDataSource.configure().import_data()"""
        logger.info("Verifying FileDataSource.configure().import_data().")
        for fmt in IMPORT_FORMATS:
            self.verify_import_data_configure_header(fmt) 
            self.verify_import_data_configure_limits(fmt, limit=3)
            self.verify_import_data_configure_limits(fmt, limit=(3, ))
            self.verify_import_data_configure_limits(fmt, limit=(3, 4))
            self.verify_import_data_configure_limits(fmt, limit=(3, 4), maxcount=5)
            self.verify_import_data_configure_limits(fmt, limit=(2, 14))
            self.verify_import_data_configure_limits(fmt, maxcount=0)
            self.verify_import_data_configure_limits(fmt, limit=0)


    def verify_import_data_configure_header(self, fmt):
        """Verifies FileDataSource.configure(has_header=False).import_data() for specific format."""
        logger.debug("Verifying FileDataSource.configure(has_header=False).import_data() with %s.",
                     fmt.upper())
        has_header = fmt in SPREADSHEET_FORMATS
        infile, schema, data, tables = self.prepare_import(fmt)
        outfile = self.mktemp(".db")
        db = database.Database(outfile)

        source = importexport.FileDataSource(infile, db).configure(has_header=False)
        result = source.import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                expected = data[table]
                if has_header:
                    expected = [{k: k for k in schema[table]}] + expected
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)


    def verify_import_data_configure_limits(self, fmt, limit=None, maxcount=None):
        """Verifies FileDataSource.configure(..limits..).import_data() for specific format."""
        logger.debug("Verifying FileDataSource.configure(limit=%s, maxcount=%s).import_data() "
                     "with %s.", limit, maxcount, fmt.upper())
        infile, schema, data, tables = self.prepare_import(fmt)
        outfile = self.mktemp(".db")
        db = database.Database(outfile)

        source = importexport.FileDataSource(infile, db).configure(limit=limit, maxcount=maxcount)
        result = source.import_data(tables)
        self.assertTrue(result, "Unexpected failure from import.")
        self.assertTrue(os.path.getsize(outfile), "Expected database not created.")
        with contextlib.closing(sqlite3.connect(outfile)) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            total = 0
            for table in schema:
                rows = sqldb.execute("SELECT * FROM %s" % grammar.quote(table)).fetchall()
                if "csv" == fmt: rows = [{k: intify(v) for k, v in r.items()} for r in rows]
                expected = data[table]
                if limit and isinstance(limit, tuple) and len(limit) > 1: # OFFSET
                    expected = expected[limit[1]:]
                if limit is not None: # LIMIT
                    expected = expected[:(limit[0] if isinstance(limit, tuple) else limit)]
                if maxcount is not None:
                    if total + len(expected) > maxcount:
                        expected = expected[:maxcount - total - len(expected)]
                self.assertEqual(rows, expected, "Unexpected data in import %r." % table)
                total += len(expected)


    def verify_iter_rows(self, fmt):
        """Verifies FileDataSource.iter_rows() for specific format."""
        logger.info("Verifying iter_rows() for %s.", fmt.upper())

        has_header = fmt in SPREADSHEET_FORMATS
        infile, schema, data, _ = self.prepare_import(fmt)
        source = importexport.FileDataSource(infile)
        for table, rows in data.items():
            row_index = 0
            for i, row in enumerate(source.iter_rows(section=table)):
                if has_header and not i:
                    self.assertEqual(row, schema[table],
                                     "Expected header row from iter_rows().")
                else:
                    if "csv" == fmt: row = [intify(x) for x in row]
                    expected = [rows[row_index][k] for k in schema[table]]
                    self.assertEqual(row, expected, "Unexpected data from iter_rows().")
                    row_index += 1


    def verify_iter_rows_columns(self, fmt):
        """Verifies FileDataSource.iter_rows(columns) for specific format."""
        logger.info("Verifying iter_rows(columns) for %s.", fmt.upper())

        has_header = fmt in SPREADSHEET_FORMATS
        infile, schema, data, _ = self.prepare_import(fmt)
        source = importexport.FileDataSource(infile)
        for do_add_dummies in (False, True):
            for table, rows in data.items():
                columns = schema[table][:1]
                columns_arg = list(range(len(columns))) if has_header else list(columns)
                if do_add_dummies:
                    columns_arg += [11, 12, 13] if has_header else ["no", "such", "column"]
                row_index = 0
                for i, row in enumerate(source.iter_rows(columns_arg, section=table)):
                    if has_header and not i:
                        expected = columns + [None] * (len(columns_arg) - len(columns))
                        self.assertEqual(row, expected, "Expected header row from iter_rows().")
                    else:
                        if "csv" == fmt: row = [intify(x) for x in row]
                        expected = [rows[row_index][k] for k in columns]
                        expected += [None] * (len(columns_arg) - len(columns))
                        self.assertEqual(row, expected, "Unexpected data from iter_rows().")
                        row_index += 1


    def verify_iter_rows_progress(self, fmt):
        """Verifies FileDataSource(progress).iter_rows() for specific format."""
        if fmt not in SPREADSHEET_FORMATS: return # Seek progress only done for spreadsheets
        logger.info("Verifying FileDataSource(progress).iter_rows() for %s.", fmt.upper())

        progress_calls = []
        def progress(**kwargs):
            progress_calls.append(kwargs)
            return False if do_cancel else True

        infile, schema, data, _ = self.prepare_import(fmt)
        source = importexport.FileDataSource(infile, progress=progress)
        table = "parent"
        itemlabel = "%r in %s output" % (table, fmt.upper())
        for do_cancel in (False, True):
            del progress_calls[:]
            received = list(source.iter_rows(section=table))
            if "csv" == fmt: received = [[intify(x) for x in r] for r in received]
            expected = []
            if not do_cancel:
                expected = [schema[table]] + [[r[k] for k in schema[table]] for r in data[table]]
            self.assertEqual(received, expected, "Unexpected data for %s." % itemlabel)
            self.assertTrue(progress_calls, "Expected calls to progress().")


    def verify_iter_rows_unknown_sheet(self, fmt):
        """Verifies FileDataSource.iter_rows() with a nonexistent sheet."""
        logger.info("Verifying iter_rows() failing with unknown sheet for %s.", fmt.upper())
        infile, _, _, _ = self.prepare_import(fmt)
        with self.assertRaises(Exception, msg="Expected error on unknown sheet."):
            next(importexport.FileDataSource(infile).iter_rows(section="no such sheet"))


    def prepare_import(self, fmt):
        """Populates import data file in given format, returns (infile, schema, data, tables)."""
        single_name = None if fmt in MULTISHEET_FORMATS else "parent"
        has_names = fmt in ("json", "yaml")
        schema = collections.OrderedDict((k, COLUMNS[k]) for k in ([single_name] if single_name else COLUMNS))
        data   = collections.OrderedDict((k, DATA[k])    for k in ([single_name] if single_name else COLUMNS))
        infile = self.mktemp("." + fmt)
        populate_datafile(infile, fmt, data, schema)

        tables = []
        for table, cols in ((k, schema[k]) for k in COLUMNS if k in schema):
            cc = collections.OrderedDict((c if has_names else i, c) for i, c in enumerate(cols))
            tables.append({"name": table, "section": table, "columns": cc})

        return infile, schema, data, tables


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
