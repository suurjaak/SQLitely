# -*- coding: utf-8 -*-
"""
SQLite parsing and generating functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     04.09.2019
@modified    09.09.2019
------------------------------------------------------------------------------
"""
from collections import defaultdict
import logging
import re
import uuid

from antlr4 import InputStream, CommonTokenStream, TerminalNode

from .. lib.vendor import step
from . import templates
from . SQLiteLexer import SQLiteLexer
from . SQLiteParser import SQLiteParser

logger = logging.getLogger(__name__)



def parse(sql, category=None):
    """
    Returns data structure for SQL statement.

    @param   category  expected statement category if any
    @return            {}, or None on error
    """
    result = None
    try:
        result = Parser().parse(sql, category)
    except Exception:
        logger.exception("Error parsing SQL %s.", sql)
    return result


def generate(data, indent="  "):
    """
    Returns SQL statement from data structure.

    @param   data    {"__type__": "CREATE TABLE"|.., ..}
    @param   indent  indentation level to use. If falsy,
                     result is not indented in any, including linefeeds.
    @return          SQL string, or None on error
    """
    result, generator = None, Generator(indent)
    try:
        result = generator.generate(data)
    except Exception:
        logger.exception("Error generating SQL for %s.", data)
    return result


def transform(sql, flags=None, renames=None, indent="  "):
    """
    Returns transformed SQL.

    @param   flags    flags to toggle, like {"exists": True}
    @param   renames  renames to perform in SQL statement body,
                      supported types "schema" (top-level rename only),
                      "table", "index", "trigger", "view".
                      Renames all items of specified category, unless
                      given nested value like {"table": {"old": "new"}}
    @param   indent   indentation level to use. If falsy,
                      result is not indented in any, including linefeeds.
    """
    result, parser, generator = None, Parser(), Generator(indent)
    try:
        data = parser.parse(sql, renames=renames)
        if flags: data.update(flags)
        result = generator.generate(data)
    except Exception:
        logger.exception("Error transforming SQL %s.", sql)
    return result


def quote(val, force=False):
    """
    Returns value in quotes and proper-escaped for queries,
    if name needs quoting (whitespace etc) or if force set.
    Always returns unicode.
    """
    result = uni(val)
    if force or re.search(r"\W", result, re.U):
        result = u'"%s"' % result.replace('"', '""')
    return result


def unquote(val):
    """
    Returns unquoted string, if string within '' or "" or [].
    Always returns unicode.
    """
    result = uni(val)
    if re.match(r"^([\"].*[\"])|([\'].*[\'])|([\[].*[\]])$", result):
        result, sep = result[1:-1], result[0]
        if sep != "[": result = result.replace(sep * 2, sep)
    return result


def uni(x, encoding="utf-8"):
    """Convert anything to Unicode, except None."""
    if x is None or isinstance(x, unicode): return x
    return unicode(str(x), encoding, errors="replace")




