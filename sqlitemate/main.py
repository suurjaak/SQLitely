# -*- coding: utf-8 -*-
"""
SQLiteMate main program entrance: launches GUI application,
handles logging and status calls.

------------------------------------------------------------------------------
This file is part of SQLiteMate - SQLite database tool.
Released under the MIT License.

@author      Erki Suurjaak
@created     21.08.2019
@modified    26.08.2019
------------------------------------------------------------------------------
"""
from __future__ import print_function
import argparse
import datetime
import glob
import os
import sys

import wx

from lib import util
import conf
import guibase
import gui


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
    arguments, _ = argparser.parse_known_args(argv)

    if arguments.FILE: # Expand wildcards to actual filenames
        arguments.FILE = sum([glob.glob(f) if "*" in f else [f]
                              for f in arguments.FILE], [])
        arguments.FILE = sorted(set(util.to_unicode(f) for f in arguments.FILE))

    run_gui(arguments.FILE)


def win32_unicode_argv():
    """
    Returns Windows command-line arguments converted to Unicode.

    @from    http://stackoverflow.com/a/846931/145400
    """
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


if "__main__" == __name__:
    run()
