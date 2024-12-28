#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests importexport.InfoSink.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     13.09.2024
@modified    28.12.2024
------------------------------------------------------------------------------
"""
import contextlib
import io
import logging
import os
try: import Queue as queue        # Py2
except ImportError: import queue  # Py3
import sqlite3
import sys
import unittest

try: import wx
except ImportError: wx = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import conf, database, importexport, scheme, workers
if wx:
    from sqlitely.lib import controls

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test.common import COLUMNS, SCHEMA, DATA, STATS_FORMATS
from test.common import FileTest, list_database, populate_database


logger = logging.getLogger()


class TestInfoSink(FileTest):
    """Unit-tests InfoSink public API."""


    def __init__(self, *args, **kwargs):
        super(TestInfoSink, self).__init__(*args, **kwargs)
        self._db = None   # database.Database instance


    def setUp(self):
        """Populates test database."""
        super(TestInfoSink, self).setUp()
        infile = self.mktemp(".db")
        populate_database(infile, SCHEMA, COLUMNS, DATA)
        self._db = database.Database(infile, parse=True)
        self._db.populate_schema(count=True)


    def tearDown(self):
        """Deletes temoorary files."""
        try: self._db.close()
        except Exception: pass
        super(TestInfoSink, self).tearDown()


    def test_write_sql(self):
        """Verifies InfoSink SQL export."""
        logger.info("Verifying InfoSink.write_sql().")
        outfile = self.mktemp(".sql")
        sql = "SELECT * FROM sqlite_master"
        for headers in (None, "singular", ["multi", "line"]):
            sink = importexport.InfoSink(self._db, outfile)
            result = sink.write_sql(sql, headers)
            self.assertTrue(result, "Unexpected failure from write_sql().")
            self.assertTrue(os.path.isfile(outfile), "Expected output file.")
            self.assertTrue(os.path.getsize(outfile), "Expected output file to have content.")
            with io.open(outfile, encoding="utf-8") as f:
                content = f.read()
            self.assertIn(sql, content, "Expected content in output file: %r." % sql)
            if headers:
                for header in (x for x in (headers if isinstance(headers, list) else [headers])):
                    self.assertIn(header, content, "Expected header in output file: %r." % header)


    def test_write_statistics(self):
        """Verifies InfoSink statistics export."""
        logger.info("Verifying InfoSink.write_statistics().")
        stats, diagram = self.make_statistics(), self.make_diagram()
        for fmt in STATS_FORMATS:
            self.verify_write_statistics(fmt, stats, diagram)
        outfile = self.mktemp(".sql")
        with self.assertRaises(Exception, msg="Expected error on unsupported format."):
            importexport.InfoSink(self._db, outfile).write_statistics("xlsx", stats, diagram)


    def verify_write_statistics(self, fmt, stats=None, diagram=None):
        """Verifies statistics output for given format."""
        logger.info("Verifying InfoSink.write_statistics() for %s.", fmt.upper())
        outfile = self.mktemp("." + fmt)
        sink = importexport.InfoSink(self._db, outfile)

        result = sink.write_statistics(fmt, stats, diagram)
        self.assertTrue(result, "Unexpected failure from write_statistics().")
        self.assertTrue(os.path.isfile(outfile), "Expected output file.")
        self.assertTrue(os.path.getsize(outfile), "Expected output file to have content.")
        with io.open(outfile, encoding="utf-8") as f:
            content = f.read()
        self.assertIn(self._db.filename, content, "Expected database filename in output.")
        for category, names in SCHEMA.items():
            if "sql" == fmt and ("table" != category or not stats): continue # for
            for name in names:
                self.assertIn(name, content, "Expected entity in output file: %r." % name)
        if "html" == fmt and diagram:
            self.assertIn(diagram["svg"], content, "Expected schema diagram in output.")
        if "sql" == fmt and stats:
            with contextlib.closing(sqlite3.connect(self.mktemp(".db"))) as sqldb:
                sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                sqldb.executescript(content)
                tables = list_database(sqldb)
                self.assertIn("space_used", tables, "Expected statistics table in SQL output.")


    def make_statistics(self):
        """Returns statistics structure for export, or None if not available."""
        logger.debug("Running statistics analysis on database.")
        results = queue.Queue()
        worker = workers.AnalyzerThread(results.put)
        worker.work(self._db.filename)
        stats = next((x["data"] for x in [results.get()] if "data" in x), None)
        if stats: self._db.set_sizes(stats)
        return stats


    def make_diagram(self):
        """Returns schema diagram structure for export, or None if not available."""
        if not wx: return None
        _ = wx.App()
        controls.Patch.patch_wx()
        layout = scheme.SchemaDiagram(self._db)
        layout.SetFonts("Verdana",
                        ("Open Sans", conf.FontDiagramSize,
                         conf.FontDiagramFile, conf.FontDiagramBoldFile))
        layout.Populate({"stats": True})
        layout.Redraw(scheme.Rect(0, 0, *conf.WindowSize), scheme.LayoutStyle.GRID)
        bmp = layout.MakeBitmap() 
        svg = layout.MakeTemplate("SVG", embed=True)
        return {"bmp": bmp, "svg": svg}


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
