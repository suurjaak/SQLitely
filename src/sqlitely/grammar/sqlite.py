# -*- coding: utf-8 -*-
"""
SQLite parsing and generating functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     04.09.2019
@modified    13.12.2024
------------------------------------------------------------------------------
"""
import codecs
from collections import defaultdict
import json
import logging
import re
import traceback
import uuid

from antlr4 import InputStream, CommonTokenStream, TerminalNode, Token
import six
import step

from .. lib import util
from . import templates
from . SQLiteLexer import SQLiteLexer
from . SQLiteParser import SQLiteParser

"""Regex for matching unprintable characters (\x00 etc)."""
SAFEBYTE_RGX = re.compile(r"[\x00-\x1f\x7f-\xa0]")

logger = logging.getLogger(__name__)



@util.memoize(__nohash__=True)
def parse(sql, category=None, renames=None):
    """
    Returns data structure for SQL statement.

    @param   category  expected statement category if any, like "table"
    @param   renames   renames to perform in SQL statement body,
                       supported types "schema" (top-level rename only),
                       "table", "index", "trigger", "view", "column".
                       Schema renames as {"schema": s2} or {"schema": {s1: s2}},
                       category renames as {category: {v1: v2}},
                       column renames as {"column": {table or view: {c1: c2}}},
                       where category value should be the renamed value if
                       the same transform is renaming the category as well.
    @return            ({..}, None), or (None, error)
    """
    result, err = None, None
    try:
        result, err = Parser().parse(sql, category, renames=renames)
    except Exception as e:
        logger.exception("Error parsing SQL %s.", sql)
        err = util.format_exc(e)
    return result, err


def generate(data, indent="  ", category=None):
    """
    Returns SQL statement from data structure.

    @param   data      {"__type__": "CREATE TABLE"|.., ..}
    @param   indent    indentation level to use. If falsy,
                       result is not indented in any, including linefeeds.
    @param   category  data category if not using data["__type__"]
    @return            (SQL string, None) or (None, error)
    """
    if not data: return None, "Empty schema item"
    result, err, generator = None, None, Generator(indent)
    try:
        result, err = generator.generate(data, category=category)
    except Exception as e:
        logger.exception("Error generating SQL for %s.", data)
        err = util.format_exc(e)
    return result, err


@util.memoize
def get_type(sql):
    """
    Returns SQL statement type.

    @param  sql  SQL statement like "SELECT * FROM foo"
    @return      one of (SQL.DELETE, SQL.INSERT, SQL.SELECT, SQL.UPDATE), or None
    """
    result = None
    try:
        parser = SQLiteParser(CommonTokenStream(SQLiteLexer(InputStream(sql))))
        parser.removeErrorListeners()
        tree = parser.parse()
        if sum(not isinstance(x, TerminalNode) for x in tree.children) > 1 \
        or sum(not isinstance(x, TerminalNode) for x in tree.children[0].children) > 1:
            raise Exception("Too many statements")
        ctx = tree.children[0].children[0].children[0]
        if isinstance(ctx, (CTX.DELETE, CTX.DELETE_LIMITED)):
            result = SQL.DELETE
        elif isinstance(ctx, CTX.INSERT):
            result = SQL.INSERT
        elif isinstance(ctx, (CTX.SELECT, CTX.SELECT_COMPOUND,
                              CTX.SELECT_FACTORED, CTX.SELECT_SIMPLE)):
            result = SQL.SELECT
        elif isinstance(ctx, (CTX.UPDATE, CTX.UPDATE_LIMITED)):
            result = SQL.UPDATE
    except Exception:
        logger.exception("Error determining type of SQL %r.", sql)
    return result


@util.memoize(__nohash__=True)
def transform(sql, flags=None, renames=None, indent="  "):
    """
    Returns transformed SQL.

    @param   flags    flags to toggle, like {"exists": True}
    @param   renames  renames to perform in SQL statement body,
                      supported types "schema" (top-level rename only),
                      "table", "index", "trigger", "view", "column".
                      Schema renames as {"schema": s2} or {"schema": {s1: s2}},
                      category renames as {category: {v1: v2}},
                      column renames as {"column": {table or view: {c1: c2}}},
                      where category value should be the renamed value if
                      the same transform is renaming the category as well.
    @param   indent   indentation level to use. If falsy,
                      result is not indented in any, including linefeeds.
    @return           (SQL string, None) or (None, error)
    """
    result, err, parser = None, None, Parser()
    try:
        data, err = parser.parse(sql, renames=renames)
        if data and (flags or not indent):
            if flags: data.update(flags)
            result, err = Generator(indent).generate(data)
        elif data: result = parser.get_text()
    except Exception as e:
        logger.exception("Error transforming SQL %s.", sql)
        err = util.format_exc(e)
    return result, err


@util.memoize
def quote(val, force=False, allow="", embed=False):
    """
    Returns value in quotes and proper-escaped for queries,
    if name needs quoting (has non-alphanumerics or starts with number)
    or if force set. Always returns a string.

    @param   allow  extra characters to allow without quoting
    @param   embed  quote only if empty string or contains quotes or starts/ends with spaces
    """
    pattern = r"(^[^\w\d%s])|(?=[^\w%s])" % ((re.escape(allow) ,) * 2) \
              if allow else r"(^[\W\d])|(?=\W)"
    result = uni(val) or ""
    if "" == val or force or result.upper() in RESERVED_KEYWORDS \
    or re.search(pattern, result, re.U):
        if not embed or '"' in result or re.search("^$|^ | $", result):
            result = u'"%s"' % result.replace('"', '""')
    return result


@util.memoize
def unquote(val):
    """
    Returns unquoted string, if string within '' or "" or `` or [].
    Converts value to string if not already.
    """
    result = uni(val) or ""
    if re.match(r"^([\"].*[\"])|([\'].*[\'])|([\`].*[\`])|([\[].*[\]])$", result, re.DOTALL):
        result, sep = result[1:-1], result[0]
        if sep != "[": result = result.replace(sep * 2, sep)
    return result


def format(value, coldata=None):
    """Formats a value for use in an SQL statement like INSERT."""
    result = None
    if value is None: result = "NULL"
    elif isinstance(value, six.integer_types + (float, )): result = str(value)
    elif not isinstance(value, six.string_types): value = str(value)

    if result is None:
        if isinstance(coldata, dict) \
        and isinstance(coldata.get("type"), six.string_types) \
        and "JSON" == coldata["type"].upper():
            try: result = "'%s'" % json.dumps(json.loads(value))
            except Exception: pass

        if result is None and SAFEBYTE_RGX.search(value):
            if isinstance(value, six.text_type):
                try:
                    value = value.encode("latin1")
                except UnicodeError:
                    value = value.encode("utf-8", errors="backslashreplace")
            result = "X'%s'" % codecs.encode(value, "hex").decode("latin1").upper()
        elif result is None:
            if isinstance(value, six.text_type):
                value = value.encode("utf-8").decode("latin1")
            result = "'%s'" % value.replace("'", "''")
    return result


