# -*- coding: utf-8 -*-
"""
SQLitely main program entrance: launches GUI application,
handles logging and status calls.

------------------------------------------------------------------------------
This file is part of SQLitely - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    23.10.2023
------------------------------------------------------------------------------
"""
from __future__ import print_function
import argparse
import atexit
import codecs
import collections
import copy
import errno
import functools
import glob
import locale
import logging
import math
import os
try: import Queue as queue        # Py2
except ImportError: import queue  # Py3
import re
import sys
import tempfile
import threading
import time
import traceback
import warnings

import six
try: # For printing to a console from a packaged Windows binary
    import win32console
except ImportError:
    win32console = None
try:
    import wx
    is_gui_possible = True
except ImportError:
    is_gui_possible, wx = False, None

from . lib import util
from . import conf
from . import database
from . import grammar
if is_gui_possible:
    from . import guibase
    from . import gui
from . import importexport
from . import scheme
from . import searchparser
from . import workers


ARGUMENTS = {
    "description": "%s - SQLite database tool." % conf.Title,
    "arguments": [
        {"args": ["-v", "--version"], "action": "version",
         "version": "%s %s, %s." % (conf.Title, conf.Version, conf.VersionDate)},
        {"args": ["--verbose"], "action": "store_true",
         "help": "print detailed logging messages to stderr"},
        {"args": ["--config-file"], "dest": "config_file", "metavar": "FILE",
         "help": "path of program configuration file to use"}
    ],

    "commands": [
        {"name": "gui",
         "help": "launch SQLitely graphical program (default option)",
         "description": "Launch SQLitely graphical program (default option)",
         "arguments": [
             {"args": ["INFILE"], "metavar": "DATABASE", "nargs": "*",
              "help": "SQLite database(s) to open on startup, if any\n"
                      "(supports * wildcards)"},

             {"args": ["--config-file"], "dest": "config_file", "metavar": "FILE",
              "help": "path of program configuration file to use"},
        ]},
        {"name": "export",
         "help": "export SQLite database in various output formats",
         "description": "Export data or schema from an SQLite database,\n"
                        "printed to console or written to file.",
         "arguments": [
             {"args": ["INFILE"], "metavar": "DATABASE", "help": "SQLite database to export"},
             {"args": ["-f", "--format"], "dest": "format",
              "choices": sorted(["db"] + importexport.EXPORT_EXTS), "type": str.lower,
              "help": "export format:\n%s\n"
                      "(auto-detected from output filename if not specified)" % "\n".join(sorted(
                        "  %-5s  %s%s" % ("%s:" % k, importexport.EXT_NAMES[k],
                                          " (default)" if "sql" == k else "")
                        for k in sorted(["db"] + importexport.EXPORT_EXTS)
                      ))},
             {"args": ["-o", "--output"], "dest": "OUTFILE", "metavar": "FILE",
                       "nargs": "?", "const": "",
              "help": "write output to file instead of printing to console;\n"
                      "filename will be auto-generated if not given;\n"
                      "used as prefix if not --combine;\n"
                      "automatic for non-printable formats (%s)" %
                      ",".join(["db"] + sorted(set(importexport.EXPORT_EXTS) -
                                               set(importexport.PRINTABLE_EXTS)))},
             {"args": ["-p", "--path"], "metavar": "DIR",
              "help": "output file directory if not current directory"},
             {"args": ["--combine"], "action": "store_true",
              "help": "combine all outputs into a single file,\n"
                      "instead of each table or view to a separate file;\n"
                      "automatic if exporting to another database."},
             {"args": ["--overwrite"], "action": "store_true",
              "help": "overwrite output file if already exists\n"
                      "(by default appends unique counter to filename)"},
             {"args": ["--no-data"], "dest": "schema_only", "action": "store_true",
              "help": "export database structure only, without data"},
             {"args": ["--no-empty"], "action": "store_true",
              "help": "skip empty tables and views from output altogether,\n"
                      "ignored if exporting to another database,\n"
                      "(affected by offset and limit)"},
             {"args": ["--include-related"], "dest": "related", "action": "store_true",
              "help": "include related entities:\n"
                      "foreign tables and view dependencies if using filter,\n"
                      "and indexes and triggers if exporting to database or SQL"},
             {"args": ["--filter"], "nargs": "+",
              "help": "names of specific entities to export or skip\n"
                      "(supports * wildcards; initial ~ skips)"},
             {"args": ["--limit"], "type": int, "metavar": "NUM",
              "help": "maximum number of rows to export per table or view"},
             {"args": ["--offset"], "type": int, "metavar": "NUM",
              "help": "number of initial rows to skip from each table or view"},
             {"args": ["--reverse"], "action": "store_true",
              "help": "query table rows in reverse ROWID/PK order,\n"
                      "view rows in reverse row_number() order"},
             {"args": ["--max-count"], "dest": "maxcount", "type": int, "metavar": "NUM",
              "help": "maximum total number of rows to export over all tables and views"},
             {"args": ["--progress"], "action": "store_true",
              "help": "display progress bar"},

             {"args": ["--verbose"], "action": "store_true",
              "help": "print detailed logging messages to stderr"},
             {"args": ["--config-file"], "dest": "config_file", "metavar": "FILE",
              "help": "path of program configuration file to use"},
        ]},
        {"name": "import",
         "help": "import data from file to database ",
         "description": "Import data from spreadsheet/JSON/YAML files\n"
                        "to a new or existing SQLite database.",
         "arguments": [
             {"args": ["INFILE"],
              "help": "file to import from.\nSupported extensions: {%s}." %
                      ",".join(sorted(importexport.IMPORT_EXTS))},
             {"args": ["OUTFILE"], "metavar": "DB",
              "help": "SQLite database to import to, will be created if not present"},
             {"args": ["--filter"], "nargs": "+",
              "help": "names of specific Excel worksheets to import or skip\n"
                      "(supports * wildcards; initial ~ skips)"},
             {"args": ["--row-header"], "action": "store_true",
              "help": "use first row of input spreadsheet for column names"},
             {"args": ["--table-name"],
              "help": "name of table to import into, defaults to file base name\n"
                      "or worksheet name if Excel spreadsheet"},
             {"args": ["--create-always"], "action": "store_true",
              "help": "create new table even if a matching table already exists"},
             {"args": ["--add-pk"], "action": "store_true",
              "help": "add auto-increment primary key column to created tables"},
             {"args": ["--assume-yes"], "action": "store_true",
              "help": "skip confirmation prompt for starting import"},
             {"args": ["--limit"], "type": int, "metavar": "NUM",
              "help": "maximum number of rows to import, per table"},
             {"args": ["--offset"], "type": int, "metavar": "NUM",
              "help": "number of initial rows to skip from each table"},
             {"args": ["--max-count"], "dest": "maxcount", "type": int, "metavar": "NUM",
              "help": "maximum total number of rows to import over all tables"},
             {"args": ["--progress"], "action": "store_true",
              "help": "display progress bar"},

             {"args": ["--verbose"], "action": "store_true",
              "help": "print detailed logging messages to stderr"},
             {"args": ["--config-file"], "dest": "config_file", "metavar": "FILE",
              "help": "path of program configuration file to use"},
        ]},
        {"name": "parse",
         "help": "search in SQLite database schema",
         "description": "Parse and search database schema CREATE SQL.",
         "arguments": [
             {"args": ["INFILE"], "metavar": "DATABASE",
              "help": "SQLite database file to parse"},
             {"args": ["SEARCH"], "nargs": "?", "default": "", "type": str.strip,
              "help": "search text if any, with simple query syntax, for example:\n"
                      '"each word present" or "fk_* trigger:on_insert_*".\n'
                      "More at https://suurjaak.github.io/SQLitely/help.html."},
             {"args": ["--case"], "action": "store_true",
              "help": "case-sensitive search"},
             {"args": ["-o", "--output"], "dest": "OUTFILE", "metavar": "FILE",
                       "nargs": "?", "const": "",
              "help": "write output to SQL file instead of printing to console;\n"
                      "filename will be auto-generated if not given"},
             {"args": ["--overwrite"], "action": "store_true",
              "help": "overwrite output file if already exists\n"
                      "(by default appends unique counter to filename)"},
             {"args": ["--limit"], "type": int, "metavar": "NUM",
              "help": "maximum number of matches to find"},
             {"args": ["--offset"], "type": int, "metavar": "NUM",
              "help": "number of initial matches to skip"},
             {"args": ["--reverse"], "action": "store_true",
              "help": "find matches in reverse order"},

             {"args": ["--verbose"], "action": "store_true",
              "help": "print detailed logging messages to stderr"},
             {"args": ["--config-file"], "dest": "config_file", "metavar": "FILE",
              "help": "path of program configuration file to use"},
        ]},
        {"name": "search",
         "help": "search in SQLite database data",
         "description": "Search over all columns of all rows in an SQLite database,\n"
                        "matches printed to console or written to file.",
         "arguments": [
             {"args": ["INFILE"], "metavar": "DATABASE",
              "help": "SQLite database file to search"},
             {"args": ["SEARCH"], "type": str.strip,
              "help": "search text, with simple query syntax, for example:\n"
                      '"each word in some col" or "this OR that column:foo*".\n'
                      "More at https://suurjaak.github.io/SQLitely/help.html." },
             {"args": ["--case"], "action": "store_true",
              "help": "case-sensitive search"},
             {"args": ["-f", "--format"], "dest": "format",
              "choices": sorted(["db"] + importexport.EXPORT_EXTS), "type": str.lower,
              "help": "output format:\n%s\n"
                      "(auto-detected from output filename if not specified)" % "\n".join(sorted(
                        "  %-5s  %s%s" % ("%s:" % k, importexport.EXT_NAMES[k],
                                          " (default)" if "yaml" == k else "")
                        for k in sorted(["db"] + importexport.EXPORT_EXTS)
                      ))},
             {"args": ["-o", "--output"], "dest": "OUTFILE", "metavar": "FILE",
                       "nargs": "?", "const": "",
              "help": "write output to file instead of printing to console;\n"
                      "filename will be auto-generated if not given;\n"
                      "used as prefix if not --combine;\n"
                      "automatic for non-printable formats (%s)" %
                      ",".join(["db"] + sorted(set(importexport.EXPORT_EXTS) -
                                               set(importexport.PRINTABLE_EXTS)))},
             {"args": ["-p", "--path"], "metavar": "DIR",
              "help": "output file directory if not current directory"},
             {"args": ["--combine"], "action": "store_true",
              "help": "combine all outputs into a single file,\n"
                      "instead of each table or view to a separate file;\n"
                      "automatic if exporting to another database."},
             {"args": ["--overwrite"], "action": "store_true",
              "help": "overwrite output file if already exists\n"
                      "(by default appends unique counter to filename)"},
             {"args": ["--limit"], "type": int, "metavar": "NUM",
              "help": "maximum number of matches to find from each table or view"},
             {"args": ["--offset"], "type": int, "metavar": "NUM",
              "help": "number of initial matches to skip from each table or view"},
             {"args": ["--reverse"], "action": "store_true",
              "help": "query table matches in reverse ROWID/PK order,\n"
                      "view matches in reverse row_number() order"},
             {"args": ["--max-count"], "dest": "maxcount", "type": int, "metavar": "NUM",
              "help": "maximum total number of rows to export over all tables and views"},
             {"args": ["--progress"], "action": "store_true",
              "help": "display progress bar"},

             {"args": ["--verbose"], "action": "store_true",
              "help": "print detailed logging messages to stderr"},
             {"args": ["--config-file"], "dest": "config_file", "metavar": "FILE",
              "help": "path of program configuration file to use"},
        ]},
        {"name": "stats",
         "help": "print or save database statistics",
         "description": "Analyze an SQLite database and produce statistics as HTML, SQL or text.",
         "arguments": [
             {"args": ["INFILE"], "metavar": "DATABASE", "help": "SQLite database to analyze"},
             {"args": ["-o", "--output"], "dest": "OUTFILE", "metavar": "FILE",
                       "nargs": "?", "const": "",
              "help": "write output to file instead of printing to console,\n"
                      "filename will be auto-generated if not given;\n"
                      "auto-populated for non-printable formats (html)"},
             {"args": ["-f", "--format"], "dest": "format",
              "choices": ["html", "sql", "txt"], "type": str.lower,
              "help": "output format:\n%s\n"
                      "(auto-detected from output filename if not specified)" % "\n".join(sorted(
                        "  %-5s  %s%s" % ("%s:" % k, importexport.EXT_NAMES[k],
                                          " (default)" if "txt" == k else "")
                        for k in ["html", "sql", "txt"]
                      ))},
             {"args": ["--overwrite"], "action": "store_true",
              "help": "overwrite output file if already exists\n"
                      "(by default appends unique counter to filename)"},
             {"args": ["--start-file"], "action": "store_true",
              "help": "open output file with registered program"},
             {"args": ["--disk-usage"], "action": "store_true",
              "help": "count bytes of disk usage per table and index\n"
                      "(enabled by default in SQL output)"},
             {"args": ["--progress"], "action": "store_true",
              "help": "display progress bar"},

             {"args": ["--verbose"], "action": "store_true",
              "help": "print detailed logging messages to stderr"},
             {"args": ["--config-file"], "dest": "config_file", "metavar": "FILE",
              "help": "path of program configuration file to use"},
        ]},
    ],
}


