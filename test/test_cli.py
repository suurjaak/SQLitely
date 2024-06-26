#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests command-line interface.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     24.06.2024
@modified    26.06.2024
------------------------------------------------------------------------------
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest

try: import xlsxwriter
except ImportError: xlsxwriter = None
try: import yaml
except ImportError: yaml = None


logger = logging.getLogger()


class TestCLI(unittest.TestCase):
    """Tests the command-line interface.."""


    FORMATS = ["db", "csv", xlsxwriter and "xlsx", "html", "json", "sql", "txt", yaml and "yaml"]
    FORMATS = list(filter(bool, FORMATS))

    PRINTABLE_FORMATS = [x for x in FORMATS if x not in ("html", "xlsx")]


    def __init__(self, *args, **kwargs):
        super(TestCLI, self).__init__(*args, **kwargs)
        self.maxDiff = None  # Full diff on assert failure
        try: unittest.util._MAX_LENGTH = 100000
        except Exception: pass
        self._proc   = None  # subprocess.Popen instance
        self._dbname = None  # Path to source database
        self._paths  = []    # [path to temporary test file, ]


    def setUp(self):
        """Populates temporary file paths."""
        super(TestCLI, self).setUp()
        self._dbname = self.mktemp(".db")


    def tearDown(self):
        """Deletes temoorary files, closes subprocess if any."""
        try: self._proc and self._proc.terminate()
        except Exception: pass
        for path in self._paths:
            try: os.remove(path)
            except Exception: pass
        super(TestCLI, self).tearDown()


    def test_execute(self):
        """Tests 'execute' command in command-line interface."""
        logger.info("Testing 'execute' command.")

        self.verify_execute_blank()
        self.verify_execute_crud()
        self.verify_execute_file_args()
        self.verify_execute_formats()
        self.verify_execute_flags()


    def verify_execute_blank(self):
        """Tests 'execute': queries on missing or blank database."""
        logger.info("Testing failure of query on nonexistent file.")
        res, out, err = self.run_cmd("execute", self._dbname, "SELECT 1")
        self.assertTrue(res, "Unexpected success from query on nonexistent file.")

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
        self.assertTrue(os.path.getsize(self._dbname), "Expected database file to not empty.")

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
        for fmt in self.PRINTABLE_FORMATS:
            logger.info("Testing query export as %s.", fmt.upper())
            res, out, err = self.run_cmd("execute", self._dbname, "SELECT * FROM foo", "-f", fmt)
            self.assertFalse(res, "Unexpected failure from SELECT query.")
            self.assertTrue(out, "Unexpected lack of output from SELECT query.")

        for fmt in self.FORMATS:
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


    def run_cmd(self, command, *args):
        """Executes SQLitely command, returns (exit code, stdout, stderr)."""
        TIMEOUT = dict(timeout=60) if sys.version_info > (3, 2) else {}
        workdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
        args = [str(x) for x in args]
        #cmd = [r"c:\Program Files\Python\python.exe", "-m", "sqlitely", command] + list(args)
        cmd = ["python", "-m", "sqlitely", command] + list(args)
        logger.debug("Executing command %r.", " ".join(repr(x) if " " in x else x for x in cmd))
        self._proc = subprocess.Popen(cmd, universal_newlines=True, cwd=workdir,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = (x.strip() for x in self._proc.communicate(**TIMEOUT))
        logger.debug("Command result: %r.", self._proc.poll())
        if out: logger.debug("Command stdout:\n%s", out)
        if err: logger.debug("Command stderr:\n%s", err)
        return self._proc.returncode, out, err


    def mktemp(self, suffix=None, content=None):
        """Returns path of a new temporary file, optionally retained on disk with given content."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=not content) as f:
            if content: f.write(content.encode("utf-8"))
            self._paths.append(f.name)
            return f.name


if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t[%(created).06f] [test_cli] %(message)s"
    )
    unittest.main()