def strip_and_collapse(sql, literals=True, upper=True):
    """
    Returns SQL with comments stripped and string/identifier literals reduced to empty placeholders,
    surrounding whitespace and semicolons removed and inner whitespace collapsed.

    @param   literals  do collapse string/identifier literals, or retain as is
    @param   upper     return in uppercase
    """
    placeholders = {}
    def repl(match): # Store match and return placeholder key
        key = ("<%s>" % (uuid.uuid4())).upper()
        placeholders[key] = match.group(0)
        return key

    # Strip single-line comments
    sql = re.sub("%s.*$" % re.escape("--"), "", sql, flags=re.MULTILINE)
    # Strip multi-line comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL) # Leave space if e.g. "SELECT/**/COL"
    # Reduce string literals to empty strings or placeholders
    sql = re.sub('"([^"]|"")*"',  '""' if literals else repl, sql)
    sql = re.sub("'([^']|'')*'",  "''" if literals else repl, sql)
    # Reduce identifiers to empty strings or placeholders
    sql = re.sub("`([^`]|``)*`",  "``" if literals else repl, sql)
    sql = re.sub(r"\[([^\]])*\]", "[]" if literals else repl, sql)
    # Strip whitespace inside brackets
    sql = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", sql))
    # Collapse all whitespace to single space and strip surrounding whitespace and semicolons
    sql = re.sub(r"\s+", " ", re.sub(r"^[\s;]+|[\s;]*$", "", sql.upper() if upper else sql))
    # Replace temporary placeholders with original literals if any
    for k, v in placeholders.items(): sql = sql.replace(k, v, 1)
    return sql


def terminate(sql, data=None):
    """
    Returns given SQL statement terminated with semicolon, if not already.

    Adds a linefeed before terminator if statement ends with a line comment.

    @param   sql   any statement of recognized type, e.g. "CREATE VIEW foo AS SELECT 3 -- comment"
    @param   data  parsed metadata dictionary, statement will be parsed if not given
    """
    sql = sql.rstrip()
    if data is None:
        data = {}
        try:
            stream = CommonTokenStream(SQLiteLexer(InputStream(sql)))
            parser = SQLiteParser(stream)
            parser.removeErrorListeners()
            tree = parser.parse()
            comments = stream.filterForChannel(0, len(stream.tokens) - 1, channel=2) or []
            data["__comments__"]   = {x.start: x.text for x in comments}
            data["__terminated__"] = any(isinstance(x, TerminalNode) and ";" == x.getText() and
                                         any(c.start > x.getSourceInterval()[0] for c in comments)
                                         for x in tree.children[0].children[1:])
        except Exception: pass
    if data and data.get("__terminated__"): return sql
    if data and data.get("__comments__") \
    and any(int(n) + len(s) >= len(sql) for n, s in data["__comments__"].items()):
        sql += "\n"
    return sql if sql.endswith(";") else (sql + ";")


def uni(x, encoding="utf-8"):
    """Convert anything to Unicode, except None."""
    if x is None or isinstance(x, six.text_type): return x
    if isinstance(x, six.binary_type): return six.text_type(x, encoding, errors="replace")
    return six.text_type(x)


def collapse_whitespace(s):
    """Collapse all whitespace into a single space, and strip if between non-alphanumerics."""
    return re.sub(r"(\W)\s+(\W)", r"\1\2", re.sub(r"\s+", " ", s), re.U)



class SQL(object):
    """SQL word constants."""
    AFTER                = "AFTER"
    ALTER_TABLE          = "ALTER TABLE"
    AUTOINCREMENT        = "AUTOINCREMENT"
    BEFORE               = "BEFORE"
    CHECK                = "CHECK"
    COLLATE              = "COLLATE"
    COLUMN               = "COLUMN"
    CONSTRAINT           = "CONSTRAINT"
    CREATE_INDEX         = "CREATE INDEX"
    CREATE_TABLE         = "CREATE TABLE"
    CREATE_TRIGGER       = "CREATE TRIGGER"
    CREATE_VIEW          = "CREATE VIEW"
    CREATE_VIRTUAL_TABLE = "CREATE VIRTUAL TABLE"
    CREATE               = "CREATE"
    DEFAULT              = "DEFAULT"
    DEFERRABLE           = "DEFERRABLE"
    DELETE               = "DELETE"
    EXPLAIN              = "EXPLAIN"
    FOR_EACH_ROW         = "FOR EACH ROW"
    FOREIGN_KEY          = "FOREIGN KEY"
    INSERT               = "INSERT"
    INITIALLY            = "INITIALLY"
    INSTEAD_OF           = "INSTEAD OF"
    MATCH                = "MATCH"
    NOT_NULL             = "NOT NULL"
    NOT                  = "NOT"
    ON_CONFLICT          = "ON CONFLICT"
    ON                   = "ON"
    PRAGMA               = "PRAGMA"
    PRIMARY_KEY          = "PRIMARY KEY"
    REFERENCES           = "REFERENCES"
    SELECT               = "SELECT"
    TABLE                = "TABLE"
    TEMPORARY            = "TEMPORARY"
    UNIQUE               = "UNIQUE"
    UPDATE               = "UPDATE"
    WITHOUT_ROWID        = "WITHOUT ROWID"



class CTX(object):
    """Parser context shorthands."""
    CREATE_INDEX         = SQLiteParser.Create_index_stmtContext
    CREATE_TABLE         = SQLiteParser.Create_table_stmtContext
    CREATE_TRIGGER       = SQLiteParser.Create_trigger_stmtContext
    CREATE_VIEW          = SQLiteParser.Create_view_stmtContext
    CREATE_VIRTUAL_TABLE = SQLiteParser.Create_virtual_table_stmtContext
    DELETE               = SQLiteParser.Delete_stmtContext
    DELETE_LIMITED       = SQLiteParser.Delete_stmt_limitedContext
    INSERT               = SQLiteParser.Insert_stmtContext
    SELECT               = SQLiteParser.Select_stmtContext
    SELECT_COMPOUND      = SQLiteParser.Compound_select_stmtContext
    SELECT_FACTORED      = SQLiteParser.Factored_select_stmtContext
    SELECT_SIMPLE        = SQLiteParser.Simple_select_stmtContext
    JOIN_CLAUSE          = SQLiteParser.Join_clauseContext
    UPDATE               = SQLiteParser.Update_stmtContext
    UPDATE_LIMITED       = SQLiteParser.Update_stmt_limitedContext
    COLUMN_DEF           = SQLiteParser.Column_defContext
    COLUMN_NAME          = SQLiteParser.Column_nameContext
    INDEX_NAME           = SQLiteParser.Index_nameContext
    SCHEMA_NAME          = SQLiteParser.Schema_nameContext
    TABLE_NAME           = SQLiteParser.Table_nameContext
    TRIGGER_NAME         = SQLiteParser.Trigger_nameContext
    VIEW_NAME            = SQLiteParser.View_nameContext
    EXPRESSION           = SQLiteParser.ExprContext
    LITERAL_VALUE        = SQLiteParser.Literal_valueContext
    FOREIGN_TABLE        = SQLiteParser.Foreign_tableContext
    FOREIGN_KEY          = SQLiteParser.Foreign_key_clauseContext
    SELECT_CORE          = SQLiteParser.Select_coreContext
    RESULT_COLUMN        = SQLiteParser.Result_columnContext


