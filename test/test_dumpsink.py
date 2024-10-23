#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests importexport.DumpSink.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     13.09.2024
@modified    17.09.2024
------------------------------------------------------------------------------
"""
import io
import itertools
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import database, importexport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test.common import ROWCOUNT, COLUMNS, SCHEMA, DATA
from test.common import FileTest, populate_database, validate_data_sql


logger = logging.getLogger()


class TestDumpSink(FileTest):
    """Unit-tests DumpSink public API."""


    def __init__(self, *args, **kwargs):
        super(TestDumpSink, self).__init__(*args, **kwargs)
        self._db = None   # database.Database instance


    def setUp(self):
        """Populates test database."""
        super(TestDumpSink, self).setUp()
        infile = self.mktemp(".db")
        populate_database(infile, SCHEMA, COLUMNS, DATA)
        self._db = database.Database(infile, parse=True)
        self._db.populate_schema(count=True)


    def tearDown(self):
        """Deletes temoorary files."""
        try: self._db.close()
        except Exception: pass
        super(TestDumpSink, self).tearDown()


    def test_dump(self):
        """Verifies DumpSink."""
        logger.info("Verifying DumpSink.")

        partial_schema = {c: [n for n in nn if "view" == c or "empty" in n or "parent" in n]
                          for c, nn in SCHEMA.items()}

        self.verify_dump_database()
        self.verify_dump_database(info={"info_title": "info_text"})
        self.verify_dump_database(info={"info_title": {"info_label": "info_text"}})
        self.verify_dump_database(data=True)
        self.verify_dump_database(data=True, allow_empty=False)
        self.verify_dump_database(data=True, schema=partial_schema)
        self.verify_dump_database(data=True, limit=0)
        self.verify_dump_database(data=True, limit=ROWCOUNT)
        self.verify_dump_database(data=True, limit=5)
        self.verify_dump_database(data=True, limit=(5, 5))
        self.verify_dump_database(data=True, limit=(5, 5))
        self.verify_dump_database(data=True, limit=(ROWCOUNT, ROWCOUNT))
        self.verify_dump_database(data=True, maxcount=5)
        self.verify_dump_database(data=True, limit=5, maxcount=8)
        self.verify_dump_database(data=True, pragma=False)
        self.verify_dump_database(data=True, reverse=True)
        self.verify_dump_database_progress()
        self.verify_dump_database_error()

    
    def verify_dump_database(self, schema=None, info=None, data=None, allow_empty=None,
                             limit=None, maxcount=None, pragma=None, reverse=None):
        """Verifies DumpSink.dump_database()."""
        config = dict(data=data, allow_empty=allow_empty, limit=limit, maxcount=maxcount,
                      pragma=pragma, reverse=reverse)
        for k, v in list(config.items()):
            if v is None: config.pop(k)
        argstr, configstr = "", ""
        if config:
            configstr = "configure(%s)." % ", ".join("%s=%s" % kv for kv in config.items())
        if schema: argstr += "schema=.."
        if info:   argstr += "%sinfo=.." % (", " if argstr else "")
        label = "%sdump_database(%s)" % (configstr, argstr)

        logger.info("Verifying DumpSink.%sdump_database(%s).", configstr, argstr)
        outfile = self.mktemp(".sql")
        sink = importexport.DumpSink(self._db, outfile).configure(**config)
        result = sink.dump_database(schema, info)
        self.assertTrue(result, "Unexpected failure from %s." % label)
        self.assertTrue(os.path.isfile(outfile), "Expected output file from %s." % label)
        self.assertTrue(os.path.getsize(outfile), "Expected output content from %s." % label)
        self.validate_dump(outfile, label, schema, info, **config)


    def verify_dump_database_progress(self):
        """Verifies DumpSink.dump_database() with progress callback."""

        progress_calls = []
        progress_result = False
        def progress(**kwargs):
            progress_calls.append(kwargs)
            return progress_result

        logger.info("Verifying DumpSink().dump_database() with progress callback.")
        for progress_result in (False, True):
            outfile = self.mktemp(".sql")
            sink = importexport.DumpSink(self._db, outfile, progress).configure(data=True)
            result = sink.dump_database()
            if progress_result:
                self.assertTrue(result, "Unexpected failure from dump.")
                self.assertTrue(os.path.isfile(outfile), "Expected output file from dump.")
                self.validate_dump(outfile, "dump_database()", data=True)
            else:
                self.assertEqual(result, None, "Unexpected success from dump on cancel.")
                self.assertFalse(os.path.isfile(outfile), "Expected no output file from dump on cancel.")


    def verify_dump_database_error(self):
        """Verifies DumpSink.dump_database() with raised error."""

        def progress(**kwargs):
            raise Exception("fatal error")

        logger.info("Verifying DumpSink().dump_database() with raised error.")
        outfile = self.mktemp(".sql")
        sink = importexport.DumpSink(self._db, outfile, progress).configure(data=True)
        result = sink.dump_database()
        self.assertEqual(result, False, "Unexpected success from dump on error.")
        self.assertFalse(os.path.isfile(outfile), "Expected no output file from dump on error.")


    def validate_dump(self, filename, label, schema=None, info=None, **config):
        """Validates results of DumpSink.dump_database()."""
        with io.open(filename, encoding="utf-8") as f:
            content = f.read()
        if config.get("pragma") is False:
            self.assertNotIn("PRAGMA ", content, "Expected no PRAGMAs from %s." %label)
        else:
            self.assertIn("PRAGMA ", content, "Expected PRAGMAs from %s." % label)
        infostrings = sum((list(v) + list(v.values()) if isinstance(v, dict) else [k, v]
                           for k, v in (info or {}).items()), [])
        for text in infostrings:
            self.assertIn(text, content, "Expected metadata texts from %s." % label)

        schema_expected, data_expected = self.collect_expecteds(schema, **config)
        validate_data_sql(self, content, data_expected, schema_expected)


    def collect_expecteds(self, schema=None, **config):
        """Returns {..expected schema by category..}, {..expected data by table..}."""
        schema_expected = schema or dict(SCHEMA)
        data_expected = {k: DATA[k] for c in self._db.DATA_CATEGORIES
                         for k in schema_expected.get(c, {}) if k in DATA}

        if config.get("allow_empty") is False:
            for category, names in list(schema_expected.items()):
                schema_expected[category] = [n for n in names if "empty" not in n]
                if not schema_expected[category]: schema_expected.pop(category)
            data_expected.pop("empty", None)

        if not config.get("data"):
            data_expected = {k: [] for k in data_expected}
        if config.get("reverse"):
            data_expected = {k: vv[::-1] for k, vv in data_expected.items()}
        if config.get("limit") not in (None, (), []) or config.get("maxcount") is not None:
            from_to = (0, sys.maxsize)
            limit, maxcount = config.get("limit"), config.get("maxcount", sys.maxsize)
            limit = limit if isinstance(limit, (list, tuple)) else () if limit is None else (limit, )
            if limit:
                from_to = (limit[1], limit[1] + limit[0]) if len(limit) > 1 else (0, limit[0])
            counter = itertools.count()
            data_expected = {n: [r for r in rows[from_to[0]:from_to[1]] if next(counter) < maxcount]
                             for n, rows in DATA.items() if n in data_expected}
        if "myview" in data_expected:
            data_expected["myview"] = data_expected["parent"]

        return schema_expected, data_expected


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
