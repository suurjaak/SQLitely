# -*- coding: utf-8 -*-
"""
SQLite database access functionality.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    07.10.2019
------------------------------------------------------------------------------
"""
from collections import defaultdict, OrderedDict
import copy
import datetime
import logging
import os
import re
import sqlite3
import tempfile

from . lib import util
from . import conf
from . import grammar

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
        ?deprecated:  whether directive is deprecated,
        ?min:         minimum integer value,
        ?max:         maximum integer value,
        ?read:        false if setting is write-only,
        ?write:       false if setting is read-only,
        ?col:         result column to select if type "table"
    }.
    """
    PRAGMA = {
      "application_id": {
        "name": "application_id",
        "label": "Application ID",
        "type": int,
        "short": "Application-specified unique integer",
        "description": "Applications can set a unique integer so that utilities can determine the specific file type.",
      },
      "auto_vacuum": {
        "name": "auto_vacuum",
        "label": "Auto-vacuum",
        "type": int,
        "values": {0: "NONE", 1: "FULL", 2: "INCREMENTAL"},
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
        "deprecated": True,
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
        "write": False,
        "short": "Total number of pages",
        "description": "The total number of pages in the database file.",
      },
      "page_size": {
        "name": "page_size",
        "label": "Page size",
        "type": int,
        "values": {512: 512, 1024: 1024, 2048: 2048, 4096: 4096, 8192: 8192, 16384: 16384, 32768: 32768, 65536: 65536},
        "short": "Database page byte size",
        "description": "The page size of the database. Specifying a new size does not change the page size immediately. Instead, the new page size is remembered and is used to set the page size when the database is first created, if it does not already exist when the page_size pragma is issued, or at the next VACUUM command that is run on the same database connection while not in WAL mode.",
      },
      "query_only": {
        "name": "query_only",
        "label": "Query only",
        "type": bool,
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



    def __init__(self, filename=None, log_error=True):
        """
        Initializes a new database object from the file.

        @param   filename   if None, creates a temporary file database,
                            file deleted on close
        @param   log_error  if False, exceptions on opening the database
                            are not written to log (written by default)
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
        self.compile_options = []
        self.consumers = set() # Registered objects using this database
        # {category: {name.lower(): set()}}
        self.locks = defaultdict(lambda: defaultdict(set))
        # {"table|index|view|trigger":
        #   {name.lower():
        #     {name: str, sql: str, table: str, ?columns: [], ?count: int,
        #      ?meta: {full metadata}}}}
        self.schema = defaultdict(OrderedDict)
        self.connection = None
        self.open(log_error=log_error)


    def __str__(self):
        return self.name


    def open(self, log_error=True):
        """Opens the database."""
        try:
            self.connection = sqlite3.connect(self.filename,
                                              check_same_thread=False)
            self.connection.row_factory = self.row_factory
            self.connection.text_factory = str
            self.compile_options = [x["compile_option"] for x in 
                                    self.execute("PRAGMA compile_options", log=False).fetchall()]
            self.populate_schema()
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
        self.filename = self.name = filename
        self.open()


    def check_integrity(self):
        """Checks SQLite database integrity, returning a list of errors."""
        result = []
        rows = self.execute("PRAGMA integrity_check").fetchall()
        if len(rows) != 1 or "ok" != rows[0]["integrity_check"].lower():
            result = [r["integrity_check"] for r in rows]
        return result


    def recover_data(self, filename):
        """
        Recovers as much data from this database to a new database as possible.

        @return  a list of encountered errors, if any
        """
        result = []
        with open(filename, "w") as _: pass # Truncate file
        self.execute("ATTACH DATABASE ? AS new", (filename, ))
        fks = self.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"]
        if fks: self.execute("PRAGMA foreign_keys = FALSE")

        # Create structure for all tables
        for name, opts in sorted(self.schema["table"].items()):
            try:
                sql, err = grammar.transform(opts["sql"], renames={"schema": "new"})
                if sql: self.execute(sql)
                else: result.append(err)
            except Exception as e:
                result.append(util.format_exc(e))
                logger.exception("Error creating table %s in %s.",
                                 grammar.quote(name), filename)

        # Copy data from all tables
        for name, opts in sorted(self.schema["table"].items()):
            sql = "INSERT INTO new.%s SELECT * FROM main.%s" % ((grammar.quote(opts["name"]),) * 2)
            try:
                self.execute(sql)
            except Exception as e:
                result.append(util.format_exc(e))
                logger.exception("Error copying table %s from %s to %s.",
                                 grammar.quote(name), self.filename, filename)

        # Create indexes-triggers-views
        for category in "index", "trigger", "view":
            for name, opts in sorted(self.schema[category].items()):
                try:
                    sql, err = grammar.transform(opts["sql"], renames={"schema": "new"})
                    if sql: self.execute(sql)
                    else: result.append(err)
                except Exception as e:
                    result.append(util.format_exc(e))
                    logger.exception("Error creating %s %s for %s.",
                                     category, grammar.quote(name), filename)
        if fks: self.execute("PRAGMA foreign_keys = TRUE")
        self.execute("DETACH DATABASE new")
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


    def lock(self, category, name, key):
        """Locks a schema object for altering or deleting."""
        category, name = category.lower(), name.lower()
        self.locks[category][name].add(key)


    def unlock(self, category, name, key):
        """Unlocks a schema object for altering or deleting."""
        category, name = category.lower(), name.lower()
        self.locks[category][name].discard(key)
        if not self.locks[category][name]: self.locks[category].pop(name)
        if not self.locks[category]:       self.locks.pop(category)


    def is_locked(self, category=None, name=None):
        """
        Returns whether there are currently locks on specified schema object,
        or any category object, or any object.
        """
        category, name = (x.lower() if x else x for x in (category, name))
        return self.locks[category].get(name) if name and category in self.locks \
               else self.locks.get(category) if not name and category else self.locks


    def has_rowid(self, table):
        """Returns whether the table has ROWID, or is WITHOUT ROWID."""
        meta = self.schema["table"].get(table.lower(), {}).get("meta")
        return not meta.get("without") if meta else None


    def has_view_columns(self):
        """Returns whether SQLite supports view columns (from version 3.9)."""
        return sqlite3.sqlite_version_info >= (3, 9)


    def has_rename_column(self):
        """Returns whether SQLite supports renaming columns (from version 3.25)."""
        return sqlite3.sqlite_version_info >= (3, 25)


    def execute(self, sql, params=(), log=True):
        """Shorthand for self.connection.execute()."""
        result = None
        if self.connection:
            if log and conf.LogSQL:
                logger.info("SQL: %s%s", sql,
                            ("\nParameters: %s" % params) if params else "")
            result = self.connection.execute(sql, params)
        return result


    def execute_action(self, sql):
        """
        Executes the specified SQL INSERT/UPDATE/DELETE statement and returns
        the number of affected rows.
        """
        res = self.execute(sql)
        affected_rows = res.rowcount
        if self.connection.isolation_level is not None: self.connection.commit()
        return affected_rows


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

        Returns the names and rowcounts of all tables in the database,
        as [{"name": "tablename", "sql": CREATE SQL}, ].
        Uses already retrieved cached values if possible, unless refreshing.

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

            row["sql"] = row["sql0"] = row["sql"].strip()
            self.schema[row["type"]][row["name"].lower()] = row

        for mycategory, itemmap in self.schema.items():
            if category and category != mycategory: continue # for mycategory
            for myname, opts in itemmap.items():
                if category and name and myname != name: continue # for myname

                opts0 = schema0.get(mycategory, {}).get(myname, {})

                # Retrieve metainfo from PRAGMA
                if mycategory in ("table", "view") and opts0 and opts["sql0"] == opts0["sql0"]:
                    opts["columns"] = opts0.get("columns") or []
                elif mycategory in ("table", "view"):
                    sql = "PRAGMA table_info(%s)" % grammar.quote(opts["name"])
                    try:
                        rows = self.execute(sql, log=False).fetchall()
                    except Exception:
                        opts.update(columns=[])
                        logger.exception("Error fetching columns for %s %s.",
                                         mycategory, grammar.quote(opts["name"]))
                    else:
                        opts["columns"] = []
                        for row in rows:
                            col = {"name": row["name"], "type": row["type"].upper()}
                            if row["dflt_value"] is not None:
                                col["default"] = row["dflt_value"]
                            if row["notnull"]: col["notnull"] = {}
                            if row["pk"]:      col["pk"]      = {}
                            opts["columns"].append(col)

                # Parse metainfo from SQL
                meta, sql = None, None
                if opts0 and opts0.get("meta") and opts["sql0"] == opts0["sql0"]:
                    meta, sql = opts0["meta"], opts0["sql"]
                elif parse:
                    meta, _ = grammar.parse(opts["sql"])
                    if meta: sql, _ = grammar.generate(meta)
                if meta and sql:
                    opts.update(meta=meta, sql=sql)
                    if "table" == mycategory: opts["columns"] = meta["columns"]

                # Retrieve table row counts
                if "table" == mycategory and count:
                    opts.update(self.get_count(opts["name"]))
                elif "table" == mycategory and opts0 and "count" in opts0:
                    opts["count"] = opts0["count"]
                    if "is_count_estimated" in opts0:
                        opts["is_count_estimated"] = opts0["is_count_estimated"]


    def get_count(self, table):
        """
        Returns {"count": int, ?"is_count_estimated": bool}.
        Uses MAX(ROWID) to estimate row count and skips COUNT(*) if likely
        to take too long (file over half a gigabyte).
        """
        result, do_full = {"count": None}, False
        tpl = "SELECT %%s AS count FROM %s LIMIT 1" % grammar.quote(table)
        try:
            result = self.execute(tpl % "MAX(ROWID)", log=False).fetchone()
            result["is_count_estimated"] = True
            if self.filesize < conf.MaxDBSizeForFullCount \
            or result["count"] < conf.MaxTableRowIDForFullCount:
                do_full = True
        except Exception: do_full = self.filesize < conf.MaxDBSizeForFullCount

        try:
            if do_full:
                result = self.execute(tpl % "COUNT(*)", log=False).fetchone()
        except Exception:
            logger.exception("Error fetching COUNT for table %s.",
                             grammar.quote(table))
        return result


    def get_category(self, category, name=None, table=None):
        """
        Returns database objects in specified category.

        @param   category  "table"|"index"|"trigger"|"view"
        @param   name      returns only this object
        @param   table     specific table or view (or a list of tables/views)
                           the object references in any way
        @result            OrderedDict({name_lower: {opts}}),
                           or {opts} if name or None if no object by such name
        """
        category, name = (x.lower() if x else x for x in (category, name))
        table = [table] if isinstance(table, basestring) else table or []
        table = set(x.lower() for x in table)

        if name is not None:
            result = self.schema.get(category, {}).get(name)
            if table and "table" in result and result["table"].lower() not in table:
                result = None
            return copy.deepcopy(result)

        result = OrderedDict()
        for myname, opts in self.schema.get(category, {}).items():
            if table and not ("table" in opts.get("meta", {})
            and opts["meta"]["table"].lower() in table
            or table & set(opts["meta"].get("__tables__", []))):
                continue # for myname, opts
            result[myname] = opts
        return copy.deepcopy(result)


    def get_related(self, category, name):
        """
        Returns database objects related to specified object in any way,
        like triggers selecting from a view, as {category: [{item}, ]}.
        """
        result = {}
        SUBCATEGORIES = {"table":   ["index", "trigger", "view"],
                         "index":   ["table"],
                         "trigger": ["table", "view"],
                         "view":    ["table", "trigger", "view"]}
        category, name = category.lower(), name.lower()
        if category not in SUBCATEGORIES: return ""
        item = self.get_category(category, name)

        for subcategory in SUBCATEGORIES.get(category, []):
            itemmap = {}
            if category in ("table", "view"):
                itemmap.update(self.get_category(subcategory, table=name))
            items = filter(bool, (self.get_category(subcategory, x)
                                  for x in item["meta"]["__tables__"]))
            itemmap.update({x["name"].lower(): x for x in items})
            if itemmap:
                result[subcategory] = [v for k, v in sorted(itemmap.items())
                                       if category != subcategory or k != name]
        return result


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
        result = ""
        category, column = (x.lower() if x else x for x in (category, column))
        names = [name.lower()] if isinstance(name, basestring) \
                else [x.lower() for x in name] if isinstance(name, (list, tuple)) else []

        for mycategory in self.CATEGORIES:
            if category and category != mycategory \
            or not self.schema.get(mycategory): continue # for mycategory

            chunk = ""
            for myname, opts in self.schema[mycategory].items():
                if names and myname not in names:
                    continue # for myname, opts

                if names and column and "table" == mycategory:
                    col = next((c for c in opts["columns"]
                                if c["name"].lower() == column.lower()), None)
                    if not col: continue # for myname, opts
                    chunk, err = grammar.generate(dict(col, __type__="column"), indent=False)
                    if err: raise Exception(err)
                    break # for myname, opts

                sql = opts["sql"]
                kws = {x: transform[x] for x in ("flags", "renames")
                       if transform and x in transform}
                if not opts.get("meta") or kws or indent != "  ":
                    sql, err = grammar.transform(sql, indent=indent, **kws)
                    if err: raise Exception(err)
                chunk += sql + (";\n\n" if not names or len(names) < 2 else "")
            result += ("\n\n" if result else "") + chunk

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
        if table:    result = not table[:7].lower().startswith("sqlite_")
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
        for c in cols:
            if isinstance(c, dict): c = c["name"]
            name = base = re.sub(r"\W", "", c, flags=re.I)
            count = 1
            while name in result or existing and name in existing:
                name, count = "%s_%s" % (base, count), count + 1
            result[name] = data[c]
        return result


    def insert_row(self, table, row):
        """
        Inserts the new table row in the database.

        @return  ID of the inserted row
        """
        if not self.is_open():
            return
        table = table.lower()
        logger.info("Inserting 1 row into table %s, %s.",
                    grammar.quote(self.schema["table"][table]["name"]),
                    self.name)
        col_data = self.schema["table"][table]["columns"]
        fields = [col["name"] for col in col_data]
        row = self.blobs_to_binary(row, fields, col_data)
        args = self.make_args(fields, row)
        str_cols = ", ".join(map(grammar.quote, fields))
        str_vals = ":" + ", :".join(args)

        cursor = self.execute("INSERT INTO %s (%s) VALUES (%s)" %
                              (grammar.quote(table), str_cols, str_vals), args)
        if self.connection.isolation_level is not None: self.connection.commit()
        self.last_modified = datetime.datetime.now()
        return cursor.lastrowid


    def update_row(self, table, row, original_row, rowid=None):
        """
        Updates the table row in the database, identified by the given ROWID,
        or by the primary keys in its original values, or by all columns in its
        original values if table has no primary key.
        """
        if not self.is_open():
            return
        table, where = table.lower(), ""
        logger.info("Updating 1 row in table %s, %s.",
                    grammar.quote(self.schema["table"][table]["name"]), self.name)
        col_data = self.schema["table"][table]["columns"]

        changed_cols = [x for x in col_data
                            if row[x["name"]] != original_row[x["name"]]]
        where, args = "", self.make_args(changed_cols, row)
        setsql = ", ".join("%s = :%s" % (grammar.quote(changed_cols[i]["name"]), x)
                                         for i, x in enumerate(args))
        if rowid is not None:
            key_data = [{"name": "rowid"}]
            keyargs = self.make_args(key_data, {"rowid": rowid}, args)
        else:
            # If no primary key either, use all columns to identify row
            key_data = [c for c in col_data if "pk" in c] or col_data
            keyargs = self.make_args(key_data, original_row, args)
        for col, key in zip(key_data, keyargs):
            where += (" AND " if where else "") + \
                     "%s IS :%s" % (grammar.quote(col["name"]), key)
        args.update(keyargs)
        self.execute("UPDATE %s SET %s WHERE %s" %
                     (grammar.quote(table), setsql, where), args)
        if self.connection.isolation_level is not None: self.connection.commit()
        self.last_modified = datetime.datetime.now()


    def delete_row(self, table, row, rowid=None):
        """
        Deletes the table row from the database. Row is identified by its
        primary key, or by rowid if no primary key.

        @return   success as boolean
        """
        if not self.is_open():
            return
        table, where = table.lower(), ""
        logger.info("Deleting 1 row from table %s, %s.",
                    grammar.quote(self.schema["table"][table]["name"]),
                    self.name)
        col_data = self.schema["table"][table]["columns"]

        where, args = "", {}

        if rowid is not None:
            key_data = [{"name": "rowid"}]
            keyargs = self.make_args(key_data, {"rowid": rowid}, args)
        else:
            # If no primary key either, use all columns to identify row
            key_data = [c for c in col_data if "pk" in c] or col_data
            keyargs = self.make_args(key_data, row, args)
        for col, key in zip(key_data, keyargs):
            where += (" AND " if where else "") + "%s IS :%s" % (grammar.quote(col["name"]), key)
        args.update(keyargs)
        self.execute("DELETE FROM %s WHERE %s" % (grammar.quote(table), where), args)
        if self.connection.isolation_level is not None: self.connection.commit()
        self.last_modified = datetime.datetime.now()
        return True


    def get_pragma_values(self):
        """
        Returns values for all defined and available PRAGMA settings, as
        {pragma_name: scalar value or [{row}, ]}.
        """
        result = {}
        for name, opts in self.PRAGMA.items():
            if opts.get("read") == False: continue # for name, opts

            rows = self.execute("PRAGMA %s" % name, log=False).fetchall()
            if not rows:
                if callable(opts["type"]): result[name] = opts["type"]()
                continue # for name, opts

            if "table" == opts["type"]:
                result[name] = [x[opts["col"]] for x in rows]
            else:
                result[name] = rows[0].values()[0]
                if callable(opts["type"]):
                    result[name] = opts["type"](result[name])

        return result