"""Words that need quoting if in name context, e.g. table name."""
RESERVED_KEYWORDS = ["ABORT", "ACTION", "ADD", "AFTER", "ALL", "ALTER", "ALWAYS", "ANALYZE", "AND",
    "AS", "ASC", "ATTACH", "AUTOINCREMENT", "BEFORE", "BEGIN", "BETWEEN", "BY", "CASCADE", "CASE",
    "CAST", "CHECK", "COLLATE", "COLUMN", "COMMIT", "CONFLICT", "CONSTRAINT", "CREATE", "CROSS",
    "CURRENT", "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP", "DATABASE", "DEFAULT",
    "DEFERRABLE", "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DO", "DROP", "EACH", "ELSE",
    "END", "ESCAPE", "EXCEPT", "EXCLUDE", "EXCLUSIVE", "EXISTS", "EXPLAIN", "FAIL", "FILTER",
    "FIRST", "FOLLOWING", "FOR", "FOREIGN", "FROM", "FULL", "GENERATED", "GLOB", "GROUP", "GROUPS",
    "HAVING", "IF", "IGNORE", "IMMEDIATE", "IN", "INDEX", "INDEXED", "INITIALLY", "INNER", "INSERT",
    "INSTEAD", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "KEY", "LAST", "LEFT", "LIKE", "LIMIT",
    "MATCH", "MATERIALIZED", "NATURAL", "NO", "NOT", "NOTHING", "NOTNULL", "NULL", "NULLS", "OF",
    "OFFSET", "ON", "OR", "ORDER", "OTHERS", "OUTER", "OVER", "PARTITION", "PLAN", "PRAGMA",
    "PRECEDING", "PRIMARY", "QUERY", "RAISE", "RANGE", "RECURSIVE", "REFERENCES", "REGEXP",
    "REINDEX", "RELEASE", "RENAME", "REPLACE", "RESTRICT", "RETURNING", "RIGHT", "ROLLBACK", "ROW",
    "ROWS", "SAVEPOINT", "SELECT", "SET", "TABLE", "TEMP", "TEMPORARY", "THEN", "TIES", "TO",
    "TRANSACTION", "TRIGGER", "UNBOUNDED", "UNION", "UNIQUE", "UPDATE", "USING", "VACUUM", "VALUES",
    "VIEW", "VIRTUAL", "WHEN", "WHERE", "WINDOW", "WITH", "WITHOUT"
]


class ParseError(Exception):
    """Parse exception with line and column."""

    def __init__(self, message, line, column):
        Exception.__init__(self, message)
        self.message, self.line, self.column = message, line, column

    def __str__ (self): return str(self.message)