logger = logging.getLogger(__package__)
window = None  # Application main window instance


class MainApp(wx.App if wx else object):

    def OnInit(self):
        self.SingleChecker = None
        return True

    def InitLocale(self):
        self.ResetLocale()
        if "win32" == sys.platform:  # Avoid dialog buttons in native language
            mylocale = wx.Locale(wx.LANGUAGE_ENGLISH_US, wx.LOCALE_LOAD_DEFAULT)
            mylocale.AddCatalog("wxstd")
            self._initial_locale = mylocale  # Override wx.App._initial_locale
            # Workaround for MSW giving locale as "en-US"; standard format is "en_US".
            # Py3 provides "en[-_]US" in wx.Locale names and accepts "en" in locale.setlocale();
            # Py2 provides "English_United States.1252" in wx.Locale.SysName and accepts only that.
            name = mylocale.SysName if sys.version_info < (3, ) else mylocale.Name.split("_", 1)[0]
            locale.setlocale(locale.LC_ALL, name)


class ConsoleWriter(object):
    """
    Wrapper for sys.stdout/stderr, attaches to the parent console or creates
    a new command console, usable from python.exe, pythonw.exe or
    compiled binary. Hooks application exit to wait for final user input.
    """
    handle = None # note: class variables
    is_loaded = False
    realwrite = None

    def __init__(self, stream):
        """
        @param   stream  sys.stdout or sys.stderr
        """
        self.encoding = getattr(stream, "encoding", locale.getpreferredencoding())
        self.stream = stream


    def flush(self):
        if not ConsoleWriter.handle and ConsoleWriter.is_loaded:
            self.stream.flush()
        elif hasattr(ConsoleWriter.handle, "flush"):
            ConsoleWriter.handle.flush()


    def write(self, text):
        """
        Prints text to console window. GUI application will need to attach to
        the calling console, or launch a new console if not available.
        """
        global window
        if not window and win32console:
            if not ConsoleWriter.is_loaded and not ConsoleWriter.handle:
                self.init_console()

            try: self.realwrite(text), self.flush()
            except Exception: self.stream.write(text)
        else:
            self.stream.write(text)


    def init_console(self):
        """Sets up connection to console."""
        try:
            win32console.AttachConsole(-1) # pythonw.exe from console
            atexit.register(lambda: ConsoleWriter.realwrite("\n"))
        except Exception:
            pass # Okay if fails: can be python.exe from console
        try:
            handle = win32console.GetStdHandle(
                                  win32console.STD_OUTPUT_HANDLE)
            handle.WriteConsole("\n")
            ConsoleWriter.handle = handle
            ConsoleWriter.realwrite = handle.WriteConsole
        except Exception: # Fails if GUI program: make new console
            try: win32console.FreeConsole()
            except Exception: pass
            try:
                win32console.AllocConsole()
                handle = open("CONOUT$", "w")
                argv = [util.longpath(sys.argv[0])] + sys.argv[1:]
                handle.write(" ".join(argv) + "\n\n")
                handle.flush()
                ConsoleWriter.handle = handle
                ConsoleWriter.realwrite = handle.write
                sys.stdin = open("CONIN$", "r")
                if getattr(sys, "frozen", False): atexit.register(self.on_exe_exit)
            except Exception:
                try: win32console.FreeConsole()
                except Exception: pass
                ConsoleWriter.realwrite = self.stream.write
        ConsoleWriter.is_loaded = True


    def on_exe_exit(self):
        """atexit handler for compiled binary, keeps window open for a minute."""
        q = queue.Queue()

        def waiter():
            six.moves.input()
            q.put(None)

        def ticker():
            countdown = 60
            txt = "\rClosing window in %s.. Press ENTER to exit."
            while countdown > 0 and q.empty():
                output(txt, countdown, end=" ")
                countdown -= 1
                time.sleep(1)
            q.put(None)

        self.write("\n\n")
        for f in waiter, ticker:
            t = threading.Thread(target=f)
            t.daemon = True
            t.start()
        q.get()



