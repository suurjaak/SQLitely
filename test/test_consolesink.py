#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests importexport.ConsoleSink.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     09.09.2024
@modified    16.09.2024
------------------------------------------------------------------------------
"""
import contextlib
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import importexport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from test.common import COLUMNS, SCHEMA, DATA, text_type, validate_data


logger = logging.getLogger()


class TestConsoleSink(unittest.TestCase):
    """Unit-tests ConsoleSink public API."""


    def __init__(self, *args, **kwargs):
        super(TestConsoleSink, self).__init__(*args, **kwargs)
        self.maxDiff = None  # Full diff on assert failure
        try: unittest.util._MAX_LENGTH = 100000
        except Exception: pass
        self._outputs = {} # {stream: [line, ]}


    def test_formats(self):
        """Verifies ConsoleSink output."""
        logger.info("Verifying ConsoleSink output for all formats.")
        for fmt in importexport.PRINTABLE_EXTS:
            logger.info("Verifying ConsoleSink output for %s.", fmt.upper())
            self._outputs.clear()
            sink = importexport.ConsoleSink(fmt, self.output)
            with self.mock_stdout():
                result = sink.write(self.make_iterables)
            self.assertTrue(result, "Unexpected failure from ConsoleSink.write().")
            self.validate_output(fmt)


    def test_formats_combined(self):
        """Verifies ConsoleSink combined output."""
        logger.info("Verifying ConsoleSink combined output.")

        for fmt in importexport.PRINTABLE_EXTS:
            logger.info("Verifying ConsoleSink combined output for %s.", fmt.upper())
            self._outputs.clear()
            sink = importexport.ConsoleSink(fmt, self.output).configure(combined=True)
            with self.mock_stdout():
                result = sink.write(self.make_iterables)
            self.assertTrue(result, "Unexpected failure from ConsoleSink.write().")
            self.validate_output(fmt, combined=True)


    def test_formats_empty(self):
        """Verifies ConsoleSink output with no empty data."""
        logger.info("Verifying ConsoleSink output with no empty data.")

        for fmt in importexport.PRINTABLE_EXTS:
            logger.info("Verifying ConsoleSink output with no empty data for %s.", fmt.upper())
            self._outputs.clear()
            sink = importexport.ConsoleSink(fmt, self.output).configure(allow_empty=False)
            with self.mock_stdout():
                result = sink.write(self.make_iterables)
            self.assertTrue(result, "Unexpected failure from ConsoleSink.write().")
            self.validate_output(fmt, allow_empty=False)


    def test_metainfo(self):
        """Verifies ConsoleSink metadata output."""
        logger.info("Verifying ConsoleSink metainfo output for all formats.")
        for fmt in importexport.PRINTABLE_EXTS:
            logger.info("Verifying ConsoleSink metainfo output for %s.", fmt.upper())
            for title in (None, "titulus titulus", ["titulus1", "titulus2"]):
                self._outputs.clear()
                sink = importexport.ConsoleSink(fmt, self.output)
                with self.mock_stdout():
                    result = sink.write(self.make_iterables, title)
                self.assertTrue(result, "Unexpected failure from ConsoleSink.write().")
                self.validate_output(fmt)

                errput = "\n".join(self._outputs.get(sys.stderr, []))
                if title:
                    expected = "\n".join(title) if isinstance(title, list) else title
                    self.assertIn(expected, errput, "Expected title in metainfo.")
                else:
                    self.assertFalse(errput, "Expected no metainfo output.")


    def test_progress(self):
        """Verifies ConsoleSink error cases."""
        logger.info("Verifying ConsoleSink progress-callback.")
        for fmt in importexport.PRINTABLE_EXTS:
            logger.info("Verifying ConsoleSink progress-callback for %s.", fmt.upper())

            progress_calls = []
            def progress(**kwargs):
                progress_calls.append(kwargs)
                return False if skipped_names and kwargs.get("name") in skipped_names else True

            for skipped_names in ([], ["related", "myview"]):
                del progress_calls[:]
                self._outputs.clear()
                sink = importexport.ConsoleSink(fmt, self.output, progress)
                with self.mock_stdout():
                    result = sink.write(self.make_iterables)
                if skipped_names:
                    self.assertEqual(result, None, "Unexpected success from ConsoleSink.write().")
                else:
                    self.assertTrue(result, "Unexpected failure from ConsoleSink.write().")
                names = [n for n in DATA if not skipped_names or n not in skipped_names]
                self.validate_output(fmt, names=names)
                for name in DATA:
                    itemlabel = "%r in %s output" % (name, fmt.upper())
                    entry = next((x for x in progress_calls
                                  if x.get("name") == name and x.get("done") and "count" in x), None)
                    if skipped_names and name in skipped_names:
                        self.assertFalse(entry, "Unexpected progress entry for %s." % itemlabel)
                    else:
                        self.assertTrue(entry, "Expected progress entry for %s." % itemlabel)


    def test_write_errors(self):
        """Verifies ConsoleSink error cases."""
        logger.info("Verifying ConsoleSink error cases.")

        logger.info("Verifying ConsoleSink error for unsupported format.")
        for fmt in ("html", "xlsx", "xlsx"):
            with self.assertRaises(Exception, msg="Expected error on unsupported format."):
                sink = importexport.ConsoleSink(fmt, self.output)

        logger.info("Verifying ConsoleSink output for no items.")
        sink = importexport.ConsoleSink("json", self.output)
        result = sink.write(lambda: [])
        self.assertTrue(result, "Unexpected failure from ConsoleSink.write().")
        output = "\n".join(self._outputs.get(sys.stdout, []))
        self.assertFalse(output, "Expected no output if no items.")

        logger.info("Verifying ConsoleSink on raised error.")
        def progress(**kwargs):
            raise Exception("fatal error")
        sink = importexport.ConsoleSink("txt", self.output, progress)
        with self.mock_stdout():
            result = sink.write(self.make_iterables)
        self.assertEqual(result, False, "Unexpected success from ConsoleSink on error.")


    def validate_output(self, fmt, allow_empty=True, combined=False, names=None):
        """Asserts current output containing valid expected data."""
        content = ("" if "csv" == fmt else "\n").join(self._outputs.get(sys.stdout, []))
        if sys.version_info < (3, ): content = content.decode("utf-8")
        validate_data(self, fmt, content=content, names=names, allow_empty=allow_empty,
                      combined=combined)


    def make_iterables(self):
        """Yields pairs of ({name, type, columns, sql}, function yielding rows)."""
        for name, rows in DATA.items():
            category = "table" if name in SCHEMA["table"] else "view"
            columns = [{"name": col} for col in COLUMNS[name]]
            sql = SCHEMA[category][name] + ";"
            item = {"name": name, "type": category, "columns": columns, "sql": sql}
            yield item, (lambda rows: lambda: iter(rows))(rows)


    @contextlib.contextmanager
    def mock_stdout(self):
        """Returns context manager replacing sys.stdout with local content capture."""
        sys_stdout = sys.stdout
        try:
            sys.stdout = type("mockstream", (), {"write": self.output})()
            yield sys.stdout
        finally:
            sys.stdout = sys_stdout


    def output(self, value="", file=sys.stdout):
        """Output callback for sink, stores value, returns value length."""
        if not isinstance(value, text_type): value = str(value)
        self._outputs.setdefault(file, []).append(value)
        return len(value)


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
