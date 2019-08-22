# -*- coding: utf-8 -*-
"""
SQLite database access functionality.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    22.08.2019
------------------------------------------------------------------------------
"""
import datetime
import os
import sqlite3
import shutil
import time
import traceback

from lib import util

import conf
import main


class Database(object):
    """Access to an SQLite database file."""


    def __init__(self, filename, log_error=True):
        """
        Initializes a new database object from the file.

        @param   log_error  if False, exceptions on opening the database
                            are not written to log (written by default)
        """
        self.filename = filename
        self.basefilename = os.path.basename(self.filename)
        self.backup_created = False
        self.consumers = set() # Registered objects using this database
        self.tables = {} # {"name": {"Name":str, "rows": 0, "columns": []}, }
        self.tables_list = None # Ordered list of table items
        self.table_rows = {}    # {"tablename1": [..], }
        self.table_objects = {} # {"tablename1": {id1: {rowdata1}, }, }
        self.update_fileinfo()
        try:
            self.connection = sqlite3.connect(self.filename,
                                              check_same_thread=False)
            self.connection.row_factory = self.row_factory
            self.connection.text_factory = str
            rows = self.execute("SELECT name, sql FROM sqlite_master "
                                "WHERE type = 'table'").fetchall()
            for row in rows:
                self.tables[row["name"].lower()] = row
        except Exception:
            if log_error: main.log("Error opening database %s.\n\n%s",
                                   filename, traceback.format_exc())
            self.close()
            raise


    def __str__(self):
        if self and hasattr(self, "filename"):
            return self.filename


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
        # Create structure for all tables
        for t in (x for x in self.tables_list or [] if x.get("sql")):
            if t["name"].lower().startswith("sqlite_"): continue # Internal use
            sql  = t["sql"].replace("CREATE TABLE ", "CREATE TABLE new.")
            self.execute(sql)
        # Copy data from all tables
        for t in (x for x in self.tables_list or [] if x.get("sql")):
            if t["name"].lower().startswith("sqlite_"): continue # Internal use
            sql = "INSERT INTO new.%(name)s SELECT * FROM main.%(name)s" % t
            try:
                self.execute(sql)
            except Exception as e:
                result.append(repr(e))
                main.log("Error copying table %s from %s to %s.\n\n%s",
                         t["name"], self.filename, filename,
                         traceback.format_exc())
        # Create indexes
        indexes = []
        try:
            sql = "SELECT * FROM sqlite_master WHERE TYPE = ?"
            indexes = self.execute(sql, ("index", )).fetchall()
        except Exception as e:
            result.append(repr(e))
            main.log("Error getting indexes from %s.\n\n%s",
                     self.filename, traceback.format_exc())
        for i in (x for x in indexes if x.get("sql")):
            sql  = i["sql"].replace("CREATE INDEX ", "CREATE INDEX new.")
            try:
                self.execute(sql)
            except Exception as e:
                result.append(repr(e))
                main.log("Error creating index %s for %s.\n\n%s",
                         i["name"], filename, traceback.format_exc())
        self.execute("DETACH DATABASE new")
        return result


    def clear_cache(self):
        """Clears all the currently cached rows."""
        self.table_rows.clear()
        self.table_objects.clear()
        self.get_tables(True)


    def stamp_to_date(self, timestamp):
        """Converts the UNIX timestamp to datetime using localtime."""
        return datetime.datetime.fromtimestamp(timestamp)


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
        return len(self.consumers) > 0


    def close(self):
        """Closes the database and frees all allocated data."""
        if hasattr(self, "connection"):
            try:
                self.connection.close()
            except Exception:
                pass
            del self.connection
            self.connection = None
        for attr in ["tables", "tables_list", "table_rows", "table_objects"]:
            if hasattr(self, attr):
                delattr(self, attr)
                setattr(self, attr, None if ("tables_list" == attr) else {})


    def execute(self, sql, params=[], log=True):
        """Shorthand for self.connection.execute()."""
        result = None
        if self.connection:
            if log and conf.LogSQL:
                main.log("SQL: %s%s", sql,
                         ("\nParameters: %s" % params) if params else "")
            result = self.connection.execute(sql, params)
        return result


    def execute_action(self, sql):
        """
        Executes the specified SQL INSERT/UPDATE/DELETE statement and returns
        the number of affected rows.
        """
        self.ensure_backup()
        res = self.execute(sql)
        affected_rows = res.rowcount
        self.connection.commit()
        return affected_rows


    def is_open(self):
        """Returns whether the database is currently open."""
        return (self.connection is not None)


    def get_tables(self, refresh=False, this_table=None):
        """
        Returns the names and rowcounts of all tables in the database, as
        [{"name": "tablename", "rows": 0, "sql": CREATE SQL}, ].
        Uses already retrieved cached values if possible, unless refreshing.

        @param   refresh     if True, information including rowcounts is
                             refreshed
        @param   this_table  if set, only information for this table is
                             refreshed
        """
        if self.is_open() and (refresh or self.tables_list is None):
            sql = "SELECT name, sql FROM sqlite_master WHERE type = 'table' " \
                  "%sORDER BY name COLLATE NOCASE" % \
                  ("AND name = ? " if this_table else "")
            params = [this_table] if this_table else []
            rows = self.execute(sql, params).fetchall()
            tables = {}
            tables_list = []
            for row in rows:
                table = row
                try:
                    res = self.execute("SELECT COUNT(*) AS count FROM %s" %
                                       table["name"], log=False)
                    table["rows"] = res.fetchone()["count"]
                except sqlite3.DatabaseError:
                    table["rows"] = 0
                    main.log("Error getting %s row count for %s.\n\n%s",
                             table, self.filename, traceback.format_exc())
                # Here and elsewhere in this module - table names are turned to
                # lowercase when used as keys.
                tables[table["name"].lower()] = table
                tables_list.append(table)
            if this_table:
                self.tables.update(tables)
                for t in self.tables_list or []:
                    if t["name"] == this_table:
                        self.tables_list.remove(t)
                if self.tables_list is None:
                    self.tables_list = []
                self.tables_list += tables_list
                self.tables_list.sort(key=lambda x: x["name"])
            else:
                self.tables = tables
                self.tables_list = tables_list

        return self.tables_list


    def row_factory(self, cursor, row):
        """
        Creates dicts from resultset rows, with BLOB fields converted to
        strings.
        """
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


    def get_table_rows(self, table):
        """
        Returns all the rows of the specified table.
        Uses already retrieved cached values if possible.
        """
        rows = []
        table = table.lower()
        if table in self.tables:
            if table not in self.table_rows:
                col_data = self.get_table_columns(table)
                pks = [c["name"] for c in col_data if c["pk"]]
                pk = pks[0] if len(pks) == 1 else None
                rows = self.execute("SELECT * FROM %s" % table).fetchall()
                self.table_rows[table] = rows
                self.table_objects[table] = {}
                if pk:
                    for row in rows:
                        self.table_objects[table][row[pk]] = row
            else:
                rows = self.table_rows[table]
        return rows


    def get_table_columns(self, table):
        """
        Returns the columns of the specified table, as
        [{"name": "col1", "type": "INTEGER", }, ], or [] if not retrievable.
        """
        table = table.lower()
        table_columns = []
        if self.is_open() and self.tables_list is None:
            self.get_tables()
        if self.is_open() and table in self.tables:
            if "columns" in self.tables[table]:
                table_columns = self.tables[table]["columns"]
            else:
                table_columns = []
                try:
                    res = self.execute("PRAGMA table_info(%s)" % table, log=False)
                    for row in res.fetchall():
                        table_columns.append(row)
                except sqlite3.DatabaseError:
                    main.log("Error getting %s column data for %s.\n\n%s",
                             table, self.filename, traceback.format_exc())
                self.tables[table]["columns"] = table_columns
        return table_columns


    def update_fileinfo(self):
        """Updates database file size and modification information."""
        self.filesize = os.path.getsize(self.filename)
        self.last_modified = datetime.datetime.fromtimestamp(
                             os.path.getmtime(self.filename))


    def ensure_backup(self):
        """Creates a backup file if configured so, and not already created."""
        if conf.DBDoBackup:
            if (not self.backup_created
            or not os.path.exists("%s.bak" % self.filename)):
                shutil.copyfile(self.filename, "%s.bak" % self.filename)
                self.backup_created = True


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
            if "blob" == map_columns[list_columns[i]]["type"].lower() and val:
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


    def create_table(self, table):
        """Creates the specified table and updates our column data."""
        table = table.lower()
        self.execute(create_sql)
        self.connection.commit()
        row = self.execute("SELECT name, sql FROM sqlite_master "
                            "WHERE type = 'table' "
                            "AND LOWER(name) = ?", [table]).fetchone()
        self.tables[table] = row


    def update_row(self, table, row, original_row, rowid=None):
        """
        Updates the table row in the database, identified by its primary key
        in its original values, or the given rowid if table has no primary key.
        """
        if not self.is_open():
            return
        table, where = table.lower(), ""
        main.log("Updating 1 row in table %s, %s.",
                 self.tables[table]["name"], self.filename)
        self.ensure_backup()
        col_data = self.get_table_columns(table)
        values, where = row.copy(), ""
        setsql = ", ".join("%(name)s = :%(name)s" % x for x in col_data)
        if rowid is not None:
            pk_key = "PK%s" % int(time.time()) # Avoid existing field collision
            where, values[pk_key] = "ROWID = :%s" % pk_key, rowid
        else:
            for pk in [c["name"] for c in col_data if c["pk"]]:
                pk_key = "PK%s" % int(time.time())
                values[pk_key] = original_row[pk]
                where += (" AND " if where else "") + "%s IS :%s" % (pk, pk_key)
        if not where:
            return False # Sanity check: no primary key and no rowid
        self.execute("UPDATE %s SET %s WHERE %s" % (table, setsql, where),
                     values)
        self.connection.commit()
        self.last_modified = datetime.datetime.now()


    def insert_row(self, table, row):
        """
        Inserts the new table row in the database.

        @return  ID of the inserted row
        """
        if not self.is_open():
            return
        table = table.lower()
        main.log("Inserting 1 row into table %s, %s.",
                 self.tables[table]["name"], self.filename)
        self.ensure_backup()
        col_data = self.get_table_columns(table)
        fields = [col["name"] for col in col_data]
        str_cols = ", ".join(fields)
        str_vals = ":" + ", :".join(fields)
        row = self.blobs_to_binary(row, fields, col_data)
        cursor = self.execute("INSERT INTO %s (%s) VALUES (%s)" %
                              (table, str_cols, str_vals), row)
        self.connection.commit()
        self.last_modified = datetime.datetime.now()
        return cursor.lastrowid


    def delete_row(self, table, row, rowid=None):
        """
        Deletes the table row from the database. Row is identified by its
        primary key, or by rowid if no primary key.

        @return   success as boolean
        """
        if not self.is_open():
            return
        table, where = table.lower(), ""
        main.log("Deleting 1 row from table %s, %s.",
                 self.tables[table]["name"], self.filename)
        self.ensure_backup()
        col_data = self.get_table_columns(table)
        values, where = row.copy(), ""
        if rowid is not None:
            pk_key = "PK%s" % int(time.time()) # Avoid existing field collision
            where, values[pk_key] = "ROWID = :%s" % pk_key, rowid
        else:
            for pk in [c["name"] for c in col_data if c["pk"]]:
                pk_key = "PK%s" % int(time.time())
                values[pk_key] = original_row[pk]
                where += (" AND " if where else "") + "%s IS :%s" % (pk, pk_key)
        if not where:
            return False # Sanity check: no primary key and no rowid
        self.execute("DELETE FROM %s WHERE %s" % (table, where), values)
        self.connection.commit()
        self.last_modified = datetime.datetime.now()
        return True



def is_sqlite_file(filename, path=None):
    """Returns whether the file looks to be an SQLite database file."""
    result = ".db" == filename[-3:].lower()
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
    # First, search system directories for *.db files.
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
        main.log("Looking for SQLite databases under %s.", search_path)
        for root, dirs, files in os.walk(search_path):
            results = []
            for f in files:
                if is_sqlite_file(f, root):
                    results.append(os.path.realpath(os.path.join(root, f)))
            if results: yield results

    # Then search current working directory for *.db files.
    search_path = util.to_unicode(os.getcwd())
    main.log("Looking for SQLite databases under %s.", search_path)
    for root, dirs, files in os.walk(search_path):
        results = []
        for f in (x for x in files if is_sqlite_file(x, root)):
            results.append(os.path.realpath(os.path.join(root, f)))
        if results: yield results


def find_databases(folder):
    """Yields a list of all SQLite databases under the specified folder."""
    for root, dirs, files in os.walk(folder):
        for f in (x for x in files if is_sqlite_file(x, root)):
            yield os.path.join(root, f)