def except_hook(etype, evalue, etrace):
    """Handler for all unhandled exceptions."""
    mqueue = getattr(except_hook, "queue", [])
    setattr(except_hook, "queue", mqueue)

    text = "".join(traceback.format_exception(etype, evalue, etrace)).strip()
    log = "An unexpected error has occurred:\n\n%s"
    logger.error(log, text)
    if not conf.PopupUnexpectedErrors: return
    conf.UnexpectedErrorCount += 1
    msg = "An unexpected error has occurred:\n\n%s\n\n" \
          "See log for full details." % util.ellipsize(util.format_exc(evalue), limit=2000)
    mqueue.append(msg)

    def after():
        if not mqueue: return
        msg = mqueue[0]
        dlg = wx.RichMessageDialog(None, msg, conf.Title, wx.OK | wx.ICON_ERROR)
        if conf.UnexpectedErrorCount > 2:
            dlg.ShowCheckBox("&Do not pop up further errors")
        dlg.ShowModal()
        if dlg.IsCheckBoxChecked():
            conf.PopupUnexpectedErrors = False
            del mqueue[:]
            conf.save()
        if mqueue: mqueue.pop(0)
        if mqueue and conf.PopupUnexpectedErrors: wx.CallAfter(after)

    if len(mqueue) < 2: wx.CallAfter(after)


def install_thread_excepthook():
    """
    Workaround for sys.excepthook not catching threading exceptions.

    @from   https://bugs.python.org/issue1230540
    """
    init_old = threading.Thread.__init__
    def init(self, *args, **kwargs):
        init_old(self, *args, **kwargs)
        run_old = self.run
        def run_with_except_hook(*a, **b):
            try: run_old(*a, **b)
            except Exception: sys.excepthook(*sys.exc_info())
        self.run = run_with_except_hook
    threading.Thread.__init__ = init


def output(s="", *args, **kwargs):
    """
    Print wrapper, avoids "Broken pipe" errors if piping is interrupted.

    @param   args    format arguments for text
    @param   kwargs  additional arguments to print()
    """
    BREAK_EXS = (KeyboardInterrupt, )
    try: BREAK_EXS += (BrokenPipeError, )  # Py3
    except NameError: pass  # Py2

    if args: s %= args
    try: print(s, **kwargs)
    except UnicodeError:
        try:
            if isinstance(s, six.binary_type): print(s.decode(errors="replace"), **kwargs)
        except Exception: pass
    except BREAK_EXS:
        # Redirect remaining output to devnull to avoid another BrokenPipeError
        try: os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (Exception, KeyboardInterrupt): pass
        sys.exit()

    try:
        sys.stdout.flush() # Uncatchable error otherwise if interrupted
    except IOError as e:
        if e.errno in (errno.EINVAL, errno.EPIPE):
            sys.exit() # Stop work in progress if sys.stdout or pipe closed
        raise # Propagate any other errors


def make_progress(action, entities, args, results=None, **ns):
    """
    Returns progress-function for reporting output status.

    @param   action    name of action being progressed, like "export" or "search"
    @param   entities  {name: {name, type, count, ?total, ?table}}
    @param   args      argparse.Namespace
    @param   results   list to append progress values to, if any
    @param   ns        namespace defaults
    """
    NAME_MAX = 25
    infinitive = "%sing" % action

    ns = dict({"bar": None, "name": None, "afterword": None}, **ns)
    def progress(result=None, **kwargs):
        """Prints out progress texts, registers counts."""
        result = result or kwargs
        itemname = result.get("source" if "import" == action else "name")
        item = entities.get(itemname)
        itemindex = next((i for i, n in enumerate(entities) if util.lceq(n, itemname)), None)

        if itemname and itemname != ns["name"]:
            if ns["bar"]:
                ns["bar"].stop(), ns.update(bar=None)
                output()

        if "error" in result:
            if ns["bar"]:
                ns["bar"].stop(), ns.update(bar=None)
                output()
            output("\nError %s from %s: %s", infinitive, args.INFILE, result["error"])
        elif "count" in result and item:
            item["count"] = result["count"]

            if itemname != ns["name"]:
                if item["type"]:
                    label = util.unprint(itemname)
                    if args.progress: label = util.ellipsize(label, NAME_MAX)
                    text = " %s %s %s" % (infinitive.capitalize(), item["type"],
                                          grammar.quote(label, force=True))
                else: text = " %s %s" % (infinitive.capitalize(), itemname) # "Importing <JSON data>"
                if item.get("total", -1) != -1:
                    text += ", %s total" % util.count(item, "row", "total")
                itemcount = sum(x["type"] == item["type"] for x in entities.values())
                if itemcount > 1: text += " (%s of %s)" % (itemindex + 1, itemcount)
                ns.update(afterword=text, name=itemname)

            if args.progress:
                if not ns["bar"]:
                    pulse = ("import" == action and (item["total"] == -1 or item["total"] < 100)) or \
                            ("search" == action) or ("export" == action and "table" != item["type"])
                    ns["bar"] = util.ProgressBar(pulse=pulse, interval=0.05, value=item["count"],
                                                 afterword=ns["afterword"], echo=output)
                    if action in ("export", "import") and "view" != item["type"] \
                    and item.get("total", -1) != -1:
                        total = max(0, item["total"] - (args.offset or 0))
                        if max(-1, -1 if args.limit is None else args.limit) >= 0:
                            total = min(total, args.limit)
                        ns["bar"].max = total
                    ns["bar"].draw()
                    if 0 not in (item.get("total"), args.limit):
                        ns["bar"].start()
                else:
                    ns["bar"].update(item["count"], pulse=False)
            elif itemname != ns["name"]:
                logger.info(ns["afterword"].strip())
        elif "index" in result and "total" in result and args.progress: # E.g. db.populate_schema()
            if not ns["bar"]:
                ns["bar"] = util.ProgressBar(value=result["index"], max=result["total"],
                                             afterword=ns["afterword"], echo=output)
                ns["bar"].draw()
            else:
                ns["bar"].update(result["index"])
        if result.get("done"):
            if ns["bar"]:
                ns["bar"].update(value=ns["bar"].max, pulse=False)
                ns["bar"].stop(), ns.update(bar=None)
                output()
            ns["name"] = None
        if result.get("errorcount") and item:
            item["errorcount"] = result["errorcount"]

        if isinstance(results, list): results.append(result)
        return True

    return progress


