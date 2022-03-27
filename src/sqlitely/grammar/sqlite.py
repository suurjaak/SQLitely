# -*- coding: utf-8 -*-
"""
SQLite parsing and generating functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     04.09.2019
@modified    26.03.2022
------------------------------------------------------------------------------
"""
import codecs
from collections import defaultdict
import json
import logging
import re
import sys
import traceback
import uuid

from antlr4 import InputStream, CommonTokenStream, TerminalNode, Token
import six

from .. lib import util
from .. lib.vendor import step
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
def quote(val, force=False, allow=""):
    """
    Returns value in quotes and proper-escaped for queries,
    if name needs quoting (has non-alphanumerics or starts with number)
    or if force set. Always returns unicode.

    @param   allow  extra characters to allow without quoting
    """
    pattern = r"(^[^\w\d%s])|(?=[^\w%s])" % ((re.escape(allow) ,) * 2) \
              if allow else r"(^[\W\d])|(?=\W)"
    result = uni(val)
    if force or result.upper() in RESERVED_KEYWORDS \
    or re.search(pattern, result, re.U):
        result = u'"%s"' % result.replace('"', '""')
    return result


@util.memoize
def unquote(val):
    """
    Returns unquoted string, if string within '' or "" or `` or [].
    Always returns unicode.
    """
    result = uni(val)
    if re.match(r"^([\"].*[\"])|([\'].*[\'])|([\`].*[\`])|([\[].*[\]])$", result, re.DOTALL):
        result, sep = result[1:-1], result[0]
        if sep != "[": result = result.replace(sep * 2, sep)
    return result


def format(value, coldata=None):
    """Formats a value for use in an SQL statement like INSERT."""
    if isinstance(value, six.string_types):
        success = False
        if isinstance(coldata, dict) \
        and isinstance(coldata.get("type"), six.string_types) \
        and "JSON" == coldata["type"].upper():
            try: result, success = "'%s'" % json.dumps(json.loads(value)), True
            except Exception: pass

        if not success and SAFEBYTE_RGX.search(value):
            if isinstance(value, six.text_type):
                try:
                    value = value.encode("latin1")
                except UnicodeError:
                    value = value.encode("utf-8", errors="backslashreplace")
            result = "X'%s'" % codecs.encode(value, "hex").decode("latin1").upper()
        elif not success:
            if isinstance(value, six.text_type):
                value = value.encode("utf-8").decode("latin1")
            result = "'%s'" % value.replace("'", "''")
    else:
        result = "NULL" if value is None else str(value)
    return result


def uni(x, encoding="utf-8"):
    """Convert anything to Unicode, except None."""
    if x is None or isinstance(x, six.text_type): return x
    return six.text_type(str(x), encoding, errors="replace")



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
    INSERT               = SQLiteParser.Insert_stmtContext
    SELECT               = SQLiteParser.Select_stmtContext
    UPDATE               = SQLiteParser.Update_stmtContext
    COLUMN_NAME          = SQLiteParser.Column_nameContext
    INDEX_NAME           = SQLiteParser.Index_nameContext
    SCHEMA_NAME          = SQLiteParser.Database_nameContext
    TABLE_NAME           = SQLiteParser.Table_nameContext
    TRIGGER_NAME         = SQLiteParser.Trigger_nameContext
    VIEW_NAME            = SQLiteParser.View_nameContext
    EXPRESSION           = SQLiteParser.ExprContext
    FOREIGN_TABLE        = SQLiteParser.Foreign_tableContext
    FOREIGN_KEY          = SQLiteParser.Foreign_key_clauseContext
    SELECT_OR_VALUES     = SQLiteParser.Select_or_valuesContext


