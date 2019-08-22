# -*- coding: utf-8 -*-
"""
SQLiteMate main program entrance: launches GUI application,
handles logging and status calls.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    22.08.2019
------------------------------------------------------------------------------
"""
from __future__ import print_function
import argparse
import atexit
import codecs
import collections
import datetime
import errno
import getpass
import glob
import locale
import io
import itertools
import Queue
import os
import shutil
import sys
import threading
import time
import traceback
import warnings

import wx
try: # For printing to a console from a packaged Windows binary
    import win32console
except ImportError:
    win32console = None

from lib import util

import conf
import database
import export
import guibase
import gui
import support
import workers


ARGUMENTS = {
    "description": "%s - SQLite database tool." % conf.Title,
    "arguments": [
        {"args": ["-v", "--version"], "action": "version",
         "version": "%s %s, %s." % (conf.Title, conf.Version, conf.VersionDate)},
        {"args": ["FILE"], "nargs": "*",
         "help": "SQLite database to open on startup, if any"},
    ],
}


window = None         # Application main window instance
deferred_logs = []    # Log messages cached before main window is available
deferred_status = []  # Last status cached before main window is available


def log(text, *args):
    """
    Logs a timestamped message to main window.

    @param   args  string format arguments, if any, to substitute in text
    """
    global deferred_logs, window
    now = datetime.datetime.now()
    try:
        finaltext = text % args if args else text
    except UnicodeError:
        args = tuple(map(util.to_unicode, args))
        finaltext = text % args if args else text
    if "\n" in finaltext: # Indent all linebreaks
        finaltext = finaltext.replace("\n", "\n\t\t")
    msg = "%s.%03d\t%s" % (now.strftime("%H:%M:%S"), now.microsecond / 1000,
                           finaltext)
    if window:
        process_deferreds()
        wx.PostEvent(window, guibase.LogEvent(text=msg))
    else:
        deferred_logs.append(msg)


def status(text, *args):
    """
    Sets main window status text.

    @param   args  string format arguments, if any, to substitute in text
    """
    global deferred_status, window
    try:
        msg = text % args if args else text
    except UnicodeError:
        args = tuple(map(util.to_unicode, args))
        msg = text % args if args else text
    if window:
        process_deferreds()
        wx.PostEvent(window, guibase.StatusEvent(text=msg))
    else:
        deferred_status[:] = [msg]



def status_flash(text, *args):
    """
    Sets main window status text that will be cleared after a timeout.

    @param   args  string format arguments, if any, to substitute in text
    """
    global deferred_status, window
    try:
        msg = text % args if args else text
    except UnicodeError:
        args = tuple(map(util.to_unicode, args))
        msg = text % args if args else text
    if window:
        process_deferreds()
        wx.PostEvent(window, guibase.StatusEvent(text=msg))
        def clear_status():
            if window.StatusBar and window.StatusBar.StatusText == msg:
                window.SetStatusText("")
        wx.CallLater(conf.StatusFlashLength, clear_status)
    else:
        deferred_status[:] = [msg]


def logstatus(text, *args):
    """
    Logs a timestamped message to main window and sets main window status text.

    @param   args  string format arguments, if any, to substitute in text
    """
    log(text, *args)
    status(text, *args)


def logstatus_flash(text, *args):
    """
    Logs a timestamped message to main window and sets main window status text
    that will be cleared after a timeout.

    @param   args  string format arguments, if any, to substitute in text
    """
    log(text, *args)
    status_flash(text, *args)


def process_deferreds():
    """
    Forwards log messages and status, cached before main window was available.
    """
    global deferred_logs, deferred_status, window
    if window:
        if deferred_logs:
            for msg in deferred_logs:
                wx.PostEvent(window, guibase.LogEvent(text=msg))
            del deferred_logs[:]
        if deferred_status:
            wx.PostEvent(window, guibase.StatusEvent(text=deferred_status[0]))
            del deferred_status[:]


def run_gui(filenames):
    """Main GUI program entrance."""
    global deferred_logs, deferred_status, window

    # Values in some threads would otherwise not be the same
    sys.modules["main"].deferred_logs = deferred_logs
    sys.modules["main"].deferred_status = deferred_status

    # Create application main window
    app = wx.App(redirect=True) # stdout and stderr redirected to wx popup
    window = sys.modules["main"].window = gui.MainWindow()
    app.SetTopWindow(window) # stdout/stderr popup closes with MainWindow
    # Decorate write to catch printed errors
    try: sys.stdout.write = support.reporting_write(sys.stdout.write)
    except Exception: pass

    # Some debugging support
    window.run_console("import datetime, os, re, time, sys, wx")
    window.run_console("# All %s modules:" % conf.Title)
    window.run_console("import conf, database, export, guibase, gui, images, "
                       "main, searchparser, support, templates, workers")
    window.run_console("from lib import controls, util, wx_accel")

    window.run_console("self = main.window # Application main window instance")
    log("Started application on %s.", datetime.date.today())
    for f in filter(os.path.isfile, filenames):
        wx.CallAfter(wx.PostEvent, window, gui.OpenDatabaseEvent(file=f))
    app.MainLoop()


