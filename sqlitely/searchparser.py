# -*- coding: utf-8 -*-
"""
Parses a Google-like search grammar into SQL for querying a database.

- words can consist of any non-whitespace characters including all Unicode,
  excluding round brackets and quotes ()"
- asterisk (*) can be used as a wildcard, matching any character or whitespace
- quoted text is a literal phrase: "one two  three   ."
- can use operator "OR" to make an either-or search: one OR two
- words can be grouped with round brackets: (one two) OR (three four)
- keywords table:tablename, column:columnname,
  date:year[-month[-day]][..year[-month[-day]]],
  value can be in quotes, e.g. table:"table name". Keywords are global, ignoring
  all groups and OR-expressions.
- "-" immediately before: exclude words, phrases, grouped words and keywords
- can also provide queries to search all fields in any table

If pyparsing is unavailable, falls back to naive split into words and keywords.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    03.11.2019
"""
import calendar
import collections
import datetime
import logging
import re
import string
import warnings

try:
    from pyparsing import CaselessLiteral, Combine, FollowedBy, Forward, Group, \
                          Literal, NotAny, OneOrMore, Optional, ParseResults, \
                          ParserElement, Suppress, Word, ZeroOrMore
    ParserElement.enablePackrat() # Speeds up recursive grammar significantly
except ImportError:
    ParserElement = None

from . lib import util
from . import grammar

logger = logging.getLogger(__name__)


ALLWORDCHARS = re.sub("[\x00-\x1f\x7f-\xa0]", "", u"".join(
    unichr(c) for c in range(65536) if not unichr(c).isspace()
))
ALLCHARS = ALLWORDCHARS + string.whitespace
WORDCHARS = ALLWORDCHARS.replace("(", "").replace(")", "").replace("\"", "")
ESCAPE_CHAR = "\\" # Character used to escape SQLite special characters like _%