class SQL(object):
    """SQL word constants."""
    AFTER                = "AFTER"
    AUTOINCREMENT        = "AUTOINCREMENT"
    BEFORE               = "BEFORE"
    CHECK                = "CHECK"
    COLLATE              = "COLLATE"
    CONSTRAINT           = "CONSTRAINT"
    CREATE_INDEX         = "CREATE INDEX"
    CREATE_TABLE         = "CREATE TABLE"
    CREATE_TRIGGER       = "CREATE TRIGGER"
    CREATE_VIEW          = "CREATE VIEW"
    CREATE_VIRTUAL_TABLE = "CREATE VIRTUAL TABLE"
    CREATE               = "CREATE"
    DEFAULT              = "DEFAULT"
    DEFERRABLE           = "DEFERRABLE"
    FOR_EACH_ROW         = "FOR EACH ROW"
    FOREIGN_KEY          = "FOREIGN KEY"
    IF_NOT_EXISTS        = "IF NOT EXISTS"
    INITIALLY            = "INITIALLY"
    INSTEAD_OF           = "INSTEAD OF"
    MATCH                = "MATCH"
    NOT_NULL             = "NOT NULL"
    NOT                  = "NOT"
    ON_CONFLICT          = "ON CONFLICT"
    ON                   = "ON"
    PRIMARY_KEY          = "PRIMARY KEY"
    REFERENCES           = "REFERENCES"
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
    INDEX_NAME           = SQLiteParser.Index_nameContext
    TABLE_NAME           = SQLiteParser.Table_nameContext
    TRIGGER_NAME         = SQLiteParser.Trigger_nameContext
    VIEW_NAME            = SQLiteParser.View_nameContext



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
    RENAME_CTXS = {"index":   CTX.INDEX_NAME,   "table": CTX.TABLE_NAME,
                   "trigger": CTX.TRIGGER_NAME, "view":  CTX.VIEW_NAME}
    TRIGGER_BODY_CTXS = [CTX.DELETE, CTX.INSERT, CTX.SELECT, CTX.UPDATE]


    def __init__(self):
        self._stream  = CommonTokenStream(SQLiteLexer())


    def parse(self, sql, category=None, renames=None):
        """
        Parses the SQL statement and returns data structure.

        @param   sql       source SQL string
        @param   category  expected statement category if any
        @param   renames   renames to perform in SQL data,
                           supported types: "schema" (top-level rename only),
                           "table", "index", "trigger", "view".
                           Renames all items of specified category, unless
                           given nested value like {"table": {"old": "new"}}
        @return            {..}, or None on error

        """
        self._stream.tokenSource.inputStream = InputStream(sql)
        tree = SQLiteParser(self._stream).parse()

        # parse ctx -> statement list ctx -> statement ctx -> specific type ctx
        ctx = tree.children[0].children[0].children[0]
        result, name = None, self.CTXS.get(type(ctx))
        if category and name != category or name not in self.BUILDERS:
            return

        if renames: self.recurse_rename([ctx], renames, name)
        result = self.BUILDERS[name](self, ctx)
        result["__type__"] = name
        if renames and "schema" in renames:
            if isinstance(renames["schema"], dict):
                for v1, v2 in renames["schema"].items():
                    if result.get("schema", "").lower() == v1.lower():
                        result["schema"] = v2
            elif renames["schema"]: result["schema"] = renames["schema"]
            else: result.pop("schema", None)

        self._stream.tokenSource.inputStream = None
        return result


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
        result = self._stream.getText(interval)

        for c, r in ((ctx, "^%s"), (ctx2, "%s$")) if ctx and ctx2 else ():
            if not isinstance(c, TerminalNode): continue # for c, r
            result = re.sub(r % re.escape(self.t(c)), "", result, flags=re.I)
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
            columns:  [{?name, ?expr, ?collate, ?direction}, ]
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
                col["direction"] = self.t(c.K_ASC() or c.K_DESC())
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
          ?columns:    [column_name, ] for UPDATE OF action
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
        if cols: result["columns"] =  [self.u(x) for x in cols]

        result["table"] = self.u(ctx.table_name)

        if ctx.K_FOR() and ctx.K_EACH() and ctx.K_ROW():
            result["for"]  = SQL.FOR_EACH_ROW

        if ctx.K_WHEN():
            result["when"] = self.r(ctx.expr())

        result["body"] = self.r(ctx.K_BEGIN(), ctx.K_END()).rstrip()

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
        if cols: result["columns"] =  [self.u(x) for x in cols]
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
        if args: result["module"]["arguments"] =  [self.u(x) for x in args]

        return result


    def build_table_column(self, ctx):
        """
        Assembles and returns column data for CREATE TABLE, as {
          name:                column name
          ?type:               column type
          ?pk                  { if PRIMARY KEY
              ?autoincrement:  True if AUTOINCREMENT
              ?direction:      ASC | DESC
              ?conflict:       ROLLBACK | ABORT | FAIL | IGNORE | REPLACE
          ?
          ?notnull             { if NOT NULL
              ?conflict:       ROLLBACK | ABORT | FAIL | IGNORE | REPLACE
          ?
          ?unique              { if UNIQUE
              ?conflict:       ROLLBACK | ABORT | FAIL | IGNORE | REPLACE
          ?
          ?default:            DEFAULT value or expression
          ?check:              (expression)
          ?collate:            NOCASE | ..
          ?fk:                 { if REFERENCES
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
              ?match:          [MATCH-clause name, ]
          }
        }.
        """
        result = {}
        result["name"] = self.u(ctx.column_name().any_name)
        if ctx.type_name():
            result["type"] = " ".join(self.u(x) for x in ctx.type_name().name())

        for c in ctx.column_constraint():
            conflict = self.get_conflict(c)

            if c.K_PRIMARY() and c.K_KEY():
                result["pk"] = {}
                if c.K_AUTOINCREMENT(): result["pk"]["autoincrement"] = True
                direction = c.K_ASC() or c.K_DESC()
                if direction: result["pk"]["direction"] = self.t(direction)
                if conflict:  result["pk"]["conflict"] = conflict

            elif c.K_NOT() and c.K_NULL():
                result["notnull"] = {}
                if conflict: result["notnull"]["conflict"] = conflict

            elif c.K_UNIQUE():
                result["unique"] = {}
                if conflict: result["unique"]["conflict"] = conflict

            elif c.K_DEFAULT():
                default = None
                if   c.signed_number(): default = self.t(c.signed_number)
                elif c.literal_value(): default = self.t(c.literal_value)
                elif c.expr():          default = "(%s)" % self.r(c.expr())
                result["default"] = default

            elif c.K_CHECK():
                result["check"] = self.r(c.expr())

            elif c.K_COLLATE():
                result["collate"] = self.u(c.collation_name).upper()

            elif c.foreign_key_clause():
                fkctx = c.foreign_key_clause()
                result["fk"] = self.build_fk_extra(fkctx)
                result["fk"]["table"] = self.u(fkctx.foreign_table)
                result["fk"]["key"] = self.u(fkctx.column_name(0))

        return result


    def build_table_constraint(self, ctx):
        """
        Assembles and returns table constraint data for CREATE TABLE, as {
            type:       PRIMARY KEY | FOREIGN KEY | UNIQUE | CHECK
            ?name:      constraint name
                        
            ?key:       [{?name, ?expr, ?collate, ?direction}, ] for PRIMARY KEY
            ?conflict:  ROLLBACK | ABORT | FAIL | IGNORE | REPLACE for PRIMARY KEY

            ?check      (SQL expression) for CHECK

            ?columns:   [column_name, ] for FOREIGN KEY
            ?table:     table name for FOREIGN KEY
            ?key:       [foreign_column_name, ] for FOREIGN KEY
        }.
        """
        result = {}
        if ctx.name(): result["name"] = self.u(ctx.name().any_name)

        conflict = self.get_conflict(ctx)

        if ctx.K_PRIMARY() and ctx.K_KEY() or ctx.K_UNIQUE():
            result["type"] = SQL.UNIQUE if ctx.K_UNIQUE() else SQL.PRIMARY_KEY
            result["key"] = [] # {?name: column, ?expr: "expr", ?collate: name, ?asc|desc}
            for c in ctx.indexed_column():
                col = {}
                if c.column_name(): col["name"] = self.u(c.column_name)
                else: col["expr"] = self.r(c.expr())

                if c.K_COLLATE(): col["collate"] = self.u(c.collation_name).upper()
                direction = c.K_ASC() or c.K_DESC()
                if direction: col["direction"] = self.t(direction)
                result["key"].append(col)
            if conflict: result["conflict"] = conflict

        elif ctx.K_CHECK():
            result["type"] = SQL.CHECK
            result["check"] = self.t(ctx.expr())

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
                result.setdefault("match", []).append(accum[1])
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
                if not top: break # while
        return result


    def recurse_rename(self, items, renames, category):
        """
        Recursively goes through all items and item children,
        renaming specified types to specified values.

        @param   category  original statement category
        """
        for ctx in items:
            for k, v in renames.items():
                cls, c = self.RENAME_CTXS.get(k), ctx
                if not cls or not isinstance(ctx, cls): continue # for k, v

                # Get the deepest terminal, the one holding name value
                while not isinstance(c, TerminalNode): c = c.children[0]
                v0 = self.u(c).lower()

                # Skip special table names "OLD"/"NEW" in trigger body and WHEN
                if "table" == k and SQL.CREATE_TRIGGER == category \
                and v0 in ("old", "new") \
                and self.get_parent(c, self.TRIGGER_BODY_CTXS):
                    continue # for k, v

                if isinstance(v, dict):
                    for v1, v2 in v.items():
                        if v0 == v1.lower(): c.getSymbol().text = quote(v2)
                else: c.getSymbol().text = quote(v)

            if getattr(ctx, "children", None):
                self.recurse_rename(ctx.children, renames, category)