def is_sqlite_file(filename, path=None):
    """Returns whether the file looks to be an SQLite database file."""
    result = os.path.splitext(filename)[1].lower() in conf.DBExtensions
    if result:
        try:
            fullpath = os.path.join(path, filename) if path else filename
            result = bool(os.path.getsize(fullpath))
            if result:
                result = False
                SQLITE_HEADER = "SQLite format 3\00"
                with open(fullpath, "rb") as f:
                    result = (f.read(len(SQLITE_HEADER)) == SQLITE_HEADER)
        except Exception: pass
    return result


def detect_databases():
    """
    Tries to detect SQLite database files on the current computer, looking
    under "Documents and Settings", and other potential locations.

    @yield   each value is a list of detected database paths
    """

    # First, search system directories for database files.
    if "nt" == os.name:
        search_paths = [os.getenv("APPDATA")]
        c = os.getenv("SystemDrive") or "C:"
        for path in ["%s\\Users" % c, "%s\\Documents and Settings" % c]:
            if os.path.exists(path):
                search_paths.append(path)
                break # break for path in [..]
    else:
        search_paths = [os.getenv("HOME"),
                        "/Users" if "mac" == os.name else "/home"]
    search_paths = map(util.to_unicode, search_paths)
    for search_path in filter(os.path.exists, search_paths):
        logger.info("Looking for SQLite databases under %s.", search_path)
        for root, _, files in os.walk(search_path):
            results = []
            for f in files:
                if is_sqlite_file(f, root):
                    results.append(os.path.realpath(os.path.join(root, f)))
            if results: yield results

    # Then search current working directory for database files.
    search_path = util.to_unicode(os.getcwd())
    logger.info("Looking for SQLite databases under %s.", search_path)
    for root, _, files in os.walk(search_path):
        results = []
        for f in (x for x in files if is_sqlite_file(x, root)):
            results.append(os.path.realpath(os.path.join(root, f)))
        if results: yield results


def find_databases(folder):
    """Yields lists of all SQLite databases under the specified folder."""
    for root, _, files in os.walk(folder):
        yield []
        for f in files:
            p = os.path.join(root, f)
            yield [p] if is_sqlite_file(p) else []