"""Words that need quoting if in name context, e.g. table name."""
RESERVED_KEYWORDS = ["ACTION", "ADD", "AFTER", "ALL", "ALTER", "ALWAYS", "ANALYZE",
    "AND", "AS", "ASC", "ATTACH", "AUTOINCREMENT", "BEFORE", "BEGIN", "BETWEEN",
    "BY", "CASE", "CAST", "CHECK", "COLLATE", "COMMIT", "CONSTRAINT", "CREATE",
    "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP", "DEFAULT", "DEFERRABLE",
    "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DO", "DROP", "EACH",
    "ELSE", "END", "ESCAPE", "EXCEPT", "EXISTS", "EXPLAIN", "FOR", "FOREIGN",
    "FROM", "GENERATED", "GROUP", "HAVING", "IF", "IMMEDIATE", "IN", "INDEX",
    "INITIALLY", "INSERT", "INSTEAD", "INTERSECT", "INTO", "IS", "ISNULL",
    "JOIN", "KEY", "LIKE", "LIMIT", "MATCH", "NO", "NOT", "NOTHING", "NOTNULL",
    "NULL", "OF", "ON", "OR", "ORDER", "OVER", "PRAGMA", "PRECEDING", "PRIMARY",
    "RAISE", "RECURSIVE", "REFERENCES", "REGEXP", "REINDEX", "RELEASE", "RENAME",
    "REPLACE", "RESTRICT", "ROLLBACK", "SAVEPOINT", "SELECT", "SET", "TABLE",
    "TEMPORARY", "THEN", "TIES", "TO", "TRANSACTION", "TRIGGER", "UNBOUNDED",
    "UNION", "UNIQUE", "UPDATE", "USING", "VACUUM", "VALUES", "VIEW", "WHEN",
    "WHERE", "WITHOUT"]