class Generator(object):
    """
    SQL generator.
    """

    TEMPLATES = {
        "COLUMN":                  templates.COLUMN_DEFINITION,
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
        @return            SQL string, or None if unknown data category
        """
        category = self._category = (category or data["__type__"]).upper()
        if category not in self.TEMPLATES: return

        REPLACE_ORDER = ["Q", "PAD", "LF", "CM", "GLUE", "PRE", "WS"]
        ns = {"Q":    self.quote,   "LF": self.linefeed, "PRE": self.indentation,
              "PAD":  self.padding, "CM": self.comma,    "WS":  self.token,
              "GLUE": self.glue,
              "data": data, "step": step, "templates": templates}

        # Generate SQL, using unique tokens for whitespace-sensitive parts,
        # replaced after stripping down whitespace in template result.
        tpl = step.Template(self.TEMPLATES[category], strip=True, collapse=True)
        while True:
            self._tokens.clear(); self._tokendata.clear(); self._data = data
            result = tpl.expand(ns)

            for token in self._tokens.values():
                # Redo if data happened to contain a generated token
                if result.count(token) > self._tokendata[token]["count"]:
                    continue # while

            # Calculate max length for paddings
            widths = defaultdict(int)
            for (tokentype, _), token in self._tokens.items():
                if "PAD" != tokentype: continue # for
                data = self._tokendata[token]
                widths[data["key"]] = max(len(data["value"]), widths[data["key"]])

            for (tokentype, val), token in sorted(
                self._tokens.items(), key=lambda x: REPLACE_ORDER.index(x[0][0])
            ):
                if tokentype in ("GLUE", "LF"):  # Strip surrounding whitespace
                    result = re.sub(r"\s*%s\s*" % re.escape(token), val, result)
                elif "PAD" == tokentype: # Insert spaces per padding type/value
                    data = self._tokendata[token]
                    ws = " " * (widths[data["key"]] - len(data["value"]))
                    result = result.replace(token, ws)
                elif "CM" == tokentype:
                    # Strip leading whitespace and multiple trailing spaces from commas
                    r = r"\s*" + re.escape(token) + ("" if self._indent else " *")
                    result = re.sub(r, val, result, flags=re.U)
                else: result = result.replace(token, val)
            break # while

        self._tokens.clear(); self._tokendata.clear(); self._data = None
        return result


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


    def indentation(self):
        """Returns line indentation token if indented SQL, else empty string."""
        return self.token(self._indent, "PRE") if self._indent else ""


    def quote(self, val):
        """Returns token for quoted value if needs quoting, else given value."""
        val, quoted = uni(val), quote(val)
        return self.token(quoted, "Q") if quoted != val else val


    def padding(self, key, data):
        """
        Returns whitespace padding token for data[key] if indented SQL,
        else empty string. Whitespace will be justified to data[key] max length.
        """
        if not self._indent: return ""
        return self.token("%s-%s" % (key, data[key]), "PAD",
                          key=key, value=data[key])


    def glue(self):
        """ Returns token that consumes surrounding whitespace. """
        return self.token("", "GLUE")


    def comma(self, collection, index, subcollection=None, subindex=None):
        """
        Returns trailing comma token for item in specified collection,
        if not last item and no other collections following.
        """
        islast = True
        if subcollection:
            container = self._data[collection][index]
            islast = (subindex == len(container[subcollection]) - 1)
        elif "columns" == collection and SQL.CREATE_TABLE == self._category:
            islast = not self._data.get("constraints") and \
                     (index == len(self._data[collection]) - 1)
        else:
            islast = (index == len(self._data[collection]) - 1)
            
        val = "" if islast else "," + (" " if not self._indent else "")
        return self.token(val, "CM") if val else ""



def test():
    import json
    logging.basicConfig()

    TEST_STATEMENTS = [
        u'''
        CREATE UNIQUE INDEX IF NOT EXISTS
        myschema.myname ON mytable (mycol1, mycol) WHERE mytable.mycol1 NOT BETWEEN mytable.mycol2 AND mytable.mycol3
        ''',


        """
        -- comment
        CREATE TEMP TABLE -- comment
        -- comment
        IF NOT EXISTS 
        -- comment
        feeds (
            -- first line comment
            myname TEXT PRIMARY KEY AUTOINCREMENT,
            mynumber INTEGER NOT NULL, -- my comment
            mybool
            /* multiline
            comment */
            -- last line comment
        ) -- comment
        WITHOUT ROWID -- comment
        -- comment

        """,


        u'''
        CREATE TABLE IF NOT EXISTS "feeds2" (
            mykey     INTEGER NOT NULL DEFAULT (666666),
            myinteger INTEGER NOT NULL ON CONFLICT ABORT DEFAULT /* uhuu */ -666.5 UNIQUE ON CONFLICT ROLLBACK,
            mycol     INTEGER CHECK (NULL IS /* hoho */ NULL) COLLATE /* haha */ BiNARY,
            mytext    TEXT NOT NULL CHECK (sometable.somecolumn),
            mydate    TIMESTAMP WITH TIME ZONE,
            fk_col    INTEGER REFERENCES ratings (id) ON delete cascade on update no action match foo MATCH bar,
            PRIMARY KEY (mykey) ON CONFLICT ROLLBACK,
            FOREIGN KEY (fk_col, myinteger) REFERENCES ratings (id, someid2) ON DELETE CASCADE ON UPDATE RESTRICT,
            CONSTRAINT myconstraint CHECK (666)
        )
        ''',


        u'''
        CREATE TRIGGER myschema.mytriggéér AFTER UPDATE OF address ON customers 
        WHEN 1 NOT IN (SELECT rootpage FROM sqlite_master)
          BEGIN
            UPDATE "söme öther täble" SET address = NEW.address WHERE customer_name = OLD.name;
            INSERT INTO foo (bar) VALUES (42);
            UPDATE orders2 SET address2 = new.address WHERE customer_name = old.name;
          END;
        ''',


        u'''
            CREATE TEMPORARY VIEW IF NOT EXISTS
            myschema.myname (mycol1, mycol2, "my col 3")
            AS SELECT * FROM mytable
        ''',


        u'''
        CREATE VIRTUAL TABLE IF NOT EXISTS myschemaname.mytable
        USING mymodule (myargument1, myargument2);
        ''',
    ]


    indent = "  "
    renames = {"table": "renämed tablé", "trigger": "renämed triggér",
               "index": "renämed indéx", "schema":  "renämed schéma",
               "view":   {"myname": u"renämed viéw"}}
    for sql1 in TEST_STATEMENTS:
        print "\n%s\nORIGINAL:\n" % ("-" * 70)
        print sql1.encode("utf-8")

        x = parse(sql1)
        if not x: continue # for sql1

        print "\n%s\nPARSED:" % ("-" * 70)
        print json.dumps(x, indent=2)
        sql2 = generate(x, indent)
        if sql2:
            print "\n%s\nGENERATED:\n" % ("-" * 70)
            print sql2.encode("utf-8") if sql2 else sql2

            print "\n%s\nTRANSFORMED:\n" % ("-" * 70)
            sql3 = transform(sql2, renames=renames, indent=indent)
            print sql3.encode("utf-8") if sql3 else sql3



if __name__ == '__main__':
    test()