def make_search_title(args):
    """
    Returns a list of texts with search parameters.

    @param   args
               SEARCH       search query
               case         case-sensitive search
               limit        maximum number of matches to find
               offset       number of initial matches
               reverse      find matches in reverse order
               ?maxcount    maximum total number of rows to export over all tables and views
    """
    result = []
    if args.SEARCH:
        result.append("Search query: %s" % args.SEARCH)
    limit  = (-1 if args.limit  is None or args.limit  < 0 else args.limit)
    offset = (-1 if args.offset is None or args.offset < 0 else args.offset)
    if limit >= 0 or offset > 0:
        result.append("Search limit: %s" % ", ".join(filter(bool, [
            ("" if limit  < 0 else "max %s" % util.plural("row", limit)),
            ("" if offset < 0 else "skipping initial %s" % offset)
        ])))
    if getattr(args, "maxcount", None) is not None and args.maxcount >= 0:
        result.append("Search total limit: %s" % args.maxcount)
    if args.reverse:
        result.append("Search order: reverse")
    return result


def prepare_args(action, args):
    """
    Populates format and outfile and limits and defaults of command-line arguments in-place.

    @param   action  name like "export" or "search"
    @param   args    argparse.Namespace
    """
    DEFAULT_FORMATS   = {"export": "sql", "search": "yaml", "stats": "txt"}
    ACTION_FORMATS    = {"stats": ["html", "sql", "txt"]}
    OUTFILE_TEMPLATES = {"stats": "%(db)s statistics"}
    FORMATS = {x: [x] for x in importexport.EXPORT_EXTS}
    FORMATS["db"] = [x.lstrip(".") for x in conf.DBExtensions]
    FORMATS["yaml"] = list(importexport.YAML_EXTS)
    if action in ACTION_FORMATS:
        FORMATS = {k: v for k, v in FORMATS.items() if k in ACTION_FORMATS[action]}

    if "import" != action and args.OUTFILE and not args.format: # Detect format from output filename
        fmt = os.path.splitext(args.OUTFILE)[-1].lower().lstrip(".")
        if fmt in FORMATS:
            args.format = fmt
    if hasattr(args, "format"):
        args.format = args.format or DEFAULT_FORMATS[action]
    if "stats" == action and "sql" == args.format:
        args.disk_usage = True
    if hasattr(args, "combine"):
        args.combine = args.combine or ("db" == args.format)
    if hasattr(args, "maxcount"):
        args.maxcount = None if args.maxcount is None or args.maxcount <  0 else args.maxcount
    if hasattr(args, "limit"):
        args.limit    =   -1 if args.limit    is None or args.limit    <  0 else args.limit
    if hasattr(args, "offset"):
        args.offset   =    0 if args.offset   is None or args.offset   <= 0 else args.offset

    outfile_transient = args.OUTFILE is None and args.format in importexport.PRINTABLE_EXTS
    outfile_required  = "stats" == action or (getattr(args, "combine", False) and args.OUTFILE == "")
    if not args.OUTFILE and (outfile_required or args.format not in importexport.PRINTABLE_EXTS):
        dct = {"action": action.capitalize(), "db": os.path.basename(args.INFILE)}
        base = OUTFILE_TEMPLATES.get(action, "%(action)s from %(db)s") % dct
        args.OUTFILE = "%s.%s" % (base, args.format)
        if outfile_transient:
            with tempfile.NamedTemporaryFile(prefix=base + ".", suffix="." + args.format) as f:
                args.OUTFILE = f.name
    if hasattr(args, "path") and args.path and args.OUTFILE and not outfile_transient:
        args.OUTFILE = os.path.join(args.path, args.OUTFILE)

    if args.OUTFILE and getattr(args, "combine", True) \
    and not getattr(args, "overwrite", True) and not outfile_transient:
        args.OUTFILE = util.unique_path(args.OUTFILE)


def validate_args(action, args):
    """
    Populates format and outfile and limits and defaults of command-line arguments in-place.

    Prints error and exits if any arguments are invalid.

    @param   action  name like "export" or "search"
    @param   args    argparse.Namespace
    """
    prepare_args(action, args)
    if 0 in (args.limit, args.maxcount):
        sys.exit("Nothing to export with %s." %
                 ("limit %r" % args.limit if not args.limit else "max count %r" % args.maxcount))
    if "export" == action and args.schema_only and args.format in ("json", "yaml"):
        sys.exit("Nothing to export from %s without data as %s." % (dbname, args.format.upper()))


def do_output(action, args, func, entities, files):
    """
    Invokes output function, handles errors, prints final information.

    @param   action    name like "export" or "search"
    @param   args      argparse.Namespace
    @param   func      output function to invoke
    @param   entities  {name: {item}} to process
    @param   files     {name: filename} populated by func
    """
    infinitive, past = "%sing" % action, "%sed" % action
    adverb = "in" if "search" == action else "from"

    try:
        if not func(): return
    except Exception:
        _, e, tb = sys.exc_info()
        logger.exception("Error %s %s %s.", infinitive, adverb, args.INFILE)
        if args.OUTFILE and args.combine and "db" != args.format:
            util.try_ignore(os.unlink, args.OUTFILE)
        six.reraise(type(e), e, tb)
    else:
        count_total = {"count": sum(x.get("count", 0) for x in entities.values())}
        fmt_bytes = lambda f, s=None: util.format_bytes((s or os.path.getsize)(f))
        errput = lambda s="": output(s, file=sys.stderr)

        errput()
        errput("%s %s: %s (%s)" % (past.capitalize(), adverb, os.path.abspath(args.INFILE),
                                   fmt_bytes(args.INFILE, database.get_size)))
        if args.OUTFILE and args.combine:
            errput("Wrote %s to %s (%s):" % (util.count(count_total, "row"),
                                             args.OUTFILE, fmt_bytes(args.OUTFILE)))
        elif args.OUTFILE:
            errput("Wrote %s to %s (%s):" % (util.count(count_total, "row"),
                util.plural("file", files),
                util.format_bytes(sum(os.path.getsize(f) for f in files.values()))))
        else:
            errput("Printed %s to console:" % util.count(count_total, "row"))
        for item in (x for x in (reversed if args.reverse else list)(entities.values())
                     if x["type"] in database.Database.DATA_CATEGORIES and x["count"]):
            countstr = "" if item.get("count") is None else ", %s" % util.count(item, "row")
            if item["name"] in files:
                filename = files[item["name"]]
                errput("  %s%s (%s)" % (filename, countstr, fmt_bytes(filename)))
            else:
                errput("  %s%s" % (item["title"], countstr))