class SearchQueryParser(object):

    # For naive identification of "table:xyz", "date:xyz" etc keywords
    PATTERN_KEYWORD = re.compile("^(-?)(table|view|column|date)\\:([^\\s]+)$", re.I)


    def __init__(self):
        if not ParserElement: return
        with warnings.catch_warnings():
            # In Python 2.6, pyparsing throws warnings on its own code.
            warnings.simplefilter("ignore")
            orOperator = Suppress(CaselessLiteral("OR")
                                 ).setResultsName("OR_OPERATOR")
            quoteContents = Group(Word(ALLCHARS.replace("\"", "")))
            quoteContents.leaveWhitespace()
            quotedWord = Group(Suppress('"') + quoteContents + Suppress('"')
                              ).setResultsName("QUOTES")
            plainWord = Group(NotAny(CaselessLiteral("OR"))
                              + Word(WORDCHARS.replace("-", ""), WORDCHARS)
                             ).setResultsName("PLAINWORD")
            anyWord = Group(NotAny('(') + ~FollowedBy(')') + Word(ALLWORDCHARS)
                           ).setResultsName("ANYWORD")
            keyWord = Group(Combine(Optional("-") + Word(string.ascii_letters)
                                    + Literal(":")
                                    + (Word(WORDCHARS) | quotedWord))
                           ).setResultsName("KEYWORD")
            notExpr = Group(Suppress("-") + NotAny(string.whitespace)
                            + (quotedWord | plainWord)
                           ).setResultsName("NOT")
            word = Group(keyWord | notExpr | quotedWord | plainWord
                        ).setResultsName("WORD")

            query = Forward()
            parens = Forward()

            orOperand = Group(word | parens | notExpr | anyWord
                             ).setResultsName("OR_OPERAND")
            orExpr = Group(
                FollowedBy(orOperand + orOperator + orOperand)
                + Group(orOperand + OneOrMore(orOperator + orOperand))
                ).setResultsName("OR_EXPRESSION")
            oneExpr = Group(orExpr | parens | word | anyWord
                           ).setResultsName("ONE EXPRESSION")
            parens <<= Group(
                Group(Optional("-")).setResultsName("NOT_PARENTHESIS")
                + Suppress("(") + ZeroOrMore(parens | query)
                + Suppress(")")).setResultsName("PARENTHESIS")
            query <<= ((oneExpr + query) | oneExpr
                        ).setResultsName("GRAMMAR")
            self._grammar = query


    def Parse(self, query, item=None):
        """
        Parses the query string and returns (sql, sql params, words).

        @param   item  if set, search is performed on all the fields of this
                       specific table or view
                       {"name": "Item name", "columns": [{"name", "pk", }, ]}
        @return        (SQL string, SQL parameter dict, word and phrase list,
                        keyword map); phrases as tuple-wrapped strings
                       
        """
        words = [] # All encountered text words and quoted phrases
        keywords = collections.defaultdict(list) # {"table": [], "column": [], ..}
        sql_params = {} # Parameters for SQL query {"column_like0": "%word%", ..}

        try:
            parse_results = self._grammar.parseString(query, parseAll=True)
        except Exception:
            # Grammar parsing failed: do a naive parsing into keywords and words
            logger.exception('Failed to use grammar to parse search query "%s".', query)
            split_words = query.split()

            for word in split_words[:]:
                if self.PATTERN_KEYWORD.match(word):
                    _, negation, key, value, _ = self.PATTERN_KEYWORD.split(word)
                    key = negation + key
                    keywords[key.lower()].append(value.lower())
                    split_words.remove(word)
            try:
                parse_results = ParseResults(split_words)
            except NameError: # pyparsing.ParseResults not available
                parse_results = split_words

        self._makeSQL(parse_results, [], keywords, {}, item) # Populate keywords
        result = self._makeSQL(parse_results, words, keywords, sql_params, item)
        match_kw = lambda k, x: any(y in x["name"].lower() for y in keywords[k])
        if item:
            skip_item = False
            for kw in keywords:
                if (item["type"]  == kw and not match_kw(item["type"], item)) \
                or ("-" + item["type"] == kw and match_kw("-" + item["type"], item)):
                    skip_item = True
                    break # for kw
            if skip_item:
                result = ""
            else:
                kw_sql = self._makeKeywordsSQL(keywords, sql_params, item)
                result = "SELECT * FROM %s WHERE %s %s%s" % (
                         grammar.quote(item["name"]), result,
                         " AND " if result and kw_sql else "", kw_sql)

                pk_cols = [c for c in item["columns"] if c.get("pk")]
                if pk_cols: result += " ORDER BY " + ", ".join(
                    "%s ASC" % grammar.quote(c["name"])
                    for c in sorted(pk_cols, key=lambda x: x["pk"])
                )
        else:
            kw_sql = self._makeKeywordsSQL(keywords, sql_params, item)
        if not item and kw_sql:
            result = "%s%s" % ("%s AND " % result if result else "", kw_sql)

        return result, sql_params, words, keywords


    def _makeSQL(self, parseresult, words, keywords, sql_params,
                 item=None, parent_name=None):
        """
        Returns the ParseResults item as an SQL string, appending
        words and phrases to words list, and keyword and sql parameter values
        to argument dictionaries.
        """
        result = ""
        match_kw = lambda k, x: any(y in x["name"].lower() for y in keywords[k])

        if isinstance(parseresult, basestring):
            words.append(parseresult if "QUOTES" != parent_name else (parseresult, ))
            safe = self._escape(parseresult, ("" if "QUOTES" == parent_name else "*"))
            if not item:
                item = {"name": "m", "columns": [{"name": "n"}]}

            i = len(sql_params)
            for col in item["columns"]:
                if (keywords.get("column") and not match_kw("column", col)) \
                or (keywords.get("-column") and match_kw("-column", col)):
                    continue # for col

                result_col = "%s LIKE :column_like%s" % (grammar.quote(col["name"]), i)
                if len(safe) > len(parseresult):
                    result_col += " ESCAPE '%s'" % ESCAPE_CHAR
                result += (" OR " if result else "") + result_col
            if not result:
                return "1 = 0" # No matching columns

            if len(item["columns"]) > 1: result = "(%s)" % result
            sql_params["column_like%s" % i] = "%" + safe + "%"
        else:
            elements = parseresult
            parsed_elements = []
            name = hasattr(parseresult, "getName") and parseresult.getName()
            do_recurse = True
            negation = ("NOT" == name)
            if "KEYWORD" == name:
                key, word = elements[0].split(":", 1)
                if key.lower() in ["table", "-table", "view", "-view", "column", "-column", "date", "-date"]:
                    keywords[key.lower()].append(word.lower())
                    do_recurse = False
            elif "PARENTHESIS" == name:
                name_elem0 = getattr(elements[0], "getName", lambda: "")()
                if len(elements) and "NOT_PARENTHESIS" == name_elem0:
                    negation = bool(elements[0])
                    elements = elements[1:] # Drop the optional "-" in front
            elif "QUOTES" == name:
                elements = self._flatten(elements)
            if do_recurse:
                words_ptr = [] if negation else words # No words from negations
                for i in elements:
                    sql = self._makeSQL(i, words_ptr, keywords, sql_params,
                                       item, name)
                    parsed_elements.append(sql)
                or_names = ["OR_OPERAND", "OR_EXPRESSION"]
                glue = " OR " if name in or_names else " AND "
                result, count = self._join_strings(parsed_elements, glue)
                result = "(%s)"   % result if count > 1 else result
                result = "NOT %s" % result if negation else result
        return result


    def _makeKeywordsSQL(self, keywords, sql_params, item):
        """
        Returns the keywords as an SQL string, appending SQL argument values
        to parameters dictionary.
        """
        result = ""
        match_kw = lambda k, x: any(y in x["name"].lower() for y in keywords[k])

        for keyword, words in keywords.items():
            kw_sql = ""
            for word in words:
                sql = ""
                if keyword.endswith("date"): # date:2002..2003-11-21
                    datecols = [c for c in (item or {}).get("columns", [])
                        if c.get("type") in ("DATE", "DATETIME")
                        and (not keywords.get("column")  or match_kw("column", c))
                        and (not keywords.get("-column") or not match_kw("-column", c))
                    ]
                    if not datecols:
                        kw_sql += (" OR " if kw_sql else "") + "1 = 0"
                        break # for word

                    date_words, dates = [None] * 2, [None] * 2
                    if ".." not in word:
                        # Single date value given: use strftime matching
                        ymd = list(map(util.to_int, word.split("-")[:3]))
                        while len(ymd) < 3: ymd.append(None) # Ensure 3 values
                        if not any(ymd): # No valid values given: skip
                            continue # for word
                        format, value = "", ""
                        for j, (frm, val) in enumerate(zip("Ymd", ymd)):
                            if val is None: continue # for j, (frm, val)
                            format += ("-" if format else "") + "%" + frm
                            value += ("-" if value else "")
                            value += "%02d" % val if j else "%04d" % val
                        param = "timestamp_%s" % len(sql_params)
                        sql_params[param] = value
                        for j, col in enumerate(datecols):
                            temp = "STRFTIME('%s', %s) = :%s"
                            x = temp % (format, grammar.quote(col["name"]), param)
                            sql += (" OR " if j else "") + x
                        if len(datecols) > 1: sql = "(%s)" % sql

                    else:
                        # Date range given: use timestamp matching
                        date_words = word.split("..", 1)

                    for i, d in ((i, d) for i, d in enumerate(date_words) if d):
                        parts = filter(None, d.split("-")[:3])
                        ymd = list(map(util.to_int, parts))
                        if not ymd or ymd[0] is None:
                            continue # for i, d
                        while len(ymd) < 3: ymd.append(None) # Ensure 3 values
                        ymd[0] = max(min(ymd[0], 9999), 1) # Year in 1..9999
                        # Force month into legal range
                        if ymd[1] is None:
                            ymd[1] = [1, 12][i]
                        else:
                            ymd[1] = max(min(ymd[1], 12), 1) # Month in 1..12
                        # Force day into legal range
                        day_max = calendar.monthrange(*ymd[:2])[1]
                        if ymd[2] is None:
                            ymd[2] = day_max if i else 1
                        else:
                            ymd[2] = max(min(ymd[2], day_max), 1)
                        dates[i] = datetime.date(*ymd)
                    for i, d in ((i, d) for i, d in enumerate(dates) if d):
                        param = "timestamp_%s" % len(sql_params)
                        sql_params[param] = d
                        colsql = ""
                        for j, col in enumerate(datecols):
                            colsql += (" OR " if j else "")
                            colsql += "%s %s :%s" % (
                                      grammar.quote(col["name"]), [">=", "<="][i], param)
                        sql += (" AND " if sql else "")
                        sql += "(%s)" % (colsql) if len(datecols) > 1 else colsql

                if sql: kw_sql += (" OR " if kw_sql else "") + sql
            if kw_sql:
                negation = keyword.startswith("-")
                result += " AND " if result else ""
                result += "%s(%s)" % ("NOT " if negation else "", kw_sql)
        return result


    def _flatten(self, items):
        """
        Flattens the list to a single level, if possible,
        e.g. [[['a', 'b']]] to ['a', 'b'].
        """
        result = items
        while len(result) == 1 and not isinstance(result, basestring):
            result = result[0]
        result = [result]
        return result


    def _escape(self, item, wildcards=""):
        """
        Escapes special SQLite characters _% in item.

        @param   wildcards  characters to replace with SQL wildcard %
        """
        result   = item.replace("%", ESCAPE_CHAR + "%")
        result = result.replace("_", ESCAPE_CHAR + "_")
        if wildcards:
            result = "".join(result.replace(c, "%") for c in wildcards)
        return result


    def _join_strings(self, strings, glue=" AND "):
        """
        Returns the non-empty strings joined together with the specified glue.

        @param   glue  separator used as glue between strings
        @return        (joined string, number of strings actually used)
        """
        strings = list(filter(None, strings))
        return glue.join(strings), len(strings)



