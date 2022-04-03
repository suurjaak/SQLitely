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
@modified    26.03.2022
"""
import calendar
import collections
import datetime
import logging
import re
import string
import warnings

import six
from six import unichr

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
ESCAPE_LIKE = "\\" # Character used to escape SQLite LIKE special characters _%


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


    def Parse(self, query, case=False, item=None):
        """
        Parses the query string and returns (sql, sql params, words).

        @param   case  whether search is case-sensitive
        @param   item  if set, search is performed on all the fields of this
                       specific table or view
                       {"name": "Item name", "columns": [{"name"}, ]}
        @return        (SQL string, SQL parameter dict, word and phrase list,
                        keyword map); phrases as tuple-wrapped single strings
        """
        words = [] # All encountered text words and quoted phrases
        keywords = collections.defaultdict(list) # {"table": [], "column": [], ..}
        params = {} # Parameters for SQL query {"like0": "%word%", ..}

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
                    keywords[key.lower()].append(value if case else value.lower())
                    split_words.remove(word)
            try:
                parse_results = ParseResults(split_words)
            except NameError: # pyparsing.ParseResults not available
                parse_results = split_words

        words, keywords = self._parseWords(parse_results, words, keywords, case)
        result, params = self._makeSQL(parse_results, params, keywords, case, item)
        match_kw = lambda k, x: match_words(x["name"], keywords[k], any, case)
        if item:
            skip_item = False
            for kw in keywords:
                if (item["type"] == kw and not match_kw(item["type"], item)) \
                or ("-" + item["type"] == kw and match_kw("-" + item["type"], item)):
                    skip_item = True
                    break # for kw
            if skip_item:
                result = ""
            else:
                kw_sql = self._makeKeywordsSQL(keywords, params, item)
                result = "SELECT * FROM %s%s%s%s%s" % (
                         grammar.quote(item["name"]),
                         " WHERE " if result else "", result,
                         " AND " if result and kw_sql else "", kw_sql)
        else:
            kw_sql = self._makeKeywordsSQL(keywords, params, item)
        if not item and kw_sql:
            result = "%s%s" % ("%s AND " % result if result else "", kw_sql)

        return result, params, words, keywords


    def _parseWords(self, parseresult, words, keywords, case=False, parent_name=None):
        """Populates the words and keywords collections."""
        if isinstance(parseresult, six.string_types):
            words.append(parseresult if "QUOTES" != parent_name else (parseresult, ))
            return words, keywords

        # ParseResults instance
        name = hasattr(parseresult, "getName") and parseresult.getName()
        elements, negation = parseresult, ("NOT" == name)
        if "KEYWORD" == name:
            key, word = elements[0].split(":", 1)
            key, word = key.lower(), (word if case else word.lower())
            if key in ["table",  "-table",  "view", "-view",
                       "column", "-column", "date", "-date"]:
                if getattr(elements, "QUOTES", None): word = (word, )
                keywords[key].append(word)
                return words, keywords
        elif "PARENTHESIS" == name:
            name_elem0 = getattr(elements[0], "getName", lambda: "")()
            if len(elements) and "NOT_PARENTHESIS" == name_elem0:
                negation = bool(elements[0])
                elements = elements[1:] # Drop the optional "-" in front
        elif "QUOTES" == name:
            elements = flatten(elements)
        mywords = [] if negation else words # No words from negations
        for elem in elements: self._parseWords(elem, mywords, keywords, case, name)
        return words, keywords


    def _makeSQL(self, parseresult, params, keywords, case, item, parent_name=None):
        """
        Returns the ParseResults item as an SQL string,
        appending parameter values to params.
        """
        result = ""
        if not item: return result, params
        match_kw = lambda k, x: match_words(x["name"], keywords[k], any, case)

        if isinstance(parseresult, six.string_types):
            op, wild = ("GLOB", "*") if case else ("LIKE", "%")
            safe = escape(parseresult, "QUOTES" == parent_name)

            i = len(params)
            for col in item["columns"]:
                if (keywords.get("column") and not match_kw("column", col)) \
                or (keywords.get("-column") and match_kw("-column", col)):
                    continue # for col

                cname = grammar.quote(col["name"])
                if "notnull" not in col: cname = "COALESCE(%s, '')" % cname
                result_col = "%s %s :like%s" % (cname, op, i)
                if not case and len(safe) > len(parseresult):
                    result_col += " ESCAPE '%s'" % ESCAPE_LIKE
                result += (" OR " if result else "") + result_col
            if not result: return "1 = 0", params # No matching columns

            if len(item["columns"]) > 1: result = "(%s)" % result
            params["like%s" % i] = wild + safe + wild
        else:
            elements = parseresult
            name = hasattr(parseresult, "getName") and parseresult.getName()
            negation = ("NOT" == name)
            if "KEYWORD" == name: return result, params
            elif "PARENTHESIS" == name:
                name_elem0 = getattr(elements[0], "getName", lambda: "")()
                if len(elements) and "NOT_PARENTHESIS" == name_elem0:
                    negation = bool(elements[0])
                    elements = elements[1:] # Drop the optional "-" in front
            elif "QUOTES" == name:
                elements = flatten(elements)
            parseds = [self._makeSQL(x, params, keywords, case, item, name)[0]
                       for x in elements]
            glue = " OR " if name in ("OR_OPERAND", "OR_EXPRESSION") else " AND "
            result, count = join_strings(parseds, glue)
            result = "(%s)"   % result if count > 1 else result
            result = "NOT %s" % result if negation else result
        return result, params


    def _makeKeywordsSQL(self, keywords, params, item):
        """
        Returns the keywords as an SQL string, appending SQL argument values
        to parameters dictionary.
        """
        result = ""
        match_kw = lambda k, x: match_words(x["name"], keywords[k], any)
        kw_sqls  = {} # {"date": [], "-date": []}

        for keyword, word in ((k, w) for k, ww in keywords.items() for w in ww):
            if not keyword.endswith("date"): continue # Only dates go into SQL

            datecols = [c for c in (item or {}).get("columns", [])
                if c.get("type") in ("DATE", "DATETIME")
                and (not keywords.get("column")  or     match_kw( "column", c))
                and (not keywords.get("-column") or not match_kw("-column", c))
            ]
            if not datecols: return "1 = 0" # Force 0 results from query

            sql, date_words, dates = "", [None] * 2, [None] * 2
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
                param = "timestamp_%s" % len(params)
                params[param] = value
                for j, col in enumerate(datecols):
                    temp = "STRFTIME('%s', %s) = :%s"
                    if "notnull" not in col: temp = "COALESCE(STRFTIME('%s', %s), '') = :%s"
                    x = temp % (format, grammar.quote(col["name"]), param)
                    sql += (" OR " if j else "") + x
                if len(datecols) > 1: sql = "(%s)" % sql

            else:
                # Date range given: use timestamp matching
                date_words = word.split("..", 1)

            for i, d in ((i, d) for i, d in enumerate(date_words) if d):
                parts = list(filter(bool, d.split("-")[:3]))
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
                param = "timestamp_%s" % len(params)
                params[param] = d
                colsql = ""
                for j, col in enumerate(datecols):
                    cname = grammar.quote(col["name"])
                    if "notnull" not in col: cname = "COALESCE(%s, '')" % cname
                    colsql += (" OR " if j else "")
                    colsql += "%s %s :%s" % (
                              cname, [">=", "<="][i], param)
                sql += (" AND " if sql else "")
                sql += "(%s)" % (colsql) if len(datecols) > 1 else colsql

            if sql: kw_sqls.setdefault(keyword, []).append(sql)

        for keyword, sqls in kw_sqls.items():
            negation = keyword.startswith("-")
            result += " AND " if result else ""
            result += "%s(%s)" % ("NOT " if negation else "", " OR ".join(sqls))
        return result


def flatten(items):
    """
    Flattens the list to a single level, if possible,
    e.g. [[['a', 'b']]] to ['a', 'b'].
    """
    result = items
    while len(result) == 1 and isinstance(result, (list, tuple, ParseResults)):
        result = result[0]
    result = [result]
    return result


def escape(item, op="LIKE", exact=False):
    """
    Prepares string as parameter for SQLite LIKE/GLOB operator.

    @param   op         target SQL operator, "LIKE" or "GLOB"
    @param   exact      whether to do exact match, or to escape
                        LIKE/GLOB special characters %_ and *?
    @param   wildcards  characters to replace with SQL LIKE wildcard %
    """
    if "GLOB" == op: # Replace GLOB specials ?[ with single-char classes [?] [[]
        result = item.replace("[", "[[]").replace("?", "[?]")
        if exact: result = result.replace("*", "[*]")
    else: # Escape LIKE specials %_ with \% \_
        result = item.replace("%", ESCAPE_LIKE + "%").replace("_", ESCAPE_LIKE + "_")
        if exact: result = result.replace("*", "%") # Swap user-entered * with %
    return result


def join_strings(strings, glue=" AND "):
    """
    Returns the non-empty strings joined together with the specified glue.

    @param   glue  separator used as glue between strings
    @return        (joined string, number of strings actually used)
    """
    strings = list(filter(bool, strings))
    return glue.join(strings), len(strings)


def match_words(text, words, when=all, case=False):
    """
    Returns whether all words match given text.

    @param   words  [string matched as regex, (string matched as-is), ]
    @param   when   truth function to use, like all or any
    @param   case   whether match is case-sensitive
    """
    words_re = [x if isinstance(w, tuple) else x.replace(r"\*", ".*")
                for w in words for x in [re.escape(flatten(w)[0])]]
    text_search, flags = (text, 0) if case else (text.lower(), re.I)
    return when(re.search(y, text_search, flags) for y in words_re)



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
    if DO_TRACE:
        parser._makeSQL = makeSQLLogger(parser._makeSQL)

    item = {"name": "m", "type": "table",
            "columns": [{"name": "n"}, {"name": "d", "type": "DATETIME"}]}
    for i, text in enumerate(TEST_QUERIES):
        del loglines[:]
        print("\n%s\n" % ("-" * 60) if i else "")
        print("QUERY: %s" % repr(text))
        d1 = datetime.datetime.now()
        r = parser.Parse(text, item)
        d2 = datetime.datetime.now()
        print("\n".join(loglines))
        print("PARSE DURATION: %s" % (d2 - d1))
        try:
            parsetree = parser._grammar.parseString(text, parseAll=True)
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
        print("KEYWORDS: %s" % repr(keywords))
        print("QUERY: %s" % text)



if "__main__" == __name__:
    test()