class ParseError(Exception):
    """Parse exception with line and column."""

    def __init__(self, message, line, column):
        Exception.__init__(self, message)
        self.message, self.line, self.column = message, line, column

    def __getattribute__(self, name):
        if name in dir(str): return getattr(self.message, name)
        return Exception.__getattribute__(self, name)

    def __repr__(self):           return repr(self.message)
    def __str__ (self):           return str(self.message)



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
    TRIGGER_BODY_CTXS = [CTX.DELETE, CTX.INSERT, CTX.SELECT, CTX.UPDATE]

    class ReparseException(Exception): pass

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
                for i, (f, l, fn, t) in enumerate(stack):
                    if f == __file__:
                        del stack[:max(i-1, 0)]
                        break # for i, (..)
                self._stack = traceback.format_list(stack)

        def getErrors(self, stack=False):
            es = self._errors
            res = es[0] if len(es) == 1 else "\n\n".join(e.message for e in es)
            return "%s\n%s" % (res, "".join(self._stack)) if stack else res


    def __init__(self):
        self._category = None # "CREATE TABLE" etc
        self._stream   = None # antlr TokenStream
        self._repls    = []   # [(start index, end index, replacement)]


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
        def parse_tree(sql):
            self._stream = CommonTokenStream(SQLiteLexer(InputStream(sql)))
            parser, listener = SQLiteParser(self._stream), self.ErrorListener()
            parser.removeErrorListeners()
            parser.addErrorListener(listener)

            tree = parser.parse()
            if parser.getNumberOfSyntaxErrors():
                logger.error('Errors parsing SQL "%s":\n\n%s', sql,
                             listener.getErrors(stack=True))
                return None, listener.getErrors()

            # parse ctx -> statement list ctx -> statement ctx -> specific type ctx
            ctx = tree.children[0].children[0].children[0]
            name = self.CTXS.get(type(ctx))
            categoryname = self.CATEGORIES.get(category)
            if category and name != categoryname or name not in self.BUILDERS:
                error = "Unexpected statement category: '%s'%s."% (name,
                         " (expected '%s')" % (categoryname or category)
                         if category else "")
                logger.error(error)
                return None, error
            self._category = name
            return ctx, None

        def build(ctx):
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

            cc = self._stream.filterForChannel(0, len(self._stream.tokens) - 1, channel=2)
            result["__comments__"] = [x.text for x in cc or []]

            return result

        result, error, tries = None, None, 0
        while not result and not error:
            ctx, error = parse_tree(sql)
            if error: break # while
            try: result = build(ctx)
            except self.ReparseException as e:
                sql, tries = e.message, tries + 1
                if tries > 1: error = "Failed to parse SQL"
        return result, error


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
        if ctx.database_name(): result["schema"] = self.u(ctx.database_name)
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
          ?without:      True if WITHOUT ROWID
          columns:       [{name, ..}]
          ?constraints:  [{type, ..}]
        }.
        """
        result = {}

        result["name"] = self.u(ctx.table_name)
        if ctx.database_name(): result["schema"]  = self.u(ctx.database_name)
        if ctx.K_TEMP() or ctx.K_TEMPORARY(): result["temporary"] = True
        if ctx.K_EXISTS():      result["exists"]  = True
        if ctx.K_WITHOUT():     result["without"] = True

        result["columns"] = [self.build_table_column(x) for x in ctx.column_def()]
        if self._repls:
            sql, shift = self._stream.getText(0, sys.maxsize), 0
            for start, end, repl in self._repls:
                sql = sql[:start + shift] + repl + sql[end + shift:]
                shift = len(repl) - end + start
            del self._repls[:]
            raise self.ReparseException(sql)

        if ctx.table_constraint():
            result["constraints"] = [self.build_table_constraint(x)
                                     for x in ctx.table_constraint()]

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
        if ctx.database_name(0): result["schema"]  = self.u(ctx.database_name(0))
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
        if ctx.database_name(): result["schema"]  = self.u(ctx.database_name)
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
        if ctx.database_name(): result["schema"]  = self.u(ctx.database_name)
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
        }.
        """
        result = {}
        result["name"] = self.u(ctx.column_name().any_name)
        if ctx.type_name():
            if ctx.type_name().type_name_text().ENCLOSED_IDENTIFIER():
                result["type"] = self.u(ctx.type_name().type_name_text().ENCLOSED_IDENTIFIER).upper()
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
                result[key]["key"] = self.u(fkctx.column_name(0))

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
        if not conflict: return
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
            if any(isinstance(ptr, x) for x in types):
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
            stack = []
            renames["column"] = {k.lower(): {c1.lower(): c2 for c1, c2 in v.items()}
                                 for k, v in renames["column"].items()}
        for ctx in items:
            ownerctx = None
            if isinstance(ctx, CTX.SELECT_OR_VALUES):
                tables = ctx.table_or_subquery()
                if len(tables) == 1 and tables[0].table_name():
                    ownerctx = tables[0].table_name
            elif isinstance(ctx, CTX.EXPRESSION):
                if self.t(ctx.table_name): ownerctx = ctx.table_name
            elif isinstance(ctx, CTX.FOREIGN_KEY):
                ownerctx = ctx.foreign_table().any_name
            elif isinstance(ctx, CTX.CREATE_VIEW):
                ownerctx = ctx.view_name
            elif isinstance(ctx, (CTX.UPDATE, CTX.DELETE)):
                ownerctx = ctx.qualified_table_name().table_name
            elif isinstance(ctx, (CTX.CREATE_TABLE, CTX.CREATE_VIRTUAL_TABLE,
                                  CTX.CREATE_INDEX, CTX.CREATE_TRIGGER, CTX.INSERT)):
                ownerctx = ctx.table_name
            if ownerctx:
                name = self.u(ownerctx).lower()
                if SQL.CREATE_TRIGGER == self._category and name in ("old", "new") \
                and stack and isinstance(stack[0][0], CTX.CREATE_TRIGGER):
                    name = stack[0][1]
                stack.append((ctx, name))

            if isinstance(ctx, CTX.COLUMN_NAME) and stack:
                c = ctx # Get the deepest terminal, the one holding name value
                while not isinstance(c, TerminalNode): c = c.children[0]
                v0 = self.u(c).lower()

                v = renames["column"].get(stack and stack[-1][1])
                for v1, v2 in v.items() if v else ():
                    if v0 == v1.lower(): c.getSymbol().text = quote(v2)

            if getattr(ctx, "children", None):
                self.recurse_rename_column(ctx.children, renames, stack)

            if ownerctx: stack.pop(-1)



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
              "GLUE": self.glue, "data": data, "root": data,
              "Template": step.Template, "templates": templates}

        # Generate SQL, using unique tokens for whitespace-sensitive parts,
        # replaced after stripping down whitespace in template result.
        tpl = step.Template(self.TEMPLATES[category], strip=True, collapse=True)
        while True:
            self._tokens.clear(); self._tokendata.clear(); self._data = data
            result = tpl.expand(ns)

            # Calculate max length for paddings
            widths = defaultdict(int)
            for (tokentype, _), token in self._tokens.items():
                if "PAD" != tokentype: continue # for (tokentype, _), token
                data = self._tokendata[token]
                widths[data["key"]] = max(len(data["value"]), widths[data["key"]])

            for (tokentype, val), token in sorted(
                self._tokens.items(), key=lambda x: REPLACE_ORDER.index(x[0][0])
            ):
                count = self._tokendata[token]["count"]
                if tokentype in ("GLUE", "LF"):  # Strip surrounding whitespace
                    result = re.sub(r"\s*%s\s*" % re.escape(token), val, result, count=count)
                elif "PAD" == tokentype: # Insert spaces per padding type/value
                    data = self._tokendata[token]
                    ws = " " * (widths[data["key"]] - len(data["value"]))
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
        val = quote(val, **quotekw or {}) if val and quoted else val
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



