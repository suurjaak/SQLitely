# -*- coding: utf-8 -*-
"""
SQLite database access functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    29.07.2020
------------------------------------------------------------------------------
"""
from collections import defaultdict, OrderedDict
import copy
import datetime
import logging
import math
import os
import re
import sqlite3
import tempfile

from . lib.util import CaselessDict
from . lib.vendor import step
from . lib import util
from . import conf
from . import grammar
from . import templates

logger = logging.getLogger(__name__)


class Database(object):
    """Access to an SQLite database file."""


    """Column type affinity map."""
    AFFINITY = {
        "INTEGER": ["INT", "INTEGER", "TINYINT", "SMALLINT", "MEDIUMINT", "BIGINT", "UNSIGNED BIG INT", "INT2", "INT8"],
        "TEXT":    ["CHARACTER", "VARCHAR", "VARYING CHARACTER", "NCHAR", "NATIVE CHARACTER", "NVARCHAR", "TEXT", "CLOB"],
        "BLOB":    ["BLOB"],
        "REAL":    ["DOUBLE", "DOUBLE PRECISION", "FLOAT", "REAL"],
        "NUMERIC": ["DECIMAL", "BOOLEAN", "DATE", "DATETIME", "NUMERIC"],
    }

    """Schema object categories."""
    CATEGORIES = ["table", "index", "trigger", "view"]


    """
    SQLite PRAGMA settings, as {
        name:         directive name,
        label:        directive label,
        type:         type function or special like "table",
        short:        "short text",
        description:  "long text",
        ?values:      {primitive: label},
        ?default:     directive default value,
        ?deprecated:  whether directive is deprecated,
        ?dump:        whether directive should be included in db dump
                      and statistics export,
        ?stats:       whether directive should be included in statistics export,
        ?initial:     whether directive should be issued before creating schema
                      or a callable(db, value) returning whether,
        ?min:         minimum integer value,
        ?max:         maximum integer value,
        ?read:        false if setting is write-only,
        ?write:       false if setting is read-only
                      or a callable(db) returning false,
        ?col:         result column to select if type "table"
    }.
    """
    PRAGMA = {
      "application_id": {
        "name": "application_id",
        "label": "Application ID",
        "type": int,
        "dump": True,
        "short": "Application-specified unique integer",
        "description": "Applications can set a unique integer so that utilities can determine the specific file type.",
      },
      "auto_vacuum": {
        "name": "auto_vacuum",
        "label": "Auto-vacuum",
        "type": int,
        "values": {0: "NONE", 1: "FULL", 2: "INCREMENTAL"},
        "dump": True,
        "initial": True,
        "write": lambda db: not db.schema.values() and not db.filesize,
        "short": "Auto-vacuum settings",
        "description": """  FULL: truncate deleted rows on every commit.
  INCREMENTAL: truncate on PRAGMA incremental_vacuum.

  Must be turned on before any tables are created, not possible to change afterwards.""",
      },
      "automatic_index": {
        "name": "automatic_index",
        "label": "Automatic index",
        "type": bool,
        "short": "Use an automatic index if table has none of its own",
        "description": "When no indexes are available to aid the evaluation of a query, SQLite might create an automatic index that lasts only for the duration of a single SQL statement.",
      },
      "busy_timeout": {
        "name": "busy_timeout",
        "label": "Busy timeout",
        "type": int,
        "min": 0,
        "short": "Locked table access timeout",
        "description": "Timeout in milliseconds for busy handler when table is locked.",
      },
      "cache_size": {
        "name": "cache_size",
        "label": "Cache size",
        "type": int,
        "short": "Suggested number of disk pages in nemory",
        "description": """  Suggested maximum number of database disk pages that SQLite will hold in memory at once per open database file. Endures only for the length of the current session.
  If positive, the suggested cache size is set to N. If negative, the number of cache pages is adjusted to use approximately abs(N*1024) bytes.""",
      },
      "case_sensitive_like": {
        "name": "case_sensitive_like",
        "label": "Case-sensitive LIKE",
        "type": bool,
        "read": False,
        "short": "Case sensitivity on LIKE operator",
        "description": "Toggles case sensitivity on LIKE operator.",
      },
      "cache_spill": {
        "name": "cache_spill",
        "label": "Cache spill",
        "type": bool,
        "short": "Spill dirty cache pages to file during transaction",
        "description": "Enables or disables the ability of the pager to spill dirty cache pages to the database file in the middle of a transaction.",
      },
      "cell_size_check": {
        "name": "cell_size_check",
        "label": "Cell-size check",
        "type": bool,
        "read": False,
        "short": "Additional sanity checking on b-tree pages",
        "description": "Enables or disables additional sanity checking on database b-tree pages as they are initially read from disk. If enabled, database corruption is detected earlier and is less likely to 'spread', with the price of a small performance hit.",
      },
      "checkpoint_fullfsync": {
        "name": "checkpoint_fullfsync",
        "label": "Full FSYNC on checkpoint",
        "type": bool,
        "read": False,
        "short": "Full FSYNC during checkpoint operations",
        "description": "If enabled, then the F_FULLFSYNC syncing method is used during checkpoint operations on systems that support F_FULLFSYNC (Mac OS-X only).",
      },
      "collation_list": {
        "name": "collation_list",
        "label": "Collation list",
        "type": "table",
        "col": "name",
        "write": False,
        "short": "Collating sequences for current session",
        "description": "A list of the collating sequences defined for the current database connection.",
      },
      "compile_options": {
        "name": "compile_options",
        "label": "Compile options",
        "type": "table",
        "col": "compile_option",
        "write": False,
        "short": "SQLite compile-time options",
        "description": "Compile-time options used when building current SQLite library.",
      },
      "count_changes": {
        "name": "count_changes",
        "label": "Count changes",
        "type": bool,
        "deprecated": True,
        "short": "Return number of affected rows on action queries",
        "description": "If enabled, INSERT, UPDATE and DELETE statements return a single data row, with the number of rows inserted, modified or deleted (not including trigger or foreign key actions).",
      },
      "data_store_directory": {
        "name": "data_store_directory",
        "label": "Data-store directory",
        "type": unicode,
        "default": "",
        "deprecated": True,
        "short": "Windows-specific directory for relative pathnames",
        "description": "Global variable, used by interface backends on Windows to determine where to store database files specified using a relative pathname.",
      },
      "data_version": {
        "name": "data_version",
        "label": "Data version",
        "type": int,
        "write": False,
        "short": "Data change indicator",
        "description": "Indication that the database file has been modified by another connection during the current session.",
      },
      "default_cache_size": {
        "name": "default_cache_size",
        "label": "Default cache size",
        "type": int,
        "default": -2000,
        "deprecated": True,
        "dump": True,
        "short": "Suggested number of disk cache pages",
        "description": "The suggested maximum number of pages of disk cache that will be allocated per open database file; persists across database connections.",
      },
      "defer_foreign_keys": {
        "name": "defer_foreign_keys",
        "label": "Defer foreign keys",
        "type": bool,
        "short": "Delay foreign key enforcement",
        "description": "If enabled, enforcement of all foreign key constraints is delayed until the outermost transaction is committed. By default, foreign key constraints are only deferred if they are created as 'DEFERRABLE INITIALLY DEFERRED'. Is automatically switched off at each COMMIT or ROLLBACK, and must be separately enabled for each transaction.",
      },
      "empty_result_callbacks": {
        "name": "empty_result_callbacks",
        "label": "Empty-result-callbacks",
        "type": bool,
        "deprecated": True,
        "short": "sqlite3_exec() returns column names even on no data",
        "description": "Affects the sqlite3_exec() API only. Normally, the callback function supplied to sqlite3_exec() is not invoked for commands that return zero rows of data. If enabled, the callback function is invoked exactly once, with the third parameter set to 0 (NULL), to enable programs that use the sqlite3_exec() API to retrieve column-names even when a query returns no data.",
      },
      "encoding": {
        "name": "encoding",
        "label": "Encoding",
        "type": str,
        "dump": True,
        "initial": True,
        "write": lambda db: not db.schema.values() and not db.filesize,
        "short": "Database text encoding",
        "values": {"UTF-8": "UTF-8", "UTF-16": "UTF-16 native byte-ordering", "UTF-16le": "UTF-16 little endian", "UTF-16be": "UTF-16 big endian"},
        "description": "The text encoding used by the database. It is not possible to change the encoding after the database has been created.",
      },
      "foreign_keys": {
        "name": "foreign_keys",
        "label": "Foreign key constraints",
        "type": bool,
        "short": "Foreign key enforcement",
        "description": "If enabled, foreign key constraints are enforced for the duration of the current session.",
      },
      "freelist_count": {
        "name": "freelist_count",
        "label": "Freelist count",
        "type": int,
        "stats": True,
        "write": False,
        "short": "Unused pages",
        "description": "The number of unused pages in the database file.",
      },
      "full_column_names": {
        "name": "full_column_names",
        "label": "Full column names",
        "type": bool,
        "deprecated": True,
        "short": "Result columns as TABLE.COLUMN",
        "description": "If enabled and short_column_names is disabled, specifying TABLE.COLUMN in SELECT will yield result columns as TABLE.COLUMN.",
      },
      "fullfsync": {
        "name": "fullfsync",
        "label": "Full FSYNC",
        "type": bool,
        "short": "Use Full FSYNC",
        "description": "Determines whether or not the F_FULLFSYNC syncing method is used on systems that support it (Mac OS-X only).",
      },
      "ignore_check_constraints": {
        "name": "ignore_check_constraints",
        "label": "Ignore check constraints",
        "type": bool,
        "short": "CHECK constraint enforcement",
        "description": "Enables or disables the enforcement of CHECK constraints.",
      },
      "journal_mode": {
        "name": "journal_mode",
        "label": "Journal mode",
        "type": str,
        "values": {"delete": "DELETE", "truncate": "TRUNCATE", "persist": "PERSIST", "memory": "MEMORY", "wal": "WAL", "off": "OFF"},
        "short": "Database journaling mode",
        "description": """  DELETE: the rollback journal is deleted at the conclusion of each transaction."
  TRUNCATE: commits transactions by truncating the rollback journal to zero-length instead of deleting it (faster on many systems).
  PERSIST: prevents the rollback journal from being deleted at the end of each transaction. Instead, the header of the journal is overwritten with zeros. This will prevent other database connections from rolling the journal back.
  MEMORY: stores the rollback journal in volatile RAM. This saves disk I/O but at the expense of database safety and integrity. If the application using SQLite crashes in the middle of a transaction, the database file will very likely go corrupt.
  WAL: uses a write-ahead log instead of a rollback journal to implement transactions. The WAL journaling mode is persistent; after being set it stays in effect across multiple database connections and after closing and reopening the database.
  OFF: disables the rollback journal completely. Disables the atomic commit and rollback capabilities of SQLite. The ROLLBACK command no longer works and its behavior is undefined. If the application crashes in the middle of a transaction, the database file will very likely go corrupt.""",
      },
      "journal_size_limit": {
        "name": "journal_size_limit",
        "label": "Journal size limit",
        "type": int,
        "short": "Journal size byte limit",
        "description": """  Byte limit on the size of rollback-journal and WAL files left in the file-system after transactions or checkpoints. Each time a transaction is committed or a WAL file resets, SQLite compares the size of the rollback journal file or WAL file left in the file-system to the size limit set by this pragma, and if the journal or WAL file is larger, it is truncated to the limit.
  A negative number implies no limit. To always truncate rollback journals and WAL files to their minimum size, set to zero.""",
      },
      "legacy_file_format": {
        "name": "legacy_file_format",
        "label": "Legacy file format",
        "type": bool,
        "short": "Backwards-compatible database file format",
        "description": "If enabled, new SQLite databases are created in a file format that is readable and writable by all versions of SQLite going back to 3.0.0. If disabled, new databases are created using the latest file format, which might not be readable or writable by versions of SQLite prior to 3.3.0. Does not tell which file format the current database is using; it tells what format will be used by any newly created databases.",
      },
      "locking_mode": {
        "name": "locking_mode",
        "label": "Locking mode",
        "type": str,
        "values": {"normal": "NORMAL", "exclusive": "EXCLUSIVE"},
        "short": "Transaction locking mode",
        "description": """  NORMAL: a database connection unlocks the database file at the conclusion of each read or write transaction.
  EXCLUSIVE: the database connection never releases file-locks. The first time the database is read in EXCLUSIVE mode, a shared lock is obtained and held. The first time the database is written, an exclusive lock is obtained and held. Database locks obtained by a connection in EXCLUSIVE mode may be released either by closing the database connection, or by setting the locking-mode back to NORMAL using this pragma and then accessing the database file (for read or write). Simply setting the locking-mode to NORMAL is not enough - locks are not released until the next time the database file is accessed.""",
      },
      "max_page_count": {
        "name": "max_page_count",
        "label": "Max page count",
        "type": int,
        "min": 0,
        "short": "Maximum number of database pages",
        "description": "The maximum number of pages in the database file. Cannot be reduced below the current database size.",
      },
      "mmap_size": {
        "name": "mmap_size",
        "label": "Memory-map size",
        "type": int,
        "short": "Maximum byte number for memory-mapped I/O",
        "description": """  The maximum number of bytes that are set aside for memory-mapped I/O on a single database. If zero, memory mapped I/O is disabled.
  If negative, the limit reverts to the default value determined by the most recent sqlite3_config(SQLITE_CONFIG_MMAP_SIZE), or to the compile time default determined by SQLITE_DEFAULT_MMAP_SIZE if no start-time limit has been set.""",
      },
      "page_count": {
        "name": "page_count",
        "label": "Page count",
        "type": int,
        "stats": True,
        "write": False,
        "short": "Total number of pages",
        "description": "The total number of pages in the database file.",
      },
      "page_size": {
        "name": "page_size",
        "label": "Page size",
        "type": int,
        "values": {512: 512, 1024: 1024, 2048: 2048, 4096: 4096, 8192: 8192, 16384: 16384, 32768: 32768, 65536: 65536},
        "dump": True,
        "initial": True,
        "short": "Database page byte size",
        "description": "The page size of the database. Specifying a new size does not change the page size immediately. Instead, the new page size is remembered and is used to set the page size when the database is first created, if it does not already exist when the page_size pragma is issued, or at the next VACUUM command that is run on the same database connection while not in WAL mode.",
      },
      "query_only": {
        "name": "query_only",
        "label": "Query only",
        "type": bool,
        "initial": lambda db, v: not v, # Should be first only if false, else last
        "short": "Prevent database changes",
        "description": "If enabled, prevents all changes to the database file for the duration of the current session.",
      },
      "recursive_triggers": {
        "name": "recursive_triggers",
        "label": "Recursive triggers",
        "type": bool,
        "short": "Enable recursive trigger capability",
        "description": "Affects the execution of all statements prepared using the database connection, including those prepared before the setting was changed.",
      },
      "reverse_unordered_selects": {
        "name": "reverse_unordered_selects",
        "label": "Reverse unordered selects",
        "type": bool,
        "short": "Unordered SELECT queries return results in reverse order",
        "description": "If enabled, this PRAGMA causes many SELECT statements without an ORDER BY clause to emit their results in the reverse order from what they normally would, for the duration of the current session.",
      },
      "schema_version": {
        "name": "schema_version",
        "label": "Schema version",
        "type": int,
        "min": 0,
        "dump": True,
        "short": "Database schema-version",
        "description": "SQLite automatically increments the schema-version whenever the schema changes or VACUUM is performed. As each SQL statement runs, the schema version is checked to ensure that the schema has not changed since the SQL statement was prepared. Subverting this mechanism by changing schema_version may cause SQL statement to run using an obsolete schema, which can lead to incorrect answers and/or database corruption.",
      },
      "secure_delete": {
        "name": "secure_delete",
        "label": "Secure delete",
        "type": bool,
        "short": "Zero-fill deleted content",
        "description": "If enabled, SQLite overwrites deleted content with zeros. If disabled, improves performance by reducing the number of CPU cycles and the amount of disk I/O.",
      },
      "short_column_names": {
        "name": "short_column_names",
        "label": "Short column names",
        "type": bool,
        "deprecated": True,
        "short": "Result columns omit table name prefix",
        "description": "Affects the way SQLite names columns of data returned by SELECT statements.",
      },
      "synchronous": {
        "name": "synchronous",
        "label": "Synchronous",
        "type": int,
        "values": {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"},
        "short": "File synchronization mode",
        "description": """  OFF: SQLite continues without syncing as soon as it has handed data off to the operating system. If the application running SQLite crashes, the data will be safe, but the database might become corrupted if the operating system crashes or the computer loses power before that data has been written to the disk surface. On the other hand, commits can be orders of magnitude faster with synchronous OFF.
  NORMAL: the SQLite database engine will still sync at the most critical moments, but less often than in FULL mode. There is a very small (though non-zero) chance that a power failure at just the wrong time could corrupt the database in NORMAL mode. But in practice, you are more likely to suffer a catastrophic disk failure or some other unrecoverable hardware fault. Many applications choose NORMAL when in WAL mode.
  FULL: the SQLite database engine will use the xSync method of the VFS to ensure that all content is safely written to the disk surface prior to continuing. This ensures that an operating system crash or power failure will not corrupt the database. FULL synchronous is very safe, but it is also slower. FULL is the most commonly used synchronous setting when not in WAL mode.
  EXTRA: like FULL but with the addition that the directory containing a rollback journal is synced after that journal is unlinked to commit a transaction in DELETE mode. EXTRA provides additional durability if the commit is followed closely by a power loss.""",
      },
      "temp_store": {
        "name": "temp_store",
        "label": "Temporary store",
        "type": int,
        "values": {0: "DEFAULT", 1: "FILE", 2: "MEMORY"},
        "default": 0,
        "dump": True,
        "short": "Location of temporary tables and indexes",
        "description": """  DEFAULT: the compile-time C preprocessor macro SQLITE_TEMP_STORE is used to determine where temporary tables and indexes are stored.
  FILE: temporary tables and indexes are stored in a file. The temp_store_directory pragma can be used to specify the directory containing temporary files when FILE is specified. 
  MEMORY: temporary tables and indexes are kept in as if they were pure in-memory databases memory. 

  When the temp_store setting is changed, all existing temporary tables, indexes, triggers, and views are immediately deleted.""",
      },
      "temp_store_directory": {
        "name": "temp_store_directory",
        "label": "Temporary store directory",
        "type": unicode,
        "default": "",
        "deprecated": True,
        "short": "Location of temporary storage",
        "description": "Value of the sqlite3_temp_directory global variable, which some operating-system interface backends use to determine where to store temporary tables and indexes.",
      },
      "threads": {
        "name": "threads",
        "label": "Threads",
        "type": int,
        "min": 0,
        "short": "Number of auxiliary threads for prepared statements",
        "description": "The upper bound on the number of auxiliary threads that a prepared statement is allowed to launch to assist with a query.",
      },
      "user_version": {
        "name": "user_version",
        "label": "User version",
        "type": int,
        "min": 0,
        "dump": True,
        "short": "User-defined database version number",
        "description": "User-defined version number for the database.",
      },
      "wal_autocheckpoint": {
        "name": "wal_autocheckpoint",
        "label": "WAL auto-checkpoint interval",
        "type": int,
        "short": "Auto-checkpoint interval for WAL",
        "description": "Auto-checkpoint interval for WAL. When the write-ahead log is enabled (via PRAGMA journal_mode), a checkpoint will be run automatically whenever the write-ahead log equals or exceeds N pages in length. Zero or a negative value turns auto-checkpointing off.",
      },
      "writable_schema": {
        "name": "writable_schema",
        "label": "Writable schema",
        "type": bool,
        "short": "Writable sqlite_master",
        "description": """If enabled, the sqlite_master table can be changed using ordinary UPDATE, INSERT, and DELETE statements, for the duration of the current session. 

WARNING: misuse can easily result in a corrupt database file.""",
      },
    }
    """Additional PRAGMA directives not usable as settings."""
    EXTRA_PRAGMAS = [
        "database_list", "foreign_key_check", "foreign_key_list",
        "incremental_vacuum", "index_info", "index_list", "index_xinfo",
        "integrity_check", "optimize", "quick_check", "read_uncommitted",
        "shrink_memory", "soft_heap_limit", "table_info", "wal_checkpoint"
    ]

    """Temporary file name counter."""
    temp_counter = 1



    def __init__(self, filename=None, log_error=True, parse=False):
        """
        Initializes a new database object from the file.

        @param   filename   if None, creates a temporary file database,
                            file deleted on close
        @param   log_error  if False, exceptions on opening the database
                            are not written to log (written by default)
        @param   parse      parse all CREATE statements in full, complete metadata
        """
        self.filename = filename
        self.name = filename
        self.temporary = (filename is None)
        if self.temporary:
            fh, self.filename = tempfile.mkstemp(".db")
            os.close(fh)
            self.name = "New database"
            if self.temp_counter > 1: self.name += " (%s)" % self.temp_counter
            Database.temp_counter += 1
        self.filesize = None
        self.date_created = None
        self.last_modified = None
        self.log = [] # [{timestamp, action, sql: "" or [""], ?params: x or [x]}]
        self.compile_options = []
        self.consumers = set() # Registered objects using this database
        # {category: {name.lower(): set(lock key, )}}
        self.locks = defaultdict(lambda: defaultdict(set))
        self.locklabels = {} # {lock key: label}
        # {"table|index|view|trigger":
        #   {name:
        #     {name: str, sql: str, ?table: str, ?columns: [], ?count: int,
        #      ?meta: {full metadata}}}}
        self.schema = defaultdict(CaselessDict)
        self.connection = None
        self.open(log_error=log_error, parse=parse)


    def __str__(self):
        return self.name


    def open(self, log_error=True, parse=False):
        """Opens the database."""
        try:
            self.connection = sqlite3.connect(self.filename,
                                              check_same_thread=False)
            self.connection.row_factory = self.row_factory
            self.connection.text_factory = str
            self.compile_options = [x.values()[0] for x in
                                    self.execute("PRAGMA compile_options", log=False).fetchall()]
            self.populate_schema(parse=parse)
            self.update_fileinfo()
        except Exception:
            if log_error: logger.exception("Error opening database %s.", self.filename)
            try: self.connection.close()
            except Exception: pass
            self.connection = None
            raise


    def close(self):
        """Closes the database and frees all allocated data."""
        if self.connection:
            try: self.connection.close()
            except Exception: pass
            self.connection = None
        if self.temporary:
            try: os.unlink(self.filename)
            except Exception: pass
        self.schema.clear()


    def reopen(self, filename):
        """Opens the database with a new file, closing current connection if any."""
        if self.connection:
            try: self.connection.close()
            except Exception: pass
            self.connection = None
        self.filename = filename
        if not self.temporary: self.name = filename
        self.open()


    def check_integrity(self):
        """Checks SQLite database integrity, returning a list of errors."""
        result = []
        rows = self.execute("PRAGMA integrity_check").fetchall()
        if len(rows) != 1 or "ok" != rows[0].values()[0].lower():
            result = [r["integrity_check"] for r in rows]
        return result


    def recover_data(self, filename):
        """
        Recovers as much data from this database to a new database as possible.

        @return  a list of encountered errors, if any
        """
        result, sqls, pragma = [], [], {}
        with open(filename, "w") as _: pass # Truncate file
        self.execute("ATTACH DATABASE ? AS new", (filename, ))
        sqls.append("ATTACH DATABASE ? AS new")

        # Set initial PRAGMAs
        pragma_tpl = step.Template(templates.PRAGMA_SQL, strip=False)
        try: pragma = self.get_pragma_values(dump=True)
        except Exception: logger.exception("Failed to get PRAGMAs for %s.", self.name)
        pragma_first = {k: v for k, v in pragma.items()
                        if k in ("auto_vacuum", "page_size")}
        if pragma_first:
            sql = pragma_tpl.expand(pragma=pragma_first, schema="new")
            self.executescript(sql)
            sqls.append(sql)

        # Create structure for all tables
        for name, opts in self.schema["table"].items():
            try:
                sql, err = grammar.transform(opts["sql"], renames={"schema": "new"})
                if sql:
                    sqls.append(sql)
                    self.execute(sql)
                else: result.append(err)
            except Exception as e:
                result.append(util.format_exc(e))
                logger.exception("Error creating table %s in %s.",
                                 util.unprint(grammar.quote(name)), filename)

        # Copy data from all tables
        for name, opts in self.schema["table"].items():
            sql = "INSERT INTO new.%s SELECT * FROM main.%s" % ((grammar.quote(name),) * 2)
            try:
                self.execute(sql)
                sqls.append(sql)
            except Exception as e:
                result.append(util.format_exc(e))
                logger.exception("Error copying table %s from %s to %s.",
                                 util.unprint(grammar.quote(name)), self.filename, filename)

        # Create indexes-triggers-views
        for category in "index", "trigger", "view":
            for name, opts in self.schema[category].items():
                try:
                    sql, err = grammar.transform(opts["sql"], renames={"schema": "new"})
                    if sql:
                        self.execute(sql)
                        sqls.append(sql)
                    else: result.append(err)
                except Exception as e:
                    result.append(util.format_exc(e))
                    logger.exception("Error creating %s %s for %s.",
                                     category, util.unprint(grammar.quote(name)), filename)

        # Set closing PRAGMAs
        pragma_last  = {k: v for k, v in pragma.items()
                        if k in ("application_id", "schema_version", "user_version")}
        if pragma_last:
            sql = pragma_tpl.expand(pragma=pragma_last, schema="new")
            self.executescript(sql)
            sqls.append(sql)

        self.execute("DETACH DATABASE new")
        sqls.append("DETACH DATABASE new")
        self.log_query("RECOVER", sqls, filename)
        return result


    def register_consumer(self, consumer):
        """
        Registers a consumer with the database, notified on clearing cache by
        consumer.on_database_changed().
        """
        self.consumers.add(consumer)


    def unregister_consumer(self, consumer):
        """Removes a registered consumer from the database."""
        if consumer in self.consumers:
            self.consumers.remove(consumer)


    def has_consumers(self):
        """Returns whether the database has currently registered consumers."""
        return len(self.consumers) > 0 \
               or any(x.values() for x in self.locks.values())


    def lock(self, category, name, key, label=None):
        """
        Locks a schema object for altering or deleting. For tables, cascades
        lock to views that query the table; and for views, cascades lock to
        tables the view queries, also to other views that the view queries
        or that query the view; recursively.

        @param   key       any hashable to identify lock by
        @param   label     an informational label for lock
        """
        category, name = (x.lower() if x else x for x in (category, name))
        if name and name not in self.schema.get(category, {}): return            
        self.locks[category][name].add(key)
        self.locklabels[key] = label
        if category and name:
            relateds = self.get_related(category, name, data=True)
            if not relateds: return
            subkey = (hash(key), category, name)
            for subcategory, itemmap in relateds.items():
                for subname in itemmap:
                    self.locks[subcategory][subname.lower()].add(subkey)
            qname = util.unprint(grammar.quote(self.schema[category][name]["name"], force=True))
            self.locklabels[subkey] = " ".join(filter(bool, (category, qname, label, "cascade")))


    def unlock(self, category, name, key):
        """Unlocks a schema object for altering or deleting."""
        category, name = (x.lower() if x else x for x in (category, name))
        self.locks[category][name].discard(key)
        self.locklabels.pop(key, None)
        if category and name:
            subkey = (hash(key), category, name)
            relateds = self.get_related(category, name, data=True)
            for subcategory, itemmap in relateds.items():
                for subname in (x.lower() for x in itemmap):
                    self.locks[subcategory][subname].discard(subkey)
                    if not self.locks[subcategory][subname]:
                        self.locks[subcategory].pop(subname)
            self.locklabels.pop(subkey, None)
        if not self.locks[category][name]: self.locks[category].pop(name)
        if not self.locks[category]:       self.locks.pop(category)


    def clear_locks(self):
        """Clears all current locks."""
        self.locks.clear()
        self.locklabels.clear()


    def get_lock(self, *args, **kwargs):
        """
        Returns user-friendly information on current lock status, as
        "Database is currently locked (statistics analysis)" or
        "Table "foo" is currently locked" if querying category and name.

        @param   category  item category, or None for global lock,
                           or not given for any lock
        @param   name      specific item, if any
        @param   skip      keys to skip, if any
        """
        if "category" not in kwargs and args: kwargs["category"]  = args[0]
        if "name" not in kwargs and len(args) > 1: kwargs["name"] = args[1]
        if "skip" not in kwargs and len(args) > 2: kwargs["skip"] = args[2]
        skipkeys = set(util.tuplefy(kwargs.get("skip", ())))
        for k, v in kwargs.items():
            if isinstance(v, basestring): kwargs[k] = v.lower()
        result, keys = "", ()

        if kwargs.get("category") and kwargs.get("name"):
            category, name = kwargs["category"], kwargs["name"]
            keys = self.locks.get(category, {}).get(name)
            if keys and skipkeys: keys -= skipkeys
            name = self.schema.get(category, {}).get(name, {}).get("name", name)
            if keys: result = "%s %s is currently locked" % \
                              (category.capitalize(), util.unprint(grammar.quote(name, force=True)))
        elif kwargs.get("category"): # Check for lock on any item in category
            category = kwargs["category"]
            keys = set(y for x in self.locks.get(category, {}).values() for y in x)
            if keys and skipkeys: keys -= skipkeys
            if keys: result = "%s are currently locked" % util.plural(category.capitalize())

        if not result: # Check for global lock
            keys = self.locks.get(None, {}).get(None)
            if keys and skipkeys: keys -= skipkeys
            if keys: result = "Database is currently locked"
        if not kwargs and not result and self.locks: # No args: check for any lock
            keys = self.locklabels.keys()
            if keys and skipkeys: keys -= skipkeys
            if keys: result = "Database is currently locked"

        if result and keys:
            labels = filter(bool, map(self.locklabels.get, keys))
            if labels: result += " (%s)" % ", ".join(sorted(labels))
        return result


    def get_locks(self):
        """
        Returns user-friendly information on all current locks, as
        ["global lock (statistics analysis)", "table "MyTable" (export)", ].
        """
        result = []
        for category in sorted(self.locks):
            for name, keys in sorted(self.locks[category].items()):
                t, labels = "", filter(bool, map(self.locklabels.get, keys))
                if category and name:
                    name = self.schema.get(category, {}).get(name, {}).get("name", name)
                    t = "%s %s" % (category, util.unprint(grammar.quote(name, force=True)))
                elif category: t = util.plural(category)
                else: t = "global lock"
                if labels: t += " (%s)" % ", ".join(sorted(labels))
                result.append(t)
        return result


    def get_rowid(self, table):
        """
        Returns ROWID name for table, or None if table is WITHOUT ROWID
        or has columns shadowing all ROWID aliases (ROWID, _ROWID_, OID).
        """
        if util.get(self.schema["table"], table, "meta", "without"): return
        sql = self.schema["table"].get(table, {}).get("sql")
        if re.search("WITHOUT\s+ROWID[\s;]*$", sql, re.I): return
        ALIASES = ("_rowid_", "rowid", "oid")
        cols = [c["name"].lower() for c in self.schema["table"][table]["columns"]]
        return next((x for x in ALIASES if x not in cols), None)


    def has_view_columns(self):
        """Returns whether SQLite supports view columns (from version 3.9)."""
        return sqlite3.sqlite_version_info >= (3, 9)


    def has_rename_column(self):
        """Returns whether SQLite supports renaming columns (from version 3.25)."""
        return sqlite3.sqlite_version_info >= (3, 25)


    def has_full_rename_table(self):
        """
        Returns whether SQLite supports cascading table rename
        to triggers/views referring the table (from version 3.25).
        """
        return sqlite3.sqlite_version_info >= (3, 25)


    def execute(self, sql, params=(), log=True, cursor=None):
        """
        Shorthand for self.connection.execute(), returns cursor.
        Uses given cursor else creates new.
        """
        result = None
        if cursor or self.connection:
            if log and conf.LogSQL:
                logger.info("SQL: %s%s", sql,
                            ("\nParameters: %s" % params) if params else "")
            result = (cursor or self.connection).execute(sql, params)
        return result


    def executeaction(self, sql, params=(), log=True, name=None, cursor=None):
        """
        Executes the specified SQL INSERT/UPDATE/DELETE statement and returns
        the number of affected rows. Uses given cursor else creates new.
        """
        result = 0
        if cursor or self.connection:
            if log and conf.LogSQL:
                logger.info("SQL: %s%s", sql,
                            ("\nParameters: %s" % params) if params else "")
            result = (cursor or self.connection).execute(sql, params).rowcount
            if self.connection.isolation_level is not None: self.connection.commit()
            if name: self.log_query(name, sql, params)
            self.last_modified = datetime.datetime.now()
        return result


    def executescript(self, sql, log=True, name=None, cursor=None):
        """
        Executes the specified SQL as script. Uses given cursor else creates new.
        """
        if cursor or self.connection:
            if log and conf.LogSQL: logger.info("SQL: %s", sql)
            (cursor or self.connection).executescript(sql)
            if name: self.log_query(name, sql)


    def log_query(self, action, sql, params=None):
        """Adds the query to action log."""
        item = {"timestamp": datetime.datetime.now(), "action": action, "sql": sql}
        if params: item["params"] = params
        self.log.append(item)


    def is_open(self):
        """Returns whether the database is currently open."""
        return self.connection is not None


    def row_factory(self, cursor, row):
        """Returns dict from resultset rows, with BLOBs converted to strings."""
        result = {}
        for idx, col in enumerate(cursor.description):
            name = col[0]
            result[name] = row[idx]
        for name in result.keys():
            datatype = type(result[name])
            if datatype is buffer:
                result[name] = str(result[name]).decode("latin1")
            elif datatype is str or datatype is unicode:
                try:
                    result[name] = str(result[name]).decode("utf-8")
                except Exception:
                    result[name] = str(result[name]).decode("latin1")
        return result


    def populate_schema(self, count=False, parse=False, category=None, name=None):
        """
        Retrieves metadata on all database tables, triggers etc.

        @param   count      populate table row counts
        @param   parse      parse all CREATE statements in full, complete metadata
        @param   category   "table" | "index" | "trigger" | "view" if not everything
        @param   name       category item name if not everything in category
        """
        if not self.is_open(): return
        category, name = (x.lower() if x else x for x in (category, name))

        schema0 = copy.deepcopy(self.schema)
        if category:
            if name: self.schema[category].pop(name, None)
            else: self.schema[category].clear()
        else: self.schema.clear()

        # Retrieve general information from master
        where = "sql != :sql AND name NOT LIKE :notname"
        args = {"sql": "", "notname": "sqlite_%"}
        if category:
            where += " AND type = :type"; args.update(type=category)
            if name: where += " AND LOWER(name) = :name"; args.update(name=name)
        for row in self.execute(
            "SELECT * FROM sqlite_master "
            "WHERE %s ORDER BY type, name COLLATE NOCASE" % where, args, log=False
        ).fetchall():
            if "table" == row["type"] \
            and "ENABLE_ICU" not in self.compile_options: # Unsupported tokenizer
                if  re.match(r"CREATE\s+VIRTUAL\s+TABLE", row["sql"], re.I) \
                and re.search(r"TOKENIZE\s*[\W]*icu[\W]", row["sql"], re.I):
                    continue # for row

            sql = row["sql"].strip().replace("\r\n", "\n")
            sql = re.sub("\n\s+\)[\s;]*$", "\n)", sql) # Strip trailing whitespace and ;
            if not sql.endswith(";"): sql += ";"
            row["sql"] = row["sql0"] = sql
            self.schema[row["type"]][row["name"]] = row

        for mycategory, itemmap in self.schema.items():
            if category and category != mycategory: continue # for mycategory
            for myname, opts in itemmap.items():
                if category and name and not util.lceq(myname, name): continue # for myname

                opts0 = schema0.get(mycategory, {}).get(myname, {})

                # Retrieve metainfo from PRAGMA
                if mycategory in ("table", "view") and opts0 and opts["sql0"] == opts0["sql0"]:
                    opts["columns"] = opts0.get("columns") or []
                elif mycategory in ("table", "index", "view"):
                    pragma = "index_info" if "index" == mycategory else "table_info"
                    sql = "PRAGMA %s(%s)" % (pragma, grammar.quote(myname))
                    try:
                        rows = self.execute(sql, log=False).fetchall()
                    except Exception:
                        opts.update(columns=[])
                        logger.exception("Error fetching columns for %s %s.",
                                         mycategory, util.unprint(grammar.quote(myname)))
                    else:
                        opts["columns"] = []
                        for row in rows:
                            col = {"name": row["name"]}
                            if "type" in row: col["type"] = row["type"].upper()
                            if row.get("dflt_value") is not None:
                                col["default"] = row["dflt_value"]
                            if row.get("notnull"): col["notnull"] = {}
                            if row.get("pk"):      col["pk"]      = {}
                            opts["columns"].append(col)

                # Parse metainfo from SQL
                meta, sql = None, None
                if opts0 and opts0.get("meta") and opts["sql0"] == opts0["sql0"]:
                    meta, sql = opts0["meta"], opts0["sql"]
                elif parse:
                    meta, _ = grammar.parse(opts["sql0"])
                    if meta: sql, _ = grammar.generate(meta)
                if meta: opts.update(meta=meta)
                if sql and (not meta or not meta.get("__comments__")):
                    opts.update(sql=sql)
                if meta and "table" == mycategory and meta.get("columns"):
                    opts["columns"] = meta["columns"]

                # Retrieve table row counts
                if "table" == mycategory and count:
                    opts.update(self.get_count(myname))
                elif "table" == mycategory and opts0 and "count" in opts0:
                    opts["count"] = opts0["count"]
                    if "is_count_estimated" in opts0:
                        opts["is_count_estimated"] = opts0["is_count_estimated"]


    def get_count(self, table):
        """
        Returns {"count": int, ?"is_count_estimated": bool}.
        Uses MAX(ROWID) to estimate row count and skips COUNT(*) if likely
        to take too long (file over half a gigabyte).
        Estimated count is rounded upwards to 100.
        """
        result, do_full = {"count": None}, False
        tpl = "SELECT %%s AS count FROM %s LIMIT 1" % grammar.quote(table)
        try:
            rowidname = self.get_rowid(table)
            if rowidname:
                result = self.execute(tpl % "MAX(%s)" % rowidname, log=False).fetchone()
                result["count"] = int(math.ceil(result["count"] / 100.) * 100)
                result["is_count_estimated"] = True
            if self.filesize < conf.MaxDBSizeForFullCount \
            or result and result["count"] < conf.MaxTableRowIDForFullCount:
                do_full = True
        except Exception:
            do_full = (self.filesize < conf.MaxDBSizeForFullCount)

        try:
            if do_full:
                result = self.execute(tpl % "COUNT(*)", log=False).fetchone()
        except Exception:
            logger.exception("Error fetching COUNT for table %s.",
                             util.unprint(grammar.quote(table)))
        return result


    def get_category(self, category, name=None):
        """
        Returns database objects in specified category.

        @param   category  "table"|"index"|"trigger"|"view"
        @param   name      returns only this object,
                           or a dictionary with only these if collection
        @result            CaselessDict{name: {opts}},
                           or {opts} if single name
                           or None if no object by single name
        """
        category = category.lower()

        if isinstance(name, basestring):
            return copy.deepcopy(self.schema.get(category, {}).get(name))

        result = CaselessDict()
        for myname, opts in self.schema.get(category, {}).items():
            if name and myname not in name: continue # for myname
            result[myname] = opts
        return copy.deepcopy(result)


    def get_related(self, category, name, own=None, data=False, skip=None):
        """
        Returns database objects related to specified object in any way,
        like triggers selecting from a view,
        as {category: CaselessDict({name: item, })}.

        @param   own   if true, returns only direct ownership relations,
                       like table's own indexes and triggers for table,
                       view's own triggers for views,
                       index's own table for index,
                       and trigger's own table or view for triggers;
                       if False, returns only indirectly associated items,
                       like tables and views and triggers for tables and views
                       that query them in view or trigger body,
                       also foreign tables for tables;
                       if None, returns all relations
        @param   data  whether to return cascading data dependency
                       relations: for views, the tables and views they query,
                       recursively
        @param   skip  CaselessDict{name: True} to skip (internal recursion helper)
        """
        category, name = category.lower(), name.lower()
        result, skip = CaselessDict(), (skip or CaselessDict({name: True}))
        SUBCATEGORIES = {"table":   ["table", "index", "view", "trigger"],
                         "index":   ["table"],
                         "trigger": ["table", "view"],
                         "view":    ["table", "view", "trigger"]}
        if data: SUBCATEGORIES = {"view": ["table", "view"]}
            
        item = self.get_category(category, name)
        if not item or category not in SUBCATEGORIES or "meta" not in item:
            return result

        for subcategory in SUBCATEGORIES.get(category, []):
            for subname, subitem in self.schema[subcategory].items():
                if "meta" not in subitem or subname in skip:
                    continue # for subname, subitem
                is_own = util.lceq(subitem["meta"].get("table"), name) or \
                         util.lceq(item["meta"].get("table"), subname)
                is_rel_from = name in subitem["meta"]["__tables__"] \
                              or "trigger" == subcategory and is_own
                is_rel_to   = subname.lower() in item["meta"]["__tables__"] \
                              or "trigger" == category and is_own
                if not is_rel_to and not is_rel_from or data and not is_rel_to \
                or own is not None and bool(own) is not is_own:
                    continue # for subname, subitem

                if subcategory not in result: result[subcategory] = CaselessDict()
                result[subcategory][subname] = copy.deepcopy(subitem)

        visited = CaselessDict()
        for vv in result.values() if data else ():
            skip.update({v: True for v in vv})
        for mycategory, items in result.items() if data else ():
            if mycategory not in SUBCATEGORIES: continue # for mycategory, items
            for item in items:
                if item["name"] in visited: continue # for item
                visited[item["name"]] = True
                subresult = self.get_related(mycategory, item["name"], own, data, skip)
                for subcategory, subitemmap in subresult.items():
                    if subcategory not in result: result[subcategory] = CaselessDict()
                    result[subcategory].update(subitemmap)
                    visited.update(subitemmap)
                    skip.update(visited)

        return result


    def get_keys(self, table, pks_only=False):
        """
        Returns the local and foreign keys of a table. Local keys are
        table primary keys, plus any columns used as foreign keys by other tables.

        @param    pks_only  true if local keys should only be table primary keys,
                            not all columns used as foreign keys by other tables
        @return   ([{"name": ["col", ], "table": CaselessDict{ftable: ["fcol", ]}}],
                   [{"name": ["col", ], "table": CaselessDict{ftable: ["fcol", ]}}])
        """
        table = table.lower()
        item = self.schema["table"].get(table)
        if not item: return [], []

        def get_fks(myitem):
            cc = [c for c in myitem["columns"] if "fk" in c] + [
                dict(name=c["columns"], fk=c)
                for c in myitem.get("meta", {}).get("constraints", [])
                if grammar.SQL.FOREIGN_KEY == c["type"]
            ]
            return [dict(name=util.tuplefy(c["name"]), table=CaselessDict(
                {c["fk"]["table"]: util.tuplefy(c["fk"]["key"])}
            )) for c in cc]

        mykeys = CaselessDict((util.tuplefy(c["name"]),
                               dict(name=util.tuplefy(c["name"]), pk=c["pk"]))
                              for c in item["columns"] if "pk" in c)
        for c in item.get("meta", {}).get("constraints", []):
            if grammar.SQL.PRIMARY_KEY == c["type"]:
                names = tuple(x["name"] for x in c["key"])
                mykeys[names] = {"name": names, "pk": {}}
        relateds = {} if pks_only else self.get_related("table", table, False)
        for name2, item2 in relateds.get("table", {}).items():
            for fk in [x for x in get_fks(item2) if table in x["table"]]:
                keys = fk["table"][table]
                lk = mykeys.get(keys) or {"name": keys}
                lk.setdefault("table", CaselessDict())[name2] = fk["name"]
                mykeys[keys] = lk
        lks = sorted(mykeys.values(), key=lambda x: (len(x["name"]), "pk" not in x, x["name"]))

        fks = get_fks(item)
        fks.sort(key=lambda x: (len(x["name"]), x["name"])) # Singulars first
        fks = [x for x in fks]

        return lks, fks


    def get_sql(self, category=None, name=None, column=None, indent="  ",
                transform=None):
        """
        Returns full CREATE SQL statement for database, or for specific
        category only, or for specific category object only,
        or SQL line for specific table column only.

        @param   category   "table" | "index" | "trigger" | "view" if not everything
        @param   name       category item name if not everything in category,
                            or a list of names
        @param   column     named table column to return SQL for
        @param   indent     whether to format SQL with linefeeds and indentation
        @param   transform  {"flags":   flags to toggle, like {"exists": True},
                             "renames": renames to perform in SQL statement body,
                                        supported types "schema" (top-level rename only),
                                        "table", "index", "trigger", "view", "column".
                                        Schema renames as {"schema": s2} or {"schema": {s1: s2}},
                                        category renames as {category: {v1: v2}},
                                        column renames as {"columns": {table or view: {c1: c2}}},
                                        where category value should be the renamed value if
                                        the same transform is renaming the category as well.
                            }
        """
        sqls = OrderedDict() # {category: []}
        category, column = (x.lower() if x else x for x in (category, column))
        names = [x.lower() for x in ([] if name is None else util.tuplefy(name))]

        for mycategory in self.CATEGORIES:
            if category and category != mycategory \
            or not self.schema.get(mycategory): continue # for mycategory

            for myname, opts in self.schema[mycategory].items():
                if names and myname.lower() not in names:
                    continue # for myname, opts

                if names and column and "table" == mycategory:
                    col = next((c for c in opts["columns"]
                                if util.lceq(c["name"], column)), None)
                    if not col: continue # for myname, opts
                    sql, err = grammar.generate(dict(col, __type__="column"), indent=False)
                    if err: raise Exception(err)
                    return sql

                sql = sql0 = opts["sql"]
                kws = {x: transform[x] for x in ("flags", "renames")
                       if transform and x in transform}
                if not opts.get("meta") or kws or indent != "  ":
                    sql, err = grammar.transform(sql, indent=indent, **kws)
                    if err and kws: raise Exception(err)
                    elif not sql: sql = sql0
                sqls.setdefault(category, []).append(sql)

        return "\n\n".join("\n\n".join(vv) for vv in sqls.values())


    def get_default(self, col):
        """Returns the default value for column, selected from database."""
        result = None
        if "default" in col:
            result = self.execute("SELECT %s AS v" % col["default"]).fetchone()["v"]
        return result


    @staticmethod
    def get_affinity(col):
        """
        Returns column type affinity, e.g. "REAL" for "FLOAT".

        @param   col  column type string or {"type": column type}
        @return       matched affinity, or "BLOB" if unknown or unspecified type
        """
        mytype = col.get("type") if isinstance(col, dict) else col
        if not mytype or not isinstance(mytype, basestring): return "BLOB"

        mytype = mytype.upper()
        for aff, types in Database.AFFINITY.items(): # Exact match
            if mytype in types:
                return aff
        for aff, types in Database.AFFINITY.items(): # Partial match
            for afftype in types:
                if afftype.startswith(mytype) or mytype.startswith(afftype):
                    return aff
        return "BLOB"


    @staticmethod
    def is_valid_name(table=None, column=None):
        """
        Returns whether table or column name is a valid identifier.

        Tables must not start with "sqlite_", no limitations otherwise.
        """
        result = False
        if table:    result = not util.lceq(table[:7], "sqlite_")
        elif column: result = True
        return result


    def update_fileinfo(self):
        """Updates database file size and modification information."""
        self.filesize = os.path.getsize(self.filename)
        self.date_created  = datetime.datetime.fromtimestamp(
                             os.path.getctime(self.filename))
        self.last_modified = datetime.datetime.fromtimestamp(
                             os.path.getmtime(self.filename))


    def blobs_to_binary(self, values, list_columns, col_data):
        """
        Converts blob columns in the list to sqlite3.Binary, suitable
        for using as a query parameter.
        """
        result = []
        is_dict = isinstance(values, dict)
        list_values = [values[i] for i in list_columns] if is_dict else values
        map_columns = dict([(i["name"], i) for i in col_data])
        for i, val in enumerate(list_values):
            if val and "BLOB" == self.get_affinity(map_columns[list_columns[i]]):
                if isinstance(val, unicode):
                    val = val.encode("latin1")
                val = sqlite3.Binary(val)
            result.append(val)
        if is_dict:
            result = dict([(list_columns[i], x) for i, x in enumerate(result)])
        return result


    def fill_missing_fields(self, data, fields):
        """Creates a copy of the data and adds any missing fields."""
        filled = data.copy()
        for field in fields:
            if field not in filled:
                filled[field] = None
        return filled


    def make_args(self, cols, data, existing=None):
        """
        Returns ordered params dictionary, with column names made safe to use
        as ":name" parameters.

        @param   cols      ["col", ] or [{"name": "col"}, ]
        @param   data      {"col": val}
        @param   existing  already existing params dictionary,
                           for unique
        """
        result = OrderedDict()
        existing = dict(existing or {})
        for c in cols:
            if isinstance(c, dict): c = c["name"]
            name = re.sub(r"\W", "", c, flags=re.I)
            name = util.make_unique(name, existing, counter=1, case=True)
            result[name] = existing[name] = data[c]
        return result


    def select_row(self, table, row, rowid=None):
        """
        Fetches the table row from the database, identified by the given ROWID,
        or by the primary keys in its original values, or by all columns in its
        original values if table has no primary key.
        """
        if not self.is_open(): return

        table, where = self.schema["table"][table]["name"], ""
        col_data = self.schema["table"][table]["columns"]
        pks = [{"name": y} for x in self.get_keys(table, True)[0] for y in x["name"]]

        if rowid is not None and not (len(pks) == 1 and pks[0]["name"] in row):
            rowidname = self.get_rowid(table)
            key_data = [{"name": rowidname}]
            keyargs = self.make_args(key_data, {rowidname: rowid})
        else: # Use either primary key or all columns to identify row
            key_data = pks or col_data
            keyargs = self.make_args(key_data, row)
        for col, key in zip(key_data, keyargs):
            where += (" AND " if where else "") + "%s IS :%s" % (grammar.quote(col["name"]), key)
        sql = "SELECT * FROM %s WHERE %s" % (grammar.quote(table), where)
        return self.execute(sql, keyargs).fetchone()


    def insert_row(self, table, row):
        """
        Inserts the new table row in the database.

        @return  ID of the inserted row
        """
        if not self.is_open(): return

        table = self.schema["table"][table]["name"]
        logger.info("Inserting 1 row into table %s, %s.",
                    util.unprint(grammar.quote(table)), self.name)
        col_data = self.schema["table"][table]["columns"]
        fields = [col["name"] for col in col_data if col["name"] in row]
        row = self.blobs_to_binary(row, fields, col_data)
        args = self.make_args(fields, row)

        if args:
            str_cols = ", ".join(map(grammar.quote, fields))
            str_vals = (":" if args else "") + ", :".join(args)
            sql = "INSERT INTO %s (%s) VALUES (%s)" % \
                  (grammar.quote(table), str_cols, str_vals)
        else: sql = "INSERT INTO %s DEFAULT VALUES" % grammar.quote(table)
        cursor = self.execute(sql, args)
        if self.connection.isolation_level is not None: self.connection.commit()
        self.log_query("INSERT", sql, args)
        self.last_modified = datetime.datetime.now()
        return cursor.lastrowid


    def update_row(self, table, row, original_row, rowid=None):
        """
        Updates the table row in the database, identified by the given ROWID,
        or by the primary keys in its original values, or by all columns in its
        original values if table has no primary key.
        """
        if not self.is_open(): return

        table = self.schema["table"][table]["name"]
        logger.info("Updating 1 row in table %s, %s.",
                    grammar.quote(table), self.name)
        col_data = self.schema["table"][table]["columns"]

        changed_cols = [x for x in col_data
                        if row[x["name"]] != original_row[x["name"]]]
        where, args = "", self.make_args(changed_cols, row)
        setsql = ", ".join("%s = :%s" % (grammar.quote(changed_cols[i]["name"]), x)
                                         for i, x in enumerate(args))
        pks = [{"name": y} for x in self.get_keys(table, True)[0] for y in x["name"]]
        if rowid is not None and not (len(pks) == 1 and pks[0]["name"] in row):
            key_data = [{"name": "_rowid_"}]
            keyargs = self.make_args(key_data, {"_rowid_": rowid}, args)
        else: # Use either primary key or all columns to identify row
            key_data = pks or col_data
            keyargs = self.make_args(key_data, original_row, args)
        for col, key in zip(key_data, keyargs):
            where += (" AND " if where else "") + \
                     "%s IS :%s" % (grammar.quote(col["name"]), key)
        args.update(keyargs)
        self.executeaction("UPDATE %s SET %s WHERE %s" %
                           (grammar.quote(table), setsql, where), args,
                           name="UPDATE")


    def delete_row(self, table, row, rowid=None):
        """
        Deletes the table row from the database. Row is identified by its
        primary key, or by rowid if no primary key.

        @return   success as boolean
        """
        if not self.is_open(): return

        table, where = self.schema["table"][table]["name"], ""
        logger.info("Deleting 1 row from table %s, %s.",
                    util.unprint(grammar.quote(table)), self.name)
        col_data = self.schema["table"][table]["columns"]

        pks = [{"name": y} for x in self.get_keys(table, True)[0] for y in x["name"]]

        if rowid is not None and not (len(pks) == 1 and pks[0]["name"] in row):
            rowidname = self.get_rowid(table)
            key_data = [{"name": rowidname}]
            keyargs = self.make_args(key_data, {rowidname: rowid})
        else: # Use either primary key or all columns to identify row
            key_data = pks or col_data
            keyargs = self.make_args(key_data, row)
        for col, key in zip(key_data, keyargs):
            where += (" AND " if where else "") + "%s IS :%s" % (grammar.quote(col["name"]), key)
        self.executeaction("DELETE FROM %s WHERE %s" % (grammar.quote(table), where),
                           keyargs, name="DELETE")
        self.last_modified = datetime.datetime.now()
        return True


    def chunk_args(self, cols, rows):
        """
        Yields WHERE-clause and arguments in chunks of up to 1000 items
        (SQLite can have a maximum of 1000 host parameters per query).

        @yield    "name IN (:name1, ..)", {"name1": ..}
        """
        MAX = 1000
        for rows in [rows[i:i + MAX] for i in range(0, len(rows), MAX)]:
            wheres, args, names = [], OrderedDict(), set()

            for col in cols:
                base = re.sub(r"\W", "", col["name"], flags=re.I)
                name = base = util.make_unique(base, names, case=True)
                names.add(base)
                if len(rows) == 1:
                    where = "%s = :%s" % (grammar.quote(col["name"]), name)
                    args[name] = rows[0][col["name"]]
                else:
                    mynames = []
                    for i, row in enumerate(rows):
                        name = util.make_unique(base, names, counter=1, case=True)
                        args[name] = row[col["name"]]
                        mynames.append(name); names.add(name)
                    where = "%s IN (:%s)" % (grammar.quote(col["name"]), ", :".join(mynames))
                wheres.append(where)

            yield " AND ".join(wheres), args


    def delete_cascade(self, table, rows, rowids=()):
        """
        Deletes the table rows from the database, cascading delete to any
        related rows in foreign tables, and their related rows, etc.

        @return   [(table, [{identifying column: value}])] in order of deletion
        """
        if not self.is_open(): return
        result, queue = [], [(self.schema["table"][table]["name"], rows, rowids)]

        queries = [] # [(sql, params)]
        try:
            isolevel = self.connection.isolation_level
            self.connection.isolation_level = None # Disable autocommit
            with self.connection:
                cursor = self.connection.cursor()
                self.execute("BEGIN TRANSACTION", cursor=cursor)

                while queue:
                    table1, rows1, rowids1 = queue.pop(0)
                    if not util.lceq(table1, table):
                        lock = self.get_lock("table", table1)
                        if lock: raise Exception("%s, cannot delete." % lock)
                    col_data = self.schema["table"][table1]["columns"]
                    pks = [{"name": y} for x in self.get_keys(table, True)[0]
                           for y in x["name"]]
                    rowidname = self.get_rowid(table1)
                    use_rowids = rowidname and rowids1 and all(rowids1) and \
                                 not (len(pks) == 1 and all(pks[0]["name"] in r for r in rows1))
                    key_cols = [{"name": "_rowid_"}] if use_rowids else pks or col_data
                    key_data, myrows = [], []

                    for row, rowid in zip(rows1, rowids1):
                        data = {rowidname: rowid} if use_rowids else \
                               {c["name"]: row[c["name"]] for c in key_cols}
                        if not any(data in xx for t, xx in result if util.lceq(t, table1)):
                            key_data.append(data); myrows.append(row)
                    if not key_data: continue # while queue

                    logger.info("Deleting %s from table %s, %s.", util.plural("row", key_data),
                                util.unprint(grammar.quote(table1)), self.name)
                    for where, args in self.chunk_args(key_cols, key_data):
                        sql = "DELETE FROM %s WHERE %s" % (grammar.quote(table1), where)
                        self.execute(sql, args, cursor=cursor)
                        queries.append((sql, args))
                    result.append((table1, key_data))

                    for lk in self.get_keys(table1)[0]:
                        if "table" not in lk: continue # for lk
                        lkrows = [x for x in myrows
                                  if all(x[c] is not None for c in lk["name"])]
                        if not lkrows: continue # for lk
                        for table2, keys2 in lk["table"].items():
                            table2 = self.schema["table"][table2]["name"]

                            key_cols2 = [{"name": x} for x in keys2]
                            key_data2 = [{x: row[y] for x, y in zip(keys2, lk["name"])}
                                         for row in lkrows]
                            cols = "*"
                            rowidname2 = self.get_rowid(table2)
                            if rowidname2: cols = "%s AS %s, *" % ((rowidname2, ) * 2)
                            sqlbase = "SELECT %s FROM %s" % (cols, grammar.quote(table2))
                            rows2, rowids2 = [], []
                            for where2, args2 in self.chunk_args(key_cols2, key_data2):
                                sql2 = "%s WHERE %s" % (sqlbase, where2)
                                myrows2 = self.execute(sql2, args2, cursor=cursor).fetchall()
                                rowids2 += [x.pop(rowidname2) if rowidname2 else None
                                            for x in myrows2]
                                rows2.extend(myrows2)
                            if rows2: queue.append((table2, rows2, rowids2))

                self.execute("COMMIT", cursor=cursor)
                self.log_query("DELETE CASCADE", [x for x, _ in queries],
                               [x for _, x in queries])
                self.last_modified = datetime.datetime.now()
        finally:
            self.connection.isolation_level = isolevel

        return result


    def get_pragma_values(self, dump=False, stats=False):
        """
        Returns values for all defined and available PRAGMA settings, as
        {pragma_name: scalar value or [{row}, ]}.

        @param   dump   if True, returns only directives for db dump
        @param   stats  if True, returns only directives for statistics export
        """
        result = {}
        for name, opts in self.PRAGMA.items():
            if opts.get("read") == False: continue # for name, opts
            if dump  and not opts.get("dump") \
            or stats and not opts.get("dump") and not opts.get("stats"):
                continue # for name, opts

            rows = self.execute("PRAGMA %s" % name, log=False).fetchall()
            if not rows:
                if not callable(opts["type"]): continue # for name, opts
                value = opts["type"]()
            elif "table" == opts["type"]: value = [x.values()[0] for x in rows]
            else:
                value = rows[0].values()[0]
                if callable(opts["type"]): value = opts["type"](value)
            if not (dump or stats) or value != opts.get("default"):
                result[name] = value

        return result



def is_sqlite_file(filename, path=None, empty=False, ext=True):
    """
    Returns whether the file looks to be an SQLite database file.

    @param   path   path to prepend to filename, if any
    @param   empty  whether an empty file is considered valid
    @param   ext    whether to check file extension
    """
    SQLITE_HEADER = "SQLite format 3\00"
    result = not ext or os.path.splitext(filename)[1].lower() in conf.DBExtensions
    if result:
        try:
            result = empty
            fullpath = os.path.join(path, filename) if path else filename
            if os.path.getsize(fullpath):
                result = False
                with open(fullpath, "rb") as f:
                    result = (f.read(len(SQLITE_HEADER)) == SQLITE_HEADER)
        except Exception: pass
    return result


def detect_databases(progress=None):
    """
    Tries to detect SQLite database files on the current computer, looking
    under "Documents and Settings", and other potential locations.

    @param   progress  callback function returning whether task should continue
    @yield             each value is a list of detected database paths
    """

    # First, search system directories for database files.
    if "nt" == os.name:
        search_paths = [os.getenv("APPDATA")]
        c = os.getenv("SystemDrive") or "C:"
        for path in ["%s\\Users" % c, "%s\\Documents and Settings" % c]:
            if os.path.exists(path):
                search_paths.append(path)
                break # for path
    else:
        search_paths = [os.getenv("HOME"),
                        "/Users" if "mac" == os.name else "/home"]
    search_paths = map(util.to_unicode, search_paths)
    for search_path in filter(os.path.exists, search_paths):
        if progress and not progress(): return
        logger.info("Looking for SQLite databases under %s.", search_path)
        for root, _, files in os.walk(search_path):
            results = []
            for f in files:
                if progress and not progress(): break # for f
                if is_sqlite_file(f, root):
                    results.append(os.path.realpath(os.path.join(root, f)))
            if results: yield results
    if progress and not progress(): return

    # Then search current working directory for database files.
    search_path = util.to_unicode(os.getcwd())
    logger.info("Looking for SQLite databases under %s.", search_path)
    for root, _, files in os.walk(search_path):
        if progress and not progress(): return
        results = []
        for f in files:
            if progress and not progress(): break # for f
            if is_sqlite_file(f, root):
                results.append(os.path.realpath(os.path.join(root, f)))
        if results: yield results


def find_databases(folder):
    """Yields lists of all SQLite databases under the specified folder."""
    for root, _, files in os.walk(folder):
        yield []
        for f in files:
            p = os.path.join(root, f)
            yield [p] if is_sqlite_file(p) else []