class Parser(object):
    """
    SQL statement parser.
    """

    CTXS = {
        CTX.CREATE_INDEX:          SQL.CREATE_INDEX,
        CTX.CREATE_TABLE:          SQL.CREATE_TABLE,
        CTX.CREATE_TRIGGER:        SQL.CREATE_TRIGGER,
        CTX.CREATE_VIEW:           SQL.CREATE_VIEW,
        CTX.CREATE_VIRTUAL_TABLE:  SQL.CREATE_VIRTUAL_TABLE,
    }
    BUILDERS = {
        SQL.CREATE_INDEX:          lambda self, ctx: self.build_create_index(ctx),
        SQL.CREATE_TABLE:          lambda self, ctx: self.build_create_table(ctx),
        SQL.CREATE_TRIGGER:        lambda self, ctx: self.build_create_trigger(ctx),
        SQL.CREATE_VIEW:           lambda self, ctx: self.build_create_view(ctx),
        SQL.CREATE_VIRTUAL_TABLE:  lambda self, ctx: self.build_create_virtual_table(ctx),
    }
    RENAME_CTXS = {"index": CTX.INDEX_NAME, "trigger": CTX.TRIGGER_NAME,
                   "view":  (CTX.VIEW_NAME, CTX.TABLE_NAME), "column":  CTX.COLUMN_NAME,
                   "table": (CTX.TABLE_NAME, CTX.FOREIGN_TABLE),
                   "virtual table": CTX.TABLE_NAME}
    CATEGORIES = {"index":   SQL.CREATE_INDEX,   "table": SQL.CREATE_TABLE,
                  "trigger": SQL.CREATE_TRIGGER, "view":  SQL.CREATE_VIEW,
                  "virtual table":  SQL.CREATE_VIRTUAL_TABLE}
    TRIGGER_BODY_CTXS = [CTX.DELETE, CTX.DELETE_LIMITED, CTX.INSERT,
                         CTX.SELECT, CTX.SELECT_COMPOUND, CTX.SELECT_FACTORED, CTX.SELECT_SIMPLE,
                         CTX.UPDATE, CTX.UPDATE_LIMITED]

    class ErrorListener(object):
        """Collects errors during parsing."""
        def __init__(self): self._errors, self._stack = [], []

        def reportAmbiguity(self, *_, **__): pass

        def reportAttemptingFullContext(self, *_, **__): pass

        def reportContextSensitivity(self, *_, **__): pass

        def syntaxError(self, recognizer, offendingToken, line, column, msg, e):
            err = "Line %s:%s %s" % (line, column + 1, msg) # Column is 0-based
            self._errors.append(ParseError(err, line - 1, column)) # Line is 1-based
            if not self._stack:
                stack = traceback.extract_stack()[:-1]
                for i, (filename, lineno, functionname, linetext) in enumerate(stack):
                    if filename == __file__: # Retain only the stack from this file and lower
                        del stack[:max(i - 1, 0)]
                        break # for i, (..)
                self._stack = traceback.format_list(stack)

        def getErrors(self): return self._errors[:]

        def getStack(self):  return self._stack[:]


    def __init__(self):
        self._category = None # "CREATE TABLE" etc
        self._stream   = None # antlr TokenStream
        self._tree     = None # Parsed context tree


    def parse(self, sql, category=None, renames=None):
        """
        Parses the SQL statement and returns data structure.
        Result will have "__tables__" as a list of all the table and view names
        the SQL statement refers to, in lowercase.

        @param   sql       source SQL string
        @param   category  expected statement category if any, like "table"
        @param   renames   renames to perform in SQL statement body,
                           supported types "schema" (top-level rename only),
                           "table", "index", "trigger", "view", "column".
                           Schema renames as {"schema": s2} or {"schema": {s1: s2}},
                           category renames as {category: {v1: v2}},
                           column renames as {"column": {table or view: {c1: c2}}},
                           where category value should be the renamed value if
                           the same transform is renaming the category as well.
        @return            ({..}, None) or (None, error)

        """
        result, err = None, None
        ctx, errors = self.parse_tree(sql, category)
        if not errors: result = self.build(ctx, renames)
        else: err = "\n\n".join(util.ellipsize(e.message, limit=150) if isinstance(e, ParseError)
                                else e for e in errors)
        return result, err


    def parse_tree(self, sql, category=None):
        """
        Parses the SQL statement, returns (root context, [ParseError or str, ] or None).

        @param   sql       source SQL string
        @param   category  expected statement category if any, like "table"
        """
        self._stream = CommonTokenStream(SQLiteLexer(InputStream(sql)))
        parser, listener = SQLiteParser(self._stream), self.ErrorListener()
        parser.removeErrorListeners()
        parser.addErrorListener(listener)

        tree = parser.parse()
        if parser.getNumberOfSyntaxErrors():
            errors = listener.getErrors()
            logger.error('Errors parsing SQL "%s":\n\n%s\n%s',
                         sql, "\n\n".join(e.message for e in errors), "".join(listener.getStack()))
            return None, errors

        if sum(not isinstance(x, TerminalNode) for x in tree.children) > 1 \
        or sum(not isinstance(x, TerminalNode) for x in tree.children[0].children) > 1:
            stmts = [x for x in tree.children if not isinstance(x, TerminalNode)] or \
                    [x for x in tree.children[0].children if not isinstance(x, TerminalNode)]
            logger.error('Error parsing SQL "%s":\n\n'
                         "encountered %s statements where one was expected.", sql, len(stmts))
            return None, ["Too many statements"]

        # parse ctx -> statement list ctx -> statement ctx -> specific type ctx
        ctx = tree.children[0].children[0].children[0]
        name = self.CTXS.get(type(ctx))
        categoryname = self.CATEGORIES.get(category)
        if category and name != categoryname or name not in self.BUILDERS:
            error = "Unexpected statement category: '%s'%s."% (name,
                     " (expected '%s')" % (categoryname or category)
                     if category else "")
            logger.error(error)
            return None, [error]
        self._category = name
        self._tree = tree
        return ctx, None


    def build(self, ctx, renames=None):
        """Returns data structure built from CREATE context, with renames applied if any."""
        if renames: self.recurse_rename([ctx], renames)
        result = self.BUILDERS[self._category](self, ctx)
        result["__type__"] = self._category
        ctxitems, ctxtypes = [ctx], [CTX.TABLE_NAME]
        if SQL.CREATE_TABLE == self._category: ctxtypes = [CTX.FOREIGN_TABLE]
        if SQL.CREATE_TRIGGER == self._category: # Skip trigger header
            ctxitems = [ctx.expr()] + ctx.select_stmt() + ctx.update_stmt() + \
                       ctx.insert_stmt() + ctx.delete_stmt()
        result["__tables__"] = self.recurse_collect(ctxitems, ctxtypes)
        if renames and "schema" in renames:
            if isinstance(renames["schema"], dict):
                for v1, v2 in renames["schema"].items():
                    if util.lceq(result.get("schema"), v1):
                        if v2: result["schema"] = v2
                        else: result.pop("schema", None)
            elif renames["schema"]: result["schema"] = renames["schema"]
            else: result.pop("schema", None)
            self.rename_schema(ctx, renames)

        comments = self._stream.filterForChannel(0, len(self._stream.tokens) - 1, channel=2) or []
        result["__comments__"] = {x.start: x.text for x in comments}
        result["__terminated__"] = any(isinstance(x, TerminalNode) and ";" == x.getText() and
                                       any(c.start > x.getSourceInterval()[0] for c in comments)
                                       for x in self._tree.children[0].children[1:])
        return result


    def rename_schema(self, ctx, renames):
        """Alters stream tokens to add, change or remove schema name, for get_text()."""
        srenames = renames["schema"]

        sctx = next((x for x in ctx.children if isinstance(x, CTX.SCHEMA_NAME)), None)
        if sctx:
            # Schema present in statement: modify content or remove token
            if isinstance(srenames, six.string_types):
                sctx.start.text = util.to_unicode(srenames)
            elif srenames is None or isinstance(srenames, dict) \
            and any(v is None and util.lceq(k, self.u(sctx)) for k, v in srenames.items()):
                idx = self._stream.tokens.index(sctx.start)
                del self._stream.tokens[idx:idx + 2] # Remove schema and dot tokens
            elif isinstance(srenames, dict) \
            and any(util.lceq(k, self.u(sctx)) for k, v in srenames.items()):
                sctx.start.text = util.to_unicode(next(v for k, v in srenames.items()
                                                       if util.lceq(k, self.u(sctx))))
        elif isinstance(srenames, six.string_types):
            # Schema not present in statement: insert tokens before item name token
            cname = next(k for k, v in self.CATEGORIES.items() if v == self._category)
            ctype = self.RENAME_CTXS[cname]
            nctx = next((x for x in ctx.children if isinstance(x, ctype)), None)
            if nctx:
                ntoken = Token()
                ntoken.text = util.to_unicode(srenames)
                dtoken = Token()
                dtoken.text = u"."
                idx = self._stream.tokens.index(nctx.start)
                self._stream.tokens[idx:idx] = [ntoken, dtoken]


    def get_text(self):
        """Returns full text of current input stream."""
        return self._stream.getText()


    def t(self, ctx):
        """
        Returns context (or context callable result) text content,
        uppercase if terminal node.
        """
        if callable(ctx): ctx = ctx()
        result = ctx and ctx.getText()
        return result.upper() if isinstance(ctx, TerminalNode) else result


    def r(self, ctx, ctx2=None):
        """
        Returns context (or context callable result) raw text content from SQL,
        or raw text between two contexts, exclusive if terminal node tokens.
        """
        ctx, ctx2 = (x() if callable(x) else x for x in (ctx, ctx2))
        if ctx and ctx2:
            interval = ctx.getSourceInterval()[0], ctx2.getSourceInterval()[1]
        else: interval = ctx.getSourceInterval()
        result = self._stream.getText(*interval)

        for c in (ctx, ctx2) if ctx and ctx2 else ():
            if not isinstance(c, TerminalNode): continue # for c
            upper = self.t(c)
            a, b = (None, len(upper)) if c is ctx else (-len(upper), None)
            if result[a:b].upper() == upper: result = result[b:a]
        return result


    def u(self, ctx):
        """
        Returns context (or context callable result) text content, unquoted.
        """
        return unquote(self.t(ctx))


    def build_create_index(self, ctx):
        """
        Assembles and returns CREATE INDEX data, as {
            name:     index name
            table:    table the index is on
            ?schema:  index schema name
            ?exists:  True if IF NOT EXISTS
            ?unique:  True if UNIQUE
            columns:  [{?name, ?expr, ?collate, ?order}, ]
            where:    index WHERE SQL expression
        }.
        """
        result = {}

        result["name"]  = self.u(ctx.index_name)
        result["table"] = self.u(ctx.table_name)
        if ctx.schema_name(): result["schema"] = self.u(ctx.schema_name)
        if ctx.K_UNIQUE(): result["unique"]  = True
        if ctx.K_EXISTS(): result["exists"]  = True

        result["columns"] = []
        for c in ctx.indexed_column():
            col = {}
            if c.column_name(): col["name"] = self.u(c.column_name)
            elif c.expr(): col["expr"] = self.r(c.expr())
            if c.K_COLLATE():
                col["collate"] = self.u(c.collation_name).upper()
            if c.K_ASC() or c.K_DESC():
                col["order"] = self.t(c.K_ASC() or c.K_DESC())
            result["columns"].append(col)

        if ctx.expr(): result["where"] = self.r(ctx.expr())

        return result


    def build_create_table(self, ctx):
        """
        Assembles and returns CREATE TABLE data, as {
          name:          table name
          ?schema:       table schema name
          ?temporary:    True if TEMPORARY | TEMP
          ?exists:       True if IF NOT EXISTS
          columns:       [{name, ..}]
          ?constraints:  [{type, ..}]
          ?options:      [{"without" if WITHOUT ROWID or "strict" if STRICT: True}, ]
        }.
        """
        result = {}

        result["name"] = self.u(ctx.table_name)
        if ctx.schema_name(): result["schema"]  = self.u(ctx.schema_name)
        if ctx.K_TEMP() or ctx.K_TEMPORARY(): result["temporary"] = True
        if ctx.K_EXISTS(): result["exists"]  = True

        result["columns"] = [self.build_table_column(x) for x in ctx.column_def()]
        if ctx.table_constraint():
            result["constraints"] = [self.build_table_constraint(x) for x in ctx.table_constraint()]

        for optctx in ctx.table_option():
            for flag, key in ((optctx.K_WITHOUT, "without"), (optctx.C_STRICT, "strict")):
                if flag() and not any(key in x for x in result.get("options", [])):
                    result.setdefault("options", []).append({key: True})

        return result


    def build_create_trigger(self, ctx):
        """
        Assembles and returns CREATE TRIGGER data, as {
          name:        trigger name
          table:       table to trigger on
          action:      DELETE | INSERT | UPDATE
          body:        trigger body SQL expression
          ?schema:     trigger schema name
          ?temporary:  True if TEMPORARY | TEMP
          ?exists:     True if IF NOT EXISTS
          ?upon:       BEFORE | AFTER | INSTEAD OF
          ?columns:    {"name": column_name}, ] for UPDATE OF action
          ?for:        True if FOR EACH ROW
          ?when:       trigger WHEN-clause SQL expression
        }.
        """
        result = {}

        result["name"] = self.u(ctx.trigger_name)
        if ctx.schema_name(0): result["schema"]  = self.u(ctx.schema_name(0))
        if ctx.K_TEMP() or ctx.K_TEMPORARY(): result["temporary"] = True
        if ctx.K_EXISTS(): result["exists"]  = True

        upon = ctx.K_BEFORE() or ctx.K_AFTER()
        if upon: result["upon"] = self.t(upon)
        elif ctx.K_INSTEAD() and ctx.K_OF(): result["upon"] = SQL.INSTEAD_OF

        action = ctx.K_DELETE() or ctx.K_INSERT() or ctx.K_UPDATE()
        result["action"] = self.t(action)

        cols = ctx.column_name()
        if cols: result["columns"] =  [{"name": self.u(x) for x in cols}]

        result["table"] = self.u(ctx.table_name)

        if ctx.K_FOR() and ctx.K_EACH() and ctx.K_ROW():
            result["for"]  = SQL.FOR_EACH_ROW

        if ctx.K_WHEN():
            result["when"] = self.r(ctx.expr())

        body = self.r(ctx.K_BEGIN(), ctx.K_END()).rstrip(" \t")
        if body[:1]  == "\n": body = body[1:]
        if body[-1:] == "\n": body = body[:-1]
        result["body"] = body

        return result


    def build_create_view(self, ctx):
        """
        Assembles and returns CREATE VIEW data, as {
          name:          view name
          select:        view SELECT SQL expression
          ?schema:       table schema name
          ?temporary:    True if TEMPORARY | TEMP
          ?exists:       True if IF NOT EXISTS
          ?columns:      [column_name, ]
        }.
        """
        result = {}

        result["name"] = self.u(ctx.view_name)
        if ctx.schema_name(): result["schema"]  = self.u(ctx.schema_name)
        if ctx.K_TEMP() or ctx.K_TEMPORARY(): result["temporary"] = True
        if ctx.K_EXISTS(): result["exists"]  = True

        cols = ctx.column_name()
        if cols: result["columns"] =  [{"name": self.u(x)} for x in cols]
        result["select"] = self.r(ctx.select_stmt())

        return result


    def build_create_virtual_table(self, ctx):
        """
        Assembles and returns CREATE VIRTUAL TABLE data, as {
          name:          table name
          module:        namde of virtual table module
          ?schema:       table schema name
          ?exists:       True if IF NOT EXISTS
          ?arguments:    [module_argument, ]
        }
        """
        result = {}

        result["name"] = self.u(ctx.table_name)
        if ctx.schema_name(): result["schema"]  = self.u(ctx.schema_name)
        if ctx.K_EXISTS(): result["exists"]  = True
        result["module"] = {"name":  self.u(ctx.module_name)}
        args = ctx.module_argument()
        if args: result["module"]["arguments"] =  [self.r(x) for x in args]

        return result


    def build_table_column(self, ctx):
        """
        Assembles and returns column data for CREATE TABLE, as {
          name:                column name
          ?type:               column type
          ?pk                  { if PRIMARY KEY
              ?name            constraint name
              ?autoincrement:  True if AUTOINCREMENT
              ?order:          ASC | DESC
              ?conflict:       ROLLBACK | ABORT | FAIL | IGNORE | REPLACE
          ?
          ?notnull             { if NOT NULL
              ?name            constraint name
              ?conflict:       ROLLBACK | ABORT | FAIL | IGNORE | REPLACE
          ?
          ?unique              { if UNIQUE
              ?name            constraint name
              ?conflict:       ROLLBACK | ABORT | FAIL | IGNORE | REPLACE
          ?
          ?default             { if DEFAULT
              ?name            constraint name
              expr:            value or expression
          ?
          ?check               { if CHECK
              ?name            constraint name
              expr:            value or expression
          ?
          ?collate             { if COLLATE
              ?name            constraint name
              value:           NOCASE | ..
          ?
          ?fk:                 { if REFERENCES
              ?name            constraint name
              table:           foreign table
              key:             foreign table column name
              ?defer:          { if DEFERRABLE
                  ?not         True if NOT
                  ?initial:    DEFERRED | IMMEDIATE
              }
              ?action:         {
                  ?UPDATE:     SET NULL | SET DEFAULT | CASCADE | RESTRICT | NO ACTION
                  ?DELETE:     SET NULL | SET DEFAULT | CASCADE | RESTRICT | NO ACTION
              }
              ?match:          MATCH-clause value
          ?
          ?generated:
              ?name            constraint name
              expr:            value or expression
              ?type:           STORED | VIRTUAL
              ?always:         True if GENERATED ALWAYS
          ?
        }.
        """
        result = {}
        result["name"] = self.u(ctx.column_name().any_name)
        if ctx.type_name():
            if isinstance(ctx.type_name().type_name_text().children[0], TerminalNode):
                result["type"] = self.u(ctx.type_name().type_name_text().children[0]).upper()
            else:
                ww = ctx.type_name().type_name_text().type_or_constraint_name_word()
                result["type"] = unquote(" ".join(self.t(x).upper() for x in ww))
            if ctx.type_name().signed_number():
                result["type"] += "(%s)" % ",".join(self.t(x).upper() for x in ctx.type_name().signed_number())

        for c in ctx.column_constraint():
            conflict = self.get_conflict(c)
            key = None

            if c.K_PRIMARY() and c.K_KEY():
                key = "pk"
                result[key] = {}
                if c.K_AUTOINCREMENT(): result[key]["autoincrement"] = True
                order = c.K_ASC() or c.K_DESC()
                if order:    result[key]["order"]    = self.t(order)
                if conflict: result[key]["conflict"] = conflict

            elif c.K_NOT() and c.K_NULL():
                key = "notnull"
                result[key] = {}
                if conflict: result[key]["conflict"] = conflict

            elif c.K_UNIQUE():
                key = "unique"
                result[key] = {}
                if conflict: result[key]["conflict"] = conflict

            elif c.K_DEFAULT():
                key, default = "default", None
                if   c.signed_number(): default = self.t(c.signed_number)
                elif c.literal_value(): default = self.t(c.literal_value)
                elif c.expr():          default = "(%s)" % self.r(c.expr())
                result[key] = {"expr": default}

            elif c.K_CHECK():
                key = "check"
                result[key] = {"expr": self.r(c.expr())}

            elif c.K_COLLATE():
                key = "collate"
                result[key] = {"value": self.u(c.collation_name).upper()}

            elif c.foreign_key_clause():
                key = "fk"
                fkctx = c.foreign_key_clause()
                result[key] = self.build_fk_extra(fkctx)
                result[key]["table"] = self.u(fkctx.foreign_table)
                result[key]["key"] = self.u(fkctx.column_name(0) or "")

            elif c.generated_clause():
                key = "generated"
                gctx = c.generated_clause()
                result[key] = {"expr": self.r(gctx.expr())}
                if gctx.K_GENERATED(): result[key]["always"] = True
                if   gctx.C_STORED():  result[key]["type"] = "STORED"
                elif gctx.K_VIRTUAL(): result[key]["type"] = "VIRTUAL"

            if key and c.constraint_name(): result[key]["name"] = self.u(c.constraint_name)

        return result


    def build_table_constraint(self, ctx):
        """
        Assembles and returns table constraint data for CREATE TABLE, as {
            type:       PRIMARY KEY | FOREIGN KEY | UNIQUE | CHECK
            ?name:      constraint name

          # for PRIMARY KEY | UNIQUE:
            ?key:       [{name, ?collate, ?order}, ]
            ?conflict:  ROLLBACK | ABORT | FAIL | IGNORE | REPLACE

          # for CHECK:
            ?check      (SQL expression)

          # for FOREIGN KEY:
            ?columns:   [column_name, ]
            ?table:     foreign table name
            ?key:       [foreign_column_name, ]
            ?defer:          { if DEFERRABLE
                ?not         True if NOT
                ?initial:    DEFERRED | IMMEDIATE
            }
            ?action:         {
                ?UPDATE:     SET NULL | SET DEFAULT | CASCADE | RESTRICT | NO ACTION
                ?DELETE:     SET NULL | SET DEFAULT | CASCADE | RESTRICT | NO ACTION
            }
            ?match:          MATCH-clause value
        }.
        """
        result = {}
        if ctx.constraint_name(): result["name"] = self.u(ctx.constraint_name)

        conflict = self.get_conflict(ctx)

        if ctx.K_PRIMARY() and ctx.K_KEY() or ctx.K_UNIQUE():
            result["type"] = SQL.UNIQUE if ctx.K_UNIQUE() else SQL.PRIMARY_KEY
            result["key"] = [] # {name: column, ?collate: name, ?asc|desc}
            for c in ctx.indexed_column():
                col = {}
                col["name"] = self.u(c.column_name)

                if c.K_COLLATE(): col["collate"] = self.u(c.collation_name).upper()
                order = c.K_ASC() or c.K_DESC()
                if order: col["order"] = self.t(order)
                result["key"].append(col)
            if conflict: result["conflict"] = conflict

        elif ctx.K_CHECK():
            result["type"] = SQL.CHECK
            result["check"] = self.r(ctx.expr())

        elif ctx.K_FOREIGN() and ctx.K_KEY():
            result["type"] = SQL.FOREIGN_KEY
            result["columns"] = [self.u(x) for x in ctx.column_name()]

            fkctx = ctx.foreign_key_clause()
            result["table"] = self.u(fkctx.foreign_table)
            if fkctx.column_name():
                result["key"] = [self.u(x) for x in fkctx.column_name()]

            if conflict: result["conflict"] = conflict
            result.update(self.build_fk_extra(fkctx))

        return result


    def build_fk_extra(self, ctx):
        """
        Returns foreign key deferrable, action and match constraint data.
        """
        result = {}
        if ctx.K_DEFERRABLE():
            result["defer"] = {}
            if ctx.K_NOT(): result["defer"]["not"] = True
            initial = ctx.K_DEFERRED() or ctx.K_IMMEDIATE()
            if initial:
                result["defer"]["initial"] = self.t(initial)

        accum, accums = [], []
        for t in map(self.t, ctx.children):
            if accum and t in (SQL.ON, SQL.MATCH):
                accums.append(accum); accum = []
            accum.append(t)
        accums.append(accum)
        for accum in accums:
            if SQL.ON == accum[0]:
                result.setdefault("action", {})
                result["action"][accum[1]] = " ".join(accum[2:])
            elif SQL.MATCH == accum[0]:
                result["match"] = accum[1]
        return result


    def get_conflict(self, ctx):
        """Returns ctx.conflict_clause value like "ROLLBACK", if any."""
        conflict = ctx.conflict_clause()
        if not conflict: return None
        action = (conflict.K_ROLLBACK() or
            conflict.K_ABORT() or conflict.K_FAIL() or conflict.K_IGNORE()
        )
        return self.t(action)


    def get_parent(self, ctx, types, top=True):
        """
        Returns a parent context of one of types specified, by default topmost.
        """
        result, ptr = None, ctx
        while ptr and ptr.parentCtx:
            ptr = ptr.parentCtx
            if isinstance(ptr, tuple(types)):
                result = ptr
                if not top: break # while ptr
        return result


    def recurse_collect(self, items, ctxtypes):
        """
        Recursively goes through all items and item children,
        returning a list of terminal values of specified context type,
        lower-cased.

        @param   ctxtypes  node context types to collect,
                           like SQLiteParser.Table_nameContext
        """
        result, ctxtypes = [], tuple(ctxtypes)
        for ctx in items:
            if getattr(ctx, "children", None):
                for x in self.recurse_collect(ctx.children, ctxtypes):
                    if x not in result: result.append(x)

            if not isinstance(ctx, ctxtypes): continue # for ctx

            # Get the deepest terminal, the one holding name value
            c = ctx
            while not isinstance(c, TerminalNode): c = c.children[0]
            v = self.u(c).lower()

            # Skip special table names "OLD"/"NEW" in trigger body and WHEN
            if SQL.CREATE_TRIGGER == self._category and v in ("old", "new") \
            and self.get_parent(c, self.TRIGGER_BODY_CTXS):
                continue # for ctx

            if v not in result: result.append(v)

        return result


    def recurse_rename(self, items, renames, level=0):
        """
        Recursively goes through all items and item children,
        renaming specified types to specified values.
        """
        for ctx in items:
            for k, v in renames.items():
                if "column" == k: continue # for k, v

                cls, c = self.RENAME_CTXS.get(k), ctx
                if not cls or not isinstance(ctx, cls): continue # for k, v

                # Get the deepest terminal, the one holding name value
                while not isinstance(c, TerminalNode): c = c.children[0]
                v0 = self.u(c).lower()

                # Skip special table names OLD|NEW in trigger body and WHEN
                if "table" == k and SQL.CREATE_TRIGGER == self._category \
                and v0 in ("old", "new") \
                and self.get_parent(c, self.TRIGGER_BODY_CTXS):
                    continue # for k, v

                for v1, v2 in v.items():
                    if v0 == v1.lower(): c.getSymbol().text = quote(v2)

            if getattr(ctx, "children", None):
                self.recurse_rename(ctx.children, renames, level+1)

        if not level and renames.get("column"):
            self.recurse_rename_column(items, renames)


    def recurse_rename_column(self, items, renames, stack=None):
        """
        Recursively goes through all items and item children, renaming columns.
        """
        if stack is None:
            stack = [] # Nested ownerships as [(context, [entity nane, ])]
            lowercased = {k.lower(): {c1.lower(): c2 for c1, c2 in v.items()}
                          for k, v in renames["column"].items()}
            renames = dict(renames, column=lowercased)
        for ctx in items:
            namectx = None # Single context with owner name, or a list for SELECT/JOIN tables
            if isinstance(ctx, CTX.SELECT_CORE):
                tables = ctx.table_or_subquery()
                if ctx.join_clause(): tables += ctx.join_clause().table_or_subquery()
                namectx = [c.table_name() for c in tables if c.table_name()]
            elif isinstance(ctx, CTX.JOIN_CLAUSE):
                tables = ctx.table_or_subquery()
                namectx = [c.table_name() for c in tables if c.table_name()]
            elif isinstance(ctx, CTX.EXPRESSION):
                if self.t(ctx.table_name): namectx = ctx.table_name
            elif isinstance(ctx, CTX.FOREIGN_KEY):
                namectx = ctx.foreign_table().any_name
            elif isinstance(ctx, CTX.CREATE_VIEW):
                namectx = ctx.view_name
            elif isinstance(ctx, (CTX.UPDATE, CTX.UPDATE_LIMITED, CTX.DELETE, CTX.DELETE_LIMITED)):
                namectx = ctx.qualified_table_name().table_name
            elif isinstance(ctx, (CTX.CREATE_TABLE, CTX.CREATE_VIRTUAL_TABLE,
                                  CTX.CREATE_INDEX, CTX.CREATE_TRIGGER, CTX.INSERT)):
                namectx = ctx.table_name
            if namectx:
                names = [self.u(c).lower() for c in util.tuplefy(namectx)]
                if SQL.CREATE_TRIGGER == self._category and names in (["old"], ["new"]) \
                and stack and isinstance(stack[0][0], CTX.CREATE_TRIGGER):
                    names = stack[0][1]
                stack.append((ctx, names))

            if stack:
                renamectx = None
                if isinstance(ctx, CTX.COLUMN_NAME):
                    renamectx = ctx
                elif isinstance(ctx, CTX.LITERAL_VALUE) and isinstance(ctx.parentCtx, CTX.EXPRESSION):
                    PARENT_TYPES = [CTX.COLUMN_DEF, CTX.SELECT_CORE, CTX.UPDATE, CTX.DELETE]
                    if self.get_parent(ctx, PARENT_TYPES) and self.t(ctx) != self.u(ctx):
                        # Interpret any quoted string in potential column context as column
                        renamectx = ctx
                if renamectx:
                    terminal = renamectx # Get the deepest terminal, the one holding name value
                    while not isinstance(terminal, TerminalNode): terminal = terminal.children[0]
                    text = self.u(terminal).lower()
                    for ownername in stack[-1][1]:
                        col_renames = renames["column"].get(ownername) or {}
                        for name_old, name_new in col_renames.items():
                            if text == name_old and not getattr(terminal, "__renamed__", False):
                                terminal.getSymbol().text = quote(name_new)
                                setattr(terminal, "__renamed__", True)

            if getattr(ctx, "children", None):
                self.recurse_rename_column(ctx.children, renames, stack)

            if namectx: stack.pop(-1)



