#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests SQLite grammar functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     12.10.2024
@modified    21.10.2024
------------------------------------------------------------------------------
"""
import collections
import json
import logging
import os
import re
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import database, grammar


logger = logging.getLogger()


## CREATE statements for testing, as {label: sql}
CREATE_SQLS = collections.OrderedDict([
    ("table", """CREATE TABLE mytable (mycol1, mycol2, "my col3")"""),
    ("table with flags and comments", """
-- comment
CREATE TABLE -- comment
-- comment
IF NOT EXISTS
-- comment
othertable (
  -- first line comment
  otherkey TEXT PRIMARY KEY,
  othercol1, -- comment
  othercol2 TEXT NOT NULL UNIQUE,
  "other col3" INTEGER -- my comment
  /* multiline
  comment */
  -- last line comment
  NOT NULL
) -- comment
WITHOUT ROWID -- comment
-- comment

"""),
    ("table with columns and constraints", u'''
CREATE TEMPORARY TABLE IF NOT EXISTS "mytable" (
  mykey           INTEGER NOT NULL DEFAULT (1 < 0),
  mycol1          INTEGER NOT NULL ON CONFLICT ABORT UNIQUE ON CONFLICT ROLLBACK DEFAULT /* uhuu */ -666.5,
  mycol2          INTEGER COLLATE /* haha */ BiNARY CHECK ("my col3" IS /* hoho */ NULL),
  "my col3"       TEXT NOT NULL DEFAULT "double "" quoted" CHECK (LENGTH(mytable."my col3") > 0),
  myfk            INTEGER REFERENCES othertable (otherkey) on update no action ON delete cascade match SIMPLE,
  myfk2           INTEGER,
  myfk3           INTEGER,
  mycol4          TIMESTAMP WITH TIME ZONE,
  PRIMARY KEY (mykey) ON CONFLICT ROLLBACK,
  FOREIGN KEY (myfk2, myfk3) REFERENCES othertable (othercol1, othercol2) ON UPDATE RESTRICT ON DELETE CASCADE,
  CONSTRAINT myconstraint CHECK (mycol1 != mycol2)
)
'''),
    ("virtual table", u'''
CREATE VIRTUAL TABLE IF NOT EXISTS main.mytable
USING fts4 (mycol1, mycol2, "my col3");
'''),
    ("index", u'''
CREATE UNIQUE INDEX IF NOT EXISTS
main.myindex ON mytable (mycol1, mycol2)
WHERE mytable.mycol1 NOT BETWEEN mytable.mycol2 AND mytable."my col3"
'''),
    ("trigger", u'''
CREATE TRIGGER main.mytriggér AFTER UPDATE OF "my col3" ON mytable
WHEN 1 NOT IN (SELECT "my col3" FROM mytable)
  BEGIN
    SELECT mycol1, mycol2, "my col3" FROM mytable
      JOIN othertable ON mycol1 == othercol1 AND "my col3" = "other col3"
      WHERE mycol2 == othercol2 AND "my col3" == "other col3";
    SELECT myviewcol1, "myview col3" FROM myview;
    UPDATE othertable SET othercol1 = NEW.mycol1 WHERE othercol2 = OLD.mycol2;
    INSERT INTO othertable (othercol1) VALUES (42)
      ON CONFLICT (othercol1) DO UPDATE SET "other col3" = 43;
    DELETE FROM othertable WHERE "other col3" != old."my col3";
    UPDATE othertable SET othercol2 = new.mycol2 WHERE "other col3" = old."my col3";
  END;
'''),
    ("view", u'''
CREATE VIEW IF NOT EXISTS
main.myview (myviewcol1, myviewcol2, "myview col3")
AS SELECT mycol1, mycol2, "my col3" FROM mytable
'''),
    ("temporary view", u'''
CREATE TEMPORARY VIEW IF NOT EXISTS
myview (myviewcol1, myviewcol2, "myview col3")
AS SELECT mycol1, mycol2, "my col3" FROM mytable
   JOIN othertable ON mytable."my col3" == othertable."other col3"
'''),
    ("view with union", u'''
CREATE VIEW IF NOT EXISTS
main.myview (myviewcol1, myviewcol2, "myview col3")
AS SELECT mycol1, mycol2, "my col3" FROM mytable
   UNION
   SELECT othercol1, othercol2, "other col3" FROM othertable
   UNION
   SELECT 1 AS myview2col1, 2 AS myview2col2, 3 AS "myview2 col3"
'''),
])


## CREATE structures for testing, as {label: {..item..}}
CREATE_ITEMS = {
    "table": {
        "name":           "mytable",
        "columns":        [{"name": u"mycol1"}, {"name": u"mycol2"}, {"name": u"my col3"}],
        "__type__":       "CREATE TABLE",
        "__tables__":     [],
        "__terminated__": False,
        "__comments__":   {},
    },

    "table with flags and comments": {
        "name":           "othertable",
        "exists":         True,
        "options":        [{"without": True}],
        "columns":        [{"name": "otherkey", "type": "TEXT", "pk": {}},
                           {"name": "othercol1"},
                           {"name": "othercol2", "type": "TEXT", "unique": {}, "notnull": {}},
                           {"name": "other col3", "type": "INTEGER", "notnull": {}},
        ],
        "__type__":       "CREATE TABLE",
        "__tables__":     [],
        "__terminated__": False,
        "__comments__":   {  1: "-- comment",
                            25: "-- comment",
                            36: "-- comment",
                            61: "-- comment",
                            87: "-- first line comment",
                           151: "-- comment",
                           219: "-- my comment",
                           235: "/* multiline\n  comment */",
                           263: "-- last line comment",
                           297: "-- comment",
                           322: "-- comment",
                           333: "-- comment"},
    },

    "table with columns and constraints": {
        "name": "mytable",
        "columns": [{"name": "mykey", "type": "INTEGER", "notnull": {},
                     "default": {"expr": "(1 < 0)"}},
                    {"name": "mycol1", "type": "INTEGER", "notnull": {"conflict": "ABORT"},
                     "unique": {"conflict": "ROLLBACK"}, "default": {"expr": "-666.5"}},
                    {"name": "mycol2", "type": "INTEGER", "collate": {"value": "BINARY"},
                     "check": {"expr": '"my col3" IS /* hoho */ NULL'}},
                    {"name": "my col3", "type": "TEXT", "notnull": {},
                     "check": {"expr": 'LENGTH(mytable."my col3") > 0'},
                     "default": {"expr": '"double "" quoted"'}},
                    {"name": "myfk", "type": "INTEGER",
                     "fk": {"action": {"UPDATE": "NO ACTION", "DELETE": "CASCADE"},
                            "table": "othertable", "match": "SIMPLE", "key": "otherkey"}},
                    {"name": "myfk2", "type": "INTEGER"},
                    {"name": "myfk3", "type": "INTEGER"},
                    {"name": "mycol4", "type": "TIMESTAMP WITH TIME ZONE"}
        ],
        "exists":         True,
        "temporary":      True,
        "constraints":    [
          {"type": "PRIMARY KEY", "key": [{"name": "mykey"}], "conflict": "ROLLBACK"},
          {"table": "othertable", "type": "FOREIGN KEY",
           "columns": ["myfk2", "myfk3"], "key": ["othercol1", "othercol2"],
           "action": {"UPDATE": "RESTRICT", "DELETE": "CASCADE"}},
          {"name": "myconstraint", "type": "CHECK", "check": "mycol1 != mycol2"},
        ],
        "__type__":       "CREATE TABLE",
        "__tables__":     ["othertable"],
        "__terminated__": False,
        "__comments__":   {191: "/* uhuu */",
                           244: "/* haha */",
                           282: "/* hoho */",
        },
    },

    "virtual table": {
        "name":           "mytable",
        "schema":         "main",
        "module":         {"name": "fts4", "arguments": ["mycol1", "mycol2", '"my col3"']},
        "exists":         True,
        "__type__":       "CREATE VIRTUAL TABLE",
        "__tables__":     ["mytable"],
        "__terminated__": False,
        "__comments__":   {},
    },

    "index": {
        "name":           "myindex",
        "schema":         "main",
        "columns":        [{"name": "mycol1"}, {"name": "mycol2"}],
        "table":          "mytable",
        "unique":         True,
        "where":          'mytable.mycol1 NOT BETWEEN mytable.mycol2 AND mytable."my col3"',
        "exists":         True,
        "__type__":       "CREATE INDEX",
        "__tables__":     ["mytable"],
        "__terminated__": False,
        "__comments__":   {},
    },

    "trigger": {
          "name":        u"mytriggér",
          "schema":       "main",
          "body":        u'    SELECT mycol1, mycol2, "my col3" FROM mytable\n      JOIN othertable ON mycol1 == othercol1 AND "my col3" = "other col3"\n      WHERE mycol2 == othercol2 AND "my col3" == "other col3";\n    SELECT myviewcol1, "myview col3" FROM myview;\n    UPDATE othertable SET othercol1 = NEW.mycol1 WHERE othercol2 = OLD.mycol2;\n    INSERT INTO othertable (othercol1) VALUES (42)\n      ON CONFLICT (othercol1) DO UPDATE SET "other col3" = 43;\n    DELETE FROM othertable WHERE "other col3" != old."my col3";\n    UPDATE othertable SET othercol2 = new.mycol2 WHERE "other col3" = old."my col3";',
          "when":           '1 NOT IN (SELECT "my col3" FROM mytable)',
          "action":         "UPDATE",
          "table":          "mytable",
          "upon":           "AFTER",
          "columns":        [{"name": "my col3"}],
          "__type__":       "CREATE TRIGGER",
          "__tables__":     ["mytable", "othertable", "myview"],
          "__terminated__": False,
          "__comments__":   {},
    },

    "view": {
        "name":           "myview",
        "schema":         "main",
        "select":         'SELECT mycol1, mycol2, "my col3" FROM mytable',
        "columns":        [{"name": "myviewcol1"}, {"name": "myviewcol2"}, {"name": "myview col3"}],
        "exists":         True,
        "__tables__":     ["mytable"],
        "__type__":       "CREATE VIEW",
        "__terminated__": False,
        "__comments__":   {},
    },

    "temporary view": {
        "name":           "myview",
        "temporary":      True,
        "exists":         True,
        "select":         'SELECT mycol1, mycol2, "my col3" FROM mytable\n   JOIN othertable ON mytable."my col3" == othertable."other col3"',
        "columns":        [{"name": "myviewcol1"}, {"name": "myviewcol2"}, {"name": "myview col3"}],
        "__type__":       "CREATE VIEW",
        "__tables__":     ["mytable", "othertable"],
        "__terminated__": False,
        "__comments__":   {},
    },

    "view with union": {
        "name":           "myview",
        "schema":         "main",
        "select":         'SELECT mycol1, mycol2, "my col3" FROM mytable\n   UNION\n   SELECT othercol1, othercol2, "other col3" FROM othertable\n   UNION\n   SELECT 1 AS myview2col1, 2 AS myview2col2, 3 AS "myview2 col3"',
        "columns":        [{"name": "myviewcol1"}, {"name": "myviewcol2"}, {"name": "myview col3"}],
        "exists":         True,
        "__type__":       "CREATE VIEW",
        "__tables__":     ["mytable", "othertable"],
        "__terminated__": False,
        "__comments__":   {},
    },
}


## Names of test entities, as {label: entity name}
CREATE_NAMES = {
    "table":                              "mytable",
    "table with flags and comments":      "othertable",
    "table with columns and constraints": "mytable",
    "virtual table":                      "mytable",
    "index":                              "myindex",
    "trigger":                           u"mytriggér",
    "view":                               "myview",
    "temporary view":                     "myview",
    "view with union":                    "myview",
}

RENAMES = {
    "table":   {"mytable":                "renamed mytable",
                "othertable":             "renamed othertable"},
    "index":   {"myindex":               u"renämed myindex"},
    "trigger": {u"mytriggér":            u"renämed mytriggér"},
    "view":    {"myview":                u"renämed myview"},
    "column":  {"renamed mytable": {
                    "mycol1":             "myrenamedcol1",
                    "mycol2":             "myrenamedcol2",
                    "my col3":            "myrenamed col3",
                    "mycol4":             "myrenamedcol4",
                    "mykey":              "myrenamedkey",
                    "myfk2":              "myrenamed fk2",
                },
                "renamed othertable": {
                    "othercol1":          "otherrenamedcol1",
                    "othercol2":          "otherrenamedcol2",
                    "other col3":         "other renamed col3",
                    "otherkey":           "otherrenamedkey",
                },
                u"renämed myview":  {
                    "myviewcol1":         "myviewrenamedcol1",
                    "myview col3":        "myview renamed col3",
                },
    },
}



class TestGrammar(unittest.TestCase):
    """Unit-tests grammar operations."""


    def __init__(self, *args, **kwargs):
        super(TestGrammar, self).__init__(*args, **kwargs)
        self.maxDiff = None  # Full diff on assert failure
        try: unittest.util._MAX_LENGTH = 100000
        except Exception: pass


    def test_format(self):
        """Verifies grammar.format()."""
        logger.info("Verifying grammar.format().")
        expecteds = [(42,         "42"),
                     (None,       "NULL"),
                     ("word",     "'word'"),
                     ("\x00\x01", "X'0001'"),
                     (u"é",       u"'\xC3\xA9'"),
                     ]
        for original, expected in expecteds:
            received = grammar.format(original)
            self.assertEqual(received, expected, "Unexpected result from format(%r)." % original)

        coldata = {"type": "json"}
        expecteds = [('[ ]',           "'[]'"),
                     ('{\n  "a":  4}', '\'{"a": 4}\''),
                     ("0.300",         "'0.3'")]
        for original, expected in expecteds:
            received = grammar.format(original, coldata=coldata)
            self.assertEqual(received, expected,
                             "Unexpected result from format(%r, coldata=%r)." % (original, coldata))


    def test_generate(self):
        """Verifies grammar.generate()."""
        logger.info("Verifying grammar.generate().")

        for label, item in CREATE_ITEMS.items():
            logger.info("Verifying grammar.generate() for %s.", label)

            logger.debug("Generating SQL for %s:\n%s", label, item)
            generated_sql, err = grammar.generate(item)
            self.assertFalse(err, "Unexpected failure from generating %s." % label)
            logger.debug("Generated SQL for %s:\n%s", label, generated_sql)

            stripped = [grammar.strip_and_collapse(x, literals=False)
                        for x in (CREATE_SQLS[label], generated_sql)]
            stripped = [re.sub(r'[\s"]', "", x.upper()) for x in stripped]
            self.assertEqual(stripped[0], stripped[1], "Unexpected result for generated %s." % label)
            self.verify_sql(label, CREATE_SQLS[label], generated_sql)


    def test_get_type(self):
        """Verifies grammar.get_type()."""
        logger.info("Verifying grammar.get_type(sql).")
        expecteds = [("/* */\nSeLect 1;",                  grammar.SQL.SELECT),
                     ("INSERT\nINTO\nmytable VALUES (1)",  grammar.SQL.INSERT),
                     ("UPDATE/* */mytable SET mycol1 = 1", grammar.SQL.UPDATE),
                     ("DELETE -- \nFROM mytable",          grammar.SQL.DELETE),
                     ('SELECT*FROM"x"',                    grammar.SQL.SELECT),
                     ('SELECT',                            None)]
        for sql, expected in expecteds:
            received = grammar.get_type(sql)
            self.assertEqual(received, expected, "Unexpected result from get_type(%r)." % sql)


    def test_parse(self):
        """Verifies grammar.parse()."""
        logger.info("Verifying grammar.parse().")

        for label, create_sql in CREATE_SQLS.items():
            logger.info("Verifying grammar.parse() for %s.", label)
            logger.debug("Parsing %s SQL:\n%s", label, create_sql)
            item, err = grammar.parse(create_sql)
            self.assertFalse(err, "Unexpected failure from parsing %s." % label)
            logger.debug("Parsed structure for %s:\n%s", label, json.dumps(item, indent=2))
            self.assertEqual(item, CREATE_ITEMS[label], "Unexpected result for parsed %s." % label)

        logger.debug("Verifying grammar.ParseError.")
        item, errors = grammar.Parser().parse_tree("CREATE INDEX ON")
        self.assertFalse(item, "Unexpected success for invalid SQL: %s" % item)
        self.assertTrue(any(isinstance(e, grammar.ParseError) for e in errors),
                        "Expected ParseError for invalid SQL.")


    def test_quote(self):
        """Verifies grammar.quote()."""
        logger.info("Verifying grammar.quote().")
        expecteds = [("SELECT",    '"SELECT"'),
                     ("word",      "word"),
                     ("two words", '"two words"'),
                     ('wo"rd',     '"wo""rd"'),
                     ('""',        '""""""'),
                     (" ",         '" "'),
                     (14,          '"14"'),
                     (None,         ""),
                     ("14a",       '"14a"'),
                     (u"m#",       '"m#"')]
        for original, expected in expecteds:
            received = grammar.quote(original)
            self.assertEqual(received, expected, "Unexpected result from quote(%r)." % original)

        expecteds = [("word",      '"word"'),
                     ("two words", '"two words"')]
        for original, expected in expecteds:
            received = grammar.quote(original, force=True)
            self.assertEqual(received, expected,
                             "Unexpected result from quote(%r, force=True)." % original)

        expecteds = [("word",      "word"),
                     ("two words", "two words"),
                     ("14a",       "14a"),
                     (" leading",  '" leading"'),
                     ("trailing ",  '"trailing "')]
        for original, expected in expecteds:
            received = grammar.quote(original, embed=True)
            self.assertEqual(received, expected,
                             "Unexpected result from quote(%r, embed=True)." % original)

        expecteds = [(("func()", "()"),   "func()"),
                     (("two words", " "), "two words")]
        for (original, allow), expected in expecteds:
            received = grammar.quote(original, allow=allow)
            self.assertEqual(received, expected,
                             "Unexpected result from quote(%r, allow=%r)." % (original, allow))


    def test_strip_and_collapse(self):
        """Verifies grammar.strip_and_collapse()."""
        logger.info("Verifying grammar.strip_and_collapse().")
        expecteds = [('/* */select --\n  *  from "my table"  ; ;', 'SELECT * FROM ""'),
                     ('insert  into  foo  VALUES  ( 1,   2 )',     "INSERT INTO FOO VALUES (1, 2)")]
        for original, expected in expecteds:
            received = grammar.strip_and_collapse(original)
            self.assertEqual(received, expected,
                             "Unexpected result from strip_and_collapse(%r)." % original)

        expecteds = [('SELECT   "a  b"  from  "my  table"; ', 'SELECT "a  b" from "my  table"'),
                     ('insert into foo VALUES  ("  ( 3 )" )', 'insert into foo VALUES ("  ( 3 )")')]
        for original, expected in expecteds:
            received = grammar.strip_and_collapse(original, literals=False, upper=False)
            self.assertEqual(received, expected, "Unexpected result from "
                             "strip_and_collapse(%r, literals=False, upper=False)." % original)


    def test_terminate(self):
        """Verifies grammar.terminate()."""
        logger.info("Verifying grammar.terminate().")
        expecteds = [("SELECT * FROM a",      "SELECT * FROM a;"),
                     ("SELECT * FROM a;\n\n", "SELECT * FROM a;"),
                     ("SELECT * FROM a --",   "SELECT * FROM a --\n;")]
        for original, expected in expecteds:
            received = grammar.terminate(original)
            self.assertEqual(received, expected,
                             "Unexpected result from terminate(%r)." % original)


    def test_transform_flags(self):
        """Verifies grammar.transform(flags={..})."""
        logger.info("Verifying grammar.transform(flags={..}).")

        FLAG_EXPECTS = {"exists": "IF NOT EXISTS", "temporary": "TEMPORARY", "unique": "UNIQUE"}
        def verify_flags(category, create_sql, flags):
            logger.debug("Verifying grammar.transform(%s, %s).", create_sql, flags)
            transformed_sql, err = grammar.transform(create_sql, flags)
            self.assertFalse(err, "Unexpected failure from transforming CREATE %s." %
                             category.upper())
            logger.debug("Transformed SQL for %s:\n%s", category, transformed_sql)
            for flag, flag_value in flags.items():
                self.assertEqual(flag_value, FLAG_EXPECTS[flag] in transformed_sql,
                                 "Unexpected %s state from transform of CREATE %s." %
                                 (FLAG_EXPECTS[flag], category.upper()))

        for category in database.Database.CATEGORIES:
            logger.info("Verifying grammar.transform(flags={..}) for CREATE %s.", category.upper())
            create_sql = CREATE_SQLS[category]
            exists_values = [False, True][::1 if FLAG_EXPECTS["exists"] in create_sql else -1]
            temp_values, unique_values = [], []
            if "table" == category: 
                temp_values = [False, True][::1 if FLAG_EXPECTS["temporary"] in create_sql else -1]
            if "index" == category: 
                 unique_values = [False, True][::1 if FLAG_EXPECTS["unique"] in create_sql else -1]
            for exists in exists_values:
                flags = {"exists": exists}
                verify_flags(category, create_sql, flags)
                for temp in temp_values:
                    verify_flags(category, create_sql, dict(flags, **{"temporary": temp}))
                for unique in unique_values:
                    verify_flags(category, create_sql, dict(flags, **{"unique": unique}))


    def test_transform_rename_schema(self):
        """Verifies grammar.transform) for dropping-adding-changing schema."""
        logger.info("Verifying grammar.transform() for toggling schema.")
        for label, create_sql in CREATE_SQLS.items():
            schema_values = [False, True][::1 if "main." in create_sql else -1]
            for flag in schema_values:
                renames = {"schema": "main" if flag else None}
                transformed_sql, err = grammar.transform(create_sql, renames=renames)
                self.assertFalse(err, "Unexpected failure from transforming %s." % label)
                logger.debug("Transformed SQL for %s:\n%s", label, transformed_sql)
                self.assertEqual(flag, "main." in transformed_sql,
                                 "Failed to %s schema in %s." % ("add" if flag else "drop", label))
                if flag and "TEMPORARY" in create_sql: continue # for flag
                self.verify_sql(label, transformed_sql)
            if "main." in create_sql: # Test schema rename separately
                renames = {"schema": {"main": "otherschema"}}
                transformed_sql, err = grammar.transform(create_sql, renames=renames)
                self.assertFalse(err, "Unexpected failure from transforming %s." % label)
                logger.debug("Transformed SQL for %s:\n%s", label, transformed_sql)
                self.assertIn("otherschema.", transformed_sql,
                              "Failed to rename schema in %s." % label)
                # Rename back to main and verify validity
                renames = {"schema": {"otherschema": "main"}}
                transformed_sql, err = grammar.transform(create_sql, renames=renames)
                self.assertFalse(err, "Unexpected failure from transforming %s." % label)
                self.assertIn("main.", transformed_sql, "Failed to rename schema in %s." % label)
                self.verify_sql(label, transformed_sql)


    def test_transform_renames(self):
        """Verifies grammar.transform(renames={..})."""
        logger.info("Verifying grammar.transform(renames={..}).")
        renamed_schema = {} # {name: CREATE SQL} for required entities in database testing
        for label, create_sql in CREATE_SQLS.items():
            logger.info("Verifying grammar.transform(renames={..}) for %s.", label)
            transformed_sql, err = grammar.transform(create_sql, renames=RENAMES)
            self.assertFalse(err, "Unexpected failure from transforming %s." % label)
            logger.debug("Transformed SQL for %s:\n%s", label, transformed_sql)

            for category in RENAMES:
                if "schema" == category:
                    self.assertIn(RENAMES[category], transformed_sql,
                                  "Expected renamed schema in transformed %s." % label)
                elif "column" == category:
                    for entity, renames in RENAMES[category].items():
                        if entity not in transformed_sql: continue # for entity,
                        for col1, col2 in renames.items():
                            if col1 not in create_sql: continue # for col1,
                            self.assertIn(col2, transformed_sql,
                                          "Expected renamed column in transformed %s." % label)
                            self.assertNotIn(col1, transformed_sql,
                                          "Unexpected original column in transformed %s." % label)
                else:
                    for name1, name2 in RENAMES[category].items():
                        if name1 in create_sql:
                            self.assertIn(name2, transformed_sql,
                                          "Expected renamed entity in transformed %s." % label)
            if CREATE_NAMES[label] in ("mytable", "othertable"):
                renamed_schema.setdefault(CREATE_NAMES[label], transformed_sql)
            self.verify_sql(label, transformed_sql, baseschema=list(renamed_schema.values()))


    def test_unquote(self):
        """Verifies grammar.unquote()."""
        logger.info("Verifying grammar.unquote().")
        expecteds = [("word",      "word"),
                     ('"word"',    "word"),
                     ('[word]',    "word"),
                     ("'word'",    "word"),
                     ('"wo""rd"',  'wo"rd'),
                     (14,          "14"),
                     (None,        "")]
        for original, expected in expecteds:
            received = grammar.unquote(original)
            self.assertEqual(received, expected, "Unexpected result from unquote(%r)." % original)



    def verify_sql(self, label, *create_sqls, **kwargs):
        """
        Verffies that SQL create statements result in valid schema in actual database.

        If more than one statement given, verifies also that their created schema is identical.

        @param  baseschema  list of CREATE statements to execute as base for non-table entities,
                            for testing renames
        """
        if any("VIRTUAL TABLE" in x for x in create_sqls):
            if sys.version_info < (3, ):
                logger.debug("FTS not available, skipping verify inside SQLite for %s.", label)
                return # FTS not available

        BASELABELS = ["table"] + [k for k, v in CREATE_NAMES.items() if v == "othertable"]
        baseschema = kwargs.get("baseschema")
        db_sqls, db_infos = [], []
        for sql in create_sqls:
            with sqlite3.connect(":memory:") as sqldb:
                sqldb.row_factory = lambda cursor, row: dict(sqlite3.Row(cursor, row))
                if "TABLE" not in sql: # Add an actual table as well for index/trigger/view
                    base_sqls = baseschema
                    if not base_sqls:
                        base_sqls = [CREATE_SQLS[k] for k in BASELABELS]
                    for base_sql in base_sqls:
                        sqldb.execute(base_sql)
                sqldb.executescript(sql)

                schema_prefix = "temp." if "TEMPORARY" in sql else ""
                schema_sql = "SELECT * FROM %ssqlite_master WHERE name = ?" % schema_prefix
                name = CREATE_NAMES[label]
                if baseschema:
                    name = next((vv[name] for c, vv in RENAMES.items()
                                 if c != "column" and name in vv), name)
                row = next(sqldb.execute(schema_sql, [name]))
                self.assertTrue(row, "Expected creation of %s." % label)
                if len(create_sqls) < 2: return

                db_sqls.append(row["sql"])
                if "trigger" != row["type"]:
                    pragma = "index_info" if "index" == row["type"] else "table_info"
                    info_sql = "PRAGMA %s(%s)" % (pragma, grammar.quote(row["name"]))
                    db_infos.append(sqldb.execute(info_sql).fetchone())

        if db_infos:
            self.assertEqual(db_infos[0], db_infos[1],
                             "Database information does not match for %s." % label)
        stripped = [grammar.strip_and_collapse(x, literals=False) for x in db_sqls]
        stripped = [x.upper().replace('"', "").replace("'", "") for x in stripped]
        self.assertEqual(stripped[0], stripped[1], "Processed SQLs do not match for %s." % label)



if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