def run_export(dbname, args):
    """
    Exports database contents in various formats to file, or prints to console.

    @param   dbname         path of database to export
    @param   args
               OUTFILE      path of output file, if any,
                            auto-generated if not given
               format       export format
               path         output directory if not current
               combine      combine all outputs into a single file
               overwrite    overwrite existing file instead of creating unique name
               schema_only  export database schema only, no data rows
               filter       names of specific tables or views to export or skip
                            (supports * wildcards; initial dash - skips)
               limit        maximum number of rows to export per table or view
               offset       number of initialrows to skip from each table or view
               reverse      query rows in reverse order
               maxcount     maximum total number of rows to export over all tables and views
               no_empty     skip empty tables and views from output altogether
                            ignored if exporting to db (affected by offset and limit)
               related      include related entities, like data dependencies or index/trigger items
               progress     show progress bar
    """
    validate_args("export", args)
    entity_rgx = util.filters_to_regex(args.filter) if args.filter else None

    db = database.Database(dbname)
    if args.related or args.format in ("db", "sql"):
        progress = None
        if args.progress:
            progress, _ = make_progress("export", {}, args, afterword=" Parsing schema"), output()
        db.populate_schema(parse=True, generate=False, progress=progress)

    entities = util.CaselessDict((kv for c in db.DATA_CATEGORIES for kv in db.schema[c].items()))
    renames = collections.defaultdict(util.CaselessDict) # {category: {name1: name2}}
    if args.filter:
        entities.clear()
        # First pass: select all data entities matching by name
        for category in db.CATEGORIES if args.format in ("db", "sql") else db.DATA_CATEGORIES:
            for name, item in db.schema.get(category, {}).items():
                if entity_rgx.match(name):
                    entities[name] = item
    if args.filter and args.format in ("db", "sql"):
        # Second pass: select dependent tables and views for views, recursively
        for item in [x for x in entities.values() if "view" == x["type"]]:
            for category, items in db.get_full_related(item["type"], item["name"])[0].items():
                if category in db.DATA_CATEGORIES: entities.update(items)
    if args.filter and args.related:
        # Third pass: select foreign tables for tables, recursively
        for item in [x for x in entities.values() if "table" == x["type"]]:
            for category, items in db.get_full_related(item["type"], item["name"])[0].items():
                if "table" == category: entities.update(items)
    if args.related and args.format in ("db", "sql"):
        # Fourth pass: select owned indexes and triggers
        for item in list(entities.values()):
            for items in db.get_related(item["type"], item["name"], own=True, clone=False).values():
                entities.update(items)
    if args.filter and args.related and args.format in ("db", "sql"):
        # Fifth pass: select referred tables/views for triggers, recursively
        for item in [x for x in entities.values() if "trigger" == x["type"]]:
            for category, items in db.get_full_related(item["type"], item["name"])[0].items():
                if category in db.DATA_CATEGORIES: entities.update(items)
    entities = util.CaselessDict([(n, copy.deepcopy(d)) for c in db.CATEGORIES
                                  for n, d in entities.items() if c == d["type"]], insertorder=True)

    if not entities:
        extra = "" if not args.filter else " using filter: %s" % " ".join(args.filter)
        sys.exit("Nothing to export as %s from %s%s." % (args.format.upper(), dbname, extra))

    if "db" == args.format and args.overwrite:
        os.path.exists(args.OUTFILE) and os.unlink(args.OUTFILE)

    if "db" == args.format and os.path.exists(args.OUTFILE):
        db2 = database.Database(args.OUTFILE)
        allitems2 = util.CaselessDict((n, True) for nn in db2.schema.values() for n in nn)
        db2.close()
        for name, item in entities.items():
            name2 = util.make_unique(name, allitems2) if name in allitems2 else name
            if name != name2: renames[item["type"]][name] = name2
            allitems2[name2] = True

    for item in (x for x in entities.values() if x["type"] in db.DATA_CATEGORIES):
        item["title"] = "%s %s" % (item["type"], grammar.quote(item["name"], force=True))
        item["count"] = 0
        if args.progress and "table" == item["type"]:
            item.update(db.get_count(item["name"], key="total"))

    schema = collections.OrderedDict() # {category: [name, ]}
    schema.update((c, [n for n, x in entities.items() if c == x["type"]]) for c in db.CATEGORIES
                  if any(c == x["type"] for x in entities.values()))
    files = collections.OrderedDict()  # {entity name: output filename}
    maxrow, fromrow = args.limit, args.offset
    limit = (maxrow, fromrow) if (fromrow > 0) else (maxrow, ) if (maxrow >= 0) else ()
    progress = make_progress("export", entities, args)
    func, posargs, kwargs = None, [], dict(progress=progress)

    def make_iterables():
        """Yields pairs of ({item}, callable returning iterable cursor)."""
        items = [x for c in db.DATA_CATEGORIES for x in entities.values() if c == x["type"]]
        maxcount = 0 if args.schema_only else args.maxcount
        for item in (reversed if args.reverse else list)(items):
            order_sql = db.get_order_sql(item["name"], reverse=True) if args.reverse else ""
            limit_sql = db.get_limit_sql(*limit, maxcount=maxcount, totals=entities.values())
            sql = "SELECT * FROM %s%s%s" % (grammar.quote(item["name"]), order_sql, limit_sql)

            make_iterable = functools.partial(db.select, sql,
                                              error="Error querying %s." % item["title"])
            yield item, make_iterable

    if "db" == args.format:
        func, posargs = importexport.export_to_db, [db, args.OUTFILE, schema]
        kwargs.update(data=not args.schema_only, limit=limit, maxcount=args.maxcount,
                      related=args.related, renames=renames, reverse=args.reverse)

    elif args.OUTFILE and args.combine and "sql" == args.format:
        func, posargs = importexport.export_dump, (args.OUTFILE, db, schema)
        kwargs.update(data=not args.schema_only, pragma=not args.filter, limit=limit,
                      maxcount=args.maxcount, empty=not args.no_empty, reverse=args.reverse)

    elif args.OUTFILE and args.combine:
        title = "Export from %s" % os.path.basename(dbname)
        func, posargs = importexport.export_data_multiple, [args.OUTFILE, args.format, title, db]
        kwargs.update(empty=not args.no_empty, maxcount=args.maxcount, make_iterables=make_iterables)

    elif args.OUTFILE:
        def do_export():
            result, basenames = True, []
            path, prefix = os.path.split(os.path.splitext(args.OUTFILE)[0]) if args.OUTFILE \
                           else (args.path or "",  "")
            for item, make_iterable in make_iterables():
                title = util.cap(item["title"])
                basename = util.make_unique(util.safe_filename(title), basenames, suffix=" (%s)")
                basenames.append(basename)
                filename = "%s.%s" % (" ".join(filter(bool, (prefix, basename))), args.format)
                filename = os.path.join(path, filename)
                if not args.overwrite: filename = util.unique_path(filename)

                result = importexport.export_data(make_iterable, filename, args.format, title, db,
                    item["columns"], category=item["type"], name=item["name"], progress=progress
                )
                if not result or args.no_empty and not item["count"]:
                    util.try_ignore(os.unlink, filename)
                else: files[item["name"]] = filename
                if not result: break # for item
            return result

        func = do_export
        kwargs.clear()

    else: # Print to console
        func = importexport.export_to_console
        posargs = [make_iterables, args.format]
        kwargs.update(output=output, multiple=True, progress=progress)

    do_output("export", args, functools.partial(func, *posargs, **kwargs), entities, files)


def run_search(dbname, args):
    """
    Exports database contents in various formats to file, or prints to console.

    @param   dbname         path of database to export
    @param   args
               SEARCH       search query
               OUTFILE      path of output file, if any
               format       export format
               path         output directory if not current
               combine      combine all outputs into a single file
               overwrite    overwrite existing output file instead of creating unique name
               case         case-sensitive search
               limit        maximum number of matches to find per table or view
               offset       number of initial matches to skip from each table or view
               reverse      query rows in reverse order
               maxcount     maximum total number of rows to export over all tables and views
    """
    validate_args("search", args)

    db = database.Database(dbname)
    queryparser = searchparser.SearchQueryParser()

    entities = util.CaselessDict(insertorder=True)
    _, _, _, kws = queryparser.Parse(args.SEARCH, args.case)
    for category, item in ((c, x) for c in db.DATA_CATEGORIES for x in db.schema[c].values()):
        if (category in kws
        and not searchparser.match_words(item["name"], kws[category], any, args.case)
        or "-" + category in kws
        and searchparser.match_words(item["name"], kws["-" + category], any, args.case)):
            continue # for item
        title = "%s %s" % (item["type"], grammar.quote(item["name"], force=True))
        entities[item["name"]] = dict(item, **{"count": 0, "title": title})
    maxrow, fromrow = max(-1, -1 if args.limit is None else args.limit), max(-1, args.offset or 0)
    limit = (maxrow, fromrow) if (fromrow > 0) else (maxrow, ) if (maxrow >= 0) else ()

    if not entities:
        sys.exit("Nothing to search in %s with %r." % (dbname, args.SEARCH))


    def make_iterables():
        """Yields pairs of ({item}, callable returning iterable cursor)."""
        for item in (reversed if args.reverse else list)(entities.values()):
            sql, params, _, _ = queryparser.Parse(args.SEARCH, args.case, item)
            if not sql: continue  # for item

            order_sql = db.get_order_sql(item["name"], reverse=True) if args.reverse else ""
            limit_sql = db.get_limit_sql(*limit, maxcount=args.maxcount, totals=entities.values())
            sql += order_sql + limit_sql
            item.update(query=sql, params=params)
            yield item, functools.partial(db.select, sql, params,
                                          error="Error querying %s." % item["title"])

    if args.overwrite and args.OUTFILE:
        os.path.exists(args.OUTFILE) and os.unlink(args.OUTFILE)

    files = collections.OrderedDict()  # {entity name: output filename}
    progress = make_progress("search", entities, args)
    func, posargs, kwargs = None, [], {}

    if "db" == args.format:
        def output_to_db():
            result = False
            for item, _ in make_iterables():
                if args.maxcount is not None \
                and sum(x.get("count", 0) for x in entities.values()) >= args.maxcount:
                    break # for item

                sql, params = item["query"], item["params"]
                create_sql = item["sql"] if "table" == item["type"] else None
                res = importexport.export_query_to_db(db, args.OUTFILE, item["name"],
                    sql, params, create_sql=create_sql, empty=False, progress=progress
                )
                result = res or result
                if res is None: break # for item
            return result

        func = output_to_db

    elif args.OUTFILE and args.combine:
        func = importexport.export_data_multiple
        posargs.extend((args.OUTFILE, args.format, make_search_title(args), db))
        kwargs.update(empty=False, make_iterables=make_iterables, progress=progress)

    elif args.OUTFILE:
        def do_export():
            result, basenames = True, []
            path, prefix = os.path.split(os.path.splitext(args.OUTFILE)[0]) if args.OUTFILE \
                           else (args.path or "",  "")
            for item, make_iterable in make_iterables():
                category, name = item["type"], item["name"]
                title = util.cap(item["title"])
                basename = util.make_unique(util.safe_filename(title), basenames, suffix=" (%s)")
                basenames.append(basename)
                filename = "%s.%s" % (" ".join(filter(bool, (prefix, basename))), args.format)
                filename = os.path.join(path, filename)
                if not args.overwrite: filename = util.unique_path(filename)

                title = [title] + make_search_title(args)
                result = importexport.export_data(make_iterable, filename, args.format, title, db,
                    item["columns"], category=category, name=name, progress=progress
                )
                if result and item["count"]: files[name] = filename
                else: util.try_ignore(os.unlink, filename)
                if not result: break # for item
            return result

        func = do_export

    else: # Print to console
        func = importexport.export_to_console
        posargs = [make_iterables, args.format, make_search_title(args)]
        kwargs.update(output=output, multiple=True, progress=progress)

    do_output("search", args, functools.partial(func, *posargs, **kwargs), entities, files)