def run():
    """Parses command-line arguments and runs GUI."""
    if (getattr(sys, 'frozen', False) # Binary application
    or sys.executable.lower().endswith("pythonw.exe")):
        sys.stdout = ConsoleWriter(sys.stdout) # Hooks for attaching to 
        sys.stderr = ConsoleWriter(sys.stderr) # a text console
    if "main" not in sys.modules: # E.g. setuptools install, calling main.run
        srcdir = os.path.abspath(os.path.dirname(__file__))
        if srcdir not in sys.path: sys.path.append(srcdir)
        sys.modules["main"] = __import__("main")

    argparser = argparse.ArgumentParser(description=ARGUMENTS["description"])
    for arg in ARGUMENTS["arguments"]:
        argparser.add_argument(*arg.pop("args"), **arg)

    argv = sys.argv[1:]
    if "nt" == os.name: # Fix Unicode arguments, otherwise converted to ?
        argv = win32_unicode_argv()[1:]
    arguments = argparser.parse_args(argv)

    if hasattr(arguments, "FILE1") and hasattr(arguments, "FILE2"):
        arguments.FILE1 = [util.to_unicode(f) for f in arguments.FILE1]
        arguments.FILE2 = [util.to_unicode(f) for f in arguments.FILE2]
        arguments.FILE = arguments.FILE1 + arguments.FILE2
    if arguments.FILE: # Expand wildcards to actual filenames
        arguments.FILE = sum([glob.glob(f) if "*" in f else [f]
                              for f in arguments.FILE], [])
        arguments.FILE = sorted(set(util.to_unicode(f) for f in arguments.FILE))

    run_gui(arguments.FILE)


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
                try:
                    win32console.AttachConsole(-1) # pythonw.exe from console
                    atexit.register(lambda: ConsoleWriter.realwrite("\n"))
                except Exception:
                    pass # Okay if fails: can be python.exe from console
                try:
                    handle = win32console.GetStdHandle(
                                          win32console.STD_OUTPUT_HANDLE)
                    handle.WriteConsole("\n" + text)
                    ConsoleWriter.handle = handle
                    ConsoleWriter.realwrite = handle.WriteConsole
                except Exception: # Fails if GUI program: make new console
                    try: win32console.FreeConsole()
                    except Exception: pass
                    try:
                        win32console.AllocConsole()
                        handle = open("CONOUT$", "w")
                        argv = [util.longpath(sys.argv[0])] + sys.argv[1:]
                        handle.write(" ".join(argv) + "\n\n" + text)
                        handle.flush()
                        ConsoleWriter.handle = handle
                        ConsoleWriter.realwrite = handle.write
                        sys.stdin = open("CONIN$", "r")
                        exitfunc = lambda s: (handle.write(s), handle.flush(),
                                              raw_input())
                        atexit.register(exitfunc, "\nPress ENTER to exit.")
                    except Exception:
                        try: win32console.FreeConsole()
                        except Exception: pass
                        ConsoleWriter.realwrite = self.stream.write
                ConsoleWriter.is_loaded = True
            else:
                try:
                    self.realwrite(text)
                    self.flush()
                except Exception:
                    self.stream.write(text)
        else:
            self.stream.write(text)


def win32_unicode_argv():
    # @from http://stackoverflow.com/a/846931/145400
    result = sys.argv
    from ctypes import POINTER, byref, cdll, c_int, windll
    from ctypes.wintypes import LPCWSTR, LPWSTR
 
    GetCommandLineW = cdll.kernel32.GetCommandLineW
    GetCommandLineW.argtypes = []
    GetCommandLineW.restype = LPCWSTR
 
    CommandLineToArgvW = windll.shell32.CommandLineToArgvW
    CommandLineToArgvW.argtypes = [LPCWSTR, POINTER(c_int)]
    CommandLineToArgvW.restype = POINTER(LPWSTR)
 
    argc = c_int(0)
    argv = CommandLineToArgvW(GetCommandLineW(), byref(argc))
    if argc.value:
        # Remove Python executable and commands if present
        start = argc.value - len(sys.argv)
        result = [argv[i].encode("utf-8") for i in range(start, argc.value)]
    return result


def output(*args, **kwargs):
    """Print wrapper, avoids "Broken pipe" errors if piping is interrupted."""
    print(*args, **kwargs)
    try:
        sys.stdout.flush() # Uncatchable error otherwise if interrupted
    except IOError as e:
        if e.errno in (errno.EINVAL, errno.EPIPE):
            sys.exit() # Stop work in progress if sys.stdout or pipe closed
        raise # Propagate any other errors


if "__main__" == __name__:
    try: run()
    except KeyboardInterrupt: sys.exit()