def test():
    DO_TRACE = True
    TEST_QUERIES = [
        'WORDTEST word "quoted words"',
        'ORTEST OR singleword OR (grouped words) OR lastword',
        'NEGATIONTEST -notword -"not this phrase" -(not these words) '
                     '-table:notthistable -column:notthiscolumn -date:1..9999',
        'WILDCARDTEST under_score percent% wild*card table:notawild*card',
        'DATETEST date:2002 -date:2002-12-24..2003 date:..2002-12-29 '
                 'date:*-*-24',
        'CHARACTERTEST ragnarök OR bust!½{[]}\\$$£@~§´` table:jörmungandr',
        'KEYWORDTEST --table:notkeyword tables:notkeyword table: singleword '
                    'table:"quoted title" date:t date:20022-x-20..2003-x-y',
        'WORDFAILTEST table:parens in(anyword',
        'BIGTEST OR word OR (grouped words) OR -(excluded grouped words) '
                'OR -excludedword OR (word2 OR (nested grouped words)) '
                'date:2011-11..2013-02 -date:2012-06..2012-08 '
                '-(excluded last grouped words) (last grouped words) '
                '(last (nested grouped words)) verylastword',
    ]
    import textwrap

    parser = SearchQueryParser()
    # Decorate SearchQueryParser._makeSQL() with a print logger
    loglines = [] # Cached trace lines
    def makeSQLLogger(func):
        level = [0] # List as workaround: enclosing scope cannot be reassigned
        def inner(parseresult, words, keywords, sql_params, item=None, parent_name=None):
            txt = "%s_makeSQL(<%s> %s, parent_name=%s)" % \
                  ("  " * level[0], parseresult.__class__.__name__, item, parent_name)
            if hasattr(parseresult, "getName"):
                txt += ", name=%s" % parseresult.getName()
            loglines.append(txt)
            level[0] += 1
            result = func(parseresult, words, keywords, sql_params, item, parent_name)
            level[0] -= 1
            loglines.append("%s = %s." % (txt, result))
            return result
        return inner
    if DO_TRACE:
        parser._makeSQL = makeSQLLogger(parser._makeSQL)

    for i, item in enumerate(TEST_QUERIES):
        del loglines[:]
        print("\n%s\n" % ("-" * 60) if i else "")
        print("QUERY: %s" % repr(item))
        d1 = datetime.datetime.now()
        r = parser.Parse(item)
        d2 = datetime.datetime.now()
        print("\n".join(loglines))
        print("PARSE DURATION: %s" % (d2 - d1))
        try:
            parsetree = parser._grammar.parseString(item, parseAll=True)
            print("PARSE TREE: %s" % parsetree)
        except Exception as e:
            print("PARSE TREE: FAILED: %s" % e)
        sql, params, words, keywords = r
        for name, value in params.items():
            sql = sql.replace(":%s " % name, '"%s" ' % value)
            sql = sql.replace(":%s)" % name, '"%s")' % value)
        wrapper = textwrap.TextWrapper(width=140, subsequent_indent="  ",
                                       replace_whitespace=False,
                                       drop_whitespace=False)
        print("SQL: %s" % "\n".join(wrapper.wrap(sql)))
        print("PARAMS: %s" % "\n".join(wrapper.wrap(repr(params))))
        print("WORDS: %s" % repr(words))
        print("QUERY: %s" % item)



if "__main__" == __name__:
    test()