def run_parse(dbname, args):
    """
    Searches database schema, and writes matching entities to file or prints to console.

    @param   dbname         path of database to export
    @param   args
               SEARCH       search query
               OUTFILE      path of output file, if any
               case         case-sensitive search
               limit        maximum number of matches to find
               offset       number of initial matches
               reverse      find matches in reverse order
               overwrite    overwrite existing output file instead of creating unique name
    """
    file_existed = args.OUTFILE and not args.overwrite and os.path.isfile(args.OUTFILE)
    if args.OUTFILE and not args.overwrite:
        args.OUTFILE = util.unique_path(args.OUTFILE)

    _, _, words, kws = searchparser.SearchQueryParser().Parse(args.SEARCH, args.case)

    counts = collections.defaultdict(int) # {category: count}
    matches = [] # [SQL, ]
    try:
        i = 0
        imin = 0 if args.offset is None else max(0, args.offset)
        imax = imin + (sys.maxsize if args.limit is None or args.limit < 0 else args.limit)
        db = database.Database(dbname)
        for category in (reversed if args.reverse else list)(db.CATEGORIES):
            othercats = set(db.CATEGORIES) - set([category])
            if category not in kws and othercats & set(kws):
                continue # for category

            for item in (reversed if args.reverse else list)(db.get_category(category).values()):
                if (category in kws
                and not searchparser.match_words(item["name"], kws[category], any, args.case)
                or "-" + category in kws
                and searchparser.match_words(item["name"], kws["-" + category], any, args.case)):
                    continue # for item

                if not searchparser.match_words(item["sql"], words, all, args.case) \
                and (words or category not in kws):
                    continue # for item

                if imin <= i < imax:
                    counts[category] += 1
                    matches.append(item["sql"])
                i += 1

        headers = make_search_title(args)
        if args.OUTFILE:
            importexport.export_sql(args.OUTFILE, db, "\n\n".join(matches), headers)
    except Exception:
        _, e, tb = sys.exc_info()
        if args.OUTFILE and not file_existed:
            util.try_ignore(os.unlink, args.OUTFILE)
        output("Error searching %s.", dbname, file=sys.stderr)
        six.reraise(type(e), e, tb)
    else:
        errput = lambda s="": output(s, file=sys.stderr)
        countstr = ", ".join(util.plural(c, counts[c]) for c in db.CATEGORIES if c in counts)
        if not counts:
            errput()
            errput("Found nothing in %s%s." %
                   (dbname, " matching %r" % args.SEARCH if db.schema and args.SEARCH else ""))
        elif not args.OUTFILE:
            output("\n-- Source: %s", dbname)
            for l in headers:
                output("-- %s", l)
            if headers: output()
            output("\n\n".join(matches))
            if args.SEARCH:
                output("\n-- Found %s: %s.", util.plural("entity", matches), countstr)
        else:
            fmt_bytes = lambda f, s=None: util.format_bytes((s or os.path.getsize)(f))

            errput()
            errput("Parse from: %s (%s)" % (os.path.abspath(dbname),
                                             fmt_bytes(dbname, database.get_size)))
            errput("Found %s: %s." % (util.plural("entity", len(matches)), countstr))
            errput("Wrote %s (%s)." % (args.OUTFILE, fmt_bytes(args.OUTFILE)))


def run_stats(dbname, args):
    """
    Writes database statistics to file or prints to console.

    @param   dbname         path of database to analyze
    @param   args
               OUTFILE      path of output file, if any
               format       export format
               overwrite    overwrite existing output file instead of creating unique name
               start_file   open output file with registered program
               disk_usage   count bytes of disk usage per table and index
               progress     show progress bar
    """
    outfile0 = args.OUTFILE
    file_existed = args.OUTFILE and not args.overwrite and os.path.isfile(args.OUTFILE)
    validate_args("stats", args)

    db = database.Database(os.path.abspath(dbname))
    stats = {}
    if args.disk_usage:
        resultqueue = queue.Queue()
        worker = workers.AnalyzerThread(resultqueue.put)

    output()
    progressargs = dict(pulse=True, interval=0.05) if args.progress else dict(static=True)
    bar = util.ProgressBar(**progressargs)
    try:
        args.progress and bar.start()
        if "sql" != args.format:
            bar.update(afterword=" Parsing schema")
            db.populate_schema(parse=True)
            bar.update(afterword=" Counting rows")
            db.populate_schema(count=True)
        if args.disk_usage:
            bar.update(afterword=" Counting disk usage")
            worker.work(dbname)
            stats = next((x["data"] for x in [resultqueue.get()] if "data" in x), None)
            if stats: db.set_sizes(stats)
        diagrams = None
        if "html" == args.format:
            bar.update(afterword=" Generating diagram")
            a = MainApp() if is_gui_possible else None
            layout = scheme.SchemaPlacement(db)
            layout.SetFonts("Verdana",
                            ("Open Sans", conf.FontDiagramSize,
                             conf.FontDiagramFile, conf.FontDiagramBoldFile))
            layout.Populate({"stats": True})
            layout.Redraw(scheme.Rect(0, 0, *conf.Defaults["WindowSize"]), layout.LAYOUT_GRID)
            bmp = layout.MakeBitmap() 
            svg = layout.MakeTemplate("SVG", embed=True)
            diagrams = {"bmp": bmp, "svg": svg}
        bar.update(afterword=" Writing output")
        importexport.export_stats(args.OUTFILE, args.format, db, stats, diagrams)
        bar.stop()
        output()
    except Exception:
        _, e, tb = sys.exc_info()
        bar.stop()
        output()
        if args.OUTFILE and not file_existed:
            util.try_ignore(os.unlink, args.OUTFILE)
        output("Error analyzing %s.", dbname, file=sys.stderr)
        six.reraise(type(e), e, tb)
    else:
        fmt_bytes = lambda f, s=None: util.format_bytes((s or os.path.getsize)(f))
        errput = lambda s="": output(s, file=sys.stderr)

        if outfile0 is None and args.format in importexport.PRINTABLE_EXTS:
            output()
            try:
                with open(args.OUTFILE) as f:
                    output(f.read())
            finally:
                util.try_ignore(os.unlink, args.OUTFILE)
        else:
            errput()
            errput("Source: %s (%s)" % (os.path.abspath(dbname),
                                        fmt_bytes(dbname, database.get_size)))
            errput("Wrote statistics to: %s (%s)" % (os.path.abspath(args.OUTFILE),
                                                     fmt_bytes(args.OUTFILE)))
            if args.start_file: util.start_file(args.OUTFILE)