def test():
    logging.basicConfig()

    TEST_STATEMENTS = [
        u'''
        CREATE UNIQUE INDEX IF NOT EXISTS
        myschema.myindex ON mytable (mytablecol1, mytablecol2) WHERE mytable.mytablecol1 NOT BETWEEN mytable.mytablecol2 AND mytable.mytablecol3
        ''',


        """
        -- comment
        CREATE TEMP TABLE -- comment
        -- comment
        IF NOT EXISTS
        -- comment
        mytable (
            -- first line comment
            mytablecol1 TEXT PRIMARY KEY AUTOINCREMENT,
            "mytable col2" INTEGER NOT NULL, -- my comment
            mytablecol3
            /* multiline
            comment */
            -- last line comment
            UNIQUE NOT NULL
        ) -- comment
        WITHOUT ROWID -- comment
        -- comment

        """,


        u'''
        CREATE TABLE IF NOT EXISTS "mytable" (
            mytablekey    INTEGER NOT NULL DEFAULT (mytablecol1),
            mytablecol1   INTEGER NOT NULL ON CONFLICT ABORT DEFAULT /* uhuu */ -666.5 UNIQUE ON CONFLICT ROLLBACK,
            mytablecol2   INTEGER CHECK (mytablecol3 IS /* hoho */ NULL) COLLATE /* haha */ BiNARY,
            mytablecol3   TEXT NOT NULL DEFAULT "double "" quoted" CHECK (LENGTH(mytable.mytablecol1) > 0),
            mytablecol4   TIMESTAMP WITH TIME ZONE,
            mytablefk     INTEGER REFERENCES mytable2 (mytable2key) ON delete cascade on update no action match SIMPLE,
            mytablefk2    INTEGER,
            mytablefk3    INTEGER,
            mytablecol5   DOUBLE TYPE,
            PRIMARY KEY (mytablekey) ON CONFLICT ROLLBACK,
            FOREIGN KEY (mytablefk2, mytablefk3) REFERENCES mytable2 (mytable2col1, mytable2col2) ON DELETE CASCADE ON UPDATE RESTRICT,
            CONSTRAINT myconstraint CHECK (mytablecol1 != mytablecol2)
        )
        ''',


        u'''
        CREATE TRIGGER myschema.mytriggér AFTER UPDATE OF mytablecol1 ON mytable
        WHEN 1 NOT IN (SELECT mytablecol2 FROM mytable)
          BEGIN
            SELECT mytablecol1, mytablecol2, "mytable col3" FROM mytable;
            SELECT myviewcol1, myviewcol2 FROM myview;
            UPDATE "my täble2" SET mytable2col1 = NEW.mytablecol1 WHERE mytable2col2 = OLD.mytablecol2;
            INSERT INTO mytable2 (mytable2col1) VALUES (42);
            DELETE FROM mytable2 WHERE mytable2col2 != old.mytablecol2;
            UPDATE mytable2 SET mytable2col2 = new.mytablecol2 WHERE mytable2col1 = old.mytablecol1;
          END;
        ''',


        u'''
            CREATE TEMPORARY VIEW IF NOT EXISTS
            myschema.myview (myviewcol1, myviewcol2, "myview col3")
            AS SELECT mytablecol1, mytablecol2, "mytable col3" FROM mytable
        ''',


        u'''
            CREATE TEMPORARY VIEW IF NOT EXISTS
            myschema.myview (myviewcol1, myviewcol2, "myview col3")
            AS SELECT mytablecol1, mytablecol2, "mytable col3" FROM mytable
               UNION
               SELECT mytable2col1, mytable2col2, "mytable2 col3" FROM mytable2
               UNION
               SELECT myview2col1, myview2col2, "myview2 col3" FROM myview2
        ''',


        u'''
        CREATE VIRTUAL TABLE IF NOT EXISTS myschemaname.mytable
        USING mymodule (myargument1, myargument2);
        ''',
    ]


    indent = "  "
    renames = {"table":   {"mytable": "renamed mytable", "mytable2": "renamed mytable2"},
               "trigger": {u"mytriggér": u"renämed mytriggér"},
               "index":   {"myindex":  u"renämed myindex"},
               "view":    {"myview":  u"renämed myview",
                           "myview2": u"renämed myview2"},
               "column":  {
                           "renamed mytable":  {"mytablecol1": u"renamed mytablecol1", "mytable col2": "renamed mytable col2", "mytablecol2": "renamed mytablecol2", "mytablecol3": "renamed mytablecol3", "mytable col3": "renamed mytable col3", "mytablekey": "renamed mytablekey", "mytablefk2": "renamed mytablefk2"},
                           "renamed mytable2": {"mytable2col1": u"renamed mytable2col1", "mytable2col2": u"renamed mytable2col2", "mytable2key": "renamed mytable2key", "mytablefk2": "renamed mytablefk2"},
                           u"renämed myview":  {"myviewcol1": "renamed myviewcol1", "myview col3": "renamed myview col3"},
                           u"renämed myview2": {"myview2col1": "renamed myview2col1", "myview2 col3": "renamed myview2 col3"},
               },
               "schema":  u"renämed schéma"}
    for sql1 in TEST_STATEMENTS:
        print("\n%s\nORIGINAL:\n" % ("-" * 70))
        print(sql1.encode("utf-8"))

        x, err = parse(sql1)
        if not x:
            print("ERROR: %s" % err)
            continue # for sql1

        print("\n%s\nPARSED:" % ("-" * 70))
        print(json.dumps(x, indent=2))
        sql2, err2 = generate(x, indent)
        if sql2:
            print("\n%s\nGENERATED:\n" % ("-" * 70))
            print(sql2.encode("utf-8") if sql2 else sql2)

            print("\n%s\nTRANSFORMED:\n" % ("-" * 70))
            sql3, err3 = transform(sql2, renames=renames, indent=indent)
            print(sql3.encode("utf-8") if sql3 else sql3)



if __name__ == '__main__':
    test()
