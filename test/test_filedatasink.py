#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests importexport.FileDataSink.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     13.09.2024
@modified    17.09.2024
------------------------------------------------------------------------------
"""
import functools
import io
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import database, grammar, importexport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test.common import ROWCOUNT, COLUMNS, SCHEMA, DATA, EXPORT_FORMATS
from test.common import FileTest, populate_database, validate_data


logger = logging.getLogger()


class TestFileDataSink(FileTest):
    """Unit-tests FileDataSink public API."""


    def __init__(self, *args, **kwargs):
        super(TestFileDataSink, self).__init__(*args, **kwargs)
        self._db = None   # database.Database instance


    def setUp(self):
        """Populates test database."""
        super(TestFileDataSink, self).setUp()
        infile = self.mktemp(".db")
        populate_database(infile, SCHEMA, COLUMNS, DATA)
        self._db = database.Database(infile, parse=True)
        self._db.populate_schema(count=True)


    def tearDown(self):
        """Deletes temoorary files."""
        try: self._db.close()
        except Exception: pass
        super(TestFileDataSink, self).tearDown()


    def test_export_entity(self):
        """Verifies FileDataSink.export_entity()."""
        logger.info("Verifying FileDataSink.export_entity().")
        for fmt in EXPORT_FORMATS:
            self.verify_export_entity(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_entity_columns(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_entity_iterable(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_entity_configure(fmt)
        self.verify_export_entity_metainfo()
        self.verify_export_entity_progress()
        self.verify_export_entity_error()


    def test_export_combined(self):
        """Verifies FileDataSink.export_combined()."""
        logger.info("Verifying FileDataSink.export_combined().")
        for fmt in EXPORT_FORMATS:
            self.verify_export_combined(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_combined_category(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_combined_names(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_combined_iterables(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_combined_configure(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_combined_cased(fmt)
        self.verify_export_combined_metainfo()
        self.verify_export_combined_progress()
        self.verify_export_combined_error()


    def test_export_query(self):
        """Verifies FileDataSink.export_query()."""
        logger.info("Verifying FileDataSink.export_query().")
        for fmt in EXPORT_FORMATS:
            self.verify_export_query(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_query_columns(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_query_iterable(fmt)
        for fmt in EXPORT_FORMATS:
            self.verify_export_query_configure(fmt)
        self.verify_export_query_metainfo()
        self.verify_export_query_progress()
        self.verify_export_query_error()


    def verify_export_entity(self, fmt):
        """Verifies FileDataSink.export_entity() for given format."""
        logger.info("Verifying export_entity() for %s.", fmt.upper())
        for category, name in ((c, n) for c in self._db.DATA_CATEGORIES for n in SCHEMA[c]):
            make_iterable = lambda: self._db.execute("SELECT * FROM %s" % grammar.quote(name))
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_entity(category, name, make_iterable, "title", COLUMNS[name])
            self.assertTrue(result, "Unexpected failure from export_entity() for %s." % fmt.upper())
            validate_data(self, fmt, outfile, names=[name])



    def verify_export_entity_columns(self, fmt):
        """Verifies FileDataSink.export_entity() with custom columns for given format."""
        logger.info("Verifying export_entity() with constrained columns for %s.", fmt.upper())
        category, name = "table", "parent"
        for columns in (COLUMNS[name][:-1], [{"name": c} for c in COLUMNS[name][:-1]]):
            make_iterable = lambda: self._db.execute("SELECT * FROM %s" % grammar.quote(name))
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_entity(category, name, make_iterable, "title", columns)
            self.assertTrue(result, "Unexpected failure from export_entity(columns=%s) for %s." %
                            (columns, fmt.upper()))
            validate_data(self, fmt, outfile, names=[name], columns=columns)


    def verify_export_entity_iterable(self, fmt):
        """Verifies FileDataSink.export_entity() with custom iterable."""
        logger.info("Verifying export_entity() with custom iterable for %s.", fmt.upper())
        for category, name in ((c, n) for c in self._db.DATA_CATEGORIES for n in SCHEMA[c]):
            colstr = ", ".join(("10 - %s AS %s" % (c, c)) if "id"== c else c for c in COLUMNS[name])
            make_iterable = lambda: self._db.execute("SELECT %s FROM %s" %
                                                     (colstr, grammar.quote(name)))
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_entity(category, name, make_iterable, "title", COLUMNS[name])
            self.assertTrue(result, "Unexpected failure from export_entity() for %s." % fmt.upper())
            rows_expected = [{k: (10 - v if "id" == k else v) for k, v in r.items()} for r in DATA[name]]
            validate_data(self, fmt, outfile, names=[name], data_expected={name: rows_expected})


    def verify_export_entity_configure(self, fmt):
        """Verifies FileDataSink.configure(..)export_entity()."""
        logger.info("Verifying export_entity() configuration for %s.", fmt.upper())
        category, name = "table", "parent"
        make_iterable = lambda: self._db.execute("SELECT * FROM %s" % grammar.quote(name))

        for limit in (5, (10, ), (5, 5), (10, ROWCOUNT)):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt).configure(limit=limit)
            result = sink.export_entity(category, name, make_iterable, "title", COLUMNS[name])
            self.assertTrue(result, "Unexpected failure from export_entity() for %s." % fmt.upper())
            validate_data(self, fmt, outfile, names=[name], limit=limit)

        limit, maxcount = 5, 3
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, maxcount=maxcount)
        result = sink.export_entity(category, name, make_iterable, "title", COLUMNS[name])
        self.assertTrue(result, "Unexpected failure from export_entity() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, names=[name], limit=limit, maxcount=maxcount)

        limit, allow_empty = 0, False
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, allow_empty=allow_empty)
        result = sink.export_entity(category, name, make_iterable, "title", COLUMNS[name])
        self.assertTrue(result, "Unexpected failure from export_entity() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, names=[name], limit=limit, allow_empty=allow_empty)


    def verify_export_entity_metainfo(self):
        """Verifies FileDataSink.export_entity(title=.., info=..)."""
        logger.info("Verifying export_entity(title=.., info=..).")
        fmt = "txt"
        category, name = "table", "parent"
        make_iterable = lambda: self._db.execute("SELECT * FROM %s" % grammar.quote(name))
        title = "Export %s %s" % (category, grammar.quote(name, force=True))
        for info in ({"info_label": "info_text"}, {"info_title": {"info_label": "info_text"}}):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_entity(category, name, make_iterable, title, COLUMNS[name], info)
            self.assertTrue(result, "Unexpected failure from export_entity(info=%r)." % info)
            with io.open(outfile, encoding="utf-8") as f: content = f.read()
            infostrings = sum((list(v) + list(v.values()) if isinstance(v, dict) else [k, v]
                               for k, v in (info or {}).items()), [])
            for text in infostrings:
                self.assertIn(text, content, "Expected info %r in output." % info)
            self.assertIn(title, content, "Expected title %r in output." % title)
            validate_data(self, fmt, outfile, names=[name])
        for title in ("single_title", ["multi_title1", "multi_title2"]):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_entity(category, name, make_iterable, title, COLUMNS[name], info)
            self.assertTrue(result, "Unexpected failure from export_entity(title=%r)." % title)
            with io.open(outfile, encoding="utf-8") as f: content = f.read()
            for text in (title if isinstance(title, list) else [title]):
                self.assertIn(text, content, "Expected title %r in output." % title)
            validate_data(self, fmt, outfile, names=[name])


    def verify_export_entity_progress(self):
        """Verifies FileDataSink.export_entity() with progress callback."""
        logger.info("Verifying export_entity() with progress callback.")

        progress_calls = []
        progress_result = False
        def progress(**kwargs):
            progress_calls.append(kwargs)
            return progress_result or len(progress_calls) < 2

        fmt = "json"
        category, name = "table", "parent"
        make_iterable = lambda: self._db.execute("SELECT * FROM %s" % grammar.quote(name))
        for progress_result in (False, True):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt, progress)
            result = sink.export_entity(category, name, make_iterable, "title", COLUMNS[name])
            self.assertTrue(progress_calls, "Expected calls to progress()")
            if progress_result:
                self.assertTrue(result, "Unexpected failure from export_entity().")
                self.assertIn(name, [x.get("name") for x in progress_calls],
                              "Expected table name in progress calls.")
                self.assertIn("count", sum(map(list, progress_calls), []),
                              "Expected count in progress calls.")
                validate_data(self, fmt, outfile, names=[name])
            else:
                self.assertEqual(result, None, "Unexpected success from export_entity() on cancel.")
                self.assertFalse(os.path.isfile(outfile),
                                 "Expected no output file from export_entity() on cancel.")


    def verify_export_entity_error(self):
        """Verifies FileDataSink.export_entity() with raised error."""
        logger.info("Verifying export_entity() with raised error.")

        def progress(**kwargs):
            raise Exception("fatal error")

        fmt = "json"
        category, name = "table", "parent"
        make_iterable = lambda: self._db.execute("SELECT * FROM %s" % grammar.quote(name))
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt, progress)
        result = sink.export_entity(category, name, make_iterable, "title", COLUMNS[name])
        self.assertEqual(result, False, "Unexpected success from export_entity() on error.")
        self.assertFalse(os.path.isfile(outfile), "Expected no output file on error.")


    def verify_export_combined(self, fmt):
        """Verifies FileDataSink.export_combined() for given format."""
        logger.info("Verifying export_combined() for %s.", fmt.upper())
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        result = sink.export_combined("title")
        self.assertTrue(result, "Unexpected failure from export_combined() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, combined=True)


    def verify_export_combined_category(self, fmt):
        """Verifies FileDataSink.export_combined(category=..) for given format."""
        logger.info("Verifying export_combined(category=..) for %s.", fmt.upper())
        for category in ("table", "view"):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_combined("title", category)
            self.assertTrue(result, "Unexpected failure from export_combined(category=%r) for %s." %
                                    (category, fmt.upper()))
            validate_data(self, fmt, outfile, names=list(SCHEMA[category]), combined=True)


    def verify_export_combined_names(self, fmt):
        """Verifies FileDataSink.export_combined(names=..) for given format."""
        logger.info("Verifying export_combined(names=..) for %s.", fmt.upper())
        for names in (list(COLUMNS), list(COLUMNS)[2:], list(COLUMNS)[-1:]):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_combined("title", names=names)
            self.assertTrue(result, "Unexpected failure from export_combined(names=%r) for %s." %
                                    (names, fmt.upper()))
            validate_data(self, fmt, outfile, names=names, combined=True)


    def verify_export_combined_iterables(self, fmt):
        """Verifies FileDataSink.export_combined(make_iterables=..) for given format."""
        def make_iterables():
            for category, name in ((c, n) for c in self._db.DATA_CATEGORIES for n in SCHEMA[c]):
                sql = "SELECT * FROM %s ORDER BY id DESC" % grammar.quote(name)
                callback = functools.partial(self._db.execute, sql)
                yield dict(name=name, type=category, title=name, columns=COLUMNS[name]), callback
                
        logger.info("Verifying export_combined(make_iterables=..) for %s.", fmt.upper())
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        result = sink.export_combined("title", make_iterables=make_iterables)
        self.assertTrue(result, "Unexpected failure from export_combined(make_iterables=..) "
                                "for %s." % fmt.upper())
        validate_data(self, fmt, outfile, reverse=True, combined=True)


    def verify_export_combined_configure(self, fmt):
        """Verifies FileDataSink.configure(..)export_combined()."""
        logger.info("Verifying export_combined() configuration for %s.", fmt.upper())

        for limit in (5, (10, ), (5, 5), (10, ROWCOUNT)):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt).configure(limit=limit)
            result = sink.export_combined("title")
            self.assertTrue(result, "Unexpected failure from export_combined() for %s." % fmt.upper())
            validate_data(self, fmt, outfile, limit=limit, combined=True)

        limit, maxcount = 5, 8
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, maxcount=maxcount)
        result = sink.export_combined("title")
        self.assertTrue(result, "Unexpected failure from export_combined() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, limit=limit, maxcount=maxcount, combined=True)

        limit, allow_empty = 0, False
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, allow_empty=allow_empty)
        result = sink.export_combined("title")
        self.assertTrue(result, "Unexpected failure from export_combined() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, limit=limit, allow_empty=allow_empty, combined=True)

        limit, maxcount, allow_empty = 0, ROWCOUNT - 1, False
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, maxcount=maxcount, allow_empty=allow_empty)
        result = sink.export_combined("title")
        self.assertTrue(result, "Unexpected failure from export_combined() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, limit=limit, maxcount=maxcount, allow_empty=allow_empty,
                      combined=True)

        reverse = True
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(reverse=reverse)
        result = sink.export_combined("title")
        self.assertTrue(result, "Unexpected failure from export_combined() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, reverse=reverse, combined=True)

        def make_iterables():
            for category, name in ((c, n) for c in self._db.DATA_CATEGORIES for n in SCHEMA[c]):
                sql = "SELECT * FROM %s ORDER BY id DESC" % grammar.quote(name)
                callback = functools.partial(self._db.execute, sql)
                yield dict(name=name, type=category, title=name, columns=COLUMNS[name]), callback

        limit, maxcount = 5, 8
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, maxcount=maxcount)
        result = sink.export_combined("title", make_iterables=make_iterables)
        self.assertTrue(result, "Unexpected failure from export_combined() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, limit=limit, maxcount=maxcount, reverse=True,
                      combined=True)


    def verify_export_combined_cased(self, fmt):
        """Verifies FileDataSink.export_combined() for given format."""
        logger.info("Verifying export_combined(names=..) with cased selection for %s.", fmt.upper())
        names = [x.upper() for x in COLUMNS]
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        result = sink.export_combined("title", names=names)
        self.assertTrue(result, "Unexpected failure from export_combined(names=%r) for %s." %
                                (names, fmt.upper()))
        validate_data(self, fmt, outfile, combined=True)


    def verify_export_combined_metainfo(self):
        """Verifies FileDataSink.export_combined(title=.., info=..)."""
        logger.info("Verifying export_combined(title=.., info=..).")
        fmt = "html"
        title = "Export from %s" % self._db.filename
        for info in ({"info_label": "info_text"}, {"info_title": {"info_label": "info_text"}}):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_combined(title, info=info)
            self.assertTrue(result, "Unexpected failure from export_combined(info=%r)." % info)
            with io.open(outfile, encoding="utf-8") as f: content = f.read()
            infostrings = sum((list(v) + list(v.values()) if isinstance(v, dict) else [k, v]
                               for k, v in (info or {}).items()), [])
            for text in infostrings:
                self.assertIn(text, content, "Expected info %r in output." % info)
                self.assertIn(title, content, "Expected title %r in output." % title)
            validate_data(self, fmt, outfile, combined=True)
        for title in ("single_title", ["multi_title1", "multi_title2"]):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_combined(title, info=info)
            self.assertTrue(result, "Unexpected failure from export_combined(info=%r)." % info)
            with io.open(outfile, encoding="utf-8") as f: content = f.read()
            for text in (title if isinstance(title, list) else [title]):
                self.assertIn(text, content, "Expected title %r in output." % title)
            validate_data(self, fmt, outfile, combined=True)


    def verify_export_combined_progress(self):
        """Verifies FileDataSink.export_combined() with progress callback."""
        logger.info("Verifying export_combined() with progress callback.")

        progress_calls = []
        progress_result = False
        def progress(**kwargs):
            progress_calls.append(kwargs)
            return progress_result or len(progress_calls) < 2

        fmt = "json"
        for progress_result in (False, True):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt, progress)
            result = sink.export_combined("title")
            self.assertTrue(progress_calls, "Expected calls to progress()")
            if progress_result:
                self.assertTrue(result, "Unexpected failure from export_combined().")

                progress_names = set(x["name"] for x in progress_calls if "name" in x)
                self.assertEqual(progress_names, set(COLUMNS),
                                 "Expected entity names in progress calls.")
                self.assertIn("count", sum(map(list, progress_calls), []),
                              "Expected count in progress calls.")
                validate_data(self, fmt, outfile, combined=True)
            else:
                self.assertEqual(result, None, "Unexpected success from export_combined() on cancel.")
                self.assertFalse(os.path.isfile(outfile),
                                 "Expected no output file from export_combined() on cancel.")


    def verify_export_combined_error(self):
        """Verifies FileDataSink.export_combined() with raised error."""
        logger.info("Verifying export_combined() with raised error.")

        def progress(**kwargs):
            raise Exception("fatal error")

        fmt = "json"
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt, progress)
        result = sink.export_combined("title")
        self.assertEqual(result, False, "Unexpected success from export_combined() on error.")
        self.assertFalse(os.path.isfile(outfile), "Expected no output file on error.")


    def verify_export_query(self, fmt):
        """Verifies FileDataSink.export_query() for given format."""
        logger.info("Verifying export_query() for %s.", fmt.upper())
        name, table_name = "parent", "SQL query"
        query = "SELECT * FROM %s" % grammar.quote(name)
        make_iterable = lambda: self._db.execute(query)
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        result = sink.export_query(query, make_iterable, "title", table_name, COLUMNS[name])
        self.assertTrue(result, "Unexpected failure from export_query() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, names=[table_name], query=query, columns=COLUMNS[name],
                      data_expected={table_name: DATA[name]})


    def verify_export_query_columns(self, fmt):
        """Verifies FileDataSink.export_query() with custom columns for given format."""
        logger.info("Verifying export_query() with constrained columns for %s.", fmt.upper())
        name, table_name = "parent", "SQL query"
        query = "SELECT * FROM %s" % grammar.quote(name)
        make_iterable = lambda: self._db.execute(query)
        for columns in (COLUMNS[name][:-1], [{"name": c} for c in COLUMNS[name][:-1]]):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_query(query, make_iterable, "title", table_name, columns)
            self.assertTrue(result, "Unexpected failure from export_query(columns=%s) for %s." %
                            (columns, fmt.upper()))
            columnnames = [x["name"] if isinstance(x, dict) else x for x in columns]
            rows_expected = [{k: r[k] for k in columnnames} for r in DATA[name]]
            validate_data(self, fmt, outfile, names=[table_name], query=query, columns=columns,
                          data_expected={table_name: rows_expected})


    def verify_export_query_iterable(self, fmt):
        """Verifies FileDataSink.export_query() with custom iterable."""
        logger.info("Verifying export_query() with custom iterable for %s.", fmt.upper())
        name, table_name = "parent", "SQL query"
        colstr = ", ".join(("10 - %s AS %s" % (c, c)) if "id"== c else c for c in COLUMNS[name])
        query = "SELECT %s FROM %s" % (colstr, grammar.quote(name))
        make_iterable = lambda: self._db.execute(query)
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        result = sink.export_query(query, make_iterable, "title", table_name, COLUMNS[name])
        self.assertTrue(result, "Unexpected failure from export_query() for %s." % fmt.upper())
        rows_expected = [{k: (10 - v if "id" == k else v) for k, v in r.items()} for r in DATA[name]]
        validate_data(self, fmt, outfile, names=[table_name], query=query, columns=COLUMNS[name],
                      data_expected={table_name: rows_expected})


    def verify_export_query_configure(self, fmt):
        """Verifies FileDataSink.configure(..)export_query()."""
        logger.info("Verifying export_query() configuration for %s.", fmt.upper())
        name, table_name = "parent", "SQL query"
        query = "SELECT * FROM %s" % grammar.quote(name)
        make_iterable = lambda: self._db.execute(query)

        for limit in (5, (10, ), (5, 5), (10, ROWCOUNT)):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt).configure(limit=limit)
            result = sink.export_query(query, make_iterable, "title", table_name, COLUMNS[name])
            self.assertTrue(result, "Unexpected failure from export_query() for %s." % fmt.upper())
            from_, to_ = (0, limit) if isinstance(limit, int) else \
                         (limit[1], limit[1] + limit[0]) if len(limit) > 1 else (0, limit[0])
            validate_data(self, fmt, outfile, names=[table_name], query=query,
                          columns=COLUMNS[name], limit=limit, 
                          data_expected={table_name: DATA[name][from_:to_]})

        limit, maxcount = 5, 3
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, maxcount=maxcount)
        result = sink.export_query(query, make_iterable, "title", table_name, COLUMNS[name])
        self.assertTrue(result, "Unexpected failure from export_query() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, names=[table_name], query=query, columns=COLUMNS[name],
                      limit=limit, maxcount=maxcount,
                      data_expected={table_name: DATA[name][:min(limit, maxcount)]})

        limit, allow_empty = 0, False
        sink = importexport.FileDataSink(self._db, outfile, fmt)
        sink.configure(limit=limit, allow_empty=allow_empty)
        result = sink.export_query(query, make_iterable, "title", table_name, COLUMNS[name])
        self.assertTrue(result, "Unexpected failure from export_query() for %s." % fmt.upper())
        validate_data(self, fmt, outfile, names=[table_name], query=query, columns=COLUMNS[name],
                      limit=limit, allow_empty=allow_empty, data_expected={})


    def verify_export_query_metainfo(self):
        """Verifies FileDataSink.export_query(title=.., info=..)."""
        logger.info("Verifying export_query(title=.., info=..).")
        fmt = "txt"
        name, table_name = "parent", "SQL query"
        query = "SELECT * FROM %s" % grammar.quote(name)
        make_iterable = lambda: self._db.execute(query)
        title = "some_title"
        for info in ({"info_label": "info_text"}, {"info_title": {"info_label": "info_text"}}):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_query(query, make_iterable, title, table_name, COLUMNS[name], info)
            self.assertTrue(result, "Unexpected failure from export_query(info=%r)." % info)
            with io.open(outfile, encoding="utf-8") as f: content = f.read()
            infostrings = sum((list(v) + list(v.values()) if isinstance(v, dict) else [k, v]
                               for k, v in (info or {}).items()), [])
            for text in infostrings:
                self.assertIn(text, content, "Expected info %r in output." % info)
            self.assertIn(title, content, "Expected title %r in output." % title)
            validate_data(self, fmt, outfile, names=[table_name], query=query, columns=COLUMNS[name],
                          data_expected={table_name: DATA[name]})
        for title in ("single_title", ["multi_title1", "multi_title2"]):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt)
            result = sink.export_query(query, make_iterable, title, table_name, COLUMNS[name], info)
            self.assertTrue(result, "Unexpected failure from export_query(title=%r)." % title)
            with io.open(outfile, encoding="utf-8") as f: content = f.read()
            for text in (title if isinstance(title, list) else [title]):
                self.assertIn(text, content, "Expected title %r in output." % title)
            validate_data(self, fmt, outfile, names=[table_name], query=query, columns=COLUMNS[name],
                          data_expected={table_name: DATA[name]})


    def verify_export_query_progress(self):
        """Verifies FileDataSink.export_query() with progress callback."""
        logger.info("Verifying export_query() with progress callback.")

        progress_calls = []
        progress_result = False
        def progress(**kwargs):
            progress_calls.append(kwargs)
            return progress_result or len(progress_calls) < 2

        fmt = "json"
        name, table_name = "parent", "SQL query"
        query = "SELECT * FROM %s" % grammar.quote(name)
        make_iterable = lambda: self._db.execute(query)
        for progress_result in (False, True):
            outfile = self.mktemp("." + fmt)
            sink = importexport.FileDataSink(self._db, outfile, fmt, progress)
            result = sink.export_query(query, make_iterable, "title", table_name, COLUMNS[name])
            self.assertTrue(progress_calls, "Expected calls to progress()")
            if progress_result:
                self.assertTrue(result, "Unexpected failure from export_query().")
                self.assertIn(table_name, [x.get("name") for x in progress_calls],
                              "Expected table name in progress calls.")
                self.assertIn("count", sum(map(list, progress_calls), []),
                              "Expected count in progress calls.")
                validate_data(self, fmt, outfile, names=[table_name], query=query,
                              columns=COLUMNS[name], data_expected={table_name: DATA[name]})
            else:
                self.assertEqual(result, None, "Unexpected success from export_query() on cancel.")
                self.assertFalse(os.path.isfile(outfile),
                                 "Expected no output file from export_query() on cancel.")


    def verify_export_query_error(self):
        """Verifies FileDataSink.export_query() with raised error."""
        logger.info("Verifying export_query() with raised error.")

        def progress(**kwargs):
            raise Exception("fatal error")

        fmt = "json"
        name, table_name = "parent", "SQL query"
        query = "SELECT * FROM %s" % grammar.quote(name)
        make_iterable = lambda: self._db.execute(query)
        outfile = self.mktemp("." + fmt)
        sink = importexport.FileDataSink(self._db, outfile, fmt, progress)
        result = sink.export_query(query, make_iterable, "title", table_name, COLUMNS[name])
        self.assertEqual(result, False, "Unexpected success from export_query() on error.")
        self.assertFalse(os.path.isfile(outfile), "Expected no output file on error.")


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