def run_import(infile, args):
    """
    Imports data from file to database, prints results.

    @param   infile           path of data file to import
    @param   args
               OUTFILE        path of database to create or update
               filter         names of worksheets to import, supports * wildcards, leading - skips
               table_name     table to import into, defaults to sheet or file name
               create_always  whether to create new table even if matching table exists
               row_header     whether to use first row of input spreadsheet for column names
               add_pk         whether to add auto-increment primary key column to created tables
               assume_yes     whether to skip confirmation prompt
               limit          maximum number of rows to import per table
               offset         number of initial rows to skip from each table
               maxcount       maximum total number of rows to import over all tables
               progress       show progress bar
    """

    def build_mappings(sheets):
        """Populates source-to-table mappings for all sheets."""
        items = util.CaselessDict((n, xx[n]) for xx in db.schema.values() for n in xx)
        for sheet in sheets:
            colmapping, pk, existing_ok = collections.OrderedDict(), None, False
            tname = sheet["name"] if has_sheets else os.path.splitext(os.path.basename(infile))[0]
            if args.table_name: tname = args.table_name

            sourcecols = sheet["columns"] if has_names or args.row_header else \
                         [util.make_spreadsheet_column(i) for i in range(len(sheet["columns"]))]

            if not args.create_always:
                # Find closest matching table, with the least number of columns and preferably matching names
                candidates = [] # [(whether column names match, table column names, {item}), ]
                name_matches = lambda s: re.match(r"%s(_\d+)?" % re.escape(tname), s, re.I)
                for item in (x for x in items.values() if "table" == x["type"] and name_matches(x["name"])):
                    tablecols = [x["name"] for x in item["columns"]]
                    if len(tablecols) >= len(sourcecols):
                        cols_match = (has_names or args.row_header) and \
                                     all(any(util.lceq(a, b) for b in tablecols) for a in sourcecols)
                        candidates.append((cols_match, tablecols, item))
                for cols_match, tablecols, item in sorted(candidates, key=lambda x: (not x[0], len(x[1]))):
                    tname, existing_ok = item["name"], True
                    if cols_match:
                        colmapping.update((a if has_names else i,
                                           next(b for b in tablecols if util.lceq(a, b)))
                                          for i, a in enumerate(sourcecols))
                    else:
                        colmapping.update(enumerate(tablecols[:len(sourcecols)]))
                    break # for
            if not existing_ok:
                tname = util.make_unique(tname, items)
                if has_names: colmapping.update(zip(sourcecols, sourcecols))
                else: colmapping.update(enumerate(sourcecols))
                if args.add_pk: pk = util.make_unique("id", list(colmapping.values()))
                item = {"name": tname, "type": "table",
                        "columns": ([{"name": pk, "pk": {"autoincrement": True}}] if pk else []) + 
                                   [{"name": n} for n in colmapping.values()]}

            sheettotal = sheet["rows"]
            if args.row_header and not has_names and sheet["rows"] != -1: sheettotal -= 1
            sheet.update(table=tname, tablecolumns=colmapping, tablepk=pk, count=None,
                         total=sheettotal, type="sheet" if has_sheets else None)
            if not existing_ok: items[tname] = item


    validate_args("import", args)
    entity_rgx = util.filters_to_regex(args.filter) if args.filter else None
    dbname, file_existed, total = args.OUTFILE, os.path.isfile(args.OUTFILE), 0
    db = database.Database(dbname)

    output()
    progressargs = dict(pulse=True, interval=0.05) if args.progress else dict(static=True)
    bar = util.ProgressBar(**progressargs)
    try:
        args.progress and bar.start()
        bar.update(afterword=" Examining data")
        info = importexport.get_import_file_data(infile)
        if args.progress: bar.pause, _ = True, output()
        has_sheets, has_names = "xls" in info["format"], info["format"] in ("json", "yaml")
        output()
        output("Import from: %s (%s%s)", info["name"], util.format_bytes(info["size"]),
               ", %s" % util.plural("sheet", info["sheets"]) if has_sheets else "")

        sheets = info["sheets"]
        if entity_rgx: sheets = [x for x in sheets if entity_rgx.match(x["name"])]
        if not sheets:
            extra = "" if not args.filter else " using sheet filter: %s" % " ".join(args.filter)
            output()
            sys.exit("Nothing to import from %s%s." % (infile, extra))
        sheets = [x for x in sheets if x["rows"]]
        if not sheets:
            output()
            sys.exit("Nothing to import from %s." % infile)
        output("Import into: %s (%s)", db.name,
                util.format_bytes(db.filesize) if file_existed else "new file")

        bar.update(afterword=" Parsing schema", pause=False)
        db.populate_schema(parse=True)
        if args.progress: bar.pause, _ = True, output()
        build_mappings(sheets)

        output()
        output("Importing%s:", " " + util.plural("sheet", sheets) if has_sheets else "")
        for sheet in sheets:
            output("- %s (%s%s) into %stable %s",
                grammar.quote(sheet["name"], force=True) if has_sheets else sheet["name"],
                util.plural("column", sheet["columns"]),
                ", %s" % util.plural("row", sheet["total"]) if sheet["total"] >= 0 else "",
                "" if sheet["table"] in db.schema["table"] else "new ",
                grammar.quote(sheet["table"], force=True)
            )
            output("  Mapping from source columns to table columns:")
            maxlen1 = max(len(grammar.quote(a, force=True)) for a in sheet["columns"])
            for i, (a, b) in enumerate(sheet["tablecolumns"].items()):
                key1 = grammar.quote(list(sheet["columns"])[i], force=True) \
                       if has_names or args.row_header else ""
                output("  %s. %s%s -> %s",
                    ("%%%ds" % math.ceil(math.log(len(sheet["columns"]), 10))) % (i + 1),
                    key1 or "column",
                    " " * (maxlen1 - len(key1)) if key1 else "",
                    grammar.quote(b, force=True)
                )
        if not args.assume_yes:
            output()
            output("Proceed with import? (Y/n) ", end="")
            resp = six.moves.input().strip()
            if resp.lower() not in ("", "y", "yes"):
                return

        entities = util.CaselessDict(((x["name"], x) for x in sheets), insertorder=True)
        reports = []
        tables = [{"name": x["table"], "source": x["name"], "pk": x.get("tablepk"),
                   "columns": x["tablecolumns"]} for x in sheets]
        progress = make_progress("import", entities, args, reports=reports)
        limit = None if (args.limit < 0 and not args.offset) else (args.limit, ) \
                if not args.offset else (args.limit, args.offset)
        maxcount = args.maxcount
        bar.update(afterword=" Importing")
        importexport.import_data(infile, db, tables, args.row_header, limit, maxcount, progress)

    except Exception:
        _, e, tb = sys.exc_info()
        bar.stop()
        output()
        output("Error reading %s.", infile, file=sys.stderr)
        six.reraise(type(e), e, tb)
    else:
        bar.update(afterword=" Finalizing", pause=False)
        db.close()
        if args.progress: bar.update(value=100, pulse=False)
        bar.stop()
        if args.progress: output()
        output()
        total = sum(x["count"] or 0 for x in sheets)
        errors = [x for x in reports if x.get("error")]
        for sheet in (x for x in sheets if x["count"]) if total else ():
            output("Imported %s %sto table %s%s.",
                   util.plural("row", sheet["count"] or 0),
                   "from sheet %s " % grammar.quote(sheet["name"], force=True)
                   if has_sheets else "",
                   grammar.quote(sheet["table"], force=True),
                   " (%s failed)" % (util.plural("row", sheet["errorcount"]))
                   if sheet.get("errorcount") else "")
        if total:
            output("Import complete, %s inserted to %s (%s).",
                   util.plural("row", total), db.name,
                   util.format_bytes(db.get_size()))
            if any (x.get("errorcount") for x in sheets):
                output("Failed to insert %s.",
                       util.plural("row", sum(x.get("errorcount") or 0 for x in sheets)))
        else:
            output("Nothing imported.")
        if errors:
            output()
            output("Errors encountered:")
            for result in errors:
                output("- %s%s", "sheet %s: " % grammar.quote(result["name"], force=True)
                                 if has_sheets and result.get("name") else "", result["error"])

    finally:
        util.try_ignore(db.close)
        if not total and not file_existed:
            util.try_ignore(os.unlink, dbname)


