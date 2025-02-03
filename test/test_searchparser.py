#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests search text parsing.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     17.10.2024
@modified    28.12.2024
------------------------------------------------------------------------------
"""
import contextlib
import logging
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from sqlitely import searchparser


logger = logging.getLogger()


## Prints query parsing flow
DO_TRACE = False

QUERIES = {
    'WORDTEST':      'word "quoted words"',
    'ORTEST':        'singleword OR (grouped words) OR lastword',
    'NEGATIONTEST':  ' -notword -"not this phrase" -(not these words) '
                     '-table:notthistable -column:notthiscolumn -date:1..9999',
    'WILDCARDTEST':  'under_score percent% wild*card table:notawild*card',
    'DATETEST':      'date:2002 -date:2002-12-24..2003 date:..2002-12-29 date:*-*-24',
    'CHARACTERTEST': u'ragnarök OR bust!½{[]}\\$$£@~§´` table:mytable table:jörmungandr',
    'KEYWORDTEST':   '--table:notkeyword tables:notkeyword table: singleword '
                     'table:"quoted title" date:t date:20022-x-20..2003-x-y',
    'WORDFAILTEST':  'table:parens in(anyword',
    'BIGTEST':       'word OR (grouped words) OR -(excluded grouped words) '
                     'OR -excludedword OR (word2 OR (nested grouped words)) '
                     'date:2011-11..2013-02 -date:2012-06..2012-08 '
                     '-(excluded last grouped words) (last grouped words) '
                     '(last (nested grouped words)) verylastword',
}

WORDS = {
    'WORDTEST':      ['word', ('quoted words',)],
    'ORTEST':        ['singleword', 'grouped', 'words', 'lastword'],
    'WILDCARDTEST':  ['under_score', 'percent%', 'wild*card'],
    'CHARACTERTEST': [u'ragnarök', u'bust!½{[]}\\$$£@~§´`'],
    'KEYWORDTEST':   ['--table:notkeyword', 'tables:notkeyword', 'table:', 'singleword'],
    'WORDFAILTEST':  ['in(anyword'],
    'BIGTEST':       ['word', 'grouped', 'words', 'word2', 'nested', 'grouped', 'words', 'last',
                      'grouped', 'words', 'last', 'nested', 'grouped', 'words', 'verylastword'],
}

KEYWORDS = {
    'NEGATIONTEST':  {'-table': ['notthistable'], '-column': ['notthiscolumn'], '-date': ['1..9999']},
    'WILDCARDTEST':  {'table': ['notawild*card']},
    'DATETEST':      {'date': ['2002', '..2002-12-29', '*-*-24'], '-date': ['2002-12-24..2003']},
    'CHARACTERTEST': {'table': ['mytable', u'jörmungandr']},
    'KEYWORDTEST':   {'table': [('quoted title',)], 'date': ['t', '20022-x-20..2003-x-y']},
    'WORDFAILTEST':  {'table': ['parens']},
    'BIGTEST':       {'date': ['2011-11..2013-02'], '-date': ['2012-06..2012-08']},
}

NOSQLS = ['KEYWORDTEST', 'WORDFAILTEST', 'WILDCARDTEST']

SCHEMA_SQL = "CREATE TABLE mytable (textcol, datecol DATETIME)"

SCHEMA_ITEM = {"name": "mytable", "type": "table",
               "columns": [{"name": "textcol"}, {"name": "datecol", "type": "DATETIME"}]}


class TestSearchParser(unittest.TestCase):
    """Unit-tests grammar operations."""


    def __init__(self, *args, **kwargs):
        global DO_TRACE
        super(TestSearchParser, self).__init__(*args, **kwargs)
        self.maxDiff = None  # Full diff on assert failure
        try: unittest.util._MAX_LENGTH = 100000
        except Exception: pass


    def test_parse(self):
        """Verifies SearchQueryParser.parse()."""
        logger.info("Verifying SearchQueryParser.parse().")
        parser = searchparser.SearchQueryParser()
        loglines = []

        if DO_TRACE:
            parser._makeSQL = self.make_parse_tracer(parser._makeSQL, loglines)

        for label, query in QUERIES.items():
            logger.info("Verifying %s.", label)
            logger.debug("Query for %s: %s.", label, query)
            del loglines[:]
            sql, params, words, keywords = parser.Parse(query, item=SCHEMA_ITEM)
            logger.debug("SQL for %s query:\n%s", label, sql)
            logger.debug("SQL parameters for %s query:\n%s", label, params)
            if DO_TRACE:
                logger.info("Parse tracing for %s:\n%s", label, "\n".join(loglines))
            self.assertEqual(words, WORDS.get(label, []),
                             "Unexpected words from parsing %s query %r." % (label, query))
            self.assertEqual(keywords, KEYWORDS.get(label, {}),
                             "Unexpected keywords from parsing %s query %r." % (label, query))
            self.assertEqual(not sql, label in NOSQLS,
                             "%s SQL statement from parsing %s query %r." %
                             ("Unexpected" if sql else "Expected", label, query))
            if sql:
                self.verify_query_sql(label, sql, params)


    def verify_query_sql(self, label, sql, params):
        """Verifies SQL query in database."""
        with contextlib.closing(sqlite3.connect(":memory:")) as sqldb:
            sqldb.executescript(SCHEMA_SQL)
            try: sqldb.execute(sql, params)
            except Exception as e:
                self.fail("Unexpected error from running query for %s: %r" % (label, e))


    def make_parse_tracer(self, func, loglines):
        """Returns function wrapping """
        level = [0] # List as workaround: enclosing scope cannot be reassigned
        def inner(parseresult, params, keywords, case=False, item=None, parent_name=None):
            txt = "%s_makeSQL(<%s> %s, parent_name=%s)" % \
                  ("  " * level[0], parseresult.__class__.__name__, item, parent_name)
            if hasattr(parseresult, "getName"):
                txt += ", name=%s" % parseresult.getName()
            loglines.append(txt)
            level[0] += 1
            result = func(parseresult, params, keywords, case, item, parent_name)
            level[0] -= 1
            loglines.append("%s = %s." % (txt, result))
            return result
        return inner



if "__main__" == __name__:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s]\t%(relativeCreated)12.06f [%(filename)s] %(message)s"
    )
    unittest.main()