class Generator(object):
    """
    SQL generator.
    """

    TEMPLATES = {
        SQL.COLUMN:                templates.COLUMN_DEFINITION,
        SQL.CONSTRAINT:            templates.TABLE_CONSTRAINT,
        SQL.ALTER_TABLE:           templates.ALTER_TABLE,
        "COMPLEX ALTER TABLE":     templates.ALTER_TABLE_COMPLEX,
        "ALTER INDEX":             templates.ALTER_INDEX,
        "ALTER TRIGGER":           templates.ALTER_TRIGGER,
        "ALTER VIEW":              templates.ALTER_VIEW,
        "ALTER MASTER":            templates.ALTER_MASTER,
        "INDEX COLUMN":            templates.INDEX_COLUMN_DEFINITION,
        SQL.CREATE_INDEX:          templates.CREATE_INDEX,
        SQL.CREATE_TABLE:          templates.CREATE_TABLE,
        SQL.CREATE_TRIGGER:        templates.CREATE_TRIGGER,
        SQL.CREATE_VIEW:           templates.CREATE_VIEW,
        SQL.CREATE_VIRTUAL_TABLE:  templates.CREATE_VIRTUAL_TABLE,
    }


    def __init__(self, indent="  "):
        """
        @param   indent    indentation level to use. If falsy,
                           result is not indented in any, including linefeeds.
        """
        self._indent    = indent
        self._category  = None # Current data category like "CREATE TABLE"
        self._data      = None # data structure given to generate()
        self._tokens    = {}                # {(type, content): unique token text}
        self._tokendata = defaultdict(dict) # {token: {count, ..}}


    def generate(self, data, category=None):
        """
        Generates SQL statement from data in specified category.

        @param   data      SQL data structure {"__type__": "CREATE TABLE"|.., }
        @param   category  data category if not using data["__type__"]
        @return            (SQL string, None) or (None, error)
        """
        category = self._category = (category or data["__type__"]).upper()
        if category not in self.TEMPLATES:
            return None, "Unknown category: %s" % category

        REPLACE_ORDER = ["Q", "GLUE", "CM", "LF", "PRE", "PAD", "WS"]
        ns = {"Q":    self.quote,   "LF": self.linefeed, "PRE": self.indentation,
              "PAD":  self.padding, "CM": self.comma,    "WS":  self.token,
              "GLUE": self.glue, "data": data, "root": data, "collapse": collapse_whitespace,
              "Template": step.Template, "templates": templates, "terminate": terminate}

        # Generate SQL, using unique tokens for whitespace-sensitive parts,
        # replaced after stripping down whitespace in template result.
        tpl = step.Template(self.TEMPLATES[category], strip=True, postprocess=collapse_whitespace)
        while True:
            self._tokens.clear(); self._tokendata.clear(); self._data = data
            result = tpl.expand(ns)

            # Calculate max length for paddings
            widths = defaultdict(int)
            for (tokentype, _), token in self._tokens.items():
                if "PAD" != tokentype: continue # for (tokentype, _), token
                data = self._tokendata[token]
                datalines = data["value"].splitlines() or [""]
                widths[data["key"]] = max(len(datalines[-1]), widths[data["key"]])

            for (tokentype, val), token in sorted(
                self._tokens.items(), key=lambda x: REPLACE_ORDER.index(x[0][0])
            ):
                count = self._tokendata[token]["count"]
                if tokentype in ("GLUE", "LF"):  # Strip surrounding whitespace
                    result = re.sub(r"\s*%s\s*" % re.escape(token), val, result, count=count)
                elif "PAD" == tokentype: # Insert spaces per padding type/value
                    data = self._tokendata[token]
                    datalines = data["value"].splitlines() or [""]
                    ws = " " * (widths[data["key"]] - len(datalines[-1]))
                    if len(datalines) > 1: ws += self._indent
                    result = result.replace(token, ws, count)
                elif "CM" == tokentype:
                    # Strip leading whitespace and multiple trailing spaces from commas
                    r = r"\s*" + re.escape(token) + ("" if self._indent else " *")
                    result = re.sub(r, val, result, count=count, flags=re.U)
                else: result = result.replace(token, val, count)
                if token in result:
                    result = None # Redo if data happened to contain a generated token
                    break # for (tokentype, val)
            if result is None: continue # while True
            break # while True

        self._tokens.clear(); self._tokendata.clear(); self._data = None
        return result, None


    def token(self, val, tokentype="WS", **kwargs):
        """
        Returns token for string value, registering token if new content.
        Most token types set the value as-is in final result, whitespace intact.

        @param   kwargs  additional data to associate with token
        """
        key = (tokentype, val)
        result = self._tokens.get(key)
        if not result:
            result = self._tokens[key] = "[[%s-%s]]" % (tokentype, uuid.uuid4())
        self._tokendata[result].setdefault("count", 0)
        self._tokendata[result]["count"] += 1
        self._tokendata[result].update(kwargs)
        return result


    def linefeed(self):
        """Returns linefeed token if indented SQL, else empty string."""
        return self.token("\n", "LF") if self._indent else ""


    def indentation(self, val=None):
        """
        Returns line indentation token if indented SQL, else empty string.
        If value given, inserts indentation after each LF-token in value.
        """
        if not self._indent: return val or ""

        if not val: return self.token(self._indent, "PRE")

        return self.token(self._indent, "PRE") + \
               re.sub(r"(\[\[LF\-[-\w]+\]\](?!\s+$))", # Skip LF at content end
                      lambda m: m.group() + self.token(self._indent, "PRE"), val)


    def quote(self, val, force=False, allow=""):
        """Returns token for quoted value."""
        return self.token(quote(val, force=force, allow=allow), "Q")


    def padding(self, key, data, quoted=False, quotekw=None):
        """
        Returns whitespace padding token for data[key] if indented SQL,
        else empty string. Whitespace will be justified to data[key] max length.
        If quoted is true, data[key] is quoted if necessary, with quotekw as
        quote() keywords.
        """
        if not self._indent: return ""
        val = data[key] if key in data else ""
        val = quote(val, **quotekw or {}) if quoted and val is not None else val
        return self.token("%s-%s" % (key, val), "PAD", key=key, value=val)


    def glue(self):
        """ Returns token that consumes surrounding whitespace. """
        return self.token("", "GLUE")


    def comma(self, collection, index, subcollection=None, subindex=None, root=None):
        """
        Returns trailing comma token for item in specified collection,
        if not last item and no other collections following.

        @param   root  collection root if not using self._data
        """
        islast = True
        root = root or self._data
        if collection not in root \
        or subcollection and subcollection not in root[collection][index]:
            return ""

        if subcollection:
            container = root[collection][index]
            islast = (subindex == len(container[subcollection]) - 1)
        elif "columns" == collection:
            islast = not root.get("constraints") and \
                     (index == len(root[collection]) - 1)
        else:
            islast = (index == len(root[collection]) - 1)

        val = "" if islast else ", "
        return self.token(val, "CM") if val else ""


__all__ = [
    "CTX", "Generator", "ParseError", "Parser", "SQL", "format", "generate", "get_type",
    "parse", "quote", "strip_and_collapse", "terminate", "transform", "unquote",
]