def run_gui(filenames):
    """Main GUI program entrance."""
    global logger, window
    filenames = list(filter(os.path.isfile, filenames))

    # Set up logging to GUI log window
    logger.addHandler(guibase.GUILogHandler())
    logger.setLevel(logging.DEBUG)

    singlechecker = util.SingleInstanceChecker(conf.IPCName, appname=conf.Title)
    if not conf.AllowMultipleInstances and singlechecker.IsAnotherRunning():
        data = list(map(os.path.realpath, filenames))
        if singlechecker.SendToOther(data, conf.IPCPort):
            info = " (PID %s)" % singlechecker.GetOtherPid() if singlechecker.GetOtherPid() else ""
            sys.exit("Another instance of %s seems to be running%s: exiting." % (conf.Title, info))
        else: logger.error("Failed to communicate with other running instance.")

    install_thread_excepthook()
    sys.excepthook = except_hook

    # Create application main window
    app = MainApp(redirect=True) # stdout and stderr redirected to wx popup
    app.SingleChecker, singlechecker = singlechecker, None
    window = gui.MainWindow()
    app.SetTopWindow(window) # stdout/stderr popup closes with MainWindow

    if "posix" == os.name:
        # Override stdout/stderr.write to swallow Gtk deprecation warnings
        swallow = lambda w, s: None if ("Gtk" in s and "eprecat" in s) else w(s)
        try:
            sys.stdout.write = functools.partial(swallow, sys.stdout.write)
            sys.stderr.write = functools.partial(swallow, sys.stderr.write)
        except Exception: pass

    # Some debugging support
    window.run_console("import datetime, os, re, time, sys, wx")
    window.run_console("# All %s modules:" % conf.Title)
    window.run_console("from sqlitely import components, conf, database, grammar, "
                       "guibase, gui, images, importexport, main, scheme, "
                       "searchparser, support, templates, workers")
    window.run_console("from sqlitely.lib import controls, util, wx_accel")

    window.run_console("self = wx.GetApp().TopWindow # Application main window")
    for f in filenames:
        wx.CallAfter(wx.PostEvent, window, gui.OpenDatabaseEvent(-1, file=f))
    try: app.MainLoop()
    finally: del app.SingleChecker


def run(nogui=False):
    """Parses command-line arguments, and runs GUI or a CLI action."""
    global is_gui_possible, logger

    warnings.simplefilter("ignore", UnicodeWarning)

    if (getattr(sys, "frozen", False) # Binary application
    or sys.executable.lower().endswith("pythonw.exe")):
        sys.stdout = ConsoleWriter(sys.stdout) # Hooks for attaching to
        sys.stderr = ConsoleWriter(sys.stderr) # a text console
    if "main" not in sys.modules: # E.g. setuptools install, calling main.run
        srcdir = os.path.abspath(os.path.dirname(__file__))
        if srcdir not in sys.path: sys.path.append(srcdir)
        #sys.modules["main"] = __import__("main")

    argparser = argparse.ArgumentParser(description=ARGUMENTS["description"])
    for arg in map(dict, ARGUMENTS["arguments"]):
        argparser.add_argument(*arg.pop("args"), **arg)
    subparsers = argparser.add_subparsers(dest="command")
    for cmd in ARGUMENTS["commands"]:
        kwargs = dict((k, cmd[k]) for k in ["help", "description"] if k in cmd)
        kwargs.update(formatter_class=argparse.RawTextHelpFormatter)
        subparser = subparsers.add_parser(cmd["name"], **kwargs)
        for arg in map(dict, cmd["arguments"]):
            subparser.add_argument(*arg.pop("args"), **arg)

    argv = sys.argv[:]
    if "nt" == os.name and six.PY2: # Fix Unicode arguments, otherwise converted to ?
        argv = util.win32_unicode_argv()
    argv = argv[1:]

    if not argv or not any(x in argv for x in tuple(subparsers.choices) + ("-h", "--help")):
        argv[:0] = ["gui"] # argparse hack: force default argument
    if argv[0] in ("-h", "--help") and len(argv) > 1:
        argv[:2] = argv[:2][::-1] # Swap "-h option" to "option -h"

    arguments, _ = argparser.parse_known_args(argv)
    infile0, outfile0 = (getattr(arguments, x, None) for x in ("INFILE", "OUTFILE"))

    for argname in ("INFILE", "OUTFILE"):
        filearg = filearg0 = getattr(arguments, argname, [])
        if filearg:
            filearg = sorted(set(util.to_unicode(f) for f in util.tuplefy(filearg)))
            filearg = sum([sorted(glob.glob(f)) if "*" in f else [f]
                           for f in filearg], []) if "INFILE" == argname else filearg
            filearg = list(map(util.longpath, filearg))
            setattr(arguments, argname, filearg if isinstance(filearg0, list) else
                                        filearg[0] if filearg else None)

    conf.load(arguments.config_file)
    database.register_types()
    if "gui" == arguments.command and (nogui or not is_gui_possible):
        argparser.print_help()
        status = None
        if not nogui: status = ("\n\nwxPython not found. %s graphical program "
                                "will not run." % conf.Title)
        sys.exit(status)
    elif "gui" != arguments.command:
        if six.PY2:
            # Avoid Unicode errors when printing to console.
            enc = sys.stdout.encoding or locale.getpreferredencoding() or "utf-8"
            sys.stdout = codecs.getwriter(enc)(sys.stdout, "backslashreplace")
            sys.stderr = codecs.getwriter(enc)(sys.stderr, "backslashreplace")

        if arguments.verbose:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter("%(asctime)s\t%(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        else:
            logger.addHandler(logging.NullHandler())

    if "gui" == arguments.command:
        try: run_gui(arguments.INFILE)
        except Exception: traceback.print_exc()
        return

    if not arguments.INFILE and infile0:
        sys.exit("File not found: %s" % infile0)
    if not os.path.isfile(arguments.INFILE):
        sys.exit("File not found: %s" % arguments.INFILE)
    if not os.path.getsize(arguments.INFILE):
        sys.exit("Empty file: %s" % arguments.INFILE)
    arguments.INFILE = os.path.normpath(arguments.INFILE)
    if getattr(arguments, "OUTFILE", None):
        arguments.OUTFILE = os.path.normpath(arguments.OUTFILE)
    if getattr(arguments, "INFILE", None) and getattr(arguments, "OUTFILE", None):
        if os.path.realpath(arguments.INFILE) == os.path.realpath(arguments.OUTFILE):
            sys.exit("Input file and output file are the same file.")

    if "export" == arguments.command:
        run_export(arguments.INFILE, arguments)
    elif "import" == arguments.command:
        run_import(arguments.INFILE, arguments)
    elif "parse" == arguments.command:
        run_parse(arguments.INFILE, arguments)
    elif "search" == arguments.command:
        run_search(arguments.INFILE, arguments)
    elif "stats" == arguments.command:
        run_stats(arguments.INFILE, arguments)



if "__main__" == __name__:
    try: run()
    except KeyboardInterrupt: sys.exit()
