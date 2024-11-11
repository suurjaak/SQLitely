#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests importexport.DatabaseSink.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     09.09.2024
@modified    11.11.2024
------------------------------------------------------------------------------
"""
import copy
import itertools
import logging
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import database, grammar, importexport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test.common import ROWCOUNT, COLUMNS, SCHEMA, DATA, FileTest, list_database, populate_database


logger = logging.getLogger()


class TestDatabaseSink(FileTest):
    """Unit-tests DatabaseSink public API."""


    def __init__(self, *args, **kwargs):
        super(TestDatabaseSink, self).__init__(*args, **kwargs)
        self._db = None   # database.Database instance


    def setUp(self):
        """Populates test database."""
        super(TestDatabaseSink, self).setUp()
        infile = self.mktemp(".db")
        populate_database(infile, SCHEMA, COLUMNS, DATA)
        self._db = database.Database(infile, parse=True)


    def tearDown(self):
        """Deletes temoorary files."""
        try: self._db.close()
        except Exception: pass
        super(TestDatabaseSink, self).tearDown()


    def test_entities(self):
        """Verifies DatabaseSink entity export."""
        logger.info("Verifying DatabaseSink.export_entities().")
        self.verify_export_entities()
        self.verify_export_entities_renames()
        self.verify_export_entities_selects()
        self.verify_export_entities_iterables()
        self.verify_export_entities_existing()
        self.verify_export_entities_configure()
        self.verify_export_entities_fks()
        self.verify_export_entities_progress()
        self.verify_export_entities_error()


    def test_query(self):
        """Verifies DatabaseSink query export."""
        logger.info("Verifying DatabaseSink.export_query().")
        self.verify_export_query()
        self.verify_export_query_params()
        self.verify_export_query_cursor()
        self.verify_export_query_create_sql()
        self.verify_export_query_configure()
        self.verify_export_query_progress()
        self.verify_export_query_error()
        self.verify_export_query_invalid()


    def verify_export_entities(self):
        """Verifies DatabaseSink.export_entities()."""
        logger.info("Verifying export_entities() with full selection.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, DATA)

        logger.info("Verifying export_entities() with partial selection.")
        outfile = self.mktemp(".db")
        schema = {"table": [k for k in SCHEMA["table"] if "related" != k]}
        data   = {k: v for k, v in DATA.items() if k in schema["table"]}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(schema)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, schema, data)

        logger.info("Verifying export_entities() with cased selection.")
        outfile = self.mktemp(".db")
        schema = {"table": [k.upper() for k in SCHEMA["table"] if "related" != k]}
        data   = {k: v for k, v in DATA.items() if k in schema["table"]}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(schema)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, schema, data)

        logger.info("Verifying export_entities() with invalid selection.")
        outfile = self.mktemp(".db")
        schema = {"table": list(SCHEMA["table"])}
        schema["table"].append("no such table")
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.configure(data=True).export_entities(schema)
        self.assertFalse(result, "Unexpected success from export_entities().")
        self.assertFalse(os.path.isfile(outfile), "Expected database file to not exist.")

        logger.info("Verifying export_entities() with empty selection.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities({})
        self.assertFalse(result, "Unexpected success from export_entities().")
        self.assertFalse(os.path.isfile(outfile), "Expected database file to not exist.")

        logger.info("Verifying export_entities() with no data.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, {k: [] for k in DATA})


    def verify_export_entities_progress(self):
        """Verifies DatabaseSink(progress=..).export_entities()."""
        progress_calls = []
        progress_result = False
        def progress(**kwargs):
            progress_calls.append(kwargs)
            return progress_result

        logger.info("Verifying export_entities() with progress callback.")
        outfile = self.mktemp(".db")
        schema = {"table": list(SCHEMA["table"])}
        sink = importexport.DatabaseSink(self._db, outfile, progress).configure(data=True)
        result = sink.export_entities(schema)
        self.assertFalse(result, "Unexpected success from export_query() for empty result.")
        self.assertFalse(os.path.isfile(outfile), "Expected dropping database on empty result.")
        self.assertTrue(progress_calls, "Expected calls to progress().")
        progress_names = set(x["name"] for x in progress_calls if "name" in x)
        self.assertEqual(progress_names, set([next(iter(schema["table"]))]),
                         "Expected table name in progress calls.")
        self.assertIn(True, [x.get("done") for x in progress_calls],
                      "Expected done in progress calls.")

        progress_calls = []
        progress_result = True
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile, progress).configure(data=True)
        result = sink.export_entities(schema)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, schema, {k: DATA[k] for k in schema["table"]})
        self.assertTrue(progress_calls, "Expected calls to progress().")
        progress_names = set(x["name"] for x in progress_calls if "name" in x)
        self.assertEqual(progress_names, set(SCHEMA["table"]),
                         "Expected table names in progress calls.")
        self.assertIn(True, [x.get("done") for x in progress_calls],
                      "Expected done in progress calls.")


    def verify_export_entities_error(self):
        """Verifies export_entities() with raised error."""
        def progress(**kwargs):
            raise Exception("fatal error")

        logger.info("Verifying export_entities() with raised error.")
        outfile = self.mktemp(".db")
        schema = {"table": list(SCHEMA["table"])}
        sink = importexport.DatabaseSink(self._db, outfile, progress).configure(data=True)
        result = sink.export_entities(schema)
        self.assertEqual(result, False, "Unexpected success from export_entities() on error.")
        self.assertFalse(os.path.isfile(outfile), "Expected no output file on error.")


    def verify_export_entities_renames(self):
        """Verifies DatabaseSink.export_entities(renames=..)."""
        logger.info("Verifying export_entities() with renames.")
        outfile = self.mktemp(".db")
        renames = {c: {n: "%s_renamed" % n for n in nn} for c, nn in SCHEMA.items()}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, renames)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, DATA, renames)

        logger.info("Verifying export_entities() with cased renames.")
        outfile = self.mktemp(".db")
        renames = {c: {n.upper(): "%s_renamed" % n for n in nn} for c, nn in SCHEMA.items()}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, renames)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, DATA, renames)

        logger.info("Verifying export_entities() with whitespaced renames.")
        outfile = self.mktemp(".db")
        counter = itertools.count()
        renames = {c: {n: " " * next(counter) for n in nn} for c, nn in SCHEMA.items()}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, renames)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, DATA, renames)


    def verify_export_entities_selects(self):
        """Verifies DatabaseSink.export_entities(selects=..)."""
        COL = lambda c: ("{0} * {0}" if c != "value" else "{0}").format(grammar.quote(c))

        logger.info("Verifying export_entities() with selects.")
        outfile = self.mktemp(".db")
        selects = {n: "SELECT %s FROM %s" % (", ".join(COL(c) for c in COLUMNS[n]), grammar.quote(n))
                   for n in DATA} # Provide SELECTs returning all numeric values as power of 2
        data = {n: [{k: v**2 if isinstance(v, int) else v for k, v in r.items()} for r in rr]
                for n, rr in DATA.items()}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, selects=selects)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, data)

        logger.info("Verifying export_entities() with blank selects.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, selects={})
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, DATA)

        logger.info("Verifying export_entities() with invalid selects.")
        outfile = self.mktemp(".db")
        selects = {n: "SELECT something totally invalid" for n in DATA}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, selects=selects)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, {n: [] for n in selects})


    def verify_export_entities_iterables(self):
        """Verifies DatabaseSink.export_entities(iterables=..)."""
        COL = lambda c: ("{0} * {0}" if c != "value" else "{0}").format(grammar.quote(c))

        logger.info("Verifying export_entities() with iterables.")
        outfile = self.mktemp(".db")
        iterables = {"related": [{k: (v ** 2 if isinstance(v, int) else v) for k, v in x.items()}
                                 for x in DATA["related"]]}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, iterables=iterables)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        data_expected = {k: (iterables[k] if "related" == k else v) for k, v in DATA.items()}
        self.validate_database(outfile, SCHEMA, data_expected)

        logger.info("Verifying export_entities() with iterables and selects.")
        outfile = self.mktemp(".db")
        selects = {n: "SELECT %s FROM %s" % (", ".join(COL(c) for c in COLUMNS[n]), grammar.quote(n))
                   for n in DATA if n != "related"}
        iterables = {"related": [{k: (v ** 2 if isinstance(v, int) else v) for k, v in x.items()}
                                 for x in DATA["related"]]}
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA, selects=selects, iterables=iterables)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        data_expected = {n: [{k: (v ** 2 if isinstance(v, int) else v) for k, v in x.items()}
                             for x in vv] for n, vv in DATA.items()}
        self.validate_database(outfile, SCHEMA, data_expected)


    def verify_export_entities_existing(self):
        """Verifies DatabaseSink.export_entities() for existing database or entities."""
        logger.info("Verifying export_entities() into existing database.")
        outfile = self.mktemp(".db")
        populate_database(outfile, SCHEMA, COLUMNS, DATA)
        with sqlite3.connect(outfile) as sqldb:
            for table in SCHEMA["table"]:
                sqldb.execute("UPDATE %s SET id = id + 1" % grammar.quote(table))
            sqldb.execute("CREATE TABLE extra (id, value)")
            sqldb.execute("INSERT INTO extra VALUES (1, NULL)")

        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        schema_expected = copy.deepcopy(SCHEMA)
        schema_expected["table"]["extra"] = "CREATE TABLE extra (id, value)"
        data_expected = dict(DATA, extra=[{"id": 1, "value": None}])
        self.validate_database(outfile, schema_expected, data_expected)

        logger.info("Verifying export_entities() into same database.")
        infile = outfile = self.mktemp(".db")
        populate_database(infile, SCHEMA, COLUMNS, DATA)
        db = database.Database(infile, parse=True)
        db.execute("CREATE TABLE extra (id, value)")
        db.execute("INSERT INTO extra VALUES (1, NULL)")

        schema = copy.deepcopy(SCHEMA)
        schema.pop("trigger") # Skip creating triggers for renamed tables
        renames = {c: {n: "%s_renamed" % n for n in nn} for c, nn in schema.items()}
        sink = importexport.DatabaseSink(db, outfile).configure(data=True)
        result = sink.export_entities(schema, renames)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        schema_expected = {c: list(SCHEMA[c]) for c in SCHEMA}
        for category, mapping in renames.items():
            schema_expected[category] += list(mapping.values())
        schema_expected["table"].append("extra")
        data_expected = dict(DATA, **{"%s_renamed" % k: v for k, v in DATA.items()})
        data_expected["extra"] = [{"id": 1, "value": None}]
        self.validate_database(outfile, schema_expected, data_expected)
        self.assertIn("empty_renamed", db.schema["table"], "Expected db.schema to be updated.")


    def verify_export_entities_configure(self):
        """Verifies DatabaseSink.configure(..).export_entities()."""
        logger.info("Verifying export_entities() with configure(allow_empty=False).")

        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(allow_empty=False, data=True)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        schema_expected = {c: [n for n in nn if "empty" not in n] for c, nn in SCHEMA.items()}
        data_expected = {n: rows for n, rows in DATA.items() if "empty" != n}
        self.validate_database(outfile, schema_expected, data_expected)

        logger.info("Verifying export_entities() with configure(limit=..).")
        for limit, from_to in [(5, (0, 5)), (10, (0, 10)), ((5, 5), (5, 10)), ((10, ROWCOUNT), (0, 0))]:
            outfile = self.mktemp(".db")
            sink = importexport.DatabaseSink(self._db, outfile).configure(data=True, limit=limit)
            result = sink.export_entities(SCHEMA)
            self.assertTrue(result, "Unexpected failure from export_entities().")
            data_expected = {n: rows[from_to[0]:from_to[1]] for n, rows in DATA.items()}
            self.validate_database(outfile, SCHEMA, data_expected)

        logger.info("Verifying export_entities() with configure(maxcount=..).")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True, maxcount=8)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        counter = itertools.count()
        data_expected = {n: [r for r in rows if next(counter) < 8] for n, rows in DATA.items()}
        if "myview" in data_expected: data_expected["myview"] = data_expected["parent"]
        self.validate_database(outfile, SCHEMA, data_expected)

        logger.info("Verifying export_entities() with configure(limit=.., maxcount=..).")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True, limit=5, maxcount=8)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        counter = itertools.count()
        data_expected = {n: [r for r in rows[:5] if next(counter) < 8] for n, rows in DATA.items()}
        if "myview" in data_expected: data_expected["myview"] = data_expected["parent"]
        self.validate_database(outfile, SCHEMA, data_expected)

        logger.info("Verifying export_entities() with configure(reverse=True).")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(data=True, reverse=True)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        data_expected = {n: rows[::-1] for n, rows in DATA.items()}
        if "myview" in data_expected: data_expected["myview"] = data_expected["parent"]
        self.validate_database(outfile, SCHEMA, data_expected)

        logger.info("Verifying export_entities() with configure(allow_empty=False, data=False).")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(allow_empty=True, data=False)
        result = sink.export_entities(SCHEMA)
        self.assertTrue(result, "Unexpected failure from export_entities().")
        self.validate_database(outfile, SCHEMA, {n: [] for n in DATA})


    def verify_export_entities_fks(self):
        """Verifies DatabaseSink.export_entities() restoring foreign_keys PRAGMA."""
        logger.info("Verifying export_entities() restoring foreign keys PRAGMA.")
        self._db.execute("PRAGMA foreign_keys = on")
        try:
            outfile = self.mktemp(".db")
            sink = importexport.DatabaseSink(self._db, outfile).configure(data=True)
            result = sink.export_entities(SCHEMA)
            self.assertTrue(result, "Unexpected failure from export_entities().")
            self.assertTrue(self._db.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"],
                            "Expected PRAGMA foreign_keys to be restored after export.")
            self.validate_database(outfile, SCHEMA, DATA)
        finally:
            self._db.execute("PRAGMA foreign_keys = off")


    def verify_export_query(self):
        """Verifies DatabaseSink.export_query()."""
        logger.info("Verifying export_query() with simple queries.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile)
        schema_expected, data_expected = {"table": []}, {}
        for table, rows in DATA.items():
            query = "SELECT * FROM %s ORDER BY ID desc" % grammar.quote(table)
            result = sink.export_query(table, query)
            self.assertTrue(result, "Unexpected failure from export_query().")
            schema_expected["table"].append(table)
            data_expected[table] = rows[::-1]
            self.validate_database(outfile, schema_expected, data_expected)

        logger.info("Verifying export_query() with PRAGMA query.")
        table, query = "pragma_table", "PRAGMA application_id"
        result = sink.export_query(table, query)
        self.assertTrue(result, "Unexpected failure from export_query().")
        schema_expected["table"].append(table)
        data_expected[table] = [{"application_id": 0}]
        self.validate_database(outfile, schema_expected, data_expected)

        logger.info("Verifying export_query() with action query.")
        table, query = "action_table", "UPDATE parent SET id = id"
        result = sink.export_query(table, query)
        self.assertTrue(result, "Unexpected failure from export_query().")
        schema_expected["table"].append(table)
        data_expected[table] = [{"rowcount": len(DATA["parent"])}]
        self.validate_database(outfile, schema_expected, data_expected)


    def verify_export_query_params(self):
        """Verifies DatabaseSink.export_query(params=..)."""
        logger.info("Verifying export_query() with parameters.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile)
        schema_expected, data_expected = {"table": []}, {}
        for table in DATA:
            query, params = "SELECT * FROM %s WHERE id = ?" % grammar.quote(table), [1]
            result = sink.export_query(table, query, params)
            self.assertTrue(result, "Unexpected failure from export_query().")
            schema_expected["table"].append(table)
            data_expected[table] = [x for x in DATA[table] if x["id"] == 1]
            self.validate_database(outfile, schema_expected, data_expected)


    def verify_export_query_cursor(self):
        """Verifies DatabaseSink.export_query(cursor=..)."""
        logger.info("Verifying export_query() with cursor.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile)
        schema_expected, data_expected = {"table": []}, {}
        for table, rows in DATA.items():
            if table not in SCHEMA["table"]: continue # for
            colstr = ", ".join(("10 - %s AS %s" % (c, c)) if "id"== c else c for c in COLUMNS[table])
            cursor_query = "SELECT %s FROM %s" % (colstr, grammar.quote(table))
            query = "SELECT * FROM %s" % grammar.quote(table)
            cursor = self._db.execute(cursor_query)
            result = sink.export_query(table, query, cursor=cursor)
            self.assertTrue(result, "Unexpected failure from export_query().")
            schema_expected["table"].append(table)
            data_expected[table] = [{k: (10 - v if "id" == k else v)
                                    for k, v in r.items()} for r in rows]
            self.validate_database(outfile, schema_expected, data_expected)


    def verify_export_query_create_sql(self):
        """Verifies DatabaseSink.export_query(create_sql=..)."""
        logger.info("Verifying export_query() with CREATE SQL.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile)
        schema_expected, data_expected = {"table": []}, {}
        for table, rows in DATA.items():
            if table not in SCHEMA["table"]: continue # for
            colstr = ", ".join(COLUMNS[table]) + ", extra1, extra2"
            create_sql = "CREATE TABLE %s (%s)" % (grammar.quote(table), colstr)
            query = "SELECT * FROM %s" % grammar.quote(table)
            result = sink.export_query(table, query, create_sql=create_sql)
            self.assertTrue(result, "Unexpected failure from export_query().")
            schema_expected["table"].append(table)
            data_expected[table] = [dict(x, extra1=None, extra2=None) for x in rows]
            self.validate_database(outfile, schema_expected, data_expected)

        logger.info("Verifying export_query() with CREATE SQL and whitespaced columns.")
        table = "parent"
        outfile = self.mktemp(".db")
        colstr = ", ".join(grammar.quote(" " * i) for i, _ in enumerate(COLUMNS[table]))
        create_sql = "CREATE TABLE %s (%s)" % (grammar.quote(table), colstr)
        query = "SELECT * FROM %s" % grammar.quote(table)
        sink = importexport.DatabaseSink(self._db, outfile)
        result = sink.export_query(table, query, create_sql=create_sql)
        schema_expected = {"table": {table: [" " * i for i, _ in enumerate(COLUMNS[table])]}}
        data_expected = {table: [{" " * i: r[c] for i, c in enumerate(COLUMNS[table])}
                         for r in DATA[table]]}
        self.validate_database(outfile, schema_expected, data_expected)


    def verify_export_query_configure(self):
        """Verifies DatabaseSink.configure(..).export_query()."""
        logger.info("Verifying export_query() with configure(allow_empty=False).")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(allow_empty=False)
        table = "empty"
        query = "SELECT * FROM %s" % grammar.quote(table)
        result = sink.export_query(table, query)
        self.assertFalse(result, "Unexpected success from export_query() for empty result.")
        self.assertFalse(os.path.isfile(outfile), "Expected dropping database on empty result.")

        logger.info("Verifying export_query() with configure(limit=..).")
        table = "parent"
        query = "SELECT * FROM %s" % grammar.quote(table)
        for limit, from_to in [(5, (0, 5)), ((5, 5), (5, 10)), ((10, ROWCOUNT), (0, 0))]:
            outfile = self.mktemp(".db")
            sink = importexport.DatabaseSink(self._db, outfile).configure(limit=limit)
            cursor = self._db.execute(query)
            result = sink.export_query(table, query, cursor=cursor)
            self.assertTrue(result, "Unexpected failure from export_query().")
            schema_expected = {"table": [table]}
            data_expected = {table: DATA[table][from_to[0]:from_to[1]]}
            self.validate_database(outfile, schema_expected, data_expected)

        logger.info("Verifying export_query() with configure(allow_empty=False, limit=..).")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile).configure(allow_empty=False, limit=0)
        cursor = self._db.execute(query)
        result = sink.export_query(table, query, cursor=cursor)
        self.assertFalse(result, "Unexpected success from export_query() for empty result.")
        self.assertFalse(os.path.isfile(outfile), "Expected dropping database on empty result.")


    def verify_export_query_invalid(self):
        """Verifies DatabaseSink.export_query() with invalid query."""
        logger.info("Verifying export_query() with invalid query.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile)
        result = sink.export_query("mytable", "this is totally not a query")
        self.assertFalse(result, "Unexpected success from export_query() for invalid query.")
        self.assertFalse(os.path.isfile(outfile), "Expected dropping database on error.")


    def verify_export_query_progress(self):
        """Verifies DatabaseSink(progress=..).export_query()."""
        progress_calls = []
        progress_result = False
        def progress(**kwargs):
            progress_calls.append(kwargs)
            return progress_result

        logger.info("Verifying export_query() with progress callback.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile, progress)
        table = "parent"
        query = "SELECT * FROM %s" % grammar.quote(table)
        result = sink.export_query(table, query)
        self.assertTrue(progress_calls, "Expected calls to progress().")
        self.assertIn(table, [x.get("name") for x in progress_calls],
                      "Expected table name in progress calls.")
        self.assertIn(True, [x.get("done") for x in progress_calls],
                      "Expected done in progress calls.")
        self.assertFalse(result, "Unexpected success from export_query() on cancel.")
        self.assertFalse(os.path.isfile(outfile), "Expected dropping database on cancel.")

        progress_result = True
        result = sink.export_query(table, query)
        self.assertTrue(progress_calls, "Expected calls to progress().")
        self.assertIn(table, [x.get("name") for x in progress_calls],
                      "Expected table name in progress calls.")
        self.assertIn(True, [x.get("done") for x in progress_calls],
                      "Expected done in progress calls.")
        self.assertTrue(result, "Unexpected failure from export_query().")
        schema_expected = {"table": [table]}
        data_expected = {table: DATA[table]}
        self.validate_database(outfile, schema_expected, data_expected)


    def verify_export_query_error(self):
        """Verifies export_query() with raised error."""
        def progress(**kwargs):
            raise Exception("fatal error")

        logger.info("Verifying export_query() with raised error.")
        outfile = self.mktemp(".db")
        sink = importexport.DatabaseSink(self._db, outfile, progress)
        table = "parent"
        query = "SELECT * FROM %s" % grammar.quote(table)
        result = sink.export_query(table, query)
        self.assertEqual(result, False, "Unexpected success from export_query() on error.")
        self.assertFalse(os.path.isfile(outfile), "Expected no output file on error.")


    def validate_database(self, filename, schema, data, renames=None):
        """
        Validates given database having expected schema and data.

        @param   filename  path to database file
        @param   schema    {category: [name, ]}
        @param   data      {name: [{col1: ..}]}
        @param   renames   {category: {name1: name2}}
        """
        renames = renames or {}
        for category, mapping in list(renames.items()):
            renames[category] = {k.lower(): v for k, v in mapping.items()}
        self.assertTrue(os.path.isfile(filename), "Expected database file to exist.")
        self.assertTrue(os.path.getsize(filename), "Expected database file to have content.")
        with sqlite3.connect(filename) as sqldb:
            sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
            self.validate_schema(sqldb, schema, renames)
            for name, expected in data.items():
                category = "table" if name in schema["table"] else "view"
                name2 = renames.get(category, {}).get(name.lower(), name)
                received = sqldb.execute("SELECT * FROM %s" % grammar.quote(name2)).fetchall()
                self.assertEqual(received, expected, "Unexpected data in output database.")


    def validate_schema(self, connection, schema, renames):
        """
        @param   connection  sqlite3.Connection
        @param   schema      {category: [name, ]}
        @param   renames     {category: {name1: name2}}
        """
        expected = {k: set(v.lower() for v in vv) for k, vv in schema.items()}
        for k, v in list(expected.items()):
            if not v: expected.pop(k)
        for category, mapping in (renames or {}).items():
            mapping = {k.lower(): v.lower() for k, v in mapping.items()}
            if category in expected and set(mapping) & set(expected[category]):
                expected[category] = {mapping.get(n, n) for n in expected[category]}
        received = {}
        for category in database.Database.CATEGORIES:
            names = list_database(connection, category)
            if names: received[category] = set(x.lower() for x in names)
        self.assertEqual(received, expected, "Unexpected schema in output database.")


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
